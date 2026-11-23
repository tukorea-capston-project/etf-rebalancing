"""시세·분배금 수집 로직. 설계는 docs/market-data.md.

CLI(`python -m app.market_data`)와 (나중의) 워커가 `run_collection`을 부른다.
출처(KRX, yfinance)는 아래 Protocol로만 다루므로, 출처를 바꿔도 이 파일은 고치지 않는다.
"""

import logging
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, col, select

from app.core.config import Settings
from app.market_data.models import (
    CollectionStatus,
    DistributionSource,
    EtfDailyPrice,
    EtfDistribution,
    PriceCollectionLog,
)
from app.market_data.overrides import DistributionOverride, load_overrides

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
# KRX ETF 일별매매정보가 2010년 이후만 있다. 분배금도 같은 기간만 저장한다.
COLLECTION_START = date(2010, 1, 1)


# --- 출처 인터페이스 ---------------------------------------------------------


@dataclass(frozen=True)
class DailyQuote:
    """하루치 ETF 시세 한 행. 휴장일 행은 close가 None이다."""

    trade_date: date
    code: str
    name: str
    close: int | None
    change: int | None = None
    change_rate: Decimal | None = None
    nav: Decimal | None = None
    open: int | None = None
    high: int | None = None
    low: int | None = None
    volume: int | None = None
    trade_value: int | None = None
    market_cap: int | None = None
    net_assets: int | None = None
    listed_shares: int | None = None
    index_name: str | None = None
    index_close: Decimal | None = None
    index_change: Decimal | None = None
    index_change_rate: Decimal | None = None


@dataclass(frozen=True)
class Distribution:
    ex_date: date  # 분배락일
    amount: Decimal  # 주당 분배금(세전, 원)


class SourceUnavailableError(Exception):
    """출처가 오류 응답을 줬다(인증·한도·서버 오류). 그 출처의 수집을 멈춘다."""


class FetchError(Exception):
    """재시도 후에도 네트워크 오류로 한 건을 받지 못했다. 그 건만 실패로 두고 계속한다."""


class DailyPriceSource(Protocol):
    def fetch_daily(self, trade_date: date) -> list[DailyQuote]:
        """그날의 전체 ETF 시세. 아직 제공 전이면 빈 목록이다."""
        ...


class DistributionHistorySource(Protocol):
    def fetch_distributions(self, code: str) -> list[Distribution]:
        """그 ETF의 전체 분배금 이력."""
        ...


# --- 실행 결과 ---------------------------------------------------------------


@dataclass
class CollectionReport:
    krx_calls: int = 0
    statuses: Counter[CollectionStatus] = field(default_factory=Counter)
    saved_rows: int = 0
    stopped_reason: str | None = None  # 시세 수집을 중간에 멈춘 이유
    refilled_days: int = 0  # ETF 전체를 다시 받아 빠진 행을 채운 영업일 수
    distribution_codes_updated: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def has_problems(self) -> bool:
        return (
            self.stopped_reason is not None
            or self.statuses[CollectionStatus.FAILED] > 0
            or bool(self.warnings)
        )


# --- 시세 ----------------------------------------------------------------------


class _CallBudget:
    def __init__(self, limit: int, report: CollectionReport) -> None:
        self.limit = limit
        self.report = report

    def exhausted(self) -> bool:
        return self.report.krx_calls >= self.limit


def today_kst() -> date:
    return datetime.now(KST).date()


def _now() -> datetime:
    return datetime.now(UTC)


def _dates_to_fetch(session: Session, today: date) -> tuple[list[date], set[date]]:
    """받을 날짜와, 그중 ETF 전체를 다시 받아 채울 영업일.

    받을 날짜: 수집 이력에 없거나, 대기·실패로 남았거나, ETF 전체를 저장하지 않은 영업일.
    """
    logs = session.exec(
        select(
            col(PriceCollectionLog.trade_date),
            col(PriceCollectionLog.status),
            col(PriceCollectionLog.all_etfs_saved),
        )
    ).all()
    settled: set[date] = set()
    refill: set[date] = set()
    for trade_date, status, all_etfs_saved in logs:
        if status == CollectionStatus.HOLIDAY:
            settled.add(trade_date)
        elif status == CollectionStatus.BUSINESS_DAY:
            (settled if all_etfs_saved else refill).add(trade_date)
    days = (today - COLLECTION_START).days + 1
    all_dates = (COLLECTION_START + timedelta(days=i) for i in range(days))
    return [d for d in all_dates if d not in settled], refill


def _classify(
    quotes: Sequence[DailyQuote], trade_date: date, today: date, pending_days: int
) -> CollectionStatus:
    if any(q.close is not None for q in quotes):
        return CollectionStatus.BUSINESS_DAY
    if quotes:  # 행은 왔지만 종가가 모두 비었다
        return CollectionStatus.HOLIDAY
    # 빈 목록: 아직 제공 전일 수 있다
    if (today - trade_date).days < pending_days:
        return CollectionStatus.PENDING
    return CollectionStatus.HOLIDAY


