#!/usr/bin/env bash
# U5 casa: wheel import and metadata checks (run in WSL Ubuntu 26.04, 2026-11-12).
# S = site-packages of a uv venv (Python 3.12) holding casatools 6.7.6.14 manylinux_2_34.
set -u
D=/mnt/d/rang/scratch/u5/casa
uv venv -q -p 3.12 $D/venv312
uv pip install -q -p $D/venv312/bin/python --index-url https://pypi.org/simple \
  casatools==6.7.6.14 casatasks==6.7.6.14 casaconfig            # picks manylinux_2_34 here
uv venv -q -p 3.12 $D/venv228
uv pip install -q -p $D/venv228/bin/python --python-platform x86_64-manylinux_2_28 \
  --index-url https://pypi.org/simple casatools==6.7.6.14 casatasks==6.7.6.14 casaconfig six
S=$D/venv312/lib/python3.12/site-packages
grep -E '^(License|Classifier: License|Requires-Python|Classifier: Programming Language :: Python ::)' \
  $S/casatools-6.7.6.14.dist-info/METADATA $S/casatasks-6.7.6.14.dist-info/METADATA
$D/venv312/bin/python -I -c 'import casatools'                 # Ubuntu 26.04: OPENSSL_3.0.1 not found
objdump -T $S/casatools/__casac__/lib/libssl.so.3 | grep UND | grep -E 'OPENSSL_3\.(0\.1|2\.0)'
objdump -T $S/casatools/__casac__/lib/libldap.so.2 | grep UND | grep md2
# Ubuntu 24.04 (rang-o-casa image = ubuntu:24.04 + python3.12; its own casatools is the 2_28 wheel)
docker run --rm -v $S:/sp:ro rang-o-casa:6.7.6.14 bash -c '
  openssl version
  /opt/casa/bin/python -I -c "import sys; sys.path.insert(0, \"/sp\"); import casatools"
  LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libssl.so.3 /opt/casa/bin/python -I -c "import sys; sys.path.insert(0, \"/sp\"); import casatools"'
