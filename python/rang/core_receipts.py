# SPDX-License-Identifier: GPL-3.0-or-later
"""SHA256 receipts of the code a run used (`source_receipts`).

Until task W4-1 this module was the P11 extract of the frozen
`rangtoy.flagging_next` (research/p11-extract.md; the history copy is
history/python/flagging_next.py). Its globs assumed a checkout: an installed
wheel raised FileNotFoundError on `Cargo.lock`, and the recipe and
`tools/flagging` globs matched nothing after P8 moved those files to
`history/` (research/w4-review.md, W4R-02). Now, in a checkout (the three
manifests of `core.checkout_root`), the receipts cover what they covered
on disk before (`python/rang/*.py`, `src/*.rs`, the root manifests and the
loaded extension); outside one, every file of the installed package and
the extension. The CLI receipt format (`rang.receipt`, version 3 since
W4-1) is `core_cli`'s, not this module's.
"""

from hashlib import sha256
from pathlib import Path

from .core import MANIFESTS
from .projector import _native_library


def _package_files(package):
    return [
        p
        for p in package.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    ]


def source_receipts():
    """{path: SHA256} of the running code: a checkout's Python modules, root
    Rust sources and manifests, or an installed package's files; and the
    native library actually loaded."""
    package = Path(__file__).resolve().parent
    root = package.parents[1]
    if all((root / name).is_file() for name in MANIFESTS):
        paths = list((root / "python/rang").glob("*.py"))
        paths += list((root / "src").glob("*.rs"))
        paths += [
            root / name
            for name in ("Cargo.toml", "Cargo.lock", "pyproject.toml")
            if (root / name).is_file()
        ]
    else:
        paths = _package_files(package)
    paths.append(Path(_native_library()._name).resolve())
    return {str(p): sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}
