"""Host checker of task C4a (research/c4a-apply.md): the Rust apply kernel
(`rang.cal_apply`) against CASA `applycal` and `caltable.correct`.

    python examples/check_apply.py <run> [--heldout] [--predict] [--outputs <dir>]

`<run>` is a fresh `/mnt/d/rang/outputs/c4a-<date>-NN`; `<dir>` holds
O-CASA's `o-casa-20261030-01/c.ms`, E4's CASA tables
`e4-20261030-01/casa/x.{K,G,B,Df}` and DF-IO's `dfio-20261030-02/ct/casa/x.T`
(default `~/Github/rang/outputs`, read only). Writes the synthetic tables,
one `applycal` per case in `rang-o-casa:6.7.6.14` (DF-IO's container
conventions), `<run>/c4a.json` with the criteria and verdicts, and one
`<run>/export/<case>.npz` per case (CORRECTED_DATA and FLAG of the field);
the MS copies are then removed.

The default set is the frozen one of section 3 (runs -01, -02). `--heldout`
runs the held-out set of section 5, frozen before run -03. `--predict`
writes the kernel's flag counts for the chosen set without running CASA
(the predictions recorded in the note before -03).
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_formats as cf
from rang import cal_apply
from rang.formats import caltable

SEED_DF = 20261106
SEED_HELDOUT = 20261107
THREADS = (1, 2, 4, 16)
L = "linear"
# Held-out input-flag edits: (antenna1, antenna2, first channel, end
# channel, the one correlation left flagged); the other three are unflagged.
EDITS = [(0, 1, 500, 600, 0), (2, 3, 700, 800, 3)]


def synth_df(ms, nant, times, fid, posthoc=False):
    """The new seeded Df (protocol section 3): leakages about 0.05, a
    flagged channel range on antenna 2's d_x, antenna 1's d_y flagged in
    every channel. `posthoc` (added after run -01, which found CASA's Df
    flags per cross hand): the same leakages with antenna 0's d_x flagged in
    every channel, both of antenna 2's flagged in every channel and antenna
    3's d_y flagged in channels 1000-1099."""
    rng = np.random.default_rng(SEED_DF)
    full = caltable.subtables_from_ms(ms, single_channel=False)
    nchan = len(full["SPECTRAL_WINDOW"]["CHAN_FREQ"][0])
    d = 0.05 * (
        rng.standard_normal((1, nant, nchan, 2))
        + 1j * rng.standard_normal((1, nant, nchan, 2))
    )
    flag = np.zeros(d.shape, bool)
    if posthoc:
        flag[0, 0, :, 0] = True
        flag[0, 2, :, :] = True
        flag[0, 3, 1000:1100, 1] = True
    else:
        flag[0, 2, 300:420, 0] = True
        flag[0, 1, :, 1] = True
    return caltable.from_gains(
        "Df",
        [float(np.mean(times))],
        list(range(nant)),
        d,
        flag,
        subtables=full,
        field_id=fid,
        refant=0,
        ms_name="c.ms",
    )


def coarse_subtables(ms, step):
    """The MS subtables with every `step`-th channel as the solution grid."""
    full = caltable.subtables_from_ms(ms, single_channel=False)
    spw = dict(full["SPECTRAL_WINDOW"])
    nchan = len(spw["CHAN_FREQ"][0])
    for col in ("CHAN_FREQ", "CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"):
        if col in spw:
            spw[col] = [
                np.asarray(c)[::step] * (1 if col == "CHAN_FREQ" else step)
                for c in spw[col]
            ]
    spw["NUM_CHAN"] = [np.int32(len(range(0, nchan, step))) for _ in spw["NUM_CHAN"]]
    full["SPECTRAL_WINDOW"] = spw
    return full


