# A-FLAG: AOFlagger 3.5 as a second oracle for the SumThreshold port

Task A-FLAG of [big-plan.md](big-plan.md) (ecosystem survey section 5.2
item 7), started 2026-10-30 on branch `aflag-aoflagger` from `main`
`17adc1e`. The protocol below was frozen in its own commit, before any
AOFlagger or comparison code ran on the four task D controls. Only
synthetic data had been used at that point: the API probes and the
noise-estimator calibration in section 1.

Status (2026-10-31): **implemented; measured.** The protocol was frozen in
`4c3f7c7`; nothing above "Measured result" changed except through the
dated, labelled amendment there.

- **Kernel level: every difference attributed; the frozen match claim
  holds against AOFlagger's intended kernel, not against the shipped 3.5.0
  binary.** For all 48 passes (16 `sum_threshold` steps × spectrum, time
  and frequency), a NumPy bridge kernel reproduces both Tricolour's raw
  SumThreshold flags (the dump) and AOFlagger 3.5.0's own flags (the
  hybrid test) bit for bit.
  - Against AOFlagger with input flags kept as values (H1), and against
    AOFlagger's intended masked semantics (K3i), the ladder attributes
    every differing cell to A1/A2 alone: lengths 1–256 with ρ = 4/3,
    clamping against exclusion, and input flags as values against as
    missing. The spectrum pass also has one χ₁ = 0 chunk (408 cells),
    which a normalised input cannot express.
  - Against the shipped binary (H2) a further rung remains: an AOFlagger
    3.5.0 defect in the masked x-direction kernel, 24,253–225,955 cells
    per pass type. That rung is not A1/A2, so rule 2.7 is not met as
    frozen against H2.
  - The extra cells come from an AOFlagger bug, not from Tricolour or the
    port. This reading of 2.7 is labelled (deviation 8).
- **Stage level: no step matches.** Agreement on cells unflagged at entry
  is 0.60–0.95 for the mapped strategy and 0.63–0.95 for tuned. A large
  part of the gap is not separated, so under the frozen rule this is
  recorded as a difference between Tricolour's SumThreshold flagger and
  AOFlagger's, not a defect of the port.
- **The dominant named cause (post hoc)** is Tricolour's handling of
  input flags. `_average_freq` zeroes flagged samples, and they then enter
  every window as 0 − background. On these controls that, not RFI,
  produces almost all of the first step's new flags: removing it alone
  takes 93,341 new flags to 224.
- **Two AOFlagger 3.5.0 bugs, and one wrong frozen claim.**
  - Bug 1: `sumthreshold_masked` reads its direction arguments from the
    wrong Lua stack slots.
  - Bug 2: the masked horizontal kernel keeps one missing sample in the
    running sum.
  - The frozen A3 mechanism (`clear_mask` + `invert_mask`) did not do
    what the protocol said. Hybrid run `-04` is void; post-hoc run `-10`
    replaces it.
- **Final FLAG (chained, secondary):** 0.937–0.999 agreement with
  `after-native.npz`.
- **Cost:** AOFlagger spends 0.63–0.94 s per control on all
  `sum_threshold` steps (one thread); the port 0.92–1.48 s at one thread
  and 0.31–0.52 s at four.
- **Checks:** `bash tools/check-all.sh`, see section 10.

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
  - *Amendment 2026-10-31 (post hoc; see "Deviations"):* the
    verification above was flawed. The probe image was zero apart from the
    spikes, so the winsorized mode was 0 whatever the mask. The mask idiom
    used (`clear_mask` then `invert_mask`) leaves the mask empty in 3.5.
    A3 itself holds, re-verified on noise with an all-flagged mask made by
    `flag_zeros()` on a zero image.
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

All runs took place 2026-10-30/31 on the WSL host, load average 5–7 on
16 cores. Archive: [results/a-flag-aoflagger.json](results/a-flag-aoflagger.json)
(derived numbers only). The comparator is `examples/compare_aoflagger.py`.
A re-run of the comparator and of the port chain with the final, linted
code reproduces the archive exactly.

### 3. Implementation

| File | Role |
| --- | --- |
| `tools/oracles/aoflagger/Dockerfile`, `build.sh` | the pinned oracle image (section 1); `build.sh` records Id, size, build time and the debs |
| `tools/oracles/aoflagger/tricolour-firstpass.lua` | mapped strategy (one Tricolour `sum_threshold` step per call, parameters from `RANG_AFLAG_PARAMS`) |
| `tools/oracles/aoflagger/tuned.lua` | tuned strategy |
| `tools/oracles/aoflagger/hybrid.lua` | absolute-threshold SumThreshold for the hybrid kernel test |
| `tools/oracles/aoflagger/st_bridge.py` | NumPy bridge kernels: Tricolour's `_sum_threshold1d`, AOFlagger's `SumThresholdMissing::horizontal` (with and without the 3.5.0 defect) and `VerticalStacked`; column builders; Tricolour's smearing and fraction cuts |
| `tools/oracles/aoflagger/tricolour_dump.py` | Tricolour 0.2.1 re-chain, per-pass dump, gate, stage bridge S1 |
| `examples/oracle_aoflagger.py` | host driver and in-container runner: `stages`, `hybrid`, `chain`, `port-cost` |
| `examples/compare_aoflagger.py` | the frozen measures, the ladder, chain and cost; writes the archive |
| `tests/test_aflag.py` | 10 tests: bridge-kernel properties (reference semantics, the defect, ρ = 4/3, smearing), archive gates, ladder composition, one stage recomputed from `outputs/` (skips without) |

