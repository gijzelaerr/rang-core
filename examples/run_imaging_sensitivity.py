"""Rerun the archived fifteen-job imaging family with varied gridding settings.

Runs inside ``rang-flagging-next-imaging:local`` (WSClean 3.6-1,
python-casacore, astropy). Protocol: ``research/core-a-imaging-sensitivity.md``.

    python3 examples/run_imaging_sensitivity.py \
        --archive outputs/tv-next-imaging-wsl-20261029-01 \
        --output outputs/core-a-20261029-01 [--variants a,b] [--jobs x,y]

The archive is read only (its checkpoints, images and backups are digested
before and after); the output directory must not exist.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from rangtoy.flagging_imaging import _read_images
from rangtoy.flagging_workflow import tree_digest, write_json
from rangtoy.imaging_sensitivity import (
    JOBS,
    ROLES,
    WEIGHT_KEYS,
    pixel_differences,
    pixel_digest,
    proposed_tolerances,
    spread,
    variant_command,
    variant_metrics,
    variants,
)

CLOSURE_JY = 1e-6
HEADER_KEYS = (*WEIGHT_KEYS, "WSCGKRNL", "WSCNWLAY", "BMAJ", "BMIN", "BPA")


def _headers(prefix):
    from astropy.io import fits

    out = {}
    for kind in ("dirty", "psf"):
        header = fits.getheader(f"{prefix}-{kind}.fits")
        out[kind] = {key: header[key] for key in HEADER_KEYS if key in header}
    return out


def _write_columns(ms, checkpoint):
    from casacore.tables import makearrcoldesc, maketabdesc, table

    saved = np.load(checkpoint)
    expected = saved["CORRECTED_DATA"]
    if expected.dtype != np.complex64:
        raise ValueError("checkpointed CORRECTED_DATA must be complex64")
    with table(str(ms), readonly=False, ack=False) as work:
        if "CORRECTED_DATA" not in work.colnames():
            work.addcols(
                maketabdesc(
                    makearrcoldesc(
                        "CORRECTED_DATA",
                        0j,
                        ndim=2,
                        valuetype="complex",
                        datamanagertype="StandardStMan",
                        datamanagergroup="RANG_IMAGING_CORRECTED",
                    )
                )
            )
        work.putcol("CORRECTED_DATA", expected)
        work.putcol("FLAG", saved["FLAG"])
        work.putcol("FLAG_ROW", saved["FLAG_ROW"])
        work.flush()
        if (
            not np.array_equal(work.getcol("CORRECTED_DATA"), expected)
            or not np.array_equal(work.getcol("FLAG"), saved["FLAG"])
            or not np.array_equal(work.getcol("FLAG_ROW"), saved["FLAG_ROW"])
        ):
            raise RuntimeError("checkpointed column persistence mismatch")
    return int(saved["support"].sum())


def _archive_digests(archive):
    return {
        name: tree_digest(archive / name)
        for name in ("checkpoints", "images", "backups")
    }


def _archive_pixels(archive, jobs):
    digests = {}
    for job in jobs:
        images, _ = _read_images(archive / "images" / job)
        digests[job] = {kind: pixel_digest(images[kind]) for kind in ("dirty", "psf")}
    return digests


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--variants", default="")
    parser.add_argument("--jobs", default="")
    args = parser.parse_args(argv)
    archive, output = Path(args.archive).resolve(), Path(args.output).resolve()
    grid = variants()
    names = [x for x in args.variants.split(",") if x] or list(grid)
    jobs = tuple(x for x in args.jobs.split(",") if x) or JOBS
    if any(name not in grid for name in names) or any(job not in JOBS for job in jobs):
        raise SystemExit("unknown variant or job")
    if names[0] != "default":
        raise SystemExit("the default variant must run first")
    if output.exists() or not (archive / "checkpoints").is_dir():
        raise SystemExit("fresh output directory and archive with checkpoints required")
    started = time.perf_counter()
    before = _archive_digests(archive)
    archive_pixels = _archive_pixels(archive, jobs)
    output.mkdir(parents=True)
    (output / "variants").mkdir()
    work = {}
    for role in ("response", "caracal"):
        work[role] = output / f"{role}-diagnostic.ms"
        shutil.copytree(archive / "backups" / f"{role}-input.ms", work[role])
    tempdir = output / "temp"
    tempdir.mkdir()
    commands = {
        job: json.loads((archive / "checkpoints" / f"{job}-command.json").read_text())
        for job in jobs
    }
    results, default_images, timings = {}, {}, {}
    for name in names:
        variant = grid[name]
        folder = output / "variants" / name
        (folder / "images").mkdir(parents=True)
        all_images, headers, seconds = {}, {}, {}
        for job in jobs:
            support = _write_columns(
                work[ROLES[job]], archive / "checkpoints" / f"{job}-written.npz"
            )
            command = variant_command(
                commands[job],
                variant,
                folder / "images" / job,
                tempdir,
                work[ROLES[job]],
            )
            write_json(folder / f"{job}-command.json", command)
            start = time.perf_counter()
            with (folder / f"{job}-wsclean.log").open("x") as log:
                completed = subprocess.run(
                    command, stdout=log, stderr=subprocess.STDOUT, check=False
                )
            seconds[job] = time.perf_counter() - start
            if completed.returncode:
                raise RuntimeError(
                    f"WSClean failed for {name}/{job}: {completed.returncode}"
                )
            (folder / "images" / f"{job}-image.fits").unlink()
            images, _ = _read_images(folder / "images" / job)
            all_images[job] = images
            headers[job] = _headers(folder / "images" / job)["dirty"]
            headers[job]["support"] = support
        if set(jobs) == set(JOBS):
            metrics = variant_metrics(all_images, headers)
        else:
            metrics = {"jobs": {job: {} for job in jobs}, "partial": True}
        for job in jobs:
            metrics["jobs"][job]["headers"] = headers[job]
            metrics["jobs"][job].setdefault(
                "pixel_sha256",
                {
                    kind: pixel_digest(all_images[job][kind])
                    for kind in ("dirty", "psf")
                },
            )
        if name == "default":
            default_images = all_images
        for job in jobs:
            metrics["jobs"][job]["pixels"] = pixel_differences(
                all_images[job], default_images[job]
            )
        metrics["settings"] = variant
        metrics["seconds_per_job"] = seconds
        metrics["seconds"] = float(sum(seconds.values()))
        write_json(folder / "result.json", metrics)
        results[name] = metrics
        timings[name] = metrics["seconds"]
        print(f"{name}: {metrics['seconds']:.1f} s", file=sys.stderr, flush=True)
    shutil.rmtree(tempdir)
    reproduction = {
        job: {
            kind: results["default"]["jobs"][job]["pixel_sha256"][kind]
            == archive_pixels[job][kind]
            for kind in ("dirty", "psf")
        }
        for job in jobs
    }
    weights_equal = {
        job: all(
            {k: results[name]["jobs"][job]["headers"].get(k) for k in WEIGHT_KEYS}
            == {
                k: results["default"]["jobs"][job]["headers"].get(k)
                for k in WEIGHT_KEYS
            }
            for name in names
        )
        for job in jobs
    }
    complete = set(jobs) == set(JOBS) and set(names) == set(grid)
    summary = {
        "status": "measured approximation sensitivity; archive unchanged",
        "complete_grid": complete,
        "archive": str(archive),
        "variants": {name: grid[name] for name in names},
        "criterion_1_reproduction": reproduction,
        "criterion_1_pass": all(all(x.values()) for x in reproduction.values()),
        "criterion_2_weights_equal": weights_equal,
        "criterion_2_pass": all(weights_equal.values()),
        "seconds_per_variant": timings,
        "seconds_total": time.perf_counter() - started,
    }
    if complete:
        closures = {
            name: results[name]["dirty_image_closures_jy_per_beam"] for name in names
        }
        summary["criterion_3_closures"] = closures
        summary["criterion_3_pass"] = all(
            value <= CLOSURE_JY for x in closures.values() for value in x.values()
        )
        table = spread(results)
        summary["spread"] = table
        summary["proposed_tolerances"] = proposed_tolerances(table)
    after = _archive_digests(archive)
    summary["criterion_6_archive_unchanged"] = before == after
    summary["archive_digests"] = after
    write_json(output / "result.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if "criterion" in k}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
