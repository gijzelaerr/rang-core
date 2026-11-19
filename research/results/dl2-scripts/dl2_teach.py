"""DL2 teacher runner, teachers x one block (research/dl2-data.md section 6).

    python dl2_teach.py ROOT TEACHERS CBID [--scans S ...] [--threads T]
    TEACHERS: a comma list of rang, tricolour, aoflagger (run in that order)

Per scan of ROOT/manifests/<cbid>.json (converted scans only); a teacher's
shard is skipped when done/<teacher>/<cbid>/<scan>.done exists:
1. one private full copy of the frozen MS per scan, work/copies/<cbid>/
   scan<NNN>.ms (ext4 on nash has no reflink, and the teachers open the MS
   read-write, so hard links to the read-only original fail), marked
   complete by a `.copied` file beside it and shared by the teachers in turn;
2. before each teacher every file except the DATA, WEIGHT_SPECTRUM and
   SIGMA_SPECTRUM storage-manager files is restored from the frozen MS, so
   each teacher starts from the native flags; those bulk files are checked
   unchanged after it (size and mtime of the _TSM data files, SHA-256 of
   their headers);
3. the teacher writes FLAG in the copy:
   - rang: `rang-core flag` (the Tricolour port) with `data.executor: spool`,
     T workers started here (`python -m rang.core_spool worker`);
   - tricolour: Tricolour 0.2.1 in rang-tricolour_0.2.1-e1.sif, E2's argv;
   - aoflagger: stimela_aoflagger_1.2.0.sif with CARACal's firstpass_QUV.rfis;
4. labels/<teacher>/<cbid>/scan<NNN>/: flag.npy (FLAG bit-packed per row,
   uint8, shape (rows, ceil(chan*corr/8)), MS row order, C order of
   (chan, corr)), flag_row.npy, label.json (teacher, pins, strategy and its
   SHA-256, wall, peak RSS, input MS hash, shapes) and SHA256SUMS.
The copy is deleted when every listed teacher is done for the scan. The
frozen MS is never opened for writing. Refuses held-out blocks unless
--heldout-read is given (section 5).
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

BIG = {"DATA", "WEIGHT_SPECTRUM", "SIGMA_SPECTRUM"}
HOME = Path.home()
SIF = {
    "tricolour": HOME / "rang-data/oracle-images/rang-tricolour_0.2.1-e1.sif",
    "aoflagger": HOME / "rang-data/stimela-sif/stimela_aoflagger_1.2.0.sif",
}
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STRATEGY = {
    "rang": REPO
    / "research/results/e2-acceptance-scripts"
    / "mk_rfi_flagging_calibrator_fields_firstpass.yaml",
    "tricolour": REPO
    / "research/results/e2-acceptance-scripts"
    / "mk_rfi_flagging_calibrator_fields_firstpass.yaml",
    # CARACal 8f7bb363 caracal/data/meerkat_files/firstpass_QUV.rfis, fetched into
    # ROOT/strategies/ (not committed); checked against AOFLAGGER_RFIS_SHA256
    "aoflagger": Path("strategies") / "firstpass_QUV.rfis",
}
AOFLAGGER_RFIS_SHA256 = (
    "edcb4131cae82b80e495ba719a2d0da19627586b2592f5ced400b1e9e90c69c8"
)
RANG_VENV = REPO / ".venv"


def utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(8 << 20):
            h.update(block)
    return h.hexdigest()


def big_files(ms):
    """Relative paths of the main table's files that hold only BIG columns."""
    from casacore.tables import table

    t = table(str(ms), readonly=True, ack=False)
    try:
        info = t.getdminfo()
    finally:
        t.close()
    seqs = [d["SEQNR"] for d in info.values() if set(d["COLUMNS"]) <= BIG]
    out = set()
    for p in ms.iterdir():
        for s in seqs:
            if re.fullmatch(rf"table\.f{s}(_\w+)?", p.name):
                out.add(p.name)
    return out


def private_copy(ms, dest):
    """A full writable copy of `ms` at `dest`, made once (resumable)."""
    marker = dest.with_name(dest.name + ".copied")
    if marker.exists():
        return
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ms, dest, copy_function=shutil.copyfile)
    for q in [dest, *dest.rglob("*")]:
        q.chmod(0o755 if q.is_dir() else 0o644)
    marker.write_text(utc() + "\n")


def restore(ms, wc, big):
    """Every non-bulk file of `wc` back to the frozen MS's bytes."""
    keep = {Path(n) for n in big}
    have = {q.relative_to(wc) for q in wc.rglob("*") if q.is_file()}
    want = {q.relative_to(ms) for q in ms.rglob("*") if q.is_file()}
    for rel in have - want - keep:
        (wc / rel).unlink()
    for rel in sorted(want - keep):
        (wc / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ms / rel, wc / rel)
        (wc / rel).chmod(0o644)


def snapshot(wc, big):
    out = {}
    for n in sorted(big):
        q = wc / n
        out[n] = (
            (q.stat().st_size, q.stat().st_mtime_ns) if "_TSM" in n else sha256_file(q)
        )
    return out


