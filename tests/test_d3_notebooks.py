"""Task D3: the science notebooks and `rang.notebook.science`
(research/d3-science-notebooks.md).

The archive readers are checked against the committed JSON (no data needed);
the quoted B1 rules against the frozen protocol text; the JAX reference path
and one observability audit against the Rust toy and their archives; and both
notebooks are executed through papermill on the public fixture with every
switch off, as the documentation workflow runs them. The execution test skips
without the fixture or papermill (the `docs` extra).
"""

import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytest.importorskip("pandas")
pytest.importorskip("matplotlib")

from rang.notebook import science

ROOT = Path(__file__).resolve().parents[1]
SCIENCE = ROOT / "notebooks" / "science"
BOOKS = (
    "06-gain-tv-flagging-the-experiment.ipynb",
    "07-beam-and-pointing.ipynb",
)
SWITCHES_OFF = {
    "RANG_NOTEBOOK_LUNO": "0",
    "RANG_NOTEBOOK_SLOW": "0",
    "RANG_NOTEBOOK_HOLOGRAPHY": "0",
}
EXECUTION_BUDGET_S = 300


def _results(name):
    return json.loads((ROOT / "research" / "results" / name).read_text("utf-8"))


# --- archive readers ---------------------------------------------------------


def test_call_table_matches_the_verdict_archive():
    record = _results("flagging-verdict.json")
    counts = science.call_counts(record)
    assert int(counts.loc["all"].sum()) == record["summary"]["calls"]
    for call, n in record["summary"]["by_call"].items():
        assert int(counts.loc["all", call]) == n
    calls = science.calls_table(record)
    assert len(calls) == len(record["calls"])
    # every call is re-derived from its ratio with the frozen band
    from rang.core_campaign import BETTER, WORSE

    for _, row in calls.iterrows():
        ratio = row["ratio"]
        if math.isnan(ratio):
            assert row["call"] == "undecidable"
        else:
            expected = (
                "better" if ratio <= BETTER else "worse" if ratio >= WORSE else "null"
            )
            assert row["call"] == expected


def test_headline_and_policy_and_cost_readers():
    record = _results("flagging-verdict.json")
    head = science.headline_calls(record)
    assert len(head) and set(head["call"]) <= {"null", "undecidable"}
    assert all(p.endswith("vs tricolour-firstpass") for p in head["pair"])
    selections = science.policy_selections(record)
    assert len(selections) == len(record["tv_policy_selections"])
    assert int(selections["guided_accepted"].fillna(0).sum()) == 0
    cost = science.cost_table(record)
    assert list(cost["ratio"]) == [c["ratio"] for c in record["cost_clause"]]
    assert science.cost_limit() == 3.0
    text = science.verdict_summary_markdown(record)
    assert f"**{record['summary']['calls']}**" in text
    assert f"**{record['summary']['by_call']['null']} are null**" in text


def test_context_and_fixture_era_readers():
    record = _results("flagging-verdict.json")
    ctx = science.context_tables(record)
    assert set(ctx) == {
        "L1-M model calls",
        "C1 closure-TV map (Q1)",
        "L5 whole-array solve",
        "A1 emptied station-bins",
        "O-CASA matched crosscal (arm SH)",
    }
    assert (
        ctx["L5 whole-array solve"].loc["anderson-3", "iterations"]
        == (record["context"]["l5_array"]["anderson-3"]["iterations"])
    )
    era = science.fixture_era(record)
    assert era["policy selected"] is None
    assert era["injected case: TV and residual rankings chose the same mask"]


def test_flagging_rules_are_the_frozen_constants():
    from rang import core_campaign as cc

    rules = science.flagging_rules()
    assert rules["thresholds τ"] == cc.THRESHOLDS
    assert rules["TV weights α"] == cc.TV_WEIGHTS
    assert rules["call band (better ≤, worse ≥)"] == (cc.BETTER, cc.WORSE)


def test_wave3_map_names_committed_archives():
    table = science.wave3_table()
    for task, row in table.iterrows():
        assert row["archive present"] == (task != "L3"), task


def test_verdict_table_is_current():
    ok, output = science.verdict_tables_check()
    assert ok, output


def test_b1_readers_match_the_product_archive():
    record = _results("b1-beam-product.json")
    gates = science.b1_gates(record)
    assert list(gates["pass"]) == [True, True, True] and record["gates_pass"]
    comparison = science.b1_comparison(record)
    key = "max |ΔI| on the HP ring / 30″ signal"
    for model in ("katbeam", "eidos"):
        assert comparison.loc[key, model] == pytest.approx(
            record["summary"][model]["ring_max_over_30arcsec_signal_median"]
        )
    science.b1_per_channel_figure(record)
    science.b1_antenna_spread_figure(record)


def _flat(text):
    return re.sub(r"\s+", " ", text)


def test_quoted_b1_rules_are_verbatim_in_the_protocol():
    protocol = _flat((ROOT / science.B1_PROTOCOL).read_text("utf-8"))
    for rule in (
        science.B1_2_DECISION_RULE,
        science.B1_3_DECISION_RULE,
        science.B1_3_MATCHED_COST,
    ):
        assert _flat(rule) in protocol
    for metric in science.B1_3_METRICS:
        assert f"**{metric}**" in protocol


def test_g1b_reader_on_a_synthetic_record():
    record = {
        "antennas": ["a", "b"],
        "g1b": {
            "cases": [
                {
                    "injected_arcmin": [0.0, 0.0],
                    "noiseless_error_arcmin": [[0.1, 0.2], [0.3, 0.4]],
                    "rms_error_arcmin": [[1, 2], [3, 4]],
                    "coverage_1sigma": 0.7,
                },
                {
                    "injected_arcmin": [1.0, 0.0],
                    "noiseless_error_arcmin": [[0.1, 0.2], [0.3, 0.4]],
                    "rms_error_arcmin": [[1, 2], [3, 4]],
                    "coverage_1sigma": 0.6,
                },
            ]
        },
    }
    table = science.g1b_table(record)
    assert table.shape[0] == 4
    assert table.loc[((1.0, 0.0), "b"), "noise-free error xEl"] == 0.3
    science.g1b_figure(record)


