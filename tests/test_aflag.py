"""A-FLAG: AOFlagger 3.5 as a second SumThreshold oracle (research/a-flag-aoflagger.md).

The bridge-kernel tests run anywhere. The archive tests read the committed
`research/results/a-flag-aoflagger.json`; the recomputation test needs the
ignored run directories under `outputs/` and skips without them.
"""

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "research/results/a-flag-aoflagger.json"
sys.path.insert(0, str(ROOT / "tools/oracles/aoflagger"))
import st_bridge


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reference_sumthreshold(z, missing, lengths=st_bridge.AO_LENGTHS, sens=1.0 / 6.0):
    """Brute-force SumThreshold with missing samples removed (intended
    semantics): each window holds `length` non-missing samples; samples
    flagged by an earlier length are left out of the mean."""
    out = np.zeros(z.shape, bool)
    for col in range(z.shape[0]):
        idx = np.nonzero(~missing[col])[0]
        mask = np.zeros(z.shape[1], bool)
        for length, chi in zip(lengths, st_bridge.ao_mean_thresholds(lengths, sens)):
            if length > z.shape[1]:
                continue
            new = mask.copy()
            for p in range(idx.size - length + 1):
                win = idx[p : p + length]
                vals = z[col, win][~mask[win]]
                if vals.size and abs(vals.astype(np.float64).mean()) > chi:
                    new[idx[p] : idx[p + length - 1] + 1] = True
            mask = new
        out[col] = mask
    return out


def test_ao_thresholds_are_rho_four_thirds():
    chi = st_bridge.ao_mean_thresholds()
    assert chi[0] == pytest.approx(1.0, rel=1e-6)
    for length, value in zip(st_bridge.AO_LENGTHS, chi):
        assert value == pytest.approx((4.0 / 3.0) ** -math.log2(length), rel=1e-6)


def test_horizontal_without_quirk_is_reference():
    rng = np.random.default_rng(1)
    z = rng.normal(0, 0.3, (12, 40)).astype(np.float32)
    z[rng.random(z.shape) < 0.05] += 1.3
    missing = rng.random(z.shape) < 0.3
    got = st_bridge.aoflagger_columns(z, missing, vertical=False, quirk=False)
    assert np.array_equal(got, reference_sumthreshold(z, missing))


def test_vertical_equals_horizontal_without_missing():
    rng = np.random.default_rng(2)
    z = rng.normal(0, 0.3, (10, 50)).astype(np.float32)
    z[rng.random(z.shape) < 0.05] -= 1.4
    none = np.zeros(z.shape, bool)
    vertical = st_bridge.aoflagger_columns(z, none, vertical=True)
    horizontal = st_bridge.aoflagger_columns(z, none, vertical=False)
    assert np.array_equal(vertical, horizontal)


def test_xright_quirk_keeps_a_missing_sample_in_the_sum():
    # Length 2: the sample after the first non-missing one is missing and
    # large; AOFlagger 3.5.0 adds it once and never subtracts it, so the
    # moderate samples after it are flagged too.
    z = np.array([[0.1, 5.0, 0.4, 0.4, 0.4, 0.4]], np.float32)
    missing = np.array([[False, True, False, False, False, False]])
    intended = st_bridge.aoflagger_columns(z, missing, vertical=False, quirk=False)
    quirk = st_bridge.aoflagger_columns(z, missing, vertical=False, quirk=True)
    assert not intended[0, 2:].any()
    assert quirk[0, 2:].all()


def test_tricolour_columns_clamps_and_smears():
    values = np.zeros((1, 20), np.float32)
    values[0, 10] = 20.0
    valid = np.ones(values.shape, bool)
    flags = st_bridge.tricolour_columns(
        values, valid, np.ones(1, np.float32), [1, 2, 4], 1.3
    )
    assert flags[0, 10] and flags[0].sum() >= 1
    assert not flags[0, :5].any()


def test_smear_and_cut():
    det = np.zeros((14, 100), bool)
    det[5, 50] = True
    out = st_bridge.smear_and_cut(det, 3, 3, 0.6, 0.8)
    assert out[4:7, 49:52].all() and out.sum() == 9
    det[:, 10] = True  # one channel fully flagged in time stays a column
    out = st_bridge.smear_and_cut(det, 3, 3, 0.6, 0.8)
    assert out[:, 9:12].all()


def test_lua_table():
    oracle = _load("oracle_aoflagger", ROOT / "examples/oracle_aoflagger.py")
    text = oracle.lua_table(
        {"ntime": 14, "outlier_nsigma": 10, "spike_width_time": 12.5, "vertical": False}
    )
    assert (
        text
        == "return {ntime = 14, outlier_nsigma = 10, spike_width_time = 12.5, vertical = false}\n"
    )


def _archive():
    if not RESULTS.exists():
        pytest.skip("archive not present")
    return json.loads(RESULTS.read_text())


def test_archive_gates_and_bridge_validation():
    r = _archive()
    assert r["tricolour_dump"]["gate_pass"] is True
    assert all(r["port_equals_oracle"].values())
    for label, steps in r["kernel"].items():
        for step, passes in steps.items():
            for pas, m in passes.items():
                assert m["validation_numpy_tricolour_vs_dump"]["all"] == 0, (
                    label,
                    step,
                    pas,
                )
                assert m["validation_K2_vs_H1"]["all"] == 0, (label, step, pas)
                assert m["validation_K3_vs_H2"]["all"] == 0, (label, step, pas)
                if pas != "time":
                    assert m["validation_K2v_vs_H1v"]["all"] == 0
                    assert m["validation_K3v_vs_H2v"]["all"] == 0
    for label, chain in r["chain"].items():
        assert chain["port"]["vs_after_native"]["equal"], label


def test_archive_ladder_composes():
    """Each pass's Tricolour-vs-AOFlagger difference is bounded by the rungs."""
    r = _archive()
    for steps in r["kernel"].values():
        for passes in steps.values():
            for m in passes.values():
                rungs = (
                    "rung_normalisation_K0_to_K0n",
                    "rung_lengths_rho_K0n_to_K1",
                    "rung_clamp_to_exclude_K1_to_K2",
                    "rung_input_as_missing_K2_to_K3i",
                    "rung_xright_quirk_K3i_to_K3",
                )
                assert m["tricolour_vs_H2"]["all"] <= sum(m[k]["all"] for k in rungs)


def test_recompute_one_stage_from_outputs():
    r = _archive()
    outputs = ROOT / "outputs"
    label, step = "strategy-01-holdout_masked", "06-sum_threshold"
    oracle_dir = outputs / "core-d-oracle-20261029-01/run" / label
    tuned = outputs / "aflag-20261030-03-stages/tuned" / f"{label}.npz"
    if not (oracle_dir.exists() and tuned.exists()):
        pytest.skip("A-FLAG outputs not present")
    compare = _load("compare_aoflagger", ROOT / "examples/compare_aoflagger.py")
    stages = np.load(oracle_dir / "stages.npz")
    names = list(stages.files)
    k = names.index(step)
    ubl = np.load(oracle_dir / "arrays.npz")["ubl"]
    before = np.asarray(stages[names[k - 1]][:, 0], bool)
    autos = np.broadcast_to((ubl[:, 1] == ubl[:, 2])[:, None, None], before.shape)
    got = np.asarray(np.load(tuned)[step][:, 0], bool)
    m, _ = compare.stage_measures(
        got, np.asarray(stages[step][:, 0], bool), before, autos
    )
    assert m["all"] == r["stages"][label][step]["tuned_vs_tricolour"]["all"]
