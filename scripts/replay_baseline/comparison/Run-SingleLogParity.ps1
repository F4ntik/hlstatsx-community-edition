[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$LogFile,
    [string]$Name = "",
    [string]$EventTime = "",
    [string]$Pattern = "",
    [int]$LineNumber = 0,
    [int]$Before = 200,
    [int]$After = 100,
    [string]$ServerIdentity = "37.230.137.48:27015",
    [string[]]$TraceTable = @(),
    [string[]]$TraceParamContains = @(),
    [switch]$Build
)

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $here "..\..\..")).Path
$runDual = Join-Path $here "Run-DualContour-1000.ps1"
$restore = Join-Path $repoRoot "scripts\replay_baseline\restore-baseline.ps1"
$traceRoot = Join-Path $repoRoot "scripts\replay_baseline\artifacts\parity-traces"
$ftpWork = Join-Path $here "python\ftp_work"

if (-not (Test-Path $runDual)) { throw "Run-DualContour-1000.ps1 not found: $runDual" }
if (-not (Test-Path $restore)) { throw "restore-baseline.ps1 not found: $restore" }
if (-not (Test-Path $ftpWork)) { New-Item -ItemType Directory -Path $ftpWork | Out-Null }

$sourceLog = (Resolve-Path $LogFile).Path
if (-not $Name) {
    $Name = [IO.Path]::GetFileNameWithoutExtension($sourceLog)
}
$safeName = ($Name -replace '[^A-Za-z0-9_.-]', '_')
$runDir = Join-Path $traceRoot $safeName
$inputDir = Join-Path $runDir "input"
$legacyTrace = Join-Path $runDir "legacy-general.log"
$pythonTrace = Join-Path $runDir "python-writes.jsonl"
$compareOut = Join-Path $runDir "compare-stats.txt"
$traceDiffOut = Join-Path $runDir "write-trace-diff.txt"
$statePath = Join-Path $runDir "state.json"
$pythonContainerTrace = "/tmp/ftp_work/$safeName-python-writes.jsonl"
$pythonHostTrace = Join-Path $ftpWork "$safeName-python-writes.jsonl"

New-Item -ItemType Directory -Force -Path $runDir, $inputDir | Out-Null
Remove-Item -Force $statePath, $legacyTrace, $pythonTrace, $compareOut, $traceDiffOut, $pythonHostTrace -ErrorAction SilentlyContinue

$inputLog = Join-Path $inputDir ([IO.Path]::GetFileName($sourceLog))
if ($EventTime -or $Pattern -or $LineNumber -gt 0) {
    $extractArgs = @(
        "scripts/replay_baseline/extract_log_window.py",
        "--log-file", $sourceLog,
        "--output", $inputLog,
        "--before", "$Before",
        "--after", "$After"
    )
    if ($EventTime) { $extractArgs += @("--event-time", $EventTime) }
    if ($Pattern) { $extractArgs += @("--pattern", $Pattern) }
    if ($LineNumber -gt 0) { $extractArgs += @("--line-number", "$LineNumber") }
    python @extractArgs | Tee-Object -FilePath (Join-Path $runDir "extract-window.txt")
    if ($LASTEXITCODE -ne 0) { throw "extract_log_window.py failed" }
} else {
    Copy-Item -Path $sourceLog -Destination $inputLog -Force
}

$dualCommon = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", $runDual,
    "-MaxImportFiles", "1",
    "-ArtifactsDir", $inputDir,
    "-UseDumpRestore",
    "-StatePath", $statePath
)
if (-not $Build) { $dualCommon += "-SkipBuild" }

Write-Host "==> Prepare clean comparison contours"
powershell @($dualCommon + @("-ToStage", "preflight"))
if ($LASTEXITCODE -ne 0) { throw "preflight failed" }

Write-Host "==> Legacy import with MariaDB general_log"
$generalLogSql = "SET GLOBAL general_log=OFF; SET GLOBAL log_output='TABLE'; TRUNCATE TABLE mysql.general_log; SET GLOBAL general_log=ON;"
docker exec hlstatsx-legacy-db mysql -uroot -proot123 -e $generalLogSql
if ($LASTEXITCODE -ne 0) { throw "failed to enable legacy general_log" }

