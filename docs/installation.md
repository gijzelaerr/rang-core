# Installation

## From the wheel

```sh
pip install rang-core
```

```{note}
`rang-core` is not on PyPI until the first release is tagged (`v0.1.0`
publishes it). Until then, install [from source](#from-source), or download
a wheel from the artifacts of a `wheels` workflow run and
`pip install rang_core-<version>-cp310-abi3-<platform>.whl`.
```

The wheel carries the compiled core, so no Rust compiler is needed for the
flagging chain, imaging and the tutorials. The kernels are inside the
extension `rang._core`, including the root crate's (gain TV, phase trend,
anchored response, projector, the pointing toy); importing `rang` never runs
Cargo, and the extension releases the GIL around every kernel.

Three later additions are not in the extension yet: the exact wgridder
(`rang.core_wgridder`), the closure statistic (`rang.core_closure`) and the
Rust path of the flux standards (`rang.fluxstd`; its Python tables need no
build) build a standalone library with `cargo` from a source checkout on
first use. The archive drivers and comparators read archived inputs from a
checkout too.

{gh}`.github/workflows/wheels.yml` builds and tests one `abi3` wheel per
platform for CPython 3.10 and newer, five platforms in all
({gh}`research/x1-crossplatform.md`):

| Platform | Wheel tag | Built on |
| --- | --- | --- |
| Linux x86_64 | `manylinux_2_28_x86_64` (glibc 2.28 or newer) | `ubuntu-24.04` |
| Linux aarch64 | `manylinux_2_28_aarch64` | `ubuntu-24.04` (cross), tested on `ubuntu-24.04-arm` |
| macOS arm64 | `macosx_*_arm64` | `macos-15` |
| macOS x86_64 | `macosx_*_x86_64` | `macos-15-intel` |
| Windows x86_64 | `win_amd64` | `windows-2022` |

Each wheel is built for the platform's baseline CPU and tested on CPython
3.10 and 3.14 on its own operating system with `cargo` absent from `PATH`.
On GitHub, a `v*` tag that equals the `pyproject.toml` version attaches the
wheels and the sdist to a GitHub release, with the version's
{gh}`CHANGELOG.md` section as its notes, and publishes `rang-core` to PyPI by
trusted publishing ([Releases](#releases)). The macOS and Windows wheels are
newer than the Linux ones; the frozen campaigns' guards still assume POSIX
({gh}`research/x1-crossplatform.md`).

The sdist holds the three Rust crates, the Python package, `tests/` and
`tools/wheel/`: it builds the wheel (Rust 1.93 and a C compiler needed) and
runs the wheel's test subset (`tools/wheel/pytest_wheel.py`). The full test
suite, the examples, the notebooks, the recipes and `research/` are in the
[repository](https://github.com/gijzelaerr/rang-core) only.

## Optional extras

| Extra | Installs | For |
| --- | --- | --- |
| `notebook` | matplotlib, pandas, ipywidgets, ipykernel, jupyterlab, nbformat, nbconvert | the tutorials and `rang.notebook` |
| `imaging` | astropy | FITS output of the gridders |
| `pointing` | JAX, SciPy | the JAX direct-Fourier reference path of the pointing solver |
| `beam` | katbeam, EIDOS | the beam controls of `rang.beam_holography` |
| `plot` | matplotlib | plots in the examples |
| `test` | pytest | the test suite |
| `docs` | Sphinx, furo, myst-nb, papermill | this site |
| `recipes` | Stimela 2.1.4 | the core-native Stimela2 recipes in `recipes/` (Python 3.13) |

```sh
pip install 'rang-core[notebook,imaging]'
```

Install from public PyPI (`--index-url https://pypi.org/simple`). Stimela
2.1.4 needs Python 3.13; its native backend fails on 3.14. The frozen
campaigns in `history/` ran on QuartiCal 0.2.7, Stimela 2.1.4 and
python-casacore 3.8.1; there is no extra for that stack since 0.1.0, and
{gh}`history/tools/flagging/requirements.lock` keeps its pins.

## From source

Building needs Rust 1.93 (edition 2024) on `PATH` and Python 3.10 or newer.
`pip install -e .` builds the PyO3 extension through
[maturin](https://www.maturin.rs/), so `cargo` must be on `PATH` at install
time; `RUSTUP_TOOLCHAIN=1.93` pins the toolchain when a newer default is
installed.

```sh
git clone https://github.com/gijzelaerr/rang-core
cd rang-core
python3 -m venv .venv   # or: uv venv -p 3.14 .venv
.venv/bin/python -m pip install --index-url https://pypi.org/simple \
    -e '.[pointing,beam,test,imaging,notebook]' ruff maturin
```

After a Rust change, rebuild the extension with
`.venv/bin/maturin develop --release`; Python never runs Cargo itself.
`bash tools/wheel/build.sh outputs/wheel-<date>-NN` builds the manylinux
wheel in docker, and `python tools/wheel/build.py` builds the native wheel
without docker ({gh}`research/wheel.md`).

## Check the install

```sh
rang-core --version                                           # rang-core 0.1.0
python -c "import rang; print(rang.__version__)"
python -c "import rang.core as c; print(c.backend_name())"   # extension
rang-core -h
```

Native Windows runs the test suite; for campaign work on Windows use a WSL2
checkout on the Linux filesystem ({doc}`contributing`).

## Releases

The version is written once, in `pyproject.toml`; the three `Cargo.toml`s
and their `Cargo.lock` entries, `rang.__version__`, `rang-core --version`
and this site follow it, and {gh}`tests/test_w4_5_release.py` fails when they
disagree. A release bumps the version (and the three lock files, or
`maturin build --locked` fails; {doc}`contributing` has the commands),
adds the version's section to {gh}`CHANGELOG.md`, and is tagged
`v<version>` on `main`. The `wheels` workflow then builds and tests the five wheels and
the sdist, checks that the tag equals the version of every file and of
`pyproject.toml` before any upload, creates the GitHub release with the
changelog section as notes and publishes to PyPI.
