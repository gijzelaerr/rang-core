# SPDX-License-Identifier: MIT
"""The UHF gate's post steps (research/uhf-gate.md), on nash, on the block's own
MS copy in its run root. E2-N's chain (e2n-scripts, e2-acceptance-scripts) with
the UHF changes of the frozen protocol and nothing else:

- fields per block (UG_BLOCK = D, H, or A1 for the smoke of section 8.3);
- the five 100 MHz bins of section 5.1 (544-1044 MHz);
- the scorer's field limit 1.0 deg (section 5) for gate 3c and the target rows;
- gate 3c and the target rows on the unaveraged `*-3c.yaml` image (section 4);
- the CASA arm of section 7: e2n-followup's flag-state split, 1934-638 from
  rang's MODEL_DATA (no first setjy), 3C 286 by setjy manual (NRAO_XCAL);
- the new rows of section 5: the model row, and on H the J0408-6545 leakage
  (inner 0.5 deg, 0.5 %, rang <= 1.2 x CASA) and flux-transfer (1 %) rows.

    python ug.py STEP MS R [ARGS]

Steps (in ug_chain.sh's order):
    model-row MS R LSM          rang's MODEL_DATA on 2,000 rows of the block's first
                                fcal scan against a float64 direct sum of the catalogue
                                                                 -> R/model-row.json
    c3-flag MS R                FLAG = the version rang's selfcal saved (FLAG after
                                apply and image), so the 3c image sees the image
                                stage's flags                    -> R/c3-flag.json
    c3-unit MS R on|off         matched state for WSClean (WEIGHT_SPECTRUM away, unit
                                WEIGHT; FLAG kept)               -> R/c3-unit-{on,off}.json
    ws3c MS R dirty|clean N     WSClean 3.7 on CORRECTED_1GC, the c3 run's gemclean
                                argv                             -> R/ws3c/
    score3c MS R                e2_score3c_a at 1.0 deg          -> R/g3c.json
    rows-snap MS R ARM DATA FLAG MODEL OUT.npy
    rows-score MS R             secondary, 3C 286 parity, (H) J0408-6545 flux
                                transfer; reported rows          -> R/rows.json
    leakage MS R COLUMN ARM     J0408-6545 IQUV, unit weights    -> R/leakage/ARM.json
    leak-score MS R             (H) each <= 0.5 %, rang <= 1.2 x CASA -> R/row-leakage.json
    casa-model MS R CONFIG      rang's set_model of the fcal catalogue into MODEL_DATA
                                (the call calibrate makes) and its check against the
                                model row's saved values          -> R/casa-model.json
    casa-prep-a / casa-run-a / casa-prep-b / casa-run-b MS R
                                section 7's CASA solves          -> R/casa/tables/
    casa-corr-prep / casa-applycal MS R
    target-wsclean MS R N       WSClean on CASA's CORRECTED_DATA, the c3 argv -> R/oracle-c3/
    target-score MS R           compact (1.0 deg), noise, dynamic range -> R/row-target.json
    selfcal-score MS R          rms after / before at 1.0 deg    -> R/row-selfcal.json
    reported MS R               fluxscale of both arms, flag fractions -> R/reported.json
"""

import json
import math
import multiprocessing
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RES = ROOT / "research" / "results"

BLOCK = os.environ.get("UG_BLOCK", "D")
FIELDS = {
    "D": {"fcal": "J1939-6342", "xcal": "J1331+3030", "gcal": "J1609+2641",
          "target": "ILTJ153010", "leak": None},
    "H": {"fcal": "J1939-6342", "xcal": "J1331+3030", "gcal": "J1605-1734",
          "target": "HD142184", "leak": "J0408-6545"},
    # the smoke (section 8.3): A1 small; SIM-GCAL stands in for J0408-6545 so that
    # the H-only rows run on development data first (their scores mean nothing)
    "A1": {"fcal": "J1939-6342", "xcal": "3C286-SIM", "gcal": "SIM-GCAL",
           "target": "SIM-TARGET", "leak": "SIM-GCAL"},
}[BLOCK]  # fmt: skip
# e2n-scripts read their fields from these at import
os.environ.update(E2N_FCAL=FIELDS["fcal"], E2N_XCAL=FIELDS["xcal"], E2N_GCAL=FIELDS["gcal"],
                  E2N_TARGET=FIELDS["target"], E2N_LEAK=FIELDS["leak"] or "")  # fmt: skip
sys.path[:0] = [str(RES / "e2n-scripts"), str(RES / "e2-acceptance-scripts")]

import e2_post as P  # noqa: E402
import e2n_nash  # noqa: E402,F401  (patches e2_post.docker with apptainer)