powershell @($dualCommon + @("-OnlyStage", "legacy_import"))
if ($LASTEXITCODE -ne 0) { throw "legacy import failed" }

docker exec hlstatsx-legacy-db mysql -uroot -proot123 -e "SET GLOBAL general_log=OFF;"
if ($LASTEXITCODE -ne 0) { throw "failed to disable legacy general_log" }
docker exec hlstatsx-legacy-db mysql -uroot -proot123 --batch --raw --skip-column-names -e "SELECT argument FROM mysql.general_log WHERE command_type='Query' ORDER BY event_time" |
    Out-File -FilePath $legacyTrace -Encoding utf8

Write-Host "==> Python direct import with pre-batch write trace"
powershell -NoProfile -ExecutionPolicy Bypass -File $restore -Stack python -ForceDumpRestore
if ($LASTEXITCODE -ne 0) { throw "python restore failed" }
Get-ChildItem -Path $ftpWork -Filter "direct-artifacts-*.last" -ErrorAction SilentlyContinue | Remove-Item -Force

$dockerArgs = @(
    "run", "--rm",
    "--network", "python_hlstatsx_python_net",
    "-v", "${repoRoot}\scripts:/app/scripts",
    "-v", "${ftpWork}:/tmp/ftp_work",
    "-v", "${inputDir}:/tmp/single-log-window:ro",
    "-e", "PYTHONPATH=/app/scripts:/app/scripts/proxy_daemon_py",
    "-e", "HLSTATS_DB_WRITE_TRACE_PATH=$pythonContainerTrace",
    "python-hlstats-worker",
    "python", "/app/scripts/replay_baseline/direct_import_artifacts.py",
    "--artifacts-dir", "/tmp/single-log-window",
    "--configfile", "/app/hlstats.conf",
    "--work-dir", "/tmp/ftp_work",
    "--max-files", "1",
    "--gs-ip", ($ServerIdentity.Split(":")[0]),
    "--gs-port", ($ServerIdentity.Split(":")[1]),
    "--parser-backend", "python"
)
docker @dockerArgs | Tee-Object -FilePath (Join-Path $runDir "python-direct-import.txt")
if ($LASTEXITCODE -ne 0) { throw "python direct import failed" }
Copy-Item -Path $pythonHostTrace -Destination $pythonTrace -Force

Write-Host "==> Logical DB compare"
python scripts/replay_baseline/compare_stats_dbs.py --max-examples 10 *> $compareOut
$compareExit = $LASTEXITCODE

Write-Host "==> Normalized write trace diff"
$env:PYTHONIOENCODING = "utf-8"
$traceArgs = @(
    "scripts/replay_baseline/parity_trace.py",
    "diff",
    "--unordered",
    "--max-examples", "30",
    "--legacy", $legacyTrace,
    "--python", $pythonTrace,
    "--include-table-prefix", "hlstats_",
    "--ignore-table", "hlstats_Servers",
    "--ignore-table", "hlstats_Players",
    "--ignore-table", "hlstats_PlayerUniqueIds",
    "--ignore-table", "hlstats_PlayerNames",
    "--ignore-table", "hlstats_Players_History",
    "--ignore-table", "hlstats_Livestats",
    "--ignore-table", "hlstats_Events_Admin"
)
foreach ($table in $TraceTable) {
    if ($table) { $traceArgs += @("--table", $table) }
}
foreach ($term in $TraceParamContains) {
    if ($term) { $traceArgs += @("--param-contains", $term) }
}
python @traceArgs *> $traceDiffOut
$traceExit = $LASTEXITCODE

$summary = [ordered]@{
    name = $safeName
    input = $inputLog
    run_dir = $runDir
    legacy_trace = $legacyTrace
    python_trace = $pythonTrace
    compare_exit = $compareExit
    trace_diff_exit = $traceExit
    trace_table = $TraceTable
    trace_param_contains = $TraceParamContains
}
$summary | ConvertTo-Json | Out-File -FilePath (Join-Path $runDir "summary.json") -Encoding utf8

Write-Host "==> Single-log parity artifacts: $runDir"
Write-Host "compare exit: $compareExit"
Write-Host "trace diff exit: $traceExit"
exit 0
