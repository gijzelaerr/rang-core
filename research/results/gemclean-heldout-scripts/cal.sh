W=/home/gijsm/Worktrees/rang/gemclean-heldout
R=/mnt/d/rang/outputs/20261103-gemclean-heldout/real
Z=/mnt/d/rang/data/eso137-pilot/ESO137/ms1_target.zarr
cd /tmp
py="nice -n 5 $W/.venv/bin/python -I $W/examples/gemclean_heldout_real.py"
/usr/bin/time -f "calibrate %e s %M kB" $py calibrate $Z $R/gains.npz $R/cal.ms
echo CAL-DONE
