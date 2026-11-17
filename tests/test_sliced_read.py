"""Channel- and row-sliced reads (research/sliced-read.md).

The core reader reads a channel slice of a list of rows in one call; the
tiled storage managers read only the tiles the slice intersects. Every read
must equal the whole read cut in NumPy, on tables whose tiles split the
channel and correlation axes without dividing them, for both tiled managers
and StandardStMan, both byte orders and every value type the visibility
columns use (Bool from a bit that is not the first of a byte). The
pre-apply on a channel window equals the whole-band pre-apply cut, and the
chunked solves that now read only their channels equal the one-call solves.
"""

import shutil
from pathlib import Path

import numpy as np
import pytest
from rang import (
    cal_apply,
    cal_bandpass,
    cal_chain,
    cal_delay,
    cal_gain,
    cal_pol,
    core_chunks,
    core_ms,
    core_ms_write,
)
from test_c2e_calibrate import calibrator_ms
from test_c6w_polwire import _with_feed
from test_w3b_chainchunks import budget, same, unit

NROW, NCHAN, NCORR = 23, 13, 4
CHANS = [
    slice(0, NCHAN),
    slice(None),
    slice(0, 1),
    slice(1, 2),
    slice(4, 11),
    slice(5, 10),
    slice(7, None),
    slice(12, 13),
]
ROWS = [
    np.arange(NROW),
    np.arange(3, 9),
    np.array([0, 1, 2, 9, 10, 17, 22]),
    np.array([22, 4, 5, 6, 1, 13]),  # not ascending
    np.array([11]),
]
# Casacore order (corr, chan, row): 3 and 5 split 4 and 13 without dividing
# them; 4 rows a tile.
TILE = [3, 5, 4]
MANAGERS = ["TiledShapeStMan", "TiledColumnStMan", "StandardStMan"]


def _cut(name, chans):
    """`chans` for column `name`: WEIGHT's cells are its 4 correlations."""
    return (
        slice(1, 3) if name == "WEIGHT" and chans.indices(NCHAN)[1] > NCORR else chans
    )


def _values(seed):
    rng = np.random.default_rng(seed)
    shape = (NROW, NCHAN, NCORR)
    return {
        "DATA": (rng.standard_normal(shape) + 1j * rng.standard_normal(shape)).astype(
            np.complex64
        ),
        "FLAG": rng.random(shape) < 0.4,
        "WEIGHT_SPECTRUM": rng.random(shape).astype(np.float32),
        "SIGMA_SPECTRUM": rng.random(shape),
        "INTS": rng.integers(-1000, 1000, shape).astype(np.int32),
        "WEIGHT": rng.random((NROW, NCORR)).astype(np.float32),
    }


def _make(path, manager, endian):
    w = core_ms_write
    cell = [NCHAN, NCORR]
    cols = [
        w.makearrcoldesc("DATA", 0j, shape=cell, valuetype="complex"),
        w.makearrcoldesc("FLAG", False, shape=cell, valuetype="boolean"),
        w.makearrcoldesc("WEIGHT_SPECTRUM", 0.0, shape=cell, valuetype="float"),
        w.makearrcoldesc("SIGMA_SPECTRUM", 0.0, shape=cell, valuetype="double"),
        w.makearrcoldesc("INTS", 0, shape=cell, valuetype="int"),
        w.makearrcoldesc("WEIGHT", 0.0, shape=[NCORR], valuetype="float"),
    ]
    spectral = ["DATA", "FLAG", "WEIGHT_SPECTRUM", "SIGMA_SPECTRUM", "INTS"]
    dminfo = None
    if manager != "StandardStMan":
        dminfo = {
            f"*{i + 1}": {
                "TYPE": manager,
                "NAME": f"T{name}",
                "SPEC": {"DEFAULTTILESHAPE": TILE},
                "COLUMNS": [name],
            }
            for i, name in enumerate(spectral)
        }
    values = _values(len(str(path)))
    t = w.create_table(path, cols, nrow=NROW, dminfo=dminfo, endian=endian)
    for name, v in values.items():
        t.putcol(name, v)
    t.close()
    return values


@pytest.fixture(
    scope="module", params=[(m, e) for m in MANAGERS for e in ("little", "big")]
)
def table(request, tmp_path_factory):
    manager, endian = request.param
    path = tmp_path_factory.mktemp("sliced") / f"{manager}-{endian}.tab"
    return path, _make(path, manager, endian)


