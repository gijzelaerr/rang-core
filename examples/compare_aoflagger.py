"""Frozen A-FLAG measures (research/a-flag-aoflagger.md, sections 2.3-2.6).

Usage:
    python examples/compare_aoflagger.py --outputs outputs --date 20261030 \
        --results research/results/a-flag-aoflagger.json --details outputs/aflag-<date>-NN-compare

Reads the archived task D oracle, the fresh port run and the A-FLAG run
directories (image record `-01`, Tricolour dump `-02`, isolated stages `-03`,
hybrid `-04`, chains `-05` port / `-06` mapped / `-07` tuned, port run `-08`,
port cost `-09`) and writes the derived numbers as JSON; per-baseline and
per-channel arrays go to `<details>/details.npz`.
"""

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/oracles/aoflagger"))
import st_bridge

CONTROLS = (
    "strategy-00-operational",
    "strategy-00-holdout_masked",
    "strategy-01-operational",
    "strategy-01-holdout_masked",
)
VARIANTS = ("mapped", "mapped_fix", "tuned", "tuned_plus", "s1")
PASSES = ("spec", "time", "freq")
ORACLE = "core-d-oracle-20261029-01/run"
HOST_RUN = "tv-caracal-wsl-20261029-01"


def file_sha256(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def time_field(text, key):
    """The value of one `/usr/bin/time -v` line."""
    line = next(ln for ln in text.splitlines() if key in ln)
    return line.strip().rsplit(": ", 1)[-1]


def components(new):
    """4-connected components of a `(ntime, nchan)` mask."""
    labels, count = ndimage.label(new)
    return labels, count


def windows_match(a_new, b_new):
    """RFI windows: per baseline, components of A matched by any cell of B."""
    total_a = matched_a = total_b = matched_b = 0
    for b in range(a_new.shape[0]):
        la, na = components(a_new[b])
        lb, nb = components(b_new[b])
        total_a += na
        total_b += nb
        if na:
            hit = np.unique(la[b_new[b] & (la > 0)])
            matched_a += hit.size
        if nb:
            hit = np.unique(lb[a_new[b] & (lb > 0)])
            matched_b += hit.size
    return {
        "a_windows": int(total_a),
        "b_windows": int(total_b),
        "a_matched_fraction": matched_a / total_a if total_a else None,
        "b_matched_fraction": matched_b / total_b if total_b else None,
    }


def stage_measures(a, b, before, autos):
    """A = AOFlagger-side stage flags, B = reference; `(nbl, ntime, nchan)`."""
    eligible = ~before
    a_new, b_new = a & eligible, b & eligible
    out = {}
    for part, sel in (("cross", ~autos), ("auto", autos), ("all", np.ones_like(autos))):
        e = eligible[sel]
        an, bn = a_new[sel], b_new[sel]
        n_e = int(e.sum())
        a_only = int((an & ~bn).sum())
        b_only = int((bn & ~an).sum())
        union = int((an | bn).sum())
        out[part] = {
            "eligible": n_e,
            "agree_fraction": 1.0 - (a_only + b_only) / n_e if n_e else None,
            "a_new": int(an.sum()),
            "b_new": int(bn.sum()),
            "a_only": a_only,
            "b_only": b_only,
            "jaccard_new": int((an & bn).sum()) / union if union else None,
        }
    diff = a_new != b_new
    per_bl_a = (a_new & ~b_new).sum(axis=(1, 2))
    per_bl_b = (b_new & ~a_new).sum(axis=(1, 2))
    per_chan = diff.sum(axis=(0, 1))
    top = np.argsort(per_chan)[::-1][:5]
    out["per_baseline_a_only"] = per_bl_a.tolist()
    out["per_baseline_b_only"] = per_bl_b.tolist()
    out["channels_with_difference"] = int((per_chan > 0).sum())
    out["top_channels"] = [[int(c), int(per_chan[c])] for c in top if per_chan[c] > 0]
    out["rfi_windows"] = windows_match(a_new, b_new)
    out["all_cells_equal"] = bool(np.array_equal(a, b))
    return out, {
        "per_channel": per_chan.astype(np.int32),
        "per_baseline_a_only": per_bl_a,
        "per_baseline_b_only": per_bl_b,
    }


def ladder(dump, hybrid, step, meta):
    """Kernel ladder per pass for one step: counts of flipped cells."""
    res = {}
    for pas in PASSES:
        key = f"{step}_{pas}"
        data = dump[f"{key}_data"]
        flags = dump[f"{key}_flags"]
        thr = dump[f"{key}_thr"]
        k0 = dump[f"{key}_out"]
        h1 = hybrid[f"{key}_H1"]
        h2 = hybrid[f"{key}_H2"]
        nbl, niter, nrow, nchan = data.shape
        windows = np.asarray(
            meta["windows_time"] if pas == "time" else meta["windows_freq"]
        )
        rho = meta["rho"]
        names = ("T", "K0n", "K1", "K2", "K3i", "K3", "K2v", "K3v")
        rungs = {name: np.zeros(data.shape, bool) for name in names}
        for b in range(nbl):
            for i in range(niter):
                if pas == "time":
                    values, valid, t = st_bridge.time_columns(data[b, i], thr[b, i])
                    z = st_bridge.normalise(values, t)
                    miss_in = np.asarray(flags[b, i], bool).T

                    def back(f):
                        return f.T
                else:
                    values, valid, t, index = st_bridge.chunk_columns(
                        data[b, i],
                        thr[b, i],
                        np.asarray(meta["freq_chunk_ends"]),
                        int(windows.max()),
                    )
                    z = st_bridge.normalise(values, t)
                    miss_in = st_bridge.chunk_missing(
                        flags[b, i], index, values.shape[1]
                    )

                    def back(f, index=index, nrow=nrow, nchan=nchan):
                        return st_bridge.chunk_flags_back(f, index, nrow, nchan)

                rungs["T"][b, i] = back(
                    st_bridge.tricolour_columns(values, valid, t, windows, rho)
                )
                rungs["K0n"][b, i] = back(
                    st_bridge.tricolour_in_ao_units(z, valid, windows, rho)
                )
                rungs["K1"][b, i] = back(
                    st_bridge.tricolour_in_ao_units(
                        z, valid, st_bridge.AO_LENGTHS, 4.0 / 3.0
                    )
                )
                rungs["K2"][b, i] = back(
                    st_bridge.exclusion_columns(z, valid, vertical=False)
                )
                rungs["K3i"][b, i] = back(
                    st_bridge.aoflagger_columns(
                        z, ~valid | miss_in, vertical=False, quirk=False
                    )
                )
                rungs["K3"][b, i] = back(
                    st_bridge.aoflagger_columns(z, ~valid | miss_in, vertical=False)
                )
                if pas != "time":
                    rungs["K2v"][b, i] = back(
                        st_bridge.exclusion_columns(z, valid, vertical=True)
                    )
                    rungs["K3v"][b, i] = back(
                        st_bridge.aoflagger_columns(z, ~valid | miss_in, vertical=True)
                    )
        inflag = np.asarray(flags, bool)

        def count(x, y, inflag=inflag):
            d = x != y
            return {
                "all": int(d.sum()),
                "not_input_flagged": int((d & ~inflag).sum()),
                "x_only": int((x & ~y).sum()),
                "y_only": int((y & ~x).sum()),
            }

        res[pas] = {
            "cells": int(data.size),
            "tricolour_flagged": int(k0.sum()),
            "validation_numpy_tricolour_vs_dump": count(rungs["T"], k0),
            "validation_K2_vs_H1": count(rungs["K2"], h1),
            "validation_K3_vs_H2": count(rungs["K3"], h2),
            "rung_normalisation_K0_to_K0n": count(rungs["K0n"], k0),
            "rung_lengths_rho_K0n_to_K1": count(rungs["K1"], rungs["K0n"]),
            "rung_clamp_to_exclude_K1_to_K2": count(rungs["K2"], rungs["K1"]),
            "rung_input_as_missing_K2_to_K3i": count(rungs["K3i"], rungs["K2"]),
            "rung_xright_quirk_K3i_to_K3": count(rungs["K3"], rungs["K3i"]),
            "tricolour_vs_H1": count(h1, k0),
            "tricolour_vs_H2": count(h2, k0),
        }
        if pas != "time":
            res[pas]["validation_K2v_vs_H1v"] = count(
                rungs["K2v"], hybrid[f"{key}_H1v"]
            )
            res[pas]["validation_K3v_vs_H2v"] = count(
                rungs["K3v"], hybrid[f"{key}_H2v"]
            )
            res[pas]["vertical_vs_horizontal_K3"] = count(rungs["K3v"], rungs["K3"])
            res[pas]["tricolour_vs_H2v"] = count(hybrid[f"{key}_H2v"], k0)
    return res


def chain_measures(a, b):
    d = a != b
    return {
        "agree_fraction": 1.0 - d.sum() / d.size,
        "a_only": int((a & ~b).sum()),
        "b_only": int((b & ~a).sum()),
        "equal": bool(not d.any()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outputs", type=Path, default=ROOT / "outputs")
    ap.add_argument("--date", default="20261030")
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--details", type=Path, required=True)
    ap.add_argument("--controls", nargs="*", default=list(CONTROLS))
    ap.add_argument(
        "--hybrid",
        default="10-hybrid",
        help="hybrid run (-04 is void, see the write-up)",
    )
    ap.add_argument(
        "--stages-fix",
        default="11-stages",
        help="post-hoc stages run with the fixed mapped Lua",
    )
    ap.add_argument(
        "--chain-fix",
        default="12-chain-mapped",
        help="post-hoc chain with the fixed mapped Lua",
    )
    ap.add_argument(
        "--s1",
        default="14-dump",
        help="dump run whose S1 uses the validated AOFlagger kernel model",
    )
    args = ap.parse_args()
    o = args.outputs
    run = {
        n: o / f"aflag-{args.date}-{n}"
        for n in (
            "01",
            "02-dump",
            "03-stages",
            "05-chain-port",
            "06-chain-mapped",
            "07-chain-tuned",
            "08-port",
            "09-port-cost",
        )
    }
    run["04-hybrid"] = o / f"aflag-{args.date}-{args.hybrid}"
    run["14-s1"] = o / f"aflag-{args.date}-{args.s1}"
    run["11-stages"] = o / f"aflag-{args.date}-{args.stages_fix}"
    run["12-chain-mapped"] = o / f"aflag-{args.date}-{args.chain_fix}"
    args.details.mkdir(parents=True, exist_ok=True)
    dump_receipt = json.loads((run["02-dump"] / "receipt.json").read_text())
    stages_receipt = json.loads((run["03-stages"] / "receipt.json").read_text())
    result = {
        "task": "A-FLAG",
        "protocol": "research/a-flag-aoflagger.md",
        "image": json.loads((run["01"] / "image.json").read_text()),
        "aoflagger_version": stages_receipt.get("aoflagger_version"),
        "lua_sha256": stages_receipt["lua"],
        "tricolour_dump": {
            "gate_pass": dump_receipt["gate_pass"],
            "tricolour_version": dump_receipt["tricolour_version"],
            "numpy": dump_receipt["numpy_version"],
            "numba": dump_receipt["numba_version"],
        },
        "port_equals_oracle": {},
        "stages": {},
        "kernel": {},
        "chain": {},
        "cost": {},
    }
    details = {}
    for label in args.controls:
        oracle = np.load(o / ORACLE / label / "stages.npz")
        names = list(oracle.files)
        port = np.load(run["08-port"] / label / "stages.npz")
        result["port_equals_oracle"][label] = all(
            np.array_equal(port[n], oracle[n]) for n in names
        )
        arrays = np.load(o / ORACLE / label / "arrays.npz")
        ubl = arrays["ubl"]
        autos = np.broadcast_to(
            (ubl[:, 1] == ubl[:, 2])[:, None, None], oracle[names[0]][:, 0].shape
        )
        s1 = np.load(run["14-s1"] / f"s1-{label}.npz")
        stage_sets = {
            v: np.load(run["03-stages"] / v / f"{label}.npz")
            for v in ("mapped", "tuned", "tuned_plus")
        }
        stage_sets["mapped_fix"] = np.load(run["11-stages"] / "mapped" / f"{label}.npz")
        fix_tuned = {
            v: np.load(run["11-stages"] / v / f"{label}.npz")
            for v in ("tuned", "tuned_plus")
        }
        result.setdefault("rerun_identical", {})[label] = all(
            np.array_equal(fix_tuned[v][n], stage_sets[v][n])
            for v in fix_tuned
            for n in fix_tuned[v].files
        )
        dump = np.load(run["02-dump"] / f"dump-{label}.npz")
        hybrid = np.load(run["04-hybrid"] / f"hybrid-{label}.npz")
        result["stages"][label] = {}
        result["kernel"][label] = {}
        for step, info in dump_receipt["controls"][label].items():
            name = info["name"]
            k = names.index(name)
            before = np.asarray(oracle[names[k - 1]][:, 0], bool)
            ref = np.asarray(oracle[name][:, 0], bool)
            entry = {}
            got = {v: np.asarray(stage_sets[v][name][:, 0], bool) for v in stage_sets}
            got["s1"] = np.asarray(s1[step][:, 0], bool)
            for v in VARIANTS:
                m, det = stage_measures(got[v], ref, before, autos)
                entry[f"{v}_vs_tricolour"] = m
                for key, arr in det.items():
                    details[f"{label}/{name}/{v}/{key}"] = arr
            # Bridges between rungs, on eligible cells (counts of differing cells).
            for a_name, b_name in (
                ("s1", "tuned_plus"),
                ("tuned", "tuned_plus"),
                ("tuned_plus", "mapped"),
                ("tuned_plus", "mapped_fix"),
                ("mapped", "mapped_fix"),
            ):
                d = (got[a_name] != got[b_name]) & ~before
                entry[f"bridge_{a_name}_vs_{b_name}"] = int(d.sum())
            entry["port_vs_tricolour_equal"] = bool(
                np.array_equal(np.asarray(port[name][:, 0], bool), ref)
            )
            entry["eligible"] = int((~before).sum())
            entry["tricolour_new"] = int((ref & ~before).sum())
            result["stages"][label][name] = entry
            result["kernel"][label][name] = ladder(dump, hybrid, step, info["meta"])
            print(label, name, "done", flush=True)
        # Chains (secondary).
        after = np.load(o / HOST_RUN / "native" / label / "after-native.npz")["FLAG"]
        port_final = np.load(run["08-port"] / label / "flags.npz")["FLAG"]
        chain = {}
        for variant, key in (
            ("port", "05-chain-port"),
            ("mapped", "06-chain-mapped"),
            ("tuned", "07-chain-tuned"),
            ("mapped_fix", "12-chain-mapped"),
        ):
            final = np.load(run[key] / f"{label}.npz")["FLAG"]
            chain[variant] = {
                "vs_after_native": chain_measures(final, after),
                "vs_port": chain_measures(final, port_final),
                "flag_fraction": float(final.mean()),
            }
        chain["after_native_fraction"] = float(after.mean())
        result["chain"][label] = chain
    # Cost.
    timings = stages_receipt["timings"]
    for label in args.controls:
        c = {}
        for variant in ("mapped", "tuned", "tuned_plus"):
            t = timings[f"{variant}/{label}"]
            c[f"aoflagger_{variant}"] = {
                "strategy_seconds": float(sum(t["job_seconds"].values())),
                "process_wall": t["wall"],
                "max_rss_mb": t["max_rss_kb"] / 1024,
                "cpu_percent": t["cpu_percent"],
                "docker_wall": t["docker_wall"],
            }
        for threads in ("1", "4"):
            rec = json.loads(
                (run["09-port-cost"] / f"port-{label}-rayon{threads}.json").read_text()
            )
            tt = (run["09-port-cost"] / f"time-{label}-rayon{threads}.txt").read_text()
            rss = time_field(tt, "Maximum resident")
            wall = time_field(tt, "Elapsed")
            cpu = time_field(tt, "Percent of CPU")
            c[f"port_rayon{threads}"] = {
                "core_seconds": rec["core_seconds"],
                "process_wall": wall,
                "max_rss_mb": int(rss) / 1024,
                "cpu_percent": cpu.strip(),
                "steps_equal_oracle": all(
                    v["equals_oracle"] for v in rec["steps"].values()
                ),
            }
        result["cost"][label] = c
    result["load"] = {
        "stages": stages_receipt.get("load"),
        "stages_end": stages_receipt.get("load_end"),
    }
    np.savez_compressed(
        args.details / "details.npz",
        **{k.replace("/", "__"): v for k, v in details.items()},
    )
    result["details_sha256"] = file_sha256(args.details / "details.npz")
    args.results.parent.mkdir(parents=True, exist_ok=True)
    args.results.write_text(json.dumps(result, indent=1, default=float) + "\n")
    print("wrote", args.results)


if __name__ == "__main__":
    main()
