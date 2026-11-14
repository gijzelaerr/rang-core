"""Self-calibration arms 1 and 2 of issue #6 (research/selfcal-arms.md): the
frozen schedules validate with C5's keys, their round-to-term and gate
mapping is the note's, the defaults and E2-A are unchanged, and every
schedule runs end to end on the public fixture with the extension's
gemclean (skipped without the fixture)."""

import importlib.util
import json
import shutil
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest
from rang import cal_selfcal, core_cli, core_config, core_ms
from rang import core_pipeline as pipe

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))
_spec = importlib.util.spec_from_file_location(
    "check_selfcal_arms", ROOT / "examples/check_selfcal_arms.py"
)
arms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(arms)


def resolved(text):
    raw = core_config._yaml().safe_load(text)
    return core_config.resolve(raw)


@pytest.mark.parametrize("key", sorted(arms.SCHEDULES))
def test_every_frozen_schedule_validates_with_c5s_keys(key):
    arm, loop = key
    config, errors = resolved(arms.config_text(arm, loop, gemclean="auto"))
    assert errors == []
    assert [r for r in core_config.refusals(config, ["selfcal"])] == []
    rounds, _ = arms.SCHEDULES[key]
    assert config["selfcal"]["rounds"] == rounds
    assert config["image"]["threads"] == 4


def test_round_terms_follow_the_frozen_schedules():
    def kinds(arm, loop):
        config, _ = resolved(arms.config_text(arm, loop, gemclean="auto"))
        n = config["selfcal"]["rounds"]
        return [
            (t["type"], t["solint"], t.get("freqint", "inf"))
            for t in (pipe.selfcal_round_term(config, k) for k in range(1, n + 1))
        ]

    assert kinds("r", "pa") == [("Sp", "inf", "inf")] * 2 + [("Sp", 8, "inf")] * 2 + [
        ("Sa", 8, "inf")
    ]
    assert kinds("r", "delay") == [("Sd", "inf", "inf")] * 2 + [("Sd", 8, "inf")] * 3
    assert kinds("p", "delay") == [("Sp", 8, 1), ("Sd", 8, "inf")]
    assert kinds("u", "pa") == [("Sp", 8, "inf"), ("Sa", 8, "inf")]
    assert ("p", "pa") not in arms.SCHEDULES  # arm 2 on pa is u (section 4)


def test_the_gate_mapping_is_the_notes():
    T2 = arms.c5.T2
    sp, sd = {"type": "Sp"}, {"type": "Sd"}
    # Round R: T2's round-2 rows; round R - 1: round-1 rows of its term.
    assert arms.gates_of("pa", 5, 5, {"type": "Sa"}) == T2[("pa", 2)]
    assert arms.gates_of("pa", 4, 5, sp) == T2[("pa", 1)]
    assert arms.gates_of("pa", 3, 5, sp) is None
    assert arms.gates_of("delay", 4, 5, sd) == T2[("delay", 1)]
    assert arms.gates_of("delay", 1, 2, sp) == {"phase_deg": (1.0, 3.0)}
    # u (R = 2) is C5's own table.
    for loop in ("pa", "delay"):
        term = {"type": "Sd" if loop == "delay" else "Sp"}
        for k in (1, 2):
            assert arms.gates_of(loop, k, 2, term) == T2[(loop, k)]


def test_defaults_and_e2a_are_unchanged():
    config, errors = resolved("version: 1\n")
    assert errors == []
    sc = config["selfcal"]
    assert sc["rounds"] == 2
    assert [t["type"] for t in sc["terms"]] == ["Sp", "Sa"]
    raw = core_config.load(ROOT / "tests/data/w2/e2a.yaml")
    e2a, errors = core_config.resolve(raw)
    assert errors == []
    # E2-A's own schedule, as C5 section 6.6 records it.
    terms = [pipe.selfcal_round_term(e2a, k) for k in (1, 2)]
    assert [(t["type"], t["solint"]) for t in terms] == [("Sp", 120), ("Sa", 120)]


# --- the public fixture ----------------------------------------------------------


def fixture_ms(tmp_path_factory):
    from rang.notebook import data as fixture_data

    source = fixture_data.find_fixture()
    if source is None:
        pytest.skip("public fixture not present (RANG_FIXTURE)")
    if source.suffix == ".zip":
        cache = tmp_path_factory.mktemp("fixture")
        source = fixture_data.extract_fixture(source, cache)
    return Path(source)


@pytest.fixture(scope="module")
def fixture_copy(tmp_path_factory):
    return fixture_ms(tmp_path_factory)


SMALL_IMAGE = (
    "{fields: [target], gemclean: auto, size: 128, scale: 30asec, niter: 200, auto_threshold: 3.0, "
    "threads: 2}"
)


@pytest.mark.parametrize("key", sorted(arms.SCHEDULES))
def test_every_schedule_runs_on_the_public_fixture(key, fixture_copy, tmp_path):
    _arm, _loop = key
    rounds, terms = arms.SCHEDULES[key]
    ms = tmp_path / "scan9.ms"
    shutil.copytree(fixture_copy, ms)
    with core_ms.open_table(ms / "FIELD") as t:
        field = t.getcol("NAME")[0]
    with core_ms.open_table(ms / "ANTENNA") as t:
        refant = t.getcol("NAME")[0]
    config = tmp_path / "config.yaml"
    config.write_text(
        textwrap.dedent(
            f"""\
            version: 1
            fields: {{target: ['{field}']}}
            image: {SMALL_IMAGE}
            selfcal:
              rounds: {rounds}
              terms: {terms}
              input_column: DATA
              refant: {refant}
            """
        ),
        encoding="utf-8",
    )
    run = tmp_path / "run"
    core_cli.dispatch(["selfcal", str(config), str(ms), "--run-dir", str(run)])
    summary = json.loads((run / "selfcal" / "summary.json").read_text())
    (got,) = summary["fields"]
    assert len(got["rounds"]) == rounds
    config_resolved, _ = core_config.resolve(
        core_config._yaml().safe_load(config.read_text())
    )
    with core_ms.open_table(ms) as t:
        scan = t.getcol("SCAN_NUMBER")
        time = t.getcol("TIME")
    for r in got["rounds"]:
        want = pipe.selfcal_round_term(config_resolved, r["round"])
        assert r["term"]["type"] == want["type"]
        assert r["term"]["solint"] == want["solint"]
        # Bins per scan follow the round's interval (C5's G4 rule).
        nint = {s: len(np.unique(time[scan == s])) for s in np.unique(scan)}
        step = None if want["solint"] == "inf" else int(want["solint"])
        bins = {str(s): (1 if step is None else -(-n // step)) for s, n in nint.items()}
        assert r["solve"]["time_bins_per_scan"] == bins
        gains, _flags, _t, gfreq, _s = cal_selfcal.read_store(
            r["store"], r["term"]["name"]
        )
        assert np.isfinite(gains).all()
        if want["type"] == "Sp" and want.get("freqint") == 1:
            assert len(gfreq) == gains.shape[1] and gains.shape[1] > 1
    assert got["final_image"]["column"] == "CORRECTED_DATA"
