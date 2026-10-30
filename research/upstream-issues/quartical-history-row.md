# QuartiCal: no HISTORY row for the columns and flags it writes

Repository: ratt-ru/QuartiCal. Status: **filed 2026-10-30, https://github.com/ratt-ru/QuartiCal/issues/453**.
Checked 2026-10-30 on QuartiCal 0.2.7 (PyPI, identical to `main` 942f77f), dask-ms 0.2.32,
python-casacore 3.8.1, Python 3.13, on a copy of scan 9 of the public SKA pointing test data
(`outer_scans.zip`, SHA256 `d4dae56f…144f`; 140 rows, 4 antennas, 4096 channels) with a unit
MODEL_DATA added. `grep -rni history quartical/` on `main` and v0.2.8-dev finds only the reader
in `apps/summary.py`. Origin: [flagging-luno-candidate.md](../flagging-luno-candidate.md), where
a third-party `CORRECTED_DATA_QCAL` column could not be traced to its command.

<!-- issue-title: Feature request: append a HISTORY row when writing output columns or flags -->
<!-- issue-body -->
**Is your feature request related to a problem?**
When QuartiCal writes visibility products (`output.products` / `output.columns`) or flags into a Measurement Set, nothing in the MS records that it did so. CASA tasks append their parameters to the `HISTORY` subtable, so a later reader of a shared MS can tell how `CORRECTED_DATA` was made; for a column written by QuartiCal there is no trace of the version, the command or the gain terms, and the gain directory is usually not shipped with the MS.

**To Reproduce**
```bash
goquartical input_ms.path=scan9.ms input_ms.data_column=DATA input_model.recipe=MODEL_DATA \
  solver.terms=[G] G.type=complex G.time_interval=2 G.freq_interval=32 \
  output.products=[corrected_data] output.columns=[CORRECTED_DATA] output.flags=false \
  output.gain_directory=qc/gains.qc output.log_directory=qc/logs.qc
python -c "from casacore.tables import table; print(table('scan9.ms::HISTORY', ack=False).nrows())"
```
The MS gains `CORRECTED_DATA`; `HISTORY` has 21 rows before and after (all from the CASA `split` that made the file).

**Describe the solution you'd like**
An option (default on, or at least available), e.g. `output.history=true`, that appends one row to `HISTORY` whenever QuartiCal writes to the MS: `ORIGIN="QuartiCal"`, the version in `MESSAGE` or `APP_PARAMS`, the full command line or resolved configuration in `CLI_COMMAND`/`APP_PARAMS`, and `TIME` set to the write time. A single row appended (with python-casacore, or through dask-ms) after the column writes have completed would be enough; `apps/summary.py` already reads `HISTORY`.
<!-- end-issue-body -->
