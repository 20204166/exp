# Verify a built wheel before installing it: no forbidden content, expected
# members, entry points present, and (when present) the SHA256SUMS entry.
param([string]$Version, [string]$Python)
. (Join-Path $PSScriptRoot "_common.ps1")

$py = Resolve-Python $Python
Require-Python $py
$wheel = Get-WheelPath $Version
Write-Host "Verifying: $wheel"
Invoke-Versioned $py "maintenance._release" @("verify-wheel", $wheel)

$sums = Join-Path (Get-PackageDir) "dist\SHA256SUMS"
if (Test-Path $sums) {
    $leaf = Split-Path $wheel -Leaf
    $line = Get-Content $sums | Where-Object { $_.EndsWith($leaf) } | Select-Object -First 1
    if ($line) {
        $expected = ($line -split "\s+")[0]
        $actual = & $py -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" $wheel
        if ($expected -ne $actual) { throw "SHA256 mismatch for $leaf" }
        Write-Host "SHA256SUMS OK"
    } else {
        Write-Host "note: no SHA256SUMS entry for $leaf"
    }
}