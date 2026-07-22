param(
    [Parameter(Mandatory = $true)][string] $Variant,
    [Parameter(Mandatory = $true)][string] $Sample,
    [Parameter(Mandatory = $true)][string] $Repo,
    [Parameter(Mandatory = $true)][int] $Port,
    [switch] $Profile,
    [switch] $KeepContainer
)

$ErrorActionPreference = 'Stop'
$audit = Split-Path -Parent $PSCommandPath
$name = "hlstatsx-sqlwrite-1000-$Variant-$Sample"
$volume = "hlstatsx_sqlwrite_1000_$Variant`_$Sample"
$log = Join-Path $audit "$Variant-$Sample-run.log"
$dump = Join-Path $Repo 'scripts\replay_baseline\artifacts\baseline_reset_20260418.sql.gz'
$config = Join-Path $audit "hlstats-bench-$Port.conf"
$stage = 'C:\Users\semer\AppData\Local\Temp\hlstatsx-sqlwrite-1000-bench-r1'

function Run([string[]] $Command) {
    & $Command[0] $Command[1..($Command.Count - 1)] 2>&1 | Tee-Object -FilePath $log -Append
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $($Command -join ' ')" }
}

$anchorSql = "SELECT 'players' AS metric, COUNT(*) AS value FROM hlstats_Players UNION ALL SELECT 'history',COUNT(*) FROM hlstats_Players_History UNION ALL SELECT 'frags',COUNT(*) FROM hlstats_Events_Frags UNION ALL SELECT 'admin',COUNT(*) FROM hlstats_Events_Admin UNION ALL SELECT 'statsme',COUNT(*) FROM hlstats_Events_Statsme UNION ALL SELECT 'statsme2',COUNT(*) FROM hlstats_Events_Statsme2;"
function Capture-Anchor([string] $Path) {
    & docker exec $name mysql -uroot -proot123 -D hlstatsxce --batch --raw -e $anchorSql 2>&1 | Tee-Object -FilePath $Path
    if ($LASTEXITCODE -ne 0) { throw "Anchor query failed ($LASTEXITCODE)" }
}

try {
    Run @('docker','run','-d','--name',$name,'-p',"${Port}:3306",'-v',"${volume}:/var/lib/mysql",'-e','MARIADB_ROOT_PASSWORD=root123','-e','MARIADB_DATABASE=hlstatsxce','-e','MARIADB_USER=hlstatsxce','-e','MARIADB_PASSWORD=hlx123','mariadb:10.11','--character-set-server=utf8mb4','--collation-server=utf8mb4_unicode_ci','--max-allowed-packet=256M','--sql-mode=NO_ENGINE_SUBSTITUTION')
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = 'SilentlyContinue'
        & docker exec $name sh -lc 'mariadb-admin ping -h127.0.0.1 -uroot -proot123' 2>$null | Out-Null
        $pingExitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousErrorAction
        if ($pingExitCode -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw 'MariaDB did not become ready' }
    Run @('docker','run','--rm','--network',"container:$name",'-v',"${dump}:/dump.sql.gz:ro",'mariadb:10.11','sh','-lc','gunzip -c /dump.sql.gz | mariadb -h127.0.0.1 -uroot -proot123 hlstatsxce')
    Capture-Anchor (Join-Path $audit "$Variant-$Sample-initial-anchors.tsv")
    Push-Location $Repo
    try {
        $env:PYTHONPATH = 'scripts;scripts\proxy_daemon_py'
        $importArgs = @('scripts/replay_baseline/direct_import_artifacts.py','--artifacts-dir',$stage,'--configfile',$config,'--work-dir',(Join-Path $stage "$Variant-$Sample-work"),'--max-files','1000','--gs-ip','172.19.0.1','--gs-port','27015','--parser-backend','native','--stdin-transaction-batch-size','2500','--input-manifest',(Join-Path $audit "$Variant-$Sample-input-manifest.txt"),'--ignored-lines-manifest',(Join-Path $audit "$Variant-$Sample-ignored-lines.txt"))
        if ($Profile) { $importArgs += @('--profile','--audit-dir',(Join-Path $audit "$Variant-$Sample-profile")) }
        @("profile=$($Profile.IsPresent)", "command=python $($importArgs -join ' ')") | Set-Content -LiteralPath (Join-Path $audit "$Variant-$Sample-command.txt") -Encoding utf8
        python @importArgs 2>&1 | Tee-Object -FilePath $log -Append
        if ($LASTEXITCODE -ne 0) { throw "direct import failed: $LASTEXITCODE" }
    }
    finally { Pop-Location }
    Capture-Anchor (Join-Path $audit "$Variant-$Sample-final-anchors.tsv")
    Set-Content -LiteralPath (Join-Path $audit "$Variant-$Sample-success.txt") -Value "container=$name`nvolume=$volume`nport=$Port" -NoNewline
}
catch {
    $_ | Out-String | Tee-Object -FilePath (Join-Path $audit "$Variant-$Sample-failure.txt")
    exit 1
}
finally {
    if (-not $KeepContainer) {
        docker rm -f $name 2>&1 | Tee-Object -FilePath $log -Append
        docker volume rm $volume 2>&1 | Tee-Object -FilePath $log -Append
    }
}
