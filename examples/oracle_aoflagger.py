"""AOFlagger 3.5 as a second SumThreshold oracle (research/a-flag-aoflagger.md).

Host commands (worktree venv; they start the pinned container
`rang-aflag-aoflagger:3.5.0` with `--network none`):

    python examples/oracle_aoflagger.py stages <oracle-run> <strategy-dir> outputs/<fresh>
    python examples/oracle_aoflagger.py hybrid <dump-dir> outputs/<fresh>
    python examples/oracle_aoflagger.py chain  <oracle-run> <strategy-dir> <variant> outputs/<fresh> [<host-run>]
    python examples/oracle_aoflagger.py port-cost <oracle-run> <strategy-dir> <control> outputs/<dir>

- `stages`: every `sum_threshold` step of the four task D controls, isolated
  (input = the oracle's window flags before the step), with the mapped
  strategy (`tricolour-firstpass.lua`), the tuned strategy (`tuned.lua`) and
  the labelled ablation `tuned_plus` (tuned, one major iteration per call,
  with Tricolour's box smearing and fraction cuts applied between calls).
  One container run per variant and control, timed with `/usr/bin/time -v`.
- `hybrid`: the hybrid kernel test, Tricolour's per-pass residuals from
  `tools/oracles/aoflagger/tricolour_dump.py` normalised by Tricolour's
  thresholds and run through `hybrid.lua` (H1: padding missing; H2: padding
  and the pass's input flags missing).
- `chain`: the full CARACal strategy per control, `sum_threshold` steps by
  AOFlagger (`mapped`, `tuned`) or by the port (`port`, the harness gate),
  every other step by the port one step at a time.

Each command writes per-control `.npz` files, a `receipt.json` with SHA256
of every input and output, the image id, versions and timings.
The `container` command is what runs inside the image.
"""

import json
import os
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools/oracles/aoflagger"
IMAGE = "rang-aflag-aoflagger:3.5.0"
CONTROLS = (
    ("strategy-00-operational", "mk_rfi_flagging_calibrator_fields_firstpass.yaml"),
    ("strategy-00-holdout_masked", "mk_rfi_flagging_calibrator_fields_firstpass.yaml"),
    ("strategy-01-operational", "calibrator_mild_flagging.yaml"),
    ("strategy-01-holdout_masked", "calibrator_mild_flagging.yaml"),
)
LUA = {
    "mapped": "tricolour-firstpass.lua",
    "tuned": "tuned.lua",
    "tuned_plus": "tuned.lua",
    "hybrid": "hybrid.lua",
}
STAGE_VARIANTS = ("mapped", "tuned", "tuned_plus")


def file_sha256(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def lua_table(params):
    def value(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float, np.integer, np.floating)):
            return (
                repr(float(v)) if isinstance(v, (float, np.floating)) else str(int(v))
            )
        raise TypeError(v)

    return (
        "return {" + ", ".join(f"{k} = {value(v)}" for k, v in params.items()) + "}\n"
    )


# ------------------------------------------------------------ inside the image


def container(jobs_dir):
    """Run every job of `jobs.json` on the images of `inputs.npz`."""
    import aoflagger

    sys.path.insert(0, "/work/tools/oracles/aoflagger")
    import st_bridge

    jobs_dir = Path(jobs_dir)
    jobs = json.loads((jobs_dir / "jobs.json").read_text())
    inputs = np.load(jobs_dir / "inputs.npz")
    flagger = aoflagger.AOFlagger()
    outputs, timings = {}, {}
    for job in jobs:
        name = job["name"]
        params_path = jobs_dir / f"{name}.params.lua"
        params_path.write_text(lua_table(job["params"]))
        os.environ["RANG_AFLAG_PARAMS"] = str(params_path)
        strategy = flagger.load_strategy_file(job["lua"])
        images = inputs[f"{name}_img"]
        masks = inputs[f"{name}_mask"]
        n, height, width = images.shape
        out = np.zeros((n, height, width), bool)
        tic = time.perf_counter()
        for i in range(n):
            if job["kind"] == "tuned_plus":
                post = job["post"]
                nan = inputs[f"{name}_nan"][i]
                iter_flags = masks[i].copy()
                last = None
                for _ in range(post["num_major_iterations"]):
                    det = _run(flagger, strategy, images[i], iter_flags)
                    last = (
                        st_bridge.smear_and_cut(
                            det.T,
                            post["time_extend"],
                            post["freq_extend"],
                            post["flag_all_time_frac"],
                            post["flag_all_freq_frac"],
                        ).T
                        | nan
                    )
                    iter_flags |= last
                out[i] = last
            else:
                out[i] = _run(flagger, strategy, images[i], masks[i])
        timings[name] = time.perf_counter() - tic
        outputs[name] = out
    np.savez_compressed(jobs_dir / "outputs.npz", **outputs)
    (jobs_dir / "container.json").write_text(
        json.dumps(
            {
                "aoflagger_version": aoflagger.AOFlagger.get_version_string(),
                "aoflagger_date": aoflagger.AOFlagger.get_version_date(),
                "numpy_version": np.__version__,
                "python": sys.version,
                "timings": timings,
            },
            indent=1,
        )
        + "\n"
    )


