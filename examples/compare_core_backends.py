"""Compare two `tools/core-j-suite.sh` output directories file by file
(research/core-j-packaging.md, criterion 6).

    python examples/compare_core_backends.py REFERENCE CANDIDATE RECEIPT.json [IGNORE,...]

Every `.npz` and `.npy` array must be byte-equal, every FITS image's data
and header cards equal, every other file byte-equal, and every JSON leaf
equal except under the volatile keys listed in VOLATILE (wall times, memory,
dates, library and code hashes, interpreter and backend names, load) and
except strings that name the same file under the two run directories; both
are counted and reported. Logs, `.time` files and `timings.tsv`
are skipped, as are the top-level entries named in the optional
comma-separated IGNORE list; symbolic links are not followed. Exit status 1
on any difference or missing file.
"""

import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

VOLATILE = {
    "seconds",
    "seconds_total",
    "core_seconds",
    "wall",
    "wall_seconds",
    "wall_seconds_excluding_decode",
    "wall_excluding_decode",
    "process_wall_seconds",
    "decode_seconds",
    "load_seconds",
    "solve_seconds",
    "fused_seconds",
    "step_seconds",
    "timings",
    "timing",
    "read_seconds",
    "ms_read_seconds",
    "elapsed",
    "started",
    "finished",
    "date",
    "max_rss_mb",
    "max_rss_mb_self",
    "process_max_rss_mb",
    "self_maxrss_mb",
    "peak_rss_mb",
    "cost",
    "library_sha256",
    "core_library_sha256",
    "code_sha256",
    "module_sha256",
    "rang_core_lib",
    "rang_core_backend",
    "executable",
    "python",
    "python_version",
    "platform",
    "hostname",
    "load",
    "run",
    "run_dir",
    "output",
    "candidate",
    "reference",
    "receipt",
    "artifact_directory",
    "git_status_unchanged",
}
SKIP_SUFFIXES = {".log", ".time", ".tsv"}


def leaves(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, path + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from leaves(item, path + (index,))
    else:
        yield path, value


def run_path(a, b, roots):
    """Both strings name the same file under their own run directory."""
    return (
        isinstance(a, str)
        and isinstance(b, str)
        and a != b
        and a.replace(roots[0], "<run>") == b.replace(roots[1], "<run>")
    )


def equal_leaf(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return (math.isnan(a) and math.isnan(b)) or a == b
    return a == b


def compare_json(ref, cand, record, roots=("", "")):
    a = json.loads(ref.read_text())
    b = json.loads(cand.read_text())
    ours = dict(leaves(a))
    theirs = dict(leaves(b))
    failures = []
    for path in sorted(set(ours) | set(theirs), key=str):
        keys = [p for p in path if isinstance(p, str)]
        volatile = next((k for k in keys if k in VOLATILE), None)
        if volatile is not None:
            record["volatile"][volatile] += 1
            continue
        if path not in ours or path not in theirs:
            failures.append(f"{'/'.join(map(str, path))}: missing on one side")
        elif run_path(ours[path], theirs[path], roots):
            record["volatile"]["<run path>"] += 1
        elif not equal_leaf(ours[path], theirs[path]):
            failures.append(
                f"{'/'.join(map(str, path))}: {ours[path]!r} != {theirs[path]!r}"
            )
        else:
            record["json_leaves"] += 1
    return failures


def compare_arrays(ref, cand, record):
    failures = []
    if ref.suffix == ".npy":
        pairs = [
            ("", np.load(ref, allow_pickle=False), np.load(cand, allow_pickle=False))
        ]
    else:
        with (
            np.load(ref, allow_pickle=False) as a,
            np.load(cand, allow_pickle=False) as b,
        ):
            if set(a.files) != set(b.files):
                return [f"{ref}: keys {sorted(a.files)} != {sorted(b.files)}"]
            pairs = [(k, a[k], b[k]) for k in a.files]
    for key, x, y in pairs:
        if x.dtype != y.dtype or x.shape != y.shape or x.tobytes() != y.tobytes():
            failures.append(f"{ref}:{key}: arrays differ")
        else:
            record["arrays"] += 1
    return failures


def compare_fits(ref, cand, record):
    from astropy.io import fits

    failures = []
    with fits.open(ref) as a, fits.open(cand) as b:
        if len(a) != len(b):
            return [f"{ref}: HDU count differs"]
        for i, (x, y) in enumerate(zip(a, b)):
            if x.header.tostring() != y.header.tostring():
                failures.append(f"{ref}[{i}]: header cards differ")
            if (x.data is None) != (y.data is None) or (
                x.data is not None
                and np.asarray(x.data).tobytes() != np.asarray(y.data).tobytes()
            ):
                failures.append(f"{ref}[{i}]: pixel data differ")
            if not failures:
                record["fits_hdus"] += 1
    return failures


def files(root, ignore=()):
    out = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if rel.parts[0] in ignore:
            continue
        if any((root / parent).is_symlink() for parent in rel.parents):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        out.append(rel)
    return out


def main(reference, candidate, receipt, ignore=""):
    reference, candidate = Path(reference), Path(candidate)
    ignore = tuple(x for x in ignore.split(",") if x)
    record = {
        "reference": str(reference),
        "candidate": str(candidate),
        "ignored": list(ignore),
        "files": 0,
        "json_leaves": 0,
        "arrays": 0,
        "fits_hdus": 0,
        "bytes_equal_files": 0,
        "volatile": Counter(),
        "failures": [],
    }
    ours, theirs = set(files(reference, ignore)), set(files(candidate, ignore))
    for rel in sorted(ours ^ theirs):
        record["failures"].append(
            f"{rel}: only in {'reference' if rel in ours else 'candidate'}"
        )
    for rel in sorted(ours & theirs):
        ref, cand = reference / rel, candidate / rel
        record["files"] += 1
        if rel.suffix == ".json":
            record["failures"] += compare_json(
                ref, cand, record, (str(reference), str(candidate))
            )
        elif rel.suffix in (".npz", ".npy"):
            record["failures"] += compare_arrays(ref, cand, record)
        elif rel.suffix == ".fits":
            record["failures"] += compare_fits(ref, cand, record)
        elif ref.read_bytes() == cand.read_bytes():
            record["bytes_equal_files"] += 1
        else:
            record["failures"].append(f"{rel}: bytes differ")
    record["volatile"] = dict(sorted(record["volatile"].items()))
    record["pass"] = not record["failures"]
    Path(receipt).write_text(json.dumps(record, indent=1) + "\n")
    summary = {k: v for k, v in record.items() if k not in ("failures", "volatile")}
    print(json.dumps(summary, indent=1))
    print("volatile keys skipped:", record["volatile"])
    for failure in record["failures"][:40]:
        print("FAIL", failure)
    return 0 if record["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
