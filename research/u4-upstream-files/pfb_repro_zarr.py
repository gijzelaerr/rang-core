# ruff: noqa
"""pfb-imaging [full] closure: xarray vs zarr. Usage: python -I pfb_repro_zarr.py <workdir>"""

import os
import sys
from importlib.metadata import version

os.chdir(sys.argv[1])
for p in ["pfb-imaging", "xarray", "zarr", "dask-ms", "numpy"]:
    print(p, version(p))
import numpy as np
import xarray as xr

ds = xr.Dataset({"a": ("x", np.arange(3.0))})
try:
    ds.to_zarr("t.zarr", mode="w")
    print("to_zarr OK", xr.open_zarr("t.zarr").a.values)
except Exception as e:
    print("to_zarr raised:", type(e).__name__, e)
