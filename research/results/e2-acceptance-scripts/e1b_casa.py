"""E1b's CASA-chain arm (finish-plan section 7 item 27; research/e1-chain.md
9 item 3): CARACal's full-Stokes chain in CASA 6.7.6.14 (`rang-o-casa`), as
E1's rang configuration runs it (results/e1-chain-scripts/e1_config.yaml),
on m32 and on the small twin, so each E1 failure splits into "CASA too" and
"rang only". The call sequence is C6w's (`examples/check_c6w.py`
`casa_calls`) with E1's additions: Gsec, `flagdata(mode='extend')` with
CARACal's settings before the polcal solves (E0), and the refant list of the
command line (`refantmode` flex).

    python e1b_casa.py prepare ARM {m32,twin} --refant LIST|auto [--asec-flags]
    python3 e1b_casa.py casa ARM                                   (WSL, stdlib)
    python e1b_casa.py check ARM                                   (Windows venv)
    python3 e1b_casa.py drop ARM                                   (WSL, stdlib)

ARM is `D:\\rang\\outputs\\e2-20261110-03-casaarm\\<arm>` (from WSL the
`/mnt/d/...` path). `prepare` copies the input MS to `ARM/ms/`, writes the
input flags (m32: rang's FLAG after its flag stage, the `rang_calibrate_*`
version of E1's `-03`; twin: none) and saves them as flag version
`e1b_casa_input`, writes `casa-spec.json` and the `.code/` snapshot. `casa`
runs the spec in one network-less container (`oracle_pol.py tasks`), which
also saves flag version `e1b_casa_before_apply` before the first applycal;
on the twin it exports CORRECTED_DATA, FLAG and MODEL_DATA. `check` refuses
any task error and checks the flags. `drop` removes DATA, MODEL_DATA, WEIGHT_SPECTRUM and
CORRECTED_DATA from the copy (m32, after `e1b_casa_score.py` has written its
export and scores). Run every CASA step under `tools/heavy_lock.py`.

Deviations from E1's rang chain that CASA cannot avoid: no A step (Asec is
rang's Tricolour port on corrected data; C2e's CASA side has none either),
so F solves on SIM-GCAL without Asec's flags; CASA's own parallactic frame
(E1 runs `polcal.frame: rang`); no self-calibration or image.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
IMAGE = "rang-o-casa:6.7.6.14"
CASA = "/opt/casa/bin/python"
FCAL, XCAL, GCAL, TARGET = "J1939-6342", "3C286-SIM", "SIM-GCAL", "SIM-TARGET"
UVRANGE = ">150"
LIN, NEAR = "linear", "nearest"
INPUT_VERSION = "e1b_casa_input"
APPLY_VERSION = "e1b_casa_before_apply"
M32 = Path(r"D:\rang\outputs\e1-20261109-02-data\a1-full-m32.ms")
M32_RANG = Path(r"D:\rang\outputs\e1-20261109-03\ms\a1-full-m32.ms")
TWIN = Path(r"D:\rang\outputs\fp-a1-20261106-simtruth\small\a1-small-twin.ms")
# CARACal's nrao_xcal.yml 3C286 (rang.calmodels.NRAO_XCAL), setjy manual.
X286 = {"fluxdensity": [14.7172, 0.0, 0.0, 0.0], "spix": [-0.4507, -0.1798, 0.0357],
        "reffreq": "1.47GHz", "polindex": [0.098], "polangle": [0.575959],
        "rotmeas": 0.0}  # fmt: skip
# CARACal's polcal worker "preliminary flags" (research/e0-refant-extend.md 1.2).
EXTEND = {"mode": "extend", "ntime": "60s", "combinescans": True, "growtime": 80.0,
          "growfreq": 80.0, "growaround": True, "flagnearfreq": True,
          "flagneartime": True, "flagbackup": False}  # fmt: skip
# E1's apply targets (e1_config.yaml): field, tables, interp, gainfield.
APPLY = [
    (XCAL, ["K", "G", "B", "Gpol", "Kcross", "Xf", "Df"], [LIN] * 4 + [NEAR] * 3,
     [""] * 7),
    (FCAL, ["K", "G", "B", "Kcross", "Xf", "Df"], [LIN] * 3 + [NEAR] * 3, [""] * 6),
    (GCAL, ["K", "F", "B", "Kcross", "Xf", "Df"], [LIN] * 3 + [NEAR] * 3,
     [FCAL, NEAR, FCAL, "", "", ""]),
    (TARGET, ["K", "F", "B", "Kcross", "Xf", "Df"], [LIN] * 3 + [NEAR] * 3,
     [FCAL, NEAR, FCAL, "", "", ""]),
]  # fmt: skip


def casa_calls(ms, refant):
    """E1's calibrate and apply stages as CASA task calls, in rang's order
    (core_pipeline.chain_terms, polcal_terms): K without uvrange, uvrange on
    every other solve, CASA's minsnr 3 and minblperant 4."""
    t = "/run/casa"
    common = {"vis": ms, "refant": refant, "minsnr": 3.0, "minblperant": 4}
    mode = {"refantmode": "flex"}
    cc = [f"{t}/K", f"{t}/G", f"{t}/B"]
    calls = [
        {"task": "setjy", "args": {"vis": ms, "field": FCAL,
         "standard": "Stevens-Reynolds 2016", "scalebychan": True, "usescratch": True}},
        {"task": "setjy", "args": {"vis": ms, "field": XCAL, "standard": "manual", **X286,
         "scalebychan": True, "usescratch": True}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/K", "field": FCAL,
         "gaintype": "K", "solint": "inf", "combine": "", "parang": False}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/G", "field": FCAL,
         "gaintype": "G", "calmode": "ap", "solint": "inf", "combine": "", "parang": False,
         "uvrange": UVRANGE, "gaintable": [f"{t}/K"], "interp": [LIN]}},
        {"task": "bandpass", "args": {**common, "caltable": f"{t}/B", "field": FCAL,
         "bandtype": "B", "solint": "inf", "combine": "scan", "solnorm": False,
         "fillgaps": 70, "parang": False, "uvrange": UVRANGE,
         "gaintable": [f"{t}/K", f"{t}/G"], "interp": [LIN, LIN]}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/Gsec", "field": GCAL,
         "gaintype": "G", "calmode": "ap", "solint": "inf", "combine": "", "parang": False,
         "uvrange": UVRANGE, "gaintable": [f"{t}/K", f"{t}/B"], "interp": [LIN, LIN],
         "gainfield": [FCAL, FCAL]}},
        {"task": "copytree", "args": {"src": f"{t}/G", "dst": f"{t}/Gapp"}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/Gapp", "field": GCAL,
         "gaintype": "G", "calmode": "ap", "solint": "inf", "combine": "", "parang": False,
         "uvrange": UVRANGE, "append": True, "smodel": [1.0, 0.0, 0.0, 0.0],
         "gaintable": [f"{t}/K", f"{t}/B"], "interp": [LIN, LIN], "gainfield": [FCAL, FCAL]}},
        {"task": "fluxscale", "args": {"vis": ms, "caltable": f"{t}/Gapp",
         "fluxtable": f"{t}/F", "reference": FCAL, "transfer": ""}},
        {"task": "flagdata", "args": {"vis": ms, "field": XCAL, **EXTEND}},
        {"task": "flagdata", "args": {"vis": ms, "field": FCAL, **EXTEND}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/Gpol", "field": XCAL,
         "gaintype": "G", "calmode": "p", "solint": "60s", "combine": "", "parang": True,
         "uvrange": UVRANGE, "gaintable": cc, "interp": [LIN] * 3}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/Kcross", "field": XCAL,
         "gaintype": "KCROSS", "solint": "inf", "combine": "", "parang": True,
         "uvrange": UVRANGE, "gaintable": cc + [f"{t}/Gpol"], "interp": [LIN] * 4}},
        {"task": "polcal", "args": {**common, "caltable": f"{t}/Xf", "field": XCAL,
         "poltype": "Xf", "solint": "inf", "combine": "scan", "uvrange": UVRANGE,
         "gaintable": cc + [f"{t}/Gpol", f"{t}/Kcross"], "interp": [LIN] * 4 + [NEAR]}},
        {"task": "polcal", "args": {**common, "caltable": f"{t}/Df.raw", "field": FCAL,
         "poltype": "Df", "solint": "inf", "combine": "scan", "uvrange": UVRANGE,
         "gaintable": cc + [f"{t}/Kcross", f"{t}/Xf"], "interp": [LIN] * 3 + [NEAR] * 2}},
        {"task": "copytree", "args": {"src": f"{t}/Df.raw", "dst": f"{t}/Df"}},
        {"task": "flagdata", "args": {"vis": f"{t}/Df", "mode": "clip",
         "clipminmax": [-0.6, 0.6], "datacolumn": "CPARAM", "flagbackup": False}},
        {"task": "flagmanager", "args": {"vis": ms, "mode": "save",
         "versionname": APPLY_VERSION, "comment": "e1b_casa: flags before applycal"}},
    ]  # fmt: skip
    for field, names, interp, gainfield in APPLY:
        calls.append({"task": "applycal", "args": {
            "vis": ms, "field": field, "gaintable": [f"{t}/{n}" for n in names],
            "interp": interp, "gainfield": gainfield, "calwt": [False] * len(names),
            "parang": True, "applymode": "calflag", "flagbackup": False}})  # fmt: skip
    return calls


