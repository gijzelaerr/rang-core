"""Offline tests of the range-request fetcher against a local HTTP server."""

import hashlib
import http.server
import json
import threading
from typing import ClassVar

import numpy as np
import pytest
from rangtoy import core_fetch, core_zarr


def _memcpyed_chunk(payload, blocksize):
    header = bytes([2, 1, 0x02, 4])
    header += len(payload).to_bytes(4, "little")
    header += blocksize.to_bytes(4, "little")
    header += (16 + len(payload)).to_bytes(4, "little")
    return header + payload


def _zarray(shape, chunks, dtype):
    return json.dumps(
        {
            "chunks": list(chunks),
            "compressor": {"id": "blosc", "cname": "lz4", "clevel": 5, "shuffle": 1},
            "dtype": dtype,
            "fill_value": None,
            "filters": None,
            "order": "C",
            "shape": list(shape),
            "zarr_format": 2,
        }
    ).encode()


class _Store:
    """A synthetic MAIN_1 group: 12 rows, two tile columns, two tiles."""

    def __init__(self, nchan=4, ncorr=2):
        rng = np.random.default_rng(7)
        a1 = np.array([0, 0, 0, 1, 1, 2, 3, 0, 1, 2, 0, 5], "<i4")
        a2 = np.array([1, 2, 3, 2, 3, 3, 3, 1, 2, 3, 0, 6], "<i4")
        time_ = np.repeat([1.0, 2.0], 6).astype("<f8")
        flag_row = np.zeros(12, "|b1")
        flag_row[8] = True
        self.rows = {
            "ANTENNA1": a1,
            "ANTENNA2": a2,
            "TIME": time_,
            "FLAG_ROW": flag_row,
        }
        self.tiles = {
            "DATA": [
                (
                    rng.normal(size=(12, nchan, ncorr))
                    + 1j * rng.normal(size=(12, nchan, ncorr))
                ).astype("<c8")
                for _ in range(2)
            ],
            "FLAG": [rng.random((12, nchan, ncorr)) < 0.3 for _ in range(2)],
        }
        self.objects = {}
        g = "MAIN/MAIN_1"
        for name, values in self.rows.items():
            self.objects[f"{g}/{name}/.zarray"] = _zarray(
                (12,), (12,), values.dtype.str
            )
            self.objects[f"{g}/{name}/0"] = _memcpyed_chunk(values.tobytes(), 32)
        for name, parts in self.tiles.items():
            dtype = parts[0].dtype.str
            row_bytes = nchan * ncorr * parts[0].dtype.itemsize
            self.objects[f"{g}/{name}/.zarray"] = _zarray(
                (12, 2 * nchan, ncorr), (12, nchan, ncorr), dtype
            )
            for tile, values in enumerate(parts):
                # Two rows per block, so runs are visible.
                self.objects[f"{g}/{name}/0.{tile}.0"] = _memcpyed_chunk(
                    values.tobytes(), 2 * row_bytes
                )


class _Handler(http.server.BaseHTTPRequestHandler):
    store = None
    ignore_range_once = False
    requests: ClassVar[list] = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        key = self.path.lstrip("/")
        body = self.store.objects.get(key)
        type(self).requests.append((key, self.headers.get("Range")))
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        rng = self.headers.get("Range")
        if rng and type(self).ignore_range_once:
            type(self).ignore_range_once = False
            rng = None
        if rng:
            start, end = rng.removeprefix("bytes=").split("-")
            start, end = int(start), min(int(end), len(body) - 1)
            part = body[start : end + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(body)}")
            self.send_header("Content-Length", str(len(part)))
            self.send_header("ETag", '"test"')
            self.end_headers()
            self.wfile.write(part)
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


@pytest.fixture
def server():
    store = _Store()
    handler = type("Handler", (_Handler,), {"store": store, "requests": []})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield store, handler, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()


def test_plan_runs_matches_read_rows(tmp_path):
    values = np.arange(400, dtype="<i4").reshape(100, 4)
    chunk = _memcpyed_chunk(values.tobytes(), blocksize=64)
    path = tmp_path / "0"
    path.write_bytes(chunk)
    rows = [0, 1, 5, 6, 7, 40, 99]
    runs = core_fetch.plan_runs(chunk[: core_fetch.PREFIX], 16, rows)
    _, stats = core_zarr.read_rows(path, 16, rows)
    assert sum(count for _, count, _, _ in runs) == stats["blocks_decoded"]
    assert sum(end - start for _, _, start, end in runs) + 16 == stats["bytes_read"]
    assert [(r[0], r[1]) for r in runs] == [(0, 2), (10, 1), (24, 1)]
    with pytest.raises(ValueError):
        core_fetch.plan_runs(chunk, 16, [3, 2])


def test_fetch_slice_bytes_and_arrays_equal_the_store(server, tmp_path):
    store, _handler, url = server
    out = tmp_path / "fetched"
    columns = ("DATA", "FLAG")
    result = core_fetch.fetch_slice(
        url, "MAIN/MAIN_1", (0, 1, 2, 3), (0, 1), out, workers=3, tile_columns=columns
    )
    receipt = json.loads((out / "receipt.json").read_text())
    assert result["requests"] == len(receipt)
    # Every fetched span equals the same bytes of the stored object.
    for record in receipt:
        body = store.objects[record["key"]]
        if record["range"] is None:
            assert record["status"] == 200
            expected = body
        else:
            assert record["status"] == 206
            start, end = record["range"]
            expected = body[start:end]
        assert record["sha256"] == hashlib.sha256(expected).hexdigest()
    assert result["rows"] == [0, 1, 2, 3, 4, 5, 7, 9]  # no autos, row 8 flagged
    # Run spans are exactly the planned byte ranges (the toy tiles are smaller
    # than the head prefix, so the head GETs alone cover them whole).
    spans = sum(r["bytes"] for r in receipt if r["range"] and r["range"][0] != 0)
    planned = sum(
        end - start
        for plan in result["plans"].values()
        for *_, start, end in plan["runs"]
    )
    assert spans == planned > 0
    arrays, stats = core_fetch.decode_slice(out)
    rows = np.array(result["rows"])
    for name, values in store.rows.items():
        np.testing.assert_array_equal(arrays[name], values[rows])
    for name, parts in store.tiles.items():
        np.testing.assert_array_equal(arrays[name], np.concatenate(parts, axis=1)[rows])
    assert (
        stats["blocks_decoded"] == 2 * 2 * 5
    )  # rows 0-7 and 9 span 5 of 6 blocks per tile
    # The head request past a small object's end is clamped and recorded as served.
    heads = [r for r in receipt if r["range"] and r["range"][0] == 0]
    assert heads and all(r["range"][1] == len(store.objects[r["key"]]) for r in heads)
    with pytest.raises(FileExistsError):
        core_fetch.fetch_slice(
            url, "MAIN/MAIN_1", (0, 1, 2, 3), (0, 1), out, tile_columns=columns
        )


def test_ranged_get_retries_a_whole_object_response(server):
    _, handler, url = server
    handler.ignore_range_once = True
    client = core_fetch.Client(url, backoff=(0.0,))
    record, body = client.get("MAIN/MAIN_1/DATA/0.0.0", (0, 16))
    assert len(body) == 16 and record["status"] == 206
    assert [a["status"] for a in record["attempts"]] == [200, 206]
    assert "ranged request" in record["attempts"][0]["failure"]
    client.close()
