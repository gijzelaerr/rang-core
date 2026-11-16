# MSv4 interoperability: reading an xradio processing set into ra-ng

2026-11-16, branch `msv4-interop`, gijzelaerr/rang-core issue #5 (second part;
the first part is [msv2-edge-cases.md](msv2-edge-cases.md)). Status:
**measured, pass** (section 7). Sections 1 to 6 are frozen in the commit that adds this note,
before any ra-ng code reads an MSv4 store. Later changes are dated and
labelled post hoc. The note makes no performance or science claim: it checks
that a new read path returns the same bits as the MSv2 path.

## 1. What MSv4 means for ra-ng users

- **The format.** MSv4 is the xradio schema (NRAO/CASA-NG, `schema_version`
  4.0.x): a *processing set*, an xarray DataTree, by default a Zarr v3 store.
  Each child is one MSv4, a partition of the MSv2 main table (xradio 1.3.1
  partitions by `DATA_DESC_ID`, `OBS_MODE` and `OBSERVATION_ID`). It holds a
  correlated dataset on a regular grid, `VISIBILITY`, `FLAG` and `WEIGHT`
  over `(time, baseline_id, frequency, polarization)` and `UVW` over
  `(time, baseline_id, uvw_label)`, plus `antenna_xds`, `field_and_source_*_xds`
  and `pointing_xds` children. Antennas are named, not numbered; `time` is
  Unix seconds; missing `(time, baseline)` cells are padded.
- **Who writes it.** xradio's `convert_msv2_to_processing_set`; xarray-ms
  (RATT) opens an MSv2 as the same kind of DataTree
  (`engine="xarray-ms:msv2"`), which `to_zarr` writes as a store. The CASA-NG
  and RATT tools are moving to it. An astronomer who receives a processing
  set, or converts an MS to use those tools, cannot give it to ra-ng today.
- **What ra-ng reads today.** MSv2 through its own Rust reader
  (`rang.core_ms`, checked against arcae in the first part of #5), MVFv4
  through katdal (`rang.meerkat`), and the section 6 zarr v2 slices.

## 2. Which direction first: reading

Reading an MSv4 into ra-ng comes first, and writing waits:

- **Users.** Reading lets a processing set from xradio or xarray-ms reach
  ra-ng's stages. Writing would only help a user whose next tool reads MSv4
  and not MSv2, and xradio and xarray-ms both read MSv2 already.
- **Oracle.** Reading has an exact oracle now: the MSv2 an xradio store was
  converted from, read by ra-ng's MSv2 reader, which matched arcae on 928
  of 1009 columns with 0 mismatches. A writer would need xradio's validator
  and a schema that is still moving (xarray-ms lists itself as not yet at
  parity), and the issue's gate for writing (per-chunk writes, object
  storage, multi-node) needs a cluster this host is not.
- **Size.** A reader is a pure Python adapter over xarray and zarr. A writer
  touches the writeback sessions and the journal (`core_writeback.py`).

## 3. The piece built here (frozen scope)

- **Module:** `rang.msv4`, behind a new optional extra `msv4` (xarray, zarr 3,
  numcodecs; Python 3.11 or later, as zarr 3 requires). The core install gains
  nothing. arcae, which both xradio's converter (`xradio[casacore]`) and
  xarray-ms need, has no Windows wheel (0.5.9: manylinux and macOS only), so
  xradio and xarray-ms stay oracle-only and run in WSL. The probe (section 5)
  showed xarray 2026.9.0, zarr 3.4.2 and numcodecs 0.17.1 open xradio's store
  natively on Windows.
- **Input:** a processing-set path or an opened `xarray.DataTree`, so the
  same code reads an xradio store and an xarray-ms tree.
- **Output:** per partition, row chunks in the layout `rang.meerkat.MvfLoader`
  already yields (the keys and dtypes of `core_fetch.decode_slice`):
  - `TIME` (MJD seconds, `time + 3506716800.0`);
  - `ANTENNA1`, `ANTENNA2` (int32 indices into the partition's
    `antenna_xds.antenna_name`, with the names alongside);
  - `FLAG_ROW` (false: MSv4 has none);
  - `DATA` complex64, `FLAG` bool and `WEIGHT_SPECTRUM` float32, each
    `(row, channel, corr)`;
  - `UVW` float64 `(row, 3)`;
  - `FIELD_NAME` and `SCAN_NAME` per row.
  Rows are time-major in `baseline_id` order; channels and correlations in
  the store's order. The data group is `base` unless asked.
- **Pads:** a `(time, baseline)` cell is a pad when every `UVW` and every
  `VISIBILITY` value of it is NaN. Pads are dropped, so the rows are those of
  the MSv2. xradio pads `FLAG` with false and xarray-ms with true, so `FLAG`
  cannot mark them.
- **Refusals:** a `schema_version` other than 4.x; a partition whose `type` is
  not `visibility` (single dish, radiometer); other dimension names; a
  `VISIBILITY` other than complex64, `FLAG` other than bool, `WEIGHT` other
  than float32, `UVW` other than float64.
- **Untouched:** `core_ms`, the writer, the stages and the CLI. Feeding the
  rows to a stage is the next step, not this one.
- **Not claimed:** writing MSv4; a Rust (`zarrs`) reader; object storage;
  throughput; LOFAR or any telescope beyond what the cases hold. Telescope
  specifics stay behind the existing boundary: the module reads the schema
  and knows no telescope.

## 4. Oracle and cases (frozen)

**Writers (WSL, uv venv `~/Build/tmp/20261116-msv4-oracle/venv`, Python 3.12,
public PyPI):** xradio 1.3.1 (`xradio[casacore]`, with arcae 0.5.9, zarr
3.4.2, numcodecs 0.17.1, toolviper 0.1.13) and xarray-ms 0.5.14 (xarray
2026.9.0); python-casacore 3.8.1 only to write the gap case. The arms:

- **xradio arm:** `convert_msv2_to_processing_set(in_file, out_file,
  persistence_mode="w")`, all else default (parallel mode `none`, blosc lz4).
  This is the reference writer of the schema.
- **xarray-ms arm:** `xarray.open_datatree(ms, engine="xarray-ms:msv2")`,
  then `to_zarr(out)`, defaults.

**Reader under test (Windows):** `rang.msv4` in the worktree's `.venv` with
the extra, over each store.

