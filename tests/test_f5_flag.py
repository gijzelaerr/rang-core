"""F5 (research/f5-flagger.md): the Rust features against the NumPy
reference at every ladder level and fit degree, the split-stem Rust logits
against the PyTorch network on the materialised planes, G-perm on a
relabelled scan, the block planes on a wide scan-long antenna-local
injection, and the helpers of the gates, on small synthetic scans."""

import numpy as np
import pytest
from rang import f3flag as f3
from rang import f5flag as f5
from rang import f5net

from tests.test_f4_flag import synthetic


def _scan(**kw):
    kw.setdefault("nant", 8)
    kw.setdefault("nt", 6)
    kw.setdefault("nc", 128)
    return synthetic(phases=True, **kw)


@pytest.mark.parametrize(("level", "degree"), [(0, 1), (0, 2), (0, 3), (1, 2), (2, 2)])
def test_features_match_numpy_reference(level, degree):
    scan = _scan()
    flagged = scan["input_flags"].any(-1)
    sel = np.arange(len(f3.index(scan)["ubl"]))
    r = f5.rust_features(scan, flagged, sel, level, degree)
    n = f5.features_numpy(scan, flagged, sel, level, degree)
    assert r.shape == (len(sel), 6, 128, f5.nplanes(level))
    assert np.abs(r - n).max() <= 1e-4
    # The block planes are not all zero, and the mask is the last plane.
    blk = r[..., f5.CELL_PLANES + (8 if level <= 1 else 0) :][..., :-1]
    assert np.abs(blk).max() > 0.1
    ix = f3.index(scan)
    mask = np.ones(r.shape[:3], bool)
    mask[ix["bl"], ix["t"]] = flagged | ~np.isfinite(scan["data"]).all(-1)
    assert np.array_equal(r[..., -1] != 0, mask)


def test_weight_counts():
    assert [f5.weight_count(k) for k in (0, 1, 2)] == [3201, 3169, 3105]


@pytest.mark.parametrize("level", [0, 1, 2])
def test_split_stem_logits_match_pytorch(level):
    torch = pytest.importorskip("torch")
    scan = _scan()
    flagged = scan["input_flags"].any(-1)
    ix = f3.index(scan)
    n = f5.nplanes(level)
    rng = np.random.default_rng(3)
    arrays = [
        (w, rng.normal(0, 0.1, b.shape).astype(np.float32))
        for w, b in f5net.init_arrays(9, n, True)
    ]
    x = f5.rust_features(scan, flagged, np.arange(len(ix["ubl"])), level, 2)
    with torch.no_grad():
        zt = f5net.build(n, True, arrays)(torch.from_numpy(x)).numpy()[
            ix["bl"], ix["t"]
        ]
    zr = f5.rust_logits(scan, flagged, f5net.flat_from_arrays(arrays), level, 2)
    d = np.abs(zr - zt)[~flagged]
    assert np.quantile(d, 0.999) <= 1e-4 and d.max() <= 1e-3


def test_relabelled_antennas_give_identical_logits():
    scan = _scan()
    flagged = scan["input_flags"].any(-1)
    w = f5net.flat_from_arrays(f5net.init_arrays(2, 33, True))
    z0 = f5.rust_logits(scan, flagged, w)
    a0 = f5.rust_anomaly(scan, flagged)
    for seed in (20265201, 20265202):
        s2, _ = f5.relabel(scan, seed)
        assert np.array_equal(f5.rust_logits(s2, flagged, w), z0)
        assert np.array_equal(f5.rust_anomaly(s2, flagged), a0, equal_nan=True)


def test_wide_antenna_band_is_seen_by_the_block_planes():
    scan = _scan(nant=10, nt=8, nc=256, source=50.0)
    ix = f3.index(scan)
    flagged = np.zeros(scan["data"].shape[:2], bool)
    ant = 4
    rows = (scan["antenna1"] == ant) | (scan["antenna2"] == ant)
    rng = np.random.default_rng(8)
    band = slice(60, 140)
    phase = rng.uniform(-np.pi, np.pi)
    scan["data"][np.ix_(rows, np.arange(256)[band])] += (
        10.0 * np.exp(1j * phase)
    ).astype(np.complex64)
    a = f5.rust_anomaly(scan, flagged)
    hit = a > 5
    inband = np.zeros_like(hit)
    inband[np.ix_(rows, np.arange(256)[band])] = True
    assert hit[inband].mean() >= 0.9
    assert hit[~rows].mean() <= 0.05
    x = f5.rust_features(scan, flagged, np.arange(len(ix["ubl"])))
    # asinh max(z_p, z_q) of the cross family: the parallel hands carry the
    # source, where the shift is signed (section 1) and Q is the plane for it.
    zmax = x[..., f5.CELL_PLANES + 8 + 3]
    on = np.flatnonzero((ix["ant1"] == ant) | (ix["ant2"] == ant))
    off = np.setdiff1d(np.arange(len(ix["ubl"])), on)
    assert np.median(np.abs(zmax[on][:, :, band])) > 2 * np.median(
        np.abs(zmax[off][:, :, band])
    )


def test_gate_helpers():
    scan = _scan(nant=40, nt=2, nc=16)
    live = f5.live_antennas(scan)
    keep = f5.drop_draw(scan, 4, 20265301)
    assert len(keep) == len(live) - 4
    assert np.array_equal(keep, f5.drop_draw(scan, 4, 20265301))
    sub, rows = f5.subarray(scan, keep)
    assert np.isin(sub["antenna1"], keep).all() and len(rows) == len(sub["times"])
    lay = f5.layouts(scan)
    assert len(lay["core16"]) == 16 and len(lay["outer32"]) == 32
    av = f5.average_channels(scan)
    assert av["data"].shape[1] == 4 and np.allclose(av["chan_width"], 4 * 2.1e5)
    s2, perm = f5.relabel(scan, 1)
    assert np.allclose(
        np.asarray(s2["antenna_position"])[perm[live]],
        np.asarray(scan["antenna_position"])[live],
    )


