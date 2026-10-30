# Tricolour: frequency axis of the box filter and SumThreshold one row at a time

Repository: ratt-ru/tricolour. Status: **filed 2026-10-30 (task U2),
https://github.com/ratt-ru/tricolour/issues/113** (improvement, with numbers).

PR: https://github.com/ratt-ru/tricolour/pull/114 on `0.5.0-dev` (branch
`lanes-frequency-axis`, commit 2f476ad). CI: no checks reported yet (fork PR; the project's
`ratt-priv-ci` asks an admin to verify fork patches).

Origin: [../p3-sumthreshold.md](../p3-sumthreshold.md) section 5 (rows as lanes gave 2.3-3.0x on
one thread in rang's Rust port; not measured in Tricolour then).

- Code on `0.5.0-dev` (b01ac8f), `src/tricolour/core/kernels/flagging.py`: `_box_gaussian_filter`
  filters the frequency axis per row (`for i in range(data.shape[0])`), `_sum_threshold` with
  `axis == 1` calls `_sum_threshold1d` per row; axis 0 already works in 256-column blocks.
- Change: for 2-D input, transpose to a contiguous copy, process blocks of up to 256 columns
  of the transpose with the existing 1-D kernels, write back. Per-element arithmetic unchanged.
- Benchmark (`sum_threshold_flagger`, `background_flags` kwargs of the default strategy,
  `num_major_iterations=1`; synthetic float32 amplitudes with an RFI block, a bad dump, a narrow
  channel, 1/64 of the band pre-flagged; Python 3.13.16, Numba 0.68.1, NumPy 2.5.4;
  `NUMBA_NUM_THREADS=1`, `taskset -c 13`, JIT warm; 7 interleaved rounds x 5 calls per
  variant = 35 calls; host load average 22-62 on 16 CPUs, so minima are the cleaner figure):

  | window (bl x time x chan) | base min / median (s) | lanes min / median (s) | speed-up min / median |
  |---|---|---|---|
  | 4 x 64 x 4096 | 0.610 / 1.544 | 0.438 / 1.048 | 1.39 / 1.47 |
  | 8 x 32 x 2048 | 0.240 / 0.757 | 0.183 / 0.479 | 1.31 / 1.58 |
  | 2 x 256 x 1024 | 0.338 / 1.152 | 0.159 / 0.434 | 2.12 / 2.66 |

  Flags bit-identical for all three shapes (flag fractions 0.0725, 0.1283, 0.0621).
- Tests: new `test_frequency_axis_matches_per_row` (bitwise equality with the per-row calls on
  300 x 700, two chunks; passes before and after, an equivalence check); `pytest -m "not
  acceptance"` 57 passed, 2 skipped; ruff 0.13.2 format and check clean.
- Smaller than the port's 2.3-3.0x because this times the whole flagger (time axis, background
  fits, medians unchanged), not the frequency-axis kernels alone.
