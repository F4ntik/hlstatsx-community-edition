<#
.SYNOPSIS
  Restores one disposable database, imports the deterministic heatmap fixture,
  and writes a sanitized coordinate receipt.

.DESCRIPTION
  This runner is deliberately limited to bench_ephemeral. It refuses the fixed
  container, port, or volume when another run could own them, and never targets
  the persistent comparison contour. Task 10 validates this source contract;
  live execution is a separate runtime-acceptance gate.
#>
param(
    [ValidateSet("bench_ephemeral")]
    [string]$Target = "bench_ephemeral",
    [ValidatePattern("^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")]
    [string]$EvidenceLabel = "heatmap-coordinate-contract",
    [string]$BaselineDumpRel = "scripts\replay_baseline\artifacts\baseline_reset_20260418.sql.gz",
    [string]$ReceiptDirectory = "scripts\replay_baseline\artifacts\heatmap-coordinate-acceptance"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $PSScriptRoot) {
    $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$composeProject = "hlstatsxwritebench"
$containerName = "hlstatsx-writebench-db"
$hostPort = 3328
$volumeName = "${composeProject}_hlstatsx_writebench_mysql"
$composeFile = Join-Path $repoRoot "scripts\replay_baseline\bench_ephemeral\docker-compose.yml"
$benchConfigPath = Join-Path $repoRoot "scripts\replay_baseline\bench_ephemeral\hlstats.host.conf"
$fixturePath = Join-Path $repoRoot "scripts\replay_baseline\fixtures\modern_heatmap_coordinates.log"
$dumpPath = Join-Path $repoRoot $BaselineDumpRel
$receiptRoot = Join-Path $repoRoot $ReceiptDirectory

function Get-ConfigValue {
    param([Parameter(Mandatory = $true)][string]$Key)

    $match = [regex]::Match($script:benchConfigText, "(?m)^\s*$([regex]::Escape($Key))\s+(.+?)\s*$")
    if (-not $match.Success) {
        throw "Required disposable configuration value is missing."
    }
    return $match.Groups[1].Value.Trim()
}

function Get-ComposeValue {
    param([Parameter(Mandatory = $true)][string]$Key)

    $match = [regex]::Match($script:composeText, "(?m)^\s*$([regex]::Escape($Key)):\s*(\S+)\s*$")
    if (-not $match.Success) {
        throw "Required disposable compose value is missing."
    }
    return $match.Groups[1].Value.Trim()
}

function Invoke-CheckedDocker {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    $discardedOutput = @(& docker @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

function Assert-UnoccupiedDisposableTarget {
    $existingContainer = [string](& docker container ls -a --filter "name=^/${containerName}$" --format '{{.ID}}' 2>$null)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect the disposable container."
    }
    if (-not [string]::IsNullOrWhiteSpace($existingContainer)) {
        throw "Refusing an occupied fixed disposable container."
    }

    $portListeners = @(Get-NetTCPConnection -State Listen -LocalPort $hostPort -ErrorAction SilentlyContinue)
    if ($portListeners.Count -gt 0) {
        throw "Refusing an occupied fixed disposable port."
    }

    $existingVolume = [string](& docker volume ls --filter "name=^${volumeName}$" --format '{{.Name}}' 2>$null)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect the disposable volume."
    }
    if (-not [string]::IsNullOrWhiteSpace($existingVolume)) {
        throw "Refusing a stale disposable volume; clean it only after owner review."
    }
}

function Wait-ForDisposableDatabase {
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        $discardedOutput = @(& docker exec -e "MYSQL_PWD=$script:dbPassword" $script:containerName `
                mariadb-admin --protocol=socket -u $script:dbUsername ping 2>&1)
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "Disposable MariaDB did not become ready."
}

function Invoke-DatabaseRows {
    param([Parameter(Mandatory = $true)][string]$Sql)

    $rows = @($Sql | & docker exec -i -e "MYSQL_PWD=$script:dbPassword" $script:containerName `
            mariadb --protocol=socket -u $script:dbUsername --batch --skip-column-names $script:dbName 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "A coordinate assertion database command failed."
    }
    return @($rows | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ -ne "" })
}

