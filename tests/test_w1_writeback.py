"""W1 write-back (research/w1-writeback.md): columns added and initialised as
CASA's clearcal leaves them, flags backed up and restored exactly, and an
interrupted write (SIGKILL) leaves the original flags recoverable. The MSs
are written by the core writer inside each test, so nothing here skips for
want of data."""

import importlib.util
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest
from rang import core_ms, core_ms_write
from rang import core_writeback as wb
from rang.formats import _aipsio, flagversions

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "w1_writeback", ROOT / "examples/w1_writeback.py"
)
w1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w1)

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


@pytest.fixture(params=["ssm", "tiled"])
def ms(request, tmp_path):
    return w1.make_ms(tmp_path / "x.ms", 150, 16, flag=request.param)


def test_columns_added_as_clearcal_and_flags_round_trip(ms):
    before = w1.hashes(ms)
    rng = np.random.default_rng(2)
    with wb.WriteBack(ms, stage="test", chunk_rows=64) as w:
        assert w.ensure_column("MODEL_DATA") and w.ensure_column("CORRECTED_DATA")
        assert w.ensure_column("WEIGHT_SPECTRUM")
        for start, n in w.chunks():
            w.write_flags(start, rng.random((n, 16, 4)) < 0.5, rng.random(n) < 0.5)
    journal = wb.read_journal(ms)
    assert journal["state"] == "closed" and journal["initialising"] == []
    assert flagversions.versions(ms)[0][0] == "rang_original"
    with core_ms.open_table(ms) as t:
        data, model = t.getcol("DATA"), t.getcol("MODEL_DATA")
        assert np.array_equal(t.getcol("CORRECTED_DATA"), data)
        assert np.all(model[..., [0, 3]] == 1) and np.all(model[..., [1, 2]] == 0)
        spectrum = t.getcol("WEIGHT_SPECTRUM")
        assert np.array_equal(spectrum, np.repeat(t.getcol("WEIGHT")[:, None], 16, 1))
        cols = t.columns
    for name, manager in (
        ("MODEL_DATA", "TiledModel"),
        ("CORRECTED_DATA", "TiledCorrected"),
    ):
        assert cols[name]["manager_type"] == "TiledShapeStMan"
        assert cols[name]["manager_name"] == manager
        assert cols[name]["dtype"] == "complex64" and cols[name]["shape"] == [4, 16]
    desc = _aipsio.column_descriptions(ms)
    assert desc["CORRECTED_DATA"]["keywords"] == {"UNIT": "Jy"}
    assert desc["MODEL_DATA"]["keywords"] == {}
    assert desc["CORRECTED_DATA"]["comment"] == "The data column"
    for col, h in before.items():
        if col not in ("FLAG", "FLAG_ROW"):
            assert w1.hashes(ms)[col] == h, col
    assert w1.sha(ms, "FLAG") != before["FLAG"]
    assert wb.restore_flags(ms, chunk_rows=37) == 150
    assert w1.sha(ms, "FLAG") == before["FLAG"]
    assert w1.sha(ms, "FLAG_ROW") == before["FLAG_ROW"]


def test_existing_columns_are_kept_and_backup_not_retaken(ms):
    with wb.WriteBack(ms) as w:
        w.ensure_column("CORRECTED_DATA")
        w.write("CORRECTED_DATA", 0, np.full((10, 16, 4), 3 + 1j, np.complex64))
        w.write_flags(0, np.ones((150, 16, 4), bool))
    saved = flagversions.load(ms, "rang_original")
    with wb.WriteBack(ms) as w:
        assert w.ensure_column("CORRECTED_DATA") is False
        with pytest.raises(ValueError):
            w.write("CORRECTED_DATA", 0, np.zeros((2, 8, 4), np.complex64))
        with pytest.raises(ValueError):
            w.write("NO_SUCH", 0, np.zeros((2, 16, 4), np.complex64))
    assert len(flagversions.versions(ms)) == 1
    again = flagversions.load(ms, "rang_original")
    assert all(np.array_equal(a, b) for a, b in zip(saved, again))
    with core_ms.open_table(ms) as t:
        assert np.all(t.getcol("CORRECTED_DATA", 0, 10) == 3 + 1j)


def test_a_version_renamed_but_not_listed_is_listed_on_the_next_save(ms):
    """E5-42 (WB-10): a kill between the rename of `flags.<name>` and its list
    line leaves a complete, unlisted version. The next save of the same flags
    lists it; a save of other flags is still refused."""
    path = flagversions.save(ms, "v1", comment="first")
    listing = flagversions.root(ms) / flagversions.LIST
    listing.write_text("", encoding="utf-8")  # as if killed before the line
    assert not flagversions.exists(ms, "v1")
    assert flagversions.save(ms, "v1", comment="first") == path
    assert flagversions.versions(ms) == [("v1", "first")]
    listing.write_text("", encoding="utf-8")
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("FLAG", ~t.getcol("FLAG", 0, 1), 0)
    with pytest.raises(ValueError, match="remove it first"):
        flagversions.save(ms, "v1")


def test_failed_session_refuses_until_restored(ms):
    f0 = w1.sha(ms, "FLAG")
    with pytest.raises(RuntimeError, match="boom"), wb.WriteBack(ms) as w:
        w.write_flags(0, np.ones((150, 16, 4), bool))
        raise RuntimeError("boom")
    assert wb.read_journal(ms)["state"] == "failed"
    with pytest.raises(wb.InterruptedWriteBack, match="restore_flags"):
        wb.WriteBack(ms).begin()
    with wb.WriteBack(ms, on_interrupted="restore") as w:
        assert w.read("FLAG", 0, 150).sum() < 150 * 64
    assert w1.sha(ms, "FLAG") == f0


