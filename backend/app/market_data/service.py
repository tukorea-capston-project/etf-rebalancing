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
from app.core.whitelist import load_whitelist
from app.market_data.models import (
    CollectionStatus,
    DistributionSource,
    EtfBackfill,
    EtfDailyPrice,
    EtfDistribution,
    PriceCollectionLog,
)
from app.market_data.overrides import DistributionOverride, load_overrides

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
# KRX ETF 일별매매정보가 2010년 이후만 있다. 분배금도 같은 기간만 저장한다.
COLLECTION_START = date(2010, 1, 1)
# 백테스트 비교 기준. 화이트리스트에 없어도 수집한다.
BENCHMARK_CODE = "069500"


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
    backfilled_codes: list[str] = field(default_factory=list)
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


def target_codes() -> set[str]:
    return set(load_whitelist().codes) | {BENCHMARK_CODE}


def _now() -> datetime:
    return datetime.now(UTC)


def _dates_to_fetch(session: Session, today: date) -> list[date]:
    """수집 이력에 없거나, 대기·실패로 남은 날짜."""
    settled = set(
        session.exec(
            select(col(PriceCollectionLog.trade_date)).where(
                col(PriceCollectionLog.status).in_(
                    [CollectionStatus.BUSINESS_DAY, CollectionStatus.HOLIDAY]
                )
            )
        ).all()
    )
    days = (today - COLLECTION_START).days + 1
    all_dates = (COLLECTION_START + timedelta(days=i) for i in range(days))
    return [d for d in all_dates if d not in settled]


def _business_days(session: Session) -> list[date]:
    return sorted(
        session.exec(
            select(col(PriceCollectionLog.trade_date)).where(
                PriceCollectionLog.status == CollectionStatus.BUSINESS_DAY
            )
        ).all()
    )


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


def _save_quotes(
    session: Session, quotes: Iterable[DailyQuote], codes: set[str]
) -> int:
    """대상 ETF의 종가 있는 행만 저장한다. 이미 있는 행은 덮어쓰지 않는다."""
    rows = [
        asdict(q)  # DailyQuote 필드는 etf_daily_price 컬럼과 같다
        for q in quotes
        if q.code in codes and q.close is not None
    ]
    if not rows:
        return 0
    session.exec(insert(EtfDailyPrice).values(rows).on_conflict_do_nothing())
    return len(rows)


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
    }
    stmt = insert(PriceCollectionLog).values(values)
    session.exec(
        stmt.on_conflict_do_update(
            index_elements=["trade_date"],
            set_={k: v for k, v in values.items() if k != "trade_date"},
        )
    )


def collect_new_dates(
    session: Session,
    source: DailyPriceSource,
    codes: set[str],
    today: date,
    settings: Settings,
    budget: _CallBudget,
) -> None:
    """① 수집 이력에 없거나 대기·실패로 남은 날짜의 시세를 받는다."""
    report = budget.report
    dates = _dates_to_fetch(session, today)
    logger.info("시세 수집 대상 날짜: %d일", len(dates))
    for i, trade_date in enumerate(dates, 1):
        if i % 100 == 0:
            logger.info("시세 수집 %d/%d (%s)", i, len(dates), trade_date)
        if budget.exhausted():
            report.stopped_reason = f"실행당 KRX 호출 상한({budget.limit}회)에 도달했다"
            return
        report.krx_calls += 1
        try:
            quotes = source.fetch_daily(trade_date)
        except SourceUnavailableError as e:
            _write_log(session, trade_date, CollectionStatus.FAILED, error=str(e))
            session.commit()
            report.statuses[CollectionStatus.FAILED] += 1
            report.stopped_reason = f"KRX 오류 응답으로 멈췄다: {e}"
            return
        except FetchError as e:
            _write_log(session, trade_date, CollectionStatus.FAILED, error=str(e))
            session.commit()
            report.statuses[CollectionStatus.FAILED] += 1
            logger.warning("%s 시세를 받지 못했다: %s", trade_date, e)
            continue

        status = _classify(quotes, trade_date, today, settings.krx_pending_days)
        saved = None
        if status == CollectionStatus.BUSINESS_DAY:
            saved = _save_quotes(session, quotes, codes)
            report.saved_rows += saved
        _write_log(session, trade_date, status, saved_rows=saved)
        session.commit()
        report.statuses[status] += 1


