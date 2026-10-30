"""Export the LUNO 1934-638 four-station slice for the certified CLEAN driver.

Research note: research/clean-certified-imaging.md. Reads the O-CASA arm C
Measurement Set (CASA-calibrated CORRECTED_DATA, field 1) through the core's
own reader, forms WSClean's `-pol I` Stokes I and Briggs 0.5 imaging weights
on the core, compares the core's exact-gridder dirty image and PSF with
WSClean 3.7 `-gridder wgridder` FITS (`--reference NAME=PREFIX`, reading
`PREFIX-dirty.fits` and `PREFIX-psf.fits`), and writes raw little-endian
arrays for the Rust example `clean_certified`:

    uvw.f64   (nrow, 3) metres
    freq.f64  (nchan,) Hz
    vis.c128  (nrow, nchan) Stokes I, interleaved re/im
    wgt.f64   (nrow, nchan) gridding weight (Stokes I weight x Briggs weight,
              zero on unselected or flagged rows)
    wsclean-psf-NAME.f64  (512, 512) a WSClean PSF in the gridder layout
              (`--wsclean-psf NAME=FITS`)
    meta.json shapes, counts, weight sums, SHA256s and the comparisons

Usage:
    .venv/bin/python examples/clean_certified_export.py MS OUT_DIR \
        [--reference NAME=PREFIX ...] [--wsclean-psf NAME=FITS ...]
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from rang import core_ms, core_weights, core_wgridder
from rang.core_imaging import read_fits

SIZE = 512
SCALE_ARCSEC = 8.0
ROBUST = 0.5
FIELD = 1


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(ms):
    with core_ms.open_table(ms) as table:
        cols = {
            name: table.getcol(name)
            for name in (
                "UVW",
                "CORRECTED_DATA",
                "FLAG",
                "FLAG_ROW",
                "WEIGHT_SPECTRUM",
                "FIELD_ID",
                "ANTENNA1",
                "ANTENNA2",
                "DATA_DESC_ID",
            )
        }
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as spw:
        cols["CHAN_FREQ"] = spw.getcol("CHAN_FREQ")[0]
    with core_ms.open_table(Path(ms) / "POLARIZATION") as pol:
        cols["CORR_TYPE"] = pol.getcol("CORR_TYPE")[0]
    return cols


def compare(images, prefix):
    """Core dirty image and PSF (FITS order) against one WSClean pair."""
    dirty, _ = read_fits(f"{prefix}-dirty.fits")
    psf, _ = read_fits(f"{prefix}-psf.fits")
    peak = float(np.abs(dirty).max())
    inner = slice(SIZE // 4, 3 * SIZE // 4)
    return {
        "prefix": str(Path(prefix).resolve()),
        "dirty_sha256": _sha(f"{prefix}-dirty.fits"),
        "psf_sha256": _sha(f"{prefix}-psf.fits"),
        "dirty_linf_over_peak": float(np.abs(images["dirty"] - dirty).max() / peak),
        "dirty_inner_half_linf_over_peak": float(
            np.abs(images["dirty"][inner, inner] - dirty[inner, inner]).max() / peak
        ),
        "psf_linf": float(np.abs(images["psf"] - psf).max()),
        "reference_dirty_peak": float(dirty.max()),
        "reference_psf_max": float(psf.max()),
        "reference_dirty_argmax_yx": [
            int(i) for i in np.unravel_index(np.argmax(dirty), dirty.shape)
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ms")
    parser.add_argument("out_dir")
    parser.add_argument(
        "--reference", action="append", default=[], metavar="NAME=PREFIX"
    )
    parser.add_argument(
        "--wsclean-psf", action="append", default=[], metavar="NAME=FITS"
    )
    args = parser.parse_args(argv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.perf_counter()
    cols = read(args.ms)
    t_read = time.perf_counter()
    if tuple(int(c) for c in cols["CORR_TYPE"]) != (9, 10, 11, 12):
        raise SystemExit("XX, XY, YX, YY correlations required")
    rows = (
        (cols["FIELD_ID"] == FIELD)
        & (cols["ANTENNA1"] != cols["ANTENNA2"])
        & (cols["DATA_DESC_ID"] == 0)
    )
    vis, weight = core_weights.stokes_i(
        cols["CORRECTED_DATA"], cols["WEIGHT_SPECTRUM"], cols["FLAG"]
    )
    freq = np.ascontiguousarray(cols["CHAN_FREQ"], np.float64)
    uvw = np.ascontiguousarray(cols["UVW"], np.float64)
    padded = core_weights.padded_size(SIZE)
    imaging = core_weights.imaging_weights(
        uvw,
        core_weights.wsclean_wavelengths(freq),
        weight,
        rows,
        mode="briggs",
        robust=ROBUST,
        width=padded,
        height=padded,
        pixel_scale=core_weights.pixel_scale_radians(SCALE_ARCSEC),
        return_grid=False,
    )
    gw = weight.astype(np.float64) * imaging["weights"].astype(np.float64)
    gw[~rows] = 0.0
    gw[np.asarray(cols["FLAG_ROW"], bool)] = 0.0
    vis128 = np.ascontiguousarray(vis, np.complex128)
    t_weights = time.perf_counter()

    images = core_wgridder.fits_image(
        uvw, freq, vis128, gw, SIZE, SIZE, SCALE_ARCSEC, epsilon=1e-9
    )
    t_image = time.perf_counter()
    comparisons = {}
    for item in args.reference:
        name, prefix = item.split("=", 1)
        comparisons[name] = compare(images, prefix)

    uvw.tofile(out / "uvw.f64")
    freq.tofile(out / "freq.f64")
    vis128.tofile(out / "vis.c128")
    np.ascontiguousarray(gw).tofile(out / "wgt.f64")
    wsclean_psfs = {}
    for item in args.wsclean_psf:
        name, path = item.split("=", 1)
        pixels, _ = read_fits(path)
        # FITS order is the gridder image transposed (DF1 item 0).
        np.ascontiguousarray(pixels.T, np.float64).tofile(
            out / f"wsclean-psf-{name}.f64"
        )
        wsclean_psfs[name] = {
            "fits": str(Path(path).resolve()),
            "fits_sha256": _sha(path),
            "max": float(pixels.max()),
            "centre": float(pixels[SIZE // 2, SIZE // 2]),
            "linf_vs_core_psf": float(np.abs(pixels - images["psf"]).max()),
        }
    meta = {
        "ms": str(Path(args.ms).resolve()),
        "field": FIELD,
        "size": SIZE,
        "scale_arcsec": SCALE_ARCSEC,
        "weighting": f"briggs {ROBUST}, padded weight grid {padded}, rank filter default",
        "nrow": int(uvw.shape[0]),
        "nchan": int(freq.size),
        "rows_selected": int(rows.sum()),
        "active_visibilities": int(np.count_nonzero(gw)),
        "gridding_weight_sum": float(gw.sum()),
        "imaging_weight_sums": imaging["sums"],
        "psf_centre_raw_wgridder": images["psf_centre_raw"],
        "frequency_range_hz": [float(freq.min()), float(freq.max())],
        "core_dirty_peak": float(images["dirty"].max()),
        "core_dirty_argmax_yx": [
            int(i)
            for i in np.unravel_index(np.argmax(images["dirty"]), images["dirty"].shape)
        ],
        "core_psf_max": float(images["psf"].max()),
        "comparisons": comparisons,
        "wsclean_psfs": wsclean_psfs,
        "sha256": {
            name: _sha(out / name)
            for name in ("uvw.f64", "freq.f64", "vis.c128", "wgt.f64")
        },
        "seconds": {
            "read": t_read - t0,
            "stokes_and_weights": t_weights - t_read,
            "core_dirty_psf_eps1e-9": t_image - t_weights,
        },
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n")
    np.save(out / "core-dirty-fits-order.npy", images["dirty"])
    np.save(out / "core-psf-fits-order.npy", images["psf"])
    print(json.dumps(meta, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
