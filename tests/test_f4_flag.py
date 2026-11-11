"""F4 (research/f4-flagger.md): the Rust features against the NumPy
reference, the Rust logits against the JAX network, the spectral planes on
a wide scan-long antenna-local injection, T6 and H3, the labels and the
data guards, on small synthetic scans."""

import numpy as np
import pytest
from rang import f3flag as f3
from rang import f3net
from rang import f4flag as f4
from rang.core_injection_model import make_injection


def synthetic(nant=6, nt=7, nc=96, seed=3, source=20.0, phases=False):
    rng = np.random.default_rng(seed)
    p, q = np.triu_indices(nant, 1)
    rows = [(t, a, b) for t in range(nt) for a, b in zip(p, q, strict=True)]
    t_, a1, a2 = (np.array(x) for x in zip(*rows, strict=True))
    n = len(rows)
    data = (rng.normal(0, 1, (n, nc, 4)) + 1j * rng.normal(0, 1, (n, nc, 4))).astype(
        np.complex64
    )
    if phases:
        nbl = len(p)
        phi = rng.uniform(-np.pi, np.pi, nbl)[np.arange(n) % nbl]
        rate = rng.uniform(-0.3, 0.3, nbl)[np.arange(n) % nbl]
        src = source * np.exp(1j * (phi + rate * t_))
        data[..., [0, 3]] += src[:, None, None].astype(np.complex64)
    else:
        data[..., [0, 3]] += source
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


def test_features_match_numpy_reference_and_keep_f3s_planes():
    scan = synthetic()
    flagged = scan["input_flags"].any(-1)
    sel = np.arange(len(f3.index(scan)["ubl"]))
    r = f4.rust_features(scan, flagged, sel)
    n = f4.features_numpy(scan, flagged, sel)
    assert r.shape == (len(sel), 7, 96, 23)
    assert np.abs(r - n).max() <= 1e-4
    old = f3.rust_features(scan, flagged, sel)
    assert np.array_equal(r[..., :14], old[..., :14])
    assert np.array_equal(r[..., 22], old[..., 14])
    # The spectral planes are constant in time on unflagged cells.
    spec = r[..., f4.SPEC0 : f4.SPEC0 + 8]
    ok = r[..., 22] == 0
    ref = spec.max(1, keepdims=True)
    assert np.allclose(np.where(ok[..., None], spec, ref), ref)


def test_logits_match_jax():
    pytest.importorskip("jax")
    scan = synthetic()
    flagged = scan["input_flags"].any(-1)
    params = f3net.init_params(5, nplanes=f4.NPLANES)
    assert f3net.count_weights(params) == 4009
    assert f3net.count_weights(f3net.init_params(5)) == 3433
    ix = f3.index(scan)
    x = f4.rust_features(scan, flagged, np.arange(len(ix["ubl"])))
    zj = np.asarray(f3net.forward(params, x))[ix["bl"], ix["t"]]
    zr = f4.rust_logits(scan, flagged, f3net.flat_weights(params))
    assert np.abs(zr - zj)[~flagged].max() <= 1e-3


def test_wide_scan_long_antenna_band_is_seen_by_the_spectral_planes_only():
    """F1's antenna-local injection (`make_injection`, all times, one antenna,
    coherent phasor conjugated at the far end), widened by its occupancy to
    about 100 of 256 channels, at 10 sigma on a calibrator-like scan whose
    parallel hands carry a 50-sigma source with per-baseline phases."""
    scan = synthetic(nant=16, nt=6, nc=256, seed=7, source=50.0, phases=True)
    scan["input_flags"][:] = False
    w3 = np.zeros(scan["data"].shape[:2], bool)
    state = {
        "data": scan["data"],
        "train": ~w3,
        "validation": w3,
        "test": w3,
        "original_flags": scan["input_flags"],
        "original_rows": np.zeros(len(w3), bool),
        "antenna1": scan["antenna1"],
        "antenna2": scan["antenna2"],
        "times": scan["times"],
        "weights": np.ones(scan["data"].shape, np.float32),
        "window": np.ones(w3.shape[1], bool),
    }
    mask, _, meta = make_injection(state, "antenna-local", 1.0, 19, occupancy=0.05)
    assert 60 <= meta["channels"][1] - meta["channels"][0] <= 140
    rows, chans = np.nonzero(mask)
    sigma = f3.baseline_sigma(scan, ~w3)
    p = scan["antenna1"][rows]
    ph = np.random.default_rng(1).uniform(-np.pi, np.pi)
    phasor = np.exp(1j * ph) * np.ones(len(rows))
    phasor = np.where(p == meta["antenna"], phasor, phasor.conj())
    data = scan["data"].copy()
    data[rows, chans, :] += (10 * sigma[rows] * phasor)[:, None].astype(np.complex64)
    ze = f4.ze_flags(scan, w3, data)
    z2 = f3.z2_flags(scan, w3, data)
    assert ze[rows, chans].mean() >= 0.9
    assert z2[rows, chans].mean() <= 0.2
    other = ~mask
    assert ze[other].mean() <= 0.01
    # The cross family alone carries it (noise-dominated hands).
    s = f4.strength_rows(scan, w3, data)
    assert np.median(s[rows, chans]) >= 5


