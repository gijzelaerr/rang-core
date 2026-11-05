# A0: development and acceptance data, and the frozen acceptance protocol

Task A0 of [finish-plan.md](finish-plan.md), written 2026-11-05 on branch
`fp-a0-acceptance` from main `a81999b`.

**Status: protocol frozen; nothing in it has been run.** The data probes in
section 2 are measured; they read metadata and a few tens of MB of
development scans. Every gate, tolerance and setting in sections 5 to 7 is
proposed and frozen here, before any E1, E2 or E3 run. Results go below the
protocol in later reports; this text changes only through a dated, labelled
amendment. Probe archive:
[results/a0-acceptance-probes.json](results/a0-acceptance-probes.json).

## 0. The answer in brief

1. **No public observation meets the finish line's gate 1 as written.** Gate 1
   asks for an unseen MeerKAT L-band Measurement Set that is calibrated,
   imaged and self-calibrated in full polarisation. Every candidate fails at
   least one of these:
   - no polarised calibrator (ESO137);
   - processed flags and weights, with pre-phased DATA (LUNO);
   - no usable target (LUNO's target is the Moon);
   - two correlations only (G330).

   The gate stays open for native data. v0.2.0 must say so, as the plan
   already foresees (section 3, "fallback").
2. **Polarisation can be tested on real data, in one place only:** LUNO,
   scheduling block 20210818-0008. It holds 3C 286 (two scans), PKS 1934−638
   (two scans) and PKS 1830−211 (18 scans) in the same observation, checked in
   the store's own metadata (section 2.1).
   - Its DATA still carries the instrument's leakage: 1934−638 has 1.5 %
     median |XY|/|XX| per baseline, against 0.23 % in the publisher's
     CORRECTED_DATA. So leakage (Df) is a real test there.
   - Its parallel-hand and cross-hand phases are already flat in DATA (section
     2.2). So delay, KCROSS and Xf are near-null terms on LUNO and are tested
     for real only weakly.
   - Its flags and weights are processing products.

   **This is real but weaker than native data, and labelled so.**
3. **The only raw-phase real data is ESO137 ms1** (CC BY 4.0). Its DATA has
   antenna-dependent XX−YY phases (median 1.49 rad, coherence 0.018), so K, B
   and G are tested for real there. It has no polarised calibrator and zero
   cross-hand weights, so it is a Stokes I leg only.
4. **The split.** Acceptance is three legs, each with its own frozen gates.
   Each leg is labelled with what it can and cannot show:

   | Leg | Data | Tests | Cannot test |
   | --- | --- | --- | --- |
   | **E1** | A1's simulated truth (full polarisation, large K, KCROSS, Xf, Df, ≥ 90° parallactic rotation) | every term against known truth | real-instrument effects |
   | **E2-A** | ESO137 ms1: primary scans 9 and 11, target scan 10 (1 h), never read except one 128-channel tile chunk read by B1-2 | flag, K, G, B, apply, image, self-calibrate on raw phases; Stokes I | polarisation (no polarised calibrator; XY weights zero) |
   | **E2-B** | LUNO scans 17 to 20 (3C 286, 1934−638, two 1830−211 scans), never read | flag, K, G, B, F (`fluxscale`), Gpol, KCROSS, Xf, Df, apply, polarised images of calibrators; a 43° parallactic step from the development half | self-calibration on a real target; native flags and weights; large delays or cross-hand phases |
   | **E2-N** (open) | a native MeerKAT observation with 1934−638 and 3C 286 or 3C 138 | everything | – |

   Development is everything already read: LUNO scans 1 to 16, ESO137 ms1
   target scan 2, the ms1 primary subset and the simulations.
5. **Fetches needing approval** (section 8): E2-A 180 GB, E2-B 36 GB, the E2-A
   reserve 164 GB, CARACal's Stimela images (size not measured). An archive
   scheduling block for E2-N is the owner's decision. Nothing was fetched.

## 1. The candidates

| Candidate | State of DATA (measured, section 2) | Calibrators | Size | Licence | CARACal baseline |
| --- | --- | --- | --- | --- | --- |
| **LUNO calibrators** `LBAND_LUNO_CALIBRATORS.zarr`, SB 20210818-0008, 2021-08-18, 56 antennas, 4,096 ch, 8 s | pre-phased (XX−YY phase 0.016 rad, coherence 0.9997), uncalibrated amplitude (about 0.6 of Jy scale), leakage intact; FLAG and WEIGHT_SPECTRUM processed | 3C 286 (scans 1, 17), 1934−638 (2, 18), 1830−211 (3–16, 19, 20) | about 12.5 to 13 GB DATA per 10 min scan; 1.9 GB per 80 s scan | observer's permission (chat 2026-10-29), owner decision 2026-10-30; cite SARAO acknowledgement | none run; O-CASA ran CARACal's crosscal by hand on a four-station slice of scan 2 |
| **LUNO target** `LBAND_LUNO_TARGET.zarr` | as above | target = the Moon; FIELD direction 44–149′ from the Moon during the track | 16 × 10 min | as above | none |
| **LUNO/** | duplicate of the calibrator store (`flagging-luno-candidate.md`) | – | – | – | – |
| **ESO137 ms1** primary (8 scans of 1934−638, 408 s each) + target (7 × 1 h), 2019-05-09/10, 61 antennas, 4,096 ch | raw: XX−YY phase median 1.49 rad, coherence 0.018; XY present (1.35 % of XX) but XY/YX WEIGHT_SPECTRUM zero; flags processed (a `flautos` backup exists) | 1934−638 only (it is also the gain calibrator); no polarised calibrator | primary 16.4 GB per scan; target 147 GB per hour (DATA 105, WEIGHT_SPECTRUM 42); publisher's gains `ms1_gains.qc` 29.6 GB | CC BY 4.0, AWS Open Data registry, cite Ramatsoku et al. 2020 | none; the publisher describes CARACal processing, its gains are QuartiCal products |
| **ESO137 ms2** target only (7 × 1 h, 58 antennas), one day earlier | raw (not inspected beyond metadata) | **no calibrator scans in the bucket**; publisher's gains `ms2_gains.qc` 82.5 GB | 94 GB DATA per hour; WEIGHT and SIGMA columns empty | CC BY 4.0 | none |
| `eso.ms.tar.gz` (bucket root, 5.0 GB) | a CASA MS: `ms1_primary_subset.ms` (first tar entries read) | 1934−638 | 5.0 GB | as ESO137 | – |
| **G330** `G330.89-0.36.zarr` | 2 correlations, 2,048 channels, 30 scans of one field | none in the store | not measured | none found | – |
| **MGCLS_HI/** | HI image cubes and SoFiA products (22 GB FITS each), no visibilities | – | – | – | – |
| **SARAO archive** via katdal (MK1 loader) | native MVF | any project with 1934−638 and 3C 286/3C 138 (many L-band projects have both, e.g. MIGHTEE-pol) | about 13 GB per 10 min calibrator scan and 105–190 GB per target hour at 4k channels | public once the proprietary period ends (12 months for open time); a registered account issues a per-user token | – |
| **Ben Hugo's native set (L3)** | native, offered 2026-10-29, not received | same SB as LUNO | unknown | as LUNO | – |

Notes:

- **Ben Hugo's set is the same scheduling block as LUNO.** It would add native
  flags and weights, not independence: the LUNO development half has been
  read in detail. An independent native observation needs a different
  scheduling block (owner decision, section 9).
- The public listing in `mk1-katdal.md` is confirmed and complete for this
  purpose: `ESO137/` (`ms1_primary`, `ms1_primary_subset`, `ms1_target`,
  `ms1_target_subset`, `ms1_gains.qc`, `ms1_primary.bkp`, `ms2_target`,
  `ms2_gains.qc`), `G330/`, `LBAND_LUNO_*.zarr`, `LUNO/`, `MGCLS_HI/`,
  `MeerKATbeams*/`, `test-data/`, `scratch/`, and the root objects
  `eso.ms.tar.gz`, `index.html`, `test.txt`.
- No public MVF exists without a token (`mk1-katdal.md`), so a native set
  needs the owner.

## 2. Probes (measured, 2026-11-05)

All runs on the WSL host, single thread, `outputs/fp-a0-20261105-probe/`
(scripts `fp_a0_probe_state.py`, `fp_a0_probe_band.py` there; CARACal
sources under `caracal/`). The ranged reads decode blosc blocks with the
core's decoder; no pickle or object array was decoded. 31 MB and 94 MB of
visibility chunks were read, all from **development** scans (LUNO MAIN_0 and
MAIN_1, ESO137 ms1_primary MAIN_0). Held-out groups were read only for row
columns (TIME, ANTENNA1/2), `.zattrs` and listings.

### 2.1 Scans and parallactic angle

Parallactic angles from astropy at the MeerKAT reference position (the hand
formula agreed to 0.02°). LUNO, 2021-08-18:

| Scan (group) | Field | UTC start | Length | Parallactic angle | Elevation |
| --- | --- | --- | ---: | --- | --- |
| 1 (MAIN_0) | 3C 286 (J1331+3030) | 13:32:47 | 584 s | −169.3° → −171.6° | 28° |
| 2 (MAIN_1) | 1934−638 (J1939−6342) | 13:44:06 | 584 s | −113.2° → −111.2° | 23–24° |
| 3–16 (MAIN_2–15) | 1830−211 (J1833−2103) | 13:54–15:52 | 72–80 s each | −116.8° → −112.9° | 18–51° |
| **17 (MAIN_16)** | 3C 286 | 16:42:18 | 584 s | 147.1° → 145.3° | 19.6 → 18.5° |
| **18 (MAIN_17)** | 1934−638 | 16:53:53 | 592 s | −70.6° → −68.0° | 44° |
| **19, 20 (MAIN_18, 19)** | 1830−211 | 17:04:41, 17:16:33 | 80 s each | −114.8°, −115.7° | 59–61° |

- 3C 286's parallactic angle moves by 43.3° (mod 180°) between its two scans.
  That is enough to expose a wrong sign or a missing parallactic rotation, which
  would move the angle by about 87°. It is not enough to solve the source's
  own polarisation from rotation (CARACal strategy 3 needs at least 3 scans).
- 1830−211's angle barely changes (−117° to −113°), so it adds no
  parallactic leverage.
- The LUNO target store's single FIELD direction is fixed while the Moon moves.

ESO137 (2019-05-09/10): the primary scans 1, 3, …, 15 (408 s each)
alternate with target scans 2, 4, …, 14 (3,590 s each). Scan 10 (MAIN_4,
01:11 UTC) runs at parallactic angle 37° → 57° and elevation 56° → 51°. ms2 is
the same layout one day earlier with 58 antennas.

### 2.2 State of DATA: one channel tile, first 800 rows (development scans)

Tile 20 (1391.0–1417.5 MHz), cross-correlation cells with no correlation
flagged. Stokes are instrument-frame (`I=(XX+YY)/2`, `Q=(XX−YY)/2`,
`U=(XY+YX)/2`, `V=(XY−YX)/2i`), averaged over the cells.

| | LUNO 3C 286 DATA | LUNO 3C 286 CORRECTED | LUNO 1934 DATA | LUNO 1934 CORRECTED | ESO137 1934 DATA | ESO137 1934 CORRECTED |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| median \|XX\| | 10.20 | 16.05 | 9.31 | 14.98 | 7.96 | 14.90 |
| XX−YY phase, median \|rad\| | 0.016 | 0.015 | 0.016 | 0.014 | **1.488** | 0.011 |
| XX−YY phase coherence | 0.9997 | 0.9997 | 0.9997 | 0.9998 | **0.018** | 0.9999 |
| baseline XX phase scatter | 14.3° | 4.9° | 11.1° | 8.1° | 104° | 5.1° |
| per-baseline \|⟨XY⟩\|/\|⟨XX⟩\|, median | 4.0 % | 7.2 % | **1.48 %** | **0.23 %** | 1.35 % | 0 (zeroed) |
| cross-hand phase over baselines (3C 286) | 1.9°, coherence 0.967 | 0.4°, 0.996 | – | – | – | – |

Readings:

- **LUNO DATA is pre-phased but not amplitude-calibrated.** Its amplitude is
  about 0.6 of the flux scale for both sources (ESO137's raw DATA is 0.53).
  Its parallel and cross-hand phases are already nearly flat.
- **Whether that phasing is the observatory's or a processing step is not
  established.** CASA HISTORY has no split or mstransform row, and an
  observatory phase-up or an archive conversion with online solutions applied
  would produce the same picture. Either way, K, KCROSS and Xf solve to near
  zero on LUNO (O-CASA: K within ±0.011 ns).
- **Leakage is uncorrected in LUNO DATA:** 1.48 % per baseline on 1934−638,
  against 0.23 % in CORRECTED_DATA.
- **ESO137 DATA is raw in phase:** the XX−YY phases are incoherent across
  baselines. Its CORRECTED_DATA has XY and YX set to zero.

**3C 286 across the band** (development scan 1, first 800 rows of each tile,
publisher's CORRECTED_DATA; DATA in brackets):

| Tile (MHz) | Unflagged | p (%) | Angle in the instrument frame plus parallactic angle |
| --- | ---: | ---: | ---: |
| 909–936 | 11 % | 8.28 (8.08) | 28.5° (17.2°) |
| 1070–1097 | 23 % | 9.18 (9.24) | 31.4° (20.3°) |
| 1177–1204 | 0.5 % | 9.55 (9.45) | 32.8° (21.7°) |
| 1284–1311 | 12 % | 9.77 (9.77) | 34.0° (22.4°) |
| 1364–1391 | 76 % | 9.91 (9.75) | 34.8° (23.2°) |
| 1498–1525 | 39 % | 10.08 (10.25) | 35.5° (25.2°) |
| 1605–1632 | 9 % | 10.30 (10.43) | 35.8° (25.1°) |

These are a probe, not a measurement of the source:

- The angle column uses an ad hoc convention (χ_obs + PA) and is **not used
  for any frozen tolerance** below.
- The drift of about 7° across the band in CORRECTED_DATA is compatible with an
  uncorrected rotation measure of about −1.8 rad m⁻² (ionospheric or
  calibration). That is a post-hoc reading, not established.
- The fractional polarisation in DATA already matches CORRECTED_DATA to about
  0.2 points: leakage barely affects 3C 286's p at the 10 % level.
- On 1934−638 the publisher's CORRECTED_DATA has |Q|, |U|, |V| ≤ 0.08 % of I
  in tiles with at least 10 % of the cells unflagged.

### 2.3 Published values used below

| Source, quantity | Value | Reference |
| --- | --- | --- |
| 3C 286, p and χ at 1.4 GHz (MeerKAT) | 9.30 ± 0.02 %, 33.1 ± 0.1° | Taylor & Legodi 2024, AJ 167, 273 (arXiv:2405.04131) |
| 3C 286, p and χ (VLA) | 8.6 %, 33° at 1.05 GHz; 9.5 %, 33° at 1.45 GHz | Perley & Butler 2013, ApJS 206, 16 |
| 3C 286, CARACal's model | 14.7172 Jy at 1.47 GHz, p 9.8 %, χ 0.575959 rad (33.0°), RM 0 | `caracal/data/nrao_xcal.yml` at `8f7bb363` |
| 1934−638 | unpolarised (< 0.2 % at L band) | SARAO polarisation-calibrator notes; CARACal's `unpolarized_calibrators` list |

## 3. Polarisation: what real data can and cannot show

- **Present in LUNO:** a polarised calibrator (3C 286) and an unpolarised one
  (1934−638) in the same observation. DATA carries uncorrected leakage of about
  1.5 %, there are 584 s on each, and the parallactic step is 43°. That
  supports Gpol, KCROSS, Xf and Df solves, their apply, and a physical
  transfer check (section 6.3, E2-B).
- **Missing on real data, exactly:**
  1. native flags and weights for any polarised observation;
  2. an observation whose cross-hand delay and phase have not already been
     flattened, so KCROSS and Xf are tested at their real size;
  3. three or more 3C 286 scans spread in parallactic angle, which CARACal's
     strategy 3 and an in-observation check of the source model need;
  4. a target field worth imaging in Q and U: the LUNO target is the Moon;
  5. an ionospheric rotation-measure correction (no tool or data here).
- **Fallback, labelled weaker:** A1's simulated truth carries the large terms
  (requirements in "For the coordinator"). E2-B carries the real-instrument
  leakage and parallactic geometry. E2-N stays open.

## 4. Development and held-out data (frozen)

**Development data: may be read, plotted and tuned on.**

- LUNO calibrator store scans 1–16 (MAIN_0–MAIN_15), all tiles and columns.
- ESO137 ms1 target scan 2 (the GeMClean pilot), `ms1_target_subset`,
  `ms1_primary_subset`, ms1 primary scans 1 and 3 (MAIN_0, MAIN_1).
- The simulations S1–S3 and H1–H4, and everything A1 makes.
- O-CASA's slice and every archived campaign input.

**Held out: no visibility, flag, weight or image may be read before its E2
run.** Row columns, `.zarray`/`.zattrs`, listings and sizes are allowed.

- **E2-A:** ESO137 ms1 primary scans 9 and 11 (MAIN_4, MAIN_5) and target scan
  10 (MAIN_4).
- **E2-A reserve:** primary scan 13 (MAIN_6) and target scan 12 (MAIN_5).
  Used only for a second attempt after a fix (section 6.5).
- **E2-B:** LUNO calibrator store scans 17–20 (MAIN_16–MAIN_19).
- **Untouched:** ESO137 ms2 and `ms2_gains.qc`, the LUNO target store and the
  remaining ms1 target scans (4, 6, 8, 14).
  - These stay unread. They are a second reserve for an imaging and
    self-calibration-only check, since ms2 has no calibrator scans.

**Prior touches, disclosed:**

- B1-2 (S5, 2026-10-30) fetched `DATA/0.20.0`, FLAG and WEIGHT_SPECTRUM of row
  chunk 0, tile 20 of every ms1 target group, MAIN_4 and MAIN_5 included. That
  is 50,000 of 850,950 rows and 128 of 4,096 channels, used in a Fisher survey
  and never imaged. The E2-A target is therefore "unread except 0.18 % of its
  cells in one noise survey".
- `flagging-public-data.md` read nine small numeric chunks of the ms1 primary
  in September (listed in `results/meerkat-public-primary-metadata.json`;
  not checked here against MAIN_4 and MAIN_5).
- No report reads LUNO MAIN_16–MAIN_19 (searched in `research/`).
- **The E2-A sky is not unseen:** scan 2 of the same field was imaged in
  `gemclean-heldout.md`. The held-out unit is the visibilities and their
  calibration, not the sky.

## 5. Common rules for every gate (frozen)

1. **Order.** Every tolerance here is fixed now. A later task may tighten a
   gate for its own stage, never loosen one. A note written before a
   comparison may only add measures.
2. **One shot.** Each E2 leg runs once, in full, with the configuration
   committed beforehand. Its result is reported as frozen, pass or fail.
3. **Same inputs for every arm.** Arms are rang, the oracle chain and CARACal:
   - same channel and time selection, averaging, model column and weights;
   - LUNO weights over-state the noise 10–60 times, and ESO137 has zero
     cross-hand weights, so E2 and E3 use **`weights: uniform`** in every arm,
     as CARACal's shipped `prep.specweights: uniform` does;
   - `calwt=False` in every apply;
   - E2-N, when it exists, also runs `weights: as_is`.
4. **Noise-relative measures** use noise measured from adjacent-channel
   differences of the data (`examples/check_luno_noise.py`'s method), never the
   weights.
5. **Gauge.** Gains are compared through gauge-free products: per cell
   `P = DATA / CORRECTED_DATA` on the parallel hands, and the composite applied
   Jones on all four (O-CASA's method). Solutions alone are compared only for
   terms with a fixed reference (K, KCROSS, Xf, Df with refant).
6. **Image comparisons** run through one scorer. Fixed in advance:
   - the off-source mask: the mean of the arms' images above 5σ, dilated by 2
     beams;
   - one common restoring beam;
   - the threshold rule: automatic masking at 5σ, then cleaning to 3σ, σ the
     MAD of the residual. This holds for every imager.

   Nothing is chosen after seeing an arm, unlike `gemclean-heldout.md`'s
   threshold.
7. **Cost.** Wall time is end to end and per stage. Peak memory:
   - processes on the host: `/usr/bin/time -v`;
   - containers: the cgroup's `memory.peak`, read inside the container before
     exit, because `time` around `docker run` measures only the client.

   Every timing run has the host to itself and takes the heavy lock.
8. **Versions pinned:**
   - CASA 6.7.6.14 (`rang-o-casa`) and WSClean 3.7 (`rang-wsclean-native`);
   - QuartiCal 0.2.7 (`rang-formats-oracle:20261030`);
   - Tricolour 0.2.1, CARACal's strategies at `8f7bb363`; a Tricolour image
     must be rebuilt from `history/tools/flagging/`, since
     `rang-flagging:local` is gone;
   - CARACal at `8f7bb363876f5f0daecbf2167c36bb597c7e5160`.

   A newer upstream release is reported beside, never substituted.

## 6. The gates

### 6.1 Finish-line gates 1 to 5

| Gate | Measure, and how it is computed | Pass | Reason | A failure means |
| --- | --- | --- | --- | --- |
| **1 One command** | `rang-core run config.yaml my.ms` on the E2-A and E2-B Measurement Sets, from a clean venv with the wheel from public PyPI (or the tagged wheel before upload), config committed before the run | exit 0; every stage ran; no hand edit; receipt complete | the gate's wording | a stage crashed or needed a hand step: fix, then rerun on the reserve (6.5) |
| **2 Written back** | (a) FLAG backup restored, then the FLAG and FLAG_ROW hashes compared with the input's; (b) casacore opens every written column and table; CASA `listobs`, `flagmanager(mode='list')` and `applycal` (with rang's tables, on a copy) run; WSClean images CORRECTED_DATA and MODEL_DATA with `-niter 0`; QuartiCal reads the MS through dask-ms; (c) FITS headers parse with astropy WCS | (a) hashes equal; (b) every call exits 0, and CASA's `applycal` with rang's tables equals rang's own apply within class C; (c) WCS valid | exact round trip is the only meaningful bound for storage | a writer or schema bug: blocks release |
| **3a Flags vs Tricolour** | rang's flagging step against Tricolour 0.2.1 with the same strategy file, input flags and chunking, on the leg's data | 0 cells differ. If W3 must chunk differently from Tricolour, ≥ 1 − 1e-4 of cells agree and every differing cell lies within one window of a chunk edge | the port is flag for flag on four controls (`core-d-tricolour.md`, run `-02`) | a porting error, or a chunking effect if every difference sits at an edge |
| **3b Solutions vs CASA and QuartiCal** | per term, classes A, B, C and T of C1 (restated in 6.2) on the leg's data with matched settings | every term within its class | measured agreements, below | an estimator difference: located by term, not averaged away |
| **3c Images vs WSClean** | dirty images with matched gridder accuracy; cleaned images through the scorer; MODEL_DATA against WSClean `-predict` | dirty L∞ ≤ 1e-6 of the peak. Cleaned: compact-source flux ratio median within 0.5 %, robust scatter ≤ 1 %; Q/Q₀ within 0.5 %; off-source \|model\| ≤ 1.6 × WSClean's better loop; spectral index (sources ≥ 50σ) median \|Δα\| ≤ 0.05; each Stokes Q, U, V image of an unpolarised source no worse than WSClean's by 1.2 ×. MODEL_DATA per cell ≤ 1e-5 of the peak visibility at gridder ε 1e-6 | measured: dirty 6.5e-8 to 2.2e-7 of the peak, compact ratios 0.24–0.31 % scatter, Q/Q₀ differences 0.2–0.4 %, worst false-flux ratio 1.37 (`gemclean-heldout.md`) | an imager difference: G-task bug or a default that needs settling (G7) |
| **4 Against CARACal** | E3 (6.4) | runs and is reported with every number, any outcome | the plan | none for the gate; the reading is stated, not reworded |
| **5 Usable** | (a) the tutorial, followed by a reader without repository context (a fresh agent given only the docs and a public MS: `ms1_primary_subset` or an A1 product); (b) the W4 refusals, including a real two-correlation case from G330 (one small tile); (c) the CI end-to-end job on all five wheels | (a) an image is produced from the docs alone; (b) each case works or is refused with a message naming the cause; (c) green | the plan | docs or packaging, not science |

### 6.2 Stage tolerances (C1's classes, adopted)

From the C1 draft (`research/c1-calibration-chain.md`, branch `fp-c1-chain`),
restated so this note stands alone:

- **A**, same algorithm as QuartiCal 0.2.7: flags exact; complex entries and
  products ≤ 1e-6; iteration counts equal. Measured 1.4e-15 (`core-phase2.md`).
- **B**, CASA's estimator differs: composite products' relative difference has
  median ≤ 7e-4 and p95 ≤ 3e-3. The held-out parallel-hand MSE is within 2e-4
  relative. Measured on matched intervals: 4.9e-4 and 2.0e-3 (fixture),
  7.5e-5 and 2.1e-4 (slice) (`l5c-casa-gaincal`).
- **C**, apply: per cell ≤ 1e-6 relative, or ≤ 11 float32 epsilons of the
  cell's largest correlation; flags exact (measured up to 10.3 ε,
  `dfio-formats.md`).
- **T**, against simulated truth: noise-free products within 1e-5. With noise,
  each term's median error is at most 3 standard errors of the expected thermal
  error.

Term limits against CASA:

- **K:** |Δτ| median ≤ 0.01 ns, p95 ≤ 0.03 ns.
- **KCROSS:** |Δτ| ≤ 0.02 ns.
- **Gpol phase:** median ≤ 0.1°.
- **Xf:** median ≤ 0.5°, p95 ≤ 2° per channel.
- **Df, gauge-free combinations:** median ≤ 1e-3, p95 ≤ 5e-3.
- **F (`fluxscale`):** per-field flux and scale factors within 1e-3.
- **`setjy` and `manual` models:** 0 ulps (FS1).
- **Polarised model rows:** ≤ 1e-6 of |I|.

**On E2-B real data the class B limits apply only to the half's own solve.**
Transfers are judged by 6.3.

### 6.3 E1, E2 and E3

**E1: the chain on A1's simulated truth.** Everything is known, so every
failure is diagnosable.

| Measure | How | Pass | Reason |
| --- | --- | --- | --- |
| Each term | solution against truth, class T | T | thermal limit |
| Flags | recall of injected RFI cells above 5σ; false positives | recall ≥ 0.90; false-positive count equals Tricolour's on the same data (exact, 3a) | the oracle's own rate is the bound |
| Image, Stokes I | compact sources ≥ 50σ: flux ratio to truth; position | median within 1 %, scatter ≤ 1 %; position ≤ 0.1 beam | the 3c bounds, against truth |
| Residual | off-source rms after self-calibration, against a control run with the true gains | ≤ 1.1 × the control's | calibration should add at most 10 % above perfect gains |
| Polarisation | polarised sources (p ≥ 1 %, SNR ≥ 50): Δp and Δχ against truth; unpolarised sources: QUV/I | \|Δp\| ≤ 0.2 points, \|Δχ\| ≤ 1°; leakage ≤ 0.1 % of I | Df is known exactly in simulation; 0.1 % is below the CARACal-calibrated level seen on 1934−638 (≤ 0.08 %) plus noise |
| Self-calibration | gains recovered from a deliberately wrong starting model | T | as above |

**E2-A: ESO137 ms1, Stokes I, raw phases.**

- **Data:** primary scans 9 and 11 bracket target scan 10. All 4,096 channels
  for flagging and calibration, then averaged by 8 to 512 channels for imaging,
  identically for every arm.
- **Image:** 4,096 × 3″, Briggs 0.5, Stokes I, `-channels-out` 8 with a
  2-term spectral fit, the threshold rule of section 5 (item 6), no hand
  mask. This matches
  the pilot geometry.
- **Field limit:** at 512 channels bandwidth smearing reaches β ≈ 1 at the
  field edge, so the scorer uses the inner 0.7° radius.
- **Oracle chain:** CASA K, G, B by CARACal's sequence (6.4), then WSClean 3.7.
- **Second reference:** the publisher's `GKB-net` gains, compared only after
  the frozen run.

| Measure | How | Pass | Reason |
| --- | --- | --- | --- |
| Flags | 3a | 3a | – |
| Solutions | K, G, B against CASA on these scans | class B on composite products; K by its limit | – |
| Flux scale | solve on scan 9 only, apply to scan 11; 1934−638's Stokes I per 100 MHz against SR2016 | median within 2 % in every bin with ≥ 10 % unflagged | O-CASA: corrected I = 1.0003 × model; models differ by up to 1 % across the band |
| Target, compact sources | ≥ 10σ isolated sources: flux ratio rang/oracle | median within 1 %, robust scatter ≤ 1.5 % | 3c's imager bound plus calibration differences |
| Target, noise and dynamic range | off-source rms; peak/rms | rms ≤ 1.2 × the oracle's; dynamic range ≥ 0.8 × | parity, not thermal: the pilot's floor is 40–60 × thermal in every imager |
| Self-calibration | rms before and after; gains | after ≤ 1.02 × before; class B against QuartiCal on the same model | self-calibration must not degrade |

**E2-B: LUNO scans 17 to 20, full polarisation, calibrators.**

- **Stages:** flag, then the CARACal full-Stokes chain. That is K, G, B on
  1934−638 (scan 18); G and F on 1830−211 (scans 19–20); then Gpol, KCROSS
  and Xf on 3C 286 (scan 17), and Df on 1934−638.
- **Images:** 2,048 × 2″, robust 0, 8 joined channels, joined polarisations,
  for each field.
- **Feed angle:** `feed_angle_rotation: -90`. The store's RECEPTOR_ANGLE is 0,
  and CARACal's shipped config rewrites it to −90°, so rang uses the same frame.
- **Not imaged:** the Moon target.

| Measure | How | Pass | Reason |
| --- | --- | --- | --- |
| Flags | 3a | 3a | – |
| Own-half solutions | every term against CASA on scans 17–20 | 6.2 | – |
| 3C 286 parity | p and χ per 100 MHz bin (1.0–1.65 GHz, ≥ 10 % unflagged) from rang's and CASA's calibrated scan 17, sky frame | \|Δp\| ≤ 0.1 point, \|Δχ\| ≤ 0.5° | matched solves on the same data |
| **3C 286 transfer** | apply the development half's B, KCROSS, Xf and Df (scans 1–2) with per-scan G to scan 17, which sits 43° away in parallactic angle | at 1.3–1.5 GHz: p ∈ [9.0, 10.1] % and \|χ − 33.1°\| ≤ 7°; both arms reported | p spans 9.30 (MeerKAT), 9.5 (VLA), 9.8 (CARACal model) and 9.8–9.9 in the publisher's data; for χ, a 2 rad m⁻² change in ionospheric RM is 5.3° at 1.4 GHz, plus 1.7° for calibration. A sign error would move χ by about 87°. **Not circular:** Xf was solved on another scan |
| **1934−638 leakage** | dev-half Df applied to scan 18 (43° further in parallactic angle than scan 2); the peak of the Q, U and V MFS images over I | ≤ 0.3 % | the publisher reaches ≤ 0.08 % in sampled tiles; the transfer allows four times that |
| 1830−211 | I, p, χ against CASA after the full chain | flux within 1 %; \|Δp\| ≤ 0.1 point; \|Δχ\| ≤ 1° | parity only: the source is variable and its own polarisation is not a standard |

**E3: against CARACal (gate 4).** The settings are in 6.4.

- **Reported for each leg (E2-A and E2-B):**
  - image off-source rms and dynamic range;
  - compact-source and calibrator fluxes;
  - spectral index;
  - on E2-B, 3C 286's p and χ and 1934−638's leakage;
  - wall time for the whole run and per stage, at the same thread count
    (16), on an idle host;
  - peak memory (cgroup for containers) and peak disk.
- **There is no pass bar.** To prevent rewording, the reading words are frozen:
  - "**comparable**": every quality measure within 20 % of CARACal's, and flux
    within 2 %;
  - "**better**" or "**worse**": outside that, in the stated direction.
- Speed is read as "comparable" within a factor of 1.5.
- No reading is a novelty claim (AGENTS.md).

### 6.4 CARACal settings for E3 (frozen)

**Inspected:** CARACal `8f7bb363`.

- Workers: `crosscal_worker.py`, `polcal_worker.py`, `flag_worker.py`,
  `selfcal_worker.py`.
- Schemas: `crosscal`, `polcal`, `flag`, `selfcal`, `obsconf`, `transform`.
- Sample configs: `meerkat-defaults.yml`,
  `meerkat-fullStokes-continuum-defaults.yml`, `meerkat-polcal-strategies.yml`.
- Model and strategy files: `nrao_xcal.yml`, `firstpass_QUV.rfis`.

Copies are in `outputs/fp-a0-20261105-probe/caracal/`. The flag-worker
semantics were inspected as AGENTS.md requires: they are recorded in
`flagging-caracal.md` and below.

**E3-A uses `meerkat-defaults.yml`, as shipped:**

- `transform` splits the calibrators; `prep.specweights: uniform`.
- Calibrator flagging: autocorrelations; `flag_spw` 856–880 MHz,
  1658–1800 MHz and 1419.8–1421.3 MHz; `flag_mask` `meerkat.rfimask.npy` on
  0–1000 m; AOFlagger `firstpass_QUV.rfis`.
- `crosscal`: `uvrange '>150'`, `meerkat_skymodel: true` (the 1934−638 lsm),
  primary `KGBAKGB` with solints `inf, inf, inf, –, 60s, 60s, inf`,
  `b_fillgaps 70`.
- 1934−638 is both fcal and gcal, so the `no_secondary` branch runs; apply to
  gcal and bpcal.
- `transform__2` applies the calibration on the fly to the target.
- `flag__2`: `flag_spw` and AOFlagger `firstpass_QUV.rfis` on DATA.
- `selfcal` with CubiCal: `img_npix 4096`, `img_cell 1.3`, robust 0,
  `img_nchans 3` joined, `img_specfit_nrcoeff 2`, `img_mgain 0.9`,
  `cleanmask_thr 10, 6`, `clean_cutoff 0.5, 0.5`, `cal_niter 2`,
  `gain_matrix_type Fslope, Fslope`, `gsols_timeslots [120]`,
  `cal_timeslots_chunk 240`.
- `line` and `ddcal` are off.

**E3-B uses `meerkat-fullStokes-continuum-defaults.yml`, as shipped:**

- Calibrator flagging: shadow, autocorrelations, CASA `tfcrop`.
- `crosscal`: `uvrange '>150'`, `meerkat_skymodel`, primary `KGB` (solint
  `inf`), secondary `GAF` with `KB` applied.
- `polcal`: `pol_calib: xcal`, `leakage_calib: fcal`, `nrao_model: true`,
  `feed_angle_rotation: '-90'`, `extendflags`, `gain_solint 60s`,
  `time_solint inf`, `uvrange '>150'`; apply to gcal, bpcal and xcal.

**Deviations, labelled and fixed now:**

1. `getdata.dataid` and the MS names.
2. `obsconf` field roles set explicitly:
   - E3-A: fcal = bpcal = gcal = J1939−6342 (1934−638), target = the ESO137
     field;
   - E3-B: fcal = bpcal = J1939−6342, gcal = J1833−2103, **xcal = J1331+3030**
     (the shipped `J0521+1638` is not in the data).
3. E3-B's target stages (`transform__2`, `prep__2`, `flag__2`, `selfcal`,
   `polimg`) are disabled: there is no usable target.
4. `inspect` is disabled; it makes plots only.
5. E3-A `transform__2.split_field.chan_avg: 8`, the averaging every arm gets,
   because the host has 30 GB of RAM.
6. `shared_mem` and WSClean `absmem` are capped at 20 GB.
7. `refant`: the shipped value (`'0'` for E3-A, `auto` for E3-B). If that
   fails, as O-CASA found on short baselines, the antenna with the lowest
   flagged fraction under CARACal's own `get_refant` rule is used, recorded as a
   deviation.

**How CARACal runs:**

- Stimela with the CARACal cab images (not on this host; section 8).
- If it cannot run here, the same CASA calls run by hand in `rang-o-casa`, as
  O-CASA did, labelled "CARACal's sequence by hand". The selfcal stage is then
  WSClean plus QuartiCal `delay_and_offset` as the CubiCal stand-in, labelled
  as such.
- The MS for CARACal is the same file rang reads, with real FIELD and ANTENNA
  names. The ESO137 string subtables are pickled, so names come from a
  no-execution `pickletools` opcode walk or from `eso.ms.tar.gz` (section 8).

**Not like for like, reported rather than changed:**

- CARACal's shipped flaggers are AOFlagger `firstpass_QUV` and `tfcrop`, not
  Tricolour. Rang's flagger is the Tricolour port, so E3 compares whole
  strategies.
- CARACal's self-calibration is a delay self-calibration (`Fslope`). Rang's
  terms follow the owner's C5 decision (C1, owner decision 1).

### 6.5 Failure, retry and reporting

- **E1 failure:** a bug, located with truth. It is fixed, and E1 reruns; E1 is
  not held out.
- **E2-A failure:** recorded as frozen. After a fix, E2-A runs once on the
  reserve (scans 12, 11 and 13), reported as the second attempt beside the
  first.
- **E2-B failure:** recorded. There is no reserve, because both 3C 286 scans
  are used. A rerun after a fix is labelled "seen". The polarisation claim of
  v0.2.0 then rests on E1 plus the labelled rerun.
- **E3:** any outcome is reported; a "worse" reading goes into the release
  notes.
- **E2-N (native):** the same gates when the data exist; v0.2.0 states it is
  open.

## 7. Proposed, implemented, measured

| Item | State |
| --- | --- |
| Bucket listing, store metadata, scan table, parallactic angles, DATA-state probe, band probe, fetch sizes | **measured** (this report) |
| Choice of legs, held-out lists, all gates and tolerances, CARACal settings | **proposed, frozen** |
| E1, E2-A, E2-B, E2-N, E3 | not run |
| Every rang stage the gates test (C2–C7, G3–G9, W1–W4) | not implemented |

## 8. Fetches for the coordinator (none made)

All go under `/mnt/d/rang` (D: has 1.8 TB free); C: has 67 GB free and takes
none.

| Fetch | For | Compressed size (S3 listing) | On-disk footprint when written as an MS |
| --- | --- | ---: | --- |
| LUNO MAIN_16–19: DATA, FLAG, WEIGHT_SPECTRUM, row columns | E2-B | 15.7 + 15.6 + 2.5 + 2.5 = **36.3 GB** | 272,916 rows × 4,096 × 4: DATA 35.8 GB, WEIGHT_SPECTRUM 17.9 GB; with MODEL_DATA and CORRECTED_DATA about 125 GB per arm |
| LUNO MAIN_16–19 CORRECTED_DATA (publisher's reference, read only after E2-B) | E2-B, post hoc | 29.5 GB | – |
| LUNO MAIN_0 and MAIN_1, whole (development) | C6, C7 | 16.2 + 15.3 GB | – |
| ESO137 ms1 primary MAIN_4, MAIN_5 + target MAIN_4: DATA, FLAG, WEIGHT_SPECTRUM | E2-A | 16.4 × 2 + 147.2 = **180 GB** | about 1.05 M rows × 4,096 × 4: DATA 137 GB, WEIGHT_SPECTRUM 69 GB; about 480 GB per arm with MODEL and CORRECTED; CARACal's splits add about 300 GB |
| ESO137 reserve: primary MAIN_6 + target MAIN_5 | E2-A retry only | 16.4 + 147.2 = 164 GB | as above |
| `ms1_gains.qc/GKB-net` for scans 9–11 | E2-A, post hoc | part of 29.6 GB, not listed per scan | – |
| `eso.ms.tar.gz` | real subtable strings (FIELD, ANTENNA, FEED) for ESO137 | 5.0 GB | – |
| G330 one small tile and its subtables | gate 5b | not measured, expected < 50 MB | – |
| CARACal and its Stimela cab images (CASA, CubiCal, WSClean, AOFlagger, Tricolour) | E3 | not measured | – |
| A native SARAO scheduling block with 1934−638 and 3C 286 (or 3C 138) | E2-N | about 13 GB per 10 min calibrator scan, 105–190 GB per target hour at 4k channels | owner's decision |

## 9. Owner decisions

1. **Accept the split legs as the acceptance data** (E1 + E2-A + E2-B, E2-N
   open), with v0.2.0 stating that native data is not yet tested.
2. **Native data for E2-N:**
   - (a) ask Ben Hugo for a different scheduling block, since his offered set
     is LUNO's own; or
   - (b) obtain a SARAO archive token for a public scheduling block with
     1934−638 and 3C 286 or 3C 138, which MK1's loader reads; or
   - (c) leave E2-N open.

   Only the owner can contact the observer or register for a token.
3. **Approve the fetches** in section 8 and the CARACal image pulls.
4. **The polarisation claim of v0.2.0** rests on processed LUNO data and
   simulation. Confirm that this is acceptable wording for the release.

## 10. Not checked

- Whether LUNO's flat DATA phases come from an observatory phase-up or from a
  processing step.
- How many 3C 286 cells survive flagging over the whole of scans 1 and 17; only
  the first 800 rows of a few tiles were read.
- The source of the ≈ 7° angle drift across the band.
- The size of CARACal's Stimela images, and whether CARACal at `8f7bb363` runs
  under Stimela 2.1.4 on this host.
- Whether `eso.ms.tar.gz` holds subtables with real strings; only its first
  entries were listed.
- ms2's DATA state, the G330 field and its licence.
- Which SARAO archive scheduling blocks are public and suitable (no access).
- CASA `polcal` itself: O-CASA ran no polarisation task, so the oracle's
  polarisation chain is unexercised in `rang-o-casa`.
- Ionospheric RM for the LUNO track.

## 11. Timings

| Date | Tool | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-11-05 | bucket listing (`p1`, top-level and prefixes) | `ratt-public-data` | 1.2 s | – | anonymous S3 listing |
| 2026-11-05 | store metadata probe (`p2`): MAIN groups, shapes, columns | 10 stores | 48.6 s | – | listings and `.zarray` only |
| 2026-11-05 | `fp_a0_probe_state.py`, scan tables + DATA state (run 1; the state part failed on a decode call) | 5 stores' row columns | 1 min 29 s | 86 MB | 12.1 MB read |
| 2026-11-05 | `fp_a0_probe_state.py`, DATA state (run 3, after two fixes) | 3 groups × 800 rows × tile 20 | 8.1 s | 77 MB | 31.2 MB read |
| 2026-11-05 | `fp_a0_probe_band.py` | sizes, `eso.ms.tar.gz` first 2 MB, 2 groups × 7 tiles × 800 rows | 32.8 s | 79 MB | 94.3 MB read |
| 2026-11-05 | astropy parallactic angles | scan table | < 5 s | – | `iers.conf.auto_download = False` |
| 2026-11-05 | CARACal source downloads (`curl`) | 22 files at `8f7bb363` | a few s | – | raw.githubusercontent.com |

## For the coordinator

**`research/STATE.md`, new top entry:**

> A0, 2026-11-05 (proposed, frozen; probes measured;
> [a0-acceptance.md](a0-acceptance.md)). No public observation meets gate 1
> as written (unseen, native, calibrated through self-calibration, full
> polarisation).
> - **Polarisation:** testable on real data only in LUNO (SB 20210818-0008),
>   which has 3C 286, 1934−638 and 1830−211 together. Its DATA keeps 1.5 %
>   leakage but is pre-phased (XX−YY 0.016 rad), with processed flags and
>   weights.
> - **Raw phases:** ESO137 ms1 is the only raw-phase real set (XX−YY 1.49 rad),
>   but it has no polarised calibrator and zero cross-hand weights.
> - **Acceptance legs:** E1 (A1's simulated truth, full polarisation, large
>   delays and cross-hand phase); E2-A (ESO137 ms1 primary scans 9, 11 and
>   target scan 10, Stokes I, held out); E2-B (LUNO scans 17–20, held out,
>   with a 43° parallactic step from the development half); E2-N (native) open.
> - **Gates, tolerances and CARACal settings frozen:** `meerkat-defaults` for
>   E3-A, full-Stokes for E3-B, seven labelled deviations.
> - **Fetches awaiting approval:** E2-A 180 GB, E2-B 36 GB.

**`research/README.md` index entry:**

> New, 2026-11-05: A0, [acceptance data and protocol](a0-acceptance.md):
> development and held-out data, the frozen gates for the finish line, E1–E3,
> and CARACal's settings.

**`research/finish-plan.md`:**

- Section 3, under "Candidates for A0", replace the three bullets and the
  polarisation paragraph with: "Settled by A0 ([a0-acceptance.md](a0-acceptance.md)):
  E1 simulated truth; E2-A ESO137 ms1 (Stokes I, raw phases); E2-B LUNO scans
  17–20 (full polarisation, processed); E2-N native, open. Ben Hugo's set is
  LUNO's own scheduling block and adds native flags, not independence."
- E2 row: "Gates of A0 reported as frozen, on E2-A and E2-B; E2-N open."
- Section 5 risks, "Native data": add "LUNO's DATA is pre-phased, so KCROSS
  and Xf are near zero there; A1 must carry them."

**A1 requirements (from A0):**

- Full polarisation, linear feeds, MeerKAT 64-antenna geometry, 856–1712 MHz
  with at least 256 channels.
- Per-antenna delays of ±(1–10) ns and a bandpass with structure.
- KCROSS of a few ns, an Xf of tens of degrees varying with frequency, and Df
  of 1–3 % per antenna, frequency-dependent.
- An unpolarised flux calibrator and a polarised one (3C 286-like, p 9.5 %,
  χ 33°) with at least 90° of parallactic rotation over at least 3 scans.
- A gain calibrator, and a target with compact and extended sources, including
  polarised ones.
- RFI injected with a known mask.
- A thermal-noise level from which σ follows exactly.
- Seeds and provenance recorded.

**C1 answers (its "For A0"):**

- Matched CARACal arm: `meerkat-defaults` for E3-A; full-Stokes for E3-B with
  `xcal = J1331+3030`.
- Weights: `uniform` for E2 and E3 in every arm; `as_is` additionally on E2-N.
- LUNO's 3C 286 satisfies the polarisation data requirement in a weaker,
  labelled form (section 3).
- C7's limits: 6.3, "3C 286 transfer" and "1934−638 leakage".

**`research/tool-timings.md`:** the rows of section 11.

**Ignored outputs:** `outputs/fp-a0-20261105-probe/` (652 KB: probe scripts,
JSON, logs, CARACal sources). Nothing under `~/Build/tmp`.
