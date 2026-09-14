[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RepoRoot,
    [Parameter(Mandatory=$true)][string]$Endpoint,
    [Parameter(Mandatory=$true)][string]$SnapshotFile,
    [Parameter(Mandatory=$true)][string]$ControlFile,
    [Parameter(Mandatory=$true)][string]$DoneFile,
    [Parameter(Mandatory=$true)][string]$ErrorFile
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$configured=[Environment]::GetEnvironmentVariable('TRIPLENS_PYTHON')
$python=$null
foreach($candidate in @($configured,(Join-Path $RepoRoot '.venv\Scripts\python.exe'),(Join-Path $RepoRoot 'venv\Scripts\python.exe'))) {
    if(-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { $python=$candidate; break }
}
if($null -eq $python) {
    $found=Get-Command python.exe -ErrorAction SilentlyContinue
    if($null -ne $found) { $python=$found.Source }
}
if($null -eq $python) { throw 'python.exe was not found.' }
$script=Join-Path $RepoRoot 'scripts\ecms_bfp_alarm_engine.py'
$stdoutFile="$ErrorFile.stdout.log"
$utf8NoBom=New-Object System.Text.UTF8Encoding($false)
$code=99
try {
    $arguments=@(
        ('"'+$script+'"'),
        '--repo-root',('"'+$RepoRoot+'"'),
        '--endpoint',('"'+$Endpoint+'"'),
        '--snapshot-file',('"'+$SnapshotFile+'"'),
        '--control-file',('"'+$ControlFile+'"'),
        '--period','0.25',
        '--raw-period','1.0'
    )
    # Preserve Python's real exit code and avoid Windows PowerShell promoting
    # native stderr into a wrapper failure (the earlier code=98 problem).
    $process=Start-Process -FilePath $python -ArgumentList $arguments `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $stdoutFile -RedirectStandardError $ErrorFile
    $code=$process.ExitCode
} catch {
    [System.IO.File]::WriteAllText($ErrorFile,($_ | Out-String),$utf8NoBom)
    $code=98
} finally {
    Remove-Item -LiteralPath $stdoutFile -Force -ErrorAction SilentlyContinue
    $temporary="$DoneFile.tmp"
    [System.IO.File]::WriteAllText($temporary,[string]$code,$utf8NoBom)
    Move-Item -LiteralPath $temporary -Destination $DoneFile -Force
}
exit $code
