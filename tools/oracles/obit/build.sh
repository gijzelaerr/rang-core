#!/bin/sh
# Configure and build ObitSystem/Obit (library and tasks) against Ubuntu's libraries.
set -eu
cd /src/Obit/ObitSystem/Obit
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
