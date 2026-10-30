"""Task L5-C (research/l5c-casa-gaincal.md): the reader's `nearest` time
interpolation, and the committed archive's internal consistency (recomputed
from the run directory when it exists)."""

import json
from pathlib import Path

import numpy as np
import pytest
from rang.formats import caltable

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "research/results/l5c-casa-gaincal.json"
DELTA = 1e-4


def test_nearest_picks_the_closest_slot_with_its_flag():
    times = np.array([10.0, 20.0, 30.0])
    vals = np.arange(3, dtype=np.float32).reshape(3, 1)
    flags = np.array([[False], [True], [False]])
    out, fl = caltable._interpolate(
        times, vals, flags, [9.0, 14.9, 15.0, 16.0, 26.0, 31.0], "nearest"
    )
    assert out[:, 0].tolist() == [0, 0, 0, 1, 2, 2]  # 15.0 is a tie: the earlier
    assert fl[:, 0].tolist() == [False, False, False, True, False, False]


def test_linear_is_the_default_and_unknown_modes_fail():
    times = np.array([10.0, 20.0])
    vals = np.array([[0.0], [1.0]], np.float32)
    flags = np.zeros((2, 1), bool)
    a = caltable._interpolate(times, vals, flags, [12.5])
    b = caltable._interpolate(times, vals, flags, [12.5], "linear")
    assert np.array_equal(a[0], b[0]) and abs(a[0][0, 0] - 0.25) < 1e-6
    with pytest.raises(ValueError):
        caltable._interpolate(times, vals, flags, [12.5], "cubic")


def test_correct_with_nearest_divides_by_the_nearest_solution():
    subtables = {
        "SPECTRAL_WINDOW": {"CHAN_FREQ": [np.array([1.4e9])]},
    }
    g = np.zeros((2, 2, 1, 2), complex)
    g[0] = [[[2.0, 3.0]], [[1.0, 1.0]]]
    g[1] = [[[5.0, 7.0]], [[1.0, 1.0]]]
    table = caltable.from_gains("G", [100.0, 200.0], [0, 1], g, subtables=subtables)
    data = np.ones((2, 1, 4), complex)
    out, flag = caltable.correct(
        data,
        np.zeros(data.shape, bool),
        np.array([120.0, 190.0]),
        np.array([0, 0]),
        np.array([1, 1]),
        np.array([1.4e9]),
        [table],
        time_interp="nearest",
    )
    assert not flag.any()
    # Row 0 takes the first solution, row 1 the second; antenna 1 is unity.
    assert np.allclose(out[0, 0], [1 / 2, 1 / 2, 1 / 3, 1 / 3])
    assert np.allclose(out[1, 0], [1 / 5, 1 / 5, 1 / 7, 1 / 7])


def _archive():
    if not ARCHIVE.exists():
        pytest.skip("no L5-C archive")
    return json.loads(ARCHIVE.read_text())


def test_archive_gates_and_margin_verdicts():
    sets = _archive()["sets"]
    assert {"fixture", "slice"} <= set(sets)
    for name, report in sets.items():
        assert all(report["gates"].values()), (name, report["gates"])
        arms = report["heldout"]["arms"]
        for ref, verdict in report["margin"]["casa_G_vs"].items():
            r = arms["CASA_G"]["test_parallel"] / arms[ref]["test_parallel"] - 1
            assert abs(r - verdict["relative"]) < 1e-12
            if verdict["in_sample_reference"]:
                assert verdict["within_margin"] is None
            else:
                assert verdict["within_margin"] == (abs(r) <= DELTA)
        route = report["routes"]["G"]["reader_vs_casa"]
        assert route["within_dfio_bound"] and route["flag_differences"] == 0


def test_archive_tail_verdict_follows_the_frozen_rule():
    for report in _archive()["sets"].values():
        conv = report["convergence"]
        p = conv["thresholds"]["0.0001"]
        if p["core_capped"] == 0:
            expected = "undecidable"
        elif (
            p["fraction_of_core_capped_casa_unsettled"] >= 0.5
            and (p["enrichment"] or 0) >= 5
        ):
            expected = "reproduced"
        elif p["fraction_of_core_capped_casa_unsettled"] < 0.1:
            expected = "not reproduced"
        else:
            expected = "partly"
        assert conv["verdict"] == expected


def test_archive_thresholds_recomputed_from_the_run():
    for report in _archive()["sets"].values():
        path = ROOT / report["run"] / "per-interval.npz"
        if not path.exists():
            pytest.skip("L5-C run directory not present")
        z = np.load(path)
        core, casa = z["core_D_vs_R"], z["casa_first_vs_restarted"]
        both = np.isfinite(core) & np.isfinite(casa)
        for key, entry in report["convergence"]["thresholds"].items():
            thr = float(key)
            assert entry["core_capped"] == int((both & (core >= thr)).sum())
            assert entry["casa_unsettled"] == int((both & (casa >= thr)).sum())
