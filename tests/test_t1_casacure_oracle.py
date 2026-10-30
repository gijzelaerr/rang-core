"""casacure as the second oracle of the core's table reader and writer.

research/t1-casacure-ci.md (task T1). On every platform with a casacure
3.8.35 wheel (the `casacure` extra; the wheels workflow's test jobs install
it), and with the public fixture `outer_scans.zip` (`RANG_FIXTURE` or
`outputs/ska-pointing/outer_scans.zip`; `rang.notebook.data.download_fixture`
fetches it):

1. every table and column of the five fixture MSs reads the same in
   `rang.core_ms` and casacure, and casacure's read of ms0's ANTENNA (scan 9,
   byte-identical to ms0) equals the golden archive's MS entry;
2. tables the core writes (E3) and creates (E4) on copies read back in
   casacure with the cells and keywords written. casacure only reads: its
   writes are not a reference (research/casacure-evaluation.md, verdict (c)).

A casacure table is always closed before the core writes the same files:
casacure memory-maps them.
"""

import json
import platform
import shutil
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
from rang.oracles import casacure as oracle

# casacure 3.8.35 publishes no macOS x86_64 wheel and no cp310 macOS arm64
# wheel (PyPI, 2026-10-30); the extra's marker skips it there.
NO_WHEEL = sys.platform == "darwin" and (
    platform.machine() == "x86_64" or sys.version_info < (3, 11)
)
_version = oracle.installed_version()
if _version is None:
    pytest.skip(
        "casacure 3.8.35 has no wheel for this platform"
        if NO_WHEEL
        else "casacure not installed",
        allow_module_level=True,
    )
if _version != oracle.PIN:
    pytest.skip(
        f"casacure {_version} installed, the oracle is pinned to {oracle.PIN}",
        allow_module_level=True,
    )

from rang import core_ms, core_ms_write
from rang.notebook import data as fixture_data

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "data" / "core-backends-golden"
SCANS = [f"1672727931_sdp_l0_scan_{n}.ms" for n in (1, 4, 5, 8, 9)]
SCAN9 = SCANS[-1]
# Columns the core does not read, per table, the same in all five MSs (the
# scratch inventory of research/t1-casacure-ci.md): never-written
# FLAG_CATEGORY, and POINTING's IncrementalStMan, which holds a string.
CORE_REFUSES = {
    "MAIN": {"FLAG_CATEGORY"},
    "POINTING": {
        "ANTENNA_ID",
        "INTERVAL",
        "NAME",
        "NUM_POLY",
        "TIME_ORIGIN",
        "TRACKING",
    },
}
# String-array columns: read in the core with core_ms_write.read_cells.
STRING_ARRAYS = {
    "FEED": {"POLARIZATION_TYPE"},
    "HISTORY": {"APP_PARAMS", "CLI_COMMAND"},
    "OBSERVATION": {"LOG", "SCHEDULE"},
}


@pytest.fixture(scope="session")
def fixture_mss(tmp_path_factory):
    """{name: path} of the fixture MSs, extracted once per session."""
    source = fixture_data.find_fixture()
    if source is None:
        pytest.skip("fixture MS not present")
    if source.is_dir():
        return {source.name: source}
    if fixture_data._sha256(source) != fixture_data.FIXTURE_SHA256:
        pytest.fail(f"{source} is not the pinned public fixture")
    dest = tmp_path_factory.mktemp("fixture")
    with zipfile.ZipFile(source) as zipped:
        for info in fixture_data._safe_members(zipped, "outer_scans/"):
            zipped.extract(info, dest)
    return {p.name: p for p in sorted((dest / "outer_scans").glob("*.ms"))}


def _ms(fixture_mss, name):
    if name not in fixture_mss:
        pytest.skip(f"fixture MS not present: {name}")
    return fixture_mss[name]


def _same(actual, expected, what):
    """Same dtype, shape and bytes (strings by value)."""
    actual, expected = np.asarray(actual), np.asarray(expected)
    assert actual.dtype == expected.dtype, (what, actual.dtype, expected.dtype)
    assert actual.shape == expected.shape, (what, actual.shape, expected.shape)
    if actual.dtype == object:
        assert all(isinstance(s, str) for s in actual.ravel()), what
        assert actual.tolist() == expected.tolist(), what
    else:
        assert (
            np.ascontiguousarray(actual).tobytes()
            == np.ascontiguousarray(expected).tobytes()
        ), what


