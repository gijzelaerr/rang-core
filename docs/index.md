# rang-core

```{image} logo/logo-256.png
:alt: the rang-core mark, an interferogram with one amber source
:width: 160px
:align: right
```

**ra-ng aims to be the home for agentic radio astronomy, MeerKAT first.**
rang-core is its first package: flagging, calibration and imaging on one Rust
core, driven from Python and one command line. The PyPI distribution and
command are `rang-core`, the Python package is `rang`, and the imager is
`gemclean`. "Rang" began as Radio Astronomy Next Generation; *rang* is Dutch
for *rank*, the first thing the identifiability survey measures.

```{important}
**Status, November 2026: a tested research demonstrator,
not an operational calibrator.** No novelty is claimed: the goal is better
calibration and imaging at comparable cost, or comparable quality at much lower
cost, and neither has been shown. Two questions are closed as null, as tested: a
gain-TV-guided threshold flagging policy ({gh}`research/flagging-verdict.md`),
and beam and pointing ({gh}`research/b1-3-pointing-selfcal.md`). Three learned
flaggers stopped or failed as frozen ({doc}`research/index`, section 7). The
reference imager GeMClean is faster than WSClean on 16 threads, not always on
one, at 2.0–2.4 times the memory on the real pilot with its current defaults
({gh}`research/g7-defaults.md`). The v0.2.0 acceptance on real data (E2) and
the comparison with CARACal (E3) have not reported; {doc}`limits` lists what is
known.
```

## Where to start

::::{list-table}
:header-rows: 1
:widths: 18 42 40

* - You are
  - Start with
  - Then
* - **New to radio astronomy**
  - {doc}`learn/index`: the introductory notebooks I1–I9, from the radio sky
    to a CLEANed image, polarisation and pulsars, each under a minute on a
    laptop
  - {doc}`concepts/basics`, the {doc}`glossary`, and an agent in a checkout
    that answers from the notebooks and reports ({doc}`agents/answer-a-question`)
* - **An astronomer with a MeerKAT MS**
  - {doc}`installation` (`pip install rang-core`), then {doc}`quickstart`:
    A1 small to a calibrated image with `rang-core run` in under a minute
  - {doc}`howto/index`: your own L-band MS, calibration, flagging,
    checking the result, and the {doc}`limits`
* - **An algorithm scientist or developer**
  - {doc}`developer/index`: the Rust core and the Python layer, building,
    testing
  - {doc}`developer/claims`: the claims rule, oracles and frozen tolerances;
    {doc}`contributing` for the pull-request route
::::

## What is in it

- **A Rust core**, reached through the compiled extension `rang._core`: a
  Measurement Set reader and casacore table writer, zarr ingest with HTTP range
  fetch, QuartiCal's full-Jones solver, CASA's K, G, B, F and polarisation
  solves and applycal, Tricolour's SumThreshold strategies, WSClean's imaging
  weights and w-stacking gridder (CPU, and GPU in a source build), ducc0's
  wgridder, CASA's flux standards and a component predictor.
- **GeMClean**, a reference imager: `gemclean` takes a Measurement Set to FITS
  with WSClean-style options, using the exact image-domain value at each
  minor-cycle step ({gh}`research/gemclean.md`).
- **One command line** ({doc}`cli`): `rang-core flag`, `calibrate`, `apply`,
  `image`, `selfcal` and `run` take a `config.yaml` and your Measurement Set,
  write back into it and resume where a run stopped; `rang-core research STAGE
  VERB` replays each research chain. Every call writes a versioned receipt.
- **The tools' file formats**: CASA calibration tables, QuartiCal stores, sky
  models, H5parm, killMS solutions, CASA flag versions and MVFv4 archives.
- **Oracles.** Each port is gated on reproducing the upstream tool's output,
  within a tolerance written before the run.
- **Notebooks**: nine introductory ones, the MS-to-image tutorial, five on the
  chain on real data and two on the research questions ({doc}`tutorials/index`);
  [the research story](research/index.md) keeps the negative results.

```{toctree}
:hidden:
:caption: Start

installation
quickstart
```

```{toctree}
:hidden:
:caption: Learn

learn/index
concepts/basics
tutorials/index
glossary
```

```{toctree}
:hidden:
:caption: Astronomers

howto/index
casa-users
limits
```

```{toctree}
:hidden:
:caption: Developers

developer/index
developer/claims
contributing
```

```{toctree}
:hidden:
:caption: Reference

cli
mcp
concepts/index
api/index
```

```{toctree}
:hidden:
:caption: Project

research/index
licence
```
