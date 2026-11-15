"""애플리케이션 설정. 저장소 루트의 .env에서 읽는다."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# backend/app/core/config.py 기준으로 저장소 루트
ROOT_DIR = Path(__file__).resolve().parents[3]

# KIS는 모의투자 도메인만 사용한다. 실전투자 도메인은 어떤 용도로도 쓰지 않는다.
KIS_MOCK_REST_URL = "https://openapivts.koreainvestment.com:29443"
KIS_MOCK_WS_URL = "ws://ops.koreainvestment.com:31000"


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

    # KIS 모의투자
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""  # 계좌번호 앞 8자리
    kis_account_product_code: str = "01"  # 계좌 상품코드 뒤 2자리 (주식 종합계좌는 01)
    kis_rest_url: str = KIS_MOCK_REST_URL
    kis_ws_url: str = KIS_MOCK_WS_URL

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

    @field_validator("kis_rest_url")
    @classmethod
    def _kis_rest_must_be_mock(cls, value: str) -> str:
        if value.rstrip("/") != KIS_MOCK_REST_URL:
            raise ValueError(
                f"KIS REST 주소는 모의투자 주소({KIS_MOCK_REST_URL})만 허용한다: {value}"
            )
        return value.rstrip("/")

    @field_validator("kis_ws_url")
    @classmethod
    def _kis_ws_must_be_mock(cls, value: str) -> str:
        if value.rstrip("/") != KIS_MOCK_WS_URL:
            raise ValueError(
                f"KIS WebSocket 주소는 모의투자 주소({KIS_MOCK_WS_URL})만 허용한다: {value}"
            )
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # 값은 .env/환경변수에서 채워진다