def _same_cells(actual, expected, what):
    assert len(actual) == len(expected), what
    for row, (a, e) in enumerate(zip(actual, expected, strict=True)):
        _same(a, e, f"{what} row {row}")


def _tables(ms):
    return [ms] + sorted(p.parent for p in ms.glob("*/table.dat"))


def _label(ms, path):
    return "MAIN" if path == ms else path.name


# -- 1. the reader ----------------------------------------------------------


@pytest.mark.parametrize("name", SCANS)
def test_core_reader_equals_casacure(fixture_mss, name):
    ms = _ms(fixture_mss, name)
    compared = 0
    for path in _tables(ms):
        label = _label(ms, path)
        with core_ms.open_table(path) as core, oracle.open_table(path) as cc:
            assert core.nrows == cc.nrows, label
            assert sorted(core.colnames()) == sorted(cc.colnames()), label
            if label == "MAIN":
                links = {k: Path(v) for k, v in cc.subtables().items()}
                subdirs = {p.name for p in _tables(ms)[1:]}
                assert set(links) == subdirs
                assert all(v.resolve() == (ms / k).resolve() for k, v in links.items())
            if core.nrows == 0:
                # casacure 3.8.35 reads every column of a 0-row table as an
                # empty int32 array (E3's twelfth casacure item).
                continue
            strings = {
                c
                for c, d in core.columns.items()
                if d["dtype"] == "str" and d["is_array"]
            }
            assert strings == STRING_ARRAYS.get(label, set()), label
            for column in core.colnames():
                what = f"{name}/{label}.{column}"
                if column in CORE_REFUSES.get(label, set()):
                    with pytest.raises(Exception):  # noqa: B017 - any refusal
                        core.getcol(column)
                    continue
                if column in strings:
                    cells = core_ms_write.read_cells(path, column, 0, core.nrows)
                    _same_cells(cc.getcells(column), cells, what)
                    if core.nrows >= 5:
                        _same_cells(
                            cc.getcells(column, 3, 2),
                            core_ms_write.read_cells(path, column, 3, 2),
                            what + " [3, 5)",
                        )
                    compared += 1
                    continue
                _same(cc.getcol(column), core.getcol(column), what)
                _same(
                    cc.getcol(column, 0, 1), core.getcol(column, 0, 1), what + " [0, 1)"
                )
                if core.nrows >= 5:
                    _same(
                        cc.getcol(column, 3, 2),
                        core.getcol(column, 3, 2),
                        what + " [3, 5)",
                    )
                compared += 1
            if label == "MAIN":
                # E2 candidate 7: a (nrow,) False array where casacore raises.
                category = cc.getcol("FLAG_CATEGORY")
                assert category.shape == (cc.nrows,) and not category.any()
            if label == "POINTING":
                with pytest.raises(Exception, match="IncrementalStMan strings"):
                    cc.getcol("NAME")
    assert compared > 100


def test_casacure_equals_the_golden_ms_entry(fixture_mss):
    """The golden archive's `ms` leaves (ms0's ANTENNA through the core at
    5965d37) read by casacure, byte for byte on every platform."""
    antenna = _ms(fixture_mss, SCAN9) / "ANTENNA"
    with np.load(GOLDEN.with_suffix(".npz")) as arrays:
        golden = {k: arrays[k] for k in ("ms.2", "ms.3", "ms.4")}
    scalars = json.loads(GOLDEN.with_suffix(".json").read_text())
    description = json.loads(scalars["ms.0"])
    with oracle.open_table(antenna) as cc:
        names = cc.getcol("NAME")
        assert names.tolist() == [scalars[f"ms.1.{i}"] for i in range(len(names))]
        assert f"ms.1.{len(names)}" not in scalars
        _same(cc.getcol("POSITION"), golden["ms.2"], "POSITION")
        _same(cc.getcol("POSITION", 1, 2), golden["ms.3"], "POSITION [1, 3)")
        _same(cc.getcol("FLAG_ROW"), golden["ms.4"], "FLAG_ROW")
        assert description["nrows"] == cc.nrows
        assert [c["name"] for c in description["columns"]] == cc.colnames()
        for column in description["columns"]:
            dtype = cc.getcol(column["name"]).dtype
            assert ("str" if dtype == object else dtype.name) == column["dtype"]


