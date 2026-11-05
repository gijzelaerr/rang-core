# Quality and compute research gates

## Next phase: one decisive algorithm experiment

Checkpoint: 2026-09-11. The simulator and joint-model controls are sufficient to
start a discriminating experiment. The dual-budget selection rule remains a
proposal; additional fitted physics alone is not the contribution.

1. Establish the precise difference from existing solution-interval selection,
   influence-based tuning and joint sky/beam inference. If the proposed rule
   is already established, narrow the contribution or change course.
2. Specify selection using both faint-signal distortion and contamination from
   plausible model errors. Include refitting effects: a frozen local Jacobian
   is only an approximation. Keep relative pointing exactly zero-mean.
3. Predeclare a fair comparison against full regularized joint fitting and
   simple model selection. Match data, sky freedom, tuning effort and stopping
   tolerances; document prior differences. Count all selection and diagnostic
   overhead, not just the final fit.
4. Run a small paired-seed falsification campaign with matched and out-of-family
   beams, missing faint sources and gain mismatch. Separate tuning and final
   test data. Measure absolute flux bias, finite-injection response/distortion,
   relative pointing and held-out prediction separately.
5. Fix science tolerances and seed counts before the campaign. Proposed go/no-go
   targets: at least 2x lower end-to-end runtime with no more than 5% degradation
   in predeclared quality metrics and no breach of absolute flux tolerances;
   alternatively, at least 20% lower flux or image error at matched compute
   without material regression elsewhere. These thresholds need justification
   for the chosen experiment and are not achieved results. Stop extending this
   candidate if a fairly tuned joint fit removes the advantage.
6. Only for a surviving candidate, broaden truth realizations, prior sensitivity,
   unseen source locations and image-domain tests. Record hardware, cold/warm
   timing and peak memory. Fewer parameters or faster isolated QR is insufficient.
7. Resolve real-data antenna/coordinate conventions, obtain suitable science-field
   observations and verified geometry, and choose an established comparator with
   Oleg. Match supported physics and inputs. Reference pointing scans alone
   cannot demonstrate continuous science-field calibration.

Planning estimate: several focused days for an initial go/no-go experiment;
weeks for a robust comparison if it succeeds. Real-data progress depends on
metadata and suitable observations. This is not a promise of discovery.

## Supporting validation backlog

The objective is a demonstrable quality or efficiency advance over a relevant
state-of-the-art calibration/imaging method. Joint fitting, splines, automatic
differentiation, zero-mean constraints and QR elimination are not individually
novel. Our gain-only simulation is a control, not a state-of-the-art comparison.

Use these gates to support the focused experiment, preserving negative results;
they are not ten prerequisites to another novelty decision:

1. Beam mismatch: controlled width, squint and antenna-dependent errors.
2. Gain flexibility: smooth frequency-dependent gains; quantify lost pointing information.
3. Out-of-family pointing: sinusoidal motion and jumps, beyond fitted splines.
4. Sky incompleteness: spectral mismatch, missing and extended sources.
5. Uncertainty coverage: repeated-noise tests and prior sensitivity.
6. Common pointing: map adequacy against true shared offset and external information.
7. Validation: contiguous gaps, baseline holdouts, initializations and separate tuning data.
8. Measured history: establish coordinate/record semantics before drift statistics.
9. Scaling: verified 64-antenna coordinates; measured runtime and peak memory.
10. Real observation: matched data/sky/beam comparison against an established pipeline.

For quality claims, compare visibility prediction, flux bias and image residuals
at matched compute. For efficiency claims, match output accuracy and report
hardware, warm/cold timings, convergence tolerance and peak memory. End-to-end
pipeline costs matter; a faster isolated kernel is insufficient.

Potential research direction, not an established result: use information after
accounting for uncertain sky and gains to decide which physical pointing/beam
parameters to fit, with predictive checks detecting inadequate models. This
must beat ordinary regularized joint fitting and relevant existing methods;
previous simulated mode-selection tests did not demonstrate an accuracy advantage.

Historical data inspection (gate 8) already identified missing/repeated records;
external clarification is needed before a physically grounded drift model.
This does not block synthetic tests, but limits what we can claim about them.
