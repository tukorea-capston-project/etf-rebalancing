"""종목코드 형식 검사 테스트."""

import pytest
import yaml

from app.core.codes import check_code


@pytest.mark.parametrize("code", ['"069500"', '"0184E0"'])
def test_앞자리_0과_영문자가_섞인_코드를_문자열로_읽는다(code: str) -> None:
    value = yaml.safe_load(f"code: {code}")["code"]

    assert check_code(value) == code.strip('"')


@pytest.mark.parametrize(
    "code",
    [
        "012450",  # 따옴표 없음: PyYAML이 8진수 int로 읽는다
        "69500",  # 따옴표 없음: int
        '"69500"',  # 5자리
        '"0695000"',  # 7자리
        '"0184e0"',  # 영문 소문자
        '"06950-"',  # 허용하지 않는 문자
    ],
)
def test_형식이_틀린_코드는_거부한다(code: str) -> None:
    value = yaml.safe_load(f"code: {code}")["code"]

    with pytest.raises(ValueError, match="종목코드"):
        check_code(value)
