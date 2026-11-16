"""E2-N fetch: the selected scans' MVFv4 chunks from the SARAO archive to disk
(research/e2n-native.md section 4). Run in the WSL katdal venv.

    python e2n_fetch.py LINKFILE DEST --scans 1 3 5 ... [--workers 8]

What it does, as katdal's own `mvf_download.py` but without rclone (not on
this host) and with the token kept in memory:
- reads the RDB URL from LINKFILE; it is never printed, logged, written or
  put on a command line (rclone would carry it in argv);
- downloads the RDB to DEST/<cbid>/ and opens it with katdal, applies
  `select(scans=...)` and lists the chunks of every stored array that the
  selection covers (`mvf_download.chunk_names`, imported from the venv);
- fetches each chunk with HTTPS GET and an `Authorization: Bearer` header
  into DEST/<bucket>/<name>, written as `.part` and renamed when complete,
  so a rerun skips finished chunks and refetches partial ones;
- appends one JSON line per minute to DEST/fetch-progress.jsonl (chunks,
  bytes, MB/s) and writes DEST/fetch-receipt.json at the end.
The chunks are bytes only: nothing is decoded. Exit 1 if any chunk failed.
"""

import argparse
import importlib.util
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests


def read_url(path):
    for line in Path(path).read_text().splitlines():
        if line.strip().startswith("http"):
            return line.strip()
    raise SystemExit("no URL in the link file")


def scrub(text, token):
    text = str(text)
    if token:
        text = text.replace(token, "<TOKEN>")
    return re.sub(r"token=[A-Za-z0-9._\-]+", "token=<TOKEN>", text)


def mvf_download_module():
    script = Path(sys.executable).parent / "mvf_download.py"
    spec = importlib.util.spec_from_file_location("mvf_download", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get(session, url, token, dest, retries=6):
    part = dest.with_name(dest.name + ".part")
    for attempt in range(retries):
        try:
            with session.get(url, headers={"Authorization": f"Bearer {token}"},
                             stream=True, timeout=(60, 300)) as r:  # fmt: skip
                r.raise_for_status()
                n = 0
                with open(part, "wb") as f:
                    for block in r.iter_content(1 << 20):
                        f.write(block)
                        n += len(block)
                expect = r.headers.get("Content-Length")
                if expect is not None and int(expect) != n:
                    raise OSError(f"short read {n} of {expect}")
            part.replace(dest)
            return n
        except Exception as exc:  # noqa: BLE001  (retried; the message may carry the URL)
            last = scrub(f"{type(exc).__name__}: {exc}", token)
            time.sleep(min(120, 5 * 2**attempt))
    raise RuntimeError(last)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("linkfile")
    p.add_argument("dest", type=Path)
    p.add_argument("--scans", type=int, nargs="+", required=True)
    p.add_argument("--workers", type=int, default=8)
    a = p.parse_args(argv)
    url = read_url(a.linkfile)
    parts = urlparse(url)
    token = dict(parse_qsl(parts.query)).get("token")
    endpoint = urlunparse((parts.scheme, parts.netloc, "", "", "", ""))
    *_, cbid, rdb_name = PurePosixPath(parts.path).parts
    a.dest.mkdir(parents=True, exist_ok=True)
    progress = a.dest / "fetch-progress.jsonl"
    t0 = time.time()
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=a.workers + 2))
    try:
        rdb = a.dest / cbid / rdb_name
        rdb.parent.mkdir(parents=True, exist_ok=True)
        if not rdb.exists():
            get(session, f"{endpoint}/{cbid}/{rdb_name}", token, rdb)
        import katdal

        query = urlencode({"s3_endpoint_url": endpoint, "token": token})
        d = katdal.open(urlunparse(("file", "", str(rdb.absolute()), "", query, "")))
        d.select(scans=a.scans)
        selected = {"scans": a.scans, "dumps": int(d.shape[0]),
                    "channels": int(d.shape[1]), "products": int(d.shape[2])}  # fmt: skip
        # chunk_names fails in dask on a selection of several separate scans
        # ("zero-dimensional arrays cannot be concatenated"), so the chunk
        # lists are made per scan and merged.
        names = mvf_download_module().chunk_names
        merged = {}
        for scan in a.scans:
            d.select()
            d.select(scans=[scan])
            for bucket, files in names(d.source.data, d.vis.keep).items():
                merged.setdefault(bucket, set()).update(files)
        chunks = {b: sorted(f) for b, f in merged.items()}
    except Exception as exc:  # noqa: BLE001  (the message may carry the URL)
        raise SystemExit(scrub(f"{type(exc).__name__}: {exc}", token)) from None
    jobs = []
    for bucket, names in chunks.items():
        for name in names:
            out = a.dest / bucket / name
            out.parent.mkdir(parents=True, exist_ok=True)
            jobs.append((f"{endpoint}/{bucket}/{name}", out))
    todo = [(u, o) for u, o in jobs if not o.exists()]
    lock = threading.Lock()
    state = {
        "done": len(jobs) - len(todo),
        "bytes": 0,
        "failed": [],
        "last": time.time(),
    }

    def note(final=False):
        el = time.time() - t0
        rec = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "seconds": round(el, 1), "chunks_done": state["done"],
               "chunks_total": len(jobs), "bytes_this_run": state["bytes"],
               "mb_per_s": round(state["bytes"] / 1e6 / max(el, 1e-9), 2),
               "failed": len(state["failed"]), "final": final}  # fmt: skip
        with open(progress, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec

    def one(job):
        u, o = job
        n = get(session, u, token, o)
        with lock:
            state["done"] += 1
            state["bytes"] += n
            if time.time() - state["last"] > 60:
                state["last"] = time.time()
                note()

    with ThreadPoolExecutor(a.workers) as pool:
        futs = {pool.submit(one, j): j for j in todo}
        for fut in as_completed(futs):
            exc = fut.exception()
            if exc is not None:
                state["failed"].append({"chunk": str(futs[fut][1].relative_to(a.dest)),
                                        "error": scrub(exc, token)})  # fmt: skip
    rec = note(final=True)
    receipt = {"cbid": cbid, "rdb": rdb_name, "selection": selected,
               "chunks_by_bucket": {b: len(n) for b, n in chunks.items()},
               "already_present": len(jobs) - len(todo), "workers": a.workers,
               "progress": rec, "failed": state["failed"][:50],
               "katdal": katdal.__version__}  # fmt: skip
    (a.dest / "fetch-receipt.json").write_text(
        scrub(json.dumps(receipt, indent=1), token)
    )
    print(scrub(json.dumps(rec), token))
    return 1 if state["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
