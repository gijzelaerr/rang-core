# gmclean: lazy exact CLEAN with a certified step

Status, 2026-11-02: **implemented and tested; accuracy measured on simulated
MeerKAT data and the LUNO slice; every time is PROVISIONAL** (shared host, load
average 4 to 25; no final speed claim is made here and none should be quoted).
Branch `gmclean`. Code: `core/src/gmclean.rs`, `core/src/gmclean/` (`kernels`,
`fits`, `input`, `measure`, `sim`, `host`), `core/src/bin/gmclean.rs`,
`core/examples/gmclean_sim.rs`, `examples/gmclean_compare.py`,
`wgridder::Prepared` (additive), `formal/RangFormal/Gmclean.lean`. Archives:
[results/gmclean.json](results/gmclean.json) (the 1024² simulated MS, with the
timing benchmark) and
[results/gmclean-optimisation.json](results/gmclean-optimisation.json) (the
bisection, the stop rules, the sweeps at 2048²). Benchmark and its datasets:
[gmclean-benchmark.md](gmclean-benchmark.md) on `origin/gmclean-bench`.

Credit: the exact per-step correction, the larger patch and the drift stopping
signal were suggested by an early reader of the draft on 2026-11-02.

## 1. Summary

- **Implemented.** The lazy exact minor cycle of §2, an MS-to-FITS binary with
  WSClean-like flags, SIMD kernels with runtime dispatch, a real-input FFT resync,
  a gridder plan kept between major cycles.
- **Measured, the main result.** A long minor cycle fits the phase-centre beam's
  off-centre error as false components (§4). The default now ends a cycle at the
  pointwise error the previous major cycle measured. On S1, S2 and S3 that gives
  **5, 5 and 4 major cycles and 4.3, 4.9 and 1.6 mJy of false flux**, against
  WSClean's Högbom loop at 6, 6 and 5 cycles and 5.4, 6.7 and 1.7 mJy, and its
  fast loop at 9, 9 and 6 cycles and 3.5, 3.2 and 1.5 mJy. gmclean reaches the
  threshold exactly (inner peak 100 µJy against 102-117 and 197-245 µJy).
- **Negative results.** The "1-3 major cycles" this design expected do not exist
  at low false flux on these skies: 4 cycles at `-mgain 0.99` carry 72-77 mJy of
  false flux. The large speedups an image-domain Gram step seemed to promise come
  mostly from where the gridder is cheap; the gridder is about 60 % of the time
  and was already at ducc0's speed. The slice's central flux is still −12.4 %.
- **Regression found by the benchmark, fixed.** `961e162` made a cycle whose gap
  was small run to the threshold: 1,000,000 components, 20.3 Jy false flux on S1.
  §4.1.

## 2. Design (implemented)

The provable rule of [clean-certified-imaging.md](clean-certified-imaging.md)
bounds the beam-truncation error by the worst case `f Σ|c_j|`. gmclean replaces
the bound with the exact value at the one pixel about to be cleaned.

1. **Exact beam.** The PSF on the `2n × 2n` grid holds every offset two image
   pixels can have. Its FFT is cached.
2. **Lazy exact Högbom minor cycle.** A working map `r̃` takes the beam within
   `±P` only. For the candidate `p = argmax |r̃|` the exact value is
   `r_p = r̃_p − Σ_{j: ‖x_p − x_j‖_∞ > P} c_j b(x_p − x_j)` over the components
   since the map was last exact. (The brief wrote `+`; with `r̃ = d − Σ c b_patch`
   the sign is `−`, and the audit test confirms it.) The component is
   `c = γ r_p / b(0)`.
3. **Resync.** On drift (`|r_p − r̃_p| > d |r̃_p|`, default `d = 0.1`), on a weak
   certificate (`τ_k < τ_min`, default 0.5), every `K` components (default 2000)
   and before deciding that the peak is below the threshold, the map is rebuilt by
   one FFT pair on the `2n` grid as `r̃ = r_major − B (m − m_major)`. The delta
   matters: `r_major` already carries the w-term. No visibility is touched.
