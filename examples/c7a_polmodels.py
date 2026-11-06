"""C7a oracles: polarised calibrator models against CASA `setjy`, cell by
cell, and against published polarisation values (research/c7a-polmodels.md).

    python examples/c7a_polmodels.py run <run>             # cases M1-M8, P1, P2, T
    python examples/c7a_polmodels.py run <run> --held-out  # case H1 only

`<run>` is a fresh directory under /mnt/d/rang/outputs/. Inputs are copied
into it and hashed before and after; CASA runs in `rang-o-casa:6.7.6.14`
through C3a's container helper (`c3a_models.py casa-setjy`, network off, this
user, only `<run>` writable). Run it under `flock ~/.rang-heavy.lock`. The
frozen gates are section 6 of the note; the result goes to `<run>/c7a.json`.
"""

import hashlib
import importlib.util
import json
import math
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
_spec = importlib.util.spec_from_file_location("c3a_models", HERE / "c3a_models.py")
c3a = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c3a)

SLICE, A1 = c3a.SLICE, c3a.A1 / "a1-small.ms"
TOL_G1 = 1e-6  # |V_rang - V_casa| / I per cell (C1 step 8)
TOL_IMAG = 1e-9  # imaginary parts, of I (C3a)
SPIX_286 = [-0.4507, -0.1798, 0.0357]
SPIX_138 = [-0.4981, -0.1552, -0.0102, 0.0223]
X286 = {
    "fluxdensity": [14.7172],
    "spix": SPIX_286,
    "reffreq": "1.47GHz",
    "polindex": [0.098],
    "polangle": [0.575959],
    "rotmeas": 0.0,
}
X138 = {
    "fluxdensity": [8.33843],
    "spix": SPIX_138,
    "reffreq": "1.47GHz",
    "polindex": [0.078],
    "polangle": [-0.16755],
    "rotmeas": 0.0,
}
# Taylor & Legodi J1331+3030 as CARACal's read_taylor_legodi_row builds it.
TL286 = {
    "fluxdensity": [float("14.673")],
    "spix": [float("-0.630")],
    "reffreq": "1.4GHz",
    "polindex": [float("9.90") / 100.0],
    "polangle": [float("29.2") * math.pi / 180],
    "rotmeas": float("-0.3"),
}
CASES = {
    "M1": ("S", "J1939-6342", X286),
    "M2": ("S", "J1939-6342", X138),
    "M3": ("A", "3C286-SIM", X286),
    "M4": (
        "A",
        "3C286-SIM",
        {
            **X286,
            "polindex": [0.098, 0.02, -0.01],
            "polangle": [0.575959, 0.05],
            "rotmeas": 50.0,
        },
    ),
    "M5": (
        "S",
        "J1939-6342",
        {
            "fluxdensity": [14.7172, 0.6, 1.2, 0.05],
            "spix": SPIX_286,
            "reffreq": "1.47GHz",
            "polindex": [0.098, 0.03],
            "polangle": [0.575959, -0.04],
            "rotmeas": 10.0,
        },
    ),
    "M6": (
        "A",
        "3C286-SIM",
        {
            "fluxdensity": [14.7172, 0.4, 1.3, 0.0],
            "spix": SPIX_286,
            "reffreq": "1.47GHz",
            "rotmeas": -30.0,
        },
    ),
    "M7": ("A", "3C286-SIM", TL286),
    "M8": (
        "A",
        "SIM-GCAL",
        {"fluxdensity": [4.0, 0.0, 0.0, 0.04], "spix": [-0.6], "reffreq": "1.4GHz"},
    ),
}
HELD_OUT = {
    "H1": ("A", [
        ("3C286-SIM", {"fluxdensity": [8.33843, -0.3, 0.5, -0.02], "spix": SPIX_138,
                       "reffreq": "1.47GHz", "polindex": [0.078, 0.03],
                       "polangle": [-0.16755, -0.02, 0.01], "rotmeas": -20.0}),
        ("SIM-GCAL", {"fluxdensity": [4.0, 0.1, -0.05, 0.0], "spix": [-0.6],
                      "reffreq": "1.4GHz", "rotmeas": 15.0}),
    ]),
}  # fmt: skip
# Published (section 6): (GHz, p %, chi deg, table).
PUBLISHED = {
    "3C286": [(1.05, 8.6, 33, "PB2013"), (1.45, 9.5, 33, "PB2013"), (1.64, 9.9, 33, "PB2013"),
              (1.02, 8.6, 33, "NRAO2019"), (1.47, 9.8, 33, "NRAO2019")],
    "3C138": [(1.05, 5.6, -14, "PB2013"), (1.45, 7.5, -11, "PB2013"), (1.64, 8.4, -10, "PB2013"),
              (1.02, 5.5, -13, "NRAO2019"), (1.47, 7.8, -9.6, "NRAO2019")],
}  # fmt: skip
TAYLOR_LEGODI = {"J1331+3030": (9.90, 29.2, -0.3), "J0521+1638": (7.71, -15.1, -2.4)}


