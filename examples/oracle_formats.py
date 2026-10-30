"""Container side of the DF-IO format checks (research/dfio-formats.md).

Runs inside the oracle images, never on the host; `examples/check_formats.py`
calls it. Every mode reads its inputs read-only and writes only under the
given output path.

    # rang-o-casa:6.7.6.14 (/opt/casa/bin/python)
    oracle_formats.py casa-t <out-table> <ms> <k-table>
    oracle_formats.py casa-flagversions <ms> <restore|list|save> <name>
    # rang-formats-oracle:20261030
    oracle_formats.py qc-dump <store> <out.npz>              (/opt/qc)
    oracle_formats.py qc-delay <ms> <out-dir>                (/opt/qc)
    oracle_formats.py qc-apply <ms> <store> <term> <out-dir>  (/opt/qc)
    oracle_formats.py tigger-dump <model> <out.json>         (/opt/sky)
    oracle_formats.py wsclean-dump <list> <out.json>         (/opt/sky)
    oracle_formats.py crystalball <ms> <list>                (/opt/sky)
    oracle_formats.py losoto-dump <h5> <out.json>            (/opt/h5)
    oracle_formats.py losoto-make <h5> <values.npz>          (/opt/h5)
    oracle_formats.py dicomodel-dump <dicomodel> <out.npz>   (/opt/ddf)
    oracle_formats.py npy-save <values.npz> <key> <out.npy>  (/opt/ddf)
    oracle_formats.py npz-dump <in.npz> <out.npz>            (/opt/ddf)
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REFANT = "m000"
FIELD = "J1939-6342"


def timed(log, name, fn, *args, **kwargs):
    start = time.perf_counter()
    out = fn(*args, **kwargs)
    log[name] = time.perf_counter() - start
    return out


# ---------------------------------------------------------------------------
# CASA (rang-o-casa:6.7.6.14).


def casa_t(out, ms, k_table):
    from casatasks import gaincal

    log = {}
    timed(
        log,
        "gaincal_T",
        gaincal,
        vis=ms,
        caltable=out,
        field=FIELD,
        refant=REFANT,
        minblperant=3,
        solint="120s",
        combine="",
        gaintype="T",
        calmode="p",
        gaintable=[k_table],
        interp=["linear"],
    )
    Path(out + ".json").write_text(json.dumps(log))


def casa_split(ms, out, field):
    """CASA split of one field's DATA into a new MS (DP3 needs one FIELD row)."""
    from casatasks import split

    start = time.perf_counter()
    split(vis=ms, outputvis=out, field=field, datacolumn="data", keepflags=True)
    Path(out + ".split.json").write_text(
        json.dumps({"wall_s": time.perf_counter() - start})
    )


def casa_flagversions(ms, mode, name):
    from casatasks import flagmanager

    start = time.perf_counter()
    result = flagmanager(vis=ms, mode=mode, versionname=name, comment="rang")
    wall = time.perf_counter() - start
    Path(ms + f".{mode}.json").write_text(
        json.dumps({"wall_s": wall, "result": result}, default=str)
    )


# ---------------------------------------------------------------------------
# QuartiCal 0.2.7 (/opt/qc).


def qc_dump(store, out):
    """Every variable and coordinate of every partition of a gain store as
    `xds_from_zarr` reads it, and the attributes."""
    from daskms.experimental.zarr import xds_from_zarr

    store = Path(store)
    arrays, meta = {}, {}
    for term in sorted(p.name for p in store.iterdir() if p.is_dir()):
        for i, ds in enumerate(xds_from_zarr(f"{store}::{term}")):
            ds = ds.compute()
            key = f"{term}/{i}"
            meta[key] = {
                "attrs": json.loads(json.dumps(ds.attrs, default=str)),
                "dims": {k: int(v) for k, v in ds.sizes.items()},
                "vars": {},
            }
            for name, var in list(ds.data_vars.items()) + list(ds.coords.items()):
                arrays[f"{key}/{name}"] = np.asarray(var.values)
                meta[key]["vars"][name] = {
                    "dims": list(var.dims),
                    "dtype": str(var.dtype),
                }
    np.savez(out, **arrays)
    Path(str(out) + ".json").write_text(json.dumps(meta, indent=1, sort_keys=True))


