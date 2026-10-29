import numpy as np
from rangtoy import core, core_zarr


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
