"""yfinance 출처 테스트. 실제 야후를 호출하지 않고 받아오는 함수를 바꿔 끼운다."""

from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
import pytest

from app.market_data.service import Distribution, FetchError
from app.market_data.yahoo import YahooDistributionSource


def make_source(
    fetch: Any, sleeps: list[float] | None = None
) -> YahooDistributionSource:
    return YahooDistributionSource(
        timeout_seconds=1,
        max_retries=2,
        fetch=fetch,
        sleep=(sleeps if sleeps is not None else []).append,
    )


def test_한국_시간_날짜와_Decimal로_바꾼다() -> None:
    def fetch(ticker: str, timeout: float) -> list[tuple[Any, float]]:
        assert ticker == "0184E0.KS"
        return [
            (pd.Timestamp("2026-07-30 09:00", tz="Asia/Seoul"), 30.0),
            # UTC로 와도 한국 날짜로 바꾼다 (2026-10-28 15:00 UTC = 10-29 00:00 KST)
            (pd.Timestamp("2026-10-28 15:00", tz="UTC"), 64.1),
        ]

    assert make_source(fetch).fetch_distributions("0184E0") == [
        Distribution(date(2026, 7, 30), Decimal("30.0")),
        Distribution(date(2026, 10, 29), Decimal("64.1")),
    ]


def test_실패하면_재시도하고_그래도_실패하면_FetchError() -> None:
    sleeps: list[float] = []

    def fetch(ticker: str, timeout: float) -> list[tuple[Any, float]]:
        raise ConnectionError("network down")

    with pytest.raises(FetchError, match="network down"):
        make_source(fetch, sleeps).fetch_distributions("069500")
    assert sleeps == [1, 2]


def test_재시도_중_성공하면_결과를_돌려준다() -> None:
    attempts: list[int] = []

    def fetch(ticker: str, timeout: float) -> list[tuple[Any, float]]:
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("temporary")
        return []

    assert make_source(fetch).fetch_distributions("069500") == []
    assert len(attempts) == 2