def test_two_spectral_windows_of_different_widths_are_refused(tmp_path):
    ms = w1.make_ms(tmp_path / "x.ms", 12, 8)
    with core_ms_write.open_table(ms / "SPECTRAL_WINDOW", readonly=False) as s:
        s.addrows(1)
        s.putcell("CHAN_FREQ", 1, np.arange(4.0))
        s.putcol("NUM_CHAN", np.array([4], np.int32), 1)
    with core_ms_write.open_table(ms / "DATA_DESCRIPTION", readonly=False) as d:
        d.addrows(1)
        d.putcol("SPECTRAL_WINDOW_ID", np.array([1], np.int32), 1)
        d.putcol("POLARIZATION_ID", np.array([0], np.int32), 1)
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("DATA_DESC_ID", np.array([1], np.int32), 5)
    with pytest.raises(wb.UnsupportedLayout, match="one cell shape.*split"):
        wb.WriteBack(ms).begin()
    assert not flagversions.root(ms).exists()


CHILD = textwrap.dedent(
    """
    import os, signal, sys
    import numpy as np
    from rang import core_writeback as wb
    ms, when, count = sys.argv[1], sys.argv[2], int(sys.argv[3])
    seen = []
    def hook(event, column, start, n):
        if event == when and column in ("FLAG", "CORRECTED_DATA"):
            seen.append(start)
            if len(seen) == count:
                os.kill(os.getpid(), signal.SIGKILL)
    with wb.WriteBack(ms, chunk_rows=32, on_chunk=hook) as w:
        w.ensure_column("MODEL_DATA")
        w.ensure_column("CORRECTED_DATA")
        nchan, ncorr = w.cell
        for start, n in w.chunks():
            w.write_flags(start, np.ones((n, nchan, ncorr), bool), np.ones(n, bool))
    """
)


@pytest.mark.skipif(os.name != "posix", reason="SIGKILL and the fcntl lock are POSIX")
@pytest.mark.parametrize(
    "when,count",
    [("flushed", 6), ("written", 7), ("backup", 2), ("init", 3)],
    ids=["after-flush", "before-flush", "during-backup", "during-init"],
)
def test_sigkill_leaves_original_flags_recoverable(tmp_path, when, count):
    ms = w1.make_ms(tmp_path / "x.ms", 150, 16, flag="tiled")
    f0, r0 = w1.sha(ms, "FLAG"), w1.sha(ms, "FLAG_ROW")
    child = tmp_path / "child.py"
    child.write_text(CHILD)
    event = "flushed" if when == "init" else when
    # "init": the third flushed chunk of CORRECTED_DATA's initialisation;
    # MODEL_DATA's chunks do not count (the hook counts FLAG and
    # CORRECTED_DATA only), and FLAG is written after both columns.
    p = subprocess.run(
        [sys.executable, str(child), str(ms), event, str(count)], check=False
    )
    assert p.returncode == -9
    with core_ms.open_table(ms) as t:  # the MS still opens
        assert t.nrows == 150
        t.getcol("FLAG")
    if when == "backup":
        assert flagversions.versions(ms) == []
        assert wb.read_journal(ms) is None
        assert w1.sha(ms, "FLAG") == f0
        with wb.WriteBack(ms) as w:  # a rerun takes the backup afresh
            pass
        assert flagversions.versions(ms)[0][0] == "rang_original"
        assert w1.sha(ms, "FLAG") == f0
        return
    journal = wb.read_journal(ms)
    assert journal["state"] == "open"
    if when == "init":
        assert journal["initialising"] == ["CORRECTED_DATA"]
        assert w1.sha(ms, "FLAG") == f0
    else:
        assert w1.sha(ms, "FLAG") != f0  # the kill landed after a FLAG write
    with pytest.raises(wb.InterruptedWriteBack):
        wb.WriteBack(ms).begin()
    if when == "init":
        with wb.WriteBack(ms, on_interrupted="continue") as w:
            assert w.ensure_column("CORRECTED_DATA") is False  # re-initialised
        with core_ms.open_table(ms) as t:
            assert np.array_equal(t.getcol("CORRECTED_DATA"), t.getcol("DATA"))
        assert wb.read_journal(ms)["initialising"] == []
    wb.restore_flags(ms)
    assert w1.sha(ms, "FLAG") == f0 and w1.sha(ms, "FLAG_ROW") == r0
    assert wb.read_journal(ms)["state"] in ("restored", "closed")
    with wb.WriteBack(ms):
        pass


def test_column_descriptions_read_typed_keywords(tmp_path):
    ms = w1.make_ms(tmp_path / "x.ms", 6, 4)
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcolkeyword("DATA", "RANG_I", np.int32(3))
        t.putcolkeyword("DATA", "RANG_F", np.float32(1.5))
        t.putcolkeyword("DATA", "RANG_A", np.array([1.0, 2.0]))
    kw = _aipsio.column_descriptions(ms)["DATA"]["keywords"]
    assert kw["UNIT"] == "Jy"
    assert kw["RANG_I"].dtype == np.int32 and kw["RANG_I"] == 3
    assert kw["RANG_F"].dtype == np.float32
    assert np.array_equal(kw["RANG_A"], [1.0, 2.0])
    assert (
        _aipsio.column_descriptions(ms)["TIME"]["keywords"]["MEASINFO"]["type"]
        == "epoch"
    )