Every `.npz` written has its SHA256 in the run's `receipt.json`, with the
image Id, the Lua hashes and the input hashes. The Lua files were
committed first as the frozen runs used them (`b266fd6`; their hashes
equal those in the `-03` and `-04` receipts), then with the post-hoc fixes
(`3f50002`).

### 4. Runs

| Run | What | Status |
| --- | --- | --- |
| `outputs/aflag-20261030-00-upstream` | AOFlagger v3.5.0 source tarball, read as data (SHA256SUMS) | – |
| `-01` | image record (`image.json`, `image-debs.txt`), build log, synthetic probes | frozen, before data |
| `-02-dump` | Tricolour re-chain dump, S1 (time pass with intended semantics) | frozen; gate PASS 16/16 |
| `-03-stages` | mapped, tuned, tuned⁺ on the 16 isolated steps | frozen |
| `-04-hybrid` | hybrid kernel test | frozen, **void** (A3 mechanism and the direction bug; deviations 1–2) |
| `-05-chain-port` | chained harness with the port's own `sum_threshold` | frozen; gate PASS: 0 differences from `after-native.npz` on all four |
| `-06-chain-mapped`, `-07-chain-tuned` | chained, AOFlagger `sum_threshold` | frozen |
| `-08-port` | fresh `run_core_flags.py` | equals the oracle in every stage |
| `-09-port-cost` | port on the isolated steps, `RAYON_NUM_THREADS` 1 and 4 | frozen |
| `-10-hybrid` | hybrid with the fixed `hybrid.lua` and the x-only layout, plus width-1 vertical images | post hoc |
| `-11-stages`, `-12-chain-mapped` | mapped with the fixed spectrum direction (tuned and tuned⁺ re-ran bit-identical) | post hoc |
| `-13-compare` | comparator details (`details.npz`: per-baseline and per-channel arrays) | – |
| `-14-dump` | dump re-run; S1 with the validated AOFlagger kernel model | post hoc; gate PASS 16/16 |
| `-15-s1-variants` | S1 split into input handling and the rest (script kept there) | post hoc |

### 5. Kernel level: hybrid test and ladder

Precondition: the re-chain of the unmodified jitted Tricolour functions
reproduces all 16 oracle `sum_threshold` stages bitwise (`-02` and `-14`).

**Validation of the bridge at both ends.** Every count is 0, on all 48
passes. Each pass type sums over 4 controls × 4 steps × baselines ×
major iterations.

- NumPy Tricolour kernel = Tricolour's raw flags.
- K2 = H1: AOFlagger, input as values.
- K3 = H2: AOFlagger, input as missing, x direction, including the 3.5.0
  defect.
- K2v = H1v and K3v = H2v: the `VerticalStacked` model on width-1 images
  (spectrum and frequency passes).

No near-threshold rounding was needed.

**Ladder from Tricolour (K0) to AOFlagger (H2).** Cells flipped at each
rung, summed. In parentheses: cells not flagged at the pass's input.

| Pass | Cells | Tricolour flags | χ₁ normalisation (K0→K0n) | lengths 1–256, ρ 4/3 (→K1) | clamp → exclude (→K2) | input flags → missing (→K3i) | 3.5.0 x-direction defect (→K3 = H2) | Tricolour vs AOFlagger H2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| spectrum | 1,310,720 | 337,569 | 408 (0) | 34,210 (15,608) | 10,789 (10,150) | 350,218 (15,377) | 21,779 (11,141) | 330,818 (23,472) |
| time | 18,350,080 | 162,040 | 0 | 8,360 (1,815) | 198 (169) | 169,009 (2,159) | 24,253 (19,067) | 175,608 (20,334) |
| frequency | 18,350,080 | 4,276,986 | 0 | 1,253,845 (257,310) | 199,306 (157,077) | 5,468,858 (350,719) | 225,955 (116,325) | 4,284,514 (195,157) |

- The 408 normalisation cells are one spectrum chunk with χ₁ = 0
  (`strategy-00-holdout_masked`, step 02, baseline 1, iteration 1,
  chunk 7). The median |residual| is 0 there, so Tricolour flags every
  non-zero residual, and a normalised input cannot express that threshold.
- The time axis has 14 samples, so AOFlagger's time lengths are exactly
  Tricolour's {1, 2, 4, 8}. The time-pass length rung (8,360) is ρ = 4/3
  against 1.3 alone.
- AOFlagger's own two directions disagree on the same masked data:
  K3 (x) against K3v (y) differs in 29,647 spectrum and 298,810 frequency
  cells. That is the x-direction defect plus the y-direction zero tail,
  both AOFlagger implementation effects (deviation 3), not A1/A2.
- A 2-D AOFlagger strategy runs the spectrum and frequency passes along y,
  which has no x defect. Tricolour against H2v (y, input flags missing)
  differs in 336,247 spectrum cells (12,575 not input-flagged) and
  4,316,798 frequency cells (83,547). Against H1 (x, input as values) the
  counts are 44,511 (24,888), 8,556 (1,982) and 1,418,807 (394,395).

**Kernel decision (frozen rule 2.7, as a labelled reading; deviation 8).**
All three pass types have a validated bridge at both ends, and nothing is
left as near-threshold rounding.

