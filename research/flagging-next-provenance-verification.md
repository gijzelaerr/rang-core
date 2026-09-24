# Independent native provenance artifact verification

Verified2026-09-24 against scientific source checkpoint
`ec2f17d1dad5f4de65311db19db6daaf1aa4fc2a`. This is a retrospective read-only
artifact audit, not another calibration measurement or a premeasurement claim.
The executed offline Stimela2 branch is
`outputs/tv-next-20260924-01/experiments/provenance`; the exact audit program,
command, source hashes and657 passed predicates are retained in
[the verification archive](results/gain-tv-next-provenance-audit.json).

## What passed

All93 campaign runtime paths, including the actual Linux native library
SHA`cf61db3728a1bb1e1a8bc66ec738d80a102f636185dd527e11a1f6290c530a84`,
and all five frozen input-tree hashes match. No runtime path was unavailable.
Verification used campaign image
`sha256:5da4c1b754ddc3a43f57b5cb7f4d8b7bf9aa182c53eeac5c4ac0fb6208ac1d22`,
network disabled, read-only filesystem/repository, one CPU and2GiB memory.
No QC invocation, native-MS conversion or dataset write was performed.

The complete85-object HEAD receipt precedes conditional acquisition, which
precedes offline inspection. Every ordered key/schema/size/ETag/payload SHA
matches its frozen receipt; all85 checkpoint headers match the complete HEAD
record. There are82 string chunks and three numeric HISTORY chunks, no MAIN
request,15672 compressed bytes in total, and a maximum546-byte object. Both
compressed and decoded totals remain below1MiB, and every object below64KiB.
The existing888855-byte metadata copy matches its original pinned SHA.

All85 decoded-byte SHA/size receipts independently replay. Shared inert
`pickletools` recognition reproduces all82 string arrays/505 strings and all21
ordered HISTORY rows, including their numeric columns. The audit observes
pickle opcode names without executing reducers, imports or object state;
it does not invoke an unpickler or the Zarr pickle codec. This uses the same
adversarially tested inert grammar, not a second independent parser design.
Native labels include61 MeerKAT antenna names, ALT-AZ mounts, telescope
`MeerKAT`, and primary field `J1939-6342`.

The decoded total is16538 bytes. Exact result SHA is
`2c67687e7cdb2b51a59b8adf67a43e0f9c513abe449bc435160f4570b6f869ae`.
HEAD receipt SHA is
`92d18475723e6e1ef2586a4a90bf382b0beb4391fd2ae9b55a1626b6ebc41029`;
acquisition receipt SHA is
`3dc7fd843cb570778a4527349c6cb576aebcf927ee49823eab43097c530b65fc`.

## Measured finding and remaining gate

The21 HISTORY rows constitute one recorded CASA5.6.0-60 `split` task, not21
independent processing events. It records source
`../ms-orig/1557433849_sdp_l0.ms`, output `ms1_primary.ms`, field0,
`datacolumn="all"`, `keepflags=True`, channel width1 and `timebin="0s"`.
CLI_COMMAND and APP_PARAMS are empty. No inspected HISTORY text mentions
applycal, calwt, initweights, statwt, weight or sigma. `split` occurs in all rows
because it is also their recorded origin.

Those received settings support the recorded split configuration; they do not
prove absence of earlier/later calibration, certify DATA-associated sigma/noise
units, explain zero native cross-hand WEIGHT_SPECTRUM, or recover missing
measure-reference keywords. The original four-correlation eligibility finding
is unchanged. The conversion/solver gate remains explicitly false, with native
weight/sigma provenance unvalidated; no row-weight substitution, invented
sigma, flag clearing or independent-transfer success follows from this audit.

The audit confirms reproducible, safely recovered native metadata. A genuinely
independent MeerKAT L-band calibration/transfer result still requires the
publisher/export/noise and measure-frame evidence listed in the raw gate,
followed by a separately frozen native-MS/solver protocol.
