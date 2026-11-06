"""Host side of tasks C6w and C7b (research/c6w-polwire.md): Gpol, KCROSS,
Xf, Df and P in `rang-core calibrate` and `apply` against C6's library
chain (gates 1 and 2), and the applied polarisation calibration against the
truth and CASA 6.7.6.14's own chain on the same data (gate 4, C7b). Worktree
venv; every container step is one network-less run (`check_formats.docker`).

    python examples/check_c6w.py run <run> --version poldx|polholdout

`<run>` is a fresh `/mnt/d/rang/outputs/c6w-<date>-NN`. The version's noisy
MS and truth are read in place from C6's `c6-20261106-sets`. Steps: CASA
prepares one copy (the RFI mask OR'd into FLAG) and copies it three times;
CASA runs CARACal's chain on one (`setjy`, K, G, B, F, Gpol, KCROSS, Xf, Df,
clip, `applycal(parang=True)`); `rang-core calibrate` then `apply` run on
another; the hand-written library chain (`rang.calmodels`,
`rang.cal_chain.run`, `rang.cal_pol`) runs on the third, with the same
basename. Exit 0 only when every gated item passes; `result.json` holds
everything.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import check_formats as cf
from check_gain import rfi_flags
from rang import cal_apply, cal_chain, cal_gain, cal_pol, calmodels, core_ms, simtruth
from rang.formats import caltable

CASA = "/opt/casa/bin/python"
SETS = Path("/mnt/d/rang/outputs/c6-20261106-sets")
RANG_CORE = Path(os.environ.get("C6W_RANG_CORE", ROOT / ".venv/bin/rang-core"))
FIELDS = ("J1939-6342", "3C286-SIM", "SIM-GCAL", "SIM-TARGET")
FCAL, XCAL, GCAL, TARGET = range(4)
FEED_DEG = -90.0
UVRANGE = ">150"
CHUNK_ROWS = 700
COLUMNS = ("DATA", "MODEL_DATA", "FLAG", "FLAG_ROW", "WEIGHT", "WEIGHT_SPECTRUM",
           "SIGMA")  # fmt: skip

# Frozen tolerances (research/c6w-polwire.md section 4).
CLASS_B = {"median": 7e-4, "p95": 3e-3}
P_TRUE = simtruth.XCAL["p"]
CHI_TRUE = simtruth.XCAL["chi_deg"]
TRUTH_TOL = {"chi_median": 1.11, "chi_p95": 2.22, "p_abs": 0.0015,
             "target_chi": 1.11, "target_p_rel": 0.05, "target_sigma_chi": 0.2}  # fmt: skip
CASA_TOL = {"xcal_chi_median": np.degrees(7e-4 / (2 * P_TRUE)),
            "xcal_chi_p95": np.degrees(3e-3 / (2 * P_TRUE)),
            "xcal_p_median": 7e-4 / P_TRUE, "xcal_p_p95": 3e-3 / P_TRUE}  # fmt: skip
# C7a's published 3C286 values (Perley & Butler 2013, NRAO 2019), reported.
PUBLISHED = [("PB2013", 1.05e9, 8.6, 33.0), ("PB2013", 1.45e9, 9.5, 33.0),
             ("PB2013", 1.64e9, 9.9, 33.0), ("NRAO2019", 1.02e9, 8.6, 33.0),
             ("NRAO2019", 1.47e9, 9.8, 33.0)]  # fmt: skip

CONFIG = f"""\
version: 1
fields: {{fcal: [J1939-6342], gcal: [SIM-GCAL], xcal: [3C286-SIM],
         target: [SIM-TARGET]}}
data: {{chunk_rows: {CHUNK_ROWS}}}
calibrate:
  model: {{source: setjy, standard: Stevens-Reynolds 2016}}
  refant: m000
  uvrange: "{UVRANGE}"
  primary:
    terms:
      - {{type: K, name: K, solint: inf}}
      - {{type: G, name: G, solint: inf, preapply: [K], interp: [linear]}}
      - {{type: B, name: B, solint: inf, combine: scan, fillgaps: 70, preapply: [K, G],
         interp: [linear, linear]}}
  secondary:
    terms:
      - {{type: F, name: F, solint: inf, preapply: [K, B], interp: [linear, linear]}}
  polcal:
    model: {{source: nrao, name: 3C286}}
    feed_angle_rotation: {FEED_DEG}
    terms:
      - {{type: Gpol, name: Gpol, solint: 60s, preapply: [K, G, B]}}
      - {{type: KCROSS, name: Kcross, solint: inf, preapply: [K, G, B, Gpol]}}
      - {{type: Xf, name: Xf, solint: inf, combine: scan,
         preapply: [K, G, B, Gpol, Kcross]}}
      - {{type: Df, name: Df, field: [fcal], solint: inf, combine: scan,
         clip: [-0.6, 0.6], preapply: [K, G, B, Kcross, Xf]}}
