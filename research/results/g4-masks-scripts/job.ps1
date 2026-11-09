# job.ps1 LOG COMMAND... : run COMMAND under tools/heavy_lock.py, all output to LOG, with START,
# END, the exit code and the wall time written into LOG, so a restart leaves a readable record.
param([Parameter(Mandatory = $true)][string]$Log,
      [Parameter(ValueFromRemainingArguments = $true)][string[]]$Cmd)
$W = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$py = Join-Path $W '.venv\Scripts\python.exe'
$t = Get-Date
"START $($t.ToString('s')) pid $PID :: $($Cmd -join ' ')" | Set-Content $Log
& $py (Join-Path $W 'tools\heavy_lock.py') run -- @Cmd *>> $Log
$rc = $LASTEXITCODE
$e = Get-Date
"END $($e.ToString('s')) rc=$rc wall=$([math]::Round(($e - $t).TotalSeconds, 1))s" | Add-Content $Log
exit $rc