4. **Major cycles** run the model through the gridder, and record the Gram gap
   `ΔQ_exact − ΔQ_predicted` and the pointwise stale error
   `‖r_exact − r̃‖_∞`. Termination is decided on the exact peak of the measured
   residual, never on the gap: the cycle that produced 20 Jy of false flux has a gap
   of 1.1 % of its predicted decrease, far inside the forcing rule's 50 % allowance
   (agreeing with [clean-major-cycles.md](clean-major-cycles.md) on
   `origin/clean-major-cycles`).
5. **When a cycle hands back** (`CycleStop`). Default `MeasuredStale { rho: 1,
   g: 0.95 }`: the first cycle ends at `(1 − g)` of its first peak; later cycles
   end once `|r_p| ≤ ρ δ Σ|c|`, with `δ = ‖r_exact − r̃‖_∞ / Σ|c|` from the previous
   major cycle. `-mgain g` selects `PeakFraction(g)`, which is WSClean's `-mgain`
   and only now the same setting; `-mgain-misfit f` the misfit fraction of the
   first version, a different setting; `-minor-to-threshold` no hand-back.
6. **Restoring.** A Gaussian fitted by linear least squares to `−ln b` over the
   connected pixels above half maximum, convolved by the same FFT machinery. BPA
   is measured in the FITS frame (north `+y`, east `−x`).
7. **The binary** reads an MS with the core reader, forms Stokes I and WSClean's
   imaging weights by the rules of `examples/clean_certified_export.py`, and
   writes `-dirty`, `-psf`, `-model`, `-residual`, `-image` FITS and `-report.json`.
   The MS sign is `exp(+2πi(ul+vm+w(n−1)))`: a test puts a source east and north
   of the centre where the WCS says.

## 3. What is proven about a step

"Exact" means exact **for the image-domain beam at the phase centre**. It is not a
statement about the visibility-space misfit or the sky: §4 is what happens where
that beam is wrong. The per-step certificate held throughout the 20 Jy run.

| Claim | Status | Pointer |
| --- | --- | --- |
| The exact value follows from the working value through the ignored beam | Lean | `Clean.exact_value_identity` |
| A step with the exact value lowers the misfit by `γ(2−γ)/2 r_p²` at any proposed pixel | Lean | `Clean.exact_value_step`, `Clean.misfit_step` |
| `|r_p| ≥ τ (M + e)` with stale error `≤ e` and `|r̃| ≤ M` makes the pick `τ`-weak greedy | Lean | `Clean.certificate_bound`, `Clean.weak_greedy_of_certificate` |
| With `τ_k ≥ τ_min > 0` at every step the residual tends to zero | Lean, applying | `Clean.dirty_tendsto_zero` |
| The run enforces `τ_k ≥ τ_min` | tested, not formalised | `exact_steps_audit_and_gap_on_the_direct_measurement` |
| Lazy value equals brute force | tested to 1e-12 Jy; f32 gridder to 1e-11 | same test; `single_precision_keeps_the_amplitudes_exact` |
| Gap at rounding without a w-term | tested to 1e-11 `Q` | same test |
| Tile bounds leave the picks bit-identical | tested | `lazy_bounds_keep_the_picks_bit_identical` |
| The measured stale rule keeps false flux low | measured only, no theorem | §4 |

## 4. The long minor cycle (measured)

Datasets S1, S2, S3 and the job of [gmclean-benchmark.md](gmclean-benchmark.md):
2048², 1.5″, Briggs 0.5, threshold 100 µJy, gain 0.1, `-j 16`, one noise
realisation, sources off the pixel grid. Scored by `gmclean_bench_compare.py
score` (beam 10.76″; "false" is farther than two beams from any source).

### 4.1 The regression, bisected

`s1-abs`, `-mgain 0.8`:

| commit | components | major | Q/Q_truth | false pixels | false flux |
| --- | ---: | ---: | ---: | ---: | ---: |
| `d94850e` | 120,899 | 6 | 1.01152 | 16,011 | 0.368 Jy |
| `961e162` | 1,000,000 (limit) | 2 | 1.24444 | 191,870 | 20.257 Jy |
| `49e1258` | 1,000,000 (limit) | 2 | 1.24444 | 191,870 | 20.257 Jy |
| `0d804e4` | 1,000,000 (limit) | 2 | 1.24444 | 191,870 | 20.257 Jy |

First bad commit: `961e162`, the forcing rule that moved `φ` towards one after a
small gap. The real-input FFT, the tile bounds, the plan reuse and the `f32` path
are not involved; they leave every printed digit identical. On the current tree
`-mgain-misfit 0.8` reproduces `d94850e`: 120,899 components, Q/Q_truth 1.01152,
16,011 false pixels. The forcing rule is back to its original form (it never
exceeds the initial `φ`). The long cycle of `961e162` still lowers the true misfit
(0.526 to 0.0072 Jy²) and its gap is small; it stops on the budget with an inner peak
of 1.07 mJy, and a sky that is 20 Jy wrong. `-minor-to-threshold` shows the limit:
Q/Q_truth 2.66, 50.6 Jy false flux, inner peak 4.2 mJy at the same budget.

### 4.2 The mechanism

The second issue from the benchmark (`d94850e`: 263-368 mJy of false flux in
12,000-16,000 pixels, balanced in sign, against WSClean's 3.5 mJy) has the same
cause. The per-cycle record of `-mgain-misfit 0.8` on S1:

| cycle | components | stop | first peak | Σ\|c\| | stale `‖r−r̃‖_∞` | gap/Q |
| ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 0 | 137 | fraction | 958 mJy | 5.04 Jy | 1,735 µJy | −5.2e-5 |
| 1 | 255 | fraction | 207 mJy | 3.22 Jy | 540 µJy | 1.9e-5 |
| 2 | 446 | fraction | 76 mJy | 1.88 Jy | 240 µJy | 3.3e-5 |
| 3 | **115,150** | threshold | 23.6 mJy | 4.18 Jy | **186 µJy** | 1.6e-3 |
| 4 | 4,842 | threshold | 201 µJy | 0.05 Jy | 1.7 µJy | −6e-8 |
| 5 | 69 | threshold | 101 µJy | 7e-4 Jy | 0.09 µJy | −1e-10 |

The phase-centre beam is not the Gram matrix off centre: `b` is wrong by about
`δ ≈ 1-3e-4` per unit of flux subtracted. In cycle 3 the stale error (186 µJy)
exceeds the threshold (100 µJy), so pixels nowhere near a source stand above the
threshold in the working map, and the loop cleans them: 115,150 components. A
misfit fraction cannot see this. Once `Q` is near its noise floor (here
`Q_truth/Q0 = 2.2e-3`), a fraction of `Q` is unreachable, so the cycle runs on to
the threshold whatever the peak; and the gap is a sum over the map, small when the
error is pointwise. The lower `Q` it reports (1.01152 against 1.0136) is noise and
beam error being fitted, as the benchmark suspected. This is a statement about
these data; the measured `δ` falls as the bright flux leaves (2-4e-4 in the first
cycle, 2-3e-5 near the end), which is why only the middle of the run is at risk.

### 4.3 Stop rules

| rule | majors S1/S2 (S3) | Q/Q_truth S1/S2 (S3) | false mJy S1/S2 (S3) | false pixels S1/S2 |
| --- | ---: | ---: | ---: | ---: |
| peak 0.5 | 15/15 | 1.01356/1.01487 | 4.13/4.69 | 161/173 |
| peak 0.8 | 7/8 (7) | 1.01343/1.01485 (1.00987) | 4.87/5.66 (1.59) | 209/233 |
| peak 0.95 | 6/6 (5) | 1.01357/1.01504 (1.00984) | 4.73/5.32 (1.69) | 190/202 |
| peak 0.98 | 5/5 | 1.01338/1.01489 | 5.26/5.84 | 235/255 |
| peak 0.99 | 4/4 | 1.01249/1.01417 | **72.4/76.9** | 4,167/4,418 |
| peak 0.995 | 4/4 | 1.01284/1.01461 | 29.1/32.5 | 1,790/2,003 |
| stale ρ=8, g=0.8 | 8/9 | 1.01358/1.01491 | 4.36/5.00 | 166/173 |
| stale ρ=2, g=0.8 | 6/7 | 1.01362/1.01506 | 4.32/4.97 | 165/176 |
| **stale ρ=1, g=0.95 (default)** | **5/5 (4)** | **1.01358/1.01507 (1.00986)** | **4.34/4.88 (1.57)** | **165/180** |
| stale ρ=0.5, g=0.95 | 5/5 | 1.01340/1.01490 | 5.35/6.42 | 240/285 |
| misfit 0.8 | 6/6 | 1.01152/1.01314 | 368/263 | 16,011/12,270 |
| WSClean Högbom loop | 6/6 (5) | 1.01361/1.01536 (1.00989) | 5.41/6.72 (1.65) | 243/297 |
| WSClean fast loop | 9/9 (6) | 1.01410/1.01577 (1.01007) | 3.48/3.17 (1.52) | 171/194 |

Answer to the question put by the benchmark: a default with low false flux and few
major cycles exists on these three skies, with few meaning 4-5, not 1-3. It is
level with WSClean's plain loop on accuracy at one cycle fewer, and three to four
cycles fewer than its fast loop, which has less false flux but stops at 197-245 µJy.
gmclean's last cycles are short (S1: 195 components; S2: 77; S3: 91): the exact
peak is a hair above the threshold, and that pass is what the exact stop costs.
Caveats: ρ and g were chosen on these same skies and one noise realisation; `δ` is
extrapolated from the previous cycle and is not a bound; the rule has no theorem.

The fixed-seed regression test `long_minor_cycles_do_not_fit_the_beam_error` runs
a strong w-term on a 128² field: the default stays within five thresholds of a
many-cycle reference while `-minor-to-threshold` has more than twice the default's
false flux. It would have failed at `961e162`'s behaviour (the run-to-threshold
variant stands in for it; I did not rebuild that commit under the test).