# -- 2. the writer: in-place writes on copies of scan 9 (E3) ---------------


def _copy(fixture_mss, tmp_path):
    if not core_ms_write.has_writer():
        pytest.skip("extension built without the table writer")
    dst = tmp_path / SCAN9
    shutil.copytree(_ms(fixture_mss, SCAN9), dst)
    return dst


def _read(cc, column):
    """A column as casacure gives it: per-row cells for string arrays and
    for arrays whose rows differ in shape, `getcol` otherwise."""
    desc = cc.coldesc(column)
    if "ndim" in desc:
        cells = cc.getcells(column)
        if desc["valueType"] == "string" or len({c.shape for c in cells}) > 1:
            return cells
    return cc.getcol(column)


def _snapshot(path, skip=("FLAG_CATEGORY",)):
    """Every column, the table keywords and column keywords, in casacure;
    the table is closed on return."""
    with oracle.open_table(path) as cc:
        columns = {c: _read(cc, c) for c in cc.colnames() if c not in skip}
        return {
            "columns": columns,
            "keywords": cc.keywords(),
            "colkeywords": {c: cc.colkeywords(c) for c in cc.colnames()},
        }


def _check(after, expected, what):
    assert sorted(after["columns"]) == sorted(expected["columns"]), what
    for column, value in expected["columns"].items():
        got = after["columns"][column]
        if isinstance(value, list):
            _same_cells(got, value, f"{what}.{column}")
        else:
            _same(got, value, f"{what}.{column}")
    assert after["keywords"] == expected["keywords"], what
    assert after["colkeywords"] == expected["colkeywords"], what


def _expected(before, **columns):
    out = {key: dict(value) for key, value in before.items()}
    out["columns"].update(columns)
    return out


def test_tiled_writes_read_back(fixture_mss, tmp_path):
    ms = _copy(fixture_mss, tmp_path)
    before = _snapshot(ms)
    c = before["columns"]
    flag = ~c["FLAG"]
    weights = c["WEIGHT_SPECTRUM"].copy()
    weights[10:15] *= 2
    uvw = c["UVW"] * 1.5
    data = c["DATA"].copy()
    data[3] += 1
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("FLAG", flag)
        t.putcol("WEIGHT_SPECTRUM", weights[10:15], startrow=10, nrow=5)
        t.putcol("UVW", uvw)
        t.putcell("DATA", 3, data[3])
    after = _snapshot(ms)
    _check(
        after,
        _expected(before, FLAG=flag, WEIGHT_SPECTRUM=weights, UVW=uvw, DATA=data),
        "MAIN",
    )
    with oracle.open_table(ms) as cc:
        managers = cc.managers()
    assert managers["FLAG"] == managers["DATA"] == "TiledShapeStMan"
    assert managers["UVW"] == "TiledColumnStMan"


def test_standard_writes_read_back(fixture_mss, tmp_path):
    ms = _copy(fixture_mss, tmp_path)
    tables = {"MAIN": ms, **{n: ms / n for n in ("SPECTRAL_WINDOW", "ANTENNA", "FEED")}}
    before = {label: _snapshot(path) for label, path in tables.items()}
    main = before["MAIN"]["columns"]
    rows = ~main["FLAG_ROW"]
    antenna1 = main["ANTENNA1"][::-1].copy()
    chan_freq = before["SPECTRAL_WINDOW"]["columns"]["CHAN_FREQ"] * 2
    names = np.array(
        ["m0", "a-rather-long-antenna-name", "x", "MeerKAT-07"], dtype=object
    )
    pol = [np.array(["Y", "X"], dtype=object) for _ in range(4)]
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("FLAG_ROW", rows)
        t.putcol("ANTENNA1", antenna1)
    with core_ms_write.open_table(ms / "SPECTRAL_WINDOW", readonly=False) as t:
        t.putcol("CHAN_FREQ", chan_freq)
    with core_ms_write.open_table(ms / "ANTENNA", readonly=False) as t:
        t.putcol("NAME", list(names))
    with core_ms_write.open_table(ms / "FEED", readonly=False) as t:
        for row, cell in enumerate(pol):
            t.putcell("POLARIZATION_TYPE", row, cell)
    written = {
        "MAIN": {"FLAG_ROW": rows, "ANTENNA1": antenna1},
        "SPECTRAL_WINDOW": {"CHAN_FREQ": chan_freq},
        "ANTENNA": {"NAME": names},
        "FEED": {"POLARIZATION_TYPE": pol},
    }
    for label, path in tables.items():
        _check(_snapshot(path), _expected(before[label], **written[label]), label)


