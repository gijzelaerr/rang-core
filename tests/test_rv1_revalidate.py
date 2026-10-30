"""Task RV1 (research/rv1-revalidate.md): the committed archive is consistent
with itself and, where the ignored run directories exist, with them."""

import json
import re
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "research/results/rv1-revalidate.json"
GAIN_TOL = 1e-6
CONTROLS = (
    "strategy-00-operational",
    "strategy-00-holdout_masked",
    "strategy-01-operational",
    "strategy-01-holdout_masked",
)


@pytest.fixture(scope="module")
def archive():
    return json.loads(ARCHIVE.read_text())


def test_facts_name_exact_commits(archive):
    up = archive["upstream"]
    sha = re.compile(r"^[0-9a-f]{40}$")
    assert up["tricolour"]["release_0_5_0"] is None
    assert up["quartical"]["release_0_2_8"] is None
    assert up["tricolour"]["commit"] == "367ff54d700c134b2ea167b69c950d07873d36cb"
    assert up["tricolour"]["pr114_head"] == "2f476ad1a32e61d140f42cf243abb270eb9ed96c"
    assert up["quartical"]["commit"] == "d54c46b99dc059df678e8e2866883e3440073c2d"
    for tool in ("tricolour", "quartical"):
        assert sha.match(up[tool]["commit"])


def test_tricolour_verdict_matches_counts(archive):
    t = archive["tricolour"]
    assert set(t["controls"]) == set(CONTROLS)
    identical = all(
        not any(c["t1_vs_021_stage_differences"].values())
        and c["t1_vs_021_final_differences"] == 0
        and c["t1_vs_021_intensity_bit_equal"]
        and c["t2_final_vs_after_native"] == 0
        for c in t["controls"].values()
    )
    assert t["verdict"]["identical"] is identical is True
    assert t["verdict"]["t0_identical_to_021"] and t["verdict"]["t3_identical_to_t1"]
    assert t["core_vs_021_pass"] and t["core_vs_050_pass"]
    assert t["numba_get_flags_impl_signatures"] == {"0.5.0-dev": 1, "pr114_head": 2}
    # every baseline of the controls is shorter than the 550 m uvrange bound
    assert all(c["uvw_length_range_m"][1] < 550 for c in t["controls"].values())
    assert t["host_unchanged"]


def test_tricolour_frozen_failures_recorded(archive):
    f = archive["tricolour"]["frozen_runs"]
    assert not f["t1_stage_aliasing"]["verdict"]["t1_identical_to_021"]
    assert set(f["t2_frozen_returncodes"].values()) == {2}
    assert set(f["t2_posthoc1_returncodes"].values()) == {1}
    assert set(f["t2_posthoc2_returncodes"].values()) == {1}


def test_quartical_verdicts_follow_the_tolerances(archive):
    q = archive["quartical"]
    for name in ("fixture", "luno"):
        for key, c in q[name]["comparisons"].items():
            gauge_free = key.startswith("qc028-") or " vs qc028-" in key
            ok = c["flags_equal"] and c["max_abs_baseline_product_diff"] <= GAIN_TOL
            if not gauge_free:
                ok = ok and c["max_abs_gain_entry_diff"] <= GAIN_TOL
            if c["reference_iterations"] is not None:
                ok = ok and c["iterations"] == c["reference_iterations"]
            if name == "luno":
                ok = (
                    ok
                    and abs(c["converged_fraction"] - c["reference_converged_fraction"])
                    <= 1e-12
                )
            assert c["pass"] is ok, (name, key)
    v = q["verdict"]
    assert v["precondition_qc027_reproduces_archive"]
    assert v["qc028u_reproduces_0_2_7"] == {"fixture": False, "luno": False}
    assert v["core_T_reproduces_qc028u"] == {"fixture": True, "luno": True}
    assert v["qc028_referenced_products_equal_core_T"] == {
        "fixture": True,
        "luno": True,
    }
    assert all(all(c.values()) for c in archive["quartical_inputs"]["checks"].values())


def _run(archive, key):
    path = ROOT / archive["runs"][key]
    if not path.exists():
        pytest.skip(f"{path} is not on this machine (ignored outputs)")
    return path


def test_tricolour_outputs_reproduce_the_archive(archive):
    t1 = _run(archive, "t1")
    t2 = _run(archive, "t2")
    oracle = ROOT / "outputs/core-d-oracle-20261029-01/run"
    host = ROOT / "outputs/tv-caracal-wsl-20261029-01/native"
    if not oracle.exists() or not host.exists():
        pytest.skip("task D archive not on this machine")
    for label in CONTROLS:
        a, b = (
            np.load(t1 / label / "stages.npz"),
            np.load(oracle / label / "stages.npz"),
        )
        assert a.files == b.files
        for name in a.files:
            assert np.array_equal(a[name], b[name]), (label, name)
        after = np.load(host / label / "after-native.npz")["FLAG"]
        assert np.array_equal(np.load(t2 / label / "final.npz")["FLAG"], after)


def test_quartical_outputs_reproduce_the_archive(archive):
    run = _run(archive, "qc_run")
    for name in ("fixture", "luno"):
        a = np.load(run / name / "qc028u/gains.npy")
        b = np.load(run / name / "core-T/gains.npy")
        flagged = np.load(run / name / "qc028u/gain_flags.npy") != 0
        diff = np.abs(a - b)[~flagged].max()
        recorded = archive["quartical"][name]["comparisons"]["qc028u vs core-T"]
        assert diff == pytest.approx(recorded["max_abs_gain_entry_diff"], abs=1e-18)
        assert diff <= GAIN_TOL
