# v0.3.0 readiness tracker

Status, 2026-11-18: **release-ready except three results still running**: E2-N (#7, nash), E3-A (the
comparison with CARACal on E2-A, nash) and the owner's decision on #28's stop tolerance (switch the default
or keep it opt-in). The version is bumped to 0.3.0 on branch `release-030` (task release-030, from
origin/main `09604d60`), with the CHANGELOG section `0.3.0` written and one `TODO-RELEASE` placeholder for
each of the three (section 6). The delta pass over what merged since the review (section 7) found five
false statements in the shipped docs and CHANGELOG, all fixed on `release-030`, and no blocker left open.
Nothing is tagged or released. Earlier status (2026-11-17, branch `v030-ready`, main `9b4542cb`): four
results running and the licence notices B-01, B-02 open; all four and `v030-fix` have since merged. The
release review is [v030-review.md](v030-review.md); the plan is [roadmap.md](roadmap.md) (v0.3.0 section).

States: **met** (the evidence closes it), **outcome recorded** (a measured result, fixed or a documented
limit), **running** (a result still to come, with where it lands), **open**.

## 0. Merged since 2026-11-17's tracker (`git log --first-parent 9b4542cb..origin/main`)

`v030-ready` (`41bc3efb`), `uhf-scope` (`a3d21bcf`), `floor-4` with the selfcal-defaults grid (`c1f7b016`),
`mit-audit` (`8439b717`) and `mit-own` (`1596c76d`), `f5-draft` (`9a94a31f`), `e2a-3b-k` (`f0c5e630`),
`v030-fix` (`e57faddb`) and the GPL-3.0-only metadata (`11fdd993`), `multinode-executor` (`2987035d`),
`floor-5` (`7d78828e`), `calchain-floor` (`37d8d43d`), `selfcal-memory` (`281a1a79`), `gemclean-memory3`
(`9c6516f1`), `gemclean-ms-mask` (`02f1d39b`), `fp-f4-flagger` (`5de12d16`), `floor-6` (`0ea106bd`),
`gpu-grid` research (`c34c79ad`, code not merged), `xf-gap` (`798d1713`), `stop28-default` research
(`b0388c0c`, code held on its branch), `calwt-terms` (`6c615524`), digest 2026-11-18 (`31750e14`),
`katdal-0-24` (`affe3530`), `digest-skill-oai` (`09604d60`).

## 1. "Done when" (roadmap.md, v0.3.0)

| Item | State | Evidence | Still to come |
| --- | --- | --- | --- |
| #7 has run; "native data not tested" gone or replaced by measured limits | **running** | E2-N smoke met (branch `e2n`, `793c645`, e2-acceptance 9.3); the rang arm and post chain on nash (`~/rang-data/outputs/e2n-20261116/`) | E2-N's scores (merge of `e2n`); then the `TODO-RELEASE (E2-N)` items in CHANGELOG 0.3.0, `docs/limits.md` (box and Scope) and `docs/index.md` become its measured limits |
| χ is gated or stated as a limit | **met (stated as a limit)** | [chi-offset.md](chi-offset.md) section 11: RM-corrected χ(λ²=0) 29.4°, 3.6° from 33°; #14 closed 2026-11-17 | an RM-term follow-up, later |
| #6 ends in a recorded outcome | **outcome recorded: documented limit** | [selfcal-defaults.md](selfcal-defaults.md) section 8: best cell P2@600 D_ho 0.905 against the default's 0.892, under the 0.05 margin; default unchanged; #6 closed 2026-11-17 | none |
| #22 ends in a recorded outcome | **outcome recorded: documented limit** | section 4; #22 closed 2026-11-17 | none |
| #23 ends in a recorded outcome | **outcome recorded: measured null, documented limit** | [multiscale-flux-fix.md](multiscale-flux-fix.md) 8.1; #23 closed 2026-11-17 | none |
| #13 ends in a recorded outcome | **outcome recorded: attributed in part, documented limit** | [floor-4.md](floor-4.md) (H1 share 0.83), [floor-5.md](floor-5.md) (J2), [floor-6.md](floor-6.md) (held out: depth D_h 0.201, spectral 0.474; SDm03 0.717; no default before E2-A and E2-N are re-read) | the owner closes #13 at the tag |
| tfcrop is at parity or still refused | **met (still refused)** | [v8-tfcrop.md](v8-tfcrop.md), [v8c-tfcrop-poly.md](v8c-tfcrop-poly.md) | none |
| An agent can run the chain through MCP | **met** | `tests/test_mcp_chain.py`, [results/v030-mcp/](results/v030-mcp/) | none |

