# rang-core

```{image} logo/logo-256.png
:alt: the rang-core mark, an interferogram with one amber source
:width: 160px
:align: right
```

Experimental MeerKAT calibration, flagging and imaging research on one Rust
core, driven from Python (`pip install rang-core`, `import rang`, command line
`rang-core`). "Rang" began as Radio Astronomy Next Generation; *rang* is also
Dutch for *rank*, the first thing the identifiability survey measures.

```{important}
**Status: a tested research demonstrator, not an operational calibrator or a
demonstrated novel algorithm.** The objective is better calibration and
imaging at comparable cost, or comparable quality with substantially less
computation. Neither advantage over the state of the art has been
established.
```

```{warning}
**The flagging experiment is closed as null.** Gain-TV-guided flagging gave
no measurable improvement in calibration or imaging quality over CARACal's
first-pass Tricolour strategy on the evidence available (one MeerKAT L-band
observation with two calibrators, and a four-antenna fixture): of 90
pre-registered calls, 64 are null and 26 undecidable, none better and none
worse, and the TV chain costs 4.6 to 5.9 times the first pass.
See [the research story](research/index.md) and the verdict,
{gh}`research/flagging-verdict.md`.
```

What exists, all tested against archived oracles:

- a Rust core, reached mostly through the compiled extension `rang._core`
  ({doc}`installation` names the exceptions): a read-only Measurement Set reader and an in-place table writer, zarr ingest
  with HTTP range fetch, a port of QuartiCal's full-Jones complex solver, the
  fused residual pass, gain total variation, Tricolour's SumThreshold
  strategies, WSClean's imaging weights and w-stacking gridder, an exact port
  of ducc0's wgridder, and CASA's flux standards;
- one command line, `rang-core STAGE VERB`, that replays and compares every
  archived chain and writes versioned receipts;
- five tutorial notebooks on a public 45 MB MeerKAT fixture;
- research notes, compact result archives and negative results for every
  question asked so far.

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
