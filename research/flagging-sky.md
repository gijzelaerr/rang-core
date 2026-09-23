# MeerKAT L-band calibrator sky-model diagnostic

Status: final three-control Stimela2 recipe completed successfully in
`outputs/tv-flagging-sky-02`. All input preservation audits passed. No flagging
or imaging improvement is claimed.

This is a paired diagnostic alongside the TV-guided flagging experiment. It does
not choose additional flags or claim that a lower-TV sky model is physically
correct. Both actual QuartiCal full-Jones complex 2x2 solves use the same real
data, native weights, seeded train/validation/test splits, solution grid and
point-baseline gain normalization. The TV comparison uses the original point
solve's fixed edge support and rejects missing reference edges.

The [SARAO calibration guidance](https://skaafrica.atlassian.net/wiki/spaces/ESDKB/pages/1481408634/Flux+and+bandpass+calibration)
recommends multi-component calibrator models for accurate L-band calibration.
The selected [official B. V. Hugo/SARAO 2021 release](https://doi.org/10.48479/hhhy-4r55)
contains the complete `fitted.PKS1934.LBand.wsclean.cat.txt` model, 5153 POINT
components, SHA256
`b277bc6d4095bb22798cc70547d9563a56460eb6e450474854b93117534b1fb9`.
Its CC BY-NC 4.0 model is kept in ignored outputs, not redistributed in this
repository. It is an **apparent-scale** catalog, with no primary-beam correction;
another beam must not be applied to it without transforming the convention.

The input is the existing checksum-pinned public SKA reference-pointing scan9,
not a standard science calibrator observation. Only four MeerKAT antennas and
short baselines are present. The catalog assumes nominal MeerKAT pointing and
its applicability to this dedicated pointing scan is unverified. Any apparent
improvement remains diagnostic and could reflect pointing/beam/model mismatch.

Prediction uses [Crystalball](https://github.com/caracal-pipeline/crystalball)
0.4.3 and Africanus0.4.4, as recommended by SARAO, with all components and no
source truncation. A separate `/opt/sky` Python3.12 venv is required: Crystalball
needs psutil>=6.1 while Stimela2.1.4 needs psutil<6. Installing them together
correctly failed dependency validation; the isolated image runs pip check in
both environments. Other predictor dependencies are constrained by the base
lock, and its complete freeze is retained in each run's configuration.

Before prediction the working MS is backed up, all existing input-column arrays
are hashed, and flags are snapshotted. Crystalball adds only a new model column.
An independent NumPy DFT, using a separate catalog parser and documented additive
Jy polynomial convention, checks nine row/channel samples against the full
catalog prediction. An official-primary-only Crystalball control (the uniquely
brightest `PRIM` source) separates the primary spectrum/position change from the
contribution of secondary sources. Its prediction is independently checked too.
Original DATA, weights, input MS tree and immutable copied
MS are audited. Original flags are restored after solving; originals are never
unflagged, and no additional flags are selected.

Build the base image and retrieve the checksum-verified official catalog, then:

```sh
docker build --platform linux/amd64 -f tools/flagging/sky/Dockerfile -t rang-flagging-sky:local .
mkdir -p outputs/flagging-sky-inputs
curl --fail --location --proto '=https' --tlsv1.2 --output outputs/flagging-sky-inputs/fitted.PKS1934.LBand.wsclean.cat.txt https://archive-gw-1.kat.ac.za/public/repository/10.48479/hhhy-4r55/data/fitted.PKS1934.LBand.wsclean.cat.txt
bash tools/flagging/sky/run-pilot.sh outputs/tv-flagging-sky-new
```

The native Stimela2 recipe is `recipes/tv-flagging-sky.yaml`; its callable API is
`rangtoy.flagging_sky.compare(run_dir, archive, sky_model, iterations=50)`.
Fresh output directories are mandatory. Download the official model via the
linked release before running; runtime prediction and calibration need no network.

## Measured results

All three full-Jones solves used seed7, channels1024:3072 (1070–1497.791MHz),
time interval2, frequency interval32, 50iterations and fixed train/validation/test
counts73720/9115/9169. The point-baseline median gain norm1.05200390630565 was
used throughout. Fixed TV support contained984 temporal and1094 spectral edges;
no reference edges or evaluation predictions were lost.

| Sky | Fixed-support TV | Validation weighted MSE | Test weighted MSE |
| --- | ---: | ---: | ---: |
| Reynolds phase-centre point approximation | 0.1474368701 | 25.20612260 | 24.91960760 |
| Official SARAO primary-only | 0.1474151791 | 25.20651550 | 24.92006123 |
| Official full5153-component SARAO apparent sky | 0.1475149857 | 24.90457754 | 24.67678155 |

The full sky improved validation prediction error by1.198% relative to the
official-primary-only control and test prediction error by0.976%, while
increasing fixed-support gain TV by0.0677%. Therefore the TV ordering does not
match the prediction-error ordering in this test. The differences have not been
assigned statistical confidence, and neither lower MSE nor lower TV verifies a
physical sky/gain solution on this special pointing dataset. Gain TV remained
dominated by the frequency component (~0.1204 versus temporal~0.0271).

Independent full and primary DFT checks both had maximum absolute discrepancies
below4.70e-7Jy across the nine checked cross-correlation row/channel samples. The
catalog primary lies0.0328arcsec from the MS phase centre, which does not resolve
the actual antenna pointing/beam-state ambiguity.

The first pilot completed its two-model comparison before the intermediate
control was added. `complete_primary()` appended the control recoverably, retaining
the original two-model result in `backups/result-before-primary.json`. The fresh
second pilot verified all three controls within the final Stimela2 recipe and
reproduced the first pilot's scientific metrics to floating-point precision.
An initial single-environment predictor image failed pip check because of the
psutil dependency conflict; no raw observation was changed.

The final sky image also retains pip's installation report, including public-PyPI
download URLs and artifact SHA256 values, for the predictor environment. These
are included in `sky-config.json` in subsequent runs, alongside the full freeze.
Recorded amd64-emulated timings are diagnostic, not native performance claims.

The next scientifically useful comparison is on a normal, adequately modelled
MeerKAT calibrator scan, with calibrated sky-signal recovery and imaging checks,
while retaining this small negative TV/prediction-ordering result.
