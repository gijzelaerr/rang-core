W=/home/gijsm/Worktrees/rang/gemclean-heldout
S=/home/gijsm/Build/tmp/20261103-gemclean-heldout/sim
py=$W/.venv/bin/python
cd $W
for ds in h1 h2 h3 h4; do
  for im in wsclean gemclean; do
    flock /home/gijsm/.rang-heavy.lock $py examples/gemclean_bench_compare.py score $S/prep/$ds $S/data/$ds.json $S/$im $S/scores/$im-$ds.json --jobs $(cd $S/$im; ls | grep "^$ds-.*-model.fits" | sed 's/-model.fits//')
  done
done
echo SCORE-DONE
