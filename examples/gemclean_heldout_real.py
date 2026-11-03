"""The ESO 137-006 pilot for the gemclean held-out test (research/gemclean-heldout.md).

Run with `python -I`: the inputs are untrusted downloads, and only numeric,
filter-free blosc arrays are ever decoded (`core_zarr.check_meta` refuses
object and pickle arrays).

    convert ZARR OUT.ms          raw DATA, FLAG, WEIGHT_SPECTRUM to an MS
    verify  ZARR OUT.ms OUT.json compare the MS with the Zarr source cell by cell
    gainload GAINS ZARR OUT.npz  the publisher's net gains on the pilot's grid
    gaincheck ZARR GAINS.npz OUT.json  coherence before and after, one convention each
    calibrate ZARR GAINS.npz OUT.ms [--raw]  XX, YY cross-correlations, corrected
    prep MS OUT_DIR --size --scale  Stokes I and Briggs 0.5 weights for scoring
    score PREP RUN OUT.json --job NAME ...  common-gridder metrics of each model
    compare PREP RUN OUT.json --job NAME ...  masks, compact sources, common-beam images
"""

import argparse
import importlib.util
import json
import math
import time
from pathlib import Path

import numpy as np
from rang import core_ms, core_weights, core_wgridder, core_zarr
from rang import core_ms_write as tables
from rang.core_imaging import read_fits
from scipy import ndimage

ARCSEC = math.pi / (180.0 * 3600.0)
CHAN0, CHAN1 = 640, 1152  # channel tiles 5-8 of the 4096-channel store
TILE = 128
ROW_CHUNK = 50_000
HERE = Path(__file__).resolve().parent


