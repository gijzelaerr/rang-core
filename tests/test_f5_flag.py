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