def run(argv, log, env=None):
    t0 = time.perf_counter()
    with open(log, "a") as f:
        f.write(f"START {utc()} {' '.join(map(str, argv))}\n")
        f.flush()
        rc = subprocess.call(
            ["nice", "-n", "19", "ionice", "-c3", "/usr/bin/time", "-v", *map(str, argv)],
            stdout=f, stderr=subprocess.STDOUT, env=env,
        )  # fmt: skip
        f.write(f"END {utc()} rc {rc} wall {time.perf_counter() - t0:.1f} s\n")
    text = Path(log).read_text(errors="replace")
    rss = re.findall(r"Maximum resident set size \(kbytes\): (\d+)", text)
    return rc, time.perf_counter() - t0, int(rss[-1]) if rss else None


def apptainer(sif, binds, cmd, threads):
    b = []
    for host, inside in binds:
        b += ["--bind", f"{Path(host).resolve()}:{inside}"]
    return ["apptainer", "exec", "--containall", "--env", "HOME=/tmp",
            "--env", f"OMP_NUM_THREADS={threads}", "--pwd", "/tmp", *b,
            str(sif), "sh", "-c", cmd]  # fmt: skip


def teach(teacher, strat, wc, work, threads, log):
    if teacher == "tricolour":
        shutil.copy(strat, work / "strategy.yaml")
        cmd = (f"tricolour -c /p/strategy.yaml -fs polarisation -dc DATA -dpm "
               f"-nw {threads} /ms/{wc.name}")  # fmt: skip
        return run(
            apptainer(SIF[teacher], [(wc.parent, "/ms"), (work, "/p")], cmd, threads),
            log,
        )
    if teacher == "aoflagger":
        if sha256_file(strat) != AOFLAGGER_RFIS_SHA256:
            raise SystemExit(f"{strat}: not CARACal's firstpass_QUV.rfis")
        shutil.copy(strat, work / "firstpass_QUV.rfis")
        cmd = f"aoflagger -j {threads} -strategy /p/firstpass_QUV.rfis /ms/{wc.name}"
        return run(
            apptainer(SIF[teacher], [(wc.parent, "/ms"), (work, "/p")], cmd, threads),
            log,
        )
    spool = work / f"spool-{wc.stem}"
    if spool.exists():
        shutil.rmtree(spool)
    spool.mkdir(mode=0o700)
    cfg = work / f"rang-{wc.stem}.yaml"
    shutil.copy(strat, work / strat.name)
    cfg.write_text(
        "schema: rang-config\nversion: 1\n"
        f"data:\n  executor: spool\n  spool: {spool}\n  processes: {threads}\n"
        f"  memory_limit_gb: {2.0 * threads}\n"
        f"flag:\n  strategy: {strat.name}\n"
    )
    py = RANG_VENV / "bin" / "python"
    env = dict(os.environ, RAYON_NUM_THREADS="1")
    argv = [str(py), "-m", "rang.core_spool", "worker", str(spool)]
    argv += ["--threads", "1", "--idle-exit", "120"]
    logs = [open(work / f"worker-{wc.stem}-{i}.log", "w") for i in range(threads)]  # noqa: SIM115
    workers = [
        subprocess.Popen(
            ["nice", "-n", "19", *argv], stdout=f, stderr=subprocess.STDOUT, env=env
        )
        for f in logs
    ]
    try:
        res = run([RANG_VENV / "bin" / "rang-core", "flag", "--run-dir",
                   work / f"run-{wc.stem}", cfg, wc], log, env)  # fmt: skip
    finally:
        subprocess.call([str(py), "-m", "rang.core_spool", "stop", str(spool)])
        for w in workers:
            w.wait(timeout=300)
        for f in logs:
            f.close()
    return res


def extract(wc, out, chunk=20000):
    from casacore.tables import table

    t = table(str(wc), readonly=True, ack=False)
    try:
        n = t.nrows()
        first = t.getcol("FLAG", 0, 1)
        nchan, ncorr = first.shape[1:]
        width = (nchan * ncorr + 7) // 8
        packed = np.lib.format.open_memmap(out / "flag.npy", "w+", np.uint8, (n, width))
        rows = np.empty(n, bool)
        flagged = 0
        for r0 in range(0, n, chunk):
            k = min(chunk, n - r0)
            f = t.getcol("FLAG", r0, k).reshape(k, -1)
            flagged += int(f.sum())
            packed[r0 : r0 + k] = np.packbits(f, axis=1)
            rows[r0 : r0 + k] = t.getcol("FLAG_ROW", r0, k)
        packed.flush()
        del packed
        np.save(out / "flag_row.npy", rows)
    finally:
        t.close()
    return {
        "rows": n,
        "chan": int(nchan),
        "corr": int(ncorr),
        "flagged_fraction": flagged / (n * nchan * ncorr),
    }


