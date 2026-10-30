"""Compare the Rust Measurement Set reader with the python-casacore oracle.

Usage:
    python examples/check_ms_reader.py <oracle-dir> outputs/<fresh-check-dir>
    python examples/check_ms_reader.py --self-check <oracle-dir-1> <oracle-dir-2> outputs/<fresh-check-dir>

The first form opens every table of the oracle receipt with
`rang.core_ms`, reads every oracle column in full and in two row ranges,
and compares column-exactly (dtype, shape and bytes; strings by value). It
also checks that the MS tree is unchanged by hashing it before and after and
records every read's wall time. The second form is the comparator
precondition of `research/core-e-ms-reader.md`: it compares two oracle dumps
of the same tables with the same comparator and then a perturbed copy of
the second, which must fail. Both write `result.json` into the fresh check
directory; the process exits non-zero when a gated criterion fails.
"""

import json
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RANGES = ((0, 1), (3, 5))


def file_hashes(ms):
    return {
        p.relative_to(ms).as_posix(): sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path(ms).rglob("*"))
        if p.is_file() and p.name != "table.lock"
    }


def load_oracle(oracle_dir, label):
    arrays = dict(np.load(Path(oracle_dir) / f"{label}.npz"))
    strings = json.loads((Path(oracle_dir) / f"{label}.strings.json").read_text())
    return arrays, strings


def compare_arrays(name, expected, actual):
    """Column-exact comparison: dtype, shape and the bytes themselves."""
    expected = np.asarray(expected)
    actual = np.asarray(actual)
    if expected.dtype != actual.dtype:
        return f"{name}: dtype {actual.dtype} != {expected.dtype}"
    if expected.shape != actual.shape:
        return f"{name}: shape {actual.shape} != {expected.shape}"
    e = np.ascontiguousarray(expected).view(np.uint8)
    a = np.ascontiguousarray(actual).view(np.uint8)
    if not np.array_equal(e, a):
        bad = int(np.count_nonzero(e != a))
        return f"{name}: {bad} of {e.size} bytes differ"
    return None


def compare_strings(name, expected, actual):
    if list(map(list, np.asarray(expected, dtype=object).reshape(-1, 1))) != list(
        map(list, np.asarray(actual, dtype=object).reshape(-1, 1))
    ):
        return f"{name}: strings differ"
    if (
        np.asarray(expected, dtype=object).shape
        != np.asarray(actual, dtype=object).shape
    ):
        return f"{name}: string shape differs"
    return None


def compare_table(expected, actual):
    """Compare (arrays, strings) pairs; returns the list of failures."""
    failures = []
    e_arrays, e_strings = expected
    a_arrays, a_strings = actual
    for name, value in e_arrays.items():
        if name not in a_arrays:
            failures.append(f"{name}: missing")
            continue
        error = compare_arrays(name, value, a_arrays[name])
        if error:
            failures.append(error)
    for name, value in e_strings.items():
        if name not in a_strings:
            failures.append(f"{name}: missing")
            continue
        error = compare_strings(name, value, a_strings[name])
        if error:
            failures.append(error)
    return failures


def read_with_core(path, columns, start, count, timings):
    from rang import core_ms

    arrays, strings = {}, {}
    with core_ms.open_table(path) as t:
        for name in columns:
            started = time.perf_counter()
            value = t.getcol(name, start, count)
            timings.append(
                (str(path), name, start, count, time.perf_counter() - started)
            )
            if isinstance(value, np.ndarray) and value.dtype.kind not in "OU":
                arrays[name] = value
            else:
                strings[name] = np.asarray(value, dtype=object).tolist()
    return arrays, strings


