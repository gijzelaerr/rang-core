"""The DF-IO formats (research/dfio-formats.md).

Unit tests on synthetic data only: no Docker, no oracle image, no
observation data. The oracle verdicts are made by
`examples/check_formats.py` and archived in
`research/results/dfio-formats.json`, whose structure is checked here.
"""

import io
import json
import math
import pickle
from pathlib import Path

import numpy as np
import pytest
from rang import core_ms_write
from rang.formats import caltable, cli, flagversions, killms, quartical_store, sky

ROOT = Path(__file__).resolve().parents[1]
writer = pytest.mark.skipif(
    not (core_ms_write.has_writer() and core_ms_write.has_creator()),
    reason="extension without the E4 table creation",
)


def spw_subtables(freqs):
    return {
        "SPECTRAL_WINDOW": {
            "CHAN_FREQ": [np.asarray(freqs, float)],
            "CHAN_WIDTH": [np.full(len(freqs), 1e6)],
            "EFFECTIVE_BW": [np.full(len(freqs), 1e6)],
            "RESOLUTION": [np.full(len(freqs), 1e6)],
            "NUM_CHAN": [np.int32(len(freqs))],
            "REF_FREQUENCY": [float(freqs[0])],
            "TOTAL_BANDWIDTH": [1e6 * len(freqs)],
            "MEAS_FREQ_REF": [np.int32(5)],
            "NAME": ["spw0"],
            "NET_SIDEBAND": [np.int32(1)],
            "FLAG_ROW": [False],
            "FREQ_GROUP": [np.int32(0)],
            "FREQ_GROUP_NAME": [""],
            "IF_CONV_CHAIN": [np.int32(0)],
        }
    }


@writer
def test_caltable_round_trip_keywords_and_semantics(tmp_path):
    rng = np.random.default_rng(1)
    times = [100.0, 220.0]
    g = (1 + 0.1 * rng.standard_normal((2, 3, 1, 2))) * np.exp(
        1j * rng.uniform(-1, 1, (2, 3, 1, 2))
    )
    ct = caltable.from_gains(
        "G", times, [0, 1, 2], g, subtables=spw_subtables([1.4e9]), ms_name="x.ms"
    )
    caltable.write(ct, tmp_path / "x.G")
    back = caltable.read(tmp_path / "x.G")
    assert back.vis_cal == "G Jones" and back.kind == "G" and not back.float_param
    assert back.keywords["MSName"] == "x.ms" and back.keywords["ParType"] == "Complex"
    assert back.info[:2] == ["Calibration", "G Jones"]
    assert np.array_equal(back.params, ct.params)
    assert back.reference_antenna == [0]
    assert back.main["WEIGHT"] == [None] * 6
    # Correction at a solution time divides out the gains exactly enough.
    freqs = np.array([1.4e9, 1.41e9])
    a1, a2 = np.array([0, 0, 1]), np.array([1, 2, 2])
    true = np.ones((3, 2, 4), complex)
    data = np.empty_like(true)
    for c, (p, q) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
        data[..., c] = (
            true[..., c] * (g[0, a1, 0, p] * np.conj(g[0, a2, 0, q]))[:, None]
        )
    out, flag = caltable.correct(
        data, np.zeros(data.shape, bool), np.full(3, 100.0), a1, a2, freqs, [back]
    )
    assert not flag.any()
    assert np.max(np.abs(out - true)) < 1e-6


def test_caltable_time_interpolation_tracks_phase():
    # Two slots whose phases differ by more than pi: CASA tracks the phase.
    vals = np.zeros((2, 1, 1, 2), np.float32)
    vals[:, 0, 0, 0] = 1
    vals[0, 0, 0, 1] = np.float32(3.0)
    vals[1, 0, 0, 1] = caltable._track_phase(np.array([3.0, -3.0], np.float32))[1]
    out, fl = caltable._interpolate(
        np.array([10.0, 20.0]), vals, np.zeros((2, 1, 1), bool), [15.0]
    )
    assert abs(out[0, 0, 0, 1] - (3.0 + (2 * math.pi - 6.0) / 2)) < 1e-5
    assert not fl.any()


def test_caltable_frequency_bridging_of_flagged_channels():
    fin = np.array([1.0, 2.0, 3.0, 4.0]) * 1e9
    vals = np.zeros((4, 1, 2), np.float32)
    vals[:, 0, 0] = [1.0, 9.0, 3.0, 4.0]
    flags = np.array([[False], [True], [False], [False]])
    out, oflag = caltable._resample_freq(vals, flags, fin, fin, True)
    assert not oflag.any()
    assert out[1, 0, 0] == pytest.approx(2.0)  # bridged between channels 0 and 2


