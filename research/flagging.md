# Gain-TV-guided flagging: experiment log

Started 2026-09-23 at the user's request. This is a new MeerKAT flagging
experiment alongside the earlier pointing work. No scientific improvement has
yet been measured.

Paths (2026-10-30, task P8): the frozen `tv-flagging*` recipes,
`tools/flagging/` and the recipe-only modules named here now live under
[`history/`](../history/README.md); this text keeps the paths it was written
with.

Follow-up implementation and concurrent execution are now complete:
[four-workstream diagnostic suite and measured conclusions](flagging-parallel.md),
[Stimela2 scatter recipe](../recipes/tv-flagging-parallel.yaml).
Retain the negative findings: lower gain TV is not consistently better
held-out prediction, and the tested learned policies select no additional flags.

The first dataset is the existing official SKA pointing-offset fixture,
`outer_scans.zip`, SHA256
`d4dae56f7ad1bb4a49ab8c4a3846871d5b8ebb4b731ee958cb9f1baf3306144f`.
Use scan 9 (140 rows, four antennas, 4096 channels, four correlations).
It is a real MeerKAT **L-band** reference-pointing scan, not a science-field imaging benchmark.
See [inspection](measurement-set-inspection.md) for provenance and limitations.

Initial backup: `outputs/flagging-backups/20260923-initial/` contains the code
archive and a second copy of the original observation archive. Code archive
SHA256: `9afe38d6ce6ebefb437b59226ed8b83f71aad1ce537f2aa18309fe09413c5a01`.
Initial git revision: `39eeb53`. The working tree was clean.

Implemented model: a small interpretable residual-outlier policy conditioned on
antenna/time/frequency TV maps. Train its threshold and TV sensitivity by actual
QuartiCal re-solves with `G.type=complex` (full 2x2 Jones matrices). QuartiCal is
a black-box inner solver; no gradient through it is claimed. Use a fixed
gain grid, fixed TV-edge support, flag penalty, bounded additional flag budget,
and fixed validation/test visibility sets. Include an unguided policy control.

Original `FLAG` and `FLAG_ROW` are immutable lower bounds, including on full-row
flags. Only copied Measurement Sets may be opened writable. Keep original raw
columns, immutable flag snapshots, and a pre-write snapshot for every solve.
Candidate masks are recomputed from the original baseline, allowing additional
flags to decrease without ever clearing an original flag. Disable QuartiCal
flag writes and archive all trials, including rejected/null outcomes.

Full-Jones calibration on an unpolarized calibrator has a unitary ambiguity.
Record raw TV and reference-polar-gauge TV; use the latter only under an
explicit unpolarized-model convention. High TV can also reflect genuine gain
structure, low SNR, model error or solver failure. Require residual evidence
and fixed held-out checks before adding flags. This first fixture does not
validate polarization, flux fidelity or imaging improvements.

