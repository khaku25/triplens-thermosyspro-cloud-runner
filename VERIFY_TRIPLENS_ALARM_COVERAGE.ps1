[CmdletBinding()]
param(
    [string]$RepoRoot = 'C:\TripLens\triplens-thermosyspro-cloud-runner',
    [string]$Endpoint = 'opc.tcp://127.0.0.1:4841'
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$repo=[System.IO.Path]::GetFullPath($RepoRoot)
$python=$null
foreach($candidate in @((Join-Path $repo '.venv\Scripts\python.exe'),(Join-Path $repo 'venv\Scripts\python.exe'))) {
    if(Test-Path -LiteralPath $candidate -PathType Leaf) { $python=$candidate; break }
}
if($null -eq $python) {
    $found=Get-Command python.exe -ErrorAction SilentlyContinue
    if($null -ne $found) { $python=$found.Source }
}
if($null -eq $python) { throw 'python.exe was not found.' }
$registry=Join-Path $repo 'config\alarm_registry_v1.csv'
$verifier=Join-Path $repo 'scripts\verify_alarm_coverage_live.py'
$output=Join-Path $repo 'runtime\events\ALARM_COVERAGE_LIVE.json'
& $python $verifier --repo-root $repo --endpoint $Endpoint --registry $registry --output $output
if($LASTEXITCODE -ne 0) { throw "Plant alarm live coverage failed (code=$LASTEXITCODE)." }
Write-Host 'PASS: TRIPLENS_PLANT_ALARM_LIVE_COVERAGE_V7_4'
Write-Host "Report: $output"
