# P flag spread: why CASA flags XX and YY where Df is flagged

Task df-flag-rule, 2026-11-12. Status: **implemented and measured** (sections 1-4 frozen in `66b8cb5` before any code or CASA run; predictions
in `3d91dce` before the CASA run): gate met, flags exact on all five cases.

## 1. The finding to explain

E2's development slice (J1331+3030, the only field whose apply includes Df; `applycal(parang=True)`): CASA flags
1,008,519 XX cells and as many YY cells that rang leaves unflagged; rang never flags a cell CASA leaves unflagged.
Every extra flag sits where Df is flagged for one of the baseline's antennas, but only 70 % of such cells (of
1,446,125) gain one. rang's apply follows C4a's reading of `Jones.cc` (`research/c4a-apply.md` 4.3): Df flags only
the cross hands. C4a, C4b and C6 measured that with `parang=False`; C6w ran `parang=True` but its tables had no
effective (post-interpolation) Df flags and its input flags covered all four correlations.

## 2. Hypothesis, read in CASA's source

Sources: `casa6-9269a52` (`outputs/c7a-sources-20261106`, WSL) and the 2023 mirror (`c1-sources-20261105`), not
6.7.6.14 itself; the simulation below is the arbiter.

- `PJones::syncMeta2` (`StandardVisCal.cc`): for linear feeds (`correlationTypes()(0)==9`) P's Jones type is
  `Jones::General`; `calcOneJones` gives `[[c, s], [-s, c]]` with every element OK.
- `VisCal::Type` (`VisCal.h`): `Test, ANoise, M, KAntPos, B, K, G, J, D, X, C, P, E, T, F, A`;
  `VisEquation::correct2` applies the terms in that order, so P comes after D and X.
- `VisJones::applyCal2` (`VisCal.cc`): per row and channel `J1().applyRight(V()); J2().applyLeft(V())`, and
  `Jones::applyRight`/`applyLeft` call `flagRight`/`flagLeft` first whenever the VisVector carries flags.
- `Jones::flagRight` (general): `f0 |= f0|f2`, `f1 |= f1|f3`, `f2 |= f0|f2`, `f3 |= f1|f3` (plus `!ok`), and
  `flagLeft`: `f0 |= f0|f1`, `f1 |= f0|f1`, `f2 |= f2|f3`, `f3 |= f2|f3`. Right then left: **any one flagged
  correlation flags all four.**

So the rule is not about Df: with `parang=True` on linear feeds, P spreads every flag that stands when it is
applied (input flags, and the flags of B, K, G, J, D, X, C) to all four correlations of the cell. Terms after P
(E, T, F) are scalar or diagonal and flag on their own. Df's cross-hand flags are simply the most common
per-correlation flags in E2's chain. The values agree: rang's P rotation makes XX from all four correlations, so
today rang writes unflagged parallel hands that contain a flagged cross hand.

Not claimed: anything about calibration quality; the 70 % fraction is explained only if E2's own data show (check
E below) that the remaining 30 % are cells where no correlation is flagged after the tables (bridged Df channels)
or where XX and YY are already flagged.

## 3. Change

A key, `apply.parang_flags` (library: `parang_flags=` on `rang.applycal.applycal` and `rang.cal_pol.apply`):

