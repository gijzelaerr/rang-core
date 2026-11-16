# SPDX-License-Identifier: GPL-3.0-or-later
"""Residual snapshot light curves at given positions (task TS-P1,
research/ts-p1.md; issue #9).

After `rang-core run`, the residual of a field is its data column minus
MODEL_DATA. `light_curves` splits the field's rows into intervals of
`interval_steps` consecutive TIME values (one 8 s integration by default:
WSClean's `-intervals-out N` for N timesteps) and gives, per interval and
position:

- `flux_jy`: the exact DFT of the Stokes I residual at the position
  (`rang._core.lightcurve_dft`, `core/src/lightcurve.rs`), natural weights;
- `flux_snapshot_jy`: the pixel nearest to the position in the interval's
  dirty image (the exact wgridder, WSClean's FITS orientation and
  normalisation), with the pixel's offset from the position;
- `sigma_meas_jy`: 1.4826 times the median absolute deviation of that image.

Stokes I and its weight follow WSClean's `-pol I` (`core_weights.stokes_i`):
`I = (XX + YY) / 2`, weight `min(4 w_XX, 4 w_YY)`, zero when a hand is
flagged; FLAG_ROW rows weigh zero. Rows: the field, data description 0,
cross-correlations (`core_model.selected_rows`). Linear feeds with four
correlations only (MeerKAT). The MS is only read.
"""

import csv
import json
import math
import re
import time
from pathlib import Path

import numpy as np

from . import core, core_grid, core_model, core_ms, core_weights, core_wgridder

__all__ = [
    "LightcurveError",
    "light_curves",
    "lm_from_radec",
    "parse_position",
    "write_outputs",
]

ARCSEC = math.pi / (180.0 * 3600.0)
LINEAR = [9, 10, 11, 12]
MAD_TO_SIGMA = 1.482602218505602
CSV_COLUMNS = (
    "interval",
    "time_mjd_s",
    "timesteps",
    "position",
    "ra_deg",
    "dec_deg",
    "flux_jy",
    "flux_snapshot_jy",
    "sigma_meas_jy",
    "pixel_x",
    "pixel_y",
    "pixel_offset_arcsec",
    "weight_sum",
    "samples",
    "rows",
)


class LightcurveError(ValueError):
    """A refusal: the inputs cannot give a light curve as asked."""


def _angle(text, hours):
    text = text.strip()
    if ":" in text or re.search(r"[hdms]", text):
        parts = [float(p) for p in re.split(r"[:hdms]+", text.lstrip("+-")) if p]
        while len(parts) < 3:
            parts.append(0.0)
        value = parts[0] + parts[1] / 60.0 + parts[2] / 3600.0
        if text.startswith("-"):
            value = -value
        return value * (15.0 if hours else 1.0)
    return float(text)


def parse_position(text, index=0):
    """`[NAME=]RA,DEC`: degrees, or sexagesimal (RA in hours,
    `hh:mm:ss.s`; Dec `dd:mm:ss.s`). Returns (name, ra_deg, dec_deg)."""
    name, sep, rest = text.partition("=")
    if not sep:
        name, rest = f"p{index}", text
    try:
        ra, dec = rest.split(",")
        ra_deg, dec_deg = _angle(ra, hours=":" in ra or "h" in ra), _angle(dec, False)
    except ValueError:
        raise LightcurveError(
            f"position {text!r}: [NAME=]RA,DEC in degrees or hh:mm:ss,dd:mm:ss"
        ) from None
    if not -90.0 <= dec_deg <= 90.0:
        raise LightcurveError(f"position {text!r}: Dec outside [-90, 90] degrees")
    return name.strip(), ra_deg % 360.0, dec_deg


def lm_from_radec(ra, dec, ra0, dec0):
    """Direction cosines (l east, m north) of (ra, dec) about (ra0, dec0) by
    the SIN projection, radians; refuses a position behind the sky plane."""
    da = ra - ra0
    cos_d, sin_d = math.cos(dec), math.sin(dec)
    east = cos_d * math.sin(da)
    north = sin_d * math.cos(dec0) - cos_d * math.sin(dec0) * math.cos(da)
    n = sin_d * math.sin(dec0) + cos_d * math.cos(dec0) * math.cos(da)
    if n <= 0.0:
        raise LightcurveError("position more than 90 degrees from the phase centre")
    return east, north


def _field_id(ms, field):
    with core_ms.open_table(Path(ms) / "FIELD") as t:
        names = [str(n) for n in t.getcol("NAME")]
    if isinstance(field, int) or str(field).isdigit():
        index = int(field)
        if not 0 <= index < len(names):
            raise LightcurveError(f"field {index} does not exist ({len(names)} fields)")
        return index, names[index]
    if field not in names:
        raise LightcurveError(f"field {field!r} not in the MS ({', '.join(names)})")
    return names.index(field), field


