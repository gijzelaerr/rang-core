"""E0 (research/e0-refant-extend.md): CARACal's `refant: auto`
(`rang.cal_refant`) and CASA's `flagdata(mode='extend')` with CARACal's
settings (`rang.flag_extend`, Rust kernel `core/src/flag_extend.rs`). The
comparisons against CARACal's own function and CASA 6.7.6.14 are
`examples/check_e0.py`; these tests check the rules on small cases."""

import importlib.util
import itertools
import math
from pathlib import Path

import numpy as np
import pytest
from rang import cal_refant, core_config, core_ms, core_ms_write, flag_extend
from rang import core_writeback as wb

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "w1_writeback", ROOT / "examples/w1_writeback.py"
)
w1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w1)

needs_writer = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


# -- the kernel against a direct transcription of CASA's loops -----------------------


def casa_cube(flags, s):
    """FlagAgentExtension::computeAntennaPairFlags on a (pol, chan, time)
    cube, loop by loop (CASA's index order)."""
    f = flags.copy()
    npol, nchan, nt = f.shape
    if s["flagneartime"] or s["flagnearfreq"] or s["growaround"]:
        grow = np.zeros((npol, nchan + 2, nt + 2), bool)
        for t in range(nt):
            for c in range(nchan):
                for p in range(npol):
                    if f[p, c, t]:
                        if s["flagneartime"]:
                            grow[p, c + 1, t + 2] = grow[p, c + 1, t] = True
                        if s["flagnearfreq"]:
                            grow[p, c + 2, t + 1] = grow[p, c, t + 1] = True
                    elif s["growaround"]:
                        around = 0
                        for ti in range(t - 1, t + 2):
                            for ci in range(c - 1, c + 2):
                                if 0 <= ti < nt and 0 <= ci < nchan:
                                    around += int(f[p, ci, ti])
                        if around > 4:
                            grow[p, c + 1, t + 1] = True
        f |= grow[:, 1:-1, 1:-1]
    if s["growtime"] > 0 or s["growfreq"] > 0:
        acc_time = f.sum(axis=1).astype(float)  # (pol, time)
        acc_freq = f.sum(axis=2).astype(float)  # (pol, chan)
        if s["growfreq"] > 0:
            for t in range(nt):
                for p in range(npol):
                    if 100.0 * acc_time[p, t] / nchan >= s["growfreq"]:
                        f[p, :, t] = True
        if s["growtime"] > 0:
            for c in range(nchan):
                for p in range(npol):
                    if 100.0 * acc_freq[p, c] / nt >= s["growtime"]:
                        f[p, c, :] = True
    if s["extendpols"]:
        f |= f.any(axis=0, keepdims=True)
    return f


@pytest.mark.parametrize("density", [0.02, 0.1, 0.3, 0.6])
def test_kernel_equals_casas_loops(density):
    rng = np.random.default_rng(20261191)
    s = flag_extend.CARACAL
    for nt, nchan, npol in [(1, 7, 4), (5, 9, 4), (12, 16, 2), (3, 1, 1)]:
        cube = rng.random((nt, nchan, npol)) < density  # (row, chan, corr)
        # a burst row and a bad channel, so both 80 % rules can fire
        cube[min(1, nt - 1), : max(1, int(0.85 * nchan)), 0] = True
        cube[:, 0, npol - 1] |= rng.random(nt) < 0.9
        want = casa_cube(np.transpose(cube, (2, 1, 0)), s).transpose(2, 1, 0)
        got = cube.copy()
        chunk = np.zeros(nt, np.int64)
        counts = flag_extend.extend_flags(
            got, np.zeros(nt), np.ones(nt), np.arange(nt, dtype=float), chunk
        )
        assert np.array_equal(got, want), (nt, nchan, npol)
        assert counts["extendpols"] >= 0 and set(counts) == set(flag_extend.RULES)