**Reference:** ra-ng's MSv2 reader (`rang.core_ms`) on the source MS. It is
itself checked against arcae ([msv2-edge-cases.md](msv2-edge-cases.md)); every
column read here (`DATA`, `FLAG`, `WEIGHT_SPECTRUM`, `WEIGHT`, `UVW`, `TIME`,
`ANTENNA1`, `ANTENNA2`, `DATA_DESC_ID`, `ANTENNA::NAME`,
`SPECTRAL_WINDOW::CHAN_FREQ`) matched there.

**Cases** (outputs under `D:\rang\outputs\msv4-20261116`):

| id | source | why |
| --- | --- | --- |
| c1 to c5 | the public fixture `outer_scans.zip` (`RANG_FIXTURE`; SKA `ska-sdp-wflow-pointing-offset`), scans 1, 4, 5, 8, 9: MeerKAT, 4 antennas with autocorrelations, 4096 channels, 4 correlations, `WEIGHT_SPECTRUM` | the public fixture |
| c6 | `D:\rang\c3a\c3a-20261106-01\A-casa.ms` (archived; 12480 rows, 16 antennas, 4 fields, 23 scans, 64 channels, `MODEL_DATA`) | several fields and scans, so several partitions or names per time; a second data column |
| c7 | `D:\rang\outputs\c7a-20261106-03\M1-casa.ms` (archived; 192 rows, 2048 channels, 70 % flagged, `MODEL_DATA`) | a CASA-written MS with heavy flags |
| c8 | c5 with rows removed by python-casacore: baseline (m001, m002) at time indices 3 to 5 and the (m003, m003) autocorrelation at the last time | an incomplete grid, so pads |
| c9 | `m05-var-spw-tssm` from the edge-case set (two spectral windows, 4 and 8 channels) | two partitions by `DATA_DESC_ID` |

The fixture's grids are full (c5: 140 rows = 14 times × 10 baselines), as
are c6 and c7; only c8 has pads. No case has `FLAG_ROW` set, `CORRECTED_DATA`,
`SIGMA`-only weights, unwritten `WEIGHT_SPECTRUM` cells, or decreasing
channel frequencies, so those paths are not covered and the note claims
nothing about them.

**Mapping (frozen, so the harness fixes of the first part are not post hoc
here):**

- **Partition to `DATA_DESC_ID`:** the spectral window whose `CHAN_FREQ` holds
  exactly the partition's `frequency` values; ambiguity is a mapping failure.
- **Channels:** MSv2 channel `c` maps to the MSv4 channel whose `frequency`
  equals `CHAN_FREQ[c]` exactly (xradio sorts channels by frequency; all
  cases are ascending).
- **Correlations:** in the order of the partition's `polarization`
  coordinate, which must equal the MSv2 `CORR_TYPE` names (9 to 12 are `XX`,
  `XY`, `YX`, `YY`); otherwise a mapping failure.
- **Rows:** by (`DATA_DESC_ID`, `TIME`, `ANTENNA::NAME[ANTENNA1]`,
  `ANTENNA::NAME[ANTENNA2]`), never by order. `TIME` must equal the
  loader's `TIME` exactly. If no exact match exists, `TIME` is booked a
  mismatch and the rows are mapped by the nearest time within 1 ms, so that
  the other columns are still compared; that fallback is frozen here.
- **Coverage:** every MSv2 row maps to exactly one loader row, and every
  loader row to one MSv2 row (the pads are gone, none is invented).

**Equality and tolerance:** bit-identical. Same shape, same dtype, equal
bytes; NaN payloads and signed zeros count. No tolerance on any column.

**Measures, per case × arm:** `DATA` against MSv2 `DATA`; `FLAG` against
`FLAG`; `WEIGHT_SPECTRUM` against `WEIGHT_SPECTRUM` when that column exists
and every cell is written, otherwise against `WEIGHT` repeated over channels;
`UVW` against `UVW`; `TIME`; the antenna names; the coverage. Each is
`match`, `mismatch`, `refused` (the loader refuses the store or partition,
with its message), `writer fails` (the arm cannot write the case) or `not
measured` (with the reason).

## 5. Probe before the freeze

Before this note, xradio 1.3.1 converted c5 in the oracle venv (3.7 s) to
`D:\rang\outputs\msv4-20261116\probe\scan9.ps.zarr`, and the layout and
xradio's source were read:

- one partition `1672727931_sdp_l0_scan_9_0`, `schema_version` 4.0.1, zarr
  v3 with inline consolidated metadata, blosc lz4 without shuffle, one chunk
  per variable;
- the variables and dimensions of section 1, `time` in Unix seconds;
- xradio pads missing cells with its `get_pad_value` (NaN for floats and
  complex, false for bool) and sorts channels by frequency; the
  `add_reshaping_indices` option (off by default) adds MSv2 row ids for
  testing, which the reader does not use;
- in a scratch native Windows venv, xarray 2026.9.0 with zarr 3.4.2 and
  numcodecs 0.17.1 opened the store with `open_datatree(engine="zarr")` and
  loaded `VISIBILITY`.

ra-ng has read no MSv4 value and compared nothing before this freeze.

## 6. Decision rule (frozen)

The xradio arm decides; the xarray-ms arm is reported beside it.

- **Pass:** every measure of every case in the xradio arm is `match`. Then
  `rang.msv4` is offered for merge as ra-ng's MSv4 read path, behind the
  extra, and the next step (rows into a stage, then `zarrs`) is proposed.
- **Partial:** `DATA`, `FLAG` and the coverage match in every xradio case,
  and some other measure (`WEIGHT_SPECTRUM`, `UVW`, `TIME`, names) does not.
  The reader is offered with that column refused or documented as named
  here, and the miss becomes a task.
- **Failure:** `DATA`, `FLAG` or the coverage mismatches in any xradio case,
  or a case is refused that the scope of section 3 says the reader reads.
  The reader is not offered; the note records why.
- **Oracle disagreement:** where the xradio and xarray-ms stores differ from
  each other and the reader matches the MSv2 for one of them, it is booked
  as a writer difference, not a reader outcome.
- A reader bug found by a run may be fixed and the run repeated; every run is
  recorded with its number, and the rule is applied to the last run of the
  final code. A changed tolerance, mapping or case list is post hoc.

Cost is reported (wall time of each conversion and of each check, at the
threads booked), with no claim attached.

## 7. Measured result (2026-11-16)

Status after the run: **measured, pass** (xradio arm); the xarray-ms arm is
refused by the frozen scope. (2026-11-16: for M1, the amended rerun, see "M1 run" at the end of this section.)

