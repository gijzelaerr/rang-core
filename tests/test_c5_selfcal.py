"""C5 (research/c5-selfcal.md): self-calibration terms Sp, Sa and Sd, their
solution intervals, the apply, the configuration and the `selfcal` stage
with a stand-in gemclean, on Measurement Sets written inside each test.
The simulated truth and the QuartiCal oracle are `examples/check_c5.py`."""

import importlib.util
import json
import os
import textwrap
from pathlib import Path

import numpy as np
import pytest
from rang import cal_gain, cal_selfcal, core_cli, core_config, core_ms, core_ms_write
from rang import core_pipeline as pipe
from rang import core_writeback as wb
from rang.formats import flagversions

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "w1_writeback", ROOT / "examples/w1_writeback.py"
)
w1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w1)
_spec = importlib.util.spec_from_file_location(
    "test_g6_model", ROOT / "tests/test_g6_model.py"
)
g6 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g6)

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)
POSIX = pytest.mark.skipif(os.name != "posix", reason="POSIX only")

NANT, NCHAN, NINT = 6, 8, 12  # two scans of 6 integrations
CENTRE = (0.5, -0.6)
FLUX = 2.0


def gains_of(kind, nbin, freq, seed=20261341):
    """Diagonal gains (bin, chan, antenna, hand) of `kind` (pa or delay)."""
    rng = np.random.default_rng(seed)
    if kind == "pa":
        amp = 1 + rng.uniform(-0.1, 0.1, (nbin, NANT, 2))
        ph = rng.uniform(-0.6, 0.6, (nbin, NANT, 2))
        g = amp * np.exp(1j * ph)
        return np.broadcast_to(g[:, None], (nbin, len(freq), NANT, 2)).copy()
    tau = rng.uniform(-0.5e-9, 0.5e-9, (nbin, NANT, 2))
    ph = rng.uniform(-0.4, 0.4, (nbin, NANT, 2))
    arg = ph[:, None] + 2 * np.pi * tau[:, None] * (freq[None, :, None, None] - 1.3e9)
    return np.exp(1j * arg)


