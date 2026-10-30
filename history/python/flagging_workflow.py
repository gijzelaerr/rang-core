"""Recoverable real-MS experiment, exposed as Stimela2 Python callable cabs."""

import json
import os
import shutil
import subprocess
import time
import zipfile
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

import numpy as np

from .flagging import (
    assert_preserved,
    fixed_support_tv,
    gain_tv,
    polar_gauge,
    policy_mask,
    protected_flags,
    require_meerkat_lband,
    residual_features,
    snapshot_flags,
    split_holdout,
)

FIXTURE_SHA256 = "d4dae56f7ad1bb4a49ab8c4a3846871d5b8ebb4b731ee958cb9f1baf3306144f"
FIXTURE_SOURCE = "https://gitlab.com/ska-telescope/sdp/science-pipeline-workflows/ska-sdp-wflow-pointing-offset/-/tree/main/tests/data"


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def tree_digest(path):
    """Hash every original file except casacore's transient lock bookkeeping."""
    digest = sha256()
    for file in sorted(Path(path).rglob("*")):
        if file.is_file() and file.name != "table.lock":
            digest.update(str(file.relative_to(path)).encode())
            with file.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
    return digest.hexdigest()


def unpack_fixture(archive, destination):
    """Checksum-pinned extraction with the already verified archive validator."""
    if sha256(Path(archive).read_bytes()).hexdigest() != FIXTURE_SHA256:
        raise ValueError("unexpected public fixture checksum")
    # Reuse the inspector's archive safety checks without importing casacore.
    from importlib.util import module_from_spec, spec_from_file_location

    script = (
        Path(__file__).resolve().parents[2] / "examples/inspect_measurement_sets.py"
    )
    spec = spec_from_file_location("rang_ms_inspection", script)
    reader = module_from_spec(spec)
    spec.loader.exec_module(reader)
    destination.mkdir()
    with zipfile.ZipFile(archive) as zipped:
        reader.validate_members(zipped.infolist())
        zipped.extractall(destination)
    return destination / "outer_scans/1672727931_sdp_l0_scan_9.ms"


