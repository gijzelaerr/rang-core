# A-FLAG: AOFlagger 3.5 as a second oracle for the SumThreshold port

Task A-FLAG of [big-plan.md](big-plan.md) (ecosystem survey section 5.2
item 7), started 2026-10-30 on branch `aflag-aoflagger` from `main`
`17adc1e`. The protocol below was frozen in its own commit, before any
AOFlagger or comparison code ran on the four task D controls. Only
synthetic data had been used at that point: the API probes and the
noise-estimator calibration in section 1.

Status: **proposed** (protocol frozen). Results are appended under
"Measured result" and nothing above it changes except through a dated,
labelled amendment.

## 0. Question and context

Task D ported Tricolour 0.2.1's SumThreshold flagger
([core-d-tricolour.md](core-d-tricolour.md)). Its kernel is the
katsdpsigproc `twodflag.py` code. The port reproduces Tricolour flag for
flag on the four archived CARACal controls, and RV1 showed that
Tricolour 0.5.0-dev is identical ([rv1-revalidate.md](rv1-revalidate.md)).
Both of those checks are against Tricolour itself.

SumThreshold was introduced by Offringa et al. (2010), and the reference
implementation is AOFlagger. CARACal's flag worker also runs AOFlagger
(`autoflagger` cab), for which it ships the v2 XML strategies
`firstpass_Q.rfis` and `firstpass_Q_sparsescans.rfis`
(`outputs/caracal-strategy-inputs-8f7bb363`). AOFlagger 3 runs Lua, and
those files are not used here. A-FLAG asks whether Tricolour's
first-pass strategy, translated onto AOFlagger 3.5's Lua API, flags what
the port flags. Where it does not, the question is which documented
algorithmic difference accounts for the gap.

This is a comparison of two flaggers, not a scientific contribution under
AGENTS.md.

## 1. Facts established before freezing (synthetic data only)

**Oracle image.** `rang-aflag-aoflagger:3.5.0`
(`tools/oracles/aoflagger/Dockerfile`).

- Image Id `sha256:383ec2a346bc95d751f1a533cda284784a6f8e5577eb292ca2fbc5d5d78b6025`
  (427 MB, 91 s build). A local image has no RepoDigest, so the Id, the
  base digest and the deb list pin it.
- Base `ubuntu:24.04@sha256:fe815609…f852`, `ppa:kernsuite/kern-10`.
- Debs:
  - `aoflagger` and `libaoflagger0` `3.5.0-1kern1`;
  - `python3-casacore` `3.7.1-1kern2`, with `libcasa-*` `3.7.1-1kern1`;
  - `python3-numpy` `1:1.26.4+ds-6ubuntu1`;
  - `liblua5.3-0` `5.3.6-2build2`.
- Full list: `outputs/aflag-20261030-01/image-debs.txt` (309 debs); build
  record in `image.json`.
- The deb installs the Python module as
  `/usr/lib/aoflagger.cpython-312-x86_64-linux-gnu.so`, so the image sets
  `PYTHONPATH=/usr/lib`.
- The deb carries no `meerkat-default.lua`, only the 21 shipped
  strategies under `/usr/share/aoflagger/strategies`.
- Runs use `--network none`.

**Documentation read.** The AOFlagger v3.5.0 source tarball,
`outputs/aflag-20261030-00-upstream/aoflagger-v3.5.0.tar.gz`, from
gitlab.com/aroffringa/aoflagger, read as data (SHA256 in `SHA256SUMS`
there). What was read:

- the documentation: `doc/source/lua_functions.rst`,
  `lua_class_data.rst`, `python_interface.rst`, `strategy_options.rst`;
- the Lua bindings: `lua/functions.cpp`, `lua/functionswrapper.cpp`,
  `lua/luastrategy.cpp`;
- the algorithms: `algorithms/thresholdconfig.cpp`, `sumthreshold.cpp`,
  `sumthresholdmissing.cpp`, `highpassfilter.{h,cpp}`, `siroperator.h`,
  `thresholdtools.cpp` (`WinsorizedMode`), `resampling.h`;
