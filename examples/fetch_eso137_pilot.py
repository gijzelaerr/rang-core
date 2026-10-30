"""Bounded fetches of the ESO137 B1-2 sets (research/b1-2-identifiability.md).

`probe OUT` is the pre-protocol probe tool (small objects only): S3 listings
of the subset's MAIN columns and subtables, the `.zarray` metadata, and the
row columns, FLAG, MODEL_DATA and UVW of row chunk 0 (5.5 MB).

`fetch OUT` is the frozen S4 pilot: row chunk 0 of `ms1_target_subset.zarr`
(scan 2, 1347-1451 MHz) for DATA, FLAG, WEIGHT_SPECTRUM, MODEL_DATA, UVW and
the row columns, plus the subtable arrays the survey needs (bound 1.25 GB).

`track OUT` is the frozen S5 track: row chunk 0, channel tile 20 of DATA,
FLAG and WEIGHT_SPECTRUM, UVW and the row columns of each of the seven
`ms1_target.zarr` scans, plus CHAN_FREQ, ANTENNA POSITION and PHASE_DIR
(bound 2.0 GB).

Every object's bytes, SHA256, HTTP headers and time go to `receipt.json`
and `objects/receipt.txt`. The planned total is computed from the S3
listing (or HEAD) sizes and refused above the bound before any large
object is requested. Object (pickle) columns are never fetched or decoded.
ESO137 data: CC BY 4.0, cite Ramatsoku et al. 2020.
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from rang import core_fetch

BUCKET = "https://ratt-public-data.s3.af-south-1.amazonaws.com"
SUBSET = "ESO137/ms1_target_subset.zarr"
TRACK = "ESO137/ms1_target.zarr"
GROUP = "MAIN/MAIN_0"
TRACK_GROUPS = tuple(f"MAIN/MAIN_{k}" for k in range(7))
TRACK_TILE = 20
ROW_COLUMNS = ("TIME", "ANTENNA1", "ANTENNA2", "FLAG_ROW", "INTERVAL")
CUBE_COLUMNS = ("DATA", "FLAG", "WEIGHT_SPECTRUM", "MODEL_DATA")
TRACK_CUBE_COLUMNS = ("DATA", "FLAG", "WEIGHT_SPECTRUM")
SUBTABLE_ARRAYS = (
    "ANTENNA/ANTENNA_0/POSITION",
    "ANTENNA/ANTENNA_0/DISH_DIAMETER",
    "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ",
    "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_WIDTH",
    "FIELD/FIELD_0/PHASE_DIR",
    "POLARIZATION/POLARIZATION_0/CORR_TYPE",
    "FEED/FEED_0/RECEPTOR_ANGLE",
    "FEED/FEED_0/ANTENNA_ID",
    "OBSERVATION/OBSERVATION_0/TIME_RANGE",
)
TRACK_SUBTABLES = (
    "ANTENNA/ANTENNA_0/POSITION",
    "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ",
    "FIELD/FIELD_0/PHASE_DIR",
)
# Frozen bounds (research/b1-2-identifiability.md, "Fetch").
MAX_BYTES = 1_250_000_000
TRACK_MAX_BYTES = 2_000_000_000


def listing(prefix, delimiter=True):
    keys, prefixes, token = [], [], None
    while True:
        url = f"{BUCKET}/?list-type=2&prefix={prefix}"
        if delimiter:
            url += "&delimiter=/"
        if token:
            url += "&continuation-token=" + urllib.parse.quote(token)
        with urllib.request.urlopen(url, timeout=120) as response:
            text = response.read().decode()
        prefixes += re.findall(r"<CommonPrefixes><Prefix>(.*?)</Prefix>", text)
        keys += [
            (k, int(s))
            for k, s in re.findall(r"<Key>(.*?)</Key>.*?<Size>(\d+)</Size>", text)
        ]
        match = re.search(r"<NextContinuationToken>(.*?)</NextContinuationToken>", text)
        if not match:
            return keys, prefixes
        token = match.group(1)


def head_size(store, key):
    request = urllib.request.Request(f"{BUCKET}/{store}/{key}", method="HEAD")
    with urllib.request.urlopen(request, timeout=120) as response:
        return int(response.headers["Content-Length"])


def chunk0_key(meta, tile=0):
    if len(meta["shape"]) == 3:
        return f"0.{tile}.0"
    return ".".join("0" for _ in meta["shape"])


def get_all(client, store, keys, out):
    records = []
    for key in keys:
        record, body = client.get(f"{store}/{key}")
        dest = out / "objects" / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        record["key"] = key
        records.append(record)
    return records


def metadata(client, store, out, arrays):
    """`.zarray` of every array (None when absent); returns key -> meta."""
    metas = {}
    records = []
    for name in arrays:
        try:
            record, body = client.get(f"{store}/{name}/.zarray")
        except OSError:
            metas[name] = None
            continue
        meta = json.loads(body)
        if meta.get("filters") or meta["dtype"] == "|O":
            raise ValueError(f"{name}: object or filtered arrays are never fetched")
        dest = out / "objects" / name / ".zarray"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        record["key"] = f"{name}/.zarray"
        records.append(record)
        metas[name] = meta
    return metas, records


def write_receipts(out, store, records, planned, bound, started_utc, seconds):
    lines = [f"{r['bytes']} {r['sha256']} {r['key']}" for r in records]
    (out / "objects" / "receipt.txt").write_text("\n".join(lines) + "\n")
    result = {
        "store": f"{BUCKET}/{store}",
        "licence": "CC BY 4.0 (cite Ramatsoku et al. 2020)",
        "started_utc": started_utc,
        "planned_bytes": planned,
        "max_bytes": bound,
        "requests": [
            {
                k: r.get(k)
                for k in ("key", "status", "bytes", "seconds", "sha256", "headers")
            }
            for r in records
        ],
        "bytes": sum(r["bytes"] for r in records),
        "seconds": seconds,
    }
    (out / "receipt.json").write_text(json.dumps(result, indent=1))
    print(json.dumps({k: result[k] for k in ("bytes", "seconds", "planned_bytes")}))
    return result


def probe(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    listings = {}
    for prefix in (f"{SUBSET}/{GROUP}/", f"{SUBSET}/FEED/", f"{SUBSET}/"):
        keys, prefixes = listing(prefix)
        listings[prefix] = {"prefixes": prefixes, "keys": keys}
    sizes = {}
    for column in ("DATA", "FLAG", "WEIGHT_SPECTRUM", "MODEL_DATA", "UVW"):
        keys, _ = listing(f"{SUBSET}/{GROUP}/{column}/", delimiter=False)
        sizes[column] = {k.split("/")[-1]: s for k, s in keys}
    client = core_fetch.Client(BUCKET)
    try:
        arrays = [f"{GROUP}/{c}" for c in ROW_COLUMNS + ("FLAG", "MODEL_DATA", "UVW")]
        metas, records = metadata(client, SUBSET, out, arrays + list(SUBTABLE_ARRAYS))
        keys = [f"{GROUP}/.zattrs"]
        keys += [f"{a}/{chunk0_key(metas[a])}" for a in arrays]
        keys += [f"{a}/{chunk0_key(metas[a])}" for a in SUBTABLE_ARRAYS if metas[a]]
        records += get_all(client, SUBSET, keys, out)
    finally:
        client.close()
    result = {
        "listings": listings,
        "chunk_sizes": sizes,
        "metas": metas,
        "requests": [
            {k: r[k] for k in ("key", "status", "bytes", "seconds", "sha256")}
            for r in records
        ],
        "bytes": sum(r["bytes"] for r in records),
        "seconds": time.perf_counter() - started,
    }
    (out / "probe.json").write_text(json.dumps(result, indent=1))
    print(json.dumps({k: result[k] for k in ("bytes", "seconds")}))
    return result


def fetch(out):
    """The frozen S4 pilot (bound MAX_BYTES)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    started = time.perf_counter()
    sizes = {}
    for column in CUBE_COLUMNS + ("UVW",) + ROW_COLUMNS:
        keys, _ = listing(f"{SUBSET}/{GROUP}/{column}/", delimiter=False)
        sizes[column] = {k.split("/")[-1]: s for k, s in keys}
    client = core_fetch.Client(BUCKET, timeout=600.0)
    try:
        arrays = [f"{GROUP}/{c}" for c in ROW_COLUMNS + CUBE_COLUMNS + ("UVW",)]
        metas, records = metadata(client, SUBSET, out, arrays + list(SUBTABLE_ARRAYS))
        planned = sum(
            sizes[a.split("/")[-1]].get(chunk0_key(metas[a]), 0) for a in arrays
        )
        if planned > MAX_BYTES:
            raise RuntimeError(f"planned {planned} bytes exceed the frozen bound")
        keys = [f"{GROUP}/.zattrs"]
        keys += [f"{a}/{chunk0_key(metas[a])}" for a in arrays]
        keys += [f"{a}/{chunk0_key(metas[a])}" for a in SUBTABLE_ARRAYS if metas[a]]
        records += get_all(client, SUBSET, keys, out)
    finally:
        client.close()
    return write_receipts(
        out,
        SUBSET,
        records,
        planned,
        MAX_BYTES,
        started_utc,
        time.perf_counter() - started,
    )


