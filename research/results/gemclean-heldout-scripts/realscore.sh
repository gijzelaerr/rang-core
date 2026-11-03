W=/home/gijsm/Worktrees/rang/gemclean-heldout
D=/mnt/d/rang/outputs/20261103-gemclean-heldout/real
S=/home/gijsm/Build/tmp/20261103-gemclean-heldout/real
G=/mnt/c/Users/gijsm/AppData/Local/Temp/claude/gh
cd /tmp
py="$W/.venv/bin/python -I $W/examples/gemclean_heldout_real.py"
flock /home/gijsm/.rang-heavy.lock bash -c "
/usr/bin/time -f 'score %e s %M kB' $py score $D/prep2 $S/run $D/scores.json --job $*
"
J3=$(for j in "$@"; do case $j in *003*) echo $j;; esac; done)
[ -n "$J3" ] && flock /home/gijsm/.rang-heavy.lock /usr/bin/time -f 'compare %e s %M kB' $py compare $D/prep2 $S/run $D/compare-003.json $D/images --job $J3 --beam-arcsec 12.7 --mask-sigma 5 --compact-sigma 10
J1=$(for j in "$@"; do case $j in *001*) echo $j;; esac; done); [ -n "$J1" ] && flock /home/gijsm/.rang-heavy.lock /usr/bin/time -f "compare %e s %M kB" $py compare $D/prep2 $S/run $D/compare-001.json $D/images-001 --job $J1 --beam-arcsec 12.7 --mask-sigma 5 --compact-sigma 10
echo SCORE-REAL-DONE
