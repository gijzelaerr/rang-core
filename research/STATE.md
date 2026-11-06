# Rang research state

## Current status

Update this block when a merge changes it. The log below is the record.

- **What `main` is:** rang-core after the 0.1.0 release: a tested research demonstrator, one Rust core reached through the extension `rang._core`, one command line `rang-core`, wheels for five platforms and the [documentation site](https://pythonic.nl/rang-core/).
- **Merged:** the port and simplification (P1–P12, W1, X1, X2), the table writer (E3–E6), the exact gridder (DF1, DF2a–c), the deconvolution oracles (DF5-O), the file formats (DF-IO), CLEAN theory and its major cycles, B1-0 to B1-3, the docs (D1–D3), the [final review](w4-review.md) and its fixes W4-1 to W4-8, the reference imager [gemclean](gemclean.md) with its [benchmark](gemclean-benchmark.md) and the flagged [Gram operator](gridder-theory.md) (their times provisional); see the [research index](README.md).
- **Closed as null, as tested:** a gain-TV-guided threshold flagging policy ([verdict](flagging-verdict.md)); beam and pointing at [B1-3](b1-3-pointing-selfcal.md).
- **Stopped before training:** a flagger trained on gain TV, NO-GO at its [go/no-go test](f1-tv-flagger.md) on LUNO 1934−638 alone; no network was trained.
- **To reopen beam and pointing:** first a deeper ESO137 field model (an external catalogue, an owner decision).
- **Running:** the [finish plan](finish-plan.md), from 2026-11-05. Done: A0, A1, C1, C2a, C2b, C3a, C4a, C4b, G1, W1, W2, W2b. Waiting on the owner: A0's data fetches and native-data source.
- **Next:** the tasks of the [finish plan](finish-plan.md), to v0.2.0 in full polarisation. The flagger's non-TV arms wait for Landman's reply; DF5 and B1 fall outside that plan unless added.
- **User items** ([big plan](big-plan.md#user-items-not-blocking)): decide whether to test the flagger's non-TV arms; put the result to Landman; forward the observer's native data when it arrives.
- **Open items:** the [todo at close](big-plan.md#todo-at-close-2026-11-03).
- **Older history:** everything before 2026-10-29 is in [STATE-history.md](STATE-history.md), unedited.

## Log (newest first)

A new paragraph goes directly under this heading.

C2b, 2026-11-06 (implemented; measured; class A met, against CASA and class T not met as frozen; [c2b-delay.md](c2b-delay.md)): the delay term K in Rust (`core/src/cal/delay.rs`, `rang.cal_delay`): QuartiCal 0.2.7's `delay` kernel with its FFT initial estimate (FFT, then Gauss-Newton), CASA's K conventions (referenced to the first refant, no flex, `minsnr` or `minblperant`, which CASA's K does not apply) and `K Jones` tables that CASA applies as rang does. Against QuartiCal all eight cases agree to 1e-14 ns with equal flags and iterations, with delay differences up to 88 ns (a new `delay50` version of A1's generator). Against CASA it passes wherever a G is pre-applied (nine cases, median 0.0002-0.0015 ns, refant rule equal) but fails without one: 0.06 ns on the slice, 1.3 ns on A1. Post hoc, the cause is `delay`'s missing per-antenna phase offset; QuartiCal's `delay_and_offset` meets CASA's tolerance on all three failing cases. Class T: twins within 3e-8; with noise the frozen bias test fails on A1's field 0 because referenced delays share the refant's error; the gauge-free (centred) form, post hoc, passes everywhere. The delay error is low by 1.5-2. Coordinator's provisional choice, open to the owner: K becomes `delay_and_offset`, ported and measured in C2c before the K, G, B chain. No novelty claim.

C4b and W2b, 2026-11-06 (implemented; measured; frozen run failed, held-out run passed; [c4b-apply-ms.md](c4b-apply-ms.md)): `rang.applycal.applycal` applies CASA tables to a Measurement Set as CASA `applycal`: row chunks through W1's write-back, CORRECTED_DATA, FLAG OR'd, `calwt` weights, CASA's three field maps. Against `applycal` 6.7.6 on O-CASA's slice and A1 small, the frozen run failed (WEIGHT's channel median, 12.7 eps on 86 cells, a field-map case that could not tell two maps apart); after three ports from CASA's and casacore's sources (the lower middle channel for WEIGHT, phase tracking per interpolated pair, casacore's linear formula), a held-out run passed every criterion on ten cases: CORRECTED_DATA class C on every cell including flagged ones (largest 9.17 eps), FLAG exact, FLAG_ROW untouched as CASA, WEIGHT and WEIGHT_SPECTRUM within 6.9e-7, K's `calwt` writing nothing. C4a's "values under solution flags differ" is resolved: CASA still applies the good side of a one-sided diagonal flag. The kernel's output changed at the ulp level, and more under one-sided flags. W2b: `rang-core calibrate` writes setjy, manual and lsm models (bit-identical to `calmodels.set_model`) and solves against them; `rang-core apply` applies the complex term on its own bins (0 eps against a float64 reference); `rang-core run` flag, calibrate, apply, image runs end to end on A1 small. Criterion 13 failed as frozen: `data.weights: uniform` for imaging is still refused, naming C4. Reported, not gated: with `freqint: 16` the end-to-end solve does not converge (owner decision on the solve settings). No novelty claim.

C2a, 2026-11-06 (implemented; measured; class A met, B and T not met as frozen; [c2a-gain.md](c2a-gain.md)): the gain term G in Rust (`core/src/cal/diag.rs`, `reference.rs`; `rang.cal_gain`), QuartiCal 0.2.7's `diag_complex` and `phase` kernels with CASA's solution intervals, `uvrange`, `minblperant`, `minsnr` and reference antenna (flex, strict), pre-apply through `rang.cal_apply`, and CASA `G Jones` tables. Against QuartiCal all seven cases agree to 1.4e-15 with equal flags and iterations. Against `gaincal` the slice passes at 4e-6. On A1, after two post-hoc fixes (CASA solves with SIGMA weights when it pre-applies; a checker margin), a held-out set equals CASA in bins, refant choice and continuity, `minblperant` and `minsnr`, with products within 2.4e-4 median, but solution TIME misses its 0.01 s gate by up to 0.054 s on RFI-flagged scans, and `combine='scan'` differs by about 1 % (CASA averages before solving). Class T failed on one noise-free case because C2a's model left out A1's per-antenna parallactic rotation; with A1's reference model every case passes (3e-8 noise-free, no bias with noise). CASA `applycal` reads rang's G tables (3.2 eps). `tools/check-all.sh` now replays the gain hashes (`gain-hashes` step). Coordinator's provisional choices, open to the owner: the TIME failure stands and TIME is reported, not gated, until CASA's centroid rule is found; QuartiCal's estimator for `combine='scan'`; SIGMA weights with a pre-apply, recorded in the receipt. No novelty claim.

W2, 2026-11-06 (implemented and measured; [w2-commands.md](w2-commands.md)). `rang-core flag`, `calibrate`, `apply`, `image`, `selfcal` and `run` take a `config.yaml` (schema `rang-config` version 1; every default printed by `rang-core config defaults`) and an MS. `flag` runs the Tricolour port per field and scan and writes FLAG, `calibrate` solves the `complex` term and writes a QuartiCal gain store, and `image` runs `gemclean`. C1's whole chain and A0's E2-A and E2-B settings can be written in the schema and are refused term by term, naming the plan task that adds each. A run directory holds the state: `run` skips finished stages, resumes at a failed one and refuses a changed configuration unless forced. Flags are saved as `rang_original` before the first write and as `rang_<stage>_<time>` before each writing stage. On A1's small MS: FLAG equals the port's call in every cell, the gain store is byte-identical to `core.solve_complex`, and a resumed run reran only the failed stage. The research stages moved under `rang-core research`. W2 branched before C3a and C4a merged, so wiring models and apply into the commands is a follow-up (W2b). No novelty claim.

C3a, 2026-11-06 (implemented and measured; [c3a-models.md](c3a-models.md)). `rang.calmodels.set_model` writes calibrator models to MODEL_DATA through W1's write-back: flux standards, `manual`, per-channel Stokes rows and component lists such as CARACal's `pks1934-638.lsm`. Against CASA `setjy` on O-CASA's slice and on A1 small, the real parts differ by 0 float32 ulps; CASA's imaginary parts are at most 1.8e-12 Jy, and other fields' rows are bit-identical to CASA's. The lsm route through `predict_components` is bit-identical to Crystalball 0.4.3, and A1's calibrator sky is reproduced bit for bit. CARACal's own lsm route is MeqTrees, which has no oracle here (open for E3). Polarised `manual` is refused until C7a. No novelty claim.

C4a, 2026-11-06 (implemented; measured; class C not met on two stress cases; [c4a-apply.md](c4a-apply.md)). A Rust apply kernel (`core/src/cal/apply.rs`, `rang.cal_apply`) corrects and corrupts chunks by K, G, T, B and Df with CASA's interpolation and flags. Against `applycal` on O-CASA's slice the frozen run failed on Df flags; CASA's rules were read in its source (`Jones.cc`) and ported (cross hands flagged by bad leakages and by flagged parallel hands; both leakages −1 when one is bad), then CASA's float32 phase tracking and unwrap. In the second held-out run flags were exact on all 13 cases and class C held on 11; two random-phase B stress tables miss by 1-2 ulp of CASA's unwrapped phase (33 eps, 4e-6 relative), mechanism not found. On CASA's own tables every case passed (max 4.38 eps). Threads bit-identical. Coordinator's provisional choices, open to the owner: accept that residual and state it in C4's acceptance; copy CASA's Df substitution for parity with the oracle. C1 §3.1's Df flag rule is wrong for CASA 6.7.6 (erratum in c4a-apply.md §4.3). Throughput not yet recorded (no timing work).

A1, 2026-11-06 (implemented, measured; [a1-simtruth.md](a1-simtruth.md)). Simulated truth for E1 and C2-C7: MeerKAT 64 antennas, 856-1712 MHz, 256 channels, full polarisation, with K (1-10 ns), structured B, G, KCROSS (3 ns), Xf (30-62°), linear Df (1-3 %), 115° of parallactic rotation on the polarised calibrator over 4 scans, a self-calibration residual, RFI with masks and exact σ, written through rang's table writer. Full version 35.8 GB and small version 41 MB under `/mnt/d/rang/outputs/fp-a1-20261106-simtruth/`. CASA `applycal` with the truth as CASA tables inverts it within class C: 0 of 130 M elements (full twin) and 0 of 3.2 M (small) fail. Noise z = 0.40 (full), −1.00 (small). CASA's K window pivot is the band centre. One frozen check failed: CASA's `parang=True` angle is geocentric and from apparent north, up to 0.54° from rang's frame near the zenith, against a 0.3° bound. No novelty claim.

W1, 2026-11-06 (implemented and measured; [w1-writeback.md](w1-writeback.md)). `rang.core_writeback` writes into an existing MS. It adds MODEL_DATA and CORRECTED_DATA as CASA's `clearcal` does (TiledShapeStMan, initialised, but with a fixed shape) and writes any column, FLAG and FLAG_ROW in flushed row chunks. Before the first write it saves the flags as the CASA flag version `rang_original`; a journal refuses a new session after an interrupted one until the flags are restored. python-casacore 3.8.1 and 3.7.1, dask-ms, CASA (`split`, `flagmanager`, `applycal` into the new column) and WSClean read every written column bit for bit. Flags round-trip exactly through rang and CASA versions both ways; 12 SIGKILL cases all recovered; peak memory grew 53 MB while a 268 MB column was written. One frozen criterion failed: the unit model's image peaks off-centre on the 4-antenna fixture's broad PSF, which peaks at the same pixel (post hoc). Open for W2: variable-shape columns, and the flag-backup naming. No novelty claim.

A0, 2026-11-05 (frozen; probes measured; [a0-acceptance.md](a0-acceptance.md)). No public observation meets gate 1 as written (unseen, native, calibrated through self-calibration, full polarisation). Polarisation is testable on real data only in LUNO (SB 20210818-0008: 3C 286, 1934−638 and 1830−211 together); its DATA keeps 1.5 % leakage but is pre-phased (XX−YY 0.016 rad), with processed flags and weights. ESO137 ms1 is the only raw-phase real set (XX−YY 1.49 rad), with no polarised calibrator. Acceptance legs: E1 (A1's simulated truth, full polarisation); E2-A (ESO137 ms1 primary scans 9, 11 and target scan 10, Stokes I, held out); E2-B (LUNO scans 17-20, held out); E2-N (native) open. Gates, tolerances and the CARACal settings are frozen: `meerkat-defaults` for E3-A, full-Stokes for E3-B, seven labelled deviations. Fetches await the owner's approval (E2-A about 180 GB, E2-B 36 GB).

C1, 2026-11-05 (specified; nothing implemented; [c1-calibration-chain.md](c1-calibration-chain.md)) freezes the calibration chain for C2 to C7, read from CARACal `8f7bb363`, QuartiCal 0.2.7 and CASA's sources. CARACal's order is K, G, B (with `fluxscale` for a secondary), then Gpol, KCROSS, Xf, Df, parallactic angle, then self-calibration. QuartiCal has no cross-hand delay term, so KCROSS has CASA as its only oracle. Twelve items of CARACal's sequence are left out or replaced, with reasons; thirteen mergeable steps. Owner decisions ("Do what you think is best"): self-calibration defaults to phase then amplitude, with CARACal's delay form (`Fslope`) also built and E3 stating the difference; the Tricolour port replaces tfcrop inside crosscal, with E3 reporting flagged fractions; K is estimated by FFT then Gauss-Newton.

Finish plan confirmed, 2026-11-05: the owner added polarisation (G9, C6, C7), confirmed multiscale, and left the coarse-gridding default until it is measured. 29 tasks; first A0, C1 and G1.

Finish plan, 2026-11-05 (proposed; nothing started; [finish-plan.md](finish-plan.md)): 26 tasks to a v0.2.0 that flags, calibrates, images and self-calibrates a user's own MeerKAT L-band MS, compared once with CARACal. The largest gap is calibration: only the `complex` term is ported. Awaits the owner's confirmation of the finish line.

Names and landing page, 2026-11-05 (implemented; no science changed): the root crate and binary are now `rang-sim`, at the owner's request, with `rang.sim_output`, `RANG_SIM_BIN`, `RANG_SIM_LIB` and `examples/pointing_sim.py`; no aliases. Golden output is unchanged and receipts are version 4. Dated reports, `research/results/` and `history/` keep the old names as records. GeMClean is now on the README and the docs home page; it is still not in the wheels, and its name clash check is still open.

GeMClean tuning, 2026-11-05 ([gemclean-speed.md](gemclean-speed.md#tuning-after-the-native-pass-measured-provisional-not-a-result); one run per setting, provisional): resyncs take 19-43 % of the wall at `-j 1`, which is why GeMClean loses on one core on hard skies. `-single -wgridder-accuracy 1e-4 -tau-min 0.2` gives 7.4-27.5 s at `-j 16` and 27.6-103 s at `-j 1`, 1.40-3.13 and 0.75-1.60 against WSClean's fastest `-mgain` per sky. **No default changed; no novelty claim.** `-beam-band` is kept, off by default (task G1; [result](gemclean-speed.md#-beam-band-on-and-off-interleaved-measured-task-g1)). Under a rule committed before the run, 12 interleaved pairs with coarse gridding saved 11-16 % of the wall on H2 and H3 at `-j 1` and `-j 16`, and 4-5 % on S1. Images agree with flag off within the bounds on all seven skies. On H2 about half the saving is one fewer major cycle; from resyncs alone only H3 clears 10 %. Every pair ran with one host core busy (a stray process), so no run met the quiet-host test; the rule's all-pairs fallback applied. No default changed; no novelty claim. Next: memory (G2), then the tuned form on the real pilot.

Native timing, 2026-11-04 (measured at `3945394`; [gemclean-speed.md](gemclean-speed.md)): WSClean v3.7 built with `-DPORTABLE=OFF`, S1-S3 and H1-H4, `-j 16` and `-j 1`. At matched accuracy WSClean over GeMClean is 1.21-2.35 at `-j 16`, 0.93-2.09 at `-j 1`. GeMClean `-single -wgridder-accuracy 1e-4` (24-38 % faster, 2.2-2.45 GB) against WSClean's default accuracy and its fastest `-mgain` per sky: 1.05-2.91 and 0.60-1.55, with WSClean faster on H1-H3 on one core. **No novelty claim.** Coarse gridding is not the default; that is an owner decision. Next: optimising GeMClean's code.

Timing pass, 2026-11-04 (measured at `3945394`; [gemclean-speed.md](gemclean-speed.md)): 57 jobs plus a baseline pass of 24. GeMClean with AVX-512 is 1.3-1.5 times faster than WSClean 3.7 at its defaults and 2.2-3.0 times at matched gridding accuracy on S1-S3, with 4-6 times the memory. The KERN WSClean's gridder is SSE2 only; with GeMClean at baseline code WSClean is faster (GeMClean takes 1.1 to 4.5 times as long). **No novelty claim follows.** Next, an owner decision: build WSClean from source for this CPU and time the held-out skies too. Outputs in `D:\rang\outputs\20261104-speed`.

Many-pass solver, 2026-11-03 (merged; [note](gram-solver.md)): **a speed gain only against FISTA run on the exact gridder**
(22.7 G against 131 G instructions per iteration on S1), none against a PSF inner loop with exact passes (9.5-17.6 T against 64.6 T
for the operator alone) and none against CLEAN, so the novelty rule is not met. Signed ℓ1 at λ = 100 µJy has false flux about ×3
below GeMClean's default at 11-21 times the instructions; the S2 disc and the faintest S3 decade are slightly worse; non-negative
ℓ1 fails; the SARA-style prior did not converge. Nothing was run against BASPLib, PURIFY, resolve or pfb-imaging. Merged with a
corrected GeMClean baseline: the first version scored a run with `-mgain 0.8`. All wall times provisional.

Overview and paper, 2026-11-03: [clean-overview.md](clean-overview.md) gathers the programme; the draft paper no longer states 4-5 cycles as general and carries the held-out test, the floor, the pilot and 96 audited theorems. Not submitted; the WSClean report is not posted. Owner decisions are in the overview.

Stale floor, 2026-11-03 (measured; merged; [note](stale-floor.md)): **`-stale-floor 0.01` is now the default.** It leaves all images identical on
S1-S3, H1-H4 and the pilot and ends the bright-source failure on eight cases, four of them not used to choose it. One measure of the bar written first
missed, H3 plus 100 Jy at 1.12 × the model pixels against a limit of 1.1; the owner adopted it knowing that. Simulated sources only; no proof.
GeMClean held-out test, 2026-11-03 (measured; merged;
[gemclean-heldout.md](gemclean-heldout.md)). **The claim "4-5 major cycles at WSClean-level
false flux" did not survive as stated on new simulated skies:** 6, 6, 8, 5 major cycles
against a bar of 5 written first; false flux held (at most 1.37 × the better WSClean loop)
and cycles never exceeded WSClean fast's, but exceeded plain's on two skies. Real ESO 137-006
pilot (1 h, 107 MHz, publisher's GKB-net gains, 4096 × 3″, 256 channels): at 3 mJy 3 cycles
with extra baseline flags and 5 on received flags, off-source model flux 1.02-1.03 ×
WSClean's, compact flux within 0.1 %, no divergence; at 1 mJy 8 against fast's 6. Floor about
40-60 × thermal in all imagers. GeMClean needed 18 GB on 152 M visibilities and did not fit
24 GB at the full 512 channels. Table writer: tile files of 2 GiB or more now written.
Next if wanted: a stop that ends near the threshold rather than exactly, on its own held-out test.

GeMClean rename and paper merged, 2026-11-03 (merge record). `rename-gemclean` as `068efcd`: command, module,
Cargo profile, `RANG_GEMCLEAN_SIMD`, Lean file, notes and scripts; archive JSON, timing history and old on-disk
paths keep the old name. `paper-gemclean` updates the CLEAN theory draft, with wall-clock comparisons withheld until
a quiet-host benchmark. Check-all and `lake build` (73 audited theorems) pass on the rename. The final timing pass is
postponed at the owner's word; the plane-group default stays an open owner decision.
Stop-rule theorem, 2026-11-03 (merged; [note](stop-rule-theorem.md)): **proved in Lean** a minor-cycle rule
`e ≤ κ |r̃_p|` with the true sign and size at the pick, descent with a rate, no flux below `(1 − κ) T`, a flux bound per pixel; `formal/RangFormal/StopRule.lean`, 96 audited. **On paper:** the form of `E` and its
supremum on Chebyshev nodes. **Measured:** 15, 17, 10 major cycles on S1-S3 against the default's 5, 5, 4 at the same false flux, plus about 100 gridder calls, and 96 against 11 on a 3.4° field with a sampled table, so the default is unchanged (images byte-identical on S1). **Found:** S1 plus 30 or 100 Jy at the phase centre sends the
default to its budget with 50.6 Jy of false flux, because a batch at the centre measures `δ` near zero, and 10 Jy costs 395 mJy; the proved rule gives 4.15 mJy and the peak fraction 0.95 gives 4.5-9.5 mJy. **Open owner decision:** a guard for the default; none is tested.

gemclean second optimisation pass merged, 2026-11-02 (implemented; output comparison measured;
**times provisional**; [gemclean.md](gemclean.md) section 5.7, merge `5972124`). The peer session reports
model, residual and image FITS byte-identical to the `58e07e1` benchmark run on S1, S2, S3 and
the slice, and `tests/test_core_wgridder.py` with ducc0 installed: 7 passed, 0 skipped. Check-all still
skips that ducc0 comparison. **Open owner decision:** plane groups of 4 are now the library's default, which
reverses the opt-in of [DF2a](df2-wgridder-speed.md). That note measured no gain at 16 threads and a memory-gate
failure on the array case for its older form; the new default has been measured on gemclean's S1 only. Results do
not change; peak memory does (2.84 to 3.38 GB on S1).

F1 Stages 1a and 1b, 2026-11-02 (implemented; measured; [note](f1-tv-flagger.md)): **NO-GO, outcome D**, as frozen. The implicit gradient of gain TV through the solver's fixed point is right (finite differences within 3.5e-6 median, bound 1 %), but on LUNO 1934−638 at 53 stations it does not mark injected RFI: patch AUC 0.54–0.64 on four of five morphologies at 10σ (bar 0.80), against 0.97–1.00 for the residual z-score; gates B, C and E fail, A and D pass. Removing a whole contaminated mask does lower TV (45 of 45). LUNO only; no network was trained; F-SIM not built. Whether to test the non-TV arms is the owner's call.

gemclean family merged, 2026-11-02 (merge record; the science is in the three paragraphs below).
`gemclean-bench` as `8ed836b`, `gemclean` as `ef6d2ed` with follow-ups `303478d` and `705085d`
(`RANG_GEMCLEAN_SIMD` registered, a script formatted, the CLI page regenerated), `gridder-gram` as
`ce03bf2`. Check-all passes on each pushed head; `lake build` of the merged tree passes with 73
audited theorems on the standard axioms. Not exercised by check-all: the ducc0 comparison in
`tests/test_core_wgridder.py` is skipped because ducc0 is not in the venv. Every speed figure in
these notes stays provisional until the idle-host pass.

Gridder theory, 2026-11-02 (prototype behind a flag; accuracy and instructions measured;
**times provisional**; [gridder-theory.md](gridder-theory.md), branch `gridder-gram`):

- **Implemented.** `gemclean -gram-operator S,THETA`: major cycles from a w-node Toeplitz
  operator, no visibilities after the setup. 23 Lean theorems (`Gridder.lean`).
- **Measured.** 2048²: one apply 23.7 G instructions at any `N_vis`, against 307 G for
  grid+degrid at 31 M, same error at ε 1e-6. Same Q, false flux and peak as the default on
  S1-S3. S1 at 87 major cycles: 480 → 140 s (load 13-15).
- **Negative.** No wall-time gain on gemclean's own 3-5 cycles: setup costs 2-3 passes. At
  4096² the cube is 8.3 GB in `f32` and the apply only 15 % cheaper at 31 M. Operator Q is
  unreliable near the floor. Visibility averaging and per-baseline support: nothing.
- **Prior art.** Fessler et al. 2005 (the sum), Dabbech and Wiaux 2026 (visibility-free with
  w, sparse). Not a novelty claim.
- **Next.** Try it in a solver with many passes; the weight-aware kernel budget (Briggs
  only, ×0.64-0.99 in `S³`, counted); idle-host wall times.

gemclean, 2026-11-02 (implemented; accuracy measured; **all times provisional**,
shared host; [gemclean.md](gemclean.md), branch `gmclean`):

- **Implemented.** A reference CLEAN whose minor step takes the exact image-domain
  value at the pixel it cleans: the binary `gemclean` (MS in, WSClean-oriented FITS
  out), SIMD kernels, a real-input FFT resync, a kept gridder plan
  (`wgridder::Prepared`), 4 Lean lemmas.
- **Measured.** A long minor cycle fits the phase-centre beam's off-centre error as
  false components; a misfit fraction and the gap do not see it. Benchmark `961e162`
  to `0d804e4` were wrong on S1 (1,000,000 components, 20.3 Jy false flux). Fixed:
  cycles now end at the pointwise error the last major cycle measured. S1, S2, S3: 5,
  5, 4 major cycles, false flux 4.3, 4.9, 1.6 mJy; WSClean's Högbom loop 6, 6, 5 and
  5.4, 6.7, 1.7 mJy.
- **Negative.** "1-3 major cycles" is not reachable at low false flux here. The gridder
  is about 60 % of the time. Explicit SIMD helps only the minor loop, invisible in a whole run. Slice
  central flux still −12.4 %. The rule's ρ and g were chosen on the same skies.
- **Next.** Re-test the timing decisions in gemclean.md §5.4 on an idle host, re-run
  the benchmark at the current commit (its `-mgain 0.8` now means WSClean's peak
  fraction, so drop it to get the default).

gemclean benchmark, 2026-11-02 (implemented; accuracy measured; speed PROVISIONAL;
[gemclean-benchmark.md](gemclean-benchmark.md), branch `gmclean-bench`):

- **Datasets.** Three simulated 64-dish MS (S1 50 points, S2 plus a 40″ disc, S3 500
  points; 1,814,400 rows × 8 channels, exact DFT, rang's own table writer, natural
  noise 19.84 µJy) and the LUNO slice; core against WSClean 2.3e-7 of the peak.
- **Baselines.** At 100 µJy, neither imager diverges on the full array. gemclean
  `d94850e` is 0.03 to 0.27 % lower in misfit, with the same flux recovery, and stops
  at the threshold where WSClean's fast loop leaves 178 to 245 µJy.
- **Negative.** At gemclean's mgain 0.8, S1 and S2 carry 263 to 368 mJy of false flux,
  100 times WSClean's. On S1 `-mgain 0.1` removes it and gives WSClean's plain-loop
  answer at 59 major cycles.
- **Slice.** WSClean diverges at `abs`, `-padding 2` included, and cleans nothing at
  `auto`. gemclean converges (Q/Q0 4.7e-4), with central flux −12 % at `abs`, −0.9 % at
  `auto`.
- **Later commit.** The same S1 job at `0d804e4` stops on the 1,000,000-component
  limit with Q/Q_truth 1.244 (§4.5 of the note); cause not investigated.
- **Speed.** Every time is contended: no speed ratio is final. The rerun subset is in
  §7 of the note (`examples/gemclean_bench_timing.sh`).

v0.1.0 released, 2026-11-02. The owner tagged `09bb03f`; the wheels workflow built and tested the
five wheels and the sdist, created the GitHub release and published to PyPI by trusted publishing.
`pip install rang-core==0.1.0` from PyPI on native Windows runs `rang-core --version` and imports
`rang._core`. Merged with this note: the F1 protocol ([f1-tv-flagger.md](f1-tv-flagger.md),
proposed; nothing trained; its early test waits for the owner's decision on JAX in training).


U4, upstream findings filed (big plan), 2026-11-02 (implemented; measured;
[u4-upstream.md](u4-upstream.md)). Filed, each reproduced on the latest release: tigger-lsm#55, #56,
#57; crystalball#83; pfb-imaging#390, #391; tricolour#115; killMS#28; casacure#24, #25, #26, #28, #29
with PR #27; purr#39 with PR #40; the L5-C comment on QuartiCal#455. `eval` and pickle went in as public
issues: neither repository has a security policy. Tricolour #114 is rebased to c1000f1: mergeable, CI 4
of 4, flags bit-identical to `367ff54` on RV1's four controls, one kernel signature. Correction: `purr`
declares PyPI `kittens` instead of `astro-kittens`, but that breaks astro-tigger-lsm only on a
case-insensitive filesystem (measured on NTFS through WSL), not on ordinary Linux; `purr` alone fails
everywhere. DF5-O's `kclean` failure comes from the call order in `core/kclean.py`, not from a plain venv.


Scope of the flagging verdict narrowed, 2026-11-02. Landman pointed out that the original idea
was gain TV as the loss that trains an ML flagger, self-supervised, for a faster flagger with
fewer tunable parameters, with no improvement in calibration expected. The closed experiment
tested a two-parameter threshold policy with re-solves on every observation, so it does not
answer that. The README, CHANGELOG, docs and verdict now say so; the numbers are unchanged. The
user asked for that flagger as the next experiment, after the v0.1.0 tag.

FS2, PB2017 and PB2013 against `setjy` (big plan), 2026-11-02 (implemented; measured;
[fs2-casarundata.md](fs2-casarundata.md)). CASA 6.7.6 `setjy` with CASA's own tables
(`casarundata-2026.10.27-1`, byte-identical to the rsync tree; 80 KB on D:). 3C123, 3C286,
3C295 and Hercules A equal `setjy` at 0 float32 ulps and are now regular, stored float32
as CASA stores them. The other 16 PB2017 sources stay opt-in: the core equals the paper's
Table 5 (no transcription error), but CASA's table is not Table 5 (an extra decimal on 12,
epoch rows for 3C48, 3C138, 3C147, a different a3 for 3C353, a different range for 3C380).
PB2013 is measured and archived, not ported. 1934-638 is in neither table and J0408-6545 is
not recognised, so these standards do not cover MeerKAT's primaries. User decisions: the
per-source lift stands, the 16 stay on the printed table, PB2013 and the journal check for
3C353 are skipped for now.

W4-6, portability hygiene (big plan wave 4), 2026-11-02 (implemented; measured).
`python/rang` names UTF-8 on 90 text reads and writes and LF on every write;
three verbatim P11 sites stay as frozen and are listed in the new AST test.
`.gitattributes` makes the tree LF outside `research/results/` and `history/`
(11 files renormalised, none hashed; `closure.py` keeps its CRLF). 19 example
scripts use `as_posix()`. The identity suite is identical before and after, and
`python -m rang.check` passes on native Windows with UTF-8 mode off and
`core.autocrlf=true`. The Windows py3.14 CI cell now sets `PYTHONUTF8=0`; it has
not run on GitHub yet, and its local equivalent passes.
[Note](w4-6-portability.md).


W4-8, the documentation pass (big plan wave 4), 2026-11-02 (implemented; checked;
[w4-8-readme-docs.md](w4-8-readme-docs.md)). The README is a 151-line landing page
and the research index is by theme with every note linked. STATE has a status
block and a log heading, and its entries before 2026-10-29 moved unedited to
[STATE-history.md](STATE-history.md). AGENTS.md matches the layout. The docs deploy
job warns and skips without GitHub Pages. The status box says both questions are closed as null. The canonical site is
<https://pythonic.nl/rang-core/>. No numerical code or result changed.

B1-3 pointing self-calibration against both baselines (big plan wave 3),
2026-11-02 (implemented; measured;
[b1-3-pointing-selfcal.md](b1-3-pointing-selfcal.md)). Protocol frozen
first, two labelled amendments (the gains must be solved exactly: Gauss–Newton
polishing after StefCal; the beam frequency of the simulations). Survey rerun
with a per-channel bandpass and per-antenna beams: the snapshot common
pointing goes on S2, S3 and S4 (gate G3a: ρ ≤ 8e-9 for a diagonal beam on the
1830 point); per-antenna pointing and squint survive (S4 60/60, S2 52/53 x,
48/53 y); per-scan common pointing and ellipticity survive on the track; width
fails where it would be fitted. Fits in one solver (profiled Levenberg–Marquardt,
same nuisances): gains-only, physical pointing self-calibration (ii), and the
rang method R (selected from its own first pass). **Overall negative under the
frozen rule; B1 closes null.** On simulations pointing self-calibration works
(F2: 0.62′ → 0.054′, held-out −3 %, faint outer-source errors down 2.6×), and R
matches (ii) there (F3: better offsets, 0.110′ against 0.173′, held-out equal).
On the fixture R beats the SARAO/SKA Gaussian fit (0.357′ against 0.634′) but is
worse than (ii) (0.200′), because declining an axis holds a real offset at zero.
On real ESO137 and 1934 data neither arm measures pointing with B1-2's model:
offsets to 24′, squint at 10–140σ, sky-frame structure, all arms unconverged at
10 passes; S4's negative label is a cost-clause ratio (2.18) from (ii)'s free
rejected trials. Archive `results/b1-3-pointing-selfcal.json`.

DF5-O, the deconvolution oracles (big plan;
[df5o-deconv-oracles.md](df5o-deconv-oracles.md)), 2026-11-02
(implemented; measured): a simulated MeerKAT L-band field (64 antennas,
4 h, 16 channels 900–1,670 MHz, radiometer noise σ_img = 1.42 µJy, 40
points from 15 µJy to 20 mJy, four Gaussians and an ESO 137−006-like
radio galaxy, all on the grid) predicted by the core's exact degridder
(DFT check 1.2e-11) into an MS the core creates, read bit-identically by
both tools' python-casacore; their dirty images agree with the core's to
1.7e-7 (WSClean) and 2.6e-7 (pfb). Frozen, with the core-recomputed
residuals: WSClean Högbom 1.606 µJy RMS (1.13σ) in 7 major cycles and
pfb kclean/Clark 1.566 µJy in 5, both meeting the truth tolerances (flux
within 5 % + 3σ for every source above 20σ, points within 0.1 beam);
WSClean multiscale 1.446 µJy and total flux to 0.03 %, but ±3 mJy of
large-scale flux outside the sources and faint points beside it 9–16 %
high; pfb sara at its recipe settings unconverged in 10 cycles (30σ).
DF5 Högbom must reach ≤ 1.598 µJy, multiscale ≤ 1.475 µJy. pfb's flux mop
moved nothing here; two pfb packaging defects (closure, tbb path) and two
WSClean rules (read/write MS, source list) recorded. DDFacet open.
`outputs/df5o-20261031-01`, `outputs/df5o-20261102-02`,
`research/results/df5o-deconv-oracles.json`.

W4-2 and W4-7 boundary checks and GPU gate (big plan
wave 4), 2026-11-02 (implemented; measured;
[w4-2-boundaries.md](w4-2-boundaries.md)). Every `rang._core` binding now
refuses arrays that are not C-contiguous, and arrays of the wrong length,
with a ValueError naming the argument. Size products are checked. The
review's r01 out-of-bounds write and the transposed Fortran-ordered `uvw`
now raise. Changes in the wrappers and core:
- `flag_rows` checks its per-row arrays.
- The blosc span decoders refuse rows outside the decoded blocks.
- `fluxstd_eval` catches panics.
- Zarr metadata with Fortran order, big-endian or unexpected dtypes is
  refused.
- `core_fetch` shares `core_zarr`'s block table and its fallback for
  out-of-order blocks.

The identity suite is numerically identical to `ecccbf0`: 282 arrays,
88 FITS HDUs and 22,500 JSON leaves, with C, D, I, K and P5 passing.
`rang-core check` gains `core-clippy-gpu` and `core-test-gpu`: 6.1 min
cold, 3 s warm, skippable with `--skip`.

How many major cycles CLEAN needs, 2026-11-02 (proposed; implemented; measured;
timings provisional; [clean-major-cycles.md](clean-major-cycles.md), branch
`clean-major-cycles`):

- **Theory.** Theorems for the batch quadratic, the Gram-gap identity, per-cycle
  descent, a running gap bound, the forcing term and the outer linear rate; 12 new
  theorems in `formal/RangFormal/MajorCycle.lean`, 46 audited in all, standard axioms
  only. The worst case is one Högbom step per cycle, so the theory does not promise
  few cycles.
- **Implemented.** `core/src/clean_major.rs`: a driver with provable and threshold
  schedules, exact FFT batches on the `2n` grid, an optimisation phase and an analytic
  w-term bound. Research code; no pipeline uses it.
- **Measured.** MeerKAT 4 h tracks at two declinations through the exact gridder, 158
  runs, seeds fixed, [archive](results/clean-major-cycles.json). Passes at 512²:
  WSClean's scheme 4-7, double-size PSF with mgain 0.8 3-4, run to the threshold 2-3,
  planar control 1. The remaining passes come from the w-term moving pixels across the
  threshold (exact peak 15.6-24.2 mJy against 15), not from the misfit gap (at most
  2e-2 of the believed decrease).
- **Negative.** The certified rules with the analytic w bound take 7-30 passes (19 of
  36 runs hit the cap of 30), because the bound is 6e3-4e6 times the gap. The
  optimisation phase raises passes to 6-10. The image-size PSF does not diverge on 64
  dishes. `Q_∞` from 20 CG iterations is too loose to use.
- **Timing.** Provisional: contended host, CPU time and load during the runs not
  recorded. A speed-up from FFT batches is not established.
- **Next.** Timings on an idle host, real data with many visibilities, faceted PSFs,
  an ℓ∞ stopping analysis.

E6, the last of the core table writer (big plan;
[e6-table-writer-final.md](e6-table-writer-final.md)), 2026-10-31
(implemented; measured):
rang's core now writes TiledDataStMan hypercubes (addHypercube and
extendHypercube, coordinate and id values, rows added to a hypercube,
hypercubes of several row axes), TiledCellStMan tables, IncrementalStMan
string arrays, tiled managers without a default tile shape and MultiFile
tables of any block size with casacore's block order (bucket- and
tile-cache writes during a session, the free list, header continuation),
as casacore does. 20 of 21 frozen cases are byte-identical to casacore
(3.8.1 through python-casacore; 3.7.1 through a pinned C++ oracle for the
hypercubes; 3 with the masked MultiFile header tail); IS-arrays differs
only in array-file alignment gaps that the frozen gap walk could not
mask (post hoc: all 677 bytes are gaps), so criteria 1 and 3 fail as
frozen; read-back, E3-E5 regressions, serialisation, refusals and the
cross-version check (3.7.1 and 3.8.1 write the same TiledCellStMan table)
pass. MultiHDF5 is refused as not supported (libhdf5 layout; two
casacore runs differ in an HDF5 modification time); no writer error
names E6. W4-4 is absorbed: 2-D string-array keywords are now stored in
C order as python-casacore stores them (a 2x3 keyword table.dat differed
in 61 bytes before, identical after). `outputs/e6-20261031-01`,
`research/results/e6-table-writer-final.json`.

W4-1 receipts record what changed the result (big plan wave 4 fix task;
[w4-1-receipts.md](w4-1-receipts.md)), 2026-10-31 (implemented; measured).
`rang.receipt` version 3 records the value of every result-affecting
`RANG_*` variable, from one registry (`rang.core.ENVIRONMENT`, 37 names, 29
recorded; a grep test fails on any unregistered variable), and a `source`
record (checkout or distribution, version, extension SHA256). The K, L1, L2,
L1-M, C1, imaging and L5 records carry the same `rang_environment`. The
solver takes `options=` and `trace=` explicitly; the Rust core reads no
environment. From a wheel, `commit` is null and `source_receipts()` hashes
the installed package (W4R-01, W4R-02). Results are unchanged: the P9
identity suite and the K, L1, L2, L1-M, C1 and L5 comparators are identical,
and L5 run through the new argument equals the archived sweep bit for bit.
`RANG_C1_LIB` and `RANG_DF1_LIB` are retired (W4-3).

W4-5, the release metadata (big plan wave 4 fix task;
[w4-5-release.md](w4-5-release.md)), 2026-10-31 (implemented; measured):
`rang.__version__` and `rang-core --version` (`rang-core 0.1.0`) read the
one version in `pyproject.toml`, and a test checks that the three
`Cargo.toml`s, the lock files and `docs/conf.py` agree. The classifiers list
all five wheel platforms and Python 3.10–3.14; Documentation, Issues and
Changelog URLs are added; the frozen `flagging` extra is dropped. The
README renders on PyPI with no relative URL. `CHANGELOG.md` has a 0.1.0
section, and the release job uses it as notes. `release` and `publish`
refuse a tag that differs from the version before any upload. The actions
are on their Node 24 majors, and actionlint is clean. The sdist is 250
entries and 1.2 MB, down from 1,012 and 5.4 MB; it builds a wheel and runs
the wheel test subset on its own. check-all `overall: PASS`. The workflow has
not run on GitHub; a `workflow_dispatch` of the pushed branch is the next
check. v0.1.0 still waits on W4-1 and W4-3.

W4-3 (2026-10-31, measured; [w4-3-kernels.md](w4-3-kernels.md)): the
extension binds `closure_scores` and `fluxstd_eval`, and no kernel call runs
Cargo. The standalone builders, the ctypes fallbacks and the dead P5 branch
are gone. The kernels are byte-identical to the standalone builds, and a
wheel without cargo runs both. This closes W4R-06 and W4R-16.

W4 final review (big plan wave 4), 2026-10-31 (reviewed; measured;
[w4-review.md](w4-review.md)). It is a read-only `/code-review` of `main` at
`17653e4`:

- **Checks.** `bash tools/check-all.sh` passes (784 passed, 10 skipped,
  730 s). The suite's archive comparisons pass, with one skipped:
  `test_task_k_additions_equal_the_archive`, whose input is absent. The
  live kernels are bit-identical at 1–4 rayon threads and under the
  gridder's SIMD and plane-group settings. cargo-audit and pip-audit report
  no advisories.
- **Findings.** 17: 1 high, 8 medium, 8 low.
- **High.** `RANG_SOLVE_OPTIONS` changes the solver's gains, and no receipt
  records it.
- **Medium.**
  - Wheel installs record the commit of any enclosing git repository.
  - The extension takes array sizes on trust and reads Fortran-ordered
    arrays transposed; an out-of-bounds write was reproduced.
  - `flag_rows` does not check its input lengths; one row short gives
    different flags and no error.
  - The closure and flux-standard kernels still build with Cargo, so they
    fail from the wheel.
  - 2-D string-array keywords are stored in an element order different from
    python-casacore 3.8.1.
  - There is no `--version`.
  - The classifiers list Linux only, and the README breaks on PyPI.
  - Text I/O depends on the Windows locale.
- **Release.** v0.1.0 is no-go as it stands; it is go after W4-1
  (receipts), W4-3 (kernels into the extension) and W4-5 (release
  metadata).
- **Fix tasks.** W4-1 to W4-8.
- **Outputs.** `outputs/w4-review-20261031-0{1..5}`.

NB-CARTA, an optional CARTA helper for the notebooks (big plan;
[nb-carta.md](nb-carta.md)), 2026-10-31 (implemented; measured):
`rang.notebook.carta` writes a NumPy image or cube, or the core's dirty
image, to FITS in a session directory and opens it in a running CARTA
backend through CARTA's wrapper (`open`, `snapshot`, `available`;
`channel_cube` images channel blocks with the core). The `[carta]` extra
holds the PyPI dependencies only: carta-python has no PyPI release, its
distribution name collides with the unrelated PyPI `carta`, and PyPI
refuses direct references, so the wrapper installs from commit
`989af8ed` (v1.2.0) by a documented command. The backend runs in
`cartavis/carta:6.0.0` and the views render in a pinned headless
Chromium (SwiftShader WebGL), both by digest and on 127.0.0.1 only;
nothing starts unless asked. On WSL the LUNO whole-array dirty image
(1024²) and an 8-plane channel-block cube of the LUNO slice open from a
notebook kernel (7.1 s and 0.27 s) and snapshot with the raster drawn;
on native Windows `available()` is False, `open` raises, and notebook
04's new cell (`RANG_NOTEBOOK_CARTA=1`, default off) prints its skip
line. `outputs/nbcarta-20261031-01`.

L5-C CASA `gaincal` as the second solver comparator (big plan),
2026-10-31 (implemented; measured; [l5c-casa-gaincal.md](l5c-casa-gaincal.md)).
Protocol frozen first. CASA 6.7.6 `gaincal` (O-CASA's image) solves on
L5's own intervals (2 integrations × 32 channels: one call per chunk,
scans relabelled to the core's time bins, `solint='inf'`,
`minblperant=1`, `minsnr=0`), flags and model, with the held-out cells
flagged, on the fixture and the LUNO four-station slice. Held-out test
error on the parallel hands against the core's QuartiCal port: +7.6e-5
on the slice (within L5's δ = 1e-4) and +1.23e-4 on the fixture
(outside); both are below the core's unrefitted diagonal part (+9.4e-5,
+2.4e-4), and what the remaining gap is due to is not measured. CASA's
`applycal` and the core's reader (new `nearest` time interpolation)
agree to 6.2e-7. The convergence tail is reproduced on the slice: the 4
intervals where the core's cap-50 iterate is 1e-4 from its
500-iteration run are all unsettled for CASA (enrichment 5.6 against a
threshold of 5); post hoc, all 12 intervals with a gain failing the
core's test at the cap rank in CASA's top 2 % (slice) / 30 % (fixture),
and six of the slice's seven are under-constrained. CASA never hits its own
50-iteration cap in a first solve: its chi-squared stop leaves the
products 3.8e-5 (slice) / 6.4e-4 (fixture) from its restarted solution.
The fixture is undecidable (no interval at 1e-4), the whole array not run
(the frozen budget rule: 341 min against 60). CASA costs 75–350× the
core's D wall as run. No default changes. Archive
`results/l5c-casa-gaincal.json`.

DF2c, `--gridder` for the campaign runs (big plan), 2026-10-31
(implemented; measured; [df2c-campaign-gridder.md](df2c-campaign-gridder.md)).
Plan frozen first. `--gridder wstack|wgrid` now reaches all five campaign
drivers: `rang-core campaign run`, the `campaign-array`, `campaign-1830` and
`campaign-fieldmodel` run scripts, and `run_c1.py`. For `wgrid`, L1-family
runs image in one call. The run records `settings.gridder` with the plan
(ε, Rayon threads, backend, the `_ex2` entry point), and every image records
`gridder_name` and its own plan, which closes DF2b's L1 receipt gap. The
default `wstack` is bit-identical to before: 28 precondition FITS, every
image number and three whole-array images. L1, L2, L1-M and C1 also ran end
to end with `wgrid` on four stations. Post hoc, all 44 archived arms of L1,
L2, L1-M and C1 were re-imaged with `wgrid` from their saved gains and
flags. Before that, the `wstack` replay reproduced every arm (equal numbers;
L1 `-01` within 1.1e-15). Against the archived images the move is aliasing
at the edge: dirty L∞ ≤ 0.45 % of the peak on chunk 0 and 0.68 % on L2,
≤ 0.017 % in the central half. The residual RMS drops by 0.36–1.1 %. All 55
recorded residual-RMS calls are unchanged, with ratio moves ≤ 1.4e-4. No
verdict changes. Per whole-array image at 4 threads, `wgrid` grids in
4.2–7.4 s against `wstack`'s 11.5–21.4 s with four groups.

A-FLAG AOFlagger second oracle (big plan), 2026-10-31 (implemented;
measured; [a-flag-aoflagger.md](a-flag-aoflagger.md)). Protocol frozen
first. A pinned image, `rang-aflag-aoflagger:3.5.0` (Ubuntu 24.04 +
KERN-10 AOFlagger 3.5.0, python-casacore 3.7.1), runs Lua translations of
CARACal's Tricolour first-pass (and mild) `sum_threshold` steps on the
core's polarised intensity for task D's four controls. Two strategies:
mapped (AOFlagger idiom) and tuned (as close as the Lua API allows).
**Kernel level: every difference attributed.** A NumPy bridge
reproduces both Tricolour's raw SumThreshold flags (re-chained from the
unmodified 0.2.1 functions, gate 16/16) and AOFlagger's own flags
(absolute thresholds, hybrid test) bit for bit on all 48 passes.
Against AOFlagger's intended kernel every differing cell lies on the
documented differences: fixed lengths 1–256 with ρ = 4/3 (against
1.3), clamping against exclusion, and input flags as values against as
missing. One χ₁ = 0 chunk adds 408 cells. So the port is AOFlagger's
SumThreshold up to those. Against the shipped 3.5.0 binary, a further
AOFlagger defect adds cells, so the frozen rule is not met there (a
labelled reading).
**Stage level: the flaggers differ.** On cells unflagged at entry,
mapped agrees 0.60–0.95 and tuned 0.63–0.95; the final FLAG agrees
0.937–0.999. The largest cause (post hoc) is Tricolour itself: flagged
samples enter its windows as 0 − background, so on high-SNR baselines
every input flag is detected and grown. Removing only that takes the
first step's 93,341 new flags to 224. Two AOFlagger 3.5.0 bugs:
`sumthreshold_masked` reads its direction flags from the wrong Lua
arguments, and the masked horizontal kernel keeps one missing sample in
the running sum. The frozen hybrid run was void (wrong all-flagged-mask
idiom); post-hoc fixes are labelled. Cost: AOFlagger 0.63–0.94 s per
control on one thread, the port 0.92–1.48 s on one and 0.31–0.52 s on
four. Next: none required. Upstream reports wait for the user's say.

E5, the rest of the core table writer (big plan;
[e5-table-writer-rest.md](e5-table-writer-rest.md)), 2026-10-31
(implemented; measured):
rang's core now writes IncrementalStMan columns (values and rows, the MS
bookkeeping columns and POINTING), removes the last row of a
StandardStMan, writes variable-shape and multi-hypercube TiledShapeStMan
columns (rows without a hypercube, the fixture's FLAG_CATEGORY, new rows
of a CASA MS), creates TiledDataStMan (no hypercube) and MemoryStMan
tables, and writes big-endian and MultiFile tables, all as casacore 3.8.1
does. 21 of 23 frozen cases are byte-identical (2 with the masked
MultiFile header tail); 2 ISM cases differ only in array values casacore
reserves and never writes, which hold uninitialised heap memory
(casacore's own MALLOC_PERTURB_ run differs there, post hoc), so criteria
1-3 fail as frozen; python-casacore reads the reopened MemoryStMan
columns as zeros and uninitialised values where the protocol expected an
error (the core refuses). E3 and E4 unchanged, refusals (E6:
TiledDataStMan values, TiledCellStMan, MultiHDF5) and serialisation pass;
C-ABI creation skipped (P7 removed ctypes). `outputs/e5-20261031-01`,
`research/results/e5-table-writer-rest.json`.

T1 casacure as the second oracle (big plan), 2026-10-30 (implemented;
measured locally; [t1-casacure-ci.md](t1-casacure-ci.md)). Plan frozen
first. An optional `[casacure]` extra (`casacure==3.8.35`, with a marker
for the platforms that have wheels: none for macOS x86_64 or for cp310 on
macOS arm64) and a read-only adapter `rang.oracles.casacure`. The wheel
test (`tools/wheel/test.py --fixture-cache`, `wheels.yml` `test` jobs)
now downloads the public fixture (45 MB, hash-verified, cached) and runs
`tests/test_t1_casacure_oracle.py`: the core reader against casacure on
every column of the five fixture MSs (70 tables), the golden archive's MS
entry through casacure, and the core's E3 writes and E4 creations read
back by casacure (cells and keywords; casacure's writes are never a
reference). The backend golden test's MS case now runs from the fixture
(scan 9 is ms0 file for file) instead of skipping, on every job including
macOS x86_64. Passes on WSL and natively on Windows (Python 3.10 and
3.14, wheels built fresh, no unexpected skip); macOS and aarch64 run on
the merge push. Two new casacure defects: it cannot read a fixed-shape
Direct string array even when casacore wrote it, and its `getcol` of a
ragged variable-shape column silently returns the first row's shape (the
adapter refuses it). The core reader's misleading errors on string-array
columns are an E5 item. Next: the first CI run's timings.

DF-IO formats (big plan; [dfio-formats.md](dfio-formats.md)),
2026-10-30 (implemented; measured): `rang.formats` reads and writes the
file formats of the tools the core replaces, each judged by its own tool.
Passing as frozen: CASA caltables read (K, G, B, Df, T) and written
(CASA's bytes but the masked gaps, `applycal` bit-identical); QuartiCal
0.2.7 gain stores read and written (metadata byte-identical, `load_from`
bit-identical, a core-made store to 5.9e-8; a core blosc defect with
out-of-order blocks fixed); Tigger ASCII and `.lsm.html`; WSClean lists
read and predicted by Crystalball within the float32 bound (99.95 % of
cells bit-identical); DicoModel read through a restricted unpickler;
ClusterCat; killMS solutions merged by `MergeSols`; CASA flag versions
restored by `flagmanager`. Failing as frozen: the core's own `applycal`
model to 1e-6 (post hoc K, G, B, T pass; Df and the chain within 10.3
float32 eps but up to 6.9e-5 relative where cross hands cancel), WSClean
shape text (1 ulp, a format limit), Tigger's ASCII and BBS writers (Tigger
defects), and the H5parm (a setup error and DP3's one-field rule; post hoc
losoto reads and writes it exactly and DP3 `applycal` applies it to 4.0e-7
after NUL-terminated strings). `rang-core formats check|convert`; image
`rang-formats-oracle:20261030`; `outputs/dfio-20261030-01` to `-04`,
`research/results/dfio-formats.json`.

MK1 MVFv4 loader (big plan), 2026-10-30 (implemented; measured;
[mk1-katdal.md](mk1-katdal.md)). Protocol frozen first. An optional
`[meerkat]` extra (`katdal==0.23`, `katsdptelstate[rdb]==1.0.0`; installs
on Python 3.12–3.14 on Linux and 3.13–3.14 on native Windows; python-lzf and rdbtools
are sdist-only, so a C compiler is needed everywhere, and cityhash has no
cp314 wheel) and `rang.meerkat`, which opens an MVFv4 archive (RDB URL with
token, or a local `.rdb` and `.npy` chunk store) through katdal and yields
row chunks in the core's layout (ANTENNA1/2, TIME, FLAG_ROW, UVW, DATA,
FLAG, WEIGHT_SPECTRUM, plus the uint8 FLAG_BITS) with mvftoms' column
conventions (rows time-major, baselines in its own lexicographic order);
`examples/fetch_meerkat_mvf.py` writes them to `.npy` without an MS. No
public MVF archive exists (SARAO's are token-gated), so the acceptance ran
on a synthetic archive written by katdal's own writers: shuffled baseline
order, partial chunks, a lost chunk, a zero autocorrelation and an L1 flag
stream. Against arrays rebuilt from the raw chunks, katdal's own arrays
(local and over HTTP) and `mvftoms.py`'s MS read by the core, DATA, FLAG,
FLAG_BITS, WEIGHT_SPECTRUM, TIME and ANTENNA1/2 are bitwise equal; UVW is
within 1.8e-12 m of katdal and bitwise equal to mvftoms. Weights are
`weights × weights_channel` divided (not multiplied) by both
autocorrelation powers. katdal by default replaces the L0 ingest flags
with katsdpcal's `sdp_l1_flags`; L3 must open with `upgrade_flags=False`
to see native observatory flags (bits static, cam, data_lost, ingest_rfi,
predicted_rfi). katdal's dask read is 0.19 s of 0.75 s per 64-antenna,
4,096-channel dump, so the chunk reader is not ported. Next: L3 when the
observer's data arrive, preferably as MVF; then the LUNO cross-check (c).

B1-2 identifiability survey (big plan wave 3), 2026-10-30 (implemented;
measured; [b1-2-identifiability.md](b1-2-identifiability.md)). Protocol
frozen first. Which beam and pointing directions can the data
constrain once per-antenna diagonal gains (2 dumps × 32 channels) and
the sky fluxes (flux and spectral index per component) are profiled?
Five sets: LUNO 1934−638 chunk 0 on four stations and on the whole array
(CARACal lsm), 1830−211 (a point), the ESO137 pilot (subset row chunk
0, fetched 1.04 GB) and a new ESO137 track set (one 3.5-min chunk of
tile 20 from each of the 7 scans, 1.88 GB, 160° of parallactic angle).
Beam: the B1-0 holography array average with analytic spline
derivatives. Noise: calibrated from adjacent-channel differences (the
LUNO weights over-state the variance by 10–60×). Field model for ESO137:
the stored MODEL_DATA is all zero and the subset DATA is uncalibrated,
so three frozen self-calibration and CLEAN rounds; E0 passes, but the
model is the central radio galaxy only (157 components within 0.26°).
The frozen convergence rule fired, so the verdict uses 16-channel beam
evaluation. **B1 does not close null.** Per-antenna pointing is
constrainable on the ESO137 pilot (60/60 antennas, σ ≈ 0.07′ in 3.5 min,
ρ ≈ 0.8) and per track chunk, and marginally on 1934 (52/53, 0.18′, only
with the recalibrated noise). Squint is constrainable on 1934 and
ESO137 (0.004–0.04′). Array-common pointing and ellipticity are
constrainable only on the track (0.005′, 0.06 %), and array-common width
nowhere (0.54 % against 0.5 %). The snapshot array-common pointing that passes on 1934, 1830 and the
pilot is the beam's chromaticity inside a 32-channel gain interval: a
per-channel bandpass removes it exactly on the 1830 point (post hoc).
Native anchored response: 5,446 of 6,048 calls pass; it agrees with
NumPy to 2.5e-14. Next: B1-3, which first re-runs the survey with a
per-channel bandpass nuisance and per-antenna beams, then fits only the
surviving directions against both baselines.

X2 GPU gridder (big plan), 2026-10-30
(implemented; measured; [x2-wgpu.md](x2-wgpu.md)). The w-stacking
gridder runs on the GPU through `wgpu` 30 behind the cargo feature `gpu`
(`RANG_GRIDDER_DEVICE=gpu`), no CUDA: gather gridding without atomics, a
mixed-radix Stockham FFT in WGSL at WSClean's exact padded size and the
projection with an ordered layer sum, in f64 (Vulkan `SHADER_F64`) with
the counters from the CPU code. On the RTX 4070 Ti from native Windows the
f64 path passes the task C, I and K comparators with the CPU's margins
(response fraction 1.31e-7 of 1.6e-7), differs from the CPU images by at
most 2.2e-15 of the peak and is deterministic; one frozen clause fails
(the PSF normalisation entry is not bit-equal, 4.4e-16). Per image, f64
including transfers: four stations 0.09–0.12 s against 0.30 s on 16
threads (2.5–3.3×), the 23.8 M-visibility whole-array image 2.5 s against
3.1 s, where the CPU's serial counters pass (1.1 s) now dominates. An f32
path passes C and I but fails K's residual metrics and stays
experimental. Archive `results/x2-wgpu.json`.

E4 core table creation (big plan; [e4-table-create.md](e4-table-create.md)),
2026-10-30 (implemented; measured): rang's core now creates casacore tables
as casacore 3.8.1 does: new tables from a description (StandardStMan,
TiledColumnStMan, TiledShapeStMan, keywords, `table.info`), rows added and
removed on new and existing managers, string arrays, `default_ms` with its
subtables (SOURCE on request), and CASA calibration tables (G, B, K, Df)
written in CASA's own sequence. 18 casacore cases and CASA 6.7.6's own K,
G, B and Df tables are byte-identical except casacore's uninitialised
alignment gaps in `table.fNi` (masked, 7 of 22); CASA `applycal` with the
core's copies gives bit-identical CORRECTED_DATA and FLAG, a core-made G
table applies to 4.3e-7; read-back, determinism (twin and MALLOC_PERTURB_),
E5 refusals, E3 and serialisation checks pass. Freed StandardStMan buckets
are now byte-identical too (E3's open item). Deferred to E5 with an error:
IncrementalStMan writes (an empty one is written for POINTING only),
big-endian, variable-shape tiled columns, MultiFile, MemoryStMan,
TiledDataStMan, removing the last StandardStMan row, creation in the C ABI.
`outputs/e4-20261030-01`, `research/results/e4-table-create.json`.

D3 science notebooks (big plan, documentation track), 2026-10-30
(implemented; executed and built locally and on a clean export;
documentation only; [d3-science-notebooks.md](d3-science-notebooks.md)).
Two guided notebooks in `notebooks/science/`, rendered on the site. 06
tells the gain-TV flagging experiment from the question to the null
verdict: the method live on the fixture, every real-data number read from
`flagging-verdict.json` (the pre-registered calls, the TV policy's
selections, the cost clause, L1-M, C1, L5, A1, O-CASA) and a live
`verdict_tables.py --check`; L3 as the reopening item. 07 takes the
original beam and pointing question through the Rust toy, the JAX
reference path (agrees with Rust to 1e-11 Jy), the smooth pointing solver
and the observability audits (live, equal to their archives), then B1-0
from `b1-beam-product.json` and B1-1 (the SARAO/SKA fit reproduced live on
the fixture), with B1-2 and B1-3 as proposed and their frozen rules
quoted. Switches `RANG_NOTEBOOK_LUNO`, `_SLOW` and `_HOLOGRAPHY` are
opt-in; the site never renders the CC BY-NC holography maps. Readers in
`rang.notebook.science`. A clean export ran the workflow's steps with 0
Sphinx warnings; the science notebooks take 10 s and 40 s.

Certified CLEAN on real data (CLEAN programme question 3;
[clean-certified-imaging.md](clean-certified-imaging.md)), 2026-10-30
(implemented; measured on the LUNO 1934−638 four-station slice; branch
`clean-certified-imaging`). `core/src/clean_certified.rs` is a Cotton-Schwab
driver over the exact wgridder with Clark, Theorem 6 and WSClean-mgain minor
rules and the four diagnostics (Gram gap per major cycle, `Q_∞` by CG, ERC
of the component list, ascending-step audit); six tests, including the
closed form of the gap (a quadratic form in the components with the ignored
beam, both signs: the expected "positive with a patch" is false) and no
ascending step under the provable rule in 72 runs. On O-CASA arm C's
`c.ms` through the core reader, Stokes I and Briggs 0.5 (117,556
visibilities and weight sum equal to WSClean's): **WSClean 3.7 diverges at
gain 0.1, mgain 0.8, 50 mJy in all four variants**; the driver with
WSClean's image-size beam reproduces that run to 5e-6 Jy and shows the
cause (Gram gap 99 Q and 158 ascending steps in the third major cycle,
components at the image edge where the truncated beam misses 0.77 of the
peak); with the exact 1024² beam it converges in 65 components and 4 major
cycles, residual rms 22 mJy, flux 14.885 Jy against the band-averaged
model's 14.953 Jy. `Q_∞/Q_0` ≤ 3.69e-4 (flat in the CG budget); the ERC
never certifies on this beam (coherence 0.99972). The provable rule removes
ascending steps but its low-misfit models put 4.7-7 Jy off-centre and up to
2.5 Jy negative: descent certified, model not. **For DF1/DF2b:** O-CASA's
WSClean reference `r1-*.fits` uses WSClean's default minimum-grid-resolution
upsampling and is 17 % (L∞/peak) off the exact transform on this field;
`-no-min-grid-resolution -wgridder-accuracy 1e-6` matches the core to
2.6e-7. Python: `rang.core_clean.certified_clean` (PyO3, 3 tests). Archive
`results/clean-certified-imaging.json`.

DF2b, the exact gridder in the imaging drivers (big plan), 2026-10-30
(implemented; measured; [df2b-wgrid.md](df2b-wgrid.md)). The imaging paths
of tasks C, I, K and L1 now take `core_grid.invert(...,
gridder="wstack"|"wgrid")`: `run_core_gridder.py --gridder`,
`rang-core imaging run --gridder`, `core_campaign.image_arm` and L1's
driver through its image dict. `wstack` stays the default and is
bit-identical to before on every C, I, K and L1 image. A two-weight entry
point (`Weights::F32Product`, `vis2dirty_ex2`) forms the reader × imaging
weight in the core, bit-identical to the float32 product, so the drivers'
copy is gone. `rang._core` binds the gridder, so `core_wgridder` no longer
builds its standalone library; DF2a's 20 hashes and DF1's gates pass
through the binding. Against WSClean 3.7's wgridder (O-CASA's image, ε
1e-6, run on an MS written from the same gridder inputs), the exact
gridder agrees within 2.5–4.0e-7 of the peak on the 15 C/I jobs, the six K
arms and L1's 34 M-visibility whole-array image. The counters are equal.
That MS harness was first checked pixel for pixel against the archived
WSClean 3.6 image. The comparison closes DF1's open item 4 (orientation
and normalisation) and shows that WSClean does not divide by n; at
WSClean's default accuracy 1e-4 the gap is 1.5–4.2e-5. Against archived
exact-gridder images: K 5.8e-14 (bound 1.8e-13, set from a measured
row-permutation floor); C and I within one float32 ulp. Against the
archived w-stacking images the move is the predicted aliasing: 17–32 % of
the peak at the edge and ≤ 0.56 % in the central half for C/I/K, but
0.45 % and 0.01 % on L1's whole-array image. I's 23 metric values move as
DF1 found, K's residual RMS by +0.65 % and L1's by −0.36 %, and no
hypothesis call changes. Per image at 4 threads the exact gridder takes
0.19 s against 0.66 s (68 against 218 MB) at four stations, and 8.9 s
against 23.5 s on L1 (4.4 s at 16 threads); WSClean 3.7 needs 42 s at
`-j 4`. Open: `--gridder` for `campaign run` and `campaign-array run`, and
the plan in L1's receipts.

RV1 re-validation (big plan), 2026-10-30 (implemented; measured;
[rv1-revalidate.md](rv1-revalidate.md)). Neither Tricolour 0.5.0 nor
QuartiCal 0.2.8 is released (PyPI: 0.2.1 and 0.2.7), so the release branches
were used at recorded commits. Tricolour `0.5.0-dev` `367ff54` (Python
≥ 3.11, Ray Serve, xarray-ms) reproduces 0.2.1 on task D's four controls: all
44 strategy-step windows, the polarised intensity bit for bit and the final
FLAG are identical, and the `tricolour` CLI run end to end matches
`after-native.npz`, so task D's comparator passes the core against 0.5.0-dev
unchanged. The one difference is latent: `apply_static_mask`'s `uvrange` now
selects |uvw| ≤ 550 m, where 0.2.1 and the port select 0.5·|Δp|² ≤ 550²
(up to 778 m), which affects 165 of 1540 LUNO array baselines and none of
task D's. #112 leaves one kernel signature; #114 gives identical flags but
needs a rebase, because its branch predates #112. QuartiCal `v0.2.8-dev`
`d54c46b` fixes #452 (#456), which moves the capped 50-iteration gains away
from the archived 0.2.7 oracle: entries by up to 1.7e-3 on the fixture
(gauge only) and 2.8e-4 on LUNO, products by up to 1.1e-7 and 9.7e-5. The
core with `RANG_SOLVE_OPTIONS=qp_weights=transposed` (L5) reproduces
0.2.8-dev to 1.2e-15, with the same flags, iterations and converged
fractions, and #440's default referencing of `complex` is a pure gauge change
(products equal to 5.6e-16). A 0.2.7 rerun in a fresh venv reproduces the
archive to 4e-16. No port change. Archive `results/rv1-revalidate.json`.

CLEAN implicit objective (research question 1 of the CLEAN programme;
[clean-implicit-objective.md](clean-implicit-objective.md)), 2026-10-30
(proved; implemented; measured; partly checked). Högbom CLEAN with gain γ is
incremental forward stagewise (FS) with step γ|r_p| (LS-Boost; the
subgradient method on the peak residual, Freund, Grigas and Mazumder). New
proof: as γ → 0 and ε → 0, parametrised by ℓ1 arc length, CLEAN and FS_ε
converge to one limit; in data space it is unique for any dictionary (the
gradient flow of the peak residual, by monotonicity of the ℓ∞
subdifferential), its direction is the minimum-norm (non-negative least
squares) one, and in model space it is Hastie, Taylor, Tibshirani and
Walther's monotone lasso when the tied atoms are independent; the converged
small-gain model tends to the path's end point. No pointwise objective
exists (their Lemma 2); the implicit objective is local: dQ/dL = −max|r|,
the steepest possible per unit arc length. Example `clean_implicit`
(36.5 s; track-uniform and snapshot-natural, noiseless disc and six
sources, matched misfit 1e-1 to 1e-5, exact lasso homotopy): CLEAN model →
FS₀ by 22-64× (disc) and 280-2,400× (points) from γ = 1 to 0.003, rate about
γ^0.76-0.86 (disc) and γ^1.0-1.4 (points); the lasso path has 3,503-5,836
zero crossings on the disc (arc 64-70× its norm), so lasso ≠ small-gain CLEAN
there (rms 0.13-0.25); on the track six-source scene the lasso is monotone
and the two agree to 3e-7. FS₀ itself goes negative on the snapshot (−0.22),
so small gain does not imply positivity; the disc's near-tied sets become
numerically dependent, so model convergence for extended emission is
measured, not proved: the conjecture holds unconditionally for residuals
and misfit, for models only under tied-atom independence. Lean:
`Stagewise.lean` (step lemmas, ℓ1 steepest descent, optimality of the argmax
pick, arc length, data-space uniqueness for right-differentiable limit
curves; the compactness and almost-everywhere steps are prose only),
`Separation.lean` (Proposition 4'), `Clark.lean` (Theorem 6); 34 audited
theorems, standard axioms only. Branch `clean-implicit-objective`.

CLEAN phase transition (question 2 of the CLEAN programme; user-directed;
[clean-phase-transition.md](clean-phase-transition.md)), 2026-10-30
(implemented; measured). The question: when does Högbom CLEAN recover point
sources exactly? It was measured on MeerKAT, VLA-C, WSRT and KAT-7 (simms
layouts, [data/README.md](../data/README.md)), as snapshot or 4 h track,
with natural or uniform weights. Each cell had 100 trials for
`k = 2..32` sources and minimum separations of 1-24 pixels, noiseless with
gain 1 and with 1 % noise and gain 0.1; the run took 301 s. Proven in
prose: an exact two-source rule for gain 1 (dirty peak on a source and
`max_q ‖B_SS⁻¹B_{S,q}‖_∞ < 1`, where the ERC asks for the ℓ1 norm), which
agrees with all 40,000 two-source trials; Theorem 7, which replaces
Proposition 4''s counting bounds by worst separated sums; and Theorem 8, an
anchored bound that keeps the ERC's sidelobe cancellation. Theorem 8
certifies 14 of 80 (configuration, `k`) cases, against 3 for Proposition 4'
and Theorem 7, and reaches the exact two-source worst case on 7 PSFs.
Measured: `d*(k)` is 1, 1, 1, 2-3, 3 pixels for `k = 2..32` on the MeerKAT
and VLA-C uniform tracks and larger on natural-weight PSFs. There is no
transition on the degenerate WSRT snapshot (an east-west line, `μ_1 = 1`)
or on the floor-limited KAT-7 snapshot. Every sufficient condition is far
above the measured transition for `k ≥ 4`: 32 sources at 3 pixels recover
in 100 % of trials, of which at most 1 % have `η < 1`. Two negative
results: there is no universal success curve beyond the ERC threshold (the
per-configuration 95 % point of `η` lies at 0.99-1.41, and no other
statistic collapses better), and with 1 % noise no configuration reaches
95 % exact support, a rate set by `μ_1` rather than by separation. A
measured pattern: for many sources the far-sidelobe floor decides. Not
done: figures (no matplotlib in `.venv`) and Lean proofs. Archive:
[results/clean-phase-transition.json](results/clean-phase-transition.json).

D1 documentation site (big plan, documentation track), 2026-10-30
(implemented; built and measured locally; not yet run on GitHub;
[d1-docs.md](d1-docs.md)). A Sphinx site (furo, myst-nb, autodoc) in
`docs/`: the status line and the flagging null verdict on the landing
page, installation from the wheel and from source, concepts, the
`rang-core` help texts (generated, checked by a test), the five tutorials
executed with papermill on the public fixture, the API reference of all 66
public modules with the three quoted constants, the research story linking
the reports, contributing and licence pages; PNG and ICO renders of the
logo (resvg-py, Pillow). `.github/workflows/docs.yml` builds the
extension, executes the notebooks (LUNO off, teaching strategy) and builds
with `-W` on every push and pull request, and deploys to GitHub Pages from
`main` once the user selects "GitHub Actions" as the Pages source. A clean
export ran the workflow's steps in 2.2 min (extension 89 s, notebooks
27 s, Sphinx 12 s, 0 warnings).

P12 rename (big plan), 2026-10-30 (implemented; measured;
[p12-rename.md](p12-rename.md)). The package is `rang` (`import rang`,
extension `rang._core`, `python/rang/`); the project, repository and PyPI
distribution are `rang-core`; the CLI is still `rang-core`. The move used
`git mv` with history (71 × R100). On P9's 20-case suite through `rang-core`,
every comparator verdict, count, stdout and receipt is identical. CLI
receipts are now `rang.receipt` v2 (`environment.rang_core`). The wheel is
`rang_core-0.1.0-cp310-abi3-*` and passes the cargo-absent test on Linux and
Windows, and the full checks pass on both. Archived notes, results and
`history/` keep `rangtoy`. Windows `rang-core check` is green again: 18
pre-existing failures, from the C1/DF1/FS1 standalone builds and the P11
test's encoding, are fixed. Publishing is the user's: tagging `v0.1.0` runs
the workflow, which publishes `rang-core` by trusted publishing.

CLEAN theory, continued (user-directed; [clean-theory.md](clean-theory.md)
§3, §5), 2026-10-30 (implemented; measured). Lean now covers Theorems 2 and
3 in full: `formal/RangFormal/FiniteDim.lean` (a positive greedy constant on
the finite-dimensional span by compactness; geometric rate for data in the
span) and `Projection.lean` (the CLEAN sequence ignores the data component
orthogonal to the atoms; the misfit floor Q_∞; Q_K − Q_∞ ≤ ρ^K (Q_0 − Q_∞)
for arbitrary data; the model converges); thirteen audited theorems, standard
axioms only, 41 s builds. Two experiments added: E2c, recovery with 1 %
image noise and sources 8 px apart, keeps 89-99.7 % of picks on the support
but exact supports are rare except on the uniform-weight track (32-79 %),
the failures being adjacent-pixel components (neighbour coherence
0.68-0.93); E7, the coherence of a delta + Gaussian (2, 4, 8 px) dictionary
is 0.98-0.99 on every MeerKAT PSF, so no coherence-type guarantee exists
for multi-scale CLEAN. Archive `results/clean-theory.json` refreshed
(71.1 s run).

CLEAN theory (user-directed study; [clean-theory.md](clean-theory.md)),
2026-10-30 (implemented; measured). Verdict on "CLEAN was never proven":
false for Högbom's iteration as a data fit (Schwarz 1978; his 1984 summary
read in full: Q = Δtᵀ B Δt falls by g(2−g) r² per step for 0 < g < 2 with a
symmetric PSD beam), true for the limit being the sky outside the sparse
regime, for Clark/Cotton-Schwab/multi-scale as run, and for noise. Formalism:
CLEAN is the pure greedy algorithm on the pixel atoms in the weighted
visibility space; the PSF is their Gram matrix, so the three classical
conditions collapse to one (the subtracted beam must be that Gram matrix),
and every known divergence mode is its violation. Theorems: the exact
one-step identity, square-summable peaks and residual image → 0 for τ-weak
greedy rules, convergence to the least-squares fit Q_∞, a geometric rate set
by the greedy ratio κ (≥ λ_min(B_SS)/k on a k-support, ≈ 1/N on noise), the
coherence pick condition, Tropp's ERC, a separated-source corollary, and a
provable Clark minor-cycle rule (continue while f Σ|c_j| < (1 − γ/2)|r̃_p|).
Lean (`formal/RangFormal/Clean.lean`, Mathlib v4.33.1): Theorems 1-4 checked,
standard axioms only, 44 s builds. Rust (`core/src/clean.rs`, example
`clean_theory`, 5 tests): on MeerKAT snapshot and track PSFs (64 antennas,
2″ pixels) the identity holds to 2e-13 and gain 2.1 diverges; same-grid and
patch beams raise Q on 44-93 % of steps and natural-weight ±8 patches
diverge; the on-grid coherence is 0.68-0.93 so the coherence bound allows
one source, while the ERC never failed in 9,600 noiseless trials and 12
sources 8 px apart are recovered 100 % on three of four configurations;
measured κ is 1.5-3.2× its bound; pure-noise κ matches 1/N; an off-grid
source fits Q to 1e-6 with 157-713 pixels; Clark's rule leaves 0-119 ascending
minor steps per 200, the provable rule none; a Gaussian disc is fitted to
1e-6 by every gain with limits differing by 0.26-0.42 peak rms and negative
pixels to −1.9 peak at gain 1. No pipeline change; three diagnostics proposed
(Gram-consistency gap, Q_∞ floor and κ, ERC certificate). Archive
`results/clean-theory.json`; `data/meerkat.itrf.txt` added with provenance.

B1 beam and pointing, B1-0 and B1-1 (i) (big plan wave 3), 2026-10-30
(implemented; measured; [b1-beam-pointing.md](b1-beam-pointing.md)). Protocol
frozen first. B1-0: SARAO's 2023 L-band holography cube (de Villiers 2023,
DOI 10.48479/wdb0-h061, CC BY-NC 4.0; only derived statistics are committed,
the maps stay in ignored outputs, attribution in the report) is read by HTTP
range from its stored 35 GB npz (3.72 GB: array average at 1,024 channels, 64
antennas at 9.2 MHz), oriented (s = +1, from the metrics file and katbeam's
squint sign), spline-interpolated and normalised; all three gates pass
(metrics reproduced to 0.08′ and 0.2 %; frequency interpolation 1.0e-3
median, spatial 6e-5). Against it, over 900–1650 MHz, katbeam errs 0.83 %
(median max) in the main lobe and 0.54× the signal of a 30″ offset on the
half-power ring, with a fixed 0.50 % sidelobe (measured 0.30–0.76 %); EIDOS
errs 2.1 % in the core (1.8× the 30″ signal) and 0.05 % RMS in the sidelobe,
with an ambiguous grid orientation (post hoc). Antennas differ from the array
average by 0.12–0.21 % RMS in the main lobe. B1-1 (i): the SARAO/SKA Gaussian
pointing-offset fit (SKA SDP pipeline `5ede554` with its pinned dependencies)
is ported and reproduces the pipeline's own reference on the five-scan fixture
to 8.9e-16 (scan 9 is the on-source point of a five-point pattern). On the
fixture it gives offsets of 1.4–6.0′ with formal σ 1.2–7.3′ (all within 1.9σ
of zero; 3–4 informative chunks of 14, plus three fully flagged GNSS chunks it
marks valid at their starting values). Against simulated truth with the
holography beam it over-recovers offsets by 1.2–1.5× and returns up to 0.6′
at zero offset, about half of it the beam's squint and up to 0.37′ shape bias
(post hoc); its 1σ interval covers the truth 59–78 % of the time. ESO137
(`ms1_target`, CC BY 4.0, 734 GB DATA) is the B1 target; no public store has
pointing scans. Measures frozen as the geodetic parallactic angle with astropy
as reference. Next: B1-2 identifiability survey over beam and pointing
parameters, then B1-3 pointing self-calibration against both baselines.

PC1 preconditions (big plan; [pc1-preconditions.md](pc1-preconditions.md)),
2026-10-30 (fixed; measured): the L1 and L2 preconditions pass again. Both
failures were merge interactions, not regressions inside a task. L1's
precondition compared image hashes exactly and had failed on main since the
L1 merge, because P2 (rustfft gridder, pixels within 2e-15) merged first; it
now gates on L2's tolerant comparison, as L1-M and C1 already did, and keeps
the exact comparison in its output. L2's driver broke at the P5 merge: P5
stores additions as cell indices and L2's `run` (not in P5's base) passed
them as a mask; it now expands them with `additions_dense`. No archived number
changes; the L2 replay equals pre-P5 main on every non-timing field and file;
the C1 and L1-M checkers flip only their L1-precondition fields from false to
true. `tests/test_pc1_preconditions.py` runs both preconditions (about 18 s)
whenever the LUNO inputs are on the host, the check that was missing. Lesson
for the coordinator: a merge is only verified once the preconditions of every
driver it touches have been rerun on the merged tree.

