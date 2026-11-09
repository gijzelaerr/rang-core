# C5b: per-image clean masks and cut-offs in self-calibration

Task C5b of [finish-plan.md](finish-plan.md), on branch `fp-c5b-masks` from
main `eaf40b7` (G4 merged), 2026-11-09. Native Windows.

**Status: implemented and measured.** The protocol (sections 1-3) was
committed (`b8ad597`) before any comparison; the freeze record (section 4)
before the held-out runs.

- **Not met: C5's T2 gate on the held-out cases**, new and C5's pair alike,
  with CARACal's masks (automatic, 10σ then 6σ, cut-off 0.5σ, multiscale):
  phase p95 9-17° against 1.5-3°, delay p95 0.064-0.128 ns against
  0.03-0.06, Sa amplitude median 1.7-1.9 % against 1 %. Only the delay
  medians pass.
- Against C5's unmasked loop on the same MSs the masks move the medians by
  at most 0.6° and leave the model error on > 6 km baselines unchanged; a
  post-hoc oracle mask from the true sky does no better. Masks do not lift
  C5's model-absorption limit.
- Implemented: `selfcal.clean_cutoff`, `cleanmask_method`, `cleanmask_thr`
  with CARACal's per-image semantics; no selfcal image reached `niter`.
  No novelty claim.

Row: "Per-round masks and image settings in `rang-core selfcal` (CARACal's
`cleanmask_thr`, `clean_cutoff`, auto-masking from G4) | oracle: C5's truth
sets | gate: C5's T2 gate met on its held-out cases".

## 1. What CARACal does (read in its source)

CARACal `8f7bb363` (`workers/selfcal_worker.py`, `schema/selfcal_schema.yml`,
`config_parser.py`; the shipped sources in the ignored
`outputs/c1-sources-20261105/caracal-8f7bb363/` of the WSL checkout, as C5
and G4 read them):

- **Images are numbered 1 to `cal_niter + 1`.** The loop (lines 2270-2340)
  calls `image(..., num)` for `num = 1`, calibrates, `num = 2`, ..., and the
  final image is `num = cal_niter + 1`.
- **Per-image lists, the last repeating.** In `image()` (lines 560-680):
  `auto-threshold = clean_cutoff[num - 1 if len >= num else -1]`;
  `mask_key = cleanmask_method[...]` the same way; for `mask_key == "wsclean"`
  WSClean gets `auto-mask = cleanmask_thr[...]` and `local-rms =
  cleanmask_localrms[...]` (with `local-rms-window` when true); `sofia` and
  `breizorro` build a FITS mask from an earlier image (SoFiA, Breizorro) and
  pass `fitsmask`; any other string is a prefix of an existing
  `masking/<prefix>_<field>.fits`, regridded to the image when needed
  (`mProject`) and passed as `fitsmask`. No `auto-mask` with a FITS mask.
  `col` (the data column) is a per-image list too, default `[DATA,
  CORRECTED_DATA]`.
- **Defaults.** CARACal takes a schema's `example` as the default
  (`config_parser.py`, lines 295-318): `clean_cutoff [0.5, 0.5]`,
  `cleanmask_method [wsclean, wsclean]`, `cleanmask_thr [10.0, 6.0]`,
  `cleanmask_localrms [False, False]`, `img_mgain 0.90`, `img_gain 0.10`,
  `img_niter 1000000`, `img_nmiter 0`, `img_multiscale False`. So CARACal's
  default self-calibration image is Högbom CLEAN with an automatic mask at
  10σ in image 1 and 6σ in images 2 and 3, each cleaned to 0.5σ inside its
  mask. Neither MeerKAT sample configuration
  (`meerkat-defaults.yml`, `meerkat-continuum-defaults.yml`) overrides these.

## 2. Implementation (implemented)

`rang.core_config` gains three `selfcal` keys, empty by default:

| CARACal | rang-core | Effect on image k (1 to `rounds + 1`) |
| --- | --- | --- |
| `clean_cutoff` | `selfcal.clean_cutoff` (floats) | `image.auto_threshold` |
| `cleanmask_method` | `selfcal.cleanmask_method` (strs) | `wsclean`: `-auto-mask` at `cleanmask_thr`; `none`: no mask; a `.fits` path (`{field}` = the field name): `-fits-mask`. Each replaces `image.auto_mask`, `abs_auto_mask` and `fits_mask` for that image |
| `cleanmask_thr` | `selfcal.cleanmask_thr` (floats) | the `-auto-mask` sigma where the method is `wsclean` |

