"""시세·분배금 수집 명령. `backend/`에서 `uv run python -m app.market_data`로 실행한다.

공용 개발 DB에는 한 곳(담당 팀원)에서만 실행한다. 여러 곳에서 동시에 실행하지 않는다.
"""

import argparse
import logging
import sys

from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.core.db import get_engine
from app.market_data.krx import KrxPriceSource
from app.market_data.service import CollectionReport, run_collection
from app.market_data.yahoo import YahooDistributionSource


def _print_report(report: CollectionReport) -> None:
    statuses = ", ".join(f"{s.value} {n}" for s, n in sorted(report.statuses.items()))
    print(f"KRX 호출: {report.krx_calls}회 ({statuses or '수집할 날짜 없음'})")
    print(f"저장한 시세 행: {report.saved_rows}")
    if report.backfilled_codes:
        codes = report.backfilled_codes
        shown = ", ".join(codes[:10]) + (" 등" if len(codes) > 10 else "")
        print(f"백필 완료 ETF: {len(codes)}개 ({shown})")
    if report.stopped_reason:
        print(f"시세 수집 중단: {report.stopped_reason}")
    print(f"분배금 갱신 ETF: {report.distribution_codes_updated}")
    for warning in report.warnings:
        print(f"경고: {warning}")


def main(settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.market_data",
        description=(
            "KRX 시세와 yfinance 분배금을 수집해 DB에 저장한다. "
            "미수집 날짜 시세 → 신규 ETF 백필 → 분배금 갱신 순으로 실행한다."
        ),
    )
    parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    # 요청마다 찍히는 httpx 로그는 끈다. 진행 상황은 100일마다 따로 남긴다.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = settings or get_settings()
    price_source = KrxPriceSource(
        settings.krx_api_key,
        interval_seconds=settings.krx_request_interval_seconds,
        timeout_seconds=settings.market_data_timeout_seconds,
        max_retries=settings.market_data_max_retries,
    )
    distribution_source = YahooDistributionSource(
        timeout_seconds=settings.market_data_timeout_seconds,
        max_retries=settings.market_data_max_retries,
    )
    print(
        f"DB: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    with Session(get_engine()) as session:
        report = run_collection(session, price_source, distribution_source, settings)
    _print_report(report)
    # 실패·경고가 있으면 1로 끝내 스크립트나 워커가 알 수 있게 한다.
    return 1 if report.has_problems else 0


if __name__ == "__main__":
    sys.exit(main())
