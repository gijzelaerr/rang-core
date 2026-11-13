# Quickstart

From nothing to a calibrated, deconvolved MeerKAT image in about a minute, on
A1 small: rang's simulated L-band observation (16 antennas, 64 channels,
41 MB, written from seeds; {gh}`research/a1-simtruth.md`), so every number can
be checked against the truth. The same chain runs in CI on all five wheels
({gh}`tools/e2e/run.py`).

```{note}
The 0.1.0 wheel on PyPI predates `rang-core run` and `gemclean`. Until 0.2.0,
install from a source checkout ({doc}`installation`, "From source"). The
generator `examples/a1_simtruth.py` and the example configuration are in the
checkout too.
```

## 1. Install from source

Linux or macOS:

```sh
git clone https://github.com/gijzelaerr/rang-core && cd rang-core
python3 -m venv .venv
.venv/bin/python -m pip install --index-url https://pypi.org/simple -e '.[notebook]'
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
git clone https://github.com/gijzelaerr/rang-core; cd rang-core
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install --index-url https://pypi.org/simple -e ".[notebook]"
.venv\Scripts\Activate.ps1
```

This needs Rust 1.93 and `cargo` on `PATH`; maturin builds the extension
`rang._core` during the install. Check it:

```sh
rang-core -h
gemclean -h
```

## 2. Write A1 small

```sh
mkdir work && cd work
python ../examples/a1_simtruth.py generate small . --workers 2
```

This writes `a1-small.ms`, the truth (`truth.json`, `truth.npz`), the RFI mask
(`a1-small.rfi_mask.npz`) and the provenance with seeds and hashes, in about
4 s.

## 3. Configure and check

```sh
cp ../examples/ms-to-image/config.yaml ../examples/ms-to-image/strategy.yaml .
rang-core config check config.yaml a1-small.ms
```

{gh}`examples/ms-to-image/config.yaml` is CARACal's continuum chain in
Stokes I: the Tricolour port on DATA; K, G, B on the flux calibrator
J1939-6342 (PKS 1934−638, Stevens-Reynolds 2016); G and the flux scale F on
the gain calibrator; applied to the target; one 1024² GeMClean image at 3″,
Briggs 0. `config check` validates the whole file against the schema and the
MS and reports every problem at once, exit 2 if there is one.

## 4. Run

```sh
rang-core run config.yaml a1-small.ms
```

The MS is written in place (FLAG, MODEL_DATA, CORRECTED_DATA); everything else
goes into `a1-small.ms.rang-run/`:

| Path | Contents |
| --- | --- |
| `state.json` | each stage's status, wall time and configuration hash |
| `calibrate/` | the CASA tables `K`, `G`, `B`, `Gsec`, `F` |
| `image/SIM-TARGET/` | `image-image.fits`, `-model`, `-residual`, `-dirty`, `-psf` |
| `receipts/` | one `rang.receipt` (version 5) per command |

Beside the MS, `a1-small.ms.flagversions/` holds the CASA flag versions:
`rang_original`, saved before the first write, and one per writing stage.

Run the same command again: every finished stage with an unchanged
configuration is skipped. A changed one is refused unless you pass
`--force STAGE`.

What CI measures on this run (Windows x86_64, 2026-11-11;
{gh}`research/e4-tutorial.md`): flagged fraction 0.364, brightest peak 0.4957 Jy
against a true 0.500 Jy, residual rms 0.70 mJy, restoring beam 29.0″ × 4.97″.
On other platforms the numbers differ in the last digits; images are not
byte-identical across platforms ({doc}`limits`).

## 5. Image directly with gemclean

`gemclean` takes WSClean-style options and images a Measurement Set without a
configuration:

```sh
gemclean -name direct -size 1024 1024 -scale 3asec -weight briggs 0 \
    -niter 20000 -auto-threshold 3 -data-column CORRECTED_DATA \
    -no-update-model-required a1-small.ms
```

`-no-update-model-required` keeps MODEL_DATA as it is; by default `gemclean`
writes the model column, as WSClean does.

## Next

- {doc}`tutorials/notebooks/00-ms-to-image` runs the same chain in a
  notebook and shows every output: flag versions and restore, FLAG against the
  RFI mask, the tables, the FITS images, the receipt, resume, and two refusals.
- {doc}`howto/index` for your own MeerKAT Measurement Set.
- {doc}`cli` for every command and configuration key.