def _save_quotes(session: Session, quotes: Iterable[DailyQuote]) -> tuple[int, int]:
    """종가 있는 행을 ETF 전체 저장한다. 이미 있는 행은 덮어쓰지 않는다.

    (그날 종가 있는 행 수, 새로 넣은 행 수)를 돌려준다.
    """
    rows = [
        asdict(q)  # DailyQuote 필드는 etf_daily_price 컬럼과 같다
        for q in quotes
        if q.close is not None
    ]
    if not rows:
        return 0, 0
    inserted = session.exec(
        insert(EtfDailyPrice)
        .values(rows)
        .on_conflict_do_nothing()
        .returning(col(EtfDailyPrice.code))
    ).all()
    return len(rows), len(inserted)


def _write_log(
    session: Session,
    trade_date: date,
    status: CollectionStatus,
    saved_rows: int | None = None,
    error: str | None = None,
) -> None:
    values = {
        "trade_date": trade_date,
        "status": status,
        "saved_rows": saved_rows,
        "error": error,
        "checked_at": _now(),
        "all_etfs_saved": status == CollectionStatus.BUSINESS_DAY,
    }
    stmt = insert(PriceCollectionLog).values(values)
    session.exec(
        stmt.on_conflict_do_update(
            index_elements=["trade_date"],
            set_={k: v for k, v in values.items() if k != "trade_date"},
        )
    )


def collect_prices(
    session: Session,
    source: DailyPriceSource,
    today: date,
    settings: Settings,
    report: CollectionReport,
) -> None:
    """수집 이력에 없거나 대기·실패로 남은 날짜, ETF 전체를 저장하지 않은 영업일의 시세를 받는다.

    ETF 전체를 다시 받는 영업일(전체 저장 전에 수집한 날짜)은 빠진 행만 채우고, 받지 못해도
    영업일 기록은 그대로 둔다. 과거 영업일 달력이 비지 않게 하려는 것이다.
    """
    budget = _CallBudget(settings.krx_max_calls_per_run, report)
    dates, refill = _dates_to_fetch(session, today)
    logger.info(
        "시세 수집 대상 날짜: %d일 (ETF 전체 재수집 %d일)", len(dates), len(refill)
    )
    for i, trade_date in enumerate(dates, 1):
        if i % 100 == 0:
            logger.info("시세 수집 %d/%d (%s)", i, len(dates), trade_date)
        if budget.exhausted():
            report.stopped_reason = f"실행당 KRX 호출 상한({budget.limit}회)에 도달했다"
            return
        is_refill = trade_date in refill
        report.krx_calls += 1
        try:
            quotes = source.fetch_daily(trade_date)
        except SourceUnavailableError as e:
            if not is_refill:
                _write_log(session, trade_date, CollectionStatus.FAILED, error=str(e))
                session.commit()
                report.statuses[CollectionStatus.FAILED] += 1
            report.stopped_reason = f"KRX 오류 응답으로 멈췄다: {e}"
            return
        except FetchError as e:
            if is_refill:
                report.warnings.append(f"{trade_date} 영업일을 다시 받지 못했다: {e}")
                continue
            _write_log(session, trade_date, CollectionStatus.FAILED, error=str(e))
            session.commit()
            report.statuses[CollectionStatus.FAILED] += 1
            logger.warning("%s 시세를 받지 못했다: %s", trade_date, e)
            continue

        status = _classify(quotes, trade_date, today, settings.krx_pending_days)
        if is_refill and status != CollectionStatus.BUSINESS_DAY:
            report.warnings.append(
                f"{trade_date}는 영업일로 기록돼 있는데 다시 받은 응답에 종가가 없다"
            )
            continue
        saved = None
        if status == CollectionStatus.BUSINESS_DAY:
            saved, inserted = _save_quotes(session, quotes)
            report.saved_rows += inserted
            if is_refill:
                report.refilled_days += 1
        _write_log(session, trade_date, status, saved_rows=saved)
        session.commit()
        report.statuses[status] += 1


# --- 분배금 --------------------------------------------------------------------


def _apply_overrides(
    session: Session, code: str, overrides: Sequence[DistributionOverride]
) -> None:
    for o in overrides:
        if o.code != code:
            continue
        if o.delete:
            session.exec(
                delete(EtfDistribution).where(
                    col(EtfDistribution.code) == o.code,
                    col(EtfDistribution.ex_date) == o.ex_date,
                )
            )
            continue
        values = {
            "code": o.code,
            "ex_date": o.ex_date,
            "amount": o.amount,
            "source": DistributionSource.OVERRIDE,
        }
        session.exec(
            insert(EtfDistribution)
            .values(values)
            .on_conflict_do_update(
                index_elements=["code", "ex_date"],
                set_={"amount": o.amount, "source": DistributionSource.OVERRIDE},
            )
        )


