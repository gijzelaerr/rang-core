# Controlled RFI injections on real MeerKAT L-band data

This experiment tests whether full-matrix gain TV reacts usefully to known
added contamination, separately from whether the present TV-guided proposal
policy identifies that contamination. It supplements, rather than replaces,
the unmodified-real-data negative result in [flagging.md](flagging.md).

## Implemented controls

The checksum-pinned SKA pointing fixture, scan 9, provides the same four-antenna
MeerKAT L-band observation, 1070–1497.8 MHz window and fixed seed-7 splits as the
original experiment. Every solve uses QuartiCal `G.type=complex`, a complete 2×2
Jones matrix, two-integration/32-channel bins and 50 iterations. Polar gauge
alignment is valid for the explicitly unpolarized scalar sky approximation.

There is one clean-reference solve. For each morphology and strength, a fresh
copy receives additive contamination only on eligible, originally fully
unflagged, cross-correlation training row-channel samples. Validation and test
DATA are unchanged. Morphologies are:

- A narrow contiguous frequency patch persistent across training times.
- A single-integration time burst spanning a contiguous frequency patch.
- A narrow frequency patch on baselines incident on one selected antenna.

The three morphologies use injection seeds 19, 20 and 21. Strengths 3 and 10
mean additive complex amplitude divided by the square root of the original
per-correlation weight. These are inverse-weight units, not a measured
thermal-noise-sigma claim. All four correlations receive a coherent phasor
with small seeded phase jitter. These deliberately simple morphological
controls are not a physical electromagnetic RFI simulation.

Each contaminated copy receives three controls:

1. Contaminated training DATA, no additional flags.
2. An injection-mask oracle which flags exactly the added contamination.
3. The existing independently selected TV-guided policy, including an unguided
   residual-only ablation and a no-change candidate.

The oracle is a diagnostic, not an input or training target for policy selection.
It is an oracle only for the synthetic additions, not for unlabeled RFI already
present in the real observation. Removing injected samples also removes their
original signal/noise contribution, so oracle gains need not equal the clean
reference exactly.

## Selection and evaluation

Policy selection retains the existing objective:

`fixed_contaminated_support_TV / TV0 + 2 × added_fraction + 0.25 × validation_MSE / validation_MSE0`.

It requires all contaminated-baseline gain edges to remain supported, at most
2% additional training flags, and clean-validation degradation no greater than
1%. Features use weighted training residuals and gain-TV maps only. Neither the
known injection mask, oracle gains nor test residuals choose a policy.

Separate reported diagnostics compare every control against the clean
reference using its frozen gain-edge support and normalization scale. They
include TV, weighted clean validation/test prediction error, gauge-aligned
gain distance and visibility-prediction distance to the clean solve. Missing
gain support is counted and the distance/TV comparison becomes unavailable;
it is never improved by silently dropping invalid bins.

Known-injection recovery is measured exactly. Additional flags outside the
injection mask are reported separately: they are not proven false positives
because the original observation lacks complete contamination labels.

## Safety and reproduction

The original archive, extracted input and immutable `original.ms` are never
written. Every case has its own working MS, full original-DATA backup before
the sole injection DATA write, exact sparse injection values/mask, manifest,
state and before/after flag snapshots. Original cell and row flags always
remain a lower bound. Final case `work.ms` files deliberately retain synthetic
contamination and must not be mistaken for a scientific calibrated product.
Exact comparisons verify unchanged held-out/protected DATA, original flags,
and original source/copy file digests.

Run from the checkout using the existing pinned Docker image:

```sh
bash tools/flagging/run-injections.sh outputs/tv-injections-pilot-01
```

The script runs [the Stimela2 recipe](../recipes/tv-flagging-injections.yaml),
mounts the checkout read-only, permits writes only beneath `outputs`, disables
network access, and uses an isolated compilation cache. Output directories
must be fresh. To reduce the pilot, pass Stimela parameters, for example
`'patterns=[narrowband]' 'strengths=[10]'`.

The full result, commands, gains, truth, checkpoints and backups are archived
under the run directory. Runtime measurements are Linux amd64 under emulation
on the development machine, not evidence of native performance or novelty.

## Scientific limits

This is a short four-antenna reference pointing scan with an approximate
phase-centre point-source model, not an imaging-quality benchmark. One seed
per morphology and two strengths establish diagnostic intuition, not statistical
significance. Better sky-model adequacy, established-flagger comparisons and
larger representative MeerKAT observations are independent follow-up tests.

Measured outcomes are retained in [the compact result archive](results/gain-tv-injections.json).

## Measured first pilot

`outputs/tv-injections-pilot-01` completed the entire Stimela2 recipe. The clean
reference TV was 0.1474368701. All controls retained fixed clean gain-edge
support, and all training/validation/test prediction counts were valid.

| Injection | Strength | Actual training occupancy | Contaminated TV | Oracle TV |
| --- | ---: | ---: | ---: | ---: |
| Narrowband | 3 | 1.001% | 0.147592 | 0.147845 |
| Narrowband | 10 | 1.001% | 0.148604 | 0.147845 |
| Time burst | 3 | 0.515% | 0.147703 | 0.147535 |
| Time burst | 10 | 0.515% | 0.149009 | 0.147535 |
| Antenna-local | 3 | 0.834% | 0.147833 | 0.148676 |
| Antenna-local | 10 | 0.834% | 0.149428 | 0.148676 |

The oracle reduced TV in four cases but increased it in two weak-contamination
cases. Removing a small number of measurements can increase solution noise;
TV cannot be assumed to fall for every truly contaminated sample. Actual
occupancy differs from the requested 0.5% because a fixed-width contiguous
patch can contain more eligible samples than the band-average estimate.

The present policy selected **no additional flags in all six cases**. After
selection, a separate report scored archived proposals against injection truth.
The highest-recall strong-contamination proposals recovered 66.8% of narrowband,
53.7% of time-burst and 40.0% of antenna-local injections. They also flagged
many samples outside the known injection mask and increased TV; their recovery
numbers do not establish a scientifically improved selection.

The strength-10 time burst is especially informative. Its injection-mask oracle
has diagnostic objective 1.24873479, below no-change 1.25, with admissible clean
validation error. Thus at least one beneficial action exists under the current
objective which the proposal family fails to find. The highest-recall actual
proposal flags 204 injected and 1075 outside-injection samples, and has worse
objective 1.32341949. This supports testing counterfactual patch-action models
on this archived contaminated copy without reading injection truth.

All source/original file digests and flag protection audits passed. Full DATA
backups precede every injection write. The original calibration module is
preserved in `outputs/flagging-backups/20260923-injection-implementation/code.tar.gz`
with SHA256 `f5b322bb025f87420737a7ecb0b005b33b406bd463c2d4587dad226cf89b5c4e`
for the module itself. The post-selection reporting helper was added afterward,
unit-tested, and independently exercised on the completed immutable diagnostics;
the tracked result records its separate module hash. No calibration was rerun
or policy reselected using truth diagnostics.

The experiment establishes useful positive and negative controls, not improved
real-data flagging, imaging quality, statistical significance or novelty.
