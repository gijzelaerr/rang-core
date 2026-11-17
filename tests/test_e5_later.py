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
        (["research", "bogus"], "unknown stage 'bogus'"),
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


# -- E5-41: mask paths relative to the configuration file ------------------------


def _mask_config(tmp_path, mask, cleanmask=()):
    from rang import core_config

    raw = {
        "version": 1,
        "image": {"fits_mask": mask},
        "selfcal": {"cleanmask_method": list(cleanmask)},
    }
    config, errors = core_config.resolve(raw)
    assert errors == []
    return config


def test_mask_paths_resolve_against_the_configuration_file(tmp_path, monkeypatch):
    from rang import core_pipeline

    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    (conf_dir / "m.fits").write_bytes(b"")
    monkeypatch.chdir(tmp_path)
    img = core_pipeline._with_mask({"fits_mask": "m.fits"}, conf_dir / "c.yaml")
    assert img["fits_mask"] == str(conf_dir.resolve() / "m.fits")
    config = _mask_config(tmp_path, "m.fits", ["wsclean", "none", "m.fits"])
    assert core_pipeline._missing_masks(config, conf_dir / "c.yaml", ["image"]) == []


def test_a_mask_only_in_the_working_directory_is_used_with_a_warning(
    tmp_path, monkeypatch
):
    from rang import core_pipeline

    (tmp_path / "conf").mkdir()
    (tmp_path / "m.fits").write_bytes(b"")
    monkeypatch.chdir(tmp_path)
    said = []
    img = core_pipeline._with_mask(
        {"fits_mask": "m.fits"}, tmp_path / "conf" / "c.yaml", said.append
    )
    assert img["fits_mask"] == str((tmp_path / "m.fits").resolve())
    assert len(said) == 1 and "deprecated" in said[0]


def test_a_missing_mask_is_refused_before_anything_runs(tmp_path, monkeypatch):
    from rang import core_pipeline

    monkeypatch.chdir(tmp_path)
    config = _mask_config(
        tmp_path, "nope.fits", ["wsclean", "gone.fits", "{field}.fits"]
    )
    stages = ["image", "selfcal"]
    missing = core_pipeline._missing_masks(config, tmp_path / "c.yaml", stages)
    assert [m.split(":")[0] for m in missing] == [
        "image.fits_mask",
        "selfcal.cleanmask_method[1]",
    ]


# -- E5-42 (WB-12): a recorded flag version that is gone ------------------------


def test_a_version_never_saved_is_not_reported_lost(tmp_path):
    """The name is recorded before the version is saved: an attempt killed
    during that save wrote no flags, so its rerun gets no warning."""
    import json

    from rang import core_pipeline, core_writeback
    from rang.formats import flagversions

    ms = tmp_path / "x.ms"
    lost = core_pipeline._version_lost
    assert lost(ms, "rang_flag_1", "failed")  # no .flagversions at all
    flagversions.root(ms).mkdir()
    assert not lost(ms, "rang_flag_1", "failed")  # killed during the backup
    assert not lost(ms, "rang_flag_1", "running")
    assert lost(ms, "rang_flag_1", "done")  # it finished, so it was saved
    journal = core_writeback.journal_path(ms)
    journal.write_text(json.dumps({"flag_backup": "rang_flag_1"}), encoding="utf-8")
    assert lost(ms, "rang_flag_1", "failed")  # a session began after the save
