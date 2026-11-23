"""Task TS-P2: the dynamic-spectrum simulations (research/ts-p2.md, 4.1).

Usage (worktree venv):
    python examples/ts_p2_sim.py CASE OUTDIR [--ntime N --nant N --nchan N]

CASE is `tsp2-dev` or `tsp2-held`. As TS-P1's `tsp1-held2`
(research/ts-p1.md 13.1; examples/ts_p1_sim.py): 64 antennas, 64 channels
over 856-1712 MHz, 450 x 8 s on SIM-TARGET; static sky in DATA and exactly
in MODEL_DATA; CORRECTED_DATA = sky + transients + noise, DATA =
CORRECTED_DATA x 2 e^{0.7i}; spectral unequal WEIGHT_SPECTRUM; cell flags
(3 % all, 2 % XX, 2 % YY, channel 10 in every row); RESIDUAL_DATA =
CORRECTED_DATA - MODEL_DATA for the WSClean oracle only. Changed (4.1): no
FLAG_ROW; the last 4 channels flagged in every row (an empty group at
M = 16); positions on pixel centres of the 2 arcsec grid within 0.25 deg;
each source's flux a(t) f(nu), f with a channel mean of one.

Writes OUTDIR/<case>.ms, <case>.truth.json (amplitudes, spectra, sigma per
interval and per interval and group at --groups) and <case>.provenance.json.
`--ntime/--nant/--nchan` make a smaller version for tests.
"""

import argparse
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_ms_write as tables
from rang import simtruth as st
from rang import simtruth_ms

_spec = importlib.util.spec_from_file_location(
    "ts_p1_sim", Path(__file__).with_name("ts_p1_sim.py")
)
p1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p1)

CASES = ("tsp2-dev", "tsp2-held")
NTIME, NCHAN, GROUPS = 450, 64, 16
SCALE_ARCSEC = 2.0
ROLES = p1.ROLES
RADII_DEG = (0.0, 0.15, 0.25, 0.15, 0.2, 0.1)
EMPTY_CHANNELS = 4  # the last channels, flagged in every row
FLAG_ALL, FLAG_XX, FLAG_YY, FLAG_CHANNEL = 0.03, 0.02, 0.02, 10
NU_C_PERIOD = 150e6

# Development layout (research/ts-p2.md 4.1; pixels in 2 arcsec units,
# amplitudes in sigma_snap).
DEV = {
    "A": {"pixel": (0, 0), "pulses": [(40, 1, 20.0), (300, 1, 10.0)]},
    "B": {"pixel": (191, -191), "pulses": [(100, 2, 15.0)]},
    "C": {"pixel": (-318, 318), "pulses": [(200, 8, 8.0)]},
    "D": {"pixel": (-150, 230), "periodic": {"first_s": 403.0, "amplitude": 25.0}},
    "E": {"pixel": (250, 260), "variable": {"mean": 10.0}},
    "F": {"pixel": (-127, 127)},
}
DEV_SPECTRA = {
    "A": {"kind": "powerlaw", "alpha": -1.5},
    "B": {"kind": "gaussian", "centre_hz": 1.2e9, "fwhm_hz": 200e6},
    "C": {"kind": "scintillation", "phase": 1.0},
    "D": {"kind": "flat"},
    "E": {"kind": "powerlaw", "alpha": 1.0},
    "F": {"kind": "flat"},
}


def spectrum(spec, freq):
    """f(nu) with a channel mean of one."""
    freq = np.asarray(freq, np.float64)
    kind = spec["kind"]
    if kind == "flat":
        f = np.ones_like(freq)
    elif kind == "powerlaw":
        f = (freq / 1.284e9) ** spec["alpha"]
    elif kind == "gaussian":
        f = np.exp(
            -4 * math.log(2) * (freq - spec["centre_hz"]) ** 2 / spec["fwhm_hz"] ** 2
        )
    elif kind == "scintillation":
        f = 1.0 + 0.8 * np.sin(2 * math.pi * freq / NU_C_PERIOD + spec["phase"])
    else:
        raise ValueError(kind)
    return f / f.mean()


