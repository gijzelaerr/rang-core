# SPDX-License-Identifier: MIT
"""uhf-s-fetch: one capture block's MVFv4 chunks from the SARAO archive to disk
(research/uhf-s-fetch.md section 3).

    python uhfs_fetch.py LINKFILE DEST --cbid CBID [--scans S ...] [--workers 6]
                         [--max-mbps 40] [--max-lost 0.001]

dl2_fetch.py's method (itself e2n_fetch.py's), changed in five points:
- LINKFILE has one line per block, `cbid band url`; the block is picked by
  --cbid. The URL and token are read here only and never printed, logged,
  written or put on a command line;
- the selection is every track scan of the block (mvftoms converts tracks
  only), or --scans, listed per scan with katdal's `mvf_download.chunk_names`
  and merged; with --scans the receipts go to DEST/<cbid>-receipts-scans-<S-S>;
- each chunk's SHA-256 is computed while it streams and appended to
  DEST/<cbid>-receipts/chunks-sha256.txt (`sha256  bucket/name`); chunks
  already on disk without a line are hashed at the end;
- one global rate cap (--max-mbps, MB/s over all workers) keeps the shared
  host's link friendly;
- a chunk the archive does not hold (HTTP 404) is recorded as lost, not
  retried (katdal marks it data_lost in the conversion). More lost chunks than
  --max-lost (fraction of all, at least 5) means the block is not streaming
  from the archive (not staged): fetch.done is withheld and the exit is 3.
  Below the bound, fetch.done is written only when the same lost list was
  recorded by an earlier pass at least an hour before (lost-previous.json), so
  chunks that are merely not staged yet are not taken as lost; otherwise the
  list is recorded and the exit is 3.
Writes DEST/<cbid>-receipts/fetch-progress.jsonl (one line a minute) and
fetch.json at the end, then DEST/<cbid>-receipts/fetch.done when no chunk
failed. Exit 1 if any chunk failed other than lost, 3 if too many were lost.
"""

import argparse
import hashlib
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


class Lost(Exception):
    """The archive does not hold this chunk (HTTP 404)."""


def read_url(path, cbid):
    for line in Path(path).read_text().splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == cbid and parts[2].startswith("http"):
            return parts[2]
    raise SystemExit(f"no URL for {cbid} in the link file")


def scrub(text, token):
    text = str(text)
    if token:
        text = text.replace(token, "<TOKEN>")
    text = re.sub(r"token=[A-Za-z0-9._\-]+", "token=<TOKEN>", text)
    return re.sub(r"eyJ[A-Za-z0-9._\-]{20,}", "<TOKEN>", text)


