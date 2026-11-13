# Roadmap after v0.2.0 (v0.3.0 and later)

Status, 2026-11-13: **proposed by the coordinator; the owner decides the
milestones.** Nothing listed here is built, unless a row says so. Each item is a GitHub
issue, so people can discuss it. The milestones are:

- **v0.2.0:** the finish line ([finish-plan.md](finish-plan.md)).
- **v0.3.0:** the next release.
- **Later:** scoped work with no date.

Every item keeps the claims rule in `AGENTS.md`: a proposal note, a frozen
tolerance, an oracle and a measurement before a gain is claimed.

## 1. v0.2.0: what is left (2026-11-13)

| Step | State |
| --- | --- |
| E2-B (LUNO, full polarisation) | running: leakage/transfer rows, amended post chain, archive; gates 2b applycal, 3b, 3c as committed and 1830−211 recorded not met |
| E2-A (ESO 137, 180 GB) | next; needs about 225 GB to build plus 470 GB after on `D:` |
| E3 (against CARACal) | correctness done; timed E3-B and E3-A wait for E2 |
| chi-offset | running; until it reports, nothing is claimed about absolute polarisation angle |
| E5 delta review | after E3 |
| E6 | the owner tags and publishes; owner sets the `pypi` environment protection |

Estimate, not a measurement: four to six days of host time if E2-A and E3
run without a rerun.

## 2. Proposed v0.3.0

| Issue | Why | Note |
| --- | --- | --- |
| Multi-node execution, stage 1 (chunk task API, multi-process) | users on ilifu and Lengau; Simon Perkins' question | [multi-node-scope.md](multi-node-scope.md) |
| MSv4 / xarray-ms interoperability | the format the RATT and NRAO tools are moving to | [multi-node-scope.md](multi-node-scope.md) stage 3 |
| Self-calibration beyond model absorption | C5/C5b T2 not met; the owner deferred rounds until after the release | [c5b-selfcal-masks.md](c5b-selfcal-masks.md), [proposals/joint-selfcal-regularised.md](proposals/joint-selfcal-regularised.md) |
| Native MeerKAT data (E2-N) | v0.2.0 states that native data is not tested | [a0-acceptance.md](a0-acceptance.md) |
| Open CASA tasks, next pieces (tfcrop parity, task layer) | V8 direction; tfcrop stopped at round 2 of 4 | [v8-open-casa.md](v8-open-casa.md) |
| Time series P1: residual snapshot light curves | V1's recommended first product | [v1-timeseries-scope.md](v1-timeseries-scope.md) |
| Trained flagger F4 | the owner asked F4 to follow F3 | [f3-flagger.md](f3-flagger.md) |
| UHF band | the next MeerKAT receiver | [meerkat-scope.md](meerkat-scope.md) |
| GPU gridding in GeMClean, with CPU parity | outside v0.2.0; the cross-platform rule | [gemclean-speed.md](gemclean-speed.md) |
| The imaging floor (40-60 × thermal) | unexplained in all imagers on the pilot | [stale-floor.md](stale-floor.md) |
| Polarisation angle: absolute χ | depends on chi-offset's result | chi-offset note (branch) |

## 3. Later (scoped, no date)

| Issue | Note |
| --- | --- |
| Multi-node stages 2 and 3 (Dask distributed, Zarr on object storage) | [multi-node-scope.md](multi-node-scope.md) |
| Direction-dependent calibration and facets (DF3 onwards) | [finish-plan.md](finish-plan.md) section 1 |
| LOFAR: DI ionospheric solve against DP3 DDECal | [v7-lofar-scope.md](v7-lofar-scope.md) |
| VLBI: fringe fitting against CASA `fringefit` and AIPS FRING | [v6-vlbi-scope.md](v6-vlbi-scope.md) |
| S band | [meerkat-scope.md](meerkat-scope.md) |
| Beamformed time series (dedispersion, single pulse, folding) | [v1-timeseries-scope.md](v1-timeseries-scope.md) |
| RFI as a mixture inside the gain solve | [proposals/mixture-likelihood-gain-solve.md](proposals/mixture-likelihood-gain-solve.md) |
| Imaging-quality gap against RML and learned imagers | [proposals/imaging-gap-comparators.md](proposals/imaging-gap-comparators.md) |
| Sidereal visibility averaging | [proposals/sidereal-visibility-averaging.md](proposals/sidereal-visibility-averaging.md) |

## For the coordinator

- The issues and milestones were created on 2026-11-13 with the label
  `roadmap` (section 4).
- The owner moves issues between milestones; the coordinator does not start
  v0.3.0 work before E6.

## 4. Issues (created 2026-11-13, gijzelaerr/rang-core)

- v0.2.0: #2 release tracking.
- v0.3.0:
  - #3 multi-node stage 1
  - #5 MSv4 / xarray-ms
  - #6 selfcal beyond model absorption
  - #7 native data (E2-N)
  - #8 open CASA tasks
  - #9 time series P1
  - #10 F4 flagger
  - #11 UHF
  - #12 GPU gridding
  - #13 imaging floor
  - #14 absolute χ
- Later:
  - #4 multi-node stage 2
  - #15 direction-dependent calibration
  - #16 LOFAR
  - #17 VLBI
  - #18 S band
  - #19 beamformed time series
  - #20 digest proposals
- Earlier: #1 F2 flagger discussion.
