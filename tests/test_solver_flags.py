# SPDX-License-Identifier: MIT
"""Issues #58 and #59 (research/solver-flags.md): flags at the gain solve
(`calibrate.solver_flags`) and the MeerKAT L-band known-RFI preset
(`flag.known_rfi`). Off by default and out of every stage hash; the kernels
find injected RFI; `gaincal` and `bandpass` flag the injected cells, write
them to FLAG and re-solve; the preset selects oxkat's bands by frequency."""

import copy
import shutil

import numpy as np
import pytest
from rang import (
    cal_bandpass,
    cal_gain,
    core,
    core_config,
    core_ms,
    core_ms_write,
    core_pipeline,
    meerkat,
    solver_flags,
)


def _config(**extra):
    raw = {"schema": "rang-config", "version": 1, "flag": {"strategy": "s.yaml"}}
    raw.update(extra)
    config, errors = core_config.resolve(raw)
    assert not errors, errors
    return config


def test_defaults_are_off_and_leave_every_stage_hash():
    config = _config()
    assert config["calibrate"]["solver_flags"]["mode"] == "off"
    assert config["flag"]["known_rfi"] == "none"
    without = copy.deepcopy(config)
    del without["calibrate"]["solver_flags"]
    del without["flag"]["known_rfi"]
    for stage in core_config.STAGES:
        assert core_config.stage_hash(config, stage) == core_config.stage_hash(
            without, stage
        )


def test_on_changes_only_its_stage_hash():
    off = _config()
    on = copy.deepcopy(off)
    on["calibrate"]["solver_flags"]["mode"] = "quartical"
    assert core_config.stage_hash(on, "calibrate") != core_config.stage_hash(
        off, "calibrate"
    )
    assert core_config.stage_hash(on, "flag") == core_config.stage_hash(off, "flag")
    preset = copy.deepcopy(off)
    preset["flag"]["known_rfi"] = "meerkat_l"
    assert core_config.stage_hash(preset, "flag") != core_config.stage_hash(off, "flag")
    assert core_config.stage_hash(preset, "calibrate") == core_config.stage_hash(
        off, "calibrate"
    )


def test_refusals():
    config = _config(
        calibrate={"solver_flags": {"mode": "quartical", "terms": ["K"], "guard": 0}},
        data={"processes": 2},
    )
    paths = {r.path for r in core_config.refusals(config, ["calibrate"])}
    assert "calibrate.solver_flags.terms" in paths
    assert "calibrate.solver_flags.guard" in paths
    assert "calibrate.solver_flags.mode" in paths
    ok = _config(calibrate={"solver_flags": {"mode": "rang"}})
    paths = {r.path for r in core_config.refusals(ok, ["calibrate"])}
    assert not {p for p in paths if p.startswith("calibrate.solver_flags")}


def test_unquoted_off_reads_as_off():
    config = _config(calibrate={"solver_flags": {"mode": False}})
    assert config["calibrate"]["solver_flags"]["mode"] == "off"


# -- the kernels -------------------------------------------------------------------


def _array(nant, ndump):
    rows = [
        (p, q, d) for d in range(ndump) for p in range(nant) for q in range(p + 1, nant)
    ]
    a1, a2, dump = (np.array(x, np.uint32) for x in zip(*rows))
    return a1, a2, dump


def test_diag_residual_and_solver_flags_find_rfi():
    ext = core.extension()
    nant, ndump, nchan = 7, 25, 24
    a1, a2, dump = _array(nant, ndump)
    nrow = len(a1)
    rng = np.random.default_rng(58)
    g = np.exp(1j * rng.uniform(-np.pi, np.pi, (1, 1, nant, 2))) * rng.uniform(
        0.8, 1.2, (1, 1, nant, 2)
    )
    model = np.zeros((nrow, nchan, 4), np.complex64)
    model[..., 0] = model[..., 3] = 2.0
    data = np.zeros_like(model)
    for h, k in ((0, 0), (1, 3)):
        data[..., k] = g[0, 0, a1, h][:, None] * 2.0 * np.conj(g[0, 0, a2, h])[:, None]
    data += 0.05 * (rng.normal(size=data.shape) + 1j * rng.normal(size=data.shape))
    hits = [(3, 2), (60, 11), (200, 23)]
    for r, c in hits:
        data[r, c, 3] += 5.0
    res, bad = ext.flag_residual_diag(
        data.view(np.float32).reshape(-1),
        model.view(np.float32).reshape(-1),
        nrow,
        nchan,
        a1,
        a2,
        np.zeros(nrow, np.uint32),
        np.zeros(nchan, np.uint32),
        np.ascontiguousarray(g, np.complex128).reshape(-1).view(np.float64),
        np.zeros(nant * 2, np.uint8),
        1,
        1,
        nant,
    )
    assert not bad.any()
    r = res.view(np.complex64).reshape(nrow, nchan, 2)
    assert np.median(np.abs(r)) < 0.1
    for quartical in (True, False):
        new, counts = ext.flag_residual_solver(
            res,
            np.zeros(nrow * nchan, np.uint8),
            nrow,
            nchan,
            a1,
            a2,
            dump,
            nant,
            quartical,
            5.0,
            10.0,
            3.0,
            16,
            1.0,
            0,
        )
        new = new.reshape(nrow, nchan)
        for rr, c in hits:
            assert new[rr, c], (quartical, rr, c)
        # QuartiCal's rule at 5 sigma on 525 x 24 cells: about 1 % false flags here.
        assert new.mean() < 0.02, (quartical, new.mean())
        assert counts["added"] == int(new.sum())