def _run(flagger, strategy, image, mask):
    height, width = image.shape
    iset = flagger.make_image_set(width, height, 1)
    iset.set_image_buffer(0, np.ascontiguousarray(image, dtype=np.float32))
    fm = flagger.make_flag_mask(width, height, False)
    fm.set_buffer(np.ascontiguousarray(mask, dtype=bool))
    return np.array(strategy.run(iset, fm).get_buffer(), dtype=bool)


# ------------------------------------------------------------------- host side


def image_id():
    return subprocess.run(
        ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def run_container(jobs_dir, jobs, inputs, cpus=4):
    """Write the jobs and inputs, run the image once, return outputs and the
    `/usr/bin/time -v` record."""
    jobs_dir.mkdir(parents=True)
    (jobs_dir / "jobs.json").write_text(json.dumps(jobs, indent=1) + "\n")
    np.savez(jobs_dir / "inputs.npz", **inputs)
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cpus",
        str(cpus),
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-v",
        f"{ROOT}:/work:ro",
        "-v",
        f"{jobs_dir.resolve()}:/jobs",
        IMAGE,
        "/usr/bin/time",
        "-v",
        "-o",
        "/jobs/time.txt",
        "python3",
        "/work/examples/oracle_aoflagger.py",
        "container",
        "/jobs",
    ]
    tic = time.perf_counter()
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    wall = time.perf_counter() - tic
    (jobs_dir / "container.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError(
            f"container failed ({proc.returncode}): {proc.stderr[-2000:]}"
        )
    timing = parse_time((jobs_dir / "time.txt").read_text())
    timing["docker_wall"] = wall
    outputs = np.load(jobs_dir / "outputs.npz")
    return {k: outputs[k] for k in outputs.files}, timing


def parse_time(text):
    keys = {
        "Elapsed (wall clock) time (h:mm:ss or m:ss)": "wall",
        "Maximum resident set size (kbytes)": "max_rss_kb",
        "Percent of CPU this job got": "cpu_percent",
        "User time (seconds)": "user",
        "System time (seconds)": "system",
    }
    out = {}
    for line in text.splitlines():
        key, _, value = line.strip().rpartition(": ")
        if key in keys:
            value = value.strip().rstrip("%")
            if keys[key] == "wall":
                parts = [float(p) for p in value.split(":")]
                value = sum(p * 60**i for i, p in enumerate(reversed(parts)))
            out[keys[key]] = float(value)
    return out


def load_strategy(strategy_dir, name):
    sys.path.insert(0, str(ROOT / "python"))
    from rang import core_flag

    return core_flag.parse_strategy((Path(strategy_dir) / name).read_text())


def st_params(kwargs):
    from rang import core_flag

    params = dict(core_flag.SUM_THRESHOLD_DEFAULTS)
    params.update(kwargs)
    return params


def stage_inputs(intensity, before):
    """Images `(nbl, nchan, ntime)` (NaN -> 0) and masks for one step."""
    vis = np.abs(intensity[:, 0]).astype(np.float32)  # (nbl, ntime, nchan), imag is 0
    nan = np.isnan(vis)
    images = np.where(nan, np.float32(0), vis).transpose(0, 2, 1).copy()
    masks = np.asarray(before[:, 0], bool).transpose(0, 2, 1).copy()
    return images, masks, nan.transpose(0, 2, 1).copy()