- the shipped `generic-default.lua`.

**What the source says** (v3.5.0; each item is a place where the two
algorithms are documented to differ):

- **A1. `sumthreshold(data, xf, yf, x, y)`.**
  - It builds `ThresholdConfig` with lengths {1, 2, 4, 8, 16, 32, 64,
    128, 256} in both directions. These are fixed: the Lua API cannot
    choose them.
  - The threshold on the window *mean* for length L is
    `6 · 1.5^log2(L) / L · factor`. This equals χ₁/ρ^log2 L with an
    effective **ρ = 4/3**, against Tricolour's YAML `rho: 1.3`.
  - `factor = sensitivity · WinsorizedMode(image, data mask)`. That is
    one noise estimate per call, for the whole image (one baseline).
    The estimate is a Rayleigh mode computed from the *signed* values,
    winsorized at the 90th percentile, × 1.0541.
  - Tricolour estimates `outlier_nsigma · 1.4826 · median|r|`, per
    channel for the time pass and per (time, frequency chunk) for the
    frequency pass and the spectrum.
  - After the estimate, the data mask is **reset** (`additive = false`).
    Samples enter the sums unless an *earlier length of the same call*
    flagged them, in which case they are **excluded** (count reduced).
    Tricolour instead **clamps** samples already flagged by the same pass
    to ±threshold and keeps them in the sum.
  - Both directions run in one call, interleaved per length (H1, V1, H2,
    V2, …). Tricolour runs all time windows, then all frequency windows.
  - Its frequency pass sees the time flags only through the noise
    estimate.
  - The returned mask holds the new detections only.
- **A2. `sumthreshold_masked(data, missing, …)`.** As A1, but samples
  flagged in `missing` are removed: the windows run over the
  concatenation of the non-missing samples. This is AOFlagger's
  documented way to keep input flags out of detection.
  - Tricolour has no such notion. `_average_freq` sets flagged samples to
    0, so after background subtraction they enter every window sum as
    `0 − background`.
- **A3. Absolute thresholds (implementation detail, not documented API).**
  - If every sample of the data mask is flagged, `WinsorizedMode`
    returns 0. The factor is then the sensitivity itself, so the
    length-L threshold is `6 · sens · 1.5^log2 L / L` in data units.
  - Verified on synthetic data: a spike of 0.999 · 3.0 is kept and one of
    1.001 · 3.0 is flagged at `sens = 0.5`, and the same holds for a pair
    at the L = 2 threshold of 2.25.
  - A3 is used only for the hybrid kernel test (section 2.3).
- **A4. `high_pass_filter(data, xsize, ysize, xs, ys)`.**
  - The source passes `xs` and `ys` to `SetHKernelSigmaSq` and
    `SetVKernelSigmaSq`. They are the *variances* σ². The documentation
    calls them "Gaussian width".
  - The kernel is a sampled, unnormalised Gaussian of odd size, clipped
    at the image edges.
  - The filter is masked: low-pass(data·w)/low-pass(w). Where no weight
    survives, the low-pass value is set to 0, so the residual equals the
    data.
  - Tricolour's `masked_gaussian_filter` uses a 4-pass box cascade. Its
    radius is r = ⌊½√(12σ²/4 + 1)⌋, its support 8r + 1 and its effective
    variance 4((2r+1)² − 1)/12. Where no weight survives it returns NaN,
    and those values are interpolated linearly along frequency.
  - Tricolour's `_get_background2d` iterates `background_iterations`
    times with widths e·σ for e = n…1. Each pass rejects samples beyond
    `background_reject · 1.4826 · MAD` per frequency chunk, before the
    final filter.
  - The 3.5 Lua API has no per-sample threshold primitive: `sumthreshold`
    always runs all nine lengths, and the RMS thresholds act on whole
    rows. So that rejection loop **cannot be expressed**.
