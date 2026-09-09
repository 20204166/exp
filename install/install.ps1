# Install the stable wheel into the target venv (explicit, non-editable).
# REPLACES any existing install. Cut over only when intended.
param([string]$Version, [string]$Python)
. (Join-Path $PSScriptRoot "_common.ps1")

$py = Resolve-Python $Python
Require-Python $py
$wheel = Get-WheelPath $Version
Write-Host "Target python: $($py -join ' ')"
Write-Host "Before:"; Show-InstalledVersion $py
Remove-InstalledPackage $py
& $py -m pip install --no-index --no-deps --force-reinstall $wheel
if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }
Verify-InstalledWheel $py (Get-WheelVersion $wheel)
Write-Host "After:"; Show-InstalledVersion $py
Write-Host "Verify: system-analyzer-snapshot --help"
