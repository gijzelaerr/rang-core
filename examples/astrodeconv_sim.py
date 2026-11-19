"""ASTRODECONV2019 regenerated with rang (route b), DL4b step 0.

Specification: research/dl4b-astrodeconv.md (frozen at 0b128ddb).

    python examples/astrodeconv_sim.py split OUT
    python examples/astrodeconv_sim.py identity SPIEL_DIR OUT_JSON
    python examples/astrodeconv_sim.py run OUT --workers N [--shards A-B] [--pilot]
    python examples/astrodeconv_sim.py manifest OUT
    python examples/astrodeconv_sim.py pngs OUT PNG_DIR

The draws are a port of spiel's `steps/randomize.cwl` and `steps/skymodel.cwl`
(github.com/gijzelaerr/spiel, c4a8e315, MIT), kept in spiel's order under
numpy's legacy global RandomState. The truth is the sky-model text as spiel
wrote it (rounded), predicted exactly with the core DFT, written to an MS
by the core writer in /dev/shm and imaged by WSClean.
"""

import os

for _v in ("RAYON_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

# -- frozen specification (note section 1) -----------------------------------

FLUX_SETS = (10, 100, 1000)
SEEDS = range(3000)
SHARD_SEEDS = 10
NSHARD = len(SEEDS) // SHARD_SEEDS
JOB = {
    "nant": 16,
    "dtime": 10,
    "freq0": 1049833007.8125,
    "ra": 63.36,
    "dec_min": -55,
    "dec_max": -65,
    "synthesis_min": 7.5,
    "synthesis_max": 8,
    "dfreq_min": 200e6,
    "dfreq_max": 300e6,
    "nsrc": 100,
    "fov": 1,
    "pb_fwhm": 0.25,
    "sefd": 520,
}
NPIX, NPIX_BIG, CELL_ASEC = 256, 512, 1.6
MJD_DAY = 61120.0  # 2026-03-21 0h UTC (note 1.2)
NOISE_ROOT = 20261119
SPLIT_SEED = 20261119
WSCLEAN = os.environ.get("ASTRODECONV_WSCLEAN", "wsclean")
TIMEOUT_S = 900
PRODUCTS = (
    "dirty",
    "truth",
    "model_a",
    "residual_a",
    "image_a",
    "model_b",
    "residual_b",
    "image_b",
)
# spiel's data/MeerKAT16_ANTENNAS (ITRF, m), read with rang's table reader
SPIEL_ANTENNAS = (
    ("m000", 5109224.2440815, 2006790.3296817124, -3239100.601853014),
    ("m002", 5109224.943710827, 2006764.9807025143, -3239115.1928513832),
    ("m005", 5109222.728014064, 2006688.920476567, -3239165.938258335),
    ("m011", 5109122.918980513, 2006849.6678755488, -3239225.879103076),
    ("m012", 5109094.976656865, 2006898.8629206284, -3239239.9432084416),
    ("m018", 5109164.95329747, 2006889.5156141303, -3239134.2333439165),
    ("m020", 5109142.86621357, 2006871.4695822771, -3239180.649435223),
    ("m042", 5109233.0930122845, 2006414.0631003045, -3239318.0776903145),
    ("m049", 5110840.935829126, 2003560.0833854747, -3238544.1275997483),
    ("m057", 5110746.279857638, 2007713.6579817033, -3236109.834689674),
    ("m058", 5109561.316727074, 2009946.0924032007, -3236606.062809408),
    ("m059", 5108335.204937152, 2010410.6283685728, -3238271.543744482),
    ("m060", 5107206.614034378, 2009680.71443666, -3240512.429427901),
    ("m061", 5108231.263887399, 2006391.5318148837, -3240926.7338583376),
    ("m062", 5108666.756191877, 2005032.436432919, -3241081.698018931),
    ("m063", 5109701.398386069, 2003312.6840800678, -3240508.7211381607),
)


# -- the port of spiel's draws (note 1.1) -------------------------------------


def randomize(seed, flux):
    """steps/randomize.cwl, line for line."""
    from numpy import random

    random.seed(seed)
    dec = random.uniform(JOB["dec_min"], JOB["dec_max"])
    synthesis = random.uniform(JOB["synthesis_min"], JOB["synthesis_max"])
    dfreq = int(random.uniform(JOB["dfreq_min"], JOB["dfreq_max"]))
    flux_scale = random.uniform(flux, flux)
    return {
        "dec": dec,
        "synthesis": synthesis,
        "dfreq": dfreq,
        "flux_scale": flux_scale,
    }


def skymodel_text(seed, params):
    """steps/skymodel.cwl, line for line; returns skymodel.txt's text."""
    from numpy import random, sqrt

    ra, dec, nsrc = JOB["ra"], params["dec"], JOB["nsrc"]
    pb_fwhm, freq0 = JOB["pb_fwhm"], JOB["freq0"]
    sefd, dtime, dfreq, nant = JOB["sefd"], JOB["dtime"], params["dfreq"], JOB["nant"]
    Srms = sefd / sqrt(2 * dtime * dfreq * (nant * (nant - 1)) / 2)
    noise = sqrt(Srms * 2)
    random.seed(seed)
    fluxes = random.pareto(8, nsrc) * noise * params["flux_scale"]
    ras = ra - random.randn(nsrc) * pb_fwhm / 2
    decs = dec - random.randn(nsrc) * pb_fwhm / 2
    spi = -0.7 + random.randn(nsrc) * 0.01
    out = ["#format: name ra_d dec_d i freq0 spi\n"]
    for i in range(nsrc):
        out.append(
            f"src{i:04d} {ras[i]:.5g} {decs[i]:.5g} {fluxes[i]:.3g} {freq0:.5g} {spi[i]:.3f}\n"
        )
    return "".join(out)


def parse_skymodel(text):
    """(ra_deg, dec_deg, I, ref_freq, spi) arrays of the sky-model text."""
    rows = [ln.split() for ln in text.splitlines() if ln and not ln.startswith("#")]
    a = np.array([[float(x) for x in r[1:]] for r in rows])
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4]


