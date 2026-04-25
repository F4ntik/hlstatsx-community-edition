param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("legacy", "python")]
    [string]$Stack,

    [string]$BaselineDump = "",
    [ValidateSet("snapshot", "dump")]
    [string]$RestoreMode = "snapshot",
    [string]$SnapshotName = "",
    [switch]$CreateSnapshot,
    [switch]$ForceDumpRestore,
    [switch]$DisableDumpFallback
)

$ErrorActionPreference = "Stop"

$DatabaseName = "hlstatsxce"
$BaselineServerAddress = "172.19.0.1"
$BaselineServerPort = 27015
$ReplayServerAddress = "37.230.137.48"
$ReplayServerPort = 27015
$ReplayServerGame = "cstrike"
$ReplayServerName = "Replay Server 37.230.137.48"
$ReplayServerPublicAddress = "${ReplayServerAddress}:${ReplayServerPort}"
$ComparisonSqlMode = "NO_ENGINE_SUBSTITUTION"

if (-not $PSScriptRoot) {
    $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

if (-not $BaselineDump) {
    $BaselineDump = Join-Path $PSScriptRoot "artifacts\baseline_reset_20260418.sql.gz"
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$composePath = Join-Path $PSScriptRoot "comparison\$Stack\docker-compose.yml"
$artifactsRoot = Join-Path $PSScriptRoot "artifacts"
$snapshotRoot = Join-Path $artifactsRoot "snapshots\$Stack"

$stackInfo = switch ($Stack) {
    "legacy" {
        @{
            DbContainer = "hlstatsx-legacy-db"
            DbVolume = "hlstatsx_legacy_db"
            ComposeProject = "legacy"
        }
    }
    "python" {
        @{
            DbContainer = "hlstatsx-python-db"
            DbVolume = "hlstatsx_python_db"
            ComposeProject = "python"
        }
    }
}
$dbContainer = $stackInfo.DbContainer
$dbVolume = $stackInfo.DbVolume

if (-not (Test-Path $BaselineDump)) {
    throw "Baseline dump not found: $BaselineDump"
}

if (-not (Test-Path $snapshotRoot)) {
    New-Item -ItemType Directory -Path $snapshotRoot | Out-Null
}

function Get-BaselineStem {
    param([string]$Path)
    $name = [System.IO.Path]::GetFileName($Path)
    if ($name.EndsWith(".sql.gz", [System.StringComparison]::OrdinalIgnoreCase)) {
        return $name.Substring(0, $name.Length - 7)
    }
    return [System.IO.Path]::GetFileNameWithoutExtension($name)
}

if (-not $SnapshotName) {
    $SnapshotName = "$Stack-$(Get-BaselineStem -Path $BaselineDump)-with-bootstrap"
}
$snapshotArchive = Join-Path $snapshotRoot "$SnapshotName.tar.gz"

function Invoke-ContainerMysql {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Sql,

        [switch]$SkipColumnNames
    )

    $command = @(
        "exec",
        $dbContainer,
        "mysql",
        "-uroot",
        "-proot123",
        "-D",
        $DatabaseName
    )

    if ($SkipColumnNames) {
        $command += "--batch"
        $command += "--raw"
        $command += "--skip-column-names"
    }

    $command += "-e"
    $command += $Sql

    $output = docker @command
    if ($LASTEXITCODE -ne 0) {
        throw "MySQL command failed in $dbContainer"
    }
    return $output
}

function Invoke-DbServiceUp {
    docker compose -f $composePath up -d db | Out-Null
}

function Wait-DbReady {
    docker exec $dbContainer sh -lc "until mysqladmin ping -h 127.0.0.1 -uroot -proot123 --silent; do sleep 1; done" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "MySQL in $dbContainer did not become ready"
    }
}

function Set-ComparisonSqlMode {
    docker exec $dbContainer mysql -uroot -proot123 -e "SET GLOBAL sql_mode='$ComparisonSqlMode';" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to set sql_mode in $dbContainer"
    }
}

function Stop-DbService {
    docker compose -f $composePath stop db | Out-Null
}

function Clear-DbVolume {
    docker run --rm -v "${dbVolume}:/volume" alpine sh -lc "rm -rf /volume/* /volume/.[!.]* /volume/..?*"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to clear Docker volume $dbVolume"
    }
}

