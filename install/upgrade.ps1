# Upgrade to a given wheel, or build the latest wheel then install it.
param([string]$Version, [string]$Python)
. (Join-Path $PSScriptRoot "_common.ps1")

$py = Resolve-Python $Python
Require-Python $py
Write-Host "Before:"; Show-InstalledVersion $py
if ($Version) {
    $wheel = Get-WheelPath $Version
} else {
    & (Join-Path $PSScriptRoot "build.ps1") -Python $Python
    $wheel = Get-WheelPath
}
Write-Host "Upgrading to: $(Split-Path $wheel -Leaf)"
& $py -m pip install --no-index --no-deps --force-reinstall $wheel
if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }
Write-Host "After:"; Show-InstalledVersion $py
Write-Host "Rollback: rollback.ps1 -Version <previous>"