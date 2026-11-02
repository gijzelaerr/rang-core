# E6 C++ casacore oracle image (research/e6-table-writer-final.md). A tool
# image: nothing in it is copied into rang. Ubuntu 24.04 (Noble) + the KERN-10
# casacore 3.7.1 development debs and g++, same base digest as the A-FLAG and
# O-CASA images. python-casacore has no TiledDataStManAccessor and no storage
# option, so the tables it cannot make (TiledDataStMan hypercubes,
# TiledCellStMan, MultiFile tables with large logical files, big ISM string
# arrays) are made by a small C++ program (oracle.cc) compiled at build time.
# Run with --network none.
FROM ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852

ENV DEBIAN_FRONTEND=noninteractive
ARG KERN_PPA=ppa:kernsuite/kern-10
RUN apt-get update \
 && apt-get install -y --no-install-recommends software-properties-common gpg-agent ca-certificates \
 && add-apt-repository -y "$KERN_PPA" \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      casacore-dev=3.7.1-1kern1 libcasa-tables8=3.7.1-1kern1 libcasa-casa8=3.7.1-1kern1 \
      g++ make time \
 && rm -rf /var/lib/apt/lists/* \
 && (dpkg-query -W -f '${Package}=${Version}\n' | sort > /opt/image-debs.txt)

COPY oracle.cc /opt/oracle/oracle.cc
RUN g++ -O1 -std=c++17 -o /opt/oracle/oracle /opt/oracle/oracle.cc \
      -I/usr/include/casacore -lcasa_tables -lcasa_casa \
 && (ldd /opt/oracle/oracle > /opt/oracle/ldd.txt)

ENV HOME=/tmp
WORKDIR /work
ENTRYPOINT ["/opt/oracle/oracle"]