DF2a exact gridder speed (big plan; [df2-wgridder-speed.md](df2-wgridder-speed.md)),
2026-10-30 (implemented; measured): DF1's Rust port of ducc0's wgridder now
runs at ducc0's speed. Planes are gridded in sequence, the grid in tiles
under a fixed parity colouring with fixed-size tasks (deterministic, no
locks), the kernel evaluated by ducc0's even/odd Horner scheme with FMA, the
loops monomorphised on the support and compiled for AVX-512 and AVX2 (chosen
at run time), the dirty image and PSF in one pass, data and weights read in
place (new `_ex` entry points). Per image (f64, ε 1e-6) 1.06–1.07× ducc0 0.42
on a 23.8 M-visibility whole-array case at 1 and 16 threads (DF1 3.6× and
6.9×), 1.13× / 1.37× on K × 41 at 1 / 16 threads (clean repeat), memory
0.68–1.07× ducc0's peak; outputs bit-identical at 1–16 threads and at every
SIMD level; all of DF1's gates pass. Not gated: the four-station K arms stay
at 1.46× ducc0 on one thread and 2.27× at 16 threads (fixed per-plane
overhead), the first images DF2b wires in. The frozen agreement bound with
DF1's outputs (1e-13) failed on wide-field and f32 images: rounding
amplification by the correction function (row order alone moves the border by
1.7e-11), flat inside and out once divided by the correction. DF1's open edge
difference from ducc0 is the same effect: the port and ducc0 are equally close
to the DFT there. Plane groups (taps reused across planes) gained ≤ 13 % at up
to 2.7× the memory: off by default. Archive `results/df2-wgridder-speed.json`.

