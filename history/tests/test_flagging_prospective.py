"""Prospective split, native-response, receipt and bounded-execution controls.

These tests never launch QuartiCal, read an MS or use the network. Numerical
tests call the existing Rust Jones-response and TV kernels on synthetic data;
orchestration tests substitute explicit calibration hooks and tiny receipts.
"""

import json
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from rangtoy import flagging_prospective as prospective
from rangtoy.flagging_influence import _predict


def synthetic_problem():
    rng = np.random.default_rng(401)
    pairs = np.array([(p, q) for p in range(4) for q in range(p + 1, 4)])
    p, q = np.tile(pairs, (4, 1)).T
    shape = (len(p), 64)
    train = np.ones(shape, bool)
    train[:, :2] = False
    train[0, 2] = False
    validation = np.zeros(shape, bool)
    validation[:, 0] = True
    test = np.zeros(shape, bool)
    test[:, 1] = True
    flags = np.zeros((*shape, 4), bool)
    flags[0, 2, 1] = True
    state = {
        "data": np.zeros((*shape, 4), complex),
        "model": np.tile((2 * np.eye(2, dtype=complex)).reshape(4), (*shape, 1)),
        "weights": rng.uniform(0.8, 1.2, (*shape, 4)),
        "train": train,
        "validation": validation,
        "test": test,
        "original_flags": flags,
        "original_rows": np.zeros(shape[0], bool),
        "window": np.ones(shape[1], bool),
        "times": np.repeat(np.arange(4) * 8.0, 6),
        "frequencies": np.linspace(1.0e9, 1.5e9, shape[1]),
        "antenna1": p,
        "antenna2": q,
        "names": np.array([f"m{i:03}" for i in range(4)]),
    }
    gains = np.tile(np.eye(2, dtype=complex), (2, 2, 4, 1, 1))
    gains += 0.02 * (rng.normal(size=gains.shape) + 1j * rng.normal(size=gains.shape))
    baseline = {
        "gains": gains,
        "gain_valid": np.ones((2, 2, 4), bool),
        "gain_times": np.array([4.0, 20.0]),
        "gain_frequencies": np.array([1.125e9, 1.375e9]),
    }
    rows, channels, prediction = _predict(state, gains, np.ones(shape, bool))
    noise = 0.005 * (
        rng.normal(size=prediction.shape) + 1j * rng.normal(size=prediction.shape)
    )
    state["data"][rows, channels] = prediction + noise
    aligned, valid = prospective.polar_gauge(gains, baseline["gain_valid"])
    tv = prospective.gain_tv(
        aligned, valid, baseline["gain_times"], baseline["gain_frequencies"], scale=1.7
    )
    baseline["edges"] = tv["edges"]
    mse = (np.abs(noise) ** 2 * state["weights"][rows, channels]).mean(axis=-1)
    losses = {
        split: float(mse[state[split][rows, channels]].mean())
        for split in ("train", "validation", "test")
    }
    metrics = {
        "tv": prospective.fixed_support_tv(tv["edges"], tv["edges"]),
        "scale": 1.7,
        "added_fraction": 0.0,
        "losses": losses,
    }
    return state, baseline, metrics


def candidate(state, indices=None, slot=0):
    if indices is None:
        indices = np.flatnonzero(state["train"])[slot * 8 : (slot + 1) * 8]
    indices = np.asarray(indices)
    return {
        "indices": indices,
        "mask_id": sha256(indices.astype("<i8").tobytes()).hexdigest(),
        "sample_count": len(indices),
        "added_fraction": len(indices) / state["train"].sum(),
        "metadata": {"group": "baseline", "slot": slot},
        "residual_score": float(slot + 1),
        "tv_score": float(slot + 1),
    }


def test_native_response_freezes_fixed_scale_support_and_prediction_payload():
    state, baseline, metrics = synthetic_problem()
    result = prospective.forecast_family(state, baseline, metrics, [candidate(state)])
    record = result["records"][0]
    assert record["guard_pass"], record
    assert len(record["bin_audits"]) == 1
    assert record["bin_audits"][0]["diagnostics"]["full_rank"] == 28
    prediction = result["raw_predicted_gains"][0]
    aligned, valid = prospective.polar_gauge(prediction, baseline["gain_valid"])
    tv = prospective.gain_tv(
        aligned,
        valid,
        baseline["gain_times"],
        baseline["gain_frequencies"],
        scale=metrics["scale"],
    )
    assert record["predicted_fixed_tv"] == prospective.fixed_support_tv(
        tv["edges"], baseline["edges"]
    )
    np.testing.assert_array_equal(prediction[1], baseline["gains"][1])
    np.testing.assert_array_equal(prediction[0, 1], baseline["gains"][0, 1])


