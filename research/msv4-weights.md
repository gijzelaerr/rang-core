# MSv4 weights: which weight a weighted stage takes from a store (M5)

2026-11-28, branch `msv4-m5`, gijzelaerr/rang-core issue #5 step M5 (the
read path is [msv4-interop.md](msv4-interop.md), whose section 8 proposed
M5; the flag stage on a store is [msv4-flag-write.md](msv4-flag-write.md)
and [msv4-cli.md](msv4-cli.md)). Status: **proposed, frozen**. Sections 1
to 6 are frozen in the commit that adds this note, before any code. No
frozen M5 criterion existed before today: msv4-interop.md listed M5 as
"proposed, not started", and the coordinator's ruling of 2026-11-16 left
settling it to "a later task, with its own amendment"; this note is that.
Later changes are dated and labelled post hoc. No performance or science
claim: the step checks that a weighted solve fed from a store reads the
MSv2 path's weights and gives its gains bit for bit.

## 1. The step

With `CORRECTED_DATA` in the MS, xradio 1.3.1's base data group carries
`1/SIGMA^2` and its `corrected` group the MSv2 `WEIGHT_SPECTRUM`;
xarray-ms 0.5.14 gives every group `WEIGHT_SPECTRUM` (msv4-interop.md M3,
c11 and c12). ra-ng's MSv2 path weights every column it solves on with
`WEIGHT_SPECTRUM` (else `WEIGHT` repeated over channels), and solves with
`1/SIGMA^2` computed from `SIGMA_SPECTRUM` (else `SIGMA`) where tables are
pre-applied (`cal_gain`, `cal_bandpass`, `cal_delay`, `cal_pol`; research
c2a-gain.md section 6). Since 2026-11-16 no weighted stage takes a store.
This step fixes, per data group, which store variable stands for each of
those two MSv2 inputs, builds it into `rang.msv4`, and measures it against
the MSv2 path, inputs and one weighted solve.

## 2. Probe before the freeze (2026-11-28)

Read or run on the 2026-11-16 stores and MSs, nothing written:

- **Layouts.** xradio 1.3.1, MS with `CORRECTED_DATA` (c11, c12): groups
  `base` (weight `WEIGHT`), `corrected` (`WEIGHT_CORRECTED`), `model`
  (`WEIGHT_CORRECTED`); no sigma variable. Without it (c5, c13): one group,
  `WEIGHT`; no sigma variable. xarray-ms 0.5.14 (`auto_corrs`): every group
  names `WEIGHT`, and every store has `SIGMA_SPECTRUM`, also where the MS
  has only `SIGMA` (c12) or no `SIGMA_SPECTRUM` (c13). `creator.software_name`
  is `xradio` or `xarray-ms` on every partition.
- **Two sigma formulas.** The solver path (`cal_gain.py`, `cal_pol.py`)
  computes `1/sigma**2` in float64 and casts to float32; `applycal`'s calwt
  reset and xradio (M3) compute `1/(s*s)` in float32. On the MSs' sigma
  they differ by 1 ULP on 634,413 of 2,293,760 cells (c5), 634,411 (c11),
  532,480 (c12), 536,576 (c13); never by more. So xradio's base `WEIGHT`
  cannot stand in for the solver's sigma weights bit for bit.
- **W is not S.** On c5 `WEIGHT_SPECTRUM` differs from the solver's
  `1/SIGMA_SPECTRUM^2` on 1,028,508 cells (c11 1,028,509; c12 all
  2,293,760), so a solve that took the wrong one would differ (checked by
  measure W4, not assumed).
- **Row order.** The reader yields rows time-major in `baseline_id` order;
  `flag_sha256` differs from the MSv2's on every M7 case for that reason
  (msv4-cli.md section 9). `solve_partition` sorts rows stably by `TIME`
  and accumulates over rows, so a solve on the store's order may round
  differently; the deciding solve below feeds the rows in the MSv2 order.
- `RowSource.getcol_rows` answers only the data columns and `FLAG`;
  `core_tasks._run_solve` reads `DATA`, `WEIGHT_SPECTRUM` (or `WEIGHT`),
  `FLAG`, `FLAG_ROW` through it (`core_pipeline._solve_inputs`).

## 3. The rule and the piece built here (frozen)

**The convention.** A weighted stage on a store takes, for every data group
it reads data from, the weights the MSv2 path would read for that column:
**W** (the MSv2 `WEIGHT_SPECTRUM`, else `WEIGHT` repeated) as its weights,
and the MSv2 **sigma** (`SIGMA_SPECTRUM`, else `SIGMA` repeated) where it
resets weights from sigma. The data group's own weight variable is not used
as is; it is used only when the rule below says it is W.

**W of a partition** (`rang.msv4`, one variable per partition, all groups):

1. every data group names the same weight variable: that variable (xarray-ms;
   xradio without `CORRECTED_DATA`; any writer that keeps one weight);
2. the groups name different weight variables: only where the partition's
   `creator.software_name` is `xradio` and it has a `corrected` group, the
   `corrected` group's weight variable (xradio writes the MSv2
   `WEIGHT_SPECTRUM` there and `1/SIGMA^2` in the base group's);
