# DL2: the training-data factory (issue #39)

Status: **frozen 2026-11-19, before any visibility of the nine blocks was read.** Sections 1-2 are
measured (metadata only); sections 3-8 are the plan the fetch, conversion and teacher runs follow.
Later changes are dated amendments, labelled post hoc where they could have seen data. Parent plan:
[dl-plan.md](dl-plan.md) sections 5, 6 and 10 (decision 6, the frozen selection rule and its
nine-block table).

What this task delivers: per-scan Measurement Sets of nine SARAO capture blocks with SHA-256
manifests, teacher labels written outside the MSs, and one registered manifest per stage 1, 2 and 7
with fixed train, validation and held-out sets. It claims no scientific result; the stages that use
the data (#40-#42) carry their own frozen notes and gates.

## 1. Publication terms (step 1)

Read 2026-11-19 from SARAO's public support pages (skaafrica.atlassian.net, space ESDKB, through
Confluence's REST API, page IDs given):

- **2026 Call for Proposals** (page 3080126470), section 9: "After the proprietary period expires,
  the visibilities, and data cubes produced automatically by the SDP pipeline if any, will become
  freely available through the MeerKAT data archive interface." Default proprietary period 12 months
  (DDT 3 months, PhD projects up to 18). SARAO "does not guarantee the storage of either visibility
  data or any associated image cubes substantially beyond the proprietary period".
- Same page, section 10, and **Science with MeerKAT** (page 1382154297): refereed papers and theses
  that include MeerKAT data carry the acknowledgement "The MeerKAT telescope is operated by the South
  African Radio Astronomy Observatory, which is a facility of the National Research Foundation, an
  agency of the Department of Science, Technology and Innovation" (page 1382154297 still says
  "Department of Science and Innovation"), and authors inform SARAO (publications@ska.ac.za).
- **Instructions to PIs** (899448833) and **FAQ** (1452441609): proprietary periods as above; PIs may
  waive them. **Accessing and examining your data** (1451589674): non-proprietary data are
  "observations past their proprietary periods".
- **Not found:** no licence for archive data, and no statement on derived products (trained weights)
  or commercial use, on any page searched (Confluence full-text search for "proprietary", "public
  data", "data policy", "licence", "license", "publications"). Proposal-specific terms are not
  public: the cover sheets are not published, and telstate's `proposal_description` is empty for
  all nine blocks.

**Reading:** public archive data are "freely available"; the only condition found is the
acknowledgement and the publication notice. No block's terms forbid publishing derived weights, so
**no block is replaced.** Every weights file trained on these data carries the acknowledgement in
its header and its documentation. Whether "freely available" with no stated licence suffices for
shipping weights under rang's GPL is an owner decision (coordinator section).

Public state: taken from the owner's catalogue read of 2026-11-19 (dl-plan decision 6: state
AVAILABLE, public). The archive's per-block open date is behind the owner's login and is not
re-read here.

| Capture block | Observed (UTC) | Proposal ID (telstate `obs_params`) | dl-plan table says | Description (telstate) |
| --- | --- | --- | --- | --- |
| 1678312253 | 2023-03-08 | SCI-20220822-BD-01 | same | Observation of HD 142990 at L band part 2 |
| 1749428161 | 2025-06-09 | SCI-20241102-GS-01 | same | GRB 250520A L-band Epoch 4 |
| 1629213076 | 2021-08-17 | SCI-20200703-MK-01 | same | MPIfR Galactic Plane Survey L-band |
| 1573212012 | 2019-11-08 | **SCI-20180721-SP-01** | SSV-20180721-FC-01 | Galactic plane 88 |
| 1579022459 | 2020-01-14 | **SCI-20180721-SP-01** | SSV-20180721-FC-01 | Galactic Plane 61 QA-Repeat |
| 1571938260 | 2019-10-24 | **SCI-20180505-FC-02** | SSV-20180505-FC-02 | LMC mosaic: epoch 16/23 |
| 1735892129 | 2025-01-03 | SCI-20241101-KR-02 | same | ASKAP J1745 epoch 3 (part 2) |
| 1611426666 | 2021-01-23 | SCI-20180516-EB-01 | same | MHONGOOSE J0516-37 setting 3 |
| 1674958551 | 2023-01-29 | SCI-20220822-BD-01 | same | Observation of HD 142990 at L band |

