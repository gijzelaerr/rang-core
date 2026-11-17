# SPDX-License-Identifier: MIT
"""Issue #34 (research/selfcal-memory.md): the streamed Sp and Sa solve
(`rang.cal_stream`) equals the one-call solve bit for bit, at any block
size, with flags, zero weights, zero and non-finite data, a cross-hand
model and an antenna without data; `stream="auto"` streams only an interval
that does not fit; the selfcal budget's own figure. Gate G1 (a) and (b)."""

import importlib.util
import shutil
from pathlib import Path

import numpy as np
import pytest
from rang import cal_gain, cal_selfcal, cal_stream, core_chunks, core_ms, core_ms_write
from rang import core_writeback as wb

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "test_c5_selfcal", ROOT / "tests/test_c5_selfcal.py"
)
c5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c5)

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)

TERMS = [
    {"name": "P", "type": "Sp", "solint": 3, "freqint": "inf"},
    {"name": "A", "type": "Sa", "solint": 3, "freqint": 4},
    {"name": "P", "type": "Sp", "solint": "inf", "freqint": 2},
    {"name": "A", "type": "Sa", "solint": "inf", "freqint": "inf"},
]


def awkward_ms(path):
    """C5's two-scan MS with noise, then: random flags, zero weights, zero
    and non-finite data, a FLAG_ROW, a cross-hand model, and antenna 5
    without unflagged data."""
    ms, _, row_block = c5.make_ms(path, "pa", noise=0.05)
    rng = np.random.default_rng(20261734)
    with core_ms_write.open_table(ms, readonly=False) as t:
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        flag = t.getcol("FLAG")
        flag |= rng.uniform(size=flag.shape) < 0.05
        flag[(a1 == 5) | (a2 == 5)] = True
        t.putcol("FLAG", flag)
        frow = t.getcol("FLAG_ROW")
        frow[7] = True
        t.putcol("FLAG_ROW", frow)
        w = t.getcol("WEIGHT")
        w[3, 0] = 0.0
        w[11, 3] = 0.0
        w *= rng.uniform(0.5, 1.5, w.shape).astype(np.float32)
        t.putcol("WEIGHT", w)
        d = t.getcol("DATA")
        d[5, 2, 0] = 0.0
        d[9, 1, 3] = np.nan
        t.putcol("DATA", d)
    m = c5.columns(ms, "MODEL_TRUE")[0].copy()
    m[..., 1] = 0.1 + 0.05j
    m[..., 2] = -0.07j
    m[..., 0] *= rng.uniform(0.8, 1.2, m.shape[:2]).astype(np.float32)
    with wb.WriteBack(ms, stage="test") as w:
        w.write("MODEL_TRUE", 0, m)
    return ms, np.arange(len(row_block))


def solve(ms, rows, term, **kw):
    return cal_selfcal.solve(
        ms, term, rows=rows, field_id=0, input_column="DATA", model_column="MODEL_TRUE",
        weight_column="WEIGHT", **kw,
    )  # fmt: skip


def same(a, b):
    assert a.iterations == b.iterations
    assert a.converged_fraction == b.converged_fraction
    assert np.array_equal(a.gains, b.gains)
    assert np.array_equal(a.flags, b.flags)
    assert np.array_equal(a.gain_time, b.gain_time)
    assert a.clipped == b.clipped


def cell_bytes_budget(rows, cells, ngain, cell_bytes=core_chunks.CELL_BYTES["selfcal"]):
    """A selfcal budget whose chunks hold `cells` cells after the rows and
    `ngain` gains of a streamed solve."""
    return core_chunks.ChainBudget(
        chunk_bytes=core_chunks.CHAIN_ROW_BYTES * rows
        + cal_stream.GAIN_BYTES * ngain
        + cell_bytes * cells,
        limit_gb=1.0,
        limit_text="1",
        cell_bytes=cell_bytes,
    )


def ngain(sol):
    return int(np.prod(sol.gains.shape[:3]))


@pytest.mark.parametrize("term", TERMS, ids=lambda t: f"{t['type']}-{t['solint']}")
def test_streamed_solve_is_bit_identical(tmp_path, term):
    ms, rows = awkward_ms(tmp_path / "x.ms")
    whole = solve(ms, rows, term, stream=False)
    assert whole.flags[:, :, 5].all()  # the antenna without data
    assert not whole.flags.all()
    streamed = solve(ms, rows, term, stream=True)
    assert streamed.settings["streamed"]["cells"] > 0
    same(whole, streamed)
    # Blocks of 1, 7 and 40 rows in the read pass.
    for nrows in (1, 7, 40):
        budget = cell_bytes_budget(len(rows), nrows * c5.NCHAN * 4, ngain(whole))
        parts = solve(ms, rows, term, stream=True, budget=budget)
        assert parts.settings["streamed"]["block_rows"] == nrows
        same(whole, parts)


