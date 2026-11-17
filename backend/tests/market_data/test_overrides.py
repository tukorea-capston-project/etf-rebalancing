"""분배금 보정 YAML 로더 테스트."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.market_data.overrides import load_overrides

TARGETS = {"069500", "0184E0"}
SOURCE = "source: https://kind.krx.co.kr/x"


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "overrides.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_저장소의_보정_파일을_읽는다() -> None:
    assert load_overrides({"069500"}) == []


def test_추가와_삭제_항목을_읽는다(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "overrides:\n"
        f'  - {{code: "069500", ex_date: 2015-04-29, amount: 150.5, {SOURCE}}}\n'
        f'  - {{code: "0184E0", ex_date: 2026-07-30, delete: true, {SOURCE}}}\n',
    )

    first, second = load_overrides(TARGETS, path)

    assert (first.code, first.ex_date, first.amount) == (
        "069500",
        date(2015, 4, 29),
        Decimal("150.5"),
    )
    assert second.delete and second.amount is None


def test_빈_파일은_보정_없음이다(tmp_path: Path) -> None:
    assert load_overrides(TARGETS, write(tmp_path, "")) == []


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (f"{{code: 69500, ex_date: 2015-04-29, amount: 1, {SOURCE}}}", "종목코드"),
        (f'{{code: "069500", ex_date: 2015-04-29, {SOURCE}}}', "하나만"),
        (
            f'{{code: "069500", ex_date: 2015-04-29, amount: 1, delete: true, {SOURCE}}}',
            "하나만",
        ),
        (f'{{code: "069500", ex_date: 2015-04-29, amount: 0, {SOURCE}}}', "0보다"),
        ('{code: "069500", ex_date: 2015-04-29, amount: 1, source: " "}', "source"),
        ('{code: "069500", ex_date: 2015-04-29, amount: 1}', "source"),
        (f'{{code: "069500", ex_date: 2015-04-29, delet: true, {SOURCE}}}', "delet"),
    ],
)
def test_형식이_틀린_항목은_거부한다(tmp_path: Path, entry: str, message: str) -> None:
    path = write(tmp_path, f"overrides:\n  - {entry}\n")

    with pytest.raises(ValidationError, match=message):
        load_overrides(TARGETS, path)


def test_같은_종목_같은_날짜가_두_번_나오면_거부한다(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "overrides:\n"
        f'  - {{code: "069500", ex_date: 2015-04-29, amount: 1, {SOURCE}}}\n'
        f'  - {{code: "069500", ex_date: 2015-04-29, delete: true, {SOURCE}}}\n',
    )

    with pytest.raises(ValidationError, match="중복"):
        load_overrides(TARGETS, path)


def test_수집_대상이_아닌_종목코드는_거부한다(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        f'overrides:\n  - {{code: "999999", ex_date: 2015-04-29, amount: 1, {SOURCE}}}\n',
    )

    with pytest.raises(ValueError, match="999999"):
        load_overrides(TARGETS, path)
