"""Issue #23 step 4's default control: are two runs' FITS images bit-identical?

    python same_fits.py NEW_DIR OLD_DIR OUT.json

Compares the data of every `*-model.fits` (and the MFS residual) present in
both directories, ignoring header cards (dates, the binary's path).
"""

import hashlib
import json
import sys
from pathlib import Path


def data_digest(path):
    raw = path.read_bytes()
    # FITS headers are 2880-byte blocks ending with the END card.
    i = 0
    while True:
        block = raw[i : i + 2880]
        i += 2880
        cards = [block[k : k + 80] for k in range(0, 2880, 80)]
        if any(c.startswith(b"END") and c[3:].strip() == b"" for c in cards):
            break
    return hashlib.sha256(raw[i:]).hexdigest()


def main():
    new, old, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    names = sorted(
        p.name
        for p in new.glob("*.fits")
        if (p.name.endswith("-model.fits") or p.name.endswith("MFS-residual.fits"))
        and (old / p.name).exists()
    )
    diff = [n for n in names if data_digest(new / n) != data_digest(old / n)]
    rec = {"new": str(new), "old": str(old), "compared": len(names), "differ": diff}
    rec["identical"] = bool(names) and not diff
    out.write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))
    sys.exit(0 if rec["identical"] else 1)


if __name__ == "__main__":
    main()
