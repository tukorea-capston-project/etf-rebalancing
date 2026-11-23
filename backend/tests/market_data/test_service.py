"""수집 흐름 테스트. KRX·yfinance 대신 가짜 출처를 쓰고, 테스트 DB에 저장한다."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, update
from sqlmodel import Session, col, select

from app.core.config import Settings
from app.market_data import service
from app.market_data.models import (
    CollectionStatus,
    DistributionSource,
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
    check_distributions,
    collect_prices,
    refresh_distributions,
    run_collection,
)

# 2010-01-01 ~ 2010-01-10 열흘만 수집하도록 '오늘'을 고정한다.
TODAY = date(2010, 1, 10)
CODES = {"069500", "0184E0"}
ALL_CODES = ["069500", "0184E0", "999999"]


def d(day: int) -> date:
    return date(2010, 1, day)


def quote(day: int, code: str, close: int | None = 100) -> DailyQuote:
    return DailyQuote(trade_date=d(day), code=code, name=f"ETF {code}", close=close)


def business(day: int, close: int = 100) -> list[DailyQuote]:
    """ETF 세 개가 있는 영업일."""
    return [quote(day, c, close) for c in ALL_CODES]


def holiday(day: int) -> list[DailyQuote]:
    return [quote(day, c, None) for c in ALL_CODES]


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
        self.calls: list[str] = []

    def fetch_distributions(self, code: str) -> list[Distribution]:
        self.calls.append(code)
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
    session: Session, source: FakeKrx, settings: Settings
) -> CollectionReport:
    report = CollectionReport()
    collect_prices(session, source, TODAY, settings, report)
    return report


def mark_partial(session: Session, *days: int) -> None:
    """전체 저장으로 바꾸기 전에 일부 ETF만 저장했던 영업일로 만든다."""
    session.exec(
        update(PriceCollectionLog)
        .where(col(PriceCollectionLog.trade_date).in_([d(day) for day in days]))
        .values(all_etfs_saved=False)
    )
    session.commit()


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
    assert report.stopped_reason is None


def test_그날_응답의_ETF_전체를_저장한다(session: Session, settings: Settings) -> None:
    report = run_prices(session, FakeKrx({d(4): business(4)}), settings)

    assert prices(session) == {(d(4), c): 100 for c in ALL_CODES}
    assert report.saved_rows == 3
    log = session.get(PriceCollectionLog, d(4))
    assert log is not None and log.all_etfs_saved and log.saved_rows == 3


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


def test_호출_상한에_도달하면_멈춘다(session: Session, settings: Settings) -> None:
    source = FakeKrx({})

    report = run_prices(
        session, source, settings.model_copy(update={"krx_max_calls_per_run": 4})
    )

    assert len(source.calls) == 4
    assert report.krx_calls == 4
    assert report.stopped_reason is not None and "상한" in report.stopped_reason


# --- 시세: 전체 저장 전에 수집한 영업일 재수집 ---------------------------------


def test_ETF_전체를_저장하지_않은_영업일은_다시_받아_빠진_행만_채운다(
    session: Session, settings: Settings
) -> None:
    # 전체 저장 전: 1/4·1/5에 069500만 저장돼 있었다
    run_prices(session, FakeKrx({d(4): business(4), d(5): business(5)}), settings)
    session.exec(delete(EtfDailyPrice).where(col(EtfDailyPrice.code) != "069500"))
    session.commit()
    mark_partial(session, 4, 5)

    # 다시 받은 응답의 069500 값은 달라도 덮어쓰지 않아야 한다
    source = FakeKrx({d(4): business(4, close=999), d(5): business(5, close=999)})
    report = run_prices(session, source, settings)

    assert source.calls == [d(4), d(5)]
    assert prices(session) == {
        (d(4), "069500"): 100,
        (d(5), "069500"): 100,
        (d(4), "0184E0"): 999,
        (d(5), "0184E0"): 999,
        (d(4), "999999"): 999,
        (d(5), "999999"): 999,
    }
    assert report.refilled_days == 2
    assert report.saved_rows == 4
    log = session.get(PriceCollectionLog, d(4))
    assert log is not None and log.all_etfs_saved


def test_재수집에_실패해도_영업일_기록은_그대로_둔다(
    session: Session, settings: Settings
) -> None:
    run_prices(session, FakeKrx({d(4): business(4), d(5): business(5)}), settings)
    mark_partial(session, 4, 5)

    source = FakeKrx({d(4): FetchError("timeout"), d(5): holiday(5)})
    report = run_prices(session, source, settings)

    assert statuses(session)[d(4)] == CollectionStatus.BUSINESS_DAY
    assert statuses(session)[d(5)] == CollectionStatus.BUSINESS_DAY
    log = session.get(PriceCollectionLog, d(4))
    assert log is not None and not log.all_etfs_saved  # 다음 실행 때 다시 받는다
    assert report.refilled_days == 0
    assert len(report.warnings) == 2


def test_재수집_중_KRX_오류_응답이면_기록을_바꾸지_않고_멈춘다(
    session: Session, settings: Settings
) -> None:
    run_prices(session, FakeKrx({d(4): business(4)}), settings)
    mark_partial(session, 4)

    source = FakeKrx({d(4): SourceUnavailableError("HTTP 401")})
    report = run_prices(session, source, settings)

    assert statuses(session)[d(4)] == CollectionStatus.BUSINESS_DAY
    assert report.stopped_reason is not None


# --- 전체 실행 -----------------------------------------------------------------


def test_분배금은_DB에_시세가_있는_ETF_전체를_받는다(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "load_overrides", list)
    # 상장폐지된 ETF(시세가 과거에만 있음)도 대상이다
    session.add(EtfDailyPrice(trade_date=d(1), code="091190", name="폐지", close=1))
    session.commit()
    yahoo = FakeYahoo({})

    run_collection(session, FakeKrx({d(4): business(4)}), yahoo, settings, TODAY)

    assert sorted(yahoo.calls) == sorted([*ALL_CODES, "091190"])


def test_보정_YAML에_시세가_없는_종목코드가_있으면_오류다(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        service,
        "load_overrides",
        lambda: [
            DistributionOverride.model_validate(
                {"code": "123456", "ex_date": "2015-04-29", "amount": 1, "source": "x"}
            )
        ],
    )

    with pytest.raises(ValueError, match="123456"):
        run_collection(
            session, FakeKrx({d(4): business(4)}), FakeYahoo({}), settings, TODAY
        )


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


# --- 분배금 점검 ---------------------------------------------------------------


def add_distribution(
    session: Session,
    code: str,
    ex_date: date,
    amount: str,
    source: DistributionSource = DistributionSource.YFINANCE,
) -> None:
    session.add(
        EtfDistribution(
            code=code, ex_date=ex_date, amount=Decimal(amount), source=source
        )
    )


def add_close(session: Session, code: str, trade_date: date, close: int) -> None:
    session.add(
        EtfDailyPrice(trade_date=trade_date, code=code, name=f"ETF {code}", close=close)
    )


def test_정수가_아닌_분배금을_경고한다(session: Session) -> None:
    add_distribution(session, "069500", date(2025, 12, 12), "1.458")
    session.commit()
    report = CollectionReport()

    check_distributions(session, CODES, report)

    assert len(report.warnings) == 1
    assert "069500 2025-12-12" in report.warnings[0]
    assert "정수가 아니다" in report.warnings[0]


def test_분배율이_범위_밖이면_경고한다(session: Session) -> None:
    add_close(session, "069500", date(2025, 4, 28), 10000)
    add_close(
        session, "069500", date(2025, 4, 29), 9000
    )  # 분배락일 당일 종가는 쓰지 않는다
    add_distribution(session, "069500", date(2025, 4, 29), "1001")  # 10.01%
    add_close(session, "0184E0", date(2025, 7, 29), 100000)
    add_distribution(session, "0184E0", date(2025, 7, 30), "9")  # 0.009%
    session.commit()
    report = CollectionReport()

    check_distributions(session, CODES, report)

    assert len(report.warnings) == 2
    joined = "\n".join(report.warnings)
    assert "069500 2025-04-29" in joined and "10.0100%" in joined
    assert "0184E0 2025-07-30" in joined and "0.0090%" in joined


def test_범위_안이거나_시세가_없으면_경고하지_않는다(session: Session) -> None:
    add_close(session, "069500", date(2025, 4, 28), 10000)
    add_distribution(session, "069500", date(2025, 4, 29), "1000")  # 정확히 10%
    add_distribution(session, "0184E0", date(2025, 7, 30), "9")  # 전일 시세 없음
    session.commit()
    report = CollectionReport()

    check_distributions(session, CODES, report)

    assert report.warnings == []


def test_보정_YAML로_확인한_항목은_점검하지_않는다(session: Session) -> None:
    add_distribution(
        session, "069500", date(2025, 12, 12), "1.458", DistributionSource.OVERRIDE
    )
    session.commit()
    report = CollectionReport()

    check_distributions(session, CODES, report)

    assert report.warnings == []
