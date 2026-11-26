"""#48 real-data scores and rule (research/weights-48.md sections 4-6).

    python w48_rule.py W48_DIR OUT.json

W48_DIR holds, per field F and arm a: F-a-img/image.json, F-a-n.json, F-a-weights.json, and on the
target F-a-lc/lightcurve.csv. I: per weighting, the 16 tile rms of the arm over the reference arm's
(raw, unity, calwt); tiles whose raw V peak exceeds 10x its rms are dropped from every arm. r = median
of the tile ratios; beats when r <= 0.99 and mean + 2 sem < 1; not worse when r <= 1.005.
S: sigma_snap = 1.4826 MAD over the control positions' snapshot fluxes (held-out dumps), SNR per
source = mean flux / sigma_snap.
"""

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

FIELDS = ("J1744-5144", "J0408-6545", "ASKAPJ1745")
HELD_OUT = ("J1744-5144", "J0408-6545")
ARMS = ("raw", "unity", "calwt", "rmad", "rclip")
REFS = ("raw", "unity", "calwt")


def load(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def tiles(d, field, arm, tag):
    img = load(d / f"{field}-{arm}-img" / "image.json")
    if not img or img["images"].get(tag, {}).get("rc") != 0:
        return None
    t = img["images"][tag]["tiles"]
    return np.array([x["rms"] for x in t]), np.array([x["peak_abs"] for x in t])


def lightcurve(d, field, arm):
    p = d / f"{field}-{arm}-lc" / "lightcurve.csv"
    if not p.exists():
        return None
    rows = list(csv.DictReader(open(p)))
    flux = {}
    for r in rows:
        try:
            v = float(r["flux_jy"])
        except (TypeError, ValueError):
            continue
        if math.isfinite(v):
            flux.setdefault(r["position"], []).append(v)
    ctrl = np.concatenate([np.array(v) for k, v in flux.items() if k.startswith("ctrl")])
    sig = float(1.4826 * np.median(np.abs(ctrl - np.median(ctrl))))
    snr = [float(np.mean(v)) / sig for k, v in flux.items() if k.startswith("src")]
    return {"sigma_snap_jy": sig, "snr_median": float(np.median(snr)), "points": int(ctrl.size)}


def main(d, out):
    d = Path(d)
    rec = {"I": {}, "N": {}, "S": {}, "weights": {}}
    for f in FIELDS:
        rec["N"][f] = {a: (load(d / f"{f}-{a}-n.json") or {}).get("e") for a in ARMS}
        rec["weights"][f] = {
            a: {k: (load(d / f"{f}-{a}-weights.json") or {}).get(k)
                for k in ("filled_blocks", "heldout_unflagged_cells_at_weight_0", "blocks_finite")}
            for a in ARMS
        }  # fmt: skip
        rec["I"][f] = {}
        for tag in ("natural", "briggs-0.5"):
            base = tiles(d, f, "raw", tag)
            if base is None:
                continue
            keep = base[1] <= 10 * base[0]
            r = {"tiles_kept": int(keep.sum()), "rms_uJy": {}}
            for a in ARMS:
                t = tiles(d, f, a, tag)
                if t is not None:
                    r["rms_uJy"][a] = float(np.median(t[0][keep]) * 1e6)
            for a in ("rmad", "rclip"):
                ta = tiles(d, f, a, tag)
                if ta is None:
                    continue
                for ref in REFS:
                    tr = tiles(d, f, ref, tag)
                    if tr is None:
                        continue
                    q = ta[0][keep] / tr[0][keep]
                    sem = float(np.std(q, ddof=1) / math.sqrt(q.size))
                    m = float(np.median(q))
                    r[f"{a}/{ref}"] = {"median": m, "mean": float(q.mean()), "sem": sem,
                                       "beats": bool(m <= 0.99 and q.mean() + 2 * sem < 1.0),
                                       "not_worse": bool(m <= 1.005)}  # fmt: skip
            rec["I"][f][tag] = r
        if f == "ASKAPJ1745":
            rec["S"] = {a: lightcurve(d, f, a) for a in ARMS}
    rule = {}
    for f in HELD_OUT:
        nat = rec["I"].get(f, {}).get("natural", {})
        rule[f] = {ref: nat.get(f"rclip/{ref}", {}) for ref in REFS}
    beats_all = all(rule[f].get(ref, {}).get("beats") for f in HELD_OUT for ref in ("raw", "unity"))
    nw_all = all(rule[f].get(ref, {}).get("not_worse") for f in HELD_OUT for ref in ("raw", "unity"))
    beats_one = any(rule[f].get(ref, {}).get("beats") for f in HELD_OUT for ref in ("raw", "unity"))
    worse_raw = [f for f in HELD_OUT if not rule[f].get("raw", {}).get("not_worse", False)]
    rec["rule"] = {
        "beats_raw_and_unity_everywhere": beats_all,
        "not_worse_everywhere_and_beats_one": nw_all and beats_one,
        "worse_than_raw_on": worse_raw,
        "outcome": "recommend" if beats_all else ("option" if nw_all and beats_one else
                                                  ("null on " + ",".join(worse_raw) if worse_raw
                                                   else "option, no gain")),
    }  # fmt: skip
    Path(out).write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
