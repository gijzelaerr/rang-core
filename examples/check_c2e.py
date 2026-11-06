"""Host side of task C2e (research/c2e-calibrate.md): `rang-core calibrate`
with K, G, B, A and F against the library chain (gate 1) and against CASA's
chain (gate 2). Worktree venv; every container step is one network-less run
(`check_formats.docker`), timed.

    python examples/check_c2e.py identity <run> I-slice|I-a1
    python examples/check_c2e.py casa <run> C-slice|C-a1|H-h128 [--h128 <dir>]

`<run>` is a fresh `/mnt/d/rang/outputs/c2e-<date>-NN`. Inputs are read in
place: O-CASA's slice (under `~/Github/rang/outputs`), A1 small and, for
H-h128, the held-out version's directory (`--h128`). Exit 0 only when every
gated item passes; `result.json` holds everything.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import check_formats as cf
from check_gain import a1_model, rfi_flags
from rang import applycal, cal_apply, cal_chain, calmodels, core_flag, core_ms
from rang.formats import caltable

CASA = "/opt/casa/bin/python"
OUTPUTS = Path.home() / "Github/rang/outputs"
A1 = Path("/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small")
STRATEGY = (
    OUTPUTS
    / "caracal-strategy-inputs-8f7bb363/mk_rfi_flagging_calibrator_fields_firstpass.yaml"
)
# The worktree venv's console script; C2E_RANG_CORE overrides it (the run's
# log records which was used).
RANG_CORE = Path(os.environ.get("C2E_RANG_CORE", ROOT / ".venv/bin/rang-core"))
TOL = {"median": 7e-4, "p95": 3e-3, "fd": 1e-3}
COLUMNS = (
    "DATA",
    "MODEL_DATA",
    "CORRECTED_DATA",
    "FLAG",
    "FLAG_ROW",
    "WEIGHT",
    "WEIGHT_SPECTRUM",
    "SIGMA",
)


def write(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, default=_default) + "\n")


def _default(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    return str(x)


def copy_ms(src, dst):
    shutil.copytree(src, dst)  # with table.lock: rang's writer needs it
    return Path(dst)


def colnames(ms):
    with core_ms.open_table(ms) as t:
        return set(t.colnames())


def column_sha(ms, name):
    with core_ms.open_table(ms) as t:
        if name not in t.colnames():
            return None
        try:
            v = t.getcol(name)
        except (OSError, ValueError):
            return "undefined"
    return hashlib.sha256(np.ascontiguousarray(v).tobytes()).hexdigest()


def table_equal(a, b):
    """Every main cell, keyword and subtable cell of two CASA tables."""
    ta, tb = caltable.read(a), caltable.read(b)
    diffs = []
    if ta.vis_cal != tb.vis_cal:
        diffs.append("VisCal")
    if ta.keywords != tb.keywords:
        diffs.append("keywords")
    for part, ma, mb in [("main", ta.main, tb.main)] + [
        (f"sub {k}", ta.subtables[k], tb.subtables.get(k, {})) for k in ta.subtables
    ]:
        if set(ma) != set(mb):
            diffs.append(f"{part}: columns")
            continue
        for name in ma:
            xs, ys = ma[name], mb[name]
            if len(xs) != len(ys):
                diffs.append(f"{part} {name}: rows")
                continue
            for x, y in zip(xs, ys):
                if (x is None) != (y is None) or (
                    x is not None and not np.array_equal(np.asarray(x), np.asarray(y))
                ):
                    diffs.append(f"{part} {name}")
                    break
    files_a = sorted(p.relative_to(a) for p in Path(a).rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(b) for p in Path(b).rglob("*") if p.is_file())
    same_files = files_a == files_b and all(
        (Path(a) / f).read_bytes() == (Path(b) / f).read_bytes() for f in files_a
    )
    return {"equal": not diffs, "differences": diffs, "files_identical": same_files}


def rang_core(*argv, log):
    with open(log, "w", encoding="utf-8") as fh:
        done = subprocess.run(
            [str(RANG_CORE), *map(str, argv)],
            check=False,
            stdout=fh,
            stderr=subprocess.STDOUT,
        )
    if done.returncode:
        raise SystemExit(f"rang-core {argv[0]} failed, see {log}")


# --- gate 1 ------------------------------------------------------------------------

SLICE_CONFIG = """\
version: 1
fields: {fcal: [1]}
flag: {strategy: %(strategy)s}
calibrate:
  model: {source: column}
  refant: m000
  minblperant: 3
  primary:
    terms:
      - {type: K, name: K0, solint: inf}
      - {type: G, name: G0, solint: inf, preapply: [K0], interp: [linear]}
      - {type: B, name: B0, solint: inf, combine: scan, fillgaps: 70, preapply: [K0, G0],
         interp: [linear, linear]}
      - {type: A, name: A0}
      - {type: K, name: K1, solint: int, preapply: [G0, B0], interp: [linear, linear]}
      - {type: G, name: G1, solint: int, preapply: [K1, B0], interp: [linear, linear]}
      - {type: B, name: B1, solint: inf, combine: scan, fillgaps: 70, preapply: [K1, G1],
         interp: [linear, linear]}
