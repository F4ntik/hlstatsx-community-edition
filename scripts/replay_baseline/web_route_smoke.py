#!/usr/bin/env python3
"""Smoke-test replay-backed web routes for EN/RU runtime regressions."""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.parse
import urllib.request


ROUTES = (
    ("hlstats.php", {"mode": "game", "game": "cstrike"}),
    ("hlstats.php", {"mode": "players", "game": "cstrike"}),
    ("hlstats.php", {"mode": "servers", "server_id": "2", "game": "cstrike"}),
    ("status.php", {}),
)

LANG_MARKERS = {
    "en": ("Language", "Players", "Servers", "Status"),
    "ru": ("Язык", "Игрок", "Сервер", "Статус"),
}

PHP_ERROR_MARKERS = (
    "Fatal error",
    "Parse error",
    "Warning:",
    "Notice:",
    "Stack trace:",
)


def build_url(base_url: str, route: str, params: dict[str, str], lang: str) -> str:
    query = dict(params)
    query["lang"] = lang
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", route) + "?" + urllib.parse.urlencode(query)


def fetch_text(url: str, timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "hlstats-web-route-smoke/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            encoding = response.headers.get_content_charset() or "utf-8"
            return response.status, body.decode(encoding, errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body


def assert_route(url: str, lang: str, timeout: float) -> list[str]:
    status, text = fetch_text(url, timeout)
    failures: list[str] = []
    if status != 200:
        failures.append(f"{url}: expected HTTP 200, got {status}")
    for marker in PHP_ERROR_MARKERS:
        if marker in text:
            failures.append(f"{url}: found PHP error marker {marker!r}")
    if not any(marker in text for marker in LANG_MARKERS.get(lang, ())):
        failures.append(f"{url}: no {lang!r} language marker found")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="Base URL, for example http://127.0.0.1:8281")
    parser.add_argument("--langs", nargs="+", default=["en", "ru"], help="Languages to smoke")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout per route")
    args = parser.parse_args(argv)

    failures: list[str] = []
    for lang in args.langs:
        for route, params in ROUTES:
            url = build_url(args.base_url, route, params, lang)
            failures.extend(assert_route(url, lang, args.timeout))

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    print("web route smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
