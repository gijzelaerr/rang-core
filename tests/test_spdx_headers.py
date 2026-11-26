# SPDX-License-Identifier: MIT
"""Every source file carries an SPDX licence line (E5-45, CONTRIBUTING.md
"Licence headers"), and that line matches the file's provenance class
(research/mit-relicense-audit.md, "Step 1 done: own code MIT"): ra-ng's own
code is MIT, code translated from a permissive upstream is `MIT AND` that
licence, and code derived from GPL or LGPL upstreams keeps its GPL line.

The checked-in list is research/results/mit-relicense-audit/spdx.csv, written
by spdx.py beside it from the audit's files.csv. A file not in the list passes
if its line is bare `MIT` (new own code is MIT); with any other line it fails
until it is added to spdx.py's HELD with its class and spdx.py is rerun."""

import csv
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "research" / "results" / "mit-relicense-audit"
DIRS = ("python/rang", "core/src", "src", "tools")
SUFFIXES = {".py": "#", ".sh": "#", ".rs": "//", ".cc": "//"}
EXPR = r"[A-Za-z0-9.+-]+(?: (?:AND|OR|WITH) [A-Za-z0-9.+-]+)*"
LINE = re.compile(rf"SPDX-License-Identifier: ({EXPR})")
# Files another task is changing when the headers go in; stamp them once it
# merges. Empty since sliced-read merged (E5 final).
PENDING: set[str] = set()
OWN = {"a", "c"}
# Classes whose code follows GPL or LGPL upstream code or source: never MIT.
COPYLEFT = {"b-copyleft", "c-src", "d"}
PERMISSIVE = {"MIT", "BSD-3-Clause"}


def _git(*args):
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout


def _tracked():
    out = _git("ls-files", *DIRS)
    return [p for p in out.split() if Path(p).suffix in SUFFIXES]


def _expression(path):
    """The licence expression of `path`'s SPDX line (first three lines)."""
    with open(ROOT / path, "rb") as fh:
        head = fh.read(4096).split(b"\n")[:3]
    m = LINE.search(b"\n".join(head).decode("utf-8", "replace"))
    return m.group(1) if m else None


def _header(path):
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()[:3]
    comment = SUFFIXES[Path(path).suffix]
    for line in lines:
        if line.startswith(comment) and LINE.search(line):
            return line
    return None


def _csv(name):
    path = AUDIT / name
    if not path.is_file():
        pytest.skip("research/ is not in the sdist")
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["path"]: r for r in csv.DictReader(fh)}


def test_every_source_file_has_an_spdx_line():
    files = _tracked()
    assert len(files) > 200
    missing = [p for p in files if p not in PENDING and _header(p) is None]
    assert missing == []


def test_every_spdx_line_is_listed_and_matches_its_class():
    listed = _csv("spdx.csv")
    found = {}
    for p in _git("ls-files").splitlines():
        if Path(p).suffix in {".md", ".txt", ".csv", ".json"}:
            continue
        if (ROOT / p).is_file():
            expr = _expression(p)
            if expr is not None:
                found[p] = expr
    unlisted = sorted(p for p in set(found) - set(listed) if found[p] != "MIT")
    assert unlisted == [], (
        "not bare MIT: add each to HELD with its class in "
        "research/results/mit-relicense-audit/spdx.py and rerun it"
    )
    assert sorted(set(listed) - set(found)) == []
    wrong = {
        p: (found[p], r["spdx"]) for p, r in listed.items() if found[p] != r["spdx"]
    }
    assert wrong == {}
    for p, r in listed.items():
        cls, expr = r["class"], r["spdx"]
        terms = expr.split(" AND ")
        if cls in OWN:
            assert expr == "MIT", p
        elif cls == "b-permissive":
            assert terms[0] == "MIT" and set(terms) <= PERMISSIVE, p
        else:
            assert cls in COPYLEFT, (p, cls)
            assert any("GPL" in t for t in terms), p
            assert terms[0] != "MIT", p


