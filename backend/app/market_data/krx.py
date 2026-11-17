"""KRX Open API ETF 일별매매정보 출처. 응답 형태는 docs/market-data.md의 '응답 형태'."""

import logging
import time
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.market_data.service import DailyQuote, FetchError, SourceUnavailableError

logger = logging.getLogger(__name__)

KRX_ETF_DAILY_URL = "https://data-dbg.krx.co.kr/svc/apis/etp/etf_bydd_trd"


def _blank(value: str) -> bool:
    return value.strip() in ("", "-")


def _to_int(value: str) -> int | None:
    if _blank(value):
        return None
    return int(value.replace(",", ""))


def _to_decimal(value: str) -> Decimal | None:
    if _blank(value):
        return None
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation as e:
        raise ValueError(f"숫자로 바꿀 수 없다: {value!r}") from e


def _to_str(value: str) -> str | None:
    return None if _blank(value) else value


def parse_row(row: dict[str, str]) -> DailyQuote:
    """KRX 응답 한 행을 변환한다. 응답 필드는 모두 문자열이다."""
    return DailyQuote(
        trade_date=datetime.strptime(row["BAS_DD"], "%Y%m%d").date(),
        code=row["ISU_CD"],  # 종목코드는 문자열 그대로 둔다
        name=row["ISU_NM"],
        close=_to_int(row["TDD_CLSPRC"]),
        change=_to_int(row["CMPPREVDD_PRC"]),
        change_rate=_to_decimal(row["FLUC_RT"]),
        nav=_to_decimal(row["NAV"]),
        open=_to_int(row["TDD_OPNPRC"]),
        high=_to_int(row["TDD_HGPRC"]),
        low=_to_int(row["TDD_LWPRC"]),
        volume=_to_int(row["ACC_TRDVOL"]),
        trade_value=_to_int(row["ACC_TRDVAL"]),
        market_cap=_to_int(row["MKTCAP"]),
        net_assets=_to_int(row["INVSTASST_NETASST_TOTAMT"]),
        listed_shares=_to_int(row["LIST_SHRS"]),
        index_name=_to_str(row["IDX_IND_NM"]),
        index_close=_to_decimal(row["OBJ_STKPRC_IDX"]),
        index_change=_to_decimal(row["CMPPREVDD_IDX"]),
        index_change_rate=_to_decimal(row["FLUC_RT_IDX"]),
    )


class KrxPriceSource:
    """KRX ETF 일별매매정보. 호출 간격을 지키고, 네트워크 오류만 재시도한다."""

    def __init__(
        self,
        api_key: str,
        *,
        interval_seconds: float,
        timeout_seconds: float,
        max_retries: int,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError(".env에 KRX_API_KEY가 없다")
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._headers = {"AUTH_KEY": api_key}
        self._interval = interval_seconds
        self._max_retries = max_retries
        self._sleep = sleep
        self._last_call: float | None = None

    def _wait_interval(self) -> None:
        if self._last_call is not None:
            remaining = self._interval - (time.monotonic() - self._last_call)
            if remaining > 0:
                self._sleep(remaining)
        self._last_call = time.monotonic()

    def _get(self, trade_date: date) -> httpx.Response:
        params = {"basDd": trade_date.strftime("%Y%m%d")}
        for attempt in range(self._max_retries + 1):
            self._wait_interval()
            try:
                return self._client.get(
                    KRX_ETF_DAILY_URL, params=params, headers=self._headers
                )
            except httpx.TransportError as e:
                if attempt == self._max_retries:
                    raise FetchError(f"네트워크 오류: {type(e).__name__}") from e
                delay = 2**attempt
                logger.info("%s KRX 네트워크 오류, %s초 뒤 재시도", trade_date, delay)
                self._sleep(delay)
        raise AssertionError("unreachable")

    def fetch_daily(self, trade_date: date) -> list[DailyQuote]:
        response = self._get(trade_date)
        try:
            body: Any = response.json()
        except ValueError:
            body = None

        if response.status_code != 200 or not isinstance(body, dict):
            raise SourceUnavailableError(
                f"HTTP {response.status_code} {_error_message(body)}".strip()
            )
        rows = body.get("OutBlock_1")
        if not isinstance(rows, list):
            raise SourceUnavailableError(f"예상하지 못한 응답: {_error_message(body)}")
        return [parse_row(row) for row in rows]


def _error_message(body: Any) -> str:
    if isinstance(body, dict) and ("respCode" in body or "respMsg" in body):
        return f"respCode={body.get('respCode')} respMsg={body.get('respMsg')}"
    return ""
