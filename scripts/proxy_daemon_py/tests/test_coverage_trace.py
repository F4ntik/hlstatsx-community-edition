from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

CONFTST_PATH = Path(__file__).with_name("conftest.py")
SPEC = importlib.util.spec_from_file_location("coverage_trace_conftest", CONFTST_PATH)
assert SPEC is not None and SPEC.loader is not None
conftest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(conftest)


def _frame(filename: str, lineno: int) -> SimpleNamespace:
    return SimpleNamespace(
        f_code=SimpleNamespace(co_filename=filename),
        f_lineno=lineno,
    )


def test_trace_records_package_lines_but_ignores_test_lines() -> None:
    package_filename = str((conftest.PACKAGE_DIR / "daemon.py").resolve())
    test_filename = str(Path(__file__).resolve())
    package_line = 1
    package_before = conftest.EXECUTED_LINES.get(package_filename)
    test_before = conftest.EXECUTED_LINES.get(test_filename)

    try:
        traced = conftest._trace(_frame(package_filename, package_line), "line", None)
        assert traced is conftest._trace
        assert package_line in conftest.EXECUTED_LINES[package_filename]

        assert conftest._trace(_frame(test_filename, package_line), "line", None) is conftest._trace
        assert conftest.EXECUTED_LINES.get(test_filename) is test_before
    finally:
        if package_before is None:
            conftest.EXECUTED_LINES.pop(package_filename, None)
        else:
            conftest.EXECUTED_LINES[package_filename] = package_before