function Get-FragCoordinates {
    param(
        [Parameter(Mandatory = $true)][string]$KillerUniqueId,
        [Parameter(Mandatory = $true)][string]$VictimUniqueId,
        [Parameter(Mandatory = $true)][string]$Weapon,
        [switch]$Headshot
    )

    $coordinateProjection = @"
CONCAT_WS('|',
  COALESCE(CAST(frag.pos_x AS CHAR), 'NULL'),
  COALESCE(CAST(frag.pos_y AS CHAR), 'NULL'),
  COALESCE(CAST(frag.pos_z AS CHAR), 'NULL'),
  COALESCE(CAST(frag.pos_victim_x AS CHAR), 'NULL'),
  COALESCE(CAST(frag.pos_victim_y AS CHAR), 'NULL'),
  COALESCE(CAST(frag.pos_victim_z AS CHAR), 'NULL')
)
"@
    $killerId = $KillerUniqueId.Replace("'", "''")
    $victimId = $VictimUniqueId.Replace("'", "''")
    $weaponName = $Weapon.Replace("'", "''")

    $headshotPredicate = if ($Headshot) { "AND frag.headshot = 1" } else { "" }
    $sql = @"
SELECT $coordinateProjection
FROM hlstats_Events_Frags AS frag
INNER JOIN hlstats_Players AS killer ON killer.playerId = frag.killerId
INNER JOIN hlstats_Players AS victim ON victim.playerId = frag.victimId
WHERE killer.uniqueId = '$killerId'
  AND victim.uniqueId = '$victimId'
  AND frag.weapon = '$weaponName'
  $headshotPredicate
ORDER BY frag.id
"@
    return Invoke-DatabaseRows -Sql $sql
}

function Get-SuicideCoordinates {
    param(
        [Parameter(Mandatory = $true)][string]$VictimUniqueId,
        [Parameter(Mandatory = $true)][string]$Weapon
    )

    $victimId = $VictimUniqueId.Replace("'", "''")
    $weaponName = $Weapon.Replace("'", "''")
    $sql = @"
SELECT CONCAT_WS('|',
  'NULL', 'NULL', 'NULL',
  COALESCE(CAST(suicide.pos_x AS CHAR), 'NULL'),
  COALESCE(CAST(suicide.pos_y AS CHAR), 'NULL'),
  COALESCE(CAST(suicide.pos_z AS CHAR), 'NULL')
)
FROM hlstats_Events_Suicides AS suicide
INNER JOIN hlstats_Players AS victim ON victim.playerId = suicide.playerId
WHERE victim.uniqueId = '$victimId'
  AND suicide.weapon = '$weaponName'
ORDER BY suicide.id
"@
    return Invoke-DatabaseRows -Sql $sql
}

foreach ($requiredPath in @($composeFile, $benchConfigPath, $fixturePath, $dumpPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required coordinate-acceptance input is missing."
    }
}

$composeText = Get-Content -LiteralPath $composeFile -Raw
$benchConfigText = Get-Content -LiteralPath $benchConfigPath -Raw
$rootPassword = Get-ComposeValue -Key "MARIADB_ROOT_PASSWORD"
$dbUsername = Get-ConfigValue -Key "DBUsername"
$dbPassword = Get-ConfigValue -Key "DBPassword"
$dbName = Get-ConfigValue -Key "DBName"
foreach ($databaseIdentifier in @($dbUsername, $dbName)) {
    if ($databaseIdentifier -notmatch "^[A-Za-z0-9_]+$") {
        throw "Disposable database identifiers are invalid."
    }
}