- **Against H1 and against AOFlagger's intended masked kernel (K3i).**
  Every Tricolour–AOFlagger difference lies on A1 rungs (lengths, ρ,
  clamp against exclude) and A2 rungs (input handling). The only extra is
  the χ₁ = 0 spectrum chunk, a degenerate input of the normalised feed.
  **So at kernel level Tricolour's SumThreshold, and therefore the port, is
  AOFlagger's SumThreshold up to A1 and A2.**
- **Against the shipped 3.5.0 binary with input flags as missing (H2).**
  The x-direction defect is a further rung, and it is not A1/A2. As
  frozen, the rule is therefore not met against H2. The cells it adds
  come from an AOFlagger bug, not from Tricolour or the port.

### 6. Stage level

Agreement on eligible cells (unflagged at entry, all baselines). In
parentheses: cells flagged only by AOFlagger's side (+) and only by
Tricolour (−). The port equals Tricolour in every stage (`-08`), so the
numbers against the port are identical and are not repeated.

| Control | Step | Eligible | Tricolour new | mapped (frozen) | mapped (fixed spectrum) | tuned | tuned⁺ (A5 ablation) | S1 (Tricolour + AOFlagger kernel) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 00-op | 02 | 231,233 | 93,341 | 0.6052 (+10,790 / −80,494) | 0.6006 (+12,885 / −79,459) | 0.6279 (+14,510 / −71,530) | 0.7357 (+35,697 / −25,417) | 0.5974 (+786 / −92,317) |
| 00-op | 06 | 321,395 | 68,670 | 0.7726 (+13,418 / −59,666) | 0.7492 (+24,641 / −55,957) | 0.7221 (+40,320 / −49,002) | 0.6972 (+52,449 / −44,875) | 0.8375 (+8,915 / −43,327) |
| 00-op | 07 | 252,725 | 20,641 | 0.9016 (+6,053 / −18,822) | 0.9052 (+6,200 / −17,748) | 0.9094 (+7,034 / −15,862) | 0.9127 (+13,748 / −8,310) | 0.9219 (+12,696 / −7,039) |
| 00-op | 08 | 232,084 | 15,606 | 0.9302 (+1,147 / −15,048) | 0.9201 (+3,634 / −14,905) | 0.9048 (+9,395 / −12,689) | 0.9166 (+13,483 / −5,879) | 0.9368 (+7,321 / −7,356) |
| 00-ho | 02 | 60,342 | 13,691 | 0.7731 (+0 / −13,691) | 0.7731 (+0 / −13,691) | 0.7157 (+14,358 / −2,800) | 0.7731 (+0 / −13,691) | 0.7729 (+15 / −13,691) |
| 00-ho | 06 | 194,745 | 35,300 | 0.8072 (+4,798 / −32,757) | 0.7948 (+8,615 / −31,339) | 0.7470 (+21,375 / −27,892) | 0.7324 (+26,922 / −25,189) | 0.8432 (+4,174 / −26,369) |
| 00-ho | 07 | 159,445 | 11,122 | 0.9271 (+1,114 / −10,505) | 0.9300 (+1,371 / −9,795) | 0.9290 (+2,424 / −8,891) | 0.9360 (+5,290 / −4,915) | 0.9469 (+4,347 / −4,113) |
| 00-ho | 08 | 148,323 | 6,159 | 0.9549 (+555 / −6,141) | 0.9475 (+1,636 / −6,144) | 0.9479 (+2,660 / −5,073) | 0.9544 (+5,081 / −1,687) | 0.9477 (+3,577 / −4,187) |
| 01-op | 01 | 304,662 | 119,029 | 0.6265 (+12,777 / −101,018) | 0.6182 (+18,776 / −97,546) | 0.6404 (+20,609 / −88,939) | 0.7156 (+52,989 / −33,658) | 0.6090 (+692 / −118,429) |
| 01-op | 04 | 483,317 | 22,990 | 0.9284 (+19,218 / −15,399) | 0.8889 (+41,239 / −12,464) | 0.8515 (+62,164 / −9,632) | 0.8194 (+81,957 / −5,350) | 0.9188 (+34,400 / −4,843) |
| 01-op | 05 | 460,327 | 43,434 | 0.9005 (+9,492 / −36,292) | 0.8967 (+13,252 / −34,311) | 0.8899 (+23,059 / −27,630) | 0.8801 (+38,342 / −16,832) | 0.9324 (+21,095 / −10,023) |
| 01-op | 06 | 416,893 | 24,897 | 0.9359 (+4,288 / −22,427) | 0.9289 (+8,088 / −21,551) | 0.9219 (+17,129 / −15,419) | 0.9185 (+27,990 / −5,971) | 0.9441 (+11,342 / −11,967) |
| 01-ho | 01 | 73,720 | 21,067 | 0.7141 (+61 / −21,013) | 0.7141 (+61 / −21,013) | 0.7250 (+13,492 / −6,783) | 0.7142 (+0 / −21,067) | 0.7133 (+69 / −21,067) |
| 01-ho | 04 | 269,900 | 12,835 | 0.9336 (+6,052 / −11,856) | 0.9231 (+9,373 / −11,382) | 0.9030 (+17,604 / −8,587) | 0.8782 (+28,444 / −4,443) | 0.9215 (+15,103 / −6,082) |
| 01-ho | 05 | 257,065 | 18,442 | 0.9263 (+1,889 / −17,055) | 0.9275 (+2,196 / −16,441) | 0.9219 (+7,392 / −12,696) | 0.9198 (+15,335 / −5,274) | 0.9416 (+5,246 / −9,766) |
| 01-ho | 06 | 238,623 | 11,720 | 0.9506 (+581 / −11,199) | 0.9482 (+1,242 / −11,108) | 0.9421 (+5,620 / −8,202) | 0.9429 (+11,609 / −2,018) | 0.9489 (+3,494 / −8,698) |

