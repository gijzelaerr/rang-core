"""B1-1 (i): the SARAO/SKA Gaussian pointing-offset fit, ported and measured.

research/b1-beam-pointing.md freezes the method: the default path of the SKA
SDP pointing-offset pipeline (ska-sdp-wflow-pointing-offset commit 5ede554,
which follows SARAO's MeerKAT procedure) as its end-to-end test runs it on the
public fixture `outer_scans.zip` (a five-point reference-pointing
observation: scans 1, 4, 5, 8 at 1 deg throws and scan 9 on source):

    pointing-offset compute --use_source_offset_column --thresh_width=1.15
        --num_chunks=16

The functions below are a NumPy port of the code paths that command runs,
kept literal so that `reference_offsets.txt` is reproduced to 1e-6. Ported
from (all BSD-3-Clause; notices below):

- ska-sdp-wflow-pointing-offset (`read_data.py`, `array_data_func.py`,
  `beam_fitting.py`, `utils.py`), Copyright 2026 SKA Observatory;
- ska-sdp-func-python (`calibration/solvers.py`: `solve_gaintable` with
  `solve_antenna_gains_itsubs_nocrossdata` and the matrix gain
  substitution), Copyright SKA Observatory;
- ska-sdp-datamodels (`create_visibility_from_ms`,
  `create_gaintable_from_visibility`), Copyright SKA Observatory;
- scikits.fitting 0.7.2 (`GaussianFit`, `NonLinearLeastSquaresFit`),
  Copyright (c) 2007-2018 SKA South Africa.

> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions are
> met: 1. Redistributions of source code must retain the above copyright
> notice, this list of conditions and the following disclaimer. 2.
> Redistributions in binary form must reproduce the above copyright notice,
> this list of conditions and the following disclaimer in the documentation
> and/or other materials provided with the distribution. 3. Neither the name
> of the copyright holder nor the names of its contributors may be used to
> endorse or promote products derived from this software without specific
> prior written permission. THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT
> HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
> INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
> AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
> COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
> INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
> NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
> DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
> THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
> (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
> THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

The port and its integration are part of Rang (GPL-3.0-or-later).

Usage:
    python examples/b1_baselines.py --fixture outputs/ska-pointing/outer_scans.zip \
        --out outputs/b1-20261030-06-baseline [--beam outputs/b1-...-holography]
"""

import argparse
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
from scipy import optimize
from scipy.interpolate import interp1d

LIGHTSPEED = 299792458.0  # katpoint.lightspeed
BW_FACTOR = (0.976, 1.098)
THRESH_WIDTH = 1.15
NUM_CHUNKS = 16
SCANS = (1, 4, 5, 8, 9)
SCAN_NAME = "outer_scans/1672727931_sdp_l0_scan_{}.ms"
COLUMNS = (
    "xel_offset",
    "xel_offset_std",
    "el_offset",
    "el_offset_std",
    "expected_width_h",
    "expected_width_v",
    "fitted_width_h",
    "fitted_width_h_std",
    "fitted_width_v",
    "fitted_width_v_std",
    "fitted_height",
    "fitted_height_std",
)


# --------------------------------------------------------------------------
# Reading (ska-sdp-datamodels create_visibility_from_ms; pipeline read_data)


