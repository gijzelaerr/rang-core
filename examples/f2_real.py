"""F2 on real data (research/f2-flagger.md, sections 4-5): LUNO 1934-638 (whole
array) and 1830-211 agreement with T, injections on 1934-638, and the cost
measures C1 and C2.

Usage:
  python examples/f2_real.py agree OUT.json --net LABEL=W.npz ... [--set 1934|1830]
  python examples/f2_real.py time OUT.json --net F-SIM=W.npz [--repeats 3]
  python examples/f2_real.py rss OUT.json --arm T|net --net F-SIM=W.npz

OUT `RUN/x.json` means $RUN_DIR/x.json. `time` uses the rayon pool as set by
RAYON_NUM_THREADS (one process per thread count). `--set eso` is ESO137's
target chunk (target class; exploratory).
"""

import argparse
import json
import os
import resource
import time
from pathlib import Path

import numpy as np
from rang import core_campaign_1830 as l2
from rang import core_campaign_array as array
from rang import f2flag as ff
from rang.core_injection_model import make_injection
from scipy.ndimage import binary_dilation

MAIN = Path.home() / "Github/rang/outputs"
ROOTS_1934 = (
    MAIN / "luno-support-20261029-01/slice",
    MAIN / "luno-solve-20261029-02/inputs",
)
FETCH_1830 = MAIN / "l2-1830-20261030-01-fetch"
ESO = Path("/mnt/d/rang/data/eso137-pilot/ESO137/ms1_target.zarr")
ESO_TILES = (5, 6, 7, 8)  # the channel tiles on disk: 512 channels, 989.7-1096.6 MHz
MORPHOLOGIES = ("narrowband", "time-burst", "antenna-local", "single-baseline")
SEEDS = (19, 20, 21)
STRENGTH = 10.0


def _eso(name, chunk=None):
    """One decoded chunk of ESO137's zarr (examples/b1_identifiability.py)."""
    from rang import core

    meta = json.loads((ESO / name / ".zarray").read_text())
    key = chunk or ".".join("0" for _ in meta["shape"])
    raw = core.blosc_decode((ESO / name / key).read_bytes())
    full = np.frombuffer(raw, np.dtype(meta["dtype"])).reshape(meta["chunks"])
    index = [int(i) for i in key.split(".")]
    return full[
        tuple(
            slice(0, min(c, n - i * c))
            for c, n, i in zip(meta["chunks"], meta["shape"], index, strict=True)
        )
    ]


def load_eso():
    """ESO137 target, MAIN_0 row chunk 0, the four channel tiles on disk."""
    g = "MAIN/MAIN_0"
    a1 = _eso(f"{g}/ANTENNA1").astype(np.int32)
    a2 = _eso(f"{g}/ANTENNA2").astype(np.int32)
    keep = a1 != a2
    data = np.concatenate([_eso(f"{g}/DATA", f"0.{t}.0") for t in ESO_TILES], axis=1)
    flag = np.concatenate([_eso(f"{g}/FLAG", f"0.{t}.0") for t in ESO_TILES], axis=1)
    frow = _eso(f"{g}/FLAG_ROW")
    freq = _eso("SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ")[0]
    width = _eso("SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_WIDTH")[0]
    ch = np.concatenate([np.arange(t * 128, (t + 1) * 128) for t in ESO_TILES])
    flags = np.asarray(flag[keep], bool) | np.asarray(frow[keep], bool)[:, None, None]
    p, q = a1[keep], a2[keep]
    scan = {
        "data": np.ascontiguousarray(data[keep], np.complex64),
        "input_flags": np.ascontiguousarray(flags),
        "antenna1": np.ascontiguousarray(p),
        "antenna2": np.ascontiguousarray(q),
        "times": np.ascontiguousarray(_eso(f"{g}/TIME")[keep], np.float64),
        "antenna_position": _eso("ANTENNA/ANTENNA_0/POSITION").astype(np.float64),
        "chan_freq": np.ascontiguousarray(freq[ch], np.float64),
        "chan_width": np.ascontiguousarray(width[ch], np.float64),
        "corr_type": _eso("POLARIZATION/POLARIZATION_0/CORR_TYPE")[0].astype(np.int32),
        "field": "ESO137 (MAIN_0 row chunk 0)",
    }
    scan["nant"] = len(scan["antenna_position"])
    scan["eligible"] = ~flags.any(-1)
    scan["planes"] = ff.Planes(p, q, scan["times"])
    return scan