00 = first-pass strategy; 01 = mild; op = operational; ho = holdout_masked.
The archive has the cross/auto split, per-baseline counts, the number of
channels with a difference (807–2,947 per step for the fixed mapped) and
the five worst channels. They are mostly in channels 3,170–3,825 near the
top of the band, often differing at all 140 baseline-times.

**RFI windows** (4-connected components of newly flagged cells per
baseline). For tuned⁺, 0.74–0.95 of Tricolour's windows are matched by
some AOFlagger cell, on every step apart from the two holdout first steps,
where tuned⁺ adds nothing (below). For tuned the figure is 0.44–0.73, and
mapped (fixed) matches only 0.00–0.49. The other way round, 0.33–0.99 of
mapped's windows and 0.34–0.93 of tuned's are matched by Tricolour.
Per-step values are in the archive (`rfi_windows`).

**Attribution of the stage differences.**

- **S0 → S1 (kernel only, A1/A2 + the AOFlagger defect).** Replacing only
  the kernel inside Tricolour's own pipeline removes almost all of
  Tricolour's new flags on the first step: 1,810 against 93,341 (00-op),
  1,292 against 119,029 (01-op). On the later single-iteration steps it
  removes about half.
- **Post-hoc split of S0 → S1** (`-15`). Tricolour's own kernel with *only*
  the input flags removed from the windows (compressed, as AOFlagger's
  `missing`) leaves 224 of 93,341 new flags on 00-op step 02, 112 of
  119,029 on 01-op step 01, and 0 on both holdout first steps. With
  AOFlagger's kernel but Tricolour's input handling, 157,961 cells are
  flagged on 00-op step 02.
- **Mechanism.** Tricolour's `_average_freq` sets flagged samples to 0.
  `_sum_threshold1d` uses the input flags only for the noise estimate,
  so a flagged sample enters every window as 0 − background. Wherever the
  background (the polarised intensity's level) exceeds χ₁, every input
  flag is a negative outlier. Its windows and the box smearing then flag
  its neighbours, and with 5 major iterations the growth repeats. On these
  controls (47–90 % flagged at entry to the first step, high-SNR
  calibrator baselines) that
  growth is most of what the first `sum_threshold` step adds. AOFlagger's
  documented handling (`missing`) cannot grow input flags. This is the
  single largest named difference between the two flaggers here, and it
  is a property of Tricolour/katsdpsigproc, not of the port.
- **S2 → S2⁺ (A5).** Adding Tricolour's box smearing and fraction cuts to
  tuned changes 5,807–130,967 eligible cells per step
  (`bridge_tuned_vs_tuned_plus`). It raises the share of Tricolour's
  windows matched from 0.44–0.73 to 0.74–0.95.
- **The holdout first steps under tuned⁺ (00-ho 02, 01-ho 01).**
  - tuned⁺ returns no new flag. A trace (post hoc) shows major
    iterations 1–2 adding about 10,000 cells on a cross-correlation
    baseline, then nothing.
  - Tricolour returns only the *last* major iteration's flags
    (`sum_threshold_flagger` returns `out_flags`, not the accumulated
    `iter_flags`), so the step returns nothing.
  - Mapped also adds nothing there, for a different reason. AOFlagger's
    global noise estimate on its high-passed residual puts χ₁ at roughly
    13σ (MAD), not 10σ (estimated from a sensitivity scan, post hoc), and
    `missing` stops input-flag growth, so nothing exceeds it.
  - Tricolour itself avoids this only because the input-flag growth
    re-detects in every iteration. The S1 split is consistent with this:
    with the input flags removed from the windows, Tricolour's own kernel
    also returns nothing on those two steps.
- **S1 → S2⁺ (not separated).** This bundle holds:
  - the background estimator (A4: the box cascade with rejection loop
    and NaN interpolation, against a sampled Gaussian with zero-weight
    → 0);
  - the global winsorized-mode noise estimate against the per-channel
    and per-chunk MAD (A1);
  - interleaving and order;
  - mean against median spectrum (A6);
  - zeroing.

  The eligible-cell differences are in `bridge_s1_vs_tuned_plus`
  (13,346–138,312 per step; 15 and 69 on the two holdout first steps).
  They are **not attributed cell by cell**, as the protocol anticipated.
- **S2⁺ → S3 (mapped against tuned⁺).** 9,206–142,224 eligible cells per
  step (0 and 115 on the holdout first steps). Mapped has no smearing and
  cuts, uses `missing`, and uses nominal σ² and SIR dilation.

**Stage decision (frozen rule).** No `sum_threshold` step agrees on every
eligible cell, and on every step part of the difference is in the
not-separated bundle. The claim "the port matches the reference
implementation" is therefore **not** made at stage level. The finding is
recorded as a difference between Tricolour's SumThreshold flagger and
AOFlagger's, with the named causes above. Task D and RV1 established that
the port equals Tricolour.

### 7. Chained run (secondary)

The harness gate passes: the port's own steps, one at a time, reproduce
`after-native.npz` at all 4 × 2,293,760 elements. Final FLAG agreement
against `after-native.npz` (= the port) over all elements, with (+)
cells flagged only by the chain and (−) cells flagged only by Tricolour:

| Control | Tricolour flagged | mapped (frozen) | mapped (fixed) | tuned |
| --- | ---: | ---: | ---: | ---: |
| 00-op | 0.80641 | 0.95027 (+5,804 / −108,272) | 0.94602 (+17,512 / −106,300) | 0.93685 (+57,436 / −87,424) |
| 00-ho | 0.91789 | 0.97657 (+816 / −52,936) | 0.97693 (+252 / −52,676) | 0.97427 (+13,940 / −45,080) |
| 01-op | 0.71847 | 0.99079 (+2,820 / −18,316) | 0.98864 (+10,128 / −15,936) | 0.98647 (+16,828 / −14,208) |
| 01-ho | 0.87272 | 0.99860 (+268 / −2,936) | 0.99687 (+4,240 / −2,936) | 0.99696 (+4,040 / −2,928) |

The final agreement is higher than the per-stage agreement because the
`uvcontsub_flagger` steps replace the running flags and the static mask
and `combine_with_input_flags` dominate the end state, as stated in
advance.

### 8. Cost

All `sum_threshold` steps of one control, isolated, same inputs. The host
load average was 5–7 throughout.

| Control | AOFlagger mapped: strategy s / process wall / RSS / CPU | tuned | tuned⁺ | port `RAYON=1`: core s / process wall / RSS | port `RAYON=4` |
| --- | --- | --- | --- | --- | --- |
| 00-op | 0.72 s / 1.04 s / 82 MB / 99 % | 0.68 s / 1.03 s / 84 MB | 0.83 s / 1.13 s / 82 MB | 1.48 s / 1.84 s / 84 MB | 0.52 s / 0.91 s / 93 MB (236 %) |
| 00-ho | 0.72 s / 1.06 s / 82 MB / 99 % | 0.63 s / 0.99 s / 83 MB | 0.87 s / 1.21 s / 83 MB | 1.48 s / 1.84 s / 84 MB | 0.48 s / 0.83 s / 94 MB |
| 01-op | 0.75 s / 1.14 s / 81 MB / 99 % | 0.69 s / 1.05 s / 83 MB | 0.94 s / 1.28 s / 83 MB | 0.98 s / 1.34 s / 84 MB | 0.33 s / 0.72 s / 92 MB |
| 01-ho | 0.71 s / 1.05 s / 82 MB / 99 % | 0.63 s / 0.99 s / 83 MB | 0.89 s / 1.24 s / 83 MB | 0.92 s / 1.34 s / 84 MB | 0.31 s / 0.73 s / 92 MB |

- AOFlagger's Python run is one thread (99 % CPU; one `strategy.run` per
  baseline). Each container start adds about 0.4 s
  (`docker_wall − process wall`).