def test_segments_are_baselines_within_chunks_in_time_order():
    a1 = np.array([0, 0, 1, 0, 0, 1])
    a2 = np.array([1, 2, 2, 1, 1, 2])
    time = np.array([10.0, 10.0, 10.0, 30.0, 20.0, 99.0])
    chunk = np.array([0, 0, 0, 0, 0, 1])
    order, starts = flag_extend.segments(chunk, a1, a2, time)
    groups = [order[a:b].tolist() for a, b in itertools.pairwise(starts)]
    assert groups == [[0, 4, 3], [1], [2], [5]]


def test_chunks_follow_msinterval():
    # 7.9966 s integrations (the slice): t - t0 < 59.99 s stays in the chunk.
    t = 5.0e9 + 7.99661697 * np.arange(20)
    ids = flag_extend.casa_chunks(*(np.zeros(20, int),) * 4, t)
    assert ids.tolist() == [0] * 8 + [1] * 8 + [2] * 4
    # The 0.01 s offset: 59.985 s after t0 is in, 59.995 s is out.
    t = np.array([0.0, 30.0, 59.985, 100.0, 159.995]) + 4.0e9
    ids = flag_extend.casa_chunks(*(np.zeros(5, int),) * 4, t)
    assert ids.tolist() == [0, 0, 0, 1, 2]
    # A new field (or array, observation, data description) starts a chunk;
    # scans do not (combinescans): the caller passes no scan.
    field = np.array([0, 0, 1, 1, 0])
    t = 4.0e9 + np.array([0.0, 8.0, 16.0, 24.0, 32.0])
    ids = flag_extend.casa_chunks(np.zeros(5, int), np.zeros(5, int), field,
                                  np.zeros(5, int), t)  # fmt: skip
    assert ids[0] == ids[1] == ids[4] and ids[2] == ids[3] and ids[0] != ids[2]


def test_chunk_rule_is_floor_based():
    t0 = 4.0e9 + 0.37
    t = np.array([t0, t0 + 59.9899, t0 + 59.9901])
    ids = flag_extend.casa_chunks(*(np.zeros(3, int),) * 4, t)
    want = [math.floor((x - (t0 - 0.01)) / 60.0) for x in t]
    assert ids.tolist() == [0, 0, 1] and want == [0, 0, 1]


