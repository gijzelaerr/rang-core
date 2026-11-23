# TS-P4: unit weights become `rang-core lightcurve`'s default

Issue #9. Owner decision of 2026-11-23, relayed by the coordinator: make
`--weights unit` the default. Branch `ts-p4` from `origin/main` at
`3e26dd49` (it holds ts-p3's merge `db571c35`). Written 2026-11-23.

**Status 2026-11-23: implemented and measured (section 7): met, V1-V7 all
pass.**

**Status at freeze: proposed. Nothing in this note is built or measured.** It
is committed before the code change. Later changes are dated amendments in
section 6.

## 1. The change

- `rang-core lightcurve` and `rang.lightcurve.light_curves` default to
  `weights="unit"`: every correlation weighs 1, FLAG and FLAG_ROW applied
  (gemclean's `-unit-weights`; [ts-p3.md](ts-p3.md) 1a). `--weights ms`
  keeps the MS's WEIGHT_SPECTRUM (else WEIGHT), the old default.
- **Why** (ts-p3 9.5, reported): on E2-A's scan 10 the unit weights cut the
  snapshot σ_meas by 28 % and the residual's offsets at forced positions from
  up to 1.19 to at most 0.15 mJy; E2-A's deep model was itself made with
  `-unit-weights`, and the scope note calls MeerKAT data weights untrusted.
- **CHANGELOG**, under Unreleased, marked **behaviour change**: the new
  default, what changes, and `--weights ms` for the old outputs.

## 2. What changes

| Output | Changes? |
| --- | --- |
| Any run without `--weights` on an MS whose Stokes I weights are not all equal | yes: every flux, σ_meas, snapshot and candidate |
| The same on an MS with equal weights in every unflagged cell (P1's `tsp1-dev`, `tsp1-held`, `tsp1-noise*`) | values equal mathematically (a constant weight cancels in Σw x / Σw); `weight_sum` changes, bits may change |
| P1 protocol 2 (`tsp1-held2`), P2 (`tsp2-*`), the P2/P3 real track and P3's run arm with MS weights | yes |
| Archived results in `research/results/ts-p1`, `ts-p2`, `ts-p3` | unchanged; they were made with MS weights, which `--weights ms` reproduces (V1) |
| `lightcurve.json` `settings.weights` | `"unit"` by default |

No gate of ts-p1, ts-p2 or ts-p3 is re-scored or re-labelled; their verdicts
stand for the weights they used. The unit-weight path itself was verified in
ts-p3 (U1-U4, real track: WSClean 3.3e-7 of the peak, pixels ≤ 3.2e-6 σ,
DFT ≤ 6.3e-12 σ). The change is the default only, so the re-verification
below checks that the default now is that path, and repeats WSClean and DFT
parity on a simulation with unequal weights. The real-track MS was deleted
after ts-p3 (rebuilding it takes about 1.5 h of replay, split and predict);
it is not rebuilt unless the coordinator asks.

## 3. Re-verification (gates, frozen)

Data: `tsp2-dev` regenerated from its seeds (ts-p2 4.1: spectral unequal
WEIGHT_SPECTRUM, flags, CORRECTED_DATA), in
`D:\rang\outputs\ts-p4-20261123`. Settings for every run: positions A-F,
`--size 1024 --scale 2asec --channels-out 16 --candidates 5`.

| Run | Code | Option |
| --- | --- | --- |
| L-old | `origin/main` (before the change), this worktree | none (MS weights) |
| L-new | the change | none |
| L-ms | the change | `--weights ms` |
| L-unit | the change | `--weights unit` |
| W-T1, W-D2 | WSClean 3.7 on an ext4 copy with RESIDUAL_DATA and WEIGHT_SPECTRUM = 1 (ts-p3's `unit_copy.sh` recipe) | `-intervals-out 450`, and with `-channels-out 16`; 1024² at 2″ |

| ID | Check | Bound |
| --- | --- | --- |
| V1 | L-ms against L-old: `lightcurve.csv`, `dynspec.csv`, `candidates.csv` | byte-identical |
| V2 | L-new against L-unit: the same three files | byte-identical |
| V3 | L-new snapshots against W-T1, every interval | L∞ ≤ 1e-5 × max \|WSClean\| |
| V4 | L-new band DFT against the WSClean W-T1 pixel, and against NumPy with unit weights | ≤ 1e-3 σ per point |
| V5 | L-new cells against W-D2 pixels, and against NumPy per group | ≤ 1e-3 σ per cell |
| V6 | L-new: group-weighted mean against the band DFT; empty group null | ≤ 1e-6 σ; null everywhere |
| V7 | L-new differs from L-old in `flux_jy` (the default did change) | at least one value differs |

σ: the truth's σ_snap,k and σ_k,g (computed for MS weights; here only a
scale for parity bounds). Tests: the default equals `--weights unit`;
`--weights ms` equals the previous default's CSVs (the existing U5 test,
re-pointed). `docs/cli.md` regenerated.

## 4. Decision rule

Met when V1-V7 pass, the quick check passes and CI is green. A failure is
recorded with its numbers; no tolerance changes.

## 5. For the coordinator, at freeze

- The real-track re-verification is ts-p3's U1-U4 (the same code path);
  rebuilding the 92 GB MS to repeat it is left to your call.
- Users of the old default must add `--weights ms` to reproduce earlier
  light curves; the CHANGELOG says so.

## 6. Amendments

(none)

## 7. Measured result

Run root `D:\rang\outputs\ts-p4-20261123` (deleted after scoring), host
glacier, shared slots. L-old ran with this branch at `88b5e09c` before any
code change (`results/ts-p4/lc-old.code.txt`); L-new, L-ms and L-unit with
the change (committed as `eaded5bc`, product code identical to the runs).
`tsp2-dev` regenerated in about 90 s; each lightcurve run 59-81 s (4 slots).
WSClean 3.7 `-j 8` on the unit-weighted ext4 copy (`unit_copy.sh ... none`):
`-intervals-out 450` in 80 s, with `-channels-out 16` in 815 s.
Scores: [results/ts-p4/verify.json](results/ts-p4/verify.json); CSV hashes:
[results/ts-p4/csv-sha256.txt](results/ts-p4/csv-sha256.txt).

| Gate | Reading | Bound | Outcome |
| --- | --- | --- | --- |
| V1 | `lightcurve.csv`, `dynspec.csv`, `candidates.csv` of L-ms equal L-old's | byte-identical | **met** |
| V2 | the same files of L-new equal L-unit's | byte-identical | **met** |
| V3 | L-new snapshots against WSClean: max 4.8e-7 of the peak (median 2.4e-7; worst interval 276) | 1e-5 | **met** |
| V4 | band DFT against WSClean's pixel 1.4e-6 σ, against NumPy (unit weights) 2.4e-12 σ | 1e-3 σ | **met** |
| V5 | cells against WSClean `-channels-out` 1.1e-6 σ, against NumPy 2.6e-12 σ; CRVAL3 offset 0 Hz | 1e-3 σ | **met** |
| V6 | group-weighted mean against the band 1.3e-14 σ; group 15 null throughout | 1e-6 σ; null | **met** |
| V7 | L-new differs from L-old by up to 5.0 σ_snap in `flux_jy` | > 0 | **met** |

`settings.weights` reads `"unit"` in L-new and `"ms"` in L-old. Tests: the
default equals `--weights unit` byte for byte and `--weights ms` changes the
fluxes (`tests/test_ts_p2_dynspec.py`); the P1 protocol-2 test now runs both
weightings against the NumPy oracle (`tests/test_ts_p1_lightcurve.py`; the
P1 scorer reads the run's weights). Quick check PASS.

**Met.** The default is the unit-weight path verified in ts-p3 (U1-U4 on the
real track) and here on a simulation with unequal weights; `--weights ms`
reproduces the earlier default byte for byte.