def test_switches_default_off(monkeypatch):
    for name in science.SWITCHES:
        monkeypatch.delenv(name, raising=False)
        assert not science.switch(name)
        assert science.skip_line(name).startswith(f"skipped: set {name}=1")
        monkeypatch.setenv(name, "1")
        assert science.switch(name)


# --- the JAX reference path and an audit, live on the Rust toy ----------------


@pytest.fixture(scope="module")
def toy():
    pytest.importorskip("jax")
    science.enable_x64()
    return science.toy_fixture()


def test_jax_reference_path_agrees_with_rust(toy):
    check = science.jax_against_rust(toy)
    assert check["max |V_jax − V_rust| (Jy)"] < 1e-8
    assert check["max |J_jax − J_rust| (Jy/arcmin)"] < 1e-10


def test_symmetry_audit_reproduces_the_archive(toy):
    live = science.symmetry_audit(toy, cases=science.SYMMETRY_CASES[:3])
    assert list(live["observable common modes"]) == [0, 2, 0]
    archived = science.gain_audit_archive().loc["thinned, gains fixed"]
    row = live.loc["ellipse 1.1, rotating"]
    assert row["σ axis 1 (arcsec)"] == pytest.approx(
        archived["σ axis 1 (arcsec)"], rel=1e-9
    )


# --- the notebooks ------------------------------------------------------------


def test_committed_notebooks_have_no_outputs():
    nbformat = pytest.importorskip("nbformat")
    for name in BOOKS:
        book = nbformat.read(SCIENCE / name, as_version=4)
        for cell in book.cells:
            if cell.cell_type == "code":
                assert not cell.outputs and cell.execution_count is None, name


def test_docs_build_picks_up_the_science_notebooks():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "execute_notebooks", ROOT / "docs" / "execute_notebooks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = [p.name for p in module.sources()]
    for name in BOOKS:
        assert name in names
    assert len(names) == len(set(names)), "flat output names must be unique"
    index = (ROOT / "docs" / "tutorials" / "index.md").read_text("utf-8")
    for name in BOOKS:
        assert f"notebooks/{name.removesuffix('.ipynb')}" in index


def _execute(name, out_dir):
    import papermill

    started = time.perf_counter()
    papermill.execute_notebook(
        str(SCIENCE / name),
        str(out_dir / name),
        cwd=str(SCIENCE),
        kernel_name="python3",
        progress_bar=False,
        request_save_on_cell_execute=False,
        execution_timeout=EXECUTION_BUDGET_S,
        shutdown_kernel="immediate",
    )
    return time.perf_counter() - started


@pytest.fixture(scope="module")
def executed(tmp_path_factory):
    pytest.importorskip("papermill")
    pytest.importorskip("ipykernel")
    pytest.importorskip("jax")
    from rang.notebook import data

    if data.find_fixture() is None:
        pytest.skip("fixture archive not present")
    cache = tmp_path_factory.mktemp("science-cache")
    out = tmp_path_factory.mktemp("science-executed")
    # Extract before the kernels start, so they do not race on the cache.
    data.extract_fixture(data.find_fixture(), cache)
    science.pointing_fixture(cache)
    env = {
        **SWITCHES_OFF,
        "RANG_NOTEBOOK_CACHE": str(cache),
        "MPLBACKEND": "Agg",
        "RAYON_NUM_THREADS": os.environ.get("RAYON_NUM_THREADS", "2"),
        "JAX_PLATFORMS": "cpu",
    }
    # The kernels inherit the process environment (papermill has no env
    # argument), so it is set once for both and restored afterwards.
    previous = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        with ThreadPoolExecutor(max_workers=len(BOOKS)) as pool:
            futures = {name: pool.submit(_execute, name, out) for name in BOOKS}
        seconds = {name: f.result() for name, f in futures.items()}
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return out, seconds


def _outputs(path):
    import nbformat

    book = nbformat.read(path, as_version=4)
    text, errors, images = [], [], 0
    for cell in book.cells:
        for output in cell.get("outputs", []):
            if output.output_type == "error":
                errors.append(output.ename)
            text.append("".join(output.get("text", "")))
            data = output.get("data", {})
            text.append(str(data.get("text/plain", "")))
            text.append(str(data.get("text/markdown", "")))
            images += "image/png" in data
    return "".join(text), errors, images


def test_notebook_06_executes_with_switches_off(executed):
    out, seconds = executed
    text, errors, images = _outputs(out / BOOKS[0])
    assert not errors
    assert seconds[BOOKS[0]] < EXECUTION_BUDGET_S
    assert images >= 4
    assert "skipped: set RANG_NOTEBOOK_LUNO=1" in text
    record = _results("flagging-verdict.json")
    assert f"**{record['summary']['by_call']['null']} are null**" in text
    assert "up to date" in text


def test_notebook_07_executes_with_switches_off(executed):
    out, seconds = executed
    text, errors, images = _outputs(out / BOOKS[1])
    assert not errors
    assert seconds[BOOKS[1]] < EXECUTION_BUDGET_S
    assert images >= 4
    assert "skipped: set RANG_NOTEBOOK_SLOW=1" in text
    assert "skipped: set RANG_NOTEBOOK_HOLOGRAPHY=1" in text
    assert "gate G1a" in text
    assert science.B1_2_DECISION_RULE.split(" ")[0] in text
