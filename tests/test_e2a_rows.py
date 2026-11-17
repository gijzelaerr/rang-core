# SPDX-License-Identifier: MIT
"""E2-A's oracle arms and rows (research/e2-acceptance.md 9.11): the CASA 3b
task list, the flux row's configuration and bins, the off-source rms shared by
the self-calibration and target rows, and the K limit. Stand-ins only; the
smoke on A1 small is in the note."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1] / "research/results/e2-acceptance-scripts"
sys.path.insert(0, str(HERE))


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rows = load("e2_rows_a")
casa = load("e2_casa3b_a")


def test_casa_calls_follow_e2a_yaml():
    calls = casa.casa_calls("/c/e2a.ms", "m022,m023,m024")
    assert calls[0]["task"] == "setjy" and calls[0]["args"]["usescratch"] is False
    tables = {c["args"]["caltable"].rsplit("/", 1)[1]: c for c in calls[1:]}
    assert list(tables) == list(casa.TERMS)
    pre = {
        n: [g.rsplit("/", 1)[1] for g in c["args"]["gaintable"]]
        for n, c in tables.items()
    }
    assert pre == {"K0": [], "G0": ["K0"], "B0": ["K0", "G0"], "K1": ["G0", "B0"],
                   "G1": ["K1", "B0"], "B1": ["K1", "G1"]}  # fmt: skip
    for n, c in tables.items():
        a = c["args"]
        assert a["field"] == "J1939-6342" and a["refant"] == "m022,m023,m024"
        assert ("uvrange" in a) == (n[0] != "K")  # K without uvrange, as E2-B
        assert a["solint"] == {"K0": "inf", "G0": "inf", "B0": "inf", "K1": "60s",
                               "G1": "60s", "B1": "inf"}[n]  # fmt: skip
        if n[0] == "B":
            assert (
                a["combine"] == "scan" and a["fillgaps"] == 70 and a["solnorm"] is False
            )
        if n[0] == "G":
            assert a["calmode"] == "ap" and a["refantmode"] == "flex"


def test_flux_config_edits_once():
    text = (HERE / "e2a-rerun.yaml").read_text(encoding="utf-8")
    out = rows.flux_config(text)
    assert "  scans: [9]\n" in out and "  stages: [calibrate]\n" in out
    assert out.count("\n") == text.count("\n")
    assert (
        rows.flux_config(
            text.replace("[9, 10, 11]", "[1, 4, 23]"), "1,4,23", "1"
        ).count("  scans: [1]\n")
        == 1
    )
    with pytest.raises(SystemExit):
        rows.flux_config(text.replace("  scans: [9, 10, 11]\n", ""))


def test_flux_bins():
    freq = np.linspace(856e6, 1711.8e6, 4096)
    model = 15.0 * (freq / 1.4e9) ** -0.7
    n = np.full(4096, 50)
    n[freq < 956e6] = 2  # a heavily flagged first bin: not counted
    total = 100
    s = model * n * 1.01
    s[(freq >= 1256e6) & (freq < 1356e6)] *= 0.97 / 1.01  # one bin 3 % low
    bins = rows.flux_bins(freq, s, n, total, model)
    assert len(bins) == 9 and not bins[0]["counted"]
    assert bins[1]["median_ratio"] == pytest.approx(1.01) and bins[1]["met"]
    low = [b for b in bins if abs(b["lo_mhz"] - 1256) < 1]
    assert low[0]["counted"] and not low[0]["met"]
    assert bins[1]["unflagged_fraction"] == pytest.approx(0.5)


def test_offsource_masks_sources_and_keeps_the_radius():
    fits = pytest.importorskip("astropy.io.fits")
    n = 200
    h = fits.Header()
    for k, v in (("CRPIX1", 101), ("CRPIX2", 101), ("CDELT1", -0.01), ("CDELT2", 0.01),
                 ("BMAJ", 0.03)):  # fmt: skip
        h[k] = v
    rng = np.random.default_rng(1)
    a = rng.normal(0, 1e-3, (n, n))
    b = a * 1.1
    for img in (a, b):
        img[100, 120] += 1.0  # a source inside 0.7 deg, masked
        img[10, 10] += 5.0  # beyond 0.7 deg: neither rms nor peak sees it
    arms, info = rows.offsource([(a, h), (b, h)], a)
    assert arms[0]["peak_jy"] == pytest.approx(1.0, abs=0.01)
    assert arms[1]["rms_jy"] / arms[0]["rms_jy"] == pytest.approx(1.1, rel=1e-6)
    assert arms[0]["rms_jy"] == pytest.approx(1e-3, rel=0.05)
    assert info["masked"] > 0


def test_k_limit():
    s3b = load("e2_score3b_a")
    assert s3b.k_class({"abs_ns": {"median": 0.009, "p95": 0.03}})
    assert not s3b.k_class({"abs_ns": {"median": 0.011, "p95": 0.01}})
    assert not s3b.k_class({"abs_ns": {}})
