"""D1 of research/e2a-3b-diag.md: the 15-antenna field-0 subset, rang and
CASA arms. Windows side; every step is one heavy-lock job (the caller wraps
it).

    python d1_run.py build D          subset of e2a.ms (read-only mount), flags, copies
    python d1_run.py rang D CASE      CASE r0 | tt | ti (frozen wheel)
    python d1_run.py casa D CASE      CASE c0 | tf | tk | tw | tm
    python d1_run.py score D          composites and terms -> D/d1-score.json

D is the output directory (D:\\rang\\outputs\\e2a-3b-diag-20261117\\d1).
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = Path(r"D:\rang\outputs\e2a-20261115")
FROZEN_PY = Path(r"C:\Users\gijsm\Build\tmp\20261111-e2-wheel\venv\Scripts\python.exe")
CASA_IMAGE = "rang-o-casa:6.7.6.14"
ANTS = [0, 5, 10, 15, 20, 21, 22, 25, 30, 35, 40, 45, 50, 55, 60]
FCAL = "J1939-6342"
REFANT = "m022,m023,m024"
LIN = "linear"
FLAG_STAGE = "flags.rang_calibrate_20261115T132707Z"
PINNED = HERE / "pinned"  # e2a-rerun.yaml and the strategy at 51291b7


def wsl(path):
    p = str(Path(path).resolve()).replace("\\", "/")
    return "/mnt/" + p[0].lower() + p[2:]


def log(d, text):
    with open(Path(d) / "d1.log", "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {text}\n")


def docker(d, script, label, threads=4, src_ro=False):
    vols = ["-v", f"'{wsl(d)}:/d1:rw'", "-v", f"'{wsl(HERE)}:/s:ro'"]
    if src_ro:
        vols += ["-v", f"'{wsl(SRC)}:/src:ro'"]
    inner = " ".join(
        ["docker", "run", "--rm", "--network", "none", "--user", "$(id -u):$(id -g)",
         "--tmpfs", "/tmp", "-e", "HOME=/tmp", "-e", f"OMP_NUM_THREADS={threads}",
         *vols, "-w", "/tmp", CASA_IMAGE, "sh", "-c", f"'{script}'"]
    )  # fmt: skip
    log(d, f"START {label}: {inner}")
    t0 = time.perf_counter()
    with open(Path(d) / f"{label}.out", "w", encoding="utf-8") as fh:
        rc = subprocess.run(["wsl", "-e", "bash", "-lc", inner], stdout=fh,
                            stderr=subprocess.STDOUT, check=False).returncode  # fmt: skip
    dt = time.perf_counter() - t0
    log(d, f"END {label} rc={rc} {dt:.1f}s")
    return rc, dt


def tasks(d, label, calls, threads=4, src_ro=False):
    (Path(d) / f"{label}-spec.json").write_text(json.dumps(calls, indent=1) + "\n")
    rc, dt = docker(d, f"/opt/casa/bin/python -I /s/d1_casa.py tasks /d1/{label}-spec.json "
                    f"/d1/{label}-result.json", label, threads, src_ro)  # fmt: skip
    return rc


RANG_CASES = ("r0", "tt", "ti")  # ts, tts: copied from src.ms after D1 (post hoc)
CASA_COPIES = {"c0": "casa-a", "tf": "casa-a", "tk": "casa-a", "tk2": "casa-a", "tw": "casa-w", "tm": "casa-m"}


def build(d):
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    if (d / "src.ms").exists():
        raise SystemExit("src.ms exists")
    ants = ",".join(map(str, ANTS))
    rc, dt = docker(d, f"/opt/casa/bin/python -I /s/d1_casa.py base /src/e2a.ms /d1/src.ms "
                    f"/d1/base.json {ants}", "base", 4, src_ro=True)  # fmt: skip
    if rc:
        return rc
    calls = [
        {"task": "putflags", "args": {"vis": "/d1/src.ms", "rows": "/d1/base.json",
         "version": f"/src/e2a.ms.flagversions/{FLAG_STAGE}"}},
        {"task": "delmod", "args": {"vis": "/d1/src.ms", "otf": True, "scr": False}},
        {"task": "flaghash", "args": {"vis": "/d1/src.ms"}},
        {"task": "weights_read", "args": {"vis": "/d1/src.ms"}},
    ]  # fmt: skip
    for c in RANG_CASES:
        calls.append({"task": "copytree", "args": {"src": "/d1/src.ms", "dst": f"/d1/rang-{c}.ms"}})
    for c in sorted(set(CASA_COPIES.values())):
        calls.append({"task": "copytree", "args": {"src": "/d1/src.ms", "dst": f"/d1/{c}.ms"}})
    return tasks(d, "build", calls, 4, src_ro=True)


def rang_config(case):
    text = (PINNED / "e2a-rerun.yaml").read_text(encoding="utf-8")
    text = text.replace("  scans: [9, 10, 11]\n", "  scans: [9, 11]\n")
    text = text.replace("  refant: auto\n", "  refant: [m022, m023, m024]\n")
    text = text.replace("  stages: [flag, calibrate, apply, image, selfcal]", "  stages: [calibrate]")
    if case in ("tt", "tts"):
        text = text.replace("  average_time: true\n  primary:", "  average_time: false\n  primary:")
        # unaveraged, one K0 interval needs 9.8 GiB (refused at the default 8)
        text = text.replace("  weights: uniform\n", "  weights: uniform\n  memory_limit_gb: 16\n")
    head = f"# research/e2a-3b-diag.md D1 case {case}: e2a-rerun.yaml (51291b7), calibrate only, subset scans and refants.\n"
    return head + text


def rang(d, case):
    d = Path(d)
    ms = d / f"rang-{case}.ms"
    run_dir = Path(str(ms) + ".rang-run")
    if run_dir.exists():
        raise SystemExit(f"{run_dir} exists")
    cfg = d / f"rang-{case}.yaml"
    cfg.write_text(rang_config(case), encoding="utf-8")
    shutil.copy(PINNED / "mk_rfi_flagging_calibrator_fields_firstpass.yaml", d)
    if case == "ti":
        argv = [str(FROZEN_PY), str(HERE / "d1_rang_iter.py"), "200", "run", str(cfg), str(ms)]
    elif case in ("ts", "tts"):  # post hoc T-S (section 6): a strict stop rule
        argv = [str(FROZEN_PY), str(HERE / "d1_rang_iter.py"), "1000:1e-12:1.0", "run", str(cfg),
                str(ms)]  # fmt: skip
    else:
        argv = [str(FROZEN_PY), "-m", "rang.core_cli", "run", str(cfg), str(ms)]
    t0 = time.perf_counter()
    log(d, f"START rang-{case}: {argv}")
    with open(d / f"rang-{case}.log", "w", encoding="utf-8") as fh:
        rc = subprocess.run(argv, stdout=fh, stderr=subprocess.STDOUT, check=False,
                            env={**__import__("os").environ, "PYTHONPATH": ""}).returncode  # fmt: skip
    dt = time.perf_counter() - t0
    log(d, f"END rang-{case} rc={rc} {dt:.1f}s")
    (d / f"rang-{case}-run.json").write_text(json.dumps({"exit": rc, "seconds": dt}) + "\n")
    return rc


def _calls(vis, out, *, usescratch, flags_pass0, flags_pass1, k1=None, terms=None):
    """`e2_casa3b_a.casa_calls` (51291b7) for `vis`, tables in `out`, with a
    FLAG copy before setjy (`flags_pass0`) and before K1 (`flags_pass1`).
    `k1`: a K1 table path pre-applied in G1 and B1 instead of out/K1 (T-K)."""
    common = {"vis": vis, "field": FCAL, "refant": REFANT, "minsnr": 3.0, "minblperant": 4,
              "parang": False}  # fmt: skip
    flex = {"refantmode": "flex"}
    t = out

    def path(p):
        return k1 if (p == "K1" and k1) else f"{t}/{p}"

    def gk(name, solint, pre):
        return {"task": "gaincal", "args": {**common, **flex, "caltable": f"{t}/{name}",
                "gaintype": "K", "solint": solint, "combine": "",
                "gaintable": [path(p) for p in pre], "interp": [LIN] * len(pre)}}  # fmt: skip

    def gg(name, solint, pre):
        return {"task": "gaincal", "args": {**common, **flex, "caltable": f"{t}/{name}",
                "gaintype": "G", "calmode": "ap", "solint": solint, "combine": "",
                "uvrange": ">150", "gaintable": [path(p) for p in pre],
                "interp": [LIN] * len(pre)}}  # fmt: skip

    def bb(name, pre):
        return {"task": "bandpass", "args": {**common, "caltable": f"{t}/{name}",
                "bandtype": "B", "solint": "inf", "combine": "scan", "solnorm": False,
                "fillgaps": 70, "uvrange": ">150", "gaintable": [path(p) for p in pre],
                "interp": [LIN] * len(pre)}}  # fmt: skip

    setjy = {"task": "setjy", "args": {"vis": vis, "field": FCAL,
             "standard": "Stevens-Reynolds 2016", "scalebychan": True, "usescratch": usescratch}}  # fmt: skip
    calls = {
        "flags0": {"task": "copyflags", "args": {"src": flags_pass0, "vis": vis}},
        "hash0": {"task": "flaghash", "args": {"vis": vis}},
        "setjy": setjy,
        "K0": gk("K0", "inf", []), "G0": gg("G0", "inf", ["K0"]), "B0": bb("B0", ["K0", "G0"]),
        "flags1": {"task": "copyflags", "args": {"src": flags_pass1, "vis": vis}},
        "hash1": {"task": "flaghash", "args": {"vis": vis}},
        "K1": gk("K1", "60s", ["G0", "B0"]), "G1": gg("G1", "60s", ["K1", "B0"]),
        "B1": bb("B1", ["K1", "G1"]),
    }  # fmt: skip
    order = terms or ["flags0", "hash0", "setjy", "K0", "G0", "B0", "flags1", "hash1", "K1", "G1", "B1"]
    return [calls[k] for k in order]


def casa(d, case):
    d = Path(d)
    vis = f"/d1/{CASA_COPIES[case]}.ms"
    out = f"/d1/casa-{case}"
    if (d / f"casa-{case}").exists():
        raise SystemExit(f"casa-{case} exists")
    (d / f"casa-{case}").mkdir()
    after = "/d1/rang-r0.ms"  # FLAG after rang's calibrate (A0 on the subset)
    stage = "/d1/src.ms"  # the flag stage's FLAG
    pre = [{"task": "delmod", "args": {"vis": vis, "otf": True, "scr": False}}]
    if case == "c0":  # as frozen: every call on the after-calibrate FLAG
        calls = _calls(vis, out, usescratch=False, flags_pass0=after, flags_pass1=after)
    elif case == "tf":
        calls = _calls(vis, out, usescratch=False, flags_pass0=stage, flags_pass1=after)
    elif case == "tw":
        pre.append({"task": "weights_ones", "args": {"vis": vis}})
        calls = _calls(vis, out, usescratch=False, flags_pass0=stage, flags_pass1=after)
    elif case == "tm":
        calls = _calls(vis, out, usescratch=True, flags_pass0=stage, flags_pass1=after)
    elif case == "tk":  # T-F's B0 and rang's K1 pre-applied; G1, B1 only
        calls = _calls(vis, out, usescratch=False, flags_pass0=stage, flags_pass1=after,
                       k1="/d1/rang-r0.ms.rang-run/calibrate/K1",
                       terms=["flags1", "hash1", "G1", "B1"])  # fmt: skip
        for c in calls:
            if c["task"] in ("gaincal", "bandpass"):
                c["args"]["gaintable"] = [g.replace(f"{out}/B0", "/d1/casa-tf/B0")
                                          for g in c["args"]["gaintable"]]  # fmt: skip
        pre = []
    elif case == "tk2":  # post hoc: rang's K0 and K1 (T-T, unaveraged) in every CASA pre-apply
        rk = "/d1/rang-tt.ms.rang-run/calibrate"
        calls = _calls(vis, out, usescratch=False, flags_pass0=stage, flags_pass1=after,
                       terms=["flags0", "hash0", "G0", "B0", "flags1", "hash1", "G1", "B1"])  # fmt: skip
        for c in calls:
            if c["task"] in ("gaincal", "bandpass"):
                c["args"]["gaintable"] = [g.replace(f"{out}/K0", f"{rk}/K0").replace(f"{out}/K1", f"{rk}/K1")
                                          for g in c["args"]["gaintable"]]  # fmt: skip
        pre = []  # casa-a keeps T-F's virtual model
    else:
        raise SystemExit(f"unknown case {case}")
    return tasks(d, f"casa-{case}", pre + calls, 4)


if __name__ == "__main__":
    step = sys.argv[1]
    if step == "build":
        sys.exit(build(sys.argv[2]))
    if step == "rang":
        sys.exit(rang(sys.argv[2], sys.argv[3]))
    if step == "casa":
        sys.exit(casa(sys.argv[2], sys.argv[3]))
    if step == "score":
        import d1_score

        sys.exit(d1_score.main(sys.argv[2]))
    sys.exit(__doc__)
