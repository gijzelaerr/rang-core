"""The documentation site (task D1, research/d1-docs.md).

The CLI page must equal what `rang-core -h` prints, and the site must build
with Sphinx without a single warning (`-W`), which covers the API reference
generated from every public module's docstrings. The build test is skipped
without the `docs` extra; it renders the tutorials from whatever
`docs/tutorials/notebooks/` holds (the committed notebooks unless
`docs/execute_notebooks.py` ran) and writes only gitignored files under
`docs/` plus its output under pytest's temporary directory.
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def _gen_cli():
    spec = importlib.util.spec_from_file_location("d1_gen_cli", DOCS / "gen_cli.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_page_matches_help():
    page = (DOCS / "cli.md").read_text(encoding="utf-8")
    assert page == _gen_cli().page(), "docs/cli.md is stale: run python docs/gen_cli.py"


def test_cli_page_covers_every_stage():
    from rang.core_cli import STAGES

    page = (DOCS / "cli.md").read_text(encoding="utf-8")
    for stage in STAGES:
        assert f"$ rang-core {stage} -h\n" in page


def test_repository_links_exist():
    """`{gh}` and `{ghdir}` links are external URLs, which a strict build
    cannot check; every target must exist in the checkout."""
    role = re.compile(r"\{gh(?:dir)?\}`([^`]+)`")
    sources = [*DOCS.rglob("*.md"), DOCS / "gen_cli.py"]
    targets = set()
    for source in sources:
        if "_build" in source.parts or "generated" in source.parts:
            continue
        targets.update(role.findall(source.read_text(encoding="utf-8")))
    assert len(targets) > 40
    missing = sorted(t for t in targets if not (ROOT / t).exists())
    assert not missing, missing


def test_site_builds_without_warnings(tmp_path):
    pytest.importorskip("sphinx")
    pytest.importorskip("myst_nb")
    pytest.importorskip("furo")
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "sphinx",
            "-W",
            "--keep-going",
            "-E",
            "-q",
            "-b",
            "html",
            "-d",
            str(tmp_path / "doctrees"),
            str(DOCS),
            str(tmp_path / "html"),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-4000:]
    assert "WARNING" not in done.stderr
    api = tmp_path / "html" / "api" / "generated"
    pages = {p.name for p in api.glob("rang.*.html")}
    for module in ("core", "core_ms", "core_flag", "core_wgridder", "notebook.survey"):
        assert f"rang.{module}.html" in pages
    index = (tmp_path / "html" / "index.html").read_text(encoding="utf-8")
    assert "not an operational calibrator" in index
    assert "closed as null" in index
