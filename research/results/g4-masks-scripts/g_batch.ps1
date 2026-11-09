# g_batch.ps1 BIN TAG RUN... : GeMClean runs of research/g4-masks.md natively, each under
# tools/heavy_lock.py.
param([Parameter(Mandatory = $true)][string]$Bin, [Parameter(Mandatory = $true)][string]$Tag,
      [Parameter(ValueFromRemainingArguments = $true)][string[]]$Runs)
$W = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$py = Join-Path $W '.venv\Scripts\python.exe'
foreach ($r in $Runs) {
    & $py (Join-Path $W 'tools\heavy_lock.py') run -- $py (Join-Path $PSScriptRoot 'runs.py') g $Bin $Tag $r
}