def mvf_download_module():
    script = Path(sys.executable).parent / "mvf_download.py"
    spec = importlib.util.spec_from_file_location("mvf_download", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RateCap:
    """A shared byte budget: callers sleep when the run is ahead of the cap."""

    def __init__(self, mb_per_s):
        self.rate = mb_per_s * 1e6
        self.t0 = time.time()
        self.n = 0
        self.lock = threading.Lock()

    def take(self, n):
        if self.rate <= 0:
            return
        with self.lock:
            self.n += n
            ahead = self.n / self.rate - (time.time() - self.t0)
        if ahead > 0:
            time.sleep(ahead)


def get(session, url, token, dest, cap, retries=6):
    part = dest.with_name(dest.name + ".part")
    last = None
    for attempt in range(retries):
        try:
            with session.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                stream=True,
                timeout=(60, 300),
            ) as r:
                if r.status_code == 404:
                    raise Lost(dest.name)
                r.raise_for_status()
                n = 0
                h = hashlib.sha256()
                with open(part, "wb") as f:
                    for block in r.iter_content(1 << 20):
                        f.write(block)
                        h.update(block)
                        n += len(block)
                        cap.take(len(block))
                expect = r.headers.get("Content-Length")
                if expect is not None and int(expect) != n:
                    raise OSError(f"short read {n} of {expect}")
            part.replace(dest)
            return n, h.hexdigest()
        except Lost:
            raise
        except Exception as exc:  # noqa: BLE001  (retried; the message may carry the URL)
            last = scrub(f"{type(exc).__name__}: {exc}", token)
            time.sleep(min(120, 5 * 2**attempt))
    raise RuntimeError(last)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("linkfile")
    p.add_argument("dest", type=Path)
    p.add_argument("--cbid", required=True)
    p.add_argument("--scans", type=int, nargs="+", default=None)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--max-lost", type=float, default=0.001)
    p.add_argument("--max-mbps", type=float, default=40.0)
    a = p.parse_args(argv)
    url = read_url(a.linkfile, a.cbid)
    parts = urlparse(url)
    token = dict(parse_qsl(parts.query)).get("token")
    endpoint = urlunparse((parts.scheme, parts.netloc, "", "", "", ""))
    *_, cbid, rdb_name = PurePosixPath(parts.path).parts
    a.dest.mkdir(parents=True, exist_ok=True)
    tag = "" if a.scans is None else "-scans-" + "-".join(map(str, a.scans))
    receipts = a.dest / f"{cbid}-receipts{tag}"
    receipts.mkdir(exist_ok=True)
    progress = receipts / "fetch-progress.jsonl"
    manifest = receipts / "chunks-sha256.txt"
    cap = RateCap(a.max_mbps)
    t0 = time.time()
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=a.workers + 2))
    try:
        rdb = a.dest / cbid / rdb_name
        rdb.parent.mkdir(parents=True, exist_ok=True)
        if not rdb.exists():
            get(session, f"{endpoint}/{cbid}/{rdb_name}", token, rdb, cap)
        import katdal

        query = urlencode({"s3_endpoint_url": endpoint, "token": token})
        d = katdal.open(urlunparse(("file", "", str(rdb.absolute()), "", query, "")))
        tracks = [int(i) for i, state, _ in d.scans() if state == "track"]
        if a.scans is not None:
            tracks = [i for i in tracks if i in a.scans]
        d.select(scans=tracks)
        selected = {
            "scans": tracks,
            "dumps": int(d.shape[0]),
            "channels": int(d.shape[1]),
            "products": int(d.shape[2]),
        }
        names = mvf_download_module().chunk_names
        merged = {}
        for scan in tracks:
            d.select()
            d.select(scans=[scan])
            for bucket, files in names(d.source.data, d.vis.keep).items():
                merged.setdefault(bucket, set()).update(files)
        chunks = {b: sorted(f) for b, f in merged.items()}
    except Exception as exc:  # noqa: BLE001  (the message may carry the URL)
        raise SystemExit(scrub(f"{type(exc).__name__}: {exc}", token)) from None
    jobs = []
    for bucket, files in chunks.items():
        for name in files:
            out = a.dest / bucket / name
            out.parent.mkdir(parents=True, exist_ok=True)
            jobs.append((f"{endpoint}/{bucket}/{name}", out))
    todo = [(u, o) for u, o in jobs if not o.exists()]
    lock = threading.Lock()
    state = {
        "done": len(jobs) - len(todo),
        "bytes": 0,
        "failed": [],
        "lost": [],
        "last": time.time(),
    }

    def note(final=False):
        el = time.time() - t0
        rec = {
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "seconds": round(el, 1),
            "chunks_done": state["done"],
            "chunks_total": len(jobs),
            "bytes_this_run": state["bytes"],
            "mb_per_s": round(state["bytes"] / 1e6 / max(el, 1e-9), 2),
            "failed": len(state["failed"]),
            "lost": len(state["lost"]),
            "final": final,
        }
        with open(progress, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec

    def one(job):
        u, o = job
        n, sha = get(session, u, token, o, cap)
        with lock:
            with open(manifest, "a") as f:
                f.write(f"{sha}  {o.relative_to(a.dest).as_posix()}\n")
            state["done"] += 1
            state["bytes"] += n
            if time.time() - state["last"] > 60:
                state["last"] = time.time()
                note()

    note()
    with ThreadPoolExecutor(a.workers) as pool:
        futs = {pool.submit(one, j): j for j in todo}
        for fut in as_completed(futs):
            exc = fut.exception()
            if isinstance(exc, Lost):
                state["lost"].append(str(futs[fut][1].relative_to(a.dest).as_posix()))
            elif exc is not None:
                state["failed"].append(
                    {
                        "chunk": str(futs[fut][1].relative_to(a.dest)),
                        "error": scrub(exc, token),
                    }
                )
    hashed = set()
    if manifest.exists():
        hashed = {
            ln.split("  ", 1)[1] for ln in manifest.read_text().splitlines() if ln
        }
    late = 0
    for _, o in jobs:
        rel = o.relative_to(a.dest).as_posix()
        if o.exists() and rel not in hashed:
            with open(manifest, "a") as f:
                f.write(f"{sha256_file(o)}  {rel}\n")
            late += 1
    rec = note(final=True)
    receipt = {
        "cbid": cbid,
        "rdb": rdb_name,
        "rdb_sha256": sha256_file(rdb),
        "selection": selected,
        "chunks_by_bucket": {b: len(n) for b, n in chunks.items()},
        "chunks_total": len(jobs),
        "already_present": len(jobs) - len(todo),
        "hashed_after": late,
        "workers": a.workers,
        "max_mbps": a.max_mbps,
        "progress": rec,
        "failed": state["failed"][:50],
        "lost": state["lost"],
        "katdal": katdal.__version__,
    }
    (receipts / "fetch.json").write_text(
        scrub(json.dumps(receipt, indent=1), token) + "\n"
    )
    print(scrub(json.dumps(rec), token))
    if state["failed"]:
        return 1
    if len(state["lost"]) > max(5, a.max_lost * len(jobs)):
        print(f"{len(state['lost'])} of {len(jobs)} chunks lost: not streaming")
        return 3
    if state["lost"]:
        prev_path = receipts / "lost-previous.json"
        lost = sorted(state["lost"])
        prev = json.loads(prev_path.read_text()) if prev_path.exists() else None
        if not (prev and prev["lost"] == lost and time.time() - prev["time"] >= 3600):
            if not (prev and prev["lost"] == lost):
                prev_path.write_text(
                    json.dumps({"time": time.time(), "lost": lost}) + "\n"
                )
            print(
                f"{len(lost)} chunks lost: recorded; fetch.done waits for a pass an hour later"
            )
            return 3
    (receipts / "fetch.done").write_text(
        time.strftime("%Y-%m-%dT%H:%M:%SZ\n", time.gmtime())
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
