"""Static validation for PHP translation maps."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

ENTRY = re.compile(
    r"(?m)^\s*'((?:\\.|[^'])*)'\s*=>\s*(?:'((?:\\.|[^'])*)'|\"((?:\\.|[^\"])*)\")\s*,?"
)
TOKEN = re.compile(r"(?::[a-z][A-Za-z0-9_]*|\{[A-Za-z0-9_.-]+\})")


def _php_unescape(value: str) -> str:
    return value.replace(r"\'", "'").replace(r"\\", "\\")


def read_map(path: Path) -> dict[str, list[str]]:
    entries = [
        (_php_unescape(match.group(1)), _php_unescape(match.group(2) or match.group(3)))
        for match in ENTRY.finditer(path.read_text(encoding="utf-8"))
    ]
    duplicates = sorted(key for key, count in Counter(key for key, _ in entries).items() if count > 1)
    if duplicates:
        raise ValueError(f"{path}: duplicate keys: {', '.join(duplicates)}")
    return {key: sorted(set(TOKEN.findall(value))) for key, value in entries}


def validate_pair(en_path: Path, ru_path: Path) -> None:
    en = read_map(en_path)
    ru = read_map(ru_path)
    missing_ru = sorted(set(en) - set(ru))
    missing_en = sorted(set(ru) - set(en))
    if missing_ru or missing_en:
        details = []
        if missing_ru:
            details.append(f"missing in ru: {', '.join(missing_ru)}")
        if missing_en:
            details.append(f"missing in en: {', '.join(missing_en)}")
        raise ValueError("keyset mismatch; " + "; ".join(details))
    mismatches = [key for key in en if en[key] != ru[key]]
    if mismatches:
        raise ValueError("placeholder mismatch: " + ", ".join(sorted(mismatches)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--en", type=Path, required=True)
    parser.add_argument("--ru", type=Path, required=True)
    args = parser.parse_args()
    validate_pair(args.en, args.ru)
    print(f"i18n validation ok: {len(read_map(args.en))} keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
