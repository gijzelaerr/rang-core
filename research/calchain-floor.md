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

## 9. Results (measured 2026-11-17 on nash)

Receipts: [results/calchain-floor/receipts/](results/calchain-floor/receipts/);
outputs `~/rang-data/outputs/calchain-floor-20261117/` on nash. Every job
rc 0. Medians on the primary cell set (flag-stage FLAG) unless labelled.

**Controls.** R met: S0f′'s DATA equal archived S0f's bitwise on all
41,978 rows, FLAG equal to `src.ms`'s; rang U on S0f′ reproduces archived
U's six tables bitwise (0 flags differ, max difference 0); with this
note's scorer on e2a-3b-k's cells (the arm's post-A0 FLAG) KGB0 3.70e-4
and KGB1 5.65e-4, as archived. Pass 0's residual is 7.21e-4 on the
primary cells (e2a-3b-k's 6.9e-4, +4.6 %; its cell set was not
recorded) and 3.70e-4 on the post-A0 cells. C-S met on every arm: null 0;
G of one antenna × (1 + 1e-4) reads 1.0004e-4 on its baselines, 0
elsewhere; T7's common phase and 2.9 ns common delay read 1.4e-7
(median; max 7.3e-7); a ±1e-3 rad per-antenna phase reads 2.0e-3.

**T0 (H-S): cleared.** On every field-0 cross row of S0f′ and S0c
(8.9e7 cells each) DATA equal `corrupt(M_T, J_T)` exactly (0.0; the
generator and the scorer share `cal_apply`). MODEL_DATA is real (phase 0)
and constant in time per channel (a point at the phase centre: no DFT
smearing), and the column rang wrote on every arm copy equals
`rang-u.ms`'s exactly.

**T1 (H-I, no solve).** Truth sampled at U's K0, G0 solution TIMEs and
interpolated linearly: median 0, p95 1.0e-2, max 2.9e-2 (S0f′). The
median is 0 because the outer half of each scan is clamped to its own
scan's value; the inner halves (scan 9 after its centroid, scan 11 before
its) carry up to 2.9e-2. By T1's frozen median rule H-I "cannot carry"
(0 < 0.1 × 3.7e-4); the rule was blind to an error confined to half the
cells, and T2 decides. On S0c the same construction gives 0 (max 0):
T2's internal control met.

**T2 (H-I, decisive), pass 0: O-I.**

| Arm | KGB0 median / p95 / max | pass-0 residual median | machine precision |
| --- | --- | --- | --- |
| stepped, linear (R's run) | 7.21e-4 / 9.4e-3 / 3.0e-2 | 7.21e-4 | no |
| stepped, nearest (NS) | 0 / 1.1e-7 / 2.8e-7 | 0 | yes |
| constant, linear (CL) | 0 / 8.2e-8 / 2.5e-7 | 0 | yes |
| constant, nearest (CN) | 0 / 8.2e-8 / 2.5e-7 | 0 | yes |

The pass-0 floor is the linear pre-apply of per-scan solutions across
the step of a per-scan constant truth: removing the step (CL) or the
interpolation (NS) each takes KGB0 from 7.2e-4 to the float32 limit of
the data (max 2.8e-7, under 10 × the T8 bound for every cell). By T6 on
R's run the floor sits in G0 (truth with U's G0 alone 1.2e-4) and B0
(alone 3.4e-4), not in K0 (5e-8): G0 and B0 absorb the interpolated K0's
phase error on the inner half-scans. Not a rang defect: CASA interpolates
the same way (`interp='linear'` across scans), which is why CASA and rang
shared the floor to 7e-7 in e2a-3b-k.

