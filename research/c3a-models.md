# C3a: calibrator models into MODEL_DATA (CASA `setjy` equivalent)

Task C3a of [finish-plan.md](finish-plan.md) (C3), which is step 1 of
[c1-calibration-chain.md](c1-calibration-chain.md), section 6. Branch
`fp-c3a-models` from main `d099bb3`.

**Status: implemented and measured. Every frozen comparison passes as
written** (run `/mnt/d/rang/c3a/c3a-20261106-02`). Point and `manual` models
equal CASA `setjy` at 0 float32 ulps on the real parts. The `.lsm` prediction
equals Crystalball 0.4.3 bit for bit on both MSs. A1's calibrator sky is
reproduced bit for bit. The design and tolerances were committed in `601f893`
before any comparison. Archive: [results/c3a-models.json](results/c3a-models.json).
No novelty is claimed: this reproduces `setjy` and Crystalball.

## Scope (from C1)

- **T0** (C1 1.3): point-source standards from `rang.fluxstd` (Stokes I with
  the standard's spectral shape; Q = U = V = 0) and `manual` (flux density,
  reference frequency, `spix` in CASA's log10 convention, so curvature and
  higher terms are included), written to MODEL_DATA through
  `rang.core_writeback`.
- **The local sky model** of 1934−638 that CARACal's MeerKAT configs use
  (`meerkat_skymodel: true`, `pks1934-638.lsm`), predicted through
  `core.predict_components`.
- **T7** (polarised `manual`) is C1 step 8 (C6a, C7a), not this step. Only the
  groundwork is here: the row writer takes per-channel I, Q, U, V and maps them
  to correlations with C1's convention. `polindex`, `polangle` and `rotmeas`
  are refused with a message naming C7a.

## Design (proposed in 601f893; implemented as written)

New module `python/rang/calmodels.py`, Python only. No new Rust kernel: the
spectra are evaluated by `rang.fluxstd` (the canonical port FS1 measured at
0 ulps against `setjy`; its Rust twin `fluxstd.rs` differs by up to 1.6e-14
relative, which could flip a float32 rounding, so it is not used here), and
the `.lsm` route calls the existing Rust kernel `predict_components`. The
point-model writer is a broadcast of one spectrum per spectral window over the
selected rows, which is not a computational kernel.

Model specifications (frozen dataclasses), and `spec_from_config(dict)` for W2:

| Spec | Config form | Writes |
| --- | --- | --- |
| `Standard(source=None, standard="Stevens-Reynolds 2016", extrapolate=False)` | `{standard: SR2016, source: J1939-6342}` (`source` defaults to the field name) | `fluxstd.flux` per channel, a point at the field's phase centre |
| `Manual(fluxdensity, reffreq, spix=())` | `{standard: manual, fluxdensity: 14.9, reffreq: 1.4GHz, spix: [...]}` | `fluxstd.manual`; `polindex`, `polangle`, `rotmeas` refused (C7a) |
| `PointStokes(stokes)` | not from config | per-channel (I, Q, U, V) from a callable `freq_hz -> (nchan, 4)`; T7 groundwork |
| `SkyModel(path)` | `{skymodel: path}` | `formats.sky.load_any` (Tigger `.lsm`, `.lsm.html`, WSClean list), then `predict_components` with the row's field phase centre and UVW; Stokes I only, a polarised component is refused |

Entry point for W2's `calibrate`:

```python
receipt = calmodels.set_model(ms, field, spec, spw=None, column="MODEL_DATA",
                              session=None, chunk_rows=None)
```

- `field`: a name, an index, or a list of either; `spw` the same for spectral
  windows (default all). Unknown names are refused.
- Rows of other fields and windows are left as they are. If the column does not
  exist it is added by `WriteBack.ensure_column` (CASA's `clearcal` layout, 1 on
  the parallel hands, 0 on the cross hands); whether `setjy` initialises the
  other rows the same way is measured below (O2).
- Correlations from Stokes, sky frame (C1 1.1): `XX = I+Q`, `XY = U+iV`,
  `YX = U−iV`, `YY = I−Q`; circular `RR = I+V`, `RL = Q+iU`, `LR = Q−iU`,
  `LL = I−V`. Computed in float64, cast once to complex64.
