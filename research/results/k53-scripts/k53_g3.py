"""Issue #53 gates G2 (noisy, class T) and G3 (CASA) on a simulated MS
(research/k-refant-53.md section 3).

    python k53_g3.py make OUT           # rang venv: the MS, the truth, rang's solves
    python k53_g3.py casa OUT           # CASA venv (rang-o-casa_6.7.6.14): CASA's solves
    python k53_g3.py score OUT          # rang venv: score.json

The MS: 12 antennas, 4 scans of 6 integrations of 8 s, 64 channels over
856-1712 MHz, a 10 Jy point (MODEL_DATA), delays per scan and antenna
uniform in +-8 ns (seed 53), complex noise of 0.3 Jy per cell. Case A: scan 2
loses every baseline to m000; case B: scan 3 loses m000-m005. rang solves
`gaincal(gaintype K)` per scan (`solint inf`) with `refant [0, 1]`, flex and
strict. CASA solves at refant m000 (all scans), m001 (scan 2) and m001 (scan
3, for case B's composition `(tau_5 - tau_1) + (tau_1 - tau_0)`).
"""

import json
import sys
from pathlib import Path

import numpy as np

NANT, NINT, NSCAN, NCHAN = 12, 6, 4, 64
SEED, NOISE, FLUX = 53, 0.3, 10.0


