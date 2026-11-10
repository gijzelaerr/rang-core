# side_jobs.ps1 : the untimed jobs of research/g7-defaults.md, each under the heavy lock (they
# interleave with a timing plan between its runs): GP's class B images on S1 and H3 (identity
# settings, RANG_WGRIDDER_PLANE_GROUP=1, default form), then the exact scoring of the -j 16
# repeat-1 models on the pilot.
$W = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$py = Join-Path $W '.venv\Scripts\python.exe'
$lock = Join-Path $W 'tools\heavy_lock.py'
$O = 'D:\rang\outputs\g7-20261109-01'
$bin = "$O\bin\gemclean-beam-c7ca268.exe"
$env:G7_KEEP = '1'
$env:PYTHONIOENCODING = 'utf-8'
foreach ($r in 's1', 'h3') {
    $env:RANG_WGRIDDER_PLANE_GROUP = '1'
    & $py $lock run -- $py (Join-Path $PSScriptRoot 'id_run.py') $bin gp1 $r def
    "gp1 $r rc=$LASTEXITCODE $((Get-Date).ToString('s'))"
}
Remove-Item Env:RANG_WGRIDDER_PLANE_GROUP
$R = "$O\runs"
New-Item -ItemType Directory -Force "$O\scores" | Out-Null
& $py $lock run -- $py (Join-Path $PSScriptRoot 'g7_score.py') "$O\scores\j16-r1.json" `
    "GD=$R\GD-j16-r1\g-model.fits" "GC=$R\GC-j16-r1\g-model.fits" "GB=$R\GB-j16-r1\g-model.fits" `
    "GT=$R\GT-j16-r1\g-model.fits" "GP=$R\GP-j16-r1\g-model.fits" "WN=$R\WN-j16-r1\w-model.fits" `
    "WM=$R\WM-j16-r1\w-model.fits" --check-dirty "$R\GD-j16-r1\g-dirty.fits"
"score rc=$LASTEXITCODE $((Get-Date).ToString('s'))"
