"""Every source file carries an SPDX licence line (E5-45, CONTRIBUTING.md
"Licence headers")."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIRS = ("python/rang", "core/src", "src", "tools")
SUFFIXES = {".py": "#", ".sh": "#", ".rs": "//", ".cc": "//"}
# New files from 2026-11-17 (the owner's licence rule) are MIT.
LINE = re.compile(
    r"SPDX-License-Identifier: (GPL-3\.0-or-later( AND [A-Za-z0-9.-]+)*|MIT)$"
)
# Files another task is changing when the headers go in; stamp them once it
# merges. Empty since sliced-read merged (E5 final).
PENDING: set[str] = set()


def _tracked():
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", *DIRS],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [p for p in out.split() if Path(p).suffix in SUFFIXES]


def _header(path):
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()[:3]
    comment = SUFFIXES[Path(path).suffix]
    for line in lines:
        if line.startswith(comment) and LINE.search(line):
            return line
    return None


def test_every_source_file_has_an_spdx_line():
    files = _tracked()
    assert len(files) > 200
    missing = [p for p in files if p not in PENDING and _header(p) is None]
    assert missing == []


def test_ported_files_name_the_upstream_licence_too():
    """docs/licence.md: ported code keeps its upstream notice."""
    for path, licence in {
        "core/src/solve.rs": "MIT",
        "core/src/predict.rs": "BSD-3-Clause",
        "core/src/sumthreshold.rs": "BSD-3-Clause",
        "python/rang/meerkat.py": "BSD-3-Clause",
        # B-02 (research/v030-review.md): radler 76fe4474 is LGPL-3.0-only.
        "core/src/gemclean/mask.rs": "LGPL-3.0-only",
        "core/src/gemclean/joined.rs": "LGPL-3.0-only",
        "core/src/gemclean/multiscale.rs": "LGPL-3.0-only",
        "core/src/gemclean/stokes.rs": "LGPL-3.0-only",
        # research/mit-relicense-audit.md section 3.2: permissive upstreams.
        "core/src/blosc.rs": "BSD-3-Clause",
        "python/rang/core_flag.py": "BSD-3-Clause",
        "python/rang/formats/sky.py": "BSD-3-Clause",
        "core/src/gpu/shader.rs": "SunPro",
    }.items():
        if not (ROOT / path).is_file():
            pytest.skip("not a checkout")
        assert _header(path).endswith(f"GPL-3.0-or-later AND {licence}")
