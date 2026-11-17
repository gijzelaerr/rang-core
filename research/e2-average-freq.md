# E2 helper: `calibrate.average_freq`, CASA's frequency pre-averaging of G-type solves

Part of task E2 ([e2-acceptance.md](e2-acceptance.md) 6.7: the pre-registered
"E2-B amended" arm, coordinator's decision 2026-11-11 under owner item 33).
Branch `fp-e2-freqavg` from `fp-e2-acceptance` `b2d80dc` (the E2 freeze).
Estimator parity with CASA; no novelty claimed.

**Status:** implemented and tested; the LUNO validation protocol (section 2)
was written before its run. Measured 2026-11-12 (section 3): class B met on
every gated term except Gpol, 0.108° against 0.1° (0.250° without the key).

## 0. Why

The LUNO validation of `calibrate.average_time` ([e2-average-time.md](e2-average-time.md)
4.2) met class B against CASA 6.7.6.14 on every gated term except Gpol: phase
median 0.250° against ≤ 0.1° (p95 2.03°), up to 3° on the outer antennas,
nearly constant in time and equal in both hands. Post hoc, CASA's G-type
solves average the selected channels before solving, while rang's kernel
takes each channel as a sample of one frequency bin. An emulation (the
kernel's input averaged over channels) brought Gpol to a median of 0.108°
(p95 0.94°).

## 1. What is implemented

Configuration key `calibrate.average_freq` (bool, default false; left out of
the stage hash at its default, as `average_time`). With it on, every G
(primary and secondary), F and Gpol solve averages its data and model over
the window's channels before the solve: `rang.cal_gain.frequency_averaged`,
weighted means per row and correlation over unflagged channels, after the
pre-applies and P (and after `average_time` when both are on); the weight is
their sum; a cell with no unflagged weight is flagged. The kernel then sees
one channel. K, B, KCROSS, Xf, Df, the A step and selfcal are unchanged.
Chunks of a G solve hold every channel (W3b), so the average is exact per
chunk; a chunk without every channel would raise.

Files: `python/rang/cal_gain.py` (`frequency_averaged`,
`_solve_gain_field(average_freq=)`, `gaincal(average_freq=)`),
`cal_chain.py` (`run(average_freq=)`; G, F, Gpol only), `core_config.py`
(key, `HASH_DEFAULTS`), `core_pipeline.py`; `docs/cli.md` regenerated;
`tests/test_e2_average_freq.py`.

Tests: the average against a NumPy reference; off equals the call without
the key, and the stage hash stays at the default; G equals the reference
(prepared rows averaged over channels, then the unchanged solver) for solint
inf, int and 30 s, alone and after `average_time`, chunked and not; in the
chain K is unchanged and G moves; Gpol equals the post hoc emulation of
e2-average-time.md 4.2 bit for bit, alone, with `average_time`, and chunked;
e2b.yaml validates with the key.

## 2. Validation protocol (written before the run)

Development data only. `e2fa_luno.py` (results/e2-average-freq/): a copy of
the converted LUNO scans 1-2 MS of the averaging validation
(`D:\rang\outputs\e2-20261110-11-avg\luno\luno-dev.ms`), the same
calibrate-only configuration (`average_time: true`) plus `average_freq:
true`, scored by the same class-B scorer (`e2avg_luno.score`) against the
same CASA tables (`e2-20261110-11-avg\casa`). Run directory
`D:\rang\outputs\e2-20261111-13-freqavg`.

Gates, A0 class B, as e2-average-time.md 2: K median ≤ 0.01 ns, p95 ≤ 0.03;
KCROSS ≤ 0.02 ns; **Gpol phase median ≤ 0.1°**; Xf median ≤ 0.5°, p95 ≤ 2°;
Df gauge-free median ≤ 1e-3, p95 ≤ 5e-3; fcal K G B composite median
≤ 7e-4, p95 ≤ 3e-3. Reported beside each: the `average_time`-only run's
number. Whatever this shows, the amended arm runs (e2-acceptance.md 6.7).

## 3. Results

Run 2026-11-12, `e2fa_luno.py`; rang-core calibrate (`average_time` and
`average_freq` on) rc 0, 1,667.7 s under shared slots; score
`D:\rang\outputs\e2-20261111-13-freqavg\luno-freqavg-score.json`. Beside
each: the `average_time`-only run (e2-average-time.md 4.2).

| Term (gate, class B) | median | p95 | max | `average_time` only (median / p95 / max) | Gate |
| --- | --- | --- | --- | --- | --- |
| K \|Δτ\| (≤ 0.01, ≤ 0.03 ns) | 0.0032 ns | 0.0093 | 0.012 | 0.0032 / 0.0093 / 0.012 | **met** (unchanged: K ignores the key) |
| KCROSS \|Δτ\| (≤ 0.02 ns) | 0.00062 ns (rang −0.00718, CASA −0.00656) | – | 0.00062 | 0.00086 | **met** |
| Gpol phase (median ≤ 0.1°) | **0.108°** | 0.94° | 1.42° | 0.250 / 2.03 / 3.19 | **not met** |
| Xf phase (≤ 0.5°, ≤ 2°) | 0.053° | 0.30° | 3.16° | 0.064 / 0.60 / 6.7 | **met** (664 / 664 channels flagged) |
| Df gauge-free (≤ 1e-3, ≤ 5e-3) | 2.4e-5 | 2.2e-4 | 0.017 | 2.7e-5 / 2.2e-4 / 0.017 | **met** (flags 172,212 / 177,682, 5,470 differ, as before) |
| fcal composite K G B (≤ 7e-4, ≤ 3e-3) | 4.5e-5 | 2.2e-3 | 0.052 | 4.5e-5 / 2.2e-3 / 0.052 | **met**, 0 flags differ |

Gpol equals the post hoc emulation (median 0.108°, p95 0.94°) as the tests
require: frequency pre-averaging removes 57% of the Gpol median difference
and 54% of p95, but the median stays 8% above the 0.1° gate. The remaining
0.108° is not this key's. Not investigated here. Candidates are
CASA's in-solve weighting and the Gpol model's
parallactic rotation per row before the average. Xf and KCROSS move
because their pre-applied Gpol moves. The composite (fcal K G B) is
unchanged at its printed precision: G's
effect on it is far below the B-dominated difference.

Gate outcome: class B met on K, KCROSS, Xf, Df and the composite; **not met
on Gpol** (0.108° against 0.1°). As section 2 fixed, the E2-B amended arm
runs regardless; its Gpol miss is expected at about this size.

Checks: the branch's check-all failed on two items outside its diff. ruff
0.17.4 in this venv flagged SIM102 in `tests/test_p11_extract.py`; pinned to the
acceptance venv's 0.17.3 it passes. `tests/test_w4_unsupported.py::test_missing_weights`
fails here with a Windows "Access is denied" in casacure's addcols after
removecols (`examples/check_w4_unsupported.py:197`, unchanged code). It runs
only because this venv has casacure, and is skipped in the acceptance venv. It
is a follow-up, not this branch's.
