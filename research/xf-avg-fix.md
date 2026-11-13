# Xf and time pre-averaging across parallactic angle

Task xf-avg-fix (v0.2.0 critical path, 2026-11-13). The defect was found by
chi-offset (branch `claude/chi-offset-80cb6a`, `research/chi-offset.md`
sections 8 and 10, owner decision 3): with `calibrate.average_time: true`,
an Xf solve with `combine: scan` averages the P-rotated model and the data
across scans at different parallactic angles ψ. On chi-offset's noiseless
simulation (control truth, four 3C286-SIM scans over 115° of ψ) Xf moved 78°
(median) against the unaveraged solve, which equals CASA.

Status: section 1 measured; sections 2-3 frozen 2026-11-13 before any code of
this task; results below the line, dated.

## 1. Exposure of E2-A (measured 2026-11-13)

The brief assumed E2-A solves Xf with `combine: scan` and `average_time` on.
It does not.

- **E2-A's frozen configuration** (`research/results/e2-acceptance-scripts/e2a.yaml`
  on `fp-e2-acceptance` at 63b8641, read, not edited) has no `polcal` block
  and no Xf, KCROSS, Gpol or Df term. Its terms are K0, G0, B0 (`combine:
  scan`), A0, K1, G1, B1 (`combine: scan`) on J1939-6342 and selfcal Sp, Sa
  on the target; `average_time: true` is line 30, `selfcal.average_time: true`
  line 69. Line 56 is `scale: 3asec`. The Xf line the brief quotes
  (`{type: Xf, ..., combine: scan, parang: true, ...}`, line 56) is
  `e2b.yaml`'s.
- **E2-A's data** (`rang-core listobs D:\rang\data\e2-a\e2a.ms`, 2 s): ESO137
  ms1, project 20190507-0022, 4,096 channels, XX XY YX YY, 61 antennas. Scans
  9 and 11 J1939-6342 (6 min 56 s each), scan 10 ESO137-001 (60 min). **Two
  fields, no polarisation calibrator: 0 polcal scans, so no Xf and no ψ range
  to combine.**
- **No other route.** K, G, B and F (`rang.cal_delay`, `cal_gain`,
  `cal_bandpass`, `cal_fluxscale`) and selfcal Sp, Sa (`rang.cal_selfcal`)
  never apply P; only `rang.cal_pol`'s solves (Gpol, KCROSS, Xf, Df) rotate
  the model by P before averaging (`_PolField.prepare`). J1939-6342's model is
  Stokes I (Stevens-Reynolds 2016), which P leaves unchanged.
- **Expected Xf error for E2-A as frozen: none (no Xf term).** E2-A's B0 and
  B1 do average scans 9 and 11 together; that is CASA's `bandpass` with
  `combine='scan'` and an unpolarised model, not this defect.
- **E2-A has no rang result yet.** `D:\rang\outputs\e2-20261113-30-e2a` holds
  only `build-verify.log`, `verify.json`, `flaghash-input.json` (2026-11-13
  15:45); the branch's last commit (63b8641) says the rang arm waits.

**Where the exposure is.** Every configuration with `average_time: true` and
a polarisation term, on `main` and `fp-e2-acceptance`, is E2-B's family:
`e2b.yaml`, `e2b-amended.yaml`, `e2b-dev.yaml`, `e2b-amended-dev.yaml` and
five dev-archive configs. E2-B's MS (`listobs D:\rang\data\e2-b\e2b.ms`)
holds one J1331+3030 scan (17, 16:42:14-16:52:06, ψ 145.3-147.2°, chi-offset
section 9) and one J1939-6342 scan (18): its Xf (`combine: scan`) and Df
(`combine: scan`) each average one scan, Gpol 60 s, KCROSS one scan. **E2-B is
not exposed** (as chi-offset found). No E3 configuration on these branches
has a polarisation term with `average_time`.

## 2. The rule (frozen 2026-11-13, before any code)

**Rule.** When a `rang.cal_pol` solve (Gpol, KCROSS, Xf, Df) is time
pre-averaged and its model is rotated by P (`parang: true`), an averaged row
holds samples of **one scan** only, and within one solution interval and one
scan the samples' ψ spans at most **ψ_tol = 5°**. Concretely, per (solution
interval, scan) of the field's rows:

- ψ of a row is P's angle of its ANTENNA1 (the angle table the solve already
  uses; the receptor angle is a constant and cancels), taken as the circular
  difference (−180°, 180°] from the first row of that (interval, scan);
- span = max − min of those differences; n = max(1, ceil(span / ψ_tol));
  piece = min(floor((ψ − min) / (span / n)), n − 1);