function Restore-DbVolumeFromSnapshot {
    param([string]$ArchivePath)
    if (-not (Test-Path $ArchivePath)) {
        throw "Snapshot archive not found: $ArchivePath"
    }
    $snapshotDir = Split-Path -Parent $ArchivePath
    $snapshotFile = Split-Path -Leaf $ArchivePath
    Clear-DbVolume
    docker run --rm `
        -v "${dbVolume}:/volume" `
        -v "${snapshotDir}:/snapshots:ro" `
        alpine sh -lc "tar -C /volume -xzf /snapshots/$snapshotFile"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to restore snapshot archive $snapshotFile into $dbVolume"
    }
}

function Save-DbVolumeSnapshot {
    param([string]$ArchivePath)
    $snapshotDir = Split-Path -Parent $ArchivePath
    $snapshotFile = Split-Path -Leaf $ArchivePath
    if (-not (Test-Path $snapshotDir)) {
        New-Item -ItemType Directory -Path $snapshotDir | Out-Null
    }
    docker run --rm `
        -v "${dbVolume}:/volume:ro" `
        -v "${snapshotDir}:/snapshots" `
        alpine sh -lc "tar -C /volume -czf /snapshots/$snapshotFile ."
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to save snapshot archive $snapshotFile from $dbVolume"
    }
}

function Invoke-PythonProxyBootstrap {
    $proxySchemaPath = Join-Path $repoRoot "scripts\proxy_daemon_py\fullstack\mysql\01_create_proxy_daemons.sql"
    docker exec $dbContainer sh -lc "rm -f /tmp/01_create_proxy_daemons.sql"
    docker cp $proxySchemaPath "${dbContainer}:/tmp/01_create_proxy_daemons.sql"
    docker exec $dbContainer sh -lc "mysql -uroot -proot123 $DatabaseName < /tmp/01_create_proxy_daemons.sql"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create Proxy_Daemons table in $dbContainer"
    }

    Invoke-ContainerMysql -Sql "UPDATE hlstats_Options SET value='hlstatsx-python-worker:28000' WHERE keyname='Proxy_Daemons';" | Out-Null
}