EDGES = [544e6, 644e6, 744e6, 844e6, 944e6, 1044e6]  # section 5.1
RADIUS_DEG = 1.0  # section 5: the scorer's field limit
LEAK_RADIUS_DEG = 0.5
LEAK_MAX = 0.005
LEAK_RATIO = 1.2
MODEL_TOL = 1e-5
MODEL_ROWS = 2000
C = 299792458.0
X286 = {
    "fluxdensity": [14.7172, 0.0, 0.0, 0.0],
    "spix": [-0.4507, -0.1798, 0.0357],
    "reffreq": "1.47GHz",
    "polindex": [0.098],
    "polangle": [0.575959],
    "rotmeas": 0.0,
}  # fmt: skip  (e2n_casa3b.X286: NRAO_XCAL, uhf-gate.md section 3)


def write(path, payload):
    P.write(Path(path), payload)
    print(json.dumps(payload, indent=1, default=str)[:4000])


def field_id(ms, name):
    from rang import core_ms

    with core_ms.open_table(Path(ms) / "FIELD") as t:
        return [str(n) for n in t.getcol("NAME")].index(name)


def scans_of(ms, name):
    from rang import core_ms

    fid = field_id(ms, name)
    with core_ms.open_table(ms) as t:
        f = np.asarray(t.getcol("FIELD_ID"))
        s = np.asarray(t.getcol("SCAN_NUMBER"))
    return sorted({int(x) for x in s[f == fid]})


def freqs(ms):
    from rang import core_ms

    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        return np.asarray(t.getcol("CHAN_FREQ"), np.float64)[0]


def rang_run(r):
    """The run directory as archived (R/rang-run) or as moved by restore."""
    m = Path(r) / "rang-run-moved"
    return m if m.is_dir() else Path(r) / "rang-run"


# --- the model row (section 3) ------------------------------------------------------


def _sexa(text, hours):
    sign = -1.0 if text.strip().startswith("-") else 1.0
    parts = text.strip().lstrip("+-").replace(":", ".").split(".", 2)
    d, m, s = float(parts[0]), float(parts[1]), float(parts[2])
    val = sign * (d + m / 60 + s / 3600)
    return math.radians(val * 15 if hours else val)