def goquartical(args, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    exe = Path(sys.executable).parent / "goquartical"
    start = time.perf_counter()
    with (out / "quartical.log").open("w") as log:
        code = subprocess.run(
            [str(exe), *args], stdout=log, stderr=subprocess.STDOUT, check=False
        ).returncode
    wall = time.perf_counter() - start
    (out / "run.json").write_text(
        json.dumps({"args": args, "code": code, "wall_s": wall})
    )
    if code:
        raise SystemExit(f"goquartical failed ({code}); see {out}/quartical.log")


COMMON = [
    "input_ms.data_column=DATA",
    "input_ms.weight_column=WEIGHT_SPECTRUM",
    "input_model.recipe=MODEL_DATA",
    "solver.reference_antenna=0",
    "solver.robust=false",
    "mad_flags.enable=false",
    "output.flags=false",
    "dask.threads=1",
    "solver.threads=1",
    "dask.scheduler=single-threaded",
]


def qc_delay(ms, out):
    """A parametrised (delay) store from QuartiCal on a copy of the MS."""
    out = Path(out)
    goquartical(
        [
            f"input_ms.path={ms}",
            *COMMON,
            "solver.terms=[K]",
            "K.type=delay",
            "K.time_interval=2",
            "K.freq_interval=0",
            "solver.iter_recipe=[20]",
            "solver.convergence_criteria=1e-7",
            f"output.gain_directory={out / 'gains.qc'}",
            f"output.log_directory={out / 'logs.qc'}",
        ],
        out,
    )


def qc_apply(
    ms, store, term, out, kind="complex", time_interval="2", freq_interval="32"
):
    """QuartiCal applies `<store>/<term>` (load_from, no iterations) and
    writes CORRECTED_DATA."""
    out = Path(out)
    goquartical(
        [
            f"input_ms.path={ms}",
            *COMMON,
            f"solver.terms=[{term}]",
            f"{term}.type={kind}",
            f"{term}.time_interval={time_interval}",
            f"{term}.freq_interval={freq_interval}",
            f"{term}.load_from={store}/{term}",
            "solver.iter_recipe=[0]",
            "output.products=[corrected_data]",
            "output.columns=[CORRECTED_DATA]",
            f"output.gain_directory={out / 'gains.qc'}",
            f"output.log_directory={out / 'logs.qc'}",
        ],
        out,
    )


# ---------------------------------------------------------------------------
# Tigger, africanus and Crystalball (/opt/sky).


def _jsonable(value):
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    return repr(value)


def tigger_dump(model, out):
    """Every source of a model as Tigger 1.8.0 loads it (floats as repr)."""
    import Tigger

    m = Tigger.load(model)
    sources = []
    for s in m.sources:
        spectrum = s.spectrum
        d = {
            "name": s.name,
            "ra": repr(float(s.pos.ra)),
            "dec": repr(float(s.pos.dec)),
            "i": repr(float(s.flux.I)),
            "q": repr(float(getattr(s.flux, "Q", 0.0))),
            "u": repr(float(getattr(s.flux, "U", 0.0))),
            "v": repr(float(getattr(s.flux, "V", 0.0))),
            "freq0": repr(float(spectrum.freq0)) if spectrum is not None else None,
            "spi": (
                [repr(float(x)) for x in np.atleast_1d(spectrum.spi)]
                if spectrum is not None and hasattr(spectrum, "spi")
                else []
            ),
            "shape": None,
        }
        if s.shape is not None:
            d["shape"] = [
                repr(float(s.shape.ex)),
                repr(float(s.shape.ey)),
                repr(float(s.shape.pa)),
            ]
        sources.append(d)
    Path(out).write_text(
        json.dumps({"freq0": _jsonable(m.freq0), "sources": sources}, indent=1)
    )


def wsclean_dump(path, out):
    """A WSClean source list as africanus `file_model.load` (Crystalball's
    parser) returns it."""
    from africanus.model.wsclean.file_model import load

    columns = {}
    for name, values in load(path):
        columns[name] = [
            repr(float(v)) if isinstance(v, (float, np.floating)) else _jsonable(v)
            for v in values
        ]
    Path(out).write_text(json.dumps(columns, indent=1))


def crystalball(ms, sky_list):
    """Crystalball 0.4.3 predicts `sky_list` into MODEL_DATA of `ms`."""
    exe = Path(sys.executable).parent / "crystalball"
    start = time.perf_counter()
    proc = subprocess.run(
        [str(exe), ms, "-sm", sky_list, "-o", "MODEL_DATA", "-f", FIELD, "-j", "1"],
        capture_output=True,
        text=True,
        check=False,
    )
    Path(ms + ".crystalball.json").write_text(
        json.dumps(
            {
                "code": proc.returncode,
                "wall_s": time.perf_counter() - start,
                "log": (proc.stdout + proc.stderr)[-4000:],
            }
        )
    )
    if proc.returncode:
        raise SystemExit(proc.stdout[-2000:] + proc.stderr[-2000:])


# ---------------------------------------------------------------------------
# losoto (/opt/h5).


def losoto_dump(h5, out):
    """Every solset and soltab of an H5parm as losoto's API reads it."""
    from losoto.h5parm import h5parm

    h = h5parm(h5, readonly=True)
    result = {}
    arrays = {}
    for ss_name in h.getSolsetNames():
        ss = h.getSolset(ss_name)
        ant = ss.getAnt()
        sou = ss.getSou()
        result[ss_name] = {
            "antennas": {k: [float(x) for x in v] for k, v in ant.items()},
            "sources": {k: [float(x) for x in v] for k, v in sou.items()},
            "soltabs": {},
        }
        for st_name in ss.getSoltabNames():
            st = ss.getSoltab(st_name)
            axes = st.getAxesNames()
            entry = {"type": st.getType(), "axes": axes}
            for a in axes:
                values = st.getAxisValues(a)
                arrays[f"{ss_name}/{st_name}/axis/{a}"] = np.asarray(values)
            arrays[f"{ss_name}/{st_name}/val"] = np.asarray(
                st.getValues(retAxesVals=False)
            )
            arrays[f"{ss_name}/{st_name}/weight"] = np.asarray(
                st.getValues(weight=True, retAxesVals=False)
            )
            result[ss_name]["soltabs"][st_name] = entry
    h.close()
    np.savez(
        str(out) + ".npz",
        **{
            k: (v.astype(str) if v.dtype.kind in "SUO" else v)
            for k, v in arrays.items()
        },
    )
    Path(out).write_text(json.dumps(result, indent=1))


def h5_list(h5, out):
    """Every node of an HDF5 file as PyTables sees it: class, dtype,
    shape and attributes (the protocol's layout listing)."""
    import tables

    rows = []
    with tables.open_file(h5) as h:
        for node in h.walk_nodes("/"):
            attrs = {
                k: repr(node._v_attrs[k])
                for k in node._v_attrs._v_attrnames
                if k != "FILTERS"
            }
            rows.append(
                {
                    "path": node._v_pathname,
                    "class": type(node).__name__,
                    "dtype": str(getattr(node, "dtype", "")),
                    "shape": [int(x) for x in getattr(node, "shape", ()) or ()],
                    "attrs": attrs,
                }
            )
    Path(out).write_text(json.dumps(rows, indent=1))


def dp3_apply(ms, h5):
    """DP3 6.6.0 applycal of an H5parm's amplitude000 and phase000 into
    CORRECTED_DATA (nearest interpolation, the default)."""
    exe = Path(sys.executable).parent / "DP3.py"
    args = [
        f"msin={ms}",
        "msin.datacolumn=DATA",
        "msout=.",
        "msout.datacolumn=CORRECTED_DATA",
        "steps=[ac]",
        "ac.type=applycal",
        f"ac.parmdb={h5}",
        "ac.steps=[amp,ph]",
        "ac.amp.correction=amplitude000",
        "ac.ph.correction=phase000",
    ]
    start = time.perf_counter()
    proc = subprocess.run(
        [str(exe), *args], capture_output=True, text=True, check=False
    )
    Path(ms + ".dp3.json").write_text(
        json.dumps(
            {
                "args": args,
                "code": proc.returncode,
                "wall_s": time.perf_counter() - start,
                "log": (proc.stdout + proc.stderr)[-4000:],
            }
        )
    )
    if proc.returncode:
        raise SystemExit(proc.stdout[-2000:] + proc.stderr[-2000:])


def merge_sols(pattern, out):
    """killMS 3.3.0 MergeSols.py (run in a scratch working directory: it
    writes last_InterPol.obj there)."""
    exe = Path(sys.executable).parent / "MergeSols.py"
    start = time.perf_counter()
    proc = subprocess.run(
        [str(exe), f"--SolsFilesIn={pattern}", f"--SolFileOut={out}"],
        capture_output=True,
        text=True,
        check=False,
        cwd="/tmp",
    )
    Path(out + ".json").write_text(
        json.dumps(
            {
                "code": proc.returncode,
                "wall_s": time.perf_counter() - start,
                "log": (proc.stdout + proc.stderr)[-4000:],
            }
        )
    )
    if proc.returncode:
        raise SystemExit(proc.stdout[-2000:] + proc.stderr[-2000:])


def losoto_make(h5, values):
    """A reference H5parm made by losoto's own API from given values."""
    from losoto.h5parm import h5parm

    v = np.load(values)
    h = h5parm(h5, readonly=False)
    ss = h.makeSolset("sol000")
    names = [str(x) for x in v["ant"]]
    ss.obj.antenna.append([(n, p) for n, p in zip(names, v["ant_pos"])])
    ss.obj.source.append([("pointing", v["dir"])])
    axes = ["time", "freq", "ant", "dir", "pol"]
    vals = [v["time"], v["freq"], names, ["pointing"], ["XX", "YY"]]
    ss.makeSoltab(
        "amplitude", axesNames=axes, axesVals=vals, vals=v["amp"], weights=v["weight"]
    )
    ss.makeSoltab(
        "phase", axesNames=axes, axesVals=vals, vals=v["phase"], weights=v["weight"]
    )
    h.close()


# ---------------------------------------------------------------------------
# DDFacet and killMS (/opt/ddf).


def _flatten(prefix, value, arrays, meta):
    """A pickled structure as arrays and a type description."""
    if isinstance(value, dict):
        meta[prefix] = {"type": type(value).__name__, "keys": [repr(k) for k in value]}
        for k, v in value.items():
            _flatten(f"{prefix}/{k!r}", v, arrays, meta)
    elif isinstance(value, (list, tuple)):
        meta[prefix] = {"type": type(value).__name__, "len": len(value)}
        for i, v in enumerate(value):
            _flatten(f"{prefix}/{i}", v, arrays, meta)
    elif isinstance(value, np.ndarray):
        meta[prefix] = {
            "type": "ndarray",
            "dtype": value.dtype.str,
            "shape": list(value.shape),
        }
        arrays[prefix] = value
    elif isinstance(value, np.generic):
        meta[prefix] = {"type": type(value).__name__, "dtype": value.dtype.str}
        arrays[prefix] = np.asarray(value)
    else:
        meta[prefix] = {"type": type(value).__name__, "value": repr(value)}


def dicomodel_dump(path, out):
    """DDFacet's own load of a DicoModel (`MyPickle.Load`: pickle.load)."""
    from DDFacet.Other import MyPickle

    d = MyPickle.Load(path)
    arrays, meta = {}, {}
    _flatten("", d, arrays, meta)
    np.savez(out, **{f"a{i}": a for i, a in enumerate(arrays.values())})
    Path(str(out) + ".json").write_text(
        json.dumps({"meta": meta, "arrays": list(arrays)}, indent=1)
    )


def npy_save(values, key, out):
    np.save(out, np.load(values)[key])


def npy_dump(path, out):
    """A `.npy` as `np.load` reads it (DDFacet's numpy)."""
    np.savez(out, a=np.load(path))


def wsclean_list(ms, name):
    """WSClean 3.7 cleans `ms` (field J1939-6342) and saves its source list."""
    start = time.perf_counter()
    proc = subprocess.run(
        [
            "wsclean",
            "-name",
            name,
            "-size",
            "512",
            "512",
            "-scale",
            "2asec",
            "-niter",
            "200",
            "-mgain",
            "0.8",
            "-field",
            "1",
            "-data-column",
            "DATA",
            "-save-source-list",
            "-j",
            "4",
            ms,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    Path(name + ".json").write_text(
        json.dumps(
            {
                "code": proc.returncode,
                "wall_s": time.perf_counter() - start,
                "log": (proc.stdout + proc.stderr)[-3000:],
            }
        )
    )
    if proc.returncode:
        raise SystemExit(proc.stdout[-2000:] + proc.stderr[-2000:])


def npz_dump(path, out):
    """A killMS npz as `np.load(allow_pickle=True)` reads it."""
    z = np.load(path, allow_pickle=True)
    arrays, meta = {}, {}
    for k in z.files:
        _flatten(k, z[k], arrays, meta)
    np.savez(out, **{f"a{i}": a for i, a in enumerate(arrays.values())})
    Path(str(out) + ".json").write_text(
        json.dumps({"meta": meta, "arrays": list(arrays)}, indent=1)
    )


MODES = {
    "casa-t": casa_t,
    "casa-flagversions": casa_flagversions,
    "casa-split": casa_split,
    "qc-dump": qc_dump,
    "qc-delay": qc_delay,
    "qc-apply": qc_apply,
    "tigger-dump": tigger_dump,
    "wsclean-dump": wsclean_dump,
    "crystalball": crystalball,
    "losoto-dump": losoto_dump,
    "losoto-make": losoto_make,
    "dicomodel-dump": dicomodel_dump,
    "npy-save": npy_save,
    "npy-dump": npy_dump,
    "npz-dump": npz_dump,
    "wsclean-list": wsclean_list,
    "h5-list": h5_list,
    "dp3-apply": dp3_apply,
    "merge-sols": merge_sols,
}


def main(argv):
    if len(argv) < 2 or argv[1] not in MODES:
        print(__doc__)
        return 2
    MODES[argv[1]](*argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
