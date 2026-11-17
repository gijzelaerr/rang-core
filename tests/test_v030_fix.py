"""v0.3.0 review fixes on branch v030-fix (research/v030-review.md): R-02,
B-13, B-16 and the write-back findings E5-22, E5-23 and E5-24."""

import json
import os
import shutil
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest
from rang import cal_gain, core_ms_write

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "python"
STRATEGY = ROOT / "examples" / "ms-to-image" / "strategy.yaml"

needs_writer = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


# -- R-02: a solve with every solution flagged ---------------------------------


def test_no_solutions_is_a_runtime_error_and_pickles():
    """Callers that caught RuntimeError still do; the chunk-task pool sends
    it between processes."""
    import pickle

    exc = cal_gain.NoSolutions("gaincal wrote no solutions for field 0")
    assert isinstance(exc, RuntimeError)
    back = pickle.loads(pickle.dumps(exc))
    assert type(back) is cal_gain.NoSolutions and str(back) == str(exc)


@pytest.fixture(scope="module")
def fixture_scan(tmp_path_factory):
    from rang.notebook import data as fixture_data

    source = fixture_data.find_fixture()
    if source is None:
        pytest.skip("public fixture not present (RANG_FIXTURE)")
    if source.is_dir():
        return source
    if fixture_data._sha256(source) != fixture_data.FIXTURE_SHA256:
        pytest.fail(f"{source} is not the pinned public fixture")
    dest = tmp_path_factory.mktemp("fixture")
    with zipfile.ZipFile(source) as zipped:
        for info in fixture_data._safe_members(zipped, fixture_data.FIXTURE_SCAN + "/"):
            zipped.extract(info, dest)
    return dest / fixture_data.FIXTURE_SCAN


# As tests/test_mcp_chain.py, with refant m000: the example strategy flags
# baselines m000-m001 and m000-m003 entirely on this scan, so with m000 as the
# only reference every G solution is flagged (found by the chain test, R-02).
R02_CONFIG = """\
    version: 1
    fields:
      fcal: [{field}]
      target: [{field}]
    flag:
      strategy: strategy.yaml
    calibrate:
      model: {{source: setjy, standard: Stevens-Reynolds 2016}}
      refant: m000
      minblperant: 2
      primary:
        field: [fcal]
        terms:
          - {{type: K, name: K, solint: inf}}
          - {{type: G, name: G, solint: inf, calmode: ap, preapply: [K], interp: [linear]}}
    run:
      stages: [flag, calibrate]
    """


@needs_writer
def test_fully_flagged_gaincal_ends_run_with_a_stage_failure(fixture_scan, tmp_path):
    """R-02: `rang-core run` exits 1 with `failed: calibrate: ...` and the
    state file says failed; before the fix it ended in a traceback."""
    from rang import core_ms

    work = tmp_path / "work"
    work.mkdir()
    ms = work / "scan9.ms"
    shutil.copytree(fixture_scan, ms)
    shutil.copyfile(STRATEGY, work / "strategy.yaml")
    with core_ms.open_table(ms / "FIELD") as t:
        field = t.getcol("NAME")[0]
    config = work / "r02.yaml"
    config.write_text(textwrap.dedent(R02_CONFIG.format(field=field)), encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PACKAGE), *filter(None, [env.get("PYTHONPATH")])]
    )
    done = subprocess.run(
        [sys.executable, "-m", "rang.core_cli", "run", str(config), str(ms)],
        capture_output=True,
        text=True,
        env=env,
        timeout=900,
        check=False,
    )
    assert done.returncode == 1, done.stderr
    assert "Traceback" not in done.stderr, done.stderr
    assert "rang-core run: failed: calibrate:" in done.stderr
    assert "wrote no solutions" in done.stderr
    assert "calibrate.refant" in done.stderr
    state = json.loads((Path(f"{ms}.rang-run") / "state.json").read_text("utf-8"))
    assert state["stages"]["flag"]["status"] == "done"
    assert state["stages"]["calibrate"]["status"] == "failed"
    assert "NoSolutions" in state["stages"]["calibrate"]["error"]


# -- B-13 and B-16: lightcurve --------------------------------------------------