def prepare(
    run_dir,
    archive=None,
    ms=None,
    model_column=None,
    seed=7,
    channel_start=1024,
    channel_stop=3072,
    time_interval=2,
    freq_interval=32,
):
    """Create immutable original and working copies, model and fixed splits.

    An archive invokes only the pinned public fixture/phase-centre approximation.
    An external MS requires an existing model column and a single scan/SPW/field.
    Original flags mean the entire input state, even if prior pipeline flags exist.
    """
    from casacore.tables import makearrcoldesc, maketabdesc, table

    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    if bool(archive) == bool(ms):
        raise ValueError("supply exactly one of archive or ms")
    fixture = bool(archive)
    source = (
        unpack_fixture(archive, run_dir / "fixture") if fixture else Path(ms).resolve()
    )
    if not fixture and not model_column:
        raise ValueError("external data require a verified model column")
    if source.is_relative_to(run_dir) and not fixture:
        raise ValueError("external input must be outside the output directory")
    digest = tree_digest(source)
    shutil.copytree(source, run_dir / "original.ms")
    shutil.copytree(run_dir / "original.ms", run_dir / "work.ms")
    with table(
        str(run_dir / "original.ms"), readonly=True, ack=False, lockoptions="autonoread"
    ) as original:
        flags, rows = original.getcol("FLAG"), original.getcol("FLAG_ROW")
        data = original.getcol("DATA")
        times = original.getcol("TIME")
        p, q = original.getcol("ANTENNA1"), original.getcol("ANTENNA2")
        for column in ("SCAN_NUMBER", "FIELD_ID", "DATA_DESC_ID"):
            if len(np.unique(original.getcol(column))) != 1:
                raise ValueError(
                    "first experiment requires one scan, field and data descriptor"
                )
        if data.shape[-1] != 4 or data.shape != flags.shape:
            raise ValueError("full Jones experiment requires four correlations")
        if "WEIGHT_SPECTRUM" in original.colnames():
            weights = original.getcol("WEIGHT_SPECTRUM")
        else:
            weights = np.broadcast_to(
                original.getcol("WEIGHT")[:, None], data.shape
            ).copy()
        if not fixture:
            model = original.getcol(model_column)
    with table(
        str(source / "POLARIZATION"), readonly=True, ack=False, lockoptions="autonoread"
    ) as pol:
        if not np.array_equal(pol.getcol("CORR_TYPE"), [[9, 10, 11, 12]]):
            raise ValueError(
                "first experiment requires linear XX XY YX YY correlation order"
            )
    with table(
        str(source / "SPECTRAL_WINDOW"),
        readonly=True,
        ack=False,
        lockoptions="autonoread",
    ) as spw:
        if spw.nrows() != 1:
            raise ValueError(
                "first experiment requires exactly one spectral-window table row"
            )
        frequencies = spw.getcol("CHAN_FREQ")[0]
    with table(
        str(source / "OBSERVATION"), readonly=True, ack=False, lockoptions="autonoread"
    ) as observation:
        scope = require_meerkat_lband(observation.getcol("TELESCOPE_NAME"), frequencies)
        project = np.asarray(observation.getcol("PROJECT")).tolist()
    with table(
        str(source / "ANTENNA"), readonly=True, ack=False, lockoptions="autonoread"
    ) as antennas:
        names = antennas.getcol("NAME")
    if not 0 <= channel_start < channel_stop <= len(frequencies):
        raise ValueError("invalid initial channel window")
    if fixture:
        # Reynolds (1994), MHz and Jy. Explicitly approximate unpolarized point sky.
        log_nu = np.log10(frequencies / 1e6)
        flux = 10 ** (
            -30.7667 + 26.4908 * log_nu - 7.0977 * log_nu**2 + 0.605334 * log_nu**3
        )
        model = np.zeros_like(data)
        model[..., 0] = model[..., 3] = flux[None, :]
        model_column = "RANG_MODEL_DATA"
        with table(str(run_dir / "work.ms"), readonly=False, ack=False) as work:
            work.addcols(
                maketabdesc(
                    makearrcoldesc(model_column, 0j, ndim=2, valuetype="complex")
                )
            )
            work.putcol(model_column, model)
    if model.shape != data.shape or not np.isfinite(model).all():
        raise ValueError("finite full-correlation model matching DATA required")
    original_hash = snapshot_flags(run_dir / "backups/original-flags.npz", flags, rows)
    protected, _ = protected_flags(flags, rows, np.zeros_like(flags))
    window = np.zeros(len(frequencies), bool)
    window[channel_start:channel_stop] = True
    eligible = (~protected.any(axis=-1)) & (p != q)[:, None] & window[None]
    eligible &= (
        np.isfinite(data).all(axis=-1)
        & np.isfinite(weights).all(axis=-1)
        & (weights > 0).all(axis=-1)
    )
    if min(time_interval, freq_interval) < 1:
        raise ValueError("positive integer solution intervals required")
    time_bins = np.unique(times, return_inverse=True)[1] // time_interval
    freq_bins = np.arange(len(frequencies)) // freq_interval
    groups = (time_bins[:, None] * (freq_bins.max() + 1) + freq_bins[None]) * len(
        names
    ) ** 2 + (p * len(names) + q)[:, None]
    train, validation, test = split_holdout(eligible, seed, groups=groups)
    if min(np.count_nonzero(x) for x in (train, validation, test)) < 20:
        raise ValueError(
            "insufficient clean cross-correlation samples for fixed splits"
        )
    np.savez_compressed(
        run_dir / "state.npz",
        original_flags=flags,
        original_rows=rows,
        data=data,
        model=model,
        weights=weights,
        times=times,
        frequencies=frequencies,
        antenna1=p,
        antenna2=q,
        names=names,
        train=train,
        validation=validation,
        test=test,
        window=window,
    )
    manifest = {
        "fixture": fixture,
        "scope": scope,
        "observation_projects": project,
        "selected_frequency_range_mhz": (
            frequencies[[channel_start, channel_stop - 1]] / 1e6
        ).tolist(),
        "source": str(source),
        "source_url": FIXTURE_SOURCE if fixture else None,
        "archive_sha256": FIXTURE_SHA256 if fixture else None,
        "source_digest": digest,
        "original_copy_digest": tree_digest(run_dir / "original.ms"),
        "original_flag_snapshot_sha256": original_hash,
        "model_column": model_column,
        "model_convention": "unpolarized phase-centre Reynolds point approximation"
        if fixture
        else "user supplied",
        "seed": seed,
        "channels": [channel_start, channel_stop],
        "split_gain_intervals": [time_interval, freq_interval],
        "minimum_train_per_baseline_gain_bin": 2,
        "shape": list(data.shape),
        "original_cell_flag_fraction": float(np.mean(flags)),
        "original_row_flag_count": int(np.sum(rows)),
        "split_counts": {
            k: int(np.count_nonzero(v))
            for k, v in zip(("train", "validation", "test"), (train, validation, test))
        },
        "versions": {
            k: version(k)
            for k in (
                "quartical",
                "stimela",
                "numpy",
                "python-casacore",
                "dask-ms",
                "numba",
            )
        },
        "kernel_sha256": sha256(
            Path(os.environ["RANG_TOY_LIB"]).read_bytes()
        ).hexdigest()
        if "RANG_TOY_LIB" in os.environ
        else None,
        "code_sha256": {
            name: sha256(
                (Path(__file__).resolve().parents[2] / name).read_bytes()
            ).hexdigest()
            for name in (
                "python/rangtoy/flagging.py",
                "python/rangtoy/flagging_workflow.py",
                "src/tv.rs",
                "recipes/tv-flagging.yaml",
                "tools/flagging/Dockerfile",
                "tools/flagging/requirements.lock",
            )
        },
    }
    write_json(run_dir / "manifest.json", manifest)
    print(
        f"Prepared real data: {manifest['split_counts']}; every original flag protected",
        flush=True,
    )


