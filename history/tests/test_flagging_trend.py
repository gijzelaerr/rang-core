import numpy as np
import pytest
from rangtoy.flagging import polar_gauge
from rangtoy.flagging_trend import detrended_tv, estimate_trend


def fixture():
    times, frequencies = np.arange(4, dtype=float), np.arange(7, dtype=float)
    rng = np.random.default_rng(271828)
    base = np.broadcast_to(np.eye(2), (4, 7, 4, 2, 2)).astype(complex).copy()
    base += 0.002 * (rng.normal(size=base.shape) + 1j * rng.normal(size=base.shape))
    valid = np.ones(base.shape[:3], bool)
    return base, valid, times, frequencies


def test_train_estimated_slopes_shift_with_unaliased_receiver_trends():
    gains, valid, t, f = fixture()
    a, b = np.array([0, 0.04, -0.06, 0.08]), np.array([0, 0.1, 0.2, 0.3])
    first, v = polar_gauge(gains, valid)
    phase = t[:, None, None] * a + f[None, :, None] * b
    second, v2 = polar_gauge(gains * np.exp(1j * phase)[..., None, None], valid)
    s1, n1 = estimate_trend(first, v, t, f, valid)
    s2, n2 = estimate_trend(second, v2, t, f, valid)
    assert s2 - s1 == pytest.approx(np.stack([a, b], axis=1), abs=1e-14)
    assert np.array_equal(n1, n2)
    tv1, tv2 = (
        detrended_tv(g, v, t, f, s) for g, v, s in ((first, v, s1), (second, v2, s2))
    )
    assert tv1["edges"] == pytest.approx(tv2["edges"], abs=1e-14, nan_ok=True)


def test_unsupported_gain_values_never_change_training_estimate():
    gains, valid, t, f = fixture()
    support = valid.copy()
    support[-1] = False
    s1, n1 = estimate_trend(gains, valid, t, f, support)
    gains[-1] = complex(np.nan, np.inf)
    s2, n2 = estimate_trend(gains, valid, t, f, support)
    assert np.array_equal(s1, s2)
    assert np.array_equal(n1, n2)


def test_singular_insufficient_and_missing_fit_are_explicit():
    gains, valid, t, f = fixture()
    gains[:, :, 2] = 0
    slopes, counts = estimate_trend(gains, valid, t, f, valid)
    assert np.isnan(slopes[2]).all()
    assert (counts[2] == 0).all()
    tv = detrended_tv(gains, valid, t, f, slopes)
    assert not np.isfinite(tv["edges"][:, :, :, 2]).any()


@pytest.mark.parametrize("bad", [np.arange(4)[::-1], [0, 1, 1, 2], [0, 1, 2, np.nan]])
def test_invalid_native_coordinates_refused(bad):
    gains, valid, _, f = fixture()
    with pytest.raises(ValueError):
        estimate_trend(gains, valid, bad, f, valid)