function Invoke-ReplayServerBootstrap {
    $baselineServerId = (Invoke-ContainerMysql -SkipColumnNames -Sql @"
SELECT serverId
FROM hlstats_Servers
WHERE address = '$BaselineServerAddress' AND port = $BaselineServerPort
LIMIT 1;
"@).Trim()

    if (-not $baselineServerId) {
        throw "Baseline server ${BaselineServerAddress}:${BaselineServerPort} was not found in hlstats_Servers"
    }

    Invoke-ContainerMysql -Sql @"
DELETE cfg
FROM hlstats_Servers_Config AS cfg
INNER JOIN hlstats_Servers AS srv ON srv.serverId = cfg.serverId
WHERE srv.address = '$ReplayServerAddress' AND srv.port = $ReplayServerPort;

DELETE FROM hlstats_Servers
WHERE address = '$ReplayServerAddress' AND port = $ReplayServerPort;

INSERT INTO hlstats_Servers (
  address,
  port,
  name,
  game,
  publicaddress,
  act_players,
  max_players,
  act_map
)
SELECT
  '$ReplayServerAddress',
  $ReplayServerPort,
  '$ReplayServerName',
  '$ReplayServerGame',
  '$ReplayServerPublicAddress',
  act_players,
  max_players,
  act_map
FROM hlstats_Servers
WHERE serverId = $baselineServerId
LIMIT 1;
"@ | Out-Null

    $replayServerId = (Invoke-ContainerMysql -SkipColumnNames -Sql @"
SELECT serverId
FROM hlstats_Servers
WHERE address = '$ReplayServerAddress' AND port = $ReplayServerPort
LIMIT 1;
"@).Trim()

    if (-not $replayServerId) {
        throw "Replay server ${ReplayServerAddress}:${ReplayServerPort} was not created in hlstats_Servers"
    }

    Invoke-ContainerMysql -Sql @"
DELETE FROM hlstats_Servers_Config
WHERE serverId = $replayServerId;

INSERT INTO hlstats_Servers_Config (serverId, parameter, value)
SELECT $replayServerId, parameter, value
FROM hlstats_Servers_Config
WHERE serverId = $baselineServerId;
"@ | Out-Null

    $replayServerCount = (Invoke-ContainerMysql -SkipColumnNames -Sql @"
SELECT COUNT(*)
FROM hlstats_Servers
WHERE address = '$ReplayServerAddress' AND port = $ReplayServerPort;
"@).Trim()
    if ($replayServerCount -ne "1") {
        throw "Expected exactly one replay server row for ${ReplayServerAddress}:${ReplayServerPort}, got $replayServerCount"
    }

    $replayConfigCount = (Invoke-ContainerMysql -SkipColumnNames -Sql @"
SELECT COUNT(*)
FROM hlstats_Servers_Config
WHERE serverId = $replayServerId;
"@).Trim()
    if ([int]$replayConfigCount -le 0) {
        throw "Replay server ${ReplayServerAddress}:${ReplayServerPort} has no copied hlstats_Servers_Config rows"
    }
}

function Invoke-StateChecks {
    $baselineServerCount = (Invoke-ContainerMysql -SkipColumnNames -Sql @"
SELECT COUNT(*)
FROM hlstats_Servers
WHERE address = '$BaselineServerAddress' AND port = $BaselineServerPort;
"@).Trim()
    if ($baselineServerCount -ne "1") {
        throw "Expected baseline server ${BaselineServerAddress}:${BaselineServerPort} in $dbContainer, got $baselineServerCount"
    }
    $replayServerCount = (Invoke-ContainerMysql -SkipColumnNames -Sql @"
SELECT COUNT(*)
FROM hlstats_Servers
WHERE address = '$ReplayServerAddress' AND port = $ReplayServerPort;
"@).Trim()
    if ($replayServerCount -ne "1") {
        throw "Expected replay server ${ReplayServerAddress}:${ReplayServerPort} in $dbContainer, got $replayServerCount"
    }
}

function Invoke-DumpRestore {
    Invoke-DbServiceUp
    Wait-DbReady
    Set-ComparisonSqlMode
    docker exec $dbContainer mysql -uroot -proot123 -e "DROP DATABASE IF EXISTS $DatabaseName; CREATE DATABASE $DatabaseName CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to recreate database $DatabaseName in $dbContainer"
    }

    docker exec $dbContainer sh -lc "rm -f /tmp/baseline_reset.sql.gz"
    docker cp $BaselineDump "${dbContainer}:/tmp/baseline_reset.sql.gz"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to copy baseline dump into $dbContainer"
    }

    docker exec $dbContainer sh -lc "gzip -dc /tmp/baseline_reset.sql.gz | mysql -uroot -proot123 $DatabaseName"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to restore baseline into $dbContainer"
    }

    if ($Stack -eq "python") {
        Invoke-PythonProxyBootstrap
    }
    Invoke-ReplayServerBootstrap
    Invoke-StateChecks
}

function Invoke-SnapshotRestore {
    Stop-DbService
    Restore-DbVolumeFromSnapshot -ArchivePath $snapshotArchive
    Invoke-DbServiceUp
    Wait-DbReady
    Set-ComparisonSqlMode
    Invoke-StateChecks
}

$effectiveMode = if ($CreateSnapshot -or $ForceDumpRestore) { "dump" } else { $RestoreMode }
$usedDumpFallback = $false

if ($effectiveMode -eq "snapshot") {
    Write-Host "Restore mode: snapshot-first (archive: $snapshotArchive)"
    try {
        Invoke-SnapshotRestore
        Write-Host "Snapshot restore succeeded for $dbContainer."
    } catch {
        if ($DisableDumpFallback) {
            throw
        }
        $usedDumpFallback = $true
        Write-Host "Snapshot restore failed, falling back to dump restore: $($_.Exception.Message)"
        Invoke-DumpRestore
    }
} else {
    Write-Host "Restore mode: dump"
    Invoke-DumpRestore
}

$shouldSaveSnapshot = $CreateSnapshot -or $usedDumpFallback -or (($RestoreMode -eq "snapshot") -and (-not (Test-Path $snapshotArchive)))
if ($shouldSaveSnapshot) {
    Write-Host "Saving DB snapshot archive: $snapshotArchive"
    Stop-DbService
    Save-DbVolumeSnapshot -ArchivePath $snapshotArchive
    Invoke-DbServiceUp
    Wait-DbReady
    Set-ComparisonSqlMode
    Invoke-StateChecks
}

Write-Host "Restore complete for $dbContainer. source=$($effectiveMode + ($(if($usedDumpFallback){'+dump-fallback'}else{''}))) snapshot=$snapshotArchive"
