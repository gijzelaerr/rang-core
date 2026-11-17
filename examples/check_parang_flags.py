"""Host checker of task df-flag-rule (research/p-flag-spread.md): P's flags
in `rang.applycal.applycal(parang=...)` against CASA 6.7.6.14 `applycal`.

    python examples/check_parang_flags.py predict <run> [--ms <c.ms>]
    python examples/check_parang_flags.py run <run> [--ms <c.ms>]

`<run>` is a fresh `D:\\rang\\outputs\\pfs-<date>-NN`; `<c.ms>` is O-CASA's
slice (default `\\\\wsl.localhost\\Ubuntu\\home\\gijsm\\Github\\rang\\outputs\\
o-casa-20261030-01\\c.ms`, read only, copied into `<run>/base.ms`).
`predict` writes rang's new-flag counts per case and correlation with
`parang_flags='spread'` (`<run>/predict.json`) without CASA. `run` writes
the seeded tables, runs one `applycal` per case in `rang-o-casa:6.7.6.14`
through WSL's docker (`examples/oracle_parang_flags.py`), applies rang
with `spread` and with `none` on copies, and writes `<run>/result.json`
with the frozen gate (CASA's FLAG equals rang's `spread` FLAG on every cell
of the field, every case) and the reported comparisons. MS copies are
removed afterwards; the FLAG arrays are kept in `<run>/export/<case>.npz`.
Run the CASA step under the main checkout's `tools/heavy_lock.py`.
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from rang import applycal, core_ms, core_ms_write
from rang.formats import caltable

SEED = 20261112
FIELD = "J1939-6342"
IMAGE = "rang-o-casa:6.7.6.14"
DEFAULT_MS = Path(
    r"\\wsl.localhost\Ubuntu\home\gijsm\Github\rang\outputs\o-casa-20261030-01\c.ms"
)
# Case D's input-flag edits: (antenna1, antenna2, first channel, end channel,
# the one correlation left flagged).
EDITS = [(0, 1, 500, 600, 0), (2, 3, 700, 800, 3)]


def wsl_path(p):
    p = Path(p).resolve()
    drive = p.drive.rstrip(":").lower()
    return f"/mnt/{drive}/" + "/".join(p.parts[1:])


def columns(ms, names=("FLAG", "DATA", "CORRECTED_DATA", "FIELD_ID")):
    with core_ms.open_table(ms) as t:
        have = set(t.colnames())
        return {c: t.getcol(c) for c in names if c in have}


def field_id(ms):
    with core_ms.open_table(Path(ms) / "FIELD") as t:
        return [str(x) for x in t.getcol("NAME")].index(FIELD)


def tables(ms):
    """The seeded tables of the protocol (section 4)."""
    rng = np.random.default_rng(SEED)
    with core_ms.open_table(ms) as t:
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        times, fids = t.getcol("TIME"), t.getcol("FIELD_ID")
    fid = field_id(ms)
    times = times[fids == fid]
    nant = int(max(a1.max(), a2.max())) + 1
    ants = list(range(nant))
    single = caltable.subtables_from_ms(ms, single_channel=True)
    full = caltable.subtables_from_ms(ms, single_channel=False)
    nchan = len(full["SPECTRAL_WINDOW"]["CHAN_FREQ"][0])
    common = {"field_id": fid, "refant": 0, "ms_name": "c.ms"}
    t_mid = [float(np.mean(times))]
    # Df: leakages about 0.05; whole-parameter flags on antenna 0's d_x and
    # antenna 3's d_y (effective under any frequency interpolation).
    d = 0.05 * (
        rng.standard_normal((1, nant, nchan, 2))
        + 1j * rng.standard_normal((1, nant, nchan, 2))
    )
    dflag = np.zeros(d.shape, bool)
    dflag[0, 0, :, 0] = True
    dflag[0, 3, :, 1] = True
    # G: 3 slots, antenna 2 receptor X bad at every slot.
    nt = 3
    t_sol = np.linspace(times.min(), times.max(), nt)
    g = (1 + 0.2 * rng.standard_normal((nt, nant, 1, 2))) * np.exp(
        1j * rng.uniform(-np.pi, np.pi, (nt, nant, 1, 2))
    )
    g[:, 0] = 1
    gflag = np.zeros(g.shape, bool)
    gflag[:, 2, 0, 0] = True
    # The chain's G: flagged slots on single receptors; B with a flagged
    # range on one receptor; K.
    gc = (1 + 0.2 * rng.standard_normal((4, nant, 1, 2))) * np.exp(
        1j * rng.uniform(-np.pi, np.pi, (4, nant, 1, 2))
    )
    gc[:, 0] = 1
    gcflag = np.zeros(gc.shape, bool)
    gcflag[1, nant - 1, 0, 1] = True
    gcflag[3, 1, 0, 0] = True
    b = (1 + 0.1 * rng.standard_normal((1, nant, nchan, 2))) * np.exp(
        1j * 0.3 * rng.standard_normal((1, nant, nchan, 2))
    )
    bflag = np.zeros(b.shape, bool)
    bflag[0, 2, 100:140, 1] = True
    k = rng.normal(0, 2.0, (1, nant, 1, 2))
    k[:, 0] = 0
    t4 = np.linspace(times.min(), times.max(), 4)
    return {
        "Df": caltable.from_gains(
            "Df", t_mid, ants, d, dflag, subtables=full, **common
        ),
        "G": caltable.from_gains(
            "G", t_sol, ants, g, gflag, subtables=single, interval=120.0, **common
        ),
        "Gc": caltable.from_gains(
            "G", t4, ants, gc, gcflag, subtables=single, interval=120.0, **common
        ),
        "B": caltable.from_gains("B", t_mid, ants, b, bflag, subtables=full, **common),
        "K": caltable.from_gains("K", t_mid, ants, k, subtables=single, **common),
    }


# name: ([(table, interp)], parang, input-flag edits)
CASES = {
    "A-df-noparang": ([("Df", "nearest")], False, False),
    "B-df-parang": ([("Df", "nearest")], True, False),
    "C-g-parang": ([("G", "linear")], True, False),
    "D-inflag-parang": ([], True, True),
    "E-chain-parang": (
        [("K", "linear"), ("Gc", "linear"), ("B", "linear"), ("Df", "nearest")],
        True,
        False,
    ),
}


def edit_flags(ms):
    """Case D: in each block only one correlation flagged."""
    with core_ms_write.open_table(ms, readonly=False) as t:
        flag = t.getcol("FLAG")
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        for p, q, c0, c1, corr in EDITS:
            m = np.flatnonzero((a1 == p) & (a2 == q))
            flag[m, c0:c1, :] = False
            flag[m[:, None], np.arange(c0, c1)[None, :], corr] = True
        t.putcol("FLAG", flag)


def rang_apply(ms, run, case, mode):
    tabs, parang, _ = CASES[case]
    return applycal.applycal(
        ms,
        [run / "tables" / f"s.{n}" for n, _ in tabs],
        interp=[m for _, m in tabs],
        gainfield=["nearest"] * len(tabs),
        calwt=[False],
        field=[FIELD],
        applymode="calflag",
        parang=parang,
        parang_flags=mode,
    )


def prepare(run, src):
    run.mkdir(parents=True, exist_ok=False)
    shutil.copytree(src, run / "base.ms")
    (run / "tables").mkdir()
    for name, ct in tables(run / "base.ms").items():
        caltable.write(ct, run / "tables" / f"s.{name}")


def case_copy(run, case, label):
    dst = run / "apply" / case / f"{label}.ms"
    shutil.copytree(run / "base.ms", dst)
    if CASES[case][2]:
        edit_flags(dst)
    return dst


def counts(new):
    return {
        "new": int(new.sum()),
        "new_per_corr": [int(x) for x in new.sum(axis=(0, 1))],
    }


def predict(run, src):
    prepare(run, src)
    fid = field_id(run / "base.ms")
    out = {}
    for case in CASES:
        ms = case_copy(run, case, "rang")
        before = columns(ms, ("FLAG", "FIELD_ID"))
        rang_apply(ms, run, case, "spread")
        after = columns(ms, ("FLAG",))["FLAG"]
        s = before["FIELD_ID"] == fid
        out[case] = counts(after[s] & ~before["FLAG"][s])
        print(case, out[case], flush=True)
        shutil.rmtree(ms.parent)
    (run / "predict.json").write_text(json.dumps(out, indent=1))
    shutil.rmtree(run / "apply")
    return 0


def casa(run):
    steps = []
    for case, (tabs, parang, _) in CASES.items():
        ms = f"/run/apply/{case}/casa.ms"
        steps.append(
            f"/opt/casa/bin/python -I /ex/oracle_parang_flags.py /run {ms} {FIELD} "
            f"{int(parang)} '{';'.join(m for _, m in tabs)}' "
            + " ".join(f"/run/tables/s.{n}" for n, _ in tabs)
        )
    cmd = [
        "wsl", "-e", "docker", "run", "--rm", "--network", "none",
        "-v", f"{wsl_path(run)}:/run",
        "-v", f"{wsl_path(Path(__file__).parent)}:/ex:ro",
        IMAGE, "sh", "-c", " && ".join(steps),
    ]  # fmt: skip
    started = time.perf_counter()
    subprocess.run(cmd, check=True)
    return time.perf_counter() - started


def main(argv):
    if len(argv) < 3 or argv[1] not in ("predict", "run"):
        print(__doc__)
        return 2
    run = Path(argv[2]).resolve()
    src = Path(argv[argv.index("--ms") + 1]) if "--ms" in argv else DEFAULT_MS
    if argv[1] == "predict":
        return predict(run, src)
    started = time.perf_counter()
    prepare(run, src)
    fid = field_id(run / "base.ms")
    for case in CASES:
        for label in ("casa", "spread", "none"):
            case_copy(run, case, label)
    casa_s = casa(run)
    rang_s = {}
    for case in CASES:
        for mode in ("spread", "none"):
            t0 = time.perf_counter()
            rang_apply(run / "apply" / case / f"{mode}.ms", run, case, mode)
            rang_s[f"{case}/{mode}"] = time.perf_counter() - t0
    (run / "export").mkdir()
    results = {}
    for case in CASES:
        base = case_copy(run, case, "input")
        f0 = columns(base, ("FLAG", "FIELD_ID"))
        s = f0["FIELD_ID"] == fid
        f0 = f0["FLAG"][s]
        c = {
            k: columns(run / "apply" / case / f"{k}.ms")
            for k in ("casa", "spread", "none")
        }
        cf = c["casa"]["FLAG"][s]
        r = {}
        for mode in ("spread", "none"):
            rf = c[mode]["FLAG"][s]
            ok = ~cf & ~rf
            vr, vc = c[mode]["CORRECTED_DATA"][s], c["casa"]["CORRECTED_DATA"][s]
            scale = np.max(np.abs(vc), axis=-1, keepdims=True)
            rel = (np.abs(vr - vc) / np.where(scale > 0, scale, 1))[ok]
            r[mode] = {
                "flags_exact": bool(np.array_equal(rf, cf)),
                "rang_only": counts(rf & ~cf),
                "casa_only": counts(cf & ~rf),
                **{f"rang_{k}": v for k, v in counts(rf & ~f0).items()},
                "class_b_median": float(np.median(rel)) if rel.size else None,
                "class_b_p95": float(np.percentile(rel, 95)) if rel.size else None,
            }
        results[case] = {
            "casa": counts(cf & ~f0),
            "casa_four_equal": bool(np.all(cf == cf[..., :1])),
            "spread": r["spread"],
            "none": r["none"],
            "spread_none_values_identical": bool(
                np.array_equal(
                    c["spread"]["CORRECTED_DATA"].view(np.uint32),
                    c["none"]["CORRECTED_DATA"].view(np.uint32),
                )
            ),
            "pass": r["spread"]["flags_exact"],
        }
        np.savez_compressed(
            run / "export" / f"{case}.npz",
            input=f0,
            casa=cf,
            spread=c["spread"]["FLAG"][s],
            none=c["none"]["FLAG"][s],
        )
        print(case, json.dumps(results[case]), flush=True)
    out = {
        "seed": SEED,
        "image": IMAGE,
        "cases": results,
        "pass": all(v["pass"] for v in results.values()),
        "casa_wall_s": casa_s,
        "rang_wall_s": rang_s,
        "wall_s": time.perf_counter() - started,
    }
    (run / "result.json").write_text(json.dumps(out, indent=1))
    shutil.rmtree(run / "apply")
    shutil.rmtree(run / "base.ms")
    print("pass" if out["pass"] else "FAIL")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
