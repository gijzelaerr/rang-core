"""A1: audit the station-bins the CARACal first pass empties (research/a1-rfi-audit.md).

Usage:
    python examples/audit_emptied_bins.py run {l1,l2} outputs/a1-rfi-audit-<date>-NN/<campaign>
    python examples/audit_emptied_bins.py summarise outputs/a1-rfi-audit-<date>-NN \
        [--archive research/results/a1-rfi-audit.json] [--figures research/figures]

`run` decodes a campaign's inputs with the campaign's own functions, rebuilds
the seed-7 split, reruns the Tricolour port (first pass and mild with per-step
stages, plus three counterfactual strategies), checks the reproduction gates
and writes per station-bin arrays (`bins.npz`) and `run.json`. Nothing but
counts, fractions and small per-bin arrays is written; no visibilities.
`summarise` turns the per-campaign outputs into the band, time, station and
baseline tables, the archive and the figures. Explanation only: no flags are
applied anywhere and no input is modified.
"""

import argparse
import datetime
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_campaign, core_flag
from rang import core_campaign_1830 as l2mod
from rang import core_campaign_array as l1mod
from rang.core_campaign import STRATEGIES, STRATEGY_DIR, array_sha256
from rang.core_workflow import gain_grid

ROOT = core_campaign.ROOT
NF = 64
WIDTH = 32
TILE = 128
BLOCK = 2048
Z_EDGES = [-np.inf, -5, -3, -1, 0, 1, 3, 5, 10, 20, 50, 100, np.inf]
LENGTH_BANDS = ((0, 200), (200, 1000), (1000, 3000), (3000, 9000))
CAMPAIGNS = {
    "l1": {
        "label": "L1 PKS 1934-638 (MAIN_1 row chunk 0)",
        "runs": {"l1": "outputs/luno-array-campaign-20261030-01"},
    },
    "l2": {
        "label": "L2 PKS 1830-211 (MAIN_2 scan 3)",
        "runs": {
            "l2-stored": "outputs/l2-1830-20261030-02-stored",
            "l2-scalar": "outputs/l2-1830-20261030-02-scalar",
        },
        "fetch": "outputs/l2-1830-20261030-01-fetch",
    },
}
ARMS = ("tricolour-firstpass", "tricolour-mild")
# Reference allocations (ITU Region 1, approximate edges), research/a1-rfi-audit.md.
BANDS = (
    ("GSM/LTE downlinks", 0.0, 960.0),
    ("DME/TACAN, SSR/ADS-B", 960.0, 1215.0),
    ("GNSS L5/E5a/E5b/B2/G3", 1164.0, 1215.0),
    ("GNSS L2/G2/E6/B3", 1215.0, 1300.0),
    ("aeronautical radionavigation / radar", 1300.0, 1350.0),
    ("fixed/mobile/radiolocation", 1350.0, 1400.0),
    ("radio astronomy (protected)", 1400.0, 1427.0),
    ("mobile IMT L-band / BSS-DAB", 1427.0, 1518.0),
    ("Inmarsat/MSS downlink", 1525.0, 1559.0),
    ("GPS L1/E1/G1", 1559.0, 1610.0),
    ("Iridium / Inmarsat uplink", 1616.0, 1660.5),
)
CATEGORY = {
    "flag_nans_zeros": "nan_zero",
    "apply_static_mask": "static_mask",
    "sum_threshold": "sum_threshold",
    "uvcontsub_flagger": "uvcontsub",
    "flag_autos": "autos",
    "combine_with_input_flags": "input",
}


def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def blocks(n, size=BLOCK):
    for start in range(0, n, size):
        yield slice(start, min(start + size, n))


def strategies():
    """The two shipped strategies and the three counterfactuals."""
    fp = core_flag.parse_strategy(
        (STRATEGY_DIR / STRATEGIES["tricolour-firstpass"]).read_text()
    )
    mild = core_flag.parse_strategy(
        (STRATEGY_DIR / STRATEGIES["tricolour-mild"]).read_text()
    )
    by_name = {s["name"]: s for s in fp}
    return {
        "tricolour-firstpass": (fp, True),
        "tricolour-mild": (mild, True),
        "firstpass-no-static-mask": (
            [s for s in fp if s["task"] != "apply_static_mask"],
            False,
        ),
        "static-mask-all-baselines": (
            [
                by_name["nan_dropouts_flag"],
                by_name["background_static_mask"],
                by_name["combine_with_input_flags"],
            ],
            False,
        ),
        "static-mask-uvrange": (
            [
                by_name["nan_dropouts_flag"],
                by_name["uvrange_static_mask"],
                by_name["combine_with_input_flags"],
            ],
            False,
        ),
    }