P11 extract and retire (big plan wave 2), 2026-10-30 (implemented; measured;
[p11-extract.md](p11-extract.md)): the 21 frozen campaign modules
(`flagging*.py`, `imaging_sensitivity.py`, 11,217 lines) and their 21 test
files moved byte-identical to `history/`. What the live chains use from them,
127 top-level definitions by the static closure, is copied verbatim into 20
`core_*` extracts (`core_policy`, `core_influence`, `core_trend_run`,
`core_forecast`, `core_guard`, `core_response`, … one per frozen module, 3,389
lines), checked definition by definition against `history/` by
`tests/test_p11_extract.py`. Live Python in `python/rangtoy` 31,100 → 23,283
lines (−7,817). The live-chain suite (S1's, through `rang-core`) is identical
before and after: every verdict, class count and binary output; only receipt
provenance (trend and imaging `module_sha256`, script hashes) changes. No live
chain imports anything from `history/` (coverage, a blocked-import check, a
static check). Tests 722 → 572 collected (169 of the moved tests run live
again). The C1 driver now imports from `core_policy`; the temporary
`flagging.py` shim is gone. Reported, not P11's: the L1 and L2 preconditions
fail on current main (`all_equal: false`; a broadcast error in
`core_campaign_array.solve_flags_lean`), being traced (PC1) before P12.

L4 gain-TV flagging verdict, 2026-10-30: **closed: null**
([flagging-verdict.md](flagging-verdict.md)). Gain-TV-guided flagging was
tested on the SKA pointing fixture (2026-09-23/24) and on the public LUNO
MeerKAT L-band calibrators: PKS 1934−638 at four stations (K) and on the
whole array (L1), under three calibrator models (L1-M) and with a gauge-free
closure arm (C1), and PKS 1830−211 under two models (L2). All LUNO runs used
the core with the seed-7 split against the CARACal first-pass Tricolour
strategy. Of 90 pre-registered calls, 64 are null and 26 undecidable; none is
better or worse. The frozen policy selected no TV-guided (α > 0) mask on the
fixture or on LUNO. Against the first pass, held-out MSE agrees within 0.06 %
(matched 0.99943) and residual RMS within 0.6 % (0.5 % on the stored model;
corrected 2026-10-30 by D3). On the parallel kernels the
TV chain costs 4.6–5.9× the first pass, so neither novelty route holds. Model
completeness (L1-M), closure structure (C1), convergence (L5) and the
GNSS-band bins (A1) do not change the answer. Calibration choices (model,
solver chain) move held-out error 30× or more than any flag. Scope: one
observation, processed FLAG and weights. Native data (L3) would reopen it.
Table `results/flagging-verdict.json`. Next: B1, the beam and pointing
question.

FS1 flux standards (big plan; [fs1-flux-standards.md](fs1-flux-standards.md)),
2026-10-30 (implemented; measured): CASA 6.7.6 `setjy` flux standards ported
to `rangtoy.fluxstd` (canonical) with a Rust per-channel kernel
(`core/src/fluxstd.rs`). PB2010 (3C48, 3C138, 3C147, 3C286, 3C295, 3C196,
1934−638), Baars (5 + 1934−638), Stevens-Reynolds 2016 (1934−638) and
CARACal's `manual` model equal `setjy` to ≤ 1.6e-14 on 0.05–50 GHz and
bit-for-bit in float32 MODEL_DATA; unknown names refused where CASA writes
1 Jy with a SEVERE log. CASA stores compiled coefficients as float32; SR2016
switches to its power law at the 11.1496 GHz crossing, not the documented
11 GHz. Erratum to O-CASA: its 2.7e-6 SR2016–Reynolds residual was its own
float32 row mean; CASA's MODEL_DATA equals the port to 0 ulps and the
Reynolds 1994 polynomial to 6e-8, and CARACal's manual model agrees with
SR2016 to 6.4e-8 on all MeerKAT bands. A setjy-equivalent 1934−638 model arm
(`fluxstd.lsm_source` → `lsm.components` → `core.predict_components`) equals
CASA's MODEL_DATA rows to 0 ulps and differs from the campaigns' stored model
by +0.033 % at 1.4 GHz. PB2017 is transcribed from the paper and opt-in,
pending the casarundata tables (a download for the user to approve). Archive
`results/fs1-flux-standards.json`.

E3 core table writer (big plan; [e3-table-writer.md](e3-table-writer.md)),
2026-10-30 (implemented; measured): rang's core now writes existing casacore
tables as casacore 3.8.1 does (`core/src/aipsio.rs`, `ms_desc.rs`,
`ms_write.rs`, `ffi_ms_write.rs`; Python `rangtoy.core_ms_write`, extension
class `MsWriter`): putcol/putcell for StandardStMan (scalars, Direct and
indirect arrays, variable-length strings) and the tiled managers, keywords,
addcols (the drivers' default binding, new StandardStMan, TiledColumnStMan,
TiledShapeStMan) and the fcntl lock with the sync record. Against
python-casacore: 20 of 24 frozen cases byte-identical, the other 4 identical
except the alignment padding casacore fills from uninitialised memory
(criterion 1 fails as frozen; casacore's own output differs between runs
there); read-back by python-casacore, casacure and `core_ms`, round trip of
41 tables (byte-identical), addcols, locks, serialisation identity and the
342 M-flag whole-array write (0.09–0.14 s, at most +2.3 MB peak RSS,
byte-identical) pass. Bug found and fixed: POSIX drops all of a process's
fcntl locks when any descriptor of `table.lock` closes, which the reader was
doing. Deferred to E4/E5: table creation, IncrementalStMan writes, big-endian
writes, adding rows. python-casacore stays the oracle. Archive
`results/e3-table-writer.json`.

C1 closure-invariant arm (big plan wave 3), 2026-10-30 (implemented;
measured; [c1-closure-arm.md](c1-closure-arm.md)). A Rust kernel
(`core/src/closure.rs`) scores every training sample of LUNO 1934−638 chunk 0
(53 stations) with closure traces (GL(2,C) invariant, Broderick & Pesce 2020;
cyclic quadrangles with re-routing around missing baselines), parallel-hand
closure phases and log closure amplitudes, normalised by noise from
WEIGHT_SPECTRUM; it matches a NumPy reference to 8.6e-8, and closure traces
are invariant under random 2×2 gains to 1e-10. L1's campaign ran unedited
(reproduced on every non-image field) with two added arms. Q1: the closure-TV
map is reproducible (split-half ρ 0.81; a post-hoc noise-only null gives
0.37) and unrelated to the gain-TV map (R² 0.0035), but its structure is the
GNSS band plus an antenna-additive part consistent with an uneven per-antenna
weight scale. Q2: every closure-guided mask is rejected by the frozen
objective; the policy selects L1's 21-cell unguided mask; the 918-cell
closure-outlier arm moves MSE by 1.5e-7; against the CARACal first pass both
arms are null under amendment 1 and under A1's emptied-bin drop (0.99943,
decidable without the matched fallback). Q3: closure outliers coincide with
the first-pass additions (lift 11.5) and the GNSS range (78 %, lift 8.5), not
with A1's emptied bins. The closure chain costs 1.18× the TV chain and 6.2×
the first-pass port. Neither the antenna-factorable (gain TV) nor the
non-factorable (closure) statistic improves on the first pass. Archive
`results/c1-closure-arm.json`. This was the last pre-registered arm before
the verdict (L4).

