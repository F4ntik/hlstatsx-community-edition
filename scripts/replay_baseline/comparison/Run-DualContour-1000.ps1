[CmdletBinding()]
param(
    [int]$MaxImportFiles = 1000,
    [string]$ServerIdentity = "37.230.137.48:27015",
    [string]$ArtifactsDir = "",
    [string]$ArtifactLabel = "",
    [string]$EvidenceRunId = "",
    [switch]$OverwriteEvidence,
    [ValidateSet("both", "legacy", "python")]
    [string]$Stack = "both",
    [switch]$SkipBuild,
    [switch]$SkipLegacyImport,
    [switch]$SkipPythonImport,
    [switch]$ReuseValidLegacy,
    [switch]$AdoptCurrentLegacy,
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
$contourInfoDir = Join-Path $stateRoot "contour-info"

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
if (-not (Test-Path $contourInfoDir)) {
    New-Item -ItemType Directory -Path $contourInfoDir | Out-Null
}

if (-not $ArtifactsDir) {
    $ArtifactsDir = Join-Path $repoRoot "scripts\replay_baseline\artifacts"
}
$artifactsPath = (Resolve-Path $ArtifactsDir).Path
if (-not (Test-Path $artifactsPath)) {
    throw "Artifacts path not found: $ArtifactsDir"
}

function Resolve-ArtifactLabel {
    param(
        [string]$Requested,
        [int]$ImportLimit
    )
    if ($Requested) {
        $value = $Requested.Trim()
        if ($value -notmatch '^(narrow-1000|full-41513|prefix-[A-Za-z0-9][A-Za-z0-9_.-]*)$') {
            throw "ArtifactLabel must be narrow-1000, full-41513, or prefix-*; got '$Requested'"
        }
        if ($value -eq "narrow-1000" -and $ImportLimit -ne 1000) {
            throw "ArtifactLabel narrow-1000 requires MaxImportFiles=1000"
        }
        if ($value -eq "full-41513" -and $ImportLimit -ne 41513) {
            throw "ArtifactLabel full-41513 requires MaxImportFiles=41513"
        }
        return $value
    }
    if ($ImportLimit -eq 1000) {
        return "narrow-1000"
    }
    if ($ImportLimit -eq 41513) {
        return "full-41513"
    }
    return "prefix-$ImportLimit"
}

$script:ArtifactLabel = Resolve-ArtifactLabel -Requested $ArtifactLabel -ImportLimit $MaxImportFiles
$script:ContourName = $script:ArtifactLabel
$script:EvidenceRunId = if ($EvidenceRunId) {
    $safeRunId = $EvidenceRunId.Trim() -replace '[^A-Za-z0-9_.-]', '_'
    if ($safeRunId -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]*$') {
        throw "EvidenceRunId must contain only letters, digits, dot, underscore, or hyphen"
    }
    $safeRunId
} else {
    $generatedRunId = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmssfff")
    "$generatedRunId-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
}
$script:EvidenceLabel = "$script:ArtifactLabel-$script:EvidenceRunId"

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

function Get-Sha256Text {
    param([string]$Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        $hash = $sha.ComputeHash($bytes)
        return -join ($hash | ForEach-Object { $_.ToString("x2") })
    } finally {
        $sha.Dispose()
    }
}

function Publish-EvidenceFile {
    param(
        [string]$SourcePath,
        [string]$DestinationPath
    )
    if (-not (Test-Path -LiteralPath $SourcePath)) {
        throw "evidence source not found: $SourcePath"
    }
    if ((Test-Path -LiteralPath $DestinationPath) -and -not $OverwriteEvidence) {
        throw "evidence destination already exists; use a new EvidenceRunId or -OverwriteEvidence: $DestinationPath"
    }
    $destinationDir = Split-Path -Parent $DestinationPath
    if (-not (Test-Path -LiteralPath $destinationDir)) {
        New-Item -ItemType Directory -Path $destinationDir | Out-Null
    }
    Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force:$OverwriteEvidence
}

