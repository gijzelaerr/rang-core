"""Build the compact archive of the task I replay from its run directories
(research/core-i-imaging-replay.md).

    python examples/archive_core_imaging.py OUT.json RUN [--stimela DIR] [--cli DIR]
        [--protocol-commit SHA] [--status TEXT] [--wall SECONDS --rss-mb MB]

RUN is the frozen run (`result.json`, `compare-archive.json`,
`compare-host.json`, `side-effects.json`); the Stimela and direct CLI runs
of criterion 9 are optional and are compared with the frozen run's result
field by field under the same comparator. Nothing in the run directories is
modified.
"""

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from rang.core_imaging import JOBS, TOLERANCES, compare_replay


def load(path):
    return json.loads(Path(path).read_text())


def summary(report):
    out = {
        "classes": {
            k: {
                "compared": v["compared"],
                "worst": v["worst"],
                "worst_path": v["worst_path"],
            }
            for k, v in report["classes"].items()
        },
        "failures": len(report["failures"]),
        "excluded": report["excluded"],
        "passed": report["passed"],
    }
    if "pixels" in report:
        out["pixels"] = {
            "summary": report["pixels"]["summary"],
            "wcs_equal": report["pixels"]["wcs_equal"],
            "passed": report["pixels"]["passed"],
            "per_job": {
                label: {
                    kind: {
                        k: job[kind][k]
                        for k in (
                            "max_abs_difference",
                            "rms_difference",
                            "central_rms_difference",
                            "border_rms_difference",
                            "reference_peak",
                            "max_relative_to_peak",
                        )
                    }
                    for kind in ("dirty", "psf")
                }
                for label, job in report["pixels"]["jobs"].items()
            },
        }
    return out


TIME_KEYS = {"seconds", "seconds_total", "ms_read_seconds", "archive", "export"}


def _timeless(value):
    if isinstance(value, dict):
        return {k: _timeless(v) for k, v in value.items() if k not in TIME_KEYS}
    if isinstance(value, list):
        return [_timeless(v) for v in value]
    return value


