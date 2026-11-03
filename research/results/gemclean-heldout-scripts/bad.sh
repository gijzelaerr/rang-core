G=/mnt/c/Users/gijsm/AppData/Local/Temp/claude/gh
W=/home/gijsm/Worktrees/rang/gemclean-heldout
D=/mnt/d/rang/outputs/20261103-gemclean-heldout/real
S=/home/gijsm/Build/tmp/20261103-gemclean-heldout/real
python3 $G/fix12.py
cd /tmp
py="$W/.venv/bin/python -I $W/examples/gemclean_heldout_real.py"
flock /home/gijsm/.rang-heavy.lock bash -c "$py badbaselines $D/prep2 $S/cal2.ms $S/run/cal2-003-plain-model.fits $D/badbaselines.json --factor 5"
echo BAD-DONE
$py average $S/cal2.ms $S/cal3.ms --factor 1 --flag-baselines $D/badbaselines.json | tail -1 | cut -c1-300
flock /home/gijsm/.rang-heavy.lock bash -c "$py prep $S/cal3.ms $D/prep3 --size 4096 --scale 3"
MS=cal3 bash $G/real2.sh 0.003 fast
echo STAGE3-DONE
