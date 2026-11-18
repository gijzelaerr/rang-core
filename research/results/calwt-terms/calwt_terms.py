# SPDX-License-Identifier: MIT
"""The calwt-terms measurement (research/calwt-terms.md sections 5-8) on
glacier: rang's K, G, Gpol, KCROSS and Df solves with and without CASA's
calwt solve weights, against CASA 6.7.6.14 on shared upstream tables and
against simulated truth.

    python calwt_terms.py gen SET             SET: D1 H1-H4 (noisy) | dev held held4
    python calwt_terms.py rang SET ARM        ARM: off k g gpol kcross df all
    python calwt_terms.py casa SET            CASA's chain (WSL docker), model.ms kept
    python calwt_terms.py shared SET          S reads: rang's T on CASA's upstream
    python calwt_terms.py h0 SET              control C2 (harness = pipeline)
    python calwt_terms.py score SET           every read of the set -> score-SET.json
    python calwt_terms.py clean SET           delete the set's MS copies
    python calwt_terms.py set SET [STEP ...]  the steps in order (default all)

Run root D:\\rang\\outputs\\calwt-terms-20261118 (CALWT_OUT). The chain is
section 6's; CASA runs through chi-offset's docker runner (`sim_chi`).
"""

import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "chi-offset"))
import sim_chi

O = Path(os.environ.get("CALWT_OUT", r"D:\rang\outputs\calwt-terms-20261118"))
THREADS = int(os.environ.get("CALWT_THREADS", "4"))
FCAL, XCAL, GCAL = "J1939-6342", "3C286-SIM", "SIM-GCAL"
UV = ">150"
# Section 5: noisy sets (s0: jones, sky, rfi, noise = s0 .. s0 + 3) and
# xf-gap's noiseless sets (seeds, 3C286-SIM integrations per scan).
NOISY = {"D1": 20261881, "H1": 20261891, "H2": 20261901, "H3": 20261911, "H4": 20261921}
XF_HELD = "20261751,20261752,20261753,20261754"
NOISELESS = {"dev": (None, 4), "held": (XF_HELD, 90), "held4": (XF_HELD, 4)}
ARMS = {
    "off": [],
    "k": ["k_calwt"],
    "g": ["g_calwt"],
    "gpol": ["gpol_calwt"],
    "kcross": ["kcross_calwt"],
    "df": ["df_calwt"],
    "all": ["k_calwt", "g_calwt", "gpol_calwt", "kcross_calwt", "df_calwt", "xf_calwt"],
}
# Chain order; the keyed solves and their type; the structural no-ops.
ORDER = ("K", "G", "B", "K2", "G2", "B2", "Kg", "Gg", "Gpol", "Kcross", "Xf", "Df")
KEYED = {"K2": "K", "Kg": "K", "G2": "G", "Gg": "G", "Gpol": "Gpol",
         "Kcross": "KCROSS", "Df": "Df"}  # fmt: skip
NOOPS = ("G", "B", "B2")
KEY_OF = {"K": "k", "G": "g", "Gpol": "gpol", "KCROSS": "kcross", "Df": "df"}

CONFIG = """\
version: 1
fields: {{fcal: [J1939-6342], bpcal: [J1939-6342], gcal: [SIM-GCAL], xcal: [3C286-SIM]}}
data: {{weights: uniform}}
calibrate:
  model: {{source: setjy, standard: Stevens-Reynolds 2016}}
  refant: m000
  uvrange: "{uv}"
  average_time: false
{keys}  primary:
    field: [fcal]
    terms:
      - {{type: K, name: K, solint: inf}}
      - {{type: G, name: G, solint: inf, calmode: ap, preapply: [K], interp: [linear]}}
      - {{type: B, name: B, solint: inf, preapply: [K, G], interp: [linear, linear]}}
      - {{type: K, name: K2, solint: inf, preapply: [G, B], interp: [linear, linear]}}
      - {{type: G, name: G2, solint: inf, calmode: ap, preapply: [K2, B],
         interp: [linear, linear]}}
      - {{type: B, name: B2, solint: inf, preapply: [K2, G2], interp: [linear, linear]}}
  secondary:
    field: [gcal]
    terms:
      - {{type: K, name: Kg, solint: inf, preapply: [B2], interp: [linear]}}
      - {{type: G, name: Gg, solint: inf, calmode: ap, preapply: [Kg, B2],
         interp: [linear, linear]}}
  polcal:
    field: [xcal]
    model: {{source: nrao, name: 3C286}}
    feed_angle_rotation: -90
    terms:
      - {{type: Gpol, name: Gpol, solint: 60s, calmode: p, parang: true,
         preapply: [K2, G2, B2], interp: [linear, linear, linear]}}
      - {{type: KCROSS, name: Kcross, solint: inf, parang: true,
         preapply: [K2, G2, B2, Gpol], interp: [linear, linear, linear, linear]}}
      - {{type: Xf, name: Xf, solint: inf, combine: scan, parang: true,
         preapply: [K2, G2, B2, Gpol, Kcross],
         interp: [linear, linear, linear, linear, nearest]}}
      - {{type: Df, name: Df, field: [fcal], solint: inf, combine: scan, parang: true,
         clip: [-0.6, 0.6], preapply: [K2, G2, B2, Kcross, Xf],
         interp: [linear, linear, linear, nearest, nearest]}}
run:
  stages: [calibrate]
"""


