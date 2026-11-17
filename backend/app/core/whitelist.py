"""투자 대상 ETF 화이트리스트(backend/config/etf_whitelist.yaml)를 읽는다.

시세 수집, 전략 검증, 백테스트가 함께 쓴다.
"""

import re
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, field_validator, model_validator

WHITELIST_PATH = Path(__file__).resolve().parents[2] / "config" / "etf_whitelist.yaml"

# 최근 상장 종목은 영문 대문자가 섞인다(예: 0184E0).
CODE_PATTERN = re.compile(r"[0-9A-Z]{6}")


class WhitelistEtf(BaseModel):
    code: str
    name: str
    group: str | None = None

    @field_validator("code", mode="before")
    @classmethod
    def _code_must_be_quoted_6_digits(cls, value: Any) -> Any:
        # 따옴표 없이 쓰면 PyYAML이 숫자(8진수 포함)로 읽어 int가 들어온다.
        if not isinstance(value, str) or not CODE_PATTERN.fullmatch(value):
            raise ValueError(
                "종목코드는 따옴표로 감싼 6자리 문자열(숫자·영문 대문자)이어야 한다: "
                f"{value!r}"
            )
        return value


class WhitelistCategory(BaseModel):
    id: str
    name: str
    etfs: list[WhitelistEtf]


class Whitelist(BaseModel):
    categories: list[WhitelistCategory]

    @model_validator(mode="after")
    def _codes_must_be_unique(self) -> Self:
        seen: set[str] = set()
        for etf in self.etfs:
            if etf.code in seen:
                raise ValueError(f"화이트리스트에 종목코드가 중복되어 있다: {etf.code}")
            seen.add(etf.code)
        return self

    @property
    def etfs(self) -> list[WhitelistEtf]:
        return [etf for category in self.categories for etf in category.etfs]

    @property
    def codes(self) -> list[str]:
        return [etf.code for etf in self.etfs]


def load_whitelist(path: Path = WHITELIST_PATH) -> Whitelist:
    with path.open(encoding="utf-8") as f:
        return Whitelist.model_validate(yaml.safe_load(f))