def load_campaign(name):
    """Decode a campaign's inputs and rebuild its state with the campaign code."""
    if name == "l1":
        arrays, rows, _ = l1mod.decode_inputs()
        extra = l1mod.decode_extra(rows)
    else:
        roots = l2mod.roots_for(l2mod.GROUP, ROOT / CAMPAIGNS["l2"]["fetch"])
        arrays, rows, _ = l2mod.decode_inputs(l2mod.GROUP, roots)
        extra = l2mod.decode_extra(l2mod.GROUP, rows, roots)
        # The stored model arm leaves MODEL_DATA as stored; the scalar arm
        # splits the same samples (the archived split hashes are equal).
    nant = len(extra["antenna_names"])
    state = l1mod.build_state(arrays, extra, nant)
    del arrays
    return state, extra


def station_bins(cells, tb, p, q, nt, nant, weights=None):
    """Count `cells` (nrow, nchan) per (time bin, block, station) over p and q rows."""
    out = np.zeros((nt, NF, nant), np.int64)
    f = np.arange(NF)[None, :]
    for s in blocks(len(cells)):
        c = cells[s].reshape(-1, NF, WIDTH).sum(-1, dtype=np.int64)
        np.add.at(out, (tb[s][:, None], f, p[s][:, None]), c)
        np.add.at(out, (tb[s][:, None], f, q[s][:, None]), c)
    return out


def station_bin_max(values, cells, tb, p, q, nt, nant):
    out = np.full((nt, NF, nant), -np.inf)
    f = np.arange(NF)[None, :]
    for s in blocks(len(cells)):
        v = np.where(cells[s], values[s], -np.inf).reshape(-1, NF, WIDTH).max(-1)
        np.maximum.at(out, (tb[s][:, None], f, p[s][:, None]), v)
        np.maximum.at(out, (tb[s][:, None], f, q[s][:, None]), v)
    return out


def row_index(result, p, q, times):
    lookup = {(int(a), int(b)): i for i, (a, b) in enumerate(result["ubl"])}
    bl = np.array([lookup[(int(a), int(b))] for a, b in zip(p, q)], np.int64)
    return bl, np.asarray(result["time_inv"], np.int64)


def attribution(result, steps, bl, ti, nrow, nchan):
    """Per cell, the earliest step of the trailing run of set window flags that
    reaches the last flagging step (the one before `combine_with_input_flags`);
    -1 where that step leaves the cell unflagged."""
    names = list(result["stages"])
    last = (
        len(names) - 2
        if steps[-1]["task"] == "combine_with_input_flags"
        else len(names) - 1
    )
    attr = np.full((nrow, nchan), -1, np.int8)
    for s in blocks(nrow):
        run = np.ones((s.stop - s.start, nchan), bool)
        for k in range(last, -1, -1):
            run &= result["stages"][names[k]][bl[s], 0, ti[s]]
            attr[s][run] = k
            if not run.any():
                break
    return attr, names, last


def polarised_z(state, kept, bl, nbl):
    """Robust z of the polarised intensity per baseline and 128-channel tile,
    against the cells the first pass keeps (`kept`)."""
    data = state["data"]
    nrow, nchan = kept.shape
    pol = np.empty((nrow, nchan), np.float32)
    for s in blocks(nrow):
        d = data[s]
        qv = 0.5 * (d[..., 0] - d[..., 3])
        uv = 0.5 * (d[..., 1] + d[..., 2])
        vv = -0.5j * (d[..., 1] - d[..., 2])
        pol[s] = np.sqrt(np.abs(qv) ** 2 + np.abs(uv) ** 2 + np.abs(vv) ** 2)
    z = np.full((nrow, nchan), np.nan, np.float32)
    order = np.argsort(bl, kind="stable")
    bounds = np.flatnonzero(np.diff(np.r_[-1, bl[order], nbl + 1]))
    fallback = 0
    for t0 in range(0, nchan, TILE):
        cols = slice(t0, t0 + TILE)
        for i in range(len(bounds) - 1):
            r = order[bounds[i] : bounds[i + 1]]
            if not len(r):
                continue
            x = pol[r, cols]
            ref = x[kept[r, cols]]
            if ref.size < 20:
                ref = pol[:, cols][kept[:, cols]]
                fallback += 1
            if not ref.size:
                continue
            med = np.median(ref)
            mad = 1.4826 * np.median(np.abs(ref - med))
            if mad > 0:
                z[r, cols] = (x - med) / mad
    del pol
    return z, fallback


