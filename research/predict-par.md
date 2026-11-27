# predict-par: the component predictor on many threads

Task predict-par for the UHF gate (issue #11, [uhf-gate.md](uhf-gate.md) section 3, "Cost risk").
Branch `predict-par` from main `59e590a8`. Protocol committed before the kernel change.

## Problem

`core.predict_components` (`core/src/predict.rs`, the africanus `wsclean_predict` port used by
calibrate's model step and the casa-model step) runs on one thread. Measured on nash with the
frozen wheel: 29.6 ns per row x channel x component, so one predict of the DOI 1934-638 UHF model
(7,779 point components) over D's 294,903 rows x 4,096 channels is about 9.4e12 terms, about 77 h.

## Change (proposed)

- Split the visibilities into blocks of whole rows and predict the blocks in parallel (rayon).
  Inside a block the loop nest is the existing one (component outer, row inner, channel innermost),
  so every visibility receives its terms in component order 0..nsrc from the same expressions:
  the output does not depend on the thread count or the block size. Blocks of a few rows keep the
  accumulator in L2 and stream the (nsrc, nchan) spectrum once per block, not once per row.
- Threads: rayon's global pool (`RAYON_NUM_THREADS`, which rang's workers set from `data.threads`)
  by default; an explicit `threads` argument (0 = global pool) as in `cal/apply.rs`.
- Single-thread hoists that keep the arithmetic: per-component n and Gaussian shape terms once per
  component, the kind match out of the row loop, the FFI writing straight into the caller's buffer
  (no (row, chan) temporary, spectra computed once). No `mul_add`, `sin_cos`, reassociation or
  fast-math.

## Gate (frozen)

- **Bit identity.** The new kernel equals the old single-threaded loop (kept verbatim as a test
  reference) bit for bit (`f64::to_bits` on every real and imaginary part) on random rows,
  channels and mixed point/Gaussian components with both spectrum kinds and ncoeff > 1, at 1, 2, 8
  and 16 threads, block-size edge cases (rows below, at and not a multiple of the block) and empty
  inputs. Python: the binding at 1, 2, 8 and 16 threads equals the binding at 1 thread bit for bit.
  A stored hash is not used: Linux and Windows CI link different libm sin/cos.
- **Gain hashes.** The gain-hash gate in `tools/check_all.py` unchanged.
- **Decision rule (cost).** Projected D predict = nash's 29.6 ns x (glacier new/old at 1 thread) x
  9.4e12 / (scaling at the thread count). If the projection at 32 threads is above about 6 h,
  threads alone are not enough: say so and propose the next step without implementing it.

## Measurement plan

Glacier (16 threads, Windows, MSVC CRT), shared under the heavy lock (exclusive timing runs on
glacier only from 21:00), labelled as such. Shape: 7,779 point components with ordinary polynomial
spectra (the DOI model's kind), 4,096 channels over 544-1088 MHz, a few hundred rows of
MeerKAT-like UVW; old kernel at 1 thread, new kernel at 1, 8 and 16 threads. Report ns per
row x channel x component and wall. The 16-to-32-thread and glacier-to-nash steps are assumptions
and are labelled.

## Results (2026-11-27, branch `predict-par`)

**Implemented and measured; the gate is met.** `BLOCK_ROWS` = 8.

Bit identity:
- Rust `predict::tests::parallel_blocks_equal_the_single_threaded_loop_bit_for_bit`: seven shapes
  (nrow 0-101, nchan 0-64, nsrc 0-23, ncoeff 1-3, mixed kinds, both spectrum kinds, zero major
  axes) at 1, 2, 8 and 16 threads and blocks of 1, 3, 8, 13 and 256 rows: `to_bits` equal to the
  old loop on every value, spectra equal. Passes on Windows (glacier) and in CI on Linux.
- At the timing shape (256 rows x 4,096 channels x 7,779 point components) the bench compared
  every value with the old loop: bitwise equal at 1 and 8 threads.
- Python `test_predict_components_is_bitwise_the_same_at_any_thread_count`: the binding at 0 (the
  pool), 2, 8 and 16 threads equals 1 thread byte for byte; the existing numpy-template test passes.
- Gain-hash gate (`check_all --quick`): PASS, every hash unchanged.

Timings, glacier (AMD Ryzen 7 7700X, 8 cores / 16 threads, Windows), release build,
`cargo test --release -p rang-core predict::tests::bench -- --ignored`, 256 rows x 4,096 channels
x 7,779 point components with ordinary polynomials (8.16e9 terms):

| Run | Lock | Threads | Wall | ns per row x chan x comp | Speed-up |
| --- | --- | ---: | ---: | ---: | ---: |
| old loop | 8 slots shared, DD13 on the other 8 | 1 | 99.18 s | 12.16 | 1 |
| new | same | 1 | 99.69 s | 12.22 | 1.00 |
| new | same | 8 | 15.52 s | 1.90 | 6.4 |
| new | all 16 slots (host otherwise idle) | 1 | 60.18 s | 7.38 | 1 |
| new | same | 8 | 13.67 s | 1.68 | 4.4 |
| new | same | 16 | 9.08 s | 1.11 | 6.6 |

The two 1-thread rows differ by the host's load (boost clock and shared cache with DD13 on the
other cores), not the code. No single-thread win: sin and cos are the cost and are kept. On an
otherwise idle host 8 threads give 4.4x against one boosted core (the all-core clock is lower),
SMT adds 1.5x. Not an exclusive run (glacier's timing window starts at 21:00).

Projection for the UHF D predict (294,903 rows x 4,096 channels x 7,779 components = 9.40e12
terms):
- glacier at 16 threads: 1.11 ns x 9.40e12 = **2.9 h** (measured rate).
- nash at 32 threads, from nash's 29.6 ns per term at 1 thread (frozen wheel, old loop; new/old at
  1 thread is 1.00 on glacier): 29.6 ns x 9.40e12 / (32 x e) = **3.0 h** at parallel efficiency
  e = 0.80 (glacier's shared 8-thread figure) and **4.4 h** at e = 0.55 (glacier's idle-host
  8-thread figure). Assumptions: the glacier efficiency carries to nash's 36 physical cores,
  and nash's 29.6 ns (2.4-4x glacier's) holds for this build.

By the decision rule (6 h at 32 threads) threads alone are enough. Not measured on nash (this task
does not touch nash); the gate run's model step is the first nash measurement.

## Next step if it is not enough (proposed, not implemented)

Phase recurrence over channels: for uniform channels exp(i p nu_(k+1)) = exp(i p nu_k) x
exp(i p dnu), one complex multiply per term instead of a sin and a cos, about 5-10x on one thread.
It is not bit-identical: it needs a frozen tolerance against the old loop (the rounding grows
with k; re-seed with sin and cos every 64 or 128 channels) and the model-row gate of
uhf-gate.md section 5 (1e-5) as the oracle. A coarser alternative is a flux cut of the model,
which uhf-gate.md section 3 names as an amendment.
