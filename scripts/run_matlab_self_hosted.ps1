param(
    [Parameter(Mandatory=$true)]
    [string]$MatlabCommand
)

$ErrorActionPreference = 'Stop'

function Find-MatlabExe {
    $cmd = Get-Command matlab.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $roots = @(
        'C:\Program Files\MATLAB',
        'C:\Program Files (x86)\MATLAB'
    )

    foreach ($root in $roots) {
        if (Test-Path $root) {
            $candidates = Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending |
                ForEach-Object { Join-Path $_.FullName 'bin\matlab.exe' } |
                Where-Object { Test-Path $_ }
            if ($candidates) { return $candidates[0] }
        }
    }

    throw 'MATLAB executable not found. Add MATLAB\bin to PATH or install MATLAB under C:\Program Files\MATLAB.'
}

$matlab = Find-MatlabExe
Write-Host "Using MATLAB: $matlab"
& $matlab -batch $MatlabCommand
if ($LASTEXITCODE -ne 0) {
    throw "MATLAB exited with code $LASTEXITCODE"
}
