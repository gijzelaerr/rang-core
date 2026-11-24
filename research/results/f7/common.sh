# F7 chains on nash (research/f7-flagger.md): shared paths and the job wrapper.
# Sourced by the d*.sh chains; O (the run root) is set before sourcing.
source ~/.rang-env.sh
W=$HOME/Worktrees/rang/f7-draft
# Python with rang importable. Until a chain needs a kernel change it uses
# dl3-f6's venv (editable rang from ~/Worktrees/rang/dl3-f6/python; core/,
# src/ and python/ identical to f7-draft at 7588f74a); kernel arms set PY.
PY=${PY:-$HOME/Worktrees/rang/dl3-f6/.venv/bin/python}
F6=$HOME/rang-data/outputs/dl3-f6-20261120; D3=$HOME/rang-data/outputs/f7-d3-20261121
D7=$HOME/rang-data/outputs/f7-d7-20261122
R5=$HOME/rang-data/outputs/dl3-f5-20261119; D=$R5/d; C=$HOME/rang-data/outputs/dl2-data-20261119
SIF=$R5/images/rang-aflag-aoflagger_3.5.0.sif; FL=$D/outputs/f4-20261111-07-shards-target
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py run"
mkdir -p $O; cd $W
echo "$(date +%FT%T) chain $0 at $(git -C $W rev-parse --short HEAD), PY $PY" >> $O/chain.log
log(){ echo "$(date +%FT%T) $*" >> $O/chain.log; }
job(){ n=$1; s=$2; m=$3; shift 3; [ -f $O/$n.done ] && return 0; log "$n start"
  /usr/bin/time -f "wall %e s rss %M KB" -o $O/$n.time $LOCK --slots $s --mem $m -- nice -n 19 ionice -c3 env RAYON_NUM_THREADS=$s OMP_NUM_THREADS=$s MKL_NUM_THREADS=$s "$@" > $O/$n.log 2>&1 && touch $O/$n.done && log "$n done" || { log "$n FAILED"; return 1; }; }