def run_record(run_dir):
    run_dir = Path(run_dir)
    result = load(run_dir / "result.json")
    record = {
        "run_dir": str(run_dir),
        "result_sha256": sha256((run_dir / "result.json").read_bytes()).hexdigest(),
        "core_library_sha256": result["provenance"]["core_library_sha256"],
        "module_sha256": result["provenance"]["module_sha256"],
        "export_checks": result["provenance"]["export_checks"],
        "seconds_total": result["seconds_total"],
        "ms_read_seconds": result["provenance"]["ms_read_seconds"],
        "jobs": {
            label: {
                "gridded_count": job["stats"]["gridded_count"],
                "image_weight": job["stats"]["image_weight"],
                "visibility_weight_sum": job["stats"]["visibility_weight_sum"],
                "w_limits": [job["stats"]["min_w"], job["stats"]["max_w"]],
                "psf_normalization": job["stats"]["psf_normalization"],
                "weight_check_pass": job["weight_check_vs_archive_fits"]["pass"],
                "weight_check_worst_relative": max(
                    job["weight_check_vs_archive_fits"][k]["relative_difference"]
                    for k in ("WSCVWSUM", "WSCIMGWG", "WSCNORMF")
                ),
                "seconds": job["seconds"],
                "PSF_linf_difference_vs_fixedG0": job["PSF_linf_difference_vs_fixedG0"],
                "conditional_response_vs_fixedG0": job.get(
                    "conditional_response_vs_fixedG0"
                ),
                "coefficients_jy": job.get("known_family_dirty_fit", {}).get(
                    "coefficients_jy"
                ),
                "dirty_offsource_RMS_jy_per_beam": job["diagnostics"][
                    "dirty_offsource_RMS_jy_per_beam"
                ],
            }
            for label, job in result["jobs"].items()
        },
        "reference_fit": result["reference_fit"],
        "dirty_image_closures_jy_per_beam": result["dirty_image_closures_jy_per_beam"],
        "criterion_1_weights": all(
            result["jobs"][label]["weight_check_vs_archive_fits"]["pass"]
            for label in JOBS
        ),
        "criterion_5_closures": all(
            v <= TOLERANCES["image_closure_jy_per_beam"]
            for v in result["dirty_image_closures_jy_per_beam"].values()
        ),
    }
    for name in ("archive", "host"):
        path = run_dir / f"compare-{name}.json"
        if path.is_file():
            record[f"against_{name}"] = summary(load(path))
    if (run_dir / "side-effects.json").is_file():
        audit = load(run_dir / "side-effects.json")
        record["side_effects"] = {
            k: audit[k]
            for k in (
                "input_files_checked",
                "inputs_unchanged",
                "git_status_unchanged",
                "run_dir_files",
                "images_written",
            )
        }
    return record, result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output")
    parser.add_argument("run")
    parser.add_argument("--stimela")
    parser.add_argument("--cli")
    parser.add_argument("--protocol-commit", default=None)
    parser.add_argument("--status", default=None)
    parser.add_argument("--wall", type=float, default=None)
    parser.add_argument("--rss-mb", type=float, default=None)
    parser.add_argument("--stimela-wall", type=float, default=None)
    parser.add_argument("--stimela-rss-mb", type=float, default=None)
    parser.add_argument("--cli-wall", type=float, default=None)
    parser.add_argument("--cli-rss-mb", type=float, default=None)
    args = parser.parse_args(argv)
    frozen, frozen_result = run_record(args.run)
    archive = {
        "schema_version": 1,
        "task": "core wave 2 task I: imaging track replay on the core",
        "protocol": "research/core-i-imaging-replay.md",
        "protocol_commit": args.protocol_commit,
        "status": args.status,
        "tolerances": dict(TOLERANCES),
        "oracle": "research/results/gain-tv-next-imaging.json (raw_result) and outputs/tv-next-imaging-wsl-20261029-01/result.json",
        "frozen_run": frozen,
        "cost": {
            "frozen_run_wall_seconds": args.wall,
            "frozen_run_max_rss_mb": args.rss_mb,
            "frozen_run_grid_seconds_per_job": {
                label: frozen_result["jobs"][label]["seconds"]["grid"] for label in JOBS
            },
            "archived_container_wsclean_seconds_per_job": "2.5-4.8 s each, 24.7 s in all (seconds_emulated_not_native_benchmark of the archive run)",
        },
        "novelty": "reimplementation only; no scientific result changes",
    }
    for name, run_dir, wall, rss in (
        ("stimela_run", args.stimela, args.stimela_wall, args.stimela_rss_mb),
        ("cli_run", args.cli, args.cli_wall, args.cli_rss_mb),
    ):
        if run_dir is None:
            continue
        record, result = run_record(run_dir)
        record["wall_seconds"] = wall
        record["max_rss_mb"] = rss
        # Run against run: wall times and the run's own paths differ by
        # construction; everything else is compared under the frozen classes.
        against_frozen = compare_replay(_timeless(frozen_result), _timeless(result))
        record["against_frozen_run"] = summary(against_frozen)
        record["result_identical_to_frozen_run"] = (
            all(
                frozen_result["jobs"][label]["FITS_sha256"]
                == result["jobs"][label]["FITS_sha256"]
                for label in JOBS
            )
            and frozen_result["reference_fit"] == result["reference_fit"]
        )
        archive[name] = record
    Path(args.output).write_text(json.dumps(archive, indent=1, sort_keys=True) + "\n")
    print(
        json.dumps(
            {k: v for k, v in archive.items() if k in ("protocol_commit", "status")}
        )
    )
    for name in ("frozen_run", "stimela_run", "cli_run"):
        if name in archive:
            r = archive[name]
            print(
                name,
                "weights",
                r["criterion_1_weights"],
                "closures",
                r["criterion_5_closures"],
                "archive",
                r.get("against_archive", {}).get("passed"),
                "host",
                r.get("against_host", {}).get("passed"),
                "frozen",
                r.get("against_frozen_run", {}).get("passed"),
                "identical",
                r.get("result_identical_to_frozen_run"),
            )


if __name__ == "__main__":
    main()