def read_catalogue(path):
    """WSClean's component list, parsed here from the format's definition (not
    through rang): every component a POINT, ordinary or logarithmic spectrum."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    head = lines[0]
    ref0 = float(head.split("ReferenceFrequency='")[1].split("'")[0])
    out = []
    for line in lines[1:]:
        if not line.strip() or line.startswith("#"):
            continue
        a, b = line.index("["), line.index("]")
        pre = line[:a].rstrip(",").split(",")
        post = line[b + 1 :].lstrip(",").split(",")
        name, kind, ra, dec, flux = pre[0], pre[1], pre[2], pre[3], float(pre[4])
        if kind.strip().upper() != "POINT":
            raise SystemExit(f"{name}: {kind} is not a point component")
        coeffs = [float(x) for x in line[a + 1 : b].split(",") if x.strip()]
        log_si = post[0].strip().lower() == "true"
        ref = float(post[1]) if post[1].strip() else ref0
        out.append(
            (name, _sexa(ra, True), _sexa(dec, False), flux, coeffs, log_si, ref)
        )
    return out


def spectrum(comp, nu):
    _, _, _, flux, coeffs, log_si, ref = comp
    x = nu / ref
    if log_si:
        lx = np.log(x)
        return flux * np.exp(sum(c * lx ** (k + 1) for k, c in enumerate(coeffs)))
    return flux + sum(c * (x - 1) ** (k + 1) for k, c in enumerate(coeffs))


_G = {}  # the catalogue for the workers (fork: shared, not pickled per task)


def _dft_rows(uvw):
    nu, ll, m, n1, spec = _G["nu"], _G["l"], _G["m"], _G["n1"], _G["spec"]
    out = np.zeros((len(uvw), len(nu)), np.complex128)
    # the MS sign, exp(+2 pi i ...) (research/gemclean.md 2.7, g6-predict.md: WSClean's
    # predict without conjugation); the smoke found -2j gave the conjugate
    k = 2j * np.pi * nu / C
    for i, (u, v, w) in enumerate(uvw):
        path = u * ll + v * m + w * n1  # (src,)
        out[i] = (spec * np.exp(np.outer(path, k))).sum(0)
    return out


def model_row(ms, r, lsm):
    from rang import core_ms

    ms, r = Path(ms), Path(r)
    fcal = FIELDS["fcal"]
    fid = field_id(ms, fcal)
    first = scans_of(ms, fcal)[0]
    with core_ms.open_table(ms / "FIELD") as t:
        ra0, dec0 = np.asarray(t.getcol("PHASE_DIR"), np.float64)[fid].reshape(-1)[:2]
    with core_ms.open_table(ms) as t:
        sel = np.flatnonzero((np.asarray(t.getcol("FIELD_ID")) == fid)
                             & (np.asarray(t.getcol("SCAN_NUMBER")) == first))  # fmt: skip
        stride = max(1, len(sel) // MODEL_ROWS)
        rows = sel[::stride][:MODEL_ROWS]
        uvw = np.stack(
            [np.asarray(t.getcol("UVW", int(x), 1), np.float64)[0] for x in rows]
        )
        col = "MODEL_DATA" if "MODEL_DATA" in t.colnames() else "RANG_MODEL_DATA"
        model = np.stack([np.asarray(t.getcol(col, int(x), 1))[0] for x in rows])
        ddid = {int(np.asarray(t.getcol("DATA_DESC_ID", int(x), 1))[0]) for x in rows}
    if ddid != {0}:
        raise SystemExit(f"rows span data descriptions {ddid}")
    nu = freqs(ms)
    cat = read_catalogue(lsm)
    ra = np.array([c[1] for c in cat])
    dec = np.array([c[2] for c in cat])
    ll = np.cos(dec) * np.sin(ra - ra0)
    m = np.sin(dec) * np.cos(dec0) - np.cos(dec) * np.sin(dec0) * np.cos(ra - ra0)
    n1 = np.sqrt(1 - ll * ll - m * m) - 1
    spec = np.stack([spectrum(c, nu) for c in cat])  # (src, chan)
    t0 = time.perf_counter()
    nproc = int(os.environ.get("RAYON_NUM_THREADS", "4"))
    parts = np.array_split(np.arange(len(rows)), nproc * 4)
    _G.update(nu=nu, l=ll, m=m, n1=n1, spec=spec)
    # fork, not 3.14's default forkserver: the workers read _G as set here
    with multiprocessing.get_context("fork").Pool(nproc) as pool:
        got = pool.map(_dft_rows, [uvw[p] for p in parts if len(p)])
    ref = np.concatenate(got)  # Stokes I visibilities (row, chan)
    seconds = time.perf_counter() - t0
    np.save(r / "model-row-rang.npy", model)
    np.save(r / "model-row-rows.npy", rows)
    peak = float(np.abs(ref).max())
    # linear feeds, unpolarised model: XX = YY = I, XY = YX = 0
    want = np.stack([ref, np.zeros_like(ref), np.zeros_like(ref), ref], -1)
    d = np.abs(model.astype(np.complex128) - want)
    worst = float(d.max() / peak)
    per_corr = [float(d[..., k].max() / peak) for k in range(4)]
    rec = {"ms": str(ms), "column": col, "field": fcal, "scan": first, "rows": len(rows),
           "stride": int(stride), "channels": len(nu), "components": len(cat),
           "catalogue": str(lsm), "peak_abs_model_jy": peak,
           "max_abs_diff_over_peak": worst, "per_correlation": per_corr,
           "median_abs_diff_over_peak": float(np.median(d) / peak),
           "tolerance": MODEL_TOL, "met": worst <= MODEL_TOL,
           "direct_sum_seconds": seconds, "processes": nproc,
           "convention": "V = sum S(nu) exp(+2 pi i nu (u l + v m + w (n - 1)) / c); "
                         "spectra by the WSClean format's definition"}  # fmt: skip
    write(r / "model-row.json", rec)
    return 0


def casa_model(ms, r, config):
    """MODEL_DATA of the fcal for the CASA arm (section 3, A0 rule 3): rang's
    own call, after `restore` dropped rang's column; then the model row's
    saved rows are read back and compared."""
    from rang import calmodels, core_ms, core_pipeline

    ms, r = Path(ms), Path(r)
    cfg = json.loads((rang_run(r) / "config.resolved.json").read_text(encoding="utf-8"))
    spec = core_pipeline.model_spec(cfg["calibrate"]["model"], Path(config))
    t0 = time.perf_counter()
    receipt = calmodels.set_model(ms, [FIELDS["fcal"]], spec)
    seconds = time.perf_counter() - t0
    rows = np.load(r / "model-row-rows.npy")
    saved = np.load(r / "model-row-rang.npy")
    with core_ms.open_table(ms) as t:
        now = np.stack([np.asarray(t.getcol("MODEL_DATA", int(x), 1))[0] for x in rows])
    rec = {"receipt": receipt, "seconds": seconds, "rows_checked": len(rows),
           "equal_to_rang_run": bool(np.array_equal(now, saved)),
           "max_abs_diff": float(np.abs(now - saved).max())}  # fmt: skip
    write(r / "casa-model.json", rec)
    return 0 if rec["equal_to_rang_run"] else 3


# --- gate 3c on the unaveraged image (section 4) -------------------------------------


def c3_flag(ms, r):
    from rang import core_writeback

    ms, r = Path(ms), Path(r)
    st = P.state(ms)["stages"]
    version = (st.get("selfcal") or {}).get("flag_version")
    before = P.flag_hash(ms)
    rows = core_writeback.restore_flags(ms, version) if version else 0
    write(r / "c3-flag.json", {"flag_version": version, "rows": rows, "before": before,
                               "after": P.flag_hash(ms)})  # fmt: skip
    return 0


UNIT_PY = r"""
import json, sys
import numpy as np
from casacore.tables import table, makecoldesc
ms, mode, out = sys.argv[1:4]
t = table(ms, readonly=False, ack=False)
cols = t.colnames()
if mode == "on":
    assert "UG_WEIGHT" not in cols, cols
    n = t.nrows()
    t.renamecol("WEIGHT_SPECTRUM", "UG_WEIGHT_SPECTRUM")
    t.renamecol("WEIGHT", "UG_WEIGHT")
    desc = t.getcoldesc("UG_WEIGHT")
    t.addcols(makecoldesc("WEIGHT", desc),
              {"TYPE": "StandardStMan", "NAME": "UGUnitWeight", "SPEC": {}})
    t.putcol("WEIGHT", np.ones((n, t.getcell("UG_WEIGHT", 0).shape[0]), np.float32))
