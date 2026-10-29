"""WSClean imaging-weight oracle for core task B (research/core-b-weighting.md).

Runs once inside ``rang-flagging-next-imaging:local`` (WSClean 3.6-1,
python-casacore, astropy). For each archived imaging job it rebuilds the job's
Measurement Set state from the archived checkpoint, reruns the archived WSClean
command with ``-store-imaging-weights`` appended, checks the rerun's images and
header sums against the archive, and exports everything the core comparison
needs to one ``.npz`` and one ``.json`` per run. Two jobs are repeated to measure
WSClean's own reproducibility and are also run with uniform and natural
weighting.

    docker run --rm --network none -u "$(id -u):$(id -g)" -e HOME=/tmp \\
      -v "$PWD:/workspace:ro" -v "$HOME/Github/rang/outputs:/o" \\
      --entrypoint python3 rang-flagging-next-imaging:local \\
      /workspace/examples/oracle_wsclean_weights.py \\
      /o/tv-next-imaging-wsl-20261029-01 /o/core-b-20261030-01
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HEADER_KEYS = ("WSCVWSUM", "WSCIMGWG", "WSCNORMF", "WSCNVIS", "WSCENVIS")
REPEATED = ("clean-full", "caracal-firstpass-rejected")
EXTRA_MODES = {"uniform": ["uniform"], "natural": ["natural"]}
COLUMNS = (
    "UVW",
    "WEIGHT_SPECTRUM",
    "FLAG",
    "FLAG_ROW",
    "FIELD_ID",
    "ANTENNA1",
    "ANTENNA2",
    "DATA_DESC_ID",
    "TIME",
    "CORRECTED_DATA",
    "IMAGING_WEIGHT_SPECTRUM",
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_fits(path):
    from astropy.io import fits

    with fits.open(path, memmap=False) as hdus:
        header = hdus[0].header
        data = np.asarray(hdus[0].data, np.float64).squeeze()
    return {key: float(header[key]) for key in HEADER_KEYS}, data


def prepare_ms(source, target, checkpoint):
    from casacore.tables import table

    shutil.copytree(source, target)
    written = np.load(checkpoint, allow_pickle=False)
    with table(str(target), readonly=False, ack=False) as work:
        for key in ("CORRECTED_DATA", "FLAG", "FLAG_ROW"):
            work.putcol(key, written[key])
        work.flush()
    with table(str(target), ack=False) as work:
        for key in ("CORRECTED_DATA", "FLAG", "FLAG_ROW"):
            if not np.array_equal(work.getcol(key), written[key]):
                raise RuntimeError(f"{key} did not round-trip into {target}")


def rewrite_command(command, archive, output, name, ms, mode):
    prefix = f"{archive}/images/"
    out = []
    skip = 0
    for item in command:
        if skip:
            skip -= 1
            continue
        if item.startswith(prefix):
            out.append(str(output / "images" / name))
        elif item == f"{archive}/temp":
            out.append(str(output / "temp"))
        elif item.endswith(".ms"):
            out.append(str(ms))
        elif item == "briggs" and mode != "briggs":
            out.extend(EXTRA_MODES[mode])
            skip = 1
        else:
            out.append(item)
    out.insert(len(out) - 1, "-store-imaging-weights")
    return out


def export(ms, output, name, archive_label, archive, timing, command, mode):
    from casacore.tables import table

    arrays = {}
    with table(str(ms), ack=False) as work:
        for key in COLUMNS:
            arrays[key] = work.getcol(key)
    with table(str(ms / "SPECTRAL_WINDOW"), ack=False) as spw:
        freq = spw.getcol("CHAN_FREQ")[0]
    arrays["CHAN_FREQ"] = freq
    arrays["WAVELENGTH"] = (
        np.longdouble(299792458) / freq.astype(np.longdouble)
    ).astype(np.float64)
    rerun = {}
    checks = {}
    for kind in ("dirty", "psf"):
        header, pixels = read_fits(output / "images" / f"{name}-{kind}.fits")
        arrays[f"{kind}_pixels"] = pixels.astype(np.float32)
        rerun[kind] = header
        if archive_label is not None:
            archived, archived_pixels = read_fits(
                archive / "images" / f"{archive_label}-{kind}.fits"
            )
            checks[kind] = {
                "max_abs_pixel_difference": float(
                    np.max(np.abs(pixels - archived_pixels))
                ),
                "pixels_identical": bool(np.array_equal(pixels, archived_pixels)),
                "archive_header": archived,
                "header_max_relative_difference": max(
                    abs(header[k] - archived[k]) / max(abs(archived[k]), 1e-300)
                    for k in HEADER_KEYS
                ),
            }
    np.savez(output / "oracle" / f"{name}.npz", **arrays)
    record = {
        "name": name,
        "mode": mode,
        "archive_label": archive_label,
        "command": command,
        "wall_seconds": timing,
        "rerun_header": rerun,
        "archive_checks": checks,
        "imaging_weight_nonzero": int(
            np.count_nonzero(arrays["IMAGING_WEIGHT_SPECTRUM"])
        ),
    }
    (output / "oracle" / f"{name}.json").write_text(json.dumps(record, indent=2))
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--keep-ms", action="store_true")
    args = parser.parse_args()
    archive = args.archive.resolve()
    output = args.output.resolve()
    for folder in ("ms", "oracle", "images", "logs", "temp"):
        (output / folder).mkdir(parents=True, exist_ok=True)
    config = json.loads((archive / "imaging-config.json").read_text())
    labels = config["fixed_jobs"]
    if len(labels) != 15:
        raise RuntimeError("fifteen archived jobs expected")
    binary = Path(shutil.which("wsclean"))
    binary_sha = sha256(binary)
    expected = config["tool"]["package_manifest"]["wsclean_binary_sha256"]
    if binary_sha != expected:
        raise RuntimeError(
            f"WSClean binary {binary_sha} differs from archive {expected}"
        )
    runs = [(label, label, "briggs") for label in labels]
    for label in REPEATED:
        runs.append((f"{label}--repeat", label, "briggs"))
        for mode in EXTRA_MODES:
            runs.append((f"{label}--{mode}", label, mode))
    records = []
    started = time.perf_counter()
    for name, label, mode in runs:
        role = "caracal" if label.startswith("caracal-") else "response"
        ms = output / "ms" / f"{name}.ms"
        t0 = time.perf_counter()
        prepare_ms(
            archive / f"{role}-diagnostic.ms",
            ms,
            archive / "checkpoints" / f"{label}-written.npz",
        )
        prepare_seconds = time.perf_counter() - t0
        archived_command = json.loads(
            (archive / "checkpoints" / f"{label}-command.json").read_text()
        )
        command = rewrite_command(
            archived_command,
            "/workspace/outputs/" + archive.name,
            output,
            name,
            ms,
            mode,
        )
        command[0] = str(binary)
        t0 = time.perf_counter()
        with (output / "logs" / f"{name}-wsclean.log").open("w") as log:
            completed = subprocess.run(
                command, check=False, stdout=log, stderr=subprocess.STDOUT
            )
        wsclean_seconds = time.perf_counter() - t0
        if completed.returncode:
            raise RuntimeError(f"WSClean failed for {name}; see logs")
        t0 = time.perf_counter()
        record = export(
            ms,
            output,
            name,
            label if mode == "briggs" else None,
            archive,
            {"prepare": prepare_seconds, "wsclean": wsclean_seconds},
            command,
            mode,
        )
        record["wall_seconds"]["export"] = time.perf_counter() - t0
        records.append(record)
        if not args.keep_ms:
            shutil.rmtree(ms)
        print(name, json.dumps(record["wall_seconds"]), file=sys.stderr)
    summary = {
        "archive": str(archive),
        "wsclean_binary_sha256": binary_sha,
        "runs": records,
        "total_wall_seconds": time.perf_counter() - started,
    }
    (output / "oracle" / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