def test_train_response_cannot_read_poisoned_holdout_values():
    state, baseline, metrics = synthetic_problem()
    original = prospective.forecast_family(state, baseline, metrics, [candidate(state)])
    poisoned = deepcopy(state)
    holdout = poisoned["validation"] | poisoned["test"]
    poisoned["data"][holdout] = complex(np.nan, np.nan)
    poisoned["model"][holdout] = complex(np.nan, np.nan)
    poisoned["weights"][holdout] = np.nan
    result = prospective.forecast_family(
        poisoned, baseline, metrics, [candidate(poisoned)]
    )
    for key in ("full_h", "full_b", "raw_predicted_gains"):
        np.testing.assert_array_equal(result[key], original[key])
    for records in (original["records"], result["records"]):
        for record in records:
            record.pop("native_response_seconds")
    assert result["records"] == original["records"]


@pytest.mark.parametrize("dtype", [np.int64, np.uint64])
@pytest.mark.parametrize("order", ["descending", "duplicate"])
def test_unsorted_or_duplicate_masks_rejected_for_signed_and_unsigned(dtype, order):
    state, baseline, metrics = synthetic_problem()
    indices = np.flatnonzero(state["train"])[:8].astype(dtype)
    if order == "descending":
        indices = indices[::-1]
    else:
        indices[1] = indices[0]
    with pytest.raises(ValueError, match="sorted|unique"):
        prospective.forecast_family(
            state, baseline, metrics, [candidate(state, indices)]
        )


@pytest.mark.parametrize("fault", ["hash", "count", "fraction", "holdout", "budget"])
def test_mask_identity_training_membership_and_exact_flag_budget(fault):
    state, baseline, metrics = synthetic_problem()
    item = candidate(state)
    if fault == "hash":
        item["mask_id"] = "0" * 64
    elif fault == "count":
        item["sample_count"] += 1
    elif fault == "fraction":
        item["added_fraction"] = np.nextafter(item["added_fraction"], np.inf)
    elif fault == "holdout":
        item = candidate(state, np.r_[0, np.flatnonzero(state["train"])[:7]])
    else:
        item = candidate(
            state,
            np.flatnonzero(state["train"])[: int(0.02 * state["train"].sum()) + 1],
        )
    with pytest.raises(ValueError):
        prospective.forecast_family(state, baseline, metrics, [item])


def test_invalid_curvature_is_missing_prediction_not_zero(monkeypatch):
    state, baseline, metrics = synthetic_problem()
    monkeypatch.setattr(
        prospective,
        "anchored_response",
        lambda *_args: {"guard_pass": False, "delta": np.zeros((4, 2, 2))},
    )
    result = prospective.forecast_family(state, baseline, metrics, [candidate(state)])
    assert not result["records"][0]["guard_pass"]
    assert "predicted_fixed_tv" not in result["records"][0]
    assert np.isnan(result["raw_predicted_gains"]).all()


def test_validation_score_uses_full_guarded_objective_and_never_test_values():
    state, baseline, metrics = synthetic_problem()
    forecast = prospective.forecast_family(state, baseline, metrics, [candidate(state)])
    clean = prospective.score_forecasts(state, deepcopy(forecast))
    poison = deepcopy(state)
    poison["data"][poison["test"]] = complex(np.nan, np.nan)
    poison["model"][poison["test"]] = complex(np.nan, np.nan)
    poison["weights"][poison["test"]] = np.nan
    scored = prospective.score_forecasts(poison, deepcopy(forecast))
    assert scored["records"] == clean["records"]
    record = scored["records"][0]
    assert record["guard_pass"]
    fraction = record["candidate"]["added_fraction"]
    expected = (
        record["predicted_fixed_tv"] / metrics["tv"]
        + 2 * fraction
        + 0.25 * record["predicted_validation_MSE"] / metrics["losses"]["validation"]
    )
    assert record["predicted_objective"] == expected
    assert record["predicted_benefit"] == 1.25 - expected
    assert record["predicted_cost_removed_benefit"] == 1.25 - expected + 2 * fraction