- an averaged row is one (interval, scan, piece, ANTENNA1, ANTENNA2), ordered
  in that order; the solve's interval is unchanged (Xf with `combine: scan`
  still solves one interval over all scans, on more averaged rows).

When every interval of the field is one (scan, piece), the averaging is the
existing code path, unchanged (no group key is formed), so those solves are
bit-identical by construction. K, G, B, F and selfcal are not touched. Solves
without P (`parang: false`) are not touched.

This is CASA's behaviour in kind: CASA's `polcal` pre-averages within
`preavg` (300 s by default) and so never across scans hours apart; the ψ cap
also bounds a long scan near transit.

**Tolerance, why 5°.** Averaging a cross-hand model whose phase is 2ψ over a
ψ range W keeps sin W / W of its amplitude: 0.99873 at 5°, so the
closed-form Xf (`arg Σ w V M*` over averaged rows) moves by at most a
fraction ≈ W²/3 = 0.25 % of the leakage-to-polarised ratio. 5° exceeds every
single-scan span seen so far (E2-B scan 17 1.85°, chi-offset's sim scans
≤ 0.45°, the public fixture's fields 1.2°), so none of those solves changes.

**Gates** (all must pass):

1. **Simulation control.** chi-offset's control truth
   (`D:\rang\outputs\chi-offset-20261113-02-sim\truth-control`, read-only;
   arms written to `D:\rang\outputs\xf-avg-fix-20261113-*`), chi-offset's
   `sim_chi.py` rang arm `m90` with `average_time: true` and the fix: |χ − 33°|
   ≤ 1.11° (C6w's tolerance, which the `average_time: false` arm met with
   0.95°) on each of the four 3C286-SIM scans. Reported, not gating: χ per
   scan against `m90_noavg` and CASA, the Xf table against `m90_noavg`'s
   (median and max |Δ| over unflagged channels), and the feed0 `null` arm with
   averaging on.
2. **Bit-identity where no average crosses a ψ step.**
   (a) E2-B: from `e2b.ms`'s metadata and the solve's own angle table, every
   interval of Gpol (60 s on 3C 286), KCROSS and Xf (3C 286) and Df (J1939)
   is one (scan, piece), so the fixed code takes the unchanged path;
   (b) on the public fixture (`test_c2e_calibrate.calibrator_ms` with
   `_with_feed`), every Gpol, KCROSS, Xf and Df table with `average_time` on
   and off has the same SHA-256 as at the base commit 30d9412;
   (c) the existing gain hashes and averaging tests pass unchanged
   (`tests/test_e2_average_time.py`, the gain-hash tests, `check_all --quick`).
3. **Tests on the public fixture**: a field split into two scans whose times
   differ by hours (ψ tens of degrees apart) gets one averaged row per scan and
   baseline; the averaged Xf then equals a NumPy reference of the per-scan
   average and the unaveraged Xf within a stated tolerance, while the
   whole-interval average (the old estimator) does not; a ψ range wider than
   ψ_tol within one scan is split into equal pieces.

If gate 1 fails, the fix is not shipped and the result is reported.

## 3. E2-A's amended arm: void (2026-11-13, before any E2-A result)

The coordinator's rule asks for `e2a-amended.yaml` (the fix on, nothing else
changed), committed before any E2-A result exists. The fix is unconditional
(no configuration key), so that file would be byte-identical to the frozen
`e2a.yaml`, and section 1 shows E2-A has no P-rotated solve, so every E2-A
table is bit-identical with and without the fix. **No amended arm is written
for E2-A: E2-A as frozen is the record, and it is unaffected.** E2-B's
frozen and amended arms are likewise unaffected (gate 2a). Not edited:
`fp-e2-acceptance`.

---

(Results below this line, dated.)

## 4. Implementation (2026-11-13)

- `rang.cal_chunks.psi_groups(time_bin, scan, psi, tol_deg=PSI_TOL_DEG)`:
  section 2's rule; returns None when every interval is one group.
  `cal_chunks.Average(..., group=None)`: with groups, one averaged row per
  (group, baseline) in (interval, group, ANTENNA1, ANTENNA2) order, each
  carrying its interval; without, the code is the old one line for line.
- `rang.cal_pol._PolField.chunks(average=True)` (KCROSS, Xf, Df): groups from
  the solve's own angle table when P is on.
- `rang.cal_pol.gpol` passes P's angles (`average_psi`) to
  `rang.cal_gain.gaincal`, whose `_Field.averaged` forms the groups; K, G, B,
  F and selfcal never pass angles.
- Docs: `calibrate.average_time`'s description (`docs/cli.md` regenerated),
  `docs/limits.md`, `docs/howto/calibrate.md`.

## 5. Results (2026-11-13)

