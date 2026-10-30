"""Fast synthetic tests of the B1-2 survey (research/b1-2-identifiability.md)."""

import math

import numpy as np
import pytest
from rang import beam_identifiability as bi
from rang import measures
from scipy import ndimage

LIGHT = bi.LIGHTSPEED


def test_spline_values_and_gradients_match_map_coordinates():
    rng = np.random.default_rng(3)
    maps = rng.normal(size=(2, 2, 24, 24))
    coeffs = np.stack(
        [ndimage.spline_filter(m, order=3) for m in maps.reshape(-1, 24, 24)]
    ).reshape(maps.shape)
    rows = rng.uniform(3, 20, 50)
    cols = rng.uniform(3, 20, 50)
    value = bi.spline_sample(coeffs, rows, cols)
    for i in range(2):
        for j in range(2):
            ref = ndimage.map_coordinates(
                coeffs[i, j], np.stack([rows, cols]), order=3, prefilter=False
            )
            assert np.max(np.abs(value[i, j] - ref)) < 1e-12
    eps = 1e-5
    for order, (dr, dc) in (((1, 0), (eps, 0)), ((0, 1), (0, eps))):
        grad = bi.spline_sample(coeffs, rows, cols, order)
        plus = bi.spline_sample(coeffs, rows + dr, cols + dc)
        minus = bi.spline_sample(coeffs, rows - dr, cols - dc)
        fd = (plus - minus) / (2 * eps)
        assert np.max(np.abs(grad - fd)) < 1e-6 * max(1.0, np.max(np.abs(grad)))


def test_toy_beam_gradient():
    beam = bi.GaussianToyBeam(1.0, squint_deg=(0.02, -0.01), ratio=1.1)
    x, y = np.array([0.3, -0.2]), np.array([0.1, 0.4])
    _e, ex, ey = beam(x, y, 1e9)
    eps = 1e-6
    fx = (beam(x + eps, y, 1e9)[0] - beam(x - eps, y, 1e9)[0]) / (2 * eps)
    fy = (beam(x, y + eps, 1e9)[0] - beam(x, y - eps, 1e9)[0]) / (2 * eps)
    assert np.allclose(ex, fx, atol=1e-8) and np.allclose(ey, fy, atol=1e-8)


# --------------------------------------------------------------------------
# A small synthetic array and the dense reference


def _setup(lm, seed=0, nant=4, ntime=4, nchan=8, fluxes=None):
    rng = np.random.default_rng(seed)
    pos = rng.uniform(-400, 400, (nant, 2))
    pairs = [(p, q) for p in range(nant) for q in range(p + 1, nant)]
    rows = []
    for t in range(ntime):
        ang = 0.05 * t
        rot = np.array(
            [[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]]
        )
        for p, q in pairs:
            b = rot @ (pos[q] - pos[p])
            rows.append((t, p, q, b[0], b[1], rng.uniform(-20, 20)))
    rows = np.array(rows)
    freqs = np.linspace(1.3e9, 1.4e9, nchan)
    k = len(lm)
    sky = {
        "lm": np.asarray(lm, float),
        "kind": np.zeros(k, np.uint8),
        "flux": np.asarray(fluxes if fluxes is not None else np.linspace(1, 0.5, k)),
        "coeffs": np.zeros((k, 1)),
        "ref_freq": np.full(k, 1.35e9),
        "gauss_shape": np.zeros((k, 3)),
    }
    return {
        "time_bin": rows[:, 0].astype(int) // 2,
        "a1": rows[:, 1].astype(int),
        "a2": rows[:, 2].astype(int),
        "uvw": rows[:, 3:6],
        "freqs": freqs,
        "sky": sky,
        "nant": nant,
        "weights": rng.uniform(0.5, 2.0, (len(rows), nchan, 2)),
    }


