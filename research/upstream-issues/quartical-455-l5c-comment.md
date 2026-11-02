# QuartiCal #455: comment with the L5-C result

Repository: ratt-ru/QuartiCal. Status: **posted 2026-11-02 (U4), https://github.com/ratt-ru/QuartiCal/issues/455#issuecomment-6577475036**. Text from
[../l5c-casa-gaincal.md](../l5c-casa-gaincal.md), "For the coordinator", verbatim. The older
"L5 numbers" section of `upstream-notes.md` is not part of this comment.

<!-- issue-body -->
CASA 6.7.6 `gaincal` G solved on the same 2 × 32 intervals of the LUNO four-station slice is slowest in the same intervals as QuartiCal 0.2.7's `complex` (measured with rang's validated port of it: Spearman 0.70 of the per-interval distance to each solver's own long run; all 4 intervals whose products still move by 1e-4 between 50 and 500 iterations are unsettled for CASA; post hoc, all 7 intervals with a gain failing the 1e-7 test at 50 iterations are in CASA's top 2 %, and six of the seven are under-constrained: an antenna with one observed baseline, or no observed triangle). CASA shows no tail because its chi-squared stop ends earlier (its own 50-iteration cap never binds; its products stay 4e-5 median from its restarted solution), with a held-out error within 1e-4 of the port's. This supports counting only constrained intervals in the stop fraction.
<!-- /issue-body -->
