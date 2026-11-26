# Rang: why `k_zero_start` missed a K at −1/(2Δν) (DL4s stage 3, block 1678312253)

Status 2026-11-26: **measured** (sections 6-7). Cause: **the data** (H4): antenna index 25 (m054;
the block's 29 antennas are not numbered by dish) has visibilities multiplied by (−1)^channel from
scan 50 to the end of the block; −1/(2Δν) is the right K for those data and `k_zero_start`
correctly kept it. **No solver defect.** One recording gap fixed (section 8). Diagnosis frozen
before the re-solve in `4a68b7e5`; branch `k-ambiguity` from origin/main `cf9d6dd2`. Correction
2026-11-26 17:30 SAST: the first results commit (`29768e6b`) named the antenna m025; it is m054.

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

## 6. Addendum, post hoc (committed with the results in `29768e6b`, not before them)

Order of events (UTC; the note was frozen and pushed at 14:13): flag, K off and K on and the two
probes ran 14:23-14:35 (`receipts/timings.tsv`). Before the probe outputs were read, a
solver-independent check was added (`ka_raw.py`): on an MS copy, per baseline and dump, the
circular mean of the adjacent-channel phase step angle(V[k+1] V[k]*) on unflagged channel pairs
(dumps with at least 8 pairs), per parallel hand, for antenna 25's baselines and 8 random
baselines without it; and the parity of its unflagged channels. It ran on scan 32 while K was
solving, then, after the key-off capture had shown the reproduction (−2,392.39 / −2,392.41 ns),
on scan 60, and then (`ka_onset.sh`) on every scan of the block, each copied into the run root,
read and deleted. The raw and onset results were read before the probe's. H4's frozen wording
("both runs converge near −1/(2Δν)") was too strict: a zero start cannot reach −1/(2Δν) on
full-band data, so under H4 the zero run is expected to stay near 0 and lose on cost. H4 is read
here as: the antenna's own data peak at ±1/(2Δν) and the FFT run has the lower cost on its cells.

Provenance: the nash venv was built from `4a68b7e5` (this note, code as `cf9d6dd2`). The archived
scripts were ruff-formatted after they ran, and `ka_onset.sh` gained a `chmod` before its `rm`
(the copies of read-only MSs could not be deleted; the first attempt stopped at scan 4). The nash
run root and worktree were removed after the receipts were copied.

## 7. Results (measured 2026-11-26, nash; [receipts](results/k-ambiguity/receipts/))

**Reproduced on scan 60 alone.** Own copy of `scan060.ms`, rang-core flag with stage 3's strategy,
K alone with stage 3's calibrate section (refant auto: m008, m015, m032 = 7, 8, 14; refant used 7;
one interval, `average_time`, 21 iterations, fraction 0.992): antenna 25 **−2,392.388 /
−2,392.415 ns**, key off and on, the same values as stage 3's table.