def pins(teacher):
    if teacher == "rang":
        py = RANG_VENV / "bin" / "python"
        out = subprocess.run(
            [str(py), "-c", "import json,rang.core_spool as s;print(json.dumps(s.build()))"],
            capture_output=True, text=True, check=True,
        )  # fmt: skip
        b = json.loads(out.stdout)
        git = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=False).stdout.strip()  # fmt: skip
        return {"rang": b["version"], "core_sha256": b["core_sha256"], "commit": git}
    pin = {"image": SIF[teacher].name, "image_sha256": sha256_file(SIF[teacher])}
    if teacher == "aoflagger":
        argv = [
            "apptainer",
            "exec",
            "--containall",
            str(SIF[teacher]),
            "aoflagger",
            "--version",
        ]
        out = subprocess.run(argv, capture_output=True, text=True, check=False).stdout
        pin["version"] = out.strip().splitlines()[-1] if out.strip() else None
    else:
        pin["version"] = "tricolour 0.2.1 (image tag 0.2.1-e1)"
    return pin


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("teachers")
    p.add_argument("cbid")
    p.add_argument("--scans", type=int, nargs="*", default=None)
    p.add_argument("--threads", type=int, default=8)
    p.add_argument("--heldout-read", action="store_true")
    a = p.parse_args(argv)
    root, cbid = a.root.resolve(), a.cbid
    teachers = [
        x for x in ("rang", "tricolour", "aoflagger") if x in a.teachers.split(",")
    ]
    if not teachers or set(a.teachers.split(",")) - set(teachers):
        raise SystemExit("teachers: a comma list of rang, tricolour, aoflagger")
    block = json.loads((root / "manifests" / f"{cbid}.json").read_text())
    if block["split"] == "heldout" and not a.heldout_read:
        raise SystemExit(f"{cbid} is held out (dl2-data.md section 5)")
    pin, strat, done, work, logs = {}, {}, {}, {}, {}
    for te in teachers:
        done[te] = root / "done" / te / cbid
        work[te] = root / "work" / te / cbid
        logs[te] = root / "logs" / te / cbid
        for d in (done[te], work[te], logs[te]):
            d.mkdir(parents=True, exist_ok=True)
        pin[te] = pins(te)
        strat[te] = STRATEGY[te] if STRATEGY[te].is_absolute() else root / STRATEGY[te]
    copies = root / "work" / "copies" / cbid
    for s in block["scans"]:
        n = s["scan"]
        if "ms_hash" not in s or (a.scans is not None and n not in a.scans):
            continue
        todo = [te for te in teachers if not (done[te] / f"{n}.done").exists()]
        if not todo:
            continue
        ms = root / "ms" / cbid / s["ms"]
        text = (root / "manifests" / cbid / f"scan{n:03d}.sha256").read_bytes()
        if hashlib.sha256(text).hexdigest() != s["ms_hash"]:
            raise SystemExit(f"{ms}: manifest hash differs from the block manifest")
        wc = copies / s["ms"]
        private_copy(ms, wc)
        big = big_files(ms)
        for te in todo:
            restore(ms, wc, big)
            before = snapshot(wc, big)
            log = logs[te] / f"scan{n:03d}.log"
            rc, wall, rss = teach(te, strat[te], wc, work[te], a.threads, log)
            if rc != 0:
                raise SystemExit(f"{te} {cbid} scan {n}: rc {rc} (log {log})")
            if snapshot(wc, big) != before:
                raise SystemExit(f"stop: {te} changed DATA or weights in {wc}")
            out = root / "labels" / te / cbid / f"scan{n:03d}"
            if out.exists():
                shutil.rmtree(out)
            out.mkdir(parents=True)
            shape = extract(wc, out)
            label = {"teacher": te, "pins": pin[te], "strategy": strat[te].name,
                     "strategy_sha256": sha256_file(strat[te]), "threads": a.threads,
                     "cbid": cbid, "scan": n, "class": s["class"],
                     "split": block["split"], "input_ms_hash": s["ms_hash"],
                     "wall_s": round(wall, 1), "peak_rss_kb": rss,
                     "written_utc": utc(), **shape}  # fmt: skip
            (out / "label.json").write_text(json.dumps(label, indent=1) + "\n")
            files = ("flag.npy", "flag_row.npy", "label.json")
            sums = "".join(f"{sha256_file(out / f)}  {f}\n" for f in files)
            (out / "SHA256SUMS").write_text(sums)
            digest = hashlib.sha256(sums.encode()).hexdigest()
            (done[te] / f"{n}.done").write_text(f"{utc()} {digest}\n")
            frac = shape["flagged_fraction"]
            print(f"{te} {cbid} scan {n}: {wall:.0f} s, flagged {frac:.4f}", flush=True)
        if all((done[te] / f"{n}.done").exists() for te in teachers):
            shutil.rmtree(wc)
            shutil.rmtree(wc.with_name(wc.name + ".flagversions"), ignore_errors=True)
            wc.with_name(wc.name + ".copied").unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
