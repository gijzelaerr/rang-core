# P flag spread: why CASA flags XX and YY where Df is flagged

Task df-flag-rule, 2026-11-12. Status: **proposed** (this section frozen before any code or CASA run of the task).

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

(filled by `--predict` before the CASA run)

## 6. Measured result

(after the run)
