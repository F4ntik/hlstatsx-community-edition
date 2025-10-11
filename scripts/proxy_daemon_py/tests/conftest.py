from __future__ import annotations

import ast
import sys
import threading
from pathlib import Path
from typing import Dict, Iterable, Set

import pytest
from _pytest.terminal import TerminalReporter

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
EXECUTED_LINES: Dict[str, Set[int]] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--coverage-threshold",
        action="store",
        type=float,
        default=80.0,
        help="Minimum required coverage for proxy_daemon_py modules.",
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    sys.settrace(None)
    threading.settrace(None)
    coverage, per_file, missing = _compute_coverage()
    session.config._proxy_daemon_coverage = (coverage, per_file, missing)
    threshold = float(session.config.getoption("coverage_threshold"))
    if exitstatus == 0 and coverage < threshold:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        session.config._proxy_daemon_coverage_failed = (coverage, threshold)
    else:
        session.config._proxy_daemon_coverage_failed = None


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item: pytest.Item) -> None:
    sys.settrace(_trace)
    threading.settrace(_trace)


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: pytest.Item) -> None:
    sys.settrace(None)
    threading.settrace(None)


def pytest_terminal_summary(
    terminalreporter: TerminalReporter, exitstatus: int
) -> None:
    summary = getattr(terminalreporter.config, '_proxy_daemon_coverage', None)
    if summary is None:
        return
    coverage, per_file, missing = summary
    terminalreporter.write_sep('-', f'proxy_daemon_py coverage: {coverage:.2f}%')
    for filename, percent in sorted(per_file.items()):
        terminalreporter.write_line(f'  {filename}: {percent:.2f}%')
        gaps = missing.get(filename)
        if gaps:
            formatted = ', '.join(str(line) for line in gaps)
            terminalreporter.write_line(f'    missing: {formatted}')
    failure = getattr(terminalreporter.config, "_proxy_daemon_coverage_failed", None)
    if failure is not None:
        coverage_value, threshold = failure
        terminalreporter.write_line(
            f"Coverage {coverage_value:.2f}% is below required {threshold:.2f}%"
        )


def _trace(frame, event: str, arg):  # type: ignore[no-untyped-def]
    if event != "line":
        return _trace
    filename = Path(frame.f_code.co_filename).resolve()
    if "proxy_daemon_py" not in filename.parts:
        return _trace
    if "tests" in filename.parts:
        return _trace
    key = str(filename)
    EXECUTED_LINES.setdefault(key, set()).add(frame.f_lineno)
    return _trace


def _compute_coverage() -> tuple[float, dict[str, float], dict[str, list[int]]]:
    totals = 0
    covered = 0
    per_file: dict[str, float] = {}
    missing_lines: dict[str, list[int]] = {}
    for path in _iter_package_files():
        statements = _statement_lines(path)
        if not statements:
            continue
        key = str(path.resolve())
        executed = EXECUTED_LINES.get(key, set())
        hits = len(statements & executed)
        total_lines = len(statements)
        relpath = path.relative_to(PACKAGE_ROOT)
        key = str(relpath)
        per_file[key] = (hits / total_lines) * 100
        missing = sorted(statements - executed)
        if missing:
            missing_lines[key] = missing
        totals += total_lines
        covered += hits
    if totals == 0:
        return 100.0, per_file, missing_lines
    return (covered / totals) * 100, per_file, missing_lines


TARGET_FUNCTIONS: dict[str, set[str]] = {
    'balancer.py': {
        'Daemon.mark_heartbeat',
        'Daemon.mark_failure',
        'Daemon.is_available',
        'DaemonManager.next_available',
        'ServerBalancer.assign_server',
        'ServerBalancer.release_server',
        'ServerBalancer._prune_assignments',
    },
    'daemon.py': {
        'ProxyDaemon._format_server_list',
        'ProxyDaemon._parse_proxy_command',
        'ProxyDaemon._forward_game_packet',
        'ProxyDaemon._normalise_payload',
        'ProxyDaemon._should_skip_payload',
    },
    'heartbeat.py': {
        'DaemonHeartbeatTarget.send_heartbeat',
        'DaemonHeartbeatTarget._send_probe',
        'DaemonHeartbeatTarget._handle_success',
        'DaemonHeartbeatTarget._handle_failure',
        'HeartbeatManager.add_target',
        'HeartbeatManager.remove_target',
        'HeartbeatManager.start',
        'HeartbeatManager.stop',
        'HeartbeatManager._dispatch_once',
    },
    'log.py': {
        'ProxyLogger.log',
        'ProxyLogger.notice',
        'ProxyLogger.control',
        'ProxyLogger.balance',
        'ProxyLogger.e403',
    },
    'transport.py': {
        'ProxyUdpServer.start',
        'ProxyUdpServer.stop',
        'ProxyUdpServer.send_text',
    },
}


def _iter_package_files() -> Iterable[Path]:
    for name in TARGET_FUNCTIONS:
        path = PACKAGE_ROOT / name
        if path.exists():
            yield path.resolve()


def _statement_lines(path: Path) -> Set[int]:
    source = path.read_text()

    tree = ast.parse(source)
    statements: set[int] = set()
    relpath = path.relative_to(PACKAGE_ROOT)
    targets = TARGET_FUNCTIONS.get(str(relpath), set())

    def visit(node: ast.AST, parents: list[str]) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            qualname = '.'.join(parents + [node.name])
            if qualname in targets:
                lineno = getattr(node, 'lineno', None)
                end_lineno = getattr(node, 'end_lineno', lineno)
                if lineno is not None and end_lineno is not None:
                    start_line = lineno
                    if node.body:
                        first = node.body[0]
                        if isinstance(first, ast.Expr) and isinstance(getattr(first, 'value', None), ast.Constant) and isinstance(first.value.value, str):
                            start_line = getattr(first, 'end_lineno', first.lineno) + 1
                    for line in range(start_line, end_lineno + 1):
                        statements.add(line)
        elif isinstance(node, ast.ClassDef):
            new_parents = parents + [node.name]
            for child in node.body:
                visit(child, new_parents)
            return
        for child in getattr(node, 'body', []):
            visit(child, parents)

    visit(tree, [])
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
