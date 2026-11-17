"""research/e2a-3b-k.md on nash: the subset, the CASA arms (apptainer), the
rang arms and the simulated-truth cases. Every step is one heavy-lock job
(the caller wraps it, booking the cores it uses).

    python k_run.py build                 src.ms from e3-input/e2a.ms (bound read-only), flags, copies
    python k_run.py rang MS ARM           ARM u | d on O/MS (rang-core run, this checkout)
    python k_run.py casa CASE [TAG]       real: ntk3 ntf tkg tk3m; sim: c ck (TAG the sim case)
    python k_run.py copy SRC DST          copytree inside O
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIAG = ROOT / "research" / "results" / "e2a-3b-diag"
sys.path.insert(0, str(DIAG))

import d1_run  # noqa: E402  (its _calls and rang_config; Windows constants unused)

O = Path.home() / "rang-data" / "outputs" / "e2a-3b-k-20261117"
SRC = Path.home() / "rang-data" / "e3-input"
SIF = Path.home() / "rang-data" / "oracle-images" / "rang-o-casa_6.7.6.14.sif"
WIN = O / "win"
PY = ROOT / ".venv" / "bin" / "python"
THREADS = int(os.environ.get("K_THREADS", "4"))


def log(text):
    with open(O / "k.log", "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {text}\n")


def apptainer(script_args, label, src_ro=False):
    binds = ["--bind", f"{O}:/d1", "--bind", f"{HERE}:/s:ro", "--bind", f"{DIAG}:/s2:ro"]
    if src_ro:
        binds += ["--bind", f"{SRC}:/src:ro"]
    cmd = ["nice", "-n", "19", "ionice", "-c3", "apptainer", "exec", "--containall",
           "--env", "HOME=/tmp", "--env", f"OMP_NUM_THREADS={THREADS}", "--pwd", "/tmp",
           *binds, str(SIF), "/opt/casa/bin/python", "-I", "/s/k_casa.py", *script_args]  # fmt: skip
    log(f"START {label}: {' '.join(cmd)}")
    t0 = time.perf_counter()
    with open(O / f"{label}.out", "w", encoding="utf-8") as fh:
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, check=False).returncode
    dt = time.perf_counter() - t0
    log(f"END {label} rc={rc} {dt:.1f}s")
    return rc


def tasks(label, calls, src_ro=False):
    (O / f"{label}-spec.json").write_text(json.dumps(calls, indent=1) + "\n")
    return apptainer(["tasks", f"/d1/{label}-spec.json", f"/d1/{label}-result.json"], label,
                     src_ro)  # fmt: skip


def build():
    O.mkdir(parents=True, exist_ok=True)
    if (O / "src.ms").exists():
        raise SystemExit("src.ms exists")
    ants = ",".join(map(str, d1_run.ANTS))
    rc = apptainer(["base", "/src/e2a.ms", "/d1/src.ms", "/d1/base.json", ants], "base", True)
    if rc:
        return rc
    mine = json.loads((O / "base.json").read_text())
    theirs = json.loads((WIN / "base.json").read_text())
    same = mine["source_rows"] == theirs["source_rows"]
    log(f"base source_rows equal the diag's: {same}")
    if not same:
        return 4
    calls = [
        {"task": "npzflags", "args": {"vis": "/d1/src.ms", "npz": "/d1/win/flags/src-flags.npz"}},
        {"task": "delmod", "args": {"vis": "/d1/src.ms", "otf": True, "scr": False}},
        {"task": "flaghash", "args": {"vis": "/d1/src.ms"}},
        {"task": "weights_read", "args": {"vis": "/d1/src.ms"}},
    ]  # fmt: skip
    for c in ("rang-u", "rang-d", "casa-a"):
        calls.append({"task": "copytree", "args": {"src": "/d1/src.ms", "dst": f"/d1/{c}.ms"}})
    return tasks("build", calls)


def rang(ms, arm):
    ms = O / ms
    run_dir = Path(str(ms) + ".rang-run")
    if run_dir.exists():
        raise SystemExit(f"{run_dir} exists")
    text = d1_run.rang_config("tt" if arm == "u" else "r0")
    if arm == "d":
        text = text.replace("  average_time: true\n",
                            "  average_time: true\n  bandpass_model_divided: true\n")  # fmt: skip
        assert "bandpass_model_divided: true" in text
    text = text.replace("e2a-3b-diag.md D1 case", "e2a-3b-k.md arm " + arm + ", from D1 case")
    cfg = O / f"{ms.stem}.yaml"
    cfg.write_text(text, encoding="utf-8")
    shutil.copy(DIAG / "pinned" / "mk_rfi_flagging_calibrator_fields_firstpass.yaml", O)
    env = {**os.environ, "PYTHONPATH": "", "RAYON_NUM_THREADS": str(THREADS),
           "OMP_NUM_THREADS": str(THREADS)}  # fmt: skip
    argv = ["nice", "-n", "19", "ionice", "-c3", str(PY), "-m", "rang.core_cli", "run", str(cfg),
            str(ms)]  # fmt: skip
    log(f"START rang {ms.name} {arm}: {argv}")
    t0 = time.perf_counter()
    with open(O / f"{ms.stem}.log", "w", encoding="utf-8") as fh:
        rc = subprocess.run(argv, stdout=fh, stderr=subprocess.STDOUT, check=False,
                            env=env).returncode  # fmt: skip
    dt = time.perf_counter() - t0
    log(f"END rang {ms.name} {arm} rc={rc} {dt:.1f}s")
    (O / f"{ms.stem}-run.json").write_text(json.dumps({"exit": rc, "seconds": dt}) + "\n")
    return rc


def _flags(calls):
    """d1_run's copyflags steps from a packed export where the source is .npz."""
    for c in calls:
        if c["task"] == "copyflags" and c["args"]["src"].endswith(".npz"):
            c["task"] = "npzflags"
            c["args"] = {"vis": c["args"]["vis"], "npz": c["args"]["src"]}
    return calls


