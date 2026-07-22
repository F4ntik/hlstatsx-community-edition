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


def test_python_ftp_stages_only_the_canonical_sorted_selection_before_compose() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    selector = script[script.index("function Get-SelectedReplayLogs") : script.index("function Get-SelectedLogFingerprint")]
    fingerprint = script[script.index("function Get-SelectedLogFingerprint") : script.index("function Get-ContourFingerprint")]
    legacy_import = script[script.index("function Invoke-LegacyReplayImport") : script.index("function Invoke-PythonFtpImport")]
    stage = script[script.index("function Stage-SelectedFtpLogs") : script.index("function Get-MaintenanceCounts")]
    infra = script[script.index('"infra_updown" {') : script.index('"baseline_restore" {')]

    assert 'Get-ChildItem -LiteralPath $InputDirectory -Filter "*.log" -File | Sort-Object Name | Select-Object -First $ImportLimit' in selector
    assert '$script:SelectedReplayLogs = $selected' in selector
    assert 'return $script:SelectedReplayLogs' in selector
    assert 'Get-SelectedReplayLogs -InputDirectory $InputDirectory -ImportLimit $ImportLimit' in fingerprint
    assert 'Get-SelectedReplayLogs -InputDirectory $InputDirectory -ImportLimit $ImportLimit' in legacy_import
    assert 'Join-Path $stateRoot "ftp-logs"' in script
    assert '$script:FtpLogStagePath = Join-Path $ftpLogStageRoot $script:EvidenceRunId' in script
    assert 'Get-SelectedReplayLogs -InputDirectory $artifactsPath -ImportLimit $MaxImportFiles' in stage
    assert 'Copy-Item -LiteralPath $log.FullName -Destination $stagedPath' in stage
    assert 'FTP log stage does not contain exactly the selected replay logs' in stage
    assert 'Remove-Item' not in stage
    assert 'Stage-SelectedFtpLogs | Out-Null' in infra
    assert '$env:HLSTATS_FTP_LOGS_HOST_PATH = $script:FtpLogStagePath' in infra
    assert '$env:HLSTATS_FTP_LOGS_HOST_PATH = $artifactsPath' not in infra
    assert infra.index('Stage-SelectedFtpLogs | Out-Null') < infra.index('Invoke-ComposeUp -ComposePath $pythonCompose')


def test_compose_up_fails_closed_with_one_bounded_python_ftp_health_retry() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    compose = script.index("function Invoke-ComposeUp")
    function_end = script.index("function Invoke-ContainerMysqlScalar", compose)
    compose_body = script[compose:function_end]
    initial_invoke = compose_body.index("$composeResult = Invoke-DockerCaptured -DockerArguments $args")
    initial_success = compose_body.index("if ($composeResult.exit_code -eq 0)", initial_invoke)
    python_only = compose_body.index("$isPythonCompose", initial_success)
    ftp_only = compose_body.index("$ftpDependencyFailure", python_only)
    wait = compose_body.index("$ftpHealth = Wait-PythonFtpHealthy", ftp_only)
    retry = compose_body.index("$retryResult = Invoke-DockerCaptured -DockerArguments $args", wait)
    strict_failure = compose_body.index('throw "docker compose up failed: $ComposePath. Diagnostics:', retry)
    assert initial_invoke < initial_success < python_only < ftp_only < wait < retry < strict_failure
    assert compose_body.count("Invoke-DockerCaptured -DockerArguments $args") == 2
    assert '$ftpDependencyFailure = $composeOutput -match "hlstatsx-python-log-ftp"' in compose_body
    assert "if ($isPythonCompose -and $ftpDependencyFailure)" in compose_body
    assert "if ($ftpHealth.healthy)" in compose_body
    assert 'throw "docker compose up retry failed: $ComposePath.' in compose_body

    capture = script[script.index("function Invoke-DockerCaptured") : script.index("function Get-ContainerHealthDiagnostic")]
    assert '$ErrorActionPreference = "Continue"' in capture
    assert "& docker @DockerArguments 2>&1 | Out-String" in capture
    assert "$ErrorActionPreference = $previousErrorActionPreference" in capture
    assert "exit_code = $exitCode" in capture

    wait_function = script[script.index("function Wait-PythonFtpHealthy") : compose]
    assert "for ($attempt = 1; $attempt -le 45; $attempt++)" in wait_function
    assert "Start-Sleep -Seconds 2" in wait_function
    assert 'if ($health.status -eq "healthy")' in wait_function
    assert 'healthy = $false' in wait_function


