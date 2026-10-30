"""The simulated MeerKAT field of big-plan task DF5-O (research/df5o-deconv-oracles.md).

    python examples/simulate_df5_field.py OUT_DIR

Writes, into a fresh OUT_DIR:

- `field.ms`: a Measurement Set created by the core (`core_ms_write.default_ms`)
  and filled through the core writer: 64 MeerKAT antennas, 120 dumps of 120 s
  (hour angle -2 h to +2 h), 16 channels of 48.125 MHz from 900 MHz, XX, XY,
  YX, YY with radiometer noise, WEIGHT_SPECTRUM = 1/sigma^2;
- `truth-mfs.fits`, `truth-cube.fits` (float64, WSClean's orientation and
  header), `truth.json` (the component list) and `truth-wsclean.txt` (the
  same as a WSClean source list, `rang.formats.sky.dumps_wsclean`);
- `field.npz`: Stokes-I visibilities as the tools read them, weights, UVW,
  frequencies, the truth cube, the noise-free visibilities;
- `field.json`: settings, seeds, the PSF size and the multiscale scales the
  protocol's rule gives, the orientation and prediction checks, the exact
  image noise, hashes and timings.

The truth is defined on the image grid (points on pixel centres, Gaussians
sampled at pixel centres and normalised to their flux) and predicted per
channel by the core's exact degridder; the point components are checked
against the core's DFT predictor.
"""

import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from rang import core, core_grid, core_ms_write, core_wgridder, rusage
from rang.formats import sky

ROOT = Path(__file__).resolve().parents[1]
C = 299792458.0
ARCSEC = math.pi / (180 * 3600)

# -- frozen settings (research/df5o-deconv-oracles.md section 1) --------------
RA0 = math.radians(15 * (16 + 15 / 60))  # 16h15m00s
DEC0 = -math.radians(60 + 54 / 60)  # -60d54m00s
MJD_DAY = 61120.0  # 2026-03-21 0h UTC
NDUMP, DUMP = 120, 120.0
NCHAN, CHAN0, CHANW = 16, 900e6, 48.125e6
NU0 = 1284e6
NPIX, CELL = 1024, 2.0  # pixels, arcsec
RADIUS = 240  # pixels: all emission within the inner half
SEFD = 425.0
SKY_SEED, NOISE_SEED = 20261031, 5101
EPS_PREDICT = 1e-10
BLOCK_DUMPS = 4


def sha256_bytes(*arrays):
    h = hashlib.sha256()
    for a in arrays:
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_hashes(directory):
    """SHA256 of every file under `directory` (sorted) and of the listing."""
    files = sorted(p for p in Path(directory).rglob("*") if p.is_file())
    rows = {str(p.relative_to(directory)): sha256_file(p) for p in files}
    listing = "".join(f"{k} {v}\n" for k, v in rows.items())
    return rows, hashlib.sha256(listing.encode()).hexdigest()


# -- geometry -----------------------------------------------------------------


def gmst82(mjd_ut1):
    """Greenwich mean sidereal time (radians), IAU 1982."""
    jd = np.asarray(mjd_ut1, float) + 2400000.5
    t = (jd - 2451545.0) / 36525.0
    seconds = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * t
        + 0.093104 * t**2
        - 6.2e-6 * t**3
    )
    return np.mod(seconds, 86400.0) / 86400.0 * 2 * math.pi


def antennas():
    rows = [
        ln.split()
        for ln in (ROOT / "data/meerkat.itrf.txt").read_text().splitlines()
        if ln.strip()
    ]
    xyz = np.array([[float(r[0]), float(r[1]), float(r[2])] for r in rows])
    names = [r[4] for r in rows]
    diam = np.array([float(r[3]) for r in rows])
    return xyz, names, diam


