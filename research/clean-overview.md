# Rang: overview of the CLEAN programme

Status, 2026-11-03, at main after the [floor](stale-floor.md). Read this first; the notes it links hold the numbers.
Draft paper: [paper/clean-theory/main.tex](paper/clean-theory/main.tex). No speed figure here is final: the timing pass
on an idle host has not run.

## What holds

- **Theory, proved in Lean (96 audited theorems, no `sorry`).** One line, the exact change of misfit per component;
  descent under the single condition that the beam is the Gram matrix of the atoms; the least-squares floor and its rate;
  convergence of the model; small-gain CLEAN as forward stagewise regression, so it minimises no global objective.
  [clean-theory.md](clean-theory.md), [clean-implicit-objective.md](clean-implicit-objective.md).
- **Measured laws.** The recovery coefficient was never wrong in 30,206 trials on four arrays, and the two-source rule
  held in 40,000 of 40,000. [clean-phase-transition.md](clean-phase-transition.md).
- **WSClean 3.7 on a sparse real slice.** It diverges in all four variants on a 4-station PKS 1934−638 slice. The same loop
  with its image-sized beam reproduces the run to 5.4e-6 Jy, and with a PSF of twice the size converges to 0.45 % of the
  calibrator flux. This is a worst case: on 64 dishes neither imager diverges. [clean-certified-imaging.md](clean-certified-imaging.md).
- **GeMClean's accuracy, simulated.** It reaches the threshold exactly at false flux comparable to WSClean's, on three
  tuned and four new skies: at most 1.37 × the better WSClean loop on the new ones. WSClean's fast loop has lower false flux
  on H1, H3 and the tuned S1-S3. [gemclean-benchmark.md](gemclean-benchmark.md), [gemclean-heldout.md](gemclean-heldout.md).
- **GeMClean on a real scan.** On ESO 137-006, 3 mJy: 3-5 cycles against 4-5, off-source model flux 1.02-1.03 ×,
  compact-source flux within 0.1 % in the median. Matched, not blind: the threshold and extra flags came after seeing WSClean's runs.
- **Reproducibility.** Images are identical at 1 and 16 threads on S1. Native Windows matches Linux to 9.1e-13 Jy, on
  different commits, with no change of data. [x1-crossplatform.md](x1-crossplatform.md).

## What failed or came back null

- **"4-5 major cycles" did not generalise.** 6, 6, 8, 5 on four new skies, against a bar of 5 written first. More than
  WSClean's plain loop on H2 and H3. GeMClean passes plain's stopping peak in 4, 4, 5, 3 cycles, but that was seen afterwards.
- **The stop rule had a real failure,** now guarded: a bright source near the phase centre ran it to the component budget.
  The floor of 0.01 ends this in eight simulated cases and changes no image on the ordinary skies. It is not proved, its value
  was chosen after seeing those skies, it missed one limit written first, and no real observation has such a source.
- **The rule with a theorem is not the practical one.** It takes three times the cycles for the same false flux, and its
  bound is on paper, not in Lean. [stop-rule-theorem.md](stop-rule-theorem.md).
- **The many-pass solver meets no novelty rule.** About three times less false flux than GeMClean at 11-21 times the
  instructions, faster only than FISTA on the exact gridder. Not compared with BASPLib, PURIFY, resolve or pfb-imaging.
  [gram-solver.md](gram-solver.md).
- **A visibility-free major cycle does not pay at GeMClean's cycle count.** [gridder-theory.md](gridder-theory.md).

## Not established

- Any speed claim against WSClean. Instruction counts exist; wall times are provisional.
- Real-data accuracy: there is no truth on the pilot, whose floor is 40-60 × thermal in all three imagers, for a reason not
  found. One scan, one flat-spectrum term, no `-channels-out`, no multiscale.
- The full 7 h track: about 126 GB to fetch and, roughly, 110 GB of memory at 2× averaging. GeMClean used 18 GB on 152 M
  visibilities and did not fit 24 GB at 512 channels.
- A stop that ends close to the threshold rather than exactly on it, which could lower the cycle count. It would be a
  new rule and need its own held-out test.

## Open decisions (owner)

1. **The WSClean report** ([draft](../outputs/clean-theory-20261030/wsclean-report-draft.md), not in the repository). Held until this overview.
   Nothing in the later work changes its three findings.
2. **The paper.** Read the draft; say whether the early reader is named. The name GeMClean has not been checked for clashes.
3. **The timing pass.** About 3.3 h on an idle host, or 1.5 h on one dataset. Every speed figure waits on it.
4. **Further tests, none started.** A close-to-threshold stop with its own held-out test; a comparison with pfb-imaging
   (`rang-pfb-imaging:0.0.11` is built locally).