- **A5. `scale_invariant_rank_operator[_masked](data, [missing,] ηt, ηf)`.**
  This is SIR dilation (Offringa et al. 2012): it flags a sample when it
  lies in an interval whose flagged fraction is at least 1 − η. That is
  scale-invariant.
  - Tricolour smears by a fixed box: `time_extend: 3` and
    `freq_extend: 3`, i.e. ±1 sample, then applies the
    `flag_all_time_frac` (0.6) and `flag_all_freq_frac` (0.8) row and
    column cuts.
  - The Lua API has no box dilation and no fraction cut.
    `threshold_channel_rms` and `threshold_timestep_rms` threshold RMS
    statistics, which is a different rule.
- **A6. Spectrum.**
  - Tricolour flags a time-*median* spectrum: its own 1-D background,
    then SumThreshold along frequency with `windows_freq`, broadcast to
    all times.
  - The closest Lua translation is `downsample(data, ntime, 1, true)`.
    That is a masked time-*mean*, 1 × nchan. Then a 1-D `high_pass_filter`
    with `xsize = 1`, `sumthreshold_masked` along y only, and
    `upsample_mask(spec, full, ntime, 1)`. The last call replaces the
    destination mask, so it is joined afterwards.
- **A7. Other details.**
  - AOFlagger's sums are `float` (num_t) running sums. Tricolour
    accumulates float64 cumulative sums of float32 values.
  - Non-finite image values are replaced by 0 before thresholding
    (`MakeFiniteCopy`).
- **A8. Python API and polarisations.**
  - `ImageSet(width = ntime, height = nchan, count)` takes buffers
    `(nchan, ntime)`.
  - `strategy.run(imageset, flagmask)` returns the strategy's final mask.
    That is the input mask unless the strategy replaces it, which a
    probe confirmed.
  - With `count = 1`, the Lua `execute(input)` sees one real
    polarisation `I`: `is_complex() = false`, i.e. the amplitude
    representation.
  - The Lua state opens the standard libraries (`os.getenv` and `dofile`
    work), so the strategies read their per-stage parameters from a Lua
    table file named by `RANG_AFLAG_PARAMS`.

**Noise-estimator calibration** (synthetic, before any control data).

- For N(0, σ) samples of the control size (14 × 4096, 200 draws, seed
  20261030), AOFlagger's winsorized mode is **0.68273 σ ± 0.0022**.
  Tricolour's 1.4826 · median|x| is 0.99973 σ.
- So a Tricolour threshold of `nσ` corresponds to an AOFlagger
  sensitivity of **`0.2441 · n`**, i.e. 2.441 for `outlier_nsigma: 10`
  (`probe/calib.py`, kept in `outputs/aflag-20261030-01/probe/`).
- This constant is frozen. It is never fitted on the controls.

## 2. Protocol (frozen)

### 2.1 Input (identical for every AOFlagger run)

- **Controls.** Task D's four controls, from the archived oracle
  `outputs/core-d-oracle-20261029-01/run/<control>`:
  - `strategy-00-operational` and `strategy-00-holdout_masked` use
    CARACal's `mk_rfi_flagging_calibrator_fields_firstpass.yaml`;
  - `strategy-01-operational` and `strategy-01-holdout_masked` use
    `calibrator_mild_flagging.yaml`.
  - Each window is 10 baselines (4 autocorrelations) × 14 times × 4096
    channels, one polarisation product.
- **What AOFlagger is fed.** The core's polarised intensity
  √(|Q|² + |U|² + |V|²): the oracle's `intensity.npz`, bit-equal to the
  port's (task D criterion 4). It goes in as a single real image per
  baseline (count 1, polarisation I, amplitude).
- **Why not the MS directly.** AOFlagger has no mode for this quantity.
  Its `polarizations` option flags each listed polarisation separately
  and ORs the results, which is a different detector input. Feeding the
  same intensity isolates the flagging algorithm from the input
  definition.
