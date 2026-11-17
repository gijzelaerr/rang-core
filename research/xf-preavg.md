# Xf pre-averaging: held-out check of xf-avg-fix against CASA

Task xf-preavg (issue #14, chi-offset section 10.3, coordinator decision
2026-11-17). Status: **proposal, frozen 2026-11-17** before any solve of this
task. Results go in dated sections below the line.

## 1. The premise was stale

The brief asked for a fix of chi-offset's averaging defect (section 8 of
`chi-offset.md`: with `calibrate.average_time` and Xf `combine: scan` over
3C286-SIM scans at different ψ, Xf moved 78° median against the unaveraged
solve, which equals CASA). **That defect was fixed on `main` on 2026-11-13** by
task xf-avg-fix (`research/xf-avg-fix.md`; rule frozen in 7132274, code in
cd446e2, merged f8a6435): a P-rotated `rang.cal_pol` solve (Gpol, KCROSS, Xf,
Df) averages no samples of two scans and no samples spanning more than
ψ_tol = 5° (`rang.cal_chunks.psi_groups`). Its gate 1 passed on chi-offset's
dev simulation (χ within 0.95° of 33°, within 0.0015° of CASA, Xf within
0.015° of the unaveraged solve). chi-offset's "Not fixed here" (sections 8 and
10.3), written before that task, is what the brief read; section 10.3 gets a
dated pointer.

So this task does not write a new fix. It measures what xf-avg-fix did not:

- **No held-out set.** Gate 1 ran on the dev truth that found the defect.
- **The piece split was never run against CASA.** Every dev 3C286-SIM scan
  spans ≤ 0.47° of ψ, so the split of one scan into 5° pieces was only
  unit-tested (`tests/test_xf_avg_fix.py`).
- **No Xf table against CASA's.** Gate 1 compared rang's Xf with rang's
  unaveraged Xf, and χ with CASA's χ; CASA's Xf table was not read.
- **CASA's `preavg` was assumed** (300 s from its documentation), not read.

## 2. Hypothesis

H: on a held-out simulation whose 3C286-SIM scans span more than 5° of ψ,
rang with `average_time: true` (the per-scan, ≤ 5° pieces) gives the same Xf
and χ as rang unaveraged and as CASA 6.7.6.14's `polcal` at its default
`preavg`, within section 3's tolerances, and χ within C6w's 1.11° of the truth.

Why the tolerance can be tight: averaging data and model together over a ψ
range W scales the rotated polarised model by sinc W = sin W / W and leaves
the leakage term unchanged, so the closed form `arg Σ w V M*` moves its
existing leakage bias by a fraction 1/sinc W − 1 ≈ W²/6 = 0.13 % at 5°.
With that bias ≤ 1.11° (C6w), the shift is ≤ 0.0015°, which is what gate 1
measured (0.0012°). CASA's 300 s average on these scans spans ≤ 4.2° (the
fastest ψ rate here is 0.84° per minute), the same order. The tolerances
below are 30 times that bound, to allow for the Gpol and KCROSS solves (also
averaged) and for CASA's different chunking.

## 3. Data, settings, gates and decision rule (frozen)

**Code under test:** `origin/main` at d3746c9, extension built in this
worktree (`maturin develop --release`). No package code is changed before
the rule is evaluated.

**Data.**
- **Dev:** chi-offset's control truth
  (`D:\rang\outputs\chi-offset-20261113-02-sim\truth-control`, read-only,
  copied to the run root): poldx's noiseless twin, 16 antennas, 256
  channels, four 3C286-SIM scans of 4 × 8 s (ψ −121°, −140°, +168°, +123°),
  FEED −90°.
- **Held-out (new):** `rang.simtruth_ms generate poldx --noiseless --seeds
  20261751,20261752,20261753,20261754` (fresh Jones, sky, RFI and noise
  seeds; unused anywhere in the repository), control truth (FEED −90°,
  a = ψ − 90°), with the 3C286-SIM scans 90 × 8 s = 720 s long
  (`SMALL_LENGTH["X"] = FULL_LENGTH["X"] = 90`, so later scans start later
  and ψ coverage changes). From the schedule alone (antenna 0, CASA frame):
  scans 2, 8, 14, 22 run −121.2→−123.7°, −145.8→−155.9°, +151.9→+142.7°,
  +118.7→+117.2°: spans 2.6°, **10.1°, 9.2°**, 1.4°, so scans 8 and 14 are
  split into 3 and 2 pieces. The `psi` step confirms this on the MS before
  any solve; if no scan spans more than 5° the run stops and the design is
  amended (dated) before any solve.

**Settings.** chi-offset's `sim_chi.py` unchanged (imported from
`research/results/chi-offset/`): E2-B's polcal chain (K, G, B on J1939−6342;
Gpol p 60 s, KCROSS inf, Xf inf `combine: scan`, Df inf `combine: scan` on
J1939−6342; `parang: true`; `feed_angle_rotation: -90`; apply with parang).
Arms per set: rang `m90` (`average_time: true`), rang `m90_noavg`
(`average_time: false`), CASA `m90` (FEED −90° written, polcal with no
`preavg` argument). χ estimator: chi-offset's (`chi_vs_psi.py`, unit-weight
mean over 0.8-1.8 GHz). CASA's `polcal` defaults are printed from the
container and archived.

