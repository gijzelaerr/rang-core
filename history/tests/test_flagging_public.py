import json
import struct
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from rangtoy import flagging_public as public


def schema(dtype="<f4", shape=(12, 128, 4), chunks=(12, 128, 4)):
    return {
        "zarr_format": 2,
        "dtype": dtype,
        "shape": list(shape),
        "chunks": list(chunks),
        "order": "C",
        "filters": None,
        "compressor": {"id": "blosc"},
    }


@pytest.mark.parametrize(
    "change",
    [
        {"dtype": "|O"},
        {"filters": [{"id": "pickle", "protocol": 5}]},
        {"dtype": ">f4"},
        {"dtype": "<b16"},
        {"order": "F"},
        {"chunks": [0, 128, 4]},
        {"chunks": [13, 128, 4]},
        {"shape": [True, 128, 4]},
        {"compressor": None},
        {"compressor": {"id": "pickle"}},
        {"zarr_format": 3},
    ],
)
def test_numeric_schema_rejects_unsafe_or_invalid(change):
    candidate = schema()
    candidate.update(change)
    with pytest.raises(ValueError):
        public.numeric_schema(candidate)


def test_numeric_schema_budget():
    assert public.numeric_schema(schema()) == 12 * 128 * 4 * 4
    with pytest.raises(ValueError, match="budget"):
        public.numeric_schema(schema(shape=(100000000,), chunks=(100000000,)))


def test_object_plan_is_bounded_and_excludes_object_strings():
    metadata = {
        "MAIN/MAIN_0/DATA/.zarray": schema("<c8", (12, 4096, 4)),
        "MAIN/MAIN_0/CORRECTED_DATA/.zarray": schema("<c8", (12, 4096, 4)),
        "MAIN/MAIN_0/TIME/.zarray": schema("<f8", (12,), (12,)),
        "ANTENNA/ANTENNA_0/NAME/.zarray": schema("|O", (3,), (3,)),
        "OTHER/UNKNOWN/DATA/.zarray": schema(),
    }
    objects, rejected = public.object_plan(metadata, groups=(0,))
    assert [item["key"] for item in objects] == [
        "MAIN/MAIN_0/DATA/0.8.0",
        "MAIN/MAIN_0/TIME/0",
    ]
    assert rejected == ["ANTENNA/ANTENNA_0/NAME"]
    assert all(item["url"].startswith(public.BASE + "/") for item in objects)


@pytest.mark.parametrize(
    "groups,tile", [((), 8), ((2,), 8), ((0, 0), 8), ((True,), 8), ((0,), 9)]
)
def test_object_plan_rejects_unfrozen_scope(groups, tile):
    with pytest.raises(ValueError):
        public.object_plan({}, groups, tile)


def test_numeric_filtered_main_column_is_not_silently_skipped():
    candidate = schema("<c8", (12, 4096, 4))
    candidate["filters"] = [{"id": "pickle"}]
    with pytest.raises(ValueError):
        public.object_plan({"MAIN/MAIN_0/DATA/.zarray": candidate}, groups=(0,))


def row_grid():
    pairs = np.array([(a, b) for a in range(3) for b in range(a, 3)])
    return (
        np.repeat([1.0, 2.0, 3.0], 6),
        np.tile(pairs[:, 0], 3),
        np.tile(pairs[:, 1], 3),
    )


def test_complete_integrations_keeps_all_physical_pairs_and_skips_partial():
    times, p, q = row_grid()
    keep = np.ones(len(times), bool)
    keep[0] = False
    selected, centers = public.complete_integrations(
        times[keep], p[keep], q[keep], 3, 2
    )
    assert centers == [2.0, 3.0]
    assert selected.sum() == 12
    assert not selected[times[keep] == 1].any()


def test_complete_integrations_rejects_duplicates_and_bad_coordinates():
    times, p, q = row_grid()
    q[1] = q[0]
    with pytest.raises(ValueError, match="few complete"):
        public.complete_integrations(times, p, q, 3, 3)
    p[0] = 3
    with pytest.raises(ValueError, match="invalid"):
        public.complete_integrations(times, p, q, 3, 1)


def test_fresh_paths_rejects_nested_existing_and_dangling(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for output in (source, source / "nested", tmp_path):
        with pytest.raises(ValueError):
            public.fresh_paths(output, source)
    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError, match="symlink"):
        public.fresh_paths(dangling, source)
    assert public.fresh_paths(tmp_path / "fresh", source)[0].name == "fresh"