def manual_spec(model):
    from rang import calmodels

    return calmodels.spec_from_config({"standard": "manual", **model})


def field_rows(ms, name):
    from rang import calmodels

    names = calmodels.metadata(ms)["field_names"]
    return c3a.column(ms, "FIELD_ID") == names.index(name)


def compare(rang_ms, casa_ms, fields):
    """G1, G2, G3 of section 6 for `fields` [(name, spec)]."""
    rang, casa = c3a.column(rang_ms, "MODEL_DATA"), c3a.column(casa_ms, "MODEL_DATA")
    freq = c3a.column(Path(rang_ms) / "SPECTRAL_WINDOW", "CHAN_FREQ")[0]
    out, inside = {}, np.zeros(len(rang), bool)
    for name, spec in fields:
        rows = field_rows(rang_ms, name)
        inside |= rows
        i = spec.stokes(freq)[:, 0]
        r, c = rang[rows], casa[rows]
        diff = np.abs(r.astype(np.complex128) - c.astype(np.complex128))
        g1 = float((diff / i[None, :, None]).max())
        ulps = max(c3a.f32_ulps(r[..., k].real, c[..., k].real) for k in range(4))
        imag = float((np.abs(r.imag.astype(float) - c.imag) / i[None, :, None]).max())
        q = (c[..., 0].real.astype(float) - c[..., 3].real) / 2
        res = {
            "rows": int(rows.sum()),
            "g1_max_rel": g1,
            "g2_real_max_ulps": ulps,
            "g2_imag_max_rel": imag,
            "casa_imag_max_jy": float(np.abs(c.imag).max()),
            "bit_identical_cell_fraction": float(
                np.mean(np.all(c3a.bits(r) == c3a.bits(c), axis=-1))
            ),
            "casa_q_u_v_max_jy": [
                float(np.abs(q).max()),
                float(np.abs(c[..., 1].real).max()),
                float(np.abs(c[..., 1].imag).max()),
            ],
            "casa_path": spec.casa_path,
        }
        res["pass_g1"] = g1 <= TOL_G1
        res["pass_g2"] = ulps == 0 and imag <= TOL_IMAG
        out[name] = res
    g3 = bool(np.array_equal(c3a.bits(rang[~inside]), c3a.bits(casa[~inside])))
    return {
        "fields": out,
        "g3_other_rows_identical": g3,
        "pass": g3 and all(v["pass_g1"] and v["pass_g2"] for v in out.values()),
    }


def pol_of(i, q, u):
    return 100 * np.hypot(q, u) / i, np.degrees(0.5 * np.arctan2(u, q))