def _swap(calls, mapping):
    for c in calls:
        if c["task"] in ("gaincal", "bandpass"):
            c["args"]["gaintable"] = [mapping.get(g, g) for g in c["args"]["gaintable"]]
    return calls


def _model_from(calls, src):
    """setjy writes MODEL_DATA (usescratch) and the rang copy's column replaces it."""
    out = []
    for c in calls:
        if c["task"] == "setjy":
            c["args"]["usescratch"] = True
            out += [c, {"task": "copycol", "args": {"src": src, "vis": c["args"]["vis"],
                                                     "column": "MODEL_DATA"}}]  # fmt: skip
        else:
            out.append(c)
    return out


ALL = ["flags0", "hash0", "setjy", "K0", "G0", "B0", "flags1", "hash1", "K1", "G1", "B1"]


def casa(case, tag=None):
    pre = None
    if case in ("ntk3", "ntf", "tkg", "tk3m"):  # the real subset
        vis = "/d1/casa-a.ms"
        out = f"/d1/casa-{case}"
        f0, f1 = "/d1/win/flags/src-flags.npz", "/d1/win/flags/rang-tt-flags.npz"
        rk = "/d1/win/rang-tt.ms.rang-run/calibrate"
        label = f"casa-{case}"
    else:  # a simulated case
        vis = f"/d1/sim-{tag}-casa.ms"
        out = f"/d1/sim-{tag}-casa-{case}"
        f0, f1 = "/d1/win/flags/src-flags.npz", f"/d1/sim-{tag}-u.ms"
        rk = f"/d1/sim-{tag}-u.ms.rang-run/calibrate"
        label = f"sim-{tag}-casa-{case}"
    if (O / out[4:]).exists():
        raise SystemExit(f"{out} exists")
    (O / out[4:]).mkdir()
    kw = {"usescratch": False, "flags_pass0": f0, "flags_pass1": f1}
    if case == "ntf":
        calls = d1_run._calls(vis, out, **kw)
    elif case in ("ntk3", "tk3m", "ck"):
        terms = [t for t in ALL if t not in ("K0", "K1")]
        calls = d1_run._calls(vis, out, terms=terms, **kw)
        _swap(calls, {f"{out}/K0": f"{rk}/K0", f"{out}/K1": f"{rk}/K1"})
    elif case == "tkg":
        terms = [t for t in ALL if t not in ("K0", "G0", "K1", "G1")]
        calls = d1_run._calls(vis, out, terms=terms, **kw)
        _swap(calls, {f"{out}/{n}": f"{rk}/{n}" for n in ("K0", "G0", "K1", "G1")})
    elif case == "c":
        calls = d1_run._calls(vis, out, **kw)
    else:
        raise SystemExit(f"unknown case {case}")
    if case == "tk3m":
        calls = _model_from(calls, "/d1/rang-u.ms")
    if case in ("c", "ck"):  # the truth model: rang U's column on the same copy
        calls = _model_from(calls, f"/d1/sim-{tag}-u.ms")
    pre = [{"task": "delmod", "args": {"vis": vis, "otf": True, "scr": False}}]
    return tasks(label, pre + _flags(calls))


def copy(src, dst):
    if (O / dst).exists():
        raise SystemExit(f"{dst} exists")
    t0 = time.perf_counter()
    shutil.copytree(O / src, O / dst)
    log(f"copy {src} -> {dst} {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    step, *args = sys.argv[1:]
    fn = {"build": build, "rang": rang, "casa": casa, "copy": copy}.get(step)
    if not fn:
        sys.exit(__doc__)
    sys.exit(fn(*args))