def stage_jobs(variant, label, strategies, intensity, stages):
    names = list(stages.files)
    ntime = intensity.shape[2]
    jobs, inputs = [], {}
    for k, step in enumerate(strategies):
        if step["task"] != "sum_threshold":
            continue
        p = st_params(step.get("kwargs") or {})
        images, masks, nan = stage_inputs(intensity, stages[names[k - 1]])
        name = f"s{k:02d}"
        params = {
            "ntime": ntime,
            "outlier_nsigma": p["outlier_nsigma"],
            "spike_width_time": p["spike_width_time"],
            "spike_width_freq": p["spike_width_freq"],
            "num_major_iterations": 1
            if variant == "tuned_plus"
            else p["num_major_iterations"],
        }
        job = {
            "name": name,
            "lua": f"/work/tools/oracles/aoflagger/{LUA[variant]}",
            "params": params,
            "kind": "tuned_plus" if variant == "tuned_plus" else "stage",
            "step": names[k],
        }
        if variant == "tuned_plus":
            job["post"] = {
                key: p[key]
                for key in (
                    "time_extend",
                    "freq_extend",
                    "flag_all_time_frac",
                    "flag_all_freq_frac",
                    "num_major_iterations",
                )
            }
            inputs[f"{name}_nan"] = nan
        jobs.append(job)
        inputs[f"{name}_img"] = images
        inputs[f"{name}_mask"] = masks
    return jobs, inputs


def stage_result(outputs, jobs, intensity, stages):
    """Window flags after each step: before | detections | NaN."""
    names = list(stages.files)
    nan = np.isnan(np.abs(intensity[:, 0]))
    result = {}
    for job in jobs:
        k = names.index(job["step"])
        det = outputs[job["name"]].transpose(0, 2, 1)
        before = np.asarray(stages[names[k - 1]][:, 0], bool)
        result[job["step"]] = (before | det | nan)[:, None]
    return result


def cmd_stages(oracle, strategy_dir, out):
    out.mkdir(parents=True, exist_ok=False)
    receipt = {
        "command": "stages",
        "oracle": str(oracle),
        "image": IMAGE,
        "image_id": image_id(),
        "lua": {v: file_sha256(TOOLS / LUA[v]) for v in STAGE_VARIANTS},
        "st_bridge": file_sha256(TOOLS / "st_bridge.py"),
        "inputs": {},
        "outputs": {},
        "timings": {},
        "load": os.getloadavg(),
    }
    for label, strategy_name in CONTROLS:
        strategies = load_strategy(strategy_dir, strategy_name)
        intensity = np.load(oracle / label / "intensity.npz")["intensity"]
        stages = np.load(oracle / label / "stages.npz")
        receipt["inputs"][label] = {
            n: file_sha256(oracle / label / n) for n in ("intensity.npz", "stages.npz")
        }
        for variant in STAGE_VARIANTS:
            jobs, inputs = stage_jobs(variant, label, strategies, intensity, stages)
            outputs, timing = run_container(
                out / "jobs" / variant / label, jobs, inputs
            )
            result = stage_result(outputs, jobs, intensity, stages)
            path = out / variant / f"{label}.npz"
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, **result)
            receipt["outputs"][f"{variant}/{label}"] = file_sha256(path)
            inner = json.loads(
                (out / "jobs" / variant / label / "container.json").read_text()
            )
            timing["job_seconds"] = inner["timings"]
            receipt["aoflagger_version"] = inner["aoflagger_version"]
            receipt["timings"][f"{variant}/{label}"] = timing
            print(
                variant,
                label,
                f"{timing['wall']:.2f} s",
                f"{timing['max_rss_kb'] / 1024:.0f} MB",
                f"{timing['cpu_percent']:.0f}%",
                flush=True,
            )
            for f in (out / "jobs" / variant / label).glob("inputs.npz"):
                f.unlink()  # regenerable from the oracle run; keep the jobs and outputs
    receipt["load_end"] = os.getloadavg()
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")


# --------------------------------------------------------------------- hybrid


