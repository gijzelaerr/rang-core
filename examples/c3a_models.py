"""C3a oracles: calibrator models against CASA `setjy`, Crystalball 0.4.3 and
A1's simulated truth (research/c3a-models.md).

    python examples/c3a_models.py run <run>          # host: everything
    /opt/casa/bin/python -I /ex/c3a_models.py casa-setjy <calls.json>   # in rang-o-casa

`<run>` is a fresh directory under /mnt/d/rang/c3a/. Inputs are copied into
it (never opened for writing); the containers run with the network off, as
this user, inputs read-only and only `<run>` writable. The comparison and its
frozen criteria go to `<run>/c3a.json`.
"""

import hashlib
import json
import os
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CASA_IMAGE = "rang-o-casa:6.7.6.14"
FORMATS_IMAGE = "rang-formats-oracle:20261030"
SLICE = Path.home() / "Github/rang/outputs/o-casa-20261030-01/work.ms"
A1 = Path("/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small")
LSM = (
    Path.home()
    / "Github/rang/outputs/c1-sources-20261105/caracal-8f7bb363/pks1934-638.lsm"
)
LSM_SHA256 = "0964b9f4c547bb802bfb16a2e8fdccddff84beeec05b6f3492521a46fa77d101"
FCAL = "J1939-6342"
CARACAL_SPIX = [-0.19473727, -1.3843252, 0.60533435, 1.43e-06]
TOL_REL = 1e-9  # CASA imaginary and cross hands, relative to I (frozen)
TOL_PEAK = 1e-6  # lsm against Crystalball, of the peak (frozen)


# -- inside the CASA image ------------------------------------------------------------


def casa_setjy(calls_path):
    """Run the `setjy` calls of a JSON list in order; record each return."""
    from casatasks import casalog, setjy

    calls = json.loads(Path(calls_path).read_text())
    out = []
    for k, call in enumerate(calls):
        log = Path(call["vis"]).with_suffix(f".setjy{k}.log")
        casalog.setlogfile(str(log))
        start = time.time()
        result = setjy(**call)
        wall = time.time() - start
        fluxd = {}
        for fid, per in (result or {}).items():
            if fid == "format" or not isinstance(per, dict):
                continue
            for spw, value in per.items():
                if isinstance(value, dict) and "fluxd" in value:
                    fluxd[f"{fid}/{spw}"] = [
                        float(v) for v in np.asarray(value["fluxd"])
                    ]
        lines = [
            x for x in log.read_text().splitlines() if "SEVERE" in x or "WARN" in x
        ]
        out.append(
            {"call": call, "wall_s": round(wall, 3), "fluxd": fluxd, "warn": lines[:10]}
        )
    Path(str(calls_path) + ".result.json").write_text(json.dumps(out, indent=1))


# -- host -------------------------------------------------------------------------------

TIMINGS = []


def docker(image, args, run, label, extra=()):
    cmd = ["docker", "run", "--rm", "--network", "none"]
    cmd += ["--user", f"{os.getuid()}:{os.getgid()}", "--tmpfs", "/tmp"]
    cmd += [
        "-e",
        "HOME=/tmp",
        "-e",
        "OMP_NUM_THREADS=4",
        "-e",
        "OPENBLAS_NUM_THREADS=1",
    ]
    for host, guest, mode in [(run, "/run", "rw"), (HERE, "/ex", "ro"), *extra]:
        cmd += ["-v", f"{Path(host).resolve()}:{guest}:{mode}"]
    cmd += ["-w", "/tmp", image, *args]
    start = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    TIMINGS.append(
        {
            "label": label,
            "image": image,
            "wall_s": round(time.perf_counter() - start, 2),
        }
    )
    if proc.returncode:
        raise RuntimeError(f"{label}: {proc.stdout[-3000:]}\n{proc.stderr[-3000:]}")
    return proc.stdout


def timed(label, fn, *args, **kwargs):
    start = time.perf_counter()
    out = fn(*args, **kwargs)
    TIMINGS.append({"label": label, "wall_s": round(time.perf_counter() - start, 3)})
    return out


