# wait_end.ps1 LOG... : block until every LOG has an END line (checked every 60 s), then print
# each log's RUN and END lines. research/g4-masks.md.
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Logs)
while ($true) {
    $done = $Logs | Where-Object { (Test-Path $_) -and (Select-String -Path $_ -Pattern '^END ' -Quiet) }
    if (@($done).Count -eq $Logs.Count) { break }
    Start-Sleep 60
}
foreach ($l in $Logs) { "== $l"; Select-String -Path $l -Pattern '^(RUN|END)' | ForEach-Object Line }
