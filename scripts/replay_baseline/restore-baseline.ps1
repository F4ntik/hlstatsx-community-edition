param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("legacy", "python")]
    [string]$Stack,

    [string]$BaselineDump = ""
)

$ErrorActionPreference = "Stop"

if (-not $PSScriptRoot) {
    $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

if (-not $BaselineDump) {
    $BaselineDump = Join-Path $PSScriptRoot "artifacts\baseline_reset_20260418.sql.gz"
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$composePath = Join-Path $PSScriptRoot "comparison\$Stack\docker-compose.yml"

$dbContainer = switch ($Stack) {
    "legacy" { "hlstatsx-legacy-db" }
    "python" { "hlstatsx-python-db" }
}

if (-not (Test-Path $BaselineDump)) {
    throw "Baseline dump not found: $BaselineDump"
}

docker compose -f $composePath up -d db | Out-Null

docker exec $dbContainer sh -lc "until mysqladmin ping -h 127.0.0.1 -uroot -proot123 --silent; do sleep 1; done" | Out-Null
docker exec $dbContainer mysql -uroot -proot123 -e "DROP DATABASE IF EXISTS hlstatsxce; CREATE DATABASE hlstatsxce CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" | Out-Null

docker exec $dbContainer sh -lc "rm -f /tmp/baseline_reset.sql.gz"
docker cp $BaselineDump "${dbContainer}:/tmp/baseline_reset.sql.gz"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to copy baseline dump into $dbContainer"
}

docker exec $dbContainer sh -lc "gzip -dc /tmp/baseline_reset.sql.gz | mysql -uroot -proot123 hlstatsxce"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to restore baseline into $dbContainer"
}

if ($Stack -eq "python") {
    $proxySchemaPath = Join-Path $repoRoot "scripts\proxy_daemon_py\fullstack\mysql\01_create_proxy_daemons.sql"
    docker exec $dbContainer sh -lc "rm -f /tmp/01_create_proxy_daemons.sql"
    docker cp $proxySchemaPath "${dbContainer}:/tmp/01_create_proxy_daemons.sql"
    docker exec $dbContainer sh -lc "mysql -uroot -proot123 hlstatsxce < /tmp/01_create_proxy_daemons.sql"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create Proxy_Daemons table in $dbContainer"
    }
    docker exec $dbContainer mysql -uroot -proot123 -D hlstatsxce -e "UPDATE hlstats_Options SET value='hlstatsx-python-worker:28000' WHERE keyname='Proxy_Daemons';" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to update Proxy_Daemons option in $dbContainer"
    }
}

Write-Host "Restored baseline into $dbContainer from $BaselineDump"
