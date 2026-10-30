"""Smoke test of the installed wheel (tools/wheel/test.sh, step nocargo).

Checks that rang and its extension come from site-packages, that the
extension backend is chosen without RANG_CORE_BACKEND, and runs one fused
pass; prints the import times and the extension's sha256.
"""

import hashlib
import os
import shutil
import sys
import sysconfig
import time
from pathlib import Path

start = time.perf_counter()
import numpy as np

numpy_seconds = time.perf_counter() - start
start = time.perf_counter()
import rang._core  # noqa: F401
from rang import core

import_seconds = time.perf_counter() - start

site = Path(sysconfig.get_paths()["purelib"]).resolve()
assert shutil.which("cargo") is None, "cargo is on PATH"
assert "RANG_CORE_BACKEND" not in os.environ and "RANG_CORE_LIB" not in os.environ
assert Path(core.__file__).resolve().is_relative_to(site), core.__file__
assert core.backend_name() == "extension", core.backend_name()
library = core.library_path()
assert library.is_relative_to(site), library

rng = np.random.default_rng(0)
pairs = [(0, 1), (0, 2), (1, 2)]
nrow, nchan = len(pairs) * 2, 4
shape = (nrow, nchan, 4)
data = (rng.standard_normal(shape) + 1j * rng.standard_normal(shape)).astype(
    np.complex64
)
start = time.perf_counter()
result = core.fused_pass(
    data,
    np.ones(shape, np.float32),
    np.tile([p for p, _ in pairs], 2),
    np.tile([q for _, q in pairs], 2),
    np.repeat([0, 1], len(pairs)),
    np.zeros(nchan, np.int32),
    np.tile(np.eye(2, dtype=np.complex128), (2, 1, 3, 1, 1)),
    np.ones((2, 1, 3), bool),
    np.ones((nrow, nchan), np.uint8),
    model=np.ones(shape, np.complex64),
)
call_seconds = time.perf_counter() - start
assert result.residuals is not None and np.isfinite(result.residuals).all()
print(
    f"python {sys.version.split()[0]} backend {core.backend_name()} "
    f"library {library} sha256 {hashlib.sha256(library.read_bytes()).hexdigest()} "
    f"numpy {np.__version__} import_numpy {numpy_seconds:.3f} s "
    f"import_rang {import_seconds:.3f} s first_fused {call_seconds * 1e3:.2f} ms"
)
