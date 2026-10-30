"""Post-hoc re-imaging of the L1, L2, L1-M and C1 archives with the exact
gridder (big-plan task DF2c, research/df2c-campaign-gridder.md).

    python examples/reimage_df2c.py chunk0 OUT_DIR [--archives ...] [--arms ...] [--gridders wstack wgrid]
    python examples/reimage_df2c.py l2 OUT_DIR [--archives ...] [--arms ...] [--gridders wstack wgrid]
    python examples/reimage_df2c.py default BASE.json AFTER.json OUT.json
    python examples/reimage_df2c.py summary OUT.json REIMAGE.json... [--default DEFAULT.json]

`chunk0` rebuilds the state of LUNO row chunk 0 (L1, L1-M and C1 share it)
and `l2` the PKS 1830 state (L2) by the drivers' own functions, from the
local tiles and L2's fetch (both checked against their receipts). For each
archived arm it loads the run's saved gains and additions (SHA256 checked
against the archive) and images them through the driver's own
`core_campaign_array.image_arm`: first with the archived settings
(`wstack`, the archived channel groups: the reconstruction gate), then with
`gridder="wgrid"` in one call. No solve, flagger or TV loop is repeated.
Metrics are recomputed with the archive's boxes and its recorded model flux
(the L1-M model arms replace the model, which only enters the flux
recovery). Arms with equal gains and additions are imaged once per state.
Every residual-RMS call recorded in the archive (hypotheses, amendment 1,
C1's pairs) is recomputed from the wgrid residual RMS. Nothing archived is
read for writing; everything goes to OUT_DIR.
"""

import argparse
import hashlib
import json
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
ARCHIVES = {
    "l1": ("chunk0", OUTPUTS / "luno-array-campaign-20261030-01"),
    "l1m-stored": ("chunk0", OUTPUTS / "l1m-20261030-01-stored"),
    "l1m-point": ("chunk0", OUTPUTS / "l1m-20261030-02b-point"),
    "l1m-field": ("chunk0", OUTPUTS / "l1m-20261030-03-field"),
    "c1": ("chunk0", OUTPUTS / "c1-20261030-01"),
    "l2-stored": ("l2", OUTPUTS / "l2-1830-20261030-02-stored"),
    "l2-scalar": ("l2", OUTPUTS / "l2-1830-20261030-02-scalar"),
}
L2_FETCH = OUTPUTS / "l2-1830-20261030-01-fetch"
METRIC_TOLERANCE = 1e-9  # PC1's / P2's relative tolerance on image numbers
F32_QUANTUM = 2.0**-23  # one float32 ulp at the peak (FITS are float32)
GATED_METRICS = ("peak_jy_per_beam", "residual_rms", "offsource_rms")
REPORTED_METRICS = (
    "peak_jy_per_beam",
    "peak_pixel",
    "residual_rms",
    "residual_rms_offsource",
    "offsource_rms",
    "offsource_robust_sigma",
    "residual_robust_sigma_offsource",
    "residual_max_abs",
    "psf_max_sidelobe",
    "psf_max_far",
    "flux_recovery",
)


def maxrss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")


def read_json(path):
    return json.loads(Path(path).read_text())


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_fits_image(path):
    from astropy.io import fits

    with fits.open(path) as hdul:
        return hdul[0].data[0, 0].astype(np.float64)