def heldout_tables(ms, nant, times, fid, seed=SEED_HELDOUT):
    """The held-out tables of section 5 (seed 20261107 for run -03); with
    another seed (section 6, run -04) also `hGmany` (G at 9 slots with
    phases over the whole circle, which stresses phase tracking in time) and
    `hBgaps` (B on every 4th channel with random phases and three flagged
    gaps, which stresses the frequency unwrap)."""
    rng = np.random.default_rng(seed)
    full = caltable.subtables_from_ms(ms, single_channel=False)
    single = caltable.subtables_from_ms(ms, single_channel=True)
    nchan = len(full["SPECTRAL_WINDOW"]["CHAN_FREQ"][0])
    ants = list(range(nant))
    common = {"field_id": fid, "refant": 0, "ms_name": "c.ms"}

    def leak(nt):
        return 0.05 * (
            rng.standard_normal((nt, nant, nchan, 2))
            + 1j * rng.standard_normal((nt, nant, nchan, 2))
        )

    t2 = [float(times.min() + 60.0), float(times.max() - 60.0)]
    d2 = leak(2)
    f2 = np.zeros(d2.shape, bool)
    f2[0, 3, :, 1] = True  # slot 0: antenna 3's d_y in every channel
    f2[1, 0, 800:900, 0] = True  # slot 1: a bridged range
    mid = [float(np.mean(times))]
    ddx = leak(1)
    fdx = np.zeros(ddx.shape, bool)
    fdx[0, 3, :, 0] = True  # a lone d_x, antenna 3
    d0 = leak(1)
    tg = np.linspace(times.min(), times.max(), 3)
    g = (1 + 0.2 * rng.standard_normal((3, nant, 1, 2))) * np.exp(
        1j * rng.uniform(-np.pi, np.pi, (3, nant, 1, 2))
    )
    gflag = np.zeros(g.shape, bool)
    gflag[:, 2, 0, 0] = True  # antenna 2's X receptor at every slot
    coarse = coarse_subtables(ms, 8)
    nc = len(coarse["SPECTRAL_WINDOW"]["CHAN_FREQ"][0])
    b = (1 + 0.1 * rng.standard_normal((1, nant, nc, 2))) * np.exp(
        1j * 0.5 * rng.standard_normal((1, nant, nc, 2))
    )
    bflag = np.zeros(b.shape, bool)
    bflag[0, 1, 50:60, :] = True
    extra = {}
    if seed != SEED_HELDOUT:
        tm = np.linspace(times.min() - 5.0, times.max() + 5.0, 9)
        gm = (1 + 0.2 * rng.standard_normal((9, nant, 1, 2))) * np.exp(
            1j * rng.uniform(-np.pi, np.pi, (9, nant, 1, 2))
        )
        gmflag = np.zeros(gm.shape, bool)
        gmflag[4, 1, 0, :] = True
        gaps = coarse_subtables(ms, 4)
        ng = len(gaps["SPECTRAL_WINDOW"]["CHAN_FREQ"][0])
        bg = (1 + 0.1 * rng.standard_normal((1, nant, ng, 2))) * np.exp(
            1j * rng.uniform(-np.pi, np.pi, (1, nant, ng, 2))
        )
        bgflag = np.zeros(bg.shape, bool)
        bgflag[0, 0, 40:47, 0] = True
        bgflag[0, 2, 200:260, :] = True
        bgflag[0, 3, 400:403, 1] = True
        extra = {
            "hGmany": caltable.from_gains(
                "G", tm, ants, gm, gmflag, subtables=single, interval=30.0, **common
            ),
            "hBgaps": caltable.from_gains(
                "B", mid, ants, bg, bgflag, subtables=gaps, **common
            ),
        }
    return extra | {
        "hDf2slot": caltable.from_gains(
            "Df", t2, ants, d2, f2, subtables=full, interval=60.0, **common
        ),
        "hDfdx": caltable.from_gains(
            "Df", mid, ants, ddx, fdx, subtables=full, **common
        ),
        "hDf0": caltable.from_gains("Df", mid, ants, d0, subtables=full, **common),
        "hG": caltable.from_gains(
            "G", tg, ants, g, gflag, subtables=single, interval=120.0, **common
        ),
        "hBc": caltable.from_gains(
            "B", mid, ants, b, bflag, subtables=coarse, **common
        ),
    }


