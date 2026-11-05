"""Fast synthetic tests of B1-3 (research/b1-3-pointing-selfcal.md)."""

import json
import math

import numpy as np
import pytest
from rang import beam_holography as bh
from rang import beam_identifiability as bi
from rang import pointing_selfcal as ps
from scipy import ndimage

LIGHT = bi.LIGHTSPEED


# --------------------------------------------------------------------------
# A small synthetic array


def _small_scan(
    nant=6, ntime=8, nchan=32, seed=0, f0=1.30e9, df=1.0e6, q0=-0.6, dq=0.15
):
    rng = np.random.default_rng(seed)
    pos = rng.uniform(-600, 600, (nant, 2))
    pairs = [(p, q) for p in range(nant) for q in range(p + 1, nant)]
    rows = []
    for t in range(ntime):
        ang = 0.04 * t
        rot = np.array(
            [[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]]
        )
        for p, q in pairs:
            b = rot @ (pos[q] - pos[p])
            rows.append((t, p, q, b[0], b[1], rng.uniform(-20, 20)))
    rows = np.array(rows)
    n = len(rows)
    freqs = f0 + df * np.arange(nchan)
    nbins = math.ceil(ntime / ps.TIME_BIN)
    return {
        "time": 1e9 + 8.0 * rows[:, 0],
        "a1": rows[:, 1].astype(int),
        "a2": rows[:, 2].astype(int),
        "uvw": rows[:, 3:6],
        "freqs": freqs,
        "positions": np.zeros((nant, 3)),
        "phase_dir": np.zeros(2),
        "q_bins": q0 + dq * np.arange(nbins),
        "data": np.zeros((n, nchan, 4), np.complex64),
        "flag": np.zeros((n, nchan, 4), bool),
        "weight": np.ones((n, nchan, 4), np.float32),
    }


def _sky(lm, flux, nchan, nu0):
    lm = np.asarray(lm, float)
    k = len(lm)
    flux = np.asarray(flux, float)
    return {
        "lm": lm,
        "kind": np.zeros(k, np.uint8),
        "gauss_shape": np.zeros((k, 3)),
        "beamed": np.ones(k, bool),
        "gauge_flux": flux,
        "base": [np.repeat(flux[:, None], nchan, 1)],
    }


def _small_beams(nant, squints, ratio=1.05, fwhm=1.0):
    return ps.SimpleBeams(
        [
            bi.GaussianSimpleBeam(fwhm, squint_deg=sq, ratio=ratio)
            for sq in squints[:nant]
        ],
        average=bi.GaussianSimpleBeam(fwhm, ratio=ratio),
    )


def _simulate(d, sky, beams, delta, gains):
    """Fill d["data"] with the model (noise free) at truth delta and gains."""
    sc = ps.prepare_scan(d, [1.0, 1.0])
    nu0 = float(d["freqs"].mean())
    prob = ps.Problem([sc], sky, beams, nu0, nproc=1, extra={"truth_gains": [gains]})
    params = {"delta": delta}
    out = prob.map([(0, f, params, None, "predict") for _s, f in prob.tasks])
    for r in out:
        ch = np.arange(
            r["block"] * ps.BLOCK, r["block"] * ps.BLOCK + r["pred"].shape[1]
        )
        d["data"][:, ch, 0] = r["pred"][..., 0]
        d["data"][:, ch, 3] = r["pred"][..., 1]
    return d


# --------------------------------------------------------------------------
# Normal equations


def test_normals_columns_equal_block_normals_for_identical_beams():
    rng = np.random.default_rng(1)
    nant, n, k = 5, 60, 3
    a1 = rng.integers(0, nant - 1, n)
    a2 = np.minimum(a1 + 1 + rng.integers(0, 2, n), nant - 1)
    z = rng.normal(size=(n, k)) + 1j * rng.normal(size=(n, k))
    gamma = rng.normal(size=(k, 2)) + 1j * rng.normal(size=(k, 2))
    beta = rng.normal(size=(k, 6))
    ref = bi.block_normals(a1, a2, nant, z, gamma[None, None], beta[None, None])
    new = bi.normals_columns(
        a1, a2, nant, z, [(z @ gamma, z @ np.conj(gamma), z @ beta)]
    )
    assert np.max(np.abs(new - ref)) <= 1e-10 * np.max(np.abs(ref))


