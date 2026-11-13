# C7a: polarised calibrator models (CASA `setjy` manual with polindex, polangle, rotmeas)

Task C7a of [finish-plan.md](finish-plan.md) (row C7, "polarised calibrator
models"), the model half of step 8 of
[c1-calibration-chain.md](c1-calibration-chain.md) (term T7). Branch
`fp-c7a-polmodels` from main `a05119a`. It extends C3a's
`rang.calmodels.set_model` ([c3a-models.md](c3a-models.md)).

**Status: implemented and measured. Frozen run `-03`: M1–M6, P1, P2 and T1
pass; M7 and M8 fail as written. Post-hoc fix (run `-04`): M7 and M8 pass G1
(1.5e-7 and 1.3e-7 of I) and still fail G2 (2 ulps). Held-out H1 (`-05`):
its tabular half is bit-identical to CASA's; its SpectralIndex half passes G1
(1.3e-7) and fails G2 (2 ulps), so H1 fails as written.**
The design, cases and tolerances were frozen in `9893fbe` before any
comparison. On CASA's tabular path (CARACal's 3C286 and 3C138, polynomial
`polindex`/`polangle`, RM, `fluxdensity` Q, U, V) rang equals CASA 6.7.6.14
`setjy` at **0 float32 ulps** on the real parts of all four correlations, on
both MSs. MODEL_DATA is the sky-frame coherency, independent of the
parallactic angle and of RECEPTOR_ANGLE (P1, P2 pass). On CASA's
`SpectralIndex` path (one `spix` term; M7, CARACal's Taylor & Legodi form,
and M8) CASA's model is rang's times a constant 1 − 5.7e-6 and 1 − 1.6e-5:
G1 and G2 fail in `-03`. Section 8 has the diagnosis, section 9 the
post-hoc fix and the held-out case. Archive:
[results/c7a-polmodels.json](results/c7a-polmodels.json). No novelty is
claimed: this reproduces `setjy`.

## 1. Scope

