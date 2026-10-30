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
| `rang.notebook` | the tutorials' plot, table and steering functions |

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