def test_normals_columns_rhs_is_jacobian_transpose_residual():
    rng = np.random.default_rng(2)
    nant, n, k = 4, 40, 2
    a1 = rng.integers(0, nant - 1, n)
    a2 = np.minimum(a1 + 1, nant - 1)
    z = rng.normal(size=(n, k)) + 1j * rng.normal(size=(n, k))
    y1 = rng.normal(size=(n, 2)) + 1j * rng.normal(size=(n, 2))
    y2 = rng.normal(size=(n, 2)) + 1j * rng.normal(size=(n, 2))
    d = rng.normal(size=(n, 3)) + 1j * rng.normal(size=(n, 3))
    r = rng.normal(size=n) + 1j * rng.normal(size=n)
    h, b = bi.normals_columns(a1, a2, nant, z, [(y1, y2, d)], r)
    m = z.sum(1)
    cols = []
    for a in range(nant):
        cols.append(m * ((a1 == a) + (a2 == a)))
    for a in range(nant):
        cols.append(1j * m * ((a1 == a).astype(float) - (a2 == a)))
    cols += list(z.T)
    for j in range(2):
        for a in range(nant):
            cols.append(y1[:, j] * (a1 == a) + y2[:, j] * (a2 == a))
    cols += list(d.T)
    jac = np.array(cols).T
    dense_h = (np.conj(jac).T @ jac).real
    dense_b = (np.conj(jac).T @ r).real
    assert np.allclose(h, dense_h, atol=1e-9 * np.abs(dense_h).max())
    assert np.allclose(b, dense_b, atol=1e-9 * np.abs(dense_b).max())


def test_channel_survey_equals_b12_survey_on_channel_bins():
    """With one channel per bin, the per-channel accumulator gives B1-2's
    Survey information (validated there against a dense projection)."""
    rng = np.random.default_rng(4)
    nant, k = 4, 3
    old = bi.Survey(nant, k, anchored=False)
    new = bi.ChannelSurvey(nant, k, 1, 1, ncom=6)
    freqs = 1.3e9 + 2e6 * np.arange(6)
    for c, nu in enumerate(freqs):
        for hand in range(2):
            n = 30
            a1 = rng.integers(0, nant - 1, n)
            a2 = np.minimum(a1 + 1 + rng.integers(0, 2, n), nant - 1)
            z = rng.normal(size=(n, k)) + 1j * rng.normal(size=(n, k))
            gamma = rng.normal(size=(k, 2)) + 1j * rng.normal(size=(k, 2))
            beta = rng.normal(size=(k, 6))
            h = bi.block_normals(a1, a2, nant, z, gamma[None, None], beta[None, None])
            old.add(0, c, hand, nu, h, n)
            new.add(0, c, hand, math.log(nu / 1.31e9), h, n)
    kappa = {(0, 0): 1.7, (0, 1): 0.6}
    a = old.information(kappa, 1.31e9)
    b = new.information(kappa)
    for key in a:
        scale = max(np.abs(a[key]).max(), 1e-30)
        assert np.max(np.abs(a[key] - b[key])) <= 1e-8 * scale, key


# --------------------------------------------------------------------------
# Beams


@pytest.fixture
def product(tmp_path):
    margin = (np.arange(bh.NPIX) - bh.CENTRE_INDEX) * bh.PIXEL_DEG
    nchan = 6
    freq_mhz = 1000.0 + 10.0 * np.arange(nchan)
    y, x = np.meshgrid(margin, margin, indexing="ij")

    def maps(x0, y0, fwhm, scale):
        out = np.zeros((4, nchan, len(margin), len(margin)), np.complex64)
        for c in range(nchan):
            w = fwhm * (1 + 0.05 * c)
            v = np.exp(-2 * np.log(2) * ((x - x0) ** 2 + (y - y0) ** 2) / w**2)
            out[0, c] = scale * v
            out[3, c] = 0.95 * v
            out[1, c] = 0.01j * v * (x - x0)
        return out

    average = maps(0.02, -0.03, 1.0, 1.0)
    np.save(tmp_path / "array_average_native.npy", average)
    channels = [0, 2, 5]
    a0 = maps(0.05, -0.01, 1.02, 1.0)[:, channels]
    a1 = maps(-0.03, 0.04, 0.98, 1.01)[:, channels]
    np.save(tmp_path / "antennas_sampled.npy", np.stack([a0, a1], axis=1))
    np.savez(
        tmp_path / "small.npz",
        pols=np.array([b"HH", b"HV", b"VH", b"VV"]),
        antnames=np.array([b"m000", b"m001", b"array_average"]),
        freq_MHz=freq_mhz,
        margin_deg=margin,
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"channels_sampled": channels, "antennas_sampled": [0, 1]})
    )
    return bh.HolographyBeam(tmp_path), freq_mhz * 1e6, channels


