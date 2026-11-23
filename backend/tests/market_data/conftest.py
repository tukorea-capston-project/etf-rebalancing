"""시세·분배금 테스트 공통 준비. 루트 conftest.py가 DB 주소를 테스트 DB로 바꾼 뒤 실행된다."""

from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel

import app.market_data.models  # noqa: F401  테이블 등록
from app.core.config import Settings, get_settings
from app.core.db import get_engine

TABLES = ["etf_daily_price", "price_collection_log", "etf_distribution"]


@pytest.fixture(scope="session")
def _tables() -> None:
    # create_all은 있는 테이블을 고치지 않는다. 모델이 바뀌어도 테스트 DB가 따라가도록
    # 테스트 시작 때 지우고 다시 만든다.
    engine = get_engine()
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


@pytest.fixture
def session(_tables: None) -> Iterator[Session]:
    with Session(get_engine()) as s:
        s.exec(text(f"TRUNCATE {', '.join(TABLES)}"))  # pyright: ignore[reportCallIssue, reportArgumentType]
        s.commit()
        yield s


@pytest.fixture
def settings() -> Settings:
    return get_settings().model_copy(
        update={"krx_pending_days": 3, "krx_max_calls_per_run": 9000}
    )
