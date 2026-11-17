# The calibration chain's noise-free floor

Status 2026-11-17: **protocol frozen before any test** (sections 1-5).
Results go below it. Anything decided after a result is read is dated and
labelled post hoc. Follows [e2a-3b-k.md](e2a-3b-k.md) sections 9, 10 and
its coordinator decision 4; issue #2, v0.4.0.

## 1. What is open

On e2a-3b-k's noise-free simulations, rang's chain does not reach truth:

| Case | rang U against truth, KGB0 / KGB1 (data-unflagged median) | CASA C, KGB0 / KGB1 |
| --- | --- | --- |
| S0 (static K_T, G_T per scan; B_T = abs of T-T's B0) | 6.4e-3 / 2.9e-4 | 6.5e-3 / 6.0e-4 |
| S0f (as S0, B_T = 1) | 3.7e-4 / 5.7e-4 | – / 2.1e-3 |

At rang's S0f solution, |DATA − M J_U| / |M J_U| has median 6.9e-4
(pass 0) and 7.6e-4 (pass 1) on data-unflagged cells. Known: the
generator is exact on every 50th row (DATA = M J_T to 2.5e-7); K0 is
recovered exactly (0.0 ns); with rang's K shared, CASA's KGB0 equals
rang's to 7e-7. A correct chain on noise-free data should reach the
float32 limit of its data and tables, or a model or discretisation
limit that can be named and sized.

Read before this note was written (orientation, no new solve, composite or
residual): `k_sim.py`, `k_run.py`, `k_score.py`, `nash/simtag.sh`;
`e2avg_common.composite` (it scores `J_p J_q^*`, so a per-antenna phase
gauge cancels); `core/src/cal/apply.rs`'s header and `interpolate_time`
(time interpolation linear between the two nearest solutions with no
regard for scan boundaries, clamped beyond the first and last; float32
values, float32 relative times; K applied as `exp(2 pi i tau (nu -
nu_ref))` with `nu_ref = CHAN_FREQ[nchan // 2]` of the table, in
float64); S0f's `calibrate/summary.json` on nash: K0 and G0 converged
fraction 1.0 (28, 25 iterations), B0 0.995 (21 iterations), K1 0.89 and
G1 0.93 at the 50-iteration cap, B1 0.992; no alternate refant; A0 took
field 0's flagged fraction from 92.3 % to 96.7 % (S0: 94.8 %). The
chain's stop rule is `max_iterations` 50, `stop_criterion` 1e-7,
`stop_fraction` 0.99 (`cal_gain`).

One fact of the simulation's design, read from `k_sim.py`, not yet sized:
S0f's truth K_T and G_T are **constant within a scan and step at the scan
boundary** (scans 9 and 11; scan 10 is another field), while the chain
holds one K0 and one G0 solution per scan at the scan's time centroid and
pre-applies them by **linear interpolation in time across the gap**. Away
from each centroid the pre-applied K0 is a mix of the two scans' delays,
so the data that G0 and B0 see carry a residual phase
`2 pi f(t) (tau_11 − tau_9) (nu − nu_ref)` that no per-scan G or
time-constant B can represent.

## 2. Hypotheses

| # | Hypothesis | Where |
| --- | --- | --- |
| H-S | the simulation: DATA are not `corrupt(M, J_T)` everywhere, or the model the chain solves against is not the truth's model (the column rang writes on the sim copy against `rang-u.ms`'s; a model that is not a point at the phase centre would bring DFT time and frequency smearing against the averaging cells) | the generator, the model column |
| H-I | time interpolation and centroid: per-scan constant truth against linearly interpolated per-scan solutions (section 1); the solution TIMEs (centroids) set the mix | K0, G0 pre-applied in G0, B0, K1 ...; the composite |
| H-C | convergence: the stop rule (1e-7, fraction 0.99, cap 50) stops short on noise-free data | every term; B0 0.995, K1, G1 at the cap |
| H-B | B's channel interpolation or `fillgaps: 70`: scored cells where a B solution channel was filled, not solved | B0, B1 |
| H-F | flag propagation: a flagged K, G or B solution (calflag) changes which cells later terms see, or the scored cells | pre-apply, the composite |
| H-K | delay-and-offset parametrisation and K's gauge: the K table holds delays only (offsets left for G), referenced to the refant | K0, K1, G |
| H-R | refant gauge: a phase reference that differs between truth and solution, or between terms | every term |
| H-P | single precision: float32 data (2.5e-7), float32 tables (delays: `|tau| × 6e-8` ns), float32 interpolation, or a float32 step in a solver | everywhere |

## 3. Data

- **e2a-3b-k's outputs** (`~/rang-data/outputs/e2a-3b-k-20261117/` on
  nash) are read only. Its `sim-s0f-*.ms` carry their runs' state (A0's
  FLAG, MODEL_DATA, CORRECTED_DATA), so no new solve starts from them.
