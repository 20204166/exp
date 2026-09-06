# Roll back to a previous wheel kept in dist/. Usage: rollback.ps1 -Version <v>
param([string]$Version, [string]$Python)
. (Join-Path $PSScriptRoot "_common.ps1")

if (-not $Version) { throw "usage: rollback.ps1 -Version <version>" }
$py = Resolve-Python $Python
Require-Python $py
$wheel = Get-WheelPath $Version
Write-Host "Rolling back to: $(Split-Path $wheel -Leaf)"
& $py -m pip install --no-index --no-deps --force-reinstall $wheel
if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }
Write-Host "Restored:"; Show-InstalledVersion $py