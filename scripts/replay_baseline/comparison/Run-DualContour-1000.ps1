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
    [switch]$SkipMaintenance,
    [string]$MaintenanceDate = "",
    [ValidateRange(1, 36500)]
    [int]$MaintenanceNumDays = 1,
    [ValidateSet("infra_updown", "baseline_restore", "preflight", "legacy_import", "python_import", "maintenance", "sql_snapshot", "logical_compare", "web_smoke")]
    [string]$FromStage = "",
    [ValidateSet("infra_updown", "baseline_restore", "preflight", "legacy_import", "python_import", "maintenance", "sql_snapshot", "logical_compare", "web_smoke")]
    [string]$ToStage = "",
    [ValidateSet("infra_updown", "baseline_restore", "preflight", "legacy_import", "python_import", "maintenance", "sql_snapshot", "logical_compare", "web_smoke")]
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
$ftpLogStageRoot = Join-Path $stateRoot "ftp-logs"

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
$script:SelectedReplayLogs = $null

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
$script:FtpLogStagePath = Join-Path $ftpLogStageRoot $script:EvidenceRunId
$script:EvidenceClassification = if ($SkipMaintenance) { "raw-only" } else { "release-clean" }
$script:LegacyMaintenanceActions = "-i -a -r -g"
$script:PythonMaintenanceActions = "--inactive --awards --ribbons --geoip"