def track(out):
    """The frozen S5 track (bound TRACK_MAX_BYTES)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    started = time.perf_counter()
    client = core_fetch.Client(BUCKET, timeout=600.0)
    try:
        arrays = [
            f"{g}/{c}"
            for g in TRACK_GROUPS
            for c in ROW_COLUMNS[:4] + TRACK_CUBE_COLUMNS + ("UVW",)
        ]
        metas, records = metadata(client, TRACK, out, arrays + list(TRACK_SUBTABLES))
        large = [f"{a}/{chunk0_key(metas[a], TRACK_TILE)}" for a in arrays]
        planned = sum(head_size(TRACK, key) for key in large)
        if planned > TRACK_MAX_BYTES:
            raise RuntimeError(f"planned {planned} bytes exceed the frozen bound")
        keys = [f"{g}/.zattrs" for g in TRACK_GROUPS]
        keys += [f"{a}/{chunk0_key(metas[a])}" for a in TRACK_SUBTABLES]
        records += get_all(client, TRACK, keys + large, out)
    finally:
        client.close()
    return write_receipts(
        out,
        TRACK,
        records,
        planned,
        TRACK_MAX_BYTES,
        started_utc,
        time.perf_counter() - started,
    )


if __name__ == "__main__":
    command, target = sys.argv[1], sys.argv[2]
    {"probe": probe, "fetch": fetch, "track": track}[command](target)
