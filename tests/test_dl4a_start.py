# SPDX-License-Identifier: MIT
"""DL4a (issue #41, research/dl4a-screen.md): the gain solve's optional
start. No start is today's solve bit for bit; a start at the converged
solution stops within three iterations at the same gains; the start is
refused where it is not implemented (Sd, averages, the streamed path)."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from rang import core_ms_write

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "test_selfcal_memory_for_dl4a", ROOT / "tests/test_selfcal_memory.py"
)
sm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sm)

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


@pytest.mark.parametrize("term", sm.TERMS, ids=lambda t: f"{t['type']}-{t['solint']}")
def test_no_start_is_todays_solve(tmp_path, term):
    ms, rows = sm.awkward_ms(tmp_path / "a.ms")
    a = sm.solve(ms, rows, term, stream=False)
    b = sm.solve(ms, rows, term, stream=False, start=None)
    sm.same(a, b)


@pytest.mark.parametrize("term", sm.TERMS, ids=lambda t: f"{t['type']}-{t['solint']}")
def test_a_converged_start_stops_early_at_the_same_gains(tmp_path, term):
    ms, rows = sm.awkward_ms(tmp_path / "a.ms")
    a = sm.solve(ms, rows, term, stream=False)
    b = sm.solve(ms, rows, term, stream=False, start=a.gains)
    assert b.iterations <= 3, (a.iterations, b.iterations)
    assert b.iterations <= a.iterations
    live = ~(a.flags | b.flags)
    assert np.max(np.abs(a.gains - b.gains)[live]) < 1e-5


def test_start_is_refused_where_not_implemented(tmp_path):
    ms, rows = sm.awkward_ms(tmp_path / "a.ms")
    sp = sm.TERMS[0]
    a = sm.solve(ms, rows, sp, stream=False)
    with pytest.raises(ValueError, match="one-call"):
        sm.solve(ms, rows, sp, stream=True, start=a.gains)
    with pytest.raises(ValueError, match="one-call"):
        sm.solve(ms, rows, sp, average_time=True, start=a.gains)
    with pytest.raises(ValueError, match="Sp and Sa"):
        sm.solve(ms, rows, {"name": "K", "type": "Sd", "solint": "inf"}, start=a.gains)
