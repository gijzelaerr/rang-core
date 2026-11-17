# Opportunities for a novel contribution (overview, 2026-11-13)

Status: **proposed; nothing here is built or measured.** Built from the repository's own
measured notes, the [2026-10 literature scan](literature-2024-2026.md) and the
[2026-11-11 digest](digests/2026-11-11.md). No new literature search was run; items marked
**[unverified]** come from memory and need the novelty check of
`docs/agents/propose-and-measure.md` before a proposal is frozen.

## 1. Can ra-ng beat the incumbents? What the measurements say

| Incumbent | ra-ng today (measured) | Verdict |
| --- | --- | --- |
| WSClean 3.7 | GeMClean: same images within bounds; 1.5x faster at -j16, 0.76-1.13x at -j1 (on the same OS layer 1.04x and 0.81x); 2.0-3.6x the memory ([g7](g7-defaults.md), [g2](g2-memory.md)) | Parity. No novelty from speed. |
| CLEAN itself | Signed l1 over the Gram operator: about 3x less false flux at 11-21x the instructions ([gram-solver](gram-solver.md)). pfb `sara` did not converge in DF5-O (30 sigma residual after 10 cycles) | Open. Nobody has measured whether a gap to CLEAN exists on MeerKAT skies at comparable cost. |
| AOFlagger / Tricolour | Four attempts: TV policy null, F1 NO-GO, F2 and F3 outcome F (0.2-0.34x T's wall, but miss scan-long antenna-local RFI: 0.024 against 0.907) | Not beaten. F4 in flight. |
| DDFacet | No direction-dependent code in ra-ng. DDFacet 1.0 is maintained; Hogbom diverges with more than one facet ([U3](upstream-saopicc.md)) | Out of reach now. Needs DD calibration first (V7 scope). |

## 2. Ranking rule

One discriminator: is there a **measured failure of the state-of-the-art method, on truth data
already in hand, with an oracle and a tunable baseline?** A, B and C meet it. Below that, the
size of the prize if it works, then cost, then prior art.

## 3. Opportunities, ranked

### A. Joint self-calibration: gains and image as one problem (rank 1)

- **Gap (measured):** CARACal's loop misses simulated gains: phase p95 9-17 deg against a
  1.5-3 deg gate; masks, an oracle mask included, do not help; a model from truly corrected data
  gives 0.08 deg ([c5](c5-selfcal.md), [c5b](c5b-selfcal-masks.md)). The CLEAN model absorbs
  gain errors on baselines > 6 km.
- **Comparator:** the loop tuned in an equal budget (more rounds, longer first intervals,
  phase-only first round). **Data:** C5's truths plus two new held-out skies.
- **ra-ng's lever:** exact gain Jacobians and the predictor in one Rust core, and C5's sets are
  small (32 antennas, 64 channels). The Gram operator is no lever here until item D's
  negatives are answered.
- **Prior art:** Ikeda 2024 (ALMA), resolve (Kim 2024, 2025, VLBI), Comrade. None gated on
  MeerKAT L-band truth.
- **Cost:** medium-large; runs take minutes. **Null:** p95 within 20 % of the tuned loop.
- Stub exists: [joint-selfcal-regularised](proposals/joint-selfcal-regularised.md). The owner
  placed selfcal follow-ups after v0.2.0 (finish-plan item 29).

### B. Joined polarisations on the squared sum (rank 2; small)

- **Gap (measured):** WSClean 3.7's binary joins polarisations on the normalised linear sum, not
  the sum of squares its help states. Components whose Q and U cancel stay uncleaned, in
  WSClean and in GeMClean, which copies it; both miss the polarised truth on held-out H1p
  ([g9](g9-stokes.md)).
- **Work:** the squared-sum join in GeMClean behind a flag, scored on H1p and one new held-out
  polarised sky against WSClean 3.7. First check whether WSClean !1068 / radler !238 already
  change the join.
- **Prize:** small but real: a measured gain over WSClean on polarised truth, days of work.
  **Null:** polarised truth error within 10 % of the linear join.

### C. Multiscale flux on compact sources (rank 3; small-medium)

- **Gap (measured):** WSClean multiscale fails DF5-O's A1 on three sources
  ([df5o](df5o-deconv-oracles.md)). GeMClean's multiscale is radler's algorithm (G5), so it
  probably shares the miss; **not measured**.
- **Work:** run GeMClean multiscale on DF5-O's field; if it misses too, find the cause (scale
  bias, sub-minor loop) and test a fix on DF5-O plus a new held-out field.
- **Null:** the miss is a setting, not the algorithm.

### D. Is there a gap beyond CLEAN? (rank 4; step 1 is a cheap comparison)

- **Step 1, comparison only:** pfb `sara` run to convergence (and R2D2 or HyperAIRI if released
  weights fit MeerKAT) against GeMClean multiscale on S1-S3, H1-H4, M1 with truth. Bar: relative
  L2 <= 0.5x GeMClean's at <= 5x wall. About a day of host time, no rang code. Stub:
  [imaging-gap-comparators](proposals/imaging-gap-comparators.md).
- **Step 2, only if a gap is found:** an RML or plug-and-play loop on the w-aware Gram operator.
  Its measured record is mostly negative ([gram-solver](gram-solver.md),
  [gridder-theory](gridder-theory.md)): one apply is 23.7 G instructions against 307 G for grid
  plus degrid at 2048² and 31 M visibilities, but there is no gain against a PSF inner loop
  with exact passes (64.6 T for the operator against 9.5-17.6 T); the SARA-style prior did
  not converge and non-negative l1 failed; at 4096² the apply is only 15 % cheaper and the
  cube takes 8.3 GB; setup costs 2-3 passes. So step 2 is untested with a converging prior
  and has no cost advantage established.