def test_dual_contour_runs_default_maintenance_before_snapshots() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    assert "[switch]$SkipMaintenance" in script
    assert "[string]$MaintenanceDate = \"\"" in script
    assert "[int]$MaintenanceNumDays = 1" in script
    assert '$script:EvidenceClassification = if ($SkipMaintenance) { "raw-only" } else { "release-clean" }' in script
    assert '$allStages = @("infra_updown", "baseline_restore", "preflight", "legacy_import", "python_import", "maintenance", "sql_snapshot", "logical_compare", "web_smoke")' in script
    assert "function Resolve-MaintenanceInputs" in script
    assert "replay-window-max-plus-one" in script
    assert '"-i", "-a", "-r", "-g"' in script
    assert '"--inactive", "--awards", "--ribbons", "--geoip"' in script
    assert '"--numdays", "$($inputs.numdays)", "--date", "$($inputs.date)"' in script
    assert "Historical replay evidence must retain its complete corpus; default maintenance never prunes it." in script
    maintenance_block = script[script.index('"maintenance" {') : script.index('"sql_snapshot" {')]
    assert '"-p"' not in maintenance_block
    assert '"--prune"' not in maintenance_block

    legacy_import = script.index('"legacy_import" {')
    python_import = script.index('"python_import" {')
    maintenance = script.index('"maintenance" {')
    snapshots = script.index('"sql_snapshot" {')
    logical_compare = script.index('"logical_compare" {')
    web_smoke = script.index('"web_smoke" {')
    assert legacy_import < python_import < maintenance < snapshots < logical_compare < web_smoke


def test_dual_contour_maintenance_failure_and_compare_are_evidenced() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    assert 'status = "failed"' in script
    assert 'throw "legacy maintenance failed"' in script
    assert 'throw "python maintenance failed"' in script
    assert '"maintenance-summary-$script:EvidenceLabel.txt"' in script
    assert '"logical-compare-$script:EvidenceLabel.txt"' in script
    assert 'Invoke-PythonCaptured -Command @("scripts/replay_baseline/compare_stats_dbs.py", "--max-examples", "20") -LogPath $comparePath' in script
    assert 'throw "logical DB compare failed; evidence: $comparePath"' in script
    assert "logical_compare_evidence=$($compare.evidence_path)" in script
    assert "legacy_global_awards=http://127.0.0.1:8181/hlstats.php?mode=awards&game=cstrike&tab=global&lang=en" in script
    assert "python_ribbons=http://127.0.0.1:8281/hlstats.php?mode=awards&game=cstrike&tab=ribbons&lang=en" in script
    assert "function Set-MaintenanceSummaryPath" in script
    assert "legacy_maintenance_actions=$($maintenance.legacy_actions)" in script
    assert "python_maintenance_actions=$($maintenance.python_actions)" in script
    assert "inactive_time_mode=$($maintenance.inactive_time_mode)" in script
    assert "legacy_use_timestamp=$($maintenance.legacy_use_timestamp)" in script
    assert "python_use_timestamp=$($maintenance.python_use_timestamp)" in script


def test_dual_contour_web_smoke_is_retained_and_fails_closed() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    assert '"web_smoke" = @("logical_compare")' in script
    assert "function Invoke-WebRouteSmoke" in script
    assert "function Invoke-PythonCaptured" in script
    assert '"scripts/replay_baseline/web_route_smoke.py", "--base-url", $BaseUrl, "--langs") + $Languages' in script
    assert '"legacy-web-smoke-$script:EvidenceLabel.log"' in script
    assert '"python-web-smoke-$script:EvidenceLabel.log"' in script
    assert '"http://127.0.0.1:8181"' in script
    assert '"http://127.0.0.1:8281"' in script
    assert "web_smoke=$($webSmoke.status)" in script
    assert "legacy_web_smoke_languages=$($webSmoke.legacy_languages -join ',')" in script
    assert "python_web_smoke_languages=$($webSmoke.python_languages -join ',')" in script
    assert "legacy_web_smoke_evidence=$($webSmoke.legacy.evidence_path)" in script
    assert "python_web_smoke_evidence=$($webSmoke.python.evidence_path)" in script
    assert 'throw "web route smoke failed; inspect evidence in $auditDir"' in script