def refresh_distributions(
    session: Session,
    source: DistributionHistorySource,
    codes: set[str],
    overrides: Sequence[DistributionOverride],
    report: CollectionReport,
) -> None:
    """② ETF별 분배금 전체 이력을 다시 받아 바꾸고, 그 위에 보정 YAML을 적용한다."""
    for code in sorted(codes):
        try:
            fetched = [
                d
                for d in source.fetch_distributions(code)
                if d.ex_date >= COLLECTION_START
            ]
        except (FetchError, SourceUnavailableError) as e:
            report.warnings.append(f"{code} 분배금을 받지 못해 기존 값을 유지했다: {e}")
            _apply_overrides(session, code, overrides)
            session.commit()
            continue

        if not fetched:
            existing = session.exec(
                select(col(EtfDistribution.ex_date)).where(
                    EtfDistribution.code == code,
                    EtfDistribution.source == DistributionSource.YFINANCE,
                )
            ).first()
            if existing is not None:
                report.warnings.append(
                    f"{code} 분배금이 0건으로 왔지만 DB에는 있어 기존 값을 유지했다"
                )
                _apply_overrides(session, code, overrides)
                session.commit()
                continue

        session.exec(delete(EtfDistribution).where(col(EtfDistribution.code) == code))
        session.add_all(
            EtfDistribution(
                code=code,
                ex_date=d.ex_date,
                amount=d.amount,
                source=DistributionSource.YFINANCE,
            )
            for d in fetched
        )
        session.flush()
        _apply_overrides(session, code, overrides)
        session.commit()
        report.distribution_codes_updated += 1


# 분배율(주당 분배금 ÷ 분배락 전일 종가)이 이 범위 밖이면 단위 오류 등을 의심한다.
MIN_DISTRIBUTION_YIELD = Decimal("0.0001")  # 0.01%
MAX_DISTRIBUTION_YIELD = Decimal("0.10")  # 10%


def _previous_close(session: Session, code: str, ex_date: date) -> int | None:
    """분배락 전일 종가. 그 전에 시세가 없으면(초기 적재 전 등) None이다."""
    return session.exec(
        select(EtfDailyPrice.close)
        .where(
            col(EtfDailyPrice.code) == code,
            col(EtfDailyPrice.trade_date) < ex_date,
        )
        .order_by(col(EtfDailyPrice.trade_date).desc())
        .limit(1)
    ).first()


def check_distributions(
    session: Session, codes: set[str], report: CollectionReport
) -> None:
    """③ yfinance 분배금 중 의심 건을 경고한다.

    보정 YAML로 확인·수정한 항목(source=override)은 건너뛴다. 값이 맞는 의심 건은
    보정 YAML에 같은 금액과 근거를 적으면 경고가 꺼진다.
    """
    rows = session.exec(
        select(EtfDistribution)
        .where(
            col(EtfDistribution.code).in_(codes),
            EtfDistribution.source == DistributionSource.YFINANCE,
        )
        .order_by(col(EtfDistribution.code), col(EtfDistribution.ex_date))
    ).all()
    for row in rows:
        label = f"{row.code} {row.ex_date} 분배금 {row.amount}원"
        # 주당 분배금은 원 단위 정수다. 소수는 단위·구분 기호를 잘못 읽은 값일 수 있다.
        if row.amount != row.amount.to_integral_value():
            report.warnings.append(f"점검: {label}이 정수가 아니다")
            continue
        close = _previous_close(session, row.code, row.ex_date)
        if close is None or close <= 0:
            continue
        rate = row.amount / close
        if not MIN_DISTRIBUTION_YIELD <= rate <= MAX_DISTRIBUTION_YIELD:
            report.warnings.append(
                f"점검: {label}의 분배율 {rate:.4%}가 범위"
                f"({MIN_DISTRIBUTION_YIELD:.2%}~{MAX_DISTRIBUTION_YIELD:.0%}) 밖이다"
                f" (전일 종가 {close}원)"
            )


# --- 전체 실행 -----------------------------------------------------------------


def stored_codes(session: Session) -> set[str]:
    """시세가 한 번이라도 저장된 ETF 전체. 상장폐지된 ETF도 들어 있다."""
    return set(session.exec(select(EtfDailyPrice.code).distinct()).all())


def run_collection(
    session: Session,
    price_source: DailyPriceSource,
    distribution_source: DistributionHistorySource,
    settings: Settings,
    today: date | None = None,
) -> CollectionReport:
    """① 시세 → ② 분배금 갱신 → ③ 분배금 점검을 차례로 한다.

    분배금 대상은 DB에 시세가 있는 ETF 전체다. KRX가 멈춰도 ②·③은 진행한다(출처가 다르다).
    보정 YAML에 시세가 없는 종목코드가 있으면 오류다.
    """
    report = CollectionReport()
    collect_prices(session, price_source, today or today_kst(), settings, report)
    codes = stored_codes(session)
    overrides = load_overrides()
    unknown = sorted({o.code for o in overrides} - codes)
    if unknown:
        raise ValueError(f"보정 YAML에 시세가 없는 종목코드가 있다: {unknown}")
    refresh_distributions(session, distribution_source, codes, overrides, report)
    check_distributions(session, codes, report)
    return report