def histogram(values):
    v = values[np.isfinite(values)]
    counts, _ = np.histogram(v, bins=Z_EDGES)
    q = (
        np.quantile(v, [0.1, 0.25, 0.5, 0.75, 0.9, 0.99]).tolist()
        if v.size
        else [None] * 6
    )
    return {
        "n": int(v.size),
        "edges": [str(e) for e in Z_EDGES],
        "counts": counts.tolist(),
        "quantiles_10_25_50_75_90_99": q,
        "fraction_above_5": float(np.mean(v > 5)) if v.size else None,
    }


def run(name, out):
    out = Path(out)
    if out.exists():
        sys.exit(f"{out} exists; use a fresh directory")
    out.mkdir(parents=True)
    timings = {}
    t0 = time.perf_counter()
    state, extra = load_campaign(name)
    timings["decode_and_split"] = time.perf_counter() - t0
    nrow, nchan = state["train"].shape
    p, q = state["antenna1"].astype(np.int64), state["antenna2"].astype(np.int64)
    nant = len(state["names"])
    time_map, freq_map, gain_times, _ = gain_grid(state, *core_campaign.GRID)
    tb = np.asarray(time_map, np.int64)
    nt = len(gain_times)
    runs = {k: ROOT / v for k, v in CAMPAIGNS[name]["runs"].items()}
    archived = {k: json.loads((v / "result.json").read_text()) for k, v in runs.items()}
    first = next(iter(archived.values()))
    gates = {}
    counts = {
        k: int(np.count_nonzero(state[k]))
        for k in ("eligible", "train", "validation", "test")
    }
    gates["split_counts_equal"] = counts == first["split"]["counts"]
    if "sha256" in first["split"]:
        gates["split_sha256_equal"] = {
            k: array_sha256(state[k]) for k in counts
        } == first["split"]["sha256"]
    heldout = state["validation"] | state["test"]
    eligible = state["eligible"]
    input_any = state["original_flags"].any(-1)

    per = {}
    windows = {}
    record = {"campaign": name, "label": CAMPAIGNS[name]["label"], "strategies": {}}
    bl = ti = None
    for label, (steps, want_stages) in strategies().items():
        t1 = time.perf_counter()
        result = core_flag.flag_rows(
            state["data"],
            state["original_flags"],
            state["antenna1"],
            state["antenna2"],
            state["times"],
            extra["antenna_position"],
            state["frequencies"],
            extra["chan_width"],
            extra["corr_type"],
            steps,
            want_intensity=False,
            want_stages=want_stages,
        )
        wall = time.perf_counter() - t1
        window = np.ascontiguousarray(result["flags"][..., 0])
        rec = {
            "steps": [s["name"] for s in steps],
            "wall_seconds": wall,
            "window_flag_fraction": float(window.mean()),
            "new_cells": int(np.count_nonzero(window & ~input_any)),
            "additions_on_train": int(np.count_nonzero(window & state["train"])),
        }
        if bl is None:
            bl, ti = row_index(
                result, state["antenna1"], state["antenna2"], state["times"]
            )
            nbl = len(result["ubl"])
            ntime = int(ti.max()) + 1
        if want_stages:
            attr, names, last = attribution(result, steps, bl, ti, nrow, nchan)
            rec["stage_names"] = names
            rec["last_flagging_step"] = names[last]
            fractions = [float(result["stages"][n].mean()) for n in names]
            rec["stage_fractions"] = fractions
            new = window & ~input_any
            rec["new_cells_without_attribution"] = int(
                np.count_nonzero(new & (attr < 0))
            )
            per[label] = {"attr": attr, "names": names}
        if label in ARMS:
            stored = np.load(next(iter(runs.values())) / "flags" / f"{label}.npz")[
                "additions"
            ]
            gates[f"{label}_additions_equal"] = bool(
                np.array_equal(stored, window & state["train"])
            )
            for k, v in list(runs.items())[1:]:
                other = np.load(v / "flags" / f"{label}.npz")["additions"]
                gates[f"{label}_additions_equal_{k}"] = bool(
                    np.array_equal(other, window & state["train"])
                )
        windows[label] = window
        record["strategies"][label] = rec
        del result
        timings[f"flag_{label}"] = wall
        print(label, f"{wall:.1f} s", rec["additions_on_train"], flush=True)

    t1 = time.perf_counter()
    arrays = {}
    arrays["cells"] = station_bins(np.ones((nrow, nchan), bool), tb, p, q, nt, nant)
    arrays["input_flagged"] = station_bins(input_any, tb, p, q, nt, nant)
    arrays["eligible"] = station_bins(eligible, tb, p, q, nt, nant)
    arrays["train"] = station_bins(state["train"], tb, p, q, nt, nant)
    arrays["heldout"] = station_bins(heldout, tb, p, q, nt, nant)
    for label, window in windows.items():
        key = label
        arrays[f"support_{key}"] = station_bins(
            state["train"] & ~window, tb, p, q, nt, nant
        )
        arrays[f"heldout_flagged_{key}"] = station_bins(
            heldout & window, tb, p, q, nt, nant
        )
    # Step attribution of removed training cells, per station-bin and step.
    for label, info in per.items():
        removed = state["train"] & windows[label]
        attr = info["attr"]
        arrays[f"attr_{label}"] = np.stack(
            [
                station_bins(removed & (attr == k), tb, p, q, nt, nant)
                for k in range(len(info["names"]))
            ]
        )
    timings["station_bins"] = time.perf_counter() - t1

    # (dump, channel) columns: rows at the dump that are input-unflagged
    # (eligible) and the fraction of them the strategy flags.
    t1 = time.perf_counter()
    columns = {}
    elig_col = np.zeros((ntime, nchan), np.int64)
    np.add.at(elig_col, ti, eligible.astype(np.int64))
    columns["eligible"] = elig_col
    for label in ARMS:
        c = np.zeros((ntime, nchan), np.int64)
        np.add.at(c, ti, (eligible & windows[label]).astype(np.int64))
        columns[label] = c
    timings["columns"] = time.perf_counter() - t1

    # Whole-column excision: removed training cells in emptied bins that lie on
    # (dump, channel) columns where the strategy flags >= 90 % / 100 % of the
    # input-unflagged cells.
    emptied_cells = {}
    for label in ARMS:
        support0 = arrays["train"]
        emptied = (support0 > 0) & (arrays[f"support_{label}"] == 0)
        removed = state["train"] & windows[label]
        frac = np.divide(
            columns[label], elig_col, out=np.zeros(elig_col.shape), where=elig_col > 0
        )
        inbin = np.zeros((nrow, nchan), bool)
        for s in blocks(nrow):
            e = (
                emptied[tb[s][:, None], np.arange(NF)[None], p[s][:, None]]
                | emptied[tb[s][:, None], np.arange(NF)[None], q[s][:, None]]
            )
            inbin[s] = np.repeat(e, WIDTH, axis=1)
        inbin &= removed
        col = frac[ti]
        emptied_cells[label] = inbin
        record["strategies"][label]["removed_in_emptied_bins"] = int(inbin.sum())
        record["strategies"][label]["removed_in_emptied_on_whole_columns"] = {
            "100%": int(np.count_nonzero(inbin & (col >= 1.0))),
            ">=90%": int(np.count_nonzero(inbin & (col >= 0.9))),
            ">=50%": int(np.count_nonzero(inbin & (col >= 0.5))),
        }
        record["strategies"][label]["removed_all_on_whole_columns"] = {
            "n": int(removed.sum()),
            "100%": int(np.count_nonzero(removed & (col >= 1.0))),
            ">=90%": int(np.count_nonzero(removed & (col >= 0.9))),
        }
        del col

    # Baseline lengths (physical, ECEF).
    pos = extra["antenna_position"]
    length = np.linalg.norm(pos[p] - pos[q], axis=1)
    lengths = {}
    for label in ARMS:
        removed = state["train"] & windows[label]
        per_row_in = emptied_cells[label].sum(1)
        per_row_removed = removed.sum(1)
        per_row_train = state["train"].sum(1)
        lengths[label] = [
            {
                "band_m": list(b),
                "train": int(per_row_train[(length >= b[0]) & (length < b[1])].sum()),
                "removed": int(
                    per_row_removed[(length >= b[0]) & (length < b[1])].sum()
                ),
                "removed_in_emptied_bins": int(
                    per_row_in[(length >= b[0]) & (length < b[1])].sum()
                ),
            }
            for b in LENGTH_BANDS
        ]
    record["baseline_length"] = lengths

    # Which baselines the uvrange static-mask step touched (from its stage).
    uv = windows["static-mask-uvrange"] & ~input_any
    rows_touched = uv.any(1)
    record["uvrange_static_mask_rows"] = {
        "rows_with_new_flags": int(rows_touched.sum()),
        "max_length_m": float(length[rows_touched].max())
        if rows_touched.any()
        else None,
        "min_length_untouched_m": float(length[~rows_touched].min()),
    }

    # Polarised-intensity z against the first pass's kept cells.
    t1 = time.perf_counter()
    kept = eligible & ~windows["tricolour-firstpass"]
    z, fallback = polarised_z(state, kept, bl, nbl)
    zrec = {"fallback_groups": fallback}
    for label in ARMS:
        removed = state["train"] & windows[label]
        inbin = emptied_cells[label]
        zrec[label] = {
            "removed_in_emptied_bins": histogram(z[inbin]),
            "removed_elsewhere": histogram(z[removed & ~inbin]),
            "kept_train": histogram(z[state["train"] & ~windows[label]]),
        }
        arrays[f"zmax_{label}"] = station_bin_max(z, removed, tb, p, q, nt, nant)
        arrays[f"z5_{label}"] = station_bins(removed & (z > 5), tb, p, q, nt, nant)
    record["polarised_z"] = zrec
    del z
    timings["polarised_z"] = time.perf_counter() - t1

    # Lost bins (archived gains) and the invalid-prediction gate.
    lost = {}
    for run_label, run_dir in runs.items():
        gv0 = np.load(run_dir / "gains" / "original.npz")["gain_valid"]
        arrays[f"gain_valid_original_{run_label}"] = gv0
        for label in ARMS:
            gv = np.load(run_dir / "gains" / f"{label}.npz")["gain_valid"]
            arrays[f"gain_valid_{label}_{run_label}"] = gv
            valid = l1mod.valid_prediction(state, gv, time_map, freq_map)
            got = {
                "validation": int(np.count_nonzero(state["validation"] & ~valid)),
                "test": int(np.count_nonzero(state["test"] & ~valid)),
            }
            want = archived[run_label]["arms"][label]["metrics"]["invalid_predictions"]
            gates[f"invalid_predictions_{label}_{run_label}"] = {
                "reproduced": got,
                "archived": {k: want[k] for k in got},
                "equal": got == {k: want[k] for k in got},
            }
            lost[f"{label}_{run_label}"] = int(np.count_nonzero(gv0 & ~gv))
            del valid
    record["lost_counts"] = lost
    record["gates"] = gates
    record["gates_pass"] = all(
        (v["equal"] if isinstance(v, dict) else v) for v in gates.values()
    )

    # Metadata.
    utimes = np.unique(state["times"])
    epoch = datetime.datetime(1858, 11, 17, tzinfo=datetime.timezone.utc)
    record["dumps_utc"] = [
        (epoch + datetime.timedelta(seconds=float(t))).isoformat() for t in utimes
    ]
    record["shape"] = [nrow, nchan]
    record["nant"] = nant
    record["stations"] = state["names"]
    record["stations_with_rows"] = sorted(set(p.tolist()) | set(q.tolist()))
    record["timings"] = timings
    record["max_rss_mb"] = rss_mb()
    np.savez_compressed(
        out / "bins.npz",
        chan_freq=state["frequencies"],
        chan_width=extra["chan_width"],
        gain_times=gain_times,
        columns_eligible=columns["eligible"],
        **{f"columns_{k}": v for k, v in columns.items() if k != "eligible"},
        **arrays,
    )
    (out / "run.json").write_text(json.dumps(record, indent=1))
    print(json.dumps({"gates": gates, "gates_pass": record["gates_pass"]}, indent=1))
    print("timings", json.dumps(timings), "max_rss_mb", rss_mb())


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("campaign", choices=sorted(CAMPAIGNS))
    r.add_argument("out")
    s = sub.add_parser("summarise")
    s.add_argument("out_root")
    s.add_argument("--archive", default=None)
    s.add_argument("--figures", default=None)
    args = parser.parse_args()
    if args.command == "run":
        run(args.campaign, args.out)
    else:
        summarise(args.out_root, args.archive, args.figures)


