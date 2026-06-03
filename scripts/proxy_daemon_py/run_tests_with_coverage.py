from __future__ import annotations

import ast
import sys
from pathlib import Path
import trace

import pytest

ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = ROOT / "proxy_daemon_py"
TEST_PATH = ROOT / "tests"
DEFAULT_THRESHOLD = 80.0


def _iter_package_files() -> list[Path]:
    files: list[Path] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        if "/tests/" in str(path):
            continue
        files.append(path)
    return files


def _statement_lines(path: Path) -> set[int]:
    source = path.read_text()
    tree = ast.parse(source)
    statements: set[int] = set()
    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", None)
        if lineno is None:
            continue
        end_lineno = getattr(node, "end_lineno", lineno)
        for line in range(lineno, end_lineno + 1):
            statements.add(line)
    lines = source.splitlines()
    filtered: set[int] = set()
    for line_no in statements:
        if line_no <= 0 or line_no > len(lines):
            continue
        text = lines[line_no - 1].strip()
        if not text or text.startswith("#"):
            continue
        filtered.add(line_no)
    return filtered


def _compute_coverage(results: trace.CoverageResults) -> tuple[float, dict[str, float]]:
    counts = results.counts
    totals = 0
    covered = 0
    per_file: dict[str, float] = {}
    for path in _iter_package_files():
        key = str(path)
        lines = _statement_lines(path)
        if not lines:
            continue
        total_lines = len(lines)
        hits = sum(1 for line in lines if counts.get((key, line), 0) > 0)
        relpath = path.relative_to(PACKAGE_ROOT.parent)
        per_file[str(relpath)] = (hits / total_lines) * 100
        totals += total_lines
        covered += hits
    if totals == 0:
        return 100.0, per_file
    return (covered / totals) * 100, per_file


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    threshold = DEFAULT_THRESHOLD
    if argv and argv[0].startswith("--threshold="):
        threshold = float(argv.pop(0).split("=", 1)[1])
    tracer = trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])
    exit_code = tracer.runfunc(pytest.main, argv or [str(TEST_PATH)])
    results = tracer.results()
    coverage, per_file = _compute_coverage(results)

    print(f"Overall coverage: {coverage:.2f}%")
    for filename, percent in sorted(per_file.items()):
        print(f"  {filename}: {percent:.2f}%")

    if exit_code != 0:
        return exit_code
    if coverage < threshold:
        print(f"Coverage {coverage:.2f}% is below required {threshold:.2f}%")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