- **Prior art:** Dabbech and Wiaux 2026 (visibility-free with w), uSARA, AIRI, pfb-imaging.
- **Null:** no gap on these skies; GeMClean = WSClean recorded as the state of the art there.

### Not a separate opportunity: the pilot's floor

The ESO 137-006 pilot floor is 0.6-1.0 mJy, 40-60x the 15.5 uJy thermal estimate, the same in
all three imagers ([gemclean-heldout](gemclean-heldout.md) section 5-6). That is 1 h on the
publisher's gains, no self-calibration, 83 Jy of model flux, with a few short baselines
(antenna 1) at 40-200x the median misfit; the paper reaches 0.02 mJy. It reads as an ordinary
calibration limit, not an open algorithmic problem. E2-A images ESO137 with rang's own chain
on the critical path and will say more; A is the method that would address it.

### E. Flagger: the antenna-domain arm (rank 5, inside F4)

- **Gap (measured):** F3 misses wide-band, scan-long, antenna-local RFI (0.024 against 0.907).
  Ravi 2026 (arXiv:2611.01308) argues such RFI is most detectable per antenna.
- **Work:** autocorrelation and per-antenna features as an F4 arm (the owner added an
  autocorrelation arm to F4 on 2026-11-11). Not a new line; it belongs to the F4 session.
- **Related, cheap, likely null:** RFI as a latent mixture inside the gain solve, against
  QuartiCal's robust mode ([mixture-likelihood-gain-solve](proposals/mixture-likelihood-gain-solve.md)).

### F. Open snapshot light curves, P1 (rank 6; a landscape gap, not an algorithm)

- **Gap:** TRON (three MeerKAT discovery papers) has no public code. V1's P1 is scoped
  ([v1-timeseries-scope](v1-timeseries-scope.md)): 8 s residual light curves, oracles WSClean
  `-intervals-out` and the exact DFT.
- **ra-ng's lever:** exact DFT at known positions on residuals costs O(N_vis) per source, no
  imaging. **Blocked on:** the owner's P1 decision and a SARAO token for the held-out set.
- **Novelty:** none claimed; a first open implementation.

### G. Agentic tooling (rank 7; no science claim)

- **Gap:** no radio-astronomy MCP server found (digest 8.8); no agent benchmark for radio
  interferometry. ra-ng's frozen oracle gates (C2-C7, G2-G9, W1-W6) could score an agent
  (compare gwBenchmarks, arXiv:2605.11269).
- **Cost:** small-medium. Fits the vision; contributes to the landscape without a novelty rule.

### H. Close-to-threshold stop (rank 8; cheap)

Could cut GeMClean's major cycles (6, 6, 8, 5 on held-out skies against a bar of 5). Listed in
[clean-overview](clean-overview.md) decision 4; never tested. A gain over GeMClean's own
rule, not over WSClean, whose plain loop already needs fewer cycles on two skies.

## 4. Not proposed, with the reopening condition

- **A DDFacet rival:** needs DD calibration, station or dish beams and a DD oracle set first.
- **Beam and pointing:** closed at B1-3; reopens with a deeper ESO137 field model.
- **Gain-TV flagging:** closed; a per-interval normalised saliency would be a new pre-registered test.
- **TABASCAL-style RFI subtraction:** the scan rejected it (simulated, single channel, needs
  trajectories). Reopens only with real multi-channel evidence.
- **More GeMClean speed:** no novelty at -j1; memory is the weaker side.

## 5. Constraints

- v0.2.0's critical path (E2, E3, E6) holds the exclusive host time. A to D run on shared
  slots; timing claims wait for an exclusive hold.
- JAX is allowed for the pointing reference only; a JAX reference for A needs an owner decision.
- Each opportunity goes through propose-and-measure: note frozen before code, held-out data,
  tuned baseline.

## Issues (filed 2026-11-13, each with a step plan and agent-level advice)

| Item | Issue | Agent level |
| --- | --- | --- |
| A, joint self-calibration | plan as a comment on #6 (arm 3) | Fable for design and protocol, Opus for tuning and runs |
| B, polarisation join | #22 | Opus |
| C, multiscale compact flux | #23 | Opus to measure; Fable if a fix must be designed |
| D, gap beyond CLEAN | #24 (linked from #20) | Opus for step 1; Fable for a step 2 proposal |
| E, antenna-domain flagger arm | plan as a comment on #10 | Opus in the F4 session |
| F, P1 light curves | plan as a comment on #9 | Opus |
| G, agentic tooling | #27 | Opus; Fable for the benchmark's task design |
| H, close-to-threshold stop | #28 | Fable for the rule and protocol, Opus for runs |
| the pilot's floor | reading added as a comment on #13 | Fable for the protocol, Opus for injections |

#21, #25 and #26 were opened and closed as duplicates of #6, #10 and #9.

## For the coordinator

- Landman's request is F4 (`fp-f4-flagger`, session idle since 2026-11-13 08:46): calibrators
  passed the label audit and go to training; **targets stopped** (ignored uninjected cells
  0.47-0.64 against a 0.40 bar). Owner decision open: a target-calibrated threshold for s,
  labels without s, or Landman's expert labels.
- No session works on a CLEAN improvement.
- Recommended order: B now (smallest, a measured WSClean miss), D step 1 alongside (no rang
  code, decides whether anything beyond CLEAN is worth building), C next, A after v0.2.0 as
  already decided.
- This note is uncommitted and not indexed in README or STATE; the Advisor session works in the
  same checkout.
- Owner decision: which opportunity to take through propose-and-measure first.
