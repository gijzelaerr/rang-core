"""Five-track dispatch/schema/boundary contracts, without external operations.

Live part of tests/test_flagging_next.py at commit 2da566c
(now history/tests/test_flagging_next.py,
sha256 30db4c72fb189c1dc67be7fb0d50c501ca8444bb0ca81c2551ef27e36a9f9551):
the test functions that use only extracted names, with the helpers they
use, copied verbatim in source order; only import statements point at
the extracts (big plan task P11, research/p11-extract.md).
"""

from hashlib import sha256
from types import SimpleNamespace

from rang import core_receipts as campaign


def test_source_receipts_cover_modules_rust_recipes_and_actual_native_file(
    tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    files = {
        "python/rang/flagging_next.py": b"campaign",
        "python/rang/flagging_signal_guard.py": b"signal",
        "src/lib.rs": b"Rust",
        "recipes/tv-flagging-next.yaml": b"recipe",
        "recipes/unrelated.yaml": b"not a flagging recipe",
        "Cargo.toml": b"manifest",
        "Cargo.lock": b"lock",
        "pyproject.toml": b"python manifest",
        "tools/flagging/run-next.sh": b"wrapper",
        "tools/flagging/Dockerfile": b"base image",
        "tools/flagging/next/Dockerfile": b"suite image",
        "tools/flagging/requirements.lock.txt": b"dependencies",
        "tools/flagging/next/helper.py": b"entrypoint",
        "tools/flagging/unrelated.bin": b"not source",
        "native/lib.so": b"native",
    }
    for name, value in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    monkeypatch.setattr(
        campaign, "__file__", str(root / "python/rang/flagging_next.py")
    )
    monkeypatch.setattr(
        campaign,
        "_native_library",
        lambda: SimpleNamespace(_name=str(root / "native/lib.so")),
    )
    receipts = campaign.source_receipts()
    assert str(root / "recipes/unrelated.yaml") not in receipts
    assert str(root / "tools/flagging/unrelated.bin") not in receipts
    assert set(receipts) == {
        str(root / name)
        for name in files
        if name not in ("recipes/unrelated.yaml", "tools/flagging/unrelated.bin")
    }
    assert receipts[str(root / "native/lib.so")] == sha256(b"native").hexdigest()
    (root / "native/lib.so").write_bytes(b"changed")
    assert campaign.source_receipts() != receipts
