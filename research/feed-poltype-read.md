# FEED POLARIZATION_TYPE: reading StandardStMan's indirect string arrays

2026-11-12, branch `claude/feed-poltype-read-ea1d2d`. Status: implemented and
measured against python-casacore 3.8.1. This is a reader correctness fix
with no performance or science claim; the oracle is python-casacore's
`getcell` on the same tables.

## Fault

`rang.core_ms` failed on FEED's `POLARIZATION_TYPE` (C7a, `c7a-polmodels.md`
section 8 and its items for others; `finish-plan.md` section 7 item 14).
Reproduced on 2026-11-12 with the main checkout's extension from before the fix:

- `D:\rang\outputs\c7a-20261106-03\M1-casa.ms\FEED`: `read of 8 bytes at
  206158430210 failed`, the C7a message;
- `D:\rang\c3a\c3a-20261106-01\A-casa.ms\FEED`: `read of 507510784 bytes
  at 6 failed`.

## Cause

`POLARIZATION_TYPE` is a variable-shape (`ndim` 1) string array in
StandardStMan without the Direct option. casacore stores such a column with
`SSMIndStringColumn`: each row has a 12-byte slot (string bucket, offset,
length), and the cell sits in SSM's own string buckets as canonical
(big-endian) ints: the dimension count, the dimensions, a filled flag, and
then for each string its length and characters. A fixed-shape column (shape
in the description with the FixedShape option, or set for the whole column)
stores the strings alone. Nothing of it goes to `table.f0i`.

The reader sent every non-direct array, strings included, down the numeric
indirect path: it read an 8-byte `table.f0i` offset from the row's slot and
followed it. For M1-casa row 0 the slot is (2, 0x30, 0x16); read as a
little-endian u64 that is 0x30_0000_0002 = 206158430210, the reported offset.
The writer (`core/src/ms_write.rs`, E4) already had this layout right
(`str_get_array`); only the reader had it wrong.

## Fix

`core/src/ms.rs`: the new `SsmKind::IndirectStringArray(fixed)` covers
non-direct string arrays in StandardStMan. It reads the slot, then the shape
and filled flag (variable shape only), then the strings, following the
bucket chain. An empty slot is refused as an undefined cell for a
variable-shape column (as numeric indirect arrays already are) and read as
empty strings for a fixed-shape one (`SSMStringHandler::get`). Rows that
differ in shape are refused for a multi-row read, as for numbers. A cell
whose declared strings cannot fit in the slot's length is refused before
anything is allocated. `ColumnDesc.fixed_shape` records whether the shape is
fixed, the same rule the writer uses. IncrementalStMan string arrays are
still refused cleanly ("IncrementalStMan array or string column ... is not
supported").

Other columns on the same path, all covered by the fix and the comparison
below: HISTORY `APP_PARAMS` and `CLI_COMMAND`, and OBSERVATION `LOG` and
`SCHEDULE`. SOURCE and FIELD names, ANTENNA `NAME` and the like are scalar
strings, which were already read correctly. `POLARIZATION.CORR_TYPE` is an
int array.

## Oracle checks

1. **Fixture** `tests/data/strarray` (24 kB, written by python-casacore
   3.8.1 with `tools/oracles/strarray/fixture.py`, 12 rows, 512-byte
   buckets): FEED-like `POLARIZATION_TYPE` (`X, Y` and `R, L`); a
   variable-shape column with shapes [2], [3], [2, 3] and [0], empty strings
   and non-ASCII text; fixed-shape non-direct, direct, strings of 300 to
   707 characters across buckets, and scalars; and an IncrementalStMan
   string array. `oracle.json` holds each cell as `getcell` returns it.
   `tests/test_core_ms_strarray.py` compares every cell, whole columns and
   out-of-order row lists, and the refusals. RESULT_FIXTURE
2. **Real MSs** (`tools/oracles/strarray/compare.py`: `dump` in WSL with
   python-casacore 3.8.1, `check` natively): every string column, scalar or
   array, of the main table and every subtable of 13 MSs: C7a M1-casa and
   M1-rang (`c7a-20261106-03`); c3a A-casa and S-rang-sr; LUNO `work.ms`
   and E2's `luno-dev.ms`; a MeerKAT `sdp_l0` scan (`b1-20261030-03-fixture`);
   E4's `casa.ms` and rang-written `core.ms`; E2's `e2b.ms`, `pilot.ms`
   (converted by rang) and `a1-small.ms` (dry run `e2-20261111-12`); and the
   C2d `slice2.ms`. That is 170 tables and 3,344 cells, at most 2,000 rows
   per table. RESULT_REAL

## Using POLARIZATION_TYPE

`rang.cal_pol.receptor_angles`, the one place that reads FEED to build P
for linear feeds, now also reads `POLARIZATION_TYPE` (`cal_pol.feed_types`)
and refuses a FEED whose rows are not `X, Y`. Rows without a value, or with
empty strings only, are not checked, so a FEED written without the column's
values reads as before. All 13 MSs above, E2's among them, are `X, Y` in
casacore, so nothing that runs now changes. The pipeline's own circular-feed
refusals go by `POLARIZATION.CORR_TYPE` (`core_pipeline`, `applycal`,
`core_imaging`, the campaign modules); they are left as they are.

## For the coordinator

- Item 14's reader bug (finish-plan section 7) and the matching C7a item are
  fixed; the C7a harness's `casa-feed` workaround can read FEED with
  `rang.core_ms` again if wanted (not changed here).
- Open, not done: whether the CORR_TYPE-based linear checks should also
  check FEED (two sources of the same fact); and IncrementalStMan string
  arrays, which are still refused (none in the 13 MSs).
