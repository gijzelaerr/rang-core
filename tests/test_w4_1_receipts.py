"""Task W4-1 (research/w4-1-receipts.md): receipts record every
result-affecting setting, and the solver takes its options as an argument.

- `core.solve_complex(options=, trace=)` equals the environment path bit for
  bit, and the Rust core no longer reads `RANG_SOLVE_OPTIONS` or
  `RANG_SOLVE_TRACE` itself;
- the registry `core.ENVIRONMENT` names every `RANG_*` read anywhere under
  `python/rang/` or the Rust sources, so a new variable cannot be added
  silently;
- every receipt writer records the registry.
"""

import importlib.util
import re
from pathlib import Path

import numpy as np
import pytest
from rang import core

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"RANG_[A-Z0-9_]*[A-Z0-9]")
SOURCES = ("python/rang", "core/src", "core/py/src", "src")

needs_core = pytest.mark.skipif(
    importlib.util.find_spec("rang._core") is None, reason="rang._core is not built"
)


def problem(seed=5):
    rng = np.random.default_rng(seed)
    pairs = [(p, q) for p in range(4) for q in range(p + 1, 4)]
    rows = [(t, p, q) for t in range(6) for p, q in pairs]
    nrow, nchan = len(rows), 16
    a1 = np.array([r[1] for r in rows], np.uint32)
    a2 = np.array([r[2] for r in rows], np.uint32)
    truth = np.eye(2) + 0.1 * (
        rng.standard_normal((4, 2, 2)) + 1j * rng.standard_normal((4, 2, 2))
    )
    model = (np.eye(2) + 0.2 * rng.standard_normal((nrow, nchan, 2, 2))).astype(
        np.complex64
    )
    data = np.einsum("rij,rcjk,rlk->rcil", truth[a1], model, truth[a2].conj())
    data = data + 0.01 * rng.standard_normal(data.shape)
    weights = rng.uniform(0.2, 2.0, (nrow, nchan, 4)).astype(np.float32)
    return (
        data.reshape(nrow, nchan, 4).astype(np.complex64),
        weights,
        np.zeros((nrow, nchan, 4), bool),
        np.zeros(nrow, bool),
        a1,
        a2,
        np.array([r[0] // 2 for r in rows], np.uint32),
        np.arange(nchan, dtype=np.uint32) // 8,
    ), {
        "ntime_bins": 3,
        "nfreq_bins": 2,
        "nant": 4,
        "model": model.reshape(nrow, nchan, 4),
    }


def solve(**kwargs):
    args, sizes = problem()
    return core.solve_complex(*args, **sizes, **kwargs)


def same(a, b):
    return (
        a.gains.tobytes() == b.gains.tobytes()
        and a.flags.tobytes() == b.flags.tobytes()
        and (a.iterations, a.converged_fraction) == (b.iterations, b.converged_fraction)
    )


CASES = ["", "qp_weights=transposed", "anderson=3", "stop=product:1e-4,freeze=1"]


@needs_core
@pytest.mark.parametrize("text", CASES)
def test_options_argument_equals_the_environment_path(text, monkeypatch):
    monkeypatch.setenv(core.SOLVE_OPTIONS_VAR, text)
    from_env = solve(max_iterations=80)
    monkeypatch.delenv(core.SOLVE_OPTIONS_VAR)
    explicit = solve(max_iterations=80, options=text)
    parsed = solve(max_iterations=80, options=core.solve_options(text))
    assert same(from_env, explicit) and same(explicit, parsed)
    assert from_env.options == explicit.options == core.solve_options(text)


@needs_core
def test_default_is_the_archived_solver_and_the_core_ignores_the_environment(
    monkeypatch,
):
    monkeypatch.delenv(core.SOLVE_OPTIONS_VAR, raising=False)
    default = solve()
    archived = solve(options="qp_weights=archived,stop=gain,anderson=0,freeze=0")
    assert same(default, archived)
    assert default.options.record() == {
        "text": "",
        "qp_weights": "archived",
        "stop": "gain",
        "tolerance": None,
        "anderson": 0,
        "freeze": False,
    }
    # An explicit argument wins: the environment reaches no solve by itself.
    monkeypatch.setenv(core.SOLVE_OPTIONS_VAR, "qp_weights=transposed")
    assert same(solve(options=""), default)
    assert not same(solve(), default)


@needs_core
def test_malformed_options_fail_as_before():
    with pytest.raises(ValueError, match="malformed solver options"):
        core.solve_options("stop=sideways")
    with pytest.raises(RuntimeError, match="status 1"):
        solve(options="anderson=11")
    for text in ("qp_weights=both", "freeze=2", "stop=loss:-1", "unknown=1"):
        with pytest.raises(ValueError):
            core.solve_options(text)
    parsed = core.solve_options(" stop = loss:2e-7 , anderson=2 ")
    assert (parsed.stop, parsed.tolerance, parsed.anderson) == ("loss", 2e-7, 2)


@needs_core
def test_trace_argument_and_environment(tmp_path, monkeypatch):
    monkeypatch.delenv(core.SOLVE_TRACE_VAR, raising=False)
    explicit = tmp_path / "explicit.json"
    a = solve(trace=explicit)
    assert explicit.is_file() and a.trace == str(explicit)
    from_env = tmp_path / "env.json"
    monkeypatch.setenv(core.SOLVE_TRACE_VAR, str(from_env))
    b = solve()
    assert from_env.read_text() == explicit.read_text() and same(a, b)
    from_env.unlink()
    c = solve(trace="")
    assert not from_env.exists() and c.trace is None and same(a, c)


def _source_names():
    found = {}
    for top in SOURCES:
        for path in sorted((ROOT / top).rglob("*")):
            if path.suffix not in (".py", ".rs") or "__pycache__" in path.parts:
                continue
            for name in NAME.findall(path.read_text(encoding="utf-8")):
                found.setdefault(name, set()).add(path.relative_to(ROOT).as_posix())
    return found


def test_registry_covers_every_rang_variable_in_the_sources():
    found = _source_names()
    registered = {v.name for v in core.ENVIRONMENT}
    missing = sorted(set(found) - registered - set(core.NOT_ENVIRONMENT))
    assert not missing, f"add these to rang.core.ENVIRONMENT: {missing}"
    live = {v.name for v in core.ENVIRONMENT if v.kind != "retired"}
    stale = sorted(live - set(found))
    assert not stale, f"no longer read anywhere (mark them retired): {stale}"
    assert len(registered) == len(core.ENVIRONMENT)
    for v in core.ENVIRONMENT:
        assert v.kind in core.KINDS, v
        assert (ROOT / v.report).is_file(), v
        if v.kind != "retired":
            assert v.reader in found[v.name], (v.name, sorted(found[v.name]))
    # W4-3 removed the two ctypes libraries: nothing reads them.
    for path in (ROOT / "python/rang").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in ("RANG_C1_LIB", "RANG_DF1_LIB"):
            assert f'environ.get("{name}")' not in text, (path, name)
    for name in core.NOT_ENVIRONMENT:
        assert name in found


def test_the_rust_core_reads_no_solver_variable():
    for path in (ROOT / "core/src").rglob("*.rs"):
        text = path.read_text(encoding="utf-8")
        assert 'RANG_SOLVE_OPTIONS")' not in text and "TRACE_VAR" not in text, path
    solve_rs = (ROOT / "core/src/solve.rs").read_text(encoding="utf-8")
    assert "std::env" not in solve_rs and "from_env" not in solve_rs


def test_settings_record_every_recorded_kind_and_only_those():
    settings = core.environment_settings({"RANG_SOLVE_OPTIONS": "anderson=2"})
    assert settings["RANG_SOLVE_OPTIONS"] == "anderson=2"
    assert settings["RANG_GRIDDER_DEVICE"] is None
    assert "RANG_DF1_LIB" not in settings  # retired by W4-3
    kinds = {v.name: v.kind for v in core.ENVIRONMENT}
    assert {kinds[n] for n in settings} <= set(core.RECORDED_KINDS)
    assert set(settings) == {
        v.name for v in core.ENVIRONMENT if v.kind in core.RECORDED_KINDS
    }


WRITERS = {
    "python/rang/core_cli.py": 2,  # the receipt and environment.json
    "python/rang/core_campaign.py": 1,  # K
    "python/rang/core_campaign_array.py": 1,  # L1
    "python/rang/core_campaign_1830.py": 1,  # L2
    "python/rang/core_campaign_fieldmodel.py": 1,  # L1-M
    "python/rang/core_campaign_closure.py": 1,  # C1
    "python/rang/core_imaging.py": 1,  # I
    "examples/run_l5_solver_study.py": 1,  # L5
}


def test_every_receipt_writer_records_the_registry():
    for rel, count in WRITERS.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert text.count("environment_settings") >= count, rel


def test_checkout_detection():
    assert core.checkout_root() == ROOT
