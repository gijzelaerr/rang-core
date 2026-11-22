#!/bin/bash
# gemclean-mem-32b (research/gemclean-mem-32b.md section 3), nash, one hold:
# build main (b1fa64a1) and arm V1/V2, then case I three ways side by side.
set -u
source ~/.rang-env.sh
O=~/rang-data/outputs/gemclean-mem-32b
I=~/rang-data/outputs/gemclean-mem-32-20261121/i.ms
W=~/Worktrees/rang/gemclean-mem-32b
log() { echo "$(date -u +%FT%TZ) $*" >> $O/run.log; }
cd $W
if [ ! -x $O/gemclean-main ]; then
  git diff --quiet core/src/gemclean/cli.rs || { log "worktree not at main"; exit 1; }
  cargo build -q --profile gemclean --bin gemclean --manifest-path core/Cargo.toml && cp core/target/gemclean/gemclean $O/gemclean-main || exit 1
  log "main built"
fi
if [ ! -x $O/gemclean-v ]; then
  cp $O/cli-arm.rs core/src/gemclean/cli.rs
  cargo build -q --profile gemclean --bin gemclean --manifest-path core/Cargo.toml && cp core/target/gemclean/gemclean $O/gemclean-v || exit 1
  git checkout core/src/gemclean/cli.rs
  log "arm built"
fi
A="-size 4096 4096 -scale 3asec -weight briggs 0.5 -niter 20000 -mgain 0.9 -auto-threshold 3.0 -auto-mask 5 -wgridder-accuracy 0.0001 -channels-out 8 -join-channels -fit-spectral-pol 2 -multiscale -average-channels 2 -data-column DATA -field 3 -no-update-model-required -j 4 -memory-report"
one() { # tag binary extra...
  local tag=$1 bin=$2; shift 2
  local o=$O/$tag; mkdir -p $o
  local s=$(date +%s)
  /usr/bin/time -v -o $o/time.txt $bin -name $o/image $A "$@" $I > $o/log.txt 2>&1
  log "$tag rc=$? $(( $(date +%s) - s )) s $(grep Maximum $o/time.txt)"
  (cd $o && sha256sum *.fits > fits.sha256 && rm -f *.fits)
  ls $o/*.tmp $o/*.spill 2>/dev/null | sed "s/^/left: /" >> $O/run.log
}
one ${1:-main1} $O/gemclean-main &
one ${2:-v1} $O/gemclean-v &
one ${3:-v2} $O/gemclean-v -reorder -temp-dir $O/${3:-v2} &
wait
log "pass done"