**Gates** (degrees; χ per 3C286-SIM scan; Xf per unflagged channel and
polarisation over all antenna rows):

- **V0, dev reproduces xf-avg-fix:** dev `m90` χ equals
  `research/results/xf-avg-fix/gate1.json`'s `chi_fixed_avg` within 0.001°
  on every scan.
- **G_avg:** |χ_avg − χ_noavg| ≤ 0.05 per scan, and Xf avg against noavg
  median ≤ 0.05 and max ≤ 0.25.
- **G_casa:** |χ_avg − χ_CASA| ≤ 0.05 per scan, and Xf avg against CASA
  median ≤ 0.05 and max ≤ 0.25.
- **G_truth:** |χ_avg − 33| ≤ 1.11 per scan.
- Reported, not gating: noavg against CASA (same tolerances), p per scan,
  the number of averaging groups.



**Decision rule.**

1. **Fix holds:** V0, and G_avg, G_casa, G_truth on both sets. No code change;
   `preavg` stays "not ported" in `core_config` (rejected by the config
   check), and rang's ψ rule stands in for it. Whether to accept a
   `preavg` key as an alias or keep rejecting it is a coordinator decision.
2. **Regression:** V0 fails. The defect is back on `main`; bisect from
   cd446e2 to d3746c9, fix, and rerun the gates (a dated amendment first).
3. **Rule insufficient:** G_avg fails on the held-out set (V0 passes). The
   5° rule does not bound the error for wide scans; a dated amendment
   proposes a tighter ψ_tol or CASA's 300 s `preavg` as an extra cap, frozen
   before its code, and the gates are rerun.
4. **Other defect:** G_avg passes but G_casa fails and noavg against CASA fails
   too. rang and CASA differ without averaging; reported, not fixed here.
5. **Averaging differs from CASA only:** G_avg passes, noavg = CASA, G_casa
   fails (only possible near the tolerance edge). Reported with the numbers;
   treated as 3 if the Xf difference exceeds 0.25° on more than 1 % of
   channels.
6. **Design invalid for the absolute gate:** CASA's χ is also more than 1.11°
   from 33° on some held-out scan. G_truth is void; the rule is read on
   G_avg and G_casa alone, and the reason is reported.

Run root `D:\rang\outputs\xf-preavg-20261117-01-sim`; heavy jobs under the main
checkout's `tools/heavy_lock.py`; receipts in `research/results/xf-preavg/`.
Script: `research/results/xf-preavg/xf_preavg.py`.

---

(Results below this line, dated.)

## 4. Results against the frozen rule (2026-11-17)

Host: the Windows workstation (16 threads), heavy lock shared, 4 slots, 10 GB.
Run root `D:\rang\outputs\xf-preavg-20261117-01-sim`; receipts in
`research/results/xf-preavg/`: `results.json` (the gates), `psi-held.json`,
`psi-control.json` (ψ per scan, receptor −90° included, and the averaging
groups), `casa-polcal-defaults.txt`, `chain.sh`, `xf_preavg.py`.

**Design checks.** The held-out MS (677 MB, 448 integrations, 8.8 s to
generate) has 3C286-SIM scans 2, 8, 14, 22 spanning 2.68°, **10.30°, 9.35°**,
1.50° of ψ; `psi_groups` cuts the Xf interval into 7 averaging groups (1, 3,
2, 1 per scan). The dev set: spans 0.15-0.63°, 4 groups (one per scan).
CASA 6.7.6.14's `polcal` default, read in the container: `preavg` 300.0 s
(also `solint` 'inf', `combine` 'obs,scan' by default; the chain passes
`combine='scan'`).

**Tests at d3746c9:** `tests/test_xf_avg_fix.py` and
`tests/test_e2_average_time.py` 21 passed, 2 skipped (E2 metadata MSs not on
this host).

| Gate | Dev | Held-out |
| --- | --- | --- |
| V0: dev `m90` χ against gate1.json | 0.0005° (≤ 0.001): **pass** | – |
| G_avg: χ avg − noavg, max over scans | 0.0011° | 0.0062° |
| G_avg: Xf avg − noavg, median / max | 0.020° / 0.022° | 0.017° / 0.031° |
| G_avg | **pass** | **pass** |
| G_casa: χ avg − CASA, max | 0.0012° | 0.0069° |
| G_casa: Xf avg − CASA, median / max | 0.023° / 0.040° | **0.054°** / 0.107° |
| G_casa | **pass** | **fail** (median 0.054 > 0.05) |
| Reported: χ noavg − CASA, max | 0.00007° | 0.0023° |
| Reported: Xf noavg − CASA, median / max | 0.016° / 0.041° | **0.065°** / 0.114° |
| G_truth: max \|χ_avg − 33°\| | 0.946° | 0.723° |
| Reported: max \|χ_CASA − 33°\| | 0.947° | 0.721° |

