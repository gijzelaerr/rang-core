"""killMS solution files (`killMS.<name>.sols.npz`; research/dfio-formats.md, F5).

killMS 3.3.0 (`kMS.py`) saves with `np.savez`: `Sols`, a record array of
solution intervals (`t0`, `t1` float64, `G` complex64 of shape
(nchan, nant, ndir, 2, 2), `Stats` float32 (nchan, nant, 4)), and
`StationNames`, `ClusterCat` and `SkyModel` (the direction catalogue,
`Name S200, ra, dec, SumI, Cluster`, DDFacet adds `l, m`), `SourceCatSub`,
`ModelName`, `MSName`, `MSNameTime0`, `FreqDomains` ((nchan, 2) Hz) and
`BeamTimes`. `MergeSols.py` joins files in frequency and adds
`MaskedSols`.

`write` stores no object arrays, so `np.load(allow_pickle=False)` reads the
core's files. `read` loads any killMS file; members that hold Python
objects are unpickled by `rang.formats.sky.RestrictedUnpickler` (NumPy
arrays and scalars only). Never use it on untrusted files.
"""

import io
import zipfile
from pathlib import Path

import numpy as np

from .sky import CLUSTERCAT_DTYPE, restricted_load


def sols_dtype(nchan, nant, ndir):
    return np.dtype(
        [
            ("t0", np.float64),
            ("t1", np.float64),
            ("G", np.complex64, (nchan, nant, ndir, 2, 2)),
            ("Stats", np.float32, (nchan, nant, 4)),
        ]
    )


def make_sols(t0, t1, gains, stats=None):
    """The `Sols` record array from interval edges and gains
    (time, chan, ant, dir, 2, 2)."""
    gains = np.asarray(gains)
    nt, nchan, nant, ndir = gains.shape[:4]
    sols = np.zeros(nt, sols_dtype(nchan, nant, ndir))
    sols["t0"], sols["t1"] = t0, t1
    sols["G"] = gains
    if stats is not None:
        sols["Stats"] = stats
    return sols.view(np.recarray)


def write(
    path,
    sols,
    station_names,
    cluster_cat,
    freq_domains,
    *,
    beam_times=None,
    ms_name="",
    ms_time0=0.0,
    model_name="",
    source_cat_sub=None,
):
    """A killMS solution file, as `kMS.py` saves one, without object arrays."""
    cluster_cat = np.asarray(cluster_cat)
    sub = (
        np.zeros(0, CLUSTERCAT_DTYPE)
        if source_cat_sub is None
        else np.asarray(source_cat_sub)
    )
    arrays = {
        "MSName": np.str_(ms_name),
        "MSNameTime0": np.float64(ms_time0),
        "Sols": np.asarray(sols),
        "StationNames": np.array([str(s) for s in station_names]),
        "SkyModel": cluster_cat,
        "ClusterCat": cluster_cat,
        "SourceCatSub": sub,
        "ModelName": np.str_(model_name),
        "FreqDomains": np.asarray(freq_domains, np.float64),
        "BeamTimes": np.asarray([] if beam_times is None else beam_times, np.float64),
    }
    for k, v in arrays.items():
        if np.asarray(v).dtype.hasobject:
            raise ValueError(f"{k} would need pickle")
    np.savez(path, **arrays)
    return Path(path)


def _member(data):
    stream = io.BytesIO(data)
    version = np.lib.format.read_magic(stream)
    if version == (1, 0):
        _, _, dtype = np.lib.format.read_array_header_1_0(stream)
    else:
        _, _, dtype = np.lib.format.read_array_header_2_0(stream)
    if dtype.hasobject:
        array = restricted_load(stream)
        if not isinstance(array, np.ndarray):
            raise ValueError("object member is not an array")
        return array
    stream.seek(0)
    return np.lib.format.read_array(stream, allow_pickle=False)


def read(path):
    """Every member of a killMS `.npz` (object members through the
    restricted unpickler); `Sols` as a record array."""
    out = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            key = name.removesuffix(".npy")
            out[key] = _member(z.read(name))
    if "Sols" in out:
        out["Sols"] = out["Sols"].view(np.recarray)
    return out


def normalise_to_antenna0(G):
    """`ClassMergeSols.NormMatrices`: per time, channel and direction, the
    unitary part U = u v of antenna 0's SVD; every antenna's G -> U^H G."""
    G = np.array(G)
    nt, nch, na, nd = G.shape[:4]
    for ich in range(nch):
        for it in range(nt):
            for d in range(nd):
                gt = G[it, ich, :, d]
                u, _, v = np.linalg.svd(gt[0])
                U = u @ v
                for a in range(na):
                    gt[a] = U.T.conj() @ gt[a]
    return G


def merge(files):
    """The merge `MergeSols.py` performs on killMS files (dicts from `read`)
    joined in frequency: sorted by central frequency, equal solution widths,
    one output channel per width, G normalised to antenna 0, `MaskedSols`
    (0 where a file filled the channel)."""
    files = sorted(files, key=lambda d: np.mean(d["FreqDomains"]))
    widths = [d["FreqDomains"][:, 1] - d["FreqDomains"][:, 0] for d in files]
    df = widths[0].ravel()[0]
    f0 = min(d["FreqDomains"][:, 0].min() for d in files)
    f1 = max(d["FreqDomains"][:, 1].max() for d in files)
    nout = (f1 - f0) / df
    if nout % 1:
        raise ValueError("solutions are not equally spaced in frequency")
    nout = int(nout)
    domains = np.zeros((nout, 2))
    domains[:, 0] = f0 + np.arange(nout) * df
    domains[:, 1] = f0 + df + np.arange(nout) * df
    s0 = files[0]["Sols"]
    nt, _, na, nd = s0.G.shape[:4]
    out = np.zeros(nt, sols_dtype(nout, na, nd)).view(np.recarray)
    out.t0, out.t1 = s0.t0, s0.t1
    mask = np.ones(out.G.shape, np.int16)
    for d in files:
        g = d["Sols"].G
        fmean = np.mean(d["FreqDomains"][0, :])
        i = np.where((fmean > domains[:, 0]) & (fmean < domains[:, 1]))[0][0]
        out.G[:, i : i + g.shape[1]] = g
        mask[:, i : i + g.shape[1]] = 0
    out.G[...] = normalise_to_antenna0(out.G)
    return {"Sols": out, "FreqDomains": domains, "MaskedSols": mask}


def summary(sols):
    s = sols["Sols"]
    return {
        "intervals": len(s),
        "g_shape": list(s.G.shape),
        "stations": [str(x) for x in sols.get("StationNames", [])],
        "directions": len(sols.get("ClusterCat", [])),
        "freq_domains": len(sols.get("FreqDomains", [])),
        "members": sorted(sols),
    }


__all__ = [
    "make_sols",
    "merge",
    "normalise_to_antenna0",
    "read",
    "sols_dtype",
    "summary",
    "write",
]
