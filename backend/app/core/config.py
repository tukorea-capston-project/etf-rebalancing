"""애플리케이션 설정. 저장소 루트의 .env에서 읽는다."""

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# backend/app/core/config.py 기준으로 저장소 루트
ROOT_DIR = Path(__file__).resolve().parents[3]


class KisMode(StrEnum):
    """KIS 주문 모드. 사용자마다 하나를 고른다."""

    MOCK = "mock"
    REAL = "real"


@dataclass(frozen=True)
class KisEndpoints:
    rest_url: str
    ws_url: str


# KIS 주소는 이 두 개만 쓴다. 설정값(.env)으로 주소를 받지 않는다.
KIS_ENDPOINTS: dict[KisMode, KisEndpoints] = {
    KisMode.MOCK: KisEndpoints(
        rest_url="https://openapivts.koreainvestment.com:29443",
        ws_url="ws://ops.koreainvestment.com:31000",
    ),
    KisMode.REAL: KisEndpoints(
        rest_url="https://openapi.koreainvestment.com:9443",
        ws_url="ws://ops.koreainvestment.com:21000",
    ),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL. compose.yaml과 같은 .env 값을 쓴다. 비밀번호는 POSTGRES_PASSWORD 한 곳에만 둔다.
    postgres_user: str = "capston"
    postgres_password: SecretStr
    postgres_db: str = "capston"
    postgres_host: str = "localhost"
    # 개발 DB 포트. 테스트 실행 시에는 conftest.py가 15433(테스트 DB)으로 바꾼다.
    postgres_port: int = 15432

    # 서버 실전 스위치. false면 실전 주문을 보내지 않고 실전 전환도 막는다. AWS 서버에서만 켠다.
    real_trading_enabled: bool = False

    # KIS 자격 증명 암호화 마스터키. KIS 앱키·계좌는 .env가 아니라 사용자별로 DB에 암호화해 저장한다.
    # local: 팀원 PC(개발·테스트), kms: AWS 서버
    credential_key_provider: Literal["local", "kms"] = "local"
    credential_local_key: SecretStr = SecretStr("")
    kms_key_id: str = ""

    # KRX Open API
    krx_api_key: str = ""

    @property
    def database_url(self) -> str:
        """SQLAlchemy 접속 주소. 비밀번호의 특수문자는 자동으로 인코딩된다."""
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)

    @model_validator(mode="after")
    def _check_credential_key(self) -> Self:
        if self.credential_key_provider == "kms" and not self.kms_key_id:
            raise ValueError("CREDENTIAL_KEY_PROVIDER=kms이면 KMS_KEY_ID가 필요하다")
        if self.real_trading_enabled and self.credential_key_provider != "kms":
            raise ValueError(
                "REAL_TRADING_ENABLED=true는 CREDENTIAL_KEY_PROVIDER=kms일 때만 허용한다"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # 값은 .env/환경변수에서 채워진다