def make_ms(path, kind="pa", block=3, noise=0.0):
    """Two scans of 6 integrations on NANT antennas; DATA = g_p M g_q^H for
    a FLUX Jy point at the phase centre (M), MODEL_TRUE = M, the gains
    constant over `block` integrations from each scan start. Returns
    (ms, gains per block, block of each row)."""
    pairs = NANT * (NANT - 1) // 2
    ms = w1.make_ms(path, pairs * NINT, NCHAN, flag="tiled", nant=NANT)
    base = np.array([5109224.0, 2006790.0, -3239100.0])
    with core_ms_write.open_table(ms / "ANTENNA", readonly=False) as t:
        t.addrows(NANT)
        t.putcol("POSITION", base + 150.0 * np.arange(NANT)[:, None] * [1, 0.5, 0.2])
        t.putcol("NAME", [f"m{a:03d}" for a in range(NANT)])
    with core_ms_write.open_table(ms / "FIELD", readonly=False) as t:
        t.addrows(1)
        t.putcol("NAME", ["TGT"])
        t.putcol("PHASE_DIR", np.array([[list(CENTRE)]]))
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ")[0], float)
    integration = np.arange(pairs * NINT) // pairs
    scan = 1 + (integration >= NINT // 2)
    within = integration - (NINT // 2) * (scan - 1)
    row_block = (scan - 1) * (NINT // 2 // block) + within // block
    nblock = int(row_block.max()) + 1
    g = gains_of(kind, nblock, freq)
    with core_ms_write.open_table(ms, readonly=False) as t:
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        t.putcol("SCAN_NUMBER", scan.astype(np.int32))
        t.putcol("FLAG", np.zeros((len(a1), NCHAN, 4), bool))
        t.putcol("FLAG_ROW", np.zeros(len(a1), bool))
        t.putcol("WEIGHT", np.ones((len(a1), 4), np.float32))
        rng = np.random.default_rng(20261342)
        u = rng.uniform(-300, 300, (len(a1), 3))
        t.putcol("UVW", u)
        gp, gq = g[row_block, :, a1], np.conj(g[row_block, :, a2])
        v = np.zeros((len(a1), NCHAN, 4), complex)
        v[..., 0] = gp[..., 0] * FLUX * gq[..., 0]
        v[..., 3] = gp[..., 1] * FLUX * gq[..., 1]
        if noise:
            v += noise * (
                rng.standard_normal(v.shape) + 1j * rng.standard_normal(v.shape)
            )
        t.putcol("DATA", v.astype(np.complex64))
    with wb.WriteBack(ms, stage="test") as w:
        m = np.zeros((len(a1), NCHAN, 4), np.complex64)
        m[..., 0] = m[..., 3] = FLUX
        w.ensure_column("MODEL_TRUE", init=lambda s, n: m[s : s + n])
    return ms, g, row_block


def columns(ms, *names):
    with core_ms.open_table(ms) as t:
        return [t.getcol(n) for n in names]


def products(g, flags=None):
    if flags is None:
        flags = np.zeros(g.shape, bool)
    return cal_gain.baseline_products(g, flags)[:2]


# --- intervals ----------------------------------------------------------------


def test_time_bins_follow_each_scan_and_never_cross_one():
    time = np.repeat(100.0 + 8.0 * np.arange(10), 3)
    scan = np.repeat([1] * 7 + [2] * 3, 3)
    for solint, per_scan in (
        (3, [3, 1]),
        ("int", [7, 3]),
        ("inf", [1, 1]),
        (100, [1, 1]),
        ("2", [4, 2]),
    ):
        tb, bin_scan, gain_time = cal_selfcal.time_bins(time, scan, 0, solint)
        assert [int((bin_scan == s).sum()) for s in (1, 2)] == per_scan, solint
        for b in range(len(bin_scan)):
            assert len(np.unique(scan[tb == b])) == 1
            assert gain_time[b] == np.unique(time[tb == b]).mean()
        assert np.all(np.diff(gain_time) > 0)
    # Seconds are CASA's bins (rang.cal_gain.solint_bins), renumbered in time.
    tb, bin_scan, _ = cal_selfcal.time_bins(time, scan, 0, "16s")
    ref, _ = cal_gain.solint_bins(time, scan, np.zeros_like(scan), "16s", "")
    assert len(np.unique(tb)) == len(np.unique(ref))
    for b in np.unique(ref):
        assert len(np.unique(tb[ref == b])) == 1
    with pytest.raises(ValueError):
        cal_selfcal.time_bins(time, scan, 0, 0)


def test_freq_bins():
    freq = np.arange(10) * 1e6 + 1e9
    fb, gf = cal_selfcal.freq_bins(freq, 4)
    assert fb.tolist() == [0, 0, 0, 0, 1, 1, 1, 1, 2, 2]
    assert np.allclose(gf, [freq[:4].mean(), freq[4:8].mean(), freq[8:].mean()])
    fb, gf = cal_selfcal.freq_bins(freq, "inf")
    assert fb.max() == 0 and gf[0] == freq.mean()


# --- solve and apply ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "term", "tol"),
    [
        ("pa", {"type": "Sa", "solint": 3}, 1e-5),
        ("pa", {"type": "Sa", "solint": 3, "freqint": 4}, 1e-5),
        ("delay", {"type": "Sd", "solint": 3}, 1e-4),
    ],
)
def test_a_noiseless_perfect_model_gives_the_gains_back(tmp_path, kind, term, tol):
    ms, g, row_block = make_ms(tmp_path / "x.ms", kind)
    rows = np.arange(len(row_block))
    sol = cal_selfcal.solve(
        ms, {"name": "S", **term}, rows=rows, field_id=0, input_column="DATA",
        model_column="MODEL_TRUE", weight_column="WEIGHT", gain_clip=(0.5, 2.0),
    )  # fmt: skip
    assert sol.gains.shape[0] == 4  # two bins per scan
    assert np.array_equal(sol.time_bin, row_block)
    if kind == "delay":
        assert sol.gains.shape[1] == NCHAN
        truth = g
    else:
        nf = sol.gains.shape[1]
        assert nf == (2 if term.get("freqint") == 4 else 1)
        truth = g[:, :: NCHAN // nf][:, :nf]
    p, ok = products(sol.gains, sol.flags)
    pt, _ = products(truth)
    assert ok.all()
    assert np.max(np.abs(p - pt) / np.abs(pt)) < tol
    # Applied: the corrected data equal the model.
    with wb.WriteBack(ms, stage="test") as w:
        cal_selfcal.apply(w, sol, input_column="DATA", output_column="CORRECTED_DATA")
    out, model, flag = columns(ms, "CORRECTED_DATA", "MODEL_TRUE", "FLAG")
    assert not flag.any()
    hands = out[..., (0, 3)]
    assert np.max(np.abs(hands - model[..., (0, 3)])) < 10 * tol * FLUX
    # The store reads back the same gains on the same grid.
    store = cal_selfcal.to_store(
        sol, tmp_path / "g.qc", [f"m{a:03d}" for a in range(NANT)]
    )
    gains, flags, times, freqs, scans = cal_selfcal.read_store(store, "S")
    assert np.array_equal(gains, sol.gains) and np.array_equal(times, sol.gain_time)
    assert np.array_equal(freqs, sol.gain_freq) and scans.tolist() == [1, 1, 2, 2]
    assert not flags.any()


def test_phase_only_and_the_gain_clip(tmp_path):
    ms, g, row_block = make_ms(tmp_path / "x.ms", "pa")
    rows = np.arange(len(row_block))
    sol = cal_selfcal.solve(
        ms, {"name": "S", "type": "Sp", "solint": 3}, rows=rows, field_id=0,
        input_column="DATA", model_column="MODEL_TRUE", weight_column="WEIGHT",
    )  # fmt: skip
    assert np.allclose(np.abs(sol.gains), 1.0)
    p, _ = products(sol.gains)
    pt, _ = products(g[:, :1])
    assert np.max(np.abs(np.angle(p / pt))) < 0.02  # amplitudes left
    # Gains above the clip are flagged and flag the data they touch.
    with wb.WriteBack(ms, stage="test") as w:
        w.write("MODEL_TRUE", 0, columns(ms, "MODEL_TRUE")[0] / 4)
    sol = cal_selfcal.solve(
        ms, {"name": "S", "type": "Sa", "solint": 3}, rows=rows, field_id=0,
        input_column="DATA", model_column="MODEL_TRUE", weight_column="WEIGHT",
        gain_clip=(0.5, 1.5),
    )  # fmt: skip
    assert sol.clipped == sol.flags.size and sol.flags.all()  # |g| near 2
    with wb.WriteBack(ms, stage="test") as w:
        cal_selfcal.apply(w, sol, input_column="DATA", output_column="CORRECTED_DATA")
    assert columns(ms, "FLAG")[0].all()


def test_chunked_solve_is_bit_identical(tmp_path):
    from rang import core_chunks

    ms, _, row_block = make_ms(tmp_path / "x.ms", "pa", noise=0.05)
    rows = np.arange(len(row_block))
    for term in ({"type": "Sa", "solint": 3}, {"type": "Sd", "solint": 3}):
        kw = {
            "rows": rows, "field_id": 0, "input_column": "DATA", "model_column": "MODEL_TRUE",
            "weight_column": "WEIGHT",
        }  # fmt: skip
        whole = cal_selfcal.solve(ms, {"name": "S", **term}, **kw)
        budget = core_chunks.ChainBudget(
            chunk_bytes=core_chunks.CHAIN_ROW_BYTES * len(rows)
            + core_chunks.CELL_BYTES["chain"] * 15 * 3 * NCHAN * 4
        )
        parts = cal_selfcal.solve(ms, {"name": "S", **term}, budget=budget, **kw)
        assert np.array_equal(whole.gains, parts.gains)
        assert np.array_equal(whole.flags, parts.flags)


# --- configuration ----------------------------------------------------------------


def _resolved(text):
    raw = core_config._yaml().safe_load(textwrap.dedent(text))
    return core_config.resolve(raw)


def test_selfcal_configuration_errors_and_refusals():
    config, errors = _resolved(
        """\
        version: 1
        selfcal:
          rounds: 1
          terms: [{type: Sp}, {type: Sa, freqint: 60s}]
          output_column: DATA
          gain_clip: [2, 1]
        """
    )
    paths = [p for p, _ in errors]
    assert "selfcal.terms" in paths  # two terms for one round
    assert "selfcal.terms[1].freqint" in paths
    assert "selfcal.output_column" in paths and "selfcal.gain_clip" in paths
    config, errors = _resolved(
        """\
        version: 1
        calibrate: {refant: auto}
        image: {size: 64, scale: 2asec}
        selfcal: {terms: [{type: complex}]}
        """
    )
    assert errors == []
    refused = {r.path for r in core_config.refusals(config, ["selfcal"])}
    # Since task E2, selfcal resolves auto itself (core_pipeline.selfcal_refant).
    assert refused == {"selfcal.terms[0].type"}
    # E2-A's selfcal part validates; its automatic mask needs an mgain (G4).
    raw = core_config.load(ROOT / "tests/data/w2/e2a.yaml")
    config, errors = core_config.resolve(raw)
    assert errors == []
    left = core_config.refusals(config, ["selfcal"])
    assert [(r.path, r.task) for r in left] == [("image.auto_mask", "")]
    assert pipe.selfcal_round_term(config, 1)["type"] == "Sp"
    assert pipe.selfcal_round_term(config, 2)["type"] == "Sa"
    assert pipe.selfcal_round_term(config, 3)["type"] == "Sa"  # the last repeats


# --- the stage -------------------------------------------------------------------------


def fake_gemclean(tmp_path):
    """A stand-in gemclean: writes `<name>-model.fits` (a FLUX Jy point at
    the phase centre) and `<name>-image.fits` after `-name`."""
    template = tmp_path / "template-model.fits"
    image = np.zeros((32, 32))
    image[16, 16] = FLUX
    g6.write_fits(template, image, 2.0 / 3600, CENTRE)
    path = tmp_path / "fake-gemclean"
    path.write_text(
        "#!/bin/sh\n"
        'while [ $# -gt 0 ]; do [ "$1" = -name ] && name=$2; shift; done\n'
        f'cp "{template}" "$name-model.fits"\n'
        'echo fake > "$name-image.fits"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def write_config(tmp_path, extra=""):
    text = textwrap.dedent(
        f"""\
        version: 1
        fields: {{target: [TGT]}}
        image: {{gemclean: {fake_gemclean(tmp_path)}, size: 32, scale: 2asec}}
        selfcal:
          rounds: 2
          terms: [{{type: Sp, solint: 3}}, {{type: Sa, solint: 3}}]
          refant: m001
        """
    )
    path = tmp_path / "config.yaml"
    path.write_text(text + extra, encoding="utf-8")
    return path


@POSIX
def test_the_stage_runs_rounds_and_writes_corrected_data(tmp_path, capsys):
    ms, g, _row_block = make_ms(tmp_path / "x.ms", "pa")
    config = write_config(tmp_path, "  input_column: DATA\n")
    core_cli.dispatch(["selfcal", str(config), str(ms)])
    run = Path(str(ms) + ".rang-run")
    summary = json.loads((run / "selfcal" / "summary.json").read_text())
    (field,) = summary["fields"]
    assert [r["term"]["type"] for r in field["rounds"]] == ["Sp", "Sa"]
    assert [r["image"]["column"] for r in field["rounds"]] == ["DATA", "CORRECTED_DATA"]
    assert field["final_image"]["column"] == "CORRECTED_DATA"
    for r in field["rounds"]:
        assert r["solve"]["time_bins_per_scan"] == {"1": 2, "2": 2}
    assert summary["refant"] == 1
    out, model = columns(ms, "CORRECTED_DATA", "MODEL_DATA")
    assert np.max(np.abs(out[..., (0, 3)] - model[..., (0, 3)])) < 1e-4
    assert np.allclose(model[..., 0], FLUX, atol=1e-5)
    store = field["rounds"][1]["store"]
    gains, *_ = cal_selfcal.read_store(store, "Sa")
    p, _ = products(gains)
    pt, _ = products(g[:, :1])
    assert np.max(np.abs(p - pt) / np.abs(pt)) < 1e-5
    # A flag version before the stage's first write; DATA untouched.
    assert any(v[0].startswith("rang_selfcal_") for v in flagversions.versions(ms))
    first = out.copy()
    core_cli.dispatch(["selfcal", str(config), str(ms), "--force"])
    assert np.array_equal(columns(ms, "CORRECTED_DATA")[0], first)


@POSIX
def test_the_input_column_comes_from_apply_or_must_exist(tmp_path, capsys):
    ms, _, _ = make_ms(tmp_path / "x.ms", "pa")
    config = write_config(tmp_path)  # input_column CORRECTED_1GC
    with pytest.raises(SystemExit) as exc:
        core_cli.dispatch(["selfcal", str(config), str(ms)])
    assert exc.value.code == 1
    assert "has no CORRECTED_1GC" in capsys.readouterr().err
    # After an apply in this run directory CORRECTED_DATA is copied in.
    with wb.WriteBack(ms, stage="test") as w:
        w.ensure_column("CORRECTED_DATA", init="data")
    run = pipe.RunDir(Path(str(ms) + ".rang-run"), ms)
    with run.locked():
        run.state["stages"]["apply"] = {"status": "done", "finished": "t1"}
        run.save()
    core_cli.dispatch(["selfcal", str(config), str(ms), "--force"])
    data, gc = columns(ms, "DATA", "CORRECTED_1GC")
    assert np.array_equal(data, gc)
    marker = json.loads((run.path / "selfcal-input.json").read_text())
    assert marker == {
        "column": "CORRECTED_1GC",
        "copied_from": "CORRECTED_DATA",
        "apply_finished": "t1",
    }
    # A rerun does not copy the self-calibrated CORRECTED_DATA back.
    core_cli.dispatch(["selfcal", str(config), str(ms), "--force"])
    assert np.array_equal(columns(ms, "CORRECTED_1GC")[0], data)
