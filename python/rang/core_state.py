"""Recoverable real-MS experiment, exposed as Stimela2 Python callable cabs.

Verbatim extract of the frozen `rangtoy.flagging_workflow` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_workflow.py at commit
2da566c (now history/python/flagging_workflow.py),
sha256 137daffae931fd80a6d8d743ca20fabb39ed9a97c8dfb2a7405838a65941391a.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import json
from hashlib import sha256
from pathlib import Path

import numpy as np


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def tree_digest(path):
    """Hash every original file except casacore's transient lock bookkeeping."""
    digest = sha256()
    for file in sorted(Path(path).rglob("*")):
        if file.is_file() and file.name != "table.lock":
            digest.update(str(file.relative_to(path)).encode())
            with file.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
    return digest.hexdigest()


def load_state(run_dir):
    with np.load(Path(run_dir) / "state.npz", allow_pickle=False) as saved:
        return {key: saved[key] for key in saved.files}
