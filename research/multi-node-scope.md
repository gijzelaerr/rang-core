# Multi-node execution: scoping note

Status, 2026-11-13: **proposed; nothing built or measured.** Prompted by Simon
Perkins (SARAO) asking whether ra-ng is single-node only. Sources were read
on 2026-11-13. **[V]** marks a claim checked in the cited source; **[I]** marks
an inference. Discussion: the GitHub issue "Multi-node execution" (milestone
v0.3.0).

## 1. Where ra-ng stands

ra-ng is single-node today. The Rust kernels use rayon threads inside a single
Python process. W3 and W3b chunk the data by time and row within a memory budget
(8 GiB by default), and chunked and unchunked runs are bit-identical on the
slice, A1, `poldx`, `polholdout` and the whole-array set
([w3-chunking.md](w3-chunking.md), [w3b-chainchunks.md](w3b-chainchunks.md)).
That determinism is the oracle a distributed executor can be gated against.

## 2. How others distribute

| Tool | Model | Source |
| --- | --- | --- |
| QuartiCal | Dask: `dask.scheduler=threads/distributed`, `dask.address`, `dask.workers × dask.threads`, Numba `solver.threads` per Dask thread; chunks by `time_chunk`/`freq_chunk`; per-scan K, G, B scaled about linearly over nodes on AWS (Africanus II) [V] | [options](https://quartical.readthedocs.io/en/latest/options.html), [arXiv:2412.10072](https://arxiv.org/abs/2412.10072) |
| dask-ms, codex-africanus | Dask as the distributed framework for RATT tools (Africanus I) [V] | [arXiv:2412.12052](https://arxiv.org/abs/2412.12052) |
| xarray-ms, arcae | MSv4 view over MSv2 via arcae (Arrow over casacore, multi-threaded, Parquet/Zarr export; concurrent writers refused) [V] | [xarray-ms](https://xarray-ms.readthedocs.io/en/stable/changelog.html), [arcae](https://github.com/ratt-ru/arcae) |
| pfb-imaging | Dask, `--nworkers × --nthreads` [V] | [repo](https://github.com/ratt-ru/pfb-imaging), [arXiv:2412.10073](https://arxiv.org/abs/2412.10073) |
| WSClean | `wsclean-mp` (MPI) distributes gridding only, round-robin over output channels; deconvolution in the main process; single-node `-parallel-gridding` preferred [V] | [docs](https://wsclean.readthedocs.io/en/latest/distributed_imaging.html) |
| Rapthor, LINC | CWL with Toil or StreamFlow on Slurm; DP3 and WSClean as separate jobs [V] | [docs](https://rapthor.readthedocs.io/en/v1.0/running.html) |
| CASA | mpicasa over a Multi-MS by scan, spw or baseline; MMS processing documented as "unverified" [V] | [casadocs](https://casadocs.readthedocs.io/en/stable/notebooks/parallel-processing.html) |
| SKA SDP | Dask execution engine in the scripting library; DALiuGE graphs [V, partly] | [ska-sdp-scripting](https://developer.skao.int/projects/ska-sdp-scripting/en/latest/_modules/ska_sdp_scripting/dask_deploy.html) |
| MSv4 / xradio | xarray DataTree processing set, Zarr backend, not backward compatible [V] | [xradio](https://xradio.readthedocs.io/en/latest/measurement_set/overview.html) |

The clusters MeerKAT users run on:

- **ilifu (IDIA):** Slurm, Singularity, CephFS and BeeGFS [V,
  [processMeerKAT](https://idia-pipelines.github.io/docs/processMeerKAT)].
- **CHPC Lengau:** PBS Pro [V, third-party].
- **SARAO and cloud:** Kubernetes with stimela [I].

A design has to stay neutral between schedulers.

## 3. What splits across nodes

| Stage | Natural split | Barrier or reduce |
| --- | --- | --- |
| flag | field/scan × channel block | none |
| calibrate | solution interval × channel block per term | between terms (K → G → B → …); fluxscale, Df, Xf and KCROSS across scans are reductions on small tables |
| apply | row chunk | one writer per MSv2 table (CTDS) |
| image | output channel (as wsclean-mp), facet; rows need a grid sum | minor cycle in one process |
| selfcal | the above per round | model update per round |

## 4. Proposed path

1. **Stage 1: a chunk task API, run multi-process on one node.**
   - Turn W3/W3b's chunk loop into `plan(ms, stage, budget) -> [ChunkSpec]`, `run(ChunkSpec) -> partial` and `reduce(partials)`, with a fixed reduction order and a single writer.
   - The first executor is a local process pool.
   - **Gate:** bit-identical to today's single-process output on the W3/W3b sets; wall time against process count at a fixed thread budget (exclusive host).
2. **Stage 2: Dask distributed.**
   - Same ChunkSpecs through `client.submit`, with dask-jobqueue's SLURMCluster and PBSCluster.
   - Rust kernels release the GIL.
   - Config: `executor: local|dask` and `dask.address`, mirroring QuartiCal; one worker thread × N rayon threads.
   - **Gate:** bit-identical to stage 1, then strong scaling over 1-8 nodes on a whole-array MeerKAT set. Matched-accuracy comparisons:
     - against QuartiCal on the same terms and chunks (gain residuals, χ²);
     - against `wsclean-mp -channels-out N` for imaging (rms, residual).
   - Report scaling efficiency, not speed-up alone.
3. **Stage 3: MSv4 / Zarr.**
   - A Zarr reader and writer behind the same ChunkSpec, with layout compatible with xradio and xarray-ms.
   - Per-chunk writes remove the single-writer limit.
   - **Gate:** round-trip against xradio and xarray-ms on the MSv4 test corpus; identical results from MSv2 and MSv4 input; throughput from object storage against CephFS.

Not proposed:

- **Ray:** no uptake in the field was found [V, negative].
- **MPI:** outside gridding it duplicates wsclean-mp and is fragile under containers and Toil [V for Rapthor].
- **Dataflow engines** (timely, Ballista): they do not fit dense complex arrays [I].

## 5. Risks

- Shared-filesystem read bandwidth (CTDS on CephFS or Lustre).
- Dask overhead with many small chunks.
- Nondeterministic reductions, so the reduce order is fixed.
- MSv4's schema still changes [V].
- Two readers to maintain.

## 6. Questions for Simon Perkins

- xarray-ms/MSv4 chunks first (interoperability), or the stage 1 task API first?
- Should ra-ng's Rust MS reader be offered as an arcae alternative, or should ra-ng read through arcae?
- Which cluster and data size would make a fair first scaling test?

## 7. Simon Perkins' reply (2026-11-13)

Relayed by the owner:

- xarray-ms can ingest MSv2 data behind an MSv4 view interface, "but that will mean data access is in Python".
- arcae plus xarray-ms "handles a lot unpleasant MSv2 edge cases (variable, partially filled columns)".

What it changes (coordinator, proposed):

1. **The fast path stays the Rust reader.** Data access through xarray-ms runs in Python, which would put a Python boundary inside every chunk read. #5 therefore keeps two paths:
   - ra-ng's Rust reader for MSv2;
   - a Rust MSv4/Zarr reader for MSv4.
   - An optional `xarray-ms` ingest arrives as an xarray Dataset at the Python layer, for interoperability; its cost is measured, not assumed.
2. **arcae + xarray-ms becomes an oracle for MSv2 edge cases.**
   - Build a case set of variable-shaped and partially filled columns: unwritten WEIGHT_SPECTRUM cells (as in W4), variable-shape DATA across spectral windows, string arrays (as fixed in [feed-poltype-read.md](feed-poltype-read.md)) and tiled storage managers.
   - Gate ra-ng's reader against arcae's reads on it: equal values and equal "unwritten" masks.
   - Wherever ra-ng refuses and arcae reads, record the gap as a reader task.
3. **Arrow as the meeting point** [I]: arcae exports Arrow, and arrow-rs reads the Arrow C data interface without a copy. So a Rust path through arcae's Arrow tables is possible without Python per read. Whether that costs less than ra-ng's own reader is to be measured.

Still open for Simon: whether he would review the edge-case set, and which MSv2 cases he has seen break readers.

### Follow-up from Simon (2026-11-13, relayed by the owner)

- In his view Dask "is veering towards unmaintained" and has task-scaling limits that are unlikely to be fixed.
- The exception would be depending on Matthew Rocklin's Rust implementation of the Dask scheduler ([getfrisky.dev](https://getfrisky.dev/)). It is closed source, and how well it is or will be maintained is unclear.
- xarray-ms does not depend on Dask as its execution framework.

None of these claims were checked here [I].

What it changes (proposed, not decided):

1. **Stage 2 is no longer "Dask distributed" by default.** Stage 1's `plan`/`run`/`reduce` ChunkSpec API stays independent of the executor. Stage 2 becomes "a multi-node executor", with Dask (dask-jobqueue) as one candidate beside a plain Slurm/PBS job-array executor (one ChunkSpec list per array task, reduced by a final job). Before stage 2 starts, a short note compares the candidates on maintenance (commit and release activity), task-count scaling at the planned chunk counts, and Slurm/PBS support. No closed-source scheduler is a dependency.
2. **Interoperability does not need Dask.** #5's optional xarray-ms ingest (point 1 above) does not pull in Dask as a runtime requirement.
3. **Risks (section 5):** add Dask's maintenance and its task-scaling limits; the existing "Dask overhead with many small chunks" item becomes part of the stage 2 comparison.
4. **Owner decision:** whether #4 (stage 2) is renamed executor-neutral in the roadmap and on the issue.

## For the coordinator

None of this is on the v0.2.0 finish line. Stage 1 is proposed for v0.3.0, and stages 2 and 3 after it, subject to the owner's decision.
