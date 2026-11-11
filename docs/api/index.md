# API reference

Generated from the docstrings of every public module under `python/rang/`,
imported with the compiled extension `rang._core` present. The wrappers that
reach the core:

| Module | What it wraps |
| --- | --- |
| `rang.core` | the fused residual pass and the full-Jones complex solver |
| `rang.core_ms`, `rang.core_ms_write` | Measurement Set reads and in-place writes |
| `rang.core_zarr`, `rang.core_fetch` | zarr ingest and the HTTP range fetch |
| `rang.core_workflow` | the core-native solve of the flagging workflow |
| `rang.core_flag` | Tricolour's SumThreshold strategies |
| `rang.core_weights` | WSClean imaging weights and Stokes I |
| `rang.core_grid`, `rang.core_wgridder` | the w-stacking gridder and the exact wgridder |
| `rang.core_imaging` | the imaging track replay |
| `rang.core_cli` | the `rang-core` command line |
| `rang.core_config` | the configuration of the user chain: schema, defaults, refusals |
| `rang.core_pipeline` | the user chain's stages (flag, calibrate, apply, image, selfcal), run directory and resume |
| `rang.core_writeback` | in-place writes to the MS with flag versions and a journal |
| `rang.cal_chain`, `rang.cal_delay`, `rang.cal_gain`, `rang.cal_bandpass`, `rang.cal_fluxscale`, `rang.cal_pol`, `rang.cal_apply`, `rang.cal_selfcal`, `rang.cal_refant` | calibrate's K, G, B, F and polarisation solves, applycal and self-calibration |
| `rang.calmodels` | calibrator models into MODEL_DATA, as CASA's setjy writes them |
| `rang.gemclean` | the `gemclean` console script (GeMClean, the imager) |
| `rang.formats` | the file formats of the tools the core replaces: CASA calibration tables, flag versions, sky models |
| `rang.notebook` | the tutorials' plot, table and steering functions |

What the chain refuses is listed by `rang-core config check CONFIG --all`
(for one MS: `rang-core config check CONFIG MS --all`); the data it refuses
are the cases of {gh}`research/w4-unsupported.md`.

The stage drivers (`core_injections`, `core_actions`, `core_prospective`,
`core_signal`, `core_trend`, `core_campaign*`) and the verbatim extracts of
frozen modules (`core_policy`, `core_influence`, `core_trend_run`, ...)
replay archived campaigns; their docstrings name the report that defines
them.

## Quoted constants

The tutorials quote three constants of `rang.notebook`; here they are as the
code holds them.

### `rang.notebook.survey.STATUS`

The identifiability survey's native status codes, per gain bin:

```{include} ../_generated/status.md
```

### `rang.notebook.gains.GAUGE_NOTE`

```{include} ../_generated/gauge_note.md
```

### `rang.notebook.experiment.DECISION_RULE`

```{include} ../_generated/decision_rule.md
```

## Modules

```{eval-rst}
.. autosummary::
   :toctree: generated
   :recursive:

   rang
```

## Frozen flagging policy (`rang.core_campaign`)

```{include} ../_generated/flagging_rules.md
```

## B1 rules (`rang.notebook.science`)

```{include} ../_generated/b1_rules.md
```