def tree_sha(path):
    """SHA-256 over sorted relative paths and file hashes (no table.lock)."""
    h = hashlib.sha256()
    for f in sorted(p for p in Path(path).rglob("*") if p.is_file()):
        if f.name == "table.lock":
            continue
        h.update(f.relative_to(path).as_posix().encode())
        h.update(hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


def column(ms, name):
    from rang import core_ms

    with core_ms.open_table(ms) as t:
        return t.getcol(name)


def main_columns(ms, skip=("MODEL_DATA",)):
    from rang import core_ms

    with core_ms.open_table(ms) as t:
        names = [c for c in t.colnames() if c not in skip and c != "FLAG_CATEGORY"]
        return {
            c: hashlib.sha256(np.ascontiguousarray(t.getcol(c)).tobytes()).hexdigest()
            for c in names
        }


def bits(a):
    a = np.ascontiguousarray(a)
    return a.view(np.uint32) if a.dtype == np.complex64 else a.view(np.uint8)


def f32_ulps(a, b):
    """Largest distance in float32 ulps between two float32 arrays."""
    ia = np.ascontiguousarray(a, np.float32).view(np.int32).astype(np.int64)
    ib = np.ascontiguousarray(b, np.float32).view(np.int32).astype(np.int64)
    ia = np.where(ia < 0, -(ia & 0x7FFFFFFF), ia)
    ib = np.where(ib < 0, -(ib & 0x7FFFFFFF), ib)
    return int(np.abs(ia - ib).max()) if ia.size else 0


def point_vs_casa(rang, casa, rows):
    """C3a parts 1-3 on the selected rows (XX, XY, YX, YY)."""
    r, c = rang[rows], casa[rows]
    i = np.abs(r[..., 0].real).astype(np.float64)
    res = {
        "rows": int(rows.sum()),
        "cells": int(r.shape[0] * r.shape[1]),
        "real_parallel_max_ulps": max(
            f32_ulps(r[..., 0].real, c[..., 0].real),
            f32_ulps(r[..., 3].real, c[..., 3].real),
        ),
        "rang_xx_equals_yy": bool(np.array_equal(r[..., 0], r[..., 3])),
        "rang_imag_and_cross_zero": bool(
            np.all(r[..., [0, 3]].imag == 0) and np.all(r[..., [1, 2]] == 0)
        ),
        "casa_imag_parallel_max_rel": float(
            (np.abs(c[..., [0, 3]].imag) / i[..., None]).max()
        ),
        "casa_imag_parallel_max_jy": float(np.abs(c[..., [0, 3]].imag).max()),
        "casa_cross_max_rel": float((np.abs(c[..., [1, 2]]) / i[..., None]).max()),
        "complex_bit_identical_fraction": float(
            np.mean(np.all(bits(r) == bits(c), axis=-1))
        ),
        "stokes_i_range_jy": [float(i.min()), float(i.max())],
    }
    res["pass"] = (
        res["real_parallel_max_ulps"] == 0
        and res["rang_imag_and_cross_zero"]
        and res["casa_imag_parallel_max_rel"] <= TOL_REL
        and res["casa_cross_max_rel"] <= TOL_REL
    )
    return res


def lsm_vs_cb(rang, cb, rows, flux_sum):
    r, c = rang[rows], cb[rows]
    peak = float(np.abs(c).max())
    diff = np.abs(r.astype(np.complex128) - c.astype(np.complex128))
    bound = 2.0**-22 * flux_sum
    res = {
        "rows": int(rows.sum()),
        "peak_jy": peak,
        "max_abs_diff_jy": float(diff.max()),
        "max_diff_over_peak": float(diff.max() / peak),
        "dfio_bound_ratio_max": float((diff[..., [0, 3]] / bound[None, :, None]).max()),
        "bit_identical_cell_fraction": float(np.mean(bits(r) == bits(c))),
        "cross_zero_rang": bool(np.all(r[..., [1, 2]] == 0)),
        "cross_zero_cb": bool(np.all(c[..., [1, 2]] == 0)),
    }
    res["pass"] = (
        res["max_diff_over_peak"] <= TOL_PEAK
        and res["cross_zero_rang"]
        and res["cross_zero_cb"]
    )
    return res


def run(run_dir):
    sys.path.insert(0, str(ROOT / "python"))
    from rang import calmodels, fluxstd, simtruth
    from rang.formats import sky

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    result = {
        "criteria": {"tol_rel_casa_imag_cross": TOL_REL, "tol_lsm_peak": TOL_PEAK}
    }
    # Inputs, hashed before and after.
    lsm_sha = hashlib.sha256(LSM.read_bytes()).hexdigest()
    if lsm_sha != LSM_SHA256:
        raise SystemExit(f"lsm SHA-256 {lsm_sha} != {LSM_SHA256}")
    inputs = {"slice": SLICE, "a1": A1 / "a1-small.ms"}
    before = {k: timed(f"hash {k}", tree_sha, v) for k, v in inputs.items()}
    truth_path = A1 / "truth.npz"
    result["inputs"] = {
        "slice": str(SLICE),
        "a1": str(inputs["a1"]),
        "truth": str(truth_path),
        "truth_sha256": hashlib.sha256(truth_path.read_bytes()).hexdigest(),
        "lsm": str(LSM),
        "lsm_sha256": lsm_sha,
        "tree_sha256_before": before,
    }
    copies = {}
    for tag in (
        "S-casa-sr",
        "S-casa-man",
        "S-rang-sr",
        "S-rang-man",
        "S-cb",
        "S-rang-list",
        "S-rang-lsm",
    ):
        copies[tag] = run_dir / f"{tag}.ms"
        shutil.copytree(SLICE, copies[tag])
    for tag in ("A-casa", "A-rang", "A-cb", "A-rang-list", "A-stokes"):
        copies[tag] = run_dir / f"{tag}.ms"
        shutil.copytree(inputs["a1"], copies[tag])
    # The converted list (C1: "the same converted list").
    (run_dir / "sky").mkdir()
    sources = sky.load(LSM)
    wlist = run_dir / "sky" / "pks1934-638.wsclean.txt"
    wlist.write_text(sky.dumps_wsclean(sources))
    result["lsm"] = sky.summary(sources)
    # CASA setjy.
    g, x = simtruth.GCAL, simtruth.XCAL
    calls = [
        {"vis": "/run/S-casa-sr.ms", "field": FCAL, "standard": "Stevens-Reynolds 2016"},
        {
            "vis": "/run/S-casa-man.ms", "field": FCAL, "standard": "manual",
            "fluxdensity": fluxstd.CARACAL_1934["fluxdensity"], "reffreq": "1.400000GHz",
            "spix": CARACAL_SPIX,
        },
        {"vis": "/run/A-casa.ms", "field": FCAL, "standard": "Stevens-Reynolds 2016"},
        {
            "vis": "/run/A-casa.ms", "field": "SIM-GCAL", "standard": "manual",
            "fluxdensity": g["fluxdensity"], "reffreq": "1.4GHz", "spix": list(g["spix"]),
        },
        {
            "vis": "/run/A-casa.ms", "field": "3C286-SIM", "standard": "manual",
            "fluxdensity": x["fluxdensity"], "reffreq": "1.47GHz", "spix": list(x["spix"]),
        },
    ]  # fmt: skip
    for c in calls:
        c.update(scalebychan=True, usescratch=True)
    (run_dir / "setjy-calls.json").write_text(json.dumps(calls, indent=1))
    docker(
        CASA_IMAGE,
        [
            "/opt/casa/bin/python",
            "-I",
            "/ex/c3a_models.py",
            "casa-setjy",
            "/run/setjy-calls.json",
        ],
        run_dir,
        "CASA setjy (5 calls)",
    )
    result["setjy"] = json.loads((run_dir / "setjy-calls.json.result.json").read_text())
    # Crystalball 0.4.3 on the converted list.
    for tag in ("S-cb", "A-cb"):
        docker(
            FORMATS_IMAGE,
            ["/opt/sky/bin/python", "-I", "/ex/oracle_formats.py", "crystalball",
             f"/run/{tag}.ms", "/run/sky/pks1934-638.wsclean.txt"],
            run_dir,
            f"Crystalball 0.4.3 {tag}",
        )  # fmt: skip
        result.setdefault("crystalball", {})[tag] = json.loads(
            (run_dir / f"{tag}.ms.crystalball.json").read_text()
        )["wall_s"]
    # Rang.
    rec = {}
    rec["S-rang-sr"] = timed(
        "rang SR2016 slice", calmodels.set_model, copies["S-rang-sr"], FCAL,
        {"standard": "Stevens-Reynolds 2016"},
    )  # fmt: skip
    rec["S-rang-man"] = timed(
        "rang manual slice", calmodels.set_model, copies["S-rang-man"], FCAL,
        {"standard": "manual", "fluxdensity": fluxstd.CARACAL_1934["fluxdensity"],
         "reffreq": "1.400000GHz", "spix": CARACAL_SPIX},
    )  # fmt: skip
    a_specs = [
        (FCAL, {"standard": "Stevens-Reynolds 2016"}),
        ("SIM-GCAL", {"standard": "manual", "fluxdensity": g["fluxdensity"],
                      "reffreq": "1.4GHz", "spix": list(g["spix"])}),
        ("3C286-SIM", {"standard": "manual", "fluxdensity": x["fluxdensity"],
                       "reffreq": "1.47GHz", "spix": list(x["spix"])}),
    ]  # fmt: skip
    rec["A-rang"] = [
        timed(f"rang {f} A1", calmodels.set_model, copies["A-rang"], f, spec)
        for f, spec in a_specs
    ]
    for tag in ("S-rang-list", "A-rang-list"):
        rec[tag] = timed(
            f"rang lsm list {tag}",
            calmodels.set_model,
            copies[tag],
            FCAL,
            {"skymodel": str(wlist)},
        )
    rec["S-rang-lsm"] = timed(
        "rang lsm slice",
        calmodels.set_model,
        copies["S-rang-lsm"],
        FCAL,
        {"skymodel": str(LSM)},
    )
    truth = np.load(truth_path)
    cal = truth["calibrator_stokes"]
    a_freq = column(copies["A-rang"] / "SPECTRAL_WINDOW", "CHAN_FREQ")[0]
    if not np.array_equal(a_freq, truth["freq_hz"]):
        raise SystemExit("A1 truth frequencies differ from the MS")

    def stokes_3c286(nu):
        if not np.array_equal(nu, truth["freq_hz"]):
            raise ValueError("frequencies differ from the truth's")
        return cal[1]

    rec["A-stokes"] = timed(
        "rang PointStokes 3C286-SIM", calmodels.set_model, copies["A-stokes"], "3C286-SIM",
        calmodels.PointStokes(stokes_3c286, "A1 truth 3C286-SIM"),
    )  # fmt: skip
    result["receipts"] = rec
    # Comparisons.
    cmp = {}
    s_fid = column(SLICE, "FIELD_ID")
    s_rows = s_fid == calmodels.metadata(SLICE)["field_names"].index(FCAL)
    for arm, casa in (("O1a", "S-casa-sr"), ("O1b", "S-casa-man")):
        rang_ms = copies["S-rang-sr" if arm == "O1a" else "S-rang-man"]
        res = point_vs_casa(
            column(rang_ms, "MODEL_DATA"), column(copies[casa], "MODEL_DATA"), s_rows
        )
        res["other_columns_unchanged"] = main_columns(rang_ms) == main_columns(SLICE)
        res["pass"] = res["pass"] and res["other_columns_unchanged"]
        cmp[arm] = res
    a_fid = column(copies["A-rang"], "FIELD_ID")
    names = calmodels.metadata(copies["A-rang"])["field_names"]
    rang_a = column(copies["A-rang"], "MODEL_DATA")
    casa_a = column(copies["A-casa"], "MODEL_DATA")
    o2 = {}
    for f in (FCAL, "SIM-GCAL", "3C286-SIM"):
        o2[f] = point_vs_casa(rang_a, casa_a, a_fid == names.index(f))
    tgt = a_fid == names.index("SIM-TARGET")
    o2["SIM-TARGET"] = {
        "rows": int(tgt.sum()),
        "bit_identical_to_casa": bool(
            np.array_equal(bits(rang_a[tgt]), bits(casa_a[tgt]))
        ),
        "casa_values": sorted({str(v) for v in np.unique(casa_a[tgt])})[:8],
    }
    o2["other_columns_unchanged"] = main_columns(copies["A-rang"]) == main_columns(
        inputs["a1"]
    )
    o2["pass"] = (
        all(o2[f]["pass"] for f in (FCAL, "SIM-GCAL", "3C286-SIM"))
        and o2["SIM-TARGET"]["bit_identical_to_casa"]
        and o2["other_columns_unchanged"]
    )
    cmp["O2"] = o2
    # Crystalball.
    flux_sum = None
    for arm, tag, base, fid_all in (
        ("O3a", "S-rang-list", "S-cb", s_fid),
        ("O3b", "A-rang-list", "A-cb", a_fid),
    ):
        ms = copies[tag]
        meta = calmodels.metadata(ms)
        freqs = meta["ddid"][0]["freq_hz"]
        flux_sum = np.sum(np.abs([s.flux(freqs) for s in sources]), axis=0)
        rows = fid_all == meta["field_names"].index(FCAL)
        cb = column(copies[base], "MODEL_DATA")
        res = lsm_vs_cb(column(ms, "MODEL_DATA"), cb, rows, flux_sum)
        others = ~rows
        if others.any():
            vals = np.unique(cb[others])
            res["crystalball_other_rows"] = {
                "rows": int(others.sum()),
                "distinct_values": [str(v) for v in vals[:6]],
            }
        cmp[arm] = res
    lsm_m = column(copies["S-rang-lsm"], "MODEL_DATA")[s_rows].astype(np.complex128)
    list_m = column(copies["S-rang-list"], "MODEL_DATA")[s_rows].astype(np.complex128)
    peak = float(np.abs(list_m).max())
    cmp["O3c"] = {
        "max_abs_diff_jy": float(np.abs(lsm_m - list_m).max()),
        "max_diff_over_peak": float(np.abs(lsm_m - list_m).max() / peak),
        "bit_identical_cell_fraction": float(
            np.mean(
                bits(lsm_m.astype(np.complex64)) == bits(list_m.astype(np.complex64))
            )
        ),
    }
    # A1 truth.
    o4 = {}
    for f in (FCAL, "SIM-GCAL"):
        k = names.index(f)
        exp = simtruth.stokes_coherency(cal[k]).astype(np.complex64)
        got = rang_a[a_fid == k]
        o4[f] = {
            "rows": int(got.shape[0]),
            "equal": bool(np.all(got == exp[None])),
            "bit_identical": bool(
                np.all(bits(got) == bits(np.broadcast_to(exp, got.shape)))
            ),
        }
    k = names.index("3C286-SIM")
    got = rang_a[a_fid == k]
    i32 = cal[k][:, 0].astype(np.float32)
    o4["3C286-SIM"] = {
        "rows": int(got.shape[0]),
        "stokes_i_equal": bool(
            np.all(got[..., 0].real == i32) and np.all(got[..., 3].real == i32)
        ),
        "imag_and_cross_zero": bool(
            np.all(got[..., [0, 3]].imag == 0) and np.all(got[..., [1, 2]] == 0)
        ),
        "truth_q_over_i_max": float(np.abs(cal[k][:, 1] / cal[k][:, 0]).max()),
    }
    got_t = rang_a[tgt]
    o4["SIM-TARGET"] = {
        "as_initialised": bool(
            np.all(got_t[..., [0, 3]] == 1) and np.all(got_t[..., [1, 2]] == 0)
        )
    }
    o4["pass"] = (
        o4[FCAL]["equal"] and o4[FCAL]["bit_identical"]
        and o4["SIM-GCAL"]["equal"] and o4["SIM-GCAL"]["bit_identical"]
        and o4["3C286-SIM"]["stokes_i_equal"] and o4["3C286-SIM"]["imag_and_cross_zero"]
        and o4["SIM-TARGET"]["as_initialised"]
    )  # fmt: skip
    cmp["O4"] = o4
    st = column(copies["A-stokes"], "MODEL_DATA")
    rows = column(copies["A-stokes"], "FIELD_ID") == k
    exp = simtruth.stokes_coherency(cal[k]).astype(np.complex64)
    cmp["O4p"] = {
        "rows": int(rows.sum()),
        "equal": bool(np.all(st[rows] == exp[None])),
        "bit_identical": bool(
            np.all(bits(st[rows]) == bits(np.broadcast_to(exp, st[rows].shape)))
        ),
        "other_rows_unity": bool(
            np.all(st[~rows][..., [0, 3]] == 1) and np.all(st[~rows][..., [1, 2]] == 0)
        ),
    }
    cmp["O4p"]["pass"] = all(
        cmp["O4p"][key] for key in ("equal", "bit_identical", "other_rows_unity")
    )
    for arm in ("O3a", "O3b"):
        cmp[arm]["pass"] = bool(cmp[arm]["pass"])
    result["comparisons"] = cmp
    after = {k: tree_sha(v) for k, v in inputs.items()}
    result["inputs"]["tree_sha256_after"] = after
    result["inputs"]["unchanged"] = after == before
    result["verdict"] = {
        arm: bool(cmp[arm]["pass"])
        for arm in ("O1a", "O1b", "O2", "O3a", "O3b", "O4", "O4p")
    }
    result["timings"] = TIMINGS
    result["wall_s"] = round(time.perf_counter() - started, 2)
    result["host_peak_rss_kb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    (run_dir / "c3a.json").write_text(json.dumps(result, indent=1, default=str))
    print(
        json.dumps(
            {"verdict": result["verdict"], "comparisons": cmp}, indent=1, default=str
        )
    )


if __name__ == "__main__":
    if sys.argv[1] == "casa-setjy":
        casa_setjy(sys.argv[2])
    elif sys.argv[1] == "run":
        run(sys.argv[2])
    else:
        raise SystemExit(__doc__)
