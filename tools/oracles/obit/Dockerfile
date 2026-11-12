# Obit (Bill Cotton, NRAO) built from source, for MFImage as a second imaging oracle
# next to WSClean (research/v5-obit.md, task V5).
#
#   docker build -t rang-obit:dc26694 tools/oracles/obit
#
# Only the C library and tasks (ObitSystem/Obit) and its Python module are built: no
# ObitView, ObitTalk or ObitSD, no plplot, no X. Third-party libraries come from
# Ubuntu, not Obit's bundled copies. -march=native as for rang-wsclean-native, so the
# image belongs to the host that built it. Obit reads only its own UV FITS table form
# ("AIPS UV" binary table), not random-groups UVFITS, so the MS is written through
# Obit's Python bindings (research/results/v5-obit-scripts/ms_to_obit.py).
FROM ubuntu:24.04 AS src
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gfortran git ca-certificates time pkg-config python3 python-is-python3 \
      libglib2.0-dev libfftw3-dev libgsl-dev libcfitsio-dev zlib1g-dev \
      libcurl4-openssl-dev libxmlrpc-core-c3-dev libxmlrpc-c++8-dev \
      libboost-dev libopenblas-dev liblapack-dev \
    && rm -rf /var/lib/apt/lists/*
ARG OBIT_COMMIT=dc2669429fdb5bfde2910f7f55e46e55df3ee204
RUN git clone https://github.com/bill-cotton/Obit /src/Obit \
    && git -C /src/Obit checkout -q "$OBIT_COMMIT" \
    && git -C /src/Obit rev-parse HEAD > /obit-commit.txt \
    && cd /src/Obit/ObitSystem/Obit \
    && ./configure --help > /obit-configure-help.txt

FROM src
ARG OBIT_ARCH="-march=native"
ARG OBIT_JOBS=8
COPY build.sh /build.sh
RUN OBIT_ARCH="$OBIT_ARCH" OBIT_JOBS="$OBIT_JOBS" sh /build.sh
# Obit's Python 3 module (pregenerated SWIG wrapper) and python-casacore.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3-dev python3-numpy python3-setuptools python3-pip python3-six \
    && rm -rf /var/lib/apt/lists/*
COPY build_py.sh /build_py.sh
RUN sh /build_py.sh
ENV OBIT=/src/Obit/ObitSystem/Obit \
    PATH=/src/Obit/ObitSystem/Obit/bin:$PATH \
    PYTHONPATH=/src/Obit/ObitSystem/Obit/python \
    LD_LIBRARY_PATH=/src/Obit/ObitSystem/Obit/lib