- **Consequences for `flag_representations` and `polarizations`.** They
  are therefore `{"amplitude"}` and `{I}` trivially. The strategies do
  not call `convert_to_polarization` or `convert_to_complex`.
- **Input flags per stage.** For each `sum_threshold` step k, the input
  flags are the oracle's window flags *before* the step,
  `stages[k−1]`, as a `FlagMask`. Those are the same running flags
  Tricolour's step k received.
- **NaN cells.** Intensity cells that are NaN (all flagged by
  `flag_nans_zeros`) are given value 0. Their output is ORed with
  `isnan`, as `_get_flags_impl` does.
- **Assembling the stage output.** The driver ORs the step's detections
  with `stages[k−1]`, as the executor does. That gives the AOFlagger
  analogue of `stages[k]`.
- **Per-stage parameters.** Each `sum_threshold` step's YAML kwargs, with
  `core_flag.SUM_THRESHOLD_DEFAULTS` filled in, are written as a Lua table
  per stage.

### 2.2 The two Lua strategies (one Tricolour `sum_threshold` step each)

**Mapping of every YAML parameter** (mapped / tuned):

| Tricolour parameter | Mapped (`tricolour-firstpass.lua`) | Tuned (`tuned.lua`) | Documented difference |
| --- | --- | --- | --- |
| `outlier_nsigma` (10) | sensitivity 0.2441 · n | same | A1 estimator: one global winsorized mode per baseline against per-channel / per-chunk MAD |
| `windows_time` [1,2,4,8] | AOFlagger lengths 1–256 (only 1–8 fit 14 times) | same | none on these windows: time lengths ≤ 14 are exactly {1,2,4,8} |
| `windows_freq` [1,2,4,8]; very broad [32,48,64,128]; mild very broad default [1,2,4,8] | lengths 1–256 | same | A1: AOFlagger also runs 16–256 (resp. 1–16 and 256, without 48); not settable |
| `rho` (1.3) | fixed 4/3 | same | A1 |
| `background_reject`, `background_iterations` | not expressible; AOFlagger's own idiom instead: each major iteration recomputes the high-pass with the flags so far | not expressible (A4); omitted | A4 |
| `spike_width_time`, `spike_width_freq` | `high_pass_filter` with σ² = spike_width², size = Tricolour's support 8r+1 (odd) | σ² = the box cascade's effective variance 4((2r+1)²−1)/12, same size | A4 kernel shape, zero-weight handling |
| time-median spectrum + 1-D background + SumThreshold | masked time-mean spectrum (A6), 1-D high-pass, `sumthreshold_masked` y only, broadcast | same | A6 median vs mean |
| `freq_chunks` (10) | none (one image per baseline) | none | A1 |
| ordering: spectrum → time → frequency with time flags in the estimate | one `sumthreshold_masked` call, both directions interleaved | separate calls: time (x only), then frequency (y only) with spectrum and time flags in the estimate mask | A1 |
| flagged samples in the sums | excluded as `missing` (A2, AOFlagger's documented way) | set to 0 (`set_masked_visibilities` of a zero image, as `_average_freq`) and kept in the sums via `sumthreshold` | A1 clamp vs exclude |
| `time_extend`, `freq_extend` (3) | `scale_invariant_rank_operator_masked(·, missing, 0.2, 0.2)` (generic-default's η) per major iteration | none (not expressible) | A5 |
| `flag_all_time_frac`, `flag_all_freq_frac` | none | none | A5 |
| `num_major_iterations` (5 / 1) | same loop; iteration flags accumulate | same | none |
| `average_freq` (1) | nothing to do | same | none |
| return value: last major iteration's flags | same | same | none |

Kernel sizes and variances per `spike_width` value:

| σ | r | size 8r+1 | mapped σ² | tuned σ² |
| ---: | ---: | ---: | ---: | ---: |
| 12.5 | 10 | 81 | 156.25 | 146.667 |
| 10 | 8 | 65 | 100 | 96 |
| 6.5 | 5 | 41 | 42.25 | 40 |
| 2 | 1 | 9 | 4 | 2.667 |
| 64 | 55 | 441 | 4096 | 4106.667 |

The time axis has 14 samples, so time kernels are clipped by the image
edges in both implementations.

### 2.3 Hybrid kernel test (attribution at the SumThreshold kernel)

**Dump step.**

- `tools/oracles/aoflagger/tricolour_dump.py` runs in a uv venv with
  exactly RV1's `venv-tric021` resolution: Tricolour 0.2.1, NumPy 2.0.2,
  Numba 0.60.0, public PyPI.
- For every control, every `sum_threshold` step, baseline and major
  iteration, it re-chains the unmodified jitted Tricolour functions as
  `sum_threshold_flagger` and `_get_baseline_flags` do. The chain is
  `_average_freq`, `_time_median`, `_get_background2d`,
  `_sum_threshold` ×3, `_combine_flags`, `_unaverage_freq`.
- It saves the inputs and outputs of the three `_sum_threshold` passes
  (spectrum, time, frequency): the residual, the flags, the chunk ends,
  the windows, the raw output flags. It also saves the thresholds
  computed with `_median_abs_axis0` exactly as `_sum_threshold1d` does.
- **Gate.** The re-chain reproduces every oracle `sum_threshold` stage
  bitwise. If it fails, the hybrid test is void and is reported as such.

**AOFlagger run (`hybrid.lua`).** AOFlagger is fed each pass's residual,
normalised by Tricolour's own threshold of that column (time pass: per
channel) or chunk (spectrum and frequency passes: per time row and
chunk).

- In the spectrum and frequency passes, each (row, chunk) is one image
  column. It holds Tricolour's padded slice (the chunk ± (max window − 1),
  clipped at the band edges), and the unused tail is marked missing.
  Only the chunk's own cells are read back.
