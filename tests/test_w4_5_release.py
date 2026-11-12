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
    # No alpha, beta or rc versions: the owner releases only finished
    # versions (E5, research/e5-prereview.md).
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    cff = re.search(r"^version: (\S+)$", _text("CITATION.cff"), re.MULTILINE)
    assert cff and cff.group(1) == version, "CITATION.cff"
    crates = {
        "Cargo.toml": "rang-sim",
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
    # E5-17: the install check's expected output names the current version.
    install = _text("docs/installation.md")
    assert re.findall(r"# rang-core (\S+)", install) == [version]


def test_version_falls_back_to_pyproject(monkeypatch):
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    # From a checkout the checkout's pyproject.toml; from an installed wheel
    # (no pyproject.toml beside site-packages) "unknown".
    in_checkout = Path(rang.__file__).resolve().parents[2] == ROOT
    assert rang._version() == (pyproject_version() if in_checkout else "unknown")


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
    # Images from raw.githubusercontent.com (a blob/ URL serves HTML), or this
    # repository's workflow status badges, which serve SVG.
    badge = re.compile(
        r"https://github\.com/gijzelaerr/rang-core/actions/workflows/"
        r"[\w.-]+/badge\.svg(\?branch=main)?$"
    )
    for source in re.findall(r'src="([^"]+)"', readme):
        assert source.startswith("https://raw.githubusercontent.com/") or badge.match(
            source
        ), source


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
    # E5: the MIT and BSD notices of the translated code ship in every wheel.
    assert 'license-files = ["LICENSE", "THIRD-PARTY-NOTICES.txt"]' in project
    notices = _text("THIRD-PARTY-NOTICES.txt")
    for path, holder in (
        ("core/src/solve.rs", "Copyright (c) 2022 Jonathan Simon Kenyon"),
        ("core/src/predict.rs", "Copyright (c) 2019, National Research Foundation"),
        (
            "core/src/sumthreshold.rs",
            "Copyright (c) 2019, National Research Foundation",
        ),
    ):
        assert holder in notices and path in notices, path
    # E5 final (E5-12): the GPL ports keep their upstream copyright lines,
    # in the source header and in the notices the wheel carries.
    for path, holder in (
        ("core/src/grid.rs", "2008-2015 A. R. Offringa"),
        ("core/src/weights.rs", "2008-2015 A. R. Offringa"),
        ("core/src/wgridder.rs", "Copyright (C) 2019-2026 Max-Planck-Society"),
        ("core/src/wgridder.rs", "Copyright (C) 2020-2026 Max-Planck-Society"),
    ):
        assert holder in notices and holder in _text(path), (path, holder)
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
        ".cargo",
    ):
        assert f'{{ path = "{tree}/**/*", format = "sdist" }}' in maturin, tree
    # gemclean's simulator includes data/meerkat.itrf.txt at compile time (G8).
    assert '{ path = "data/**/*", format = "sdist" }' not in maturin
    assert '{ path = "data/meerkat.itrf.txt", format = "sdist" }' not in maturin
    # E5-37: checkout tools stay out; tools/wheel/ is what tests the wheel.
    for tool in (
        ".claude/**/*",
        "tools/a1_casa.sh",
        "tools/a1_checks.sh",
        "tools/e2e/**/*",
        "tools/gain_hash_gate.py",
        "tools/heavy_lock.py",
    ):
        assert f'{{ path = "{tool}", format = "sdist" }}' in maturin, tool
    assert '{ path = "tools/wheel/**/*", format = "sdist" }' not in maturin
    # Owner decision E5-11: the three tables only core/examples/ reads stay out.
    for name in ("kat7", "vla-c", "wsrt"):
        assert f'{{ path = "data/{name}.itrf.txt", format = "sdist" }}' in maturin


def test_the_antenna_tables_are_recorded_as_facts():
    """Owner decision E5-11: the simms coordinates are facts, not code."""
    licence = _text("docs/licence.md")
    assert "Facts, not code" in licence and "owner decision E5-11" in licence
    assert "| MeerKAT ITRF positions from simms | GPL-2.0" not in licence
    meerkat = ROOT / "data" / "meerkat.itrf.txt"
    if meerkat.exists():  # every row is a position record, nothing else
        rows = [
            r.split()
            for r in meerkat.read_text(encoding="utf-8").splitlines()
            if r.strip() and not r.lstrip().startswith("#")
        ]
        assert rows and all(len(r) == 6 for r in rows)


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
    # E5: PyPI only after the release job's checks and notes have passed.
    needs = re.search(r"^    needs: \[(.*)\]$", _job(workflow, "publish"), re.MULTILINE)
    assert "release" in [n.strip() for n in needs.group(1).split(",")]


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


def test_the_licence_table_lists_every_upstream():
    """Owner decision E5-33: the ported, adapted and reimplemented upstreams
    are all listed; CARACal and msutils as behaviour reimplemented."""
    licence = _text("docs/licence.md")
    for name in (
        "codex-africanus",
        "katdal",
        "CARACal",
        "msutils",
        "CASA",
        "casacore 3.8.1",
        "casacore-data",
    ):
        assert name in licence, name
    section = licence.split("Behaviour reimplemented", 1)[1]
    rows = [r for r in section.splitlines() if r.startswith("| ")]
    end = next(i for i, r in enumerate(rows) if r.startswith("| casacore 3.8.1"))
    table = rows[: end + 1]
    assert any(r.startswith("| CARACal") for r in table)
    assert any(r.startswith("| msutils") for r in table)
    assert any("confirm GPL-2.0-or-later" in r for r in table)


def test_the_recipes_extra_resolves_on_every_declared_python():
    """E5-38: stimela 2.1.4 requires Python < 3.14, a version the package
    declares, so the extra carries a marker instead of failing to resolve."""
    from packaging.requirements import Requirement

    extras = _section(_text("pyproject.toml"), "project.optional-dependencies")
    line = re.search(r"^recipes = \[(.*)\]$", extras, re.MULTILINE).group(1)
    (stimela,) = [Requirement(s.strip().strip('"')) for s in line.split('",')]
    assert stimela.name == "stimela" and str(stimela.specifier) == "==2.1.4"
    assert stimela.marker.evaluate({"python_version": "3.13"})
    assert not stimela.marker.evaluate({"python_version": "3.14"})
