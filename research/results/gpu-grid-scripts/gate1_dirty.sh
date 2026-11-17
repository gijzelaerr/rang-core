#!/usr/bin/env bash
# Gate 1 amendment 9.3 (a): the dirty image (model none) of every sky in single precision, for its peak.
# GeMClean model of that sky (Gate 0 baseline). Usage: gate1.sh PARITY_EXE BUDGET [skies]
P=$1; B=$2; shift 2
SK=${*:-"s1 s2 s3 h1 h2 h3 h4"}
O=D:/rang/outputs/20261116-gpu-grid
mkdir -p $O/gate1
for sky in $SK; do
  case $sky in
    s1|s2|s3) MS=D:/rang/outputs/20261102-gemclean/bench/data/$sky.ms; N=2048;;
    h3) MS=D:/rang/outputs/20261103-gemclean-heldout/sim/data/h3.ms; N=4096;;
    *) MS=D:/rang/outputs/20261103-gemclean-heldout/sim/data/$sky.ms; N=2048;;
  esac
  for form in coarse; do
    if [ $form = coarse ]; then E=1e-4; PR=single; else E=1e-6; PR=double; fi
    nvidia-smi --query-gpu=memory.used --format=csv,noheader > $O/gate1/$sky-$form-dirty-b$B.gpu
    RAYON_NUM_THREADS=8 "$P" $MS $N 1.5 $E $PR - $B > $O/gate1/$sky-$form-dirty-b$B.json 2> $O/gate1/$sky-$form-dirty-b$B.err
    echo "$sky $form rc $? $(head -c 400 $O/gate1/$sky-$form-dirty-b$B.json | grep -o '"residual_rel": [^,]*, "residual_abs_ujy": [^,]*')"
  done
done
