"""identity.py TAG: criterion A of research/g3-spectral.md. Every FITS file of every run in G2's
reference set (D:/rang/outputs/20261106-g2-memory/runs/c34, binary 83baf9f) must have the same
SHA-256 under TAG."""

import sys
from pathlib import Path

REF = Path("/mnt/d/rang/outputs/20261106-g2-memory/runs/c34/img")
O = Path("/mnt/d/rang/outputs/20261106-g3-spectral/identity")


def sums(f):
    out = {}
    for line in f.read_text().splitlines():
        if line.strip():
            h, fn = line.split()
            out[fn.rsplit("-", 1)[-1]] = h
    return out


tag = sys.argv[1]
names = sys.argv[2:] or sorted(
    p.stem for p in REF.glob("*.sha256") if not p.stem.startswith("p512")
)
ok, checked = True, 0
for name in names:
    a = sums(REF / f"{name}.sha256")
    f = O / tag / "img" / f"{name}.sha256"
    if not f.exists():
        print(f"{name}: not run under {tag}")
        ok = False
        continue
    b = sums(f)
    same = a == b and len(a) == 5
    ok &= same
    checked += 1
    print(
        f"{name}: {'identical' if same else 'DIFFERENT ' + ','.join(k for k in a if a[k] != b.get(k))}"
    )
print(
    f"{checked} runs compared: {'all five files byte-identical' if ok and checked else 'RULE FAILS'}"
)
