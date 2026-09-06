# Build the System Analyzer wheel into dist/. Building NEVER installs it.
# Offline: uses the already-present setuptools (no build isolation / no network).
# Auto-bumps the version and syncs dist/SHA256SUMS (maintenance._release).
param([string]$Python, [string]$Bump = "auto")
. (Join-Path $PSScriptRoot "_common.ps1")

$py = Resolve-Python $Python
Require-Python $py
$here = Get-PackageDir

try {
    Write-Host "Preparing build inputs and version..."
    Invoke-Versioned $py "maintenance._release" @("prepare-build", "--package-dir", $here, "--bump", $Bump)

    Write-Host "Building system-analyzer wheel from: $here"
    & $py -m pip wheel $here --no-deps --no-build-isolation -w (Join-Path $here "dist")
    if ($LASTEXITCODE -ne 0) { throw "pip wheel failed (exit $LASTEXITCODE)" }

    Invoke-Versioned $py "maintenance._release" @("sync-artifacts", "--package-dir", $here)
} finally {
    Remove-Item -Recurse -Force (Join-Path $here "build") -ErrorAction SilentlyContinue
    Get-ChildItem $here -Filter "*.egg-info" -Directory |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

Get-ChildItem (Join-Path $here "dist\system_analyzer-*.whl") | Select-Object -ExpandProperty Name
Write-Host "Building does not install. Run install.ps1 to install explicitly."