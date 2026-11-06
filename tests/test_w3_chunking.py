"""W3 (research/w3-chunking.md): chunking by time and row gives the
unchunked result bit for bit, and a limit too small for the smallest chunk is
refused before anything is written. The comparisons on A1's sets, O-CASA's
slice and the whole-array set are `tools/oracles/w3/run.sh`."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from rang import core_chunks, core_config, core_flag, core_ms, core_ms_write
from rang import core_pipeline as pipe

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "w2_commands", ROOT / "tests" / "test_w2_commands.py"
)
w2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w2)

needs_writer = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)


# -- helpers -------------------------------------------------------------------------


def test_runs_and_read_rows_follow_the_row_order():
    assert core_chunks.runs([3, 4, 5, 9, 10, 20]) == [(3, 3), (9, 2), (20, 1)]
    assert core_chunks.runs([]) == []
    with pytest.raises(ValueError):
        core_chunks.runs([2, 1])

    class Source:
        def __init__(self):
            self.calls = []
            self.x = np.arange(40).reshape(20, 2)

        def getcol(self, name, start, n):
            self.calls.append((start, n))
            return self.x[start : start + n]

    src = Source()
    rows = np.array([7, 2, 3, 15, 4])
    got = core_chunks.read_rows(src, "X", rows)
    np.testing.assert_array_equal(got, src.x[rows])
    assert src.calls == [(2, 3), (7, 1), (15, 1)]
    got = core_chunks.read_rows(src, "X", rows, chans=slice(1, 2), block_rows=2)
    np.testing.assert_array_equal(got, src.x[rows][:, 1:2])


def test_the_budget_counts_the_process_and_the_rows():
    b = core_chunks.Budget(8.0, 1000, (64, 4))
    assert b.chunk_bytes == 8 * core_chunks.GIB - (
        core_chunks.BASE_BYTES + core_chunks.ROW_BYTES * 1000
    )
    assert b.rows("apply") == b.chunk_bytes // (core_chunks.CELL_BYTES["apply"] * 256)
    capped = core_chunks.Budget(8.0, 1000, (64, 4), chunk_rows=7)
    assert capped.rows("flag") == 7 and capped.rows("flag", capped=False) > 7
    assert capped.cells("calibrate") == 7 * 256
    with pytest.raises(core_chunks.MemoryLimitError, match="raise the limit"):
        _ = core_chunks.Budget(0.1, 1000, (64, 4)).chunk_bytes


def test_resource_keys_are_not_in_the_stage_hash():
    a, _ = core_config.resolve({"version": 1})
    b, _ = core_config.resolve(
        {"version": 1, "data": {"memory_limit_gb": 2, "chunk_rows": 7}}
    )
    c, _ = core_config.resolve({"version": 1, "data": {"scans": [1]}})
    for stage in core_config.STAGES:
        assert core_config.stage_hash(a, stage) == core_config.stage_hash(b, stage)
        assert core_config.stage_hash(a, stage) != core_config.stage_hash(c, stage)
    _, errors = core_config.resolve(
        {"version": 1, "data": {"memory_limit_gb": 0, "chunk_rows": 0}}
    )
    assert {p for p, _ in errors} == {"data.memory_limit_gb", "data.chunk_rows"}


def test_solve_chunks_hold_whole_intervals():
    tb = np.repeat(np.arange(5), [3, 3, 3, 3, 2])
    fb = np.repeat(np.arange(4), 2)  # 8 channels, 4 bins of 2
    chunks, largest = core_chunks.solve_chunks(tb, fb, 3 * 8 * 4 * 2, 4)
    assert largest == 3 * 2 * 4
    assert [(c.t0, c.t1) for c in chunks] == [(0, 2), (2, 4), (4, 5)]
    # A time bin larger than a chunk goes by frequency bins.
    chunks, _ = core_chunks.solve_chunks(tb, fb, 3 * 4 * 4, 4)
    assert [(c.t0, c.f0, c.f1, c.chans) for c in chunks[:2]] == [
        (0, 0, 2, slice(0, 4)),
        (0, 2, 4, slice(4, 8)),
    ]
    assert core_chunks.solve_chunks(tb, fb, 10, 4)[0] is None
    # A chunk_rows cap below one interval still leaves one interval per chunk.
    chunks, _ = core_chunks.solve_chunks(tb, fb, 10, 4, hard_cells=1000)
    assert len(chunks) == 5 * 4
    assert core_chunks.replay_stop([(1, 0), (9, 1), (10, 0)], 10, 0.99) == (1, 1.0)
    assert core_chunks.replay_stop([(1, 0), (2, 0)], 10, 0.99) == (1, 0.2)


# -- the solve -------------------------------------------------------------------


def _partition(seed, nant=6, ntime=8, nchan=12, flagged_time=None, noise=0.05):
    rng = np.random.default_rng(seed)
    a1, a2 = np.triu_indices(nant, 1)
    nbl = len(a1)
    g = (1 + 0.2 * rng.standard_normal((ntime, nant, 2))) * np.exp(
        1j * rng.uniform(-1, 1, (ntime, nant, 2))
    )
    rows = ntime * nbl
    data = np.zeros((rows, nchan, 4), np.complex64)
    t = np.repeat(np.arange(ntime), nbl)
    p, q = np.tile(a1, ntime), np.tile(a2, ntime)
    data[:, :, 0] = (g[t, p, 0] * np.conj(g[t, q, 0]))[:, None]
    data[:, :, 3] = (g[t, p, 1] * np.conj(g[t, q, 1]))[:, None]
    data += noise * (
        rng.standard_normal(data.shape) + 1j * rng.standard_normal(data.shape)
    ).astype(np.complex64)
    flag = rng.random(data.shape) < 0.05
    if flagged_time is not None:
        flag[t == flagged_time] = True
    columns = {
        "DATA": data,
        "FLAG": flag,
        "FLAG_ROW": np.zeros(rows, bool),
        "WEIGHT_SPECTRUM": rng.uniform(0.5, 2, data.shape).astype(np.float32),
    }
    info = {
        "cell": (nchan, 4),
        "chan_freq": 1e9 + 1e6 * np.arange(nchan),
        "antennas": [f"a{i}" for i in range(nant)],
        "weight_spectrum": True,
        "rows": {
            "TIME": 4.0e9 + 8.0 * t,
            "ANTENNA1": p.astype(np.int32),
            "ANTENNA2": q.astype(np.int32),
        },
    }

    class Source:
        def getcol(self, name, start, n):
            return columns[name][start : start + n]

    return Source(), info, np.arange(rows)


def _term(**kw):
    term = {
        "solint": "int",
        "freqint": 4,
        "max_iterations": 50,
        "stop_criterion": 1e-7,
        "stop_fraction": 0.99,
    }
    term.update(kw)
    return term


def test_the_trace_does_not_change_the_solve(tmp_path):
    src, info, idx = _partition(1)
    term = _term()
    order, tb, fb, gt, gf = pipe.partition_grid(info, idx, term)
    inputs = pipe._solve_inputs(src, order, slice(0, 12), info, "as_is", "unity", None)
    plain = pipe._complex(inputs, info, order, tb, fb, len(gt), len(gf), term, trace="")
    traced = pipe._complex(
        inputs, info, order, tb, fb, len(gt), len(gf), term, trace=str(tmp_path / "t")
    )
    assert plain.gains.tobytes() == traced.gains.tobytes()
    assert np.array_equal(plain.flags, traced.flags)
    assert plain.iterations == traced.iterations
    assert len(core_chunks.trace_counts(tmp_path / "t")) == traced.iterations


@pytest.mark.parametrize(
    "case",
    [
        {"seed": 2},  # stops early
        {"seed": 3, "max_iterations": 3},  # runs to its maximum
        {"seed": 4, "flagged_time": 2},  # an interval with no data
        {"seed": 5, "noise": 0.5, "freqint": 1},  # noisy, many bins
        {"seed": 6, "solint": 3, "freqint": "inf"},
    ],
)
def test_a_replayed_chunked_solve_equals_one_call(case):
    case = dict(case)
    kw = {k: case.pop(k) for k in ("max_iterations", "freqint", "solint") if k in case}
    src, info, idx = _partition(**case)
    term = _term(**kw)
    one = pipe.solve_partition(src, idx, info, term, "as_is", "unity", None)
    assert one[5] == {"chunks": 1, "passes": 1}
    nbl = 15
    for max_cells in (nbl * 12 * 4 * 2, nbl * 12 * 4, nbl * 4 * 4, 1):
        many = pipe.solve_partition(
            src, idx, info, term, "as_is", "unity", None, max_cells, 10**9
        )
        assert many[5]["chunks"] > 1
        assert many[0].gains.tobytes() == one[0].gains.tobytes()
        assert np.array_equal(many[0].flags, one[0].flags)
        assert many[0].iterations == one[0].iterations
        assert many[0].converged_fraction == one[0].converged_fraction
        for a, b in zip(many[1:5], one[1:5]):
            assert np.array_equal(a, b)


# -- the flagger -----------------------------------------------------------------


def test_flag_blocks_of_baselines_on_the_group_grid_equal_one_call():
    rng = np.random.default_rng(7)
    nant, ntime, nchan = 5, 30, 64
    a1, a2 = np.triu_indices(nant, 1)
    nbl = len(a1)
    t = np.repeat(np.arange(ntime), nbl)
    p, q = np.tile(a1, ntime), np.tile(a2, ntime)
    keep = np.ones(len(t), bool)
    keep[(t == 4) & (p == 0)] = False  # a dump missing on some baselines
    keep[(t == 0) & (q == 4)] = False
    t, p, q = t[keep], p[keep], q[keep]
    data = (rng.standard_normal((len(t), nchan, 4)) * (1 + 1j)).astype(np.complex64)
    data[t == 10, 20:23] += 40  # RFI
    data[:, 50] += 25
    flags = rng.random(data.shape) < 0.02
    times = 5.0e9 + 8.0 * t
    pos = np.array([[0.0, 0.0, 0.0]] * nant) + 100.0 * np.arange(nant)[:, None]
    freq = 1.3e9 + 1e5 * np.arange(nchan)
    width = np.full(nchan, 1e5)
    strategies = core_flag.parse_strategy(w2.STRATEGY)
    args = (pos, freq, width, np.array([9, 10, 11, 12]), strategies)
    one = core_flag.flag_rows(
        data,
        flags,
        p,
        q,
        times,
        *args,
        masks=[],
        want_intensity=False,
        want_stages=False,
    )["flags"]
    assert one.any()
    grid = np.unique(times)
    for size in (1, 2, 3):
        got = np.zeros_like(one)
        for start in range(0, nbl, size):
            sel = np.isin(
                p * nant + q,
                [a1[b] * nant + a2[b] for b in range(start, start + size) if b < nbl],
            )
            got[sel] = core_flag.flag_rows(
                data[sel],
                flags[sel],
                p[sel],
                q[sel],
                times[sel],
                *args,
                masks=[],
                want_intensity=False,
                want_stages=False,
                time_grid=grid,
            )["flags"]
        assert np.array_equal(got, one)
    # Without the group's grid a block missing a dump is flagged differently.
    sel = p == 0
    alone = core_flag.flag_rows(
        data[sel],
        flags[sel],
        p[sel],
        q[sel],
        times[sel],
        *args,
        masks=[],
        want_intensity=False,
        want_stages=False,
    )["flags"]
    assert not np.array_equal(alone, one[sel])


# -- the commands ----------------------------------------------------------------


def _columns(ms, *names):
    with core_ms.open_table(ms) as t:
        return {n: t.getcol(n) for n in names}


CONFIG = (
    "calibrate:\n"
    "  model: {source: manual, flux_jy: [2.0], reffreq_hz: 1.0e9}\n"
    "  primary:\n"
    "    terms:\n"
    "      - {type: complex, name: G1, solint: int, freqint: 4}\n"
    "      - {type: complex, name: G2, solint: 3, freqint: inf}\n"
)


BASE_CALIBRATE = (
    "calibrate:\n  primary:\n    terms: [{type: complex, solint: 4, freqint: 8}]\n"
)


def _config(work, calibrate, data):
    path = w2.write_config(work, data)
    text = path.read_text(encoding="utf-8")
    assert BASE_CALIBRATE in text
    path.write_text(text.replace(BASE_CALIBRATE, calibrate), encoding="utf-8")
    return path


@needs_writer
def test_the_stages_do_not_depend_on_the_chunking(tmp_path):
    out = {}
    for arm, data in (
        ("one", "data: {chunk_rows: 100000}\n"),
        ("tiny", "data: {chunk_rows: 7}\n"),
    ):
        work = tmp_path / arm
        work.mkdir()
        ms = w2.make_ms(work / "x.ms")
        config = _config(work, CONFIG, data)
        for stage in ("flag", "calibrate", "apply"):
            state = w2.cli(stage, str(config), str(ms))
            assert state["stages"][stage]["status"] == "done", stage
        run = ms.with_name("x.ms.rang-run")
        out[arm] = {
            "columns": _columns(ms, "FLAG", "MODEL_DATA", "CORRECTED_DATA"),
            "stores": {
                p.relative_to(run): p.read_bytes()
                for p in sorted((run / "calibrate").rglob("*"))
                if p.is_file() and p.name != "summary.json"
            },
            "summary": pipe.json.loads(
                (run / "calibrate" / "summary.json").read_text()
            ),
        }
    one, tiny = out["one"], out["tiny"]
    for name, value in one["columns"].items():
        assert value.tobytes() == tiny["columns"][name].tobytes(), name
    assert one["stores"] == tiny["stores"]
    assert [t["partitions"] for t in one["summary"]["tables"]] == [
        t["partitions"] for t in tiny["summary"]["tables"]
    ]
    assert max(p["chunks"] for p in tiny["summary"]["chunking"]["partitions"]) > 1


@needs_writer
def test_a_solution_interval_above_the_limit_is_refused_before_writing(tmp_path):
    ms = w2.make_ms(tmp_path / "x.ms")
    fixed = core_chunks.BASE_BYTES + core_chunks.ROW_BYTES * w2.NROW
    limit = (fixed + 50_000) / core_chunks.GIB
    config = _config(
        tmp_path,
        "calibrate:\n"
        "  model: {source: manual, flux_jy: [2.0], reffreq_hz: 1.0e9}\n"
        "  primary: {terms: [{type: complex, solint: inf, freqint: inf}]}\n",
        f"data: {{memory_limit_gb: {limit!r}}}\n",
    )
    before = _columns(ms, "FLAG", "DATA")
    with pytest.raises(SystemExit) as exit_:
        w2.cli("calibrate", str(config), str(ms))
    assert exit_.value.code == 2
    after = _columns(ms, "FLAG", "DATA")
    assert all(before[k].tobytes() == after[k].tobytes() for k in before)
    assert not ms.with_name("x.ms.flagversions").exists()
    assert not ms.with_name("x.ms.rang-run").exists()
    info = pipe.inspect_ms(ms)
    problems = pipe.memory_problems(
        core_config.validate_file(config, ["calibrate"]), info, ["calibrate"]
    )
    assert len(problems) == 1 and "solution interval" in problems[0]
    assert "GiB" in problems[0]


@needs_writer
def test_chain_terms_below_one_interval_are_refused_before_writing(tmp_path):
    """K, G, B, A and F (task C2e) are chunked since task W3b
    (research/w3b-chainchunks.md); a limit below one solution interval of K
    and G (`solint: inf`, a whole scan) is refused before anything is
    written, and the A step's smallest block (one baseline) still fits."""
    ms = w2.make_ms(tmp_path / "x.ms")
    fixed = core_chunks.BASE_BYTES + core_chunks.ROW_BYTES * w2.NROW
    chain = (
        "calibrate:\n"
        "  refant: m000\n"
        "  minblperant: 3\n"
        "  primary:\n"
        "    terms:\n"
        "      - {type: K, name: K}\n"
        "      - {type: G, name: G, preapply: [K], interp: [linear]}\n"
        "      - {type: A, name: A}\n"
    )
    small = _config(
        tmp_path,
        chain,
        f"data: {{memory_limit_gb: {(fixed + 100_000) / core_chunks.GIB!r}}}\n",
    )
    with pytest.raises(SystemExit) as exit_:
        w2.cli("calibrate", str(small), str(ms))
    assert exit_.value.code == 2
    assert not ms.with_name("x.ms.flagversions").exists()
    info = pipe.inspect_ms(ms)
    problems = pipe.memory_problems(
        core_config.validate_file(small, ["calibrate"]), info, ["calibrate"]
    )
    assert len(problems) == 2
    assert all("solution interval" in p and "GiB" in p for p in problems)
    work = tmp_path / "default"
    work.mkdir()
    default = _config(work, chain, "")
    config = core_config.validate_file(default, ["calibrate"])
    assert pipe.memory_problems(config, info, ["calibrate"]) == []
