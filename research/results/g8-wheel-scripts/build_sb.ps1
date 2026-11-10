# build_sb.ps1 TAG : the gemclean-profile source build (SB) of this worktree, natively (rustc 1.93),
# under the heavy lock, copied to D:\rang\outputs\g8-20261110-01\bin\gemclean-TAG.exe with its
# provenance (commit, dirty files under core/, sha256, build wall inside the lock).
# research/g8-wheel.md section 2.
param([Parameter(Mandatory = $true)][string]$Tag)
$ErrorActionPreference = 'Stop'
$W = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$py = Join-Path $W '.venv\Scripts\python.exe'
$O = 'D:\rang\outputs\g8-20261110-01\bin'
$wallFile = Join-Path $O "build-$Tag.wall"
Push-Location (Join-Path $W 'core')
try {
    & $py (Join-Path $W 'tools\heavy_lock.py') run -- $py (Join-Path $PSScriptRoot 'timed.py') $wallFile cargo +1.93 build --profile gemclean --bin gemclean
    if ($LASTEXITCODE -ne 0) { throw "cargo build failed ($LASTEXITCODE)" }
} finally { Pop-Location }
$secs = [double]((Get-Content $wallFile).Split(' ')[0])
$exe = Join-Path $O "gemclean-$Tag.exe"
Copy-Item (Join-Path $W 'core\target\gemclean\gemclean.exe') $exe -Force
$commit = git -C $W rev-parse HEAD
$dirty = (git -C $W status --porcelain -- core | Measure-Object -Line).Lines
$sha = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
"$commit $dirty dirty files under core/ build_wall_s $([math]::Round($secs,1))`n$sha  gemclean-$Tag.exe" | Set-Content "$exe.provenance"
Get-Content "$exe.provenance"