def log(msg):
    O.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(O / "calwt_terms.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def src(s):
    """The generated MS: `a1-poldx.ms` (noisy) or `a1-poldx-twin.ms`."""
    return O / f"truth-{s}" / ("a1-poldx.ms" if s in NOISY else "a1-poldx-twin.ms")


def rang_core():
    exe = Path(sys.executable).parent / (
        "rang-core.exe" if os.name == "nt" else "rang-core"
    )
    return [str(exe)] if exe.exists() else [sys.executable, "-m", "rang.cli"]


# -- data -----------------------------------------------------------------------


def gen(s):
    from rang import core_ms_write, simtruth, simtruth_ms

    d = O / f"truth-{s}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    argv = ["generate", "poldx", str(d), "--workers", str(THREADS)]
    if s in NOISY:
        s0 = NOISY[s]
        argv += ["--seeds", ",".join(str(s0 + k) for k in range(4))]
    else:
        seeds, xints = NOISELESS[s]
        simtruth.SMALL_LENGTH["X"] = xints
        simtruth.FULL_LENGTH["X"] = xints
        argv += ["--noiseless"] + (["--seeds", seeds] if seeds else [])
    t0 = time.perf_counter()
    simtruth_ms.main(argv)
    ms = src(s)
    masks = sorted(d.glob("*.rfi_mask.npz"))
    flagged = 0
    if masks:
        # Section 5: FLAG is the generator's RFI mask on every copy.
        z = np.load(masks[0])
        nchan = int(z["nchan"])
        anyc = np.unpackbits(z["any"], axis=1, count=nchan).astype(bool)
        with core_ms_write.open_table(ms, readonly=False) as t:
            flag = t.getcol("FLAG")
            if anyc.shape[0] != flag.shape[0]:
                raise SystemExit(
                    f"mask rows {anyc.shape[0]} != MS rows {flag.shape[0]}"
                )
            flag |= anyc[:, :, None]
            t.putcol("FLAG", flag)
            flagged = int(flag[..., 0].sum())
    log(f"gen {s} argv={argv[1:]} masks={len(masks)} flagged_cells={flagged} "
        f"{time.perf_counter() - t0:.1f}s")  # fmt: skip


# -- rang ----------------------------------------------------------------------


def config_text(arm):
    keys = "".join(f"  {k}: true\n" for k in ARMS[arm])
    return CONFIG.format(uv=UV, keys=keys)


def rang(s, arm):
    d = O / f"rang-{s}-{arm}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    ms = d / "sim.ms"
    shutil.copytree(src(s), ms)
    (d / "config.yaml").write_text(config_text(arm), encoding="utf-8")
    t0 = time.perf_counter()
    with open(d / "rang.log", "w", encoding="utf-8") as fh:
        rc = subprocess.run([*rang_core(), "run", str(d / "config.yaml"), str(ms)],
                            stdout=fh, stderr=subprocess.STDOUT, check=False).returncode  # fmt: skip
    log(f"rang {s} {arm} rc={rc} {time.perf_counter() - t0:.1f}s")
    return rc


def rang_tables(d):
    return Path(d) / "sim.ms.rang-run" / "calibrate"


# -- CASA ----------------------------------------------------------------------


def casa_calls(ms, t, refant="m000"):
    common = {"vis": ms, "refant": refant, "minsnr": 3.0, "minblperant": 4}
    mode = {"refantmode": "flex"}
    x286 = {"fluxdensity": [14.7172, 0.0, 0.0, 0.0], "spix": [-0.4507, -0.1798, 0.0357],
            "reffreq": "1.47GHz", "polindex": [0.098], "polangle": [0.575959],
            "rotmeas": 0.0}  # fmt: skip
    LIN, NEAR = "linear", "nearest"
    T = lambda n: f"{t}/{n}"
    cc = [T("K2"), T("G2"), T("B2")]

    def k(name, field, tables, smodel=None):
        a = {**common, **mode, "caltable": T(name), "field": field, "gaintype": "K",
             "solint": "inf", "combine": "", "parang": False}  # fmt: skip
        if tables:
            a.update(gaintable=[T(x) for x in tables], interp=[LIN] * len(tables))
        if smodel:
            a["smodel"] = smodel
        return {"task": "gaincal", "args": a}

    def g(name, field, tables, smodel=None):
        a = {**common, **mode, "caltable": T(name), "field": field, "gaintype": "G",
             "calmode": "ap", "solint": "inf", "combine": "", "parang": False,
             "uvrange": UV, "gaintable": [T(x) for x in tables],
             "interp": [LIN] * len(tables)}  # fmt: skip
        if smodel:
            a["smodel"] = smodel
        return {"task": "gaincal", "args": a}

    def b(name, tables):
        return {"task": "bandpass", "args": {
            **common, "caltable": T(name), "field": FCAL, "bandtype": "B", "solint": "inf",
            "combine": "", "solnorm": False, "parang": False, "uvrange": UV,
            "gaintable": [T(x) for x in tables], "interp": [LIN] * len(tables)}}  # fmt: skip

    unit = [1.0, 0.0, 0.0, 0.0]
    return [
        {"task": "setjy", "args": {"vis": ms, "field": FCAL, "standard": "Stevens-Reynolds 2016",
         "scalebychan": True, "usescratch": True}},
        {"task": "setjy", "args": {"vis": ms, "field": XCAL, "standard": "manual", **x286,
         "scalebychan": True, "usescratch": True}},
        # The MS as the solves see it (after setjy): the shared-upstream reads.
        {"task": "copytree", "args": {"src": ms, "dst": ms.replace("sim.ms", "model.ms")}},
        k("K", FCAL, []),
        g("G", FCAL, ["K"]),
        b("B", ["K", "G"]),
        k("K2", FCAL, ["G", "B"]),
        g("G2", FCAL, ["K2", "B"]),
        b("B2", ["K2", "G2"]),
        k("Kg", GCAL, ["B2"], unit),
        g("Gg", GCAL, ["Kg", "B2"], unit),
        {"task": "gaincal", "args": {**common, **mode, "caltable": T("Gpol"), "field": XCAL,
         "gaintype": "G", "calmode": "p", "solint": "60s", "combine": "", "parang": True,
         "uvrange": UV, "gaintable": cc, "interp": [LIN] * 3}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": T("Kcross"), "field": XCAL,
         "gaintype": "KCROSS", "solint": "inf", "combine": "", "parang": True,
         "uvrange": UV, "gaintable": cc + [T("Gpol")], "interp": [LIN] * 4}},
        {"task": "polcal", "args": {**common, "caltable": T("Xf"), "field": XCAL,
         "poltype": "Xf", "solint": "inf", "combine": "scan", "uvrange": UV,
         "gaintable": cc + [T("Gpol"), T("Kcross")], "interp": [LIN] * 4 + [NEAR]}},
        {"task": "polcal", "args": {**common, "caltable": T("Df.raw"), "field": FCAL,
         "poltype": "Df", "solint": "inf", "combine": "scan", "uvrange": UV,
         "gaintable": cc + [T("Kcross"), T("Xf")], "interp": [LIN] * 3 + [NEAR] * 2}},
        {"task": "copytree", "args": {"src": T("Df.raw"), "dst": T("Df")}},
        {"task": "flagdata", "args": {"vis": T("Df"), "mode": "clip",
         "clipminmax": [-0.6, 0.6], "datacolumn": "CPARAM", "flagbackup": False}},
    ]  # fmt: skip