- Frequencies are each window's `CHAN_FREQ` as stored (FS1: CASA evaluates at
  `CHAN_FREQ` with no frame conversion). Only `scalebychan=True` is
  implemented; there is no `scalebychan=False` mode.
- Subtables (FIELD, SPECTRAL_WINDOW, DATA_DESCRIPTION, POLARIZATION) are read
  before the write session; FIELD_ID, DATA_DESC_ID and UVW are read through the
  session (W1: another reader in the same process drops the lock). Chunks with
  no selected rows are not rewritten.
- `session` lets a caller (W2) pass an open `WriteBack`, so several fields go
  into one session and one flag backup.
- The receipt records the spec, per field the rows written and the model's
  Stokes I at the first, middle and last channel of each window, the column,
  and whether it was added.

## Data and provenance

Every MS is a copy under `/mnt/d/rang/c3a/<run>/`; the inputs are read, hashed
and never opened for writing.

| Name | Source | Layout |
| --- | --- | --- |
| S, the slice | `~/Github/rang/outputs/o-casa-20261030-01/work.ms` (O-CASA's rebuild of the LUNO four-station 1934−638 slice, before its `setjy`) | 192 rows × 2048 ch × 4 corr; one field in use (`J1939-6342`, FIELD_ID 1, of three FIELD rows); MODEL_DATA present (the stored model) |
| A, A1 small | `/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms` and `truth.npz` (A1, seeds in `a1-simtruth.md`) | 12,480 rows × 64 ch × 4 corr; fields `J1939-6342`, `3C286-SIM`, `SIM-GCAL`, `SIM-TARGET`; no MODEL_DATA |
| L, the lsm | CARACal `8f7bb363` `caracal/data/meerkat_files/pks1934-638.lsm`, SHA-256 `0964b9f4c547bb802bfb16a2e8fdccddff84beeec05b6f3492521a46fa77d101` (the copy in `outputs/c1-sources-20261105/caracal-8f7bb363/`) | 196 components (points and Gaussians, up to `spi4`). GPL-2.0, so it is not committed; tests use synthetic models |

Oracle images: `rang-o-casa:6.7.6.14` (`sha256:24822b40…`, casatasks
6.7.6.14) and `rang-formats-oracle:20261030` (`sha256:6ddf0359…`, `/opt/sky`:
Crystalball 0.4.3, astro-tigger-lsm 1.8.0), under O-CASA's container rules
(`--network none`, this user, `--tmpfs /tmp`, `HOME=/tmp`, inputs read-only).

**CARACal's own `.lsm` route is not Crystalball.** With `meerkat_skymodel:
true` its `set_model` uses `cab/simulator` (MeqTrees, `mode: simulate`,
`column: MODEL_DATA`, `field-id`, `tile-size`, `threads`;
`crosscal_worker.py` lines 655–705 at `8f7bb363`). No MeqTrees image exists
here. Crystalball is C1's oracle for the predictor; agreement with it says
nothing about MeqTrees' Gaussian and spectral-index semantics, so it is not
parity with CARACal's lsm path.

## Oracles and tolerances (frozen before the first comparison)

**The 0-ulp bound, confirmed.** C1 asks for 0 ulps from `setjy` "as FS1".
What FS1 measured (`fs1-flux-standards.md`, criterion 2 and run `-06`): the
real part of CASA's MODEL_DATA parallel hands equals the port's Stokes I cast
to float32 at 0 ulps, on 1001 channels of a synthetic MS and on all
2048 channels × 192 rows of O-CASA's slice; XX = YY; Q = U = V = 0. Its run
`-05` compared the complex rows and did *not* find them identical, because
CASA's rows on the slice's geometry carry imaginary parts up to 1.8e-12 Jy.
So the bound is on the real parts. The bound used here, in three parts:

1. real parts of XX and YY: **0 float32 ulps** on every cell of the selected
   rows;
2. cross hands: rang writes exactly 0; CASA's XY and YX must have
   |·| ≤ 1e-9 × I of the cell (reported);
3. imaginary parts of XX and YY: rang writes exactly 0; CASA's must be
   ≤ 1e-9 × I (FS1: 1.8e-12 Jy at 15 Jy, 1.2e-13 relative); the maximum is
   reported.

| # | Comparison | Data | Rang | Oracle | Pass when |
| --- | --- | --- | --- | --- | --- |
| O1a | point standard | S | `Standard("J1939-6342", "SR2016")` on field `J1939-6342` | `setjy(field='J1939-6342', standard='Stevens-Reynolds 2016', scalebychan=True, usescratch=True)` on another copy | parts 1–3 on the 192 field rows; every other column and row unchanged in rang's copy |
| O1b | CARACal's manual model | S | `Manual(**fluxstd.CARACAL_1934)` | `setjy(standard='manual', fluxdensity=14.907688923, reffreq='1.400000GHz', spix=[-0.19473727, -1.3843252, 0.60533435, 1.43e-06], scalebychan=True, usescratch=True)`, CARACal's call (`o-casa.md`) | parts 1–3 |
| O2 | field selection and a new column | A | three calls on one copy: SR2016 on `J1939-6342`; `Manual` with A1's `SIM-GCAL` values; `Manual` with A1's `3C286-SIM` Stokes I (no polarisation) | the same three `setjy` calls on another copy, in the same order | parts 1–3 on the three fields' rows; **target rows bit-identical to CASA's** (whatever CASA initialises them to); if they differ, the comparison fails as written |
| O3a | the lsm through `predict_components` | S | `SkyModel` of the converted WSClean list (L → `sky.load` → `sky.dumps_wsclean`, zero-padded spectra) on field `J1939-6342` | Crystalball 0.4.3 `-sm <list> -o MODEL_DATA -f J1939-6342 -j 1` on another copy | per cell and correlation, \|V_rang − V_cb\| ≤ 1e-6 × peak, where **peak = max \|V_cb\| over the compared rows, channels and all four correlations**; XY and YX exactly 0 in both |
| O3b | the same, longer baselines | A, field `J1939-6342` | as O3a | as O3a | as O3a |
| O3c | lsm read against list read (reported, not gated) | S | `SkyModel(L)` against `SkyModel(list)` | – | max \|Δ\| / peak reported (the list carries positions to 1e-12 rad) |
| O4 | A1's known calibrator sky | A, rang's O2 copy | – | `truth.npz` `calibrator_stokes`, mapped to correlations in float64 and cast to complex64 | `J1939-6342` and `SIM-GCAL`: every cell bit-identical. `3C286-SIM`: Re XX = Re YY = float32(truth I) exactly, imaginary and cross hands 0 (Q and U deferred to C1 step 8). `SIM-TARGET` rows: as initialised |
| O4p | T7 groundwork: Stokes rows | A, a fresh copy | `PointStokes` of the truth's (I, Q, U, V) of `3C286-SIM` | the same mapping of `truth.npz` in float64, cast to complex64 | every cell bit-identical |

O4 and O4p are partly circular: A1 computes its calibrator Stokes with
`fluxstd.flux` and `fluxstd.manual` and states the same correlation convention.
They check field selection, row mapping, the column writer and the convention
of the writer against A1's file, not the flux standards (O1 and O2 do that).

Also recorded, not gated: what Crystalball writes into rows of other fields
when it creates MODEL_DATA (O3b), and wall times of each call.

## Tests

`tests/test_calmodels.py`, on MSs written by `core_ms_write.default_ms` in a
pytest temporary directory and synthetic models: point and manual values equal
`fluxstd` cast to complex64; other fields untouched; a new column initialised
as `ensure_column`; a polarised `Manual` and a polarised `SkyModel` refused;
`PointStokes` mapping for linear and circular feeds; the `.lsm` route equals a
direct `predict_components` call; `spec_from_config` forms and refusals.

The tests are as proposed, seven of them; they pass.

## Measured (2026-11-06, after the freeze)

Run `/mnt/d/rang/c3a/c3a-20261106-02` (580 MB, ignored), made by
`examples/c3a_models.py run <run>` at code SHA-256 `a8b49708…` (`calmodels.py`)
and `745c6fbb…` (`c3a_models.py`), the files of this commit. Inputs were hashed
before and after; they were unchanged. `truth.npz` SHA-256 `49580d7d…`. No seeds
are involved: every model is deterministic, and A1's seeds are in its own note.

| # | Result | Numbers | Pass |
| --- | --- | --- | --- |
| O1a SR2016, slice | real XX, YY 0 ulps on 192 rows × 2048 ch; rang XX = YY, imaginary and cross hands 0; CASA imaginary max 1.76e-12 Jy (1.2e-13 of I), CASA cross hands 0; other MS columns unchanged | I 14.673–15.138 Jy; `setjy` fluxd 15.0077077 Jy | **yes** |
| O1b CARACal manual, slice | as O1a | CASA imaginary 1.76e-12 Jy; fluxd 15.0077068 Jy | **yes** |
| O2 A1 small, three `setjy` calls | real 0 ulps on J1939−6342 (1,440 rows), SIM-GCAL (2,400), 3C286-SIM Stokes I (1,920); CASA's cells are bit-identical to rang's here (imaginary 0 on this geometry); SIM-TARGET's 6,720 rows bit-identical to CASA's, which initialises them as `clearcal` does (1 on XX and YY, 0 on XY and YX), the same as `ensure_column` | 64 ch × 4 corr per row | **yes** |
| O3a lsm list, slice | rang against Crystalball 0.4.3: max \|Δ\| **0** over 192 rows × 2048 ch × 4 corr; all cells bit-identical; cross hands 0 in both | peak 15.213 Jy | **yes** |
| O3b lsm list, A1 small | as O3a, 1,440 rows × 64 ch: max \|Δ\| 0, all bit-identical | peak 15.281 Jy. Crystalball created MODEL_DATA with **0** in the other 11,040 rows, where CASA and rang put 1 on the parallel hands (reported, not gated) | **yes** |
| O3c lsm read against list read | reported only | max \|Δ\| 2.98e-8 Jy, 1.96e-9 of the peak; 99.987 % of cells bit-identical (the list carries positions to 1e-12 rad) | – |
| O4 A1 truth | J1939−6342 and SIM-GCAL bit-identical to `stokes_coherency(calibrator_stokes)` in complex64; 3C286-SIM Stokes I equal and Q, U absent as planned (the truth's \|Q\|/I reaches 0.039); SIM-TARGET as initialised | – | **yes** |
| O4p Stokes rows (T7 groundwork) | 3C286-SIM's full (I, Q, U, V) truth through `PointStokes`: bit-identical to A1's `stokes_coherency` in complex64; other rows unity | 1,920 rows | **yes** |

**Reading.**

- The FS1 bound holds on the real parts. On the slice's geometry CASA writes
  imaginary parts of about 1.8e-12 Jy, as FS1 run `-05` found, and rang writes 0.
  On A1's geometry CASA writes 0 too. The difference is 1.2e-13 of I, far below
  any calibration effect. It comes from CASA's own phase evaluation, not from the
  model.
- rang's `.lsm` route is bit-identical to Crystalball on these two MSs. DF-IO
  measured 99.95 % bit-identical cells on `c.ms`. The difference may lie in the
  MS (`work.ms` against O-CASA's arm-C copy); I did not investigate it, because
  both meet the bound.
- One behaviour differs between the oracles and is not a C3a criterion: when
  Crystalball creates MODEL_DATA, other fields' rows are 0, while `setjy` and rang
  put 1 on the parallel hands. Rang follows CASA.

**Deviations.**

- Run `-01` (`/mnt/d/rang/c3a/c3a-20261106-01`, kept) stopped after its writes
  and before any comparison. The receipt called the `PointStokes` function again
  on three channels, and the checker's function accepted only the full band. The
  receipt now reuses the spectra computed for the write, and `-02` reran
  everything from fresh copies. No verdict came from `-01`.
- `ruff` 0.17.4, which uv installed, flags `tests/test_p11_extract.py` (SIM102).
  The worktree venv was pinned to main's 0.17.3. This is unrelated to C3a.

## Timings

Wall times inside the run (host RSS of the driver 293 MB; `/usr/bin/time` of the whole run 109.7 s):

| Step | Wall |
| --- | --- |
| CASA `setjy`, 5 calls in one container (each call 1.3–3.3 s) | 12.2 s |
| Crystalball 0.4.3, slice / A1 small (`-j 1`) | 15.7 s / 9.0 s |
| rang point and manual, slice (192 × 2048) | 0.80 s each |
| rang SR2016, A1 small, first call (adds MODEL_DATA, flag backup, 12,480 × 64 on `/mnt/d`) | 10.1 s |
| rang manual, A1 small, later calls | 0.6 s each |
| rang lsm, slice (196 components) / A1 small (with column creation) | 1.5 s / 9.9 s |

The A1 calls that add the column are dominated by initialising and backing up
over `/mnt/d` (a 9P mount), not by the model.

## API for W2

`calmodels.set_model(ms, field, spec, *, spw=None, column="MODEL_DATA",
session=None, chunk_rows=None) -> receipt`. `spec` is a `Standard`, a
`Manual`, a `PointStokes`, a `SkyModel`, or a config mapping as described in
`spec_from_config`. W2's `calibrate` can open one `core_writeback.WriteBack`
(stage `calibrate`) and pass it as `session` for every model call, so there is
one flag backup and one journal. The receipt is JSON-ready, for W2's run receipt.

## What was not checked

- **CARACal's own lsm route (MeqTrees `cab/simulator`)**: no image exists. Agreement
  with Crystalball does not show that MeqTrees reads Tigger's `spi2`–`spi4`, its
  Gaussian extents or the position angle the same way. E3's two-arm comparison
  (A0) depends on this.
- `setjy` with `scalebychan=False`, other fields' `REFERENCE_DIR` or `DELAY_DIR`
  differing from `PHASE_DIR`, several spectral windows in one MS (W1 refuses
  differing cell shapes), circular feeds against CASA (unit-tested only), and
  PB2017 sources other than FS2's four.
- The full A1 MS and LUNO's 56-antenna data: the cost per row of the lsm route at
  scale was not measured. `predict_components` on 2.8 M rows × 256 ch × 196
  components needs heavy-lock time. No timing work was done, as the brief says.
- Polarised models (T7 proper): C1 step 8.

## For the coordinator

**`research/STATE.md`, new top entry:**

> C3a, 2026-11-06 (implemented and measured). [c3a-models.md](c3a-models.md):
> `rang.calmodels.set_model` writes calibrator models to MODEL_DATA through W1's
> write-back. It takes flux standards, `manual`, per-channel Stokes rows and
> component lists such as CARACal's `pks1934-638.lsm`. Against CASA `setjy` on
> O-CASA's slice and on A1 small, the real parts differ by 0 float32 ulps.
> CASA's imaginary parts are at most 1.8e-12 Jy, and other fields' rows are
> bit-identical to CASA's. The lsm route through `predict_components` is
> bit-identical to Crystalball 0.4.3. A1's calibrator sky is reproduced bit for
> bit. CARACal's own lsm route is MeqTrees, which has no oracle here. Polarised
> `manual` is refused until C7a.

**`research/README.md`, index line:**

> [C3a, calibrator models](c3a-models.md): `setjy`-equivalent point, manual and
> `.lsm` models into MODEL_DATA; 0 ulps against `setjy`, bit-identical to
> Crystalball.

**`research/finish-plan.md`:** C3 row, C3a done (step 1 of C1); T7's polarised
model stays with C7a (C1 step 8).

**For A0 / E3:** CARACal's `meerkat_skymodel: true` predicts the lsm with MeqTrees
(`cab/simulator`), not Crystalball. Rang's second E3 arm ("the same lsm through
`predict_components`") matches Crystalball exactly. Whether MeqTrees agrees is
open. A MeqTrees image would be needed to separate "model" from "predictor" in
that arm.

**Not removed:** `/mnt/d/rang/c3a/` (run `-01`, run `-02`, check-all logs, about
1.2 GB) can be deleted after merge. `~/Github/rang/outputs/status/fp-c3a.md`
can go after merge.
