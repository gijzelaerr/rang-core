"""Self-calibration arms 1 and 2 of issue #6 (research/selfcal-arms.md): C5's
loop with more rounds and longer first solution intervals (arm `r`) and with
a phase-only first round (arm `p`, delay loop), against C5's arm `u`, scored
with C5's frozen T2 limits under the note's frozen round mapping (section 4).
Native Windows (or any host with the worktree venv).

    python examples/check_selfcal_arms.py loop RUN CASE ARM LOOP  # run, score
    python examples/check_selfcal_arms.py score RUN CASE ARM LOOP # score again
    python examples/check_selfcal_arms.py qc RUN CASE ARM LOOP    # QuartiCal (WSL)
    python examples/check_selfcal_arms.py table RUN               # the results
    python examples/check_selfcal_arms.py verdict RUN             # section 5

RUN is `D:\\rang\\outputs\\selfcal-arms-<date>-NN`. CASE is c5pa, c5delay,
c5pa-held, c5delay-held, c5pa-held2 or c5delay-held2 (generated once by
`examples/c5_selfcal_sim.py` into RUN/data/ and copied per run). ARM is u, r
or p (p on the delay loop only), or a post-hoc variant registered in
`VARIANTS`. LOOP is pa or delay. The stage runs under the main checkout's
`tools/heavy_lock.py` with shared slots (`RANG_ARMS_SLOTS`, default 4; memory
`RANG_ARMS_MEM`, default 4 GB); gemclean is `RANG_ARMS_GEMCLEAN` or `auto`
(the extension's); the image's `threads` is
`RANG_ARMS_THREADS` (default 4; `default` for gemclean's own). Each result
is RUN/loop-<ARM>-<LOOP>-<CASE>.json. Exit status 0 when every gated row
passes.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import check_c5 as c5
import check_c5b as c5b
from rang import cal_selfcal, core_model, core_ms

EXE = ".exe" if os.name == "nt" else ""
# `auto`: the extension's gemclean (task G8), recorded by rang._core's sha256.
GEMCLEAN = os.environ.get("RANG_ARMS_GEMCLEAN", "auto")
RANG_CORE = Path(sys.executable).parent / f"rang-core{EXE}"
# The main checkout's lock (AGENTS.md), shared slots at normal priority.
MAIN_LOCK = Path(r"C:\Users\gijsm\Github\rang\tools\heavy_lock.py")
SLOTS = os.environ.get("RANG_ARMS_SLOTS", "4")
MEM = os.environ.get("RANG_ARMS_MEM", "4")
THREADS = os.environ.get("RANG_ARMS_THREADS", "4")


def lock(slots=SLOTS, mem=MEM):
    script = MAIN_LOCK if MAIN_LOCK.is_file() else ROOT / "tools" / "heavy_lock.py"
    return [sys.executable, str(script), "run", "--slots", str(slots), "--mem",
            str(mem), "--"]  # fmt: skip


# Frozen (research/selfcal-arms.md, section 4). C5's image section
# (check_c5.IMAGE) for every arm, with `threads` from RANG_ARMS_THREADS.
SCHEDULES = {
    ("u", "pa"): (2, "[{type: Sp, solint: 8}, {type: Sa, solint: 8}]"),
    ("u", "delay"): (2, "[{type: Sd, solint: 8}, {type: Sd, solint: 8}]"),
    ("r", "pa"): (
        5,
        (
            "[{type: Sp, solint: inf}, {type: Sp, solint: inf}, {type: Sp, solint: 8}, "
            "{type: Sp, solint: 8}, {type: Sa, solint: 8}]"
        ),
    ),
    ("r", "delay"): (
        5,
        (
            "[{type: Sd, solint: inf}, {type: Sd, solint: inf}, {type: Sd, solint: 8}, "
            "{type: Sd, solint: 8}, {type: Sd, solint: 8}]"
        ),
    ),
    ("p", "delay"): (2, "[{type: Sp, solint: 8, freqint: 1}, {type: Sd, solint: 8}]"),
}
# Post-hoc variants (section 6, step 4): at most one per arm, development
# first, labelled post hoc in the note. None registered at the freeze of the
# protocol.
VARIANTS = {}
FROZEN_ARMS = ("u", "r", "p")
HELD_OUT = {
    "pa": ("c5pa-held", "c5pa-held2"),
    "delay": ("c5delay-held", "c5delay-held2"),
}
DEVELOPMENT = {"pa": "c5pa", "delay": "c5delay"}
# Section 5: the 20 % rule on round R's phase p95 against u's round 2.
HELPS, WORSE = 0.8, 1.2


def schedule(arm, loop):
    table = {**SCHEDULES, **VARIANTS}
    if (arm, loop) not in table:
        raise SystemExit(f"no arm {arm!r} on loop {loop!r} (section 4 of the note)")
    return table[(arm, loop)]


def image_text(gemclean):
    image = c5.IMAGE[:-1]
    if THREADS != "default":
        image += f", threads: {int(THREADS)}"
    if gemclean != "auto":
        gemclean = Path(gemclean).as_posix()
    return image + f", gemclean: '{gemclean}'}}"


def config_text(arm, loop, gemclean=GEMCLEAN):
    rounds, terms = schedule(arm, loop)
    return (
        "schema: rang-config\nversion: 1\nfields: {target: [SIM-TARGET]}\n"
        f"image: {image_text(gemclean)}\nselfcal:\n  rounds: {rounds}\n"
        f"  terms: {terms}\n  input_column: DATA\n  refant: 0\n"
        "run: {stages: [selfcal]}\n"
    )


def gates_of(loop, k, rounds, term):
    """The T2 rows round `k` of `rounds` is gated on (section 4): round R
    takes the round-2 rows; round R - 1 the round-1 rows its term has (the
    delay row only for Sd); earlier rounds none."""
    if k == rounds:
        return dict(c5.T2[(loop, 2)])
    if k == rounds - 1:
        rows = dict(c5.T2[(loop, 1)])
        if term["type"] != "Sd":
            rows.pop("delay_ns", None)
        return rows
    return None


def paths(run, case, arm, loop):
    d = Path(run) / f"{arm}-{loop}-{case}"
    return d, d / f"{case}.ms", d / "run"


def loop(run, case, arm, loop_name):
    d, ms, run_dir = paths(run, case, arm, loop_name)
    summary_path = run_dir / "selfcal" / "summary.json"
    if not summary_path.is_file():
        source = c5b.base_ms(run, case)
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        shutil.copytree(source, ms)
        for suffix in (".truth.npz", ".provenance.json"):
            src = source.with_suffix(suffix)
            if src.exists():
                shutil.copy(src, ms.with_suffix(suffix))
        config = d / "config.yaml"
        config.write_text(config_text(arm, loop_name), encoding="utf-8")
        argv = [*lock(), str(RANG_CORE), "selfcal", str(config), str(ms),
                "--run-dir", str(run_dir)]  # fmt: skip
        started = time.perf_counter()
        with (d / "stage.log").open("w", encoding="utf-8") as log:
            done = subprocess.run(
                argv, stdout=log, stderr=subprocess.STDOUT, check=False
            )
        c5.write(
            d / "stage-timing.json",
            {
                "wall_s_with_lock_wait": time.perf_counter() - started,
                "rc": done.returncode,
                "slots": SLOTS,
                "threads": THREADS,
            },
        )
        if done.returncode:
            raise SystemExit(f"stage exited {done.returncode}; see {d / 'stage.log'}")
    return score(run, case, arm, loop_name)


def stage_seconds(summary_field):
    """The stage's own time: every image, model, solve and apply."""
    total = 0.0
    for r in summary_field["rounds"]:
        total += r["image"]["wall_seconds"] + r["model"]["wall_seconds"]
        total += r["solve"]["wall_seconds"] + r["apply"]["wall_seconds"]
    return total + summary_field["final_image"]["wall_seconds"]