**T3 (H-C) on S0f′: cleared.** Every term at 1000 iterations, 1e-12,
fraction 1.0 (3,056 s): KGB0 7.21e-4 (unchanged), pass-0 residual
7.21e-4; B0 converged fully at 77 iterations. KGB1 1.07e-3 (worse than
the default's 7.8e-4): K1 still stops at the 1,000 cap with 0.91
converged, and one K1 solution is 2,154 ns from truth.

**T4 (H-B): cleared.** 68 of 962,190 scored cells have a B0 channel with
no data on a > 150 m baseline (filled); without them KGB0 is 7.215e-4.
B0's flagged channels (1,100-2,100 per antenna where data exist,
`minblperant`) are excluded cell by cell by the composite already.

**T5 (H-F): unreadable as frozen, T5′ cleared for pass 0.** Every antenna
has flagged B0 channels, so T5's rule leaves no cells (section 7). In
K0 and G0 only ID 21 is flagged, which has no data at all; T5′ (K, G
only) therefore removes no scored baseline and moves nothing. Pass 1 is
section 10.

**T6 (H-K): cleared for pass 0.** K0 against truth: median 0, max 6e-8
ns in every arm; truth with U's K0 alone 5e-8 (median), with U's G0 alone
1.2e-4, with U's B0 alone 3.4e-4 (R's run). Both tables' K pivot is
1,283,895,507.8 Hz.

**T7 (H-R): cleared for pass 0.** The scorer cancels a common phase and
delay to 1.4e-7 and sees a per-antenna one (controls above). m022 is
unflagged in every K0, G0 and K1 solution and `used_alternate_refant` is
false in every term. In pass 1, G1 flags m022 in 4 rows of R's run and 9
of NS (0 in CL) and writes ANTENNA2 = −1 there: intervals without the
refant, which A0 emptied (NS: m022 keeps 0 cells in intervals 5-9). Their
effect is inside section 10's pass-1 reading, not separated.

**T8 (H-P).** The float32 bound's median over the scored cells is 5.0e-7
(ID 50's stored delays dominate its baselines). NS, CL and CN meet machine
precision with 0 % of cells above `max(1e-5, 10 b)`; their maxima
(2.5e-7 to 2.8e-7) are the data's own float32 rounding. What is left of
pass 0 after T2 is float32: **O-P** for the residue, **O-I** for the floor.

## 10. Pass 1 (sections 7, 8; post hoc)

| Arm | KGB1 median / p95 | A0: field-0 flagged after | K1 off by > 1e-3 ns |
| --- | --- | --- | --- |
| stepped, linear (R) | 7.8e-4 / 2.2e-2 | 96.7 % | 12 (IDs 5, 40 in interval 7: 0.57 ns, 2,384 ns) |
| stepped, nearest (NS) | 8.0e-8 / 2.6e-7 | 98.8 % | 0 |
| constant, linear (CL) | 3.5e-3 / 2.9e-2 | 92.8 % | 2 (ID 50, interval 7: 1,293 ns X, 2,263 ns Y) |
| constant, nearest (CN) | 7.7e-4 / 7.6e-3 | 92.8 % | the same 2 |
| stepped, strict (T3) | 1.07e-3 / 7.9e-3 | 96.7 % | ID 50 region, 2,154 ns |

(Flag-stage FLAG 92.3 %.) P1 on CL: truth with CL's K1 alone 0 (median;
max 7.5e-4, the wrong solution sits on cells the scorer's flag-stage
set excludes), with its G1 alone 0 (p95 6.2e-3), with its **B1 alone
3.2e-3**: the floor is B1, solved with the wrong K1 pre-applied; B1 per
antenna is off by 1.2e-3 to 3.2e-3 everywhere and 1.8e-2 on ID 50 (B1
combines scans, so one interval's wrong K1 reaches every antenna and
every time).