def test_bad_level_is_refused():
    scan = _scan(nant=4, nt=2, nc=16)
    flagged = scan["input_flags"].any(-1)
    with pytest.raises(RuntimeError, match="code 3"):
        f5.rust_anomaly(scan, flagged, level=3)
    with pytest.raises(RuntimeError, match="code 3"):
        f5.rust_anomaly(scan, flagged, degree=4)


def _inj(scan, seed=5):
    flagged = scan["input_flags"].any(-1)
    sigma = f3.baseline_sigma(scan, ~flagged)
    return f5.Injector(scan, ~flagged, sigma, np.random.default_rng(seed)), flagged


def test_t7_is_noise_on_one_antenna_and_labelled_by_beta():
    scan = _scan(nant=8, nt=8, nc=256)
    inj, flagged = _inj(scan)
    inj.t7()
    ev = inj.events[-1]
    hit = inj.beta > 0
    rows = np.flatnonzero(hit.any(1))
    k = ev["antenna"]
    assert ((scan["antenna1"][rows] == k) | (scan["antenna2"][rows] == k)).all()
    assert (inj.amp == 0).all()
    assert np.allclose(inj.beta[hit], ev["beta"])
    lab = f5.labels(inj, ~flagged)
    want = 1 if ev["beta"] >= 0.5 else -1
    assert (lab[hit & ~flagged] == want).all()
    assert (lab[flagged] == -1).all()
    t = np.zeros_like(flagged)
    t[0, :10] = True
    lab2 = f5.labels(inj, ~flagged, t, np.zeros_like(t))
    assert (lab2[t & ~hit] == -1).all()


def test_ramps_rise_from_zero_and_are_held_out():
    scan = _scan(nant=8, nt=12, nc=256)
    flagged = scan["input_flags"].any(-1)
    sigma = f3.baseline_sigma(scan, ~flagged)
    for code in ("H4", "H4n"):
        _, rows, _ = f5.r2_case(scan, ~flagged, sigma, code, 31)
        assert len(rows) > 0
        assert code not in f5.TRAIN_MORPHOLOGIES
    inj = f5.Injector(scan, ~flagged, sigma, np.random.default_rng(3), fixed=10.0)
    inj.held_out("H4")
    t = f3.index(scan)["t"]
    per_t = [inj.amp[t == k].max() for k in range(12)]
    assert min(per_t) < 1.0 and max(per_t) > 5.0


def test_trainer_resumes_to_the_same_weights(tmp_path):
    pytest.importorskip("torch")
    import subprocess
    import sys
    from pathlib import Path

    rng = np.random.default_rng(0)
    for role in ("train", "validation"):
        d = tmp_path / "shards" / role
        d.mkdir(parents=True)
        for kind in ("real", "sim"):
            x = rng.normal(0, 1, (4, 3, 256, 33)).astype(np.float16)
            y = (rng.random((4, 3, 256)) < 0.1).astype(np.int8)
            np.savez(d / f"{kind}.npz", x=x, y=y, kind=kind)
    script = str(Path(__file__).resolve().parents[1] / "examples" / "f5_train.py")
    common = [sys.executable, script, str(tmp_path / "shards")]
    opts = ["--seed", "1", "--steps", "40", "--device", "cpu"]
    subprocess.run([*common, str(tmp_path / "a"), *opts], check=True)
    subprocess.run([*common, str(tmp_path / "b"), *opts, "--stop-at", "20"], check=True)
    subprocess.run([*common, str(tmp_path / "b"), *opts], check=True)
    wa = np.load(tmp_path / "a" / "weights.npz")["flat"]
    wb = np.load(tmp_path / "b" / "weights.npz")["flat"]
    assert wa.size == 3201 and np.array_equal(wa, wb)


def test_one_pass_matches_two_and_antenna_arrays_match_numpy():
    scan = _scan()
    flagged = scan["input_flags"].any(-1)
    w = f5net.flat_from_arrays(f5net.init_arrays(4, 33, True))
    logit, anom = f5.rust_logits_anomaly(scan, flagged, w)
    assert np.array_equal(logit, f5.rust_logits(scan, flagged, w))
    assert np.array_equal(anom, f5.rust_anomaly(scan, flagged), equal_nan=True)
    m = f5.method_flags(scan, flagged, w, 0.0, kappa=4.0)
    with np.errstate(invalid="ignore"):
        assert np.array_equal(m, flagged | (logit > 0) | (anom > 4.0))
    r = f5.rust_antenna(scan, flagged)
    n = f5.antenna_numpy(scan, flagged)
    for k in ("z", "q", "tt", "tf"):
        a, b = r[k], n[k]
        fin = np.isfinite(b)
        assert np.array_equal(np.isfinite(a), fin), k
        if fin.any():
            assert np.abs(a - b)[fin].max() <= 1e-6 * max(1.0, np.abs(b[fin]).max()), k
    assert np.isfinite(n["z"]).any() and np.isfinite(n["q"]).any()


def test_variance_planes_are_defined_and_match_numpy_on_256_channels():
    scan = _scan(nant=8, nt=10, nc=256)
    flagged = scan["input_flags"].any(-1)
    sel = np.arange(len(f3.index(scan)["ubl"]))
    r = f5.rust_features(scan, flagged, sel, 0, 2)
    n = f5.features_numpy(scan, flagged, sel, 0, 2)
    var = r[..., 28:32]
    assert np.abs(var).max() > 0.1
    assert np.abs(r - n).max() <= 1e-4
