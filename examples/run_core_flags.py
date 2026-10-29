"""Run the Tricolour port on the four archived controls (research/core-d-tricolour.md).

Usage:
    python examples/run_core_flags.py <oracle-dir> <host-run> <strategy-dir> outputs/<fresh>

Reads the arrays the oracle step exported for each control, runs
`rangtoy.core_flag.flag_rows` with the pinned CARACAL strategy, derives the
training proposal from the host run's `state.npz`, and writes per control
`flags.npz` (FLAG and `added`), `intensity.npz` and `stages.npz`, plus
`receipt.json` with timings and the host input hashes.
`examples/compare_core_flags.py run` applies the frozen criteria.
"""

import json
import platform
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np
from rangtoy import core, core_flag
from rangtoy.flagging_caracal import training_proposal

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "research/results/gain-tv-caracal.json"
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
        digest.update(str(p.relative_to(path)).encode())
        digest.update(p.read_bytes())
    return digest.hexdigest()


def file_sha256(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def host_hashes(host_run):
    return {
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


def main():
    oracle_dir, host_run, strategy_dir, out = (Path(a) for a in sys.argv[1:5])
    out.mkdir(parents=True, exist_ok=False)
    before = host_hashes(host_run)
    state = np.load(host_run / "state.npz")
    archive = json.loads(ARCHIVE.read_text())["result"]["controls"]
    archive_added = {c["native"]["label"]: c["metrics"]["added_count"] for c in archive}
    masks = [core_flag.load_static_mask(p) for p in core_flag.static_mask_files()]
    receipt = {
        "oracle_dir": str(oracle_dir),
        "host_run": str(host_run),
        "core_library_sha256": file_sha256(core.library_path()),
        "static_masks": {p.name: file_sha256(p) for p in core_flag.static_mask_files()},
        "strategies": {},
        "archive_added_count": archive_added,
        "numpy_version": np.__version__,
        "python_version": platform.python_version(),
        "timings": {},
        "controls": {},
    }
    total = time.perf_counter()
    for label, strategy_name in CONTROLS:
        strategy_path = strategy_dir / strategy_name
        receipt["strategies"][strategy_name] = file_sha256(strategy_path)
        strategies = core_flag.parse_strategy(strategy_path.read_text())
        arrays = np.load(oracle_dir / label / "arrays.npz")
        tic = time.perf_counter()
        result = core_flag.flag_rows(
            arrays["DATA"],
            arrays["FLAG"],
            arrays["ANTENNA1"],
            arrays["ANTENNA2"],
            arrays["TIME"],
            arrays["antenna_position"],
            arrays["chan_freq"],
            arrays["chan_width"],
            arrays["corr_type"],
            strategies,
            masks=masks,
        )
        wall = time.perf_counter() - tic
        added = training_proposal(state, result["flags"])
        control_dir = out / label
        control_dir.mkdir()
        np.savez(control_dir / "flags.npz", FLAG=result["flags"], added=added)
        np.savez(control_dir / "intensity.npz", intensity=result["intensity"])
        np.savez_compressed(control_dir / "stages.npz", **result["stages"])
        receipt["timings"][label] = {"core_seconds": result["seconds"], "wall": wall}
        receipt["controls"][label] = {
            "strategy": strategy_name,
            "steps": len(strategies),
            "flag_fraction": float(result["flags"].mean()),
            "added_count": int(np.count_nonzero(added)),
            "stage_fractions": {
                k: float(v.mean()) for k, v in result["stages"].items()
            },
            "ubl_equals_oracle": bool(
                np.array_equal(result["ubl"], arrays["ubl"][:, 1:])
            ),
        }
        print(label, f"{result['seconds']:.2f} s", flush=True)
    receipt["timings"]["total"] = time.perf_counter() - total
    receipt["host_hashes"] = host_hashes(host_run)
    receipt["host_unchanged"] = receipt["host_hashes"] == before
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")
    print(json.dumps(receipt["timings"], indent=1))


if __name__ == "__main__":
    main()
