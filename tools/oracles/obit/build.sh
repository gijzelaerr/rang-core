#!/bin/sh
# Configure and build ObitSystem/Obit (library and tasks) against Ubuntu's libraries.
set -eu
cd /src/Obit/ObitSystem/Obit
# Obit bug at dc26694: MFMakeResiduals (src/ObitDConCleanVisMF.c, lines 1088 and 1115) sets
# "dim[1] = dim[2] = dim[3] = dim[5]" with dim[MAXINFOELEMDIM = 5], an out-of-bounds read; the
# garbage size makes MFImage CLEAN segfault or abort (g_malloc0 of 2^64 - 1.75e9 bytes) at the
# first residual. All four trailing dimensions are meant to be 1 (dim was {4,1,1,1,1}).
F=src/ObitDConCleanVisMF.c
test "$(grep -c 'dim\[1\] = dim\[2\] = dim\[3\] = dim\[5\];' $F)" = 2
sed -i 's/dim\[1\] = dim\[2\] = dim\[3\] = dim\[5\];/dim[1] = dim[2] = dim[3] = dim[4] = 1;/' $F
test "$(grep -c 'dim\[5\]' $F)" = 0
./configure \
    --with-cfitsio=/usr --with-fftw3=/usr --with-gsl=/usr --with-zlib=/usr \
    --with-xmlrpc=/usr --without-plplot --without-pgplot --without-python \
    --without-wvr --without-x \
    > /obit-configure.log 2>&1 || { tail -60 /obit-configure.log; exit 1; }
# configure ignores CFLAGS and writes "-g -O3 -fPIC -msse" into every Makefile. Replace
# -msse there with OBIT_ARCH (-march=native, as for rang-wsclean-native), keeping each
# Makefile's own extra flags (tasks add -DFASTOBITMEM), which a CFLAGS= on the make
# command line would drop.
ARCH="${OBIT_ARCH:--march=native}"
find . -name Makefile -exec grep -l -e "-fPIC -msse" {} + > /obit-patched-makefiles.txt
xargs sed -i "s/-O3 -fPIC -msse/-O3 $ARCH -fPIC/" < /obit-patched-makefiles.txt
# The top-level targets have no dependencies on each other, so a parallel top-level make
# builds the tasks before the library: run them in order, parallel inside each.
# pythonupdate is left to build_py.sh.
: > /obit-make.log
for t in versionupdate cfitsioupdate xmlrpcupdate srcupdate libupdate taskupdate; do
    if ! make -j"${OBIT_JOBS:-$(nproc)}" "$t" >> /obit-make.log 2>&1; then
        echo "target $t failed"
        grep -n -E "error:|Error [0-9]|undefined reference|No such|not found" /obit-make.log | head -60
        exit 1
    fi
done
cp config.log /obit-config.log
ls bin > /obit-tasks.txt
test -x bin/MFImage
rm -rf /src/Obit/.git
