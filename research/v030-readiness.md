# v0.3.0 readiness tracker

Status, 2026-11-17: **release-ready except the four results still running** (E2-N and E3-A on nash, the
selfcal-defaults grid on branch `floor-4`, the E2-A 3b K follow-up on branch `e2a-3b-k`). The two
licence-notice findings B-01 and B-02 have their notices on branch `v030-fix` ([v030-review.md](v030-review.md)
section 5.1); **B-02 leaves one owner decision**: radler is LGPL-3.0-only, so while GeMClean follows it the
extension can be conveyed under GPL version 3 only (`LICENSE` and the package metadata unchanged). Written on branch
`v030-ready` from origin/main `9b4542cb`. Nothing here is tagged or released. The release review is
[v030-review.md](v030-review.md). The plan is [roadmap.md](roadmap.md) (v0.3.0 section).

States: **met** (the evidence closes it), **outcome recorded** (a measured result, fixed or a documented
limit), **running** (a result still to come, with where it lands), **open**.

## 1. "Done when" (roadmap.md, v0.3.0)

| Item | State | Evidence | Still to come |
| --- | --- | --- | --- |
| #7 has run; "native data not tested" gone or replaced by measured limits | **running** | E2-N smoke met (branch `e2n`, `793c645`, e2-acceptance 9.3); the rang arm runs on nash (`~/rang-data/outputs/e2n-20261116/R/`, `chain-steps.log`), the post chain starts after it | E2-N's scores (merge of `e2n`); then the CHANGELOG line "Native MeerKAT data is not tested" is replaced by its measured limits |
| χ is gated or stated as a limit | **met (stated as a limit)** | [chi-offset.md](chi-offset.md) section 11, coordinator decisions 2026-11-17: RM-corrected χ(λ²=0) 29.4°, 3.6° from 33°, a limit, not gated; 10.1 per-product note; 10.3 closed by [xf-avg-fix.md](xf-avg-fix.md) and [xf-preavg.md](xf-preavg.md). CHANGELOG Unreleased, Known limitations | a frozen RM-term follow-up, listed for later (not v0.3.0) |
| #6 ends in a recorded outcome | **running** | arms 1-2 measured, no arm meets T2 ([selfcal-arms.md](selfcal-arms.md)); one Sp round removes most of the pilot's floor ([floor-3.md](floor-3.md), [floor-4](https://github.com/gijzelaerr/rang-core/blob/84392cdd/research/floor-4.md)) | the selfcal-defaults grid (branch `floor-4`, `research/selfcal-defaults.md`; 10 runs scored, N120-N600 and X running on nash); its outcome is #6's |
| #22 ends in a recorded outcome | **outcome recorded: documented limit** | upstream read 2026-11-17 (section 4): radler !238 merged (keeps the linear join on every path), WSClean !1068 merged, neither in a release; GeMClean already matches; CHANGELOG known limitation | none |
| #23 ends in a recorded outcome | **outcome recorded: measured null, documented limit** | [multiscale-flux-fix.md](multiscale-flux-fix.md) 8.1: no arm passes on both fields; +9 to +18 µJy median excess on compact sources ≥ 20σ_ap in WSClean and GeMClean alike; CHANGELOG known limitation | none (automatic scales on DF5-O is a separate decision, 8.8) |
| #13 ends in a recorded outcome | **outcome recorded (merge of `floor-4` pending)** | [floor-3.md](floor-3.md) (merged): H1 attributed under floor-3's standard, share 0.88; floor-4 (branch `floor-4`, pushed result commit [`84392cdd`](https://github.com/gijzelaerr/rang-core/blob/84392cdd/research/floor-4.md)): H1 attributed under imaging-floor's full criterion, share D_T1p 0.83, T1p specific; XX−YY phase real and invisible to Stokes I; 8.6 × thermal after one round remains unexplained | the coordinator merges `floor-4` (with the grid) |
| tfcrop is at parity or still refused | **met (still refused)** | [v8-tfcrop.md](v8-tfcrop.md) fails as frozen; [v8c-tfcrop-poly.md](v8c-tfcrop-poly.md) null; `tfcrop.ENABLED = False`, the refusal names the note | none |
| An agent can run the chain through MCP | **met** | `tests/test_mcp_chain.py`: a scripted JSON-RPC 2.0 client over stdio drives `rang-core mcp --allow-write` through listobs, config_check, run (plan, then the confirmed token) and run_status until flag, calibrate, apply, image and selfcal are done on the public fixture; receipt [results/v030-mcp/](results/v030-mcp/). It found a Windows race that failed the run (R-01, fixed here) | none |

