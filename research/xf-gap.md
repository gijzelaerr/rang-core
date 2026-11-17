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