@needs_writer
def test_extend_ms_writes_flag_only_on_the_selection(tmp_path):
    nant, nchan = 4, 8
    ms = w1.make_ms(tmp_path / "x.ms", 6 * 30, nchan, nant=nant, seed=20261192)
    with core_ms_write.open_table(ms, readonly=False) as t:
        field = (np.arange(180) // 6 >= 15).astype(np.int32)
        t.putcol("FIELD_ID", field)
        t.putcol("SCAN_NUMBER", 1 + field)
        before = t.getcol("FLAG")
        flag_row = t.getcol("FLAG_ROW")
    out = flag_extend.extend_ms(ms, [0], flag_backup="e0_test", chunk_rows=50)
    with core_ms.open_table(ms) as t:
        after = t.getcol("FLAG")
        assert np.array_equal(t.getcol("FLAG_ROW"), flag_row)
    assert np.array_equal(after[field == 1], before[field == 1])
    assert (after >= before).all() and out["rows"] == 90
    # The same with the arrays: one call per field equals the MS route.
    with core_ms.open_table(ms) as t:
        meta = {k: t.getcol(k) for k in flag_extend.META}
    want = before.copy()
    keep = field == 0
    chunk = np.full(180, -1)
    chunk[keep] = flag_extend.casa_chunks(*(meta[k][keep] for k in (
        "OBSERVATION_ID", "ARRAY_ID", "FIELD_ID", "DATA_DESC_ID", "TIME")))  # fmt: skip
    flag_extend.extend_flags(
        want, meta["ANTENNA1"], meta["ANTENNA2"], meta["TIME"], chunk
    )
    assert np.array_equal(after, want)
    assert wb.read_journal(ms)["state"] == "closed"


# -- refant auto -------------------------------------------------------------------


def _centre():
    e = cal_refant.observatories()["MEERKAT"]
    return np.array(cal_refant.wgs84_to_ecef(e["m0"], e["m1"], e["m2"]))


@needs_writer
def test_refant_auto_picks_by_name_not_by_flags(tmp_path):
    ms = w1.make_ms(tmp_path / "r.ms", 30, 4, nant=6, seed=20261193)
    east = np.array([1.0, 0.0, 0.0])
    offsets = [0.0, 400.0, 30.0, 800.0, 1600.0, 600.0]  # metres along x
    pos = _centre() + np.array(offsets)[:, None] * east
    names = ["m005", "m004", "m003", "m002", "m001", "m000"]
    with core_ms_write.open_table(ms / "ANTENNA", readonly=False) as t:
        t.addrows(6)
        t.putcol("POSITION", pos)
        t.putcol("NAME", names)
    with core_ms_write.open_table(ms / "OBSERVATION", readonly=False) as t:
        if t.nrows() == 0:
            t.addrows(1)
        t.putcol("TELESCOPE_NAME", ["MeerKAT"])
    choice = cal_refant.caracal_refant(ms)
    # Rows 0 and 2 are 30 m apart; row 4 is 1.6 km out. Rows 1, 3, 5 qualify
    # (m004, m002, m000) and come back in name order.
    assert choice.names == ["m000", "m002", "m004"]
    by_name = {a["name"]: a for a in choice.antennas}
    assert not by_name["m005"]["all_baselines_ge_minbase"]
    assert not by_name["m001"]["within_maxdist"]
    # Flags do not matter: flag every row of m000 (row 5); the choice stays.
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("FLAG", np.ones((30, 4, 4), bool))
    assert cal_refant.caracal_refant(ms).names == ["m000", "m002", "m004"]
    # An unknown telescope: the centre is antenna 0 (row 0, m005).
    with core_ms_write.open_table(ms / "OBSERVATION", readonly=False) as t:
        t.putcol("TELESCOPE_NAME", ["E0-NOWHERE"])
    choice = cal_refant.caracal_refant(ms)
    assert choice.centre_source.startswith("antenna 0")
    assert choice.names == ["m000", "m002", "m004"]  # all within 1 km of row 0
    with pytest.raises(cal_refant.NoReferenceAntenna):
        cal_refant.caracal_refant(ms, minbase=2000.0)


def test_observatory_lookup_ignores_case():
    table = cal_refant.observatories()
    assert "MEERKAT" in table and table["MEERKAT"]["refer"] == "WGS84"
    centre, source = cal_refant.array_centre("meerkat", [[0.0, 0.0, 0.0]])
    assert source.startswith("casacore MeerKAT")
    assert np.allclose(centre, _centre())


# -- the configuration ---------------------------------------------------------------


def test_e2b_validates_and_the_new_errors():
    raw = core_config.load(ROOT / "tests/data/w2/e2b.yaml")
    core_config.validate(raw, ["flag", "calibrate", "apply"])
    config, problems = core_config.resolve(raw)
    assert problems == []
    assert config["calibrate"]["refant_maxdist"] == 1000.0
    assert config["calibrate"]["refant_minbase"] == 150.0

    def paths(raw):
        config, problems = core_config.resolve(raw)
        assert problems == []
        return {r.path for r in core_config.refusals(config, ["calibrate"])}

    base = {"version": 1, "fields": {"fcal": [0]}, "calibrate": {
        "refant": ["auto", "m000"], "model": {"source": "column"},
        "primary": {"terms": [{"type": "K", "name": "K", "solint": "inf"}]},
        "polcal": {"extendflags": True}}}  # fmt: skip
    got = paths(base)
    assert "calibrate.primary.terms[0].refant" in got  # auto stands alone
    assert "calibrate.polcal.extendflags" in got  # no Gpol, KCROSS or Xf term