function Invoke-DockerCaptured {
    param([string[]]$DockerArguments)
    $previousErrorActionPreference = $ErrorActionPreference
    $exitCode = 1
    try {
        # Docker Compose reports ordinary progress on stderr; capture it without converting exit-zero output into a terminating error.
        $ErrorActionPreference = "Continue"
        $output = & docker @DockerArguments 2>&1 | Out-String
        if ($null -ne $LASTEXITCODE) {
            $exitCode = $LASTEXITCODE
        }
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return [pscustomobject]@{ output = $output; exit_code = $exitCode }
}

function Get-ContainerHealthDiagnostic {
    param([string]$ContainerName)
    $inspect = Invoke-DockerCaptured -DockerArguments @(
        "inspect", "-f", "{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-health{{end}}", $ContainerName
    )
    $diagnostic = $inspect.output.Trim()
    if ($inspect.exit_code -ne 0) {
        return [pscustomobject]@{ status = "inspect-failed"; diagnostic = $diagnostic }
    }
    return [pscustomobject]@{ status = $diagnostic; diagnostic = $diagnostic }
}

function Wait-PythonFtpHealthy {
    param([string]$ContainerName = "hlstatsx-python-log-ftp")
    $diagnostics = @()
    for ($attempt = 1; $attempt -le 45; $attempt++) {
        $health = Get-ContainerHealthDiagnostic -ContainerName $ContainerName
        $diagnostics += "attempt=$attempt,status=$($health.status),detail=$($health.diagnostic)"
        if ($health.status -eq "healthy") {
            return [pscustomobject]@{ healthy = $true; diagnostics = ($diagnostics -join " | ") }
        }
        if ($attempt -lt 45) {
            Start-Sleep -Seconds 2
        }
    }
    return [pscustomobject]@{ healthy = $false; diagnostics = ($diagnostics -join " | ") }
}

function Invoke-ComposeUp {
    param(
        [string]$ComposePath
    )
    $args = @("compose", "-f", $ComposePath, "up", "-d")
    if (-not $SkipBuild) {
        $args += "--build"
    }
    $composeResult = Invoke-DockerCaptured -DockerArguments $args
    $composeOutput = $composeResult.output
    if ($composeResult.exit_code -eq 0) {
        return
    }

    $isPythonCompose = [System.IO.Path]::GetFullPath($ComposePath) -eq [System.IO.Path]::GetFullPath($pythonCompose)
    $ftpDependencyFailure = $composeOutput -match "hlstatsx-python-log-ftp"
    if ($isPythonCompose -and $ftpDependencyFailure) {
        $ftpHealth = Wait-PythonFtpHealthy
        if ($ftpHealth.healthy) {
            Write-Host "==> Python FTP health recovered; retrying docker compose up once."
            $retryResult = Invoke-DockerCaptured -DockerArguments $args
            $retryOutput = $retryResult.output
            if ($retryResult.exit_code -eq 0) {
                return
            }
            throw "docker compose up retry failed: $ComposePath. Initial diagnostics: $($composeOutput.Trim()). FTP health diagnostics: $($ftpHealth.diagnostics). Retry diagnostics: $($retryOutput.Trim())"
        }
        throw "docker compose up failed while Python FTP dependency remained non-healthy: $ComposePath. Initial diagnostics: $($composeOutput.Trim()). FTP health diagnostics: $($ftpHealth.diagnostics)"
    }
    throw "docker compose up failed: $ComposePath. Diagnostics: $($composeOutput.Trim())"
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

function Invoke-ContainerMysqlCommand {
    param(
        [string]$ContainerName,
        [string]$Sql
    )
    docker exec $ContainerName mysql -uroot -proot123 -D hlstatsxce -e $Sql | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "mysql command failed in $ContainerName"
    }
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

function Get-SelectedReplayLogs {
    param(
        [string]$InputDirectory,
        [int]$ImportLimit
    )
    $isCanonicalReplaySelection = $InputDirectory -eq $artifactsPath -and $ImportLimit -eq $MaxImportFiles
    if ($isCanonicalReplaySelection -and $null -ne $script:SelectedReplayLogs) {
        return $script:SelectedReplayLogs
    }
    $selected = @(Get-ChildItem -LiteralPath $InputDirectory -Filter "*.log" -File | Sort-Object Name | Select-Object -First $ImportLimit)
    if ($selected.Count -eq 0) {
        throw "no *.log files found for replay in $InputDirectory"
    }
    if ($isCanonicalReplaySelection) {
        $script:SelectedReplayLogs = $selected
    }
    return $selected
}

function Get-SelectedLogFingerprint {
    param(
        [string]$InputDirectory,
        [int]$ImportLimit
    )
    $selected = @(Get-SelectedReplayLogs -InputDirectory $InputDirectory -ImportLimit $ImportLimit)
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
        maintenance_classification = $script:EvidenceClassification
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

function Get-SharedSignaturePlayerIds {
    $signaturePlayerSql = @"
SELECT playerId
FROM hlstats_Players
WHERE playerId > 0
  AND game = 'cstrike'
  AND lastName <> ''
  AND (kills > 0 OR deaths > 0)
ORDER BY playerId ASC
LIMIT 2;
"@
    $legacyIds = @((Invoke-ContainerMysqlScalar -ContainerName "hlstatsx-legacy-db" -Sql $signaturePlayerSql) -split '\r?\n' | Where-Object { $_ -match '^[1-9][0-9]*$' })
    $pythonIds = @((Invoke-ContainerMysqlScalar -ContainerName "hlstatsx-python-db" -Sql $signaturePlayerSql) -split '\r?\n' | Where-Object { $_ -match '^[1-9][0-9]*$' })
    if ($legacyIds.Count -ne 2 -or $pythonIds.Count -ne 2) {
        throw "web route smoke requires two populated cstrike signature players in both contours"
    }
    if (($legacyIds | Select-Object -Unique).Count -ne 2 -or ($pythonIds | Select-Object -Unique).Count -ne 2) {
        throw "web route smoke signature player IDs must be distinct in both contours"
    }
    if (($legacyIds -join ',') -ne ($pythonIds -join ',')) {
        throw "web route smoke signature player IDs are not shared by legacy and python contours"
    }
    return $legacyIds
}

function Stage-SelectedFtpLogs {
    $selected = @(Get-SelectedReplayLogs -InputDirectory $artifactsPath -ImportLimit $MaxImportFiles)
    if (-not (Test-Path -LiteralPath $ftpLogStageRoot)) {
        New-Item -ItemType Directory -Path $ftpLogStageRoot | Out-Null
    }
    if (-not (Test-Path -LiteralPath $script:FtpLogStagePath)) {
        New-Item -ItemType Directory -Path $script:FtpLogStagePath | Out-Null
    }

    $selectedByName = @{}
    foreach ($log in $selected) {
        $selectedByName[$log.Name] = $log
    }
    $stagedItems = @(Get-ChildItem -LiteralPath $script:FtpLogStagePath)
    foreach ($stagedItem in $stagedItems) {
        if ($stagedItem.PSIsContainer -or -not $selectedByName.ContainsKey($stagedItem.Name)) {
            throw "FTP log stage contains an unexpected item; preserve it for diagnostics and use a new EvidenceRunId: $($stagedItem.FullName)"
        }
        $source = $selectedByName[$stagedItem.Name]
        if ($stagedItem.Length -ne $source.Length -or (Get-FileHash -LiteralPath $stagedItem.FullName -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256).Hash) {
            throw "FTP log stage differs from the selected replay log; preserve it for diagnostics and use a new EvidenceRunId: $($stagedItem.FullName)"
        }
    }
    foreach ($log in $selected) {
        $stagedPath = Join-Path $script:FtpLogStagePath $log.Name
        if (-not (Test-Path -LiteralPath $stagedPath)) {
            Copy-Item -LiteralPath $log.FullName -Destination $stagedPath
        }
    }
    $finalFiles = @(Get-ChildItem -LiteralPath $script:FtpLogStagePath -File)
    if ($finalFiles.Count -ne $selected.Count) {
        throw "FTP log stage does not contain exactly the selected replay logs: $script:FtpLogStagePath"
    }
    foreach ($log in $selected) {
        if (-not (Test-Path -LiteralPath (Join-Path $script:FtpLogStagePath $log.Name))) {
            throw "FTP log stage is missing selected replay log: $($log.Name)"
        }
    }
    return $script:FtpLogStagePath
}

function Get-MaintenanceCounts {
    param([string]$ContainerName)
    return [ordered]@{
        awards = [int](Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COUNT(*) FROM hlstats_Awards;")
        player_awards = [int](Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COUNT(*) FROM hlstats_Players_Awards;")
        player_ribbons = [int](Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COUNT(*) FROM hlstats_Players_Ribbons;")
        geoip_flag = [int](Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COUNT(*) FROM hlstats_Players WHERE lastAddress <> '' AND flag <> '';")
        geoip_country = [int](Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COUNT(*) FROM hlstats_Players WHERE lastAddress <> '' AND country <> '';")
        geoip_city = [int](Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COUNT(*) FROM hlstats_Players WHERE lastAddress <> '' AND city <> '';")
        geoip_state = [int](Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COUNT(*) FROM hlstats_Players WHERE lastAddress <> '' AND state <> '';")
        geoip_coordinates = [int](Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COUNT(*) FROM hlstats_Players WHERE lastAddress <> '' AND lat IS NOT NULL AND lng IS NOT NULL;")
    }
}

function Get-ContourReplayMaxDate {
    param([string]$ContainerName)
    $value = Invoke-ContainerMysqlScalar -ContainerName $ContainerName -Sql "SELECT COALESCE(DATE(MAX(eventTime)), '') FROM hlstats_Events_Frags;"
    if (-not $value) {
        throw "cannot resolve maintenance date: no fragment eventTime in $ContainerName"
    }
    try {
        return [DateTime]::ParseExact($value, "yyyy-MM-dd", [System.Globalization.CultureInfo]::InvariantCulture)
    } catch {
        throw "cannot resolve maintenance date: invalid fragment date '$value' in $ContainerName"
    }
}

function Set-HistoricalMaintenanceTimestamp {
    param([string]$ContainerName)
    Invoke-ContainerMysqlCommand `
        -ContainerName $ContainerName `
        -Sql "UPDATE hlstats_Options SET value='1' WHERE keyname='UseTimestamp';"
    $readback = Invoke-ContainerMysqlScalar `
        -ContainerName $ContainerName `
        -Sql "SELECT value FROM hlstats_Options WHERE keyname='UseTimestamp';"
    if ($readback -ne "1") {
        throw "UseTimestamp override verification failed in ${ContainerName}: expected 1, got '$readback'"
    }
    return $readback
}

function Resolve-MaintenanceInputs {
    if ($MaintenanceDate) {
        try {
            $parsed = [DateTime]::ParseExact($MaintenanceDate, "yyyy-MM-dd", [System.Globalization.CultureInfo]::InvariantCulture)
            return [ordered]@{ date = $parsed.ToString("yyyy-MM-dd"); numdays = $MaintenanceNumDays; source = "explicit" }
        } catch {
            throw "MaintenanceDate must use YYYY-MM-DD, got '$MaintenanceDate'"
        }
    }
    if ($script:RunState.maintenance -and $script:RunState.maintenance.resolved_date) {
        return [ordered]@{ date = [string]$script:RunState.maintenance.resolved_date; numdays = $MaintenanceNumDays; source = "resumed" }
    }
    $legacyMax = $null
    $pythonMax = $null
    if ($Stack -eq "both" -or $Stack -eq "legacy") { $legacyMax = Get-ContourReplayMaxDate -ContainerName "hlstatsx-legacy-db" }
    if ($Stack -eq "both" -or $Stack -eq "python") { $pythonMax = Get-ContourReplayMaxDate -ContainerName "hlstatsx-python-db" }
    if ($Stack -eq "both" -and $legacyMax -ne $pythonMax) {
        throw "maintenance date verification failed: legacy fragment maximum $($legacyMax.ToString('yyyy-MM-dd')) differs from Python $($pythonMax.ToString('yyyy-MM-dd'))"
    }
    $replayMax = if ($legacyMax) { $legacyMax } else { $pythonMax }
    return [ordered]@{ date = $replayMax.AddDays(1).ToString("yyyy-MM-dd"); numdays = $MaintenanceNumDays; source = "replay-window-max-plus-one" }
}

function ConvertTo-RedactedMaintenanceCommand {
    param([string[]]$Command)
    $redacted = @()
    for ($index = 0; $index -lt $Command.Count; $index++) {
        $argument = $Command[$index]
        if ($argument -eq "--db-password") {
            $redacted += $argument
            if ($index + 1 -lt $Command.Count) {
                $redacted += "***REDACTED***"
                $index++
            }
            continue
        }
        if ($argument -match "^--db-password=") {
            $redacted += "--db-password=***REDACTED***"
            continue
        }
        $redacted += $argument
    }
    return $redacted
}

function Invoke-MaintenanceCommand {
    param([string]$StackName, [string]$LogPath, [string[]]$Command)
    $displayCommand = @(ConvertTo-RedactedMaintenanceCommand -Command $Command)
    Write-Host "==> $StackName maintenance: $($displayCommand -join ' ')"
    docker @Command 2>&1 | Tee-Object -FilePath $LogPath | Out-Host
    $exitCode = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $LogPath)) {
        New-Item -ItemType File -Path $LogPath -Force | Out-Null
    }
    return [pscustomobject]@{ stack = $StackName; status = if ($exitCode -eq 0) { "passed" } else { "failed" }; exit_code = $exitCode; log_path = $LogPath; counts = [ordered]@{} }
}

function Invoke-PythonCaptured {
    param([string[]]$Command, [string]$LogPath)
    $previousErrorActionPreference = $ErrorActionPreference
    $exitCode = 1
    $output = ""
    try {
        # Preserve the native exit code and its complete output even when this runner uses Stop globally.
        $ErrorActionPreference = "Continue"
        $output = python @Command 2>&1 | Out-String
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($output.Length -gt 0) {
        Set-Content -Path $LogPath -Value $output -NoNewline
        Write-Host $output -NoNewline
    } elseif (-not (Test-Path -LiteralPath $LogPath)) {
        New-Item -ItemType File -Path $LogPath -Force | Out-Null
    }
    return $exitCode
}

function Invoke-WebRouteSmoke {
    param(
        [string]$StackName,
        [string]$BaseUrl,
        [string]$LogPath,
        [string[]]$Languages,
        [string[]]$SignaturePlayerIds
    )
    if ($Languages.Count -ne $SignaturePlayerIds.Count) {
        throw "web route smoke requires one signature player ID for each requested language"
    }
    Write-Host "==> $StackName web route smoke: $BaseUrl"
    $command = @("scripts/replay_baseline/web_route_smoke.py", "--base-url", $BaseUrl, "--langs") + $Languages
    foreach ($playerId in $SignaturePlayerIds) {
        $command += @("--sig-player-id", $playerId)
    }
    $exitCode = Invoke-PythonCaptured -Command $command -LogPath $LogPath
    return [pscustomobject]@{ stack = $StackName; status = if ($exitCode -eq 0) { "passed" } else { "failed" }; exit_code = $exitCode; evidence_path = $LogPath }
}

function Get-MaintenanceCountSummaryLines {
    param([object]$Counts)
    if ($Counts -is [System.Collections.IDictionary]) {
        foreach ($entry in $Counts.GetEnumerator()) { "$($entry.Key)=$($entry.Value)" }
        return
    }
    foreach ($property in $Counts.PSObject.Properties) { "$($property.Name)=$($property.Value)" }
}

function Set-MaintenanceSummaryPath {
    param([object]$State, [string]$SummaryPath)
    $maintenance = $State.maintenance
    if ($maintenance -is [System.Collections.IDictionary]) {
        $maintenance["summary_path"] = $SummaryPath
    } else {
        $maintenance.summary_path = $SummaryPath
    }
}

function Write-MaintenanceSummary {
    param([object]$State)
    $summaryPath = Join-Path $auditDir "maintenance-summary-$script:EvidenceLabel.txt"
    $maintenance = $State.maintenance
    $compare = $State.logical_compare
    $webSmoke = $State.web_smoke
    $lines = @(
        "evidence_label=$script:EvidenceLabel",
        "evidence_classification=$script:EvidenceClassification",
        "maintenance_status=$($maintenance.status)",
        "maintenance_date=$($maintenance.resolved_date)",
        "maintenance_numdays=$($maintenance.numdays)",
        "maintenance_date_source=$($maintenance.date_source)",
        "legacy_maintenance_actions=$($maintenance.legacy_actions)",
        "python_maintenance_actions=$($maintenance.python_actions)",
        "inactive_time_mode=$($maintenance.inactive_time_mode)",
        "legacy_use_timestamp=$($maintenance.legacy_use_timestamp)",
        "python_use_timestamp=$($maintenance.python_use_timestamp)",
        "legacy_maintenance_status=$($maintenance.legacy.status)",
        "legacy_maintenance_exit_code=$($maintenance.legacy.exit_code)",
        "python_maintenance_status=$($maintenance.python.status)",
        "python_maintenance_exit_code=$($maintenance.python.exit_code)",
        "logical_compare=$($compare.status)",
        "logical_compare_evidence=$($compare.evidence_path)",
        "web_smoke=$($webSmoke.status)",
        "web_smoke_signature_player_ids=$($webSmoke.signature_player_ids -join ',')",
        "legacy_web_smoke_languages=$($webSmoke.legacy_languages -join ',')",
        "legacy_web_smoke_signature_player_ids=$($webSmoke.legacy_signature_player_ids -join ',')",
        "legacy_web_smoke_status=$($webSmoke.legacy.status)",
        "legacy_web_smoke_evidence=$($webSmoke.legacy.evidence_path)",
        "python_web_smoke_languages=$($webSmoke.python_languages -join ',')",
        "python_web_smoke_signature_player_ids=$($webSmoke.python_signature_player_ids -join ',')",
        "python_web_smoke_status=$($webSmoke.python.status)",
        "python_web_smoke_evidence=$($webSmoke.python.evidence_path)",
        "",
        "[legacy_counts]"
    )
    $lines += Get-MaintenanceCountSummaryLines -Counts $maintenance.legacy.counts
    $lines += ""
    $lines += "[python_counts]"
    $lines += Get-MaintenanceCountSummaryLines -Counts $maintenance.python.counts
    $lines += ""
    $lines += "[visual_inspection]"
    $lines += "legacy_players=http://127.0.0.1:8181/hlstats.php?mode=players"
    $lines += "legacy_daily_awards=http://127.0.0.1:8181/hlstats.php?mode=awards&game=cstrike&tab=daily&lang=en"
    $lines += "legacy_global_awards=http://127.0.0.1:8181/hlstats.php?mode=awards&game=cstrike&tab=global&lang=en"
    $lines += "legacy_ribbons=http://127.0.0.1:8181/hlstats.php?mode=awards&game=cstrike&tab=ribbons&lang=en"
    $lines += "python_players=http://127.0.0.1:8281/hlstats.php?mode=players"
    $lines += "python_daily_awards=http://127.0.0.1:8281/hlstats.php?mode=awards&game=cstrike&tab=daily&lang=en"
    $lines += "python_global_awards=http://127.0.0.1:8281/hlstats.php?mode=awards&game=cstrike&tab=global&lang=en"
    $lines += "python_ribbons=http://127.0.0.1:8281/hlstats.php?mode=awards&game=cstrike&tab=ribbons&lang=en"
    $lines += "python_daily_awards_ru=http://127.0.0.1:8281/hlstats.php?mode=awards&game=cstrike&tab=daily&lang=ru"
    $lines += "python_global_awards_ru=http://127.0.0.1:8281/hlstats.php?mode=awards&game=cstrike&tab=global&lang=ru"
    $lines += "python_ribbons_ru=http://127.0.0.1:8281/hlstats.php?mode=awards&game=cstrike&tab=ribbons&lang=ru"
    $lines -join "`r`n" | Set-Content -LiteralPath $summaryPath -Encoding UTF8
    return $summaryPath
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
    $selected = @(Get-SelectedReplayLogs -InputDirectory $InputDirectory -ImportLimit $ImportLimit)
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
    $pythonReplayVolume = "hlstatsx-python-replay-" + ([guid]::NewGuid().ToString("N"))
    $pythonReplayVolumeCreated = $false

    if ($UsePythonUdpReplay) {
        $cmd = @(
            "run", "--rm",
            "--network", "python_hlstatsx_python_net",
            "-v", "${repoRoot}\scripts:/app/scripts",
            "--mount", "type=volume,source=$pythonReplayVolume,target=/tmp/ftp_work",
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
            "--mount", "type=volume,source=$pythonReplayVolume,target=/tmp/ftp_work",
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
    try {
        $existingDockerVolumes = @(docker volume ls --format '{{.Name}}')
        if ($LASTEXITCODE -ne 0) { throw "failed to list docker volumes" }
        if ($existingDockerVolumes -contains $pythonReplayVolume) {
            throw "python replay volume collision: $pythonReplayVolume"
        }
        docker volume create $pythonReplayVolume | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "failed to create python replay volume" }
        $pythonReplayVolumeCreated = $true

        docker @cmd | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "python ftp import failed"
        }
        docker run --rm `
            --mount "type=volume,source=$pythonReplayVolume,target=/from,readonly" `
            -v "${pythonFtpWork}:/to" `
            --entrypoint sh `
            python-hlstats-worker -lc "cp /from/$pythonInputManifestName /to/$pythonInputManifestName && cp /from/$pythonIgnoredManifestName /to/$pythonIgnoredManifestName"
        if ($LASTEXITCODE -ne 0) { throw "failed to copy python replay manifests" }
        Publish-EvidenceFile `
            -SourcePath $pythonInputManifestTemp `
            -DestinationPath (Join-Path $auditDir $pythonInputManifestName)
        Publish-EvidenceFile `
            -SourcePath $pythonIgnoredManifestTemp `
            -DestinationPath (Join-Path $auditDir $pythonIgnoredManifestName)
    } finally {
        if ($pythonReplayVolumeCreated) {
            docker volume rm $pythonReplayVolume | Out-Null
        }
    }
}

$allStages = @("infra_updown", "baseline_restore", "preflight", "legacy_import", "python_import", "maintenance", "sql_snapshot", "logical_compare", "web_smoke")
$stageDependencies = @{
    "legacy_import" = @("baseline_restore", "preflight")
    "python_import" = @("baseline_restore", "preflight")
    "maintenance" = @("baseline_restore", "preflight")
    "sql_snapshot"  = @("baseline_restore", "preflight", "maintenance")
    "logical_compare" = @("sql_snapshot")
    "web_smoke" = @("logical_compare")
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
        skip_maintenance = [bool]$SkipMaintenance
        maintenance_date = $MaintenanceDate
        maintenance_numdays = $MaintenanceNumDays
        maintenance_legacy_actions = $script:LegacyMaintenanceActions
        maintenance_python_actions = $script:PythonMaintenanceActions
        maintenance_inactive_time_mode = "per-game-server-last_event"
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
        if ($propNames -notcontains "evidence_classification") {
            $state | Add-Member -NotePropertyName "evidence_classification" -NotePropertyValue $script:EvidenceClassification
        }
        if ($propNames -notcontains "maintenance") {
            $state | Add-Member -NotePropertyName "maintenance" -NotePropertyValue $null
        }
        if ($propNames -notcontains "logical_compare") {
            $state | Add-Member -NotePropertyName "logical_compare" -NotePropertyValue ([ordered]@{ status = "pending"; evidence_path = "" })
        }
        if ($propNames -notcontains "web_smoke") {
            $state | Add-Member -NotePropertyName "web_smoke" -NotePropertyValue ([ordered]@{
                status = "pending"
                signature_player_ids = @()
                legacy = [ordered]@{ status = "pending"; exit_code = ""; evidence_path = "" }
                python = [ordered]@{ status = "pending"; exit_code = ""; evidence_path = "" }
            })
        } elseif (@($state.web_smoke.PSObject.Properties.Name) -notcontains "signature_player_ids") {
            $state.web_smoke | Add-Member -NotePropertyName "signature_player_ids" -NotePropertyValue @()
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
        evidence_classification = $script:EvidenceClassification
        maintenance = $null
        logical_compare = [ordered]@{ status = "pending"; evidence_path = "" }
        web_smoke = [ordered]@{
            status = "pending"
            signature_player_ids = @()
            legacy = [ordered]@{ status = "pending"; exit_code = ""; evidence_path = "" }
            python = [ordered]@{ status = "pending"; exit_code = ""; evidence_path = "" }
        }
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
    if ($Stage -eq "maintenance") {
        if (($Stack -eq "both" -or $Stack -eq "legacy") -and $completed -notcontains "legacy_import") {
            throw "Stage 'maintenance' requires completed stage 'legacy_import'."
        }
        if (($Stack -eq "both" -or $Stack -eq "python") -and $completed -notcontains "python_import") {
            throw "Stage 'maintenance' requires completed stage 'python_import'."
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
            Stage-SelectedFtpLogs | Out-Null
            $env:HLSTATS_FTP_LOGS_HOST_PATH = $script:FtpLogStagePath
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
        "maintenance" {
            $summaryPath = Join-Path $auditDir "maintenance-summary-$script:EvidenceLabel.txt"
            $legacyLogPath = Join-Path $auditDir "legacy-maintenance-$script:EvidenceLabel.log"
            $pythonLogPath = Join-Path $auditDir "python-maintenance-$script:EvidenceLabel.log"
            Assert-EvidencePathsAvailable @($summaryPath, $legacyLogPath, $pythonLogPath)
            if ($SkipMaintenance) {
                Write-Host "==> Maintenance skipped via -SkipMaintenance; evidence is raw-only."
                $script:RunState.maintenance = [ordered]@{
                    status = "skipped"
                    resolved_date = ""
                    numdays = $MaintenanceNumDays
                    date_source = "skipped"
                    legacy_actions = $script:LegacyMaintenanceActions
                    python_actions = $script:PythonMaintenanceActions
                    inactive_time_mode = "skipped"
                    legacy_use_timestamp = ""
                    python_use_timestamp = ""
                    summary_path = ""
                    legacy = [ordered]@{ status = "skipped"; exit_code = ""; log_path = ""; counts = [ordered]@{} }
                    python = [ordered]@{ status = "skipped"; exit_code = ""; log_path = ""; counts = [ordered]@{} }
                }
                Save-RunState -State $script:RunState -Path $script:StateFile
                return
            }

            $inputs = [ordered]@{ date = ""; numdays = $MaintenanceNumDays; source = "unresolved" }
            $legacyRecord = [pscustomobject]@{ status = "not_applicable"; exit_code = ""; log_path = ""; counts = [ordered]@{} }
            $pythonRecord = [pscustomobject]@{ status = "not_applicable"; exit_code = ""; log_path = ""; counts = [ordered]@{} }
            $legacyUseTimestamp = ""
            $pythonUseTimestamp = ""
            try {
                $inputs = Resolve-MaintenanceInputs
                # Historical replay evidence must retain its complete corpus; default maintenance never prunes it.
                # Use per-game server last_event for inactivity instead of the host clock for historical replay data.
                if ($Stack -eq "both" -or $Stack -eq "legacy") {
                    $legacyUseTimestamp = Set-HistoricalMaintenanceTimestamp -ContainerName "hlstatsx-legacy-db"
                }
                if ($Stack -eq "both" -or $Stack -eq "python") {
                    $pythonUseTimestamp = Set-HistoricalMaintenanceTimestamp -ContainerName "hlstatsx-python-db"
                }
                if ($Stack -eq "both" -or $Stack -eq "legacy") {
                    # The legacy image's /scripts/hlstats.conf deliberately has blank DB fields;
                    # daemon CLI options are not inherited by this separate Perl process.
                    $legacyCommand = @(
                        "exec", "--workdir", "/scripts", "hlstatsx-legacy-daemon",
                        "perl", "./hlstats-awards.pl",
                        "--db-host", "db:3306",
                        "--db-name", "hlstatsxce",
                        "--db-username", "hlstatsxce",
                        "--db-password", "hlx123",
                        "-i", "-a", "-r", "-g",
                        "--numdays", "$($inputs.numdays)",
                        "--date", "$($inputs.date)"
                    )
                    $legacyRecord = Invoke-MaintenanceCommand -StackName "legacy" -LogPath $legacyLogPath -Command $legacyCommand
                    if ($legacyRecord.exit_code -ne 0) { throw "legacy maintenance failed" }
                    $legacyRecord.counts = Get-MaintenanceCounts -ContainerName "hlstatsx-legacy-db"
                }
                if ($Stack -eq "both" -or $Stack -eq "python") {
                    $pythonCommand = @("exec", "hlstatsx-python-worker", "python", "-m", "hlstats_awards_py", "--configfile", "/app/hlstats.conf", "--inactive", "--awards", "--ribbons", "--geoip", "--numdays", "$($inputs.numdays)", "--date", "$($inputs.date)")
                    $pythonRecord = Invoke-MaintenanceCommand -StackName "python" -LogPath $pythonLogPath -Command $pythonCommand
                    if ($pythonRecord.exit_code -ne 0) { throw "python maintenance failed" }
                    $pythonRecord.counts = Get-MaintenanceCounts -ContainerName "hlstatsx-python-db"
                }
                $script:RunState.maintenance = [ordered]@{
                    status = "passed"
                    resolved_date = $inputs.date
                    numdays = $inputs.numdays
                    date_source = $inputs.source
                    legacy_actions = $script:LegacyMaintenanceActions
                    python_actions = $script:PythonMaintenanceActions
                    inactive_time_mode = "per-game-server-last_event (UseTimestamp=1)"
                    legacy_use_timestamp = $legacyUseTimestamp
                    python_use_timestamp = $pythonUseTimestamp
                    summary_path = ""
                    legacy = $legacyRecord
                    python = $pythonRecord
                }
            } catch {
                $script:RunState.maintenance = [ordered]@{
                    status = "failed"
                    resolved_date = $inputs.date
                    numdays = $inputs.numdays
                    date_source = $inputs.source
                    legacy_actions = $script:LegacyMaintenanceActions
                    python_actions = $script:PythonMaintenanceActions
                    inactive_time_mode = "override_pending_or_failed"
                    legacy_use_timestamp = $legacyUseTimestamp
                    python_use_timestamp = $pythonUseTimestamp
                    summary_path = ""
                    legacy = $legacyRecord
                    python = $pythonRecord
                }
                Save-RunState -State $script:RunState -Path $script:StateFile
                $summaryPath = Write-MaintenanceSummary -State $script:RunState
                Set-MaintenanceSummaryPath -State $script:RunState -SummaryPath $summaryPath
                Save-RunState -State $script:RunState -Path $script:StateFile
                throw
            }
            Save-RunState -State $script:RunState -Path $script:StateFile
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
        "logical_compare" {
            $comparePath = Join-Path $auditDir "logical-compare-$script:EvidenceLabel.txt"
            Assert-EvidencePathsAvailable @($comparePath)
            if ($Stack -ne "both") {
                $script:RunState.logical_compare = [ordered]@{ status = "not_applicable"; evidence_path = "" }
                Save-RunState -State $script:RunState -Path $script:StateFile
                return
            }
            Write-Host "==> Logical DB compare"
            $compareExit = Invoke-PythonCaptured -Command @("scripts/replay_baseline/compare_stats_dbs.py", "--max-examples", "20") -LogPath $comparePath
            $script:RunState.logical_compare = [ordered]@{
                status = if ($compareExit -eq 0) { "passed" } else { "failed" }
                exit_code = $compareExit
                evidence_path = $comparePath
            }
            Save-RunState -State $script:RunState -Path $script:StateFile
            $summaryPath = Write-MaintenanceSummary -State $script:RunState
            Set-MaintenanceSummaryPath -State $script:RunState -SummaryPath $summaryPath
            Save-RunState -State $script:RunState -Path $script:StateFile
            if ($compareExit -ne 0) {
                throw "logical DB compare failed; evidence: $comparePath"
            }
        }
        "web_smoke" {
            $legacyLogPath = Join-Path $auditDir "legacy-web-smoke-$script:EvidenceLabel.log"
            $pythonLogPath = Join-Path $auditDir "python-web-smoke-$script:EvidenceLabel.log"
            $evidencePaths = @()
            if ($Stack -eq "both" -or $Stack -eq "legacy") { $evidencePaths += $legacyLogPath }
            if ($Stack -eq "both" -or $Stack -eq "python") { $evidencePaths += $pythonLogPath }
            Assert-EvidencePathsAvailable $evidencePaths
            $signaturePlayerIds = @(Get-SharedSignaturePlayerIds)
            $legacyLanguages = @("en")
            $pythonLanguages = @("en", "ru")
            $legacySignaturePlayerIds = @($signaturePlayerIds[0])
            $pythonSignaturePlayerIds = @($signaturePlayerIds)
            $legacyRecord = [pscustomobject]@{ status = "not_applicable"; exit_code = ""; evidence_path = "" }
            $pythonRecord = [pscustomobject]@{ status = "not_applicable"; exit_code = ""; evidence_path = "" }
            if ($Stack -eq "both" -or $Stack -eq "legacy") {
                $legacyRecord = Invoke-WebRouteSmoke -StackName "legacy" -BaseUrl "http://127.0.0.1:8181" -LogPath $legacyLogPath -Languages $legacyLanguages -SignaturePlayerIds $legacySignaturePlayerIds
            }
            if ($Stack -eq "both" -or $Stack -eq "python") {
                $pythonRecord = Invoke-WebRouteSmoke -StackName "python" -BaseUrl "http://127.0.0.1:8281" -LogPath $pythonLogPath -Languages $pythonLanguages -SignaturePlayerIds $pythonSignaturePlayerIds
            }
            $smokeFailed = $legacyRecord.status -eq "failed" -or $pythonRecord.status -eq "failed"
            $script:RunState.web_smoke = [ordered]@{
                status = if ($smokeFailed) { "failed" } else { "passed" }
                signature_player_ids = @($signaturePlayerIds)
                legacy_languages = $legacyLanguages
                legacy_signature_player_ids = $legacySignaturePlayerIds
                legacy = $legacyRecord
                python_languages = $pythonLanguages
                python_signature_player_ids = $pythonSignaturePlayerIds
                python = $pythonRecord
            }
            Save-RunState -State $script:RunState -Path $script:StateFile
            $summaryPath = Write-MaintenanceSummary -State $script:RunState
            Set-MaintenanceSummaryPath -State $script:RunState -SummaryPath $summaryPath
            Save-RunState -State $script:RunState -Path $script:StateFile
            if ($smokeFailed) {
                throw "web route smoke failed; inspect evidence in $auditDir"
            }
        }
        default {
            throw "Unknown stage: $StageName"
        }
    }
}

Validate-StageParamCombination
if ($ReuseValidLegacy -and -not $SkipMaintenance -and ($Stack -eq "both" -or $Stack -eq "legacy")) {
    throw "ReuseValidLegacy cannot be combined with maintenance-enabled replay: reused legacy import anchors are not a post-maintenance receipt. Use -SkipMaintenance for raw-only reuse or run a full legacy import."
}
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
$script:RunState = $runState
$script:StateFile = $stateFile
if (-not $runState.config_fingerprint) {
    $runState.config_fingerprint = $fingerprint
}

if ((Test-Path $stateFile) -and $runState.config_fingerprint -ne $fingerprint) {
    throw "State fingerprint mismatch for run '$($runState.run_id)'. Provide new StatePath/RunId or align parameters."
}

foreach ($stageName in $targetStages) {
    if ($stageName -eq "legacy_import" -or $stageName -eq "python_import" -or $stageName -eq "maintenance" -or $stageName -eq "sql_snapshot" -or $stageName -eq "logical_compare" -or $stageName -eq "web_smoke") {
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
