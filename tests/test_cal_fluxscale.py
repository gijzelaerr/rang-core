"""The flux-scale term F (task C2d, research/c2d-fluxscale.md): CASA's
`fluxscale` rules on synthetic G tables, against the rules written out in
NumPy, and the point model and append helpers."""

import numpy as np
import pytest
from rang import cal_fluxscale
from rang.formats import caltable

FIELDS = ["PRIMARY", "SECONDARY", "OTHER"]


def subtables(nant, freqs):
    return {
        "ANTENNA": {"NAME": [f"m{a:03d}" for a in range(nant)]},
        "SPECTRAL_WINDOW": {
            "NAME": [f"spw{w}" for w in range(len(freqs))],
            "CHAN_FREQ": [np.array([f]) for f in freqs],
        },
        "FIELD": {"NAME": list(FIELDS)},
    }


def make_table(amps, phases=None, flags=None, freqs=(1.0e9, 1.4e9)):
    """`amps[field][spw]`: (time, ant, 2) amplitudes; one G table with every
    (field, spw), times distinct per field."""
    nant = next(iter(next(iter(amps.values())).values())).shape[1]
    sub = subtables(nant, freqs)
    rng = np.random.default_rng(20261106)
    tables = []
    for f, per_spw in amps.items():
        for w, a in per_spw.items():
            nt = a.shape[0]
            ph = rng.uniform(-np.pi, np.pi, a.shape) if phases is None else phases
            values = (a * np.exp(1j * ph))[:, :, None, :]
            fl = None if flags is None else flags.get((f, w))
            if fl is not None:
                fl = fl[:, :, None, :]
            times = 1000.0 * (f + 1) + 10.0 * np.arange(nt)
            tables.append(
                caltable.from_gains(
                    "G",
                    times,
                    list(range(nant)),
                    values,
                    fl,
                    subtables=sub,
                    field_id=f,
                    spw=w,
                )
            )
    return cal_fluxscale.append(tables[0], *tables[1:])


def numpy_fluxscale(table, ref, tran, nspw, nant, threshold=-1.0):
    """The rules of the note's section 0.1, written out again in NumPy."""
    p = table.params[:, 0, :]
    amp = np.sqrt(p.real.astype(float) ** 2 + p.imag.astype(float) ** 2).astype(
        np.float32
    )
    flag = table.flags[:, 0, :]
    field = table.column("FIELD_ID")
    spw = table.column("SPECTRAL_WINDOW_ID")
    ant = table.column("ANTENNA1")

    def median(values, total):
        v = np.sort(values)
        n = len(v)
        n2 = (n - 1) // 2
        return 0.5 * (v[n2] + v[n2 + 1]) if n % 2 == 0 and total <= 100 else v[n2]

    def means(f):
        mg = np.zeros((nspw, nant, 2))
        ok = np.zeros((nspw, nant, 2), bool)
        for w in range(nspw):
            sel = (field == f) & (spw == w)
            vals = amp[sel][~flag[sel]]
            med = np.float32(median(vals, sel.sum() * 2)) if len(vals) else 0
            for a in range(nant):
                for h in range(2):
                    r = sel & (ant == a)
                    g = amp[r, h][~flag[r, h]].astype(float)
                    if threshold >= 0:
                        lo = np.float32(1 - threshold) if 0 < threshold < 1 else 0.0
                        g = g[(g >= lo * med) & (g <= (1 + threshold) * float(med))]
                    if len(g):
                        mg[w, a, h], ok[w, a, h] = g.mean(), True
        return mg, ok

    refs = [means(f) for f in ref]
    mgref = np.zeros((nspw, nant, 2))
    nok = np.zeros((nspw, nant, 2))
    for mg, ok in refs:
        mgref += np.where(ok, mg, 0)
        nok += ok
    refok = nok > 0
    mgref = np.where(refok, mgref / np.maximum(nok, 1), 0)
    out = {}
    for f in tran:
        mg, ok = means(f)
        for w in range(nspw):
            good = ok[w] & refok[w] & (mgref[w] > 0)
            r = (mg[w] / np.where(good, mgref[w], 1))[good]
            if not len(r):
                continue
            ratio = median(r, 2 * nant)
            rms = np.std(r, ddof=1) if len(r) > 1 else 0.0
            err = 2 * rms / np.sqrt(len(r) - 1) if len(r) > 1 else 0.0
            out[(f, w)] = (ratio**2, err, len(r), ratio)
    return out


def amplitudes(rng, nt, nant, scale=1.0):
    return scale * rng.uniform(0.8, 1.2, (nt, nant, 2))