def load_state(run_dir):
    with np.load(Path(run_dir) / "state.npz", allow_pickle=False) as saved:
        return {key: saved[key] for key in saved.files}


def set_flags(run_dir, state, added, trial, *, holdout=True):
    from casacore.tables import table

    temporary = np.zeros_like(state["original_flags"])
    # Exclude autocorrelations, outside-window channels, and all ineligible samples
    # from training, while leaving the final original state intact outside proposals.
    if holdout:
        temporary |= ~state["train"][..., None]
    temporary |= added[..., None]
    flags, rows = protected_flags(
        state["original_flags"], state["original_rows"], temporary
    )
    with table(str(Path(run_dir) / "work.ms"), readonly=False, ack=False) as work:
        snapshot_flags(
            Path(run_dir) / "backups" / f"{trial}-before.npz",
            work.getcol("FLAG"),
            work.getcol("FLAG_ROW"),
        )
        work.putcol("FLAG", flags)
        work.putcol("FLAG_ROW", rows)
        work.flush()
        assert_preserved(
            state["original_flags"],
            state["original_rows"],
            work.getcol("FLAG"),
            work.getcol("FLAG_ROW"),
        )
    snapshot_flags(Path(run_dir) / "backups" / f"{trial}-solve.npz", flags, rows)
    return flags, rows