def test_antenna_rule_is_the_antenna_at_product_channels(product):
    beam, freqs, channels = product
    beams = ps.AntennaBeams(beam, [0, 1], radius_deg=0.6)
    x = np.array([[0.1, -0.25, 0.3], [0.0, 0.2, -0.4]])
    yy = np.array([[0.05, 0.1, -0.2], [0.3, -0.1, 0.15]])
    for c in channels:
        e, _ex, _ey = beams.evaluate(beams.prepare(freqs[c]), x, yy)
        for i in range(2):
            ref = beam.jones(i, x[i], yy[i], freqs[c])
            assert np.max(np.abs(e[i] - ref)) < 1e-6
    # between product channels: average native + linear difference
    f = 0.5 * (freqs[2] + freqs[3])
    e, _, _ = beams.evaluate(beams.prepare(f), x, yy)
    t = (f - freqs[2]) / (freqs[5] - freqs[2])
    for i in range(2):
        raw = beam.raw_jones("array_average", x[i], yy[i], f)
        for k, w in ((2, 1 - t), (5, t)):
            raw = raw + w * (
                beam.raw_jones(i, x[i], yy[i], freqs[k])
                - beam.raw_jones("array_average", x[i], yy[i], freqs[k])
            )
        centre = beam.raw_jones("array_average", np.zeros(1), np.zeros(1), f)
        for k, w in ((2, 1 - t), (5, t)):
            centre = centre + w * (
                beam.raw_jones(i, np.zeros(1), np.zeros(1), freqs[k])
                - beam.raw_jones("array_average", np.zeros(1), np.zeros(1), freqs[k])
            )
        norm = math.sqrt(bh.stokes_i(centre)[0])
        assert np.max(np.abs(e[i] - raw / norm)) < 1e-6


def test_antenna_beam_gradients_match_finite_differences(product):
    beam, freqs, _ = product
    beams = ps.AntennaBeams(beam, [0, 1], radius_deg=0.6)
    hd = beams.prepare(0.5 * (freqs[1] + freqs[2]))
    x = np.array([[0.1, -0.25], [0.0, 0.2]])
    y = np.array([[0.05, 0.1], [0.3, -0.1]])
    _, ex, ey = beams.evaluate(hd, x, y)
    eps = 1e-5
    fx = (beams.evaluate(hd, x + eps, y)[0] - beams.evaluate(hd, x - eps, y)[0]) / (
        2 * eps
    )
    fy = (beams.evaluate(hd, x, y + eps)[0] - beams.evaluate(hd, x, y - eps)[0]) / (
        2 * eps
    )
    assert np.max(np.abs(ex - fx)) < 1e-6 * np.abs(ex).max()
    assert np.max(np.abs(ey - fy)) < 1e-6 * np.abs(ey).max()


def test_sample_stack_matches_map_coordinates():
    rng = np.random.default_rng(3)
    maps = rng.normal(size=(2, 2, 2, 24, 24))
    coeffs = np.stack(
        [
            ps._stack8(
                *(
                    np.stack(
                        [
                            ndimage.spline_filter(m, order=3)
                            for m in part.reshape(-1, 24, 24)
                        ]
                    ).reshape(2, 2, 24, 24)
                    for part in (maps[0], maps[1])
                )
            )
        ]
    )
    rows = rng.uniform(3, 20, (1, 30))
    cols = rng.uniform(3, 20, (1, 30))
    value, _, _ = ps.sample_stack(coeffs, rows, cols)
    for ch in range(8):
        ref = ndimage.map_coordinates(
            coeffs[0, ..., ch], np.stack([rows[0], cols[0]]), order=3, prefilter=False
        )
        assert np.max(np.abs(value[0, :, ch] - ref)) < 1e-12