- At matched threads the port costs about 1.3–2.1× AOFlagger's strategy
  time. It also does more work than the Lua strategies: the 5-pass
  background rejection, three separate SumThreshold passes with
  per-column statistics, and the smearing and cuts.
- At four threads the port is faster than single-threaded AOFlagger.
  RSS is equal within 10 MB and dominated by Python and NumPy.
- No speed conclusion beyond this is drawn. The workloads are small,
  14 × 4096 per baseline.

### Deviations (all labelled; frozen results kept)

1. **A3 mechanism wrong in the frozen `hybrid.lua` (run `-04` void).**
   - `clear_mask()` removes the mask, and `invert_mask()` then changes
     nothing, so AOFlagger's own noise estimate stayed on.
   - The frozen synthetic "verification" could not detect this: the probe
     image was zero apart from the spikes.
   - Found when the bridge disagreed with `-04`, before any `-04` number
     was used. Fixed with `flag_zeros()` on a zero image, re-verified on
     N(0, 0.01) noise (`posthoc/probe5.py`), and re-run as `-10`.
2. **AOFlagger 3.5.0 direction-argument bug.**
   - `Functions::sumthreshold_masked` (`lua/functionswrapper.cpp`) reads
     `horizontal = lua_toboolean(L, 4)` and `vertical = lua_toboolean(L, 5)`.
     The direction arguments are 5 and 6, and argument 4 is the y
     threshold factor, which is always true in Lua.
   - Shown with a probe (`probe9.py`): (true, false) runs both directions;
     (false, true) runs x only.
   - Consequence 1, the frozen mapped run: its spectrum call (false, true)
     ran only an L = 1 threshold on the width-1 spectrum. The fixed mapped
     calls (true, true), which is exactly the intended y pass there; it ran
     post hoc as `-11` and `-12`. tuned uses `sumthreshold`, which is
     unaffected, and re-ran bit-identical.
   - Consequence 2, the hybrid: it lays every pass out along x, and
     validates y separately on width-1 images (H1v/H2v).
3. **An AOFlagger 3.5.0 defect in `SumThresholdMissing::horizontal`, found
   by the bridge.**
   - After the initial loop, xRight can point at a missing sample. The
     main loop then adds it, because it tests only the mask, and never
     subtracts it, because xLeft visits only non-missing samples.
   - It stays in the sum and the count for the rest of the row.
   - The bridge models it (`quirk=True`): 0 differences from AOFlagger on
     synthetic data (`probe11.py`) and on all real passes. The intended
     semantics give 655 differences on the same synthetic set.
   - The y direction (`VerticalStacked`) instead pads the compacted column
     with zero-valued samples: 4 differences against the intended
     semantics in 40 synthetic columns, modelled exactly.
