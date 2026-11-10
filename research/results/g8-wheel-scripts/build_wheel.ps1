# build_wheel.ps1 TAG CPU LTO : a Windows wheel of this worktree as CI builds it (research/g8-wheel.md
# section 2): maturin 1.16.0 (the .venv's), rustc 1.93.1, `maturin build --release --locked`,
# RUSTFLAGS="-C target-cpu=CPU" (x86-64 for WH and WF, x86-64-v3 for WV3), LTO thin (the profile)
# or fat (CARGO_PROFILE_RELEASE_LTO=fat, WF), its own target dir; under the heavy lock. Then a fresh
# uv venv (Python 3.14) with the wheel at D:\rang\outputs\g8-20261110-01\venvs\TAG. Provenance and
# build wall in wheels\TAG\provenance.txt.
param(
    [Parameter(Mandatory = $true)][string]$Tag,
    [Parameter(Mandatory = $true)][string]$Cpu,
    [Parameter(Mandatory = $true)][string]$Lto
)
$ErrorActionPreference = 'Stop'
$W = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$py = Join-Path $W '.venv\Scripts\python.exe'
$O = 'D:\rang\outputs\g8-20261110-01'
$dist = Join-Path $O "wheels\$Tag"
$target = Join-Path $O "target-$Tag"
New-Item -ItemType Directory -Force $dist | Out-Null
$env:RUSTUP_TOOLCHAIN = '1.93.1'
$env:RUSTFLAGS = "-C target-cpu=$Cpu"
$env:CARGO_TARGET_DIR = $target
if ($Lto -eq 'fat') { $env:CARGO_PROFILE_RELEASE_LTO = 'fat' } else { Remove-Item Env:CARGO_PROFILE_RELEASE_LTO -ErrorAction SilentlyContinue }
$t0 = Get-Date
Push-Location $W
try {
    & $py (Join-Path $W 'tools\heavy_lock.py') run -- $py (Join-Path $PSScriptRoot 'timed.py') (Join-Path $dist 'build-wall.txt') $py -m maturin build --release --locked --out $dist
    if ($LASTEXITCODE -ne 0) { throw "maturin build failed ($LASTEXITCODE)" }
} finally { Pop-Location }
$secs = [double]((Get-Content (Join-Path $dist 'build-wall.txt')).Split(' ')[0])
Remove-Item Env:RUSTFLAGS, Env:CARGO_TARGET_DIR -ErrorAction SilentlyContinue
Remove-Item Env:CARGO_PROFILE_RELEASE_LTO -ErrorAction SilentlyContinue
$whl = Get-ChildItem $dist -Filter *.whl | Select-Object -First 1
$venv = Join-Path $O "venvs\$Tag"
if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
uv venv -q -p 3.14 $venv
uv pip install -q --python (Join-Path $venv 'Scripts\python.exe') $whl.FullName
if ($LASTEXITCODE -ne 0) { throw "install failed" }
$commit = git -C $W rev-parse HEAD
$dirty = (git -C $W status --porcelain | Measure-Object -Line).Lines
$sha = (Get-FileHash $whl.FullName -Algorithm SHA256).Hash.ToLower()
$mat = & $py -m maturin --version
"$commit $dirty dirty files; $mat; rustc 1.93.1; RUSTFLAGS=-C target-cpu=$Cpu; lto $Lto; build_wall_s $([math]::Round($secs,1))`n$sha  $($whl.Name)" | Set-Content (Join-Path $dist 'provenance.txt')
Remove-Item -Recurse -Force $target
Get-Content (Join-Path $dist 'provenance.txt')