def test_quartical_store_round_trip(tmp_path):
    rng = np.random.default_rng(2)
    g = rng.standard_normal((3, 2, 4, 1, 2, 2)) + 1j * rng.standard_normal(
        (3, 2, 4, 1, 2, 2)
    )
    part = quartical_store.complex_partition(
        g,
        np.zeros((3, 2, 4, 1), bool),
        [1.0, 2.0, 3.0],
        [1e9, 2e9],
        ["a", "b", "c", "d"],
        field_name="F",
    )
    quartical_store.write({"G": [part]}, tmp_path / "s.qc")
    back = quartical_store.read(tmp_path / "s.qc")["G"][0]
    assert back.type == "complex" and back.attrs["FIELD_NAME"] == "F"
    assert np.array_equal(back["gains"], part["gains"])
    assert np.array_equal(back.gains_2x2(), g)
    assert [str(a) for a in back["antenna"]] == ["a", "b", "c", "d"]
    meta = json.loads((tmp_path / "s.qc" / "G" / "G_0" / ".zmetadata").read_text())
    assert meta["zarr_consolidated_format"] == 1 and "gains/.zarray" in meta["metadata"]


def test_blosc_memcpyed_frame_layout():
    data = bytes(range(64))
    frame = quartical_store.blosc_frame(data, 8, {"cname": "lz4", "shuffle": 1})
    assert frame[2] & 0x02 and len(frame) == 64 + 16
    assert frame[16:] == data


def lsm_sources():
    return sky.loads(
        "#format: name ra_h ra_m ra_s dec_d dec_m dec_s i emaj_s emin_s pa_d freq0 spi spi2\n"
        "A0 19 39 25.03 -63 42 45.7 15.0 0.0 0.0 0.0 1300000000.0 -0.1 -0.6\n"
        "G1 19 37 32.09 -63 35 59.49 0.01 12.0 4.0 54.0 1300000000.0 -3.1 0.0\n"
    )


def test_sky_html_ascii_and_wsclean_round_trips():
    src = lsm_sources()
    html = sky.loads_html(sky.dumps_html(src, freq0=1.3e9))
    assert html.freq0 == 1.3e9
    for a, b in zip(src, html.sources):
        assert (a.name, a.ra, a.dec, a.i, a.spi, a.emaj, a.emin, a.pa) == (
            b.name,
            b.ra,
            b.dec,
            b.i,
            b.spi,
            b.emaj,
            b.emin,
            b.pa,
        )
    ascii_back = sky.loads(sky.dumps_ascii(src))
    assert [(s.ra, s.dec, s.spi, s.emaj) for s in ascii_back] == [
        (s.ra, s.dec, s.spi, s.emaj) for s in src
    ]
    ws = sky.loads_wsclean(sky.dumps_wsclean(src))
    for a, b in zip(src, ws):
        assert abs(a.ra - b.ra) < 1e-12 and abs(a.dec - b.dec) < 1e-12
        assert a.spi == b.spi and a.log_si and b.log_si
        assert b.emaj == pytest.approx(a.emaj, rel=1e-15)


def test_tigger_html_parser_never_evaluates():
    text = (
        "<HTML><BODY mdltype=SkyModel>"
        "<TR mdltype=Source ><TD mdltype=str mdlval=\"__import__('os')\"></TD></TR></BODY></HTML>"
    )
    with pytest.raises(ValueError):
        sky.loads_html(text)


def test_bbs_reader_units_and_patches():
    text = (
        "FORMAT = Name, Type, Patch, Ra, Dec, I, ReferenceFrequency='1e9', SpectralIndex='[]', "
        "MajorAxis, MinorAxis, Orientation\n"
        " , , P1, 19:39:25.0, -63.42.45.7\n"
        "s1, GAUSSIAN, P1, 19:39:25.0, -63.42.45.7, 2.0, , [-0.7, 0.1], 36.0, 18.0, 90.0\n"
    )
    (s,) = sky.loads_bbs(text)
    assert s.name == "P1:s1" and s.i == 2.0 and s.spi == (-0.7, 0.1) and s.freq0 == 1e9
    assert s.emaj == pytest.approx(math.radians(0.01)) and s.pa == pytest.approx(
        math.pi / 2
    )
    assert s.ra == pytest.approx(math.radians((19 + 39 / 60 + 25 / 3600) * 15))


def test_restricted_unpickler(tmp_path):
    good = {"Type": "HMP", "Comp": {(1, 2): np.arange(3.0)}, "RefFreq": np.float64(1e9)}
    p = tmp_path / "m.DicoModel"
    p.write_bytes(pickle.dumps(good, protocol=4))  # as DDFacet writes it
    d = sky.load_dicomodel(p)
    assert d["Type"] == "HMP" and np.array_equal(d["Comp"][(1, 2)], np.arange(3.0))
    with pytest.raises(pickle.UnpicklingError):
        sky.restricted_load(io.BytesIO(b"cos\nsystem\n(S'echo x'\ntR."))