def test_whole_reads_round_trip(table):
    path, values = table
    with core_ms.open_table(path) as t:
        for name, v in values.items():
            np.testing.assert_array_equal(t.getcol(name), v)


@pytest.mark.parametrize("chans", CHANS, ids=str)
def test_sliced_reads_equal_whole_reads_cut(table, chans):
    path, values = table
    with core_ms.open_table(path) as t:
        for name, v in values.items():
            c = _cut(name, chans)
            got = t.getcol(name, chans=c)
            assert got.dtype == v.dtype
            np.testing.assert_array_equal(got, v[:, c])
            np.testing.assert_array_equal(t.getcol(name, 5, 9, chans=c), v[5:14, c])
            for rows in ROWS:
                np.testing.assert_array_equal(
                    t.getcol_rows(name, rows, chans=c), v[rows][:, c]
                )
                assert t.getcol_rows(name, rows).tobytes() == v[rows].tobytes()


def test_writer_reads_equal_whole_reads_cut(table):
    path, values = table
    with core_ms_write.open_table(path, readonly=False) as t:
        for name, v in values.items():
            for chans in CHANS:
                c = _cut(name, chans)
                np.testing.assert_array_equal(t.getcol(name, chans=c), v[:, c])
                for rows in ROWS:
                    np.testing.assert_array_equal(
                        t.getcol_rows(name, rows, chans=c), v[rows][:, c]
                    )


@pytest.mark.parametrize("block", [None, 1, 4, 100])
def test_read_rows_equals_the_runs_read(table, block):
    """`core_chunks.read_rows` through the core reader (one call per block)
    equals the runs of python-casacore's interface (`getcol` only)."""
    path, values = table

    class RunsOnly:
        def __init__(self, t):
            self.t = t

        def getcol(self, name, start, n):
            return self.t.getcol(name, start, n)

    with core_ms.open_table(path) as t:
        for name in values:
            for chans in (None, slice(4, 11), slice(12, 13)):
                chans = chans if chans is None else _cut(name, chans)
                for rows in ROWS:
                    want = core_chunks.read_rows(RunsOnly(t), name, rows, chans, block)
                    got = core_chunks.read_rows(t, name, rows, chans, block)
                    assert got.dtype == want.dtype and got.shape == want.shape
                    assert got.tobytes() == want.tobytes()


def test_steps_fall_back_to_a_numpy_cut(table):
    path, values = table
    with core_ms.open_table(path) as t:
        for chans in (slice(1, 12, 3), slice(5, 5), slice(-3, None)):
            np.testing.assert_array_equal(
                t.getcol("DATA", chans=chans), values["DATA"][:, chans]
            )


def test_a_slice_outside_the_cell_is_refused(table):
    path, _ = table
    with core_ms.open_table(path) as t:
        with pytest.raises(OSError, match="outside a cell"):
            t.getcol("DATA", chans=slice(10, 14))
        with pytest.raises(OSError, match="outside a cell"):
            t.getcol_rows("FLAG", [0, 1], chans=slice(13, 15))


def test_casacure_reads_the_same_slices(table):
    ct = pytest.importorskip("casacure.tables")
    path, values = table
    t = ct.table(str(path), ack=False)
    try:
        with core_ms.open_table(path) as r:
            for name in values:
                for chans in CHANS[2:]:
                    if name == "WEIGHT":
                        c = _cut(name, chans)
                        want = t.getcol(name)[:, c]
                    else:
                        c = chans
                        start, stop, _ = chans.indices(NCHAN)
                        want = t.getcolslice(name, [start, 0], [stop - 1, NCORR - 1])
                    np.testing.assert_array_equal(r.getcol(name, chans=c), want)
    finally:
        t.close()


