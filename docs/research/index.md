# The research story

rang is a research project, and its notes are the primary record: each one
states its protocol before the code, separates what was proposed, implemented
and measured, and keeps negative results. This page summarises the main
threads and links to the reports and their compact archives in
{ghdir}`research`; it does not replace them. Start with the index,
{gh}`research/README.md`, and the latest progress, {gh}`research/STATE.md`.

## 1. The port: one Rust core

The flagging experiment first ran on a stack of upstream tools (QuartiCal,
Tricolour, WSClean, casacore, Stimela containers). The port replaced each
with a Rust kernel and gated it on reproducing that tool's archived output
before anything new was built on it: the fused residual pass and QuartiCal's
`complex` solver ({gh}`research/core-phase1.md`,
{gh}`research/core-phase2.md`), the Measurement Set reader
({gh}`research/core-e-ms-reader.md`), zarr ingest and the HTTP range fetch
({gh}`research/core-section6.md`, {gh}`research/core-g-http-fetch.md`),
Tricolour ({gh}`research/core-d-tricolour.md`), WSClean's weights and
gridder ({gh}`research/core-b-weighting.md`,
{gh}`research/core-c-gridder.md`) and the imaging replay
({gh}`research/core-i-imaging-replay.md`). The campaigns were then rerun on
the core alone ({gh}`research/core-k-luno-campaign.md`).

The architecture was then simplified: every kernel moved into the extension,
nothing runs Cargo at import, the GIL is released, and a wheel-only install
reproduces every archived verdict ({gh}`research/p7-architecture.md`); one
command line and receipt format ({gh}`research/p9-cli.md`); wheels for
Linux, macOS and Windows ({gh}`research/x1-crossplatform.md`); and the
rename to `rang` / `rang-core` ({gh}`research/p12-rename.md`). These are
reimplementations and engineering, not scientific contributions.

## 2. The flagging experiment, closed as null

**Question.** Gains of a well-behaved telescope vary smoothly; does the total
variation (TV) of full-Jones gain solutions show where to flag? The policy,
objective and decision rule were frozen on 2026-09-23 before any real-data
run ({gh}`research/flagging.md`, {doc}`../concepts/flagging`).

**Evidence.** A four-antenna fixture pilot, then the LUNO observation's
calibrators: the four-station PKS 1934−638 slice (task K), the whole array
(L1, {gh}`research/luno-array-campaign.md`), PKS 1830−211 (L2,
{gh}`research/luno-1830-campaign.md`), the calibrator's field model (L1-M,
{gh}`research/l1-model-completeness.md`) and a gauge-free closure statistic
(C1, {gh}`research/c1-closure-arm.md`), with a CASA oracle running CARACal's
cross-calibration as the matched baseline ({gh}`research/o-casa.md`).

**Verdict** ({gh}`research/flagging-verdict.md`, archive
{gh}`research/results/flagging-verdict.json`): gain-TV-guided flagging gives
no measurable improvement in calibration or imaging quality over the CARACal
first-pass Tricolour strategy, and it is not cheaper. Of 90 pre-registered
calls, 64 are null and 26 undecidable; none is better and none is worse (the
calls are not independent). The frozen policy never selected a TV-guided
mask. The TV chain costs 4.6 to 5.9 times the first pass. The scope is one
L-band observation and one fixture; the verdict names what would reopen it.

Along the way the experiment produced findings that stand on their own:
lower gain TV does not consistently mean better prediction, smooth receiver
phases change TV-guided decisions, and an incomplete sky model lets the
calibration absorb real signal ({gh}`research/flagging-findings.md`).

## 3. The beam and pointing question

The project began with smoothly time-varying antenna pointing errors,
together with uncertain sky, gains and beam. In simulation, small
dish-to-dish beam differences masquerade as pointing: with 1 % width
scatter across eight antennas, ignoring it leaves 6.3 to 9.2 arcsec of
relative pointing error, fitting the widths brings it to 0.8 to 1.1 arcsec,
close to the oracle ({gh}`research/antenna-beam-widths.md`). Gaussian beams
admit an exact pointing–sky–gain ambiguity
({gh}`research/gaussian-gauge.md`), and relative and shared pointing must be
kept apart ({gh}`research/common-pointing-priors.md`). These are
matched-family simulations, and joint sky/beam/pointing inference has prior
art ({gh}`research/novelty.md`).

With the flagging experiment closed, B1 takes the question to real data
({gh}`research/b1-beam-pointing.md`). SARAO's 2023 holography release is
rang's reference beam (`rang.beam_holography`, read by HTTP range): katbeam
errs 0.54 times and EIDOS 1.8 times the signal of a 30″ offset at half
power. The SARAO/SKA Gaussian pointing-offset fit was ported bit for bit
and reproduces the reference on the five-scan fixture; against the measured
beam it over-recovers offsets by 1.2 to 1.5 times and returns up to 0.6′ at
zero offset, about half of it the beam's squint. B1-2 and B1-3 are proposed.

## 4. CLEAN theory

Is it true that CLEAN "has never been proven"? Not for Högbom's iteration as
a data fit: Schwarz (1978) proved convergence for loop gains between 0 and 2
with a symmetric positive semi-definite beam. It is true for the limit being
the sky outside the sparse regime, for Clark, Cotton–Schwab and multi-scale
CLEAN as run, and for noise. The study recasts CLEAN as the pure greedy
algorithm on pixel atoms, with the PSF as their Gram matrix, so the three
classical conditions become one. Thirteen theorems are machine-checked in
Lean ({ghdir}`formal`), and MeerKAT measurements confirm the one-step
identity to about 1e-13 and find a provable minor-cycle rule where Clark's has no
guarantee ({gh}`research/clean-theory.md`, archive
{gh}`research/results/clean-theory.json`). No pipeline change follows from it.

## 5. The gridder

A study of DDFacet and killMS found no faithful port, and recommended an
exact gridder first ({gh}`research/ddfacet-feasibility.md`). DF1 ported
ducc0's wgridder and passed every gate: agreement with ducc0 to 1e-12 to
1e-14 of the peak, adjointness to 4e-13, bit-identical results at any thread
count. It also explained a 19 % discrepancy between w-stacking and the direct
Fourier transform as aliasing of WSClean's kernel at padding 1.2
({gh}`research/df1-wgridder.md`). DF2a brought it to ducc0's speed on
whole-array inputs ({gh}`research/df2-wgridder-speed.md`).

## 6. Upstream contributions

Findings that reproduce upstream are reported there, with fixes where they
are small and certain: Tricolour (a recompilation fix, merged), CARACal
(strategy files, approved), Stimela (Python 3.14), QuartiCal (convergence and
weights), and six issues and four pull requests on DDFacet and killMS
({gh}`research/upstream-prs.md`, {gh}`research/upstream-saopicc.md`,
{gh}`research/upstream-notes.md`).

## How to read a report

Every report has a status line (proposed, implemented, measured), the
protocol as frozen, deviations labelled post hoc, the exact commands and run
directories, and its tool timings ({gh}`research/tool-timings.md`).
Generated outputs live in ignored `outputs/` directories; the compact
archives under {ghdir}`research/results` are what the comparators and the
tutorials read.
