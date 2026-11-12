"""v5_run.py: the runs of research/v5-obit.md, driven from Windows (after G7's g7_run.py).

    v5_run.py one ARM DS J REP [TAG]   one run (call under tools/heavy_lock.py): probe, run, probe
    v5_run.py plan NAME                every run of plan NAME, each under the heavy lock;
                                       runs whose timing.json exists are skipped (resume)
    v5_run.py convert DS               MS -> Obit UV table file (ms_to_obit.py in rang-obit)
    v5_run.py inp DS J                 print the MFImage input file
    v5_run.py probe                    print the load probe once

Arms: G = GeMClean (native, $V5_GBIN), W = WSClean 3.7 (rang-wsclean-native:3.7),
O = Obit MFImage (rang-obit:dc26694), both in Docker in WSL. DS: S1 or P (pilot-512).
TAG (optional) names a non-timed plumbing run (e.g. niter0) and changes only the name.
Outputs under $V5_OUT (default D:/rang/outputs/v5-20261111-01): runs/<ARM>-<DS>-j<J>-r<REP>/.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "g7-defaults-scripts"))
from g7_run import now, probe, sha, time_v, win_stats, wsl_path  # noqa: E402

OUT = Path(os.environ.get("V5_OUT", "D:/rang/outputs/v5-20261111-01"))
GBIN = os.environ.get("V5_GBIN", "D:/rang/outputs/g8-20261110-01/bin/gemclean-sb-ed836ec.exe")
OBIT_IMG = os.environ.get("V5_OBIT_IMG", "rang-obit:dc26694")
WSC_IMG = "rang-wsclean-native:3.7"
WSCTMP = "/home/gijsm/Build/tmp/20261111-v5-wsctmp"
OBIT_STAGE = "/home/gijsm/Build/tmp/20261111-v5-obit"
W = HERE.parents[2]
PY = str(W / ".venv" / "Scripts" / "python.exe")
# The main checkout's lock queues first come, first served (main bd15126); branch copies poll.
LOCK = os.environ.get("RANG_HEAVY_LOCK", "C:/Users/gijsm/Github/rang/tools/heavy_lock.py")
if not Path(PY).exists():
    PY = r"C:\Users\gijsm\Github\rang\.venv\Scripts\python.exe"
STATUS = Path(r"C:\Users\gijsm\Github\rang\outputs\status\v5-obit.md")

DS = {
    "S1": {
        "ms_dir": "D:/rang/outputs/20261102-gemclean/bench/data", "ms": "s1.ms",
        "size": 2048, "scale": 1.5, "thr": 0.0001, "maxfbw": float(os.environ.get("V5_FBW_S1", "0.0195")),
    },
    "P": {
        "ms_dir": "D:/rang/outputs/20261103-gemclean-heldout/real", "ms": "cal.ms",
        # maxFBW x 989.75 MHz / 208.98 kHz = 64.03 channels per bin: 8 planes of 64 channels
        # (ObitImageMF.c:904-931; 0.0128 gave 9 planes, the last one of 28 channels)
        "size": 4096, "scale": 3.0, "thr": 0.003, "maxfbw": float(os.environ.get("V5_FBW_P", "0.013521")),
    },
}  # fmt: skip
UVDIR = OUT / "uv"
NCHAN_OUT = 8


def common(ds, j):
    d = DS[ds]
    return [
        "-size", str(d["size"]), str(d["size"]), "-scale", f"{d['scale']}asec",
        "-weight", "briggs", "0.5", "-niter", "1000000", "-gain", "0.1", "-nmiter", "1000",
        "-abs-threshold", str(d["thr"]), "-data-column", "DATA", "-field", "0",
        "-channels-out", str(NCHAN_OUT), "-join-channels", "-fit-spectral-pol", "2",
        "-j", str(j),
    ]  # fmt: skip


def source_name(ds):
    # the converter's JSON is followed by Obit's own log lines on the same stdout
    meta = json.JSONDecoder().raw_decode((UVDIR / f"{ds}.json").read_text())[0]
    return meta["source"]


def tdf_defaults():
    """Every input of MFImage.TDF (dc26694) with its default, as ObitTalk fills them.

    MFImage run with -input knows only the keys in the file: a missing array key can be
    dereferenced as NULL (BeamOne reads "nx" with ObitInfoListGetP: SIGSEGV). Numbers and
    booleans default to **DEF** or 0 / F; strings are written only with a **DEF** value.
    """
    lines = (HERE / "MFImage.TDF").read_text(encoding="utf-8").splitlines()
    end = next(i for i, ln in enumerate(lines) if ln.startswith("-----"))
    typ_map = {"int": "Int", "float": "Flt", "boo": "Boo", "str": "Str"}
    out = []
    for i, ln in enumerate(lines[:end]):
        if not ln.startswith("**PARAM**"):
            continue
        head = ln.split("**DEF**")
        f = head[0].split()
        typ, dims = typ_map[f[1]], [int(x) for x in f[2:]]
        dflt = head[1].strip() if len(head) > 1 else None
        nf = lines[i + 1].split()
        name = nf[0]
        if len(nf) > 1 and nf[1] == "$":  # output parameter
            continue
        if typ == "Str":
            if dflt is None:
                continue
            out.append((name, typ, [dflt]))
            continue
        n = 1
        for x in dims:
            n *= x
        if typ == "Boo":
            v = dflt if dflt in ("T", "F") else "F"
        elif typ == "Int":
            v = str(int(float(dflt))) if dflt else "0"
        else:
            v = repr(float(dflt)) if dflt else "0.0"
        out.append((name, typ, [v] * n))
    return out


def inp(ds, j, niter=1000000):
    """MFImage input file, settings matched as in research/v5-obit.md section 3."""
    d = DS[ds]
    fov = d["size"] * d["scale"] / 2.0 / 3600.0  # inscribed circle of the square field
    keys = [
        ("DataType", "Str", ["FITS"]), ("inFile", "Str", [f"{ds}.uvtab"]), ("inDisk", "Int", [2]),
        ("Sources", "Str", [source_name(ds)]), ("Stokes", "Str", ["I"]),
        ("BChan", "Int", [0]), ("EChan", "Int", [0]), ("BIF", "Int", [0]), ("EIF", "Int", [0]),
        ("doCalib", "Int", [-1]), ("doBand", "Int", [-1]), ("flagVer", "Int", [-1]),
        ("doPol", "Boo", ["F"]), ("norder", "Int", [1]), ("Alpha", "Flt", [0.0]),
        ("BLFact", "Flt", [1.0]),
        ("outDType", "Str", ["FITS"]), ("outFile", "Str", [".fits"]), ("outDisk", "Int", [1]),
        ("out2File", "Str", [".uvtab"]), ("out2Disk", "Int", [1]),
        ("maxFBW", "Flt", [d["maxfbw"]]), ("FOV", "Flt", [fov]), ("NField", "Int", [0]),
        ("xCells", "Flt", [d["scale"]]), ("yCells", "Flt", [d["scale"]]),
        ("UVTaper", "Flt", [0.0, 0.0, 0.0]), ("MFTaper", "Flt", [-1.0]), ("UVRange", "Flt", [0.0, 0.0]),
        ("Robust", "Flt", [0.5]), ("WtBox", "Int", [0]), ("WtFunc", "Int", [1]),
        ("doComRes", "Boo", ["F"]), ("doFull", "Boo", ["T"]), ("doRestore", "Boo", ["T"]),
        ("doFit", "Boo", ["T"]), ("do3D", "Boo", ["F"]), ("Catalog", "Str", ["None"]),
        ("OutlierDist", "Flt", [0.0]), ("autoWindow", "Boo", ["F"]), ("Gain", "Flt", [0.1]),
        ("minFlux", "Flt", [d["thr"]]), ("Niter", "Int", [niter]), ("ccfLim", "Flt", [0.2]),
        ("SDIGain", "Flt", [0.0]), ("Beam", "Flt", [0.0, 0.0, 0.0]), ("autoCen", "Flt", [1.0e20]),
        # targBeam > 0 skips BeamOne, an extra image of the first IF (MFImage.c:3092). The
        # target beam is read only when MFTaper > 0 (ObitUVGridMF.c:412-418), so with
        # MFTaper -1 its value does not change the images; V5_OBIT_TARGBEAM=0 restores BeamOne.
        ("targBeam", "Flt", [0.0, 0.0, 0.0] if os.environ.get("V5_OBIT_TARGBEAM") == "0" else [1.0, 1.0, 0.0]),
        ("Cmethod", "Str", ["DFT"]), ("PBCor", "Boo", ["F"]), ("CCFilter", "Flt", [0.0, 0.0]),
        ("maxPSCLoop", "Int", [0]), ("maxASCLoop", "Int", [0]), ("PeelFlux", "Flt", [1.0e20]),
        ("nTaper", "Int", [0]), ("doQU", "Boo", ["F"]), ("prtLv", "Int", [1]),
        ("dispURL", "Str", ["None"]), ("nThreads", "Int", [int(j)]),
        ("doGPU", "Boo", ["F"]), ("doGPUGrid", "Boo", ["F"]), ("taskLog", "Str", ["/run/mfimage.log"]),
        ("nFITS", "Int", [2]), ("FITSdirs", "Str", ["/run/", "/uv/"]),
        ("nAIPS", "Int", [0]), ("AIPSuser", "Int", [100]),
    ]  # fmt: skip
    out = [f"# MFImage input, research/v5-obit.md, {ds} -j{j}"]
    mine = {k[0] for k in keys}
    keys = [k for k in tdf_defaults() if k[0] not in mine] + keys
    for name, typ, vals in keys:
        if typ == "Str":
            width = max(len(v) for v in vals)
            dim = f"({width},{len(vals)})" if len(vals) > 1 or name == "Sources" else f"({width})"
            out.append(f"$Key = {name} Str {dim}")
            out += [str(v) for v in vals]
        else:
            out.append(f"$Key = {name} {typ} ({len(vals)})")
            out.append(" ".join(str(v) for v in vals))
    return "\n".join(out) + "\n"


def docker(args, mounts, workdir="/run"):
    m = []
    for host, cont, mode in mounts:
        m += ["-v", f"{wsl_path(host)}:{cont}{':ro' if mode == 'ro' else ''}"]
    return ["docker", "run", "--rm", "--user", "$(id -u):$(id -g)", "--network", "none",
            "-e", "HOME=/tmp", *m, "-w", workdir, *args]  # fmt: skip


def wsl(script, log):
    with open(log, "w") as f:
        return subprocess.call(["wsl", "-e", "bash", "-c", script], stdout=f, stderr=subprocess.STDOUT)


def convert(ds):
    UVDIR.mkdir(parents=True, exist_ok=True)
    d = DS[ds]
    tmpl = "/src/Obit/ObitSystem/Obit/share/data/MKATTemplate.uvtab.gz"
    args = docker(
        [OBIT_IMG, "/usr/bin/time", "-v", "-o", f"/uv/{ds}-convert-time.txt", "python3",
         "/code/ms_to_obit.py", f"/data/{d['ms']}", "0", f"/uv/{ds}.uvtab", tmpl],
        [(d["ms_dir"], "/data", "ro"), (UVDIR, "/uv", "rw"), (HERE, "/code", "ro")], "/uv")  # fmt: skip
    script = " ".join(args) + f" > {wsl_path(UVDIR)}/{ds}.json"
    t = time.perf_counter()
    rc = wsl(script, UVDIR / f"{ds}-convert.log")
    print(f"convert {ds} rc={rc} {time.perf_counter() - t:.0f}s")
    return rc


def one(arm, ds, j, rep, tag=""):
    j, rep = int(j), int(rep)
    name = f"{arm}-{ds}-j{j}-r{rep}" + (f"-{tag}" if tag else "")
    d = OUT / "runs" / name
    d.mkdir(parents=True, exist_ok=True)
    timed = not tag
    waited, busy = 0, []
    lines = []
    for k in range(11 if timed else 1):
        lines, busy = probe()
        if not busy or k == 10 or not timed:
            break
        time.sleep(60)
        waited += 60
    (d / "load-before.txt").write_text("\n".join(lines) + "\n")
    spoiled = bool(busy) and timed
    D = DS[ds]
    stats = {}
    if arm == "G":
        extra = ["-niter", "0"] if tag == "niter0" else []
        cmd = [GBIN, "-name", str(d / "g"), *common(ds, j), *extra, "-no-update-model-required",
               f"{D['ms_dir']}/{D['ms']}"]  # fmt: skip
        (d / "cmd.txt").write_text(" ".join(cmd) + "\n")
        t = time.perf_counter()
        with open(d / "log.txt", "w") as log:
            p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            rc = p.wait()
            wall = time.perf_counter() - t
            stats = win_stats(int(p._handle))
        stats["wall_s"] = wall
    elif arm == "W":
        par = ["-parallel-reordering", "1"] if j == 1 else []
        extra = ["-niter", "0"] if tag == "niter0" else []
        args = docker(
            ["-e", f"OMP_NUM_THREADS={j}", WSC_IMG, "/usr/bin/time", "-v", "-o", "/run/time.txt",
             "wsclean", "-gridder", "wgridder", "-pol", "I", "-no-update-model-required",
             "-temp-dir", "/run/tmp", *common(ds, j), *extra, "-mgain", "0.8", *par,
             "-name", "/run/w", f"/data/{D['ms']}"],
            [(D["ms_dir"], "/data", "ro"), (d, "/run", "rw"), (WSCTMP, "/run/tmp", "rw")])  # fmt: skip
        script = (f"mkdir -p {WSCTMP} && rm -rf {WSCTMP}/* && " + " ".join(args)
                  + f"; rc=$?; rm -rf {WSCTMP}/*; exit $rc")
        (d / "cmd.txt").write_text(script + "\n")
        t = time.perf_counter()
        rc = wsl(script, d / "log.txt")
        stats = time_v(d / "time.txt") if (d / "time.txt").exists() else {}
        stats["outer_wall_s"] = time.perf_counter() - t
    elif arm == "O":
        (d / "mfimage.inp").write_bytes(inp(ds, j, niter=0 if tag.startswith("niter0") else 1000000).encode())  # LF: Obit reads CR into values
        cap = os.environ.get("V5_OBIT_CAP_S", "28800")  # 8 h hard cap (protocol section 5)
        # MFImage reads its uvtab many times and writes scratch copies next to its output;
        # on /mnt/d (drvfs) it is I/O bound (pilot Niter 0: 7,982 s CPU in 14,143 s wall at
        # -j8). Unless V5_OBIT_STAGE=0, the uvtab and the run directory are staged on the WSL
        # ext4 disk (as WSClean's -temp-dir), copied in and out outside the timed command;
        # every run then starts from the same bytes of the D: copy, which is never opened.
        stage = os.environ.get("V5_OBIT_STAGE", "1") != "0"
        S = f"{OBIT_STAGE}/{name}"
        uvh, runh = (f"{S}/uv", f"{S}/run") if stage else (UVDIR, d)
        args = docker(
            [OBIT_IMG, "timeout", cap, "/usr/bin/time", "-v", "-o", "/run/time.txt",
             "MFImage", "-input", "/run/mfimage.inp", "-output", "/run/mfimage.out", "-pgmNumber", "1"],
            [(uvh, "/uv", "rw"), (runh, "/run", "rw")])  # fmt: skip
        # MFImage opens its input read-write (ObitUVUtilWhichSources), so /uv is mounted rw;
        # the input's size and mtime before and after show whether it was changed.
        st = f"stat -c '%s %Y %n' {wsl_path(uvh)}/{ds}.uvtab"
        pre = post = ""
        if stage:
            pre = (f"rm -rf {S} && mkdir -p {S}/uv {S}/run && cp {wsl_path(UVDIR)}/{ds}.uvtab {S}/uv/"
                   f" && cp {wsl_path(d)}/mfimage.inp {S}/run/ && sync && ")  # fmt: skip
            post = (f"rm -f {S}/run/*.uvtab; cp {S}/run/* {wsl_path(d)}/; "
                    f"sha256sum {wsl_path(UVDIR)}/{ds}.uvtab {S}/uv/{ds}.uvtab > {wsl_path(d)}/input-sha.txt; "
                    f"rm -rf {S}; ")  # fmt: skip
        script = (pre + f"{st} > {wsl_path(d)}/input-stat-before.txt; " + " ".join(args)
                  + f"; rc=$?; {st} > {wsl_path(d)}/input-stat-after.txt; {post}"
                  + f"rm -f {wsl_path(d)}/*.uvtab; exit $rc")
        (d / "cmd.txt").write_text(script + "\n")
        t = time.perf_counter()
        rc = wsl(script, d / "log.txt")
        stats = time_v(d / "time.txt") if (d / "time.txt").exists() else {}
        stats["outer_wall_s"] = time.perf_counter() - t
    else:
        raise SystemExit(f"unknown arm {arm}")
    lines, busy_after = probe()
    (d / "load-after.txt").write_text("\n".join(lines) + "\n")
    hashes = {f.name: sha(f) for f in sorted(d.glob("*.fits"))}
    rec = {"run": name, "arm": arm, "ds": ds, "j": j, "rep": rep, "tag": tag, "rc": rc,
           "spoiled": spoiled, "waited_s": waited, "busy_before": busy, "busy_after": busy_after,
           "end": now(), **stats, "sha256": hashes}  # fmt: skip
    (d / "timing.json").write_text(json.dumps(rec, indent=1) + "\n")
    with open(OUT / "runs.tsv", "a") as f:
        f.write(f"{name}\t{rc}\t{int(spoiled)}\t{stats.get('wall_s', float('nan')):.1f}\t{now()}\n")
    if rep > 1:  # later repeats keep hashes only
        for f in d.glob("*.fits"):
            f.unlink()
    print(f"{name} rc={rc} wall={stats.get('wall_s', float('nan')):.1f}s spoiled={spoiled}")
    return rc


ORDER = ["G", "W", "O"]
PLANS = {
    # section 5: S1 then the pilot; -j16 two repeats interleaved (reversed on repeat 2), then -j1 once.
    "s1": [(a, "S1", 16, r) for r in (1, 2) for a in (ORDER if r == 1 else ORDER[::-1])]
    + [(a, "S1", 1, 1) for a in ORDER],
    "p16": [(a, "P", 16, r) for r in (1, 2) for a in (ORDER if r == 1 else ORDER[::-1])],
    "p1": [(a, "P", 1, 1) for a in ORDER],
}


def status(line):
    try:
        old = STATUS.read_text(encoding="utf-8").splitlines() if STATUS.exists() else []
        head = [ln for ln in old if not ln.startswith("- ")][:1] or ["# V5 Obit oracle — status"]
        items = [ln for ln in old if ln.startswith("- ")]
        items = (items + [f"- {now()} {line}"])[-13:]
        STATUS.write_text("\n".join(head + items) + "\n", encoding="utf-8")
    except OSError:
        pass


def plan(name):
    log = OUT / f"plan-{name}.log"
    with open(log, "a") as f:
        f.write(f"START {now()} pid {os.getpid()} plan {name}\n")
    status(f"plan {name} START")
    for arm, ds, j, rep in PLANS[name]:
        run = f"{arm}-{ds}-j{j}-r{rep}"
        if (OUT / "runs" / run / "timing.json").exists():
            continue
        if arm == "O" and ds == "P" and (j == 1 or rep == 2):
            # section 5 contingency: MFImage's first pilot run at -j16 over 4 h (or capped)
            # means no second -j16 repeat and no -j1 run for it.
            first = OUT / "runs" / "O-P-j16-r1" / "timing.json"
            r1 = json.loads(first.read_text()) if first.exists() else {}
            if os.environ.get("V5_SKIP_OP1") or r1.get("rc", 0) != 0 or r1.get("wall_s", 0) > 4 * 3600:
                status(f"plan: {run} skipped under the contingency of section 5")
                continue
        t = time.time()
        rc = subprocess.call([PY, LOCK, "run", "--", PY, __file__,
                              "one", arm, ds, str(j), str(rep)])  # fmt: skip
        with open(log, "a") as f:
            f.write(f"RUN {run} rc={rc} wall={time.time() - t:.0f}s {now()}\n")
        status(f"plan {name} RUN {run} rc={rc} wall={time.time() - t:.0f}s")
        if rc == 124 and arm == "O":  # timeout: reported as not finished, the plan goes on
            status(f"plan {name} {run} hit the MFImage cap (timeout rc 124)")
            continue
        if rc != 0:
            status(f"plan {name} STOPPED at {run} rc={rc}")
            sys.exit(rc)
    with open(log, "a") as f:
        f.write(f"END {now()}\n")
    status(f"plan {name} END")


def main():
    mode = sys.argv[1]
    if mode == "one":
        sys.exit(one(*sys.argv[2:7]))
    elif mode == "plan":
        plan(sys.argv[2])
    elif mode == "convert":
        sys.exit(convert(sys.argv[2]))
    elif mode == "inp":
        print(inp(sys.argv[2], sys.argv[3]))
    elif mode == "probe":
        lines, busy = probe()
        print("\n".join(lines))
        print("BUSY:", busy)


if __name__ == "__main__":
    main()
