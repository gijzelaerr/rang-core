"""MK1: the MVFv4 loader's conventions on a synthetic archive (research/mk1-katdal.md).

The archive is written with katdal's own chunk store and telstate writers
(`rang.meerkat.write_synthetic_mvf`); no public MVF archive exists. The
katdal tests skip without the `[meerkat]` extra; the mvftoms comparison also
needs python-casacore and pkg_resources (setuptools<81).
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from rang import meerkat


def test_import_without_katdal_and_flag_masks():
    assert "katdal" not in meerkat.__dict__
    assert meerkat.flag_mask("all") == 255
    assert meerkat.flag_mask(["cal_rfi"]) == 64
    assert meerkat.flag_mask("static,data_lost") == 0b1010
    assert meerkat.flag_mask([]) == 0
    with pytest.raises(ValueError):
        meerkat.flag_mask(["nonsense"])
    a1, a2 = meerkat.baselines(4)
    assert list(zip(a1, a2)) == [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    a1, a2 = meerkat.baselines(3, autos=True)
    assert list(zip(a1, a2)) == [(0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2)]


def test_to_rows_maps_and_fills_missing():
    products = [("m001h", "m000h"), ("m000h", "m001h"), ("m000v", "m001v")]
    a1, a2 = meerkat.baselines(2)
    cp = meerkat.corrprod_index(products, ["m000", "m001"], a1, a2)
    assert cp.tolist() == [[1, -1, -1, 2]]
    array = np.arange(2 * 3 * 3, dtype=np.float32).reshape(2, 3, 3)
    rows = meerkat.to_rows(array, cp, 0)
    assert rows.shape == (2, 3, 4)
    assert np.array_equal(rows[:, :, 0], array[:, :, 1])
    assert np.array_equal(rows[:, :, 3], array[:, :, 2])
    assert not rows[:, :, 1:3].any()


@pytest.fixture(scope="module")
def archive(tmp_path_factory):
    pytest.importorskip("katdal", reason="needs the [meerkat] extra")
    root = tmp_path_factory.mktemp("mvf")
    return meerkat.write_synthetic_mvf(
        root, n_ants=4, n_dumps=12, n_chans=24, dump_chunk=4, chan_chunk=8
    )


def _expected(fixture, dumps, names, bits):
    """Rows by name lookup from the stored arrays (no katdal DataSet)."""
    where = {p: k for k, p in enumerate(fixture["bls_ordering"])}
    pairs = [(i, j) for i in range(len(names)) for j in range(i + 1, len(names))]
    index = np.array(
        [
            [where[(names[i] + p[0], names[j] + p[1])] for p in meerkat.POLS]
            for i, j in pairs
        ]
    )
    sub = bits[dumps][:, :, index]
    return np.ascontiguousarray(sub.transpose(0, 2, 1, 3)).reshape(-1, bits.shape[1], 4)


def _track_dumps(loader):
    ds = loader.dataset
    return np.concatenate(
        [ds.dumps.copy() for _, state, _ in ds.scans() if state in meerkat.TRACK_STATES]
    )


def test_native_bits_vis_and_weights(archive):
    loader = meerkat.open_mvf(archive["rdb"], upgrade_flags=False)
    got = loader.read()
    dumps = _track_dumps(loader)
    names = [f"m{n:03d}" for n in range(4)]
    stored = archive["arrays"]
    lost = np.zeros(stored["flags"].shape, bool)
    d0, d1 = archive["dropped"]["dumps"]
    c0, c1 = archive["dropped"]["channels"]
    lost[d0:d1, c0:c1] = True
    l0 = stored["flags"] | (lost * np.uint8(8))
    assert np.array_equal(got["FLAG_BITS"], _expected(archive, dumps, names, l0))
    vis = np.where(lost, 0, stored["correlator_data"]).astype(np.complex64)
    assert np.array_equal(got["DATA"], _expected(archive, dumps, names, vis))
    assert np.array_equal(got["FLAG"], got["FLAG_BITS"] != 0)
    # Weights: stored × weights_channel, divided by both autocorrelation powers.
    bls = archive["bls_ordering"]
    where = {p: k for k, p in enumerate(bls)}
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        recip = np.reciprocal(vis.real)
        scale = (
            recip[:, :, [where[(x, x)] for x, _ in bls]]
            * recip[:, :, [where[(y, y)] for _, y in bls]]
        )
    scale[~np.isfinite(scale)] = np.float32(2.0**-32)
    weights = scale * (stored["weights"] * stored["weights_channel"][..., None])
    assert np.array_equal(
        got["WEIGHT_SPECTRUM"], _expected(archive, dumps, names, weights)
    )
    assert got["TIME"].dtype == np.float64 and not got["FLAG_ROW"].any()
    assert got["SCAN_NUMBER"].min() == 1 and got["SCAN_NUMBER"].max() == 2


def test_upgraded_bits_and_per_bit_selection(archive):
    loader = meerkat.open_mvf(archive["rdb"])
    got = loader.read()
    dumps = _track_dumps(loader)
    names = [f"m{n:03d}" for n in range(4)]
    lost = np.zeros(archive["l1_flags"].shape, bool)
    d0, d1 = archive["dropped"]["dumps"]
    c0, c1 = archive["dropped"]["channels"]
    lost[d0:d1, c0:c1] = True
    l1 = archive["l1_flags"] | (lost * np.uint8(8))
    assert np.array_equal(got["FLAG_BITS"], _expected(archive, dumps, names, l1))
    for bit, name in enumerate(meerkat.FLAG_NAMES):
        loader.select(flags=[name])
        chunk = loader.read()
        assert np.array_equal(
            chunk["FLAG"], ((chunk["FLAG_BITS"] >> bit) & 1).astype(bool)
        )


def test_matches_katdal_arrays_under_selection(archive):
    loader = meerkat.open_mvf(archive["rdb"])
    loader.select(scans=[3], antennas=["m000", "m002", "m003"], channels=slice(3, 20))
    got = loader.read()
    ds = loader.dataset
    names = [a.name for a in ds.ants]
    a1, a2 = meerkat.baselines(len(names))
    cp = meerkat.corrprod_index(ds.corr_products, names, a1, a2)
    assert names == ["m000", "m002", "m003"]
    assert np.array_equal(got["DATA"], meerkat.to_rows(ds.vis[:], cp, 0))
    assert np.array_equal(got["WEIGHT_SPECTRUM"], meerkat.to_rows(ds.weights[:], cp, 0))
    assert np.array_equal(got["FLAG_BITS"], meerkat.to_rows(ds.raw_flags[:], cp, 0))
    uvw = np.stack([ds.u[:], ds.v[:], ds.w[:]], axis=-1)[:, cp[:, 0]].reshape(-1, 3)
    assert np.max(np.abs(got["UVW"] - uvw)) < 1e-6
    assert got["DATA"].shape == (len(ds.dumps) * 3, 17, 4)


def test_iter_chunks_follow_store_chunks_and_save(archive, tmp_path):
    loader = meerkat.open_mvf(archive["rdb"])
    chunks = list(loader.iter_chunks())
    nbl = 6
    dumps = [c["_stats"]["dumps"] for c in chunks]
    # Chunks never span a scan and split at the store's 4-dump boundaries.
    assert all(c["DATA"].shape[0] == (d[1] - d[0]) * nbl for c, d in zip(chunks, dumps))
    whole = loader.read()
    assert np.array_equal(np.concatenate([c["DATA"] for c in chunks]), whole["DATA"])
    manifest = loader.save_chunks(tmp_path / "saved")
    assert len(manifest["chunks"]) == len(chunks)
    first = meerkat.load_saved_chunk(tmp_path / "saved" / manifest["chunks"][0]["path"])
    for key in (
        "ANTENNA1",
        "ANTENNA2",
        "TIME",
        "UVW",
        "DATA",
        "FLAG",
        "WEIGHT_SPECTRUM",
    ):
        assert np.array_equal(first[key], chunks[0][key])
    assert manifest["metadata"]["corr_types"] == [9, 10, 11, 12]


@pytest.mark.skipif(
    importlib.util.find_spec("casacore") is None
    or importlib.util.find_spec("pkg_resources") is None,
    reason="mvftoms needs python-casacore and pkg_resources",
)
def test_mvftoms_ms_matches_loader(archive, tmp_path):
    from rang import core_ms

    mvftoms = Path(sys.executable).parent / "mvftoms.py"
    if not mvftoms.is_file() or not core_ms.has_reader():
        pytest.skip("mvftoms.py or the core MS reader is missing")
    ms = tmp_path / "x.ms"
    subprocess.run(
        [
            sys.executable,
            str(mvftoms),
            "-f",
            "--quack",
            "0",
            "-o",
            str(ms),
            archive["rdb"],
        ],
        check=True,
        capture_output=True,
    )
    loader = meerkat.open_mvf(archive["rdb"]).select(autos=True)
    got = loader.read()
    with core_ms.open_table(ms) as table:
        cols = {
            n: table.getcol(n)
            for n in (
                "TIME",
                "ANTENNA1",
                "ANTENNA2",
                "DATA",
                "FLAG",
                "WEIGHT_SPECTRUM",
                "UVW",
            )
        }
    keys = {
        k: n
        for n, k in enumerate(zip(cols["TIME"], cols["ANTENNA1"], cols["ANTENNA2"]))
    }
    order = [keys[k] for k in zip(got["TIME"], got["ANTENNA1"], got["ANTENNA2"])]
    assert len(order) == len(cols["TIME"]) == len(set(order))
    for name, column in cols.items():
        assert np.array_equal(got[name], column[order]), name


def test_public_source_drops_the_token():
    url = "https://archive-gw-1.kat.ac.za/1/1_sdp_l0.full.rdb?token=secret#x"
    assert (
        meerkat.public_source(url)
        == "https://archive-gw-1.kat.ac.za/1/1_sdp_l0.full.rdb"
    )
    assert meerkat.public_source("/data/1/1_sdp_l0.rdb") == "/data/1/1_sdp_l0.rdb"
