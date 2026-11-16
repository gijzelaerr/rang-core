# E2-N: E2's frozen protocol on native, unprocessed MeerKAT data

Issue #7, task E2-N of [finish-plan.md](finish-plan.md) (A0 row E2-N,
[a0-acceptance.md](a0-acceptance.md) 0.4, 6.5). Branch `e2n` from main
`a931b6c`, 2026-11-16. Native Windows for rang; WSL for katdal's
`mvftoms.py` (python-casacore) and the Linux oracles.

**Status: proposal, frozen (2026-11-16) before any E2-N visibility, flag or
weight value was read.** Results so far in section 9 (fetch, conversion, DATA state). Sections 1 to 8 are the protocol; they change only by
a dated amendment, labelled post hoc for anything it could have seen. Results
go below section 9.

## 1. Data and provenance

| Item | Value |
| --- | --- |
| Archive | SARAO MeerKAT archive, MVFv4, read through katdal 0.23 with the owner's per-user token (read-only, about 60 days; kept in `D:\rang\sarao-link.txt`, never copied into a file, log, command line or note) |
| Capture block | **1735268787** (`1735268787_sdp_l0`), schedule block experiment ID 20241208-0049 |
| Proposal | SCI-20241101-KR-02, "ASKAP J1745 epoch 1 (part 1)" |
| Date | 2024-12-27, 03:06:36 to 08:21:20 UTC (5.25 h) |
| Status in the archive | public, AVAILABLE, QA Good; the visibility product was restaged for this task |
| Band | L, 856.0-1711.2 MHz, 1,024 channels of 835.9 kHz (`bc856M1k`) |
| Dumps | 2,360 at 8.0015 s |
| Antennas | 62: m000-m063 without m028 and m035 |
| Products | 7,812 (autos included), 7,564 cross (1,891 baselines × 4) |
| Size | visibilities of all products 151.0 GB (katdal shape × 8 B); with flags and weights about 162 GB in the archive |
| Licence and credit | public SARAO data; acknowledge "The MeerKAT telescope is operated by the South African Radio Astronomy Observatory, which is a facility of the National Research Foundation, an agency of the Department of Science and Innovation." and the proposal ID |