def _survey(setup, beam, q=0.0, fblock=4, slope=False):
    """Run the factorised survey and return (Survey, per-sample dense data)."""
    nant, sky = setup["nant"], setup["sky"]
    survey = bi.Survey(
        nant, len(sky["lm"]), anchored=False, gain_sets=2 if slope else 1
    )
    freqs = setup["freqs"]
    dense = []
    for t in np.unique(setup["time_bin"]):
        rows = np.flatnonzero(setup["time_bin"] == t)
        for f in range(len(freqs) // fblock):
            ch = np.arange(f * fblock, (f + 1) * fblock)
            nu = freqs[ch].mean()
            fac = bi.factors_at(beam, sky["lm"], q, nu)
            kt = bi.phase_terms(setup["uvw"][rows], freqs[ch], sky)
            s = bi.spectra(sky, freqs[ch])
            terms = kt * s.T[None]
            for hand in range(2):
                w = setup["weights"][rows][:, ch, hand]
                z = (terms * np.sqrt(w)[..., None]).reshape(-1, len(sky["lm"]))
                a1 = np.repeat(setup["a1"][rows], len(ch))
                a2 = np.repeat(setup["a2"][rows], len(ch))
                gamma = fac["gamma"][None, None, :, hand]
                beta = fac["beta"][None, None, :, hand]
                xs = np.tile(
                    (np.arange(len(ch)) - (len(ch) - 1) / 2) / len(ch), len(rows)
                )
                h = bi.block_normals(
                    a1, a2, nant, z, gamma, beta, slope=xs if slope else None
                )
                survey.add(0, f, hand, nu, h, len(a1))
                dense.append(
                    (
                        t,
                        f,
                        hand,
                        a1,
                        a2,
                        z,
                        fac["gamma"][:, hand],
                        fac["beta"][:, hand],
                        nu,
                        xs if slope else None,
                    )
                )
    return survey, dense


def _dense_information(dense, nant, ncomp, nf, nu0):
    """Dense real-stacked columns and the exact projections."""
    nsamp = sum(len(d[3]) for d in dense)
    bins = sorted({(d[0], d[1], d[2]) for d in dense})
    bin_index = {b: i for i, b in enumerate(bins)}
    sets = 1 if dense[0][9] is None else 2
    ng = len(bins) * 2 * nant * sets
    cols_g = np.zeros((nsamp, ng), complex)
    cols_strict = np.zeros((nsamp, nf * ncomp), complex)
    cols_primary = np.zeros((nsamp, 2 * ncomp), complex)
    cols_theta = np.zeros((nsamp, 2 * nant + 6), complex)
    at = 0
    for t, f, hand, a1, a2, z, gamma, beta, nu, xs in dense:
        n = len(a1)
        sl = slice(at, at + n)
        model = z.sum(1)
        b0 = bin_index[(t, f, hand)] * 2 * nant * sets
        for i in range(n):
            r = at + i
            for p, sign in ((a1[i], 1), (a2[i], -1)):
                cols_g[r, b0 + p] = model[i]
                cols_g[r, b0 + nant + p] = sign * 1j * model[i]
                if sets == 2:
                    cols_g[r, b0 + 2 * nant + p] = model[i] * xs[i]
                    cols_g[r, b0 + 3 * nant + p] = sign * 1j * model[i] * xs[i]
        cols_strict[sl, f * ncomp : (f + 1) * ncomp] = z
        cols_primary[sl, :ncomp] = z
        cols_primary[sl, ncomp:] = z * math.log(nu / nu0)
        y1 = z @ gamma
        y2 = z @ np.conj(gamma)
        for i in range(n):
            r = at + i
            for j in range(2):
                cols_theta[r, j * nant + a1[i]] += y1[i, j]
                cols_theta[r, j * nant + a2[i]] += y2[i, j]
        cols_theta[sl, 2 * nant :] = z @ beta
        at += n

    def stack(c):
        return np.concatenate((c.real, c.imag))

    g, st, pr, th = map(stack, (cols_g, cols_strict, cols_primary, cols_theta))

    def prof(nuis):
        if nuis is None:
            return np.einsum("ij,ij->j", th, th)
        coef = np.linalg.lstsq(nuis, th, rcond=None)[0]
        r = th - nuis @ coef
        return np.einsum("ij,ij->j", r, r)

    return {
        "raw": prof(None),
        "gains": prof(g),
        "sky_primary": prof(pr),
        "sky_strict": prof(st),
        "both_primary": prof(np.hstack((g, pr))),
        "both_strict": prof(np.hstack((g, st))),
    }


@pytest.mark.parametrize("slope", [False, True])
def test_schur_survey_equals_dense_projection(slope):
    setup = _setup([[0.0, 0.0], [0.006, 0.002], [-0.004, 0.007]], seed=1)
    beam = bi.GaussianToyBeam(1.2, squint_deg=(0.01, 0.005), ratio=1.05)
    survey, dense = _survey(setup, beam, slope=slope)
    info = survey.information({(0, 0): 1.0, (0, 1): 1.0}, nu0=1.35e9)
    ref = _dense_information(dense, setup["nant"], 3, 2, 1.35e9)
    for key, value in ref.items():
        got = np.diag(info[key])
        scale = np.max(np.abs(value))
        assert np.max(np.abs(got - value)) <= 1e-9 * scale, key


def test_single_component_is_degenerate():
    setup = _setup([[0.005, -0.003]], seed=2, fluxes=[2.0])
    beam = bi.GaussianToyBeam(1.0, squint_deg=(0.01, 0.0))
    survey, _ = _survey(setup, beam)
    info = survey.information({(0, 0): 1.0, (0, 1): 1.0}, nu0=1.35e9)
    raw = np.diag(info["raw"])
    both = np.diag(info["both_primary"])
    ok = raw > 0
    assert ok.sum() > 6
    assert np.all(np.sqrt(np.clip(both[ok], 0, None) / raw[ok]) <= 1e-6)


def test_two_components_identifiable_and_fisher_matches_finite_difference():
    lm = [[0.0, 0.0], [math.radians(0.5), 0.0]]
    setup = _setup(lm, seed=4, fluxes=[1.0, 0.5])
    beam = bi.GaussianToyBeam(1.0, squint_deg=(0.003, 0.002), ratio=1.07)
    survey, dense = _survey(setup, beam)
    info = survey.information({(0, 0): 1.0, (0, 1): 1.0}, nu0=1.35e9)
    nant = setup["nant"]
    rho = np.sqrt(
        np.clip(np.diag(info["both_primary"]), 0, None) / np.diag(info["raw"])
    )
    assert rho[0] > 0.05  # antenna 0, pointing x
    # Raw information against a finite-difference model with the perturbed beam.
    sky = setup["sky"]
    eps = 1e-4

    def perturbed(kind, d, xk, yk, nu):
        """(E of antenna 0, E of the others) with direction `kind` moved by d."""
        e0 = beam(xk, yk, nu)[0]
        if kind == "p0x":
            return beam(xk - d / 60, yk, nu)[0], e0
        if kind == "width":
            e = beam(xk * math.exp(-d), yk * math.exp(-d), nu)[0]
        elif kind == "ellip":
            e = beam(xk * math.exp(-d), yk * math.exp(d), nu)[0]
        else:  # squint_x: H row at u - s/2, V row at u + s/2
            e = beam(xk - d / 120, yk, nu)[0]
            e[:, 1] = beam(xk + d / 120, yk, nu)[0][:, 1]
        return e, e

    def visibilities(kind, d):
        vals = []
        for _t, _f, hand, a1, a2, z, _g, _b, nu, _xs in dense:
            fac = bi.factors_at(beam, sky["lm"], 0.0, nu)
            xk, yk = fac["x_deg"], fac["y_deg"]
            ref = np.sum(np.abs(beam(xk, yk, nu)[0][:, hand]) ** 2, axis=-1)
            e_first, e_other = perturbed(kind, d, xk, yk, nu)
            ep = np.where(
                (a1 == 0)[:, None, None], e_first[None, :, hand], e_other[None, :, hand]
            )
            eq = np.where(
                (a2 == 0)[:, None, None], e_first[None, :, hand], e_other[None, :, hand]
            )
            b = np.sum(ep * np.conj(eq), axis=-1) / ref[None, :]
            vals.append((z * b).sum(1))
        return np.concatenate(vals)

    raw = np.diag(info["raw"])
    for kind, index in (
        ("p0x", 0),
        ("width", 2 * nant + 2),
        ("ellip", 2 * nant + 3),
        ("squint_x", 2 * nant + 4),
    ):
        s = (visibilities(kind, eps) - visibilities(kind, -eps)) / (2 * eps)
        fisher = float(np.sum(s.real**2 + s.imag**2))
        assert abs(fisher - raw[index]) <= 1e-6 * raw[index], kind


def test_noise_scale_recovers_known_variance():
    rng = np.random.default_rng(5)
    w = rng.uniform(1, 3, (2000, 64))
    sigma = 1.7 / np.sqrt(w)
    data = 5.0 + sigma * (rng.normal(size=w.shape) + 1j * rng.normal(size=w.shape))
    out = bi.noise_scale(data, w, np.ones(w.shape, bool))
    assert abs(out["s2"] / 1.7**2 - 1) < 0.02


def test_hogbom_recovers_point():
    n = 64
    yy, xx = np.mgrid[:n, :n]
    psf = np.exp(-((xx - n // 2) ** 2 + (yy - n // 2) ** 2) / 8.0)
    dirty = 3.0 * np.roll(np.roll(psf, 5, 0), -7, 1)
    comp, _res, _ = bi.hogbom(dirty, psf, 32, gain=0.2, threshold=1e-4, max_iter=500)
    assert abs(comp.sum() - 3.0) < 1e-3
    py, px = np.unravel_index(np.argmax(comp), comp.shape)
    assert (py - 16, px - 16) == (5, -7)


def test_stefcal_recovers_gains():
    rng = np.random.default_rng(6)
    nant = 6
    pairs = [(p, q) for p in range(nant) for q in range(p + 1, nant)] * 5
    a1 = np.array([p for p, _ in pairs])
    a2 = np.array([q for _, q in pairs])
    g = rng.uniform(0.8, 1.2, nant) * np.exp(1j * rng.uniform(-1, 1, nant))
    model = rng.normal(size=len(a1)) + 1j * rng.normal(size=len(a1)) + 3
    data = g[a1] * np.conj(g[a2]) * model
    sol, _ = bi.stefcal(data, model, np.ones(len(a1)), a1, a2, nant, False, 300, 1e-12)
    ratio = sol / g
    assert np.allclose(np.abs(ratio), 1, atol=1e-6)
    phase = np.angle(ratio * np.conj(ratio[0]))
    assert np.allclose(phase, 0, atol=1e-6)


# --------------------------------------------------------------------------
# measures


MEERKAT = np.array([5109360.13332123, 2006852.58604291, -3238948.12747888])


def test_parallactic_angle_sign_and_closed_form():
    pytest.importorskip("astropy")
    ra, dec = math.radians(243.79583), math.radians(-60.90583)
    t0 = 5064151193.482062
    times = t0 + np.arange(0, 8 * 3600, 3600.0)
    q = measures.parallactic_angle(times, ra, dec, MEERKAT)
    fast = measures.parallactic_angle_closed_form(times, ra, dec, MEERKAT)
    assert np.max(np.abs(np.degrees(np.angle(np.exp(1j * (q - fast)))))) <= 0.01
    # the ESO137 track rises through transit: q increases through zero
    assert np.all(np.diff(q) > 0)
    assert q[0] < 0 < q[-1]


def test_sky_to_beam_rotation():
    x, y = measures.sky_to_beam(1.0, 0.0, 0.0)
    assert (x, y) == (-1.0, 0.0)
    x, y = measures.sky_to_beam(0.0, 1.0, math.pi / 2)
    assert np.allclose((x, y), (1.0, 0.0))


@pytest.mark.parametrize("q", [0.0, 0.7])
def test_pointing_factor_vanishes_at_centre_without_squint(q):
    beam = bi.GaussianToyBeam(1.0)
    fac = bi.factors_at(beam, np.zeros((1, 2)), q, 1e9)
    assert np.allclose(fac["gamma"], 0) and np.allclose(fac["beta"], 0)