Three proposal IDs in dl-plan's table differ from telstate's (the catalogue column it was copied from
is not telstate's `proposal_id`); telstate's are used from here on. The latest block (2025-06-09)
is past a 12-month period.

## 2. Dump time and scan list, from each block's own metadata (step 2)

[dl2_meta.py](results/dl2-scripts/dl2_meta.py) opened each block's RDB (telstate and sensors; no
visibility, flag or weight chunk) on nash with katdal 0.23; output in
[results/dl2-data/meta/](results/dl2-data/meta/) (one JSON per block, tokens scrubbed, no `token=`
or token string in any file or log, checked by grep). Two runs (the second added
`proposal_description`): 253 s and 266 s, 8.1 GB peak RSS.

| Capture block | Dump | Channels | Antennas | Dumps | Track scans | Cal scans | Target scans | Split |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1678312253 | 7.997 s | 4,096 | 29 | 4,090 | 38 | 23 | 15 | held out |
| 1749428161 | 7.997 s | 4,096 | 48 | 1,821 | 18 | 11 | 7 | train |
| 1629213076 | 7.997 s | 4,096 | 56 | 3,865 | 61 | 17 | 44 | train |
| 1573212012 | 7.997 s | 4,096 | 57 | 3,477 | 114 | 29 | 85 | validation |
| 1579022459 | 7.997 s | 4,096 | 58 | 3,702 | 118 | 28 | 90 | held out |
| 1571938260 | 7.997 s | 4,096 | 59 | 5,117 | 79 | 43 | 36 | train |
| 1735892129 | 8.002 s | 1,024 | 62 | 1,671 | 13 | 8 | 5 | train |
| 1611426666 | 7.997 s | 4,096 | 64 | 2,640 | 19 | 14 | 5 | train |
| 1674958551 | 7.997 s | 4,096 | 32 | 4,035 | 35 | 19 | 16 | held out (ninth) |

- **All nine have dumps of about 8 s** (7.997 s; 8.002 s for the 1k block). This includes the two
  blocks that replaced the 2018 MIGHTEE blocks dropped for an estimated 4 s dump (dl-plan decision 6);
  the estimate is now replaced by the measured value and no further replacement is needed.
- **Outer array confirmed:** 1674958551 has m020 and m033-m063 (32 antennas, the outer array).
  1678312253's 29 are m000-m006, m008, m015, m026-m027, m029-m033, m035-m036, m039-m040, m046-m047,
  m049-m050, m052, m054, m057, m059, m061.
