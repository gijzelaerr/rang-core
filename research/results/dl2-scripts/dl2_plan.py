"""DL2 subset plan from metadata only (research/dl2-data.md section 3).

    python dl2_plan.py METADIR PLANDIR

For each METADIR/<cbid>.json writes PLANDIR/<cbid>.json: the split, every
calibrator scan and the middle three target scans (katdal indices), with
their dumps. A scan is used when its state is `track` with at least one
dump; calibrator when its target has a calibrator tag, else target when it
has `target`. Middle three: indices (n-3)//2 .. +2 of the target scans in
time order (lower middle for even n).
"""

import hashlib
import json
import sys
from pathlib import Path

CAL = {"bpcal", "fluxcal", "gaincal", "polcal", "delaycal", "phasecal"}
SPLIT = {
    "1678312253": "heldout",
    "1579022459": "heldout",
    "1674958551": "heldout",
    "1573212012": "validation",
    "1749428161": "train",
    "1629213076": "train",
    "1571938260": "train",
    "1735892129": "train",
    "1611426666": "train",
}


def plan(meta):
    track = [s for s in meta["scans"] if s["state"] == "track" and s["dumps"] > 0]
    cal = [s for s in track if CAL & set(s["tags"])]
    tgt = [s for s in track if s not in cal and "target" in s["tags"]]
    other = [s for s in track if s not in cal and s not in tgt]
    if other:
        raise SystemExit(f"unclassified track scans: {[s['scan'] for s in other]}")
    k = max(0, (len(tgt) - 3) // 2)
    mid = tgt[k : k + 3]
    sel = sorted(cal + mid, key=lambda s: s["scan"])
    return [
        {
            "scan": s["scan"],
            "class": "calibrator" if s in cal else "target",
            "target": s["target"],
            "tags": s["tags"],
            "dumps": s["dumps"],
        }
        for s in sel
    ]


def main(argv=None):
    metadir, plandir = (Path(x) for x in (argv or sys.argv[1:]))
    plandir.mkdir(parents=True, exist_ok=True)
    for f in sorted(metadir.glob("*.json")):
        meta = json.loads(f.read_text())
        cbid = f.stem
        scans = plan(meta)
        out = {
            "cbid": cbid,
            "split": SPLIT[cbid],
            "meta_sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
            "channels": meta["channels"],
            "antennas": len(meta["antennas"]),
            "dump_period_s": meta["dump_period_s"],
            "cross_products": meta["cross_products"],
            "scans": scans,
            "dumps": sum(s["dumps"] for s in scans),
        }
        out["mvf_bytes_estimate"] = (
            out["dumps"] * meta["cross_products"] * meta["channels"] * 10
        )
        (plandir / f"{cbid}.json").write_text(json.dumps(out, indent=1) + "\n")
        print(cbid, out["split"], len(scans), "scans", out["dumps"], "dumps",
              f"{out['mvf_bytes_estimate'] / 1e9:.0f} GB")  # fmt: skip


if __name__ == "__main__":
    sys.exit(main())