- `spread` (proposed default): where P is applied, a cell with any correlation flagged after the tables gets all
  four flagged (CASA's general-Jones rule). Flags are computed in correct order for both directions, as the
  kernel already does, so `corrupt` flags the same cells as `correct`.
- `none`: today's behaviour, byte-identical output.

Without `parang` the key does nothing. E2's frozen protocol, wheel and run directories are not touched; the
default applies to code after E2.

## 4. Oracle, data and gate (frozen)

Oracle: CASA 6.7.6.14 `applycal` in `rang-o-casa:6.7.6.14` (`applymode='calflag'`, `calwt=[False]`,
`gainfield='nearest'`, `flagbackup=False`), against `rang.applycal.applycal` on copies of O-CASA's slice
`outputs/o-casa-20261030-01/c.ms` (J1939-6342, 4 antennas, 192 rows, 2048 channels, linear feeds). Synthetic
tables written by `examples/check_parang_flags.py`, seed 20261112. Run directories `D:\rang\outputs\pfs-20261112-NN`.

| Case | Tables (interp) | parang | What it separates |
| --- | --- | --- | --- |
| A df-noparang | Df with whole-parameter flags: antenna 0 `d_x`, antenna 3 `d_y` (nearest) | False | C4a's rule still holds without P |
| B df-parang | the same Df | True | Df's cross-hand flags spread by P |
| C g-parang | G, 3 slots, antenna 2 receptor X bad at every slot (linear) | True | P spreads a diagonal term's flags: not Df-specific |
| D inflag-parang | none (P only); input FLAG with only XX flagged on baseline 0-1, channels 500-599, only YY on 2-3, channels 700-799 | True | P spreads input flags |
| E chain-parang | K, G, B (seeded, flagged slots and a flagged B range), Df as in A (E2's interps: linear, linear, linear, nearest) | True | the chain in E2's order |

Predicted new flags per correlation (rang with `spread`, written by `--predict` before CASA runs) are recorded in
section 5 before the run.

**Gate, per case:** CASA's FLAG equals rang's FLAG (`parang_flags='spread'`) on every cell of the field. Pass
when all five cases are exact. Reported, not gated: rang with `parang_flags='none'` against CASA (expected: exact
on A, differing on B-E by the spread cells only), CORRECTED_DATA against CASA on cells both leave unflagged
(class B, `|V_rang − V_casa| / max_k |V_casa,k|`), `spread` against `none` byte-identical on A.

**Decision:** pass → `spread` is CASA's rule; recommend it as the default. Fail on any case → the hypothesis is
incomplete; record the counts, return to the source, and any revised rule is post hoc and needs a fresh case.

**E2's slice (read-only, if E2 gives the paths):** CASA's four flags equal in every J1331+3030 cell; CASA's XX flag
equal to the OR of rang's four output flags; the 437,606 cells that gain no flag classified as already flagged in
XX/YY or with no flagged correlation after the tables. Reported, not gated (E2's run is frozen).

Cost: a cheap OR over four booleans per cell; no timing claim.

## 5. Predictions

`examples/check_parang_flags.py predict D:\rang\outputs\pfs-20261112-01-predict` (rang with `spread`, before any
CASA run; new flags over the field's input FLAG, per XX, XY, YX, YY; 18.2 min wall, nearly all of it waiting
in the heavy-lock queue):

| Case | New flags (XX, XY, YX, YY) |
| --- | --- |
| A df-noparang | 0, 96,407, 0, 0 |
| B df-parang | 96,407 each |
| C g-parang | 60,135 each |
| D inflag-parang | 3,200, 6,400, 6,400, 3,200 (over the edited FLAG) |
| E chain-parang | 103,626 each |

E2's own measurements (relayed 2026-11-12 by the E2 session, read-only; not gated): every CASA-only XX or YY
cell on J1331+3030 had XY and YX already flagged in both CASA's and rang's FLAG, and no cross-hand cell was
flagged by CASA alone. That is what `spread` predicts. E2's snapshot of CASA's post-applycal FLAG was taken after
a later step had reset FLAG, so check E of section 4 waits for E2-B's snapshot.

## 6. Measured result

Run `D:\rang\outputs\pfs-20261112-02` (code `3d91dce`, `examples/check_parang_flags.py run`; `result.json`, the
seeded tables, `casa-apply.json` and one `export/<case>.npz` per case with the input, CASA, `spread` and `none`
FLAG; 1.3 MB). CASA 6.7.6.14 in `rang-o-casa:6.7.6.14`. 21.6 s wall inside the script (5 `applycal` 14.7 s; rang
0.2-1.8 s per apply), under the heavy lock's shared slots.

**Gate: met, flags exact on all five cases.** Every count equals the prediction of section 5.

| Case | CASA new (XX, XY, YX, YY) | CASA four equal | `spread` | `none` (CASA only; rang only) | Class B median / p95 (reported) |
| --- | --- | --- | --- | --- | --- |
| A df-noparang | 0, 96,407, 0, 0 | no | exact | exact | 0 / 1.4e-8 |
| B df-parang | 96,407 each | yes | exact | 96,407, 0, 96,407, 96,407; none | 3.2e-7 / 6.6e-7 |
| C g-parang | 60,135 each | yes | exact | 0, 38,320, 21,815, 60,135; none | 3.5e-6 / 6.0e-6 |
| D inflag-parang | 3,200, 6,400, 6,400, 3,200 | yes | exact | 3,200, 6,400, 6,400, 3,200; none | 1.2e-7 / 2.5e-7 |
| E chain-parang | 103,626 each | yes | exact | 83,857, 0, 44,638, 64,407; none | 4.5e-6 / 6.5e-6 |

`spread` and `none` give bit-identical CORRECTED_DATA on every case; only FLAG differs. Without P (case A) CASA's
Df rule is C4a's: only cross hands are flagged. With P every flag spreads to all four correlations, whether it
comes from Df (B), a diagonal term's receptor (C), the input FLAG (D) or the chain (E). So the rule is P's, not
Df's. `none` never flags a cell CASA leaves unflagged, which is E2's observation.

**E2's 70 %.** CASA flags XX and YY exactly where rang flags XY or YX (or any one correlation). Where a Df
parameter is flagged on the table but rang's cross hands are not flagged after interpolation (nearest frequency
interpolation moves to the closest unflagged solution channel), or where XX is already flagged, nothing new
appears. That would explain why only 1,008,519 of 1,446,125 cells gain a flag, but it is not counted on the
development slice: E2's snapshot there was taken after a later step had reset FLAG. E2's measurement that every
CASA-only cell had both cross hands flagged fits the rule.

**Check E on E2-B (read-only, reported).** `D:\rang\outputs\e2-20261111-20-e2b\df-flag-snapshot\flags-after-applycal.npz`
(CASA's FLAG after `applycal` and rang's applied FLAG; 272,916 rows × 4,096 channels; script and counts kept in
this session's scratch, summarised here): on fields 0, 1 and 2 (484M, 490M and 144M cells) CASA's and rang's
flags differ in 0 cells, neither has a partly flagged cell, and rang's FLAG ORed over the four correlations
equals CASA's in every cell. That is consistent but does not discriminate: with no partly flagged cell,
`spread` and `none` give the same flags (presumably no Df flag on E2-B survives interpolation; not checked on
its table).

**Recommendation for the owner: `spread` as the default** (implemented so). It is CASA's rule. It also matches
the values: P builds XX and YY from all four correlations, so with `none` rang writes unflagged parallel hands
that contain a flagged cross hand. E2's frozen run is unaffected (its wheel and code paths predate this);
E2's gate 2b flag difference on J1331+3030 is this rule.

**Full check** (`python -m rang.check`, after the measured run): every step passes (1,279 pytest). The
gain-hash gate passed on a separate run (8.2 s) with `RANG_ARCHIVE_OUTPUTS` set to the WSL outputs over
`\\wsl.localhost`. After the measured run, the constant was renamed from `PARANG_FLAGS` to `P_FLAG_RULES`
because the receipts test reads `RANG_`-like names as environment variables. Behaviour is unchanged.

Not done here: CASA's solves with `parang=True` (Gpol, KCROSS, Xf, Df) corrupt the model by P, which may flag
the same way in the solver's pre-apply. rang's solves rotate the model without flags. Not tested; a follow-up if
the polarisation solves' flag counts ever matter.