**Runs.** Conversions: WSL, one run, `convert-01.log`, under
`heavy_lock run --slots 2 --mem 4`. Checks: Windows, worktree `.venv`
(Python 3.13.16, extension built by `tools/check_all.py --quick` at this
branch), under `heavy_lock run --slots 1 --mem 4`:

| run | code | outcome |
| --- | --- | --- |
| 01 | harness at `7ebf6ed` + uncommitted reader | stopped at c1's xarray-ms arm: the reader's refusal (`FLAG is uint8, not bool`) escaped the harness instead of being booked `refused` (harness fix) |
| 02 | harness books partition refusals | stopped at c9: ra-ng's MSv2 `getcol("DATA")` refuses rows of two shapes (two windows), so the harness now reads cell columns per `DATA_DESC_ID` with `getcol_rows` (harness fix). The unit test found a reader bug at the same time: the pad rule viewed complex values as float pairs, but the pads are `nan+0j`, so no pad was found; it now uses `np.isnan` of the complex value, as section 3 says |
| 03 | the fixes above, uncommitted | xradio arm all `match`; xarray-ms arm `refused` |
| 04 | `3fd8d97` (committed) | identical to 03; the receipt |

Neither harness fix touches the tolerance, the mapping or the case list;
both make it do what section 4 says. The conversions ran from a copy of the
harness taken before `3fd8d97`; its `make-gaps` and `convert` code is the
committed code apart from formatting and lint fixes.

**Skip path:** with xarray and zarr blocked by an import hook, the 6 tests of
`tests/test_msv4.py` skip ("the [msv4] extra is absent").

**Receipt:** [`results/msv4-interop.json`](results/msv4-interop.json) (run
04: per case and arm the measures, partitions, pads, `DATA_DESC_ID` mapping,
weight source, time fallbacks, versions, commit). Stores and logs:
`D:\rang\outputs\msv4-20261116` (`ps/xradio`, `ps/xms`, `convert.json`,
`convert-01.log`).

**xradio 1.3.1 arm: every measure of every case matches, bit for bit.**

| case | MSv2 rows | partitions | pads dropped | weights compared with |
| --- | ---: | ---: | ---: | --- |
| c1 to c4 (fixture scans 1, 4, 5, 8) | 20 each | 1 | 0 | `WEIGHT_SPECTRUM` |
| c5 (fixture scan 9) | 140 | 1 | 0 | `WEIGHT_SPECTRUM` |
| c6 (`A-casa.ms`) | 12480 | 4 | 0 | `WEIGHT_SPECTRUM` |
| c7 (`M1-casa.ms`) | 192 | 1 | 0 | `WEIGHT_SPECTRUM` |
| c8 (c5 less 4 rows) | 136 | 1 | 4 | `WEIGHT_SPECTRUM` |
| c9 (`m05`, two windows) | 36 | 2 | 0 | `WEIGHT_SPECTRUM` |

- `DATA`, `FLAG`, `WEIGHT_SPECTRUM` and `UVW`: same dtype, shape and bytes on
  all 13,064 rows.
- `TIME`: exact on every row (`time + 3506716800.0`); the 1 ms fallback was
  used 0 times.
- Coverage: every MSv2 row maps to one loader row and back. In c8 the reader
  dropped exactly the 4 pads xradio wrote for the removed rows, and invented
  no row.
- Partitions: c6 became 4 partitions, one per field (2 to 10 scans each),
  and c9's two windows two; each mapped to one `DATA_DESC_ID`. No case had
  its channels reordered.
- The "antenna names" measure is not independent: rows are mapped by name,
  so it is implied by the coverage.
- Under the frozen rule this is **pass**.

**xarray-ms 0.5.14 arm: refused in all 9 cases.** Its stores hold `FLAG` as
uint8, and section 3 refuses a `FLAG` other than bool. This is the same
representation as arcae's booleans in the first part (uint8 0 and 1). It was
not predicted. No xarray-ms value was compared, so the arm says nothing about
xarray-ms's values, and nothing in it is booked as an oracle disagreement.
It contradicts section 3's claim that the same code reads an xarray-ms tree:
as frozen, it does not, for any of these cases. Under M1 more differences may
sit behind the dtype (xarray-ms pads `FLAG` with 1, which section 3's pad
rule already ignores).
Converting xarray-ms's tree with `to_zarr` worked in all 9 cases (3-12 s).

**Cost** (no claim): xradio conversion 3.2-4.3 s per case and 11.6 s for
c6; xarray-ms 3.0-11.8 s. The whole WSL job took 6 min 51 s, mostly the
lock queue; its peak RSS was 689 MB. The native check of all 9 cases × 2
arms took 9 s including the start-up, and c6's xradio arm 0.4 s.

**Not covered** (as section 4 said; 2026-11-16: M3 below covers `FLAG_ROW`,
`CORRECTED_DATA`, `SIGMA` weights, `WEIGHT` repeated, non-base groups and
decreasing frequencies; still not covered: unwritten `WEIGHT_SPECTRUM`
cells, negative channel widths, other schema versions, other telescopes): `FLAG_ROW` set, `CORRECTED_DATA`,
weights from `SIGMA`, unwritten `WEIGHT_SPECTRUM`, decreasing channel
frequencies, schema versions other than 4.0.1, and LOFAR or other telescopes.
Also not covered (added 2026-11-16, after the run): the `WEIGHT`-repeated
comparison (every case had a written `WEIGHT_SPECTRUM`), and every data
group but `base`. c6 and c7 carry a `model` group from `MODEL_DATA`, which
nothing read, so c6's "second data column" reason in section 4 was not
exercised.
Throughput, Rust `zarrs`, object storage and writing were not attempted.

**Found on the way, no MSv4 fault:** python-casacore 3.8.1 can leave
`table.dat` with 0 rows and the true count in `table.lock`'s sync record;
ra-ng's reader reads it there (`lock_sync_rows`, `core/src/ms.rs`). A copy
without `table.lock` reads as 0 rows. The test fixture `m05.zip` therefore
keeps `table.lock`.

### M1 run (2026-11-16, under section 9)

Status: **measured, M1 not met; booked a writer difference.** The xradio arm
is still all `match`; the xarray-ms arm matches in c6, c7 and c9 and
mismatches in the six cases that hold autocorrelations, because xarray-ms
0.5.14 does not write them.