- **Calibrators** per block (tags from the block's catalogue): every block has 1934-638 (J1939-6342)
  or 0408-65 (J0408-6545) as bpcal/fluxcal; gain calibrators J0408-6545 (1571938260 uses it as gaincal
  too), J2011-0644, J0828-3731, J0538-4405, J1318-4620 and three others (1629213076), J1517-2422,
  J1744-5144, J1911-2006; polarisation calibrators J1331+3030 (3C 286), J0521+1638, J1130-1449,
  J2232+1143.

## 3. Subset plan

Per dl-plan decision 6: every calibrator scan plus the middle three target scans, as E2-N.

- **Scan class.** A scan is used when katdal's state is `track` and it has at least one dump. It is a
  **calibrator** scan when its target carries any of the tags `bpcal`, `fluxcal`, `gaincal`,
  `polcal`, `delaycal`, `phasecal`; otherwise it is a **target** scan when its target carries
  `target`. Slews and stops are not fetched. No track scan in the nine blocks falls outside these two
  classes.
- **Middle three.** Target scans in time order, n of them: indices `(n-3)//2` to `(n-3)//2 + 2`
  (for even n the lower middle). This reproduces E2-N's 15, 19, 23 out of 7 target scans.
- The selection is a function of the metadata JSON only: [dl2_plan.py](results/dl2-scripts/dl2_plan.py)
  wrote [results/dl2-data/plan/](results/dl2-data/plan/) (one JSON per block), committed with this note.

| Capture block | Middle three target scans (katdal index) | Selected dumps of track dumps | MVF estimate |
| --- | --- | ---: | ---: |
| 1678312253 | 36, 40, 44 | 1,263 of 3,897 | 84 GB |
| 1674958551 | 31, 35, 39 | 1,125 of 3,899 | 91 GB |
| 1735892129 | 9, 13, 17 | 1,079 of 1,642 | 84 GB |
| 1749428161 | 12, 16, 22 | 883 of 1,751 | 163 GB |
| 1629213076 | 54, 56, 58 | 606 of 3,659 | 153 GB |
| 1573212012 | 111, 113, 115 | 778 of 3,187 | 203 GB |
| 1579022459 | 115, 117, 121 | 827 of 3,383 | 224 GB |
| 1571938260 | 71, 75, 83 | 1,183 of 4,874 | 332 GB |
| 1611426666 | 12, 20, 28 | 1,600 of 2,469 | 528 GB |
| **Total** | | 9,344 | **1.86 TB** |

Estimate: dumps × cross products (4 polarisations) × channels × 10 B (8 visibility, 1 flag, 1
weight), which gives 92 GB for E2-N's selection against the 94 GB measured.

## 4. Fetch, conversion and manifests

Run root on nash: `~/rang-data/outputs/dl2-data-20261119/` (mode 700). Code from
`~/Worktrees/rang/dl2-data` (this branch), venv `.venv-dl2` (uv, Python 3.12, katdal 0.23,
python-casacore, public PyPI). Every job: `heavy_lock.py run --slots N --mem G --`
then `nice -n 19 ionice -c3`. Fetches are network-bound and book 1 slot each.

- **Order.** (0) Smoke: the chain below on one short calibrator scan of train block 1735892129, so
  that nothing is debugged on held-out data. (1) 1678312253 and 1674958551, side by side (G-sub data
  for #40). (2) The train blocks, smallest first: 1735892129, 1629213076, 1749428161, 1571938260,
  1611426666. (3) Validation 1573212012. (4) Held-out 1579022459.
- **Fetch** ([e2n_fetch.py](results/e2n-scripts/e2n_fetch.py)'s method, as `dl2_fetch.py`: token
  in memory only, `Authorization: Bearer`, chunks written `.part` and renamed, a rerun skips present
  chunks). Shard: one katdal scan; `done/<cbid>/fetch-<scan>.done` after rc 0 and no failed chunk.
  A crash loses only the chunks in flight.
- **Conversion.** `mvftoms.py -f -a --flags static,cam,data_lost,ingest_rfi,predicted_rfi --scans
  <scan>` (E2-N's options: full polarisation, no autocorrelations, no calibration applied, native
  observatory flags, default `--quack 1`), one MS per scan: `ms/<cbid>/scan<NNN>.ms`, written as
  `.ms.part` and renamed. Shard: one scan, `done/<cbid>/convert-<scan>.done`. Expected rate: E2-N's
  14 scans took 13 min 55 s on nash (94 GB in, 105 GB out). The largest single scan (1611426666's
  target scans, about 150 GB) takes about 25 min, the one stated exception to the 15-minute rule; a
  crash there redoes that scan's conversion only. Every log is grepped for `token=` after the run.
- **Manifests.** Per scan, `manifests/<cbid>/scan<NNN>.sha256`: `sha256sum` lines for every file in
  the MS, relative paths, sorted; its own SHA-256 is the scan's **MS hash**. Per block,
  `manifests/<cbid>.json`: the metadata JSON's SHA-256, the split, every selected scan with class,
  target, dumps, rows, MS hash, katdal and mvftoms versions and the mvftoms argv. Rows and the column
  list are read from the table descriptor (casacore `nrows`, `colnames`): no cell is read.
- **Immutability.** After its manifest is written the MS is made read-only (`chmod -R a-w`); it is
  never written again. The MVF chunks of a block are deleted once every selected scan of the block
  is converted and hashed (refetchable while the tokens last); the RDB and the metadata are kept.
- **Disk.** MSs about 2.1 TB in all (1.1 × MVF, E2-N's ratio); peak with MVF of two blocks in flight
  about 3 TB. Guard: no fetch or conversion starts with less than 2 TB free on `/home` (16 TB free
  on 2026-11-19; other users share it).
- **Time.** At E2-N's 9-15 MB/s: the held-out pair (175 GB) in 3-5 h, everything (1.86 TB) in 35-57
  h. Whether two concurrent fetches add up is measured on the pair and recorded.

## 5. Held-out blocks: what "never opened" means

Held out: 1678312253 and 1579022459 (the rule's first and fifth by antenna count) and 1674958551
(the owner's ninth). Validation: 1573212012. For the held-out three, this task does **only**: fetch,
conversion, the table-descriptor row count and column list, and the SHA-256 manifests. Not done:
flag fractions, a DATA-state check, any teacher run, any statistic of a cell. Labels on them are
generated by the runners of section 6, invoked once when a stage reads its held-out set after its
own freeze (for #40, at D's single read); who triggers that run is the coordinator's call.

## 6. Teacher runners

Teachers never write the frozen MS. Each runs on a **working copy** per scan: the files of the
storage managers that hold DATA, WEIGHT_SPECTRUM and SIGMA_SPECTRUM are hard-linked (read-only, so a
write to them fails rather than corrupting the original); every other file (FLAG, FLAG_ROW, the
subtables) is copied. So each teacher starts from the native flag state. After the run the
teacher's FLAG (and FLAG_ROW) is written as `labels/<teacher>/<cbid>/scan<NNN>/flag.npz`
(bit-packed, rows in MS order) with `label.json` (teacher, version, image SHA-256, argv or strategy
file with its SHA-256, wall, peak RSS, the input MS hash) and a SHA-256 line; then the working copy
is deleted. Shard: one teacher × one scan, `done/<teacher>/<cbid>/<scan>.done`.

| Stage | Teacher | Form | Pin |
| --- | --- | --- | --- |
| 1 | rang's flag stage (the Rust Tricolour port, `core/src/sumthreshold.rs`) | `rang-core` from this branch's wheel on nash, **`data.executor: spool`** with workers on nash | the wheel's version and `_core` SHA-256 (the spool's `build()`) |
| 1 | Tricolour 0.2.1 | `rang-tricolour_0.2.1-e1.sif` (apptainer) | image SHA-256 |
| 1 | AOFlagger with CARACal's `firstpass_QUV.rfis` (f5-flagger.md) | `stimela_aoflagger_1.2.0.sif`, not nash's `/usr/bin/aoflagger` | image and strategy SHA-256 |
| 1 | `pfb hci` with Landman's settings | pfb-imaging at #40's pin (`1836fbcf`), run only once #40 has validated it on injections (f5-flagger.md section 6) | commit |
| 2 | rang calibrate (K, G, B) and CASA 6.7.6.14 (gaincal, bandpass) on the calibrator scans | `rang-core` (spool) and `rang-o-casa_6.7.6.14.sif`; field roles from the block's tags; solutions written as tables outside the MS | wheel, image |
| 7 | GeMClean and WSClean 3.7 deep models on the middle target scans after stage 2's apply | `rang-core gemclean`; WSClean from `rang-o-casa_6.7.6.14.sif` (the native image fails on nash's Xeon) | wheel, image |

Image SHA-256s (nash, 2026-11-19; `logs/sif-sha256.txt`), copied into every `label.json`:
`rang-tricolour_0.2.1-e1.sif` 1fec3916…c2c4e1, `rang-o-casa_6.7.6.14.sif` 6cd2314c…2a79,
`stimela_aoflagger_1.2.0.sif` fd89f5d9…0d38 (full hashes in
[results/dl2-data/sif-sha256.txt](results/dl2-data/sif-sha256.txt)).

**The spool, read precisely.** `core_tasks.RUNNERS` has `flag`, `solve` and `apply` only. The rang
teachers run through it as stages with `data.executor: spool` (workers started on nash with
`python -m rang.core_spool worker`). The external teachers are whole-MS container processes run by a
shard driver (`dl2_teach.py`) with done-markers; no arbitrary-command task kind is added to
`core_tasks` in this task (coordinator section).

## 7. Stage manifests and augmentation

- `manifests/stage1.json`, `stage2.json`, `stage7.json`: for every entry the capture block, scan,
  class (calibrator or target), MS hash, label paths with their SHA-256 and teacher pins, and the
  split. Splits are by capture block (dl-plan decision 6), never by scan, cell or baseline. The
  held-out and validation entries are registered (their MS hashes) in these files before any
  training run of the stage reads them.
- **Augmentation is a sampling recipe, not new data.** Sub-arrays and antenna dropout are drawn at
  sample time from the train blocks' antenna sets and recorded per sample: `{cbid, scan, antennas
  kept, seed}`. Recipe frozen here: sub-array size uniform in 4 to all; layout half random subsets,
  half radius-limited (core-only, nearest-N to the array centre); antenna dropout of 1, 4 or 8 on
  full-array samples; seeds from a fixed root seed per stage manifest. No MS is written for an
  augmented sample. Gate data (G-sub, G-drop) come from the held-out blocks only.

## 8. Stop rules

- A token error (HTTP 401/403) stops the fetch and is reported to the coordinator; no new link is
  requested from here.
- A chunk the archive does not hold (HTTP 404) is recorded per scan; katdal marks it `data_lost` in
  the conversion. A scan with more than 1 % of its chunks lost is recorded and kept, not refetched.
- Less than 2 TB free on `/home`: no new shard starts.
- A `token=` line or a token string in any log, JSON or manifest: stop, scrub, report.

## 9. Amendment 1 (2026-11-19, after the smoke test; implementation only, no visibility statistic of any block was read for it)

Found on the smoke scan (train block 1735892129, katdal scan 3) and in the first hour of the fetch:

- **Working copies (section 6).** Hard links to the read-only MS fail: Tricolour (dask-ms) and AOFlagger
  open the MS read-write, so casacore opens every storage-manager file for writing ("table.f6_TSM0 could
  not be opened: Permission denied"). nash's `/home` is ext4, with no reflink. Changed: one private full
  copy per scan (`work/copies/<cbid>/scan<NNN>.ms`, made once, shared by the teachers in turn). Before each
  teacher every file except the DATA, WEIGHT_SPECTRUM and SIGMA_SPECTRUM storage-manager files is restored
  from the frozen MS, so each still starts from the native flags. After each teacher those bulk files are
  checked unchanged: size and mtime of the `_TSM` data files, SHA-256 of their headers. The frozen MS is
  never opened for writing and stays read-only. The copy is deleted once the scan's teachers are done.
  Cost: one copy of the bulk data per scan, not one per teacher.
- **Label format.** `flag.npy` is a bit-packed `uint8` array, shape (rows, ceil(chan × corr / 8)),
  memory-mapped, not `flag.npz`.
- **AOFlagger** in `stimela_aoflagger_1.2.0.sif` is 2.13.0 (2018-11-07). It reads CARACal's 2.9.0 XML.
  CARACal's `firstpass_QUV.rfis` is fetched from GitHub at `8f7bb363` into the run root's `strategies/`,
  checked against F5's SHA-256 (`edcb4131…c69c8`, matched), and not committed. Recorded in each `label.json`.
- **mvftoms** in katdal 0.23 imports `pkg_resources`: `setuptools<81` is pinned in `.venv-dl2` (80.10.2).
- **Smoke result.** Fetch 29 s (1.15 GB, 41 MB/s); conversion 40 s, 4.4 GB peak RSS; 26,474 rows
  (14 dumps × 1,891 baselines); 79 files hashed; a write into the frozen MS is refused. Tricolour
  308 s, AOFlagger 27 s, both at 4 threads.
- **Rates and sizes, revised.** Each block's fetch runs at 90-130 MB/s on the large scans (two blocks
  side by side), not E2-N's 9-15 MB/s, so conversion and hashing set the pace. MS size is about 1.5 ×
  MVF on the smoke scan (1.77 GB from 1.15 GB), so the nine MSs come to about 2.9 TB, not 2.1 TB.
  The 2 TB free-space guard is unchanged.

## 10. Amendment 2 (2026-11-19 08:35 UTC; fetch order and manifest hygiene, no data read)

- **Order.** Held-out 1579022459 was moved from last to fifth, beside train block 1749428161, because
  #40 uses it for G-obs and the fetch runs far faster than planned. Done: 1678312253 and 1674958551,
  then 1735892129 and 1629213076. The set, the split and the subsets are unchanged.
- **Block manifests** are rewritten only when their content changes, so their SHA-256 stays stable on
  a rerun. The first rerun (used to delete the pair's MVF) had changed only `written_utc`.

## 11. Measured: the held-out pair (2026-11-19)

| Capture block | Scans | Rows | MS | Lost chunks | Wall (fetch + convert + hash) | Block manifest SHA-256 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1678312253 | 26 | 512,372 | 136.7 GB | 0 of 7,145 | 2,374 s | 157b3b2f…b520 |
| 1674958551 | 22 | 558,000 | 148.8 GB | 0 of 6,329 | 2,400 s | e4723aee…0000 |

Run side by side, 2 slots each; peak RSS 4.2 and 5.0 GB. MVF 77 and 83 GB (deleted after hashing,
RDB kept), so the MS is 1.8 × MVF here. No `token=` or token string in any log, manifest or receipt.
Only conversion, row counts and checksums were done on them (section 5). The coordinator was told at
08:40 UTC.

## 12. Measured: first teacher runs (train block 1735892129, 2026-11-19)

| Scan | MS | rang port (spool) | Tricolour 0.2.1 | AOFlagger 2.13.0 | rang vs Tricolour |
| --- | ---: | --- | --- | --- | --- |
| 3 (J1744-5144, 14 dumps) | 1.8 GB | 125 s, 0.5072, 4 workers | 308 s, 0.5072, `-nw 4` | 27 s, 0.6035, `-j 4` | bit-identical (same `flag.npy` SHA-256) |
| 1 (J1939-6342, 74 dumps) | 8.8 GB | 135 s, 0.5797, 8 workers | 308 s, 0.5797, `-nw 8` | 115 s, 0.6920, `-j 8` | 28 of 573,169,664 cells differ (4.9e-8), all flagged by rang only, in 3 rows |

The fractions include the native flags, so they are not RFI fractions. Tricolour runs at about
29 MB/s of MS at 8 threads and the port at about 65 MB/s, which gives about 23 h of Tricolour over
the train and validation MSs (about 2.4 TB), split across blocks running side by side. The private
copy of an 8.8 GB scan took about 6 min under `ionice -c3`, behind the other blocks' fetch I/O.
rang-core's flag stage leaves `<copy>.flagversions` beside the copy (its timestamps match the rang runs; the Tricolour and AOFlagger test left none); the runner now deletes it before each teacher and with the copy.

Stage manifests were first written at 08:58 UTC (`manifests/stage{1,2,7}.json` on nash). They
register 48 held-out stage 1 scans (42 for stage 2, 6 for stage 7) by MS hash before any training
read. Augmentation root seeds come from SHA-256("rang dl2 stage N"); stage 1's is 960723432.

## 13. Amendment 3 (2026-11-19 09:20 UTC; teacher settings, before any target scan was labelled)

- **Strategy per scan class.** Section 6 named no Tricolour strategy, and the runner used CARACal's
  calibrator strategy for every scan (as E2-N's `e2n.yaml` does for a whole MS). Changed: rang's port and
  Tricolour use `mk_rfi_flagging_calibrator_fields_firstpass.yaml` on calibrator scans and
  `mk_rfi_flagging_target_fields_firstpass.yaml` on target scans. Both are CARACal `8f7bb363` files:
  ce9ac66a…1774 (the committed copy, the same bytes) and f9d4881b…6807. The target file is fetched into the
  run root and not committed (CARACal is GPL-2.0). AOFlagger keeps `firstpass_QUV.rfis` for both
  classes, which is what CARACal's `meerkat-defaults.yml` sets for its calibrator and target flag
  workers. No target-scan label existed when this changed: the labels written so far are of
  calibrator scans 1, 3 and 7 of 1735892129, and they stand. The running teacher job was stopped
  and restarted; each file's SHA-256 is checked before use.
- **Rerun safety.** A rang shard deletes its run directory first. Otherwise, after a crash between
  the stage's end and the done-marker, `rang-core flag` would skip the finished stage and the native
  flags would be saved as its label. Tested: the rerun of 1735892129 scan 3 gives the same
  `flag.npy` (9f94a7cd…).
- **AOFlagger read mode.** `-direct-read` for a scan whose MS exceeds 40 GB, else its default
  (auto: in memory when it fits). It peaked at 6.3 GB on the 8.8 GB scan.
- **Bookings.** Teacher jobs book 6 GB per thread: 8 threads on 1735892129, 1629213076 and
  1749428161, 4 on 1571938260, 1611426666 and 1573212012.
- **15-minute rule.** A teacher shard is one teacher on one scan. On the largest target scans (up
  to about 270 GB of MS), a Tricolour shard is expected to take well over an hour at about 29 MB/s:
  a stated exception, as for the conversion. A crash costs that one shard.
- **Stage 2 route (probe, nothing built).** Each per-scan MS has SCAN_NUMBER 1, and its FIELD id
  0 is its own source. A casacore virtual concat (`msconcat`) of 1735892129 scans 1 and 3 gave
  166,408 rows but no FIELD subtable, and it would mix up field ids. A real merge is needed: CASA
  `concat` in `rang-o-casa_6.7.6.14.sif` into a private MS, which remaps fields and needs no MVF.
  The katdal scan index is in the file name and the block manifest. The stage 2 and stage 7
  teacher runners are not built in this task (coordinator section).

## 14. Amendment 4 (2026-11-19 09:38 UTC; bookings, no data read)

The lock audit at 09:36 UTC showed 40 of 44 slots booked against 4.8 cores in use, and a job
waiting 5 min in the queue. The teacher jobs held 8 slots while they made the private copy, which
is I/O only and slow under `ionice -c3`. Changed: per scan,
[teach_block.sh](results/dl2-scripts/teach_block.sh) makes the copy under a 1-slot, 4 GB booking
(`dl2_teach.py --copy-only`), then runs the three teachers under a T-slot booking. The jobs were
stopped by process group and restarted; every finished shard was kept by its done-marker. A copy
killed midway keeps read-only directory modes from `copytree`, so the runner now makes it writable
before removing it.

## 15. Amendment 5 (2026-11-19 12:30 UTC; scheduling, no data read)

nash's disk (sda) ran at 93 % utilisation with all of DL2's jobs under `ionice -c3`. The block
driver hashing 1611426666's 233 GB target scan 12 read at 10 MB/s, about 6.5 h for one scan. The
teacher jobs' private copies were competing with the conversions. Changed: the teacher jobs were
stopped (finished shards kept by their done-markers; at most one in-flight shard per job lost).
`relaunch_teach.sh` on nash restarts them once all nine blocks have ended. With the teachers
stopped, the hash read rose to 47 MB/s and utilisation fell to 69 %. Teacher shards measured
before the stop: 1629213076 scan 0 (25 GB) 3,098 s for the three teachers, 1749428161 scans 0
and 2 630 s and 515 s.

## For the coordinator

- Terms: no licence and no statement on derived products found; only the acknowledgement and the
  publication notice. Shipping weights trained on "freely available" archive data under GPL is the
  owner's call; no block was replaced.
- Measured rate: one block (fetch, convert, hash) in about 40 min at 90-130 MB/s fetch; all nine
  converted within about 3-4 h of the start. Flag teachers: about 23 h of Tricolour in all, split
  across blocks.
- Held-out labels (section 5): who runs the teachers on them, and when, is your call
  (`dl2_teach.py --heldout-read`).
- Stage 2 and stage 7 teachers are not built (amendment 3: CASA `concat` into a private MS is the
  route). Open them as a follow-up under #41/#42 if wanted.
- An arbitrary-command task kind for the spool (for container teachers) is not added here; open it
  under #4 if wanted.
