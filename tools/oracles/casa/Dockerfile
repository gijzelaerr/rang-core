# O-CASA oracle image (research/o-casa.md). A tool image: nothing in it is
# copied into rang. Ubuntu 24.04 (Noble) + KERN-10 debs (WSClean, AOFlagger,
# python-casacore, Ubuntu's casacore measures data) + CASA casatools/casatasks
# 6.7.6.14 from public PyPI in a Python 3.12 venv at /opt/casa.
FROM ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852

ENV DEBIAN_FRONTEND=noninteractive
ARG KERN_PPA=ppa:kernsuite/kern-10
RUN apt-get update \
 && apt-get install -y --no-install-recommends software-properties-common gpg-agent ca-certificates \
 && add-apt-repository -y "$KERN_PPA" \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      wsclean=3.7-1kern1 \
      aoflagger=3.5.0-1kern1 \
      python3-casacore=3.7.1-1kern2 \
      casacore-data=20250826-160001-5 \
      python3-numpy=1:1.26.4+ds-6ubuntu1 python3-numcodecs=0.12.1+ds-1build2 python3-scipy=1.11.4-6build1 python3.12-venv \
      libgomp1 libgfortran5 time \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /opt/casa-requirements.lock
RUN python3.12 -m venv /opt/casa \
 && /opt/casa/bin/pip install --isolated --no-cache-dir --index-url https://pypi.org/simple \
      -r /opt/casa-requirements.lock \
 && printf '%s\n' \
      'measurespath = "/usr/share/casacore/data"' \
      'measures_auto_update = False' \
      'data_auto_update = False' \
      'nologfile = False' \
      > "$(/opt/casa/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')/casasiteconfig.py" \
 && (dpkg-query -W -f '${Package}=${Version}\n' | sort > /opt/image-debs.txt) \
 && /opt/casa/bin/pip freeze --all > /opt/image-pip.txt

ENV OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 HOME=/tmp
WORKDIR /work