else:
    assert "UG_WEIGHT" in cols, cols
    t.removecols(["WEIGHT"])
    t.renamecol("UG_WEIGHT", "WEIGHT")
    t.renamecol("UG_WEIGHT_SPECTRUM", "WEIGHT_SPECTRUM")
rec = {"mode": mode, "columns": t.colnames()}
t.close()
json.dump(rec, open(out, "w"), indent=1)
print(json.dumps(rec))
"""


def c3_unit(ms, r, mode):
    ms, r = Path(ms), Path(r)
    (r / "ug_unit.py").write_text(UNIT_PY, encoding="utf-8")
    return P.docker(r, P.FORMATS_IMAGE, P.inplace_mounts(ms, r),
                    f"{P.QC_PY} -I /p/ug_unit.py /c/{ms.name} {mode} /p/c3-unit-{mode}.json",
                    f"c3-unit-{mode}", 1)  # fmt: skip


def c3_entry(r):
    s = json.loads((Path(r) / "c3" / "rang-run" / "image" / "summary.json").read_text())
    (entry,) = s["images"]
    return entry


def _wsclean(ms, r, sub, kind, column, threads, label):
    from rang import core_ms

    ms, r = Path(ms), Path(r)
    if "UG_WEIGHT" not in P.ms_columns(ms) and "E2_WEIGHT" not in P.ms_columns(ms):
        raise SystemExit("no matched (unit weight) state")
    entry = c3_entry(r)
    gem = list(entry["argv"])
    if "-scans" in gem:
        with core_ms.open_table(ms) as t:
            fids = np.asarray(t.getcol("FIELD_ID"))
            scans = np.asarray(t.getcol("SCAN_NUMBER"))
        listed = {int(x) for x in gem[gem.index("-scans") + 1].split(",")}
        have = {int(x) for x in np.unique(scans[fids == int(entry["field_id"])])}
        if not have <= listed:
            raise SystemExit(
                f"-scans {sorted(listed)} selects part of the field {sorted(have)}"
            )
    d = r / sub
    (d / "tmp").mkdir(parents=True, exist_ok=True)
    tag = entry["field"].replace("+", "p").replace("-", "m")
    argv, dropped = P.wsclean_argv(gem, name=f"/p/{sub}/{tag}-{kind}", column=column,
                                   threads=threads, temp=f"/p/{sub}/tmp",
                                   ms_inside=f"/c/{ms.name}", dirty=kind == "dirty")  # fmt: skip
    t0 = time.perf_counter()
    rc = P.docker(r, P.WSCLEAN_IMAGE, P.inplace_mounts(ms, r), " ".join(argv), label,
                  int(threads))  # fmt: skip
    shutil.rmtree(d / "tmp", ignore_errors=True)
    P.write(r / f"{label}-run.json",
            {"exit": rc, "argv": argv, "gemclean_argv": gem, "dropped": dropped,
             "seconds": time.perf_counter() - t0,
             "fits": sorted(p.name for p in d.glob(f"{tag}-{kind}*.fits"))})  # fmt: skip
    return rc


def ws3c(ms, r, kind, threads="8"):
    return _wsclean(ms, r, "ws3c", kind, "CORRECTED_1GC", threads, f"ws3c-{kind}")


def scorer():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "e2_score3c_a", RES / "e2-acceptance-scripts" / "e2_score3c_a.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.RADIUS_DEG = (
        RADIUS_DEG  # read at call time; keys named "0p7deg" mean 1.0 deg here
    )
    return mod


def score3c(ms, r):
    r = Path(r)
    rc = scorer().main(r / "c3", r / "ws3c", r / "g3c.json")
    g = json.loads((r / "g3c.json").read_text())
    g["field_limit_deg"] = RADIUS_DEG
    g["note"] = "keys named 0p7deg hold the 1.0 deg field limit (uhf-gate.md section 5)"
    P.write(r / "g3c.json", g)
    return rc


# --- calibrator rows (section 5) ------------------------------------------------------


def rows_snap(ms, r, arm, data, flag, model, out):
    import e2_rows_b as B

    ms = Path(ms)
    nu = freqs(ms)
    res = {"arm": arm, "ms": str(ms), "column": data, "flag": flag, "model": model,
           "edges": EDGES}  # fmt: skip
    plan = {"parity": (FIELDS["xcal"], None), "secondary": (FIELDS["gcal"], None)}
    if FIELDS["leak"]:
        plan["leak_flux"] = (FIELDS["leak"], "first")
    plan["fcal_second"] = (FIELDS["fcal"], "second")
    for row, (field, which) in plan.items():
        sc = scans_of(ms, field)
        if which == "first":
            sc = sc[:1]
        elif which == "second":
            sc = sc[1:2]
        s, n, tot = B.accumulate(ms, data, flag, field, sc, nu, EDGES)
        res[row] = {"field": field, "scans": sc, "s": s, "n": n, "tot": tot}
        if row == "fcal_second":
            sm, nm, _ = B.accumulate(ms, model, flag, field, sc, nu, EDGES)
            res[row].update(model_s=sm, model_n=nm)
    if not str(out).endswith(".npy"):
        raise SystemExit("OUT must end in .npy")
    np.save(out, res, allow_pickle=True)
    print(json.dumps({k: v["scans"] for k, v in res.items() if isinstance(v, dict)}))
    return 0


def arm_stokes(a):
    import e2_rows_b as B

    i, q, u, v = B.stokes(a["s"], a["n"])
    return {"I": i, "Q": q, "U": u, "V": v, "frac": a["n"] / np.maximum(a["tot"], 1),
            "p": np.hypot(q, u) / i, "chi_deg": np.degrees(0.5 * np.arctan2(u, q))}  # fmt: skip


LIMITS = {"parity": {"dp": 0.001, "dchi_deg": 0.5, "di": None},
          "secondary": {"dp": 0.001, "dchi_deg": 1.0, "di": 0.01},
          "leak_flux": {"dp": None, "dchi_deg": None, "di": 0.01}}  # fmt: skip


def rows_score(ms, r):
    from rang import fluxstd

    r = Path(r)
    ra = np.load(r / "rows-rang.npy", allow_pickle=True).item()
    ca = np.load(r / "rows-casa.npy", allow_pickle=True).item()
    res = {"edges_hz": EDGES, "rang": ra["ms"], "casa": ca["ms"]}
    for row, lim in LIMITS.items():
        if row not in ra:
            continue
        a, c = arm_stokes(ra[row]), arm_stokes(ca[row])
        bins = []
        for b in range(len(EDGES) - 1):
            rec = {"lo_hz": EDGES[b], "hi_hz": EDGES[b + 1],
                   "frac_unflagged": [float(a["frac"][b]), float(c["frac"][b])],
                   **{f"{k}_{arm}": float(x[k][b]) for k in ("I", "p", "chi_deg")
                      for arm, x in (("rang", a), ("casa", c))}}  # fmt: skip
            rec["scored"] = bool(min(rec["frac_unflagged"]) >= 0.1)
            rec["dp"] = float(a["p"][b] - c["p"][b])
            rec["dchi_deg"] = float((a["chi_deg"][b] - c["chi_deg"][b] + 90) % 180 - 90)
            rec["dI_rel"] = float(a["I"][b] / c["I"][b] - 1)
            ok = True
            if lim["dp"] is not None:
                ok = (
                    ok
                    and abs(rec["dp"]) <= lim["dp"]
                    and abs(rec["dchi_deg"]) <= lim["dchi_deg"]
                )
            if lim["di"] is not None:
                ok = ok and abs(rec["dI_rel"]) <= lim["di"]
            rec["met"] = bool(ok) if rec["scored"] else None
            bins.append(rec)
        scored = [x for x in bins if x["scored"]]
        res[row] = {"field": ra[row]["field"], "scans": ra[row]["scans"], "limits": lim,
                    "bins": bins, "bins_scored": len(scored),
                    "max_abs_dp": max((abs(x["dp"]) for x in scored), default=None),
                    "max_abs_dchi_deg": max((abs(x["dchi_deg"]) for x in scored), default=None),
                    "max_abs_dI_rel": max((abs(x["dI_rel"]) for x in scored), default=None),
                    "met": bool(scored) and all(x["met"] for x in scored)}  # fmt: skip
    rep = {}
    # 3C 286 same scan, not a transfer (section 5, reported), beside the model's flat 9.8 %, 33 deg
    rep["xcal_same_scan"] = {arm: {"p": arm_stokes(d["parity"])["p"].tolist(),
                                   "chi_deg": arm_stokes(d["parity"])["chi_deg"].tolist()}
                             for arm, d in (("rang", ra), ("casa", ca))}  # fmt: skip
    rep["xcal_same_scan"]["label"] = (
        "same-scan, not a transfer; model flat p 9.8 %, chi 33 deg"
    )
    # 1934-638 corrected I over its model column, second scan (not a transfer)
    rep["fcal_second_over_model"] = {}
    for arm, d in (("rang", ra), ("casa", ca)):
        x = d["fcal_second"]
        di = ((x["s"][:, 0] + x["s"][:, 3]) / 2).real / np.maximum(x["n"], 1)
        mi = ((x["model_s"][:, 0] + x["model_s"][:, 3]) / 2).real / np.maximum(
            x["model_n"], 1
        )
        rep["fcal_second_over_model"][arm] = {"scans": x["scans"],
                                              "ratio": (di / np.where(mi == 0, np.nan, mi)).tolist(),
                                              "frac": (x["n"] / np.maximum(x["tot"], 1)).tolist()}  # fmt: skip
    if (
        "leak_flux" in ra
    ):  # against the two 0408-65 models: reported, not gated (section 3)
        mid = np.array([(EDGES[b] + EDGES[b + 1]) / 2 for b in range(len(EDGES) - 1)])
        cubic = fluxstd.flux("J0408-6545", mid, "CARACal 2016", extrapolate=True)[
            ..., 0
        ]
        prim = None
        cat = os.environ.get("UG_0407_CAT")
        if cat and Path(cat).is_file():
            (p,) = [c for c in read_catalogue(cat) if c[0] == "PRIM"]
            prim = spectrum(p, mid)
        rep["leak_flux_models"] = {
            "bin_centre_hz": mid.tolist(), "caracal_2016_cubic_jy": cubic.tolist(),
            "doi_0407_prim_jy": None if prim is None else prim.tolist(),
            **{f"I_{arm}": arm_stokes(d["leak_flux"])["I"].tolist() for arm, d in (("rang", ra), ("casa", ca))}}  # fmt: skip
    res["reported"] = rep
    write(r / "rows.json", res)
    return 0


def leakage(ms, r, column, arm):
    """J0408-6545's IQUV MFS images (E2-N's leakage argv, e2n_rows.leakage),
    unit weights; the peak |Q|, |U|, |V| within 0.5 deg over the I peak
    (section 5), and E2-N's 3-beam measure beside it (reported)."""
    from astropy.io import fits

    ms, r = Path(ms), Path(r)
    if not FIELDS["leak"]:
        raise SystemExit("this block has no leakage row")
    out = r / "leakage"
    (out / "tmp").mkdir(parents=True, exist_ok=True)
    fid = field_id(ms, FIELDS["leak"])
    cmd = (f"wsclean -name /o/{arm} -size 2048 2048 -scale 2asec -weight briggs 0.0 "
           "-make-psf -channels-out 8 -join-channels -pol IQUV -join-polarizations "
           f"-data-column {column} -gridder wgridder -wgridder-accuracy 0.0001 -niter 0 "
           f"-no-update-model-required -j 8 -temp-dir /o/tmp -field {fid} /m/{ms.name}")  # fmt: skip
    rc = P.docker(out, P.WSCLEAN_IMAGE, [(ms.parent, "/m"), (out, "/o")], cmd,
                  f"{arm}-wsclean", 8)  # fmt: skip
    shutil.rmtree(out / "tmp", ignore_errors=True)
    rec = {"arm": arm, "column": column, "field": FIELDS["leak"], "field_id": fid,
           "wsclean_exit": rc, "command": cmd}  # fmt: skip
    if rc == 0:
        img = {p: np.asarray(fits.getdata(out / f"{arm}-MFS-{p}-image.fits"), float).squeeze()
               for p in "IQUV"}  # fmt: skip
        h = fits.getheader(out / f"{arm}-MFS-I-image.fits")
        rad = scorer().radius_deg(h, img["I"].shape)
        inner = rad <= LEAK_RADIUS_DEG
        py, px = np.unravel_index(
            int(np.argmax(np.where(inner, img["I"], -np.inf))), img["I"].shape
        )
        peak = float(img["I"][py, px])
        hp = fits.getheader(out / f"{arm}-MFS-I-psf.fits")
        bmaj = max(float(h.get("BMAJ", 0)), float(hp.get("BMAJ", 0))) / abs(h["CDELT2"])
        near = np.hypot(*np.mgrid[: img["I"].shape[0], : img["I"].shape[1]][::-1]
                        - np.array([px, py])[:, None, None]) <= 3 * bmaj  # fmt: skip
        rec.update(
            i_peak_jy=peak, i_peak_pix=[int(px), int(py)], radius_deg=LEAK_RADIUS_DEG
        )
        for p in "QUV":
            rec[f"{p}_over_I"] = float(np.max(np.abs(img[p][inner]))) / peak
            rec[f"{p}_over_I_3beam_reported"] = (
                float(np.max(np.abs(img[p][near]))) / peak
            )
    write(out / f"{arm}.json", rec)
    return rc


