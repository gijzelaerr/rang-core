# rang-core

```{image} logo/logo-256.png
:alt: the rang-core mark, an interferogram with one amber source
:width: 160px
:align: right
```

**ra-ng aims to be the home for agentic radio astronomy, MeerKAT first.**
rang-core is its first package: flagging, calibration and imaging on one Rust
core, driven from Python. The PyPI distribution and command line are `rang-core`;
the Python package is `rang` ({doc}`installation`). "Rang" began as Radio Astronomy Next Generation, and *rang* is Dutch
for *rank*, the first thing the identifiability survey measures.

```{important}
**Status, November 2026: a tested research demonstrator,
not an operational calibrator.** No novelty is claimed: the goal is better
calibration and imaging at comparable cost, or comparable quality at much lower cost, and
neither has been shown. Two questions are closed as null, as tested: a
gain-TV-guided threshold flagging policy ({gh}`research/flagging-verdict.md`), and
beam and pointing ({gh}`research/b1-3-pointing-selfcal.md`). A flagger trained on
gain TV stopped at its go/no-go test on one observation, before any training
({gh}`research/f1-tv-flagger.md`). A deeper
field model (an external
catalogue) is the first condition for reopening beam and pointing on real data.
The reference imager GeMClean beats WSClean's time on 16 threads, not always on one, at
3–5 times the memory ({gh}`research/gemclean-speed.md`).
```

What it is:

- **A Rust core**, reached through the compiled extension `rang._core`: a
  Measurement Set reader and casacore table writer, zarr ingest with HTTP range
  fetch, QuartiCal's full-Jones solver, Tricolour's SumThreshold strategies,
  WSClean's imaging weights and w-stacking gridder (CPU, and
  GPU in a source build), ducc0's
  wgridder, CASA's flux standards and a component predictor.
- **GeMClean, a reference imager.** `gemclean` takes a Measurement Set to FITS with
  WSClean-style flags, using the exact image-domain value at each minor-cycle step
  ({gh}`research/gemclean.md`). The wheel installs it as the command `gemclean`
  ({gh}`research/g8-wheel.md`).
- **A Python package and command line** ({doc}`cli`). `rang-core flag`, `calibrate`,
  `apply`, `image`, `selfcal` and `run` take a `config.yaml` and your Measurement Set,
  write back into it and resume where a run stopped; `rang-core research STAGE VERB`
  replays, compares and archives each research chain. Every call writes a versioned
  receipt.
- **The tools' file formats**: CASA calibration tables, QuartiCal stores, sky
  models, H5parm, killMS solutions, CASA flag versions and MVFv4 archives.
- **Oracles.** Each port is gated on reproducing the upstream tool's output.
- **New to radio astronomy?** Nine introductory notebooks, from the radio sky
  through calibration and CLEAN to pulsars ({doc}`tutorials/index`), start
  with {doc}`tutorials/notebooks/i1-radio-sky`.
- **Start here:** {doc}`tutorials/notebooks/00-ms-to-image` takes a simulated
  MeerKAT Measurement Set to a calibrated image with `rang-core run` and `gemclean`,
  section by section, in under a minute.
- **Tutorials and research.** Five more tutorial and two science notebooks
  ({doc}`tutorials/index`) on a public 45 MB MeerKAT fixture and the Rust pointing simulation;
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
