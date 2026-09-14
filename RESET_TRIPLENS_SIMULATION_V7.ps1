[CmdletBinding()]
param(
    [string]$RepoRoot = 'C:\TripLens\triplens-thermosyspro-cloud-runner',
    [int]$OpcUaPort = 4841,
    [double]$StopTime = 86400,
    [Parameter(Mandatory=$true)][string]$DoneFile,
    [Parameter(Mandatory=$true)][string]$ErrorFile
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$code=99
$utf8NoBom=New-Object System.Text.UTF8Encoding($false)
try {
    $repo=[System.IO.Path]::GetFullPath($RepoRoot)
    $startup=Join-Path $repo 'START_TRIPLENS_PROTECTION_V8_5_STABLE.ps1'
    $pathFile=Join-Path $repo 'runtime\protection_dashboard_v8_5_stable\server.exe.path.txt'
    if(-not (Test-Path -LiteralPath $startup -PathType Leaf)) {
        throw "Runtime startup script is missing: $startup"
    }
    if(-not (Test-Path -LiteralPath $pathFile -PathType Leaf)) {
        throw "Verified server path is missing: $pathFile"
    }
    $expectedExe=[System.IO.Path]::GetFullPath((Get-Content -LiteralPath $pathFile -Raw).Trim())
    $listener=Get-NetTCPConnection -State Listen -LocalPort $OpcUaPort -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if($null -ne $listener) {
        $owner=Get-Process -Id $listener.OwningProcess -ErrorAction Stop
        $ownerPath=$owner.PSObject.Properties['Path']
        if($null -eq $ownerPath -or [string]::IsNullOrWhiteSpace([string]$ownerPath.Value)) {
            throw "Cannot verify owner of TCP $OpcUaPort (PID=$($owner.Id))."
        }
        $actualExe=[System.IO.Path]::GetFullPath([string]$ownerPath.Value)
        if(-not [string]::Equals($actualExe,$expectedExe,[System.StringComparison]::OrdinalIgnoreCase)) {
            throw "TCP $OpcUaPort belongs to another program: PID=$($owner.Id), path=$actualExe"
        }
        Stop-Process -Id $owner.Id -Force
    }
    $deadline=(Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 250
        $listener=Get-NetTCPConnection -State Listen -LocalPort $OpcUaPort -ErrorAction SilentlyContinue |
            Select-Object -First 1
    } until ($null -eq $listener -or (Get-Date) -ge $deadline)
    if($null -ne $listener) { throw "TCP $OpcUaPort did not close after stopping the verified server." }

    & $startup -RepoRoot $repo -OpcUaPort $OpcUaPort -StopTime $StopTime
    $listener=Get-NetTCPConnection -State Listen -LocalPort $OpcUaPort -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if($null -eq $listener) { throw "Fresh server did not listen on TCP $OpcUaPort." }
    $code=0
} catch {
    [System.IO.File]::WriteAllText($ErrorFile,($_ | Out-String),$utf8NoBom)
    $code=1
} finally {
    $temporary="$DoneFile.tmp"
    [System.IO.File]::WriteAllText($temporary,[string]$code,$utf8NoBom)
    Move-Item -LiteralPath $temporary -Destination $DoneFile -Force
}
exit $code
