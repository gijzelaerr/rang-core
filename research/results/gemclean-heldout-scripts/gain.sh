W=/home/gijsm/Worktrees/rang/gemclean-heldout
R=/mnt/d/rang/outputs/20261103-gemclean-heldout/real
Z=/mnt/d/rang/data/eso137-pilot/ESO137/ms1_target.zarr
cd /tmp
py="nice -n 5 $W/.venv/bin/python -I $W/examples/gemclean_heldout_real.py"
cat /mnt/c/Users/gijsm/AppData/Local/Temp/claude/gh/fetch.log | tail -1
/usr/bin/time -f "gainload %e s %M kB" $py gainload /mnt/d/rang/data/eso137-pilot/gains $Z $R/gains.npz
/usr/bin/time -f "gaincheck %e s %M kB" $py gaincheck $Z $R/gains.npz $R/gaincheck.json
