"""identity.py TAG [REF]: the class-A image rule. Every FITS file of every run of REF (default base)
must have the same SHA-256 under TAG. Prints one line per run and the verdict; also the peak RSS
of both (GNU time -v), in GB."""
import sys
from pathlib import Path

O = Path("/mnt/d/rang/outputs/20261106-g2-memory")
tag = sys.argv[1]
ref = sys.argv[2] if len(sys.argv) > 2 else "base"


def sums(t, name):
    f = O / "runs" / t / "img" / f"{name}.sha256"
    if not f.exists():
        return None
    out = {}
    for line in f.read_text().split("\n"):
        if line.strip():
            h, fn = line.split()
            out[fn.split("-", 2)[-1]] = h
    return out


def rss(t, name):
    f = O / "runs" / t / "time" / f"{name}.txt"
    if not f.exists():
        return float("nan")
    for line in f.read_text().splitlines():
        if "Maximum resident" in line:
            return int(line.split(":")[1]) * 1024 / 1e9
    return float("nan")


ok = True
checked = 0
for f in sorted((O / "runs" / ref / "img").glob("*.sha256")):
    name = f.stem
    a, b = sums(ref, name), sums(tag, name)
    if not a or len(a) != 5:
        continue
    if b is None:
        print(f"{name}: not run under {tag}")
        continue
    same = a == b
    ok &= same
    checked += 1
    diff = [k for k in a if a.get(k) != b.get(k)]
    print(f"{name}: {'identical' if same else 'DIFFERENT ' + ','.join(diff)}; "
          f"peak RSS {ref} {rss(ref, name):.3f} GB, {tag} {rss(tag, name):.3f} GB")
print(f"{checked} runs compared: {'all five files byte-identical' if ok else 'RULE FAILS'}")
