"""E1b's CASA-chain arm scored with e1b_score.py's measures (a thin wrapper;
e1b_score.py is not changed). The arm directory from `e1b_casa.py` holds
`ms/<name>.ms` (CASA's CORRECTED_DATA, flag versions `e1b_casa_input` and
`e1b_casa_before_apply`) and `casa/` (CASA's tables). The wrapper reads the
tables from `casa/`, maps the scorer's flag versions (`rang_calibrate_*`:
the input FLAG; `rang_apply_*`: FLAG before applycal, after the extension;
no `rang_selfcal_*`) and takes F's flux from CASA's `fluxscale` return.

Scored where they apply: class T, noisy (m32) or noise-free (twin): K
centred, the target 1GC composite, the cross-hand phase arg(Kc Xf), KCROSS,
Xf, Df; the calibrators' composites (reported). m32 also: polarisation and
leakage in the visibility domain on CORRECTED_DATA (CASA's 1GC; compare
with rang's CORRECTED_1GC, E1 7.2), gated on E1's control set
(components 0, 17, 30, 40, from E1 -03's result.json: the arm has no
control column), and SIM-GCAL's leakage. Not scored: flags, image,
residual, self-calibration (the arm does none). With `--rang-run`, the
tables are also compared with rang's of that run directly (reported).

    python e1b_casa_score.py ARM --refant LIST [--rang-run RUN]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import e1b_casa
import e1b_score as S
from e1b_score import FCAL, GCAL, TARGET, XCAL
from rang import core_ms
from rang.formats import caltable, flagversions

E1_RESULT = Path(r"D:\rang\outputs\e1-20261109-03\result.json")
MAP = {"rang_calibrate_": e1b_casa.INPUT_VERSION, "rang_apply_": e1b_casa.APPLY_VERSION}


class CasaCtx(S.Ctx):
    def __init__(self, run, version, refant):
        super().__init__(run, version, refant)
        self.casa = Path(run) / "casa"
        self.refant_names = list(refant)

    def version_name(self, prefix):
        name = MAP.get(prefix)
        return name if name in self.versions else None

    def table(self, name):
        return caltable.read(self.casa / name)


def fluxes(ctx):
    tasks = json.loads((ctx.run / "casa-tasks.json").read_text())
    rec = next(r for r in tasks if r["task"] == "fluxscale")["return"]
    out = {}
    for v in rec.values():
        if isinstance(v, dict) and v.get("fieldName") == GCAL:
            out["fluxscale"] = {GCAL: {"fitted_flux_jy": float(v["fitFluxd"]),
                                       "fit_ref_freq_hz": float(v["fitRefFreq"]),
                                       "per_window_flux_jy": [float(str(v["0"]["fluxd"]).strip("[]").split()[0])]}}  # fmt: skip
    out["truth_gcal_jy_at_1284mhz"] = float(
        np.interp(1.284e9, ctx.freq, ctx.cal[2, :, 0])
    )
    return out


def pol(ctx, twin):
    """Visibility-domain polarisation and leakage (E1 4.5) on CORRECTED_DATA."""
    if twin:
        # The calibrator points only (reported): the target-component fit is
        # not valid on the twin (rang's own twin gives dp -52 to +8 points on
        # it, so do CASA's; checked 2026-11-10), and E1 has no twin pol gate.
        out = S.score_pol(ctx, {})
        out["note"] = "twin: calibrator points only; target fit not valid on the twin"
        return out
    points = S.leak_points(ctx)
    gated = json.loads(E1_RESULT.read_text())["polarisation"]["gated_polarised"]
    recs, _, _ = S.target_pass(ctx, ["CORRECTED_DATA"], points)
    out = S.score_pol(ctx, recs)
    out["gated_polarised"] = gated
    out["gated_from"] = str(E1_RESULT)
    o = out["columns"]["CORRECTED_DATA"]
    pp = [recs["CORRECTED_DATA"][k] for k in gated]
    o["polarised_pass"] = bool(all(abs(r["dp"]) <= 0.002 and abs(r["dchi_deg"]) <= 1.0
                                   for r in pp))  # fmt: skip
    out["pass"] = bool(o["polarised_pass"] and o["leak_targets_pass"] is not False
                       and out["gcal_leak"]["pass"])  # fmt: skip
    return out


def vs_rang(ctx, rang_run):
    """CASA's tables against rang's of the same data (reported, not gated)."""
    ms = S.e1_run.ms_of(rang_run)
    rdir = Path(str(ms) + ".rang-run") / "calibrate"
    out = {"rang_run": str(rang_run)}
    rk, ck = caltable.read(rdir / "K"), ctx.table("K")
    d = []
    for t in (rk, ck):
        key = {(int(s), int(a)): i for i, (s, a) in
               enumerate(zip(t.column("SCAN_NUMBER"), t.column("ANTENNA1")))}  # fmt: skip
        d.append(key)
    common = sorted(set(d[0]) & set(d[1]))
    a = np.array([rk.params[d[0][k], 0, :].real for k in common], float)
    b = np.array([ck.params[d[1][k], 0, :].real for k in common], float)
    ok = ~np.array([rk.flags[d[0][k], 0, :] | ck.flags[d[1][k], 0, :] for k in common])
    diff = a - b
    scans = np.array([k[0] for k in common])
    cen = diff.copy()
    for s in np.unique(scans):
        for h in range(2):
            m = (scans == s) & ok[:, h]
            cen[scans == s, h] -= diff[m, h].mean() if m.any() else 0.0
    out["K_ns"] = {"raw": S.stats(np.abs(diff[ok])), "centred": S.stats(np.abs(cen[ok])),
                   "flagged_rang_only": int((np.array([rk.flags[d[0][k], 0, :] for k in common])
                                             & ~np.array([ck.flags[d[1][k], 0, :]
                                                          for k in common])).sum()),
                   "flagged_casa_only": int((~np.array([rk.flags[d[0][k], 0, :] for k in common])
                                             & np.array([ck.flags[d[1][k], 0, :]
                                                         for k in common])).sum())}  # fmt: skip
    for name in ("Kcross",):
        r, c = caltable.read(rdir / name), ctx.table(name)
        out["Kcross_ns_per_scan"] = {
            "rang": [float(np.median(r.params[r.column("TIME") == t, 0, 0].real))
                     for t in np.unique(r.column("TIME"))],
            "casa": [float(np.median(c.params[c.column("TIME") == t, 0, 0].real))
                     for t in np.unique(c.column("TIME"))]}  # fmt: skip
    r, c = caltable.read(rdir / "Xf"), ctx.table("Xf")

    def first(t):
        v, f = t.params[:, :, 0].astype(complex), t.flags[:, :, 0]
        return np.array([v[~f[:, j], j][0] if (~f[:, j]).any() else np.nan
                         for j in range(v.shape[1])])  # fmt: skip

    xr, xc = first(r), first(c)
    out["Xf_rad"] = S.stats(np.abs(np.angle(xr / xc)))
    r, c = caltable.read(rdir / "Df"), ctx.table("Df")
    ok = ~r.flags & ~c.flags
    out["Df_abs"] = S.stats(np.abs(r.params - c.params)[ok])
    out["Df_flags"] = {"rang": int(r.flags.sum()), "casa": int(c.flags.sum())}
    summ = json.loads((rdir / "summary.json").read_text(encoding="utf-8"))
    fs = [s.get("fluxscale") for s in summ["steps"] if s.get("type") == "F"]
    out["F_flux_rang"] = fs[0] if fs else None
    # Rang's CORRECTED_DATA on the calibrator points (1GC on these fields).
    rctx = S.Ctx(rang_run, ctx.version, ctx.refant_names)
    pts = {}
    for name in (GCAL, XCAL, FCAL):
        i, q, u, v, n = S.point_field(rctx, name, "CORRECTED_DATA")
        good = n > 0
        den = np.where(i != 0, i, 1)
        pts[name] = {"quv_over_i": S.stats((np.sqrt(q**2 + u**2 + v**2) / den)[good]),
                     "p": S.stats((np.hypot(q, u) / den)[good]),
                     "abs_chi_minus_33": S.stats(np.abs(np.degrees(np.arctan2(u, q)) / 2
                                                        - 33.0)[good])}  # fmt: skip
    out["rang_points"] = pts
    return out


def export(ctx, path, twin):
    """Tables, per-channel point means and packed cell flags: what a scorer
    reads once the MS's large columns are gone."""
    z = {}
    for n in ("K", "G", "B", "Gsec", "F", "Gpol", "Kcross", "Xf", "Df"):
        t = ctx.table(n)
        z[f"{n}_params"] = t.params
        z[f"{n}_flags"] = t.flags
        for col in ("TIME", "ANTENNA1", "FIELD_ID", "SCAN_NUMBER"):
            z[f"{n}_{col}"] = t.column(col)
    for name in (FCAL, XCAL, GCAL, TARGET):
        i, q, u, v, n = S.point_field(ctx, name, "CORRECTED_DATA")
        z[f"point_{name}"] = np.stack([i, q, u, v, n.astype(float)])
    for tag, ver in (
        ("input", e1b_casa.INPUT_VERSION),
        ("before_apply", e1b_casa.APPLY_VERSION),
    ):
        z[f"flag_{tag}"] = np.packbits(
            flagversions.load(ctx.ms, ver)[0].any(-1), axis=1
        )
    with core_ms.open_table(ctx.ms) as t:
        z["flag_final"] = np.packbits(t.getcol("FLAG").any(-1), axis=1)
        for col in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID", "SCAN_NUMBER"):
            z[col] = t.getcol(col)
    z["freq"] = ctx.freq
    np.savez_compressed(path, **z)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("arm")
    p.add_argument("--refant", required=True, help="the arm's refant list, names")
    p.add_argument("--rang-run", default=None)
    p.add_argument("--only", default="")
    a = p.parse_args(argv)
    arm = Path(a.arm)
    ms = e1b_casa.ms_in(arm)
    twin = "twin" in ms.name
    refant = [n for n in a.refant.split(",") if n]
    ctx = CasaCtx(arm, "small" if twin else "full", refant)
    only = set(a.only.split(",")) - {""}
    want = lambda k: not only or k in only
    path = arm / "result-e1b-casa.json"
    res = json.loads(path.read_text(encoding="utf-8")) if path.exists() and only else {}
    res.update({"mode": "twin" if twin else "chain", "version": ctx.version,
                "ms": str(ms), "scorer": "e1b_casa_score (e1b_score's measures)",
                "refant": refant, "arm": "CASA 6.7.6.14"})  # fmt: skip
    terms = res.setdefault("terms", {})
    if want("k"):
        terms["K"] = S.k_term(ctx, twin)
    if want("composite"):
        terms["composite"] = S.composites(ctx, twin)
    if want("crosshand"):
        terms["crosshand"] = S.crosshand(ctx, twin)
    if want("df"):
        terms["Df"] = S.df_term(ctx, twin)
    if want("flux"):
        terms["F"] = fluxes(ctx)
    if want("pol"):
        res["polarisation"] = pol(ctx, twin)
    if a.rang_run and want("vs_rang"):
        res["vs_rang"] = vs_rang(ctx, Path(a.rang_run))
    if want("export"):
        export(ctx, arm / "export.npz", twin)
        res["export"] = str(arm / "export.npz")
    S.e1_run.write_json(path, res)
    print(json.dumps(res, indent=1, default=S.e1_run._default)[:20000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
