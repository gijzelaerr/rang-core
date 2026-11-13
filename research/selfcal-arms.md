# Self-calibration arms 1 and 2: more rounds with longer first intervals, a phase-only first round

Issue [gijzelaerr/rang-core#6](https://github.com/gijzelaerr/rang-core/issues/6),
arms 1 and 2 (roadmap v0.3.0; arm 3, joint gains and image, is v0.6.0). Branch
`claude/selfcal-arms-82d5c9` from main `30d9412`, 2026-11-13. Native Windows.

**Status: proposed.** Sections 1 to 6 are the protocol, committed before any
code that tests it and before any arm is scored. Results go in section 8 and
later, dated; changes after a result are labelled post hoc.

## 1. Hypothesis

C5 ([c5-selfcal.md](c5-selfcal.md)) and C5b
([c5b-selfcal-masks.md](c5b-selfcal-masks.md)) found that the loop's CLEAN
model, imaged from gain-corrupted data, absorbs the gain errors on baselines
longer than about 2 km. The solve is not the limit: a model imaged from data
corrected by the true gains passes every T2 row. Masks do not help, an oracle
mask included.

**Hypothesis.** Changing the loop's schedule, with no new algorithm, lets the
model converge to the sky before the short-interval solves that are gated:

- **arm 1:** more rounds, the first ones on longer solution intervals;
- **arm 2:** a phase-only first round.

With either schedule the loop meets C5's T2 gate on the held-out cases where
C5's two-round loop does not.

**Not claimed.** Both arms are CARACal's own options (`cal_niter`, the
per-round `gain_matrix_type` and `gsols_timeslots` lists), so no result here
is novelty (AGENTS.md, Claims). A pass would show that `rang-core selfcal`
with a stated schedule recovers the simulated gains. It would not show an
improvement over CARACal.

**Prior development evidence (C5 section 7, post hoc, `c5pa` only).** Four
rounds (Sp, Sp, Sa, Sa at solint 8) gave phase p95 of 16.6, 13.7, 12.3 and
11.7° per round, against a limit of 1.5-3°. More rounds alone at solint 8
converge slowly. Neither longer first intervals nor a phase-only first round
on the delay truth has been run.

## 2. What the arms need in `rang-core selfcal`

The arms need no new configuration key. C5's schema already expresses them:

- `selfcal.rounds` is CARACal's `cal_niter`;
- `selfcal.terms` holds one term per round, the last repeating;
- each term has its own `solint` (`inf` is the scan, N is N integrations
  from each scan start) and, for Sp and Sa, its own `freqint`.

So the arms are configurations, and the defaults stay C5's: 2 rounds,
`[{Sp}, {Sa}]`. E2's configurations, stage hashes and results are untouched,
because no key, default or code path of the stage changes. A new key would
change the selfcal stage hash, as C5b's keys did. The branch adds:

- `examples/check_selfcal_arms.py`: the harness. It holds the frozen arm
  configurations, generates the cases, runs the stage under the main
  checkout's `tools/heavy_lock.py` with shared slots, scores with the frozen
  mapping of section 4, and runs QuartiCal on the new interval forms.
- `tests/test_selfcal_arms.py`:
  - every arm configuration validates, with no refusal under `selfcal`;
  - the round-to-term mapping is as frozen;
  - the defaults, and E2-A's selfcal section and hash, are unchanged;
  - the stage runs every arm's schedule end to end on the public fixture
    (scan 9 of `outer_scans.zip`, SHA256 `d4dae56f…`, through
    `rang.notebook.data`), with real gemclean on a small image. This checks
    that the stage executes and that the store bins and term types follow
    the schedule. It is not a quality measure: the fixture has no truth. The
    test skips without the fixture.

If a run shows that a schedule cannot be expressed or crashes, the fix goes in
as a labelled code change before the held-out runs, and section 7 records it.

## 3. Data, oracles and images

**Simulated truth (primary oracle):** C5's generator
`examples/c5_selfcal_sim.py`, unchanged. The sets have:

- 32 antennas and 64 channels of 13.375 MHz;
- seven target scans of 16 integrations (8 s);
- the `pa` and `delay` truths of C5 section 3, with gains constant over
  8-integration blocks, two blocks per scan.

No new seeds are drawn.