## 2. Carried over from v0.2.0 (#2)

| Item | State | Evidence | Still to come |
| --- | --- | --- | --- |
| E2-B Gpol | **met** (A3) | [e2b-misses.md](e2b-misses.md) 9.27: `calibrate.casa_phase_weights` 0.00038° (class B 0.1°); off by default, E3 turns it on | none |
| E2-B K G B composites | **met** (A2, matched inputs) | e2b-misses 9.4: both composites met when CASA solves on rang's flags and weights; the frozen miss was an oracle input error | none |
| E2-B CASA applycal (2b) | **met** | e2b-misses 9.25, confirmed 9.29: 0 of 408,827,131 cells over class C, flags exact | none |
| E2-B image gate 3c | **dirty met; cleaned with the mask a known limitation** | e2b-misses 9.29: dirty 2.0e-7 to 3.3e-7; cleaned compact scatter 1.18 % (bound 1 %); coordinator decision 2026-11-16 | none |
| E2-B 1830−211 χ, transfer χ, leakage 0.30 % | **known limitations** (proposed in e2b-misses table, owner decision 2 of e2b-misses "For the coordinator") | e2b-misses sections 5-7; chi-offset section 11 for the transfer χ | the owner may set new tolerances instead (A0 rule 1) |
| E2-A scored | **outcome recorded: not met as frozen** | [e2-acceptance.md](e2-acceptance.md) 9.13-9.14: gates 1, 2a-c, flux, target noise, selfcal rms met; 3b composite, 3c, target compact scatter not met; 3c and target compact a known limitation | — |
| E2-A 3b composite | **running** | [e2a-3b-diag.md](e2a-3b-diag.md): part B time averaging (fixed behind `calibrate.bandpass_model_divided`), part K estimators | the K follow-up (branch `e2a-3b-k`, `research/e2a-3b-k.md`; CASA arms on nash); a confirmation leg on the reserve data is proposed, not run |
| E3 against CARACal (timed) | **E3-B met; E3-A running** | [e3-caracal.md](https://github.com/gijzelaerr/rang-core/blob/e3-caracal/research/e3-caracal.md) 10.16-10.17 (branch `e3-caracal`): E3-B timed CARACal 6,926 s against rang 6,195 s, 3C 286 \|Δp\| ≤ 0.03 points, Δχ ≤ 0.22° | E3-A correctness, cost and timed runs on nash (driver `~/Build/tmp/20261117-e3-drive/drive.sh` on nash); merge of `e3-caracal` |
| The E5 review | **done for main at `9b4542cb`** | [v030-review.md](v030-review.md) | a delta pass over what the four running results merge |

## 3. Other v0.3.0 rows (not in "Done when")

| Issue | State | Evidence |
| --- | --- | --- |
| #8 open CASA tasks | progressed: V8b's fixed-rule modes at parity, FLAG_ROW 9/9 on a fresh LUNO split; tfcrop refused | [v8b-flagdata.md](v8b-flagdata.md), [v8-tfcrop.md](v8-tfcrop.md) |
| #10 trained flagger F4 | open: calibrator parity and label audit done, targets stopped at the label audit; training not run | `outputs/status/f4-flagger.md`, [f3-flagger.md](f3-flagger.md) |
| #27 piece 1 | met (MCP server merged for 0.2.0; chain demonstrated here); piece 2 is v0.6.0 | [mcp-server.md](mcp-server.md), section 1 |
| #33 Xf rang-CASA 0.054° on held-out 3C 286 | known limitation, open, low priority | [xf-preavg.md](xf-preavg.md) |

## 4. #22 upstream check (read 2026-11-17, GitLab APIs, read only)

- **radler !238** ("Make peak finding consistently use linear or squared values"): **merged 2026-11-16
  08:51 UTC**, squash `620e0a76`, into radler `main`. GenericClean's last squared path (`-no-fast-subminor`
  after the first pick) now uses the linear sum too; squares only with `-squared-channel-joining`.
