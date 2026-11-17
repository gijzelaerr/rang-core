# Propose and measure an algorithm change

For: an algorithm scientist (or their agent) with an idea that should make
calibration, flagging or imaging better or cheaper. Ends in a pull request that
carries a proposal note frozen before the code, a measurement against an oracle,
and the outcome, whether it is a gain, a null or a failure.

The record so far (gain-TV flagging, pointing, the supervised flaggers F2 and
F3) is that ideas promising on paper were null or failed their own test. This
procedure proposes and measures; it never merges on its own.

## 1. Check that it is new

- Read `research/README.md` and `research/STATE.md`, and search `research/` for
  the idea: it may already be closed as null, or be an open owner decision.
- Name the closest primary literature and the state-of-the-art tool it must
  beat (WSClean, CASA, QuartiCal, CARACal, AOFlagger, Tricolour). The novelty
  rule in `AGENTS.md` applies: a win against a weak baseline or a
  reimplementation does not count.

## 2. Freeze a proposal note

Write `research/<id>-<name>.md` and commit it on your branch before any code
that tests it. It states:

- the hypothesis, in one sentence, and what is not claimed;
- the data (simulated with a seed, or real with provenance and licence) and the
  held-out part that is read once;
- the oracle: the upstream tool or reference path the result is checked
  against, with its version;
- the measures, the frozen tolerances and a decision rule that names every
  outcome (gain, null, failure) before any result is seen;
- the cost measure (wall time, peak memory, at stated threads, on an idle host)
  and the comparison at matched accuracy;
- stages and stop rules.

`research/f3-flagger.md` and `research/g8-wheel.md` are worked examples. Any
later change is a dated amendment, labelled post hoc for results it could
have seen.

## 3. Implement and measure

- Rust for kernels, Python for orchestration; keep the existing path and add
  the new one beside it until the measurement decides.
- First reproduce the oracle (numerical correctness), then measure the change.
- Run timings and campaigns under `python tools/heavy_lock.py run -- ...`;
  write outputs to ignored `outputs/`, compact archives to `research/results/`,
  and timing rows to `research/tool-timings.md`.
- Record every arm, seed and failure under a "Measured result" heading of the
  note; read the decision from the frozen rule, not from the numbers you hoped
  for.

## 4. Open the pull request

- Run the full local checks (`python -m rang.check`) and paste the summary.
- The pull request description gives: the hypothesis, the outcome under the
  frozen rule, the tolerance and oracle, cost against the baseline, and what is
  not checked. A null or failed result is still worth a pull request when it
  adds only the note and its archive.
- Leave the decision to merge, and any change to defaults, to the owner.
