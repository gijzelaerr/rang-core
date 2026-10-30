"""Inert object-string grammar and bounded native provenance boundaries."""

import builtins
import io
import json
import pickle
import struct
from copy import deepcopy
from email.message import Message
from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest
from rangtoy import flagging_provenance as provenance


def payload(values, shape=None, protocol=5):
    array = np.array(values, dtype=object)
    if shape is not None:
        array = array.reshape(shape)
    return pickle.dumps(array, protocol=protocol)


def replace(raw, before, after):
    assert before in raw
    changed = raw.replace(before, after, 1)
    return changed[:3] + struct.pack("<Q", len(changed) - 11) + changed[11:]


@pytest.mark.parametrize(
    "values,shape",
    [(["a", "a", ""], (3,)), (["one", "two"], (2, 1)), ([""], (1,)), ([], (0,))],
)
def test_recognizer_extracts_only_known_local_strings(values, shape):
    result = provenance.recognize_strings(payload(values, shape), shape)
    assert result["strings"] == values
    assert result["shape"] == list(shape)


def test_old_numpy_module_spelling_is_inert():
    raw = replace(
        payload(["m000"]),
        b"\x8c\x16numpy._core.multiarray",
        b"\x8c\x15numpy.core.multiarray",
    )
    assert provenance.recognize_strings(raw, (1,))["strings"] == ["m000"]


def test_no_unpickler_or_payload_selected_import_is_called(monkeypatch):
    raw = payload(["safe"])

    def forbidden(*args, **kwargs):
        raise AssertionError("must not execute payload")

    monkeypatch.setattr(pickle, "loads", forbidden)
    monkeypatch.setattr(pickle, "load", forbidden)
    monkeypatch.setattr(pickle, "Unpickler", forbidden)
    monkeypatch.setattr(builtins, "__import__", forbidden)
    assert provenance.recognize_strings(raw, (1,))["strings"] == ["safe"]


def test_payload_selected_eval_reducer_is_never_called(monkeypatch):
    class Foreign:
        def __reduce__(self):
            return eval, ("1+1",)

    array = np.empty(1, object)
    array[0] = Foreign()
    raw = pickle.dumps(array, protocol=5)
    monkeypatch.setattr(
        builtins, "eval", lambda *args: pytest.fail("payload callable executed")
    )
    with pytest.raises(ValueError, match="GLOBAL"):
        provenance.recognize_strings(raw, (1,))


@pytest.mark.parametrize(
    "before,after",
    [
        (b"\x8c\x16numpy._core.multiarray", b"\x8c\x16foreign.bad_.multiarray"),
        (b"\x8c\x0c_reconstruct", b"\x8c\x0cpayload_call"),
        (b"\x8c\x02O8", b"\x8c\x02i8"),
        (b"\x89\x88\x87", b"K\x00K\x01\x87"),
        (b"C\x01b", b"C\x01x"),
        (b"\x8c\x04safe", b"\x8c\x04a\x00bc"),
        (b"\x8c\x04safe", b"\x8c\x04\xed\xa0\x80x"),
        (b"\x8c\x04safe", b"\x8c\x04\xffabc"),
    ],
)
def test_foreign_symbols_state_and_invalid_strings_are_rejected(before, after):
    with pytest.raises(ValueError):
        provenance.recognize_strings(replace(payload(["safe"]), before, after), (1,))


@pytest.mark.parametrize(
    "kind",
    [
        "protocol4",
        "truncated",
        "trailing",
        "short_frame",
        "huge_frame",
        "shape",
        "bytes",
        "number",
        "long_string",
        "huge_payload",
        "recursive",
    ],
)
def test_adversarial_payloads_fail_closed(kind):
    raw = payload(["safe"])
    shape = (1,)
    if kind == "protocol4":
        raw = payload(["safe"], protocol=4)
    elif kind == "truncated":
        raw = raw[:-1]
    elif kind == "trailing":
        raw += b"extra"
    elif kind == "short_frame":
        raw = raw[:3] + struct.pack("<Q", 1) + raw[11:]
    elif kind == "huge_frame":
        raw = raw[:3] + struct.pack("<Q", 2**63) + raw[11:]
    elif kind == "shape":
        shape = (2,)
    elif kind == "bytes":
        raw = payload([b"safe"])
    elif kind == "number":
        raw = payload([1])
    elif kind == "long_string":
        raw = payload(["a" * (provenance.MAX_STRING_BYTES + 1)])
    elif kind == "huge_payload":
        raw = b"x" * (provenance.MAX_OBJECT_BYTES + 1)
    elif kind == "recursive":
        items = []
        items.append(items)
        array = np.empty(1, object)
        array[0] = items
        raw = pickle.dumps(array, protocol=5)
    with pytest.raises(ValueError):
        provenance.recognize_strings(raw, shape)