def test_keyword_writes_read_back(fixture_mss, tmp_path):
    ms = _copy(fixture_mss, tmp_path)
    before = _snapshot(ms)
    record = {"a": 1.0, "b": "x"}
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putkeyword("RANG_D", 1.5)
        t.putkeyword("RANG_I", 7)
        t.putkeyword("RANG_S", "a string keyword")
        t.putkeyword("RANG_A", np.array([1.0, 2.0, 3.0]))
        t.putkeyword("RANG_R", record)
        t.putcolkeyword("DATA", "RANG_UNIT", "Jy")
        t.putcolkeyword("UVW", "QuantumUnits", np.array(["km", "km", "km"]))
    expected = _expected(before)
    expected["keywords"] = dict(before["keywords"])
    expected["keywords"].update(
        RANG_D=1.5,
        RANG_I=7,
        RANG_S="a string keyword",
        RANG_A=[1.0, 2.0, 3.0],
        RANG_R=record,
    )
    expected["colkeywords"] = {k: dict(v) for k, v in before["colkeywords"].items()}
    expected["colkeywords"]["DATA"]["RANG_UNIT"] = "Jy"
    expected["colkeywords"]["UVW"]["QuantumUnits"] = ["km", "km", "km"]
    _check(_snapshot(ms), expected, "MAIN")


def test_addcols_read_back(fixture_mss, tmp_path):
    ms = _copy(fixture_mss, tmp_path)
    before = _snapshot(ms)
    nrows = len(before["columns"]["TIME"])
    rng = np.random.default_rng(20261030)
    model = (rng.standard_normal((nrows, 64, 4)) + 1j).astype(np.complex64)
    flags = rng.random((nrows, 64, 4)) < 0.5
    weights = rng.random((nrows, 64, 4)).astype(np.float32)
    w = core_ms_write
    with w.open_table(ms, readonly=False) as t:
        t.addcols(
            w.maketabdesc(
                w.makearrcoldesc("RANG_MODEL", 0j, ndim=2, valuetype="complex")
            )
        )
        t.putcol("RANG_MODEL", model)
        t.addcols(
            w.maketabdesc(
                w.makearrcoldesc(
                    "RANG_FLAGS", False, shape=[64, 4], valuetype="boolean"
                )
            ),
            {
                "TYPE": "TiledColumnStMan",
                "NAME": "RANG_FLAGS_DM",
                "SPEC": {"DEFAULTTILESHAPE": [4, 16, 8]},
            },
        )
        t.putcol("RANG_FLAGS", flags)
        t.addcols(
            w.maketabdesc(
                w.makearrcoldesc("RANG_WEIGHTS", 0.0, shape=[64, 4], valuetype="float")
            ),
            {
                "TYPE": "TiledShapeStMan",
                "NAME": "RANG_WEIGHTS_DM",
                "SPEC": {"DEFAULTTILESHAPE": [4, 16, 8]},
            },
        )
        t.putcol("RANG_WEIGHTS", weights)
    expected = _expected(
        before, RANG_MODEL=model, RANG_FLAGS=flags, RANG_WEIGHTS=weights
    )
    after = _snapshot(ms)
    for column in ("RANG_MODEL", "RANG_FLAGS", "RANG_WEIGHTS"):
        expected["colkeywords"][column] = after["colkeywords"][column]
        assert after["colkeywords"][column] == {}, column
    _check(after, expected, "MAIN")
    with oracle.open_table(ms) as cc:
        managers = cc.managers()
    assert managers["RANG_MODEL"] == "StandardStMan"
    assert managers["RANG_FLAGS"] == "TiledColumnStMan"
    assert managers["RANG_WEIGHTS"] == "TiledShapeStMan"


# -- 2. the writer: tables the core creates (E4) ----------------------------


@pytest.fixture
def creator():
    if not (core_ms_write.has_writer() and core_ms_write.has_creator()):
        pytest.skip("extension without the E4 table creation")
    return core_ms_write


