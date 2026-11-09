# id_job.ps1 LOG BIN TAG : gate A's identity set (research/g4-masks.md, section 3) for one binary,
# each run under tools/heavy_lock.py, START / RUN rc / END lines in LOG. Runs whose .sha256
# already exists for TAG are skipped (a restart resumes).
param([Parameter(Mandatory = $true)][string]$Log, [Parameter(Mandatory = $true)][string]$Bin,
      [Parameter(Mandatory = $true)][string]$Tag)
$W = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$py = Join-Path $W '.venv\Scripts\python.exe'
$out = if ($env:G4_ID_OUT) { $env:G4_ID_OUT } else { 'D:\rang\outputs\g4-20261109-02' }
$set = @()
foreach ($r in 's1', 's2', 's3', 'h1', 'h2', 'h3', 'h4', 'p256') { foreach ($f in 'def', 'coarse') { $set += , @($r, $f) } }
$set += , @('D1-C1', 'def'); $set += , @('D1-C3', 'def')
"START $((Get-Date).ToString('s')) pid $PID :: $Bin $Tag" | Add-Content $Log
foreach ($p in $set) {
    $name = "$($p[0])-$($p[1])"
    if (Test-Path (Join-Path $out "identity\$Tag\img\$name.sha256")) { "SKIP $name" | Add-Content $Log; continue }
    $t = Get-Date
    & $py (Join-Path $W 'tools\heavy_lock.py') run -- $py (Join-Path $PSScriptRoot 'id_run.py') $Bin $Tag $p[0] $p[1] *>> $Log
    "RUN $name rc=$LASTEXITCODE wall=$([math]::Round(((Get-Date) - $t).TotalSeconds, 1))s $((Get-Date).ToString('s'))" | Add-Content $Log
}
"END $((Get-Date).ToString('s'))" | Add-Content $Log
