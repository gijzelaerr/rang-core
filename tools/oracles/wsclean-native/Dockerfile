# WSClean built from source for the build host's CPU (research/gemclean-speed.md):
# the KERN package in rang-o-casa is a portable build whose gridder has no
# instruction wider than SSE2, which does not match a local GeMClean build.
#
#   docker build -t rang-wsclean-native:3.7 tools/oracles/wsclean-native
#
# -march=native binds the image to the host that built it. It runs no IDG and no
# EveryBeam. casacore comes from KERN, as for the packaged WSClean; Ubuntu's 3.5
# does not compile as C++20.
FROM ubuntu:24.04
ARG KERN_PPA=ppa:kernsuite/kern-10
RUN apt-get update && apt-get install -y --no-install-recommends \
      software-properties-common gpg-agent ca-certificates \
    && add-apt-repository -y "$KERN_PPA" && apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential cmake git time pkg-config python3 python3-dev pybind11-dev \
      casacore-dev=3.7.1-1kern1 libfftw3-dev libgsl-dev libhdf5-dev libcfitsio-dev \
      liblapack-dev libblas-dev libopenmpi-dev libboost-filesystem-dev \
      libboost-program-options-dev libboost-system-dev libboost-date-time-dev libboost-test-dev
ARG WSCLEAN_TAG=v3.7
RUN git clone --depth 1 --branch "$WSCLEAN_TAG" --recurse-submodules --shallow-submodules \
      https://gitlab.com/aroffringa/wsclean.git /src/wsclean \
    && git -C /src/wsclean rev-parse HEAD > /wsclean-commit.txt \
    && cmake -S /src/wsclean -B /src/build -DCMAKE_BUILD_TYPE=Release -DPORTABLE=OFF \
    && cmake --build /src/build -j "$(nproc)" --target wsclean \
    && install /src/build/wsclean /usr/local/bin/wsclean \
    && cp /src/build/CMakeCache.txt /wsclean-cmakecache.txt \
    && rm -rf /src