def test_created_table_reads_back(creator, tmp_path):
    w, path = creator, tmp_path / "t"
    strings = ["", "a", "abcdefghij", "x" * 300, "z"]
    fixed = np.arange(15.0).reshape(5, 3)
    var = {
        0: np.arange(1, dtype=np.float32),
        2: np.arange(3, dtype=np.float32),
        4: np.arange(5, dtype=np.float32),
    }
    sa = [np.array(["s"] * row, dtype=object) for row in range(5)]
    sd = np.array([["p", "q" * r] for r in range(5)], dtype=object)
    t = w.create_table(
        path,
        [
            w.makescacoldesc("I", 0),
            w.makescacoldesc("S", ""),
            w.makearrcoldesc("D", 0.0, shape=[3], options=1),
            w.makearrcoldesc("V", 0.0, ndim=1, valuetype="float"),
            w.makearrcoldesc("SA", "", ndim=1),
            w.makearrcoldesc("SD", "", shape=[2], options=1),
        ],
        nrow=5,
    )
    t.putcol("I", np.arange(5, dtype=np.int32))
    t.putcol("S", strings)
    t.putcol("D", fixed)
    for row, cell in var.items():
        t.putcell("V", row, cell)
    for row in range(5):
        t.putcell("SA", row, np.array(["s"] * row))
    t.putcol("SD", sd)
    t.putkeyword("K", 1.5)
    t.putcolkeyword("D", "UNIT", "m")
    t.close()
    with oracle.open_table(path) as cc:
        assert cc.nrows == 5 and cc.colnames() == ["I", "S", "D", "V", "SA", "SD"]
        _same(cc.getcol("I"), np.arange(5, dtype=np.int32), "I")
        _same(cc.getcol("S"), np.array(strings, dtype=object), "S")
        _same(cc.getcol("D"), fixed, "D")
        for row, cell in var.items():  # rows 1 and 3 are undefined
            _same_cells(cc.getcells("V", row, 1), [cell], f"V row {row}")
        _same_cells(cc.getcells("SA"), sa, "SA")
        # casacure 3.8.35 cannot read a Direct fixed-shape string array, also
        # when python-casacore 3.8.1 wrote it (research/t1-casacure-ci.md);
        # the core's SD is checked by E4's python-casacore read-back.
        with pytest.raises(RuntimeError, match="bad string reference"):
            cc.getcol("SD")
        assert cc.keywords() == {"K": 1.5}
        assert cc.colkeywords("D") == {"UNIT": "m"}


def test_rows_added_and_removed_read_back(creator, tmp_path):
    w, path = creator, tmp_path / "t"
    t = w.create_table(
        path,
        [
            w.makescacoldesc("I", 0),
            w.makescacoldesc("B", False),
            w.makescacoldesc("S", ""),
        ],
        nrow=40,
    )
    label = [f"row {i} " * (i % 4) for i in range(70)]
    t.putcol("I", np.arange(40, dtype=np.int32))
    t.putcol("B", np.arange(40) % 3 == 0)
    t.putcol("S", label[:40])
    t.addrows(30)
    t.putcol("I", np.arange(40, 70, dtype=np.int32), 40, 30)
    t.putcol("B", np.arange(40, 70) % 3 == 0, 40, 30)
    t.putcol("S", label[40:], 40, 30)
    t.removerows([0, 5, 69, 33])
    t.close()
    keep = np.array([i for i in range(70) if i not in (0, 5, 33, 69)])
    with oracle.open_table(path) as cc:
        assert cc.nrows == 66
        _same(cc.getcol("I"), keep.astype(np.int32), "I")
        _same(cc.getcol("B"), keep % 3 == 0, "B")
        _same(cc.getcol("S"), np.array([label[i] for i in keep], dtype=object), "S")


