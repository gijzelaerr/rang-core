"""Run the core gridder on the fifteen archived imaging jobs
(research/core-c-gridder.md).

    .venv/bin/python examples/run_core_gridder.py ARCHIVE ORACLE OUTPUT [--gridder wgrid]

ARCHIVE is `outputs/tv-next-imaging-wsl-20261029-01` (checkpoint columns per
job), ORACLE the WSClean oracle run (`outputs/core-c-20261029-01`: UVW,
frequencies, weights, phase centre and WSClean's stored imaging weights) and
OUTPUT a fresh directory. For every job the wrapper forms WSClean's Stokes I
sample and reader weight, inverts on the core, writes `<label>-dirty.fits` and
`<label>-psf.fits`, and checks the gated criteria 1–3 of the protocol against
the oracle's FITS headers and logs. Pixel differences are measured separately
by `compare_core_gridder.py`. `--gridder wgrid` inverts with the exact
gridder instead of w-stacking (research/df2b-wgrid.md); its FITS carry
`RCGRID`, and the result records the gridder either way.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from rang import core, core_grid

CHANNELS = (1024, 3072)
SETTINGS = {
    "width": 512,
    "height": 512,
    "scale_arcsec": 8.0,
    "w_layers": 64,
    "kernel_size": 7,
    "oversampling": 1023,
    "padding": 1.2,
}
WEIGHT_TOLERANCE = 1e-6
W_TOLERANCE = 1e-4


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(archive, oracle, output, gridder="wstack"):
    archive, oracle, output = Path(archive), Path(oracle), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "images").mkdir()
    receipt = json.loads((oracle / "receipt.json").read_text())
    common = {
        role: np.load(oracle / "inputs" / f"{role}-common.npz")
        for role in ("response", "caracal")
    }
    result = {
        "settings": SETTINGS,
        "gridder": gridder,
        "core_library_sha256": sha256(core.library_path()),
        "oracle": str(oracle),
        "archive": str(archive),
        "jobs": {},
        "criteria": {},
    }
    failures = []
    for label, job in receipt["jobs"].items():
        start = time.perf_counter()
        role = job["role"]
        shared = common[role]
        checkpoint = np.load(archive / "checkpoints" / f"{label}-written.npz")
        inputs = np.load(oracle / "inputs" / f"{label}-inputs.npz")
        if str(inputs["checkpoint_sha256"]) != sha256(
            archive / "checkpoints" / f"{label}-written.npz"
        ):
            raise RuntimeError(f"{label}: oracle inputs come from another checkpoint")
        flags = checkpoint["FLAG"][:, CHANNELS[0] : CHANNELS[1]]
        if not np.array_equal(flags, inputs["FLAG"]):
            raise RuntimeError(f"{label}: flag mismatch between checkpoint and oracle")
        data = checkpoint["CORRECTED_DATA"][:, CHANNELS[0] : CHANNELS[1]]
        sample, weight = core_grid.stokes_i_reader(
            data, shared["WEIGHT_SPECTRUM"], flags, checkpoint["FLAG_ROW"]
        )
        prepared = time.perf_counter()
        products = core_grid.invert(
            shared["UVW"],
            shared["CHAN_FREQ"],
            sample,
            weight,
            inputs["IMAGING_WEIGHT"],
            **SETTINGS,
            gridder=gridder,
        )
        gridded = time.perf_counter()
        stats = products["stats"]
        header = core_grid.wcs_header(
            shared["PHASE_DIR"],
            SETTINGS["width"],
            SETTINGS["height"],
            SETTINGS["scale_arcsec"],
            shared["CHAN_FREQ"],
        )
        extra = {
            "RCIMGWG": stats["image_weight"],
            "RCNVIS": stats["gridded_count"],
            "RCVWSUM": stats["visibility_weight_sum"],
            "RCMINW": stats["min_w"],
            "RCMAXW": stats["max_w"],
            "RCNWLAY": stats["n_w_layers"],
            "RCPSFNRM": stats["psf_normalization"],
        }
        if gridder != "wstack":  # w-stacking FITS stay as archived
            extra["RCGRID"] = gridder
        for kind in ("dirty", "psf"):
            core_grid.write_fits(
                output / "images" / f"{label}-{kind}.fits",
                products[kind],
                header,
                extra,
            )
        wsclean_header = job["fits"]["dirty"]["header"]
        log = job["log"]
        reference_weight = float(wsclean_header["WSCIMGWG"])
        checks = {
            "image_weight_relative": abs(stats["image_weight"] - reference_weight)
            / reference_weight,
            "gridded_count_equal": stats["gridded_count"]
            == log["gridded_visibility_count"],
            "wsclean_nvis": int(wsclean_header.get("WSCNVIS", -1)),
            "visibility_weight_sum_relative": abs(
                stats["visibility_weight_sum"] - float(wsclean_header["WSCVWSUM"])
            )
            / float(wsclean_header["WSCVWSUM"]),
            "min_w_relative": abs(stats["min_w"] - log["min_w"]) / log["min_w"],
            "max_w_relative": abs(stats["max_w"] - log["max_w"]) / log["max_w"],
            "psf_centre": float(
                products["psf"][SETTINGS["height"] // 2, SETTINGS["width"] // 2]
            ),
        }
        checks["criterion_1_weight_sum"] = (
            checks["image_weight_relative"] <= WEIGHT_TOLERANCE
            and checks["gridded_count_equal"]
        )
        checks["criterion_2_w_limits"] = (
            checks["min_w_relative"] <= W_TOLERANCE
            and checks["max_w_relative"] <= W_TOLERANCE
        )
        checks["criterion_3_psf_centre"] = checks["psf_centre"] == 1.0
        for key in (
            "criterion_1_weight_sum",
            "criterion_2_w_limits",
            "criterion_3_psf_centre",
        ):
            if not checks[key]:
                failures.append(f"{label}: {key}")
        result["jobs"][label] = {
            "role": role,
            "stats": stats,
            **({"wgridder": products["wgridder"]} if "wgridder" in products else {}),
            "checks": checks,
            "seconds": {
                "prepare": prepared - start,
                "grid": gridded - prepared,
                "total": time.perf_counter() - start,
            },
            "FITS_sha256": {
                kind: sha256(output / "images" / f"{label}-{kind}.fits")
                for kind in ("dirty", "psf")
            },
        }
        print(
            f"{label:28s} {role:8s} grid {gridded - prepared:6.2f}s "
            f"IMGWG rel {checks['image_weight_relative']:.2e} "
            f"count {stats['gridded_count']}={log['gridded_visibility_count']} "
            f"w rel {checks['min_w_relative']:.1e}/{checks['max_w_relative']:.1e} "
            f"psf0 {checks['psf_centre']!r}",
            flush=True,
        )
    result["criteria"] = {
        "criterion_1_weight_sum": all(
            j["checks"]["criterion_1_weight_sum"] for j in result["jobs"].values()
        ),
        "criterion_2_w_limits": all(
            j["checks"]["criterion_2_w_limits"] for j in result["jobs"].values()
        ),
        "criterion_3_psf_centre": all(
            j["checks"]["criterion_3_psf_centre"] for j in result["jobs"].values()
        ),
        "failures": failures,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    print("criteria", result["criteria"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("archive")
    parser.add_argument("oracle")
    parser.add_argument("output")
    parser.add_argument("--gridder", choices=core_grid.GRIDDERS, default="wstack")
    args = parser.parse_args()
    main(args.archive, args.oracle, args.output, args.gridder)
