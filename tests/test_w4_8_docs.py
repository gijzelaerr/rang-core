"""Task W4-8 (research/w4-8-readme-docs.md): the documentation pass.

The README stays a short landing page whose links resolve, the research index
reaches every note and has no dated stack left, STATE keeps its structure, and
the docs workflow's deploy job skips, with a warning, a repository without
GitHub Pages.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/gijzelaerr/rang-core/"
RESEARCH = ROOT / "research"

# The sdist carries README.md but no research/, docs/ or .github/.
checkout_only = pytest.mark.skipif(
    not (RESEARCH / "README.md").is_file(), reason="in a checkout, not in the sdist"
)


def _readme():
    return (ROOT / "README.md").read_text(encoding="utf-8")


def _targets(markdown):
    """Link and image targets of Markdown or inline HTML."""
    targets = re.findall(r"\]\(([^)\s]+)", markdown)
    targets += re.findall(r'(?:src|srcset|href)="([^"]+)"', markdown)
    return targets


def test_readme_is_short():
    assert len(_readme().splitlines()) < 160


def test_readme_sections_in_order():
    headings = re.findall(r"^## (.+)$", _readme(), re.MULTILINE)
    assert headings == [
        "What it is",
        "Install",
        "Quick start",
        "Documentation",
        "Research results",
        "Repository guide",
        "Names",
        "Contributing",
        "Licence and data acknowledgements",
        "Citation",
    ]


@checkout_only
def test_readme_links_are_absolute_and_exist():
    prefix = re.compile(
        rf"^(?:{re.escape(REPOSITORY)}(?:blob|tree)/main/"
        r"|https://raw\.githubusercontent\.com/gijzelaerr/rang-core/main/)"
    )
    targets = _targets(_readme())
    assert len(targets) > 20
    for target in targets:
        assert target.startswith("https://"), target
        if prefix.match(target):
            path = prefix.sub("", target).split("#")[0]
            assert (ROOT / path).exists(), target


@checkout_only
def test_every_note_is_in_the_research_index():
    index = (RESEARCH / "README.md").read_text(encoding="utf-8")
    linked = {t.split("#")[0] for t in re.findall(r"\]\(([^)\s]+)", index)}
    notes = {p.name for p in RESEARCH.glob("*.md")} - {"README.md"}
    assert sorted(notes - linked) == []


@checkout_only
def test_research_index_links_resolve():
    index = (RESEARCH / "README.md").read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)\s]+)", index):
        path = target.split("#")[0]
        if path and "://" not in path:
            assert (RESEARCH / path).exists(), target


@checkout_only
def test_no_dated_stack_in_the_research_index():
    index = (RESEARCH / "README.md").read_text(encoding="utf-8")
    assert not re.search(r"^New,? 2026", index, re.MULTILINE)
    assert "New, 2026" not in index
    assert "rangtoy" in index  # the rename note


@checkout_only
def test_state_structure():
    state = (RESEARCH / "STATE.md").read_text(encoding="utf-8")
    assert state.startswith("# Rang research state\n\n## Current status\n")
    assert state.index("## Current status") < state.index("## Log (newest first)")
    assert "STATE-history.md" in state
    assert "FINAL CHECKED PUBLICATION READY" not in state
    history = (RESEARCH / "STATE-history.md").read_text(encoding="utf-8")
    assert "FINAL CHECKED PUBLICATION READY" in history


def test_citation_version_agrees():
    citation = ROOT / "CITATION.cff"
    if not citation.is_file():
        pytest.skip("in a checkout, not in the sdist")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE).group(1)
    assert f"version: {version}\n" in citation.read_text(encoding="utf-8")


def _deploy_job():
    workflow = ROOT / ".github" / "workflows" / "docs.yml"
    if not workflow.is_file():
        pytest.skip("in a checkout, not in the sdist")
    text = workflow.read_text(encoding="utf-8")
    return text[text.index("  deploy:\n") :]


def test_deploy_steps_wait_for_the_pages_check():
    job = _deploy_job()
    guard = "if: steps.pages.outputs.enabled == 'true'"
    assert job.index("id: pages") < job.index("actions/configure-pages")
    for action in ("actions/configure-pages", "actions/deploy-pages"):
        before = job[: job.index(action)]
        assert before[before.rindex("- ") :].count(guard) == 1, action


def _pages_check():
    job = _deploy_job()
    step = job[job.index("id: pages") :]
    block = step[step.index("run: |\n") + len("run: |\n") : step.index("      - if:")]
    return textwrap.dedent(block)


@pytest.mark.skipif(sys.platform == "win32", reason="the deploy job runs on Linux")
@pytest.mark.parametrize(
    ("status", "code", "enabled", "message"),
    [
        ("200", 0, "enabled=true", None),
        ("404", 0, "enabled=false", "::warning::GitHub Pages is not enabled"),
        ("500", 1, None, "::error::"),
    ],
)
def test_pages_check_shell(tmp_path, status, code, enabled, message):
    fake = tmp_path / "curl"
    fake.write_text(f"#!/bin/sh\nprintf {status}\n", encoding="utf-8")
    fake.chmod(0o755)
    output = tmp_path / "output"
    output.write_text("", encoding="utf-8")
    done = subprocess.run(
        ["bash", "-c", _pages_check()],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "GH_TOKEN": "token",
            "GITHUB_API_URL": "https://api.github.com",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": str(output),
        },
    )
    assert done.returncode == code
    assert (enabled or "") in output.read_text(encoding="utf-8")
    if enabled is None:
        assert output.read_text(encoding="utf-8") == ""
    if message:
        assert message in done.stdout
