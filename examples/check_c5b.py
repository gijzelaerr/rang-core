"""Host side of task C5b (research/c5b-selfcal-masks.md): C5's self-calibration
loops on C5's simulated truths, with and without CARACal's per-image clean
masks and cut-offs, scored with C5's frozen T2 limits. Native Windows (or any
host with the worktree venv), gemclean built from the worktree.

    python examples/check_c5b.py loop RUN CASE ARM LOOP   # run the stage once, score
    python examples/check_c5b.py score RUN CASE ARM LOOP  # score an existing run
    python examples/check_c5b.py table RUN                # every result as a table

RUN is `D:\\rang\\outputs\\c5b-<date>-NN`. CASE is one of C5's c5pa, c5delay,
c5pa-held, c5delay-held or C5b's c5pa-held2, c5delay-held2 (generated once by
`examples/c5_selfcal_sim.py` into RUN/data/ and copied per run). ARM is u (C5's
frozen, unmasked images), m (the frozen masked arm, gated) or mh (the masked
arm with Hogbom CLEAN, reported). LOOP is pa or delay (C5's L-pa, L-delay).
The stage runs under `tools/heavy_lock.py`; each result is
RUN/loop-<ARM>-<LOOP>-<CASE>.json. Exit status 0 when the T2 limits of every
gated round pass.
"""

import hashlib
import itertools
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
from rang import core_ms

EXE = ".exe" if os.name == "nt" else ""
GEMCLEAN = ROOT / "core" / "target" / "gemclean" / f"gemclean{EXE}"
RANG_CORE = Path(sys.executable).parent / f"rang-core{EXE}"
LOCK = [sys.executable, str(ROOT / "tools" / "heavy_lock.py"), "run", "--"]

# C5's frozen image section (research/c5-selfcal.md, section 3).
IMAGE_U = (
    "{fields: [target], size: 2048, scale: 2asec, weight: briggs, robust: 0.0, "
    "niter: 100000, auto_threshold: 3.0, gemclean: '%s'}"
)
# Frozen in research/c5b-selfcal-masks.md, section 3: CARACal 8f7bb363's
# selfcal image defaults (img_mgain 0.9, img_niter 1e6, clean_cutoff [0.5],
# cleanmask_method [wsclean], cleanmask_thr [10, 6]) with multiscale on.
IMAGE_M = (
    "{fields: [target], size: 2048, scale: 2asec, weight: briggs, robust: 0.0, "
    "niter: 1000000, mgain: 0.9, multiscale: %s, gemclean: '%s'}"
)
MASKS = (
    "  cleanmask_method: [wsclean]\n  cleanmask_thr: [10, 6]\n  clean_cutoff: [0.5]\n"
)
ARMS = ("u", "m", "mh")
GATED_ARM = "m"
HELD_OUT = ("c5pa-held2", "c5delay-held2", "c5pa-held", "c5delay-held")
BASELINE_BINS_M = (0, 500, 1000, 2000, 4000, 6000, 1e9)


def write(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, default=float) + "\n")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def config_text(arm, loop):
    gem = GEMCLEAN.as_posix()
    if arm == "u":
        image, masks = IMAGE_U % gem, ""
    else:
        image, masks = IMAGE_M % ("true" if arm == "m" else "false", gem), MASKS
    return (
        "schema: rang-config\nversion: 1\nfields: {target: [SIM-TARGET]}\n"
        f"image: {image}\nselfcal:\n  rounds: 2\n  terms: {c5.LOOPS[loop]}\n"
        f"  input_column: DATA\n  refant: 0\n{masks}run: {{stages: [selfcal]}}\n"
    )


def paths(run, case, arm, loop):
    d = Path(run) / f"{arm}-{loop}-{case}"
    return d, d / f"{case}.ms", d / "run"


def base_ms(run, case):
    """The case's MS in RUN/data (generated once, never written by a loop)."""
    data = Path(run) / "data"
    data.mkdir(parents=True, exist_ok=True)
    ms = data / f"{case}.ms"
    if not ms.exists():
        started = time.perf_counter()
        c5.generate(case, data)
        write(data / f"{case}.timing.json", {"wall_s": time.perf_counter() - started})
    return ms


def loop(run, case, arm, loop_name):
    d, ms, run_dir = paths(run, case, arm, loop_name)
    summary_path = run_dir / "selfcal" / "summary.json"
    if not summary_path.is_file():
        source = base_ms(run, case)
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
        argv = [*LOCK, str(RANG_CORE), "selfcal", str(config), str(ms),
                "--run-dir", str(run_dir)]  # fmt: skip
        started = time.perf_counter()
        with (d / "stage.log").open("w", encoding="utf-8") as log:
            done = subprocess.run(
                argv, stdout=log, stderr=subprocess.STDOUT, check=False
            )
        write(
            d / "stage-timing.json",
            {
                "wall_s_with_lock_wait": time.perf_counter() - started,
                "rc": done.returncode,
            },
        )
        if done.returncode:
            raise SystemExit(f"stage exited {done.returncode}; see {d / 'stage.log'}")
    return score(run, case, arm, loop_name)


