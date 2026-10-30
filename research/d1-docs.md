# D1: the documentation site

Big plan task D1 ([big-plan.md](big-plan.md), "Documentation, teaching and
upstream fixes"), branch `d1-docs` from main `3b875e0`. Status:
**in progress** (this commit records the tool decision before any site file
exists). Documentation only; no scientific claim.

## Tool decision: Sphinx

Sphinx 9.2 with `autodoc`/`autosummary`, `myst-nb` (MyST Markdown pages and
notebook rendering) and the `furo` theme, not MkDocs with `mkdocstrings`.
The deciding feature is the API reference from the core wrappers'
docstrings: Sphinx autodoc imports `rang` with the compiled `rang._core`
present, so what it documents is what a user imports, and a trial strict
build (`-W --keep-going`, `automodule :members:` over all 61 modules under
`python/rang/`, 2026-10-30) documented 453 objects with 11 warnings and no
import failure; every warning had one cause, `|x|` read as an RST
substitution, which a docstring hook in `conf.py` escapes without touching
the shared modules. The docstrings are plain prose with backtick code
spans, which `default_role = "literal"` renders as code. `myst-nb` renders
the five notebooks without pandoc (which `nbsphinx` needs and no apt install
may provide), and the pages stay in Markdown like the rest of the
repository. MkDocs with `mkdocstrings` would have parsed the same docstrings
statically (griffe) and so would not prove the extension imports; it would
also have added a second Markdown dialect for no gain here.