Other checks: `-j 1` and `-j 16` give bit-identical model and residual FITS on S1.
`-tau-min 0.25` and `0.1` halve the resyncs (85 to 47) with no change in false flux
on S1, but add a cycle and worsen S2 slightly (Q/Q_truth 1.01543, 5.3 mJy): not
adopted. `-beam-no-w` is equal in accuracy here (S1 1.01358, 4.29 mJy; S2 1.01528,
4.70 mJy) with a PSF several times cheaper: a candidate, not the default, as it is
untested on wider fields.

**The slice** (LUNO, four stations): 93 components, 3 cycles, Q/Q0 4.76e-4 where
WSClean diverges (2.5e-2). Central 65 pixels hold 13.10 Jy, −12.4 % of the
calibrator (`d94850e`: −12.0 %): the known non-uniqueness of this beam, unchanged.

On pixel-grid skies (§5), `point` recovers exactly the 50 true pixels (11.2470 Jy,
no negative flux) where WSClean has 130 pixels and −8.1 mJy. An inverse crime, so
this is a consistency check rather than a claim about real skies.

## 5. Optimisation

**All times here are provisional engineering comparisons on a loaded host, not
results.** Hardware counters came from `perf stat` in WSL (Ryzen 7 7700X, 8 cores,
16 threads). `.cargo/config.toml` builds locally for `x86-64-v3`, so "scalar" below
is already AVX2 by autovectorisation.

Test data: 64 antennas, 4 h, 64 channels, 30,965,760 visibilities (1.5 GB MS), 2048²
at 1.5″, on three skies: `point` (50 sources), `disc` (8 discs, 20 points),
`crowded` (5,000 sources). Pixel-grid models, Briggs 0, thresholds 0.1, 1, 0.3 mJy.