def load(which):
    if which == "eso":
        return load_eso()
    if which == "1934":
        arrays, rows, _ = array.decode_inputs(None, roots=ROOTS_1934)
        extra = array.decode_extra(rows, roots=ROOTS_1934)
    else:
        roots = (FETCH_1830 / "objects", *ROOTS_1934)
        arrays, rows, _ = l2.decode_inputs(l2.GROUP, roots)
        extra = l2.decode_extra(l2.GROUP, rows, roots)
    flags = (
        np.asarray(arrays["FLAG"], bool)
        | np.asarray(arrays["FLAG_ROW"], bool)[:, None, None]
    )
    p = np.ascontiguousarray(arrays["ANTENNA1"], np.int32)
    q = np.ascontiguousarray(arrays["ANTENNA2"], np.int32)
    scan = {
        "data": np.ascontiguousarray(arrays["DATA"], np.complex64),
        "input_flags": flags,
        "antenna1": p,
        "antenna2": q,
        "times": np.ascontiguousarray(arrays["TIME"], np.float64),
        "antenna_position": extra["antenna_position"],
        "chan_freq": extra["chan_freq"],
        "chan_width": extra["chan_width"],
        "corr_type": extra["corr_type"],
        "nant": len(extra["antenna_names"]),
        "field": extra["field_name"],
    }
    model = arrays.get("MODEL_DATA")
    weights = arrays.get("WEIGHT_SPECTRUM")
    if model is not None and weights is not None:
        scan["eligible"] = array.eligible_cells(
            np.asarray(arrays["FLAG"], bool),
            np.asarray(arrays["FLAG_ROW"], bool),
            scan["data"],
            weights,
            model,
            p,
            q,
        )
        scan["weights"] = np.ascontiguousarray(weights, np.float32)
    else:
        scan["eligible"] = ~flags.any(-1) & (p != q)[:, None]
    scan["planes"] = ff.Planes(p, q, scan["times"])
    return scan


def far_stratum(scan):
    """F1's far stratum: no input flag within 3 dumps and 8 channels."""
    planes = scan["planes"]
    flagged = planes.to_planes(scan["input_flags"].any(-1), True)
    s = np.zeros((1, 7, 17), bool)
    s[0] = True
    return planes.from_planes(~binary_dilation(flagged, s)) & scan["eligible"]


def arm_flags(scan, label, steps, weights, data=None):
    """Final (row, chan) flags of an arm on `data` (default: DATA)."""
    sc = dict(scan, data=scan["data"] if data is None else data)
    if label in ("T", "T-mild"):
        return ff.run_strategy(sc, steps[label], scan["input_flags"])[0]
    shared, _ = ff.run_strategy(sc, steps["shared"], scan["input_flags"])
    if label == "Z":
        planes = sc["planes"]
        vis = planes.to_planes(sc["data"], 0)
        fl = planes.to_planes(shared, True)
        z = np.zeros(fl.shape, bool)
        for b in range(0, planes.nbl, 64):
            z[b : b + 64] = ff.z_flags(ff.features(vis[b : b + 64], fl[b : b + 64])[1])
        return shared | planes.from_planes(z)
    if label == "shared":
        return shared
    return ff.network_flags(sc, shared, *weights[label])[0]


def per_baseline_noise(data, eligible, p, q):
    """F1's `per_baseline_noise` (examples/f1_saliency.py): real-component
    noise per row, scaled MAD of parallel-hand channel differences."""
    key = p.astype(np.int64) * (p.max() + q.max() + 2) + q
    sigma = np.zeros(len(p))
    for b in np.unique(key):
        rows = np.flatnonzero(key == b)
        both = eligible[rows, 1:] & eligible[rows, :-1]
        if not both.any():
            continue
        d = (data[rows, 1:][..., [0, 3]] - data[rows, :-1][..., [0, 3]])[both]
        v = np.concatenate([d.real.ravel(), d.imag.ravel()])
        sigma[rows] = 1.4826 * np.median(np.abs(v - np.median(v))) / np.sqrt(2)
    return sigma


