"""Offline five-track Stimela2 campaign with independent branch outputs.

Verbatim extract of the frozen `rangtoy.flagging_next` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_next.py at commit
2da566c (now history/python/flagging_next.py),
sha256 2a2ae5ed96229e0d2fca2e5e2dad81b3579b788e92d543ea5718a7a808d69754.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

from hashlib import sha256
from pathlib import Path

from .projector import _native_library


def source_receipts():
    root = Path(__file__).resolve().parents[2]
    paths = list((root / "python/rangtoy").glob("*.py"))
    paths += list((root / "src").glob("*.rs"))
    paths += list((root / "recipes").glob("tv-flagging*.yaml"))
    paths += [
        p
        for p in (root / "tools/flagging").rglob("*")
        if p.is_file()
        and (p.suffix in (".py", ".sh", ".txt") or p.name == "Dockerfile")
    ]
    paths += [root / name for name in ("Cargo.toml", "Cargo.lock", "pyproject.toml")]
    paths.append(Path(_native_library()._name).resolve())
    return {str(p): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