| run | code | outcome |
| --- | --- | --- |
| 05 | `7d82e46` (committed; amendment `8a93cfa` before it) | xradio: 9 of 9 `match`; xarray-ms: c6, c7, c9 `match`, c1 to c5 and c8 `mismatch` (coverage); the receipt |
| 06 | diagnosis `results/msv4-interop/m1_diag_autos.py`, same code | not a measure (post hoc): xarray-ms arm against the MSv2 with its autocorrelation rows removed, all 9 `match`. A first run 06 from an uncommitted copy of the same script, before lint and formatting, gave the same result; its output was not kept |

A first launch of run 05 failed before the harness started (`heavy_lock`
could not spawn a relative interpreter path); nothing was read. Checks on
Windows, worktree `.venv` (Python 3.13.16, xarray 2026.9.0, zarr 3.4.2,
numcodecs 0.17.1), `heavy_lock run --slots 1 --mem 4`, 9 s each. Stores:
those of `convert-01`, unchanged.

**Receipts:** [`results/msv4-interop-m1.json`](results/msv4-interop-m1.json)
(run 05, the format of run 04) and
[`results/msv4-interop-m1-diag.json`](results/msv4-interop-m1-diag.json)
(run 06).

**xarray-ms 0.5.14 arm, run 05:**

| case | MSv2 rows | of which autocorrelations | xarray-ms rows read | outcome |
| --- | ---: | ---: | ---: | --- |
| c1 to c4 | 20 each | 8 each | 12 each | `mismatch` (coverage: 8 MSv2 rows unmapped) |
| c5 | 140 | 56 | 84 | `mismatch` (56 unmapped) |
| c6 | 12480 | 0 | 12480 | `match` |
| c7 | 192 | 0 | 192 | `match` |
| c8 | 136 | 55 | 81 (3 pads dropped) | `mismatch` (55 unmapped) |
| c9 | 36 | 0 | 36 | `match` |

- The uint8 `FLAG` holds only 0 and 1 in every case: no read was refused.
- c6, c7, c9: `DATA`, `FLAG`, `WEIGHT_SPECTRUM`, `UVW` bit-identical,
  `TIME` exact (no 1 ms fallback), coverage exact, on 12,708 rows.
- c1 to c5 and c8: every store has 6 baselines for 4 antennas and none of
  them an autocorrelation. xarray-ms's MSv2 backend takes `auto_corrs`,
  default `False` (`xarray_ms/backend/msv2/entrypoint.py`), and the arm
  used the defaults (section 4). The harness books every measure of a case
  `mismatch` when coverage fails, so these six cases say nothing per column
  in the receipt.
- In run 06, with the autocorrelation rows taken out of the reference,
  every measure of all 9 cases matches: 12,921 rows bit-identical, coverage
  exact. In c8 xarray-ms wrote 3 pads (the 3 removed cross-correlation
  cells; xradio wrote 4, the fourth for the removed autocorrelation), and
  the reader dropped exactly those.
- Under section 9 this is **M1 not met**. Under section 6 it is a writer
  difference: for the six cases the reader matches the MSv2 for xradio's
  store, and xarray-ms's store lacks the MSv2's autocorrelation rows. The
  reader read every row xarray-ms wrote bit for bit. No reader change
  followed.

**Other writer differences** (recorded, not measures, nothing claimed):
`schema_version` 4.0.0 against xradio's 4.0.1; partitions
`<ms>_partition_<nnn>` against `<ms>_<n>`; `field_name` without xradio's
`_<id>` suffix, so `FIELD_NAME` rows differ between the writers; an extra
`SIGMA_SPECTRUM`; no `pointing_xds`; no autocorrelations by default; `FLAG`
pads 1 against false.

### M1b run (2026-11-16, under section 10)

Status: **measured, M1b pass.** With `auto_corrs=True` the xarray-ms 0.5.14
arm matches in every measure of all 9 cases; the `xradio` arm is still all
`match` and the `xms` arm is as in run 05.

| run | code | outcome |
| --- | --- | --- |
| conversion `convert-02` | harness `4d72bb4` (amendment `2de2199` before it), WSL, `heavy_lock run --slots 2 --mem 4`, `convert ROOT --arms xms-auto` | 9 of 9 written, 3.0-4.0 s each, 12.2 s for c6; 42 s wall, peak RSS 890 MB |
| 07 | `4d72bb4`, Windows worktree `.venv` (Python 3.13.16), `heavy_lock run --slots 1 --mem 4` | `xradio` 9/9 `match`; `xms` c6, c7, c9 `match`, the rest `mismatch` (as run 05); `xms-auto` 9/9 `match`; the receipt |

**Receipt:** [`results/msv4-interop-m1b.json`](results/msv4-interop-m1b.json)
(run 07, three arms). Stores: `D:\rang\outputs\msv4-20261116\ps\xms-auto`;
`convert-02.log`; entries `<case>/xms-auto` in `convert.json`.

**`xms-auto` arm, run 07:**

| case | MSv2 rows | rows read | pads dropped | outcome |
| --- | ---: | ---: | ---: | --- |
| c1 to c4 | 20 each | 20 each | 0 | `match` |
| c5 | 140 | 140 | 0 | `match` |
| c6 | 12480 | 12480 | 1664 | `match` |
| c7 | 192 | 192 | 128 | `match` |
| c8 | 136 | 136 | 4 | `match` |
| c9 | 36 | 36 | 24 | `match` |

- `DATA`, `FLAG` (uint8 0/1, read as bool), `WEIGHT_SPECTRUM` and `UVW`
  bit-identical on all 13,064 rows; `TIME` exact (no 1 ms fallback);
  coverage exact.
- With `auto_corrs=True` xarray-ms lays out the autocorrelation baselines
  whether or not the MS has them. c6, c7 and c9 have none, so their
  autocorrelation cells are pads (c6: 16 antennas × 104 times; c7: 4 × 32;
  c9: 4 × 3 in each of two windows), and the reader dropped exactly those.
  c8's 4 pads are the 4 removed rows, as in the xradio arm.
- Under section 10 this is **M1b pass**: `rang.msv4` reads xarray-ms
  0.5.14 trees of these 9 cases bit for bit when xarray-ms is asked for
  autocorrelations. With xarray-ms's default (`auto_corrs=False`) the
  autocorrelation rows are missing from the store (M1, as booked).

### M3 run (2026-11-16, under section 11)

Status: **measured, M3 not met on c10 (a writer outcome); c11 to c14
pass.** Neither writer carries `FLAG_ROW` into the store. Every other
uncovered path reads bit for bit in both arms. No reader outcome, no reader
change.