P9 one CLI (big plan wave 2), 2026-10-30 (implemented; measured;
[p9-cli.md](p9-cli.md)): one CLI, `rang-core STAGE VERB`, for every stage,
comparator and check (`rang-core -h`); the comparators live in
`rangtoy.core_compare` and `examples/compare_core_*.py` are thin wrappers;
every comparator verdict and count is identical through the wrappers and the
CLI on a 20-case suite. Every CLI call writes a `rang.receipt` v1 beside its
output, `STAGE archive` writes a `rang.archive` v1 that the comparators read,
and the CLI caps the BLAS/XLA pools (opt out with `--no-pin-threads`).
`rang-core check` (= `python -m rangtoy.check`, wrapped by
`tools/check-all.sh`) runs the full checks on Linux and native Windows (PASS
on both). Bug found and fixed: the `rang-core` console script exited 1 after
every successful command. The A/B benches take `--python NAME=VENV` instead
of `RANG_CORE_LIB`. L1-M (`campaign-fieldmodel`) and DF1 (`wgridder`) are
registered at the merge; DF1's comparator is the one not yet on the engine.

O-CASA (big plan), 2026-10-30 (implemented; measured;
[o-casa.md](o-casa.md)). A CASA oracle image (`rang-o-casa:6.7.6.14`: Ubuntu
24.04 + KERN-10 WSClean 3.7, AOFlagger 3.5, python-casacore 3.7.1;
casatools/casatasks 6.7.6.14 from PyPI, the manylinux_2_28 wheel because the
2_34 wheel does not import on Noble) runs CARACal's crosscal sequence by hand
on the LUNO 1934−638 four-station slice. CARACal's defaults stop at K: the
automatic reference antenna is empty because all baselines are under 150 m;
solving needs `refant`, `minblperant=3` and no `uvrange` cut (arms D/E/F show
each is necessary). With those, CASA's K·G·B reproduces in hash over two runs
(119 gated hashes; only WSClean `-j 4` pixels differ, at 2e-6; `-j 1` is
bit-identical). Against the core's QuartiCal port: applied gains agree to
0.4 % and 0.33° (median, stored model); held-out test MSE on the parallel
hands, the matched number, is 0.2529 against 0.2294 (×1.10); the total
0.3815 against 0.2760 also contains the cross hands, where K·G·B has no
leakage term by design. Flagging baselines: tfcrop with CARACal's defaults
adds 1.49 % of unflagged cells, rflag 0.14 % (the Tricolour first pass
0.14 %). CARACal's `setjy` is `standard='manual'` from its own Reynolds 1994
table (14.9077 Jy at 1.4 GHz, log10 `spix`), not Stevens-Reynolds 2016; CASA's
SR2016 and PB2010 for 1934−638 are bit-identical and equal that polynomial
to 6e-8 (FS1 erratum: the 3e-6 first reported was O-CASA's float32 row mean). Archive `results/o-casa-crosscal.json`. FS1 and L4
are unblocked; DF0 shares the image base.

L1-M model completeness (big plan wave 3), 2026-10-30 (implemented;
measured; [l1-model-completeness.md](l1-model-completeness.md)). The premise
was wrong: LUNO's stored 1934−638 MODEL_DATA is not a point but a field model.
A least-squares decomposition shows CARACal's lsm compact sources in it at
coefficients near 1, more flux at the lsm's extended sources, and a common
0.077″ offset; A0 sits 2.1″ from the phase centre, not 1.5″. Three models ran
through L1's frozen campaign unedited (scoped model hook; identical split and
Tricolour flags): the stored model; the lsm's A0 alone, predicted by the core;
all 196 lsm components, predicted by the core (apparent flux, no beam, as
CARACal's simulator). Field against point: held-out MSE 0.981 (better; 0.962
under 200 m), Heywood's point-model effect. Field against stored: 1.031
(worse); the stored model fits best and the point model is 4.9 % worse than
it. Gain TV moves by at most 0.7 % (null) and convergence stays at 0.83. The
TV policy's decisions are identical under all three models: the headline is
undecidable as frozen and null under amendment 1, and no TV-guided mask is
selected. Model incompleteness did not cause the nulls. Amendment 2: the
Gaussian PA bound failed as frozen on the whole array (0.028 Jy max) and is
reported, not gated. The cost clause fails (5.1–5.7×) on the parallel
kernels. `rangtoy.lsm` reads Tigger ASCII sky models (the first DF-IO reader).
Archive `results/l1-model-completeness.json`. Corrections: the L1 entry below
and the literature entry's "14.96 Jy point" wording are superseded by this
finding.

