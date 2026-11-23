"""분배금 보정 YAML(backend/config/distribution_overrides.yaml)을 읽는다.

형식은 docs/market-data.md의 '보정 파일'을 따른다. (종목코드, 분배락일)별 최종값을 적는다.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.core.codes import check_code

OVERRIDES_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "distribution_overrides.yaml"
)


class DistributionOverride(BaseModel):
    # 오타(예: delet)를 조용히 무시하지 않도록 정의하지 않은 키는 거부한다.
    model_config = ConfigDict(extra="forbid")

    code: str
    ex_date: date
    amount: Decimal | None = None
    delete: bool = False
    source: str  # 근거(KIND 공시 URL 등)

    @field_validator("code", mode="before")
    @classmethod
    def _check_code(cls, value: Any) -> str:
        return check_code(value)

    @field_validator("source")
    @classmethod
    def _source_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source(근거)는 비울 수 없다")
        return value

    @model_validator(mode="after")
    def _amount_xor_delete(self) -> Self:
        if self.delete == (self.amount is not None):
            raise ValueError(
                f"{self.code} {self.ex_date}: amount와 delete: true 중 하나만 적는다"
            )
        if self.amount is not None and self.amount <= 0:
            raise ValueError(f"{self.code} {self.ex_date}: amount는 0보다 커야 한다")
        return self


class DistributionOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overrides: list[DistributionOverride] = []

    @model_validator(mode="after")
    def _no_duplicates(self) -> Self:
        seen: set[tuple[str, date]] = set()
        for o in self.overrides:
            key = (o.code, o.ex_date)
            if key in seen:
                raise ValueError(f"보정 항목이 중복되어 있다: {o.code} {o.ex_date}")
            seen.add(key)
        return self


def load_overrides(path: Path = OVERRIDES_PATH) -> list[DistributionOverride]:
    """보정 항목을 읽는다. 시세가 없는 종목코드인지는 수집할 때 DB와 대조한다."""
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return DistributionOverrides.model_validate(data).overrides
