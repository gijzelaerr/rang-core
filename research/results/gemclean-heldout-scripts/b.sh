G=/mnt/c/Users/gijsm/AppData/Local/Temp/claude/gh
W=/home/gijsm/Worktrees/rang/gemclean-heldout
D=/mnt/d/rang/outputs/20261103-gemclean-heldout/real
S=/home/gijsm/Build/tmp/20261103-gemclean-heldout/real
MS=cal3 bash $G/real2.sh 0.003 gem plain
cd /tmp
py="$W/.venv/bin/python -I $W/examples/gemclean_heldout_real.py"
flock /home/gijsm/.rang-heavy.lock bash -c "$py score $D/prep3 $S/run $D/scores3.json --job cal3-003-gem cal3-003-fast cal3-003-plain"
flock /home/gijsm/.rang-heavy.lock $py compare $D/prep3 $S/run $D/compare3-003.json $D/images3 --job cal3-003-gem cal3-003-fast cal3-003-plain --beam-arcsec 12.7 --mask-sigma 5 --compact-sigma 10
echo B-DONE
