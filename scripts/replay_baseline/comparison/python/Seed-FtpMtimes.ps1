# Ensure import_me.log is older than active_newest.log so hlstats_ftp_py imports the former
# and skips the latter as the "newest" active file (same idea as hlstats-ftp.pl).
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$import = Join-Path $here "ftp_logs\import_me.log"
$active = Join-Path $here "ftp_logs\active_newest.log"
if (-not (Test-Path $import) -or -not (Test-Path $active)) {
    throw "Expected ftp_logs\import_me.log and ftp_logs\active_newest.log under $here"
}
(Get-Item $import).LastWriteTime = (Get-Date).AddHours(-2)
(Get-Item $active).LastWriteTime = (Get-Date)
Write-Host "Set $($import.Name) older, $($active.Name) newer (mtime)."