### 5.1 Remaining hot spots (`perf record`, current tree, thin LTO, 16 threads)

| where | point | disc | crowded |
| --- | ---: | ---: | ---: |
| gridding kernel (`grid_task`) | 33.7 % | 28.6 % | 29.5 % |
| degridding kernel (`degrid_task`) | 26.9 % | 26.3 % | 27.4 % |
| rayon-inlined closures, mostly the gridder's plane loop (`grid_to_image`, 7-8 %, resync, values) | 19.7 % | 22.4 % | 20.7 % |
| rustfft butterflies | about 4 % | about 5 % | about 5 % |
| memcpy/memset (libc) | 4.9 % | 6.1 % | 5.9 % |
| `wgridder::dump` | 2.6 % | 2.7 % | 3.0 % |
| gmclean's own minor loop and resync lines | under 1 % | about 1-2 % | about 1 % |

Wall by phase at `-j 8` on `point` before the last changes: major 24 s, PSF 5.6 s,
read 3 s, dirty 3 s, resync 0.6 s, weights 0.5 s, restore 0.4 s, minor 0.24 s, FITS
0.2 s. **The gridder is the bottleneck, and it is at ducc0's speed
([df2-wgridder-speed.md](df2-wgridder-speed.md)).** The minor loop has little left
to give on these sizes.

### 5.2 Kept

| change | evidence | science |
| --- | --- | --- |
| Real-input FFT resync: half spectra, row pairs, pruned rows, zero-row skip; work space kept | `disc` resync 16.35 → 1.94 s minimum, S1 368 → 45 s (918 resyncs, both under load); 3m → 1.5m FFTs by count, the rest is page faults on 4096² buffers | Q and components identical to all digits printed; 1e-12 against direct subtraction in a test |
| Lazy tile bounds | rescanned pixels ×0.26 on `disc`, ×0.14 on `crowded` (deterministic); minor loop 1.20 against 1.44 s, 2.24 against 3.00 s | picks bit-identical, tested |
| Tile 64 | 1.20 against 1.55 s on `disc`, 2.24 against 2.31 s on `crowded`, 0.062 against 0.076 s on `point`; tile 256 worse (2.32 s, 7.92 s, 0.166 s), 128 a little worse, 16 worse in a whole-run comparison | picks bit-identical |
| Plan, layout and tables kept (`wgridder::Prepared`) | **instructions −10.6 % on `point`, −9.9 % on `disc`** (deterministic) | identical; `GridMeasurement<f64>` equals `WgridMeasurement` bit for bit in a test. Zero-weight visibilities are no longer predicted (nothing reads them) |
| Stokes I per row in parallel | read phase about 3 s, not isolated | bit-identical arithmetic, tested |
| `[profile.gmclean]`, fat LTO, the binary only (`cargo build --profile gmclean --bin gmclean`); the crate-wide release profile is unchanged | instructions −5.9 % (1,647 → 1,551 G on `disc`) | Q identical to all printed digits |
| Stop rule of §4 | 3-4 fewer major cycles than fast WSClean; each pass is 8-12 % of the run | §4 |

Optional, not default: `-single` gridding in `f32`, with `-wgridder-accuracy 1e-4`
as WSClean's settings. On S1 major time 17.7 → 6.4 s, Q/Q_truth 1.01359 against
1.01358, false flux 4.32 against 4.34 mJy. The amplitude is still the exact value
on the image-domain beam (regression test `single_precision_keeps_the_amplitudes_exact`).
`-single` at ε 1e-6 alone saved only 8-11 % of the major time.

### 5.3 Rejected, or not attempted

