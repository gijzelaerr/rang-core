# SPDX-License-Identifier: MIT
"""`rang.msv4`, the MSv4 processing-set reader (research/msv4-interop.md).

The synthetic store below is written by this test with xarray, so it checks
the reader's own consistency (layout, pads, refusals), not the schema as
xradio writes it. `tests/data/msv4/m05.zip` holds an xradio 1.3.1 store and
the MSv2 it was converted from (the edge-case set's two-window MS); that
test compares the reader with ra-ng's MSv2 reader bit for bit, as the note's
oracle does. Everything skips without the `[msv4]` extra.
"""

import zipfile
from pathlib import Path

import numpy as np
import pytest
from rang import msv4

pytestmark = pytest.mark.skipif(
    not msv4.has_msv4(), reason="the [msv4] extra is absent"
)

DATA = Path(__file__).resolve().parent / "data" / "msv4"


def _tree(
    schema="4.0.1", kind="visibility", vis_dtype="complex64", pad=True, flag=None
):
    import xarray as xr

    rng = np.random.default_rng(7)
    ntime, nbl, nchan, ncorr = 3, 3, 5, 2
    shape = (ntime, nbl, nchan, ncorr)
    vis = (rng.normal(size=shape) + 1j * rng.normal(size=shape)).astype(vis_dtype)
    flag_bool = rng.random(shape) > 0.7
    flag_store = flag_bool if flag is None else flag(flag_bool)
    weight = rng.random(shape).astype("float32")
    uvw = rng.normal(size=(ntime, nbl, 3))
    if pad:
        vis[1, 2] = np.nan
        uvw[1, 2] = np.nan
        weight[1, 2] = np.nan
        vis[2, 0, 0, 0] = np.nan  # a NaN sample in a real row stays a row
    grid = ("time", "baseline_id", "frequency", "polarization")
    ds = xr.Dataset(
        {
            "VISIBILITY": (grid, vis),
            "FLAG": (grid, flag_store),
            "WEIGHT": (grid, weight),
            "UVW": (("time", "baseline_id", "uvw_label"), uvw),
        },
        coords={
            "time": 1.6e9 + 8.0 * np.arange(ntime),
            "baseline_id": np.arange(nbl),
            "baseline_antenna1_name": ("baseline_id", ["a0", "a0", "a1"]),
            "baseline_antenna2_name": ("baseline_id", ["a1", "a2", "a2"]),
            "frequency": 1e9 + 1e6 * np.arange(nchan),
            "polarization": ["XX", "YY"],
            "uvw_label": ["u", "v", "w"],
            "field_name": ("time", ["f", "f", "g"]),
            "scan_name": ("time", ["1", "1", "2"]),
        },
        attrs={
            "schema_version": schema,
            "type": kind,
            "data_groups": {
                "base": {
                    "correlated_data": "VISIBILITY",
                    "flag": "FLAG",
                    "weight": "WEIGHT",
                    "uvw": "UVW",
                }
            },
        },
    )
    ant = xr.Dataset(coords={"antenna_name": ["a0", "a1", "a2"]})
    tree = xr.DataTree.from_dict({"/p0": ds, "/p0/antenna_xds": ant})
    return tree, (vis, flag_bool, weight, uvw)


def test_rows_layout_and_pads(tmp_path):
    tree, (vis, flag, weight, uvw) = _tree()
    path = tmp_path / "ps.zarr"
    tree.to_zarr(str(path))
    ps = msv4.open_processing_set(path)
    assert ps.names == ["p0"] and ps.refused == {}
    part = ps.partition("p0")
    rows = part.rows()
    keep = np.ones(9, bool)
    keep[1 * 3 + 2] = False
    assert rows["PADS"] == 1 and len(rows["TIME"]) == 8
    assert rows["DATA"].dtype == np.complex64 and rows["DATA"].shape == (8, 5, 2)
    assert rows["DATA"].tobytes() == vis.reshape(9, 5, 2)[keep].tobytes()
    assert rows["FLAG"].tobytes() == flag.reshape(9, 5, 2)[keep].tobytes()
    assert rows["WEIGHT_SPECTRUM"].tobytes() == weight.reshape(9, 5, 2)[keep].tobytes()
    assert rows["UVW"].tobytes() == uvw.reshape(9, 3)[keep].tobytes()
    assert rows["ANTENNA1"].dtype == np.int32
    assert list(rows["ANTENNA1"]) == [0, 0, 1, 0, 0, 0, 0, 1]
    assert list(rows["ANTENNA2"]) == [1, 2, 2, 1, 2, 1, 2, 2]
    t = 1.6e9 + 8.0 * np.arange(3) + msv4.UNIX_TO_MJD_SECONDS
    assert rows["TIME"].tobytes() == np.repeat(t, 3)[keep].tobytes()
    assert list(rows["FIELD_NAME"]) == ["f"] * 5 + ["g"] * 3
    assert not rows["FLAG_ROW"].any()
    # chunks by time give the same rows
    pieces = list(part.chunks(time_rows=2))
    assert len(pieces) == 2
    assert (
        np.concatenate([p["DATA"] for p in pieces]).tobytes() == rows["DATA"].tobytes()
    )