# -- the identity check (note section 2) -------------------------------------


def js(v):
    """A CWL parameter reference as JavaScript renders the number."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return repr(v)


def spiel_snippet(cwl_path, values):
    import yaml

    doc = yaml.safe_load(Path(cwl_path).read_text())
    src = next(a["valueFrom"] for a in doc["arguments"] if a.get("prefix") == "-c")
    src = re.sub(r"\$\(inputs\.(\w+)\)", lambda m: js(values[m.group(1)]), src)
    return src.replace("\\\\", "\\").replace("xrange", "range")


def run_snippet(src, python):
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run(
            [python, "-I", "-c", src], cwd=d, capture_output=True, text=True, check=True
        )
        p = Path(d) / "skymodel.txt"
        return r.stdout, (p.read_text() if p.exists() else None)


def identity(spiel_dir, out_json, python=sys.executable, cases=None):
    spiel_dir = Path(spiel_dir)
    cases = cases or [(s, f) for s in (0, 1, 2999) for f in FLUX_SETS]
    rows, ok = [], True
    for s, f in cases:
        rv = dict(JOB, random_seed=s, flux_scale_min=float(f), flux_scale_max=float(f))
        out, _ = run_snippet(
            spiel_snippet(spiel_dir / "steps/randomize.cwl", rv), python
        )
        theirs = json.loads(out)
        mine = randomize(s, f)
        same_r = all(float(theirs[k]) == float(mine[k]) for k in mine)
        sv = dict(JOB, seed=s, dec=theirs["dec"], dfreq=theirs["dfreq"])
        sv["flux_scale"] = theirs["flux_scale"]
        _, text = run_snippet(
            spiel_snippet(spiel_dir / "steps/skymodel.cwl", sv), python
        )
        mine_text = skymodel_text(s, mine)
        same_t = text == mine_text
        ok &= same_r and same_t
        rows.append(
            {
                "seed": s,
                "flux": f,
                "randomize_equal": same_r,
                "skymodel_equal": same_t,
                "skymodel_sha256": hashlib.sha256(mine_text.encode()).hexdigest(),
                "spiel_sha256": hashlib.sha256((text or "").encode()).hexdigest(),
                "params": mine,
            }
        )
    ver = subprocess.run(
        [
            python,
            "-I",
            "-c",
            "import numpy,sys;print(numpy.__version__, sys.version.split()[0])",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    rec = {
        "pass": bool(ok),
        "spiel_python": python,
        "spiel_numpy": ver[0],
        "spiel_python_version": ver[1],
        "port_numpy": np.__version__,
        "cases": rows,
    }
    Path(out_json).write_text(json.dumps(rec, indent=1))
    print(
        f"identity: {'PASS' if ok else 'FAIL'} ({len(rows)} cases, spiel numpy {ver[0]})"
    )
    return ok


# -- the split (note section 4) ----------------------------------------------


def split_of():
    perm = np.random.default_rng(SPLIT_SEED).permutation(len(SEEDS))
    out = {}
    for i, s in enumerate(perm):
        out[int(s)] = "train" if i < 2820 else ("validation" if i < 2910 else "test")
    return out


def write_split(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    sp = split_of()
    text = "seed,split\n" + "".join(f"{s},{sp[s]}\n" for s in sorted(sp))
    (out / "split.csv").write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    print(f"split.csv sha256 {digest}")
    return digest


def published(seed, flux):
    return (
        {10: 0, 100: 1000, 1000: 2000}[flux]
        <= seed
        < {10: 0, 100: 1000, 1000: 2000}[flux] + 1000
    )


# -- observation (note 1.2) --------------------------------------------------


def gmst82(mjd_ut1):
    jd = np.asarray(mjd_ut1, float) + 2400000.5
    t = (jd - 2451545.0) / 36525.0
    seconds = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * t
        + 0.093104 * t**2
        - 6.2e-6 * t**3
    )
    return np.mod(seconds, 86400.0) / 86400.0 * 2 * math.pi


def track(xyz, ra0, dec0, ndump, dtime):
    """Dump-centre times (MJD s), uvw (time, ant, 3), elevation (deg), as
    examples/simulate_df5_field.py, centred on transit."""
    centre = xyz.mean(0)
    lon = math.atan2(centre[1], centre[0])
    lat = math.atan2(centre[2], math.hypot(centre[0], centre[1]))
    grid = MJD_DAY + np.arange(0, 86400.0, 1.0) / 86400.0
    ha = np.angle(np.exp(1j * (gmst82(grid) + lon - ra0)))
    k = int(np.flatnonzero((ha[:-1] < 0) & (ha[1:] >= 0))[0])
    t_tr = (k + (-ha[k]) / (ha[k + 1] - ha[k])) / 86400.0 + MJD_DAY
    offsets = (np.arange(ndump) - (ndump - 1) / 2) * dtime
    mjd = t_tr + offsets / 86400.0
    h_g = gmst82(mjd) - ra0
    local = np.angle(np.exp(1j * (h_g + lon)))
    sd, cd = math.sin(dec0), math.cos(dec0)
    sh, ch = np.sin(h_g)[:, None], np.cos(h_g)[:, None]
    x, y, z = xyz[None, :, 0], xyz[None, :, 1], xyz[None, :, 2]
    u = sh * x + ch * y
    v = -sd * ch * x + sd * sh * y + cd * z
    w = cd * ch * x - cd * sh * y + sd * z
    el = np.degrees(np.arcsin(math.sin(lat) * sd + math.cos(lat) * cd * np.cos(local)))
    return mjd * 86400.0, np.stack([u, v, w], -1), el


def write_ms(path, xyz, names, times, uvw, a1, a2, columns, sigma, freq, width):
    from rang import core_ms_write as w

    nrow = len(a1)
    nbl = nrow // len(times)
    desc = [w.makearrcoldesc(c, 0j, valuetype="complex", shape=[1, 4]) for c in columns]
    desc += [
        w.makearrcoldesc("WEIGHT_SPECTRUM", 0.0, valuetype="float", shape=[1, 4]),
        w.makearrcoldesc("SIGMA_SPECTRUM", 0.0, valuetype="float", shape=[1, 4]),
        w.makearrcoldesc("FLAG", False, shape=[1, 4]),
        w.makearrcoldesc("WEIGHT", 0.0, valuetype="float", shape=[4]),
        w.makearrcoldesc("SIGMA", 0.0, valuetype="float", shape=[4]),
    ]
    # fixed shapes and tiled storage (as examples/c5_selfcal_sim.py): the
    # indirect StandardStMan arrays made WSClean's read take 22 s per call
    tiled = {c: [c] for c in columns}
    tiled["TiledSpectrum"] = ["WEIGHT_SPECTRUM", "SIGMA_SPECTRUM"]
    tiled["TiledFlag"] = ["FLAG"]
    dminfo = {
        f"*{i + 1}": {
            "TYPE": "TiledColumnStMan",
            "NAME": f"Tiled{name}" if name in columns else name,
            "COLUMNS": cols,
            "SPEC": {
                "DEFAULTTILESHAPE": [4, 1, 8192 * (8 if name == "TiledFlag" else 1)]
            },
        }
        for i, (name, cols) in enumerate(tiled.items())
    }
    ms = w.default_ms(str(path), desc, dminfo)
    ms.addrows(nrow)
    t_rows = np.repeat(times, nbl)
    for name, value in (
        ("TIME", t_rows),
        ("TIME_CENTROID", t_rows),
        ("INTERVAL", np.full(nrow, float(JOB["dtime"]))),
        ("EXPOSURE", np.full(nrow, float(JOB["dtime"]))),
        ("ANTENNA1", a1),
        ("ANTENNA2", a2),
        ("UVW", uvw),
        ("SCAN_NUMBER", np.ones(nrow, np.int32)),
        ("FLAG_ROW", np.zeros(nrow, bool)),
        ("WEIGHT", np.full((nrow, 4), 1 / sigma**2, np.float32)),
        ("SIGMA", np.full((nrow, 4), sigma, np.float32)),
        ("WEIGHT_SPECTRUM", np.full((nrow, 1, 4), 1 / sigma**2, np.float32)),
        ("SIGMA_SPECTRUM", np.full((nrow, 1, 4), sigma, np.float32)),
        ("FLAG", np.zeros((nrow, 1, 4), bool)),
    ):
        ms.putcol(name, value)
    for c, data in columns.items():
        ms.putcol(c, data)
    ms.close()
    nant = len(names)
    with w.open_table(f"{path}/ANTENNA", readonly=False) as t:
        t.addrows(nant)
        t.putcol("NAME", names)
        t.putcol("STATION", names)
        t.putcol("TYPE", ["GROUND-BASED"] * nant)
        t.putcol("MOUNT", ["ALT-AZ"] * nant)
        t.putcol("DISH_DIAMETER", np.full(nant, 13.5))
        t.putcol("POSITION", xyz)
        t.putcol("OFFSET", np.zeros((nant, 3)))
        t.putcol("FLAG_ROW", np.zeros(nant, bool))
    with w.open_table(f"{path}/SPECTRAL_WINDOW", readonly=False) as t:
        t.addrows(1)
        t.putcell("CHAN_FREQ", 0, np.array([freq]))
        for col in ("CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"):
            t.putcell(col, 0, np.array([width]))
        t.putcell("NUM_CHAN", 0, 1)
        t.putcell("REF_FREQUENCY", 0, freq)
        t.putcell("TOTAL_BANDWIDTH", 0, width)
        t.putcell("MEAS_FREQ_REF", 0, 5)
        t.putcell("NAME", 0, "00")
        t.putcell("NET_SIDEBAND", 0, 1)
    with w.open_table(f"{path}/POLARIZATION", readonly=False) as t:
        t.addrows(1)
        t.putcell("NUM_CORR", 0, 4)
        t.putcell("CORR_TYPE", 0, np.array([9, 10, 11, 12], np.int32))
        t.putcell(
            "CORR_PRODUCT", 0, np.array([[0, 0], [0, 1], [1, 0], [1, 1]], np.int32)
        )
    with w.open_table(f"{path}/DATA_DESCRIPTION", readonly=False) as t:
        t.addrows(1)
        t.putcell("SPECTRAL_WINDOW_ID", 0, 0)
        t.putcell("POLARIZATION_ID", 0, 0)
    with w.open_table(f"{path}/FIELD", readonly=False) as t:
        t.addrows(1)
        direction = np.array([[math.radians(JOB["ra"]), FIELD_DEC[0]]])
        for col in ("PHASE_DIR", "DELAY_DIR", "REFERENCE_DIR"):
            t.putcell(col, 0, direction)
        t.putcell("NAME", 0, "00")
        t.putcell("TIME", 0, float(times[0]))
    with w.open_table(f"{path}/OBSERVATION", readonly=False) as t:
        t.addrows(1)
        t.putcell("TELESCOPE_NAME", 0, "MeerKAT")
        dt = float(JOB["dtime"])
        t.putcell("TIME_RANGE", 0, np.array([times[0] - dt / 2, times[-1] + dt / 2]))
        t.putcell("OBSERVER", 0, "rang ASTRODECONV2019 regeneration")
        t.putcell("PROJECT", 0, "DL4b")
    with w.open_table(f"{path}/FEED", readonly=False) as t:
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


FIELD_DEC = [0.0]  # set per seed before write_ms (one process, one seed at a time)


def predict(text, uvw_rows, ra0, dec0):
    """Stokes I visibilities (row,) of the sky-model text at freq0 (note 1.2)."""
    from rang import core
    from rang.formats import sky

    ra, dec, flux, ref, spi = parse_skymodel(text)
    freq0 = JOB["freq0"]
    l, m = sky.direction_cosines(np.radians(ra), np.radians(dec), ra0, dec0)
    eff = flux * (freq0 / ref) ** spi
    n = len(flux)
    vis = core.predict_components(
        uvw_rows,
        np.array([freq0]),
        np.stack([l, m], 1),
        np.zeros(n, np.uint8),
        eff,
        np.zeros((n, 1)),
        [True] * n,
        np.full(n, freq0),
        np.zeros((n, 3)),
    )
    return vis[:, 0]


def outside_only(text, uvw_rows, ra0, dec0):
    """Pilot diagnostic: noise-free XX = YY of the sources outside the 256²
    image (WSClean's grid: centre pixel n/2, SIN, 1.6 arcsec), flux10."""
    from rang.formats import sky

    ra, dec, *_ = parse_skymodel(text)
    l, m = sky.direction_cosines(np.radians(ra), np.radians(dec), ra0, dec0)
    cell = math.radians(CELL_ASEC / 3600)
    x, y = NPIX // 2 - l / cell, NPIX // 2 + m / cell
    keep = ~((np.floor(x + 0.5) >= 0) & (np.floor(x + 0.5) < NPIX))
    keep |= ~((np.floor(y + 0.5) >= 0) & (np.floor(y + 0.5) < NPIX))
    lines = text.splitlines(keepends=True)
    sub = lines[0] + "".join(ln for ln, k in zip(lines[1:], keep) if k)
    vis = predict(sub, uvw_rows, ra0, dec0)
    data = np.zeros((len(vis), 1, 4), np.complex64)
    data[:, 0, 0] = data[:, 0, 3] = vis
    return data


def noisy(vis, sigma, seed, flux):
    rng = np.random.Generator(
        np.random.PCG64(np.random.SeedSequence([NOISE_ROOT, seed, flux]))
    )
    noise = rng.standard_normal((len(vis), 1, 4, 2)) * sigma
    data = (noise[..., 0] + 1j * noise[..., 1]).astype(np.complex64)
    data[:, 0, 0] += vis.astype(np.complex64)
    data[:, 0, 3] += vis.astype(np.complex64)
    return data


# -- imaging (note 1.3) and truth (note 1.4) ---------------------------------


def wsclean(args, log_path, cwd):
    t = time.perf_counter()
    try:
        with open(log_path, "w") as log:
            r = subprocess.run(
                [WSCLEAN, "-j", "1", *args],
                check=False,
                cwd=cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=TIMEOUT_S,
            )
        rc, timeout = r.returncode, False
    except subprocess.TimeoutExpired:
        rc, timeout = None, True
    text = Path(log_path).read_text(errors="replace")
    iters = [int(x) for x in re.findall(r"Performed (\d+) iterations in total", text)]
    major = re.findall(r"(\d+) major iterations? (?:was|were) performed", text)
    return {
        "rc": rc,
        "timeout": timeout,
        "wall_s": time.perf_counter() - t,
        "iterations": max(iters or [0]),
        "major_cycles": int(major[-1]) if major else 0,
    }


def read_image(path):
    from astropy.io import fits

    with fits.open(path) as h:
        return np.asarray(h[0].data[0, 0], np.float32), h[0].header.copy()


def truth_image(text, header):
    """tigger-restore -b 0 --clear: nearest pixel by the image WCS, origin 0,
    half away from zero (Python 2 round), outside skipped, fluxes summed."""
    from astropy.wcs import WCS

    ra, dec, flux, _ref, spi = parse_skymodel(text)
    wcs = WCS(header).celestial
    x, y = wcs.wcs_world2pix(ra, dec, 0)
    xi = np.floor(np.asarray(x) + 0.5).astype(int)
    yi = np.floor(np.asarray(y) + 0.5).astype(int)
    inside = (xi >= 0) & (xi < NPIX) & (yi >= 0) & (yi < NPIX)
    img = np.zeros((NPIX, NPIX), np.float32)
    np.add.at(img, (yi[inside], xi[inside]), flux[inside].astype(np.float32))
    comps = np.stack([ra, dec, flux, spi, np.asarray(x), np.asarray(y), inside], 1)
    return img, comps, inside


def beam(header):
    return [float(header.get(k, float("nan"))) for k in ("BMAJ", "BMIN", "BPA")]


def field_sha(arrays):
    h = hashlib.sha256()
    for a in arrays:
        h.update(np.ascontiguousarray(a, np.float32).tobytes())
    return h.hexdigest()


def simulate_seed(seed, shm, pilot=False):
    """All products of one seed's three fields."""
    t0 = time.perf_counter()
    params = {f: randomize(seed, f) for f in FLUX_SETS}
    p = params[FLUX_SETS[0]]
    for f in FLUX_SETS:
        assert all(params[f][k] == p[k] for k in ("dec", "synthesis", "dfreq"))
    texts = {f: skymodel_text(seed, params[f]) for f in FLUX_SETS}
    ra0, dec0 = math.radians(JOB["ra"]), math.radians(p["dec"])
    FIELD_DEC[0] = dec0
    names = [a[0] for a in SPIEL_ANTENNAS]
    xyz = np.array([a[1:] for a in SPIEL_ANTENNAS])
    ndump = math.floor(p["synthesis"] * 3600 / JOB["dtime"])
    times, uvw, el = track(xyz, ra0, dec0, ndump, JOB["dtime"])
    a1, a2 = np.triu_indices(len(names), 1)
    nbl = len(a1)
    uvw_rows = (uvw[:, a2] - uvw[:, a1]).reshape(-1, 3)
    a1r, a2r = np.tile(a1, ndump).astype(np.int32), np.tile(a2, ndump).astype(np.int32)
    sigma = JOB["sefd"] / math.sqrt(2 * JOB["dtime"] * p["dfreq"])
    timing = {}
    t = time.perf_counter()
    columns = {}
    for f in FLUX_SETS:
        columns[f"DATA_F{f}"] = noisy(
            predict(texts[f], uvw_rows, ra0, dec0), sigma, seed, f
        )
    if pilot:
        columns["DATA_NOISE"] = noisy(np.zeros(len(uvw_rows)), sigma, seed, 0)
        columns["DATA_OUTSIDE"] = outside_only(texts[FLUX_SETS[0]], uvw_rows, ra0, dec0)
    timing["predict_noise_s"] = time.perf_counter() - t
    work = Path(tempfile.mkdtemp(prefix=f"s{seed:04d}-", dir=shm))
    try:
        t = time.perf_counter()
        ms = work / "field.ms"
        write_ms(
            ms,
            xyz,
            names,
            times,
            uvw_rows,
            a1r,
            a2r,
            columns,
            sigma,
            JOB["freq0"],
            float(p["dfreq"]),
        )
        del columns
        timing["ms_write_s"] = time.perf_counter() - t
        base = [
            "-size", str(NPIX), str(NPIX), "-scale", f"{CELL_ASEC}asec",
            "-weight", "uniform", "-niter", "100000000",
            "-auto-threshold", "0.125", "-auto-mask", "5",
            "-temp-dir", str(work), "-no-update-model-required", "-reorder",
        ]  # fmt: skip
        fields, runs = {}, {}
        psfs = {}
        for f in FLUX_SETS:
            col = f"DATA_F{f}"
            ra_ = wsclean(
                base
                + [
                    "-mgain",
                    "1.0",
                    "-make-psf",
                    "-data-column",
                    col,
                    "-name",
                    str(work / f"a{f}"),
                    str(ms),
                ],
                work / f"a{f}.log",
                work,
            )
            rb_ = wsclean(base + ["-mgain", "0.8", "-data-column", col, "-name", str(work / f"b{f}"), str(ms)], work / f"b{f}.log", work)  # fmt: skip
            runs[f] = {"a": ra_, "b": rb_}
            prod = {}
            hdr_a = hdr_b = None
            for tag, run in (("a", ra_), ("b", rb_)):
                for kind in ("model", "residual", "image"):
                    path = work / f"{tag}{f}-{kind}.fits"
                    if path.exists():
                        img, hdr = read_image(path)
                    else:
                        img, hdr = np.full((NPIX, NPIX), np.nan, np.float32), None
                    prod[f"{kind}_{tag}"] = img
                    if kind == "image":
                        if tag == "a":
                            hdr_a = hdr
                        else:
                            hdr_b = hdr
            dirty, hdr_d = read_image(work / f"a{f}-dirty.fits")
            prod["dirty"] = dirty
            psfs[f] = read_image(work / f"a{f}-psf.fits")[0]
            truth, comps, inside = truth_image(texts[f], hdr_d)
            prod["truth"] = truth
            fields[f] = {
                "prod": prod,
                "comps": comps,
                "n_inside": int(inside.sum()),
                "flux_inside": float(comps[inside, 2].sum()),
                "beam_a": beam(hdr_a) if hdr_a is not None else None,
                "beam_b": beam(hdr_b) if hdr_b is not None else None,
                "header": {
                    k: hdr_d[k]
                    for k in (
                        "CRVAL1",
                        "CRVAL2",
                        "CRPIX1",
                        "CRPIX2",
                        "CDELT1",
                        "CDELT2",
                        "CTYPE1",
                        "CTYPE2",
                    )
                },
            }
        noise_rms = outside_rms = None
        if pilot:
            wsclean(base + ["-niter", "0", "-data-column", "DATA_NOISE", "-name", str(work / "n"), str(ms)], work / "n.log", work)  # fmt: skip
            noise_rms = float(
                np.sqrt(np.mean(read_image(work / "n-dirty.fits")[0] ** 2))
            )
            wsclean(base + ["-niter", "0", "-data-column", "DATA_OUTSIDE", "-name", str(work / "o"), str(ms)], work / "o.log", work)  # fmt: skip
            outside_rms = float(
                np.sqrt(np.mean(read_image(work / "o-dirty.fits")[0] ** 2))
            )
        rp = wsclean(["-size", str(NPIX_BIG), str(NPIX_BIG), "-scale", f"{CELL_ASEC}asec", "-name", str(work / "bigpsf"), "-make-psf-only", "-data-column", "DATA_F10", "-temp-dir", str(work), "-reorder", str(ms)], work / "p.log", work)  # fmt: skip
        bigpsf = read_image(work / "bigpsf-psf.fits")[0]
        psf = psfs[FLUX_SETS[0]]
        psf_diff = max(float(np.abs(psfs[f] - psf).max()) for f in FLUX_SETS) / float(
            psf.max()
        )
        version = re.search(
            r"WSClean version ([^\n]+)", (work / "p.log").read_text(errors="replace")
        )
    finally:
        keep = os.environ.get("ASTRODECONV_KEEP_LOGS")
        if keep:
            dest = Path(keep) / f"s{seed:04d}"
            dest.mkdir(parents=True, exist_ok=True)
            for log in work.glob("*.log"):
                shutil.copy(log, dest / log.name)
        shutil.rmtree(work, ignore_errors=True)
    rec = {
        "seed": seed,
        "params": {k: p[k] for k in ("dec", "synthesis", "dfreq")},
        "ndump": ndump,
        "nrow": ndump * nbl,
        "sigma_vis": sigma,
        "min_elevation_deg": float(el.min()),
        "psf_max_rel_diff": psf_diff,
        "noise_only_rms": noise_rms,
        "outside_only_rms_f10": outside_rms,
        "bigpsf_run": rp,
        "wsclean_version": version.group(1).strip() if version else None,
        "timing": timing,
        "wall_s": time.perf_counter() - t0,
        "runs": runs,
        "sky_sha256": {
            f: hashlib.sha256(texts[f].encode()).hexdigest() for f in FLUX_SETS
        },
    }
    return rec, fields, psf, bigpsf


def run_shard(k, out, shm, pilot=False):
    out = Path(out)
    npz, js_, done = (out / f"shard-{k:03d}{e}" for e in (".npz", ".json", ".done"))
    if done.exists() and npz.exists() and done.read_text().split()[0] == sha_file(npz):
        return f"shard {k}: done, skipped"
    t0 = time.perf_counter()
    stacks = {p: [] for p in PRODUCTS}
    comps, psf_s, big_s, recs, frows = [], [], [], [], []
    split = split_of()
    for s in range(k * SHARD_SEEDS, (k + 1) * SHARD_SEEDS):
        rec, fields, psf, bigpsf = simulate_seed(s, shm, pilot)
        psf_s.append(psf)
        big_s.append(bigpsf)
        rec["psf_sha256"] = field_sha([psf, bigpsf])
        recs.append(rec)
        for f in FLUX_SETS:
            fd = fields[f]
            for p in PRODUCTS:
                stacks[p].append(fd["prod"][p])
            comps.append(fd["comps"])
            ra_, rb_ = rec["runs"][f]["a"], rec["runs"][f]["b"]
            frows.append(
                {
                    "field": f"s{s:04d}-f{f}",
                    "seed": s,
                    "flux": f,
                    "split": split[s],
                    "published": published(s, f),
                    "shard": k,
                    "index": len(frows),
                    **rec["params"],
                    "ndump": rec["ndump"],
                    "sigma_vis": rec["sigma_vis"],
                    "n_inside": fd["n_inside"],
                    "flux_inside": fd["flux_inside"],
                    "beam_a": fd["beam_a"],
                    "beam_b": fd["beam_b"],
                    "iter_a": ra_["iterations"],
                    "major_a": ra_["major_cycles"],
                    "wall_a": ra_["wall_s"],
                    "iter_b": rb_["iterations"],
                    "major_b": rb_["major_cycles"],
                    "wall_b": rb_["wall_s"],
                    "timeout": bool(ra_["timeout"] or rb_["timeout"]),
                    "rc_ok": ra_["rc"] == 0 and rb_["rc"] == 0,
                    "sha256": field_sha([fd["prod"][p] for p in PRODUCTS]),
                    "psf_sha256": rec["psf_sha256"],
                    "sky_sha256": rec["sky_sha256"][f],
                    "header": fd["header"],
                }
            )
    arrays = {p: np.stack(v) for p, v in stacks.items()}
    arrays["components"] = np.stack(comps)
    arrays["psf"] = np.stack(psf_s)
    arrays["bigpsf"] = np.stack(big_s)
    tmp = out / f"shard-{k:03d}.tmp.npz"
    np.savez(tmp, **arrays)
    os.replace(tmp, npz)
    meta = {
        "shard": k,
        "seeds": recs,
        "fields": frows,
        "wall_s": time.perf_counter() - t0,
    }
    js_.write_text(json.dumps(meta, indent=1, default=float))
    done.write_text(f"{sha_file(npz)}  {npz.name}\n")
    return f"shard {k}: {len(frows)} fields in {meta['wall_s']:.0f} s"


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _worker(args):
    k, out, shm, pilot = args
    try:
        return run_shard(k, out, shm, pilot)
    except Exception as e:  # noqa: BLE001 (recorded, the pool goes on)
        return f"shard {k}: FAILED {type(e).__name__}: {e}"


def run(out, workers, shards, shm, pilot):
    from multiprocessing import get_context

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(k, str(out), shm, pilot) for k in shards]
    with get_context("spawn").Pool(workers, maxtasksperchild=1) as pool:
        for msg in pool.imap_unordered(_worker, jobs):
            print(time.strftime("%H:%M:%S"), msg, flush=True)