def test_validation_degradation_abstains_instead_of_using_test(monkeypatch):
    state, baseline, metrics = synthetic_problem()
    forecast = prospective.forecast_family(state, baseline, metrics, [candidate(state)])
    poison = deepcopy(state)
    poison["data"][poison["validation"]] *= 10
    result = prospective.score_forecasts(poison, forecast)
    assert not result["records"][0]["guard_pass"]
    assert result["records"][0]["reason"] == "validation guard"
    assert "predicted_objective" not in result["records"][0]


@pytest.mark.parametrize(
    "used,needed,passes", [(99, 1, True), (99, 2, False), (0, -1, False)]
)
def test_campaign_exact_allocation_boundary(
    tmp_path, monkeypatch, used, needed, passes
):
    monkeypatch.setattr(prospective, "allocated_bytes", lambda _path: used)
    monkeypatch.setattr(
        prospective.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=2 * prospective.RESERVE_BYTES),
    )
    budget = prospective.CampaignBudget(tmp_path / "new", 100)
    if passes:
        assert budget.check(needed) == used
    else:
        with pytest.raises(ValueError, match="allocation"):
            budget.check(needed)


@pytest.mark.parametrize("offset,passes", [(0, True), (-1, False)])
def test_campaign_exact_eight_gib_reserve(tmp_path, monkeypatch, offset, passes):
    monkeypatch.setattr(prospective, "allocated_bytes", lambda _path: 0)
    monkeypatch.setattr(
        prospective.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=prospective.RESERVE_BYTES + 7 + offset),
    )
    budget = prospective.CampaignBudget(tmp_path / "new", 100)
    if passes:
        assert budget.check(7) == 0
    else:
        with pytest.raises(ValueError, match="reserve"):
            budget.check(7)