def model_by_baseline(ms, rows):
    """rms |MODEL_DATA - MODEL_TRUE| / rms |MODEL_TRUE| (XX) per baseline
    length bin: the last round's model against the sky (C5's diag2)."""
    c = c5.columns(ms, ["UVW", "MODEL_DATA", "MODEL_TRUE"], rows)
    length = np.linalg.norm(c["UVW"][:, :2], axis=1)
    out = []
    for lo, hi in itertools.pairwise(BASELINE_BINS_M):
        sel = (length >= lo) & (length < hi)
        if not sel.any():
            continue
        m, t = c["MODEL_DATA"][sel, :, 0], c["MODEL_TRUE"][sel, :, 0]
        rel = np.sqrt(np.mean(np.abs(m - t) ** 2) / np.mean(np.abs(t) ** 2))
        out.append({"m": [lo, None if hi >= 1e9 else hi], "rows": int(sel.sum()),
                    "rel_rms": float(rel)})  # fmt: skip
    return out


def per_antenna_phase(sol, ms):
    """Median |Δ arg P| (deg) per antenna over its products (reported)."""
    from rang import cal_gain

    truth = c5.truth_of(ms)
    t = c5.columns(ms, ["TIME"], sol.rows)["TIME"]
    blocks = c5.bin_blocks(sol.time_bin, t, truth)
    gt = c5.truth_gains(truth, blocks, sol.gains.shape[1], sol.freq_bin)
    p, ok, _ = cal_gain.baseline_products(sol.gains, sol.flags)
    pt, _, _ = cal_gain.baseline_products(gt, np.zeros(gt.shape, bool))
    nant = sol.gains.shape[2]
    a, b = np.triu_indices(nant, 1)
    err = np.degrees(np.abs(np.angle(p / pt)))
    out = []
    for ant in range(nant):
        pair = (a == ant) | (b == ant)
        sel = ok[:, :, pair]
        out.append(float(np.median(err[:, :, pair][sel])) if sel.any() else None)
    return out


def score(run, case, arm, loop_name):
    d, ms, run_dir = paths(run, case, arm, loop_name)
    summary = json.loads((run_dir / "selfcal" / "summary.json").read_text())
    (field,) = summary["fields"]
    timing = json.loads((d / "stage-timing.json").read_text())
    res = {
        "case": case,
        "arm": arm,
        "loop": loop_name,
        "gated": arm == GATED_ARM,
        "held_out": case in HELD_OUT,
        "gemclean": summary["gemclean"],
        "gemclean_sha256": summary["gemclean_sha256"],
        "stage_wall_s_with_lock_wait": timing["wall_s_with_lock_wait"],
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
        entry = {
            "round": k,
            "term": term,
            "solve": r["solve"],
            "truth": got,
            "per_antenna_phase_deg_median": per_antenna_phase(sol, ms),
        }
        gates = c5.T2.get((loop_name, k))
        if gates and got is not None:
            entry["t2"] = c5.t2_gates(gates, got)
            ok &= entry["t2"]["pass"]
        res["rounds"].append(entry)
        images.append(r["image"])
    images.append(field["final_image"])
    res["images"] = [
        {
            key: im.get(key)
            for key in (
                "image",
                "column",
                "auto_threshold",
                "auto_mask",
                "clean",
                "wall_seconds",
            )
        }
        for im in images
    ]
    final = field["rounds"][-1]
    res["g4_apply"] = c5.final_apply(ms, final, rows, meta, freq)
    res["model_by_baseline"] = model_by_baseline(ms, rows)
    res["t2_pass"] = bool(ok)
    write(Path(run) / f"loop-{arm}-{loop_name}-{case}.json", res)
    return ok


def table(run):
    rows = []
    for p in sorted(Path(run).glob("loop-*.json")):
        r = json.loads(p.read_text())
        for e in r["rounds"]:
            pr = e["truth"]["products"]
            dl = e["truth"].get("delays")
            rows.append(
                f"| {r['case']} | {r['arm']} | r{e['round']} {e['term']['type']} | "
                f"{pr['phase_deg']['median']:.3f} / {pr['phase_deg']['p95']:.2f} | "
                + (
                    f"{100 * pr['amp_rel']['median']:.2f} / {100 * pr['amp_rel']['p95']:.2f} %"
                    if e["term"]["type"] == "Sa"
                    else f"({100 * pr['uncorrected_amp_rel']['median']:.1f} %)"
                )
                + " | "
                + (f"{dl['median']:.4f} / {dl['p95']:.3f}" if dl else "–")
                + f" | {e.get('t2', {}).get('pass', '–')} |"
            )
        imgs = ", ".join(
            "{}:{}".format(i["image"], (i["clean"] or {}).get("components"))
            + "/"
            + str((i["clean"] or {}).get("stop"))
            for i in r["images"]
        )
        rows.append(f"|  |  | images {imgs} | model rel rms by baseline: "
                    + ", ".join(f"{b['rel_rms']:.3f}" for b in r["model_by_baseline"])
                    + " |  |  |  |")  # fmt: skip
    print("\n".join(rows))


def main(argv):
    cmd = argv[0]
    if cmd == "table":
        table(argv[1])
        return 0
    run, case, arm, loop_name = argv[1:5]
    if arm not in ARMS or loop_name not in ("pa", "delay"):
        raise SystemExit(__doc__)
    ok = (loop if cmd == "loop" else score)(run, case, arm, loop_name)
    print(f"{cmd} {case} {arm} {loop_name}: T2 {'pass' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
