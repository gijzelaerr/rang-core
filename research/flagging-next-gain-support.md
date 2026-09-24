# Original TRAIN gain-support survey

Protocol frozen2026-09-24 before survey computation, using the original
prospective baselines for clean/time-burst-seed107/time-burst-seed109 in
`outputs/tv-next-20260924-01/experiments/prospective`. This survey asks how much
original support meets the existing local full-Jones identifiability condition;
it does not tune the signal guard, change masks or certify safety.

Use every gain bin on the frozen2integration×32channel grid. Recompute the
weighted GN normal matrix with the existing native Rust kernel using only
original TRAIN samples, native four-correlation weights, the actual baseline
full-complex2×2 gains and original scalar calibration model. Rank is the count
of raw normal-matrix eigenvalues strictly greater than1e-10 times its largest
eigenvalue, the native relative cutoff. Active stations are those present in
original TRAIN cross-baseline geometry. Compare raw rank with8*nactive−4,
retaining the current common U2 gauge assumption. Bins with no TRAIN data are
counted separately; over-rank/numerical anomalies are retained if encountered.

Record per-bin sample counts, station/baseline geometry, graph connected
components/bipartiteness, fully/underidentified counts and original TRAIN cells
in each category. Crosscheck each supported bin using native zero-response
`anchored_response(H,0,0,0)` without a new calibration solve. Explicitly verify
the already observed bin811 has two TRAIN cells on baseline0–2, rank8 versus
the two-active-station required12. Do not discard it or any failure after this
survey. This is descriptive artifact replay, not independent data or a
signal-transfer measurement.

Use the existing frozen-code/native-library image with measurement/code
mounts readonly, runtime network disabled and no MS writes, downloads or
Quartical invocations. Only an exclusive generated audit namespace may be
writable, checked at8MiB with8GiB free-disk reserve. Preserve exact source,
commands, receipts, input/tree hashes and thresholds in the new survey archive.

## Measured result

The three baselines have the same support/rank counts:

| Gain bins / original TRAIN cells | Count per case |
| --- | ---: |
|All gain bins|896|
|Bins with original TRAIN samples|288|
|Fully identified supported bins|287|
|Underidentified supported bins|1|
|No TRAIN data bins|608|
|Over-rank/numerical anomalies|0|
|Fully identified original TRAIN cells|73,718|
|Underidentified original TRAIN cells|2|

Thus99.65278% of supported bins and99.997287% of original TRAIN cells meet the
unchanged common-U2 rank condition. No-data bins are not classified as failures.
The sole underidentified bin is811 in all three cases: two TRAIN cells, active
stations0 and2, one connected bipartite baseline edge0–2, raw normal rank8
versus required12. Original support is overwhelmingly locally identified; the
all-original-TRAIN signal guard nevertheless cannot certify its full domain.
Graph connectedness alone does not imply the required gain identifiability.

All864 supported-bin native zero-response decisions agree with the raw-rank
classification;1,751/1,751 survey predicates pass. No DATA, weights, flags,
models, masks, gain grid, eigencutoff or gauge assumptions were changed, and no
new QuartiCal invocation was made. Every case tree and raw-source digest is
unchanged. This follow-up does not change the previous nine-solve signal audit
or retroactively remove its two problematic TRAIN cells.

[The new survey archive](results/gain-tv-next-gain-support.json) retains all
supported-bin rank/sample/graph summaries, complete failure rows, all1,751
predicates, exact code/command, baselines/source/helper hashes and native/runtime
receipts. The complete generated artifact SHA256 is
`e1b89f91fd352d2a3c87cc7adab85052feef49190005de1127cb0958077fe149`;
its namespace allocates1,548,288 bytes, below the checked8MiB allowance, with
the8GiB reserve checked before writing. These are checked reservations, not
OS-enforced quotas.

The next data/experimental-design gate is to predeclare and verify complete
gain-support identifiability before relying on this particular certificate.
A future independently frozen grid/model/support design can be tested; this
survey does not authorize post-hoc exclusion, relaxed gauges, unmeasured safety
or representative-data/novelty claims.