def leak_score(ms, r):
    out = Path(r) / "leakage"
    a = json.loads((out / "rang.json").read_text())
    c = json.loads((out / "casa.json").read_text())
    rec = {
        "limit_each": LEAK_MAX,
        "ratio_limit": LEAK_RATIO,
        "radius_deg": LEAK_RADIUS_DEG,
    }
    ok = True
    for p in "QUV":
        x, y = a[f"{p}_over_I"], c[f"{p}_over_I"]
        rec[p] = {"rang": x, "casa": y, "ratio": x / y if y else None}
        ok = ok and x <= LEAK_MAX and y <= LEAK_MAX and (y > 0 and x <= LEAK_RATIO * y)
    rec["met"] = bool(ok)
    write(Path(r) / "row-leakage.json", rec)
    return 0


# --- the CASA arm (section 7) ----------------------------------------------------------


def casa_module():
    import e2n_casa3b as CB

    fcal, xcal, gcal = FIELDS["fcal"], FIELDS["xcal"], FIELDS["gcal"]
    sec = [
        f
        for f in (gcal, FIELDS["target"], FIELDS["leak"])
        if f and f not in (fcal, xcal)
    ]
    sec = list(dict.fromkeys(sec))
    lin, near = "linear", "nearest"
    # the configuration's apply entries (uhf-dev.yaml, uhf-heldout.yaml)
    CB.APPLY = [
        (",".join(sec), ["K", "F", "B", "Kcross", "Xf", "Df"], [lin] * 3 + [near] * 3,
         [fcal, gcal, fcal, "", "", ""]),
        (f"{fcal},{xcal}", ["K", "G", "B", "Gpol", "Kcross", "Xf", "Df"],
         [lin] * 4 + [near] * 3, [""] * 7),
    ]  # fmt: skip
    CB.X286 = X286
    return CB


