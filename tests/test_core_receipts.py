"""`core_receipts.source_receipts` in a checkout and in an installed package.

The first test began as the live part of tests/test_flagging_next.py at
commit 2da566c (now history/tests/test_flagging_next.py, big plan task P11,
research/p11-extract.md). Task W4-1 (research/w4-1-receipts.md) made
`core_receipts` a live module: a checkout is recognised by its three
manifests, the recipe and `tools/flagging` globs that matched nothing since
P8 are gone, and outside a checkout every file of the installed package is
hashed instead of raising FileNotFoundError.
"""

from hashlib import sha256
from types import SimpleNamespace

from rang import core_receipts as campaign


def _tree(root, files, monkeypatch, module):
    for name, value in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    monkeypatch.setattr(campaign, "__file__", str(root / module))
    monkeypatch.setattr(
        campaign,
        "_native_library",
        lambda: SimpleNamespace(_name=str(root / "native/lib.so")),
    )


def test_source_receipts_cover_modules_rust_manifests_and_actual_native_file(
    tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    files = {
        "python/rang/flagging_next.py": b"campaign",
        "python/rang/flagging_signal_guard.py": b"signal",
        "src/lib.rs": b"Rust",
        "recipes/tv-flagging-next.yaml": b"recipe (moved to history/ by P8)",
        "Cargo.toml": b"manifest",
        "Cargo.lock": b"lock",
        "pyproject.toml": b"python manifest",
        "core/Cargo.toml": b"core manifest",
        "tools/flagging/run-next.sh": b"wrapper (moved to history/ by P8)",
        "native/lib.so": b"native",
    }
    _tree(root, files, monkeypatch, "python/rang/flagging_next.py")
    receipts = campaign.source_receipts()
    assert set(receipts) == {
        str(root / name)
        for name in (
            "python/rang/flagging_next.py",
            "python/rang/flagging_signal_guard.py",
            "src/lib.rs",
            "Cargo.toml",
            "Cargo.lock",
            "pyproject.toml",
            "native/lib.so",
        )
    }
    assert receipts[str(root / "native/lib.so")] == sha256(b"native").hexdigest()
    (root / "native/lib.so").write_bytes(b"changed")
    assert campaign.source_receipts() != receipts


def test_source_receipts_hash_the_installed_package_outside_a_checkout(
    tmp_path, monkeypatch
):
    # A wheel's layout: parents[2] of the module is lib/python3.X, which holds
    # no manifests (W4R-02 found FileNotFoundError on its Cargo.lock).
    site = tmp_path / "venv/lib/python3.14/site-packages"
    files = {
        "rang/__init__.py": b"package",
        "rang/core_receipts.py": b"this module",
        "rang/data/mask.txt": b"package data",
        "rang/__pycache__/core.cpython-314.pyc": b"bytecode",
        "native/lib.so": b"native",
    }
    _tree(site, files, monkeypatch, "rang/core_receipts.py")
    receipts = campaign.source_receipts()
    assert set(receipts) == {
        str(site / name)
        for name in (
            "rang/__init__.py",
            "rang/core_receipts.py",
            "rang/data/mask.txt",
            "native/lib.so",
        )
    }
    assert (
        receipts[str(site / "rang/data/mask.txt")]
        == sha256(b"package data").hexdigest()
    )
