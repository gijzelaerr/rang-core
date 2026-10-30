"""B1-0 beam product: range reader, sampler, normalisation, controls.

Offline: a synthetic stored npz stands in for the SARAO release and a
synthetic product directory for the fetched product
(research/b1-beam-pointing.md)."""

import json

import numpy as np
import pytest
from rang import beam_holography as bh


def _gaussian_maps(margin, x0, y0, fwhm, nchan):
    y, x = np.meshgrid(margin, margin, indexing="ij")
    out = np.zeros((4, nchan, len(margin), len(margin)), np.complex64)
    for c in range(nchan):
        width = fwhm * (1 + 0.1 * c)
        voltage = np.exp(-2 * np.log(2) * ((x - x0) ** 2 + (y - y0) ** 2) / width**2)
        out[0, c] = voltage
        out[3, c] = 0.9 * voltage
        out[1, c] = 0.01j * voltage
    return out


@pytest.fixture
def product(tmp_path):
    margin = (np.arange(bh.NPIX) - bh.CENTRE_INDEX) * bh.PIXEL_DEG
    nchan = 6
    freq_mhz = 1000.0 + 10.0 * np.arange(nchan)
    average = _gaussian_maps(margin, 0.05, -0.1, 1.0, nchan)
    np.save(tmp_path / "array_average_native.npy", average)
    channels = [0, 2, 5]
    sampled = np.stack([average[:, channels], 1.01 * average[:, channels]], axis=1)
    np.save(tmp_path / "antennas_sampled.npy", sampled)
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
    return tmp_path, average, freq_mhz


def test_stored_npz_range_reader(tmp_path):
    rng = np.random.default_rng(3)
    beam = (
        rng.normal(size=(4, 3, 5, 8, 8)) + 1j * rng.normal(size=(4, 3, 5, 8, 8))
    ).astype(np.complex64)
    path = tmp_path / "cube.npz"
    np.savez(
        path, beam=beam, freq_MHz=np.arange(5.0), antnames=np.array([b"a", b"b", b"c"])
    )
    read = bh.file_reader(path)
    members = bh.npz_members(read)
    assert members["beam.npy"]["method"] == 0
    assert members["beam.npy"]["shape"] == (4, 3, 5, 8, 8)
    np.testing.assert_array_equal(
        bh.read_member(read, members["freq_MHz.npy"]), np.arange(5.0)
    )
    for pol, ant, chan in [(0, 0, 0), (2, 1, 3), (3, 2, 4)]:
        maps = bh.read_maps(read, members["beam.npy"], pol, ant, chan, 1)
        np.testing.assert_array_equal(maps[0], beam[pol, ant, chan])
    run = bh.read_maps(read, members["beam.npy"], 1, 2, 1, 3)
    np.testing.assert_array_equal(run, beam[1, 2, 1:4])
    with pytest.raises(IndexError):
        bh.map_offset(members["beam.npy"], 4, 0, 0)


def test_object_members_refused(tmp_path):
    path = tmp_path / "obj.npz"
    np.savez(path, names=np.array(["a", None], dtype=object))
    read = bh.file_reader(path)
    members = bh.npz_members(read)
    with pytest.raises(ValueError):
        bh.read_member(read, members["names.npy"])