## 2. Carried over from v0.2.0 (#2)

| Item | State | Evidence | Still to come |
| --- | --- | --- | --- |
| E2-B Gpol | **met** (A3) | [e2b-misses.md](e2b-misses.md) 9.27 | none |
| E2-B K G B composites | **met** (A2, matched inputs) | e2b-misses 9.4 | none |
| E2-B CASA applycal (2b) | **met** | e2b-misses 9.25, 9.29 | none |
| E2-B image gate 3c | **dirty met; cleaned with the mask a known limitation** | e2b-misses 9.29 | none |
| E2-B 1830−211 χ, transfer χ, leakage 0.30 % | **known limitations** | e2b-misses sections 5-7 | the owner may set new tolerances instead (A0 rule 1) |
| E2-A scored | **outcome recorded: not met as frozen** | [e2-acceptance.md](e2-acceptance.md) 9.13-9.14 | — |
| E2-A 3b composite | **outcome recorded: documented limitation with its cause** | [e2a-3b-k.md](e2a-3b-k.md), coordinator decisions 2026-11-17: CASA's K biased against truth; the subset's 1.1e-3 is one `minsnr`-flagged G1 solution; reserve not spent | the shared noise-free floor (3.7e-4 to 5.7e-4) under #2 for v0.4.0 |
| E3 against CARACal (timed) | **E3-B met; E3-A running** | [e3-caracal.md](https://github.com/gijzelaerr/rang-core/blob/e3-caracal/research/e3-caracal.md) 10.16-10.17 (branch `e3-caracal`) | E3-A on nash; merge of `e3-caracal`; then the `TODO-RELEASE (E3-A)` items in CHANGELOG 0.3.0, `docs/limits.md` and `docs/index.md` |
| The E5 review | **done for main at `9b4542cb`; delta pass done for `09604d60`** | [v030-review.md](v030-review.md); section 7 here | a delta pass over `e2n` and `e3-caracal` when they merge |

## 3. Other v0.3.0 rows (not in "Done when")

| Issue | State | Evidence |
| --- | --- | --- |
| #8 open CASA tasks | progressed: V8b's fixed-rule modes at parity, FLAG_ROW 9/9 on a fresh LUNO split; tfcrop refused | [v8b-flagdata.md](v8b-flagdata.md), [v8-tfcrop.md](v8-tfcrop.md) |
| #10 trained flagger F4 | closed 2026-11-17: F4 stopped on its calibrator cost gate C1(U4) (0.458, 0.459 against 0.45), weights not shipped; F5 proposed | [f4-flagger.md](f4-flagger.md), [f5-flagger.md](f5-flagger.md) |
| #27 piece 1 | met; piece 2 is v0.6.0 | [mcp-server.md](mcp-server.md), section 1 |
| #33 Xf rang-CASA gap | closed 2026-11-17: the cause is CASA's `calwt` weighting; `calibrate.xf_calwt` (opt-in) 0.012°; the other terms in calwt-terms (opt-in) | [xf-gap.md](xf-gap.md), [calwt-terms.md](calwt-terms.md) |
| #28 stop tolerance | `-stop-tolerance` shipped opt-in; the default switch is an open owner decision (switch only under post hoc amendment 3) | [stop28-default.md](stop28-default.md), coordinator decision 2026-11-18 |
| #34 selfcal memory | fixed: streamed Sp/Sa solves, 3.6 GiB at the 8 GiB limit; GeMClean's 9.3 GiB on the pilot left; issue still open | [selfcal-memory.md](selfcal-memory.md) |
| #35 multiscale with a FITS mask | closed 2026-11-17: no defect, a documented limit | [gemclean-ms-mask.md](gemclean-ms-mask.md) |

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

The table, one row per issue touched since v0.2.0 with its outcome and note, is in `CHANGELOG.md`, section
0.3.0, "Issues" (from `gh issue list -R gijzelaerr/rang-core --state all -L 60`, read 2026-11-18; no issue
was opened, closed or commented from this branch). Open on GitHub and to close at the tag (a proposal for
the owner): #13 (attributed in part, documented limit), #34 (fixed; GeMClean's 9.3 GiB left, which could
move to a new issue), #7 when E2-N merges. #28 stays open (milestone v0.4.0) whatever the default decision.
Already closed: #6, #10, #12, #14, #22, #23, #30, #31, #33, #35.