3. otherwise W is refused (`ValueError` naming the partition, the writer
   and the groups' variables) when a weight is read.

**Sigma of a partition:** the variable `SIGMA_SPECTRUM` with dimensions
`(time, baseline_id, frequency, polarization)` and dtype float32, when the
partition has it; otherwise refused when read (`ValueError` naming the
partition and saying that the store keeps no sigma; xradio 1.3.1 writes
none, and its base `WEIGHT` is not substituted, section 2).

**Reader API:**

- `Partition.rows()`: `WEIGHT_SPECTRUM` is W (until now it was the group's
  own weight; for xradio's base group with `CORRECTED_DATA` that was
  `1/SIGMA^2`). The flag path does not read it (bytes of M6/M7 unchanged).
- `Partition.weight_variable` and `Partition.sigma_variable`: the names the
  rule picks, or None with the reason in `Partition.weight_refusal`.
- `RowSource.getcol_rows` also answers `WEIGHT_SPECTRUM` (W), `SIGMA_SPECTRUM`
  (sigma) and `FLAG_ROW` (false, as `rows()`); `WEIGHT` and `SIGMA` (MSv2
  per-row columns) are refused: on a store the spectral variables stand for
  them, so a stage on a store reads with `weight_spectrum` true.

**Not built:** calibrate, apply, image and selfcal on a store stay refused
(msv4-cli.md C7 unchanged); the refusal message keeps naming M5 and points
to this note. No pre-applied-table solve on a store (it needs `cal_gain`'s
MS reads). No new `RANG_*` variable, no CLI change.

## 4. Oracle and cases (frozen)

**Run root** `D:\rang\outputs\20261128-msv4-m5` (new). Inputs are copied into
it before any measurement (`inputs/ms/<case>.ms`, `inputs/ps/<arm>/<case>.ps.zarr`)
and only the copies are read:

| case | MS | stores (both arms) |
| --- | --- | --- |
| c1 to c5 | `msv4-20261116/fixture/outer_scans/` scans 1, 4, 5, 8, 9 | `msv4-20261116/ps/<arm>/` |
| c8 (gaps) | `msv4-20261116/ms/c8-scan9-gaps.ms` | same root |
| c11 to c14 | `msv4-20261116/ms/` | same root |
| c6x (4 fields, 4 partitions), c9 (two windows) | `msv4-next-20261125/ms-src/` | `msv4-next-20261125/ps/<arm>/<case>-before.ps.zarr` |

c10 (`FLAG_ROW`) is left out: both writers drop row flags (M4), which no
weight rule changes. c6 and c7: not measured (sources deleted). Arms
`xradio` (deciding) and `xms-auto` (reported), as in M3.

**Oracle:** ra-ng's MSv2 path on the copied MS through `rang.core_ms`: W as
msv4-interop.md section 4 (`WEIGHT_SPECTRUM`, else `WEIGHT` repeated);
sigma `SIGMA_SPECTRUM`, else `SIGMA` repeated; the solve
`core_pipeline.solve_partition(table, idx, info, term, "as_is", "unity",
None)`. Mapping of rows, channels and correlations: msv4-interop.md section
4 (the M3 harness's `_pick`), zero tolerance.

**Measures:**

- **W1, weights (deciding):** for every data group of every partition,
  `Partition.rows()["WEIGHT_SPECTRUM"]` and `RowSource.getcol_rows(
  "WEIGHT_SPECTRUM", ...)` equal the MSv2 W cell for cell, bit-identical,
  every case.
- **W2, sigma (deciding):** `xms-auto`: `getcol_rows("SIGMA_SPECTRUM")`
  equals the MSv2 sigma cell for cell, bit-identical, every case. `xradio`:
  the read is refused with `ValueError` on every case (asserted), nothing
  substituted.
- **W3, weighted solve (deciding):** on c5, c11, c12, c13 (one field, one
  partition each) and c14 (decreasing frequencies): `solve_partition` on the
  store's `RowSource` (base group), rows fed in the MSv2 row order (each MS
  row's store row by the mapping), store antenna names equal to the MS's
  (asserted), `info` with `weight_spectrum` true, term `solint: int`,
  `freqint: 256`, `max_iterations: 50`, `stop_criterion: 1e-7`,
  `stop_fraction: 0.99`: gains (`tobytes`), flags, iterations and converged
  fraction equal the MSv2 solve's. On c14 the channels are mapped back to
  the MS order before the solve (xradio sorts them).
- **W4, the test can fail (deciding for validity):** on c11 and c12, the W3
  solve with the xradio base group's own weight variable instead of W (the
  reader before this step) gives gains that differ from the W solve's
  bytes. If not, W3 is void on those cases.
- **Reported, no rule:** W3 with the store's own row order (max relative
  gain difference, equal or not); W1 on the old reading (group's own
  weight) for the record; wall seconds of each step under the lock.

## 5. Decision rule (frozen)

- **Pass:** W1, W2 and W3 hold on every measured case of the `xradio` arm
  and W4 holds. Then section 3 is the base-weight convention: the M5 ruling
  of 2026-11-16 is replaced by "a weighted stage on a store takes W and
  sigma by msv4-weights.md section 3, under its own stage gate", and the
  reader change is offered for merge.
- **Fail:** W1 or W3 misses on any measured case, or W4 does not hold.
  The rule is not adopted and the reader change is not offered.
- **Partial:** only W2 misses: offered with the miss named.
- `xms-auto` is read the same way and reported as met or not met.
- A bug found by a run may be fixed and the run repeated; runs are numbered
  from 01 and all recorded; the rule is read on the last run of the final
  code. A changed case, measure or tolerance is post hoc.

## 6. What a pass says, and what it does not

A pass says: on xradio 1.3.1 and xarray-ms 0.5.14 stores of these cases,
`rang.msv4` gives a weighted stage the MSv2 path's `WEIGHT_SPECTRUM` for
every data group and, where the store keeps it, its sigma, and a `complex`
solve fed from a store in the MSv2 row order gives the MSv2 gains bit for
bit. It does not say that calibrate, apply, image or selfcal run on a
store (not built), that a solve in the store's own row order is
bit-identical, that sigma-weighted (pre-applied) solves can run on an
xradio store (they cannot: no sigma is kept), nor anything about other
writers, partly unwritten `WEIGHT_SPECTRUM` cells or `FLAG_ROW`.