| candidate | numbers | decision |
| --- | --- | --- |
| `f32` working map with exact `f64` correction | patch 0.15 ns/px against 0.117 for `f64` (cache-bound, no gain); the loop is under 3 % of the profile | rejected, not implemented; the kernel benchmark holds the number |
| Patch 8, 16, 32 | resync 24 s at ±16 against 2.0 s at ±64 on `disc` | rejected; ±64 stays |
| Patch 96, 128 | minor 2.09 s against 1.33 s at ±64, 2.79 against 1.30; resync gains under 0.5 s | rejected |
| `K` 8000, 32000 | resyncs 28 against 41 (−0.7 s), but correction terms ×1.57: minor +0.12 s on `disc`, +1.2 s or more on `crowded` | mixed; `K` stays 2000; re-test |
| Spatial index for the correction | every exterior term is needed; a term costs about 0.8 ns in the kernel, 9 ns in the loop's cache pattern | not implemented; 1 % of the time |
| Explicit SIMD on this build | patch 0.117, 0.114, 0.128 ns/px at scalar, AVX2, AVX-512 (memory-bound); tile argmax 0.346, 0.184, 0.236; gather 0.797, 0.788, 0.776. Whole loop: no resolved difference | kept for non-v3 builds; **no meaningful speedup measured, and AVX-512 is no faster than AVX2 on Zen 4** |
| `x86-64` baseline build | 1,685 G instructions against 1,647 G: +2.3 % | fine for wheels; dispatch does its job |
| Plane groups | df2-wgridder-speed.md, negative | not repeated |
| Pruned FFT beyond the dropped rows | estimated under 10 % of the resync | not implemented |
| PGO | needs `llvm-profdata`, not on this host | not attempted |
| Thread pinning, NUMA | one socket, shared host | not attempted |
| `-j 16` against `-j 8` | wall −15 %, CPU +33-41 % (SMT) | user's choice |

### 5.4 Decisions resting on timings under load

To re-test on an idle host before the final benchmark: tile 64 against 32; `K`;
lazy against eager in wall time (the counts are solid); AVX2 against AVX-512 as the
dispatch default on Zen 4; `-j`; the fat LTO wall gain (its instruction count is
solid); resync gain (the FFT count is solid, the size of the page-fault part is not).
Not dependent on load: everything in §4, plan reuse and fat LTO instruction counts,
tile rescan counts, resync and major-cycle counts.

### 5.5 Where this stopped

Headroom I think remains, in order: (1) the 5 % in memcpy and the 20 % in rayon
closures have not been attributed line by line; a frame-pointer profile was planned
and dropped for the accuracy work; (2) a last pass of a few dozen components costs
a full major cycle (8-12 % of the run) and a tolerance on the exact stop would save
it, at a different stopping point; (3) `-beam-no-w` saves most of the PSF if it holds
on wide fields; (4) the gridder itself has no easy gain. I do not think the code is
perfect, only that the bulk of the time is no longer in anything written here.

### 5.6 Target (provisional, under load)

WSClean 3.7 (`-gridder wgridder`, default accuracy, `-j 8`) on the `sim` skies, three
interleaved repeats of each, fastest wall time:

| sky | WSClean default | `-parallel-deconvolution 1024` | gmclean default (`f64`, ε 1e-6) | gmclean `-single`, ε 1e-4 |
| --- | ---: | ---: | ---: | ---: |
| point | 22.5 s (6 majors) | 24.5 s | 24.4 s (3) | 14.9 s (3) |
| disc | 29.3 s (5) | 21.9 s | 33.5 s (4) | 21.6 s (4) |
| crowded | 29.6 s (5) | 22.4 s | 30.6 s (4) | 18.9 s (4) |

Residual peak: gmclean 0.1, 1, 0.3 mJy (the thresholds); WSClean default 0.14, 1.8,
0.30 mJy. This is not a speed claim: repeats scatter by up to 50 % at load 5-13.

## 6. Measured, 1024² simulated MS (timings provisional)

64 antennas, 2 h, 60 s dumps, 8 channels (1.94 M visibilities), 50 point sources
log-uniform over 0.01-1 Jy on pixels, `dirty2vis` predict (an inverse crime,
labelled), σ = 5 mJy per part per correlation; 1024², 2″, Briggs 0, gain 0.1,
threshold 1 mJy, seed 20261102, default rule.