def diff_record(candidate, reference, kind, border=2):
    """DF2b's terms: L-infinity of `candidate - reference` over the reference
    peak (dirty) or absolute (PSF, peak one), over the whole image, the
    outer `border` pixels (the edge) and the central half."""
    candidate = np.asarray(candidate, np.float64)
    reference = np.asarray(reference, np.float64)
    peak = float(np.abs(reference).max())
    scale = peak if kind == "dirty" else 1.0
    d = candidate - reference
    h, w = d.shape
    edge = np.zeros((h, w), bool)
    edge[:border] = edge[-border:] = True
    edge[:, :border] = edge[:, -border:] = True
    centre = d[h // 4 : h - h // 4, w // 4 : w - w // 4]
    return {
        "linf_over_peak": float(np.abs(d).max() / scale),
        "edge_linf_over_peak": float(np.abs(d[edge]).max() / scale),
        "central_half_linf_over_peak": float(np.abs(centre).max() / scale),
        "rms_over_peak": float(np.sqrt(np.mean(d**2)) / scale),
        "reference_peak": peak,
        "differing_pixels": int(np.count_nonzero(d)),
    }


# --- archives ------------------------------------------------------------------


def archived_arms(name):
    """label -> archived arm record (L1's arms, plus C1's two new arms)."""
    run = ARCHIVES[name][1]
    result = read_json(run / "result.json")
    arms = dict(result["arms"])
    if name == "c1":
        arms.update(read_json(run / "c1.json")["arms"])
    return result, arms


def load_solve(run, label, arm):
    from rang import core_campaign

    with np.load(run / "gains" / f"{label}.npz") as g:
        gains, valid = g["gains"], g["gain_valid"]
    with np.load(run / "flags" / f"{label}.npz") as f:
        added = f["additions"]
    checks = {
        "gains_sha256": core_campaign.array_sha256(gains) == arm["gains_sha256"],
        "additions_sha256": core_campaign.array_sha256(added)
        == arm["additions_sha256"],
        "additions_dense": bool(added.dtype == bool),
    }
    if not (checks["gains_sha256"] and checks["additions_sha256"]):
        raise RuntimeError(f"{run.name}/{label}: saved gains or additions differ")
    index = np.flatnonzero(added) if added.dtype == bool else np.asarray(added)
    solve = {
        "label": label,
        "diagnostics": {"gains": gains, "gain_valid": valid},
        "added": index,
    }
    return solve, checks


def chunk0_state():
    from rang import core
    from rang import core_campaign_array as array

    core.library()
    integrity = array.verify_inputs()
    if not (integrity["all_match_receipts"] and integrity["whole_tile_headers"]):
        raise RuntimeError("local inputs differ from the archived receipts")
    arrays, rows, _ = array.decode_inputs(None)
    extra = array.decode_extra(rows)
    state = array.build_state(arrays, extra, len(extra["antenna_names"]))
    return state, extra


def l2_state():
    from rang import core
    from rang import core_campaign_1830 as l2
    from rang import core_campaign_array as array

    core.library()
    roots = l2.roots_for(l2.GROUP, L2_FETCH)
    fetched = read_json(L2_FETCH / "result.json")
    integrity = l2.verify_inputs(l2.GROUP, roots, fetched)
    if not (integrity["all_match_receipts"] and integrity["whole_tile_headers"]):
        raise RuntimeError("L2 inputs differ from their receipts")
    arrays, rows, _ = l2.decode_inputs(l2.GROUP, roots, None)
    extra = l2.decode_extra(l2.GROUP, rows, roots)
    # The model arm only replaces MODEL_DATA, which no image reads (the flux
    # recovery uses the archived model flux), so both arms share one state.
    state = array.build_state(arrays, extra, len(extra["antenna_names"]))
    return state, extra


# --- the replay ----------------------------------------------------------------


def residual_calls(records, residual):
    """Every recorded residual-RMS call (dicts with candidate, reference and
    a residual_rms call), recomputed from `residual` (label -> RMS)."""
    from rang import core_campaign

    out = []

    def walk(value, path):
        if isinstance(value, dict):
            rr = value.get("residual_rms")
            if (
                "candidate" in value
                and "reference" in value
                and isinstance(rr, dict)
                and "call" in rr
            ):
                c, r = value["candidate"], value["reference"]
                new = core_campaign.call(residual.get(c), residual.get(r))
                out.append(
                    {
                        "where": path,
                        "candidate": c,
                        "reference": r,
                        "archived": rr,
                        "wgrid": new,
                        "call_unchanged": new["call"] == rr["call"],
                    }
                )
            for k, v in value.items():
                walk(v, f"{path}/{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, f"{path}/{i}")

    for name, record in records.items():
        walk(record, name)
    return out


def cmd_replay(args):
    from rang import core_campaign
    from rang import core_campaign_array as array

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.perf_counter()
    names = [n for n in args.archives if ARCHIVES[n][0] == args.cmd]
    state, extra = chunk0_state() if args.cmd == "chunk0" else l2_state()
    record = {
        "dataset": args.cmd,
        "head": os.popen(f"git -C {ROOT} rev-parse HEAD").read().strip(),
        "rayon_num_threads": os.environ.get("RAYON_NUM_THREADS"),
        "state_seconds": time.perf_counter() - t0,
        "state_max_rss_mb": maxrss_mb(),
        "archives": {},
    }
    print(f"state {record['state_seconds']:.1f}s", flush=True)
    cache = {}  # (gains, additions, gridder) -> imaged products and receipt
    for name in names:
        run = ARCHIVES[name][1]
        result, arms = archived_arms(name)
        settings = result["settings"]
        rec = {
            "run": str(run.relative_to(ROOT)),
            "result_sha256": sha256_file(run / "result.json"),
            "image": settings["image"],
            "channel_groups": settings["channel_groups"],
            "arms": {},
        }
        residual = {}
        for label, arm in arms.items():
            if arm is None or (args.arms and label not in args.arms):
                continue
            solve, checks = load_solve(run, label, arm)
            archived = arm["image"]
            boxes = archived.get("boxes_used") or result["boxes"]
            flux = archived.get("model_stokes_i_jy")
            entry = {"checks": checks, "archived": {}}
            for g in args.gridders:
                key = (arm["gains_sha256"], arm["additions_sha256"], g)
                if key not in cache:
                    image = dict(settings["image"])
                    groups = settings["channel_groups"]
                    if g != "wstack":
                        image["gridder"] = g
                        groups = 1
                    s0 = time.perf_counter()
                    metrics, products = array.image_arm(
                        state,
                        extra,
                        solve,
                        out / "images" / g / name,
                        label,
                        image,
                        groups,
                        boxes=boxes,
                    )
                    cache[key] = {
                        "dirty": products["dirty"],
                        "psf": products["psf"],
                        "first": f"{name}/{label}",
                        "groups": groups,
                        "seconds": time.perf_counter() - s0,
                        "image_arm_seconds": metrics["seconds"],
                        "receipt": {
                            k: metrics[k]
                            for k in ("gridder_name", "wgridder")
                            if k in metrics
                        },
                        "dirty_sha256": metrics["dirty_sha256"],
                        "psf_sha256": metrics["psf_sha256"],
                        "stats": metrics["gridder"],
                    }
                    del products
                    print(
                        f"{name}/{label} {g} {cache[key]['seconds']:.1f}s",
                        flush=True,
                    )
                c = cache[key]
                m = array.array_image_metrics(c["dirty"], c["psf"], boxes, flux)
                e = {
                    "imaged_as": c["first"],
                    "groups": c["groups"],
                    "seconds": c["seconds"],
                    "image_arm_seconds": c["image_arm_seconds"],
                    "receipt": c["receipt"],
                    "dirty_sha256": c["dirty_sha256"],
                    "psf_sha256": c["psf_sha256"],
                    "dirty_sha256_equals_archive": c["dirty_sha256"]
                    == archived["dirty_sha256"],
                    "stats": c["stats"],
                    "metrics": {k: m[k] for k in REPORTED_METRICS if k in m},
                }
                # A reused arm (C1's closure-tv-policy) has its source's FITS.
                fits_label = archived.get("reused_from") or label
                for kind in ("dirty", "psf"):
                    ref = read_fits_image(run / "images" / f"{fits_label}-{kind}.fits")
                    e[f"vs_archive_{kind}"] = diff_record(c[kind], ref, kind)
                if g == "wstack":
                    rel = {
                        k: abs(m[k] - archived[k]) / abs(archived[k])
                        for k in GATED_METRICS
                    }
                    e["reconstruction"] = {
                        "metric_relative_differences": rel,
                        "metrics_pass": all(
                            v <= METRIC_TOLERANCE for v in rel.values()
                        ),
                        "pixels_pass": all(
                            e[f"vs_archive_{k}"]["linf_over_peak"] <= F32_QUANTUM
                            for k in ("dirty", "psf")
                        ),
                    }
                    e["reconstruction"]["pass"] = (
                        e["reconstruction"]["metrics_pass"]
                        and e["reconstruction"]["pixels_pass"]
                    )
                else:
                    residual[label] = m["residual_rms"]
                    wstack = cache.get(
                        (arm["gains_sha256"], arm["additions_sha256"], "wstack")
                    )
                    if wstack is not None:
                        for kind in ("dirty", "psf"):
                            e[f"vs_wstack_{kind}"] = diff_record(
                                c[kind], wstack[kind], kind
                            )
                entry[g] = e
            entry["archived"] = {
                k: archived[k] for k in REPORTED_METRICS if k in archived
            }
            rec["arms"][label] = entry
        if residual:
            records = {"result": result}
            if name == "c1":
                records["c1"] = read_json(run / "c1.json")
            for label, arm in arms.items():
                if arm is not None and label not in residual:
                    residual[label] = arm["image"]["residual_rms"]
            calls = residual_calls(records, residual)
            rec["calls"] = calls
            rec["calls_unchanged"] = all(c["call_unchanged"] for c in calls)
        record["archives"][name] = rec
        write_json(out / "reimage.json", record)
    record["total_seconds"] = time.perf_counter() - t0
    record["max_rss_mb"] = maxrss_mb()
    record["core_campaign_call_band"] = [core_campaign.BETTER, core_campaign.WORSE]
    write_json(out / "reimage.json", record)
    print(f"total {record['total_seconds']:.1f}s, {record['max_rss_mb']:.0f} MB")


# --- the default bit-identity --------------------------------------------------


def _wstack_view(path):
    """Image hashes and numbers of a wstack replay (the default path)."""
    rec = read_json(path)
    out = {}
    for name, a in rec["archives"].items():
        for label, entry in a["arms"].items():
            e = entry.get("wstack")
            if e is not None:
                out[f"{name}/{label}"] = {
                    "dirty_sha256": e["dirty_sha256"],
                    "psf_sha256": e["psf_sha256"],
                    "stats": e["stats"],
                    "metrics": e["metrics"],
                }
    return out


def cmd_default(args):
    """Base against branch: precondition FITS and image numbers (hashes.py
    output) or wstack replays (reimage.json); every common entry equal."""
    base, after = Path(args.base), Path(args.after)
    if base.name == "reimage.json" or after.name == "reimage.json":
        a, b = _wstack_view(base), _wstack_view(after)
    else:
        ra, rb = read_json(base), read_json(after)
        a = {**ra["fits"], **ra["image_metrics"]}
        b = {**rb["fits"], **rb["image_metrics"]}

    def strip(v):
        # Receipt fields added by DF2c are not image products.
        if isinstance(v, dict):
            return {
                k: strip(x)
                for k, x in v.items()
                if k not in ("gridder_name", "wgridder", "seconds")
            }
        return v

    common = sorted(set(a) & set(b))
    differ = [k for k in common if strip(a[k]) != strip(b[k])]
    out = {
        "base": str(base),
        "after": str(after),
        "compared": len(common),
        "only_base": sorted(set(a) - set(b)),
        "only_after": sorted(set(b) - set(a)),
        "differ": differ,
        # Every base entry is present and equal (the branch run may cover more).
        "identical": not differ and set(a) <= set(b),
    }
    write_json(args.out, out)
    print(json.dumps({k: out[k] for k in ("compared", "differ", "identical")}))


# --- the compact archive -------------------------------------------------------


def _worst(arms, gridder, field, key):
    values = [
        e[gridder][field][key]
        for e in arms.values()
        if gridder in e and field in e[gridder]
    ]
    return max(values) if values else None


def cmd_summary(args):
    archives = {}
    meta = []
    for path in args.reimage:
        rec = read_json(path)
        meta.append(
            {
                "path": str(Path(path).relative_to(ROOT)),
                "dataset": rec["dataset"],
                "head": rec["head"],
                "state_seconds": rec["state_seconds"],
                "total_seconds": rec["total_seconds"],
                "max_rss_mb": rec["max_rss_mb"],
            }
        )
        for name, a in rec["archives"].items():
            arms = a["arms"]
            s = {
                "run": a["run"],
                "result_sha256": a["result_sha256"],
                "archived_channel_groups": a["channel_groups"],
                "arms_imaged": sorted(arms),
                "reconstruction_pass": all(
                    e["wstack"]["reconstruction"]["pass"] for e in arms.values()
                ),
                "reconstruction_worst_metric_relative": max(
                    max(
                        e["wstack"]["reconstruction"][
                            "metric_relative_differences"
                        ].values()
                    )
                    for e in arms.values()
                ),
                "wgrid_vs_archive": {
                    kind: {
                        key: _worst(arms, "wgrid", f"vs_archive_{kind}", key)
                        for key in (
                            "linf_over_peak",
                            "edge_linf_over_peak",
                            "central_half_linf_over_peak",
                            "rms_over_peak",
                        )
                    }
                    for kind in ("dirty", "psf")
                },
                "metrics": {
                    label: {
                        k: {
                            "wgrid": e["wgrid"]["metrics"].get(k),
                            "archive": e["archived"].get(k),
                        }
                        for k in (
                            "peak_jy_per_beam",
                            "residual_rms",
                            "offsource_rms",
                            "residual_robust_sigma_offsource",
                            "flux_recovery",
                        )
                    }
                    for label, e in arms.items()
                },
                "calls": [
                    {
                        "where": c["where"],
                        "pair": [c["candidate"], c["reference"]],
                        "archived": c["archived"],
                        "wgrid": c["wgrid"],
                    }
                    for c in a.get("calls", [])
                ],
                "calls_unchanged": a.get("calls_unchanged"),
            }
            archives[name] = s
    out = {
        "task": "DF2c",
        "protocol": "research/df2c-campaign-gridder.md",
        "label": "post hoc; changes no verdict; nothing archived is rewritten",
        "runs": meta,
        "archives": archives,
        "all_reconstructions_pass": all(
            a["reconstruction_pass"] for a in archives.values()
        ),
        "all_calls_unchanged": all(a["calls_unchanged"] for a in archives.values()),
    }
    if args.default:
        out["default_bit_identity"] = {
            Path(p).name: {
                k: v
                for k, v in read_json(p).items()
                if k in ("compared", "differ", "identical")
            }
            for p in args.default
        }
    write_json(args.out, out)
    print(
        json.dumps(
            {k: out[k] for k in ("all_reconstructions_pass", "all_calls_unchanged")}
        )
    )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for dataset in ("chunk0", "l2"):
        s = sub.add_parser(dataset)
        s.add_argument("out")
        s.add_argument(
            "--archives",
            nargs="+",
            default=[n for n, (d, _) in ARCHIVES.items() if d == dataset],
            choices=[n for n, (d, _) in ARCHIVES.items() if d == dataset],
        )
        s.add_argument("--arms", nargs="+", default=None)
        s.add_argument(
            "--gridders",
            nargs="+",
            default=["wstack", "wgrid"],
            choices=("wstack", "wgrid"),
        )
    s = sub.add_parser("default")
    s.add_argument("base")
    s.add_argument("after")
    s.add_argument("out")
    s = sub.add_parser("summary")
    s.add_argument("out")
    s.add_argument("reimage", nargs="+")
    s.add_argument("--default", nargs="+", default=None)
    args = p.parse_args(argv)
    if args.cmd in ("chunk0", "l2"):
        if "wgrid" in args.gridders and "wstack" not in args.gridders:
            sys.exit(
                "wgrid numbers need the wstack reconstruction gate in the same run"
            )
        cmd_replay(args)
    elif args.cmd == "default":
        cmd_default(args)
    else:
        cmd_summary(args)


if __name__ == "__main__":
    main()
