# Roadmap: releases after v0.2.0

Status, 2026-11-13: **approved by the owner** ("i approve all of it", 2026-11-13),
including the three open decisions as resolved in "Owner decisions" below. Nothing here is built unless a row says so. Each item is an issue
on [gijzelaerr/rang-core](https://github.com/gijzelaerr/rang-core/issues?q=label%3Aroadmap),
grouped into one GitHub milestone per release. This note replaces
`roadmap-v030.md` (same day). The rules:

- **No pre-releases and no fixed dates** (owner, 2026-11-11). A release ships
  when its "done when" holds.
- **Every claim follows `AGENTS.md`:** a proposal note, a frozen tolerance, an
  oracle and a measurement. A null or failed result is recorded and can still
  ship as a documented limit.
- **Research runs ahead of releases.** Comparisons and measurements (#13, #23
  step 1, #24 step 1) can run any time on shared slots. A release only decides
  when their outcome ships.
- **One theme per release**, so each release answers one question for users.

## Releases

| Release | Theme | Question it answers for users |
| --- | --- | --- |
| v0.2.0 | Parity | Does one command take an unseen MeerKAT L-band MS to a calibrated, full-polarisation image, each stage matching its oracle? |
| v0.3.0 | Science grade on real data | Can I trust the images and polarisation on my own native data, and drive it from an agent? |
| v0.4.0 | Scale | Does it run on my cluster and on the formats the other tools are moving to, faster at the same accuracy? |
| v0.5.0 | More of MeerKAT | UHF, S band, time-domain products and the first direction-dependent piece |
| v0.6.0 | Beyond the state of the art | Do any of the method proposals beat WSClean, QuartiCal and CARACal at matched cost? |
| Later | Other telescopes | LOFAR, VLBI, beamformed pulsar and FRB search |

### v0.2.0: parity (tracking issue #2)

Status on 2026-11-13:

- E2-B is running.
- E2-A comes next.
- E3, the comparison against CARACal, waits for E2.
- chi-offset is running.
- Then the E5 delta review and E6 (the owner tags).

Estimate, not a measurement: four to six days of host time if nothing needs a rerun.

### v0.3.0: science grade on real data

| Issue | Item | Size | Depends on |
| --- | --- | --- | --- |
| #7 | Native MeerKAT data (E2-N), frozen E2 protocol unseen | M (fetch + one E2 run) | the data source (owner) |
| #14 | Absolute polarisation angle χ | M | chi-offset's result |
| #6 | Self-calibration beyond model absorption: arms 1-2 (rounds and intervals, phase-only first round) | M | — |
| #22 | GeMClean: join polarisations on the squared sum | S | upstream check (WSClean !1068, radler !238) |
| #23 | Multiscale flux miss on compact sources (DF5-O A1) | S to measure, M to fix | — |
| #13 | The imaging floor, 40-60 × thermal: attribute or reject each cause | M | — |
| #8 | Open CASA tasks: tfcrop parity, FLAG_ROW on a fresh split, the next tasks | M | V8b merged |
| #10 | Trained flagger F4 (calibrators; targets need a label decision) | M | owner: target labels |
| #27 | Agentic tooling, piece 1: an MCP server over rang-core | S | — |

**Done when:**

- #7 has run, and v0.2.0's "native data not tested" is gone or replaced by measured limits.
- χ is gated or stated as a limit.
- #6, #22, #23 and #13 each end in a recorded outcome (fixed, or a documented limit).
- tfcrop is at parity or still refused.
- An agent can run the chain through MCP.

### v0.4.0: scale

| Issue | Item | Size | Depends on |
| --- | --- | --- | --- |
| #3 | Multi-node stage 1: chunk task API, multi-process on one node | M | — |
| #5 | MSv4 / xarray-ms interoperability (stage 3 of the scoping note) | L | #3's ChunkSpec |
| #4 | Multi-node stage 2: Dask distributed on Slurm and PBS | L | #3 |
| #12 | GPU gridding in GeMClean, CPU path the reference | L | — |
| #28 | Close-to-threshold stop rule (fewer major cycles at the same false flux) | M | — |

**Done when:**

- Outputs are bit-identical across executors.
- Strong scaling over 1-8 nodes is measured against QuartiCal and `wsclean-mp` at matched accuracy.
- Data round-trips through MSv4 against xradio and xarray-ms.
- GPU images are within tolerance of the CPU path.

Scoping note: [multi-node-scope.md](multi-node-scope.md).

### v0.5.0: more of MeerKAT

| Issue | Item | Size | Depends on |
| --- | --- | --- | --- |
| #11 | UHF band | M | UHF data |
| #18 | S band | M | #11's pattern |
| #9 | Time series P1: residual snapshot light curves, then dynamic spectra | M | owner approves P1 |
| #15 | Direction-dependent calibration and facets, first piece | L | a scoping note; #4 helps |

**Done when:**

- Each band passes CARACal's strategy and CASA on a public track, with tolerances frozen first.
- P1 is within tolerance of WSClean `-intervals-out` and an exact DFT.
- The first DD piece has been measured against its oracle.

### v0.6.0: beyond the state of the art

| Issue | Item | Size | Depends on |
| --- | --- | --- | --- |
| #24 | Gap between CLEAN and RML/learned imagers (step 1 is a comparison and can run early) | M, then L | — |
| #6 | Self-calibration arm 3: gains and image as one regularised problem | L | #6 arms 1-2, #24's outcome |
| #20 | Digest proposals: RFI mixture inside the gain solve, sidereal averaging, provenance checks | M each | owner approval per proposal |
| #27 | Agentic tooling, piece 2: an agent benchmark from the frozen gates | M | #27 piece 1 |

**Done when:**

- Each proposal has a measured outcome against the state of the art at matched cost.
- What wins ships behind an option.
- What does not win is recorded as null.

This is the release where a novelty claim can be made. Nothing is promised.

### Later: other telescopes

| Issue | Item | Note |
| --- | --- | --- |
| #16 | LOFAR: DI ionospheric solve against DP3 DDECal | [v7-lofar-scope.md](v7-lofar-scope.md) |
| #17 | VLBI: fringe fitting against CASA `fringefit` and AIPS FRING | [v6-vlbi-scope.md](v6-vlbi-scope.md) |
| #19 | Beamformed time series: dedispersion, single pulse, folding | [v1-timeseries-scope.md](v1-timeseries-scope.md) |

The rule stays: don't generalise beyond MeerKAT until a second telescope's data
and oracle are in hand.

## Why this order

1. **Trust before speed.** v0.2.0's own records list the known misses: native data untested, χ not claimed, selfcal model absorption, the polarisation join, the multiscale flux miss and the floor. A user hits those before they hit the limits of one node.
2. **Scale before breadth.** UHF, S band and DD calibration multiply data volume, and DD calibration needs the cluster path. The multi-node and MSv4 work (Simon Perkins' question) also opens collaboration with the RATT tools.
3. **Methods last, measured early.** The record (gain-TV flagging, pointing, F2, F3) is that promising ideas were null, so v0.6.0's comparisons start on shared slots long before it, and only measured winners ship.
4. **Other telescopes after MeerKAT is complete.** Each needs its own data, oracle and owner decision.

## Sizes

- **S:** a day or two of agent time.
- **M:** under a week.
- **L:** weeks.

These are estimates, not measurements. The weekly API limit and the shared host bound the pace.

## Notes and links

- Opportunities filed on 2026-11-13 by another session at the owner's request: #22, #23, #24, #27, #28, plus plans as comments on #6, #9, #10 and #13 ([opportunities-2026-11-13.md](opportunities-2026-11-13.md)). Its #21, #25 and #26 were closed as duplicates.
- Issue #1 is the F2 flagger discussion with Landman. F4's target labels are an open owner decision, with three options:
  - a target-calibrated threshold for `s`;
  - labels without `s`;
  - Landman's expert labels.

## Owner decisions (2026-11-13)

The owner approved the plan as a whole ("i approve all of it"). The three items
he had left open are resolved by the coordinator's choice under that approval:

1. **#7, native data:**
   - Source: the SARAO archive through katdal (MVF), an L-band block with 1934−638 and 3C 286 or 3C 138 (for example from MIGHTEE-pol).
   - Data goes to `D:ang`.
   - **Owner action:** register at the archive and provide the per-user token. Until then #7 waits.
2. **#9, time series:** P1 (residual snapshot light curves) is the first product, and P2 (dynamic spectra) follows.
3. **#10, F4's target labels:**
   - Primary arm: a threshold for `s` calibrated on target fields.
   - Second arm, pre-registered with it: labels without `s`.
   - Landman's expert labels are asked for as an independent held-out check, not as a dependency.

## For the coordinator

- One milestone per release on GitHub.
- New work items join a release only on the owner's word, or go to "Later" with the label `roadmap`.
- Don't start v0.3.0 implementation before E6. Comparisons with no rang code (#24 step 1, #23 step 1) may run on shared slots without delaying the critical path.
