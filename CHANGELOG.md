# Changelog

All notable changes to rang-core (PyPI `rang-core`, package `rang`). The
version is set once, in `pyproject.toml`; the three `Cargo.toml`s, the
documentation and `rang.__version__` follow it, and
`tests/test_w4_5_release.py` checks that they agree. Pushing the tag `v<version>`
builds, tests and publishes that version (`.github/workflows/wheels.yml`);
the release notes are the section of this file for that version.

## Unreleased

- **Behaviour change: `rang-core lightcurve` now uses unit weights by default** (`--weights unit`:
  every correlation weighs 1, flags still applied, as `gemclean -unit-weights`). Every flux, σ_meas,
  snapshot and candidate of a run without `--weights` changes on a Measurement Set whose weights
  are not all equal. `--weights ms` (the MS's WEIGHT_SPECTRUM, else WEIGHT) reproduces earlier
  outputs byte for byte. Why: on E2-A's ESO137 scan 10 unit weights cut the snapshot rms by 28 %
  and the residual's offsets at forced positions from up to 1.19 to at most 0.15 mJy (#9,
  `research/ts-p3.md`, `research/ts-p4.md`).
- `rang-core lightcurve --channels-out M`: dynamic spectra, the DFT flux per interval in M equal
  channel groups; `--weights unit|ms` (#9, `research/ts-p2.md`, `research/ts-p3.md`).
- GeMClean: a Stokes I run keeps only each channel's active visibilities and weights, sorted, after
  its PSF (as the polarisation path does): case I (E2-N, 4096² multiscale, 8 channels) peaks at 37.9
  GB instead of 40.2 (0.944 ×), wall 0.993 ×, images byte-identical (#32, `research/gemclean-mem-32b.md`).

## 0.4.0 (2026-11-22)

0.4.0's question is whether learned stages can sit inside the chain without changing a single classical
result, and whether any of them earns its place (`research/dl-plan.md`, `research/v040-plan.md`). The
first part is met: every learned path is `off` by default, bit-identical to 0.3.0 on 60 configurations
× 5 stages. The second is not: no learned stage passed its frozen gates, so no weights ship.

### Highlights

- **The learned-stage contract ([#38](https://github.com/gijzelaerr/rang-core/issues/38))**: a `learned:` key on every stage. Weights come as ONNX files
  with a `rang.learned/1` header, and a mode runs only if its frozen gates passed, unless forced.
  rang's own interpreter runs them (`Conv` and `Relu` only, pure Rust, +49,664 B): 0.852 s at 1 thread
  and 0.166 s at 8 for 128 planes, within 2.4e-5 of PyTorch, bit-identical at 1-16 threads. See
  `docs/learned.md`.
- **A SARAO data factory ([#39](https://github.com/gijzelaerr/rang-core/issues/39))**: 219 L-band scans of 9 capture blocks registered with SHA-256
  manifests; 140 scans labelled by the rang Tricolour port, Tricolour 0.2.1 and AOFlagger 2.13.0
  (52 GB). Weights trained on them are CC BY 4.0, with SARAO's acknowledgement.
- **A retrain procedure for agents ([#46](https://github.com/gijzelaerr/rang-core/issues/46))**: `docs/agents/retrain-a-stage.md`, frozen rules, a
  held-out configuration (1k channels, block 1735892129), and a dry run on F5 that found and fixed
  13 gaps.
- **`rang-core watch`**: liveness of runs, spools and output directories, without touching them.
- **Fixes**:
  - K under `refantmode: flex` solves an antenna with no unflagged baseline to the reference
    ([#53](https://github.com/gijzelaerr/rang-core/issues/53); truth within 1e-6 ns).
  - GeMClean multiscale drops a scale whose convolved PSF has no positive peak, instead of stopping
    ([#54](https://github.com/gijzelaerr/rang-core/issues/54); images byte-identical where nothing is dropped).
  - `-memory-report` now covers the joined-channel path ([#32](https://github.com/gijzelaerr/rang-core/issues/32)).
  - The heavy lock counts CPU inside WSL and audits resident memory against bookings.
- **Measured, nothing shipped**:
  - F5 and F6 flaggers: F ([#40](https://github.com/gijzelaerr/rang-core/issues/40)). F6's SARAO validation passes every gate in both classes; it fails
    on the F4-era LUNO and ESO137 sets.
  - Gain-solver warm starts, stage 2: null ([#41](https://github.com/gijzelaerr/rang-core/issues/41); 8-15 % of iterations).
  - Learned clean masks, stage 6: null ([#43](https://github.com/gijzelaerr/rang-core/issues/43); 19-20 % fewer convolutions, 0 of 5 cases at equal
    quality).
  - Learned minor-cycle proposals, step 0: F ([#42](https://github.com/gijzelaerr/rang-core/issues/42); false flux +0.07 to +0.12 against +0.01).
  - `apply` with `calwt`: null ([#48](https://github.com/gijzelaerr/rang-core/issues/48); 4 % worse on E2-N).
  - GeMClean's beam spectra on disk: 0.811 × memory at 1.140 × wall, not adopted ([#32](https://github.com/gijzelaerr/rang-core/issues/32)).

### Known limitations

- **No learned stage passed, so no weights ship and every `learned:` mode needs your own weights file**
  (and `force: true` without passed gates). DL6's agent test (a fresh agent retrains a passed stage
  from the procedure alone) therefore did not run ([#46](https://github.com/gijzelaerr/rang-core/issues/46)).
- **#42 step 1** (learned minor-cycle proposals on real data): outcome F. On the four gated MeerKAT
  skies the learned proposal P is outside the tolerance for all three seeds (relative L2 1.22-1.79 × W1's)
  and slower than the best classical setting W\* (minor cycle 1.10-1.93 ×); `research/dl4b-step1.md`.
- **WSClean 3.8 is 6-23 % slower than 3.7 at `-j 1` on the minres path** ([#47](https://github.com/gijzelaerr/rang-core/issues/47)): GeMClean's
  coarse imaging now leads WSClean at one thread on S1, S2, S3 and H4. At 16 threads, and without
  minres, the two versions are level.
- **GeMClean's memory is 7.4 × WSClean 3.7's on E2-N joined IQUV at 2048², and 3.6 × on Stokes I
  multiscale at 4096²** (10.43 / 1.41 GB; 40.2 / 11.0 GB; [#32](https://github.com/gijzelaerr/rang-core/issues/32), `research/gemclean-mem-32.md`).
- 0.3.0's limitations still hold (below), apart from those listed as fixed here.

### Issues

Milestone v0.4.0, and the other issues touched since 0.3.0, from `gh issue list -R
gijzelaerr/rang-core` on 2026-11-22. Open issues are moved at the tag, as each outcome says.

| # | Title | Outcome | Note |
| --- | --- | --- | --- |
| 1 | Fast supervised flagger | progressed: F5 and F6 results posted to Landman; F7 drafted for v0.5.0 | [f6-flagger.md](https://github.com/gijzelaerr/rang-core/blob/main/research/f6-flagger.md) |
| 12 | GPU gridding in GeMClean | closed 2026-11-17: limitation (GPU 18-52 % slower at `-j 16`; code on branch `gpu-grid`) | [gpu-grid.md](https://github.com/gijzelaerr/rang-core/blob/main/research/gpu-grid.md) |
| 24 | CLEAN against RML/learned imagers | progressed: pfb sara also worse than GeMClean at upstream's own preset (N2, 5.05 ×) | [rml-gap.md](https://github.com/gijzelaerr/rang-core/blob/main/research/rml-gap.md) |
| 28 | Close-to-threshold stop rule | closed 2026-11-18: `-stop-tolerance 0.02` the default (shipped in 0.3.0) | [stop28-default.md](https://github.com/gijzelaerr/rang-core/blob/main/research/stop28-default.md) |
| 32 | GeMClean joined-IQUV memory | progressed: E2-N profile, memory report on the joined-channel path; spectra spill not adopted (time) | [gemclean-mem-32.md](https://github.com/gijzelaerr/rang-core/blob/main/research/gemclean-mem-32.md) |
| 34 | Self-cal scan-long solve memory | moved to v0.5.0 (GeMClean's share is #32's) | [selfcal-memory.md](https://github.com/gijzelaerr/rang-core/blob/main/research/selfcal-memory.md) |
| 37 | DL0: literature and cost profile | closed 2026-11-20: done (selfcal minor cycle and resyncs 63-65 % of selfcal) | [dl0-profile.md](https://github.com/gijzelaerr/rang-core/blob/main/research/dl0-profile.md) |
| 38 | DL1: contract, weights format, registry | closed 2026-11-20: done (own ONNX interpreter, gates I1-I5 pass) | [dl1-contract.md](https://github.com/gijzelaerr/rang-core/blob/main/research/dl1-contract.md) |
| 39 | DL2: training-data factory | closed 2026-11-20: stage 1 shipped (219 scans registered, 140 labelled) | [dl2-data.md](https://github.com/gijzelaerr/rang-core/blob/main/research/dl2-data.md) |
| 40 | DL3: F5 flagger | F5 and F6 F; nothing ships; F7 for v0.5.0 | [f6-flagger.md](https://github.com/gijzelaerr/rang-core/blob/main/research/f6-flagger.md) |
| 41 | DL4a: gain-solve warm start | closed 2026-11-20: null (8-15 % of iterations; no network pilot) | [dl4a-screen.md](https://github.com/gijzelaerr/rang-core/blob/main/research/dl4a-screen.md) |
| 42 | DL4b: minor-cycle proposals | step 0 F; step 1 F | [dl4b-step0.md](https://github.com/gijzelaerr/rang-core/blob/main/research/dl4b-step0.md), [dl4b-step1.md](https://github.com/gijzelaerr/rang-core/blob/main/research/dl4b-step1.md) |
| 43 | DL4c: mask, quick-look, settings | closed 2026-11-22: stage 6 null, stage 9 headroom only, quick-look not started | [dl4c-mask.md](https://github.com/gijzelaerr/rang-core/blob/main/research/dl4c-mask.md) |
| 44 | DL4s: one-day screenings | moved to v0.5.0 | |
| 45 | DL5: combined learned selfcal | moved to v0.5.0 (needed a DL4 pass) | |
| 46 | DL6: retrain-a-stage procedure | procedure and dry run done; the agent test waits for a passed stage | [dl6-retrain.md](https://github.com/gijzelaerr/rang-core/blob/main/research/dl6-retrain.md) |
| 47 | WSClean 3.8 rebaseline | closed 2026-11-22: done (parity holds; 3.8 slower at `-j 1` minres) | [wsclean38-rebaseline.md](https://github.com/gijzelaerr/rang-core/blob/main/research/wsclean38-rebaseline.md) |
| 48 | Native L0 weights (`calwt`) | null: default stays `false` | [apply-calwt.md](https://github.com/gijzelaerr/rang-core/blob/main/research/apply-calwt.md) |
| 53 | K drops an antenna without a baseline to the refant | closed 2026-11-21: fixed (`refantmode: flex`) | [k-refant-53.md](https://github.com/gijzelaerr/rang-core/blob/main/research/k-refant-53.md) |
| 54 | Multiscale stops on a scale without a positive PSF peak | closed 2026-11-21: fixed (scale dropped with a warning) | [gemclean-54.md](https://github.com/gijzelaerr/rang-core/blob/main/research/gemclean-54.md) |

### Changes since 0.3.0

- **WSClean 3.8 rebaseline ([#47](https://github.com/gijzelaerr/rang-core/issues/47))**: GeMClean's WSClean statements re-measured against 3.8 (`research/wsclean38-rebaseline.md`). Parity, the mask and the multiscale results hold. The speed table changes only at one thread with coarse gridding, where WSClean 3.8's `minres` is 6-23 % slower than 3.7's. `tools/oracles/wsclean-native/Dockerfile` builds 3.8 (`--build-arg WSCLEAN_TAG=v3.8`, `cmake --install` and `ldconfig` for its FetchContent shared libraries, dependency commits in `/wsclean-deps.txt`); `examples/oracle_wsclean_clean.py run --image` selects the WSClean image.
- **Learned stages, contract and interpreter ([#38](https://github.com/gijzelaerr/rang-core/issues/38))**: a `learned:` key on every stage (`mode: off` by
  default, propose, settings, replace; `off` bit-identical on 60 configurations × 5 stages), ONNX
  weights files with a `rang.learned/1` header, refusal by gates, header and envelope with an explicit
  `force`, and receipts. rang's own ONNX interpreter (`Conv`, `Relu`; pure Rust, +49,664 B in the
  extension) is the reference runtime: PyTorch agreement 8.6e-6 (F3) and 2.4e-5 (F4), bit-identical at
  1-16 threads; the hand-written kernel is its fast path, within 1.1e-5. Final timing, 128 planes: the
  interpreter takes 0.852 s at 1 thread and 0.166 s at 8 (kernel 0.881 / 0.142 s, tract 4.59 / 1.00 s);
  no runtime crate passed the frozen gates (tract +20.4 MB against 8 MB). See `docs/learned.md`.
- **Data factory for learned stages ([#39](https://github.com/gijzelaerr/rang-core/issues/39))**: 219 SARAO L-band scans of 9 capture blocks registered
  with SHA-256 manifests, and 140 training and validation scans labelled by the rang Tricolour port,
  Tricolour 0.2.1 and AOFlagger 2.13.0 (52 GB). Weights trained on these data are CC BY 4.0 with
  SARAO's acknowledgement (owner, 2026-11-20).
- **F5 supervised flagger ([#40](https://github.com/gijzelaerr/rang-core/issues/40)): no weights shipped.** Targets: outcome F (R1 1.000 against
  Tricolour's 0.865 and cost C1 0.365-0.409 pass, but R5, G-drop, R2 H2 and G-sub outer32 fail).
  Calibrators: stopped at the label audit (Stop-L), and a post hoc arm also failed (F).
- **F6 flagger (#40): F, no weights shipped** (`research/f6-flagger.md`). Hybrid positives lift R5
  from F5's 0.338 to 0.98-0.996; antenna-dropout training passes G-drop on every SARAO and LUNO set;
  every SARAO validation scan passes every gate in both classes. Failed on F4-era data: calibrators
  R3 16.9 × T on LUNO MAIN_7 (T flags 45 × fewer cells there than on SARAO), targets G-drop 0.350 at
  8 antennas and outer32 R3 1.94 on ESO137. No held-out set read; F7 drafted for v0.5.0.
- **DL4a, classical warm starts for the gain solver ([#41](https://github.com/gijzelaerr/rang-core/issues/41)): null.** A one-day screening found warm
  starts saving 8-15 % of iterations, so no network pilot followed. The optional gain start
  (`diag::solve_from`) is bit-identical without a start.
- **DL4b, a learned deconvolution step ([#42](https://github.com/gijzelaerr/rang-core/issues/42) step 0): outcome F.** An iterated mode-P CNN, tested
  once on 270 regenerated ASTRODECONV2019 fields, gave false flux +0.07 to +0.12 against +0.01, and
  4-7 inversions against 3. Nothing ships.
- **Retraining a passed learned stage for another configuration ([#46](https://github.com/gijzelaerr/rang-core/issues/46))**:
  an agent procedure (`docs/agents/retrain-a-stage.md`, skill `retrain-a-stage`) with frozen rules
  (`research/dl6-retrain.md`). The held-out configuration is 1k channels (block 1735892129, scans 23
  and 25 unread). The dry run on F5 ran every step and found 13 gaps in the procedure, now fixed. The
  agent test waits for a stage that passes.
- **DL0 ([#37](https://github.com/gijzelaerr/rang-core/issues/37))**: literature verdicts and the selfcal cost split (GeMClean minor cycle
  and resyncs 63 % (E2-A) and 65 % (E2-N) of selfcal, major cycles 1.6-2.3 %).
- **DL4c, learned clean mask ([#43](https://github.com/gijzelaerr/rang-core/issues/43)): null.** Masking from cycle 1 needs 19-20 % fewer
  convolutions on real E2-N scans and 41-56 % fewer on simulations, but 0 of 5 cases reach equal
  quality. Stage 9 (settings): headroom, nothing trainable now; quick-look not started.
- **GeMClean memory, phase 4 ([#32](https://github.com/gijzelaerr/rang-core/issues/32))**: `-memory-report` covers the joined-channel path.
  E2-N profile against WSClean 3.7: 7.4 × on joined IQUV (2048²), 3.6 × on Stokes I multiscale
  (4096²). Beam spectra in the `-reorder` file give 0.811 × memory at 1.140 × wall, over the frozen
  1.10, so they are kept as a patch, not merged.
- **GPU gridding ([#12](https://github.com/gijzelaerr/rang-core/issues/12)): closed as a limitation.** GPU 18-52 % slower than the CPU at
  `-j 16`; the code stays on branch `gpu-grid`.
- **`rang-core watch PATH...`** shows each stage's status and time and whether its process is still
  alive. It also lists spool tasks and worker heartbeats, receipts, the newest file and the last log
  line; options `--once`, `--json` and `--interval`. It watches run directories, spool directories or
  any output directory without changing them. It shows liveness, not progress
  (`research/live-view-scope.md`).
- **K with `refantmode: flex` ([#53](https://github.com/gijzelaerr/rang-core/issues/53))**: an antenna with no unflagged baseline to the reference is
  solved through other baselines (a fallback centre plus hops): truth within 1e-6 ns, CASA within
  0.0016 ns p95, and bit-identical where the reference's baselines are present. `strict` keeps CASA's
  rule.
- **GeMClean multiscale ([#54](https://github.com/gijzelaerr/rang-core/issues/54))**: an automatic scale whose PSF-convolved peak is not positive (about
  n / 2.5 px on sparse coverage) is dropped with a warning, and listed as `dropped_scales` in the
  report, instead of stopping the run. With nothing dropped, all 45 FITS of a 4096², 8-channel run are
  byte-identical to before. (radler keeps such a scale with gain g / peak.)
- **`apply` with `calwt` ([#48](https://github.com/gijzelaerr/rang-core/issues/48)): null.** It equals CASA's applycal to 1e-6 but is channel-flat by
  CASA's rule, and on E2-N it is 4 % worse than raw weights. The default stays `false`.
- **Heavy lock**: `tools/heavy_lock.py status` now counts CPU inside WSL for holds launched through
  `wsl.exe`. A WSL busy loop now reads 1.0 core, where it read 0.0 (IDLE). It also shows each hold's
  resident memory, summed over its process tree, against the booked GB, and flags holds over their
  booking with `OVER`.

## 0.3.0 (2026-11-19)

0.3.0's question is "can I trust the images and polarisation on my own native data, and drive it from an
agent?" (`research/roadmap.md`, v0.3.0). Its "done when" rows and their evidence are in
`research/v030-readiness.md`; the release review is `research/v030-review.md`.

### Highlights

- **Native MeerKAT data runs end to end**: SARAO 1735268787 (L band) through flag, calibrate, apply, image
  and self-calibration, rc 0; 17 of 25 frozen rows met against CASA (limitations below).
- **Against CARACal's shipped strategy on LUNO (E3-B)**: rang 6,195 s against CARACal 6,926 s, 3C 286
  |Δp| ≤ 0.03 points, Δχ ≤ 0.22°.
- **GeMClean stops earlier by default**: `-stop-tolerance 0.02` saves a mean 1.125 major cycles on 8 of 8
  blind skies (issue #28). `-reorder` is the default with joined polarisations (issue #32).
- **Self-calibration fits in 8 GiB**: scan-long Sp/Sa solves are streamed, 3.6 GiB peak against 35 GiB,
  bit-identical, 9-41 % more wall (issue #34).
- **Opt-in CASA `calwt` weighting** for Xf, K, G, Gpol, KCROSS and Df: the Xf gap to CASA drops from
  0.054-0.065° to 0.012° (issue #33).
- **New**: `rang-core lightcurve` (residual snapshot light curves, issue #9); an MSv4 read path
  (`rang.msv4`, bit-identical on 9 MSs, issue #5); a `spool` executor prototype for multi-node runs
  (bit-identical; 4.67 × with 8 workers on one host, issue #4); an MCP server through which an agent runs the whole chain (issue #27).
- **Measured null or negative, so no default changed**: SDm03 as the imaging default (#13); GeMClean's
  auto-mask cycle gap, which is WSClean's fast sub-minor loop (#36); the multiscale compact-source excess
  (+9 to +18 µJy, in WSClean too, #23); the GPU gridder (not faster at `-j 16`, #12); the trained flagger
  (F4 stopped on its cost gate, #10); self-calibration defaults (#6).

### Known limitations

- **Native MeerKAT data (E2-N, issue #7): not met as frozen, 17 of 25 rows.** SARAO 1735268787, L band, observatory-phased: rang runs all five stages end to end (rc 0). Missed: 3a (73 of 2.28e9 flag cells), Xf p95 (2.085° against 2.0°), the K/G/B composites, 3c (dirty L∞; compact scatter 2.7 % against 1 %), the J1744−5144 χ and the target's compact-source scatter (13.3 % against 1.5 %). The data are observatory-phased, so K, KCROSS and Xf are near-null and their real-size solve is untested. The CASA reference flagged 19 of 62 antennas in its delay solve because the oracle set-up gave CASA's solves the flags from after rang's calibrate-stage `extendflags`, not the flags rang solved on. That leaves those antennas no unflagged baseline to the reference antenna. The K-downstream misses are therefore partly an oracle defect; a corrected CASA rerun is in progress (`research/e2n-followup.md`) (`research/e2n-native.md`).
- **The comparison with CARACal on E2-A (E3-A) is not in this release.** Its timed passes were running on
  the release date (rang pinned to 16 cores, then CARACal's shipped strategy); the result follows in
  `research/e3-caracal.md` and in 0.3.1. E3-B is measured (CARACal 6,926 s against
  rang 6,195 s on LUNO, 3C 286 |Δp| ≤ 0.03 points, Δχ ≤ 0.22°; `research/e3-caracal.md` 10.16-10.17 on
  branch `e3-caracal`).
- **`-stop-tolerance 0.02` on the pipeline's `-auto-threshold 3` path is not measured** (issue #28,
  `research/stop28-default.md`): the default switch rests on runs with absolute thresholds; the GeMClean
  benchmark and the E2/E5 image archive gates are re-read at the next archive run.
- **χ is stated as a limit, not gated** (issue #14, `research/chi-offset.md` section 11). On LUNO's 3C 286
  the RM-corrected χ(λ²=0) is 29.4°, 3.6° from 33°, with rang equal to CASA; under the frozen absolute
  limit the test failed by 0.47° and 2.31°. No absolute χ claim is made. On LUNO's calibrator product use
  FEED's receptor angle 0, not CARACal strategy 1's −90 (the fitted angle is +8.2°): a per-product
  configuration note. A frozen follow-up with an RM term in the 3C 286 model is for later.
- **Xf differs from CASA by 0.054-0.065° by default** (median, held-out 3C 286 simulations, limit 0.05°).
  The cause is CASA's `calwt` weighting of the Xf solve (issue #33, `research/xf-gap.md`);
  `calibrate.xf_calwt: true` takes the gap to 0.012° (0.021° averaged). It stays off by default, as do the
  other solve types' `*_calwt` keys (`research/calwt-terms.md`).
- **Multiscale CLEAN over-estimates compact sources** (issue #23, `research/multiscale-flux-fix.md` 8.1,
  measured null): under natural weighting on DF5-O's array a median +9 to +18 µJy excess on sources
  ≥ 20σ_ap, in WSClean 3.7 and GeMClean alike. No setting tested passes on both fields. Automatic scales
  (no `-multiscale-scales`) come nearest (+11.0 / +9.05 µJy); Högbom is unbiased (−4 µJy) at 7-11 % higher
  residual RMS. No default changes.
- **With multiscale, a FITS mask confines component centres, not flux** (issue #35,
  `research/gemclean-ms-mask.md`), as in WSClean 3.7. Large scales centred in small mask islands take up
  extended emission outside the mask. Cleaned deep (about 1.6σ), both imagers can diverge. Use Högbom
  when nothing may be cleaned outside the mask.
- **Joined polarisations peak on the linear sum** (issue #22, `research/v030-readiness.md` section 4), as
  WSClean 3.7 and radler (!238, merged 2026-11-16, unreleased) do: with `-pol QU -join-polarizations`,
  components whose Q and U cancel are not cleaned, in either imager. `-squared-channel-joining` stays
  refused.
- **The imaging floor is attributed in part** (issue #13; `research/floor-3.md`, `floor-4.md`,
  `floor-5.md`, `floor-6.md`). Steady antenna gains are its main cause (share 0.83 under imaging-floor's
  full criterion): on floor-3's subset of the pilot one phase-only self-calibration round takes the floor
  from 1,073 to 379 µJy. Of the 379 µJy left (8.6 × thermal), deconvolution depth and spectral modelling
  are confirmed on a held-out scan (D_h 0.201 and 0.474); masked Högbom to 0.3 mJy after the round
  (SDm03) explains 0.717 of the held-out excess. SDm03 as the imaging default is "not yet": it fails the
  WSClean oracle on reserve scan 4, so the default stays A0 and #13 is closed (`research/sdm03-default.md`).
  That oracle failure rests on WSClean's fast sub-minor loop leaving 1,096 pixels above its own stop
  (issue #36, closed null, `research/automask-cycle.md`); oracle runs comparing cycle counts or residual
  excess now use WSClean's `-no-fast-subminor`.
- **Self-calibration defaults are unchanged** (issue #6, `research/selfcal-defaults.md`): on the pilot the
  best cell of the frozen grid (two phase rounds at 600 s) scores 0.905 against the default's 0.892, less
  than the frozen 0.05 margin. More rounds, longer first intervals and a phase-only first round do not
  meet the truth gate on simulation (`research/selfcal-arms.md`).
- **Image gate 3c is not met on the cleaned images** (E2-B with the mask: compact scatter 1.18 % against
  1 %; E2-A: dirty 5.0e-3 of the peak, compact scatter 3.6 %, target scatter 4.3 %, ratios falling with
  radius as 512- against 4,096-channel smearing predicts; `research/e2b-misses.md` 9.29,
  `research/e2-acceptance.md` 9.13-9.14). E2-A is not passed as frozen.
- **E2-A's K1 G1 B1 composite (gate 3b) is a documented limitation with its cause**
  (`research/e2a-3b-k.md`, coordinator decisions 2026-11-17): CASA's K estimator is biased against
  simulated truth (1.1e-4 ns noise-free, about 5 × rang's error with noise), and the subset's 1.1e-3 is
  one G1 solution that CASA flags by its `minsnr` and rang keeps. With rang's K shared, CASA's composite
  is 4.1e-5 / 4.0e-3. A shared 3.7e-4 to 5.7e-4 noise-free floor is not located yet.
- **E2-B's 1830−211 χ (|Δχ| up to 13° at p of 0.02-0.06 %), transfer χ and leakage (0.30 %)** stay as in
  0.2.0 (`research/e2b-misses.md` sections 5-7).
- **GeMClean memory and temporary files with joined polarisations** (issue #32,
  `research/gemclean-memory3.md`): `-reorder` is now the default with `-join-polarizations`; it writes
  temporary files beside `-name` (or in `-temp-dir`), about 28 GB on 115,000 rows of 4,096 channels in
  IQUV, and a killed run leaves them (`-no-reorder` keeps everything in memory). With the default
  self-calibration on the E2 pilot GeMClean peaks at 9.3 GiB, above the default `data.memory_limit_gb` of
  8 (issue #34, `research/selfcal-memory.md`).
- `flagdata` mode `tfcrop` is still refused (`research/v8-tfcrop.md`, `research/v8c-tfcrop-poly.md`), and
  no trained flagger ships: F4 stopped on its calibrator cost gate (issue #10, `research/f4-flagger.md`).
- The GPU gridder is not merged: at `-j 16` it is not faster than the CPU path (f64 18-52 % slower; f32
  up to 9 % slower and failing gate 1; issue #12, `research/gpu-grid.md`).
- A run directory made by 0.2.0 resumes "done" stages by their configuration hash; rerun with
  `--force all` to get 0.3.0's parallactic angles and imaging weights.
- Strategy, sky-model and mask files enter a stage's configuration hash by path, not by content
  (`research/v030-review.md` E5-21): after editing one in place, rerun that stage with `--force`. Hashing
  the contents would change every stage hash once, so it waits for a release that may do that.
- **Licence** (`docs/licence.md`, `research/mit-relicense-audit.md`): the package is `GPL-3.0-only`.
  GeMClean's automatic mask, joined peak finding, multiscale CLEAN and polarisation normalisation follow
  radler (LGPL-3.0-only), and WSClean's README says "version 3" without "or any later version"; while they
  are in it, the extension `rang._core` is conveyed under the GPL, version 3 only. ra-ng's own files are
  MIT; the files translated or derived from GPL or LGPL code keep their GPL lines.
  `THIRD-PARTY-NOTICES.txt` lists the upstreams.

### Issues

Every gijzelaerr/rang-core issue touched since v0.2.0 (2026-11-14), from
`gh issue list -R gijzelaerr/rang-core --state all -L 60` on 2026-11-19. "Closed" gives the date it was
closed on GitHub; the owner closes the rest at the tag, as each outcome says.

| # | Title | Outcome | Note |
| --- | --- | --- | --- |
| 1 | Fast supervised flagger (F2) | progressed: Landman's review answered, F4's result posted; F5 proposed, not frozen | [f5-flagger.md](https://github.com/gijzelaerr/rang-core/blob/main/research/f5-flagger.md) |
| 2 | v0.2.0 release tracking | closed 2026-11-14; its carry-overs are 0.3.0's first rows | [v030-readiness.md](https://github.com/gijzelaerr/rang-core/blob/main/research/v030-readiness.md) |
| 3 | Multi-node stage 1: chunk task API | progressed: chunk tasks run multi-process, bit-identical | [chunk-task-api.md](https://github.com/gijzelaerr/rang-core/blob/main/research/chunk-task-api.md) |
| 4 | Multi-node stage 2: a multi-node executor | progressed: `data.executor: spool` prototype, bit-identical, S(8) 4.67 on nash | [multinode-executor.md](https://github.com/gijzelaerr/rang-core/blob/main/research/multinode-executor.md) |
| 5 | MSv4 / xarray-ms interoperability | progressed: `rang.msv4` read path, bit-identical on 9 MSs | [msv4-interop.md](https://github.com/gijzelaerr/rang-core/blob/main/research/msv4-interop.md) |
| 6 | Self-calibration beyond model absorption | closed 2026-11-17: limitation (defaults unchanged under the frozen grid) | [selfcal-defaults.md](https://github.com/gijzelaerr/rang-core/blob/main/research/selfcal-defaults.md) |
| 7 | Native MeerKAT data (E2-N) | limitation: not met as frozen, 17 of 25 rows; stays open | [e2-acceptance.md](https://github.com/gijzelaerr/rang-core/blob/main/research/e2-acceptance.md) |
| 8 | Open CASA tasks | progressed: V8b's fixed-rule modes at parity, FLAG_ROW 9/9; tfcrop still refused | [v8b-flagdata.md](https://github.com/gijzelaerr/rang-core/blob/main/research/v8b-flagdata.md) |
| 9 | Time series P1: residual snapshot light curves | progressed: `rang-core lightcurve` | [ts-p1.md](https://github.com/gijzelaerr/rang-core/blob/main/research/ts-p1.md) |
| 10 | Trained flagger (F4) | closed 2026-11-17: limitation (stopped on the calibrator cost gate; weights not shipped) | [f4-flagger.md](https://github.com/gijzelaerr/rang-core/blob/main/research/f4-flagger.md) |
| 11 | UHF band | progressed: scoping note; out-of-L-band warning | [uhf-scope.md](https://github.com/gijzelaerr/rang-core/blob/main/research/uhf-scope.md) |
| 12 | GPU gridding in GeMClean | closed 2026-11-17: limitation (not faster at `-j 16`; research only, code not merged) | [gpu-grid.md](https://github.com/gijzelaerr/rang-core/blob/main/research/gpu-grid.md) |
| 13 | The imaging floor | closed 2026-11-18: attributed in part; SDm03 as default not yet (no switch) | [sdm03-default.md](https://github.com/gijzelaerr/rang-core/blob/main/research/sdm03-default.md) |
| 14 | Absolute polarisation angle χ | closed 2026-11-17: limitation (stated, not gated) | [chi-offset.md](https://github.com/gijzelaerr/rang-core/blob/main/research/chi-offset.md) |
| 22 | Join polarisations on the squared sum | closed 2026-11-17: limitation (linear sum kept; upstream agrees) | [pol-join-squared.md](https://github.com/gijzelaerr/rang-core/blob/main/research/pol-join-squared.md) |
| 23 | Multiscale flux miss on compact sources | closed 2026-11-17: limitation (measured null) | [multiscale-flux-fix.md](https://github.com/gijzelaerr/rang-core/blob/main/research/multiscale-flux-fix.md) |
| 24 | CLEAN against RML/learned imagers | progressed: step 1, pfb sara worse than GeMClean on 4 of 4 gated skies | [rml-gap.md](https://github.com/gijzelaerr/rang-core/blob/main/research/rml-gap.md) |
| 27 | MCP server and agent benchmark | progressed: piece 1 met (an agent runs the chain over MCP); piece 2 is v0.6.0 | [mcp-server.md](https://github.com/gijzelaerr/rang-core/blob/main/research/mcp-server.md) |
| 28 | Close-to-threshold stop rule | closed 2026-11-18: `-stop-tolerance 0.02` the default (blind confirmation H17-H24, 8 of 8 skies, mean 1.125 cycles saved) | [stop28-default.md](https://github.com/gijzelaerr/rang-core/blob/main/research/stop28-default.md) |
| 30 | Flaky `test_confirmed_gemclean[False]` | closed 2026-11-15: fixed (job-file race; its run-state form, R-01, fixed too) | [v030-review.md](https://github.com/gijzelaerr/rang-core/blob/main/research/v030-review.md) |
| 31 | `test_waiters_acquire_in_ticket_order` flaky | closed 2026-11-15: fixed (heavy-lock ticket races) | [nash-host.md](https://github.com/gijzelaerr/rang-core/blob/main/research/nash-host.md) |
| 32 | GeMClean joined-IQUV memory | progressed: phase 3 met, `-reorder` the default with joins | [gemclean-memory3.md](https://github.com/gijzelaerr/rang-core/blob/main/research/gemclean-memory3.md) |
| 33 | Xf rang-CASA gap | closed 2026-11-17: limitation with its cause (`calibrate.xf_calwt`, opt-in) | [xf-gap.md](https://github.com/gijzelaerr/rang-core/blob/main/research/xf-gap.md) |
| 34 | Self-cal scan-long solve needs 37 GB | fixed (streamed Sp/Sa solves, 3.6 GiB); still open on GitHub, GeMClean's 9.3 GiB left | [selfcal-memory.md](https://github.com/gijzelaerr/rang-core/blob/main/research/selfcal-memory.md) |
| 35 | Multiscale with a FITS mask ignores the mask | closed 2026-11-17: no defect (centres stay inside the mask; a limitation) | [gemclean-ms-mask.md](https://github.com/gijzelaerr/rang-core/blob/main/research/gemclean-ms-mask.md) |
| 36 | Auto-mask freezes a major cycle earlier than WSClean | closed 2026-11-18: null, no defect (WSClean's fast sub-minor loop leaves 1,096 px above its stop; `-no-fast-subminor` for such oracle runs) | [automask-cycle.md](https://github.com/gijzelaerr/rang-core/blob/main/research/automask-cycle.md) |

Not touched since v0.2.0: #15-#20. Closed before v0.2.0 as duplicates: #21, #25, #26.

### Changes since 0.2.0

- Changed (`research/mk1-katdal.md`, deviation 3, post hoc 2026-11-18): the `[meerkat]` extra pins `katdal==0.24`, which no longer needs `pkg_resources` (no setuptools pin for `mvftoms.py`). Fixed: `rang.meerkat.open_mvf` opens a local archive by its Windows drive path (katdal read `C:\...` as a URL scheme `c`, with 0.23 as with 0.24).
- New (issue #33, `research/xf-gap.md`): `calibrate.xf_calwt` (default false, out of the stage hash at its default; off byte-identical). With it an Xf solve weights each cell as CASA 6.7.6.14's polcal does: the 1/SIGMA^2 weight times F(p) F(q), F the antenna's |G|^2 times its channel mean of |B|^2 per hand (CASA's `calwt` scaling by the pre-applied tables, measured on a split MS to 1e-6). The held-out 3C 286 simulation's rang-CASA Xf gap (median 0.054-0.065°) came from this weighting; with the key it is 0.012° (unaveraged) and 0.021° (averaged). The other solves are unchanged.
- New (`research/calwt-terms.md`, follow-up of #33): `calibrate.k_calwt`, `g_calwt`, `gpol_calwt`, `kcross_calwt` and `df_calwt` (each default false, out of the stage hash at its default; off byte-identical). With one on, that solve type weights its cells by CASA's `calwt` factor of the pre-applied tables that correct its data (B, G or T, each by CASA's `calcWtScale`: |G|^2, the channel mean of |B|^2), computed in a new Rust kernel (`rang.cal_apply.calwt_scale`, memory O(rows + times x antennas)). A G solve with only K, and every B solve, are unchanged by construction. Measured against CASA and simulated truth in the note; no default changes.
- Changed (issue #28, `research/stop28-default.md`, amendment 4): `gemclean` now ends the run by default when the exact peak after a major cycle is below 1.02 times the threshold (`-stop-tolerance 0.02`); the minor cycles still clean to the threshold. At the default 1e-4 accuracy on eight new blind 2048² simulated skies (the confirmation leg, H17-H24) it saved 1.125 major cycles per run on average (all 8 skies; 1 or 2 each) at the default's false flux, Q and recovery; S1-S3, H1-H8 and the three pilot runs held every check. It applies to Stokes I, separate polarisations or channels and `-fits-mask`; with `-auto-mask`, `-multiscale` or the joins it stays 0 and an explicit nonzero value is refused. `-stop-tolerance 0` restores the exact stop. Runs without the flag now end up to two major cycles earlier, and their `report.json` carries `stop_tolerance` 0.02. This includes `rang-core image` and the selfcal images (they call `gemclean` without `-stop-tolerance`), except images with an automatic mask (`image.auto_mask`, `selfcal.cleanmask_method: wsclean`) or `image.multiscale`: their images, residuals and models change. The stage configuration hashes do not (they hash the configuration only), so an image or selfcal stage finished before this change is not run again unless forced (`--force image`, `--force selfcal`).
- Changed (licence metadata, `docs/licence.md`): the package's licence expression is now `GPL-3.0-only` (pyproject, `core` and `core/py` crates, CITATION). It contains WSClean-derived code ("GPL 3", with no "or later") and radler code (LGPL-3.0-only, conveyed under GPL v3). ra-ng's own files are MIT (next entry).
- Changed (licences per file, `docs/licence.md`, `research/mit-relicense-audit.md` "Step 1 done: own code MIT"): ra-ng's own code is now MIT (`LICENSES/MIT.txt`): 436 files, 125,726 lines with `SPDX-License-Identifier: MIT` (every shipped file now has an SPDX line), and 5 files (3,730 lines) translated from BSD upstreams with `MIT AND BSD-3-Clause`. The 64 files (61,685 lines) translated or derived from GPL or LGPL code (casacore, ducc0, WSClean, radler, aocommon, schaapcommon, CASA, CARACal, Tigger, EIDOS, msutils, AOFlagger) keep their GPL lines. The package stays GPL-3.0-only while those parts are in it; the root crate `rang-sim` is MIT. Contributions take the licence of the file they change. `tests/test_spdx_headers.py` checks each line against `research/results/mit-relicense-audit/spdx.csv`.
- Fixed (issue #34, `research/selfcal-memory.md`): the default self-calibration (Sp then Sa, `solint: inf`) runs within the default `data.memory_limit_gb` of 8. An Sp or Sa solve whose solution interval does not fit is streamed (`rang.cal_stream`, Rust `cal::diag_stream`) through a scratch file beside the MS, 92 bytes per unflagged visibility, with bit-identical solutions; on the E2 pilot the scan-long solve peaks at 3.6 GiB instead of 35.4. The selfcal solves are planned at their own measured 45 bytes per cell (`CELL_BYTES["selfcal"]`, was the chain's 96). GeMClean's 9.3 GiB on the pilot is not under the limit yet.
- Investigated (issue #35, `research/gemclean-ms-mask.md`): `gemclean -multiscale -fits-mask` does not lose the mask. Every component centre stays inside it at every scale, as in WSClean 3.7. After one major iteration on simulated H4 and on the ESO 137 pilot, against WSClean: the same scales are chosen, the flux inside the mask agrees within 0.5 %, and the flux outside agrees within 0.21 Jy (2.72 Jy against 2.93 Jy). The deeper runs could not be compared because WSClean diverges on them. The flux the model has outside the mask comes from the scale shapes of centres inside it. The clean path is unchanged. Added: a test that every centre stays inside the mask at every scale, and a line on this behaviour in the `-fits-mask` help and in `image.fits_mask`.
- Notices (`research/v030-review.md` B-01, B-02): `THIRD-PARTY-NOTICES.txt` and `docs/licence.md` now
  list casacore's measures (`MCDirection.cc`, `MeasMath.cc`, `MeasTable.cc`, `MSDerivedValues.cc`,
  LGPL-2.0-or-later), which the CASA-frame parallactic angle follows, and WSClean 3.7 with radler
  `76fe4474` (LGPL-3.0-only), aocommon and schaapcommon, which GeMClean follows; each read in the
  upstream sources. The four GeMClean files that follow radler carry `GPL-3.0-or-later AND LGPL-3.0-only`.
  No casacore data table is read: the parallactic angle's Earth orientation is astropy's IERS table.
- Notices (`research/mit-relicense-audit.md` 3.2, `research/v030-review.md` 5.5): c-blosc, katdal's BSD
  text, Tricolour in `core_flag.py`, fdlibm, Tigger and codex-africanus in `formats/sky.py`, schaapcommon in
  `gemclean/input.rs`, CASA and casacore in `calmodels.py`, `apply.rs` and `flag_extend.py`, EIDOS, msutils
  (its licence statements conflict, GPL v2 against GPL-3.0-or-later: an owner decision), and the casacore storage managers the table writer translates, whose headers
  said "nothing is copied"; WSClean 3.6's `wstackinggridder.h` "GPL 3" stated exactly; the CARACal strategy
  copies in `research/results/` named with CARACal's GPL-2.0 (`research/results/CARACAL-NOTICE.md`).
- Fixed (R-02): a calibrate solve whose every solution is flagged (for one, a reference antenna whose
  baselines the strategy flags) now ends `rang-core run` with `failed: calibrate: ... wrote no
  solutions ...` and a hint (exit 1, the stage recorded as failed), not a traceback
  (`rang.cal_gain.NoSolutions`, a RuntimeError).
- Fixed (B-11, B-12): GeMClean's `-temp-dir` now also takes the joined runs' dirty-image spill files
  (`<name>-dirty-<n>.spill`); `-reorder` with one polarisation, `-reorder` with `-channel-range` or
  `-average-channels > 1`, and `-temp-dir` where it has no effect print a warning and are in `-h`.
  Images are unchanged.
- Changed (B-13): `lightcurve.json` is strict JSON; a value that is not finite (the flux of a fully
  flagged interval) is `null`, not a bare `NaN`. `lightcurve.csv` keeps `nan`.
- Fixed (B-16): `rang-core lightcurve` refuses a field with rows on a data description other than 0; it
  imaged DATA_DESC_ID 0 only, silently.
- Fixed (E5-22, E5-23, E5-24, write-back): a session that failed or was killed before writing FLAG no
  longer blocks the next one (only a session that may have written FLAG is refused, and the record of a
  written column is made before its first write); a column left half-initialised is initialised again
  after `restore_flags`; the journal is written only once the MS is open for writing, and an MS that
  cannot be written is refused before the flag backup with a clear message.

- New (`research/uhf-scope.md`, decision D6): a stage given channels outside MeerKAT L band (856-1712 MHz;
  UHF 544-1088 MHz, S band) logs one warning that only L band is validated, naming `docs/limits.md`
  (`rang.core_pipeline.band_warning`; also in `config check`). Nothing is refused and no result changes.
- Fixed (`research/v030-review.md` R-01): on Windows a run's `state.json` replace failed with
  PermissionError while another process read it, so polling `run_status` through `rang-core mcp` (or any
  reader) failed the run after a finished stage. The replace now retries for up to 10 s, as the MCP job
  files do since #30. Found by `tests/test_mcp_chain.py`, which drives the whole chain (flag, calibrate,
  apply, image, selfcal) through `rang-core mcp` on the public fixture with a scripted JSON-RPC client.
- New (issue #9, `research/ts-p1.md`): `rang-core lightcurve`, residual snapshot light curves at given
  positions (a Rust DFT kernel `rang._core.lightcurve_dft`, snapshot images and a robust rms;
  `--candidates`, `--gridder wstack --device gpu`). Checked against WSClean `-intervals-out` and an
  independent DFT on held-out simulations, under post hoc amendments 9.1 and 9.2.
- New (issue #28, `research/gemclean-stop28.md`): `gemclean -stop-tolerance e`, off by default: the run also
  ends when the exact peak after a major cycle is below (1 + e) T. Refused with auto-masks, multiscale and
  joins.
- New (issue #23, `research/multiscale-flux-fix.md`): `gemclean -multiscale-bias-reference`,
  `-multiscale-point-cap` and `-no-negative`; defaults unchanged.
- Changed (`research/ts-p1.md` section 14): GeMClean leaves FLAG_ROW rows out of the imaging-weight grid. Uniform
  and Briggs weights change where FLAG_ROW is set and FLAG is not; WSClean 3.7 counts those rows. Every
  archived G2-G9 case is bit-identical (none has such rows).
- New (issue #5, `research/msv2-edge-cases.md`): the MSv2 reader reads IncrementalStMan string and array
  columns and TiledCellStMan, and refuses per column; MSs refused before now read.
- Changed (tools, `research/nash-host.md`): `tools/heavy_lock.py` backfills past a queue head that does not
  fit (drain limit `RANG_HEAVY_DRAIN_MIN`, `run --drain`); `RANG_HEAVY_NICE` and a default Linux lock
  directory. Fixed (#30, #31): Windows sharing violations on MCP job files and heavy-lock tickets.
- New (issue #4, multi-node stage 2 step 1, `research/multinode-executor.md`): `data.executor: spool` with
  `data.spool` (an absolute directory on a filesystem every node mounts) and `data.spool_wait_s` (default 600).
  The stage writes each chunk task into the spool, workers started by any launcher (`python -m rang.core_spool
  worker DIR --threads T`: on this host, over ssh, by `srun` or by a Slurm or PBS job array) run them, and the
  stage reduces the partials in plan order as the single MS writer, so results are bit-identical to one process.
  `data.processes` is then the number of workers planned for. A worker that stops beating for 60 s has its task
  re-run elsewhere (at most 3 runs); a worker of another rang or `_core` build is refused. Partials are pickles,
  so the spool must be private to the user (refused on POSIX otherwise). Resource keys: they leave the stage hash
  unchanged. A prototype: chosen over Slurm/PBS job arrays, Dask and Ray by the comparison in that note.
- Changed (issue #32 phase 3, `research/gemclean-memory3.md`): `gemclean -reorder` is now the default when
  several polarisations are joined (`-pol` with more than one and `-join-polarizations`); `-no-reorder` keeps
  everything in memory. Its temporary files (12 B per row, channel and polarisation read plus 8 B per weighted
  visibility; about 28 GB on 115,000 rows of 4096 channels in IQUV, 9 GB on 34,000) go beside `-name` or in
  `-temp-dir`; a killed run leaves them. The joined clean also holds the models sparse and one resync work
  space for every beam. Every FITS file is byte-identical. On E2-B's joined-IQUV 8-channel 2048² runs the peak
  is 7.7 GiB on J1331+3030 and J1939−6342 (16.5-16.9 without `-reorder`) and 5.7 GiB on J1833−2103 (7.2 with
  phase 2's `-reorder`), about 5-8 % slower than `-no-reorder` (exclusive pairs: five of six 1.04-1.08 ×). `-memory-report` also lists
  the live blocks of 1 MiB or more at the heap's highest.
- New (issue #32 phase 2, `research/gemclean-memory2.md`): `gemclean -reorder` (off by default) with several
  polarisations reads each polarisation in chunks into a temporary file per output channel and keeps each
  entry's compacted visibilities in a temporary file between residuals, as WSClean's reordered files;
  `-temp-dir DIR` places them (default: the directory of `-name`). Every FITS file is byte-identical. On E2-B's
  joined-IQUV 8-channel 2048² runs the peak falls from 15.9-16.5 to 9.1 GiB (J1331+3030, J1939−6342) and from
  8.4 to 7.2 GiB (J1833−2103); about 28 GB of temporary files on the large fields.
- New (`research/calchain-floor.md`): `calibrate.k_zero_start` (default false, out of the stage hash at its
  default). K solves also run from zero delays and keep, per solution interval, the run with the lower weighted
  residual (`rang.cal_delay.solve(zero_start=True)`). The FFT start uses the refant baselines only; with a few
  cells there it can land on a sidelobe, and Gauss-Newton converges to a wrong delay: on E2-A, ID 50's K1
  interval 7 (2,335 ns against 0.11 ns; CASA's K1 holds 2,365 ns). With the key that solution is 0.121 ns on the
  real subset and nothing else moves by more than 1e-3 ns. About 10 % more K time. Off is unchanged.
- New (`research/e2a-3b-diag.md`): `calibrate.bandpass_model_divided` (default false, out of the stage hash at
  its default). B solves divide the pre-applied data by the model, which the K and G pre-applies corrupt, before
  any time average (`rang.cal_bandpass.bandpass(model_divided=True)`, `rang.cal_gain.model_divided`, CASA's
  `divideCorrByModel`). With `calibrate.average_time` and K or G varying inside B's interval this changes B; on
  E2-A's 15-antenna subset the averaged B then equals the unaveraged B to 4e-7. Off is unchanged.
- New (`research/msv4-interop.md`, #5): `rang.msv4` reads an MSv4 processing set (xradio schema 4.x, Zarr)
  into the core's row layout, behind the optional `[msv4]` extra (xarray, zarr 3, numcodecs; Python 3.11+).
  Bit-identical to the MSv2 path on xradio 1.3.1's conversions of 9 MSs; a uint8 `FLAG` (xarray-ms) is read as
  bool when it holds only 0 and 1 and refused otherwise. xarray-ms 0.5.14 drops autocorrelations by default,
  so its stores of MSs with them lack those rows; with `auto_corrs=True` all 9 are bit-identical. `CORRECTED_DATA` and `MODEL_DATA` groups,
  SIGMA-derived weights, repeated `WEIGHT` and decreasing frequencies read bit for bit; neither writer keeps
  `FLAG_ROW`, so row flags are lost in conversion. The Tricolour flag stage gives the same flags fed from MSv4
  rows as from the MSv2 (fixture scan 9); no stage reads MSv4 directly yet.
- Fixed (WSClean #208, fixed upstream by !1068, commit `ca23d835`, not yet in a release; v3.7 still has
  the old rule): `gemclean`'s theoretic beam (the start and box of the restoring-beam fit, the circular
  beam when the fit fails, the default multiscale scales, `theoretic_beam_rad` in `-report.json`) now
  keeps only visibilities whose `v`, as well as `u`, falls inside the grid; it tested `u` on both axes,
  as WSClean 3.5-3.7 do. Only coverage the grid cuts in `v` but not in `u` changes; every archived G2-G9
  case is bit-identical (`research/u5-upstream.md`). The core gridder's `w_limits` (WSClean 3.6 port)
  still tests `u`.
- New (E2-B arm A3, `research/e2b-misses.md` 9.26-9.27): `calibrate.casa_phase_weights` (default false, out of
  the stage hash at its default; needs `calibrate.average_freq`). Calmode `p` solves (Gpol, and G with
  calmode p) use CASA's phase-only datum, read from CASA's source: the pre-applied data divided by the
  model per channel with weight `w|M|^2`, averaged in time and frequency, then normalised to unit
  amplitude with the weight times the amplitude squared (`rang.cal_gain.model_divided`, `phase_only`).
  `ap` solves and every other term are unchanged; off is byte-identical.
- Changed (issue #32, `research/gemclean-memory.md`): `gemclean` with several polarisations
  (`-pol IQUV -join-polarizations`, joined channels, masks) needs about half the memory, with
  byte-identical images: polarisations are read and gridded one at a time, measurements keep only
  their weighted visibilities, polarisations with the same rows and weights share one gridder plan,
  and the clean keeps fewer image copies (the dirty images wait in a `<name>-dirty-<n>.spill` file
  until they are written). On E2-B's J1833−2103 (IQUV, 8 joined channels, 2048², masked) the peak fell from 20.2 to
  9.2 GiB. `-memory-report` now works on Windows, and the polarisation
  path's `-report.json` has the `memory` section.
- Changed (E2-B P1, `research/e2b-misses.md` 9.15-9.16): `frame='casa'` parallactic angles now follow
  casacore (IAU 1976/1980 apparent place, `gst94`, casacore's diurnal shift and polar motion in HADEC) and
  match casacore's own angle to 1.3e-8 rad, against 7e-6 rad before. Calibrate and apply angles shift by up
  to about 7e-6 rad, so archived `RANG_CORRECTED_DATA` no longer matches a rerun bit for bit. The old form
  is kept as `cal_pol.parallactic_angle_tete`.
- New (E2-B fix 5, `research/e2b-misses.md` 9.21-9.22): `gemclean -auto-mask` / `-abs-auto-mask` with
  `-join-polarizations` (and `image.auto_mask` with `image.join_polarizations`), as WSClean 3.7's
  radler: the noise and the peaks are those of the joined I + Q + U + V residual, and the mask is
  the union of every polarisation's model pixels. Masks on unjoined polarisations and `-fits-mask`
  on several polarisations stay refused.
- New (multi-node stage 1, issue #3, `research/chunk-task-api.md`): the chunk loops of `flag`, the
  `complex` solve and `complex` apply are chunk tasks (`rang.core_tasks`: serialisable `ChunkSpec`s, `run`,
  an ordered reduce through the one MS writer) run by a local process pool. New keys `data.executor`
  (`local`), `data.processes` (default 1: in this process, as before) and `data.threads` (the rayon
  threads the processes share); each process plans its chunks under `memory_limit_gb / processes`.
  None of them enters the stage hash. Chain terms, models, CASA-table applies and imaging stay in one
  process.

## 0.2.0 (2026-11-14)

The owner released 0.2.0 on 2026-11-14. Its finish line
(`research/finish-plan.md` section 1) is met in part, and the parts not met
move to 0.3.0 (`research/roadmap.md`).

### Known limitations

- **Not every stage is within its oracle tolerance.**
  - E2-B is the acceptance run on processed LUNO MeerKAT L-band data against
    CASA 6.7.6.14, WSClean and QuartiCal (`research/e2-acceptance.md` 7.3-7.5).
  - **Met:** run and write-back, the readers (casacore, CASA listobs and
    flagmanager, WSClean, dask-ms), FITS output, gridding (exact on all
    1.1e9 cells), K, KCROSS, Xf, Df, and 3C 286 polarisation parity
    (|Δχ| ≤ 0.055°).
  - **Not met, in the frozen and in the amended arm:**
    - Gpol: median 0.124° in the amended arm, against a 0.1° limit.
    - The fcal and gcal K G B composites: median 1.1e-3.
    - CASA applycal on rang's tables: 40 cells over, max 25 eps; flags exact.
    - Image gate 3c.
    - Polarisation angle on 1830−211: |Δχ| up to 13°.
    - Transfer χ (polarisation angle carried from calibrator to target).
    - Rang's leakage: 0.30 %.
  - The diagnosis (`research/e2b-misses.md`, from code and archived numbers;
    no new runs) confirms no rang bug among the seven. Its likely causes:
    - CASA's oracle solved on different flags and weights (composites);
    - the estimators weight data differently (Gpol);
    - float32 rounding in CASA's long apply chain (applycal);
    - a scorer error and unmasked cleaning (3c);
    - χ at p of 0.02-0.06 % (1830−211);
    - LUNO's receptor angle and ionospheric RM (transfer χ).
  - Pre-registered arms A1-A5 test these in v0.3.0.
- **The measurements still to come are now v0.3.0 work:**
  - the E2-A run on ESO 137;
  - E3, the comparison with CARACal's MeerKAT strategy (image quality, flux,
    wall time and memory);
  - the E5 review.
- **Native MeerKAT data is not tested.** The acceptance data is processed LUNO
  data plus simulation (issue #7).
- **No absolute χ claim.** LUNO's χ offset is not explained; see
  `research/chi-offset.md`.
- `flagdata` mode `tfcrop` is refused, and the trained flagger is not shipped.

### Changes since 0.1.0


- Fixed (2026-11-14): a `tools/heavy_lock.py run` or `tools/check_all.py` started inside a heavy-lock
  hold (`RANG_HEAVY_LOCK_HELD`, set by `heavy_lock.py run` for its child) runs inside that hold
  instead of queueing again. A check wrapped in `heavy_lock.py run` held 4 slots idle for five hours
  while its own inner ticket waited, and would deadlock on a full queue. A nested request for more
  than the hold warns and still runs.
- New (2026-11-14): `tools/heavy_lock.py status` prints each hold's real CPU use (its process tree,
  sampled for 2 s) next to its booked slots, marks a hold IDLE under 5 % of one core per booked slot,
  and ends with `booked N slots, using ~M cores`. Report only; nothing is stopped.

- Fixed (correctness audit, `research/correctness-audit-2026-11-13.md`): bad input now fails clearly
  instead of running wrong. A NaN visibility made every gain, bandpass, delay or Df solution NaN with
  its flag clear; non-finite data, model and weight cells are now flagged, which gives exactly the
  solution of the same cells flagged (gain, bandpass, delay, KCROSS, Xf, Df). `core_grid.invert(gridder="wgrid")` with a GPU device raises instead of
  running on the CPU. gemclean's FITS reader (`-predict` models, `-fits-mask`) no longer panics on a
  non-ASCII header byte. `-threshold`, `-abs-threshold` and `-auto-threshold` must be finite and not
  negative. The gain and bandpass solvers refuse zero rows and per-row arrays of the wrong length; delay refuses zero rows.
  Write-back refuses out-of-range DATA_DESCRIPTION ids (a negative one picked the last row). Flag-version
  names with `\ : * ? " < > |` are refused on every platform. `fluxstd.manual` refuses non-positive
  frequencies. No default's numbers change.

- Changed (task df-flag-rule, `research/p-flag-spread.md`): with `apply.parang`, P now flags as CASA's
  `applycal(parang=True)` does on linear feeds: a cell with any correlation flagged after the tables
  (input flags, a bad receptor, a Df-flagged cross hand) is flagged in all four, since P rotates XX and
  YY out of all four correlations. New key `apply.parang_flags` (`spread`, the default; `none`, the
  previous flags) and `parang_flags=` on `rang.applycal.applycal` and `rang.cal_pol.apply`. Values are
  unchanged; without `parang` nothing changes.

- Fixed (E5 final E5-02): `gemclean -model-column DATA`, or a model column equal to the column being
  imaged (`-data-column`, or CORRECTED_DATA when the MS has it), overwrote that column after imaging;
  both are refused with exit 2 before anything is read. `-no-update-model-required` still writes nothing.
- Changed (E5 final F-05): the licence page and `THIRD-PARTY-NOTICES.txt` list CASA's C++ sources that
  the calibration and flag-extension ports follow (GPL-2.0-or-later, LGPL-2.0/2.1-or-later), with
  their copyright notices; each derived file names CASA.
- Changed (E5 final F-01): astropy is a required dependency. Every polarisation solve and `apply.parang`
  take the parallactic angle from it, and a bare `pip install rang-core` stopped there with
  `ModuleNotFoundError`; the `imaging` extra is kept and now adds nothing.
- New: a known-limits page (`docs/limits.md`, linked from the README): scope, flagging, calibration,
  self-calibration, imaging and platform limits with the reports behind them; the E2 and E3 results
  are added when they land (E5 final, `research/e5-final.md`).
- Changed (finish-plan item 27, f11fdd1): an unset `calibrate.refant` (it was refused) means CARACal's
  `auto` choice, or antenna 0 when no antenna qualifies; the default selfcal reference antenna is the
  same choice (it was antenna 0), and `selfcal.refant: auto` runs; the `image.niter` default is
  1,000,000 (it was 100,000).
- Changed: Measurement Set reads take a channel slice in the reader (`core/src/ms.rs`), 2.1-2.2x
  faster on the channel-chunked polarisation solves and bit-identical on 19 frozen comparisons
  (`research/sliced-read.md`).
- Changed (E5 pre-review "Later" findings, `research/e5-prereview.md` section 2.3): `image.fits_mask`
  and a selfcal FITS `cleanmask_method` are read relative to the configuration file, as `flag.strategy`
  and `calibrate.model.lsm`; **deprecated:** a mask found only relative to the working directory is still
  used, with a warning, and a mask found in neither place is refused before anything runs (E5-41).
  Repeated YAML keys are refused with their line numbers (PyYAML kept the last one). Unknown commands and
  options exit 2 on stderr (was 1); `--version` works after other global options; `run --force STAGE` of a
  stage outside `run.stages` is refused; the complex-term refusals and unknown term keys say what to change
  (E5-40). Data whose OBSERVATION `TELESCOPE_NAME` is not MeerKAT run with a warning, and `state.json`
  records `telescope` (E5-39). A flag version left unlisted by a kill is listed by the next save of the same
  flags; a flag version the last attempt recorded but the MS no longer has is warned about
  (`restore_missing`) (E5-42). Every source file carries an SPDX `GPL-3.0-or-later` line (E5-45).

- New: `calibrate.average_time` (default false; task E2, `research/e2-average-time.md`). With it on,
  the K, G, B, F, Gpol, KCROSS, Xf and Df solves use CASA's estimator for long intervals: data and
  model averaged in time within each solution interval (weighted means over unflagged cells after the
  pre-applied tables and P, weight the sum, per baseline, channel and correlation), streamed in blocks
  of rows, and the memory plan counts the averaged rows. E2's whole-scan solves on 4096-channel
  MeerKAT data (176 GiB per interval unaveraged) then fit `data.memory_limit_gb: 8`. Off, every
  solve and the stage hash are unchanged. Refused with a `complex` term.
- New: `selfcal.average_time` (default false; task E2): Sp and Sa solve on data and model averaged
  in time within each solution interval, as `calibrate.average_time` does, so CARACal's solint 120 fits
  8 GiB at 4,096 channels (333 GiB per interval without). Not CubiCal's estimator, which solves every
  sample (owner item 33(3)). Off, the stage hash is unchanged. Refused with Sd.
- New: `calibrate.average_freq` (default false; task E2, the pre-registered "E2-B amended" arm,
  `research/e2-average-freq.md`): the G, F and Gpol solves average their data and model over the
  window's channels before solving (weighted means per row and correlation after the pre-applies and
  P), as CASA's G-type solves do; K, B, KCROSS, Xf and Df are unchanged. Off, every solve and the
  stage hash are unchanged.

- Changed (owner decisions on the E5 pre-review, `research/e5-prereview.md` section 3): receipts are
  `rang.receipt` version 5; a Measurement Set a command modified is listed by its `listing_sha256` (file
  sizes and mtimes), not a full content hash; the stage summaries hash the flags, gain solutions and images
  written and name the tables and settings behind a written column (E5-20). This holds for every directory
  a command modified, not only the MS. The default `run.stages` is the whole chain, flag, calibrate, apply, image, selfcal (was flag,
  calibrate, image, which imaged uncalibrated DATA) (E5-28). The simms antenna tables `data/*.itrf.txt` are
  recorded in `docs/licence.md` as facts, not code; the sdist carries only `meerkat.itrf.txt`, which GeMClean
  compiles in (E5-11). `docs/licence.md` lists codex-africanus and katdal's test helpers (BSD-3), and as
  behaviour reimplemented with no code copied CARACal's `get_refant`, msutils, CASA's flag extension,
  fluxscale and applycal semantics and casacore's table formats, plus casacore-data's observatory
  positions (E5-33). `rang/data/README.md` records the source and SHA256 of `casacore_observatories.json`
  (E5-34). The sdist leaves out `.claude/` and the checkout tools under `tools/` other than `tools/wheel/`,
  and CONTRIBUTING lists what it carries (E5-37). The `recipes` extra installs stimela 2.1.4 on Python 3.13
  and older only, so `pip install 'rang-core[recipes]'` resolves on 3.14 (E5-38).

- New (task E4, `research/e4-tutorial.md`): the tutorial `notebooks/00-ms-to-image.ipynb`, from a
  Measurement Set to an image with `rang-core run` and `gemclean` on A1 small, with its configuration
  and strategy in `examples/ms-to-image/`; the wheels workflow's job `e2e` runs the same chain on all
  five wheels (`tools/e2e/run.py`); `docs/cli.md` gains `gemclean -h`. `examples/a1_simtruth.py`
  finds the checkout's antenna table when rang-core is installed from a wheel.

- Fixed (E5 pre-review, `research/e5-prereview.md`): after `rang-core run ... --force flag`, a stale later stage
  put back the flags saved before its earlier attempt (the old flag output); later stages now start from the
  flags the rerun stage left, whenever that stage restored or wrote FLAG. Before a rerun restores a stage's
  earlier flags, the flags it replaces are saved as the flag version `rang_rerun_<UTC time>`, so flags set
  outside rang are never lost (one more version per rerun). DATA is never written: `apply.column: DATA` and
  `selfcal.model_column: DATA` are configuration errors, selfcal refuses to copy apply's output into an
  `input_column: DATA`, and `rang.core_writeback.WriteBack` refuses DATA. The run directory is locked on
  Windows too, so a second `rang-core` command on the same MS is refused. Malformed configuration values give
  the error report (exit 2), not a traceback. The changed-configuration refusal names `--force` forms both
  commands accept. The wheels and sdist carry `THIRD-PARTY-NOTICES.txt` (QuartiCal's MIT, codex-africanus's
  and Tricolour's BSD-3 notices). The release job publishes to PyPI only after its own checks pass. The MS
  table lock holds on Linux only, as the docs now say.

- Research (task F3, `research/f3-flagger.md`): a second learned RFI flagger, not wired into
  `rang-core flag`. New `rang.f3flag` (wrapper W3, features reference, injections, labels, measures),
  `rang.f3net` (the JAX network for training), the Rust kernel `rang_core::f3flag` with
  `rang._core.f3flag_features` and `f3flag_logits`, the AOFlagger driver
  `tools/oracles/aoflagger/f3_aoflag.py` and `examples/f3_*.py`. `rang.f2flag_sim` gains the
  held-out observation `f3sim-t` (seeds registered in `rang.simtruth.SEEDS`).

- New: `gemclean` is in the wheel (task G8, `research/g8-wheel.md`): the console script `gemclean`
  (and `python -m rang.gemclean`) runs GeMClean's command line inside the extension
  (`rang._core.gemclean_main`); no second binary ships. The command line moved from
  `core/src/bin/gemclean.rs` into `rang_core::gemclean::cli`, which the source build's binary now
  wraps; files, output and exit codes are the binary's (0, 2 on an error, 101 on a panic), and
  Ctrl-C ends the run at once. New `-version` (also `--version`). On 64-bit Linux the extension
  uses gemclean's huge-page allocator, so `-memory-report` works from the wheel.
- Changed: `rang-core`'s `image.gemclean: auto` runs the installed extension's gemclean
  (`python -m rang.gemclean` of the running interpreter) and records the sha256 of `rang._core`;
  the search of PATH and of the checkout's `core/target` is gone. A source build is used only when
  `image.gemclean` names it.

- Changed: `gemclean` grids at `-wgridder-accuracy 1e-4` in single precision by default (task G7,
  `research/g7-defaults.md`): on the 512-channel ESO 137 pilot 33 % less wall at `-j 16`, 27 % at
  `-j 1` and 4.1 GB less memory, within the class B bounds written first. Single precision is the
  default for an accuracy of 1e-5 or coarser; the new `-double` forces double precision, and
  `-wgridder-accuracy 1e-6` alone gives the earlier form. `rang-core`'s `image.wgridder_accuracy`
  defaults to 1e-4, the model column follows gemclean's precision, and the image and selfcal stage
  hashes change once (`--force`).
- Fixed: `gemclean`'s restoring beam is fitted as WSClean 3.7's binary fits it (a unit-peak Gaussian
  in linear space over a box of 10 theoretic beams, regrown up to five times, on the box's quadrant
  that schaapcommon's unsigned offsets leave in; the start is the theoretic beam, raised to the
  Gaussian taper). BMAJ and BMIN agree with WSClean's to 4.3e-7 on 19 cases; before, BMAJ was 9-30 %
  narrower. Every restored image and every FITS header's `BMAJ`, `BMIN`, `BPA` change; dirty, PSF,
  model and residual data do not. The report's `main_lobe_pixels` is now `fit_pixels`.

- New: per-image clean masks and cut-offs in `rang-core selfcal` (`research/c5b-selfcal-masks.md`),
  CARACal's `clean_cutoff`, `cleanmask_method` and `cleanmask_thr` as `selfcal.clean_cutoff`,
  `selfcal.cleanmask_method` (`wsclean`, `none` or a FITS mask path) and `selfcal.cleanmask_thr`:
  lists over images 1 to `rounds + 1`, the last entry repeating, passed to gemclean as
  `-auto-threshold`, `-auto-mask` and `-fits-mask`. Empty by default (images as before); `sofia`,
  `breizorro` and local-rms masks are refused. The selfcal summary records each image's
  components, major cycles and stop reason. The new keys change the selfcal stage hash once
  (`--force`). Measured on C5's truths: CARACal's masks do not meet C5's T2 gate (held-out cases
  included) and do not lift C5's model-absorption limit; archive
  `research/results/c5b-selfcal-masks.json`.
- Research: E1, the whole chain on A1's simulated truth (`research/e1-chain.md`): `rang-core run`
  (flag, CARACal's full-Stokes calibrate, apply, selfcal, image) on A1 full's first 32 integrations
  per scan exits 0; no E1 gate of A0 is met as frozen and no rang bug was located (the K failures are
  CASA's own on the same flags). Scripts in `research/results/e1-chain-scripts/`, archive
  `research/results/e1-chain.json`. No package code changed.
- New: GeMClean masks, tapers and uv limits (`research/g4-masks.md`), WSClean 3.7's options:
  `-fits-mask` (one plane, the image's size); radler's automatic mask `-auto-mask`,
  `-abs-auto-mask`, `-auto-mask-nmiter` in the default `dual` mode (Högbom, joined channels and
  multiscale with its per-scale masks; needs `-mgain` or `-minor-to-threshold`);
  `-taper-gaussian` (arcseconds by default), `-taper-tukey`, `-taper-inner-tukey`, `-taper-edge`,
  `-taper-edge-tukey`, `-minuv-l` and `-maxuv-l` on the weight grid's cells, and `-minuvw-m`,
  `-maxuvw-m` on rows. `rang-core image` passes `auto_mask`, `abs_auto_mask`,
  `auto_mask_nmiter`, `fits_mask`, `taper_gaussian`, `taper_tukey`, `taper_inner_tukey`,
  `minuv_l`, `maxuv_l`, `minuvw_m`, `maxuvw_m`; `image.uvrange` stays refused (use those keys),
  and `auto_mask` without `mgain` is a configuration refusal. `-local-rms`, `-casa-mask`,
  `-horizon-mask` and `-clean-border` are refused.
- Fixed: `image.gemclean: auto` finds `core/target/<profile>/gemclean.exe` on Windows. The test
  stand-in for gemclean is a Python script (a `.cmd` wrapper on Windows), and the selfcal refusal
  test no longer needs a built binary. `examples/a1_simtruth.py` uses spawned workers where fork is
  missing (Windows); fork elsewhere, unchanged. New `tools/heavy_lock.py`, one heavy job at a time across
  Windows and WSL; CONTRIBUTING describes native Windows development.
- New: `gemclean -pol` and `-join-polarizations` (`research/g9-stokes.md`): Stokes I, Q, U, V and
  XX, YY in any combination, parsed as WSClean 3.7 parses `-pol` (`IQUV`, `iquv`, `xx,yy`), formed
  from linear-feed correlations with WSClean's arithmetic and weights (`min(4 w_a, 4 w_b)` for a
  formed Stokes parameter); WSClean's file names (`<name>[-0000]-<pol>-<kind>.fits`, one PSF per
  channel from the first polarisation), `CRVAL4`, imaging-weight sources and header weights; joined
  polarisations pick peaks on the normalised linear sum, as WSClean 3.7's default loop does (its
  help text says the sum of squares; recorded in the note), so with QU joined, components whose
  Q and U cancel are not cleaned, in GeMClean as in WSClean 3.7 (IQUV joining, as E2-B's, is far
  less exposed); both work with `-channels-out` and
  `-join-channels`. XY, YX, circular correlations and `-link-polarizations` are refused.
  `rang-core image` passes `image.pol` and `image.join_polarizations` (only when not the defaults),
  so E2-B's image section is no longer refused. Single-polarisation I imaging is unchanged.
- New: `gemclean -multiscale` (`research/g5-multiscale.md`): WSClean 3.7's multiscale CLEAN,
  radler's algorithm with its sub-minor loop (`rang_core::gemclean::multiscale`), with
  `-multiscale-scales`, `-multiscale-max-scales`, `-multiscale-scale-bias`, `-multiscale-shape`
  (tapered quadratic or Gaussian) and `-multiscale-gain`; scales from WSClean's theoretic beam;
  the residual made exact for the image-domain beam after every sub-minor loop. Works with one
  output channel, joined channels (with `-fit-spectral-pol`) and unjoined ones, and with
  `-auto-threshold`. `rang-core image` passes `multiscale` and the new keys `multiscale_scales`,
  `multiscale_max_scales`, `multiscale_scale_bias`, `multiscale_shape` and `multiscale_gain`.
  Without `-multiscale` the images are byte-identical to before.
- New: `rang-core selfcal` (and `run` with `selfcal` in its stages) runs CARACal's self-calibration
  rounds (`research/c5-selfcal.md`): `selfcal.rounds` rounds of a gemclean image (the input column
  first, the output column after), its model images predicted into `selfcal.model_column`
  (`rang.core_model.write_model_data`), one term solved on `selfcal.input_column` against it and
  applied into `selfcal.output_column`, then a final image. One term per round, the last repeating
  (CARACal's `gain_matrix_type`): `Sp` (phase, QuartiCal `phase`), `Sa` (amplitude and phase,
  `diag_complex`) and `Sd` (CARACal's `Fslope`, QuartiCal `delay_and_offset`, started at zero
  delay); default phase then amplitude. An integer `solint` is N integrations from each scan start
  (CARACal's timeslots), `Ns` CASA's seconds bins; `freqint` N channels for Sp and Sa. Solves are
  chunked within `data.memory_limit_gb`; `selfcal.gain_clip` flags solutions, `selfcal.minuvw_m`
  drops short baselines, new key `selfcal.refant`. `CORRECTED_1GC` is copied from `apply.column`
  after this run's apply. Solutions go to a QuartiCal gain store per round. New module
  `rang.cal_selfcal`; `rang.cal_gain`'s chunked solve takes channel chunks. `complex`
  self-calibration terms are refused (`refant: auto` in selfcal was refused too, until item 27).
- New: `rang-core calibrate` runs the K, G, B, A and F terms and the polarisation terms Gpol,
  KCROSS, Xf and Df within `data.memory_limit_gb` (`research/w3b-chainchunks.md`): each solve reads
  its field in chunks of whole solution intervals (B, Xf and Df also in channels of one interval),
  pre-applied on whole rows, with the result of the one-call solve bit for bit. The stop test of the
  G, B and K kernels is replayed over the chunks from new counted kernels (`rang._core.cal_gain_trace`,
  `cal_delay_trace`, `cal_delay_offset_trace`; Rust `diag::solve_counted`, `delay::solve_counted`,
  `delay_offset::solve_counted`), Df's gauge test is found exactly over the chunks, and the A step's
  Tricolour pass flags in blocks of baselines on each group's time grid. `preflight` no longer refuses
  these terms above the limit; it refuses only a solution interval (B, Xf, Df: one channel of one)
  that does not fit, naming the GiB. The library functions take a `budget` (default: one chunk, as
  before). P's angles come from a table per unique time and antenna (`rang.cal_pol.angle_table`,
  `table_angles`), so `applycal(parang=True)` and the polarisation solves hold no per-row angle array.
  New module `rang.cal_chunks`. The `extendflags` step (`rang.flag_extend.extend_ms`) splits a 60 s chunk
  larger than its batch into blocks of whole baselines, with the same flags.
- New: `refant: auto` and `calibrate.polcal.extendflags: true` run in `rang-core calibrate`
  (`research/e0-refant-extend.md`). `auto` is CARACal's `get_refant` (`rang.cal_refant`): the
  first three antennas **by name** within `calibrate.refant_maxdist` (1000 m) of the array centre
  whose every baseline is at least `calibrate.refant_minbase` (150 m); flags play no part, as in
  CARACal's code (its comment says fewest flags). It is chosen once before anything is written, and
  the stage stops when no antenna qualifies. `extendflags` is CASA's `flagdata(mode='extend')`
  with CARACal's settings (`ntime='60s'`, `combinescans`, `growtime` and `growfreq` 80,
  `growaround`, `flagneartime`, `flagnearfreq`, `extendpols`; `rang.flag_extend`, Rust kernel
  `core/src/flag_extend.rs`), run before the polcal solves on the Gpol, KCROSS and Xf fields and then
  the Df fields, within `data.scans`. The two new keys change the calibrate stage hash, so a
  calibrate stage finished earlier reruns once with `--force`.
- New (research, task F2, `research/f2-flagger.md`): `rang.f2flag`, a 2,785-weight per-baseline
  convolutional RFI flagger (features and network in NumPy/JAX, training in JAX on CPU), its Rust
  inference kernel `rang_core::cnnflag` (`rang._core.cnnflag_logits`, rows in, logits out, parity with
  JAX tested), and `rang.f2flag_sim`, simulated MeerKAT L-band scans on LUNO's window with RFI of known
  mask from `rang.simtruth` (F2's seeds registered in `simtruth.SEEDS`). Not wired into `rang-core
  flag`; weights are run outputs, not shipped.
- New: `gemclean` writes the model column after imaging, as WSClean 3.7 does (`-update-model-required`,
  the default; `-no-update-model-required` leaves the MS unwritten), and has WSClean's `-predict` mode
  and `-model-column` (`research/g6-predict.md`). The model images (`<name>-model.fits` or
  `<name>-000k-model.fits`, gemclean's or WSClean's) are predicted with the gridder at the MS's own
  channels into every selected row (field, data description 0, cross-correlations; flags play no part):
  XX = YY = I, XY = YX = 0. An added column is TiledShapeStMan and starts at zero, as WSClean's does.
  `rang-core image` with `image.write_model: true` writes MODEL_DATA through W1's write-back with the
  same predictor (`rang.core_model`, `rang._core.gemclean_predict`), and always runs gemclean with
  `-no-update-model-required`. The scripts in `examples/` that image shared data now pass
  `-no-update-model-required`.
- New: `gemclean -scans <list>` and `-unit-weights` (rang's own options). gemclean now falls back to WEIGHT
  as WSClean does: WEIGHT_SPECTRUM is read only when row 0 holds a cell of the data's shape
  (`research/w6-imaging-inputs.md`). `rang-core image` passes `data.scans` and `data.weights: uniform`
  to these options. It no longer refuses either of them, nor a declared WEIGHT_SPECTRUM with unwritten
  cells, and it writes nothing into the MS for uniform weights. An imaged field with no rows in
  `data.scans` is refused.

- New: the Stimela2 recipe `recipes/rang-chain.yaml` runs `rang-core flag`, `calibrate`, `apply`
  and `image` in order on one configuration and MS, with the cabs `rang-flag`, `rang-calibrate`,
  `rang-apply` and `rang-image` in `recipes/rang-cabs.yaml`; each cab runs the console script
  (`research/w5-stimela.md`). The recipes `recipes/core-*.yaml` are unchanged in their steps and
  now start with `# rang-recipe: research`: they replay frozen campaigns. `tests/test_w5_recipes.py`
  checks the marker on every recipe and the cabs' arguments against the commands.
- New: `rang-core calibrate` runs the polcal section's Gpol, KCROSS, Xf and Df (CARACal's strategy 1,
  `rang.cal_pol`; `research/c6w-polwire.md`) after the primary and secondary terms, and `rang-core
  apply` corrects by the parallactic angle with `apply.parang: true` (after the tables, as CASA's
  `parang=True`; `rang.applycal.applycal(parang=True)`, angles per field independent of the
  chunking). New keys: `calibrate.polcal.model` (`nrao`: CARACal's `nrao_xcal.yml` 3C286 or 3C138
  written to MODEL_DATA on the polcal fields; `column`), `calibrate.polcal.frame` (`casa` default),
  KCROSS `estimator` (`casa` default, `refined`), Df `min_data_fraction` (off by default; CASA has
  no such rule). Df's table is clipped at CARACal's 0.6 by default. `feed_angle_rotation` now sets
  the receptor angle used for P, in memory (CARACal sets it in FEED); FEED is not rewritten. Applying
  polarisation tables without `apply.parang`, `preavg`, Gpol `calmode: ap` and `extendflags: true`
  (not ported, no owner) are configuration errors; nothing is refused for C6a, C6b or C6c any more.
  The defaults of C6's open decisions are provisional.
- New: `rang.cal_pol`, the polarisation terms in CARACal's order (`research/c6-polterms.md`): `gpol`
  (phase-only G with the parallactic angle), `kcross` (CASA's cross-hand delay FFT), `xf` (CASA's
  cross-hand phase), `df` (the linearised leakage by least squares with CASA's subtractive reference),
  `clip_df`, `parallactic_angles`/`row_angles` (CASA's frame by default, provisionally; `frame='rang'`
  keeps the geodetic one), `rotate` and `apply` (tables, then P). Rust kernels
  `core/src/cal/parang.rs`, `crosshand.rs`, `leakage.rs`; `cal/apply.rs` and `formats/caltable.py`
  now apply `Kcross Jones` and `Xf Jones` tables. Wired into `rang-core calibrate` and `apply` by
  task C6w (the entry above).
  `rang.simtruth` gains the versions `poldx` and `polholdout` (CASA's parallactic frame, a leaking
  reference antenna); the other versions are unchanged.
- New: `rang-core calibrate` runs CARACal's cross-calibration terms K, G, B, A and F in C1's order
  (`research/c2e-calibrate.md`). The config's `calibrate.primary` and `calibrate.secondary` terms
  go to `rang.cal_chain.run`: K (`delay_and_offset`), G and B with their listed tables pre-applied,
  written as CASA tables in the run directory; F appends a G solved on the secondary against a
  unit point model to a copy of the primary's last G, then `fluxscale`, and the fitted flux densities
  go into the summary; A applies the section's last table of each type to its fields
  (CORRECTED_DATA, `calflag`) and runs the Tricolour port on the corrected data, OR-ing its flags
  into FLAG (CARACal runs tfcrop there). `rang-core apply` applies these tables through
  `rang.applycal` with each target's `interp` and `gainfield`. calibrate now saves and restores a
  flag version like the other writing stages. A K table applied without a G or F is reported:
  its phase offsets are left for G. Refusals no longer name C2a to C2d; what the `complex` term
  never takes is a configuration error pointing to the K, G and B terms. `refant: auto`,
  `solnorm: true` and `calmode: a` are refused as not ported.
- Changed: `rang.cal_gain.gaincal`, `rang.cal_delay.gaincal`, `rang.cal_bandpass.bandpass` and
  `rang.applycal.applycal` take `scan` (a list of SCAN_NUMBERs); the solves take
  `weight_column=None` for unit weights and read a WEIGHT column per channel. Defaults are
  unchanged. `rang.simtruth` has a held-out version `holdout128` (new seeds).
- Added: polarised calibrator models (task C7a, `research/c7a-polmodels.md`).
  `rang.calmodels.Manual` takes CASA `setjy(standard='manual')`'s full form, `fluxdensity=[I, Q,
  U, V]`, `polindex`, `polangle` and `rotmeas` (referenced to `reffreq`, as CASA), following
  CASA's tabular and spectral-index paths, and writes all four correlations in the sky frame
  (`XX = I+Q`, `XY = U+iV`, `YX = U-iV`, `YY = I-Q`; no parallactic angle, as `setjy`).
  With one `spix` term it copies CASA's TOPO-to-LSRK conversion of channel 0
  (`calmodels.lsrk_over_topo`, astropy; recorded in the receipt), within 1.5e-7 of CASA.
  `calmodels.NRAO_XCAL` and `caracal_xcal()` hold CARACal's 3C286 and 3C138 models.
  `rang-core calibrate` accepts `calibrate.model.flux_jy` with Q, U, V and the polarisation
  keys for `source: manual`; `polindex` without `polangle` (or the reverse) and the polarisation
  keys with another source are refused. Polarised sky-model components stay refused.
- New: `rang-core flag`, `calibrate` and `apply` run within `data.memory_limit_gb` (default 8 GiB of
  resident memory) by chunking by time and row (`rang.core_chunks`, `research/w3-chunking.md`):
  the flagger takes blocks of baselines of a field and scan on the group's whole time grid
  (`core_flag.flag_rows(time_grid=...)`), the `complex` solve takes chunks of whole solution
  intervals (time bins, or frequency bins of one time bin) and replays the solver's global stop
  test over them, so gains equal the one-call solve bit for bit, and apply and the models use row
  chunks of the limit. Results do not depend on the limit or on `data.chunk_rows` (now a cap on
  the rows of every chunk), so neither enters a stage's configuration hash. A limit too small for
  the process, one baseline of a scan or one solution interval is refused before anything is
  written, naming the GiB needed. No visibility column is read whole by the three stages;
  `cal_gain` and `cal_delay` read only the rows of the field they solve. The K, G, B, A and F
  terms are not chunked yet: a field they would read beyond the limit is refused, naming the GiB
  needed.
- New: A1's generator has a `w3` version (64 antennas, 4096 channels) and `--chunk-ints`.

- Changed: `rang-core flag`, `calibrate`, `apply`, `image` and `config check CONFIG MS` check the
  Measurement Set per stage before anything is written and report every problem at once, each
  naming its reason (`research/w4-unsupported.md`). Refused: several data descriptions in use
  (split one spectral window out first), circular, single or reordered correlations, two
  correlations for `calibrate` and `apply` (the complex term needs four), no FLAG or FLAG_ROW,
  no weights for `calibrate` (unless `data.weights: uniform`) or `image`, a FIELD_ID without a
  FIELD row, a named field or a `data.scans` selection with no rows, a FIELD name of several
  fields in `image.fields`, and `image` when `data.scans` leaves out a scan of an imaged field
  (gemclean has no scan selection), on a data description other than 0 or with a
  WEIGHT_SPECTRUM column whose cells were never written. Two linear correlations (XX, YY)
  are now flagged and imaged. Autocorrelations are flagged and corrected but left out of the
  `complex` solve; `calibrate` reads WEIGHT when row 0 of WEIGHT_SPECTRUM has no cell of the
  DATA shape, and `image` refuses such an MS because gemclean would stop on it.
  `data.weights: uniform` for imaging is still refused, now naming W4 (an owner decision).
- New: `rang.cal_fluxscale`, the flux-scale term F (`research/c2d-fluxscale.md`). `fluxscale(caltable,
  reference=..., transfer=...)` is CASA's `fluxscale` on a G table, with its statistics in the Rust
  core (`core/src/cal/fluxscale.rs`): per-antenna mean amplitudes, the median ratio to the reference
  (casacore's median rule), `fd = ratio²` and CASA's error, `gainthreshold`, several reference
  fields, `refspwmap`, and the weighted spectral fit across windows (`fitorder`); it returns the
  flux-scaled table and a record shaped as CASA's. `bootstrap(ms, primary, secondary)` runs
  CARACal's F step: G on the secondaries against a unit point model (`smodel_array`), appended to a
  copy of the primary's table (`append`), then `fluxscale`. Selections by antenna, time or scan and
  `incremental=True` are refused. Measured against CASA 6.7.6 `fluxscale`: the same flux densities,
  errors and F tables as CASA on CASA's own G tables (fit errors at `fitorder=2` within 2.6e-5), and
  within 4e-4 end to end.
- Changed: `rang.cal_gain.gaincal` takes `spw` to solve one window of a multi-window MS (tables are
  pre-applied on single-window data only).
- Changed: `examples/a1_simtruth.py generate` takes `--seeds` and `--gcal-flux`, `--gcal-spix`,
  `--gcal-reffreq` (the default versions are unchanged).

- New: `gemclean -channels-out N`, `-join-channels`, `-fit-spectral-pol N`, `-channel-range S E`,
  `-mf-weighting`/`-no-mf-weighting` and rang's own `-average-channels N`, as WSClean 3.7 has
  them: output channels grouped as WSClean groups them, MF weighting by default with joined
  channels, a joined minor loop that picks on the weighted sum of the channel residuals and puts a
  component in every channel (GeMClean's exact value per channel, then WSClean's ordinary polynomial
  fit in `nu/nu_ref - 1`), and per-channel `<name>-0000-<kind>.fits` and weighted
  `<name>-MFS-<kind>.fits` images. `-fit-spectral-log-pol`, `-deconvolution-channels` and squared
  joining are refused. One output channel is byte-identical to before. `rang-core image` passes
  `channels_out`, `join_channels`, `fit_spectral_pol` and `average_channels` to gemclean instead
  of refusing them (`research/g3-spectral.md`).
- New: `rang.applycal.applycal(ms, gaintable, interp, gainfield, calwt, field)`, CASA's
  `applycal` on a Measurement Set: row chunks through `rang.core_writeback` (a flag version first),
  the Rust kernel per field and data description, CORRECTED_DATA (added as `clearcal` does when
  absent), FLAG OR'd, and with `calwt` on a G, T or B table WEIGHT and WEIGHT_SPECTRUM reset from
  SIGMA and scaled as CASA does (K, Df and general Jones terms leave weights alone). Field maps
  `''`, a field name and `nearest` as CASA's. Measured against CASA 6.7.6 `applycal`
  (`research/c4b-apply-ms.md`).
- Changed: the apply kernel (`rang.cal_apply`) writes cells under a one-sided diagonal solution flag
  as CASA does (the good side still applied), tracks phases over the two slots it interpolates
  between, and uses casacore's linear-interpolation formula; new `cal_apply.apply_jones` applies
  a general 2×2 term on its own solution bins.
- New: `rang-core apply` applies the `complex` terms of `rang-core calibrate` to the fields they were
  solved on, into CORRECTED_DATA; `rang-core calibrate` writes `setjy`, `manual` and `lsm` models to
  MODEL_DATA through `rang.calmodels` and solves against them. Applying a complex term to another
  field and polarised models are refused, naming C2a and C7a.

- Changed: `rang.cal_delay` solves K as QuartiCal 0.2.7's `delay_and_offset` by default (a delay
  and a free phase per antenna and hand, `core/src/cal/delay_offset.rs`), with rang's offset start
  (the FFT peak's phase, `offset_start=True`; `False` is QuartiCal's estimator exactly) and a delay
  error with the offset marginalised; `kind="delay"` keeps C2b's term. It meets CASA's
  `gaincal(gaintype='K')` with nothing pre-applied, as CARACal solves K. The `K Jones` table holds
  the delays only; the offsets are in `DelaySolution.offsets` and G absorbs them
  (`research/c2c-bandpass.md`).
- New: `rang.cal_bandpass`, the bandpass B: `diag_complex` per channel in Rust with CASA's rules per
  channel (`minblperant`, `minsnr`, the reference antenna) and CASA's `fillgaps`
  (`core/src/cal/bandpass.rs`), `bandpass(ms, ...)` as CASA's `bandpass(bandtype='B')` (defaults
  `combine='scan'`, `fillgaps=0`), writing CASA `B Jones` tables. `rang.cal_chain.primary` solves
  the primary calibrator's K, G, B in CARACal's order, each with the earlier tables applied.
  `rang.simtruth` has a `holdout256` version (new seeds, 256 channels) (`research/c2c-bandpass.md`).
- New: `rang.cal_delay`, the delay term K in Rust (`core/src/cal/delay.rs`): QuartiCal 0.2.7's
  `delay` kernel with its FFT initial estimate (FFT, then Gauss-Newton over all baselines).
  `solve(...)` on arrays; `gaincal(ms, ...)` as CASA's `gaincal(gaintype='K')`, with CASA's
  solution intervals, pre-applied tables through `rang.cal_apply` (SIGMA weights then, as
  `rang.cal_gain`) and CASA's K referencing (to the first refant, no flex or strict, no `minsnr`
  or `minblperant`, which CASA's K does not apply); `to_caltable` writes a CASA `K Jones` table
  (float32 delays in ns, the one-channel window at the band centre), which `rang.cal_apply`
  applies. It matches CASA only with a G pre-applied; without one, antenna phases bias it
  (`research/c2b-delay.md` section 6; the K model is an owner decision). `rang.simtruth` has a
  `delay50` version (delays of 1-50 ns, 256 channels) (`research/c2b-delay.md`).
- Changed: `gemclean` needs far less memory, with byte-identical images (task G2,
  `research/g2-memory.md`). It reads the Measurement Set at the exact size with Stokes I in single
  precision, compacts in place, keeps no copy of the gridding weights, holds single-precision
  visibilities as read, forms each residual in the gridder's sorted values instead of a
  visibility-sized buffer, forms the 2n PSF before the plan of the image grid and frees it after
  the beam is built. Peak RSS on the ESO 137-006 pilot at 512 channels went from more than 24 GB
  (about 32 GB estimated) to 19.7 GB; at 256 channels from 18.4 to 12.2 GB; on 2048² simulated
  skies from 3.46 to 2.99 GB.
- New: `gemclean -memory-report` prints the heap held per phase of a run (read, weights, PSF,
  beam, each major cycle) and the main buffers' sizes; `-report.json` carries the same under
  `memory` (`research/g2-memory.md`). Images are unchanged.
- New: `rang.calmodels`, calibrator models written to `MODEL_DATA` as CASA's `setjy` writes them
  (C1 term T0). `set_model(ms, field, spec)` takes a flux-density standard of `rang.fluxstd`, a
  `manual` model (flux density, reference frequency, log10 spectral terms), per-channel Stokes rows
  (`PointStokes`), or a component list such as CARACal's `pks1934-638.lsm`, predicted through
  `core.predict_components`. It writes through `rang.core_writeback` and leaves other fields'
  rows as they are. Polarised `manual` models are refused until C7a (`research/c3a-models.md`).
- New: commands for your own Measurement Set, `rang-core flag`, `calibrate`, `apply`, `image`,
  `selfcal` and `run CONFIG MS`, driven by one YAML configuration (schema `rang-config`, version
  1; `rang-core config defaults` prints every key with its default, `rang-core config check`
  validates). `flag` runs the Tricolour port per field and scan and writes FLAG; `calibrate`
  solves the `complex` term and writes a QuartiCal gain store; `image` runs `gemclean`. The rest
  of CARACal's chain (K, G, B, F, polarisation terms, apply, self-calibration, multi-channel and
  polarised imaging) can be written in the configuration and is refused with the task that adds
  it. A run directory (`<ms>.rang-run`) keeps the state, so `run` skips finished stages and
  resumes at a failed one. Flags are saved as the CASA flag version `rang_original` before the
  first write, and as `rang_<stage>_<time>` before each stage writes (`research/w2-commands.md`).
- Changed: the research stages moved under `rang-core research` (for example `rang-core research
  flags compare`); the old top-level forms now say where they went. PyYAML is a dependency.
- New: `rang.cal_gain`, the gain term G in Rust (`core/src/cal/diag.rs`, `reference.rs`):
  diagonal complex (`calmode='ap'`) and phase-only (`'p'`) solves ported from QuartiCal 0.2.7's
  `diag_complex` and `phase` kernels, with CASA's solution intervals (`solint`, `combine`),
  `uvrange` (metres), `minblperant`, `minsnr` and reference antenna (`flex`, `strict`); earlier
  tables are pre-applied through `rang.cal_apply`, and the result is a CASA `G Jones` table
  (`research/c2a-gain.md`).
- `tools/check-all.sh` has a new last step, `gain-hashes` (`tools/gain_hash_gate.py`): it recomputes
  the archived `complex` gains (`4ed2aa89…`, `7b370c13…`) and core phase 2's LUNO convergence, and
  fails on any change. The archived inputs are found in `$RANG_ARCHIVE_OUTPUTS`, `outputs/` or
  `~/Github/rang/outputs`; `RANG_GAIN_HASHES=optional` skips the step on a host without them.

- New: `rang.core_writeback`, write-back to an existing Measurement Set. `WriteBack` adds
  `MODEL_DATA`, `CORRECTED_DATA` (or any data column) and `WEIGHT_SPECTRUM` as CASA's `clearcal`
  adds them, writes any column, `FLAG` and `FLAG_ROW` in row chunks, saves the original flags as a
  CASA flag version (`rang_original`) before the first write, and refuses to start after an
  interrupted session until the flags are restored (`restore_flags`). `rang.formats.flagversions`
  now saves in chunks, atomically, and gains `restore`. CASA, WSClean, python-casacore and dask-ms
  read the written columns (`research/w1-writeback.md`).
- The core table writer now writes a tiled column's header through a temporary file and a rename,
  so a process killed during a flush cannot leave it truncated. The bytes written are unchanged.

- New: `rang.simtruth` and `examples/a1_simtruth.py`, a simulated MeerKAT L-band observation in
  full polarisation with known truth. It has K, B, G, KCROSS, Xf, linear Df and parallactic
  rotation, a self-calibration residual, RFI with bit masks, and thermal noise of known σ, and is
  written as a Measurement Set through rang's table writer. There are two versions: small (16
  antennas, 64 channels, 41 MB) and full (64 antennas, 256 channels, 35.8 GB). CASA
  `applycal` with tables made from the truth inverts it within class C
  (`research/a1-simtruth.md`).
- New: `rang.cal_apply.apply`, a Rust kernel (`rang._core.cal_apply`) that corrects or corrupts
  visibilities in memory by CASA K, G, T, B and Df tables, with `applycal`'s `linear` and `nearest`
  interpolation in time and frequency and its `calflag` flags, including how Df flags and
  substitutes bad leakages (`research/c4a-apply.md`). KCROSS, Xf and the parallactic angle are
  refused until their steps. Weights are not changed and nothing is written to a Measurement Set yet.
- New: `gemclean -beam-band`, off by default. Resyncs use the beam's spectrum only as far as the
  longest baseline and the w-term reach. Images differ slightly from flag off. Over 12 interleaved
  pairs with coarse gridding (`-single -wgridder-accuracy 1e-4`) it saved 11-16 % of the wall on
  two simulated skies and 4-5 % on a third (`research/gemclean-speed.md`).
- The root crate and binary are now `rang-sim`, `rang.toy_output` is now `rang.sim_output`,
  `RANG_TOY_BIN` and `RANG_TOY_LIB` are now `RANG_SIM_BIN` and `RANG_SIM_LIB`, and
  `examples/toy.py` is now `examples/pointing_sim.py`. No aliases are kept. Output bytes are
  unchanged. Receipts are `rang.receipt` version 4.
- `gemclean` takes w-planes in groups of 4, within 2 GiB of grids. Results are unchanged; peak
  memory rises (2.84 to 3.38 GB on one simulated job). Other callers of the exact gridder stay at
  one plane, because larger groups were measured only on gemclean. `RANG_WGRIDDER_PLANE_GROUP`
  overrides either default.
- New: the reference imager `gemclean` and its binary, and the flagged Gram operator. Their
  speed figures are provisional.
- New: `gemclean -stop-rule certified`, a minor-cycle stop rule with Lean-proved consequences
  (`research/stop-rule-theorem.md`). It costs about three times the default's major cycles and a
  table of about 100 gridder calls, so it is not the default, and the default's images are unchanged.

## 0.1.0 (2026-11-02)

First release. A research demonstrator for MeerKAT calibration and
flagging, not an operational calibrator; no advantage over the state of
the art is claimed.

**The Rust core.** The calibration chain of the gain-TV flagging
experiment runs in one Rust core, reached from Python through the PyO3
extension `rang._core`: fused visibility statistics, a QuartiCal-style
gain solver, the component predictor, blosc decoding of the public zarr
stores with HTTP range reads, the Tricolour strategies and SumThreshold,
WSClean imaging weights, a w-stacking gridder and the exact wgridder, a
read-only Measurement Set reader and a casacore table writer that creates
Measurement Sets and CASA calibration tables byte-identical to casacore
3.8.1 and CASA 6.7.6 (bar uninitialised memory). Every port is checked against its upstream oracle
(QuartiCal, Tricolour, AOFlagger, WSClean, python-casacore, casacure) or
against the archived results of the frozen campaigns.

**Simplification and speed.** The solver, the fused pass, SumThreshold and
the gridder run in parallel; the w-stacking gridder and FFT also run on the
GPU through `wgpu` behind the `gpu` feature. The ctypes backend is gone:
importing `rang` or calling a kernel never runs Cargo, and the extension
releases the GIL around every kernel. One command line, `rang-core STAGE
VERB`, writes a `rang.receipt` per call and a `rang.archive` per run. The
frozen QuartiCal and Stimela campaigns, their containers and modules moved
to `history/`; the package keeps verbatim extracts of what the core uses.
The package was renamed from `rangtoy` to `rang` (distribution
`rang-core`). `rang-core --version` and `rang.__version__` report the
version.

**Wheels and CI.** One abi3 wheel per platform for CPython 3.10 and newer:
Linux x86_64 and aarch64 (manylinux_2_28), macOS arm64 and x86_64, and
Windows x86_64, each tested on CPython 3.10 and 3.14 on its own OS with
Cargo absent, with casacure as a second oracle of the table reader and
writer. A `v*` tag that equals the `pyproject.toml` version attaches the
wheels and the sdist to a GitHub release and publishes them to PyPI by
trusted publishing. The sdist holds only the crates, the Python package
and the tests the wheel runs.

**Documentation.** A Sphinx site (<https://pythonic.nl/rang-core/>)
with installation, concepts, the command line, the API reference and the
research story; five executed tutorial notebooks (data and rank, flagging
step by step, gains and TV, imaging, the flagging experiment) and two
science notebooks (the gain-TV verdict; beam and pointing).

**Science verdicts.** The gain-TV-guided flagging experiment is closed as
null: on LUNO 1934−638 at four stations and across the whole array, on
PKS 1830−211 under a stored and a scalar model, under CARACal's field model
and with a closure-invariant arm, 90 pre-registered calls gave 64 null and
26 undecidable, none better or worse, and the method costs 4.6–5.9× the
baseline. The solver study changed no default (the QuartiCal issue 452
weight fix is opt-in through `RANG_SOLVE_OPTIONS`). For beam and pointing,
the SARAO holography beam is the reference and the SARAO/SKA Gaussian
pointing fit is ported bit-exact; the identifiability survey finds
per-antenna pointing and squint constrainable on the calibrator and ESO137
data, array-common pointing and ellipticity on the ESO137 track, and beam
width nowhere. Pointing self-calibration against those baselines is the
next step. Negative results are kept in `research/`.
This covers a gain-TV-guided threshold policy; a flagger trained on gain TV
is a separate question, not yet tested.

**Provenance and the wheel (wave 4 fixes).** Receipts (`rang.receipt`
version 3) record every result-affecting `RANG_*` variable from one registry
and the package source; the solver takes its options as an argument; `commit`
is null outside a checkout (W4-1). The closure and flux-standard kernels run
in the extension, so no kernel call builds with Cargo and the wheel is
self-contained (W4-3).