def casa(s):
    d = O / f"casa-{s}"
    if d.exists():
        shutil.rmtree(d)
    (d / "tables").mkdir(parents=True)
    shutil.copytree(src(s), d / "sim.ms")
    (d / "spec.json").write_text(
        json.dumps(casa_calls("/r/sim.ms", "/r/tables"), indent=1)
    )
    t0 = time.perf_counter()
    rc = sim_chi.casa_docker(d, -math.pi / 2)
    errs = []
    res = d / "tasks.json"
    if res.exists():
        errs = [r["error"] for r in json.loads(res.read_text()) if r.get("error")]
    log(f"casa {s} rc={rc} errors={len(errs)} {time.perf_counter() - t0:.1f}s")
    if rc == 0 and not errs:
        log(f"casa {s} C3 Gpol rows {gpol_rows(d / 'tables' / 'Gpol')}")
    return 1 if errs else rc


def gpol_rows(path):
    from rang.formats import caltable

    return len(caltable.read(path).column("TIME"))


# -- the harness: rang's solvers as the pipeline calls them ----------------------


def pipeline_terms(cfg, ms):
    from rang import cal_refant, core_chunks, core_config, core_pipeline

    raw = core_config.load(cfg)
    config = core_config.validate(raw, ["calibrate"], source=Path(cfg))
    config, _ = cal_refant.resolve_config(config, ms)
    info = core_pipeline.inspect_ms(ms)
    terms = core_pipeline.chain_terms(config, info, Path(cfg))
    plan = core_chunks.budget(config, info)
    weight = core_pipeline.chain_weight_column(config, info)
    return {t["name"]: t for t in terms}, plan, weight


