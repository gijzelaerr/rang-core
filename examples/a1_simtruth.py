"""Task A1: write the simulated truth as a Measurement Set (research/a1-simtruth.md).

Usage (host, worktree venv):
    python examples/a1_simtruth.py generate {small,full} OUTDIR [--workers N]
        [--noiseless] [--scans 1,2,3] [--max-per-scan N] [--name NAME]
    python examples/a1_simtruth.py size {small,full}

`generate` writes OUTDIR/<name>.ms through rang's table writer
(`rang.core_ms_write`), OUTDIR/truth.npz (the Jones terms, raw and in
refant 0's CASA gauge, the geometry and the schedule), OUTDIR/truth.json
(design, fields, calibrator and target models, RFI events),
OUTDIR/<name>.rfi_mask.npz (bit-packed per-cell masks in MS row order) and
OUTDIR/<name>.provenance.json (seeds, argv, commit, versions, timings,
sizes, hashes). `--noiseless` leaves out noise and RFI (the twin for the
round trip); `--scans`/`--max-per-scan` keep a subset of integrations with
their global indices, so noise and RFI of those rows equal the full run's.
"""

import argparse
import json
import multiprocessing as mp
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_ms_write as tables
from rang import simtruth as st

ROOT = Path(__file__).resolve().parents[1]
CHUNK_INTS = 4
_STATE = {}


def select(d, times, scans, scan_list, max_per_scan):
    keep = np.ones(len(times), bool)
    if scan_list:
        keep &= np.isin(scans, scan_list)
    if max_per_scan:
        for s in np.unique(scans):
            idx = np.flatnonzero(keep & (scans == s))
            keep[idx[max_per_scan:]] = False
    return np.flatnonzero(keep)


def bytes_per_row(nchan, ncorr=4):
    # DATA c64, WEIGHT_SPECTRUM f32, FLAG bool (1 byte per cell, tiled),
    # plus UVW, TIME, ... and WEIGHT/SIGMA (about 160 bytes).
    return nchan * ncorr * (8 + 4 + 1) + 160


def size(version):
    d = st.design(version)
    times = st.schedule(d)[0]
    nant = len(d.antennas)
    nbl = nant * (nant - 1) // 2
    nrow = nbl * len(times)
    b = nrow * bytes_per_row(d.nchan)
    extra = nrow * d.nchan * 4 * 8 * 2
    return {
        "version": version,
        "nant": nant,
        "nbaseline": nbl,
        "nintegration": len(times),
        "nrow": nrow,
        "nchan": d.nchan,
        "ms_bytes_estimate": b,
        "ms_gb_estimate": b / 1e9,
        "with_model_and_corrected_gb": (b + extra) / 1e9,
        "track_hours": (times[-1] - times[0] + d.dt) / 3600.0,
    }


def _chunk(job):
    """Worker: DATA, UVW and RFI masks of a run of integrations."""
    s = _STATE
    d, truth, q, uvw_ant = s["design"], s["truth"], s["q"], s["uvw"]
    tidx = np.asarray(job, np.int64)
    nbl = len(s["a1"])
    rows = st.chunk_rows(tidx, s["a1"], s["a2"])
    t0 = time.perf_counter()
    m, uvw = st.sky_coherency(d, rows, uvw_ant, s["fields"], s["sky"], s["cal"])
    t1 = time.perf_counter()
    v = st.corrupt(m, truth, d, rows, q)
    out = {"uvw": uvw, "predict_s": t1 - t0}
    if s["noiseless"]:
        out["data"] = v.astype(np.complex64)
        out["mask_any"] = out["mask_5s"] = None
    else:
        r = st.rfi_chunk(s["events"], d, rows, s["enu"])
        n = np.concatenate([st.noise_integration(d, t, nbl) for t in tidx])
        out["data"] = (v + r + n).astype(np.complex64)
        absr = np.abs(r)
        out["mask_any"] = np.packbits((absr > 0).any(-1), axis=1)
        out["mask_5s"] = np.packbits((absr > 5 * d.sigma).any(-1), axis=1)
    out["seconds"] = time.perf_counter() - t0
    return out