def solve(
    run_dir,
    state,
    manifest,
    added,
    trial,
    time_interval,
    freq_interval,
    iterations,
    *,
    scale=None,
    gauge="polar",
):
    """Actual QuartiCal full-matrix solve; no synthetic substitute."""
    from casacore.tables import table
    from daskms.experimental.zarr import xds_from_zarr

    run_dir = Path(run_dir)
    directory = run_dir / "trials" / trial
    directory.mkdir(parents=True, exist_ok=False)
    flags, rows = set_flags(run_dir, state, added, trial)
    command = [
        "goquartical",
        f"input_ms.path={run_dir / 'work.ms'}",
        "input_ms.data_column=DATA",
        "input_ms.weight_column=WEIGHT_SPECTRUM",
        f"input_model.recipe={manifest['model_column']}",
        "solver.terms=[G]",
        "G.type=complex",
        f"G.time_interval={time_interval}",
        f"G.freq_interval={freq_interval}",
        f"solver.iter_recipe=[{iterations}]",
        "solver.convergence_criteria=1e-7",
        "solver.reference_antenna=0",
        "solver.robust=false",
        "mad_flags.enable=false",
        "output.flags=false",
        "output.overwrite=false",
        f"output.gain_directory={directory / 'gains.qc'}",
        f"output.log_directory={directory / 'logs.qc'}",
        "dask.threads=1",
        "solver.threads=1",
        "dask.scheduler=single-threaded",
    ]
    # Inputs without spectrum weights use the original row weights.
    with table(
        str(run_dir / "work.ms"), readonly=True, ack=False, lockoptions="autonoread"
    ) as work:
        if "WEIGHT_SPECTRUM" not in work.colnames():
            command[3] = "input_ms.weight_column=WEIGHT"
    write_json(directory / "command.json", command)
    started = time.perf_counter()
    with (directory / "quartical.log").open("x") as log:
        completed = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    elapsed = time.perf_counter() - started
    with table(
        str(run_dir / "work.ms"), readonly=True, ack=False, lockoptions="autonoread"
    ) as work:
        if not np.array_equal(work.getcol("FLAG"), flags) or not np.array_equal(
            work.getcol("FLAG_ROW"), rows
        ):
            raise RuntimeError("QuartiCal altered flags despite output.flags=false")
    if completed.returncode:
        write_json(
            directory / "failure.json",
            {"returncode": completed.returncode, "seconds": elapsed},
        )
        raise RuntimeError(f"QuartiCal failed; inspect {directory / 'quartical.log'}")
    datasets = xds_from_zarr(f"{directory / 'gains.qc'}::G")
    if len(datasets) != 1:
        raise ValueError("unexpected gain partition count")
    ds = datasets[0].compute()
    if (
        ds.attrs["TYPE"] != "complex"
        or ds.sizes["direction"] != 1
        or ds.sizes["correlation"] != 4
    ):
        raise ValueError(
            "QuartiCal did not produce direction-independent full 2x2 complex gains"
        )
    gains = (
        ds.gains.transpose(
            "gain_time", "gain_freq", "antenna", "direction", "correlation"
        )
        .values[..., 0, :]
        .reshape(
            ds.sizes["gain_time"], ds.sizes["gain_freq"], ds.sizes["antenna"], 2, 2
        )
    )
    valid = (
        ds.gain_flags.transpose(
            "gain_time", "gain_freq", "antenna", "direction"
        ).values[..., 0]
        == 0
    )
    valid &= np.isfinite(gains).all(axis=(-1, -2))
    unique_times, inverse_times = np.unique(state["times"], return_inverse=True)
    time_map = inverse_times // time_interval
    freq_map = np.arange(len(state["frequencies"])) // freq_interval
    expected_times = np.array(
        [
            np.mean(unique_times[i : i + time_interval])
            for i in range(0, len(unique_times), time_interval)
        ]
    )
    expected_freqs = np.array(
        [
            np.mean(state["frequencies"][i : i + freq_interval])
            for i in range(0, len(freq_map), freq_interval)
        ]
    )
    np.testing.assert_allclose(ds.gain_time.values, expected_times, rtol=0, atol=1e-5)
    np.testing.assert_allclose(ds.gain_freq.values, expected_freqs, rtol=0, atol=1e-4)
    if not np.array_equal(ds.antenna.values, state["names"]):
        raise ValueError("unexpected gain antenna order")
    p, q = state["antenna1"], state["antenna2"]
    gp = gains[time_map[:, None], freq_map[None], p[:, None]]
    gq = gains[time_map[:, None], freq_map[None], q[:, None]]
    model = state["model"].reshape(*state["model"].shape[:2], 2, 2)
    prediction = (gp @ model @ gq.conj().swapaxes(-1, -2)).reshape(state["data"].shape)
    residuals = state["data"] - prediction
    sample_valid = (
        valid[time_map[:, None], freq_map[None], p[:, None]]
        & valid[time_map[:, None], freq_map[None], q[:, None]]
    )
    if scale is None:
        scale = float(np.median(np.linalg.norm(gains[valid], axis=(-1, -2))))
    raw_tv = gain_tv(gains, valid, expected_times, expected_freqs, scale=scale)
    if gauge == "polar":
        aligned, tv_valid = polar_gauge(gains, valid)
    elif gauge == "raw":
        aligned, tv_valid = gains, valid
    else:
        raise ValueError("gauge must be polar (unpolarized model) or raw")
    tv = gain_tv(aligned, tv_valid, expected_times, expected_freqs, scale=scale)
    maps = tv["map"]
    guidance = np.maximum(
        maps[time_map[:, None], freq_map[None], p[:, None]],
        maps[time_map[:, None], freq_map[None], q[:, None]],
    )
    mse = np.mean(np.abs(residuals) ** 2 * state["weights"], axis=-1)
    losses = {}
    invalid_predictions = {}
    for split in ("train", "validation", "test"):
        mask = state[split]
        invalid_predictions[split] = int(np.count_nonzero(mask & ~sample_valid))
        # Never drop invalid predictions from evaluation to improve the metric.
        losses[split] = (
            float(np.mean(mse[mask]))
            if sample_valid[mask].all() and np.isfinite(mse[mask]).all()
            else None
        )
    np.savez_compressed(
        directory / "diagnostics.npz",
        gains=gains,
        gain_valid=valid,
        tv_valid=tv_valid,
        gauge_gains=aligned,
        edges=tv["edges"],
        tv_map=maps,
        raw_edges=raw_tv["edges"],
        guidance=guidance,
        residuals=residuals,
        added=added,
        gain_times=expected_times,
        gain_frequencies=expected_freqs,
    )
    result = {
        "trial": trial,
        "seconds": elapsed,
        "tv": tv["total"],
        "raw_tv": raw_tv["total"],
        "time_tv": tv["time"],
        "frequency_tv": tv["frequency"],
        "scale": scale,
        "valid_gain_fraction": float(np.mean(valid)),
        "losses": losses,
        "invalid_predictions": invalid_predictions,
        "added_count": int(np.sum(added)),
        "added_fraction": float(np.sum(added) / np.sum(state["train"])),
    }
    write_json(directory / "metrics.json", result)
    print(
        f"{trial}: TV={result['tv']:.6g}, extra={result['added_fraction']:.3%}, validation={losses['validation']}",
        flush=True,
    )
    return result, tv, residuals, guidance


