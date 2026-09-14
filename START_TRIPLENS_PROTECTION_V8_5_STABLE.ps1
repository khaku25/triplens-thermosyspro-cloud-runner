[CmdletBinding()]
param(
    [string]$RepoRoot = 'C:\TripLens\triplens-thermosyspro-cloud-runner',
    [int]$OpcUaPort = 4841,
    [double]$StopTime = 86400,
    [double]$StepSize = 0.04,
    [double]$Tolerance = 0.001
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$repo=[System.IO.Path]::GetFullPath($RepoRoot)
$runtime=Join-Path $repo 'runtime\protection_dashboard_v8_5_stable'
$pathFile=Join-Path $runtime 'server.exe.path.txt'
if(-not (Test-Path -LiteralPath $pathFile -PathType Leaf)) {
    throw "Protection Dashboard V8.5 server path is missing. Run APPLY_TRIPLENS_PROTECTION_DASHBOARD_V8_5_2_DUAL_LOG_EVENT_HOTFIX.ps1 first."
}
$exe=(Get-Content -LiteralPath $pathFile -Raw).Trim()
if(-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Server executable is missing: $exe" }
$exe=[System.IO.Path]::GetFullPath($exe)
$buildRoot=[System.IO.Path]::GetFullPath((Join-Path $repo 'build'))
if(-not $exe.StartsWith($buildRoot + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase) -or
   [System.IO.Path]::GetFileName($exe) -notlike 'TripLens_v36_ProtectionDashboardV8_5_Stable*.exe') {
    throw "Refusing unverified server path: $exe"
}
$listener=Get-NetTCPConnection -State Listen -LocalPort $OpcUaPort -ErrorAction SilentlyContinue | Select-Object -First 1
if($null -ne $listener) {
    $owner=Get-Process -Id $listener.OwningProcess -ErrorAction Stop
    $ownerPath=$owner.PSObject.Properties['Path']
    if($null -eq $ownerPath -or -not [string]::Equals(
        [System.IO.Path]::GetFullPath([string]$ownerPath.Value),
        [System.IO.Path]::GetFullPath($exe),
        [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "TCP $OpcUaPort is already owned by a different process (PID=$($listener.OwningProcess))."
    }
    Write-Host "PASS: Protection Dashboard V8 OPC UA server already running PID=$($owner.Id)"
    exit 0
}
$build=Split-Path -Parent $exe
$stdout=Join-Path $build 'server.stdout.log'
$stderr=Join-Path $build 'server.stderr.log'
$serverArgs=@(
    '-startTime=0',"-stopTime=$StopTime","-stepSize=$StepSize","-tolerance=$Tolerance",
    '-s=dassl','-outputFormat=mat','-variableFilter=.*',"-r=$build\TripLens_v36_ProtectionDashboardV8_5_Stable_live_res.mat",
    '-rt=1','-w','-lv=LOG_STDOUT,LOG_ASSERT,LOG_STATS',
    '-embeddedServer=opc-ua',"-embeddedServerPort=$OpcUaPort"
)
$server=Start-Process -FilePath $exe -ArgumentList $serverArgs -WorkingDirectory $build `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$deadline=(Get-Date).AddSeconds(120)
do {
    Start-Sleep -Milliseconds 250
    $server.Refresh()
    if($server.HasExited) { throw "Protection Dashboard server exited early. Log: $stdout" }
    $listener=Get-NetTCPConnection -State Listen -LocalPort $OpcUaPort -ErrorAction SilentlyContinue | Select-Object -First 1
} until (($null -ne $listener -and $listener.OwningProcess -eq $server.Id) -or (Get-Date) -ge $deadline)
if($null -eq $listener -or $listener.OwningProcess -ne $server.Id) {
    Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
    throw "Protection Dashboard server did not listen on TCP $OpcUaPort. Log: $stdout"
}
$python=$null
foreach($candidate in @((Join-Path $repo '.venv\Scripts\python.exe'),(Join-Path $repo 'venv\Scripts\python.exe'))) {
    if(Test-Path -LiteralPath $candidate -PathType Leaf) { $python=$candidate; break }
}
if($null -eq $python) {
    $found=Get-Command python.exe -ErrorAction SilentlyContinue
    if($null -ne $found) { $python=$found.Source }
}
if($null -eq $python) { throw 'python.exe was not found.' }
$controller=Join-Path $repo 'scripts\opcua_run_controller.py'
if(-not (Test-Path -LiteralPath $controller -PathType Leaf)) {
    $controller=Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'TripLens_ProtectionDashboard_V8_5_LOGIC_STABLE\tools\opcua_run_controller.py'
}
if(-not (Test-Path -LiteralPath $controller -PathType Leaf)) { throw 'opcua_run_controller.py is missing.' }
& $python $controller --endpoint "opc.tcp://127.0.0.1:$OpcUaPort"
if($LASTEXITCODE -ne 0) {
    Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
    throw 'OpenModelica Run controller failed.'
}
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$server.Id | Set-Content -LiteralPath (Join-Path $runtime 'server.pid') -Encoding ASCII
Write-Host ''
Write-Host 'PASS: TRIPLENS_PROTECTION_DASHBOARD_V8_5_LOGIC_STABLE_STARTED'
Write-Host "PID:      $($server.Id)"
Write-Host "Endpoint: opc.tcp://127.0.0.1:$OpcUaPort"
Write-Host 'MATLAB:   cd(''C:\TripLens\triplens-thermosyspro-cloud-runner''); ECMSVPP'