def test_t6_and_h3_are_seeded_wide_and_on_eligible_cells():
    scan = synthetic(nant=8, nt=6, nc=128)
    w3 = scan["input_flags"].any(-1)
    sigma = f3.baseline_sigma(scan, ~w3)
    a = f4.realise(scan, w3, sigma, 11, False, w3, w3, np.zeros(w3.shape))
    b = f4.realise(scan, w3, sigma, 11, False, w3, w3, np.zeros(w3.shape))
    assert np.array_equal(a[0], b[0], equal_nan=True) and np.array_equal(a[2], b[2])
    inj = a[3]
    t6 = [e for e in inj.events if e["code"] == "T6"]
    assert 1 <= len(t6) <= 3
    assert not (inj.amp[w3] > 0).any()
    code = 1 + f4.CODES.index("T6")
    cells = inj.morph == code
    assert cells.any()
    widths = cells.sum(1)[cells.any(1)]
    assert widths.max() <= int(0.6 * 128)
    rng = np.random.default_rng(0)
    ws = [f4.t6_width(rng, 2048) for _ in range(2000)]
    assert min(ws) >= 9 and max(ws) <= 400 and np.median(ws) > 40
    assert max(f4.t6_width(rng, 512) for _ in range(500)) <= 307
    _, rows, chans = f4.r2_case(scan, ~w3, sigma, "H3", 31)
    assert len(rows) and not w3[rows, chans].any()
    ants = np.r_[scan["antenna1"][rows], scan["antenna2"][rows]]
    counts = np.bincount(ants, minlength=8)
    assert (counts >= counts.max() // 3).sum() >= 2
    assert len(np.unique(chans)) >= int(0.1 * 128)
    for c in f4.HELD_OUT:
        _, rows, chans = f4.r2_case(scan, ~w3, sigma, c, 32)
        assert len(rows)
    env = f4.raised_cosine(20, np.arange(5, 15))
    assert env[5] < 1 and env[14] < 1 and env[9] == 1 and env[0] == 1


def test_labels():
    amp = np.array([[0, 4, 1, 0, 0, 0]], np.float32)
    elig = np.array([[1, 1, 1, 1, 1, 0]], bool)
    t = np.array([[0, 0, 0, 1, 1, 0]], bool)
    a = np.array([[0, 0, 0, 1, 0, 0]], bool)
    s = np.array([[1, 1, 1, 4, 1, 1]], np.float32)
    lt = f4.labels_target(amp, elig, t, a, s)
    assert lt.tolist() == [[0, 1, -1, -1, -1, -1]]
    s2 = s.copy()
    s2[0, 0] = 3.5
    assert f4.labels_target(amp, elig, t, a, s2)[0, 0] == -1
    lc = f4.labels_calibrator(amp, elig, t, a, s)
    assert lc.tolist() == [[0, 1, -1, 1, -1, -1]]
    assert f4.strong_consensus(t, a, elig, s, 3).tolist() == [[0, 0, 0, 1, 0, 0]]


def test_guards():
    for g in ("MAIN_16", "MAIN_19", "MAIN_3", "MAIN_8", "MAIN_13", "MAIN_1x"):
        with pytest.raises(ValueError):
            f4.check_luno_group(g)
    for g in f4.FETCH_GROUPS:
        with pytest.raises(ValueError):
            f4.check_luno_group(g)
        assert f4.check_luno_group(g, heldout=True) == g
    for c in (1, 3, 15, 17, 18):
        with pytest.raises(ValueError):
            f4.check_eso_chunk(c)
    for c in (11, 12, 13):
        with pytest.raises(ValueError):
            f4.check_eso_chunk(c)
        assert f4.check_eso_chunk(c, heldout=True) == c
    assert f4.check_luno_group("MAIN_1") == "MAIN_1"
    assert f4.real_sets("target", "test") == ["eso:11", "eso:12", "eso:13"]
    assert set(f4.LUNO_ROLE) & set(f4.LUNO_FORBIDDEN) == set()


def test_na_arm_sees_an_uncorrelated_antenna_band_in_the_autos():
    """Amendment 1: NA on synthetic autos (radiometer noise 1e-3, smooth
    per-antenna bandpasses within 0.2 %); a scan-long band of +10 sigma_auto
    on one antenna is found (G2), clean antennas are not flagged."""
    rng = np.random.default_rng(4)
    nant, nt, nc = 10, 8, 256
    f = np.linspace(0, 1, nc)
    bp = 400 * (1 + 0.1 * np.sin(6 * f))[None, None, :, None]
    gain = 1 + 0.002 * np.sin(3 * f[None, :] + rng.uniform(0, 6, (nant, 1)))
    autos = (
        bp * gain[:, None, :, None] * (1 + 1e-3 * rng.normal(size=(nant, nt, nc, 2)))
    )
    clean = f4.na_antenna_hits(autos, 0.01)
    assert clean.mean() < 0.01
    chans = np.arange(60, 160)
    inj = f4.auto_inject(autos, chans, 3)
    hit = f4.na_antenna_hits(inj, 0.01)
    assert hit[3][:, chans].mean() >= 0.9
    others = np.delete(hit, 3, axis=0)
    assert others.mean() < 0.01
    scan = synthetic(nant=nant, nt=nt, nc=nc)
    w3 = np.zeros(scan["data"].shape[:2], bool)
    fl = f4.na_flags(scan, inj, w3, 0.01)
    on3 = (scan["antenna1"] == 3) | (scan["antenna2"] == 3)
    assert fl[on3][:, chans].mean() >= 0.9
    assert fl[~on3].mean() < 0.02
