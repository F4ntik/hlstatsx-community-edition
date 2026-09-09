from pathlib import Path

import pytest

from i18n_validate import read_map, validate_pair


ROOT = Path(__file__).resolve().parents[1]
EN = ROOT / "web/lang/en.php"
RU = ROOT / "web/lang/ru.php"


def write_catalog(path: Path, entries: str) -> None:
    path.write_text("<?php\nreturn array(\n" + entries + "\n);\n", encoding="utf-8")


def test_current_catalogs_pass() -> None:
    validate_pair(EN, RU)
    assert len(read_map(EN)) == len(read_map(RU)) > 1000


def test_duplicate_key_fails(tmp_path: Path) -> None:
    path = tmp_path / "en.php"
    write_catalog(path, "    'literal.name' => 'Name',\n    'literal.name' => 'Name again',")
    with pytest.raises(ValueError, match="duplicate keys: literal.name"):
        read_map(path)


def test_missing_key_fails(tmp_path: Path) -> None:
    en = tmp_path / "en.php"
    ru = tmp_path / "ru.php"
    write_catalog(en, "    'ui.name' => 'Name',\n    'ui.role' => 'Role',")
    write_catalog(ru, "    'ui.name' => 'Имя',")
    with pytest.raises(ValueError, match="keyset mismatch"):
        validate_pair(en, ru)


def test_placeholder_mismatch_fails(tmp_path: Path) -> None:
    en = tmp_path / "en.php"
    ru = tmp_path / "ru.php"
    write_catalog(en, "    'error.page' => 'Unable to find :path',")
    write_catalog(ru, "    'error.page' => 'Не найдено: {page}',")
    with pytest.raises(ValueError, match="placeholder mismatch: error.page"):
        validate_pair(en, ru)
