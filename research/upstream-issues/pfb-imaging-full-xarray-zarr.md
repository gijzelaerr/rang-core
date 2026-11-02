# pfb-imaging: the [full] closure pairs xarray >= 2026.4 with zarr < 3

Repository: ratt-ru/pfb-imaging. Status: **filed 2026-11-02 (U4), https://github.com/ratt-ru/pfb-imaging/issues/390**. Found by DF5-O (D3), reproduced by U4 on
0.0.11 in a fresh uv venv
([../u4-upstream-files/pfb_repro_zarr.py](../u4-upstream-files/pfb_repro_zarr.py); `pfb init` on
the DF5-O field: `outputs/u4-20261102-01/logs/pfb-init-closure.log`, then exit 0 with
`xarray<2026.4`). On `main` 4cbbf625, `uv pip compile --extra full` resolves the same pair.
No duplicate; #334 is the dask-ms 0.3.0 pre-release notice.

<!-- issue-title: pip install pfb-imaging[full] resolves xarray >= 2026.4 with zarr < 3, and writing a zarr store fails -->
<!-- issue-body -->
A fresh `uv pip install "pfb-imaging[full]"` (0.0.11, Python 3.12, 2026-11-02) resolves xarray 2026.9.0 with zarr 2.18.7, which dask-ms 0.2.32 holds below 3. xarray 2026.4 and later need zarr 3, so `pfb init` fails with:

```
File ".../xarray/backends/zarr.py", line 1951, in _get_open_params
    zarr_group = zarr.open_group(store, **open_kwargs)
TypeError: open_group() got an unexpected keyword argument 'zarr_format'
```

Without any measurement set, in the same environment:

```python
import numpy as np, xarray as xr
xr.Dataset({"a": ("x", np.arange(3.0))}).to_zarr("t.zarr", mode="w")
```

gives the same `TypeError`. After `uv pip install "xarray<2026.4"` (2026.2.0), `pfb init` and `pfb grid` complete on a simulated MS.

The extras on `main` (4cbbf625) resolve to the same pair: `uv pip compile --extra full pyproject.toml` gives xarray 2026.9.0 and zarr 2.18.7, and `core/deconv.py` and `core/hci.py` there still use `to_zarr`. `uv.lock` holds xarray 2025.6.1, so this only shows up for installs from PyPI.

An `xarray<2026.4` bound in the extra would keep these installs working until dask-ms moves to zarr 3.
<!-- /issue-body -->