def create_ms(path, nrow, nchan):
    desc = [
        tables.makearrcoldesc("DATA", 0j, shape=[nchan, 4], valuetype="complex"),
        tables.makearrcoldesc(
            "WEIGHT_SPECTRUM", 0.0, shape=[nchan, 4], valuetype="float"
        ),
        tables.makearrcoldesc("FLAG", False, shape=[nchan, 4]),
        tables.makearrcoldesc("WEIGHT", 0.0, shape=[4], valuetype="float"),
        tables.makearrcoldesc("SIGMA", 0.0, shape=[4], valuetype="float"),
    ]
    rows_per_tile = max(1, 32768 // (nchan * 4))
    dminfo = {
        "*1": {
            "TYPE": "TiledColumnStMan",
            "NAME": "TiledData",
            "COLUMNS": ["DATA"],
            "SPEC": {"DEFAULTTILESHAPE": [4, nchan, rows_per_tile]},
        },
        "*2": {
            "TYPE": "TiledColumnStMan",
            "NAME": "TiledWeightSpectrum",
            "COLUMNS": ["WEIGHT_SPECTRUM"],
            "SPEC": {"DEFAULTTILESHAPE": [4, nchan, rows_per_tile]},
        },
        "*3": {
            "TYPE": "TiledColumnStMan",
            "NAME": "TiledFlag",
            "COLUMNS": ["FLAG"],
            "SPEC": {"DEFAULTTILESHAPE": [4, nchan, rows_per_tile * 8]},
        },
    }
    t = tables.default_ms(str(path), desc, dminfo)
    t.addrows(nrow)
    return t


def fill_subtables(ms, d, names, xyz, diameter, times, fields_present):
    nant, nchan, nu = len(names), d.nchan, d.freq
    width = d.chan_width

    def sub(name, nrow):
        t = tables.table(str(Path(ms) / name), readonly=False)
        if nrow:
            t.addrows(nrow)
        return t

    with sub("ANTENNA", nant) as t:
        t.putcol("NAME", np.array(names))
        t.putcol("STATION", np.array(names))
        t.putcol("TYPE", np.array(["GROUND-BASED"] * nant))
        t.putcol("MOUNT", np.array(["ALT-AZ"] * nant))
        t.putcol("POSITION", xyz)
        t.putcol("OFFSET", np.zeros((nant, 3)))
        t.putcol("DISH_DIAMETER", diameter)
        t.putcol("FLAG_ROW", np.zeros(nant, bool))
    t_mid = (times[0] + times[-1]) / 2
    span = times[-1] - times[0] + d.dt
    with sub("FEED", nant) as t:
        t.putcol("ANTENNA_ID", np.arange(nant, dtype=np.int32))
        t.putcol("FEED_ID", np.zeros(nant, np.int32))
        t.putcol("SPECTRAL_WINDOW_ID", np.full(nant, -1, np.int32))
        t.putcol("TIME", np.full(nant, t_mid))
        t.putcol("INTERVAL", np.full(nant, span))
        t.putcol("NUM_RECEPTORS", np.full(nant, 2, np.int32))
        t.putcol("BEAM_ID", np.full(nant, -1, np.int32))
        for i in range(nant):
            t.putcell("BEAM_OFFSET", i, np.zeros((2, 2)))
            t.putcell("POLARIZATION_TYPE", i, np.array(["X", "Y"]))
            t.putcell("POL_RESPONSE", i, np.eye(2, dtype=np.complex64))
            t.putcell("RECEPTOR_ANGLE", i, np.array([st.RECEPTOR_ANGLE] * 2))
        t.putcol("POSITION", np.zeros((nant, 3)))
    with sub("SPECTRAL_WINDOW", 1) as t:
        t.putcell("CHAN_FREQ", 0, nu)
        t.putcell("CHAN_WIDTH", 0, np.full(nchan, width))
        t.putcell("EFFECTIVE_BW", 0, np.full(nchan, width))
        t.putcell("RESOLUTION", 0, np.full(nchan, width))
        t.putcol("REF_FREQUENCY", np.array([d.nu0]))
        t.putcol("NUM_CHAN", np.array([nchan], np.int32))
        t.putcol("TOTAL_BANDWIDTH", np.array([width * nchan]))
        t.putcol("MEAS_FREQ_REF", np.array([5], np.int32))
        t.putcol("NAME", np.array(["L-band"]))
        t.putcol("NET_SIDEBAND", np.array([1], np.int32))
        t.putcol("FREQ_GROUP", np.array([0], np.int32))
        t.putcol("FREQ_GROUP_NAME", np.array(["Group 1"]))
        t.putcol("IF_CONV_CHAIN", np.array([0], np.int32))
        t.putcol("FLAG_ROW", np.array([False]))
    with sub("POLARIZATION", 1) as t:
        t.putcol("NUM_CORR", np.array([4], np.int32))
        t.putcell("CORR_TYPE", 0, np.array([9, 10, 11, 12], np.int32))
        t.putcell(
            "CORR_PRODUCT", 0, np.array([[0, 0], [0, 1], [1, 0], [1, 1]], np.int32)
        )
        t.putcol("FLAG_ROW", np.array([False]))
    with sub("DATA_DESCRIPTION", 1) as t:
        t.putcol("SPECTRAL_WINDOW_ID", np.array([0], np.int32))
        t.putcol("POLARIZATION_ID", np.array([0], np.int32))
        t.putcol("FLAG_ROW", np.array([False]))
    nf = len(st.FIELDS)
    with sub("FIELD", nf) as t:
        for i, (_, ra, dec, _, _) in enumerate(st.FIELDS):
            direction = np.array([[ra * st.DEG, dec * st.DEG]])
            for col in ("DELAY_DIR", "PHASE_DIR", "REFERENCE_DIR"):
                t.putcell(col, i, direction)
        t.putcol("NAME", np.array([f[0] for f in st.FIELDS]))
        t.putcol("CODE", np.array([""] * nf))
        t.putcol("TIME", np.full(nf, times[0]))
        t.putcol("NUM_POLY", np.zeros(nf, np.int32))
        t.putcol("SOURCE_ID", np.arange(nf, dtype=np.int32))
        t.putcol("FLAG_ROW", np.zeros(nf, bool))
    with sub("STATE", nf) as t:
        t.putcol("OBS_MODE", np.array([f[4] for f in st.FIELDS]))
        t.putcol("SIG", np.ones(nf, bool))
        t.putcol("REF", np.zeros(nf, bool))
        t.putcol("CAL", np.zeros(nf))
        t.putcol("LOAD", np.zeros(nf))
        t.putcol("SUB_SCAN", np.zeros(nf, np.int32))
        t.putcol("FLAG_ROW", np.zeros(nf, bool))
    with sub("OBSERVATION", 1) as t:
        t.putcol("TELESCOPE_NAME", np.array(["MeerKAT"]))
        t.putcell(
            "TIME_RANGE", 0, np.array([times[0] - d.dt / 2, times[-1] + d.dt / 2])
        )
        t.putcol("OBSERVER", np.array(["rang A1 simulated truth"]))
        t.putcol("PROJECT", np.array([f"rang-a1-simtruth-{d.name}"]))
        t.putcol("RELEASE_DATE", np.array([times[0]]))
        t.putcol("SCHEDULE_TYPE", np.array([""]))
        t.putcell("LOG", 0, np.array([""]))
        t.putcell("SCHEDULE", 0, np.array([""]))
        t.putcol("FLAG_ROW", np.array([False]))


def git_facts():
    def run(*args):
        return subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False
        ).stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD"),
        "dirty": bool(run("status", "--porcelain")),
    }


