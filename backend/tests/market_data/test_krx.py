"""KRX 출처 테스트. 실제 KRX를 호출하지 않고 httpx.MockTransport로 응답을 흉내 낸다."""

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.market_data.krx import KRX_ETF_DAILY_URL, KrxPriceSource, parse_row
from app.market_data.service import FetchError, SourceUnavailableError

# 2026-11-13 실제 응답의 한 행
BUSINESS_ROW = {
    "BAS_DD": "20261113",
    "ISU_CD": "0184E0",
    "ISU_NM": "1Q 200채권혼합50액티브",
    "TDD_CLSPRC": "9655",
    "CMPPREVDD_PRC": "-65",
    "FLUC_RT": "-0.67",
    "NAV": "9677.23",
    "TDD_OPNPRC": "9845",
    "TDD_HGPRC": "9880",
    "TDD_LWPRC": "9635",
    "ACC_TRDVOL": "104154",
    "ACC_TRDVAL": "1021193775",
    "MKTCAP": "29930500000",
    "INVSTASST_NETASST_TOTAMT": "29999412289",
    "LIST_SHRS": "3100000",
    "IDX_IND_NM": "코스피 200 단기국공채 혼합지수",
    "OBJ_STKPRC_IDX": "1969.69",
    "CMPPREVDD_IDX": "-10.34",
    "FLUC_RT_IDX": "-0.52",
}

# 2026-11-15(일) 실제 응답의 한 행. 종목명·상장좌수·지수명만 값이 있다.
HOLIDAY_ROW = {
    **{k: "" for k in BUSINESS_ROW},
    "BAS_DD": "20261115",
    "ISU_CD": "451060",
    "ISU_NM": "1Q 200액티브",
    "LIST_SHRS": "13200000",
    "IDX_IND_NM": "코스피 200",
}

API_KEY = "test-key-should-not-leak"


def make_source(
    handler: Callable[[httpx.Request], httpx.Response],
    sleeps: list[float] | None = None,
) -> KrxPriceSource:
    recorded = sleeps if sleeps is not None else []
    return KrxPriceSource(
        API_KEY,
        interval_seconds=0,
        timeout_seconds=1,
        max_retries=3,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=recorded.append,
    )


def test_영업일_행을_숫자로_변환한다() -> None:
    q = parse_row(BUSINESS_ROW)

    assert q.trade_date == date(2026, 11, 13)
    assert q.code == "0184E0"
    assert q.close == 9655
    assert q.change == -65
    assert q.change_rate == Decimal("-0.67")
    assert q.nav == Decimal("9677.23")
    assert q.market_cap == 29930500000
    assert q.index_close == Decimal("1969.69")


def test_빈_값과_대시는_None이다() -> None:
    q = parse_row({**HOLIDAY_ROW, "NAV": "-"})

    assert q.close is None
    assert q.nav is None
    assert q.listed_shares == 13200000
    assert q.index_name == "코스피 200"


def test_인증키는_헤더로_보내고_기준일자를_넘긴다() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"OutBlock_1": [BUSINESS_ROW]})

    quotes = make_source(handler).fetch_daily(date(2026, 11, 13))

    assert len(quotes) == 1
    request = seen[0]
    assert str(request.url).startswith(KRX_ETF_DAILY_URL)
    assert request.url.params["basDd"] == "20261113"
    assert request.headers["AUTH_KEY"] == API_KEY
    assert API_KEY not in str(request.url)


def test_빈_목록은_그대로_돌려준다() -> None:
    source = make_source(lambda _: httpx.Response(200, json={"OutBlock_1": []}))

    assert source.fetch_daily(date(2026, 11, 17)) == []


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (401, {"respMsg": "Unauthorized Key", "respCode": "401"}),
        (200, {"respMsg": "한도 초과", "respCode": "999"}),  # OutBlock_1 없는 오류 응답
        (500, None),
    ],
)
def test_오류_응답은_재시도하지_않고_멈춘다(
    status: int, body: dict[str, str] | None
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if body is None:
            return httpx.Response(status, text="Internal Server Error")
        return httpx.Response(status, json=body)

    with pytest.raises(SourceUnavailableError) as exc:
        make_source(handler).fetch_daily(date(2026, 11, 13))

    assert len(calls) == 1
    assert API_KEY not in str(exc.value)


def test_네트워크_오류는_재시도한다() -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            raise httpx.ConnectTimeout("timeout", request=request)
        return httpx.Response(200, json={"OutBlock_1": []})

    assert make_source(handler, sleeps).fetch_daily(date(2026, 11, 13)) == []
    assert len(attempts) == 3
    assert [s for s in sleeps if s >= 1] == [1, 2]


def test_재시도해도_네트워크_오류면_FetchError() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(FetchError):
        make_source(handler).fetch_daily(date(2026, 11, 13))


def test_인증키가_없으면_시작하지_않는다() -> None:
    with pytest.raises(ValueError, match="KRX_API_KEY"):
        KrxPriceSource("", interval_seconds=0, timeout_seconds=1, max_retries=0)
