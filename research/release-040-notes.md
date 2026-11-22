# rang-core 0.4.0: release notes (draft for the GitHub release)

Drafted 2026-11-22 on branch `release-040` from the CHANGELOG's 0.4.0 section. The coordinator tags
`v0.4.0` after #42 step 1 is merged; the tag publishes the wheels to PyPI. Before tagging, replace the
two "OUTCOME PENDING" lines (Known limitations and the #42 row) with step 1's result.

---

**rang-core 0.4.0 (2026-11-22)**: `pip install rang-core==0.4.0`

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
- **#42 step 1** (learned minor-cycle proposals on real data): OUTCOME PENDING (the read lands on
  2026-11-22; filled in at the tag).
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
| 42 | DL4b: minor-cycle proposals | step 0 F; step 1 OUTCOME PENDING | [dl4b-step0.md](https://github.com/gijzelaerr/rang-core/blob/main/research/dl4b-step0.md) |
| 43 | DL4c: mask, quick-look, settings | closed 2026-11-22: stage 6 null, stage 9 headroom only, quick-look not started | [dl4c-mask.md](https://github.com/gijzelaerr/rang-core/blob/main/research/dl4c-mask.md) |
| 44 | DL4s: one-day screenings | moved to v0.5.0 | |
| 45 | DL5: combined learned selfcal | moved to v0.5.0 (needed a DL4 pass) | |
| 46 | DL6: retrain-a-stage procedure | procedure and dry run done; the agent test waits for a passed stage | [dl6-retrain.md](https://github.com/gijzelaerr/rang-core/blob/main/research/dl6-retrain.md) |
| 47 | WSClean 3.8 rebaseline | closed 2026-11-22: done (parity holds; 3.8 slower at `-j 1` minres) | [wsclean38-rebaseline.md](https://github.com/gijzelaerr/rang-core/blob/main/research/wsclean38-rebaseline.md) |
| 48 | Native L0 weights (`calwt`) | null: default stays `false` | [apply-calwt.md](https://github.com/gijzelaerr/rang-core/blob/main/research/apply-calwt.md) |
| 53 | K drops an antenna without a baseline to the refant | closed 2026-11-21: fixed (`refantmode: flex`) | [k-refant-53.md](https://github.com/gijzelaerr/rang-core/blob/main/research/k-refant-53.md) |
| 54 | Multiscale stops on a scale without a positive PSF peak | closed 2026-11-21: fixed (scale dropped with a warning) | [gemclean-54.md](https://github.com/gijzelaerr/rang-core/blob/main/research/gemclean-54.md) |

**At the tag** (owner and coordinator): close #42 if step 1 ends it, else move it to v0.5.0 with its
outcome; move #1, #24, #32, #40 and #46 to v0.5.0 with the outcomes above. #44, #45 and #34 are
already on v0.5.0.

Full changes: `CHANGELOG.md`, section 0.4.0. Known limits: https://pythonic.nl/rang-core/limits.html
