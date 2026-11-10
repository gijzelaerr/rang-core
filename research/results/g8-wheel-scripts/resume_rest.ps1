# resume_rest.ps1: plan j1 (resumes: runs with timing.json are kept), then the Linux builds and runs
# (research/g8-wheel.md). Started detached; START/END/rc in runs.log and the status file.
$S = $PSScriptRoot
$W = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $S))
$py = Join-Path $W '.venv\Scripts\python.exe'
$O = 'D:\rang\outputs\g8-20261110-01'
$st = 'C:\Users\gijsm\Github\rang\outputs\status\fp-g8.md'
function Log($m) { "- $(Get-Date -Format s) $m" | Add-Content $st; "$(Get-Date -Format s) $m" | Add-Content "$O\runs.log" }
Log "resume START (plan j1, then Linux)"
& $py "$S\g8_run.py" plan j1 *>> "$O\plan-j1.out"
Log "plan j1 rc=$LASTEXITCODE"
& $py (Join-Path $W 'tools\heavy_lock.py') run -- wsl -e bash /mnt/c/Users/gijsm/Worktrees/rang/fp-g8-wheel/research/results/g8-wheel-scripts/build_linux.sh ed836ec /mnt/d/rang/outputs/g8-20261110-01/bin/src-ed836ec.tar *>> "$O\build-linux.log"
Log "linux builds rc=$LASTEXITCODE"
foreach ($p in @(('SBL','s1-def'),('WHL','s1-def'),('SBL','d1c1-def'),('WHL','d1c1-def'))) {
    if (Test-Path "$O\identity\$($p[0])\$($p[1])\result.json") { continue }
    & $py (Join-Path $W 'tools\heavy_lock.py') run -- $py "$S\g8_run.py" ident $p[0] $p[1] *>> "$O\runs-ident.out"
    Log "ident $($p[0]) $($p[1]) rc=$LASTEXITCODE"
}
foreach ($plan in 'lx16','lx1') {
    & $py "$S\g8_run.py" plan $plan *>> "$O\plan-$plan.out"
    Log "plan $plan rc=$LASTEXITCODE"
}
$whl = (Get-ChildItem "$O\wheels\WHL" -Filter *.whl | Select-Object -First 1).Name
& $py (Join-Path $W 'tools\heavy_lock.py') run -- wsl -e bash -c "rm -rf ~/Build/tmp/20261110-g8-wheeltest && cd /mnt/c/Users/gijsm/Worktrees/rang/fp-g8-wheel && python3 tools/wheel/test.py /mnt/d/rang/outputs/g8-20261110-01/wheels/WHL/$whl ~/Build/tmp/20261110-g8-wheeltest --python 3.14; rc=`$?; mkdir -p /mnt/d/rang/outputs/g8-20261110-01/wheeltest-linux; cp ~/Build/tmp/20261110-g8-wheeltest/*.log ~/Build/tmp/20261110-g8-wheeltest/timings.tsv /mnt/d/rang/outputs/g8-20261110-01/wheeltest-linux/; exit `$rc" *>> "$O\wheeltest-linux.out"
Log "wheel test Linux rc=$LASTEXITCODE"
$wh = (Get-ChildItem "$O\wheels\WH" -Filter *.whl | Select-Object -First 1).FullName
if (Test-Path "$O\wheeltest-windows") { Remove-Item -Recurse -Force "$O\wheeltest-windows" }
& $py (Join-Path $W 'tools\heavy_lock.py') run -- $py (Join-Path $W 'tools\wheel\test.py') $wh "$O\wheeltest-windows" --python 3.14 *>> "$O\wheeltest-windows.out"
Log "wheel test Windows rc=$LASTEXITCODE"
Log "resume END"