def class_t(casa_m1, casa_m2):
    from rang import calmodels

    out = {}
    for src, ms in (("3C286", casa_m1), ("3C138", casa_m2)):
        m = calmodels.caracal_xcal(src)
        rows = field_rows(ms, "J1939-6342")
        c = c3a.column(ms, "MODEL_DATA")[rows].astype(np.complex128)
        i, q, u = (
            (c[..., 0].real + c[..., 3].real) / 2,
            (c[..., 0].real - c[..., 3].real) / 2,
            c[..., 1].real,
        )
        p_c, chi_c = pol_of(i, q, u)
        entry = {"rows": []}
        for ghz, p, chi, table in PUBLISHED[src]:
            s = m.stokes(np.array([ghz * 1e9]))[0]
            pm, chim = pol_of(s[0], s[1], s[2])
            entry["rows"].append(
                {
                    "ghz": ghz,
                    "table": table,
                    "p_pub": p,
                    "chi_pub": chi,
                    "p_model": float(pm),
                    "chi_model": float(chim),
                    "dp": float(pm - p),
                    "dchi": float(chim - chi),
                }
            )
        ref = next(r for r in entry["rows"] if r["ghz"] == 1.47)
        entry["t1_model"] = abs(ref["dp"]) <= 0.05 and abs(ref["dchi"]) <= 0.05
        entry["casa_model_data_p_range"] = [float(p_c.min()), float(p_c.max())]
        entry["casa_model_data_chi_range"] = [float(chi_c.min()), float(chi_c.max())]
        entry["t1_casa"] = bool(
            np.all(np.abs(p_c - ref["p_pub"]) <= 0.05)
            and np.all(np.abs(chi_c - ref["chi_pub"]) <= 0.05)
        )
        out[src] = entry
    out["taylor_legodi"] = TAYLOR_LEGODI
    return out  # fmt: skip


def frame_checks(a_casa_m3, a_casa_m4, a_casa_p1):
    def constant(ms):
        rows = field_rows(ms, "3C286-SIM")
        m = c3a.bits(c3a.column(ms, "MODEL_DATA")[rows])
        return bool(np.all(m == m[:1]))

    # rang's table reader cannot read FEED's string-array POLARIZATION_TYPE,
    # so CASA's casatools reads it (casa-feed, before setjy, into feed.json).
    feed = json.loads((Path(a_casa_m3).parent / "feed.json").read_text())
    p1 = bool(
        np.array_equal(
            c3a.bits(c3a.column(a_casa_p1, "MODEL_DATA")),
            c3a.bits(c3a.column(a_casa_m3, "MODEL_DATA")),
        )
    )
    return {"p1_receptor_angle_0_equals_minus_90": p1,
            "p2_constant_over_parallactic_angle": {"M3": constant(a_casa_m3), "M4": constant(a_casa_m4)},
            "feed": feed}  # fmt: skip


def set_receptor_angle(ms, value):
    from rang import core_ms_write

    with core_ms_write.open_table(Path(ms) / "FEED", readonly=False) as t:
        ra = np.asarray(t.getcol("RECEPTOR_ANGLE"))
        ra[...] = value
        t.putcol("RECEPTOR_ANGLE", ra)


