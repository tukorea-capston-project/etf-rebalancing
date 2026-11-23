"""yfinance(Yahoo Finance) 분배금 출처. 티커는 `<종목코드>.KS`, 날짜는 분배락일이다."""

import logging
import math
import time
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import yfinance as yf
from yfinance.exceptions import YFTickerMissingError

from app.market_data.service import Distribution, FetchError

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


def _fetch_dividends(ticker: str, timeout_seconds: float) -> list[tuple[Any, float]]:
    # 분배금 열은 수정주가 여부(auto_adjust)와 관계없이 주당 분배금 원값이다.
    history = yf.Ticker(ticker).history(
        period="max",
        auto_adjust=False,
        actions=True,
        timeout=timeout_seconds,
        raise_errors=True,
    )
    if "Dividends" not in history.columns:
        return []
    amounts: list[Any] = history["Dividends"].tolist()
    # 0은 분배금이 없는 날이다. NaN도 함께 거른다(NaN은 참으로 평가된다).
    return [
        (ts, float(v))
        for ts, v in zip(history.index, amounts, strict=True)
        if v and not math.isnan(v)
    ]


def _to_kst_date(ts: Any) -> date:
    # 야후는 한국 시간 자정(또는 09:00) 시각으로 준다. 시간대를 맞춘 뒤 날짜만 쓴다.
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.tz_convert(KST)
    return ts.date()


class YahooDistributionSource:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_retries: int,
        fetch: Callable[[str, float], list[tuple[Any, float]]] = _fetch_dividends,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._fetch = fetch
        self._sleep = sleep

    def fetch_distributions(self, code: str) -> list[Distribution]:
        ticker = f"{code}.KS"
        for attempt in range(self._max_retries + 1):
            try:
                raw = self._fetch(ticker, self._timeout)
                break
            # 종목이 없다(상장폐지 등). 다시 시도해도 같으므로 분배금 0건으로 본다.
            # DB에 기존 분배금이 있으면 수집 쪽에서 값을 유지하고 경고한다.
            except YFTickerMissingError as e:
                logger.info(
                    "%s yfinance에 종목이 없어 분배금 0건으로 본다: %s", ticker, e
                )
                return []
            # yfinance는 네트워크·데이터 오류를 여러 예외로 던진다
            except Exception as e:
                if attempt == self._max_retries:
                    raise FetchError(f"{type(e).__name__}: {e}") from e
                delay = 2**attempt
                logger.info("%s yfinance 오류, %s초 뒤 재시도: %s", ticker, delay, e)
                self._sleep(delay)
        else:
            raise AssertionError("unreachable")

        # float 오차를 남기지 않도록 문자열을 거쳐 Decimal로 바꾼다.
        return [Distribution(_to_kst_date(ts), Decimal(str(v))) for ts, v in raw]
