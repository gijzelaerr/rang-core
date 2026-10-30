"""Classify py-spy raw (collapsed) stacks into Rust / NumPy / I/O / Python glue.

Usage: python classify.py <raw.txt> [<raw.txt> ...] > summary.json

Each sample is assigned by walking from the leaf towards the root and taking
the first frame that matches a category:
  rust    frames from _core.abi3.so, librang_core.so, librang_toy.so or with
          rang_core:: / rang_toy:: symbols
  io      read/write/open/stat/fsync/mmap syscalls in libc, hashlib/libcrypto
          (SHA256 receipts), zlib/zipfile (npz), json encode/decode
  numpy   numpy/openblas/lapack native frames or numpy/*.py frames
  python  everything else (interpreter, rangtoy and stdlib Python frames)
Also reports the top leaf-most rangtoy Python functions and Rust symbols.
"""

import json
import re
import sys
from collections import Counter

RUST = re.compile(r"(_core\.abi3\.so|librang_core|librang_toy|rang_core::|rang_toy::)")
IO = re.compile(
    r"(\b(__libc_)?(read|pread64|write|pwrite64|open|openat|__open64|fstat|stat|statx|lstat|newfstatat|fsync|mmap|munmap|getdents64|close|readlink)\b"
    r"|_hashlib|libcrypto|sha256|SHA256|hashlib\.py|file_sha256|zlib|zipfile|_io\b|\(io\.py|_bootstrap_external|json/encoder|json/decoder|_json|pathlib|rglob|scandir|os\.py|shutil\.py|_stat)"
)
NUMPY = re.compile(r"(numpy/|_multiarray_umath|libopenblas|libscipy_openblas|lapack|_umath_linalg|libgfortran)")


IMPORT = re.compile(r"(<frozen importlib|_find_and_load|exec_module|create_module)")


def classify(frames):
    if any(IMPORT.search(f) for f in frames):
        return "import"
    for f in reversed(frames):
        if RUST.search(f):
            return "rust"
        if IO.search(f):
            return "io"
        if NUMPY.search(f):
            return "numpy"
    return "python"


def main():
    out = {}
    for path in sys.argv[1:]:
        cats = Counter()
        rust_syms = Counter()
        py_funcs = Counter()
        io_leaf = Counter()
        np_leaf = Counter()
        total = 0
        for line in open(path):
            line = line.rstrip("\n")
            if not line:
                continue
            stack, _, count = line.rpartition(" ")
            n = int(count)
            frames = stack.split(";")
            total += n
            cat = classify(frames)
            cats[cat] += n
            for f in reversed(frames):
                if RUST.search(f):
                    rust_syms[re.sub(r"\s*\(.*\)$", "", f)[:120]] += n
                    break
            for f in reversed(frames):
                if ".py:" in f and "rangtoy" in f or "examples/" in f or "s1_profile" in f:
                    py_funcs[f[:140]] += n
                    break
            if cat == "io":
                for f in reversed(frames):
                    if IO.search(f):
                        io_leaf[f[:120]] += n
                        break
            if cat == "numpy":
                for f in reversed(frames):
                    if ".py:" in f and "numpy" not in f:
                        np_leaf[f[:140]] += n
                        break
        out[path.split("/")[-1]] = {
            "samples": total,
            "fractions": {k: round(v / total, 4) for k, v in cats.most_common()},
            "top_rust_symbols": [[k, round(v / total, 4)] for k, v in rust_syms.most_common(12)],
            "top_rangtoy_python_frames": [[k, round(v / total, 4)] for k, v in py_funcs.most_common(15)],
            "top_io_frames": [[k, round(v / total, 4)] for k, v in io_leaf.most_common(8)],
            "numpy_callers": [[k, round(v / total, 4)] for k, v in np_leaf.most_common(8)],
        }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