def versions():
    import astropy

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "astropy": astropy.__version__,
        "platform": platform.platform(),
    }


def truth_arrays(d, truth, gauge, q, elev, uvw, times, scans, fields, within):
    out = {f"raw_{k}": v for k, v in truth.items()}
    out.update(
        {
            f"gauge{gauge['refant']}_{k}": v
            for k, v in gauge.items()
            if isinstance(v, np.ndarray)
        }
    )
    out.update(
        {
            "freq_hz": d.freq,
            "nu0_hz": np.array(d.nu0),
            "time": times,
            "scan": scans,
            "field": fields,
            "within_scan": within,
            "parallactic_angle": q,
            "parallactic_angle_casa_frame": st.parallactic_angle_casa(d, times, fields),
            "receptor_angle": np.array([st.RECEPTOR_ANGLE] * 2),
            "elevation_deg": elev,
            "uvw_antenna": uvw,
            "antenna_index": np.array(d.antennas),
            "sigma_jy": np.array(d.sigma),
            "calibrator_stokes": st.calibrator_stokes(d),
        }
    )
    return out


def with_overrides(d, args):
    """Task C2d's held-out version (research/c2d-fluxscale.md, section 5):
    `--seeds jones,sky,rfi,noise` and `--gcal-flux`, `--gcal-spix`
    (comma-separated) and `--gcal-reffreq` replace the version's seeds and
    the gain calibrator's model; without them the version is unchanged."""
    import dataclasses

    seeds = getattr(args, "seeds", "")
    flux = getattr(args, "gcal_flux", None)
    if not seeds and flux is None:
        return d
    changes = {}  # the name stays: the A1 checks rebuild the design from it
    if seeds:
        values = [int(s) for s in seeds.split(",")]
        if len(values) != 4:
            raise SystemExit("--seeds takes jones,sky,rfi,noise")
        changes["seeds"] = dict(zip(("jones", "sky", "rfi", "noise"), values))
    if flux is not None:
        spix = (
            tuple(float(s) for s in args.gcal_spix.split(",")) if args.gcal_spix else ()
        )
        gcal = {"fluxdensity": float(flux), "reffreq_hz": float(args.gcal_reffreq),
                "spix": spix}  # fmt: skip
        changes["extra"] = {**d.extra, "gcal": gcal}
    return dataclasses.replace(d, **changes)


