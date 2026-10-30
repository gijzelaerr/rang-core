# A-FLAG oracle image (research/a-flag-aoflagger.md). A tool image: nothing in
# it is copied into rang. Ubuntu 24.04 (Noble) + the KERN-10 AOFlagger 3.5.0
# debs (the C++ library, the CLI and its Python module, which the deb installs
# as /usr/lib/aoflagger.cpython-312-x86_64-linux-gnu.so) and python-casacore
# 3.7.1, as research/ecosystem-survey.md section 5.4 proposes for DF0. Same
# base digest and deb versions as the O-CASA image (tools/oracles/casa/).
# Run with --network none; inputs come in as .npz arrays.
FROM ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852

ENV DEBIAN_FRONTEND=noninteractive
ARG KERN_PPA=ppa:kernsuite/kern-10
RUN apt-get update \
 && apt-get install -y --no-install-recommends software-properties-common gpg-agent ca-certificates \
 && add-apt-repository -y "$KERN_PPA" \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      aoflagger=3.5.0-1kern1 libaoflagger0=3.5.0-1kern1 \
      python3-casacore=3.7.1-1kern2 \
      python3-numpy=1:1.26.4+ds-6ubuntu1 \
      time \
 && rm -rf /var/lib/apt/lists/* \
 && (dpkg-query -W -f '${Package}=${Version}\n' | sort > /opt/image-debs.txt)

ENV PYTHONPATH=/usr/lib OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 HOME=/tmp
WORKDIR /work
