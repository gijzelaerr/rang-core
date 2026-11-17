"""E2-A's rows (research/e2-acceptance.md 6.5; appendix A, E2-A) after the
in-place post chain (9.9, 9.10), on the restored leg's MS itself. Estimators
fixed in 9.11 before any E2-A row value was read.

    python e2_rows_a.py STEP MS R [ARGS]

Self-calibration (rms before and after; the gains are qc-selfcal's):
    selfcal-score     off-source rms of selfcal's image 1 (from CORRECTED_1GC)
                      and of its final image; met when after <= 1.02 x before
                                                                -> R/row-selfcal.json
Target, compact sources and noise (rang's image stage against the oracle
chain: CASA's K1, G1, B1 (e2_casa3b_a.py) applied to the target, WSClean 3.7
at the image stage's settings, unit weights):
    target-prep       FLAG from rang's FLAG after calibrate; CORRECTED_DATA
                      added natively (a copy of DATA), so CASA writes into an
                      existing column over 9p rather than creating one (9.20)
    target-applycal   CASA applycal of CASA's tables, rang's apply entry for
                      the target (gainfield, interp, calwt, applymode)
    target-unit-on    WEIGHT_SPECTRUM renamed away, a unit WEIGHT (CASA's FLAG kept)
    target-wsclean    WSClean 3.7 cleaned, `e2_post.wsclean_argv` on
                      CORRECTED_DATA                            -> R/oracle-a/
    target-unit-off
    target-score      compact ratios (median within 1 %, robust scatter
                      <= 1.5 %), off-source rms (rang <= 1.2 x oracle) and
                      dynamic range (rang >= 0.8 x oracle), within 0.7 deg
                                                                -> R/row-target.json
Flux scale (K, G, B solved on scan 9 only, applied to scan 11):
    flux-prep         FLAG from rang's flag stage (FLAG before calibrate);
                      R/flux/e2a-flux.yaml = e2a-rerun.yaml with data.scans [9]
                      and run.stages [calibrate]
    flux-run          rang-core run of it (frozen wheel venv); its run
                      directory moved to R/flux-run
    flux-score        scan 11 (J1939-6342) corrected by R/flux-run's K1, G1, B1
                      in memory (rang's library apply); per 100 MHz bin the
                      median over channels of I / SR2016 I; met when within
                      2 % in every bin with >= 10 % unflagged   -> R/row-flux.json
Finally:
    final-restore     every column not in columns-before.json dropped, FLAG
                      from rang_original, hashes against INPUT  -> R/final-restore.json
"""

import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import e2_post as P

FCAL = "J1939-6342"
RADIUS_DEG = 0.7
ROW_COMPACT = {"median": 0.01, "scatter": 0.015}
WPY = r"C:\Users\gijsm\Build\tmp\20261111-e2-wheel\venv\Scripts\python.exe"
BIN_HZ = 100e6


def moved(r):
    m = Path(r) / "rang-run-moved"
    return m if m.is_dir() else Path(r) / "rang-run"


