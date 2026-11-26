# UHF and S-band data: inventory, rule check and fetch (issues #11, #18)

Branch `uhf-s-fetch` from main `18726ccc`, 2026-11-26. Host nash (shared; every
job under `nice -n 19 ionice -c3` and the main checkout's `tools/heavy_lock.py`).
Run root `~/rang-data/uhf-s/` on nash. Follows [uhf-scope.md](uhf-scope.md)
(the frozen data rule, section 5) and [e2n-native.md](e2n-native.md) (the fetch
and conversion route). The protocol for the UHF gate is
[uhf-gate.md](uhf-gate.md); the S-band scoping note is
[sband-scope.md](sband-scope.md).

**Status (2026-11-26, amendment 2 at 10:15 UTC): the first four blocks are on
tape and are replaced by four online blocks, which also pass the rule and are
being fetched. The first four, as read before amendment 2: metadata read for
all four blocks; every block passes the
data rule; none is fetched, because the archive's object store holds no
visibility or flag chunk of any of them (section 3.1).** A watcher on nash
fetches and converts each block when its chunks appear. Only RDB metadata
(telstate, sensors) has been read: no visibility, flag or weight value of any
block.

## 1. The blocks

The owner approved these four public blocks on 2026-11-26 (owner decision D1 of
uhf-scope.md, through the coordinator). The links (one per block, read-only,
about 60 days) are in `~/rang-data/uhf-s/sarao-links.txt` on nash (mode 600) and
are read only inside the scripts; no link or token is in any file, log or note.

| Capture block | Band, product | Proposal | Description | Start (UTC) | Tracks | Antennas | Cross visibilities (katdal) |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| 1737424638 | UHF, `c544M4k` | SCI-20241101-HE-01 | M49_UHF setting repeat | 2025-01-21 01:58 | 20, 4.45 h | 60 | 488.6 GB |
| 1740534088 | UHF, `bc544M4k` | SCI-20241101-TM-01 | ASKAP J1424-6126 repeat | 2025-02-26 01:42 | 17, 3.80 h | 58 | 388.5 GB |
| 1729932377 | S (S4), `c875M4k` | SCI-20230907-RF-01 | XKAT S-band 2024-10-20 | 2024-10-26 08:47 | 13, 2.52 h | 60 | 276.5 GB |
| 1690097605 | S (S1), `c875M4k` | SSV-20230209-AD-01 | S-band continuum study of NGC 1566 and NGC 2442 (Part 1) | 2023-07-23 07:34 | 22, 3.23 h | 60 | 363.5 GB |

- All four: 4,096 channels, 8 s dumps (7.988 s at UHF, 8.015 s at S), four
  correlations, public in the archive (the owner's selection).
- Channels: UHF 544.000-1087.867 MHz of 132.8 kHz; S4 2625.000-3499.786 MHz and
  S1 1968.750-2843.536 MHz, both of 213.6 kHz (875 MHz sub-bands).
- `vis_bytes_cross_all` is katdal's shape times 8 B over all dumps, slews
  included; the brief's sizes (432-542 GB) include flags and weights.
- Things the metadata shows that the brief did not say:
  - 1729932377 started 2024-10-26, although its description says 2024-10-20.
  - Its 1934-638 target carries the tags `delaycal` and `bpcal` but not
    `fluxcal`. It is matched by name.
  - The two UHF blocks are different products, `c544M4k` and `bc544M4k`
    (the second also fed a beamformer). E2-N's question of F-engine phase-up
    gains applies to the second at least (e2n-native.md section 2).
  - The two S blocks are different sub-bands, so neither is a held-out set for
    the other's band-specific rows ([sband-scope.md](sband-scope.md)).
  - 1740534088 has an extra target J1446-4701 (one 15-dump scan before the
    first gain calibrator).

Scan tables (katdal track indices; slews omitted; dumps per scan):

| Block | Flux and bandpass | Polarisation | Gain calibrator | Target |
| --- | --- | --- | --- | --- |
| 1737424638 | J0408-6545: 0 (77); J1939-6342: 20 (74), 37 (75) | J1331+3030: 18 (74) | J1150-0023 (1148-001): 2, 6, 10, 14, 22, 23, 27, 31, 35 (14-16) | NGC4472: 4, 8, 12, 16, 25, 29, 33 (224-225) |
| 1740534088 | J1939-6342: 2 (75), 34 (75) | J1331+3030: 4 (74) | J1424-4913 (1421-490): 8, 12, 16, 20, 24, 28, 32 (14-15) | J1424-6126: 10, 14, 18, 22, 26 (250), 30 (125); J1446-4701: 6 (15) |
| 1729932377 | J1939-6342: 0 (40), 24 (37) | J1331+3030: 2 (75) | J1427-4206 (1424-418): 4, 8, 12 (14-15); J1733-1304 (NRAO530): 14, 18, 22 (14-15) | CirX1: 6, 10 (224); SwiftJ1727: 16, 20 (224) |
| 1690097605 | PKS 0408-658: 0 (40), 42 (37) | 3C138: 2 (37) | J0825-5010: 4, 10, ..., 40 (18 each, 7 scans) | NGC2442: 6, 12, ..., 36 (100-101); NGC1566: 8, 14, ..., 38 (100-101) |

Full scan tables, targets with tags and positions, antennas and obs_params are
in [results/uhf-s-fetch/meta/](results/uhf-s-fetch/meta/) (one JSON per block,
scrubbed; no `token=` or JWT string in any of them, checked).

## 2. The frozen data rule, per block

The rule is uhf-scope.md section 5, frozen 2026-11-17: R1 band, R4 a scan of
1934-638 or 0408-65, R5 at least 40 antennas, four correlations and at least
1,024 channels over the full band. R2 (access) and R3 (terms) hold for all four
by the owner's links to public archive data. The brief adds the scan table.
[uhfs_meta.py](results/uhf-s-fetch/scripts/uhfs_meta.py) computes it from the
RDB alone.

| Check | 1737424638 | 1740534088 | 1729932377 | 1690097605 |
| --- | --- | --- | --- | --- |
| ≥ 40 antennas | 60 | 58 | 60 | 60 |
| 4 correlations | HH HV VH VV | HH HV VH VV | HH HV VH VV | HH HV VH VV |
| Channel centres inside the receiver band | UHF 544-1088 | UHF 544-1088 | S 1750-3500 | S 1750-3500 |
| ≥ 1,024 channels | 4,096 | 4,096 | 4,096 | 4,096 |
| Full band: channel span ≥ 0.99 of the stream bandwidth, no zoom | 544 of 544 MHz | 544 of 544 MHz | 875 of 875 MHz | 875 of 875 MHz |
| Flux-calibrator scan | 1934-638, 0408-65 | 1934-638 | 1934-638 | 0408-65 |
| Polarisation calibrator (not required) | 3C 286 | 3C 286 | 3C 286 | 3C 138 |
| Scan table (track scans, each with dumps) | 20 | 17 | 13 | 22 |
| **Rule** | **pass** | **pass** | **pass** | **pass** |

- **Disclosed: the first rule run failed 1690097605 on name matching.** It
  matched J names only, and that block names its primary `PKS 0408-658` and its
  polarisation calibrator `3C138`. The script now matches every spelling of the
  catalogues (J name, B name, PKS name, aliases); the rule was recomputed from
  the same JSONs without reopening the RDB (`--rule-only`). The first run's
  output is kept as [meta-run1.log](results/uhf-s-fetch/meta/meta-run1.log).
  No threshold changed.
- **"Full band" at S band** is read against the 875 MHz digitised sub-band of
  the stream, not the receiver's 1750-3500 MHz. MeerKAT's S-band receiver is
  sampled in 875 MHz sub-bands; no single stream covers the receiver band. The
  rule as written (uhf-scope.md R5) was written for UHF, where the stream covers
  the receiver band; at S band this reading is the only one any block can meet,
  and it excludes narrow-band zoom modes as intended.

**Development and held-out sets (the rule's own order, metadata only).**
uhf-scope.md section 5: the development set is the eligible block with a
polarisation calibrator; ties go to native data, then to the smallest on disk.
Both UHF blocks have 3C 286 and both are native, so the **development set is
1740534088** (388.5 GB) and the **held-out set is 1737424638** (488.6 GB, a
different scheduling block). This reverses the brief's naming of 1737424638 as
the "primary": the frozen rule decides, and the coordinator's fetch order (that
block first) is kept, since it changes nothing that is read. The protocol
([uhf-gate.md](uhf-gate.md)) is frozen on this split.

## 3. Fetch and conversion (method)

Scripts in [results/uhf-s-fetch/scripts/](results/uhf-s-fetch/scripts/), copied to
`~/rang-data/uhf-s/scripts/` on nash. Venv `~/rang-data/uhf-s/venv` (moved
there from `~/Build/tmp` the same day, since `~/Build/tmp` may be wiped after 14
days and the watcher may run for 60; the same freeze; uv, Python 3.11.18, public PyPI: katdal 0.23, katsdptelstate 1.0.0,
python-casacore 3.8.1, setuptools < 81 for katdal's `pkg_resources` import;
[venv-freeze.txt](results/uhf-s-fetch/venv-freeze.txt)).

- **Fetch** ([uhfs_fetch.py](results/uhf-s-fetch/scripts/uhfs_fetch.py)):
  DL2's `dl2_fetch.py` method (itself E2-N's), with the token in memory only,
  for every track scan of the block (mvftoms converts tracks only). Changes:
  the link file's `cbid band url` format; SHA-256 of every chunk computed while
  it streams (`<cbid>-receipts/chunks-sha256.txt`); one global rate cap
  (default 40 MB/s over 6 workers) to keep nash's link friendly; and a
  lost-chunk bound: more than max(5, 0.1 %) of chunks answering HTTP 404 means
  the block is not on the store, so `fetch.done` is withheld (exit 3). E2-N
  lost 2 of 6,545. Below the bound, `fetch.done` waits until a pass at least an
  hour later finds the same lost list, so chunks still being staged are not
  taken as lost.
- **Driver** ([uhfs_fetch_all.sh](results/uhf-s-fetch/scripts/uhfs_fetch_all.sh)):
  every 30 minutes it lists every block's buckets
  ([uhfs_stagecheck.py](results/uhf-s-fetch/scripts/uhfs_stagecheck.py)) and
  fetches the first block, in the order 1737424638, 1740534088, 1729932377,
  1690097605, whose two buckets both list objects and which is not yet fetched,
  so one unstaged block does not hold up the others. A fetch that ends with
  chunks missing is retried on a later pass (fetched chunks are kept). Disk rule:
  2 TiB stays free after the block's MVF and MS (3.3 times the cross
  visibilities). It stops at the links' expiry (2027-01-24). Each fetch is a
  shared lock job of 1 slot and 4 GB. It writes `~/rang-data/uhf-s/status.md`.