| run | code | outcome |
| --- | --- | --- |
| build | harness `72f2186` (amendment `6a6e5f4` before it), WSL, `heavy_lock run --slots 1 --mem 4`, `make-m3` | c10 to c14 written, 17 s; each read by `rang.core_ms` before conversion (140 rows each) |
| conversion `convert-03` | `72f2186`, WSL, `heavy_lock run --slots 2 --mem 4`, `convert-m3` | 10 of 10 written (xradio 3.6-5.6 s, xms-auto 3.3-6.2 s); 52 s run, 193 s with the lock wait, peak RSS 512 MB |
| 08 | `72f2186`, Windows worktree `.venv` (Python 3.13.16), `heavy_lock run --slots 1 --mem 4`, `check-m3` | control: c1 to c9 equal run 07 in both arms; c10 base `mismatch` on `FLAG` with `FLAG_ROW` in both arms; c11 to c14 every group `match` in both arms; the receipt |

**Receipt:** [`results/msv4-interop-m3.json`](results/msv4-interop-m3.json)
(run 08). Cases `D:\rang\outputs\msv4-20261116\ms\c10-*.ms` to `c14-*.ms`;
stores under `ps/xradio` and `ps/xms-auto`; `convert-03.log`.

| case | groups in both stores | data, `FLAG` cells, `UVW`, `TIME`, coverage | `FLAG` with `FLAG_ROW` | weights (xradio; xms-auto) | outcome |
| --- | --- | --- | --- | --- | --- |
| c10 `FLAG_ROW` on 28 rows | base | match | **mismatch** in both arms | base W; W | not met, writer outcome |
| c11 `CORRECTED_DATA`, `MODEL_DATA`, `SIGMA_SPECTRUM` with 0, NaN, -1 | base, corrected, model | match | match | base **S**, corrected W, model W; all W | match |
| c12 as c11, `SIGMA` only | base, corrected, model | match | match | base **S**, corrected W, model W; all W | match |
| c13 no `WEIGHT_SPECTRUM`, `SIGMA_SPECTRUM` | base | match | match | W and S (equal here); same | match |
| c14 decreasing frequencies | base | match | match | W; W | match |

- **c10:** in both stores `FLAG` equals the MSv2 `FLAG` cells bit for bit,
  and the 28 row flags are gone; no data variable holds them (xradio:
  `EFFECTIVE_INTEGRATION_TIME`, `FLAG`, `TIME_CENTROID`, `UVW`,
  `VISIBILITY`, `WEIGHT`; xarray-ms the same plus `SIGMA_SPECTRUM`; read
  directly from the stores). The receipt books the group `mismatch`; the
  writer-outcome booking is this note's, resting on `FLAG cells` being
  `match`: a writer outcome (xradio 1.3.1 and
  xarray-ms 0.5.14 alike), as the probe suggested. `rang.msv4` cannot
  recover them, and its `FLAG_ROW` (false) is then true to the store but not
  to the MSv2. A consumer that needs row flags must OR them in before
  conversion. Under section 11 this is **M3 not met** on c10.
- **Weights with `CORRECTED_DATA` (c11, c12):** xradio's base group carries
  S (`1/SIGMA^2`, 0 for the invalid 0, NaN and -1 sigmas), bit for bit with
  section 11's formula, and its corrected group W; xarray-ms gives every
  group W. Both match a frozen candidate, so both are `match`. The
  consequence: a stage fed xradio's base group gets `1/SIGMA^2` weights,
  where ra-ng's MSv2 path weights `DATA` with `WEIGHT_SPECTRUM`; the two
  differ in these cases. Measured on the references (post hoc, not a
  frozen measure): W and S differ on 1,070,235 of 2,293,760 cells in c11 (as
  in c5: `WEIGHT_SPECTRUM` is not `1/SIGMA_SPECTRUM^2` there) and on all
  2,293,760 in c12; in c13 the per-row `WEIGHT` and `SIGMA` agree, so W
  equals S.
- **Non-base groups (c11, c12):** `corrected` and `model` are complete in
  both stores and read bit for bit against `CORRECTED_DATA` and
  `MODEL_DATA`.
- **`WEIGHT` repeated (c13):** both writers repeat `WEIGHT` over channels;
  bit-identical.
- **Decreasing frequencies (c14):** xradio stores the channels ascending
  (sorted), xarray-ms keeps them descending (read directly from the stores,
  not in the receipt); the reversed `CHAN_WIDTH` is a constant positive
  array, so negative widths are not covered; with section 4's mapping by
  frequency both are bit-identical. The reader yields the store's order, so
  the two stores give rows in opposite channel order.
- **Control:** c1 to c9, both arms, every measure equal to run 07.

### M2 run (2026-11-16, under section 11)

Status: **measured, M2 pass.**

| run | code | outcome |
| --- | --- | --- |
| 09 | `72f2186`, Windows worktree `.venv`, `heavy_lock run --slots 4 --mem 8`, `m2` | MSv2 side: the stage on two copies of c5, identical `FLAG` (sha256 `50846c21...`); xradio and xms-auto: kernel fed from `Partition.chunks(time_rows=4)` (4 chunks), `FLAG` identical on every cell, no metadata fallback; the receipt |

**Receipt:** [`results/msv4-interop-m2.json`](results/msv4-interop-m2.json)
(run 09). MSv2 copies `D:\rang\outputs\msv4-20261116\m2\c5-copy-a.ms`, `-b.ms`.

- Strategy CARACAL calibrator firstpass (sha256 `ce9ac66a...`, as frozen);
  `column="DATA"`, the two shipped static masks.
- The stage raised c5's flagged cells from 1,074,094 to 1,849,716 of
  2,293,760 (46.8 % to 80.6 %), so the identity is not vacuous.
- MSv4 side, both arms: 140 rows, 0 pads, antenna positions, channel
  frequencies and widths and correlation codes from the store equal the
  MSv2's bit for bit; final `FLAG` equal to the stage's on all 140 rows, 0
  differing cells.
- Wording as frozen: the reader's rows give the flag stage's flags; the
  stage itself still reads only an MSv2. No weight or `UVW` is exercised;
  c5 is one field/scan group; nothing about calibration or imaging.
- c5's MS was not touched by the stage: no file under it is newer than
  `convert-03.log` (checked after run 09).
- Cost (no claim): stage 0.5-0.6 s per copy; kernel 0.19 s (xradio), 0.22 s
  (xms-auto); the whole run 5 s.

## 8. Next steps (proposed; M1, M1b, M2 and M3 done)

- **M1** (done 2026-11-16: section 9 amendment, section 7 M1 run; not met,
  a writer difference, xarray-ms drops autocorrelations by default): accept xarray-ms's uint8 `FLAG` when every value is 0 or 1 (as the
  edge-case harness does for arcae), frozen as an amendment, and rerun the
  xarray-ms arm.
