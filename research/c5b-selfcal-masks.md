# C5b: per-image clean masks and cut-offs in self-calibration

Task C5b of [finish-plan.md](finish-plan.md), on branch `fp-c5b-masks` from
main `eaf40b7` (G4 merged), 2026-11-09. Native Windows.

**Status: protocol frozen (sections 1-4); results follow in later sections.**

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

## For the coordinator

(at the end)
