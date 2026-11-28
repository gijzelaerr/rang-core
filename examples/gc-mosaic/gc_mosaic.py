# SPDX-License-Identifier: MIT
"""Primary-beam correction, linear mosaic and a press-style rendering.

The last three steps of docs/tutorials/galactic-centre.md, which rang-core
and gemclean do not do themselves:

    python gc_mosaic.py pbcor  IMAGE.fits OUT.fits [--beam katbeam|mauch]
    python gc_mosaic.py mosaic OUT.fits IMAGE.fits [IMAGE.fits ...] [--frame galactic]
    python gc_mosaic.py render MOSAIC.fits OUT.png [--faint-max JY] [--bright-max JY]

Inputs are gemclean's (or WSClean's) restored images, not corrected for the
primary beam. The beam is the Stokes I power beam at the image's frequency,
azimuthally averaged, as Heywood et al. (2022, ApJ 925, 165) did with eidos:

- `katbeam` (default): SARAO's MKAT-AA-L-JIM-2020 model, read through the
  `beam` extra (`pip install 'rang-core[beam]'`), averaged over 72 angles;
- `mauch`: the analytic cosine beam of Mauch et al. (2020, ApJ 888, 61),
  eq. 3, theta_pb = 57.5' (nu / 1.5 GHz)^-1.

Pixels where the beam is below `--cutoff` (0.5, the paper's) are blanked.
The mosaic weights every pointing by its beam squared (equal noise per
pointing assumed): M = sum(B_i I_i) / sum(B_i^2), with I_i the uncorrected
image, which is sum(B_i^2 (I_i / B_i)) / sum(B_i^2). The rendering is the
paper's Figure 1 scheme: linear greyscale for faint emission and a heat map
with a square-root stretch above `--faint-max`.

Nothing here is a rang result; the tutorial says which steps were measured.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates

KATBEAM_MODEL = "MKAT-AA-L-JIM-2020"


# --- the beam -------------------------------------------------------------


def beam_mauch(r_deg, freq_mhz):
    """Mauch et al. (2020) eq. 3: the Stokes I power beam at radius r."""
    theta_pb = (57.5 / 60.0) * (1500.0 / freq_mhz)  # degrees
    x = 1.189 * np.asarray(r_deg, dtype=float) / theta_pb
    with np.errstate(divide="ignore", invalid="ignore"):
        amp = np.cos(np.pi * x) / (1.0 - 4.0 * x * x)
    amp = np.where(np.isclose(4.0 * x * x, 1.0), np.pi / 4.0, amp)
    return amp * amp


def beam_katbeam(r_deg, freq_mhz, n_angles=72):
    """katbeam's Stokes I beam, averaged over n_angles position angles."""
    try:
        from katbeam import JimBeam
    except ImportError as err:
        raise SystemExit(
            "katbeam is not installed: pip install 'rang-core[beam]', "
            "or use --beam mauch"
        ) from err
    beam = JimBeam(KATBEAM_MODEL)
    r = np.asarray(r_deg, dtype=float)
    total = np.zeros_like(r)
    for phi in np.linspace(0.0, 2.0 * np.pi, n_angles, endpoint=False):
        total += beam.I(r * np.cos(phi), r * np.sin(phi), freq_mhz)
    return total / n_angles


def beam_function(name):
    """The radial power beam B(r_deg, freq_mhz), tabulated for speed."""
    exact = {"katbeam": beam_katbeam, "mauch": beam_mauch}[name]

    def tabulated(r_deg, freq_mhz):
        grid = np.linspace(0.0, 3.0, 3001)  # 3.6 arcsec steps out to 3 deg
        table = exact(grid, freq_mhz)
        r = np.asarray(r_deg, dtype=float)
        return np.interp(r, grid, table, right=0.0)

    return tabulated


def cutoff_radius(beam, freq_mhz, cutoff):
    """The first radius (deg) where the beam falls to `cutoff`."""
    grid = np.linspace(0.0, 3.0, 30001)
    below = np.nonzero(beam(grid, freq_mhz) < cutoff)[0]
    if len(below) == 0:
        raise SystemExit(f"the beam never falls below {cutoff} within 3 deg")
    return grid[below[0]]