def test_clustercat_is_np_save(tmp_path):
    cat = sky.clustercat_from_sources(lsm_sources(), (5.146, -1.112))
    sky.write_clustercat(tmp_path / "a.npy", cat)
    np.save(tmp_path / "b.npy", cat)
    assert (tmp_path / "a.npy").read_bytes() == (tmp_path / "b.npy").read_bytes()
    assert np.array_equal(sky.read_clustercat(tmp_path / "a.npy"), cat)


def test_killms_files_need_no_pickle_and_merge(tmp_path):
    rng = np.random.default_rng(3)
    names = ["m000", "m001", "m002"]
    cat = np.zeros(1, sky.CLUSTERCAT_DTYPE)
    files = []
    for half in range(2):
        g = (np.eye(2) + 0.1 * rng.standard_normal((2, 1, 3, 1, 2, 2))).astype(
            np.complex64
        )
        dom = np.array([[1e9 + half * 2**20, 1e9 + (half + 1) * 2**20]])
        path = tmp_path / f"h{half}.npz"
        killms.write(
            path,
            killms.make_sols([0.0, 1.0], [1.0, 2.0], g),
            names,
            cat,
            dom,
            beam_times=[0.0, 2.0],
        )
        with np.load(path, allow_pickle=False) as z:
            assert z["Sols"]["G"].shape == (2, 1, 3, 1, 2, 2)
        files.append(killms.read(path))
    merged = killms.merge(files)
    assert merged["Sols"].G.shape == (2, 2, 3, 1, 2, 2)
    assert not merged["MaskedSols"].any()
    # Antenna 0 is rotated to a positive-definite Hermitian matrix.
    g0 = merged["Sols"].G[0, 0, 0, 0]
    assert np.allclose(g0, g0.conj().T, atol=1e-6)


def test_h5parm_round_trip(tmp_path):
    pytest.importorskip("h5py")
    from rang.formats import h5parm

    rng = np.random.default_rng(4)
    amp = 1 + 0.1 * rng.random((2, 3, 2, 1, 2))
    ph = rng.uniform(-3, 3, (2, 3, 2, 1, 2))
    ss = h5parm.diagonal_solset(
        None, [1.0, 2.0], [1e9, 2e9, 3e9], ["m000", "m001"], amplitude=amp, phase=ph
    )
    h5parm.write(tmp_path / "s.h5", {"sol000": ss})
    back = h5parm.read(tmp_path / "s.h5")["sol000"]
    assert back.soltabs["amplitude000"].type == "amplitude"
    assert np.array_equal(back.soltabs["amplitude000"].val, amp)
    assert np.array_equal(back.soltabs["phase000"].val, ph)
    assert list(back.soltabs["phase000"].axis_values["ant"]) == ["m000", "m001"]
    assert [a[0] for a in back.antennas] == ["m000", "m001"]
    import h5py

    with h5py.File(tmp_path / "s.h5") as f:
        assert (
            f["sol000/amplitude000/ant"].id.get_type().get_strpad()
            == h5py.h5t.STR_NULLTERM
        )


@writer
def test_flag_version_written_and_read(tmp_path):
    ms = tmp_path / "x.ms"
    ms.mkdir()
    rng = np.random.default_rng(5)
    flag = rng.random((6, 8, 4)) < 0.5
    row = np.array([True, False, False, True, False, False])
    flagversions.save(ms, "v1", "a comment", flag, row)
    f, r = flagversions.load(ms, "v1")
    assert np.array_equal(f, flag) and np.array_equal(r, row)
    assert flagversions.versions(ms) == [("v1", "a comment")]
    with pytest.raises(ValueError):
        flagversions.save(ms, "v1", "", flag, row)


def test_cli_detects_and_converts_sky(tmp_path):
    p = tmp_path / "m.lsm.html"
    p.write_text(sky.dumps_html(lsm_sources()))
    assert cli.detect(p) == "tigger-html"
    out = cli.convert(p, tmp_path / "m.wsclean")
    assert out["to"] == "wsclean" and out["sources"] == 2
    assert cli.summary(tmp_path / "m.wsclean")["components"] == 2


def test_lsm_shim_reexports_everything():
    from rang import lsm

    for name in lsm.__all__:
        assert getattr(lsm, name) is getattr(sky, name)


def test_archived_verdicts():
    path = ROOT / "research" / "results" / "dfio-formats.json"
    if not path.exists():
        pytest.skip("no DF-IO archive")
    r = json.loads(path.read_text())
    table = {(row["format"], row["direction"]): row for row in r["table"]}
    assert table[("CASA caltable", "read")]["verdict"] == "pass"
    assert table[("QuartiCal store", "write")]["verdict"] == "pass"
    assert table[("killMS solutions", "write")]["verdict"] == "pass"
    assert all(
        row["verdict"] in ("pass", "fail", "pass post hoc", "open")
        for row in r["table"]
    )
