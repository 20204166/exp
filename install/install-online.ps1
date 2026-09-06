# Standalone online installer. Run from any folder:
# irm https://raw.githubusercontent.com/20204166/exp/main/install/install-online.ps1 | iex
param([switch]$System)
$ErrorActionPreference = "Stop"
$base = "https://raw.githubusercontent.com/20204166/exp/main/dist"
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("system-analyzer-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    $sumsPath = Join-Path $tmp "SHA256SUMS"
    Invoke-WebRequest "$base/SHA256SUMS" -OutFile $sumsPath
    $line = Get-Content $sumsPath | Where-Object { $_.Trim() } | Select-Object -Last 1
    $parts = $line -split "\s+"; $expected = $parts[0]; $wheel = $parts[1]
    $wheelPath = Join-Path $tmp $wheel
    Invoke-WebRequest "$base/$wheel" -OutFile $wheelPath
    $actual = (Get-FileHash $wheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "Wheel checksum mismatch" }

    $py = $null
    foreach ($candidate in @(@("py", "-3.13"), @("py", "-3.12"), @("py", "-3.11"), @("py", "-3.10"), @("python3"), @("python"))) {
        try { & $candidate -c "import sys; assert sys.version_info >= (3,10)" 2>$null; if ($LASTEXITCODE -eq 0) { $py = $candidate; break } } catch {}
    }
    if (-not $py) { throw "System Analyzer requires Python 3.10 or newer." }
    $pipArgs = @("-m", "pip", "install")
    if (-not $System) { $pipArgs += "--user" }
    $pipArgs += @("--break-system-packages", $wheelPath)
    & $py @pipArgs
    if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }
    $bin = & $py -c "import os,sysconfig;print(sysconfig.get_path('scripts', scheme='nt_user' if os.name=='nt' else 'posix_user'))"
    Write-Host "Installed $wheel. Console scripts: $bin"
    Write-Host "Add this directory to PATH if needed, then run: system-analyzer"
} finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