def test_pair_term_derivatives_match_finite_differences():
    beams = _small_beams(3, [(0.02, -0.01), (-0.01, 0.02), (0.0, 0.03)])
    hd = beams.prepare(1.3e9)
    u = np.array([[0.2, -0.1], [-0.3, 0.25], [0.05, 0.4]])
    delta = np.array([[0.3, -0.2], [0.1, 0.4], [-0.5, 0.0]])
    bp, bq = np.array([0, 0, 1]), np.array([1, 2, 2])
    sq, el = np.array([0.2, -0.1]), 0.01
    for h in range(2):
        base = ps.pair_terms(
            ps.beam_terms(beams, hd, u, delta, sq, el)[h], bp, bq, "fit"
        )
        eps = 1e-5
        for p in range(3):
            for j in range(2):
                dp = delta.copy()
                dp[p, j] += eps
                dm = delta.copy()
                dm[p, j] -= eps
                fp = ps.pair_terms(
                    ps.beam_terms(beams, hd, u, dp, sq, el)[h], bp, bq, "fit"
                )["F"]
                fm = ps.pair_terms(
                    ps.beam_terms(beams, hd, u, dm, sq, el)[h], bp, bq, "fit"
                )["F"]
                fd = (fp - fm) / (2 * eps)
                ana = (
                    base["dp"][..., j] * (bp == p)[:, None]
                    + base["dq"][..., j] * (bq == p)[:, None]
                )
                assert np.max(np.abs(ana - fd)) < 1e-7
        fp = ps.pair_terms(
            ps.beam_terms(beams, hd, u, delta, sq, el + eps)[h], bp, bq, "fit"
        )["F"]
        fm = ps.pair_terms(
            ps.beam_terms(beams, hd, u, delta, sq, el - eps)[h], bp, bq, "fit"
        )["F"]
        assert np.max(np.abs(base["de"] - (fp - fm) / (2 * eps))) < 1e-7
        for j in range(2):
            sp, sm = sq.copy(), sq.copy()
            sp[j] += eps
            sm[j] -= eps
            fp = ps.pair_terms(
                ps.beam_terms(beams, hd, u, delta, sp, el)[h], bp, bq, "fit"
            )["F"]
            fm = ps.pair_terms(
                ps.beam_terms(beams, hd, u, delta, sm, el)[h], bp, bq, "fit"
            )["F"]
            ana = 0.5 * ps.SIGMA_HAND[h] * (base["dp"][..., j] + base["dq"][..., j])
            assert np.max(np.abs(ana - (fp - fm) / (2 * eps))) < 1e-7


def test_jax_reference_path_gradient():
    """Our analytic pointing columns against JAX forward differentiation of
    the existing reference predictor `pointing.predict` (conventions
    mapped: its phase is -2 pi, x = cos b l + sin b m with b = pi - q, which
    flips y)."""
    jax = pytest.importorskip("jax")
    jax.config.update("jax_enable_x64", True)
    import jax.numpy as jnp
    from rang import pointing

    d = _small_scan(nant=4, ntime=2, nchan=3, seed=5)
    q = float(d["q_bins"][0])
    lm = np.array([[0.004, -0.003], [-0.006, 0.002]])
    flux = np.array([1.0, 0.5])
    nrow = len(d["a1"])
    freqs = d["freqs"]
    delta = np.array([[0.4, -0.2], [0.1, 0.3], [-0.2, 0.1], [0.0, -0.4]])
    comps = pointing.component_list(
        lm[:, 0], lm[:, 1], flux, spectral_index=0.0, reference_hz=1.3e9
    )
    rows = np.repeat(np.arange(nrow), len(freqs))
    obs = pointing.Observation(
        jnp.asarray(d["uvw"][rows]),
        jnp.asarray(np.tile(freqs, nrow)),
        jnp.asarray(d["a1"][rows]),
        jnp.asarray(d["a2"][rows]),
        jnp.zeros(len(rows), int),
        jnp.full(len(rows), math.pi - q),
    )
    theirs_offset = np.stack((delta[:, 0], -delta[:, 1]), 1)[None]
    v_jax = np.asarray(pointing.predict(comps, obs, jnp.asarray(theirs_offset)))
    jac = np.asarray(
        jax.jacfwd(lambda o: pointing.predict(comps, obs, o))(
            jnp.asarray(theirs_offset)
        )
    )
    beams = ps.ScaledGaussianBeams(4)
    x, y = bi.measures.sky_to_beam(lm[:, 0], lm[:, 1], q)
    u = np.degrees(np.stack((x, y), 1))
    bp, bq = d["a1"], d["a2"]
    for ci, nu in enumerate(freqs):
        pt = ps.pair_terms(
            ps.beam_terms(beams, beams.prepare(nu), u, delta)[0], bp, bq, "fit"
        )
        tau = ps._delays(d["uvw"], lm)
        amp = np.exp(2j * np.pi / LIGHT * nu * tau) * flux
        ours = np.sum(amp * pt["F"], 1)
        sel = rows * 0 + np.tile(np.arange(len(freqs)), nrow) == ci
        assert np.max(np.abs(np.conj(ours) - v_jax[sel])) < 1e-12
        y1, y2, _ = ps.sample_columns(amp, pt, np.arange(nrow), 1.0, 0)
        for p in range(4):
            for j, sign in ((0, 1.0), (1, -1.0)):
                ana = y1[:, j] * (bp == p) + y2[:, j] * (bq == p)
                ref = jac[sel, 0, p, j] * sign
                assert np.max(np.abs(np.conj(ana) - ref)) < 1e-10 * max(
                    1, np.abs(ref).max()
                )