Scans (katdal's indices; slews omitted):

| katdal scan | Target | Tags | Dumps | Length |
| ---: | --- | --- | ---: | ---: |
| 1 | J0408-6545 | fluxcal, bpcal, delaycal | 74 | 592 s |
| 3 | J1331+3030 (3C 286) | polcal | 74 | 592 s |
| 5, 9, 13, 17, 21, 25, 29, 33 | J1744-5144 | gaincal | 14 (scan 25: 15) | 112 s (120 s) |
| 7, 11, 15, 19, 23, 27, 31 | ASKAP J1745 | target | 281-282 | 2,248-2,256 s |
| 35 | J1939-6342 (PKS 1934-638) | fluxcal, bpcal, delaycal | 74 | 592 s |

Each target scan is bracketed by J1744-5144. 3C 286 and 1934-638 have one
scan each, 4.7 h apart; J0408-6545 has one, at the start.

**What was read before this freeze, all metadata** (scripts in
[results/e2n-scripts/](results/e2n-scripts/), record
`D:\rang\outputs\e2n-20261116\meta\meta.json`):
- `e2n_meta.py`, run 2 (wall 732 s, 469 s of it opening the RDB at about
  0.7 MB/s): telstate, the scan list, targets and tags, antennas, the
  spectral window, shapes. Nothing else.
- **Run 1 failed and is disclosed.** It also asked for a sparse flag fraction
  (`--flag-every 50`). katdal's flag view requests the matching
  `correlator_data` chunks (its `data_lost` bit depends on them), and one
  request timed out (`StoreUnavailable`, connect timeout to the gateway).
  About 600 MB went over the network in that run. The script had computed and
  printed nothing; no flag, weight or visibility value was read, kept or
  written. **No flag fraction exists before the freeze.**

## 2. Why this data is native, and the check

- **Claim (an expectation, checked after the freeze).** DATA is the
  correlator's output with no calibration applied:
  - `mvftoms.py` runs without `--applycal` (default empty), so katdal applies
    none of the SDP L1/L2 solutions;
  - nothing between the archive and the MS phases the data. The LUNO product
    (A0 2.2) was pre-phased (XX−YY phase 0.016 rad, coherence 0.9997), which
    made KCROSS and Xf near-null there.
  - If so, K, KCROSS and Xf are solved here at their real size, which no
    earlier leg could test.
- **Possible confound, named now.** The F-engines apply delay tracking, and
  an observation that also fed a beamformer may carry F-engine phase-up
  gains. Whether this one did is not known from the metadata read.
- **Check (post-freeze, reported first in the results):** A0 2.2's DATA
  state probe, on J1939-6342, tile 1391.0-1417.5 MHz, the first 800 rows,
  cross-correlation cells with no flagged correlation: median |XX−YY phase|
  and its coherence over baselines; the baseline XX phase scatter; per
  baseline |⟨XY⟩|/|⟨XX⟩|. On J1331+3030 the cross-hand phase and its
  coherence.
- **Rule:** coherence below 0.5 → "native, unphased", as ESO137 (0.018).
  At 0.9 or above → "**observatory-phased**": the leg is reported under that
  name, and the KCROSS and Xf statements are worded "near-null as on LUNO".
  Between 0.5 and 0.9 → "partly phased", stated with the numbers. Every gate
  is read as frozen in each case.
- **Flags and weights are native too:** mvftoms writes the observatory's
  online flags and katdal's weights. `--flags` is set to rang's
  `meerkat.NATIVE_FLAGS` (static, cam, data_lost, ingest_rfi,
  predicted_rfi), so the SDP calibration pipeline's `cal_rfi` and
  post-processing `postproc` flags, which are processing products, are not
  carried. mvftoms's default `--quack 1` is kept.

## 3. Selection and the reserve (rule fixed now, from the scan table only)

The whole observation does not fit (section 4: about 600 GiB with the chain's
columns against about 400 GiB above D:'s 150 GiB floor). So, as the brief's
subset branch:
- **every calibrator scan:** katdal scans 1, 3, 5, 9, 13, 17, 21, 25, 29, 33,
  35;
- **the middle three target scans:** 15, 19, 23 (1.87 h on source). They are
  the middle of the track, so they are bracketed on both sides by the gain
  calibrator and by unused target scans.
- **Reserve, never fetched unless needed:** target scans 27 and 31 (with gain
  calibrator scans 25, 29, 33 already fetched). They are used only for one
  second attempt of the target gates after a fix (A0 6.5's E2-A rule), and
  fetched only then. The calibrator gates have no reserve: a rerun after a
  fix is labelled "seen", as E2-B's.
- **Untouched:** target scans 7 and 11.

1,179 dumps, 2.20 M cross rows after the quack. mvftoms numbers the written
scans 1 to 14 in time order (its `scan_itr`); the MS-to-katdal map is written
in the results from the MS's own SCAN_NUMBER and FIELD, before the run.

## 4. Fetch, conversion and disk budget

**Fetch.** [e2n_fetch.py](results/e2n-scripts/e2n_fetch.py) in a WSL uv venv
(katdal 0.23, katsdptelstate 1.0.0, python-casacore 3.8.1, public PyPI):
katdal's `mvf_download.py` chunk selection (`chunk_names` over every stored
array for `select(scans=...)`), but fetched over HTTPS by Python with the
token in memory (rclone, which `mvf_download.py` drives, is not on this host
and would carry the token in its argv). Resumable (`.part` then rename),
8 workers, one progress line per minute, to
`D:\rang\outputs\e2n-20261116\mvf\`. Booked `--slots 1 --mem 4`; wall time and
MB/s go to [tool-timings.md](tool-timings.md).

**Conversion.** `mvftoms.py -f -a --flags static,cam,data_lost,ingest_rfi,predicted_rfi`
on the local RDB (no token, no network), full polarisation, no
autocorrelations, no `-m` (rang writes MODEL_DATA and CORRECTED_DATA). First
straight to `D:` over 9p on one calibrator scan; if casacore's bulk I/O fails
there (ENOMEM, as in e2b-misses 9.20), to WSL ext4 and then copied to `D:`.
Every GiB on ext4 is counted as lost from `D:` (the vhdx shrinks only after
the owner's `Optimize-VHD`). After conversion: a `token=` search of every
log, the MS's HISTORY and OBSERVATION tables and their keywords, then
SHA-256 of FLAG and FLAG_ROW (gate 2a's reference, `e2_flaghash.py`) and
`rang-core listobs`.

**The MS lives at** `D:\rang\outputs\e2n-20261116\e2n.ms`.

**Disk (GiB; D: had 550.7 free at the freeze).** 2.20 M rows × 1,024 × 4
cells, 9.02e9 per column: complex64 67.2, float32 33.6, bit-packed FLAG
1.05.

| Step | Writes | Change | D: free after |
| --- | --- | ---: | ---: |
| fetch | MVF chunks of the selection (1,179 of 2,360 dumps: visibilities 75 GB, flags and weights about 19 GB) | −88 | 463 |
| mvftoms | DATA, WEIGHT_SPECTRUM, FLAG, subtables | −102 | 361 |
| delete the MVF chunks (after the MS's hashes; refetchable) | | +88 | 449 |
| rang chain (E2-A 9.6's table: MODEL_DATA, CORRECTED_DATA, CORRECTED_1GC, flag versions, images) | | −222 | 227 |
| post chain in place (E2-A 9.9, 9.10: CASA's CORRECTED_DATA, WSClean's reorder files) | | −70 peak | ≈ 157 |

- **Start rule for the rang arm:** at least 222 + 150 + 40 = **412 GiB**
  free at launch. If it is not met, the arm runs without target scan 23 and
  gain-calibrator scan 25 (`data.scans` then lists the rest), which saves
  about 72 GiB; that is recorded, not a gate.
- **Stop rule:** every command that writes to the MS runs inside
  [e2_diskguard.py](results/e2-acceptance-scripts/e2_diskguard.py) with the
  165 GiB floor (E2-A 9.6). A halt is an interruption, resumed by the same
  command (E2-A 9.5).
- The post chain's WSClean reorder files go to the same disk. If its peak
  would cross 165 GiB, its 3c images run on the target's rows only.

## 5. The configuration (frozen)

[results/e2n-scripts/e2n.yaml](results/e2n-scripts/e2n.yaml), with the
strategy file
[mk_rfi_flagging_calibrator_fields_firstpass.yaml](results/e2n-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml)
(byte-equal to E2's). `rang-core config check e2n.yaml` at the freeze: "valid
for flag, calibrate, apply, image, selfcal" (without an MS; the check against
the MS's fields runs after conversion and must give the same verdict, or the
leg stops before the run).

It is E2-B's chain plus E2-A's target as rerun (neither file alone fits this
track). Differences, each with its reason:

| Key | E2-N | E2-B / E2-A | Reason |
| --- | --- | --- | --- |
| roles | fcal = bpcal J1939-6342; gcal J1744-5144; xcal J1331+3030; target ASKAPJ1745 (mvftoms removes spaces) | E2-B: gcal J1833-2103 | this track's calibrators |
| J0408-6545 | flagged; corrected like the secondary; in no solve | – | rang and CASA have no matched model for it (CARACal: "not well tested yet"); it is unpolarised (CARACal `polcal_worker` list), so it carries the adapted leakage row (section 6) |
| `calibrate.average_freq`, `casa_phase_weights` | true | false | e2b-misses.md 9.26-9.27, frozen rule met on L and X: "the key becomes the E2 configuration's for the next unseen leg"; this is that leg |
| apply to target | K, F, B, Kcross, Xf, Df (gainfield J1939-6342, J1744-5144, J1939-6342), `parang: true` | E2-A: K1, G1, B1 from the primary | a gain calibrator brackets every target scan; CARACal's transfer |
| `image` | target only, E2-A's settings (4,096², 3″, Briggs 0.5, 8 joined channels, 2-term fit, mask 5σ, clean to 3σ, multiscale) with `average_channels: 2` | E2-A: `average_channels: 8` | 1,024 native channels: 2 gives 512 imaging channels of 1.67 MHz, as E2-A's 4,096 / 8 |
| `selfcal` | 2 rounds, Sp and Sa at solint 120, `average_time`, no C5b mask keys | E2-A rerun (9.5) | A0 rule 6 for every selfcal image, as accepted on 2026-11-15; the 0.5σ depth hit `niter` |
| `feed_angle_rotation` | −90 | the same | it sets the angle; mvftoms writes −π/2 itself (`ms_extra.populate_feed_dict`), so this is a no-op here and CASA's copies need no rewrite. The absolute χ of 3C 286 (section 6) is the test of that frame on a native product, the question chi-offset.md 10.1 left open |
| calibrator IQUV images (E2-B's 3c form) | not in the run | E2-B | one `image` section per configuration; the target's Stokes I is the image this leg adds |

Also fixed now:
- `calibrate.average_time` with Xf `combine: scan`: the defect of
  chi-offset.md 8 needs several 3C 286 scans; this track has one, and the key
  now never averages Gpol, KCROSS, Xf or Df across scans. Not exposed.
- The parallactic angle is casacore's (`parallactic_angle_casa`, main since
  e2b-misses 9.15) and joined-IQUV masking is WSClean's; both are main's
  behaviour and in this run.
- **Code:** a wheel built by `maturin build --release` at this branch's head
  (main `a931b6c` plus this note), installed with `uv pip install
  'rang-core[imaging]'` into a fresh venv
  `~/Build/tmp/20261116-e2n/wheel-venv`; its SHA-256 goes in the result.
- `rang-core run e2n.yaml e2n.ms` is gate 1's one command.

**Weights (A0 rule 3).** The frozen arm uses `weights: uniform`. A0 rule 3
also asks for `weights: as_is` on E2-N: a second rang arm,
`e2n-asis.yaml` = `e2n.yaml` with `data.weights: as_is` and
`run.stages: [flag, calibrate, apply, image]`, runs on the restored MS
after the first arm's post chain. It is read on gates 1, 2a and 3b (CASA
with the MS's own weights) and its target image against the uniform arm's
(reported, not gated). If time or disk does not allow it, it is "not run",
with the reason.

## 6. Gates

A0's gates (verbatim in [appendix A](results/e2-acceptance/appendix-a.md))
and E2's computations ([e2-acceptance.md](e2-acceptance.md) 6.5, E2-A 9.9,
9.10), with the scripts of `results/e2-acceptance-scripts/` adapted only in
field names, scans and paths (copies under `results/e2n-scripts/`, each run
once on E2-B's or E2-A's archived inputs or a development slice before it
reads an E2-N result).

**Unchanged:**

| Gate | E2-N |
| --- | --- |
| 1 | exit 0, every stage of `run.stages` in the receipt, no hand step |
| 2a | FLAG and FLAG_ROW restored from `rang_original` equal the hashes taken after conversion |
| 2b | python-casacore opens every table and column; CASA `listobs`, `flagmanager(mode='list')`; CASA `applycal` with rang's tables against rang's apply (class C, in place as E2-A 9.9); WSClean `-niter 0` on CORRECTED_DATA and MODEL_DATA; dask-ms reads the MS |
| 2c | astropy WCS parses every FITS rang wrote |
| 3a | Tricolour 0.2.1, the same strategy, `-fs polarisation`, `-dc DATA`, native input flags, every field; 0 cells differ, or the chunk-edge rule |
| 3b | CASA 6.7.6.14 runs CARACal's full-Stokes sequence (`e2_casa3b.py` with E2-N's fields) on rang's flags after calibrate, same refant list and models; K, KCROSS, Xf, Df by their limits; Gpol class B (0.1°); fcal K G B and gcal K F B composites class B (median 7e-4, p95 3e-3) |
| 3c | WSClean 3.7 of rang's CORRECTED_1GC (the apply output) at the image stage's settings (Stokes I, mask 5σ, threshold 3σ, multiscale): dirty L∞ ≤ 1e-6 of the peak; compact sources through `e2_score3c_a.py` (inner 0.7°, the 512-channel smearing limit) as 3c's bounds. WSClean 3.7 has no `-average-channels`, so it images 1,024 channels against GeMClean's 512, as E2-A |
| J1744-5144 | E2-B's 1830−211 row: I within 1 %, \|Δp\| ≤ 0.1 point, \|Δχ\| ≤ 1° against CASA after the full chain |
| 3C 286 parity | p and χ per 100 MHz (1.0-1.65 GHz, ≥ 10 % unflagged), visibility domain, sky frame, rang against CASA: \|Δp\| ≤ 0.1 point, \|Δχ\| ≤ 0.5° |
| Target, compact sources | ≥ 10σ isolated sources, rang's image-stage image against the oracle's (CASA-corrected data imaged by WSClean): ratio median within 1 %, robust scatter ≤ 1.5 % |
| Target, noise and dynamic range | off-source rms ≤ 1.2 × the oracle's; peak/rms ≥ 0.8 × |
| Self-calibration | rms after ≤ 1.02 × before (image 1 from CORRECTED_1GC against the final image); gains class B against QuartiCal 0.2.7 in E2-A 9.10's amended form (on rang's time-averaged inputs, labelled; unaveraged needs more memory than WSL has) |

**Adapted (labelled; gated at the frozen tolerance):**
- **1934−638 leakage → J0408-6545 leakage.** E2-B applied the development
  half's Df to a second 1934−638 scan. Here 1934−638 has one scan, so Df
  solved on it is applied (through the run's own apply) to J0408-6545, an
  unpolarised source 4.7 h earlier: the peak of the Q, U and V MFS images
  over I ≤ 0.3 % (`e2_leakage.py`'s method, field J0408-6545). Not circular:
  J0408-6545 is in no solve.

**Reported, not gated (they cannot apply as frozen):**
- **3C 286 transfer.** It needs Xf and Df from a different scan (E2-B's
  development half). This track has one 3C 286 scan, so the transfer would be
  circular. Reported: 3C 286's p and χ at 1.3-1.5 GHz on scan 3 against the
  frozen window (p 9.0-10.1 %, |χ − 33.1°| ≤ 7°), labelled "same-scan, not a
  transfer". This is the absolute-frame reading of section 5.
- **Flux scale (E2-A).** It needs two 1934−638 scans (solve on one, apply to
  the other). One exists, and J0408-6545 has no matched model. Reported:
  fluxscale's J1744-5144 flux density per spectral window, beside the
  SR2016-based scale.
- **Native size of the terms** (no tolerance exists): K, KCROSS and Xf of
  rang and CASA, the DATA-state probe of section 2.

**Expected before the run (from E2-B and E2-A, development and seen data
only):**
- Gpol: met (casa_phase_weights met class B on E2-B scan 17).
- fcal and gcal composites: not met at about E2-B's size (1.1e-3, p95
  1.5e-2), which e2b-misses section 3 traced to CASA's and rang's different
  K, G and B inputs, not a rang bug.
- 2b applycal: met (P follows casacore since e2b-misses 9.15; class C met on
  the whole E2-B MS).
- 3c dirty L∞: **not met** (WSClean's small inversion, e2b-misses 9.14). As
  E2-A 9.10, one `-no-small-inversion` dirty reading follows the primary
  one, labelled seen.
- 3a: exact on E2-B; expected exact or within a few cells.
- J1744-5144 χ: likely noise-limited if its p is a few tenths of a percent,
  as 1830−211's was. Read as frozen.

## 7. Oracles (A0 rule 8, pinned)

CASA 6.7.6.14 (`rang-o-casa`), QuartiCal 0.2.7 (`rang-formats-oracle:20261030`),
WSClean 3.7 (`rang-wsclean-native`), Tricolour 0.2.1 (`rang-tricolour:0.2.1-e1`).
CARACal's E3 arm is not part of E2-N.

## 8. Decision rule, cost and what is unseen

- **Unseen.** No E2-N visibility, flag or weight has been read by anyone in
  this project: the data were restaged for this task and the only access
  before this commit is section 1's metadata. The rang arm runs once with
  this configuration (A0 rule 2), and its result is reported as frozen.
- **Outcome.** Each gate in section 6's two gated groups is read met or not
  met against its tolerance; E2-N is **met** only if every gated row is met,
  and otherwise the misses are listed by gate. "Not checked" (an oracle that
  cannot run here, with the reason) is never read as met. Nothing is retuned
  against E2-N data and presented as a pass. A fix found here is tested on
  the reserve (target gates) or labelled "seen" (calibrator gates).
- **Cost.** The rang arm runs as one shared heavy-lock job (exclusive holds
  are blocked on this host for hours; ts-p1 T6), booked at **12 slots and
  40 GB** (GeMClean's 4,096², 512-channel Stokes I peak on the pilot was
  19.7 GB; calibrate's `memory_limit_gb` is 8), under `e2_timed.py` inside
  the disk guard. Its wall time is therefore indicative, not a timing claim;
  the lock's load records go beside it. Each oracle step is a shared job
  with its own booking (WSClean in WSL at 2 slots for dirty, 4 for clean).
  Everything goes in [tool-timings.md](tool-timings.md).
- No result here is a novelty claim (AGENTS.md).

## 8a. Amendment 1 (2026-11-16 16:58 local; metadata and layout only, before any value was read)

Found while fetching, from table layouts and receipts only:
- **A conversion test on katdal scan 35 alone** (`e2n_tomss.sh`, straight to `D:` over 9p) gave rc 0 in
  171 s at 3.7 GB peak RSS: casacore's bulk writes over 9p work for mvftoms, so the full conversion goes
  to `D:` directly and nothing goes to ext4. Of that MS only its table layout, column list, FEED
  RECEPTOR_ANGLE (−π/2 on every receptor, as `ms_extra.py` writes) and FIELD NAME were read; it was then
  deleted. Its log has no `token=` line.
- **mvftoms also writes SIGMA_SPECTRUM** (float32, its own tiled file). 139,934 rows took 8.8 GB, so the
  selection's MS is about 137 GiB, not 102. Nothing on the E2 path reads SIGMA_SPECTRUM (rang, CASA
  applycal and the solves, WSClean, Tricolour and QuartiCal use WEIGHT_SPECTRUM or unit weights), and E2's
  MSs had none. **It is removed right after conversion, before the hashes** (−34 GiB), which restores
  section 4's 102 GiB.
- **`mvf_download.chunk_names` fails in dask on a selection of several separate scans** ("zero-dimensional
  arrays cannot be concatenated"); `e2n_fetch.py` now lists chunks per scan and merges them. Same chunks.
- **Disk.** D: fell from 550.7 GiB (first reading, about 15:40 local) to 417.8 GiB at 16:30 local, because E2-A's rows chain
  (`e2a-score`) wrote CASA's CORRECTED_DATA into `e2a.ms` (374 GiB on D: in all). That chain still has its
  WSClean steps to run. Section 4's rules are unchanged; in addition, **the conversion starts only when
  D: will still hold 165 GiB plus the other sessions' announced writes after it**, so that no other
  session's disk guard trips because of E2-N. The rang arm's start rule (412 GiB) stands.

## 8b. Amendment 2 (2026-11-16 21:30 local; host only, no protocol change)

By the coordinator's message (owner's decision), E2-N moves to the shared Linux host **nash**
(`nash.ru.ac.za`: 36 cores, 503 GB RAM, 16 TB free on /home; other people use it). Every job there runs
under `nice -n 19 ionice -c3`, without sudo. What changes, and only this:
- **Data.** The selection of section 3 is fetched again on nash by the same `e2n_fetch.py`, into
  `~/rang-data/outputs/e2n-20261116/mvf/` (the owner placed the link file there, mode 600). nash's link
  is faster (about 20 MB/s against 5-7 MB/s on the Windows host). The Windows copy on `D:` is complete
  but for one weights chunk (read timeout) and two `correlator_data` chunks of dump 2 that the archive
  does not hold (HTTP 404; katdal marks such chunks `data_lost`). It is kept until nash's MS is built
  and hashed, then deleted.
- **Runs.** Conversion, the rang arm and the oracle arms run on nash, on the MS
  `~/rang-data/outputs/e2n-20261116/e2n.ms`. Section 4's D: budget and its 412 GiB start rule apply to
  the Windows host only; on nash the disk guard keeps 1 TB free. The rang arm runs from a Linux wheel
  built on nash at this branch's head, once nash's set-up reports a working build.
- **Oracles: the same pinned container images** (A0 rule 8). Revised at 21:50, before any oracle step
  ran: rather than PyPI venvs (whose casatools 6.7.6.14 wheel needs the image's manylinux_2_28 pin and
  measures data, which is exactly what the image already fixes), the four images `rang-o-casa:6.7.6.14`,
  `rang-wsclean-native:3.7`, `rang-tricolour:0.2.1-e1` and `rang-formats-oracle:20261030` are exported
  with `docker save` from the Windows host's WSL and run on nash by apptainer (SIF built from the
  docker archive), with the same bind mounts as `e2_post.docker`
  ([e2n_nash.py](results/e2n-scripts/e2n_nash.py) swaps the runner and nothing else). nash's own WSClean
  and CASA are not used.
- **WSClean's image does not run on nash** (`Illegal instruction`: `rang-wsclean-native` is built with
  `-DPORTABLE=OFF` for the Windows host's Ryzen 7 7700X; nash is a Xeon E5-2695 v4). The WSClean 3.7 in
  `rang-o-casa:6.7.6.14` (KERN's portable `wsclean=3.7-1kern1`, the same version string) runs instead.
  **Build check (development data, before any E2-N oracle step):** both images on the Windows host, the
  same argv (G3's D1.ms, 1,024², 2″, Briggs 0, dirty and PSF): L∞ differences 1.35e-7 of the dirty peak
  and 1.19e-7 of the PSF's, not bit-identical; that is float32 rounding, below gate 3c's 1e-6
  ([results/e2n/wsclean-build-check.json](results/e2n/wsclean-build-check.json)).
- **Timings** are labelled host nash; they are not comparable with the Windows host's.

## 9. Results

### 9.1 Fetch and conversion (2026-11-16)

- **Selection fetched** (section 3; katdal scans 1, 3, 5, 9, 13, 15, 17, 19, 21, 23, 25, 29, 33, 35):
  1,179 dumps, 6,545 chunks (5,948 in `sdp-l0`: `correlator_data`, `weights`, `weights_channel`; 597 in
  `sdp-l1-flags`). **6,543 present; 2 absent from the archive** (HTTP 404 on both hosts:
  `correlator_data/00002_00000` and `00002_00256`, dump 2 of the first scan; katdal flags such chunks
  `data_lost`). About 89 GB.
  - Windows host (WSL, to D:): scan 35 alone 5.98 GB in 1,457 s; the rest in two runs (16 then 32
    workers), 88.7 GB in 16,000 s, 5.5 MB/s, the server's rate rather than the workers'.
  - nash (amendment 2): the same script, 16 workers, 9-15 MB/s; the tail was filled by streaming the
    Windows copy's chunks to nash in reverse order (5 MB/s), then one refetch. **SHA-256 of all 6,542
    chunks the two copies share are equal**; nash's chunk manifest is
    `~/rang-data/outputs/e2n-20261116/mvf-sha256-nash.txt`.
- **Conversion on nash** (`e2n_tomss.sh`, mvftoms with `-f -a`, NATIVE_FLAGS, no `--applycal`):
  rc 0, 835 s wall, 5.6 GB peak RSS; no `token=` in its log. Then `e2n_prep_ms.py`: no `token=` in any
  subtable string, table or column keyword; SIGMA_SPECTRUM removed (amendment 1); MS 105 GiB.
- **The MS** `~/rang-data/outputs/e2n-20261116/e2n.ms` on nash: 2,229,489 rows, 1,024 channels × 4,
  fields J0408-6545, J1331+3030, J1744-5144, ASKAPJ1745, J1939-6342; RECEPTOR_ANGLE −π/2. MS scans
  ([ms-map.json](results/e2n/ms-map.json)):

  | MS scan | Field | Dumps | katdal scan |
  | ---: | --- | ---: | ---: |
  | 1 | J0408-6545 | 74 | 1 |
  | 2 | J1331+3030 | 74 | 3 |
  | 3, 4, 5 | J1744-5144 | 14 each | 5, 9, 13 |
  | 6, 8, 10 | ASKAPJ1745 | 281, 281, 282 | 15, 19, 23 |
  | 7, 9, 11, 12, 13 | J1744-5144 | 14, 14, 15, 14, 14 | 17, 21, 25, 29, 33 |
  | 14 | J1939-6342 | 74 | 35 |

- **Gate 2a's reference** ([flaghash-input.json](results/e2n/flaghash-input.json)): FLAG SHA-256
  `50c7ea35…194e`, FLAG_ROW `f2809997…c2ec9`.

### 9.2 The DATA-state check (section 2): **observatory-phased**

A0 2.2's probe, first 800 rows of each field, 1391.0-1416.9 MHz (channels 640-671), DATA
([datastate.json](results/e2n/datastate.json)); LUNO's and ESO137's values from A0 2.2 beside:

| | J1939-6342 | J1331+3030 | J1744-5144 | LUNO 1934 (A0) | ESO137 1934 (A0) |
| --- | ---: | ---: | ---: | ---: | ---: |
| median \|XX−YY phase\| (rad) | 0.0117 | 0.0087 | 0.0192 | 0.016 | 1.488 |
| XX−YY phase coherence | **0.99977** | 0.99991 | 0.99959 | 0.9997 | 0.018 |
| row XX phase scatter | 9.9° | 13.1° | 9.4° | 11.1° | 104° |
| per-row \|⟨XY⟩\|/\|⟨XX⟩\|, median | 1.52 % | 2.57 % | 1.60 % | 1.48 % | 1.35 % |
| XY phase over rows: mean, coherence | −49°, 0.12 | −176°, 0.69 | 0.5°, 0.08 | – | – |

- **Under section 2's rule (coherence 0.99977 ≥ 0.9) the leg is "observatory-phased".** DATA written
  by katdal's `mvftoms.py` with no calibration applied has the same flat parallel-hand phases as LUNO's
  product. So the flat phases are the observatory's (the F-engine gains this observation was taken
  with), not a processing step: this answers A0 section 10's first "not checked" item for a 2024 product.
- From here on the leg is reported as **E2-N (observatory-phased)**. K and KCROSS are expected near
  zero, as on LUNO. The XY phase of 3C 286, −176° with coherence 0.69, is the source's polarisation
  seen through the instrument frame plus any cross-hand phase; Xf's solve will separate the two, and
  is reported, not anticipated.
- Native, as claimed: no calibration was applied by the conversion, and flags and weights are the
  observatory's. Unphased, as hoped: **no**. Leakage is uncorrected (1.5 % on 1934−638, as LUNO).
- Every gate of section 6 is read as frozen. Nothing else changes.
