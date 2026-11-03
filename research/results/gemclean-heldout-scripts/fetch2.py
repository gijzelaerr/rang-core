import hashlib, json, urllib.request
from pathlib import Path
B = "https://ratt-public-data.s3.af-south-1.amazonaws.com"
OUT = Path("/mnt/d/rang/data/eso137-pilot/gains")
R = "ESO137/ms1_gains.qc/GKB-net/GKB-net_0"
print((OUT/R/"gain_time/.zarray").read_text().replace("\n","").replace(" ",""))
print((OUT/R/"gain_freq/.zarray").read_text().replace("\n","").replace(" ",""))
keys = [f"{R}/gain_time/{i}" for i in (1,2)] + [f"{R}/gain_freq/{i}" for i in (2,3,4)]
man = json.loads((OUT/"manifest.json").read_text())
for k in keys:
    p = OUT/k
    with urllib.request.urlopen(f"{B}/{k}", timeout=60) as f: b = f.read()
    p.write_bytes(b)
    man["files"].append({"key": k, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()})
    man["bytes"] += len(b)
    print(k, len(b))
(OUT/"manifest.json").write_text(json.dumps(man, indent=1))
