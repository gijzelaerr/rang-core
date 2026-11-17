# Upstream report status, 2026-11-13

Read-only check (`glab`, `gh`) on 2026-11-13; nothing was filed or commented. All 22 U5 filings
([manifest](upstream-issues/u5-manifest.md)) were posted 2026-11-12 around 14:45 UTC, so most are one day old.
Rows 1, 24, 25 were never posted (row 1 for the owner to send; 24 and 25 are CASA, never sent).

## 1. Fixes rang is waiting for

| MR | Fixes | State 2026-11-13 | In a release? |
| --- | --- | --- | --- |
| [wsclean !1068](https://gitlab.com/aroffringa/wsclean/-/merge_requests/1068) `CalculateMsLimits` v bound | #208 | open, not merged, no discussion; opened 2026-11-12 by Offringa (assigned) | No. Latest WSClean tag is v3.7 (2026-02-14) |
| [radler !238](https://git.astron.nl/RD/radler/-/merge_requests/238) linear peak finding | #207 | open, not merged; Offringa pushed 3 more commits 2026-11-12 (last 20:17 UTC: "Lower sensitivity of rm deconvolution test"); only a bot review note | No. Latest Radler tag is v1.2.0 (2026-10-12), older than the MR |
| [wsclean !1070](https://gitlab.com/aroffringa/wsclean/-/merge_requests/1070) docs for #207 | #207 | open | No |

No release carries either fix, so nothing is switched. The next WSClean release after v3.7 (and a Radler
release after v1.2.0 that WSClean pins) is the trigger; check
`glab api projects/aroffringa%2Fwsclean/repository/tags` and the radler tags page weekly.

### Plan once a release carries them (not done yet)

1. Build or obtain that WSClean release (with its Radler); record version, commit and build flags in `research/`.
   Confirm from the release's source that `msprovidercollection.cpp` uses `v` for `y` and that Radler's
   GenericClean peak finding is linear.
2. Keep the current oracle outputs of G2, G7, G9 as the "old binary" reference (v3.7); do not overwrite.
3. In `core/src/grid.rs` change `w_limits` to test `v` with the y bound; in `core/src/gemclean/multiscale.rs`
   change `theoretic_beam` likewise. (`theoretic_beam` is also in `core/src/grid.rs` per the task; grep both.)
   Make it a switch by oracle version if the old binary must stay reproducible.
4. Rerun the G2, G7, G9 oracle cases (same seeds and settings as the original runs, under `tools/heavy_lock.py`,
   shared job with honest slots/memory) against the new binary. Expected: G2/G7 differ only where the grid
   undersamples the longest v baselines or pixel_size_x != pixel_size_y, so on the MeerKAT test sets the
   w range and theoretical beam should be unchanged. G9: only the non-subminor Hogbom path changes.
5. Pass if the frozen tolerances of those gates hold against the new binary; if the old and new binaries
   differ on a case, record both and the cause. Record as a dated note, update `u5-upstream.md`, STATE.md.
6. Run `python -m rang.check` after `maturin develop --release`; log wall times in `research/tool-timings.md`.

## 2. U5 filings

Status as of 2026-11-13; "replies" are comments by anyone but us.

| # | Issue | State | Replies | Next action |
| --- | --- | --- | --- | --- |
| 2 | [RD/schaapcommon#1](https://git.astron.nl/RD/schaapcommon/-/work_items/1) Fit2DGaussianCentred quadrant | open, status "To do" | none | wait; WSClean beam size is related, check again in a week |
| 3 | [wsclean#207](https://gitlab.com/aroffringa/wsclean/-/work_items/207) join-polarizations | open | Offringa: thanks; docs fixed in !1070, Radler consistency in radler !238 | follow both MRs; close on release |
| 4 | [wsclean#208](https://gitlab.com/aroffringa/wsclean/-/work_items/208) MsLimits v bound | open | Offringa: "genuine bug", fix in !1068 | follow !1068; rang rerun plan above |
| 5 | [wsclean#209](https://gitlab.com/aroffringa/wsclean/-/work_items/209) save-source-list help | **closed** 2026-11-12 | Offringa: will not list all combinations in the help; the error message is enough | none. Accepted as wontfix; consider our docs noting the restrictions |
| 6 | [aoflagger#44](https://gitlab.com/aroffringa/aoflagger/-/work_items/44) sumthreshold_masked args | open | none | wait; Offringa answered the WSClean ones within hours, so check again |
| 7 | [aoflagger#45](https://gitlab.com/aroffringa/aoflagger/-/work_items/45) SumThresholdMissing xright | open | none | as #44 |
| 8 | [aoflagger#46](https://gitlab.com/aroffringa/aoflagger/-/work_items/46) Lua doc notes | open | none | as #44 |
| 9 | [casacore#1550](https://github.com/casacore/casacore/issues/1550) uninitialised bytes | open | none | wait; casacore latest release is v3.8.2, no fix yet |
| 10 | [casacore#1551](https://github.com/casacore/casacore/issues/1551) ISM refcount | open | none | wait |
| 11 | [casacore#1552](https://github.com/casacore/casacore/issues/1552) TiledCellStMan range | open | none | wait |
| 12 | [casacore#1553](https://github.com/casacore/casacore/issues/1553) MemoryStMan reopen | open | none | wait |
| 13 | [casacure#42](https://github.com/tmolteno/casacure/issues/42) tiled create | open | none | wait |
| 14 | [casacure#43](https://github.com/tmolteno/casacure/issues/43) measures relabel | open | none | wait |
| 15 | [casacure#44](https://github.com/tmolteno/casacure/issues/44) TaQL gaps | open | none | wait |
| 16 | [casacure#45](https://github.com/tmolteno/casacure/issues/45) unwritten cells | open | none | wait |
| 17 | [casacure#46](https://github.com/tmolteno/casacure/issues/46) LICENSE file | open | none | wait |
| 18 | [celestial-eop-data#1](https://github.com/gaker/celestial-eop-data/issues/1) build.rs date | open | none | wait |
| 19 | [dask#12716](https://github.com/dask/dask/issues/12716) ProgressBar | open, label "needs triage" | none | wait for triage |
| 20 | [katdal#400](https://github.com/ska-sa/katdal/issues/400) release request | open | Ludwig Schwardt: opened a branch last month, sidetracked | wait; recheck for a katdal release after 0.23 |
| 21 | [carta-python#192](https://github.com/CARTAvis/carta-python/issues/192) driver_path | open | none | wait (busy repo) |
| 22 | [carta-python#193](https://github.com/CARTAvis/carta-python/issues/193) __del__ double close | open | none | wait |
| 23 | [casadocs#205](https://github.com/casangi/casadocs/issues/205) 1934-638 flux standards | open | none | wait. casadocs is CASA-adjacent but the issue is already filed; file no more there |
| 1 | Obit dim[5] note | not posted | n/a | owner decision to send |
| 24, 25 | CASA tickets | not sent (owner decision) | n/a | none; never contact CASA/NRAO |

Summary: 22 posted; 3 with a maintainer reply and an MR (#207, #208, plus #209 closed as won't fix), 1 reply
without a fix (katdal), 19 with no reply yet after about one day.

Not checked: private activity, pull requests linked from other repositories, and emails.
