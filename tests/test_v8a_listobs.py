"""V8a listobs (research/v8a-listobs.md): the summary on an MS the core writer
builds inside each test, the CASA keyword layer's refusals, the command line,
and the WGS84 conversion."""

import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest
from rang import core_ms_write, listobs, tasks
from rang.core_cli import dispatch

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "w1_writeback", ROOT / "examples/w1_writeback.py"
)
w1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w1)

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)
FIELDS = (("J1939-6342", 5.146179, -1.111986), ("3C286", 3.539258, 0.532485))
# MeerKAT m000's ITRF position (m), from the fixture's ANTENNA table.
M000 = (5109271.49735416, 2006808.89302781, -3239130.73614072)


def make_ms(path):
    """6 baselines x 10 times; times 0-3 field 0 scan 1, 4-6 field 1 scan 2,
    7-9 field 0 scan 3 with state 1 for times 8-9 (two sub-entries)."""
    nrow = 60
    ms = w1.make_ms(path, nrow, 8)
    with core_ms_write.open_table(ms / "FIELD", readonly=False) as t:
        t.addrows(len(FIELDS))
        t.putcol("NAME", [f[0] for f in FIELDS])
        t.putcol("CODE", ["T", "T"])
        for k, (_, ra, dec) in enumerate(FIELDS):
            for col in ("PHASE_DIR", "DELAY_DIR", "REFERENCE_DIR"):
                t.putcell(col, k, np.array([[ra, dec]]))
    step = np.arange(nrow) // 6
    field = np.where((step >= 4) & (step <= 6), 1, 0).astype(np.int32)
    scan = np.select([step <= 3, step <= 6], [1, 2], 3).astype(np.int32)
    state = (step >= 8).astype(np.int32)
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("FIELD_ID", field)
        t.putcol("SCAN_NUMBER", scan)
        t.putcol("STATE_ID", state)
    with core_ms_write.open_table(ms / "ANTENNA", readonly=False) as t:
        t.addrows(4)
        t.putcol("NAME", [f"m00{a}" for a in range(4)])
        t.putcol("STATION", [f"m00{a}" for a in range(4)])
        t.putcol("DISH_DIAMETER", np.full(4, 13.5))
        for a in range(4):
            t.putcell("POSITION", a, np.array(M000) + 10.0 * a)
    return ms


@pytest.fixture
def ms(tmp_path):
    return make_ms(tmp_path / "m.ms")


def test_record_has_casa_keys_times_and_scans(ms):
    r = listobs.summary(ms)
    assert r["numrecords"] == 60 and r["nfields"] == 2 and r["timeref"] == "UTC"
    # TIME = 5e9 + 8 k, INTERVAL 8: from 5e9 - 4 to 5e9 + 72 + 4 seconds.
    assert r["BeginTime"] == pytest.approx((5.0e9 - 4) / 86400, abs=1e-12)
    assert r["EndTime"] == pytest.approx((5.0e9 + 76) / 86400, abs=1e-12)
    assert r["IntegrationTime"] == pytest.approx(80.0)
    assert sorted(k for k in r if k.startswith("scan_")) == [
        "scan_1",
        "scan_2",
        "scan_3",
    ]
    s1 = r["scan_1"]["0"]
    assert (s1["FieldId"], s1["FieldName"], s1["nRow"]) == (0, "J1939-6342", 24)
    assert s1["SpwIds"] == [0] and s1["StateId"] == 0 and s1["scanId"] == 1
    assert s1["IntegrationTime"] == pytest.approx(8.0)
    assert r["scan_2"]["0"]["FieldId"] == 1 and r["scan_2"]["0"]["nRow"] == 18
    sub = r["scan_3"]
    assert [sub[k]["StateId"] for k in ("0", "1")] == [0, 1]
    assert [sub[k]["nRow"] for k in ("0", "1")] == [6, 12]
    f1 = r["field_1"]
    assert f1["name"] == "3C286" and f1["code"] == "T"
    # RA in (-pi, pi], as CASA returns it.
    assert f1["direction"]["m0"]["value"] == pytest.approx(3.539258 - 2 * math.pi)
    assert f1["direction"]["refer"] == "J2000"