- Thresholds are absolute (A3) with `sens = 1/6`, so χ_L = 1.5^log2 L / L
  in units of Tricolour's χ₁. One direction per call.
- **H1:** padding is the only `missing`; flagged samples enter the sums
  with Tricolour's values. This is AOFlagger's kernel with Tricolour's
  input handling.
- **H2:** Tricolour's input flags of the pass are `missing` too. This is
  AOFlagger's documented input handling.

**NumPy bridge kernel** (`compare_aoflagger.py`). It has three switches:

- the window set and ρ: Tricolour's, or AOFlagger's 1–256 and 4/3;
- clamp or exclude;
- input flags as values or as missing.

It is validated at both ends:

- with Tricolour's settings it must equal the dumped raw flags bitwise;
- with AOFlagger's settings it must equal H1 and H2.

Differences at the AOFlagger end that lie within 1e-5 relative of a
threshold are counted as float rounding (A7).

**Kernel ladder, per pass.**

- K0 = Tricolour (dump).
- K1 = K0 with AOFlagger's lengths and ρ.
- K2 = K1 with exclusion instead of clamping. This should equal H1.
- K3 = K2 with the input flags as missing. This should equal H2.

Each step's flipped cells are counted. The order is fixed as written.

**Stage-level bridge.**

- S1 = Tricolour's whole `sum_threshold` step (re-chained in the
  Tricolour venv) with its three `_sum_threshold` calls replaced by the
  bridge kernel in the K3 setting. S1 gives the stage-level effect of
  the kernel alone.
- S0 = the oracle stage `stages[k]`. S2 = tuned. S2⁺ = tuned with Tricolour's box smearing and fraction cuts
  applied in Python to tuned's raw detections, as a labelled ablation
  outside AOFlagger. S3 = mapped.
- Attribution:
  - S0 → S1 is attributed to A1/A2;
  - S2 → S2⁺ to A5;
  - S1 → S2⁺ is the remaining bundle (A4, A6, A1's estimator and
    ordering, zeroing), reported with counts as "not separated";
  - S2⁺ → S3 is mapped-versus-tuned.

### 2.4 Chained run

