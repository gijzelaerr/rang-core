# E2-A gate 3b: diagnosis of the composite miss

Status 2026-11-17: **diagnosed** (sections 7-9): rang's `average_time` in B
(data and corrupted model averaged apart; fixed behind
`calibrate.bandpass_model_divided`) and the K estimators; CASA's model and
weights cleared. Sections 1-5 are the protocol, committed (`d825aea`)
before any test; 6 and 8 are post hoc addenda, each committed before its
test. A diagnosis, not a rerun: the E2-A verdict stays as booked in
`research/e2-acceptance.md` 9.13 (branch `e2a-score`, `51291b7`). A
confirmation would be a new frozen leg on the reserve data (proposed at the
end, not run).

## 1. The miss (as booked, 9.13)

| Term | Reading (rang against CASA) | Limit |
| --- | --- | --- |
| K1 | median 0.0053 ns, p95 0.0148 ns, max 89.4 ns | 0.01 / 0.03 ns: met |
| fcal composite K1 G1 B1 (`J_p J_q*`, every 8th time) | median 3.2e-3, p95 2.4e-2, max 4.24 | 7e-4 / 3e-3: **not met** |
| K0 G0 B0 composite (reported) | median 3.5e-3, p95 5.7e-2 | – |
| G1 / B1 alone | rel. median 2.6e-3 / 6.7e-3; B1 phase median 0.31° | – |
| B0 flags differ | 37,910 (B1: 0) | – |

Read before this note was written (all orientation, no solve, no composite):
`g3b-a.json`; rang's `calibrate/summary.json` and `config.resolved.json`;
`e2_casa3b_a.py`, `e2_score3b_a.py`; two probes of `e2a.ms`'s
WEIGHT_SPECTRUM and FLAG on four 3,782-row blocks of scans 9 and 11 (below);
the main table's keywords.

Facts these give:
- **Flags per pass.** rang solved K0, G0, B0 on the flag stage's FLAG
  (`rang_calibrate_20261115T132707Z`), then A0 flagged field 0 (89.75 % →
  90.12 %), then K1, G1, B1 on the after-A FLAG (`rang_apply_20261115T144017Z`).
  CASA solved all six on the after-A FLAG. Pass 0 is E2-B's A2 mismatch
  again (`research/e2b-misses.md` 9.4); pass 1 is matched.
- **Weights.** rang: unit (`weight_column: unit`). CASA: WEIGHT_SPECTRUM.
  On the probed blocks the parallel hands carry 4.5-26 (p5-p95) within a
  dump, scan 11's first block 15-42; the cross hands are 0 (half of the
  unflagged cells, all with |V| about 0.18). E2-B's A2 found CASA invariant
  to its weights, not explained.
- **Model.** rang writes SR2016 into MODEL_DATA; CASA's setjy used
  `usescratch=False`, and `e2a.ms` still holds that virtual model
  (`model_0`, `definedmodel_field_0` in the main table's keywords; FLAG and
  column hashes were restored, keywords were not checked).
- **Solution intervals.** K1 and G1 are 60 s over 8 s dumps (7.5 dumps per
  interval), 14 intervals in both. E2-B's primary terms were all `inf`. B1
  (`inf`, combine scan) cannot absorb a per-interval K1 or G1 difference;
  K0 (`inf` per scan) is per scan while B0 combines scans.
- **Iterations.** rang's B0, K1 and B1 stopped at the 50-iteration cap
  with converged fractions 0.88, 0.93, 0.93.
- **Size.** A per-interval delay difference Δτ gives a phase 2π Δτ Δν: with
  Δτ = 0.0053 ns at 214 MHz from band centre, 7e-3 rad, the size of the
  miss. K's own limit (0.01 ns) allows 2.7e-2 rad at the band edge, so K1
  meeting its limit and the composite meeting class B are not consistent
  for 60 s K solutions over 856 MHz.
