# Notebooks for v0.2.0: audit and the learning path

2026-11-13, branch `claude/notebooks-v020-3666c9`. Status: **implemented;
every notebook executed clean on the public fixture** in the documentation
job's mode (below). No scientific or performance claim; nothing here changes
code outside `notebooks/`.

## The path

Beginner to astronomer, as `docs/tutorials/index.md` now lists it: I1-I6,
then 00 (MS to image), then I7-I9, then the new 08 and 09; notebooks 01-05
look inside each step on real data; 06-07 tell the two research questions.

| Need | Notebook |
| --- | --- |
| calibration end to end: solve, apply, check | I6 (K, G, B, F, apply, each table against the truth; **new section 7**: residuals against the noise, overall and per antenna), 00 (the same in one `rang-core run`) |
| polarisation basics | I8 (**new warning**: agreement on A1 is self-consistency; absolute χ on real data is under investigation) |
| reading rang-core's reports, judging image quality | **new 08** |
| GPU and CPU paths | **new 09** |

## New notebooks

- **08, reports and image quality** (A1 small, E4's configuration, about
  20 s). Reads `state.json`, the flag, calibrate, apply and image summaries,
  the receipt and GeMClean's `-report.json`; then judges the image by ten
  numbers computed from the FITS files alone (noise over the radiometer
  prediction, pixels beyond 5σ and excess kurtosis, dynamic range, σ near the
  brightest source over σ far from it, largest PSF sidelobe and axis ratio,
  restored over true point flux, CLEAN's stop), on the run's image and on an
  image of uncalibrated DATA made with the same settings; a checklist table.
  Measured: calibrated noise ratio 17.9, dynamic range 710, restored/true
  point flux 0.95; uncalibrated 46.5, 10 and 0.05.
- **09, CPU and GPU paths** (public fixture, about 10 s). What runs where
  (only the w-stacking gridder has a GPU path, `--features gpu`); the CPU
  reference image; w-stacking against the exact w-gridder by region, matching
  DF2b's 17-32 % of the peak at the edge and ≤ 0.56 % in the central half;
  the CPU image bit-identical at 4 threads and 1 (fresh process); a GPU cell
  gated on `core_grid.gpu_available()` with X2's measured figures beside it;
  GeMClean's SIMD tiers (best and scalar), with the tier read from the report.
  **The GPU branch was not executed**: this host's extension, like CI's and
  the wheels', is built without the feature. Its code calls the same
  `image.image(..., device="gpu", precision=...)` that X2's tests cover.

## Audit of the existing notebooks

Numbers in prose checked against the executed outputs (this run) and against
the reports they cite. A static pass over 01-07, I1-I5 and I9 (every quoted
number traced to its report or code) found nine items; fixed:

| Notebook | Was | Now (source) |
| --- | --- | --- |
| 07 cell 0 | B1-2, B1-3 "proposed", no result | both run; beam and pointing closed as null at B1-3 (`STATE.md`, `b1-3-pointing-selfcal.md`) |
| 07 cell 31 | `b1-baselines.json` "not yet committed" | committed under `research/results/` |
| I1 cell 4 | source "10⁴ times weaker" than the receiver noise | about 400 (S / SEFD = 1/420, the cell's own inputs) |
| 01 cell 6, 03 cell 0 | solver a "bit-for-bit" port of QuartiCal | agrees to about 1e-10 per gain, not bit for bit (`core-phase2.md`: QuartiCal uses fastmath) |
| 05 cell 14 | amendment 1's calls only in the run's `result.json` | the matched call is in `research/results/flagging-verdict.json` (ratio 0.99943, null, 678 dropped) |
| I9 cells 0, 18 | V1 "names the first product" (vision section 3); "candidate products" | V1's note (`v1-timeseries-scope.md`, proposed) recommends residual snapshot light curves; building it is an owner decision |
| I3 cell 14 | "a full track takes 12 h" | 24 h close an ellipse; V(−u, −v) adds the mirrored part |
| I3 cell 15 | "2-arcminute field" | 4 arcminutes across (the grid is ±120″) |
| I5 cell 2 | FLAG holds "MeerKAT's online flagger" flags | the flags it was published with (no source names the flagger) |
| 00 cell 25 | true \|τ\| "1-10 ns" beside delays relative to m000 | raw 1-10 ns, and the computed maximum relative to m000 (12.5 ns) |

Checked and correct (executed): 00's σ = 28.7 mJy per real part
(420 / √(2 · 13.375 MHz · 8 s)), restoring beam 29.0″ × 5.0″, residual
0.70 mJy/beam = 18× the 39 µJy natural-weighting thermal noise; I1's
31 µJy/beam, which I7 quotes; I7's residual 0.698 against 0.358 mJy/beam
truth-corrected and natural weighting's higher residual (0.937); I8's
χ 33.55° against 33.0° (median per-channel 0.55°, inside C6w's 1.11°) and
p 0.0945 against 0.095; I6's fluxscale 4.295 Jy against the band-averaged
truth 4.292 Jy. The static pass also confirmed the quoted figures of 01-05,
06, 07, I1-I5 and I9 against their reports (fixture sizes, bin counts,
converged fractions 98 % and 83 %, static mask 41.5 %, SumThreshold recall
3.3 %, the frozen flagging rule, the B1 settings).

## A finding left open (I6 section 7)

On A1 small's gain calibrator the residual (corrected minus the true model)
has an rms 1.16× that of the same cells corrected with the true Jones terms;
per antenna the ratio runs from 1.01 to 1.52 (m056). The truth-corrected
residual is above σ in both parts by the division by the gains and bandpass
(its imaginary part, noise alone, is 72 mJy; the same on RFI-free cells).
The calibrated excess is mostly in the imaginary part (114 against 72 mJy),
a phase error; the true gains are constant within each gain-calibrator scan,
so it is not unresolved time variation. The cause is not established here;
the notebook says so and sets it as an exercise. It may be K, B or the
unpolarised-model assumption; whoever owns E1's calibration findings should
look (E1 also found K errors on A1, `e1-chain.md`).

## Polarisation wording

I8 now says that A1 writes its data in the same feed convention the
configuration solves in (receptor angle −90°, `feed_angle_rotation: -90`),
so agreement there shows the chain inverts its own forward model and says
nothing about the absolute angle on a real telescope; that on LUNO's 3C 286
the absolute χ is wrong in rang and CASA alike, scan-dependent, under
investigation (`handoff-2026-11-13.md`); and E1's 1.9-4.1° on A1 full. No
hypothesis (H3 of chi-offset) is presented as a finding. Exercise 3
(`feed_angle_rotation: 0`) is limited to the simulation.

## Runs

- Host: the Windows workstation of `research/STATE.md`; extension built in
  the branch's venv (`maturin develop --release`, 3 min 6 s compile after
  31 min queued on the lock, 8 slots).
- Fixture: `download_fixture` into `D:\rang\tmp\20261113-notebooks-v020\fixture`
  (SHA256 pinned). All 19 notebooks through `docs/execute_notebooks.py` with
  `RANG_NOTEBOOK_LUNO=0`, `RANG_NOTEBOOK_INTRO_SLOW=1`, under the lock
  (4 slots): 246 s in total. Final run at 3987d96 (6 slots): all 19 clean in
  255 s (08 20.3 s, 09 7.8 s), `sphinx-build -W` clean in 32 s; rows in
  `research/tool-timings.md`.

## For the coordinator

- Merge `claude/notebooks-v020-3666c9`; touches `notebooks/`, the notebook
  list in `docs/tutorials/index.md`, `tests/test_notebook_execute.py` (08
  runs on A1 small, so it is asserted by its own output, not the LUNO line)
  and this note. No other `docs/` page.
- I6 and I8 changed code, so their cached nightly outputs are dropped until
  the next nightly run (`docs/execute_notebooks.py`).
- I6 section 7's per-antenna phase excess (above) is a calibration finding on
  A1 small without a cause; worth a look alongside E1.
- 09's GPU cell has never run with a GPU; run it once on the RTX 4070 Ti with
  `maturin develop --release --features gpu` before claiming it works.