| Case | Truth | Seeds (jones, sky, rfi, noise) | Role here |
| --- | --- | --- | --- |
| `c5pa`, `c5delay` | pa, delay | 20261301-04, 20261311-14 | development |
| `c5pa-held`, `c5delay-held` | pa, delay | 20261321-24, 20261331-34 | **held out** (C5's pair; seen before only with C5's and C5b's arms) |
| `c5pa-held2`, `c5delay-held2` | pa, delay | 20261501-04, 20261511-14 | **held out** (C5b's pair; seen only with `u` and `m`) |

Each case is generated once, natively, into `RUN/data/` and copied for each
arm's run, so every arm sees the same bits.

**Images (every arm):** C5's frozen image section, unchanged apart from the
thread count:

- 2048 × 2048 pixels at 2asec;
- Briggs robust 0;
- Högbom CLEAN, `niter` 100000, `auto_threshold` 3;
- no mask; `fields: [target]`;
- `threads: 4`, which matches the lock's slots and does not change the
  result. A probe checks that claim on `c5pa` with `u` (section 6).

Holding the images fixed isolates the schedule. Crossing the schedules with
C5b's masks is not part of this protocol.

**QuartiCal 0.2.7 (second oracle, solve agreement):**
`rang-formats-oracle:20261030` in WSL, with C5's `QC_OPTIONS` and C5's G2
class B tolerance:

- products: median ≤ 7e-4 and p95 ≤ 3e-3;
- Sd delays: median ≤ 0.01 ns and p95 ≤ 0.03 ns;
- precondition: rang's re-solve on the oracle's copy equals the stored gains
  bit for bit.

The solve code is unchanged since C5, which met G2 to 1e-15. QuartiCal runs
here only on the interval forms C5 did not compare, round 1 of each on
development:

- arm 1 `Sp, solint inf` and `Sd, solint inf`;
- arm 2 `Sp, solint 8, freqint 1`.

**CARACal on E2-A (later):** issue #6 names it. It is not part of this task.
It runs after v0.2.0, and only for an arm whose verdict (section 5) is
"met" or "helps".

## 4. Arms (frozen)

Each arm is one `selfcal` section. All arms use `input_column: DATA`,
`refant: 0`, `gain_clip [0.5, 2.0]` and `minuvw_m: 0`; every other key is at
its default.

| Arm | Loop | rounds | terms (round 1, 2, ...; the last repeating) |
| --- | --- | --- | --- |
| `u` (baseline, C5's) | pa | 2 | `{Sp, solint 8}`, `{Sa, solint 8}` |
| `u` | delay | 2 | `{Sd, solint 8}`, `{Sd, solint 8}` |
| **`r`** (arm 1) | pa | 5 | `{Sp, solint inf}`, `{Sp, solint inf}`, `{Sp, solint 8}`, `{Sp, solint 8}`, `{Sa, solint 8}` |
| **`r`** (arm 1) | delay | 5 | `{Sd, solint inf}`, `{Sd, solint inf}`, `{Sd, solint 8}`, `{Sd, solint 8}`, `{Sd, solint 8}` |
| **`p`** (arm 2) | delay | 2 | `{Sp, solint 8, freqint 1}`, `{Sd, solint 8}` |

- **Arm 1.** `inf` is the scan, 16 integrations: twice C5's interval and the
  longest one that stays inside a scan. Two long rounds come first, so that
  the first models are imaged after the base phases (±30°, or the delays)
  are removed and before the solve can follow the block scatter. Then come
  two short phase rounds and, on pa, the amplitude round.
- **Arm 2.** On L-pa, C5's loop already starts with a phase-only round (Sp),
  so arm 2 on pa is arm `u`. It is not run twice and has no verdict of its
  own on pa. On L-delay, C5's round 1 is Sd. Arm 2 replaces it with a
  phase-only Sp round per channel (`freqint 1`; a band-averaged phase would
  lose up to about 120° of delay slope across the band), so that the first
  model is imaged from phase-corrected data before any delay is fitted. The
  round count stays at 2 to isolate the change.

**Gated rounds, a frozen mapping of C5's T2 table (`check_c5.T2`, limits
unchanged).** C5's table is keyed by rounds 1 and 2 of a two-round loop. For
an arm of R rounds:

- **round R** takes T2's round-2 rows of its loop:
  - pa: phase 0.5 / 1.5°, amplitude 1.0 / 3.0 %, and the amplitude median at
    most 0.25 × the uncorrected one;
  - delay: delay 0.01 / 0.03 ns and phase per channel 1.0 / 3.0°;
- **round R − 1** takes T2's round-1 rows that apply to its term:
  - phase 1.0 / 3.0°, every term;
  - delay 0.02 / 0.06 ns, only when the term is Sd. Arm `p`'s round 1 is Sp,
    so the delay row does not apply to it;
- **rounds before R − 1** are reported, not gated. A round whose bins span
  two truth blocks (`solint inf`) cannot be scored against block truth: C5's
  `against_truth` returns nothing for it. Its block scatter, N(0, 10°) per
  block, would in any case keep it from the round-1 limits. Such rounds are
  reported as "not scored".

For `u` (R = 2) the mapping is C5's own table, so `u`'s verdicts are C5's.

## 5. Decision rule (frozen)

Per arm and loop, on the held-out cases of that loop (pa: `c5pa-held`,
`c5pa-held2`; delay: `c5delay-held`, `c5delay-held2`). Each pair is reported
apart; the verdict needs both.

- **Met:** every gated T2 row passes on both held-out cases.
- **Helps, not met:** not met, and round R's phase p95 is at most 0.8 × that
  of `u`'s round 2 on both held-out cases (the 20 % rule of issue #6's
  plan).
- **Worse:** not met, and round R's phase p95 is above 1.2 × `u`'s on at
  least one held-out case.
- **Null:** anything else (not met, within 20 % of `u`).

A "met" or "helps" verdict sends the arm on to CARACal on E2-A (after
v0.2.0) and to an owner decision on defaults. Defaults never change in this
task. A null or worse verdict closes the arm, recorded as carefully as a
pass.

Reported and not gated:

- every round's phase, amplitude and delay errors;
- rounds marked "not scored";
- the median phase error per antenna;
- the last round's MODEL_DATA against MODEL_TRUE per baseline-length bin
  (C5's diagnostic, and the mechanism);
- the components, major cycles and stop reason of each image;
- C5's G4 apply check on the final column;
- the stage wall time.

## 6. Order, stop rules and cost

Run directories are `D:\rang\outputs\selfcal-arms-20261113-NN`. Each `.code/`
holds the harness, the commit and the gemclean binary's sha256.

1. This note is committed. Then the harness and test are committed.
2. **Probe** (`-01`): `u` on a copy of `c5pa`, once with `threads: 4` and once
   with gemclean's default threads. The check is the exit status, and that
   the two runs' stored gains are equal; truth is not scored. If they
   differ, `threads` is left at the default and the stage runs with
   `--slots 8`. The probe also runs arm `r` once to check that it executes.
3. **Development** (`-02`): `u` and `r` on `c5pa` and `c5delay`, and `p` on
   `c5delay`, scored. QuartiCal on the three new interval forms (section 3).
   `u`'s numbers are compared with C5b's native arm `u` (consistency; this
   worktree's gemclean differs from C5b's binary, so the digits may move).
4. **Post-hoc variants.** If a frozen arm fails T2 on development, at most
   one variant per arm may be tried. It is tried on development only, uses
   only existing keys (`rounds`, the terms, `solint`, `freqint`) and is
   labelled post hoc. At most one variant per arm goes to the held-out cases,
   beside the frozen arm. The frozen arm always runs on the held-out cases
   and alone carries the section 5 verdict.
5. **Freeze record** (section 7), committed before any held-out MS of this
   task is generated. It names the code commit, the gemclean sha256 and any
   variant that goes along.
6. **Held out** (`-03`): every held-out case runs once with `u`, `r` (both
   loops), `p` (delay) and any variant. Nothing is redrawn or rerun to
   change a number.

**Cost.** The stage wall time of each run (`stage-timing.json`, lock wait
excluded where the lock reports it) goes in `research/tool-timings.md`. The
host is shared, so this is not a timing claim. Arm `r` runs 5 rounds plus a
final image, against `u`'s 2 plus one, so it is expected to cost about 2.5 ×
`u`. That ratio is stated with every verdict.

**Lock.** Every stage runs under
`python C:\Users\gijsm\Github\rang\tools\heavy_lock.py run --slots 4 --mem 4
-- ...` at normal priority. C5 measured a peak of 2.25 GB.