def casa_calls(ms, r):
    """e2n_casa3b.casa_calls with the first setjy (1934-638 by a standard) left
    out: MODEL_DATA of the fcal is rang's (casa-model). The rest unchanged."""
    CB = casa_module()
    calls = CB.casa_calls(f"/c/{Path(ms).name}", CB.refant_names(r))
    first = calls[0]
    assert first["task"] == "setjy" and first["args"]["field"] == FIELDS["fcal"], first
    return calls[1:]


SPLIT = (
    5  # setjy 3C 286, K, G, B, Gsec on the flag stage's flags; the rest after calibrate
)


def versions(r):
    s = json.loads((rang_run(r) / "state.json").read_text())["stages"]
    return s["calibrate"]["flag_version"], s["apply"]["flag_version"]


def _restore(ms, r, version, label):
    from rang import core_writeback

    rows = core_writeback.restore_flags(Path(ms), version)
    h = P.flag_hash(Path(ms))
    write(
        Path(r) / f"casa-{label}.json",
        {"flag_version": version, "rows": rows, "hash": h},
    )
    return h


def _tasks(ms, r, calls, label):
    r = Path(r)
    P.write(r / f"{label}-spec.json", calls)
    rc = P.docker(r, P.CASA_IMAGE, [*P.inplace_mounts(ms, r), (ROOT / "examples", "/ex")],
                  f"/opt/casa/bin/python -I /ex/oracle_pol.py tasks /p/{label}-spec.json "
                  f"/p/{label}-tasks.json", label, 4)  # fmt: skip
    tasks = json.loads((r / f"{label}-tasks.json").read_text())
    errors = [(t["task"], t["error"]) for t in tasks if t["error"]]
    P.log(r, f"{label} tasks {len(tasks)} errors {errors}")
    return rc or (3 if errors else 0)