- The index is CARACal's (`core_config.selfcal_image_index`), the final
  image being `rounds + 1`; `core_config.selfcal_image_settings(config, k,
  field)` returns the image section image k uses, and the stage passes it to
  `gemclean_arguments`. With the three lists empty every image's argv is
  C5's (unit-tested).
- Validation: a list longer than `rounds + 1`, a method that is neither one
  of `wsclean`, `none`, `sofia`, `breizorro` nor a `.fits` path, and
  negative values are schema errors. Refused: `sofia` and `breizorro` (not
  ported), `cleanmask_thr` without a `wsclean` method, `wsclean` without
  `cleanmask_thr`, and per image G4's rules (an automatic mask needs
  `image.mgain`; the cut-off below the mask's sigma; `auto_mask_nmiter`
  only with a mask).
- Not ported: `cleanmask_localrms` (gemclean refuses `-local-rms`, G4),
  CARACal's regridding of a FITS mask (gemclean needs the image's size), and
  `col` (rang's rule is CARACal's default: the input column for image 1, the
  output column after).
- The stage's summary records per image the cut-off, the mask, and
  gemclean's components, major cycles and stop reason
  (`core_pipeline.gemclean_stop`).
- The three keys are in the selfcal stage hash, so a selfcal stage finished
  before C5b needs `--force` once.
- Tests: `tests/test_c5b_selfcal_masks.py` (the index, unchanged argv,
  CARACal's defaults per image, `none` and FITS paths, errors and refusals,
  the stage with a portable stand-in gemclean, the stop-line parser).

## 3. Protocol (frozen before any comparison)

### Oracle, loops and gates

- **Oracle:** C5's simulated truths (`examples/c5_selfcal_sim.py`, C5
  section 3), unchanged: 32 antennas, 64 channels, seven target scans of 16
  integrations, `pa` and `delay` truths, gains constant over 8-integration
  blocks.
- **Loops:** C5's L-pa (`{Sp, solint 8}`, `{Sa, solint 8}`) and L-delay
  (`{Sd, solint 8}` twice), 2 rounds, `input_column: DATA`, `refant: 0`,
  other selfcal keys at their defaults.
- **Gate (T2):** C5's frozen T2 table (C5 section 4, `check_c5.T2`),
  unchanged, gauge-free products against truth: L-pa round 1 phase median ≤
  1.0°, p95 ≤ 3.0°; round 2 phase ≤ 0.5° / 1.5°, amplitude ≤ 1.0 % / 3.0 %,
  amplitude median ≤ 0.25 × the uncorrected; L-delay round 1 delay ≤ 0.02 /
  0.06 ns, round 2 ≤ 0.01 / 0.03 ns, phase per channel ≤ 1.0° / 3.0° in both
  rounds.

### Arms (image settings; every arm 2048², 2asec, Briggs 0, gemclean of this branch)

| Arm | Images | Role |
| --- | --- | --- |
| `u` | C5's frozen images: Högbom, `niter 100000`, `auto_threshold 3`, gemclean's measured `mgain`, no mask | the unmasked baseline, rerun natively on the same MSs |
| `m` | CARACal's defaults (section 1) with multiscale: `mgain 0.9`, `niter 1000000`, `multiscale: true`; `cleanmask_method [wsclean]`, `cleanmask_thr [10, 6]`, `clean_cutoff [0.5]` | **gated** |
| `mh` | `m` with Högbom (`multiscale: false`), CARACal's literal default | reported, development cases only |

Multiscale in the gated arm departs from CARACal's default (Högbom): G4
found the multiscale automatic mask finishing on WSClean's major iteration
and the Högbom one finishing two iterations early (G4 decision 4), and the
truth sky holds Gaussians of 20-120″ and an arc. `mh` measures what
CARACal's literal default would give.

### Cases