def test_auto_streams_only_an_interval_that_does_not_fit(tmp_path):
    ms, rows = awkward_ms(tmp_path / "x.ms")
    term = {"name": "A", "type": "Sa", "solint": "inf", "freqint": "inf"}
    whole = solve(ms, rows, term, stream=False)
    pairs = c5.NANT * (c5.NANT - 1) // 2
    scan_cells = pairs * (c5.NINT // 2) * c5.NCHAN * 4  # one interval per scan
    fits = cell_bytes_budget(len(rows), scan_cells, ngain(whole))
    small = cell_bytes_budget(len(rows), scan_cells // 3, ngain(whole))
    held = solve(ms, rows, term, budget=fits)
    assert "streamed" not in held.settings
    same(whole, held)
    streamed = solve(ms, rows, term, budget=small)
    assert streamed.settings["streamed"]["block_rows"] == scan_cells // 3 // (
        c5.NCHAN * 4
    )
    same(whole, streamed)
    with pytest.raises(core_chunks.MemoryLimitError, match="one solution interval"):
        solve(ms, rows, term, budget=small, stream=False)
    tiny = cell_bytes_budget(len(rows), c5.NCHAN * 4 - 1, ngain(whole))
    with pytest.raises(core_chunks.MemoryLimitError, match="streamed solve needs"):
        solve(ms, rows, term, budget=tiny)


def test_row_weights_and_refusals(tmp_path):
    ms, rows = awkward_ms(tmp_path / "x.ms")
    with core_ms.open_table(ms / "ANTENNA") as t:
        nant = len(t.getcol("NAME"))
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ")[0], float)

    def field():
        return cal_gain._Field(
            ms, rows, data_column="DATA", model=None, model_column="MODEL_TRUE",
            weight_column="WEIGHT", sigma_column="SIGMA", tables=[], interp=[],
            nant=nant, field_id=0, solved="G", freq=freq, uvrange="",
        )  # fmt: skip

    fld = field()
    tb, _, _ = cal_selfcal.time_bins(
        fld.meta["TIME"], fld.meta["SCAN_NUMBER"], fld.meta["FIELD_ID"], 3
    )
    opts = {
        "nant": nant, "calmode": "ap", "refant": [0], "refantmode": "flex",
        "minsnr": 0.0, "minblperant": 0, "positions": None, "casa_rules": False,
        "max_iterations": 50, "stop_criterion": 1e-7, "stop_fraction": 0.99,
    }  # fmt: skip
    a, wa = cal_gain._solve_gain_field(
        fld, tb, nchan=len(freq), per_channel=False, budget=None, what="t", **opts
    )
    b, wb_ = cal_gain._solve_gain_field(
        field(), tb, nchan=len(freq), per_channel=False, budget=None, what="t",
        stream=True, **opts,
    )  # fmt: skip
    assert np.array_equal(wa, wb_)
    assert np.array_equal(a.gains, b.gains) and np.array_equal(a.flags, b.flags)
    assert np.isnan(b.snr).all() and np.isnan(b.err).all()
    with pytest.raises(ValueError, match="QuartiCal rules"):
        cal_gain._solve_gain_field(
            field(), tb, nchan=len(freq), per_channel=False, budget=None, what="t",
            stream=True, **{**opts, "casa_rules": True},
        )  # fmt: skip


def test_the_scratch_file_is_removed(tmp_path):
    ms, rows = awkward_ms(tmp_path / "x.ms")
    solve(ms, rows, TERMS[0], stream=True)
    assert not list(tmp_path.glob(".rang-stream-*"))


def test_selfcal_budget_has_its_own_figure():
    plan = core_chunks.Budget(8.0, 823_500, (256, 4))
    chain, selfcal = plan.chain(), plan.selfcal()
    assert chain.cell_bytes == core_chunks.CELL_BYTES["chain"]
    assert selfcal.cell_bytes == core_chunks.CELL_BYTES["selfcal"]
    assert selfcal.chunk_bytes == chain.chunk_bytes
    _, hard, _ = selfcal.plan(823_500, 256, 4, False)
    assert (
        hard
        == (chain.chunk_bytes - core_chunks.CHAIN_ROW_BYTES * 823_500)
        // core_chunks.CELL_BYTES["selfcal"]
    )


# --- the public fixture (gate G1 b) ----------------------------------------------


def test_streamed_equals_whole_on_the_public_fixture(tmp_path_factory, tmp_path):
    from rang.notebook import data as fixture_data

    source = fixture_data.find_fixture()
    if source is None:
        pytest.skip("public fixture not present (RANG_FIXTURE)")
    if source.suffix == ".zip":
        source = fixture_data.extract_fixture(source, tmp_path_factory.mktemp("fx"))
    ms = tmp_path / "scan9.ms"
    shutil.copytree(source, ms)
    with core_ms.open_table(ms) as t:
        nrow = int(t.nrows)
        shape = t.getcol("DATA", 0, 1).shape[1:]
        fields = np.asarray(t.getcol("FIELD_ID"))
    model = np.zeros(shape, np.complex64)
    model[:, 0] = model[:, 3] = 1.0  # 1 Jy at the phase centre

    def init(start, n):
        return np.broadcast_to(model, (n, *shape)).copy()

    with wb.WriteBack(ms, stage="test") as w:
        w.ensure_column("MODEL_POINT", init=init)
    field_id = int(fields[0])
    rows = np.flatnonzero(fields == field_id)
    for term in (
        {"name": "P", "type": "Sp", "solint": "inf", "freqint": "inf"},
        {"name": "A", "type": "Sa", "solint": "inf", "freqint": "inf"},
    ):
        kw = {
            "rows": rows, "field_id": field_id, "input_column": "DATA",
            "model_column": "MODEL_POINT", "weight_column": None,
        }  # fmt: skip
        whole = cal_selfcal.solve(ms, term, stream=False, **kw)
        streamed = cal_selfcal.solve(ms, term, stream=True, **kw)
        assert streamed.settings["streamed"]["cells"] > 0
        assert nrow >= len(rows)
        same(whole, streamed)
