"""DL2 stage manifests (research/dl2-data.md section 7).

    python dl2_stage.py ROOT

Writes ROOT/manifests/stage1.json, stage2.json and stage7.json from the
block manifests and the labels present, and prints one line per stage.
- stage 1 (flag): every converted scan; labels of the flag teachers;
- stage 2 (K, G, B solve): the calibrator scans; solution tables when
  their runner has written them (none yet: the entry lists no labels);
- stage 7 (minor cycle): the target scans; deep models when written.
Splits are by capture block. Held-out and validation entries are
registered by MS hash; for held-out blocks no label is listed even if one
exists (they are read once, at the stage's own read). The augmentation
recipe is the same for every stage, with its own root seed.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

TEACHERS = {"1": ["rang", "tricolour", "aoflagger"], "2": [], "7": []}
CLASSES = {"1": {"calibrator", "target"}, "2": {"calibrator"}, "7": {"target"}}
AUGMENT = {
    "subarray_size": "uniform integer in [4, antennas of the block]",
    "layout": "half uniform random subsets; half radius-limited: the N antennas nearest the array centre",
    "dropout": "on full-array samples only: remove 1, 4 or 8 antennas, equally likely",
    "seed_rule": "sample k uses numpy.random.default_rng([root_seed, k])",
    "recorded_per_sample": ["cbid", "scan", "antennas_kept", "k"],
    "no_ms_written": True,
}


def root_seed(stage):
    return int(hashlib.sha256(f"rang dl2 stage {stage}".encode()).hexdigest()[:8], 16)


def label_entry(root, teacher, cbid, scan):
    d = root / "labels" / teacher / cbid / f"scan{scan:03d}"
    if not (d / "SHA256SUMS").exists():
        return None
    sums = (d / "SHA256SUMS").read_bytes()
    info = json.loads((d / "label.json").read_text())
    return {
        "teacher": teacher,
        "path": str(d.relative_to(root)),
        "sha256sums_sha256": hashlib.sha256(sums).hexdigest(),
        "pins": info["pins"],
        "strategy_sha256": info["strategy_sha256"],
    }


def main(argv=None):
    root = Path((argv or sys.argv[1:])[0]).resolve()
    blocks = []
    for f in sorted((root / "manifests").glob("[0-9]*.json")):
        blocks.append((f, json.loads(f.read_text())))
    for stage in ("1", "2", "7"):
        entries, counts = [], {}
        for f, b in blocks:
            for s in b["scans"]:
                if s["class"] not in CLASSES[stage] or "ms_hash" not in s:
                    continue
                e = {
                    "cbid": b["cbid"], "split": b["split"], "scan": s["scan"],
                    "class": s["class"], "target": s["target"], "rows": s["rows"],
                    "ms": f"ms/{b['cbid']}/{s['ms']}", "ms_hash": s["ms_hash"],
                    "labels": [],
                }  # fmt: skip
                if b["split"] != "heldout":
                    for te in TEACHERS[stage]:
                        lab = label_entry(root, te, b["cbid"], s["scan"])
                        if lab:
                            e["labels"].append(lab)
                entries.append(e)
                counts[b["split"]] = counts.get(b["split"], 0) + 1
        blocks_by_split = {}
        for _, b in blocks:
            blocks_by_split.setdefault(b["split"], []).append(
                {"cbid": b["cbid"], "complete": b["complete"],
                 "manifest_sha256": hashlib.sha256(
                     (root / "manifests" / f"{b['cbid']}.json").read_bytes()).hexdigest()}
            )  # fmt: skip
        out = {
            "stage": stage,
            "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "note": "research/dl2-data.md section 7",
            "split_rule": "by capture block (dl-plan decision 6); held out read once",
            "blocks": blocks_by_split,
            "augmentation": {**AUGMENT, "root_seed": root_seed(stage)},
            "entries": entries,
        }
        (root / "manifests" / f"stage{stage}.json").write_text(
            json.dumps(out, indent=1) + "\n"
        )
        labelled = sum(1 for e in entries if e["labels"])
        print(f"stage {stage}: {len(entries)} scans {counts}, {labelled} with labels")
    return 0


if __name__ == "__main__":
    sys.exit(main())