# --- FITS -----------------------------------------------------------------


def read_image(path):
    """The 2-D plane, its celestial WCS, header and frequency in MHz."""
    with fits.open(path) as hdul:
        header = hdul[0].header
        data = np.asarray(hdul[0].data, dtype=np.float64)
    plane = data.reshape(data.shape[-2:]) if data.ndim > 2 else data
    wcs = WCS(header).celestial
    freq = None
    for axis in range(1, header.get("NAXIS", 0) + 1):
        if str(header.get(f"CTYPE{axis}", "")).upper().startswith("FREQ"):
            freq = float(header[f"CRVAL{axis}"]) / 1e6
    if freq is None and "RESTFRQ" in header:
        freq = float(header["RESTFRQ"]) / 1e6
    return plane, wcs, header, freq


def pointing_centre(wcs):
    """The image's reference position, the phase (= pointing) centre."""
    lon, lat = wcs.wcs.crval
    frame = "galactic" if wcs.wcs.ctype[0].startswith("GLON") else "icrs"
    return SkyCoord(lon * u.deg, lat * u.deg, frame=frame).icrs


def separation_deg(wcs, centre, rows, cols):
    """Angular distance (deg) of pixels (rows, cols) from `centre`."""
    world = wcs.pixel_to_world(cols, rows)
    return world.icrs.separation(centre).deg


def restoring_beam(header):
    keys = ("BMAJ", "BMIN", "BPA")
    return {k: header[k] for k in keys if k in header}


# --- pbcor ----------------------------------------------------------------


def pbcor(image_path, out_path, beam_name="katbeam", cutoff=0.5, freq_mhz=None):
    """Divide one image by the beam; blank below `cutoff`; write it and B."""
    plane, wcs, header, freq = read_image(image_path)
    freq = freq_mhz or freq
    if freq is None:
        raise SystemExit(f"{image_path}: no FREQ axis; pass --freq-mhz")
    beam = beam_function(beam_name)
    rows, cols = np.indices(plane.shape)
    b = beam(separation_deg(wcs, pointing_centre(wcs), rows, cols), freq)
    with np.errstate(divide="ignore", invalid="ignore"):
        corrected = np.where(b >= cutoff, plane / b, np.nan)
    out = wcs.to_header()
    out.update(restoring_beam(header))
    out["BUNIT"] = header.get("BUNIT", "JY/BEAM")
    out["HISTORY"] = (
        f"gc_mosaic pbcor: {beam_name} beam at {freq:.3f} MHz, cutoff {cutoff}"
    )
    fits.writeto(out_path, corrected.astype(np.float32), out, overwrite=True)
    pb_path = Path(out_path).with_name(Path(out_path).stem + "-pb.fits")
    fits.writeto(pb_path, b.astype(np.float32), wcs.to_header(), overwrite=True)
    return corrected, b


# --- mosaic ---------------------------------------------------------------


def output_wcs(inputs, frame, pixel_deg, radii):
    """A grid covering every input out to its cutoff radius."""
    centres = [pointing_centre(w) for _, w, _, _ in inputs]
    ring = np.linspace(0.0, 2.0 * np.pi, 73)
    edge = []
    for c, r in zip(centres, radii):
        pts = c.directional_offset_by(ring * u.rad, r * u.deg)
        edge.append(pts.galactic if frame == "galactic" else pts.icrs)
    if frame == "galactic":
        lon = np.concatenate([e.l.wrap_at(180 * u.deg).deg for e in edge])
        lat = np.concatenate([e.b.deg for e in edge])
        ctype = ["GLON-CAR", "GLAT-CAR"]
    else:
        lon = np.concatenate([e.ra.deg for e in edge])
        lat = np.concatenate([e.dec.deg for e in edge])
        ctype = ["RA---SIN", "DEC--SIN"]
    lon0, lat0 = 0.5 * (lon.min() + lon.max()), 0.5 * (lat.min() + lat.max())
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ctype
    wcs.wcs.crval = [lon0 % 360.0, 0.0 if frame == "galactic" else lat0]
    wcs.wcs.cdelt = [-pixel_deg, pixel_deg]
    wcs.wcs.crpix = [1.0, 1.0]
    # place every edge point at a positive pixel, with a 2-pixel margin
    sky = (
        SkyCoord(lon * u.deg, lat * u.deg, frame="galactic")
        if frame == "galactic"
        else SkyCoord(lon * u.deg, lat * u.deg, frame="icrs")
    )
    x, y = wcs.world_to_pixel(sky)
    wcs.wcs.crpix = [2.0 - x.min() + 1.0, 2.0 - y.min() + 1.0]
    nx = int(np.ceil(x.max() - x.min())) + 5
    ny = int(np.ceil(y.max() - y.min())) + 5
    return wcs, (ny, nx)