def log_line(arm, text):
    with open(Path(arm) / "e1b_casa.log", "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {text}\n")


def ms_in(arm):
    found = sorted((Path(arm) / "ms").glob("*.ms"))
    assert len(found) == 1, found
    return found[0]


# --- prepare (Windows venv) ------------------------------------------------------------


def snapshot(arm):
    code = Path(arm) / ".code"
    if code.exists():
        shutil.rmtree(code)
    code.mkdir(parents=True)

    def git(*a):
        return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True,
                              text=True, check=True).stdout  # fmt: skip

    (code / "commit.txt").write_text(git("rev-parse", "HEAD"), encoding="utf-8")
    (code / "status.txt").write_text(git("status", "--porcelain"), encoding="utf-8")
    (code / "diff.patch").write_text(git("diff", "HEAD"), encoding="utf-8")
    shutil.copytree(HERE, code / "e2-acceptance-scripts",
                    ignore=shutil.ignore_patterns("__pycache__"))  # fmt: skip
    shutil.copy2(ROOT / "examples" / "oracle_pol.py", code / "oracle_pol.py")


def prepare(arm, which, refant, asec=False):
    sys.path.insert(0, str(ROOT / "python"))
    import numpy as np
    from rang import cal_refant, core_ms
    from rang.formats import flagversions

    arm = Path(arm)
    src = M32 if which == "m32" else TWIN
    dst = arm / "ms" / src.name
    if dst.exists():
        raise SystemExit(f"{dst} exists")
    arm.mkdir(parents=True, exist_ok=True)
    log_line(arm, f"START prepare {which} refant={refant}")
    started = time.perf_counter()
    record = {"which": which, "source": str(src)}
    if refant == "auto":
        choice = cal_refant.caracal_refant(src)
        refant = ",".join(choice.names)
        record["refant_auto"] = refant
    record["refant"] = refant
    shutil.copytree(src, dst)
    if which == "m32":
        # E1 4.2: rang's FLAG after its flag stage, saved by calibrate first.
        name = [n for n, _ in flagversions.versions(M32_RANG)
                if n.startswith("rang_calibrate_")]  # fmt: skip
        assert len(name) == 1, name
        with core_ms.open_table(dst) as a, core_ms.open_table(M32_RANG) as b:
            for col in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID"):
                assert np.array_equal(a.getcol(col), b.getcol(col)), col
        record["input_flags"] = f"{M32_RANG} version {name[0]}"
        if asec:
            # Post hoc (labelled): add rang's Asec flags, i.e. its FLAG before
            # apply on SIM-GCAL's rows only, so F solves on rang's cells.
            f, fr = flagversions.load(M32_RANG, name[0])
            apply_name = next(n for n, _ in flagversions.versions(M32_RANG)
                              if n.startswith("rang_apply_"))  # fmt: skip
            fa, fra = flagversions.load(M32_RANG, apply_name)
            with core_ms.open_table(M32_RANG / "FIELD") as t:
                gid = [str(n) for n in t.getcol("NAME")].index(GCAL)
            with core_ms.open_table(dst) as t:
                rows = t.getcol("FIELD_ID") == gid
            f[rows] |= fa[rows]
            fr[rows] |= fra[rows]
            del fa, fra
            flagversions.save(dst, INPUT_VERSION,
                              f"e1b_casa: {name[0]}, SIM-GCAL rows OR {apply_name}",
                              flag=f, flag_row=fr, chunk_rows=20160)  # fmt: skip
            del f, fr
            record["input_flags"] += f", SIM-GCAL rows OR {apply_name} (Asec)"
        else:
            top = flagversions.root(dst)
            top.mkdir()
            shutil.copytree(flagversions.root(M32_RANG) / f"flags.{name[0]}",
                            top / f"flags.{INPUT_VERSION}")  # fmt: skip
            (top / "FLAG_VERSION_LIST").write_text(
                f"{INPUT_VERSION} : e1b_casa: rang's {name[0]} of {M32_RANG}\n",
                encoding="utf-8")  # fmt: skip
        flagversions.restore(dst, INPUT_VERSION, chunk_rows=20160)
    else:
        flagversions.save(dst, INPUT_VERSION, "e1b_casa: input flags (twin: none)",
                          chunk_rows=20160)  # fmt: skip
        record["input_flags"] = "the twin's own (none)"
    with core_ms.open_table(dst) as t:
        f = t.getcol("FLAG")
    v = flagversions.load(dst, INPUT_VERSION)[0]
    assert np.array_equal(f, v)
    record["input_flagged_fraction"] = float(f.mean())
    spec = casa_calls(f"/run/ms/{dst.name}", refant)
    (arm / "casa-spec.json").write_text(json.dumps(spec, indent=1) + "\n")
    snapshot(arm)
    record["seconds"] = time.perf_counter() - started
    (arm / "prepare.json").write_text(json.dumps(record, indent=1) + "\n")
    log_line(arm, f"END prepare rc=0 {record['seconds']:.1f}s refant={refant}")
    print(json.dumps(record, indent=1))


