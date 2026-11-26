set -e
cd C:/Users/gijsm/Worktrees/rang/msv4-cli
export PYTHONPATH=C:/Users/gijsm/Worktrees/rang/msv4-cli/python RAYON_NUM_THREADS=2
for s in copy cli kill refuse products; do t0=$(date +%s); C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe research/results/msv4-cli/msv4_cli.py $s D:/rang/outputs/msv4-cli-20261125 > D:/rang/outputs/msv4-cli-20261125/$s-01.log 2>&1; echo "$s $(($(date +%s)-t0)) s" >> D:/rang/outputs/msv4-cli-20261125/steps-01.txt; done
