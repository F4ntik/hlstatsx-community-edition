<#
.SYNOPSIS
  Full Python comparison contour: compose down/up, FTP bind-mount to replay artifacts, baseline restore, hlstats_ftp_py import.

.PARAMETER MaxImportFiles
  Cap per run (default 400). Use -NoCap for entire queue (many hours).

.PARAMETER SkipBuild
  Faster `docker compose up -d` without --build when images are current.
#>
[CmdletBinding()]
param(
    [int] $MaxImportFiles = 400,
    [int] $FtpProbeLimit = 0,
    [switch] $NoCap,
    [switch] $SkipBuild,
    [switch] $SkipGeoIp,
    [switch] $GeoIpReplaySafe,
    [switch] $UseUdpReplay,
    [string] $ServerIdentity = "37.230.137.48:27015",
    [switch] $UseDumpRestore,
    [switch] $RecreateBaselineSnapshot
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $here "..\..\..\..")).Path
$compose = Join-Path $here "docker-compose.yml"
$artifacts = Join-Path $repoRoot "scripts\replay_baseline\artifacts"
if (-not (Test-Path $artifacts)) {
    throw "Artifacts directory not found: $artifacts"
}
$ftpWork = Join-Path $here "ftp_work"
if (-not (Test-Path $ftpWork)) {
    New-Item -ItemType Directory -Path $ftpWork | Out-Null
}
$scripts = Join-Path $repoRoot "scripts"
$geoIpDir = Join-Path $repoRoot "scripts\GeoLiteCity"
$geoIpDbPath = Join-Path $geoIpDir "GeoLite2-City.mmdb"
$restore = Join-Path $repoRoot "scripts\replay_baseline\restore-baseline.ps1"

$env:HLSTATS_FTP_LOGS_HOST_PATH = (Resolve-Path $artifacts).Path
$env:HLSTATS_GEOIP_DIR_HOST_PATH = (Resolve-Path $geoIpDir).Path
$env:HLSTATS_FTP_PASSWORD = "hlxftp123"

if (-not (Test-Path $geoIpDir)) {
    New-Item -ItemType Directory -Path $geoIpDir | Out-Null
}

if (-not (Test-Path $geoIpDbPath)) {
    Write-Host "==> GeoIP DB not found at $geoIpDbPath"
    $legacyContainer = "hlstatsx-legacy-daemon"
    $legacyHasDb = (docker exec $legacyContainer sh -lc "test -r /scripts/GeoLiteCity/GeoLite2-City.mmdb; echo `$?").Trim()
    if ($LASTEXITCODE -eq 0 -and $legacyHasDb -eq "0") {
        Write-Host "==> Copying GeoLite2-City.mmdb from $legacyContainer"
        docker cp "${legacyContainer}:/scripts/GeoLiteCity/GeoLite2-City.mmdb" $geoIpDbPath
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to copy GeoLite2-City.mmdb from $legacyContainer"
        }
    } else {
        Write-Host "==> Legacy GeoIP DB unavailable; strict --geoip will fail until GeoLite2-City.mmdb is provided."
    }
}

Write-Host "==> docker compose down"
docker compose -f $compose down

$upArgs = @("compose", "-f", $compose, "up", "-d")
if (-not $SkipBuild) {
    $upArgs += "--build"
}
Write-Host "==> docker $($upArgs -join ' ') (HLSTATS_FTP_LOGS_HOST_PATH -> artifacts)"
docker @upArgs

Write-Host "==> restore baseline (python)"
$restoreArgs = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $restore,
    "-Stack",
    "python"
)
if ($UseDumpRestore) {
    $restoreArgs += "-ForceDumpRestore"
}
if ($RecreateBaselineSnapshot) {
    $restoreArgs += "-CreateSnapshot"
}
powershell @restoreArgs

Write-Host "==> clear FTP import state for replay server 37.230.137.48:27015"
Get-ChildItem -Path $ftpWork -Filter "hlstats-ftp-37.230.137.48-27015.*" -ErrorAction SilentlyContinue | Remove-Item -Force

$identityParts = $ServerIdentity.Split(":", 2)
if ($identityParts.Count -ne 2) {
    throw "ServerIdentity must be HOST:PORT, got '$ServerIdentity'"
}
$serverIp = $identityParts[0]
$serverPort = [int]$identityParts[1]

if ($UseUdpReplay) {
    $replayPath = "/app/scripts/replay_baseline/artifacts"
    $shCmd = "python /app/scripts/replay_baseline/replay_python_log.py $replayPath --server-identity $ServerIdentity"
    Write-Host "==> Python import mode: UDP replay (opt-in)."
    Write-Host "==> UDP replay path keeps transport behavior for dedicated transport tests."
    if (-not $NoCap) {
        Write-Host "==> MaxImportFiles applies to FTP/stdin mode only; ignored for UDP replay."
    }
} else {
    $shCmd = "python -m hlstats_ftp_py --gs-ip $serverIp --gs-port $serverPort --ftp-ip log-ftp --ftp-port 21 --ftp-active --ftp-usr hlxslogs --ftp-dir / --configfile /app/hlstats.conf --cwd /tmp/ftp_work"
    if (-not $NoCap) {
        Write-Host "==> FTP import (stdin default, max $MaxImportFiles files this run). Re-run with higher -MaxImportFiles or -NoCap to continue."
        $shCmd += " --max-import-files $MaxImportFiles"
        if ($FtpProbeLimit -le 0) {
            $FtpProbeLimit = [Math]::Max(500, $MaxImportFiles + 150)
        }
        Write-Host "==> FTP metadata probe cap: $FtpProbeLimit (avoid 40k+ MDTM on huge dirs)"
        $shCmd += " --ftp-probe-limit $FtpProbeLimit"
    } else {
        Write-Host "==> FTP import (stdin default, NO FILE CAP - very long run)."
    }
}

docker compose -f $compose run -T --rm --no-deps `
    -v "${scripts}:/app/scripts" `
    -v "${ftpWork}:/tmp/ftp_work" `
    -e PYTHONPATH=/app/scripts:/app/scripts/proxy_daemon_py `
    -e HLSTATS_FTP_PASSWORD `
    hlstats-worker `
    sh -c $shCmd

if (-not $SkipGeoIp) {
    $geoipCmd = "python -m hlstats_awards_py --configfile /app/hlstats.conf --geoip"
    if ($GeoIpReplaySafe) {
        $geoipCmd += " --replay-mode"
        Write-Host "==> GeoIP backfill (replay-safe mode): $geoipCmd"
    } else {
        Write-Host "==> GeoIP backfill (strict mode): $geoipCmd"
    }
    docker compose -f $compose run -T --rm --no-deps `
        -v "${scripts}:/app/scripts" `
        -e PYTHONPATH=/app/scripts:/app/scripts/proxy_daemon_py `
        hlstats-worker `
        sh -c $geoipCmd
} else {
    Write-Host "==> GeoIP backfill skipped via -SkipGeoIp."
}

Write-Host "==> Done. Web: http://127.0.0.1:8281/hlstats.php - server 37.230.137.48:27015 (Replay)."
