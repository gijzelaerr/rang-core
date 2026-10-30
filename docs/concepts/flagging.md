# Flagging: SumThreshold, the Tricolour port and the TV policy

## SumThreshold and Tricolour

Radio-frequency interference (RFI) shows up as bright, narrow structure in
time and frequency. SumThreshold (Offringa et al. 2010) flags runs of
samples whose summed amplitude exceeds a threshold that falls as the run
grows, so faint but extended RFI is caught along with bright spikes.
Tricolour applies it per baseline to a polarised intensity, together with
static masks of known RFI bands, background estimation, flag dilation and
uniformity rules, in a sequence that a strategy YAML describes.

`rang.core_flag` runs Tricolour 0.2.1's `polarisation` strategy, ported to
Rust (`core/src/sumthreshold.rs`), on in-memory arrays: a strategy YAML of
the kind CARACAL ships, the two static masks shipped as package data under
Tricolour's BSD notice, and the rows, flags and metadata of one field and
scan. On all four archived controls the port reproduces Tricolour flag for
flag, including every intermediate stage
({gh}`research/core-d-tricolour.md`). `flag_rows(..., want_stages=True)`
returns each step's window, which tutorial 2 uses to show what every step
adds and clears.

## The TV-guided policy

The experiment asked whether gain smoothness can guide flagging. A training
sample is proposed when its robust residual score satisfies `z ≥ 2` and

$$z\,[1+\alpha\min(h/\operatorname{median} h,5)]>\tau,$$

with `h` the TV guidance ({doc}`gains`), `τ ∈ {8, 5, 3}` and
`α ∈ {0, 1, 3}`; `α = 0` is the unguided control. At most 2 % of training
samples are added and the original flags are an immutable lower bound. Each
candidate mask is re-solved and scored on TV, the flagged fraction and the
validation error; held-out test cells never choose anything
({gh}`research/flagging.md`).

The decision rule, frozen before every real-data run
(`rang.notebook.experiment.DECISION_RULE`):

```{include} ../_generated/decision_rule.md
```

## The result

Closed as null ({gh}`research/flagging-verdict.md`): the frozen policy never
selected a TV-guided (`α > 0`) mask on the fixture or on any LUNO campaign,
none of 90 pre-registered calls is better or worse than CARACal's first pass,
and the TV chain costs 4.6 to 5.9 times as much. Tutorial 5 replays the
experiment and reads the real calls from the archives.
