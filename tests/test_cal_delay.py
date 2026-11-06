"""The delay term K (task C2b, research/c2b-delay.md): kernel, CASA's K
referencing and the table route, on seeded simulated arrays."""

import numpy as np
import pytest
from rang import cal_apply, cal_delay
from rang.formats import caltable


def simulate(nant=6, ntime=3, nchan=64, noise=0.0, seed=20261106, scale=8.0):
    """`V = K_p M K_q^H` with delays up to `scale` ns, pivot the mean
    frequency, on 856-1712 MHz."""
    rng = np.random.default_rng(seed)
    freq = 856e6 + 856e6 / nchan * (np.arange(nchan) + 0.5)
    nu0 = freq.mean()
    tau = rng.uniform(-scale, scale, (ntime, nant, 2))
    a1, a2 = np.triu_indices(nant, 1)
    nbl = len(a1)
    a1, a2 = np.tile(a1, ntime), np.tile(a2, ntime)
    tb = np.repeat(np.arange(ntime), nbl)
    nrow = len(a1)
    model = np.zeros((nrow, nchan, 4), complex)
    model[..., 0] = 10 + rng.normal(0, 1, (nrow, nchan))
    model[..., 3] = 9 + rng.normal(0, 1, (nrow, nchan))
    k = np.exp(2j * np.pi * tau[..., None, :] * 1e-9 * (freq - nu0)[:, None])
    kp, kq = k[tb, a1], k[tb, a2]  # (row, chan, hand)
    data = model.copy()
    data[..., 0] *= kp[..., 0] * np.conj(kq[..., 0])
    data[..., 3] *= kp[..., 1] * np.conj(kq[..., 1])
    data[..., 1] *= kp[..., 0] * np.conj(kq[..., 1])
    data[..., 2] *= kp[..., 1] * np.conj(kq[..., 0])
    data += noise * (rng.normal(size=data.shape) + 1j * rng.normal(size=data.shape))
    return {
        "data": data.astype(np.complex64),
        "model": model.astype(np.complex64),
        "weights": np.ones(data.shape, np.float32),
        "flag": np.zeros(data.shape, bool),
        "flag_row": np.zeros(nrow, bool),
        "a1": a1,
        "a2": a2,
        "tb": tb,
        "nant": nant,
        "freq": freq,
        "tau": tau,
    }


def run(s, **kw):
    # C2b's tests are pinned to `delay`; C2c's `delay_and_offset` (the
    # default) is tested below.
    kw.setdefault("kind", "delay")
    return cal_delay.solve(
        s["data"], s["model"], s["weights"], s["flag"], s["flag_row"], s["a1"],
        s["a2"], s["tb"], nant=s["nant"], chan_freq=s["freq"], **kw,
    )  # fmt: skip


TIGHT = {"stop_fraction": 1.0, "stop_criterion": 1e-12, "max_iterations": 200}


@pytest.mark.parametrize("casa_rules", [True, False])
def test_noise_free_delays_are_recovered(casa_rules):
    s = simulate()
    sol = run(s, refant=2, casa_rules=casa_rules, **TIGHT)
    want = s["tau"] - s["tau"][:, 2:3]
    assert not sol.flags.any()
    assert np.abs(sol.delays[:, 0] - want).max() < 1e-6
    assert np.all(sol.delays[:, 0, 2] == 0)


def test_casa_k_referencing_flags_what_casa_cannot_solve():
    s = simulate(nant=5)
    # Interval 1: no data on the baselines to the refant (0); interval 2:
    # antenna 4 keeps its baselines to 1-3 only.
    s["flag_row"][(s["tb"] == 1) & ((s["a1"] == 0) | (s["a2"] == 0))] = True
    s["flag_row"][(s["tb"] == 2) & (s["a1"] == 0) & (s["a2"] == 4)] = True
    sol = run(s, refant=0)
    assert not sol.flags[0].any()
    assert sol.flags[1, 0, 1:].all() and not sol.flags[1, 0, 0].any()
    assert sol.delays[1, 0, 0].tolist() == [0.0, 0.0]
    assert sol.flags[2, 0, 4].all() and not sol.flags[2, 0, :4].any()
    # QuartiCal's route still solves antenna 4 from its other baselines.
    q = run(s, refant=0, casa_rules=False)
    assert not q.kernel_flags[2, 0, 4]


def test_errors_follow_the_noise():
    quiet = run(simulate(noise=0.05, seed=1), refant=0)
    loud = run(simulate(noise=0.5, seed=1), refant=0)
    ratio = np.median(loud.err[:, 0, 1:]) / np.median(quiet.err[:, 0, 1:])
    assert 7 < ratio < 13