# --------------------------------------------------------------------------
# The solver on a small array


def _small_problem(seed=0, noise=0.0, nant=6, nchan=32):
    d = _small_scan(nant=nant, ntime=8, nchan=nchan, seed=seed)
    nu0 = float(d["freqs"].mean())
    lm = np.radians([[0.35, -0.2], [-0.3, 0.25], [0.1, 0.4], [0.0, 0.0]])
    flux = np.array([1.0, 0.8, 0.6, 2.0])
    sky = _sky(lm, flux, nchan, nu0)
    rng = np.random.default_rng(seed + 10)
    squints = [tuple(rng.normal(0, 0.01, 2)) for _ in range(nant)]
    beams = _small_beams(nant, squints)
    delta = rng.normal(0, 0.6, (nant, 2))
    gains = np.exp(
        rng.normal(0, 0.05, (nchan, 2, nant))
        + 1j * rng.uniform(-np.pi, np.pi, (nchan, 2, nant))
    )
    d = _simulate(d, sky, beams, delta, gains)
    if noise:
        d["data"] += (
            noise
            * (rng.normal(size=d["data"].shape) + 1j * rng.normal(size=d["data"].shape))
        ).astype(np.complex64)
    return d, sky, beams, delta, nu0


def test_physical_pointing_recovers_offsets_noise_free():
    d, sky, beams, delta, nu0 = _small_problem()
    sc = ps.prepare_scan(d, [1e-8, 1e-8])
    prob = ps.Problem([sc], sky, beams, nu0, nproc=1)
    res = ps.solve(prob, "ii", log=lambda *a: None, max_passes=12)
    got = res["state"]["delta"][0]
    assert np.max(np.abs(got - delta)) < 2e-3, (got, delta)


def test_rang_recovers_contrasts_noise_free():
    d, sky, beams, delta, nu0 = _small_problem(seed=1)
    sc = ps.prepare_scan(d, [1e-6, 1e-6])  # tiny noise scale: every direction passes
    prob = ps.Problem([sc], sky, beams, nu0, nproc=1)
    res = ps.solve(
        prob,
        "R",
        candidates={"antenna", "interval_common"},
        log=lambda *a: None,
        max_passes=12,
    )
    got = res["state"]["delta"][0]
    assert np.max(np.abs(got - delta)) < 2e-3
    assert all(r["selected"] for r in res["selection"]["antenna"])