def held_layout(d, ntime, radii=RADII_DEG, scale_arcsec=SCALE_ARCSEC):
    """ts-p1.md 4.1's held-out rule with TS-P2's radii and grid, then the
    spectral parameters from the same layout seed (ts-p2.md 4.1)."""
    rng = np.random.default_rng(d.seeds["layout"])
    step = scale_arcsec * st.ARCSEC
    out = {}
    for role, radius in zip(ROLES, radii, strict=True):
        angle = rng.uniform(0.0, 2 * math.pi)
        r = radius * st.DEG / step
        out[role] = {"pixel": (round(r * math.cos(angle)), round(r * math.sin(angle)))}

    def amp(lo, hi):
        return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))

    first_d = float(rng.integers(0, int(p1.PERIOD_D)))
    out["D"]["periodic"] = {"first_s": first_d, "amplitude": amp(7.0, 50.0)}
    out["E"]["variable"] = {"mean": amp(5.0, 20.0)}
    busy = set()
    for k in range(int(ntime * d.dt // p1.PERIOD_D) + 1):
        s0 = first_d + k * p1.PERIOD_D
        busy |= set(range(int(s0 // d.dt), int((s0 + p1.LENGTH_D) // d.dt) + 1))
    for role, lengths in (("A", (1, 1)), ("B", (2,)), ("C", (8,))):
        pulses = []
        for n in lengths:
            while True:
                start = int(rng.integers(10, ntime - 10 - n))
                span = set(range(start, start + n))
                if not span & busy:
                    break
            busy |= span
            pulses.append((start, n, amp(7.0, 50.0)))
        out[role]["pulses"] = pulses
    spectra = {
        "A": {"kind": "powerlaw", "alpha": float(rng.uniform(-2.0, 0.0))},
        "B": {
            "kind": "gaussian",
            "centre_hz": float(rng.uniform(1.0e9, 1.5e9)),
            "fwhm_hz": 200e6,
        },
        "C": {"kind": "scintillation", "phase": float(rng.uniform(0.0, 2 * math.pi))},
        "D": {"kind": "flat"},
        "E": {"kind": "powerlaw", "alpha": 1.0},
        "F": {"kind": "flat"},
    }
    return out, spectra


def sources(layout, ra0_deg, dec0_deg, scale_arcsec=SCALE_ARCSEC):
    step = scale_arcsec * st.ARCSEC
    out = []
    for role in ROLES:
        dx, dy = layout[role]["pixel"]
        east, north = -dx * step, dy * step
        ra, dec = st.radec(east, north, ra0_deg * st.DEG, dec0_deg * st.DEG)
        out.append(
            {
                "name": role,
                "pixel": [dx, dy],
                "l": east,
                "m": north,
                "ra_deg": ra / st.DEG,
                "dec_deg": dec / st.DEG,
            }
        )
    return out


def generate(args):
    started = time.perf_counter()
    d = p1.design(args.case, args.nant, args.nchan, args.ntime)
    ntime = args.ntime
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    ms = out / f"{args.case}.ms"
    if ms.exists():
        raise SystemExit(f"{ms} exists; remove it first")
    unit = p1.sigma_snap(d)
    if args.case == "tsp2-dev":
        layout, spectra = DEV, DEV_SPECTRA
    else:
        layout, spectra = held_layout(d, ntime)
    _, ra0, dec0, _, _ = st.FIELDS[p1.TARGET]
    srcs = sources(layout, ra0, dec0)
    amp = p1.truth_flux(layout, d, ntime, unit)  # (ntime, nsrc) a(t) in Jy
    spec = np.array([spectrum(spectra[r], d.freq) for r in ROLES])  # (nsrc, nchan)
    xyz_all, diameter_all, names_all = st.antenna_table()
    names = [names_all[i] for i in d.antennas]
    xyz, diameter = xyz_all[d.antennas], diameter_all[d.antennas]
    t_start = st.schedule(st.design("small"))[0][0] - d.dt / 2
    times = t_start + d.dt * (np.arange(ntime) + 0.5)
    fields = np.full(ntime, p1.TARGET, np.int32)
    uvw_ant, _, _ = st.geometry(d, times, fields)
    comps = p1.static_sky(d)
    points = p1.unit_points(srcs)
    nant = len(names)
    a1i, a2i = np.triu_indices(nant, 1)
    nbl = len(a1i)
    nrow = nbl * ntime
    groups = args.groups if d.nchan % args.groups == 0 else 1
    per = d.nchan // groups
    p1.create_ms(ms, nrow, d.nchan, protocol2=True).close()
    rng_w = np.random.default_rng(d.seeds["weights"])
    ant_w = rng_w.uniform(0.5, 1.5, (nant, 2))
    k = np.arange(d.nchan)
    chan_w = 1.0 + 0.5 * np.cos(2 * math.pi * k / 64)
    rng_f = np.random.default_rng(d.seeds["flags"])
    sigma_k = np.full(ntime, unit)
    sigma_kg = np.full((ntime, groups), np.nan)
    simtruth_ms.fill_subtables(ms, d, names, xyz, diameter, times, fields)
    with tables.table(str(ms / "OBSERVATION"), readonly=False) as t:
        t.putcol("PROJECT", np.array([f"rang-ts-p2-{args.case}"]))
        t.putcol("OBSERVER", np.array(["rang TS-P2 simulated truth"]))
    tab = tables.table(str(ms), readonly=False)
    w = np.float32(1.0 / d.sigma**2)
    r0 = 0
    for c0 in range(0, ntime, p1.CHUNK_INTS):
        job = np.arange(c0, min(c0 + p1.CHUNK_INTS, ntime))
        rows = st.chunk_rows(job, a1i, a2i)
        uvw = uvw_ant[rows.tindex, rows.a1] - uvw_ant[rows.tindex, rows.a2]
        model = st.target_coherency(uvw, d.freq, comps)
        stokes = np.zeros(model.shape[:2], np.complex128)
        for s, p in enumerate(points):
            a = amp[rows.tindex, s]
            if np.any(a):
                v = st._predict(uvw, d.freq, st._component_arrays([p]))
                stokes += v * a[:, None] * spec[s][None, :]
        v = model.copy()
        v[..., 0] += stokes
        v[..., 3] += stokes
        n = len(rows.tindex)
        wx = w * chan_w[None, :] * (ant_w[rows.a1, 0] * ant_w[rows.a2, 0])[:, None]
        wy = w * chan_w[None, :] * (ant_w[rows.a1, 1] * ant_w[rows.a2, 1])[:, None]
        wc = np.sqrt(wx * wy)
        wspec = np.stack([wx, wc, wc, wy], axis=-1)
        scale = np.sqrt(1.0 / wspec) / d.sigma
        u = rng_f.random((n, d.nchan))
        flags = np.zeros((n, d.nchan, 4), bool)
        flags[u < FLAG_ALL] = True
        flags[(u >= FLAG_ALL) & (u < FLAG_ALL + FLAG_XX), 0] = True
        yy = (u >= FLAG_ALL + FLAG_XX) & (u < FLAG_ALL + FLAG_XX + FLAG_YY)
        flags[yy, 3] = True
        if d.nchan > FLAG_CHANNEL:
            flags[:, FLAG_CHANNEL, :] = True
        if d.nchan >= 2 * EMPTY_CHANNELS:
            flags[:, d.nchan - EMPTY_CHANNELS :, :] = True
        if not args.noiseless:
            noise = np.concatenate([st.noise_integration(d, t, nbl) for t in job])
            v = v + noise * scale
        data = v.astype(np.complex64)
        model = model.astype(np.complex64)
        tix = times[rows.tindex]
        tab.putcol("UVW", uvw, r0, n)
        tab.putcol("MODEL_DATA", model, r0, n)
        tab.putcol("RESIDUAL_DATA", data - model, r0, n)
        tab.putcol("FLAG", flags, r0, n)
        tab.putcol("CORRECTED_DATA", data, r0, n)
        tab.putcol("DATA", (data * p1.WRONG_COLUMN_GAIN).astype(np.complex64), r0, n)
        tab.putcol("WEIGHT_SPECTRUM", wspec.astype(np.float32), r0, n)
        tab.putcol("WEIGHT", wspec.mean(axis=1).astype(np.float32), r0, n)
        tab.putcol(
            "SIGMA", (1.0 / np.sqrt(wspec.mean(axis=1))).astype(np.float32), r0, n
        )
        wi = np.minimum(4 * wx, 4 * wy)
        wi[flags[..., 0] | flags[..., 3]] = 0.0
        var = (1.0 / wx + 1.0 / wy) / 4.0
        for t in job:
            sel = rows.tindex == t
            s, vv = wi[sel], var[sel]
            sigma_k[t] = math.sqrt(float(np.sum(s**2 * vv))) / float(s.sum())
            for g in range(groups):
                sg, vg = s[:, g * per : (g + 1) * per], vv[:, g * per : (g + 1) * per]
                tot = float(sg.sum())
                if tot > 0:
                    sigma_kg[t, g] = math.sqrt(float(np.sum(sg**2 * vg))) / tot
        tab.putcol("TIME", tix, r0, n)
        tab.putcol("TIME_CENTROID", tix, r0, n)
        tab.putcol("ANTENNA1", rows.a1.astype(np.int32), r0, n)
        tab.putcol("ANTENNA2", rows.a2.astype(np.int32), r0, n)
        tab.putcol("INTERVAL", np.full(n, d.dt), r0, n)
        tab.putcol("EXPOSURE", np.full(n, d.dt), r0, n)
        tab.putcol("FLAG_ROW", np.zeros(n, bool), r0, n)
        for col, value in (
            ("FIELD_ID", p1.TARGET),
            ("STATE_ID", p1.TARGET),
            ("SCAN_NUMBER", 1),
            ("DATA_DESC_ID", 0),
            ("ARRAY_ID", 0),
            ("OBSERVATION_ID", 0),
            ("FEED1", 0),
            ("FEED2", 0),
            ("PROCESSOR_ID", -1),
        ):
            tab.putcol(col, np.full(n, value, np.int32), r0, n)
        r0 += n
    tab.close()
    truth = {
        "case": args.case,
        "field_id": p1.TARGET,
        "scale_arcsec": SCALE_ARCSEC,
        "sigma_jy": d.sigma,
        "sigma_snap_jy": unit,
        "sigma_snap_interval_jy": sigma_k.tolist(),
        "groups": groups,
        "sigma_cell_jy": [
            [None if not np.isfinite(x) else float(x) for x in row] for row in sigma_kg
        ],
        "nbaseline": nbl,
        "nchan": d.nchan,
        "freq_hz": [float(f) for f in d.freq],
        "time_mjd_s": times.tolist(),
        "layout": layout,
        "spectra": spectra,
        "spectrum": spec.tolist(),
        "sources": srcs,
        "amplitude_jy": amp.tolist(),
        "frozen_design": (args.nant, args.nchan, args.ntime) == (None, NCHAN, NTIME),
    }
    st.write_json(out / f"{args.case}.truth.json", truth)
    files = sorted(p for p in ms.rglob("*") if p.is_file())
    prov = {
        "task": "TS-P2 simulated truth (research/ts-p2.md, section 4.1)",
        "case": args.case,
        "ms": str(ms.resolve()),
        "noiseless": bool(args.noiseless),
        "argv": sys.argv,
        "design": d.as_json(),
        "nrow": nrow,
        "ms_bytes": sum(p.stat().st_size for p in files),
        "git": simtruth_ms.git_facts(),
        "versions": simtruth_ms.versions(),
        "seconds": time.perf_counter() - started,
    }
    st.write_json(out / f"{args.case}.provenance.json", prov)
    print(json.dumps({k: prov[k] for k in ("ms", "nrow", "ms_bytes", "seconds")}))
    return ms


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("case", choices=CASES)
    p.add_argument("outdir")
    p.add_argument("--noiseless", action="store_true")
    p.add_argument("--ntime", type=int, default=NTIME)
    p.add_argument("--nant", type=int)
    p.add_argument("--nchan", type=int, default=NCHAN)
    p.add_argument("--groups", type=int, default=GROUPS)
    return generate(p.parse_args(argv))


if __name__ == "__main__":
    main()
