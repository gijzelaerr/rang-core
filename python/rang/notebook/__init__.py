"""Jupyter tooling for students and professionals (research/d2-notebook.md).

Plain functions first; every plot returns a `matplotlib.figure.Figure` and
every table a pandas DataFrame or a dict, so they work in scripts and tests.
`steer` adds a thin ipywidgets layer. Every heavy call goes to the core
wrappers (`core_ms`, `core_fetch`, `core_workflow`, `core_flag`,
`core_weights`, `core_grid`, `core_campaign`); nothing is reimplemented.

Modules, in teaching order:

- `data`: load the fixture scan or the four-station LUNO slice;
- `survey`: rank first, which gain bins the data can identify and why;
- `flags`: flags, weights and amplitudes; a Tricolour strategy step by step;
- `gains`: solve, gain amplitude/phase/TV maps, the unitary gauge;
- `image`: Briggs weights, dirty image and PSF, comparisons;
- `experiment`: the campaign arms, the frozen decision rule, the archives;
- `science`: the two research questions (D3), archive readers and live demonstrations;
- `steer`: sliders and dropdowns that rerun the affected stage.
- `carta`: optional; open images and cubes in a running CARTA backend (research/nb-carta.md).

Install with the `notebook` extra (matplotlib, pandas, ipywidgets, a
Jupyter kernel). Submodules import lazily, so `import rang.notebook`
is cheap.
"""

import importlib

__all__ = [
    "carta",
    "data",
    "experiment",
    "flags",
    "gains",
    "image",
    "science",
    "steer",
    "survey",
]


def __getattr__(name):
    if name in __all__:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(name)