def test_created_tiled_table_reads_back(creator, tmp_path):
    w, path = creator, tmp_path / "t"
    dminfo = {
        "*1": {
            "TYPE": "TiledShapeStMan",
            "NAME": "T",
            "SPEC": {"DEFAULTTILESHAPE": [4, 8, 8]},
            "COLUMNS": ["DATA"],
        }
    }
    data = (np.arange(10 * 64) * (1 + 1j)).astype(np.complex64).reshape(10, 16, 4)
    t = w.create_table(
        path,
        [w.makearrcoldesc("DATA", 0j, shape=[16, 4], valuetype="complex")],
        nrow=4,
        dminfo=dminfo,
    )
    t.addrows(6)
    t.putcol("DATA", data)
    t.close()
    with oracle.open_table(path) as cc:
        _same(cc.getcol("DATA"), data, "DATA")
        _same(cc.getcol("DATA", 3, 5), data[3:8], "DATA [3, 8)")
        assert cc.managers() == {"DATA": "TiledShapeStMan"}


def test_default_ms_reads_back(creator, tmp_path):
    path = tmp_path / "x.ms"
    creator.default_ms(path).close()
    subdirs = sorted(p.parent.name for p in path.glob("*/table.dat"))
    assert len(subdirs) == 12
    with oracle.open_table(path) as cc, core_ms.open_table(path) as core:
        assert cc.nrows == core.nrows == 0
        assert cc.colnames() == core.colnames()
        links = cc.subtables()
        assert sorted(links) == subdirs
        assert all(Path(v).resolve() == (path / k).resolve() for k, v in links.items())
    for name in subdirs:
        with (
            oracle.open_table(path / name) as cc,
            core_ms.open_table(path / name) as core,
        ):
            assert cc.nrows == core.nrows == 0, name
            assert cc.colnames() == core.colnames(), name


def test_caltable_reads_back(creator, tmp_path):
    path = tmp_path / "x.G"
    rng = np.random.default_rng(20261030)
    gains = [
        (rng.standard_normal((1, 2)) + 1j * rng.standard_normal((1, 2))).astype(
            np.complex64
        )
        for _ in range(3)
    ]
    snr = [rng.random((1, 2)).astype(np.float32) for _ in range(3)]
    flags = [np.array([[False, True]]), np.zeros((1, 2), bool), np.ones((1, 2), bool)]
    antenna1 = [2, 0, 1]
    main = {
        "TIME": [5e9] * 3,
        "FIELD_ID": [0] * 3,
        "SPECTRAL_WINDOW_ID": [0] * 3,
        "ANTENNA1": antenna1,
        "ANTENNA2": [0] * 3,
        "INTERVAL": [0.0] * 3,
        "SCAN_NUMBER": [1] * 3,
        "OBSERVATION_ID": [0] * 3,
        "CPARAM": gains,
        "PARAMERR": [np.zeros((1, 2), np.float32)] * 3,
        "FLAG": flags,
        "SNR": snr,
        "WEIGHT": [None] * 3,
    }
    positions = [np.array([1.0, 2.0, 3.0]) * i for i in range(3)]
    ant = {"NAME": ["a", "b", "c"], "POSITION": positions}
    creator.create_caltable(path, "G Jones", main, {"ANTENNA": ant}, "x.ms")
    order = np.argsort(antenna1)  # rows sorted by (spw, time, antenna1, antenna2)
    with oracle.open_table(path) as cc:
        assert cc.nrows == 3
        _same(cc.getcol("ANTENNA1"), np.array([0, 1, 2], np.int32), "ANTENNA1")
        _same(cc.getcol("TIME"), np.full(3, 5e9), "TIME")
        _same(cc.getcol("SCAN_NUMBER"), np.ones(3, np.int32), "SCAN_NUMBER")
        for column, values in (("CPARAM", gains), ("SNR", snr), ("FLAG", flags)):
            _same_cells(cc.getcells(column), [values[i] for i in order], column)
        keywords = cc.keywords()
        assert {
            k: keywords[k] for k in ("ParType", "MSName", "VisCal", "PolBasis")
        } == {
            "ParType": "Complex",
            "MSName": "x.ms",
            "VisCal": "G Jones",
            "PolBasis": "unknown",
        }
        links = cc.subtables()
    assert sorted(links) == sorted(
        ["OBSERVATION", "ANTENNA", "FIELD", "SPECTRAL_WINDOW", "HISTORY"]
    )
    assert all(Path(v).resolve() == (path / k).resolve() for k, v in links.items())
    with oracle.open_table(path / "ANTENNA") as cc:
        _same(cc.getcol("NAME"), np.array(["a", "b", "c"], dtype=object), "NAME")
        _same(cc.getcol("POSITION"), np.stack(positions), "POSITION")
