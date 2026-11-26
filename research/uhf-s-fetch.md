# UHF and S-band data: inventory, rule check and fetch (issues #11, #18)

Branch `uhf-s-fetch` from main `18726ccc`, 2026-11-26. Host nash (shared; every
job under `nice -n 19 ionice -c3` and the main checkout's `tools/heavy_lock.py`).
Run root `~/rang-data/uhf-s/` on nash. Follows [uhf-scope.md](uhf-scope.md)
(the frozen data rule, section 5) and [e2n-native.md](e2n-native.md) (the fetch
and conversion route). The protocol for the UHF gate is
[uhf-gate.md](uhf-gate.md); the S-band scoping note is
[sband-scope.md](sband-scope.md).

**Status (2026-11-26): metadata read for all four blocks; every block passes the
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
`~/rang-data/uhf-s/scripts/` on nash. Venv `~/Build/tmp/20261126-uhf-s/venv`
(uv, Python 3.11.18, public PyPI: katdal 0.23, katsdptelstate 1.0.0,
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
  lost 2 of 6,545.
- **Driver** ([uhfs_fetch_all.sh](results/uhf-s-fetch/scripts/uhfs_fetch_all.sh)):
  blocks in the order 1737424638, 1740534088, 1729932377, 1690097605. Before each
  fetch it lists the block's buckets
  ([uhfs_stagecheck.py](results/uhf-s-fetch/scripts/uhfs_stagecheck.py)) every
  30 minutes and fetches only when both list objects; a fetch that stops on the
  lost bound waits an hour and resumes (fetched chunks are kept). Disk rule:
  2 TiB stays free after the block's MVF and MS (3.3 times the cross
  visibilities). It stops at the links' expiry (2027-01-24). Each fetch is a
  shared lock job of 1 slot and 4 GB. It writes `~/rang-data/uhf-s/status.md`.
- **Conversion** ([uhfs_convert.sh](results/uhf-s-fetch/scripts/uhfs_convert.sh)),
  one block at a time: E2-N's `mvftoms.py -f -a --flags
  static,cam,data_lost,ingest_rfi,predicted_rfi` on the local RDB (no token, no
  network, no `--applycal`, default `--quack 1`), the whole block, into
  `~/rang-data/uhf-s/ms/<cbid>.ms`; booked 4 slots and 32 GB (unmeasured at 4k:
  E2-N's 1k conversion peaked at 5.6 GB). Then E2-N's prep step unchanged
  ([uhfs_prep_ms.py](results/uhf-s-fetch/scripts/uhfs_prep_ms.py): token search
  of every subtable and keyword, SIGMA_SPECTRUM removed, the MS map, SHA-256 of
  FLAG and FLAG_ROW), then SHA-256 of every file of the MS. Every log is
  searched for `token=` and JWT strings.
- **The MVF chunks are kept** after conversion (about 1.7 TB for all four). The
  links expire in about 60 days and restaging is slow, so the chunks are the
  only way to rebuild an MS after that; they are deleted when the gate has run.
- **Disk.** /home on nash had 12.8 TB free at the start. All four blocks at 3.3
  times their cross visibilities need about 5.1 TiB at the peak, leaving about
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

## For the coordinator

- **Fetched: nothing.** All four blocks pass the frozen rule, but their chunks
  are not on the archive's object store (0 objects listed; the control lists
  DL2's blocks). Only the RDBs are online. A watcher on nash fetches and
  converts each block when it appears; it writes `~/rang-data/uhf-s/status.md`.
- **The owner may want to ask SARAO to restage** (or check the archive's
  status page for these blocks): the links expire about 2027-01-24, and the
  watcher stops then.
- **Development set by the frozen rule: 1740534088**, held out 1737424638
  (section 2). The brief called 1737424638 the primary; the fetch order is
  kept.
- **Disk:** at the peak about 5.1 TiB of nash's 12.8 TB, MVF chunks kept until
  the gate has run.
- `uhf-11` (unmerged) and this branch both append to `uhf-scope.md`: a
  trivial merge conflict, both sections kept.
