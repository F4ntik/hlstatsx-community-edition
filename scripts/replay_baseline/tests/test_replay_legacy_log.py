from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "replay_legacy_log.py"
    spec = importlib.util.spec_from_file_location("replay_legacy_log_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


replay_legacy_log = _load_module()


@pytest.mark.parametrize("options", [[], ["--db-container", "isolated-db"], ["--docker-network", "isolated-net"]])
def test_replay_requires_explicit_container_and_network(options: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        replay_legacy_log.parse_args(["fixture.log", *options])
    assert error.value.code == 2


def test_replay_keeps_explicit_target() -> None:
    args = replay_legacy_log.parse_args([
        "fixture.log", "--db-container", "isolated-db", "--docker-network", "isolated-net"
    ])
    assert args.db_container == "isolated-db"
    assert args.docker_network == "isolated-net"


def test_write_manifest_uses_lf_for_cross_platform_evidence(tmp_path: Path) -> None:
    output = tmp_path / "input.txt"
    replay_legacy_log.write_manifest(
        str(output),
        [tmp_path / "L0000001.log", tmp_path / "L0000002.log"],
    )

    assert output.read_bytes() == b"L0000001.log\nL0000002.log\n"
