Target: NRAO helpdesk https://help.nrao.edu (CASA department; my.nrao.edu login) or casa-feedback@nrao.edu. TEXT-ONLY: CASA has no public issue tracker.
Status: ready to post
Reproduced on: casatools/casatasks 6.7.6.14 (latest on PyPI), manylinux_2_28 wheel, Python 3.12, Ubuntu 26.04, run 2026-11-12. The setup has the Ubuntu casacore-data 20250826 measures, casaconfig auto-updates off and casarundata 2026.10.27-1 for the Perley-Butler tables. `six` was installed by hand (see the note at the end). Code references are read in source at casa6 master 90e9d3dae955. The VisCalSolver2 iteration-limit message is read in source only; it was observed on 6.7.6.14 in October and not rerun here.
Duplicates checked: CASA Docs Known Issues (stable), which lists two setjy items (a segfault with usescratch=False, and models not being overwritten); neither is these. GitHub-wide issue search "setjy minblperant", "gaincal minblperant K": no matches. NRAO JIRA is not public.

Title: setjy/bandpass report failures only as SEVERE log lines and return normally; gaincal K ignores minblperant; solver messages go to stdout only

---

The cases below all come from one 8-second script: a simulated 4-antenna MeerKAT MS (64 ch at 1.4 GHz, 32 x 8 s) and a 2-antenna MS with four fields. The relevant calls are inline. In each case a scripted pipeline cannot tell that the step failed without parsing the CASA log.

**1. setjy returns `{}` and leaves the old model in place when the standard has no data for the source**

```python
setjy(vis='s.ms', field='3C286', standard='Perley-Butler 2010', usescratch=True)   # sets MODEL_DATA
setjy(vis='s.ms', field='J1939-6342', standard='Perley-Butler 2017', usescratch=True)
# -> {}   no exception
# SEVERE imager::setjy()  Exception: 1934-638 does not appears to be in .../PerleyButler2017Coeffs
```

- Perley-Butler 2017 is the default standard, and 1934-638 is a primary calibrator for MeerKAT and ATCA. With the default standard, `setjy` on 1934-638 returns `{}` and does not touch MODEL_DATA. Any model from an earlier call stays in the column.
- The same happens when the PerleyButler2017Coeffs/2013Coeffs tables cannot be found. That gives `{}`, MODEL_DATA unchanged (checked bit for bit), and `SEVERE Exception: The coefficient data for Perley-Butler 2017, PerleyButler2017Coeffs is not found in the current directory or in datapath/measurespath.`
- Cause: `Imager::setjy` catches the AipsError, logs it as SEVERE and returns the empty record (`casatools/src/code/synthesis/MeasurementEquations/Imager.cc:5066-5076`). The throws are at `components/ComponentModels/FluxCalcVQS.cc:174` and `FluxStdsQS2.cc:230/290/364`.
- For contrast, a source name the standard does not recognise is not an error at all. `setjy(field='FOO')` or `field='FORNAXA'` with PB2010 or PB2017 returns `fluxd = [1, 0, 0, 0]` Jy for every spw and writes a 1 Jy model, with only `SEVERE FOO is not recognized by Perley-Butler 2017` (`FluxStandard.cc:225-231`). (`FORNAX_A` is recognised; `FORNAXA` is not.)

Requested: raise from the task, or at least return a record that says which fields got no model, when the standard cannot produce a flux density. The silent 1 Jy fallback for unknown names should also be opt-in rather than the default.

Typos (strings only):

- "does not appears" (`FluxCalcVQS.cc:174`).
- The casarundata 2026.10.27-1 table `nrao/VLA/standards/PerleyButler2013Coeffs` has the keywords `Revison` (for `REVISION`), `Type = " Perely-Butler 2013 coefficients"` (leading space, "Perely") and `Date`. PerleyButler2017Coeffs uses `REVISION`, `TYPE` and `DATE`.

**2. bandpass with a missing `gaintable` logs SEVERE and returns normally**

```python
bandpass(vis='g.ms', caltable='Bm.tb', refant='m000', solint='inf', gaintable=['G4.tb'])  # G4.tb does not exist
# returns {'apply_tables': [], ..., 'solve_tables': []}   no exception, no Bm.tb
# SEVERE Exception Reported: Table G4.tb does not exist.
```

A missing input table is a user error that should raise.

**3. gaincal gaintype='K' does not apply minblperant**

With 4 antennas (3 baselines per antenna) and `minblperant=4`:

```python
gaincal(vis='g.ms', caltable='K4.tb', gaintype='K', solint='inf', refant='m000', minblperant=4)
# K4.tb written: 4 rows, 0 % flagged. The log's own statistics say above_minblperant [0, 0].
gaincal(vis='g.ms', caltable='G4.tb', gaintype='G', solint='inf', refant='m000', minblperant=4)
# "Found good G Jones solutions in 0 solution intervals." / "No output calibration table written." (INFO)
```

- minblperant is enforced only in `SolvableVisCal::verifyConstraints`, called from `VisCalSolver2::solve` (`VisCalSolver2.cc:162/316`).
- KJones uses `selfSolveOne`. In `Calibrater.cc:3852-3861` that branch never calls `verifyConstraints`, and it counts every interval as a good solution (`keepNCT(); ++nGood;`).
- So delays are solved, and written unflagged, from antennas that the G and B steps of the same pipeline reject. This is how a CARACal-style K/G/B sequence with its default `minblperant: 4` on a 4-antenna subarray ends after K. G writes no table (logged at INFO), and the following bandpass then fails as in item 2.

Requested:

- Apply the baseline-per-antenna constraint in the selfSolveOne path, or document that K ignores minblperant.
- Log "No output calibration table written" at WARN.
- Do not list a table that was not written in the returned `solve_tables` (gaincal returns `solve_tables: ['G4.tb']` here).

**4. Solver messages written with `cout`, not to the CASA log**

- `" Insufficient unflagged antennas to proceed with this solve."` (`VisCalSolver2.cc:278/479`) appears on the process stdout for the G call in item 3 and not in the casalog file. Run-confirmed: we captured file descriptor 1 separately.
- `"Reached iteration limit: 50 iterations."` (`VisCalSolver2.cc:265/466`, `maxIter_(50)` at :64/:90) also goes to stdout only. It is not in the log, and the iteration count is not in the returned solve statistics. When gaincal is run from a pipeline or a notebook with stdout discarded, there is no record that any solution stopped at the limit.

Requested: send both through the LogIO sink, and add a per-interval "stopped at iteration limit" count to the returned statistics.

**5. (minor) The frequency part of `solint` is dropped silently for G/T**

`gaincal(gaintype='G', solint='16s,32ch')` writes 1 channel per solution, and the log echoes `solint=16s` with the suffix dropped. `bandpass(solint='inf,32ch')` gives 2 channels as expected. This is consistent with G/T not being frequency dependent (`SolvableVisCal.cc:2734-2739`), and the gaincal `solint` help does not promise a frequency part. A WARN when a given frequency interval is discarded would avoid surprises.

Note: a fresh `pip install casatasks==6.7.6.14` currently fails at `import casatasks`. The error is `ModuleNotFoundError: No module named 'six'` from `private/task_plotbandpass.py:33`: `six` is not declared, and python-dateutil 4.0.0 (2026-11-01) no longer pulls it in. Master has the fix ("Remove six dependency", 4fce2abe0658), but no release carries it yet. A 6.7.6.x patch release, or a temporary `six` requirement, would unbreak new installs.