def inject(scan, state, morphology, seed):
    """F1's `inject_mask` (examples/f1_saliency.py) on eligible cells:
    (rows, channels, unit phasors)."""
    train = state["train"]
    if morphology in ("narrowband", "time-burst", "antenna-local"):
        mask, delta, _ = make_injection(state, morphology, 1.0, seed)
        rows, channels = np.nonzero(mask)
        phasor = delta[rows, channels, 0] * np.sqrt(state["weights"][rows, channels, 0])
        return rows, channels, np.asarray(phasor, np.complex128)
    rng = np.random.default_rng(seed)
    p, q = state["antenna1"], state["antenna2"]
    key = p.astype(np.int64) * (p.max() + q.max() + 2) + q
    baselines, inverse = np.unique(key, return_inverse=True)
    occupancy = np.bincount(inverse, train.mean(axis=1)) / np.bincount(inverse)
    chosen = rng.choice(baselines[occupancy >= np.median(occupancy)])
    support = key == chosen
    per_channel = train[support].mean(axis=0)
    width = np.convolve(per_channel, np.ones(8) / 8, mode="valid")
    first = int(rng.choice(np.flatnonzero(width >= 0.5)))
    mask = np.zeros(train.shape, bool)
    mask[np.ix_(support, np.arange(first, first + 8))] = True
    mask &= train
    rows, channels = np.nonzero(mask)
    phase = rng.uniform(-np.pi, np.pi) + rng.normal(0, 0.15, len(rows))
    return rows, channels, np.exp(1j * phase)


def nets(args):
    items = dict(item.split("=", 1) for item in args.net)
    return {k: ff.load_net(v) for k, v in items.items()}, items


def steps_for(klass="calibrator"):
    out = {
        "T": ff.strategy(ff.STRATEGIES[klass]),
        "shared": ff.shared_strategy(klass),
    }
    if klass == "calibrator":
        out["T-mild"] = ff.strategy(ff.MILD)
    return out


