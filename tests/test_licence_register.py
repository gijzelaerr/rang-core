# SPDX-License-Identifier: MIT
"""The provenance register research/results/mit-relicense-audit/files.csv
(research/mit-relicense-audit.md, update 2026-11-26): every tracked source
file under python/rang, core/src, core/py/src, src and tools has a row that
declares its origin, and every row names a tracked file. Own new code is one
row, `<path>,<lines>,a,-,-,-,0,-,-`; derived code names its upstream with
version, the upstream's licence, the derived lines and the pieces.
tools/prepush_check.py runs the same presence check before a push."""

import csv
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "research" / "results" / "mit-relicense-audit" / "files.csv"
DIRS = ("python/rang", "core/src", "core/py/src", "src", "tools")
SUFFIXES = {".py", ".sh", ".rs", ".cc", ".wgsl"}
COLUMNS = [
    "path",
    "lines",
    "class",
    "upstream",
    "licence",
    "upstream_files",
    "derived_lines_est",
    "piece",
    "decision",
]
CLASSES = {"a", "b-permissive", "b-copyleft", "c-src", "c", "d"}
RADLER = {
    "core/src/gemclean/joined.rs",
    "core/src/gemclean/mask.rs",
    "core/src/gemclean/multiscale.rs",
    "core/src/gemclean/stokes.rs",
}


def _rows():
    if not REGISTER.is_file():
        pytest.skip("research/ is not in the sdist")
    with open(REGISTER, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == COLUMNS
        return list(reader)


def _tracked():
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", *DIRS],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [p for p in out if Path(p).suffix in SUFFIXES]


def test_every_source_file_has_a_row_and_every_row_a_file():
    rows = _rows()
    paths = [r["path"] for r in rows]
    assert len(paths) == len(set(paths)), "one row per path"
    tracked = _tracked()
    assert len(tracked) > 400
    assert sorted(set(tracked) - set(paths)) == [], (
        "add a row to research/results/mit-relicense-audit/files.csv "
        "(own new code: <path>,<lines>,a,-,-,-,0,-,-)"
    )
    assert sorted(p for p in paths if not (ROOT / p).is_file()) == []


def test_rows_declare_their_origin():
    for r in _rows():
        p, cls = r["path"], r["class"]
        assert cls in CLASSES, p
        assert int(r["lines"]) >= 0 and int(r["derived_lines_est"]) >= 0, p
        if cls == "a":
            assert r["upstream"] == "-" and r["derived_lines_est"] == "0", p
        elif cls != "c":
            for col in ("upstream", "licence", "upstream_files", "piece"):
                assert r[col] not in ("", "-"), (p, col)


def test_owner_decisions_of_2026_11_26_are_recorded():
    rows = {r["path"]: r for r in _rows()}
    for p in RADLER:
        assert rows[p]["decision"] == "rewrite later (owner 2026-11-26)", p
    refant = rows["python/rang/cal_refant.py"]
    assert "msutils GPL-2.0-or-later" in refant["licence"]


def _prepush():
    spec = importlib.util.spec_from_file_location(
        "prepush_check", ROOT / "tools" / "prepush_check.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_prepush_check_agrees_and_catches_a_new_file():
    rows = _rows()
    tracked = _tracked()
    mod = _prepush()
    assert mod.register_gaps(tracked) == ([], [])
    new = "python/rang/brand_new_module.py"
    missing, gone = mod.register_gaps([*tracked, new, "python/rang/notes.txt"])
    assert missing == [new] and gone == []
    assert len(rows) >= len(tracked)
