"""종목코드 형식 검사. 설정 YAML(분배금 보정 등)에서 읽은 종목코드를 검증한다."""

import re
from typing import Any

# 최근 상장 종목은 영문 대문자가 섞인다(예: 0184E0).
CODE_PATTERN = re.compile(r"[0-9A-Z]{6}")


def check_code(value: Any) -> str:
    """YAML에서 읽은 종목코드를 검증한다."""
    # 따옴표 없이 쓰면 PyYAML이 숫자(8진수 포함)로 읽어 int가 들어온다.
    if not isinstance(value, str) or not CODE_PATTERN.fullmatch(value):
        raise ValueError(
            "종목코드는 따옴표로 감싼 6자리 문자열(숫자·영문 대문자)이어야 한다: "
            f"{value!r}"
        )
    return value