def test_k_table_applies_back_to_the_model(tmp_path):
    """The solved K written as a CASA `K Jones` table (pivot: the one-channel
    window at the mean frequency) and applied by `rang.cal_apply` turns the
    noise-free data into the model."""
    s = simulate(nant=4, nchan=32, scale=5.0)
    sol = run(s, refant=0, **TIGHT)
    times = 1000.0 + np.arange(3) * 8.0
    subtables = {
        "ANTENNA": {"NAME": [f"m{a:03d}" for a in range(4)]},
        "SPECTRAL_WINDOW": {"CHAN_FREQ": [np.array([s["freq"].mean()])]},
    }
    table = caltable.from_gains(
        "K", times, list(range(4)), sol.delays[:, 0, :, None, :],
        sol.flags[:, 0, :, None, :], subtables=subtables, refant=-1,
    )  # fmt: skip
    corrected, flags = cal_apply.apply(
        s["data"], s["flag"], times[s["tb"]], s["a1"], s["a2"], s["freq"], [table],
        interp="nearest",
    )  # fmt: skip
    assert not flags.any()
    par = (0, 3)
    assert np.allclose(corrected[..., par], s["model"][..., par], rtol=2e-5, atol=2e-5)
    path = tmp_path / "x.K"
    caltable.write(table, path)
    back = caltable.read(path)
    assert back.keywords["VisCal"] == "K Jones" and back.float_param
    assert np.array_equal(back.params, table.params)


def test_refant_out_of_range():
    s = simulate(nant=3, ntime=1, nchan=8)
    with pytest.raises(ValueError):
        run(s, refant=3)


# --- task C2c (research/c2c-bandpass.md): delay_and_offset, the default ---


def with_offsets(s, seed=7):
    """Multiply each antenna and hand by a constant phase (G with no
    amplitude): `delay` is biased by it where weights are uneven,
    `delay_and_offset` absorbs it."""
    rng = np.random.default_rng(seed)
    ntime = int(s["tb"].max()) + 1
    phi = rng.uniform(-2.5, 2.5, (ntime, s["nant"], 2))
    gp, gq = np.exp(1j * phi[s["tb"], s["a1"]]), np.exp(1j * phi[s["tb"], s["a2"]])
    data = s["data"].astype(complex)
    data[..., 0] *= (gp[:, 0] * np.conj(gq[:, 0]))[:, None]
    data[..., 3] *= (gp[:, 1] * np.conj(gq[:, 1]))[:, None]
    data[..., 1] *= (gp[:, 0] * np.conj(gq[:, 1]))[:, None]
    data[..., 2] *= (gp[:, 1] * np.conj(gq[:, 0]))[:, None]
    out = dict(s)
    out["data"] = data.astype(np.complex64)
    out["phi"] = phi
    return out


@pytest.mark.parametrize("casa_rules", [True, False])
def test_delay_and_offset_recovers_delays_and_offsets(casa_rules):
    s = with_offsets(simulate())
    sol = run(s, refant=2, casa_rules=casa_rules, kind="delay_and_offset", **TIGHT)
    assert sol.settings["kind"] == "delay_and_offset"
    assert not sol.flags.any()
    want = s["tau"] - s["tau"][:, 2:3]
    assert np.abs(sol.delays[:, 0] - want).max() < 1e-6
    dphi = sol.offsets[:, 0] - (s["phi"] - s["phi"][:, 2:3])
    assert np.abs(np.angle(np.exp(1j * dphi))).max() < 1e-5
    assert np.all(sol.offsets[:, 0, 2] == 0)


def test_offsets_bias_delay_but_not_delay_and_offset():
    s = with_offsets(simulate(nchan=64))
    # Uneven weights about mid-band (as RFI flags make them).
    s["weights"][:, :20] = 0.05
    plain = run(s, refant=0, kind="delay", **TIGHT)
    free = run(s, refant=0, kind="delay_and_offset", **TIGHT)
    want = s["tau"] - s["tau"][:, :1]
    assert np.abs(free.delays[:, 0] - want).max() < 1e-6
    assert np.abs(plain.delays[:, 0] - want).max() > 1e-3


def test_delay_and_offset_errors_follow_the_noise():
    kw = {"refant": 0, "kind": "delay_and_offset"}
    quiet = run(simulate(noise=0.05, seed=1), **kw)
    loud = run(simulate(noise=0.5, seed=1), **kw)
    ratio = np.median(loud.err[:, 0, 1:]) / np.median(quiet.err[:, 0, 1:])
    assert 7 < ratio < 13
    # The offset-marginalised error is about the fixed-offset one on this
    # symmetric band (the marginalisation adds little) and unaffected by an
    # amplitude the term does not carry.
    fixed = run(simulate(noise=0.5, seed=1), refant=0)
    ratio = np.median(loud.err[:, 0, 1:] / fixed.err[:, 0, 1:])
    assert 0.8 < ratio < 1.25
    s = simulate(noise=0.5, seed=1)
    s["data"] = s["data"] * np.float32(1.3)
    scaled = run(s, **kw)
    ratio = np.median(scaled.err[:, 0, 1:] / loud.err[:, 0, 1:])
    assert 0.8 < ratio < 1.25


def test_unknown_kind_is_refused():
    s = simulate(nant=3, ntime=1, nchan=8)
    with pytest.raises(ValueError):
        run(s, kind="delay_tec")
