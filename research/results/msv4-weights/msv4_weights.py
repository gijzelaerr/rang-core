# SPDX-License-Identifier: MIT
"""M5, the weights a weighted stage takes from a store (research/msv4-weights.md).

Steps (section 4 of the note):

    copy ROOT              the inputs into ROOT/inputs (MSs and both arms' stores)
    measure ROOT RECEIPT   W1 to W4 and the reported measures, every case and arm

ROOT is `D:/rang/outputs/20261128-msv4-m5`. The MSv2 reference and the row
mapping are msv4-interop.md section 4's (`msv4_interop._ms_reference`,
`msv4_m3m2._pick`), imported from `research/results/msv4-interop/`.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "msv4-interop"))
import msv4_interop as h
import msv4_m3m2 as m3

OLD = "D:/rang/outputs/msv4-20261116"
NEXT = "D:/rang/outputs/msv4-next-20261125"
ARMS = ("xradio", "xms-auto")
SOURCES = {
    **{
        c: (
            f"{OLD}/fixture/outer_scans/{v}",
            {a: f"{OLD}/ps/{a}/{c}.ps.zarr" for a in ARMS},
        )
        for c, v in h.FIXTURE_SCANS.items()
    },
    "c8": (f"{OLD}/ms/c8-scan9-gaps.ms", {a: f"{OLD}/ps/{a}/c8.ps.zarr" for a in ARMS}),
    **{
        c: (f"{OLD}/ms/{v}", {a: f"{OLD}/ps/{a}/{c}.ps.zarr" for a in ARMS})
        for c, v in m3.M3_CASES.items()
        if c != "c10"
    },
    **{
        c: (
            f"{NEXT}/ms-src/{c}.ms",
            {a: f"{NEXT}/ps/{a}/{c}-before.ps.zarr" for a in ARMS},
        )
        for c in ("c6x", "c9")
    },
}
SOLVE_CASES = ("c5", "c11", "c12", "c13", "c14")
NONVACUOUS = ("c11", "c12")
TERM = {
    "solint": "int",
    "freqint": 256,
    "max_iterations": 50,
    "stop_criterion": 1e-7,
    "stop_fraction": 0.99,
}


def paths(root):
    root = Path(root) / "inputs"
    return {
        c: (
            root / "ms" / f"{c}.ms",
            {a: root / "ps" / a / f"{c}.ps.zarr" for a in ARMS},
        )
        for c in SOURCES
    }


def _tree_size(path):
    files = [p for p in Path(path).rglob("*") if p.is_file()]
    return len(files), sum(p.stat().st_size for p in files)


def copy(root):
    out = {}
    for case, (ms, stores) in SOURCES.items():
        dst_ms, dst_stores = paths(root)[case]
        pairs = [(Path(ms), dst_ms)] + [(Path(stores[a]), dst_stores[a]) for a in ARMS]
        for src, dst in pairs:
            if dst.exists():
                raise SystemExit(f"{dst} exists: copy once")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst)
            n, size = _tree_size(dst)
            if (n, size) != _tree_size(src):
                raise SystemExit(f"copy of {src} differs in files or bytes")
            out[str(dst)] = {"from": str(src), "files": n, "bytes": size}
    (Path(root) / "copy.json").write_text(json.dumps(out, indent=1))
    print(f"copied {len(out)} trees")


# --- measures -----------------------------------------------------------------


def _same(a, b):
    import numpy as np

    a, b = np.asarray(a), np.asarray(b)
    return (
        a.shape == b.shape
        and a.dtype == b.dtype
        and np.ascontiguousarray(a).tobytes() == np.ascontiguousarray(b).tobytes()
    )


def _sigma_ref(ms, ref):
    import numpy as np
    from rang import core_ms

    out = {}
    with core_ms.open_table(ms) as t:
        cols = set(t.columns)
        for ddid, cells in ref["cells"].items():
            rows = np.flatnonzero(ref["DATA_DESC_ID"] == ddid)
            if "SIGMA_SPECTRUM" in cols:
                out[ddid] = (t.getcol_rows("SIGMA_SPECTRUM", rows), "SIGMA_SPECTRUM")
            else:
                nchan = cells["DATA"].shape[1]
                sig = t.getcol_rows("SIGMA", rows)
                out[ddid] = (
                    np.repeat(sig[:, None, :], nchan, axis=1),
                    "SIGMA repeated",
                )
    return out


def inputs(ms, store, ref, sigma):
    """W1, W2 and the old reading (reported) of one case and arm."""
    import numpy as np
    from rang import msv4

    ps = msv4.open_processing_set(store)
    used = np.zeros(len(ref["TIME"]), np.int64)
    rec = {"partitions": {}, "refused_partitions": ps.refused}
    w1, w1_src, w2, old, failures = [], [], [], [], []
    for pname in ps.names:
        base = ps.partition(pname)
        groups = list(base.node.attrs["data_groups"])
        prec = {
            "groups": groups,
            "weight_variable": base.weight_variable,
            "weight_refusal": base.weight_refusal,
            "sigma_variable": base.sigma_variable,
            "sigma_refusal": base.sigma_refusal,
            "group_weights": {
                g: base.node.attrs["data_groups"][g].get("weight") for g in groups
            },
        }
        rec["partitions"][pname] = prec
        hits = h._ddid_of(base, ref)
        if len(hits) != 1:
            failures.append(f"{pname}: DATA_DESC_ID mapping {hits}")
            continue
        ddid = hits[0]
        rows0 = base.rows()
        msrows, pick, chan, fallback, fails = m3._pick(base, rows0, ref, ddid)
        failures += fails
        if fallback:
            failures.append(f"{pname}: {fallback} TIME fallbacks")
        ok = pick >= 0
        used[msrows[ok]] += 1
        sel, refsel = pick[ok], np.flatnonzero(ok)
        want_w = ref["cells"][ddid]["WEIGHT_SPECTRUM"][refsel]
        want_s = sigma[ddid][0][refsel]
        for g in groups:
            part = ps.partition(pname, g)
            rows = part.rows()
            w1.append(_same(rows["WEIGHT_SPECTRUM"][sel][:, chan], want_w))
            src = msv4.RowSource(part)
            got = src.getcol_rows("WEIGHT_SPECTRUM", sel)
            w1_src.append(_same(got[:, chan], want_w))
            own = np.asarray(part.ds[part.variables["weight"]].values)
            ti, bi = part.cells()
            own = own[ti, bi][sel][:, chan]
            old.append(
                {
                    "group": g,
                    "variable": part.variables["weight"],
                    "W": _same(own, want_w),
                }
            )
            try:
                s = src.getcol_rows("SIGMA_SPECTRUM", sel)
                w2.append(("read", _same(s[:, chan], want_s)))
            except ValueError as exc:
                w2.append(("refused", str(exc)[:200]))
    coverage = bool(np.all(used == 1)) and not failures
    rec["coverage"] = coverage
    rec["failures"] = failures[:20]
    rec["W1"] = "match" if coverage and w1 and all(w1) and all(w1_src) else "mismatch"
    rec["W1_rows"] = all(w1) if w1 else None
    rec["W1_row_source"] = all(w1_src) if w1_src else None
    kinds = {k for k, _ in w2}
    if kinds == {"read"}:
        rec["W2"] = (
            "read, match" if all(v for _, v in w2) and coverage else "read, mismatch"
        )
    elif kinds == {"refused"}:
        rec["W2"] = "refused"
        rec["W2_message"] = w2[0][1]
    else:
        rec["W2"] = "mixed"
    rec["W2_sigma_source"] = sorted({v[1] for v in sigma.values()})
    rec["old_reading"] = old
    return rec


class MsOrder:
    """A store `RowSource` with its channels in the MS's order (`chan[c]` is
    the store channel of MS channel `c`), for the deciding solve."""

    def __init__(self, src, chan):
        self.src, self.chan = src, chan

    def getcol_rows(self, name, rows, chans=None):
        out = self.src.getcol_rows(name, rows)
        if out.ndim == 3:
            out = out[:, self.chan]
            if chans is not None:
                out = out[:, chans]
        return out


class OwnWeight(MsOrder):
    """`MsOrder` that reads the data group's own weight variable as
    `WEIGHT_SPECTRUM` (the reader before M5), for W4."""

    def getcol_rows(self, name, rows, chans=None):
        if name != "WEIGHT_SPECTRUM":
            return super().getcol_rows(name, rows, chans)
        import numpy as np

        part = self.src.partition
        var = part.variables["weight"]
        ti, bi = self.src.ti[rows], self.src.bi[rows]
        out = np.asarray(part.ds[var].values)[ti, bi][:, self.chan]
        return out if chans is None else out[:, chans]


def _solve(source, idx, rows, cell, chan_freq, names, weight_spectrum):
    from rang import core_pipeline as pipe

    info = {
        "rows": rows,
        "cell": cell,
        "chan_freq": chan_freq,
        "antennas": names,
        "weight_spectrum": weight_spectrum,
    }
    t0 = time.perf_counter()
    out = pipe.solve_partition(source, idx, info, TERM, "as_is", "unity", None)
    return out, time.perf_counter() - t0


def _sol_record(sol):
    import hashlib

    import numpy as np

    g = np.ascontiguousarray(sol.gains)
    return {
        "gains_sha256": hashlib.sha256(g.tobytes()).hexdigest(),
        "flags_sha256": hashlib.sha256(
            np.ascontiguousarray(sol.flags).tobytes()
        ).hexdigest(),
        "iterations": int(sol.iterations),
        "converged_fraction": float(sol.converged_fraction),
        "shape": list(g.shape),
    }


def _equal_sol(a, b):
    import numpy as np

    return (
        a.gains.tobytes() == b.gains.tobytes()
        and np.array_equal(a.flags, b.flags)
        and a.iterations == b.iterations
        and a.converged_fraction == b.converged_fraction
    )


def _rel(a, b):
    import numpy as np

    ga, gb = np.asarray(a.gains), np.asarray(b.gains)
    good = np.isfinite(ga) & np.isfinite(gb) & (np.abs(gb) > 0)
    if not good.any():
        return None
    return float(np.max(np.abs(ga[good] - gb[good]) / np.abs(gb[good])))


def solve(ms, store, ref, case, msv2_cache):
    """W3, W4 and the store-order solve (reported) of one case and arm."""
    import numpy as np
    from rang import core_ms, msv4

    nrow = len(ref["TIME"])
    idx = np.arange(nrow, dtype=np.int64)
    nchan, ncorr = ref["cells"][0]["DATA"].shape[1:]
    chan_freq = np.asarray(ref["chan_freq"][ref["dd_spw"][0]], np.float64)
    names = ref["names"]
    ms_rows = {k: ref[k] for k in ("TIME", "ANTENNA1", "ANTENNA2")}
    if case not in msv2_cache:
        with core_ms.open_table(ms) as t:
            ws = (
                "WEIGHT_SPECTRUM" in t.columns
                and ref["weight_source"][0] == "WEIGHT_SPECTRUM"
            )
            msv2_cache[case] = _solve(
                t, idx, ms_rows, (nchan, ncorr), chan_freq, names, ws
            )
    (want, *_), want_s = msv2_cache[case]
    ps = msv4.open_processing_set(store)
    if len(ps.names) != 1:
        return {"W3": "not measured", "why": f"{len(ps.names)} partitions"}
    part = ps.partition(ps.names[0])
    rec = {"antennas_equal": part.antenna_names == names}
    rows = part.rows()
    _msrows, pick, chan, fallback, failures = m3._pick(part, rows, ref, 0)
    if not rec["antennas_equal"] or (pick < 0).any() or fallback or failures:
        return {**rec, "W3": "mismatch", "why": "mapping", "failures": failures[:5]}
    src = msv4.RowSource(part)
    store_rows = {
        "TIME": rows["TIME"],
        "ANTENNA1": rows["ANTENNA1"],
        "ANTENNA2": rows["ANTENNA2"],
    }
    (got, *_), got_s = _solve(
        MsOrder(src, chan), pick, store_rows, (nchan, ncorr), chan_freq, names, True
    )
    rec.update(
        msv2=_sol_record(want),
        store=_sol_record(got),
        W3="match" if _equal_sol(got, want) else "mismatch",
        msv2_seconds=round(want_s, 3),
        store_seconds=round(got_s, 3),
        channels_reordered=bool(np.any(chan != np.arange(len(chan)))),
    )
    if case in NONVACUOUS:
        (own, *_), _ = _solve(
            OwnWeight(src, chan),
            pick,
            store_rows,
            (nchan, ncorr),
            chan_freq,
            names,
            True,
        )
        rec["W4_own_weight_variable"] = part.variables["weight"]
        rec["W4"] = (
            "holds (own weight changes the gains)"
            if own.gains.tobytes() != got.gains.tobytes()
            else "does not hold"
        )
        rec["W4_max_rel_gain_difference"] = _rel(own, got)
    # Reported: the store's own row order (sorted stably by TIME inside).
    (own_order, *_), _ = _solve(
        MsOrder(src, chan),
        np.arange(len(rows["TIME"]), dtype=np.int64),
        store_rows,
        (nchan, ncorr),
        chan_freq,
        names,
        True,
    )
    rec["store_order"] = {
        "equal": _equal_sol(own_order, want),
        "max_rel_gain_difference": _rel(own_order, want),
    }
    return rec


def _commit():
    try:
        return subprocess.run(
            ["git", "-C", str(HERE), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()  # fmt: skip
    except Exception:  # noqa: BLE001
        return None


def measure(root, receipt):
    import numpy as np
    import rang
    import xarray
    import zarr

    t_all = time.perf_counter()
    result = {
        "note": "research/msv4-weights.md",
        "root": str(root),
        "code": _commit(),
        "rang": rang.__file__,
        "versions": {
            "numpy": np.__version__,
            "xarray": xarray.__version__,
            "zarr": zarr.__version__,
        },
        "term": TERM,
        "host": os.environ.get("COMPUTERNAME"),
        "rayon_threads": os.environ.get("RAYON_NUM_THREADS"),
        "cases": {},
    }
    msv2_cache = {}
    for case, (ms, stores) in paths(root).items():
        t0 = time.perf_counter()
        ref = h._ms_reference(ms)
        sigma = _sigma_ref(ms, ref)
        crec = {"ms": str(ms), "ms_rows": len(ref["TIME"]), "arms": {}}
        for arm in ARMS:
            arec = inputs(ms, stores[arm], ref, sigma)
            if case in SOLVE_CASES:
                arec["solve"] = solve(ms, stores[arm], ref, case, msv2_cache)
            crec["arms"][arm] = arec
            print(case, arm, arec["W1"], arec["W2"], arec.get("solve", {}).get("W3", "-"),
                  arec.get("solve", {}).get("W4", ""), flush=True)  # fmt: skip
        crec["seconds"] = round(time.perf_counter() - t0, 2)
        result["cases"][case] = crec
    result["seconds"] = round(time.perf_counter() - t_all, 2)
    result["outcome"] = outcome(result)
    Path(receipt).write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps(result["outcome"], indent=1))


def outcome(result):
    """Section 5's rule per arm."""
    out = {}
    for arm in ARMS:
        w1 = all(c["arms"][arm]["W1"] == "match" for c in result["cases"].values())
        if arm == "xradio":
            w2 = all(
                c["arms"][arm]["W2"] == "refused" for c in result["cases"].values()
            )
        else:
            w2 = all(
                c["arms"][arm]["W2"] == "read, match" for c in result["cases"].values()
            )
        solves = [
            c["arms"][arm]["solve"]
            for c in result["cases"].values()
            if "solve" in c["arms"][arm]
        ]
        w3 = bool(solves) and all(s.get("W3") == "match" for s in solves)
        # W4 is defined on the xradio arm only (its base weight is S there);
        # on xms-auto every group's own weight is W, so it is recorded only.
        w4 = arm != "xradio" or (
            all(s["W4"].startswith("holds") for s in solves if "W4" in s)
            and sum("W4" in s for s in solves) == len(NONVACUOUS)
        )
        verdict = (
            "pass" if w1 and w2 and w3 and w4
            else "fail" if not (w1 and w3 and w4)
            else "partial (W2)"
        )  # fmt: skip
        out[arm] = {"W1": w1, "W2": w2, "W3": w3, "W4": w4, "verdict": verdict}
    return out


def main(argv):
    if len(argv) >= 2 and argv[0] == "copy":
        copy(Path(argv[1]))
    elif len(argv) >= 3 and argv[0] == "measure":
        measure(Path(argv[1]), Path(argv[2]))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