def track(xyz):
    """Dump-centre times (MJD s), local hour angles and (time, ant, 3) uvw."""
    centre = xyz.mean(0)
    lon = math.atan2(centre[1], centre[0])
    lat = math.atan2(centre[2], math.hypot(centre[0], centre[1]))
    # transit on MJD_DAY: local hour angle gmst + lon - ra = 0
    grid = MJD_DAY + np.arange(0, 86400.0, 1.0) / 86400.0
    ha = np.angle(np.exp(1j * (gmst82(grid) + lon - RA0)))
    k = int(np.flatnonzero((ha[:-1] < 0) & (ha[1:] >= 0))[0])
    # refine by linear interpolation
    t_tr = (k + (-ha[k]) / (ha[k + 1] - ha[k])) / 86400.0 + MJD_DAY
    offsets = (np.arange(NDUMP) - (NDUMP - 1) / 2) * DUMP
    mjd = t_tr + offsets / 86400.0
    h_g = gmst82(mjd) - RA0  # Greenwich hour angle
    local = np.angle(np.exp(1j * (h_g + lon)))
    sd, cd = math.sin(DEC0), math.cos(DEC0)
    sh, ch = np.sin(h_g)[:, None], np.cos(h_g)[:, None]
    x, y, z = xyz[None, :, 0], xyz[None, :, 1], xyz[None, :, 2]
    u = sh * x + ch * y
    v = -sd * ch * x + sd * sh * y + cd * z
    w = cd * ch * x - cd * sh * y + sd * z
    elevation = np.degrees(
        np.arcsin(math.sin(lat) * sd + math.cos(lat) * cd * np.cos(local))
    )
    return mjd * 86400.0, local, np.stack([u, v, w], -1), lon, lat, elevation


def baselines(nant):
    a1, a2 = np.triu_indices(nant, 1)
    return a1.astype(np.int32), a2.astype(np.int32)


# -- the sky ------------------------------------------------------------------


def gaussian_image(x0, y0, fwhm_maj, fwhm_min, pa, flux):
    """A Gaussian (FWHM in arcsec, PA east of north, radians) sampled at the
    pixel centres of the FITS grid (x west-to-east reversed: x grows with
    decreasing RA) and normalised to `flux`; returns (slices, patch)."""
    smaj = fwhm_maj / (2 * math.sqrt(2 * math.log(2))) / CELL
    smin = fwhm_min / (2 * math.sqrt(2 * math.log(2))) / CELL
    half = math.ceil(5 * smaj) + 1
    ys, xs = np.mgrid[-half : half + 1, -half : half + 1].astype(float)
    east, north = -xs, ys
    # major axis along (sin pa, cos pa) in (east, north)
    a = east * math.sin(pa) + north * math.cos(pa)
    b = east * math.cos(pa) - north * math.sin(pa)
    g = np.exp(-0.5 * ((a / smaj) ** 2 + (b / smin) ** 2))
    g *= flux / g.sum()
    sl = (slice(y0 - half, y0 + half + 1), slice(x0 - half, x0 + half + 1))
    return sl, g