Primary implementation references:
[QuartiCal gain types](https://quartical.readthedocs.io/en/latest/gain_types.html),
[QuartiCal options](https://quartical.readthedocs.io/en/latest/options.html), and
[Stimela2 callable cabs](https://stimela.readthedocs.io/en/latest/reference/cabdefs.html).

## Executable strategy

[The Stimela2 recipe](../recipes/tv-flagging.yaml) prepares immutable `original.ms`
and writable `work.ms` copies, trains the policy, and exports its maps and flag
audit. The original state includes both `FLAG` and `FLAG_ROW`, including any
existing pipeline flags: this fixture does not distinguish their origins.
Original partially flagged samples are retained but excluded from this first
training experiment. Native channel selection is 1024:3072; autocorrelations
are excluded from training and restored unchanged in the output.

Row-channel samples split approximately 80/10/10% into train/validation/test,
with four correlations together and a fixed seed. A deterministic reservation
retains at least two originally eligible training samples per baseline and gain
bin where available. This uses metadata/flags/seed only, preventing holdouts
from emptying a sparse bin. The gain grid must match the grid of this reservation.

Every inner solve uses QuartiCal `G.type=complex`, two integration times per
solution, 32 native channels per solution, up to 50 iterations and one thread.
Original weights are reused. QuartiCal MAD flagging and robust reweighting are
disabled for this ablation. `output.flags=false` prevents independent changes
to the mask, and the recipe checks that the solver left it exactly unchanged.
Each write gets exclusive before/after flag snapshots. Candidate additions are
recomputed from the original baseline, so extra flags can increase or decrease
without clearing an observatory flag.

For an explicitly unpolarized model, the reference polar decomposition is
$G_r=H_rU_r$. Applying $G_p\leftarrow G_pU_r^H$ fixes the right unitary gauge
while preserving common physical amplitude and the unpolarized RIME. Singular
reference bins become invalid. Raw TV is saved too; polarized external models
must use `gauge=raw`. A general polarized-model gauge treatment is future work.

The Rust kernel computes anisotropic Frobenius TV over all four complex entries:

```math
T(G)=\operatorname{mean}_{e\in E_t}
\frac{\|G_{e^+}-G_{e^-}\|_F}{s_0}\frac{\widetilde{\Delta t}}{\Delta t_e}
+\operatorname{mean}_{e\in E_\nu}
\frac{\|G_{e^+}-G_{e^-}\|_F}{s_0}\frac{\widetilde{\Delta\nu}}{\Delta\nu_e}.
```

$s_0$ is the baseline median gain norm and is fixed across candidates. Edges do
not cross invalid solutions or gaps greater than three typical spacings. The
objective uses fixed baseline edge support: losing an edge rejects a candidate,
and gaining edges cannot change the averaging denominator. Maps average the
edges incident on each antenna/time/frequency bin; a visibility inherits the
larger guidance value of its two antennas. Unsupported bins are grey in plots,
not displayed as unusually smooth gains.

The model uses robust log-amplitude outlier scores $z$ of whitened full-matrix
visibility residuals. Location and MAD are estimated per baseline on training
samples only. A sample is proposed for flagging when

```math
z\,[1+\alpha\min(h/\operatorname{median}(h>0),5)]>\tau,\qquad z\geq2.
```

The independent residual requirement avoids treating TV alone as an RFI label.
Proposals couple all four correlations and retain the largest scores up to a
2% additional training-sample budget. The predefined grid is
$\tau\in\{8,5,3\}$ and $\alpha\in\{0,1,3\}$; $\alpha=0$ is the unguided
ablation, not an established state-of-the-art comparator. A no-change policy is
always available. Actual QuartiCal re-solves train threshold and TV sensitivity:

```math
L=\frac{T(G(F))}{\max(T(G(F_0)),10^{-30})}+2f
+0.25\frac{\mathrm{MSE}_{\mathrm{val}}(F)}{\max(\mathrm{MSE}_{\mathrm{val}}(F_0),10^{-30})},
\quad \mathrm{MSE}_{\mathrm{val}}(F)\leq1.01\,\mathrm{MSE}_{\mathrm{val}}(F_0).
```

MSE uses original inverse-variance weights on fixed validation samples. Invalid
predictions are counted and make a metric unavailable, rather than being dropped
to improve it. Test data never choose a candidate. No gradient through QuartiCal,
neural network or RFI labels are claimed. Optional rounds refresh residuals/maps
from the selected solve against the same original baseline.

The final `flagged.ms` contains original flags plus selected training additions.
Temporary training exclusions are removed by restoring original flags; holdout
samples remain unchanged. Archived gains correspond to the training mask, not
an all-data calibration. The recipe exports `model.json`, trial gains, TV maps,
gain spectra, commands, checkpoints, flag snapshots, final flag audit and a
summary. The original dataset file digest and final DATA array are verified.

## Reproduce

From the checkout root on this ARM Mac:

```sh
docker build --platform linux/amd64 -f tools/flagging/Dockerfile -t rang-flagging:local .
bash tools/flagging/run-pilot.sh outputs/tv-flagging-pilot
```

The wrapper uses the existing checksum-pinned public archive in
`outputs/ska-pointing/outer_scans.zip`. Source code is mounted read-only, outputs
writable, with no runtime network. Numba compilation caches persist in ignored
outputs. Every run directory must be new. Both container bases are digest pinned;
`tools/flagging/requirements.lock` pins the public-PyPI Python environment.
Emulated timings are not native performance measurements.

On native Linux/Python 3.12, install the flagging extra from public PyPI and build
the Rust library, then run:

```sh
stimela -s opts.log.dir=outputs/stimela-flagging-logs run recipes/tv-flagging.yaml \
  tv-flagging archive=outputs/ska-pointing/outer_scans.zip run-dir=outputs/tv-flagging-native
```

For another small real dataset, replace `archive=...` with `ms=...` and
`model-column=MODEL_DATA`, adjusting the channel window. Input must contain one
scan/field/SPW with linear XX/XY/YX/YY products and a supplied finite model column.
Telescope metadata must explicitly identify MeerKAT, and native channel centres
must be within nominal L-band coverage (856–1712 MHz). The fixture has 856–1711.8
MHz channels; the initial selection is 1070–1497.8 MHz. UHF and S-band inputs are
rejected. The fixture's point model is never assumed for an external field. Set `gauge=raw`
for polarized models. Transfer of a learned policy to another observation,
multi-scan operation and independent image/flux checks remain later steps.

## Checkpoints and first measured result

- Initial code and raw archive backed up and checksum-verified before editing.
  Second code backup: `outputs/flagging-backups/20260923-implementation/`.
- Rust TV, flag invariants, training loop, pinned environment and Stimela2 recipe
  implemented. Scientific invariant checks and the full existing suite passed:
  14 Rust tests, 112 Python tests before adding the sparse-bin reservation test.
- Stimela2 2.1.4 needs `path_policies.mkdir_parent=false` so the preparation cab
  owns exclusive output creation. Initial empty startup directories were kept.
- First complete solver pilot: `outputs/tv-flagging-pilot-03/`, seed 7, 73,714
  train / 9,116 validation / 9,174 test samples. This exploratory version used
  unwhitened policy features and an unreserved split; its archives are retained.
  Baseline gauge-fixed TV 0.1476474; raw TV 0.2701043; validation weighted MSE
  25.20588. Six distinct nonempty candidate masks added 0.077–1.882% flags and
  increased TV to 0.1484466–0.1551881. No policy beat the no-change objective.
  Test MSE was unavailable because at least one heldout sample had unsupported
  baseline gains; none were silently dropped. Final original flags and data
  digests were preserved. This is a negative result, not a flagging success.
- The final strategy reserves sparse-bin training support before solving and
  whitens residual features consistently with the evaluation weights. It also
  explicitly reports invalid predictions and masks unsupported plot bins.
  Pinned-environment replay `outputs/tv-flagging-pilot-04/` passed: 73,720 train,
  9,115 validation and 9,169 test samples; no invalid predictions in any split.
  Baseline TV 0.14743687, raw TV 0.26732583, validation MSE 25.20612 and test MSE
  24.91961. Five distinct nonempty proposals increased TV to 0.1480733–0.1535371;
  again no additional flags were selected. The flag audit confirms original
  cell/row flags and final DATA array are preserved. Final replay with explicit
  MeerKAT L-band metadata enforcement passed in `outputs/tv-flagging-pilot-06/`.
  It reproduced the second run's numerical result to floating-point precision:
  no flags added, test MSE ratio 1.0, every held-out prediction supported.
  An initial scope-guard replay stopped during preparation because casacore
  returns string columns as lists; conversion now explicitly uses NumPy. Original
  data were not altered and the partial output was retained.
- Final local verification passed: release build, 14 Rust and 114 Python tests
  with no skips, Clippy, Rust/Ruff formatting, Ruff lint, byte compilation,
  dependency consistency, whitespace checks, and the complete Stimela2 recipe.
  The final flag audit verifies all 1,074,094 original flagged cells, row flags,
  source/copy digests and final DATA array. Aggregate results, all candidate
  outcomes and provenance are archived in
  [gain-tv-flagging.json](results/gain-tv-flagging.json). Code/raw observation
  backups and the final checkpoint are under `outputs/flagging-backups/`;
  every solve's flag snapshots remain in its run directory.

The first maps show mostly spectral structure, including strong variation on
m002 near the lower usable frequency island. This is not proof of residual RFI:
bandpass shape, scan-dependent attenuation, sky mismatch and gain noise all
remain plausible. The fixture point-source approximation ignores secondary
field sources; SARAO provides more complete calibrator models in its
[flux/bandpass guidance](https://skaafrica.atlassian.net/wiki/spaces/ESDKB/pages/1481408634/Flux%2Band%2Bbandpass%2Bcalibration).
The Reynolds coefficients (MHz/Jy) are also documented in the primary
[MeerKAT SMC survey paper](https://arxiv.org/abs/2401.11024). A science-field
dataset with a verified sky and independent signal-recovery checks is required
before concluding that lower TV gives better astronomy.

The implemented first strategy is runnable and preserves the original state.
It has not demonstrated a quality improvement. Next tests should distinguish
genuine gain structure/model error from residual RFI, use a verified MeerKAT
L-band calibrator sky, and include controlled RFI/signal injections plus matched
AOFlagger/QuartiCal-MAD quality and cost comparisons. The unguided threshold
ablation here is insufficient to establish state-of-the-art superiority.

## Parallel follow-up plan (2026-09-23)

The user authorized parallel work on the following experiments and requested a
commit of the implementation and findings above. These are proposed follow-ups,
not measured improvements. Independent workstreams use separate fresh output
directories; neither code integration nor concurrent solving may share a
writable Measurement Set.

1. Seeded RFI injections on copies of originally unflagged MeerKAT L-band
   samples: narrowband, time-burst and antenna-local patterns. Compare the
   untouched observation, contaminated observation, current policy and a mask
   removing exactly the injected contamination. This injection-only oracle
   does not label any pre-existing interference. Measure injection recovery,
   additions outside injections, fixed-support gain TV and predictions against
   the unmodified reference. Keep evaluation samples independent of training.
2. Replace the approximate phase-centre calibrator with the published SARAO
   multi-component L-band model, using a verified prediction tool such as
   `crystalball`. SARAO explains that secondary field sources can imprint
   bandpass structure; this is a confounder hypothesis for our scan, not its
   established cause. Retain QuartiCal full complex 2x2 gains and TV objective.
3. Compare native QuartiCal residual MAD and Tricolour's MeerKAT SumThreshold
   implementation with the TV policy under matched data, sky, masks and gain
   settings. Record calibration quality, additional flag volume and cost;
   emulated timing is not a native performance claim. External flagger masks
   must be merged with immutable original flags, never replace them.
4. Measure the effect of removing small candidate visibility patches by actual
   QuartiCal re-solves. Train a small action-benefit predictor on those measured
   TV changes, retaining fixed TV support, held-out quality guards and flag
   penalties. Its usefulness depends on the injection/oracle controls; high TV
   alone is not an RFI label. Reserve independent actions/scans for evaluation.

The workstreams can develop and run independently. A scientific go/no-go for a
learned policy requires the control results; larger observations and image/flux
recovery checks remain subsequent validation, not completion criteria for this
small diagnostic pilot.

Primary sources for these follow-ups:
[SARAO flux/bandpass calibration](https://skaafrica.atlassian.net/wiki/spaces/ESDKB/pages/1481408634/Flux%2Band%2Bbandpass%2Bcalibration),
[QuartiCal MAD options](https://quartical.readthedocs.io/en/latest/options.html),
[Tricolour paper](https://arxiv.org/abs/2206.09179), and
[Tricolour implementation](https://github.com/ratt-ru/tricolour).