def agree(args, out):
    weights, paths = nets(args)
    klass = "target" if args.set == "eso" else "calibrator"
    steps = steps_for(klass)
    scan = load(args.set)
    far = far_stratum(scan)
    elig = scan["eligible"]
    result = {
        "set": args.set,
        "field": scan["field"],
        "rows": len(scan["times"]),
        "input_flagged": float(scan["input_flags"].any(-1).mean()),
        "eligible": int(elig.sum()),
        "far": int(far.sum()),
        "far_fraction": float(far.sum() / max(elig.sum(), 1)),
        "nets": paths,
        "arms": {},
    }
    labels = ["T", *(["T-mild"] if klass == "calibrator" else []), "Z", *weights]
    # Post hoc (research/f2-flagger.md, section 9): T's first uvcontsub step
    # discards the whole-band static mask, the shared wrapper keeps it, so
    # the arms are also compared on the cells the wrapper leaves unflagged.
    scored = elig & ~arm_flags(scan, "shared", steps, weights)
    result["scored"] = int(scored.sum())
    added = {}
    for label in labels:
        t = time.perf_counter()
        f = arm_flags(scan, label, steps, weights)
        added[label] = f & elig
        result["arms"][label] = {
            "added": int(added[label].sum()),
            "added_far": int((added[label] & far).sum()),
            "seconds_not_timing": time.perf_counter() - t,
        }
    for label in labels:
        if label == "T":
            continue
        result["arms"][label]["J_all"] = ff.jaccard(added[label], added["T"])
        result["arms"][label]["J_far"] = ff.jaccard(
            added[label] & far, added["T"] & far
        )
        result["arms"][label]["J_scored_posthoc"] = ff.jaccard(
            added[label] & scored, added["T"] & scored
        )
        result["arms"][label]["J_scored_far_posthoc"] = ff.jaccard(
            added[label] & scored & far, added["T"] & scored & far
        )
    for label in labels:
        result["arms"][label]["added_scored"] = int((added[label] & scored).sum())
        result["arms"][label]["added_scored_far"] = int(
            (added[label] & scored & far).sum()
        )
    print(json.dumps(result["arms"], indent=1), flush=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    if args.set == "1934" and not args.no_inject:
        state = {
            "data": scan["data"],
            "train": elig,
            "validation": np.zeros_like(elig),
            "test": np.zeros_like(elig),
            "original_flags": scan["input_flags"],
            "original_rows": scan["input_flags"].all(axis=(1, 2)),
            "antenna1": scan["antenna1"],
            "antenna2": scan["antenna2"],
            "times": scan["times"],
            "weights": scan["weights"],
            "window": np.ones(elig.shape[1], bool),
        }
        sigma = per_baseline_noise(
            scan["data"], elig, scan["antenna1"], scan["antenna2"]
        )
        inj = {label: [0, 0] for label in ["T", "Z", *weights]}
        cases = []
        for morphology in MORPHOLOGIES:
            for seed in SEEDS:
                rows, chans, phasor = inject(scan, state, morphology, seed)
                data = scan["data"].copy()
                data[rows, chans, :] += (STRENGTH * sigma[rows] * phasor)[
                    :, None
                ].astype(np.complex64)
                shared = arm_flags(scan, "shared", steps, weights, data)
                scored = ~shared[rows, chans]
                case = {"morphology": morphology, "seed": seed, "cells": len(rows)}
                for label, tally in inj.items():
                    f = arm_flags(scan, label, steps, weights, data)[rows, chans]
                    hit = int((f & scored).sum())
                    tally[0] += hit
                    tally[1] += int(scored.sum())
                    case[label] = hit / max(int(scored.sum()), 1)
                cases.append(case)
                print(json.dumps(case), flush=True)
        result["injections"] = {
            "strength": STRENGTH,
            "cases": cases,
            "recall": {k: v[0] / max(v[1], 1) for k, v in inj.items()},
            "n": {k: v[1] for k, v in inj.items()},
        }
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")


def timing(args, out):
    weights, paths = nets(args)
    klass = "target" if args.set == "eso" else "calibrator"
    steps = steps_for(klass)
    scan = load(args.set)
    label = next(iter(weights))
    records = {"T": [], label: []}
    for k in range(args.repeats):
        for arm in ("T", label) if k % 2 == 0 else (label, "T"):
            load1 = os.getloadavg()[0]
            t = time.perf_counter()
            f = arm_flags(scan, arm, steps, weights)
            records[arm].append(
                {
                    "wall": time.perf_counter() - t,
                    "load1": load1,
                    "flagged": float(f.mean()),
                }
            )
            print(arm, json.dumps(records[arm][-1]), flush=True)
    med = {a: float(np.median([r["wall"] for r in v])) for a, v in records.items()}
    result = {
        "set": args.set,
        "threads": os.environ.get("RAYON_NUM_THREADS"),
        "nets": paths,
        "rows": len(scan["times"]),
        "cells": int(scan["data"].shape[0] * scan["data"].shape[1]),
        "records": records,
        "median_wall": med,
        "c1": med[label] / med["T"],
        "max_load1": max(r["load1"] for v in records.values() for r in v),
    }
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("median_wall", "c1", "max_load1")}))


def rss(args, out):
    weights, paths = nets(args)
    klass = "target" if args.set == "eso" else "calibrator"
    steps = steps_for(klass)
    scan = load(args.set)
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    label = "T" if args.arm == "T" else next(iter(weights))
    t = time.perf_counter()
    arm_flags(scan, label, steps, weights)
    wall = time.perf_counter() - t
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = {
        "arm": label,
        "peak_rss_kb_after_decode": before,
        "peak_rss_kb": after,
        "wall": wall,
        "nets": paths,
    }
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("agree", "time", "rss"))
    parser.add_argument("out")
    parser.add_argument("--net", action="append", default=[])
    parser.add_argument("--set", default="1934", choices=("1934", "1830", "eso"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--arm", default="T")
    parser.add_argument("--no-inject", action="store_true")
    args = parser.parse_args()
    out = args.out
    if out.startswith("RUN/"):
        out = Path(os.environ["RUN_DIR"]) / out[4:]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    {"agree": agree, "time": timing, "rss": rss}[args.mode](args, out)


if __name__ == "__main__":
    main()
