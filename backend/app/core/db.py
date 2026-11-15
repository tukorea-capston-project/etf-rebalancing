"""DB 연결. 엔진은 처음 사용할 때 만든다."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """FastAPI 의존성으로 쓰는 DB 세션."""
    with Session(get_engine()) as session:
        yield session