def casa_prep_a(ms, r):
    held = [c for c in P.ms_columns(ms) if c.startswith(("RANG_", "E2_", "UG_"))]
    if held or P.run_dir(Path(ms)).exists():
        raise SystemExit(f"restore has not run: {held}")
    if not json.loads((Path(r) / "casa-model.json").read_text())["equal_to_rang_run"]:
        raise SystemExit("casa-model is not rang's model")
    _restore(ms, r, versions(r)[0], "prep-a")
    return 0


def casa_run_a(ms, r):
    r = Path(r)
    shutil.rmtree(r / "casa" / "tables", ignore_errors=True)
    (r / "casa" / "tables").mkdir(parents=True)
    return _tasks(ms, r, casa_calls(ms, r)[:SPLIT], "casa3b-a")


def casa_prep_b(ms, r):
    h = _restore(ms, r, versions(r)[1], "prep-b")
    # e2n_casa3b.corr_prep / applycal and e2_rows_a read this name
    P.write(Path(r) / "casa3b-n-prep.json", {"flag_version": versions(r)[1], "hash": h})
    return 0


def casa_run_b(ms, r):
    r = Path(r)
    calls = casa_calls(ms, r)
    rc = _tasks(ms, r, calls[SPLIT:], "casa3b-b")
    a = json.loads((r / "casa3b-a-tasks.json").read_text())
    b = json.loads((r / "casa3b-b-tasks.json").read_text())
    P.write(r / "casa3b-n-spec.json", calls)
    P.write(r / "casa3b-n-tasks.json", a + b)
    return rc


def casa_corr_prep(ms, r):
    return casa_module().corr_prep(ms, r)


def casa_applycal(ms, r):
    return casa_module().applycal(ms, r)


# --- target and self-calibration rows -------------------------------------------------


def target_wsclean(ms, r, threads="8"):
    return _wsclean(
        ms, r, "oracle-c3", "clean", "CORRECTED_DATA", threads, "oracle-c3-clean"
    )


def _offsource(images, residual, radius_deg):
    import e2_rows_a as A

    return A.offsource(images, residual, radius_deg=radius_deg)