- **M1b** (done 2026-11-16: section 10 amendment, section 7 M1b run;
  pass, 9/9 bit-identical): rerun the xarray-ms arm with `auto_corrs=True`, a change to the
  frozen arm of section 4, so a dated amendment first; it needs the WSL
  oracle venv for the conversions.
- **M2** (done 2026-11-16: section 11, section 7 M2 run; pass): feed `Partition.chunks` to one stage (flag or image) and require
  the stage's products to be bit-identical to the same stage on the MSv2:
  the issue's gate "identical calibration and imaging results".
- **M3** (done 2026-11-16: section 11, section 7 M3 run; not met on
  `FLAG_ROW`, a writer outcome, c11 to c14 pass): cases for the uncovered paths above (`FLAG_ROW`, `CORRECTED_DATA`,
  `SIGMA` weights, decreasing frequencies).
- **M4 (proposed, not started; owner decision):** row flags lost in
  conversion. Neither writer keeps `FLAG_ROW` (M3, c10). Options: document
  that `FLAG_ROW` must be OR'd into `FLAG` before conversion, or ask the
  writers' maintainers; ra-ng's reader cannot recover it.
- **M5 (proposed, not started; owner decision):** the base-weight
  convention. With `CORRECTED_DATA`, xradio's base group carries
  `1/SIGMA^2`, xarray-ms's `WEIGHT_SPECTRUM` (M3, c11 and c12). A weighted
  stage fed xradio's base group on such an MS cannot match ra-ng's MSv2
  path, which weights `DATA` with `WEIGHT_SPECTRUM`; this bears on the
  issue's gate "identical calibration and imaging results". Decide which
  weight a weighted stage takes per data group before an M2-like gate for
  calibration or imaging.
- **Coordinator decisions, 2026-11-16 (owner delegated):**
  - M4: document, do not ask upstream (xradio is NRAO's; standing rule: no
    reports to CASA or NRAO). Done in the merge: `rang.msv4`'s docstring
    says to OR `FLAG_ROW` into `FLAG` before converting to MSv4.
  - M5: until it is settled, no weighted stage takes MSv4 input on an MS
    with `CORRECTED_DATA`; the MSv4 path stays read-and-flag only. Settling
    it (which weight each data group takes, measured against the MSv2 path)
    is a later task, with its own amendment.
- **Later, per the issue:** a Rust `zarrs` reader behind the same layout,
  then throughput, object storage and per-chunk writes; each with its own
  note.

## 9. Amendment M1: uint8 `FLAG` (2026-11-16, post hoc)

Written and committed before the code that implements it. It is post hoc to
sections 3 and 6: it changes the scope after the run of section 7 showed the
refusal. Sections 3, 4 and 6 stay as frozen; this section overrides one
refusal of section 3 and adds a rule for the xarray-ms arm.

**Probe before this amendment.** The xarray-ms stores of `convert-01`
(c5, c6, c9) were opened with xarray in the main checkout's venv and their
layout read: `FLAG` is uint8 with dimensions `GRID`; c5's `FLAG` holds only
the values 0 and 1; `schema_version` is 4.0.0 (xradio 4.0.1); partitions are
named `<ms>_partition_<nnn>` (xradio `<ms>_<n>`); `field_name` has no `_<id>`
suffix (xradio `J1939-6342_0`, xarray-ms `J1939-6342`); xarray-ms adds a
`SIGMA_SPECTRUM` variable and writes no `pointing_xds`. The partitions of c6
and c9 have the same sizes, fields' scans and antenna names in both arms. No
xarray-ms value was compared with the MSv2.

**Scope change (frozen here).**

- A `FLAG` of dtype uint8 is accepted; bool is accepted as before; every
  other dtype (int8, uint16, float, ...) is still refused at
  `Partition(...)`.
- A uint8 `FLAG` is read as `flag != 0` after a value check: if any cell
  read holds a value other than 0 or 1, the read is refused
  (`ValueError`, naming the partition and the values). The check covers
  every cell of the times read, pads included (xarray-ms pads `FLAG` with 1).
- The check can only run when values are read, so it runs in
  `Partition.rows()` (and so in `chunks()`), not when the partition is
  opened: a bad value in a later chunk is refused only when that chunk is
  read. The harness books such a refusal as `refused` for the partition.
- The output `FLAG` stays bool, `(row, channel, corr)`; nothing else in the
  layout of section 3 changes. The pad rule is unchanged.

**Cases, mapping, tolerance:** those of section 4, unchanged. Bit-identical,
no tolerance. The stores are those of `convert-01`
(`D:\rang\outputs\msv4-20261116\ps`), not rewritten; no file under `ps/`
is newer than `convert.json` (checked before this amendment).

**Decision rule for M1 (frozen here).** The check of section 4 is run again
over all 9 cases and both arms, on the committed code, with a new receipt
`results/msv4-interop-m1.json`; runs are numbered from 05.

- The xradio arm must still be all `match` in the same run; otherwise the
  change broke the reader and M1 fails whatever the xarray-ms arm shows.
- **M1 pass:** every measure of every case in the xarray-ms arm is `match`.
  Then section 3's claim that the same code reads an xarray-ms tree holds
  for these cases.
- **M1 partial or fail:** any xarray-ms measure `refused` or `mismatch`. The
  column that differs is found (for example by comparing the two stores
  directly) and booked under section 6: where the reader matches the MSv2
  for the xradio store and not for the xarray-ms store, it is a writer
  difference, not a reader outcome. The reader is not changed further
  without a second dated amendment written before that code.
- The differences listed under the probe are not measures; they are
  recorded, and nothing is claimed about them.

## 10. Amendment M1b: xarray-ms with `auto_corrs=True` (2026-11-16, post hoc)

Written and committed before any new conversion; approved by the
coordinator (owner delegated). It is post hoc to section 4: it adds a writer
setting after the M1 run showed that xarray-ms's default leaves out the
autocorrelations. The M1 result (section 7, "M1 run") stays as booked.
Sections 3, 4, 6 and 9 stay as frozen; the reader is not changed.

**Known before this amendment:** `xarray_ms/backend/msv2/entrypoint.py`
(0.5.14) takes `auto_corrs: bool = False` in `open_dataset` and
`open_datatree`; the M1 diagnosis (run 06) matched all 9 cases on their
cross-correlation rows. No store written with `auto_corrs=True` has been
opened or compared.

