import inspect
import json
import math
import re
from pathlib import Path

import numpy as np
import pytest
from rangtoy import core_imaging, core_weights

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "recipes" / "core-imaging.yaml"


def test_classification_follows_the_frozen_rules():
    classify = core_imaging.classify_replay
    assert (
        classify(
            ["jobs", "omitted-total", "known_family_dirty_fit", "coefficients_jy", 0]
        )
        == "template_flux"
    )
    assert classify(["reference_fit", "coefficients_jy", 1]) == "template_flux"
    assert (
        classify(
            ["jobs", "unit-extended", "known_family_dirty_fit", "coefficients_jy", 0]
        )
        == "unit_flux"
    )
    assert (
        classify(["jobs", "omitted-total", "conditional_response_vs_fixedG0", 1])
        == "response_fraction"
    )
    assert classify(["jobs", "x", "PSF_linf_difference_vs_fixedG0"]) == "psf_linf"
    assert classify(["jobs", "x", "headers", "dirty", "WSCVWSUM"]) == "weight_sum"
    assert classify(["jobs", "x", "image_geometry", "CRVAL1"]) == "wcs"
    assert classify(["jobs", "x", "image_geometry", "CRPIX1"]) == "exact"
    assert classify(["dirty_image_closures_jy_per_beam", "omitted"]) == "closure"
    assert (
        classify(["jobs", "x", "diagnostics", "dirty_offsource_RMS_jy_per_beam"])
        == "reported"
    )
    for key in ("BMAJ", "WSCVERSI", "training_additions", "FITS_sha256"):
        assert classify(["jobs", "x", "headers", "psf", key]) == "excluded"
    assert classify(["precast_visibility_closures_jy", "omitted"]) == "excluded"
    assert classify(["jobs", "x", "role"]) == "exact"


def _archive():
    return {
        "settings": {"size": [512, 512], "robust": 0.5},
        "jobs": {
            "omitted-total": {
                "role": "response",
                "seconds_emulated_not_native_benchmark": 2.5,
                "headers": {
                    "dirty": {"WSCVWSUM": 1000.0, "WSCNVIS": 9169, "BMAJ": 0.25}
                },
                "image_geometry": {"CRPIX1": 257, "CRVAL1": -65.1457083333333},
                "diagnostics": {
                    "dirty_offsource_RMS_jy_per_beam": 0.013,
                    "fixed_offsource_pixels": 146406,
                },
                "PSF_linf_difference_vs_fixedG0": 0,
                "known_family_dirty_fit": {
                    "coefficients_jy": [0.0295, 0.0931],
                    "rank": 2,
                },
                "conditional_response_vs_fixedG0": [0.4917, 0.7757],
            },
            "unit-extended": {
                "known_family_dirty_fit": {"coefficients_jy": [6e-17, 1.0]},
            },
        },
        "reference_fit": {"coefficients_jy": [0.06, 0.12], "condition": 1.9956},
        "dirty_image_closures_jy_per_beam": {"omitted": 3.5e-8},
    }


def test_compare_replay_passes_within_the_tolerances_and_reports():
    archive = _archive()
    core = json.loads(json.dumps(archive))
    job = core["jobs"]["omitted-total"]
    del job["seconds_emulated_not_native_benchmark"]
    del job["headers"]["dirty"]["BMAJ"]
    job["headers"]["dirty"]["WSCVWSUM"] *= 1 + 5e-10
    job["image_geometry"]["CRVAL1"] += 5e-10
    job["diagnostics"]["dirty_offsource_RMS_jy_per_beam"] = 0.0131
    job["PSF_linf_difference_vs_fixedG0"] = 1e-7
    job["known_family_dirty_fit"]["coefficients_jy"] = [0.0295 * (1 + 4e-6), 0.0931]
    job["conditional_response_vs_fixedG0"] = [0.4917 + 1e-7, 0.7757]
    core["jobs"]["unit-extended"]["known_family_dirty_fit"]["coefficients_jy"] = [
        -3e-7,
        1.0,
    ]
    core["dirty_image_closures_jy_per_beam"]["omitted"] = 2e-8
    report = core_imaging.compare_replay(archive, core)
    assert report["passed"], report["failures"]
    classes = report["classes"]
    assert classes["exact"]["compared"] == 8
    assert classes["template_flux"]["compared"] == 4
    assert math.isclose(classes["template_flux"]["worst"], 4e-6, rel_tol=1e-6)
    assert (
        classes["unit_flux"]["compared"] == 2 and classes["unit_flux"]["worst"] > 2.9e-7
    )
    assert classes["response_fraction"]["compared"] == 2
    assert classes["closure"]["compared"] == 1 and classes["closure"][
        "worst"
    ] == pytest.approx(1.5e-8)
    assert classes["reported"]["worst_path"] == [
        "jobs",
        "omitted-total",
        "diagnostics",
        "dirty_offsource_RMS_jy_per_beam",
    ]
    assert report["excluded"] == 2


