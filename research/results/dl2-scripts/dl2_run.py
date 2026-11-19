"""DL2 shard driver for one block: fetch, convert, hash, freeze
(research/dl2-data.md section 4). Runs on nash in .venv-dl2.

    python dl2_run.py ROOT CBID [--scans S ...] [--delete-mvf] [--workers 16]

ROOT is the run root (plan/, mvf/, ms/, manifests/, done/, logs/). Per
scan of ROOT/plan/<cbid>.json (or only --scans), two shards, each skipped
when its done-marker exists:
- fetch: dl2_fetch.py for that scan; done/<cbid>/fetch-<scan>.done;
- convert: mvftoms.py on the local RDB (no token, no network) into
  ms/<cbid>/scan<NNN>.part.ms, renamed to scan<NNN>.ms; then the SHA-256
  manifest manifests/<cbid>/scan<NNN>.sha256, the row count and column
  names from the table descriptor (no cell read), chmod -R a-w;
  done/<cbid>/convert-<scan>.done holds the MS hash.
Before each shard: at least MIN_FREE bytes free on ROOT, or stop. After
the scans: manifests/<cbid>.json; with --delete-mvf and every planned scan
converted, the block's MVF chunk buckets are deleted (the RDB is kept).
Every log is checked for `token=`; a hit stops the run.
"""

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

MIN_FREE = 2 * 10**12
HERE = Path(__file__).resolve().parent
MVFTOMS = ["-f", "-a", "--flags", "static,cam,data_lost,ingest_rfi,predicted_rfi"]


def utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def guard(root):
    free = shutil.disk_usage(root).free
    if free < MIN_FREE:
        raise SystemExit(f"stop: {free / 1e12:.2f} TB free on {root} (< 2 TB)")
    return free


def no_token(path):
    with open(path, "rb") as f:
        for line in f:
            if b"token=" in line or b"eyJ" in line:
                raise SystemExit(f"stop: token-like text in {path}")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(8 << 20):
            h.update(block)
    return h.hexdigest()


def manifest(ms):
    files = sorted(p for p in ms.rglob("*") if p.is_file())
    lines = [f"{sha256_file(p)}  {p.relative_to(ms).as_posix()}\n" for p in files]
    total = sum(p.stat().st_size for p in files)
    return "".join(lines), total, len(files)


def read_only(tree):
    for p in [tree, *tree.rglob("*")]:
        mode = p.stat().st_mode
        p.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def describe(ms):
    from casacore.tables import table

    t = table(str(ms), readonly=True, ack=False)
    try:
        return {"rows": int(t.nrows()), "columns": sorted(t.colnames())}
    finally:
        t.close()