# --- casa, drop (WSL, stdlib only) -----------------------------------------------------


def docker(arm, script, label):
    cmd = ["docker", "run", "--rm", "--network", "none", "--user",
           f"{os.getuid()}:{os.getgid()}", "--tmpfs", "/tmp", "-e", "HOME=/tmp",
           "-e", "OMP_NUM_THREADS=4", "-e", "OPENBLAS_NUM_THREADS=1",
           "-v", f"{Path(arm).resolve()}:/run:rw",
           "-v", f"{(ROOT / 'examples').resolve()}:/ex:ro",
           "-w", "/tmp", IMAGE, "sh", "-c", script]  # fmt: skip
    log_line(arm, f"START {label}: {script}")
    started = time.perf_counter()
    with open(Path(arm) / f"{label}.out", "a", encoding="utf-8") as fh:
        rc = subprocess.run(
            cmd, stdout=fh, stderr=subprocess.STDOUT, check=False
        ).returncode
    wall = time.perf_counter() - started
    log_line(arm, f"END {label} rc={rc} {wall:.1f}s")
    return rc


def casa(arm):
    arm = Path(arm)
    ms = f"/run/ms/{ms_in(arm).name}"
    (arm / "casa").mkdir(exist_ok=True)
    steps = [
        f"{CASA} -I /ex/oracle_pol.py tasks /run/casa-spec.json /run/casa-tasks.json"
    ]
    if "twin" in ms:
        steps.append(f"{CASA} -I /ex/oracle_pol.py export {ms} /run/casa-export.npz "
                     "CORRECTED_DATA FLAG MODEL_DATA")  # fmt: skip
    rc = docker(arm, " && ".join(steps), "casa")
    tasks = json.loads((arm / "casa-tasks.json").read_text())
    errors = [(r["task"], r["error"]) for r in tasks if r["error"]]
    log_line(arm, f"tasks {len(tasks)}, errors {len(errors)}: {errors}")
    return rc or (3 if errors else 0)


