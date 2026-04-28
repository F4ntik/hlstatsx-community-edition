<#
.SYNOPSIS
  Disposable MariaDB on port 3328, optional baseline restore, bench_write_path subprocess run.
  Does NOT modify the main Python comparison DB (3327 / hlstatsx-python-db).

.PARAMETER Lines
  Synthetic chat lines (default 300).

.PARAMETER SkipRestore
  Skip gzip restore (DB volume already contains data).

.PARAMETER TearDown
  docker compose down -v for the ephemeral project after the run.
#>
param(
    [int] $Lines = 300,
    [switch] $SkipRestore,
    [switch] $TearDown,
    [string] $ComposeProject = "hlstatsxwritebench",
    [string] $BaselineDumpRel = "scripts\replay_baseline\artifacts\baseline_reset_20260418.sql.gz"
)

$ErrorActionPreference = "Stop"
if (-not $PSScriptRoot) {
    $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$composeFile = Join-Path $PSScriptRoot "bench_ephemeral\docker-compose.yml"
$benchConf = Join-Path $PSScriptRoot "bench_ephemeral\hlstats.host.conf"
$dumpPath = Join-Path $repoRoot $BaselineDumpRel

if (-not (Test-Path $composeFile)) { throw "Missing: $composeFile" }
if (-not (Test-Path $benchConf)) { throw "Missing: $benchConf" }

Push-Location $repoRoot
try {
    Write-Host "Ephemeral DB: docker compose -p $ComposeProject (port 3328, container hlstatsx-writebench-db)"
    docker compose -p $ComposeProject -f $composeFile up -d db

    Write-Host "Waiting for MariaDB..."
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        # Avoid PowerShell misparsing -h127.0.0.1 as -h127; run ping inside the shell.
        docker exec hlstatsx-writebench-db sh -c "mariadb-admin ping -h127.0.0.1 -uroot -proot123" 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw "MariaDB not ready (docker exec hlstatsx-writebench-db ...)" }

    if (-not $SkipRestore) {
        if (-not (Test-Path $dumpPath)) {
            throw "Dump not found: $dumpPath (use -SkipRestore if already loaded)"
        }
        $absDump = (Resolve-Path $dumpPath).Path
        Write-Host "Restoring into ephemeral volume only..."
        docker run --rm `
            --network container:hlstatsx-writebench-db `
            -v "${absDump}:/dump.sql.gz:ro" `
            mariadb:10.11 bash -c "gunzip -c /dump.sql.gz | mariadb -h 127.0.0.1 -uroot -proot123 hlstatsxce"
        if ($LASTEXITCODE -ne 0) { throw "Restore failed: $LASTEXITCODE" }
    }

    $benchConfAbs = (Resolve-Path $benchConf).Path
    $env:PYTHONPATH = "scripts;scripts\proxy_daemon_py"
    Write-Host "Benchmark: $Lines lines -> hlstats_py.runtime --stdin"
    python scripts/replay_baseline/bench_write_path.py `
        --mode subprocess `
        --lines $Lines `
        --configfile $benchConfAbs `
        --server-ip 172.19.0.1 `
        --server-port 27015
    $code = $LASTEXITCODE

    if ($TearDown) {
        Write-Host "docker compose -p $ComposeProject ... down -v"
        docker compose -p $ComposeProject -f $composeFile down -v
    }

    if ($code -ne 0) { throw "bench_write_path.py exit $code" }
}
finally {
    Pop-Location
}
