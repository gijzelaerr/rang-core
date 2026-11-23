# SPDX-License-Identifier: MIT
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

With `channels_out` M (task TS-P2, research/ts-p2.md), also a dynamic
spectrum per position: the same DFT over each of M equal groups of
contiguous channels (`rang._core.lightcurve_dft_grouped`; WSClean's
`-channels-out M` grouping, M must divide the channels), written to
`dynspec.csv`. A group with no weighted sample gives NaN (`null` in JSON).
The light curve itself does not change with M. Weights: the default
`weights="unit"` (TS-P3 and TS-P4, research/ts-p3.md, research/ts-p4.md)
weighs every correlation 1 in place of WEIGHT_SPECTRUM, flags still applied,
as gemclean's `-unit-weights`; `weights="ms"`, the default before TS-P4,
reads WEIGHT_SPECTRUM (else WEIGHT) and reproduces earlier outputs.

Stokes I and its weight follow WSClean's `-pol I` (`core_weights.stokes_i`):
`I = (XX + YY) / 2`, weight `min(4 w_XX, 4 w_YY)`, zero when a hand is
flagged; FLAG_ROW rows weigh zero. Rows: the field, data description 0,
cross-correlations (`core_model.selected_rows`); a field with rows on any
other data description is refused (one spectral window per MS: split it
first). Linear feeds with four correlations only (MeerKAT). The MS is only
read.

`lightcurve.json` is strict JSON: a value that is not a finite number (the
flux of an interval whose samples are all flagged, for one) is written as
`null`, never as a bare `NaN` or `Infinity`. `lightcurve.csv` leaves such a
cell as `nan`, as Python writes it.
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
    "channel_groups",
    "dft_grouped",
    "light_curves",
    "lm_from_radec",
    "parse_position",
    "write_outputs",
]

ARCSEC = math.pi / (180.0 * 3600.0)
LINEAR = [9, 10, 11, 12]
MAD_TO_SIGMA = 1.482602218505602
# --weights (research/ts-p3.md 1a): "unit", the default since TS-P4
# (research/ts-p4.md), weighs every correlation 1, flags still applied
# (gemclean's -unit-weights); "ms" reads WEIGHT_SPECTRUM (else WEIGHT), the
# earlier default.
WEIGHTS = ("ms", "unit")
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


def _one_data_description(ms, field_id, field_name):
    """B-16 (research/v030-review.md): the light curves image data
    description 0 only, so a field with rows on another one is refused
    rather than silently cut to its first window."""
    found = set()
    with core_ms.open_table(ms) as t:
        for start in range(0, t.nrows, core_model.SELECT_CHUNK):
            n = min(core_model.SELECT_CHUNK, t.nrows - start)
            ddid = t.getcol("DATA_DESC_ID", start, n)
            mine = ddid[t.getcol("FIELD_ID", start, n) == field_id]
            found.update(int(d) for d in np.unique(mine))
    if found - {0}:
        raise LightcurveError(
            f"field {field_name} has rows on data descriptions {sorted(found)}: "
            "lightcurve reads DATA_DESC_ID 0 only; split the MS to one spectral "
            "window first (for example CASA split with spw=...)"
        )


