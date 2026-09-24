# Supported native MeerKAT L-band data and partial-Jones identifiability

Read-only research on 2026-09-24, after the reportable-work protocol freeze
`afe721f`. No new visibility downloads, Measurement Set conversion, flag writes,
solver runs or change to the previously measured all-four-positive-weight
eligibility protocol. Numeric diagnostics and source hashes are in
[meerkat-supported-data-candidates.json](results/meerkat-supported-data-candidates.json).

## Outcome and ranked next actions

1. **Investigate the already acquired primary calibrator's native
   SIGMA_SPECTRUM.** Both ESO137 tiles retain finite, strictly positive sigma
   values and nonzero DATA in all four correlations, despite zero XY/YX
   WEIGHT_SPECTRUM. QuartiCal supports selecting the original sigma column and
   computing inverse-square weights internally. This offers a possible
   full-four-correlation, complex-2x2 experiment without another visibility
   download. It requires a separately frozen noise-source protocol, credible
   DATA/sigma provenance, safe exact string/subtable conversion and gain-support
   checks. It is not yet an accepted calibration dataset or a solved result.
2. **Keep the existing native SKA pointing archive as a bounded full-correlation
   diagnostic.** All five original local scans have positive spectral weights
   in every correlation. They are already native Measurement Sets, with original
   flags and a known calibrator field. However, there is no original MODEL_DATA;
   our supplied scalar sky is approximate, the scans use only four antennas and
   share one reference-pointing observation. They do not establish independent
   observation transfer or representative science-field performance.
3. **For a genuinely independent observation, obtain metadata/provenance for a
   publisher-provided small native full-polarization calibrator subset before
   any acquisition.** Require all four correlation products, received
   FLAG/FLAG_ROW, DATA and an explicit native noise convention, complete
   subtables, export/calibration history and an appropriate calibrator sky.
   SARAO archive conversion supports bounded subsets, but archive access is
   restricted and requires registration/token authorization. This is not an
   anonymous ready-to-use candidate verified here.
4. **Treat parallel-hand-only full-Jones TV as a new research protocol, not a
   workaround.** The current common-right-unitary gauge is insufficient for
   that likelihood. A row-wise quotient/gauge and rank/support safeguards would
   need independent design and tests before measurement. Diagonal calibration
   can still be useful, but relabelling it as the requested identified full-2x2
   objective would be incorrect.

