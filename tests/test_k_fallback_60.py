# SPDX-License-Identifier: MIT
"""Issue #60 (research/k-fallback-60.md, the synthetic cases through the
pipeline path): `rang-core run` calibrate with K, G and B on a calibrator
whose baselines to the reference antenna are flagged. Case (i): two
antennas lose their baseline to m000, which keeps its others (#51's v4
pattern): with `refantmode` flex (the default) K, G and B flag no antenna,
and K's delays are the truth; with strict, K flags exactly those two, as
CASA. Case (ii): every baseline of m000 flagged: the solves fall back to
m001 and flag only m000, which has no data."""

import importlib.util
import shutil
from pathlib import Path

import numpy as np
import pytest
from rang import core_ms, core_ms_write
from rang.formats import caltable

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "w1_k60", ROOT / "examples/w1_writeback.py"
)
w1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w1)
_spec2 = importlib.util.spec_from_file_location(
    "w2_k60", ROOT / "tests/test_w2_commands.py"
)
w2 = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(w2)

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)

NANT, NCHAN, NINT = 8, 32, 20
CUT = ((0, 3), (0, 5))

CONFIG = """\
version: 1
fields: {fcal: [CAL]}
flag: {strategy: strategy.yaml}
calibrate:
  refant: [m000, m001]
  minblperant: 3
  REFANTMODE
  primary:
    terms:
      - {type: K, name: K}
      - {type: G, name: G, preapply: [K], interp: [linear]}
      - {type: B, name: B, preapply: [K, G]}
run:
  stages: [calibrate]
"""


def make(path, seed=60):
    pairs = NANT * (NANT - 1) // 2
    ms = w1.make_ms(path, pairs * NINT, NCHAN, flag="tiled", nant=NANT)
    base = np.array([5109224.0, 2006790.0, -3239100.0])
    with core_ms_write.open_table(ms / "ANTENNA", readonly=False) as t:
        t.addrows(NANT)
        t.putcol("POSITION", base + 150.0 * np.arange(NANT)[:, None] * [1, 0.5, 0.2])
        t.putcol("NAME", [f"m{a:03d}" for a in range(NANT)])
    with core_ms_write.open_table(ms / "FIELD", readonly=False) as t:
        t.addrows(1)
        t.putcol("NAME", ["CAL"])
        t.putcol("PHASE_DIR", np.array([[[0.0, -1.0]]]))
    rng = np.random.default_rng(seed)
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freq = t.getcol("CHAN_FREQ")[0]
    with core_ms.open_table(ms) as t:
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        shape = t.getcol("DATA").shape
    tau = rng.uniform(-2e-9, 2e-9, (NANT, 2))
    phase = rng.uniform(-np.pi, np.pi, (NANT, 2))
    amp = rng.uniform(0.8, 1.2, (NANT, 2))
    bp = 1 + 0.05 * rng.standard_normal((NANT, NCHAN, 2))
    nu = freq - freq[NCHAN // 2]
    g = (amp * np.exp(1j * phase))[:, None, :] * bp
    g = g * np.exp(2j * np.pi * tau[:, None, :] * nu[None, :, None])
    data = np.zeros(shape, np.complex64)
    data[..., 0] = g[a1, :, 0] * np.conj(g[a2, :, 0])
    data[..., 3] = g[a1, :, 1] * np.conj(g[a2, :, 1])
    data += 1e-3 * (rng.standard_normal(shape) + 1j * rng.standard_normal(shape))
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("DATA", data)
        t.putcol("FLAG", np.zeros(shape, bool))
        t.putcol("FLAG_ROW", np.zeros(len(a1), bool))
        t.putcol("WEIGHT", np.ones((len(a1), 4), np.float32))
    return ms, tau


def cut(ms, baselines):
    with core_ms.open_table(ms) as t:
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        flag = t.getcol("FLAG")
    for p, q in baselines:
        flag[(a1 == p) & (a2 == q)] = True
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("FLAG", flag)


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    return make(tmp_path_factory.mktemp("k60") / "src.ms")


def run(source, tmp_path, baselines, refantmode=None):
    ms = Path(shutil.copytree(source[0], tmp_path / "x.ms"))
    cut(ms, baselines)
    (tmp_path / "strategy.yaml").write_text(w2.STRATEGY, encoding="utf-8")
    line = f"refantmode: {refantmode}" if refantmode else ""
    config = tmp_path / "config.yaml"
    config.write_text(CONFIG.replace("REFANTMODE", line), encoding="utf-8")
    state = w2.cli("run", config, ms)
    assert state["stages"]["calibrate"]["status"] == "done"
    out = ms.with_name("x.ms.rang-run") / "calibrate"
    return {n: caltable.read(out / n).main for n in ("K", "G", "B")}


def flagged_antennas(main):
    flag = np.asarray([np.asarray(f) for f in main["FLAG"]])
    ant = np.asarray(main["ANTENNA1"])
    return sorted(
        {int(a) for a, f in zip(ant, flag, strict=True) if np.asarray(f).all()}
    )


def delays_ns(main):
    fp = np.asarray([np.asarray(f) for f in main["FPARAM"]])  # (row, chan, hand), ns
    return np.asarray(main["ANTENNA1"]), fp[:, 0, :]


def test_flex_solves_antennas_cut_off_from_the_refant(source, tmp_path):
    tables = run(source, tmp_path, CUT)
    for name in ("K", "G", "B"):
        assert flagged_antennas(tables[name]) == [], name
    ant, tau = delays_ns(tables["K"])
    truth = source[1] * 1e9
    want = truth[ant] - truth[0]
    assert np.abs(tau - want).max() < 0.02


def test_strict_flags_them_as_casa(source, tmp_path):
    tables = run(source, tmp_path, CUT, refantmode="strict")
    assert flagged_antennas(tables["K"]) == [3, 5]


def test_every_refant_baseline_flagged_falls_back_to_the_next_refant(source, tmp_path):
    allzero = [(0, q) for q in range(1, NANT)]
    tables = run(source, tmp_path, allzero)
    for name in ("K", "G", "B"):
        assert flagged_antennas(tables[name]) == [0], name
    ant, tau = delays_ns(tables["K"])
    truth = source[1] * 1e9
    live = ant != 0
    want = truth[ant[live]] - truth[1]
    assert np.abs(tau[live] - want).max() < 0.02