**What K1 sees there (P2 and the probes `cf_k1cells`, `cf_kstart`,
`cf_ksolve1/2`, `cf_kcapture`).** P2's control is not met as frozen:
`gaincal` re-solving CL's K1 at the chain's rule differs from CL's table
by up to 0.012 ns (not 1e-6; chunk replay of the global stop rule, not
traced), but it reproduces ID 50's interval-7 solution to 0.01 ns, and is
read with that label. Strict (692 iterations, fraction 1.0) stays at
1,293 / 2,263 ns, and one Gauss-Newton step from the FFT start is already
there: a **wrong start that converges to a local minimum**, not
non-convergence. The arrays `gaincal` hands the kernel for that interval
(captured) hold 66 rows of ID 50 and only **94 unflagged cells** (91
channels across the band, 1-10 per baseline, **2 on the baseline to the
refant**), every one consistent with truth to 1.4e-7; the FLAG is the
flag stage's (CL's A0 added almost nothing). The FFT start uses only
baselines to the refant (`delay.rs` `initial_estimate`), so it sees two
cells; on 94 cells spread over 91 channels the noise-free delay cost has
sidelobes nearly as deep as the true minimum, and Gauss-Newton settles in
one. Solved alone the same interval reaches truth when it has more cells
(`cf_ksolve1`, `cf_ksolve2`'s joint solve: those probes bin rows by the
nearest solution time, which puts 909 rows of neighbouring dumps into
"interval 7"; with `gaincal`'s own bins the captured arrays give the wrong
value again). In R's run and T3 the same happens to IDs 40 and 5 in
interval 7 because A0 flagged the inner half of each scan (intervals 4-10
keep 0.4-3 % of their cells): on noise-free data A0 flags the pass-0
interpolation residual as RFI.

