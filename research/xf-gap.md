<!-- SPDX-License-Identifier: MIT -->
# Xf gap: where rang's Xf departs from CASA's on the held-out set

Task xf-gap (issue #33). Status: **proposal, frozen 2026-11-17** before any
solve of this task. Results go in dated sections below the line.

## 1. The gap

`research/xf-preavg.md` (frozen outcome 4): on the held-out 3C 286 simulation
(seeds 20261751-4, noiseless, 3C286-SIM scans 90 × 8 s = 720 s), rang's Xf
differs from CASA 6.7.6.14's `polcal` by a median 0.054° (limit 0.05), max
0.107° (limit 0.25); unaveraged rang by 0.065° / 0.114°; χ by ≤ 0.007°. On the
dev set (default seeds, 4 × 8 s scans) the medians are 0.023° / 0.016°.
CASA's `preavg` moves its Xf by ≤ 0.01°, so averaging is excluded on both
sides. `_xf_diff` there is a median of |arg|, which hides sign and shape.

What changes between dev and held-out, from the chain (`sim_chi.CONFIG`,
`casa_calls`, unchanged):
- Gpol (`solint 60s`, calmode p, parang): dev scans (32 s) give one interval
  per scan; held-out scans give 12 per scan, 60 s over 8 s integrations
  (7.5 per interval), applied to the later solves with `linear` interp.
- KCROSS (`solint inf`, one per scan): spans ≤ 0.6° of ψ on dev, up to 10.3°
  held-out.
- The seeds (Jones, sky): new gains, leakages and Xf truth.

In the simulation G's phase is constant within a calibrator scan
(`simtruth.jones`), so any time structure a Gpol solve fits within a scan is
leakage and the polarised model's error, not gain.

## 2. Hypotheses

- **H-Gpol:** rang's and CASA's Gpol differ on 720 s scans (interval edges,
  solution times, or what each absorbs of the ψ-dependent leakage terms), and
  the X−Y part of that difference averaged over antennas moves Xf.
- **H-Kc:** rang's KCROSS delay differs from CASA's (estimator, the scan's
  span of ψ, reference frequency); Δτ moves Xf by 2π Δτ (ν − ν0), a slope.
  3e-4 ns gives 0.05° at the band edge; C6 measured a 2.2e-4 ns parabola bias.
- **H-Xf:** the Xf closed form itself, or P (parallactic angle, receptor
  angle −90°) inside it, differs from CASA's on these data.
- **H-model:** rang's `nrao 3C286` MODEL_DATA differs from CASA's manual
  `setjy` on 3C286-SIM.
- **H-gauge:** the cross-hand phase each side applies (KCROSS · Xf with Gpol's
  X−Y phases) is the same and only its split between terms differs. With χ
  equal to 0.007° this is plausible; it is not a defect.

## 3. Design

**Code under test:** `origin/main` at 02f1d39 (branch `xf-gap`), extension
built in the nash worktree `~/Worktrees/rang/xf-gap` (`maturin develop
--release`). No package code changes before section 4's rule is read.

**Host and oracle:** nash; CASA 6.7.6.14 as `~/rang-data/oracle-images/
rang-o-casa_6.7.6.14.sif` under apptainer (the image e2a-3b-k used, built
from the same recipe as glacier's docker `rang-o-casa:6.7.6.14`), calls by
`examples/oracle_pol.py tasks`. Run root `~/rang-data/outputs/
xf-gap-20261117/`. Script `research/results/xf-gap/xf_gap.py`, imports
`sim_chi` (`CONFIG`, `casa_calls`, `SET_FEED`, `score`) and `xf_preavg`
unchanged; only the CASA runner is new (apptainer for docker).

**Data** (`simtruth_ms generate poldx --noiseless`, control truth, FEED −90°
set in CASA's copy, `feed_angle_rotation: -90` in rang), a 2 × 2 of seeds and
3C286-SIM scan length:

| Set | Seeds | 3C286-SIM scan |
| --- | --- | --- |
| `dev` | poldx defaults (chi-offset's control truth) | 4 × 8 s |
| `held` | 20261751-4 (xf-preavg's held-out) | 90 × 8 s |
| `held4` | 20261751-4 | 4 × 8 s |
| `dev90` | poldx defaults | 90 × 8 s |

**Arms per set:** rang `m90_noavg` and `m90` (`sim_chi.rang_arm`), CASA `m90`
(`casa_calls`, FEED −90 written). On `held` only, pre-declared: rang and CASA
with Gpol `solint` one integration (8 s; CASA `'int'`), everything else equal
(`gpol8`).

**Swap ladder (held, then dev).** rang's solvers called as the pipeline calls
them (`core_pipeline.chain_terms` on the arm's config, `cal_chain._solve_pol`
with the pipeline's budget and weights), on a copy of CASA's arm MS (CASA's
MODEL_DATA, FEED −90), with CASA's tables read by `formats.caltable.read`:

| Step | rang solves | on CASA's |
| --- | --- | --- |
| L3 | Xf | K, G, B, Gpol, Kcross |
| L2 | Kcross, Xf | K, G, B, Gpol |
| L1 | Gpol, Kcross, Xf | K, G, B |
| L0 | K, G, B, Gpol, Kcross, Xf | nothing (CASA's model only) |
| R | the rang arm (`m90_noavg`, rang's model) | – |

With Δ(ν) = arg(Xf_A / Xf_B) per channel (deg, signed), the steps telescope:
Δ(R, CASA) = Δ(R, L0) [model] + Δ(L0, L1) [K, G, B] + Δ(L1, L2) [Gpol] +
Δ(L2, L3) [KCROSS] + Δ(L3, CASA) [Xf solver and P]. The share of step i is
s_i = Σ_ν Δ_i Δ_tot / Σ_ν Δ_tot² (they sum to 1). The same ladder is read
for `m90` (averaged) against CASA, reported.

**Mirror (CASA solving on rang's tables):** M3, CASA Xf on rang's K, G, B,
Gpol, Kcross; M2, CASA Kcross and Xf on rang's K, G, B, Gpol; M1, CASA Gpol,
Kcross and Xf on rang's K, G, B; on a fresh copy with CASA's `setjy`. Read
against the rang arm: Δ(R, M3) is rang's Xf solver against CASA's on the
same input, etc.

**Term reads (reported):** per term, rang against CASA on the same earlier
tables (L-steps): Gpol phase per antenna, interval and hand, and the
solution TIME column; KCROSS delay (ns) per scan; Xf as Δ(ν) with a fit
a + b (ν − ν0) and its RMS residual (b against 360° Δτ_KCROSS). Xf and
CASA's against the simulation's truth in CASA's gauge (`simtruth.casa_gauge`).
MODEL_DATA on 3C286-SIM rows, rang's MS against CASA's (max relative
difference). P: `tests/test_cal_pol.py`'s casacore check, rerun.

**Gauge-invariant read:** each side's tables K, G, B, Gpol, Kcross, Xf
applied by one applier (`rang.applycal`, parang off: P cancels in the ratio)
to the 3C286-SIM DATA; per channel C(ν) = arg Σ V_rang V_CASA* over rows and
times, for XY, YX, XX, YY.

## 4. Controls, tolerances and decision rule (frozen)

**Controls (each must pass before the ladder is read):**
- **V0 (nash reproduces xf-preavg):** on `held`, the ψ span per 3C286-SIM
  scan within 0.01° of `research/results/xf-preavg/psi-held.json`; Xf avg
  against CASA median 0.054 ± 0.005°, noavg against CASA 0.065 ± 0.005°;
  max |χ_avg − χ_CASA| ≤ 0.01°. On `dev`: Xf avg against CASA median
  0.023 ± 0.005°. If V0 fails, stop; a dated amendment reads nash's numbers
  against nash only, before any ladder step.
- **H0 (the harness is the pipeline):** the harness with rang's own tables
  (read back from the arm's run directory) on the rang arm's MS gives the
  arm's Gpol, Kcross and Xf within 1e-4° (phases) and 1e-6 ns.
- **T0 (table transport):** CASA's Xf solve on CASA's own tables passed
  through `caltable.read` and `caltable.write` equals CASA's arm Xf within
  1e-4°. If not, the mirror is not read.

**Decision rule (held, noavg against CASA):**

1. **Located:** one ladder step has s_i ≥ 0.5, and its mirror step (where
   one exists: Xf ↔ M3, KCROSS ↔ M2 − M3, Gpol ↔ M1 − M2) has the same sign
   and share ≥ 0.3. The gap enters there.
2. **Gauge split (H-gauge):** composite XY and YX medians |C(ν)| ≤ 0.01°
   while the Xf median |Δ| ≥ 0.05°. No defect: the two chains apply the same
   cross-hand correction. Read before 3 and 4.
3. **Fix:** in case 1, if the step is rang's and its cause is a departure
   from CASA's implemented algorithm (named from CASA's source or by a CASA
   arm with one setting changed), rang is fixed with a test. The fix passes
   if on `held` Xf against CASA is median ≤ 0.05° and max ≤ 0.25° for avg and
   noavg (xf-preavg's G_casa), on `dev` χ moves ≤ 0.001° and Xf against CASA
   does not grow, and the quick check's frozen gates (gain-hash gate) pass.
   If the cause is a defensible estimator choice on either side (CASA's
   parabola bias, an interval edge convention CASA documents), it is
   documented and not changed here.
4. **Distributed:** no step reaches 0.5. Shares reported; no fix.
5. The 2 × 2 and `gpol8` arms are read, not gating: if the gap is ≥ 0.05°
   median on `dev90` and < 0.03° on `held4`, scan length carries it; if the
   other way round, the seeds; if `gpol8` closes it on both sides (≤ 0.02°),
   Gpol's intervals carry it.

## 5. Records

Every command under `nice -n 19 ionice -c3` and nash's
`~/Github/rang/tools/heavy_lock.py run --slots 2 --mem 8` (one rang or
CASA process at a time, `RAYON_NUM_THREADS` and `OMP_NUM_THREADS` = 2). One
unattended driver `research/results/xf-gap/nash/drive.sh` (`setsid nohup`),
log `~/rang-data/outputs/xf-gap-20261117/drive.log`, ending `DRIVE END rc=N`;
a fresh agent reads that file's last lines and `steps.log`. Receipts in
`research/results/xf-gap/`; wall times in `research/tool-timings.md` (host
nash).

---

(Results below this line, dated.)

Proposal frozen in commit `f9f966d`; scripts in `8ea894c` (before any solve).

## 6. Amendment, 2026-11-17 20:25 (after the arms, before any ladder, mirror or gauge number was read)

Process note: the driver's second part (H0, ladder, mirror, gauge) was
started at 20:19, before `dev`'s V0 failure was read; section 4 said to stop
first. No number of it was read before this amendment was committed
(`6d7269d`).

**V0 on nash.** `held` reproduces xf-preavg exactly: ψ spans 2.681, 10.299,
9.349, 1.495° (archive equal), Xf avg against CASA median 0.0544° (0.054),
noavg 0.0645° (0.065), χ 0.0069° (0.0069). **`dev` fails:** Xf avg against
CASA median 0.189° against 0.023 ± 0.005°.

Read in the arms' logs (not a ladder number): CASA's Gpol table lacks a
solution interval wherever its log says `Reached iteration limit: 50
iterations` on 3C286-SIM (`field=1`); the interval's rows are absent, not
flagged, and CASA's later solves interpolate Gpol across it (`linear`).
Counts, CASA rows against rang's: `dev` 3 of 4 (one scan without Gpol),
`held` 46 of 48 (t0 + 328 s in scan 2 and t0 + 7276 s in scan 14), `dev90`
45 of 48, `held4` 4 of 4, `held` `gpol8` 339 of 360. rang writes every
interval. Noiseless data leave CASA's convergence test (relative χ² change)
at rounding level, so whether an interval converges in 50 iterations can
differ between hosts; that would explain glacier's `dev` (0.023°) against
nash's (0.189°).

**Amended (post hoc, labelled):**
- By section 4's rule nash's numbers are read against nash only. `held`
  passes V0 and is read as frozen; `dev` is read as a second nash set, not
  as a reproduction of xf-preavg.
- **P1:** the ladder step L2 is repeated with CASA's Gpol completed by
  rang's solutions for the intervals CASA dropped (`L2f`, same rows
  otherwise). If Δ(L2f, L1) is ≤ 0.02° median while Δ(L2, L1) is not, the
  dropped intervals carry the Gpol step.
- **P2:** rang's Xf on rang's own K..Kcross with rang's Gpol rows removed
  where CASA has none (`R−drop`, rang's Kcross re-solved on that Gpol).
  If Δ(R−drop, CASA) falls to ≤ 0.02° median, the gap is CASA's dropped
  intervals, not a rang defect.
- `held4` (no dropped interval, gap 0.044°) and `dev90` are read the same
  way as the remaining part once P1 and P2 are in.

## 7. Amendment, 2026-11-17 20:55 (after the ladder, mirror and post hoc reads; before any fix code)

Read so far (numbers in section 8): the ladder and the mirror put `held`'s
gap in the Xf solve on identical inputs (shares 1.06 and 1.08); the gauge
read does not clear it (XY 0.060°). Post hoc, labelled: rang's Xf with each
correlation's weight times |raw / corrected|² falls to 0.018° from CASA; a
CASA arm (`casawt`) that pre-corrects 3C286-SIM with CASA's K, G, B, Gpol,
Kcross by `applycal` and solves Xf with no table reproduces CASA's chain to
0.0000° with `calwt=True`, and rang's L3 to 0.0000° (`dev`) with
`calwt=False`. The split MS's WEIGHT with `calwt=True` over `calwt=False`
equals, per row and correlation (h, h'), F(p, h) F(q, h') with F the
antenna's |G|² times its channel mean of |B|² over unflagged channels (to
1e-6 on `dev`). So CASA's solve weights are the pre-applied tables'
`calwt` weights, which rang does not apply.

**Fix (frozen before it is written), opt-in, Xf only:**
- Key `calibrate.xf_calwt` (bool, default false; out of the stage hash at
  its default, as `casa_phase_weights`). Off is byte-identical.
- With it, an Xf solve multiplies each cell's weight by F(p, h) F(q, h'),
  F = the channel mean, over channels whose solutions are unflagged, of
  |J(p, h)(t, ν)|² for the tables that correct the data, at the row's time
  (`rang.cal_apply.apply` on a unit cell per antenna). Applied before any
  time average (every load path).
- Other solves (K, G, B, Gpol, KCROSS, Df) are not changed: their weighting
  was not measured here (C2a section 10 leaves CASA's weighting chain to the
  owner).

**Fix gates (replacing section 4 rule 3's, which assumed a `dev` without a
dropped Gpol interval):**
- F1: `dev` L3 with the key (rang's Xf on CASA's tables and model.ms)
  against CASA's Xf: median ≤ 1e-3°, max ≤ 5e-3°.
- F2: `held` rang arms with the key, `m90_noavg` and `m90`, against CASA:
  Xf median ≤ 0.05°, max ≤ 0.25°.
- F3: `held` max |χ_avg − χ_CASA| with the key ≤ 0.0069° + 0.002°, and
  |χ − 33| ≤ 1.11° per scan (G_truth).
- F4: `held4` (no dropped interval) noavg Xf against CASA with the key ≤
  its value without (0.044°).
- F5: key off byte-identical (tests); the quick check passes.
- `dev`'s Xf against CASA is not gated: its 0.189° is CASA's dropped Gpol
  scan (P1, P2) and moves the other way when the weights term is removed.

## 8. Results (measured 2026-11-17 on nash)

Run root `~/rang-data/outputs/xf-gap-20261117/` (77 MB after the MS copies
were deleted: tables, logs, JSON). Receipts in
`research/results/xf-gap/receipts/`: `results.json` (section 3's reads),
`posthoc.json` (P1, P2, `casawt`), `probe-*.json` (weight probe),
`fix.json` (F1-F4), `psi-*.json`, `steps.log` (every step's rc and wall
time; all rc 0). Drivers in `research/results/xf-gap/nash/`. Degrees; Xf
per channel, median / max of |Δ|.

**Controls.** V0 `held` passes (section 6). H0: the harness reproduces the
pipeline's Gpol to 1.5e-6°, Kcross to 0 ns and Xf to 0° on `held` and
`dev`. T0: CASA's Xf on its tables passed through rang's reader and writer
is unchanged (0°). MODEL_DATA: rang's and CASA's identical on both fields
(max relative difference 0). P: not separable from the Xf step (below);
`tests/test_cal_pol.py` passes.

**The 2 × 2 (rang `m90_noavg` / `m90` against CASA).**

| Set | Xf noavg | Xf avg | CASA Gpol rows / rang's |
| --- | --- | --- | --- |
| `dev` | 0.189 / 0.279 | 0.189 / 0.279 | 3 / 4 |
| `held` | 0.065 / 0.114 | 0.054 / 0.107 | 46 / 48 |
| `held4` | 0.044 / 0.118 | 0.044 / 0.118 | 4 / 4 |
| `dev90` | 0.071 / 0.130 | 0.031 / 0.066 | 45 / 48 |

`gpol8` (`held`, Gpol per integration both sides): 0.063 / 0.135, CASA
339 / 360 intervals; rang's Xf moves 0.002°, CASA's 0.021°. Scan length
does not carry the gap (rule 5: `held4` 0.044° with no dropped interval).

**Ladder (`held`, noavg against CASA; Σ shares = 1, telescoping checked to
5e-6°).** model 0.000, K G B 0.000, Gpol 0.051 (step median 0.015°),
KCROSS −0.012 (0.0008°), **Xf solver and P 1.062 (0.065°)**. Averaged arm:
Xf 0.789, KCROSS 0.208 (rang's averaged Kcross on scan 8 is 0.0085 ns from
CASA's; unaveraged 1.1e-4 ns), Gpol 0.002. **Mirror:** Xf solver (R − M3)
1.083 (0.063°), KCROSS −0.011, Gpol 0.000, K G B and model −0.072. KCROSS
delays, rang on CASA's K, G, B, Gpol against CASA: |Δτ| ≤ 2.1e-4 ns per
scan. **Gauge read:** composite XY 0.060° / 0.109°, YX 0.070° / 0.141°
(XX 0.006°, YY 0.008°): not a gauge split.

**`dev` (nash only):** Gpol share 1.141 (0.239°), Xf solver −0.139
(0.044°); mirror K G B and model (M1 − CASA) 1.015. The chains differ by
CASA's missing Gpol solution for one 3C286-SIM scan.

**Verdict by section 4's rule: outcome 1, located in the Xf solve** (ladder
1.06, mirror 1.08, same sign). Not a gauge split (rule 2).

**Post hoc (sections 6 and 7, labelled).**
- P1: CASA's Gpol completed with rang's rows where CASA has none gives
  rang's L1 Xf exactly (`held` 0.0000°, `dev` 0.0001°): the dropped
  intervals are the whole Gpol step. P2: rang with its Gpol rows removed
  where CASA has none: `dev` 0.044° from CASA (was 0.189°), `held` 0.064°
  (was 0.065°; P2's ≤ 0.02° not met there). The dropped intervals explain
  `dev`, not `held`.
- Weight probe (rang's Xf on L3's inputs): with each correlation's weight
  times |raw / corrected|², `held` 0.018° / 0.072° (from 0.065°), `dev`
  0.007°; unit weights on V/M 2.3°.
- `casawt` (CASA, Xf on data pre-corrected by `applycal` and split):
  `calwt=True` equals CASA's chain to 0.0000° (`held`, `dev`);
  `calwt=False` equals rang's L3 to 0.0000° (`dev`) and 0.015° / 0.035°
  (`held`). That 0.015° is not the averaging (against the averaged L3 also
  0.015°); it equals the dropped-interval step in size, and how each side
  interpolates CASA's Gpol across an interval missing inside a scan was not
  tested. The split's WEIGHT ratio is |G(p)|² |G(q)|² mean|B(p)|²
  mean|B(q)|² per correlation's hands to 1e-6 (the per-cell
  |raw/corrected|² of the probe is up to 4.6 % off it).
- **Cause:** CASA's polcal Xf weights each cell by the pre-applied tables'
  `calwt` factor; rang used 1/SIGMA² unscaled. Xf without D is biased by
  the 1-3 % leakage; our reading (not measured separately) is that the
  weighting sets that bias, so the two estimators differ by 0.04-0.07° here.

**Fix (section 7), `calibrate.xf_calwt: true`** (measured at `b534e20`):

| Gate | Measured | Limit | |
| --- | --- | --- | --- |
| F1 `dev` L3 with the key against CASA | 1e-5 / 2e-5 | 1e-3 / 5e-3 | pass |
| F2 `held` noavg against CASA | 0.012 / 0.036 | 0.05 / 0.25 | pass |
| F2 `held` avg against CASA | 0.021 / 0.025 | 0.05 / 0.25 | pass |
| F3 `held` max \|χ_avg − χ_CASA\| | 0.0064 | 0.0089 | pass |
| F3 `held` max \|χ − 33\| | 0.722 | 1.11 | pass |
| F4 `held4` noavg against CASA | 0.0003 / 0.0006 | ≤ 0.044 | pass |
| F5 tests (`tests/test_xf_calwt.py`, off unchanged, out of the stage hash) and quick check | PASS | | pass |

`held`'s remaining 0.012-0.021° is of the size of CASA's dropped Gpol
intervals (0.015°, P1); not separated further. Against the truth (fit residual after a
constant and a slope, which the gauge leaves free) the key moves rang
slightly away: `held` 0.102 → 0.108°, `held4` 0.114 → 0.119°, `dev` 0.098 →
0.117°. CASA's weighting is not nearer the truth here, so the key stays
off by default.

**Also found (CASA, not rang):** on noiseless data CASA 6.7.6.14's gaincal
drops a Gpol interval that reaches its 50-iteration limit (no row written)
and interpolates across it; on `dev` that removes a whole scan's Gpol and
moves χ by 0.13° against rang. Host-dependent (nash `dev` 0.189°, glacier
0.023° in xf-preavg; inferred, glacier's table was not read).

## For the coordinator

- Issue #33 located: CASA's polcal weights the Xf solve by the pre-applied
  tables' `calwt` factor (|G|² × channel-mean |B|² per antenna and hand),
  rang did not. Shown by a CASA arm on pre-corrected data: `calwt=True`
  equals CASA's chain to 0.0000°; `calwt=False` equals rang's solver to
  0.0000° on `dev` and 0.015° on `held` (unexplained remainder). Not
  averaging, not P, not the model, not KCROSS. With the key off (default)
  #33's gap is unchanged.
- Fix: `calibrate.xf_calwt` (default false, out of the stage hash; off
  byte-identical), Xf only. With it `held` is 0.012° (noavg) / 0.021° (avg)
  from CASA, `held4` 0.0003°. G, B, Gpol, KCROSS and Df weighting not
  measured (C2a section 10's open owner decision on CASA's weighting chain).
- Decide: default on (CASA equality) or off (truth slightly favours off);
  whether to extend calwt weights to the other solves (a separate frozen
  task: it moves every archive).
- CASA drops non-converged Gpol intervals on noiseless sims, host-dependent:
  CASA oracles on noiseless data can differ between glacier and nash by
  0.2° in Xf. Use noisy twins or check Gpol row counts in future gates.
- `calwt_factor` allocates times × antennas × channels × 4 complex values
  outside the chunk budget (about 1 GB at 90 times × 64 antennas × 4096
  channels); fine for the simulations, to bound before real-data use.
- Tests assert Xf gets the key and KCROSS does not (Gpol and Df build
  their own arguments and never receive it).
- Averaged rang Kcross differs from CASA by 0.0085 ns on one 10° scan
  (KCROSS share 0.21 of the averaged gap); recorded, not chased.
- Quick check on glacier: PASS in 737 s at `b534e20` plus the index entry
  (369 passed, gain-hash gate PASS); the later commits add docs, receipts
  and two tests (stage hash, KCROSS not keyed), run separately and passing.
  Full check (CASA oracles, archives) left to the coordinator's merge check.
- CI: run 44144084367 (`tests` at `8ea894c`) went red on the missing
  research-index entry (fixed in the next commits).
- Disk: nash `~/rang-data/outputs/xf-gap-20261117` 77 MB, can go at merge.
- To rerun: `research/results/xf-gap/nash/drive.sh` (section 5), then
  `post.sh`, `post2.sh`, `fix.sh` in the run root; each log ends
  `DRIVE END rc=N`.

## Coordinator decisions, 2026-11-17

- **`calibrate.xf_calwt` stays opt-in, default false.** It closes the rang-CASA Xf gap to 0.012°
  (held, unaveraged) against the 0.05° limit, and it is the right switch for CASA equivalence. But
  CASA's calwt weighting is not closer to the simulated truth (fit residual 0.102° → 0.108°). The
  default should follow the truth, not the oracle.
- **Extending calwt weights to G, B, Gpol, KCROSS and Df is not done here.** It would move every
  archive and is a separate frozen task. It is a v0.4 candidate, with the E2 gates re-read before
  any default.
- **The CASA finding is a known oracle limitation.** On noiseless simulations CASA silently drops
  Gpol intervals that hit its 50-iteration limit, so CASA oracles can differ between hosts. Later
  noiseless CASA oracles should log dropped intervals, and a reproduction control must check them
  before any ladder number is read.
- **Process note accepted as recorded.** The second driver part was started before the dev failure
  was read. No number from it was read before the amendment was committed.
- **Open items stay open:** the averaged Kcross is 0.0085 ns from CASA on one scan, and
  `calwt_factor`'s allocation sits outside the chunk budget (about 1 GB at 64 × 4096). The second
  must be bounded before the key could become a default.
- Issue #33 closes with this merge.
