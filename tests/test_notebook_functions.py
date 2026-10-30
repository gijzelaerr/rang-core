"""Every `rangtoy.notebook` plot and table function on the fixture, headless.

Skips when the notebook extra (matplotlib, pandas) or the fixture archive
(`outputs/ska-pointing/outer_scans.zip`, or `RANG_FIXTURE`) is absent.
Images use a small geometry to keep the module fast.
"""

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("pandas")

from matplotlib.figure import Figure
from rangtoy.notebook import data, experiment, flags, gains, image, steer, survey

ROOT = Path(__file__).resolve().parents[1]
SMALL = {"width": 128, "height": 128, "scale_arcsec": 16.0, "w_layers": 8}


@pytest.fixture(scope="module")
def ds(tmp_path_factory):
    if data.find_fixture() is None:
        pytest.skip("fixture archive not present")
    return data.load_fixture(cache_dir=tmp_path_factory.mktemp("cache"))


@pytest.fixture(scope="module")
def sol(ds):
    return gains.solve(ds)


def _fig(value):
    assert isinstance(value, Figure)
    return value


def test_loader_reproduces_the_archived_split_and_solve(ds, sol):
    counts = {k: int(ds.state[k].sum()) for k in ("train", "validation", "test")}
    assert counts == {"train": 73720, "validation": 9115, "test": 9169}
    pilot = experiment.fixture_pilot()
    assert sol["metrics"]["tv"] == pytest.approx(pilot["baseline TV (gauge)"], rel=1e-9)
    losses = sol["metrics"]["losses"]
    assert losses["validation"] == pytest.approx(pilot["validation MSE"], rel=1e-9)
    assert losses["test"] == pytest.approx(pilot["test MSE"], rel=1e-9)
    summary = data.summary(ds)
    assert summary["rows"] == 140 and summary["channels"] == 4096


def test_fixture_extraction_is_reused(ds, tmp_path):
    archive = data.find_fixture()
    first = data.extract_fixture(archive, tmp_path)
    marker = (first.parents[1] / "COMPLETE").stat().st_mtime_ns
    assert data.extract_fixture(archive, tmp_path) == first
    assert (first.parents[1] / "COMPLETE").stat().st_mtime_ns == marker


def test_survey_tables_and_plots(ds):
    table = survey.identifiability(ds)
    summary = survey.rank_summary(table)
    assert summary["bins"] == 7 * 128
    assert summary["status 3 agrees with rank label"].split("/")[0] == str(
        summary["bins with data"]
    )
    assert (
        summary["underidentified bins"]
        == summary["underidentified bins that are trees"]
    )
    frozen = survey.rank_summary(survey.identifiability(ds, crosscheck="frozen"))
    assert frozen["native status counts"].get(4) == summary["identified bins"]
    assert len(survey.status_table()) == 7
    survey.failure_shapes(table)
    _fig(survey.rank_map(table))
    _fig(survey.support_graph(ds, table, survey.example_bins(table)))
    assert survey.is_tree([0, 3], [(0, 3)])
    assert not survey.is_tree([0, 1, 2], [(0, 1), (1, 2), (0, 2)])


def test_flag_functions(ds):
    pair = ds.baselines()[0]
    for quantity in ("amplitude", "phase", "weight", "flags"):
        _fig(flags.waterfall(ds, pair, quantity))
    _fig(flags.waterfall_grid(ds, "amplitude"))
    _fig(flags.flag_fraction_by_channel(ds))
    assert list(flags.flag_fraction_by_antenna(ds).index) == ds.names
    library = flags.strategy_library()
    assert "teaching" in library
    flags.describe_strategy(library["teaching"])
    run = flags.run_strategy(ds, library["teaching"])
    table = flags.step_table(run)
    assert len(table) == len(library["teaching"]) + 1
    assert not np.any(ds.state["original_flags"] & ~run["flags"])
    _fig(flags.step_waterfall(ds, run, 2))
    assert flags.additions_by_antenna(ds, run)["added by strategy"].sum() >= 0


def test_gain_functions(ds, sol):
    table = gains.losses_table(sol)
    assert table["invalid (val/test)"].iloc[0] == "0/0"
    for quantity in gains.QUANTITIES:
        _fig(gains.gain_maps(ds, sol, quantity))
    _fig(gains.gain_maps(ds, sol, "phase", "XY", gauge=False))
    _fig(gains.gain_spectra(ds, sol))
    _fig(gains.gauge_figure(ds, sol))
    _fig(gains.residual_waterfall(ds, sol))
    sweep = gains.iteration_sweep(ds, caps=(2, 8))
    _fig(gains.plot_sweep(sweep))
    d = sol["diagnostics"]
    # The gauge is unitary: |G|_F is unchanged wherever both are valid.
    both = d["gain_valid"] & d["tv_valid"]
    np.testing.assert_allclose(
        np.linalg.norm(d["gains"][both], axis=(-1, -2)),
        np.linalg.norm(d["gauge_gains"][both], axis=(-1, -2)),
        rtol=1e-10,
    )


def test_image_functions(ds, sol):
    corrected = image.image(ds, sol, **SMALL)
    raw = image.image(ds, None, mode="natural", **SMALL)
    assert corrected["psf"][64, 64] == pytest.approx(1.0)
    assert corrected["metrics"]["flux_recovery"] == pytest.approx(1.0, abs=0.05)
    _fig(image.image_figure(corrected, zoom=64))
    _fig(image.compare(corrected, raw, zoom=64))
    _fig(image.uv_coverage(ds))
    _fig(image.weights_figure(ds, raw))
    assert len(image.metrics_table({"a": corrected, "b": raw})) == 2
    assert len(image.robust_sweep(ds, sol, robusts=(0.0,), **SMALL)) == 1


def test_experiment_and_archives(ds):
    arms, trials = experiment.run_arms(ds, flags.strategy_library()["teaching"])
    assert {"original", "comparator", "tv-policy"} <= set(arms)
    images = experiment.image_arms(ds, arms, **SMALL)
    experiment.arms_table(arms, images)
    experiment.trials_table(trials)
    calls = experiment.decisions(arms, images)
    assert set(calls["mse_test call"]) <= {"better", "worse", "null", "undecidable"}
    _fig(experiment.ratio_figure(calls))
    k = experiment.archive_hypotheses("luno-four-station")
    assert set(k["mse_test call"]) == {"null"}
    experiment.archive_arms("luno-array")
    assert "status" in experiment.archive_status("luno-array")


def test_steering_panels_update_without_a_frontend(ds):
    solve = steer.SolvePanel(ds).update(
        time_interval=4, freq_interval=64, iterations=10
    )
    _fig(solve["maps"])
    flag = steer.FlagPanel(ds).update("teaching", 2, ds.baselines()[1])
    _fig(flag["waterfall"])
    none = np.zeros_like(ds.state["train"])
    panel = steer.ImagePanel(ds, {"a": none, "b": none})
    a = panel.image("a", "briggs", 0.5, corrected=False)
    assert panel.image("a", "briggs", 0.5, corrected=False) is a  # cached
    pytest.importorskip("ipywidgets")
    assert steer.SolvePanel(ds).widget is not None


def test_committed_notebooks_have_no_outputs():
    books = sorted((ROOT / "notebooks").glob("*.ipynb"))
    assert len(books) == 5
    for path in books:
        book = json.loads(path.read_text())
        for cell in book["cells"]:
            if cell["cell_type"] == "code":
                assert cell["outputs"] == [] and cell["execution_count"] is None, (
                    path.name
                )
