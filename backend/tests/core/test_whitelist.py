"""화이트리스트 로더 테스트."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.whitelist import load_whitelist


def _slot(etfs_yaml: str, sector: str = "시장대표") -> str:
    return (
        f"  - asset_class: 주식\n    region: 국내\n    sector: {sector}\n"
        f"    etfs:\n{etfs_yaml}"
    )


def _write(tmp_path: Path, etfs_yaml: str) -> Path:
    path = tmp_path / "whitelist.yaml"
    path.write_text(f"slots:\n{_slot(etfs_yaml)}", encoding="utf-8")
    return path


def test_저장소의_화이트리스트를_읽는다() -> None:
    whitelist = load_whitelist()

    assert whitelist.codes
    assert all(isinstance(code, str) and len(code) == 6 for code in whitelist.codes)


def test_앞자리_0과_영문자가_섞인_코드를_문자열로_읽는다(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '      - { code: "069500", name: "KODEX 200" }\n'
        '      - { code: "0184E0", name: "영문자 코드" }\n',
    )

    assert load_whitelist(path).codes == ["069500", "0184E0"]


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
def test_형식이_틀린_코드는_거부한다(tmp_path: Path, code: str) -> None:
    path = _write(tmp_path, f'      - {{ code: {code}, name: "잘못된 코드" }}\n')

    with pytest.raises(ValidationError, match="종목코드"):
        load_whitelist(path)


def test_중복된_코드는_거부한다(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '      - { code: "069500", name: "KODEX 200" }\n'
        '      - { code: "069500", name: "중복" }\n',
    )

    with pytest.raises(ValidationError, match="중복"):
        load_whitelist(path)


def test_다른_슬롯에_같은_코드가_있으면_거부한다(tmp_path: Path) -> None:
    path = tmp_path / "whitelist.yaml"
    path.write_text(
        "slots:\n"
        + _slot('      - { code: "069500", name: "KODEX 200" }\n')
        + _slot('      - { code: "069500", name: "중복" }\n', sector="정보기술"),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="종목코드가 중복"):
        load_whitelist(path)


def test_같은_슬롯을_두_번_적으면_거부한다(tmp_path: Path) -> None:
    path = tmp_path / "whitelist.yaml"
    path.write_text(
        "slots:\n"
        + _slot('      - { code: "069500", name: "KODEX 200" }\n')
        + _slot('      - { code: "278530", name: "KODEX 200TR" }\n'),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="슬롯이 중복"):
        load_whitelist(path)