def train(
    run_dir,
    time_interval=2,
    freq_interval=32,
    iterations=50,
    max_fraction=0.02,
    flag_penalty=2.0,
    validation_weight=0.25,
    validation_tolerance=0.01,
    rounds=1,
    thresholds=(8.0, 5.0, 3.0),
    tv_weights=(0.0, 1.0, 3.0),
    gauge="polar",
):
    """Train policy parameters on actual gain TV with fixed validation constraints.

    Test data never select a candidate. A no-change policy is always available.
    Per-round features depend only on train residuals and gains solved on train.
    """
    run_dir = Path(run_dir).resolve()
    state = load_state(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    if manifest.get("split_gain_intervals") != [time_interval, freq_interval]:
        raise ValueError(
            "solve grid must match the grid used to reserve training support"
        )
    if (
        min(time_interval, freq_interval, iterations, rounds) < 1
        or not 0 <= max_fraction < 1
        or min(flag_penalty, validation_weight, validation_tolerance) < 0
        or not np.isfinite(
            [flag_penalty, validation_weight, validation_tolerance]
        ).all()
    ):
        raise ValueError(
            "positive integer solve settings and a fraction below one required"
        )
    if gauge == "polar" and not manifest["fixture"]:
        matrices = state["model"].reshape(*state["model"].shape[:2], 2, 2)
        if not (
            np.allclose(matrices[..., 0, 1], 0)
            and np.allclose(matrices[..., 1, 0], 0)
            and np.allclose(matrices[..., 0, 0], matrices[..., 1, 1])
        ):
            raise ValueError(
                "polar gauge requires an explicitly unpolarized scalar model; use raw for polarized data"
            )
    configuration = {
        "time_interval": time_interval,
        "freq_interval": freq_interval,
        "iterations": iterations,
        "max_fraction": max_fraction,
        "flag_penalty": flag_penalty,
        "validation_weight": validation_weight,
        "validation_tolerance": validation_tolerance,
        "rounds": rounds,
        "thresholds": list(thresholds),
        "tv_weights": list(tv_weights),
        "gauge": gauge,
        "objective": "fixed_support_TV/TV0 + flag_penalty*f + validation_weight*MSEval/MSEval0",
    }
    write_json(run_dir / "training-config.json", configuration)
    zero = np.zeros_like(state["train"])
    baseline, base_tv, residuals, guidance = solve(
        run_dir,
        state,
        manifest,
        zero,
        "baseline",
        time_interval,
        freq_interval,
        iterations,
        gauge=gauge,
    )
    if (
        baseline["losses"]["validation"] is None
        or fixed_support_tv(base_tv["edges"], base_tv["edges"]) is None
    ):
        raise ValueError(
            "baseline has insufficient gain support; adjust window/intervals before training"
        )
    denominator = max(baseline["tv"], 1e-30)
    validation0 = max(baseline["losses"]["validation"], 1e-30)
    best_objective = baseline["tv"] / denominator + validation_weight
    best_mask, best, best_policy = zero, baseline, None
    baseline["fixed_support_tv"] = baseline["tv"]
    trials = [
        {**baseline, "objective": best_objective, "accepted": True, "policy": None}
    ]
    seen = {sha256(zero.tobytes()).hexdigest()}
    unguided_best = trials[0]
    for round_index in range(rounds):
        outliers = residual_features(
            residuals * np.sqrt(state["weights"]),
            state["train"],
            state["antenna1"],
            state["antenna2"],
        )
        round_residuals, round_guidance = residuals, guidance
        for tv_weight in tv_weights:
            for threshold in thresholds:
                added = policy_mask(
                    outliers,
                    round_guidance,
                    state["train"],
                    threshold=threshold,
                    tv_weight=tv_weight,
                    max_fraction=max_fraction,
                )
                policy = {
                    "threshold": float(threshold),
                    "tv_weight": float(tv_weight),
                    "round": round_index,
                }
                fingerprint = sha256(added.tobytes()).hexdigest()
                if fingerprint in seen:
                    trials.append({"policy": policy, "duplicate_mask": fingerprint})
                    continue
                seen.add(fingerprint)
                trial = f"r{round_index}-w{tv_weight:g}-z{threshold:g}"
                try:
                    metrics, tv, candidate_residuals, candidate_guidance = solve(
                        run_dir,
                        state,
                        manifest,
                        added,
                        trial,
                        time_interval,
                        freq_interval,
                        iterations,
                        scale=baseline["scale"],
                        gauge=gauge,
                    )
                    tv_score = fixed_support_tv(tv["edges"], base_tv["edges"])
                    metrics["fixed_support_tv"] = tv_score
                    val = metrics["losses"]["validation"]
                    admissible = (
                        tv_score is not None
                        and val is not None
                        and val <= (1 + validation_tolerance) * validation0
                    )
                    objective = (
                        (
                            tv_score / denominator
                            + flag_penalty * metrics["added_fraction"]
                            + validation_weight * val / validation0
                        )
                        if admissible
                        else None
                    )
                    record = {
                        **metrics,
                        "policy": policy,
                        "fixed_support_tv": tv_score,
                        "objective": objective,
                        "accepted": bool(admissible and objective < best_objective),
                        "rejection": None
                        if admissible
                        else "gain support loss or validation degradation",
                    }
                    if (
                        tv_weight == 0
                        and admissible
                        and objective < unguided_best["objective"]
                    ):
                        unguided_best = record
                    if record["accepted"]:
                        best_objective, best_mask, best, best_policy = (
                            objective,
                            added,
                            metrics,
                            policy,
                        )
                        residuals, guidance = candidate_residuals, candidate_guidance
                except RuntimeError as error:
                    record = {
                        "trial": trial,
                        "policy": policy,
                        "accepted": False,
                        "error": str(error),
                    }
                trials.append(record)
                write_json(run_dir / "trials" / trial / "selection.json", record)
        # If no policy was accepted, retain the baseline feature maps for next round.
        if best_policy is None:
            residuals, guidance = round_residuals, round_guidance
        write_json(
            run_dir / f"checkpoint-round-{round_index}.json",
            {
                "best_trial": best["trial"],
                "best_policy": best_policy,
                "best_objective": best_objective,
                "trials": trials,
            },
        )
        np.savez_compressed(
            run_dir / f"checkpoint-round-{round_index}.npz", added=best_mask
        )
    # Restore original outside-window, autocorrelation and holdout flags exactly;
    # only the selected additional training-sample flags become final changes.
    set_flags(run_dir, state, best_mask, "final", holdout=False)
    shutil.copytree(run_dir / "work.ms", run_dir / "flagged.ms")
    snapshot_flags(
        run_dir / "backups/final-additions.npz",
        best_mask,
        np.zeros(len(best_mask), bool),
    )
    unchanged = (
        tree_digest(run_dir / "original.ms")
        == manifest["source_digest"]
        == tree_digest(Path(manifest["source"]))
    )
    if not unchanged:
        raise RuntimeError("original MS or its source copy changed")
    result = {
        "baseline": baseline,
        "selected": best,
        "selected_policy": best_policy,
        "selected_objective": best_objective,
        "unguided_best": unguided_best,
        "trials": trials,
        "original_unchanged": unchanged,
        "test_mse_ratio": best["losses"]["test"] / baseline["losses"]["test"]
        if best["losses"]["test"] is not None and baseline["losses"]["test"]
        else None,
        "limitations": "Small pointing scan; approximate unpolarized point sky, unitary gauge convention, no image/flux validation. Selection uses validation, never test. Gains were solved with holdouts excluded; final MS only restores original holdout flags.",
    }
    write_json(run_dir / "result.json", result)
    write_json(
        run_dir / "model.json",
        {
            "kind": "robust residual threshold conditioned on gain TV",
            "policy": best_policy,
            "no_change": best_policy is None,
            "training": configuration,
            "selected_trial": best["trial"],
            "training_manifest": manifest,
            "transfer_validated": False,
        },
    )


def report(run_dir):
    """Export standalone diagnostic maps, original/final flag audit and summary."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from casacore.tables import table

    run_dir = Path(run_dir)
    state, result = (
        load_state(run_dir),
        json.loads((run_dir / "result.json").read_text()),
    )
    with table(
        str(run_dir / "flagged.ms"), readonly=True, ack=False, lockoptions="autonoread"
    ) as final:
        flags, rows = final.getcol("FLAG"), final.getcol("FLAG_ROW")
    assert_preserved(state["original_flags"], state["original_rows"], flags, rows)
    panels = []
    for trial in ("baseline", result["selected"]["trial"]):
        with np.load(run_dir / "trials" / trial / "diagnostics.npz") as ds:
            panels.append(
                (
                    trial,
                    np.where(ds["tv_valid"], ds["tv_map"], np.nan),
                    ds["gain_times"],
                    ds["gain_frequencies"],
                )
            )
    fig, axes = plt.subplots(
        len(state["names"]),
        2,
        figsize=(12, 3 * len(state["names"])),
        squeeze=False,
        layout="constrained",
        sharex=True,
        sharey=True,
    )
    vmax = max(float(np.nanquantile(x[1], 0.99)) for x in panels)
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("#dddddd")
    for column, (trial, maps, times, freqs) in enumerate(panels):
        for antenna, name in enumerate(state["names"]):
            image = axes[antenna, column].imshow(
                maps[:, :, antenna],
                origin="lower",
                aspect="auto",
                vmin=0,
                vmax=max(vmax, 1e-10),
                cmap=cmap,
                extent=[freqs[0] / 1e6, freqs[-1] / 1e6, 0, times[-1] - times[0]],
            )
            axes[antenna, column].set(
                title=f"{name} — {trial}",
                ylabel="Time (s)",
                xlim=(state["frequencies"][state["window"]][[0, -1]] / 1e6),
            )
    fig.supxlabel("Frequency (MHz); grey bins have no valid gain support")
    fig.colorbar(
        image,
        ax=axes.ravel().tolist(),
        label="Normalized full-Jones TV guidance",
        shrink=0.7,
    )
    fig.savefig(run_dir / "tv-maps.png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    with np.load(run_dir / "trials/baseline/diagnostics.npz") as ds:
        gains, valid, freqs = (
            ds["gauge_gains"],
            ds["tv_valid"],
            ds["gain_frequencies"] / 1e6,
        )
        fig, axes = plt.subplots(
            len(state["names"]), 2, figsize=(12, 10), sharex=True, layout="constrained"
        )
        for antenna, name in enumerate(state["names"]):
            for component, label in ((0, "XX"), (3, "YY")):
                amplitudes = np.abs(
                    gains[:, :, antenna].reshape(*gains.shape[:2], 4)[..., component]
                )
                # Draw each integration bin; invalid gains are grey/missing, not unity.
                for time_index in range(len(amplitudes)):
                    axes[antenna, 0].plot(
                        freqs,
                        np.where(
                            valid[time_index, :, antenna],
                            amplitudes[time_index],
                            np.nan,
                        ),
                        alpha=0.5,
                        color="C0" if component == 0 else "C1",
                        label=label if time_index == 0 else None,
                    )
            leakage = np.sqrt(
                np.abs(gains[:, :, antenna, 0, 1]) ** 2
                + np.abs(gains[:, :, antenna, 1, 0]) ** 2
            )
            diagonal = np.sqrt(
                np.abs(gains[:, :, antenna, 0, 0]) ** 2
                + np.abs(gains[:, :, antenna, 1, 1]) ** 2
            )
            for time_index in range(len(leakage)):
                axes[antenna, 1].plot(
                    freqs,
                    np.where(
                        valid[time_index, :, antenna],
                        leakage[time_index] / np.maximum(diagonal[time_index], 1e-30),
                        np.nan,
                    ),
                    alpha=0.5,
                )
            axes[antenna, 0].set(
                title=f"{name}: diagonal amplitude", ylabel="Gain amplitude"
            )
            axes[antenna, 1].set(
                title=f"{name}: off-diagonal / diagonal norm", ylabel="Ratio"
            )
            axes[antenna, 0].legend()
            for ax in axes[antenna]:
                ax.set_xlim(state["frequencies"][state["window"]][[0, -1]] / 1e6)
        fig.supxlabel("Frequency (MHz); polar gauge, one curve per solution time")
        fig.savefig(run_dir / "gain-spectra.png", dpi=140)
        plt.close(fig)
    original, _ = protected_flags(
        state["original_flags"], state["original_rows"], np.zeros_like(flags)
    )
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, title, cube in zip(
        axes,
        ("Original protected flags", "Final flags", "Additional flags"),
        (original, flags, flags & ~original),
    ):
        time_indices = np.unique(state["times"], return_inverse=True)[1]
        maps = np.array(
            [
                np.mean(cube[time_indices == i], axis=(0, 2))
                for i in range(time_indices.max() + 1)
            ]
        )
        ax.imshow(maps, origin="lower", aspect="auto", vmin=0, vmax=1)
        ax.set(title=title, xlabel="Channel", ylabel="Integration")
    fig.tight_layout()
    fig.savefig(run_dir / "flag-maps.png", dpi=140)
    plt.close(fig)
    write_json(
        run_dir / "flag-audit.json",
        {
            "observatory_flags_preserved": True,
            "original_flagged_cells": int(np.sum(original)),
            "additional_flagged_cells": int(np.sum(flags & ~original)),
            "original_rows_preserved": bool(np.all(rows[state["original_rows"]])),
            "data_unchanged": tree_digest(run_dir / "original.ms")
            == tree_digest(
                Path(json.loads((run_dir / "manifest.json").read_text())["source"])
            ),
            "final_data_array_unchanged": bool(
                np.array_equal(
                    state["data"], table_data(run_dir / "flagged.ms"), equal_nan=True
                )
            ),
        },
    )
    summary = f"Selected: {result['selected']['trial']}\nOriginal data unchanged: {result['original_unchanged']}\nAdditional training fraction: {result['selected']['added_fraction']:.6%}\nGain TV: {result['baseline']['tv']:.8g} -> {result['selected']['tv']:.8g}\nTest MSE ratio: {result['test_mse_ratio']}\n\n{result['limitations']}\n"
    (run_dir / "summary.txt").write_text(summary)
    print(summary, flush=True)


def table_data(path):
    from casacore.tables import table

    with table(str(path), readonly=True, ack=False, lockoptions="autonoread") as ms:
        return ms.getcol("DATA")