def manifest(out):
    out = Path(out)
    rows = []
    for k in range(NSHARD):
        done = out / f"shard-{k:03d}.done"
        if not done.exists():
            continue
        meta = json.loads((out / f"shard-{k:03d}.json").read_text())
        for r in meta["fields"]:
            r = dict(r)
            r["shard_sha256"] = done.read_text().split()[0]
            for key in ("beam_a", "beam_b"):
                b = r.pop(key) or [float("nan")] * 3
                r[f"{key}_maj"], r[f"{key}_min"], r[f"{key}_pa"] = b
            r.pop("header")
            rows.append(r)
    rows.sort(key=lambda r: (r["seed"], r["flux"]))
    path = out / "manifest.csv"
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print(f"manifest: {len(rows)} fields, sha256 {sha_file(path)}")


def pngs(out, png_dir, shard=0, index=(2, 5, 8)):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = np.load(Path(out) / f"shard-{shard:03d}.npz")
    png_dir = Path(png_dir)
    png_dir.mkdir(parents=True, exist_ok=True)
    for i in index:
        fig, ax = plt.subplots(1, 5, figsize=(17, 3.6))
        s = shard * SHARD_SEEDS + i // 3
        for a, (name, img) in zip(
            ax,
            (
                ("dirty", d["dirty"][i]),
                ("psf", d["psf"][i // 3]),
                ("truth", d["truth"][i]),
                ("model_a", d["model_a"][i]),
                ("residual_b", d["residual_b"][i]),
            ),
        ):
            v = np.nanmax(np.abs(img)) or 1
            a.imshow(img, origin="lower", cmap="inferno" if name != "residual_b" else "RdBu_r",
                     vmin=0 if name in ("truth", "model_a") else -v, vmax=v)  # fmt: skip
            a.set_title(f"{name}")
            a.set_xticks([])
            a.set_yticks([])
        fig.suptitle(f"seed {s}, flux set {FLUX_SETS[i % 3]}")
        fig.tight_layout()
        fig.savefig(png_dir / f"s{s:04d}-f{FLUX_SETS[i % 3]}.png", dpi=70)
        plt.close(fig)


def pilot_check(out, shard=0):
    """Note section 6 (amendment 1): orientation, flux, PSF, residual, time."""
    out = Path(out)
    d = np.load(out / f"shard-{shard:03d}.npz")
    meta = json.loads((out / f"shard-{shard:03d}.json").read_text())
    rows, seeds = meta["fields"], {r["seed"]: r for r in meta["seeds"]}
    res = {"orientation": [], "flux": [], "psf": [], "residual": [], "timeouts": 0}
    for r in rows:
        i, s, f = r["index"], r["seed"], r["flux"]
        res["timeouts"] += int(r["timeout"])
        comps = d["components"][i]
        if f == 1000:
            inside = comps[:, 6] > 0
            if inside.any():
                k = int(np.flatnonzero(inside)[np.argmax(comps[inside, 2])])
                x, y = (int(np.floor(c + 0.5)) for c in comps[k, 4:6])
                y0, x0 = max(y - 5, 0), max(x - 5, 0)
                box = d["dirty"][i][y0 : y + 6, x0 : x + 6]
                py, px = np.unravel_index(np.argmax(box), box.shape)
                off = max(abs(py + y0 - y), abs(px + x0 - x))
                res["orientation"].append(
                    {"seed": s, "offset_px": int(off), "pass": bool(off <= 1)}
                )
                ra, dec = np.radians(comps[:, 0]), np.radians(comps[:, 1])
                sep = (
                    np.degrees(
                        np.arccos(
                            np.clip(
                                np.sin(dec[k]) * np.sin(dec)
                                + np.cos(dec[k]) * np.cos(dec) * np.cos(ra - ra[k]),
                                -1,
                                1,
                            )
                        )
                    )
                    * 3600
                )
                sep[k] = np.inf
                if sep.min() > 5:
                    m = d["model_b"][i][
                        max(y - 1, 0) : y + 2, max(x - 1, 0) : x + 2
                    ].sum()
                    rel = float(m / comps[k, 2] - 1)
                    res["flux"].append(
                        {
                            "seed": s,
                            "I": float(comps[k, 2]),
                            "rel_err": rel,
                            "pass": abs(rel) <= 0.10,
                        }
                    )
        if f == 10:
            sd = seeds[s]
            res["psf"].append(
                {
                    "seed": s,
                    "max_rel_diff": sd["psf_max_rel_diff"],
                    "pass": sd["psf_max_rel_diff"] < 1e-6,
                }
            )
            if sd.get("noise_only_rms") is not None:
                rms = float(np.sqrt(np.nanmean(d["residual_b"][i] ** 2)))
                ref = math.hypot(sd["noise_only_rms"], sd["outside_only_rms_f10"])
                res["residual"].append(
                    {"seed": s, "residual_b_rms": rms, "noise_rms": sd["noise_only_rms"],
                     "outside_rms": sd["outside_only_rms_f10"], "ratio": rms / ref, "pass": bool(abs(rms / ref - 1) <= 0.20)}
                )  # fmt: skip
    res["pass"] = {
        k: all(x["pass"] for x in res[k]) and bool(res[k])
        for k in ("orientation", "flux", "psf", "residual")
    }
    res["pass"]["time"] = res["timeouts"] == 0
    (out / f"pilot-check-{shard:03d}.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["pass"]), f"timeouts {res['timeouts']}")
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("split")
    p.add_argument("out")
    p = sub.add_parser("identity")
    p.add_argument("spiel_dir")
    p.add_argument("out_json")
    p.add_argument("--python", default=sys.executable)
    p = sub.add_parser("run")
    p.add_argument("out")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--shards", default=f"0-{NSHARD - 1}")
    p.add_argument("--shm", default="/dev/shm")
    p.add_argument("--pilot", action="store_true")
    p = sub.add_parser("manifest")
    p.add_argument("out")
    p = sub.add_parser("pilot-check")
    p.add_argument("out")
    p = sub.add_parser("pngs")
    p.add_argument("out")
    p.add_argument("png_dir")
    a = ap.parse_args()
    if a.cmd == "split":
        write_split(a.out)
    elif a.cmd == "identity":
        sys.exit(0 if identity(a.spiel_dir, a.out_json, a.python) else 1)
    elif a.cmd == "run":
        lo, hi = (int(x) for x in a.shards.split("-"))
        run(a.out, a.workers, range(lo, hi + 1), a.shm, a.pilot)
    elif a.cmd == "manifest":
        manifest(a.out)
    elif a.cmd == "pilot-check":
        pilot_check(a.out)
    elif a.cmd == "pngs":
        pngs(a.out, a.png_dir)


if __name__ == "__main__":
    main()