def orchestration(tmp_path, monkeypatch, count=24):
    """Replace only numerical/MS hooks; execute real checkpoint ordering."""
    state, baseline, metrics = synthetic_problem()
    source = tmp_path / "inputs"
    source.mkdir()
    (source / "cases").mkdir()
    cases = []
    case_ids = ("clean", "time-burst-seed107", "time-burst-seed109")
    manifest = {
        "split_gain_intervals": [2, 32],
        "scope": {"telescope": "MeerKAT", "band": "L"},
        "source": str(tmp_path / "original-source"),
        "source_digest": "unchanged",
        "original_copy_digest": "unchanged",
    }
    for case_id, seed in zip(case_ids, (None, 107, 109), strict=True):
        directory = source / "cases" / case_id
        directory.mkdir()
        (directory / "manifest.json").write_text(json.dumps(manifest))
        if seed is not None:
            (directory / "injection.npz").write_bytes(b"only a mocked truth read")
        cases.append(
            {
                "case_id": case_id,
                "seed": seed,
                "path": str(directory),
                "digest": "unchanged",
                "audit": {
                    "source_unchanged": True,
                    "copied_original_unchanged": True,
                    "weights_sigma_unchanged": True,
                    "boundary_validated": True,
                },
            }
        )
    (source / "cases.json").write_text(json.dumps({"cases": cases}))
    calls, output = [], tmp_path / "run"
    items = [candidate(state, slot=slot) for slot in range(count)]
    rankings = {
        mode: items[i * 6 : (i + 1) * 6]
        for i, mode in enumerate(("residual", "tv", "random", "detrended"))
    }
    native = tmp_path / "native-library"
    native.write_bytes(b"frozen mocked library, not a calibration invocation")
    monkeypatch.setattr(
        prospective, "_native_library", lambda: SimpleNamespace(_name=str(native))
    )
    monkeypatch.setattr(prospective, "tree_digest", lambda _path: "unchanged")
    monkeypatch.setattr(
        prospective.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=2 * prospective.RESERVE_BYTES),
    )

    def clone(_source, destination, budget, state_backup=False):
        assert not state_backup
        budget.mkdir(destination)
        budget.mkdir(destination / "backups")
        budget.json(destination / "manifest.json", manifest)

    monkeypatch.setattr(prospective, "_clone", clone)
    monkeypatch.setattr(prospective, "load_state", lambda _path: deepcopy(state))
    monkeypatch.setattr(prospective, "_all_weights", lambda _path: {})
    monkeypatch.setattr(prospective, "_weights_equal", lambda *_args: True)
    monkeypatch.setattr(
        prospective, "_export_audit", lambda *_args: {"protected": True}
    )
    monkeypatch.setattr(
        prospective.flagging_prepared,
        "validate_prepared_state",
        lambda *_args: {"validated": True},
    )

    def export_flags(directory, _state, added, label, holdout):
        assert label == "final-physics" and holdout is False
        assert (Path(directory) / "frozen-selection.json").exists()
        assert not np.any(added & ~_state["train"])
        assert not np.any(added & _state["original_flags"].any(axis=-1))
        assert not np.any(added & _state["original_rows"][:, None])

    monkeypatch.setattr(prospective, "set_flags", export_flags)
    monkeypatch.setattr(
        prospective,
        "make_shortlist",
        lambda *_args: (items, rankings, {"maximum_distinct": 24}),
    )

    def solve(directory, _state, _manifest, added, label, ti, fi, iterations, **kwargs):
        assert (ti, fi, iterations) == (2, 32, 50)
        assert not np.any(added & ~_state["train"])
        if label != "baseline":
            for case_id in case_ids:
                frozen = output / case_id / "frozen-forecasts.json"
                assert frozen.exists(), (
                    "action labels opened before all forecasts froze"
                )
                assert len(json.loads(frozen.read_text())["confirm_ids"]) <= 2
            assert kwargs["scale"] == metrics["scale"]
        calls.append((Path(directory).name, label))
        actual = deepcopy(metrics)
        if label != "baseline":
            slot = int(label.rsplit("-", 1)[1])
            actual["tv"] *= 0.8 + 0.001 * slot
            actual["added_fraction"] = added.sum() / _state["train"].sum()
            actual["losses"]["test"] = (-1) ** slot * 1e9
        return actual, {"edges": np.array([actual["tv"]])}, None, None

    monkeypatch.setattr(prospective, "solve", solve)
    monkeypatch.setattr(
        prospective,
        "fixed_support_tv",
        lambda edges, _support: float(np.asarray(edges).ravel()[0]),
    )

    def read_npz(path, _keys=None):
        path = Path(path)
        if path.name == "injection.npz":
            assert (output / path.parent.name / "frozen-selection.json").exists()
            calls.append((path.parent.name, "truth-after-selection"))
            return {"injected": state["train"].copy()}
        return baseline

    monkeypatch.setattr(prospective, "_npz", read_npz)

    def forecast(_state, _baseline, _metrics, candidates):
        assert sum(label == "baseline" for _, label in calls) >= 1
        return {
            "records": [
                {
                    "mask_id": x["mask_id"],
                    "candidate": prospective._compact(x),
                    "guard_pass": True,
                }
                for x in candidates
            ],
            "raw_predicted_gains": np.tile(
                baseline["gains"], (len(candidates), 1, 1, 1, 1, 1)
            ),
            "full_training_normals_seconds": 0.0,
        }

    def score(_state, forecast):
        for case_id in case_ids:
            directory = output / case_id
            frozen = directory / "frozen-train-responses.json"
            assert frozen.exists(), "validation opened before all TRAIN records froze"
            assert (directory / "gain-forecasts.npz").exists()
            assert (directory / "frozen-actions.npz").exists()
            assert (directory / "frozen-rankings.json").exists()
            assert all(
                "predicted_objective" not in row
                for row in json.loads(frozen.read_text())["records"]
            )
        for i, record in enumerate(forecast["records"]):
            record.update(
                predicted_objective=0.9 + i * 0.001, predicted_benefit=0.35 - i * 0.001
            )
        return forecast

    monkeypatch.setattr(prospective, "forecast_family", forecast)
    monkeypatch.setattr(prospective, "score_forecasts", score)
    return source, output, cases, calls


def test_all_forecasts_freeze_before_labels_and_exact_seventy_five_solve_ceiling(
    tmp_path, monkeypatch
):
    source, output, _cases, calls = orchestration(tmp_path, monkeypatch)
    result = prospective.run(output, source)
    assert result["actual_QC_solves"] == 75
    assert sum(label != "truth-after-selection" for _, label in calls) == 75
    assert sum(label == "baseline" for _, label in calls) == 3
    assert sum(label == "truth-after-selection" for _, label in calls) == 2
    for case in result["cases"]:
        assert len(case["confirmation_ids"]) == 2
        assert case["future_two_confirmation_QC_solves"] == 3
        assert (
            case["selected"]["physics_two_confirmation"]["mask_id"]
            == case["confirmation_ids"][0]
        )
        assert all(case["audit"].values())