def test_compare_replay_fails_on_missing_fields_tolerances_and_closures():
    archive = _archive()
    core = json.loads(json.dumps(archive))
    del core["jobs"]["omitted-total"]["role"]
    core["reference_fit"]["coefficients_jy"] = [0.06 * (1 + 5e-6), 0.12]
    core["jobs"]["omitted-total"]["conditional_response_vs_fixedG0"] = [
        0.4917 + 2e-7,
        0.7757,
    ]
    core["dirty_image_closures_jy_per_beam"]["omitted"] = 2e-6
    report = core_imaging.compare_replay(archive, core)
    reasons = {
        tuple(f["path"]): f.get("class", f.get("reason")) for f in report["failures"]
    }
    assert reasons[("jobs", "omitted-total", "role")] == "missing"
    assert reasons[("reference_fit", "coefficients_jy", 0)] == "template_flux"
    assert (
        reasons[("jobs", "omitted-total", "conditional_response_vs_fixedG0", 0)]
        == "response_fraction"
    )
    assert reasons[("dirty_image_closures_jy_per_beam", "omitted")] == "closure"
    assert len(report["failures"]) == 4


def test_pixel_record_separates_centre_and_border_and_gates_wcs():
    reference = np.zeros((8, 8))
    reference[4, 4] = 2.0
    candidate = reference.copy()
    candidate[0, 0] = 1e-3
    header = {
        "CRPIX1": 5,
        "CRPIX2": 5,
        "CRVAL1": 1.0,
        "CRVAL2": 2.0,
        "CDELT1": -0.1,
        "CDELT2": 0.1,
        "CTYPE1": "RA---SIN",
        "CTYPE2": "DEC--SIN",
    }
    record = core_imaging.pixel_record(reference, header, candidate, header)
    assert record["max_abs_difference"] == 1e-3
    assert record["max_relative_to_peak"] == 5e-4
    assert (
        record["central_rms_difference"] == 0.0 and record["border_rms_difference"] > 0
    )
    assert record["argmax_difference"] == [0, 0] and record["wcs_equal"]
    other = {**header, "CRVAL1": 1.0 + 1e-6}
    assert not core_imaging.pixel_record(reference, header, candidate, other)[
        "wcs_equal"
    ]
    with pytest.raises(ValueError):
        core_imaging.pixel_record(reference, header, candidate[:4], header)


