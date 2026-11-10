# builds_windows.ps1: SB, WH, WV3, WF of research/g8-wheel.md section 2, in order, each logged.
$ErrorActionPreference = 'Stop'
$S = $PSScriptRoot
$O = 'D:\rang\outputs\g8-20261110-01'
$st = 'C:\Users\gijsm\Github\rang\outputs\status\fp-g8.md'
$c = (git -C $S rev-parse --short HEAD)
function Log($m) { "- $(Get-Date -Format s) $m" | Add-Content $st; "$(Get-Date -Format s) $m" | Add-Content "$O\builds.log" }
Log "builds START (SB, WH, WV3, WF of $c)"
& "$S\build_sb.ps1" -Tag "sb-$c" *>> "$O\build-sb.log"; Log "SB done"
& "$S\build_wheel.ps1" -Tag WH -Cpu x86-64 -Lto thin *>> "$O\build-wh.log"; Log "WH done"
& "$S\build_wheel.ps1" -Tag WV3 -Cpu x86-64-v3 -Lto thin *>> "$O\build-wv3.log"; Log "WV3 done"
& "$S\build_wheel.ps1" -Tag WF -Cpu x86-64 -Lto fat *>> "$O\build-wf.log"; Log "WF done"
Log "builds END"