def solve_term(ms, cfg, given_dir, name, calwt):
    """rang's `name` solved on `ms` as `cal_chain.run` solves it, with every
    earlier term of the chain read from `given_dir`; `calwt` adds the key
    of its type (`solve_calwt`; none for B)."""
    from rang import cal_chain
    from rang.formats import caltable

    terms, plan, weight = pipeline_terms(cfg, ms)
    term = terms[name]
    common = {
        "model_column": "MODEL_DATA",
        "weight_column": weight,
        "budget": plan.chain(),
    }
    if calwt:
        # Every key on: only `name` is solved, so this is its type's key
        # (a no-op control's type has none).
        common["solve_calwt"] = cal_chain.CALWT_TYPES
    tables = {
        n: {"table": caltable.read(Path(given_dir) / n), "type": terms[n]["type"]}
        for n in ORDER[: ORDER.index(name)]
    }
    (f,) = term["fields"]
    if term["type"] in ("K", "G", "B"):
        table, _, _ = cal_chain._solve_one(ms, term, f, tables, dict(common))
    else:
        table, _ = cal_chain._solve_pol(ms, term, f, tables, dict(common))
        if term["type"] == "Df" and term.get("clip") is not None:
            from rang import cal_pol

            table, _ = cal_pol.clip_df(table, term["clip"])  # as cal_chain.run
    return table


def shared(s):
    """Section 7 S: each keyed solve and no-op control on CASA's model.ms
    with CASA's earlier tables, off and on (keyed) or off (controls)."""
    from rang.formats import caltable

    ms = O / f"casa-{s}" / "model.ms"
    ct = O / f"casa-{s}" / "tables"
    cfg = O / f"rang-{s}-off" / "config.yaml"
    out = O / f"shared-{s}"
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    for name in ORDER:
        if name not in KEYED and name not in NOOPS:
            continue
        for on in (False, True):
            table = solve_term(ms, cfg, ct, name, on)
            caltable.write(table, out / f"{name}-{'on' if on else 'off'}")
    log(f"shared {s} {time.perf_counter() - t0:.1f}s")


def h0(s):
    """Control C2: on the off arm's MS (rang's MODEL_DATA), each keyed term
    with rang's own earlier tables equals the pipeline's table."""
    from rang.formats import caltable

    d = O / f"rang-{s}-off"
    out = O / f"h0-{s}"
    out.mkdir(parents=True, exist_ok=True)
    for name in KEYED:
        caltable.write(solve_term(d / "sim.ms", d / "config.yaml", rang_tables(d), name,
                                  False), out / name)  # fmt: skip
    log(f"h0 {s} done")


# -- reads ---------------------------------------------------------------------


def _tab(path):
    from rang.formats import caltable

    return caltable.read(path)


