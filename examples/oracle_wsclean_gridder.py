"""WSClean oracle for the core gridder (research/core-c-gridder.md).

Runs once inside ``rang-flagging-next-imaging:local`` (WSClean 3.6-1,
python-casacore, astropy). For each of the fifteen archived imaging jobs it
writes the archived checkpoint columns into a fresh copy of the archived
diagnostic Measurement Set, reruns the archived WSClean command with
``-store-imaging-weights`` added, and exports what the core gridder needs:
UVW, channel frequencies, WEIGHT_SPECTRUM, FLAG, FLAG_ROW, the phase centre
and WSClean's own per-channel imaging weights (IMAGING_WEIGHT_SPECTRUM). The
rerun dirty and PSF FITS are hashed and compared pixel by pixel with the
archived ones so that the comparator precondition (archive versus host
reproduction) is measured before the protocol is frozen.

Usage (paths as seen inside the container):

    python3 oracle_wsclean_gridder.py ARCHIVE OUTPUT

ARCHIVE is the archived imaging run (``tv-next-imaging-wsl-20261029-01``);
OUTPUT must not exist. Nothing in ARCHIVE is modified.
"""

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

CHANNELS = (1024, 3072)
LABELS = (
    "unit-compact",
    "unit-extended",
    "fixedG0-reference",
    "clean-full",
    "omitted-full",
    "omitted-total",
    "omitted-direct",
    "omitted-adaptation",
    "complete-full",
    "complete-total",
    "complete-direct",
    "complete-adaptation",
    "caracal-no-change",
    "caracal-mild",
    "caracal-firstpass-rejected",
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_fits(path):
    from astropy.io import fits

    with fits.open(str(path), memmap=False) as hdus:
        return np.asarray(hdus[0].data, np.float64).squeeze(), dict(hdus[0].header)


def header_subset(header):
    keys = [
        k
        for k in header
        if k.startswith(("WSC", "CRPIX", "CRVAL", "CDELT", "CTYPE"))
        or k in ("BMAJ", "BMIN", "BPA", "BUNIT", "NAXIS1", "NAXIS2")
    ]
    out = {}
    for key in keys:
        value = header[key]
        out[key] = value if isinstance(value, (int, float, str, bool)) else str(value)
    return out


def parse_log(text):
    import re

    found = {}
    m = re.search(r"w=\[([-0-9.e+]+):([-0-9.e+]+)\] lambdas, maxuvw=([-0-9.e+]+)", text)
    if m:
        found["min_w"], found["max_w"], found["max_uvw"] = (
            float(v) for v in m.groups()
        )
    m = re.search(r"Gridded visibility count: (\d+)", text)
    if m:
        found["gridded_visibility_count"] = int(m.group(1))
    m = re.search(r"Suggested number of w-layers: (\d+)", text)
    if m:
        found["suggested_w_layers"] = int(m.group(1))
    m = re.search(r"Will process (\d+)/(\d+) w-layers per pass", text)
    if m:
        found["w_layers_per_pass"], found["w_layers"] = int(m.group(1)), int(m.group(2))
    return found


def export_common(ms, role, output):
    from casacore.tables import table

    with table(str(ms), ack=False, readonly=True) as t:
        common = {
            "UVW": t.getcol("UVW"),
            "TIME": t.getcol("TIME"),
            "ANTENNA1": t.getcol("ANTENNA1"),
            "ANTENNA2": t.getcol("ANTENNA2"),
            "WEIGHT_SPECTRUM": t.getcol("WEIGHT_SPECTRUM")[
                :, CHANNELS[0] : CHANNELS[1]
            ],
            "FIELD_ID": t.getcol("FIELD_ID"),
            "DATA_DESC_ID": t.getcol("DATA_DESC_ID"),
        }
    with table(str(ms) + "/SPECTRAL_WINDOW", ack=False, readonly=True) as sw:
        common["CHAN_FREQ"] = sw.getcol("CHAN_FREQ")[0, CHANNELS[0] : CHANNELS[1]]
    with table(str(ms) + "/FIELD", ack=False, readonly=True) as field:
        common["PHASE_DIR"] = field.getcol("PHASE_DIR")[0, 0]
    with table(str(ms) + "/POLARIZATION", ack=False, readonly=True) as pol:
        common["CORR_TYPE"] = pol.getcol("CORR_TYPE")[0]
    np.savez(output / f"{role}-common.npz", **common)


def write_checkpoint(ms, checkpoint):
    from casacore.tables import table

    with table(str(ms), ack=False, readonly=False) as t:
        if "IMAGING_WEIGHT_SPECTRUM" in t.colnames():
            t.removecols("IMAGING_WEIGHT_SPECTRUM")
        t.putcol("CORRECTED_DATA", checkpoint["CORRECTED_DATA"])
        t.putcol("FLAG", checkpoint["FLAG"])
        t.putcol("FLAG_ROW", checkpoint["FLAG_ROW"])
        t.flush()
        for key in ("CORRECTED_DATA", "FLAG", "FLAG_ROW"):
            if not np.array_equal(t.getcol(key), checkpoint[key]):
                raise RuntimeError(f"{key} persistence mismatch")


def read_imaging_weights(ms):
    from casacore.tables import table

    with table(str(ms), ack=False, readonly=True) as t:
        weights = t.getcol("IMAGING_WEIGHT_SPECTRUM")
    return weights[:, CHANNELS[0] : CHANNELS[1]]


def main(archive, output):
    archive, output = Path(archive), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for sub in ("images", "logs", "work", "temp", "inputs"):
        (output / sub).mkdir()
    receipt = {
        "archive": str(archive),
        "wsclean_binary_sha256": sha256("/usr/bin/wsclean"),
        "wsclean_version": subprocess.run(
            ["/usr/bin/wsclean", "-version"],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.splitlines()[0:2],
        "channels": list(CHANNELS),
        "jobs": {},
        "timings_s": {},
    }
    work = {}
    for role in ("response", "caracal"):
        start = time.perf_counter()
        source = archive / f"{role}-diagnostic.ms"
        work[role] = output / "work" / f"{role}.ms"
        shutil.copytree(source, work[role])
        export_common(work[role], role, output / "inputs")
        receipt["timings_s"][f"copy_and_export_{role}"] = time.perf_counter() - start
    for label in LABELS:
        job_start = time.perf_counter()
        result = json.loads(
            (archive / "checkpoints" / f"{label}-result.json").read_text()
        )
        role = result["role"]
        ms = work[role]
        checkpoint = np.load(archive / "checkpoints" / f"{label}-written.npz")
        write_checkpoint(ms, checkpoint)
        command = json.loads(
            (archive / "checkpoints" / f"{label}-command.json").read_text()
        )
        command = list(command)
        command[command.index("-name") + 1] = str(output / "images" / label)
        command[command.index("-temp-dir") + 1] = str(output / "temp")
        command[-1] = str(ms)
        command.insert(len(command) - 1, "-store-imaging-weights")
        start = time.perf_counter()
        with (output / "logs" / f"{label}-wsclean.log").open("x") as log:
            completed = subprocess.run(
                command, stdout=log, stderr=subprocess.STDOUT, cwd=output, check=False
            )
        wsclean_seconds = time.perf_counter() - start
        if completed.returncode:
            raise RuntimeError(
                f"WSClean failed for {label}: code {completed.returncode}"
            )
        log_text = (output / "logs" / f"{label}-wsclean.log").read_text()
        imaging_weights = read_imaging_weights(ms)
        if not np.array_equal(imaging_weights[..., 0], imaging_weights[..., 3]):
            raise RuntimeError("stored imaging weights differ between XX and YY")
        np.savez(
            output / "inputs" / f"{label}-inputs.npz",
            IMAGING_WEIGHT=imaging_weights[..., 0],
            FLAG=checkpoint["FLAG"][:, CHANNELS[0] : CHANNELS[1]],
            FLAG_ROW=checkpoint["FLAG_ROW"],
            checkpoint_sha256=np.array(
                sha256(archive / "checkpoints" / f"{label}-written.npz")
            ),
        )
        job = {
            "role": role,
            "command": command,
            "wsclean_seconds": wsclean_seconds,
            "log": parse_log(log_text),
            "fits": {},
        }
        for kind in ("dirty", "psf"):
            rerun_path = output / "images" / f"{label}-{kind}.fits"
            archive_path = archive / "images" / f"{label}-{kind}.fits"
            rerun, header = read_fits(rerun_path)
            archived, archived_header = read_fits(archive_path)
            delta = rerun - archived
            job["fits"][kind] = {
                "rerun_sha256": sha256(rerun_path),
                "archive_sha256": sha256(archive_path),
                "identical_bytes": sha256(rerun_path) == sha256(archive_path),
                "max_abs_difference": float(np.max(np.abs(delta))),
                "rms_difference": float(np.sqrt(np.mean(delta**2))),
                "archive_peak": float(np.max(np.abs(archived))),
                "header": header_subset(header),
                "archive_header": header_subset(archived_header),
            }
        job["seconds"] = time.perf_counter() - job_start
        receipt["jobs"][label] = job
        print(
            label,
            role,
            f"{wsclean_seconds:.2f}s",
            "dirty identical"
            if job["fits"]["dirty"]["identical_bytes"]
            else f"dirty max|d|={job['fits']['dirty']['max_abs_difference']:.3e}",
            "psf identical"
            if job["fits"]["psf"]["identical_bytes"]
            else f"psf max|d|={job['fits']['psf']['max_abs_difference']:.3e}",
            flush=True,
        )
    shutil.rmtree(output / "work")
    shutil.rmtree(output / "temp")
    receipt["input_sha256"] = {
        p.name: sha256(p) for p in sorted((output / "inputs").iterdir())
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True))
    print("receipt", output / "receipt.json")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