def _columns(ms, column, model_column):
    with core_ms.open_table(ms) as t:
        names = t.colnames()
    if column is None:
        column = "CORRECTED_DATA" if "CORRECTED_DATA" in names else "DATA"
    if column not in names:
        raise LightcurveError(f"column {column} not in the MS")
    if model_column is not None and model_column not in names:
        raise LightcurveError(
            f"column {model_column} not in the MS: run rang-core image with "
            "image.write_model: true first, or pass --no-model"
        )
    weight = "WEIGHT_SPECTRUM" if "WEIGHT_SPECTRUM" in names else "WEIGHT"
    return column, model_column, weight


def intervals(times, steps):
    """The distinct TIME values, sorted, in groups of `steps`: a list of
    arrays of TIME values (the last group may be shorter)."""
    if steps < 1:
        raise LightcurveError("interval steps must be at least one")
    unique = np.unique(times)
    return [unique[k : k + steps] for k in range(0, len(unique), steps)]


def _read(t, name, rows):
    return t.getcol_rows(name, rows)


def _residual(t, rows, column, model_column, weight_column, nchan):
    data = _read(t, column, rows)
    if model_column is not None:
        data = data - _read(t, model_column, rows)
    weights = _read(t, weight_column, rows)
    if weights.ndim == 2:  # WEIGHT: one value per correlation
        weights = np.broadcast_to(weights[:, None, :], data.shape)
    flags = _read(t, "FLAG", rows)
    vis, weight = core_weights.stokes_i(data, weights, flags)
    weight[_read(t, "FLAG_ROW", rows).astype(bool)] = 0.0
    uvw = np.ascontiguousarray(_read(t, "UVW", rows), np.float64)
    if vis.shape[1] != nchan:
        raise LightcurveError("data column and SPECTRAL_WINDOW disagree on channels")
    return uvw, vis, weight


def dft(uvw, freq, vis, weight, lm):
    """(flux per position, weight sum, samples) of one interval by the Rust
    kernel; flux is NaN where no sample has weight."""
    num, wsum, samples = core.extension().lightcurve_dft(
        np.ascontiguousarray(uvw, np.float64),
        np.ascontiguousarray(freq, np.float64),
        np.ascontiguousarray(vis, np.complex64),
        np.ascontiguousarray(weight, np.float32),
        np.ascontiguousarray(lm, np.float64).reshape(-1, 2),
    )
    flux = np.array(num) / wsum if wsum > 0 else np.full(len(num), np.nan)
    return flux, float(wsum), int(samples)


def snapshot(uvw, freq, vis, weight, size, scale_arcsec, epsilon=1e-6):
    """The interval's dirty image, `(size, size)` in WSClean's FITS pixel
    order, divided by the weight sum (natural weighting), float64."""
    wsum = float(np.sum(weight, dtype=np.float64))
    if wsum <= 0.0:
        return np.full((size, size), np.nan)
    pix = scale_arcsec * ARCSEC
    dirty = core_wgridder.vis2dirty(
        uvw=uvw,
        freq=freq,
        vis=np.ascontiguousarray(vis, np.complex128),
        wgt=np.ascontiguousarray(weight, np.float64),
        npix_x=size,
        npix_y=size,
        pixsize_x=pix,
        pixsize_y=pix,
        epsilon=epsilon,
        flip_v=True,
        flip_w=True,
    )
    return dirty.T / wsum


def pixel_of(east, north, size, scale_arcsec):
    """The nearest pixel (x, y) of the FITS array (0-based) to (l, m) =
    (east, north) and its offset in arcsec; None when outside the image."""
    step = scale_arcsec * ARCSEC
    fx, fy = size / 2 - east / step, size / 2 + north / step
    x, y = round(fx), round(fy)
    if not (0 <= x < size and 0 <= y < size):
        return None
    offset = math.hypot((x - fx) * scale_arcsec, (y - fy) * scale_arcsec)
    return x, y, offset


def robust_sigma(image):
    """1.4826 times the median absolute deviation from the median."""
    values = image[np.isfinite(image)]
    if not values.size:
        return float("nan")
    med = np.median(values)
    return float(MAD_TO_SIGMA * np.median(np.abs(values - med)))


