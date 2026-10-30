"""Integration tests of the scientific controls and Python/Rust boundary.

The pointing toy runs inside the extension (task P7,
research/p7-architecture.md); its output must stay byte-identical to the
`rang-toy` binary's stdout archived at 5965d37 (`tests/data/toy-golden.json`).
"""

import hashlib
import json
import platform
import sys
from pathlib import Path

import pytest
from rangtoy import run_experiment, toy_output

GOLDEN = json.loads(
    (Path(__file__).resolve().parent / "data" / "toy-golden.json").read_text()
)


def rows(experiment):
    return {row["method"]: row for row in experiment["results"]}


@pytest.mark.skipif(
    sys.platform != "linux" or platform.machine().lower() not in ("x86_64", "amd64"),
    reason="archived on Linux x86_64; another libm changes printed digits (P7)",
)
@pytest.mark.parametrize("args", sorted(GOLDEN))
def test_output_identical_to_the_binary(args):
    data = toy_output(*args.split()).encode()
    assert len(data) == GOLDEN[args]["bytes"]
    assert hashlib.sha256(data).hexdigest() == GOLDEN[args]["sha256"]


def test_no_error_control_does_not_invent_pointing():
    ex = run_experiment(noise=0, pointing=0, target_flux=0)
    for row in ex["results"]:
        assert abs(row["flux_jy"]) < 1e-10
        assert row["pointing_rmse_arcmin"] < 1e-9
        assert row["heldout_rms_jy"] < 1e-10


def test_recovery_and_no_claim_of_extra_benefit():
    ex = run_experiment()
    r = rows(ex)
    assert ex["visibility_count"] == 2688
    assert ex["max_abs_w"] > 1000
    # Known pointing is an essential independent check on sky discretization.
    assert abs(r["known_pointing"]["flux_jy"] - 0.02) < 0.002
    assert abs(r["joint_sky"]["flux_jy"] - 0.02) < 0.002
    assert r["pointing_only"]["template_transfer"] < 0.9
    assert r["joint_sky"]["template_transfer"] > 0.98
    assert r["protected_modes"]["local_loss"] <= ex["budget"]
    assert r["protected_modes"]["flux_jy"] == pytest.approx(
        r["joint_sky"]["flux_jy"], abs=1e-8
    )
    assert r["joint_sky"]["heldout_rms_jy"] < r["fixed_beam"]["heldout_rms_jy"]
    assert Path(ex["command"][0]).name.startswith("_core")


def test_reproducibility_and_seed_changes():
    a = run_experiment(seed=3, noise=0, pointing=0, target_flux=0)
    b = run_experiment(seed=3, noise=0, pointing=0, target_flux=0)
    assert a["results"] == b["results"]
    c = run_experiment(seed=4)
    assert a["results"] != c["results"]


def test_shared_beam_fit_resolves_width_mismatch():
    r = rows(run_experiment(beam_error=0.02))
    assert r["joint_sky"]["flux_jy"] > 0.03
    assert r["joint_sky"]["template_transfer"] > 0.99
    assert abs(r["joint_beam"]["flux_jy"] - 0.02) < 0.002
    assert abs(r["joint_beam"]["fitted_beam_width_error"] - 0.02) < 0.002
    assert len(r["joint_beam"]["pointing_arcmin"]) == 16
    assert r["joint_beam"]["retained_modes"] == 17
    assert r["joint_beam"]["heldout_rms_jy"] < r["joint_sky"]["heldout_rms_jy"]


@pytest.mark.parametrize(
    "option,value",
    [("--noise", "nan"), ("--budget", "-1"), ("--seed", "-1"), ("--pointing", "inf")],
)
def test_invalid_options_are_rejected(option, value):
    with pytest.raises(RuntimeError, match="rang-toy:"):
        toy_output(option, value)