def read_scan(ms_path):
    """One scan as the pipeline sees it: per-time baseline arrays.

    Returns dict with times (T,) (TIME - INTERVAL / 2, as datamodels 1.1.0), baselines [(a1, a2)] with a1 <= a2
    (autocorrelations included), vis (T, B, F, 4), flags (T, B, F, 4) int,
    weight (T, B, F, 4) from the per-row WEIGHT broadcast over channels,
    frequency (F,), antenna count, SOURCE_OFFSET (nants, ntimes, 2) in
    degrees and pointing TIME (ntimes,) of one antenna."""
    from rang import core_ms

    main = core_ms.open_table(ms_path)
    interval = main.getcol("INTERVAL")
    # ska-sdp-datamodels 1.1.0, the version the pipeline pins (its
    # pyproject: "1.1.1 introduces a change that changes the output"),
    # stamps each integration at TIME - INTERVAL / 2.
    time_col = main.getcol("TIME") - interval / 2.0
    a1 = main.getcol("ANTENNA1")
    a2 = main.getcol("ANTENNA2")
    data = main.getcol("DATA")
    flag = main.getcol("FLAG")
    weight = main.getcol("WEIGHT")
    spw = main.subtable("SPECTRAL_WINDOW")
    frequency = np.asarray(spw.getcol("CHAN_FREQ"))[0]
    nants = main.subtable("ANTENNA").nrows
    pointing = main.subtable("POINTING")
    source_offset = np.squeeze(pointing.getcol("SOURCE_OFFSET"))
    pointing_time = pointing.getcol("TIME")
    if np.any(a1 > a2):
        raise ValueError("fixture rows are expected with ANTENNA1 <= ANTENNA2")
    # Time index as create_visibility_from_ms assigns it.
    index = np.zeros(len(time_col), int)
    last, k = time_col[0], 0
    for row in range(len(time_col)):
        if time_col[row] > last + 0.5 * interval[row]:
            if not time_col[row] > last:
                raise ValueError("MS is not time-sorted")
            k += 1
            last = time_col[row]
        index[row] = k
    ntimes = k + 1
    baselines = [(i, j) for i in range(nants) for j in range(i, nants)]
    position = {b: n for n, b in enumerate(baselines)}
    nchan, npol = data.shape[1], data.shape[2]
    vis = np.zeros((ntimes, len(baselines), nchan, npol), complex)
    flags = np.zeros((ntimes, len(baselines), nchan, npol), int)
    weights = np.zeros((ntimes, len(baselines), nchan, npol))
    times = np.zeros(ntimes)
    for row in range(len(time_col)):
        t, b = index[row], position[(int(a1[row]), int(a2[row]))]
        times[t] = time_col[row]
        vis[t, b] = data[row]
        flags[t, b][flag[row].astype(bool)] = 1
        weights[t, b] = weight[row][np.newaxis, :]
    if pointing.nrows % nants:
        raise ValueError("POINTING rows are not antenna x time")
    per_antenna = pointing.nrows // nants
    pointing_time = pointing_time.reshape(nants, per_antenna)[0]
    source_offset = np.degrees(source_offset.reshape(nants, per_antenna, 2))
    return {
        "times": times,
        "baselines": baselines,
        "vis": vis,
        "flags": flags,
        "weight": weights,
        "frequency": frequency,
        "nants": nants,
        "source_offset_deg": source_offset,
        "pointing_time": pointing_time,
    }


def split_chunks(n, num_chunks=NUM_CHUNKS):
    """Channel index chunks of `utils.split_array_into_chunks`: equal split,
    first and last chunk dropped when num_chunks > 1."""
    channels = np.arange(n)
    if n % num_chunks:
        chunks = np.array_split(channels, num_chunks)
    else:
        chunks = list(channels.reshape(num_chunks, -1))
    return chunks[1 : num_chunks - 1] if num_chunks > 1 else chunks


def on_sky_offsets(scan):
    """Time mean of SOURCE_OFFSET after zero-order hold to the vis times
    (`interp_timestamps`, then `ExtractPerScan.__init__`): (nants, 2) deg."""
    origin_times = scan["pointing_time"]
    order = np.argsort(origin_times)
    data = scan["source_offset_deg"][:, order]
    origin_times = origin_times[order]
    out = np.zeros((data.shape[0], len(scan["times"]), 2))
    for i in range(data.shape[0]):
        for c in range(2):
            out[i, :, c] = interp1d(
                origin_times, data[i, :, c], kind="zero", fill_value="extrapolate"
            )(scan["times"])
    return out.mean(axis=1)


# --------------------------------------------------------------------------
# Gain solve (ska-sdp-func-python gain substitution, cross hands zeroed)


def _gain_substitution_matrix(gain, x, xwt):
    nants, nchan, nrec, _ = gain.shape
    x = x.reshape([nants, nants, nchan, nrec, nrec])
    diag = np.ones_like(x)
    xwt = xwt.reshape([nants, nants, nchan, nrec, nrec])
    gain_conj = np.conjugate(gain)
    for ant in range(nants):
        diag[ant, ant, ...] = 0
    n_top1 = np.einsum("ij...->j...", xwt * diag * x * gain[:, None, ...])
    n_bot = diag * xwt * gain_conj * gain
    n_bot1 = np.einsum("ij...->i...", n_bot)
    n_top2 = n_top1.copy()
    np.putmask(n_top2, n_bot1[...] <= 0, 0.0)
    n_bot2 = n_bot1.copy()
    np.putmask(n_bot2, n_bot1[...] <= 0, 1.0)
    return n_top2 / n_bot2, n_bot1.real


