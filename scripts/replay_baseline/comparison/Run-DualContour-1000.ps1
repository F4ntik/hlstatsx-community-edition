[CmdletBinding()]
param(
    [int]$MaxImportFiles = 1000,
    [string]$ServerIdentity = "37.230.137.48:27015",
    [string]$ArtifactsDir = "",
    [ValidateSet("both", "legacy", "python")]
    [string]$Stack = "both",
    [switch]$SkipBuild,
    [switch]$SkipLegacyImport,
    [switch]$SkipPythonImport,
    [switch]$UsePythonUdpReplay,
    [switch]$UseDumpRestore,
    [switch]$RecreateBaselineSnapshot,
    [ValidateSet("infra_updown", "baseline_restore", "preflight", "legacy_import", "python_import", "sql_snapshot")]
    [string]$FromStage = "",
    [ValidateSet("infra_updown", "baseline_restore", "preflight", "legacy_import", "python_import", "sql_snapshot")]
    [string]$ToStage = "",
    [ValidateSet("infra_updown", "baseline_restore", "preflight", "legacy_import", "python_import", "sql_snapshot")]
    [string]$OnlyStage = "",
    [string]$ResumeRunId = "",
    [switch]$ResumeLatest,
    [string]$StatePath = ""
)

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $here "..\..\..")).Path
$restoreScript = Join-Path $repoRoot "scripts\replay_baseline\restore-baseline.ps1"
$pythonCompose = Join-Path $here "python\docker-compose.yml"
$legacyCompose = Join-Path $here "legacy\docker-compose.yml"
$auditDir = Join-Path $repoRoot "docs\audits\legacy-python-parity-20260423"
$snapshotScript = Join-Path $here "Snapshot-ContourSql.ps1"
$pythonFtpWork = Join-Path $here "python\ftp_work"
$stateRoot = Join-Path $here ".parity-state"

if (-not (Test-Path $restoreScript)) {
    throw "restore-baseline.ps1 not found: $restoreScript"
}
if (-not (Test-Path $pythonCompose)) {
    throw "Python compose not found: $pythonCompose"
}
if (-not (Test-Path $legacyCompose)) {
    throw "Legacy compose not found: $legacyCompose"
}
if (-not (Test-Path $snapshotScript)) {
    throw "Snapshot script not found: $snapshotScript"
}
if (-not (Test-Path $pythonFtpWork)) {
    New-Item -ItemType Directory -Path $pythonFtpWork | Out-Null
}
if (-not (Test-Path $auditDir)) {
    New-Item -ItemType Directory -Path $auditDir | Out-Null
}
if (-not (Test-Path $stateRoot)) {
    New-Item -ItemType Directory -Path $stateRoot | Out-Null
}

if (-not $ArtifactsDir) {
    $ArtifactsDir = Join-Path $repoRoot "scripts\replay_baseline\artifacts"
}
$artifactsPath = (Resolve-Path $ArtifactsDir).Path
if (-not (Test-Path $artifactsPath)) {
    throw "Artifacts path not found: $ArtifactsDir"
}

function Invoke-ComposeUp {
    param(
        [string]$ComposePath
    )
    $args = @("compose", "-f", $ComposePath, "up", "-d")
    if (-not $SkipBuild) {
        $args += "--build"
    }
    docker @args | Out-Null
}

function Invoke-ContainerMysqlScalar {
    param(
        [string]$ContainerName,
        [string]$Sql
    )
    $value = docker exec $ContainerName mysql -uroot -proot123 -D hlstatsxce --batch --raw --skip-column-names -e $Sql
    if ($LASTEXITCODE -ne 0) {
        throw "mysql query failed in $ContainerName"
    }
    return ($value | Out-String).Trim()
}

