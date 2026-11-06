"""W5 (research/w5-stimela.md): the user recipe calls the rang-core commands,
and every research recipe is marked as one. Static text checks, as
tests/test_core_cli.py does: no Stimela or YAML import."""

import argparse
import re
from pathlib import Path

from rang import core_cli

ROOT = Path(__file__).resolve().parents[1]
RECIPES = sorted((ROOT / "recipes").glob("*.yaml"))
MARKER = re.compile(r"\A# rang-recipe: (research|user)\n")
USER = {"rang-cabs.yaml", "rang-chain.yaml"}
VERBS = ("flag", "calibrate", "apply", "image")


def kind(path):
    match = MARKER.match(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def test_every_recipe_is_marked_research_or_user():
    kinds = {p.name: kind(p) for p in RECIPES}
    assert None not in kinds.values(), kinds
    assert {n for n, k in kinds.items() if k == "user"} == USER
    research = {n for n, k in kinds.items() if k == "research"}
    assert research == {p.name for p in RECIPES if p.name.startswith("core-")}
    for path in RECIPES:
        text = path.read_text(encoding="utf-8")
        infos = re.findall(r"^  info: (.*)$", text, re.MULTILINE)
        if kinds[path.name] == "research":
            assert all(i.startswith('"Research recipe: ') for i in infos), path.name
            if path.name != "core-cabs.yaml":
                assert len(infos) == 1, path.name
        else:
            assert "research recipe" not in text.lower(), path.name


def test_marker_check_fails_without_the_marker(tmp_path):
    for path in RECIPES:
        copy = tmp_path / path.name
        copy.write_text(
            path.read_text(encoding="utf-8").split("\n", 1)[1], encoding="utf-8"
        )
        assert kind(copy) is None, path.name


def _pipeline_arguments(verb):
    parser = argparse.ArgumentParser()
    core_cli._configure_pipeline(verb)(parser)
    positional = [a.dest for a in parser._actions if not a.option_strings]
    options = {
        a.option_strings[0]: a
        for a in parser._actions
        if a.option_strings and a.option_strings[0] != "-h"
    }
    return positional, options


def test_user_cabs_are_the_console_commands_with_their_arguments():
    text = (ROOT / "recipes/rang-cabs.yaml").read_text(encoding="utf-8")
    cabs = dict(re.findall(r"^  (rang-[\w-]+):\n((?:    .*\n)+)", text, re.MULTILINE))
    assert sorted(cabs) == sorted(f"rang-{v}" for v in VERBS)
    anchor = re.search(r"inputs: &rang-command-inputs\n((?:      .*\n)+)", text)
    inputs = dict(
        re.findall(
            r"^      ([\w-]+):\n((?:        .*\n)+)", anchor.group(1), re.MULTILINE
        )
    )
    for verb in VERBS:
        body = cabs[f"rang-{verb}"]
        assert re.search(rf"^    command: rang-core {verb}$", body, re.MULTILINE)
        assert "flavour" not in body  # binary: the console script, not a function
        assert '    policies: {prefix: "--"}' in body
        if verb != "flag":
            assert "    inputs: *rang-command-inputs" in body
        assert verb in core_cli.USER_COMMANDS
        positional, options = _pipeline_arguments(verb)
        given = [n for n, b in inputs.items() if "positional: true" in b]
        assert given == positional == ["config", "ms"]
        named = {"--" + n for n in inputs if n not in given}
        assert named == set(options) == {"--run-dir", "--force"}
        assert "dtype: bool" in inputs["force"]
        assert isinstance(options["--force"], argparse._StoreTrueAction)


def test_chain_recipe_runs_the_four_commands_in_order():
    text = (ROOT / "recipes/rang-chain.yaml").read_text(encoding="utf-8")
    assert "_include: rang-cabs.yaml" in text
    assert "backend: {select: native}" in text
    assert "DEFAULT: rang-chain" in text
    steps = re.findall(r"^    (\w+):\n      cab: (rang-\w+)\n", text, re.MULTILINE)
    assert steps == [(v, f"rang-{v}") for v in VERBS]
    params = re.findall(r"^      params: (.*)$", text, re.MULTILINE)
    assert len(set(params)) == 1 and len(params) == len(VERBS)
    assert "config: =recipe.config" in params[0] and "ms: =recipe.ms" in params[0]