- **S0f′**: S0f rebuilt from `src.ms` by `k_sim.py`'s own `make` (imported,
  not copied), into `~/rang-data/outputs/calchain-floor-20261117/`.
- **S0c**, new, noise-free: the same construction with **scan 11's K_T
  and G_T set to scan 9's**, so K_T and G_T are constant over the whole
  observation (B_T = 1). Every interpolation of a constant is exact.
- **Scored cells.** Composites by `e2avg_common.composite`'s construction
  (every 8th time, pooled field map, `J_p J_q^*`), against truth.
  Primary cell set, common to every arm: field-0 cross cells unflagged in
  `src.ms`'s flag-stage FLAG (hash `e6910ad4…`) and in both tables; the
  e2a-3b-k set (the arm's own post-A0 FLAG) is reported beside it. Median
  and p95, each with and without ID 50 (m053, |tau| near 2,392 ns).
  **Residual**: `|DATA − corrupt(M, J)| / |corrupt(M, J)|` on the same rows
  and cells, M the MS's MODEL_DATA, J tables applied by `cal_apply.apply`
  (pooled; the arm's interpolation). KGB0 = K0 G0 B0, KGB1 = K1 G1 B1.
- **Scorer controls (C-S)**, on every cell subset a test uses: truth
  against truth gives 0 (null); truth with one antenna's G scaled by
  1 + 1e-4 gives 1e-4 ± 1e-6 on that antenna's baselines and 0 elsewhere
  (positive).

## 4. Tests

Floors are read on KGB0 first (pass 0: nothing flagged by A0, no
pre-applied term from a noisy pass) and on KGB1 second. **Machine precision** for an arm: median ≤ 1e-5, with and without ID 50,
and at most 5 % of cells above `max(1e-5, 10 × b)`, b the cell's float32
bound of T8 (forty times the data's 2.5e-7; ID 50's stored delay alone
allows about 4e-4 rad at the band edge). **Carries**: the arm meets
machine precision; **contributes**: it lowers the floor ≥ 2× without
meeting it; **cleared**: the floor moves < 20 %.

**R, reproduction (gates every reading).** S0f′'s DATA equal archived
S0f's bitwise on every row; its FLAG hash is `e6910ad4…`. rang U (this
branch, e2a-3b-k's arm `u` config, default stop rule) on S0f′ gives
tables equal to archived U's (K within 1e-6 ns, G and B within 1e-6
relative) and, with this note's scorer on e2a-3b-k's cell set, KGB0
3.7e-4, KGB1 5.7e-4 and pass 0's residual 6.9e-4 within 5 % each. If not
met, the difference is found before anything else is read.

**T0, the simulation (H-S); no solve.** On S0f′ and S0c:
(a) every field-0 cross row (not every 50th): `|DATA − corrupt(M_T, J_T)| /
|corrupt(M_T, J_T)|` with M_T `rang-u.ms`'s MODEL_DATA and J_T the truth
tables, median and max over cells with nonzero model;
(b) the MODEL_DATA rang wrote on the sim copy against `rang-u.ms`'s,
max |ΔM| / |M|;
(c) MODEL_DATA's phase (max |arg M| over parallel hands) and its time
variation per channel (max over rows of |M / median_t M − 1|).
- **H-S cleared** if (a) median ≤ 1e-6 and max ≤ 1e-5, (b) ≤ 1e-7,
  (c) phase ≤ 1e-6 rad and time variation ≤ 1e-7 (a point at the phase
  centre: no DFT smearing to match).
- Otherwise H-S **carries** if the cells where (a) to (c) fail account for
  the floor (the floor on the other cells ≤ 1e-5), else **contributes**;
  the generator or the model write is then fixed before T2 is read.

**T1, the representation floor (H-I); no solve.** Tables R: the truth's
K and G sampled at rang U's S0f′ K0 and G0 solution TIMEs (one row per
antenna and scan, as U's tables), B = 1. Composite of R (K, G) against
truth on the primary cell set: the floor that per-scan
solutions interpolated linearly reach with nothing solved; also R's K
alone and G alone; and the residual of S0f′'s DATA against R. Then the same
with R's TIMEs moved to the scan's first and last dump (sensitivity to
the centroid).
- **H-I can carry** if R's composite ≥ 0.5 × U's KGB0 (3.7e-4);
  **cannot** if < 0.1 ×; between, **can contribute**. Read with T2.

**T2, the step against interpolation (H-I, decisive); four rang U
runs.** Already known (e2a-3b-k section 10): scored at the G0 solution
times only the floor is unchanged, so the scorer's interpolation is not
it; T2 tests the solve's pre-apply. Arms, a 2 × 2:

| | linear pre-apply (default) | `interp: nearest` in every pre-apply |
| --- | --- | --- |
| stepped truth (S0f′) | R's run | **NS** |
| constant truth (S0c) | **CL** | **CN** |

The nearest arms set `interp: [nearest]` / `[nearest, nearest]` in every
term's pre-apply (A0's own apply is left as the chain does it) and are
scored with `interp="nearest"` (a deviation of the scorer, named). Read:
KGB0 and KGB1, pass-0 and pass-1 residuals, K0 error, A0's added flag
fraction.
- **O-I (interpolation across the step carries)** if CL **and** NS meet
  machine precision on KGB0 and pass 0's residual.
