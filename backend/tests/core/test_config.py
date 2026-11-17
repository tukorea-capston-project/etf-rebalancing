"""실전 스위치와 암호화 마스터키 설정 검사."""

import pytest
from pydantic import ValidationError

from app.core.config import KIS_ENDPOINTS, KisMode, Settings

SETTING_ENV_NAMES = (
    "REAL_TRADING_ENABLED",
    "CREDENTIAL_KEY_PROVIDER",
    "CREDENTIAL_LOCAL_KEY",
    "KMS_KEY_ID",
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # 개발자 셸의 환경변수가 검사 결과에 섞이지 않게 한다.
    for name in SETTING_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def make_settings(**values: object) -> Settings:
    # .env를 읽지 않고, 넘긴 값만으로 만든다.
    return Settings(_env_file=None, postgres_password="test", **values)  # pyright: ignore[reportCallIssue]


def test_real_trading_is_disabled_by_default() -> None:
    settings = make_settings()
    assert settings.real_trading_enabled is False
    assert settings.credential_key_provider == "local"


def test_real_trading_requires_kms() -> None:
    with pytest.raises(ValidationError, match="REAL_TRADING_ENABLED"):
        make_settings(real_trading_enabled=True)


def test_kms_requires_key_id() -> None:
    with pytest.raises(ValidationError, match="KMS_KEY_ID"):
        make_settings(credential_key_provider="kms")


def test_real_trading_with_kms_is_allowed() -> None:
    settings = make_settings(
        real_trading_enabled=True,
        credential_key_provider="kms",
        kms_key_id="test-key-id",
    )
    assert settings.real_trading_enabled is True


def test_kis_endpoints_cover_both_modes() -> None:
    assert set(KIS_ENDPOINTS) == set(KisMode)
    assert KIS_ENDPOINTS[KisMode.MOCK].rest_url.startswith("https://openapivts.")
    assert KIS_ENDPOINTS[KisMode.REAL].rest_url.startswith("https://openapi.")
