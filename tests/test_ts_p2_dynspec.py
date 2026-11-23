# SPDX-License-Identifier: MIT
"""TS-P2 (research/ts-p2.md): dynamic spectra by `rang-core lightcurve
--channels-out M`. A small version of the TS-P2 simulation is written inside
the test (8 antennas, 16 channels, 12 integrations); the frozen sets are
not."""

import csv
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from rang import core_cli, core_ms_write
from rang import lightcurve as lc

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"examples/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)

sim = _load("ts_p2_sim")
measure = _load("ts_p2_measure")
GROUPS = 4


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    out = tmp_path_factory.mktemp("tsp2")
    ms = sim.main(
        [
            "tsp2-dev",
            str(out),
            "--ntime",
            "12",
            "--nant",
            "8",
            "--nchan",
            "16",
            "--groups",
            str(GROUPS),
        ]
    )
    truth_path = out / "tsp2-dev.truth.json"
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    return ms, truth_path, truth


def positions(truth):
    return [(s["name"], s["ra_deg"], s["dec_deg"]) for s in truth["sources"]]


def test_groups_follow_wscleans_grouping_and_refuse_a_remainder():
    freq = np.linspace(1e9, 1.15e9, 16)
    g = lc.channel_groups(freq, 4)
    assert [(a, b) for a, b, _ in g] == [(0, 3), (4, 7), (8, 11), (12, 15)]
    assert g[1][2] == pytest.approx(freq[4:8].mean())
    with pytest.raises(lc.LightcurveError):
        lc.channel_groups(freq, 5)
    with pytest.raises(lc.LightcurveError):
        lc.channel_groups(freq, 0)


def test_light_curve_unchanged_by_the_dynamic_spectrum(small, tmp_path):
    ms, _, truth = small
    pos = positions(truth)
    kw = {"size": 256, "scale_arcsec": 2.0}
    plain = lc.light_curves(ms, pos, field=truth["field_id"], **kw)
    dyn = lc.light_curves(ms, pos, field=truth["field_id"], channels_out=GROUPS, **kw)
    lc.write_outputs(plain, tmp_path / "plain")
    lc.write_outputs(dyn, tmp_path / "dyn")
    assert (tmp_path / "plain/lightcurve.csv").read_bytes() == (
        tmp_path / "dyn/lightcurve.csv"
    ).read_bytes()
    assert not (tmp_path / "plain/dynspec.csv").exists()
    assert (tmp_path / "dyn/dynspec.csv").is_file()


def test_dynamic_spectrum_scores_against_the_numpy_oracle(small, tmp_path):
    ms, truth_path, truth = small
    out = tmp_path / "lc"
    core_cli.dispatch(
        [
            "--no-receipt",
            "lightcurve",
            str(ms),
            "--positions",
            str(_pos_csv(truth, tmp_path)),
            "--out",
            str(out),
            "--field",
            str(truth["field_id"]),
            "--size",
            "256",
            "--scale",
            "2asec",
            "--channels-out",
            str(GROUPS),
        ]
    )
    res = measure.score(ms, truth_path, out)
    assert res["D1"]["pass"], res["D1"]
    assert res["D4"]["pass"], res["D4"]
    # The last four channels are flagged in every row: group 3 is empty.
    assert res["D5"]["empty_groups"] == [GROUPS - 1] and res["D5"]["pass"]
    data = json.loads((out / "lightcurve.json").read_text(encoding="utf-8"))
    assert data["settings"]["channels_out"] == GROUPS
    assert all(k[0][GROUPS - 1] is None for k in data["dynspec_flux_jy"])
    with open(out / "dynspec.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 12 * len(truth["sources"]) * GROUPS
    # The bright pulse of A (integration 40 in the full set) is outside 12
    # integrations; the cells there are noise around the expected value.
    assert abs(res["D3"]["per_source"]["F"]) < 5 * res["D3"]["bound"]["F"]


def test_channels_out_must_divide_the_channels(small, tmp_path):
    ms, _, truth = small
    with pytest.raises(SystemExit):
        core_cli.dispatch(
            [
                "--no-receipt",
                "lightcurve",
                str(ms),
                "--position",
                "300,-36",
                "--out",
                str(tmp_path / "x"),
                "--field",
                str(truth["field_id"]),
                "--no-images",
                "--channels-out",
                "3",
            ]
        )


def _pos_csv(truth, where):
    path = where / "positions.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "ra_deg", "dec_deg"])
        for s in truth["sources"]:
            w.writerow([s["name"], repr(s["ra_deg"]), repr(s["dec_deg"])])
    return path


def test_unit_weights_are_the_default_and_scored(small, tmp_path):
    """TS-P4 (research/ts-p4.md; TS-P3 U5 re-pointed): no option equals
    `--weights unit` byte for byte; `ms` (the earlier default) changes the
    fluxes of a set with unequal weights; both match the scorer's NumPy DFT
    with their own weights."""
    ms, truth_path, truth = small
    pos = _pos_csv(truth, tmp_path)
    base = ["--no-receipt", "lightcurve", str(ms), "--positions", str(pos),
            "--field", str(truth["field_id"]), "--size", "256", "--scale", "2asec",
            "--channels-out", str(GROUPS)]  # fmt: skip
    for name, extra in (("plain", []), ("ms", ["--weights", "ms"]),
                        ("unit", ["--weights", "unit"])):  # fmt: skip
        core_cli.dispatch([*base, "--out", str(tmp_path / name), *extra])
    for f in ("lightcurve.csv", "dynspec.csv"):
        assert (tmp_path / "plain" / f).read_bytes() == (
            tmp_path / "unit" / f
        ).read_bytes()
    msw = json.loads((tmp_path / "ms/lightcurve.json").read_text(encoding="utf-8"))
    plain = json.loads((tmp_path / "plain/lightcurve.json").read_text(encoding="utf-8"))
    assert msw["settings"]["weights"] == "ms" and plain["settings"]["weights"] == "unit"
    assert msw["flux_jy"] != plain["flux_jy"]
    for name in ("unit", "ms"):
        res = measure.score(ms, truth_path, tmp_path / name)
        assert res["D1"]["pass"] and res["D4"]["pass"], (name, res["D1"], res["D4"])
    with pytest.raises(SystemExit):
        core_cli.dispatch([*base, "--out", str(tmp_path / "bad"), "--weights", "x"])
