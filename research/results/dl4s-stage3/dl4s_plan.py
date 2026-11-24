"""DL4s stage 3 (research/dl4s-screen.md 2.4): one block's scan selection and
configurations, from its dl2 block manifest (table descriptors only).

    python dl4s_plan.py MANIFEST.json E2N.yaml OUT_DIR

Writes OUT_DIR/scans.json (the merged scans: katdal index, source MS, field)
and OUT_DIR/off.yaml, OUT_DIR/on.yaml (E2-N's flag and calibrate sections,
field roles from the scan tags, polcal dropped, `k_zero_start` off / on).
"""

import json
import sys
from pathlib import Path

import yaml

FCAL, ALT = "J1939-6342", "J0408-6545"


def select(man):
    cal = [s for s in man["scans"] if s["class"] == "calibrator"]
    bp = {s["target"] for s in cal if "bpcal" in s["tags"]}
    prim = FCAL if FCAL in bp else (ALT if ALT in bp else None)
    if prim is None:
        raise SystemExit("no primary: neither J1939-6342 nor J0408-6545 is a bpcal")
    gcal = sorted({s["target"] for s in cal if "gaincal" in s["tags"]})
    use = [s for s in cal if s["target"] == prim or s["target"] in gcal]
    return prim, gcal, sorted(use, key=lambda s: s["scan"])


def config(e2n, prim, gcal, zero):
    c = {k: e2n[k] for k in ("schema", "version", "data", "flag")}
    c["fields"] = {"fcal": [prim], "bpcal": [prim], "gcal": gcal}
    cal = {k: v for k, v in e2n["calibrate"].items() if k != "polcal"}
    if prim != FCAL:
        cal["model"] = {"source": "unity"}  # 2.4: rang has no J0408-6545 model
    cal["k_zero_start"] = bool(zero)
    c["calibrate"] = cal
    c["run"] = {"stages": ["flag", "calibrate"]}
    return c


def main(manifest, e2n, out):
    man = json.loads(Path(manifest).read_text())
    e = yaml.safe_load(Path(e2n).read_text())
    prim, gcal, use = select(man)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    root = Path(manifest).resolve().parents[1]
    scans = {
        "block": man["cbid"],
        "split": man["split"], "primary": prim, "gcal": gcal,
        "scans": [{"scan": s["scan"], "target": s["target"], "tags": s["tags"],
                   "rows": s["rows"], "bytes": s["bytes"], "ms_hash": s["ms_hash"],
                   "ms": str(root / "ms" / man["cbid"] / s["ms"])}
                  for s in use],
    }  # fmt: skip
    (out / "scans.json").write_text(json.dumps(scans, indent=1))
    for name, zero in (("off", False), ("on", True)):
        (out / f"{name}.yaml").write_text(
            yaml.safe_dump(config(e, prim, gcal, zero), sort_keys=False)
        )
    print(prim, gcal, len(use), sum(s["rows"] for s in use))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
