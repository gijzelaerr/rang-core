"""The introductory notebook track I1-I9 (task V3b, research/v3-intro-track.md).

Static checks only: the notebooks are executed by the documentation workflow
(docs/execute_notebooks.py; I6-I8 nightly). Also the antenna table as package
data (V3's owner decision 4) and the A1 generator in the package.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INTRO = ROOT / "notebooks" / "intro"
BOOKS = [
    "i1-radio-sky.ipynb",
    "i2-visibilities.ipynb",
    "i3-meerkat-array.ipynb",
    "i4-measurement-equation.ipynb",
    "i5-rfi-and-flagging.ipynb",
    "i6-calibration.ipynb",
    "i7-imaging-and-deconvolution.ipynb",
    "i8-polarisation.ipynb",
    "i9-time-domain.ipynb",
]


def _book(name):
    return json.loads((INTRO / name).read_text(encoding="utf-8"))


def _markdown(name):
    return "\n".join(
        "".join(c["source"])
        for c in _book(name)["cells"]
        if c["cell_type"] == "markdown"
    )


def _execute_notebooks():
    spec = importlib.util.spec_from_file_location(
        "execute_notebooks", ROOT / "docs" / "execute_notebooks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_nine_notebooks_and_nothing_else():
    assert sorted(p.name for p in INTRO.glob("*.ipynb")) == BOOKS


@pytest.mark.parametrize("name", BOOKS)
def test_committed_without_outputs(name):
    for cell in _book(name)["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None


@pytest.mark.parametrize("name", BOOKS)
def test_goals_exercises_and_links(name):
    text = _markdown(name)
    assert text.startswith(f"# I{name[1]}. ")
    assert "**Learning goals.**" in text
    assert "## Exercises" in text and "## Where next" in text
    assert "{doc}`../index`" in text  # back to the track
    assert "toy" not in text.lower().split()


def test_where_next_links_resolve():
    """Every {doc} link of the track names a page the docs build has."""
    import re

    pages = {p.stem for p in (ROOT / "notebooks").rglob("*.ipynb")}
    for name in BOOKS:
        for target in re.findall(r"\{doc\}`(?:[^`<]*<)?([^`>]+)>?`", _markdown(name)):
            if target.startswith("../"):
                path = ROOT / "docs" / "tutorials" / "notebooks" / target
                assert path.resolve().with_suffix(".md").is_file(), (name, target)
            else:
                assert target in pages, (name, target)


def test_docs_build_runs_the_track_and_i6_to_i8_nightly():
    module = _execute_notebooks()
    names = [p.name for p in module.sources()]
    for name in BOOKS:
        assert name in names
    assert len(names) == len(set(names)), "flat output names must be unique"
    assert set(module.NIGHTLY) == {BOOKS[5], BOOKS[6], BOOKS[7]}
    index = (ROOT / "docs" / "tutorials" / "index.md").read_text("utf-8")
    for name in BOOKS:
        assert f"notebooks/{name.removesuffix('.ipynb')}" in index
    assert "@I" not in index, "runtimes not filled in"
    workflow = (ROOT / ".github" / "workflows" / "docs.yml").read_text("utf-8")
    assert "schedule:" in workflow and "RANG_NOTEBOOK_INTRO_SLOW" in workflow


def test_an_executed_copy_is_kept_only_while_the_code_is_unchanged(tmp_path):
    module = _execute_notebooks()
    source = INTRO / BOOKS[5]
    executed = _book(BOOKS[5])
    for cell in executed["cells"]:
        if cell["cell_type"] == "code":
            cell["outputs"] = [
                {"output_type": "stream", "name": "stdout", "text": ["x\n"]}
            ]
    target = tmp_path / source.name
    target.write_text(json.dumps(executed), encoding="utf-8")
    assert module.keep_executed(source, target) and target.exists()
    code = next(c for c in executed["cells"] if c["cell_type"] == "code")
    code["source"] = ["print('changed')\n"]
    target.write_text(json.dumps(executed), encoding="utf-8")
    assert not module.keep_executed(source, target) and not target.exists()
    assert not module.keep_executed(source, target)


def test_the_antenna_table_is_package_data_and_a_byte_copy():
    from rang import simtruth

    package = ROOT / "python" / "rang" / "data" / "meerkat.itrf.txt"
    assert simtruth.ITRF.resolve() == package.resolve()
    # GeMClean's simulator compiles data/meerkat.itrf.txt in: keep them equal.
    assert package.read_bytes() == (ROOT / "data" / "meerkat.itrf.txt").read_bytes()
    xyz, diameter, names = simtruth.antenna_table()
    assert xyz.shape == (64, 3) and set(diameter) == {13.5} and names[0] == "m000"


def test_the_generator_is_in_the_package():
    from rang import simtruth_ms

    assert simtruth_ms.size("small")["nrow"] == 12480
    shim = (ROOT / "examples" / "a1_simtruth.py").read_text(encoding="utf-8")
    assert "from rang.simtruth_ms import" in shim
