"""The core table writer (research/e3-table-writer.md).

Writes go to copies of the task E MSs in a temporary directory; the inputs
live in ignored `outputs/` and the tests skip when they, the writer binding
(`MsWriter`, added by the coordinator to `core/py/src/lib.rs`) or, for the
byte-identity spot check, the frozen oracle run are absent. The full
comparison with python-casacore is `examples/check_ms_writer.py`.
"""

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest
from rang import core_ms, core_ms_write

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "outputs/tv-caracal-wsl-20261029-01/original.ms"
LUNO = ROOT / "outputs/luno-solve-20261029-02/work.ms"
ORACLE = ROOT / "outputs/e3-20261030-01"


def _copy(src, tmp_path):
    if not core_ms_write.has_writer():
        pytest.skip("extension built without the table writer")
    if not src.is_dir():
        pytest.skip(f"{src} not present")
    dst = tmp_path / src.name
    shutil.copytree(src, dst)
    return dst


def test_putcol_putcell_and_keywords_read_back(tmp_path):
    ms = _copy(FIXTURE, tmp_path)
    with core_ms.open_table(ms) as t:
        flag, rows, data = t.getcol("FLAG"), t.getcol("FLAG_ROW"), t.getcol("DATA")
        weights = t.getcol("WEIGHT_SPECTRUM", 10, 5)
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("FLAG", ~flag)
        t.putcol("FLAG_ROW", ~rows)
        t.putcol("WEIGHT_SPECTRUM", weights * 2, startrow=10, nrow=5)
        t.putcell("DATA", 3, data[3] + 1)
        t.putkeyword("RANG_D", 1.5)
        t.putcolkeyword("DATA", "RANG_UNIT", "Jy")
    with core_ms.open_table(ms) as t:
        assert np.array_equal(t.getcol("FLAG"), ~flag)
        assert np.array_equal(t.getcol("FLAG_ROW"), ~rows)
        assert np.array_equal(t.getcol("WEIGHT_SPECTRUM", 10, 5), weights * 2)
        got = t.getcol("DATA")
        assert np.array_equal(got[3], data[3] + 1)
        assert np.array_equal(np.delete(got, 3, 0), np.delete(data, 3, 0))


def test_indirect_columns_and_strings(tmp_path):
    ms = _copy(LUNO, tmp_path)
    with core_ms.open_table(ms) as t:
        flag, model = t.getcol("FLAG"), t.getcol("MODEL_DATA")
    names = ["m0", "a-rather-long-antenna-name", "x", "MeerKAT-07"]
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("FLAG", ~flag)
        t.putcol("MODEL_DATA", model * 2)
    with core_ms_write.open_table(ms / "ANTENNA", readonly=False) as a:
        a.putcol("NAME", names[: a.nrows()])
    with core_ms.open_table(ms) as t:
        assert np.array_equal(t.getcol("FLAG"), ~flag)
        assert np.array_equal(t.getcol("MODEL_DATA"), model * 2)
    with core_ms.open_table(ms / "ANTENNA") as a:
        assert list(a.getcol("NAME")) == names[: a.nrows]


def test_addcols_default_binding_and_tiled_managers(tmp_path):
    ms = _copy(FIXTURE, tmp_path)
    rng = np.random.default_rng(3)
    with core_ms.open_table(ms) as t:
        nrows = t.nrows
    model = (rng.standard_normal((nrows, 64, 4)) + 1j).astype(np.complex64)
    tiled = rng.random((nrows, 64, 4)) < 0.5
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.addcols(
            core_ms_write.maketabdesc(
                core_ms_write.makearrcoldesc(
                    "RANG_MODEL_DATA", 0j, ndim=2, valuetype="complex"
                )
            )
        )
        t.putcol("RANG_MODEL_DATA", model)
        t.addcols(
            core_ms_write.maketabdesc(
                core_ms_write.makearrcoldesc(
                    "RANG_FLAGS", False, shape=[64, 4], valuetype="boolean"
                )
            ),
            {
                "TYPE": "TiledColumnStMan",
                "NAME": "RANG_FLAGS_DM",
                "SPEC": {"DEFAULTTILESHAPE": [4, 16, 8]},
            },
        )
        t.putcol("RANG_FLAGS", tiled)
    with core_ms.open_table(ms) as t:
        assert t.columns["RANG_MODEL_DATA"]["manager_type"] == "StandardStMan"
        assert t.columns["RANG_FLAGS"]["manager_type"] == "TiledColumnStMan"
        assert np.array_equal(t.getcol("RANG_MODEL_DATA"), model)
        assert np.array_equal(t.getcol("RANG_FLAGS"), tiled)


def test_formerly_deferred_writes_work(tmp_path):
    # E3 refused these (E5); research/e5-table-writer-rest.md writes them.
    ms = _copy(FIXTURE, tmp_path)
    with core_ms_write.open_table(ms, readonly=False) as t:
        nrows = t.nrows()
        t.putcol("TIME", np.arange(nrows, dtype=np.float64))
        t.putcell("FLAG_CATEGORY", 0, np.ones((1, 4096, 4), bool))
    assert np.array_equal(
        core_ms_write.read_cells(ms, "TIME", 0, 3), np.arange(3, dtype=np.float64)
    )
    cell = core_ms_write.read_cells(ms, "FLAG_CATEGORY", 0, 2)
    assert cell[0].shape == (1, 4096, 4) and cell[0].all() and cell[1] is None


def test_the_lock_keeps_a_second_process_out(tmp_path):
    ms = _copy(FIXTURE, tmp_path)
    holder = textwrap.dedent(
        f"""
        import sys, time
        sys.path.insert(0, {str(ROOT / "python")!r})
        from rang import core_ms_write
        t = core_ms_write.open_table({str(ms)!r}, readonly=False)
        print("held", flush=True)
        time.sleep(4)
        t.close()
        """
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", holder], stdout=subprocess.PIPE, text=True
    )
    try:
        assert proc.stdout.readline().strip() == "held"
        with pytest.raises(OSError, match="locked"):
            core_ms_write.open_table(ms, readonly=False, lock_attempts=1, lock_wait=0)
    finally:
        proc.wait(timeout=60)
    core_ms_write.open_table(
        ms, readonly=False, lock_attempts=10, lock_wait=1.0
    ).close()


@pytest.mark.parametrize("case", ["F-flag", "F-flagrow", "L-flag", "F-keywords"])
def test_files_equal_casacore_for_frozen_cases(tmp_path, case):
    """Spot check of criterion 1 against the frozen oracle run."""
    if not (ORACLE / "cases.json").is_file():
        pytest.skip("frozen E3 oracle run not present")
    sys.path.insert(0, str(ROOT / "examples"))
    from check_ms_writer import Make, compare_trees, host_path, load_values
    from oracle_ms_write import apply

    entry = next(
        c for c in json.loads((ORACLE / "cases.json").read_text()) if c["name"] == case
    )
    ms = _copy(host_path(entry["input"]), tmp_path)
    with core_ms_write.open_table(ms, readonly=False) as t:
        apply(t, [tuple(op) for op in entry["ops"]], load_values(ORACLE, case), Make)
    assert compare_trees(ms, ORACLE / "casacore" / case)["identical"]
