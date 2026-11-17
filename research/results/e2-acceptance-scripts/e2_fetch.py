"""E2 fetches (research/e2-acceptance.md, A0 section 8; owner approval: finish-plan item 6).

Usage: python e2_fetch.py {b|a} OUT [--workers 8]

  b  LUNO LBAND_LUNO_CALIBRATORS.zarr MAIN_16-MAIN_19 (scans 17-20)
  a  ESO137 ms1_primary.zarr MAIN_4, MAIN_5 (scans 9, 11) and ms1_target.zarr MAIN_4 (scan 10)
  d  LUNO MAIN_0, MAIN_1 (development scans 1, 2), for E2-B's transfer rows

Per MAIN group: DATA, FLAG, WEIGHT_SPECTRUM and every row column (columns with
no channel axis), plus the group's .zattrs/.zgroup. Plus every subtable of the
store (small). Not fetched: CORRECTED_DATA*, MODEL_DATA, SIGMA_SPECTRUM,
IMAGING_WEIGHT, FLAG_CATEGORY (the reserve and the publisher's products need
their own recorded reason). Objects are written whole, byte for byte, under
OUT/<key>; the file's bytes are never decoded here. Resumable: an object whose
file exists with the listed size is skipped. manifest.json records key, bytes
and SHA-256 of every object; progress.log one line per 100 objects.
Stdlib only. Data: ESO137 CC BY 4.0 (Ramatsoku et al. 2020); LUNO by the
observer's permission (A0 section 1).
"""

import concurrent.futures as cf
import hashlib
import json
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

BUCKET = "https://ratt-public-data.s3.af-south-1.amazonaws.com"
LEGS = {
    "b": [("LBAND_LUNO_CALIBRATORS.zarr", [f"MAIN_{k}" for k in (16, 17, 18, 19)])],
    "a": [
        ("ESO137/ms1_primary.zarr", ["MAIN_4", "MAIN_5"]),
        ("ESO137/ms1_target.zarr", ["MAIN_4"]),
    ],
    # development half of LUNO (scans 1, 2), needed by E2-B's frozen "3C 286
    # transfer" and "1934-638 leakage" rows (A0 6.3); development data, never held out
    "d": [("LBAND_LUNO_CALIBRATORS.zarr", ["MAIN_0", "MAIN_1"])],
}
CUBES = {"DATA", "FLAG", "WEIGHT_SPECTRUM"}
SKIP = {
    "CORRECTED_DATA",
    "CORRECTED_DATA_QCAL",
    "MODEL_DATA",
    "SIGMA_SPECTRUM",
    "IMAGING_WEIGHT",
    "FLAG_CATEGORY",
}


def listing(prefix, delimiter=False):
    keys, prefixes, token = [], [], None
    while True:
        url = f"{BUCKET}/?list-type=2&prefix={urllib.parse.quote(prefix)}"
        if delimiter:
            url += "&delimiter=/"
        if token:
            url += "&continuation-token=" + urllib.parse.quote(token)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=120) as r:
                    text = r.read().decode()
                break
            except OSError:
                time.sleep(2**attempt)
        else:
            raise SystemExit(f"listing failed: {prefix}")
        prefixes += re.findall(r"<CommonPrefixes><Prefix>(.*?)</Prefix>", text)
        keys += [
            (k, int(s))
            for k, s in re.findall(r"<Key>(.*?)</Key>.*?<Size>(\d+)</Size>", text)
        ]
        m = re.search(r"<NextContinuationToken>(.*?)</NextContinuationToken>", text)
        if not m:
            return keys, prefixes
        token = m.group(1)


def plan(leg):
    wanted = []
    for store, groups in LEGS[leg]:
        _, tops = listing(store + "/", delimiter=True)
        for top in tops:
            if top.rstrip("/").endswith("/MAIN"):
                continue
            wanted += listing(top)[0]  # subtables, whole
        for k, s in listing(store + "/", delimiter=True)[0]:
            wanted.append((k, s))  # store root .zgroup/.zattrs
        for k, s in listing(f"{store}/MAIN/", delimiter=True)[0]:
            wanted.append((k, s))
        for g in groups:
            keys, _ = listing(f"{store}/MAIN/{g}/")
            for k, s in keys:
                rest = k[len(f"{store}/MAIN/{g}/") :].split("/")
                if len(rest) == 1:
                    wanted.append((k, s))
                    continue
                col = rest[0]
                if col in SKIP:
                    continue
                wanted.append((k, s))
    # A key that is also a "directory" of other keys (S3 folder placeholders such
    # as ESO137/ms1_target.zarr) cannot be a file here: skip it and record it.
    keys = {k for k, _ in wanted}
    dirs = {k.rsplit("/", i)[0] for k in keys for i in range(1, k.count("/") + 1)}
    skipped = [(k, s) for k, s in wanted if k in dirs or k.endswith("/")]
    if skipped:
        print(f"skipped folder placeholders: {skipped}", flush=True)
    return [
        (k, s) for k, s in dict(wanted).items() if k not in dirs and not k.endswith("/")
    ]


class Getter:
    def get(self, key):
        url = f"{BUCKET}/{urllib.parse.quote(key)}"
        for attempt in range(6):
            try:
                with urllib.request.urlopen(url, timeout=300) as r:
                    return r.read()
            except OSError:
                time.sleep(min(60, 2**attempt))
        raise OSError(f"failed after retries: {key}")


def main():
    leg, out = sys.argv[1], Path(sys.argv[2])
    workers = (
        int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 8
    )
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    wanted = plan(leg)
    total = sum(s for _, s in wanted)
    (out / "plan.json").write_text(
        json.dumps({"leg": leg, "objects": len(wanted), "bytes": total, "keys": wanted})
    )
    print(f"plan: {len(wanted)} objects, {total:,} bytes", flush=True)
    man_path = out / "manifest.json"
    manifest = json.loads(man_path.read_text()) if man_path.exists() else {}
    lock = threading.Lock()
    done = [0, 0]
    log = open(out / "progress.log", "a", encoding="utf-8")  # noqa: SIM115
    getter = Getter()

    def one(item):
        key, size = item
        path = out / key
        if key in manifest and path.exists() and path.stat().st_size == size:
            return key, size, False
        data = getter.get(key)
        if len(data) != size:
            raise OSError(f"{key}: {len(data)} bytes, listed {size}")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)
        return key, size, hashlib.sha256(data).hexdigest()

    with cf.ThreadPoolExecutor(workers) as pool:
        for key, size, digest in pool.map(one, wanted):
            with lock:
                if digest:
                    manifest[key] = {"bytes": size, "sha256": digest}
                done[0] += 1
                done[1] += size
                if done[0] % 100 == 0 or done[0] == len(wanted):
                    man_path.write_text(json.dumps(manifest, indent=0))
                    el = time.time() - t0
                    log.write(
                        f"{time.strftime('%Y-%m-%d %H:%M:%S')} {done[0]}/{len(wanted)} "
                        f"{done[1]:,} B {done[1] / el / 1e6:.1f} MB/s\n"
                    )
                    log.flush()
    man_path.write_text(json.dumps(manifest, indent=0))
    el = time.time() - t0
    print(f"done: {len(manifest)} objects, {done[1]:,} bytes, {el:.0f} s", flush=True)


if __name__ == "__main__":
    main()
