# rang-core

```{image} logo/logo-256.png
:alt: the rang-core mark, an interferogram with one amber source
:width: 160px
:align: right
```

**MeerKAT calibration, flagging and imaging research on one Rust core, driven
from Python.** The project, PyPI distribution and command line are `rang-core`;
the Python package is `rang` ({doc}`installation`; the first PyPI release, v0.1.0,
is pending). "Rang" began as Radio Astronomy Next Generation, and *rang* is Dutch
for *rank*, the first thing the identifiability survey measures.

```{important}
**Status, November 2026: a tested research demonstrator,
not an operational calibrator.** No novelty is claimed: the goal is better
calibration and imaging at comparable cost, or comparable quality at much lower cost, and
neither has been shown. The gain-TV flagging experiment is closed as null
({gh}`research/flagging-verdict.md`). The beam-and-pointing question is open:
B1-2 found per-antenna pointing constrainable on real data
({gh}`research/b1-2-identifiability.md`), and B1-3 is running.
```

What it is:

- **A Rust core**, reached through the compiled extension `rang._core`: a
  Measurement Set reader and casacore table writer, zarr ingest with HTTP range
  fetch, QuartiCal's full-Jones solver, Tricolour's SumThreshold strategies,
  WSClean's imaging weights and w-stacking gridder (CPU and GPU), ducc0's
  wgridder, CASA's flux standards and a component predictor.
- **A Python package and command line.** `rang-core STAGE VERB` ({doc}`cli`)
  replays, compares and archives each chain and writes a versioned receipt.
- **The tools' file formats**: CASA calibration tables, QuartiCal stores, sky
  models, H5parm, killMS solutions, CASA flag versions and MVFv4 archives.
- **Oracles.** Each port is gated on reproducing the upstream tool's output.
- **Tutorials and research.** Five tutorial and two science notebooks
  ({doc}`tutorials/index`) on a public 45 MB MeerKAT fixture and the Rust toy;
  [the research story](research/index.md) keeps the negative results.

```{toctree}
:maxdepth: 2
:caption: Using rang

installation
concepts/index
cli
tutorials/index
api/index
```

```{toctree}
:maxdepth: 2
:caption: Project

research/index
contributing
licence
```
