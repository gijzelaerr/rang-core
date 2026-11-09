# build.ps1 TAG : build the gemclean profile binary of this worktree natively (rustc 1.93, as G5
# and G9 built in WSL) under the heavy lock, and copy it to D:\rang\outputs\g4-bin\gemclean-TAG.exe
# with its provenance (commit, dirty files, sha256). research/g4-masks.md.
param([Parameter(Mandatory = $true)][string]$Tag)
$ErrorActionPreference = 'Stop'
$W = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$py = Join-Path $W '.venv\Scripts\python.exe'
Push-Location (Join-Path $W 'core')
try {
    & $py (Join-Path $W 'tools\heavy_lock.py') run -- cargo +1.93 build --profile gemclean --bin gemclean
    if ($LASTEXITCODE -ne 0) { throw "cargo build failed ($LASTEXITCODE)" }
} finally { Pop-Location }
$O = 'D:\rang\outputs\g4-bin'
New-Item -ItemType Directory -Force $O | Out-Null
$exe = Join-Path $O "gemclean-$Tag.exe"
Copy-Item (Join-Path $W 'core\target\gemclean\gemclean.exe') $exe -Force
$commit = git -C $W rev-parse HEAD
$dirty = (git -C $W status --porcelain | Measure-Object -Line).Lines
$sha = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
"$commit $dirty dirty files`n$sha  gemclean-$Tag.exe" | Set-Content "$exe.provenance"
Get-Content "$exe.provenance"