DF1 exact gridder (big plan; [df1-wgridder.md](df1-wgridder.md)),
2026-10-30 (implemented; measured): a Rust port of ducc0 0.42's wgridder
(`core/src/wgridder.rs`, `ffi_wgridder.rs`, `core_wgridder.py`), f32 and f64,
both directions, ducc0's 939-row kernel table and a thread-free kernel
choice. All five gated criteria pass as frozen: against a float64 DFT ≤ 10 ε
(worst 4.0e-5 at f32 1e-4, 4.1e-8 at f64 1e-7), against ducc0 ≤ ε
(1e-12–1e-14 in f64 away from the field edge; up to 1.7e-10 in the outermost
pixels of a 0.3 rad field, cause not identified), adjoint to 4.2e-13,
bit-identical at 1–16 threads, kernel table and choices equal to ducc0's.
Item 0 of the DDFacet study is attributed: the core w-stacking image's 19 %
difference from the DFT on the LUNO slice is aliasing of WSClean's
Kaiser–Bessel kernel at padding 1.2 (reproduced to 98.9 % by an aliasing
prediction; 2.1e-5 at padding 2 with kernel 15) plus a pixel mis-map in the
study's search; no defect in `grid.rs`, which reproduces WSClean faithfully,
aliasing included. Through the exact gridder the C/I/K images move by 19–32 %
of the peak at the edge and 0.3–0.6 % inside; task I's response fractions move
by up to 0.036 (no sign changes); the campaigns' held-out decisions do not
depend on the images. Cost: 0.13–0.16 s per four-station image at 16 threads
(w-stacking 0.38–0.41 s, ducc0 0.06 s), but 3.7–4.4× slower than ducc0 per
visibility on one thread, so whole-array use needs the gridding loop
optimised first (DF2). The K replay could not be re-measured because the task
K fetch copy was deleted (re-fetchable).