**New arm `xms-auto` (frozen here):** in the same oracle venv (xarray-ms
0.5.14, xarray 2026.9.0, WSL), `xarray.open_datatree(ms,
engine="xarray-ms:msv2", auto_corrs=True)`, then `to_zarr(out)`, all else
default. Stores under `D:\rang\outputs\msv4-20261116\ps\xms-auto`; the
`xradio` and `xms` stores of `convert-01` are not rewritten. The conversion
runs from the committed harness (`convert ROOT --arms xms-auto`) under
`heavy_lock`, log `convert-02.log`, entries `<case>/xms-auto` added to
`convert.json`.

**Cases, mapping, tolerance, reader:** those of sections 4 and 9,
unchanged: the same 9 cases, bit-identical, no tolerance, `rang.msv4` as
merged at `6909a31`.

**Decision rule for M1b (frozen here):** the check of section 4 over all
9 cases and the three arms `xradio`, `xms` and `xms-auto`, on the committed
code, receipt `results/msv4-interop-m1b.json`, runs numbered from 07.

- The `xradio` arm must still be all `match` and the `xms` arm as in run 05
  (c6, c7, c9 `match`, the rest `mismatch`); otherwise something other than
  the setting changed, and M1b is void until found.
- **M1b pass:** every measure of every case in the `xms-auto` arm is
  `match`. Then section 3's claim that the same code reads an xarray-ms
  tree holds for these 9 cases when xarray-ms is asked for
  autocorrelations.
- **M1b not met:** any `xms-auto` measure `refused`, `writer fails` or
  `mismatch`. The column that differs is found and booked under section 6
  (writer difference or reader outcome); no reader change without another
  dated amendment written before that code.

## 11. Amendment M3 and M2 (2026-11-16, post hoc)

Written and committed before any code or conversion of M3 or M2; approved
by the coordinator (owner delegated). It is post hoc to sections 3, 4 and 6:
it adds cases and a stage gate after the runs of section 7. Sections 3 to
10 stay as frozen, and their results stay as booked. **`python/rang/msv4.py`
is not changed in this task:** whatever it does not support is refused and
booked, not widened.

**Probe before this amendment.** Read, not run: xradio 1.3.1's
`_utils/_msv2/conversion.py` (with `CORRECTED_DATA`, the MSv2 weights give
`WEIGHT_CORRECTED` and SIGMA gives the base `WEIGHT` through
`sigma_to_weight`, `1/(s*s)` where `s` is finite and positive, else 0;
`SIGMA_SPECTRUM` first, `SIGMA` as fallback; `WEIGHT` when
`WEIGHT_SPECTRUM` is absent) and `create_antenna_xds.py` (the only xradio
file that names `FLAG_ROW` besides a test helper); xarray-ms 0.5.14's
`backend/msv2/factories/correlated.py` and `entrypoint.py` (`FLAG` from
`FLAG`, from `FLAG_ROW` only when `FLAG` is absent; `WEIGHT` from
`WEIGHT_SPECTRUM`, else `WEIGHT` per row; `SIGMA_SPECTRUM` kept as a
variable; data groups `base`, `corrected`, `model` from `DATA`,
`CORRECTED_DATA`, `MODEL_DATA`). From this reading neither writer appears
to carry `FLAG_ROW` into `FLAG` when `FLAG` exists, and the two writers
appear to give the base group different weights when `CORRECTED_DATA`
exists; neither is measured yet, and neither is claimed. ra-ng's MSv2
consumers treat `FLAG_ROW` as flagging every cell of the row
(`cal_gain.py`, `cal_pol.py`, `core_campaign*.py`). No M3 case or store has
been written, and no M2 stage run made.

### M3: cases for the uncovered paths (frozen)

