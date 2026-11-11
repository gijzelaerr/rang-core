"""The "Later" findings of the E5 pre-review fixed before v0.2.0
(research/e5-prereview.md, E5-39 to E5-52)."""

import argparse

import pytest
from rang import core_cli, core_config

# -- E5-40: command line and configuration parsing -----------------------------


def test_version_is_a_global_option_anywhere_among_them(capsys):
    from rang import __version__

    assert core_cli.dispatch(["--no-receipt", "--version"]) is None
    assert capsys.readouterr().out.strip() == f"rang-core {__version__}"


@pytest.mark.parametrize(
    "argv, text",
    [
        (["--receipt"], "--receipt needs a PATH"),
        (["--bogus"], "unknown option --bogus"),
        (["bogus"], "unknown command 'bogus'"),
        (["trend"], "research stage now"),
    ],
)
def test_command_line_errors_exit_2_on_stderr(argv, text, capsys):
    with pytest.raises(SystemExit) as exc:
        core_cli.dispatch(argv)
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert text in err


def test_run_refuses_force_of_a_stage_it_does_not_run(tmp_path, capsys):
    config = tmp_path / "c.yaml"
    config.write_text("version: 1\nrun: {stages: [flag]}\n", encoding="utf-8")
    argv = ["--no-receipt", "run", str(config), str(tmp_path / "x.ms")]
    with pytest.raises(SystemExit) as exc:
        core_cli.dispatch([*argv, "--force", "selfcal"])
    assert exc.value.code == 2
    assert "--force selfcal: not in run.stages (flag)" in capsys.readouterr().err


def test_pipeline_help_says_what_is_validated_and_refused():
    parser = argparse.ArgumentParser()
    core_cli._configure_pipeline("run")(parser)
    assert "of run.stages" in parser.format_help()


def test_repeated_yaml_keys_are_refused_with_their_lines():
    text = "version: 1\nimage: {size: 64, scale: 2asec}\nimage: {niter: 5}\n"
    with pytest.raises(core_config.ConfigError) as exc:
        core_config.loads(text)
    assert exc.value.errors == [
        ("image", "repeated on line 3 (first on line 2); YAML would keep only the last")
    ]
    with pytest.raises(core_config.ConfigError, match="niter: repeated on line 4"):
        core_config.loads("version: 1\nimage:\n  niter: 5\n  niter: 6\n")


def test_yaml_merge_keys_may_still_be_overridden():
    raw = core_config.loads("a: &x {b: 1}\nd: {<<: *x, b: 2}\n")
    assert raw == {"a": {"b": 1}, "d": {"b": 2}}


def test_complex_term_refusal_names_the_key_in_yaml():
    raw = core_config.loads("version: 1\ncalibrate: {refant: auto}\n")
    with pytest.raises(core_config.ConfigError) as exc:
        core_config.validate(raw, ["calibrate"])
    text = str(exc.value)
    assert "(calibrate.refant: [auto])" in text
    assert "['auto']" not in text and "QuartiCal bins" not in text
    assert "remove it or solve K, G and B terms" in text


def test_unknown_term_key_lists_the_keys_of_its_type():
    raw = core_config.loads(
        "version: 1\ncalibrate: {primary: {terms: [{type: complex, foo: 1}]}}\n"
    )
    _, errors = core_config.resolve(raw)
    (path, text) = errors[0]
    assert path == "calibrate.primary.terms[0].foo"
    assert text.startswith("unknown term key; a complex term takes type, name,")