def backfill_new_etfs(
    session: Session,
    source: DailyPriceSource,
    new_codes: set[str],
    business_days_before: list[date],
    budget: _CallBudget,
) -> None:
    """② 이번 실행 전에 이미 영업일로 기록된 날짜를 다시 받아 신규 ETF의 과거 시세를 채운다.

    이번 실행에서 새로 받은 날짜는 이미 신규 ETF를 포함하므로 다시 받지 않는다.
    모든 날짜를 받아야 완료로 기록한다. 중간에 멈추면 다음 실행 때 처음부터 다시 받는다.
    """
    report = budget.report
    if not new_codes:
        return
    complete = True
    logger.info(
        "신규 ETF %s 백필: %d영업일", sorted(new_codes), len(business_days_before)
    )
    for i, trade_date in enumerate(business_days_before, 1):
        if i % 100 == 0:
            logger.info("백필 %d/%d (%s)", i, len(business_days_before), trade_date)
        if budget.exhausted():
            report.stopped_reason = f"실행당 KRX 호출 상한({budget.limit}회)에 도달했다"
            return
        report.krx_calls += 1
        try:
            quotes = source.fetch_daily(trade_date)
        except SourceUnavailableError as e:
            report.stopped_reason = f"KRX 오류 응답으로 멈췄다: {e}"
            return
        except FetchError as e:
            complete = False
            report.warnings.append(f"백필 중 {trade_date} 시세를 받지 못했다: {e}")
            continue
        report.saved_rows += _save_quotes(session, quotes, new_codes)
        session.commit()

    if complete:
        _mark_backfilled(session, new_codes, report)


def _mark_backfilled(
    session: Session, codes: set[str], report: CollectionReport
) -> None:
    now = _now()
    for code in sorted(codes):
        session.add(EtfBackfill(code=code, completed_at=now))
    session.commit()
    report.backfilled_codes = sorted(codes)


def collect_prices(
    session: Session,
    source: DailyPriceSource,
    codes: set[str],
    today: date,
    settings: Settings,
    report: CollectionReport,
) -> None:
    budget = _CallBudget(settings.krx_max_calls_per_run, report)
    done = set(session.exec(select(EtfBackfill.code)).all())
    new_codes = codes - done
    # 백필 대상 날짜는 ① 전에 정해 둔다. ①에서 새로 받은 날짜는 신규 ETF를 이미 포함한다.
    business_days_before = _business_days(session) if new_codes else []
    if new_codes and not business_days_before:
        # 다시 받을 과거 영업일이 없다(초기 적재 등). 앞으로 받는 날짜는 모두 이 ETF를
        # 포함하므로 바로 완료로 기록한다. ①이 중간에 멈춰도 다음 실행에 중복 호출이 없다.
        _mark_backfilled(session, new_codes, report)
        new_codes = set()

    collect_new_dates(session, source, codes, today, settings, budget)
    if report.stopped_reason is None:
        backfill_new_etfs(session, source, new_codes, business_days_before, budget)


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
    """③ ETF별 분배금 전체 이력을 다시 받아 바꾸고, 그 위에 보정 YAML을 적용한다."""
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


# --- 전체 실행 -----------------------------------------------------------------


def run_collection(
    session: Session,
    price_source: DailyPriceSource,
    distribution_source: DistributionHistorySource,
    settings: Settings,
    today: date | None = None,
) -> CollectionReport:
    """① 날짜별 시세 → ② 신규 ETF 백필 → ③ 분배금 갱신을 차례로 한다.

    KRX가 멈춰도 ③은 진행한다(출처가 다르다).
    """
    report = CollectionReport()
    codes = target_codes()
    overrides = load_overrides(codes)
    collect_prices(session, price_source, codes, today or today_kst(), settings, report)
    refresh_distributions(session, distribution_source, codes, overrides, report)
    return report
