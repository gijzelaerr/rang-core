# SPDX-License-Identifier: MIT
"""DD1 simulation (research/dd1-facet-gains.md, section 4).

    python tools/oracles/dd1/sim.py OUTDIR

Writes OUTDIR/dd1.ms (DATA noisy, DATA_NF noiseless twin, MODEL_D0..D3 one
per facet direction, WEIGHT_SPECTRUM = 1/sigma^2), OUTDIR/truth.npz (the
truth gains per block, antenna, direction and hand; the sky and its facet
assignment) and OUTDIR/provenance.json. Seeds 1501 (sky), 1502 (gains),
1503 (noise), frozen in the note.
"""

import json
import math
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from rang import core
from rang import core_ms_write as tables
from rang import simtruth as st
from rang import simtruth_ms as stms

SEEDS = {"sky": 1501, "gains": 1502, "noise": 1503}
RA0, DEC0 = 250.0, -60.0  # degrees, near ESO137
NTIME, DT, BLOCK = 48, 8.0, 4
NCHAN, CHAN_WIDTH, F0 = 16, 1.0e6, 1292.5e6
SIGMA = 0.11  # Jy per real/imaginary part per correlation
# Facet centres (degrees from the phase centre) and their central fluxes.
CENTRES = [(0.0, 0.0), (0.6, 0.3), (-0.5, 0.5), (0.0, -0.7)]
CENTRE_FLUX = [1.0, 2.0, 0.8, 0.4]
NFAINT, FAINT_RANGE, BOX = 24, (0.01, 0.1), 1.6
ALPHA, NU_REF = -0.7, 1.3e9
AMP_SCALE, PHASE_SCALE = 0.1, 0.5


def sky():
    rng = np.random.default_rng(SEEDS["sky"])
    comps = [(l, m, f) for (l, m), f in zip(CENTRES, CENTRE_FLUX, strict=True)]
    for _ in range(NFAINT):
        l, m = rng.uniform(-BOX / 2, BOX / 2, 2)
        comps.append((float(l), float(m), float(rng.uniform(*FAINT_RANGE))))
    lm = np.array([[c[0], c[1]] for c in comps]) * st.DEG
    flux = np.array([c[2] for c in comps])
    centres = np.array(CENTRES) * st.DEG
    facet = np.argmin(((lm[:, None, :] - centres[None]) ** 2).sum(-1), axis=1)
    return lm, flux, facet


def truth_gains(nant, ndir, nblock):
    """(nblock, nant, ndir, 2) complex: exp(0.1 a + 0.5 i b), with a and b a
    random-phase sinusoid plus an offset per (antenna, direction, hand)."""
    rng = np.random.default_rng(SEEDS["gains"])
    t = (np.arange(nblock) + 0.5) / nblock
    shape = (nant, ndir, 2)

    def smooth():
        offset = rng.normal(0, 1, shape)
        amp = rng.uniform(0.2, 1.0, shape)
        period = rng.uniform(0.5, 2.0, shape)
        phase = rng.uniform(0, 2 * math.pi, shape)
        return offset[None] + amp[None] * np.sin(
            2 * math.pi * t[:, None, None, None] / period[None] + phase[None]
        )

    a, b = smooth(), smooth()
    return np.exp(AMP_SCALE * a + 1j * PHASE_SCALE * b)


def geometry(xyz, times):
    """Per-antenna UVW (ntime, nant, 3) towards (RA0, DEC0), as A1's."""
    from astropy import units
    from astropy.coordinates import EarthLocation
    from astropy.time import Time
    from astropy.utils import iers

    iers.conf.auto_download = False
    when = Time(times / st.MJD_S, format="mjd", scale="utc")
    pos = np.empty((len(times), len(xyz), 3))
    for a in range(len(xyz)):
        loc = EarthLocation.from_geocentric(*xyz[a], unit=units.m)
        p, _ = loc.get_gcrs_posvel(when)
        pos[:, a] = p.xyz.to_value(units.m).T
    centre = pos.mean(axis=1, keepdims=True)
    basis = st._direction(RA0 * st.DEG, DEC0 * st.DEG)
    return np.einsum("tak,jk->taj", pos - centre, basis)