@pytest.mark.parametrize("fault", ["case_id", "duplicate_path", "digest", "audit"])
def test_registry_rejects_relabelled_duplicated_or_stale_inputs_before_any_solve(
    tmp_path, monkeypatch, fault
):
    source, output, cases, calls = orchestration(tmp_path, monkeypatch)
    if fault == "case_id":
        cases[0]["case_id"] = "not-clean"
    elif fault == "duplicate_path":
        cases[1]["path"] = cases[0]["path"]
    elif fault == "digest":
        cases[2]["digest"] = "changed-after-construction"
    else:
        cases[1]["audit"]["boundary_validated"] = False
    (source / "cases.json").write_text(json.dumps({"cases": cases}))
    with pytest.raises(ValueError):
        prospective.run(output, source)
    assert not calls


def test_shortlist_above_twenty_four_rejected_before_action_solve(
    tmp_path, monkeypatch
):
    source, output, _cases, calls = orchestration(tmp_path, monkeypatch, count=25)
    with pytest.raises(ValueError, match="24|distinct|shortlist"):
        prospective.run(output, source)
    assert all(label == "baseline" for _, label in calls)


def test_duplicate_shortlist_identity_rejected_before_action_solve(
    tmp_path, monkeypatch
):
    source, output, _cases, calls = orchestration(tmp_path, monkeypatch)
    state, _baseline, _metrics = synthetic_problem()
    item = candidate(state)
    monkeypatch.setattr(
        prospective,
        "make_shortlist",
        lambda *_args: ([item, item], {"residual": [item]}, {}),
    )
    with pytest.raises(ValueError, match="distinct"):
        prospective.run(output, source)
    assert all(label == "baseline" for _, label in calls)


@pytest.mark.parametrize("fault", ["grid", "telescope", "band"])
def test_native_metadata_protocol_rejected_before_baseline(
    tmp_path, monkeypatch, fault
):
    source, output, _cases, calls = orchestration(tmp_path, monkeypatch)
    clone = prospective._clone

    def wrong_metadata(_source, destination, budget, state_backup=False):
        clone(_source, destination, budget, state_backup)
        path = destination / "manifest.json"
        manifest = json.loads(path.read_text())
        if fault == "grid":
            manifest["split_gain_intervals"] = [14, 128]
        elif fault == "telescope":
            manifest["scope"]["telescope"] = "different telescope"
        else:
            manifest["scope"]["band"] = "UHF"
        path.write_text(json.dumps(manifest))

    monkeypatch.setattr(prospective, "_clone", wrong_metadata)
    with pytest.raises(ValueError, match="MeerKAT|2x32"):
        prospective.run(output, source)
    assert not calls


