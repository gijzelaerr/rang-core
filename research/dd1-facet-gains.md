# DD1: direction-dependent gains per facet, scoping note and piece 1

Issue #15 (v0.5.0, "the first direction-dependent piece"). The owner chose the
direction on 2026-11-23: faceted imaging with per-facet gain solutions,
amplitude and phase per facet, as QuartiCal's direction-dependent terms do.
Branch `dd-facets-15`. Sections 1-6 are frozen 2026-11-23, before any code
that tests them; later changes are dated amendments at the end, labelled post
hoc where they could have seen a result.

Status: **proposed** (section 7 records the measurement when it exists).

## 1. What exists, and what earlier work says

- **Solvers.** `core/src/solve.rs` (full-Jones `complex`) and
  `core/src/cal/diag.rs` (`diag_complex`, `phase`) are ports of QuartiCal
  0.2.7's kernels for **one direction-independent term**; `solve.rs`
  reproduces QuartiCal to 1.4e-15 ([core-phase2](core-phase2.md)), `diag.rs`
  is gated in class A against QuartiCal ([C2a](c2a-gain.md), section 2).
  Neither has a direction axis.
- **Predict.** `predict_components` (`core/src/predict.rs`) is checked
  against Crystalball and CASA `setjy` ([C3a](c3a-models.md), O3a:
  `|V_rang - V_cb| <= 1e-6 x peak`). Piece 1 uses it to make both the
  simulated data and the per-facet models; that shared use is covered by the
  C3a gate, not by this note.
- **DDFacet and killMS** were judged not worth a faithful port
  ([ddfacet-feasibility](ddfacet-feasibility.md): exact gridder first, facets
  later, DDFacet and killMS as oracles). U3 found DDFacet's Hogbom diverges
  with more than one facet ([upstream-saopicc](upstream-saopicc.md)), which
  weakens DDFacet as an imaging oracle; it stays a candidate for the real
  field (DD4), not for parity.
- **Floor-5** ([floor-5](floor-5.md)) fitted per-facet steady complex gains
  on the four central facets of a real field (arm H3c, T_D|A) and left them
  **unresolved**: not specific against model incompleteness. A DD solve only
  helps where the facet model is good; DD3 and DD4 below are designed around
  that.

## 2. The plan in pieces (sized honestly)

| Piece | What | Oracle | Size |
| --- | --- | --- | --- |
| **DD1 (this note)** | DD `diag_complex` solve: one gain per (solution interval, antenna, direction, hand), all directions solved together against the summed per-facet model, as QuartiCal 0.2.7 with `G.direction_dependent=true`; Voronoi facet assignment of a component sky and the per-facet model predict | QuartiCal 0.2.7, same MS and settings | M |
| DD2 | facet imaging: Voronoi facets around the DD directions, each facet's visibilities corrected by its facet's gains (or the model corrupted by them) in GeMClean's major cycle; solutions out as H5parm (DF-IO writer) | WSClean 3.7/3.8 `-facet-regions` with `-apply-facet-solutions` on the same H5parm; per-pixel image tolerance frozen in DD2's note | L |
| DD3 | the DD self-calibration loop on a simulation with DD errors: facet CLEAN model, DD1 solve, DD2 image, repeat | QuartiCal + WSClean facets chain; residual rms around the off-axis sources against truth | M |
| DD4 | a real MeerKAT field with a bright off-axis source (ESO137 or E2-N) after DI self-calibration | CARACal-style QuartiCal dE + WSClean facets (DDFacet/killMS as a second, weaker oracle) | L |

DD2-DD4 are listed so the first piece is shaped for them; each gets its own
frozen section before it is built. Nothing here claims novelty: DD1 is parity
with QuartiCal; any claim of better DD calibration waits for DD3/DD4 and the
novelty rule in `AGENTS.md`.

## 3. DD1: hypothesis and what is not claimed

**Hypothesis.** A Rust port of QuartiCal 0.2.7's `diag_complex` kernel with a
direction axis reproduces QuartiCal's direction-dependent solve (gains,
flags, iteration count) on a seeded simulation with direction-dependent
errors, and recovers the simulated gains on its noiseless twin.

**Why `diag_complex`.** It is amplitude and phase per hand, what the owner
asked for, and what CARACal's dE step solves; per direction it has two
complex unknowns per antenna instead of four, so it is better constrained;
and `diag.rs` is self-contained (its helpers are copied, not shared with the
bit-gated `solve.rs`), so a new module beside it changes no existing path.