def score(run, case, arm, loop_name):
    d, ms, run_dir = paths(run, case, arm, loop_name)
    summary = json.loads((run_dir / "selfcal" / "summary.json").read_text())
    (field,) = summary["fields"]
    timing = json.loads((d / "stage-timing.json").read_text())
    rounds = len(field["rounds"])
    res = {
        "case": case,
        "arm": arm,
        "loop": loop_name,
        "post_hoc": arm not in FROZEN_ARMS,
        "held_out": case in HELD_OUT[loop_name],
        "schedule": schedule(arm, loop_name)[1],
        "gemclean": summary["gemclean"],
        "gemclean_sha256": summary["gemclean_sha256"],
        "stage_wall_s_with_lock_wait": timing["wall_s_with_lock_wait"],
        "stage_wall_s": stage_seconds(field),
        "rounds": [],
    }
    ok = True
    meta = c5.columns(ms, ["FIELD_ID", "TIME", "SCAN_NUMBER"])
    rows = np.flatnonzero(meta["FIELD_ID"] == 3)
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ")[0])
    images = []
    for r in field["rounds"]:
        k, term = r["round"], r["term"]
        sol = c5.solution_from_store(r, term, rows, meta, freq)
        got = c5.against_truth(ms, sol)
        entry = {"round": k, "term": term, "solve": r["solve"], "truth": got}
        if got is None:
            entry["scored"] = "not scored: a solution bin spans two truth blocks"
        else:
            entry["per_antenna_phase_deg_median"] = c5b.per_antenna_phase(sol, ms)
        gates = gates_of(loop_name, k, rounds, term)
        if gates:
            if got is None:  # the frozen schedules never gate such a round
                raise SystemExit(f"round {k} is gated but cannot be scored")
            entry["gated_rows"] = sorted(gates)
            entry["t2"] = c5.t2_gates(gates, got)
            ok &= entry["t2"]["pass"]
        res["rounds"].append(entry)
        images.append(r["image"])
    images.append(field["final_image"])
    res["images"] = [
        {key: im.get(key) for key in ("image", "column", "clean", "wall_seconds")}
        for im in images
    ]
    res["g4_apply"] = c5.final_apply(ms, field["rounds"][-1], rows, meta, freq)
    res["model_by_baseline"] = c5b.model_by_baseline(ms, rows)
    res["t2_pass"] = bool(ok)
    c5.write(Path(run) / f"loop-{arm}-{loop_name}-{case}.json", res)
    return ok