def test_dual_contour_web_smoke_resolves_shared_populated_signature_players() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    resolver = script[
        script.index("function Get-SharedSignaturePlayerIds") : script.index(
            "function Stage-SelectedFtpLogs"
        )
    ]
    smoke = script[script.index('"web_smoke" {') : script.index("default {", script.index('"web_smoke" {'))]

    assert 'game = \'cstrike\'' in resolver
    assert "lastName <> ''" in resolver
    assert "kills > 0 OR deaths > 0" in resolver
    assert "connection_time > 0" not in resolver
    assert "ORDER BY playerId ASC" in resolver
    assert "LIMIT 2" in resolver
    assert 'ContainerName "hlstatsx-legacy-db"' in resolver
    assert 'ContainerName "hlstatsx-python-db"' in resolver
    assert "signature player IDs are not shared" in resolver
    assert "$signaturePlayerIds = @(Get-SharedSignaturePlayerIds)" in smoke
    assert "$pythonSignaturePlayerIds = @($signaturePlayerIds)" in smoke
    assert "signature_player_ids = @($signaturePlayerIds)" in smoke
    assert '"--sig-player-id", $playerId' in script


def test_dual_contour_smokes_legacy_in_english_and_python_in_en_ru() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )
    smoke = script[script.index('"web_smoke" {') : script.index("default {", script.index('"web_smoke" {'))]

    assert '$legacyLanguages = @("en")' in smoke
    assert '$pythonLanguages = @("en", "ru")' in smoke
    assert '$legacySignaturePlayerIds = @($signaturePlayerIds[0])' in smoke
    assert '$pythonSignaturePlayerIds = @($signaturePlayerIds)' in smoke
    assert '-StackName "legacy"' in smoke
    assert '-Languages $legacyLanguages -SignaturePlayerIds $legacySignaturePlayerIds' in smoke
    assert '-StackName "python"' in smoke
    assert '-Languages $pythonLanguages -SignaturePlayerIds $pythonSignaturePlayerIds' in smoke
    assert 'legacy_languages = $legacyLanguages' in smoke
    assert 'python_languages = $pythonLanguages' in smoke


def test_web_smoke_and_compare_capture_native_exit_and_preserve_evidence() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )
    capture = script[
        script.index("function Invoke-PythonCaptured") : script.index(
            "function Invoke-WebRouteSmoke"
        )
    ]
    smoke = script[
        script.index("function Invoke-WebRouteSmoke") : script.index(
            "function Get-MaintenanceCountSummaryLines"
        )
    ]

    assert '$ErrorActionPreference = "Continue"' in capture
    assert '$output = python @Command 2>&1 | Out-String' in capture
    assert '$exitCode = $LASTEXITCODE' in capture
    assert "$ErrorActionPreference = $previousErrorActionPreference" in capture
    assert 'Set-Content -Path $LogPath -Value $output -NoNewline' in capture
    assert 'elseif (-not (Test-Path -LiteralPath $LogPath))' in capture
    assert 'New-Item -ItemType File -Path $LogPath -Force' in capture
    assert 'Invoke-PythonCaptured -Command $command -LogPath $LogPath' in smoke
    assert 'Invoke-PythonCaptured -Command @("scripts/replay_baseline/compare_stats_dbs.py", "--max-examples", "20") -LogPath $comparePath' in script


def test_maintenance_date_resolution_failure_is_evidenced() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    try_start = script.index("            try {", script.index('"maintenance" {'))
    resolve = script.index("$inputs = Resolve-MaintenanceInputs", try_start)
    catch = script.index("            } catch {", resolve)
    failed = script.index('status = "failed"', catch)
    summary = script.index("Write-MaintenanceSummary -State $script:RunState", failed)
    assert try_start < resolve < catch < failed < summary
    assert '$inputs = [ordered]@{ date = ""; numdays = $MaintenanceNumDays; source = "unresolved" }' in script


def test_reused_legacy_is_raw_only_and_fails_before_runner_stages_when_maintenance_is_enabled() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    guard = script.index("if ($ReuseValidLegacy -and -not $SkipMaintenance")
    target_stages = script.index("$targetStages = Get-StageRange", guard)
    reuse_probe = script.index("Test-ReusableLegacyContour", target_stages)
    assert guard < target_stages < reuse_probe
    assert "reused legacy import anchors are not a post-maintenance receipt" in script
    assert "Use -SkipMaintenance for raw-only reuse" in script