P7 architecture (big plan wave 2), 2026-10-30 (implemented; measured;
[p7-architecture.md](p7-architecture.md)): the ctypes path and the
import-time cargo build are gone; the root crate's kernels (TV, projector and
survey with the P4 eigensolver, the pointing toy) live in the extension;
`tests/test_core_backends.py` is extension-against-archive (golden archive
recorded under both old backends, identical bytes); every C function has
`catch_unwind` (a panic returns an error code instead of aborting); the GIL is
released around kernels (two predictor calls overlap, 0.92–1.12× one call;
rayon's shared pool still serialises concurrent solver calls); the Tricolour
pack/unpack is parallel (24–32 ms → 4.5–5 ms at 16 threads, flags identical);
`solve_complex` takes bool or uint8 flags without a copy; the static masks
ship as package data. Wheel-only acceptance: a wheel from
`tools/wheel/build.py` installed with cargo absent reproduces every archived
verdict (phase 1/2 validators, section 6, the actions/B/C/D/E/I comparators,
task F, K precondition, trend, signal, the notebooks), 58 arrays and 60 FITS
HDUs byte-equal. Native Windows: 622 passed, 43 skipped with reasons, 0
failed; the libm-based kernels differ from Linux by at most 2.6e-15 relative,
so the golden test is exact on Linux x86_64 and tolerant elsewhere.
`RANG_CORE_LIB` and `rangtoy.build()` no longer exist; `core.library()` and
`backend_name()` remain as compatibility names meaning the extension.

Big plan task A1 (RFI-band audit), 2026-10-30 (implemented; measured;
explanation only; [a1-rfi-audit.md](a1-rfi-audit.md)). Reran the Tricolour
port with per-step stages on L1 and L2, reproducing the archived additions,
splits and invalid-prediction counts exactly. The station-bins the CARACal
first pass empties are exactly the campaigns' lost gain bins: 691 on 1934−638
and 122 on 1830−211. All of them are in static-mask blocks, 682/691 and
122/122 on the GNSS carriers (1176, 1207, 1268, 1279 MHz); none is in
1304–1498 MHz. They are the long-baseline residue (median 5 training samples,
99.6 % already input-flagged) that SumThreshold removes; mild and a mask-free
first pass empty the same blocks, they persist over all dumps, and the
strategy also flags 99 % of the held-out cells there. RFI excision as
intended; supports U2's not filing. Proposal for L4, L1-M and C1:
pre-register dropping the emptied bins' held-out samples, computed after the
split and before any solve (0.02 % of held-out samples), with the
matched-sample rule as fallback. One question for the CARACal and Tricolour
maintainers (in `upstream-notes.md`): the first pass's all-baseline static
mask is discarded by the next replace-semantics step.

Ecosystem survey (big plan; read-only), 2026-10-30
([ecosystem-survey.md](ecosystem-survey.md)): every KERN-10 package (38
source packages, Ubuntu 24.04), the MeerKAT tools outside KERN, CASA 6.7.6
and CARTA 6.0 assessed with licence, release date and a verdict (PORT,
DEPEND, ORACLE, FORMAT, IGNORE). Most of the ecosystem is an ORACLE for rang;
platform rules out DEPEND more than licence (almost nothing besides casacure,
ducc0 and pure-Python packages has Windows wheels; CASA ships cp312/cp313
wheels for Linux x86_64 and macOS arm64 only; CARTA has no Windows build).
CARACal's cross-calibration is CASA (`setjy`, `gaincal`, `bandpass`,
`fluxscale`, `applycal`, `polcal`), not QuartiCal, so a matched CARACal
baseline needs a CASA oracle container (O-CASA, on the KERN-10 base that
ships WSClean 3.7, AOFlagger 3.5, IDG 1.2 and casacore 3.7.1). CASA's PKS
1934−638 flux standards are Stevens-Reynolds 2016 and Perley-Butler 2010, not
Perley-Butler 2017 (FS1 ports them with `setjy` as oracle). Proposed: CASA
caltable and H5parm formats, katdal as an optional `[meerkat]` extra for L3,
AOFlagger as a second SumThreshold oracle, CASA `gaincal` as a second
comparator in the solver protocol, a 22-format table for DF-IO and the oracle
per planned task. KERN packaging lag and metadata issues are listed for the
user (KERN is the user's own).

QuartiCal issue 452 fix verified, 2026-10-30
(`upstream-issues/quartical-qp-jhj-weights.md`): PR ratt-ru/QuartiCal#456
(merged into v0.2.8-dev as d54c46b) gives the ANTENNA2 side the transposed
weights in the shared solver loop and fixes complex, leakage, rotation,
rotation_measure and crosshand_phase at once, with a test over all 14 terms.
On scan 9 with a four-fold YX weight asymmetry the old code converged 67 % of
intervals and flagged 81.5 % of antenna-intervals; the fixed code converges
98.8 % and flags 39.0 %, as with unit weights. Rang's `qp_weights=transposed`
matches the fixed QuartiCal to 1.5e-14 on three weightings, so the opt-in is
the upstream fix; `archived` matches 0.2.7 to 2e-14. Native MeerKAT weights
carry about 15 % XY/YX asymmetry, so once 0.2.8 is the reference,
`transposed` is the compatible default and the archived comparisons need
re-validation (the dev branch also restructures the solver loop and
references the complex term by default). Result posted on #452.

E2 casacure evaluation (big plan), 2026-10-30
([casacure-evaluation.md](casacure-evaluation.md)): casacure 3.8.35 (Tim
Molteno's pure-Rust casacore tables, LGPL-3.0-or-later) reads all 173 task E
oracle columns column-exactly through Python and through the Rust crate (Rust
1.93), on Linux and natively on Windows, little- and big-endian; in-place
writes and default-manager MS creation read back exactly in python-casacore.
But it accepts a TiledColumnStMan request for a variable-shape column and
writes an MS casacore cannot open (W1(b) failed as frozen), relabels epoch
conversions without converting, crashes with SIGBUS on a file truncated under
its mapping, ships no licence file, and has one maintainer at 36 releases in
33 days. Verdict as frozen: (c), do not adopt; extend task E's reader into
rang's own writer (E3, E4, E5) and keep casacure as an optional pinned second
oracle that also runs on Windows and macOS. `core_ms` passed its first
big-endian test on the way. The eleven casacure defects are listed in
`non-ratt-observations.md` (casacure is outside the reporting decision).

Big plan task U3 (saopicc upstream), 2026-10-30 (implemented; measured;
[upstream-saopicc.md](upstream-saopicc.md)): filed saopicc/killMS#23, #25,
#27 and saopicc/DDFacet#73, #75, #77; opened killMS#24, #26 and DDFacet#74,
#76 (no GitHub CI on either repository). Latest releases equal `master` in
both. The DDFacet Hogbom failure seen on the LUNO slice reproduces on a
synthetic point source in two minutes and depends on the facet count, not the
compact array (one facet converges; 3×3 diverges to inf even with 2.2 km
baselines): DF0/DF5 oracles should use one facet or reject `nan` models.
killMS still needs DDFacet < 1.0, and DDFacet 0.9.1 does not install on GCC 15
(astlib), so the killMS oracle needs an older toolchain.

L5 solver science (big plan wave 3), 2026-10-30 (implemented; measured; no
default changes; [l5-solver-science.md](l5-solver-science.md)): the core
solver gains run-time options through `RANG_SOLVE_OPTIONS` (default = archived
QuartiCal 0.2.7, bit-identical: task F checks at 1/4/8 threads, phase 2
validator, K precondition, K's and L1's `original` gains hashes): the issue 452
qp weight fix, gauge-invariant product and loss stop tests, safeguarded
Anderson acceleration of the two-step Gauss–Newton map, per-interval freeze,
and a per-iteration trace (`RANG_SOLVE_TRACE`). Measured on the fixture, the
four-station slice, 32 stations and the whole array (56 stations): the weight
fix changes no held-out error (≤ 8e-9 relative); no stop criterion beats the
50 cap on all sets (the frozen selection, cap 8, fails the fixture by 3.9e-3);
Anderson m = 3 reaches the 0.99 criterion at 27 / 21 / 65 / 65 iterations
where plain needs 55 / 91 / > 300 / > 300, with the same held-out error and
fixed point where the plain run converged, and at the cap of 50 lifts the
array's converged fraction from 0.833 to 0.982 at equal cost. As frozen no
default changes; `qp_weights=transposed,anderson=3` is the documented opt-in;
a future default protocol would pair it with a cap of 70 against a converged
plain reference. Archive `results/l5-solver-science.json`.

P5 memory (big plan wave 2), 2026-10-30 (implemented; measured;
[p5-memory.md](p5-memory.md)): one copy of the cube. Tiles decode straight
into the final arrays (strided Rust decode, mmap), the split runs in row
blocks with one lexsort, the base solves' outlier scores come from the fused
pass over baseline groups and are kept sparse, additions are stored as
indices, and gain correction plus the Stokes I reader run in Rust
(`core/src/correct.rs`, extension bindings `blosc_decode_span_rows_strided`
and `correct_stokes_i`) into reused buffers. Every identity gate passes: K's
precondition masks and the four-station replay identical (images
bit-identical); the whole-array run equals the unmodified driver on all
1,820 non-timing fields (three dirty images within 3.1e-11 of the peak) and
L1's archive on every non-image field. Whole-array peak 12,997 → 10,406 MiB
(159 → 128 B per cell, −20 %; L1's "12.46 GB" was MiB); the pre-registered
≤ 115 B per cell is missed, the gridder's per-group copies and the Tricolour
stage planes now set the peak (for P2/P3/P7). An image takes 13–15 s instead
of 5–10 min on the parallel kernels.

L2 PKS 1830−211 campaign (big plan wave 3), 2026-10-30 (implemented;
measured; null). The gain-TV-guided flagging campaign ran on the whole array
for LUNO's gain calibrator PKS 1830−211 (MAIN_2, the whole 80 s scan: 56
stations, 1,540 baselines, 126 M cells) under two model arms fixed in the
protocol: the stored MODEL_DATA with its 1e-3 cross-hand terms, and a scalar
point at the phase centre predicted by the core with a power law fitted to
the short-baseline data (α = +0.22). 877 MB of DATA and UVW were fetched
whole in 137 s; the L2 driver (`rangtoy.core_campaign_1830`) replays K on
four stations and reproduces the archived survey. Under the scalar model the
four-station survey is fully identified except 15 tree bins; under the
stored model it is status 6 everywhere. Criteria 4 and 6 fail as frozen (the
Tricolour arms leave held-out samples unpredictable; the stored model
converges on 5 % of intervals, the scalar on 94 %). The pre-registered
matched headline is null under both models (TV policy against first pass
0.99977 and 0.99969); every TV-guided mask is rejected; the cost is not
comparable on the parallel kernels as measured on a contended host (TV chain
4.6–5.9× the first pass). Verdict null. Archive
`results/luno-1830-campaign.json` ([luno-1830-campaign.md](luno-1830-campaign.md)).
What L4 can now say: gain-TV-guided flagging is null on both LUNO
calibrators at four-station and whole-array scale under a matched
state-of-the-art comparator and pre-registered rules; what could still change
the answer is native flags and weights (L3), a converged solver (L5) and the
field model (L1-M).

DDFacet/killMS feasibility (big plan; 2026-10-30; study, no core code;
[ddfacet-feasibility.md](ddfacet-feasibility.md)). DDFacet 1.0.0.0 (about
106 k lines of Python, 8.5 k C/C++, GPL-2-or-later headers) does w-projection
per facet with Voronoi tessels, BDA and per-facet 2×2 Jones; most of its
code is deconvolution heuristics. killMS 3.3.0's CohJones is LM over a
per-antenna, all-direction Jacobian. Recommendation: no faithful port; keep
DDFacet and killMS as pinned external oracles. Instead DF1, an exact
gridder/degridder porting the ducc0 wgridder algorithm (GPL-2-or-later),
facet-free, validated against the ducc0 wheel at one thread and a DFT (ducc0
matches a DFT to 1.2e-5 of peak at epsilon 1e-4 and 8.7e-8 at 1e-7 on the
LUNO slice, in 0.04–0.27 s); then facets as shifted sub-images with per-facet
Jones, a scalar CohJones and Hogbom/multiscale, against DDFacet/killMS on a
simulated MeerKAT target field (DF3–DF5, after B1 says what it needs); DF6
facet-IDG on `wgpu` after X2 with WSClean 3.7 as oracle. B1 keeps
per-component beams in the DFT predictor: away from facet nodes a
facet-constant beam errs by 13–50× a 30″ pointing signal at 9–100 facets.
Found on the host: killMS 3.3.0 does not build on GCC 15 without a flag and
does not run on DDFacet 1.0.0.0; DDFacet HMP on the 37 MB slice peaks at
8.9 GB; the core w-stacking image differs from a DFT on the slice by 19 % of
peak (1.6 % on the PSF), unattributed, to be resolved in DF1 (item 0).

Cross-platform (big plan X1), 2026-10-30 (implemented; measured on native
Windows and Linux; CI not yet run; [x1-crossplatform.md](x1-crossplatform.md)).
The core, the root crate and the PyO3 extension build natively on Windows
with Rust 1.93.1 (MSVC) and maturin with no source change, and the extension
exports the C ABI. The backend tests pass on Windows (10 passed, 1 skipped).
Of the full suite, 529 tests pass on Windows, 17 fail and 3 modules do not
collect, all from POSIX assumptions (`resource`, `st_blocks`, symlinks, path
separators, console encoding), listed for P7/P9/P12. The task D Tricolour
comparator ran natively on Windows on the archived inputs: criteria 1–4
exact, all 56 arrays byte-identical to Linux; criterion 5 fails as frozen
only because the receipt hashes `str()` paths with backslashes. `wheels.yml`
now builds and tests manylinux x86_64 and aarch64, macOS arm64 and x86_64,
and win_amd64 wheels with cargo absent, and publishes to PyPI by trusted
publishing on `v*` tags (the project name at the tag is still `rangtoy`
until P12). `tools/wheel/build.py` and `test.py` build and test the native
wheel without docker; `.cargo/config.toml`'s v3 target is scoped to x86_64.

Big plan task U2 (upstream fixes), 2026-10-30 (implemented; measured): filed
stimela#619, tricolour#113 and QuartiCal#455; opened stimela#620,
tricolour#112 (merged), tricolour#114 and caracal#1708 (approved). No PRs for
QuartiCal #452/#453 and Tricolour #110 by maintainer direction. Rows-as-lanes
in Tricolour 0.5.0-dev: 1.3–2.1× with bit-identical flags. QuartiCal 0.2.7
defaults on scan 9: 46–54 % of intervals converged at the 25-iteration cap,
chi-squared settled by 10–15; the slow tail is not gauge drift (a
gauge-invariant stop rule would not stop earlier). The CARACal first-pass
station-bin loss reproduces on scan 9 but is whole-channel excision, not
filed. Report: `research/upstream-prs.md`.

D2 notebook tooling (big plan, documentation track), 2026-10-30
(implemented; measured; no science claim). `rangtoy.notebook` gives plain
plot and table functions over the core wrappers (`data`, `survey`, `flags`,
`gains`, `image`, `experiment`) and an ipywidgets steering layer (`steer`);
five tutorial notebooks in `notebooks/` teach the data and the
identifiability rank first, Tricolour step by step, gains/gauge/TV, imaging,
and the flagging experiment with its null results read from the archives.
The fixture loader reproduces the archived split and baseline solve to ten
figures without casacore; the LUNO survey reproduces 389/43/592 and the
decision replay reproduces task K's calls exactly. On a host at load 46–61,
notebooks 01–04 ran in 9–37 s each, 05 in 66 s with its LUNO replay, and all
five on the fixture alone in 48 s together; the new tests take 78 s. Wish
list (progress hook in `fetch_slice`, POSIX-only `resource` import in
`core_campaign`, TV and normals kernels outside the wheel, amendment 1 calls
missing from the L1 archive) in [d2-notebook.md](d2-notebook.md); the
`[notebook]` extra holds the dependencies.

P10 test-suite speed (big plan wave 2), 2026-10-30 ([p10-tests.md](p10-tests.md)):
a `tests/conftest.py` caps OpenBLAS/OMP/MKL at one thread and XLA's CPU
backend at one intra-op thread, and builds the pointing references once per
session. The caps are defaults, and the caller's environment wins.
`test_blocked` computes its dense audit once, and one validation check moved
to the thinned rows. The 555 test ids are unchanged and all pass. In the
matched A/B pair under load 26, full pytest went from 672 to 223 s wall and
from 6,031 to 188 CPU-s: `test_pointing` 584 → 146 s, `test_blocked` 40 →
19 s, `test_beams` unchanged (31 s). On an idle host the cap is estimated to
cost about 1.5–2.5× wall; `OPENBLAS_NUM_THREADS` overrides it.
`tools/check-all.sh` now takes a host-wide lock so suites queue instead of
overlapping. The day's load averages of 55–98 came from up to seven
concurrent suites whose BLAS pools busy-waited on each other.

Literature scan (big plan, read-only), 2026-10-30
([literature-2024-2026.md](literature-2024-2026.md)). arXiv, release APIs and
changelogs were surveyed for 2023–2026-10 across calibration, RFI, imaging,
beams and pointing, mathematics and software; every source was accessed
2026-10-30, most papers at abstract level. The strongest finding for the
active experiment is calibrator model completeness: Heywood et al. (2020)
show a point model of PKS 1934−638 imparts 0.2–0.5 % structured amplitude
errors at MeerKAT, and CARACal ships a 196-component 1934 field model; K and
L1 solved against the stored model (later shown by L1-M to be a field model
itself), so part of the gain structure that TV
measures may be model error (task L1-M). Other recommendations: safeguarded
Anderson acceleration after the #452 fix (theory only, no radio precedent);
a closure-invariant (GL(2,C) gauge-free) comparator arm (C1), which isolates
exactly the non-antenna-factorable part gain TV cannot see; the SARAO
holography cubes and the SARAO/SKA pointing-offset fit as B1's reference
beam and baseline. Dropped: diffusion priors, robust PCA RFI separation,
ephemeris flagging as a method, an IDG port, a DDFacet rewrite (DDFacet is
maintained, v1.0.0.0 2026-06-23; WSClean 3.7 ships w-towers and facet-IDG).

P6 frozen Python hot spots (big plan wave 2), 2026-10-30 (implemented;
measured; [p6-python-hotspots.md](p6-python-hotspots.md)): the trend track's
candidate generation is ported to `core_trend.generate_candidates` (geometry
built once per case by prefix sums and one `np.nonzero` per row group, scores
vectorised with a bitwise-checked emulation of NumPy's pairwise sum), and the
signal track's `train_signal_guard`, `inverse_tangent` and
`corrected_intensity` are ported into `core_signal.py` with `cond`/`inv` once
per run of identical gain matrices. Frozen modules untouched. Trend results
and checkpoints byte-equal, signal results equal apart from wall times, both
comparators pass with identical counts through the switched drivers (the
`rang-core trend` and `signal` commands now use the ports). Trend 3.1× faster
(34.5 → 11.2 s minimum, claimed); signal `cond`/`inv` CPU 13.1 → 0.8 s per run
but no wall gain measurable in the frozen A/B at falling load (not claimed;
most signal time is now the survey eigensolver, P4). S1's premise that most
trend tiles are rejected by count was wrong: 60 % are admissible.

P4 survey eigensolver (big plan wave 2), 2026-10-30 (implemented; measured;
[p4-eigen.md](p4-eigen.md)): the anchored-response kernel's two 32 × 32
eigenproblems per call now use Householder tridiagonalisation + implicit QL
(`linalg::eigen_ql`) instead of classical Jacobi; Jacobi stays for the
pointing toy and the A/B. All 13,989 `anchored_response` calls of the
section 6 / phase 2 / LUNO surveys and the signal and prospective stages
replay with identical statuses and ranks; every archive comparator passes as
before (389 / 43 / 592, LUNO solved and support surveys leaf for leaf, signal
and prospective comparators); the smallest margin to the 1e-10 rank cutoff
over all bins is 7.3e7 above and 1.6e5 below. Under load 18–32: survey block
0.84 → 0.34 s, 1.7 → 0.35 ms per call, section 6 pass excluding decode
2.0 → 1.3 s (its `8_cost` criterion passes again at load 18–22), signal stage
67 → 50 s (minimum), 79 → 53 s (median).

L1 whole-array LUNO campaign (big plan wave 1), 2026-10-30 (implemented;
measured; null). The gain-TV-guided flagging campaign ran on the whole of
LUNO 1934−638 row chunk 0 on the core: 53 stations, 1,378 baselines, 342 M
cells, local whole tiles, no fetch. The array driver
(`rangtoy.core_campaign_array`) reproduces K's run bit for bit on four
stations and caps memory at 12.5 GB by row-block reimplementation (K's driver
would have needed about 88 GB). The run took 2 h 08 min on a shared host
before the P1–P3 kernels were merged. Frozen criteria 2, 4 and 6 fail as
frozen: the derived FLAG_ROW covers 571 input-flagged rows, convergence is
0.83 at the 50-iteration cap (0.98 on four stations), and the headline is
undecidable because the Tricolour first pass flags every training sample of
some station-bins, so the comparator's held-out loss is unavailable.
Amendment 1 (committed before the run) adds matched-sample calls, which are
null on every pair (TV policy against first pass: MSE ratio 0.99943, residual
RMS 0.9954); the policy selects a 21-cell unguided mask and rejects every
TV-guided mask; cost comparable (1.85). Diagnosed post hoc: the 1934−638
MODEL_DATA is a 14.96 Jy source about 1.5″ off the phase centre (L1-M: a field
model with A0 at 2.1″). The result is
null at both four-station and array scale. Archive
`results/luno-array-campaign.json` ([luno-array-campaign.md](luno-array-campaign.md)).
Next: L2 (1830−211) and L3 (native flags) for the L4 verdict; the array
solve's convergence goes to the wave 3 solver protocol.

P2 gridder (big plan wave 2), 2026-10-30 (implemented; measured): the
w-stacking gridder buckets samples by w-layer once, grids dirty image and PSF
in one pass, runs the layers in parallel with rayon and an ordered sum, and
uses `rustfft` at WSClean's exact padded size. One four-station image:
5.8 s → 0.80 s on one thread, 0.53–0.61 s at 4–16 threads on a loaded host;
task C, I and K comparators pass with unchanged margins (dirty 6.11e-7, PSF
4.17e-7 of peak against WSClean); images differ from the old FFT's by 2e-15
of the peak and are identical at any thread count. Whole array: about 3–6 s
per image (estimate). Consequence: archived image SHA256s (task K's
`results/core-k-luno-campaign.json`, S1's profile equality) no longer match
a rerun by design; checkers compare pixels or metrics within task A's
tolerances. `rustfft` picks AVX/SSE/scalar at run time, so images may differ
at 1e-15 between hosts and between the local v3 build and the wheel
([p2-gridder.md](p2-gridder.md)).

P1 solver and fused pass (big plan wave 2), 2026-10-30 (implemented;
measured): the ported QuartiCal solver runs each (time bin × frequency bin)
interval on rayon in epochs of 8 iterations with a serial,
iteration-by-iteration replay of the global stop test, and the fused pass
sweeps row blocks in parallel with a serial fold of the order-dependent sums
and per-interval normals. Every product is bit-identical to the single-thread
code at 1, 2, 4, 8 and 16 threads (task F checks, phase 1 and 2 validators, K
precondition, a 45-process sweep including early-stop settings); LUNO solve
0.252 → 0.047 s (5.4×) and fused pass 0.027 → 0.007 s at 8 threads under load
14–26; the fixture's 5.5× is measured but below the frozen claim rule at that
load. Thread count: `RAYON_NUM_THREADS` (default all logical CPUs, so
concurrent campaign processes should set it). QuartiCal's swapped qp weights
(issue 452) are reproduced unchanged; fixing them is a science protocol
([p1-solver.md](p1-solver.md)).

P3 SumThreshold (big plan wave 2), 2026-10-30 (implemented; measured): the
Tricolour port runs in parallel over baselines (rayon, `RAYON_NUM_THREADS`)
with per-worker scratch and a vectorised, lane-grouped box filter and
frequency-axis SumThreshold; flags bit-identical (task D comparator 5/5 at 1
and 16 threads, K additions hashes at 1–16 threads, every per-step window
identical to the unmodified port). K first-pass 1.65 → 0.55 s on one thread
and 0.14–0.16 s on 8–16; D controls 9–12×. Whole-array chunk 0 first pass
estimated about 7 min → 25–50 s. The serial packing in `ffi_flag.rs` is now
13–20 % of a 16-thread call (for P7). Archive `results/p3-sumthreshold.json`
([p3-sumthreshold.md](p3-sumthreshold.md)).

P8 history (big plan wave 2), 2026-10-30 (`p8-history.md`): the 23 frozen
`tv-flagging*` recipes, `tools/flagging/` (8 Dockerfiles, wrappers, fetch
scripts, preflight, locks) and the six recipe-only modules
`flagging_{concurrent,parallel,provenance,public,transfer,uncertainty}` with
their tests moved to `history/` by `git mv`, byte-identical (70 files, 6,258
lines; 3 wrapper and recipe test functions cut there too). Live tree 267 → 197
files and 59,145 → 52,772 lines; recipes 30 → 7; pytest 739 → 555 tests.
check-all passes; S1's live-chain suite reproduces every archived verdict and
the K replay hash for hash, except section 6's wall-time cost criterion under
shared load (2.6 s and 7.9 s against a 2 s limit, load 14–20; a post-hoc A/B
shows the pre-move tree failing it the same way at load 26–46). Re-running a
frozen campaign is done from `43dc3c7` or its recorded commit with the pinned
images (`history/README.md`). The pinned `rang-flagging*:local` images are no
longer used by any live chain and may be pruned (user item).

Wheel (big plan W1), 2026-10-30 (implemented; measured locally; CI run
started by the merge push). `rangtoy-0.1.0-cp310-abi3-manylinux_2_28_x86_64.whl`
(821 kB, built in the pinned manylinux_2_28 container with Rust 1.93.1 and
maturin 1.16.0, auditwheel-clean, nothing grafted) installs from public PyPI
on clean CPython 3.10–3.14 and runs the extension backend with no cargo;
backend tests pass and task J's archive run reproduces through the wheel
(task I included) with arrays and images identical on every version and JSON
leaves identical on NumPy 2.5 (last-bit differences on 3.10/3.11 follow their
older NumPy). aarch64 cross-builds by zig but was not run. NumPy is now a
declared dependency (a bare install was broken). The wheel does not carry the
root crate's TV kernel, the Tricolour static masks or the archive drivers'
checkout paths. Wheels are built with the baseline ISA (`RUSTFLAGS` overrides
the local `x86-64-v3` config). Publication is a user item ([wheel.md](wheel.md));
open: the distribution name (`rangtoy` or `rang`) before the first upload.

Simplification review S1 (big plan wave 1), 2026-10-30 (measured; no code
changed). Every archived chain was re-run and reproduces its archived outcome
(29 timed steps plus the phase 1 and 3c-a validators, the fetch checker and
the backends comparator; the offline task K replay matches the archived gains,
dirty images and PSFs hash for hash). The core runs one thread per stage:
87 % of the K chain's samples are in Rust, under 1 % in Python glue, and 15 of
16 hardware threads stay idle (the host is 8 physical cores with SMT). The six
K images are 67 % of the non-fetch time and 83 % of each image is the
hand-written Bluestein FFT. Peak memory is about 0.87 kB per visibility cell
against 84 B of inputs, so the whole-array chunk (100.9 M cells) would need
about 88 GB as the K code is written. Thin LTO plus `x86-64-v3` code
generation cut instructions by 22 % with bit-identical results (applied on
main as P0). The 50-iteration solver cap is not convergence: held-out MSE
settles within 2e-5 by 12 iterations, but gain products move 1.3e-3 between
50 and 91 iterations, so changing the cap is a science protocol. The test
suite's time is 98 % in three pointing modules (JAX/XLA and dense algebra,
145 threads). Wave 2 tasks P0–P11 are cut in `simplification-review.md`
section 4 with owner files and archives; P1, P2, P3 and P8 start first.

Task U1 (big plan), 2026-10-30 (done). Every RATT observation in
`upstream-notes.md` was checked against its latest release (QuartiCal 0.2.7 and
v0.2.8-dev, Tricolour 0.2.1 and 0.5.0-dev, dask-ms 0.2.32). Four issues were
filed: QuartiCal #452 (the qp normal equations use swapped XY/YX weights,
verified against QuartiCal's own kernel), QuartiCal #453 (HISTORY row),
Tricolour #110 (non-TTY ProgressBar adds up to 300 s per run, the source of the
archived 302 s runs) and Tricolour #111 (integer `spike_width_time` causes a
second compilation). Nine observations were closed with reasons in
`research/upstream-issues/`. The Tricolour licence question is settled:
0.5.0-dev declares BSD-3-Clause. Non-RATT items are in
`research/non-ratt-observations.md`. Implication for the core: the phase 2
solver port reproduces QuartiCal bit-for-bit and therefore carries the #452
weight swap; wave 2's solver task should fix it as a validated deviation
(same fixed point, fewer iterations expected when w_XY ≠ w_YX).

Big plan started, 2026-10-30 (user decisions in chat; [big-plan.md](big-plan.md)).
Four lines of work run in parallel from here: a simplification and
optimisation review of the whole chain (then its implementation), the
science continued to a settled verdict (whole-array LUNO campaign first),
upstream issues filed on RATT software only, and a distributable Linux
wheel. The coordinator merges waves without waiting for the user.

Licence decision, 2026-10-30 (user, in chat): the LUNO data may be used and
upstream software may be rewritten in the core. The observer's permission
(Ben Hugo, 2026-10-29 15:36 SAST) is the basis and publications cite the
SARAO data usage acknowledgement. Earlier "provisional pending licence"
labels on LUNO results are history; their other caveats (processed weights,
unlogged model origin, four stations) stand. Raw visibilities are still
never committed or redistributed.

Core task K (wave 2), 2026-10-30 (implemented; measured; provisional). The
first real-data campaign on the LUNO PKS 1934−638 four-station slice ran
entirely on the core (`rangtoy.core_campaign`): range fetch (752.8 MB, 74.2 s,
every byte hash-equal to task G's archive), Rust decode (0.36 s), the frozen
seed-7 split, six arms solved with the core's QuartiCal port (0.32 s each), the
Tricolour first-pass and mild strategies ported in task D (1.55 s and 0.89 s),
the frozen TV policy loop (1.7 s) and corrected-data Briggs dirty images
(3.9 s each); 110 s and 461 MB in all, criteria 1–7 pass as frozen after the
section 6 precondition reproduced the archives. Outcome: a null result by the
pre-registered rule on every pair. The TV policy selects no flag (each of the
six candidates raises the fixed-support TV and the validation MSE); the
first-pass strategy adds 128 of 94,047 training cells to a slice already
70.10 % flagged and moves the held-out test MSE by 6e-5 relative and the
point-source residual RMS by 4e-5; dirty peak 14.925 Jy/beam against the
14.940 model in every arm; cost comparable (TV chain 2.00 s against 1.54 s,
ratio 1.30). Labelled post-hoc: one checker-only path fix after the first
check call failed; the run is untouched. Caveats: SARAO's written licence
confirmation is pending (observer permission in chat 2026-10-29 15:36 SAST;
no visibilities redistributed); WEIGHT_SPECTRUM is a QuartiCal product and the
1934−638 model origin is unlogged, so every χ² and MSE is conditional; four
stations make the dirty image sidelobe-dominated (the frozen 9×9 PSF box sits
inside the main lobe); PKS 1830−211 was not run. Archive
`results/core-k-luno-campaign.json` (`core-k-luno-campaign.md`). Next: a
whole-array run and the native-flag run once the observer's data arrive;
1830−211 needs a model decision.

Core task J (wave 2), 2026-10-29 (implemented; measured; criteria 1–7 pass
as frozen). The core is packaged as the PyO3 extension `rangtoy._core`
through maturin (`core/py`, pyo3 0.30.1 and numpy 0.30.0, abi3-py310; the
`pyproject.toml` backend is now maturin): each of 17 functions and the
`MsTable` class is a second door into the same C function with NumPy arrays
borrowed in place, `core/src` unchanged. Every wrapper uses the extension
when importable and ctypes otherwise (`RANG_CORE_BACKEND`, `RANG_CORE_LIB`).
Through the extension the phase 2, section 6, actions, B, C, D, E and I
comparators reproduce their archives with every number equal to the ctypes
precondition; `examples/compare_core_backends.py` finds 94 files, 4,544 JSON
leaves, 60 npz arrays and 60 FITS HDUs identical. Timings: first kernel call
under 1 ms against 28–32 ms through ctypes, per-call cost otherwise equal;
the extension buys packaging and a typed boundary, not speed. Found and
fixed: `tools/check-all.sh` never failed on a failing pytest (now it does;
the Rust test steps were fixed the same way at the merge). Not done: a
distributable manylinux wheel and the container update. Archive receipts
under `outputs/core-j-20261029-*` (`core-j-packaging.md`). Next: task K once
the licence answer is in.

Core task I (wave 2), 2026-10-29 (implemented; measured). The imaging track
replays on the core (`rangtoy.core_imaging`, `rang-core imaging`,
`recipes/core-imaging.yaml`): the fifteen archived jobs are imaged from the
checkpoints with `core_ms`, `core_weights` and `core_grid` and the unedited
`flagging_imaging` algebra, no WSClean, container or python-casacore. Against
`results/gain-tv-next-imaging.json` and the host reproduction: weight sums
1.4e-15, dirty 6.1e-7 and PSF 4.2e-7 of peak, template fluxes 1.4e-7, response
fractions 1.3e-7 (82 % of task A's 1.6e-7), closures 7.4e-9 Jy/beam, 532 exact
fields; 62 s for the family (about 2.5× single-threaded WSClean inversion).
Criterion 8 failed as frozen on its git clause because the operator edited
tracked files during the run (not the driver); the first Stimela run failed as
frozen because Stimela 2.1.4 raises "There is no current event loop" on Python
3.14, and passes after a labelled environment step on a 3.13 venv. Archive
`results/core-i-imaging-replay.json` (`core-i-imaging-replay.md`). Next: task
J (PyO3/maturin packaging), then task K once the licence answer is in.

Wave 1 merged, 2026-10-29 (implemented; measured). The eight parallel
sessions of `core-parallel-plan.md` ran in WSL worktrees on branches
`core/<slug>` from `9e12326` and were merged onto main one at a time in the
order G, H, A, B, C, D, E, F (F last because it edits existing kernels), with
each task's "For the coordinator" section applied in the merge commit. Every
branch passed `tools/check-all.sh` once on its own (51–53 min each while eight
suites shared the 16 cores). Next: wave 2 (I imaging replay on the core, J
PyO3/maturin packaging, K the LUNO campaign, which needs the licence answer).

Core task A, 2026-10-29 (implemented; measured): WSClean approximation
sensitivity, 19 variants × 15 archived imaging jobs (kernel 5–9, oversampling
511–2047, w-layers 1–256) in 552 s; all gated criteria pass. Proposed phase 4
tolerances at one tenth of the smallest adjacent movement: dirty-image L∞
8.8e-6 of peak, PSF L∞ 2.8e-6, template flux 4.7e-6 relative, response
fraction 1.6e-7 absolute, weight sums 1e-9 (`core-a-imaging-sensitivity.md`).

Core task B, 2026-10-29 (implemented; measured): `core/src/weights.rs`
(`rangtoy.core_weights`) ports WSClean 3.6-1 Briggs, uniform and natural
imaging weights and Stokes I formation, bit-identical to WSClean's
`-store-imaging-weights` on all 19 oracle runs (`core-b-weighting.md`).

Core task C, 2026-10-29 (implemented; measured): `core/src/grid.rs`
(`rangtoy.core_grid`) ports the w-stacking gridder (Kaiser–Bessel 7, 1023×,
w-layers, PSF, normalisation, FITS orientation). The frozen run failed because
the reading missed WSClean's default `-padding 1.2`; after the labelled
post-hoc fix the core matches WSClean's dirty images and PSFs on all fifteen
jobs to at most 6.1e-7 of the peak, inside task A's 8.8e-6
(`core-c-gridder.md`).

Core task D, 2026-10-29 (implemented; measured): Tricolour 0.2.1 treated as
BSD-3-Clause (LICENSE file; the `GPLv2` metadata string is unaccompanied),
Crystalball GPL-2.0-only and not ported. `core/src/sumthreshold.rs`
(`rangtoy.core_flag`) reproduces the four archived CARACAL controls flag for
flag (run `-02`, after one post-hoc fix of the `flag_nans_zeros`
accumulation); 4.2 s CPU per first-pass strategy against 1.2 s warm Numba plus
74 s compilation. Archive `results/core-d-tricolour.json`
(`core-d-tricolour.md`). The licence reading awaits confirmation by SARAO.

Core task E, 2026-10-29 (implemented; measured): `core/src/ms.rs`
(`rangtoy.core_ms`) reads casacore tables stored with StandardStMan and
TiledStMan column-exactly against python-casacore on all 173 oracle columns of
the fixture and LUNO Measurement Sets; python-casacore is still needed to
write tables and for the oracle (`core-e-ms-reader.md`).

Core task F, 2026-10-29 (implemented; measured): solver and blosc decoder
faster with bit-identical results against the phase 2 and section 6 oracles
(solver 1.5× fewer instructions and 1.7–1.8× faster at quiet load, decoder
4.6× fewer instructions and 3.0–3.3× faster); the rank survey is a null
result because its cost is the root crate's Jacobi eigensolver, not the core
(`core-f-performance.md`).

Core task G, 2026-10-29 (implemented; measured): the LUNO four-station slice
fetched with HTTP range requests (`rangtoy.core_fetch`), 751.8 MB in 74.5 s
against 4.87 GB in about 679 s whole-tile, all bytes hash-equal to the
archive (`core-g-http-fetch.md`).

Core task H, 2026-10-29 (implemented; measured): five core-native Stimela
recipes (`recipes/core-*.yaml`) and `rang-core` (`python -m rangtoy.core_cli`)
reproduce the phase 3 archives through Stimela and directly, in a venv without
QuartiCal; two criteria failed as frozen (wall-time digests, docstring text)
and pass under labelled post-hoc rules (`core-h-recipes.md`).

Core section 6 prototype, 2026-10-29 (implemented; measured). Run as frozen
from the LUNO zarr tiles with no MS (`examples/prototype_section6.py`, checker
`examples/check_section6.py`): a Rust blosc decoder (`core/src/blosc.rs`,
`rangtoy.core_zarr`) matches numcodecs on all 68 chunks and reads only the
needed blocks (512 of 3136). Run `-01` failed criterion 8 (2.86 s excluding
decode, 299 MB); after implementation fixes with unchanged criteria, run `-02`
passes all eleven (1.67 s, 140 MB; gains equal QuartiCal to 3.3e-16; survey
389/43/592). Archive `results/core-section6.json`. Next: phase 4.

Core phase 3c-b, 2026-10-29 (implemented; measured: all gated criteria pass
as frozen). The signal track runs on the Rust core (`rangtoy.core_signal`):
9 solves in 34.5 s, prediction by the core predictor, injection and complete
sky in memory. 261 exact fields equal, floats within 1.7e-11 against
`results/gain-tv-next-signal.json` and the host reproduction. Archive
`results/core-phase3c-b.json`. Phase 3 gate covered: core drivers for
injections, actions, trend, prospective and signal reproduce their archives,
with qualifications (trend only under post-hoc 3b; injections and actions
needed post-hoc comparator steps). The frozen recipes still call QuartiCal.
Lesson: five of eight frozen runs needed a post-hoc step, three of which a
comparator run on archive versus host reproduction would have exposed; future
protocols require that precondition. Next: the section 6 prototype as frozen
(zarr ingest, no MS), then phase 4.

Core phase 3c-a, 2026-10-29 (implemented; measured). `core/src/predict.rs`
ports the WSClean-format component predictor of codex-africanus 0.4.4 (BSD
notice kept). Against a once-only africanus oracle
(`outputs/core-phase3c-oracle-20261029-01`) it is bit-identical on the response
pair, the 5153-component SARAO catalogue and a 64-component stress set. The
frozen run `-01` failed one criterion through a validator error (wrong source
list for the NumPy templates); the corrected rerun `-02` passes all. Archive
`results/core-phase3c-a.json`. Next: 3c-b, the signal track (freeze a UVW
export of the prepared cases first).

Core phase 3 trend chain test, 2026-10-29 (implemented; measured). Seven
core-solved baselines, written as a mirror of the concurrent suite
(`examples/build_core_trend_mirror.py`), are consumed by the unedited trend
module (hash equal to the archive). 875 exact fields match; criterion 3 failed
as frozen on the reference-antenna slopes (rounding zeros, at most 6e-19 rad/s);
post-hoc criterion 3b (scaled by each axis's largest slope) passes at 8.4e-14.
Archive `results/core-phase3-trend.json`. Phase 3: injections, prospective,
actions and trend done; signal track remains (needs the Rust predictor).

Core phase 3 actions stage, 2026-10-29 (implemented; measured). The actions
stage runs on the Rust core (`rangtoy.core_actions`) in 9.2 s with 17 solves;
it passes as frozen against `results/gain-tv-actions.json` (floats 6.6e-15,
differences 1.8e-11). Against the host reproduction the frozen comparator
flagged 14 float metadata scores as exact; a labelled post-hoc rule passes.
Archive `results/core-phase3-actions.json`. Phase 3 overall: in progress
(injections, prospective, actions done; trend chain test and signal remain).

Core phase 3b, 2026-10-29 (implemented; measured: all gated criteria pass as
frozen). The prospective track runs on the Rust core
(`rangtoy.core_prospective`, `examples/run_core_campaign.py`) in 32.8 s with
54 solves; every decision equals the archive and the host reproduction;
floats agree to 1.4e-14. Run `outputs/core-phase3b-20261029-01`, archive
`results/core-phase3b.json`. Next: phase 3c (signal track) needs a Rust
point/Gaussian predictor, which is also the predictor step of phase 1.

Core phase 3, 2026-10-29 (implemented; measured). The injection campaign
runs on the Rust core (`rangtoy.core_workflow`, `rangtoy.core_injections`,
`examples/run_core_injections.py`) from the prepared host reproduction, with
no MS and no container: 49 solves in 25 s against 296 s. Frozen run
`outputs/core-phase3-20261029-01`: every compared field passes (858 exact, 928
floats to 1.3e-14, 54 distances to 1.5e-14), all six selections equal the
archive, but the frozen comparator reported 18 archive-only per-case fields as
missing. Post-hoc run `-02` adds them and passes against the archive and the
host reproduction. Archive `results/core-phase3.json`. Next: phase 3b, the
prospective and signal tracks.

Core phase 2, 2026-10-29 (implemented; measured: all eight frozen criteria
pass). `core/src/solve.rs` ports the QuartiCal 0.2.7 complex solver (MIT notice
kept). Run `outputs/core-phase2-20261029-01`: gain flags identical on fixture and
LUNO; gains within 1.4e-15 and 3.3e-16; 50 iterations and converged fraction
0.9833234067897558 as QuartiCal; losses and TV within 4e-16; LUNO rank survey
389/43/592 exact. LUNO solve 0.77 s; load+solve+fused 0.94 s, 96 MB (QuartiCal
28.3 s cold, 3.6 s warm, 633/382 MB). Inputs exported once from the LUNO MS to
`outputs/core-phase2-inputs-20261029-01`. Archive `results/core-phase2.json`.
Next: phase 3, the policy loop and campaign tracks on the core.

Core phase 1, 2026-10-29 (implemented; measured: criterion 4 failed as
frozen; post-hoc 4b passes in `outputs/core-phase1-20261029-02`, archive
`results/core-phase1.json`). `core/` is a new GPL Rust crate with
a fused pass (residuals, split losses, robust scores, antenna-diagonal normal
blocks) behind ctypes (`python/rangtoy/core.py`). Frozen run
`outputs/core-phase1-20261029-01`: residuals agree with the archive to 5.7e-14 Jy,
split losses to 2e-15, scores to 2e-14, diagonal blocks exactly; criterion 4
failed on b (4.9e-11 against 1e-13) because b cancels at the optimum. See
`core-phase1.md`.

Licence and port decision, 2026-10-29 (user, in chat): rang is now
GPL-3.0-or-later (`LICENSE`, Cargo and Python metadata). The user asked to work
down the port plan in `stack-consolidation-feasibility.md` section 9, starting
with phase 0 and phase 1, Rust for performance and Python for interfaces.
Open: whether Tricolour and Crystalball are GPL-2-only, which would block
translating their code into a GPL-3 core (phase 5 only).

Stack-consolidation feasibility study, 2026-10-29 (written study, no code,
no scientific change): `stack-consolidation-feasibility.md`, linked from the
README. Verdict: partially feasible; fuse the inner loop in one Rust core, keep
MS tables, strategy flaggers and WSClean external. New measurements (logged in
`tool-timings.md`): QuartiCal on the LUNO slice is 28.3 s cold versus 3.6 s with
a warm Numba cache, with gains equal to 2e-14 relative; decoding the DATA tiles
expands 2.72 GB to 3.28 GB to keep 12.6 MB. Prototype acceptance criteria are
frozen in the study. Section 9 adds a phased single-framework port plan with
before/after step counts (about 6× fewer for the five-track campaign). Run directory
`outputs/stack-feasibility-20261029-01`.

LUNO solved-gain follow-up, 2026-10-29 (provisional; protocol `487208b`).
A four-station casacore MS was built from row chunk 0 of 1934−638 scan 2
(1070–1497.8 MHz, 192 rows × 2048 channels), and QuartiCal 0.2.7 was run with
the frozen pipeline command (G complex, 2×32, 50 iterations). Chi-squared fell
from 73.75 to 0.27, 98.3% of intervals converged, flags were unchanged, and
gains were flagged exactly on unsupported station-bins. Rank at the solved
gains is identical to identity and random gains: 389 fully identified bins
(status 0) and 43 tree-shaped underidentified bins (status 3). This is the
declared expected consistency result. Run `outputs/luno-solve-20261029-02`,
archive `results/meerkat-luno-solved.json`, report `flagging-luno-solved.md`.
Tool timings are now logged in `tool-timings.md`, and upstream observations in
`upstream-notes.md`. QuartiCal's roughly 24 s per-container Numba JIT dominates
small solves, because the image's cache lives in `/tmp`.

LUNO answers from the observer, 2026-10-29 (WhatsApp, Ben Hugo):
- 15:36 SAST: "you can use it. Just cite the Sarao data usage acknowledgement".
- 15:37 SAST: "weight spectrum would have been modified by quartical" and
  "Sigma spectrum should have the original inverse variances".

- 15:38 SAST: "I can make a full resolution dataset available to you" and "The
  zarr files I think was a subset".

Recorded in
`flagging-luno-candidate.md`. No data, weights or flags were changed on the
strength of the chat. The running solved-gain follow-up (`flagging-luno-solved.md`,
frozen in `487208b`) keeps its frozen WEIGHT_SPECTRUM inputs. A SIGMA_SPECTRUM
weight variant would need its own protocol after a numeric check.

LUNO continuation, 2026-10-29: the user chose to continue with the LUNO
calibrators while the licence and native weights are unconfirmed (Ben Hugo asked
the same day; no answer yet). All LUNO results are provisional, and no
visibilities are redistributed. The processed-support survey protocol is frozen
in `flagging-luno-support.md` before any tile download (commit `807eb52`).
Measured, provisional: on 3.22 GB of row chunk 0 (1070–1497.8 MHz, stations
m000–m003, 2×32 grid):

- **1934−638 (scalar model):** 389 of 432 supported bins are fully identified
  (116,805 of 117,556 TRAIN cells). All 43 failures are tree-shaped support
  graphs. A post-hoc audit with the original `anchored_response(H,0,0,0)`
  call gives status 0 on the 389 and status 3 on the 43. The frozen call
  `(H,0,H,0)` was mis-specified: it zeroes the retained curvature and returns
  status 4. The first push wrongly reported "432/432 agree".
- **1830−211:** the model has about 1e-3 cross-hand terms, so the scalar U(2)
  condition does not apply (145 over-rank bins and 15 tree failures; native
  status 6 on all 160).
- **Model origin:** neither surveyed model has a logged origin. `setjy` named
  only 3C 286, and a `clearcal` with `addmodel` on field 2 would have reset the
  1830−211 model.
- No-data bins are the RFI-masked roughly 1150–1311 MHz and 1471–1498 MHz
  channels. Antennas m031, m040 and m044 have no TRAIN support.

Results are identical at identity and at the seed-20261029 random gain point.
Run directory `outputs/luno-support-20261029-01`; archive
`results/meerkat-luno-support.json`.

LUNO provenance, 2026-10-29 (text metadata only; no data changed). The stores'
OBSERVATION/FIELD/HISTORY strings, which are `json2`-encoded so no pickle is
involved, give project `20210818-0008`, observer `B Hugo` and target field
`Moon`. The Moon was 44′–149′ from the stored target direction during the track.
HISTORY holds 923 calibrator and 124 target rows, all CASA 5.6 records from
2022-09-10 to 2022-11-02: 25 `applycal` with `calwt=True`/`calflag`, four manual
`flagdata`, `setjy` (Perley-Butler 2017, 3C 286 only) and `clearcal`. FLAG,
WEIGHT_SPECTRUM and MODEL_DATA are therefore processing products, so the all-four-weight
support is not native evidence. The stores were published 2024-11-29 as
AfriCalim 2024 workshop data (`africalim/resources` QuartiCal recipes, likely
source of `CORRECTED_DATA_QCAL`). No licence was found. The workshop's
Polcal-Primer notice for its UHF Moon data says SARAO-owned, teaching use,
MeerKAT data policy 4.2.2.2. Research use needs confirmation from SARAO or the
observer; a question was sent to the "Hout boys" WhatsApp group 2026-10-29
~13:06 SAST, with no reply recorded. Run `outputs/luno-text-20261029-01` via
`tools/flagging/fetch-luno-text.sh` plus `examples/decode_luno_text.py`
(60 objects, 27,237 bytes), archived in `results/meerkat-luno-provenance.json`;
details in `flagging-luno-candidate.md`. Gain-bin support was later measured
provisionally (above).

Second public candidate, 2026-10-29 (metadata plus one bounded numeric tile;
no calibration). `LBAND_LUNO_CALIBRATORS.zarr` in the anonymous RATT bucket:
56 antennas, 20 scan groups, 3C 286 / PKS 1934−638 / PKS 1830−211 by
`PHASE_DIR`, a 14,218 s track. `WEIGHT_SPECTRUM` is positive in all four
correlations, and 1,735,448 tile cells are all-four supported (ESO137: 0).
Probe `outputs/luno-probe-20261029-01` (repeated in `-02`, all 50 object hashes
equal), via `tools/flagging/fetch-luno-probe.sh` plus
`examples/decode_luno_probe.py`, archived in
`results/meerkat-luno-candidate.json`; report `flagging-luno-candidate.md`.
Open before any use: licence/citation terms (no documentation found), whether
weights/flags/model are native or processing-derived (923 HISTORY rows not
decoded), and TRAIN gain-bin support on the calibrator scans.

New host setup, 2026-10-29 (no scientific runs, no code changes):
Windows 11 workstation using WSL2 Ubuntu 26.04 (x86_64, 16 cores, 30 GiB RAM),
checkout `~/Github/rang` on the Linux filesystem, Docker 28.3.3 inside WSL.
Python 3.14.4 venv from public PyPI with the recorded pins (JAX/JAXlib 0.11.1,
NumPy 2.5.3, pytest 9.1.1, Ruff 0.16.7). All checks pass: 654 Python (no skips),
19 Rust, release build, Clippy `-D warnings` and `cargo fmt` under Rust 1.93.1,
Ruff lint+format, `git diff --check`. Stable Rust 1.99 Clippy adds
`chunks_exact_to_as_chunks` on `src/projector.rs`/`src/response.rs`. Those
sources are hashed in result receipts, so they stay unchanged and checks pin 1.93.
Native Windows Python ran 614/654: all 40 failures are POSIX-only guard tests
(symlink privilege, `st_blocks`, bash paths, cp1252 output), so Windows is
documented as unsupported rather than weakening the guards.
`rang-flagging:local` rebuilt natively as linux/amd64
(`sha256:124ee3a09bbcf7f933a7280a24bc4e36f3c82db1910f33d78d09c96d09e55be6`).
Offline smoke check: QuartiCal 0.2.7, Stimela 2.1.4, python-casacore 3.8.1 and
the Rust kernel library load; the pilot recipe parses with `stimela doc`.
The other container images (sky, comparators, imaging, next) are not rebuilt.

Data restore, 2026-10-29. The original `outputs/` tree from the previous Mac
host was deleted and no copy exists. Every raw output, prepared input,
backup and run tree named below in this file is therefore gone (for example
`outputs/flagging-backups/*`, `outputs/tv-injections-pilot-01/`,
`outputs/tv-response-20260924-precision-01/`, `outputs/tv-caracal-clean-01/`). The tracked compact archives, receipts and
recipes remain the record. Wrappers that take those directories as sources need
their producing stages rerun into fresh namespaces first. Re-fetched inputs, each
verified against the recorded hash:
- `outputs/ska-pointing/outer_scans.zip`: upstream Git LFS object
  `https://gitlab.com/ska-telescope/sdp/science-pipeline-workflows/ska-sdp-wflow-pointing-offset/-/raw/main/tests/data/outer_scans.zip`,
  45,452,147 bytes, SHA256 `d4dae56f…144f`, equal to the LFS pointer oid.
- `outputs/flagging-sky-inputs/fitted.PKS1934.LBand.wsclean.cat.txt`: SHA256
  `b277bc6d…1fb9`, 5153 components (CC BY-NC 4.0, not redistributed).
- `outputs/flagging-next-data-wsl-20261029/primary-zmetadata.json`: SHA256
  `68fdb7f4…bbaa`. Its acquisition `outputs/tv-public-acquired-wsl-20261029-01`
  matches all 75 archived objects in bytes, SHA256 and ETag (884,609,513 bytes).

Prepared clean/contaminated input rebuilt with the unchanged frozen recipe:
`bash tools/flagging/run-injections.sh outputs/tv-injections-wsl-20261029-01`
(seed 19, strengths 3/10, three patterns, 50 iterations; exit 0, 296 s versus
400 s archived). Compared with `results/gain-tv-injections.json`: all selected
policies, flag counts, integers and strings identical; every non-timing float
agrees within 6.3e-15 relative. The kernel library hash differs because
`src/lib.rs` gained later kernels after that archive. Only timings and
archive-only summary fields otherwise differ. Use this directory, not the lost
`tv-injections-pilot-01`, as the prepared-input source for later wrappers.

Later stages rerun on this host, 2026-10-29, into fresh namespaces with frozen
code/settings. Each result is compared field by field with its tracked archive.
Exact fields cover integers, booleans, strings, mask IDs and policy selections.
Paths, timings, input/image/kernel digests and archive-only summary fields are
excluded. Only rounding-level float differences remain:

| Stage (archive) | Fresh run | Exact fields | Worst float rel | Wall time |
| --- | --- | --- | --- | --- |
| Actions (`gain-tv-actions.json`) | `tv-flagging-actions-wsl-20261029-01` | 61 equal | 7.6e-11 (differences of near-equal TVs) | ~6 min |
| CARACAL native (`gain-tv-caracal.json`) | `tv-caracal-wsl-20261029-01` | 99 equal | 4.5e-14 | 1265 s |
| Response (`gain-tv-response.json`) | `tv-response-wsl-20261029-01` | 461 equal | 3.8e-12 (closure residuals ~1e-17 Jy excluded) | 96 s |
| Concurrent suite (`gain-tv-concurrent.json`) | `tv-concurrent-wsl-20261029-01` | all branches complete, no failures | see branches | 445 s |
| Balanced, 7 cases (`gain-tv-balanced.json`) | `.../experiments/<case>` | 2829 action fields, 21 selections equal | 9.6e-15 | |
| Signal (`gain-tv-signal.json`) | `.../experiments/signal` | 287 equal | 2.8e-9 | |
| Transfer (`gain-tv-transfer.json`) | `.../experiments/transfer` | 262 equal | 3.3e-12 forecasts; coefficient 11 and train bias are ~1e-21/1e-19 zeros | |
| Public pilot (`meerkat-public-pilot.json`) | `.../experiments/public` | 56 equal | exact | |
| Uncertainty (`gain-tv-uncertainty.json`) | `.../experiments/uncertainty` | 180 rows equal | 2.1e-12 | |

Only time-burst seed 105 selects a non-null mask, identically for residual and
TV, as archived. Provenance HEAD/conditional GET reran into
`tv-provenance-head-wsl-20261029-01` and `tv-provenance-acquired-wsl-20261029-01`:
85 objects, 15,672 bytes, as recorded. Receipt SHA256 values differ only
through embedded finish times; per-object hashes were not archived.
CARACAL strategy sources re-fetched at revision `8f7bb363` into
`outputs/caracal-strategy-inputs-8f7bb363/`: all nine files match
`results/caracal-strategies.json` in SHA256 and size.
Images rebuilt natively: sky, comparators, parallel, response and next.
`tools/flagging/imaging/Dockerfile` uses a BuildKit heredoc `COPY`, so imaging
and next-imaging need buildx. This host uses the official buildx v0.37.2 user
plugin (`~/.docker/cli-plugins`, release checksum verified):
`docker buildx build --load --platform linux/amd64 -f tools/flagging/<d>/Dockerfile -t rang-flagging-<d>:local .`
for `imaging` then `next-imaging`.

| Stage (archive) | Fresh run | Exact fields | Worst float rel | Wall time |
| --- | --- | --- | --- | --- |
| Corrected imaging (`gain-tv-next-imaging.json` raw_result) | `tv-next-imaging-wsl-20261029-01` | 652 equal except allocated bytes | 2.2e-15 over 394 science floats | 36 s |
| Five-track trend (`gain-tv-next-trend.json`) | `tv-next-wsl-20261029-01/experiments/trend` | 1016 equal | 1.9e-15 | 436 s (whole campaign) |
| Prospective (`gain-tv-next-prospective.json` projection) | `.../prospective` | 1909 equal except allocated bytes | 1.5e-11 | |
| Signal guard (`gain-tv-next-signal.json`) | `.../signal` | 412 equal except allocated bytes | 1.7e-11 | |
| Provenance inspection (`gain-tv-next-provenance.json`) | `.../provenance` | 939 equal | exact | |
| In-campaign imaging (`gain-tv-next-imaging.json`) | `.../imaging` | 652 equal except allocated bytes | 2.2e-15 | |

The paired dirty-image figure `dirty-response.png` is byte-identical to the
archived one (SHA256 `8e2951ef…9c40`). FITS and whole-MS backup digests differ
because those files embed per-run headers and copies. Excluded: near-zero
values below 1e-12 (template cross-terms, pixel-MSE floors) and float64→complex64
rounding audits. The provenance inspection matching exactly also validates the
re-fetched provenance content. Unlike the original 2026-09-24 master
(imaging CLI failure, no gather), this fresh `run-next.sh` completes all five
tracks and the top-level gather with the corrected code. That is a
reproduction of the corrected strategy, not a new scientific result; no
threshold, setting or source changed. Every stage of the published five-track
evidence chain is now reproduced on this host from re-fetched public inputs.

See [STATE-history.md](STATE-history.md) for the entries before 2026-10-29.
