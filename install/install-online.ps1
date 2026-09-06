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

    function Test-VenvPython {
        param([object]$Py)
        $script = "import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)"
        & $Py -c $script 2>$null
        return ($LASTEXITCODE -eq 0)
    }

    $py = $null
    $base = $null
    foreach ($candidate in @(@("py", "-3.13"), @("py", "-3.12"), @("py", "-3.11"), @("py", "-3.10"), @("python3"), @("python"))) {
        try {
            & $candidate -c "import sys; assert sys.version_info >= (3,10)" 2>$null
            if ($LASTEXITCODE -ne 0) { continue }
            if (-not (Test-VenvPython $candidate)) { $py = $candidate; break }
            if (-not $base) { $base = $candidate }
        } catch {}
    }
    # Every candidate was a venv: fall back to its base interpreter so a
    # per-user install works even while a venv is active.
    if (-not $py -and $base) {
        $basePy = & $base -c "import sys; print(sys._base_executable)" 2>$null
        if ($basePy -and (Test-Path $basePy) -and -not (Test-VenvPython $basePy)) {
            $py = @($basePy)
        }
    }
    if (-not $py) {
        throw "System Analyzer requires Python 3.10 or newer. Deactivate any active virtual environment (or run outside it) and retry."
    }
    if (Test-VenvPython $py) { throw "Cannot install: '$($py -join ' ')' is inside a virtual environment (pip disables '--user' inside venvs). Deactivate the venv and retry." }
    $pipArgs = @("-m", "pip", "install")
    if (-not $System) { $pipArgs += "--user" }
    $pipArgs += @("--break-system-packages", $wheelPath)
    & $py @pipArgs
    if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }
    if ($System) {
        $launcherCmd = Get-Command system-analyzer -ErrorAction SilentlyContinue
        if ($launcherCmd) {
            $launcherPath = $launcherCmd.Source
            if (-not $launcherPath) { $launcherPath = $launcherCmd.Path }
            $bin = Split-Path $launcherPath -Parent
        } else {
            $scheme = if ($env:OS -eq "Windows_NT") { "nt" } else { "posix_prefix" }
            $bin = & $py -c "import sysconfig;print(sysconfig.get_path('scripts', scheme='$scheme'))"
        }
    } else {
        $scheme = if ($env:OS -eq "Windows_NT") { "nt_user" } else { "posix_user" }
        $bin = & $py -c "import sysconfig;print(sysconfig.get_path('scripts', scheme='$scheme'))"
    }
    Write-Host "Installed $wheel. Console scripts: $bin"
    Write-Host "Add this directory to PATH if needed, then run: system-analyzer"
} finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
