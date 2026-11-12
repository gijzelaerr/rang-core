"""E5 final review (research/e5-final.md): its fixes."""

import sys

import numpy as np
import pytest
from rang import core_ms, simtruth_ms
from rang import core_writeback as wb
from test_g8_gemclean import SMALL, run, tiny_ms


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


def _columns(ms):
    with core_ms.open_table(str(ms)) as t:
        return {c: t.getcol(c) for c in t.colnames() if c.endswith("DATA")}


def test_gemclean_never_writes_data_or_the_column_it_images(tmp_path):
    """E5-02: `-model-column DATA`, or the column being imaged, explicit or
    chosen at run time (CORRECTED_DATA when the MS has it), is refused with
    exit 2 and a message naming the option, before anything is written."""
    ms = tiny_ms(tmp_path / "x.ms")
    with wb.WriteBack(ms, stage="test") as w:
        w.ensure_column("CORRECTED_DATA", init="data")
    before = _columns(ms)
    update = [o for o in SMALL if o != "-no-update-model-required"]
    auto = [
        o
        for i, o in enumerate(update)
        if o != "-data-column" and update[i - 1] != "-data-column"
    ]
    gemclean = [sys.executable, "-m", "rang.gemclean", "-name", tmp_path / "g"]
    for opts in (
        [*update, "-model-column", "DATA"],
        [*auto, "-model-column", "DATA"],
        [*auto, "-data-column", "CORRECTED_DATA", "-model-column", "CORRECTED_DATA"],
        [*auto, "-model-column", "CORRECTED_DATA"],  # chosen at run time
    ):
        out = run([*gemclean, *opts, ms])
        assert out.returncode == 2, (opts, out.stdout, out.stderr)
        assert out.stderr.startswith("gemclean: -model-column "), out.stderr
        assert not (tmp_path / "g-image.fits").exists()
    after = _columns(ms)
    assert after.keys() == before.keys()
    for c in before:
        np.testing.assert_array_equal(after[c], before[c], err_msg=c)
    # The default model column still works and leaves DATA alone.
    out = run([*gemclean, *auto, ms])
    assert out.returncode == 0, out.stdout + out.stderr
    after = _columns(ms)
    np.testing.assert_array_equal(after["DATA"], before["DATA"])
    assert "MODEL_DATA" in after and np.abs(after["MODEL_DATA"]).max() > 0