apply:
  targets:
    - {field: [1], tables: [K1, G1, B1]}
run: {stages: [calibrate, apply]}
"""

A1_CONFIG = """\
version: 1
fields: {fcal: [J1939-6342], gcal: [SIM-GCAL], target: [SIM-TARGET]}
data: {weights: uniform, scans: %(scans)s}
flag: {strategy: %(strategy)s}
calibrate:
  model: {source: setjy, standard: Stevens-Reynolds 2016}
  refant: m000
  uvrange: ">150"
  primary:
    terms:
      - {type: K, name: K, solint: inf}
      - {type: G, name: G, solint: inf, preapply: [K], interp: [linear]}
      - {type: B, name: B, solint: inf, combine: scan, fillgaps: 70, preapply: [K, G],
         interp: [linear, linear]}
      - {type: A, name: A}
  secondary:
    terms:
      - {type: G, name: Gsec, solint: 60s, preapply: [K, B], interp: [linear, linear]}
      - {type: A, name: Asec}
      - {type: F, name: F, solint: inf, preapply: [K, B], interp: [linear, linear]}
apply:
  targets:
    - {field: [fcal], tables: [K, G, B]}
    - {field: [gcal, target], tables: [K, F, B],
       gainfield: [J1939-6342, nearest, J1939-6342]}