@pytest.mark.parametrize("manager", ["TiledShapeStMan", "TiledColumnStMan"])
@pytest.mark.parametrize("endian", ["little", "big"])
def test_tables_casacure_writes_read_sliced(tmp_path, manager, endian):
    """Tiled tables written by casacore itself (casacure), read sliced by
    the core reader."""
    ct = pytest.importorskip("casacure.tables")
    path = str(tmp_path / "c.tab")
    cols = [
        ct.makearrcoldesc("DATA", 0j, shape=[NCHAN, NCORR], valuetype="complex"),
        ct.makearrcoldesc("FLAG", False, shape=[NCHAN, NCORR], valuetype="boolean"),
    ]
    dminfo = {
        "*1": {"TYPE": manager, "NAME": "TD", "SPEC": {"DEFAULTTILESHAPE": TILE},
               "COLUMNS": ["DATA"]},
        "*2": {"TYPE": manager, "NAME": "TF", "SPEC": {"DEFAULTTILESHAPE": TILE},
               "COLUMNS": ["FLAG"]},
    }  # fmt: skip
    values = _values(7)
    t = ct.table(path, ct.maketabdesc(cols), nrow=NROW, dminfo=dminfo, endian=endian,
                 ack=False)  # fmt: skip
    t.putcol("DATA", values["DATA"])
    t.putcol("FLAG", values["FLAG"])
    t.close()
    with core_ms.open_table(path) as r:
        for name in ("DATA", "FLAG"):
            for chans in CHANS:
                for rows in ROWS:
                    np.testing.assert_array_equal(
                        r.getcol_rows(name, rows, chans=chans),
                        values[name][rows][:, chans],
                    )


# -- the pre-apply on a channel window ---------------------------------------------


@pytest.fixture(scope="module")
def cal_ms(tmp_path_factory):
    ms = calibrator_ms(tmp_path_factory.mktemp("sliced-cal") / "x.ms")
    with core_ms_write.open_table(ms, readonly=False) as t:
        flag = t.getcol("FLAG")
        flag[30:36] = True
        t.putcol("FLAG", flag)
    return ms


@pytest.fixture(scope="module")
def chain(cal_ms):
    """K, G and B tables of CAL, and a B with flagged solution channels (so
    the resampling to the data channels interpolates)."""
    common = {
        "field_id": 0,
        "refant": 0,
        "weight_column": "WEIGHT",
        "model": unit(cal_ms, 0),
    }
    k = cal_delay.gaincal(cal_ms, solint="inf", **common)
    g = cal_gain.gaincal(
        cal_ms, solint="int", gaintable=[k[0]], minblperant=2, **common
    )
    b = cal_bandpass.bandpass(cal_ms, combine="scan", minblperant=2,
                              gaintable=[k[0], g[0]], **common)  # fmt: skip
    gapped = shutil.copytree(cal_ms, cal_ms.parent / "gapped.ms")
    with core_ms_write.open_table(gapped, readonly=False) as t:
        flag = t.getcol("FLAG")
        flag[:, 3:5] = True
        t.putcol("FLAG", flag)
    bg = cal_bandpass.bandpass(gapped, combine="scan", minblperant=2,
                               gaintable=[k[0], g[0]], **common)  # fmt: skip
    assert np.asarray(bg[0].flags)[:, 3:5].all()
    return k[0], g[0], b[0], bg[0]


def test_the_pre_apply_on_a_window_equals_the_whole_band_cut(cal_ms, chain):
    with core_ms.open_table(cal_ms) as t:
        data = t.getcol("DATA")
        flag = t.getcol("FLAG")
        time, a1, a2 = (t.getcol(c) for c in ("TIME", "ANTENNA1", "ANTENNA2"))
    with core_ms.open_table(cal_ms / "SPECTRAL_WINDOW") as t:
        freq = t.getcol("CHAN_FREQ")[0]
    nchan = len(freq)
    for tables in ([chain[0]], [chain[1]], [chain[2]], [chain[3]], list(chain[:3]),
                   [chain[0], chain[1], chain[3]]):  # fmt: skip
        for direction in ("correct", "corrupt"):
            whole, wflag = cal_apply.apply(data, flag, time, a1, a2, freq, tables,
                                           direction=direction)  # fmt: skip
            for chans in (slice(0, nchan), slice(0, 1), slice(3, 4), slice(2, 9),
                          slice(nchan - 1, nchan)):  # fmt: skip
                got, gflag = cal_apply.apply(data[:, chans], flag[:, chans], time, a1, a2,
                                             freq, tables, direction=direction,
                                             channels=chans)  # fmt: skip
                assert got.tobytes() == whole[:, chans].tobytes()
                assert np.array_equal(gflag, wflag[:, chans])
    with pytest.raises(ValueError, match="unit-step"):
        cal_apply.apply(data[:, :3], flag[:, :3], time, a1, a2, freq, [chain[0]],
                        channels=slice(0, 4))  # fmt: skip


