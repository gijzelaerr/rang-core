# Rang core: parallel work plan and handoff

Written 2026-10-30 as the handoff before clearing the coordinating session.
Status: **wave 1 merged** 2026-10-29 (all eight tasks done; outcomes in
STATE.md and `core-<slug>.md`); wave 2 next. Read
this, [STATE.md](STATE.md) and [stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
section 9 first.

## Where things stand (measured, all on origin/main at `9500c34`)

- Licence: GPL-3.0-or-later (user decision 2026-10-29). Open: whether
  Tricolour and Crystalball are GPL-2-only.
- `core/` Rust crate with a C ABI loaded through ctypes
  (`python/rangtoy/core.py`): fused statistics pass ([core-phase1.md](core-phase1.md)),
  QuartiCal `complex` solver port ([core-phase2.md](core-phase2.md)),
  africanus component predictor ([core-phase3c-a.md](core-phase3c-a.md)), blosc
  decoder with block-selective reads (`core/src/blosc.rs`,
  `rangtoy.core_zarr`, [core-section6.md](core-section6.md)).
- Core drivers reproduce the archived injections, actions, trend,
  prospective and signal stages ([core-phase3.md](core-phase3.md),
  [core-phase3-actions.md](core-phase3-actions.md),
  [core-phase3-trend.md](core-phase3-trend.md),
  [core-phase3b.md](core-phase3b.md), [core-phase3c-b.md](core-phase3c-b.md)),
  with the qualifications recorded there. The frozen Stimela recipes still
  call QuartiCal.
- The section 6 prototype runs from the LUNO zarr tiles with no MS and passes
  all eleven criteria on its second run (1.67 s excluding decode, 140 MB).
- Phase 4 (imager) was paused before its protocol: the verified WSClean
  3.6-1 Debian source is in `outputs/wsclean-3.6-1-source-20261029/`
  (SHA256SUMS there; Debian patches are build-only). Relevant code:
  `gridding/wstackinggridder.cpp`, `structures/imageweights.cpp`,
  `gridding/msgridder.cpp`, docs `doc/source/weighting_and_gridding_details.rst`.
  Defaults to honour: Kaiser–Bessel kernel of 7 pixels, 1023× oversampling,
  and rang passes `-no-min-grid-resolution`.

## Rules for every session

- Work in WSL. Own worktree and branch:
  `git -C ~/Github/rang worktree add ~/Worktrees/rang/core-<task> -b core/<task> origin/main`.
  Link inputs read-only: `ln -s ~/Github/rang/outputs ~/Worktrees/rang/core-<task>/outputs`
  and write only into fresh `outputs/<name>-<date>-NN` directories.
- Commit on the branch only; never push to `main`. The coordinator merges.
- Own files only: a new Rust module (and its C ABI in a new
  `core/src/ffi_<task>.rs` if needed), a new Python module
  `python/rangtoy/core_<task>.py` that registers its own ctypes symbols (as
  `core_zarr.py` does), examples, tests and `research/core-<task>.md`. Do not
  edit README, STATE, tool-timings, upstream-notes, the feasibility study,
  `core/src/lib.rs`, `core/src/ffi.rs` or `python/rangtoy/core.py`; put
  timings, upstream findings and the needed `pub mod` line in the task's own
  research file under "For the coordinator".
- Discipline as in phases 1–3: freeze the protocol in a commit before code;
  show the comparator passes on archive versus host reproduction before
  freezing; record failures as frozen and label post-hoc steps; time every
  tool run; run targeted tests while working and `bash tools/check-all.sh`
  once before the final commit; Rust 1.93; public PyPI only; commits as
  Gijs Molenaar <gijsmolenaar@gmail.com> with no AI attribution or
  co-author trailers.
- CPU: 16 cores shared; avoid running the full pytest suite more than once.

## Wave 1 (independent)

| | Task | Inputs and oracle | Done when |
| --- | --- | --- | --- |
| A | WSClean approximation sensitivity: rerun the 15 archived imaging jobs with varied kernel size, oversampling and w-layers in `rang-flagging-next-imaging:local` | `outputs/tv-next-imaging-wsl-20261029-01` checkpoints (`*-written.npz`), `results/gain-tv-next-imaging.json` | measured spread of template-fit fluxes, response fractions and closures, proposed phase 4 tolerances |
| B | Port WSClean Briggs/uniform weighting and Stokes I formation | WSClean `-store-imaging-weights` on the same jobs; WSClean source | weights equal WSClean's to a frozen tolerance |
| C | Port the WSClean w-stacking gridder: kernel, oversampling, w-layers, FFT, PSF, normalisation, FITS orientation | dirty and PSF FITS from WSClean on the same jobs | pixel differences reported; fits within A's tolerance |
| D | Tricolour: settle GPL-2-only or not first; if compatible, port SumThreshold and the CARACAL strategy steps | archived native controls in `results/gain-tv-caracal.json` | either a documented stop or flags reproduced |
| E | Read-only Rust MS reader (StandardStMan, TiledStMan) | python-casacore reads of the fixture and LUNO MSs | column-exact reads |
| F | Performance: solver inner loop, rank survey, blosc decode versus c-blosc | phase 2 and section 6 oracles | same results, measured speed-up |
| G | HTTP range-request fetch of the LUNO four-station slice from the RATT bucket | section 6 inputs and hashes | bytes and seconds against the 1,220 s whole-tile fetch |
| H | Core-native Stimela recipes and CLI beside the frozen ones | phase 3 archives | `goquartical` no longer needed by the core recipes |

## Wave 2 (after merging wave 1)

- I: imaging track replay on the core (needs A, B, C).
- J: PyO3/maturin packaging (touches every wrapper, so last).
- K: first real-data campaign on LUNO with the core (new science; needs its
  own protocol and the licence answer from SARAO or the observer).

## Coordinator

Merge branches one at a time onto `main`, resolve the shared-file edits
from each task's "For the coordinator" section, run `bash tools/check-all.sh`,
push, and update README and STATE.

## Open items for the user

- `~/Build/tmp/20261029-rang-core` holds a redundant scratch crate and its
  `target/`; the safety check refused to delete it, and it is safe to delete.
- Ben Hugo offered a full-resolution LUNO L-band dataset (requested
  2026-10-29 15:57 SAST); record it in `flagging-luno-candidate.md` and STATE
  when it arrives. Chat replies alone never change data or flags.
- Upstream observations in `upstream-notes.md` await approval; nothing filed.