def _finite_or_null(value):
    """`value` with every float that is not finite replaced by None (B-13)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _finite_or_null(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite_or_null(v) for v in value]
    if isinstance(value, np.ndarray):
        return _finite_or_null(value.tolist())
    if isinstance(value, np.generic):
        return _finite_or_null(value.item())
    return value


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
    if weight_column is None:  # --weights unit: every correlation weighs 1
        weights = np.ones(data.shape, np.float32)
    else:
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


def channel_groups(freq, channels_out):
    """The groups of `channels_out` (M): a list of (first channel, last
    channel, mean frequency in Hz) of M equal contiguous groups; refuses
    when M does not divide the channels."""
    nchan = len(freq)
    m = int(channels_out)
    if m < 1 or nchan % m:
        raise LightcurveError(
            f"--channels-out {channels_out} must divide the {nchan} channels"
        )
    k = nchan // m
    return [(g * k, (g + 1) * k - 1, float(np.mean(freq[g * k : (g + 1) * k])))
            for g in range(m)]  # fmt: skip


def dft_grouped(uvw, freq, vis, weight, lm, groups):
    """(flux (position, group), weight sum per group, samples per group) of
    one interval by the Rust kernel; NaN where a group has no weight."""
    num, wsum, samples = core.extension().lightcurve_dft_grouped(
        np.ascontiguousarray(uvw, np.float64),
        np.ascontiguousarray(freq, np.float64),
        np.ascontiguousarray(vis, np.complex64),
        np.ascontiguousarray(weight, np.float32),
        np.ascontiguousarray(lm, np.float64).reshape(-1, 2),
        int(groups),
    )
    wsum = np.asarray(wsum, np.float64)
    num = np.asarray(num, np.float64).reshape(-1, int(groups))
    with np.errstate(invalid="ignore", divide="ignore"):
        flux = np.where(wsum > 0, num / np.where(wsum > 0, wsum, 1.0), np.nan)
    return flux, wsum, np.asarray(samples, np.int64)


def snapshot(
    uvw,
    freq,
    vis,
    weight,
    size,
    scale_arcsec,
    epsilon=1e-6,
    gridder="wgrid",
    device="cpu",
):
    """The interval's dirty image, `(size, size)` in WSClean's FITS pixel
    order, divided by the weight sum (natural weighting), float64.
    `gridder` "wgrid" is the exact wgridder (CPU); "wstack" is rang's
    w-stacking gridder (`core_grid.invert`: 64 w layers, padding 1.2) on
    `device` cpu or gpu (f64; research/ts-p1.md 13.3), normalised by its PSF
    centre."""
    wsum = float(np.sum(weight, dtype=np.float64))
    if wsum <= 0.0:
        return np.full((size, size), np.nan)
    if gridder == "wstack":
        out = core_grid.invert(
            uvw,
            freq,
            np.ascontiguousarray(vis, np.complex64),
            np.ascontiguousarray(weight, np.float32),
            np.ones(weight.shape, np.float32),
            width=size,
            height=size,
            scale_arcsec=scale_arcsec,
            gridder="wstack",
            device=device,
            precision="f64",
        )
        return np.asarray(out["dirty"], np.float64)
    if gridder != "wgrid":
        raise LightcurveError(f"gridder must be wgrid or wstack, not {gridder!r}")
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


def outside_grid(uvw, freq, weight, scale_arcsec):
    """Weighted samples with |u| or |v| at or beyond 1/(2 x scale)
    wavelengths: the edge of a snapshot grid of that pixel size (WSClean
    with -no-min-grid-resolution drops them; research/ts-p1.md, 9.1)."""
    limit = 1.0 / (2.0 * scale_arcsec * ARCSEC)
    lam = np.abs(uvw[:, :2, None]) * (np.asarray(freq)[None, None, :] / 299_792_458.0)
    beyond = (lam[:, 0] >= limit) | (lam[:, 1] >= limit)
    return int(np.count_nonzero(beyond & (weight > 0)))


def radec_from_pixel(x, y, size, scale_arcsec, ra0, dec0):
    """(RA, Dec) in degrees of FITS pixel (x, y), 0-based: the inverse SIN
    projection of l = -(x - size/2) scale, m = (y - size/2) scale."""
    step = scale_arcsec * ARCSEC
    east, north = -(x - size / 2) * step, (y - size / 2) * step
    n = math.sqrt(max(0.0, 1.0 - east * east - north * north))
    dec = math.asin(north * math.cos(dec0) + n * math.sin(dec0))
    ra = ra0 + math.atan2(east, n * math.cos(dec0) - north * math.sin(dec0))
    return math.degrees(ra) % 360.0, math.degrees(dec)


def local_peaks(image, threshold):
    """(y, x) of pixels >= `threshold` that are at least as large as all eight
    neighbours (edge pixels compare with the neighbours they have)."""
    padded = np.pad(image, 1, constant_values=-np.inf)
    centre = padded[1:-1, 1:-1]
    keep = centre >= threshold
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                keep &= centre >= padded[1 + dy : padded.shape[0] - 1 + dy,
                                         1 + dx : padded.shape[1] - 1 + dx]  # fmt: skip
    return np.argwhere(keep)


def candidates(image, sigma, threshold, k, when, size, scale_arcsec, centre):
    """Blind candidates of one snapshot (research/ts-p1.md 13.2): local maxima
    at or above `threshold` sigma, and of the negated image (sign -1, the
    null)."""
    out = []
    if not (sigma and np.isfinite(sigma) and sigma > 0):
        return out
    for sign in (1, -1):
        for y, x in local_peaks(sign * image, threshold * sigma):
            ra, dec = radec_from_pixel(x, y, size, scale_arcsec, *centre)
            flux = float(image[y, x])
            out.append(
                {
                    "interval": k,
                    "time_mjd_s": when,
                    "sign": sign,
                    "x": int(x),
                    "y": int(y),
                    "ra_deg": ra,
                    "dec_deg": dec,
                    "flux_jy": flux,
                    "snr": flux / sigma,
                }
            )
    return out


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
    gridder="wgrid",
    device="cpu",
    candidate_sigma=None,
    channels_out=None,
    weights="unit",
):
    """Light curves of `positions` ((name, ra_deg, dec_deg) tuples) in the
    residual of `field` (id or name). `model_column=None` uses the data
    column alone. `on_snapshot(k, image, header)` receives each snapshot
    image (for FITS output). `channels_out` M adds the dynamic spectrum
    (`dynspec_*` arrays and `dynspec_groups`; research/ts-p2.md). Returns a
    dict: settings, intervals, positions
    and per-interval arrays."""
    ms = Path(ms)
    started = time.perf_counter()
    if not positions:
        raise LightcurveError("at least one position is required")
    names = [p[0] for p in positions]
    if len(set(names)) != len(names):
        raise LightcurveError("position names must differ")
    field_id, field_name = _field_id(ms, field)
    _one_data_description(ms, field_id, field_name)
    column, model_column, weight_column = _columns(ms, column, model_column)
    if weights not in WEIGHTS:
        raise LightcurveError(f"weights must be one of {', '.join(WEIGHTS)}")
    if weights == "unit":
        weight_column = None
    freq, corr, centre = core_model.band(ms, field_id)
    groups = None if channels_out is None else channel_groups(freq, channels_out)
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
            "gridder": gridder,
            "device": device,
            "candidate_sigma": candidate_sigma,
            "channels_out": None if groups is None else len(groups),
            "weights": weights,
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
    if groups is not None:
        out["dynspec_groups"] = [
            {"group": g, "first_channel": a, "last_channel": b, "freq_hz": f}
            for g, (a, b, f) in enumerate(groups)
        ]
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
                "outside_grid",
            )
        }
        if groups is not None:
            arrays.update(
                {"dynspec_flux_jy": [], "dynspec_weight_sum": [], "dynspec_samples": []}
            )
        seconds = {"read": 0.0, "dft": 0.0, "image": 0.0}
        found = []
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
            if groups is not None:
                gflux, gw, gn = dft_grouped(uvw, freq, vis, weight, lm, len(groups))
                arrays["dynspec_flux_jy"].append(gflux.tolist())
                arrays["dynspec_weight_sum"].append(gw.tolist())
                arrays["dynspec_samples"].append(gn.tolist())
            t2 = time.perf_counter()
            snap_flux = [None] * len(positions)
            sigma = None
            if images:
                image = snapshot(
                    uvw, freq, vis, weight, size, scale_arcsec, epsilon, gridder, device
                )
                sigma = robust_sigma(image)
                if candidate_sigma is not None:
                    found.extend(
                        candidates(
                            image,
                            sigma,
                            candidate_sigma,
                            k,
                            float(np.mean(span)),
                            size,
                            scale_arcsec,
                            centre,
                        )
                    )
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
            arrays["outside_grid"].append(
                outside_grid(uvw, freq, weight, scale_arcsec) if images else None
            )
            if log is not None and (k % 50 == 0 or k == len(spans) - 1):
                log(f"interval {k + 1}/{len(spans)}")
    out.update(arrays)
    if candidate_sigma is not None:
        if not images:
            raise LightcurveError("candidates need the snapshots")
        out["candidates"] = found
    beyond = sum(n or 0 for n in arrays["outside_grid"])
    out["outside_grid_total"] = beyond if images else None
    if beyond and log is not None:
        log(
            f"warning: {beyond} weighted samples lie beyond 1/(2 x {scale_arcsec} "
            "arcsec) in u or v; the snapshots include them (aliased, exact at pixel "
            "centres), WSClean -no-min-grid-resolution drops them: use a smaller "
            "--scale to match WSClean"
        )
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
        json.dumps(_finite_or_null(result), indent=1, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if result.get("candidates") is not None:
        keys = ("interval", "time_mjd_s", "sign", "x", "y", "ra_deg", "dec_deg",
                "flux_jy", "snr")  # fmt: skip
        with open(out_dir / "candidates.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(keys)
            for c in result["candidates"]:
                writer.writerow([_cell(c[k]) for k in keys])
    if result.get("dynspec_groups") is not None:
        keys = ("interval", "time_mjd_s", "position", "group", "first_channel",
                "last_channel", "freq_hz", "flux_jy", "weight_sum", "samples")  # fmt: skip
        with open(out_dir / "dynspec.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(keys)
            for k in range(result["intervals"]):
                for s, pos in enumerate(result["positions"]):
                    for g in result["dynspec_groups"]:
                        j = g["group"]
                        writer.writerow(
                            [
                                k,
                                repr(result["time_mjd_s"][k]),
                                pos["name"],
                                j,
                                g["first_channel"],
                                g["last_channel"],
                                repr(g["freq_hz"]),
                                repr(float(result["dynspec_flux_jy"][k][s][j])),
                                repr(float(result["dynspec_weight_sum"][k][j])),
                                result["dynspec_samples"][k][j],
                            ]
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
