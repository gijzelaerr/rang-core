"""Tricolour 0.5.0-dev oracle and comparator for task RV1 (research/rv1-revalidate.md).

Usage:
    # T1 / T3, in a venv with tricolour 0.5.0-dev (or a PR head) and python-casacore:
    python examples/oracle_tricolour_050.py oracle <host-run> <strategy-dir> outputs/<fresh>
    # T2, the same venv; runs the `tricolour` CLI on copies of the diagnostic MSs:
    python examples/oracle_tricolour_050.py cli <host-run> <strategy-dir> outputs/<fresh>
    # comparison, any venv with NumPy:
    python examples/oracle_tricolour_050.py compare <oracle-021> <host-run> outputs/<fresh> \
        --t1 DIR [--t0 DIR] [--t2 DIR] [--t3 DIR]

`oracle` is examples/oracle_tricolour.py for the 0.5.0 branch: it reads each
archived control's diagnostic Measurement Set read-only (with UVW, which the
0.5.0 `apply_static_mask` needs) and `before-native.npz`, packs windows with
0.2.1's sorted baseline order and time index, and calls the unmodified
`tricolour.core.kernels` functions step by step as
`tricolour.core.application.implementation.Flagger.flag` chains them for the
`polarisation` strategy. It writes the 0.2.1 oracle's layout (receipt with
`host_hashes`, `arrays.npz`, `intensity.npz`, `stages.npz`, `final.npz`) so
`examples/compare_core_flags.py run` accepts it, plus the commit and the
compiled Numba signatures. `cli` copies each `diagnostic.ms` into the run
directory, writes `before-native.npz` FLAG into the copy and runs
`tricolour <copy> -fs polarisation -c <strategy> -nw 4 -tc 100`. Neither mode
writes to the host run.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

CONTROLS = (
    ("strategy-00-operational", "mk_rfi_flagging_calibrator_fields_firstpass.yaml"),
    ("strategy-00-holdout_masked", "mk_rfi_flagging_calibrator_fields_firstpass.yaml"),
    ("strategy-01-operational", "calibrator_mild_flagging.yaml"),
    ("strategy-01-holdout_masked", "calibrator_mild_flagging.yaml"),
)
CLI_TIMEOUT = 1800


def tree_sha256(path):
    files = sorted(
        p for p in Path(path).rglob("*") if p.is_file() and p.name != "table.lock"
    )
    digest = sha256()
    for p in files:
        digest.update(p.relative_to(path).as_posix().encode())
        digest.update(p.read_bytes())
    return digest.hexdigest()


def file_sha256(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def host_hashes(host_run):
    out = {}
    for label, _ in CONTROLS:
        directory = host_run / "native" / label
        out[label] = {
            "before-native.npz": file_sha256(directory / "before-native.npz"),
            "after-native.npz": file_sha256(directory / "after-native.npz"),
            "diagnostic.ms": tree_sha256(directory / "diagnostic.ms"),
        }
    return out


def loadavg():
    return float(Path("/proc/loadavg").read_text().split()[0])


def tricolour_provenance():
    import importlib.metadata as md

    dist = md.distribution("tricolour")
    direct = dist.read_text("direct_url.json")
    return {
        "version": dist.version,
        "direct_url": json.loads(direct) if direct else None,
    }


# --- T1 / T3: the kernel chain ------------------------------------------------


def read_ms(ms):
    from casacore.tables import table

    with table(str(ms), readonly=True, ack=False, lockoptions="autonoread") as t:
        arrays = {
            name: np.ascontiguousarray(t.getcol(name))
            for name in ("DATA", "ANTENNA1", "ANTENNA2", "TIME", "FLAG_ROW", "UVW")
        }
        for name in ("FIELD_ID", "SCAN_NUMBER", "DATA_DESC_ID"):
            arrays[name] = t.getcol(name)
    with table(
        f"{ms}::ANTENNA", readonly=True, ack=False, lockoptions="autonoread"
    ) as t:
        arrays["antenna_position"] = t.getcol("POSITION")
        names = list(t.getcol("NAME"))
    with table(
        f"{ms}::SPECTRAL_WINDOW", readonly=True, ack=False, lockoptions="autonoread"
    ) as t:
        arrays["chan_freq"] = t.getcol("CHAN_FREQ")[0]
        arrays["chan_width"] = t.getcol("CHAN_WIDTH")[0]
    with table(
        f"{ms}::POLARIZATION", readonly=True, ack=False, lockoptions="autonoread"
    ) as t:
        arrays["corr_type"] = t.getcol("CORR_TYPE")[0]
    return arrays, names


def numba_signatures(module):
    return {
        name: len(getattr(module, name).signatures)
        for name in sorted(dir(module))
        if hasattr(getattr(module, name), "signatures")
    }


def run_control(host_run, strategy_path, label, out, masks):
    import yaml
    from tricolour.core.kernels.flagging import (
        apply_static_mask,
        flag_autos,
        flag_nans_and_zeros,
        sum_threshold_flagger,
        uvcontsub_flagger,
    )
    from tricolour.core.kernels.stokes import polarised_intensity, stokes_corr_map

    directory = host_run / "native" / label
    arrays, antenna_names = read_ms(directory / "diagnostic.ms")
    after = np.load(directory / "after-native.npz")
    flags_in = np.load(directory / "before-native.npz")["FLAG"]
    groups = set(
        zip(
            arrays["FIELD_ID"].tolist(),
            arrays["DATA_DESC_ID"].tolist(),
            arrays["SCAN_NUMBER"].tolist(),
        )
    )
    if len(groups) != 1:
        raise RuntimeError(f"{label}: expected one field/ddid/scan group, got {groups}")
    data, ant1, ant2 = arrays["DATA"], arrays["ANTENNA1"], arrays["ANTENNA2"]
    nrow, nchan, ncorr = data.shape
    timings = {}

    # 0.2.1's sorted unique baselines (ubl) and time index, so windows are
    # comparable element for element with the archived oracle.
    bl = np.stack([ant1, ant2], axis=1).astype(np.int32).view(np.int64)
    ubl = np.unique(bl).view(np.int32).reshape(-1, 2)
    ubl = np.concatenate([np.arange(ubl.shape[0], dtype=ubl.dtype)[:, None], ubl], 1)
    utime, time_inv = np.unique(arrays["TIME"], return_inverse=True)
    ntime, nbl = utime.shape[0], ubl.shape[0]
    row_bl = np.empty(nrow, np.int64)
    for b, a1, a2 in ubl:
        row_bl[(ant1 == a1) & (ant2 == a2)] = b
    if len(set(zip(row_bl.tolist(), time_inv.tolist()))) != nrow:
        raise RuntimeError(f"{label}: duplicate (baseline, time) rows")

    # Flagger.flag: (baseline, polarization, time, frequency) windows. The MSv4
    # reader marks absent cells flagged; there are none here (checked below).
    tic = time.perf_counter()
    bp_vis = np.full((nbl, ncorr, ntime, nchan), np.nan + np.nan * 1j, data.dtype)
    bp_flags = np.ones((nbl, ncorr, ntime, nchan), bool)
    bp_uvw = np.zeros((nbl, ntime, 3), np.float64)
    bp_vis[row_bl, :, time_inv, :] = data.transpose(0, 2, 1)
    bp_flags[row_bl, :, time_inv, :] = flags_in.transpose(0, 2, 1)
    bp_uvw[row_bl, time_inv, :] = arrays["UVW"]
    present = np.zeros((nbl, ntime), bool)
    present[row_bl, time_inv] = True
    timings["pack"] = time.perf_counter() - tic

    corr_type = arrays["corr_type"].tolist()
    stokes_map = stokes_corr_map(corr_type)
    stokes_pol = tuple(v for k, v in stokes_map.items() if k != "I")
    tic = time.perf_counter()
    bp_vis = polarised_intensity(bp_vis, stokes_pol)
    timings["polarised_intensity"] = time.perf_counter() - tic
    bp_flags = np.any(bp_flags, axis=1, keepdims=True)
    bp_flags = np.require(bp_flags, None, ["C", "W"])
    bp_vis = np.require(bp_vis, None, "C")
    original = bp_flags.copy()

    strategies = yaml.full_load(Path(strategy_path).read_text())["strategies"]
    chan_freq = arrays["chan_freq"]
    chan_width = np.broadcast_to(arrays["chan_width"], chan_freq.shape)
    stages = {}
    for index, strategy in enumerate(strategies):
        task = strategy["task"]
        kwargs = strategy.get("kwargs", {})
        tic = time.perf_counter()
        if task == "sum_threshold":
            new_flags = sum_threshold_flagger(bp_vis, bp_flags, **kwargs)
            np.logical_or(bp_flags, new_flags, out=bp_flags)
        elif task == "uvcontsub_flagger":
            bp_flags = uvcontsub_flagger(bp_vis, bp_flags, **kwargs)
        elif task == "flag_autos":
            np.logical_or(bp_flags, flag_autos(bp_flags, ubl), out=bp_flags)
        elif task == "combine_with_input_flags":
            np.logical_or(bp_flags, original, out=bp_flags)
        elif task == "unflag":
            bp_flags[...] = 0
        elif task == "flag_nans_zeros":
            bp_flags = flag_nans_and_zeros(bp_vis, bp_flags)
        elif task == "apply_static_mask":
            new_flags = apply_static_mask(
                bp_flags, bp_uvw, masks, chan_freq, chan_width, **kwargs
            )
            mode = kwargs.get("accumulation_mode", "<none>").strip()
            if mode == "or":
                np.logical_or(bp_flags, new_flags, out=bp_flags)
            elif mode == "override":
                bp_flags = new_flags
            else:
                raise ValueError(f"accumulation_mode {mode}")
        else:
            raise ValueError(f"Invalid task {task}")
        name = f"{index:02d}-{task}"
        timings[name] = time.perf_counter() - tic
        # A copy: the 0.5.0 executor updates bp_flags in place, so a view would
        # alias later steps (post-hoc fix, research/rv1-revalidate.md section 6).
        stages[name] = np.array(bp_flags, dtype=bool, order="C", copy=True)

    bp_flags = np.any(bp_flags, axis=1, keepdims=True)
    bp_flags = np.broadcast_to(bp_flags, (nbl, ncorr, ntime, nchan))
    final = np.ascontiguousarray(bp_flags[row_bl, :, time_inv, :].transpose(0, 2, 1))
    differences = int(np.count_nonzero(final != after["FLAG"]))

    control_dir = out / label
    control_dir.mkdir()
    np.savez(
        control_dir / "arrays.npz",
        DATA=data,
        ANTENNA1=ant1,
        ANTENNA2=ant2,
        TIME=arrays["TIME"],
        UVW=arrays["UVW"],
        FLAG=flags_in,
        FLAG_ROW=arrays["FLAG_ROW"],
        antenna_position=arrays["antenna_position"],
        chan_freq=arrays["chan_freq"],
        chan_width=arrays["chan_width"],
        corr_type=arrays["corr_type"],
        ubl=ubl,
        time_inv=time_inv.astype(np.int64),
    )
    np.savez(control_dir / "intensity.npz", intensity=bp_vis)
    np.savez_compressed(control_dir / "stages.npz", **stages)
    np.savez_compressed(control_dir / "final.npz", FLAG=final)
    uv = np.linalg.norm(arrays["UVW"], axis=1)
    return {
        "strategy": Path(strategy_path).name,
        "strategy_sha256": file_sha256(strategy_path),
        "rows": nrow,
        "channels": nchan,
        "correlations": ncorr,
        "baselines": nbl,
        "times": ntime,
        "absent_cells": int((~present).sum()),
        "antenna_names": antenna_names,
        "uvw_length_range_m": [float(uv.min()), float(uv.max())],
        "stages": list(stages),
        "stage_fractions": {k: float(v.mean()) for k, v in stages.items()},
        "final_fraction": float(final.mean()),
        "after_native_fraction": float(after["FLAG"].mean()),
        "final_equals_after_native": differences == 0,
        "final_differences": differences,
        "timings": timings,
        "total_seconds": float(sum(timings.values())),
    }


def oracle(host_run, strategy_dir, out):
    import numba
    from tricolour.core.kernels import flagging
    from tricolour.core.kernels.mask import collect_masks, load_masks

    out.mkdir(parents=True, exist_ok=False)
    before = host_hashes(host_run)
    mask_dict = load_masks(None)
    masks = list(mask_dict.values())
    root = Path(flagging.__file__).parents[2]
    receipt = {
        "mode": "oracle",
        "host_run": str(host_run),
        "tricolour": tricolour_provenance(),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "numba_version": numba.__version__,
        "tricolour_sources": {
            name: file_sha256(root / name)
            for name in (
                "core/application/implementation.py",
                "core/kernels/flagging.py",
                "core/kernels/mask.py",
                "core/kernels/stokes.py",
            )
        },
        "static_masks": {str(p): file_sha256(p) for p in collect_masks()},
        "masked_channel_counts": [int(m.size) for m in masks],
        "host_hashes": before,
        "controls": {},
        "timings": {},
        "load_before": loadavg(),
    }
    started = time.perf_counter()
    for label, strategy in CONTROLS:
        tic = time.perf_counter()
        receipt["controls"][label] = run_control(
            host_run, strategy_dir / strategy, label, out, masks
        )
        receipt["timings"][label] = time.perf_counter() - tic
        print(
            label,
            "final_equals_after_native",
            receipt["controls"][label]["final_equals_after_native"],
            f"{receipt['timings'][label]:.1f} s",
            flush=True,
        )
    receipt["timings"]["total"] = time.perf_counter() - started
    receipt["load_after"] = loadavg()
    receipt["numba_signatures"] = numba_signatures(flagging)
    receipt["host_unchanged"] = host_hashes(host_run) == before
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")
    print(json.dumps({k: receipt[k] for k in ("timings", "host_unchanged")}, indent=1))


# --- T2: the application end to end -----------------------------------------


def cli(host_run, strategy_dir, out):
    from casacore.tables import table

    out.mkdir(parents=True, exist_ok=False)
    before = host_hashes(host_run)
    exe = Path(sys.executable).parent / "tricolour"
    env = dict(os.environ)
    env.setdefault("RAY_USAGE_STATS_ENABLED", "0")
    receipt = {
        "mode": "cli",
        "host_run": str(host_run),
        "tricolour": tricolour_provenance(),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "host_hashes": before,
        "controls": {},
    }
    for label, strategy in CONTROLS:
        directory = host_run / "native" / label
        control_dir = out / label
        control_dir.mkdir()
        ms = control_dir / "input.ms"
        shutil.copytree(directory / "diagnostic.ms", ms)
        lock = ms / "table.lock"
        if lock.exists():
            lock.unlink()
        flags_in = np.load(directory / "before-native.npz")["FLAG"]
        with table(str(ms), readonly=False, ack=False) as t:
            t.putcol("FLAG", flags_in)
            row_before = t.getcol("FLAG_ROW")
        command = [
            str(exe),
            "-fs",
            "polarisation",
            "-c",
            str(strategy_dir / strategy),
            "-nw",
            "4",
            "-tc",
            "100",
            # Options precede the MS: the CLI is a Typer group, so options after
            # the positional are not parsed (post-hoc fix, section 6).
            str(ms),
        ]
        record = {"command": command, "strategy": strategy}
        load_before = loadavg()
        tic = time.perf_counter()
        with (control_dir / "tricolour.log").open("w") as log:
            try:
                proc = subprocess.run(
                    ["/usr/bin/time", "-f", "TIME %e %M", *command],
                    check=False,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=env,
                    timeout=CLI_TIMEOUT,
                    cwd=control_dir,
                )
                record["returncode"] = proc.returncode
            except subprocess.TimeoutExpired:
                record["returncode"] = None
                record["timeout"] = True
        record["wall"] = time.perf_counter() - tic
        record["load_before"], record["load_after"] = load_before, loadavg()
        for line in (control_dir / "tricolour.log").read_text().splitlines():
            if line.startswith("TIME "):
                _, wall, rss = line.split()
                record["time_wall"] = float(wall)
                record["driver_max_rss_mb"] = int(rss) / 1024
        with table(str(ms), readonly=True, ack=False, lockoptions="autonoread") as t:
            flag = t.getcol("FLAG")
            row_after = t.getcol("FLAG_ROW")
        np.savez_compressed(control_dir / "final.npz", FLAG=flag)
        after = np.load(directory / "after-native.npz")["FLAG"]
        record["flag_row_unchanged"] = bool(np.array_equal(row_before, row_after))
        record["changed_from_input"] = int(np.count_nonzero(flag != flags_in))
        record["final_differences_vs_after_native"] = int(
            np.count_nonzero(flag != after)
        )
        record["final_fraction"] = float(flag.mean())
        shutil.rmtree(ms)  # the copy; FLAG is kept in final.npz
        receipt["controls"][label] = record
        print(label, record.get("returncode"), f"{record['wall']:.1f} s", flush=True)
    receipt["host_unchanged"] = host_hashes(host_run) == before
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")


# --- comparison ---------------------------------------------------------------


def diff_dirs(a, b, label, intensity=True):
    out = {}
    sa, sb = np.load(a / label / "stages.npz"), np.load(b / label / "stages.npz")
    out["stages"] = {
        name: (
            int(np.count_nonzero(sa[name] != sb[name]))
            if name in sb.files
            else "missing"
        )
        for name in sa.files
    }
    out["final"] = int(
        np.count_nonzero(
            np.load(a / label / "final.npz")["FLAG"]
            != np.load(b / label / "final.npz")["FLAG"]
        )
    )
    if intensity:
        ia = np.load(a / label / "intensity.npz")["intensity"]
        ib = np.load(b / label / "intensity.npz")["intensity"]
        same = ia.shape == ib.shape and ia.dtype == ib.dtype
        out["intensity_bit_equal"] = bool(
            same and np.array_equal(ia.view(np.uint32), ib.view(np.uint32))
        )
        if same and not out["intensity_bit_equal"]:
            out["intensity_differing_words"] = int(
                np.count_nonzero(ia.view(np.uint32) != ib.view(np.uint32))
            )
    out["identical"] = (
        all(v == 0 for v in out["stages"].values())
        and out["final"] == 0
        and out.get("intensity_bit_equal", True)
    )
    return out


def compare(args):
    oracle021, host_run, out = Path(args.oracle021), Path(args.host_run), Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    result = {"oracle021": str(oracle021), "host_run": str(host_run), "controls": {}}
    t1 = Path(args.t1)
    receipt1 = json.loads((t1 / "receipt.json").read_text())
    for label, _ in CONTROLS:
        after = np.load(host_run / "native" / label / "after-native.npz")["FLAG"]
        entry = {"t1_vs_021": diff_dirs(t1, oracle021, label)}
        entry["t1_final_vs_after_native"] = int(
            np.count_nonzero(np.load(t1 / label / "final.npz")["FLAG"] != after)
        )
        if args.t0:
            entry["t0_vs_021"] = diff_dirs(Path(args.t0), oracle021, label)
        if args.t3:
            entry["t3_vs_t1"] = diff_dirs(Path(args.t3), t1, label)
        if args.t2:
            flag = np.load(Path(args.t2) / label / "final.npz")["FLAG"]
            entry["t2_final_vs_after_native"] = int(np.count_nonzero(flag != after))
            entry["t2_final_vs_t1"] = int(
                np.count_nonzero(flag != np.load(t1 / label / "final.npz")["FLAG"])
            )
        result["controls"][label] = entry
    c = result["controls"].values()
    result["t4_get_flags_impl_signatures"] = receipt1["numba_signatures"].get(
        "_get_flags_impl"
    )
    result["verdict"] = {
        "t1_identical_to_021": all(e["t1_vs_021"]["identical"] for e in c),
        "t1_final_equals_after_native": all(
            e["t1_final_vs_after_native"] == 0 for e in c
        ),
        "t0_identical_to_021": all(e["t0_vs_021"]["identical"] for e in c)
        if args.t0
        else None,
        "t3_identical_to_t1": all(e["t3_vs_t1"]["identical"] for e in c)
        if args.t3
        else None,
        "t2_final_equals_after_native": all(
            e["t2_final_vs_after_native"] == 0 for e in c
        )
        if args.t2
        else None,
        "t4_one_signature": result["t4_get_flags_impl_signatures"] == 1,
    }
    result["verdict"]["identical"] = bool(
        result["verdict"]["t1_identical_to_021"]
        and result["verdict"]["t2_final_equals_after_native"]
    )
    (out / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result["verdict"], indent=1))
    return 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("oracle", "cli"):
        p = sub.add_parser(mode)
        p.add_argument("host_run")
        p.add_argument("strategy_dir")
        p.add_argument("out")
    p = sub.add_parser("compare")
    p.add_argument("oracle021")
    p.add_argument("host_run")
    p.add_argument("out")
    for name in ("--t0", "--t1", "--t2", "--t3"):
        p.add_argument(name)
    args = parser.parse_args()
    if args.mode == "compare":
        return compare(args)
    paths = Path(args.host_run), Path(args.strategy_dir), Path(args.out)
    if args.mode == "oracle":
        oracle(*paths)
    else:
        cli(*paths)
    return 0


if __name__ == "__main__":
    sys.exit(main())