def light_curves(
    ms,
    positions,
    field=0,
    column=None,
    model_column="MODEL_DATA",
    interval_steps=1,
    size=1024,
    scale_arcsec=4.0,
    images=True,
    epsilon=1e-6,
    on_snapshot=None,
    log=None,
):
    """Light curves of `positions` ((name, ra_deg, dec_deg) tuples) in the
    residual of `field` (id or name). `model_column=None` uses the data
    column alone. `on_snapshot(k, image, header)` receives each snapshot
    image (for FITS output). Returns a dict: settings, intervals, positions
    and per-interval arrays."""
    ms = Path(ms)
    started = time.perf_counter()
    if not positions:
        raise LightcurveError("at least one position is required")
    names = [p[0] for p in positions]
    if len(set(names)) != len(names):
        raise LightcurveError("position names must differ")
    field_id, field_name = _field_id(ms, field)
    column, model_column, weight_column = _columns(ms, column, model_column)
    freq, corr, centre = core_model.band(ms, field_id)
    if list(corr) != LINEAR:
        raise LightcurveError(
            f"CORR_TYPE {corr}: four linear correlations XX, XY, YX, YY required "
            "(MeerKAT)"
        )
    lm = np.array(
        [
            lm_from_radec(math.radians(ra), math.radians(dec), *centre)
            for _, ra, dec in positions
        ]
    )
    pixels = [pixel_of(x, y, size, scale_arcsec) for x, y in lm] if images else None
    rows = core_model.selected_rows(ms, field_id)
    if not len(rows):
        raise LightcurveError(f"no cross-correlation rows of field {field_name}")
    header = core_grid.wcs_header(centre, size, size, scale_arcsec, freq)
    out = {
        "schema": "rang.lightcurve",
        "version": 1,
        "ms": ms.as_posix(),
        "field": {"id": field_id, "name": field_name, "phase_dir_rad": list(centre)},
        "settings": {
            "column": column,
            "model_column": model_column,
            "weight_column": weight_column,
            "interval_steps": int(interval_steps),
            "images": bool(images),
            "size": int(size),
            "scale_arcsec": float(scale_arcsec),
            "epsilon": float(epsilon),
            "weighting": "natural",
            "polarization": "I",
        },
        "positions": [
            {
                "name": n,
                "ra_deg": ra,
                "dec_deg": dec,
                "l": float(lm[k, 0]),
                "m": float(lm[k, 1]),
                "pixel": None if not images or pixels[k] is None else pixels[k][:2],
                "pixel_offset_arcsec": None
                if not images or pixels[k] is None
                else pixels[k][2],
            }
            for k, (n, ra, dec) in enumerate(positions)
        ],
        "nchan": len(freq),
    }
    with core_ms.open_table(ms) as t:
        times = t.getcol_rows("TIME", rows)
        order = np.lexsort((rows, times))
        rows, times = rows[order], times[order]
        spans = intervals(times, int(interval_steps))
        out["intervals"] = len(spans)
        arrays = {
            key: []
            for key in (
                "time_mjd_s",
                "timesteps",
                "flux_jy",
                "flux_snapshot_jy",
                "sigma_meas_jy",
                "weight_sum",
                "samples",
                "rows",
            )
        }
        seconds = {"read": 0.0, "dft": 0.0, "image": 0.0}
        lo = 0
        for k, span in enumerate(spans):
            hi = int(np.searchsorted(times, span[-1], side="right"))
            sel = np.sort(rows[lo:hi])
            lo = hi
            t0 = time.perf_counter()
            uvw, vis, weight = _residual(
                t, sel, column, model_column, weight_column, len(freq)
            )
            t1 = time.perf_counter()
            flux, wsum, samples = dft(uvw, freq, vis, weight, lm)
            t2 = time.perf_counter()
            snap_flux = [None] * len(positions)
            sigma = None
            if images:
                image = snapshot(uvw, freq, vis, weight, size, scale_arcsec, epsilon)
                sigma = robust_sigma(image)
                snap_flux = [
                    None if p is None else float(image[p[1], p[0]]) for p in pixels
                ]
                if on_snapshot is not None:
                    on_snapshot(k, image, {**header, "DATE-OBS": _utc(span[0])})
            seconds["read"] += t1 - t0
            seconds["dft"] += t2 - t1
            seconds["image"] += time.perf_counter() - t2
            arrays["time_mjd_s"].append(float(np.mean(span)))
            arrays["timesteps"].append(len(span))
            arrays["flux_jy"].append([float(f) for f in flux])
            arrays["flux_snapshot_jy"].append(snap_flux)
            arrays["sigma_meas_jy"].append(sigma)
            arrays["weight_sum"].append(wsum)
            arrays["samples"].append(samples)
            arrays["rows"].append(len(sel))
            if log is not None and (k % 50 == 0 or k == len(spans) - 1):
                log(f"interval {k + 1}/{len(spans)}")
    out.update(arrays)
    out["seconds"] = {**seconds, "total": time.perf_counter() - started}
    return out


def _utc(mjd_s):
    from datetime import datetime, timedelta, timezone

    epoch = datetime(1858, 11, 17, tzinfo=timezone.utc)
    when = epoch + timedelta(seconds=float(mjd_s))
    return when.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]


def _cell(value):
    if value is None:
        return ""
    return repr(value) if isinstance(value, float) else value


def write_outputs(result, out_dir):
    """`lightcurve.json` and `lightcurve.csv` in `out_dir` (created)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "lightcurve.json").write_text(
        json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    with open(out_dir / "lightcurve.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for k in range(result["intervals"]):
            for s, pos in enumerate(result["positions"]):
                pixel = pos["pixel"] or (None, None)
                writer.writerow(
                    [
                        k,
                        repr(result["time_mjd_s"][k]),
                        result["timesteps"][k],
                        pos["name"],
                        repr(pos["ra_deg"]),
                        repr(pos["dec_deg"]),
                        repr(result["flux_jy"][k][s]),
                        _cell(result["flux_snapshot_jy"][k][s]),
                        _cell(result["sigma_meas_jy"][k]),
                        _cell(pixel[0]),
                        _cell(pixel[1]),
                        _cell(pos["pixel_offset_arcsec"]),
                        repr(result["weight_sum"][k]),
                        result["samples"][k],
                        result["rows"][k],
                    ]
                )
    return out_dir