## 6. Left before tagging

1. **E2-N (#7)**: merge `e2n` with its scores; replace every `TODO-RELEASE (E2-N)` (CHANGELOG 0.3.0 Known
   limitations and the #7 row of Issues; `docs/limits.md` box and Scope item; `docs/index.md`) with its
   measured limits.
2. **E3-A**: merge `e3-caracal`; replace `TODO-RELEASE (E3-A)` (CHANGELOG 0.3.0; `docs/limits.md` box;
   `docs/index.md`) with E3-A's correctness, cost and wall-time rows.
3. **#28**: the owner decides. Keep opt-in: drop the TODO marker from the CHANGELOG item and the #28 row.
   Switch: merge `4b13f1d9` (branch `stop28-default`) under the full check, re-read the gemclean benchmark
   and the E2/E5 image gates, move the item to "Changed" and note that image and selfcal stage hashes change.
4. A delta pass (section 7's method) over `e2n` and `e3-caracal` when they merge.
5. At the tag: the date in `## 0.3.0 (TODO-RELEASE: date of the tag)` and in `docs/installation.md`;
   `git grep -n TODO-RELEASE -- ':!research'` must then find nothing; the full check on the release commit.
6. Owner items from the review still open: E5-36 (`pypi` environment protection), E5-47 ("Development
   Status :: 3 - Alpha"); msutils' conflicting licence statements (v030-review 5.5, owner decision 2).

## 7. Delta pass over what merged since the review (2026-11-18, origin/main `09604d60`)

Method: [v030-review.md](v030-review.md) section 1, scoped to `git diff 9b4542cb 09604d60` (the merges in
section 0) and to the statements the release ships (CHANGELOG, `docs/`, README, notices). Done by hand on
this branch, read only on the code; the checks named below were run, not assumed.

**Release-blocking (false statements in what ships), all fixed on `release-030`:**

| ID | Finding | Fix |
| --- | --- | --- |
| D-01 | CHANGELOG Unreleased carried the licence-metadata entry twice; the second said "ra-ng's own files keep `GPL-3.0-or-later`", and the Licence limitation said "rang-core's own code stays GPL-3.0-or-later". Both false since `mit-own` (own files MIT) | duplicate removed; the Licence limitation restated (package GPL-3.0-only, own files MIT, derived files keep their GPL lines) |
| D-02 | `docs/limits.md` and the CHANGELOG limitation gave `-reorder` as opt-in, with phase-2 figures (15.9-16.5 GiB "by default"); since `gemclean-memory3` it is the default with `-join-polarizations` (7.7 / 5.7 GiB) and writes about 28 GB of temporary files by default, which a killed run leaves | limits.md memory item and a CHANGELOG limitation rewritten from gemclean-memory3 |
| D-03 | CHANGELOG and limits.md: Xf's 0.054° gap "the cause is not found"; `xf-gap` found it (CASA's `calwt`) and closed #33 | both restated with `calibrate.xf_calwt` (opt-in, 0.012°) |
| D-04 | limits.md: "floor-4 on its branch", and the 379 µJy "not explained"; floor-4, -5 and -6 have merged and attribute part of it | limits.md floor item and the CHANGELOG #13 limitation rewritten from floor-6's coordinator decisions |
| D-05 | CHANGELOG: eight entries and the "Drafted ... still running" paragraph sat above Known limitations, outside the changes list; the Issues list was the 2026-11-17 draft (#6, #10, #12 and #33 since closed; #34 and #35 not in it) | entries moved under "Changes since 0.2.0"; Issues rebuilt from today's `gh` output, one row per issue |

**Should-fix and notes (not fixed here):**

| ID | Class | Finding |
| --- | --- | --- |
| D-06 | fixed (release-030) | `rang/mcp_tools.py`'s gemclean allowlist has `-stop-tolerance` but neither `-no-reorder` nor `-temp-dir`: with `-reorder` now the default, an agent's joined-polarisation run writes its temporary files beside `-name` with no way to move or avoid them (B-25, now more relevant) |
| D-07 | should-fix | `-reorder`'s temporary files survive a killed run (B-26), now by default; documented, not cleaned up |
| D-08 | note | `data.executor: spool`: partials are pickles; the spool is refused when not private on POSIX only (`core_spool.py`), on Windows any user who can write the spool directory can run code in a worker. The CHANGELOG states the POSIX rule; a Windows ACL check or a line in the docs is owed |
| D-09 | note | `calwt_scale` (`core/src/cal/apply.rs`) and `rang.applycal._b_scale` follow CASA's `BJones::calcWtScale`; the notices named `StandardVisCal.cc` for the bandpass port only. Pointer added to `THIRD-PARTY-NOTICES.txt` here (no new licence text: CASA's notice was already there). The G and T form (`SolvableVisJones::calcWtScale`, `SolvableVisCal.cc`) has no pointer; add it once read in the source |
| D-10 | note | The notices and `docs/licence.md` name katdal 0.23 as the translation source of `rang/meerkat.py`; the `[meerkat]` extra now pins 0.24. Correct as written (the source version), no change |
| D-11 | note | If #28's default switches, B-21 (a run ended by `-stop-tolerance` reports `StopReason::Threshold`) becomes user-visible in every `-report.json` |

**Checked, no finding:** every new calibrate key (`k_zero_start`, `xf_calwt`, `k_calwt`, `g_calwt`,
`gpol_calwt`, `kcross_calwt`, `df_calwt`) is in `HASH_DEFAULTS` at false; `data.spool` and `spool_wait_s`
are in `RESOURCE_KEYS`; the one new `RANG_*` name in `python/`, `core/`, `src/` (`RANG_SOLVE_TRACE`) is in
`rang.core.ENVIRONMENT`; `docs/cli.md` lists `-no-reorder` and the phase-3 `-reorder` text; README and
`docs/licence.md` state own code MIT, package GPL-3.0-only; the four radler-derived GeMClean files keep
`GPL-3.0-or-later AND LGPL-3.0-only`. Research-only merges (`gpu-grid`, `stop28-default`, `floor-5`,
`floor-6`, `uhf-scope`, `f5-draft`, `fp-f4-flagger`, the digest) ship no code.

## For the coordinator

Branch `release-030` (version 0.3.0, CHANGELOG section, docs, this tracker). Do not tag until section 6
items 1-3 and 5 are done; `git grep -n TODO-RELEASE -- ':!research'` lists every placeholder. README and
`docs/installation.md` say 0.3.0 is the current release from the merge on, so merge this close to the tag.
No new release blocker is open; D-06 is the one should-fix worth doing before the tag (two allowlist
entries and a test). Open owner decisions: #28's default; E5-36, E5-47; msutils (review 5.5).
