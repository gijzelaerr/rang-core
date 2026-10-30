import inspect
import json
import os
import re
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from rangtoy import core_cli

ROOT = Path(__file__).resolve().parents[1]
CORE_RECIPES = sorted((ROOT / "recipes").glob("core-*.yaml"))
FROZEN_RECIPES = sorted((ROOT / "history/recipes").glob("tv-flagging*.yaml"))


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
    # The legacy form (the verb `run` implied) and the P9 form are the same call.
    for argv in (
        ["injections", "out", "prep", "--strengths", "3", "--seed", "5"],
        ["injections", "run", "out", "prep", "--strengths", "3", "--seed", "5"],
    ):
        calls.clear()
        core_cli.main(["--no-receipt", *argv])
        assert calls["inj"] == {
            "run_dir": "out",
            "prepared_dir": "prep",
            "seed": 5,
            "strengths": [3.0],
            "patterns": list(core_cli.PATTERNS),
            "iterations": 50,
        }
    core_cli.main(["--no-receipt", "signal", "out", "inputs", "uvw"])
    assert calls["sig"] == {
        "run_dir": "out",
        "inputs_dir": "inputs",
        "uvw_dir": "uvw",
        "iterations": 50,
    }
    with pytest.raises(SystemExit):
        core_cli.main(["--no-receipt", "unknown"])
    with pytest.raises(SystemExit):
        core_cli.main(["--no-receipt", "injections", "nonsense-verb-free"])


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
    # Since P6 the driver is core_trend.run, which calls the frozen
    # flagging_trend.run unedited (research/p6-python-hotspots.md).
    assert core_cli.trend_run.__module__ == "rangtoy.core_trend"
    from rangtoy import core_trend

    assert core_trend.flagging_trend.run.__module__ == "rangtoy.flagging_trend"
    for stage, script in core_cli.COMPARATORS.items():
        assert (ROOT / "examples" / script).is_file(), stage


# --- Task P9 (research/p9-cli.md): one CLI, receipts, archives, pinning, check.


def _trend_pair(tmp_path, value=1.0):
    result = tmp_path / "result.json"
    oracle = tmp_path / "oracle.json"
    result.write_text(json.dumps({"records": [{"primary_polar_TV": value}]}))
    oracle.write_text(
        json.dumps({"raw_result": {"records": [{"primary_polar_TV": 1.0}]}})
    )
    return result, oracle


def test_stage_compare_writes_the_comparator_receipt_and_a_rang_receipt(
    tmp_path, capsys
):
    result, oracle = _trend_pair(tmp_path)
    out = tmp_path / "compare.json"
    verdict = core_cli.dispatch(
        ["trend", "compare", str(result), str(oracle), str(out)]
    )
    printed = json.loads(capsys.readouterr().out)
    assert printed["passed"] is True and printed["classes"]["float"]["compared"] == 1
    assert verdict["passed"] is True and verdict["exit"] == 0
    assert verdict["counts"] == {"classes": {"float": 1}, "excluded": 0}
    # The comparator's own receipt carries no CLI additions.
    assert "comparator" not in json.loads(out.read_text())
    receipt = json.loads((tmp_path / "compare.compare.rang-receipt.json").read_text())
    assert receipt["schema"] == "rang.receipt" and receipt["version"] == 1
    assert (receipt["stage"], receipt["verb"], receipt["exit"]) == (
        "trend",
        "compare",
        0,
    )
    assert receipt["verdict"] == verdict
    assert [i["path"] for i in receipt["inputs"]] == [
        result.as_posix(),
        oracle.as_posix(),
    ]
    assert receipt["inputs"][0]["sha256"] == sha256(result.read_bytes()).hexdigest()
    assert receipt["outputs"][0]["path"] == out.as_posix()
    assert receipt["outputs"][0]["sha256"] == sha256(out.read_bytes()).hexdigest()
    env = receipt["environment"]
    assert set(core_cli.THREAD_CAPS) <= set(env["threads"])
    assert env["platform"] and env["machine"]
    assert set(receipt["timings"]) == {"wall_seconds", "cpu_seconds", "peak_rss_mb"}
    assert set(receipt["commit"]) == {"head", "dirty"}


