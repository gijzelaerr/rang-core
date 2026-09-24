"""Pinned WSClean dirty-image evaluation of frozen MeerKAT gain controls.

Evaluation only: known injection templates and TEST DATA never select a flag
policy. Original tables are read-only; CORRECTED_DATA/diagnostic masks live only
in fresh copies. WSClean owns gridding; Python performs bounded audit algebra.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

import numpy as np

from .flagging import assert_preserved, protected_flags
from .flagging_prepared import reject_nested_paths, validate_prepared_state
from .flagging_workflow import load_state, tree_digest, write_json

PACKAGE_VERSION = "3.6-1"
SNAPSHOT_URL = "https://snapshot.debian.org/archive/debian/20250901T000000Z/"
SETTINGS = {
    "size": [512, 512],
    "scale_arcsec": 8.0,
    "robust": 0.5,
    "polarization": "I",
    "channels": [1024, 3072],
    "gridder": "wstacking",
    "w_layers": 64,
    "threads": 1,
    "niter": 0,
    "small_inversion": False,
    "update_model_required": False,
    "memory_gib": 0.5,
}
IMAGE_CLOSURE_JY = 1e-6
VISIBILITY_CLOSURE_JY = 1e-10
BUDGET_BYTES = 1536 * 1024**2
RESERVE_BYTES = 8 * 1024**3
WEIGHT_COLUMNS = ("WEIGHT", "WEIGHT_SPECTRUM", "SIGMA", "SIGMA_SPECTRUM")


def _bool(value, shape, label):
    value = np.asarray(value)
    if value.dtype != np.bool_ or value.shape != shape:
        raise ValueError(f"bool {label} with shape {shape} required")
    return value


def image_flags(state, support, added=None):
    """Keep original FLAG/FLAG_ROW lower bounds and a frozen diagnostic support."""
    original = np.asarray(state["original_flags"])
    if original.ndim != 3 or original.shape[-1] != 4:
        raise ValueError("original four-correlation FLAG cube required")
    _bool(original, original.shape, "original flags")
    rows = _bool(state["original_rows"], (len(original),), "original rows")
    shape = original.shape[:2]
    support = _bool(support, shape, "image support")
    window = _bool(state["window"], (shape[1],), "window")
    protected = (
        original.any(axis=-1)
        | rows[:, None]
        | (state["antenna1"] == state["antenna2"])[:, None]
        | ~window[None, :]
    )
    if np.any(support & protected):
        raise ValueError("image support overlaps original flags/rows/autos/window")
    additional = ~support
    if added is not None:
        added = _bool(added, shape, "frozen additions")
        train = _bool(state["train"], shape, "TRAIN")
        if np.any(added & (~train | protected)):
            raise ValueError("frozen additions must be eligible TRAIN-only")
        additional = additional | added
    return protected_flags(
        original, rows, np.broadcast_to(additional[..., None], original.shape)
    )


def corrected_visibilities(state, diagnostics, support, data=None, intervals=(2, 32)):
    """Wide inverse-Jones correction on explicit support; invalid gains abstain.

    Native weights are not transformed/replaced. The resulting images therefore
    use matched native-weight proxies, not optimal post-calibration covariance.
    """
    data = np.asarray(state["data"] if data is None else data, np.complex128)
    shape = state["data"].shape
    if data.shape != shape or len(shape) != 3 or shape[-1] != 4:
        raise ValueError("DATA with original four-correlation shape required")
    support = _bool(support, shape[:2], "correction support")
    image_flags(state, support)
    if len(intervals) != 2 or any(type(x) is not int or x <= 0 for x in intervals):
        raise ValueError("positive integer gain intervals required")
    rows, channels = np.where(support)
    ti = np.unique(state["times"], return_inverse=True)[1][rows] // intervals[0]
    fi = channels // intervals[1]
    gains = np.asarray(diagnostics["gains"], np.complex128)
    valid = np.asarray(diagnostics["gain_valid"])
    if gains.ndim != 5 or gains.shape[-2:] != (2, 2):
        raise ValueError("time/frequency/antenna full2x2 gains required")
    _bool(valid, gains.shape[:3], "gain validity")
    if len(rows) and (ti.max() >= gains.shape[0] or fi.max() >= gains.shape[1]):
        raise ValueError("gain grid does not cover support")
    p, q = state["antenna1"][rows], state["antenna2"][rows]
    gp, gq = gains[ti, fi, p], gains[ti, fi, q]
    good = valid[ti, fi, p] & valid[ti, fi, q]
    good &= np.isfinite(gp).all(axis=(-1, -2)) & np.isfinite(gq).all(axis=(-1, -2))
    weights = np.asarray(state["weights"])[rows, channels]
    if (
        not np.isfinite(data[rows, channels]).all()
        or not np.isfinite(weights).all()
        or np.any(weights <= 0)
    ):
        raise ValueError(
            "finite DATA and positive native four-product weights required"
        )
    safe_p, safe_q = (
        np.where(good[:, None, None], gp, np.eye(2)),
        np.where(good[:, None, None], gq, np.eye(2)),
    )
    good &= (np.linalg.cond(safe_p) <= 1e8) & (np.linalg.cond(safe_q) <= 1e8)
    result = np.zeros(shape, np.complex128)
    if good.any():
        corrected = (
            np.linalg.inv(gp[good])
            @ data[rows[good], channels[good]].reshape(-1, 2, 2)
            @ np.linalg.inv(gq[good]).conj().swapaxes(-1, -2)
        )
        if not np.isfinite(corrected).all():
            raise ValueError("nonfinite inverse-Jones prediction")
        result[rows[good], channels[good]] = corrected.reshape(-1, 4)
    actual = np.zeros(shape[:2], bool)
    actual[rows[good], channels[good]] = True
    return result, actual


def paired_decomposition(state, injected, clean_gains, new_gains, support):
    """Exact conditional total=direct+adaptation BEFORE complex64 storage."""
    original = np.asarray(state["data"], np.complex128)
    injected = np.asarray(injected, np.complex128)
    base, s0 = corrected_visibilities(state, clean_gains, support, original)
    changed, s1 = corrected_visibilities(state, new_gains, support, injected)
    old_changed, s2 = corrected_visibilities(state, new_gains, support, original)
    direct, s3 = corrected_visibilities(state, new_gains, support, injected - original)
    if not all(np.array_equal(support, s) for s in (s0, s1, s2, s3)):
        raise ValueError("response images require identical complete TEST support")
    total, adaptation = changed - base, old_changed - base
    closure = float(
        np.max(np.abs(total[support] - direct[support] - adaptation[support]))
    )
    if closure > VISIBILITY_CLOSURE_JY:
        raise RuntimeError("wide visibility decomposition closure failed")
    return {
        "full": changed,
        "total": total,
        "direct": direct,
        "adaptation": adaptation,
    }, closure


def linear_image_fit(image, templates):
    """Joint unrestricted known-family dirty-template coefficients; no CI."""
    image, templates = np.asarray(image, float), np.asarray(templates, float)
    if (
        image.ndim != 2
        or templates.shape != (2, *image.shape)
        or not np.isfinite(image).all()
        or not np.isfinite(templates).all()
    ):
        raise ValueError("finite image and two matched dirty templates required")
    design, target = templates.reshape(2, -1).T, image.ravel()
    coefficients, _, rank, singular = np.linalg.lstsq(design, target, rcond=1e-10)
    condition = (
        float(singular[0] / singular[-1])
        if singular.size == 2 and singular[-1] > 0
        else None
    )
    available = rank == 2 and condition is not None and condition <= 1e8
    return {
        "available": bool(available),
        "rank": int(rank),
        "condition": condition,
        "coefficients_jy": coefficients.tolist() if available else None,
        "unweighted_pixel_MSE_proxy": float(
            np.mean((target - design @ coefficients) ** 2)
        ),
        "pixel_count": int(image.size),
        "confidence_intervals": "not claimed: correlated dirty pixels, shared DATA/gains, known family",
        "blind_flux_or_morphology_recovery": False,
    }


def image_diagnostics(image):
    """Fixed regions; dirty offsource RMS includes sidelobes, not thermal noise."""
    image = np.asarray(image, float)
    if image.shape != tuple(SETTINGS["size"]) or not np.isfinite(image).all():
        raise ValueError("finite frozen512x512 image required")
    y, x = np.indices(image.shape)
    l, m = (256 - x) * 8 / 60, (y - 256) * 8 / 60
    region = (
        (np.hypot(l, m) >= 25)
        & (np.hypot(l - 9, m + 6) >= 12)
        & (np.hypot(l + 12, m + 14) >= 12)
    )
    values = image[region]
    return {
        "fixed_offsource_pixels": int(region.sum()),
        "dirty_offsource_RMS_jy_per_beam": float(np.sqrt(np.mean(values**2))),
        "dirty_offsource_std_jy_per_beam": float(np.std(values)),
        "peak_abs_jy_per_beam": float(np.max(np.abs(image))),
        "RMS_role": "fixed-region dirty diagnostic; includes PSF sidelobes/real sky, not independent thermal noise",
    }


def wsclean_command(binary, ms, prefix, tempdir):
    return [
        str(binary),
        "-name",
        str(prefix),
        "-size",
        "512",
        "512",
        "-scale",
        "8asec",
        "-weight",
        "briggs",
        "0.5",
        "-pol",
        "I",
        "-channel-range",
        "1024",
        "3072",
        "-field",
        "0",
        "-data-column",
        "CORRECTED_DATA",
        "-gridder",
        "wstacking",
        "-wstack-nwlayers",
        "64",
        "-j",
        "1",
        "-abs-mem",
        "0.5",
        "-niter",
        "0",
        "-make-psf",
        "-no-update-model-required",
        "-no-min-grid-resolution",
        "-no-reorder",
        "-temp-dir",
        str(tempdir),
        str(ms),
    ]


class Budget:
    """Checked allocated-block budget/reservation, NOT an OS filesystem quota."""

    def __init__(self, root):
        self.root = Path(root)

    def check(self, future=0):
        paths = [self.root, *self.root.rglob("*")]
        if any(p.is_symlink() for p in paths):
            raise RuntimeError("derived symlinks forbidden")
        actual = sum(p.stat().st_blocks * 512 for p in paths)
        if future < 0 or actual + future >= BUDGET_BYTES:
            raise RuntimeError("imaging1.5GiB checked allocation budget exceeded")
        if shutil.disk_usage(self.root).free < RESERVE_BYTES + future:
            raise RuntimeError("8GiB reserve would be violated")
        return actual

    def json(self, path, value):
        self.check(2 * len(json.dumps(value, allow_nan=False).encode()) + 4096)
        write_json(path, value)

    def npz(self, path, **arrays):
        self.check(sum(np.asarray(x).nbytes for x in arrays.values()) + 4096)
        with Path(path).open("xb") as stream:
            np.savez_compressed(stream, **arrays)

    def copy(self, source, target):
        source = Path(source)
        if source.is_symlink() or any(p.is_symlink() for p in source.rglob("*")):
            raise ValueError("MS source symlinks forbidden")
        self.check(
            sum(p.stat().st_size for p in source.rglob("*") if p.is_file())
            + 8 * 1024**2
        )
        shutil.copytree(source, target)
        self.check()


def _npz(path, keys=None):
    with np.load(path, allow_pickle=False) as a:
        return {k: a[k] for k in (a.files if keys is None else keys)}


def _runtime():
    names = (
        __name__,
        "rangtoy",
        "rangtoy.flagging",
        "rangtoy.flagging_prepared",
        "rangtoy.flagging_workflow",
    )
    return {
        name: {
            "path": str(Path(sys.modules[name].__file__).resolve()),
            "sha256": sha256(Path(sys.modules[name].__file__).read_bytes()).hexdigest(),
        }
        for name in names
    }


def _tool_receipt():
    path = Path("/opt/rang/imaging-packages.json")
    receipt = json.loads(path.read_text())
    binary = Path(shutil.which("wsclean") or "/missing/wsclean").resolve()
    if (
        receipt["snapshot_url"] != SNAPSHOT_URL
        or receipt["wsclean_package_version"] != PACKAGE_VERSION
        or sha256(binary.read_bytes()).hexdigest() != receipt["wsclean_binary_sha256"]
        or receipt["download_bytes"] > 256 * 1024**2
        or not receipt["preexisting_packages_unchanged"]
    ):
        raise ValueError("unverified WSClean/package/snapshot boundary")
    output = subprocess.run(
        [str(binary), "-version"], capture_output=True, text=True, check=True
    ).stdout
    if "3.6" not in output:
        raise ValueError("unexpected WSClean version")
    return binary, {
        "manifest_sha256": sha256(path.read_bytes()).hexdigest(),
        "package_manifest": receipt,
        "version_stdout": output,
    }


def parser_preflight(binary, ms):
    """Validate the complete command against the pinned binary before any copy.

    WSClean's real -dry-run checks parsing/settings without inversion or MS
    updates. Captured output stays in memory until the fresh output is reserved.
    """
    command = wsclean_command(binary, ms, "/tmp/rang-imaging-parser-only", "/tmp")
    command.insert(1, "-dry-run")
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    output = completed.stdout + completed.stderr
    if completed.returncode or "Unknown parameter:" in output:
        raise RuntimeError(
            "pinned WSClean parser preflight failed before MS copy/write: "
            + output[-2000:]
        )
    return {
        "command": command,
        "returncode": completed.returncode,
        "output": output,
        "output_sha256": sha256(output.encode()).hexdigest(),
        "dry_run_only": True,
        "precedes_any_MS_copy_or_write": True,
    }


def _write_column(ms, state, wide, support, added, label, root, budget):
    from casacore.tables import makearrcoldesc, maketabdesc, table

    flags, rows = image_flags(state, support, added)
    expected = np.asarray(wide, np.complex64)
    rounding = float(np.max(np.abs(np.asarray(wide)[support] - expected[support])))
    budget.check(expected.nbytes * 3 + flags.nbytes + 8 * 1024**2)
    with table(str(ms), readonly=False, ack=False) as work:
        exists = "CORRECTED_DATA" in work.colnames()
        backup = {"FLAG": work.getcol("FLAG"), "FLAG_ROW": work.getcol("FLAG_ROW")}
        if exists:
            backup["CORRECTED_DATA"] = work.getcol("CORRECTED_DATA")
        budget.npz(root / "backups" / f"{label}-before.npz", **backup)
        budget.json(
            root / "backups" / f"{label}-schema.json",
            {
                "columns": work.colnames(),
                "corrected_exists": exists,
                "new_column_type": "complex64 StandardStMan; original DATA/models untouched",
            },
        )
        if not exists:
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
        work.putcol("FLAG", flags)
        work.putcol("FLAG_ROW", rows)
        work.flush()
        if not np.array_equal(work.getcol("CORRECTED_DATA"), expected):
            raise RuntimeError("CORRECTED_DATA persistence mismatch")
        assert_preserved(
            state["original_flags"],
            state["original_rows"],
            work.getcol("FLAG"),
            work.getcol("FLAG_ROW"),
        )
        if not np.array_equal(work.getcol("FLAG"), flags) or not np.array_equal(
            work.getcol("FLAG_ROW"), rows
        ):
            raise RuntimeError("diagnostic mask persistence mismatch")
    budget.npz(
        root / "checkpoints" / f"{label}-written.npz",
        CORRECTED_DATA=expected,
        support=support,
        FLAG=flags,
        FLAG_ROW=rows,
    )
    budget.check()
    return {
        "CORRECTED_DATA_dtype": "complex64",
        "wide_to_native_max_rounding_jy": rounding,
        "logical_support_count": int(support.sum()),
        "native_StokesI_weight": "WSClean minimum native XX/YY WEIGHT_SPECTRUM; no replacement/propagation",
        "flags_exact_diagnostic_mask": True,
        "original_flags_rows_preserved": True,
    }


def _table_audit(ms, input_ms, state, model_column, checkpoint=None):
    from casacore.tables import table

    with (
        table(str(ms), readonly=True, ack=False, lockoptions="autonoread") as work,
        table(
            str(input_ms), readonly=True, ack=False, lockoptions="autonoread"
        ) as original,
    ):
        exact = {
            key: bool(
                np.array_equal(work.getcol(key), original.getcol(key), equal_nan=True)
            )
            for key in (
                "DATA",
                model_column,
                *[
                    x
                    for x in ("MODEL_DATA", "RANG_RESPONSE_MODEL")
                    if x in original.colnames() and x != model_column
                ],
                *[x for x in WEIGHT_COLUMNS if x in original.colnames()],
            )
        }
        assert_preserved(
            state["original_flags"],
            state["original_rows"],
            work.getcol("FLAG"),
            work.getcol("FLAG_ROW"),
        )
        if "MODEL_DATA" in work.colnames() and "MODEL_DATA" not in original.colnames():
            raise RuntimeError("WSClean unexpectedly appended MODEL_DATA")
        if checkpoint is not None:
            written = _npz(checkpoint, ("CORRECTED_DATA", "FLAG", "FLAG_ROW"))
            exact.update(
                {
                    f"written_{key}": bool(np.array_equal(work.getcol(key), value))
                    for key, value in written.items()
                }
            )
    if not all(exact.values()):
        raise RuntimeError(
            "imaging changed DATA/models/weights/SIGMA/written flags or correction"
        )
    return exact


def image_geometry(header):
    """Require frozen pixel scale/axes and expose exact matched FITS WCS."""
    keys = (
        "CRPIX1",
        "CRPIX2",
        "CRVAL1",
        "CRVAL2",
        "CDELT1",
        "CDELT2",
        "CTYPE1",
        "CTYPE2",
    )
    if any(key not in header for key in keys):
        raise RuntimeError("missing image WCS geometry")
    if (
        not np.isclose(header["CDELT1"], -8 / 3600, rtol=0, atol=1e-12)
        or not np.isclose(header["CDELT2"], 8 / 3600, rtol=0, atol=1e-12)
        or header["CTYPE1"] != "RA---SIN"
        or header["CTYPE2"] != "DEC--SIN"
        or not np.isfinite([header[key] for key in keys[:6]]).all()
    ):
        raise RuntimeError("image violates frozen scale/axes")
    return {key: header[key] for key in keys}


def _read_images(prefix):
    from astropy.io import fits

    images, headers = {}, {}
    for kind in ("dirty", "psf"):
        with fits.open(f"{prefix}-{kind}.fits", memmap=False) as hdus:
            value = np.asarray(hdus[0].data, float).squeeze()
            header = hdus[0].header
            if value.shape != (512, 512) or not np.isfinite(value).all():
                raise RuntimeError("invalid/frozen-image shape or support")
            if "WSCDATAC" in header and header["WSCDATAC"] != "CORRECTED_DATA":
                raise RuntimeError("WSClean read unexpected DATA column")
            image_geometry(header)
            if kind == "dirty" and str(header.get("BUNIT", "")).lower() != "jy/beam":
                raise RuntimeError("dirty image unit must be Jy/beam")
            images[kind] = value
            headers[kind] = {
                key: header[key]
                for key in (
                    "BITPIX",
                    "BUNIT",
                    "CRPIX1",
                    "CRPIX2",
                    "CRVAL1",
                    "CRVAL2",
                    "CDELT1",
                    "CDELT2",
                    "CTYPE1",
                    "CTYPE2",
                    "BMAJ",
                    "BMIN",
                    "BPA",
                    "WSCVERSI",
                    "WSCNWLAY",
                    "WSCDATAC",
                    "WSCWEIGH",
                    "WSCNITER",
                    "WSCVWSUM",
                    "WSCNVIS",
                )
                if key in header
            }
    return images, headers


def _plot(root, images, budget):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    budget.check(4 * 1024**2)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), constrained_layout=True)
    for ax, label in zip(
        axes, ("fixedG0-reference", "omitted-total", "complete-total"), strict=True
    ):
        artist = ax.imshow(
            images[label]["dirty"],
            origin="lower",
            extent=(34.1333, -34.1333, -34.1333, 34.1333),
            vmin=-0.06,
            vmax=0.18,
            cmap="coolwarm",
        )
        ax.set_title(label)
        ax.set_xlabel("l offset, arcmin")
    axes[0].set_ylabel("m offset, arcmin")
    fig.colorbar(artist, ax=axes, label="Jy/beam; dirty paired response")
    fig.suptitle(
        "Common TEST; known sky family; no deconvolution or blind flux inference"
    )
    path = root / "dirty-response.png"
    if path.exists():
        raise ValueError("exclusive figure path required")
    fig.savefig(path, dpi=120)
    plt.close(fig)
    budget.check()


def run(
    run_dir,
    response_dir="outputs/tv-response-20260924-precision-01",
    caracal_dir="outputs/tv-caracal-clean-01",
):
    """Fifteen fixed dirty inversions; no QC solve, policy fit/choice or export."""
    output, response = reject_nested_paths(run_dir, response_dir)
    _, caracal = reject_nested_paths(run_dir, caracal_dir)
    outputs_root = Path(__file__).resolve().parents[2] / "outputs"
    if (
        Path(run_dir).is_symlink()
        or output.exists()
        or not output.is_relative_to(outputs_root.resolve())
        or not response.is_dir()
        or not caracal.is_dir()
    ):
        raise ValueError(
            "existing sources and fresh exclusive outputs destination required"
        )
    if shutil.disk_usage(outputs_root).free < RESERVE_BYTES + BUDGET_BYTES:
        raise RuntimeError("8GiB reserve plus1.5GiB imaging allowance required")
    binary, tool = _tool_receipt()
    runtime = _runtime()
    source_hashes = {"response": tree_digest(response), "caracal": tree_digest(caracal)}
    parser = parser_preflight(binary, response / "clean/work.ms")
    case_paths = {
        "clean": response / "clean",
        "positive": response / "positive",
        "caracal": caracal,
    }
    states, manifests, boundaries = {}, {}, {}
    for name, path in case_paths.items():
        states[name] = load_state(path)
        manifests[name] = json.loads((path / "manifest.json").read_text())
        boundaries[name] = validate_prepared_state(path, states[name], manifests[name])
        if manifests[name]["channels"] != [1024, 3072] or manifests[name][
            "split_gain_intervals"
        ] != [2, 32]:
            raise ValueError("frozen L-band channels/gain intervals required")
    state, injected = states["clean"], states["positive"]["data"]
    support = state["test"]
    if support.sum() != 9169 or any(
        not np.array_equal(state[k], states[name][k], equal_nan=True)
        for name in ("positive", "caracal")
        for k in (
            "test",
            "weights",
            "times",
            "frequencies",
            "antenna1",
            "antenna2",
            "original_flags",
            "original_rows",
        )
    ):
        raise ValueError(
            "frozen commonTEST9169/nativeweights/coordinates/originals mismatch"
        )
    g0 = _npz(
        response / "clean/trials/clean-t2-f32/diagnostics.npz", ("gains", "gain_valid")
    )
    baseline, s0 = corrected_visibilities(state, g0, support)
    if not np.array_equal(support, s0):
        raise ValueError("clean baseline TEST support unavailable")
    reference, sr = corrected_visibilities(
        state,
        g0,
        support,
        injected.astype(np.complex128) - state["data"].astype(np.complex128),
    )
    if not np.array_equal(support, sr):
        raise ValueError("fixedG0 reference support unavailable")
    config = json.loads((response / "response-config.json").read_text())
    templates = _npz(response / "spectral-templates.npz")["templates"]
    if templates.shape != (2, *support.shape) or len(config["sources"]) != 2:
        raise ValueError("two frozen unit spatial templates required")
    jobs, closures = [], {}
    for index, source in enumerate(config["sources"]):
        scalar = (
            templates[index]
            * (state["frequencies"] / config["reference_frequency_hz"])
            ** source["spectral_index"]
        )
        unit = np.zeros_like(state["data"], dtype=np.complex128)
        unit[..., 0] = unit[..., 3] = np.where(support, scalar, 0)
        jobs.append((f"unit-{source['name']}", "response", unit, support, None))
    jobs.extend(
        (
            ("fixedG0-reference", "response", reference, support, None),
            ("clean-full", "response", baseline, support, None),
        )
    )
    for name, trial in (
        ("omitted", "omitted-t2-f32"),
        ("complete", "complete-diagnostic-t2-f32"),
    ):
        gains = _npz(
            response / "positive/trials" / trial / "diagnostics.npz",
            ("gains", "gain_valid"),
        )
        parts, closures[name] = paired_decomposition(
            state, injected, g0, gains, support
        )
        for part, values in parts.items():
            jobs.append((f"{name}-{part}", "response", values, support, None))
    for name, trial, native in (
        ("no-change", "baseline", None),
        ("mild", "strategy-01-operational", "strategy-01-operational"),
        ("firstpass-rejected", "strategy-00-operational", "strategy-00-operational"),
    ):
        gains = _npz(
            caracal / "trials" / trial / "diagnostics.npz", ("gains", "gain_valid")
        )
        corrected, actual = corrected_visibilities(states["caracal"], gains, support)
        added = (
            _npz(caracal / "native" / native / "frozen-proposal.npz")["added"]
            if native
            else np.zeros_like(support)
        )
        image_flags(states["caracal"], actual, added)
        jobs.append((f"caracal-{name}", "caracal", corrected, actual, added))
    if len(jobs) != 15:
        raise ValueError("frozen fifteen-job imaging family mismatch")
    output.mkdir(parents=True, exist_ok=False)
    for folder in ("backups", "checkpoints", "images", "temp"):
        (output / folder).mkdir()
    budget = Budget(output)
    budget.json(
        output / "imaging-config.json",
        {
            "settings": SETTINGS,
            "source_hashes": source_hashes,
            "sources": {"response": str(response), "caracal": str(caracal)},
            "boundaries": boundaries,
            "runtime_receipts": runtime,
            "tool": tool,
            "parser_preflight": parser,
            "suite_image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
            "versions": {
                x: version(x) for x in ("numpy", "astropy", "python-casacore")
            },
            "fixed_jobs": [x[0] for x in jobs],
            "common_TEST_samples": 9169,
            "image_closure_tolerance_jy_per_beam": IMAGE_CLOSURE_JY,
            "wide_visibility_closure_tolerance_jy": VISIBILITY_CLOSURE_JY,
            "policy_selection": False,
            "new_QC_solves": 0,
            "template_truth_role": "known family evaluation only; complete QC sky already truth-assisted",
            "budget_bytes": BUDGET_BYTES,
            "reserve_bytes": RESERVE_BYTES,
            "budget_semantics": "checked allocated blocks/reservations, not OS quota",
        },
    )
    work_paths, inputs, input_hashes = {}, {}, {}
    for name, source_path in (("response", response / "clean"), ("caracal", caracal)):
        inputs[name] = output / "backups" / f"{name}-input.ms"
        work_paths[name] = output / f"{name}-diagnostic.ms"
        budget.copy(source_path / "work.ms", inputs[name])
        budget.copy(inputs[name], work_paths[name])
        input_hashes[name] = tree_digest(inputs[name])
    records, all_images = {}, {}
    for label, role, wide, selected, added in jobs:
        role_state = state if role == "response" else states["caracal"]
        role_manifest = (
            manifests["clean"] if role == "response" else manifests["caracal"]
        )
        column_audit = _write_column(
            work_paths[role], role_state, wide, selected, added, label, output, budget
        )
        command = wsclean_command(
            binary, work_paths[role], output / "images" / label, output / "temp"
        )
        budget.json(output / "checkpoints" / f"{label}-command.json", command)
        budget.check(64 * 1024**2)
        start = time.perf_counter()
        with (output / "checkpoints" / f"{label}-wsclean.log").open("x") as log:
            completed = subprocess.run(
                command, stdout=log, stderr=subprocess.STDOUT, cwd=output, check=False
            )
        if completed.returncode:
            raise RuntimeError(
                f"WSClean failed; retained {label} log/copies, code{completed.returncode}"
            )
        images, headers = _read_images(output / "images" / label)
        audit = _table_audit(
            work_paths[role],
            inputs[role],
            role_state,
            role_manifest["model_column"],
            output / "checkpoints" / f"{label}-written.npz",
        )
        geometry = image_geometry(headers["dirty"])
        if geometry != image_geometry(headers["psf"]):
            raise RuntimeError("dirty image/PSF WCS mismatch")
        if records and geometry != next(iter(records.values()))["image_geometry"]:
            raise RuntimeError("fixed imaging family WCS changed")
        records[label] = {
            "role": role,
            "seconds_emulated_not_native_benchmark": time.perf_counter() - start,
            "headers": headers,
            "image_geometry": geometry,
            "FITS_sha256": {
                kind: sha256(
                    (output / "images" / f"{label}-{kind}.fits").read_bytes()
                ).hexdigest()
                for kind in ("dirty", "psf")
            },
            "column_audit": column_audit,
            "native_columns_exact": audit,
            "unsupported_original_TEST_samples": int(support.sum() - selected.sum()),
            "diagnostics": image_diagnostics(images["dirty"]),
            "training_additions": int(added.sum()) if added is not None else 0,
            "selected_for_policy_or_deployment": False,
        }
        all_images[label] = images
        budget.json(output / "checkpoints" / f"{label}-result.json", records[label])
    basis = np.stack(
        [all_images[f"unit-{s['name']}"]["dirty"] for s in config["sources"]]
    )
    reference_fit = linear_image_fit(all_images["fixedG0-reference"]["dirty"], basis)
    image_closures = {}
    psf_reference = all_images["fixedG0-reference"]["psf"]
    for name in ("omitted", "complete"):
        delta = (
            all_images[f"{name}-total"]["dirty"]
            - all_images[f"{name}-direct"]["dirty"]
            - all_images[f"{name}-adaptation"]["dirty"]
        )
        image_closures[name] = float(np.max(np.abs(delta)))
        if image_closures[name] > IMAGE_CLOSURE_JY:
            raise RuntimeError("frozen dirty-image decomposition tolerance failed")
    for label, record in records.items():
        record["PSF_linf_difference_vs_fixedG0"] = float(
            np.max(np.abs(all_images[label]["psf"] - psf_reference))
        )
        if (
            record["role"] == "response"
            or label in ("caracal-no-change", "caracal-mild")
        ) and record["PSF_linf_difference_vs_fixedG0"] > IMAGE_CLOSURE_JY:
            raise RuntimeError("matched-support native-weight PSF changed")
        if record["role"] == "response" and not label.endswith("full"):
            record["known_family_dirty_fit"] = linear_image_fit(
                all_images[label]["dirty"], basis
            )
            fit = record["known_family_dirty_fit"]
            record["conditional_response_vs_fixedG0"] = (
                (
                    np.asarray(fit["coefficients_jy"])
                    / reference_fit["coefficients_jy"]
                ).tolist()
                if fit["available"]
                and reference_fit["available"]
                and not label.startswith("unit-")
                else None
            )
    _plot(output, all_images, budget)
    unchanged = source_hashes == {
        "response": tree_digest(response),
        "caracal": tree_digest(caracal),
    }
    runtime_unchanged = runtime == _runtime()
    tool_unchanged = tool == _tool_receipt()[1]
    backup_unchanged = input_hashes == {
        name: tree_digest(path) for name, path in inputs.items()
    }
    if not (unchanged and runtime_unchanged and tool_unchanged and backup_unchanged):
        raise RuntimeError("imaging source/runtime/tool/whole-MS backup changed")
    result = {
        "status": "measured dirty-image conditional diagnostics; not deconvolved/blind astronomy",
        "settings": SETTINGS,
        "jobs": records,
        "reference_fit": reference_fit,
        "precast_visibility_closures_jy": closures,
        "dirty_image_closures_jy_per_beam": image_closures,
        "source_unchanged": unchanged,
        "runtime_unchanged": runtime_unchanged,
        "tool_unchanged": tool_unchanged,
        "whole_MS_backups_unchanged": backup_unchanged,
        "whole_MS_backup_digests": input_hashes,
        "actual_WSClean_inversions": 15,
        "new_QC_solves": 0,
        "policy_selection": False,
        "exported_or_deployable_MS": False,
        "allocated_bytes_before_final_result": budget.check(),
        "limitations": [
            "one four-antenna112s pointing scan, sparse broadPSF, not representative imaging",
            "dirty known-family fits, no deconvolution/blind detection/astrophysical flux or shape/CI",
            "native original weights fixed; post-Jones covariance not optimal/validated",
            "complete savedQCsky uses truth; templates/TEST are evaluation only, no mask selection",
            "CARACAL rejected control loses support/differentPSF; native flagger saw holdout features; not fullpipeline or winner comparison",
            "diagnostic copies retain frozen additional support flags/CORRECTED_DATA; original MSs remain unchanged",
            "emulated WSClean walltimes not native/end-to-end/SOTA cost benchmark",
        ],
    }
    budget.json(output / "result.json", result)
    budget.check()
    return result
