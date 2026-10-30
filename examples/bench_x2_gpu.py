"""Comparators and timing of big-plan task X2, the wgpu gridder
(research/x2-wgpu.md).

    python examples/bench_x2_gpu.py k-replay OUT
    python examples/bench_x2_gpu.py array-inputs OUT_DIR
    python examples/bench_x2_gpu.py time INPUTS OUT.json [--device cpu|gpu]
        [--precision f64|f32] [--repeats N] [--labels A,B] [--save-images DIR]
    python examples/bench_x2_gpu.py bench INPUTS OUT_DIR [--configs ...]
        [--repeats 3] [--labels ...]
    python examples/bench_x2_gpu.py compare REF_DIR CAND_DIR OUT.json

`k-replay` runs task K's frozen image comparator, `bench_p2_gridder.k_replay`
(P2), unedited; the device is the one `core_grid.invert` reads from
`RANG_GRIDDER_DEVICE` / `RANG_GRIDDER_GPU_PRECISION`. On Windows the two
POSIX calls of that module (`resource.getrusage`, `/proc/loadavg`) are
replaced by `rang.rusage` and a constant before it is imported; nothing else
of the comparator changes. `array-inputs` saves DF2a's whole-array synthetic
case (`bench_df2.array_case`, seed 2030) in P2's gridder-input layout. `time`
inverts every input in this process on one device and records per-image wall
and CPU seconds, the GPU path's own timing breakdown, peak RSS and image
hashes; the first image of a fresh process carries the adapter and shader
compilation cost, which is reported separately. `bench` runs `time` in a
fresh process per (repeat, configuration), configurations interleaved, and
samples GPU memory with `nvidia-smi` while each process runs. `compare`
reports float64 pixel differences of saved images against a reference set
and the verdicts under task A's tolerances.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "examples"))

from rang import rusage

# Task A's frozen tolerances (research/core-a-imaging-sensitivity.md) and the
# X2 agreement bound with the CPU path (research/x2-wgpu.md, criterion 4).
DIRTY_LINF_OF_PEAK = 8.8e-6
PSF_LINF = 2.8e-6
AGREEMENT_OF_PEAK = 1e-10


def _install_posix_shims():
    """`bench_p2_gridder` and `bench_df2` import `resource` and read
    `/proc/loadavg` at call time; on Windows supply both from `rang.rusage`
    (peak working set, reported in KiB as Linux `ru_maxrss` is)."""
    try:
        import resource  # noqa: F401
    except ImportError:
        shim = types.ModuleType("resource")
        shim.RUSAGE_SELF = 0

        def getrusage(_who):
            return types.SimpleNamespace(ru_maxrss=rusage.peak_rss_bytes() / 1024.0)

        shim.getrusage = getrusage
        sys.modules["resource"] = shim


def loadavg():
    """The WSL host's one/five/fifteen-minute load where readable (the CPUs
    are shared with the WSL VM), else None."""
    path = Path("/proc/loadavg")
    if path.exists():
        return path.read_text().split()[:3]
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["wsl", "-e", "cat", "/proc/loadavg"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            if out.returncode == 0:
                return out.stdout.split()[:3]
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def _p2():
    _install_posix_shims()
    import bench_p2_gridder as p2

    p2.loadavg = loadavg
    return p2


def sha256_array(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")


# --- comparators ---------------------------------------------------------------


def k_replay(out):
    p2 = _p2()
    return p2.k_replay(out)


def k_inputs(out, inputs_dir=None):
    """Task K's image comparator on P2's dumped gridder inputs.

    The archived fetched bytes (`outputs/core-k-20261030-01/fetch`, 725 MB)
    that `k_replay` decodes are no longer on the host. P2 dumped every arm's
    `core_grid.invert` arguments from the baseline replay (whose hashes equal
    the archive), so the inversion is replayed from those, and everything
    after it is P2's frozen comparison: `core_campaign.image_metrics` with the
    archived model flux, peak pixel, imaged cells (reader weight > 0), the
    gridder counters, the pixels against the archived FITS and the
    residual-RMS calls of the archived hypotheses, under the same tolerances.
    """
    from rang import core, core_campaign, core_grid

    p2 = _p2()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    inputs_dir = Path(
        inputs_dir or (p2.ROOT / "outputs" / "p2-gridder-20261030-01" / "inputs-k")
    )
    archived = json.loads(p2.K_RESULT.read_text())
    started = time.perf_counter()
    report = {
        "backend": core.backend_name(),
        "library": str(core.library_path()),
        "device": core_grid.resolve_device(),
        "precision": core_grid.resolve_precision(),
        "inputs": str(inputs_dir),
        "rayon_num_threads": os.environ.get("RAYON_NUM_THREADS"),
        "tolerances": {
            "dirty_linf_of_peak": p2.DIRTY_LINF_OF_PEAK,
            "psf_linf": p2.PSF_LINF,
            "weight_relative": p2.WEIGHT_RELATIVE,
            "dirty_metric_relative": p2.DIRTY_LINF_OF_PEAK,
            "psf_metric_absolute": p2.PSF_LINF,
        },
        "arms": {},
        "failures": [],
    }
    new_image = {}
    for label in p2.ARMS:
        payload = np.load(inputs_dir / f"k-{label}.npz")
        inputs = {
            key: payload[key]
            for key in ("uvw", "frequencies", "data", "weights", "imaging_weights")
        }
        settings = json.loads(str(payload["settings"]))
        reference = archived["arms"][label]["image"]
        w0 = time.perf_counter()
        products = core_grid.invert(**inputs, **settings)
        invert_wall = time.perf_counter() - w0
        metrics = core_campaign.image_metrics(
            products["dirty"], products["psf"], reference["model_stokes_i_jy"]
        )
        metrics["imaged_cells"] = int((inputs["weights"] > 0).sum())
        metrics["gridder"] = products["stats"]
        new_image[label] = metrics
        arm = {
            "invert_wall": invert_wall,
            "dirty_sha256": sha256_array(products["dirty"].astype(np.float32)),
            "metrics": {},
            "stats": {},
        }
        if "gpu" in products:
            arm["gpu"] = products["gpu"]
        for key in p2.DIRTY_METRICS:
            diff = p2._relative(metrics[key], reference[key])
            arm["metrics"][key] = {"relative": diff, "value": metrics[key]}
            if diff > p2.DIRTY_LINF_OF_PEAK:
                report["failures"].append(f"{label}: {key} relative {diff:.3e}")
        for key in p2.PSF_METRICS:
            diff = abs(metrics[key] - reference[key])
            arm["metrics"][key] = {"absolute": diff, "value": metrics[key]}
            if diff > p2.PSF_LINF:
                report["failures"].append(f"{label}: {key} absolute {diff:.3e}")
        if metrics["peak_pixel"] != reference["peak_pixel"]:
            report["failures"].append(f"{label}: peak pixel moved")
        if metrics["imaged_cells"] != reference["imaged_cells"]:
            report["failures"].append(f"{label}: imaged cells differ")
        for key in p2.WEIGHT_STATS:
            diff = p2._relative(metrics["gridder"][key], reference["gridder"][key])
            arm["stats"][key] = diff
            if diff > p2.WEIGHT_RELATIVE:
                report["failures"].append(f"{label}: {key} relative {diff:.3e}")
        for key in p2.EXACT_STATS:
            equal = metrics["gridder"][key] == reference["gridder"][key]
            arm["stats"][key] = equal
            if not equal:
                report["failures"].append(f"{label}: {key} differs")
        arm["stats"]["psf_normalization_relative"] = p2._relative(
            metrics["gridder"]["psf_normalization"],
            reference["gridder"]["psf_normalization"],
        )
        pixels = {}
        for kind in ("dirty", "psf"):
            ref = p2._read_fits(p2.K_RUN / "images" / f"{label}-{kind}.fits")
            cand = np.asarray(products[kind], np.float64)
            delta = np.abs(cand - ref)
            peak = float(np.max(np.abs(ref)))
            pixels[kind] = {
                "max_abs_difference": float(delta.max()),
                "rms_difference": float(np.sqrt(np.mean(delta**2))),
                "reference_peak": peak,
                "max_relative_to_peak": float(delta.max() / peak),
            }
        arm["pixels_vs_archived_fits"] = pixels
        if pixels["dirty"]["max_relative_to_peak"] > p2.DIRTY_LINF_OF_PEAK:
            report["failures"].append(f"{label}: dirty pixels")
        if pixels["psf"]["max_abs_difference"] > p2.PSF_LINF:
            report["failures"].append(f"{label}: psf pixels")
        report["arms"][label] = arm
        print(
            f"{label:24s} invert {invert_wall:6.2f}s "
            f"dirty max|d|/peak {pixels['dirty']['max_relative_to_peak']:.2e} "
            f"psf max|d| {pixels['psf']['max_abs_difference']:.2e}",
            flush=True,
        )
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
    arms = report["arms"].values()
    report["worst"] = {
        "dirty_pixels_of_peak": max(
            a["pixels_vs_archived_fits"]["dirty"]["max_relative_to_peak"] for a in arms
        ),
        "psf_pixels": max(
            a["pixels_vs_archived_fits"]["psf"]["max_abs_difference"] for a in arms
        ),
        "dirty_metric_relative": max(
            a["metrics"][k]["relative"] for a in arms for k in p2.DIRTY_METRICS
        ),
        "psf_metric_absolute": max(
            a["metrics"][k]["absolute"] for a in arms for k in p2.PSF_METRICS
        ),
        "weight_stat_relative": max(
            a["stats"][k] for a in arms for k in p2.WEIGHT_STATS
        ),
    }
    report["passed"] = not report["failures"]
    report["wall_seconds"] = time.perf_counter() - started
    report["max_rss_mb"] = rusage.peak_rss_mb()
    write_json(out / "k-inputs.json", report)
    print("worst", json.dumps(report["worst"]), "passed", report["passed"])
    for failure in report["failures"]:
        print("  FAIL", failure)
    return 0 if report["passed"] else 1


def array_inputs(out):
    _install_posix_shims()
    import bench_df2

    p2 = _p2()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    for label, inputs, settings in bench_df2.array_case():
        full = {
            "width": settings["width"],
            "height": settings["height"],
            "scale_arcsec": settings["scale_arcsec"],
            "w_layers": 64,
            "kernel_size": 7,
            "oversampling": 1023,
            "padding": 1.2,
        }
        p2.save_inputs(out / f"{label}.npz", settings=full, **inputs)
        print(label, inputs["data"].shape, full, flush=True)
    write_json(out / "array-case.json", {"array": bench_df2.ARRAY})
    return 0


def compare(reference, candidate, output):
    reference, candidate = Path(reference), Path(candidate)
    result = {"reference": str(reference), "candidate": str(candidate), "images": {}}
    failures = []
    for path in sorted(reference.glob("*-dirty.npy")):
        label = path.name[: -len("-dirty.npy")]
        entry = {}
        for kind in ("dirty", "psf"):
            ref = np.load(reference / f"{label}-{kind}.npy")
            cand = np.load(candidate / f"{label}-{kind}.npy")
            delta = np.abs(cand - ref)
            peak = float(np.max(np.abs(ref)))
            # Border: the outer eighth of the image on every side (DF2a's
            # reordering floor sits at the border of wide fields).
            h, w = ref.shape
            bh, bw = max(1, h // 8), max(1, w // 8)
            border = np.ones_like(delta, bool)
            border[bh:-bh, bw:-bw] = False
            entry[kind] = {
                "max_abs_difference": float(delta.max()),
                "max_relative_to_peak": float(delta.max() / peak),
                "rms_difference": float(np.sqrt(np.mean(delta**2))),
                "max_border_relative_to_peak": float(delta[border].max() / peak),
                "max_inner_relative_to_peak": float(delta[~border].max() / peak),
                "reference_peak": peak,
                "bit_identical": bool(np.array_equal(cand, ref)),
            }
        entry["dirty_within_task_a"] = (
            entry["dirty"]["max_relative_to_peak"] <= DIRTY_LINF_OF_PEAK
        )
        entry["psf_within_task_a"] = entry["psf"]["max_abs_difference"] <= PSF_LINF
        entry["within_agreement_bound"] = (
            entry["dirty"]["max_relative_to_peak"] <= AGREEMENT_OF_PEAK
            and entry["psf"]["max_relative_to_peak"] <= AGREEMENT_OF_PEAK
        )
        for key in ("dirty_within_task_a", "psf_within_task_a"):
            if not entry[key]:
                failures.append(f"{label}: {key}")
        result["images"][label] = entry
        print(
            f"{label:40s} dirty {entry['dirty']['max_relative_to_peak']:.3e} "
            f"psf {entry['psf']['max_relative_to_peak']:.3e} "
            f"identical {entry['dirty']['bit_identical']}/{entry['psf']['bit_identical']}",
            flush=True,
        )
    if not result["images"]:
        raise SystemExit(f"no images in {reference}")
    images = result["images"].values()
    result["worst"] = {
        kind: {
            key: max(e[kind][key] for e in images)
            for key in (
                "max_relative_to_peak",
                "max_abs_difference",
                "max_border_relative_to_peak",
                "max_inner_relative_to_peak",
            )
        }
        for kind in ("dirty", "psf")
    }
    result["all_bit_identical"] = all(
        e["dirty"]["bit_identical"] and e["psf"]["bit_identical"] for e in images
    )
    result["all_within_agreement_bound"] = all(
        e["within_agreement_bound"] for e in images
    )
    result["failures"] = failures
    result["passed"] = not failures
    write_json(output, result)
    print("worst", json.dumps(result["worst"]), "passed", result["passed"])
    return 0 if result["passed"] else 1


# --- timing --------------------------------------------------------------------


def time_inputs(
    directory, output, device, precision, repeats=1, labels=None, save_images=None
):
    from rang import core, core_grid

    p2 = _p2()
    load_before = loadavg()
    items = p2._load_inputs(directory, labels)
    # First-call cost of the GPU path: adapter, device and queue creation
    # (the first `gpu_adapter` call of the process), measured apart from the
    # images; shader compilation is in the first image's `compile_s`.
    adapter_s = None
    if device == "gpu":
        a0 = time.perf_counter()
        core_grid.gpu_adapter()
        adapter_s = time.perf_counter() - a0
    loaded_rss = rusage.peak_rss_mb()
    records = []
    first_call = None
    for repeat in range(repeats):
        for label, inputs, settings in items:
            w0, c0 = time.perf_counter(), rusage.cpu_seconds()
            products = core_grid.invert(
                **inputs, **settings, device=device, precision=precision
            )
            wall = time.perf_counter() - w0
            cpu = rusage.cpu_seconds() - c0
            record = {
                "repeat": repeat,
                "label": label,
                "samples": int(inputs["data"].size),
                "gridded_count": int(products["stats"]["gridded_count"]),
                "wall": wall,
                "cpu": cpu,
                "rss_mb_after": rusage.peak_rss_mb(),
                "dirty_sha256": sha256_array(products["dirty"]),
                "psf_sha256": sha256_array(products["psf"]),
                "stats": products["stats"],
            }
            if "gpu" in products:
                record["gpu"] = products["gpu"]
            if first_call is None:
                first_call = dict(record)
            records.append(record)
            if save_images and repeat == 0:
                out = Path(save_images)
                out.mkdir(parents=True, exist_ok=True)
                np.save(out / f"{label}-dirty.npy", products["dirty"])
                np.save(out / f"{label}-psf.npy", products["psf"])
            gpu = record.get("gpu")
            extra = (
                f" gpu upload {gpu['upload_s']:.3f} compute {gpu['compute_s']:.3f} "
                f"download {gpu['download_s']:.3f} setup {gpu['context_s'] + gpu['compile_s']:.3f}"
                if gpu
                else ""
            )
            print(
                f"{label:40s} r{repeat} wall {wall:7.3f}s cpu {cpu:7.3f}s{extra}",
                flush=True,
            )
    result = {
        "backend": core.backend_name(),
        "library": str(core.library_path()),
        "device": device,
        "precision": precision,
        "rayon_num_threads": os.environ.get("RAYON_NUM_THREADS"),
        "repeats": repeats,
        "records": records,
        "first_call": first_call,
        "max_rss_mb": rusage.peak_rss_mb(),
        "rss_mb_after_loading_inputs": loaded_rss,
        "loadavg_before_after": [load_before, loadavg()],
        "total_wall": sum(r["wall"] for r in records),
        "total_cpu": sum(r["cpu"] for r in records),
    }
    if device == "gpu":
        result["adapter"] = core_grid.gpu_adapter()
        result["adapter_s"] = adapter_s
    write_json(output, result)
    return result


def gpu_memory_used_mib():
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    used, total = (float(v) for v in out.stdout.split("\n")[0].split(","))
    return used, total


class GpuSampler:
    """Peak of `nvidia-smi` memory.used while a child process runs."""

    def __init__(self, interval=0.05):
        self.interval = interval
        self.samples = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            value = gpu_memory_used_mib()
            if value is None:
                return
            self.samples.append(value[0])
            self._stop.wait(self.interval)

    def __enter__(self):
        self.before = gpu_memory_used_mib()
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()
        self.after = gpu_memory_used_mib()

    def summary(self):
        if not self.samples or self.before is None:
            return None
        return {
            "before_mib": self.before[0],
            "total_mib": self.before[1],
            "peak_mib": max(self.samples),
            "peak_increase_mib": max(self.samples) - self.before[0],
            "after_mib": self.after[0] if self.after else None,
            "n_samples": len(self.samples),
        }


CONFIGS = {
    "cpu-t1": {"device": "cpu", "precision": "f64", "threads": "1"},
    "cpu-t16": {"device": "cpu", "precision": "f64", "threads": "16"},
    "gpu-f64": {"device": "gpu", "precision": "f64", "threads": "16"},
    "gpu-f32": {"device": "gpu", "precision": "f32", "threads": "16"},
}


def bench(directory, out_dir, configs, repeats, labels=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    runs = []
    for repeat in range(repeats):
        for name in configs:
            config = CONFIGS[name]
            env = dict(os.environ)
            env["RAYON_NUM_THREADS"] = config["threads"]
            env["OPENBLAS_NUM_THREADS"] = "1"
            output = out_dir / f"{name}-r{repeat}.json"
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "time",
                str(directory),
                str(output),
                "--device",
                config["device"],
                "--precision",
                config["precision"],
            ]
            if labels:
                command += ["--labels", ",".join(labels)]
            if repeat == 0:
                command += ["--save-images", str(out_dir / f"images-{name}")]
            started = time.perf_counter()
            with GpuSampler() as sampler:
                code = subprocess.run(command, check=False, env=env).returncode
            wall = time.perf_counter() - started
            if code:
                raise SystemExit(f"{name} repeat {repeat} failed with {code}")
            payload = json.loads(output.read_text())
            payload["process_wall"] = wall
            payload["gpu_memory"] = sampler.summary()
            write_json(output, payload)
            runs.append({"config": name, "repeat": repeat, "file": output.name})
            print(
                f"{name:8s} r{repeat} process {wall:7.2f}s images "
                f"{payload['total_wall']:7.2f}s rss {payload['max_rss_mb']:.0f} MB "
                f"gpu {payload['gpu_memory']}",
                flush=True,
            )
    write_json(out_dir / "runs.json", {"runs": runs, "configs": configs})
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    k = sub.add_parser("k-replay")
    k.add_argument("out")
    ki = sub.add_parser("k-inputs")
    ki.add_argument("out")
    ki.add_argument("--inputs")
    a = sub.add_parser("array-inputs")
    a.add_argument("out")
    t = sub.add_parser("time")
    t.add_argument("inputs")
    t.add_argument("output")
    t.add_argument("--device", default="cpu", choices=("cpu", "gpu"))
    t.add_argument("--precision", default="f64", choices=("f64", "f32"))
    t.add_argument("--repeats", type=int, default=1)
    t.add_argument("--labels")
    t.add_argument("--save-images")
    b = sub.add_parser("bench")
    b.add_argument("inputs")
    b.add_argument("out_dir")
    b.add_argument("--configs", default="cpu-t1,cpu-t16,gpu-f64,gpu-f32")
    b.add_argument("--repeats", type=int, default=3)
    b.add_argument("--labels")
    c = sub.add_parser("compare")
    c.add_argument("reference")
    c.add_argument("candidate")
    c.add_argument("output")
    args = parser.parse_args(argv)
    labels = args.labels.split(",") if getattr(args, "labels", None) else None
    if args.command == "k-replay":
        return k_replay(args.out)
    if args.command == "k-inputs":
        return k_inputs(args.out, args.inputs)
    if args.command == "array-inputs":
        return array_inputs(args.out)
    if args.command == "time":
        time_inputs(
            args.inputs,
            args.output,
            args.device,
            args.precision,
            args.repeats,
            labels,
            args.save_images,
        )
        return 0
    if args.command == "bench":
        configs = args.configs.split(",")
        for name in configs:
            if name not in CONFIGS:
                raise SystemExit(f"unknown configuration {name}")
        return bench(args.inputs, args.out_dir, configs, args.repeats, labels)
    return compare(args.reference, args.candidate, args.output)


if __name__ == "__main__":
    sys.exit(main())