def test_failing_compare_exits_like_the_script_and_records_the_verdict(tmp_path):
    result, oracle = _trend_pair(tmp_path, value=2.0)
    out = tmp_path / "compare.json"
    receipt = tmp_path / "r.json"
    with pytest.raises(SystemExit) as exc:
        core_cli.main(
            [
                "--receipt",
                str(receipt),
                "trend",
                "compare",
                str(result),
                str(oracle),
                str(out),
            ]
        )
    assert exc.value.code == 1
    saved = json.loads(receipt.read_text())
    assert saved["exit"] == 1 and saved["verdict"]["passed"] is False
    assert saved["verdict"]["failures"] == 1


def test_wrapper_script_and_cli_write_identical_receipts(tmp_path):
    result, oracle = _trend_pair(tmp_path)
    by_script, by_cli = tmp_path / "script.json", tmp_path / "cli.json"
    script = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/compare_core_trend.py"),
            str(result),
            str(oracle),
            str(by_script),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "rangtoy.core_cli",
            "--no-receipt",
            "trend",
            "compare",
            str(result),
            str(oracle),
            str(by_cli),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert script.stdout == cli.stdout
    assert by_script.read_bytes() == by_cli.read_bytes()


def test_archive_is_an_oracle_for_the_comparators(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "result.json").write_text(
        json.dumps({"records": [{"primary_polar_TV": 1.0}]})
    )
    (run_dir / "side-effects.json").write_text('{"inputs_unchanged": true}')
    archive = tmp_path / "archive.json"
    core_cli.main(["--no-receipt", "trend", "archive", str(run_dir), str(archive)])
    payload = json.loads(archive.read_text())
    assert payload["schema"] == "rang.archive" and payload["version"] == 1
    assert payload["stage"] == "trend"
    assert payload["run_files"]["side-effects.json"] == {"inputs_unchanged": True}
    assert (
        payload["result_sha256"]
        == sha256((run_dir / "result.json").read_bytes()).hexdigest()
    )
    with pytest.raises(SystemExit):  # never overwritten
        core_cli.main(["--no-receipt", "trend", "archive", str(run_dir), str(archive)])
    verdict = core_cli.dispatch(
        [
            "--no-receipt",
            "trend",
            "compare",
            str(run_dir / "result.json"),
            str(archive),
            str(tmp_path / "c.json"),
        ]
    )
    assert verdict["passed"] is True


def test_default_receipt_sits_beside_the_output_never_inside():
    assert core_cli.default_receipt("outputs/x/actions", "run") == Path(
        "outputs/x/actions.run.rang-receipt.json"
    )
    assert core_cli.default_receipt("outputs/x/a/compare-archive.json", "compare") == (
        Path("outputs/x/a/compare-archive.compare.rang-receipt.json")
    )


def test_pin_threads_defaults_only_where_unset():
    environ = {"OPENBLAS_NUM_THREADS": "8"}
    pinned = core_cli.pin_threads(environ)
    assert environ["OPENBLAS_NUM_THREADS"] == "8"
    assert pinned == ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "XLA_FLAGS"]
    assert environ["OMP_NUM_THREADS"] == "1"
    assert core_cli.pin_threads(environ) == []


