#!/bin/bash
# The regression test's case (core/tests/gemclean_memory.rs) with a given binary.
B=$1; O=$2; mkdir -p $O
"$B" -name $O/g -size 256 256 -scale 2asec -weight briggs 0 -niter 100000 -mgain 0.9 \
  -auto-threshold 3 -auto-mask 5 -wgridder-accuracy 1e-4 -pol IQUV -join-polarizations \
  -channels-out 4 -join-channels -data-column DATA -no-update-model-required -memory-report -j 2 \
  D:/rang/outputs/gemclean-memory-20261115/regcase/case.ms > $O.out 2>&1
python -c "import json,sys; r=json.load(open('$O/g-report.json')); print(max(int(p['heap_peak_bytes']) for p in r['memory']['phases']), r['peak_memory_bytes'])"
(cd $O && sha256sum *.fits > ../$(basename $O).sha)