The full CARACal strategy runs per control, with each `sum_threshold`
step done by AOFlagger (mapped or tuned) and every other step done by the
port. The port is called one step at a time through
`core_flag.flag_rows`, with row flags expanded from the running window
flags. `combine_with_input_flags` is done against the original packed
flags.

**Harness gate.** Before AOFlagger is substituted, the same harness with
the port's own `sum_threshold` must reproduce `after-native.npz` FLAG
bitwise on all four controls. If it fails, the chained result is not
reported.

The final FLAG is a **secondary** measure, stated in advance: the
`uvcontsub_flagger` steps *replace* the running flags, so they can hide or
amplify a `sum_threshold` difference.

### 2.5 Measures (frozen)

**Per isolated stage** (each `sum_threshold` step, each control, mapped,
tuned and the hybrids), against the oracle `stages[k]` and against the
fresh port run's `stages[k]`. Cells are split into *eligible* (unflagged
at entry, `~stages[k−1]`) and all. Cross-correlations and
autocorrelations are reported separately.

- the fraction of eligible cells on which A and B agree;
- `n_a_only` and `n_b_only`, i.e. cells flagged by one and not the other;
- the Jaccard index of the newly flagged sets;
- per-baseline counts of `a_only` and `b_only`;
- per-channel counts, summarised as the number of channels with any
  difference and the five channels with the most;
- **RFI windows.** These are the 4-connected components in (time,
  channel) of a stage's newly flagged cells, per baseline. A component of
  A is *matched* if at least one of its cells is newly flagged in B. The
  measure is the matched fraction of A's components and of B's
  components, plus the component counts.

**Final FLAG** (chained, secondary): the agreement fraction over all 140 ×
4096 × 4 elements, and `a_only` / `b_only`, against `after-native.npz` and
the port.

**Kernel ladder:** the flipped cells at each rung, per pass and stage;
the bridge's validation result at both ends; near-threshold counts.

### 2.6 Cost

- **AOFlagger.** Wall time and maximum RSS of the container's Python
  process running all `sum_threshold` steps of a control, isolated, from
  `/usr/bin/time -v` inside the container, together with its CPU%. The
  container is started once per strategy and control set, so the
  container start-up is reported separately.
- **Port.** The same isolated steps through `core_flag.flag_rows`
  (one `sum_threshold` step per call) at `RAYON_NUM_THREADS=1` (the
  matched number, since AOFlagger's Python run is one call per baseline)
  and `=4`, wall from `perf_counter` and RSS from `/usr/bin/time -v`.
- A fresh port run of `examples/run_core_flags.py` also confirms that the
  port still equals the archive.
- Reported, not gated. The host is shared with four other tasks, and the
  load average is recorded.

### 2.7 Decision (frozen)

- **Port matches the reference implementation, at kernel level.** This
  is claimed for a pass type (spectrum, time, frequency) only if H1 and H2
  differ from Tricolour's raw flags solely by cells the bridge ladder
  attributes to A1/A2. That requires the bridge to validate at both ends,
  with at most near-threshold rounding left over.
- **At stage level.** A `sum_threshold` step "matches" only if mapped or
  tuned agrees on every eligible cell, or if the whole difference is
  attributed by named rungs. A difference left in the "not separated"
  bundle does not count as attributed.
- **Otherwise.** The finding is recorded as a **difference between
  Tricolour's SumThreshold flagger and AOFlagger's**, with the named
  causes, and not as a defect of the port. Task D and RV1 established
  that the port equals Tricolour.
- **Prediction, written before running.** Stage-level agreement will be
  high but incomplete. The largest named contributors are expected to be
  A5 (no box smearing or fraction cuts in AOFlagger), the extra
  frequency lengths 16–256 and ρ = 4/3 (A1), and the background
  estimator (A4). At kernel level the ladder should close.

Failures of any gate are recorded as frozen. Any change after a run is a
labelled post-hoc step with its own run directory.

## Measured result

(Not yet run.)