def _strict(text):
    def refuse(name):
        raise ValueError(f"bare {name} in lightcurve.json")

    return json.loads(text, parse_constant=refuse)


def test_lightcurve_json_writes_null_for_values_that_are_not_finite(tmp_path):
    """B-13: an interval whose samples are all flagged has flux NaN; the JSON
    file holds null there (strict JSON), the CSV `nan`."""
    import numpy as np
    from rang import lightcurve as lc

    result = {
        "schema": "rang.lightcurve",
        "intervals": 2,
        "positions": [
            {
                "name": "A",
                "ra_deg": 1.0,
                "dec_deg": -2.0,
                "pixel": None,
                "pixel_offset_arcsec": None,
            }
        ],
        "time_mjd_s": [1.0, 2.0],
        "timesteps": [1, 1],
        "flux_jy": [[0.5], [float("nan")]],
        "flux_snapshot_jy": [[None], [None]],
        "sigma_meas_jy": [np.float64(0.1), np.float64("inf")],
        "weight_sum": [3.0, 0.0],
        "samples": [4, 0],
        "rows": [2, 2],
        "outside_grid": [None, None],
        "extra": np.array([1.0, np.nan]),
    }
    lc.write_outputs(result, tmp_path)
    text = (tmp_path / "lightcurve.json").read_text(encoding="utf-8")
    back = _strict(text)
    assert back["flux_jy"] == [[0.5], [None]]
    assert back["sigma_meas_jy"] == [0.1, None]
    assert back["extra"] == [1.0, None]
    assert "NaN" not in text and "Infinity" not in text
    # The returned result is not changed, and the CSV keeps Python's nan.
    assert np.isnan(result["flux_jy"][1][0])
    rows = (tmp_path / "lightcurve.csv").read_text(encoding="utf-8").splitlines()
    assert rows[2].split(",")[6] == "nan"
    # Readers that build float arrays get NaN back (examples/ts_p1_measure.py).
    assert np.isnan(np.array(back["flux_jy"], np.float64)[1, 0])


@pytest.fixture(scope="module")
def small_sim(tmp_path_factory):
    import importlib.util

    if not core_ms_write.has_creator():
        pytest.skip("extension built without the table writer")
    spec = importlib.util.spec_from_file_location(
        "ts_p1_sim", ROOT / "examples/ts_p1_sim.py"
    )
    sim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sim)
    out = tmp_path_factory.mktemp("v030lc")
    ms = sim.main(["tsp1-dev", str(out), "--ntime", "6", "--nant", "6", "--nchan", "4"])
    truth = json.loads((out / "tsp1-dev.truth.json").read_text(encoding="utf-8"))
    return Path(ms), truth


