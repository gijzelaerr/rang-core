# Bounded native-string and weight-provenance plan

Design recorded 2026-09-24, after the read-only diagnostics in
[flagging-supported-data.md](flagging-supported-data.md). This is **not** an
acquisition receipt, implemented parser, decoded HISTORY, native-MS conversion
or calibration result. No new object was downloaded or remotely unpickled in
preparing it. Freeze and review each following stage before its execution;
unsupported input remains a reported failure, not grounds to broaden a decoder.

## Exact source and requested objects

Use only the already present consolidated metadata:

- Local input: `outputs/tv-public-acquired-20260924-01/metadata.json`.
- Size: 888855 bytes; SHA256:
  `68fdb7f4f5f9392181bf645bd8e792e4dd96bd9857ad6489091b441adc59bbaa`.
- Literal HTTPS object base:
  `https://ratt-public-data.s3.af-south-1.amazonaws.com/ESO137/ms1_primary.zarr`.

Its nonempty object arrays require exactly **82 chunks containing 505 string
elements**. All have `zarr_format=2`, C order, `dtype="|O"`, pickle filter
`{"id":"pickle","protocol":5}`, and Blosc LZ4 compressor, level5, shuffle1,
blocksize0. Shapes equal chunk shapes, so each array has one chunk. The following
brace/range notation defines a finite allowlist, not a filesystem/network glob:

| Exact relative key(s) | Shape / strings per chunk | Chunk count |
| --- | --- | ---: |
| `ANTENNA/ANTENNA_0/{MOUNT,NAME,STATION,TYPE}/0` | `[61]` /61 | 4 |
| `FIELD/FIELD_0/{CODE,NAME}/0` | `[1]` /1 | 2 |
| `HISTORY/HISTORY_0/{APPLICATION,MESSAGE,ORIGIN,PRIORITY}/0` | `[21]` /21 | 4 |
| `HISTORY/HISTORY_0/{APP_PARAMS,CLI_COMMAND}/0.0` | `[21,1]` /21 | 2 |
| `OBSERVATION/OBSERVATION_0/{LOG,SCHEDULE}/0.0` | `[1,1]` /1 | 2 |
| `OBSERVATION/OBSERVATION_0/{OBSERVER,PROJECT,SCHEDULE_TYPE,TELESCOPE_NAME}/0` | `[1]` /1 | 4 |
| `SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/{FREQ_GROUP_NAME,NAME}/0` | `[1]` /1 | 2 |
| `STATE/STATE_0/OBS_MODE/0` | `[3]` /3 | 1 |
| `FEED/FEED_n/POLARIZATION_TYPE/0.0`, integer `n=0..60` | `[1,2]` /2 | 61 |

Thus 21 non-FEED chunks contain383 strings; 61 FEED chunks contain122.
Reconcile all expanded keys and element counts against the pinned metadata,
reject duplicates, and use numeric FEED group order when preserving row order.
Do not infer an antenna name from its native numeric ID.

For chronology/row references, add exactly three filter-free numeric chunks:

| Relative key | Native dtype / shape | Exact decoded bytes |
| --- | --- | ---: |
| `HISTORY/HISTORY_0/TIME/0` | `<f8` / `[21]` | 168 |
| `HISTORY/HISTORY_0/OBSERVATION_ID/0` | `<i4` / `[21]` | 84 |
| `HISTORY/HISTORY_0/OBJECT_ID/0` | `<i4` / `[21]` | 84 |

This yields an **85-object** proposed HEAD/acquisition plan. Six empty object
arrays need no chunk GET: `FLAG_CMD/FLAG_CMD_0/{COMMAND,REASON,TYPE}`,
`POINTING/POINTING_0/NAME`, and `PROCESSOR/PROCESSOR_0/{SUB_TYPE,TYPE}`. Their
metadata shapes and chunks are `[0]`; preserve explicit empty-table status.

## Network and receipt bounds, before decoding

Exact compressed sizes and ETags are **unknown**: consolidated metadata do not
contain them. First execute only the frozen HEAD plan, after root approval.
Require success, unchanged literal origin/path, no redirects, explicit positive
Content-Length and a present ETag. Cap each compressed object at65536 bytes and
the 85-object sum at1048576 bytes. Freeze the complete successful HEAD receipt
before any GET. A missing/oversized object fails the entire plan; do not select
the surviving chunks or relax limits automatically.