def test_image_job_runs_the_core_chain_on_a_small_grid():
    rng = np.random.default_rng(20261029)
    nrow, nchan = 12, 3
    uvw = rng.normal(0, 60.0, (nrow, 3))
    frequencies = np.array([1.0e9, 1.05e9, 1.1e9])
    data = np.zeros((nrow, nchan, 4), np.complex64)
    data[..., 0] = data[..., 3] = 1.0
    checkpoint = {
        "CORRECTED_DATA": data,
        "FLAG": np.zeros((nrow, nchan, 4), bool),
        "FLAG_ROW": np.zeros(nrow, bool),
    }
    checkpoint["FLAG"][0, 1, 3] = True
    checkpoint["FLAG_ROW"][1] = True
    inputs = {
        "UVW": uvw,
        "WEIGHT_SPECTRUM": np.ones((nrow, nchan, 4), np.float32),
        "CHAN_FREQ": frequencies,
        "PHASE_DIR": np.array([1.0, -0.5]),
        "rows": np.ones(nrow, bool),
        "nrow": nrow,
    }
    inputs["rows"][2] = False
    grid = {
        **core_imaging.GRID,
        "width": 32,
        "height": 32,
        "scale_arcsec": 120.0,
        "w_layers": 4,
    }
    products = core_imaging.image_job(inputs, checkpoint, grid=grid, channels=(0, 3))
    stats = products["stats"]
    assert products["dirty"].shape == (32, 32) and products["psf"].shape == (32, 32)
    assert products["psf"][16, 16] == pytest.approx(1.0, abs=1e-12)
    assert stats["gridded_count"] == (nrow - 2) * nchan - 1
    # WSClean's weight grid ignores FLAG_ROW (task B); its gridder skips the
    # row (task C), so the weight count exceeds the gridded count by a row.
    assert products["imaging_weight_sums"]["count"] == (nrow - 1) * nchan - 1
    assert 0 < stats["image_weight"] < products["imaging_weight_sums"]["total_weight"]
    assert set(products["seconds"]) == {"stokes_and_weights", "grid"}
    assert core_weights.padded_size(32, grid["padding"]) == 40


def test_main_dispatches_run_and_compare(monkeypatch):
    calls = {}
    monkeypatch.setattr(core_imaging, "run", lambda *a: calls.setdefault("run", a))
    monkeypatch.setattr(
        core_imaging, "compare", lambda *a: calls.setdefault("compare", a)
    )
    core_imaging.main(["run", "out", "--archive-dir", "arc", "--export-dir", "exp"])
    assert calls["run"] == ("out", "arc", "exp")
    core_imaging.main(["compare", "res.json", "rec.json", "--images", "cand", "ref"])
    assert calls["compare"] == (
        "res.json",
        str(core_imaging.DEFAULT_ORACLE),
        "rec.json",
        "cand",
        "ref",
    )
    with pytest.raises(SystemExit):
        core_imaging.main(["unknown"])


def test_compare_writes_a_receipt_and_exits_on_failure(tmp_path):
    archive = _archive()
    (tmp_path / "oracle.json").write_text(json.dumps({"raw_result": archive}))
    (tmp_path / "result.json").write_text(json.dumps(archive))
    report = core_imaging.compare(
        tmp_path / "result.json", tmp_path / "oracle.json", tmp_path / "receipt.json"
    )
    assert (
        report["passed"]
        and json.loads((tmp_path / "receipt.json").read_text())["passed"]
    )
    broken = json.loads(json.dumps(archive))
    broken["reference_fit"]["coefficients_jy"][0] *= 1.001
    (tmp_path / "result.json").write_text(json.dumps(broken))
    with pytest.raises(SystemExit):
        core_imaging.compare(
            tmp_path / "result.json",
            tmp_path / "oracle.json",
            tmp_path / "receipt.json",
        )
    assert not json.loads((tmp_path / "receipt.json").read_text())["passed"]
    with pytest.raises(ValueError):
        core_imaging.compare(
            tmp_path / "result.json",
            tmp_path / "oracle.json",
            tmp_path / "r.json",
            "only-one",
        )


def test_recipe_cabs_match_the_module_signatures_and_name_no_imager():
    text = RECIPE.read_text()
    assert "_include: core-cabs.yaml" in text
    assert "backend: {select: native}" in text
    assert "DEFAULT: core-imaging" in text
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    assert "wsclean" not in code.lower() and "quartical" not in code.lower()
    pattern = re.compile(
        r"^  (?P<cab>rang-core-imaging[\w-]*):\n(?P<body>(?:    .*\n)+)", re.MULTILINE
    )
    seen = set()
    for match in pattern.finditer(text):
        body = match.group("body")
        command = re.search(r"command: (\S+)", body).group(1)
        module, function = command.rsplit(".", 1)
        assert module == "rangtoy.core_imaging"
        parameters = inspect.signature(getattr(core_imaging, function)).parameters
        names = re.findall(r"\n      ([\w]+): \{", body)
        assert set(names) == set(parameters), (match.group("cab"), function)
        seen.add(function)
    assert seen == {"run", "compare"}
    assert "rang-core-environment" in text