run: {stages: [calibrate, apply]}
"""


def solve_kw(**over):
    out = {
        "solint": "inf",
        "combine": "",
        "refant": ["m000"],
        "refantmode": "flex",
        "minsnr": 3.0,
        "minblperant": 4,
        "uvrange": "",
        "max_iterations": 50,
        "stop_criterion": 1e-7,
        "stop_fraction": 0.99,
        "model": "column",
    }
    out.update(over)
    return out


def identity_reference(case, ms, out, scans):
    """The hand-written library chain of each identity case."""
    strategies = core_flag.parse_strategy(STRATEGY.read_text(encoding="utf-8"))
    masks = [core_flag.load_static_mask(p) for p in core_flag.static_mask_files()]
    extra = {}
    if case == "I-slice":
        kw = solve_kw(minblperant=3)
        b = {"combine": "scan", "fillgaps": 70}
        terms = [
            {"type": "K", "name": "K0", "fields": [1], **kw, "preapply": [], "interp": []},
            {"type": "G", "name": "G0", "fields": [1], **kw, "calmode": "ap",
             "preapply": ["K0"], "interp": ["linear"]},
            {"type": "B", "name": "B0", "fields": [1], **kw, **b,
             "preapply": ["K0", "G0"], "interp": ["linear", "linear"]},
            {"type": "A", "name": "A0", "fields": [1], "tables": ["K0", "G0", "B0"],
             "gainfield": ["1", "1", "1"], "strategies": strategies},
            {"type": "K", "name": "K1", "fields": [1], **kw, "solint": "int",
             "preapply": ["G0", "B0"], "interp": ["linear", "linear"]},
            {"type": "G", "name": "G1", "fields": [1], **kw, "solint": "int", "calmode": "ap",
             "preapply": ["K1", "B0"], "interp": ["linear", "linear"]},
            {"type": "B", "name": "B1", "fields": [1], **kw, **b,
             "preapply": ["K1", "G1"], "interp": ["linear", "linear"]},
        ]  # fmt: skip
        weight_column = (
            "WEIGHT_SPECTRUM" if "WEIGHT_SPECTRUM" in colnames(ms) else "WEIGHT"
        )
        # C2c's primary(): the first round, before A changes FLAG.
        prim = cal_chain.primary(
            ms, field_id=1, refant=["m000"], b_combine="scan", minblperant=3,
            fillgaps=70,
        )  # fmt: skip
        pdir = out.parent / "primary"
        pdir.mkdir()
        for k, v in prim.items():
            caltable.write(v[0], pdir / f"{k}0")
        extra["primary_dir"] = str(pdir)
        result = cal_chain.run(ms, terms, out_dir=out, weight_column=weight_column,
                               masks=masks)  # fmt: skip
        applycal.applycal(ms, [out / n for n in ("K1", "G1", "B1")], interp=["linear"],
                          gainfield=[""], calwt=[False], field=[1])  # fmt: skip
        return result, extra
    # I-a1: setjy on field 0, unit weights, data.scans.
    calmodels.set_model(ms, [0], calmodels.Standard(standard="Stevens-Reynolds 2016"))
    kw = solve_kw(uvrange=">150")
    k = {**kw, "uvrange": ""}
    sec = {**kw, "model": "unit"}
    terms = [
        {"type": "K", "name": "K", "fields": [0], **k, "preapply": [], "interp": []},
        {"type": "G", "name": "G", "fields": [0], **kw, "calmode": "ap",
         "preapply": ["K"], "interp": ["linear"]},
        {"type": "B", "name": "B", "fields": [0], **kw, "combine": "scan", "fillgaps": 70,
         "preapply": ["K", "G"], "interp": ["linear", "linear"]},
        {"type": "A", "name": "A", "fields": [0], "tables": ["K", "G", "B"],
         "gainfield": ["0", "0", "0"], "strategies": strategies},
        {"type": "G", "name": "Gsec", "fields": [2], **sec, "solint": "60s",
         "calmode": "ap", "preapply": ["K", "B"], "interp": ["linear", "linear"]},
        {"type": "A", "name": "Asec", "fields": [2], "tables": ["K", "B", "Gsec"],
         "gainfield": ["0", "0", "2"], "strategies": strategies},
        {"type": "F", "name": "F", "fields": [2], **sec, "calmode": "ap",
         "preapply": ["K", "B"], "interp": ["linear", "linear"], "base": "G",
         "smodel": [1.0, 0.0, 0.0, 0.0]},
    ]  # fmt: skip
    result = cal_chain.run(ms, terms, out_dir=out, weight_column=None, scan=scans,
                           masks=masks)  # fmt: skip
    applycal.applycal(ms, [out / n for n in ("K", "G", "B")], interp=["linear"],
                      gainfield=[""], calwt=[False], field=[0], scan=scans)  # fmt: skip
    applycal.applycal(ms, [out / n for n in ("K", "F", "B")], interp=["linear"],
                      gainfield=["J1939-6342", "nearest", "J1939-6342"], calwt=[False],
                      field=[2, 3], scan=scans)  # fmt: skip
    return result, extra


def identity(run, case):
    run.mkdir(parents=True)
    if case == "I-slice":
        src = OUTPUTS / "o-casa-20261030-01/work.ms"
        config_text = SLICE_CONFIG % {"strategy": STRATEGY}
        scans = None
    else:
        src = A1 / "a1-small.ms"
        with core_ms.open_table(src) as t:
            all_scans = sorted({int(s) for s in t.getcol("SCAN_NUMBER")})
        scans = all_scans[:-1]
        config_text = A1_CONFIG % {"strategy": STRATEGY, "scans": json.dumps(scans)}
    name = src.name
    cmd = copy_ms(src, run / "cmd" / name)
    ref = copy_ms(src, run / "lib" / name)
    config = run / "config.yaml"
    config.write_text(config_text, encoding="utf-8")
    rang_core("run", config, cmd, log=run / "rang-core.log")
    summary = json.loads(
        (run / "cmd" / f"{name}.rang-run/calibrate/summary.json").read_text()
    )
    out = run / "lib" / "tables"
    result, extra = identity_reference(case, ref, out, scans)
    report = {"case": case, "tables": {}, "columns": {}}
    made = [t["name"] for t in summary["tables"]]
    made += [f"{t['name']}.append" for t in summary["tables"] if t["type"] == "F"]
    for n in made:
        report["tables"][n] = table_equal(
            run / "cmd" / f"{name}.rang-run/calibrate" / n, out / n
        )
    if extra.get("primary_dir"):
        for k in ("K", "G", "B"):
            report["tables"][f"primary {k}0"] = table_equal(
                Path(extra["primary_dir"]) / f"{k}0", out / f"{k}0"
            )
    for c in COLUMNS:
        a, b = column_sha(cmd, c), column_sha(ref, c)
        report["columns"][c] = {"cmd": a, "lib": b, "equal": a == b}
    from rang.formats import flagversions

    orig = flagversions.load(cmd, "rang_original")[0]
    with core_ms.open_table(src) as t:
        report["rang_original_equals_input"] = bool(
            np.array_equal(orig, t.getcol("FLAG"))
        )
    report["steps"] = [
        {
            k: v
            for k, v in s.items()
            if k in ("type", "name", "fields", "warning", "fluxscale")
        }
        for s in summary["steps"]
    ]
    report["a_flagged"] = [
        {"name": s["name"], "before": s["flagged"]["flagged_before"],
         "after": s["flagged"]["flagged_after"]}
        for s in result["steps"] if s["type"] == "A"
    ]  # fmt: skip
    report["pass"] = bool(
        all(v["equal"] for v in report["tables"].values())
        and all(v["equal"] for v in report["columns"].values())
        and report["rang_original_equals_input"]
        and len(made)
        == len(result["tables"]) + sum(1 for s in result["steps"] if s["type"] == "F")
    )
    write(run / "result.json", report)
    return report


# --- gate 2 ------------------------------------------------------------------------


def casa_case(case, h128):
    """(source MS, truth, rfi, fcal id, gcal id or None, settings)."""
    if case == "C-slice":
        return {"src": OUTPUTS / "o-casa-20261030-01/work.ms", "truth": None, "rfi": None,
                "fcal": 1, "gcal": None, "mbl": 3, "uvrange": "", "bcombine": ""}  # fmt: skip
    base = A1 if case == "C-a1" else Path(h128)
    stem = "a1-small" if case == "C-a1" else "a1-holdout128"
    return {"src": base / f"{stem}.ms", "truth": base / "truth.npz",
            "rfi": base / f"{stem}.rfi_mask.npz", "fcal": 0, "gcal": 2, "mbl": 4,
            "uvrange": ">150", "bcombine": "scan"}  # fmt: skip


def field_names(ms):
    with core_ms.open_table(Path(ms) / "FIELD") as t:
        return [str(n) for n in t.getcol("NAME")]


def casa_steps(d, names):
    ms = "/run/casa.ms"
    f, g = d["fcal"], d["gcal"]
    common = {"vis": ms, "refant": "m000", "refantmode": "flex", "minsnr": 3.0,
              "minblperant": d["mbl"], "parang": False}  # fmt: skip
    t = "/run/casa"
    # CASA's bandpass has no refantmode argument (flex is its rule).
    nomode = {k: v for k, v in common.items() if k != "refantmode"}
    steps = [
        {"label": "K", "task": "gaincal", "args": {**common, "caltable": f"{t}/K",
         "field": str(f), "gaintype": "K", "solint": "inf", "combine": ""}},
        {"label": "G", "task": "gaincal", "args": {**common, "caltable": f"{t}/G",
         "field": str(f), "gaintype": "G", "calmode": "ap", "solint": "inf", "combine": "",
         "uvrange": d["uvrange"], "gaintable": [f"{t}/K"], "interp": ["linear"]}},
        {"label": "B", "task": "bandpass", "args": {**nomode, "caltable": f"{t}/B",
         "field": str(f), "bandtype": "B", "solint": "inf", "combine": d["bcombine"],
         "solnorm": False, "fillgaps": 70, "uvrange": d["uvrange"],
         "gaintable": [f"{t}/K", f"{t}/G"], "interp": ["linear", "linear"]}},
    ]  # fmt: skip
    apply = {"vis": ms, "applymode": "calflag", "calwt": [False], "parang": False,
             "flagbackup": False}  # fmt: skip
    steps.append({"label": "apply fcal", "task": "applycal", "args": {**apply,
                  "field": str(f), "gaintable": [f"{t}/K", f"{t}/G", f"{t}/B"],
                  "interp": ["linear"] * 3, "gainfield": ["", "", ""]}})  # fmt: skip
    if g is None:
        return steps
    steps += [
        {"label": "copy G", "task": "copytree", "args": {"src": f"{t}/G", "dst": f"{t}/Gapp"}},
        {"label": "F gaincal", "task": "gaincal", "args": {**common, "caltable": f"{t}/Gapp",
         "field": str(g), "gaintype": "G", "calmode": "ap", "solint": "inf", "combine": "",
         "uvrange": d["uvrange"], "append": True, "smodel": [1.0, 0.0, 0.0, 0.0],
         "gaintable": [f"{t}/K", f"{t}/B"], "interp": ["linear", "linear"],
         "gainfield": [names[f], names[f]]}},
        {"label": "fluxscale", "task": "fluxscale", "args": {"vis": ms, "caltable": f"{t}/Gapp",
         "fluxtable": f"{t}/F", "reference": names[f], "transfer": ""}},
        {"label": "apply gcal", "task": "applycal", "args": {**apply, "field": str(g),
         "gaintable": [f"{t}/K", f"{t}/F", f"{t}/B"], "interp": ["linear"] * 3,
         "gainfield": [names[f], "nearest", names[f]]}},
    ]  # fmt: skip
    return steps


CASA_CONFIG = """\
version: 1
fields: {fcal: [%(fcal)d]%(gcal_field)s}
calibrate:
  model: {source: column}
  refant: m000
  minblperant: %(mbl)d
  uvrange: "%(uvrange)s"
  primary:
    terms:
      - {type: K, name: K, solint: inf}
      - {type: G, name: G, solint: inf, preapply: [K], interp: [linear]}
      - {type: B, name: B, solint: inf, combine: "%(bcombine)s", fillgaps: 70,
         preapply: [K, G], interp: [linear, linear]}
