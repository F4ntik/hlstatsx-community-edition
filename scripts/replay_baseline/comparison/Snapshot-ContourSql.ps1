[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("legacy", "python")]
    [string]$Stack,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

$container = switch ($Stack) {
    "legacy" { "hlstatsx-legacy-db" }
    "python" { "hlstatsx-python-db" }
}

function Invoke-Query {
    param([string]$Sql)
    $result = docker exec $container mysql -uroot -proot123 -D hlstatsxce --batch --raw --skip-column-names -e $Sql
    if ($LASTEXITCODE -ne 0) {
        throw "query failed on $container"
    }
    return ($result | Out-String).Trim()
}

$lines = @()
$lines += "stack=$Stack"
$lines += "container=$container"
$lines += "timestamp=$((Get-Date).ToString('s'))"
$lines += ""
$lines += "[counts]"
$lines += "players=$(Invoke-Query "SELECT COUNT(*) FROM hlstats_Players;")"
$lines += "frags=$(Invoke-Query "SELECT COUNT(*) FROM hlstats_Events_Frags;")"
$lines += "frags_empty_map=$(Invoke-Query "SELECT COUNT(*) FROM hlstats_Events_Frags WHERE map='';")"
$lines += "maps_counts_rows=$(Invoke-Query "SELECT COUNT(*) FROM hlstats_Maps_Counts;")"
$lines += "awards_rows=$(Invoke-Query "SELECT COUNT(*) FROM hlstats_Players_Awards;")"
$lines += "ribbons_rows=$(Invoke-Query "SELECT COUNT(*) FROM hlstats_Players_Ribbons;")"
$lines += ""
$lines += "[event_time_range]"
$lines += "frags_minmax=$(Invoke-Query "SELECT CONCAT(COALESCE(MIN(eventTime),'NULL'),'|',COALESCE(MAX(eventTime),'NULL')) FROM hlstats_Events_Frags;")"
$lines += ""
$lines += "[top_frag_maps]"
$lines += (Invoke-Query "SELECT map, COUNT(*) c FROM hlstats_Events_Frags GROUP BY map ORDER BY c DESC LIMIT 20;")
$lines += ""
$lines += "[top_maps_counts]"
$lines += (Invoke-Query "SELECT map, kills FROM hlstats_Maps_Counts ORDER BY kills DESC LIMIT 20;")

$outputDir = Split-Path -Parent $OutputPath
if ($outputDir -and -not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}
$lines -join "`r`n" | Set-Content -Path $OutputPath -Encoding UTF8
Write-Host "Wrote SQL snapshot: $OutputPath"
