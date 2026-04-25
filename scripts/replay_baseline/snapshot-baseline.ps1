param(
    [string]$SourceContainer = "hlstatsx-local-db",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

if (-not $PSScriptRoot) {
    $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

if (-not $OutputPath) {
    $OutputPath = Join-Path $PSScriptRoot "artifacts\baseline_reset_20260418.sql.gz"
}

$outDir = Split-Path -Parent $OutputPath
if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir | Out-Null
}

docker exec $SourceContainer sh -lc "rm -f /tmp/baseline_reset.sql.gz && mysqldump -uroot -proot123 --single-transaction --routines --triggers --events hlstatsxce | gzip -1 > /tmp/baseline_reset.sql.gz"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create compressed baseline inside $SourceContainer"
}

if (Test-Path $OutputPath) {
    Remove-Item -LiteralPath $OutputPath -Force
}

docker cp "${SourceContainer}:/tmp/baseline_reset.sql.gz" $OutputPath
if ($LASTEXITCODE -ne 0) {
    throw "Failed to copy baseline dump from $SourceContainer"
}

Write-Host "Saved baseline dump to $OutputPath"
