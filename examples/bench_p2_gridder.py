"""Timing and the task K image comparator of big-plan task P2
(research/p2-gridder.md).

    python examples/bench_p2_gridder.py c-inputs OUT
    python examples/bench_p2_gridder.py k-replay OUT [--dump-inputs]
    python examples/bench_p2_gridder.py time INPUTS OUT.json [--repeats N]
        [--labels A,B] [--tile N] [--save-images DIR]
    python examples/bench_p2_gridder.py bench INPUTS OUT_DIR --lib NAME=PATH
        [--lib ...] [--threads 1,2,4] [--repeats 3] [--labels ...] [--tile N]
    python examples/bench_p2_gridder.py diff OLD_DIR NEW_DIR OUT.json

`c-inputs` writes the gridder inputs of task C's fifteen jobs (archived
checkpoints, the oracle's imaging weights, the core's Stokes I reader) as
`.npz` files. `k-replay` images the six archived task K arms from the
archived fetched bytes, gains and flag additions through the unedited
`core_campaign.image_arm`, and compares hashes, gridder counters, image
metrics, the residual-RMS hypothesis calls and the pixels with the archive
under task A's tolerances (exit status 1 on failure); `--dump-inputs` also
saves the gridder inputs of each arm. `time` inverts every input in this
process and records per-image wall and process CPU seconds, peak RSS, load
and output hashes; `bench` runs `time` in a fresh process per (repeat,
thread count, library), interleaving the libraries (ABAB), with
`RAYON_NUM_THREADS`, `RANG_CORE_LIB` and `OPENBLAS_NUM_THREADS=1` set.
`diff` reports old-versus-new float64 pixel differences of saved images.
"""

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

C_ARCHIVE = ROOT / "outputs" / "tv-next-imaging-wsl-20261029-01"
C_ORACLE = ROOT / "outputs" / "core-c-20261029-01"
K_RUN = ROOT / "outputs" / "core-k-20261030-01"
K_RESULT = ROOT / "research" / "results" / "core-k-luno-campaign.json"
C_SETTINGS = {
    "width": 512,
    "height": 512,
    "scale_arcsec": 8.0,
    "w_layers": 64,
    "kernel_size": 7,
    "oversampling": 1023,
    "padding": 1.2,
}
C_CHANNELS = (1024, 3072)
ARMS = (
    "original",
    "tricolour-firstpass",
    "tricolour-mild",
    "tv-policy",
    "tv-unguided-best",
    "tricolour-firstpass+tv",
)
# Task A's frozen tolerances (research/core-a-imaging-sensitivity.md).
DIRTY_LINF_OF_PEAK = 8.8e-6
PSF_LINF = 2.8e-6
WEIGHT_RELATIVE = 1e-9
DIRTY_METRICS = (
    "peak_jy_per_beam",
    "offsource_rms",
    "residual_rms",
    "residual_rms_offsource",
    "residual_max_abs",
    "flux_recovery",
)
PSF_METRICS = ("psf_centre", "psf_max_sidelobe", "psf_max_outside_offsource_box")
WEIGHT_STATS = ("image_weight", "visibility_weight_sum", "max_gridded_weight")
EXACT_STATS = ("gridded_count", "n_w_layers", "min_w", "max_w")