- **Noise.** B per channel, per antenna, both scans: SEFD about 450 Jy,
  209 kHz, 104 × 8 s, 60 baselines, a 14 Jy source → relative σ about 2e-4.
  B1's 6.7e-3 is 30× that, so "noise-level difference" alone needs a number.

## 2. Candidates

| # | Candidate | Where it acts |
| --- | --- | --- |
| H-K | K estimator: per-interval delays differ (K1), not absorbable by B1 | K1 (and K0 per scan) |
| H-F | pass-0 flags (CASA K0 G0 B0 on the after-A FLAG) | K0, G0, B0, then via pre-apply K1, G1 |
| H-W | weights (CASA WEIGHT_SPECTRUM, rang unit) | every solve |
| H-T | rang's `calibrate.average_time` | every rang solve |
| H-M | CASA's virtual model (`usescratch=False`) | every CASA solve |
| H-I | rang's iteration cap (50) | B0, K1, B1 |
| H-S | interval boundaries / solution TIMEs of the 60 s terms | K1, G1 |

## 3. Tests, in order

Tolerance throughout: class B as frozen (composite median ≤ 7e-4 and
p95 ≤ 3e-3), K by its limit; not loosened. The composite code is
`e2_score3b_a.py` / `e2avg_common.composite` at `51291b7` (every 8th time,
pooled field map), used unchanged.

Words used in the outcomes:
- **carries**: changing only this makes the KGB1 composite meet class B;
- **contributes**: it lowers the KGB1 composite median by ≥ 2× without
  meeting class B;
- **cleared**: it moves the KGB1 median by < 20 % (or a CASA-against-CASA
  or rang-against-rang composite is ≤ 7e-5, a tenth of class B).

### D0. Archived tables, no solve (`e2a.ms` read for metadata only)

Tables: `D:\rang\outputs\e2a-20261115\rang-run\calibrate\{K0..B1}` (r) and
`...\casa\tables\{K0..B1}` (c).
- **Control C0:** (rK1 rG1 rB1) against (cK1 cG1 cB1) reproduces
  `g3b-a.json`'s KGB1 composite: equal cells, median and p95 within 1e-6
  relative. If not, the scorer is fixed before anything else is read.
- **Swaps:** rang's set with one term from CASA — (cK1 rG1 rB1),
  (rK1 cG1 rB1), (rK1 rG1 cB1) — each against CASA's set; and two-term
  swaps. Same for K0 G0 B0.
- **Delay share:** per (baseline, time, hand), the KGB1 composite ratio
  r/c with a weighted linear fit of phase against frequency removed; the
  composite statistics of what is left.
