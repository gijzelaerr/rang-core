# Check the results

What a run records, how to read it, and how to compare it with the tools you
already trust.

## What was run

- `<run>/state.json`: per stage, its status, wall time, the SHA-256 of the
  configuration sections it depends on, and the flag version saved before it
  wrote.
- `<run>/<stage>/summary.json`: what the stage did, with the hashes of the
  flags, solutions and images written and the tables and settings behind
  each written column; the image stage's holds the exact `gemclean` command.
- `<run>/receipts/*.rang-receipt.json` (schema `rang.receipt`, version 5): the
  command, inputs, environment with every `RANG_*` variable, the commit
  (null outside a source checkout), and the MS identified by its file sizes
  and mtimes.
- `<run>/image/<field>/image-report.json` and `gemclean.log`: GeMClean's own
  record: its argv, the column and field imaged, and per channel and
  polarisation the weight sum, visibilities and rows gridded, components and
  major cycles.

Keep the configuration, `state.json` and the receipts with the images; they
are what makes the run reproducible.

## Flags

```python
from rang import core_ms

with core_ms.open_table("my.ms") as t:
    flag = t.getcol("FLAG")          # (row, channel, correlation), as python-casacore
print(f"flagged {flag.mean():.3f}")
```

Compare with `rang_original` through `rang.formats.flagversions.load(ms, name)`
to see what each stage added ({doc}`flag`).

## Calibration tables

They are CASA tables: open them in CASA (`plotms`, `tb`), or summarise them
without CASA:

```sh
rang-core formats check my.ms.rang-run/calibrate/G
```

`rang.formats.caltable` reads them into arrays with CASA's VisCal semantics.
Solutions agree with CASA's and QuartiCal's on their gating sets within the
tolerances of {gh}`research/c2e-calibrate.md` and
{gh}`research/c6w-polwire.md`; the known differences are on {doc}`../limits`.

## Images

The FITS files carry WSClean's names, axes and beam cards (`BMAJ`, `BMIN`,
`BPA`) and open in CARTA, DS9 or astropy. Measure on the files:

- **Residual rms against thermal.** The radiometer equation gives the thermal
  noise ({doc}`../tutorials/notebooks/i1-radio-sky`). On the real ESO 137-006
  pilot the residual floor is 40–60 × thermal in every imager tried,
  WSClean included, for a reason not found ({gh}`research/clean-overview.md`).
- **Flux of known sources** against a catalogue or a calibrator model.
- **Against WSClean.** Image the same MS and column with WSClean 3.7 and the
  same options (`gemclean` takes WSClean's spelling). Dirty images and PSFs
  agree within 4e-7 of the peak on the gating sets
  ({gh}`research/g9-stokes.md`, {gh}`research/g4-masks.md`); the restoring
  beam follows WSClean 3.7's fit ({gh}`research/g7-defaults.md`).

## Against CARACal

The v0.2.0 comparison is one run of CARACal's shipped MeerKAT strategy on the
same data, reporting image quality, flux, wall time and memory (task E3,
{gh}`research/finish-plan.md`). It has not reported. Until it has, run your
usual pipeline beside rang and compare the products above; report a
difference with the command, configuration, receipt and the numbers
({doc}`../contributing`, "Reporting an issue").