- **WSClean !1068** (`CalculateMsLimits` v bound): merged 2026-11-13, squash `53e25d59` (GeMClean followed it,
  u5-upstream.md).
- **Releases:** WSClean's latest tag is v3.7 (2026-02-14); radler's v1.2.0 (2026-10-12), before !238.
  WSClean master still pins radler `703c1bd7` (`CMakeLists.txt` `RADLER_COMMIT`), before !238.
- **GeMClean:** peaks on the linear sum in the first pick and in its sub-minor loop (g9-stokes.md section
  1); it has no `-no-fast-subminor` path, and `-squared-channel-joining` is refused
  (`core/src/gemclean/cli.rs`). So !238 changes nothing GeMClean runs.
- **Outcome:** kept as WSClean's linear sum, a documented limit: with QU joined, components whose Q and U
  cancel are not cleaned, by either imager (g9-stokes P1-Q6). The squared route stays the proposal
  [pol-join-squared.md](pol-join-squared.md) (frozen, nothing built), for a later release. When a WSClean
  release carries radler ≥ `620e0a76`, rerun G9's oracle cases (unchanged expectation for GeMClean's paths).

## 5. Issues at v0.3.0

From `gh issue list -R gijzelaerr/rang-core --state all -L 60`, read 2026-11-17 (no issue was opened,
closed or commented from this branch). "Close at release" is a proposal for the owner or coordinator.

