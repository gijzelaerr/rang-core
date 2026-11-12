# SPDX-License-Identifier: GPL-3.0-or-later
"""Archive CASA's listobs output on the public fixture (research/v8a-listobs.md).

Usage: archive_listobs.py CASA_DIR OUT.json NAME [NAME ...]

Keeps, per NAME, CASA's returned record, the msmetadata supplement with each
spectral window's channel frequencies and widths replaced by the SHA-256 of
their little-endian float64 bytes (and the count), and the listfile text, so
`tests/test_v8a_listobs.py` compares rang with CASA on the fixture without
CASA. Only the public fixture belongs in the archive.
"""

import json
import sys
from pathlib import Path

from rang.oracles.casa_listobs import channels_sha256


def main(argv):
    casa_dir, out = Path(argv[0]), Path(argv[1])
    if out.exists():
        raise SystemExit(f"{out} exists; choose a fresh file")
    meta = json.loads((casa_dir / "meta.json").read_text(encoding="utf-8"))
    archive = {
        "schema": "rang.v8a-listobs-casa",
        "version": 1,
        "oracle": f"CASA casatasks {meta['casatasks']} listobs, image "
        + (casa_dir / "image.txt").read_text(encoding="utf-8").strip(),
        "source_run": casa_dir.name,
        "runs": {},
    }
    for name in argv[2:]:
        msmd = json.loads((casa_dir / f"{name}.msmd.json").read_text(encoding="utf-8"))
        for spw in msmd.get("spws", []):
            for key in ("chanfreqs", "chanwidths"):
                values = spw.pop(key)
                spw[f"{key}_sha256"] = channels_sha256(values)
                spw[f"{key}_count"] = len(values)
        archive["runs"][name] = {
            "record": json.loads(
                (casa_dir / f"{name}.json").read_text(encoding="utf-8")
            ),
            "msmd": msmd,
            "text": (casa_dir / f"{name}.txt").read_text(encoding="utf-8"),
        }
    out.write_text(json.dumps(archive, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main(sys.argv[1:])