def _paired(a, b):
    """Rows of tables a and b matched per antenna by nearest TIME (within
    half the smallest spacing or 1 s); returns index arrays."""
    ia, ib = [], []
    ta, tb = a.column("TIME"), b.column("TIME")
    for ant in np.unique(a.column("ANTENNA1")):
        ra = np.flatnonzero(a.column("ANTENNA1") == ant)
        rb = np.flatnonzero(b.column("ANTENNA1") == ant)
        for r in ra:
            if not len(rb):
                continue
            j = rb[np.argmin(np.abs(tb[rb] - ta[r]))]
            if abs(tb[j] - ta[r]) <= 30.0:
                ia.append(r)
                ib.append(j)
    return np.asarray(ia, int), np.asarray(ib, int)


def table_diff(name, a, b, refant=0):
    """Section 7 S measure of table a (rang) against b (CASA)."""
    ia, ib = _paired(a, b)
    pa, pb = a.params[ia], b.params[ib]
    ok = ~(a.flags[ia] | b.flags[ib])
    ants = a.column("ANTENNA1")[ia]
    if name in ("K2", "Kg", "K"):
        keep = ok & (ants != refant)[:, None, None]
        v = np.abs(pa.astype(float) - pb.astype(float))[keep]
    elif name == "Kcross":
        v = np.abs(pa[..., 0].astype(float) - pb[..., 0].astype(float))[ok[..., 0]]
    elif name == "Gpol":
        keep = ok & (ants != refant)[:, None, None]
        r = pa.astype(np.complex128) / pb.astype(np.complex128)
        v = np.degrees(np.abs(np.angle(r)))[keep]
    elif name == "Df":
        return leak_diff(a, b)
    else:
        keep = ok & (ants != refant)[:, None, None] if name in ("G2", "Gg", "G") else ok
        r = pa.astype(np.complex128) / pb.astype(np.complex128)
        v = np.abs(r - 1)[keep]
    return {"median": float(np.median(v)) if len(v) else None, "n": len(v),
            "rows_a": len(a.column("TIME")), "rows_b": len(b.column("TIME")),
            "paired": len(ia)}  # fmt: skip


def _leak(table, nant):
    """(nant, nchan, 2) leakages and flags of a one-interval Df table."""
    d = np.zeros((nant, table.params.shape[1], 2), np.complex128)
    f = np.ones(d.shape, bool)
    for r, a in enumerate(table.column("ANTENNA1")):
        d[a] = table.params[r]
        f[a] = table.flags[r]
    return d, f


def gauge_free(d, f):
    """q_pq = d_x,p + conj(d_y,q), p != q, and its flags (nant, nant, nchan)."""
    q = d[:, None, :, 0] + np.conj(d[None, :, :, 1])
    fq = f[:, None, :, 0] | f[None, :, :, 1]
    n = d.shape[0]
    off = ~np.eye(n, dtype=bool)
    return q[off], fq[off]


def leak_diff(a, b):
    nant = int(max(a.column("ANTENNA1").max(), b.column("ANTENNA1").max())) + 1
    qa, fa = gauge_free(*_leak(a, nant))
    qb, fb = gauge_free(*_leak(b, nant))
    ok = ~(fa | fb)
    v = np.abs(qa - qb)[ok]
    return {"median": float(np.median(v)) if len(v) else None, "n": len(v)}


def bit_equal(pa, pb):
    a, b = _tab(pa), _tab(pb)
    return bool(np.array_equal(a.params, b.params) and np.array_equal(a.flags, b.flags)
                and np.array_equal(a.column("TIME"), b.column("TIME")))  # fmt: skip


# -- truth -----------------------------------------------------------------------


def _ms_layout(ms):
    from rang import core_ms

    with core_ms.open_table(ms) as t:
        time_ = t.getcol("TIME")
        field = t.getcol("FIELD_ID")
        scan = t.getcol("SCAN_NUMBER")
    with core_ms.open_table(Path(ms) / "FIELD") as t:
        names = [str(n) for n in t.getcol("NAME")]
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ")[0], float)
    with core_ms.open_table(Path(ms) / "ANTENNA") as t:
        nant = len(t.getcol("NAME"))
    return time_, field, scan, names, freq, nant


