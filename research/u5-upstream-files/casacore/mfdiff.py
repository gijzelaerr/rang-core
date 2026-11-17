# ruff: noqa  (one-off upstream reproduction probe)
"""Locate differing bytes of two table.mf files by block; print header size and block size."""

import re
import struct
import sys

a, b = (open(p, "rb").read() for p in sys.argv[1:3])
hdr = struct.unpack(">q", a[32:40])[0]
bs = struct.unpack(">q", a[40:48])[0]
print("header size", hdr, "block size", bs, "file", len(a))
diff = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
blocks = {}
for i in diff:
    blocks.setdefault(i // bs, []).append(i % bs)
for k, v in sorted(blocks.items()):
    print("block", k, "ndiff", len(v), "first", v[0], "last", v[-1])
    seg = a[k * bs + v[0] : k * bs + v[-1] + 1]
    s = [m.decode() for m in re.findall(rb"[ -~]{6,}", seg)][:6]
    print("   printable runs in file 1:", s)
