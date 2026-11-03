"""Fetch the numeric part of ms1_gains.qc for scan 2, channels 640:1152."""
import hashlib, json, time, urllib.request, sys
from pathlib import Path
B = "https://ratt-public-data.s3.af-south-1.amazonaws.com"
OUT = Path("/mnt/d/rang/data/eso137-pilot/gains")
LIMIT = 3_000_000_000
R = "ESO137/ms1_gains.qc"
keys = [f"{R}/.zgroup"]
for t, n in (("GKB-net", "GKB-net_0"), ("G", "G_0"), ("K", "K_0"), ("B", "B_0")):
    keys += [f"{R}/{t}/{n}/.zattrs", f"{R}/{t}/{n}/.zgroup"]
    for a in ("gain_time", "gain_freq"):
        keys += [f"{R}/{t}/{n}/{a}/.zarray", f"{R}/{t}/{n}/{a}/.zattrs", f"{R}/{t}/{n}/{a}/0"]
    keys += [f"{R}/{t}/{n}/gains/.zarray", f"{R}/{t}/{n}/gains/.zattrs", f"{R}/{t}/{n}/gain_flags/.zarray", f"{R}/{t}/{n}/gain_flags/.zattrs"]
for tt in range(3):
    for f in (2, 3, 4):
        keys += [f"{R}/GKB-net/GKB-net_0/gains/{tt}.{f}.0.0.0", f"{R}/GKB-net/GKB-net_0/gain_flags/{tt}.{f}.0.0"]
# The separate terms, kept for diagnostics: small except K's expanded gains (not fetched)
for f in range(16):
    pass
keys += [f"{R}/G/G_0/gains/{t}.0.0.0.0" for t in range(3)]
keys += [f"{R}/G/G_0/gain_flags/{t}.0.0.0" for t in range(3)]
keys += [f"{R}/K/K_0/params/.zarray", f"{R}/K/K_0/params/.zattrs"] + [f"{R}/K/K_0/params/{t}.0.0.0.0" for t in range(3)]
keys += [f"{R}/B/B_0/gains/{t}.0.0.0.0" for t in range(3)]
sizes = {}
for k in keys:
    q = urllib.request.Request(f"{B}/{k}", method="HEAD")
    try:
        with urllib.request.urlopen(q, timeout=40) as f:
            sizes[k] = int(f.headers["Content-Length"])
    except Exception as e:
        print("missing", k, e); sizes[k] = None
keys = [k for k in keys if sizes[k] is not None]
tot = sum(sizes[k] for k in keys)
print("objects", len(keys), "bytes", tot, flush=True)
if tot > LIMIT:
    sys.exit("over the limit")
rec = {"source": B, "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
       "licence": "CC BY 4.0; cite Ramatsoku et al. 2020, A&A 636, L1",
       "purpose": "QuartiCal GKB-net gains of scan 2 (MAIN_0), channels 640:1152 (freq chunks 2-4 of 256), research/gemclean-heldout.md",
       "files": []}
t0 = time.time()
for k in keys:
    p = OUT / k
    p.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    with urllib.request.urlopen(f"{B}/{k}", timeout=300) as f, open(p, "wb") as o:
        while True:
            b = f.read(1 << 20)
            if not b: break
            h.update(b); o.write(b)
    if p.stat().st_size != sizes[k]: sys.exit("size mismatch " + k)
    rec["files"].append({"key": k, "bytes": sizes[k], "sha256": h.hexdigest()})
rec["seconds"] = time.time() - t0
rec["bytes"] = tot
(OUT / "manifest.json").write_text(json.dumps(rec, indent=1))
print("done", tot, rec["seconds"])