apply:
  parang: true
  targets:
    - {{field: [xcal], tables: [K, G, B, Gpol, Kcross, Xf, Df],
       interp: [linear, linear, linear, linear, nearest, nearest, nearest]}}
    - {{field: [fcal], tables: [K, G, B, Kcross, Xf, Df],
       interp: [linear, linear, linear, nearest, nearest, nearest]}}
    - {{field: [gcal, target], tables: [K, F, B, Kcross, Xf, Df],
       gainfield: [J1939-6342, nearest, J1939-6342, "", "", ""],
       interp: [linear, linear, linear, nearest, nearest, nearest]}}
run: {{stages: [calibrate, apply]}}
"""
LIN, NEAR = "linear", "nearest"
POOL = cal_apply.POOLED
# (field, table names, interp, table fields) of the apply, as CONFIG writes it.
APPLY = [
    (XCAL, ["K", "G", "B", "Gpol", "Kcross", "Xf", "Df"], [LIN] * 4 + [NEAR] * 3,
     [POOL] * 7),
    (FCAL, ["K", "G", "B", "Kcross", "Xf", "Df"], [LIN] * 3 + [NEAR] * 3, [POOL] * 6),
    (GCAL, ["K", "F", "B", "Kcross", "Xf", "Df"], [LIN] * 3 + [NEAR] * 3,
     [FCAL, GCAL, FCAL, POOL, POOL, POOL]),
    (TARGET, ["K", "F", "B", "Kcross", "Xf", "Df"], [LIN] * 3 + [NEAR] * 3,
     [FCAL, GCAL, FCAL, POOL, POOL, POOL]),
]  # fmt: skip


def write(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, default=_default) + "\n")


def _default(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    return str(x)


def stats(x):
    x = np.asarray(x, float)
    if not x.size:
        return {"n": 0}
    return {"n": int(x.size), "median": float(np.median(x)),
            "p95": float(np.percentile(x, 95)), "max": float(x.max())}  # fmt: skip


def column_sha(ms, name):
    with core_ms.open_table(ms) as t:
        if name not in t.colnames():
            return None
        v = t.getcol(name)
    return hashlib.sha256(np.ascontiguousarray(v).tobytes()).hexdigest()


def table_equal(a, b):
    """Every main cell, keyword and subtable cell of two CASA tables (C2e)."""
    import check_c2e

    return check_c2e.table_equal(a, b)


def rang_core(*argv, log):
    started = time.perf_counter()
    with open(log, "a", encoding="utf-8") as fh:
        done = subprocess.run([str(RANG_CORE), *map(str, argv)], check=False,
                              stdout=fh, stderr=subprocess.STDOUT)  # fmt: skip
    if done.returncode:
        raise SystemExit(f"rang-core {argv[0]} failed, see {log}")
    return time.perf_counter() - started


# --- the CASA side -------------------------------------------------------------------


def casa_calls(ms):
    """CARACal's calls in C1's order (crosscal_worker, polcal_worker
    `xcal_model_fcal_leak`), the settings of CONFIG."""
    t = "/run/casa"
    f, x, g = (FIELDS[i] for i in (FCAL, XCAL, GCAL))
    common = {"vis": ms, "refant": "m000", "minsnr": 3.0, "minblperant": 4}
    mode = {"refantmode": "flex"}
    x286 = {"fluxdensity": [14.7172, 0.0, 0.0, 0.0], "spix": [-0.4507, -0.1798, 0.0357],
            "reffreq": "1.47GHz", "polindex": [0.098], "polangle": [0.575959],
            "rotmeas": 0.0}  # fmt: skip
    cc = [f"{t}/K", f"{t}/G", f"{t}/B"]
    calls = [
        {"task": "setjy", "args": {"vis": ms, "field": f, "standard": "Stevens-Reynolds 2016",
         "scalebychan": True, "usescratch": True}},
        {"task": "setjy", "args": {"vis": ms, "field": x, "standard": "manual", **x286,
         "scalebychan": True, "usescratch": True}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/K", "field": f,
         "gaintype": "K", "solint": "inf", "combine": "", "parang": False}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/G", "field": f,
         "gaintype": "G", "calmode": "ap", "solint": "inf", "combine": "", "parang": False,
         "uvrange": UVRANGE, "gaintable": [f"{t}/K"], "interp": [LIN]}},
        {"task": "bandpass", "args": {**common, "caltable": f"{t}/B", "field": f,
         "bandtype": "B", "solint": "inf", "combine": "scan", "solnorm": False,
         "fillgaps": 70, "parang": False, "uvrange": UVRANGE,
         "gaintable": [f"{t}/K", f"{t}/G"], "interp": [LIN, LIN]}},
        {"task": "copytree", "args": {"src": f"{t}/G", "dst": f"{t}/Gapp"}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/Gapp", "field": g,
         "gaintype": "G", "calmode": "ap", "solint": "inf", "combine": "", "parang": False,
         "uvrange": UVRANGE, "append": True, "smodel": [1.0, 0.0, 0.0, 0.0],
         "gaintable": [f"{t}/K", f"{t}/B"], "interp": [LIN, LIN], "gainfield": [f, f]}},
        {"task": "fluxscale", "args": {"vis": ms, "caltable": f"{t}/Gapp",
         "fluxtable": f"{t}/F", "reference": f, "transfer": ""}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/Gpol", "field": x,
         "gaintype": "G", "calmode": "p", "solint": "60s", "combine": "", "parang": True,
         "uvrange": UVRANGE, "gaintable": cc, "interp": [LIN] * 3}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/Kcross", "field": x,
         "gaintype": "KCROSS", "solint": "inf", "combine": "", "parang": True,
         "uvrange": UVRANGE, "gaintable": cc + [f"{t}/Gpol"], "interp": [LIN] * 4}},
        {"task": "polcal", "args": {**common, "caltable": f"{t}/Xf", "field": x,
         "poltype": "Xf", "solint": "inf", "combine": "scan", "uvrange": UVRANGE,
         "gaintable": cc + [f"{t}/Gpol", f"{t}/Kcross"], "interp": [LIN] * 4 + [NEAR]}},
        {"task": "polcal", "args": {**common, "caltable": f"{t}/Df.raw", "field": f,
         "poltype": "Df", "solint": "inf", "combine": "scan", "uvrange": UVRANGE,
         "gaintable": cc + [f"{t}/Kcross", f"{t}/Xf"], "interp": [LIN] * 3 + [NEAR] * 2}},
        {"task": "copytree", "args": {"src": f"{t}/Df.raw", "dst": f"{t}/Df"}},
        {"task": "flagdata", "args": {"vis": f"{t}/Df", "mode": "clip",
         "clipminmax": [-0.6, 0.6], "datacolumn": "CPARAM", "flagbackup": False}},
    ]  # fmt: skip
    for field, names, interp, tfields in APPLY:
        gainfield = [FIELDS[v] if v is not POOL else "" for v in tfields]
        if field in (GCAL, TARGET):
            gainfield[1] = "nearest"
        calls.append({"task": "applycal", "args": {
            "vis": ms, "field": FIELDS[field], "gaintable": [f"{t}/{n}" for n in names],
            "interp": interp, "gainfield": gainfield, "calwt": [False] * len(names),
            "parang": True, "applymode": "calflag", "flagbackup": False}})  # fmt: skip
    return calls


def prepare_and_casa(run, version):
    src = SETS / version / f"a1-{version}.ms"
    name = src.name
    edits = run / "edits"
    edits.mkdir()
    with core_ms.open_table(src) as t:
        nchan = t.getcol("FLAG", 0, 1).shape[1]
    rfi = rfi_flags(src, SETS / version / f"a1-{version}.rfi_mask.npz", nchan)
    np.savez(edits / "rfi.npz", rows=np.arange(len(rfi)), flag=rfi)
    write(edits / "edit.json", {"flag": "/run/edits/rfi.npz"})
    write(run / "casa-spec.json", casa_calls("/run/casa.ms"))
    steps = [
        f"{CASA} -I /ex/oracle_gain.py qc-copy /src/ms /run/prepared.ms",
        f"{CASA} -I /ex/oracle_pol.py edit /run/prepared.ms /run/edits/edit.json",
        "cp -r /run/prepared.ms /run/casa.ms",
        (
            f"mkdir -p /run/cmd /run/lib /run/casa && cp -r /run/prepared.ms /run/cmd/{name}"
            f" && cp -r /run/prepared.ms /run/lib/{name}"
        ),
        f"{CASA} -I /ex/oracle_pol.py tasks /run/casa-spec.json /run/casa-tasks.json",
        (
            f"{CASA} -I /ex/oracle_pol.py export /run/casa.ms /run/casa-export.npz "
            "CORRECTED_DATA FLAG MODEL_DATA"
        ),
    ]
    mounts = [(run, "/run", "rw"), (HERE, "/ex", "ro"), (src, "/src/ms", "ro")]
    cf.docker(cf.CASA_IMAGE, ["sh", "-c", " && ".join(steps)], mounts,
              f"c6w {version}: prepare and CASA chain")  # fmt: skip
    shutil.rmtree(run / "casa.ms")
    results = json.loads((run / "casa-tasks.json").read_text())
    return name, results


# --- gate 1: the library chain written out --------------------------------------------


def reference(ms, out):
    """C6's library chain by hand: the models, the crosscal through
    `cal_chain.run` (C2e's library), then `rang.cal_pol` in CARACal's order."""
    with core_ms.open_table(ms) as t:
        wc = "WEIGHT_SPECTRUM" if "WEIGHT_SPECTRUM" in t.colnames() else "WEIGHT"
    calmodels.set_model(
        ms, [FCAL], calmodels.Standard(standard="Stevens-Reynolds 2016")
    )
    calmodels.set_model(ms, [XCAL], calmodels.caracal_xcal("3C286"))
    kw = {"solint": "inf", "combine": "", "refant": ["m000"], "refantmode": "flex",
          "minsnr": 3.0, "minblperant": 4, "uvrange": UVRANGE, "max_iterations": 50,
          "stop_criterion": 1e-7, "stop_fraction": 0.99, "model": "column"}  # fmt: skip
    terms = [
        {"type": "K", "name": "K", "fields": [FCAL], **kw, "uvrange": "", "preapply": [],
         "interp": []},
        {"type": "G", "name": "G", "fields": [FCAL], **kw, "calmode": "ap",
         "preapply": ["K"], "interp": [LIN]},
        {"type": "B", "name": "B", "fields": [FCAL], **kw, "combine": "scan",
         "fillgaps": 70, "preapply": ["K", "G"], "interp": [LIN, LIN]},
        {"type": "F", "name": "F", "fields": [GCAL], **kw, "model": "unit",
         "calmode": "ap", "preapply": ["K", "B"], "interp": [LIN, LIN], "base": "G",
         "smodel": [1.0, 0.0, 0.0, 0.0]},
    ]  # fmt: skip
    result = cal_chain.run(ms, terms, out_dir=out, weight_column=wc)
    t = {n: v["table"] for n, v in result["tables"].items()}
    common = {"uvrange": UVRANGE, "frame": "casa", "receptor_angle": float(np.deg2rad(FEED_DEG)),
              "model_column": "MODEL_DATA", "weight_column": wc, "parang": True}  # fmt: skip
    cc = [t["K"], t["G"], t["B"]]
    gp, _, _ = cal_pol.gpol(ms, field_id=XCAL, solint="60s", combine="", refant=["m000"],
                            refantmode="flex", minsnr=3.0, minblperant=4, gaintable=cc,
                            interp=[LIN] * 3, **common)  # fmt: skip
    kc, ks, _ = cal_pol.kcross(ms, field_id=XCAL, solint="inf", combine="", refant=["m000"],
                               estimator="casa", gaintable=cc + [gp], interp=[LIN] * 4,
                               **common)  # fmt: skip
    xf, _, _ = cal_pol.xf(ms, field_id=XCAL, solint="inf", combine="scan",
                          gaintable=cc + [gp, kc], interp=[LIN] * 4 + [NEAR], **common)  # fmt: skip
    df, _, _ = cal_pol.df(ms, field_id=FCAL, solint="inf", combine="scan", refant=["m000"],
                          minsnr=3.0, minblperant=4, min_data_fraction=None,
                          gaintable=cc + [kc, xf], interp=[LIN] * 3 + [NEAR] * 2, **common)  # fmt: skip
    dfc, nclip = cal_pol.clip_df(df, 0.6)
    for n, v in (("Gpol", gp), ("Kcross", kc), ("Xf", xf), ("Df", dfc)):
        caltable.write(v, out / n)
        t[n] = v
    return t, {"kcross_ns": ks.delay_ns.tolist(), "df_clipped": nclip}


def reference_apply(ms, tables):
    """`rang.cal_pol.apply` per field (tables, then P) on DATA and FLAG."""
    c = cal_gain._ms_columns(ms, ["TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID", "DATA",
                                  "FLAG"])  # fmt: skip
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as tb:
        freq = np.asarray(tb.getcol("CHAN_FREQ")[0], float)
    out = {}
    for field, names, interp, tfields in APPLY:
        rows = np.flatnonzero(c["FIELD_ID"] == field)
        ang = cal_pol.row_angles(ms, c["TIME"][rows], c["ANTENNA1"][rows],
                                 c["ANTENNA2"][rows], field, "casa",
                                 float(np.deg2rad(FEED_DEG)))  # fmt: skip
        v, f = cal_pol.apply(c["DATA"][rows], c["FLAG"][rows], c["TIME"][rows],
                             c["ANTENNA1"][rows], c["ANTENNA2"][rows], freq,
                             [tables[n] for n in names], angles=ang, interp=interp,
                             field_id=field, table_fields=tfields)  # fmt: skip
        out[field] = (rows, v, f)
    return out


# --- gate 4 (C7b): what the calibrated data say ----------------------------------------


def _stokes(v):
    """(..., 4) XX, XY, YX, YY -> I, Q, U (complex averages kept complex)."""
    return (
        (v[..., 0] + v[..., 3]) / 2,
        (v[..., 0] - v[..., 3]) / 2,
        (v[..., 1] + v[..., 2]) / 2,
    )


def xcal_pol(v, flag, scans):
    """Per channel (all scans, and per scan) the polcal source's I, Q, U from
    the mean over unflagged cross-correlation cells (a point at the phase
    centre): p and chi (degrees)."""
    ok = ~flag.any(-1)
    out = {}
    for label, pick in [("all", np.ones(len(v), bool))] + [
        (f"scan {s}", scans == s) for s in np.unique(scans)
    ]:
        w = ok & pick[:, None]
        n = w.sum(0)
        i, q, u = (np.where(w, s, 0).sum(0) / np.maximum(n, 1) for s in _stokes(v))
        i, q, u = i.real, q.real, u.real
        good = n > 0
        out[label] = {"p": np.where(good, np.hypot(q, u) / np.where(i != 0, i, 1), np.nan),
                      "chi": np.where(good, np.degrees(np.arctan2(u, q)) / 2, np.nan),
                      "i": i, "n": n}  # fmt: skip
    return out


def _wrap(d):
    """Angle differences of chi (degrees) into [-90, 90)."""
    return (np.asarray(d) + 90.0) % 180.0 - 90.0


def target_pol(ms, v, flag, rows, comps, freq):
    """Per polarised target component: the visibility-domain fit of its I, Q
    and U per channel after subtracting the truth's other components (C7b,
    note section 4.3), and the band estimate derotated by the truth's
    chi(lambda^2) (rang.simtruth: chi0 + rm lambda^2)."""
    uvw = cal_gain._ms_columns(ms, ["UVW"], rows)["UVW"]
    full = simtruth.target_coherency(uvw, freq, comps)
    ok = ~flag.any(-1)
    lam2 = (simtruth.C / freq) ** 2
    out = []
    for k, c in enumerate(comps):
        if c["p"] == 0.0:
            continue
        tk = simtruth.target_coherency(uvw, freq, [c])
        resid = v.astype(np.complex128) - full + tk
        shape = (tk[..., 0] + tk[..., 3]) / 2  # the component's I visibility
        w = np.where(ok, np.abs(shape) ** 2, 0.0)
        den = w.sum(0)
        fit = [np.where(ok, np.conj(shape) * s, 0).sum(0) / np.where(den > 0, den, 1)
               for s in _stokes(resid)]  # fmt: skip
        a_i, a_q, a_u = (f.real for f in fit)
        chi_t = np.radians(c["chi0_deg"]) + c["rm"] * lam2
        z = (a_q + 1j * a_u) * np.exp(-2j * chi_t)
        good = den > 0
        wt = den[good]
        r = (wt * z[good]).sum() / wt.sum()
        var = (wt**2 * np.abs(z[good] - r) ** 2).sum() / wt.sum() ** 2
        i_mean = (wt * a_i[good]).sum() / wt.sum()
        p_meas = abs(r) / i_mean
        sigma = float(np.sqrt(var))
        out.append({
            "index": k, "kind": c["kind"], "flux_jy": c["flux"], "p_true": c["p"],
            "rm": c["rm"], "chi0_deg": c["chi0_deg"],
            "dchi_deg": float(np.degrees(np.angle(r)) / 2), "p_meas": float(p_meas),
            "p_ratio": float(p_meas / c["p"]), "i_scale": float(i_mean),
            "sigma_chi_deg": float(np.degrees(sigma / (2 * abs(r)))),
            "sigma_p_rel": float(sigma / abs(r)),
            "per_channel_dchi_deg": stats(np.abs(np.degrees(np.angle(z[good])) / 2)),
        })  # fmt: skip
    return out


def c7b(run, version, cmd, casa_npz):
    truth = json.loads((SETS / version / "truth.json").read_text())
    d = simtruth.design(version)
    comps = simtruth.target_sky(d)
    c = cal_gain._ms_columns(cmd, ["FIELD_ID", "SCAN_NUMBER", "CORRECTED_DATA", "FLAG",
                                   "MODEL_DATA"])  # fmt: skip
    z = np.load(casa_npz)
    with core_ms.open_table(cmd / "SPECTRAL_WINDOW") as tb:
        freq = np.asarray(tb.getcol("CHAN_FREQ")[0], float)
    rep = {"version": version, "tau_c_true_ns": truth["design"]["tau_c_ns"]}
    # MODEL_DATA: rang's setjy against CASA's (a sanity line, reported).
    m_r, m_c = c["MODEL_DATA"], z["MODEL_DATA"]
    for fid in (FCAL, XCAL):
        rows = c["FIELD_ID"] == fid
        a, b = m_r[rows].astype(np.complex128), m_c[rows].astype(np.complex128)
        scale = np.max(np.abs(b), -1, keepdims=True)
        rep[f"model_{FIELDS[fid]}"] = {
            "max_rel": float(np.max(np.abs(a - b) / scale)),
            "bit_identical": bool(np.array_equal(m_r[rows].view(np.uint32),
                                                  m_c[rows].view(np.uint32)))}  # fmt: skip
    # The model's own p and chi against C7a's published values (reported).
    xm = m_r[c["FIELD_ID"] == XCAL][0].astype(np.complex128)
    i, q, u = (s.real for s in _stokes(xm))
    rep["model_vs_published"] = []
    for table, nu, p_pub, chi_pub in PUBLISHED:
        k = int(np.argmin(np.abs(freq - nu)))
        rep["model_vs_published"].append({
            "table": table, "ghz": nu / 1e9, "channel_ghz": freq[k] / 1e9,
            "model_p_pct": float(100 * np.hypot(q[k], u[k]) / i[k]),
            "model_chi_deg": float(np.degrees(np.arctan2(u[k], q[k])) / 2),
            "published_p_pct": p_pub, "published_chi_deg": chi_pub,
            "dp_points": float(100 * np.hypot(q[k], u[k]) / i[k] - p_pub)})  # fmt: skip
    rep["truth_p"], rep["truth_chi_deg"] = P_TRUE, CHI_TRUE
    # Class B on CORRECTED_DATA (C6 4.2's metric) per field, cells both unflagged.
    v_r, f_r = c["CORRECTED_DATA"], c["FLAG"]
    v_c, f_c = z["CORRECTED_DATA"], z["FLAG"].astype(bool)
    rep["corrected"] = {}
    for fid in range(4):
        rows = c["FIELD_ID"] == fid
        a, b = v_r[rows].astype(np.complex128), v_c[rows].astype(np.complex128)
        ok = ~f_r[rows] & ~f_c[rows]
        scale = np.max(np.abs(b), -1, keepdims=True)
        e = (np.abs(a - b) / np.where(scale > 0, scale, 1))[ok]
        s = stats(e)
        s["pass"] = bool(s["n"] and s["median"] <= CLASS_B["median"]
                         and s["p95"] <= CLASS_B["p95"])  # fmt: skip
        s["flags_rang_only"] = int((f_r[rows] & ~f_c[rows]).sum())
        s["flags_casa_only"] = int((~f_r[rows] & f_c[rows]).sum())
        s["flags_exact"] = bool(np.array_equal(f_r[rows], f_c[rows]))
        rep["corrected"][FIELDS[fid]] = s
    # The polcal source against the truth and against CASA.
    rows = c["FIELD_ID"] == XCAL
    scans = c["SCAN_NUMBER"][rows]
    both = f_r[rows] | f_c[rows]
    pr = xcal_pol(v_r[rows], f_r[rows], scans)
    pc = xcal_pol(v_c[rows], f_c[rows], scans)
    prb = xcal_pol(v_r[rows], both, scans)
    pcb = xcal_pol(v_c[rows], both, scans)
    x = {}
    for label in pr:
        good = np.isfinite(pr[label]["chi"])
        dchi = np.abs(_wrap(pr[label]["chi"][good] - CHI_TRUE))
        gb = np.isfinite(prb[label]["chi"]) & np.isfinite(pcb[label]["chi"])
        x[label] = {
            "p_median": float(np.median(pr[label]["p"][good])),
            "chi_median_deg": float(np.median(pr[label]["chi"][good])),
            "dchi_truth_deg": stats(dchi),
            "casa_p_median": float(np.nanmedian(pc[label]["p"])),
            "casa_chi_median_deg": float(np.nanmedian(pc[label]["chi"])),
            "casa_dchi_truth_deg": stats(np.abs(_wrap(pc[label]["chi"][np.isfinite(
                pc[label]["chi"])] - CHI_TRUE))),
            "dchi_casa_deg": stats(np.abs(_wrap(prb[label]["chi"][gb] - pcb[label]["chi"][gb]))),
            "dp_casa_rel": stats(np.abs(prb[label]["p"][gb] / pcb[label]["p"][gb] - 1)),
        }  # fmt: skip
    a = x["all"]
    gates = {
        "xcal_chi_truth": a["dchi_truth_deg"]["median"] <= TRUTH_TOL["chi_median"]
        and a["dchi_truth_deg"]["p95"] <= TRUTH_TOL["chi_p95"],
        "xcal_p_truth": abs(a["p_median"] - P_TRUE) <= TRUTH_TOL["p_abs"],
        "xcal_chi_casa": a["dchi_casa_deg"]["median"] <= CASA_TOL["xcal_chi_median"]
        and a["dchi_casa_deg"]["p95"] <= CASA_TOL["xcal_chi_p95"],
        "xcal_p_casa": a["dp_casa_rel"]["median"] <= CASA_TOL["xcal_p_median"]
        and a["dp_casa_rel"]["p95"] <= CASA_TOL["xcal_p_p95"],
        "corrected_xcal_class_b": rep["corrected"][FIELDS[XCAL]]["pass"],
        "corrected_target_class_b": rep["corrected"][FIELDS[TARGET]]["pass"],
    }
    rep["xcal"] = x
    # Polarised target components.
    trows = np.flatnonzero(c["FIELD_ID"] == TARGET)
    tr = target_pol(cmd, v_r[trows], f_r[trows], trows, comps, freq)
    tboth = f_r[trows] | f_c[trows]
    trb = target_pol(cmd, v_r[trows], tboth, trows, comps, freq)
    tcb = target_pol(cmd, v_c[trows], tboth, trows, comps, freq)
    targets = []
    for r, rb, cb in zip(tr, trb, tcb):
        gated = r["sigma_chi_deg"] <= TRUTH_TOL["target_sigma_chi"]
        tol_chi = TRUTH_TOL["target_chi"] + 3 * r["sigma_chi_deg"]
        tol_p = TRUTH_TOL["target_p_rel"] + 3 * r["sigma_p_rel"]
        casa_chi = np.degrees(3e-3 / (2 * r["p_true"]))
        casa_p = 3e-3 / r["p_true"]
        entry = {**r, "gated": bool(gated), "tol_chi_deg": tol_chi, "tol_p_rel": tol_p,
                 "casa_dchi_deg": float(_wrap(rb["dchi_deg"] - cb["dchi_deg"])),
                 "casa_p_ratio": float(rb["p_meas"] / cb["p_meas"]),
                 "casa_dchi_truth_deg": cb["dchi_deg"], "casa_p_ratio_truth": cb["p_ratio"],
                 "tol_casa_chi_deg": casa_chi, "tol_casa_p_rel": casa_p}  # fmt: skip
        entry["pass_truth"] = bool(abs(r["dchi_deg"]) <= tol_chi
                                   and abs(r["p_ratio"] - 1) <= tol_p)  # fmt: skip
        entry["pass_casa"] = bool(abs(entry["casa_dchi_deg"]) <= casa_chi
                                  and abs(entry["casa_p_ratio"] - 1) <= casa_p)  # fmt: skip
        targets.append(entry)
        if gated:
            gates[f"target {r['index']} truth"] = entry["pass_truth"]
            gates[f"target {r['index']} casa"] = entry["pass_casa"]
    rep["targets"] = targets
    rep["gates"] = {k: bool(v) for k, v in gates.items()}
    rep["pass"] = bool(all(gates.values()) and any(t["gated"] for t in targets))
    return rep


# --- the run ----------------------------------------------------------------------------


def run_case(run, version):
    run.mkdir(parents=True)
    t0 = time.perf_counter()
    name, casa_results = prepare_and_casa(run, version)
    report = {"version": version, "casa_errors": [r for r in casa_results if r["error"]],
              "casa_seconds": [(r["task"], r["seconds"]) for r in casa_results]}  # fmt: skip
    cmd, lib = run / "cmd" / name, run / "lib" / name
    with core_ms.open_table(cmd) as t:
        flag_in = t.getcol("FLAG")
    config = run / "config.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    log = run / "rang-core.log"
    report["seconds"] = {"calibrate": rang_core("calibrate", config, cmd, log=log)}
    after_cal = {c: column_sha(cmd, c) for c in COLUMNS}
    report["seconds"]["apply"] = rang_core("apply", config, cmd, log=log)
    rdir = run / "cmd" / f"{name}.rang-run" / "calibrate"
    summary = json.loads((rdir / "summary.json").read_text())
    started = time.perf_counter()
    tables, extra = reference(lib, run / "lib" / "tables")
    report["seconds"]["reference"] = time.perf_counter() - started
    # Gate 1.
    g1 = {"tables": {}, "columns": {}}
    for n in ("K", "G", "B", "F", "F.append", "Gpol", "Kcross", "Xf", "Df"):
        g1["tables"][n] = table_equal(rdir / n, run / "lib" / "tables" / n)
    for col in COLUMNS:
        b = column_sha(lib, col)
        g1["columns"][col] = {
            "cmd": after_cal[col],
            "lib": b,
            "equal": after_cal[col] == b,
        }
    from rang.formats import flagversions

    orig = flagversions.load(cmd, "rang_original")[0]
    g1["rang_original_equals_input"] = bool(np.array_equal(orig, flag_in))
    g1["steps"] = [{k: v for k, v in s.items() if k in ("type", "name", "clipped",
                    "solutions")} for s in summary["steps"]]  # fmt: skip
    g1["reference_extra"] = extra
    g1["pass"] = bool(all(v["equal"] for v in g1["tables"].values())
                      and all(v["equal"] for v in g1["columns"].values())
                      and g1["rang_original_equals_input"])  # fmt: skip
    report["gate1"] = g1
    # Gate 2.
    ref = reference_apply(lib, tables)
    c = cal_gain._ms_columns(cmd, ["CORRECTED_DATA", "FLAG"])
    g2 = {}
    for field, (rows, v, f) in ref.items():
        g2[FIELDS[field]] = {
            "rows": len(rows),
            "corrected_bit_identical": bool(np.array_equal(
                c["CORRECTED_DATA"][rows].view(np.uint32), v.view(np.uint32))),
            "flag_identical": bool(np.array_equal(c["FLAG"][rows], f))}  # fmt: skip
    g2["pass"] = bool(all(e["corrected_bit_identical"] and e["flag_identical"]
                          for e in g2.values()))  # fmt: skip
    report["gate2"] = g2
    # Gate 4 (C7b).
    report["c7b"] = c7b(run, version, cmd, run / "casa-export.npz")
    report["kcross_ns"] = {
        "rang": caltable.read(rdir / "Kcross").params[::16, 0, 0].tolist(),
        "casa": caltable.read(run / "casa" / "Kcross").params[::16, 0, 0].tolist(),
    }
    rec = next(r for r in casa_results if r["task"] == "fluxscale")["return"]
    step = next(s for s in summary["steps"] if s["type"] == "F")
    report["fluxscale"] = {"rang": step["fluxscale"], "casa": rec}
    rd, cd = caltable.read(rdir / "Df"), caltable.read(run / "casa" / "Df")
    report["df_flags"] = {"rang": int(rd.flags.sum()), "casa": int(cd.flags.sum()),
                          "differ": int((rd.flags != cd.flags).sum())}  # fmt: skip
    report["wall_seconds"] = time.perf_counter() - t0
    report["pass"] = bool(g1["pass"] and g2["pass"] and report["c7b"]["pass"]
                          and not report["casa_errors"])  # fmt: skip
    return report


def snapshot(run):
    import check_c2e

    check_c2e.snapshot(run)


def main(argv):
    if len(argv) < 5 or argv[1] != "run" or "--version" not in argv:
        print(__doc__)
        return 2
    run = Path(argv[2])
    version = argv[argv.index("--version") + 1]
    snapshot(run)
    report = run_case(run, version)
    report["timings"] = cf.TIMINGS
    write(run / "result.json", report)
    brief = {k: report[k] for k in ("pass", "wall_seconds", "kcross_ns", "df_flags")}
    brief["gate1"] = report["gate1"]["pass"]
    brief["gate2"] = report["gate2"]["pass"]
    brief["c7b"] = report["c7b"]["gates"]
    print(json.dumps(brief, indent=1, default=_default))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
