from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from alembic import context
from app.core.config import get_settings

# 새 기능 폴더에 DB 모델(models.py)을 만들면 여기서 import해야 autogenerate가 테이블을 인식한다.
# 예: import app.strategy.models (사용하지 않는 import 경고는 noqa F401로 끈다)

config = context.config
# alembic 설정은 configparser라 '%'를 '%%'로 바꿔야 한다 (인코딩된 비밀번호에 '%'가 들어갈 수 있음).
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """DB 연결 없이 SQL 스크립트만 생성한다."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """DB에 연결해 마이그레이션을 적용한다."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
