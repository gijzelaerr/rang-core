"""W4 (research/w4-unsupported.md): every case of section 3 on W2's synthetic
MS (`test_w2_commands.make_ms`: 4 antennas, 240 rows, 16 channels, fields CAL
and TGT in scans 1 and 2, WEIGHT but no WEIGHT_SPECTRUM). Each command either
works or is refused (exit 2, nothing written) with a message naming the
reason. The run on A1's MS is `examples/check_w4_unsupported.py`."""

import importlib.util
import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml
from rang import core_ms, core_ms_write
from rang import core_pipeline as pipe
from rang.formats import flagversions
from test_w2_commands import STRATEGY, cli, expected_flags, fake_gemclean, make_ms

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_w4_unsupported", ROOT / "examples/check_w4_unsupported.py"
)
w4 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w4)

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)
STAGES = ("flag", "calibrate", "apply", "image")


def write(tmp_path, name="config.yaml", **extra):
    """W2's test configuration, with `extra` merged in (sections as dicts)."""
    (tmp_path / "strategy.yaml").write_text(STRATEGY, encoding="utf-8")
    config = {
        "version": 1,
        "fields": {"fcal": ["CAL"], "target": ["TGT"]},
        "flag": {"strategy": "strategy.yaml"},
        "calibrate": {
            "primary": {"terms": [{"type": "complex", "solint": 4, "freqint": 8}]}
        },
        "image": {
            "gemclean": str(fake_gemclean(tmp_path)),
            "size": [64, 64],
            "scale": "20asec",
            "niter": 10,
            "threads": 1,
        },
    }
    path = tmp_path / name
    path.write_text(yaml.safe_dump(w4.merge(config, extra)), encoding="utf-8")
    return path


def run(capsys, command, config, ms, run_dir=None):
    argv = [command, config, ms]
    if command == "check":
        argv = ["config", "check", config, ms]
        argv += [a for s in STAGES for a in ("--stage", s)]
    elif run_dir is not None:
        argv += ["--run-dir", run_dir]
    try:
        cli(*argv)
        code = 0
    except SystemExit as exc:
        code = exc.code
    return code, capsys.readouterr().err


def refused(capsys, command, config, ms, *words):
    before = w4.fingerprint(ms)
    code, err = run(capsys, command, config, ms)
    assert code == 2, err
    for word in words:
        assert word in err, (word, err)
    assert w4.fingerprint(ms) == before


def works(capsys, command, config, ms, run_dir=None):
    code, err = run(capsys, command, config, ms, run_dir)
    assert code == 0, err


def twin(tmp_path, name, edit=None, **kw):
    ms = make_ms(tmp_path / f"{name}.ms", **kw)
    if edit:
        edit(ms)
    return ms


def column(ms, name):
    with core_ms.open_table(ms) as t:
        return t.getcol(name)


def store(ms):
    return pipe.default_run_dir(ms) / "calibrate" / "complex.qc"


def same_store(a, b):
    result = w4.compare_store(store(a), store(b))
    return result["gains_and_flags_identical"] and result["files_identical"]


# -- spectral windows and data descriptions ------------------------------------


@pytest.mark.parametrize(
    ("edit", "words"),
    [
        (lambda ms: w4.add_window(ms, 16, "TGT"), ["2 data descriptions", "split"]),
        (lambda ms: w4.add_window(ms, 8, "TGT"), ["differ in shape"]),
        (
            lambda ms: w4.add_window(ms, 16, "TGT", same_spw=True),
            ["2 data descriptions"],
        ),
    ],
)
def test_several_windows_in_use_are_refused_by_every_stage(
    tmp_path, capsys, edit, words
):
    ms = twin(tmp_path, "x", edit)
    config = write(tmp_path)
    for command in ("check", *STAGES):
        refused(capsys, command, config, ms, *words)
    assert not flagversions.versions(ms)


def test_an_unused_window_changes_nothing(tmp_path, capsys):
    base = twin(tmp_path, "base")
    spw = twin(tmp_path, "spw", lambda ms: w4.add_window(ms, 8, None))
    config = write(tmp_path)
    for ms in (base, spw):
        works(capsys, "calibrate", config, ms)
    assert same_store(spw, base)


def test_one_data_description_other_than_zero(tmp_path, capsys):
    base = twin(tmp_path, "base")
    one = twin(tmp_path, "one", lambda ms: w4.add_window(ms, 16, "all", same_spw=True))
    config = write(tmp_path)
    for ms in (base, one):
        works(capsys, "flag", config, ms)
        works(capsys, "calibrate", config, ms)
    assert np.array_equal(column(one, "FLAG"), column(base, "FLAG"))
    result = w4.compare_store(store(one), store(base), files=False)
    assert result["gains_and_flags_identical"]
    works(capsys, "apply", config, one)
    refused(capsys, "image", config, one, "DATA_DESC_ID 1", "data description 0")