def solve_matrix(gain, x, xwt, niter=200, tol=1e-6, refant=0):
    """`solve_antenna_gains_itsubs_matrix` with phase_only=False."""
    nants, _, nchan, _ = x.shape
    x = x.reshape((nants, nants, nchan, 2, 2))
    xwt = xwt.reshape((nants, nants, nchan, 2, 2))
    i_diag = np.diag_indices(nants, nants)
    x[i_diag[0], i_diag[1], ...] = 0.0
    xwt[i_diag[0], i_diag[1], ...] = 0.0
    i_lower = np.tril_indices(nants, -1)
    i_upper = (i_lower[1], i_lower[0])
    x[i_upper] = np.conjugate(x[i_lower])
    xwt[i_upper] = xwt[i_lower]
    gain[..., 0, 1] = 0.0
    gain[..., 1, 0] = 0.0
    gainmask = np.abs(np.einsum("ij...->j...", x * xwt)) <= 0.0
    cross_mask = gainmask.copy()
    cross_mask[..., 0, 0] = False
    cross_mask[..., 1, 1] = False
    # Upstream `_determine_refant` picks a replacement when the reference
    # antenna is fully masked but never returns it, so refant stays 0; a
    # masked reference antenna then gets zero phase rotation and gain 1.
    np.putmask(gain, gainmask, 0.0)
    gwt = None
    for _ in range(niter):
        last = gain
        gain, gwt = _gain_substitution_matrix(gain, x, xwt)
        change = np.max(np.abs(gain - last))
        gain = 0.5 * (gain + last)
        if change < tol:
            break
    angles = np.angle(gain)
    gain = gain * np.exp(-1j * angles)[refant, ...]
    np.putmask(gain, gainmask, 1.0)
    np.putmask(gain, cross_mask, 0.0)
    return gain, gwt


def solve_gains(scan, channels):
    """G gains per integration for one channel chunk (unit point model,
    `solve_gaintable(..., crosspol=False, jones_type="G")`): returns
    gain (T, nants, 1, 2, 2) and weight (T, nants, 1, 2, 2)."""
    nants = scan["nants"]
    vis = scan["vis"][:, :, channels]
    weight = scan["weight"][:, :, channels]
    flags = scan["flags"][:, :, channels]
    ntimes = vis.shape[0]
    gains = np.zeros((ntimes, nants, 1, 2, 2), complex)
    weights = np.zeros((ntimes, nants, 1, 2, 2))
    for t in range(ntimes):
        x_b = np.sum((vis[t] * weight[t]) * (1 - flags[t]), axis=1)[:, None, :]
        xwt_b = np.sum(weight[t] * (1 - flags[t]), axis=1)[:, None, :]
        x = np.zeros([nants, nants, 1, 4], dtype="complex")
        xwt = np.zeros([nants, nants, 1, 4])
        for b, (a1, a2) in enumerate(scan["baselines"]):
            x[a1, a2, ...] = np.conjugate(x_b[b, ...])
            xwt[a1, a2, ...] = xwt_b[b, ...]
            x[a2, a1, ...] = x_b[b, ...]
            xwt[a2, a1, ...] = xwt_b[b, ...]
        mask = np.abs(xwt) > 0.0
        if not np.sum(mask) > 0:
            gains[t] = np.eye(2)
            continue
        x[mask] = x[mask] / xwt[mask]
        x[~mask] = 0.0
        xwt[mask] = xwt[mask] / np.max(xwt[mask])
        xwt[~mask] = 0.0
        x[..., 1] = 0.0
        x[..., 2] = 0.0
        xwt[..., 1] = 0.0
        xwt[..., 2] = 0.0
        start = np.zeros((nants, 1, 2, 2), complex)
        start[..., 0, 0] = start[..., 1, 1] = 1.0
        gains[t], weights[t] = solve_matrix(start, x, xwt)
    return gains, weights