def mosaic(
    out_path,
    image_paths,
    beam_name="katbeam",
    cutoff=0.5,
    frame="galactic",
    pixel_arcsec=None,
    chunk=512,
):
    """Beam-squared-weighted linear mosaic of uncorrected images."""
    inputs = [read_image(p) for p in image_paths]
    for path, (_, _, _, freq) in zip(image_paths, inputs):
        if freq is None:
            raise SystemExit(f"{path}: no FREQ axis in the header")
    beam = beam_function(beam_name)
    radii = [cutoff_radius(beam, f, cutoff) for _, _, _, f in inputs]
    if pixel_arcsec is None:
        pixel_deg = min(abs(w.wcs.cdelt[0]) for _, w, _, _ in inputs)
    else:
        pixel_deg = pixel_arcsec / 3600.0
    wcs, shape = output_wcs(inputs, frame, pixel_deg, radii)
    num = np.zeros(shape)
    den = np.zeros(shape)
    for (plane, w, _, freq), radius in zip(inputs, radii):
        centre = pointing_centre(w)
        # this input's footprint in output pixels
        ring = centre.directional_offset_by(
            np.linspace(0, 2 * np.pi, 73) * u.rad, radius * u.deg
        )
        xs, ys = wcs.world_to_pixel(ring)
        x0, x1 = (
            max(int(np.floor(xs.min())), 0),
            min(int(np.ceil(xs.max())) + 1, shape[1]),
        )
        y0, y1 = (
            max(int(np.floor(ys.min())), 0),
            min(int(np.ceil(ys.max())) + 1, shape[0]),
        )
        for r0 in range(y0, y1, chunk):
            r1 = min(r0 + chunk, y1)
            rows, cols = np.mgrid[r0:r1, x0:x1]
            world = wcs.pixel_to_world(cols, rows)
            b = beam(world.icrs.separation(centre).deg, freq)
            ix, iy = w.world_to_pixel(world)
            value = map_coordinates(
                plane, [iy.ravel(), ix.ravel()], order=1, cval=np.nan
            ).reshape(rows.shape)
            use = (b >= cutoff) & np.isfinite(value)
            num[r0:r1, x0:x1] += np.where(use, b * value, 0.0)
            den[r0:r1, x0:x1] += np.where(use, b * b, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(den > 0, num / den, np.nan)
    header = wcs.to_header()
    beams = [restoring_beam(h) for _, _, h, _ in inputs]
    if all("BMAJ" in b for b in beams):
        widest = max(beams, key=lambda b: b["BMAJ"])
        header.update(widest)
        header["COMMENT"] = "BMAJ/BMIN/BPA: the widest input restoring beam"
    header["BUNIT"] = "JY/BEAM"
    header["HISTORY"] = (
        f"gc_mosaic mosaic: {len(inputs)} pointings, {beam_name} beam, "
        f"cutoff {cutoff}, weights B^2"
    )
    fits.writeto(out_path, out.astype(np.float32), header, overwrite=True)
    weight_path = Path(out_path).with_name(Path(out_path).stem + "-weight.fits")
    fits.writeto(weight_path, den.astype(np.float32), wcs.to_header(), overwrite=True)
    return out, den, wcs


# --- render ---------------------------------------------------------------


def robust_sigma(values):
    v = values[np.isfinite(values)]
    return 1.4826 * np.median(np.abs(v - np.median(v)))


def block_mean(plane, n):
    if n <= 1:
        return plane
    ny, nx = (plane.shape[0] // n) * n, (plane.shape[1] // n) * n
    view = plane[:ny, :nx].reshape(ny // n, n, nx // n, n)
    with np.errstate(invalid="ignore"):
        return np.nanmean(view, axis=(1, 3))


def render_rgb(plane, faint_min=None, faint_max=None, bright_max=None, heat="afmhot"):
    """RGB array: linear grey below faint_max, square-root heat map above."""
    from matplotlib import colormaps

    sigma = robust_sigma(plane)
    finite = plane[np.isfinite(plane)]
    faint_min = -2.0 * sigma if faint_min is None else faint_min
    faint_max = 10.0 * sigma if faint_max is None else faint_max
    if bright_max is None:
        bright_max = max(np.percentile(finite, 99.95), 2.0 * faint_max)
    # grey runs from black to 0.7, where the heat map's orange continues it
    grey = 0.7 * np.clip((plane - faint_min) / (faint_max - faint_min), 0.0, 1.0)
    hot = np.sqrt(np.clip((plane - faint_max) / (bright_max - faint_max), 0.0, 1.0))
    rgb = np.repeat(grey[..., None], 3, axis=-1)
    bright = plane > faint_max
    # the heat map starts at 0.45 of its range, about as bright as the grey's top
    rgb[bright] = colormaps[heat](0.45 + 0.55 * hot[bright])[:, :3]
    rgb[~np.isfinite(plane)] = 0.0
    return rgb, {
        "sigma": sigma,
        "faint_min": faint_min,
        "faint_max": faint_max,
        "bright_max": bright_max,
    }


def render(mosaic_path, out_png, downsample=1, **levels):
    import matplotlib.pyplot as plt

    plane, _, _, _ = read_image(mosaic_path)
    plane = block_mean(plane, downsample)
    rgb, used = render_rgb(plane, **levels)
    plt.imsave(out_png, rgb, origin="lower")
    return rgb, used


# --- command line ---------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("pbcor", help="correct one image for the primary beam")
    p.add_argument("image", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--beam", choices=["katbeam", "mauch"], default="katbeam")
    p.add_argument("--cutoff", type=float, default=0.5)
    p.add_argument("--freq-mhz", type=float, default=None)

    m = sub.add_parser("mosaic", help="beam-squared-weighted linear mosaic")
    m.add_argument("out", type=Path)
    m.add_argument("images", type=Path, nargs="+")
    m.add_argument("--beam", choices=["katbeam", "mauch"], default="katbeam")
    m.add_argument("--cutoff", type=float, default=0.5)
    m.add_argument("--frame", choices=["galactic", "icrs"], default="galactic")
    m.add_argument("--pixel-arcsec", type=float, default=None)

    r = sub.add_parser("render", help="PNG in the paper's two-colour scheme")
    r.add_argument("mosaic", type=Path)
    r.add_argument("out", type=Path)
    r.add_argument(
        "--faint-min", type=float, default=None, help="Jy/beam (default -2 sigma)"
    )
    r.add_argument(
        "--faint-max", type=float, default=None, help="Jy/beam (default 10 sigma)"
    )
    r.add_argument(
        "--bright-max",
        type=float,
        default=None,
        help="Jy/beam (default 99.95th percentile)",
    )
    r.add_argument(
        "--downsample", type=int, default=1, help="block-average N x N pixels first"
    )

    args = parser.parse_args(argv)
    if args.command == "pbcor":
        pbcor(args.image, args.out, args.beam, args.cutoff, args.freq_mhz)
    elif args.command == "mosaic":
        _, den, _ = mosaic(
            args.out, args.images, args.beam, args.cutoff, args.frame, args.pixel_arcsec
        )
        print(
            f"{args.out}: {den.shape[1]} x {den.shape[0]} pixels, "
            f"{np.count_nonzero(den)} with data"
        )
    else:
        _, used = render(
            args.mosaic,
            args.out,
            args.downsample,
            faint_min=args.faint_min,
            faint_max=args.faint_max,
            bright_max=args.bright_max,
        )
        print(f"{args.out}: " + ", ".join(f"{k} {v:.3g}" for k, v in used.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