def test_selection_reproduces_identifiability_verdict():
    """R's selection measures from its first pass equal the per-channel
    survey's measures when the two models coincide (identical beams, no
    squint, unit gains, apparent = intrinsic x beam)."""
    nant = 5
    d = _small_scan(nant=nant, ntime=4, nchan=32, seed=3, dq=0.0)
    nu0 = float(d["freqs"].mean())
    lm = np.radians([[0.3, -0.2], [-0.25, 0.2], [0.0, 0.0]])
    flux = np.array([1.0, 0.7, 2.0])
    beams = _small_beams(nant, [(0.0, 0.0)] * nant, ratio=1.05)
    sky = _sky(lm, flux, 32, nu0)
    gains = np.ones((32, 2, nant), complex)
    d = _simulate(d, sky, beams, np.zeros((nant, 2)), gains)
    s2 = [0.04, 0.04]
    sc = ps.prepare_scan(d, s2)
    # the survey's apparent fluxes: intrinsic x the (common) beam at each bin
    # are not one number per component when q changes, so use a single bin
    sc["rows_by_bin"] = [np.arange(len(d["a1"]))]
    sc["q"] = sc["q"][:1]
    prob = ps.Problem([sc], sky, beams, nu0, nproc=1)
    first = prob.run_pass(ps.initial_state(prob, True, ps.NCOM_FIT), None, "fit")
    active = [np.ones(nant, bool)]
    _, _, rec = ps.select_directions(
        prob, first, active, {"antenna", "interval_common", "squint", "ellipticity"}
    )
    # the survey: ratio mode with apparent fluxes S * I_b(component)
    x, y = bi.measures.sky_to_beam(lm[:, 0], lm[:, 1], sc["q"][0])
    u = np.degrees(np.stack((x, y), 1))
    app = []
    for c, nu in enumerate(d["freqs"]):
        e, _, _ = beams.average(u[:, 0], u[:, 1], nu)
        app.append(flux * np.sum(np.abs(e[:, 0, :]) ** 2, -1))
    sky_app = dict(sky)
    sky_app["base"] = [np.array(app).T]
    prob2 = ps.Problem([sc], sky_app, beams, nu0, nproc=1, average=beams)
    acc, _ = prob2.survey([(beams, ps.SUB)])
    info = acc.information({(0, 0): 1 / s2[0], (0, 1): 1 / s2[1]})
    sig_cond = 1 / np.sqrt(np.diag(info["both_primary"])[: 2 * nant])
    ours = np.array(
        [
            r["sigma_conditional"]
            for r in sorted(rec["antenna"], key=lambda r: (r["axis"], r["antenna"]))
        ]
    )
    assert np.allclose(ours, sig_cond, rtol=1e-6), (ours, sig_cond)


def test_g3a_single_component_is_absorbed_by_channel_gains():
    nant = 5
    d = _small_scan(nant=nant, ntime=4, nchan=32, seed=4)
    nu0 = float(d["freqs"].mean())
    lm = np.radians([[0.3, -0.2]])
    sky = _sky(lm, [1.0], 32, nu0)
    rng = np.random.default_rng(9)
    beams = _small_beams(
        nant, [tuple(rng.normal(0, 0.02, 2)) for _ in range(nant)], ratio=1.07
    )
    sc = ps.prepare_scan(d, [1.0, 1.0])
    prob = ps.Problem([sc], sky, beams, nu0, nproc=1, average=beams)
    acc, _ = prob.survey([(beams, ps.SUB)])
    info = acc.information({(0, 0): 1.0, (0, 1): 1.0})
    raw = np.diag(info["raw"])
    both = np.diag(info["both_primary"])
    ok = raw > 0
    rho = np.sqrt(np.clip(both[ok], 0, None) / raw[ok])
    assert rho.max() <= 1e-6, rho.max()


