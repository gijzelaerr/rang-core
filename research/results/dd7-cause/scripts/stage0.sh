#!/usr/bin/env bash
# after setup/deep/compose: G3, G4 (two lanes), G4 check, R64, stage 1
R=D:/rang/outputs/dd7-20261125; L=$R/scripts/lane.sh
until grep -q "^compose end .* rc=0" $R/times.log; do grep -q "rc=[1-9]" $R/times.log && exit 1; sleep 30; done
bash $L "prep|4|15|dd7.py prep $R" "real-P-4|4|15|dd7.py grid $R/real 4 $R/b/sky.npy $R/grid/real-P-4.json" "real-MF-64|4|15|dd7.py grid $R/real 64 $R/models/RM.npy $R/grid/real-MF-64.json --free" &
bash $L "real-MF-4|4|15|dd7.py grid $R/real 4 $R/models/RM.npy $R/grid/real-MF-4.json --free" &
wait
bash $L "g4|1|2|dd7.py g4 $R" "resid|4|15|dd7.py resid $R" "stats|4|15|dd7.py stats $R"
