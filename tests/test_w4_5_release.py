"""Task W4-5 (research/w4-5-release.md): the release metadata of v0.1.0.

One source of truth for the version (pyproject.toml), `rang.__version__`
and `rang-core --version`, a README that renders on PyPI with no relative
URL, a CHANGELOG section per version, the tag-equals-version guard of the
release workflow and the sdist's exclude list.
"""

from __future__ import annotations

import importlib.metadata
import re
import runpy
from pathlib import Path

import pytest
import rang
from rang import core_cli

ROOT = Path(__file__).resolve().parents[1]


# The sdist carries no .github/ and no docs/ (pyproject.toml [tool.maturin]
# exclude); the tests of those files run from a checkout only.
CHECKOUT_ONLY = (".github/", "docs/")


def _text(path):
    if path.startswith(CHECKOUT_ONLY) and not (ROOT / ".github").is_dir():
        pytest.skip(f"{path} is in a checkout, not in the sdist")
    return (ROOT / path).read_text(encoding="utf-8")


def _section(text, header):
    """The lines of TOML table `header` up to the next table."""
    found = re.search(
        rf"^\[{re.escape(header)}\]\n(.*?)(?=^\[|\Z)", text, re.MULTILINE | re.DOTALL
    )
    assert found, header
    return found.group(1)


def _field(text, name):
    found = re.search(rf'^{name} = "([^"]+)"$', text, re.MULTILINE)
    assert found, name
    return found.group(1)


def pyproject_version():
    return _field(_section(_text("pyproject.toml"), "project"), "version")


def lock_versions(path):
    """{package name: version} of a Cargo.lock."""
    blocks = _text(path).split("[[package]]")[1:]
    return {_field(b, "name"): _field(b, "version") for b in blocks}


def test_versions_agree():
    version = pyproject_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+([ab]\d+|rc\d+)?", version)
    crates = {
        "Cargo.toml": "rang-toy",
        "core/Cargo.toml": "rang-core",
        "core/py/Cargo.toml": "rang-core-py",
    }
    for manifest, name in crates.items():
        package = _section(_text(manifest), "package")
        assert _field(package, "name") == name
        assert _field(package, "version") == version, manifest
    # A bump without the lock files fails `maturin build --locked` in CI.
    for lock in ("Cargo.lock", "core/Cargo.lock", "core/py/Cargo.lock"):
        locked = lock_versions(lock)
        for name in crates.values():
            if name in locked:
                assert locked[name] == version, (lock, name)
    assert lock_versions("core/py/Cargo.lock")["rang-core-py"] == version
    assert rang.__version__ == version
    assert importlib.metadata.version("rang-core") == version


def test_docs_version_agrees():
    version = pyproject_version()
    assert "release = _version(" in _text("docs/conf.py")
    conf = runpy.run_path(str(ROOT / "docs" / "conf.py"))
    assert conf["release"] == conf["version"] == version


def test_version_falls_back_to_pyproject(monkeypatch):
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    assert rang._version() == pyproject_version()


@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_cli_version(flag, capsys):
    assert core_cli.main([flag]) == 0
    assert capsys.readouterr().out == f"rang-core {pyproject_version()}\n"


def test_changelog_has_the_version():
    changelog = _text("CHANGELOG.md")
    assert re.search(
        rf"^## {re.escape(pyproject_version())}( |$)", changelog, re.MULTILINE
    )
    assert "## Unreleased" in changelog


_ABSOLUTE = re.compile(r"^(https?://|mailto:|#)")


def relative_targets(markdown):
    """Link targets and image sources that are not absolute URLs."""
    targets = re.findall(r"\]\(([^)\s]+)", markdown)
    targets += re.findall(r'(?:src|href)="([^"]+)"', markdown)
    targets += re.findall(r"^\s*\[[^\]]+\]:\s*(\S+)", markdown, re.MULTILINE)
    return [t for t in targets if not _ABSOLUTE.match(t)]


