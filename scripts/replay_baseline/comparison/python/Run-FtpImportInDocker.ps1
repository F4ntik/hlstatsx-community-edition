# Run hlstats_ftp_py inside the worker image (has mysqlclient). Mounts repo scripts + persistent ftp_work.
# Prereq: docker compose up -d (db + log-ftp at least; db must match restored baseline).
# Usage (from repo root hlstatsx-community-edition-python-i18n):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-FtpImportInDocker.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
# here = scripts/replay_baseline/comparison/python -> repo root is four levels up
$repoRoot = (Resolve-Path (Join-Path $here "..\..\..\..")).Path
$compose = Join-Path $here "docker-compose.yml"
$ftpWork = Join-Path $here "ftp_work"
if (-not (Test-Path $ftpWork)) {
    New-Item -ItemType Directory -Path $ftpWork | Out-Null
}

$scripts = Join-Path $repoRoot "scripts"
$env:HLSTATS_FTP_PASSWORD = "hlxftp123"

docker compose -f $compose run --rm --no-deps `
    -v "${scripts}:/app/scripts" `
    -v "${ftpWork}:/tmp/ftp_work" `
    -e PYTHONPATH=/app/scripts:/app/scripts/proxy_daemon_py `
    -e HLSTATS_FTP_PASSWORD `
    hlstats-worker `
    sh -c "python -m hlstats_ftp_py --gs-ip 172.19.0.1 --gs-port 27015 --ftp-ip log-ftp --ftp-port 21 --ftp-active --ftp-usr hlxslogs --ftp-dir / --configfile /app/hlstats.conf --cwd /tmp/ftp_work"