4. **S1 in `-02` used the intended x-direction semantics.** It was re-run
   in `-14` with the validated model of what AOFlagger does; the gate
   re-passed. The archive uses `-14`.
5. **Hybrid driver layout bug, first `-04` attempt.** A transposition error
   in the driver made the host-side assembly fail after the container ran.
   That directory was deleted and re-run under the same name before any
   result was read. It was then voided for deviation 1 anyway.
6. **Post-hoc analyses beyond the protocol** (labelled):
   - the S1 split (`-15`);
   - the tuned⁺ iteration trace;
   - the noise-estimate comparison on Tricolour's residual (AOFlagger's
     winsorized mode is 0.64–0.76 of the MAD σ on Tricolour's residual,
     as calibrated);
   - the cross/auto and channel listings.
7. **Not done.**
   - Feeding the MS to the `aoflagger` CLI, which section 2.1 rejected in
     advance.
   - A `rang-core` CLI stage. It is not needed: the oracle is a research
     tool, not a pipeline stage.
8. **Reading of decision rule 2.7.** The frozen rule asks that H1 and H2
   differ from Tricolour "solely by cells the bridge ladder attributes to
   A1/A2". The defect of deviation 3 was unknown at freezing, and it adds
   a non-A1/A2 rung between AOFlagger's intended kernel (K3i) and the
   shipped binary (H2).
   - The kernel-level claim is therefore made against H1 and K3i, where
     the rule holds.
   - Against H2 the rule is reported as not met, with the extra cells
     attributed to the AOFlagger defect.
   - The χ₁ = 0 chunk (408 spectrum cells) is a property of the
     normalised hybrid feed, not of either kernel.

   This reading was made after the results and is labelled as such.
9. **Post-hoc scripts.** The scripts behind the post-hoc numbers and the
   bug evidence are committed under `tools/oracles/aoflagger/posthoc/`:
   - `s1_values.py` and `s1_measure.py`: the S1 split, run `-15`;
   - `probe5.py`: the A3 re-verification;
   - `probe9.py`: the direction-argument bug;
   - `probe11.py`: the x-direction defect and the y zero tail;
   - `trace_tuned_plus.py`: the tuned⁺ iteration trace.

   Run the probes as `docker run --rm --network none -v $PWD:/work:ro -v
   $PWD/outputs:/work/outputs:ro -v
   $PWD/tools/oracles/aoflagger/posthoc:/probe:ro
   rang-aflag-aoflagger:3.5.0 python3 /probe/<probe>.py`. The other
   ad-hoc probes are kept in `outputs/aflag-20261030-01/probe/`.

### Open items

- **Upstream reports**, AOFlagger's tracker (non-RATT) and Tricolour
  (RATT): listed in "For the coordinator"; nothing was sent.
- **Not separated.** The stage-level bundle S1 → S2⁺ (background
  estimator, global noise estimate, ordering, spectrum statistic) is not
  separated cell by cell. Doing so needs either a bitwise NumPy model of
  `HighPassFilter`, or Tricolour's background injected into AOFlagger via
  an image subtraction. The second would be a natural A-FLAG-2 rung.
- **Develop branch not checked.** Whether AOFlagger develop still has the
  two 3.5.0 defects was not checked (no network use beyond the tarball).
- **Tricolour design question.** The input-flag growth (section 6) may be
  intended, as conservative flagging next to known-bad data. A rang-native
  recipe would want it as an explicit, measurable option.

### 9. Timings

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-30 | curl AOFlagger v3.5.0 tarball (gitlab) | 989 KB | 0.95 s | – | read as data |
| 2026-10-30 | `docker build` `rang-aflag-aoflagger:3.5.0` (KERN-10 debs) | Dockerfile | 91.1 s | – | 427 MB image |
| 2026-10-30 | `uv venv` + `uv pip install -e .[pointing,beam,test,imaging]` (worktree) | repo | 202.6 s | 1.1 GB | builds `rang._core` |
| 2026-10-30 | `uv venv` + Tricolour 0.2.1 lock (RV1 resolution) | 26 pins | 0.9 s | – | cached wheels; freeze identical to RV1 |
| 2026-10-30 | AOFlagger probes in the container | synthetic | 0.5–2 s each | – | about 15 probes |
| 2026-10-30 | `tricolour_dump.py` (Tricolour 0.2.1, Numba 0.60) | 4 controls, 16 steps | 89.2 s | 413 MB | includes Numba compilation; gate PASS |
| 2026-10-30 | `oracle_aoflagger.py stages` (AOFlagger 3.5.0) | 12 container runs | 19.6 s | 81–86 MB | 0.99–1.28 s per run, 99 % CPU |
| 2026-10-30 | `oracle_aoflagger.py hybrid` (frozen, void) | 4 runs | 12.7 s | – | |
| 2026-10-30 | `oracle_aoflagger.py chain` port / mapped / tuned | 4 controls each | 3.3 / 19.0 / 20.3 s | – | 4 container runs per control for the AOFlagger chains |
| 2026-10-30 | `run_core_flags.py` (fresh port run) | 4 controls | 3.6 s | 109 MB | 199 % CPU at `RAYON=4` |
| 2026-10-30 | `oracle_aoflagger.py port-cost` | 4 controls × 2 thread counts | 0.7–1.8 s each | 84–94 MB | |
| 2026-10-31 | `oracle_aoflagger.py hybrid` (post hoc `-10`) | 4 runs, about 24,000 images each | 13.7 s | – | |
| 2026-10-31 | `oracle_aoflagger.py stages` / `chain mapped` (post hoc) | | 12.0 / 9.2 s | – | |
| 2026-10-31 | `tricolour_dump.py` (post hoc `-14`) | 4 controls | 41.7 s | 331 MB | Numba cache warm |
| 2026-10-31 | `s1_values.py` (post hoc `-15`) | 4 controls | 37.0 s | 198 MB | |
| 2026-10-31 | `compare_aoflagger.py` | all runs | 139.6 s | 152 MB | first full run 101.3 s |
| 2026-10-31 | `bash tools/check-all.sh` | worktree | see section 10 | – | |