def sha256_array(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def loadavg():
    return Path("/proc/loadavg").read_text().split()[:3]


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")


def save_inputs(path, uvw, frequencies, data, weights, imaging_weights, settings):
    np.savez(
        path,
        uvw=np.asarray(uvw, np.float64),
        frequencies=np.asarray(frequencies, np.float64),
        data=np.asarray(data, np.complex64),
        weights=np.asarray(weights, np.float32),
        imaging_weights=np.asarray(imaging_weights, np.float32),
        settings=json.dumps(settings),
    )


# --- inputs ------------------------------------------------------------------


def c_inputs(out):
    """Task C's fifteen jobs as `run_core_gridder.py` prepares them."""
    from rangtoy import core_grid

    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    receipt = json.loads((C_ORACLE / "receipt.json").read_text())
    common = {
        role: np.load(C_ORACLE / "inputs" / f"{role}-common.npz")
        for role in ("response", "caracal")
    }
    for label, job in receipt["jobs"].items():
        shared = common[job["role"]]
        checkpoint = np.load(C_ARCHIVE / "checkpoints" / f"{label}-written.npz")
        inputs = np.load(C_ORACLE / "inputs" / f"{label}-inputs.npz")
        flags = checkpoint["FLAG"][:, C_CHANNELS[0] : C_CHANNELS[1]]
        if not np.array_equal(flags, inputs["FLAG"]):
            raise RuntimeError(f"{label}: flag mismatch between checkpoint and oracle")
        data = checkpoint["CORRECTED_DATA"][:, C_CHANNELS[0] : C_CHANNELS[1]]
        sample, weight = core_grid.stokes_i_reader(
            data, shared["WEIGHT_SPECTRUM"], flags, checkpoint["FLAG_ROW"]
        )
        save_inputs(
            out / f"c-{label}.npz",
            shared["UVW"],
            shared["CHAN_FREQ"],
            sample,
            weight,
            inputs["IMAGING_WEIGHT"],
            C_SETTINGS,
        )
        print("wrote", out / f"c-{label}.npz", flush=True)


def _relative(a, b):
    if a == b:
        return 0.0
    return abs(float(a) - float(b)) / max(abs(float(b)), 1e-300)


def _read_fits(path):
    from astropy.io import fits

    with fits.open(str(path), memmap=False) as hdus:
        return np.asarray(hdus[0].data, np.float64).squeeze()


def k_replay(out, dump_inputs=False):
    """Task K's six arms imaged again from the archived inputs, compared."""
    from rangtoy import core, core_campaign, core_fetch, core_grid

    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    load_before = loadavg()
    fetched = K_RUN / "fetch"
    arrays, _ = core_fetch.decode_slice(fetched)
    rows = np.asarray(json.loads((fetched / "result.json").read_text())["rows"])
    extra = core_campaign.decode_extra(fetched, rows)
    state = core_campaign.build_state(arrays, extra)
    archived = json.loads(K_RESULT.read_text())
    arms_archived = archived["arms"]
    prepared = time.perf_counter()
    invert = core_grid.invert
    current = {}
    if dump_inputs:
        (out / "inputs").mkdir()

    def recording(uvw, frequencies, data, weights, imaging_weights, **settings):
        if dump_inputs:
            save_inputs(
                out / "inputs" / f"k-{current['label']}.npz",
                uvw,
                frequencies,
                data,
                weights,
                imaging_weights,
                settings,
            )
        w0, c0 = time.perf_counter(), time.process_time()
        products = invert(uvw, frequencies, data, weights, imaging_weights, **settings)
        current["invert_wall"] = time.perf_counter() - w0
        current["invert_cpu"] = time.process_time() - c0
        current["dirty"] = products["dirty"]
        current["psf"] = products["psf"]
        return products

    core_grid.invert = recording
    report = {
        "backend": core.backend_name(),
        "library": str(core.library_path()),
        "library_sha256": sha256_file(core.library_path()),
        "rayon_num_threads": os.environ.get("RAYON_NUM_THREADS"),
        "tolerances": {
            "dirty_linf_of_peak": DIRTY_LINF_OF_PEAK,
            "psf_linf": PSF_LINF,
            "weight_relative": WEIGHT_RELATIVE,
            "dirty_metric_relative": DIRTY_LINF_OF_PEAK,
            "psf_metric_absolute": PSF_LINF,
        },
        "arms": {},
        "failures": [],
    }
    new_image = {}
    try:
        for label in ARMS:
            current.clear()
            current["label"] = label
            gains = np.load(K_RUN / "gains" / f"{label}.npz")
            flags = np.load(K_RUN / "flags" / f"{label}.npz")
            solve = {
                "added": np.asarray(flags["additions"], bool),
                "diagnostics": {
                    "gains": gains["gains"],
                    "gain_valid": gains["gain_valid"],
                },
            }
            metrics = core_campaign.image_arm(
                state, extra, solve, out / "images", label
            )
            reference = arms_archived[label]["image"]
            new_image[label] = metrics
            arm = {
                "invert_wall": current["invert_wall"],
                "invert_cpu": current["invert_cpu"],
                "seconds": metrics["seconds"],
                "dirty_sha256_equal": metrics["dirty_sha256"]
                == reference["dirty_sha256"],
                "psf_sha256_equal": metrics["psf_sha256"] == reference["psf_sha256"],
                "dirty_sha256": metrics["dirty_sha256"],
                "psf_sha256": metrics["psf_sha256"],
                "metrics": {},
                "stats": {},
            }
            for key in DIRTY_METRICS:
                diff = _relative(metrics[key], reference[key])
                arm["metrics"][key] = {"relative": diff, "value": metrics[key]}
                if diff > DIRTY_LINF_OF_PEAK:
                    report["failures"].append(f"{label}: {key} relative {diff:.3e}")
            for key in PSF_METRICS:
                diff = abs(metrics[key] - reference[key])
                arm["metrics"][key] = {"absolute": diff, "value": metrics[key]}
                if diff > PSF_LINF:
                    report["failures"].append(f"{label}: {key} absolute {diff:.3e}")
            if metrics["peak_pixel"] != reference["peak_pixel"]:
                report["failures"].append(f"{label}: peak pixel moved")
            if metrics["imaged_cells"] != reference["imaged_cells"]:
                report["failures"].append(f"{label}: imaged cells differ")
            for key in WEIGHT_STATS:
                diff = _relative(metrics["gridder"][key], reference["gridder"][key])
                arm["stats"][key] = diff
                if diff > WEIGHT_RELATIVE:
                    report["failures"].append(f"{label}: {key} relative {diff:.3e}")
            for key in EXACT_STATS:
                equal = metrics["gridder"][key] == reference["gridder"][key]
                arm["stats"][key] = equal
                if not equal:
                    report["failures"].append(f"{label}: {key} differs")
            arm["stats"]["psf_normalization_relative"] = _relative(
                metrics["gridder"]["psf_normalization"],
                reference["gridder"]["psf_normalization"],
            )
            pixels = {}
            for kind in ("dirty", "psf"):
                ref = _read_fits(K_RUN / "images" / f"{label}-{kind}.fits")
                cand = np.asarray(current[kind], np.float64)
                delta = np.abs(cand - ref)
                peak = float(np.max(np.abs(ref)))
                pixels[kind] = {
                    "max_abs_difference": float(delta.max()),
                    "rms_difference": float(np.sqrt(np.mean(delta**2))),
                    "reference_peak": peak,
                    "max_relative_to_peak": float(delta.max() / peak),
                }
            arm["pixels_vs_archived_fits"] = pixels
            if pixels["dirty"]["max_relative_to_peak"] > DIRTY_LINF_OF_PEAK:
                report["failures"].append(f"{label}: dirty pixels")
            if pixels["psf"]["max_abs_difference"] > PSF_LINF:
                report["failures"].append(f"{label}: psf pixels")
            report["arms"][label] = arm
            print(
                f"{label:24s} invert {arm['invert_wall']:6.2f}s cpu "
                f"{arm['invert_cpu']:6.2f}s hash dirty/psf "
                f"{arm['dirty_sha256_equal']}/{arm['psf_sha256_equal']} "
                f"dirty max|d|/peak {pixels['dirty']['max_relative_to_peak']:.2e} "
                f"psf max|d| {pixels['psf']['max_abs_difference']:.2e}",
                flush=True,
            )
    finally:
        core_grid.invert = invert
    calls = []
    for hyp in archived["hypotheses"]:
        c, r = hyp["candidate"], hyp["reference"]
        new = core_campaign.call(
            new_image[c]["residual_rms"], new_image[r]["residual_rms"]
        )
        old = hyp["residual_rms"]
        calls.append(
            {
                "candidate": c,
                "reference": r,
                "ratio": new["ratio"],
                "archived_ratio": old["ratio"],
                "call": new["call"],
                "archived_call": old["call"],
            }
        )
        if new["call"] != old["call"]:
            report["failures"].append(f"{c} vs {r}: residual-RMS call changed")
    report["hypothesis_calls"] = calls
    report["all_hashes_equal"] = all(
        a["dirty_sha256_equal"] and a["psf_sha256_equal"]
        for a in report["arms"].values()
    )
    report["worst"] = {
        "dirty_pixels_of_peak": max(
            a["pixels_vs_archived_fits"]["dirty"]["max_relative_to_peak"]
            for a in report["arms"].values()
        ),
        "psf_pixels": max(
            a["pixels_vs_archived_fits"]["psf"]["max_abs_difference"]
            for a in report["arms"].values()
        ),
        "dirty_metric_relative": max(
            a["metrics"][k]["relative"]
            for a in report["arms"].values()
            for k in DIRTY_METRICS
        ),
        "psf_metric_absolute": max(
            a["metrics"][k]["absolute"]
            for a in report["arms"].values()
            for k in PSF_METRICS
        ),
    }
    report["passed"] = not report["failures"]
    report["prepare_seconds"] = prepared - started
    report["wall_seconds"] = time.perf_counter() - started
    report["max_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    report["loadavg_before_after"] = [load_before, loadavg()]
    write_json(out / "k-replay.json", report)
    print(
        "worst",
        json.dumps(report["worst"]),
        "hashes equal",
        report["all_hashes_equal"],
        "passed",
        report["passed"],
    )
    for failure in report["failures"]:
        print("  FAIL", failure)
    return 0 if report["passed"] else 1


# --- timing ------------------------------------------------------------------


def _load_inputs(directory, labels=None, tile=1):
    items = []
    for path in sorted(Path(directory).glob("*.npz")):
        label = path.stem
        if labels and label not in labels:
            continue
        payload = np.load(path)
        inputs = {
            key: payload[key]
            for key in ("uvw", "frequencies", "data", "weights", "imaging_weights")
        }
        if tile > 1:
            for key in ("uvw", "data", "weights", "imaging_weights"):
                reps = (tile,) + (1,) * (inputs[key].ndim - 1)
                inputs[key] = np.tile(inputs[key], reps)
        settings = json.loads(str(payload["settings"]))
        items.append((label, inputs, settings))
    if not items:
        raise SystemExit(f"no inputs in {directory}")
    return items


def time_inputs(directory, output, repeats=1, labels=None, tile=1, save_images=None):
    from rangtoy import core, core_grid

    load_before = loadavg()
    items = _load_inputs(directory, labels, tile)
    loaded_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    records = []
    for repeat in range(repeats):
        for label, inputs, settings in items:
            w0, c0 = time.perf_counter(), time.process_time()
            products = core_grid.invert(**inputs, **settings)
            wall = time.perf_counter() - w0
            cpu = time.process_time() - c0
            records.append(
                {
                    "repeat": repeat,
                    "label": label,
                    "samples": int(inputs["data"].size),
                    "gridded_count": int(products["stats"]["gridded_count"]),
                    "wall": wall,
                    "cpu": cpu,
                    "rss_mb_after": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    / 1024,
                    "dirty_sha256": sha256_array(products["dirty"]),
                    "psf_sha256": sha256_array(products["psf"]),
                }
            )
            if save_images and repeat == 0:
                directory_out = Path(save_images)
                directory_out.mkdir(parents=True, exist_ok=True)
                np.save(directory_out / f"{label}-dirty.npy", products["dirty"])
                np.save(directory_out / f"{label}-psf.npy", products["psf"])
            print(
                f"{label:40s} r{repeat} wall {wall:7.3f}s cpu {cpu:7.3f}s",
                flush=True,
            )
    result = {
        "backend": core.backend_name(),
        "library": str(core.library_path()),
        "library_sha256": sha256_file(core.library_path()),
        "rayon_num_threads": os.environ.get("RAYON_NUM_THREADS"),
        "tile": tile,
        "repeats": repeats,
        "records": records,
        "max_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "rss_mb_after_loading_inputs": loaded_rss,
        "loadavg_before_after": [load_before, loadavg()],
        "total_wall": sum(r["wall"] for r in records),
        "total_cpu": sum(r["cpu"] for r in records),
    }
    write_json(output, result)
    return result


def bench(directory, out_dir, libs, threads, repeats, labels=None, tile=1, single=()):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    runs = []
    for repeat in range(repeats):
        for n in threads:
            for name, path in libs:
                if name in single and n != threads[0]:
                    continue
                env = dict(os.environ)
                env["RAYON_NUM_THREADS"] = str(n)
                env["RANG_CORE_LIB"] = str(Path(path).resolve())
                env["RANG_CORE_BACKEND"] = "ctypes"
                env["OPENBLAS_NUM_THREADS"] = "1"
                target = out_dir / f"{name}-t{n}-r{repeat}.json"
                command = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "time",
                    str(directory),
                    str(target),
                    "--tile",
                    str(tile),
                ]
                if labels:
                    command += ["--labels", ",".join(labels)]
                w0 = time.perf_counter()
                subprocess.run(command, env=env, check=True, stdout=subprocess.DEVNULL)
                wall = time.perf_counter() - w0
                record = json.loads(target.read_text())
                runs.append(
                    {
                        "lib": name,
                        "threads": n,
                        "repeat": repeat,
                        "process_wall": wall,
                        "file": target.name,
                        "total_wall": record["total_wall"],
                        "total_cpu": record["total_cpu"],
                        "max_rss_mb": record["max_rss_mb"],
                        "rss_mb_after_loading_inputs": record[
                            "rss_mb_after_loading_inputs"
                        ],
                        "loadavg_before_after": record["loadavg_before_after"],
                        "hashes": {
                            r["label"]: [r["dirty_sha256"], r["psf_sha256"]]
                            for r in record["records"]
                        },
                        "per_image": {
                            r["label"]: [r["wall"], r["cpu"]] for r in record["records"]
                        },
                    }
                )
                print(
                    f"{name:10s} t{n:<2d} r{repeat} images {record['total_wall']:8.3f}s "
                    f"cpu {record['total_cpu']:8.3f}s rss {record['max_rss_mb']:7.1f} MB "
                    f"load {record['loadavg_before_after'][0][0]}",
                    flush=True,
                )
    summary = {}
    for name, _ in libs:
        for n in threads:
            selected = [r for r in runs if r["lib"] == name and r["threads"] == n]
            if not selected:
                continue
            hashes = {json.dumps(r["hashes"], sort_keys=True) for r in selected}
            summary[f"{name}-t{n}"] = {
                "median_total_wall": float(
                    np.median([r["total_wall"] for r in selected])
                ),
                "min_total_wall": float(min(r["total_wall"] for r in selected)),
                "median_total_cpu": float(
                    np.median([r["total_cpu"] for r in selected])
                ),
                "max_rss_mb": float(max(r["max_rss_mb"] for r in selected)),
                "repeats_identical": len(hashes) == 1,
            }
    reference = {}
    for name, _ in libs:
        sets = {
            json.dumps(r["hashes"], sort_keys=True) for r in runs if r["lib"] == name
        }
        reference[name] = {"identical_across_threads_and_repeats": len(sets) == 1}
    result = {
        "inputs": str(directory),
        "libs": {
            name: {"path": path, "sha256": sha256_file(path)} for name, path in libs
        },
        "threads": threads,
        "repeats": repeats,
        "tile": tile,
        "labels": labels,
        "runs": runs,
        "summary": summary,
        "determinism": reference,
    }
    write_json(out_dir / "bench.json", result)
    for key, value in summary.items():
        print(key, json.dumps(value))
    print("determinism", json.dumps(reference))


def diff(old_dir, new_dir, output):
    old_dir, new_dir = Path(old_dir), Path(new_dir)
    records = {}
    for path in sorted(old_dir.glob("*.npy")):
        old = np.load(path)
        new = np.load(new_dir / path.name)
        delta = np.abs(new - old)
        peak = float(np.max(np.abs(old)))
        records[path.stem] = {
            "max_abs_difference": float(delta.max()),
            "rms_difference": float(np.sqrt(np.mean(delta**2))),
            "peak": peak,
            "max_relative_to_peak": float(delta.max() / peak),
            "identical": bool(np.array_equal(old, new)),
        }
    summary = {
        kind: {
            "max_relative_to_peak": max(
                r["max_relative_to_peak"]
                for k, r in records.items()
                if k.endswith(kind)
            ),
            "max_abs_difference": max(
                r["max_abs_difference"] for k, r in records.items() if k.endswith(kind)
            ),
            "identical": sum(
                r["identical"] for k, r in records.items() if k.endswith(kind)
            ),
            "images": sum(1 for k in records if k.endswith(kind)),
        }
        for kind in ("dirty", "psf")
    }
    write_json(
        output,
        {
            "old": str(old_dir),
            "new": str(new_dir),
            "images": records,
            "summary": summary,
        },
    )
    print(json.dumps(summary))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("c-inputs")
    p.add_argument("out")
    p = sub.add_parser("k-replay")
    p.add_argument("out")
    p.add_argument("--dump-inputs", action="store_true")
    p = sub.add_parser("time")
    p.add_argument("inputs")
    p.add_argument("output")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--labels")
    p.add_argument("--tile", type=int, default=1)
    p.add_argument("--save-images")
    p = sub.add_parser("bench")
    p.add_argument("inputs")
    p.add_argument("out_dir")
    p.add_argument("--lib", action="append", required=True, help="NAME=PATH")
    p.add_argument("--threads", default="1")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--labels")
    p.add_argument("--tile", type=int, default=1)
    p.add_argument(
        "--single",
        action="append",
        default=[],
        help="NAME of a library run at the first thread count only",
    )
    p = sub.add_parser("diff")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("output")
    args = parser.parse_args(argv)
    labels = args.labels.split(",") if getattr(args, "labels", None) else None
    if args.command == "c-inputs":
        c_inputs(args.out)
    elif args.command == "k-replay":
        return k_replay(args.out, args.dump_inputs)
    elif args.command == "time":
        time_inputs(
            args.inputs, args.output, args.repeats, labels, args.tile, args.save_images
        )
    elif args.command == "bench":
        libs = [tuple(item.split("=", 1)) for item in args.lib]
        threads = [int(n) for n in args.threads.split(",")]
        bench(
            args.inputs,
            args.out_dir,
            libs,
            threads,
            args.repeats,
            labels,
            args.tile,
            args.single,
        )
    elif args.command == "diff":
        diff(args.old, args.new, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
