"""E5 final review (research/e5-final.md): fixes outside E2's code paths."""

import pytest
from rang import simtruth_ms


def test_git_facts_are_null_outside_a_checkout(tmp_path, monkeypatch):
    """NEW-13: from a wheel (no .git beside the package) the A1 provenance
    records no commit rather than another repository's, and no git is
    needed."""
    monkeypatch.setattr(simtruth_ms, "ROOT", tmp_path)
    assert simtruth_ms.git_facts() == {"commit": None, "dirty": None}
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("PATH", "")
    assert simtruth_ms.git_facts() == {"commit": None, "dirty": None}


def test_the_tutorial_names_the_receipt_version_the_code_writes():
    """NEW-04: the tutorial's receipt section follows rang.core_cli."""
    import json
    from pathlib import Path

    from rang import core_cli

    path = Path(__file__).resolve().parents[1] / "notebooks" / "00-ms-to-image.ipynb"
    if not path.is_file():
        pytest.skip("the tutorial is in a checkout, not in the sdist")
    book = json.loads(path.read_text(encoding="utf-8"))
    text = "".join("".join(c["source"]) for c in book["cells"])
    assert f"version {core_cli.RECEIPT_VERSION})" in text
