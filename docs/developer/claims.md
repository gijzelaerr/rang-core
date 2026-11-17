# Claims: propose, freeze, measure

A change that claims a scientific or performance gain brings four things
before it is merged ({gh}`AGENTS.md`, "Claims"):

1. **A proposal note** in `research/`: hypothesis, data, settings, decision
   rule, committed before the code that tests it.
2. **A frozen tolerance** for every measure.
3. **An oracle**: the upstream tool or reference path the result is checked
   against, with its version.
4. **The measurement**, with run paths, seeds and receipts, under "Measured
   result" in the same note.

Later changes to the protocol are dated amendments, labelled post hoc for any
result they could have seen. {doc}`../agents/propose-and-measure` is the
procedure step by step; {gh}`research/f3-flagger.md` is a worked example, with
an amendment made after a frozen stop fired and before any held-out read.

## What counts as a gain

**Novelty** means demonstrably higher calibration or imaging quality at
comparable cost, or comparable quality at materially lower runtime or memory,
against a relevant state-of-the-art method: WSClean for MeerKAT imaging;
CASA, QuartiCal and CARACal for calibration; Tricolour and AOFlagger for
flagging. A win against a weak baseline, or a faithful reimplementation, does
not establish it. Validate numerical correctness against the oracle before
measuring a gain.

Cost is measured at matched accuracy, at stated thread counts, on an idle host
(an exclusive hold of `tools/heavy_lock.py`), and each timed tool run gets a
row in {gh}`research/tool-timings.md`.

## Ports: parity, not novelty

Most of rang is ports, each gated on reproducing its upstream tool within a
tolerance written first:

| Port | Oracle | Gate as measured |
| --- | --- | --- |
| Tricolour's strategies | Tricolour 0.2.1 | flag for flag on four archived controls ({gh}`research/core-d-tricolour.md`) |
| WSClean's imaging weights | WSClean 3.6 | bit-identical on 19 runs ({gh}`research/core-b-weighting.md`) |
| w-stacking gridder | WSClean 3.6-1 | 6.1e-7 of the peak on 15 jobs ({gh}`research/core-c-gridder.md`) |
| ducc0's wgridder | ducc0 0.42.0 | 1e-12 to 1e-14 of the peak, adjoint to 4e-13 ({gh}`research/df1-wgridder.md`) |
| casacore table writer | casacore 3.8.1, CASA 6.7.6 | byte-identical bar uninitialised memory and alignment gaps ({gh}`research/e6-table-writer-final.md`) |
| GeMClean multiscale | WSClean 3.7 | extended flux within 0.42 % on S2, H4, M1 ({gh}`research/g5-multiscale.md`) |

A port earns parity, which is what the v0.2.0 finish line asks for
({gh}`research/finish-plan.md`); it claims no gain.

## Negative results are results

Every arm, seed and failure stays in the note. The record so far: gain-TV-guided
flagging closed as null ({gh}`research/flagging-verdict.md`); beam and pointing
closed as null ({gh}`research/b1-3-pointing-selfcal.md`); the learned flaggers
F1–F3 stopped or failed as frozen; GeMClean's speed against WSClean carries no
novelty claim, and its "4–5 major cycles" prediction failed its held-out test
(6, 6, 8, 5; {gh}`research/gemclean-heldout.md`). A null or failed measurement
is still worth a pull request with its note and archive.

## Where ideas come from

A weekly literature digest writes dated digests and proposal stubs
({ghdir}`research/digests`, the `rang-digest` skill). A stub is a proposal, not
a plan: the owner approves one before it is built, and building it follows the
procedure above.
