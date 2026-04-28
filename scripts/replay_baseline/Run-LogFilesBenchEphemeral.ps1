<#
.SYNOPSIS
  Ephemeral DB (3328) + direct import of N separate .log files (default 300).
  Does not touch the main Python comparison DB on 3327.

  Uses scripts/replay_baseline/direct_import_artifacts.py --file-count N: if the
  artifacts folder has fewer than N logs, real files are copied round-robin into
  work/bench_staged_logs until there are N files (same pipeline as FTP batch import).

.PARAMETER FileCount
  Number of .log files to process (default 300).

.PARAMETER SkipRestore
  Skip baseline gzip restore (DB volume already loaded).

.PARAMETER TearDown
  docker compose down -v for the ephemeral project after the run.
#>
param(
    [int] $FileCount = 300,
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
    Write-Host "Ephemeral DB (project=$ComposeProject, port 3328) for $FileCount .log files"
    docker compose -p $ComposeProject -f $composeFile up -d db

    Write-Host "Waiting for MariaDB..."
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        docker exec hlstatsx-writebench-db sh -c "mariadb-admin ping -h127.0.0.1 -uroot -proot123" 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw "MariaDB not ready" }

    if (-not $SkipRestore) {
        if (-not (Test-Path $dumpPath)) { throw "Dump not found: $dumpPath" }
        $absDump = (Resolve-Path $dumpPath).Path
        Write-Host "Restoring baseline into ephemeral volume..."
        docker run --rm `
            --network container:hlstatsx-writebench-db `
            -v "${absDump}:/dump.sql.gz:ro" `
            mariadb:10.11 bash -c "gunzip -c /dump.sql.gz | mariadb -h 127.0.0.1 -uroot -proot123 hlstatsxce"
        if ($LASTEXITCODE -ne 0) { throw "Restore failed: $LASTEXITCODE" }
    }

    $benchConfAbs = (Resolve-Path $benchConf).Path
    $env:PYTHONPATH = "scripts;scripts\proxy_daemon_py"
    Write-Host "direct_import_artifacts.py --file-count $FileCount (stdin batch per file, server 172.19.0.1:27015)"
    python scripts/replay_baseline/direct_import_artifacts.py `
        --configfile $benchConfAbs `
        --file-count $FileCount `
        --gs-ip 172.19.0.1 `
        --gs-port 27015 `
        --parser-backend native `
        --stdin-transaction-batch-size 2500
    $code = $LASTEXITCODE

    if ($TearDown) {
        docker compose -p $ComposeProject -f $composeFile down -v
    }

    if ($code -ne 0) { throw "direct_import_artifacts.py exit $code" }
}
finally {
    Pop-Location
}
