"""The file formats of the tools the core replaces (research/dfio-formats.md).

- `caltable`: CASA calibration tables (G, B, K, T, Df), read into
  `CalTable` with the VisCal semantics, written through the core writer,
  and applied as CASA `applycal` applies them;
- `quartical_store`: QuartiCal's dask-ms zarr gain stores, read and
  written without zarr or dask-ms;
- `sky`: Tigger `.lsm.html` and ASCII, WSClean/Crystalball source lists,
  BBS (read), DDFacet DicoModel (read, restricted unpickler) and
  ClusterCat (`rang.lsm` is a compatibility module over it);
- `h5parm`: the losoto/DP3 H5parm subset (h5py, the `formats` extra);
- `killms`: killMS solution files;
- `flagversions`: CASA flag versions;
- `cli`: `rang-core formats check` and `convert`.

Each module was judged by its own tool (CASA, QuartiCal, Tigger,
africanus/Crystalball, WSClean, losoto, DP3, DDFacet, killMS). Modules are
imported on use, so that h5py stays optional.
"""

__all__ = [
    "caltable",
    "cli",
    "flagversions",
    "h5parm",
    "killms",
    "quartical_store",
    "sky",
]