def run(run_dir, held_out=False):
    sys.path.insert(0, str(ROOT / "python"))
    from rang import calmodels

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    code = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in ("python/rang/calmodels.py", "examples/c7a_polmodels.py", "examples/c3a_models.py")}  # fmt: skip
    inputs = {"S": SLICE, "A": A1}
    before = {k: c3a.timed(f"hash {k}", c3a.tree_sha, v) for k, v in inputs.items()}
    result = {"criteria": {"tol_g1": TOL_G1, "tol_imag": TOL_IMAG}, "code_sha256": code,
              "inputs": {k: str(v) for k, v in inputs.items()}, "tree_sha256_before": before,
              "held_out": held_out}  # fmt: skip
    cases = (
        {k: (d, [(f, m)]) for k, (d, f, m) in CASES.items()} if not held_out
        else {k: (d, fm) for k, (d, fm) in HELD_OUT.items()}
    )  # fmt: skip
    calls = []
    for tag, (data, fields) in cases.items():
        for side in ("casa", "rang"):
            shutil.copytree(inputs[data], run_dir / f"{tag}-{side}.ms")
        for name, model in fields:
            calls.append({"vis": f"/run/{tag}-casa.ms", "field": name, "standard": "manual",
                          **model, "scalebychan": True, "usescratch": True})  # fmt: skip
    if not held_out:
        shutil.copytree(A1, run_dir / "P1-casa.ms")
        set_receptor_angle(run_dir / "P1-casa.ms", 0.0)
        calls.append({"vis": "/run/P1-casa.ms", "field": "3C286-SIM", "standard": "manual",
                      **X286, "scalebychan": True, "usescratch": True})  # fmt: skip
    (run_dir / "setjy-calls.json").write_text(json.dumps(calls, indent=1))
    if not held_out:
        c3a.docker(
            c3a.CASA_IMAGE,
            ["/opt/casa/bin/python", "-I", "/ex/c7a_polmodels.py", "casa-feed",
             "/run/feed.json", "S=/run/M1-rang.ms", "A=/run/M3-rang.ms",
             "A-P1=/run/P1-casa.ms"],
            run_dir,
            "CASA read FEED",
        )  # fmt: skip
    c3a.docker(
        c3a.CASA_IMAGE,
        ["/opt/casa/bin/python", "-I", "/ex/c3a_models.py", "casa-setjy", "/run/setjy-calls.json"],
        run_dir,
        f"CASA setjy ({len(calls)} calls)",
    )  # fmt: skip
    result["setjy"] = json.loads((run_dir / "setjy-calls.json.result.json").read_text())
    result["cases"] = {}
    for tag, (data, fields) in cases.items():
        specs = [(name, manual_spec(model)) for name, model in fields]
        receipts = []
        for name, spec in specs:
            receipts.append(
                c3a.timed(f"rang set_model {tag} {name}", calmodels.set_model,
                          run_dir / f"{tag}-rang.ms", name, spec)
            )  # fmt: skip
        res = compare(run_dir / f"{tag}-rang.ms", run_dir / f"{tag}-casa.ms", specs)
        res["receipt_spec"] = [r["spec"] for r in receipts]
        result["cases"][tag] = res
    (run_dir / "c7a-cases.json").write_text(json.dumps(result, indent=1, default=str))
    if not held_out:
        result["frame"] = frame_checks(run_dir / "M3-casa.ms", run_dir / "M4-casa.ms",
                                       run_dir / "P1-casa.ms")  # fmt: skip
        result["class_t"] = class_t(run_dir / "M1-casa.ms", run_dir / "M2-casa.ms")
    after = {k: c3a.tree_sha(v) for k, v in inputs.items()}
    result["inputs_unchanged"] = after == before
    result["timings"] = c3a.TIMINGS
    result["wall_s"] = round(time.perf_counter() - started, 2)
    (run_dir / "c7a.json").write_text(json.dumps(result, indent=1, default=str))
    summary = {tag: v["pass"] for tag, v in result["cases"].items()}
    print(json.dumps({"cases": summary, "frame": result.get("frame"),
                      "inputs_unchanged": result["inputs_unchanged"]}, indent=1))  # fmt: skip


def casa_feed(out, *tagged):
    """Inside rang-o-casa: FEED POLARIZATION_TYPE and RECEPTOR_ANGLE."""
    from casatools import table

    res = {}
    for item in tagged:
        tag, ms = item.split("=", 1)
        tb = table()
        tb.open(ms + "/FEED")
        pt = tb.getcol("POLARIZATION_TYPE")  # (2, nrow)
        ra = tb.getcol("RECEPTOR_ANGLE")
        tb.close()
        res[tag] = {
            "polarization_type": sorted({"".join(str(x) for x in pt[:, k]) for k in range(pt.shape[1])}),
            "receptor_angle_rad": sorted({tuple(float(x) for x in ra[:, k]) for k in range(ra.shape[1])}),
        }  # fmt: skip
    Path(out).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "run":
        run(sys.argv[2], held_out="--held-out" in sys.argv[3:])
    elif len(sys.argv) >= 3 and sys.argv[1] == "casa-feed":
        casa_feed(sys.argv[2], *sys.argv[3:])
    else:
        raise SystemExit(__doc__)