χ per held-out scan (avg / noavg / CASA): scan 2 32.743 / 32.743 / 32.742;
scan 8 32.574 / 32.568 / 32.568; scan 14 32.608 / 32.609 / 32.611; scan 22
32.277 / 32.278 / 32.279. p 0.0946-0.0965 (truth 0.095), avg and CASA equal
to 4e-6.

**Verdict by the frozen rule: outcome 4 ("other defect"), not outcome 1.**
V0, G_avg and G_truth pass on both sets: the xf-avg-fix rule holds on the
held-out set, including the piece split of two scans wider than 5° (averaged
against unaveraged: χ ≤ 0.006°, Xf ≤ 0.031°). G_casa fails on the held-out
set, on the Xf median alone (0.054° against 0.05°; χ 0.007° and the Xf max
0.107° are inside), and rang **unaveraged** differs from CASA by more
(median 0.065°), so the difference is not rang's averaging. Rule 4: reported,
not fixed here. Size: 0.05-0.11° in Xf, under 0.01° in χ; far below every
calibration tolerance in use (C6w 1.11°).

## 5. Post hoc: CASA's `preavg` (2026-11-17, after section 4; labelled)

Not in the frozen protocol. To see whether outcome 4's Xf difference comes
from CASA's own 300 s pre-average on the 10° scans, CASA's chain was rerun
with polcal `preavg` 8 s (one integration) and 60 s (`xf_preavg.py
casa_preavg`; `posthoc.json`):

| CASA arm | Xf vs rang avg, median / max | Xf vs rang noavg, median / max | χ vs rang avg / noavg, max |
| --- | --- | --- | --- |
| dev, preavg 300 (default) | 0.023° / 0.040° | 0.016° / 0.041° | 0.0012° / 0.0001° |
| dev, preavg 8 | 0.035° / 0.052° | 0.021° / 0.032° | 0.0012° / 0.0001° |
| held-out, preavg 300 (default) | 0.054° / 0.107° | 0.065° / 0.114° | 0.0069° / 0.0023° |
| held-out, preavg 60 | 0.059° / 0.120° | 0.064° / 0.119° | 0.0069° / 0.0024° |
| held-out, preavg 8 | 0.052° / 0.101° | 0.055° / 0.108° | 0.0068° / 0.0023° |

CASA's `preavg` moves its Xf by at most 0.01° median here, so the 0.05-0.065°
rang-CASA difference on the held-out set is not pre-averaging on either
side. Its source is not found; a likely place is the terms solved before Xf
on the longer scans (Gpol at 60 s, KCROSS per 720 s scan), not checked here.
At under 0.01° in χ it has no effect on any gate in use.

**Reading (post hoc).** rang's averaging rule (xf-avg-fix, 5°) is as good as
CASA's `preavg` at its default or shorter on this data: averaged and
unaveraged rang differ by ≤ 0.031° in Xf, CASA's three `preavg` settings by
about 0.01° among themselves. Porting `preavg` would change nothing measurable.
It stays "not ported" (rejected by the config check).

## For the coordinator

- **No package code changed.** The fix for issue #14's item 3 has been on
  `main` since f8a6435 (xf-avg-fix). This branch adds the held-out check, the
  results, a dated pointer in `chi-offset.md` 10.3, timings and the STATE
  entry. Non-polarised terms are unchanged by construction.
- Outcome under the frozen rule: **4** (rang-CASA Xf median 0.054° > 0.05°
  on the held-out set, unaveraged too). The averaging gates pass.
- Decisions: (1) close issue #14's averaging item, or keep it open for the
  0.06° rang-CASA Xf difference (a separate diagnosis: compare the Gpol and
  KCROSS tables on the held-out set). (2) `preavg`: keep it rejected (as
  proposed), or accept it as a documented no-op alias for CASA scripts.
- On disk: `D:\rang\outputs\xf-preavg-20261117-01-sim` (860 MB: the two
  truths, the arms' tables and logs; the arm MSs were deleted after scoring).
  Can be deleted; every number is in the receipts.

## Coordinator decisions, 2026-11-17

- (a) #14's averaging item is closed: the xf-avg-fix rule holds on held-out data. The rang-CASA Xf gap
  (held-out median 0.054°, unaveraged 0.065°) is the frozen outcome 4. It is recorded as an open
  low-priority item under #14. It lies two orders below the χ science tolerance (7°), so no diagnosis
  runs now. If one runs later, it compares the held-out Gpol and KCROSS tables first.
- (b) `preavg` stays rejected ("not ported"). Accepting it as a no-op alias would suggest a behaviour
  rang does not have.
- The coordinator's brief was based on chi-offset 10.3's stale "Not fixed here". From now on a brief
  checks the STATE log and merged branches for an existing fix first.
- `D:\rang\outputs\xf-preavg-20261117-01-sim` is deleted at merge.
