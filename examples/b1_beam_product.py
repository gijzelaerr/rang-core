"""B1-0: gates G0a-G0c on the holography beam product, and the comparison
with katbeam and EIDOS (research/b1-beam-pointing.md).

The product is fetched once by `rang.beam_holography.fetch_product`
(about 3.7 GB by HTTP range from the 35 GB SARAO npz) into an `outputs/`
directory; this script only reads it. Writes the compact archive
`research/results/b1-beam-product.json` (or `--json`).

Usage:
    python examples/b1_beam_product.py --product outputs/b1-20261030-05-holography \
        --metrics outputs/b1-20261030-01/MeerKAT_L_band_primary_beam_metrics.npz \
        --lsm outputs/l1m-20261030-00-fieldmodel/pks1934-638.lsm --json out.json
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from rang import beam_holography as bh
from scipy import ndimage

LSM_SHA256 = "0964b9f4c547bb802bfb16a2e8fdccddff84beeec05b6f3492521a46fa77d101"
MOON_RADII_ARCMIN = (44.0, 98.0, 149.0)
POINTING_ARCSEC = 30.0


def native_xy(beam):
    margin = beam.margin_deg
    y, x = np.meshgrid(beam.flip * margin, margin, indexing="ij")
    return x, y


def power_from_maps(maps):
    """I_b of (4, ny, nx) Jones maps (HH, HV, VH, VV), normalised to the
    origin pixel."""
    power = 0.5 * np.sum(np.abs(np.asarray(maps)) ** 2, axis=0)
    return power / power[bh.CENTRE_INDEX, bh.CENTRE_INDEX]


# --------------------------------------------------------------------------
# G0a


WIDTH_DEFINITIONS = {
    "power FWHM, arcmin": 60.0,
    "power HWHM, arcmin": 30.0,
    "power FWHM, deg": 1.0,
    "power sigma, arcmin": 60.0 / (2 * np.sqrt(2 * np.log(2))),
}


def g0a(beam, metrics, channels):
    """Main-lobe fits on the native grid against the metrics file."""
    x, y = native_xy(beam)
    targets = [("array_average", bh.ARRAY_AVERAGE)] + [(a, a) for a in range(4)]
    rows = []
    for name, index in targets:
        for ch in channels:
            if name == "array_average":
                maps = np.asarray(beam.average[:, ch])
            else:
                k = list(beam.product_channels).index(ch)
                maps = np.asarray(
                    beam.sampled[:, beam.sampled_antennas.index(index), k]
                )
            centre = maps[:, bh.CENTRE_INDEX, bh.CENTRE_INDEX]
            for label, power in (
                ("H", np.abs(maps[0]) ** 2),
                ("V", np.abs(maps[3]) ** 2),
                ("I", 0.5 * np.sum(np.abs(maps) ** 2, axis=0)),
            ):
                fit = bh.fit_main_lobe(power, x, y)
                rows.append(
                    {
                        "antenna": name,
                        "channel": int(ch),
                        "beam": label,
                        "fit_x0_arcmin": 60 * fit["x0_deg"],
                        "fit_y0_arcmin": 60 * fit["y0_deg"],
                        "fit_fwhm_major_deg": fit["fwhm_major_deg"],
                        "fit_fwhm_minor_deg": fit["fwhm_minor_deg"],
                        "metric_x0": float(metrics[label + "x0"][index, ch]),
                        "metric_y0": float(metrics[label + "y0"][index, ch]),
                        "metric_major": float(metrics[label + "major"][index, ch]),
                        "metric_minor": float(metrics[label + "minor"][index, ch]),
                        "centre_abs": np.abs(centre).tolist(),
                    }
                )
    fx = np.array([r["fit_x0_arcmin"] for r in rows])
    fy = np.array([r["fit_y0_arcmin"] for r in rows])
    mx = np.array([r["metric_x0"] for r in rows])
    my = np.array([r["metric_y0"] for r in rows])
    fmaj = np.array([r["fit_fwhm_major_deg"] for r in rows])
    fmin = np.array([r["fit_fwhm_minor_deg"] for r in rows])
    mmaj = np.array([r["metric_major"] for r in rows])
    mmin = np.array([r["metric_minor"] for r in rows])
    width_errors = {
        name: float(
            np.median(np.abs(np.r_[fmaj * scale / mmaj, fmin * scale / mmin] - 1))
        )
        for name, scale in WIDTH_DEFINITIONS.items()
    }
    best = min(width_errors, key=width_errors.get)
    centroid = np.hypot(fx - mx, fy - my)
    centroid_flipped = np.hypot(fx - mx, -fy - my)
    significant = np.abs(my) > 0.2
    result = {
        "fits": len(rows),
        "median_centroid_error_arcmin": float(np.median(centroid)),
        "median_centroid_error_arcmin_if_flipped": float(np.median(centroid_flipped)),
        "y_sign_agreement_where_metric_abs_gt_0p2": float(
            np.mean(np.sign(fy[significant]) == np.sign(my[significant]))
        ),
        "width_definition_errors": width_errors,
        "width_definition": best,
        "median_width_relative_error": width_errors[best],
        "centre_pixel_abs_median": np.median(
            np.array([r["centre_abs"] for r in rows]), axis=0
        ).tolist(),
    }
    result["pass"] = bool(
        result["median_centroid_error_arcmin"] <= 0.2
        and result["median_width_relative_error"] <= 0.01
    )
    return result, rows


def katbeam_squint_sign(beam, metrics, channels):
    """katbeam's tabulated V elevation squint against the metrics' Vy0
    (array average) at the product channels in the katbeam band."""
    from katbeam import JimBeam

    model = JimBeam("MKAT-AA-L-JIM-2020")
    f = beam.freq_hz[channels] / 1e6
    kat = np.interp(f, model.freqMHzlist, model.squintlist[3]) * 60
    holo = metrics["Vy0"][bh.ARRAY_AVERAGE, channels]
    big = (np.abs(kat) > 0.2) & (np.abs(holo) > 0.2)
    return {
        "channels_compared": int(big.sum()),
        "sign_agreement": float(np.mean(np.sign(kat[big]) == np.sign(holo[big]))),
        "katbeam_vy_arcmin_median": float(np.median(kat)),
        "holography_vy0_arcmin_median": float(np.median(holo)),
    }


# --------------------------------------------------------------------------
# G0b, G0c


def g0b(beam, band_channels):
    """Linear-in-frequency prediction of held-out native channels of the
    array average from the product channels."""
    x, y = native_xy(beam)
    product = np.asarray(beam.product_channels)
    errors = []
    for ch in band_channels:
        if ch in product:
            continue
        k = int(np.searchsorted(product, ch)) - 1
        lo, hi = product[k], product[k + 1]
        w = (beam.freq_hz[ch] - beam.freq_hz[lo]) / (
            beam.freq_hz[hi] - beam.freq_hz[lo]
        )
        truth = np.asarray(beam.average[:, ch])
        pred = (1 - w) * np.asarray(beam.average[:, lo]) + w * np.asarray(
            beam.average[:, hi]
        )
        p_truth, p_pred = power_from_maps(truth), power_from_maps(pred)
        r, profile = bh.radial_profile(p_truth, x, y)
        radii = bh.lobe_radii(r, profile)
        inside = np.hypot(x, y) <= radii["r_first_null_deg"]
        errors.append(float(np.max(np.abs(p_pred - p_truth)[inside])))
    errors = np.array(errors)
    return {
        "held_out_channels": len(errors),
        "median_max_abs_dI_main_lobe": float(np.median(errors)),
        "p95_max_abs_dI_main_lobe": float(np.percentile(errors, 95)),
        "max_max_abs_dI_main_lobe": float(errors.max()),
        "pass": bool(np.median(errors) <= 2e-3 and np.percentile(errors, 95) <= 5e-3),
    }


def g0c(beam, channels):
    """Spline from even pixels evaluated at odd pixels (2x coarser grid)."""
    worst = []
    odd = np.arange(1, bh.NPIX, 2)
    rows, cols = np.meshgrid(odd / 2.0, odd / 2.0, indexing="ij")
    coords = np.stack([rows.ravel(), cols.ravel()])
    for ch in channels:
        maps = np.asarray(beam.average[:, ch])
        truth = power_from_maps(maps)
        sub = maps[:, ::2, ::2]
        pred = np.empty((4, odd.size, odd.size), complex)
        for p in range(4):
            re = ndimage.map_coordinates(
                sub[p].real.astype(float), coords, order=3, mode="nearest"
            )
            im = ndimage.map_coordinates(
                sub[p].imag.astype(float), coords, order=3, mode="nearest"
            )
            pred[p] = (re + 1j * im).reshape(odd.size, odd.size)
        p_pred = (
            0.5
            * np.sum(np.abs(pred) ** 2, axis=0)
            / (0.5 * np.sum(np.abs(maps[:, bh.CENTRE_INDEX, bh.CENTRE_INDEX]) ** 2))
        )
        p_truth = truth[1::2, 1::2]
        inside = p_truth >= 0.5
        worst.append(float(np.max(np.abs(p_pred - p_truth)[inside])))
    worst = np.array(worst)
    return {
        "channels": len(worst),
        "max_abs_dI_half_power": float(worst.max()),
        "median_abs_dI_half_power": float(np.median(worst)),
        "pass": bool(worst.max() <= 2e-3),
    }


# --------------------------------------------------------------------------
# Comparison


def model_power(model, x, y, freq_hz):
    jones = model.jones("array_average", x, y, freq_hz)
    return bh.stokes_i(jones), jones


def compare(beam, models, channels, lsm_offsets_deg=None, lsm_flux=None):
    half = 3.5
    step = bh.PIXEL_DEG
    x, y = bh.grid(half, step)
    r = np.hypot(x, y)
    per_channel = []
    for ch in channels:
        f = float(beam.freq_hz[ch])
        holo, holo_jones = model_power(beam, x, y, f)
        rr, profile = bh.radial_profile(holo, x, y, step_deg=step / 2, rmax_deg=half)
        radii = bh.lobe_radii(rr, profile)
        grad = bh.gradient_magnitude(holo, step)
        signal = grad * POINTING_ARCSEC / 3600.0
        ring = np.abs(r - radii["r_half_power_deg"]) <= step
        core = r <= radii["r_half_power_deg"]
        lobe = r <= radii["r_first_null_deg"]
        side = (r > radii["r_first_null_deg"]) & (r <= radii["r_second_null_deg"])
        entry = {"channel": int(ch), "freq_mhz": f / 1e6, "holography": radii}
        entry["holography"]["fit_I"] = bh.fit_main_lobe(holo, x, y)
        entry["holography"]["fit_H"] = bh.fit_main_lobe(
            np.abs(holo_jones[..., 0, 0]) ** 2, x, y
        )
        entry["holography"]["fit_V"] = bh.fit_main_lobe(
            np.abs(holo_jones[..., 1, 1]) ** 2, x, y
        )
        entry["holography"]["median_30arcsec_signal_on_ring"] = float(
            np.median(signal[ring])
        )
        for name, model in models.items():
            power, jones = model_power(model, x, y, f)
            diff = np.abs(power - holo)
            rm, prof_m = bh.radial_profile(
                power, x, y, step_deg=step / 2, rmax_deg=half
            )
            try:
                mradii = bh.lobe_radii(rm, prof_m)
            except (IndexError, ValueError):
                mradii = {}
            stats = {
                "fit_I": bh.fit_main_lobe(power, x, y),
                "fit_H": bh.fit_main_lobe(np.abs(jones[..., 0, 0]) ** 2, x, y),
                "fit_V": bh.fit_main_lobe(np.abs(jones[..., 1, 1]) ** 2, x, y),
                "radii": mradii,
                "core_max": float(diff[core].max()),
                "core_rms": float(np.sqrt(np.mean(diff[core] ** 2))),
                "lobe_max": float(diff[lobe].max()),
                "lobe_rms": float(np.sqrt(np.mean(diff[lobe] ** 2))),
                "sidelobe_max": float(diff[side].max()),
                "sidelobe_rms": float(np.sqrt(np.mean(diff[side] ** 2))),
                "ring_max_over_30arcsec_signal": float(
                    diff[ring].max() / np.median(signal[ring])
                ),
                "ring_median_ratio": float(np.median(diff[ring] / signal[ring])),
            }
            moon = {}
            for radius in MOON_RADII_ARCMIN:
                at = np.abs(r * 60 - radius) <= step * 60 / 2
                moon[f"{radius:g}"] = {
                    "holography_mean": float(holo[at].mean()),
                    "model_mean": float(power[at].mean()),
                    "abs_diff_mean": float(diff[at].mean()),
                    "abs_diff_max": float(diff[at].max()),
                }
            stats["moon"] = moon
            if lsm_offsets_deg is not None:
                # Position angles in the beam frame need the parallactic
                # angle (B1-2): use the azimuthal mean and max at each radius.
                means, maxima = [], []
                for radius in lsm_offsets_deg:
                    at = np.abs(r - radius) <= step / 2
                    if not at.any():
                        at = np.abs(r - radius) <= step
                    means.append(diff[at].mean())
                    maxima.append(diff[at].max())
                w = np.asarray(lsm_flux) / np.sum(lsm_flux)
                stats["pks1934_field"] = {
                    "flux_weighted_mean_abs_dI": float(np.sum(w * means)),
                    "flux_weighted_max_abs_dI": float(np.sum(w * maxima)),
                    "offaxis_flux_weighted_mean_abs_dI": float(
                        np.sum(w[1:] * np.asarray(means)[1:])
                        / max(np.sum(w[1:]), 1e-30)
                    ),
                }
            entry[name] = stats
        per_channel.append(entry)
    return per_channel


def antenna_spread(beam, channels):
    """RMS over antennas of I_b(antenna) - I_b(array average) in the main lobe."""
    x, y = native_xy(beam)
    out = []
    for k, ch in enumerate(beam.product_channels):
        if ch not in channels:
            continue
        avg = power_from_maps(np.asarray(beam.average[:, ch]))
        rr, profile = bh.radial_profile(avg, x, y)
        lobe = np.hypot(x, y) <= bh.lobe_radii(rr, profile)["r_first_null_deg"]
        core = avg >= 0.5
        diffs = []
        for i in range(len(beam.sampled_antennas)):
            ant = power_from_maps(np.asarray(beam.sampled[:, i, k]))
            diffs.append(ant - avg)
        diffs = np.array(diffs)
        out.append(
            {
                "channel": int(ch),
                "freq_mhz": float(beam.freq_hz[ch] / 1e6),
                "rms_over_antennas_main_lobe": float(
                    np.sqrt(np.mean(diffs[:, lobe] ** 2))
                ),
                "rms_over_antennas_core": float(np.sqrt(np.mean(diffs[:, core] ** 2))),
                "max_abs_main_lobe": float(np.abs(diffs[:, lobe]).max()),
            }
        )
    return out


def lsm_offsets(path):
    from rang import lsm

    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != LSM_SHA256:
        raise ValueError(f"lsm SHA256 {digest} does not match the frozen file")
    sources = lsm.load(path)
    flux = np.array([s.i for s in sources])
    order = np.argsort(flux)[::-1]
    sources = [sources[i] for i in order]
    ra0, dec0 = sources[0].ra, sources[0].dec
    ra = np.array([s.ra for s in sources])
    dec = np.array([s.dec for s in sources])
    cos_sep = np.sin(dec0) * np.sin(dec) + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0)
    sep = np.degrees(np.arccos(np.clip(cos_sep, -1, 1)))
    return sep, flux[order]


def summarise(per_channel, models):
    summary = {}
    for name in models:

        def col(key, sub=None, name=name):
            values = [
                c[name][key] if sub is None else c[name][key][sub] for c in per_channel
            ]
            return np.array(values, float)

        holo_major = np.array(
            [c["holography"]["fit_I"]["fwhm_major_deg"] for c in per_channel]
        )
        holo_minor = np.array(
            [c["holography"]["fit_I"]["fwhm_minor_deg"] for c in per_channel]
        )
        summary[name] = {
            "fwhm_major_ratio_median": float(
                np.median(col("fit_I", "fwhm_major_deg") / holo_major)
            ),
            "fwhm_minor_ratio_median": float(
                np.median(col("fit_I", "fwhm_minor_deg") / holo_minor)
            ),
            "fwhm_major_ratio_range": [
                float(np.min(col("fit_I", "fwhm_major_deg") / holo_major)),
                float(np.max(col("fit_I", "fwhm_major_deg") / holo_major)),
            ],
            "core_max_median": float(np.median(col("core_max"))),
            "core_max_max": float(np.max(col("core_max"))),
            "lobe_max_median": float(np.median(col("lobe_max"))),
            "lobe_rms_median": float(np.median(col("lobe_rms"))),
            "sidelobe_max_median": float(np.median(col("sidelobe_max"))),
            "sidelobe_rms_median": float(np.median(col("sidelobe_rms"))),
            "ring_max_over_30arcsec_signal_median": float(
                np.median(col("ring_max_over_30arcsec_signal"))
            ),
            "ring_max_over_30arcsec_signal_range": [
                float(np.min(col("ring_max_over_30arcsec_signal"))),
                float(np.max(col("ring_max_over_30arcsec_signal"))),
            ],
            "ring_median_ratio_median": float(np.median(col("ring_median_ratio"))),
        }
        levels = [c[name]["radii"].get("first_sidelobe_level") for c in per_channel]
        levels = np.array([v for v in levels if v is not None], float)
        if levels.size:
            summary[name]["first_sidelobe_level_median"] = float(np.median(levels))
        for radius in MOON_RADII_ARCMIN:
            key = f"{radius:g}"
            summary[name][f"moon_{key}_abs_diff_mean_median"] = float(
                np.median([c[name]["moon"][key]["abs_diff_mean"] for c in per_channel])
            )
        if "pks1934_field" in per_channel[0][name]:
            summary[name]["pks1934_flux_weighted_mean_abs_dI_median"] = float(
                np.median(
                    [
                        c[name]["pks1934_field"]["flux_weighted_mean_abs_dI"]
                        for c in per_channel
                    ]
                )
            )
            summary[name]["pks1934_offaxis_flux_weighted_mean_abs_dI_median"] = float(
                np.median(
                    [
                        c[name]["pks1934_field"]["offaxis_flux_weighted_mean_abs_dI"]
                        for c in per_channel
                    ]
                )
            )
    side = np.array([c["holography"]["first_sidelobe_level"] for c in per_channel])
    summary["holography"] = {
        "first_sidelobe_level_median": float(np.median(side)),
        "first_sidelobe_level_range": [float(side.min()), float(side.max())],
        "r_half_power_deg_range": [
            float(min(c["holography"]["r_half_power_deg"] for c in per_channel)),
            float(max(c["holography"]["r_half_power_deg"] for c in per_channel)),
        ],
        "median_30arcsec_signal_on_ring_median": float(
            np.median(
                [c["holography"]["median_30arcsec_signal_on_ring"] for c in per_channel]
            )
        ),
    }
    return summary


def _round(value, digits=6):
    """Round floats to `digits` significant digits for the committed archive."""
    if isinstance(value, dict):
        return {k: _round(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round(v, digits) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(f"{float(value):.{digits}g}")
    if isinstance(value, np.integer):
        return int(value)
    return value


def compact_channel(entry, models):
    """The per-channel numbers the report cites."""
    holo = entry["holography"]
    out = {
        "channel": entry["channel"],
        "freq_mhz": entry["freq_mhz"],
        "holography": {
            "r_half_power_deg": holo["r_half_power_deg"],
            "r_first_null_deg": holo["r_first_null_deg"],
            "first_sidelobe_level": holo["first_sidelobe_level"],
            "fwhm_I_major_deg": holo["fit_I"]["fwhm_major_deg"],
            "fwhm_I_minor_deg": holo["fit_I"]["fwhm_minor_deg"],
            "squint_H_arcmin": [
                60 * holo["fit_H"]["x0_deg"],
                60 * holo["fit_H"]["y0_deg"],
            ],
            "squint_V_arcmin": [
                60 * holo["fit_V"]["x0_deg"],
                60 * holo["fit_V"]["y0_deg"],
            ],
            "signal_30arcsec": holo["median_30arcsec_signal_on_ring"],
        },
    }
    for name in models:
        m = entry[name]
        out[name] = {
            "fwhm_I_major_deg": m["fit_I"]["fwhm_major_deg"],
            "fwhm_I_minor_deg": m["fit_I"]["fwhm_minor_deg"],
            "squint_H_arcmin": [60 * m["fit_H"]["x0_deg"], 60 * m["fit_H"]["y0_deg"]],
            "squint_V_arcmin": [60 * m["fit_V"]["x0_deg"], 60 * m["fit_V"]["y0_deg"]],
            "first_sidelobe_level": m["radii"].get("first_sidelobe_level"),
            "core_max": m["core_max"],
            "lobe_max": m["lobe_max"],
            "lobe_rms": m["lobe_rms"],
            "sidelobe_max": m["sidelobe_max"],
            "ring_max_over_30arcsec_signal": m["ring_max_over_30arcsec_signal"],
            "moon_abs_diff_mean": {k: v["abs_diff_mean"] for k, v in m["moon"].items()},
        }
        if "pks1934_field" in m:
            out[name]["pks1934_flux_weighted_mean_abs_dI"] = m["pks1934_field"][
                "flux_weighted_mean_abs_dI"
            ]
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--product", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--lsm")
    parser.add_argument("--json", default="research/results/b1-beam-product.json")
    parser.add_argument("--full-json", help="also write every fit and channel here")
    parser.add_argument("--flip", type=int, default=1)
    parser.add_argument(
        "--channel-stride",
        type=int,
        default=1,
        help="use every n-th product channel (smoke runs)",
    )
    parser.add_argument("--skip-eidos", action="store_true")
    args = parser.parse_args(argv)
    timings = {}
    t = time.perf_counter()
    beam = bh.HolographyBeam(args.product, flip=args.flip)
    metrics = np.load(args.metrics, allow_pickle=False)
    lo, hi = bh.COMPARISON_BAND_HZ
    product = np.asarray(beam.product_channels)
    band = product[(beam.freq_hz[product] >= lo) & (beam.freq_hz[product] <= hi)]
    band = band[band != 0][:: args.channel_stride]
    native_band = np.nonzero((beam.freq_hz >= lo) & (beam.freq_hz <= hi))[0]
    manifest = json.loads((Path(args.product) / "manifest.json").read_text())
    result = {
        "protocol": "research/b1-beam-pointing.md",
        "product": {
            "url": manifest["url"],
            "size": manifest["size"],
            "last_modified": manifest["last_modified"],
            "etag": manifest["etag"],
            "licence": bh.LICENCE,
            "citation": bh.CITATION,
            "channels_sampled": manifest["channels_sampled"],
            "files": {
                k: manifest[k]
                for k in manifest
                if k.endswith((".npy", "_sha256", "_bytes"))
            },
            "metrics_sha256": bh.sha256_file(args.metrics),
            "flip": beam.flip,
        },
        "band_channels": band.tolist(),
    }
    result["g0a"], g0a_rows = g0a(beam, metrics, band)
    result["katbeam_v_squint_sign"] = katbeam_squint_sign(beam, metrics, band)
    timings["g0a_s"] = time.perf_counter() - t
    t = time.perf_counter()
    result["g0b"] = g0b(beam, native_band[:: args.channel_stride])
    timings["g0b_s"] = time.perf_counter() - t
    t = time.perf_counter()
    result["g0c"] = g0c(beam, band)
    timings["g0c_s"] = time.perf_counter() - t
    t = time.perf_counter()
    models = {"katbeam": bh.KatBeam()}
    if not args.skip_eidos:
        models["eidos"] = bh.EidosBeam(flip=args.flip)
    offsets = flux = None
    if args.lsm:
        offsets, flux = lsm_offsets(args.lsm)
        result["pks1934_field"] = {
            "components": len(flux),
            "max_offset_arcmin": float(offsets.max() * 60),
            "offaxis_flux_fraction": float(flux[1:].sum() / flux.sum()),
        }
    per_channel = compare(beam, models, band, offsets, flux)
    timings["compare_s"] = time.perf_counter() - t
    t = time.perf_counter()
    spread = antenna_spread(beam, set(band.tolist()))
    timings["spread_s"] = time.perf_counter() - t
    result["summary"] = summarise(per_channel, models)
    sp = np.array([s["rms_over_antennas_main_lobe"] for s in spread])
    fq = np.array([s["freq_mhz"] for s in spread])
    result["antenna_spread"] = {
        "rms_main_lobe_median_below_1284mhz": float(np.median(sp[fq < 1284])),
        "rms_main_lobe_median_above_1284mhz": float(np.median(sp[fq >= 1284])),
        "per_channel": spread,
    }
    result["per_channel"] = per_channel
    result["g0a_rows"] = g0a_rows
    result["gates_pass"] = bool(
        result["g0a"]["pass"] and result["g0b"]["pass"] and result["g0c"]["pass"]
    )
    result["timings"] = timings
    if args.full_json:
        Path(args.full_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.full_json).write_text(json.dumps(result, indent=1, default=float))
    compact = {k: v for k, v in result.items() if k != "g0a_rows"}
    compact["per_channel"] = [compact_channel(c, models) for c in per_channel]
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(_round(compact), indent=1))
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "g0a",
                    "katbeam_v_squint_sign",
                    "g0b",
                    "g0c",
                    "summary",
                    "timings",
                )
            },
            indent=1,
            default=float,
        )
    )
    return result


if __name__ == "__main__":
    main()