$started = $false
Push-Location $repoRoot
try {
    Assert-UnoccupiedDisposableTarget
    Invoke-CheckedDocker -Arguments @("compose", "-p", $composeProject, "-f", $composeFile, "up", "-d", "db") `
        -FailureMessage "Unable to start the disposable coordinate database."
    $started = $true
    Wait-ForDisposableDatabase

    $absoluteDumpPath = (Resolve-Path -LiteralPath $dumpPath).Path
    Invoke-CheckedDocker -Arguments @(
        "run", "--rm", "--network", "container:$containerName",
        "-v", "${absoluteDumpPath}:/dump.sql.gz:ro",
        "-e", "MYSQL_PWD=$rootPassword",
        "mariadb:10.11", "sh", "-c",
        "gunzip -c /dump.sql.gz | mariadb --protocol=TCP -h 127.0.0.1 -u root $dbName"
    ) -FailureMessage "Fresh disposable baseline restore failed."

    $env:PYTHONPATH = "scripts;scripts/replay_baseline"
    $fixtureContent = Get-Content -LiteralPath $fixturePath -Raw
    $discardedImportOutput = @($fixtureContent | & python -m hlstats_py.runtime `
            --configfile $benchConfigPath --stdin --server-ip 172.19.0.1 --server-port 27015 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Fixture import failed."
    }

    $coordinateCases = @(
        [ordered]@{ name = "shipped_cstrike_distinct"; source = "frag"; killer = "STEAM_1:0:900001"; victim = "STEAM_1:0:900002"; weapon = "ak47"; headshot = $true; expected = "101|202|303|404|505|606" },
        [ordered]@{ name = "sourcemod_suicide_victim_only"; source = "suicide"; victim = "STEAM_1:0:900003"; weapon = "worldspawn"; expected = "NULL|NULL|NULL|707|808|909" },
        [ordered]@{ name = "staged_pair_consumed_once"; source = "frag"; killer = "STEAM_1:0:900004"; victim = "STEAM_1:0:900005"; weapon = "m4a1"; headshot = $false; expected = "1001|1002|1003|1101|1102|1103" },
        [ordered]@{ name = "staged_pair_not_reused"; source = "frag"; killer = "STEAM_1:0:900006"; victim = "STEAM_1:0:900007"; weapon = "m4a1"; headshot = $false; expected = "NULL|NULL|NULL|NULL|NULL|NULL" },
        [ordered]@{ name = "source_boundary_clears_staged_pair"; source = "frag"; killer = "STEAM_1:0:900008"; victim = "STEAM_1:0:900009"; weapon = "m4a1"; headshot = $false; expected = "NULL|NULL|NULL|NULL|NULL|NULL" }
    )

    $rowCounts = [ordered]@{}
    $assertedCoordinateTuples = [ordered]@{}
    foreach ($case in $coordinateCases) {
        $rows = if ($case.source -eq "suicide") {
            @(Get-SuicideCoordinates -VictimUniqueId $case.victim -Weapon $case.weapon)
        } else {
            @(Get-FragCoordinates -KillerUniqueId $case.killer -VictimUniqueId $case.victim `
                    -Weapon $case.weapon -Headshot:$case.headshot)
        }
        if ($rows.Count -ne 1 -or $rows[0] -ne $case.expected) {
            throw "Coordinate assertion failed."
        }
        $rowCounts[$case.name] = $rows.Count
        $assertedCoordinateTuples[$case.name] = $case.expected
    }

    $fixtureHash = (Get-FileHash -LiteralPath $fixturePath -Algorithm SHA256).Hash.ToLowerInvariant()
    New-Item -ItemType Directory -Force -Path $receiptRoot | Out-Null
    $receiptPath = Join-Path $receiptRoot ("{0}-{1}.json" -f $EvidenceLabel, (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ"))
    $receipt = [ordered]@{
        schema = "heatmap-coordinate-acceptance/v1"
        verdict = "pass"
        created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        contour = [ordered]@{
            target = $Target
            compose_project = $composeProject
            container = $containerName
            host_port = $hostPort
        }
        fixture_sha256 = $fixtureHash
        row_counts = $rowCounts
        asserted_coordinate_tuples = $assertedCoordinateTuples
    }
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding utf8
    Write-Host "Heatmap coordinate acceptance passed; sanitized receipt: $receiptPath"
}
finally {
    if ($started) {
        $discardedCleanupOutput = @(& docker compose -p $composeProject -f $composeFile down -v 2>&1)
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Disposable cleanup did not complete; inspect only the named bench_ephemeral resources."
        }
    }
    Pop-Location
}
