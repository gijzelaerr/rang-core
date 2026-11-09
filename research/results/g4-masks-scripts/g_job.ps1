# g_job.ps1 LOG BIN TAG RUN... : g_batch.ps1 with START, one RUN line (exit code, wall) per run
# and END in LOG, each run under tools/heavy_lock.py. research/g4-masks.md.
param([Parameter(Mandatory = $true)][string]$Log, [Parameter(Mandatory = $true)][string]$Bin,
      [Parameter(Mandatory = $true)][string]$Tag,
      [Parameter(ValueFromRemainingArguments = $true)][string[]]$Runs)
"START $((Get-Date).ToString('s')) pid $PID :: $Bin $Tag $($Runs -join ' ')" | Set-Content $Log
foreach ($r in $Runs) {
    $t = Get-Date
    & (Join-Path $PSScriptRoot 'g_batch.ps1') $Bin $Tag $r *>> $Log
    "RUN $r rc=$LASTEXITCODE wall=$([math]::Round(((Get-Date) - $t).TotalSeconds, 1))s $((Get-Date).ToString('s'))" | Add-Content $Log
}
"END $((Get-Date).ToString('s'))" | Add-Content $Log
