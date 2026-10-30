# DF5-O pfb-imaging oracle image (research/df5o-deconv-oracles.md). A tool
# image: nothing in it is copied into rang. Ubuntu 24.04 (Noble) with its
# Python 3.12 and a uv venv at /opt/pfb holding pfb-imaging[full] 0.0.11 and
# its closure from public PyPI, installed from requirements.lock with hashes
# (build-essential for the sdists in the closure: python-lzf, wget, ...)
# (pfb-imaging requires Python < 3.14, so it does not install on the host's
# 3.14). Run with --network none and `--backend native` (pfb's default
# `auto` backend may try to pull its own container).
FROM ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3.12 python3.12-venv python3.12-dev build-essential ca-certificates time libgomp1 \
 && rm -rf /var/lib/apt/lists/*

ARG UV_VERSION=0.12.23
COPY requirements.lock /opt/pfb-requirements.lock
RUN python3.12 -m venv /opt/uvboot \
 && /opt/uvboot/bin/pip install --isolated --no-cache-dir --index-url https://pypi.org/simple "uv==${UV_VERSION}" \
 && /opt/uvboot/bin/uv venv -p /usr/bin/python3.12 /opt/pfb \
 && /opt/uvboot/bin/uv pip install --no-cache --python /opt/pfb/bin/python --index-url https://pypi.org/simple \
      --require-hashes -r /opt/pfb-requirements.lock \
 && (dpkg-query -W -f '${Package}=${Version}\n' | sort > /opt/image-debs.txt) \
 && /opt/uvboot/bin/uv pip freeze --python /opt/pfb/bin/python > /opt/image-pip.txt

ENV PATH=/opt/pfb/bin:$PATH OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 NUMBA_NUM_THREADS=4 \
    HOME=/tmp RAY_USAGE_STATS_ENABLED=0 MPLBACKEND=Agg
WORKDIR /work