def test_historical_maintenance_uses_verified_server_timestamps_before_calculators() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    assert "function Invoke-ContainerMysqlCommand" in script
    assert "function Set-HistoricalMaintenanceTimestamp" in script
    assert '"UPDATE hlstats_Options SET value=\'1\' WHERE keyname=\'UseTimestamp\';"' in script
    assert '"SELECT value FROM hlstats_Options WHERE keyname=\'UseTimestamp\';"' in script
    assert "UseTimestamp override verification failed" in script
    assert "Use per-game server last_event for inactivity instead of the host clock for historical replay data." in script
    assert 'Set-HistoricalMaintenanceTimestamp -ContainerName "hlstatsx-legacy-db"' in script
    assert 'Set-HistoricalMaintenanceTimestamp -ContainerName "hlstatsx-python-db"' in script
    assert 'inactive_time_mode = "per-game-server-last_event (UseTimestamp=1)"' in script
    assert 'maintenance_inactive_time_mode = "per-game-server-last_event"' in script

    maintenance = script.index('"maintenance" {')
    legacy_override = script.index('Set-HistoricalMaintenanceTimestamp -ContainerName "hlstatsx-legacy-db"', maintenance)
    python_override = script.index('Set-HistoricalMaintenanceTimestamp -ContainerName "hlstatsx-python-db"', legacy_override)
    legacy_calculator = script.index('$legacyCommand = @(', python_override)
    python_calculator = script.index('$pythonCommand = @(', legacy_calculator)
    assert legacy_override < python_override < legacy_calculator < python_calculator


def test_legacy_maintenance_uses_compose_db_options_not_blank_daemon_config() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    maintenance = script.index('"maintenance" {')
    legacy_calculator = script.index("$legacyCommand = @(", maintenance)
    python_calculator = script.index("$pythonCommand = @(", legacy_calculator)
    legacy_command = script[legacy_calculator:python_calculator]

    assert '"exec", "--workdir", "/scripts", "hlstatsx-legacy-daemon"' in legacy_command
    assert '"perl", "./hlstats-awards.pl"' in legacy_command
    assert '"--db-host", "db:3306"' in legacy_command
    assert '"--db-name", "hlstatsxce"' in legacy_command
    assert '"--db-username", "hlstatsxce"' in legacy_command
    assert '"--db-password", "hlx123"' in legacy_command
    assert '"-c", "/scripts/hlstats.conf"' not in legacy_command
    assert '"--configfile", "/app/hlstats.conf"' in script[python_calculator:]


def test_maintenance_command_redacts_db_password_without_changing_execution_arguments() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    redactor = script.index("function ConvertTo-RedactedMaintenanceCommand")
    invoke = script.index("function Invoke-MaintenanceCommand", redactor)
    invoke_end = script.index("function Invoke-WebRouteSmoke", invoke)
    redactor_body = script[redactor:invoke]
    invoke_body = script[invoke:invoke_end]
    summary = script[script.index("function Write-MaintenanceSummary") : script.index("function Write-ContourInfo")]

    assert 'if ($argument -eq "--db-password")' in redactor_body
    assert '"***REDACTED***"' in redactor_body
    assert 'if ($argument -match "^--db-password=")' in redactor_body
    assert '"--db-password=***REDACTED***"' in redactor_body
    display = invoke_body.index("$displayCommand = @(ConvertTo-RedactedMaintenanceCommand -Command $Command)")
    write = invoke_body.index('Write-Host "==> $StackName maintenance: $($displayCommand -join \' \')"', display)
    execute = invoke_body.index("docker @Command 2>&1", write)
    assert display < write < execute
    assert "$Command -join" not in invoke_body
    assert "hlx123" not in invoke_body
    assert "hlx123" not in summary


def test_maintenance_command_retains_empty_log_evidence_after_exit_capture() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-DualContour-1000.ps1").read_text(
        encoding="utf-8"
    )

    invoke = script.index("function Invoke-MaintenanceCommand")
    invoke_end = script.index("function Invoke-WebRouteSmoke", invoke)
    invoke_body = script[invoke:invoke_end]

    exit_capture = invoke_body.index("$exitCode = $LASTEXITCODE")
    ensure_log = invoke_body.index('if (-not (Test-Path -LiteralPath $LogPath))', exit_capture)
    assert exit_capture < ensure_log
    assert 'New-Item -ItemType File -Path $LogPath -Force' in invoke_body


def test_sql_snapshot_captures_maintenance_and_full_geoip_counts() -> None:
    snapshot = Path("scripts/replay_baseline/comparison/Snapshot-ContourSql.ps1").read_text(
        encoding="utf-8"
    )

    assert '"awards_rows=$(Invoke-Query "SELECT COUNT(*) FROM hlstats_Players_Awards;")"' in snapshot
    assert '"ribbons_rows=$(Invoke-Query "SELECT COUNT(*) FROM hlstats_Players_Ribbons;")"' in snapshot
    assert "geoip_flag_rows=" in snapshot
    assert "geoip_country_rows=" in snapshot
    assert "geoip_city_rows=" in snapshot
    assert "geoip_state_rows=" in snapshot
    assert "geoip_coordinates_rows=" in snapshot
    assert "maintenance_use_timestamp=" in snapshot