**Not claimed.** No imaging (DD2), no self-calibration loop, no real data, no
speed or quality gain over QuartiCal (cost is reported, not gated), no
`complex` (full-Jones) DD term, no DD term in a chain with DI terms, no
robust reweighting or MAD flags (rang's DI ports exclude them too).

**The oracle's algorithm, read in the source before freezing**
(`quartical/gains/complex/diag_kernel.py`, 0.2.7):

- The residual of each cell is `V - sum_d G_p,d M_d G_q,d^H` over all
  directions at the gains entering the iteration; each direction's `J^H J`
  and `J^H r` are accumulated from that one residual with its own operator
  `G_q,d M_d^H`. Directions are not coupled in `J^H J` (block-diagonal: a
  Jacobi step across directions).
- `finalize_update` **halves the update on every iteration** for a DD term
  (`dd_term or loop_idx % 2 == 0`), not only on even ones as in the DI case.
- `G.pinned_directions` (default `[0]`) skips the update of the listed
  directions; their gains stay at the identity. Flag ladder, stop fraction
  and `finalize_gain_flags` run over all `(t, f, ant, dir)` gains.
- `reference_gains` references each direction to the reference antenna's
  gain **of the same direction**.
- `apply_gain_flags_to_flag_col` is skipped for a DD term.

Port: a new module `core/src/cal/diag_dd.rs` (gains laid out
`(time bin, freq bin, antenna, direction)` as QuartiCal's), the model
`nrow x nchan x ndir x 4` complex, a Python binding beside `cal_gain_solve`,
pinned directions supported.

## 4. DD1: data (seeded simulation)

`tools/oracles/dd1/sim.py`, seed `1501` (sky), `1502` (gains), `1503`
(noise). One MS with a noisy `DATA`, a noiseless twin `DATA_NF`, and one model
column per direction `MODEL_D0..MODEL_D3`.

- MeerKAT, all 64 antennas (`rang/data/meerkat.itrf.txt`), 2016 baselines, no
  autocorrelations; 48 integrations of 8 s (one scan, field at RA 250.0°,
  Dec −60.0°, near ESO137); 16 channels of 1 MHz from 1292.5 to 1307.5 MHz;
  four correlations, linear feeds.
- Directions (facet centres, offsets from the phase centre in degrees):
  d0 (0, 0), d1 (+0.6, +0.3), d2 (−0.5, +0.5), d3 (0.0, −0.7). Sky: one point
  source at each centre (1.0, 2.0, 0.8, 0.4 Jy) and 24 points of 10-100 mJy
  uniform in a 1.6° box (seed 1501), spectral index −0.7 at 1.3 GHz,
  unpolarised. Each component belongs to the facet of its nearest centre
  (Voronoi); `MODEL_Dd` is the predict of facet d's components. The model is
  complete (the sum of the four columns is the sky): DD1 tests the solver,
  not model incompleteness (that is DD3).
- Truth gains: per (block of 4 integrations, antenna, direction, hand),
  constant over frequency: amplitude `exp(0.1 a)`, phase `0.5 b` rad, with
  `a`, `b` smooth in time per (antenna, direction, hand) (a random-phase
  sinusoid plus offset, seed 1502), so they are piecewise constant on the
  solution grids of section 5 and the noiseless solve has an exact answer.
- Noise: complex Gaussian, σ = 0.11 Jy per real and imaginary part per
  correlation (MeerKAT SEFD 443 Jy, 1 MHz, 8 s), seed 1503; `WEIGHT_SPECTRUM`
  = 1/σ², no flags.

## 5. DD1: cases, oracle and frozen tolerances

**Oracle.** QuartiCal 0.2.7 (`quartical==0.2.7` from PyPI in a uv venv on
WSL, numba 0.68.1, as RV1's `venv-qc027`), `solver.terms=[G]`,
`G.type=diag_complex`, `G.direction_dependent=true`,
`input_model.recipe=MODEL_D0:MODEL_D1:MODEL_D2:MODEL_D3`,
`solver.iter_recipe=[50]`, `solver.convergence_criteria=1e-7`,
`solver.reference_antenna=0`, `solver.robust=false`, `mad_flags.enable=false`,
`output.flags=false`, `input_ms.weight_column=WEIGHT_SPECTRUM`,
`input_ms.time_chunk=0`, `input_ms.freq_chunk=0`, `solver.threads=1`,
`dask.threads=1`, `dask.scheduler=single-threaded`. Rang: the same
iterations, criterion, stop fraction 0.99, reference antenna 0 and intervals.

| Case | Column | Intervals | Pinned |
| --- | --- | --- | --- |
| P1 | `DATA` | `time_interval=4`, `freq_interval=0` | `[]` |
| P2 | `DATA` | `time_interval=1`, `freq_interval=4` | `[]` |
| P3 | `DATA_NF` | `time_interval=4`, `freq_interval=0` | `[]` |
| P4 | `DATA` | `time_interval=4`, `freq_interval=0` | `[0]` (QuartiCal's default) |

**Gate A, parity (every case), C2a's class A restated:** gain flags exact;
every complex gain entry, and every parallel-hand per-direction baseline
product `g_p,d,h conj(g_q,d,h)` over pairs QuartiCal leaves unflagged, within
`1e-6` absolute (both referenced by QuartiCal's rule); iteration count equal;
converged fraction equal to `1e-12`.

**Gate T, truth (P3, noiseless):** gauge-free comparison on the
per-direction products `P_pq,d,h = g_p,d,h conj(g_q,d,h)` against the truth's
over all baselines, directions, hands and intervals: max
`|P_solved - P_true| / |P_true| <= 1e-4`. On P1 and P2 the same statistic's
median and 95th percentile are reported against the noise expectation, not
gated.

**Cost (reported, not gated):** wall time and peak memory of rang's solve
(in-process, 1 and 8 threads) against `goquartical`'s whole process and its
solver time from its log, on glacier under `heavy_lock`.

## 6. DD1: decision rule (named before any result)

- **Pass**: gate A holds on P1-P4 and gate T on P3. The DD term is ported;
  DD2 starts from its solutions.
- **Port failure**: gate A fails on any case. Recorded with the first
  differing quantity; fixed and re-measured as a dated amendment (the
  tolerance is not loosened without a stated cause, such as summation order
  across directions under QuartiCal's `fastmath`).
- **Algorithmic non-convergence (null for the method, not for the port)**:
  gate A holds but gate T fails on P3 with the solve at 50 iterations. The
  Jacobi-style DD update with its permanent halving is then slow on this
  layout; recorded as a property of QuartiCal's algorithm, and a better DD
  update (coupled directions, or no halving) becomes a candidate for a later
  proposal, not part of DD1.
- **Truth failure**: gate A holds, the solve converged before 50 iterations,
  and gate T fails: the simulation or the gauge comparison is wrong;
  investigated before anything else.

## 7. Measured result

Not yet measured.