def _on_disk(path):
    return _expression(path) if (ROOT / path).is_file() else None


def _bare_mit_derived(audit, expression):
    """Paths the audit marks derived (GPL/LGPL code or source, or a non-MIT
    permissive upstream) whose SPDX expression is a bare `MIT`."""
    derived = [
        p
        for p, r in audit.items()
        if r["class"] in COPYLEFT
        or (r["class"] == "b-permissive" and r["licence"] != "MIT")
    ]
    assert len(derived) > 60
    return [p for p in derived if expression(p) == "MIT"]


def test_no_derived_file_is_bare_mit():
    """A file the audit marks derived never carries a bare `MIT` line."""
    audit = _csv("files.csv")
    assert _bare_mit_derived(audit, _on_disk) == []


def test_a_bare_mit_on_a_derived_file_fails():
    """The check above catches a deliberate bare `MIT` on a derived file, both
    in the audit's list and for a file spdx.csv lists."""
    audit = _csv("files.csv")
    listed = _csv("spdx.csv")
    fake = {"core/src/ism.rs": "MIT", "tests/test_e0_refant_extend.py": "MIT"}

    def found(p):
        return fake[p] if p in fake else _on_disk(p)

    assert sorted(_bare_mit_derived(audit, found)) == sorted(fake)
    for p, expr in fake.items():
        assert listed[p]["class"] in COPYLEFT and listed[p]["spdx"] != expr


def test_ported_files_name_the_upstream_licence_too():
    """docs/licence.md: ported code keeps its upstream licence and notice."""
    for path, expr in {
        "core/src/predict.rs": "MIT AND BSD-3-Clause",
        "core/src/sumthreshold.rs": "MIT AND BSD-3-Clause",
        # oxkat 421d14c5 RFI lists (GPL-3.0), class d (audit update 2026-11-26).
        "python/rang/meerkat.py": "GPL-3.0-or-later AND BSD-3-Clause",
        "core/src/blosc.rs": "MIT AND BSD-3-Clause",
        "python/rang/core_flag.py": "MIT AND BSD-3-Clause",
        # B-02 (research/v030-review.md): radler 76fe4474 is LGPL-3.0-only.
        "core/src/gemclean/mask.rs": "GPL-3.0-or-later AND LGPL-3.0-only",
        "core/src/gemclean/joined.rs": "GPL-3.0-or-later AND LGPL-3.0-only",
        "core/src/gemclean/multiscale.rs": "GPL-3.0-or-later AND LGPL-3.0-only",
        "core/src/gemclean/stokes.rs": "GPL-3.0-or-later AND LGPL-3.0-only",
        # research/mit-relicense-audit.md section 3.2.
        "python/rang/formats/sky.py": "GPL-3.0-or-later AND BSD-3-Clause",
        "core/src/gpu/shader.rs": "GPL-3.0-or-later AND SunPro",
        "core/src/cal/diag.rs": "GPL-3.0-or-later AND MIT",
    }.items():
        if not (ROOT / path).is_file():
            pytest.skip("not a checkout")
        assert _expression(path) == expr, path


def test_quartical_translations_keep_the_mit_notice():
    """QuartiCal is MIT, so its translations are `MIT` alone; the notice stays."""
    for path in (
        "core/src/solve.rs",
        "core/src/cal/delay.rs",
        "core/src/cal/delay_offset.rs",
        "core/src/cal/diag_dd.rs",
        "core/src/flag_residual.rs",
    ):
        if not (ROOT / path).is_file():
            pytest.skip("not a checkout")
        text = (ROOT / path).read_text(encoding="utf-8")
        assert _expression(path) == "MIT", path
        assert "Copyright (c) 2022 Jonathan Simon Kenyon" in text, path
        assert "Permission is hereby granted, free of charge" in text, path