@pytest.mark.parametrize(
    "opcode", [b"\x97", b"P", b"\x81", b"\x92", b"\x82", b"c", b"0"]
)
def test_unsupported_opcodes_never_execute(opcode):
    raw = payload(["safe"])
    raw = raw[:11] + opcode + raw[11:]
    raw = raw[:3] + struct.pack("<Q", len(raw) - 11) + raw[11:]
    with pytest.raises(ValueError):
        provenance.recognize_strings(raw, (1,))


@pytest.mark.parametrize("limit", ["MAX_OPCODES", "MAX_STACK", "MAX_MEMO", "MAX_DEPTH"])
def test_recognizer_checks_frozen_resource_limits(monkeypatch, limit):
    monkeypatch.setattr(provenance, limit, 1)
    with pytest.raises(ValueError):
        provenance.recognize_strings(payload(["safe"]), (1,))


def metadata():
    # Generate the complete known schema without reading/download dependencies.
    result = {}
    original = provenance.object_plan

    class SchemaLookup(dict):
        def get(self, key, default=None):
            array = key.removesuffix("/.zarray")
            column = array.split("/")[-1]
            if array.startswith("ANTENNA/"):
                shape = [61]
            elif array.startswith("HISTORY/"):
                shape = [21, 1] if column in ("APP_PARAMS", "CLI_COMMAND") else [21]
            elif array.startswith("FEED/"):
                shape = [1, 2]
            elif array.startswith("STATE/"):
                shape = [3]
            elif column in ("LOG", "SCHEDULE"):
                shape = [1, 1]
            else:
                shape = [1]
            dtype = {"TIME": "<f8", "OBSERVATION_ID": "<i4", "OBJECT_ID": "<i4"}.get(
                column, "|O"
            )
            schema = {
                "zarr_format": 2,
                "shape": shape,
                "chunks": shape,
                "dtype": dtype,
                "compressor": provenance.COMPRESSOR.copy(),
                "filters": [{"id": "pickle", "protocol": 5}] if dtype == "|O" else None,
                "order": "C",
                "fill_value": 0,
            }
            result[key] = schema
            return schema

    original(SchemaLookup())
    return result


def frozen_head():
    objects = [
        {**item, "bytes": 20, "etag": '"abc"'}
        for item in provenance.object_plan(metadata())
    ]
    return {
        "base": provenance.BASE,
        "metadata_sha256": provenance.METADATA_SHA256,
        "objects": objects,
        "bytes": 85 * 20,
        "all_complete": True,
    }


def test_plan_is_exact_and_numeric_feed_ordered():
    objects = provenance.object_plan(metadata())
    assert len(objects) == 85
    assert sum(np.prod(i["shape"]) for i in objects if i["kind"] == "string") == 505
    assert objects[21]["key"] == "FEED/FEED_0/POLARIZATION_TYPE/0.0"
    assert objects[31]["key"] == "FEED/FEED_10/POLARIZATION_TYPE/0.0"
    assert objects[-1]["key"] == "HISTORY/HISTORY_0/OBJECT_ID/0"
    assert all(
        "MAIN/" not in i["key"] and i["url"].startswith(provenance.BASE + "/")
        for i in objects
    )
    changed = metadata()
    changed["ANTENNA/ANTENNA_0/NAME/.zarray"]["shape"] = [True]
    with pytest.raises(ValueError):
        provenance.object_plan(changed)


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "oversize",
        "sumcap",
        "badtotal",
        "origin",
        "weaketag",
        "boolsize",
        "incomplete",
    ],
)
def test_head_receipts_reconcile_exact_plan(change):
    head = frozen_head()
    if change == "missing":
        head["objects"].pop()
    elif change == "duplicate":
        head["objects"][1] = deepcopy(head["objects"][0])
    elif change == "oversize":
        head["objects"][0]["bytes"] = 65537
    elif change == "sumcap":
        for item in head["objects"]:
            item["bytes"] = 65536
        head["bytes"] = 85 * 65536
    elif change == "badtotal":
        head["bytes"] += 1
    elif change == "origin":
        head["base"] = "https://foreign.example"
    elif change == "weaketag":
        head["objects"][0]["etag"] = 'W/"abc"'
    elif change == "boolsize":
        head["objects"][0]["bytes"] = True
    elif change == "incomplete":
        head["all_complete"] = False
    with pytest.raises(ValueError):
        provenance._validate_head(head, provenance.object_plan(metadata()))