def test_native_complex64_constructor_backs_up_and_changes_train_DATA_only(
    tmp_path, monkeypatch
):
    state, _baseline, _metrics = synthetic_problem()
    state["data"] = state["data"].astype(np.complex64)
    state["model"] = state["model"].astype(np.complex64)
    state["original_rows"][12] = True
    state["antenna2"][13] = state["antenna1"][13]
    state["window"][60] = False
    for split in ("train", "validation", "test"):
        state[split][12:14] = False
        state[split][:, 60] = False
    source = tmp_path / "pristine"
    source.mkdir()
    output = tmp_path / "constructed"
    native = tmp_path / "native-library"
    native.write_bytes(b"constructor only, no calibration execution")
    monkeypatch.setattr(
        prospective, "_native_library", lambda: SimpleNamespace(_name=str(native))
    )
    monkeypatch.setattr(prospective, "tree_digest", lambda _path: "unchanged")
    monkeypatch.setattr(
        prospective.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=2 * prospective.RESERVE_BYTES),
    )
    manifest = {"original_copy_digest": "unchanged"}
    stores, writes = {}, []
    original = {
        "data": state["data"].copy(),
        "flags": state["original_flags"].copy(),
        "rows": state["original_rows"].copy(),
        "weights": state["weights"].copy(),
        "times": state["times"].copy(),
        "antenna1": state["antenna1"].copy(),
        "antenna2": state["antenna2"].copy(),
    }
    observed = {
        "telescope": "MeerKAT",
        "frequencies": state["frequencies"],
        "names": state["names"],
        "correlations": np.array([[9, 10, 11, 12]]),
        "spw_rows": 1,
    }
    metadata = {"original": observed, "work": observed}
    columns = {
        "WEIGHT": np.ones((len(state["data"]), 4)),
        "WEIGHT_SPECTRUM": state["weights"].copy(),
        "SIGMA": np.ones((len(state["data"]), 4)),
        "SIGMA_SPECTRUM": 1 / np.sqrt(state["weights"]),
    }

    def clone(_source, destination, budget, state_backup=False):
        budget.mkdir(destination)
        budget.mkdir(destination / "backups")
        budget.mkdir(destination / "original.ms")
        budget.mkdir(destination / "work.ms")
        budget.json(destination / "manifest.json", manifest)
        budget.npz(
            destination / ("backups/source-state.npz" if state_backup else "state.npz"),
            **state,
        )
        stores[str(destination)] = deepcopy(original)
        stores[str(destination)]["model"] = state["model"].copy()

    monkeypatch.setattr(prospective, "_clone", clone)

    def boundary(directory, actual, _manifest):
        return prospective.flagging_prepared.validate_prepared_arrays(
            actual, original, stores[str(directory)], metadata
        )

    monkeypatch.setattr(
        prospective.flagging_prepared, "validate_prepared_state", boundary
    )
    monkeypatch.setattr(prospective, "_all_weights", lambda _path: deepcopy(columns))
    monkeypatch.setattr(
        prospective,
        "_weights_equal",
        lambda _path, before: all(
            np.array_equal(before[key], value) for key, value in columns.items()
        ),
    )

    class NativeTable:
        def __init__(self, path):
            self.directory = Path(path).parent
            self.work = stores[str(self.directory)]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def getcol(self, name):
            assert name == "DATA"
            return self.work["data"].copy()

        def putcol(self, name, values):
            assert name == "DATA" and values.dtype == np.complex64
            assert (
                self.directory / "backups/prospective-injection-data-before.npz"
            ).exists(), "exclusive full DATA backup must precede mutation"
            writes.append(self.directory.name)
            self.work["data"] = np.asarray(values, np.complex64).copy()

        def flush(self):
            pass

    tables = ModuleType("casacore.tables")
    tables.table = lambda path, **_kwargs: NativeTable(path)
    monkeypatch.setitem(sys.modules, "casacore", ModuleType("casacore"))
    monkeypatch.setitem(sys.modules, "casacore.tables", tables)
    result = prospective.prepare_inputs(output, source)
    assert writes == ["time-burst-seed107", "time-burst-seed109"]
    assert result["source_unchanged"] and len(result["cases"]) == 3
    for receipt in result["cases"]:
        directory = Path(receipt["path"])
        actual = prospective._npz(directory / "state.npz")
        assert actual["data"].dtype == np.complex64
        for key in state:
            if key != "data":
                np.testing.assert_array_equal(actual[key], state[key])
        difference = np.any(actual["data"] != state["data"], axis=-1)
        assert not np.any(difference & ~state["train"])
        np.testing.assert_array_equal(
            actual["data"][~state["train"]], state["data"][~state["train"]]
        )
        if receipt["seed"] is None:
            assert not difference.any()
        else:
            assert difference.any()
            before = prospective._npz(
                directory / "backups/prospective-injection-data-before.npz"
            )["DATA"]
            np.testing.assert_array_equal(before, state["data"])
            truth = prospective._npz(directory / "injection.npz")["injected"]
            np.testing.assert_array_equal(difference, truth)
        flags = prospective._npz(directory / "backups/original-flags.npz")
        np.testing.assert_array_equal(flags["FLAG"], state["original_flags"])
        np.testing.assert_array_equal(flags["FLAG_ROW"], state["original_rows"])


@pytest.mark.parametrize("iterations", [True, 49, 51, 50.0])
def test_frozen_iterations_reject_before_output_creation(tmp_path, iterations):
    with pytest.raises(ValueError, match="50"):
        prospective.run(tmp_path / "output", tmp_path / "input", iterations)
    assert not (tmp_path / "output").exists()
