set -e
cd C:/Users/gijsm/Worktrees/rang/msv4-fields
export PYTHONPATH=C:/Users/gijsm/Worktrees/rang/msv4-fields/python RAYON_NUM_THREADS=2
R=D:/rang/outputs/msv4-fields-20261125
mkdir -p $R
echo "code $(git rev-parse --short HEAD)" > $R/steps-01.txt
for s in copy cli products fieldids; do t0=$(date +%s); C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe research/results/msv4-fields/msv4_fields.py $s $R > $R/$s-01.log 2>&1; echo "$s $(($(date +%s)-t0)) s" >> $R/steps-01.txt; done
C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe research/results/msv4-fields/msv4_fields.py check $R $R/receipt-01.json
