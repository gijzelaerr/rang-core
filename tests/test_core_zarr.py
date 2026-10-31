import json

import numpy as np
import pytest
from rang import core, core_zarr


def _memcpyed_chunk(payload, blocksize):
    header = bytes([2, 1, 0x02, 4])
    header += len(payload).to_bytes(4, "little")
    header += blocksize.to_bytes(4, "little")
    header += (16 + len(payload)).to_bytes(4, "little")
    return header + payload


def test_read_rows_and_full_decode_of_memcpyed_chunk(tmp_path):
    values = np.arange(60, dtype="<i4").reshape(20, 3)
    chunk = _memcpyed_chunk(values.tobytes(), blocksize=48)
    path = tmp_path / "0"
    path.write_bytes(chunk)
    assert core_zarr.read_chunk(path) == values.tobytes()
    raw, stats = core_zarr.read_rows(path, 12, [1, 7, 19])
    np.testing.assert_array_equal(
        np.frombuffer(raw, "<i4").reshape(3, 3), values[[1, 7, 19]]
    )
    assert stats["blocks_decoded"] < stats["blocks_total"]
    raw, _ = core.blosc_decode_rows(chunk, 12, [0, 19])
    np.testing.assert_array_equal(
        np.frombuffer(raw, "<i4").reshape(2, 3), values[[0, 19]]
    )


def test_rejects_unsorted_rows(tmp_path):
    path = tmp_path / "0"
    path.write_bytes(_memcpyed_chunk(bytes(48), blocksize=48))
    try:
        core_zarr.read_rows(path, 12, [2, 1])
    except ValueError:
        return
    raise AssertionError("unsorted rows must be refused")


def reordered_chunk(payload, blocksize):
    """A blosc chunk whose raw (uncompressed-stream) blocks are stored in
    reverse order, as multithreaded blosc may write them (flags: LZ4, no
    split; typesize 1; each block a 4-byte stream length and its bytes)."""
    blocks = [payload[k : k + blocksize] for k in range(0, len(payload), blocksize)]
    table = 16 + 4 * len(blocks)
    starts, body = [0] * len(blocks), b""
    for j in reversed(range(len(blocks))):
        starts[j] = table + len(body)
        body += len(blocks[j]).to_bytes(4, "little") + blocks[j]
    head = bytes([2, 1, 0x30, 1])
    head += len(payload).to_bytes(4, "little") + blocksize.to_bytes(4, "little")
    head += (table + len(body)).to_bytes(4, "little")
    return head + b"".join(s.to_bytes(4, "little") for s in starts) + body


def test_blocks_stored_out_of_order_fall_back_to_a_whole_decode(tmp_path):
    values = np.arange(240, dtype="<i4").reshape(20, 12)
    chunk = reordered_chunk(values.tobytes(), 96)
    path = tmp_path / "0"
    path.write_bytes(chunk)
    assert core_zarr.read_chunk(path) == values.tobytes()
    starts, _, _, nblocks = core_zarr.block_table(chunk[:4112])
    assert nblocks == 10 and not core_zarr.blocks_in_order(starts)
    raw, stats = core_zarr.read_rows(path, 48, [1, 7, 19])
    np.testing.assert_array_equal(
        np.frombuffer(raw, "<i4").reshape(3, 12), values[[1, 7, 19]]
    )
    assert stats["blocks_decoded"] == stats["blocks_total"] == 10


def test_span_rows_outside_the_decoded_blocks_are_refused():
    """W4-2 (W4R-10): rows outside blocks `first..first + count` were left
    as the output's previous bytes with status 0."""
    payload = bytes(range(40))
    chunk = bytes([2, 1, 0x02, 1]) + (40).to_bytes(4, "little")
    chunk += (8).to_bytes(4, "little") + (56).to_bytes(4, "little") + payload
    head, span = chunk[:16], chunk[24:40]  # blocks 1 and 2: rows 2 to 5
    out = np.zeros(8, np.uint8)
    rows = np.array([2, 5], np.uintp)
    assert core_zarr.decode_span_rows(head, 1, 2, span, 4, rows, out) == 0
    assert out.tolist() == [8, 9, 10, 11, 20, 21, 22, 23]
    ext = core.extension()
    for bad in ([0, 2], [2, 6], [5, 2]):
        bad = np.array(bad, np.uintp)
        assert ext.blosc_decode_span_rows(head, 1, 2, span, 4, bad, out) == 1
        strided = np.frombuffer(span, np.uint8)
        assert (
            ext.blosc_decode_span_rows_strided(head, 1, 2, strided, 4, bad, out, 0, 4)
            == 1
        )
        with pytest.raises(ValueError, match="outside"):
            core_zarr.decode_span_rows(head, 1, 2, span, 4, bad, out)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"order": "F"}, "C-ordered"),
        ({"order": None}, "C-ordered"),
        ({"dtype": ">i4"}, "big-endian"),
        ({"filters": [{"id": "delta"}]}, "filtered"),
        ({"compressor": {"id": "zstd"}}, "blosc"),
    ],
)
def test_array_meta_refuses_what_would_decode_wrongly(tmp_path, change, match):
    """W4-2 (W4R-09): a Fortran-ordered or big-endian store would decode
    transposed or byte-swapped without an error."""
    meta = {
        "chunks": [4, 3],
        "compressor": {"id": "blosc"},
        "dtype": "<i4",
        "filters": None,
        "order": "C",
        "shape": [4, 3],
        "zarr_format": 2,
    }
    (tmp_path / ".zarray").write_text(json.dumps(meta), encoding="utf-8")
    assert core_zarr.array_meta(tmp_path)["dtype"] == "<i4"
    with pytest.raises(ValueError, match="expected <f8"):
        core_zarr.array_meta(tmp_path, dtype="<f8")
    (tmp_path / ".zarray").write_text(json.dumps({**meta, **change}), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        core_zarr.array_meta(tmp_path)