def predict(uvw, nu, lm, flux):
    n = len(flux)
    return core.predict_components(
        uvw,
        nu,
        lm,
        np.zeros(n, np.int64),
        flux,
        np.full((n, 1), ALPHA),
        np.ones(n, bool),
        np.full(n, NU_REF),
        np.zeros((n, 3)),
    )


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    xyz, diameter, names = st.antenna_table()
    nant = len(names)
    a1, a2 = np.triu_indices(nant, 1)
    nbl = len(a1)
    from astropy.time import Time

    t0 = Time(st.START_UTC, scale="utc").mjd * st.MJD_S
    times = t0 + DT * (np.arange(NTIME) + 0.5)
    nu = F0 + CHAN_WIDTH * np.arange(NCHAN)
    uvw_ant = geometry(xyz, times)
    tindex = np.repeat(np.arange(NTIME), nbl)
    ra1, ra2 = np.tile(a1, NTIME), np.tile(a2, NTIME)
    uvw = uvw_ant[tindex, ra1] - uvw_ant[tindex, ra2]
    nrow = len(tindex)
    lm, flux, facet = sky()
    ndir = len(CENTRES)
    nblock = NTIME // BLOCK
    g = truth_gains(nant, ndir, nblock)
    block = tindex // BLOCK
    models = np.zeros((ndir, nrow, NCHAN, 4), np.complex64)
    clean = np.zeros((nrow, NCHAN, 4), np.complex128)
    for d in range(ndir):
        sel = facet == d
        vi = predict(uvw, nu, lm[sel], flux[sel]).astype(np.complex64)
        models[d, :, :, 0] = vi
        models[d, :, :, 3] = vi
        # Corrupt the stored (complex64) model, as both solvers read it.
        m = models[d].astype(np.complex128)
        gp, gq = g[block, ra1, d], g[block, ra2, d]  # (row, 2)
        clean[..., 0] += gp[:, None, 0] * m[..., 0] * np.conj(gq[:, None, 0])
        clean[..., 3] += gp[:, None, 1] * m[..., 3] * np.conj(gq[:, None, 1])
        clean[..., 1] += gp[:, None, 0] * m[..., 1] * np.conj(gq[:, None, 1])
        clean[..., 2] += gp[:, None, 1] * m[..., 2] * np.conj(gq[:, None, 0])
    rng = np.random.default_rng(SEEDS["noise"])
    noise = rng.normal(0, SIGMA, (nrow, NCHAN, 4, 2))
    noisy = clean + noise[..., 0] + 1j * noise[..., 1]

    ms = out / "dd1.ms"
    tab = stms.create_ms(ms, nrow, NCHAN)
    tab.close()
    d = SimpleNamespace(
        nchan=NCHAN,
        freq=nu,
        chan_width=CHAN_WIDTH,
        nu0=nu[NCHAN // 2],
        dt=DT,
        name="dd1",
    )
    stms.fill_subtables(ms, d, names, xyz, diameter, times, None)
    with tables.table(str(ms / "FIELD"), readonly=False) as t:
        direction = np.array([[RA0 * st.DEG, DEC0 * st.DEG]])
        for col in ("DELAY_DIR", "PHASE_DIR", "REFERENCE_DIR"):
            t.putcell(col, 0, direction)
        names_f = list(t.getcol("NAME"))
        names_f[0] = "DD1-SIM"
        t.putcol("NAME", np.array(names_f))
    rows_per_tile = max(1, 32768 // (NCHAN * 4))
    tab = tables.table(str(ms), readonly=False)
    for col in ["DATA_NF"] + [f"MODEL_D{k}" for k in range(ndir)]:
        tab.addcols(
            tables.maketabdesc(
                [tables.makearrcoldesc(col, 0j, shape=[NCHAN, 4], valuetype="complex")]
            ),
            {
                "TYPE": "TiledColumnStMan",
                "NAME": f"Tiled{col}",
                "SPEC": {"DEFAULTTILESHAPE": [4, NCHAN, rows_per_tile]},
            },
        )
    w = np.float32(1.0 / SIGMA**2)
    tix = times[tindex]
    tab.putcol("UVW", uvw)
    tab.putcol("DATA", noisy.astype(np.complex64))
    tab.putcol("DATA_NF", clean.astype(np.complex64))
    for k in range(ndir):
        tab.putcol(f"MODEL_D{k}", models[k])
    tab.putcol("WEIGHT_SPECTRUM", np.full((nrow, NCHAN, 4), w))
    tab.putcol("FLAG", np.zeros((nrow, NCHAN, 4), bool))
    tab.putcol("WEIGHT", np.full((nrow, 4), w))
    tab.putcol("SIGMA", np.full((nrow, 4), np.float32(SIGMA)))
    tab.putcol("TIME", tix)
    tab.putcol("TIME_CENTROID", tix)
    tab.putcol("ANTENNA1", ra1.astype(np.int32))
    tab.putcol("ANTENNA2", ra2.astype(np.int32))
    tab.putcol("INTERVAL", np.full(nrow, DT))
    tab.putcol("EXPOSURE", np.full(nrow, DT))
    tab.putcol("FLAG_ROW", np.zeros(nrow, bool))
    for col, value in (
        ("FIELD_ID", 0),
        ("STATE_ID", 0),
        ("SCAN_NUMBER", 1),
        ("DATA_DESC_ID", 0),
        ("ARRAY_ID", 0),
        ("OBSERVATION_ID", 0),
        ("FEED1", 0),
        ("FEED2", 0),
        ("PROCESSOR_ID", -1),
    ):
        tab.putcol(col, np.full(nrow, value, np.int32))
    tab.close()
    np.savez_compressed(
        out / "truth.npz",
        gains=g,
        block=BLOCK,
        lm=lm,
        flux=flux,
        facet=facet,
        centres_deg=np.array(CENTRES),
        times=times,
        freq=nu,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    ).stdout.strip()
    prov = {
        "task": "DD1 simulation (research/dd1-facet-gains.md section 4)",
        "argv": sys.argv,
        "commit": commit,
        "seeds": SEEDS,
        "nrow": nrow,
        "nant": nant,
        "nbaseline": nbl,
        "ntime": NTIME,
        "nchan": NCHAN,
        "ndir": ndir,
        "sigma": SIGMA,
        "phase_centre_deg": [RA0, DEC0],
        "centres_deg": CENTRES,
        "centre_flux": CENTRE_FLUX,
        "facet_counts": np.bincount(facet, minlength=ndir).tolist(),
        "noise_rms_measured": float((noisy - clean).real.std()),
        "seconds": time.perf_counter() - started,
    }
    (out / "provenance.json").write_text(json.dumps(prov, indent=1), encoding="utf-8")
    print(json.dumps(prov))


if __name__ == "__main__":
    main()