function Invoke-LegacyReplayImport {
    param(
        [string]$InputDirectory,
        [int]$ImportLimit,
        [string]$Identity
    )
    $manifest = Join-Path $auditDir "legacy-input-manifest-1000.txt"
    $dropped = Join-Path $auditDir "legacy-dropped-lines-1000.txt"
    $runLog = Join-Path $auditDir "legacy-replay-1000.log"

    $windowDir = Join-Path $auditDir "legacy-window-1000"
    if (-not (Test-Path $windowDir)) {
        New-Item -ItemType Directory -Path $windowDir | Out-Null
    }
    Get-ChildItem -Path $windowDir -Filter "*.log" -ErrorAction SilentlyContinue | Remove-Item -Force
    $selected = Get-ChildItem -Path $InputDirectory -Filter "*.log" | Sort-Object Name | Select-Object -First $ImportLimit
    if (-not $selected -or $selected.Count -eq 0) {
        throw "no *.log files found for legacy import in $InputDirectory"
    }
    foreach ($log in $selected) {
        Copy-Item -Path $log.FullName -Destination (Join-Path $windowDir $log.Name) -Force
    }

    python scripts/replay_baseline/replay_legacy_log.py `
        "$windowDir" `
        --server-identity "$Identity" `
        --drop-empty-team-enter-events `
        --input-manifest "$manifest" `
        --dropped-lines-manifest "$dropped" 2>&1 | Tee-Object -FilePath "$runLog"
    if ($LASTEXITCODE -ne 0) {
        throw "legacy replay import failed"
    }
}

function Invoke-PythonFtpImport {
    param(
        [int]$ImportLimit
    )
    $stateFiles = @(Get-ChildItem -Path $pythonFtpWork -Filter "hlstats-ftp-37.230.137.48-27015.*" -ErrorAction SilentlyContinue)
    foreach ($stateFile in $stateFiles) {
        if ($null -ne $stateFile -and $stateFile.FullName -and (Test-Path $stateFile.FullName)) {
            try {
                [System.IO.File]::Delete($stateFile.FullName)
            } catch {
                # best-effort cleanup only; stale state does not block import correctness
            }
        }
    }

    if ($UsePythonUdpReplay) {
        $cmd = @(
            "run", "--rm",
            "--network", "python_hlstatsx_python_net",
            "-v", "${repoRoot}\scripts:/app/scripts",
            "-e", "PYTHONPATH=/app/scripts:/app/scripts/proxy_daemon_py",
            "python-hlstats-worker",
            "python", "/app/scripts/replay_baseline/replay_python_log.py",
            "/app/scripts/replay_baseline/artifacts",
            "--server-identity", "$ServerIdentity"
        )
    } else {
        $cmd = @(
            "run", "--rm",
            "--network", "python_hlstatsx_python_net",
            "-v", "${repoRoot}\scripts:/app/scripts",
            "-v", "${pythonFtpWork}:/tmp/ftp_work",
            "-e", "PYTHONPATH=/app/scripts:/app/scripts/proxy_daemon_py",
            "-e", "HLSTATS_FTP_PASSWORD=hlxftp123",
            "python-hlstats-worker",
            "python", "-m", "hlstats_ftp_py",
            "--gs-ip", "37.230.137.48",
            "--gs-port", "27015",
            "--ftp-ip", "log-ftp",
            "--ftp-port", "21",
            "--ftp-active",
            "--ftp-usr", "hlxslogs",
            "--ftp-dir", "/",
            "--configfile", "/app/hlstats.conf",
            "--cwd", "/tmp/ftp_work",
            "--max-import-files", "$ImportLimit",
            "--ftp-probe-limit", "2000"
        )
    }
    docker @cmd | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "python ftp import failed"
    }
}

$allStages = @("infra_updown", "baseline_restore", "preflight", "legacy_import", "python_import", "sql_snapshot")
$stageDependencies = @{
    "legacy_import" = @("baseline_restore", "preflight")
    "python_import" = @("baseline_restore", "preflight")
    "sql_snapshot"  = @("baseline_restore", "preflight")
}

function Get-ConfigFingerprint {
    $fingerprintPayload = @{
        max_import_files = $MaxImportFiles
        server_identity = $ServerIdentity
        stack = $Stack
        use_python_udp_replay = [bool]$UsePythonUdpReplay
        use_dump_restore = [bool]$UseDumpRestore
        recreate_baseline_snapshot = [bool]$RecreateBaselineSnapshot
    } | ConvertTo-Json -Compress
    return [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($fingerprintPayload))
}

function Resolve-StateFilePath {
    if ($StatePath) {
        return $StatePath
    }
    if ($ResumeRunId) {
        return (Join-Path $stateRoot "$ResumeRunId.json")
    }
    if ($ResumeLatest) {
        $latest = Get-ChildItem -Path $stateRoot -Filter "*.json" -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if ($null -eq $latest) {
            throw "ResumeLatest requested but no state files found in $stateRoot"
        }
        return $latest.FullName
    }
    $newRunId = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss")
    return (Join-Path $stateRoot "$newRunId.json")
}

function Load-RunState {
    param([string]$Path, [string]$Fingerprint)
    if (Test-Path $Path) {
        $state = Get-Content -Path $Path -Raw | ConvertFrom-Json
        $propNames = @($state.PSObject.Properties.Name)
        if ($propNames -notcontains "completed_stages") {
            $state | Add-Member -NotePropertyName "completed_stages" -NotePropertyValue @()
        }
        if ($propNames -notcontains "stage_artifacts") {
            $state | Add-Member -NotePropertyName "stage_artifacts" -NotePropertyValue @{}
        }
        if ($propNames -notcontains "invalidated_by") {
            $state | Add-Member -NotePropertyName "invalidated_by" -NotePropertyValue @()
        }
        return $state
    }
    $runId = [System.IO.Path]::GetFileNameWithoutExtension($Path)
    return [pscustomobject]@{
        run_id = $runId
        started_at = (Get-Date).ToString("o")
        updated_at = (Get-Date).ToString("o")
        config_fingerprint = $Fingerprint
        completed_stages = @()
        stage_artifacts = @{}
        invalidated_by = @()
    }
}

function Save-RunState {
    param([object]$State, [string]$Path)
    $State.updated_at = (Get-Date).ToString("o")
    $State | ConvertTo-Json -Depth 8 | Set-Content -Path $Path -Encoding UTF8
}

function Get-StageRange {
    if ($OnlyStage) {
        return @($OnlyStage)
    }
    $startIndex = 0
    $endIndex = $allStages.Count - 1
    if ($FromStage) {
        $startIndex = [array]::IndexOf($allStages, $FromStage)
    }
    if ($ToStage) {
        $endIndex = [array]::IndexOf($allStages, $ToStage)
    }
    if ($startIndex -lt 0 -or $endIndex -lt 0 -or $startIndex -gt $endIndex) {
        throw "Invalid stage range: FromStage='$FromStage' ToStage='$ToStage' OnlyStage='$OnlyStage'"
    }
    return $allStages[$startIndex..$endIndex]
}

function Validate-StageParamCombination {
    if ($OnlyStage -and ($FromStage -or $ToStage)) {
        throw "OnlyStage cannot be combined with FromStage/ToStage"
    }
    if ($ResumeLatest -and $ResumeRunId) {
        throw "ResumeLatest cannot be combined with ResumeRunId"
    }
}

function Assert-StageDependenciesSatisfied {
    param([object]$State, [string]$Stage, [string]$Fingerprint)
    if ($State.config_fingerprint -ne $Fingerprint) {
        throw "State fingerprint mismatch. Use a new run, or rerun baseline/preflight with the current parameters."
    }
    if (-not $stageDependencies.ContainsKey($Stage)) {
        return
    }
    $completed = @($State.completed_stages)
    foreach ($required in $stageDependencies[$Stage]) {
        if ($completed -notcontains $required) {
            throw "Stage '$Stage' requires completed stage '$required'."
        }
    }
}

function Invalidate-DownstreamStages {
    param([object]$State, [string]$CurrentStage)
    $currentIndex = [array]::IndexOf($allStages, $CurrentStage)
    if ($currentIndex -lt 0) {
        return
    }
    $completed = @($State.completed_stages)
    $remaining = @()
    foreach ($stageName in $completed) {
        $stageIndex = [array]::IndexOf($allStages, $stageName)
        if ($stageIndex -le $currentIndex) {
            $remaining += $stageName
        } else {
            $State.invalidated_by += [pscustomobject]@{
                stage = $stageName
                reason = "rerun_of_$CurrentStage"
                at = (Get-Date).ToString("o")
            }
        }
    }
    $State.completed_stages = $remaining
}

function Mark-StageCompleted {
    param([object]$State, [string]$Stage)
    if (@($State.completed_stages) -notcontains $Stage) {
        $State.completed_stages += $Stage
    }
}

function Invoke-Stage {
    param([string]$StageName)
    switch ($StageName) {
        "infra_updown" {
            Write-Host "==> Bring both contours down"
            docker compose -f $legacyCompose down | Out-Null
            docker compose -f $pythonCompose down | Out-Null

            Write-Host "==> Bring both contours up"
            $env:HLSTATS_FTP_LOGS_HOST_PATH = $artifactsPath
            $env:HLSTATS_FTP_PASSWORD = "hlxftp123"
            Invoke-ComposeUp -ComposePath $legacyCompose
            Invoke-ComposeUp -ComposePath $pythonCompose
        }
        "baseline_restore" {
            Write-Host "==> Restore baseline"
            $restoreArgsBase = @(
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                $restoreScript
            )
            if ($Stack -eq "both" -or $Stack -eq "legacy") {
                $legacyArgs = @($restoreArgsBase + @("-Stack", "legacy"))
                if ($UseDumpRestore) { $legacyArgs += "-ForceDumpRestore" }
                if ($RecreateBaselineSnapshot) { $legacyArgs += "-CreateSnapshot" }
                powershell @legacyArgs
            }
            if ($Stack -eq "both" -or $Stack -eq "python") {
                $pythonArgs = @($restoreArgsBase + @("-Stack", "python"))
                if ($UseDumpRestore) { $pythonArgs += "-ForceDumpRestore" }
                if ($RecreateBaselineSnapshot) { $pythonArgs += "-CreateSnapshot" }
                powershell @pythonArgs
            }
        }
        "preflight" {
            Write-Host "==> Preflight health checks"
            if ($Stack -eq "both" -or $Stack -eq "legacy") {
                $legacyServers = Invoke-ContainerMysqlScalar -ContainerName "hlstatsx-legacy-db" -Sql "SELECT COUNT(*) FROM hlstats_Servers;"
                if ([int]$legacyServers -le 0) {
                    throw "preflight failed: legacy servers not seeded"
                }
            }
            if ($Stack -eq "both" -or $Stack -eq "python") {
                $pythonServers = Invoke-ContainerMysqlScalar -ContainerName "hlstatsx-python-db" -Sql "SELECT COUNT(*) FROM hlstats_Servers;"
                if ([int]$pythonServers -le 0) {
                    throw "preflight failed: python servers not seeded"
                }
            }
        }
        "legacy_import" {
            if ($Stack -eq "python") {
                throw "legacy_import requested with Stack=python"
            }
            Write-Host "==> Legacy import (1000 logs)"
            Invoke-LegacyReplayImport -InputDirectory $artifactsPath -ImportLimit $MaxImportFiles -Identity $ServerIdentity
        }
        "python_import" {
            if ($Stack -eq "legacy") {
                throw "python_import requested with Stack=legacy"
            }
            if ($UsePythonUdpReplay) {
                Write-Host "==> Python import (UDP replay, opt-in)"
            } else {
                Write-Host "==> Python import (stdin default, 1000 logs)"
            }
            Invoke-PythonFtpImport -ImportLimit $MaxImportFiles
        }
        "sql_snapshot" {
            Write-Host "==> SQL snapshots"
            if ($Stack -eq "both" -or $Stack -eq "legacy") {
                powershell -NoProfile -ExecutionPolicy Bypass -File $snapshotScript -Stack legacy -OutputPath (Join-Path $auditDir "legacy-sql-snapshot-1000.txt")
            }
            if ($Stack -eq "both" -or $Stack -eq "python") {
                powershell -NoProfile -ExecutionPolicy Bypass -File $snapshotScript -Stack python -OutputPath (Join-Path $auditDir "python-sql-snapshot-1000.txt")
            }
        }
        default {
            throw "Unknown stage: $StageName"
        }
    }
}

Validate-StageParamCombination
$targetStages = Get-StageRange
if (-not $OnlyStage -and -not $FromStage -and -not $ToStage) {
    if ($SkipLegacyImport) {
        $targetStages = @($targetStages | Where-Object { $_ -ne "legacy_import" })
    }
    if ($SkipPythonImport) {
        $targetStages = @($targetStages | Where-Object { $_ -ne "python_import" })
    }
}

$fingerprint = Get-ConfigFingerprint
$stateFile = Resolve-StateFilePath
$runState = Load-RunState -Path $stateFile -Fingerprint $fingerprint
if (-not $runState.config_fingerprint) {
    $runState.config_fingerprint = $fingerprint
}

if ((Test-Path $stateFile) -and $runState.config_fingerprint -ne $fingerprint) {
    throw "State fingerprint mismatch for run '$($runState.run_id)'. Provide new StatePath/RunId or align parameters."
}

foreach ($stageName in $targetStages) {
    if ($stageName -eq "legacy_import" -or $stageName -eq "python_import" -or $stageName -eq "sql_snapshot") {
        Assert-StageDependenciesSatisfied -State $runState -Stage $stageName -Fingerprint $fingerprint
    }
    Invalidate-DownstreamStages -State $runState -CurrentStage $stageName
    Save-RunState -State $runState -Path $stateFile
    Invoke-Stage -StageName $stageName
    Mark-StageCompleted -State $runState -Stage $stageName
    Save-RunState -State $runState -Path $stateFile
}

Write-Host "==> Done"
Write-Host "Run state: $stateFile"
Write-Host "Legacy web: http://127.0.0.1:8181/hlstats.php"
Write-Host "Python web: http://127.0.0.1:8281/hlstats.php"
