"""identity.py TAG [NAME...]: criterion A of research/g5-multiscale.md.

G2's identity set (`20261106-g2-memory/runs/c34/img/<name>.sha256`, as G3 used it) and G3's
development runs D1-C1 and D1-C3 (`20261106-g3-spectral/runs/dev1`, every FITS file hashed here)
against the runs of TAG under `g5-20261107-02/identity/TAG`.
"""

import hashlib
import sys
from pathlib import Path

C34 = Path("/mnt/d/rang/outputs/20261106-g2-memory/runs/c34/img")
G3 = Path("/mnt/d/rang/outputs/20261106-g3-spectral/runs/dev1")
O = Path("/mnt/d/rang/outputs/g5-20261107-02/identity")


def sums(f, strip):
    out = {}
    for line in f.read_text().splitlines():
        if line.strip():
            h, fn = line.split()
            out[fn[len(strip) :]] = h
    return out


def reference(name):
    if name.startswith("D1-"):
        run = name.rsplit("-", 1)[0]
        out = {}
        for p in sorted((G3 / run).glob("g-*.fits")):
            out[p.name[2:]] = hashlib.sha256(p.read_bytes()).hexdigest()
        return out
    return sums(C34 / f"{name}.sha256", name + "-")


tag = sys.argv[1]
names = sys.argv[2:] or [
    f"{s}-{f}" for s in ("s1", "s2", "s3", "h1", "h2", "h3", "h4") for f in ("def", "coarse")
] + ["p256-def", "D1-C1-def", "D1-C3-def"]
ok, checked = True, 0
for name in names:
    f = O / tag / "img" / f"{name}.sha256"
    if not f.exists():
        print(f"{name}: not run under {tag}")
        ok = False
        continue
    a = reference(name)
    b = sums(f, name + "-")
    same = a == b and len(a) >= 5
    ok &= same
    checked += 1
    diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    print(f"{name}: {len(a)} files, " + ("identical" if same else "DIFFERENT " + ",".join(diff)))
print(f"{checked} runs compared: {'all files byte-identical' if ok and checked else 'RULE FAILS'}")