| run | components | major | resyncs | Q/Q0 | max \|gap\|/Q | τ min / median | wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gmclean ±8 | 2218 | 3 | 24 | 1.179e-5 | 7.3e-5 | 0.500 / 0.689 | 1.81 s |
| gmclean ±64 | 2218 | 3 | 6 | 1.179e-5 | 7.5e-5 | 0.506 / 0.807 | 1.69 s |
| gmclean full beam | 2218 | 3 | 2 | 1.179e-5 | 7.3e-5 | 1.000 / 1.000 | 2.53 s |
| certified provable ±64 | 2206 | 5 | – | 1.225e-5 | 4.9e-4 | – | 4.41 s |
| certified mgain 0.8 ±64 | 2209 | 6 | – | 1.212e-5 | 7.1e-4 | – | 5.14 s |
| certified mgain 0.8 full | 2207 | 5 | – | 1.215e-5 | 5.3e-5 | – | 7.41 s |
| certified Clark ±64 | 86,320 | 7 | – | 1.54e-3 | 5.7e-2 | – | 52 s, once |
| 16 antennas, gmclean | 1589 | 3 | 25 | 3.613e-4 | 4.7e-5 | 0.500 / 0.708 | 0.94 s |
| 16 antennas, provable | 1614 | 27 | – | 3.631e-4 | 8.7e-3 | – | 6.09 s |

Lazy against brute force (`-audit`): under 1e-15 Jy. Wall is the minimum of five
interleaved repeats (`gmclean_sim bench`, median machine load 7-12).

Negative results:

- **The premise does not hold for a 64-dish beam.** The provable rule's "1-4
  components per cycle" came from a four-station beam with `f = 0.77`. Here `f =
  0.005` at ±64 and it takes 441 components per cycle.
- **On 4 antennas resyncs dominate:** 3 major cycles against the provable rule's 25
  and 1.8 s against 4.4 s, but 1.16 s of that is 67 resyncs, because with so little
  data a resync costs about a third of a major cycle.
- **Clark's stop rule fails on this data at ±64** (`f · first peak` allows very deep
  cycles): 86,320 components, 14.1 Jy away from sources, an audited 2000-step run has
  500 ascending steps. This is the rule as implemented in `clean_certified`.
- **`τ_k` is a pessimistic bound.** The drift signal fires only on sparse arrays
  (43 of 67 on 4 antennas, 2 of 25 on 16, none on 64): the `τ` resyncs come from
  `f Σ|c_j|`, the bound the design set out to avoid, here only in the certificate.

## 7. Reproduction

```bash
# 1024² archive (the timing pass is one command: bench)
cargo build --release --manifest-path core/Cargo.toml --example gmclean_sim --bin gmclean
core/target/release/examples/gmclean_sim write OUT
core/target/release/gmclean -name OUT/bin -size 1024 1024 -scale 2asec -weight briggs 0 \
    -niter 200000 -abs-threshold 1e-3 OUT/sim.ms
core/target/release/examples/gmclean_sim bench OUT 5
core/target/release/examples/gmclean_sim compare OUT
# 2048² skies and the minor-loop comparison
core/target/release/examples/gmclean_sim sim OUT/disc disc 2048 1.5 240 64 4
core/target/release/examples/gmclean_sim minor OUT/disc/sim.ms 2048 1.5 1e-3 5
python3 examples/gmclean_compare.py SPEC.json OUT.json   # interleaved, under perf stat
# The benchmark job
gmclean -name OUT/s1 -size 2048 2048 -scale 1.5asec -weight briggs 0.5 -niter 1000000 -gain 0.1 \
    -nmiter 1000 -abs-threshold 0.0001 -data-column DATA -field 0 -j 16 s1.ms
```

Heavy runs on the shared host go under `flock /home/gijsm/.rang-heavy.lock`.
