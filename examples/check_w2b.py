"""Host checker of W2b (research/c4b-apply-ms.md, sections 3.3 and 3.4) on
copies of A1's small MS: `rang-core calibrate` with a setjy model against
`calmodels.set_model` and `core.solve_complex`, `rang-core apply` of the
complex term against a float64 NumPy reference, and `rang-core run` through
flag, calibrate, apply and image.

    python examples/check_w2b.py <run> [--gemclean PATH] [--strategy PATH]

No CASA. Writes `<run>/w2b.json`; the MS copies are removed at the end.
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from rang import cal_apply, calmodels, core, core_ms, core_pipeline
from rang.formats import flagversions, quartical_store

A1_SMALL = Path("/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms")
STRATEGY = (
    Path.home()
    / "Github/rang/outputs/caracal-strategy-inputs-8f7bb363"
    / "mk_rfi_flagging_calibrator_fields_firstpass.yaml"
)
GEMCLEAN = Path.home() / "Github/rang/core/target/release/gemclean"
SEED = 20261109
FCAL = "J1939-6342"
FREQINT = [16]  # --freqint N changes it (reported runs)


def config_text(gemclean, stages, column="auto", fields=(FCAL,)):
    return (
        "schema: rang-config\nversion: 1\n"
        f"fields: {{fcal: [{FCAL}], target: [SIM-TARGET]}}\n"
        "flag: {strategy: strategy.yaml}\n"
        "calibrate:\n"
        "  model: {source: setjy, standard: Stevens-Reynolds 2016}\n"
        f"  primary:\n    terms: [{{type: complex, solint: int, freqint: {FREQINT[0]}}}]\n"
        "image:\n"
        f"  gemclean: {gemclean}\n  fields: [{', '.join(fields)}]\n"
        f"  column: {column}\n"
        "  size: [512, 512]\n  scale: 2asec\n  niter: 2000\n  threads: 2\n"
        f"run: {{stages: [{', '.join(stages)}]}}\n"
    )


def cols(ms, names):
    with core_ms.open_table(ms) as t:
        return {n: t.getcol(n) for n in names}


def reference_apply(data, flag, a1, a2, gains, valid, tb, fb):
    """float64 NumPy reference (section 3.3), vectorised over cells."""
    gp = gains[tb[:, None], fb[None, :], a1[:, None]]
    gq = gains[tb[:, None], fb[None, :], a2[:, None]]
    okp = valid[tb[:, None], fb[None, :], a1[:, None]] & (np.abs(np.linalg.det(gp)) > 0)
    okq = valid[tb[:, None], fb[None, :], a2[:, None]] & (np.abs(np.linalg.det(gq)) > 0)
    eye = np.broadcast_to(np.eye(2), gp.shape)
    ip = np.where(
        okp[..., None, None],
        np.linalg.inv(np.where(okp[..., None, None], gp, eye)),
        eye,
    )
    iq = np.where(
        okq[..., None, None],
        np.linalg.inv(np.where(okq[..., None, None], gq, eye)),
        eye,
    )
    v = data.astype(np.complex128).reshape(*data.shape[:2], 2, 2)
    out = (ip @ v @ iq.conj().swapaxes(-1, -2)).reshape(data.shape).astype(np.complex64)
    bad = flag.any(axis=-1) | ~(okp & okq)
    return out, np.repeat(bad[..., None], 4, axis=-1)


def cli(run, name, *argv):
    started = time.perf_counter()
    done = subprocess.run(
        [sys.executable, "-m", "rang.core_cli", *map(str, argv)],
        capture_output=True,
        text=True,
        check=False,
    )
    (run / f"{name}.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    return {"exit": done.returncode, "wall_s": time.perf_counter() - started}


def partitions_check(ms, store, flag_in):
    """Criterion 11 on every partition of the store: CORRECTED_DATA against
    the reference, flags exact."""
    c = cols(
        ms,
        (
            "FIELD_ID",
            "SCAN_NUMBER",
            "TIME",
            "ANTENNA1",
            "ANTENNA2",
            "DATA",
            "CORRECTED_DATA",
            "FLAG",
        ),
    )
    info = core_pipeline.inspect_ms(ms)
    results, solved = [], np.zeros(len(c["TIME"]), bool)
    for p in quartical_store.read(store)["complex"]:
        rows = np.flatnonzero(
            (c["FIELD_ID"] == p.attrs["FIELD_ID"])
            & (c["SCAN_NUMBER"] == p.attrs["SCAN_NUMBER"])
        )
        rows = rows[np.argsort(c["TIME"][rows], kind="stable")]
        tb, fb, _, _ = core_pipeline.solution_grid(
            c["TIME"][rows], info["cell"][0], info["chan_freq"], "int", FREQINT[0]
        )
        gains = p.gains_2x2()[:, :, :, 0]
        valid = (p["gain_flags"][:, :, :, 0] == 0) & np.isfinite(gains).all(
            axis=(-1, -2)
        )
        want, wflag = reference_apply(
            c["DATA"][rows],
            flag_in[rows],
            c["ANTENNA1"][rows],
            c["ANTENNA2"][rows],
            gains,
            valid,
            tb,
            fb,
        )
        every = np.ones(want.shape, bool)
        results.append(
            {
                "partition": p.name,
                "field": p.attrs["FIELD_NAME"],
                "scan": p.attrs["SCAN_NUMBER"],
                "class_c": cal_apply.class_c(c["CORRECTED_DATA"][rows], want, every),
                "flags_exact": bool(np.array_equal(c["FLAG"][rows], wflag)),
            }
        )
        solved[rows] = True
    others = {
        "corrected_equals_data": bool(
            c["CORRECTED_DATA"][~solved].tobytes() == c["DATA"][~solved].tobytes()
        ),
        "flag_unchanged": bool(np.array_equal(c["FLAG"][~solved], flag_in[~solved])),
    }
    return results, others


def main(argv):
    args = argv[1:]
    if "--freqint" in args:
        FREQINT[0] = int(args[args.index("--freqint") + 1])
    run = Path(args[0]).resolve()
    gemclean = (
        Path(args[args.index("--gemclean") + 1]) if "--gemclean" in args else GEMCLEAN
    )
    strategy = (
        Path(args[args.index("--strategy") + 1]) if "--strategy" in args else STRATEGY
    )
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    shutil.copy(strategy, run / "strategy.yaml")
    for name in ("model", "direct", "e2e"):
        shutil.copytree(A1_SMALL, run / f"{name}.ms")
    out = {
        "inputs": {
            "ms": str(A1_SMALL),
            "strategy": str(strategy),
            "gemclean": str(gemclean),
        }
    }

    # Criterion 12: the model and the solve against it.
    (run / "calibrate.yaml").write_text(
        config_text(gemclean, ["calibrate"]), encoding="utf-8"
    )
    out["12_calibrate"] = cli(
        run, "calibrate", "calibrate", run / "calibrate.yaml", run / "model.ms"
    )
    calmodels.set_model(
        run / "direct.ms", FCAL, calmodels.Standard(standard="Stevens-Reynolds 2016")
    )
    m1 = cols(run / "model.ms", ("MODEL_DATA",))["MODEL_DATA"]
    m2 = cols(run / "direct.ms", ("MODEL_DATA",))["MODEL_DATA"]
    out["12_model_identical"] = bool(m1.tobytes() == m2.tobytes())
    c = cols(
        run / "model.ms",
        (
            "FIELD_ID",
            "SCAN_NUMBER",
            "TIME",
            "ANTENNA1",
            "ANTENNA2",
            "DATA",
            "FLAG",
            "FLAG_ROW",
            "WEIGHT_SPECTRUM",
        ),
    )
    info = core_pipeline.inspect_ms(run / "model.ms")
    fid = info["fields"].index(FCAL)
    store = run / "model.ms.rang-run" / "calibrate" / "complex.qc"
    same, oracle_parts = [], []
    for p in quartical_store.read(store)["complex"]:
        rows = np.flatnonzero(
            (c["FIELD_ID"] == fid) & (c["SCAN_NUMBER"] == p.attrs["SCAN_NUMBER"])
        )
        rows = rows[np.argsort(c["TIME"][rows], kind="stable")]
        tb, fb, gt, gf = core_pipeline.solution_grid(
            c["TIME"][rows], info["cell"][0], info["chan_freq"], "int", FREQINT[0]
        )
        sol = core.solve_complex(
            c["DATA"][rows],
            c["WEIGHT_SPECTRUM"][rows],
            c["FLAG"][rows],
            c["FLAG_ROW"][rows],
            c["ANTENNA1"][rows],
            c["ANTENNA2"][rows],
            tb,
            fb,
            ntime_bins=len(gt),
            nfreq_bins=len(gf),
            nant=len(info["antennas"]),
            model=m2[rows],
        )
        same.append(
            bool(
                p["gains"].reshape(sol.gains.shape).tobytes() == sol.gains.tobytes()
                and np.array_equal(p["gain_flags"][..., 0], sol.flags)
            )
        )
        oracle_parts.append(
            quartical_store.complex_partition(
                sol.gains[:, :, :, None],
                sol.flags[:, :, :, None],
                gt,
                gf,
                info["antennas"],
                name="complex",
                field_id=fid,
                field_name=FCAL,
                scan=int(p.attrs["SCAN_NUMBER"]),
                ddid=int(p.attrs["DATA_DESC_ID"]),
            )
        )
    out["12_gains_identical"] = same
    # The W2 criterion 3 oracle: every file of the store byte-identical.
    oracle = run / "oracle-complex.qc"
    quartical_store.write({"complex": oracle_parts}, oracle)
    files = sorted(q.relative_to(store) for q in store.rglob("*") if q.is_file())
    theirs = sorted(q.relative_to(oracle) for q in oracle.rglob("*") if q.is_file())
    out["12_store_files"] = len(files)
    out["12_store_identical"] = bool(
        files == theirs
        and all((store / f).read_bytes() == (oracle / f).read_bytes() for f in files)
    )

    # Criteria 11 and 14: run through flag, calibrate, apply, image.
    stages = ["flag", "calibrate", "apply", "image"]
    (run / "e2e.yaml").write_text(config_text(gemclean, stages), encoding="utf-8")
    out["14_run"] = cli(run, "run", "run", run / "e2e.yaml", run / "e2e.ms")
    rdir = run / "e2e.ms.rang-run"
    state = json.loads((rdir / "state.json").read_text(encoding="utf-8"))
    out["14_status"] = {s: e["status"] for s, e in state["stages"].items()}
    out["14_receipts"] = sorted(p.name for p in (rdir / "receipts").glob("*.json"))
    img = json.loads((rdir / "image" / "summary.json").read_text(encoding="utf-8"))
    out["14_image_column"] = img["column"]
    apply_version = state["stages"]["apply"]["flag_version"]
    flag_in = flagversions.load(run / "e2e.ms", apply_version)[0]
    res, others = partitions_check(
        run / "e2e.ms", rdir / "calibrate" / "complex.qc", flag_in
    )
    out["11_partitions"], out["11_other_rows"] = res, others
    # Criterion 11, second case: 10 % of the gains made invalid.
    rng = np.random.default_rng(SEED)
    c = cols(
        run / "e2e.ms",
        ("FIELD_ID", "SCAN_NUMBER", "TIME", "ANTENNA1", "ANTENNA2", "DATA"),
    )
    seeded = []
    for p in quartical_store.read(rdir / "calibrate" / "complex.qc")["complex"]:
        rows = np.flatnonzero(
            (c["FIELD_ID"] == p.attrs["FIELD_ID"])
            & (c["SCAN_NUMBER"] == p.attrs["SCAN_NUMBER"])
        )
        rows = rows[np.argsort(c["TIME"][rows], kind="stable")]
        tb, fb, _, _ = core_pipeline.solution_grid(
            c["TIME"][rows], info["cell"][0], info["chan_freq"], "int", FREQINT[0]
        )
        gains = p.gains_2x2()[:, :, :, 0]
        valid = (p["gain_flags"][:, :, :, 0] == 0) & (
            rng.random(gains.shape[:3]) >= 0.1
        )
        got, gflag = cal_apply.apply_jones(
            c["DATA"][rows],
            flag_in[rows],
            c["ANTENNA1"][rows],
            c["ANTENNA2"][rows],
            gains,
            valid,
            tb,
            fb,
        )
        want, wflag = reference_apply(
            c["DATA"][rows],
            flag_in[rows],
            c["ANTENNA1"][rows],
            c["ANTENNA2"][rows],
            gains,
            valid,
            tb,
            fb,
        )
        seeded.append(
            {
                "partition": p.name,
                "invalid_fraction": float((~valid).mean()),
                "class_c": cal_apply.class_c(got, want, np.ones(want.shape, bool)),
                "flags_exact": bool(np.array_equal(gflag, wflag)),
            }
        )
    out["11_seeded_invalid"] = seeded

    # Reported: the image peaks of CORRECTED_DATA and of DATA.
    (run / "data.yaml").write_text(
        config_text(gemclean, ["image"], column="DATA"), encoding="utf-8"
    )
    out["14_image_data"] = cli(
        run,
        "image-data",
        "image",
        run / "data.yaml",
        run / "e2e.ms",
        "--run-dir",
        run / "data.rang-run",
    )
    from astropy.io import fits

    def peak(path):
        with fits.open(path) as h:
            a = np.asarray(h[0].data, float).squeeze()
        return {"max": float(a.max()), "min": float(a.min())}

    model_i = calmodels.Standard(standard="Stevens-Reynolds 2016").stokes(
        [float(np.mean(info["chan_freq"]))], FCAL
    )[0][0]
    out["14_reported"] = {
        "model_stokes_i_band_centre_jy": float(model_i),
        "corrected_image": peak(rdir / "image" / FCAL / "image-image.fits"),
        "data_image": peak(run / "data.rang-run" / "image" / FCAL / "image-image.fits"),
    }
    verdict = {
        "11": all(r["class_c"]["pass"] and r["flags_exact"] for r in res + seeded)
        and all(others.values()),
        "12": out["12_calibrate"]["exit"] == 0
        and out["12_model_identical"]
        and all(same)
        and out["12_store_identical"],
        "14": out["14_run"]["exit"] == 0
        and set(out["14_status"].values()) == {"done"}
        and out["14_image_column"] == "CORRECTED_DATA",
    }
    verdict["all"] = all(verdict.values())
    out["verdicts"] = verdict
    out["wall_s"] = time.perf_counter() - started
    (run / "w2b.json").write_text(
        json.dumps(out, indent=1, default=str), encoding="utf-8"
    )
    for name in ("model", "direct", "e2e"):
        shutil.rmtree(run / f"{name}.ms")
    print(json.dumps(verdict, indent=1))
    return 0 if verdict["all"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