- **H-S:** K1 and G1 TIME per row, rang against CASA (max |Δt|, and
  whether each table's interval count and boundaries match).
- **Outliers:** K1 |Δτ| > 0.1 ns and G1 relative > 0.1, by antenna and
  interval.
- **Profiles:** composite median by scan, by antenna, by 256-channel block.

Outcome: the term whose swap meets class B carries the miss (H-K if it is
K1). If the delay-share residual meets class B, the miss is a delay
(phase ramp) difference. No single swap meeting: D1 tests every candidate.

### D1. A subset on which both arms solve

**Subset.** A deep copy (CASA `table.query` + `copy`, `a2_casa.py base`'s
method, source opened read-only) of `e2a.ms`'s field-0 rows of 15 antennas:
the refants m022, m023, m024 (IDs 20-22) and IDs 0, 5, 10, …, 60 except
20; all 4,096 channels, both scans, all times; subtables kept. The source
row of every copied row is recorded and TIME/ANTENNA1/ANTENNA2 must match.
`delmod` on the copy (the inherited virtual model). Under
`D:\rang\outputs\e2a-3b-diag-20261117\`. CASA never opens `e2a.ms` for
writing.

**Flags.** FLAG and FLAG_ROW from the flag stage's version
(`rang_calibrate_20261115T132707Z`, source rows mapped). rang's A0 then
flags the subset itself; its after-calibrate version (the subset's
`rang_apply`-equivalent: FLAG after rang's calibrate) is what pass 1 sees
in both arms. (A0 on 15 antennas flags differently from the full array;
both arms get the same flags, which is what the comparison needs.)

**rang arm, as frozen (R0).** The frozen wheel
(`C:\Users\gijsm\Build\tmp\20261111-e2-wheel\venv`), `rang-core run` of
`e2a-rerun.yaml` with `run.stages: [calibrate]`, `refant: [m022, m023,
m024]` (the resolved list, so the subset cannot resolve another),
everything else unchanged (the flux row's route, 9.11).

**CASA arm, as frozen (C0).** `e2_casa3b_a.casa_calls` on the subset, every
call on rang's after-calibrate FLAG (the frozen 3b input).

**Reproduction (decided before any variant is read):** R0 against C0 misses
class B on the KGB1 composite with median ≥ 1.4e-3 (twice the limit). If
D0 named a term, its swap on the subset must also meet class B. Otherwise
the subset does not reproduce the miss: report it, and the variants below
are not read as diagnosis.

**Variants (one change each from the arm named):**

| Test | Arm | Change | Implicates if | Fix if implicated |
| --- | --- | --- | --- | --- |
| T-F | CASA | pass 0 (setjy, K0, G0, B0) on the flag stage's FLAG, then FLAG set to the after-calibrate version before K1 (matched, as E2-B A2) | R0 vs T-F carries or contributes | oracle input (scorer side), as E2-B; no rang change |
| T-W | CASA | T-F with `initweights(wtmode='ones', dowtsp=True)` first, weights read back as 1 | R0 vs T-W against R0 vs T-F | oracle input (A0 rule 3 asks uniform weights in every arm) |
| T-M | CASA | T-F with `usescratch=True` (MODEL_DATA written) | T-F vs T-M CASA-against-CASA > 7e-5, or R0 vs T-M carries | oracle setting; or rang's model |
| T-K | CASA | T-F, with rang's K1 (R0) pre-applied in G1 and B1 instead of CASA's K1 | R0 vs T-K (composite of rK1, CASA's G1, B1) carries while R0 vs T-F misses | K estimator: see 4 |
| T-T | rang | R0 with `average_time: false` (if the memory limit refuses, the record says so) | R0 vs T-T rang-against-rang > 7e-5 and T-T vs T-F changes the miss by the rule | rang's averaging |
| T-I | rang | R0 with `max_iterations` 200 for every term (a wrapper patching `core_pipeline.chain_terms`' 50) | R0 vs T-I > 7e-5 and T-I vs T-F changes the miss | rang's iteration cap or stop rule |

**Which delay is right (T-K only, if H-K is implicated).** On the subset,
the data corrected by each arm's K1, G1, B1 (rang's library apply, linear),
averaged per 60 s interval and baseline; per antenna (least squares over
baselines, refant m022), the residual phase slope against frequency
(ns). The arm with the smaller median |residual delay about each antenna's
mean over intervals| fits the data better. A tie is within 20 %.

## 4. What a fix would be

- **H-F, H-W, H-M:** oracle inputs or settings: no rang change; the frozen
  verdict stays; a confirmation leg runs CASA on matched flags (and
  uniform weights).
- **H-K with CASA closer to the data:** rang's K estimator is changed
  behind a new key (the existing behaviour the default), with a test, on
  branch `e2a-3b-diag`.
- **H-K with rang closer, or a tie:** no rang change. The finding is that
  K's limit and class B on a composite with per-interval K are not
  consistent (section 1); the composite gate for 60 s K needs a tolerance
  derived from K's, decided by the owner.
- **H-T, H-I:** a rang change behind a key (averaging or the iteration
  rule), with a test.
- **H-S:** rang's interval rule, behind a key, with a test.

## 5. Records

Scripts in `results/e2a-3b-diag/`, outputs under
`D:\rang\outputs\e2a-3b-diag-20261117\`, compact receipts committed. Every
heavy step under the main checkout's `tools/heavy_lock.py`, timed, a row in
`research/tool-timings.md`.

## 6. Addendum 2026-11-17 02:20, post hoc (written after D0 and D1 were read, before T-S ran)

D1 reproduced the miss, and none of H-F, H-W, H-M, H-K, H-I met its rule
(results in section 7). But rang against rang, `average_time` on (R0) and
off (T-T), differs on the KGB1 composite by 1.05e-2, more than rang differs
from CASA, although on the same data and flags the averaged and unaveraged
least-squares problems have the same minimum. K1 and G1 agree to 1e-4;
B1 scatters channel to channel. So the next question is whether rang's
solves stop before the minimum. The stop rule is `stop_criterion` 1e-7 and
`stop_fraction` 0.99, which T-I (the cap) did not touch.

- **T-S** (rang): R0 with every term at `max_iterations` 1000,
  `stop_criterion` 1e-12, `stop_fraction` 1.0 (`d1_rang_iter.py`), averaged
  (`ts`) and unaveraged (`tts`).
- **Implicates the stop rule** if ts against tts is ≤ 7e-5 (rang's two
  estimators then agree) and ts against T-F changes the miss by the rule
  of section 3. If ts against T-F meets class B, the stop rule carries the
  miss.
- **Fix if implicated:** the chain's stop rule behind a key (default
  unchanged), with a test.

## 7. Results of D0, D1 and T-S (measured 2026-11-17)

Receipts: [results/e2a-3b-diag/receipts/](results/e2a-3b-diag/receipts/);
outputs `D:\rang\outputs\e2a-3b-diag-20261117\`. Every step rc 0. KGB1
is the K1 G1 B1 composite, median / p95 (class B: 7e-4 / 3e-3).

**D0, archived full tables** (`d0.json`, `d0b.json`):
- Control C0 met: the frozen composite reproduced exactly (equal cells,
  0.0 relative).
- No single-term swap meets class B; every swap makes it worse (rang's set
  with CASA's K1, G1 or B1: 7.7e-3, 5.2e-3, 7.4e-3). The terms trade gauge,
  so a swap does not localise.
- Removing a linear phase ramp per baseline leaves 2.5e-3 (from 3.2e-3):
  the miss is not mainly a delay. Phase part 1.8e-3, amplitude part 1.4e-3.
- H-S (labels): rang's K1 TIMEs equal its G1 TIMEs and CASA's G1 TIMEs
  (≤ 0.01 s); CASA's K1 TIMEs are 19-49 s earlier (K0: 204, 233 s). Moving
  either side's K labels to the other's changes the composite by ≤ 3e-4
  (3.16e-3 → 3.16e-3, 3.15e-3): **cleared**.
- Uniform over scans (3.1e-3, 3.2e-3), antennas (2.3e-3 to 5.7e-3) and
  channel blocks (1.8e-3 to 9.4e-3), except m053 (ID 50, 0.114): its K is
  near 2,300 ns (K1 rang 2,335 vs CASA 2,365 ns, 89 ns apart once), close to
  the 2,392 ns ambiguity of 209 kHz channels. Not the cause of the median.

**D1, the 15-antenna subset** (12,480 rows, 92 % flagged; `d1-score.json`):

| Pair | KGB1 median / p95 | Reading |
| --- | --- | --- |
| R0-C0 (both as frozen) | 1.04e-2 / 0.110 | **reproduces** (≥ 1.4e-3) |
| R0-TF (CASA pass 0 on matched flags) | 1.03e-2 / 0.116 | H-F **cleared** for KGB1 (KGB0 5.6e-3 → 3.4e-3) |
| TF-TW (CASA, unit weights) | 0.0 / 0.0 | H-W **cleared**: CASA's six tables identical |
| TF-TM (CASA, `usescratch=True`) | 0.0 / 0.0 | H-M **cleared** |
| R0-TK (CASA G1, B1 on rang's K1) | 9.1e-3 / 0.093 | H-K not met by the rule |
| R0-TI (rang, cap 200) | 1.6e-5 | H-I **cleared** |
| R0-TT (rang, `average_time` off) | **1.05e-2** / 0.108 | rang against rang larger than rang against CASA |
| TT-TF | 6.5e-3 / 0.031 | 1.6× lower than R0-TF: below the 2× rule |
| TS-TTS (strict stop, avg on/off) | 1.04e-2 | T-S: stop rule **cleared** (R0-TS 1.6e-5) |

Post hoc pairs, run after T-S without a written addendum (labelled post
hoc here; T-K2 is CASA's chain with rang's K0 and K1, from T-T, in every
pre-apply, `d1_run.py casa tk2`):

| Pair | KGB1 | KGB0 |
| --- | --- | --- |
| TT-TK2 (unaveraged rang, CASA on rang's K) | 1.77e-3 / 2.1e-2 (1.58e-3 without m053) | 1.0e-4 / 3.1e-3 |
| R0-TK2 (averaged rang) | 9.5e-3 / 9.6e-2 | 5.7e-4 / 3.0e-3 |

- K: rang's and CASA's K differ by 0.005 ns (K0) and 0.007 ns (K1) on the
  subset. Residual delay of the corrected data about each antenna's mean
  (median): rang's K1 with CASA's G1, B1 (TK) 2.2e-4 ns; R0
  6.1e-4 ns; CASA's chain (TF) 1.04e-3 ns, (C0) 1.14e-3 ns. rang's K fits
  the data better than CASA's.
- With K shared and averaging off, pass 0 meets class B on the median
  (1.0e-4) and p95 is 3.1e-3 (limit 3e-3); pass 1 is 1.77e-3.

## 8. Addendum 2026-11-17 03:10, post hoc (after T-S, T-K2 were read; before D2 ran)

T-S cleared the stop rule (section 7). `rang.cal_gain._pre_apply` corrupts
the model with the terms after the solved one (CASA's VisEquation): in B1
that is K1 and G1, which vary every 60 s, and `cal_chunks.load_averaged`
then averages data and corrupted model separately. That is not the
least-squares solve; CASA divides the data by the model before it
averages (`divideCorrByModel`, already ported for A3 as
`cal_gain.model_divided`). Pass 0's B0 sees K0 and G0 constant within each
scan, which fits its small averaging effect (2.4e-4).

- **D2** (this branch's code, `d2_divided.py`): B1 alone on the subset,
  T-T's K1 and G1 pre-applied, average_time {off, on} × `model_divided`
  {off, on}.
- **Control:** off/off against T-T's B1 (frozen wheel) composite ≤ 7e-5.
- **Implicates the averaging estimator** if on/off against off/off
  reproduces the R0-T-T difference (≥ 5e-3) and on/on against off/off is
  ≤ 7e-5.
- **Fix:** `calibrate.bandpass_model_divided` (default false), B solves
  on model-divided data, with a test.

## 9. D2 results and the diagnosis (measured 2026-11-17)

`d2-divided.json`, this branch's code (B1 alone, T-T's K1 and G1):

| B1 | KGB1 against unaveraged B1 | against T-K2 (CASA on rang's K) |
| --- | --- | --- |
| unaveraged (control: against T-T's frozen B1) | 0.0 (control met) | 1.77e-3 |
| averaged, data and model apart (frozen) | **9.3e-3** / 0.104 | 9.4e-3 |
| averaged, model-divided (the fix) | **0.0**, max 4.4e-7 | 1.77e-3 |
| unaveraged, model-divided | 0.0, max 3.5e-7 | 1.77e-3 |

**Diagnosis.** E2-A's 3b composite miss has two parts, both measured on
the subset; neither is CASA's model or weights.
1. **rang's time averaging in B (H-T, the larger part).** In a B solve the
   pre-applied K and G corrupt the model (CASA's order). `average_time`
   averaged data and corrupted model separately over B's interval, which
   spans both scans, an hour apart; K1 and G1 vary every 60 s, so the
   averaged model decorrelates and the per-channel ratio scatters (B1
   0.6 %). That is not CASA's estimator: CASA divides by the model first.
   Divided, the averaged B equals the unaveraged B to 4e-7, and the subset
   composite against CASA drops from 9.4e-3 to 1.77e-3 (5.3×). E2-B was
   not affected: its primary K and G were `inf`, constant within B's scan.
2. **The K estimators (H-K, the rest).** With averaging off, sharing rang's K
   with CASA lowers TT's composite from 6.5e-3 to 1.77e-3 (3.7×). rang's
   delays leave less residual delay in the data than CASA's (2.2e-4 against
   1.0e-3 ns). Per-interval K differences within K's own limit project
   through 856 MHz onto the composite and B1 cannot absorb them
   (section 1).
3. Left over: 1.6e-3 (1.77e-3 with m053), uniform over antennas, with K
   shared and averaging divided. Not attributed here. Pass 0 under the same
   conditions is at 1.0e-4.

Cleared: CASA's virtual model, weights (CASA's tables do not change with
unit weights, as in E2-B A2), K TIME labels, the iteration cap, the stop
rule. Pass-0 flags (E2-B's cause) move pass 0 only.

**Fix (implemented, branch `e2a-3b-diag`).** `calibrate.bandpass_model_divided`
(default false, out of the stage hash at its default):
`rang.cal_bandpass.bandpass(model_divided=True)` divides the pre-applied
data by the corrupted model (`cal_gain.model_divided`, CASA's
`divideCorrByModel`) before any average; the chain passes it to B only.
Tests: `tests/test_e2a_bandpass_model_divided.py` (5: the NumPy reference
of divide-then-average, unchanged without averaging, nearer the unaveraged
B on a decorrelating synthetic, the key's default and hash, B only). Off is
unchanged.

**Not changed:** the K estimator (rang's fits the data better here), and
the E2-A verdict (9.13, as booked).

## 10. Proposed confirmation (not run)

A new frozen leg on E2's reserve data, protocol written before any run:
- rang: the E2-A configuration with `calibrate.bandpass_model_divided: true`;
- CASA 3b arm: pass 0 on the flag stage's FLAG, pass 1 on the after-A FLAG
  (E2-B A2's matched inputs);
- gated as frozen (K by its limit, KGB1 class B), and reported beside it
  the KGB1 composite with CASA on rang's K (T-K2's construction), which
  separates the K estimators from the rest;
- expected from the subset: the frozen gate still misses (about 1.8e-3
  from the K estimators and the unattributed rest). Whether a composite
  of 60 s K over 856 MHz should be held to class B, or to a tolerance
  derived from K's limit, is an owner decision (section 1).

Cost: as E2-A's calibrate (about 4,400 s) and 3b CASA (about 3,200 s),
plus a K-shared CASA case (about 2,000 s).

## 11. Addendum 2026-11-17 04:20, post hoc (after section 9 was read; before D3 ran)

The subset's sizes do not carry over to E2-A by scale: its miss is 3.3×
the full one, and its pass 1 is twice its pass 0 where the full tables have
them equal. So the full-scale share of the fix is measured directly.

- **D3** (`d3_full.py`): a CASA deep copy of `e2a.ms`'s field-0 rows (all
  61 antennas, source mounted read-only), FLAG from rang's after-calibrate
  version (`rang_apply_20261115T144017Z`, the flags B1 saw). B1 re-solved
  by this branch with E2-A's archived K1 and G1, `average_time` on,
  `model_divided` off and on (chunked, 6 GB).
- **Controls:** off against the archived B1 (archived K1, G1) ≤ 7e-5; the
  archived rang set against CASA's on the copy equals 9.13's 3.16e-3.
- **Read:** the KGB1 composite of (archived K1, G1, B1-on) against CASA's
  archived tables, beside 3.16e-3. This measures how much of the booked
  miss the B averaging carries at full scale, with CASA's pass-0 flags and
  K left as frozen.