%(secondary)sapply:
  targets:
    - {field: [fcal], tables: [K, G, B]}
%(gcal_target)srun: {stages: [calibrate, apply]}
"""


def casa_config(d, names):
    sec = gt = gf = ""
    if d["gcal"] is not None:
        gf = f", gcal: [{d['gcal']}]"
        sec = ("  secondary:\n    terms:\n"
               "      - {type: F, name: F, solint: inf, preapply: [K, B], "
               "interp: [linear, linear]}\n")  # fmt: skip
        fc = names[d["fcal"]]
        gt = (f"    - {{field: [gcal], tables: [K, F, B], "
              f"gainfield: [{fc}, nearest, {fc}]}}\n")  # fmt: skip
    return CASA_CONFIG % {"fcal": d["fcal"], "gcal_field": gf, "mbl": d["mbl"],
                          "uvrange": d["uvrange"], "bcombine": d["bcombine"],
                          "secondary": sec, "gcal_target": gt}  # fmt: skip


def composite(ms, fid, tables, table_fields):
    """`J_p J_q^*` per cross-correlation row, channel and parallel hand."""
    with core_ms.open_table(ms) as t:
        c = {
            n: t.getcol(n) for n in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID", "FLAG")
        }
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        freq = t.getcol("CHAN_FREQ")[0]
    rows = (c["FIELD_ID"] == fid) & (c["ANTENNA1"] != c["ANTENNA2"])
    ones = np.zeros((rows.sum(), len(freq), 4), np.complex64)
    ones[..., 0] = ones[..., 3] = 1
    v, f = cal_apply.apply(ones, np.zeros(ones.shape, bool), c["TIME"][rows],
                           c["ANTENNA1"][rows], c["ANTENNA2"][rows], freq, tables,
                           interp="linear", direction="corrupt", table_fields=table_fields)  # fmt: skip
    return v[..., (0, 3)].astype(np.complex128), f[..., (0, 3)]


def rel_stats(a, fa, b, fb):
    ok = ~fa & ~fb & (np.abs(b) > 0)
    rel = (np.abs(a - b) / np.abs(b))[ok]
    out = {"cells": int(ok.sum()), "flags_exact": bool(np.array_equal(fa, fb)),
           "flags_differ": int((fa != fb).sum())}  # fmt: skip
    if rel.size:
        out.update(median=float(np.median(rel)), p95=float(np.percentile(rel, 95)),
                   max=float(rel.max()))  # fmt: skip
    out["pass"] = bool(rel.size and out["median"] <= TOL["median"] and out["p95"] <= TOL["p95"]
                       and out["flags_exact"])  # fmt: skip
    return out


def corrected(ms, fid):
    with core_ms.open_table(ms) as t:
        c = {n: t.getcol(n) for n in ("FIELD_ID", "ANTENNA1", "ANTENNA2", "CORRECTED_DATA",
                                      "FLAG")}  # fmt: skip
    rows = (c["FIELD_ID"] == fid) & (c["ANTENNA1"] != c["ANTENNA2"])
    return c["CORRECTED_DATA"][rows].astype(np.complex128), c["FLAG"][rows]


def casa(run, case, h128):
    run.mkdir(parents=True)
    d = casa_case(case, h128)
    names = field_names(d["src"])
    # prepare: one copy with the model and RFI flags, written by CASA.
    edits = run / "edits"
    edits.mkdir()
    spec = {}
    if d["truth"] is not None:
        truth = dict(np.load(d["truth"]))
        rows, values = a1_model(d["src"], truth, [d["fcal"]])
        np.savez(edits / "model.npz", rows=rows, values=values)
        spec["model"] = "/run/edits/model.npz"
        with core_ms.open_table(d["src"]) as t:
            nchan = t.getcol("FLAG", 0, 1).shape[1]
        rfi = rfi_flags(d["src"], d["rfi"], nchan)
        np.savez(edits / "rfi.npz", rows=np.arange(len(rfi)), flag=rfi)
        spec["flag"] = "/run/edits/rfi.npz"
    write(edits / "edit.json", spec)
    steps = [f"{CASA} -I /ex/oracle_gain.py qc-copy /src/ms /run/prepared.ms"]
    # Always: CASA's read-write open writes the table.lock rang's writer needs.
    if True:
        steps.append(
            f"{CASA} -I /ex/oracle_fluxscale.py edit /run/prepared.ms /run/edits/edit.json"
        )
    steps += ["cp -r /run/prepared.ms /run/casa.ms", "cp -r /run/prepared.ms /run/rang.ms",
              "mkdir /run/casa"]  # fmt: skip
    mounts = [(run, "/run", "rw"), (HERE, "/ex", "ro"), (d["src"], "/src/ms", "ro")]
    cf.docker(
        cf.CASA_IMAGE, ["sh", "-c", " && ".join(steps)], mounts, f"{case} prepare"
    )
    write(run / "casa-steps.json", casa_steps(d, names))
    cf.docker(cf.CASA_IMAGE, [CASA, "-I", "/ex/oracle_fluxscale.py", "steps",
                              "/run/casa-steps.json", "/run/casa-result.json"],
              mounts, f"{case} casa chain")  # fmt: skip
    config = run / "config.yaml"
    config.write_text(casa_config(d, names), encoding="utf-8")
    rang_core("run", config, run / "rang.ms", log=run / "rang-core.log")
    rdir = run / "rang.ms.rang-run/calibrate"
    summary = json.loads((rdir / "summary.json").read_text())
    rt = {n: caltable.read(rdir / n) for n in ("K", "G", "B")}
    ct = {n: caltable.read(run / "casa" / n) for n in ("K", "G", "B")}
    report = {"case": case, "casa_seconds": [s["seconds"] for s in
              json.loads((run / "casa-result.json").read_text())]}  # fmt: skip
    pooled = [cal_apply.POOLED] * 3
    a, fa = composite(run / "rang.ms", d["fcal"], [rt["K"], rt["G"], rt["B"]], pooled)
    b, fb = composite(run / "casa.ms", d["fcal"], [ct["K"], ct["G"], ct["B"]], pooled)
    report["composite_fcal"] = rel_stats(a, fa, b, fb)
    a, fa = corrected(run / "rang.ms", d["fcal"])
    b, fb = corrected(run / "casa.ms", d["fcal"])
    report["corrected_fcal"] = rel_stats(a[..., (0, 3)], fa[..., (0, 3)], b[..., (0, 3)],
                                         fb[..., (0, 3)])  # fmt: skip
    report["corrected_fcal"]["cross_hands"] = {
        k: v for k, v in rel_stats(a[..., (1, 2)], fa[..., (1, 2)], b[..., (1, 2)],
                                   fb[..., (1, 2)]).items() if k != "pass"}  # fmt: skip
    report["flag_fcal_exact"] = bool(np.array_equal(fa, fb))
    gated = ["composite_fcal", "corrected_fcal"]
    if d["gcal"] is not None:
        g = d["gcal"]
        res = json.loads((run / "casa-result.json").read_text())
        rec = next(s for s in res if s["task"] == "fluxscale")["return"]
        fd_casa = float(rec[str(g)]["fitFluxd"])
        step = next(s for s in summary["steps"] if s["type"] == "F")
        fd_rang = float(step["fluxscale"][names[g]]["fitted_flux_jy"])
        report["fluxscale"] = {"rang": fd_rang, "casa": fd_casa,
                               "rel": abs(fd_rang - fd_casa) / fd_casa}  # fmt: skip
        report["fluxscale"]["pass"] = report["fluxscale"]["rel"] <= TOL["fd"]
        rt["F"] = caltable.read(rdir / "F")
        ct["F"] = caltable.read(run / "casa" / "F")
        fields = [cal_apply.POOLED, g, cal_apply.POOLED]
        a, fa = composite(run / "rang.ms", g, [rt["K"], rt["F"], rt["B"]], fields)
        b, fb = composite(run / "casa.ms", g, [ct["K"], ct["F"], ct["B"]], fields)
        report["composite_gcal"] = rel_stats(a * fd_rang, fa, b * fd_casa, fb)
        a, fa = corrected(run / "rang.ms", g)
        b, fb = corrected(run / "casa.ms", g)
        report["corrected_gcal"] = rel_stats(
            a[..., (0, 3)] / fd_rang,
            fa[..., (0, 3)],
            b[..., (0, 3)] / fd_casa,
            fb[..., (0, 3)],
        )
        report["flag_gcal_exact"] = bool(np.array_equal(fa, fb))
        gated += ["composite_gcal", "corrected_gcal", "fluxscale"]
    report["flags_after_apply_exact"] = bool(
        report["flag_fcal_exact"] and report.get("flag_gcal_exact", True)
    )
    report["pass"] = bool(all(report[k]["pass"] for k in gated)
                          and report["flags_after_apply_exact"])  # fmt: skip
    write(run / "result.json", report)
    return report


def snapshot(run):
    """The run's `.code/`: HEAD, the diff and the untracked files."""
    code = Path(str(run) + ".code")
    code.mkdir(parents=True)
    git = ["git", "-C", str(ROOT)]
    (code / "head.txt").write_text(subprocess.run([*git, "rev-parse", "HEAD"],
                                   capture_output=True, text=True, check=False).stdout)  # fmt: skip
    (code / "diff.patch").write_text(subprocess.run([*git, "diff", "HEAD"],
                                     capture_output=True, text=True, check=False).stdout)  # fmt: skip
    untracked = subprocess.run([*git, "ls-files", "--others", "--exclude-standard"],
                               capture_output=True, text=True, check=False).stdout.split()  # fmt: skip
    if untracked:
        subprocess.run(["tar", "czf", str(code / "untracked.tgz"), "-C", str(ROOT),
                        *untracked], check=True)  # fmt: skip


def main(argv):
    if len(argv) < 4 or argv[1] not in ("identity", "casa"):
        print(__doc__)
        return 2
    run = Path(argv[2])
    snapshot(run)
    if argv[1] == "identity":
        report = identity(run, argv[3])
    else:
        h128 = argv[argv.index("--h128") + 1] if "--h128" in argv else None
        report = casa(run, argv[3], h128)
    write(run / "timings.json", cf.TIMINGS)
    print(json.dumps({k: v for k, v in report.items() if k != "steps"}, indent=1,
                     default=_default))  # fmt: skip
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
