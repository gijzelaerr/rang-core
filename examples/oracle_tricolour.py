"""Tricolour 0.2.1 oracle for the task D port (research/core-d-tricolour.md).

Usage (inside rang-flagging-parallel:local, with /opt/tricolour/bin/python):
    python examples/oracle_tricolour.py <host-run> <strategy-dir> <fresh-output-dir>

For each of the four archived controls this reads the control's diagnostic
Measurement Set read-only and its `before-native.npz`, exports the arrays the
port needs, and runs the unmodified `tricolour.stokes` and
`tricolour.flagging` NumPy functions step by step exactly as
`tricolour/apps/tricolour/strat_executor.py` chains them for the
`polarisation` flagging strategy. It saves the polarised intensity window,
the window flags after every step and the final per-row flags, checks the
latter against `after-native.npz`, and writes a receipt with hashes,
versions and per-step wall times (the first control includes Numba
compilation). It never writes to the host run.
"""

import json
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np
import tricolour
import yaml
from casacore.tables import table
from tricolour.flagging import (
    apply_static_mask,
    flag_autos,
    flag_nans_and_zeros,
    sum_threshold_flagger,
    uvcontsub_flagger,
)
from tricolour.mask import collect_masks, load_mask
from tricolour.packing import _numba_pack_data
from tricolour.stokes import polarised_intensity, stokes_corr_map

CONTROLS = (
    ("strategy-00-operational", "mk_rfi_flagging_calibrator_fields_firstpass.yaml"),
    ("strategy-00-holdout_masked", "mk_rfi_flagging_calibrator_fields_firstpass.yaml"),
    ("strategy-01-operational", "calibrator_mild_flagging.yaml"),
    ("strategy-01-holdout_masked", "calibrator_mild_flagging.yaml"),
)


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


def read_ms(ms):
    with table(str(ms), readonly=True, ack=False, lockoptions="autonoread") as t:
        arrays = {
            name: np.ascontiguousarray(t.getcol(name))
            for name in ("DATA", "ANTENNA1", "ANTENNA2", "TIME", "FLAG_ROW")
        }
        arrays["FIELD_ID"] = t.getcol("FIELD_ID")
        arrays["SCAN_NUMBER"] = t.getcol("SCAN_NUMBER")
        arrays["DATA_DESC_ID"] = t.getcol("DATA_DESC_ID")
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


