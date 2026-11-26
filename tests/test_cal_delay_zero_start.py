# SPDX-License-Identifier: MIT
"""`rang.cal_delay.solve(zero_start=True)` and `calibrate.k_zero_start`
(research/calchain-floor.md section 12): the FFT start, on the refant
baselines only, lands on a sidelobe when an interval keeps two cells on
the baseline to the refant; a second run from zero, kept per interval by
its residual, recovers the delay. Off (the default) is unchanged."""

import numpy as np
import pytest
from rang import core_config
from test_cal_delay import TIGHT, run, simulate


def sparse(seed):
    """Noise-free; in interval 1 antenna 4 keeps 2 channels on its baseline
    to the refant (0) and 12 on each other baseline, as E2-A's ID 50 in K1
    interval 7 (94 cells, 2 to the refant)."""
    s = simulate(nant=6, ntime=2, nchan=512, scale=0.5, seed=seed)
    rng = np.random.default_rng(seed)
    keep_ref = rng.choice(512, 2, replace=False)
    for r in np.flatnonzero((s["tb"] == 1) & ((s["a1"] == 4) | (s["a2"] == 4))):
        to_ref = s["a1"][r] == 0 or s["a2"][r] == 0
        keep = keep_ref if to_ref else rng.choice(512, 12, replace=False)
        f = np.ones(512, bool)
        f[keep] = False
        s["flag"][r] = f[:, None]
    return s


@pytest.mark.parametrize("seed", [0, 7, 9])
def test_zero_start_recovers_a_sparse_interval(seed):
    s = sparse(seed)
    want = s["tau"] - s["tau"][:, 0:1]
    off = run(s, refant=0, kind="delay_and_offset", **TIGHT)
    on = run(s, refant=0, kind="delay_and_offset", zero_start=True, **TIGHT)
    assert (
        np.abs(off.delays[1, 0, 4] - want[1, 4]).max() > 10
    )  # the FFT start's sidelobe, ns
    assert np.abs(on.delays[1, 0, 4] - want[1, 4]).max() < 1e-6
    assert np.abs(on.delays[:, 0] - want).max() < 1e-6
    assert 1 in on.settings["zero_start_intervals"]
    assert (
        off.settings["zero_start"] is False
        and "zero_start_intervals" not in off.settings
    )


def test_zero_start_keeps_the_fft_start_where_zero_cannot_reach():
    """Delays up to 8 ns on full data: a start at zero cannot converge, the
    FFT start can; the merged result is the FFT run's, bit for bit."""
    s = simulate(nant=6, ntime=3, nchan=64)
    off = run(s, refant=2, kind="delay_and_offset", **TIGHT)
    on = run(s, refant=2, kind="delay_and_offset", zero_start=True, **TIGHT)
    want = s["tau"] - s["tau"][:, 2:3]
    assert np.abs(on.delays[:, 0] - want).max() < 1e-6
    for i in range(3):
        if i not in on.settings["zero_start_intervals"]:
            assert np.array_equal(on.delays[i], off.delays[i])
            assert np.array_equal(on.offsets[i], off.offsets[i])


def test_without_the_initial_estimate_zero_start_is_one_run():
    s = simulate(nant=5, ntime=2, nchan=32)
    a = run(s, refant=0, initial_estimate=False, **TIGHT)
    b = run(s, refant=0, initial_estimate=False, zero_start=True, **TIGHT)
    assert np.array_equal(a.delays, b.delays) and b.settings["zero_start"] is False


def test_config_key_defaults_off_and_leaves_the_stage_hash():
    raw = {"version": 1, "fields": {"fcal": ["CAL"]},
           "calibrate": {"primary": {"terms": [{"type": "K", "name": "K"}]}}}  # fmt: skip
    config, errors = core_config.resolve(raw)
    assert not errors and config["calibrate"]["k_zero_start"] is False
    before = core_config.stage_hash(config, "calibrate")
    gone = dict(config, calibrate={k: v for k, v in config["calibrate"].items()
                                   if k != "k_zero_start"})  # fmt: skip
    assert core_config.stage_hash(gone, "calibrate") == before
    on = dict(config, calibrate=dict(config["calibrate"], k_zero_start=True))
    assert core_config.stage_hash(on, "calibrate") != before


def _rows(s, t):
    """The rows of interval `t` of a simulation, as an interval-0 problem."""
    keep = s["tb"] == t
    out = {k: (v[keep] if isinstance(v, np.ndarray) and len(v) == len(keep) else v)
           for k, v in s.items()}  # fmt: skip
    out["tb"] = np.zeros(int(keep.sum()), np.int64)
    return out


def test_chunked_zero_start_intervals_count_every_chunk():
    """research/k-ambiguity.md: a field solved in chunks of whole intervals
    reported the first chunk's `zero_start_intervals` only, numbered from
    0; the field's list is every chunk's, offset by the chunks before it."""
    from rang import cal_delay

    s = sparse(0)
    one = run(s, refant=0, kind="delay_and_offset", zero_start=True, **TIGHT)
    parts = [run(_rows(s, t), refant=0, kind="delay_and_offset", zero_start=True, **TIGHT)
             for t in (0, 1)]  # fmt: skip
    # Interval 0 converges to truth from either start, so whether it is in a
    # list is a float tie; interval 1 is the zero start's on any split.
    assert 1 in one.settings["zero_start_intervals"]
    assert 0 in parts[1].settings["zero_start_intervals"]  # chunk 2's own numbering
    merged = cal_delay.zero_kept_of_chunks(parts)
    first = parts[0].settings["zero_start_intervals"]
    assert 1 not in first  # the old record: the first chunk's list only
    assert merged == first + [1 + i for i in parts[1].settings["zero_start_intervals"]]
    assert 1 in merged


def test_solution_record_carries_zero_start_intervals():
    from rang import cal_chain

    s = sparse(0)
    on = run(s, refant=0, kind="delay_and_offset", zero_start=True, **TIGHT)
    off = run(s, refant=0, kind="delay_and_offset", **TIGHT)
    info = {"rows": len(s["tb"]), "intervals": [0, 1]}
    assert (
        cal_chain._solution_record(on, info, 0)["zero_start_intervals"]
        == (on.settings["zero_start_intervals"])
    )
    assert "zero_start_intervals" not in cal_chain._solution_record(off, info, 0)


def test_sign_alternating_channels_keep_the_half_period_delay():
    """research/k-ambiguity.md (block 1678312253, antenna 25 from scan 50):
    an antenna whose data alternate in sign channel to channel has the delay
    +- 1/(2 dnu) on its own data; the key keeps that FFT run (a zero start
    cannot reach it) and the solution is the data's, not a solver defect."""
    s = simulate(nant=6, ntime=2, nchan=256, scale=0.5)
    flip = np.where(np.arange(256) % 2, -1, 1)[:, None]
    for r in np.flatnonzero((s["tb"] == 1) & ((s["a1"] == 4) | (s["a2"] == 4))):
        s["data"][r] = s["data"][r] * flip
    want = s["tau"] - s["tau"][:, 0:1]
    on = run(s, refant=0, kind="delay_and_offset", zero_start=True, **TIGHT)
    period = 1e9 / (s["freq"][1] - s["freq"][0])
    turns = (on.delays[1, 0, 4] - want[1, 4] - period / 2) / period
    assert np.abs(turns - np.round(turns)).max() < 1e-6
    assert 1 not in on.settings["zero_start_intervals"]
    assert np.abs(on.delays[0, 0] - want[0]).max() < 1e-6
