# gmclean: lazy exact CLEAN with a certified step

Status, 2026-11-02: **implemented and tested; measured on simulated MeerKAT
data; timings provisional** (shared, loaded host; no final speedup is stated
here). Branch `gmclean`. Code: `core/src/gmclean.rs`, `core/src/gmclean/`
(`kernels`, `fits`, `input`, `sim`, `host`), `core/src/bin/gmclean.rs`,
`core/examples/gmclean_sim.rs`, `formal/RangFormal/Gmclean.lean`. Archive:
[results/gmclean.json](results/gmclean.json) once the final run is recorded.

Credit: the exact per-step correction, the larger patch and the drift stopping
signal were suggested by an early reader of the draft on 2026-11-02.

## 1. Design (implemented)

The provable rule of [clean-certified-imaging.md](clean-certified-imaging.md)
bounds the beam-truncation error by the worst case `f Σ|c_j|`. gmclean replaces
the bound with the exact value at the one pixel about to be cleaned.

1. **Exact beam.** The PSF on the `2n × 2n` grid (`WgridMeasurement::psf_image`)
   holds every offset two image pixels can have. Its FFT is cached.
2. **Lazy exact Högbom minor cycle.** A working map `r̃` takes the beam within
   `±P` only. For the candidate `p = argmax |r̃|` the exact value is
   `r_p = r̃_p − Σ_{j: ‖x_p − x_j‖_∞ > P} c_j b(x_p − x_j)` over the components
   since the map was last exact. (The brief wrote `+`; the sign that holds with
   `r̃ = d − Σ c b_patch` is `−`, and the audit test confirms it.) The component
   is `c = γ r_p / b(0)`.
3. **Resync.** On drift (`|r_p − r̃_p| > d |r̃_p|`, default `d = 0.1`), on a weak
   certificate (`τ_k < τ_min`, default 0.5), every `K` components (default 2000)
   and before deciding that the peak is below the threshold, the map is rebuilt
   by one FFT pair on the `2n` grid as `r̃ = r_major − B (m − m_major)`. The
   delta matters: `r_major` already carries the w-term. No visibility is touched.
4. **Major cycles** run the model through `WgridMeasurement`. A minor cycle ends
   when a fraction `φ` of the misfit (of `Q − Q_∞` if a floor is given) has been
   predicted removed, or at the threshold. The realised gap is
   `ΔQ_exact − ΔQ_predicted`. With `ratio = |gap| / ((1 − θ) |ΔQ_predicted|)` the
   forcing rule halves `φ` when `ratio > 1` and otherwise sets
   `φ ← 1 − (1 − φ) max(ratio, 1e-6)`, so a cycle whose prediction held lets the
   next run to the threshold. Termination is decided on the exact peak of the
   measurement's residual (an ℓ∞ test), never on the gap alone, which agrees with
   [clean-major-cycles.md](clean-major-cycles.md) on `origin/clean-major-cycles`.
5. **Restoring.** A Gaussian fitted by linear least squares to `−ln b` over the
   connected pixels above half maximum, convolved with the model by the same FFT
   machinery. BPA is measured in the FITS frame (north `+y`, east `−x`).
6. **The binary** reads an MS with the core reader, forms Stokes I and WSClean's
   imaging weights by the rules of `examples/clean_certified_export.py`, and
   writes `-dirty`, `-psf`, `-model`, `-residual`, `-image` FITS and `-report.json`.

## 2. What is proven about a step

"Exact" means exact **for the image-domain beam at the phase centre**. The
certificate is not a statement about the visibility-space misfit; the major
cycle measures that departure as the gap (w-term plus gridder accuracy).