def static_channels(freq, width):
    """Channels the shipped static masks flag, with the port's rule."""
    masked = np.zeros(len(freq), bool)
    for path in core_flag.static_mask_files():
        m = np.sort(core_flag.load_static_mask(path))
        lo, hi = freq - width / 2, freq + width / 2
        idx = np.searchsorted(m, lo, side="left")
        ok = idx < len(m)
        masked |= ok & (m[np.minimum(idx, len(m) - 1)] < hi)
    return masked


def runs_of(mask, freq, width):
    out = []
    i = 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j + 1 < len(mask) and mask[j + 1]:
                j += 1
            out.append(
                [
                    round(float(freq[i] - width[i] / 2) / 1e6, 2),
                    round(float(freq[j] + width[j] / 2) / 1e6, 2),
                ]
            )
            i = j + 1
        else:
            i += 1
    return out


def block_edges(freq, width):
    lo = (freq - width / 2).reshape(NF, WIDTH)[:, 0] / 1e6
    hi = (freq + width / 2).reshape(NF, WIDTH)[:, -1] / 1e6
    return lo, hi


def bands_of(lo, hi):
    return [b for b, a, c in BANDS if lo < c and hi > a]


def summarise_campaign(d):
    b = dict(np.load(d / "bins.npz"))
    r = json.loads((d / "run.json").read_text())
    freq, width = b["chan_freq"], b["chan_width"]
    lo, hi = block_edges(freq, width)
    static = static_channels(freq, width)
    static_block = static.reshape(NF, WIDTH).mean(1)
    names = r["stations"]
    train = b["train"]
    out = {
        "label": r["label"],
        "shape": r["shape"],
        "dumps_utc": [r["dumps_utc"][0], r["dumps_utc"][-1]],
        "ndumps": len(r["dumps_utc"]),
        "gates": r["gates"],
        "gates_pass": r["gates_pass"],
        "timings": r["timings"],
        "max_rss_mb": r["max_rss_mb"],
        "static_mask_ranges_in_window_mhz": runs_of(static, freq, width),
        "static_mask_channels_in_window": int(static.sum()),
        "station_bins": int(train.size),
        "station_bins_without_input_support": int(np.count_nonzero(train == 0)),
        "stations_without_rows": [
            names[i] for i in range(len(names)) if i not in r["stations_with_rows"]
        ],
        "uvrange_static_mask_rows": r["uvrange_static_mask_rows"],
        "polarised_z": r["polarised_z"],
        "baseline_length": r["baseline_length"],
        "strategies": {
            k: {
                kk: v[kk]
                for kk in (
                    "wall_seconds",
                    "window_flag_fraction",
                    "new_cells",
                    "additions_on_train",
                    "removed_in_emptied_bins",
                    "removed_in_emptied_on_whole_columns",
                    "removed_all_on_whole_columns",
                    "stage_fractions",
                    "new_cells_without_attribution",
                )
                if kk in v
            }
            for k, v in r["strategies"].items()
        },
        "arms": {},
    }
    emptied_sets = {}
    for arm in ARMS:
        emptied = (train > 0) & (b[f"support_{arm}"] == 0)
        emptied_sets[arm] = emptied
        n = int(emptied.sum())
        a = {"emptied_station_bins": n}
        # Array-wide: every station with support at (t, f) is emptied.
        supported = (train > 0).sum(2)
        nemp = emptied.sum(2)
        tf = nemp > 0
        a["time_freq_cells_with_emptied"] = int(tf.sum())
        a["emptied_in_array_wide_cells"] = int(nemp[tf & (nemp == supported)].sum())
        a["stations_emptied_per_cell_quantiles_min_50_max"] = (
            [int(nemp[tf].min()), float(np.median(nemp[tf])), int(nemp[tf].max())]
            if tf.any()
            else None
        )
        a["supported_stations_per_cell_median"] = (
            float(np.median(supported[tf])) if tf.any() else None
        )
        # By frequency block.
        per_block = emptied.sum((0, 2))
        a["by_block"] = [
            {
                "block": int(f),
                "mhz": [round(float(lo[f]), 2), round(float(hi[f]), 2)],
                "emptied": int(per_block[f]),
                "static_mask_fraction": round(float(static_block[f]), 3),
                "bands": bands_of(lo[f], hi[f]),
                "input_flagged_fraction": round(
                    float(b["input_flagged"][:, f].sum() / b["cells"][:, f].sum()), 4
                ),
            }
            for f in range(NF)
            if per_block[f]
        ]
        band_rows = []
        for label, blo, bhi in BANDS:
            sel = (lo < bhi) & (hi > blo)
            band_rows.append(
                {
                    "band": label,
                    "mhz": [blo, bhi],
                    "blocks_in_window": int(sel.sum()),
                    "emptied": int(per_block[sel].sum()),
                    "blocks_with_emptied": int(np.count_nonzero(per_block[sel])),
                }
            )
        none = np.array([not bands_of(lo[f], hi[f]) for f in range(NF)])
        band_rows.append(
            {
                "band": "no listed allocation",
                "blocks_in_window": int(none.sum()),
                "emptied": int(per_block[none].sum()),
                "blocks_with_emptied": int(np.count_nonzero(per_block[none])),
            }
        )
        a["by_band"] = band_rows
        sm = static_block > 0
        a["emptied_in_blocks_touching_static_mask"] = int(per_block[sm].sum())
        a["by_time_bin"] = emptied.sum((1, 2)).tolist()
        per_station = emptied.sum((0, 1))
        a["by_station"] = {
            names[i]: int(per_station[i])
            for i in np.argsort(-per_station)
            if per_station[i]
        }
        # Input flags already covering the emptied station-bins.
        a["input_flagged_fraction_emptied"] = (
            float(b["input_flagged"][emptied].sum() / b["cells"][emptied].sum())
            if n
            else None
        )
        sup = train > 0
        a["input_flagged_fraction_all_supported"] = float(
            b["input_flagged"][sup].sum() / b["cells"][sup].sum()
        )
        a["train_cells_in_emptied_quantiles_min_50_max"] = (
            [
                int(train[emptied].min()),
                float(np.median(train[emptied])),
                int(train[emptied].max()),
            ]
            if n
            else None
        )
        # Held-out cells of emptied bins that the strategy flags too.
        ho = b["heldout"][emptied].sum()
        a["heldout_in_emptied"] = int(ho)
        a["heldout_in_emptied_flagged_by_strategy"] = int(
            b[f"heldout_flagged_{arm}"][emptied].sum()
        )
        # Step attribution of removed training cells in emptied bins.
        steps = r["strategies"][arm]["stage_names"]
        attr = b[f"attr_{arm}"]
        cells = {s: int(attr[k][emptied].sum()) for k, s in enumerate(steps)}
        a["removed_by_step_in_emptied"] = {k: v for k, v in cells.items() if v}
        cats = {}
        for k, s in enumerate(steps):
            c = CATEGORY[s.split("-", 1)[1]]
            cats[c] = cats.get(c, 0) + int(attr[k][emptied].sum())
        a["removed_by_category_in_emptied"] = {k: v for k, v in cats.items() if v}
        bincat = {}
        for k, s in enumerate(steps):
            c = CATEGORY[s.split("-", 1)[1]]
            bincat.setdefault(c, np.zeros(train.shape, bool))
            bincat[c] |= attr[k] > 0
        sets = {}
        for idx in zip(*np.nonzero(emptied)):
            key = "+".join(sorted(c for c, m in bincat.items() if m[idx]))
            sets[key] = sets.get(key, 0) + 1
        a["emptied_bins_by_category_set"] = sets
        # Outliers of their own.
        zmax = b[f"zmax_{arm}"][emptied]
        a["emptied_with_max_z_above_5"] = int(np.count_nonzero(zmax > 5))
        a["emptied_without_own_outlier"] = int(
            np.count_nonzero(b[f"z5_{arm}"][emptied] == 0)
        )
        a["emptied_max_z_quantiles_10_50_90"] = (
            np.quantile(zmax[np.isfinite(zmax)], [0.1, 0.5, 0.9]).tolist()
            if n
            else None
        )
        # Lost (archived gains) against emptied.
        lost = {}
        for key, value in b.items():
            prefix = f"gain_valid_{arm}_"
            if key.startswith(prefix):
                run = key[len(prefix) :]
                gv0 = b[f"gain_valid_original_{run}"]
                lb = gv0 & ~value
                lost[run] = {
                    "lost": int(lb.sum()),
                    "emptied_and_lost": int((lb & emptied).sum()),
                    "lost_not_emptied": int((lb & ~emptied).sum()),
                    "emptied_not_lost": int((emptied & ~lb).sum()),
                    "emptied_where_original_gain_invalid": int((emptied & ~gv0).sum()),
                }
        a["lost_vs_emptied"] = lost
        out["arms"][arm] = a
    # Counterfactuals (first pass only): which strategy empties the same bins alone.
    fp = emptied_sets["tricolour-firstpass"]
    cf = {
        k: (train > 0) & (b[f"support_{k}"] == 0)
        for k in (
            "firstpass-no-static-mask",
            "static-mask-all-baselines",
            "static-mask-uvrange",
        )
    }
    static_alone = cf["static-mask-all-baselines"] | cf["static-mask-uvrange"]
    st_alone = cf["firstpass-no-static-mask"]
    out["counterfactual"] = {
        "emptied_by": {k: int(v.sum()) for k, v in cf.items()},
        "firstpass_emptied": int(fp.sum()),
        "static_alone_only": int((fp & static_alone & ~st_alone).sum()),
        "sumthreshold_alone_only": int((fp & st_alone & ~static_alone).sum()),
        "both_alone": int((fp & st_alone & static_alone).sum()),
        "only_together": int((fp & ~st_alone & ~static_alone).sum()),
        "no_mask_emptied_not_in_firstpass": int((st_alone & ~fp).sum()),
        "mild_emptied_subset_of_firstpass": int(
            (emptied_sets["tricolour-mild"] & ~fp).sum()
        )
        == 0,
        "mild_and_firstpass_emptied": int((emptied_sets["tricolour-mild"] & fp).sum()),
    }
    return out, emptied_sets, b, r