| Case | Truth | Seeds (jones, sky, rfi, noise) | Role here |
| --- | --- | --- | --- |
| `c5pa`, `c5delay` | pa, delay | 20261301-04, 20261311-14 | development |
| `c5pa-held`, `c5delay-held` | pa, delay | 20261321-24, 20261331-34 | C5's held-out pair: seen by C5 with arm `u` only; held out here (never run with `m` or `mh` before the freeze of section 4) |
| `c5pa-held2`, `c5delay-held2` | pa, delay | **20261501-04, 20261511-14** (new; not in `simtruth.SEEDS` or elsewhere before this task, registered now) | **held out**, frozen here; not generated before the freeze |

Every MS is generated natively once into `RUN/data/` and copied for each
arm's run, so `u` and `m` see the same bits. C5's WSL numbers are context
only (native builds differ from Linux ones in every file, G4 section 5).

### Verdict

- **C5b's gate is met** when arm `m` passes every T2 row on both held-out
  pairs (`c5pa-held2`, `c5delay-held2` and C5's `c5pa-held`,
  `c5delay-held`); each pair's verdict is reported apart (the finish plan
  names C5's pair, the brief new seeds).
- Reported, not gated: arm `u` against C5's published table (consistency);
  `m` against `u` per round on every case; `mh` on development; per image
  the components, major cycles and stop reason (E1 found every selfcal
  CLEAN stopped at `niter` 100,000); the last round's MODEL_DATA against
  MODEL_TRUE per baseline-length bin (C5's diagnostic); the median phase
  error per antenna; C5's G4 apply check on the final column.
- QuartiCal (C5's G2) is not rerun: the solve code is unchanged.

### Order

1. This protocol and the code are committed before any loop is scored. An
   execution probe (`D:\rang\outputs\c5b-20261109-01\probe`, arm `m` on a
   copy of `c5pa`, checked for exit status and stop lines only, never
   against truth) may run before.
2. Development: arms `u`, `m`, `mh` on `c5pa`, `c5delay`
   (`D:\rang\outputs\c5b-20261109-02`).
3. If `m` fails on development, variants may be tried on development only;
   each is labelled post hoc, and at most one is carried to the held-out
   cases, beside the frozen `m`.
4. The freeze record (section 4) is committed: the code commit, the gemclean
   binary's sha256 and whether a post-hoc variant goes along. Then the
   held-out MSs are generated and every held-out case runs once with `u`,
   `m` (and the variant, if any). Nothing is redrawn.

## 4. Freeze record

Written 2026-11-09 after the development runs (section 5), before any
held-out MS of this task was generated or run.

- Protocol and code: `b8ad597`. Commit `7c165af` adds only the post-hoc
  oracle-mask diagnostic (`examples/c5b_oracle_mask.py`, arm `mo` in
  `examples/check_c5b.py`); no setting of arms `u` or `m` changed.
- gemclean: `core/target/gemclean/gemclean.exe` built from `eaf40b7`'s Rust
  tree (unchanged on this branch), profile `gemclean`, rustc 1.93, sha256
  `0ce4aec02c5801834caeca357f7ce6e59af14c13cdbd3090c28244ecf2288e47`.
- **No post-hoc variant goes to the held-out cases**: neither `mh` nor `mo`
  met T2 on development, and `mo` (an oracle mask) was no better than `m`.
  The held-out cases run once with `u` and the frozen `m`.

## 5. Development (measured)

Run directory `D:\rang\outputs\c5b-20261109-02` (`.code/` holds `b8ad597`'s
scripts, the runner and the binary hash; START/END/rc of every job in
`logs/jobs.log`). The execution probe `c5b-20261109-01/probe` exited 0 and
was compared with nothing. Commands: `examples/check_c5b.py loop RUN CASE
ARM LOOP` (one stage, scored), `examples/c5b_summary.py` (the tables and the
archive).

Medians / p95: `|Δ arg P|` (°), `||P|/|P_true| − 1|` (%, with the median's
ratio to the uncorrected one), `|Δ(τ_p − τ_q)|` (ns):

| Case | Arm | Round | Phase | Amplitude | Delay | T2 rows failed |
| --- | --- | --- | --- | --- | --- | --- |
| c5pa | u | 1 Sp | 2.46 / 16.6 | – | – | phase |
| c5pa | u | 2 Sa | 1.88 / 13.6 | 1.05 / 3.98 (0.20×) | – | phase, amplitude |
| c5pa | **m** | 1 Sp | 2.10 / 16.1 | – | – | phase |
| c5pa | **m** | 2 Sa | 1.87 / 13.2 | 1.54 / 4.29 (0.29×) | – | phase, amplitude, ratio |
| c5pa | mh | 1 Sp | 2.33 / 15.3 | – | – | phase |
| c5pa | mh | 2 Sa | 1.87 / 12.8 | 0.84 / 3.66 (0.16×) | – | phase, amplitude p95 |
| c5delay | u | 1 Sd | 2.19 / 16.9 | – | 0.0201 / 0.131 | delay, phase |
| c5delay | u | 2 Sd | 1.55 / 13.1 | – | 0.0061 / 0.079 | delay p95, phase |
| c5delay | **m** | 1 Sd | 1.63 / 15.5 | – | 0.0123 / 0.108 | delay p95, phase |
| c5delay | **m** | 2 Sd | 1.29 / 12.6 | – | 0.0046 / 0.066 | delay p95, phase |
| c5delay | mh | 1 Sd | 1.87 / 12.9 | – | 0.0103 / 0.074 | delay p95, phase |
| c5delay | mh | 2 Sd | 1.39 / 10.9 | – | 0.0061 / 0.043 | delay p95, phase |

- **Arm `u` reproduces C5 natively**, to the printed digits of C5 section
  6.3: phase 2.46 / 16.6° and 1.88 / 13.6° (c5pa), 2.19 / 16.9° and 1.55 /
  13.1° (c5delay); amplitude 1.05 / 4.0 %; delays 0.020 / 0.131 and 0.0061 /
  0.079 ns.
- **CARACal's masks change little.** `m` against `u`: round-1 phase medians
  0.4-0.6° lower, the c5pa round-2 phase median unchanged (1.87 against
  1.88°), p95s 0.4-1.4° lower, delay medians 25-40 % lower, the c5pa
  amplitude median worse (1.54 against 1.05 %). Every p95 stays at 10-16°
  against limits of 1.5-3°.
- **The errors sit on the same antennas.** Median phase error per antenna
  (c5pa round 2): 0.8-1.8° on 22 antennas and 2.7-13.9° on antennas 22-25
  and 27-31 with `m`, against 0.9-1.9° and 3.2-14.4° with `u`.
- **The model is still wrong on long baselines.** rms `|MODEL_DATA −
  MODEL_TRUE|` / rms `|MODEL_TRUE|` (XX, last round) in the bins < 0.5,
  0.5-1, 1-2, 2-4, 4-6, > 6 km, c5pa: `u` 0.057, 0.045, 0.097, 0.158, 0.219,
  0.281; `m` 0.029, 0.044, 0.098, 0.156, 0.214, 0.281. The mask halves the
  shortest bin's error and leaves the long-baseline error where it was.
- **CLEAN depth.** Every image of every arm stopped on its threshold, none on
  `niter`: `u` 26-67 k components (Högbom, 3σ), `m` 8-11 k in image 1
  (10σ mask) and 45-99 k in images 2 and 3 (6σ mask, 0.5σ cut-off), `mh`
  2-16 k.
- C5's G4 apply check on the final column passes in every frozen arm.

### 5.1 Post hoc: an oracle mask (development only)

To test whether any mask could help, one was made from the truth alone
(`examples/c5b_oracle_mask.py`): MODEL_TRUE imaged with Högbom CLEAN on the
loop's grid to 0.1 mJy, the model's nonzero pixels dilated by 3 pixels
(42,259 pixels on c5pa, 40,465 on c5delay; 1 % of the image). Arm `mo` is
`m` with that FITS mask in every image and `clean_cutoff [0.5]`
(`D:\rang\outputs\c5b-20261109-02\oracle`):

| Case | Round | Phase | Amplitude | Delay |
| --- | --- | --- | --- | --- |
| c5pa | 1 Sp | 2.40 / 16.4 | – | – |
| c5pa | 2 Sa | 1.92 / 13.8 | 1.29 / 11.8 % | – |
| c5delay | 1 Sd | 2.03 / 17.6 | – | 0.0174 / 0.136 |
| c5delay | 2 Sd | 1.62 / 13.6 | – | 0.0040 / 0.081 |

The oracle mask is no better than the automatic one. Cleaned to 0.5σ inside
a fixed mask, c5pa's final image reached `niter` 1,000,000 and four round-2
gains were clipped; C5's G4 apply check then fails on those flagged cells
(it does not leave them out). The long-baseline model error does not move
(> 6 km: 0.34 on c5delay against 0.33 with `m`).

**What development shows:** restricting where CLEAN may put flux, with
CARACal's automatic mask or with the true support, does not remove the gain
errors on the outer antennas. C5's finding still holds: a model imaged from
truly corrected data passes every limit. So the corruption still enters the
model, but through the flux inside the support on the uv cells that only
the outer antennas sample, not through spurious components outside it.
Masks are therefore not the remedy C5 section 7 proposed. Not tested: more
rounds (CARACal's `cal_niter` > 2), longer first solution intervals, or a
deeper phase-only first round.

## 6. Held out (measured)

Run directory `D:\rang\outputs\c5b-20261109-03` (`.code/` holds `50b5690`).
The MSs of `c5pa-held2` and `c5delay-held2` were first generated there,
after the freeze commit; each case ran once with `u` and `m`.

| Case | Arm | Round | Phase | Amplitude | Delay | T2 rows failed |
| --- | --- | --- | --- | --- | --- | --- |
| c5pa-held2 | u | 1 Sp | 2.48 / 14.9 | – | – | phase |
| c5pa-held2 | u | 2 Sa | 1.47 / 10.5 | 1.54 / 4.15 (0.24×) | – | phase, amplitude |
| c5pa-held2 | **m** | 1 Sp | 2.47 / 14.1 | – | – | phase |
| c5pa-held2 | **m** | 2 Sa | 1.49 / 10.0 | 1.93 / 4.22 (0.30×) | – | phase, amplitude, ratio |
| c5delay-held2 | u | 1 Sd | 4.18 / 17.7 | – | 0.0184 / 0.144 | delay p95, phase |
| c5delay-held2 | u | 2 Sd | 2.85 / 13.5 | – | 0.0050 / 0.077 | delay p95, phase |
| c5delay-held2 | **m** | 1 Sd | 3.92 / 16.8 | – | 0.0123 / 0.128 | delay p95, phase |
| c5delay-held2 | **m** | 2 Sd | 2.73 / 12.7 | – | 0.0038 / 0.067 | delay p95, phase |
| c5pa-held | u | 1 Sp | 2.26 / 14.9 | – | – | phase |
| c5pa-held | u | 2 Sa | 1.88 / 12.9 | 1.45 / 2.84 (0.24×) | – | phase, amplitude median |
| c5pa-held | **m** | 1 Sp | 2.15 / 14.5 | – | – | phase |
| c5pa-held | **m** | 2 Sa | 1.79 / 12.7 | 1.72 / 3.26 (0.28×) | – | phase, amplitude, ratio |
| c5delay-held | u | 1 Sd | 1.95 / 15.7 | – | 0.0178 / 0.130 | delay p95, phase |
| c5delay-held | u | 2 Sd | 1.05 / 10.0 | – | 0.0074 / 0.070 | delay p95, phase |
| c5delay-held | **m** | 1 Sd | 1.64 / 14.7 | – | 0.0115 / 0.120 | delay p95, phase |
| c5delay-held | **m** | 2 Sd | 0.97 / 9.3 | – | 0.0057 / 0.064 | delay p95, phase |

On C5's held-out pair `u` again reproduces C5's WSL values (2.26 / 14.9,
1.88 / 12.9, 1.95 / 15.7, 1.05 / 9.96°). Every image stopped on its
threshold (`m`: 7-12 k components in image 1, 37-102 k after); the G4 apply
check passes on all eight runs. The archive of every run is
`research/results/c5b-selfcal-masks.json`.

## 7. Verdicts against the frozen gate

| Gate | c5pa-held2, c5delay-held2 (new) | c5pa-held, c5delay-held (C5's) | Development |
| --- | --- | --- | --- |
| T2 with arm `m` | **not met**: phase p95 10-17° against 1.5-3°; delay p95 0.067-0.128 ns against 0.03-0.06; Sa amplitude 1.9 / 4.2 % against 1 / 3 % | **not met** (the same rows) | not met |

The rows `m` meets everywhere are the delay medians: round 1 at 0.012-0.013
ns (limit 0.02, which `u` misses on c5delay) and round 2 at
0.004-0.006 ns (limit 0.01). **C5b's gate is not met.** Against the
unmasked loop the masked one lowers phase medians by 0-0.6°, p95s by
0.2-1.4° and delay errors by 10-40 %. It raises the Sa amplitude medians
(1.5-1.9 % against 1.0-1.5 %).

**E1's `niter`.** With CARACal's settings no self-calibration image of these
sets reached `niter` (largest: 102 k of 1,000,000). E1's images stopped at
100,000 on a 64-antenna, 256-channel set with a 3σ threshold;
`image.niter: 1000000` (CARACal's) lifts that cap. The effect on E1's Q/I of
−0.4 to −1.1 % was not measured (E1 not rerun).

No novelty claim: a port of CARACal's per-image settings.

## 8. Owner decisions (open)

1. **C5's model-absorption limit stands.** Masks, CARACal's or an oracle,
   do not meet T2. Proposed: accept selfcal as a working port with the limit
   stated (C5 decision 1). If the truth gate matters, a follow-up should test
   more rounds, longer first intervals or a phase-only first round against
   T2, not more masking.
2. **Defaults.** The new keys default to empty (C5's images). Proposed: keep
   them empty, so the image section governs, and put CARACal's values
   (`[wsclean]`, `[10, 6]`, `[0.5]`, `image.mgain` 0.9, `niter` 1,000,000)
   in E2-A's configuration.
3. **Multiscale.** CARACal's default selfcal image is Högbom; this task gated
   multiscale (G4 decision 4). `mh` (Högbom) was within 0.1-2° of `m` on
   development and had a better amplitude median (0.84 %).
4. **FITS masks** are used at the image's size without CARACal's regridding
   (`mProject`); SoFiA, Breizorro and local-rms masks are refused.
5. The selfcal stage hash changes once for existing runs (`--force`).

## 9. Not checked

- More than 2 rounds, other solution intervals, FITS masks on a real field
  (only the oracle mask on simulated data), several fields.
- QuartiCal agreement (C5's G2): the solve code is unchanged and was not
  rerun.
- E1 and real data: not rerun.
- `cleanmask_localrms`: refused (gemclean has no `-local-rms`).
- Timing claims: none (shared host).

## For the coordinator

Proposed `research/README.md` row:

> C5b, 2026-11-09 (implemented and measured; [c5b-selfcal-masks.md](c5b-selfcal-masks.md)). `rang-core selfcal` takes CARACal's per-image `clean_cutoff`, `cleanmask_method` (wsclean, none, a FITS mask) and `cleanmask_thr` (images 1 to rounds + 1, the last repeating). On C5's truths CARACal's masks (10σ then 6σ, cut-off 0.5σ, multiscale) do not meet C5's T2 gate on any case, held-out pairs included: phase p95 9-17° against 1.5-3°. They shift the unmasked loop's medians by at most 0.6°, and an oracle mask from the true sky does no better. The model error on > 6 km baselines (0.13-0.34 rms) does not change. No novelty claim.

Proposed finish-plan C5b row: "Done 2026-11-09 ([c5b-selfcal-masks.md](c5b-selfcal-masks.md)): per-image masks and cut-offs implemented; T2 not met on the held-out cases (masks, an oracle mask included, do not remove C5's model absorption); owner decides on a rounds or intervals follow-up."

Proposed section 7 item: "**C5b's decisions** ([c5b-selfcal-masks.md](c5b-selfcal-masks.md) section 8, open): accept C5's model-absorption limit (masks do not lift it) or a follow-up on rounds and intervals; the new keys default to empty, CARACal's values in E2-A; multiscale gated, Högbom (CARACal's default) reported; FITS masks without regridding; the stage hash changes once."

STATE.md: C5b as above. Seeds 20261501-04 (`c5pa-held2`) and 20261511-14 (`c5delay-held2`) are registered in `rang.simtruth.SEEDS`. Archive: `research/results/c5b-selfcal-masks.json`.