@pytest.mark.parametrize(
    "size,etag",
    [
        ("65537", '"abc"'),
        ("-1", '"abc"'),
        ("0", '"abc"'),
        ("x", '"abc"'),
        ("1", ""),
        ("1", 'W/"abc"'),
        ("1", '"a\nb"'),
    ],
)
def test_http_header_bounds(size, etag):
    headers = Message()
    headers["Content-Length"] = size
    headers["ETag"] = etag
    with pytest.raises(ValueError):
        provenance._headers(SimpleNamespace(headers=headers))


def test_duplicate_http_headers_and_redirects_are_rejected():
    headers = Message()
    headers["Content-Length"] = "1"
    headers["Content-Length"] = "1"
    headers["ETag"] = '"abc"'
    with pytest.raises(ValueError):
        provenance._headers(SimpleNamespace(headers=headers))
    with pytest.raises(ValueError):
        provenance._NoRedirect().redirect_request(
            None, None, 302, "redirect", {}, "https://foreign.example"
        )


def test_conditional_get_is_exact_and_has_no_redirect_handler(monkeypatch):
    captured = {}

    class Opener:
        def open(self, request, timeout):
            captured.update(
                method=request.method,
                url=request.full_url,
                etag=request.get_header("If-match"),
                timeout=timeout,
            )
            return SimpleNamespace(geturl=lambda: request.full_url, status=200)

    monkeypatch.setattr(provenance, "build_opener", lambda handler: Opener())
    item = provenance.object_plan(metadata())[0]
    provenance._request(item, "GET", '"abc"')
    assert captured == {
        "method": "GET",
        "url": item["url"],
        "etag": '"abc"',
        "timeout": 30,
    }
    with pytest.raises(ValueError):
        provenance._request({**item, "url": "https://foreign.example"}, "GET")


@pytest.mark.parametrize(
    "decoded,compressed,block",
    [(65537, 20, 16), (10, 21, 10), (0, 20, 1), (10, 20, 11), (10, 20, 0)],
)
def test_blosc_bounds_checked_before_native_decompression(
    monkeypatch, decoded, compressed, block
):
    monkeypatch.setattr(
        provenance, "_blosc_decode", lambda _: pytest.fail("must not allocate")
    )
    raw = (
        b"\x02\x01\x00\x01" + struct.pack("<III", decoded, block, compressed) + b"xxxx"
    )
    with pytest.raises(ValueError):
        provenance.decode_payload(raw, {"kind": "string"})


def test_bounded_decode_checks_exact_numeric_bytes_and_output(monkeypatch):
    raw = b"\x02\x01\x00\x01" + struct.pack("<III", 168, 168, 20) + b"xxxx"
    item = provenance.object_plan(metadata())[-3]
    monkeypatch.setattr(provenance, "_blosc_decode", lambda _: bytes(168))
    assert provenance.decode_payload(raw, item) == bytes(168)
    monkeypatch.setattr(provenance, "_blosc_decode", lambda _: bytes(167))
    with pytest.raises(ValueError):
        provenance.decode_payload(raw, item)
    with pytest.raises(ValueError):
        provenance.decode_payload(raw, {**item, "dtype": "<i4"})


