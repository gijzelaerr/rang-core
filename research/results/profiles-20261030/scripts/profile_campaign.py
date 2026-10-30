"""Offline profile of the task K campaign chain (simplification review S1).

Usage: python profile_campaign.py <fetched-dir> outputs/<fresh> [--baselines N]
       [--channels N] [--images ARM,ARM] [--no-tv]

Replays the stages of rangtoy.core_campaign.run after the fetch, on the
archived fetched bytes of task K run -01 (read-only), with every kernel
wrapper timed (wall, process CPU, peak RSS). No code of the repository is
edited; wrappers are patched on module attributes in this process only.
With no subset options the gains and dirty-image hashes are compared with
the archived run's result.json.
"""

import argparse
import functools
import json
import resource
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from rangtoy import core, core_campaign, core_flag, core_grid, core_weights
from rangtoy import core_fetch, core_workflow, flagging

CALLS = defaultdict(lambda: {"calls": 0, "wall": 0.0, "cpu": 0.0})


def cpu():
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def timed(module, name, label=None):
    fn = getattr(module, name)
    label = label or f"{module.__name__.split('.')[-1]}.{name}"

    @functools.wraps(fn)
    def wrapper(*a, **k):
        w, c = time.perf_counter(), cpu()
        try:
            return fn(*a, **k)
        finally:
            rec = CALLS[label]
            rec["calls"] += 1
            rec["wall"] += time.perf_counter() - w
            rec["cpu"] += cpu() - c

    setattr(module, name, wrapper)


for mod, names in (
    (core, ["solve_complex", "fused_pass", "blosc_decode"]),
    (core_flag, ["flag_rows"]),
    (core_grid, ["invert", "stokes_i_reader", "write_fits"]),
    (core_weights, ["imaging_weights"]),
    (core_campaign, ["apply_gains", "residual_features", "policy_mask",
                     "protected_flags", "split_holdout", "array_sha256"]),
    (core_workflow, ["gain_tv", "polar_gauge"]),
    (flagging, ["gain_tv"]),
    (core_fetch.core_zarr, ["decode_span_rows"]),
):
    for n in names:
        if hasattr(mod, n):
            timed(mod, n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fetched")
    ap.add_argument("out")
    ap.add_argument("--baselines", type=int, default=6)
    ap.add_argument("--channels", type=int, default=2048)
    ap.add_argument("--images", default="original,tricolour-firstpass")
    ap.add_argument("--no-tv", action="store_true")
    ap.add_argument("--no-reference", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    stages = {}
    load = [open("/proc/loadavg").read().split()[:3]]

    def stage(name, w, c):
        stages[name] = {
            "wall": time.perf_counter() - w,
            "cpu": cpu() - c,
            "max_rss_mb": rss_mb(),
        }
        stages[name]["cores_busy"] = stages[name]["cpu"] / max(stages[name]["wall"], 1e-9)

    w0, c0 = time.perf_counter(), cpu()
    core.library()
    w, c = time.perf_counter(), cpu()
    arrays, _ = core_fetch.decode_slice(args.fetched)
    rows = np.asarray(json.loads((Path(args.fetched) / "result.json").read_text())["rows"])
    extra = core_campaign.decode_extra(args.fetched, rows)
    stage("decode", w, c)
    # Subsets (scaling probes): first N baselines, first N channels.
    pairs = sorted({(int(p), int(q)) for p, q in zip(arrays["ANTENNA1"], arrays["ANTENNA2"])})
    keep_pairs = set(pairs[: args.baselines])
    sel = np.array([(int(p), int(q)) in keep_pairs for p, q in zip(arrays["ANTENNA1"], arrays["ANTENNA2"])])
    nchan = args.channels
    subset = args.baselines != 6 or nchan != 2048
    if subset:
        arrays = {k: (v[sel][:, :nchan] if v.ndim == 3 else v[sel]) for k, v in arrays.items()}
        extra = dict(extra)
        extra["uvw"] = extra["uvw"][sel]
        extra["chan_freq"] = extra["chan_freq"][:nchan]
        extra["chan_width"] = extra["chan_width"][:nchan]
    if not args.no_reference and not subset:
        w, c = time.perf_counter(), cpu()
        core_campaign.section6_summary(arrays)
        stage("section6_reference", w, c)
    w, c = time.perf_counter(), cpu()
    state = core_campaign.build_state(arrays, extra)
    stage("split", w, c)
    w, c = time.perf_counter(), cpu()
    original = core_campaign.solve_arm(state, np.zeros_like(state["train"]), "original")
    stage("solve_original", w, c)
    scale0 = original["metrics"]["scale"]
    solves = {"original": original}
    for label, strategy in core_campaign.STRATEGIES.items():
        w, c = time.perf_counter(), cpu()
        additions, _ = core_campaign.tricolour_arm(state, extra, core_campaign.STRATEGY_DIR / strategy)
        stage(f"flag_{label}", w, c)
        w, c = time.perf_counter(), cpu()
        solves[label] = core_campaign.solve_arm(state, additions, label, scale=scale0)
        stage(f"solve_{label}", w, c)
    if not args.no_tv:
        w, c = time.perf_counter(), cpu()
        trials, best, _ = core_campaign.tv_loop(state, original, scale0, "tv")
        stage("tv_loop", w, c)
        stages["tv_loop"]["solves"] = sum(1 for t in trials if "losses" in t)
    images = {}
    for label in [x for x in args.images.split(",") if x]:
        w, c = time.perf_counter(), cpu()
        images[label] = core_campaign.image_arm(state, extra, solves[label], out / "images", label)
        stage(f"image_{label}", w, c)
    total = {"wall": time.perf_counter() - w0, "cpu": cpu() - c0, "max_rss_mb": rss_mb()}
    load.append(open("/proc/loadavg").read().split()[:3])
    equality = None
    if not subset:
        archived = json.loads(Path(args.fetched).parent.joinpath("result.json").read_text())["arms"]
        equality = {}
        for label, s in solves.items():
            equality[f"gains_{label}"] = core_campaign.array_sha256(s["diagnostics"]["gains"]) == archived[label]["gains_sha256"]
        for label, m in images.items():
            equality[f"dirty_{label}"] = m["dirty_sha256"] == archived[label]["image"]["dirty_sha256"]
            equality[f"psf_{label}"] = m["psf_sha256"] == archived[label]["image"]["psf_sha256"]
    sizes = {k: [list(v.shape), str(v.dtype), v.nbytes] for k, v in arrays.items()}
    result = {
        "args": vars(args),
        "rows": int(state["data"].shape[0]),
        "channels": int(state["data"].shape[1]),
        "array_bytes": sizes,
        "stages": stages,
        "calls": dict(CALLS),
        "total": total,
        "loadavg_before_after": load,
        "backend": core.backend_name(),
        "equality_with_archive": equality,
        "image_seconds": {k: v["seconds"] for k, v in images.items()},
    }
    (out / "profile.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({"total": total, "equality": equality}, indent=1))


if __name__ == "__main__":
    main()