def target_score(ms, r):
    r = Path(r)
    s = scorer()
    rdir, tag, nch = s.rang_images(r / "c3")
    odir = r / "oracle-c3"
    comp = s.compact(rdir, odir, tag, nch)
    ratios = [x["ratio"] for x in comp["sources"] if x["in_0p7deg"]]
    gate = {"n": len(ratios), "field_limit_deg": RADIUS_DEG}
    if ratios:
        gate.update(median=float(np.median(ratios)), robust_scatter=s.mad(ratios))
    gate["met"] = (bool(abs(gate["median"] - 1) <= 0.01 and gate["robust_scatter"] <= 0.015)
                   if len(ratios) >= 3 else None)  # fmt: skip
    a = s._open(rdir / "image-MFS-image.fits")
    b = s._open(odir / f"{tag}-clean-MFS-image.fits")
    s.same_grid(a, b, "target images")
    arms, info = _offsource([(a[0], a[1]), (b[0], b[1])],
                            s._open(odir / f"{tag}-clean-MFS-residual.fits")[0], RADIUS_DEG)  # fmt: skip
    noise = {"rang": arms[0], "oracle": arms[1],
             "rms_ratio": arms[0]["rms_jy"] / arms[1]["rms_jy"],
             "dynamic_range_ratio": arms[0]["dynamic_range"] / arms[1]["dynamic_range"], **info}  # fmt: skip
    noise["met"] = bool(
        noise["rms_ratio"] <= 1.2 and noise["dynamic_range_ratio"] >= 0.8
    )
    out = {"compact": {"gated_within_limit": gate, "tolerance": {"median": 0.01, "scatter": 0.015},
                       "sources": comp["sources"], "radial": comp["radial"],
                       "reported": comp["reported"]},
           "noise_dynamic_range": noise,
           "note": "rang: GeMClean's unaveraged image (*-3c.yaml); oracle: CASA-corrected "
                   "data imaged by WSClean 3.7 with the same argv; keys named 0p7deg hold 1.0 deg"}  # fmt: skip
    write(r / "row-target.json", out)
    return 0


def selfcal_score(ms, r):
    r = Path(r)
    s = scorer()
    base = rang_run(r) / "selfcal"
    (field,) = [p for p in base.iterdir() if p.is_dir()]

    def mfs(d, kind):
        (p,) = sorted(Path(d).glob(f"*MFS-{kind}.fits"))
        return s._open(p)

    before, after = field / "round-1", field / "final"
    a, b = mfs(before, "image"), mfs(after, "image")
    s.same_grid(a, b, "selfcal images")
    arms, info = _offsource(
        [(a[0], a[1]), (b[0], b[1])], mfs(before, "residual")[0], RADIUS_DEG
    )
    ratio = arms[1]["rms_jy"] / arms[0]["rms_jy"]
    write(r / "row-selfcal.json", {"field": field.name, "image_1": arms[0], "final": arms[1],
                                   "ratio_after_before": ratio, "limit": 1.02,
                                   "met": ratio <= 1.02, "field_limit_deg": RADIUS_DEG, **info,
                                   "gains": "qc-selfcal.json (E2-A 9.10's amended form)"})  # fmt: skip
    return 0


def reported(ms, r):
    r = Path(r)
    rr = rang_run(r)
    out = {}
    cal = json.loads((rr / "calibrate" / "summary.json").read_text())
    out["rang_fluxscale"] = {k: v for k, v in cal.items() if "flux" in k.lower()}
    tasks = json.loads((r / "casa3b-n-tasks.json").read_text())
    out["casa_fluxscale"] = [t for t in tasks if t["task"] == "fluxscale"]
    st = json.loads((rr / "state.json").read_text())["stages"]
    out["stage_seconds"] = {k: v.get("seconds") for k, v in st.items()}
    out["flag_fractions"] = {}
    for stage in ("flag", "calibrate", "apply", "image", "selfcal"):
        p = rr / stage / "summary.json"
        if p.is_file():
            sm = json.loads(p.read_text())
            out["flag_fractions"][stage] = {k: v for k, v in sm.items() if "flag" in k.lower()
                                            and not isinstance(v, (list,))}  # fmt: skip
    write(r / "reported.json", out)
    return 0


STEPS = {"model-row": model_row, "casa-model": casa_model, "c3-flag": c3_flag,
         "c3-unit": c3_unit, "ws3c": ws3c, "score3c": score3c, "rows-snap": rows_snap,
         "rows-score": rows_score, "leakage": leakage, "leak-score": leak_score,
         "casa-prep-a": casa_prep_a, "casa-run-a": casa_run_a, "casa-prep-b": casa_prep_b,
         "casa-run-b": casa_run_b, "casa-corr-prep": casa_corr_prep,
         "casa-applycal": casa_applycal, "target-wsclean": target_wsclean,
         "target-score": target_score, "selfcal-score": selfcal_score, "reported": reported}  # fmt: skip

if __name__ == "__main__":
    step, ms, r, *rest = sys.argv[1:]
    Path(r).mkdir(parents=True, exist_ok=True)
    P.log(r, f"ug {BLOCK} {step} {ms} {rest}")
    sys.exit(STEPS[step](ms, r, *rest))