**Cases** (built in WSL with python-casacore 3.8.1 in the oracle venv from
copies of c5, `table.lock` kept; each changes one thing; written to
`D:\rang\outputs\msv4-20261116\ms\`; each checked readable by
`rang.core_ms` before it is converted):

| id | from c5, change | path covered |
| --- | --- | --- |
| c10 | `FLAG_ROW` true on rows `r % 5 == 2` (28 of 140); `FLAG` unchanged | `FLAG_ROW` set |
| c11 | add `CORRECTED_DATA = DATA * complex64(0.5 - 0.25j)` and `MODEL_DATA = DATA * complex64(2)` (numpy complex64); in `SIGMA_SPECTRUM`, row 0 channel 0 correlation 0 set to 0, row 1 channel 1 correlation 1 to NaN, row 2 channel 2 correlation 2 to -1 | `CORRECTED_DATA`; the `corrected` and `model` data groups; SIGMA-derived weights from `SIGMA_SPECTRUM` with invalid values |
| c12 | c11 with `SIGMA_SPECTRUM` removed and `SIGMA` of row 3 correlation 0 set to 0 | SIGMA-derived weights from `SIGMA` |
| c13 | `WEIGHT_SPECTRUM` and `SIGMA_SPECTRUM` removed | the `WEIGHT`-repeated fallback |
| c14 | `CHAN_FREQ`, `CHAN_WIDTH`, `EFFECTIVE_BW` and `RESOLUTION` of the spectral window reversed along the channel axis | decreasing channel frequencies |

A case that cannot be built, or whose reference `rang.core_ms` cannot read,
is booked `not measured` with the reason; a writer that cannot convert it is
booked `writer fails`.

**Arms:** `xradio` (as section 4) and `xms-auto` (as section 10), conversion
log `convert-03.log`, entries in `convert.json`. The 9 cases c1 to c9 are
checked again in the same run as a control: their base-group measures must
equal run 07 in both arms, else the M3 run is void until the cause is
found.

**References, per data group** (zero tolerance, mapping of section 4):

- the group's correlated data: `base` against `DATA`, `corrected` against
  `CORRECTED_DATA`, `model` against `MODEL_DATA`; a group is selected by
  name;
- `FLAG`, two measures: `FLAG` against MSv2 `FLAG` (cells), and `FLAG`
  against `FLAG | FLAG_ROW` (row flag over every cell). The second decides,
  as ra-ng's MSv2 consumers read it;
- weights, two candidate references: **W**, `WEIGHT_SPECTRUM` (or `WEIGHT`
  repeated over channels when that column is absent, as section 4), and
  **S**, `1/(s*s)` in float32 where `s` is finite and `> 0`, else 0, for
  `s` = `SIGMA_SPECTRUM` (or `SIGMA` repeated when that column is absent).
  Deciding: the `corrected` group against W; the `base` group against W
  when the MS has no `CORRECTED_DATA`. The `base` group of an MS with
  `CORRECTED_DATA`, and the `model` group, match when they equal W or S
  bit for bit, and which one is booked. The consequence is recorded either
  way: ra-ng's MSv2 path weights every column with `WEIGHT_SPECTRUM`;
- `UVW` and `TIME` as section 4, and coverage.

**Bookings.** A data group the MS implies (`CORRECTED_DATA` gives
`corrected`, `MODEL_DATA` gives `model`) that the store lacks, or that
lacks a role (`correlated_data`, `flag`, `weight`, `uvw`), is a writer
outcome. A complete group that `rang.msv4` refuses is a reader outcome.

**M3 rule.** The `xradio` arm decides, `xms-auto` is reported (section 6).

- **M3 pass:** every deciding measure of every data group of c10 to c14
  matches in the `xradio` arm.
- **M3 not met:** any deciding measure does not. Each miss is booked as a
  writer outcome (the store lacks what the MSv2 holds, for example the row
  flag) or a reader outcome (the store holds it and the reader misreads or
  refuses it). A reader outcome becomes a task; the reader is not changed
  here.

### M2: the flag stage fed from MSv4 (frozen)

**Stage:** `rang.cal_chain.flag_corrected` (the Tricolour port, C1's O1),
`column="DATA"`, all fields, default masks (the two shipped static masks),
strategy CARACAL's `mk_rfi_flagging_calibrator_fields_firstpass.yaml` from
`outputs/caracal-strategy-inputs-8f7bb363` (sha256
`ce9ac66aba75c62e778eabbc951e8f9760447f7824f8fd37b26b91974ec71774`),
parsed by `core_flag.parse_strategy`.

**Case:** c5 (fixture scan 9, one field, one scan, one window; 140 rows,
4096 channels, autocorrelations).

**MSv2 side:** the stage itself on two fresh copies of c5's MS (never on a
case MS: the stage writes `FLAG`), under
`D:\rang\outputs\msv4-20261116\m2\`; `FLAG` read back from each copy with
`rang.core_ms`. The two copies must give identical `FLAG` (determinism).

**MSv4 side:** an adapter in the harness, since the stage reads only an
MSv2: the rows of the `base` group from `Partition.chunks(time_rows=4)`,
concatenated in the order the reader yields them (the stage needs the
group's whole time grid), into `core_flag.flag_rows` with the stage's
arguments (`want_intensity=False`, `want_stages=False`), and
`FLAG | flags` as the stage writes it. Metadata from the store: antenna
positions (`antenna_xds.ANTENNA_POSITION`, in `antenna_name` order),
`frequency` and its `channel_width`, and the correlation codes of the
`polarization` names (`XX` 9 to `YY` 12). Each is compared with the MSv2's
(`ANTENNA::POSITION`, `CHAN_FREQ`, `CHAN_WIDTH`, `CORR_TYPE`) bit for bit;
one that differs is replaced by the MSv2's and booked as a labelled
fallback.

**Arms:** the `xradio` store of c5 decides; the `xms-auto` store is
reported.

**M2 rule.** Rows mapped by key (section 4).

- **M2 pass:** the MSv4 side's `FLAG` equals the MSv2 side's on every row
  and cell, bit for bit, with no metadata fallback; the two MSv2 copies
  agree; and the stage adds flags (`FLAG` after has more set cells than
  before), so the identity is not vacuous.
- **M2 partial:** the same with a metadata fallback.
- **M2 fail:** any other outcome.
- **Wording:** the MSv2 side is the stage; the MSv4 side feeds the stage's
  kernel through an adapter. A pass says the reader's rows give the stage's
  flags, not that the stage reads MSv4.
- **Not claimed:** the flag stage reads no weight or `UVW`; c5 is one
  group; nothing about imaging or calibration.

## For the coordinator

M2 and M3 (branch `msv4-m2`): amendment `6a6e5f4` (section 11, before any
code or conversion), harness `72f2186` (`msv4_m3m2.py`), records after.
M3 (run 08): c11 to c14 bit-identical in every data group, both arms;
c10's `FLAG_ROW` is dropped by both writers (writer outcome, M3 not met
there); control c1 to c9 equal run 07. xradio's base weights with
`CORRECTED_DATA` are `1/SIGMA^2`, not `WEIGHT_SPECTRUM`. M2 (run 09): the
flag stage's `FLAG` on c5 equals its kernel fed from both stores on every
cell, metadata from the store: **pass**. Reader unchanged. The WSL oracle
venv is removed (no named step needs it).

M1b (branch `msv4-m1b`): amendment `2de2199` (section 10, before any
conversion), harness `4d72bb4` (arm `xms-auto`, `--arms`), records after.
Run 07: `xms-auto` 9/9 `match` on 13,064 rows, `xradio` 9/9, `xms` as run
05: **M1b pass**. The reader is unchanged. The WSL oracle venv is kept for
M3 (new cases need conversions).

M1 (branch `msv4-m1`): amendment `8a93cfa` (section 9, before the code),
code `7d82e46`, records after. uint8 `FLAG` of 0/1 is read as bool, other
values refused on read. Run 05: xradio arm still 9/9 `match`; xarray-ms arm
3/9 `match`, the 6 cases with autocorrelations `mismatch` because
xarray-ms defaults to `auto_corrs=False` (writer difference; the cross rows
match in all 9, run 06). M1b proposed. The WSL oracle venv is kept for M1b
and M3.

First part (branch `msv4-interop`):

- Branch `msv4-interop`: note `7ebf6ed` (frozen first), code `3fd8d97`,
  records after. Outcome under the frozen rule: **pass** on the xradio arm,
  xarray-ms arm refused (uint8 `FLAG`, task M1).
- New optional extra `msv4` (xarray, zarr 3, numcodecs; Python 3.11 and
  later), added to the CI and `check_all.py` extras. The core install is
  unchanged. No CLI change, no new `RANG_*` variable.
- The oracle venv was in WSL (`~/Build/tmp/20261116-msv4-oracle`); removed
  2026-11-16 after M2 and M3 (its versions are in section 4 and 10 if it
  must be rebuilt).
- `tools/check_all.py` installs extras only into a new `.venv`: the main
  checkout's `.venv` needs `uv pip install xarray "zarr>=3,<4" numcodecs` (or
  `--extra msv4`) or the merge check skips `tests/test_msv4.py`.
- The extra is unpinned (lower bounds only), so a later xarray or zarr release
  can change CI on main.