def psf_fwhm_pixels(psf):
    """FWHM of the PSF main lobe (major, minor, pixels) from the second
    moments of its half-maximum region (a uniform ellipse of semi-axes
    FWHM/2 has variance (FWHM/2)^2/4 along each axis)."""
    from scipy import ndimage

    n = psf.shape[0]
    labels, _ = ndimage.label(psf > 0.5)
    region = labels == labels[n // 2, n // 2]
    ys, xs = np.nonzero(region)
    cov = np.cov(np.stack([xs - xs.mean(), ys - ys.mean()]))
    lam = np.sort(np.linalg.eigvalsh(cov))[::-1]
    return 4 * math.sqrt(lam[0]), 4 * math.sqrt(lam[1]), int(region.sum())


def make_sky(beam_arcsec):
    """The frozen truth component list (pixel positions in FITS x, y)."""
    rng = np.random.default_rng(SKY_SEED)
    centre = NPIX // 2
    placed = []  # (x, y, radius_arcsec)

    def free(x, y, r, extent):
        # the source's emission (centre plus its FWHM) lies inside the disc
        if math.hypot(x - centre, y - centre) * CELL + extent > RADIUS * CELL:
            return False
        return all(
            math.hypot(x - px, y - py) * CELL >= 1.5 * (r + pr) for px, py, pr in placed
        )

    def draw_position(r, extent):
        for _ in range(100000):
            rad = RADIUS * math.sqrt(rng.uniform(0.0, 1.0))
            ang = rng.uniform(0, 2 * math.pi)
            x = round(centre + rad * math.cos(ang))
            y = round(centre + rad * math.sin(ang))
            if free(x, y, r, extent):
                return x, y
        raise RuntimeError("placement failed")

    comps = []
    # the radio galaxy: an ESO 137-006-like wide-angle tail, 150 px from the centre
    ang = rng.uniform(0, 2 * math.pi)
    rot = rng.uniform(0, 2 * math.pi)
    gx = round(centre + 150 * math.cos(ang))
    gy = round(centre + 150 * math.sin(ang))
    parts = [("core", 0.0, 0.0, 0.0, 0.0, 0.0, 1.0e-3, 0.0)]
    for side in (-1, 1):
        for i in range(1, 6):
            ex, ny = (
                side * 12.0 * i,
                1.5 * i * i,
            )  # arcsec east, north (before rotation)
            parts.append(
                (
                    f"jet{'w' if side < 0 else 'e'}{i}",
                    ex,
                    ny,
                    8.0,
                    5.0,
                    math.atan2(side * 12.0, 3.0 * i),
                    0.15e-3,
                    -0.6,
                )
            )
        parts.append(
            (
                f"lobe{'w' if side < 0 else 'e'}",
                side * 75.0,
                55.0,
                36.0,
                18.0,
                math.radians(side * 30.0),
                2.5e-3,
                -0.9,
            )
        )
    parts.append(("tail", 0.0, 70.0, 90.0, 36.0, math.radians(90.0), 1.5e-3, -1.4))
    extent = 0.0
    for name, ex, ny, fmaj, fmin, pa, flux, alpha in parts:
        re = ex * math.cos(rot) - ny * math.sin(rot)
        rn = ex * math.sin(rot) + ny * math.cos(rot)
        x = gx + round(-re / CELL)
        y = gy + round(rn / CELL)
        extent = max(extent, math.hypot(x - gx, y - gy) * CELL + fmaj)
        comps.append(
            {
                "name": f"rg-{name}",
                "source": "rg",
                "x": x,
                "y": y,
                "flux": flux,
                "alpha": alpha,
                "fwhm_maj": fmaj,
                "fwhm_min": fmin,
                "pa": (pa + rot) % math.pi if fmaj else 0.0,
            }
        )
    r_rg = math.hypot(extent, beam_arcsec)
    if math.hypot(gx - centre, gy - centre) * CELL + extent > RADIUS * CELL:
        raise RuntimeError("radio galaxy leaves the disc")
    placed.append((gx, gy, r_rg))
    sources = [{"name": "rg", "kind": "complex", "x": gx, "y": gy, "radius": r_rg}]
    # four Gaussians
    for k, (fmaj, flux) in enumerate(
        zip((12.0, 24.0, 40.0, 64.0), (0.5e-3, 1e-3, 2e-3, 4e-3))
    ):
        ratio = rng.uniform(0.5, 1.0)
        pa = rng.uniform(0, math.pi)
        r = math.hypot(fmaj, beam_arcsec)
        x, y = draw_position(r, fmaj)
        placed.append((x, y, r))
        name = f"g{k}"
        comps.append(
            {
                "name": name,
                "source": name,
                "x": x,
                "y": y,
                "flux": flux,
                "alpha": -0.8,
                "fwhm_maj": fmaj,
                "fwhm_min": fmaj * ratio,
                "pa": pa,
            }
        )
        sources.append({"name": name, "kind": "gaussian", "x": x, "y": y, "radius": r})
    # forty points
    fluxes = np.exp(rng.uniform(math.log(15e-6), math.log(20e-3), 40))
    alphas = rng.normal(-0.7, 0.25, 40)
    for k in range(40):
        r = beam_arcsec
        x, y = draw_position(r, 0.0)
        placed.append((x, y, r))
        name = f"p{k:02d}"
        comps.append(
            {
                "name": name,
                "source": name,
                "x": x,
                "y": y,
                "flux": float(fluxes[k]),
                "alpha": float(alphas[k]),
                "fwhm_maj": 0.0,
                "fwhm_min": 0.0,
                "pa": 0.0,
            }
        )
        sources.append({"name": name, "kind": "point", "x": x, "y": y, "radius": r})
    return comps, sources


def component_image(comp, scale=1.0):
    img = np.zeros((NPIX, NPIX))
    if comp["fwhm_maj"] == 0.0:
        img[comp["y"], comp["x"]] = comp["flux"] * scale
        return img
    sl, g = gaussian_image(
        comp["x"],
        comp["y"],
        comp["fwhm_maj"],
        comp["fwhm_min"],
        comp["pa"],
        comp["flux"] * scale,
    )
    img[sl] += g
    return img


def truth_cube(comps, freqs):
    """(chan, y, x) truth in Jy/pixel; each component's pixels times its
    spectrum at the channel."""
    cube = np.zeros((len(freqs), NPIX, NPIX))
    for comp in comps:
        base = component_image(comp)
        nz = np.nonzero(base)
        for c, f in enumerate(freqs):
            cube[c][nz] += base[nz] * (f / NU0) ** comp["alpha"]
    return cube


# -- prediction ---------------------------------------------------------------


def degrid(image_fits, uvw, freq, eps=EPS_PREDICT):
    """Visibilities of a FITS-orientation image (the adjoint of fits_image)."""
    return core_wgridder.dirty2vis(
        uvw=uvw,
        freq=np.atleast_1d(freq),
        dirty=np.ascontiguousarray(image_fits.T, np.float64),
        pixsize_x=CELL * ARCSEC,
        pixsize_y=CELL * ARCSEC,
        epsilon=eps,
        do_wgridding=True,
        flip_v=True,
        flip_w=True,
        divide_by_n=False,
    )


def pixel_lm(x, y):
    """rang-convention (l, m) of FITS pixel (x, y): the gridder layout is
    the FITS image transposed, pixel (i, j) = (x, y) at l = (i - n/2) dx,
    m = (j - n/2) dy."""
    return (x - NPIX // 2) * CELL * ARCSEC, (y - NPIX // 2) * CELL * ARCSEC


def orientation_check(uvw, freq):
    """Which (l, m) of the DFT predictor a FITS pixel is: a delta at an
    asymmetric pixel degridded, against predict_components at the four sign
    choices."""
    x, y = 700, 430
    img = np.zeros((NPIX, NPIX))
    img[y, x] = 1.0
    vg = degrid(img, uvw, freq)
    l, m = pixel_lm(x, y)
    out = {}
    for sl in (1, -1):
        for sm in (1, -1):
            vd = core.predict_components(
                uvw,
                np.atleast_1d(freq),
                [[sl * l, sm * m]],
                [0],
                [1.0],
                [[0.0]],
                [True],
                [NU0],
                [[0, 0, 0]],
            )
            out[(sl, sm)] = float(np.abs(vd - vg).max())
    best = min(out, key=out.get)
    return best, {f"{k[0]:+d},{k[1]:+d}": v for k, v in out.items()}


def fits_header(freqs, header_freqs=None):
    hdr = core_grid.wcs_header(
        (RA0, DEC0),
        NPIX,
        NPIX,
        CELL,
        header_freqs if header_freqs is not None else freqs,
    )
    hdr["BUNIT"] = "JY/PIXEL"
    return hdr


def write_fits64(path, data, header):
    from astropy.io import fits

    data = np.asarray(data, np.float64)
    while data.ndim < 4:
        data = data[np.newaxis]
    hdu = fits.PrimaryHDU(data)
    for k, v in header.items():
        hdu.header[k] = v
    hdu.header["ORIGIN"] = "rang DF5-O truth"
    hdu.writeto(str(path), overwrite=False)


def pixel_radec(header, x, y):
    from astropy.wcs import WCS

    w = WCS(
        {
            k: v
            for k, v in header.items()
            if k[:5] in ("CTYPE", "CRPIX", "CRVAL", "CDELT", "CUNIT") and k[-1] in "12"
        }
    )
    ra, dec = w.wcs_pix2world(np.array([[x, y]], float), 0)[0]
    return math.radians(ra) % (2 * math.pi), math.radians(dec)


# -- the MS -------------------------------------------------------------------


def write_ms(
    path, names, xyz, diam, times, uvw_rows, a1, a2, freqs, data_blocks, sigma
):
    nrow = len(a1)
    nbl = nrow // NDUMP
    desc = [
        core_ms_write.makearrcoldesc("DATA", 0j, valuetype="complex", shape=[NCHAN, 4]),
        core_ms_write.makearrcoldesc(
            "WEIGHT_SPECTRUM", 0.0, valuetype="float", shape=[NCHAN, 4]
        ),
        core_ms_write.makearrcoldesc(
            "SIGMA_SPECTRUM", 0.0, valuetype="float", shape=[NCHAN, 4]
        ),
    ]
    hashes = {
        k: hashlib.sha256() for k in ("DATA", "UVW", "WEIGHT_SPECTRUM", "FLAG", "TIME")
    }
    ms = core_ms_write.default_ms(str(path), desc)
    ms.addrows(nrow)
    t_rows = np.repeat(times, nbl)
    for name, value in (
        ("TIME", t_rows),
        ("TIME_CENTROID", t_rows),
        ("INTERVAL", np.full(nrow, DUMP)),
        ("EXPOSURE", np.full(nrow, DUMP)),
        ("ANTENNA1", a1),
        ("ANTENNA2", a2),
        ("UVW", uvw_rows),
        ("SCAN_NUMBER", np.ones(nrow, np.int32)),
        ("FLAG_ROW", np.zeros(nrow, bool)),
        ("WEIGHT", np.full((nrow, 4), 1 / sigma**2, np.float32)),
        ("SIGMA", np.full((nrow, 4), sigma, np.float32)),
    ):
        ms.putcol(name, value)
    hashes["TIME"].update(np.ascontiguousarray(t_rows).tobytes())
    hashes["UVW"].update(np.ascontiguousarray(uvw_rows).tobytes())
    wspec_block = None
    for start, data in data_blocks:
        n = data.shape[0]
        if wspec_block is None or wspec_block.shape[0] != n:
            wspec_block = np.full((n, NCHAN, 4), 1 / sigma**2, np.float32)
            sspec_block = np.full((n, NCHAN, 4), sigma, np.float32)
            flag_block = np.zeros((n, NCHAN, 4), bool)
        ms.putcol("DATA", data, startrow=start, nrow=n)
        ms.putcol("WEIGHT_SPECTRUM", wspec_block, startrow=start, nrow=n)
        ms.putcol("SIGMA_SPECTRUM", sspec_block, startrow=start, nrow=n)
        ms.putcol("FLAG", flag_block, startrow=start, nrow=n)
        hashes["DATA"].update(data.tobytes())
        hashes["WEIGHT_SPECTRUM"].update(wspec_block.tobytes())
        hashes["FLAG"].update(flag_block.tobytes())
    ms.close()

    nant = len(names)
    with core_ms_write.open_table(f"{path}/ANTENNA", readonly=False) as t:
        t.addrows(nant)
        t.putcol("NAME", names)
        t.putcol("STATION", names)
        t.putcol("TYPE", ["GROUND-BASED"] * nant)
        t.putcol("MOUNT", ["ALT-AZ"] * nant)
        t.putcol("DISH_DIAMETER", diam)
        t.putcol("POSITION", xyz)
        t.putcol("OFFSET", np.zeros((nant, 3)))
        t.putcol("FLAG_ROW", np.zeros(nant, bool))
    with core_ms_write.open_table(f"{path}/SPECTRAL_WINDOW", readonly=False) as t:
        t.addrows(1)
        width = np.full(NCHAN, CHANW)
        t.putcell("CHAN_FREQ", 0, freqs)
        t.putcell("CHAN_WIDTH", 0, width)
        t.putcell("EFFECTIVE_BW", 0, width)
        t.putcell("RESOLUTION", 0, width)
        t.putcell("NUM_CHAN", 0, NCHAN)
        t.putcell("REF_FREQUENCY", 0, float(freqs[NCHAN // 2]))
        t.putcell("TOTAL_BANDWIDTH", 0, float(width.sum()))
        t.putcell("MEAS_FREQ_REF", 0, 5)
        t.putcell("NAME", 0, "df5o")
        t.putcell("NET_SIDEBAND", 0, 1)
    with core_ms_write.open_table(f"{path}/POLARIZATION", readonly=False) as t:
        t.addrows(1)
        t.putcell("NUM_CORR", 0, 4)
        t.putcell("CORR_TYPE", 0, np.array([9, 10, 11, 12], np.int32))
        t.putcell(
            "CORR_PRODUCT", 0, np.array([[0, 0], [0, 1], [1, 0], [1, 1]], np.int32)
        )
    with core_ms_write.open_table(f"{path}/DATA_DESCRIPTION", readonly=False) as t:
        t.addrows(1)
        t.putcell("SPECTRAL_WINDOW_ID", 0, 0)
        t.putcell("POLARIZATION_ID", 0, 0)
    with core_ms_write.open_table(f"{path}/FIELD", readonly=False) as t:
        t.addrows(1)
        direction = np.array([[RA0, DEC0]])
        for col in ("PHASE_DIR", "DELAY_DIR", "REFERENCE_DIR"):
            t.putcell(col, 0, direction)
        t.putcell("NAME", 0, "DF5O-SIM")
        t.putcell("TIME", 0, float(times[0]))
    with core_ms_write.open_table(f"{path}/OBSERVATION", readonly=False) as t:
        t.addrows(1)
        t.putcell("TELESCOPE_NAME", 0, "MeerKAT")
        t.putcell(
            "TIME_RANGE", 0, np.array([times[0] - DUMP / 2, times[-1] + DUMP / 2])
        )
        t.putcell("OBSERVER", 0, "rang DF5-O simulation")
        t.putcell("PROJECT", 0, "DF5-O")
    with core_ms_write.open_table(f"{path}/FEED", readonly=False) as t:
        t.addrows(nant)
        t.putcol("ANTENNA_ID", np.arange(nant, dtype=np.int32))
        t.putcol("FEED_ID", np.zeros(nant, np.int32))
        t.putcol("SPECTRAL_WINDOW_ID", np.full(nant, -1, np.int32))
        t.putcol("TIME", np.full(nant, float(times[0])))
        t.putcol("INTERVAL", np.full(nant, 1e30))
        t.putcol("NUM_RECEPTORS", np.full(nant, 2, np.int32))
        t.putcol("BEAM_ID", np.full(nant, -1, np.int32))
        t.putcol("BEAM_OFFSET", np.zeros((nant, 2, 2)))
        t.putcol("POLARIZATION_TYPE", np.array([["X", "Y"]] * nant))
        t.putcol("POL_RESPONSE", np.tile(np.eye(2, dtype=np.complex64), (nant, 1, 1)))
        t.putcol("POSITION", np.zeros((nant, 3)))
        t.putcol("RECEPTOR_ANGLE", np.zeros((nant, 2)))
    return {k: h.hexdigest() for k, h in hashes.items()}


def main(out):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} exists and is not empty; choose a fresh directory")
    out.mkdir(parents=True, exist_ok=True)
    timings = {}
    t0 = time.perf_counter()

    xyz, names, diam = antennas()
    times, local_ha, ant_uvw, lon, lat, elevation = track(xyz)
    a1, a2 = baselines(len(names))
    nbl = len(a1)
    uvw = (ant_uvw[:, a1] - ant_uvw[:, a2]).reshape(NDUMP * nbl, 3)
    a1r, a2r = np.tile(a1, NDUMP), np.tile(a2, NDUMP)
    freqs = CHAN0 + (np.arange(NCHAN) + 0.5) * CHANW
    nrow = len(uvw)
    sigma = SEFD / math.sqrt(2 * CHANW * DUMP)
    sigma_i = sigma / math.sqrt(2)
    w_i = 1.0 / sigma_i**2
    sigma_img_chan = sigma_i / math.sqrt(nrow)
    sigma_img = sigma_i / math.sqrt(nrow * NCHAN)
    timings["geometry_s"] = time.perf_counter() - t0

    # PSF (natural, MFS) and the protocol's multiscale rule
    t = time.perf_counter()
    ones = np.ones((nrow, NCHAN), np.complex128)
    wts = np.full((nrow, NCHAN), w_i)
    img = core_wgridder.fits_image(
        uvw, freqs, ones, wts, NPIX, NPIX, CELL, epsilon=1e-9
    )
    fmaj, fmin, npx = psf_fwhm_pixels(img["psf"])
    b = round(fmaj)
    scales = [0, 2 * b, 4 * b, 8 * b, 16 * b]
    beam_arcsec = fmaj * CELL
    timings["psf_s"] = time.perf_counter() - t

    comps, sources = make_sky(beam_arcsec)
    t = time.perf_counter()
    cube = truth_cube(comps, freqs)
    timings["truth_cube_s"] = time.perf_counter() - t

    # orientation and the DFT check of the point components
    t = time.perf_counter()
    best, orient = orientation_check(uvw, freqs[[0, -1]])
    sl, sm = best
    hdr = fits_header(freqs)
    point_comps = [c for c in comps if c["fwhm_maj"] == 0.0]
    lm = np.array(
        [
            [sl * pixel_lm(c["x"], c["y"])[0], sm * pixel_lm(c["x"], c["y"])[1]]
            for c in point_comps
        ]
    )
    radec = [pixel_radec(hdr, c["x"], c["y"]) for c in comps]
    lw, mw = sky.direction_cosines(
        [r[0] for r in radec], [r[1] for r in radec], RA0, DEC0
    )
    lm_all = np.array(
        [
            [sl * pixel_lm(c["x"], c["y"])[0], sm * pixel_lm(c["x"], c["y"])[1]]
            for c in comps
        ]
    )
    wcs_lm_err = float(np.abs(np.stack([lw, mw], 1) - lm_all).max())
    points_cube = truth_cube(point_comps, freqs)
    dft_err = []
    for c in range(NCHAN):
        vg = degrid(points_cube[c], uvw, freqs[c])
        vd = core.predict_components(
            uvw,
            freqs[c : c + 1],
            lm,
            np.zeros(len(point_comps), np.uint8),
            [p["flux"] for p in point_comps],
            [[p["alpha"]] for p in point_comps],
            [True] * len(point_comps),
            [NU0] * len(point_comps),
            np.zeros((len(point_comps), 3)),
        )
        total = sum(p["flux"] * (freqs[c] / NU0) ** p["alpha"] for p in point_comps)
        dft_err.append(float(np.abs(vg - vd).max() / total))
    del points_cube
    timings["checks_s"] = time.perf_counter() - t

    # prediction of the full truth, channel by channel
    t = time.perf_counter()
    model = np.empty((nrow, NCHAN), np.complex128)
    for c in range(NCHAN):
        model[:, c] = degrid(cube[c], uvw, freqs[c])[:, 0]
    timings["predict_s"] = time.perf_counter() - t

    # noise and the MS, block by block in row order
    t = time.perf_counter()
    rng = np.random.default_rng(NOISE_SEED)
    vis_i = np.empty((nrow, NCHAN), np.complex128)
    block = BLOCK_DUMPS * nbl

    def blocks():
        for start in range(0, nrow, block):
            n = min(block, nrow - start)
            noise = rng.standard_normal((n, NCHAN, 4, 2)) * sigma
            data = np.empty((n, NCHAN, 4), np.complex64)
            v = model[start : start + n]
            data[..., 0] = v + noise[..., 0, 0] + 1j * noise[..., 0, 1]
            data[..., 1] = noise[..., 1, 0] + 1j * noise[..., 1, 1]
            data[..., 2] = noise[..., 2, 0] + 1j * noise[..., 2, 1]
            data[..., 3] = v + noise[..., 3, 0] + 1j * noise[..., 3, 1]
            vis_i[start : start + n] = 0.5 * (
                data[..., 0].astype(np.complex128) + data[..., 3].astype(np.complex128)
            )
            yield start, data

    ms_path = out / "field.ms"
    column_hashes = write_ms(
        ms_path, names, xyz, diam, times, uvw, a1r, a2r, freqs, blocks(), sigma
    )
    timings["ms_write_s"] = time.perf_counter() - t

    # the exact noise of the MFS image, and the noise-only dirty image
    t = time.perf_counter()
    noise_i = vis_i - model
    nimg = core_wgridder.fits_image(
        uvw, freqs, noise_i, wts, NPIX, NPIX, CELL, epsilon=1e-9
    )
    noise_rms = float(np.sqrt(np.mean(nimg["dirty"] ** 2)))
    noise_rms_inner = float(np.sqrt(np.mean(nimg["dirty"][256:768, 256:768] ** 2)))
    timings["noise_image_s"] = time.perf_counter() - t

    # truth FITS, component lists, field.npz
    t = time.perf_counter()
    truth_mfs = cube.mean(0)
    write_fits64(out / "truth-mfs.fits", truth_mfs, hdr)
    hcube = dict(hdr)
    hcube.update({"CRPIX3": 1.0, "CRVAL3": float(freqs[0]), "CDELT3": CHANW})
    write_fits64(out / "truth-cube.fits", cube[np.newaxis], hcube)
    for comp, (ra, dec) in zip(comps, radec, strict=True):
        comp["ra"], comp["dec"] = ra, dec
        comp["l"], comp["m"] = (
            sl * pixel_lm(comp["x"], comp["y"])[0],
            sm * pixel_lm(comp["x"], comp["y"])[1],
        )
    srcs = [
        sky.Source(
            name=c["name"],
            ra=c["ra"],
            dec=c["dec"],
            i=c["flux"],
            freq0=NU0,
            spi=(c["alpha"],),
            emaj=c["fwhm_maj"] * ARCSEC,
            emin=c["fwhm_min"] * ARCSEC,
            pa=c["pa"],
        )
        for c in comps
    ]
    (out / "truth-wsclean.txt").write_text(sky.dumps_wsclean(srcs))
    truth = {
        "nu0_hz": NU0,
        "components": comps,
        "sources": sources,
        "note": "positions are FITS pixels (x, y; 0-based) of truth-mfs.fits; Gaussians sampled at pixel centres and normalised to their flux",
    }
    (out / "truth.json").write_text(json.dumps(truth, indent=1))
    np.savez(
        out / "field.npz",
        uvw=uvw,
        freqs=freqs,
        vis_i=vis_i,
        model_vis=model,
        weight_i=np.float64(w_i),
        truth_cube=cube,
        psf_mfs=img["psf"],
    )
    timings["outputs_s"] = time.perf_counter() - t

    t = time.perf_counter()
    ms_files, ms_digest = tree_hashes(ms_path)
    files = {
        name: sha256_file(out / name)
        for name in (
            "truth-mfs.fits",
            "truth-cube.fits",
            "truth.json",
            "truth-wsclean.txt",
            "field.npz",
        )
    }
    timings["hash_s"] = time.perf_counter() - t
    timings["total_s"] = time.perf_counter() - t0

    record = {
        "settings": {
            "phase_centre_rad": [RA0, DEC0],
            "mjd_day": MJD_DAY,
            "ndump": NDUMP,
            "dump_s": DUMP,
            "nchan": NCHAN,
            "chan0_hz": CHAN0,
            "chan_width_hz": CHANW,
            "nu0_hz": NU0,
            "npix": NPIX,
            "cell_arcsec": CELL,
            "radius_px": RADIUS,
            "sefd_jy": SEFD,
            "sky_seed": SKY_SEED,
            "noise_seed": NOISE_SEED,
            "eps_predict": EPS_PREDICT,
            "uvw_convention": "uvw(ANTENNA1) - uvw(ANTENNA2), TMS eq. 4.1 with the IAU 1982 GMST",
        },
        "geometry": {
            "nant": len(names),
            "nbaseline": nbl,
            "nrow": nrow,
            "longitude_deg": math.degrees(lon),
            "latitude_deg": math.degrees(lat),
            "hour_angle_h": [
                float(np.degrees(local_ha[0]) / 15),
                float(np.degrees(local_ha[-1]) / 15),
            ],
            "elevation_deg": [float(elevation.min()), float(elevation.max())],
            "time_mjd_s": [float(times[0]), float(times[-1])],
            "max_uvw_m": float(np.abs(uvw).max()),
            "freqs_hz": freqs.tolist(),
        },
        "noise": {
            "sigma_corr_jy": sigma,
            "sigma_stokes_i_jy": sigma_i,
            "weight_stokes_i": w_i,
            "sigma_img_channel_jy": sigma_img_chan,
            "sigma_img_mfs_jy": sigma_img,
            "threshold_3sigma_jy": 3 * sigma_img,
            "noise_only_mfs_dirty_rms_jy": noise_rms,
            "noise_only_mfs_dirty_rms_inner_jy": noise_rms_inner,
        },
        "psf": {
            "fwhm_major_px": fmaj,
            "fwhm_minor_px": fmin,
            "halfmax_pixels": npx,
            "beam_fwhm_arcsec": beam_arcsec,
            "b_px": b,
            "multiscale_scales_px": scales,
        },
        "checks": {
            "orientation_lm_sign": [sl, sm],
            "orientation_maxabs": orient,
            "dft_point_check_max_rel": max(dft_err),
            "dft_point_check_per_channel": dft_err,
            "wcs_lm_max_abs_err": wcs_lm_err,
        },
        "truth": {
            "components": len(comps),
            "sources": len(sources),
            "total_flux_nu0_jy": float(sum(c["flux"] for c in comps)),
            "total_flux_mfs_jy": float(truth_mfs.sum()),
            "truth_mfs_peak_jy_per_px": float(truth_mfs.max()),
        },
        "hashes": {
            "ms_digest": ms_digest,
            "ms_files": ms_files,
            "files": files,
            "columns": column_hashes,
            "vis_i": sha256_bytes(vis_i),
            "truth_cube": sha256_bytes(cube),
        },
        "timings": timings,
        "peak_rss_mb": rusage.peak_rss_bytes() / 2**20,
    }
    (out / "field.json").write_text(json.dumps(record, indent=1))
    print(
        json.dumps(
            {k: record[k] for k in ("noise", "psf", "checks", "truth", "timings")},
            indent=1,
        )
    )


if __name__ == "__main__":
    main(sys.argv[1])