def cmd_make(out):
    import importlib.util

    from rang import cal_delay, core_ms_write

    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "w1", root / "examples/w1_writeback.py"
    )
    w1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w1)
    out.mkdir(parents=True, exist_ok=True)
    ms = out / "k53.ms"
    pairs = NANT * (NANT - 1) // 2
    nrow = pairs * NINT * NSCAN
    w1.make_ms(ms, nrow, NCHAN, flag="tiled", nant=NANT)
    freq = 856e6 + 856e6 / NCHAN * (np.arange(NCHAN) + 0.5)
    width = np.full(NCHAN, 856e6 / NCHAN)
    with core_ms_write.open_table(ms / "SPECTRAL_WINDOW", readonly=False) as t:
        t.putcol("CHAN_FREQ", freq[None])
        for c in ("CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"):
            t.putcol(c, width[None])
        t.putcol("TOTAL_BANDWIDTH", np.array([856e6]))
        t.putcol("REF_FREQUENCY", np.array([freq[NCHAN // 2]]))
    base = np.array([5109224.0, 2006790.0, -3239100.0])
    with core_ms_write.open_table(ms / "ANTENNA", readonly=False) as t:
        t.addrows(NANT)
        t.putcol("POSITION", base + 150.0 * np.arange(NANT)[:, None] * [1, 0.5, 0.2])
        t.putcol("NAME", [f"m{a:03d}" for a in range(NANT)])
    with core_ms_write.open_table(ms / "FIELD", readonly=False) as t:
        t.addrows(1)
        t.putcol("NAME", ["CAL"])
        t.putcol("PHASE_DIR", np.array([[[0.0, -1.0]]]))
    _casa_subtables(ms, nrow // (NANT * (NANT - 1) // 2))
    rng = np.random.default_rng(SEED)
    tau = rng.uniform(-8, 8, (NSCAN, NANT, 2))  # ns
    nu0 = freq.mean()
    with core_ms_write.open_table(ms, readonly=False) as t:
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        integ = np.arange(nrow) // pairs
        scan = integ // NINT
        t.putcol("SCAN_NUMBER", (scan + 1).astype(np.int32))
        k = np.exp(2j * np.pi * tau[..., None, :] * 1e-9 * (freq - nu0)[:, None])
        kp, kq = k[scan, a1], np.conj(k[scan, a2])
        v = np.zeros((nrow, NCHAN, 4), complex)
        for c, (h1, h2) in enumerate([(0, 0), (0, 1), (1, 0), (1, 1)]):
            v[..., c] = kp[..., h1] * FLUX * kq[..., h2]
        v += NOISE * (rng.standard_normal(v.shape) + 1j * rng.standard_normal(v.shape))
        t.putcol("DATA", v.astype(np.complex64))
        flag = np.zeros((nrow, NCHAN, 4), bool)
        caseA = (scan == 1) & ((a1 == 0) | (a2 == 0))
        caseB = (scan == 2) & (a1 == 0) & (a2 == 5)
        flag[caseA | caseB] = True
        t.putcol("FLAG", flag)
        t.putcol("FLAG_ROW", caseA | caseB)
        t.putcol("WEIGHT", np.ones((nrow, 4), np.float32))
        t.putcol("SIGMA", np.ones((nrow, 4), np.float32))
    model = np.zeros((nrow, NCHAN, 4), np.complex64)
    model[..., 0] = model[..., 3] = FLUX
    _add_model(ms, model)
    np.savez(out / "truth.npz", tau=tau, freq=freq)
    res = {}
    for mode in ("flex", "strict"):
        _, sol, _ = cal_delay.gaincal(
            ms, field_id=0, solint="inf", combine="", refant=[0, 1], refantmode=mode,
            model_column="MODEL_DATA", weight_column="WEIGHT",
        )  # fmt: skip
        np.savez(out / f"rang-{mode}.npz", delays=sol.delays, flags=sol.flags, err=sol.err,
                 refant_used=sol.refant_used)  # fmt: skip
        res[mode] = {
            "refant_used": sol.refant_used.tolist(),
            "iterations": sol.iterations,
        }
    (out / "rang.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res))


def _casa_subtables(ms, nint):
    """OBSERVATION and FEED rows, which CASA's gaincal needs (w1's MS leaves
    them empty)."""
    from rang import core_ms_write

    t0, t1 = 5.0e9, 5.0e9 + 8.0 * nint
    with core_ms_write.open_table(ms / "OBSERVATION", readonly=False) as t:
        t.addrows(1)
        t.putcol("TIME_RANGE", np.array([[t0, t1]]))
        t.putcol("TELESCOPE_NAME", ["MeerKAT"])
        t.putcol("OBSERVER", ["k53"])
        t.putcol("PROJECT", ["k53"])
    with core_ms_write.open_table(ms / "FEED", readonly=False) as t:
        t.addrows(NANT)
        t.putcol("ANTENNA_ID", np.arange(NANT, dtype=np.int32))
        t.putcol("FEED_ID", np.zeros(NANT, np.int32))
        t.putcol("SPECTRAL_WINDOW_ID", np.full(NANT, -1, np.int32))
        t.putcol("BEAM_ID", np.full(NANT, -1, np.int32))
        t.putcol("NUM_RECEPTORS", np.full(NANT, 2, np.int32))
        t.putcol("TIME", np.full(NANT, (t0 + t1) / 2))
        t.putcol("INTERVAL", np.full(NANT, t1 - t0))
        t.putcol("POLARIZATION_TYPE", np.array([["X", "Y"]] * NANT))
        t.putcol("RECEPTOR_ANGLE", np.zeros((NANT, 2)))
        t.putcol("BEAM_OFFSET", np.zeros((NANT, 2, 2)))
        t.putcol("POSITION", np.zeros((NANT, 3)))
        t.putcol("POL_RESPONSE", np.tile(np.eye(2, dtype=complex), (NANT, 1, 1)))


def _add_model(ms, model):
    from rang import core_writeback as wb

    with wb.WriteBack(ms, stage="k53") as w:
        w.ensure_column("MODEL_DATA")
        w.write("MODEL_DATA", 0, model)


def cmd_casa(out):
    import casatasks
    import casatools

    ms = str(out / "k53.ms")
    runs = {"r0": ("m000", ""), "r1_scan2": ("m001", "2"), "r1_scan3": ("m001", "3")}
    res = {}
    for name, (refant, scan) in runs.items():
        cal = str(out / f"casa-{name}.K")
        casatasks.gaincal(vis=ms, caltable=cal, field="0", scan=scan, gaintype="K",
                          solint="inf", combine="", refant=refant, minsnr=0.0,
                          minblperant=1)  # fmt: skip
        tb = casatools.table()
        tb.open(cal)
        res[name] = {
            "fparam": tb.getcol("FPARAM").tolist(),  # (2 hands, 1, nrow), ns
            "flag": tb.getcol("FLAG").tolist(),
            "antenna1": tb.getcol("ANTENNA1").tolist(),
            "scan": tb.getcol("SCAN_NUMBER").tolist(),
        }
        tb.close()
    (out / "casa.json").write_text(json.dumps(res) + "\n")


def _casa_array(run):
    """(scan index 0..3, antenna, hand) delays and flags from a CASA K table."""
    f = np.asarray(run["fparam"])[:, 0, :]
    g = np.asarray(run["flag"])[:, 0, :]
    tau = np.full((NSCAN, NANT, 2), np.nan)
    for i, (a, s) in enumerate(zip(run["antenna1"], run["scan"])):
        if not g[:, i].any():
            tau[s - 1, a] = f[:, i]
    return tau


def _stats(d):
    d = np.abs(d[np.isfinite(d)])
    return {"n": int(d.size), "median": float(np.median(d)),
            "p95": float(np.percentile(d, 95)), "max": float(d.max())}  # fmt: skip


def cmd_score(out):
    tau = np.load(out / "truth.npz")["tau"]
    rf = np.load(out / "rang-flex.npz")
    casa = json.loads((out / "casa.json").read_text())
    d = rf["delays"][:, 0]  # (scan, ant, hand)
    fl = rf["flags"][:, 0]
    ref = rf["refant_used"]
    score = {"refant_used": ref.tolist()}
    # G2, class T: z = (rang - truth) / err per solved delay (not the reference).
    # C2b's class T: s^2 = err_p^2 + err_r^2 (the reference's error too).
    z, z_changed = [], []
    for s in range(NSCAN):
        want = tau[s] - tau[s, ref[s]]
        er = rf["err"][s, 0, ref[s]]
        for a in range(NANT):
            if a == ref[s] or fl[s, a].any():
                continue
            e = np.sqrt(rf["err"][s, 0, a] ** 2 + er**2)
            v = ((d[s, a] - want[a]) / np.where(e > 0, e, np.nan)).tolist()
            changed = s == 1 or (s == 2 and a == 5)
            (z_changed if changed else z).extend(v)

    def bias(z):
        z = np.asarray(z)
        z = z[np.isfinite(z)]
        bound = 3 * 1.2533 / np.sqrt(len(z))
        return {"N": len(z), "median_z": float(np.median(z)), "bound": bound,
                "std_z": float(np.std(z)), "pass": bool(abs(np.median(z)) <= bound)}  # fmt: skip

    score["G2_classT"] = bias(z + z_changed)
    score["G2_classT_unchanged_intervals"] = bias(z)
    score["G2_classT_changed_only"] = bias(z_changed)
    score["solved_with_data"] = {
        "flex_flagged_with_data": int(sum(fl[s, a].any() for s in range(NSCAN) for a in range(NANT)
                                         if not (s == 1 and a == 0))),
    }  # fmt: skip
    # G3 against CASA at m000, intervals and antennas both solve.
    c0 = _casa_array(casa["r0"])
    both = ~fl & np.isfinite(c0)
    both[ref != 0] = False
    score["G3_r0"] = _stats(np.where(both, d - c0, np.nan))
    score["casa_r0_unsolved"] = int(np.isnan(c0).any(-1).sum())
    # interval 1 (scan 2): CASA at m001.
    c1 = _casa_array(casa["r1_scan2"])
    m = ~fl[1] & np.isfinite(c1[1])
    score["G3_caseA_scan2_vs_casa_m001"] = _stats(np.where(m, d[1] - c1[1], np.nan))
    # case B: antenna 5 in scan 3 = (tau5 - tau1)_casa(m001) + (tau1 - tau0)_casa(m000).
    c3 = _casa_array(casa["r1_scan3"])
    comp = c3[2, 5] + c0[2, 1]
    score["G3_caseB_ant5"] = {"rang": d[2, 5].tolist(), "casa_composed": comp.tolist(),
                              "abs_diff": np.abs(d[2, 5] - comp).tolist(),
                              "bound_median": 0.01 * np.sqrt(2),
                              "bound_p95": 0.03 * np.sqrt(2)}  # fmt: skip
    tol = (0.01, 0.03)
    score["G3_pass"] = bool(
        score["G3_r0"]["median"] <= tol[0] and score["G3_r0"]["p95"] <= tol[1]
        and score["G3_caseA_scan2_vs_casa_m001"]["median"] <= tol[0]
        and score["G3_caseA_scan2_vs_casa_m001"]["p95"] <= tol[1]
        and max(score["G3_caseB_ant5"]["abs_diff"]) <= 0.03 * np.sqrt(2)
    )  # fmt: skip
    (out / "score.json").write_text(json.dumps(score, indent=1) + "\n")
    print(json.dumps(score, indent=1))


if __name__ == "__main__":
    cmd, out = sys.argv[1], Path(sys.argv[2]).resolve()
    {"make": cmd_make, "casa": cmd_casa, "score": cmd_score}[cmd](out)