def receipt_fixture(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    head = frozen_head()
    plan = {"head_sha256": ""}
    (source / "metadata.json").write_text("test metadata")
    (source / "head-complete.json").write_text(json.dumps(head))
    plan["head_sha256"] = sha256(
        (source / "head-complete.json").read_bytes()
    ).hexdigest()
    (source / "acquisition-plan.json").write_text(json.dumps(plan))
    records = []
    for item in head["objects"]:
        path = source / "objects" / item["key"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 20)
        records.append(
            {
                "key": item["key"],
                "bytes": 20,
                "etag": item["etag"],
                "sha256": sha256(path.read_bytes()).hexdigest(),
            }
        )
    complete = {"objects": records, "bytes": 1700}
    (source / "acquisition-complete.json").write_text(json.dumps(complete))
    monkeypatch.setattr(provenance, "read_metadata", lambda _: metadata())
    return source, head, complete


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "missing",
        "duplicate",
        "badsize",
        "badsha",
        "symlink",
        "escapedparent",
        "headsha",
        "total",
    ],
)
def test_offline_receipt_file_bounds_before_decode(tmp_path, monkeypatch, change):
    source, head, complete = receipt_fixture(tmp_path, monkeypatch)
    path = source / "objects" / head["objects"][0]["key"]
    if change == "none":
        assert len(provenance.validate_acquired(source)) == 85
        return
    if change == "missing":
        complete["objects"].pop()
    elif change == "duplicate":
        complete["objects"][1] = deepcopy(complete["objects"][0])
    elif change == "badsize":
        path.write_bytes(b"x" * 21)
    elif change == "badsha":
        complete["objects"][0]["sha256"] = "0" * 64
    elif change == "symlink":
        path.unlink()
        path.symlink_to(source / "metadata.json")
    elif change == "escapedparent":
        parent = path.parent
        outside = tmp_path / "outside"
        parent.rename(outside)
        parent.symlink_to(outside, target_is_directory=True)
    elif change == "headsha":
        (source / "acquisition-plan.json").write_text(
            json.dumps({"head_sha256": "0" * 64})
        )
    elif change == "total":
        complete["bytes"] += 1
    (source / "acquisition-complete.json").write_text(json.dumps(complete))
    monkeypatch.setattr(
        provenance, "_blosc_decode", lambda _: pytest.fail("must not decode")
    )
    with pytest.raises(ValueError):
        provenance.validate_acquired(source)


def test_output_paths_json_duplicate_keys_and_logical_cap(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    existing = tmp_path / "existing"
    existing.mkdir()
    for output in (source, source / "nested", tmp_path, existing):
        with pytest.raises(ValueError):
            provenance._fresh(output, source)
    link = tmp_path / "linked"
    link.symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError):
        provenance._fresh(link / "out", existing)
    raw = tmp_path / "duplicate.json"
    raw.write_text('{"a":1,"a":2}')
    with pytest.raises(ValueError):
        provenance._json(raw)
    target = tmp_path / "new.json"
    monkeypatch.setattr(provenance, "MAX_DERIVED_BYTES", 65537)
    with pytest.raises(ValueError):
        provenance._new_json(target, {"oversize": "a" * 100})
    assert not target.exists()


@pytest.mark.parametrize("content", ['{"v":NaN}', '{"v":Infinity}', '{"v":-Infinity}'])
def test_nonfinite_receipt_constants_are_rejected(tmp_path, content):
    path = tmp_path / "receipt.json"
    path.write_text(content)
    with pytest.raises(ValueError):
        provenance._json(path)


def test_metadata_symlink_and_bounded_input_size_are_rejected(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.write_bytes(b"test")
    path = tmp_path / "metadata.json"
    path.symlink_to(target)
    monkeypatch.setattr(
        provenance,
        "read_metadata",
        lambda _: pytest.fail("must not follow metadata symlink"),
    )
    with pytest.raises(ValueError):
        provenance._metadata(path)
    with pytest.raises(ValueError):
        provenance._read(target, limit=3)


class Response:
    def __init__(self, item, size=20, etag='"abc"', data=b"x" * 20, forbid_read=False):
        self.headers = Message()
        self.headers["Content-Length"] = str(size)
        self.headers["ETag"] = etag
        self.body = io.BytesIO(data)
        self.forbid_read = forbid_read

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, count):
        assert not self.forbid_read, "HEAD must never read a body"
        return self.body.read(count)


def network_fixture(tmp_path, monkeypatch):
    source = tmp_path / "metadata.json"
    source.write_bytes(b"{}")
    monkeypatch.setattr(provenance, "read_metadata", lambda _: metadata())
    monkeypatch.setattr(provenance, "METADATA_SHA256", sha256(b"{}").hexdigest())
    return source


