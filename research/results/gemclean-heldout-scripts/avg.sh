G=/mnt/c/Users/gijsm/AppData/Local/Temp/claude/gh
W=/home/gijsm/Worktrees/rang/gemclean-heldout
D=/mnt/d/rang/outputs/20261103-gemclean-heldout/real
S=/home/gijsm/Build/tmp/20261103-gemclean-heldout/real
pgrep -f 'gh/real2.sh' | xargs -r kill
pgrep -f 'bash -c bash .*real2' | xargs -r kill
docker ps --format '{{.ID}} {{.Command}}' | grep 'no-fast-subminor\|wsclean' | head
for c in $(docker ps -q --filter ancestor=rang-o-casa:6.7.6.14); do
  docker inspect $c --format '{{.Args}}' | grep -q 'cal.ms' && docker kill $c
done
pgrep -f 'real/run/cal-003' | xargs -r kill
python3 $G/fix10.py
cd /tmp
py="$W/.venv/bin/python -I $W/examples/gemclean_heldout_real.py"
rm -rf $S/cal.ms $S/run/cal-003-gem* $S/run/timing/cal-003-gem*  $S/run/cal-003-plain* $S/run/timing/cal-003-plain*
ls $S/run | head -30
/usr/bin/time -f "average %e s %M kB" nice -n 5 $py average $D/cal.ms $S/cal2.ms --factor 2 | tail -1 | cut -c1-300
cp -r $S/cal2.ms $D/cal2.ms
echo AVG-DONE
bash $G/real2.sh 0 dirty
flock /home/gijsm/.rang-heavy.lock bash -c "
/usr/bin/time -f 'prep %e s %M kB' $py prep $S/cal2.ms $D/prep2 --size 4096 --scale 3
/usr/bin/time -f 'dirtycheck %e s %M kB' $py dirtycheck $D/prep2 $S/run/cal2-dirty $D/dirtycheck2.json
"
bash $G/real2.sh 0.003 gem fast plain
bash $G/real2.sh 0.001 gem
echo REAL-ALL-DONE
