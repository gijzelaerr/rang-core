"""Sphinx configuration of the rang-core documentation site (task D1,
research/d1-docs.md).

Build strictly, from the checkout, with the extension present:

    python docs/execute_notebooks.py          # optional: executed tutorials
    sphinx-build -W --keep-going -b html docs docs/_build/html

Without the first step the tutorials are rendered from the committed,
output-free notebooks.
"""

import re
import shutil
from pathlib import Path

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parent
GITHUB = "https://github.com/gijzelaerr/rang-core"

project = "rang-core"
author = "Gijs Molenaar"
copyright = "2026, Gijs Molenaar; GPL-3.0-or-later"

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    release = _version("rang-core")
except PackageNotFoundError:  # only without an installed distribution
    release = "unknown"
version = release

extensions = [
    "myst_nb",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.extlinks",
]

exclude_patterns = [
    "_build",
    "_generated",
    "logo/README.md",
    "**.ipynb_checkpoints",
    "jupyter_execute",
]
templates_path = ["_templates"]

# Docstrings are plain prose with backtick code spans.
default_role = "literal"
autosummary_generate = True
autosummary_ignore_module_all = True
autodoc_default_options = {"members": True, "show-inheritance": True}
autodoc_member_order = "bysource"
# The flagging extra (python-casacore, QuartiCal, stimela) is never needed to
# import the live package; mocked so that a lazy import cannot fail the build.
autodoc_mock_imports = ["casacore", "quartical", "stimela"]

myst_enable_extensions = ["dollarmath", "amsmath", "colon_fence", "deflist"]
myst_heading_anchors = 3
# The tutorials are executed before the build (docs/execute_notebooks.py,
# papermill), never by Sphinx.
nb_execution_mode = "off"
nb_merge_streams = True

extlinks = {
    "gh": (f"{GITHUB}/blob/main/%s", "%s"),
    "ghdir": (f"{GITHUB}/tree/main/%s", "%s"),
}

html_theme = "furo"
html_title = "rang-core"
html_favicon = "logo/favicon.ico"
html_static_path = ["logo/lockup.svg", "logo/lockup-on-dark.svg"]
html_theme_options = {
    "light_logo": "lockup.svg",
    "dark_logo": "lockup-on-dark.svg",
    "sidebar_hide_name": True,
    "source_repository": GITHUB,
    "source_branch": "main",
    "source_directory": "docs/",
}

NOTEBOOKS = ROOT / "notebooks"
TUTORIALS = DOCS / "tutorials" / "notebooks"
GENERATED = DOCS / "_generated"

# Outside double backticks, a `|` in a docstring is an absolute value or a
# norm (`|G|_F`), never an RST substitution.
_LITERAL = re.compile(r"(``.*?``|`[^`]*`)")


def _escape_pipes(app, what, name, obj, options, lines):
    for i, line in enumerate(lines):
        if "|" not in line:
            continue
        parts = _LITERAL.split(line)
        lines[i] = "".join(
            part if k % 2 else part.replace("|", r"\|") for k, part in enumerate(parts)
        )


def _copy_notebooks(app):
    """Render executed copies when docs/execute_notebooks.py made them,
    otherwise the committed notebooks (no outputs)."""
    TUTORIALS.mkdir(parents=True, exist_ok=True)
    for source in sorted(NOTEBOOKS.glob("*.ipynb")):
        target = TUTORIALS / source.name
        if not target.exists() or target.stat().st_mtime < source.stat().st_mtime:
            shutil.copyfile(source, target)


def _md_cell(text):
    return text.replace("|", r"\|").replace("\n", " ")


def _write_constants(app):
    """The constants of `rang.notebook` written to be quoted (D2), as MyST
    snippets in `_generated/` that the pages include."""
    from rang.notebook import experiment, gains, survey

    status = [
        "| Code | Label | Meaning |",
        "| ---: | --- | --- |",
        *(
            f"| {code} | {_md_cell(label)} | {_md_cell(text)} |"
            for code, (label, text) in survey.STATUS.items()
        ),
    ]
    snippets = {
        "status.md": "\n".join(status) + "\n",
        "gauge_note.md": f"> {gains.GAUGE_NOTE}\n",
        "decision_rule.md": f"> {experiment.DECISION_RULE}\n",
    }
    GENERATED.mkdir(exist_ok=True)
    for name, text in snippets.items():
        path = GENERATED / name
        if not path.exists() or path.read_text() != text:
            path.write_text(text)


def setup(app):
    app.connect("builder-inited", _copy_notebooks)
    app.connect("builder-inited", _write_constants)
    app.connect("autodoc-process-docstring", _escape_pipes)
