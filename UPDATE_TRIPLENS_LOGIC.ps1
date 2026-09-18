param(
    [switch]$FromDrive,
    [switch]$SyncDrive,
    [switch]$Check,
    [switch]$Publish,
    [string]$Layout = ""
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$arguments = @("scripts/update_triplens_logic.py")
if ($FromDrive) { $arguments += "--from-drive" }
if ($SyncDrive) { $arguments += "--sync-drive" }
if ($Check) { $arguments += "--check" }
if ($Layout) { $arguments += @("--layout", $Layout) }
& python @arguments
if ($LASTEXITCODE -ne 0) { throw "Logic update blocked. No deployment was attempted." }
if ($Publish -and -not $Check) {
    & git add -- data/current_v8 logic_diagrams generated/logic apps/web/public/logic-assets apps/web/lib/current-logic-summary.json services/agent-api/triplens/current_v8
    if ($LASTEXITCODE -ne 0) { throw "git add failed" }
    & git diff --cached --quiet
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "Update generated TripLens logic assets"
        if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
        & git push
        if ($LASTEXITCODE -ne 0) { throw "git push failed; assets are saved locally" }
    } elseif ($LASTEXITCODE -ne 0) { throw "git diff failed" }
}
