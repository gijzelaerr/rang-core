"""Synthetic controls and strict TRAIN/domain/support guards, not RFI proof."""

import json

import numpy as np
import pytest
from rangtoy import flagging_uncertainty as uncertainty


def smooth_gains():
    t, f = np.linspace(0, 112, 4), np.linspace(1070e6, 1497.791015625e6, 32)
    phase = (
        2
        * np.pi
        * (f - f.mean())[None, :, None]
        * np.array([0, 3, 6, 9])[None, None]
        * 1e-9
    )
    amplitude = np.exp(
        ((t - t.mean()) / np.ptp(t))[:, None, None]
        * np.array([0, 0.04, -0.04, 0.08])[None, None]
    )
    diagonal = amplitude * np.exp(1j * phase)
    gains = np.zeros((4, 32, 4, 2, 2), complex)
    gains[..., 0, 0], gains[..., 1, 1] = diagonal, diagonal
    return gains, np.ones((4, 32, 4), bool), t, f


def test_smooth_physical_delay_can_have_high_raw_tv_but_zero_trend_residual():
    evidence = uncertainty.gain_evidence(*smooth_gains())
    assert evidence["tv"] > 0.3
    assert evidence["detrended_tv"] < 1e-12
    assert evidence["maps"]["curvature_tv"].max() < 1e-12
    assert evidence["full_support"]


def test_common_right_unitary_gauge_cannot_create_excess_tv():
    gains, valid, times, frequencies = smooth_gains()
    rng = np.random.default_rng(8)
    rotation = np.linalg.qr(rng.normal(size=(2, 2)) + 1j * rng.normal(size=(2, 2)))[0]
    first = uncertainty.gain_evidence(gains, valid, times, frequencies)
    other = uncertainty.gain_evidence(gains @ rotation, valid, times, frequencies)
    assert first["tv"] == pytest.approx(other["tv"], abs=1e-13)
    assert other["detrended_tv"] < 1e-12


@pytest.mark.parametrize("failure", ["missing", "singular", "polarized", "gap"])
def test_incomplete_support_and_unsafe_gauge_are_refused(failure):
    gains, valid, times, frequencies = smooth_gains()
    keywords = {}
    if failure == "missing":
        valid[1, 2, 1] = False
    elif failure == "singular":
        gains[1, 2, 0] = 0
    elif failure == "polarized":
        keywords["unpolarized"] = False
    else:
        times[-1] += 1000
    with pytest.raises(ValueError):
        uncertainty.gain_evidence(gains, valid, times, frequencies, **keywords)


def calibration_fixture():
    train = np.array([[True, False, True], [True, False, True]])
    values = np.array([[0.1, np.nan, 0.2], [0.3, np.inf, 0.4]])
    control = {
        "split": "train",
        "stress": "none",
        "grid_key": "g",
        "trend_key": "smooth",
        "full_support": True,
        "train": train,
        "maps": {kind: values.copy() for kind in uncertainty.KINDS},
    }
    return train, values, control


def test_calibration_and_excess_ignore_all_heldout_values():
    train, values, control = calibration_fixture()
    calibration = uncertainty.calibrate_guidance(
        [control], grid_key="g", trend_key="smooth"
    )
    altered = {
        **control,
        "maps": {kind: v.copy() for kind, v in control["maps"].items()},
    }
    for v in altered["maps"].values():
        v[~train] = -1e100
    assert (
        uncertainty.calibrate_guidance([altered], grid_key="g", trend_key="smooth")
        == calibration
    )
    excess, audit = uncertainty.excess_guidance(
        {"train": train},
        values * 10,
        calibration,
        grid_key="g",
        trend_key="smooth",
        curvature=values * 10,
    )
    assert excess[train].max() > 0 and not excess[~train].any()
    assert audit["primary_full2x2_TV_objective_unchanged"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("split", "test"),
        ("stress", "jump"),
        ("grid_key", "wrong"),
        ("trend_key", "rapid"),
        ("full_support", False),
    ],
)
def test_calibration_rejects_test_stress_mixed_trends_and_missing_support(key, value):
    _, _, control = calibration_fixture()
    control[key] = value
    with pytest.raises(ValueError, match="TRAIN-only"):
        uncertainty.calibrate_guidance([control], grid_key="g", trend_key="smooth")


def test_excess_refuses_unknown_domain_and_nonfinite_train_evidence():
    train, values, control = calibration_fixture()
    calibration = uncertainty.calibrate_guidance(
        [control], grid_key="g", trend_key="smooth"
    )
    with pytest.raises(ValueError, match="refused"):
        uncertainty.excess_guidance(
            {"train": train},
            values,
            calibration,
            grid_key="unknown",
            trend_key="smooth",
        )
    values[train] = np.nan
    with pytest.raises(ValueError, match="finite"):
        uncertainty.excess_guidance(
            {"train": train}, values, calibration, grid_key="g", trend_key="smooth"
        )


def test_run_uses_exclusive_outputs_and_frozen_calibration_before_test(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(uncertainty, "GRIDS", ((4, 4),))
    monkeypatch.setattr(uncertainty, "TRENDS", ("flat",))
    monkeypatch.setattr(
        uncertainty, "SEEDS", {"train": (1, 2), "validation": (3,), "test": (4,)}
    )
    output = tmp_path / "control"
    uncertainty.run(output)
    result = json.loads((output / "result.json").read_text())
    assert result["count"] == 6
    assert len(list((output / "backups").glob("*.npz"))) == 6
    assert result["audit"]["thresholds_frozen_before_validation_test"]
    assert not list(output.glob("*.ms"))
    with pytest.raises(FileExistsError):
        uncertainty.run(output)