@pytest.mark.parametrize(
    ("edit", "extra", "words"),
    [
        (
            lambda ms: w4.add_window(ms, 16, "all", same_spw=True),
            {},
            ["image:", "DATA_DESC_ID 1"],
        ),
        # gemclean selects scans since W6; TGT has no rows in scan 1.
        (None, {"data": {"scans": [1]}}, ["image", "'TGT'", "scans [1]", "no rows"]),
    ],
)
def test_run_is_refused_before_flag_writes_when_a_later_stage_cannot_run(
    tmp_path, capsys, edit, extra, words
):
    # `rang-core run` checks every stage's data first (W2's rule): a refusal
    # for image stops it before flag saves a version or writes FLAG.
    ms = twin(tmp_path, "x", edit)
    flag = column(ms, "FLAG")
    config = write(tmp_path, run={"stages": ["flag", "calibrate", "image"]}, **extra)
    refused(capsys, "run", config, ms, *words)
    assert not flagversions.versions(ms)
    assert np.array_equal(column(ms, "FLAG"), flag)


# -- fields and selections -------------------------------------------------------


def test_a_name_of_two_fields_needs_an_id_for_image(tmp_path, capsys):
    ms = twin(tmp_path, "dup", lambda ms: w4.rename_field(ms, 0, "TGT"))
    config = write(tmp_path, fields={"fcal": [0]})
    works(capsys, "flag", config, ms)
    works(capsys, "calibrate", config, ms)
    refused(capsys, "image", config, ms, "'TGT'", "field ids [0, 1]", "field id")
    works(capsys, "image", write(tmp_path, "id.yaml", image={"fields": [1]}), ms)


def test_a_field_id_without_a_field_row_is_refused(tmp_path, capsys):
    ms = twin(tmp_path, "stray", lambda ms: w4.stray_field_id(ms, "TGT", 2, 2))
    config = write(tmp_path)
    for command in ("check", *STAGES):
        refused(capsys, command, config, ms, "FIELD_ID 2", "no FIELD row")


def test_empty_selections_are_refused_before_anything_is_written(tmp_path, capsys):
    ms = twin(tmp_path, "x", lambda ms: w4.add_empty_field(ms, "EMPTY"))
    works(capsys, "check", write(tmp_path), ms)
    for name, extra, command in (
        ("i.yaml", {"image": {"fields": ["EMPTY"]}}, "image"),
        ("c.yaml", {"fields": {"fcal": ["EMPTY"]}}, "calibrate"),
        ("f.yaml", {"flag": {"fields": ["EMPTY"]}}, "flag"),
    ):
        refused(capsys, command, write(tmp_path, name, **extra), ms, "EMPTY", "no rows")
    none = write(tmp_path, "s.yaml", data={"scans": [99]})
    for command in ("flag", "calibrate"):
        refused(capsys, command, none, ms, "scans [99]", "no rows")
    setjy = write(
        tmp_path,
        "m.yaml",
        data={"scans": [99]},
        calibrate={"model": {"source": "setjy"}},
    )
    refused(capsys, "calibrate", setjy, ms, "scans [99]")
    assert "MODEL_DATA" not in w4._columns(ms) and not flagversions.versions(ms)
    refused(capsys, "image", none, ms, "data.scans", "'TGT'", "scans [99]", "no rows")
    other = write(tmp_path, "o.yaml", data={"scans": [2]})
    refused(capsys, "calibrate", other, ms, "'CAL'", "scans [2]", "no rows")
    works(capsys, "flag", other, ms)
    # data.scans that hold every scan of the imaged field: gemclean images the
    # same rows either way, so image runs.
    works(capsys, "image", other, ms)


def test_unknown_fields_name_themselves(tmp_path, capsys):
    ms = twin(tmp_path, "x")
    refused(capsys, "image", write(tmp_path, image={"fields": ["NOPE"]}), ms, "NOPE")
    refused(capsys, "image", write(tmp_path, image={"fields": [9]}), ms, "field id 9")


def test_an_ms_without_rows_is_refused(tmp_path, capsys):
    ms = tmp_path / "empty.ms"
    w4.no_rows(twin(tmp_path, "x"), ms)
    for command in STAGES:
        code, err = run(capsys, command, write(tmp_path), ms)
        assert code == 2 and "no rows" in err


def test_a_fully_flagged_calibrator_fails_calibrate_clearly(tmp_path, capsys):
    ms = twin(tmp_path, "x", lambda ms: w4.flag_field(ms, "CAL"))
    config = write(tmp_path)
    works(capsys, "flag", config, ms)
    code, err = run(capsys, "calibrate", config, ms)
    assert code == 1 and "no valid solution" in err
    works(capsys, "image", config, ms)


# -- autocorrelations -------------------------------------------------------------


