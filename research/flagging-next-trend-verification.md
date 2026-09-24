# Independent saved-gain trend replay verification

Verified2026-09-24 09:52UTC. The completed historical trend branch is
`outputs/tv-next-20260924-01/experiments/trend/result.json`, SHA256
`3f1666fc944e4748af28194131accba23166093a2411b5e70cf4a7252ca5dbe6`.
The source checkpoint is `ec2f17d1dad5f4de65311db19db6daaf1aa4fc2a`.
The [strict audit archive](results/gain-tv-next-trend-audit.json) records562/562
passing checks, distinct from previous injection/response/influence audits, and
embeds the exact audit program with SHA256
`21fe0b3f22639302e036d6399ff4a8de0a80969328ed73110cd5a9deb5ec80ee`.

The audit used the actual pinned Linux/amd64 campaign image offline/read-only,
`sha256:5da4c1b754ddc3a43f57b5cb7f4d8b7bf9aa182c53eeac5c4ac0fb6208ac1d22`.
No QuartiCal solve, WSClean inversion, network acquisition or source/MS write was
performed. Only the new audit archive and this report are project changes.

## What was independently checked

All28 saved-gain replays (seven cases, four frozen scalar receiver-phase patterns)
were reconstructed. A separately indexed NumPy determinant-phase oracle verifies
the native per-station median slopes and exact supported-edge counts. A full
four-entry Frobenius-edge oracle verifies coordinate-normalized temporal/spectral
TV, gap exclusion, missing edges and raw/detrended edge support. Slopes need2/4
temporal/spectral edges; no invalid or non-TRAIN bin was interpolated.

TRAIN-bin membership was independently rebuilt from native row/channel geometry
and both baseline station IDs. Protected cells/rows, autocorrelations,
outside-window cells and validation/TEST overlap were rejected. All actual fits
were available. Exact ordered residual/rawTV/detrendedTV top-six rankings were
replayed from the same frozen admissible rectangles. Poisoning all non-TRAIN
residual-score/guidance values with infinity/NaN left rankings unchanged.

Whole historical source digests, native-library/module SHA values and the full
runtime helper closure matched before and after audit. This includes bytewise
original table/data/flag/weight preservation through the whole-tree receipt;
the trend branch never writes MS tables. The audit used Linux pinned dependencies
for exact ranking replay rather than assuming cross-platform BLAS bit identity.

## Measured distinction, not a quality win

For the approved identity/frequency/time/both patterns, raw normalized polar TV
varied by85.94–88.21% relative to its within-case minimum. Fitted-detrended TV
varied by at most `3.885780586188048e-16` absolute. All21 nonidentity fitted slope
shifts matched their conditional known receiver-phase increments.

| Case | Raw TV max/min | Raw top-six retained under frequency/both | Detrended retained under all patterns |
|---|---:|---:|---:|
| clean | 1.88214 | 0/6 | 6/6 |
| time-burst101 | 1.86539 | 2/6 | 6/6 |
| antenna-local101 | 1.87230 | 0/6 | 6/6 |
| time-burst103 | 1.86562 | 2/6 | 6/6 |
| antenna-local103 | 1.87855 | 0/6 | 6/6 |
| time-burst105 | 1.86029 | 1/6 | 6/6 |
| antenna-local105 | 1.85937 | 0/6 | 6/6 |

The complete ordered detrended lists—not just their sets—were identical across
all four patterns within every case. Residual-only lists were also identical.
Raw time-only patterns retained5–6/6 identity selections. No newly TV-reranked
mask has an actual counterfactual calibration label merely because it appears
in this replay, and no primary full-Jones TV objective was replaced.

## Interpretation limits

Half determinant increments require absolute underlying scalar phase steps below
pi/2. Wrapped Jones determinants alone cannot certify this assumption; larger
steps can alias, as the separate numerical review test explicitly demonstrates.
These are four constructed smooth station-scalar patterns on saved full-Jones
gains from one sparse four-antenna112s observation. They do not prove arbitrary
Jones/beam invariance, finite-iteration QuartiCal equivariance, universal physical
trend separation, independent-observation transfer, better flagging/imaging or a
matched accuracy/runtime improvement. No TEST values or injection truth trained
the slope estimator or rankings. The first imaging launch separately stopped on
a WSClean3.6 legacy-option incompatibility before any FITS was produced; that
failure does not invalidate this completed branch or constitute an imaging result.
