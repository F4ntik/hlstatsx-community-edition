param(
    [int]$MinBytes = 15360
)

$ErrorActionPreference = "Stop"

if (-not $PSScriptRoot) {
    $PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$artifactsPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "artifacts"))
if (-not (Test-Path -LiteralPath $artifactsPath)) {
    throw "Artifacts directory not found: $artifactsPath"
}

$logFiles = Get-ChildItem -LiteralPath $artifactsPath -File -Filter *.log
$beforeTotal = $logFiles.Count
$beforeSmall = @($logFiles | Where-Object { $_.Length -lt $MinBytes })

Write-Host "Artifacts path: $artifactsPath"
Write-Host "Before prune: total=$beforeTotal, below_threshold=$($beforeSmall.Count), threshold_bytes=$MinBytes"

foreach ($logFile in $beforeSmall) {
    Remove-Item -LiteralPath $logFile.FullName
}

$afterFiles = Get-ChildItem -LiteralPath $artifactsPath -File -Filter *.log
$afterSmallCount = @($afterFiles | Where-Object { $_.Length -lt $MinBytes }).Count

Write-Host "After prune: total=$($afterFiles.Count), below_threshold=$afterSmallCount, removed=$($beforeSmall.Count)"