def test_autocorrelations_are_flagged_and_corrected_but_not_solved(tmp_path, capsys):
    base = twin(tmp_path, "base")
    autos = twin(tmp_path, "autos")
    nrow = w4.add_autos(autos)
    assert pipe.inspect_ms(autos)["autocorrelations"] == 4 * 40
    config = write(tmp_path)
    for ms in (base, autos):
        for command in ("flag", "calibrate", "apply"):
            works(capsys, command, config, ms)
    assert np.array_equal(column(autos, "FLAG")[:nrow], column(base, "FLAG"))
    assert same_store(autos, base)
    corrected = column(autos, "CORRECTED_DATA")
    assert np.array_equal(corrected[:nrow], column(base, "CORRECTED_DATA"))
    data, field = column(autos, "DATA")[nrow:], column(autos, "FIELD_ID")[nrow:]
    cal = field == 0
    assert np.isfinite(corrected[nrow:]).all()
    assert (corrected[nrow:][cal] != data[cal]).any(axis=(1, 2)).all()
    assert np.array_equal(corrected[nrow:][~cal], data[~cal])
    works(capsys, "image", config, autos)


# -- weights and flag columns -----------------------------------------------------


def test_missing_weights(tmp_path, capsys):
    pytest.importorskip("casacure")
    base = twin(tmp_path, "base")
    config = write(tmp_path)
    works(capsys, "calibrate", config, base)
    # A WEIGHT_SPECTRUM column with no cells written is taken as absent.
    undefined = twin(tmp_path, "undefined", w4.undefined_weight_spectrum)
    assert not pipe.inspect_ms(undefined)["weight_spectrum"]
    works(capsys, "calibrate", config, undefined)
    assert same_store(undefined, base)
    # gemclean falls back to WEIGHT there, as WSClean (task W6).
    works(capsys, "image", config, undefined)
    sigma = twin(tmp_path, "sigma", lambda ms: w4.remove_columns(ms, ["SIGMA"]))
    for command in ("flag", "calibrate", "apply", "image"):
        works(capsys, command, config, sigma)
    none = twin(tmp_path, "none", lambda ms: w4.remove_columns(ms, ["WEIGHT"]))
    works(capsys, "flag", config, none)
    refused(capsys, "calibrate", config, none, "WEIGHT_SPECTRUM or WEIGHT", "uniform")
    refused(capsys, "image", config, none, "WEIGHT_SPECTRUM or WEIGHT", "uniform")
    uniform = write(tmp_path, "u.yaml", data={"weights": "uniform"})
    works(capsys, "calibrate", uniform, none)
    works(capsys, "apply", uniform, none)
    works(capsys, "image", uniform, none)  # -unit-weights reads no weights (W6)


def test_uniform_imaging_weights_reach_gemclean_without_a_write(tmp_path, capsys):
    # Task W6: data.weights: uniform images with gemclean's -unit-weights, and
    # the MS is not written (research/w6-imaging-inputs.md).
    ms = twin(tmp_path, "x")
    before = w4.fingerprint(ms)
    config = write(tmp_path, data={"weights": "uniform", "scans": [2]})
    works(capsys, "image", config, ms, run_dir=tmp_path / "run")
    summary = yaml.safe_load((tmp_path / "run/image/summary.json").read_text())
    argv = summary["images"][0]["argv"]
    assert "-unit-weights" in argv and argv[argv.index("-scans") + 1] == "2"
    assert w4.fingerprint(ms) == before
    works(
        capsys, "calibrate", write(tmp_path, "c.yaml", data={"weights": "uniform"}), ms
    )


@pytest.mark.parametrize("name", ["FLAG_ROW", "FLAG"])
def test_missing_flag_columns_are_refused(tmp_path, capsys, name):
    pytest.importorskip("casacure")
    ms = twin(tmp_path, "x", lambda ms: w4.remove_columns(ms, [name]))
    for command in ("check", *STAGES):
        refused(capsys, command, write(tmp_path), ms, f"no {name} column", "required")


# -- correlations ---------------------------------------------------------------------


def test_two_correlations_flag_and_image_but_do_not_calibrate(tmp_path, capsys):
    ms = twin(tmp_path, "two", ncorr=2)
    pristine = tmp_path / "pristine.ms"
    shutil.copytree(ms, pristine)
    config = write(tmp_path)
    works(capsys, "flag", config, ms)
    assert np.array_equal(column(ms, "FLAG"), expected_flags(pristine, STRATEGY))
    for command in ("calibrate", "apply"):
        refused(capsys, command, config, ms, "XX, YY", "four correlations")
    works(capsys, "image", config, ms)


@pytest.mark.parametrize(
    ("ncorr", "codes", "words"),
    [
        (4, [5, 6, 7, 8], ["circular", "linear"]),
        (2, [5, 8], ["circular", "linear"]),
        (4, [9, 12, 10, 11], ["order", "XX, XY, YX, YY"]),
        (1, None, ["one correlation"]),
    ],
)
def test_other_correlations_are_refused(tmp_path, capsys, ncorr, codes, words):
    if ncorr == 1:
        four = twin(tmp_path, "four")
        ms = tmp_path / "one.ms"
        w4.reshape_corr(four, ms, [0])
    else:
        ms = twin(tmp_path, "x", lambda ms: w4.relabel_corr(ms, codes), ncorr=ncorr)
    config = write(tmp_path)
    for command in ("check", *STAGES):
        refused(capsys, command, config, ms, *words)