- `calmodels.Manual` takes CASA's full `setjy(standard='manual')` polarised
  form: `fluxdensity=[I, Q, U, V]`, `spix`, `reffreq`, `polindex`,
  `polangle`, `rotmeas`, and writes MODEL_DATA in all four linear
  correlations (circular feeds keep C3a's mapping; they are not tested here).
- CARACal's two shipped polarisation-calibrator models (`nrao_xcal.yml`, 3C286
  and 3C138, with CARACal's aliases J1331+3030 and J0521+1638) as constants,
  like `fluxstd.CARACAL_1934`.
- `rang-core calibrate`: `calibrate.model.source: manual` accepts Q, U, V,
  `polindex`, `polangle` and `rotmeas`; the C7a refusals go for what is
  implemented here.
- Not in scope: polarised components in `.lsm` sky models (stays refused,
  naming C7a); the parallactic-angle term P (C6a); applying anything.

## 2. What CASA does (read from source)

Sources, all copied under `~/Github/rang/outputs/c7a-sources-20261106/`
(ignored; `SHA256SUMS` in each folder):

- `casa6-9269a52/`: the GitHub mirror `dic-case-studies/casa6` at
  `9269a52` (2023-01-18), the same mirror C1 read. This is **not** the
  6.7.6.14 source. The Python task `task_setjy.py` of the oracle image
  (`casa-6.7.6.14/task_setjy.py`, SHA-256 `78bad2d1…`) differs from the
  mirror's only in Python 2 shims and two new spectral-index range checks
  (`|spix[0]| > 10` refused); the `polindex`, `polangle`, `rotmeas` arguments
  are passed to `imager.setjy` unchanged. The C++ below is the mirror's; the
  oracle run decides whether 6.7.6.14 behaves the same.
- `casacore-v3.7.1/`: `Polynomial.tcc` (`eval` is Horner from the highest
  coefficient), `PolynomialParam.tcc`.
- `caracal-8f7bb363/`: `taylor_legodi_2024.txt`, `dispatch_crew/utils.py`,
  `meerkat-polcal-strategies.yml`; the polcal worker and `nrao_xcal.yml` are
  in C1's copy (`c1-sources-20261105/caracal-8f7bb363/`).

`Imager::sjy_setmanualflux` (`Imager.cc` lines 5405–5605) and
`Imager::sjy_calcquflux` (lines 6024–6071):

1. **I.** If `spix` has more than one term, or `polindex` or `polangle` has
   more than one, the model is a `TabularSpectrum` of per-channel values
   ("tabular"). I is `sjy_calciflux`, which FS1 and C3a matched at 0 ulps
   with `fluxstd.manual`. Otherwise it is a `SpectralIndex` model.
2. **Linear polarisation.** `x = (f − f0)/f0` with `f0` = `reffreq`;
   `p = polindex(x)`, `χ = polangle(x)`, ordinary polynomials (casacore
   `Polynomial`, Horner), not log10 as `spix`. `Q = (p·I)·cos(2χ)`,
   `U = (p·I)·sin(2χ)`.
3. **Rotation measure**, referenced to `reffreq`, not to λ = 0:
   `rot = 2·RM·c·c·(f0² − f²)/(f²·f0²)` (= 2·RM·(λ² − λ0²)), then
   `Q' = Q cos rot − U sin rot`, `U' = Q sin rot + U cos rot`; skipped when
   RM = 0.
4. **`fluxdensity` Q, U.** If Q or U is nonzero, `p0 = sqrt(Q² + U²)/I` and
   `χ0 = atan2(U, Q)/2` replace the zeroth coefficients of `polindex` and
   `polangle` (or become them when either is empty; then the other terms are
   dropped).
5. **V.** `V = I(f) · V/I` with V and I from `fluxdensity` (a constant
   circular fraction).
6. **`polindex` without `polangle`** (or the reverse), with Q = U = 0:
   CASA writes no linear polarisation and says nothing.
7. **The `SpectralIndex` path when polarised** (one `spix` term, at most one
   `polindex` and `polangle` term, and any of Q, U, V nonzero): the component
   takes the (I, Q, U, V) of **channel 0** of the window, the reference
   frequency becomes channel 0's, and `SpectralIndex::sampleStokes`
   (`SpectralIndex.cc` 213–258, stokes index `[spix, 0, RM, 0]`) scales I, Q,
   U, V by `(ν/ν0)^spix` and rotates Q, U by RM relative to channel 0. This is
   the same model as items 2–5 in exact arithmetic; the bits differ. CARACal's
   Taylor & Legodi option takes this path (one `spix`, one `polindex`).
8. **Correlations.** `SimpleComponentFTMachine::get` (`TransformMachines2`,
   lines 255–274, 352–393) converts the component's Stokes to linear with
   `Flux::stokesToLinear` (`Flux.tcc` 984–1008): `XX = I+Q`, `XY = U+iV`,
   `YX = U−iV`, `YY = I−Q`, in double, cast to `Complex`, then multiplied in
   float by the conjugate phasor of the phase-centre shift. Linear or circular
   is `vb.polarizationFrame()` (the FEED table's `POLARIZATION_TYPE`).

**No parallactic angle in `setjy`.** Nothing on that path reads a feed angle.
P enters only as a calibration term: `PJones::syncMeta2` takes
`vb.feedPa(time)` and `calcOneJones` forms
`[[cos a, sin a], [−sin a, cos a]]` (`StandardVisCal.cc` 126–201), applied
by `gaincal`/`polcal`/`applycal` with `parang=True`. So MODEL_DATA holds the
**sky-frame** coherency, the same at every parallactic angle, and so does
rang's. Measured below (P1, P2).

## 3. Conventions rang states

- **MODEL_DATA convention** (C1 1.1, unchanged from C3a): sky frame,
  `XX = I+Q`, `XY = U+iV`, `YX = U−iV`, `YY = I−Q`, CASA's
  `Flux::stokesToLinear`; χ = atan2(U, Q)/2 counted as in the IAU and NRAO
  tables (3C286 χ = 33° gives U > 0, Re XY > 0).
- **MeerKAT's feeds.** The difference between MeerKAT's receptors and CASA's
  X, Y is carried by P through RECEPTOR_ANGLE, not by the model: CARACal's
  polcal worker overwrites RECEPTOR_ANGLE with −90° on both receptors
  (`feed_angle_rotation: -90`, `polcal_worker.py` 1487–1505; schema text:
  "to agree with the convention assumed in the CASA software"). A1's MS
  already holds −π/2 on both (a1-simtruth.md). So rang's MODEL_DATA is
  feed-independent, as CASA's. Whether −90° is the right sign for MeerKAT is
  decided by the calibrated 3C286 angle in C7b (C1 step 11), not here.
- **Parallactic-angle convention.** C7a writes sky-frame models and needs no
  parallactic angle, so finish-plan 7.8 (rang's geodetic/ICRS angle against
  CASA's geocentric/apparent one, up to 0.54°, A1) does not affect it.
  C6 (P with `parang=True`) and C7b (apply) do. `rang.simtruth` is not
  changed.
- **`rang.simtruth`'s RM** is `χ0 + RM·λ²` (λ = 0 reference), CASA's is
  `χ0 + RM·(λ² − λ0²)` (reference `reffreq`). Harmless at A1's RM = 0; a
  future truth with RM ≠ 0 must use CASA's reference or say which it uses.
  Recorded, not changed.

## 4. Design

`calmodels.Manual(fluxdensity, reffreq_hz, spix=(), q=0, u=0, v=0,
polindex=(), polangle=(), rotmeas=0)`; `fluxdensity` may also be
`[I, Q, U, V]` through `spec_from_config`. `Manual.stokes(freq_hz)` follows
section 2 item by item:

- unpolarised: exactly C3a's path (`fluxstd.manual`), so C3a's results hold;
- tabular: I from `fluxstd.manual`, Q and U per channel in CASA's operation
  order (Horner, `(p·I)·cos(2χ)`, the RM expression left to right) with
  `math` (libm) scalars, not vectorised numpy, so a 1-ulp double difference
  cannot flip a float32 rounding;
- `SpectralIndex` path: the channel-0 values from the tabular formulas, then
  `SpectralIndex::sampleStokes`'s per-channel scaling and rotation, also in
  libm scalars.
- **Refused** (owner decision, provisional): `polindex` without `polangle` or
  the reverse when Q = U = 0 (CASA silently writes none; rang refuses rather
  than drop what the user asked for). A negative or zero I is refused as in
  C3a.
- Constants `calmodels.NRAO_XCAL` (3C286, 3C138 of CARACal's `nrao_xcal.yml`,
  aliases J1331+3030, J0521+1638 as `polcal_worker.py` 1424–1427) and
  `calmodels.caracal_xcal(name)` returning the `Manual`.
- `set_model`'s chunk loop is unchanged (it already writes four
  correlations); the receipt records I, Q, U, V at the first, middle and last
  channel and which CASA path the model follows.
- `rang-core calibrate`: `core_pipeline.model_spec` passes `flux_jy` (I, Q,
  U, V), `polindex`, `polangle`, `rotmeas`; `core_config._model_refusals`
  keeps the refusal for a polarised model where it is not implemented and
  adds "only with source: manual" for the polarisation keys. Models stay on
  the primary fields; the secondary and polcal refusal (C2d) stays.

Taylor & Legodi (CARACal `taylor_legodi_model`,
`dispatch_crew/utils.py::read_taylor_legodi_row`): one `spix` (α only, the
table's curvature C dropped), `reffreq 1.4GHz`, `polindex = p1400/100`,
`polangle = PA1400` in rad, `rotmeas = RM`. That is a `Manual` too; case M7
below is built the same way. No rang constant (it is a 12 kB table; owner
decision whether to ship it).

## 5. Data

Every MS is a copy under `/mnt/d/rang/outputs/c7a-<run>/`; inputs are hashed
before and after and never opened for writing.

| Name | Source | Use |
| --- | --- | --- |
| S, the slice | `~/Github/rang/outputs/o-casa-20261030-01/work.ms` (C3a's S) | 192 rows × 2048 ch, field `J1939-6342`. `manual` ignores the field's name, so no relabel. The geometry where CASA writes imaginary parts near 1e-12 Jy (C3a) |
| A, A1 small | `/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms` (C3a's A) | 64 ch over 856–1712 MHz; field `3C286-SIM` (1,920 rows, four scans over 115° of parallactic angle); `SIM-GCAL` |

## 6. Cases and tolerances (frozen before the first comparison)

Each case is one `setjy(..., standard='manual', scalebychan=True,
usescratch=True)` on a CASA copy and the same model through
`calmodels.set_model` on a rang copy.

| # | Data, field | Model | CASA path |
| --- | --- | --- | --- |
| M1 | S, `J1939-6342` | CARACal 3C286: `fluxdensity=[14.7172]`, `spix=[-0.4507, -0.1798, 0.0357]`, `reffreq='1.47GHz'`, `polindex=[0.098]`, `polangle=[0.575959]`, `rotmeas=0.0` (`polcal_worker.py` 150–167) | tabular |
| M2 | S, `J1939-6342` | CARACal 3C138: `[8.33843]`, `[-0.4981, -0.1552, -0.0102, 0.0223]`, `1.47GHz`, `[0.078]`, `[-0.16755]`, `0.0` | tabular |
| M3 | A, `3C286-SIM` | M1 | tabular |
| M4 | A, `3C286-SIM` | M1 with `polindex=[0.098, 0.02, -0.01]`, `polangle=[0.575959, 0.05]`, `rotmeas=50.0` | tabular |
| M5 | S, `J1939-6342` | `fluxdensity=[14.7172, 0.6, 1.2, 0.05]`, 3C286 `spix`, `1.47GHz`, `polindex=[0.098, 0.03]`, `polangle=[0.575959, -0.04]`, `rotmeas=10.0` (Q, U override the zeroth terms; V fraction) | tabular |
| M6 | A, `3C286-SIM` | `fluxdensity=[14.7172, 0.4, 1.3, 0.0]`, 3C286 `spix`, `1.47GHz`, no `polindex`/`polangle`, `rotmeas=-30.0` | tabular |
| M7 | A, `3C286-SIM` | Taylor & Legodi J1331+3030 as CARACal reads it: `fluxdensity=14.673`, `spix=-0.630`, `reffreq='1.4GHz'`, `polindex=0.099`, `polangle=29.2°` in rad, `rotmeas=-0.3` | SpectralIndex |
| M8 | A, `SIM-GCAL` | `fluxdensity=[4.0, 0, 0, 0.04]`, `spix=[-0.6]`, `1.4GHz` (V only) | SpectralIndex |
| H1 | A, `3C286-SIM` | **held out**, run only after M1–M8: 3C138 `fluxdensity=[8.33843, -0.3, 0.5, -0.02]`, 3C138 `spix`, `1.47GHz`, `polindex=[0.078, 0.03]`, `polangle=[-0.16755, -0.02, 0.01]`, `rotmeas=-20.0`; and on `SIM-GCAL` of the same copy `fluxdensity=[4.0, 0.1, -0.05, 0]`, `spix=[-0.6]`, `1.4GHz`, `rotmeas=15.0` (SpectralIndex with Q, U from `fluxdensity`) | both |

**Gates per case** (all cells of the selected rows, all four correlations):

- **G1, C1's step-8 bound:** `|V_rang − V_casa| ≤ 1e-6 · I` per cell
  (complex difference; I the model's Stokes I of that channel).
- **G2, class C as C3a** (bit level): the real parts of XX, XY, YX, YY at
  **0 float32 ulps**; the imaginary parts within `1e-9 · I` (CASA's
  phase-centre phasor, C3a: 1.8e-12 Jy on S; 0 on A).
- **G3, the other rows**: every MODEL_DATA cell outside the selected field
  bit-identical to CASA's copy (C3a: both initialise as `clearcal`).
- A case passes when G1, G2 and G3 pass. If G2 fails and G1 passes, the case
  fails as written and the size of the miss is reported.

**Frame checks** (A):

- **P1:** `setjy` M1 on a copy whose FEED `RECEPTOR_ANGLE` is set to 0 on
  both receptors (written by rang's harness on the copy) equals `setjy` M1 on
  the copy with −π/2 (M3's CASA copy), every MODEL_DATA cell bit-identical.
- **P2:** in M3's and M4's CASA copies, for each channel every `3C286-SIM`
  row is bit-identical (the model does not rotate with parallactic angle).
- FEED `POLARIZATION_TYPE` is `X, Y` on both MSs (reported).

**Class T, published values.** From each model's Stokes, at the published
frequencies inside MeerKAT's L band (856–1712 MHz):
`p = sqrt(Q² + U²)/I`, `χ = atan2(U, Q)/2`.

Published, read twice: Perley & Butler 2013 (ApJS 206, 16; arXiv:1302.6662),
Table 3, December 2010, read from the ar5iv rendering and from NRAO's VLA
polarimetry page (Table 8.2.6), identical; NRAO's 2019 values (Table 8.2.7 of
the same page, one source only), from which `nrao_xcal.yml`'s 1.47 GHz values
come.

| Source | GHz | p % | χ ° | table |
| --- | --- | --- | --- | --- |
| 3C286 | 1.05, 1.45, 1.64 | 8.6, 9.5, 9.9 | 33, 33, 33 | PB2013 |
| 3C286 | 1.02, 1.47 | 8.6, 9.8 | 33, 33 | NRAO 2019 |
| 3C138 | 1.05, 1.45, 1.64 | 5.6, 7.5, 8.4 | −14, −11, −10 | PB2013 |
| 3C138 | 1.02, 1.47 | 5.5, 7.8 | −13, −9.6 | NRAO 2019 |

- **T1 (gated):** at 1.47 GHz, rang's M1 and M2 models give the 2019 values
  within the tables' rounding (|Δp| ≤ 0.05 percentage points, |Δχ| ≤ 0.05°);
  and the same from **CASA's MODEL_DATA** of M1 and M2 (Q = Re(XX − YY)/2,
  U = Re XY, I = Re(XX + YY)/2) at every channel, since these models hold p
  and χ constant over the band. This checks the transcription and the sign
  of χ in both.
- **T2 (reported, prediction frozen):** CARACal's models hold p and χ
  constant over the band, so against PB2013 they are off by what the
  published spectrum changes. Predicted Δ = model − published: 3C286
  Δp +1.2 (1.05 GHz), +0.3 (1.45), −0.1 (1.64), +1.2 (1.02), Δχ 0;
  3C138 Δp +2.2, +0.3, −0.6, +2.3 and Δχ +4.4°, +1.4°, +0.4°, +3.4°. A
  different measured Δ means the model is not constant and is a finding.
  This is the accuracy of CARACal's model, not of rang.
- **T3 (reported):** Taylor & Legodi 2024's MeerKAT values for J1331+3030
  (p 9.90 % and PA 29.2° at 1.4 GHz, RM −0.3) and J0521+1638 (7.71 %,
  −15.1°, RM −2.4) against `nrao_xcal.yml`.

Also reported, not gated: wall time of each call; CASA's maximum imaginary
part per case.

## 7. Tests

`tests/test_calmodels.py` gains: polarised `Manual` against an independent
float64 evaluation of section 2 (tabular and SpectralIndex paths, RM, Q/U
override, V fraction); the refusal of `polindex` without `polangle`;
`NRAO_XCAL` values and aliases; `spec_from_config` with `[I, Q, U, V]` and
the polarisation keys; a polarised `set_model` writing all four
correlations. `tests/test_core_config.py` (or the existing calibrate tests):
`source: manual` with Q, U, V and polarisation keys validates; polarisation
keys with another source are refused.

As implemented: the tests are in `tests/test_calmodels.py` (seven parametrised
models against the independent evaluation, the unpolarised path unchanged,
`NRAO_XCAL`, a four-correlation write; after the post-hoc fix, the channel-0
frame ratio, its receipt and the refusal of other frames) and
`tests/test_w2_commands.py` (the calibrate refusals); they pass.

## 8. Measured (2026-11-06, after the freeze)

Run `/mnt/d/rang/outputs/c7a-20261106-03` (928 MB, ignored), made by
`examples/c7a_polmodels.py run <run>` under `flock ~/.rang-heavy.lock`, code
SHA-256 `d6ca3b79…` (`calmodels.py`), `1d992220…` (`c7a_polmodels.py`),
`745c6fbb…` (`c3a_models.py`). Inputs hashed before and after, unchanged
(S `74f4c010…`, A `141f7ed6…`). No seeds: every model is deterministic.

| # | Path | G1 max \|Δ\|/I | G2 real ulps | G2 imag /I | G3 | Pass |
| --- | --- | --- | --- | --- | --- | --- |
| M1 3C286, S | tabular | 1.2e-13 | 0 | 1.2e-13 (CASA 1.8e-12 Jy) | yes | **yes** |
| M2 3C138, S | tabular | 1.3e-13 | 0 | 1.3e-13 | yes | **yes** |
| M3 3C286, A | tabular | 0 (all cells bit-identical) | 0 | 0 | yes | **yes** |
| M4 polynomials, RM 50, A | tabular | 0 (bit-identical) | 0 | 0 | yes | **yes** |
| M5 I, Q, U, V + override, RM 10, S | tabular | 1.2e-13 | 0 | 1.2e-13 | yes | **yes** |
| M6 I, Q, U, RM −30, A | tabular | 0 (bit-identical) | 0 | 0 | yes | **yes** |
| M7 Taylor & Legodi J1331+3030, A | SpectralIndex | **6.1e-6** | **96** | 0 | yes | **no** |
| M8 V only, SIM-GCAL, A | SpectralIndex | **1.6e-5** | **266** | 1.6e-7 | yes | **no** |

Frame checks: **P1 passes** (RECEPTOR_ANGLE 0 and −π/2 give bit-identical
MODEL_DATA in every cell); **P2 passes** (M3 and M4: every `3C286-SIM` row
bit-identical per channel over 115° of parallactic angle). FEED
`POLARIZATION_TYPE` is `X, Y` on both MSs; RECEPTOR_ANGLE is −π/2 on A1 small
and **0 on the slice** (read by casatools: rang's table reader cannot read
that string-array column, see 11).

Class T: **T1 passes.** At 1.47 GHz rang's models give 9.800 % and
33.00002° (3C286) and 7.800 % and −9.59991° (3C138); CASA's MODEL_DATA over
all 2048 channels of S gives p 9.799998–9.800002 % and χ 33.000006–33.000031°,
and 7.799995–7.800005 % and −9.599914 to −9.599901°: the published 2019 values
within the tables' rounding, with χ's sign as published (Re XY > 0 for 3C286).
**T2 as predicted**, to the digit: Δp +1.2, +0.3, −0.1, +1.2 points for 3C286
at 1.05, 1.45, 1.64, 1.02 GHz and Δχ 0; 3C138 Δp +2.2, +0.3, −0.6, +2.3 and
Δχ +4.4°, +1.4°, +0.4°, +3.4°. CARACal's constant-p models are 1.2 (3C286)
and 2.2 (3C138) points above PB2013 at 1.05 GHz (1.2 and 2.3 above NRAO 2019
at 1.02 GHz), and 3C138's angle 4.4° off at 1.05 GHz; this is
the model's accuracy, not rang's. **T3:** Taylor & Legodi's MeerKAT 3C286
angle is 29.2°, 3.8° from the NRAO 33°; 3C138 −15.1° against −9.6°.

Wall time: CASA `setjy` 1.4 s (S) and 2.6 s (A) per call, 21.2 s for nine
calls in one container; rang `set_model` 0.8 s (S) and 10.6 s (A, the column
added on `/mnt/d`); whole run 103.9 s.

**Diagnosis of M7 and M8 (post hoc, from run `-03`'s copies).** CASA's cells
are rang's times a constant: I, Q, U and V ratios 0.99999429 (M7) and
0.99998405 (M8), the same in every channel and Stokes to float32 noise, and
χ equal to 1e-5°. The rotation and spectral shapes agree; only the scale
differs. The cause is `Imager::sjy_setmanualflux` lines 5466–5495: channel 0's
I is evaluated at `cvt(ch0)`, the channel-0 frequency converted from the MS
frame (TOPO here) to `reffreq`'s frame (LSRK, casacore's default for a
quantity string), at the epoch of main-table row 0 (`Imager.cc` 4705) and the
field's direction; then the `SpectralIndex` component is referenced to the
unconverted channel 0. So CASA = rang × K, K = (f_LSRK(ch0)/f_TOPO(ch0))^α.
A prediction with nothing fitted (astropy barycentric correction plus the
Sun's LSRK motion, the ANTENNA centroid, row 0's TIME): v/c = 9.197e-6
(3C286-SIM) and 2.673e-5 (SIM-GCAL); implied from CASA's cells (mean over
channels): 9.066e-6 and 2.658e-5. Sign and size agree for both directions at
one epoch, within 1.4 % and 0.55 % (an offset of about 40 m/s for both, which
I did not trace; it is 1e-7 in K). The tabular path takes Q, U and I at the
unconverted frequencies, which is why M1–M6 agree to the bit.

**Deviations.**

- Run `-01` (`/mnt/d/rang/outputs/c7a-20261106-01`, kept, 37 MB) was killed
  by a host reboot after copying two MSs; nothing was compared.
- Run `-02` (kept, 928 MB) wrote every copy and then stopped in the frame
  checks: rang's table reader cannot read FEED's `POLARIZATION_TYPE`. Its
  comparison results were never written or read. The harness now reads FEED
  with casatools inside the CASA image (`casa-feed`) and writes the case
  results before the frame checks; `-03` reran everything from fresh copies.

## 9. Post-hoc fix and the held-out case

**Post hoc (labelled; after `-03`, committed in `52984c1` before the fix).**
`calmodels.lsrk_over_topo(time, ra, dec, itrf)` computes f_LSRK/f_TOPO with
astropy as in the prediction above (IERS download off, as `rang.measures`).
On CASA's polarised SpectralIndex path only, `set_model` reads TIME of
main-table row 0 (before its own session, or through the caller's session,
outside the chunk loop), each field's PHASE_DIR and the ANTENNA centroid, and
`Manual.stokes(..., ch0_frame_ratio=K)` evaluates channel 0's I at the
converted frequency, Q and U at the stored one, as `sjy_setmanualflux`
does. LSRK windows take K = 1; other `MEAS_FREQ_REF` values are refused on
this path. The receipt records the epoch, the centroid and K per field and
window. Every other path is unchanged (the code of the tabular and
unpolarised paths is not touched). CASA takes the observatory from
`MeasTable::Observatory(TELESCOPE_NAME)`; rang uses the ANTENNA centroid, a
difference of km at most, about 1e-4 km/s in the correction.

After the runs (outside the measured path; the archive's `calmodels.py`
SHA-256 `f0a42678…` predates it): astropy is an optional dependency
(`imaging` extra), so `rang-core calibrate` refuses a polarised one-term
`spix` model when astropy is missing, and `set_model` raises a clear error;
`lsrk_over_topo` itself is unchanged. At today's epoch it runs without IERS
warnings (bundled tables, download off).

| Run | Case | Path | G1 | G2 real ulps | G2 imag /I | G3 | Pass |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `-04` (post hoc, fresh copies, `calmodels.py` `f0a42678…`) | M1–M6 | tabular | as `-03` (0 ulps; M3, M4, M6 bit-identical) | 0 | ≤ 1.3e-13 | yes | **yes** |
| `-04` | M7 | SpectralIndex | **1.5e-7** | **2** | 0 | yes | no (G2) |
| `-04` | M8 | SpectralIndex | **1.3e-7** | **2** | 1.6e-9 | yes | no (G2) |
| `-05` (**held out**, frozen in `9893fbe`, no code change after `-04`) | H1 `3C286-SIM` (3C138 Q, U, V override, 2- and 3-term polynomials, RM −20) | tabular | 0 (bit-identical) | 0 | 0 | yes | yes |
| `-05` | H1 `SIM-GCAL` (Q, U from `fluxdensity`, RM 15) | SpectralIndex | **1.3e-7** | **2** | 0 | yes | no (G2) |

`-04` also repeats P1, P2 and T1, all pass. **H1 fails as written**: its
SpectralIndex half misses the 0-ulp bound by 2 ulps, while it is 8× inside
C1's 1e-6 bound. The residual is the 40 m/s (1.4e-7 in v/c) between
astropy's and casacore's TOPO-to-LSRK correction found in section 8; no
parameter was tuned on it. Bit parity on this path would need casacore's own
frame conversion (IERS tables, its LSRK apex and Earth-velocity model),
which rang does not have.

**Reading.** CARACal's shipped 3C286 and 3C138 models, and any model with a
multi-term `spix` or polynomial `polindex`/`polangle`, reproduce `setjy` to
the bit. The one-term `spix` path (CARACal's Taylor & Legodi option) follows
CASA's model to 1.5e-7 of I. CASA's own behaviour there is an inconsistency:
its model is scaled by (1 − v_LSRK/c)^α, 1e-5 for MeerKAT's L band, depending
on the epoch of row 0 and on the field. Rang copies it, for parity (owner
decision 1).

## 10. Owner decisions, not checked, on disk

**Owner decisions (provisional, the agent's choice):**

1. Copy CASA's channel-0 frame behaviour on the polarised SpectralIndex path
   (a scale of about 1e-5, dependent on the epoch and direction) rather than
   write the frame-consistent model. Parity with the oracle; CARACal's Taylor
   & Legodi option takes this path.
2. Refuse `polindex` without `polangle` (or the reverse) when Q = U = 0;
   CASA silently writes no linear polarisation.
3. Accept a 2-ulp, 1.5e-7 residual on that path (H1 and `-04` fail G2, pass
   G1), or ask for casacore's frame conversion to be ported.
4. Ship `taylor_legodi_2024.txt` (12 kB, CARACal's) as a rang constant table:
   not done here.
5. Polarised models stay on the primary fields: the polcal field refusal
   names C2d (C4b decision 4). A 3C286 polcal model needs that lifted.

**Not checked.** Circular feeds (the mapping is C3a's, untested against
CASA here); several spectral windows; an MS whose SPW frame is not TOPO; a
`reffreq` with an explicit frame; CASA 6.7.6.14's C++ source (the mirror is
from 2023; the oracle runs confirm the behaviour of the cases above only);
the 40 m/s astropy–casacore offset; whether the polarised path writes the
same through `rang-core calibrate` end to end (unit-tested through
`model_spec`, not run on A1); the NRAO 2019 table against a second source.

**On disk** (all ignored): runs `/mnt/d/rang/outputs/c7a-20261106-01` (37 MB,
killed), `-02` (928 MB, harness crash), `-03` (928 MB, frozen), `-04`
(928 MB, post hoc), `-05` (129 MB, held out) and their logs; sources
`~/Github/rang/outputs/c7a-sources-20261106/` (CASA mirror files, casacore
`Polynomial`, CARACal files, the oracle image's `task_setjy.py`); the
worktree venv. The run directories can be deleted once the coordinator has
read this note.

## 11. For the coordinator

Proposed STATE line: "C7a, 2026-11-06: polarised calibrator models
([c7a-polmodels.md](c7a-polmodels.md)). `calmodels.Manual` takes `setjy`
manual's I, Q, U, V, `polindex`, `polangle`, `rotmeas`; CARACal's 3C286 and
3C138 are `calmodels.NRAO_XCAL`. Against CASA 6.7.6.14: 0 float32 ulps on
all four correlations on the tabular path (7 cases: M1–M6 and the held-out
H1's tabular half); the
one-term `spix` path within 1.5e-7 of I, 2 ulps (G2 fails as written; CASA
converts channel 0 to LSRK there, which rang copies post hoc). MODEL_DATA is
sky-frame, independent of parallactic angle and RECEPTOR_ANGLE (P1, P2).
CARACal's constant-p models are 1.2 (3C286) and 2.2 (3C138) points above
Perley & Butler 2013 at 1.05 GHz."

Proposed finish-plan C7 row note: "C7a done 2026-11-06; the polcal-field
model (C2d refusal) and C7b remain."

Items for others:

- **`core_ms` reader bug:** reading FEED's string-array
  `POLARIZATION_TYPE` fails with a read at a garbage offset ("read of 8 bytes
  at 206158430210"), not a clean refusal, on both MSs. Fixed 2026-11-12
  ([feed-poltype-read.md](feed-poltype-read.md)).
- **The slice's RECEPTOR_ANGLE is 0**, A1 small's −π/2; C6 on the slice must
  set it as CARACal does.
- **Parallactic angle (finish-plan 7.8):** C7a needs none; C6 and C7b do.
- **`rang.simtruth` RM** is referenced to λ = 0, CASA's to `reffreq`
  (section 3); matters for any truth with RM ≠ 0.
- **The uv venv has no pip**, so `maturin develop` in check-all fails until
  `uv pip install pip`; the editable install already builds the extension.
- **C1's T7 open question** "the model per channel ≤ 1e-6 of |I|": met on
  every path.