- **Conversion** ([uhfs_convert.sh](results/uhf-s-fetch/scripts/uhfs_convert.sh)),
  one block at a time: E2-N's `mvftoms.py -f -a --flags
  static,cam,data_lost,ingest_rfi,predicted_rfi` on the local RDB (no token, no
  network, no `--applycal`, default `--quack 1`) into
  `~/rang-data/uhf-s/ms/<cbid>.ms`. **UHF blocks are converted as the gate's
  selection** (`--scans`, [uhf-gate.md](uhf-gate.md) section 2 and amendment 1),
  as E2-N converted its selection; the S-band blocks whole. Booked 4 slots and
  32 GB: **unmeasured** at 4k (the smoke had no data, and no 4k MVF chunks
  remain on nash to test with; E2-N's 1k conversion peaked at 5.6 GB). Then E2-N's prep step unchanged
  ([uhfs_prep_ms.py](results/uhf-s-fetch/scripts/uhfs_prep_ms.py): token search
  of every subtable and keyword, SIGMA_SPECTRUM removed, the MS map, SHA-256 of
  FLAG and FLAG_ROW), then SHA-256 of every file of the MS. Every log is
  searched for `token=` and JWT strings.
- **The MVF chunks are kept** after conversion (about 1.7 TB for all four). The
  links expire in about 60 days and restaging is slow, so the chunks are the
  only way to rebuild an MS after that; they are deleted when the gate has run.
- **Disk.** /home on nash had 12.8 TB free at the start. All four blocks at 3.3
  times their cross visibilities (whole-block MSs; the UHF selections are
  smaller) need at most about 5.1 TiB at the peak, leaving about
  7.5 TiB, above the 2 TiB floor. This exceeds uhf-scope.md section 5's "under
  2 TB on nash without a note": this section is that note.

### 3.1 Result: no block is on the archive's object store (2026-11-26)

- **Smoke, 07:09 UTC.** One scan of 1737424638 (katdal scan 0, J0408-6545,
  77 dumps). The RDB downloaded (170.5 MB, SHA-256 `58f52d29…7268`), and katdal
  listed 1,698 chunks (1,544 `correlator_data`, `weights` and `weights_channel`
  in `1737424638-sdp-l0`; 154 in `1737424638-sdp-l1-flags`). **All 1,698
  answered HTTP 404** (`NoSuchKey`, from the Ceph gateway), with the token as a
  header and as a query parameter alike. The lost bound stopped it
  ([smoke-fetch-1737424638-scan0.json](results/uhf-s-fetch/smoke-fetch-1737424638-scan0.json)).
  The smoke's mvftoms step started on the empty chunks and was killed; its MS
  was deleted unread.
- **Stage check, 07:14 UTC** ([stagecheck.jsonl](results/uhf-s-fetch/stagecheck.jsonl)).
  For all four blocks the RDB answers (206, 126-196 MB), and the S3 listings of
  `<cbid>-sdp-l0/correlator_data/` and `<cbid>-sdp-l1-flags/flags/` answer 200
  with **0 objects**.
- **Control** ([stagecheck-control.jsonl](results/uhf-s-fetch/stagecheck-control.jsonl)).
  The same listing on DL2's nine blocks (links of 2026-11-19, fetched then)
  lists objects in both buckets of every one. So the listing works and the
  token allows it; the four blocks' chunks are simply not there.
- **Reading.** The brief expected these SPOOLED blocks to stream. They do not:
  only their metadata (RDB) is online. That matches "archive restaging is slow
  right now". This is reported as the brief asked.
- **What runs now.** The driver checks every 30 minutes and fetches each block
  when it appears (pid on nash in `status.md`). Started 2026-11-26 07:16 UTC.

## 4. Provenance (filled as blocks convert)

Nothing yet. Per block, when converted: the RDB SHA-256, the chunk manifest
(`mvf/<cbid>-receipts/chunks-sha256.txt`), lost chunks, the MS map, the FLAG and
FLAG_ROW SHA-256, the MS file manifest (`ms-sha256.txt`) and its total bytes,
wall times and peak RSS; the compact receipts are copied to
`results/uhf-s-fetch/<cbid>/`. The MSs stay in `~/rang-data/uhf-s/ms/` on nash
(ignored outputs). Licence and credit as E2-N: public SARAO data; acknowledge
"The MeerKAT telescope is operated by the South African Radio Astronomy
Observatory, which is a facility of the National Research Foundation, an agency
of the Department of Science and Innovation." and the proposal IDs above.

## 5. Timings (host nash)

| Step | Wall | Peak RSS | Notes |
| --- | ---: | ---: | --- |
| uv venv and install (katdal 0.23 and its stack) | 20 s | – | plus setuptools < 81 later |
| `uhfs_meta.py`, four RDBs over the network | 53 s | 1.57 GB | RDB opens 7.5-11.6 s each |
| smoke fetch, 1737424638 scan 0 | 103 s | – | 0 bytes: every chunk 404 |
| stage check, four blocks; control on nine | 2 s; 2 s | – | |

Rows are also in [tool-timings.md](tool-timings.md).

## Amendment 2 (2026-11-26 10:15 UTC): four online blocks replace the first four

**Why.** The coordinator found the first four blocks on tape (lifecycle
ARCHIVED). The archive offers no restage of a single block, and the owner has
not decided on writing to SARAO. So the watcher keeps them at the end of its
list, at low priority, and four public blocks that are online (lifecycle
AVAILABLE) come first. Their links are the first four lines of the same link
file. The change is about storage, not about any data: nothing of the first
four was ever read beyond their RDBs.

| Capture block | Band, product | Proposal | Description | Start (UTC) | Tracks | Antennas | Cross visibilities |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| 1752418159 | UHF, `c544M4k` | SCI-20241101-MH-01 | U-band 13h | 2025-07-13 14:52 | 20, 3.83 h | 63 | 458.0 GB |
| 1726220298 | UHF, `c544M4k` | SCI-20230907-ZK-01 | RAMBO: The RAdio Magnetospheres of A, B and O Stars epoch 1 | 2024-09-13 09:39 | 31, 7.11 h | 60 | 772.8 GB |
| 1747682474 | S0 (1750.00-2624.79 MHz), `c875M4k` | SCI-20241102-GD-01 | A3528S S0band | 2025-05-19 19:23 | 18, 3.97 h | 58 | 411.2 GB |
| 1680455600 | S1 (1968.75-2843.54 MHz), `c875M4k` | SSV-20230209-AD-01 | S-band continuum study of NGC 2997 and NGC 4945 (Part 1) | 2023-04-02 17:15 | 22, 3.23 h | 57 | 336.8 GB |

**Rule** ([uhfs_meta.py](results/uhf-s-fetch/scripts/uhfs_meta.py), unchanged since
the alias fix; 58 s for the four, 2.1 GB peak):

| Check | 1752418159 | 1726220298 | 1747682474 | 1680455600 |
| --- | --- | --- | --- | --- |
| ≥ 40 antennas | 63 | 60 | 58 | 57 |
| 4 correlations | yes | yes | yes | yes |
| Inside the receiver band, ≥ 1,024 channels, full band | 4,096, 544 of 544 MHz | 4,096, 544 of 544 MHz | 4,096, 875 of 875 MHz | 4,096, 875 of 875 MHz |
| Flux calibrator (katdal scans) | 1934-638 (1, 39) | 0408-65 (0), 1934-638 (32, 60) | 1934-638 (1, 17, 35) | 0408-65 (3, 43) |
| Polarisation calibrator | 3C 286 (3, 37) | 3C 286 (2, 30) | 3C 286 (3) | 3C 138 (1) |
| Scan table | 20 tracks | 31 | 18 | 22 |
| **Rule** | **pass** | **pass** | **pass** | **pass** |

- Other calibrators: 1752418159 uses CTD93 (J1609+2641) for one target and
  3C 286 itself for two others (a duplicate catalogue name, which katdal warns
  of); 1726220298 J1605-1734 (1602-174); 1747682474 J1311-2216 (3C283);
  1680455600 J0825-5010.
- **Development 1752418159, held out 1726220298**, by the frozen tie-break (both
  have 3C 286 and are native; the smaller wins). Scan selections:
  [uhf-gate.md](uhf-gate.md) amendment 2.
- **Staged:** at 10:10 UTC all four list objects in both buckets
  ([stagecheck.jsonl](results/uhf-s-fetch/stagecheck.jsonl)); the first four
  still list none.
- **Fetch order:** 1752418159, 1726220298, 1747682474, 1680455600, then the first
  four. The UHF blocks fetch the gate's selection (H also its reserve); the S
  blocks every track scan. Disk at the peak: at most 3.3 times about 2.0 TB of
  cross visibilities, about 6 TiB of nash's 13 TB, above the 2 TiB floor.
- 1747682474 is sub-band S0 and 1680455600 S1, so [sband-scope.md](sband-scope.md)'s
  remark holds: neither is a held-out set for the other's band-specific rows.
  1747682474 has three 1934-638 scans and 1680455600 two 0408-65 scans, so both
  allow the within-block flux and leakage transfers that note sketches.

## 4.1 Development block 1752418159: fetched, converted, hashed (2026-11-26)

Receipts in [results/uhf-s-fetch/1752418159/](results/uhf-s-fetch/1752418159/).

- **Fetch** (selection of uhf-gate.md amendment 2, katdal scans 1, 3, 15, 17, 19,
  31, 33, 35, 37, 39; 736 dumps): 16,240 chunks (14,768 in `sdp-l0`, 1,472 in
  `sdp-l1-flags`). The first pass took 6,088 s for 243.2 GB at 39.96 MB/s,
  which is the 40 MB/s cap, not the archive's limit. 16,226 chunks arrived.
  **14 were lost:** flag chunks of 7 dumps (both channel halves), HTTP 404. A
  second pass 30 min later and a third an hour later found the same 14, so
  `fetch.done` was written at 12:59 UTC. katdal marks such chunks
  `data_lost`. RDB SHA-256 `93a34a11…52bf`. The chunk manifest is on nash
  (`mvf/1752418159-receipts/chunks-sha256.txt`, SHA-256 `bc430c3b…6b`).
- **Conversion** (`mvftoms.py -f -a --flags
  static,cam,data_lost,ingest_rfi,predicted_rfi --scans 1,3,15,17,19,31,33,35,37,39`):
  rc 0 in 1,766 s, 7.4 GB peak RSS, 144 % CPU. The booking of 4 slots and
  32 GB was generous; 2 slots and 12 GB fit. Prep took 183 s: no token in any
  subtable or keyword, SIGMA_SPECTRUM removed. Logs: no `token=` or JWT.
- **The MS** `~/rang-data/uhf-s/ms/1752418159.ms`: 288,684,854,689 B, 1,437,408
  rows, 4,096 channels × 4 (544.000-1087.867 MHz). Fields: J1939-6342,
  J1331+3030, J1609+2641, ILTJ153010. RECEPTOR_ANGLE −π/2. MS scans in time
  order map to katdal scans as predicted:

  | MS scan | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | katdal | 1 | 3 | 15 | 17 | 19 | 31 | 33 | 35 | 37 | 39 |
  | field | J1939-6342 | J1331+3030 | J1609+2641 | ILTJ153010 | J1609+2641 | J1609+2641 | ILTJ153010 | J1609+2641 | J1331+3030 | J1939-6342 |
  | dumps | 76 | 38 | 15 | 225 | 15 | 15 | 225 | 15 | 37 | 75 |

- **Hashes.** FLAG `d3de3335…07de` and FLAG_ROW `065ba12d…d8b0`
  ([flaghash-input.json](results/uhf-s-fetch/1752418159/flaghash-input.json), gate
  2a's reference). SHA-256 of all 77 files of the MS:
  [ms-sha256.txt](results/uhf-s-fetch/1752418159/ms-sha256.txt) (that file's own
  SHA-256 is `4ab80e59…8d73`; 1,988 s).
- **Smoke 8.1** (uhf-gate.md section 8). `rang-core config check` against the
  MS with rang-core 0.4.0 (the release-040 venv; the frozen wheel repeats it):
  `uhf-dev.yaml` is "valid for flag, calibrate, apply, image, selfcal" and
  `uhf-dev-3c.yaml` "valid for image", each with the band warning.
- **Smoke 8.2, the DATA-state probe: native, unphased**
  ([datastate.json](results/uhf-s-fetch/1752418159/datastate.json); channels
  2,048-2,079, 816.0-820.1 MHz, first 800 rows per field):

  | | J1939-6342 | J1331+3030 | J1609+2641 | E2-N 1934 (L) | ESO137 1934 (A0) |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | median \|XX−YY phase\| (rad) | 1.575 | 1.519 | 1.579 | 0.0117 | 1.488 |
  | XX−YY phase coherence | **0.0127** | 0.0047 | 0.0118 | 0.99977 | 0.018 |
  | row XX phase scatter | 105.9° | 105.3° | 105.7° | 9.9° | 104° |
  | per-row \|⟨XY⟩\|/\|⟨XX⟩\|, median | 2.03 % | 2.69 % | 2.37 % | 1.52 % | 1.35 % |

  Under E2-N's rule (coherence below 0.5) the block reads **native,
  unphased**, like ESO137 and unlike E2-N's observatory-phased L-band block.
  So the UHF gate is the first leg in which K, KCROSS and Xf are solved at
  their real size. This is the question e2n-native.md amendment 3 moved to "a
  later leg on another capture block". Every gate is read as frozen.

## 4.2 Held-out block 1726220298: fetched, converted, hashed; not read (2026-11-26)

Receipts are in [results/uhf-s-fetch/1726220298/](results/uhf-s-fetch/1726220298/).
**No visibility, flag or weight of H was read.** The steps below read
metadata and hashes only, and section 8's DATA-state probe is D's alone.

- **Fetch** (the selection plus the reserve: 24 katdal scans): 35,912 chunks
  (32,656 in `sdp-l0`, 3,256 in `sdp-l1-flags`). The first pass took
  12,221 s for 488.5 GB, 39.97 MB/s (the cap). **24 flag chunks were lost**
  (HTTP 404); two later passes found the same 24, and `fetch.done` was written
  at 17:29 UTC. RDB SHA-256 `7e070672…fc74`. The chunk manifest SHA-256 is
  `bc88e24c…7ec6` (on nash).
- **Conversion** (`--scans 0,2,4,8,12,16,20,22,24,26,28,30,32,34,36,38,42,46,50,54,58,60`,
  without the reserve): rc 0 in 3,737 s, 7.3 GB peak, 102 % CPU. Prep took
  683 s; no token anywhere; SIGMA_SPECTRUM removed.
- **The MS** `~/rang-data/uhf-s/ms/1726220298.ms`: 418,403,354,393 B, 2,083,290
  rows, 4,096 × 4. Fields: J0408-6545, J1331+3030, J1605-1734, HD142184,
  J1939-6342. Its 22 MS scans map to the katdal list in order, as predicted:
  MS 1 is 0408-65; 2 and 12 are 3C 286; 13 and 22 are 1934-638; 8, 10 and 15 are
  HD142184 (katdal 22, 26, 36); the rest are J1605-1734.
- **Hashes.** FLAG `14181651…2a71`, FLAG_ROW `bcb6b669…a216`; the 77 files in
  [ms-sha256.txt](results/uhf-s-fetch/1726220298/ms-sha256.txt) (its SHA-256 is
  `9424212d…dfd2`; 2,276 s).
- **Smoke 8.1:** `config check` against the MS (rang-core 0.4.0):
  `uhf-heldout.yaml` is valid for all five stages, `uhf-heldout-3c.yaml` for
  image.

## For the coordinator

- **Since amendment 2:** development block 1752418159 is fetched, converted
  and hashed (section 4.1): native, unphased. H 1726220298 is fetched, converted
  and hashed, not read (4.2); the two S blocks are fetching. Calibration waits for the frozen code (uhf-gate.md
  section 4: a main merge carrying the protocol).
- **First four blocks: fetched nothing.** All four blocks pass the frozen rule, but their chunks
  are not on the archive's object store (0 objects listed; the control lists
  DL2's blocks). Only the RDBs are online. A watcher on nash fetches and
  converts each block when it appears; it writes `~/rang-data/uhf-s/status.md`.
- **No restage is requested** (owner, 2026-11-26: nothing is sent to SARAO;
  uhf-scope.md). The watcher keeps polling for these blocks until the links
  expire (about 2027-01-24), at the end of its list.
- **Development set by the frozen rule: 1740534088**, held out 1737424638
  (section 2). The brief called 1737424638 the primary; the fetch order is
  kept.
- **Disk:** at the peak about 5.1 TiB of nash's 12.8 TB, MVF chunks kept until
  the gate has run.
- `uhf-11` (unmerged) and this branch both append to `uhf-scope.md`: a
  trivial merge conflict, both sections kept.
- **The watcher needs kept on nash:** `~/rang-data/uhf-s/` (link file, `venv/`,
  `scripts/`, `meta/`, `mvf/`, `ms/`) and the main checkout's
  `tools/heavy_lock.py`. Its status is `~/rang-data/uhf-s/status.md` (rewritten
  at each pass) and its log `logs/fetch-all.log`; the Windows status file
  `outputs/status/uhf-s-fetch.md` is no longer updated after this hand-back.
  Stop it with `kill` on the pid in `status.md`.
