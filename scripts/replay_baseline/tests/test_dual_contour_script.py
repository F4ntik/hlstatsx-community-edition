from __future__ import annotations

from pathlib import Path


def test_dual_contour_artifacts_are_labelled_by_import_window() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    assert '[string]$ArtifactLabel = ""' in script
    assert '[string]$EvidenceRunId = ""' in script
    assert 'function Resolve-ArtifactLabel' in script
    assert 'return "narrow-1000"' in script
    assert 'return "full-41513"' in script
    assert 'return "prefix-$ImportLimit"' in script
    assert '"legacy-input-manifest-$script:EvidenceLabel.txt"' in script
    assert '"legacy-dropped-lines-$script:EvidenceLabel.txt"' in script
    assert '"legacy-replay-$script:EvidenceLabel.log"' in script
    assert '"legacy-window-$script:EvidenceLabel"' in script
    assert '"legacy-sql-snapshot-$script:EvidenceLabel.txt"' in script
    assert '"python-sql-snapshot-$script:EvidenceLabel.txt"' in script


def test_dual_contour_metadata_can_use_explicit_contour_label() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    assert '$script:ContourName = $script:ArtifactLabel' in script
    assert '"$StackName-$script:EvidenceLabel.json"' in script
    assert '"legacy-$script:ArtifactLabel.json"' in script
    assert "artifact_label = $script:ArtifactLabel" in script
    assert 'Publish-EvidenceFile' in script
    assert '"--input-manifest", "/tmp/ftp_work/$pythonInputManifestName"' in script
    assert '"--ignored-lines-manifest", "/tmp/ftp_work/$pythonIgnoredManifestName"' in script
    assert '"--continue-on-parse-error"' in script
    assert '"--static-replay"' in script
    assert 'use a new EvidenceRunId or -OverwriteEvidence' in script
    assert 'function Assert-EvidencePathsAvailable' in script
    assert 'Assert-EvidencePathsAvailable @($manifest, $dropped, $runLog, $windowDir)' in script
    assert 'Assert-EvidencePathsAvailable @($legacySnapshotPath)' in script
    assert 'Assert-EvidencePathsAvailable @($pythonSnapshotPath)' in script


def test_python_manifests_publish_only_after_import_success() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    import_call = script.index("    docker @cmd | Out-Null")
    failure_guard = script.index('throw "python ftp import failed"', import_call)
    publish_input = script.index("-SourcePath $pythonInputManifestTemp", import_call)
    publish_ignored = script.index("-SourcePath $pythonIgnoredManifestTemp", publish_input)

    assert import_call < failure_guard < publish_input < publish_ignored


def test_python_replay_uses_ephemeral_named_volume_and_restores_manifests() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    assert '$pythonReplayVolume = "hlstatsx-python-replay-"' in script
    assert "docker volume ls --format '{{.Name}}'" in script
    assert '$existingDockerVolumes -contains $pythonReplayVolume' in script
    assert 'docker volume create $pythonReplayVolume' in script
    assert '"--mount", "type=volume,source=$pythonReplayVolume,target=/tmp/ftp_work"' in script
    assert 'target=/from,readonly' in script
    assert '--entrypoint sh' in script
    assert 'python-hlstats-worker -lc' in script
    assert 'alpine sh' not in script
    assert 'cp /from/$pythonInputManifestName /to/$pythonInputManifestName' in script
    assert 'cp /from/$pythonIgnoredManifestName /to/$pythonIgnoredManifestName' in script
    assert 'if ($pythonReplayVolumeCreated)' in script
    assert 'docker volume rm $pythonReplayVolume' in script


def test_legacy_evidence_is_guarded_before_window_cleanup_and_replay() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    guard = script.index(
        "Assert-EvidencePathsAvailable @($manifest, $dropped, $runLog, $windowDir)"
    )
    cleanup = script.index(
        "Get-ChildItem -Path $windowDir -Filter \"*.log\" -ErrorAction SilentlyContinue | Remove-Item -Force",
        guard,
    )
    replay = script.index(
        "python scripts/replay_baseline/replay_legacy_log.py",
        cleanup,
    )

    assert guard < cleanup < replay