def run_control(host_run, strategy_path, label, out):
    directory = host_run / "native" / label
    arrays, antenna_names = read_ms(directory / "diagnostic.ms")
    before = np.load(directory / "before-native.npz")
    after = np.load(directory / "after-native.npz")
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
    flags_in = before["FLAG"]
    nrow, nchan, ncorr = data.shape
    timings = {}

    # app.py: polarisation strategy.
    corr_type = arrays["corr_type"].tolist()
    stokes_map = stokes_corr_map(corr_type)
    stokes_pol = tuple(v for k, v in stokes_map.items() if k != "I")
    tic = time.perf_counter()
    vis = polarised_intensity(data, stokes_pol)
    timings["polarised_intensity"] = time.perf_counter() - tic
    flags = np.any(flags_in, axis=2, keepdims=True)

    # app.py / packing.py: unique baselines, unique times, windows.
    bl = np.stack([ant1, ant2], axis=1).astype(np.int32).view(np.int64)
    ubl = np.unique(bl).view(np.int32).reshape(-1, 2)
    ubl = np.concatenate([np.arange(ubl.shape[0], dtype=ubl.dtype)[:, None], ubl], 1)
    utime, time_inv = np.unique(arrays["TIME"], return_inverse=True)
    ntime, nbl = utime.shape[0], ubl.shape[0]
    vis_windows = np.full((nbl, 1, ntime, nchan), np.nan + np.nan * 1j, vis.dtype)
    flag_windows = np.full((nbl, 1, ntime, nchan), 1, flags.dtype)
    tic = time.perf_counter()
    _numba_pack_data(time_inv, ubl, ant1, ant2, vis, flags, vis_windows, flag_windows)
    timings["pack"] = time.perf_counter() - tic

    # strat_executor.py.
    mask_files = collect_masks()
    masks = [load_mask(fn, dilate=None) for fn in mask_files]
    strategies = yaml.full_load(Path(strategy_path).read_text())["strategies"]
    original = flag_windows.copy()
    stages = {}
    for index, strategy in enumerate(strategies):
        task = strategy["task"]
        kwargs = strategy.get("kwargs", {})
        tic = time.perf_counter()
        if task == "sum_threshold":
            new = sum_threshold_flagger(vis_windows, flag_windows, **kwargs)
            flag_windows = np.logical_or(new, flag_windows)
        elif task == "uvcontsub_flagger":
            flag_windows = uvcontsub_flagger(vis_windows, flag_windows, **kwargs)
        elif task == "flag_autos":
            new = flag_autos(flag_windows, [ubl])
            flag_windows = np.logical_or(new, flag_windows)
        elif task == "combine_with_input_flags":
            flag_windows = np.logical_or(flag_windows, original)
        elif task == "flag_nans_zeros":
            flag_windows = flag_nans_and_zeros(vis_windows, flag_windows)
        elif task == "apply_static_mask":
            new = apply_static_mask(
                flag_windows,
                ubl,
                arrays["antenna_position"],
                masks,
                arrays["chan_freq"],
                arrays["chan_width"],
                **kwargs,
            )
            if kwargs["accumulation_mode"].strip() == "or":
                flag_windows = np.logical_or(new, flag_windows)
            else:
                flag_windows = new
        else:
            raise ValueError(f"task {task!r} not handled")
        name = f"{index:02d}-{task}"
        timings[name] = time.perf_counter() - tic
        stages[name] = np.ascontiguousarray(flag_windows, dtype=bool)

    # app.py: unpack and equalise over correlations.
    unpacked = np.zeros((nrow, nchan, 1), dtype=bool)
    for b, a1, a2 in ubl:
        valid = (ant1 == a1) & (ant2 == a2)
        unpacked[valid, :, 0] = flag_windows[b, 0, time_inv[valid], :]
    final = np.broadcast_to(unpacked, (nrow, nchan, ncorr)).copy()
    differences = int(np.count_nonzero(final != after["FLAG"]))

    control_dir = out / label
    control_dir.mkdir()
    np.savez(
        control_dir / "arrays.npz",
        DATA=data,
        ANTENNA1=ant1,
        ANTENNA2=ant2,
        TIME=arrays["TIME"],
        FLAG=flags_in,
        FLAG_ROW=arrays["FLAG_ROW"],
        antenna_position=arrays["antenna_position"],
        chan_freq=arrays["chan_freq"],
        chan_width=arrays["chan_width"],
        corr_type=arrays["corr_type"],
        ubl=ubl,
        time_inv=time_inv.astype(np.int64),
    )
    np.savez(control_dir / "intensity.npz", intensity=vis_windows)
    np.savez_compressed(control_dir / "stages.npz", **stages)
    np.savez_compressed(control_dir / "final.npz", FLAG=final)
    return {
        "strategy": Path(strategy_path).name,
        "strategy_sha256": file_sha256(strategy_path),
        "rows": nrow,
        "channels": nchan,
        "correlations": ncorr,
        "baselines": nbl,
        "times": ntime,
        "antenna_names": antenna_names,
        "mask_files": [str(p) for p in mask_files],
        "masked_channel_counts": [int(m.size) for m in masks],
        "stages": list(stages),
        "stage_fractions": {k: float(v.mean()) for k, v in stages.items()},
        "final_fraction": float(final.mean()),
        "after_native_fraction": float(after["FLAG"].mean()),
        "final_equals_after_native": differences == 0,
        "final_differences": differences,
        "timings": timings,
        "total_seconds": float(sum(timings.values())),
    }


def main():
    host_run, strategy_dir, out = (
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        Path(sys.argv[3]),
    )
    out.mkdir(parents=True, exist_ok=False)
    host_hashes = {}
    for label, _ in CONTROLS:
        directory = host_run / "native" / label
        host_hashes[label] = {
            "before-native.npz": file_sha256(directory / "before-native.npz"),
            "after-native.npz": file_sha256(directory / "after-native.npz"),
            "diagnostic.ms": tree_sha256(directory / "diagnostic.ms"),
        }
    root = Path(tricolour.__file__).parent
    receipt = {
        "host_run": str(host_run),
        "tricolour_version": tricolour.__version__,
        "numpy_version": np.__version__,
        "numba_version": __import__("numba").__version__,
        "tricolour_sources": {
            name: file_sha256(root / name)
            for name in (
                "apps/tricolour/app.py",
                "apps/tricolour/strat_executor.py",
                "dask_wrappers.py",
                "flagging.py",
                "mask.py",
                "packing.py",
                "stokes.py",
            )
        },
        "static_masks": {str(p): file_sha256(p) for p in collect_masks()},
        "host_hashes": host_hashes,
        "controls": {},
        "timings": {},
    }
    started = time.perf_counter()
    for label, strategy in CONTROLS:
        tic = time.perf_counter()
        receipt["controls"][label] = run_control(
            host_run, strategy_dir / strategy, label, out
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
    after = {
        label: {
            "before-native.npz": file_sha256(
                host_run / "native" / label / "before-native.npz"
            ),
            "after-native.npz": file_sha256(
                host_run / "native" / label / "after-native.npz"
            ),
            "diagnostic.ms": tree_sha256(host_run / "native" / label / "diagnostic.ms"),
        }
        for label, _ in CONTROLS
    }
    receipt["host_unchanged"] = after == host_hashes
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")
    print(json.dumps({k: receipt[k] for k in ("timings", "host_unchanged")}, indent=1))


if __name__ == "__main__":
    main()