# -- chunked solves on sliced reads ------------------------------------------------


def test_bandpass_with_tables_and_channel_chunks_equals_one_call(cal_ms, chain):
    k, g, _, bg = chain
    common = {"field_id": 0, "refant": 0, "weight_column": "WEIGHT", "model": unit(cal_ms, 0),
              "combine": "scan", "minblperant": 2, "fillgaps": 2}  # fmt: skip
    for tables in ([k, g], [k, g, bg]):
        one = cal_bandpass.bandpass(cal_ms, gaintable=tables, **common)
        for b in (budget(2000), budget(10_000, rows=7)):
            same(
                one, cal_bandpass.bandpass(cal_ms, gaintable=tables, budget=b, **common)
            )


@pytest.fixture(scope="module")
def pol_ms(cal_ms, tmp_path_factory):
    ms = shutil.copytree(cal_ms, tmp_path_factory.mktemp("sliced-pol") / "p.ms")
    _with_feed(ms)
    return ms


def test_xf_and_df_after_b_in_channel_chunks_equal_one_call(pol_ms):
    """Xf and Df pre-apply K, G and B (B's solution channels equal to the
    data channels: the resampling's shortcut), in channel chunks."""
    model0 = unit(pol_ms, 0)
    base = {"field_id": 0, "refant": 0, "weight_column": "WEIGHT", "model": model0}
    k = cal_delay.gaincal(pol_ms, solint="inf", **base)[0]
    g = cal_gain.gaincal(pol_ms, solint="int", gaintable=[k], minblperant=2, **base)[0]
    b = cal_bandpass.bandpass(pol_ms, combine="scan", minblperant=2, gaintable=[k, g],
                              **base)[0]  # fmt: skip
    tables = [k, g, b]
    polarised = unit(pol_ms, 1, (1.0, 0.05, 0.08, 0.0))
    common = {
        "field_id": 1,
        "gaintable": tables,
        "model": polarised,
        "weight_column": "WEIGHT",
    }
    for bud in (budget(1200), budget(10_000, rows=7)):
        same(cal_pol.xf(pol_ms, combine="scan", **common),
             cal_pol.xf(pol_ms, combine="scan", budget=bud, **common))  # fmt: skip
        kw = {
            "combine": "scan",
            "minblperant": 2,
            "min_data_fraction": 0.5,
            "minsnr": 0.0,
        }
        one = cal_pol.df(pol_ms, **common, **kw)
        got = cal_pol.df(pol_ms, budget=bud, **common, **kw)
        assert cal_chain._sha(one[0]) == cal_chain._sha(got[0])
        assert one[1].gauge_fixed == got[1].gauge_fixed


@pytest.mark.parametrize(
    "rel",
    [
        "luno-solve-20261029-02/work.ms",
        "tv-caracal-wsl-20261029-01/original.ms",
        "tv-next-imaging-wsl-20261029-01/caracal-diagnostic.ms",
    ],
)
def test_sliced_reads_of_the_oracle_measurement_sets(rel):
    """The task E oracle's MSs (written by CASA and casacore): every array
    column read sliced equals the whole read cut."""
    path = Path(__file__).resolve().parents[1] / "outputs" / rel
    if not path.is_dir():
        pytest.skip(f"{path} not present")
    with core_ms.open_table(path) as t:
        n = t.nrows
        rows = np.unique(np.linspace(0, n - 1, 37).astype(np.int64))[::-1]
        for name, c in t.columns.items():
            if not c["is_array"] or not c["supported"] or c["dtype"] == "str":
                continue
            try:
                whole = t.getcol(name, 0, min(n, 300))
            except OSError:  # undefined cells (FLAG_CATEGORY)
                continue
            if whole.ndim < 2:
                continue
            k = whole.shape[1]
            for chans in {
                slice(0, 1),
                slice(k // 3, k // 3 + max(1, k // 4)),
                slice(k - 1, k),
            }:
                np.testing.assert_array_equal(
                    t.getcol(name, 0, min(n, 300), chans=chans), whole[:, chans]
                )
                np.testing.assert_array_equal(
                    t.getcol_rows(name, rows, chans=chans),
                    np.stack([t.getcol(name, int(r), 1)[0] for r in rows])[:, chans],
                )