def summarise(out_root, archive, figures):
    out_root = Path(out_root)
    result = {
        "task": "A1 RFI-band audit (research/a1-rfi-audit.md)",
        "run_root": str(out_root),
        "ephemeris_check": "not done: no skyfield, sgp4 or TLE set offline",
        "allocation_bands_mhz": [[n, a, c] for n, a, c in BANDS],
        "campaigns": {},
    }
    sets, bins, runs = {}, {}, {}
    for name in ("l1", "l2"):
        d = out_root / name
        if (d / "run.json").exists():
            result["campaigns"][name], sets[name], bins[name], runs[name] = (
                summarise_campaign(d)
            )
    if len(sets) == 2:
        cross = {}
        for arm in ARMS:
            a = sets["l1"][arm].any(0)
            c = sets["l2"][arm].any(0)
            fa, fc = a.any(1), c.any(1)
            cross[arm] = {
                "block_station_l1": int(a.sum()),
                "block_station_l2": int(c.sum()),
                "block_station_both": int((a & c).sum()),
                "jaccard": float((a & c).sum() / max(1, (a | c).sum())),
                "blocks_l1": int(fa.sum()),
                "blocks_l2": int(fc.sum()),
                "blocks_both": int((fa & fc).sum()),
                "blocks_both_list": np.flatnonzero(fa & fc).tolist(),
            }
        result["cross_calibrator"] = cross
    text = json.dumps(result, indent=1)
    print(text)
    if archive:
        Path(archive).write_text(text + "\n")
    if figures:
        plot(bins, sets, Path(figures))


