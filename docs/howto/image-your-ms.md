# Image your MeerKAT Measurement Set

From an L-band MS with linear feeds to FITS images, through `rang-core run`.
Every key is listed by `rang-core config defaults` and on {doc}`../cli`.

## 1. Before anything is written

- **Work on a copy** unless you mean to write into the original. Before its
  first write rang-core saves FLAG as the CASA flag version `rang_original`,
  but no visibility column is backed up. CORRECTED_DATA and MODEL_DATA are
  overwritten.
- **Supported data:** MeerKAT L band, linear feeds (XX, XY, YX, YY). Circular
  feeds are refused with exit 2 before anything is written; UHF and S band
  are not supported; other telescopes run with a warning, untested
  ({gh}`research/meerkat-scope.md`, {gh}`research/w4-unsupported.md`).
- **MVFv4 archives** are read by `rang.meerkat` (the `meerkat` extra) into
  arrays, not into an MS; the chain itself takes a Measurement Set
  ({gh}`research/mk1-katdal.md`).

## 2. Write the configuration

```sh
rang-core config defaults > config.yaml
```

Set at least:

```yaml
fields:                       # FIELD names or ids by role
  fcal: [J1939-6342]          # flux calibrator; bpcal defaults to it
  gcal: [J1833-2103]          # gain calibrator(s)
  xcal: [J1331+3030]          # polarisation-angle calibrator (full polarisation only)
  target: [MY-TARGET]
flag:
  strategy: mk_rfi_flagging_calibrator_fields_firstpass.yaml   # relative to config.yaml
image:
  size: [4096, 4096]          # required, even
  scale: 1.5asec              # required
```

The default `run.stages` is the whole chain, `[flag, calibrate, apply, image,
selfcal]`. Drop `selfcal` for a 1GC image; use `[image]` for data that are
already calibrated (then `image.column: auto` takes CORRECTED_DATA only after
this run's `apply`, otherwise DATA, so set `image.column: CORRECTED_DATA`).

The calibration sections are the bulk of the file: {doc}`calibrate` gives
CARACal's 1GC chain and its full-polarisation chain as rang-core configurations.
{gh}`examples/ms-to-image/config.yaml` (Stokes I, the quickstart) and
{gh}`research/results/e2-acceptance-scripts/e2b.yaml` (full polarisation, the
frozen E2-B configuration on LUNO) are complete files to start from.

## 3. Check it against the MS

```sh
rang-core config check config.yaml my.ms
rang-core config check config.yaml my.ms --all    # also what no stage can run yet
```

It validates the whole file and resolves every field against the MS, reports
every problem at once and exits 2 if there is one. A refusal names the reason;
it means the feature is not implemented, so do not work around it.

## 4. Run

```sh
rang-core run config.yaml my.ms
```

| Option | Effect |
| --- | --- |
| `--run-dir DIR` | state and outputs in `DIR` instead of `<ms>.rang-run` |
| `--force STAGE` | rerun a finished stage (repeatable; `all` for every stage); a forced `flag` first restores the flags saved before its earlier attempt |
| `rang-core --no-receipt run ...` | write no receipt (a global option, before the command) |

A rerun skips every finished stage whose configuration hash is unchanged,
reruns a failed or interrupted one, and refuses a stage whose configuration
changed until you `--force` it. The single stages (`rang-core flag`,
`calibrate`, `apply`, `image`, `selfcal`) take the same arguments.

**Threads and memory.** `data.memory_limit_gb` (8 GiB by default) bounds what
flag, calibrate and apply hold; they read in chunks within it.
`RAYON_NUM_THREADS` sets the core's threads, `image.threads` GeMClean's. On a
host shared with other heavy jobs, run under `tools/heavy_lock.py` from a
checkout ({doc}`../contributing`).

## 5. What it writes

In the MS: FLAG, CORRECTED_DATA, MODEL_DATA (calibrator models; target model
only with `image.write_model: true` or in selfcal). Beside it,
`<ms>.flagversions/`. In `<ms>.rang-run/`:

| Path | Contents |
| --- | --- |
| `state.json`, the resolved configuration | per stage: status, wall time, configuration hash, flag version saved |
| `<stage>/summary.json` | what the stage did and the SHA-256 of what it wrote |
| `calibrate/<name>/` | one CASA calibration table per term, named by `name` |
| `image/<field>/` | `image-image.fits` (restored), `-model`, `-residual`, `-dirty`, `-psf`, `image-report.json`, `gemclean.log` |
| `receipts/` | one `rang.receipt` per command |

The image stage's `summary.json` records the exact `gemclean` command line.

## 6. Or image directly with gemclean

`gemclean` takes WSClean-style options ({doc}`../cli`, end of page):

```sh
gemclean -name out/img -size 4096 4096 -scale 1.5asec -weight briggs 0 \
    -niter 100000 -auto-threshold 3 -no-update-model-required my.ms
```

By default it images CORRECTED_DATA when present, else DATA, and writes the
model column after imaging, as WSClean does; `-no-update-model-required`
leaves the MS untouched. It refuses `-model-column DATA` and the column being
imaged. Multiscale (`-multiscale`), masks (`-auto-mask`, `-fits-mask`),
Stokes (`-pol IQUV`, `-join-polarizations`) and channels (`-channels-out`,
`-join-channels`) follow WSClean 3.7; the refused options are on
{doc}`../limits`.

Next: {doc}`check-results`.