- **O-I′ (the step, not the interpolation)** if CL meets it and NS does
  not: something else that differs between scans (centroids, flags per
  scan) acts through the step.
- **Contradiction**, reported as such, if NS meets it and CL does not.
- Otherwise H-I is read on CL and NS by the words above (contributes /
  cleared against 3.7e-4); CN is the control that a constant truth with
  nearest pre-apply is no worse than CL (within 20 % or both at machine
  precision).
- KGB1 is read the same way against 5.7e-4; a pass-1 floor left after a
  pass-0 one is met goes to T3 (on S0c) and T5 (A0's flags).
- Control inside T2: T1's construction on S0c gives a composite ≤ 1e-6.

**T3, convergence (H-C).** rang U with every chain term at
`max_iterations` 1000, `stop_criterion` 1e-12, `stop_fraction` 1.0
(`e2a-3b-diag`'s `d1_rang_iter.py`, the T-S construction) on a copy of
S0f′, and on S0c if T2 leaves KGB0 or KGB1 above 1e-5.
- **H-C carries** if strict KGB0 meets machine precision on S0f′ (with
  T2 cleared) or on S0c (with T2 contributing); **contributes** if it
  lowers the floor ≥ 2×; **cleared** within 20 %.
- If H-C carries, the converged fractions and iteration counts of the
  default rule are reported per term, and the question whether the
  default should change is left to the owner (no default changes here).

**T4, B's channels (H-B); no solve, U's S0f′ and CL tables.** Per
(antenna, channel), whether pass 0's data hold any unflagged cell on a
baseline > 150 m with that antenna (U's `uvrange`): if not, B0's value
there is filled, not solved. The floor recomputed on scored cells whose
two antennas' B0 channels are both solved.
- Each of T4-T8 also runs C-S on its cell subset.
- **H-B cleared** if that floor is within 20 % of the full one;
  **contributes** if lower by ≥ 2×; **carries** if it meets machine
  precision.

**T5, flags (H-F); no solve.** Count K0, G0, B0 (and K1, G1, B1) solutions
of the 15 antennas that are flagged in U's S0f′ tables and not in truth;
the floor recomputed without baselines to an antenna with any flagged
pass-0 (pass-1) solution.
- **H-F cleared** if the floor is within 20 % of the full one;
  **contributes** ≥ 2× lower; **carries** at machine precision.

**T6, K's parametrisation (H-K); no solve.** On S0f′ and CL: K0 and K1
against truth after referencing both to m022 (ns, median, max); and the
composite of (truth K, U's G0, U's B0) against truth beside U's own
KGB0 (does the floor sit in K or in G, B).
- **H-K cleared** if K0's error ≤ 1e-6 ns and swapping in truth's K
  moves KGB0 < 20 %; **carries/contributes** by the words above applied to
  that swap.

**T7, refant gauge (H-R); no solve.** Control of the scorer: truth
multiplied by a random per-antenna phase (and a random per-antenna
delay) against truth, composite ≤ 1e-6. Then: is the refant (m022)
unflagged in every K0, G0, B0, K1, G1, B1 solution of U on S0f′, and is
`used_alternate_refant` false in every term (read from the tables and
the summary).
- **H-R cleared** if the control holds and no term changes its
  reference; otherwise the terms and intervals that change it are
  listed, and the floor recomputed without them (words as above).

**T8, single precision (H-P); no solve.** Bound: per scored cell, the
float32 errors of the stored tables (K: `2 pi |tau| eps32 |nu − nu_ref|`;
G, B: `eps32` each) plus the data's measured 2.5e-7; its median over the
scored cells. Then, on whatever floor is left after T2 (and T3):
- **H-P carries** that floor if it is ≤ 10 × the bound's median;
  **cleared** if the floor is > 100 ×; between, reported as possible.
- If a floor above 10 × the bound remains and T3 does not explain it,
  the solve is repeated on S0c in float64 from Python (SciPy least
  squares on one scan's G0 with the same pre-applied K0, the same cells)
  as a reference: if SciPy reaches ≤ 1e-6 where rang does not, a float32
  step in rang's solver is the candidate, located and fixed (section 5).

**Outcomes, named.**
- **O-I** (T2): the floor is a property of the simulation design
  (per-scan constant truth, linearly interpolated per-scan solutions),
  not a rang defect; e2a-3b-k's S0 and S0f controls could not be met as
  built. The note then states the floor a noise-free control may require
  (T1's figure), and that a future control uses constant terms or truth
  nodes at the solution times.
- **O-C**: T3 carries (with T2 cleared or contributing): the stop rule.
- **O-IC**: T2 and T3 each contribute and together carry.
- **O-B, O-F, O-K, O-R, O-S**: the named test carries or contributes.
- **O-P**: what is left is float32 (T8).
- **O-0**: none carries and none contributes: null, the floor unlocated,
  recorded as such with every figure.

## 5. Not changed, and records

No default changes. A rang defect found by a test (O-S in the model
write, O-B, O-F, O-K, O-R, or a float32 step) is fixed with a test, and
the fix is shown to leave every archived gate unchanged or each change is
explained; anything else is a documented limit.

Scripts in `research/results/calchain-floor/`, outputs in
`~/rang-data/outputs/calchain-floor-20261117/` on nash; e2a-3b-k's outputs
read only. Every job through the main checkout's `tools/heavy_lock.py`
(slots equal to the cores used), under `nice -n 19 ionice -c3`, from this
branch's venv; wall times in `research/tool-timings.md` (host nash).

## 6. Correction 2026-11-17 13:50, before any test was read

T7's scorer control as frozen ("a random per-antenna phase") is wrong:
`J_p J_q^*` cancels a phase or delay **common to every antenna** (what a
change of reference antenna does: every solution's phase minus the
refant's), not a per-antenna one. T7's control is therefore a random
common phase and a random common delay applied to truth's G and K, against
truth, ≤ 1e-6; and, as a check that the scorer is not blind, a random
per-antenna phase of 1e-3 rad, which must read about 1e-3. Nothing else
changes.

## 7. Addendum 2026-11-17 14:10, post hoc (after T0, T1, R and T2's four arms were read; before `cf_pass1.py` and CL's strict arm were read)

Read so far (section 8): pass 0 meets machine precision in CL and NS, so
O-I holds for KGB0. Pass 1 does not follow: NS's KGB1 is 8e-8, but CL's is
3.5e-3 and CN's 7.7e-4, with a K1 solution 2,263 ns from truth in CL (ID
50's delay is near the 2,392 ns ambiguity, `1 / (2 × 209 kHz)`) and K1 at
the 50-iteration cap (converged fraction 0.94). T5 as frozen is
unreadable: every antenna has B0 channels flagged where data exist
(minblperant or SNR), so "without antennas with any flagged pass-0
solution" leaves no cells.

Added, before reading them:
- **P1** (`cf_pass1.py`, no solve) on CL, CN and R's run: every K1
  solution more than 1e-3 ns from truth (referenced to m022), and each
  pass-1 term swapped alone into truth. The pass-1 floor is **in K1** if
  truth with the arm's K1 alone reads ≥ 0.5 × the arm's KGB1; **in G1 or
  B1** likewise.
- **T3 on S0c** (pre-registered in T2 for a pass-1 floor) is running; read
  by T3's words against CL's 3.5e-3.
- **T5′**: T5 with K and G solutions only (B's flags are excluded from the
  composite cell by cell already), on every arm.

## 8. Addendum 2026-11-17 14:20, post hoc (after P1 and the K1 cell counts were read; before `cf_k1solve.py` ran)

P1 (section 9) puts CL's pass-1 floor in B1 (truth with CL's B1 alone
3.2e-3; with its K1 alone 0 median), and the one K1 solution far from truth
is ID 50's interval 7 (1,293 ns X, 2,263 ns Y; truth 0.1 ns), the first
interval of scan 11, where ID 50 has 5,202 unflagged X cells on 37
baseline-dumps against 34,000-66,000 elsewhere. K is solved jointly over
all intervals and stops when 99 % of solutions have converged, or at 50
iterations; CL's K1 stopped at 50 with 0.94.

- **P2** (`cf_k1solve.py`): CL's K1 re-solved by `cal_delay.gaincal` on
  CL's MS (read only) with CL's G0, B0 pre-applied, (a) at the chain's
  rule, (b) strict (1000, 1e-12, 1.0), (c) from the FFT start alone (0
  iterations). Control: (a) equals CL's K1 table (max ≤ 1e-6 ns), else P2
  is not read.
- Reading for ID 50's interval 7: **non-convergence** if (b) reaches truth
  (≤ 1e-3 ns) where (a) does not; **a wrong start** if (c) is already far
  (> 100 ns) from truth and (b) stays there (a local minimum of a
  noise-free cost); **a walk** if (c) is near truth and (a), (b) leave it.
- T3 on S0c (CL strict), already running, is read by T3's words.