def test_opened_tree_is_accepted():
    tree, _ = _tree(pad=False)
    rows = msv4.open_processing_set(tree).partition("p0").rows()
    assert rows["PADS"] == 0 and len(rows["TIME"]) == 9


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"schema": "5.0.0"}, "schema_version"),
        ({"kind": "spectrum"}, "not visibility"),
    ],
)
def test_partition_refusals(kwargs, message):
    tree, _ = _tree(**kwargs)
    ps = msv4.open_processing_set(tree)
    assert ps.names == [] and message in ps.refused["p0"]
    with pytest.raises(ValueError, match=message):
        ps.partition("p0")


def test_dtype_refusal():
    tree, _ = _tree(vis_dtype="complex128")
    with pytest.raises(ValueError, match="complex128"):
        msv4.open_processing_set(tree).partition("p0")


def test_xradio_store_equals_msv2(tmp_path):
    """The note's oracle on one case: an xradio 1.3.1 store against the MSv2
    it came from, read by ra-ng's MSv2 reader, bit for bit."""
    from rang import core_ms

    if not core_ms.has_reader():
        pytest.skip("core library built without the reader")
    with zipfile.ZipFile(DATA / "m05.zip") as z:
        z.extractall(tmp_path)
    ms = tmp_path / "m05.ms"
    ps = msv4.open_processing_set(tmp_path / "m05.ps.zarr")
    with core_ms.open_table(ms) as t:
        ref = {c: t.getcol(c) for c in ("TIME", "ANTENNA1", "ANTENNA2", "DATA_DESC_ID")}
        ref.update({c: t.getcol_rows(c, np.arange(t.nrows)) for c in ("UVW",)})
        cells = {
            c: [t.getcol(c, r, 1)[0] for r in range(t.nrows)]
            for c in ("DATA", "FLAG", "WEIGHT_SPECTRUM")
        }
    with core_ms.open_table(ms / "ANTENNA") as t:
        names = [str(n) for n in t.getcol("NAME")]
    with core_ms.open_table(ms / "DATA_DESCRIPTION") as t:
        dd_spw = t.getcol("SPECTRAL_WINDOW_ID")
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freqs = [t.getcol("CHAN_FREQ", r, 1)[0] for r in range(t.nrows)]
    seen = 0
    assert len(ps.names) == 2
    for part in ps.partitions():
        rows = part.rows()
        (ddid,) = [
            d for d, s in enumerate(dd_spw) if np.array_equal(freqs[s], part.frequency)
        ]
        key = {
            (rows["TIME"][i], part.antenna_names[a], part.antenna_names[b]): i
            for i, (a, b) in enumerate(zip(rows["ANTENNA1"], rows["ANTENNA2"]))
        }
        for r in np.flatnonzero(ref["DATA_DESC_ID"] == ddid):
            i = key[
                (ref["TIME"][r], names[ref["ANTENNA1"][r]], names[ref["ANTENNA2"][r]])
            ]
            for c in ("DATA", "FLAG", "WEIGHT_SPECTRUM"):
                assert rows[c][i].dtype == cells[c][r].dtype
                assert rows[c][i].tobytes() == cells[c][r].tobytes()
            assert rows["UVW"][i].tobytes() == ref["UVW"][r].tobytes()
            seen += 1
        assert len(rows["TIME"]) == int(np.sum(ref["DATA_DESC_ID"] == ddid))
    assert seen == len(ref["TIME"])


def _uint8(flag):
    out = flag.astype(np.uint8)
    out[1, 2] = 1  # xarray-ms pads FLAG with 1
    return out


def test_uint8_flag_of_0_and_1_reads_as_bool(tmp_path):
    """Section 9: xarray-ms writes FLAG as uint8; 0 and 1 read as bool."""
    tree, (_, flag, _, _) = _tree(flag=_uint8)
    path = tmp_path / "ps.zarr"
    tree.to_zarr(str(path))
    part = msv4.open_processing_set(path).partition("p0")
    assert part.ds["FLAG"].dtype == np.uint8
    rows = part.rows()
    keep = np.ones(9, bool)
    keep[1 * 3 + 2] = False
    assert rows["PADS"] == 1
    assert rows["FLAG"].dtype == np.bool_
    assert rows["FLAG"].tobytes() == flag.reshape(9, 5, 2)[keep].tobytes()
    reference = msv4.open_processing_set(_tree()[0]).partition("p0").rows()
    assert rows["FLAG"].tobytes() == reference["FLAG"].tobytes()


def test_uint8_flag_other_value_is_refused():
    def two(flag):
        out = flag.astype(np.uint8)
        out[2, 1, 3, 0] = 2
        return out

    tree, _ = _tree(flag=two)
    part = msv4.open_processing_set(tree).partition("p0")  # opening reads no value
    assert next(part.chunks(time_rows=2))["PADS"] == 1  # times 0, 1 are clean
    with pytest.raises(ValueError, match=r"uint8 with values \[2\]"):
        part.rows()


def test_other_flag_dtype_is_refused():
    tree, _ = _tree(flag=lambda f: f.astype(np.int8))
    with pytest.raises(ValueError, match="int8, not bool or uint8"):
        msv4.open_processing_set(tree).partition("p0")


def test_missing_extra_names_it(monkeypatch, tmp_path):
    """research/v030-review.md B-19: without the extra, opening a store says
    which extra to install instead of a bare ModuleNotFoundError."""
    monkeypatch.setattr(msv4, "has_msv4", lambda: False)
    with pytest.raises(ImportError, match=r"rang-core\[msv4\]"):
        msv4.open_processing_set(tmp_path / "x.ps.zarr")