def hybrid_images(dump, key, meta, which, vertical=False):
    """Normalised residual images and missing masks for one pass of one step.

    Every column of the bridge (a channel's time series, or a (row, chunk)
    padded frequency slice) is one image row, so AOFlagger's horizontal pass
    slides along it (see hybrid.lua for why). With `vertical`, each column is
    instead a width-1 image (height = slice), for the VerticalStacked check.
    Returns `images (m, H, W)`, `missing (m, H, W)` and the bookkeeping to map
    AOFlagger's output back to `(nbl, niter, nrow, nchan)`.
    """
    sys.path.insert(0, str(TOOLS))
    import st_bridge

    data = dump[f"{key}_data"]
    flags = dump[f"{key}_flags"]
    thr = dump[f"{key}_thr"]
    nbl, niter = data.shape[:2]
    pas = key.split("_")[1]
    images, missing, books = [], [], []
    for b in range(nbl):
        for i in range(niter):
            if pas == "time":
                values, valid, t = st_bridge.time_columns(data[b, i], thr[b, i])
                index = None
                miss = np.zeros(values.shape, bool)
                if which == "H2":
                    miss = np.asarray(flags[b, i], bool).T.copy()
            else:
                windows = meta["windows_freq"]
                values, valid, t, index = st_bridge.chunk_columns(
                    data[b, i],
                    thr[b, i],
                    np.asarray(meta["freq_chunk_ends"]),
                    int(max(windows)),
                )
                miss = ~valid
                if which == "H2":
                    miss = miss | st_bridge.chunk_missing(
                        flags[b, i], index, values.shape[1]
                    )
            z = st_bridge.normalise(values, t)
            if vertical:
                for c in range(z.shape[0]):
                    images.append(z[c][:, None].copy())
                    missing.append(miss[c][:, None].copy())
                    books.append((b, i, index, c))
            else:
                images.append(z)  # (columns, length): x runs along each column
                missing.append(miss)
                books.append((b, i, index, None))
    return images, missing, books


def direction_check():
    """Synthetic self-check of the hybrid layout: a horizontal and a vertical
    run of 8 samples at 0.6 chi_1 on zeros (only L = 8 detects them)."""
    img = np.zeros((64, 32), np.float32)
    img[10, 4:12] = 0.6
    img[30:38, 20] = 0.6
    return img, np.zeros(img.shape, bool)


def cmd_hybrid(dump_dir, out):
    out.mkdir(parents=True, exist_ok=False)
    receipt = {
        "command": "hybrid",
        "dump": str(dump_dir),
        "image": IMAGE,
        "image_id": image_id(),
        "lua": file_sha256(TOOLS / LUA["hybrid"]),
        "inputs": {},
        "outputs": {},
        "timings": {},
        "load": os.getloadavg(),
    }
    dump_receipt = json.loads((dump_dir / "receipt.json").read_text())
    sys.path.insert(0, str(TOOLS))
    import st_bridge

    for label, _ in CONTROLS:
        path = dump_dir / f"dump-{label}.npz"
        receipt["inputs"][label] = file_sha256(path)
        dump = np.load(path)
        lua = "/work/tools/oracles/aoflagger/hybrid.lua"
        img, miss = direction_check()
        jobs = [
            {
                "name": "direction_check_h",
                "lua": lua,
                "params": {"vertical": False},
                "kind": "plain",
            },
            {
                "name": "direction_check_v",
                "lua": lua,
                "params": {"vertical": True},
                "kind": "plain",
            },
        ]
        inputs = {
            f"{j['name']}_{s}": a[None]
            for j in jobs
            for s, a in (("img", img), ("mask", miss))
        }
        books_all = {}
        for step, info in dump_receipt["controls"][label].items():
            meta = info["meta"]
            for pas in ("spec", "time", "freq"):
                key = f"{step}_{pas}"
                for which in ("H1", "H2"):
                    for vertical in (False, True) if pas != "time" else (False,):
                        images, missing, books = hybrid_images(
                            dump, key, meta, which, vertical
                        )
                        name = f"{key}_{which}" + ("v" if vertical else "")
                        shapes = {im.shape for im in images}
                        if len(shapes) != 1:
                            raise RuntimeError(
                                f"{name}: images of different shapes {shapes}"
                            )
                        inputs[f"{name}_img"] = np.stack(images)
                        inputs[f"{name}_mask"] = np.stack(missing)
                        jobs.append(
                            {
                                "name": name,
                                "lua": lua,
                                "params": {"vertical": vertical},
                                "kind": "plain",
                            }
                        )
                        books_all[name] = (books, dump[f"{key}_data"].shape)
        outputs, timing = run_container(out / "jobs" / label, jobs, inputs)
        check_h, check_v = (
            outputs["direction_check_h"][0],
            outputs["direction_check_v"][0],
        )
        receipt.setdefault("direction_check", {})[label] = {
            "horizontal_job": {
                "horizontal_run": bool(check_h[10, 4:12].all()),
                "vertical_run": bool(check_h[30:38, 20].all()),
            },
            "vertical_job": {
                "horizontal_run": bool(check_v[10, 4:12].all()),
                "vertical_run": bool(check_v[30:38, 20].all()),
            },
        }
        result = {}
        for name, (books, shape) in books_all.items():
            flags = np.zeros(shape, bool)
            raw = outputs[name]
            columns = {}
            for m, (b, i, index, c) in enumerate(books):
                if c is None:
                    cols = raw[m]
                else:
                    # Width-1 images exist only for the chunk passes.
                    columns.setdefault((b, i), []).append(raw[m][:, 0])
                    if c != len(index) - 1:
                        continue
                    cols = np.stack(columns.pop((b, i)))
                if index is None:
                    flags[b, i] = cols.T
                else:
                    flags[b, i] = st_bridge.chunk_flags_back(
                        cols, index, shape[2], shape[3]
                    )
            result[name] = flags
        dest = out / f"hybrid-{label}.npz"
        np.savez_compressed(dest, **result)
        receipt["outputs"][label] = file_sha256(dest)
        receipt["timings"][label] = timing
        (out / "jobs" / label / "inputs.npz").unlink()
        print(label, f"{timing['wall']:.1f} s", flush=True)
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")