Host: the Windows workstation (16 threads). Scripts and archives in
`research/results/xf-avg-fix/`; run root
`D:\rang\outputs\xf-avg-fix-20261113-01-sim` (chi-offset's control and feed0
truths copied in, 301 MB); chi-offset's `sim_chi.py` and `chi_vs_psi.py` taken
unchanged from `claude/chi-offset-80cb6a` at b12d2c3.

**Gate 1, PASS** (`gate1.json`). Control truth, rang `m90`
(`average_time: true`, `feed_angle_rotation: -90`) with the fix:

| Scan | ψ | χ fixed, averaged | χ unaveraged | χ CASA | χ averaged before the fix |
| --- | --- | --- | --- | --- | --- |
| 2 | −121.2° | 33.376° | 33.377° | 33.378° | 49.51° |
| 8 | −140.4° | 33.863° | 33.864° | 33.865° | 38.16° |
| 14 | +167.8° | 32.999° | 32.999° | 32.998° | 33.57° |
| 22 | +122.9° | 33.946° | 33.947° | 33.947° | 33.35° |

max |χ − 33°| = 0.946° ≤ 1.11°; fixed averaged against unaveraged ≤ 0.0012°,
against CASA ≤ 0.0015°; p 0.0935-0.0952 (truth 0.095). Xf table against the
unaveraged arm's: median 0.012°, max 0.015° over 4,096 channels (before the
fix: 78.1° median, 107.2° max). Reported: feed0 truth, `null` arm, averaged
with the fix, max |χ − 33°| 0.796°, ≤ 0.0003° from unaveraged, Xf median
0.003° (before: 99.4°). The unaveraged arms reproduce chi-offset's χ exactly
(the fix does not touch them). Four rang arms, 13.4-14.3 s each, heavy lock
critical, 4 slots, 4 GB.

**Gate 2, PASS.**
(a) `e2b_groups.py` on `D:\rang\data\e2-b\e2b.ms` (`e2b-groups.json`, 10 s):
Gpol (3C 286, 10 intervals of 60 s, scan 17, max span 0.25°), KCROSS and Xf
(3C 286, one interval, scan 17, 1.92°), Df (J1939-6342, one interval, scan
18, 2.67°): every interval one group, so E2-B's (frozen and amended) solves
take the unchanged path.
(b) `fixture_hashes.py`: the 20 tables (Gpol, KCROSS, Xf, Df on both fields;
averaging on and off; one call and chunked) have the same SHA-256 at 30d9412
(main checkout's code) and with the fix (`hashes-base-30d9412.json`).
(c) `tests/test_e2_average_time.py` and `test_e2_average_freq.py` pass
unchanged; the full quick check is in section 6.

**Gate 3, tests** (`tests/test_xf_avg_fix.py`, 9 tests, 2.7 s): the rule's
cases (one scan, two scans in one interval, a wide scan cut into equal pieces,
the ±180° wrap); on the fixture with field 1's second half moved 3 h later
(ψ −80° then −16°), DATA the P-rotated polarised model with a cross-hand
phase of 40.1° and a constant leakage: the averaged Xf equals a loop
reference of the per-scan average (2e-6) and the unaveraged Xf within 0.5°
(0.16° measured), which is 1.1° from the truth; the whole-interval average
(the old estimator) is 6° off in median; Gpol, KCROSS, Xf and Df each average
into 12 rows (6 baselines × 2 scans), P off into 6; a 0.3° tolerance cuts the
scans into pieces and Xf equals the reference per piece.

**Verdict: the fix ships.** E2-A and E2-B are unaffected (sections 1, 3 and
gate 2a); any later run that solves Xf over several 3C 286 scans with
`average_time` gets the per-scan average, equal to the unaveraged solve and
CASA on chi-offset's simulation.

## 6. Checks (2026-11-13)

`python tools/check_all.py --quick --priority critical`: PASS in 1,517 s
(fmt, ruff, clippy, Rust tests, extension build, pytest on the diff's files
215 passed / 27 skipped, gain-hash gate PASS); log
`outputs/check/20261113T152941Z-quick.log`. The full check (CASA, QuartiCal,
WSClean oracles) is left to the coordinator's merge check.

## For the coordinator

Branch `xf-avg-fix`. The brief's premise was wrong: E2-A has no polcal scan
(section 1), so its amended arm is void (section 3) and nothing was written
for it; E2-B is not exposed either. The fix is unconditional in `rang.cal_pol`
and Gpol's path through `rang.cal_gain`; gates 1-3 pass. Run outputs:
`D:\rang\outputs\xf-avg-fix-20261113-01-sim` (sim arms, deleted after
scoring except the JSONs archived here).