def test_bad_shapes_raise():
    ext = core.extension()
    with pytest.raises(ValueError):
        ext.flag_residual_solver(
            np.zeros(8, np.float32), np.zeros(1, np.uint8), 1, 2, np.zeros(1, np.uint32),
            np.zeros(1, np.uint32), np.zeros(1, np.uint32), 2, True, 5.0, 10.0, 3.0, 16,
            1.0, 0,
        )  # fmt: skip


# -- gaincal and bandpass on an MS --------------------------------------------------

needs_writer = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


@pytest.fixture(scope="module")
def rfi_ms(tmp_path_factory):
    from test_c2e_calibrate import calibrator_ms

    ms = calibrator_ms(tmp_path_factory.mktemp("sf") / "x.ms", seed=58)
    with core_ms.open_table(ms) as t:
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        field = t.getcol("FIELD_ID")
        flag = t.getcol("FLAG")
    # DATA = g_p g_q^* with gains constant over the band (so that one G
    # interval fits the data to the noise), noise 1e-2, and RFI in three cells.
    rng = np.random.default_rng(580)
    nant = int(max(a1.max(), a2.max())) + 1
    g = rng.uniform(0.8, 1.2, (nant, 2)) * np.exp(
        1j * rng.uniform(-np.pi, np.pi, (nant, 2))
    )
    data = np.zeros(flag.shape, np.complex64)
    data[..., 0] = (g[a1, 0] * np.conj(g[a2, 0]))[:, None]
    data[..., 3] = (g[a1, 1] * np.conj(g[a2, 1]))[:, None]
    data += 1e-2 * (
        rng.standard_normal(data.shape) + 1j * rng.standard_normal(data.shape)
    )
    with core_ms.open_table(ms) as t:
        flag_row = t.getcol("FLAG_ROW")
    cal = np.flatnonzero((field == 0) & (a1 != a2) & ~flag_row)
    hits = []
    for r, c in ((cal[2], 3), (cal[len(cal) // 2], 9), (cal[-3], 14)):
        while flag[r, c].any():
            c = (c + 1) % flag.shape[1]
        hits.append((int(r), int(c)))
    for r, c in hits:
        data[r, c, 0] += 3.0
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("DATA", data)
    return ms, hits


def _cfg(**kw):
    cfg = dict(
        core_config.resolve({"schema": "rang-config", "version": 1})[0]["calibrate"][
            "solver_flags"
        ]
    )
    cfg.update(mode="quartical", **kw)
    return cfg


def _unit(ms):
    from rang import cal_fluxscale

    nrow, nchan = cal_fluxscale._field_rows(ms, 0, 0)
    return cal_fluxscale.smodel_view(nrow, nchan)


@needs_writer
@pytest.mark.parametrize("solve", ["G", "B"])
def test_solve_flags_injected_rfi_and_resolves(rfi_ms, tmp_path, solve):
    src, hits = rfi_ms
    ms = tmp_path / "x.ms"
    shutil.copytree(src, ms)
    with core_ms.open_table(ms) as t:
        before = t.getcol("FLAG")
    write = solver_flags.or_writer(ms, flag_backup="rang_original", stage="calibrate")
    # B on this 4-antenna fixture: one RFI cell corrupts its channel's solve
    # (6 baselines), so the pass flags much of that channel and the re-solve
    # loses solutions there; the tripwire is not what this test checks.
    cfg = _cfg(min_cells=0, tripwire=0.05 if solve == "G" else 1.0)
    sf = {"cfg": cfg, "write": write}
    # minblperant 2: with 4 antennas each has 3 baselines.
    common = {
        "field_id": 0,
        "refant": "m000",
        "minblperant": 2,
        "model": _unit(ms),
        "weight_column": "WEIGHT",
    }
    if solve == "G":
        _, sol, info = cal_gain.gaincal(ms, calmode="ap", solver_flags=sf, **common)
        _, plain, _ = cal_gain.gaincal(src, calmode="ap", **common)
    else:
        _, sol, info = cal_bandpass.bandpass(ms, solver_flags=sf, **common)
        _, plain, _ = cal_bandpass.bandpass(src, **common)
    rec = info["solver_flags"]
    with core_ms.open_table(ms) as t:
        after = t.getcol("FLAG")
    added = after & ~before
    for r, c in hits:
        assert added[r, c].all(), (r, c)
    assert rec["added"] == int(added.any(-1).sum())
    assert rec["resolved"] >= 1
    assert np.isfinite(sol.gains[~sol.flags]).all()
    if solve == "G":
        assert added.any(-1).sum() < 0.02 * after.shape[0] * after.shape[1]
        assert sol.flags.mean() <= plain.flags.mean() + 1e-12


@needs_writer
def test_off_is_the_plain_solve(rfi_ms):
    src, _ = rfi_ms
    common = {
        "field_id": 0,
        "refant": "m000",
        "minblperant": 3,
        "model": _unit(src),
        "weight_column": "WEIGHT",
    }
    _, s1, _ = cal_gain.gaincal(src, calmode="ap", **common)
    _, s2, i2 = cal_gain.gaincal(src, calmode="ap", solver_flags=None, **common)
    assert np.array_equal(s1.gains, s2.gains) and "solver_flags" not in i2


def test_tripwire_fires_on_a_rise(monkeypatch):
    class Sol:
        def __init__(self, f):
            self.flags = np.array([f, False, False, False])

    calls = iter([{"added": 5, "intervals": []}, {"added": 0, "intervals": []}])
    monkeypatch.setattr(solver_flags, "flag_pass", lambda *a, **k: next(calls))
    with pytest.raises(solver_flags.TripwireFired) as err:
        solver_flags.rounds(
            None, None, Sol(False), _cfg(tripwire=0.1), None, lambda: (Sol(True), None)
        )
    assert err.value.record["solutions_flagged_last"] == 0.25


# -- the known-RFI preset ----------------------------------------------------------


def _lband():
    width = np.full(1024, 856e6 / 1024)
    freq = 856e6 + (np.arange(1024) + 0.5) * width
    return freq, width


def test_known_rfi_l_selects_by_frequency():
    freq, width = _lband()
    every, short = meerkat.known_rfi_l("MeerKAT", freq, width)
    mhz = freq / 1e6
    hi = (mhz >= 1419.8) & (mhz <= 1421.3)
    assert every[hi].all() and every[mhz < 900].all() and every[mhz > 1658].all()
    assert not every[(mhz > 1000) & (mhz < 1400)].any()
    gsm = (mhz >= 925) & (mhz <= 960)
    assert short[gsm].all() and not every[gsm].any()
    # 1600 MHz falls between two centres: CASA takes both neighbours.
    near = np.flatnonzero(short & (np.abs(mhz - 1600) < 1.0))
    assert len(near) == 2 and mhz[near[0]] < 1600 < mhz[near[1]]
    assert not short[(mhz > 1300) & (mhz < 1375)].any()


def test_known_rfi_l_refuses_other_data():
    freq, width = _lband()
    with pytest.raises(ValueError, match="not MeerKAT"):
        meerkat.known_rfi_l("VLA", freq, width)
    with pytest.raises(ValueError, match="L band"):
        meerkat.known_rfi_l("MeerKAT", freq * 0.65, width)


class _Session:
    def __init__(self, flag, uvw, a1, a2):
        self.cols = {"FLAG": flag, "UVW": uvw, "ANTENNA1": a1, "ANTENNA2": a2}

    def read(self, name, start, n):
        return self.cols[name][start : start + n].copy()

    def write_flags(self, start, flag):
        self.cols["FLAG"][start : start + len(flag)] = flag


def test_known_rfi_pass_flags_short_baselines_only_for_the_short_list():
    freq, width = _lband()
    every, short = meerkat.known_rfi_l("MeerKAT", freq, width)
    nrow = 6
    flag = np.zeros((nrow, len(freq), 4), bool)
    uvw = np.zeros((nrow, 3))
    uvw[:, 0] = [0, 100, 599, 601, 5000, 300]
    a1 = np.array([0, 0, 0, 0, 0, 1])
    a2 = np.array([0, 1, 2, 3, 4, 2])
    w = _Session(flag, uvw, a1, a2)
    rec = core_pipeline.known_rfi_pass(w, np.arange(1, nrow), (every, short, 600.0), 2)
    out = w.cols["FLAG"]
    assert not out[0].any()  # row 0 not selected
    for r in (1, 2, 5):
        assert out[r][every | short].all() and not out[r][~(every | short)].any()
    for r in (3, 4):
        assert out[r][every].all() and not out[r][~every].any()
    assert rec["added"] == int(out.sum())
