"""Task C5: the simulated truth of self-calibration (research/c5-selfcal.md,
section 3).

Usage (WSL host, worktree venv):
    python examples/c5_selfcal_sim.py CASE OUTDIR [--noiseless]

CASE is `c5pa`, `c5delay`, `c5pa-held` or `c5delay-held` (C5), or
`c5pa-held2` or `c5delay-held2` (C5b's held-out pair). Writes
OUTDIR/<case>[-twin].ms through rang's table writer: the seven target scans
of A1's schedule (16 integrations each) on 32 antennas and 64 channels,
DATA = S_p M S_q^H + noise, as if 1GC were perfect, M the target's Stokes I
coherency (A1's sky, unpolarised and flat in frequency) and S the diagonal
self-calibration gain, constant over blocks of 8 integrations. MODEL_TRUE
holds M. Also OUTDIR/<name>.truth.npz (gains per block, blocks, delays and
phases) and OUTDIR/<name>.provenance.json (seeds, argv, commit, sizes).
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import a1_simtruth as a1
from rang import core_ms_write as tables
from rang import simtruth as st

# Seeds in rang.simtruth.SEEDS (task C5's four cases, C5b's two).
CASES = {
    name: name.split("-")[0].removeprefix("c5")
    for name in (
        "c5pa",
        "c5delay",
        "c5pa-held",
        "c5delay-held",
        "c5pa-held2",  # task C5b
        "c5delay-held2",
    )
}
ANTENNAS = list(range(0, 64, 2))
NCHAN = 64
TARGET_LENGTH = 16
BLOCK = st.SELFCAL_BLOCK  # 8 integrations
CHUNK_INTS = 8


def design(case):
    kind = CASES[case]
    seeds = dict(st.SEEDS[case])
    return kind, st.Design(
        case,
        ANTENNAS,
        NCHAN,
        {"F": 0, "X": 0, "G": 0, "T": TARGET_LENGTH},
        seeds,
        extra={"c5_truth": kind},
    )


def sky(d):
    """A1's target sky from the case's sky seed, unpolarised and flat."""
    comps = st.target_sky(d)
    for c in comps:
        c.update({"p": 0.0, "chi0_deg": 0.0, "rm": 0.0, "alpha": 0.0})
    return comps


def blocks(scans, within):
    """Block index per integration: 8 integrations from each scan start."""
    out = np.empty(len(scans), np.int64)
    bid = 0
    for s in np.unique(scans):
        idx = np.flatnonzero(scans == s)
        local = within[idx] // BLOCK
        out[idx] = local + bid
        bid += int(local.max()) + 1
    return out


def truth_gains(kind, d, nblock):
    """Per block the gains (block, chan, antenna, hand) and their parts."""
    rng = np.random.default_rng(d.seeds["jones"])
    nant, nu, nu0 = len(d.antennas), d.freq, d.nu0
    deg = math.pi / 180.0
    if kind == "pa":
        phase = rng.uniform(-30.0, 30.0, (nant, 2))[None] + rng.normal(
            0.0, 10.0, (nblock, nant, 2)
        )
        amp = 1.0 + rng.uniform(-0.1, 0.1, (nant, 2))[None]
        amp = amp + rng.normal(0.0, 0.01, (nblock, nant, 2))
        g = amp * np.exp(1j * deg * phase)
        gains = np.broadcast_to(g[:, None], (nblock, len(nu), nant, 2)).copy()
        return gains, {"phase_deg": phase, "amplitude": amp}
    sign = rng.choice([-1.0, 1.0], (nant, 2))
    tau = sign * rng.uniform(0.05, 0.4, (nant, 2))
    tau = tau[None] + rng.normal(0.0, 0.03, (nblock, nant, 2))
    phase = rng.uniform(-20.0, 20.0, (nant, 2))[None] + rng.normal(
        0.0, 5.0, (nblock, nant, 2)
    )
    arg = deg * phase[:, None] + 2 * math.pi * tau[:, None] * 1e-9 * (
        nu[None, :, None, None] - nu0
    )
    return np.exp(1j * arg), {"tau_ns": tau, "phase_deg": phase}


def create_ms(path, nrow, nchan):
    desc = [
        tables.makearrcoldesc("DATA", 0j, shape=[nchan, 4], valuetype="complex"),
        tables.makearrcoldesc("MODEL_TRUE", 0j, shape=[nchan, 4], valuetype="complex"),
        tables.makearrcoldesc(
            "WEIGHT_SPECTRUM", 0.0, shape=[nchan, 4], valuetype="float"
        ),
        tables.makearrcoldesc("FLAG", False, shape=[nchan, 4]),
        tables.makearrcoldesc("WEIGHT", 0.0, shape=[4], valuetype="float"),
        tables.makearrcoldesc("SIGMA", 0.0, shape=[4], valuetype="float"),
    ]
    rows_per_tile = max(1, 32768 // (nchan * 4))
    tiled = {
        "*1": ("TiledData", ["DATA"], 1),
        "*2": ("TiledModelTrue", ["MODEL_TRUE"], 1),
        "*3": ("TiledWeightSpectrum", ["WEIGHT_SPECTRUM"], 1),
        "*4": ("TiledFlag", ["FLAG"], 8),
    }
    dminfo = {
        key: {
            "TYPE": "TiledColumnStMan",
            "NAME": name,
            "COLUMNS": cols,
            "SPEC": {"DEFAULTTILESHAPE": [4, nchan, rows_per_tile * k]},
        }
        for key, (name, cols, k) in tiled.items()
    }
    t = tables.default_ms(str(path), desc, dminfo)
    t.addrows(nrow)
    return t


def corrupt(m, g, tb, a1i, a2i):
    """V = g_p M g_q^H per correlation (XX, XY, YX, YY)."""
    gp = g[tb, :, a1i, :]  # (row, chan, 2)
    gq = np.conj(g[tb, :, a2i, :])
    v = np.empty_like(m)
    v[..., 0] = gp[..., 0] * m[..., 0] * gq[..., 0]
    v[..., 1] = gp[..., 0] * m[..., 1] * gq[..., 1]
    v[..., 2] = gp[..., 1] * m[..., 2] * gq[..., 0]
    v[..., 3] = gp[..., 1] * m[..., 3] * gq[..., 1]
    return v


def generate(args):
    started = time.perf_counter()
    kind, d = design(args.case)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    name = args.case + ("-twin" if args.noiseless else "")
    ms = out / f"{name}.ms"
    if ms.exists():
        raise SystemExit(f"{ms} exists; remove it first")
    xyz_all, diameter_all, names_all = st.antenna_table()
    names = [names_all[i] for i in d.antennas]
    xyz, diameter = xyz_all[d.antennas], diameter_all[d.antennas]
    times, scans, fields, within = st.schedule(d)
    uvw_ant, _, _ = st.geometry(d, times, fields)
    comps = sky(d)
    bid = blocks(scans, within)
    gains, parts = truth_gains(kind, d, int(bid.max()) + 1)
    nant = len(names)
    a1i, a2i = np.triu_indices(nant, 1)
    nbl = len(a1i)
    nrow = nbl * len(times)
    tab = create_ms(ms, nrow, d.nchan)
    tab.close()
    a1.fill_subtables(ms, d, names, xyz, diameter, times, fields)
    with tables.table(str(ms / "OBSERVATION"), readonly=False) as t:
        t.putcol("PROJECT", np.array([f"rang-c5-selfcal-{name}"]))
        t.putcol("OBSERVER", np.array(["rang C5 simulated truth"]))
    tab = tables.table(str(ms), readonly=False)
    w = np.float32(1.0 / d.sigma**2)
    r0 = 0
    for c0 in range(0, len(times), CHUNK_INTS):
        job = np.arange(c0, min(c0 + CHUNK_INTS, len(times)))
        rows = st.chunk_rows(job, a1i, a2i)
        uvw = uvw_ant[rows.tindex, rows.a1] - uvw_ant[rows.tindex, rows.a2]
        m = st.target_coherency(uvw, d.freq, comps)
        v = corrupt(m, gains, bid[rows.tindex], rows.a1, rows.a2)
        if not args.noiseless:
            v = v + np.concatenate([st.noise_integration(d, t, nbl) for t in job])
        n = len(rows.tindex)
        tix = times[rows.tindex]
        tab.putcol("UVW", uvw, r0, n)
        tab.putcol("DATA", v.astype(np.complex64), r0, n)
        tab.putcol("MODEL_TRUE", m.astype(np.complex64), r0, n)
        tab.putcol("WEIGHT_SPECTRUM", np.full((n, d.nchan, 4), w), r0, n)
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
            ("FIELD_ID", fields[rows.tindex]),
            ("STATE_ID", fields[rows.tindex]),
            ("SCAN_NUMBER", scans[rows.tindex]),
        ):
            tab.putcol(col, value.astype(np.int32), r0, n)
        for col, value in (
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
    truth = out / f"{name}.truth.npz"
    np.savez_compressed(
        truth,
        kind=kind,
        gains=gains,
        block=bid,
        time=times,
        scan=scans,
        within=within,
        freq_hz=d.freq,
        nu0_hz=d.nu0,
        sigma_jy=d.sigma,
        antenna_index=np.array(d.antennas),
        **parts,
    )
    files = sorted(p for p in ms.rglob("*") if p.is_file())
    prov = {
        "task": "C5 simulated truth (research/c5-selfcal.md, section 3)",
        "case": args.case,
        "truth": kind,
        "ms": str(ms.resolve()),
        "noiseless": bool(args.noiseless),
        "argv": sys.argv,
        "design": d.as_json(),
        "nrow": nrow,
        "nintegration": len(times),
        "nbaseline": nbl,
        "nblock": int(bid.max()) + 1,
        "scans": sorted(int(s) for s in np.unique(scans)),
        "sky": comps,
        "ms_bytes": sum(p.stat().st_size for p in files),
        "git": a1.git_facts(),
        "versions": a1.versions(),
        "seconds": time.perf_counter() - started,
        "sha256": {truth.name: st.sha256_file(truth)},
    }
    st.write_json(out / f"{name}.provenance.json", prov)
    print(json.dumps({k: prov[k] for k in ("ms", "nrow", "nblock", "seconds")}))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("case", choices=sorted(CASES))
    p.add_argument("outdir")
    p.add_argument("--noiseless", action="store_true")
    generate(p.parse_args(argv))


if __name__ == "__main__":
    main()
