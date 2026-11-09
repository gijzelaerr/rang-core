"""Task C5b (research/c5b-selfcal-masks.md): CARACal's per-image clean
masks and cut-offs in `rang-core selfcal` (`selfcal.clean_cutoff`,
`cleanmask_method`, `cleanmask_thr`), their validation, the gemclean
arguments of each image, and the stage with a portable stand-in gemclean.
"""

import importlib.util
import json
import os
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest
from rang import core_cli, core_config
from rang import core_pipeline as pipe

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "test_c5_selfcal", ROOT / "tests/test_c5_selfcal.py"
)
c5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c5)


def _resolved(text):
    raw = core_config._yaml().safe_load(textwrap.dedent(text))
    return core_config.resolve(raw)


BASE = """\
    version: 1
    image: {size: 64, scale: 2asec, mgain: 0.9}
    """


def argv_of(config, k, field="TGT"):
    img = core_config.selfcal_image_settings(config, k, field)
    return pipe.gemclean_arguments(img, "DATA", 0, "x/image", "x.ms")


def test_the_index_is_caracals_last_repeating():
    # CARACal: values[num - 1 if len(values) >= num else -1], num = 1 .. cal_niter + 1
    values = [10.0, 6.0]
    got = [core_config.selfcal_image_index(values, k) for k in (1, 2, 3, 4)]
    assert got == [10.0, 6.0, 6.0, 6.0]
    assert core_config.selfcal_image_index([], 1) is None
    assert core_config.selfcal_image_index(["a"], 3) == "a"


def test_empty_lists_give_c5s_arguments_unchanged():
    config, errors = _resolved(BASE.replace("mgain: 0.9", "auto_mask: 5, mgain: 0.8"))
    assert errors == []
    for k in (1, 2, 3):
        assert core_config.selfcal_image_settings(config, k) == config["image"]
        assert argv_of(config, k) == pipe.gemclean_arguments(
            config["image"], "DATA", 0, "x/image", "x.ms"
        )
    assert core_config.refusals(config, ["selfcal"]) == []


def test_caracals_defaults_per_image():
    config, errors = _resolved(
        BASE
        + "selfcal: {rounds: 2, cleanmask_method: [wsclean], cleanmask_thr: [10, 6], "
        "clean_cutoff: [0.5]}\n"
    )
    assert errors == []
    assert core_config.refusals(config, ["selfcal"]) == []

    def opt(argv, flag):
        return argv[argv.index(flag) + 1] if flag in argv else None

    one, two, final = (argv_of(config, k) for k in (1, 2, 3))
    assert (opt(one, "-auto-mask"), opt(one, "-auto-threshold")) == ("10.0", "0.5")
    assert (opt(two, "-auto-mask"), opt(two, "-auto-threshold")) == ("6.0", "0.5")
    assert (opt(final, "-auto-mask"), opt(final, "-auto-threshold")) == ("6.0", "0.5")
    assert "-fits-mask" not in one


def test_none_and_a_fits_path_replace_the_image_mask(tmp_path):
    config, errors = _resolved(
        BASE.replace("mgain: 0.9", "mgain: 0.9, auto_mask: 7, auto_threshold: 2")
        + "selfcal: {rounds: 2, cleanmask_method: [none, 'm/{field}.fits', wsclean], "
        "cleanmask_thr: [5]}\n"
    )
    assert errors == []
    assert core_config.refusals(config, ["selfcal"]) == []
    one, two, final = (argv_of(config, k) for k in (1, 2, 3))
    assert "-auto-mask" not in one and "-fits-mask" not in one
    assert "-auto-threshold" in one  # the image section's 2.0
    assert two[two.index("-fits-mask") + 1] == "m/TGT.fits" and "-auto-mask" not in two
    assert final[final.index("-auto-mask") + 1] == "5.0"