def weighted_avg_and_std(data, axis, weights, std_error=False):
    """`utils.weighted_avg_and_std`, literal."""
    weights = np.ma.fix_invalid(weights)
    average, sumwt = np.ma.average(data, axis=axis, weights=weights, returned=True)
    mean_subtracted = data - np.expand_dims(average, axis=axis)
    sumsqwt = (weights**2).sum(axis=axis)
    unbiased_variance = (mean_subtracted**2 * weights).sum(axis=axis) / (
        sumwt - (sumsqwt / sumwt)
    )
    if not std_error:
        return average, np.sqrt(unbiased_variance)
    return average, np.sqrt(unbiased_variance * sumsqwt) / sumwt


def gain_amplitudes(scans, sep_pol=False):
    """`ExtractPerScan.from_gains`: y and std per (antenna, chunk, scan), or
    per (hand, antenna, chunk, scan) with sep_pol; chunk frequencies (Hz)."""
    nscans, nants = len(scans), scans[0]["nants"]
    chunks = split_chunks(len(scans[0]["frequency"]))
    shape = ((2,) if sep_pol else ()) + (nants, len(chunks), nscans)
    y, std = np.zeros(shape), np.zeros(shape)
    frequency = np.array([np.mean(scans[0]["frequency"][c]) for c in chunks])
    for s, scan in enumerate(scans):
        for i, channels in enumerate(chunks):
            gain, weight = solve_gains(scan, channels)
            amp = np.dstack((np.abs(gain[:, :, :, 0, 0]), np.abs(gain[:, :, :, 1, 1])))
            wt = np.dstack((weight[:, :, :, 0, 0], weight[:, :, :, 1, 1]))
            mean, sd = weighted_avg_and_std(
                amp, axis=0 if sep_pol else (0, 2), weights=wt
            )
            if sep_pol:
                y[:, :, i, s] = np.asarray(mean).T
                std[:, :, i, s] = np.asarray(sd).T
            else:
                y[:, i, s] = mean
                std[:, i, s] = sd
    return y, std, frequency


# --------------------------------------------------------------------------
# Gaussian fit (scikits.fitting GaussianFit; pipeline BeamPatternFit)


def _gauss(p, x):
    d = x.shape[0]
    var = p[d + 1 :] ** 2
    diff = x - p[:d, np.newaxis]
    return p[d] * np.exp(-0.5 * np.dot(1 / var, diff * diff))


def _gauss_jacobian(p, x):
    d = x.shape[0]
    mu = p[:d, np.newaxis]
    sigma = p[d + 1 :, np.newaxis]
    norm_x = (x - mu) / sigma
    dy_dheight = np.exp(-0.5 * (norm_x * norm_x).sum(axis=0))
    y = p[d] * dy_dheight
    dy_dmean = y * norm_x / sigma
    dy_dstd = dy_dmean * norm_x
    return np.vstack((dy_dmean, dy_dheight, dy_dstd))


FWHM_PER_SIGMA = 2.0 * np.sqrt(2.0 * np.log(2.0))


def beam_pattern_fit(x, y, std_y, expected_width, thresh_width=THRESH_WIDTH):
    """BeamPatternFit(centre=(0, 0), width=expected_width, height=1).fit:
    returns centre, std_centre, width, std_width, height, std_height, valid.
    Widths are FWHM in the units of x (degrees)."""
    expected_width = np.atleast_1d(np.asarray(expected_width, float))
    initial = np.r_[0.0, 0.0, 1.0, expected_width / FWHM_PER_SIGMA]

    def residuals(p):
        return ((y - _gauss(p, x)) / std_y).ravel()

    def jacobian(p):
        return (-_gauss_jacobian(p, x) / std_y).T

    # A fully flagged reference antenna gets gain 1 in every integration, so
    # its sigma_y is 0 and the residuals divide by zero, exactly as upstream
    # (the fit is then invalid and dropped); silence only that warning.
    with np.errstate(divide="ignore", invalid="ignore"):
        p, cov, info, _, _ = optimize.leastsq(
            residuals, initial.copy(), Dfun=jacobian, full_output=1
        )
    if cov is None:
        ipvt, fjac = info["ipvt"], info["fjac"]
        perm = np.take(np.eye(len(ipvt)), ipvt - 1, 0)
        r = np.dot(np.triu(fjac.T[: len(ipvt), :]), perm)
        cov = np.linalg.pinv(np.dot(r.T, r), 1e-15)
        max_var = np.diag(cov).max()
        bad = np.diag(cov) <= 1e-15 * max_var
        cov[bad, bad] = max_var / 1e-15 if max_var > 0 else 1e100
    sd = np.sqrt(np.diag(cov))
    centre, height = p[:2], p[2]
    sigma = np.abs(p[3:])
    width = FWHM_PER_SIGMA * sigma
    std_width = FWHM_PER_SIGMA * sd[3:]
    valid = not any(np.isnan(centre)) and height > 0.0
    fit_snr = sigma / sd[3:]
    norm_width = width / expected_width
    # Upstream writes `all(fit_snr) > 0.0`, which tests that no SNR is zero.
    valid = bool(
        valid
        and all(norm_width > 0.9)
        and all(norm_width < thresh_width)
        and all(fit_snr) > 0.0
    )
    return {
        "centre": centre,
        "std_centre": sd[:2],
        "width": width,
        "std_width": std_width,
        "height": height,
        "std_height": sd[2],
        "expected_width": expected_width,
        "valid": valid,
    }