### 10. Checks

`bash tools/check-all.sh` (plain, `OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=4`)
before the final commit: CHECKALL_RESULT; log
`outputs/aflag-20261030-check-all.log`. No CLI stage was added, so
`docs/cli.md` is unchanged.

## For the coordinator

**Shared-file lines.** None of these are applied on the branch, and no
test needs them.

- `research/README.md`, index entry:
  "New, 2026-10-31: A-FLAG, [AOFlagger 3.5 as a second SumThreshold
  oracle](a-flag-aoflagger.md): at kernel level the port is AOFlagger's
  intended SumThreshold up to its documented differences (A1/A2), bridged
  bit for bit; against the shipped 3.5.0 binary an AOFlagger defect adds
  more. At stage level the flaggers differ: 0.60–0.95 agreement, mostly
  from Tricolour growing input flags. Two AOFlagger 3.5.0 bugs found."
- `research/big-plan.md`, line 269: replace "A-FLAG (AOFlagger as second
  SumThreshold oracle)" with "A-FLAG (done 2026-10-31,
  `a-flag-aoflagger.md`: kernel-level match with AOFlagger's intended
  kernel up to A1/A2, every difference attributed, the shipped 3.5.0
  binary adds a defect; stage-level difference, mostly Tricolour's input-flag
  growth; two AOFlagger 3.5.0 bugs; image `rang-aflag-aoflagger:3.5.0`)".
- `README.md`, after "the Tricolour strategies (`rang.core_flag`; …
  BSD notice)": add "; AOFlagger 3.5 is a second oracle for them
  (`tools/oracles/aoflagger/`, `research/a-flag-aoflagger.md`)".
- `research/tool-timings.md`: the rows of section 9, with the check-all
  row filled in, prefixed "big plan A-FLAG:".
- `research/upstream-notes.md` and `research/non-ratt-observations.md`:
  the two blocks below.
- `python/rang/core_cli.py`: none. No CLI stage, because the oracle is a
  research tool.

**STATE paragraph** (new top entry):

> A-FLAG AOFlagger second oracle (big plan), 2026-10-31 (implemented;
> measured; [a-flag-aoflagger.md](a-flag-aoflagger.md)). Protocol frozen
> first. A pinned image, `rang-aflag-aoflagger:3.5.0` (Ubuntu 24.04 +
> KERN-10 AOFlagger 3.5.0, python-casacore 3.7.1), runs Lua translations of
> CARACal's Tricolour first-pass (and mild) `sum_threshold` steps on the
> core's polarised intensity for task D's four controls. Two strategies:
> mapped (AOFlagger idiom) and tuned (as close as the Lua API allows).
> **Kernel level: every difference attributed.** A NumPy bridge
> reproduces both Tricolour's raw SumThreshold flags (re-chained from the
> unmodified 0.2.1 functions, gate 16/16) and AOFlagger's own flags
> (absolute thresholds, hybrid test) bit for bit on all 48 passes.
> Against AOFlagger's intended kernel every differing cell lies on the
> documented differences: fixed lengths 1–256 with ρ = 4/3 (against
> 1.3), clamping against exclusion, and input flags as values against as
> missing. One χ₁ = 0 chunk adds 408 cells. So the port is AOFlagger's
> SumThreshold up to those. Against the shipped 3.5.0 binary, a further
> AOFlagger defect adds cells, so the frozen rule is not met there (a
> labelled reading).
> **Stage level: the flaggers differ.** On cells unflagged at entry,
> mapped agrees 0.60–0.95 and tuned 0.63–0.95; the final FLAG agrees
> 0.937–0.999. The largest cause (post hoc) is Tricolour itself: flagged
> samples enter its windows as 0 − background, so on high-SNR baselines
> every input flag is detected and grown. Removing only that takes the
> first step's 93,341 new flags to 224. Two AOFlagger 3.5.0 bugs:
> `sumthreshold_masked` reads its direction flags from the wrong Lua
> arguments, and the masked horizontal kernel keeps one missing sample in
> the running sum. The frozen hybrid run was void (wrong all-flagged-mask
> idiom); post-hoc fixes are labelled. Cost: AOFlagger 0.63–0.94 s per
> control on one thread, the port 0.92–1.48 s on one and 0.31–0.52 s on
> four. Next: none required. Upstream reports wait for the user's say.

**Upstream observations, AOFlagger (non-RATT;
`research/non-ratt-observations.md`, "From A-FLAG (2026-10-31; not
reported by decision)")**:

| Software | Observation | Evidence | What a report would say | Status |
| --- | --- | --- | --- | --- |
| AOFlagger 3.5.0 | `Functions::sumthreshold_masked` (`lua/functionswrapper.cpp`) checks Lua arguments 5 and 6 are booleans, but reads `horizontal = lua_toboolean(L, 4)` and `vertical = lua_toboolean(L, 5)`. The x pass therefore always runs (argument 4 is a number) and the y pass follows `x_direction`. Calls with (true, true), as the shipped strategies use, are unaffected. | `a-flag-aoflagger.md` deviation 2, `tools/oracles/aoflagger/posthoc/probe9.py` | Read arguments 5 and 6 | not reported by decision |
| AOFlagger 3.5.0 | `SumThresholdMissing::horizontal`: after the initial loop xRight can point at a missing sample, which the main loop adds (it tests only the mask) and never subtracts (xLeft visits only non-missing samples). It stays in the sum and the count for the rest of the row, so the x and y masked SumThreshold disagree on the same data (here 298,810 frequency cells). | deviation 3; bridge model exact against AOFlagger on 48 real passes and on synthetic images | Skip missing samples before the first add, as the do-while does later | not reported by decision |
| AOFlagger 3.5.0 | `high_pass_filter` and `low_pass_filter` document `xsigma`/`ysigma` as Gaussian widths, but pass them to `SetHKernelSigmaSq`/`SetVKernelSigmaSq`: they are variances | `lua/functions.cpp`, `lua_functions.rst` | Documentation fix | not reported by decision |
| AOFlagger 3.5.0 | `Data:clear_mask()` removes the mask (`SetNoMask`), after which `invert_mask()` is a silent no-op. Not a bug, but the obvious "flag everything" idiom fails without an error. | deviation 1 | Documentation note, or make `invert_mask` create the mask | not reported by decision |
| AOFlagger 3.5.0 | `VerticalStacked` pads the compacted column with zero-valued, unflagged samples to the full height, so y windows can extend past the last valid sample. The x direction stops at it. Small effect: 4 cells in 40 synthetic columns. | `tools/oracles/aoflagger/posthoc/probe11.py` | Note, or stop at the valid length | not reported by decision |
| KERN-10 `aoflagger` 3.5.0-1kern1 | The Python module installs as `/usr/lib/aoflagger.cpython-312-x86_64-linux-gnu.so`, off `sys.path`, so `import aoflagger` fails until `PYTHONPATH=/usr/lib` | Dockerfile | Install to `dist-packages` | not reported by decision |

**Upstream observations, Tricolour (RATT; for `research/upstream-notes.md`,
"A-FLAG observations (2026-10-31; observed, not raised)")**. Candidates to
file once the user says so:

- **Input flags take part in SumThreshold.**
  - `_average_freq` zeroes flagged samples. `_sum_threshold1d` uses the
    input flags only for the noise estimate, so a flagged sample enters
    every window as 0 − background.
  - Wherever the background exceeds χ₁, every input flag is detected as a
    negative outlier. The windows, `time_extend` and `freq_extend` then
    grow it, and each major iteration repeats the growth.
  - On the four A-FLAG controls this makes almost all of the first
    `sum_threshold` step's new flags: 93,341 → 224 and 119,029 → 112 when
    only this is changed.
  - AOFlagger removes flagged samples instead (`missing`).
  - The code is inherited from katsdpsigproc `twodflag.py`. Worth a
    question: is the growth intended, and should it be a documented option?
- **Only the last major iteration is returned.** `sum_threshold_flagger`
  returns the last major iteration's `out_flags`, not the accumulated
  `iter_flags`. If a later iteration finds nothing new, the earlier
  iterations' detections are discarded. The tuned⁺ ablation shows this on
  the holdout controls: iterations 1–2 add about 10,000 cells, and the
  step returns none.
- **Documented differences, no report needed.**
  - `rho: 1.3` against AOFlagger's fixed ρ = 4/3.
  - The window sequence.
  - A per-channel and per-chunk MAD estimate against AOFlagger's global
    winsorized mode.

**Ignored output directories** (under the main checkout's `outputs/`,
reached through the worktree symlink):

| Directory | Size | Content |
| --- | ---: | --- |
| `aflag-20261030-00-upstream` | 5.8 MB | AOFlagger v3.5.0 source tarball + extract (data) |
| `aflag-20261030-01` | 152 KB | image record, deb list, build log, probes |
| `aflag-20261030-02-dump` | 88 MB | Tricolour per-pass dump (frozen) |
| `aflag-20261030-03-stages` | 1.2 MB | mapped, tuned, tuned⁺ stages (frozen) |
| `aflag-20261030-04-hybrid` | 5.3 MB | hybrid (void) |
| `aflag-20261030-05-chain-port`, `-06-chain-mapped`, `-07-chain-tuned` | 0.6 + 1.0 + 1.1 MB | chains |
| `aflag-20261030-08-port` | 29 MB | fresh port run |
| `aflag-20261030-09-port-cost` | 76 KB | port cost records |
| `aflag-20261030-10-hybrid` | 2.6 MB | hybrid (post hoc) |
| `aflag-20261030-11-stages`, `-12-chain-mapped` | 1.2 + 1.0 MB | fixed mapped (post hoc) |
| `aflag-20261030-13-compare` | 212 KB | `details.npz` |
| `aflag-20261030-14-dump` | 88 MB | dump re-run, S1 (post hoc) |
| `aflag-20261030-15-s1-variants` | 372 KB | S1 split and its two scripts (post hoc) |
| `aflag-20261030-check-all.log` | – | check-all log |

`-02` and `-14` dominate the space, at 176 MB together; they can be
deleted once the branch merges, because the archive keeps the derived
numbers. The image `rang-aflag-aoflagger:3.5.0` (427 MB) stays in the local
Docker store.