def test_cli_pins_before_numpy_and_honours_the_opt_out(tmp_path):
    probe = (
        "import sys\n"
        "import rangtoy.core_cli as c\n"
        "assert 'numpy' not in sys.modules, 'core_cli imported NumPy'\n"
        "c.main(sys.argv[1:])\n"
        "import numpy, os\n"
        "print(os.environ.get('OPENBLAS_NUM_THREADS'))\n"
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in core_cli.THREAD_CAPS and k != "RANG_PIN_THREADS"
    }
    pinned = subprocess.run(
        [sys.executable, "-c", probe, "--no-receipt", "check", "--only", "nonexistent"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert "unknown step" in pinned.stderr
    run = [sys.executable, "-c", probe, "--no-receipt", "-h"]
    out = subprocess.run(run, capture_output=True, text=True, env=env, check=True)
    assert out.stdout.strip().splitlines()[-1] == "1"
    opt_out = [sys.executable, "-c", probe, "--no-pin-threads", "--no-receipt", "-h"]
    out = subprocess.run(opt_out, capture_output=True, text=True, env=env, check=True)
    assert out.stdout.strip().splitlines()[-1] == "None"


def test_stage_table_names_existing_drivers_and_engine_comparators():
    from rangtoy import core_compare

    for stage, entry in core_cli.STAGES.items():
        assert entry["help"], stage
        for verb, spec in entry.items():
            if verb == "help":
                continue
            if spec["kind"] == "script":
                assert (ROOT / "examples" / spec["script"]).is_file(), (stage, verb)
            elif spec["kind"] == "engine":
                assert spec["name"] in core_compare.COMPARATORS, (stage, verb)
    wrappers = sorted(p.stem for p in (ROOT / "examples").glob("compare_core_*.py"))
    # Comparators merged after P9's branch point that are not on the engine
    # yet (research/p9-cli.md, "For the coordinator"); each stays a script.
    pending = {"compare_core_wgridder"}
    engine = sorted(f"compare_core_{n}" for n in core_compare.COMPARATORS)
    assert sorted(set(wrappers) - pending) == engine
    for wrapper in sorted(set(wrappers) - pending):
        text = (ROOT / "examples" / f"{wrapper}.py").read_text()
        assert f'sys.exit(main("{wrapper.removeprefix("compare_core_")}"))' in text
    assert "check" in core_cli.TOP_LEVEL and "environment" in core_cli.TOP_LEVEL


def test_legacy_forms_map_onto_stage_verb():
    assert core_cli._legacy(["trend-mirror", "m", "s"]) == ["trend", "mirror", "m", "s"]
    assert core_cli._legacy(["actions", "r", "p"]) == ["actions", "run", "r", "p"]
    assert core_cli._legacy(["actions", "compare", "a"]) == ["actions", "compare", "a"]
    assert core_cli._legacy(["weights", "compare", "b"]) == ["weights", "compare", "b"]


EXPECTED_STEPS = [
    "root-build",
    "root-test",
    "root-clippy",
    "root-fmt",
    "core-build",
    "core-test",
    "core-clippy",
    "core-fmt",
    "ext-build",
    "ext-clippy",
    "ext-fmt",
    "ruff",
    "ruff-format",
    "diff-check",
    "pytest",
]


def test_check_has_the_fifteen_steps_of_check_all_in_order():
    from rangtoy import check

    table = check.steps()
    assert [s[0] for s in table] == EXPECTED_STEPS
    labels = {s[0]: s[5] for s in table}
    assert labels["root-build"] == "cargo +1.93 build --offline --release -q"
    assert labels["core-test"] == "rust_test --manifest-path core/Cargo.toml"
    assert labels["ruff"] == ".venv/bin/ruff check python examples tests"
    for name, _, _, argv, _, _ in table:
        assert isinstance(argv, list) and all(isinstance(a, str) for a in argv), name
    wrapper = (ROOT / "tools/check-all.sh").read_text()
    assert "exec flock" in wrapper and "-m rangtoy.check" in wrapper


def test_check_runs_every_step_and_reports_failures(tmp_path, monkeypatch, capsys):
    from rangtoy import check

    monkeypatch.delenv("RANG_CHECKALL_LOCKED", raising=False)
    monkeypatch.setenv("RANG_CHECKALL_LOCK", str(tmp_path / "lock"))
    seen = []

    def runner(kind, argv, cwd, env):
        seen.append((kind, env.get("RANG_CHECKALL_LOCKED")))
        return 1 if argv[-3:] == ["python", "examples", "tests"] else 0

    receipt = tmp_path / "steps.json"
    code = check.main(["--json", str(receipt)], runner=runner, root=ROOT)
    out = capsys.readouterr().out.splitlines()
    assert code == 1
    assert [line[3:] for line in out if line.startswith("## ")] == [
        *EXPECTED_STEPS,
        "overall: FAIL",
    ]
    assert "FAILED: .venv/bin/ruff check python examples tests" in out
    assert len(seen) == 15 and all(locked == "1" for _, locked in seen)
    assert json.loads(receipt.read_text())["pass"] is False
    assert (tmp_path / "lock").exists()
    code = check.main(["--rust"], runner=lambda *a: 0, root=ROOT)
    out = capsys.readouterr().out
    assert code == 0 and "## pytest" not in out and out.endswith("## overall: PASS\n")
    assert "## ext-clippy" in out and "## ext-build" not in out


def test_check_finds_the_checkout():
    from rangtoy import check

    assert check.find_root(ROOT / "python" / "rangtoy") == ROOT


def test_check_sets_running_launchers_aside_for_the_reinstall(tmp_path):
    from rangtoy import check

    (tmp_path / "rang-core.exe").write_bytes(b"launcher")
    (tmp_path / "rang-core.exe.1.old").write_bytes(b"stale")
    (tmp_path / "python.exe").write_bytes(b"python")
    moved = check.set_aside_launchers(tmp_path)
    assert [p.name for p in moved] == [f"rang-core.exe.{os.getpid()}.old"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "python.exe",
        f"rang-core.exe.{os.getpid()}.old",
    ]