def expected_voltage_width(frequency_hz, diameter=13.5, bw_factor=BW_FACTOR):
    """`fit_to_gains`: sqrt(2) * k lambda / D in degrees, (x, y)."""
    return np.sqrt(2) * np.degrees(
        np.array(bw_factor) * (LIGHTSPEED / frequency_hz) / diameter
    )


def fit_offsets(x_per_scan, y, std, frequency, diameter=13.5):
    """`SolveForOffsets.fit_to_gains` then `fitted_offsets_weighted_average`.

    x_per_scan (nscans, nants, 2) deg; y, std (nants, nchunks, nscans).
    Returns (per-antenna 12-column array in radians/heights, chunk fits)."""
    nants = y.shape[0]
    rows, fits = np.zeros((nants, 12)), []
    for a in range(nants):
        beams = [
            beam_pattern_fit(
                x_per_scan[:, a].T,
                y[a, c],
                std[a, c],
                expected_voltage_width(f, diameter),
            )
            for c, f in enumerate(frequency)
        ]
        fits.append(beams)
        good = [b for b in beams if b["valid"]]
        if not good:
            rows[a] = np.nan
            continue
        offs = np.array([b["centre"] for b in good])
        offs_sd = np.array([b["std_centre"] for b in good])
        width = np.array([b["width"] for b in good])
        width_sd = np.array([b["std_width"] for b in good])
        height = np.array([b["height"] for b in good])
        height_sd = np.array([b["std_height"] for b in good])
        expected = np.array([b["expected_width"] for b in good]).mean(axis=0)
        if len(good) > 1:
            off, off_e = weighted_avg_and_std(offs, 0, 1.0 / offs_sd**2, True)
            wid, wid_e = weighted_avg_and_std(width, 0, 1.0 / width_sd**2, True)
            hei, hei_e = weighted_avg_and_std(height, 0, 1.0 / height_sd**2, True)
        else:
            off, off_e = offs[0], offs_sd[0]
            wid, wid_e = width[0], width_sd[0]
            hei, hei_e = height[0], height_sd[0]
        off, off_e, wid, wid_e = (
            np.asarray(v, float) for v in (off, off_e, wid, wid_e)
        )
        rows[a] = np.radians(
            [
                off[0],
                off_e[0],
                off[1],
                off_e[1],
                expected[0],
                expected[1],
                wid[0],
                wid_e[0],
                wid[1],
                wid_e[1],
                0.0,
                0.0,
            ]
        )
        rows[a, 10], rows[a, 11] = float(hei), float(hei_e)
    return rows, fits


def load_fixture(fixture, workdir):
    """Extract (once) and read the five scans in the pipeline's glob order."""
    fixture = Path(fixture)
    root = Path(workdir)
    if fixture.is_dir():
        root = fixture.parent if fixture.name == "outer_scans" else fixture
    else:
        if not (root / "outer_scans" / "reference_offsets.txt").exists():
            with zipfile.ZipFile(fixture) as archive:
                archive.extractall(root)
    paths = sorted(str(root / SCAN_NAME.format(s)) for s in SCANS)
    scans = [read_scan(p) for p in paths]
    reference = np.loadtxt(
        root / "outer_scans" / "reference_offsets.txt", delimiter=",", dtype=object
    )
    return scans, reference, root