def check_against_core(oracle_dir, out):
    receipt = json.loads((Path(oracle_dir) / "receipt.json").read_text())
    result = {"oracle": str(oracle_dir), "tables": {}, "timings": [], "criteria": {}}
    full_failures, range_failures, tree_failures = [], [], []
    timings = []
    for label, entry in receipt["tables"].items():
        path = Path(entry["path"])
        if not path.is_absolute() or not path.exists():
            # Oracle paths are container paths: map /outputs to the repository outputs.
            path = ROOT / "outputs" / Path(*path.parts[2:])
        before = file_hashes(path) if "." not in label else None
        expected = load_oracle(oracle_dir, label)
        columns = [c for c in entry["columns"] if "error" not in entry["columns"][c]]
        actual = read_with_core(path, columns, 0, None, timings)
        failures = compare_table(expected, actual)
        full_failures += [f"{label}: {f}" for f in failures]
        nrows = entry["nrows"]
        for start, count in RANGES:
            if start + count > nrows:
                continue
            sliced = (
                {k: v[start : start + count] for k, v in expected[0].items()},
                {k: v[start : start + count] for k, v in expected[1].items()},
            )
            actual = read_with_core(path, columns, start, count, timings)
            failures = compare_table(sliced, actual)
            range_failures += [
                f"{label}[{start}:{start + count}]: {f}" for f in failures
            ]
        if before is not None:
            after = file_hashes(path)
            if before != after:
                tree_failures.append(label)
            if before != entry["ms_file_sha256"]:
                tree_failures.append(f"{label}: tree differs from the oracle's")
        result["tables"][label] = {
            "path": str(path),
            "columns": columns,
            "nrows": nrows,
        }
    result["timings"] = [
        {"table": t, "column": c, "start": s, "count": n, "seconds": sec}
        for t, c, s, n, sec in timings
    ]
    result["criteria"] = {
        "1_full_columns_exact": {
            "passed": not full_failures,
            "failures": full_failures,
        },
        "2_row_ranges_exact": {
            "passed": not range_failures,
            "failures": range_failures,
        },
        "3_tree_unchanged": {"passed": not tree_failures, "failures": tree_failures},
    }
    return result


def self_check(oracle_1, oracle_2, out):
    receipt = json.loads((Path(oracle_1) / "receipt.json").read_text())
    same, perturbed = [], []
    for label in receipt["tables"]:
        a = load_oracle(oracle_1, label)
        b = load_oracle(oracle_2, label)
        same += [f"{label}: {f}" for f in compare_table(a, b)]
        # Perturb one byte of every array and one character of every string.
        arrays = {k: v.copy() for k, v in b[0].items()}
        strings = {k: json.loads(json.dumps(v)) for k, v in b[1].items()}
        for k, v in arrays.items():
            flat = v.view(np.uint8).reshape(-1)
            flat[len(flat) // 2] ^= 0x01
        for k, v in strings.items():
            flat = np.asarray(v, dtype=object).reshape(-1)
            flat[0] = str(flat[0]) + "x"
            strings[k] = flat.reshape(np.asarray(v, dtype=object).shape).tolist()
        failures = compare_table(a, (arrays, strings))
        expected = len(a[0]) + len(a[1])
        if len(failures) != expected:
            perturbed.append(
                f"{label}: {len(failures)} of {expected} perturbations caught"
            )
    return {
        "oracle_1": str(oracle_1),
        "oracle_2": str(oracle_2),
        "criteria": {
            "same_dumps_equal": {"passed": not same, "failures": same},
            "perturbed_dumps_fail": {"passed": not perturbed, "failures": perturbed},
        },
    }


def main():
    args = sys.argv[1:]
    if args and args[0] == "--self-check":
        out = Path(args[3])
        out.mkdir(parents=True, exist_ok=False)
        result = self_check(args[1], args[2], out)
    else:
        out = Path(args[1])
        out.mkdir(parents=True, exist_ok=False)
        result = check_against_core(args[0], out)
    passed = all(c["passed"] for c in result["criteria"].values())
    result["passed"] = passed
    (out / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    for name, criterion in result["criteria"].items():
        print(
            name, "PASS" if criterion["passed"] else "FAIL", criterion["failures"][:5]
        )
    print("overall", "PASS" if passed else "FAIL")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