No additional small, independently observed, anonymous real MeerKAT L-band
dataset with verified full-correlation noise weights, original flags **and** a
validated calibrator sky was established in this search. This is a bounded
search result, not a claim that none exists. The
[SARAO cookbook](https://github.com/ska-sa/MeerKAT-Cookbook) and
[data-format guidance](https://skaafrica.atlassian.net/wiki/spaces/ESDKB/pages/1452376079/Data+formats)
describe the authorized archive/subset route. Never use the guidance's example
flag-disabling option: Rang must retain received Observatory flags.

## What the local public data actually show

The [AWS registry](https://registry.opendata.aws/meerkat-eso137-006/) lists
`ms1_primary.zarr`, `ms1_target.zarr` and `ms2_target.zarr`. The
[pinned publisher documentation](https://github.com/ratt-ru/ratt-public-open-data-tutorial/blob/8c8c1c97c629b0a13d7c13b4b61b901f77cff88c/documentation.md)
identifies the primary as PKS1934-638 and reports a CARACAL/CASA/CubiCal
processing chain. Actual primary numeric metadata/pilots establish 61
participating antennas, native L-band channels and XX/XY/YX/YY. The target sets'
weight values have not been decoded here; their advertised columns or shapes
cannot establish that they share the zero-cross-hand convention.

Each acquired primary tile contains 30,256 rows ×128 channels ×4 correlations,
16 integrations, native channels1024:1152, 1070–1096.541015625MHz. In scans1
and3, each correlation has3,872,768 finite, nonzero DATA values. Positive
WEIGHT_SPECTRUM counts are `[3872768,0,0,3872768]`; positive SIGMA_SPECTRUM
counts are `[3872768,3872768,3872768,3872768]`. Received row WEIGHT and SIGMA
are both1. No column is replaced or repaired by these diagnostics.

Received flags retain80.489%/80.297% of cells as bad. There are755,614/763,051
unflagged cross-baseline row-channel cells before the all-four-positive
spectral-weight criterion, which still yields **zero** eligible cells under the
original frozen protocol. With positive native sigma, these counts describe
potential support only. Native antenna ID21 has no received-unflagged cross
sample in either tile. The union graphs support60 antennas and1769/1768
baselines, are connected and non-bipartite; individual native time/channel
graphs can have much weaker support. Do not infer full gain-bin support from
the union graph, infer an antenna name from its ID, or clear its flags.

Read-only inspection of the five original local SKA scans1/4/5/8/9 finds no
zero/nonfinite native spectral weights in any correlation. Positive counts per
correlation are81,920 in each20-row scan and573,440 in the140-row scan9.
Thus zero XY/YX spectral weights are **not a general MeerKAT export convention**.
Their broader occurrence in ESO137 remains unknown.

Other primary-source leads do not satisfy the present boundary: the
[IDIA DEEP2 tutorial](https://idia-pipelines.github.io/docs/processMeerKAT/deep-2-tutorial/)
uses an11GB16-dish dataset on authenticated Ilifu storage; the
[SKA MIGHTEE example](https://developer.skao.int/projects/ska-telescope-ska-sdp-wflow-mid-selfcal/en/latest/example.html)
uses a91GB subset and imaging-derived sky; the
[MeerSOLAR sample record](https://zenodo.org/records/16068485) advertises a
2,636,214,567-byte solar MS tarball, exceeding the new2GiB raw allocation before
unpacking/backups and without verified calibrator/full-correlation weight
provenance. None was downloaded or promoted to eligible status.

## Actual QuartiCal and CARACAL weight handling

Pinned QuartiCal0.2.7 maps to official commit
`d01487e3091aab03beca71128858e724b087d6e3`. Installed source bytes match the
official release for the two critical functions.

- [initialize_weights/sigma_to_weight](https://github.com/ratt-ru/QuartiCal/blob/d01487e3091aab03beca71128858e724b087d6e3/quartical/weights/weights.py):
  an explicitly selected weight column is used as supplied; two-dimensional
  row weights are broadcast across channels. There is no automatic replacement
  of zero XY/YX spectral weights by row weights. Selecting sigma computes
  `1/sigma**2` where sigma is nonzero. Weight and sigma selectors are exclusive.
- [Flag initialization](https://github.com/ratt-ru/QuartiCal/blob/d01487e3091aab03beca71128858e724b087d6e3/quartical/flagging/flagging.py):
  in four-correlation mode, `corr_sel=slice(0,4,3)` checks missing DATA/zero
  weights only in XX/YY. Zero XY/YX weights alone do **not** auto-flag the whole
  sample. Nevertheless, any received correlation FLAG or FLAG_ROW propagates
  to the internal aggregate row-channel flag. A pure in-memory initializer
  check with weights `[1,0,0,1]`, nonzero DATA and no flags returns unflagged.
- [Complex kernel](https://github.com/ratt-ru/QuartiCal/blob/d01487e3091aab03beca71128858e724b087d6e3/quartical/gains/complex/kernel.py):
  the four-correlation normal equations multiply each correlation derivative by
  its own weight (lines570–587). Zero off-diagonal weights provide no
  cross-hand information. Selecting `[0,3]` uses the two-correlation/reduced
  gain representation, not a four-entry Jones solve merely because the term
  is named `complex`.

The [pinned option schema](https://github.com/ratt-ru/QuartiCal/blob/d01487e3091aab03beca71128858e724b087d6e3/quartical/config/argument_schema.yaml)
recommends the sigma selector when calibration may already have altered
weights. A possible future command would select
`input_ms.sigma_column=SIGMA_SPECTRUM`, leave `weight_column` unset, retain all
four correlations and preserve every received weight/sigma column unchanged on
disk. This is a new, auditable noise-source choice, not permission to change
the earlier measurement protocol or proof that this archive's sigma convention
is correct. The [MSv2 specification](https://casa.nrao.edu/Memos/229.html)
prefers supplied spectral weights to row weights; the
[CASA weight documentation](https://casadocs.readthedocs.io/en/stable/notebooks/data_weights.html)
distinguishes DATA noise estimates from weights modified by calibration.

Pinned CARACAL revision `8f7bb363876f5f0daecbf2167c36bb597c7e5160`:
[prep_worker](https://github.com/caracal-pipeline/caracal/blob/8f7bb363876f5f0daecbf2167c36bb597c7e5160/caracal/workers/prep_worker.py)
can initialize uniform weights with CASA, estimate them through msutils, or
delete WEIGHT_SPECTRUM. These are explicit mutations and are inappropriate as
silent repairs of Rang's immutable input. The inspected msutils1.2.0
[weight writer](https://github.com/shinobi-dosho/msutils/blob/e2946f7efdea8dd8dace06671da67bc828fe60c5/MSUtils/ClassESW.py)
broadcasts spectral specifications to all correlations; it does not prescribe
zero XY/YX. CARACAL
[selfcal_worker](https://github.com/caracal-pipeline/caracal/blob/8f7bb363876f5f0daecbf2167c36bb597c7e5160/caracal/workers/selfcal_worker.py)
passes its configured weight-column name to CubiCal; its documented default
is WEIGHT. Neither default establishes the ESO137 publisher's actual settings.
Official katdal
[MS writing](https://github.com/ska-sa/katdal/blob/142dd342c886d35f9cc8defda3ad8ea1028fc880/src/katdal/ms_extra.py)
retains supplied spectral weights and writes sigma from them, while
[mvftoms](https://github.com/ska-sa/katdal/blob/142dd342c886d35f9cc8defda3ad8ea1028fc880/src/katdal/scripts/mvftoms.py)
requires explicit full-polarization selection to export four products.
This current source does not prove the historical publisher's export process.

There is therefore **no verified publisher explanation** for these zeros.
Processing-induced changes are plausible, but remain an inference.

## Native-sigma consistency diagnostic, not weight validation

Use every originally unflagged finite cross-baseline sample in the acquired
window; do not optimize a channel selection. For adjacent channels where
**both** received samples remain unflagged, define

`z=(DATA[c+1]-DATA[c])/sqrt(SIGMA_SPECTRUM[c+1]^2+SIGMA_SPECTRUM[c]^2)`.

Report separate real/imaginary median-centred `1.4826*MAD` and complex RMS;
assume neither a real-component nor complex-RMS sigma convention. The selected
adjacent-pair counts are270,604/245,013. These overlap, are conditioned on
publisher flags, may contain correlated channels or residual physical sky/gain
structure, and are not independent noise replicates.

| Scan | XX real/imag MAD | XY real/imag MAD | YX real/imag MAD | YY real/imag MAD |
| --- | ---: | ---: | ---: | ---: |
| 1 | .51686/.51625 | .71956/.72222 | .72099/.72182 | .52119/.52273 |
| 3 | .50058/.50212 | .71685/.71432 | .71494/.71329 | .51420/.51489 |

Complex RMS is≈1.01–1.02 in cross-hands but≈.696–.717 in parallel hands.
This is a systematic hand-dependent difference, **not proof of a single
validated noise scale**. Parallel-hand flag conditioning, averaging/correlation,
calibration history or differing sigma definitions could contribute. XY/YX
sigma arrays are not identical; their median ratios are1.01035/1.01406 and
their5–95% ranges are.8535–1.1910/.8472–1.2016. Do not impose equality.

Native `WEIGHT_SPECTRUM*SIGMA_SPECTRUM**2` medians for XX/YY are
.44824/.43273 in scan1 and.44505/.43583 in scan3; their broad baseline/channel
distributions differ from1. Cross-hands have exactly0 for this product.
These stored columns are not simply reciprocal descriptions of one variance.
The archive records baseline-median and channel-median quantiles, without
fitting new weights or changing flags. Original DATA/sigma processing history
is still needed before selecting a justified new noise-source experiment.

## What parallel hands identify with a scalar-unpolarized sky

This section is a derivation for the current scalar model, not a claim about
general polarized/full-RIME calibratability. The full-correlation unitary
ambiguity is described by
[Smirnov2011, section1.5](https://arxiv.org/html/1101.1765#S1.SS5).

For known nonzero scalar coherency `M_pq=s_pq I`,
`V_pq=s_pq J_p J_q^H`. Write the two Jones rows as complex vectors
`x_p,y_p` in C². The weighted parallel hands measure only

`XX_pq/s_pq=x_p x_q^H`, `YY_pq/s_pq=y_p y_q^H`.

For every common pair of unitary matrices `U_X,U_Y`, replacing
`x_p→x_p U_X` and `y_p→y_p U_Y` preserves both observables. Thus there is
an exact independent-row `U(2)×U(2)` symmetry, rather than only the common
right `U(2)` of a full-correlation unpolarized solve. When each row family
spans C², its orbit has8 real dimensions. Cross-hands depend on the relative
orientation `U_X U_Y^H`, which this likelihood cannot determine. Missing
baselines/flags can introduce further degeneracies; eight is not a universal
upper bound on all null directions.

An analytic real Jacobian uses
`dV_pq=dJ_p J_q^H+J_p dJ_q^H`. Small in-memory checks on complete
cross-baseline graphs, no autos, scalar flux1, confirm:

| Antennas / real parameters | Jones | Parallel-hand rank / nullity | Four-correlation rank / nullity |
| --- | --- | ---: | ---: |
| 4 /32 | generic | 24 /8 | 28 /4 |
| 4 /32 | identity | 14 /18 | 28 /4 |
| 8 /64 | generic | 56 /8 | 60 /4 |
| 8 /64 | identity | 30 /34 | 60 /4 |

Generic matrices are independent normal real/imaginary draws from NumPy PCG64
seed271828, drawn first for4 then8 antennas. Parameters interleave real/imag
in flattened antenna/row/column order. Rank threshold is `1e-10*s_max`;
central difference step1e-6 agrees with the analytic Jacobian within
5.124e-10. This is a gain-only algebra diagnostic, not a QuartiCal measurement.

At diagonal/nonzero gains with zero leakage, the parallel-hand derivative
with respect to every leakage parameter vanishes: leakage enters the
parallel visibility quadratically. On a connected non-bipartite graph,
amplitude-sum and phase-difference incidence matrices give `2N-1` observable
real scalar-gain directions per hand. Hence identity rank is `4N-2` among
`8N` full-Jones parameters. In an ideal complete61-antenna graph this is
242 observable directions and246 first-order null directions. Many of these
null directions become observable at second order; they are not all finite
gauge freedoms. The actual received graph supports only60 antennas and may
fragment per bin, so the ideal count is not an actual-pilot rank measurement.

With independent gain bins, `U_X(t,ν)` and `U_Y(t,ν)` can change with time
and frequency without altering the supported parallel-hand likelihood.
Smoothness/initialization may select a representative but cannot restore the
missing relative polarization information. A common polar-reference gauge
does not remove the extra row freedom.

Concrete fixed-support counterexample: all antennas initially have `J=I`.
In four time bins replace every X row by `[cosθ,sinθ]`, retain Y row`[0,1]`,
and use θ`[0,.3,.6,.9]` radians in two identical frequency bins. XX/YY stay1
to1.111e-16, but cross-hand predictions change by up to.78332691. After the
existing common-right polar gauge, the original native Rust TV is0 while the
transformed TV is.21193321649951627, with all cells valid, unchanged grid,
edge support and fixed scale1. This proves that the existing TV objective is
gauge-dependent on this partial-correlation domain. It does **not** imply
that the data are generally uncalibratable, that no row-Gram/diagonal
calibration is possible, or that a polarized/full-support dataset has this
same enlarged ambiguity.

## Safe string/provenance conversion: design only

Current metadata describe protocol5 pickle filters on object-string chunks.
The already inspected numeric receipt intentionally excludes those arrays.
HISTORY contains21 rows, including APPLICATION, APP_PARAMS, CLI_COMMAND,
MESSAGE and ORIGIN: exact textual history could clarify weight/sigma processing
before conversion. It is not currently decoded. FEED polarization labels and
other required subtables also need exact provenance; telescope/field/antenna
names must never be invented from numeric IDs or documentation alone.

Preferred route is a publisher-provided plain UTF-8/JSON sidecar bound to the
same dataset receipt. Otherwise, first freeze exact tiny-object paths,
metadata/header/ETag/byte limits, allocation/reserve and parser rejection
policy. Download only those bounded non-visibility objects after approval.
Bound compressed and declared decoded sizes before Blosc decoding.

`pickletools.genops`/disassembly is inspection, not deserialization. A possible
subsequent parser would be a **non-executing symbolic interpreter**, never
`pickle.load/loads`, a generic restricted Unpickler, dynamic imports or callable
REDUCE/BUILD execution. It may recognize only the exact NumPy object-array
serialization scaffold as inert symbols and bounded primitive Unicode,
integer, list, tuple and memo operations. The reconstructed output must have
the exact frozen shape, object dtype, expected element count and only bounded
UTF-8 strings. Unknown constructors/opcodes, arbitrary numeric dtypes, object
instances, recursive aliases, unsupported protocol/out-of-band buffers,
oversized stack/memo/string/frame and trailing bytes must fail closed. Tests
must include malicious GLOBAL/REDUCE, constructor spoofing and allocation
bombs. No parser is implemented or remote pickle executed in this research.

After safe provenance access, a new conversion must preserve all received
columns and flags exactly, recreate complete valid subtables and mappings,
compare read-back DATA/flags/native weight/sigma digests and keep raw receipt,
exclusive original/work copies and backups. Only then may a separately frozen
full-correlation native-sigma calibration experiment be considered. The
previous zero-eligible result remains a valid negative finding under its
original native-WEIGHT_SPECTRUM protocol.
