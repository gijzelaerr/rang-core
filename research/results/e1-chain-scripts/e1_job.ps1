# E1 job wrapper (research/e1-chain.md): runs one command from the worktree
# under tools/heavy_lock.py, appending START, the output and END with the exit
# code to the log, so a restarted coordinator can tell what finished.
# Usage: pwsh -File e1_job.ps1 <log> <command> [args...]
param([Parameter(Mandatory)][string]$Log, [Parameter(ValueFromRemainingArguments)][string[]]$Cmd)
$ErrorActionPreference = "Continue"
Set-Location C:\Users\gijsm\Worktrees\rang\fp-e1-chain
$env:PYTHONUTF8 = "1"
"START $(Get-Date -Format o) $($Cmd -join ' ')" | Out-File $Log -Append -Encoding utf8
& .venv\Scripts\python tools\heavy_lock.py run -- @Cmd *>> $Log
$rc = $LASTEXITCODE
"END $(Get-Date -Format o) rc=$rc" | Out-File $Log -Append -Encoding utf8
exit $rc