def test_head_stage_has_only85_heads_and_frozen_complete_receipt(tmp_path, monkeypatch):
    source = network_fixture(tmp_path, monkeypatch)
    calls = []

    def request(item, method, etag=None):
        calls.append((item["key"], method, etag))
        return Response(item, forbid_read=True)

    monkeypatch.setattr(provenance, "_request", request)
    output = tmp_path / "head"
    receipt = provenance.head(output, source)
    assert len(calls) == 85 and all(m == "HEAD" and e is None for _, m, e in calls)
    assert receipt["bytes"] == 1700 and receipt["all_complete"]
    assert json.loads((output / "head-complete.json").read_text()) == receipt
    with pytest.raises(ValueError):
        provenance.head(output, source)
    assert len(calls) == 85


def test_head_aggregate_cap_retains_failure_and_never_starts_get(tmp_path, monkeypatch):
    source = network_fixture(tmp_path, monkeypatch)
    calls = []

    def request(item, method, etag=None):
        calls.append(method)
        return Response(item, size=65536, forbid_read=True)

    monkeypatch.setattr(provenance, "_request", request)
    output = tmp_path / "head"
    with pytest.raises(ValueError, match="aggregate"):
        provenance.head(output, source)
    assert calls == ["HEAD"] * 17
    assert (output / "head-failed.json").exists()
    assert not (output / "head-complete.json").exists()


@pytest.mark.parametrize("change", ["etag", "length", "shortbody", "longbody"])
def test_get_refuses_changed_or_partial_objects_and_preserves_failed_receipt(
    tmp_path, monkeypatch, change
):
    source = network_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(provenance, "_request", lambda i, m, etag=None: Response(i))
    heads = tmp_path / "head"
    provenance.head(heads, source)
    calls = []

    def request(item, method, etag=None):
        calls.append((method, etag))
        opts = {
            "etag": {"etag": '"changed"'},
            "length": {"size": 21},
            "shortbody": {"data": b"x" * 19},
            "longbody": {"data": b"x" * 21},
        }[change]
        return Response(item, **opts)

    monkeypatch.setattr(provenance, "_request", request)
    output = tmp_path / "acquired"
    with pytest.raises(ValueError):
        provenance.acquire(output, heads)
    assert calls == [("GET", '"abc"')]
    assert (output / "acquisition-failed.json").exists()
    assert not (output / "acquisition-complete.json").exists()
    assert not any(p.is_file() for p in (output / "objects").rglob("*"))


def test_offline_end_to_end_inert_strings_does_not_open_gate(tmp_path, monkeypatch):
    source = network_fixture(tmp_path, monkeypatch)
    expected = provenance.object_plan(metadata())
    raw, compressed = {}, {}
    for index, item in enumerate(expected):
        if item["kind"] == "string":
            text = ["native"] * int(np.prod(item["shape"]))
            if item["array"].endswith("TELESCOPE_NAME"):
                text = ["MeerKAT"]
            values = payload(text, item["shape"])
        else:
            values = np.arange(21, dtype=item["dtype"]).tobytes()
        raw[index] = values
        compressed[item["key"]] = (
            b"\x02\x01\x00\x01"
            + struct.pack("<III", len(values), len(values), 20)
            + struct.pack("<I", index)
        )
    calls = []

    def request(item, method, etag=None):
        calls.append(method)
        return Response(
            item, data=compressed[item["key"]], forbid_read=method == "HEAD"
        )

    monkeypatch.setattr(provenance, "_request", request)
    heads, acquired, inspected = (tmp_path / n for n in ("head", "acquired", "inspect"))
    provenance.head(heads, source)
    provenance.acquire(acquired, heads)
    monkeypatch.setattr(
        provenance, "_blosc_decode", lambda p: raw[struct.unpack_from("<I", p, 16)[0]]
    )
    result = provenance.run(inspected, acquired)
    assert calls == ["HEAD"] * 85 + ["GET"] * 85
    assert result["objects"] == 85 and result["string_elements"] == 505
    assert len(result["history"]) == 21 and result["history"][20]["TIME"] == 20
    assert result["conversion_solver_gate"]["pass"] is False
    assert result["weight_sigma_provenance_status"].startswith("unvalidated")
    assert result["same_observation_not_independent_transfer"]
    assert result["audit"]["new_QC_solves"] == 0
