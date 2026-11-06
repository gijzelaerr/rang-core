"""Host checker of task C4b (research/c4b-apply-ms.md, sections 3.1 and 3.2):
`rang.applycal.applycal` against CASA `applycal` on Measurement Sets.

    python examples/check_apply_ms.py <run> [--outputs <dir>]

`<run>` is a fresh `/mnt/d/rang/outputs/c4b-<date>-NN`. Inputs, read only:
O-CASA's `c.ms` and E4's CASA tables under `<dir>` (default
`~/Github/rang/outputs`) and A1's small MS. Writes the synthetic tables
(seed 20261109), the prepared copies (weights and FLAG_ROW edited with
casatools), one CASA and one rang copy per case, the exports of every
compared column read with casatools, and `<run>/c4b.json` with every
criterion and verdict. The MS copies are removed at the end; the exports
stay.
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

import check_apply as ca
import check_formats as cf
from rang import applycal, cal_apply, core_ms
from rang.formats import caltable

SEED = 20261109
A1_SMALL = Path("/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms")
L = "linear"
WRITTEN = ("CORRECTED_DATA", "FLAG", "FLAG_ROW", "WEIGHT", "WEIGHT_SPECTRUM")
CHUNKED = {"s-G-calwt": 50, "a-chain-calwt": 1000}


def merge(tables):
    """One CalTable from several of the same kind (rows concatenated)."""
    first = tables[0]
    main = {k: [v for t in tables for v in t.main[k]] for k in first.main}
    return caltable.CalTable(
        first.vis_cal, main, first.subtables, first.keywords, first.info
    )


def s_tables(ms, nant, times, fid, rng):
    """Synthetic G, B and T on the slice (section 3.1)."""
    single = caltable.subtables_from_ms(ms, single_channel=True)
    ants = list(range(nant))
    common = {"field_id": fid, "refant": 0, "ms_name": "c.ms"}
    tg = np.linspace(times.min(), times.max(), 3)
    g = (1 + 0.2 * rng.standard_normal((3, nant, 1, 2))) * np.exp(
        1j * rng.uniform(-np.pi, np.pi, (3, nant, 1, 2))
    )
    gflag = np.zeros(g.shape, bool)
    gflag[1, 1, 0, 0] = True  # antenna 1 X at slot 1
    gflag[:, 2, 0, :] = True  # antenna 2 both, every slot
    gflag[0, 3, 0, 1] = True  # antenna 3 Y at slot 0
    coarse = ca.coarse_subtables(ms, 8)
    nc = len(coarse["SPECTRAL_WINDOW"]["CHAN_FREQ"][0])
    b = (1.3 * (1 + 0.05 * rng.standard_normal((1, nant, nc, 2)))) * np.exp(
        1j * 0.2 * rng.standard_normal((1, nant, nc, 2))
    )
    bflag = np.zeros(b.shape, bool)
    bflag[0, 0, 100:140, 0] = True
    t = (1.1 + 0.1 * rng.standard_normal((3, nant, 1, 1))) * np.exp(
        1j * rng.uniform(-1, 1, (3, nant, 1, 1))
    )
    mid = [float(np.mean(times))]
    return {
        "sG": caltable.from_gains(
            "G", tg, ants, g, gflag, subtables=single, interval=120.0, **common
        ),
        "sB": caltable.from_gains("B", mid, ants, b, bflag, subtables=coarse, **common),
        "sT": caltable.from_gains(
            "T", tg, ants, t, subtables=single, interval=120.0, **common
        ),
    }


def a_tables(ms, rng, interleave=False):
    """Synthetic two-field G and one-field B on A1 small (section 3.1). With
    `interleave` (the held-out set, section 5), J1939-6342's G also has slots
    at the middle of every SIM-TARGET scan, so the pooled map differs from
    the nearest one there."""
    with core_ms.open_table(ms) as t:
        fid, scan, tm = t.getcol("FIELD_ID"), t.getcol("SCAN_NUMBER"), t.getcol("TIME")
    with core_ms.open_table(ms / "ANTENNA") as t:
        nant = t.nrows
    single = caltable.subtables_from_ms(ms, single_channel=True)
    full = caltable.subtables_from_ms(ms, single_channel=False)
    ants = list(range(nant))
    parts = []
    for field, amp in ((0, 1.0), (2, 1.5)):
        slots = sorted(
            float(np.mean(tm[(fid == field) & (scan == s)]))
            for s in np.unique(scan[fid == field])
        )
        if interleave and field == 0:
            slots = sorted(
                slots
                + [
                    float(np.mean(tm[(fid == 3) & (scan == s)]))
                    for s in np.unique(scan[fid == 3])
                ]
            )
        g = (amp * (1 + 0.1 * rng.standard_normal((len(slots), nant, 1, 2)))) * np.exp(
            1j * rng.uniform(-np.pi, np.pi, (len(slots), nant, 1, 2))
        )
        flag = np.zeros(g.shape, bool)
        if field == 2 and len(slots) > 1:
            flag[1, 5, 0, :] = True
        if field == 0:
            flag[0, 7, 0, 0] = True
        parts.append(
            caltable.from_gains(
                "G",
                slots,
                ants,
                g,
                flag,
                subtables=single,
                field_id=field,
                refant=0,
                interval=60.0,
                ms_name="a1-small.ms",
            )
        )
    nchan = len(full["SPECTRAL_WINDOW"]["CHAN_FREQ"][0])
    b = (1.3 * (1 + 0.05 * rng.standard_normal((1, nant, nchan, 2)))) * np.exp(
        1j * 0.2 * rng.standard_normal((1, nant, nchan, 2))
    )
    bflag = np.zeros(b.shape, bool)
    bflag[0, 4, 10:20, 1] = True
    mid = [float(np.mean(tm[fid == 0]))]
    return {
        "aG": merge(parts),
        "aB": caltable.from_gains(
            "B",
            mid,
            ants,
            b,
            bflag,
            subtables=full,
            field_id=0,
            refant=0,
            ms_name="a1-small.ms",
        ),
    }


def cases(e4):
    """(MS variant, CASA field, rang field, [(table, interp, gainfield)], calwt)."""
    cal = "J1939-6342"
    return {
        "s-chain": (
            "S-plain",
            cal,
            [cal],
            [(e4 / f"x.{k}", L, "nearest") for k in ("K", "G", "B", "Df")],
            [False],
        ),
        "s-G-flags": ("S-plain", cal, [cal], [("synth/s.sG", L, "")], [False]),
        "s-G-calwt": ("S-wf", cal, [cal], [("synth/s.sG", L, "")], [True]),
        "s-BT-calwt": (
            "S-w",
            cal,
            [cal],
            [("synth/s.sB", L, ""), ("synth/s.sT", L, "")],
            [True, True],
        ),
        "s-K-calwt": ("S-w", cal, [cal], [(e4 / "x.K", L, "")], [True]),
        "s-Gnearest-mix": (
            "S-w",
            cal,
            [cal],
            [("synth/s.sG", "nearest", ""), (e4 / "x.Df", "nearest", "")],
            [True, False],
        ),
        "a-pooled": (
            "A-plain",
            "SIM-TARGET",
            ["SIM-TARGET"],
            [("synth/a.aG", L, "")],
            [False],
        ),
        "a-named": (
            "A-plain",
            "SIM-TARGET",
            ["SIM-TARGET"],
            [("synth/a.aG", L, "J1939-6342")],
            [False],
        ),
        "a-nearest": ("A-plain", "", None, [("synth/a.aG", L, "nearest")], [False]),
        "a-chain-calwt": (
            "A-w",
            "SIM-GCAL,SIM-TARGET",
            ["SIM-GCAL", "SIM-TARGET"],
            [("synth/a.aB", L, "J1939-6342"), ("synth/a.aG", L, "nearest")],
            [True],
        ),
    }


def read_cols(ms, names):
    out = {}
    with core_ms.open_table(ms) as t:
        for n in names:
            if n in t.columns:
                out[n] = t.getcol(n)
    return out


def same_bytes(a, b, names):
    return {
        n: bool(n in a and n in b and a[n].tobytes() == b[n].tobytes())
        for n in names
        if n in a or n in b
    }


def rel_check(r, c):
    r, c = np.asarray(r, np.float64), np.asarray(c, np.float64)
    err = np.abs(r - c)
    ok = err <= 1e-6 * np.abs(c)
    return {
        "values": int(r.size),
        "max_relative": float(np.max(err / np.where(c != 0, np.abs(c), 1)))
        if r.size
        else 0.0,
        "bit_identical_fraction": float(
            np.mean(r.astype(np.float32) == c.astype(np.float32))
        ),
        "failing": int((~ok).sum()),
        "pass": bool(ok.all()),
    }


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__)
        return 2
    run = Path(args[0]).resolve()
    outputs = Path.home() / "Github/rang/outputs"
    if "--outputs" in args:
        outputs = Path(args[args.index("--outputs") + 1])
    s_ms = (outputs / "o-casa-20261030-01" / "c.ms").resolve()
    e4 = (outputs / "e4-20261030-01" / "casa").resolve()
    heldout = "--heldout" in args
    seed = int(args[args.index("--seed") + 1]) if "--seed" in args else SEED
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    rng = np.random.default_rng(seed)
    cols = cf.ms_columns(s_ms)
    fid = cf.field_index(s_ms)
    nant = int(max(cols["ANTENNA1"].max(), cols["ANTENNA2"].max())) + 1
    times = cols["TIME"][cols["FIELD_ID"] == fid]
    synth = {f"s.{k}": v for k, v in s_tables(s_ms, nant, times, fid, rng).items()}
    synth |= {
        f"a.{k}": v for k, v in a_tables(A1_SMALL, rng, interleave=heldout).items()
    }
    (run / "synth").mkdir()
    for k, ct in synth.items():
        caltable.write(ct, run / "synth" / k)
    plan = cases(e4)

    def host_table(p):
        return run / p if str(p).startswith("synth/") else Path(p)

    def guest_table(p):
        if str(p).startswith("synth/"):
            return f"/run/{p}"
        return f"/e4/{Path(p).name}"

    mounts = [
        (run, "/run", "rw"),
        (HERE, "/ex", "ro"),
        (s_ms, "/in/s.ms", "ro"),
        (A1_SMALL, "/in/a.ms", "ro"),
        (e4, "/e4", "ro"),
    ]
    py = "/opt/casa/bin/python -I /ex/oracle_apply_ms.py"
    variants = {
        "S-plain": ("s", f"{fid}", 0, 0),
        "S-w": ("s", f"{fid}", 1, 0),
        "S-wf": ("s", f"{fid}", 1, 1),
        "A-plain": ("a", "0,1,2,3", 0, 0),
        "A-w": ("a", "0,1,2,3", 1, 0),
    }
    for d in ("prep", "casa", "rang", "export"):
        (run / d).mkdir()
    steps = []
    for name, (src, fids, wts, frow) in variants.items():
        steps.append(f"cp -r /in/{src}.ms /run/prep/{name}.ms")
        if wts or frow:
            steps.append(f"{py} prepare /run/prep/{name}.ms {fids} {wts} {frow} {seed}")
    cf.TIMINGS.clear()
    cf.docker(cf.CASA_IMAGE, ["sh", "-c", " && ".join(steps)], mounts, "casa prepare")

    # The copies of each case: CASA's, rang's, and the extra rang variants.
    copies = []
    for case, (variant, *_rest) in plan.items():
        copies.append(("casa", case, variant))
        copies.append(("rang", case, variant))
        if case in CHUNKED:
            copies.append(("rang", f"{case}.chunked", variant))
        if case == "s-G-calwt":
            copies.append(("rang", f"{case}.twice", variant))
    for arm, case, variant in copies:
        shutil.copytree(run / "prep" / f"{variant}.ms", run / arm / f"{case}.ms")

    # CASA arm.
    steps = []
    for case, (variant, cfield, _rf, tabs, calwt) in plan.items():
        spec = {
            "ms": f"/run/casa/{case}.ms",
            "field": cfield,
            "gaintable": [guest_table(p) for p, _, _ in tabs],
            "interp": [m for _, m, _ in tabs],
            "gainfield": [g for _, _, g in tabs],
            "calwt": calwt,
        }
        (run / "casa" / f"{case}.json").write_text(json.dumps(spec))
        steps.append(f"{py} apply /run/casa/{case}.json")
    cf.docker(
        cf.CASA_IMAGE,
        ["sh", "-c", " && ".join(steps)],
        mounts,
        f"casa applycal x{len(plan)}",
    )

    # rang arm.
    rang_runs = {}
    for arm, case, variant in copies:
        if arm != "rang":
            continue
        base = case.split(".")[0]
        _v, _cf, rfield, tabs, calwt = plan[base]
        tables = [caltable.read(host_table(p)) for p, _, _ in tabs]
        kwargs = {
            "interp": [m for _, m, _ in tabs],
            "gainfield": [g for _, _, g in tabs],
            "calwt": calwt,
            "field": rfield,
        }
        ms = run / "rang" / f"{case}.ms"
        if case.endswith(".chunked"):
            kwargs["chunk_rows"] = CHUNKED[base]
        t0 = time.perf_counter()
        summary = applycal.applycal(ms, tables, **kwargs)
        if case.endswith(".twice"):
            summary = applycal.applycal(ms, tables, **kwargs)
        rang_runs[case] = {"wall_s": time.perf_counter() - t0, "summary": summary}

    # Exports, read with casatools.
    steps = []
    for name in variants:
        steps.append(
            f"{py} export /run/prep/{name}.ms /run/export/prep-{name}.npz /run/export/prep-{name}.sha.json"
        )
    for arm, case, _variant in copies:
        steps.append(
            f"{py} export /run/{arm}/{case}.ms /run/export/{arm}-{case}.npz /run/export/{arm}-{case}.sha.json"
        )
    cf.docker(cf.CASA_IMAGE, ["sh", "-c", " && ".join(steps)], mounts, "casa export")

    def load(tag):
        z = np.load(run / "export" / f"{tag}.npz")
        return {k: z[k] for k in z.files}

    def sha(tag):
        return json.loads((run / "export" / f"{tag}.sha.json").read_text())

    results = {}
    target_cd = {}
    for case, (variant, _cf, rfield, tabs, calwt) in plan.items():
        r, c, p = load(f"rang-{case}"), load(f"casa-{case}"), load(f"prep-{variant}")
        info = applycal.ms_info(run / "prep" / f"{variant}.ms")
        fids = applycal._field_ids(rfield, info)
        sel = np.isin(c["FIELD_ID"], fids)
        every = np.ones(c["CORRECTED_DATA"][sel].shape, bool)
        res = {"rows_selected": int(sel.sum()), "rows": int(sel.size)}
        rcd, ccd = r["CORRECTED_DATA"][sel], c["CORRECTED_DATA"][sel]
        f_in = p["FLAG"][sel]
        cflag = c["FLAG"][sel]
        res["1_corrected_all_cells"] = cal_apply.class_c(rcd, ccd, every)
        res["1_unflagged_both"] = cal_apply.class_c(rcd, ccd, ~cflag & ~r["FLAG"][sel])
        under = cflag & ~f_in
        res["1_under_solution_flags"] = (
            cal_apply.class_c(rcd, ccd, under) if under.any() else None
        )
        res["1_under_input_flags"] = (
            cal_apply.class_c(rcd, ccd, f_in) if f_in.any() else None
        )
        res["2_flag_exact"] = bool(np.array_equal(r["FLAG"], c["FLAG"]))
        res["2_flag_cells_differ"] = int(np.sum(r["FLAG"] != c["FLAG"]))
        res["3_flag_row_equal"] = bool(np.array_equal(r["FLAG_ROW"], c["FLAG_ROW"]))
        res["3_flag_row_changed_by_casa"] = int(np.sum(c["FLAG_ROW"] != p["FLAG_ROW"]))
        res["3_flag_row_changed_by_rang"] = int(np.sum(r["FLAG_ROW"] != p["FLAG_ROW"]))
        if (~sel).any():
            res["4_unselected_corrected_identical"] = bool(
                r["CORRECTED_DATA"][~sel].tobytes()
                == c["CORRECTED_DATA"][~sel].tobytes()
            )
        else:
            res["4_unselected_corrected_identical"] = None
        wnames = [
            n
            for n in ("WEIGHT", "WEIGHT_SPECTRUM", "SIGMA", "SIGMA_SPECTRUM")
            if n in p
        ]
        if not any(calwt):
            res["5_weights_unchanged"] = {
                n: bool(
                    r[n].tobytes() == p[n].tobytes()
                    and c[n].tobytes() == p[n].tobytes()
                )
                for n in wnames
            }
            wpass = all(res["5_weights_unchanged"].values())
        else:
            res["6_weights"] = {
                n: rel_check(r[n], c[n])
                for n in ("WEIGHT", "WEIGHT_SPECTRUM")
                if n in p
            }
            res["6_sigma_identical"] = {
                n: bool(r[n].tobytes() == c[n].tobytes())
                for n in ("SIGMA", "SIGMA_SPECTRUM")
                if n in p
            }
            res["6_casa_changed_weights"] = {
                n: bool(c[n].tobytes() != p[n].tobytes())
                for n in ("WEIGHT", "WEIGHT_SPECTRUM")
                if n in p
            }
            wpass = all(v["pass"] for v in res["6_weights"].values()) and all(
                res["6_sigma_identical"].values()
            )
        hr, hp = sha(f"rang-{case}"), sha(f"prep-{variant}")
        res["7_other_columns_identical"] = {
            n: hr.get(n) == hp.get(n) for n in sorted(hp) if n not in WRITTEN
        }
        res["pass"] = bool(
            res["1_corrected_all_cells"]["pass"]
            and res["2_flag_exact"]
            and res["3_flag_row_equal"]
            and res["4_unselected_corrected_identical"] in (True, None)
            and wpass
            and all(res["7_other_columns_identical"].values())
        )
        res["rang_wall_s"] = rang_runs[case]["wall_s"]
        res["rang_summary"] = rang_runs[case]["summary"]
        if case.startswith("a-"):
            tsel = c["FIELD_ID"] == info["fields"].index("SIM-TARGET")
            target_cd[case] = c["CORRECTED_DATA"][tsel]
        # Criterion 10: the flag version equals the input flags.
        fv = run / "rang" / f"{case}.ms.flagversions" / "flags.rang_original"
        v = read_cols(fv, ["FLAG", "FLAG_ROW"])
        res["10_flag_backup_equal"] = bool(
            np.array_equal(v.get("FLAG"), p["FLAG"])
            and np.array_equal(v.get("FLAG_ROW"), p["FLAG_ROW"])
        )
        res["pass"] = res["pass"] and res["10_flag_backup_equal"]
        results[case] = res

    # Field maps tell the cases apart on SIM-TARGET.
    keys = ["a-pooled", "a-named", "a-nearest"]
    distinct = {
        f"{x} vs {y}": bool(not np.array_equal(target_cd[x], target_cd[y]))
        for i, x in enumerate(keys)
        for y in keys[i + 1 :]
    }
    # Criteria 8 and 9 (host reads; bit identity).
    props = {}
    for case, rows in CHUNKED.items():
        a = read_cols(run / "rang" / f"{case}.ms", WRITTEN)
        b = read_cols(run / "rang" / f"{case}.chunked.ms", WRITTEN)
        props[f"8_chunked_{case}_{rows}"] = same_bytes(a, b, WRITTEN)
    a = load("rang-s-G-calwt")
    b = load("rang-s-G-calwt.twice")
    props["9_twice_s-G-calwt"] = {n: bool(a[n].tobytes() == b[n].tobytes()) for n in a}
    props["9_twice_hashes"] = sha("rang-s-G-calwt") == sha("rang-s-G-calwt.twice")
    verdict = {
        "every_case": all(r["pass"] for r in results.values()),
        "field_maps_distinct": all(distinct.values()),
        "chunking": all(
            all(v.values()) for k, v in props.items() if k.startswith("8_")
        ),
        "idempotent": all(props["9_twice_s-G-calwt"].values())
        and props["9_twice_hashes"],
    }
    verdict["all"] = all(verdict.values())
    image = subprocess.run(
        ["docker", "image", "inspect", cf.CASA_IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    casa_walls = {}
    for case in plan:
        done = run / "casa" / f"{case}.json.done"
        if done.is_file():
            casa_walls[case] = json.loads(done.read_text())["wall_s"]
    archive = {
        "task": "C4b",
        "protocol": "research/c4b-apply-ms.md, sections 3.1 and 3.2",
        "inputs": {"S": str(s_ms), "A": str(A1_SMALL), "E4": str(e4)},
        "image": {"name": cf.CASA_IMAGE, "id": image},
        "seed": seed,
        "heldout": heldout,
        "cases": results,
        "field_maps_distinct_on_target": distinct,
        "properties": props,
        "casa_applycal_wall_s": casa_walls,
        "verdicts": verdict,
        "timings": cf.TIMINGS,
        "wall_s": time.perf_counter() - started,
    }
    (run / "c4b.json").write_text(json.dumps(archive, indent=1, default=str))
    for arm in ("prep", "casa", "rang"):
        shutil.rmtree(run / arm)
    print(json.dumps(verdict, indent=1))
    for name, r in results.items():
        v = r["1_corrected_all_cells"]
        print(
            f"{name:16s} pass={r['pass']} cells={v['cells']} eps={v['max_float32_eps_of_cell']:.3g} "
            f"flags={r['2_flag_exact']} flag_row={r['3_flag_row_equal']}"
        )
    return 0 if verdict["all"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