def test_additions_spw_antennas_fields(ms):
    r = listobs.summary(ms)
    (spw,) = r["spectral_windows"]
    assert spw["nchan"] == 8 and spw["frame"] == "TOPO" and spw["name"] == "L-band"
    assert spw["corr_types"] == ["XX", "XY", "YX", "YY"]
    assert len(spw["chan_freq_hz"]) == 8
    assert [a["name"] for a in r["antennas"]] == ["m000", "m001", "m002", "m003"]
    assert r["antennas"][0]["itrf_m"] == list(M000)
    assert [f["nrows"] for f in r["fields_extra"]] == [42, 18]
    assert r["sources"] == []
    text = listobs.text(r, "m.ms")
    assert "J1939-6342" in text and "XX XY YX YY" in text


def test_wgs84_round_trip():
    # Forward: geodetic to ITRF on WGS84, then back through `wgs84`.
    a, f = listobs.WGS84_A, listobs.WGS84_F
    e2 = f * (2 - f)
    for lon, lat, h in ((0.3743, -0.5363, 1050.0), (-2.0, 1.2, -30.0), (3.0, 0.0, 0)):
        n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        xyz = (
            (n + h) * math.cos(lat) * math.cos(lon),
            (n + h) * math.cos(lat) * math.sin(lon),
            (n * (1 - e2) + h) * math.sin(lat),
        )
        lo, la, hh = listobs.wgs84(xyz)
        assert abs(lo[0] - lon) < 1e-12 and abs(la[0] - lat) < 1e-12
        assert abs(hh[0] - h) < 1e-6


def test_tasks_listobs_refuses_selections_and_writes_listfile(ms, tmp_path, capsys):
    with pytest.raises(tasks.Unsupported, match="field='3C286'"):
        tasks.listobs(vis=str(ms), field="3C286")
    with pytest.raises(tasks.Unsupported, match="verbose=False"):
        tasks.listobs(vis=str(ms), verbose=False)
    with pytest.raises(tasks.Unsupported, match="listunfl=True"):
        tasks.listobs(vis=str(ms), listunfl=True)
    record = tasks.listobs(vis=str(ms), selectdata=False, cachesize=10)
    assert record["numrecords"] == 60 and "Fields: 2" in capsys.readouterr().out
    out = tmp_path / "l.txt"
    tasks.listobs(vis=str(ms), listfile=str(out))
    assert "Fields: 2" in out.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        tasks.listobs(vis=str(ms), listfile=str(out))
    tasks.listobs(vis=str(ms), listfile=str(out), overwrite=True)


def test_cli_json_and_refusals(ms, tmp_path, capsys):
    record = dispatch(["listobs", str(ms), "--json"])
    printed = json.loads(capsys.readouterr().out)
    assert printed["numrecords"] == record["numrecords"] == 60
    assert printed["scan_3"]["1"]["StateId"] == 1
    out = tmp_path / "l.json"
    dispatch(["listobs", str(ms), "--json", "--listfile", str(out)])
    assert json.loads(out.read_text(encoding="utf-8"))["nfields"] == 2
    with pytest.raises(SystemExit) as exc:
        dispatch(["listobs", str(ms), "--listfile", str(out)])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        dispatch(["listobs", str(tmp_path / "missing.ms")])
    assert exc.value.code == 2


def test_reads_no_visibility_column(ms, monkeypatch):
    from rang import core_ms

    seen = []
    original = core_ms.Table.getcol

    def spy(self, name, *args, **kwargs):
        seen.append((self.path.name, name))
        return original(self, name, *args, **kwargs)

    monkeypatch.setattr(core_ms.Table, "getcol", spy)
    listobs.summary(ms)
    main = {name for table, name in seen if table == ms.name}
    assert main == set(listobs.MAIN_COLUMNS)


# --- rang against CASA's archived output on the public fixture ----------------

ARCHIVE = ROOT / "research/results/v8a-listobs-casa-fixture.json"


@pytest.fixture(scope="module")
def fixture_mss(tmp_path_factory):
    import zipfile

    from rang.notebook import data as fixture_data

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


@pytest.mark.parametrize("scan", [1, 4, 5, 8, 9])
def test_fixture_matches_casa_archive(fixture_mss, scan):
    from rang.oracles import casa_listobs

    name = f"1672727931_sdp_l0_scan_{scan}.ms"
    if name not in fixture_mss:
        pytest.skip(f"fixture MS not present: {name}")
    run = json.loads(ARCHIVE.read_text(encoding="utf-8"))["runs"][f"fixture-scan{scan}"]
    result = casa_listobs.compare(
        listobs.summary(fixture_mss[name]), run["record"], run["msmd"], run["text"]
    )
    assert result["differences"] == [] and result["compared"] > 50