| Probe (scan 60, one interval) | X / Y (ns) | iterations, fraction | interval cost | antenna 25's cost |
| --- | --- | --- | --- | --- |
| FFT start (rang's rule, recomputed) | −2,392.377 / −2,392.377 | – | – | – |
| FFT run (key off) | −2,392.388 / −2,392.415 | 21, 0.992 | 4.350e9 | 6.19e8 |
| zero run | −1.99 / 0.13 | 50, 0.0 | 6.898e9 | 1.90e9 |
| zero run, stop off, 200 iterations | −2.63 / 0.15 | 200, 0.0 | 6.895e9 | 1.90e9 |
| key on | as FFT run, `zero_start` true, `zero_start_intervals` [] | 21, 0.992 | 4.350e9 | 6.19e8 |

The FFT start sat on its first FFT bin from −1/(2Δν) (−2,392.52 ns; bin width 0.146 ns), from 1,659
unflagged cells on the refant baseline, not from an empty buffer. The zero run is the costlier on
**every** antenna (29 of 29) and does not converge. Antenna 25's own delay spectrum (every other
antenna corrected by either run's gains) peaks at ±2,392.5 ns with about 1,400 times its value at
0 ns, and the median adjacent-channel step of its corrected data is 3.140 rad.

**The raw data (no solver).** On every baseline of antenna 25, in both hands and in every dump with
at least 8 unflagged channel pairs, the adjacent-channel phase step is near π in scans 50, 54, 58,
60, 62, 66, 70 and 74 (per-baseline median |step| 3.007-3.1415 rad; scan 60 3.1414-3.1415), and
near 0 in scans 4-46 (0.0000-0.082 rad, scan 32 at most 0.005); the 8 control baselines are at
0.0001-0.099 rad in every scan. Scan 50 has 15 dumps, of which 14 have 8 pairs, and all 14 are
flipped; so the onset lies between the last dump of scan 46 and the first usable dump of scan 50.
Unflagged channels are even and odd in equal numbers (scan 60: 1,870,590 / 1,868,210), so this is
not a parity alias of the flags. From then on m054's visibilities carry (−1)^channel.

**Reading (section 4 step 3).**
- **H4 holds**: the data fit a π-per-channel step and −1/(2Δν) is their delay (mod 1/Δν), not a
  solver failure. Where the step arises (the telescope or the conversion to MS) is not separated
  here. One reading, not tested: 1/(2Δν) = 2,392.52 ns is exactly 4,096 samples at L-band's
  1,712 MHz sampling, half the F-engine's 8,192-sample frame, so a coarse-delay step of half a
  frame on m054 from about scan 50 would give exactly this. If so, K is the antenna's real delay
  change and the right treatment is per-scan K (interpolation `nearest`, or a K solved on the gain
  calibrator), not flagging the antenna.
- **H1 rejected**: the zero run loses on antenna 25's own cells too, not by another antenna's cost.
- **H2 rejected**: the start is a true FFT peak, not an empty-buffer default.
- **H3 rejected**: the key is evaluated (`zero_start` true; no interval taken from the zero run).
- **H5 rejected**: the zero run with the stop off stays at 0.15-2.6 ns, cost unchanged.
- So DL4s 2.7's "K at the delay ambiguity, one new instance" is not E2-A's class (a wrong start on
  identifiable data, calchain-floor 13): E2-A's ID 50 was 2,335 / 2,291 ns, a sidelobe; this is an
  exact half-period fit of sign-alternating data. The solver class keeps one instance on record.
- What goes wrong downstream is interpolation, inferred and not measured: K is 0.1 ns at scan 32
  and −2,392 ns at scan 60, so linear interpolation onto the gain-calibrator scans between them
  (34-58) gives delays that fit neither the clean scans (34-46) nor the flipped ones (50-58); a
  delay interpolated across a half-period has no meaning. That is where DL4s 2.7's Gsec / F
  deviations on J1517-2422 would come from.
- No CASA K was run on the scan: the finding is about the data (the raw phase step), and the
  solver's answer is the data's own spectral peak; an oracle comparison is not needed for a
  result that changes no table.

## 8. Recording gap fixed (no table changes)

Stage 3 could not tell whether the zero start won an interval: `zero_start_intervals` reached
`DelaySolution.settings` but not the run summary, and a field solved in more than one chunk kept
the first chunk's list only, in that chunk's own numbering. Now `cal_delay.zero_kept_of_chunks`
merges the chunks' lists with their offsets, and `cal_chain._solution_record` writes
`zero_start_intervals` into each K solution record of `summary.json` when the key is on. Key off:
no record field, nothing else changes; key on: K tables unchanged (the merge only renumbers a
list). So the E2-A and 1678312253 outcomes are unchanged. Tests:
`tests/test_cal_delay_zero_start.py` (on calchain-floor's sparse case split into two one-interval
chunks, the merged list holds interval 1, which the old first-chunk rule lost; the record field;
a sign-alternating antenna keeps the half-period delay with the key on). The merge inside
`_solve_field` with a budget is covered by `tests/test_w3b_chainchunks.py`
`test_chunked_k_zero_start_reports_every_chunk` (one `int` interval per chunk: the list now spans
the chunks; before it was at most [0]).

Found on the way, not fixed: **with the key on, a K solved in chunks is not bit for bit the
one-call K** (W3b's promise holds with the key off). The replay traces the FFT run's stop only,
and each chunk's zero run then gets that iteration count with the stop off, while the one-call
zero run stops on its own test. On W3b's test MS the delays differ by 3.2e-6 ns, and near-tie
intervals change sides (one-call [3, 7, 11, 16, 17, 18], chunked [7, 9, 11, 16, 17, 18]). Stage 3's
K was one chunk, so it is not affected; a fix (trace both runs, or replay the zero run's own stop)
belongs with any decision to make the key a default.

## 9. Every antenna of every DL4s block, E2-A and E2-N (2026-11-26, coordinator's request after the merge)

Asked: is m054 one antenna or a pattern? `ka_scan.py` (read only; nash: the 220 dl2 per-scan MSs
of the nine DL4s blocks and E2-N's `e2n.ms`; glacier: E2-A's `e2a.ms`) takes every row, per
parallel hand, through section 7's step (circular mean of angle(V[k+1] V[k]*) over unflagged
pairs, at least 8) on channels 1,792-2,303 (512 mid-band channels; 11 MSs read before that change
used the full band). Per (scan, antenna) it counts usable and flipped (|step| > π/2) rows and sums
the rows' unit steps (angle; coherence = |sum| / pairs). A **hit**: more than half the antenna's
rows flipped in both hands and the summed angle beyond π/2. Validated first on 1678312253 scan 60:
m054 alone, 2,072 / 2,072 rows, angle 3.140 / 3.141 rad, coherence 0.99; every other antenna at
most 3.6 % (its baseline to m054). After 158 MSs, MSs with more than 200,000 rows were read in 200
evenly spaced 1,000-row chunks (`chunks_read` in each output); a step lasting a scan shows in any
sample. Wall: nash 12,351 s (two runners, three workers each, shared with other jobs); glacier
4,200 s for E2-A with its lock wait. Outputs: [scan/](results/k-ambiguity/scan/) (per-MS JSON,
`summary.json`).

| Block | Antenna | Scans | min fraction flipped | min coherence | Reading |
| --- | --- | --- | ---: | ---: | --- |
| 1678312253 | m054 | 50, 54, 58, 60, 62, 66, 70, 74 (every scan from 50; 32-46 clean) | 1.00 | 0.86 | **sign flip** |
| 1629213076 | m044, m045, m050, m059, m061, m063 | 54, 56, 58 (MSGPS target fields) | 0.50-0.63 | 0.02-0.11 | noise: half the rows by chance, no coherent step |

No hit in 1571938260 (46 MSs, 59 antennas), 1573212012 (32), 1579022459 (31), 1611426666 (17),
1674958551 (22), 1735892129 (11), 1749428161 (14), E2-A (61 antennas, 3 scans; largest non-hit
fraction 0.18 %) or E2-N (62 antennas, 14 scans; 6.5 %). Largest non-hit fraction in any MS 0.45
(target scans). So the π step is **one antenna in one block** of eleven observations, from one
time onwards, both hands, every baseline: a single event, not a pattern of the telescope or of
the conversion.

## For the coordinator

- Cause found, **not a rang solver defect**: m054 (index 25) in block 1678312253 carries
  (−1)^channel from scan 50 onwards (raw phase step π on all its baselines, every usable dump, both
  hands; clean through scan 46). −1/(2Δν) is the correct K for scan 60 and the key rightly kept it.
- The harm is K interpolated between a clean and a flipped primary scan (inferred, not measured).
  Options, none built: a QA check for an antenna whose adjacent-channel step is near π (or a K
  within one FFT bin of ±1/(2Δν)), then either per-scan K (`nearest`, if the step is a real delay
  change, e.g. a half-frame coarse delay: 4,096 samples at 1,712 MHz) or flags for the affected
  scans. DL4s stage 3's "delay ambiguity" class keeps one solver instance (E2-A's ID 50).
- Fixed: `zero_start_intervals` in the K solution records and merged over chunks (no table change;
  E2-A and 1678312253 outcomes unchanged by construction, not re-run). No CASA K run.
- Not fixed: with the key on, a chunked K is not bitwise the one-call K (3e-6 ns; the zero run's
  stop is not replayed); matters only if the key becomes a default (section 8).
- Section 9: the step is m054 in 1678312253 only, across the nine DL4s blocks, E2-A and E2-N.
