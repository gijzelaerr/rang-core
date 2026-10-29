import inspect
import json
import re
from pathlib import Path

import pytest
from rangtoy import core_cli

ROOT = Path(__file__).resolve().parents[1]
CORE_RECIPES = sorted((ROOT / "recipes").glob("core-*.yaml"))
FROZEN_RECIPES = sorted((ROOT / "recipes").glob("tv-flagging*.yaml"))


def test_audited_stage_writes_side_effects_and_reports(tmp_path, capsys):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "state.npz").write_bytes(b"state")
    run_dir = tmp_path / "run"

    def action():
        run_dir.mkdir()
        (run_dir / "result.json").write_text("{}")
        return {"seconds_total": 1.5, "actual_QC_solves": 3}

    summary = core_cli._audited("demo", run_dir, [inputs], action)
    audit = json.loads((run_dir / "side-effects.json").read_text())
    assert audit["stage"] == "demo"
    assert audit["input_files_checked"] == 1
    assert audit["inputs_unchanged"] is True
    assert audit["only_result_written"] is True
    assert audit["run_dir_files"] == ["result.json"]
    assert summary["solves"] == 3 and summary["seconds_total"] == 1.5
    assert json.loads(capsys.readouterr().out)["inputs_unchanged"] is True


def test_audited_stage_detects_input_changes(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "state.npz").write_bytes(b"state")
    run_dir = tmp_path / "run"

    def action():
        run_dir.mkdir()
        (inputs / "state.npz").write_bytes(b"changed!")
        (run_dir / "result.json").write_text("{}")
        (run_dir / "extra.json").write_text("{}")
        return {}

    core_cli._audited("demo", run_dir, [inputs], action)
    audit = json.loads((run_dir / "side-effects.json").read_text())
    assert audit["inputs_unchanged"] is False
    assert audit["only_result_written"] is False


def test_main_dispatches_stage_arguments(monkeypatch):
    calls = {}
    monkeypatch.setitem(
        core_cli.COMMANDS, "injections", lambda **kw: calls.setdefault("inj", kw)
    )
    monkeypatch.setitem(
        core_cli.COMMANDS, "signal", lambda **kw: calls.setdefault("sig", kw)
    )
    core_cli.main(["injections", "out", "prep", "--strengths", "3", "--seed", "5"])
    assert calls["inj"] == {
        "run_dir": "out",
        "prepared_dir": "prep",
        "seed": 5,
        "strengths": [3.0],
        "patterns": list(core_cli.PATTERNS),
        "iterations": 50,
    }
    core_cli.main(["signal", "out", "inputs", "uvw"])
    assert calls["sig"] == {
        "run_dir": "out",
        "inputs_dir": "inputs",
        "uvw_dir": "uvw",
        "iterations": 50,
    }
    with pytest.raises(SystemExit):
        core_cli.main(["unknown"])


def test_environment_records_quartical_absence_or_presence(tmp_path):
    record = core_cli.environment(tmp_path)
    saved = json.loads((tmp_path / "environment.json").read_text())
    assert saved["python"] == record["python"]
    assert isinstance(record["quartical_importable"], bool)
    assert isinstance(record["quartical_distribution_installed"], bool)
    assert "rangtoy.core_cli" in record["rangtoy_modules_imported"]
    for module in record["modules_with_quartical_references"]:
        assert record["rangtoy_modules_imported"][module]["quartical_references"] > 0


def test_compare_runs_the_script_and_records_its_hash(tmp_path, monkeypatch):
    script = tmp_path / "compare_core_demo.py"
    script.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "def main():\n"
        "    result, oracle, receipt = sys.argv[1:4]\n"
        "    same = Path(result).read_text() == Path(oracle).read_text()\n"
        "    Path(receipt).write_text(json.dumps({'passed': same, 'argv': sys.argv[4:]}))\n"
        "    if not same:\n"
        "        raise SystemExit(1)\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )
    monkeypatch.setattr(core_cli, "ROOT", tmp_path)
    monkeypatch.setitem(core_cli.COMPARATORS, "demo", script.name)
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / script.name).write_text(script.read_text())
    result, oracle = tmp_path / "result.json", tmp_path / "oracle.json"
    result.write_text("{}")
    oracle.write_text("{}")
    receipt = tmp_path / "receipt.json"
    comparator = core_cli.compare("demo", result, oracle, receipt, True)
    saved = json.loads(receipt.read_text())
    assert saved["passed"] is True
    assert saved["argv"] == ["--posthoc-slope-scale"]
    assert saved["comparator"] == comparator
    assert comparator["exit"] == 0 and len(comparator["sha256"]) == 64
    oracle.write_text('{"other": 1}')
    with pytest.raises(SystemExit):
        core_cli.compare("demo", result, oracle, receipt)
    assert json.loads(receipt.read_text())["comparator"]["exit"] == 1


def test_core_recipes_sit_beside_the_frozen_ones_and_never_name_quartical():
    assert [p.name for p in CORE_RECIPES] == [
        "core-actions.yaml",
        "core-cabs.yaml",
        "core-imaging.yaml",
        "core-injections.yaml",
        "core-prospective.yaml",
        "core-signal.yaml",
        "core-trend.yaml",
    ]
    assert len(FROZEN_RECIPES) == 23
    assert not {p.name for p in CORE_RECIPES} & {p.name for p in FROZEN_RECIPES}
    for recipe in CORE_RECIPES:
        assert "quartical" not in recipe.read_text().lower(), recipe.name
    # The CLI names the solver only where it checks for its absence.
    checks = inspect.getsource(core_cli.environment) + inspect.getsource(
        core_cli._rangtoy_modules
    )
    whole = (ROOT / "python/rangtoy/core_cli.py").read_text().lower()
    assert whole.count("quartical") == checks.lower().count("quartical")


def test_core_recipe_cabs_match_cli_signatures():
    # Static contract, as tests/test_flagging_next.py does for the frozen
    # recipe: no YAML dependency in the base test environment.
    pattern = re.compile(
        r"^  (?P<cab>rang-core-[\w-]+):\n(?P<body>(?:    .*\n)+)", re.MULTILINE
    )
    seen = set()
    for recipe in CORE_RECIPES:
        text = recipe.read_text()
        if recipe.name != "core-cabs.yaml":
            assert "_include: core-cabs.yaml" in text
            assert "backend: {select: native}" in text
            assert "DEFAULT: " + recipe.stem in text
        for match in pattern.finditer(text):
            body = match.group("body")
            command = re.search(r"command: (\S+)", body).group(1)
            module, function = command.rsplit(".", 1)
            if recipe.name == "core-imaging.yaml":
                # Task I's cabs call rangtoy.core_imaging and are checked by
                # tests/test_core_imaging.py (research/core-i-imaging-replay.md).
                assert module == "rangtoy.core_imaging"
                continue
            assert module == "rangtoy.core_cli"
            parameters = inspect.signature(getattr(core_cli, function)).parameters
            names = re.findall(r"\n      ([\w]+): \{", body)
            assert set(names) == set(parameters), (recipe.name, function)
            seen.add(function)
    assert seen == {
        "environment",
        "compare",
        "injections",
        "actions",
        "trend_mirror",
        "trend",
        "prospective",
        "signal",
    }


def test_frozen_consumer_and_comparators_are_the_phase3_files():
    assert core_cli.trend_run.__module__ == "rangtoy.flagging_trend"
    for stage, script in core_cli.COMPARATORS.items():
        assert (ROOT / "examples" / script).is_file(), stage
