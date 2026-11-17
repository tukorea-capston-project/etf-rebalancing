"""수집 흐름 테스트. KRX·yfinance 대신 가짜 출처를 쓰고, 테스트 DB에 저장한다."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlmodel import Session, col, select

from app.core.config import Settings
from app.market_data.models import (
    CollectionStatus,
    DistributionSource,
    EtfBackfill,
    EtfDailyPrice,
    EtfDistribution,
    PriceCollectionLog,
)
from app.market_data.overrides import DistributionOverride
from app.market_data.service import (
    CollectionReport,
    DailyQuote,
    Distribution,
    FetchError,
    SourceUnavailableError,
    collect_prices,
    refresh_distributions,
)

# 2010-01-01 ~ 2010-01-10 열흘만 수집하도록 '오늘'을 고정한다.
TODAY = date(2010, 1, 10)
CODES = {"069500", "0184E0"}


def d(day: int) -> date:
    return date(2010, 1, day)


def quote(day: int, code: str, close: int | None = 100) -> DailyQuote:
    return DailyQuote(trade_date=d(day), code=code, name=f"ETF {code}", close=close)


def business(day: int, close: int = 100) -> list[DailyQuote]:
    """대상 ETF 두 개와 대상이 아닌 ETF 하나가 있는 영업일."""
    return [quote(day, c, close) for c in ["069500", "0184E0", "999999"]]


def holiday(day: int) -> list[DailyQuote]:
    return [quote(day, c, None) for c in ["069500", "0184E0", "999999"]]


class FakeKrx:
    """날짜별 응답을 정해 두는 가짜 KRX. 정하지 않은 날짜는 휴장일 행을 돌려준다."""

    def __init__(self, responses: dict[date, list[DailyQuote] | Exception]) -> None:
        self.responses = responses
        self.calls: list[date] = []

    def fetch_daily(self, trade_date: date) -> list[DailyQuote]:
        self.calls.append(trade_date)
        response = self.responses.get(trade_date, holiday(trade_date.day))
        if isinstance(response, Exception):
            raise response
        return response


class FakeYahoo:
    def __init__(self, responses: dict[str, list[Distribution] | Exception]) -> None:
        self.responses = responses

    def fetch_distributions(self, code: str) -> list[Distribution]:
        response = self.responses.get(code, [])
        if isinstance(response, Exception):
            raise response
        return response


def statuses(session: Session) -> dict[date, CollectionStatus]:
    logs = session.exec(select(PriceCollectionLog)).all()
    return {log.trade_date: log.status for log in logs}


def prices(session: Session) -> dict[tuple[date, str], int]:
    rows = session.exec(select(EtfDailyPrice)).all()
    return {(r.trade_date, r.code): r.close for r in rows}


def run_prices(
    session: Session, source: FakeKrx, settings: Settings, codes: set[str] = CODES
) -> CollectionReport:
    report = CollectionReport()
    collect_prices(session, source, codes, TODAY, settings, report)
    return report


# --- 시세: 날짜별 수집 ----------------------------------------------------------


def test_영업일_휴장일_대기를_구분해_기록한다(
    session: Session, settings: Settings
) -> None:
    source = FakeKrx(
        {
            d(4): business(4),
            d(2): [],  # 유예 기간(3일)이 지난 빈 목록 → 휴장일
            d(8): [],  # 유예 기간 안의 빈 목록 → 대기
            d(10): [],
        }
    )

    report = run_prices(session, source, settings)

    assert source.calls == [d(i) for i in range(1, 11)]
    result = statuses(session)
    assert result[d(4)] == CollectionStatus.BUSINESS_DAY
    assert result[d(3)] == CollectionStatus.HOLIDAY  # 종가가 빈 행
    assert result[d(2)] == CollectionStatus.HOLIDAY
    assert result[d(8)] == CollectionStatus.PENDING
    assert result[d(10)] == CollectionStatus.PENDING
    # 대상 ETF의 종가 있는 행만 저장한다
    assert prices(session) == {(d(4), "069500"): 100, (d(4), "0184E0"): 100}
    assert report.saved_rows == 2
    assert report.stopped_reason is None


def test_다시_실행하면_대기와_실패_날짜만_호출한다(
    session: Session, settings: Settings
) -> None:
    run_prices(
        session,
        FakeKrx({d(4): business(4), d(5): FetchError("timeout"), d(9): []}),
        settings,
    )

    source = FakeKrx({d(5): business(5), d(9): business(9)})
    run_prices(session, source, settings)

    assert source.calls == [d(5), d(9)]
    assert statuses(session)[d(5)] == CollectionStatus.BUSINESS_DAY
    assert statuses(session)[d(9)] == CollectionStatus.BUSINESS_DAY


def test_네트워크_실패는_실패로_기록하고_계속한다(
    session: Session, settings: Settings
) -> None:
    source = FakeKrx({d(2): FetchError("timeout"), d(4): business(4)})

    report = run_prices(session, source, settings)

    assert len(source.calls) == 10
    log = session.get(PriceCollectionLog, d(2))
    assert log is not None and log.status == CollectionStatus.FAILED
    assert log.error == "timeout"
    assert report.statuses[CollectionStatus.FAILED] == 1
    assert report.has_problems


def test_KRX_오류_응답이면_즉시_멈춘다(session: Session, settings: Settings) -> None:
    source = FakeKrx({d(3): SourceUnavailableError("HTTP 401 respCode=401")})

    report = run_prices(session, source, settings)

    assert source.calls == [d(1), d(2), d(3)]
    assert statuses(session)[d(3)] == CollectionStatus.FAILED
    assert report.stopped_reason is not None and "401" in report.stopped_reason
    # 다시 받을 과거 영업일이 없었으므로, 멈춰도 신규 ETF는 완료로 기록돼 다음 실행에 중복 호출이 없다
    assert set(session.exec(select(EtfBackfill.code)).all()) == CODES


def test_호출_상한에_도달하면_멈춘다(session: Session, settings: Settings) -> None:
    source = FakeKrx({})

    report = run_prices(
        session, source, settings.model_copy(update={"krx_max_calls_per_run": 4})
    )

    assert len(source.calls) == 4
    assert report.krx_calls == 4
    assert report.stopped_reason is not None and "상한" in report.stopped_reason


# --- 시세: 신규 ETF 백필 --------------------------------------------------------


def test_초기_적재는_백필_호출_없이_완료로_기록한다(
    session: Session, settings: Settings
) -> None:
    source = FakeKrx({d(4): business(4), d(5): business(5)})

    report = run_prices(session, source, settings)

    assert len(source.calls) == 10  # 날짜별 수집만 하고 다시 호출하지 않는다
    assert set(session.exec(select(EtfBackfill.code)).all()) == CODES
    assert report.backfilled_codes == sorted(CODES)


def test_신규_ETF는_이전_영업일만_다시_받아_그_ETF_행만_저장한다(
    session: Session, settings: Settings
) -> None:
    # 069500만 대상일 때 1/4, 1/5 영업일을 수집해 두었다
    run_prices(
        session, FakeKrx({d(4): business(4), d(5): business(5)}), settings, {"069500"}
    )
    assert prices(session) == {(d(4), "069500"): 100, (d(5), "069500"): 100}

    # 0184E0을 추가했다. 과거 영업일 응답의 069500 값은 달라도 덮어쓰지 않아야 한다.
    source = FakeKrx({d(4): business(4, close=999), d(5): business(5, close=999)})
    report = run_prices(session, source, settings)

    # 새로 받을 날짜는 없고, 이전 영업일 1/4·1/5만 다시 받는다
    assert source.calls == [d(4), d(5)]
    assert prices(session) == {
        (d(4), "069500"): 100,
        (d(5), "069500"): 100,
        (d(4), "0184E0"): 999,
        (d(5), "0184E0"): 999,
    }
    assert report.backfilled_codes == ["0184E0"]


def test_백필_중_실패하면_완료로_기록하지_않는다(
    session: Session, settings: Settings
) -> None:
    run_prices(
        session, FakeKrx({d(4): business(4), d(5): business(5)}), settings, {"069500"}
    )

    source = FakeKrx({d(4): FetchError("timeout"), d(5): business(5)})
    report = run_prices(session, source, settings)

    assert set(session.exec(select(EtfBackfill.code)).all()) == {"069500"}
    assert report.backfilled_codes == []
    assert report.warnings


# --- 분배금 --------------------------------------------------------------------


def dist(y: int, m: int, day: int, amount: str) -> Distribution:
    return Distribution(date(y, m, day), Decimal(amount))


def override(**kwargs: object) -> DistributionOverride:
    return DistributionOverride.model_validate(
        {"source": "https://kind.krx.co.kr/x", **kwargs}
    )


def distributions(session: Session, code: str) -> dict[date, tuple[Decimal, str]]:
    rows = session.exec(
        select(EtfDistribution).where(col(EtfDistribution.code) == code)
    ).all()
    return {r.ex_date: (r.amount, r.source) for r in rows}


def test_분배금_전체_이력으로_바꾸고_보정을_적용한다(session: Session) -> None:
    # 이전 수집 때 있던 값. 야후가 나중에 지운 항목은 사라져야 한다.
    session.add(
        EtfDistribution(
            code="069500",
            ex_date=date(2011, 1, 1),
            amount=Decimal(1),
            source=DistributionSource.YFINANCE,
        )
    )
    session.commit()
    source = FakeYahoo(
        {
            "069500": [
                dist(2009, 4, 28, "300"),  # 2010년 이전은 저장하지 않는다
                dist(2015, 4, 29, "140"),
                dist(2015, 4, 30, "10"),
            ]
        }
    )
    overrides = [
        override(code="069500", ex_date=date(2015, 4, 29), amount=150),
        override(code="069500", ex_date=date(2015, 4, 30), delete=True),
        override(code="069500", ex_date=date(2016, 1, 28), amount=20),
    ]
    report = CollectionReport()

    refresh_distributions(session, source, {"069500"}, overrides, report)

    assert distributions(session, "069500") == {
        date(2015, 4, 29): (Decimal(150), DistributionSource.OVERRIDE),
        date(2016, 1, 28): (Decimal(20), DistributionSource.OVERRIDE),
    }
    assert report.distribution_codes_updated == 1
    assert not report.has_problems


def test_분배금이_0건으로_오면_기존_값을_유지하고_경고한다(session: Session) -> None:
    session.add(
        EtfDistribution(
            code="069500",
            ex_date=date(2015, 4, 29),
            amount=Decimal(140),
            source=DistributionSource.YFINANCE,
        )
    )
    session.commit()
    report = CollectionReport()

    refresh_distributions(session, FakeYahoo({"069500": []}), {"069500"}, [], report)

    assert distributions(session, "069500") == {
        date(2015, 4, 29): (Decimal(140), DistributionSource.YFINANCE)
    }
    assert report.warnings and report.has_problems


def test_분배금이_원래_없는_ETF는_경고하지_않는다(session: Session) -> None:
    report = CollectionReport()

    refresh_distributions(session, FakeYahoo({}), {"0184E0"}, [], report)

    assert distributions(session, "0184E0") == {}
    assert not report.has_problems


def test_분배금을_받지_못하면_기존_값을_두고_다른_ETF는_계속한다(
    session: Session,
) -> None:
    session.add(
        EtfDistribution(
            code="069500",
            ex_date=date(2015, 4, 29),
            amount=Decimal(140),
            source=DistributionSource.YFINANCE,
        )
    )
    session.commit()
    source = FakeYahoo(
        {"069500": FetchError("timeout"), "0184E0": [dist(2024, 7, 30, "30")]}
    )
    report = CollectionReport()

    refresh_distributions(session, source, CODES, [], report)

    assert distributions(session, "069500") == {
        date(2015, 4, 29): (Decimal(140), DistributionSource.YFINANCE)
    }
    assert distributions(session, "0184E0") == {
        date(2024, 7, 30): (Decimal(30), DistributionSource.YFINANCE)
    }
    assert report.distribution_codes_updated == 1
    assert len(report.warnings) == 1


def test_수집_완료_시각은_UTC_시간대가_있다(
    session: Session, settings: Settings
) -> None:
    before = datetime.now(UTC)
    run_prices(session, FakeKrx({}), settings)

    log = session.get(PriceCollectionLog, d(1))
    assert log is not None and log.checked_at >= before
