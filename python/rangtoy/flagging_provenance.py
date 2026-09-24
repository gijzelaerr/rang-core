"""Bounded native metadata acquisition and inert object-string recognition.

HEAD, approved GET and offline inspection are separate calls. No remote pickle
is unpickled; GLOBAL/REDUCE/BUILD names are inert syntax, never imported/called.
No visibilities, Measurement Sets, original flags or native weights are written.
"""

import argparse
import io
import json
import math
import pickletools
import re
import shutil
import struct
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .flagging_public import BASE, METADATA_SHA256, RESERVE_BYTES, read_metadata

MAX_OBJECT_BYTES = 65536
MAX_TOTAL_BYTES = 1048576
MAX_STRING_BYTES = 8192
MAX_OPCODES = 10000
MAX_STACK = 2048
MAX_MEMO = 4096
MAX_DEPTH = 16
MAX_DERIVED_BYTES = 8 * 1024**2
COMPRESSOR = {
    "id": "blosc",
    "cname": "lz4",
    "clevel": 5,
    "shuffle": 1,
    "blocksize": 0,
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read(path, limit=2**21):
    path = Path(path)
    if (
        any(p.is_symlink() for p in (path, *path.parents))
        or not path.is_file()
        or path.stat().st_size > limit
    ):
        raise ValueError("unsafe or oversized bounded input")
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("bounded input grew beyond its cap")
    return payload


def _digest(path, limit=2**21):
    return sha256(_read(path, limit)).hexdigest()


def _metadata(path):
    _read(path)
    return read_metadata(path)


def _budget(directory, extra, failure=False):
    allocated = sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
    reserve = 0 if failure else 65536
    if allocated + extra + reserve > MAX_DERIVED_BYTES:
        raise ValueError("metadata output exceeds8MiB checked logical cap")
    if shutil.disk_usage(directory).free < RESERVE_BYTES + extra + reserve:
        raise ValueError("metadata output would violate8GiB reserve")


def _new_json(path, value):
    path = Path(path)
    payload = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()
    _budget(path.parent, len(payload), failure=path.name.endswith("-failed.json"))
    with path.open("xb") as stream:
        stream.write(payload)


def _copy_new(source, target):
    payload = _read(source)
    _budget(target.parent, len(payload))
    with target.open("xb") as writer:
        writer.write(payload)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json(path):
    def invalid_constant(value):
        raise ValueError("nonfinite JSON constant")

    return json.loads(
        _read(path), object_pairs_hook=_pairs, parse_constant=invalid_constant
    )


def _fresh(run_dir, source):
    raw_output, raw_source = Path(run_dir), Path(source)
    if any(
        p.is_symlink() for raw in (raw_output, raw_source) for p in (raw, *raw.parents)
    ):
        raise ValueError("input/output symlink rejected")
    output, source = raw_output.resolve(), raw_source.resolve()
    if output == source or output in source.parents or source in output.parents:
        raise ValueError("input/output must not be nested")
    if output.exists():
        raise ValueError("choose a fresh exclusive output")
    ancestor = output.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < RESERVE_BYTES + MAX_DERIVED_BYTES:
        raise ValueError("keep8GiB reserve plus8MiB metadata allocation")
    return output, source


def object_plan(metadata):
    """Finite 85-key plan, independent of user-provided paths or array order."""
    arrays = []

    def add(prefix, columns, shape):
        for column in columns:
            arrays.append((f"{prefix}/{column}", shape, "string", "|O"))

    add("ANTENNA/ANTENNA_0", ("MOUNT", "NAME", "STATION", "TYPE"), [61])
    add("FIELD/FIELD_0", ("CODE", "NAME"), [1])
    add(
        "HISTORY/HISTORY_0",
        ("APPLICATION", "MESSAGE", "ORIGIN", "PRIORITY"),
        [21],
    )
    add("HISTORY/HISTORY_0", ("APP_PARAMS", "CLI_COMMAND"), [21, 1])
    add("OBSERVATION/OBSERVATION_0", ("LOG", "SCHEDULE"), [1, 1])
    add(
        "OBSERVATION/OBSERVATION_0",
        ("OBSERVER", "PROJECT", "SCHEDULE_TYPE", "TELESCOPE_NAME"),
        [1],
    )
    add("SPECTRAL_WINDOW/SPECTRAL_WINDOW_0", ("FREQ_GROUP_NAME", "NAME"), [1])
    add("STATE/STATE_0", ("OBS_MODE",), [3])
    for group in range(61):
        add(f"FEED/FEED_{group}", ("POLARIZATION_TYPE",), [1, 2])
    for column, dtype in (
        ("TIME", "<f8"),
        ("OBSERVATION_ID", "<i4"),
        ("OBJECT_ID", "<i4"),
    ):
        arrays.append((f"HISTORY/HISTORY_0/{column}", [21], "numeric", dtype))
    result = []
    for array, shape, kind, dtype in arrays:
        schema = metadata.get(array + "/.zarray")
        expected = {
            "zarr_format": 2,
            "shape": shape,
            "chunks": shape,
            "dtype": dtype,
            "compressor": COMPRESSOR,
            "filters": [{"id": "pickle", "protocol": 5}] if kind == "string" else None,
            "order": "C",
            "fill_value": 0,
        }
        if schema != expected or any(type(n) is not int for n in schema["shape"]):
            raise ValueError(f"unfrozen metadata schema: {array}")
        key = array + "/" + ".".join("0" for _ in shape)
        result.append(
            {
                "key": key,
                "array": array,
                "kind": kind,
                "shape": shape,
                "dtype": dtype,
                "schema": schema,
                "url": f"{BASE}/{key}",
            }
        )
    return result


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirects forbidden before following them")


def _request(item, method, etag=None):
    if method not in ("HEAD", "GET") or item["url"] != f"{BASE}/{item['key']}":
        raise ValueError("unfrozen request")
    request = Request(item["url"], method=method)
    if etag is not None:
        request.add_header("If-Match", etag)
    response = build_opener(_NoRedirect()).open(request, timeout=30)
    if response.geturl() != item["url"] or response.status != 200:
        response.close()
        raise ValueError("unexpected object origin/status")
    return response


def _headers(response):
    for name in ("Content-Length", "ETag"):
        values = response.headers.get_all(name, [])
        if len(values) != 1:
            raise ValueError("missing or duplicate source header")
    length, etag = response.headers["Content-Length"], response.headers["ETag"]
    if (
        not re.fullmatch(r"[0-9]{1,6}", length)
        or not 0 < int(length) <= MAX_OBJECT_BYTES
    ):
        raise ValueError("compressed object exceeds64KiB cap")
    if not re.fullmatch(r'"[\x21\x23-\x7e]{1,254}"', etag):
        raise ValueError("missing/invalid strong ETag")
    return int(length), etag


def _validate_head(head, expected):
    if head.get("base") != BASE or head.get("metadata_sha256") != METADATA_SHA256:
        raise ValueError("unfrozen HEAD source")
    objects = head.get("objects", [])
    if len(objects) != len(expected) or head.get("all_complete") is not True:
        raise ValueError("complete85-object HEAD receipt required")
    total = 0
    for actual, item in zip(objects, expected):
        base = {k: v for k, v in actual.items() if k not in ("bytes", "etag")}
        size = actual.get("bytes")
        if (
            base != item
            or type(size) is not int
            or not 0 < size <= MAX_OBJECT_BYTES
            or not isinstance(actual.get("etag"), str)
            or not re.fullmatch(r'"[\x21\x23-\x7e]{1,254}"', actual["etag"])
        ):
            raise ValueError("invalid frozen HEAD entry")
        total += size
    if total != head.get("bytes") or total > MAX_TOTAL_BYTES:
        raise ValueError("HEAD total exceeds1MiB or disagrees with entries")
    return objects


def head(run_dir, metadata_path):
    """HEAD-only; do not call until the root approves this separate stage."""
    output, source = _fresh(run_dir, metadata_path)
    expected = object_plan(_metadata(source))
    module_sha = _digest(__file__)
    output.mkdir(parents=True, exist_ok=False)
    _copy_new(source, output / "metadata.json")
    _new_json(
        output / "config.json",
        {"stage": "HEAD-only", "module_sha256": module_sha, "started_utc": _now()},
    )
    objects = []
    try:
        for index, item in enumerate(expected):
            with _request(item, "HEAD") as response:
                size, etag = _headers(response)
            objects.append({**item, "bytes": size, "etag": etag})
            _new_json(output / f"head-{index:03d}.json", objects[-1])
            if sum(x["bytes"] for x in objects) > MAX_TOTAL_BYTES:
                raise ValueError("HEAD aggregate exceeds1MiB cap")
        receipt = {
            "base": BASE,
            "metadata_sha256": METADATA_SHA256,
            "objects": objects,
            "bytes": sum(x["bytes"] for x in objects),
            "all_complete": True,
            "finished_utc": _now(),
            "no_GET_or_decoding": True,
        }
        _validate_head(receipt, expected)
        if _digest(source) != METADATA_SHA256 or _digest(__file__) != module_sha:
            raise ValueError("HEAD source/module changed")
        _new_json(output / "head-complete.json", receipt)
        return receipt
    except Exception as error:
        _new_json(
            output / "head-failed.json", {"error": str(error), "completed": objects}
        )
        raise


def acquire(run_dir, head_dir):
    """Conditional GETs only after independent root approval of all HEADs."""
    output, source = _fresh(run_dir, head_dir)
    metadata = _metadata(source / "metadata.json")
    frozen_path = source / "head-complete.json"
    objects = _validate_head(_json(frozen_path), object_plan(metadata))
    head_sha = _digest(frozen_path)
    module_sha = _digest(__file__)
    output.mkdir(parents=True, exist_ok=False)
    for name in ("metadata.json", "head-complete.json"):
        _copy_new(source / name, output / name)
    _new_json(
        output / "acquisition-plan.json",
        {"head_sha256": head_sha, "module_sha256": module_sha, "started_utc": _now()},
    )
    records = []
    try:
        for index, item in enumerate(objects):
            destination = output / "objects" / item["key"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            with _request(item, "GET", item["etag"]) as response:
                size, etag = _headers(response)
                if size != item["bytes"] or etag != item["etag"]:
                    raise ValueError("object changed since approved HEAD")
                payload = response.read(size + 1)
                if len(payload) != size or response.read(1):
                    raise ValueError("truncated/overlong object")
            _budget(output, len(payload))
            with destination.open("xb") as stream:
                stream.write(payload)
            record = {
                "key": item["key"],
                "bytes": size,
                "etag": etag,
                "sha256": sha256(payload).hexdigest(),
            }
            records.append(record)
            _new_json(output / f"object-{index:03d}.json", record)
        if (
            _digest(frozen_path) != head_sha
            or _digest(__file__) != module_sha
            or _digest(source / "metadata.json") != METADATA_SHA256
        ):
            raise ValueError("approved HEAD receipt mutated")
        complete = {
            "objects": records,
            "bytes": sum(r["bytes"] for r in records),
            "finished_utc": _now(),
        }
        _new_json(output / "acquisition-complete.json", complete)
        return complete
    except Exception as error:
        _new_json(
            output / "acquisition-failed.json",
            {"error": str(error), "completed": records},
        )
        raise


class _Symbol:
    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name


class _Dtype:
    __slots__ = ("valid",)

    def __init__(self):
        self.valid = False


class _Array:
    __slots__ = ("strings",)

    def __init__(self):
        self.strings = None


def recognize_strings(payload, shape):
    """Recognize inert NumPy object syntax; never reconstruct a Python object."""
    if (
        not isinstance(payload, bytes)
        or not 11 <= len(payload) <= MAX_OBJECT_BYTES
        or len(shape) not in (1, 2)
        or any(type(n) is not int or n < 0 for n in shape)
        or math.prod(shape) > 61
    ):
        raise ValueError("bounded string payload/shape required")
    try:
        operations = []
        for operation in pickletools.genops(io.BytesIO(payload)):
            operations.append(operation)
            if len(operations) > MAX_OPCODES:
                raise ValueError("opcode limit")
    except (ValueError, UnicodeError, struct.error, OverflowError) as error:
        raise ValueError("malformed or excessive pickle syntax") from error
    if (
        len(operations) < 3
        or operations[0][0].name != "PROTO"
        or operations[0][1:] != (5, 0)
        or operations[1][0].name != "FRAME"
        or operations[1][2] != 2
        or operations[1][1] != len(payload) - 11
        or operations[-1][0].name != "STOP"
        or operations[-1][2] != len(payload) - 1
    ):
        raise ValueError("exact single-frame PROTO5 syntax required")
    stack, memo = [], []
    marker = object()
    reductions = builds = 0
    names = {
        ("numpy._core.multiarray", "_reconstruct"): "array",
        ("numpy.core.multiarray", "_reconstruct"): "array",
        ("numpy", "ndarray"): "ndarray",
        ("numpy", "dtype"): "dtype",
    }

    def pop():
        if not stack:
            raise ValueError("stack underflow")
        return stack.pop()

    def marked():
        index = next(
            (i for i in range(len(stack) - 1, -1, -1) if stack[i] is marker), None
        )
        if index is None:
            raise ValueError("missing MARK")
        values = stack[index + 1 :]
        del stack[index:]
        return values

    def depth(value):
        if isinstance(value, (tuple, list)):
            return 1 + max((depth(x) for x in value), default=0)
        return 0

    try:
        for opcode, argument, _ in operations[2:-1]:
            name = opcode.name
            if name in ("SHORT_BINUNICODE", "BINUNICODE", "BINUNICODE8"):
                if (
                    len(argument.encode("utf8", errors="strict")) > MAX_STRING_BYTES
                    or "\0" in argument
                ):
                    raise ValueError("invalid/oversized Unicode string")
                stack.append(argument)
            elif name in ("BININT", "BININT1", "BININT2"):
                if not -1 <= argument <= 63:
                    raise ValueError("unbounded integer")
                stack.append(argument)
            elif name == "SHORT_BINBYTES":
                if argument != b"b":
                    raise ValueError("foreign bytes literal")
                stack.append(argument)
            elif name in ("NEWTRUE", "NEWFALSE", "NONE"):
                stack.append({"NEWTRUE": True, "NEWFALSE": False, "NONE": None}[name])
            elif name == "MARK":
                stack.append(marker)
                if sum(x is marker for x in stack) > MAX_DEPTH:
                    raise ValueError("nesting limit")
            elif name == "TUPLE":
                value = tuple(marked())
                if depth(value) > MAX_DEPTH:
                    raise ValueError("tuple nesting limit")
                stack.append(value)
            elif name in ("TUPLE1", "TUPLE2", "TUPLE3"):
                n = int(name[-1])
                value = tuple(reversed([pop() for _ in range(n)]))
                if depth(value) > MAX_DEPTH:
                    raise ValueError("tuple nesting limit")
                stack.append(value)
            elif name == "EMPTY_LIST":
                stack.append([])
            elif name in ("APPEND", "APPENDS"):
                values = [pop()] if name == "APPEND" else marked()
                if (
                    not stack
                    or type(stack[-1]) is not list
                    or any(type(x) is not str for x in values)
                ):
                    raise ValueError("only flat string lists allowed")
                stack[-1].extend(values)
                if len(stack[-1]) > math.prod(shape):
                    raise ValueError("too many string elements")
            elif name == "MEMOIZE":
                if not stack or len(memo) >= MAX_MEMO:
                    raise ValueError("memo limit/underflow")
                memo.append(stack[-1])
            elif name in ("BINGET", "LONG_BINGET"):
                if not 0 <= argument < len(memo) or isinstance(
                    memo[argument], (list, tuple, _Array)
                ):
                    raise ValueError("invalid/recursive container memo")
                stack.append(memo[argument])
            elif name == "STACK_GLOBAL":
                symbol, module = pop(), pop()
                if (
                    type(module) is not str
                    or type(symbol) is not str
                    or (module, symbol) not in names
                ):
                    raise ValueError("foreign GLOBAL")
                stack.append(_Symbol(names[module, symbol]))
            elif name == "REDUCE":
                args, token = pop(), pop()
                if type(token) is not _Symbol or type(args) is not tuple:
                    raise ValueError("foreign reducer")
                if (
                    token.name == "array"
                    and len(args) == 3
                    and type(args[0]) is _Symbol
                    and args[0].name == "ndarray"
                    and type(args[1]) is tuple
                    and args[1] == (0,)
                    and type(args[1][0]) is int
                    and args[2] == b"b"
                ):
                    stack.append(_Array())
                elif (
                    token.name == "dtype"
                    and args == ("O8", False, True)
                    and args[1] is False
                    and args[2] is True
                ):
                    stack.append(_Dtype())
                else:
                    raise ValueError("foreign reconstruction/dtype")
                reductions += 1
                if reductions > 2:
                    raise ValueError("extra reducer")
            elif name == "BUILD":
                state = pop()
                if not stack or type(state) is not tuple:
                    raise ValueError("foreign BUILD")
                token = stack[-1]
                if (
                    type(token) is _Dtype
                    and not token.valid
                    and state == (3, "|", None, None, None, -1, -1, 63)
                ):
                    token.valid = True
                elif (
                    type(token) is _Array and token.strings is None and len(state) == 5
                ):
                    version, dimensions, dtype, order, strings = state
                    if (
                        type(version) is not int
                        or version != 1
                        or type(dimensions) is not tuple
                        or dimensions != tuple(shape)
                        or any(type(n) is not int for n in dimensions)
                        or type(dtype) is not _Dtype
                        or not dtype.valid
                        or order is not False
                        or type(strings) is not list
                        or len(strings) != math.prod(shape)
                        or any(type(x) is not str for x in strings)
                    ):
                        raise ValueError("array state/shape/count mismatch")
                    token.strings = tuple(strings)
                else:
                    raise ValueError("foreign/duplicate BUILD state")
                builds += 1
                if builds > 2:
                    raise ValueError("extra BUILD")
            else:
                raise ValueError(f"unsupported inert opcode: {name}")
            if len(stack) > MAX_STACK:
                raise ValueError("stack limit")
    except (IndexError, UnicodeError, RecursionError) as error:
        raise ValueError("malformed bounded object syntax") from error
    if (
        len(stack) != 1
        or type(stack[0]) is not _Array
        or stack[0].strings is None
        or reductions != 2
        or builds != 2
    ):
        raise ValueError("incomplete object-string expression")
    return {
        "shape": list(shape),
        "strings": list(stack[0].strings),
        "opcode_count": len(operations),
    }


def _blosc_decode(payload):
    import numcodecs
    from numcodecs import blosc

    if numcodecs.__version__ != "0.15.1":
        raise ValueError("requires pinned numcodecs0.15.1")
    return blosc.decompress(payload)


def decode_payload(payload, item):
    """Validate Blosc size before the pinned native decompressor allocates."""
    if not 16 <= len(payload) <= MAX_OBJECT_BYTES:
        raise ValueError("compressed payload cap/header")
    decoded, blocksize, compressed = struct.unpack_from("<III", payload, 4)
    if (
        not 0 < decoded <= MAX_OBJECT_BYTES
        or compressed != len(payload)
        or not 0 < blocksize <= decoded
    ):
        raise ValueError("unbounded/conflicting Blosc header")
    if item["kind"] == "numeric" and decoded != math.prod(item["shape"]) * int(
        item["dtype"][2:]
    ):
        raise ValueError("numeric decoded size mismatch")
    raw = _blosc_decode(payload)
    if len(raw) != decoded:
        raise ValueError("decompressed size mismatch")
    return raw


def validate_acquired(source):
    """Reconcile all receipts and file bounds before any codec/payload read."""
    if Path(source).is_symlink():
        raise ValueError("acquisition source symlink rejected")
    source = Path(source).resolve()
    expected = object_plan(_metadata(source / "metadata.json"))
    objects = _validate_head(_json(source / "head-complete.json"), expected)
    plan, complete = (
        _json(source / "acquisition-plan.json"),
        _json(source / "acquisition-complete.json"),
    )
    if plan.get("head_sha256") != _digest(source / "head-complete.json"):
        raise ValueError("HEAD receipt digest mismatch")
    records = complete.get("objects", [])
    if len(records) != 85 or complete.get("bytes") != sum(
        item["bytes"] for item in objects
    ):
        raise ValueError("incomplete/acquisition total mismatch")
    for item, record in zip(objects, records):
        path = source / "objects" / item["key"]
        if (
            record.get("key") != item["key"]
            or type(record.get("bytes")) is not int
            or record["bytes"] != item["bytes"]
            or record.get("etag") != item["etag"]
            or not isinstance(record.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
            or path.is_symlink()
            or not path.is_file()
            or any(parent.is_symlink() for parent in path.parents if parent != source)
            or not path.resolve().is_relative_to(source / "objects")
            or path.stat().st_size != item["bytes"]
        ):
            raise ValueError("invalid payload receipt/file boundary")
    # All sizes/containment were checked before reading any object bytes.
    for item, record in zip(objects, records):
        if (
            _digest(source / "objects" / item["key"], MAX_OBJECT_BYTES)
            != record["sha256"]
        ):
            raise ValueError("payload SHA256 mismatch")
    return objects


def run(run_dir, acquired_dir):
    """Offline text inspection only; never converts an MS or selects sigma."""
    import numpy as np

    output, source = _fresh(run_dir, acquired_dir)
    objects = validate_acquired(source)
    module_sha = _digest(__file__)
    output.mkdir(parents=True, exist_ok=False)
    source_receipts = {
        name: _digest(source / name)
        for name in (
            "metadata.json",
            "head-complete.json",
            "acquisition-plan.json",
            "acquisition-complete.json",
        )
    }
    _new_json(
        output / "config.json",
        {
            "source": str(source),
            "source_receipts": source_receipts,
            "module_sha256": module_sha,
            "stage": "offline-inert-inspection",
            "started_utc": _now(),
            "derived_limit_bytes": MAX_DERIVED_BYTES,
        },
    )
    tables, numeric, decoded_total = {}, {}, 0
    try:
        for index, item in enumerate(objects):
            payload = _read(source / "objects" / item["key"], MAX_OBJECT_BYTES)
            declared = (
                struct.unpack_from("<I", payload, 4)[0]
                if len(payload) >= 16
                else MAX_TOTAL_BYTES + 1
            )
            if decoded_total + declared > MAX_TOTAL_BYTES:
                raise ValueError("aggregate decoded cap exceeded before allocation")
            raw = decode_payload(payload, item)
            decoded_total += len(raw)
            if item["kind"] == "string":
                tables[item["array"]] = recognize_strings(raw, item["shape"])
            else:
                values = np.frombuffer(raw, dtype=item["dtype"]).reshape(item["shape"])
                if not np.isfinite(values).all():
                    raise ValueError("nonfinite numeric HISTORY")
                numeric[item["array"].split("/")[-1]] = values.tolist()
            _new_json(
                output / f"decoded-{index:03d}.json",
                {
                    "key": item["key"],
                    "decoded_bytes": len(raw),
                    "decoded_sha256": sha256(raw).hexdigest(),
                },
            )
        history = []
        columns = (
            "APPLICATION",
            "APP_PARAMS",
            "CLI_COMMAND",
            "MESSAGE",
            "ORIGIN",
            "PRIORITY",
        )
        for index in range(21):
            row = {
                column: tables[f"HISTORY/HISTORY_0/{column}"]["strings"][index]
                for column in columns
            }
            row.update({column: values[index] for column, values in numeric.items()})
            history.append(row)
        terms = (
            "applycal",
            "calwt",
            "initweights",
            "statwt",
            "weight",
            "sigma",
            "corrected_data",
            "mstransform",
            "split",
            "average",
            "cubical",
            "caracal",
        )
        mentions = {
            term: [
                index
                for index, row in enumerate(history)
                if term in " ".join(str(row[c]) for c in columns).lower()
            ]
            for term in terms
        }
        if any(
            _digest(source / name) != digest for name, digest in source_receipts.items()
        ):
            raise ValueError("source receipts mutated during inspection")
        validate_acquired(source)
        if _digest(__file__) != module_sha:
            raise ValueError("inspection module changed")
        result = {
            "string_arrays": tables,
            "history": history,
            "history_keyword_mentions_not_operation_proof": mentions,
            "decoded_bytes": decoded_total,
            "objects": len(objects),
            "string_elements": sum(len(v["strings"]) for v in tables.values()),
            "same_observation_not_independent_transfer": True,
            "weight_sigma_provenance_status": "unvalidated; textual mentions/absence do not prove DATA-associated noise convention",
            "conversion_solver_gate": {
                "pass": False,
                "requires": [
                    "publisher DATA/sigma units and noise convention",
                    "column-specific export/calibration/averaging provenance",
                    "original units/measure-reference keywords and full numeric subtables",
                    "adequate calibrator sky and gain-bin support",
                    "separately frozen native-MS/solver protocol",
                ],
            },
            "audit": {
                "all_source_receipts_and_objects_unchanged": True,
                "no_pickle_unpickling_or_payload_callable": True,
                "no_MS_DATA_flags_weights_written": True,
                "new_QC_solves": 0,
            },
            "limitations": "Metadata-only text extraction from existing ESO137 primary observation; no verified independent data transfer, noise validation, native-MS conversion, calibration or scientific flagger advantage.",
        }
        _new_json(output / "result.json", result)
        return result
    except Exception as error:
        _new_json(
            output / "inspection-failed.json",
            {"error": str(error), "decoded_objects": len(tables) + len(numeric)},
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("head", "acquire", "inspect"))
    parser.add_argument("run_dir")
    parser.add_argument("source")
    args = parser.parse_args()
    {"head": head, "acquire": acquire, "inspect": run}[args.stage](
        args.run_dir, args.source
    )


if __name__ == "__main__":
    main()
