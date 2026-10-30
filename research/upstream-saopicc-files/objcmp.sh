#!/bin/bash
# Compare the object code of Gridder.c before and after the declaration fix.
set -u
B=~/Build/tmp/20261030-saopicc
V=$B/venv-kmsfix
PYINC=$($V/bin/python -c "import sysconfig; print(sysconfig.get_paths()['include'])")
NPINC=$($V/bin/python -c "import numpy; print(numpy.get_include())")
mkdir -p $B/objcmp; cd $B/objcmp
git -C $B/killMS show master:killMS/Gridder/Gridder.c > before.c
git -C $B/killMS show gcc15-incompatible-pointer-types:killMS/Gridder/Gridder.c > after.c
cp $B/killMS/killMS/Gridder/Gridder.h $B/killMS/killMS/Gridder/arrayobject.h . 2>/dev/null || cp $B/killMS/killMS/Gridder/*.h .
FL="-I$PYINC -I$NPINC -I$NPINC/numpy -O3 -DNDEBUG -fopenmp -std=c99 -ffast-math -fPIC"
gcc $FL -c before.c -o before.o 2> before.err; echo "before (default flags) rc=$?"; grep -c "error:" before.err
gcc $FL -Wno-error=incompatible-pointer-types -c before.c -o before.o 2>/dev/null; echo "before (workaround) rc=$?"
gcc $FL -c after.c -o after.o 2> after.err; echo "after (default flags) rc=$?"; grep -c "error:" after.err
objdump -d --no-show-raw-insn before.o | tail -n +4 > before.dis
objdump -d --no-show-raw-insn after.o | tail -n +4 > after.dis
cmp before.dis after.dis && echo "disassembly identical"