def score3c():
    import importlib.util

    spec = importlib.util.spec_from_file_location("e2_score3c_a", HERE / "e2_score3c_a.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def restored_only(ms):
    held = [c for c in P.ms_columns(ms) if c.startswith(("RANG_", "E2_"))]
    if held or P.run_dir(ms).exists():
        raise SystemExit(f"restore has not run on {ms} (or a run directory is there): {held}")


# --- off-source rms, shared by the self-calibration and target rows ------------------


def offsource(images, residual, radius_deg=RADIUS_DEG):
    """rms (sqrt of the mean square) and peak of each restored image within
    `radius_deg` of the centre, outside the sources of all of them: the
    mean of the images above 5 sigma (1.4826 MAD of `residual` over the
    inner two-thirds), dilated by 2 beams. `images` [(data, header)]."""
    from scipy import ndimage

    s = score3c()
    h = images[0][1]
    shape = images[0][0].shape
    sigma = s.mad(residual[s.inner(shape)])
    bmaj = h["BMAJ"] / abs(h["CDELT2"])
    mean = sum(a for a, _ in images) / len(images)
    mask = ndimage.binary_dilation(mean > 5 * sigma, iterations=max(1, math.ceil(2 * bmaj)))
    inside = s.radius_deg(h, shape) <= radius_deg
    use = inside & ~mask
    out = []
    for a, _ in images:
        rms = float(np.sqrt(np.mean(a[use] ** 2)))
        peak = float(a[inside].max())
        out.append({"rms_jy": rms, "peak_jy": peak, "dynamic_range": peak / rms})
    return out, {"sigma_jy": sigma, "pixels": int(use.sum()), "masked": int((mask & inside).sum())}


def mfs(d, kind):
    (p,) = sorted(Path(d).glob(f"*MFS-{kind}.fits"))
    return score3c()._open(p)


def selfcal_score(ms, r):
    r = Path(r)
    base = moved(r) / "selfcal"
    (field,) = [p for p in base.iterdir() if p.is_dir()]
    before, after = field / "round-1", field / "final"
    a, b = mfs(before, "image"), mfs(after, "image")
    score3c().same_grid(a, b, "selfcal images")
    arms, info = offsource([(a[0], a[1]), (b[0], b[1])], mfs(before, "residual")[0])
    ratio = arms[1]["rms_jy"] / arms[0]["rms_jy"]
    out = {"field": field.name, "image_1": arms[0], "final": arms[1], "ratio_after_before": ratio,
           "limit": 1.02, "met": ratio <= 1.02, **info,
           "gains": "qc-selfcal.json (9.10's amended form)"}  # fmt: skip
    P.write(r / "row-selfcal.json", out)
    return 0


# --- the target rows: the oracle chain ------------------------------------------------


def after_calibrate(r):
    return json.loads((Path(r) / "rang-run" / "apply" / "summary.json").read_text())["flag_version"]


def target_prep(ms, r):
    from rang import core_writeback

    ms, r = Path(ms), Path(r)
    restored_only(ms)
    if not (r / "casa" / "tables" / "B1").is_dir():
        raise SystemExit("e2_casa3b_a.py run has not written CASA's tables")
    version = after_calibrate(r)
    t0 = time.perf_counter()
    rows = core_writeback.restore_flags(ms, version)
    with core_writeback.WriteBack(ms, stage="e2a-oracle") as w:
        added = w.ensure_column("CORRECTED_DATA", init="data")
    P.write(r / "target-prep.json", {"flag_version": version, "rows": rows, "column_added": added,
                                     "seconds": time.perf_counter() - t0})  # fmt: skip
    return 0


def target_applycal(ms, r):
    ms, r = Path(ms), Path(r)
    s = json.loads((r / "rang-run" / "image" / "summary.json").read_text(encoding="utf-8"))
    (target,) = {e["field"] for e in s["images"]}  # the imaged field (E2-A: ESO137-001)
    calls = [c for c in P.applycal_spec(r, f"/c/{ms.name}") if c["field"] == target]
    if len(calls) != 1:
        raise SystemExit(f"rang's apply summary has {len(calls)} entries for {target}")
    for c in calls:
        c["gaintable"] = [g.replace("/p/rang-run/calibrate/", "/p/casa/tables/") for g in c["gaintable"]]
    P.write(r / "target-applycal-spec.json", calls)
    (r / "e2p_applycal.py").write_text(P.APPLY_PY, encoding="utf-8")
    return P.docker(r, P.CASA_IMAGE, P.inplace_mounts(ms, r),
                    "/opt/casa/bin/python -I /p/e2p_applycal.py /p/target-applycal-spec.json "
                    "/p/target-applycal-result.json", "target-applycal", 2)  # fmt: skip


UNIT_ORACLE_PY = r"""
import json, sys
import numpy as np
from casacore.tables import table, makecoldesc
ms, mode, out = sys.argv[1:4]
t = table(ms, readonly=False, ack=False)
cols = t.colnames()
if mode == "on":
    assert "E2_WEIGHT" not in cols and "CORRECTED_DATA" in cols, cols
    n = t.nrows()
    t.renamecol("WEIGHT_SPECTRUM", "E2_WEIGHT_SPECTRUM")
    t.renamecol("WEIGHT", "E2_WEIGHT")
    desc = t.getcoldesc("E2_WEIGHT")
    t.addcols(makecoldesc("WEIGHT", desc),
              {"TYPE": "StandardStMan", "NAME": "E2UnitWeight", "SPEC": {}})
    t.putcol("WEIGHT", np.ones((n, t.getcell("E2_WEIGHT", 0).shape[0]), np.float32))
else:
    assert "E2_WEIGHT" in cols, cols
    t.removecols(["WEIGHT"])
    t.renamecol("E2_WEIGHT", "WEIGHT")
    t.renamecol("E2_WEIGHT_SPECTRUM", "WEIGHT_SPECTRUM")
rec = {"mode": mode, "columns": t.colnames()}
t.close()
json.dump(rec, open(out, "w"), indent=1)
print(json.dumps(rec))
"""


def _unit_oracle(ms, r, mode):
    ms, r = Path(ms), Path(r)
    (r / "e2p_unit_oracle.py").write_text(UNIT_ORACLE_PY, encoding="utf-8")
    return P.docker(r, P.FORMATS_IMAGE, P.inplace_mounts(ms, r),
                    f"{P.QC_PY} -I /p/e2p_unit_oracle.py /c/{ms.name} {mode} /p/target-unit-{mode}.json",
                    f"target-unit-{mode}", 1)  # fmt: skip


def target_unit_on(ms, r):
    res = json.loads((Path(r) / "target-applycal-result.json").read_text())
    if not res or any(x["error"] for x in res):
        raise SystemExit(f"CASA applycal failed: {res}")
    return _unit_oracle(ms, r, "on")


def target_unit_off(ms, r):
    return _unit_oracle(ms, r, "off")


def target_wsclean(ms, r, threads="4"):
    ms, r = Path(ms), Path(r)
    if "E2_WEIGHT" not in P.ms_columns(ms):
        raise SystemExit("run target-unit-on first")
    s = json.loads((r / "rang-run" / "image" / "summary.json").read_text(encoding="utf-8"))
    (entry,) = s["images"]
    tag = entry["field"].replace("+", "p").replace("-", "m")
    d = r / "oracle-a"
    (d / "tmp").mkdir(parents=True, exist_ok=True)
    argv, dropped = P.wsclean_argv(entry["argv"], name=f"/p/oracle-a/{tag}-clean",
                                   column="CORRECTED_DATA", threads=threads, temp="/p/oracle-a/tmp",
                                   ms_inside=f"/c/{ms.name}", dirty=False)  # fmt: skip
    t0 = time.perf_counter()
    rc = P.docker(r, P.WSCLEAN_IMAGE, P.inplace_mounts(ms, r), " ".join(argv), "oracle-a-clean",
                  int(threads))  # fmt: skip
    shutil.rmtree(d / "tmp", ignore_errors=True)
    P.write(r / "oracle-a-run.json", {"exit": rc, "argv": argv, "dropped": dropped,
                                      "seconds": time.perf_counter() - t0})  # fmt: skip
    return rc


def target_score(ms, r):
    r = Path(r)
    s = score3c()
    rdir, tag, nch = s.rang_images(r)
    odir = r / "oracle-a"
    comp = s.compact(rdir, odir, tag, nch)
    ratios = [x["ratio"] for x in comp["sources"] if x["in_0p7deg"]]
    gate = {"n": len(ratios)}
    if ratios:
        gate.update(median=float(np.median(ratios)), robust_scatter=s.mad(ratios))
    gate["met"] = (bool(abs(gate["median"] - 1) <= ROW_COMPACT["median"]
                        and gate["robust_scatter"] <= ROW_COMPACT["scatter"])
                   if len(ratios) >= 3 else None)  # fmt: skip
    a = s._open(rdir / "image-MFS-image.fits")
    b = s._open(odir / f"{tag}-clean-MFS-image.fits")
    arms, info = offsource([(a[0], a[1]), (b[0], b[1])],
                           s._open(odir / f"{tag}-clean-MFS-residual.fits")[0])  # fmt: skip
    noise = {"rang": arms[0], "oracle": arms[1],
             "rms_ratio": arms[0]["rms_jy"] / arms[1]["rms_jy"],
             "dynamic_range_ratio": arms[0]["dynamic_range"] / arms[1]["dynamic_range"], **info}  # fmt: skip
    noise["met"] = bool(noise["rms_ratio"] <= 1.2 and noise["dynamic_range_ratio"] >= 0.8)
    out = {"compact": {"gated_within_0p7deg": gate, "tolerance": ROW_COMPACT,
                       "sources": comp["sources"], "radial": comp["radial"],
                       "reported": comp["reported"]},
           "noise_dynamic_range": noise,
           "caveat": "WSClean grids 4,096 channels, GeMClean 512 averaged (9.10)"}  # fmt: skip
    P.write(r / "row-target.json", out)
    return 0


# --- flux scale -------------------------------------------------------------------------


def flux_config(text, scans="9, 10, 11", solve="9"):
    """The flux row's configuration: `text` with data.scans `solve` in place
    of `scans` and run.stages [calibrate]; every edit must match once."""
    scans, solve = (", ".join(x.replace(" ", "").split(",")) for x in (scans, solve))
    nl = chr(10)
    for old, new in ((f"  scans: [{scans}]{nl}", f"  scans: [{solve}]{nl}"),
                     (f"  stages: [flag, calibrate, apply, image, selfcal]{nl}",
                      f"  stages: [calibrate]{nl}")):  # fmt: skip
        if text.count(old) != 1:
            raise SystemExit(f"config edit not unique: {old!r}")
        text = text.replace(old, new)
    return text


def flux_prep(ms, r, config=None, scans="9, 10, 11", solve="9"):
    """`config`, `scans` and `solve` are the development smoke's overrides only."""
    from rang import core_writeback

    ms, r = Path(ms), Path(r)
    restored_only(ms)
    st = json.loads((moved(r) / "state.json").read_text())
    version = st["stages"]["calibrate"]["flag_version"]  # FLAG before calibrate
    rows = core_writeback.restore_flags(ms, version)
    d = r / "flux"
    d.mkdir(exist_ok=True)
    text = flux_config(Path(config or HERE / "e2a-rerun.yaml").read_text(encoding="utf-8"),
                       scans, solve)
    head = "# e2_rows_a.py flux-prep: e2a-rerun.yaml, calibrate on scan 9 only (6.5 flux row).\n"
    (d / "e2a-flux.yaml").write_text(head + text, encoding="utf-8")
    shutil.copy(HERE / "mk_rfi_flagging_calibrator_fields_firstpass.yaml", d)
    P.write(r / "flux-prep.json", {"flag_version": version, "rows": rows})
    return 0


def flux_run(ms, r):
    ms, r = Path(ms), Path(r)
    if (r / "flux-run").exists():
        raise SystemExit(f"{r / 'flux-run'} exists")
    t0 = time.perf_counter()
    with open(r / "flux-run.log", "w", encoding="utf-8") as fh:
        rc = subprocess.run([WPY, "-m", "rang.core_cli", "run", str(r / "flux" / "e2a-flux.yaml"),
                             str(ms)], stdout=fh, stderr=subprocess.STDOUT, check=False).returncode  # fmt: skip
    if P.run_dir(ms).exists():
        shutil.move(str(P.run_dir(ms)), str(r / "flux-run"))
    P.write(r / "flux-run.json", {"exit": rc, "seconds": time.perf_counter() - t0})
    return rc


def stokes_i_per_channel(ms, rows, tables, fid, block=2000):
    """Per channel: the mean of Re((XX + YY) / 2) over rows whose four
    correlations are unflagged after the apply (E2-B rows' rule), and the
    count of such cells. Cross-correlations only."""
    from rang import cal_apply, core_ms

    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ")[0], np.float64)
    s = np.zeros(len(freq))
    n = np.zeros(len(freq), np.int64)
    total = 0
    with core_ms.open_table(ms) as t:
        for b0 in range(0, len(rows), block):
            part = rows[b0 : b0 + block]
            lo, hi = int(part[0]), int(part[-1]) + 1
            pick = part - lo
            data = np.asarray(t.getcol("DATA", lo, hi - lo))[pick]
            flag = np.asarray(t.getcol("FLAG", lo, hi - lo), bool)[pick]
            meta = {c: np.asarray(t.getcol(c, lo, hi - lo))[pick]
                    for c in ("TIME", "ANTENNA1", "ANTENNA2", "FLAG_ROW")}  # fmt: skip
            flag |= meta["FLAG_ROW"][:, None, None]
            v, f = cal_apply.apply(data, flag, meta["TIME"], meta["ANTENNA1"], meta["ANTENNA2"],
                                   freq, tables, field_id=fid, interp="linear")  # fmt: skip
            good = ~f.any(-1)
            i = 0.5 * (v[..., 0].real + v[..., 3].real)
            s += np.where(good, i, 0).sum(0)
            n += good.sum(0)
            total += len(part)
    return freq, s, n, total


def flux_bins(freq, s, n, total, model_i):
    out = []
    edges = np.arange(freq.min(), freq.max() + BIN_HZ, BIN_HZ)
    for lo in edges[:-1]:
        ch = (freq >= lo) & (freq < lo + BIN_HZ)
        if not ch.any():
            continue
        frac = float(n[ch].sum() / (total * ch.sum()))
        use = ch & (n > 0)
        ratios = s[use] / n[use] / model_i[use]
        rec = {"lo_mhz": lo / 1e6, "unflagged_fraction": frac, "channels": int(use.sum()),
               "median_ratio": float(np.median(ratios)) if use.any() else None}  # fmt: skip
        rec["counted"] = frac >= 0.10 and rec["median_ratio"] is not None
        rec["met"] = bool(rec["counted"] and abs(rec["median_ratio"] - 1) <= 0.02)
        out.append(rec)
    return out


def flux_score(ms, r, scan="11", field=FCAL):
    from rang import core_ms, fluxstd
    from rang.formats import caltable

    ms, r = Path(ms), Path(r)
    with core_ms.open_table(ms / "FIELD") as t:
        fid = [str(x) for x in t.getcol("NAME")].index(field)
    with core_ms.open_table(ms) as t:
        m = {c: np.asarray(t.getcol(c, 0, t.nrows)) for c in ("FIELD_ID", "SCAN_NUMBER", "ANTENNA1", "ANTENNA2")}
    rows = np.flatnonzero((m["FIELD_ID"] == fid) & (m["SCAN_NUMBER"] == int(scan))
                          & (m["ANTENNA1"] != m["ANTENNA2"]))  # fmt: skip
    res = {"rows": len(rows), "readings": {}}
    for label, cal in (("scan9_tables", r / "flux-run" / "calibrate"),
                       ("full_run_tables_context", moved(r) / "calibrate")):  # fmt: skip
        tables = [caltable.read(cal / n) for n in ("K1", "G1", "B1")]
        freq, s, n, total = stokes_i_per_channel(ms, rows, tables, fid)
        model = fluxstd.flux(field, freq, "Stevens-Reynolds 2016")[..., 0]
        bins = flux_bins(freq, s, n, total, model)
        counted = [b for b in bins if b["counted"]]
        res["readings"][label] = {"tables": str(cal), "bins": bins,
                                  "met": bool(counted) and all(b["met"] for b in counted)}  # fmt: skip
    res["met"] = res["readings"]["scan9_tables"]["met"]
    res["gate"] = "scan9_tables; the full run's tables are context only"
    P.write(r / "row-flux.json", res)
    return 0


def final_restore(ms, r, input_json):
    ms = Path(ms)
    if P.run_dir(ms).exists():
        raise SystemExit(f"{P.run_dir(ms)} exists: move it first")
    return P.restore(ms, r, input_json, label="final-restore")


STEPS = {"selfcal-score": selfcal_score, "target-prep": target_prep,
         "target-applycal": target_applycal, "target-unit-on": target_unit_on,
         "target-wsclean": target_wsclean, "target-unit-off": target_unit_off,
         "target-score": target_score, "flux-prep": flux_prep, "flux-run": flux_run,
         "flux-score": flux_score, "final-restore": final_restore}  # fmt: skip


if __name__ == "__main__":
    step, ms, r, *rest = sys.argv[1:]
    P.log(r, f"rows step {step} {ms} {rest}")
    sys.exit(STEPS[step](ms, r, *rest))