# ---------------------------------------------------------------------- chain


def expand(window, ubl_index, time_inv, ncorr):
    """Window flags `(nbl, 1, ntime, nchan)` to row flags `(row, chan, corr)`."""
    rows = window[ubl_index, 0, time_inv, :]
    return np.repeat(rows[:, :, None], ncorr, axis=2)


def port_step(arrays, masks, ubl_index, time_inv, step, window):
    """One strategy step through the port, from window flags to window flags."""
    from rang import core_flag

    res = core_flag.flag_rows(
        arrays["DATA"],
        expand(window, ubl_index, time_inv, arrays["DATA"].shape[2]),
        arrays["ANTENNA1"],
        arrays["ANTENNA2"],
        arrays["TIME"],
        arrays["antenna_position"],
        arrays["chan_freq"],
        arrays["chan_width"],
        arrays["corr_type"],
        [step],
        masks=masks,
        want_intensity=False,
    )
    return np.array(next(iter(res["stages"].values())), bool)


def cmd_chain(oracle, strategy_dir, variant, out, host_run=None):
    from rang import core_flag

    out.mkdir(parents=True, exist_ok=False)
    receipt = {
        "command": "chain",
        "variant": variant,
        "oracle": str(oracle),
        "image": IMAGE,
        "image_id": image_id() if variant != "port" else None,
        "inputs": {},
        "outputs": {},
        "timings": {},
        "load": os.getloadavg(),
    }
    masks = [core_flag.load_static_mask(p) for p in core_flag.static_mask_files()]
    for label, strategy_name in CONTROLS:
        strategies = load_strategy(strategy_dir, strategy_name)
        arrays = np.load(oracle / label / "arrays.npz")
        intensity = np.load(oracle / label / "intensity.npz")["intensity"]
        receipt["inputs"][label] = {
            n: file_sha256(oracle / label / n) for n in ("arrays.npz", "intensity.npz")
        }
        ubl = core_flag.unique_baselines(arrays["ANTENNA1"], arrays["ANTENNA2"])
        lookup = {(int(a1), int(a2)): b for b, (a1, a2) in enumerate(ubl)}
        ubl_index = np.array(
            [
                lookup[(int(a1), int(a2))]
                for a1, a2 in zip(arrays["ANTENNA1"], arrays["ANTENNA2"])
            ]
        )
        _, time_inv = np.unique(arrays["TIME"], return_inverse=True)
        ncorr = arrays["DATA"].shape[2]
        # The original packed window flags: OR over correlations, cells
        # without a row stay flagged (Tricolour's packing).
        original = np.ones(intensity.shape, bool)
        packed = np.any(arrays["FLAG"], axis=2)
        original[ubl_index, 0, time_inv, :] = packed
        window = original.copy()
        stages = {}
        tic = time.perf_counter()
        ao_seconds = 0.0
        for k, step in enumerate(strategies):
            name = f"{k:02d}-{step['task']}"
            if step["task"] == "combine_with_input_flags":
                window = window | original
            elif step["task"] == "sum_threshold" and variant != "port":
                jobs, inputs = stage_jobs(
                    variant,
                    label,
                    [{"task": "x"}] * k + [step],
                    intensity,
                    _Stages(window, k, name),
                )
                outputs, timing = run_container(
                    out / "jobs" / label / name, jobs, inputs
                )
                ao_seconds += timing["wall"]
                det = outputs[jobs[0]["name"]].transpose(0, 2, 1)
                window = window | det[:, None] | np.isnan(np.abs(intensity))
                (out / "jobs" / label / name / "inputs.npz").unlink()
            else:
                window = port_step(arrays, masks, ubl_index, time_inv, step, window)
            stages[name] = window.copy()
        final = expand(window, ubl_index, time_inv, ncorr)
        np.savez_compressed(out / f"{label}.npz", FLAG=final, **stages)
        receipt["outputs"][label] = file_sha256(out / f"{label}.npz")
        receipt["timings"][label] = {
            "total": time.perf_counter() - tic,
            "aoflagger_container_wall": ao_seconds,
        }
        if host_run is not None:
            after = np.load(Path(host_run) / "native" / label / "after-native.npz")[
                "FLAG"
            ]
            receipt.setdefault("after_native_differences", {})[label] = int(
                np.count_nonzero(final != after)
            )
        print(
            label,
            variant,
            f"{receipt['timings'][label]['total']:.1f} s",
            receipt.get("after_native_differences", {}).get(label),
            flush=True,
        )
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")