def frozen_cases(e4, t_table):
    return {
        "casa-K": [(e4 / "x.K", L)],
        "casa-G": [(e4 / "x.G", L)],
        "casa-B": [(e4 / "x.B", L)],
        "casa-Df": [(e4 / "x.Df", L)],
        "casa-T": [(t_table, L)],
        "casa-chain": [(e4 / f"x.{k}", L) for k in ("K", "G", "B", "Df")],
        "casa-caracal-pol": [(e4 / f"x.{k}", L) for k in ("K", "G", "B")]
        + [(e4 / "x.Df", "nearest")],
        "synth-G": [("synth/s.G", L)],
        "synth-B": [("synth/s.B", L)],
        "synth-K": [("synth/s.K", L)],
        "synth-T": [("synth/s.T", L)],
        "synth-chain": [(f"synth/s.{k}", L) for k in ("G", "B", "K")],
        "synth-G-nearest": [("synth/s.G", "nearest")],
        "synth-Df": [("synth/s.Df", L)],
        "synth-Df-nearest": [("synth/s.Df", "nearest")],
        "synth-B-freqnearest": [("synth/s.B", "linear,nearest")],
        # Post hoc (after run -01): CASA's Df flag rule with d_x and both
        # leakages flagged.
        "posthoc-synth-Df2": [("synth/s.Df2", L)],
        "posthoc-synth-Df2-chain": [(f"synth/s.{k}", L) for k in ("G", "B", "K")]
        + [("synth/s.Df2", "nearest")],
    }


def heldout_cases(seed=SEED_HELDOUT):
    """Section 5's cases (and section 6's two more with another seed), and
    which take the edited input flags."""
    more = {}
    if seed != SEED_HELDOUT:
        more = {
            "h-G-many-linear": [("synth/s.hGmany", L)],
            "h-G-many-nearest": [("synth/s.hGmany", "nearest")],
            "h-B-gaps-linear": [("synth/s.hBgaps", L)],
            "h-B-gaps-freqnearest": [("synth/s.hBgaps", "linear,nearest")],
        }
    cases = more | {
        "h-Df-2slot-linear": [("synth/s.hDf2slot", L)],
        "h-Df-2slot-nearest": [("synth/s.hDf2slot", "nearest")],
        "h-Df-dx": [("synth/s.hDfdx", L)],
        "h-G-receptor-Df": [("synth/s.hG", L), ("synth/s.hDf0", L)],
        "h-inputflags-Df": [("synth/s.hDf0", L)],
        "h-inputflags-G": [("synth/s.hG", L)],
        "h-B-coarse-freqnearest": [("synth/s.hBc", "linear,nearest")],
        "h-B-coarse-freqlinear": [("synth/s.hBc", L)],
        "h-chain-caracal": [
            ("synth/s.hBc", L),
            ("synth/s.hG", L),
            ("synth/s.hDf2slot", "nearest"),
        ],
    }
    edited = {"h-inputflags-Df", "h-inputflags-G"}
    return cases, edited