def plot(bins, sets, figdir):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figdir.mkdir(parents=True, exist_ok=True)
    blue, orange = "#2a78d6", "#eb6834"
    names = [n for n in ("l1", "l2") if n in bins]
    titles = {"l1": "L1 PKS 1934−638", "l2": "L2 PKS 1830−211"}
    fig, axes = plt.subplots(len(names), 1, figsize=(8, 2.6 * len(names)), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, n in zip(axes, names):
        b = bins[n]
        freq, width = b["chan_freq"], b["chan_width"]
        lo, hi = block_edges(freq, width)
        mid = (lo + hi) / 2
        static = static_channels(freq, width)
        for a0, a1 in runs_of(static, freq, width):
            ax.axvspan(a0, a1, color="#d9d9d4", lw=0, zorder=0)
        for edge in (1164, 1215, 1300):
            ax.axvline(edge, color="#8a8a85", lw=0.8, ls=":", zorder=1)
        w = (hi - lo) * 0.42
        fp = sets[n]["tricolour-firstpass"].sum((0, 2))
        mild = sets[n]["tricolour-mild"].sum((0, 2))
        ax.bar(mid - w / 2, fp, width=w, color=blue, label="first pass", zorder=2)
        ax.bar(mid + w / 2, mild, width=w, color=orange, label="mild", zorder=2)
        ax.set_ylabel("emptied\nstation-bins")
        ax.set_title(titles[n], loc="left", fontsize=10)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(axis="y", color="#ececea", lw=0.6)
        ax.set_axisbelow(True)
    axes[0].legend(frameon=False, fontsize=8, loc="upper right")
    axes[-1].set_xlabel(
        "frequency (MHz); grey: static-mask channels; dotted: 1164, 1215, 1300 MHz"
    )
    fig.tight_layout()
    fig.savefig(figdir / "a1-emptied-by-block.png", dpi=110)
    plt.close(fig)

    fig, axes = plt.subplots(1, len(names), figsize=(4.2 * len(names), 3.2))
    axes = np.atleast_1d(axes)
    for ax, n in zip(axes, names):
        b = bins[n]
        lo, hi = block_edges(b["chan_freq"], b["chan_width"])
        emp = sets[n]["tricolour-firstpass"].sum(2).astype(float)
        sup = (b["train"] > 0).sum(2)
        frac = np.where(emp > 0, emp / np.maximum(sup, 1), np.nan)
        im = ax.imshow(
            frac,
            aspect="auto",
            origin="lower",
            cmap="Blues",
            vmin=0,
            vmax=1,
            extent=[lo[0], hi[-1], -0.5, frac.shape[0] - 0.5],
            interpolation="nearest",
        )
        ax.set_title(titles[n] + ", first pass", loc="left", fontsize=10)
        ax.set_xlabel("frequency (MHz)")
        ax.set_ylabel("gain time bin (2 dumps)")
    fig.colorbar(im, ax=axes, label="fraction of supported stations emptied")
    fig.savefig(figdir / "a1-emptied-time-freq.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
