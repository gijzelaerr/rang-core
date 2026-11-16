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
refused by the frozen scope.

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

**Not covered** (as section 4 said): `FLAG_ROW` set, `CORRECTED_DATA`,
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

## 8. Next steps (proposed, not started)

- **M1:** accept xarray-ms's uint8 `FLAG` when every value is 0 or 1 (as the
  edge-case harness does for arcae), frozen as an amendment, and rerun the
  xarray-ms arm.
- **M2:** feed `Partition.chunks` to one stage (flag or image) and require
  the stage's products to be bit-identical to the same stage on the MSv2:
  the issue's gate "identical calibration and imaging results".
- **M3:** cases for the uncovered paths above (`FLAG_ROW`, `CORRECTED_DATA`,
  `SIGMA` weights, decreasing frequencies).
- **Later, per the issue:** a Rust `zarrs` reader behind the same layout,
  then throughput, object storage and per-chunk writes; each with its own
  note.

## For the coordinator

- Branch `msv4-interop`: note `7ebf6ed` (frozen first), code `3fd8d97`,
  records after. Outcome under the frozen rule: **pass** on the xradio arm,
  xarray-ms arm refused (uint8 `FLAG`, task M1).
- New optional extra `msv4` (xarray, zarr 3, numcodecs; Python 3.11 and
  later), added to the CI and `check_all.py` extras. The core install is
  unchanged. No CLI change, no new `RANG_*` variable.
- The oracle venv is in WSL (`~/Build/tmp/20261116-msv4-oracle`); kept for
  M1, remove it once M1 is done or dropped.
- `tools/check_all.py` installs extras only into a new `.venv`: the main
  checkout's `.venv` needs `uv pip install xarray "zarr>=3,<4" numcodecs` (or
  `--extra msv4`) or the merge check skips `tests/test_msv4.py`.
- The extra is unpinned (lower bounds only), so a later xarray or zarr release
  can change CI on main.
