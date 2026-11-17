# E2-A gate 3b follow-up: the K estimators, the unattributed part, the synthetic

Status 2026-11-17: **measured** (sections 8, 10); protocol frozen before any test (sections 1-6), post hoc addenda 7 and 9.
Results are added below it; anything decided after a result is read is
dated and labelled post hoc. Follows [e2a-3b-diag.md](e2a-3b-diag.md)
(sections 9-12 and its coordinator decisions 2 and 4); issue #2, v0.3.0.

## 1. What is open

With `calibrate.bandpass_model_divided: true` E2-A's K1 G1 B1 composite
against CASA is 2.28e-3 at full scale (e2a-3b-diag 12; class B 7e-4 /
3e-3). On the 15-antenna field-0 subset (e2a-3b-diag 7, 9), with rang's
averaging off (T-T):

| Pair | KGB1 median | |
| --- | --- | --- |
| TT-TF (CASA with its own K) | 6.5e-3 | |
| TT-TK2 (CASA on rang's K0, K1) | 1.77e-3 | |
| TT-TK3 (as TK2, CASA pass 1 on T-T's own after-A FLAG) | 1.10e-3 | "unattributed", uniform over antennas |

Residual delay about each antenna's mean (data side, median): rang
2.2e-4 ns, CASA 1.0e-3 ns. Also open: on the 4-antenna test synthetic
(`tests/test_e2a_bandpass_model_divided.py`, fixture `exact`) the divided
average differs from the unaveraged B by 5e-3, and averaged from
unaveraged by 4e-4 with nothing pre-applied, although divide-then-average
with weights `w |M|^2` has the same least-squares minimum as the
unaveraged solve (the cost is `sum_t w_t |M_t|^2 |V_t/M_t - J|^2`).

Read before this note was written (orientation only, no solve, no
composite): the diag's scripts and receipts; `e2a-rerun.yaml`'s calibrate
block (no CASA-parity keys set for G or K); rang's K docstring
(`rang.cal_delay`: QuartiCal `delay_and_offset`, FFT start then
Gauss-Newton over all baselines, CASA's refant referencing); the
subset's FLAG versions exported from `D:` (hashes equal the diag's
receipts: flag stage `e6910ad4…`, R0 after-A `d3217053…`, T-T after-A
`ba886c3f…`); nash's `e3-input/e2a.ms` flag hash (`1aec438d…`, equal to
9.1's).

## 2. Hypotheses

| # | Hypothesis | Where |
| --- | --- | --- |
| H-K | the two K estimators differ in accuracy; CASA's K (FFT on baselines to the refant, as CASA documents `gaintype='K'`) is noisier than rang's (all baselines, Gauss-Newton) | K0, K1 |
| H-M | rang's SR2016 model column differs from CASA's setjy (a per-channel factor common to all baselines) | every solve; the 1.1e-3 |
| H-B | given the same K, model and flags, rang's and CASA's G1 or B1 estimators differ in accuracy | G1, B1; the 1.1e-3 |
| H-C | the synthetic's averaged/unaveraged differences are solver convergence (stop rule), not bookkeeping | the 4-antenna synthetic |
| H-W | the synthetic's differences are weight or flag bookkeeping in the averaged path (a rang defect) | the same |

Expected delay noise (written before any run). For one baseline and
interval, `sigma_tau = 1 / (2 pi SNR_ch sqrt(N_ch) sigma_nu)`. A
refant-baselines-only estimator has one baseline's error per antenna
difference; a least-squares fit over all baselines of N antennas has
about `sqrt(2 / (N - 1))` of it. With N = 15, CASA/rang error ratio about
2.6 if CASA uses refant baselines only, about 1 if it uses all; above 2.6
would add estimator bias (the FFT grid) on CASA's side.

## 3. Data

Development data only. E2-A's MS (`~/rang-data/e3-input/e2a.ms` on nash,
the E3 agent's build; flag hash equal to 9.1) is already scored and is
development data now. Its reserve scans (12, 11, 13 of the reserve leg,
e2-acceptance 6.6) are not fetched, read or touched. The source MS is
bound read-only (`apptainer --bind …:ro`) and never opened for writing.

- **Subset `src.ms`** (nash): `d1_casa.py base` on field 0 of the 15
  antennas of e2a-3b-diag D1. Controls: its `source_rows` equal the
  diag's `base.json`; FLAG then set from the exported flag-stage version,
  hash `e6910ad4…`; `delmod`. Copies are made from it.
- **Field-0 copy `f0.ms`** (nash, step F): all 61 antennas, e2a-3b-diag D3's
  construction; FLAG versions exported from `D:` (flag stage; rang's
  after-A, D3's hash `24b124a4…`).
- **Simulated truth** (`sim-<case>-<seed>.ms`, copies of `src.ms`): DATA
  replaced by `corrupt(M, B_T, G_T, K_T) + n`.
  - M: rang's SR2016 MODEL_DATA (written by rang's calibrate on the
    subset). Both arms use exactly this model: rang computes it, CASA gets
    it by `setjy(usescratch=True)` followed by a column copy from the rang
    copy (so H-M cannot enter the simulation).
  - Truth terms from the real subset's T-T tables, as realistic
    parameters (they are not taken as right). Case **S1**, static: K_T
    and G_T constant per scan (T-T's K0, G0), B_T = |T-T's B0| (amplitude
    only, so that K0's truth is not shifted by a bandpass phase slope).
    Case **S2**, varying: K_T and G_T T-T's K1 and G1 interpolated
    linearly to every dump, B_T = T-T's B1 with its weighted linear phase
    slope per antenna and hand removed. Flagged template solutions are
    filled from their neighbours in time (K 0, G 1, B 1 if none). Truth
    tables are written with a row at every dump time and applied with
    `rang.cal_apply.apply(direction="corrupt")`, so the composite of the
    truth tables is exact at every scored time.
  - Noise: complex Gaussian, per channel and correlation, σ per
    component measured on the real subset as the robust (MAD) scatter of
    `(V_t - V_{t+1}) / sqrt 2` over unflagged cells, consecutive dumps of
    one baseline. Seeds 20261171, 20261172 (two per noisy case).
  - Flags: the real ones (flag stage for pass 0; rang U's own after-A for
    pass 1 of the CASA arms, as T-K3).
  - Noise-free control **S0**: S1 without noise.
- **The 4-antenna synthetic**: the test fixture `exact`, unchanged, run
  as a script.

## 4. Tests, in order

Words as in e2a-3b-diag 3: **carries** (meets class B), **contributes**
(lowers the KGB1 median ≥ 2× without meeting class B), **cleared** (moves
it < 20 %, or a same-tool composite ≤ 7e-5). Composites are
`e2avg_common.composite` (every 8th time, pooled field map) as in the diag.
"Nearer truth": an arm's median error ≤ 0.8 × the other's; within 20 %
is a tie.

**Step 1, tables only (real subset, archived T-T and T-K3 tables).**
Ratio `r = J_TT / J_TK3` per (row, channel, hand), split into (a) a
per-channel factor common to all rows (median over rows), and what is
left after dividing it out; (b) |r| − 1 against arg r; (c) the G1-only
and B1-only composites. Reading: if removing the common per-channel
factor leaves ≤ 0.5 × 1.1e-3, the part is common to baselines (model-like:
go to H-M first). Static check: the rows each arm drops for
`uvrange >150` (rang's selection against CASA's, counted).

**Step 2, model (H-M).** On `src.ms` copies: rang's MODEL_DATA (from
rang's calibrate, this branch) against CASA's `setjy(usescratch=True)`
column, and both against a NumPy evaluation of SR2016 at CHAN_FREQ with
the coefficients rang cites (`rang.fluxstd`, CASA's). Median and max
|M_r/M_c − 1| over unflagged parallel-hand cells.
- **H-M cleared** if that median is < 5.5e-5 (a twentieth of 1.1e-3).
- Otherwise run **TK3m** (T-K3 with rang's model copied into CASA's
  MODEL_DATA): H-M carries or contributes to the 1.1e-3 by the words above
  applied to TT-TK3m against TT-TK3. The side that differs from the NumPy
  evaluation (by > 1e-5) is wrong; if rang's, it is fixed (step 6).

**Step 3, sharing ladder (real subset, CASA on nash, imported flags).**
- **Control N-TK3**: T-K3 rerun on nash against the archived T-K3
  tables, every term composite ≤ 7e-5. If not met, nash CASA results are
  read only against nash CASA results.
- **TKG**: CASA's B1 on rang's K1 and G1 (pass 0 on rang's K0, G0, CASA's
  B0; pass 1 B1 only). TT-TKG against TT-TK3 says whether the 1.1e-3 is
  in B1 (TT-TKG ≥ 0.8 × TT-TK3) or in G1 (TT-TKG ≤ 0.5 × TT-TK3);
  between: both.

**Step 4, simulated truth (H-K, H-B).** Arms on each case:
- rang **U** (`average_time: false`) and rang **D** (`average_time: true`,
  `bandpass_model_divided: true`), this branch, `e2a-rerun.yaml`'s
  calibrate block, refants m022, m023, m024;
- CASA **C** (`e2_casa3b_a.casa_calls` as in D1's T-F, model as section 3)
  and **CK** (T-K3's construction: CASA on U's K0, K1).
Read, per case and seed, with and without ID 50 (m053, its delay near the
2,392 ns ambiguity):
- K error: per K1 interval (matched by rank), antenna and hand,
  |(τ_p − τ_m022) − (τ_T,p − τ_T,m022)|, the truth averaged over the
  dumps of rang's interval; median, p95; the same for K0.
- Composite of each arm against truth (KGB1 and KGB0), and U-C, U-CK,
  D-C, D-CK (does the simulation reproduce the real 6.5e-3 and 1.1e-3?).
- **Control S0:** rang U's KGB1 and KGB0 against truth ≤ 7e-5. If not
  met, the generator or a convention (K sign, reference frequency) is
  wrong; it is fixed and S0 rerun before S1/S2 are read. CASA's S0 error
  is read as its noise-free estimator bias, not as a control.
- K errors are read cleanly on S0 and S1 (K0 has nothing pre-applied and
  B_T no phase); on S2 the K1 "truth" also carries what B0 absorbed of
  K0's error, so S2 is read on the composites (labelled).

Outcomes, H-K (both noisy cases, both seeds):
- **K1** rang nearer truth: no rang change; CASA's K is the less accurate
  estimator here, with the measured ratio against the expectation of
  section 2.
- **K2** CASA nearer truth: rang's K is the defect; fixed behind a key
  (step 6), measured.
- **K3** tie, or mixed over cases/seeds: no change; reported.
- If CASA's KGB1 error against truth is ≥ 2× U's and U-C ≥ 2× U-CK, the
  simulation reproduces the real pattern and attributes it to CASA's K.

Outcomes, H-B (CK against U, against truth, KGB1):
- **B1** U nearer truth: the remaining real part is not rang's estimator.
- **B2** CK nearer truth: a rang defect in G1/B1; located (G or B via the
  step-3 split) and fixed behind a key.
- **B3** tie.
- **B0** U-CK on the simulation ≤ 0.3 × the real 1.1e-3 (after H-M): the
  simulation does not reproduce the real size; the part stays
  unattributed, recorded as null.

**Step 5, the synthetic (H-C, H-W).** On the fixture, for nothing
pre-applied and for K, G pre-applied: B unaveraged, averaged (separate),
averaged divided, each at the chain's stop rule and strict (1000
iterations, 1e-12, fraction 1.0). For each pair, the unaveraged weighted
χ² (`sum w |V − J_p J_q^* M|^2` over every unaveraged cell) at both
solutions.
- **H-C** if strict averaged-divided and strict unaveraged agree to
  ≤ 1e-5 (median |Δg|) and, at the chain's rule, the solution with the
  lower χ² is the less converged one's counterpart (the χ² of the
  divided average is not below the unaveraged one's by more than the
  solver tolerance): no defect.
- **H-W** if they still differ by > 1e-5 strict: the averaged path's
  weights or flags are compared cell by cell with the reference
  (`np_divided` then `np_average`, already a test) and with the
  unaveraged normal equations; the step that differs is the defect, fixed
  and tested.
- Neither (strict agreement but χ² lower for the averaged solution beyond
  tolerance): reported, unexplained.

**Step 6, fixes.** Only for a rang defect named above: behind a key
(default unchanged) or inside the opt-in `bandpass_model_divided` path
(not yet default), with a test; measured on the subset against CASA (TF
and TK3 constructions) and on S2 against truth.

**Step F, full scale (the prediction for a reserve leg).** On `f0.ms`:
CASA T-K3 construction (setjy, G0 B0 on E2-A's archived rang K0, flag-stage
FLAG; G1 B1 on rang's K1, after-A FLAG). Read: the KGB1 composite of
(archived K1, G1, D3's divided B1) against (rang K1, CASA G1, CASA B1),
beside the controls (archived rang against archived CASA on `f0.ms`
= 3.16e-3; divided = 2.28e-3). If step 2 found a model difference, also
with rang's model in CASA. This is the composite a reserve leg would
read under T-K2's construction; with CASA's own K it would read
2.28e-3 (D3).

## 5. What is not changed

The K estimator is not changed to match CASA's unless CASA is nearer
truth (K2). No frozen gate is re-read; the E2-A verdict stays as booked.
The reserve is not fetched.

## 6. Records

Scripts `research/results/e2a-3b-k/`, outputs
`~/rang-data/outputs/e2a-3b-k-20261117/` on nash, compact receipts
committed. Every heavy step through the main checkout's
`tools/heavy_lock.py` on nash under `nice -n 19 ionice -c3`, booking the
cores used; wall times in `research/tool-timings.md` (host nash).

## 7. Addendum 2026-11-17 09:40, post hoc (after steps 1-3 and 5 were read, before the test below ran)

Read so far (results in section 8): the models are identical (H-M
cleared); the 1.1e-3 is in B1 (B1-only composite 1.08e-3, G1-only 6.9e-5);
CASA's B1 on rang's K1 **and G1** (TKG) agrees with rang's to 1.0e-4
(TT-TKG), so by step 3's rule the part sits in G1, although rang's and
CASA's G1 differ by only 5.6e-5 (median relative). They differ in one
flag: CASA flags G1 of ID 50 (m053, its delay near the ambiguity) in
interval 7, X hand; rang does not. A flagged solution changes how CASA's
B1 pre-apply corrects that antenna's data in that interval, and B couples
every antenna through its baselines.

- **TKGf** (CASA): B1 only, on rang's K1 and rang's G1 with that one
  solution flagged as CASA flags it.
- **TK3u** (CASA): B1 only, on rang's K1 and CASA's G1 with that one
  solution unflagged and set to rang's value.
- **The flag carries the part** if TT-TKGf ≥ 0.8 × TT-TK3 and TT-TK3u ≤
  0.5 × TT-TK3; **it does not** if both stay within 20 % of TT-TKG and
  TT-TK3 respectively; anything else is reported as mixed. Either way the
  next question is which G1 is right for that solution (its SNR in both
  tools), not a rang change unless rang's is shown wrong.

## 8. Results (measured 2026-11-17 on nash, except step 5)

Receipts: [results/e2a-3b-k/receipts/](results/e2a-3b-k/receipts/);
outputs `~/rang-data/outputs/e2a-3b-k-20261117/` on nash. Every step rc 0.
KGB1 is the K1 G1 B1 composite, median / p95 (class B 7e-4 / 3e-3).

**Data.** `src.ms` on nash: `source_rows` equal the diag's `base.json`,
FLAG hash `e6910ad4…` after the flag-stage import. `f0.ms`: rows equal D3's,
FLAG `24b124a4…` (D3's). Noise (step 4's σ): 10,710 dump pairs, median σ
per component 0.090 (XX), 0.093 (YY), 0.126 (cross hands); 934 of 4,096
channels had fewer than 50 pairs and took the median.

**Step 5, the synthetic (on the Windows host, 1 slot; `k-synth*-win.json`).**
- Strict stopping (1000 iterations, 1e-12, fraction 1.0) changes nothing:
  averaged divided against unaveraged stays 5.05e-3 (K, G pre-applied) and
  6.3e-2 (nothing pre-applied). H-C (convergence) is **not** the cause.
- A SciPy least-squares fit of the unaveraged weighted χ² (per channel and
  hand, started from both solutions) lands on the **divided average** to
  2e-8, at χ² 14.270 (K, G) and 2548.50 (none); the unaveraged kernel's B
  sits at 14.493 and 2592.91.
- Cause (post hoc probe 3): the unaveraged kernel drops every cell with any
  correlation flagged (QuartiCal's rule, `core/src/solve.rs`
  `data_flags`), while the averages are per correlation. The kernel run on
  per-baseline means of the same rows, with FLAG OR-ed over the four
  correlations first, equals the unaveraged B to 3.5e-8. The fixture flags
  by correlation: of 1,728 cross cells, 627 have a flag and only 80 all
  four.
- E2-A's data cannot show it: FLAG is equal over the four correlations in
  every cell of the subset and of field 0 (0 of 7.8e8 cells differ,
  `flags-by-correlation.json`), which is why the subset's divided average
  equals its unaveraged B (e2a-3b-diag 9).
- Reading: H-W in the sense of section 4, located in the **unaveraged**
  path, not the averaged one. Not changed: it does not touch E2-A, and
  which rule CASA follows for a cell with one correlation flagged was not
  tested. Documented in `cal_bandpass.bandpass`, with a test (flags equal
  over correlations: divided average = unaveraged B within 1e-5).

**Step 2, model (H-M): cleared.** rang's MODEL_DATA against CASA's
`setjy(usescratch=True)` column: |M_r/M_c − 1| median 0, max 1.1e-16;
phase ≤ 4.5e-10°; both within 9.6e-8 of Reynolds 1994 in NumPy.

**Step 3, real subset (CASA on nash, imported flags).**

| Pair | KGB1 median / p95 | KGB0 |
| --- | --- | --- |
| control N-TK3 vs archived T-K3 | 0.0 / 0.0 (met) | 0.0 |
| control rang U (nash, this branch) vs archived T-T | 4.7e-6 / 1.0e-2 | 3.3e-8 |
| TT-TF (CASA's own K, nash) | 6.46e-3 / 3.3e-2 | 3.35e-3 |
| TT-TK3 (CASA on rang's K0, K1) | 1.10e-3 / 1.6e-2 | 1.0e-4 |
| **TT-TKG** (CASA's B on rang's K and G) | **1.04e-4** / 3.05e-3 | 4.6e-5 |

(U's p95 against T-T is A0's flags: nash's A0 flags a few cells
differently; CASA's arms all take T-T's imported flags.) Step 1's split of
TT-TK3: B1-only 1.08e-3, G1-only 6.9e-5; a per-channel factor common to
all rows is 1.4e-4 and removing it leaves 1.09e-3; amplitude part 3.8e-4,
phase 5.1e-4 rad. By step 3's rule (TT-TKG ≤ 0.5 × TT-TK3) the part sits
in **G1**, entering through B1's pre-apply.

**Section 7, the one G1 flag.** rang's and CASA's G1 (both on rang's K1)
differ by 5.6e-5 (median relative) and in one flag: ID 50 (m053),
interval 7, X hand, which CASA flags (its SNR 2.22 < `minsnr` 3) and rang
keeps (rang's SNR 30.1). Both solved nearly the same value (amplitude
0.091 against 0.088; ID 50's G1 amplitude is 0.72 in intervals 5 and 9,
0.38, 0.09, 0.29 in 6-8, a decorrelation of that antenna).

| Pair | KGB1 median / p95 |
| --- | --- |
| TT-TKGf (CASA's B on rang's G1 with that solution flagged) | 1.05e-3 / 1.5e-2 |
| TT-TK3u (CASA's B on CASA's G1 with it unflagged, rang's value) | 1.44e-4 / 3.3e-3 |

**The flag carries the 1.1e-3** by section 7's rule (1.05e-3 ≥ 0.8 ×
1.10e-3; 1.44e-4 ≤ 0.5 × 1.10e-3). One flagged G1 solution makes CASA's
B1 pre-apply correct ID 50's interval-7 data with a gain interpolated from
intervals 6 and 8 (amplitude about 0.33) instead of the 0.09 the data
carry, and B1 couples that into every antenna (B1 per antenna differs by
4e-4 to 1e-3, ID 50 3.4e-3). The two SNRs are different definitions, as
`research/c2a-gain.md` 1 states: CASA's on its time- and
frequency-averaged, model-divided buffer, rang's on the cells as they are
(rang's median G1 SNR 9,833, CASA's 1,323). rang's keeps a solution that
fits its data; it is not a defect by the rule of section 4.

## 9. Addendum 2026-11-17 10:05, post hoc (after S0 was read, before S0f ran)

S0's control is **not met**: rang U's KGB0 against truth is 7.5e-3 and
KGB1 3.3e-3 (CASA's 7.5e-3 and 3.6e-3). The generator is not the cause:
on every 50th row the simulated DATA equal `M J_T` (the truth composite)
to 2.5e-7, and K0 is recovered exactly (error 0.0 ns). Two things post
hoc:
- The composite counts every cell where the tables are unflagged, and B's
  `fillgaps: 70` fills most of the 92 % flagged channels, where the "truth"
  is my interpolation of the template. Scored only on cells whose data are
  unflagged, U's KGB0 is 6.4e-3 and KGB1 2.9e-4 (CASA 6.5e-3, 6.0e-4).
- What is left in pass 0 is the chain's own floor: G0 (per scan, all
  channels, B not yet applied) takes each scan's flag-weighted mean of
  B_T, the flags differ between scans, and B0 (one solution, scans
  combined) cannot follow both. Pass 1 repairs most of it.

So the frozen S0 rule tests the chain, not the generator. Added, before
running it:
- **S0f**: S0 with B_T = 1 (noise-free, static). Control: U's KGB0 and
  KGB1 against truth ≤ 7e-5 on data-unflagged cells. If met, conventions
  are right and S0's floor is the chain's.
- Every sim composite against truth is also reported on data-unflagged
  cells (the reading used below); the all-cell figures stay in the
  receipts.

## 10. Results of step 4 (simulated truth) and step F (measured 2026-11-17, nash)

`score-sim-*.json`, `score-f0.json`. Composites against truth and between
arms are on data-unflagged cells (section 9); all-cell figures are in the
receipts.

**Control S0f not met; S0's not met either (both post hoc, section 9).**
Noise-free, with B_T = 1, rang U's composite against truth is 5.7e-4
(KGB1) and 3.7e-4 (KGB0), also when scored at the G0 solution times
only, so it is not interpolation between scans. The generator is exact
(DATA = M J_T to 2.5e-7), K0 is recovered exactly (0.0 ns) and, given the
same K, rang and CASA agree to 7e-7 (U-CK, KGB0). The noise-free floor
the two tools share was not explained (null). Composites against truth
are therefore read only as a comparison between arms, not as accuracy;
the K errors are read directly.

**H-K: rang's K is nearer truth (outcome K1), in every case and seed.**
|Δτ| against truth, median ns (all antennas; without ID 50 within 10 %):

| Case | rang K0 | CASA K0 | rang K1 | CASA K1 | CASA/rang K1 |
| --- | --- | --- | --- | --- | --- |
| S0 (noise-free) | 0.0 | 1.1e-4 | 4.6e-5 | 2.5e-4 | 5.5 |
| S0f (noise-free, B flat) | 0.0 | 1.1e-4 | 4.8e-5 | 2.7e-4 | 5.6 |
| S1, seed 1 / 2 | 2.0e-5 / 1.7e-5 | 1.1e-4 / 9.9e-5 | 7.0e-5 / 6.7e-5 | 3.6e-4 / 3.4e-4 | 5.1 |
| S2, seed 1 / 2 (labelled: truth carries B0's part) | 2.1e-3 / 2.1e-3 | 7.4e-3 / 7.4e-3 | 2.0e-3 / 2.0e-3 | 5.5e-3 / 5.7e-3 | 2.8 |

With nothing pre-applied and no noise, CASA's K0 misses truth by 1.1e-4
ns where rang's is exact: a bias of CASA's estimator, not noise. The noisy
ratios (about 5) exceed section 2's 2.6 for a refant-baselines-only fit,
which fits a bias on top of the noise. CASA's `gaintype='K'` is the less
accurate estimator here; rang's K is not changed (section 5). The
averaged-divided arm D gives rang U's K to 1 %.

**Composites (KGB1, data-unflagged median).**

| Case | U-C | U-CK | U vs truth | C vs truth | CK vs truth |
| --- | --- | --- | --- | --- | --- |
| S0 | 3.6e-4 | 4.1e-6 | 2.9e-4 | 6.0e-4 | 2.9e-4 |
| S0f | 2.3e-3 | 9.0e-4 | 5.7e-4 | 2.1e-3 | 2.0e-4 |
| S1, seeds 1 / 2 | 3.6e-3 / 4.1e-3 | 2.8e-3 / 2.8e-3 | 3.9e-3 / 3.9e-3 | 2.3e-3 / 2.8e-3 | 2.6e-3 / 2.7e-3 |
| S2, seeds 1 / 2 | 6.5e-4 / 1.4e-3 | 2.8e-5 / 1.9e-4 | 2.0e-3 / 2.4e-3 | 2.2e-3 / 2.4e-3 | 2.0e-3 / 2.3e-3 |

- Section 4's attribution rule (C ≥ 2× U against truth and U-C ≥ 2× U-CK)
  is met in S0 (noise-free: 6.0e-4 against 2.9e-4; 3.6e-4 against 4e-6).
  In S2 only its second half holds: sharing rang's K takes U-C down 7-24×,
  as on the real subset, while the arms' errors against truth sit on the
  shared floor. In S1 neither half holds. Met in one case of three.
- **H-B: mixed (outcome B3).** CK is nearer truth than U in S1 (0.68×
  both seeds) and S0f; a tie in S0 and S2. Not explained; no rang
  change. The real 1.1e-3 is the one flag of section 8, not this.

**Step F, full scale (E2-A field 0, 61 antennas; CASA on matched
flags).** Controls met: B1 off against the archived B1 0.0; archived rang
against archived CASA 3.16e-3 / 2.36e-2 (9.13).

| rang (archived K1, G1; B1 as named) against | B1 as frozen | B1 divided (the fix) |
| --- | --- | --- |
| CASA as archived (9.13) | 3.16e-3 / 2.36e-2 | 2.28e-3 / 1.55e-2 |
| CASA with its own K, pass 0 on the flag stage's FLAG (section 10 of e2a-3b-diag) | 3.13e-3 / 2.29e-2 | **2.24e-3 / 1.45e-2** |
| CASA on rang's K0, K1 (T-K3's construction) | 1.79e-3 / 1.93e-2 | **4.1e-5 / 4.0e-3** |

CASA's two arms differ from each other by 2.03e-3. At full scale, with
the fix on and the K shared, rang and CASA agree to a median of 4.1e-5
(class B's median met) with p95 4.0e-3 (over 3e-3). What separates them
in the frozen construction is the K estimator, which the simulations show
is CASA's less accurate one.

## For the coordinator

- **K (H-K):** rang's K is nearer simulated truth in every case: CASA's K1
  error is 5× rang's with noise and CASA's K0 is biased by 1.1e-4 ns with
  none. No rang change. At full scale the K estimators carry E2-A's
  remaining 2.24e-3: with CASA on rang's K the composite is 4.1e-5 / 4.0e-3.
- **The 1.1e-3 (subset):** one G1 solution (ID 50, interval 7, X) that
  CASA flags by `minsnr` on its averaged SNR (2.2) and rang keeps (30).
  It enters every antenna through B1. A definition difference
  (c2a-gain.md), not a rang defect.
- **The synthetic's 5e-3:** the unaveraged kernel drops a cell with any
  correlation flagged; the averages are per correlation, and the divided
  average is the least-squares minimum (SciPy, 2e-8). Not in E2-A (flags
  equal over correlations). Documented, one test; no code change.
- **Null:** the simulations' shared noise-free floor (S0f 5.7e-4); H-B
  mixed.
- **Reserve leg:** as frozen (CASA with its own K) the predicted composite
  is 2.24e-3 / 1.45e-2 with the fix: class B fails again, on CASA's K.
  Not worth spending unless the gate changes. With T-K3's construction
  (CASA on rang's K) the prediction is 4.1e-5 / 4.0e-3: the median passes
  and p95 misses by 1.3×. Owner decision: a K-derived tolerance (decision
  3 of e2a-3b-diag) or the K-shared construction, written before data.
- **Disk (nash):** `~/rang-data/outputs/e2a-3b-k-20261117` (the subset,
  six simulated subsets with their arms, field 0 `f0.ms`), rebuildable
  with `k_run.py`/`simtag.sh`. Size is in the hand-back.

## 11. Addendum 2026-11-17 11:15, post hoc (after section 10's draft and `k_hb.py` were read, before UF ran)

`score-hb.json`: on a cell set common to U, C, CK and the data, CK is
still nearer truth than U in S1 (2.64e-3 against 3.89e-3, both seeds),
which is outcome B2 as frozen. In S1 seed 1, U's and CK's G1 differ by
1.7e-5 and in one place: CASA flags ID 50's interval 7 (both hands), rang
keeps it, the real subset's mechanism again; their B1 differ by 2.3e-3.
In S1 the truth is static, so CASA's interpolation from intervals 6 and 8
is exact and the flag helps; on the real data, where both tools solve an
amplitude of 0.09 there, which side is right is not known. rang already
has CASA's estimator for G as a key (`calibrate.average_freq`,
research/e2-average-freq.md), whose SNR is then computed on the
frequency-averaged cell as CASA does. Test, before running it:
- **UF**: rang U with `calibrate.average_freq: true`, on the real subset
  and on S1 seed 1.
- **Reading:** UF against CASA on rang's K (TT-TK3's construction, real)
  and UF against truth (S1). If UF flags ID 50's interval 7 and UF-TK3
  drops below 0.5 × TT-TK3 (1.1e-3), the key closes the part against
  CASA; on S1 it is nearer truth than U if ≤ 0.8 × U's error. Either way
  no default changes here (the key exists; making it the default is an
  owner decision).
