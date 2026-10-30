"""Bounded public numeric Zarr acquisition and read-only pilot inspection.

Network acquisition is separate from offline decoding/calibration. Never use
Zarr's object/pickle codec: string subtables and native-MS conversion remain a
separate, explicitly unresolved boundary. Raw received flags/weights are kept.
"""

import argparse
import json
import math
import shutil
import struct
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

BASE = "https://ratt-public-data.s3.af-south-1.amazonaws.com/ESO137/ms1_primary.zarr"
METADATA_SHA256 = "68fdb7f4f5f9392181bf645bd8e792e4dd96bd9857ad6489091b441adc59bbaa"
METADATA_BYTES = 888855
RESERVE_BYTES = 8 * 1024**3
MAX_COMPRESSED_BYTES = 1200 * 1024**2
MAX_DECODED_OBJECT_BYTES = 256 * 1024**2
EXCLUDED_MAIN = {"CORRECTED_DATA"}
SUBTABLES = (
    "ANTENNA/ANTENNA_0",
    "FIELD/FIELD_0",
    "POLARIZATION/POLARIZATION_0",
    "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0",
    "DATA_DESCRIPTION/DATA_DESCRIPTION_0",
    "OBSERVATION/OBSERVATION_0",
)


def _json_new(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def _now():
    return datetime.now(timezone.utc).isoformat()


def read_metadata(path):
    if Path(path).stat().st_size != METADATA_BYTES:
        raise ValueError("public metadata differs from the frozen source")
    payload = Path(path).read_bytes()
    if sha256(payload).hexdigest() != METADATA_SHA256:
        raise ValueError("public metadata differs from the frozen source")
    return json.loads(payload)["metadata"]


def numeric_schema(schema):
    """Validate numeric schemas before any codec or remote object is used."""
    dtype = schema.get("dtype", "")
    shape, chunks = schema.get("shape", []), schema.get("chunks", [])
    if (
        schema.get("zarr_format") != 2
        or schema.get("filters") not in (None, [])
        or schema.get("order") != "C"
        or dtype
        not in (
            "|b1",
            "|i1",
            "|u1",
            "<i2",
            "<i4",
            "<i8",
            "<u2",
            "<u4",
            "<u8",
            "<f4",
            "<f8",
            "<c8",
            "<c16",
        )
        or not shape
        or len(shape) != len(chunks)
        or any(type(x) is not int or x < 1 for x in (*shape, *chunks))
        or any(chunk > size for chunk, size in zip(chunks, shape))
        or not isinstance(schema.get("compressor"), dict)
        or schema["compressor"].get("id") != "blosc"
    ):
        raise ValueError(
            "only bounded filter-free C-order numeric Blosc arrays allowed"
        )
    try:
        itemsize = int(dtype[2:])
    except ValueError as error:
        raise ValueError("invalid numeric item size") from error
    if itemsize not in (1, 2, 4, 8, 16):
        raise ValueError("invalid numeric item size")
    decoded_bytes = math.prod(chunks) * itemsize
    if decoded_bytes > MAX_DECODED_OBJECT_BYTES:
        raise ValueError("numeric chunk exceeds decoded-object budget")
    return decoded_bytes


def object_plan(metadata, groups=(0, 1), tile=8):
    """Freeze exact first-row/tile objects; no target or arbitrary object access."""
    if (
        not groups
        or any(type(group) is not int or group not in (0, 1) for group in groups)
        or len(set(groups)) != len(groups)
        or type(tile) is not int
        or tile != 8
    ):
        raise ValueError("frozen MAIN_0/MAIN_1 first-row channel-tile8 pilot required")
    objects, rejected = [], []
    prefixes = [f"MAIN/MAIN_{group}" for group in groups] + list(SUBTABLES)
    for prefix in prefixes:
        for key, schema in sorted(metadata.items()):
            if not key.startswith(prefix + "/") or not key.endswith("/.zarray"):
                continue
            column = key.split("/")[-2]
            if prefix.startswith("MAIN/") and column in EXCLUDED_MAIN:
                continue
            array = key.removesuffix("/.zarray")
            try:
                decoded_bytes = numeric_schema(schema)
            except ValueError:
                if schema.get("dtype") == "|O":
                    rejected.append(array)
                    continue
                raise
            indices = [0] * len(schema["chunks"])
            if prefix.startswith("MAIN/") and len(indices) == 3:
                if schema["chunks"][1:] != [128, 4]:
                    raise ValueError("main visibility chunk layout changed")
                indices[1] = tile
            if any(
                i * chunk >= size
                for i, chunk, size in zip(indices, schema["chunks"], schema["shape"])
            ):
                raise ValueError("requested numeric chunk is outside its array")
            object_key = array + "/" + ".".join(map(str, indices))
            if ".." in PurePosixPath(object_key).parts:
                raise ValueError("object key traversal rejected")
            objects.append(
                {
                    "key": object_key,
                    "array": array,
                    "schema": schema,
                    "decoded_bytes": decoded_bytes,
                    "url": f"{BASE}/{object_key}",
                }
            )
    return objects, rejected


def fresh_paths(run_dir, source):
    if Path(run_dir).is_symlink():
        raise ValueError("output symlink rejected")
    run_dir, source = Path(run_dir).resolve(), Path(source).resolve()
    if run_dir == source or run_dir in source.parents or source in run_dir.parents:
        raise ValueError("input and output must not be nested")
    if run_dir.exists():
        raise ValueError("choose a fresh public-pilot directory")
    return run_dir, source


def check_disk(path, compressed_bytes):
    path = Path(path)
    while not path.exists():
        path = path.parent
    # Allow compressed originals plus offline products/copies; other tracks also
    # recheck their own allocation. This is a guard, not a disk reservation.
    required = RESERVE_BYTES + 3 * compressed_bytes
    if shutil.disk_usage(path).free < required:
        raise ValueError("public pilot would violate the 8GiB disk reserve")


def _request(url, method="GET"):
    response = urlopen(Request(url, method=method), timeout=60)
    if response.geturl() != url:
        response.close()
        raise ValueError("unexpected public-object redirect")
    return response


def acquire(run_dir, metadata_path, groups=(0, 1)):
    """Anonymous bounded HTTPS GETs, exact HEAD/ETag/length and exclusive files."""
    run_dir, metadata_path = fresh_paths(run_dir, metadata_path)
    metadata = read_metadata(metadata_path)
    objects, rejected = object_plan(metadata, groups=tuple(groups))
    # Verify consolidated metadata again, rather than assume yesterday's source.
    with _request(f"{BASE}/.zmetadata") as response:
        current = response.read(2 * 1024**2)
    if sha256(current).hexdigest() != METADATA_SHA256:
        raise ValueError("remote metadata changed; no visibility objects acquired")
    for item in objects:
        with _request(item["url"], "HEAD") as response:
            size = int(response.headers["Content-Length"])
            etag = response.headers.get("ETag")
        if not 0 < size <= MAX_DECODED_OBJECT_BYTES + 1024**2 or not etag:
            raise ValueError("unbounded object or missing source ETag")
        item.update({"compressed_bytes": size, "etag": etag})
    total = sum(item["compressed_bytes"] for item in objects)
    if total > MAX_COMPRESSED_BYTES:
        raise ValueError("planned compressed objects exceed 1200MiB pilot budget")
    check_disk(run_dir, total)
    run_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(metadata_path, run_dir / "metadata.json")
    plan = {
        "started_utc": _now(),
        "base": BASE,
        "metadata_sha256": METADATA_SHA256,
        "groups": list(groups),
        "native_channels": [1024, 1152],
        "planned_compressed_bytes": total,
        "disk_reserve_bytes": RESERVE_BYTES,
        "no_object_or_pickle_decoding": True,
        "rejected_object_arrays": rejected,
        "objects": objects,
    }
    _json_new(run_dir / "acquisition-plan.json", plan)
    completed = []
    try:
        for index, item in enumerate(objects):
            check_disk(run_dir, item["compressed_bytes"])
            destination = run_dir / "objects" / item["key"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            digest, received = sha256(), 0
            with _request(item["url"]) as response, destination.open("xb") as stream:
                if (
                    response.headers.get("ETag") != item["etag"]
                    or int(response.headers["Content-Length"])
                    != item["compressed_bytes"]
                ):
                    raise ValueError("object changed between HEAD and GET")
                while block := response.read(1024**2):
                    received += len(block)
                    if received > item["compressed_bytes"]:
                        raise ValueError("object exceeded its exact frozen length")
                    stream.write(block)
                    digest.update(block)
            if received != item["compressed_bytes"]:
                raise ValueError("truncated public object")
            record = {
                "key": item["key"],
                "bytes": received,
                "sha256": digest.hexdigest(),
                "etag": item["etag"],
            }
            completed.append(record)
            _json_new(run_dir / f"object-{index:03d}.json", record)
            print(f"Acquired {index + 1}/{len(objects)}: {item['key']}", flush=True)
    except Exception as error:
        _json_new(
            run_dir / "acquisition-failed.json",
            {"utc": _now(), "error": str(error), "completed": completed},
        )
        raise
    result = {"finished_utc": _now(), "objects": completed, "bytes": total}
    _json_new(run_dir / "acquisition-complete.json", result)
    return result


def decode_numeric(payload, schema):
    """Refuse object/filter codecs and validate Blosc length before allocating."""
    import numpy as np
    from numcodecs import blosc

    expected = numeric_schema(schema)
    if len(payload) < 16:
        raise ValueError("truncated Blosc header")
    decoded_bytes, _, compressed_bytes = struct.unpack_from("<III", payload, 4)
    if decoded_bytes != expected or compressed_bytes != len(payload):
        raise ValueError("Blosc header conflicts with frozen numeric schema")
    raw = blosc.decompress(payload)
    if len(raw) != expected:
        raise ValueError("decoded chunk length differs from schema")
    return np.frombuffer(raw, dtype=np.dtype(schema["dtype"])).reshape(schema["chunks"])


def complete_integrations(times, p, q, n_ant, count=16):
    """Select complete physical pair sets, never silently retain partial epochs."""
    import numpy as np

    times, p, q = np.asarray(times), np.asarray(p), np.asarray(q)
    if (
        times.ndim != 1
        or p.shape != times.shape
        or q.shape != times.shape
        or not np.isfinite(times).all()
        or p.dtype.kind not in "iu"
        or q.dtype.kind not in "iu"
        or np.any(p < 0)
        or np.any(q < 0)
        or np.any(p >= n_ant)
        or np.any(q >= n_ant)
        or type(count) is not int
        or count < 1
    ):
        raise ValueError("invalid row coordinates/integration request")
    expected = {(a, b) for a in range(n_ant) for b in range(a, n_ant)}
    selected, complete = np.zeros(len(times), bool), []
    for time in np.unique(times):
        rows = np.flatnonzero(times == time)
        pairs = list(zip(np.minimum(p[rows], q[rows]), np.maximum(p[rows], q[rows])))
        if len(pairs) != len(expected) or set(pairs) != expected:
            continue
        selected[rows] = True
        complete.append(float(time))
        if len(complete) == count:
            break
    if len(complete) != count:
        raise ValueError("too few complete integrations in acquired row chunk")
    return selected, complete


def inspect(run_dir, acquired_dir, integrations=16):
    """Offline numeric subset/audit; no native-MS/calibration/transfer claim."""
    import numpy as np

    if type(integrations) is not int or integrations != 16:
        raise ValueError("frozen16 complete integrations required")
    run_dir, acquired_dir = fresh_paths(run_dir, acquired_dir)
    plan = json.loads((acquired_dir / "acquisition-plan.json").read_text())
    complete = json.loads((acquired_dir / "acquisition-complete.json").read_text())
    metadata = read_metadata(acquired_dir / "metadata.json")
    expected_objects, rejected = object_plan(metadata, tuple(plan["groups"]))
    if plan["objects"] != expected_objects_with_headers(
        expected_objects, plan["objects"]
    ):
        raise ValueError("acquisition plan no longer describes frozen metadata")
    records = validate_receipt(plan, complete, acquired_dir)
    for item in expected_objects:
        payload = (acquired_dir / "objects" / item["key"]).read_bytes()
        record = records.get(item["key"], {})
        if sha256(payload).hexdigest() != record.get("sha256") or len(
            payload
        ) != record.get("bytes"):
            raise ValueError("acquired raw object digest mismatch")
    check_disk(run_dir, complete["bytes"])
    run_dir.mkdir(parents=True, exist_ok=False)
    subtables = {}
    for item in expected_objects:
        if not item["array"].startswith("MAIN/"):
            payload = (acquired_dir / "objects" / item["key"]).read_bytes()
            subtables[item["array"]] = decode_numeric(payload, item["schema"])
    n_ant = subtables["ANTENNA/ANTENNA_0/POSITION"].shape[0]
    frequencies = subtables["SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ"][0, 1024:1152]
    correlations = subtables["POLARIZATION/POLARIZATION_0/CORR_TYPE"]
    if n_ant != 61 or not np.array_equal(correlations, [[9, 10, 11, 12]]):
        raise ValueError("frozen antenna/polarization metadata changed")
    groups = []
    for group in plan["groups"]:
        prefix = f"MAIN/MAIN_{group}"
        items = [
            item for item in expected_objects if item["array"].startswith(prefix + "/")
        ]
        columns = {}
        for column in ("TIME", "ANTENNA1", "ANTENNA2"):
            item = next(item for item in items if item["array"] == f"{prefix}/{column}")
            payload = (acquired_dir / "objects" / item["key"]).read_bytes()
            columns[column] = decode_numeric(payload, item["schema"])
        selected, times = complete_integrations(
            columns["TIME"],
            columns["ANTENNA1"],
            columns["ANTENNA2"],
            n_ant,
            integrations,
        )
        row_indices = np.flatnonzero(selected)
        columns = {
            column: values[selected].copy() for column, values in columns.items()
        }
        for item in items:
            column = item["array"].split("/")[-1]
            if column not in columns:
                payload = (acquired_dir / "objects" / item["key"]).read_bytes()
                columns[column] = decode_numeric(payload, item["schema"])[
                    selected
                ].copy()
        data, model, flags = (columns[key] for key in ("DATA", "MODEL_DATA", "FLAG"))
        eligible = (
            ~flags.any(axis=-1)
            & ~columns["FLAG_ROW"][:, None]
            & (columns["ANTENNA1"] != columns["ANTENNA2"])[:, None]
            & np.isfinite(data).all(axis=-1)
            & np.isfinite(columns["WEIGHT_SPECTRUM"]).all(axis=-1)
            & (columns["WEIGHT_SPECTRUM"] > 0).all(axis=-1)
        )
        scalar_model = bool(
            np.isfinite(model).all()
            and np.allclose(model[..., 1:3], 0)
            and np.allclose(model[..., 0], model[..., 3])
        )
        name = f"scan-{metadata[prefix + '/.zattrs']['SCAN_NUMBER']}.npz"
        with (run_dir / name).open("xb") as stream:
            np.savez_compressed(
                stream,
                **columns,
                NATIVE_ROW_INDICES=row_indices,
                NATIVE_CHANNEL_INDICES=np.arange(1024, 1152),
                FREQUENCIES=frequencies,
                **{
                    array.replace("/", "__"): value
                    for array, value in subtables.items()
                },
            )
        groups.append(
            {
                "group": group,
                "scan": metadata[prefix + "/.zattrs"]["SCAN_NUMBER"],
                "shape": list(data.shape),
                "complete_times": times,
                "participating_antennas": n_ant,
                "cell_flag_fraction": float(flags.mean()),
                "flag_row_count": int(columns["FLAG_ROW"].sum()),
                "eligible_cross_correlation_cells": int(eligible.sum()),
                "finite_data_fraction": float(np.isfinite(data).mean()),
                "model_finite_scalar_unpolarized": scalar_model,
                "native_weight_sigma_columns_preserved": [
                    column
                    for column in columns
                    if column.startswith(("WEIGHT", "SIGMA"))
                ],
                "pilot_file": name,
                "pilot_sha256": sha256((run_dir / name).read_bytes()).hexdigest(),
            }
        )
    # Recheck actual acquired bytes after decoding, rather than trust self-report.
    for key, record in records.items():
        if (
            sha256((acquired_dir / "objects" / key).read_bytes()).hexdigest()
            != record["sha256"]
        ):
            raise RuntimeError("raw source changed during offline inspection")
    result = {
        "finished_utc": _now(),
        "acquired_dir": str(acquired_dir),
        "metadata_sha256": METADATA_SHA256,
        "compressed_bytes": complete["bytes"],
        "native_channels": [1024, 1152],
        "frequency_mhz": (frequencies[[0, -1]] / 1e6).tolist(),
        "groups": groups,
        "raw_source_digests_unchanged": True,
        "object_or_pickle_decoding": False,
        "rejected_object_arrays": rejected,
        "status": "numeric pilot only; native-MS conversion/calibration/transfer not run",
        "limits": [
            "Telescope/antenna-name/field/project strings are not decoded",
            "Received flags protected regardless of Observatory/processing origin",
            "Supplied model accuracy and noise-weight convention remain unverified",
            "Separate scans are not separate observations",
        ],
    }
    _json_new(run_dir / "result.json", result)
    return result


def expected_objects_with_headers(expected, recorded):
    """Validate header-only additions without silently accepting schema edits."""
    if len(expected) != len(recorded):
        raise ValueError("acquisition object count changed")
    result = []
    for item, record in zip(expected, recorded):
        size, etag = record.get("compressed_bytes"), record.get("etag")
        if (
            type(size) is not int
            or not 0 < size <= MAX_DECODED_OBJECT_BYTES + 1024**2
            or not isinstance(etag, str)
            or not etag
        ):
            raise ValueError("invalid recorded HTTP source headers")
        result.append({**item, "compressed_bytes": size, "etag": etag})
    return result


def validate_receipt(plan, complete, acquired_dir):
    """Reconcile exact bounded receipts/stat sizes before reading raw payloads."""
    acquired_dir = Path(acquired_dir).resolve()
    objects = plan["objects"]
    total = sum(item["compressed_bytes"] for item in objects)
    if (
        not 0 < total <= MAX_COMPRESSED_BYTES
        or type(complete.get("bytes")) is not int
        or complete["bytes"] != total
        or plan.get("planned_compressed_bytes") != total
    ):
        raise ValueError("acquisition receipt total conflicts with bounded exact plan")
    recorded = complete["objects"]
    records = {record["key"]: record for record in recorded}
    expected_keys = {item["key"] for item in objects}
    if len(records) != len(recorded) or records.keys() != expected_keys:
        raise ValueError("incomplete or duplicate acquired-object manifest")
    for item in objects:
        record = records[item["key"]]
        digest = record.get("sha256", "")
        if (
            type(record.get("bytes")) is not int
            or record["bytes"] != item["compressed_bytes"]
            or record.get("etag") != item["etag"]
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("object receipt conflicts with exact HTTP/source plan")
        path = acquired_dir / "objects" / item["key"]
        if (
            path.is_symlink()
            or not path.resolve().is_relative_to(acquired_dir)
            or path.stat().st_size != item["compressed_bytes"]
        ):
            raise ValueError("raw payload path/size conflicts with bounded receipt")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    acquire_parser = commands.add_parser("acquire")
    acquire_parser.add_argument("run_dir")
    acquire_parser.add_argument("metadata_path")
    acquire_parser.add_argument("--groups", nargs="+", type=int, default=[0, 1])
    inspect_parser = commands.add_parser("inspect")
    inspect_parser.add_argument("run_dir")
    inspect_parser.add_argument("acquired_dir")
    args = parser.parse_args()
    if args.command == "acquire":
        acquire(args.run_dir, args.metadata_path, tuple(args.groups))
    else:
        inspect(args.run_dir, args.acquired_dir)


if __name__ == "__main__":
    main()
