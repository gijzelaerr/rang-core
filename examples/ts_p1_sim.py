"""Task TS-P1: the light-curve simulations (research/ts-p1.md, section 4.1).

Usage (worktree venv):
    python examples/ts_p1_sim.py CASE OUTDIR [--ntime N --nant N --nchan N]

CASE is `tsp1-dev` or `tsp1-held`. Writes OUTDIR/<case>.ms through rang's
table writer: SIM-TARGET (field 3 of A1's FIELD table), one scan of 450
integrations of 8 s from A1's START_UTC, all 64 antennas, 64 channels over
856-1712 MHz, no autocorrelations. DATA = static sky + transients + noise;
MODEL_DATA = the static sky (A1's target sky from the case's sky seed,
unpolarised and flat, as C5), so DATA - MODEL_DATA is the transients plus
noise; RESIDUAL_DATA holds that difference in complex64, for the WSClean
oracle only. WEIGHT = 1/sigma^2 (no WEIGHT_SPECTRUM). The transients are
unpolarised flat-spectrum points on pixel centres of the 1024^2, 4 arcsec
grid (l = -dx 4", m = dy 4"); their flux per integration is the mean over
[TIME - 4 s, TIME + 4 s), evaluated at the integration centre.

Also OUTDIR/<case>.truth.json (layout, truth flux per integration and
source, sigma and sigma_snap, times) and OUTDIR/<case>.provenance.json.
`--ntime/--nant/--nchan` make a smaller version for tests (not a TS-P1 set).
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_ms_write as tables
from rang import simtruth as st
from rang import simtruth_ms

CASES = ("tsp1-dev", "tsp1-held")
NTIME, NCHAN = 450, 64
ANTENNAS = list(range(64))
TARGET = 3  # SIM-TARGET in A1's FIELD table
SCALE_ARCSEC = 4.0
CHUNK_INTS = 4
ROLES = ("A", "B", "C", "D", "E", "F")
RADII_DEG = (0.0, 0.3, 0.5, 0.3, 0.4, 0.2)
PERIOD_D, LENGTH_D = 1200.0, 30.0
PERIOD_E = 600.0

# The development layout, frozen in research/ts-p1.md section 4.1 (amplitudes
# in sigma_snap; pulses as (first integration, integrations, amplitude)).
DEV = {
    "A": {"pixel": (0, 0), "pulses": [(40, 1, 20.0), (300, 1, 10.0)]},
    "B": {"pixel": (191, -191), "pulses": [(100, 2, 15.0)]},
    "C": {"pixel": (-300, 335), "pulses": [(200, 8, 8.0)]},
    "D": {"pixel": (-100, -251), "periodic": {"first_s": 403.0, "amplitude": 25.0}},
    "E": {"pixel": (250, 260), "variable": {"mean": 10.0}},
    "F": {"pixel": (-127, 127)},
}


def design(case, nant=None, nchan=NCHAN, ntime=NTIME):
    antennas = ANTENNAS if nant is None else ANTENNAS[:nant]
    return st.Design(
        case, antennas, nchan, {"T": ntime}, dict(st.SEEDS[case]), extra={"tsp1": 1}
    )


def sigma_snap(d):
    """sigma / sqrt(2 N): the noise of one Stokes I snapshot pixel with equal
    weights over N = baselines x channels samples (research/ts-p1.md 4.1)."""
    nbl = len(d.antennas) * (len(d.antennas) - 1) // 2
    return d.sigma / math.sqrt(2.0 * nbl * d.nchan)


def held_layout(d, ntime):
    """The held-out layout from the layout seed, by the rule frozen in
    research/ts-p1.md section 4.1."""
    rng = np.random.default_rng(d.seeds["layout"])
    step = SCALE_ARCSEC * st.ARCSEC
    out = {}
    for role, radius in zip(ROLES, RADII_DEG, strict=True):
        angle = rng.uniform(0.0, 2 * math.pi)
        r = radius * st.DEG / step
        out[role] = {"pixel": (round(r * math.cos(angle)), round(r * math.sin(angle)))}

    def amp(lo, hi):
        return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))

    first_d = float(rng.integers(0, int(PERIOD_D)))
    out["D"]["periodic"] = {"first_s": first_d, "amplitude": amp(7.0, 50.0)}
    out["E"]["variable"] = {"mean": amp(5.0, 20.0)}
    busy = set()
    for k in range(int(ntime * d.dt // PERIOD_D) + 1):
        s0 = first_d + k * PERIOD_D
        busy |= set(range(int(s0 // d.dt), int((s0 + LENGTH_D) // d.dt) + 1))
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
    return out


def truth_flux(layout, d, ntime, unit):
    """(ntime, nsrc) flux (Jy) averaged over each integration; `unit` is
    sigma_snap in Jy."""
    t0 = d.dt * np.arange(ntime)  # integration starts from the scan start
    t1 = t0 + d.dt
    flux = np.zeros((ntime, len(ROLES)))
    for s, role in enumerate(ROLES):
        spec = layout[role]
        for start, n, a in spec.get("pulses", []):
            flux[start : start + n, s] += a * unit
        if "periodic" in spec:
            p = spec["periodic"]
            k = 0
            while p["first_s"] + k * PERIOD_D < t1[-1]:
                a, b = (
                    p["first_s"] + k * PERIOD_D,
                    p["first_s"] + k * PERIOD_D + LENGTH_D,
                )
                overlap = np.clip(np.minimum(t1, b) - np.maximum(t0, a), 0.0, None)
                flux[:, s] += p["amplitude"] * unit * overlap / d.dt
                k += 1
        if "variable" in spec:
            w = 2 * math.pi / PERIOD_E
            mean_sin = (np.cos(w * t0) - np.cos(w * t1)) / (w * d.dt)
            flux[:, s] += spec["variable"]["mean"] * unit * (1.0 + 0.5 * mean_sin)
    return flux


def sources(layout):
    """Per role: pixel, (l, m) and (RA, Dec) in degrees."""
    _, ra0, dec0, _, _ = st.FIELDS[TARGET]
    step = SCALE_ARCSEC * st.ARCSEC
    out = []
    for role in ROLES:
        dx, dy = layout[role]["pixel"]
        east, north = -dx * step, dy * step
        ra, dec = st.radec(east, north, ra0 * st.DEG, dec0 * st.DEG)
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


def static_sky(d):
    comps = st.target_sky(d)
    for c in comps:
        c.update({"p": 0.0, "chi0_deg": 0.0, "rm": 0.0, "alpha": 0.0})
    return comps


def unit_points(srcs):
    return [
        {
            "kind": "point",
            "l": s["l"],
            "m": s["m"],
            "flux": 1.0,
            "alpha": 0.0,
            "fwhm_arcsec": 0.0,
            "ref_freq_hz": 1.284e9,
            "p": 0.0,
        }
        for s in srcs
    ]


def create_ms(path, nrow, nchan):
    cols = ("DATA", "MODEL_DATA", "RESIDUAL_DATA")
    desc = [
        tables.makearrcoldesc(c, 0j, shape=[nchan, 4], valuetype="complex")
        for c in cols
    ]
    desc += [
        tables.makearrcoldesc("FLAG", False, shape=[nchan, 4]),
        tables.makearrcoldesc("WEIGHT", 0.0, shape=[4], valuetype="float"),
        tables.makearrcoldesc("SIGMA", 0.0, shape=[4], valuetype="float"),
    ]
    rows_per_tile = max(1, 32768 // (nchan * 4))
    tiled = {f"*{k + 1}": (f"Tiled{c}", [c], 1) for k, c in enumerate(cols)}
    tiled["*4"] = ("TiledFlag", ["FLAG"], 8)
    dminfo = {
        key: {
            "TYPE": "TiledColumnStMan",
            "NAME": name,
            "COLUMNS": c,
            "SPEC": {"DEFAULTTILESHAPE": [4, nchan, rows_per_tile * k]},
        }
        for key, (name, c, k) in tiled.items()
    }
    t = tables.default_ms(str(path), desc, dminfo)
    t.addrows(nrow)
    return t


def generate(args):
    started = time.perf_counter()
    d = design(args.case, args.nant, args.nchan, args.ntime)
    ntime = args.ntime
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    ms = out / f"{args.case}.ms"
    if ms.exists():
        raise SystemExit(f"{ms} exists; remove it first")
    unit = sigma_snap(d)
    layout = DEV if args.case == "tsp1-dev" else held_layout(d, ntime)
    srcs = sources(layout)
    flux = truth_flux(layout, d, ntime, unit)
    xyz_all, diameter_all, names_all = st.antenna_table()
    names = [names_all[i] for i in d.antennas]
    xyz, diameter = xyz_all[d.antennas], diameter_all[d.antennas]
    t_start = st.schedule(st.design("small"))[0][0] - d.dt / 2  # A1's START_UTC
    times = t_start + d.dt * (np.arange(ntime) + 0.5)
    fields = np.full(ntime, TARGET, np.int32)
    uvw_ant, _, _ = st.geometry(d, times, fields)
    comps = static_sky(d)
    points = unit_points(srcs)
    nant = len(names)
    a1i, a2i = np.triu_indices(nant, 1)
    nbl = len(a1i)
    nrow = nbl * ntime
    create_ms(ms, nrow, d.nchan).close()
    simtruth_ms.fill_subtables(ms, d, names, xyz, diameter, times, fields)
    with tables.table(str(ms / "OBSERVATION"), readonly=False) as t:
        t.putcol("PROJECT", np.array([f"rang-ts-p1-{args.case}"]))
        t.putcol("OBSERVER", np.array(["rang TS-P1 simulated truth"]))
    tab = tables.table(str(ms), readonly=False)
    w = np.float32(1.0 / d.sigma**2)
    r0 = 0
    for c0 in range(0, ntime, CHUNK_INTS):
        job = np.arange(c0, min(c0 + CHUNK_INTS, ntime))
        rows = st.chunk_rows(job, a1i, a2i)
        uvw = uvw_ant[rows.tindex, rows.a1] - uvw_ant[rows.tindex, rows.a2]
        model = st.target_coherency(uvw, d.freq, comps)
        stokes = np.zeros(model.shape[:2], np.complex128)
        for s, p in enumerate(points):
            f = flux[rows.tindex, s]
            if np.any(f):
                v = st._predict(uvw, d.freq, st._component_arrays([p]))
                stokes += v * f[:, None]
        v = model.copy()
        v[..., 0] += stokes
        v[..., 3] += stokes
        if not args.noiseless:
            v = v + np.concatenate([st.noise_integration(d, t, nbl) for t in job])
        data = v.astype(np.complex64)
        model = model.astype(np.complex64)
        n = len(rows.tindex)
        tix = times[rows.tindex]
        tab.putcol("UVW", uvw, r0, n)
        tab.putcol("DATA", data, r0, n)
        tab.putcol("MODEL_DATA", model, r0, n)
        tab.putcol("RESIDUAL_DATA", data - model, r0, n)
        tab.putcol("FLAG", np.zeros((n, d.nchan, 4), bool), r0, n)
        tab.putcol("WEIGHT", np.full((n, 4), w), r0, n)
        tab.putcol("SIGMA", np.full((n, 4), np.float32(d.sigma)), r0, n)
        tab.putcol("TIME", tix, r0, n)
        tab.putcol("TIME_CENTROID", tix, r0, n)
        tab.putcol("ANTENNA1", rows.a1.astype(np.int32), r0, n)
        tab.putcol("ANTENNA2", rows.a2.astype(np.int32), r0, n)
        tab.putcol("INTERVAL", np.full(n, d.dt), r0, n)
        tab.putcol("EXPOSURE", np.full(n, d.dt), r0, n)
        tab.putcol("FLAG_ROW", np.zeros(n, bool), r0, n)
        for col, value in (
            ("FIELD_ID", TARGET),
            ("STATE_ID", TARGET),
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
        "field_id": TARGET,
        "scale_arcsec": SCALE_ARCSEC,
        "sigma_jy": d.sigma,
        "sigma_snap_jy": unit,
        "nbaseline": nbl,
        "nchan": d.nchan,
        "time_mjd_s": times.tolist(),
        "layout": layout,
        "sources": srcs,
        "flux_jy": flux.tolist(),
        "frozen_design": (args.nant, args.nchan, args.ntime) == (None, NCHAN, NTIME),
    }
    st.write_json(out / f"{args.case}.truth.json", truth)
    files = sorted(p for p in ms.rglob("*") if p.is_file())
    prov = {
        "task": "TS-P1 simulated truth (research/ts-p1.md, section 4.1)",
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
    return generate(p.parse_args(argv))


if __name__ == "__main__":
    main()
