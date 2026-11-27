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

## Results

Not yet measured.
