"""F3 (research/f3-flagger.md): the Rust features against the NumPy
reference, the Rust logits against the JAX network, W3's steps, the data
guards and the injections, on a small synthetic scan."""

import numpy as np
import pytest
from rang import f2flag as ff
from rang import f3flag as f3
from rang import f3net


def synthetic(nant=6, nt=7, nc=96, seed=3):
    rng = np.random.default_rng(seed)
    p, q = np.triu_indices(nant, 1)
    rows = [(t, a, b) for t in range(nt) for a, b in zip(p, q, strict=True)]
    t_, a1, a2 = (np.array(x) for x in zip(*rows, strict=True))
    n = len(rows)
    data = (rng.normal(0, 1, (n, nc, 4)) + 1j * rng.normal(0, 1, (n, nc, 4))).astype(
        np.complex64
    )
    data[..., [0, 3]] += 20.0
    flags = rng.random((n, nc, 4)) < 0.05
    data[5, 10, 2] = np.nan
    return {
        "data": data,
        "input_flags": flags,
        "antenna1": a1.astype(np.int32),
        "antenna2": a2.astype(np.int32),
        "times": 1e9 + 8.0 * t_,
        "antenna_position": rng.normal(0, 500, (nant, 3)) + 5e6,
        "chan_freq": 1.07e9 + 2.1e5 * np.arange(nc),
        "chan_width": np.full(nc, 2.1e5),
        "corr_type": np.array([9, 10, 11, 12], np.int32),
        "nant": nant,
        "klass": "calibrator",
        "field": "synthetic",
    }


def test_features_match_numpy_reference():
    scan = synthetic()
    flagged = scan["input_flags"].any(-1)
    sel = np.arange(len(f3.index(scan)["ubl"]))
    r = f3.rust_features(scan, flagged, sel)
    n = f3.features_numpy(scan, flagged, sel)
    assert r.shape == (len(sel), 7, 96, 15)
    assert np.abs(r - n).max() <= 1e-4
    assert (r[..., 14] == 1).sum() >= flagged.sum()


def test_logits_match_jax():
    pytest.importorskip("jax")
    scan = synthetic()
    flagged = scan["input_flags"].any(-1)
    params = f3net.init_params(5)
    assert f3net.count_weights(params) == 3433
    ix = f3.index(scan)
    x = f3.rust_features(scan, flagged, np.arange(len(ix["ubl"])))
    zj = np.asarray(f3net.forward(params, x))[ix["bl"], ix["t"]]
    zr = f3.rust_logits(scan, flagged, f3net.flat_weights(params))
    assert np.abs(zr - zj)[~flagged].max() <= 1e-3


@pytest.mark.skipif(
    not ff.STRATEGY_DIR.is_dir(),
    reason="CARACal's archived strategy YAMLs are not here",
)
def test_w3_is_t_net_static_mask():
    for klass in ("calibrator", "target"):
        steps = f3.w3_strategy(klass)
        assert [s["task"] for s in steps] == [
            "flag_nans_zeros",
            "apply_static_mask",
            "flag_autos",
            "combine_with_input_flags",
        ]
        assert steps[1]["kwargs"]["uvrange"] == "0~550"


def test_guards_refuse_e2_groups():
    for g in ("MAIN_16", "MAIN_17", "MAIN_18", "MAIN_19", "MAIN_8", "MAIN_1x"):
        with pytest.raises(ValueError):
            f3.check_luno_group(g)
    for c in (1, 3, 5):
        with pytest.raises(ValueError):
            f3.check_eso_chunk("MAIN_0", c)
    with pytest.raises(ValueError):
        f3.check_eso_chunk("MAIN_4", 0)
    assert f3.check_luno_group("MAIN_4") == "MAIN_4"


def test_injections_are_seeded_and_on_eligible_cells():
    scan = synthetic()
    w3 = scan["input_flags"].any(-1)
    sigma = f3.baseline_sigma(scan, ~w3)
    a = f3.realise(scan, w3, sigma, 11, False, w3, w3)
    b = f3.realise(scan, w3, sigma, 11, False, w3, w3)
    assert np.array_equal(a[0], b[0], equal_nan=True) and np.array_equal(a[2], b[2])
    inj = a[3]
    assert not (inj.amp[w3] > 0).any()
    assert ((a[2] == 1) <= ((inj.amp >= 3) | (w3 & ~w3))).all()
    for code in f3.HELD_OUT:
        _, rows, chans = f3.r2_case(scan, ~w3, sigma, code, 31)
        assert len(rows) and not w3[rows, chans].any()
