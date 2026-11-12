#!/bin/sh
# Build Obit's Python 3 module in place (ObitSystem/Obit/python) and add python-casacore.
set -eu
cd /src/Obit/ObitSystem/Obit/python
# Obit bundles six 1.12.0, whose six.moves importer needs find_module (gone in Python
# 3.12); use Ubuntu's python3-six (1.16) instead.
rm -f six.py
make setupdata.py > /obit-py.log 2>&1
python3 makesetup.py >> /obit-py.log 2>&1
python3 setup.py build_ext --inplace >> /obit-py.log 2>&1 || { tail -60 /obit-py.log; exit 1; }
find /src/Obit/ObitSystem/Obit/python -name "_Obit*.so" >> /obit-py.log || { tail -40 /obit-py.log; exit 1; }
pip install --break-system-packages --no-cache-dir python-casacore==3.7.1 astropy==6.1.7 >> /obit-py.log 2>&1
cd / && PYTHONPATH=/src/Obit/ObitSystem/Obit/python LD_LIBRARY_PATH=/src/Obit/ObitSystem/Obit/lib \
  python3 -c "import Obit, OSystem, UV, casacore.tables; print('Obit python ok')" >> /obit-py.log || { tail -40 /obit-py.log; exit 1; }
