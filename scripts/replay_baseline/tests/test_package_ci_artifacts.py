from __future__ import annotations

import json
from pathlib import Path

import pytest

import package_ci_artifacts as packaging


def test_package_summary_writes_fixed_metadata_only_artifact(tmp_path) -> None:
    output = packaging.package_summary(
        tmp_path / "publication",
        max_import_files=1000,
        dual_replay_outcome="success",
    )

    assert output.name == "nightly-parity-summary.json"
    assert list(output.parent.iterdir()) == [output]
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "schema_version": 2,
        "publication": "sanitized-nightly-parity-summary",
        "max_import_files": 1000,
        "steps": {"dual_replay": "success"},
        "dual_replay_integrated_gates": [
            "historical_maintenance",
            "database_compare",
            "web_smoke",
        ],
    }


@pytest.mark.parametrize("outcome", ["", "success\nsecret", "unknown"])
def test_package_summary_rejects_unbounded_outcome_text(tmp_path, outcome: str) -> None:
    with pytest.raises(ValueError, match="unsupported step outcome"):
        packaging.package_summary(
            tmp_path,
            max_import_files=1000,
            dual_replay_outcome=outcome,
        )


def test_parse_args_rejects_nonpositive_import_limit() -> None:
    with pytest.raises(SystemExit):
        packaging.parse_args(
            [
                "--output-directory",
                "unused",
                "--max-import-files",
                "0",
                "--dual-replay-outcome",
                "success",
            ]
        )


def test_workflows_keep_shared_packages_and_raw_replay_output_out_of_uploads() -> None:
    repository = Path(__file__).resolve().parents[3]
    product_ci = (repository / ".github" / "workflows" / "product-ci.yml").read_text(encoding="utf-8")
    nightly = (repository / ".github" / "workflows" / "nightly-parity.yml").read_text(encoding="utf-8")

    for package_path in (
        "scripts/hlx_core/**",
        "scripts/hlstats_awards_py/**",
        "scripts/hlstats_ftp_py/**",
        "scripts/hlstats_resolve_py/**",
        "scripts/import_bans_py/**",
    ):
        assert product_ci.count(package_path) == 2

    for raw_path in (
        "docs/audits/legacy-python-parity-20260423/**",
        "scripts/replay_baseline/artifacts/parity-traces/**",
        "scripts/replay_baseline/comparison/.parity-state/**",
        "scripts/replay_baseline/artifacts/**/*.json",
        "scripts/replay_baseline/artifacts/**/*.txt",
    ):
        assert raw_path not in nightly

    # Release-clean maintenance needs a freshly imported legacy contour.  The
    # runner rejects reuse because its old anchors are not post-maintenance
    # evidence, so CI must not ask for that incompatible shortcut.
    assert "-ReuseValidLegacy" not in nightly
    # The canonical runner is the single fail-closed authority for its
    # maintenance, logical compare, and replay-backed EN/RU smoke gates.
    assert "scripts/replay_baseline/web_route_smoke.py" not in nightly
    assert "id: geoip-backfill" not in nightly
    assert "id: database-compare" not in nightly
    assert "--dual-replay-outcome '${{ steps.dual-replay.outcome }}'" in nightly
    assert "path: ${{ steps.package-summary.outputs.artifact_file }}" in nightly
