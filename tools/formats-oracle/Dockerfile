# DF-IO formats oracle image (research/dfio-formats.md). A tool image: nothing
# in it is copied into rang. Ubuntu 24.04 (Noble, the O-CASA base digest) with
# Python 3.12 and four venvs from public PyPI, one per conflicting closure:
#   /opt/qc   QuartiCal 0.2.7 (dask-ms zarr gain stores, load_from apply)
#   /opt/sky  astro-tigger-lsm 1.8.0 (tigger-convert) and Crystalball 0.4.3
#   /opt/h5   losoto 2.7.1 and DP3 6.6.0 (the wheel bundles libDP3, casacore, HDF5)
#   /opt/ddf  DDFacet 1.0.0.0 and killMS 3.3.0 (MergeSols, DicoModel, ClusterCat)
# The resolved closures are written to /opt/<venv>.lock and copied to
# tools/formats-oracle/<venv>.lock after the build. Run with --network none.
# Build: docker build -t rang-formats-oracle:20261030 tools/formats-oracle
FROM ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates python3.12 python3.12-venv python3.12-dev \
      build-essential cmake pkg-config git libgomp1 time \
 && rm -rf /var/lib/apt/lists/*

ARG INDEX=https://pypi.org/simple
RUN python3.12 -m venv /opt/uv && /opt/uv/bin/pip install --no-cache-dir --index-url $INDEX uv==0.9.5
ENV UV_INDEX_URL=$INDEX UV_NO_CACHE=1

RUN /opt/uv/bin/uv venv -p /usr/bin/python3.12 /opt/qc \
 && /opt/uv/bin/uv pip install --python /opt/qc/bin/python quartical==0.2.7 \
 && /opt/uv/bin/uv pip freeze --python /opt/qc/bin/python > /opt/qc.lock

RUN /opt/uv/bin/uv venv -p /usr/bin/python3.12 /opt/sky \
 && /opt/uv/bin/uv pip install --python /opt/sky/bin/python astro-tigger-lsm==1.8.0 crystalball==0.4.3 \
 && /opt/uv/bin/uv pip freeze --python /opt/sky/bin/python > /opt/sky.lock

RUN /opt/uv/bin/uv venv -p /usr/bin/python3.12 /opt/h5 \
 && /opt/uv/bin/uv pip install --python /opt/h5/bin/python losoto==2.7.1 dp3==6.6.0 python-casacore==3.7.1 \
 && /opt/uv/bin/uv pip freeze --python /opt/h5/bin/python > /opt/h5.lock

RUN /opt/uv/bin/uv venv -p /usr/bin/python3.12 /opt/ddf \
 && CFLAGS=-Wno-error=incompatible-pointer-types /opt/uv/bin/uv pip install --python /opt/ddf/bin/python ddfacet==1.0.0.0 killms==3.3.0 \
 && /opt/uv/bin/uv pip freeze --python /opt/ddf/bin/python > /opt/ddf.lock

# DP3's wheel links the system GLib (missing in the first smoke run).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglib2.0-0t64 \
 && rm -rf /var/lib/apt/lists/* \
 && dpkg-query -W -f '${Package}=${Version}\n' | sort > /opt/image-debs.txt

ENV OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 HOME=/tmp NUMBA_CACHE_DIR=/tmp/numba
WORKDIR /work