def test_errors_and_refusals():
    _, errors = _resolved(
        BASE
        + "selfcal: {rounds: 1, clean_cutoff: [1, 1, 1], cleanmask_method: [sofa], "
        "cleanmask_thr: [-1]}\n"
    )
    paths = [p for p, _ in errors]
    assert "selfcal.clean_cutoff" in paths  # three entries for two images
    assert "selfcal.cleanmask_method[0]" in paths
    assert "selfcal.cleanmask_thr[0]" in paths

    def refused(text):
        config, errors = _resolved(text)
        assert errors == []
        return {r.path: r.text for r in core_config.refusals(config, ["selfcal"])}

    got = refused(BASE + "selfcal: {cleanmask_method: [sofia]}\n")
    assert "not ported" in got["selfcal.cleanmask_method[0]"]
    got = refused(BASE + "selfcal: {cleanmask_method: [none], cleanmask_thr: [6]}\n")
    assert "selfcal.cleanmask_thr" in got
    got = refused(BASE + "selfcal: {cleanmask_method: [wsclean]}\n")
    assert "needs cleanmask_thr" in got["selfcal.cleanmask_thr"]
    got = refused(
        BASE.replace(", mgain: 0.9", "")
        + "selfcal: {cleanmask_method: [wsclean], cleanmask_thr: [6]}\n"
    )
    assert got["selfcal.cleanmask_method"].startswith("image 1:")
    got = refused(
        BASE + "selfcal: {cleanmask_method: [wsclean], cleanmask_thr: [10, 3], "
        "clean_cutoff: [3]}\n"
    )
    assert got["selfcal.clean_cutoff"].startswith("image 2:")  # 3 >= 3 from image 2


def fake_gemclean(tmp_path):
    """A portable stand-in: copies a model template to `<name>-model.fits`,
    writes `<name>-image.fits` and prints gemclean's summary line."""
    template = tmp_path / "template-model.fits"
    image = np.zeros((32, 32))
    image[16, 16] = c5.FLUX
    c5.g6.write_fits(template, image, 2.0 / 3600, c5.CENTRE)
    script = tmp_path / "fake-gemclean.py"
    script.write_text(
        "import shutil, sys\n"
        "a = sys.argv[1:]\n"
        "name = a[a.index('-name') + 1]\n"
        f"shutil.copy({str(template)!r}, name + '-model.fits')\n"
        "open(name + '-image.fits', 'w').write('fake\\n')\n"
        "print('12 components, 3 major cycles, 0 resyncs, stop Threshold; Q/Q0 1e-3')\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        path = tmp_path / "fake-gemclean.cmd"
        path.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        path = tmp_path / "fake-gemclean"
        path.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8"
        )
        path.chmod(0o755)
    return path


def test_the_stage_passes_each_images_settings(tmp_path):
    ms, _, _ = c5.make_ms(tmp_path / "x.ms", "pa")
    gem = fake_gemclean(tmp_path).as_posix()
    text = textwrap.dedent(
        f"""\
        version: 1
        fields: {{target: [TGT]}}
        image: {{gemclean: '{gem}', size: 32, scale: 2asec, mgain: 0.9}}
        selfcal:
          rounds: 2
          terms: [{{type: Sp, solint: 3}}, {{type: Sa, solint: 3}}]
          refant: m001
          input_column: DATA
          cleanmask_method: [wsclean]
          cleanmask_thr: [10, 6]
          clean_cutoff: [0.5]
        """
    )
    config = tmp_path / "config.yaml"
    config.write_text(text, encoding="utf-8")
    core_cli.dispatch(["selfcal", str(config), str(ms)])
    run = Path(str(ms) + ".rang-run")
    summary = json.loads((run / "selfcal" / "summary.json").read_text())
    (field,) = summary["fields"]
    images = [r["image"] for r in field["rounds"]] + [field["final_image"]]
    assert [i["image"] for i in images] == [1, 2, 3]
    assert [i["auto_mask"] for i in images] == [10.0, 6.0, 6.0]
    assert [i["auto_threshold"] for i in images] == [0.5, 0.5, 0.5]
    for i in images:
        argv = i["argv"]
        assert argv[argv.index("-auto-mask") + 1] == repr(i["auto_mask"])
        assert i["clean"] == {"components": 12, "major_cycles": 3, "stop": "Threshold"}


@pytest.mark.parametrize(
    "line, want",
    [
        (
            "120 components, 4 major cycles, 7 resyncs, stop Components; Q/Q0 0.1",
            {"components": 120, "major_cycles": 4, "stop": "Components"},
        ),
        (
            "joined: 5 components, 2 major cycles, 1 resyncs, stop Threshold; Q/Q0 1",
            {"components": 5, "major_cycles": 2, "stop": "Threshold"},
        ),
        ("no summary here", None),
    ],
)
def test_the_stop_line_is_read(tmp_path, line, want):
    log = tmp_path / "gemclean.log"
    log.write_text("argv\n" + line + "\n", encoding="utf-8")
    assert pipe.gemclean_stop(log) == want