def cmd_port_cost(oracle, strategy_dir, label, out):
    """The port on the same isolated `sum_threshold` steps as `stages` (one
    step per `flag_rows` call), for the cost comparison; also checks that each
    step reproduces the oracle's window flags."""
    from rang import core_flag

    out.mkdir(parents=True, exist_ok=True)
    strategy_name = dict(CONTROLS)[label]
    strategies = load_strategy(strategy_dir, strategy_name)
    arrays = np.load(oracle / label / "arrays.npz")
    stages = np.load(oracle / label / "stages.npz")
    names = list(stages.files)
    masks = [core_flag.load_static_mask(p) for p in core_flag.static_mask_files()]
    ubl = core_flag.unique_baselines(arrays["ANTENNA1"], arrays["ANTENNA2"])
    lookup = {(int(a1), int(a2)): b for b, (a1, a2) in enumerate(ubl)}
    ubl_index = np.array(
        [
            lookup[(int(a1), int(a2))]
            for a1, a2 in zip(arrays["ANTENNA1"], arrays["ANTENNA2"])
        ]
    )
    _, time_inv = np.unique(arrays["TIME"], return_inverse=True)
    ncorr = arrays["DATA"].shape[2]
    record = {
        "label": label,
        "rayon_threads": os.environ.get("RAYON_NUM_THREADS"),
        "steps": {},
        "load": os.getloadavg(),
    }
    tic = time.perf_counter()
    for k, step in enumerate(strategies):
        if step["task"] != "sum_threshold":
            continue
        flags = expand(stages[names[k - 1]], ubl_index, time_inv, ncorr)
        res = core_flag.flag_rows(
            arrays["DATA"],
            flags,
            arrays["ANTENNA1"],
            arrays["ANTENNA2"],
            arrays["TIME"],
            arrays["antenna_position"],
            arrays["chan_freq"],
            arrays["chan_width"],
            arrays["corr_type"],
            [step],
            masks=masks,
            want_intensity=False,
        )
        window = np.array(next(iter(res["stages"].values())), bool)
        record["steps"][names[k]] = {
            "core_seconds": res["seconds"],
            "equals_oracle": bool(np.array_equal(window, stages[names[k]])),
        }
    record["total_wall"] = time.perf_counter() - tic
    record["core_seconds"] = sum(v["core_seconds"] for v in record["steps"].values())
    (out / f"port-{label}-rayon{record['rayon_threads']}.json").write_text(
        json.dumps(record, indent=1) + "\n"
    )
    print(
        label,
        record["rayon_threads"],
        f"{record['core_seconds']:.3f} s core",
        all(v["equals_oracle"] for v in record["steps"].values()),
        flush=True,
    )


class _Stages:
    """The two window arrays `stage_jobs` needs for one step of the chain."""

    def __init__(self, window, k, name):
        self.files = [f"{i:02d}-prev" for i in range(k)] + [name]
        self._window = window

    def __getitem__(self, key):
        return self._window


def main():
    command = sys.argv[1]
    if command == "container":
        container(sys.argv[2])
    elif command == "stages":
        cmd_stages(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    elif command == "hybrid":
        cmd_hybrid(Path(sys.argv[2]), Path(sys.argv[3]))
    elif command == "port-cost":
        cmd_port_cost(
            Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], Path(sys.argv[5])
        )
    elif command == "chain":
        host_run = sys.argv[6] if len(sys.argv) > 6 else None
        cmd_chain(
            Path(sys.argv[2]),
            Path(sys.argv[3]),
            sys.argv[4],
            Path(sys.argv[5]),
            host_run,
        )
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