def test_lightcurve_refuses_a_field_on_two_data_descriptions(small_sim, tmp_path):
    """B-16: rows of the field on DATA_DESC_ID 1 were left out silently; now
    the command is refused, naming the data descriptions."""
    import numpy as np
    from rang import core_ms
    from rang import lightcurve as lc

    source, truth = small_sim
    pos = [(s["name"], s["ra_deg"], s["dec_deg"]) for s in truth["sources"]][:1]
    # One data description: runs.
    res = lc.light_curves(source, pos, field=3, images=False)
    assert res["intervals"] > 0
    ms = tmp_path / "two-ddid.ms"
    shutil.copytree(source, ms)
    with core_ms.open_table(ms) as t:
        ddid = t.getcol("DATA_DESC_ID")
        field = t.getcol("FIELD_ID")
    rows = np.flatnonzero(field == 3)
    ddid[rows[len(rows) // 2 :]] = 1
    t = core_ms_write.open_table(ms, readonly=False)
    try:
        t.putcol("DATA_DESC_ID", ddid, 0)
        t.flush()
    finally:
        t.close()
    with pytest.raises(lc.LightcurveError, match=r"data descriptions \[0, 1\]"):
        lc.light_curves(ms, pos, field=3, images=False)


# -- E5-22, E5-23, E5-24: write-back --------------------------------------------


def _w1():
    import importlib.util

    if not core_ms_write.has_creator():
        pytest.skip("extension built without the table writer")
    spec = importlib.util.spec_from_file_location(
        "w1_writeback", ROOT / "examples/w1_writeback.py"
    )
    w1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w1)
    return w1


def test_a_session_that_wrote_no_flags_is_not_refused(tmp_path):
    """E5-22: a failed session that never wrote FLAG left the flags as they
    were; the next session (and the pipeline's checks) do not refuse, so no
    one is told to restore an older flag version over them."""
    import numpy as np
    from rang import core_writeback as wb

    w1 = _w1()
    ms = w1.make_ms(tmp_path / "x.ms", 12, 4)
    f0 = w1.sha(ms, "FLAG")
    with pytest.raises(RuntimeError, match="boom"), wb.WriteBack(ms) as w:
        w.ensure_column("MODEL_DATA")
        raise RuntimeError("boom")
    journal = wb.read_journal(ms)
    assert journal["state"] == "failed" and "FLAG" not in journal["written"]
    assert not wb.flags_unfinished(journal)
    with wb.WriteBack(ms) as w:
        assert w.ensure_column("MODEL_DATA") is False
    assert w1.sha(ms, "FLAG") == f0
    # A session that wrote FLAG is still refused, as before.
    with pytest.raises(RuntimeError, match="boom"), wb.WriteBack(ms) as w:
        nchan, ncorr = w.cell
        w.write_flags(0, np.ones((2, nchan, ncorr), bool))
        raise RuntimeError("boom")
    assert wb.flags_unfinished(wb.read_journal(ms))
    with pytest.raises(wb.InterruptedWriteBack):
        wb.WriteBack(ms).begin()
    # A journal from before the `written` record, or from 0.2.0 (recorded
    # after the put), counts as unfinished.
    assert wb.flags_unfinished({"state": "open"})
    assert wb.flags_unfinished({"state": "failed", "written": ["MODEL_DATA"]})
    assert journal["written_before_put"] is True
    assert not wb.flags_unfinished({"state": "restored", "written": ["FLAG"]})


def test_a_half_initialised_column_is_initialised_again_after_a_restore(tmp_path):
    """E5-23: `restore_flags` marked the journal restored and the next session
    forgot that CORRECTED_DATA was half-initialised."""
    import numpy as np
    from rang import core_ms
    from rang import core_writeback as wb

    w1 = _w1()
    ms = w1.make_ms(tmp_path / "x.ms", 150, 8)

    class Stop(Exception):
        pass

    def hook(event, column, start, n):
        if event == "flushed" and column == "CORRECTED_DATA" and start > 0:
            raise Stop

    with pytest.raises(Stop), wb.WriteBack(ms, chunk_rows=32, on_chunk=hook) as w:
        nchan, ncorr = w.cell
        w.write_flags(0, np.ones((4, nchan, ncorr), bool))
        w.ensure_column("CORRECTED_DATA")
    assert wb.read_journal(ms)["initialising"] == ["CORRECTED_DATA"]
    wb.restore_flags(ms)
    assert wb.read_journal(ms)["state"] == "restored"
    with wb.WriteBack(ms) as w:
        assert w.ensure_column("CORRECTED_DATA") is False
    with core_ms.open_table(ms) as t:
        assert np.array_equal(t.getcol("CORRECTED_DATA"), t.getcol("DATA"))
    assert wb.read_journal(ms)["initialising"] == []


def test_a_read_only_ms_is_refused_before_anything_is_written(tmp_path):
    """E5-24: a read-only MS gave a raw "table.lock: Access is denied" after
    the flag backup and an open journal were written."""
    import stat

    from rang import core_writeback as wb
    from rang.formats import flagversions

    w1 = _w1()
    ms = w1.make_ms(tmp_path / "x.ms", 12, 4)
    target = ms / "table.dat"
    mode = target.stat().st_mode
    os.chmod(target, stat.S_IREAD)
    try:
        if os.access(target, os.W_OK):
            pytest.skip("this account can write read-only files (root)")
        with pytest.raises(PermissionError, match="is not writable"):
            wb.WriteBack(ms).begin()
    finally:
        os.chmod(target, mode)
    assert wb.read_journal(ms) is None
    assert flagversions.versions(ms) == []
    with wb.WriteBack(ms):
        pass
    assert wb.read_journal(ms)["state"] == "closed"