def run_baseline(scans, sep_pol=False):
    x_per_scan = np.array([on_sky_offsets(s) for s in scans])
    y, std, frequency = gain_amplitudes(scans, sep_pol=sep_pol)
    if not sep_pol:
        rows, fits = fit_offsets(x_per_scan, y, std, frequency)
        return {
            "rows": rows,
            "fits": fits,
            "x": x_per_scan,
            "y": y,
            "std": std,
            "frequency": frequency,
        }
    hands = [fit_offsets(x_per_scan, y[h], std[h], frequency) for h in range(2)]
    return {
        "hands": [h[0] for h in hands],
        "x": x_per_scan,
        "y": y,
        "std": std,
        "frequency": frequency,
    }


# --------------------------------------------------------------------------
# G1b: the baseline's bias against simulated truth with the frozen beam


def simulate_g1b(
    beam, antennas, x_per_scan, std, frequency, injections_arcmin, seeds, height=3.0
):
    """Gain amplitudes from the frozen holography beam at the fixture's
    pointings, with the beam centre placed at `injection` (arcmin) in the
    commanded (xel, el) frame: amplitude(c) = height * mean(|E_HH|, |E_VV|)
    at beam coordinate c - injection. Fitted with steps 6-7 unchanged.
    Returns recovered-minus-injected offsets (arcmin) and formal sigma."""
    nants, nchunks = len(antennas), len(frequency)
    out = []
    for inj in injections_arcmin:
        inj_deg = np.asarray(inj, float) / 60.0
        clean = np.zeros((nants, nchunks, x_per_scan.shape[0]))
        for k, ant in enumerate(antennas):
            pos = x_per_scan[:, k] - inj_deg
            for c, f in enumerate(frequency):
                jones = beam.jones(ant, pos[:, 0], pos[:, 1], f)
                clean[k, c] = (
                    height * 0.5 * (np.abs(jones[:, 0, 0]) + np.abs(jones[:, 1, 1]))
                )
        noiseless, _ = fit_offsets(x_per_scan, clean, std, frequency)
        record = {
            "injected_arcmin": list(map(float, inj)),
            "noiseless_error_arcmin": (
                np.degrees(noiseless[:, [0, 2]]) * 60 - np.asarray(inj)
            ).tolist(),
        }
        errors, sigmas = [], []
        for seed in seeds:
            rng = np.random.default_rng(seed)
            noisy = clean + rng.normal(size=clean.shape) * std
            rows, _ = fit_offsets(x_per_scan, noisy, std, frequency)
            errors.append(np.degrees(rows[:, [0, 2]]) * 60 - np.asarray(inj))
            sigmas.append(np.degrees(rows[:, [1, 3]]) * 60)
        errors, sigmas = np.array(errors), np.array(sigmas)
        ok = np.isfinite(errors)
        record.update(
            seeds=len(seeds),
            valid_fraction=float(ok.mean()),
            mean_error_arcmin=np.nanmean(errors, axis=0).tolist(),
            rms_error_arcmin=np.sqrt(np.nanmean(errors**2, axis=0)).tolist(),
            median_formal_sigma_arcmin=np.nanmedian(sigmas, axis=0).tolist(),
            coverage_1sigma=float(np.mean(np.abs(errors[ok]) <= sigmas[ok])),
        )
        out.append(record)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", default="outputs/ska-pointing/outer_scans.zip")
    parser.add_argument("--out", required=True)
    parser.add_argument("--beam", help="B1-0 product dir for G1b")
    parser.add_argument("--seeds", type=int, default=200)
    parser.add_argument("--flip", type=int, default=1)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    timings, result = (
        {},
        {
            "protocol": "research/b1-beam-pointing.md",
            "settings": {
                "bw_factor": BW_FACTOR,
                "thresh_width": THRESH_WIDTH,
                "num_chunks": NUM_CHUNKS,
                "offsets": "SOURCE_OFFSET",
                "fit": "gain amplitudes, Stokes I (XX, YY averaged)",
            },
        },
    )
    started = time.perf_counter()
    scans, reference, root = load_fixture(args.fixture, out / "fixture")
    timings["read_s"] = time.perf_counter() - started
    started = time.perf_counter()
    base = run_baseline(scans)
    timings["baseline_s"] = time.perf_counter() - started
    ref = reference[:, 1:].astype(float)
    names = [str(n) for n in reference[:, 0]]
    diff = base["rows"] - ref
    result["g1a"] = {
        "max_abs_diff": float(np.max(np.abs(diff))),
        "max_abs_diff_per_column": dict(
            zip(COLUMNS, np.max(np.abs(diff), axis=0).tolist())
        ),
        "pass": bool(np.all(np.abs(diff) < 1.5e-6)),
        "criterion": "all 12 columns to decimal=6 (|diff| < 1.5e-6), as upstream",
    }
    result["antennas"] = names
    result["rows"] = base["rows"].tolist()
    result["columns"] = list(COLUMNS)
    arcmin = np.degrees(base["rows"][:, [0, 1, 2, 3]]) * 60
    centres = np.array([[b["centre"] for b in fits] for fits in base["fits"]]) * 60
    valid = np.array([[b["valid"] for b in fits] for fits in base["fits"]])
    sd_centres = (
        np.array([[b["std_centre"] for b in fits] for fits in base["fits"]]) * 60
    )
    scatter = []
    for a in range(len(names)):
        v = valid[a]
        if v.sum() > 1:
            _, s = weighted_avg_and_std(
                centres[a, v], 0, 1.0 / sd_centres[a, v] ** 2, False
            )
            scatter.append(np.asarray(s).tolist())
        else:
            scatter.append([np.nan, np.nan])
    result["estimate_arcmin"] = {
        n: {
            "xel": arcmin[a, 0],
            "xel_formal_sigma": arcmin[a, 1],
            "el": arcmin[a, 2],
            "el_formal_sigma": arcmin[a, 3],
            "valid_chunks": int(valid[a].sum()),
            "chunk_scatter_xel_el": scatter[a],
        }
        for a, n in enumerate(names)
    }
    result["chunk_frequency_hz"] = base["frequency"].tolist()
    result["chunk_centres_arcmin"] = centres.tolist()
    result["chunk_valid"] = valid.tolist()
    result["amplitudes"] = {
        "y": base["y"].tolist(),
        "std": base["std"].tolist(),
        "x_deg": base["x"].tolist(),
    }
    started = time.perf_counter()
    sep = run_baseline(scans, sep_pol=True)
    timings["sep_pol_s"] = time.perf_counter() - started
    result["sep_pol_arcmin"] = {
        hand: {
            n: [float(v) for v in np.degrees(rows[a, [0, 1, 2, 3]]) * 60]
            for a, n in enumerate(names)
        }
        for hand, rows in zip(("H", "V"), sep["hands"])
    }
    reformatted = np.loadtxt(
        root / "outer_scans" / "reformatted_offsets.txt", delimiter=",", dtype=object
    )
    result["reformatted_offsets_arcmin"] = {
        str(r[0]): [float(v) for v in np.degrees(r[1:5].astype(float)) * 60]
        for r in reformatted
    }
    if args.beam:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
        from rang.beam_holography import HolographyBeam

        beam = HolographyBeam(args.beam, flip=args.flip)
        injections = (
            [(0, 0)]
            + [(s * v, 0) for v in (0.5, 1, 2) for s in (1, -1)]
            + [(0, s * v) for v in (0.5, 1, 2) for s in (1, -1)]
        )
        started = time.perf_counter()
        result["g1b"] = {
            "beam": "frozen B1-0 product, co-polar |HH|, |VV| of m000-m003",
            "fixture_std": "per-point sigma_y of the real fixture",
            "cases": simulate_g1b(
                beam,
                [0, 1, 2, 3],
                base["x"],
                base["std"],
                base["frequency"],
                injections,
                range(1, args.seeds + 1),
            ),
        }
        timings["g1b_s"] = time.perf_counter() - started
    result["timings"] = timings
    (out / "b1-baselines.json").write_text(json.dumps(result, indent=1, default=float))
    print(
        json.dumps(
            {
                "g1a": result["g1a"],
                "estimate_arcmin": result["estimate_arcmin"],
                "timings": timings,
            },
            indent=1,
            default=float,
        )
    )
    return result


if __name__ == "__main__":
    main()
