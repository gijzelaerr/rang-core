# Image a MeerKAT Measurement Set

For: an astronomer with a MeerKAT (L-band) Measurement Set who wants an image.
Ends in FITS images in the run directory, the receipts of every step, and a
short record of what was run. The commands are in {doc}`../cli`.

rang is a tested research demonstrator, not an operational calibrator; the
science-grade gates are those of v0.2.0 (`research/finish-plan.md`). Say so to
the user, and compare against their usual pipeline (CARACal, WSClean) before
they rely on an image.

## 1. Check the environment and the data

- `rang-core -h` must run; `gemclean -h` too. `gemclean` is a console script
  of the package since task G8 (`research/g8-wheel.md`), which is not yet in a
  release: the 0.1.0 wheel on PyPI lacks it, a source install (`maturin develop
  --release`, {doc}`../installation`) has it.
- Ask for the MS path, the field names of the calibrators and the target
  (`fcal`, `bpcal`, `gcal`, `xcal`, `target`), and whether the data are already
  calibrated (then image only).
- The commands write into the MS in place. Before the first write the flags are
  saved as the CASA flag version `rang_original`, but visibility columns are
  not: work on a copy unless the user says otherwise.

## 2. Write the configuration

```sh
rang-core config defaults > config.yaml
```

Edit only what is needed and leave the rest at the defaults:

- `fields`: the field roles above.
- `run.stages`: `["image"]` for calibrated data; the default
  `["flag", "calibrate", "image"]` otherwise (`apply` and `selfcal` as needed).
- `flag.strategy` (for `flag`): a Tricolour strategy YAML, such as CARACal's
  `mk_rfi_flagging_calibrator_fields_firstpass.yaml`, relative to `config.yaml`.
- `image.size` and `image.scale` (required): for example `[4096, 4096]` and
  `1.5asec` at L band; `image.weight` and `image.robust` (Briggs 0 by default).

Then validate against the MS before anything runs:

```sh
rang-core config check config.yaml my.ms
```

A refusal names the reason and the task that adds the missing feature
(`research/w4-unsupported.md`). Report it to the user; do not work around it.

## 3. Run

```sh
rang-core run config.yaml my.ms
```

On a shared host, take the heavy lock:
`python tools/heavy_lock.py run -- rang-core run config.yaml my.ms`. A run
resumes where it stopped; `--force STAGE` reruns a finished stage. Images go to
`<ms>.rang-run/image/<field>/`, receipts to `<ms>.rang-run/receipts/`.

To image a single MS directly, without the configuration, `gemclean` takes
WSClean-style options, for example
`gemclean -name out/img -size 4096 4096 -scale 1.5asec -weight briggs 0 -niter 100000 -auto-threshold 3 my.ms`
(`research/gemclean.md`).

## 4. Report

Give the user: the image paths; the configuration; the wall time of each stage;
the residual image's rms and peak, measured on the FITS files; anything refused
or unusual in the stage output. Do not call the image
science grade or compare it with another pipeline's without measuring both.
If a step failed or a refusal looks wrong, offer to open an issue with the
command, configuration and receipt (`docs/contributing.md`).