def _scan_times(time_, field, scan, fid):
    """The middle integration time of each scan of field fid."""
    out = []
    for s in np.unique(scan[field == fid]):
        ts = np.unique(time_[(scan == s) & (field == fid)])
        out.append(float(ts[len(ts) // 2]))
    return np.asarray(out)


def composite(tables, times, freq, nant):
    """P = J_p J_q^* (XX, YY) of `tables` for every baseline p < q at
    `times`, by the apply kernel on unit cells; returns (P, flag, t, a1, a2)
    with P (row, chan, 2)."""
    from rang import cal_apply

    a1, a2 = np.triu_indices(nant, 1)
    tt = np.repeat(times, len(a1))
    p1, p2 = np.tile(a1, len(times)), np.tile(a2, len(times))
    ones = np.ones((len(tt), len(freq), 4), np.complex64)
    out, fl = cal_apply.apply(
        ones, False, tt, p1, p2, freq, tables, interp=["linear"] * len(tables),
        direction="corrupt", nant=nant, table_fields=[cal_apply.POOLED] * len(tables),
    )  # fmt: skip
    return out[..., [0, 3]].astype(np.complex128), fl[..., [0, 3]], tt, p1, p2


def truth_composite(z, tt, p1, p2):
    """P_truth (row, chan, 2) from truth.npz's raw K, B and G at the
    integration of each time."""
    times = z["time"]
    idx = np.searchsorted(times, tt)
    if not np.allclose(times[idx], tt):
        raise ValueError("composite times are not integration times")
    j = z["raw_k"] * z["raw_bandpass"]  # (ant, chan, 2)
    g = z["raw_gain"]  # (time, ant, 2)
    jp = j[p1] * g[idx, p1][:, None, :]
    jq = j[p2] * g[idx, p2][:, None, :]
    return jp * np.conj(jq)


def composite_error(pr, fl, pt, tt):
    """Section 7: r = P_rang / P_truth divided per (time, channel) by its
    complex median over baselines and hands; median |r/r~ - 1|."""
    r = pr / pt
    r = np.where(fl, np.nan, r)
    errs = []
    for t in np.unique(tt):
        rows = tt == t
        x = r[rows]  # (bl, chan, 2)
        flat = x.transpose(1, 0, 2).reshape(x.shape[1], -1)  # (chan, bl*2)
        med = np.nanmedian(flat.real, axis=1) + 1j * np.nanmedian(flat.imag, axis=1)
        e = np.abs(flat / med[:, None] - 1)
        errs.append(e[np.isfinite(e)])
    e = np.concatenate(errs)
    return {"median": float(np.median(e)), "n": len(e)}


COMPOSITES = {
    "C_F": (FCAL, ("K2", "G2", "B2")),
    "C_G": (GCAL, ("Kg", "Gg", "B2")),
    "C_X": (XCAL, ("K2", "G2", "B2", "Gpol")),
}


def truth_reads(tdir, s):
    """Section 7 T on one arm's tables (dir of tables)."""
    from rang import cal_apply

    z = np.load(O / f"truth-{s}" / "truth.npz")
    time_, field, scan, names, freq, nant = _ms_layout(src(s))
    out = {}
    for key, (fname, tabs) in COMPOSITES.items():
        times = _scan_times(time_, field, scan, names.index(fname))
        tables = [_tab(Path(tdir) / n) for n in tabs]
        pr, fl, tt, p1, p2 = composite(tables, times, freq, nant)
        out[key] = composite_error(pr, fl, truth_composite(z, tt, p1, p2), tt)
    # C_XH: KCROSS x Xf against the truth in CASA's gauge (refant 0).
    times = _scan_times(time_, field, scan, names.index(XCAL))[:1]
    ones = np.ones((1, len(freq), 4), np.complex64)
    kx = [_tab(Path(tdir) / n) for n in ("Kcross", "Xf")]
    c, fl = cal_apply.apply(
        ones, False, times, [0], [0], freq, kx, interp=["nearest", "nearest"],
        direction="corrupt", nant=nant, table_fields=[cal_apply.POOLED] * 2,
    )  # fmt: skip
    ct = z["gauge0_kcross"] * z["gauge0_xf"]
    ph = np.angle(c[0, :, 1].astype(np.complex128) / ct)
    ok = ~fl[0, :, 1]
    ph = np.angle(np.exp(1j * (ph - np.angle(np.mean(np.exp(1j * ph[ok]))))))
    out["C_XH"] = {
        "median": float(np.degrees(np.median(np.abs(ph[ok])))),
        "n": int(ok.sum()),
    }
    # Amendment 10 (reported): after a constant and a slope in frequency.
    raw = np.unwrap(np.angle(c[0, :, 1].astype(np.complex128) / ct))
    x = (freq - freq.mean()) / 1e9
    fit = np.vstack([np.ones(int(ok.sum())), x[ok]]).T
    coef, *_ = np.linalg.lstsq(fit, raw[ok], rcond=None)
    out["C_XH_fit"] = {
        "median": float(np.degrees(np.median(np.abs(raw[ok] - fit @ coef)))),
        "slope_ns": float(coef[1] / (2 * np.pi)),
    }
    # C_D: gauge-free leakage against the truth in CASA's gauge.
    d, f = _leak(_tab(Path(tdir) / "Df"), nant)
    qr, fr = gauge_free(d, f)
    qt, _ = gauge_free(z["gauge0_leakage"], np.zeros(z["gauge0_leakage"].shape, bool))
    v = np.abs(qr - qt)[~fr]
    out["C_D"] = {"median": float(np.median(v)), "n": len(v)}
    return out


def score(s):
    res = {"set": s, "noisy": s in NOISY}
    ct = O / f"casa-{s}" / "tables"
    # C1: no-op tables, every arm against off.
    off = rang_tables(O / f"rang-{s}-off")
    arms = [a for a in ARMS if (O / f"rang-{s}-{a}").exists()]
    res["C1"] = {a: {n: bit_equal(off / n, rang_tables(O / f"rang-{s}-{a}") / n)
                     for n in NOOPS} for a in arms if a != "off"}  # fmt: skip
    # C2: harness = pipeline.
    if (O / f"h0-{s}").exists():
        res["C2"] = {n: table_diff(n, _tab(O / f"h0-{s}" / n), _tab(off / n))
                     for n in KEYED}  # fmt: skip
        res["C2_bit_equal"] = {n: bit_equal(O / f"h0-{s}" / n, off / n) for n in KEYED}
    if ct.exists():
        res["C3_gpol_rows"] = {
            "casa": gpol_rows(ct / "Gpol"),
            "rang": gpol_rows(off / "Gpol"),
        }
    # S: shared upstream, on and off against CASA.
    sh = O / f"shared-{s}"
    if sh.exists():
        res["S"] = {}
        for n in list(KEYED) + list(NOOPS):
            res["S"][n] = {
                side: table_diff(n, _tab(sh / f"{n}-{side}"), _tab(ct / n))
                for side in ("off", "on")
            }
            res["S"][n]["on_equals_off"] = bit_equal(sh / f"{n}-off", sh / f"{n}-on")
    # Full chains against CASA, per table (reported).
    res["chain_vs_casa"] = {
        a: {n: table_diff(n, _tab(rang_tables(O / f"rang-{s}-{a}") / n), _tab(ct / n))
            for n in ORDER if n != "Xf"}
        for a in arms
    } if ct.exists() else {}  # fmt: skip
    if s in NOISY:
        res["T"] = {a: truth_reads(rang_tables(O / f"rang-{s}-{a}"), s) for a in arms}
        if ct.exists():
            res["T"]["casa"] = truth_reads(ct, s)
    (O / f"score-{s}.json").write_text(json.dumps(res, indent=1) + "\n")
    log(f"score {s} written")
    return res


def clean(s):
    for d in O.glob(f"*-{s}*"):
        for ms in list(d.glob("*.ms")):
            shutil.rmtree(ms, ignore_errors=True)
    log(f"clean {s}")


def run_set(s, *steps):
    """Every step of one set in order (default: gen, the rang arms, casa,
    shared, h0, score); stops at the first failure."""
    steps = steps or ("gen", "rang", "casa", "shared", "h0", "score")
    for step in steps:
        t0 = time.perf_counter()
        if step == "rang":
            arms = ARMS if s in NOISY else ("off",)
            rc = max(int(rang(s, a) or 0) for a in arms)
        else:
            rc = {"gen": gen, "casa": casa, "shared": shared, "h0": h0, "score": score,
                  "clean": clean}[step](s)  # fmt: skip
            rc = rc if isinstance(rc, int) else 0
        log(f"STEP {s} {step} rc={rc} {time.perf_counter() - t0:.1f}s")
        if rc:
            return rc
    return 0


def main(argv):
    cmd, args = argv[0], argv[1:]
    fn = {"gen": gen, "rang": rang, "casa": casa, "shared": shared, "h0": h0,
          "score": score, "clean": clean, "set": run_set}[cmd]  # fmt: skip
    rc = fn(*args)
    return int(rc or 0) if isinstance(rc, int) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