def test_relative_targets_detector():
    sample = '[a](research/x.md) [b](https://x.org) <img src="docs/l.svg">\n[c]: y.md\n'
    assert relative_targets(sample) == ["research/x.md", "docs/l.svg", "y.md"]


def test_readme_has_no_relative_url():
    readme = _text("README.md")
    assert relative_targets(readme) == []
    # Images from raw.githubusercontent.com: a blob/ URL serves HTML.
    for source in re.findall(r'src="([^"]+)"', readme):
        assert source.startswith("https://raw.githubusercontent.com/"), source


def test_rendered_readme_has_no_relative_url():
    # readme_renderer renders Markdown only with comrak (readme-renderer[md]).
    pytest.importorskip("comrak")
    readme_renderer = pytest.importorskip("readme_renderer.markdown")
    html = readme_renderer.render(_text("README.md"))
    assert html
    urls = re.findall(r'(?:src|href)="([^"]+)"', html)
    assert urls
    assert [u for u in urls if not _ABSOLUTE.match(u)] == []


def test_pyproject_metadata():
    project = _section(_text("pyproject.toml"), "project")
    for classifier in (
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Operating System :: Microsoft :: Windows",
        *(f"Programming Language :: Python :: 3.{minor}" for minor in range(10, 15)),
    ):
        assert f'"{classifier}"' in project
    # A PEP 639 licence expression: a License classifier would be rejected.
    assert 'license = "GPL-3.0-or-later"' in project
    assert "License ::" not in project
    urls = _section(_text("pyproject.toml"), "project.urls")
    for name in ("Documentation", "Repository", "Issues"):
        assert re.search(rf'^{name} = "https://', urls, re.MULTILINE), name
    assert _field(urls, "Repository") == "https://github.com/gijzelaerr/rang-core"
    extras = _section(_text("pyproject.toml"), "project.optional-dependencies")
    assert not re.search(r"^flagging = ", extras, re.MULTILINE)


def test_sdist_excludes_the_research_tree():
    maturin = _section(_text("pyproject.toml"), "tool.maturin")
    for tree in (
        "research",
        "history",
        "outputs",
        "notebooks",
        "docs",
        "formal",
        "data",
        ".cargo",
    ):
        assert f'{{ path = "{tree}/**/*", format = "sdist" }}' in maturin, tree


def _job(workflow, name):
    found = re.search(
        rf"^  {name}:\n(.*?)(?=^  \S|\Z)", workflow, re.MULTILINE | re.DOTALL
    )
    assert found, name
    return found.group(1)


def test_release_jobs_check_the_tag():
    workflow = _text(".github/workflows/wheels.yml")
    for name in ("release", "publish"):
        job = _job(workflow, name)
        check = job.index("name: Check that the tag equals the version")
        upload = job.index(
            "gh release create" if name == "release" else "gh-action-pypi-publish"
        )
        assert check < upload, name
        assert 'tag="${GITHUB_REF_NAME#v}"' in job
    release = _job(workflow, "release")
    assert "pyproject.toml" in release
    assert release.index("CHANGELOG.md") < release.index("--notes-file")


# The first major version of each action that runs on Node 24.
NODE24 = {
    "actions/checkout": 5,
    "actions/setup-python": 6,
    "actions/upload-artifact": 6,
    "actions/download-artifact": 7,
    "actions/cache": 5,
    "actions/configure-pages": 6,
    "actions/deploy-pages": 5,
    "actions/upload-pages-artifact": 5,
}


@pytest.mark.parametrize("workflow", ["wheels.yml", "docs.yml"])
def test_actions_run_on_node24(workflow):
    text = _text(f".github/workflows/{workflow}")
    uses = re.findall(r"uses: (actions/[\w-]+)@v(\d+)", text)
    assert uses
    for action, major in uses:
        assert int(major) >= NODE24[action], (action, major)