def test_split_reserves_training_cells_per_group():
    d = _small_scan(nant=5, ntime=8, nchan=64, seed=6)
    e = ps.eligible_both(d)
    tb, blr = ps.scan_bins(d)
    ((train, val, test),) = ps.split_cells([(e, tb, blr)], 32)
    assert test.sum() > 0 and val.sum() > 0
    assert not np.any(train & test)
    groups = (tb[:, None] * 2 + np.arange(64)[None] // 32) * 100 + blr[:, None]
    for g in np.unique(groups):
        assert train[groups == g].sum() >= 2


def test_heldout_is_lower_with_the_right_pointing():
    d, sky, beams, _delta, nu0 = _small_problem(seed=2, noise=1e-3, nchan=64)
    e = ps.eligible_both(d)
    tb, blr = ps.scan_bins(d)
    ((train, _val, test),) = ps.split_cells([(e, tb, blr)], 32)
    sc = ps.prepare_scan(d, [2e-6, 2e-6], train, test)
    prob = ps.Problem([sc], sky, beams, nu0, nproc=1)
    g = ps.solve(prob, "G", log=lambda *a: None)
    p = ps.solve(prob, "ii", log=lambda *a: None, max_passes=12)
    kg, vg = ps.heldout(prob, g)
    kp, vp = ps.heldout(prob, p)
    assert np.array_equal(kg, kp)
    call = ps.paired(vp, vg)
    assert call["call"] == "better", call


def test_fit_raster_recovers_offset():
    beam = bi.GaussianSimpleBeam(1.2, squint_deg=(0.0, 0.0))

    def grad(x, y, freq):
        return beam(x, y, freq)

    x_scan = np.array([[0, -1.0], [0, 1.0], [-1.0, 0], [1.0, 0], [0, 0]])
    truth = np.array([0.8, -0.5])
    freqs = np.linspace(1.0e9, 1.6e9, 4)
    y = np.array(
        [3.0 * ps.raster_amplitude(grad, f, x_scan - truth / 60)[0] for f in freqs]
    )
    std = np.full_like(y, 1e-4)
    for select in (False, True):
        fit = ps.fit_raster(
            x_scan, y, std, freqs, ps.per_frequency_amplitude(grad, freqs), select
        )
        assert np.allclose(fit["offset"], truth, atol=1e-4), fit


def test_raster_beam_matches_the_b10_sampler(product):
    beam, freqs, _ = product
    f = np.array([freqs[1] + 1e6, freqs[3]])
    rb = ps.RasterBeam(beam, 1, f, radius_deg=0.6)
    pos = np.array([[0.1, -0.2], [0.0, 0.3], [-0.25, 0.05]])
    amp, grad = rb(pos, np.arange(2))
    for c in range(2):
        j = beam.jones(1, pos[:, 0], pos[:, 1], f[c])
        ref = 0.5 * (np.abs(j[:, 0, 0]) + np.abs(j[:, 1, 1]))
        assert np.max(np.abs(amp[c] - ref)) < 1e-6
    eps = 1e-5
    for k in range(2):
        dp = pos.copy()
        dp[:, k] += eps
        dm = pos.copy()
        dm[:, k] -= eps
        fd = (rb(dp, np.arange(2))[0] - rb(dm, np.arange(2))[0]) / (2 * eps)
        assert np.max(np.abs(grad[..., k] - fd)) < 1e-6


def test_polished_gains_are_the_exact_optimum():
    """Amendment 1: StefCal (capped) then Gauss-Newton polishing reaches the
    least-squares gains, which a long StefCal run confirms."""
    rng = np.random.default_rng(11)
    nant, n = 8, 200
    a1 = rng.integers(0, nant - 1, n)
    a2 = np.minimum(a1 + 1 + rng.integers(0, 3, n), nant - 1)
    model = rng.normal(size=n) + 1j * rng.normal(size=n) + 3.0
    g_true = np.exp(rng.normal(0, 0.1, nant) + 1j * rng.uniform(-np.pi, np.pi, nant))
    data = g_true[a1] * np.conj(g_true[a2]) * model
    data = data + 0.01 * (rng.normal(size=n) + 1j * rng.normal(size=n))
    w = np.ones(n)
    g, _ = ps.stefcal_warm(data, model, w, a1, a2, nant, np.ones(nant), iterations=5)
    g, _steps, _halvings = ps.polish_gains(data, model, w, a1, a2, nant, g, steps=20)
    ref, _ = ps.stefcal_warm(
        data, model, w, a1, a2, nant, np.ones(nant), iterations=20000, tol=1e-14
    )

    def chi2(x):
        return np.sum(np.abs(data - x[a1] * np.conj(x[a2]) * model) ** 2)

    assert chi2(g) <= chi2(ref) * (1 + 1e-12)
    # equal up to the global phase gauge
    ratio = g / ref
    assert np.max(np.abs(ratio / ratio[0] - 1)) < 1e-8


def test_polishing_never_raises_chi2_from_a_bad_start():
    """Amendment 1a: from a start far from the optimum the safeguarded steps
    only lower the bin's chi^2 and stay finite."""
    rng = np.random.default_rng(12)
    nant, n = 6, 12
    a1 = rng.integers(0, nant - 1, n)
    a2 = np.minimum(a1 + 1, nant - 1)
    model = rng.normal(size=n) + 1j * rng.normal(size=n)
    data = rng.normal(size=n) + 1j * rng.normal(size=n)
    w = np.ones(n)
    g0 = np.exp(1j * rng.uniform(-np.pi, np.pi, nant))

    def chi2(x):
        return np.sum(np.abs(data - x[a1] * np.conj(x[a2]) * model) ** 2)

    g, _steps, _halvings = ps.polish_gains(data, model, w, a1, a2, nant, g0)
    assert np.all(np.isfinite(g)) and chi2(g) <= chi2(g0)