function Assert-EvidencePathsAvailable {
    param([string[]]$Paths)
    if ($OverwriteEvidence) {
        return
    }
    foreach ($path in $Paths) {
        if (Test-Path -LiteralPath $path) {
            throw "evidence path already exists; use a new EvidenceRunId or -OverwriteEvidence: $path"
        }
    }
}

function Get-SelectedLogFingerprint {
    param(
        [string]$InputDirectory,
        [int]$ImportLimit
    )
    $selected = @(Get-ChildItem -Path $InputDirectory -Filter "*.log" | Sort-Object Name | Select-Object -First $ImportLimit)
    if ($selected.Count -eq 0) {
        throw "no *.log files found for fingerprint in $InputDirectory"
    }
    $lines = @()
    foreach ($log in $selected) {
        $lines += "$($log.Name)|$($log.Length)"
    }
    return [pscustomobject]@{
        count = $selected.Count
        first = $selected[0].Name
        last = $selected[$selected.Count - 1].Name
        sha256 = Get-Sha256Text -Text ($lines -join "`n")
    }
}

function Get-ContourFingerprint {
    param(
        [string]$StackName
    )
    $logFingerprint = Get-SelectedLogFingerprint -InputDirectory $artifactsPath -ImportLimit $MaxImportFiles
    $payload = [ordered]@{
        stack = $StackName
        max_import_files = $MaxImportFiles
        artifacts_path = $artifactsPath
        logs_count = $logFingerprint.count
        logs_first = $logFingerprint.first
        logs_last = $logFingerprint.last
        logs_sha256 = $logFingerprint.sha256
        server_identity = $ServerIdentity
        replay_policy = "drop-empty-team-enter-events"
        baseline_mode = if ($UseDumpRestore) { "dump" } else { "snapshot" }
        recreate_baseline_snapshot = [bool]$RecreateBaselineSnapshot
    }
    if ($StackName -eq "python") {
        $payload.use_python_udp_replay = [bool]$UsePythonUdpReplay
    }
    $json = $payload | ConvertTo-Json -Compress
    return [pscustomobject]@{
        sha256 = Get-Sha256Text -Text $json
        payload = $payload
    }
}

function Test-ContainerRunning {
    param([string]$ContainerName)
    $status = docker inspect -f "{{.State.Running}}" $ContainerName 2>$null
    return ($LASTEXITCODE -eq 0 -and (($status | Out-String).Trim()) -eq "true")
}