def _sim():
    spec = importlib.util.spec_from_file_location(
        "gemclean_bench_simulate", HERE / "gemclean_bench_simulate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_json(path, value):
    Path(path).write_text(
        json.dumps(value, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def decode(array_dir, key):
    """One numeric chunk as an array of its full chunk shape (or clipped)."""
    meta = core_zarr.array_meta(array_dir)
    raw = core_zarr.read_chunk(Path(array_dir) / key)
    a = np.frombuffer(raw, dtype=np.dtype(meta["dtype"]))
    return a, meta


def whole(array_dir):
    """A numeric array stored as chunk `0` (subtables, one chunk)."""
    a, meta = decode(array_dir, ".".join("0" * len(meta_of(array_dir)["shape"])))
    return a.reshape(chunk_shape(meta))


def meta_of(array_dir):
    return core_zarr.array_meta(array_dir)


def chunk_shape(meta):
    return [min(c, s) for c, s in zip(meta["chunks"], meta["shape"], strict=True)]


def rows_in_chunk(main, r):
    """A Zarr chunk is stored full size; the last one is padded with fill."""
    n = meta_of(main / "TIME")["shape"][0]
    return min(ROW_CHUNK, n - r * ROW_CHUNK)


def row_column(main, name, r):
    meta = meta_of(main / name)
    a, _ = decode(main / name, ".".join([str(r)] + ["0"] * (len(meta["shape"]) - 1)))
    extra = meta["shape"][1:]
    return a.reshape(-1, *extra)[: rows_in_chunk(main, r)]


def cube(main, name, r):
    """(rows, 512, 4) of a tiled column for row chunk r: tiles 5-8 joined."""
    parts = []
    for tile in range(CHAN0 // TILE, CHAN1 // TILE):
        a, _ = decode(main / name, f"{r}.{tile}.0")
        parts.append(a.reshape(-1, TILE, 4)[: rows_in_chunk(main, r)])
    return np.concatenate(parts, axis=1)


def main_group(root):
    return Path(root) / "MAIN" / "MAIN_0"


def subtable_arrays(root):
    root = Path(root)
    out = {
        "position": whole(root / "ANTENNA/ANTENNA_0/POSITION"),
        "diameter": whole(root / "ANTENNA/ANTENNA_0/DISH_DIAMETER"),
        "phase_dir": whole(root / "FIELD/FIELD_0/PHASE_DIR"),
    }
    spw = root / "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0"
    freq = whole(spw / "CHAN_FREQ").ravel()
    width = whole(spw / "CHAN_WIDTH").ravel()
    out["freq"] = freq[CHAN0:CHAN1]
    out["width"] = width[CHAN0:CHAN1]
    out["corr_type"] = whole(root / "POLARIZATION/POLARIZATION_0/CORR_TYPE").ravel()
    return out


def row_chunks(root):
    n = meta_of(main_group(root) / "TIME")["shape"][0]
    return n, math.ceil(n / ROW_CHUNK)


def new_ms(path, nrow, nchan, ncorr, freq, width, position, diameter, phase_dir, times):
    sim = _sim()
    t = sim.create_ms(path, nrow, nchan, ncorr)
    t.close()
    names = [f"ANT{i:02d}" for i in range(len(position))]
    dt = float(np.median(np.diff(np.unique(times))))
    ra, dec = float(phase_dir.ravel()[0]), float(phase_dir.ravel()[1])
    sim.fill_subtables(path, names, position, diameter, freq, ra, dec, times, dt)
    with tables.table(str(Path(path) / "SPECTRAL_WINDOW"), readonly=False) as s:
        s.putcell("CHAN_WIDTH", 0, width)
        s.putcell("EFFECTIVE_BW", 0, width)
        s.putcell("RESOLUTION", 0, width)
        s.putcol("TOTAL_BANDWIDTH", np.array([float(width.sum())]))
    with tables.table(str(Path(path) / "FIELD"), readonly=False) as s:
        s.putcol("NAME", np.array(["ESO137-pilot"]))
    with tables.table(str(Path(path) / "OBSERVATION"), readonly=False) as s:
        s.putcol("OBSERVER", np.array(["ratt-public-data ms1_target.zarr MAIN_0"]))
        s.putcol("PROJECT", np.array(["Ramatsoku et al. 2020, CC BY 4.0"]))
    if ncorr == 2:
        with tables.table(str(Path(path) / "POLARIZATION"), readonly=False) as s:
            s.putcol("NUM_CORR", np.array([2], np.int32))
            s.putcell("CORR_TYPE", 0, np.array([9, 12], np.int32))
            s.putcell("CORR_PRODUCT", 0, np.array([[0, 0], [1, 1]], np.int32))


SCALARS = (
    ("FIELD_ID", 0),
    ("DATA_DESC_ID", 0),
    ("SCAN_NUMBER", 2),
    ("ARRAY_ID", 0),
    ("OBSERVATION_ID", 0),
    ("FEED1", 0),
    ("FEED2", 0),
    ("PROCESSOR_ID", -1),
    ("STATE_ID", -1),
)


def put_row_columns(t, main, r, r0, keep=None):
    def col(name):
        a = row_column(main, name, r)
        return a if keep is None else a[keep]

    n = None
    for name in (
        "UVW",
        "TIME",
        "TIME_CENTROID",
        "ANTENNA1",
        "ANTENNA2",
        "INTERVAL",
        "EXPOSURE",
        "FLAG_ROW",
    ):
        a = col(name)
        n = len(a)
        t.putcol(name, a, r0, n)
    for name, value in SCALARS:
        t.putcol(name, np.full(n, value, np.int32), r0, n)
    return n


def convert(args):
    root, out = Path(args.zarr), Path(args.ms)
    main = main_group(root)
    sub = subtable_arrays(root)
    nrow, nchunks = row_chunks(root)
    times = np.concatenate([row_column(main, "TIME", r) for r in range(nchunks)])
    new_ms(
        out,
        nrow,
        CHAN1 - CHAN0,
        4,
        sub["freq"],
        sub["width"],
        sub["position"],
        sub["diameter"],
        sub["phase_dir"],
        np.unique(times),
    )
    t0 = time.perf_counter()
    with tables.table(str(out), readonly=False) as t:
        r0 = 0
        for r in range(nchunks):
            n = put_row_columns(t, main, r, r0)
            t.putcol("DATA", cube(main, "DATA", r), r0, n)
            t.putcol("FLAG", cube(main, "FLAG", r), r0, n)
            t.putcol("WEIGHT_SPECTRUM", cube(main, "WEIGHT_SPECTRUM", r), r0, n)
            t.putcol("WEIGHT", row_column(main, "WEIGHT", r), r0, n)
            t.putcol("SIGMA", row_column(main, "SIGMA", r), r0, n)
            r0 += n
            print(
                f"chunk {r + 1}/{nchunks} {time.perf_counter() - t0:.0f} s", flush=True
            )
    print("rows", r0, "seconds", time.perf_counter() - t0)


def verify(args):
    root, ms = Path(args.zarr), Path(args.ms)
    main = main_group(root)
    sub = subtable_arrays(root)
    nrow, nchunks = row_chunks(root)
    rec = {"zarr_rows": nrow, "checks": {}}
    with core_ms.open_table(ms) as t:
        rec["ms_rows"] = int(t.nrows)
        rec["rows_equal"] = rec["ms_rows"] == nrow
        eq = dict.fromkeys(
            ("UVW", "TIME", "ANTENNA1", "ANTENNA2", "DATA", "FLAG", "WEIGHT_SPECTRUM"),
            True,
        )
        flag_cells = 0
        cells = 0
        cross_flag = 0
        cross_cells = 0
        flag_by_chan = np.zeros(CHAN1 - CHAN0)
        cross_by_ant = np.zeros((len(sub["position"]), 2))
        rows_seen = 0
        nonfinite = 0
        r0 = 0
        rng = np.random.default_rng(20261103)
        spot = []
        for r in range(nchunks):
            data = cube(main, "DATA", r)
            flag = cube(main, "FLAG", r)
            weight = cube(main, "WEIGHT_SPECTRUM", r)
            n = data.shape[0]
            for name in ("UVW", "TIME", "ANTENNA1", "ANTENNA2"):
                eq[name] &= bool(
                    np.array_equal(row_column(main, name, r), t.getcol(name, r0, n))
                )
            ms_data = t.getcol("DATA", r0, n)
            eq["DATA"] &= bool(np.array_equal(data, ms_data, equal_nan=True))
            eq["FLAG"] &= bool(np.array_equal(flag, t.getcol("FLAG", r0, n)))
            eq["WEIGHT_SPECTRUM"] &= bool(
                np.array_equal(weight, t.getcol("WEIGHT_SPECTRUM", r0, n))
            )
            for _ in range(20):
                i, c, k = rng.integers(n), rng.integers(512), rng.integers(4)
                spot.append(
                    [
                        int(r0 + i),
                        int(c),
                        int(k),
                        str(complex(data[i, c, k])),
                        str(complex(ms_data[i, c, k])),
                    ]
                )
            del ms_data
            a1 = row_column(main, "ANTENNA1", r)
            a2 = row_column(main, "ANTENNA2", r)
            cross = a1 != a2
            flag_cells += int(flag.sum())
            cells += flag.size
            cross_flag += int(flag[cross].sum())
            cross_cells += flag[cross].size
            flag_by_chan += flag[cross].mean(axis=(0, 2)) * cross.sum()
            f_per_row = flag[cross].mean(axis=(1, 2))
            np.add.at(cross_by_ant[:, 0], a1[cross], f_per_row)
            np.add.at(cross_by_ant[:, 1], a1[cross], 1.0)
            np.add.at(cross_by_ant[:, 0], a2[cross], f_per_row)
            np.add.at(cross_by_ant[:, 1], a2[cross], 1.0)
            nonfinite += int((~np.isfinite(data)).sum())
            rows_seen += int(cross.sum())
            r0 += n
            print(f"chunk {r + 1}/{nchunks}", flush=True)
    rec["identical"] = eq
    rec["spot_visibilities"] = spot[:40]
    rec["spot_equal"] = all(s[3] == s[4] for s in spot)
    rec["flag_fraction_all"] = flag_cells / cells
    rec["flag_fraction_cross"] = cross_flag / cross_cells
    rec["flag_fraction_by_channel_cross"] = (flag_by_chan / rows_seen).round(4).tolist()
    rec["flag_fraction_by_antenna_cross"] = (
        (cross_by_ant[:, 0] / np.maximum(cross_by_ant[:, 1], 1)).round(4).tolist()
    )
    rec["data_nonfinite_cells"] = nonfinite
    rec["freq_first_last_hz"] = [float(sub["freq"][0]), float(sub["freq"][-1])]
    rec["phase_dir_rad"] = sub["phase_dir"].ravel().tolist()
    rec["corr_type"] = sub["corr_type"].tolist()
    rec["nant"] = len(sub["position"])
    _write_json(args.out, rec)
    print(
        {k: v for k, v in rec.items() if not k.startswith(("flag_fraction_by", "spot"))}
    )


def gainload(args):
    root = Path(args.gains) / "ESO137/ms1_gains.qc/GKB-net/GKB-net_0"
    gm = meta_of(root / "gains")
    fm = meta_of(root / "gain_flags")
    gtime = np.concatenate([decode(root / "gain_time", str(i))[0] for i in range(3)])
    gfreq = np.concatenate([decode(root / "gain_freq", str(i))[0] for i in (2, 3, 4)])
    if gm["dtype"] != "<c16" or fm["dtype"] != "|i1":
        raise SystemExit("unexpected gain dtype")
    nt, nf, na = gm["shape"][0], CHAN1 - CHAN0, gm["shape"][2]
    gains = np.zeros((nt, nf, na, 2), np.complex128)
    flags = np.zeros((nt, nf, na), bool)
    for ti, t0 in enumerate(range(0, nt, gm["chunks"][0])):
        n = min(gm["chunks"][0], nt - t0)
        for f in (2, 3, 4):
            f0 = f * gm["chunks"][1]
            g, _ = decode(root / "gains", f"{ti}.{f}.0.0.0")
            g = g.reshape(n, gm["chunks"][1], na, 1, 2)[:, :, :, 0]
            fl, _ = decode(root / "gain_flags", f"{ti}.{f}.0.0")
            fl = fl.reshape(n, gm["chunks"][1], na, 1)[:, :, :, 0]
            lo, hi = max(f0, CHAN0), min(f0 + gm["chunks"][1], CHAN1)
            gains[t0 : t0 + n, lo - CHAN0 : hi - CHAN0] = g[:, lo - f0 : hi - f0]
            flags[t0 : t0 + n, lo - CHAN0 : hi - CHAN0] = fl[:, lo - f0 : hi - f0] != 0
    sub = subtable_arrays(args.zarr)
    rec = {
        "gain_freq_vs_chan_freq_max_hz": float(
            np.abs(gfreq[CHAN0 - 512 : CHAN1 - 512] - sub["freq"]).max()
        ),
        "gain_times": len(gtime),
        "gain_flag_fraction": float(flags.mean()),
        "gain_nonfinite": int((~np.isfinite(gains)).sum()),
        "amp_median": float(np.median(np.abs(gains[~flags]))),
        "amp_p01_p99": [
            float(x) for x in np.percentile(np.abs(gains[~flags]), [1, 99])
        ],
    }
    main = main_group(args.zarr)
    t_rows = row_column(main, "TIME", 0)
    rec["gain_time_first_minus_row_time_first_s"] = float(gtime[0] - t_rows[0])
    print(rec)
    np.savez(args.out, gains=gains, flags=flags, gain_time=gtime, freq=sub["freq"])
    _write_json(str(args.out) + ".json", rec)


def time_index(gain_time, times):
    i = np.clip(np.searchsorted(gain_time, times), 0, len(gain_time) - 1)
    j = np.clip(i - 1, 0, len(gain_time) - 1)
    pick = np.where(np.abs(gain_time[j] - times) < np.abs(gain_time[i] - times), j, i)
    if np.abs(gain_time[pick] - times).max() > 1.0:
        raise SystemExit("a row has no gain within 1 s")
    return pick


def correct(data, flag, weight, gains, gflags, ti, a1, a2, hand, corr):
    """One hand: corrected visibilities, flags and weights, c = V/(g_p g_q*)."""
    gp = gains[ti, :, a1, hand]
    gq = gains[ti, :, a2, hand]
    if corr == "conjugate":
        prod = np.conj(gp) * gq
    else:
        prod = gp * np.conj(gq)
    bad = (
        gflags[ti, :, a1] | gflags[ti, :, a2] | ~np.isfinite(prod) | (np.abs(prod) == 0)
    )
    safe = np.where(bad, 1.0, prod)
    return data / safe, flag | bad, weight * np.abs(safe) ** 2


def gaincheck(args):
    """Coherence on row chunks 0 and 8: raw, corrected, and the other convention."""
    main = main_group(args.zarr)
    g = np.load(args.gains)
    gains, gflags, gtime = g["gains"], g["flags"], g["gain_time"]
    rec = {}
    for r in (0, 8):
        data = cube(main, "DATA", r)
        flag = cube(main, "FLAG", r)
        weight = cube(main, "WEIGHT_SPECTRUM", r)
        a1, a2 = row_column(main, "ANTENNA1", r), row_column(main, "ANTENNA2", r)
        times = row_column(main, "TIME", r)
        uvw = row_column(main, "UVW", r)
        keep = a1 != a2
        data, flag, weight = data[keep], flag[keep], weight[keep]
        a1, a2, times, uvw = a1[keep], a2[keep], times[keep], uvw[keep]
        ti = time_index(gtime, times)
        length = np.hypot(uvw[:, 0], uvw[:, 1])
        out = {}
        for name, corr in (
            ("raw", None),
            ("vis_over_gp_gqH", "qc"),
            ("other", "conjugate"),
        ):
            xx, fx, wx = data[..., 0], flag[..., 0], weight[..., 0]
            yy, fy, wy = data[..., 3], flag[..., 3], weight[..., 3]
            if corr:
                xx, fx, wx = correct(xx, fx, wx, gains, gflags, ti, a1, a2, 0, corr)
                yy, fy, wy = correct(yy, fy, wy, gains, gflags, ti, a1, a2, 1, corr)
            good = ~(fx | fy) & (wx > 0) & (wy > 0)
            # (a) XX-YY agreement per row, band-averaged over the good channels
            a = np.where(good, xx * np.conj(yy), 0).sum(axis=1)
            b = np.where(good, np.abs(xx * yy), 0).sum(axis=1)
            coh_xy = np.abs(a) / np.maximum(b, 1e-30)
            # (b) band coherence of Stokes I: |<I>_band| / <|I|>_band, 32 channels
            i_ = np.where(good, 0.5 * (xx + yy), 0)
            n = good.reshape(len(good), -1, 32).sum(axis=2)
            s = i_.reshape(len(good), -1, 32).sum(axis=2)
            m = np.abs(i_).reshape(len(good), -1, 32).sum(axis=2)
            coh_i = np.abs(s) / np.maximum(m, 1e-30)
            ok = n >= 16
            # (c) phase of the XX-YY band average on all rows
            ph = np.angle(a)
            short = length < 300.0
            out[name] = {
                "xx_yy_coherence_median": float(np.median(coh_xy)),
                "xx_yy_phase_abs_median_rad": float(np.median(np.abs(ph))),
                "xx_yy_phase_abs_median_short_rad": float(np.median(np.abs(ph[short]))),
                "stokes_i_32chan_coherence_median": float(np.median(coh_i[ok])),
                "stokes_i_32chan_coherence_median_short": float(
                    np.median(coh_i[ok & short[:, None]])
                ),
                "weighted_vector_avg_amp_short_jy": float(
                    np.abs(i_[short].sum() / np.maximum(good[short].sum(), 1))
                ),
                "good_fraction": float(good.mean()),
                "xx_over_yy_amp_median": float(
                    np.median(np.abs(xx[good]) / np.maximum(np.abs(yy[good]), 1e-30))
                ),
            }
        rec[f"row_chunk_{r}"] = out
        print(r, json.dumps(out, indent=0), flush=True)
        del data, flag, weight
    _write_json(args.out, rec)


def calibrate(args):
    """XX, YY and cross-correlations only; DATA is corrected unless --raw."""
    root, out = Path(args.zarr), Path(args.ms)
    main = main_group(root)
    sub = subtable_arrays(root)
    _, nchunks = row_chunks(root)
    g = np.load(args.gains)
    gains, gflags, gtime = g["gains"], g["flags"], g["gain_time"]
    extra = None
    if args.extra_flags:
        extra = np.load(args.extra_flags)["flags"]
    a = [
        row_column(main, n, r) for n in ("ANTENNA1", "ANTENNA2") for r in range(nchunks)
    ]
    a1 = np.concatenate(a[:nchunks])
    a2 = np.concatenate(a[nchunks:])
    ncross = int((a1 != a2).sum())
    times = np.concatenate([row_column(main, "TIME", r) for r in range(nchunks)])
    new_ms(
        out,
        ncross,
        CHAN1 - CHAN0,
        2,
        sub["freq"],
        sub["width"],
        sub["position"],
        sub["diameter"],
        sub["phase_dir"],
        np.unique(times),
    )
    t0 = time.perf_counter()
    stats = {"flag_cells": 0, "cells": 0, "gain_new_flag_cells": 0}
    with tables.table(str(out), readonly=False) as t:
        r0 = 0
        for r in range(nchunks):
            b1 = row_column(main, "ANTENNA1", r)
            b2 = row_column(main, "ANTENNA2", r)
            keep = b1 != b2
            n = put_row_columns(t, main, r, r0, keep)
            data = cube(main, "DATA", r)[keep][..., [0, 3]]
            flag = cube(main, "FLAG", r)[keep][..., [0, 3]]
            weight = cube(main, "WEIGHT_SPECTRUM", r)[keep][..., [0, 3]]
            before = int(flag.sum())
            if not args.raw:
                ti = time_index(gtime, row_column(main, "TIME", r)[keep])
                b1, b2 = b1[keep], b2[keep]
                for hand in range(2):
                    d, f, w = correct(
                        data[..., hand],
                        flag[..., hand],
                        weight[..., hand],
                        gains,
                        gflags,
                        ti,
                        b1,
                        b2,
                        hand,
                        "qc",
                    )
                    data[..., hand], flag[..., hand], weight[..., hand] = d, f, w
            if extra is not None:
                flag |= extra[r0 : r0 + n][..., None]
            stats["flag_cells"] += int(flag.sum())
            stats["cells"] += flag.size
            stats["gain_new_flag_cells"] += int(flag.sum()) - before
            t.putcol("DATA", data, r0, n)
            t.putcol("FLAG", flag, r0, n)
            t.putcol("WEIGHT_SPECTRUM", weight, r0, n)
            med = np.median(np.where(flag, np.nan, weight), axis=1)
            med = np.nan_to_num(med, nan=0.0).astype(np.float32)
            t.putcol("WEIGHT", med, r0, n)
            t.putcol(
                "SIGMA",
                np.where(med > 0, 1 / np.sqrt(np.maximum(med, 1e-30)), 1.0),
                r0,
                n,
            )
            r0 += n
            print(
                f"chunk {r + 1}/{nchunks} {time.perf_counter() - t0:.0f} s", flush=True
            )
    stats["flag_fraction"] = stats["flag_cells"] / stats["cells"]
    stats["rows"] = r0
    stats["seconds"] = time.perf_counter() - t0
    _write_json(str(out).rstrip("/") + ".json", stats)
    print(stats)


# -- common-gridder scoring -----------------------------------------------------


def prep(args):
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    with core_ms.open_table(args.ms) as t:
        nrow = int(t.nrows)
        uvw = np.ascontiguousarray(t.getcol("UVW"), np.float64)
        rows_ok = ~np.asarray(t.getcol("FLAG_ROW"), bool)
    with core_ms.open_table(str(Path(args.ms) / "SPECTRAL_WINDOW")) as s:
        freq = np.ascontiguousarray(s.getcol("CHAN_FREQ", 0, 1)[0], np.float64)
    nchan = freq.size
    vis = np.empty((nrow, nchan), np.complex64)
    wgt = np.empty((nrow, nchan), np.float32)
    with core_ms.open_table(args.ms) as t:
        for r0 in range(0, nrow, ROW_CHUNK):
            n = min(ROW_CHUNK, nrow - r0)
            d = t.getcol("DATA", r0, n)
            w = t.getcol("WEIGHT_SPECTRUM", r0, n)
            f = t.getcol("FLAG", r0, n)
            # stokes_i takes 4 correlations or 2: see below
            if d.shape[-1] == 2:
                full = lambda x: np.stack(
                    [x[..., 0], x[..., 0], x[..., 1], x[..., 1]], axis=-1
                )
                d, w, f = full(d), full(w), full(f)
            v, g = core_weights.stokes_i(d, w, f)
            vis[r0 : r0 + n] = v
            wgt[r0 : r0 + n] = g
    pad = core_weights.padded_size(args.size)
    imaging = core_weights.imaging_weights(
        uvw,
        core_weights.wsclean_wavelengths(freq),
        wgt,
        rows_ok,
        mode="briggs",
        robust=args.robust,
        width=pad,
        height=pad,
        pixel_scale=core_weights.pixel_scale_radians(args.scale),
        return_grid=False,
    )
    gw = wgt * imaging["weights"].astype(np.float32)
    gw[~rows_ok] = 0.0
    total = float(gw.sum(dtype=np.float64))
    q0 = 0.0
    for r0 in range(0, nrow, ROW_CHUNK):
        v = vis[r0 : r0 + ROW_CHUNK]
        q0 += float(np.sum(gw[r0 : r0 + ROW_CHUNK].astype(np.float64) * np.abs(v) ** 2))
    q0 *= 0.5 / total
    meta = {
        "ms": str(Path(args.ms).resolve()),
        "size": args.size,
        "scale_arcsec": args.scale,
        "epsilon": args.epsilon,
        "robust": args.robust,
        "nrow": nrow,
        "nchan": nchan,
        "active_visibilities": int(np.count_nonzero(gw)),
        "visibilities": int(gw.size),
        "gridding_weight_sum": total,
        "q0": q0,
    }
    uvw.tofile(out / "uvw.f64")
    freq.tofile(out / "freq.f64")
    vis.tofile(out / "vis.c64")
    gw.tofile(out / "wgt.f32")
    _write_json(out / "meta.json", meta)
    print(meta)


class Exact:
    """Q and the exact residual through one gridder, in row blocks to bound memory."""

    def __init__(self, prep_dir):
        p = Path(prep_dir)
        self.meta = json.loads((p / "meta.json").read_text(encoding="utf-8"))
        n, c = self.meta["nrow"], self.meta["nchan"]
        self.size = self.meta["size"]
        self.uvw = np.fromfile(p / "uvw.f64").reshape(n, 3)
        self.freq = np.fromfile(p / "freq.f64")
        self.vis = np.fromfile(p / "vis.c64", np.complex64).reshape(n, c)
        self.wgt = np.fromfile(p / "wgt.f32", np.float32).reshape(n, c)
        self.total = self.meta["gridding_weight_sum"]
        scale = self.meta["scale_arcsec"] * ARCSEC
        self.kw = {
            "pixsize_x": scale,
            "pixsize_y": scale,
            "epsilon": self.meta["epsilon"],
            "flip_v": True,
            "flip_w": True,
        }

    def score(self, model, block=120_000):
        m = np.ascontiguousarray(model.T, np.float64)
        q = 0.0
        r = np.zeros((self.size, self.size))
        for r0 in range(0, self.meta["nrow"], block):
            uvw = self.uvw[r0 : r0 + block]
            w = self.wgt[r0 : r0 + block].astype(np.float64) / self.total
            e = self.vis[r0 : r0 + block].astype(
                np.complex128
            ) - core_wgridder.dirty2vis(uvw=uvw, freq=self.freq, dirty=m, **self.kw)
            q += 0.5 * float(np.sum(w * np.abs(e) ** 2))
            r += core_wgridder.vis2dirty(
                uvw=uvw,
                freq=self.freq,
                vis=e,
                wgt=w,
                npix_x=self.size,
                npix_y=self.size,
                **self.kw,
            )
        return q, r.T


def mad_sigma(a):
    a = a[np.isfinite(a)]
    return 1.4826 * float(np.median(np.abs(a - np.median(a))))


def inner(size):
    k = size // 6
    return slice(k, size - k), slice(k, size - k)


def score(args):
    exact = Exact(args.prep)
    run = Path(args.run)
    out = Path(args.out_json)
    result = json.loads(out.read_text()) if out.exists() else {"jobs": {}}
    result["q0"] = exact.meta["q0"]
    ib = inner(exact.size)
    for name in args.job:
        if name in result["jobs"] and not args.force:
            continue
        s = time.perf_counter()
        model, _ = read_fits(run / f"{name}-model.fits")
        residual, _ = read_fits(run / f"{name}-residual.fits")
        q, er = exact.score(model)
        nz = model[model != 0]
        rec = {
            "q": q,
            "q_over_q0": q / exact.meta["q0"],
            "imager_residual_inner_peak_abs": float(np.abs(residual[ib]).max()),
            "imager_residual_inner_mad_sigma": mad_sigma(residual[ib]),
            "exact_residual_peak_abs": float(np.abs(er).max()),
            "exact_residual_inner_peak_abs": float(np.abs(er[ib]).max()),
            "exact_residual_inner_rms": float(np.sqrt(np.mean(er[ib] ** 2))),
            "exact_residual_inner_mad_sigma": mad_sigma(er[ib]),
            "exact_vs_imager_residual_inner_linf": float(
                np.abs(er[ib] - residual[ib]).max()
            ),
            "model_pixels": int(nz.size),
            "model_flux_total": float(nz.sum()),
            "model_flux_positive": float(nz[nz > 0].sum()),
            "model_flux_negative": float(nz[nz < 0].sum()),
            "score_seconds": time.perf_counter() - s,
        }
        np.save(run / f"{name}-exact-residual.npy", er.astype(np.float32))
        result["jobs"][name] = rec
        _write_json(out, result)
        print(name, json.dumps(rec), flush=True)


def dirtycheck(args):
    """The scorer's dirty image against WSClean's niter 0 image of the same MS."""
    exact = Exact(args.prep)
    q, dirty = exact.score(np.zeros((exact.size, exact.size)))
    ws, h = read_fits(f"{args.wsclean}-dirty.fits")
    peak = float(np.abs(ws).max())
    ib = inner(exact.size)
    rec = {
        "q0_check": q,
        "q0": exact.meta["q0"],
        "dirty_linf_over_peak": float(np.abs(dirty - ws).max()) / peak,
        "dirty_inner_linf_over_peak": float(np.abs(dirty[ib] - ws[ib]).max()) / peak,
        "wsclean_peak": peak,
        "core_peak": float(np.abs(dirty).max()),
        "wscnvis": h.get("WSCNVIS"),
        "active_visibilities": exact.meta["active_visibilities"],
        "wscimgwg": h.get("WSCIMGWG"),
        "gridding_weight_sum": exact.meta["gridding_weight_sum"],
    }
    _write_json(args.out_json, rec)
    print(rec)


def gaussian_kernel(size, fwhm_px):
    sigma = fwhm_px / (2 * math.sqrt(2 * math.log(2)))
    y, x = np.ogrid[-size // 2 : size // 2, -size // 2 : size // 2]
    return np.fft.ifftshift(np.exp(-0.5 * (x * x + y * y) / sigma**2))


def compare(args):
    """Common-beam images, the shared source mask, off-source metrics, compact flux."""
    run = Path(args.run)
    meta = json.loads((Path(args.prep) / "meta.json").read_text(encoding="utf-8"))
    size, scale = meta["size"], meta["scale_arcsec"]
    beam_px = args.beam_arcsec / scale
    ker = np.fft.rfft2(gaussian_kernel(size, beam_px))
    images, models, residuals = {}, {}, {}
    hdr = None
    for name in args.job:
        m, h = read_fits(run / f"{name}-model.fits")
        hdr = h
        models[name] = m.astype(np.float32)
        residuals[name] = np.load(run / f"{name}-exact-residual.npy")
        c = np.fft.irfft2(np.fft.rfft2(m) * ker, s=(size, size))
        images[name] = (c + residuals[name]).astype(np.float32)
    mean = sum(images.values()) / len(images)
    ib = inner(size)
    sigma = min(mad_sigma(residuals[n][ib]) for n in args.job)
    source = mean > args.mask_sigma * sigma
    radius = math.ceil(2 * beam_px)
    disk = np.hypot(*np.ogrid[-radius : radius + 1, -radius : radius + 1]) <= radius
    mask = ndimage.binary_dilation(source, structure=disk)
    off = ~mask
    box = np.zeros_like(off)
    box[ib] = True
    rec = {
        "beam_arcsec": args.beam_arcsec,
        "mask_sigma": args.mask_sigma,
        "sigma_used_jy": sigma,
        "source_mask_fraction_inner": float(mask[ib].mean()),
        "jobs": {},
    }
    for name in args.job:
        m, r = models[name], residuals[name]
        pick = off & box
        pick_all = off
        v = m[pick_all]
        rec["jobs"][name] = {
            "off_source_residual_rms": float(np.sqrt(np.mean(r[pick] ** 2))),
            "off_source_residual_mad_sigma": mad_sigma(r[pick]),
            "off_source_residual_peak_abs": float(np.abs(r[pick]).max()),
            "on_source_residual_rms": float(np.sqrt(np.mean(r[mask & box] ** 2))),
            "off_source_model_pixels": int(np.count_nonzero(v)),
            "off_source_model_abs_flux": float(np.abs(v).sum()),
            "off_source_model_flux": float(v.sum()),
            "off_source_model_negative_flux": float(v[v < 0].sum()),
            "on_source_model_flux": float(m[mask].sum()),
            "on_source_model_negative_flux": float(m[mask & (m < 0)].sum()),
            "on_source_model_pixels": int(np.count_nonzero(m[mask])),
        }
    # Compact sources: isolated peaks of the mean image, away from extended emission.
    label, _ = ndimage.label(mean > args.compact_sigma * sigma)
    objects = ndimage.find_objects(label)
    sources = []
    for i, sl in enumerate(objects):
        ny, nx = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if max(ny, nx) > 4 * beam_px:
            continue  # extended or blended
        sub = mean[sl] * (label[sl] == i + 1)
        k = np.unravel_index(np.argmax(sub), sub.shape)
        y, x = sl[0].start + k[0], sl[1].start + k[1]
        rad = math.ceil(2 * beam_px)
        if not (rad < y < size - rad - 1 and rad < x < size - rad - 1):
            continue
        yy, xx = np.ogrid[y - rad : y + rad + 1, x - rad : x + rad + 1]
        ap = (yy - y) ** 2 + (xx - x) ** 2 <= (1.5 * beam_px) ** 2
        fl = {}
        for name in args.job:
            cut = (slice(y - rad, y + rad + 1), slice(x - rad, x + rad + 1))
            area = 2 * math.pi * (beam_px / 2.3548) ** 2
            fl[name] = float(models[name][cut][ap].sum()) + float(
                residuals[name][cut][ap].sum() / area
            )
        sources.append(
            {
                "y": int(y),
                "x": int(x),
                "peak": float(mean[y, x]),
                "radius_deg": float(
                    math.hypot(y - size / 2, x - size / 2) * scale / 3600
                ),
                "flux": fl,
            }
        )
    rec["compact_sources"] = len(sources)
    ref = args.job[0]
    agree = {}
    for name in args.job[1:]:
        ratio = np.array(
            [s["flux"][name] / s["flux"][ref] for s in sources if s["flux"][ref] > 0]
        )
        peak = np.array([s["peak"] for s in sources if s["flux"][ref] > 0])
        bright = peak >= np.median(peak) if len(peak) else peak
        agree[f"{name}/{ref}"] = {
            "n": len(ratio),
            "median": float(np.median(ratio)) if len(ratio) else None,
            "mad_sigma": mad_sigma(ratio) if len(ratio) else None,
            "p05": float(np.percentile(ratio, 5)) if len(ratio) else None,
            "p95": float(np.percentile(ratio, 95)) if len(ratio) else None,
            "median_bright_half": float(np.median(ratio[bright]))
            if len(ratio)
            else None,
            "mad_sigma_bright_half": mad_sigma(ratio[bright]) if len(ratio) else None,
        }
    rec["compact_agreement"] = agree
    rec["brightest_compact"] = sorted(sources, key=lambda s: -s["peak"])[:15]
    _write_json(args.out_json, rec)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name in args.job:
        np.save(out / f"{name}-common-beam.npy", images[name])
    np.save(out / "source-mask.npy", mask)
    print(
        json.dumps({k: v for k, v in rec.items() if k != "brightest_compact"}, indent=1)
    )
    return hdr


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    s = p.add_subparsers(dest="cmd", required=True)
    a = s.add_parser("convert")
    a.add_argument("zarr")
    a.add_argument("ms")
    a = s.add_parser("verify")
    a.add_argument("zarr")
    a.add_argument("ms")
    a.add_argument("out")
    a = s.add_parser("gainload")
    a.add_argument("gains")
    a.add_argument("zarr")
    a.add_argument("out")
    a = s.add_parser("gaincheck")
    a.add_argument("zarr")
    a.add_argument("gains")
    a.add_argument("out")
    a = s.add_parser("calibrate")
    a.add_argument("zarr")
    a.add_argument("gains")
    a.add_argument("ms")
    a.add_argument("--raw", action="store_true")
    a.add_argument("--extra-flags")
    a = s.add_parser("prep")
    a.add_argument("ms")
    a.add_argument("out_dir")
    a.add_argument("--size", type=int, required=True)
    a.add_argument("--scale", type=float, required=True)
    a.add_argument("--robust", type=float, default=0.5)
    a.add_argument("--epsilon", type=float, default=1e-7)
    a = s.add_parser("dirtycheck")
    a.add_argument("prep")
    a.add_argument("wsclean")
    a.add_argument("out_json")
    a = s.add_parser("score")
    a.add_argument("prep")
    a.add_argument("run")
    a.add_argument("out_json")
    a.add_argument("--job", nargs="+", required=True)
    a.add_argument("--force", action="store_true")
    a = s.add_parser("compare")
    a.add_argument("prep")
    a.add_argument("run")
    a.add_argument("out_json")
    a.add_argument("out_dir")
    a.add_argument("--job", nargs="+", required=True)
    a.add_argument("--beam-arcsec", type=float, required=True)
    a.add_argument("--mask-sigma", type=float, default=5.0)
    a.add_argument("--compact-sigma", type=float, default=10.0)
    args = p.parse_args(argv)
    {
        "convert": convert,
        "verify": verify,
        "gainload": gainload,
        "gaincheck": gaincheck,
        "calibrate": calibrate,
        "prep": prep,
        "dirtycheck": dirtycheck,
        "score": score,
        "compare": compare,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
