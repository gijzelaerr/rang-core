# runs_windows.ps1: the native runs of research/g8-wheel.md in order: identity (A0, A1, reported
# arms), start-up, then the timing plans j16 and j1. Each identity run under the heavy lock; the
# plans take the lock per run. Logged in runs.log and the status file. Skips identity runs whose
# result.json exists, so a restart resumes.
$S = $PSScriptRoot
$W = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $S))
$py = Join-Path $W '.venv\Scripts\python.exe'
$O = 'D:\rang\outputs\g8-20261110-01'
$st = 'C:\Users\gijsm\Github\rang\outputs\status\fp-g8.md'
function Log($m) { "- $(Get-Date -Format s) $m" | Add-Content $st; "$(Get-Date -Format s) $m" | Add-Content "$O\runs.log" }
Log "native runs START"
$ident = @(('SB0','s1-def'),('SB','s1-def'),('WH','s1-def'),('SB','s1-d6'),('WH','s1-d6'),('SB','d1c1-def'),('WH','d1c1-def'),('WV3','s1-def'),('WF','s1-def'))
foreach ($p in $ident) {
    if (Test-Path "$O\identity\$($p[0])\$($p[1])\result.json") { continue }
    & $py (Join-Path $W 'tools\heavy_lock.py') run -- $py "$S\g8_run.py" ident $p[0] $p[1] *>> "$O\runs-ident.out"
    Log "ident $($p[0]) $($p[1]) rc=$LASTEXITCODE"
}
foreach ($a in 'SB','WH') {
    & $py (Join-Path $W 'tools\heavy_lock.py') run -- $py "$S\g8_run.py" startup $a 10 *>> "$O\runs-startup.out"
    Log "startup $a rc=$LASTEXITCODE"
}
foreach ($plan in 'j16','j1') {
    & $py "$S\g8_run.py" plan $plan *>> "$O\plan-$plan.out"
    Log "plan $plan rc=$LASTEXITCODE"
}
Log "native runs END"
