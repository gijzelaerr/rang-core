"""Big-plan task DF5-O (research/df5o-deconv-oracles.md): the measures of
`examples/compare_df5o.py` on synthetic inputs, and, when the frozen run
`outputs/df5o-20261031-01` is present, the archive recomputed from it."""

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "outputs" / "df5o-20261031-01"
ARCHIVE = ROOT / "research" / "results" / "df5o-deconv-oracles.json"


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "examples" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare = _load("compare_df5o")
simulate = _load("simulate_df5_field")


def test_gaussian_component_sums_to_its_flux_and_has_its_width():
    sl, g = simulate.gaussian_image(512, 512, 24.0, 12.0, math.radians(30.0), 2e-3)
    assert g.sum() == pytest.approx(2e-3, rel=1e-12)
    # the half-maximum region of a sampled Gaussian has the FWHM's moments
    img = np.zeros((1024, 1024))
    img[sl] = g / g.max()
    fmaj, fmin, _ = simulate.psf_fwhm_pixels(img)
    assert fmaj == pytest.approx(12.0, rel=0.08)
    assert fmin == pytest.approx(6.0, rel=0.15)


def test_orientations_are_the_eight_square_symmetries():
    a = np.arange(12.0).reshape(3, 4)
    a = np.pad(a, ((0, 1), (0, 0)))  # square 4x4
    outs = {name: compare.orient(a, name) for name in compare.ORIENTATIONS}
    assert len({o.tobytes() for o in outs.values()}) == 8
    assert np.array_equal(outs["identity"], a)
    assert np.array_equal(outs["transpose-flipxy"], a.T[::-1, ::-1])


def test_aperture_flux_centroid_and_tolerances():
    field = {
        "noise": {"sigma_img_mfs_jy": 1e-6},
        "psf": {"fwhm_major_px": 10.0, "fwhm_minor_px": 8.0},
        "geometry": {"freqs_hz": [1e9, 1.2e9, 1.4e9, 1.6e9]},
    }
    truth = {
        "nu0_hz": 1.2e9,
        "sources": [{"name": "p", "kind": "point", "x": 100, "y": 200, "radius": 20.0}],
    }
    freqs = np.array(field["geometry"]["freqs_hz"])
    flux = 1e-3 * (freqs / 1.2e9) ** -0.7
    t = np.zeros((4, 1024, 1024))
    t[:, 200, 100] = flux
    m = t.copy()
    m[:, 200, 100] *= 0.6
    m[:, 200, 101] = 0.4 * flux  # flux split over two pixels, half a pixel off
    m[:, 600, 600] = 5e-6  # spurious
    rows, spurious, outside = compare.score_sources(m, t, field, truth)
    (row,) = rows
    assert row["s_model_jy"] == pytest.approx(row["s_truth_jy"], rel=1e-12)
    assert row["offset_arcsec"] == pytest.approx(0.4 * compare.CELL, rel=1e-9)
    assert row["alpha_truth"] == pytest.approx(-0.7, abs=1e-9)
    assert spurious["positive_jy"] == pytest.approx(5e-6)
    assert not outside[200, 100]
    totals = {"model_mfs_jy": m.mean(0).sum(), "truth_mfs_jy": t.mean(0).sum()}
    tol = compare.tolerances(rows, totals, field)
    assert tol["A1"] and tol["A1_components_tested"] == 1
    assert tol["A2"]  # 0.8 arcsec is within 0.1 of a 20 arcsec beam
    m[:, 200, 101] = 0.0
    m[:, 200, 103] = 0.4 * flux  # now 1.2 px = 2.4 arcsec off: beyond 2 arcsec
    rows, _, _ = compare.score_sources(m, t, field, truth)
    assert not compare.tolerances(rows, totals, field)["A2"]


def test_acceptance_bounds_take_the_best_matched_oracle_and_the_spread():
    def arm(rms, red, s):
        runs = {
            "1": {"exact_residual": {"rms_inner_jy": rms}, "reducible_fraction": red}
        }
        return {"runs": runs, "spread": {"rms_inner_jy": s, "reducible_fraction": 0.0}}

    arms = {"ws-hogbom": arm(2e-6, 1e-3, 1e-8), "pfb-clark": arm(3e-6, 2e-3, 0.0)}
    acc = compare.acceptance(arms)["hogbom"]
    assert acc["A3_rms_inner_bound_jy"] == pytest.approx(2e-6 + 0.02 * 2e-6)
    assert acc["A4_reducible_bound"] == pytest.approx(1e-3 * 1.02)


needs_run = pytest.mark.skipif(
    not (RUN / "field" / "field.npz").exists() or not ARCHIVE.exists(),
    reason="the DF5-O run outputs/df5o-20261031-01 (ignored) is not on this host",
)


@needs_run
def test_field_hashes_match_the_archive():
    archive = json.loads(ARCHIVE.read_text())
    for name, digest in archive["field"]["hashes"]["files"].items():
        h = hashlib.sha256((RUN / "field" / name).read_bytes()).hexdigest()
        assert h == digest, name


@needs_run
def test_measures_recomputed_from_the_outputs_equal_the_archive():
    archive = json.loads(ARCHIVE.read_text())
    field, truth, arrays = compare.load_field(RUN / "field")
    arm_dir = RUN / "wsclean" / "ws-hogbom-r1"
    models, _, _ = compare.wsclean_outputs(arm_dir, "ws-hogbom")
    rec = archive["arms"]["ws-hogbom"]["runs"]["1"]
    assert models.mean(0).sum() == pytest.approx(
        rec["totals"]["model_mfs_jy"], rel=1e-12
    )
    res, q = compare.exact_residual(models, arrays)
    stats = compare.image_stats(res.mean(0), field["noise"]["sigma_img_mfs_jy"])
    assert stats["rms_inner_jy"] == pytest.approx(
        rec["exact_residual"]["rms_inner_jy"], rel=1e-9
    )
    assert float(q.mean()) == pytest.approx(rec["q"], rel=1e-9)
    rows, _, _ = compare.score_sources(models, arrays["truth_cube"], field, truth)
    for got, want in zip(rows, rec["sources"], strict=True):
        assert got["s_model_jy"] == pytest.approx(
            want["s_model_jy"], rel=1e-12, abs=1e-15
        )