def generate(args):
    started = time.perf_counter()
    d = with_overrides(st.design(args.version), args)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    name = args.name or (f"a1-{d.name}" + ("-twin" if args.noiseless else ""))
    ms = out / f"{name}.ms"
    if ms.exists():
        raise SystemExit(f"{ms} exists; remove it first")
    xyz_all, diameter_all, names_all = st.antenna_table()
    names = [names_all[i] for i in d.antennas]
    xyz, diameter = xyz_all[d.antennas], diameter_all[d.antennas]
    times, scans, fields, within = st.schedule(d)
    t = time.perf_counter()
    uvw, q, elev = st.geometry(d, times, fields)
    seconds = {"geometry": time.perf_counter() - t}
    truth = st.jones(d, times, scans, fields, within)
    gauge = st.casa_gauge(truth, d.refant, d.freq, d.nu0)
    sky = st.target_sky(d)
    cal = st.calibrator_stokes(d)
    events = st.rfi_events(d, len(times))
    scan_list = [int(s) for s in args.scans.split(",")] if args.scans else []
    keep = select(d, times, scans, scan_list, args.max_per_scan)
    nant = len(names)
    a1, a2 = np.triu_indices(nant, 1)
    nbl = len(a1)
    nrow = nbl * len(keep)
    print(
        json.dumps(
            {
                "ms": str(ms),
                "nrow": nrow,
                "nint": len(keep),
                "gb_estimate": nrow * bytes_per_row(d.nchan) / 1e9,
            }
        ),
        flush=True,
    )
    _STATE.update(
        design=d,
        truth=truth,
        q=q,
        uvw=uvw,
        a1=a1.astype(np.int64),
        a2=a2.astype(np.int64),
        fields=fields,
        sky=sky,
        cal=cal,
        events=events,
        enu=st.enu_baselines(d),
        noiseless=args.noiseless,
    )
    if not args.noiseless and not args.scans and not args.max_per_scan:
        np.savez_compressed(
            out / "truth.npz",
            **truth_arrays(d, truth, gauge, q, elev, uvw, times, scans, fields, within),
        )
        st.write_json(
            out / "truth.json",
            {
                "design": d.as_json(),
                "fields": [
                    {
                        "name": f[0],
                        "ra_deg": f[1],
                        "dec_deg": f[2],
                        "role": f[3],
                        "intent": f[4],
                    }
                    for f in st.FIELDS
                ],
                "calibrators": {
                    "fcal": "1934-638, Stevens-Reynolds 2016 (rang.fluxstd, setjy-equal), point at the phase centre",
                    "xcal": st.XCAL,
                    "gcal": d.extra.get("gcal", st.GCAL),
                },
                "target_components": sky,
                "rfi_events": events,
                "antenna_names": names,
                "conventions": st.__doc__,
                "gauge": {
                    "refant": d.refant,
                    "refant_name": names[d.refant],
                    "tau_c_ns_raw": d.tau_c_ns,
                    "tau_c_ns_casa_gauge": d.tau_c_ns + gauge["tau_c_eff_ns_from_k"],
                },
            },
        )
    tab = create_ms(ms, nrow, d.nchan)
    tab.close()
    fill_subtables(ms, d, names, xyz, diameter, times, fields)
    tab = tables.table(str(ms), readonly=False)
    step = args.chunk_ints
    jobs = [keep[i : i + step] for i in range(0, len(keep), step)]
    w = np.float32(1.0 / d.sigma**2)
    masks_any, masks_5s = [], []
    seconds.update(predict=0.0, compute=0.0, write=0.0)
    t_loop = time.perf_counter()
    ctx = mp.get_context("fork")
    r0 = 0
    with ctx.Pool(args.workers) as pool:
        for job, res in zip(jobs, pool.imap(_chunk, jobs), strict=True):
            n = len(job) * nbl
            seconds["predict"] += res["predict_s"]
            seconds["compute"] += res["seconds"]
            s = time.perf_counter()
            tix = np.repeat(times[job], nbl)
            tab.putcol("UVW", res["uvw"], r0, n)
            tab.putcol("DATA", res["data"], r0, n)
            tab.putcol("WEIGHT_SPECTRUM", np.full((n, d.nchan, 4), w), r0, n)
            tab.putcol("FLAG", np.zeros((n, d.nchan, 4), bool), r0, n)
            tab.putcol("WEIGHT", np.full((n, 4), w), r0, n)
            tab.putcol("SIGMA", np.full((n, 4), np.float32(d.sigma)), r0, n)
            tab.putcol("TIME", tix, r0, n)
            tab.putcol("TIME_CENTROID", tix, r0, n)
            tab.putcol("ANTENNA1", np.tile(a1, len(job)).astype(np.int32), r0, n)
            tab.putcol("ANTENNA2", np.tile(a2, len(job)).astype(np.int32), r0, n)
            tab.putcol("INTERVAL", np.full(n, d.dt), r0, n)
            tab.putcol("EXPOSURE", np.full(n, d.dt), r0, n)
            tab.putcol("FLAG_ROW", np.zeros(n, bool), r0, n)
            per_row = {
                "FIELD_ID": np.repeat(fields[job], nbl),
                "STATE_ID": np.repeat(fields[job], nbl),
                "SCAN_NUMBER": np.repeat(scans[job], nbl),
            }
            for col, value in per_row.items():
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
            if res["mask_any"] is not None:
                masks_any.append(res["mask_any"])
                masks_5s.append(res["mask_5s"])
            seconds["write"] += time.perf_counter() - s
            r0 += n
    tab.close()
    seconds["loop"] = time.perf_counter() - t_loop
    mask_path = None
    rfi_stats = None
    if masks_any:
        ma, m5 = np.concatenate(masks_any), np.concatenate(masks_5s)
        mask_path = out / f"{name}.rfi_mask.npz"
        np.savez_compressed(
            mask_path,
            any=ma,
            above_5sigma=m5,
            nchan=d.nchan,
            row_tindex=np.repeat(keep, nbl),
            layout="np.packbits(mask[row, chan], axis=1)",
        )
        cells = nrow * d.nchan
        rfi_stats = {
            "cells": cells,
            "any": int(np.unpackbits(ma, axis=1, count=d.nchan).sum()),
            "above_5sigma": int(np.unpackbits(m5, axis=1, count=d.nchan).sum()),
        }
        rfi_stats["fraction_any"] = rfi_stats["any"] / cells
        rfi_stats["fraction_above_5sigma"] = rfi_stats["above_5sigma"] / cells
    seconds["total"] = time.perf_counter() - started
    files = sorted(p for p in ms.rglob("*") if p.is_file())
    ms_bytes = sum(p.stat().st_size for p in files)
    prov = {
        "task": "A1 simulated truth (research/a1-simtruth.md)",
        "ms": str(ms.resolve()),
        "name": name,
        "argv": sys.argv,
        "noiseless": args.noiseless,
        "selection": {
            "scans": scan_list,
            "max_per_scan": args.max_per_scan,
            "integrations": keep.tolist(),
        },
        "design": d.as_json(),
        "nrow": nrow,
        "nintegration": len(keep),
        "nbaseline": nbl,
        "ms_bytes": ms_bytes,
        "rfi": rfi_stats,
        "workers": args.workers,
        "chunk_integrations": step,
        "git": git_facts(),
        "versions": versions(),
        "writer": "rang.core_ms_write (rang's casacore table writer)",
        "seconds": seconds,
        "parallactic_range_deg": {
            st.FIELDS[f][0]: [
                float(np.degrees(q[fields == f]).min()),
                float(np.degrees(q[fields == f]).max()),
            ]
            for f in range(len(st.FIELDS))
        },
        "elevation_range_deg": {
            st.FIELDS[f][0]: [
                float(elev[fields == f].min()),
                float(elev[fields == f].max()),
            ]
            for f in range(len(st.FIELDS))
        },
    }
    hashed = {}
    for p in [out / "truth.npz", out / "truth.json", mask_path]:
        if p is not None and p.exists():
            hashed[p.name] = st.sha256_file(p)
    if args.hash_ms:
        for p in files:
            hashed[str(p.relative_to(out))] = st.sha256_file(p)
    prov["sha256"] = hashed
    st.write_json(out / f"{name}.provenance.json", prov)
    print(
        json.dumps({"ms_bytes": ms_bytes, "seconds": seconds, "rfi": rfi_stats}),
        flush=True,
    )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    versions = ["small", "full", "delay50", "holdout256", "holdout128", "w3"]
    g.add_argument("version", choices=versions)
    g.add_argument("outdir")
    g.add_argument("--workers", type=int, default=4)
    g.add_argument("--noiseless", action="store_true")
    g.add_argument("--scans", default="")
    g.add_argument("--max-per-scan", type=int, default=0)
    g.add_argument("--name", default="")
    g.add_argument("--hash-ms", action="store_true")
    g.add_argument("--seeds", default="")
    g.add_argument("--gcal-flux", type=float, default=None)
    g.add_argument("--gcal-spix", default="")
    g.add_argument("--gcal-reffreq", type=float, default=1.4e9)
    g.add_argument(
        "--chunk-ints",
        type=int,
        default=CHUNK_INTS,
        help="integrations per worker job (1 suits 4096 channels)",
    )
    s = sub.add_parser("size")
    s.add_argument("version", choices=versions)
    args = p.parse_args(argv)
    if args.cmd == "size":
        print(json.dumps(size(args.version), indent=1))
    else:
        generate(args)


if __name__ == "__main__":
    main()
