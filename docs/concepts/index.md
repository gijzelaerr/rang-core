# Concepts

rang follows one chain from raw visibilities to a decision. Each stage is a
Rust kernel in the extension `rang._core` behind a thin Python wrapper, and
each was validated against an archived run of the upstream tool it replaces
before it was used for anything else.

| Stage | Wrapper | Ported from or checked against |
| --- | --- | --- |
| Read a Measurement Set | `rang.core_ms` (`rang.core_ms_write` writes) | python-casacore 3.8.1, column for column |
| Read zarr, fetch by HTTP range | `rang.core_zarr`, `rang.core_fetch` | numcodecs/blosc; the archived whole-tile fetch |
| Solve gains | `rang.core_workflow`, `rang.core` | QuartiCal 0.2.7 `complex` |
| Gain total variation (TV) | `rang.core_policy`, `rang.notebook.gains` | the frozen `flagging` module |
| Flag with SumThreshold | `rang.core_flag` | Tricolour 0.2.1, flag for flag |
| Imaging weights, Stokes I | `rang.core_weights` | WSClean 3.6, bit-identical |
| Grid and image | `rang.core_grid`, `rang.core_wgridder` | WSClean 3.6 w-stacking; ducc0 0.42 wgridder |
| Replay the imaging track | `rang.core_imaging` | the archived WSClean run |

```{toctree}
:maxdepth: 1

ingest
gains
flagging
imaging
```

The {doc}`tutorials <../tutorials/index>` walk through the same chain on real
data, and the {doc}`command line <../cli>` replays the archived campaigns.
