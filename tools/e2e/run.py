# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end run of the MS-to-image tutorial's chain (task E4,
research/e4-tutorial.md), as the wheels workflow's `e2e` job runs it on
every platform.

    python tools/e2e/run.py OUT_DIR [--rang-core CMD] [--workers N] [--installed]

1. writes A1 small (research/a1-simtruth.md) into OUT_DIR with
   examples/a1_simtruth.py (a source checkout is needed for it and for
   data/meerkat.itrf.txt; rang-core itself may come from a wheel);
2. `rang-core config check` and `rang-core run` with
   examples/ms-to-image/config.yaml;
3. checks that every output exists and that the numbers in BOUNDS hold;
4. a copy of the MS relabelled to circular feeds (RR, RL, LR, LL): `rang-core
   flag` must refuse it with exit 2 and change nothing.

`--rang-core` is the command (default: this Python's `-m rang.core_cli`).
`--installed` (CI) also checks that `rang` is imported from an installed
wheel, not from this checkout's `python/`.
Writes OUT_DIR/e2e.json with every number and check and exits 1 when a check
fails. CPU-light: about 15 s of work on a laptop.
"""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "examples" / "ms-to-image" / "config.yaml"
GENERATOR = ROOT / "examples" / "a1_simtruth.py"
TARGET = "SIM-TARGET"
STAGES = ("flag", "calibrate", "apply", "image")
IMAGES = ("image-image", "image-model", "image-residual", "image-dirty", "image-psf")
TABLES = ("K", "G", "B", "Gsec", "F")
# Chosen after one local run (Windows x86_64, 2026-11-11; research/e4-tutorial.md
# section 3), wide enough for other platforms' arithmetic. Measured there:
# flagged 0.364, peak 0.4957 Jy, residual rms 0.70 mJy, restoring beam
# 29.0" x 4.97".
BOUNDS = {
    "flagged_fraction": (0.30, 0.43),
    "brightest_peak_jy": (0.475, 0.525),  # truth 0.500 Jy at 1284 MHz
    "residual_rms_mjy": (0.5, 1.0),
    "beam_major_arcsec": (26.0, 32.0),
    "beam_minor_arcsec": (4.5, 5.5),
    "model_data_target_max_jy": (0.05, 5.0),
}


def sha256_columns(ms, names):
    from rang import core_ms

    digest = {}
    with core_ms.open_table(str(ms)) as t:
        for name in names:
            digest[name] = hashlib.sha256(
                np.ascontiguousarray(t.getcol(name)).tobytes()
            ).hexdigest()
    return digest


def run(cmd, log):
    started = time.perf_counter()
    cmd = [str(c) for c in cmd]
    p = subprocess.run(
        cmd, check=False, capture_output=True, text=True, encoding="utf-8"
    )
    seconds = time.perf_counter() - started
    log.write_text(
        "$ " + shlex.join(map(str, cmd)) + "\n" + p.stdout + p.stderr, encoding="utf-8"
    )
    return p.returncode, p.stdout + p.stderr, seconds


def image_numbers(folder, truth):
    from astropy.io import fits
    from astropy.wcs import WCS

    with fits.open(folder / "image-image.fits") as hdul:
        header = hdul[0].header
        image = hdul[0].data.squeeze()
    residual = fits.getdata(folder / "image-residual.fits").squeeze()
    wcs = WCS(header).celestial
    nu = float(header["CRVAL3"])
    brightest = max(truth["target_components"], key=lambda c: c["flux"])
    x, y = wcs.world_to_pixel_values(brightest["ra_deg"], brightest["dec_deg"])
    x, y = round(float(x)), round(float(y))
    return {
        "frequency_hz": nu,
        "brightest_true_jy": brightest["flux"]
        * (nu / brightest["ref_freq_hz"]) ** brightest["alpha"],
        "brightest_peak_jy": float(image[y - 2 : y + 3, x - 2 : x + 3].max()),
        "residual_rms_mjy": float(np.std(residual)) * 1e3,
        "beam_major_arcsec": float(header["BMAJ"]) * 3600,
        "beam_minor_arcsec": float(header["BMIN"]) * 3600,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--rang-core", default=None)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args(argv)
    out = args.out.resolve()
    if out.exists():
        raise SystemExit(f"{out} exists; choose a fresh directory")
    out.mkdir(parents=True)
    rang_core = (
        shlex.split(args.rang_core)
        if args.rang_core
        else [sys.executable, "-m", "rang.core_cli"]
    )
    record = {"checks": {}, "numbers": {}, "seconds": {}, "bounds": BOUNDS}
    checks = record["checks"]
    import rang

    record["rang"] = {"file": rang.__file__, "version": rang.__version__}
    if args.installed:
        checks["rang from an installed wheel"] = (
            ROOT / "python" not in Path(rang.__file__).resolve().parents
        )

    # 1. The MS.
    code, _, seconds = run(
        [
            sys.executable,
            GENERATOR,
            "generate",
            "small",
            out,
            "--workers",
            args.workers,
        ],
        out / "generate.log",
    )
    record["seconds"]["generate"] = seconds
    ms = out / "a1-small.ms"
    checks["generate exits 0"] = code == 0 and ms.is_dir()
    if not checks["generate exits 0"]:
        return finish(out, record)
    truth = json.loads((out / "truth.json").read_text(encoding="utf-8"))
    pristine = out / "pristine.ms"
    shutil.copytree(ms, pristine)

    # 2. The chain.
    shutil.copy(CONFIG, out / "config.yaml")
    shutil.copy(CONFIG.with_name("strategy.yaml"), out / "strategy.yaml")
    config = out / "config.yaml"
    code, text, seconds = run(
        [*rang_core, "config", "check", config, ms], out / "config-check.log"
    )
    checks["config check exits 0"] = code == 0 and "valid for" in text
    code, text, seconds = run([*rang_core, "run", config, ms], out / "run.log")
    record["seconds"]["run"] = seconds
    checks["run exits 0"] = code == 0
    rundir = Path(str(ms) + ".rang-run")
    state = json.loads((rundir / "state.json").read_text(encoding="utf-8"))
    for stage in STAGES:
        entry = state["stages"].get(stage, {})
        checks[f"{stage} done"] = entry.get("status") == "done"
        record["seconds"][stage] = entry.get("seconds")

    # 3. Outputs and numbers.
    from rang import core_ms
    from rang.formats import flagversions

    names = [n for n, _ in flagversions.versions(ms)]
    record["flag_versions"] = names
    checks["flag version rang_original"] = "rang_original" in names
    for stage in STAGES[:3]:
        checks[f"flag version rang_{stage}_*"] = any(
            n.startswith(f"rang_{stage}_") for n in names
        )
    with core_ms.open_table(str(ms)) as t:
        columns = set(t.colnames())
        flag = t.getcol("FLAG")
        field = t.getcol("FIELD_ID")
        model = t.getcol("MODEL_DATA") if "MODEL_DATA" in columns else None
        corrected = t.getcol("CORRECTED_DATA") if "CORRECTED_DATA" in columns else None
    for name in ("CORRECTED_DATA", "MODEL_DATA"):
        checks[f"column {name}"] = name in columns
    with core_ms.open_table(str(ms / "FIELD")) as t:
        target = list(t.getcol("NAME")).index(TARGET)
    numbers = record["numbers"]
    numbers["flagged_fraction"] = float(flag.mean())
    if corrected is not None:
        good = ~flag & (field[:, None, None] == target)
        checks["CORRECTED_DATA finite on the target"] = bool(
            np.isfinite(corrected[good]).all()
        )
    if model is not None:
        numbers["model_data_target_max_jy"] = float(
            np.abs(model[field == target]).max()
        )
    for table in TABLES:
        checks[f"table {table}"] = (
            rundir / "calibrate" / table / "table.dat"
        ).is_file()
    folder = rundir / "image" / TARGET
    for name in IMAGES:
        checks[f"{name}.fits"] = (folder / f"{name}.fits").is_file()
    receipts = sorted((rundir / "receipts").glob("run-*.rang-receipt.json"))
    checks["receipt"] = bool(receipts)
    if receipts:
        receipt = json.loads(receipts[-1].read_text(encoding="utf-8"))
        checks["receipt schema rang.receipt"] = receipt.get("schema") == "rang.receipt"
    if checks["image-image.fits"] and checks["image-residual.fits"]:
        numbers.update(image_numbers(folder, truth))
    for key, (low, high) in BOUNDS.items():
        value = numbers.get(key)
        checks[f"{low} <= {key} <= {high}"] = value is not None and low <= value <= high

    # 4. A refusal: circular feeds change nothing.
    circular = out / "circular.ms"
    shutil.copytree(pristine, circular)
    from rang import core_ms_write

    with core_ms_write.open_table(str(circular / "POLARIZATION"), readonly=False) as t:
        t.putcell("CORR_TYPE", 0, np.array([5, 6, 7, 8], np.int32))  # RR RL LR LL
    before = sha256_columns(circular, ("FLAG", "DATA"))
    code, text, _ = run([*rang_core, "flag", config, circular], out / "circular.log")
    checks["circular feeds: exit 2"] = code == 2
    checks["circular feeds: says circular and linear"] = (
        "circular" in text and "linear" in text
    )
    checks["circular feeds: MS unchanged"] = (
        before == sha256_columns(circular, ("FLAG", "DATA"))
        and not (Path(str(circular) + ".flagversions")).exists()
    )
    for path in (pristine, circular):
        shutil.rmtree(path, ignore_errors=True)
    return finish(out, record)


def finish(out, record):
    record["platform"] = {
        "python": sys.version,
        "os": os.name,
        "platform": sys.platform,
    }
    record["passed"] = all(record["checks"].values())
    (out / "e2e.json").write_text(
        json.dumps(record, indent=1, sort_keys=True), encoding="utf-8"
    )
    for name, ok in record["checks"].items():
        print(("ok    " if ok else "FAIL  ") + name)
    for key, value in sorted(record["numbers"].items()):
        print(f"{key} = {value:.6g}")
    for key, value in record["seconds"].items():
        if value is not None:
            print(f"{key}: {value:.1f} s")
    print("passed" if record["passed"] else "FAILED")
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