DROP = """\
from casatools import table
tb = table()
tb.open('{ms}', nomodify=False)
cols = [c for c in ('DATA', 'MODEL_DATA', 'CORRECTED_DATA', 'WEIGHT_SPECTRUM')
        if c in tb.colnames()]
tb.removecols(cols)
tb.close()
print('removed', cols)
"""


def drop(arm):
    arm = Path(arm)
    ms = f"/run/ms/{ms_in(arm).name}"
    (arm / "drop.py").write_text(DROP.format(ms=ms))
    return docker(arm, f"{CASA} -I /run/drop.py", "drop")


# --- check (Windows venv) --------------------------------------------------------------


def check(arm):
    sys.path.insert(0, str(ROOT / "python"))
    from rang import core_ms
    from rang.formats import flagversions

    arm = Path(arm)
    ms = ms_in(arm)
    tasks = json.loads((arm / "casa-tasks.json").read_text())
    out = {"errors": [(r["task"], r["error"]) for r in tasks if r["error"]],
           "seconds": [(r["task"], r["call"].get("caltable") or r["call"].get("field"),
                        round(r["seconds"], 1)) for r in tasks]}  # fmt: skip
    out["casa_seconds_total"] = sum(r["seconds"] for r in tasks)
    with core_ms.open_table(ms) as t:
        fid = t.getcol("FIELD_ID")
        cols = t.colnames()
    with core_ms.open_table(ms / "FIELD") as t:
        names = [str(n) for n in t.getcol("NAME")]
    out["columns"] = cols
    inp = flagversions.load(ms, INPUT_VERSION)[0].any(-1)
    pre = flagversions.load(ms, APPLY_VERSION)[0].any(-1)
    with core_ms.open_table(ms) as t:
        fin = t.getcol("FLAG").any(-1)
    per = {}
    for i, n in enumerate(names):
        r = fid == i
        per[n] = {"input": float(inp[r].mean()), "before_apply": float(pre[r].mean()),
                  "final": float(fin[r].mean())}  # fmt: skip
    out["flagged_fraction"] = per
    if ms.name.startswith("a1-full-m32"):
        # Wiring check: CASA's FLAG before apply against rang's on the fields
        # whose flags no A step touches (E0: the extension is CASA's).
        name = next(n for n, _ in flagversions.versions(M32_RANG)
                    if n.startswith("rang_apply_"))  # fmt: skip
        rang_pre = flagversions.load(M32_RANG, name)[0]
        cpre = flagversions.load(ms, APPLY_VERSION)[0]
        cmp = {}
        for n in (FCAL, XCAL, TARGET, GCAL):
            r = fid == names.index(n)
            cmp[n] = {"elements_differ": int((rang_pre[r] != cpre[r]).sum()),
                      "rang_only": int((rang_pre[r] & ~cpre[r]).sum()),
                      "casa_only": int((~rang_pre[r] & cpre[r]).sum())}  # fmt: skip
        out["before_apply_vs_rang"] = {"rang_version": name, "fields": cmp}
    (arm / "check.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 1 if out["errors"] else 0


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=("prepare", "casa", "check", "drop"))
    p.add_argument("arm")
    p.add_argument("which", nargs="?", choices=("m32", "twin"))
    p.add_argument("--refant", default=None, help="flex list of names, or auto")
    p.add_argument("--asec-flags", action="store_true",
                   help="m32, post hoc: add rang's Asec flags on SIM-GCAL")  # fmt: skip
    a = p.parse_args(argv)
    if a.cmd == "prepare":
        if not (a.which and a.refant):
            p.error("prepare needs m32|twin and --refant")
        prepare(a.arm, a.which, a.refant, a.asec_flags)
        return 0
    if a.cmd == "casa":
        return casa(a.arm)
    if a.cmd == "drop":
        return drop(a.arm)
    return check(a.arm)


if __name__ == "__main__":
    sys.exit(main())