# --- QuartiCal 0.2.7 on the new interval forms (section 3) ---------------------


def wsl_path(path):
    p = Path(path).resolve()
    drive = p.drive.rstrip(":").lower()
    return f"/mnt/{drive}" + p.as_posix()[len(p.drive) :]


def qc(run, case, arm, loop_name, round_k=1):
    """Round `round_k`'s solve against QuartiCal 0.2.7 on the same
    MODEL_DATA (C5's G2, class B): rang's re-solve on a copy must equal the
    stored gains bit for bit, then the products (and delays) are compared."""
    d, ms, run_dir = paths(run, case, arm, loop_name)
    summary = json.loads((run_dir / "selfcal" / "summary.json").read_text())
    (field,) = summary["fields"]
    r = field["rounds"][round_k - 1]
    term = r["term"]
    qdir = d / "qc"
    qdir.mkdir(exist_ok=True)
    meta = c5.columns(ms, ["FIELD_ID", "TIME", "SCAN_NUMBER"])
    rows = np.flatnonzero(meta["FIELD_ID"] == 3)
    if r["apply"]["cells_flagged_after"] != r["apply"]["cells_flagged_before"]:
        raise SystemExit("the round flagged data; the copy's FLAG would differ")
    if round_k != 1:
        raise SystemExit("only round 1 is compared: later rounds' FLAG may differ")
    copy = qdir / f"round-{round_k}.ms"
    started = time.perf_counter()
    if not copy.exists():
        source = c5b.base_ms(run, case)  # round 1 solves the pristine DATA
        shutil.copytree(source, copy)
        prefix = Path(r["store"]).parent / "image"
        core_model.write_model_data(copy, prefix, 3, stage="selfcal-arms-qc")
    again = cal_selfcal.solve(
        copy, {**term}, rows=rows, field_id=3, input_column="DATA",
        model_column="MODEL_DATA", weight_column="WEIGHT_SPECTRUM", refant=0,
        gain_clip=(0.5, 2.0),
    )  # fmt: skip
    stored, *_ = cal_selfcal.read_store(r["store"], term["name"])
    same = bool(np.array_equal(again.gains, stored))
    solint = term["solint"]
    n = 0 if solint == "inf" else (1 if solint == "int" else int(solint))
    fi = term.get("freqint", "inf")
    fint = 0 if term["type"] == "Sd" or fi == "inf" else int(fi)
    opts = [*c5.QC_OPTIONS, f"G.type={cal_selfcal.QUARTICAL[term['type']]}",
            f"G.time_interval={n}", f"G.freq_interval={fint}"]  # fmt: skip
    out = qdir / f"qc-round-{round_k}"
    if not (out / "summary.json").is_file():
        inner = (
            f"{c5.QC} -I /ex/oracle_gain.py qc-solve /run/round-{round_k}.ms "
            f"/run/qc-round-{round_k} " + " ".join(opts)
        )
        docker = ["docker", "run", "--rm", "--network", "none", "--user",
                  "1000:1000", "--tmpfs", "/tmp", "-e", "HOME=/tmp",
                  "-e", "OMP_NUM_THREADS=1", "-e", "NUMBA_CACHE_DIR=/run/numba",
                  "-v", f"{wsl_path(qdir)}:/run:rw", "-v", f"{wsl_path(HERE)}:/ex:ro",
                  "-w", "/tmp", c5.cf.FORMATS_IMAGE, "sh", "-c", inner]  # fmt: skip
        argv = [*lock(1, 3), "wsl", "-e", *docker]
        qc_started = time.perf_counter()
        done = subprocess.run(argv, capture_output=True, text=True, check=False)
        (qdir / "qc.log").write_text(done.stdout + done.stderr, encoding="utf-8")
        if done.returncode:
            raise SystemExit(
                f"QuartiCal exited {done.returncode}; see {qdir / 'qc.log'}"
            )
        qc_wall = time.perf_counter() - qc_started
    else:
        qc_wall = None
    entry = {"case": case, "arm": arm, "loop": loop_name, "round": round_k,
             "term": term, "resolve_equals_stage": same,
             "quartical_wall_s_with_lock_wait": qc_wall}  # fmt: skip
    entry.update(c5.qc_compare(out, term, again))
    entry["pass"] = bool(entry["pass"] and same)
    entry["wall_s"] = time.perf_counter() - started
    c5.write(Path(run) / f"qc-{arm}-{loop_name}-{case}-r{round_k}.json", entry)
    shutil.rmtree(copy, ignore_errors=True)
    return entry["pass"]