def edit_flags(flag, a1, a2, edits=EDITS):
    """The held-out input flags: in each block only one correlation flagged."""
    f = np.array(flag, bool, copy=True)
    for p, q, c0, c1, corr in edits:
        m = (a1 == p) & (a2 == q)
        f[m, c0:c1, :] = False
        f[np.flatnonzero(m)[:, None], np.arange(c0, c1)[None, :], corr] = True
    return f


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__)
        return 2
    run = Path(args[0]).resolve()
    heldout = "--heldout" in args
    predict = "--predict" in args
    seed = SEED_HELDOUT
    if "--seed" in args:
        seed = int(args[args.index("--seed") + 1])
    outputs = Path.home() / "Github/rang/outputs"
    if "--outputs" in args:
        outputs = Path(args[args.index("--outputs") + 1])
    outputs = outputs.resolve()
    ms = outputs / "o-casa-20261030-01" / "c.ms"
    e4 = outputs / "e4-20261030-01" / "casa"
    t_table = outputs / "dfio-20261030-02" / "ct" / "casa" / "x.T"
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    timings = []

    cols = cf.ms_columns(ms)
    fid = cf.field_index(ms)
    freqs = cf.ms_frequencies(ms)
    sel = cols["FIELD_ID"] == fid
    nant = int(max(cols["ANTENNA1"].max(), cols["ANTENNA2"].max())) + 1
    times = cols["TIME"][sel]
    if heldout:
        synth = heldout_tables(ms, nant, times, fid, seed)
        plan, edited = heldout_cases(seed)
    else:
        synth = cf.seeded_tables(ms, nant, times, freqs, fid)
        synth["Df"] = synth_df(ms, nant, times, fid)
        synth["Df2"] = synth_df(ms, nant, times, fid, posthoc=True)
        plan, edited = frozen_cases(e4, t_table), set()
    (run / "synth").mkdir()
    for k, ct in synth.items():
        caltable.write(ct, run / "synth" / f"s.{k}")
    lookup = {f"synth/s.{k}": v for k, v in synth.items()}

    def table(p):
        if str(p) in lookup:
            return lookup[str(p)]
        lookup[str(p)] = caltable.read(p)
        return lookup[str(p)]

    a1_all, a2_all = cols["ANTENNA1"][sel], cols["ANTENNA2"][sel]
    base_flag = cols["FLAG"][sel]

    def input_flags(name):
        return edit_flags(base_flag, a1_all, a2_all) if name in edited else base_flag

    if predict:
        pred = {}
        for name, tabs in plan.items():
            f0 = input_flags(name)
            _, gflag = cal_apply.apply(
                cols["DATA"][sel],
                f0,
                times,
                a1_all,
                a2_all,
                freqs,
                [table(p) for p, _ in tabs],
                field_id=fid,
                interp=[m for _, m in tabs],
                nant=nant,
            )
            pred[name] = {
                "flagged": int(gflag.sum()),
                "new": int((gflag & ~f0).sum()),
                "new_per_corr": [int(x) for x in (gflag & ~f0).sum(axis=(0, 1))],
            }
            print(name, pred[name])
        (run / "predict.json").write_text(json.dumps(pred, indent=1))
        return 0

    def guest(path):
        path = Path(path)
        if not path.is_absolute():
            return f"/run/{path.as_posix()}"
        if path.is_relative_to(e4):
            return f"/e4/{path.relative_to(e4).as_posix()}"
        return f"/dfio/{path.name}"

    (run / "apply").mkdir()
    spec = ";".join(",".join(str(x) for x in e) for e in EDITS)
    steps = []
    for name, tabs in plan.items():
        step = f"cp -r /o/c.ms /run/apply/{name}.ms"
        if name in edited:
            step += (
                f" && /opt/casa/bin/python -I /ex/oracle_apply.py edit-flags "
                f"/run/apply/{name}.ms {fid} '{spec}'"
            )
        step += (
            f" && /opt/casa/bin/python -I /ex/oracle_apply.py /run /run/apply/{name}.ms "
            f"'{';'.join(m for _, m in tabs)}' " + " ".join(guest(p) for p, _ in tabs)
        )
        steps.append(step)
    cf.TIMINGS.clear()
    cf.docker(
        cf.CASA_IMAGE,
        ["sh", "-c", " && ".join(steps)],
        [
            (run, "/run", "rw"),
            (HERE, "/ex", "ro"),
            (ms, "/o/c.ms", "ro"),
            (e4, "/e4", "ro"),
            (t_table, "/dfio/x.T", "ro"),
        ],
        f"casa applycal x{len(plan)}",
    )
    timings.extend(cf.TIMINGS)

    results = {}
    export = run / "export"
    export.mkdir()
    for name, tabs in plan.items():
        c = cf.ms_columns(run / "apply" / f"{name}.ms")
        s = c["FIELD_ID"] == fid
        data = c["DATA"][s]
        casa, cflag = c["CORRECTED_DATA"][s], c["FLAG"][s]
        np.savez_compressed(export / f"{name}.npz", corrected=casa, flag=cflag)
        orig_flag = input_flags(name)
        tables = [table(p) for p, _ in tabs]
        interp = [m for _, m in tabs]
        args = (
            data,
            orig_flag,
            c["TIME"][s],
            c["ANTENNA1"][s],
            c["ANTENNA2"][s],
            freqs,
            tables,
        )
        t0 = time.perf_counter()
        got, gflag = cal_apply.apply(*args, field_id=fid, interp=interp, nant=nant)
        rust_s = time.perf_counter() - t0
        ok = ~cflag & ~gflag
        vs_casa = cal_apply.class_c(got, casa, ok)
        flags_exact = bool(np.array_equal(cflag, gflag))
        # Values under a solution flag (reported, not gated).
        under = gflag & ~orig_flag
        diff = np.abs(got.astype(complex) - casa.astype(complex))
        under_report = {
            "cells": int(under.sum()),
            "equal_to_data": int(np.sum(under & (casa == data))),
            "rang_equal_to_casa_within_class_c": (
                cal_apply.class_c(got, casa, under)["pass"] if under.any() else None
            ),
            "max_abs_diff": float(diff[under].max()) if under.any() else None,
        }
        result = {
            "tables": [str(p) for p, _ in tabs],
            "interp": interp,
            "input_flags_edited": name in edited,
            "rust_vs_casa": vs_casa,
            "flags_exact": flags_exact,
            "flag_cells_casa": int(cflag.sum()),
            "flag_cells_rang": int(gflag.sum()),
            "flag_cells_differ": int(np.sum(cflag != gflag)),
            "new_flags_per_corr_casa": [
                int(x) for x in (cflag & ~orig_flag).sum(axis=(0, 1))
            ],
            "under_solution_flags": under_report,
            "rust_s": rust_s,
        }
        if any(t.kind == "Df" for t in tables):
            # Unflagged cross hands corrected with CASA's substituted
            # leakage (-1) because the antenna's other leakage is bad: a
            # baseline with any bad leakage flags XY or YX on its own.
            substituted = np.zeros(gflag.shape[:2], bool)
            for t, (_, m) in zip(tables, tabs):
                if t.kind != "Df":
                    continue
                _, f_only = cal_apply.apply(
                    np.zeros_like(data),
                    np.zeros_like(orig_flag),
                    c["TIME"][s],
                    c["ANTENNA1"][s],
                    c["ANTENNA2"][s],
                    freqs,
                    [t],
                    field_id=fid,
                    interp=[m],
                    nant=nant,
                )
                substituted |= f_only[..., 1] | f_only[..., 2]
            result["cross_hands_unflagged_with_substituted_leakage"] = int(
                np.sum(substituted[..., None] & ~gflag[..., 1:3])
            )
        modes = {cal_apply.parse_interp(m)[1] for m in interp}
        time_modes = {cal_apply.parse_interp(m)[0] for m in interp}
        if modes == {0} and len(time_modes) == 1:
            t0 = time.perf_counter()
            exp, eflag = caltable.correct(
                *args,
                field_id=fid,
                time_interp="linear" if time_modes == {0} else "nearest",
            )
            result["caltable_s"] = time.perf_counter() - t0
            # Values gated where both are unflagged; flag differences are
            # reported by count (caltable.correct flags all four for a bad
            # Df leakage and does not propagate parallel-hand flags).
            result["rust_vs_caltable"] = cal_apply.class_c(
                got, exp.astype(np.complex64), ~gflag & ~eflag
            )
            result["caltable_flag_cells_only_caltable"] = int(np.sum(eflag & ~gflag))
            result["caltable_flag_cells_only_rang"] = int(np.sum(gflag & ~eflag))
            result["caltable_vs_casa"] = cal_apply.class_c(exp, casa, ~cflag & ~eflag)
        # The other frequency mode against CASA: if it passes too, the case
        # cannot tell the two modes apart (gated on the held-out B cases).
        other = []
        for m in interp:
            tm, fm = cal_apply.parse_interp(m)
            names = {0: "linear", 1: "nearest"}
            other.append(f"{names[tm]},{names[1 - fm]}")
        alt, _ = cal_apply.apply(*args, field_id=fid, interp=other, nant=nant)
        result["other_freq_mode_vs_casa"] = cal_apply.class_c(alt, casa, ok)
        # Against caltable.correct: reported, not gated, from run -04 (the
        # kernel ports CASA's float32 phase tracking and unwrap, which
        # caltable.py does not; research/c4a-apply.md section 6).
        result["pass"] = bool(vs_casa["pass"] and flags_exact)
        if name.startswith(("h-B-coarse", "h-B-gaps")):
            result["pass"] = (
                result["pass"] and not result["other_freq_mode_vs_casa"]["pass"]
            )
        if name in ("casa-chain", "h-chain-caracal"):
            ref = None
            same = {}
            for n in THREADS:
                out = cal_apply.apply(
                    *args, field_id=fid, interp=interp, nant=nant, threads=n
                )
                if ref is None:
                    ref = out
                same[n] = bool(
                    out[0].tobytes() == ref[0].tobytes()
                    and np.array_equal(out[1], ref[1])
                )
            result["threads_bit_identical"] = same
            result["pass"] = result["pass"] and all(same.values())
        results[name] = result
        shutil.rmtree(run / "apply" / f"{name}.ms")

    threads = [
        r["threads_bit_identical"]
        for r in results.values()
        if "threads_bit_identical" in r
    ]
    verdict = {
        "class_C_against_applycal_every_case": all(
            r["rust_vs_casa"]["pass"] for r in results.values()
        ),
        "flags_exact_every_case": all(r["flags_exact"] for r in results.values()),
        "class_C_against_caltable_correct_values": all(
            r["rust_vs_caltable"]["pass"]
            for r in results.values()
            if "rust_vs_caltable" in r
        ),
        "threads_bit_identical": threads,
        "all": all(r["pass"] for r in results.values()),
    }
    image = subprocess.run(
        ["docker", "image", "inspect", cf.CASA_IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    archive = {
        "task": "C4a",
        "protocol": "research/c4a-apply.md, section 5 (held out)"
        if heldout
        else "research/c4a-apply.md, sections 2 and 3",
        "inputs": {"ms": str(ms), "e4_tables": str(e4), "t_table": str(t_table)},
        "image": {"name": cf.CASA_IMAGE, "id": image},
        "seeds": {
            "synthetic G, B, K, T (check_formats.seeded_tables)": cf.SEED,
            "synthetic Df": SEED_DF,
            "held out": seed if heldout else None,
        },
        "input_flag_edits": EDITS if heldout else None,
        "field_id": fid,
        "rows": int(sel.sum()),
        "nchan": len(freqs),
        "cases": results,
        "verdicts": verdict,
        "timings": timings,
        "wall_s": time.perf_counter() - started,
    }
    (run / "c4a.json").write_text(json.dumps(archive, indent=1, default=str))
    print(json.dumps(verdict, indent=1))
    for name, r in results.items():
        v = r["rust_vs_casa"]
        print(
            f"{name:24s} pass={r['pass']} cells={v['cells']} rel={v['max_relative']:.3g} "
            f"eps={v['max_float32_eps_of_cell']:.3g} flags_exact={r['flags_exact']}"
        )
    return 0 if verdict["all"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
