# E2-A gate 3b follow-up: the K estimators, the unattributed part, the synthetic

Status 2026-11-17: **protocol, frozen before any test** (sections 1-6).
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