def test_sampler_nodes_normalisation_and_frequency(product):
    path, average, freq_mhz = product
    beam = bh.HolographyBeam(path)
    margin = beam.margin_deg
    x = margin[60:70]
    y = margin[50:60]
    raw = beam.raw_jones("array_average", x, y, freq_mhz[2] * 1e6)
    np.testing.assert_allclose(
        raw[:, 0, 0], average[0, 2, 50:60, 60:70].diagonal(), rtol=1e-6
    )
    power = beam.power_i("array_average", np.zeros(1), np.zeros(1), freq_mhz[3] * 1e6)
    np.testing.assert_allclose(power, 1.0, rtol=1e-12)
    # Linear in frequency between native channels.
    mid = beam.raw_jones("array_average", x, y, 0.5 * (freq_mhz[1] + freq_mhz[2]) * 1e6)
    lo = beam.raw_jones("array_average", x, y, freq_mhz[1] * 1e6)
    hi = beam.raw_jones("array_average", x, y, freq_mhz[2] * 1e6)
    np.testing.assert_allclose(mid, 0.5 * (lo + hi), rtol=1e-6, atol=1e-7)
    # Antennas use the product channels only (0, 2, 5).
    a1 = beam.raw_jones(1, x, y, freq_mhz[2] * 1e6)
    np.testing.assert_allclose(a1, 1.01 * hi, rtol=1e-5)
    with pytest.raises(ValueError):
        beam.raw_jones("array_average", np.array([4.5]), np.array([0.0]), 1e9)
    with pytest.raises(ValueError):
        beam.raw_jones("array_average", x, y, 2e9)


def test_flip_and_main_lobe_fit(product):
    path, _, freq_mhz = product
    x, y = bh.grid(1.5, bh.PIXEL_DEG / 2)
    for flip in (1, -1):
        beam = bh.HolographyBeam(path, flip=flip)
        power = beam.power_i("array_average", x, y, freq_mhz[0] * 1e6)
        fit = bh.fit_main_lobe(power, x, y)
        assert fit["x0_deg"] == pytest.approx(0.05, abs=2e-3)
        assert fit["y0_deg"] == pytest.approx(-0.1 * flip, abs=2e-3)
        # exp(-2 ln2 r^2 / w^2) in voltage is a power FWHM of w = 1 deg.
        assert fit["fwhm_major_deg"] == pytest.approx(1.0, rel=5e-3)


def test_lobe_radii_on_a_sinc_squared_profile():
    r = np.linspace(0.0, 3.0, 3001)
    with np.errstate(invalid="ignore", divide="ignore"):
        profile = np.where(r == 0, 1.0, (np.sin(np.pi * r) / (np.pi * r)) ** 2)
    radii = bh.lobe_radii(r, profile)
    assert radii["r_half_power_deg"] == pytest.approx(0.4429, abs=1e-3)
    assert radii["r_first_null_deg"] == pytest.approx(1.0, abs=2e-3)
    assert radii["r_second_null_deg"] == pytest.approx(2.0, abs=2e-3)
    assert radii["first_sidelobe_level"] == pytest.approx(0.0472, abs=1e-3)


def test_stokes_i_of_identity_is_one():
    assert bh.stokes_i(np.eye(2)) == pytest.approx(1.0)


def test_katbeam_control_is_diagonal_and_normalised():
    pytest.importorskip("katbeam")
    model = bh.KatBeam()
    x, y = bh.grid(1.0, 0.25)
    jones = model.jones(0, x, y, 1.284e9)
    assert np.all(jones[..., 0, 1] == 0) and np.all(jones[..., 1, 0] == 0)
    assert model.power_i(0, np.zeros(1), np.zeros(1), 1.284e9)[0] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        model.jones(0, x, y, 1.7e9)


def test_eidos_control_normalised_and_close_to_katbeam():
    pytest.importorskip("eidos")
    pytest.importorskip("katbeam")
    eidos, kat = bh.EidosBeam(npix=128), bh.KatBeam()
    x, y = bh.grid(1.5, bh.PIXEL_DEG)
    assert eidos.power_i(0, np.zeros(1), np.zeros(1), 1.284e9)[0] == pytest.approx(1.0)
    fe = bh.fit_main_lobe(eidos.power_i(0, x, y, 1.284e9), x, y)
    fk = bh.fit_main_lobe(kat.power_i(0, x, y, 1.284e9), x, y)
    assert fe["fwhm_major_deg"] == pytest.approx(fk["fwhm_major_deg"], rel=0.05)
