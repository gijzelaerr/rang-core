import numpy as np
import pytest
from rangtoy import imaging_sensitivity as sens

COMMAND = [
    "/usr/bin/wsclean",
    "-name",
    "/old/images/job",
    "-size",
    "512",
    "512",
    "-gridder",
    "wstacking",
    "-wstack-nwlayers",
    "64",
    "-j",
    "1",
    "-temp-dir",
    "/old/temp",
    "/old/work.ms",
]


def test_variant_grid_is_frozen():
    grid = sens.variants()
    assert len(grid) == 19
    assert grid["default"] == sens.DEFAULTS
    assert all(v["kernel_size"] % 2 == 1 for v in grid.values())
    assert set(sens.ADJACENT) <= set(grid)
    assert grid["coarse-3-63-1"] == {
        "kernel_size": 3,
        "oversampling": 63,
        "w_layers": 1,
    }


def test_variant_command_moves_paths_and_sets_only_gridding_options():
    out = sens.variant_command(
        COMMAND,
        {"kernel_size": 9, "oversampling": 255, "w_layers": 8},
        "/new/x",
        "/t",
        "/new.ms",
    )
    assert out[:3] == ["/usr/bin/wsclean", "-name", "/new/x"]
    assert out[-1] == "/new.ms"
    assert out.count("-wstack-nwlayers") == 1
    assert out[out.index("-wstack-nwlayers") + 1] == "8"
    assert out[out.index("-wstack-kernel-size") + 1] == "9"
    assert out[out.index("-wstack-oversampling") + 1] == "255"
    assert out[out.index("-temp-dir") + 1] == "/t"
    assert "/old/temp" not in out and "/old/images/job" not in out
    assert out[3:8] == ["-size", "512", "512", "-gridder", "wstacking"]


@pytest.mark.parametrize(
    "bad", [{"kernel_size": 8}, {"oversampling": 0}, {"w_layers": 0}]
)
def test_variant_command_rejects_invalid_settings(bad):
    with pytest.raises(ValueError):
        sens.variant_command(COMMAND, {**sens.DEFAULTS, **bad}, "/n", "/t", "/n.ms")


def test_pixel_digest_ignores_dtype_but_not_values():
    image = np.arange(16, dtype=float).reshape(4, 4)
    assert sens.pixel_digest(image) == sens.pixel_digest(image.astype(np.float32))
    assert sens.pixel_digest(image) != sens.pixel_digest(image + 1e-6)


def test_reproduction_classes():
    assert sens.classify_reproduction(["jobs", "a", "FITS_sha256"]) == "excluded"
    assert (
        sens.classify_reproduction(
            ["jobs", "a", "seconds_emulated_not_native_benchmark"]
        )
        == "excluded"
    )
    assert (
        sens.classify_reproduction(
            ["jobs", "a", "known_family_dirty_fit", "coefficients_jy"]
        )
        == "difference"
    )
    assert (
        sens.classify_reproduction(
            ["jobs", "a", "diagnostics", "dirty_offsource_RMS_jy_per_beam"]
        )
        == "float"
    )
    assert (
        sens.classify_reproduction(["precast_visibility_closures_jy", "omitted"])
        == "reported"
    )
    assert (
        sens.classify_reproduction(["jobs", "a", "headers", "dirty", "WSCNVIS"])
        == "exact"
    )


def test_compare_reproduction_passes_on_header_and_timing_noise_only():
    archived = {
        "jobs": {
            "a": {
                "FITS_sha256": {"dirty": "x"},
                "seconds_emulated_not_native_benchmark": 1.0,
                "headers": {"dirty": {"WSCNVIS": 9169.0, "BMAJ": 0.25}},
                "known_family_dirty_fit": {"coefficients_jy": [0.06, 0.0]},
            }
        },
        "precast_visibility_closures_jy": {"omitted": 1e-14},
    }
    rerun = {
        "jobs": {
            "a": {
                "FITS_sha256": {"dirty": "y"},
                "seconds_emulated_not_native_benchmark": 2.0,
                "headers": {"dirty": {"WSCNVIS": 9169.0, "BMAJ": 0.25}},
                "known_family_dirty_fit": {"coefficients_jy": [0.06, -1e-17]},
            }
        },
        "precast_visibility_closures_jy": {"omitted": 2e-14},
    }
    report = sens.compare_reproduction(archived, rerun)
    assert report["failures"] == []
    rerun["jobs"]["a"]["headers"]["dirty"]["WSCNVIS"] = 9168.0
    assert len(sens.compare_reproduction(archived, rerun)["failures"]) == 1


def _fake_results(scale):
    """Default and one variant whose every number moves by `scale`."""

    def one(delta):
        jobs = {}
        for job in sens.JOBS:
            jobs[job] = {
                "pixels": {
                    "dirty": {"linf": delta, "linf_relative_to_peak": delta / 2},
                    "psf": {"linf": delta / 4},
                },
                "diagnostics": {"dirty_offsource_RMS_jy_per_beam": 1.0 + delta},
                "beam": {"BMAJ": 1.0 + delta, "BMIN": 0.5, "BPA": 90.0},
                "weights": {"WSCVWSUM": 1.0},
            }
            if job in sens.FITTED_JOBS:
                jobs[job]["known_family_dirty_fit"] = {
                    "available": True,
                    "coefficients_jy": [0.1 * (1 + delta), 0.2],
                }
                jobs[job]["conditional_response_vs_fixedG0"] = [1.0 + delta, 1.0]
        return {
            "jobs": jobs,
            "reference_fit": {"coefficients_jy": [0.06, 0.12 * (1 + delta)]},
            "dirty_image_closures_jy_per_beam": {"omitted": 1e-8, "complete": 1e-8},
        }

    results = {"default": one(0.0)}
    for i, name in enumerate(sens.ADJACENT):
        results[name] = one(scale * (i + 1))
    return results


def test_spread_and_tolerance_rule():
    table = sens.spread(_fake_results(1e-3))
    assert set(table) == set(sens.ADJACENT)
    row = table["kernel-5"]
    assert row["max_relative_flux_change"] == pytest.approx(1e-3)
    assert row["max_absolute_response_change"] == pytest.approx(1e-3)
    assert row["max_dirty_linf_jy_per_beam"] == pytest.approx(1e-3)
    assert row["max_psf_linf"] == pytest.approx(2.5e-4)
    assert row["weight_headers_equal_default"] is True
    proposal = sens.proposed_tolerances(table)
    assert proposal["dirty_pixel_linf_relative_to_peak"] == pytest.approx(5e-5)
    assert proposal["psf_pixel_linf"] == pytest.approx(2.5e-5)
    assert proposal["template_flux_relative"] == pytest.approx(1e-4)
    assert proposal["weight_sums_relative"] == 1e-9


def test_tolerance_rule_floors_at_float32_resolution():
    table = sens.spread(_fake_results(1e-9))
    proposal = sens.proposed_tolerances(table)
    assert proposal["dirty_pixel_linf_relative_to_peak"] == 2.0**-23
    assert proposal["smallest_adjacent"]["template_flux_relative"] == pytest.approx(
        1e-9
    )


def test_tolerance_rule_requires_all_adjacent_variants():
    table = sens.spread(_fake_results(1e-3))
    del table["wlayers-128"]
    with pytest.raises(ValueError):
        sens.proposed_tolerances(table)