| # | Title | State at v0.3.0 | Evidence |
| --- | --- | --- | --- |
| 33 | Xf: 0.05° rang-CASA gap on held-out 3C 286 simulations | open, known limitation | [xf-preavg.md](xf-preavg.md) |
| 32 | GeMClean joined-IQUV memory is 10-22x WSClean's | progressed: by default 15.9-16.5 GiB on the large fields (8.2-8.4 × WSClean), 8.4 GiB on J1833−2103; with `-reorder` 9.1 GiB (4.7 ×) and 7.2 GiB (5.4 ×); open | [gemclean-memory.md](gemclean-memory.md), [gemclean-memory2.md](gemclean-memory2.md) |
| 31 | test_waiters_acquire_in_ticket_order is flaky under host load | closed 2026-11-15 (in this release) | `61767423`, merged `02631b86` |
| 30 | Flaky: test_confirmed_gemclean[False] | closed 2026-11-15 (in this release); its run-state form found and fixed here (R-01) | `61767423`; [v030-review.md](v030-review.md) R-01 |
| 28 | GeMClean close-to-threshold stop rule | progressed (`-stop-tolerance`, off by default); milestone v0.4.0 | [gemclean-stop28.md](gemclean-stop28.md) |
| 27 | MCP server and agent benchmark | progressed: piece 1 met (chain demonstrated); piece 2 open (v0.6.0) | section 1; [results/v030-mcp/](results/v030-mcp/) |
| 26 | P1 snapshot light curves | closed 2026-11-13, duplicate of #9 | — |
| 25 | F4 antenna-domain arm | closed 2026-11-13, duplicate of #10 | — |
| 24 | CLEAN against RML/learned imagers | open, unchanged (v0.6.0) | — |
| 23 | Multiscale flux miss on compact sources | **close at release**: measured null, documented limit | [multiscale-flux-fix.md](multiscale-flux-fix.md) 8.1 |
| 22 | Join polarisations on the squared sum | **close at release**: kept as the linear sum, documented limit (upstream agrees) | section 4 |
| 21 | Joint self-calibration | closed 2026-11-13, duplicate of #6 | — |
| 20 | Method proposals from the digest | open, unchanged (v0.6.0) | — |
| 19, 17, 16 | Beamformed time series; VLBI; LOFAR | open, unchanged (Later) | — |
| 18, 11 | S band; UHF | open, unchanged (v0.5.0) | — |
| 15 | Direction-dependent calibration | open, unchanged (v0.5.0) | — |
| 14 | Absolute χ | **close at release**: stated as a limit (chi-offset 11); the RM-term follow-up and #33 stay | [chi-offset.md](chi-offset.md) section 11 |
| 13 | The imaging floor | **close at release, after `floor-4` merges**: H1 attributed under imaging-floor's full criterion (share 0.83); the 8.6 × thermal remainder a documented limit | [floor-3.md](floor-3.md), floor-4 `84392cdd` |
| 12 | GPU gridding in GeMClean | progressed on branch `gpu-grid` (not merged); v0.4.0 | STATE 2026-11-16 |
| 10 | Trained flagger F4 | open, unchanged since 2026-11-13 (targets need a label decision) | `outputs/status/f4-flagger.md` |
| 9 | Time series P1 | progressed: `rang-core lightcurve`, met on the held-out simulation under post hoc amendments; T6 met on nash | [ts-p1.md](ts-p1.md) |
| 8 | Open CASA tasks | progressed: tfcrop still refused (V8, V8c) | [v8-tfcrop.md](v8-tfcrop.md) |
| 7 | Native MeerKAT data (E2-N) | running; close when E2-N's scores merge | branch `e2n` |
| 6 | Self-calibration beyond model absorption | running; close when the selfcal-defaults grid merges with an outcome | branch `floor-4` |
| 5 | MSv4 / xarray-ms | progressed: read path bit-identical (M1-M3); v0.4.0 | [msv4-interop.md](msv4-interop.md) |
| 4 | Multi-node stage 2 | open, unchanged (v0.4.0) | — |
| 3 | Multi-node stage 1 | progressed: chunk task API merged, identity gate passed, timing points on nash | [chunk-task-api.md](chunk-task-api.md) |
| 2 | v0.2.0 release tracking | closed 2026-11-14; its carry-overs are section 2 | — |
| 1 | Fast supervised flagger (F2) | open, unchanged | [f2-flagger.md](f2-flagger.md) |

## 6. Left before tagging

1. B-01 and B-02 ([v030-review.md](v030-review.md) section 3): notices done on branch `v030-fix` (section 5.1,
   read in the upstream sources). Open: the owner's decision on the package licence expression given
   radler's LGPL-3.0-only and WSClean's "GPL 3" (section 5.5, owner decision 1), and msutils' conflicting
   licence statements (owner decision 2).
2. Merge the four running results (`e2n`, `e3-caracal`, `floor-4`, `e2a-3b-k`) and run the review's delta
   pass over them; replace the "native data not tested" limitation with E2-N's measured limits.
3. E6 as in 0.2.0: the version bump in `pyproject.toml` (and what follows it), the CHANGELOG section
   `0.3.0` from Unreleased (the "Issues" draft is in the CHANGELOG already), docs/limits.md's E3 line.
4. Issues to close at the release (the owner posts): #14, #22, #23 now; #13, #6 and #7 when their branches
   merge.

## For the coordinator

Branch `v030-ready`. Running items are named with their branch or nash path above; nothing here waits on
this branch. The MCP chain test needs `RANG_FIXTURE` and the `mcp` extra (it skips in CI without them);
it ran here on Windows (5 of 5 passes, receipt in results/v030-mcp/).