For separately approved GETs, require the HEAD ETag through an HTTP conditional
request, reconcile response length/ETag and exact bytes read, and compute SHA256
of each received compressed object. ETag is an identity validator, **not** an
assumed cryptographic checksum. Retain both headers and hashes. Abort on changed
objects, excess bytes or trailing response data. Use a fresh exclusive output
directory, disjoint from all inputs, with no symlink traversal; preserve failed
receipts rather than overwriting them. Check the8GiB free-disk reserve first.
Allow no MAIN/target/visibility request, credentials, endpoint substitution or
arbitrary user-supplied relative key in this stage.

Offline validation independently reconciles all85 entries, exact schemas,
headers, file sizes, hashes, duplicate keys, output containment and aggregate
limits **before** loading payloads. Validate each Blosc header against actual
compressed bytes and reject declared decoded size above65536 bytes before
decompression; cap the total decoded payload at1048576 bytes, including the336
numeric HISTORY bytes. Numeric decoded lengths must be exactly168/84/84.
Never instantiate Zarr's object codec or decode via its default pickle filter.

## Inert symbolic parser: specification, not implementation

The installed pinned numcodecs0.15.1
[Pickle codec](https://github.com/zarr-developers/numcodecs/blob/v0.15.1/numcodecs/pickles.py)
serializes with `pickle.dumps` and decodes with `pickle.loads`. The latter is
not acceptable for publisher-supplied objects. Its inspected source SHA256 is
`2ed70c6ba70af95e5351824d4787510ec5964662df36fd2cc9975d6eb6d1bf70`.

Use only [pickletools.genops/dis](https://docs.python.org/3/library/pickletools.html)
to inspect bytecode and a purpose-built inert recognizer. Do not call
`pickle.load/loads`, `Unpickler`, a generic restricted unpickler, imported
GLOBALS, constructors, reducers or `__setstate__`. Recognized names become
private symbolic tokens, never Python classes/functions. Final output is a
bounded list of ordinary strings plus the already frozen shape.

The [NumPy2.5.3 serializer source](https://github.com/numpy/numpy/blob/v2.5.3/numpy/_core/src/multiarray/methods.c)
uses its ordinary array reducer for object dtype even with protocol5, rather
than the numeric-array PickleBuffer path. It emits reconstruction arguments and
an array state containing version, shape, dtype, order and a list of objects.
Inspected source SHA256:
`8e02810a64c7560711892547e9785696edbba9c9df0a9e2044f785976fb12e44`.
Controlled local string-array serialization showed the scaffold below; **the
publisher's producer NumPy version and actual scaffold are not yet known**.

Proposed accepted contexts, handled symbolically only:

1. `PROTO=5`. A `STACK_GLOBAL` may name only
   `numpy._core.multiarray._reconstruct` or its old
   `numpy.core.multiarray._reconstruct` spelling, `numpy.ndarray`, or
   `numpy.dtype`, with those exact module/name strings.
2. One reconstruction `REDUCE` with inert arguments
   `(ndarray_symbol, (0,), b'b')` produces a private array token, not an ndarray.
3. One dtype `REDUCE` with `('O8', False, True)` produces a private dtype token;
   its sole `BUILD` state must be `(3,'|',None,None,None,-1,-1,63)`.
4. The sole array `BUILD` state must be
   `(1, exact_metadata_shape, validated_dtype_token, False, flat_string_list)`.
   Shape dimensions and string count must match that particular frozen object;
   here each object has at most61 elements. No subclass, fields, extra state or
   alternate constructor is accepted.
5. `STOP` must end the sole complete array expression and the byte stream.
   Empty string elements are allowed; missing elements are not filled in.

Primitive tuple/list, integer, boolean, `None`, Unicode, MARK and memo opcodes
are accepted only where required by that grammar. Short/long Unicode lengths
are validated against the bounded input before argument parsing. The only bytes
literal allowed is scaffold `b'b'`; arbitrary byte-valued array elements fail.
Support `APPEND` as well as `APPENDS` for single-element arrays. Keep memo
references bounded, sequential on insertion and valid on lookup; do not permit
recursive container aliases. Reject unknown opcodes, alternate protocols,
out-of-band buffers, persistent IDs, extension codes, arbitrary `GLOBAL` calls,
`NEWOBJ/NEWOBJ_EX`, extra `REDUCE/BUILD`, malformed frames and trailing bytes.

Additional hard limits: nesting16, stack2048, memo4096, opcodes10000 and8192 UTF-8
bytes per string. Validate Unicode without surrogate replacement; reject NUL.
History line breaks are data, never executable commands. Escape control
characters when displaying bounded JSON; retain exact input bytes and hashes.
Any legitimate payload outside this narrow grammar requires a separately
reviewed revision, not fallback unpickling.

Before accepting remote payloads, require tests covering known local1D/2D/empty
string arrays and memoized repeated strings, old/new module spellings, forbidden
reducers/globals, recursive references, oversized lengths/frames/strings,
malformed/truncated/trailing bytecode, dtype/shape/count mismatches, invalid
Unicode and Blosc size bombs. Prove that no recognized path imports or invokes
a payload-selected callable. A parser success certifies bounded textual
extraction, not truthful scientific history.

## Evidence needed for native DATA/sigma calibration

The current pilots preserve all received noise columns, but
`WEIGHT_SPECTRUM*SIGMA_SPECTRUM**2` is not1 and XY/YX spectral weights are0.
Positive sigma and approximately sensible adjacent-channel statistics alone
cannot establish the missing provenance.

[CASA's weight definitions](https://casadocs.readthedocs.io/en/stable/notebooks/data_weights.html)
distinguish DATA-associated sigma from CORRECTED_DATA-associated weights:
`applycal(calwt=True)` can update weights without updating sigma, whereas
averaging/manipulation can update DATA and sigma together. This is an actionable
explanation to investigate, **not evidence that this publisher did so**.

Seek, in original HISTORY and publisher configuration/logs:

- Exporter/CASA/CARACAL/CubiCal versions and full-polarization export settings;
  original DATA units and whether DATA was replaced by corrected visibilities.
- Actual `applycal` calls, `calwt`, calibration tables and selected output/data
  columns; any separate robust/residual-weight output column and copy operation.
- `initweights`, `statwt`, weight-column deletion/rewriting, and explicitly
  cross-hand-specific suppression or initialization.
- `split`, `mstransform`, channel/time averaging, smoothing and relevant sigma
  regeneration, with bandwidth/exposure and flags preserved through export.
- The native sigma definition: real/imaginary component standard deviation
  versus complex RMS, hand-dependent sensitivity and channel correlations.

History21 rows may be incomplete. Silence does not prove weights or DATA were
never changed; request publisher confirmation where commands/settings are
missing. More stringent confirmation would reconcile recorded multiplicative
calibration factors with weight/sigma products without refitting weights.
Do not force XY=YX sigma, use unit row weights as a fallback, rescale sigma from
these diagnostics or clear received flags.

## Conversion and solver gate remain separate

This plan obtains exact native string labels and processing evidence, not all
numeric subtables, units/measure-reference keywords or a sky model. Existing
dask-ms array attrs inspected for positions, directions and frequencies contain
axis metadata, not original MS measure keywords. Recover these from a trusted
publisher description/original table schema or explicitly document unsupported
conversion; never silently invent frames or names.

A later converter must separately preserve numeric ANTENNA/FIELD/FEED/STATE/
POLARIZATION/SPECTRAL_WINDOW/DATA_DESCRIPTION/OBSERVATION rows, native references,
row ordering, empty tables and MAIN partition constants. FEED group ordering
must not lexicographically remap native IDs. Record source-row/channel mapping,
retain every incoming FLAG/FLAG_ROW, DATA and weight/sigma column unchanged, and
validate against the original safely decoded values before any solve.

Only after justified DATA/sigma provenance, supported full-four-correlation
geometry, complete gain-bin support and an adequate calibrator sky may a **new**
frozen experiment select QuartiCal's original `SIGMA_SPECTRUM` noise source.
The old all-four-positive-WEIGHT_SPECTRUM result remains zero eligible samples.
Safe string extraction cannot retroactively change it or fix the enlarged
parallel-hand-only Jones gauge.