| Claim | Status | Pointer |
| --- | --- | --- |
| The exact value follows from the working value through the ignored beam | Lean | `Clean.exact_value_identity` |
| A step with the exact value lowers the misfit by `γ(2−γ)/2 r_p²` at any proposed pixel | Lean | `Clean.exact_value_step`, `Clean.misfit_step` |
| `|r_p| ≥ τ (M + e)` with stale error `≤ e` and `|r̃| ≤ M` makes the pick `τ`-weak greedy | Lean | `Clean.certificate_bound`, `Clean.weak_greedy_of_certificate` |
| With `τ_k ≥ τ_min > 0` at every step the residual tends to zero | Lean, applying | `Clean.dirty_tendsto_zero` |
| The run enforces `τ_k ≥ τ_min` | tested, not formalised | `exact_steps_audit_and_gap_on_the_direct_measurement` |
| Lazy value equals brute force | tested to 1e-12 Jy (`DftMeasurement`), measured 5.2e-16 Jy (§3) | same test, `-audit` |
| Gap at rounding without a w-term | tested to 1e-11 `Q` | same test |

## 3. Measured, simulated MS (timings provisional)

Simulation: 64 antennas, 2 h, 60 s dumps, 8 channels (241,920 rows, 1.94 M
visibilities), 50 point sources log-uniform over 0.01-1 Jy on pixels, `dirty2vis`
predict (an inverse crime, labelled), noise σ = 5 mJy per part per correlation.
1024², 2″, Briggs 0, gain 0.1, threshold 1 mJy, seed 20261102. Numbers below are
from the first full run and are superseded where §5 says so.

Correctness and counts (host-independent):

| run | components | major | resyncs | Q/Q0 | max \|gap\|/Q | τ min / median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gmclean ±8 | 2249 | 3 | 23 | 1.115e-5 | 4.8e-5 | 0.500 / 0.694 |
| gmclean ±64 | 2251 | 3 | 5 | 1.112e-5 | 4.9e-5 | 0.508 / 0.795 |
| gmclean full beam | 2249 | 3 | 3 | 1.115e-5 | 4.9e-5 | 1.000 / 1.000 |
| certified provable ±64 | 2206 | 5 | – | 1.225e-5 | 4.9e-4 | – |
| certified mgain 0.8 ±64 | 2209 | 6 | – | 1.212e-5 | 7.1e-4 | – |
| certified mgain 0.8 full | 2207 | 5 | – | 1.215e-5 | 5.3e-5 | – |
| certified Clark ±64 | 86,320 | 7 | – | 1.54e-3 | 5.7e-2 | – |

Negative results recorded here:

- **The premise does not hold for this beam.** The provable rule's "1-4
  components per cycle" came from a four-station beam with `f = 0.77`. With 64
  dishes `f = 0.005` at ±64, and it takes 441 components per cycle (5 cycles
  against gmclean's 3). The saving in major cycles is modest here.
- **On the 4-antenna subset gmclean's resyncs eat the saving:** 268 components,
  2 major cycles, 69 resyncs, against the provable rule's 25 major cycles, because
  with so little data a resync costs about half of a major cycle.
- **Clark's stop rule fails badly on this data at ±64** (`f·first peak` allows very
  deep cycles): 86,320 components, 14.1 Jy of absolute flux away from sources,
  Q/Q0 two orders worse, and an audited 2000-step run has 500 ascending steps.
  This is the rule as implemented in `clean_certified`, not every Clark in use.
- **`τ_k` is a pessimistic bound.** The drift signal never fired on the 64-dish
  beam: all `τ` resyncs come from `f Σ|c_j|`, the bound the design set out to
  avoid, here only in the certificate. Lowering `τ_min` trades the certificate's
  strength for resyncs.

## 4. Reproduction

```bash
cargo build --release --manifest-path core/Cargo.toml --example gmclean_sim --bin gmclean
core/target/release/examples/gmclean_sim write OUT
core/target/release/gmclean -name OUT/bin -size 1024 1024 -scale 2asec -weight briggs 0 \
    -niter 200000 -abs-threshold 1e-3 -patch 64 OUT/sim.ms
core/target/release/examples/gmclean_sim bench OUT        # the timing pass, one command
core/target/release/examples/gmclean_sim compare OUT      # counts, quality, archive
```

## 5. Optimisation

In progress; see the end of this note when it is recorded.
