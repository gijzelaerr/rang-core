# Native string/HISTORY provenance gate

Premeasurement implementation protocol, recorded2026-09-24. Implements the
previous [bounded design](flagging-supported-provenance-plan.md); no new outcomes
are available at this freeze. The user requests five parallel workstreams;
root schedules this metadata-only track separately from calibration tracks.

## Frozen scope and execution gates

Exactly82 nonempty object-string chunks/505 elements plus three numeric HISTORY
chunks from the already pinned ESO137 primary metadata. Fixed HTTPS origin and
exact allowlist, no redirects, credentials, arbitrary keys, MAIN/visibility or
target requests. Compressed limit65536 bytes/object and1048576 bytes total;
decoded limits identical. Numeric HISTORY lengths168/84/84 bytes. Metadata
input888855 bytes/SHA68fdb7f4f5f9392181bf645bd8e792e4dd96bd9857ad6489091b441adc59bbaa.
An8GiB disk reserve and fresh, nonnested, exclusive outputs are required.
Each fresh stage additionally enforces a checked8MiB logical-file cap, including
metadata copies, payloads, derived text and receipts; this is not an OS quota.

Stages are distinct: `head(run_dir,metadata_path)` requests only headers;
`acquire(run_dir,head_dir)` requires an independently approved complete frozen
HEAD receipt and conditional GETs; `run(run_dir,acquired_dir)` validates receipts
and extracts bounded text offline. Root owns actual network execution, stores,
curation and commits. No network is authorized by invoking the offline recipe.
Every stage records source/module hashes and preserves failure evidence.
HEAD and GET need separate root go-aheads after source/tests/receipts freeze.

Do not call remote pickle.load/loads/Unpickler, imported GLOBALS, reducers,
constructors or __setstate__. The decoder uses pickletools plus an inert
symbol/array/dtype grammar. PROTO5, approved NumPy reconstruction scaffold,
object dtype, exact shape/count and bounded Unicode only; unknown scaffold,
recursive containers, out-of-band buffers, malformed/trailing bytes or unknown
opcodes fail closed. Blosc declared sizes are checked before decompression.
Do not instantiate Zarr's default object/pickle codec. The publisher's producer
version remains unknown; safe extraction may legitimately refuse its payloads.

Adversarial tests precede any network acquisition: local known-safe string-array
serialization, old/new module spelling, repeated/empty strings, arbitrary
globals/reducers, protocol/dtype/shape/count mismatch, recursion, oversized
frames/Unicode/memo/stack, malformed/truncated/trailing streams, invalid Unicode,
Blosc allocation bounds, incomplete/duplicate/tampered receipts, redirect/ETag/
length/cap checks and fresh-output/symlink containment. Tests may serialize local
controlled objects; they must never execute untrusted pickle bytecode.

## Scientific interpretation stays gated

The output is received metadata/text evidence, not a validated noise source or
native Measurement Set. Received strings and numeric history rows retain their
native ordering. Extract HISTORY application/commands/parameters/messages as
data, never run them. Report possible references to applycal/calwt, initweights,
statwt, robust weights, averaging and DATA/CORRECTED_DATA, but do not infer an
operation merely from a keyword or infer that absent text proves no mutation.

Existing61-antenna pilots have native zero XY/YX WEIGHT_SPECTRUM and positive
SIGMA_SPECTRUM. Exact publisher DATA/sigma units, exporter/calibration settings,
weight-column processing and averaging/sigma regeneration are still required.
Measure-reference/units keywords are missing from the inspected dask-ms attrs;
safe string extraction does not invent them. No row-weight fallback, sigma
rescaling, flag clearing, native-MS conversion or QuartiCal solve is authorized
here. Source DATA, FLAG/FLAG_ROW and all native weight/sigma columns stay intact.

The primary archive and two scans are one observation. Textual provenance is
not independent-observation transfer, imaging validation or a matched SOTA win.
Missing provenance remains an explicit conversion/solver gate. Original strict
all-four-positive-WEIGHT_SPECTRUM eligibility stays zero; this track cannot
retroactively relabel that result.

Implementation/tests/actual-header/text receipts will be recorded separately
after measurement. At this premeasurement checkpoint: pending, not successful.

## Implementation verification, before publisher measurements

`rangtoy.flagging_provenance` and the offline
[Stimela2 recipe](../recipes/tv-flagging-provenance.yaml) are implemented.
All83 targeted tests pass on host Python3.14.7/NumPy2.5.3; Ruff check/format pass.
Tests use controlled local serialization and mocked HEAD/GET/decompression,
including an end-to-end85-object receipt/text workflow. No publisher object has
yet been requested or decoded by this track.

An additional controlled offline Linux check uses image
`sha256:102767125ea2fe1f7fc000738cb16e28d1e967188c227a583d27293596fb2d95`,
NumPy2.5.3 and numcodecs0.15.1. Real Blosc encode/decode and inert recognition
pass for85 locally constructed shape-matched chunks/505 strings,17219 decoded
bytes; zero HEAD/GET requests and zero unpickle calls. The first launch selected
the image's default Stimela entrypoint and failed on a read-only runtime home
before the test; retry with explicit `--entrypoint python` succeeds. Neither
launch writes the repository or acquires remote data.

Example separately gated root stage commands, from the pinned environment:

```sh
python -m rangtoy.flagging_provenance head outputs/fresh-head metadata.json
# Only after independently checking/freezing the complete HEAD receipt:
python -m rangtoy.flagging_provenance acquire outputs/fresh-acquired outputs/fresh-head
# Offline, and only after receipt/source checks:
python -m rangtoy.flagging_provenance inspect outputs/fresh-inspect outputs/fresh-acquired
```

The decoder dependency is explicitly numcodecs0.15.1; host lacks that package
and is not silently substituted. All stage targets are fresh/exclusive, all
input file reads are bounded and reject symlink ancestors, and module/source
guards are checked at completion. Root will add actual approved HEAD/acquisition/
text hashes and findings separately. Scientific conversion/sigma gates remain
unvalidated even when the software checks pass.

## Actual bounded recovery2026-09-24

HEAD85 passed complete separate root/agent checks before conditional GET85.
Compressed total15,672bytes/max546; decoded16,538bytes,505strings and21 HISTORY
rows safely recognized offline. Native field J1939-6342 recovered. CASA5.6.0-60
split settings record source`../ms-orig/1557433849_sdp_l0.ms`, output
`ms1_primary.ms`, field0,datacolumn=all,keepflags=True,width1,timebin=0s.
The21 rows describe one recorded split, not21 independent operations.
CLI_COMMAND/APP_PARAMS are empty and inspected HISTORY has no applycal/calwt/
initweights/statwt/weight/sigma mentions. This does not prove absence of other
processing or validate DATA-associated noise/measure frames. Conversion/sigma
solver gates remain false; no MAIN request, native-MS conversion or new QC.

[Exact recovery archive](results/gain-tv-next-provenance.json) and
[657-predicate independent verification](flagging-next-provenance-verification.md)
preserve source/payload/code/runtime receipts and the inert replay program.