def test_disk_reserve_is_enforced(monkeypatch, tmp_path):
    monkeypatch.setattr(
        public.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=public.RESERVE_BYTES + 299),
    )
    with pytest.raises(ValueError, match="reserve"):
        public.check_disk(tmp_path / "not-yet-created", 100)
    public.check_disk(tmp_path, 99)


def test_exact_metadata_pin_before_network(tmp_path, monkeypatch):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"metadata": {}}))
    monkeypatch.setattr(
        public, "_request", lambda *args: pytest.fail("unexpected network")
    )
    with pytest.raises(ValueError, match="frozen source"):
        public.acquire(tmp_path / "fresh", path)
    assert not (tmp_path / "fresh").exists()


def test_plan_headers_cannot_rewrite_frozen_schema():
    expected = [{"key": "fixed", "schema": schema()}]
    recorded = [
        {**deepcopy(expected[0]), "compressed_bytes": 17, "etag": "quoted-etag"}
    ]
    assert public.expected_objects_with_headers(expected, recorded) == recorded
    recorded[0]["schema"]["dtype"] = "|O"
    assert public.expected_objects_with_headers(expected, recorded) != recorded
    with pytest.raises(ValueError):
        public.expected_objects_with_headers(expected, [])


def test_blosc_header_checked_before_decoder(monkeypatch):
    # A fake module avoids needing the pinned container codec in host tests.
    import sys

    decoder = SimpleNamespace(decompress=lambda _: pytest.fail("unexpected decoder"))
    monkeypatch.setitem(sys.modules, "numcodecs", SimpleNamespace(blosc=decoder))
    with pytest.raises(ValueError, match="truncated"):
        public.decode_numeric(b"tiny", schema())
    payload = b"\0" * 4 + struct.pack("<III", 1, 1, 16)
    with pytest.raises(ValueError, match="conflicts"):
        public.decode_numeric(payload, schema())
    with pytest.raises(ValueError, match="filter-free"):
        public.decode_numeric(payload, schema("|O"))


def test_numeric_decoder_readonly_exact_shape(monkeypatch):
    import sys

    values = np.arange(6, dtype="<f4").reshape(3, 2)
    payload = b"\0" * 4 + struct.pack("<III", values.nbytes, 1, 16)
    decoder = SimpleNamespace(decompress=lambda _: values.tobytes())
    monkeypatch.setitem(sys.modules, "numcodecs", SimpleNamespace(blosc=decoder))
    decoded = public.decode_numeric(payload, schema("<f4", (3, 2), (3, 2)))
    np.testing.assert_array_equal(decoded, values)
    assert not decoded.flags.writeable


def receipt(tmp_path):
    payload = tmp_path / "objects/MAIN/MAIN_0/DATA/0.8.0"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b"bounded")
    item = {"key": "MAIN/MAIN_0/DATA/0.8.0", "compressed_bytes": 7, "etag": "exact"}
    plan = {"objects": [item], "planned_compressed_bytes": 7}
    complete = {
        "bytes": 7,
        "objects": [
            {"key": item["key"], "bytes": 7, "etag": "exact", "sha256": "a" * 64}
        ],
    }
    return plan, complete, payload


@pytest.mark.parametrize(
    "field", ["total", "length", "etag", "duplicate", "digest", "payload"]
)
def test_receipts_cannot_bypass_bounded_exact_plan(tmp_path, field):
    plan, complete, payload = receipt(tmp_path)
    if field == "total":
        complete["bytes"] = 1
    elif field == "length":
        complete["objects"][0]["bytes"] = 1
    elif field == "etag":
        complete["objects"][0]["etag"] = "changed"
    elif field == "duplicate":
        complete["objects"].append(complete["objects"][0])
    elif field == "digest":
        complete["objects"][0]["sha256"] = "Z" * 64
    else:
        payload.write_bytes(b"wrong-length")
    with pytest.raises(ValueError):
        public.validate_receipt(plan, complete, tmp_path)


def test_valid_receipt_and_oversized_header(tmp_path):
    plan, complete, _ = receipt(tmp_path)
    assert len(public.validate_receipt(plan, complete, tmp_path)) == 1
    with pytest.raises(ValueError):
        public.expected_objects_with_headers(
            [{"key": "fixed"}],
            [
                {
                    "compressed_bytes": public.MAX_DECODED_OBJECT_BYTES + 1024**2 + 1,
                    "etag": "exact",
                }
            ],
        )