def run_logged(argv, log):
    t0 = time.perf_counter()
    with open(log, "a") as f:
        f.write(f"START {utc()} {' '.join(map(str, argv[:3]))} ...\n")
        f.flush()
        rc = subprocess.call(
            ["nice", "-n", "19", "ionice", "-c3", "/usr/bin/time", "-v", *argv],
            stdout=f, stderr=subprocess.STDOUT,
        )  # fmt: skip
        f.write(f"END {utc()} rc {rc} wall {time.perf_counter() - t0:.1f} s\n")
    no_token(log)
    return rc


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("cbid")
    p.add_argument("--scans", type=int, nargs="*", default=None)
    p.add_argument("--delete-mvf", action="store_true")
    p.add_argument("--workers", type=int, default=16)
    p.add_argument(
        "--linkfile", default=os.path.expanduser("~/rang-data/sarao-links-dl.txt")
    )
    a = p.parse_args(argv)
    root, cbid = a.root.resolve(), a.cbid
    plan = json.loads((root / "plan" / f"{cbid}.json").read_text())
    scans = [s for s in plan["scans"] if a.scans is None or s["scan"] in a.scans]
    done = root / "done" / cbid
    msdir = root / "ms" / cbid
    mandir = root / "manifests" / cbid
    logs = root / "logs" / cbid
    mvf = root / "mvf"
    for d in (done, msdir, mandir, logs, mvf):
        d.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    rdb = mvf / cbid / f"{cbid}_sdp_l0.full.rdb"
    for s in scans:
        n = s["scan"]
        fmark = done / f"fetch-{n}.done"
        if not fmark.exists():
            guard(root)
            rc = run_logged(
                [py, "-W", "ignore", str(HERE / "dl2_fetch.py"), a.linkfile, str(mvf),
                 "--cbid", cbid, "--scans", str(n), "--workers", str(a.workers)],
                logs / f"fetch-{n}.log",
            )  # fmt: skip
            if rc != 0:
                raise SystemExit(f"{cbid} scan {n}: fetch rc {rc}")
            receipt = mvf / f"{cbid}-receipts" / f"fetch-{n}.json"
            fmark.write_text(f"{utc()} {sha256_file(receipt)}\n")
        cmark = done / f"convert-{n}.done"
        if cmark.exists():
            continue
        guard(root)
        part = msdir / f"scan{n:03d}.part.ms"
        final = msdir / f"scan{n:03d}.ms"
        for old in msdir.glob(f"scan{n:03d}.part.ms*"):
            shutil.rmtree(old) if old.is_dir() else old.unlink()
        rc = run_logged(
            [py, "-W", "ignore", str(Path(py).parent / "mvftoms.py"), *MVFTOMS,
             "--scans", str(n), "-o", str(part), str(rdb)],
            logs / f"convert-{n}.log",
        )  # fmt: skip
        if rc != 0:
            raise SystemExit(f"{cbid} scan {n}: mvftoms rc {rc}")
        if final.exists():
            raise SystemExit(f"{final} exists without a done-marker; inspect")
        part.rename(final)
        text, size, nfiles = manifest(final)
        (mandir / f"scan{n:03d}.sha256").write_text(text)
        ms_hash = hashlib.sha256(text.encode()).hexdigest()
        info = {"scan": n, "ms": final.name, "ms_hash": ms_hash, "bytes": size,
                "files": nfiles, **describe(final)}  # fmt: skip
        (mandir / f"scan{n:03d}.json").write_text(json.dumps(info, indent=1) + "\n")
        read_only(final)
        cmark.write_text(f"{utc()} {ms_hash}\n")
        print(
            f"{cbid} scan {n}: {info['rows']} rows, {size / 1e9:.1f} GB, {ms_hash[:12]}"
        )
    import katdal

    entries = []
    for s in plan["scans"]:
        j = mandir / f"scan{s['scan']:03d}.json"
        entries.append({**s, **(json.loads(j.read_text()) if j.exists() else {})})
    complete = all("ms_hash" in e for e in entries)
    block = {"cbid": cbid, "split": plan["split"], "meta_sha256": plan["meta_sha256"],
             "plan_sha256": sha256_file(root / "plan" / f"{cbid}.json"),
             "katdal": katdal.__version__, "mvftoms_args": MVFTOMS + ["--quack 1 (default)"],
             "complete": complete, "scans": entries, "written_utc": utc()}  # fmt: skip
    path = root / "manifests" / f"{cbid}.json"
    if path.exists():  # rewrite only on a change, so the manifest's hash is stable
        old = json.loads(path.read_text())
        if {**old, "written_utc": None} == {**block, "written_utc": None}:
            block = old
    path.write_text(json.dumps(block, indent=1) + "\n")
    if a.delete_mvf and complete:
        for b in sorted(mvf.glob(f"{cbid}-*")):
            if b.is_dir() and not b.name.endswith("-receipts"):
                shutil.rmtree(b)
                print(f"deleted MVF bucket {b.name}")
    print(
        f"{cbid}: {'complete' if complete else 'partial'}, free {guard(root) / 1e12:.2f} TB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
