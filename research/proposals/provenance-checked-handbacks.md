# Proposal: provenance-checked numbers in research notes

Status: **proposed, 2026-11-11 (digest [2026-11-11](../digests/2026-11-11.md), rank 5).
Nothing built or measured. Process tooling for agent work; no science or
novelty claim.**

## Hypothesis

A checker that requires each number on a note's result lines (the
"implemented, measured" summary and the gate tables) to cite a receipt
(`python/rang/core_receipts.py`), a result archive under `research/results/`
or a named run path, and that re-reads the cited value, catches number
errors in agent-written notes that the current review misses, at a few
seconds per note.

Sources: Zhou 2026 ([arXiv:2611.05251](https://arxiv.org/abs/2611.05251)):
agents fabricate or misreport numbers under task pressure; enforced provenance
as the remedy. Wang et al. 2026 ([arXiv:2609.35900](https://arxiv.org/abs/2609.35900)):
reproduction fails on unstated choices. Inguglia 2026
([arXiv:2605.28916](https://arxiv.org/abs/2605.28916)): auditability of coding
agents.

## Oracle and data

- **Audit set:** 10 merged notes chosen at random (seeded) from those with a
  result archive, e.g. [g7-defaults.md](../g7-defaults.md),
  [c5b-selfcal-masks.md](../c5b-selfcal-masks.md), [f3-flagger.md](../f3-flagger.md).
- **Oracle:** a manual audit of the same notes' result lines against their
  archives, done blind to the checker's output, before the checker is run.

## Tolerance to freeze (proposed)

- **Useful:** the checker finds every mismatch the manual audit finds (recall
  1.0 on the audit set) with ≤ 1 false alarm per note, in ≤ 10 s per note.
- **Not useful:** recall < 1.0, or the citation format adds more than about 10 %
  to a note's length (measured on the audit set).
- Either way, the audit's mismatch count is recorded as a measure of how often
  notes carry wrong numbers.

## Expected cost

Small: a script under `tools/` and a citation convention in V2's contribution
path; no core code. The manual audit is the largest part (about 2 h).

## Owner decisions

1. Approve, and whether it waits for V2's contribution path to land.