# --- tables and the verdict ------------------------------------------------------


def _fmt(e):
    t = e["truth"]
    if t is None:
        return "not scored", "–", "–"
    pr, dl = t["products"], t.get("delays")
    phase = f"{pr['phase_deg']['median']:.2f} / {pr['phase_deg']['p95']:.1f}"
    if e["term"]["type"] == "Sa":
        amp = (
            f"{100 * pr['amp_rel']['median']:.2f} / {100 * pr['amp_rel']['p95']:.2f} %"
            f" ({pr['amp_rel']['median'] / pr['uncorrected_amp_rel']['median']:.2f}×)"
        )
    else:
        amp = "–"
    delay = f"{dl['median']:.4f} / {dl['p95']:.3f}" if dl else "–"
    return phase, amp, delay


def table(run):
    lines = []
    for p in sorted(Path(run).glob("loop-*.json")):
        r = json.loads(p.read_text())
        for e in r["rounds"]:
            phase, amp, delay = _fmt(e)
            term = e["term"]
            what = f"{term['type']} {term['solint']}"
            if "freqint" in term:
                what += f"/{term['freqint']}"
            t2 = e.get("t2")
            failed = (
                "–"
                if t2 is None
                else ("pass" if t2["pass"] else ", ".join(
                    k for k, v in t2["checks"].items() if not v))
            )  # fmt: skip
            lines.append(
                f"| {r['case']} | {r['arm']} | {e['round']} {what} | {phase} | "
                f"{amp} | {delay} | {failed} |"
            )
        lines.append(
            f"|  |  | stage {r['stage_wall_s']:.0f} s; model rel rms by baseline "
            + ", ".join(f"{b['rel_rms']:.3f}" for b in r["model_by_baseline"])
            + f"; G4 apply {'pass' if r['g4_apply']['pass'] else 'FAIL'} |  |  |  |  |"
        )
    print("\n".join(lines))


def final_p95(res):
    return res["rounds"][-1]["truth"]["products"]["phase_deg"]["p95"]


def verdict(run):
    """Section 5 per arm and loop on the held-out cases."""
    out = {}
    for arm, loop_name in [*SCHEDULES, *VARIANTS]:
        if arm == "u":
            continue
        per_case, missing = {}, []
        for case in HELD_OUT[loop_name]:
            a = Path(run) / f"loop-{arm}-{loop_name}-{case}.json"
            b = Path(run) / f"loop-u-{loop_name}-{case}.json"
            if not (a.is_file() and b.is_file()):
                missing.append(case)
                continue
            ra, rb = json.loads(a.read_text()), json.loads(b.read_text())
            per_case[case] = {
                "t2_pass": ra["t2_pass"],
                "final_p95_deg": final_p95(ra),
                "u_final_p95_deg": final_p95(rb),
                "ratio": final_p95(ra) / final_p95(rb),
                "cost_ratio": ra["stage_wall_s"] / rb["stage_wall_s"],
            }
        if missing:
            out[f"{arm}-{loop_name}"] = {"missing": missing}
            continue
        ratios = [c["ratio"] for c in per_case.values()]
        if all(c["t2_pass"] for c in per_case.values()):
            v = "met"
        elif all(x <= HELPS for x in ratios):
            v = "helps, not met"
        elif any(x > WORSE for x in ratios):
            v = "worse"
        else:
            v = "null"
        out[f"{arm}-{loop_name}"] = {"verdict": v, "cases": per_case}
    c5.write(Path(run) / "verdict.json", out)
    print(json.dumps(out, indent=1))
    return out


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "table":
        table(argv[1])
        return 0
    if cmd == "verdict":
        verdict(argv[1])
        return 0
    if cmd not in ("loop", "score", "qc") or len(argv) != 5:
        raise SystemExit(__doc__)
    run, case, arm, loop_name = argv[1:5]
    schedule(arm, loop_name)
    fn = {"loop": loop, "score": score, "qc": qc}[cmd]
    ok = fn(run, case, arm, loop_name)
    print(f"{cmd} {case} {arm} {loop_name}: {'pass' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