function Get-ContourAnchorCounts {
    param(
        [string]$ContainerName
    )
    return [ordered]@{
        players = [int](Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COUNT(*) FROM hlstats_Players;")
        frags = [int](Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COUNT(*) FROM hlstats_Events_Frags;")
        team_bonuses = [int](Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COUNT(*) FROM hlstats_Events_TeamBonuses;")
        entries = [int](Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COUNT(*) FROM hlstats_Events_Entries;")
        server_rows = [int](Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COUNT(*) FROM hlstats_Servers WHERE address='37.230.137.48' AND port=27015;")
    }
}

function Write-ContourInfo {
    param(
        [string]$StackName,
        [string]$Fingerprint,
        [object]$FingerprintPayload,
        [object]$AnchorCounts,
        [string[]]$Containers,
        [string]$Status = "loaded"
    )
    $infoPath = Join-Path $contourInfoDir "$StackName-$script:EvidenceLabel.json"
    if ((Test-Path -LiteralPath $infoPath) -and -not $OverwriteEvidence) {
        throw "contour metadata already exists; use a new EvidenceRunId or -OverwriteEvidence: $infoPath"
    }
    $info = [ordered]@{
        contour = $script:ContourName
        artifact_label = $script:ArtifactLabel
        evidence_run_id = $script:EvidenceRunId
        stack = $StackName
        status = $Status
        fingerprint = $Fingerprint
        created_at = (Get-Date).ToString("o")
        git_commit = (git -C $repoRoot rev-parse --short HEAD)
        server_identity = $ServerIdentity
        replay_policy = "drop-empty-team-enter-events"
        baseline_mode = if ($UseDumpRestore) { "dump" } else { "snapshot" }
        artifacts_path = $artifactsPath
        inputs = $FingerprintPayload
        anchors = $AnchorCounts
    }
    $info | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $infoPath -Encoding UTF8
    foreach ($container in $Containers) {
        if (Test-ContainerRunning -ContainerName $container) {
            docker cp $infoPath "${container}:/CONTOUR_INFO.json" | Out-Null
        }
    }
    return $infoPath
}

function Test-ReusableLegacyContour {
    param(
        [string]$ExpectedFingerprint
    )
    $canonicalInfoPath = Join-Path $contourInfoDir "legacy-$script:ArtifactLabel.json"
    $versionedInfo = @(Get-ChildItem -LiteralPath $contourInfoDir -Filter "legacy-$script:ArtifactLabel-*.json" -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending)
    $infoPath = if (Test-Path -LiteralPath $canonicalInfoPath) {
        $canonicalInfoPath
    } elseif ($versionedInfo.Count -gt 0) {
        $versionedInfo[0].FullName
    } else {
        $null
    }
    if (-not $infoPath) {
        Write-Host "==> Legacy reuse unavailable: contour info file not found."
        return $false
    }
    if (-not (Test-ContainerRunning -ContainerName "hlstatsx-legacy-db")) {
        Write-Host "==> Legacy reuse unavailable: hlstatsx-legacy-db is not running."
        return $false
    }
    $info = Get-Content -Path $infoPath -Raw | ConvertFrom-Json
    if ($info.fingerprint -ne $ExpectedFingerprint) {
        Write-Host "==> Legacy reuse unavailable: fingerprint mismatch."
        return $false
    }
    $anchors = Get-ContourAnchorCounts -ContainerName "hlstatsx-legacy-db"
    if ($anchors.players -le 0 -or $anchors.frags -le 0 -or $anchors.server_rows -ne 1) {
        Write-Host "==> Legacy reuse unavailable: anchor counts are not loaded."
        return $false
    }
    Write-ContourInfo `
        -StackName "legacy" `
        -Fingerprint $ExpectedFingerprint `
        -FingerprintPayload $info.inputs `
        -AnchorCounts $anchors `
        -Containers @("hlstatsx-legacy-db", "hlstatsx-legacy-web", "hlstatsx-legacy-daemon") | Out-Null
    Write-Host "==> Reusing valid legacy $script:ContourName contour."
    return $true
}

function Adopt-CurrentLegacyContour {
    if (-not (Test-ContainerRunning -ContainerName "hlstatsx-legacy-db")) {
        throw "cannot adopt current legacy contour: hlstatsx-legacy-db is not running"
    }
    $anchors = Get-ContourAnchorCounts -ContainerName "hlstatsx-legacy-db"
    if ($anchors.players -le 0 -or $anchors.frags -le 0 -or $anchors.server_rows -ne 1) {
        throw "cannot adopt current legacy contour: anchor counts are not loaded"
    }
    $infoPath = Write-ContourInfo `
        -StackName "legacy" `
        -Fingerprint $script:LegacyContourFingerprint.sha256 `
        -FingerprintPayload $script:LegacyContourFingerprint.payload `
        -AnchorCounts $anchors `
        -Containers @("hlstatsx-legacy-db", "hlstatsx-legacy-web", "hlstatsx-legacy-daemon")
    Write-Host "==> Adopted current legacy $script:ContourName contour: $infoPath"
}

function Invoke-LegacyReplayImport {
    param(
        [string]$InputDirectory,
        [int]$ImportLimit,
        [string]$Identity
    )
    $manifest = Join-Path $auditDir "legacy-input-manifest-$script:EvidenceLabel.txt"
    $dropped = Join-Path $auditDir "legacy-dropped-lines-$script:EvidenceLabel.txt"
    $runLog = Join-Path $auditDir "legacy-replay-$script:EvidenceLabel.log"

    $windowDir = Join-Path $auditDir "legacy-window-$script:EvidenceLabel"
    Assert-EvidencePathsAvailable @($manifest, $dropped, $runLog, $windowDir)
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
    $pythonInputManifestName = "python-input-manifest-$script:EvidenceLabel.txt"
    $pythonIgnoredManifestName = "python-ignored-lines-$script:EvidenceLabel.txt"
    $pythonInputManifestTemp = Join-Path $pythonFtpWork $pythonInputManifestName
    $pythonIgnoredManifestTemp = Join-Path $pythonFtpWork $pythonIgnoredManifestName
    foreach ($tempEvidence in @($pythonInputManifestTemp, $pythonIgnoredManifestTemp)) {
        if ((Test-Path -LiteralPath $tempEvidence) -and -not $OverwriteEvidence) {
            throw "temporary evidence already exists; use a new EvidenceRunId or -OverwriteEvidence: $tempEvidence"
        }
        if (Test-Path -LiteralPath $tempEvidence) {
            Remove-Item -LiteralPath $tempEvidence -Force
        }
    }
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
            "-v", "${pythonFtpWork}:/tmp/ftp_work",
            "-e", "PYTHONPATH=/app/scripts",
            "python-hlstats-worker",
            "python", "/app/scripts/replay_baseline/replay_python_log.py",
            "/app/scripts/replay_baseline/artifacts",
            "--server-identity", "$ServerIdentity",
            "--input-manifest", "/tmp/ftp_work/$pythonInputManifestName",
            "--dropped-lines-manifest", "/tmp/ftp_work/$pythonIgnoredManifestName"
        )
    } else {
        $ftpProbeLimit = [Math]::Max(500, $ImportLimit + 150)
        $cmd = @(
            "run", "--rm",
            "--network", "python_hlstatsx_python_net",
            "-v", "${repoRoot}\scripts:/app/scripts",
            "-v", "${pythonFtpWork}:/tmp/ftp_work",
            "-e", "PYTHONPATH=/app/scripts",
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
            "--ftp-probe-limit", "$ftpProbeLimit",
            "--order-by-name",
            "--static-replay",
            "--input-manifest", "/tmp/ftp_work/$pythonInputManifestName",
            "--ignored-lines-manifest", "/tmp/ftp_work/$pythonIgnoredManifestName",
            "--continue-on-parse-error"
        )
    }
    docker @cmd | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "python ftp import failed"
    }
    Publish-EvidenceFile `
        -SourcePath $pythonInputManifestTemp `
        -DestinationPath (Join-Path $auditDir $pythonInputManifestName)
    Publish-EvidenceFile `
        -SourcePath $pythonIgnoredManifestTemp `
        -DestinationPath (Join-Path $auditDir $pythonIgnoredManifestName)
}

$allStages = @("infra_updown", "baseline_restore", "preflight", "legacy_import", "python_import", "sql_snapshot")
$stageDependencies = @{
    "legacy_import" = @("baseline_restore", "preflight")
    "python_import" = @("baseline_restore", "preflight")
    "sql_snapshot"  = @("baseline_restore", "preflight")
}

function Get-ConfigFingerprint {
    $fingerprintPayload = @{
        artifact_label = $script:ArtifactLabel
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
            if (-not $script:ReuseLegacyForRun) {
                Write-Host "==> Bring legacy contour down"
                docker compose -f $legacyCompose down | Out-Null
            } else {
                Write-Host "==> Keep valid legacy contour running"
            }
            Write-Host "==> Bring Python contour down"
            docker compose -f $pythonCompose down | Out-Null

            Write-Host "==> Bring contours up"
            $env:HLSTATS_FTP_LOGS_HOST_PATH = $artifactsPath
            $env:HLSTATS_FTP_PASSWORD = "hlxftp123"
            if (-not $script:ReuseLegacyForRun) {
                Invoke-ComposeUp -ComposePath $legacyCompose
            }
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
            if (($Stack -eq "both" -or $Stack -eq "legacy") -and -not $script:ReuseLegacyForRun) {
                $legacyArgs = @($restoreArgsBase + @("-Stack", "legacy"))
                if ($UseDumpRestore) { $legacyArgs += "-ForceDumpRestore" }
                if ($RecreateBaselineSnapshot) { $legacyArgs += "-CreateSnapshot" }
                powershell @legacyArgs
            } elseif ($script:ReuseLegacyForRun) {
                Write-Host "==> Legacy baseline restore skipped; valid contour is already loaded."
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
            if ($script:ReuseLegacyForRun) {
                Write-Host "==> Legacy import skipped; valid $script:ContourName contour is already loaded."
                return
            }
            Write-Host "==> Legacy import ($MaxImportFiles logs)"
            Invoke-LegacyReplayImport -InputDirectory $artifactsPath -ImportLimit $MaxImportFiles -Identity $ServerIdentity
            $anchors = Get-ContourAnchorCounts -ContainerName "hlstatsx-legacy-db"
            Write-ContourInfo `
                -StackName "legacy" `
                -Fingerprint $script:LegacyContourFingerprint.sha256 `
                -FingerprintPayload $script:LegacyContourFingerprint.payload `
                -AnchorCounts $anchors `
                -Containers @("hlstatsx-legacy-db", "hlstatsx-legacy-web", "hlstatsx-legacy-daemon") | Out-Null
        }
        "python_import" {
            if ($Stack -eq "legacy") {
                throw "python_import requested with Stack=legacy"
            }
            if ($UsePythonUdpReplay) {
                Write-Host "==> Python import (UDP replay, opt-in)"
            } else {
                Write-Host "==> Python import (stdin default, $MaxImportFiles logs)"
            }
            Invoke-PythonFtpImport -ImportLimit $MaxImportFiles
            $anchors = Get-ContourAnchorCounts -ContainerName "hlstatsx-python-db"
            Write-ContourInfo `
                -StackName "python" `
                -Fingerprint $script:PythonContourFingerprint.sha256 `
                -FingerprintPayload $script:PythonContourFingerprint.payload `
                -AnchorCounts $anchors `
                -Containers @("hlstatsx-python-db", "hlstatsx-python-web", "hlstatsx-python-worker", "hlstatsx-python-proxy", "hlstatsx-python-log-ftp") | Out-Null
        }
        "sql_snapshot" {
            Write-Host "==> SQL snapshots"
            if (($Stack -eq "both" -or $Stack -eq "legacy") -and -not $script:ReuseLegacyForRun) {
                $legacySnapshotPath = Join-Path $auditDir "legacy-sql-snapshot-$script:EvidenceLabel.txt"
                Assert-EvidencePathsAvailable @($legacySnapshotPath)
                powershell -NoProfile -ExecutionPolicy Bypass -File $snapshotScript -Stack legacy -OutputPath $legacySnapshotPath
            } elseif ($script:ReuseLegacyForRun) {
                Write-Host "==> Legacy SQL snapshot skipped; valid snapshot anchors are recorded in contour metadata."
            }
            if ($Stack -eq "both" -or $Stack -eq "python") {
                $pythonSnapshotPath = Join-Path $auditDir "python-sql-snapshot-$script:EvidenceLabel.txt"
                Assert-EvidencePathsAvailable @($pythonSnapshotPath)
                powershell -NoProfile -ExecutionPolicy Bypass -File $snapshotScript -Stack python -OutputPath $pythonSnapshotPath
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
$script:LegacyContourFingerprint = Get-ContourFingerprint -StackName "legacy"
$script:PythonContourFingerprint = Get-ContourFingerprint -StackName "python"
$script:ReuseLegacyForRun = $false
if ($AdoptCurrentLegacy -and ($Stack -eq "both" -or $Stack -eq "legacy")) {
    Adopt-CurrentLegacyContour
}
if ($ReuseValidLegacy -and ($Stack -eq "both" -or $Stack -eq "legacy")) {
    $script:ReuseLegacyForRun = Test-ReusableLegacyContour -ExpectedFingerprint $script:LegacyContourFingerprint.sha256
    if (-not $script:ReuseLegacyForRun) {
        Write-Host "==> Legacy reuse requested, but no valid reusable contour was found; running full legacy stages."
    }
}
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
