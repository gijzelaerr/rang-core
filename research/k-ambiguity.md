# Rang: why `k_zero_start` missed a K at −1/(2Δν) (DL4s stage 3, block 1678312253)

Status 2026-11-26: **proposed** (diagnosis frozen before any re-solve; no result read). Branch
`k-ambiguity` from origin/main `cf9d6dd2`.

## 1. What is open

DL4s stage 3 ([dl4s-screen.md](dl4s-screen.md) 2.6-2.7, branch `dl4s-stage3`) found, on held-out
block 1678312253 under E2-N's calibrate section (K `solint: inf`, `average_time: true`, refant
auto), antenna index 25 at 0.13 / 0.10 ns on its first J1939-6342 scan (katdal 32) and
**−2,392.39 / −2,392.41 ns** on its second (katdal 60). −1/(2Δν) with Δν = 856 MHz / 4,096 =
208.984 kHz is −2,392.52 ns. K tables were bitwise equal with `calibrate.k_zero_start` off and on;
rang records `zero_start_intervals` in the solution's settings but not in the run summary.
calchain-floor 13 states the key's limit: the choice between the FFT run and the zero-start run is
per interval over every antenna.

## 2. Reading of the code (before any data)

`core/src/cal/delay.rs` `fft_pass`: per antenna and hand the start is the first maximum of `|FFT|`
of the antenna's refant-baseline data averaged per channel, scanned over the fftshift-ed order, so
the scan starts at bin `n/2`, frequency `−(n/2)/(nΔν) = −1/(2Δν)`. If that buffer is zero (every
channel of the refant baseline flagged for that hand while the antenna is `valid` through another
correlation), or flat, the first maximum is bin `n/2` and the start is exactly −1/(2Δν). An
antenna after the refant in its row gets `−est`, so the sign depends on the index order.

## 3. Hypotheses and what separates them

- **H1 (per-interval limit, calchain-floor 13).** The zero-start run reaches ≈ 0.1 ns for
  antenna 25 but loses the interval on the summed cost, because some other antenna in scan 60 is
  worse from zero. Seen as: `zero_start` true in the settings, interval not in
  `zero_start_intervals`, zero run's antenna 25 near 0.1 ns, its per-antenna cost lower than the FFT
  run's while the interval total is higher.
- **H2 (flat or zero FFT buffer).** Antenna 25's FFT start is exactly bin `n/2` (−1/(2Δν)) because
  its refant-baseline buffer in that hand is zero or flat; Gauss-Newton then barely moves (the
  cost's gradient in delay is near zero half a period from the data's delay). Seen as: the
  start equal to ±1/(2Δν) to within one FFT bin, few or no unflagged refant-baseline cells for
  antenna 25 in scan 60. H2 says where the wrong start comes from; whether the key catches it is
  H1, H3 or H4.
- **H3 (the key not evaluated).** The zero-start run never happens on this path (config,
  dispatch, averaged or chunked route). Seen as: `settings["zero_start"]` false or no
  `zero_start_intervals` key on the solution.
- **H4 (the data, not the start).** Antenna 25's data in scan 60 genuinely fit a π-per-channel
  phase (sign alternation, a data or conversion defect): both runs converge near −1/(2Δν), and the
  cost at 0.1 ns is higher than at −2,392 ns on its own cells. Seen as: adjacent-channel phase
  differences near π on antenna 25's baselines; the zero run's antenna 25 also at ±2,392 ns.
- **H5 (stop rule).** The zero-start run stops early (the stop test counts every gain, so 99 %
  converged can stop it before antenna 25 moves) and its total cost is higher only for that.
  Seen as: zero run's iterations at the stop with antenna 25 not converged; rerunning it with the
  stop off (`stop_fraction` 1.0) reaches 0.1 ns and wins.

## 4. Measurement (before it ran)

nash, run root `~/rang-data/outputs/k-ambiguity-20261126` (own copy of `scan060.ms`, and
`scan032.ms` if the reproduction needs both scans), every job under the heavy lock with
`nice -n 19 ionice -c3`. Wheel or venv from this branch's head.

1. Reproduce: rang-core flag with E2-N's first-pass calibrator strategy on the copy, then K alone
   with stage 3's calibrate section (setjy model, refant as stage 3's `refant_auto` chose,
   uvrange > 150, `average_time`), key off and on. Reproduced if antenna 25 is within 1 ns of
   −2,392.4 ns with the key off. If not, both scans are merged as stage 3 did (CASA concat) and
   step 1 repeats; if still not, the note says so and the diagnosis is on the reproduction that
   comes closest.
2. Probe (`ka_probe.py`, one interval): `cal_delay.solve` on the captured arrays: the FFT start of
   antenna 25 per hand, its refant-baseline unflagged cells per hand, the FFT run's and zero run's
   delays, iterations, and the interval cost and per-antenna cost of each, `zero_start` and
   `zero_start_intervals` from the settings; the zero run again with the stop test off; the cost of
   antenna 25's own cells at 0.1 ns and at −2,392 ns; adjacent-channel phase differences on its
   baselines.
3. Reading: the hypotheses of section 3 that the probe's numbers satisfy. A rang defect is a wrong,
   unflagged K where the data identify the right one (H1, H2 with H3 or H5); H4 is a data defect
   and not a solver fix.

## 5. Fix rule (if a defect is found)

Fixed in the worktree with a unit test on a small synthetic case that reproduces the mechanism.
Key off: bitwise unchanged. A change to `k_zero_start`'s own behaviour (opt-in, default off) is
re-measured on block 1678312253 scan 60 and on E2-A's ID 50 case (calchain-floor 15's
`cf_kreal.py` route); a change to a default needs a K oracle (CASA `gaincal` K on the same MS) and a
frozen addendum here first.