def test_flux_is_the_squared_median_ratio_and_the_table_is_scaled():
    rng = np.random.default_rng(1)
    nant = 5
    base = {w: amplitudes(rng, 3, nant) for w in (0, 1)}
    amps = {
        0: base,
        1: {w: base[w] * np.sqrt([4.0, 3.0][w]) for w in (0, 1)},
    }
    table = make_table(amps)
    ftab, rec = cal_fluxscale.fluxscale(table, reference="PRIMARY")
    assert rec["1"]["0"]["fluxd"][0] == pytest.approx(4.0, rel=1e-6)
    assert rec["1"]["1"]["fluxd"][0] == pytest.approx(3.0, rel=1e-6)
    assert rec["1"]["0"]["numSol"][0] == 2 * nant
    # Two windows: a first-order fit through both points.
    alpha = np.log10(3.0 / 4.0) / np.log10(1.4)
    assert rec["1"]["spidx"][1] == pytest.approx(alpha, rel=1e-6)
    assert rec["1"]["fitRefFreq"] == pytest.approx(np.sqrt(1.0e9 * 1.4e9))
    p_in, p_out = table.params, ftab.params
    f = table.column("FIELD_ID")
    w = table.column("SPECTRAL_WINDOW_ID")
    assert np.array_equal(p_out[f == 0], p_in[f == 0])
    for spw, s in ((0, 2.0), (1, np.sqrt(3.0))):
        sel = (f == 1) & (w == spw)
        assert np.allclose(np.abs(p_out[sel]), np.abs(p_in[sel]) / s, rtol=1e-6)


def test_rules_match_numpy_with_flags_and_two_references():
    rng = np.random.default_rng(2)
    nant, nspw = 7, 2
    amps = {f: {w: amplitudes(rng, 4, nant, [1, 1.1, 1.7][f]) for w in range(nspw)}
            for f in range(3)}  # fmt: skip
    flags = {
        (0, 0): rng.random((4, nant, 2)) < 0.2,
        (1, 0): rng.random((4, nant, 2)) < 0.2,
        (2, 1): rng.random((4, nant, 2)) < 0.3,
    }
    flags[(0, 0)][:, 3, :] = True  # antenna 3 has no reference in field 0
    table = make_table(amps, flags=flags)
    for threshold in (-1.0, 0.15):
        _, rec = cal_fluxscale.fluxscale(
            table, reference="PRIMARY,SECONDARY", transfer="OTHER",
            gainthreshold=threshold,
        )  # fmt: skip
        want = numpy_fluxscale(table, [0, 1], [2], nspw, nant, threshold)
        for (f, w), (fd, err, n, _) in want.items():
            got = rec[str(f)][str(w)]
            assert got["fluxd"][0] == pytest.approx(fd, rel=1e-12)
            assert got["fluxdErr"][0] == pytest.approx(err, rel=1e-12)
            assert got["numSol"][0] == n


def test_even_count_median_follows_the_array_size():
    # 64 antennas: 128 ratios, an even count over 100 elements: the lower
    # middle value, not the mean (casacore's median).
    rng = np.random.default_rng(3)
    nant = 64
    base = amplitudes(rng, 1, nant)
    sec = base * rng.uniform(1.9, 2.1, base.shape)
    table = make_table({0: {0: base}, 1: {0: sec}}, freqs=(1.4e9,))
    _, rec = cal_fluxscale.fluxscale(table, reference=0)
    ratios = np.sort((sec / base).astype(np.float32).astype(float).ravel())
    r = rec["rang"]["mgratio"][0, 1]
    assert r == pytest.approx(ratios[63], rel=1e-6)
    assert r != pytest.approx(0.5 * (ratios[63] + ratios[64]), rel=1e-9)
    # One window: no fit; the flux at that window's frequency.
    assert rec["1"]["fitFluxd"] == rec["1"]["0"]["fluxd"][0]
    assert rec["1"]["fitRefFreq"] == 1.4e9


def test_selection_errors_and_refspwmap():
    rng = np.random.default_rng(4)
    nant = 4
    amps = {f: {w: amplitudes(rng, 2, nant) for w in (0, 1)} for f in (0, 1, 2)}
    flags = {(0, 1): np.ones((2, nant, 2), bool)}
    table = make_table(amps, flags=flags)
    # The reference has no window-1 gains: no scale there unless mapped.
    _, rec = cal_fluxscale.fluxscale(table, reference="PRIMARY")
    assert rec["1"]["1"]["fluxd"][0] == -1.0
    _, rec = cal_fluxscale.fluxscale(table, reference="PRIMARY", refspwmap=[0, 0])
    assert rec["1"]["1"]["fluxd"][0] > 0
    # transfer given: other fields' rows are written unscaled (as CASA).
    ftab, rec = cal_fluxscale.fluxscale(table, reference=0, transfer="SECONDARY,0")
    f = ftab.column("FIELD_ID")
    assert ftab.nrows == table.nrows
    assert np.array_equal(ftab.params[f == 2], table.params[f == 2])
    assert not np.array_equal(ftab.params[f == 1], table.params[f == 1])
    assert "2" not in rec and "0" not in rec
    dup = cal_fluxscale.append(table, table)
    with pytest.raises(ValueError, match="multiple gain solutions"):
        cal_fluxscale.fluxscale(dup, reference=0)
    with pytest.raises(ValueError, match="not ported"):
        cal_fluxscale.fluxscale(table, reference=0, antenna="m000")
    with pytest.raises(ValueError, match="reference field must"):
        cal_fluxscale.fluxscale(table, reference="")


def test_smodel_array():
    m = cal_fluxscale.smodel_array(3, 2, (2.0, 0.5, 0.25, 0.1))
    assert m.shape == (3, 2, 4) and m.dtype == np.complex64
    assert np.allclose(m[1, 1], [2.5, 0.25 + 0.1j, 0.25 - 0.1j, 1.5])
    assert np.array_equal(cal_fluxscale.smodel_array(1, 1)[0, 0], [1, 0, 0, 1])