Reading: the pass-1 floor of these simulations is **one or two K1
solutions on intervals with almost no data** (K applies no `minsnr` or
`minblperant`, as CASA's K does not; rang matches CASA there), carried by
B1's combined solve into every antenna. NS escapes because its A0 flagged
intervals 5-8 completely for IDs 50, 40, 5 and m022 (0 cells), so no K1
solution is made there. It is a property of
the estimator's start and of K's missing data-sufficiency rule, not an
arithmetic defect; nothing was changed here (section 5: a new flag rule
for K is a default change, and would move every archived K gate).

## For the coordinator

- **Pass 0 located (O-I, frozen rule).** The noise-free K G B floor of
  e2a-3b-k (KGB0 3.7e-4 on post-A0 cells, 7.2e-4 on the flag stage's) is
  the simulation's design meeting the chain's interpolation: truth
  constant per scan with a step between scans 9 and 11, per-scan K0 and
  G0 pre-applied by linear interpolation across the 4,000 s gap. Remove
  the step (S0c) or the interpolation (`interp: nearest`) and KGB0 is
  0 (median), max 2.8e-7, the data's float32. Generator, model, B's
  channels, flags, K's parametrisation, refant gauge, convergence and
  float32 all cleared as the floor's cause. Not a rang defect; CASA
  interpolates the same way, hence their 7e-7 agreement.
- **Pass 1 located (post hoc).** KGB1's floor is one or two K1 solutions
  on intervals with almost no unflagged data (ID 50 interval 7: 94 cells,
  2 on the refant baseline), where the FFT start (refant baselines only)
  and Gauss-Newton converge to a noise-free local minimum 1,293-2,384 ns
  from truth; B1, combining scans, spreads it to every antenna. In
  stepped arms A0 makes such intervals by flagging the pass-0 residual.
  Not changed. A follow-up for a frozen test: a data-sufficiency rule
  for K (cells or channels on the refant baseline, behind a key; CASA's
  K has none) or a start from all baselines.
- **For future noise-free controls:** use truth constant over the
  observation, or nodes at the solution times, or `interp: nearest`; and
  do not read pass 1 with A0 on noise-free data (A0 flags 92.3 → 96.7-98.8 %).
- **No code change, no gate moved.** Scripts and receipts in
  `research/results/calchain-floor/`; outputs on nash in
  `~/rang-data/outputs/calchain-floor-20261117/` (size in the hand-back).

## 11. Addendum 2026-11-17 14:55, post hoc (after section 10 was written, before the tests below ran)

Section 10's reading is partly inferred; by T2's frozen words pass 1 is a
**contradiction** (NS meets machine precision, CL does not; NS's KGB1 is
read on 76,994 of 962,190 primary cells, the rest flagged by A0).
Corrections: T8's bound median (5.0e-7) is `4 eps32 + 2.5e-7`, not ID
50's delays (ID 50's K is 0.1 ns in these truths, not near 2,392 ns);
`cf_k1cells`, `cf_kstart`, `cf_ksolve1` and `cf_ksolve2` bin rows by the
nearest K1 solution time, not by `cal_gain.solint_bins`, so their cell
counts (5,202 X cells, 424 refant cells, the 0.4-3 % of intervals 4-10,
NS's 0 cells) and `cf_kstart`'s cost of 2.0 are for those bins; only
`cf_kcapture` (94 cells, 2 to the refant) uses the solver's own bins. The
receipt label "FFT start only (0 iterations)" ran one iteration (the
kernel runs at least one).

Tests added before they ran:
- **F50**: CL's construction (S0c, linear) with ID 50's rows in K1
  interval 7 (`solint_bins`, 60 s) flagged before the run. The wrong K1
  solution **carries** pass 1's floor if KGB1 meets machine precision;
  **contributes** if KGB1 drops ≥ 2× from 3.5e-3; else not.
- **Cost on the solver's cells** (`cf_kcapture`): the noise-free cost of
  ID 50's 94 interval-7 cells at truth and at rang's delay, each with the
  best free phase per hand (the `delay_and_offset` offset), others at
  truth. If both are ≤ 1e-6 (relative) the delay is **unidentifiable**
  from those cells; if rang's is > 1e-3 while truth's is ≤ 1e-6, rang
  returned a **wrong unflagged answer on identifiable data**, a defect.
- **Real data**: ID 50's K1 per interval in e2a-3b-k's archived T-T
  tables (read only), against its neighbours.

## 12. Addendum 2026-11-17 15:10, post hoc (after section 11's cost, the real T-T K1 and `cf_kdiag` were read; before any code change)

Read (section 13): on the 94 cells `gaincal` gives the kernel for ID 50's
interval 7, truth's relative cost is 1.7e-15 and rang's delay's 1.7-1.8:
by section 11's rule **a rang defect** (a wrong, unflagged answer on
identifiable noise-free data). From the same captured arrays a start at
0 reaches truth (strict), the FFT start does not (with either offset
start): **the FFT start is the cause**. Refant-baseline cell counts do
not separate wrong solutions from right ones (right with 8 refant cells,
wrong with 10), so a data-sufficiency flag is the wrong fix. The real
subset's archived T-T K1 holds the same solution (ID 50, interval 7:
2,329 / 2,299 ns; neighbours 0.11 ns), and **CASA's own K1 does too**
(`casa-ntf`: 2,362 / 2,320 ns, unflagged): a shared property of an FFT
start on the refant baseline, not a CASA behaviour rang lacks.

The fix, behind a key, default off (today's behaviour bitwise):
`calibrate.k_zero_start` (`rang.cal_delay.solve(zero_start=True)`): the
kernel runs a second time from a zero start, and per interval the run
with the lower weighted residual over the interval's unflagged
parallel-hand cells is kept. Decision rules:
- **Gates unchanged**: rang U on S0f′ with this branch's code and the key
  off (arm `lin2`) gives tables bitwise equal to archived U's.
- **The fix carries pass 1** if CL with the key on (arm `zs`) meets machine
  precision on KGB1 (and KGB0 stays there); **contributes** if KGB1 drops
  ≥ 2× from 3.5e-3; else it does not.
- R's construction with the key on (`zs` on S0f′) is reported, not gated
  (A0's flags differ there).
- Unit test: a noise-free simulation where one antenna's refant-baseline
  data in one interval are reduced to a few cells; key off reproduces a
  wrong delay (or the test states that it does not), key on recovers
  truth.
