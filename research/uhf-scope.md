# UHF scope: what changes from L band, and the acceptance data

Issue #11, first leg (v0.5.0 in [roadmap.md](roadmap.md)). Branch `uhf-scope`
from main `9b4542c`, 2026-11-17.

**Status: scoping note, frozen 2026-11-17 before any UHF visibility was
read.** Nothing UHF is built. Sections 1-3 are a reading of source code and
documents (proposed, not measured). Section 4 is the data survey (metadata
only). Section 5 is the selection rule, frozen before its result in section
6. Changes go in dated amendments below section 9, labelled post hoc for
anything they could have seen.

## 0. The answer in brief

1. **No UHF data set qualifies today** under the frozen rule (section 5).
   Every candidate fails at least one of these: UHF visibilities, terms that
   allow research use and publication, full array and polarisation, a
   primary calibrator. Section 6 gives the table. So **no development or
   held-out visibilities were fetched**, and `rang-core listobs` and
   `config check` were not run. That is the rule's "no candidate" branch:
   the leg stays open as an owner decision (section 8, D1).
2. **The clean route is the SARAO archive** (public data after the
   proprietary period, E2-N's licence). It needs a new link from the owner:
   the link on nash is scoped by its token to E2-N's L-band capture block
   (`1735268787`) alone, and the archive's search API refuses anonymous
   queries ("Authentication required"). Section 7 names what to look for.
3. **On nash now:** UHF reference products only (39.2 MB, SHA-256 manifest):
   SARAO's published UHF sky models of the PKS 1934−638 and PKS 0407−65
   fields, the 1934−638 memorandum and the UHF holography beam metrics,
   in `~/rang-data/uhf/reference/` (section 6.2).
4. **The code does not refuse UHF**, although the docs say it is
   unsupported (`docs/limits.md`). Where it would be wrong:
   - the 0408−65 flux model is missing (`fluxstd` refuses the source);
   - every beam model is L band only and refuses UHF frequencies;
   - both Tricolour static masks are always OR'd, and the UHF mask holds
     only GSM 934.5-959.6 MHz;
   - the 3C 286 polarisation model is flat from 1.47 GHz;
   - there is no ionospheric RM correction, and RM rotates χ 2.5 times
     more at the band centre than at L band;
   - image size and cell are user settings, so L-band values give a field
     1.57 times too small.

   Section 2 has the detail.
5. **CARACal (`8f7bb363`) has no UHF configuration to use as the oracle.**
   - Its schema lists `meerkat_band: [L, UHF]`, but no worker reads the key.
     A case-insensitive `uhf` grep over its `*.py`, `*.yml` and `*.yaml`
     files finds only the schema.
   - None of the 8 files in `sample_configurations/` is UHF, and no code or
     configuration names `firstpass_UHF.yaml`.
   - Its UHF calibrator catalogues are registered as `crystal` models
     (`southern_calibrators.txt` lines 21-22). `crosscal_worker.py` 651-676
     predicts them only when `set_model.meerkat_crystalball_skymodel` is
     set.
   - The `lsm` branch is tested first. So the shipped
     `meerkat_skymodel: true` would put the L-band `pks1934-638.lsm` on UHF
     data.
   - The gate's CARACal arm therefore needs a UHF configuration frozen by us
     (owner decision D4).

## 1. The band

| | L | UHF |
| --- | --- | --- |
| Digitised band | 856-1712 MHz | 544-1088 MHz |
| Centre | 1284 MHz | 816 MHz |
| Wideband channels (4k mode) | 208.984 kHz | 132.812 kHz |
| Primary beam FWHM, `1.02 λ/13.5 m` (src/lib.rs:178) | 1.01° at centre | 1.59° at centre, 2.38° at 544 MHz |
| Synthesised beam at fixed uv | 1 | 1.57 times wider |
| λ² (ionospheric RM, χ rotation) | 0.055 m² | 0.135 m² (2.5 times), 0.30 m² at 544 MHz |

The SARAO guidelines give the receiver ranges (UHF 544-1088 MHz; SSA-0003C-001
rev 02, 2024). The 4k channel widths are the band divided by 4096.

## 2. What changes, stage by stage

Each row says what the code or upstream does now. BREAK means it raises or
refuses; SILENT means it runs and is wrong or poor at UHF; OK means it already
works. File references are to main `9b4542c`.

### 2.1 Flux models

- **PKS 1934−638.**
  - The default standard is SR2016 (`calmodels.py:135`). Below 11 GHz it is
    the Reynolds (1994) cubic, `fluxstd.py:94`.
  - Reynolds states his fit for 1.4-8.6 GHz. Below 1.38 GHz it rests on two
    points, 408 MHz (MRC) and 843 MHz (MOST). The whole UHF band is an
    interpolation between them (Reynolds, AT/39.3/040, Table 1).
  - rang's range guard is `ORACLE_RANGE = (0.05, 50) GHz` (`fluxstd.py:145`),
    the range the FS1 oracle sampled, not a published range. UHF passes it
    without `extrapolate`. **OK in code; the scale is the open question.**
  - Hugo (2021, SARAO memo M2600-0000-043, DOI 10.48479/pdx2-7372) compares
    the scale with Perley-Butler 2017 through 3C 286 transfer. He finds an
    absolute error of about 3 % at the top of UHF and up to 7 % at the
    bottom.
- **The 1934−638 field.**
  - At UHF the surrounding mJy AGN carry 20-40 % of the field flux over the
    lower half of the band, and the lowest 100 MHz are worst affected.
  - A point-source model biases bandpass solutions by up to 40 % (Hugo
    2021).
  - The L-band rule of thumb, off-axis sources up to about 5 %, does not
    carry over. **A field model is required, not optional.**
  - rang has no field model for 1934−638 at any band: `pks1934-638.lsm` is
    referenced (`calmodels.py:13`, `core_config.py:235`) but not shipped.
- **PKS 0408−65 (J0408-6545).**
  - Not supported: `fluxstd.flux` refuses unknown sources (`fluxstd.py:287-291`).
    **BREAK.**
  - CARACal's polynomial (`southern_calibrators.txt` line 17, epoch 2016) is
    "generally valid from 843 MHz", the file's own header. So below 843 MHz
    it is an extrapolation.
  - It is the second primary on many UHF tracks, and E2-N excluded it at L
    band for want of a model.
- **3C 286 and 3C 138.**
  - Stokes I: PB2017, with the table ranges `(0.05, 50)` and `(0.2, 50)` GHz
    (`fluxstd.py:174-181`). **OK.**
  - Polarisation: `NRAO_XCAL` (`calmodels.py:390-409`) applies the 1.47 GHz
    fraction and angle flat, with `rotmeas: 0`. Below 1 GHz this is an
    extrapolation with no frequency guard (manual models have none,
    `calmodels.py:226-256`). **SILENT.** How far 3C 286's and 3C 138's p and
    χ move across UHF was not looked up here (section 9).
- **Published UHF field models** (CC BY-NC 4.0, fetched, section 6.2):
  - `fitted.PKS1934.UBand.wsclean.cat.txt` (7,780 lines);
  - `fitted.PKS0407.UBand.wsclean.cat.txt` (8,874 lines).

  CARACal ships `1934-collapsed-uhf-cat.txt` and `0407-collapsed-uhf-cat.txt`
  as "crystal" models (catalogue epoch 2020). They are **not byte-equal** to
  the DOI release (SHA-256 `30e4b6ff…` against `37617942…` for 1934−638;
  7,831 against 7,780 lines).
  - The central components use different parametrisations: CARACal's is
    13.586 Jy at 815.87 MHz, the DOI's 15.089 Jy at 1283.79 MHz.
  - Evaluated here as WSClean ordinary polynomials in `f/f0 − 1`, they agree
    with each other and with Reynolds to about 2 % at the bottom of the band:

    | MHz | DOI `PRIM` | CARACal `prim` | Reynolds |
    | ---: | ---: | ---: | ---: |
    | 544 | 9.434 | 9.647 | 9.510 Jy |
    | 816 | 13.663 | 13.588 | 13.652 Jy |
    | 1088 | 15.042 | 15.053 | 15.043 Jy |

  - The fields (off-axis components) were not compared. Which file is the
    reference is owner decision D3.

### 2.2 Flagging

- **Static masks.**
  - `python/rang/data/4k_uhfband_meerkat.staticmask` (Tricolour 0.2.1) holds
    190 frequencies, all in one run, 934.47-959.57 MHz (GSM). Measured here
    with `core_flag.load_static_mask`.
  - `core_flag.py:294-295` and `core_pipeline.py:1045-1047, 1772-1773` load
    **both** masks whenever `static_masks: tricolour`. The Rust kernel masks
    a channel if any mask frequency falls inside it.
  - The L-band mask (13,600 frequencies, 915.8-1626.7 MHz) therefore also
    flags its entries below 1088 MHz in UHF data: 915.8-960, 1029.7-1030.5,
    1040.5-1041.3, 1051.6-1052.2 and 1085.7-1088.4 MHz.
  - Neither mask has an entry below 915.8 MHz, so 544-915 MHz is masked by
    SumThreshold alone. Which UHF allocations are active at the site was not
    checked here. **Possibly SILENT under-masking; no crash.**
- **Tricolour strategy.**
  - CARACal ships `firstpass_UHF.yaml` (at `8f7bb363`). It was diffed here
    against the calibrator strategy E2 uses,
    `mk_rfi_flagging_calibrator_fields_firstpass.yaml` (byte-equal to
    CARACal's copy). The UHF file:
    - uses `outlier_nsigma` 30 in every SumThreshold pass, where E2's uses 10;
    - runs 3 major iterations per pass, where E2's runs 5 then 1;
    - has no `uvcontsub_flagger` passes (E2's has two, Taylor degree 20 and
      25);
    - applies the static mask once with `uvrange: "0~700"`. E2's applies it
      over all baselines (`""`) and again over `0~550`.
  - Both strategies are written in channels and windows with no frequency in
    them, so they run on UHF as they are.
  - **Port check:** rang's Tricolour port is flag-for-flag on four L-band
    controls (`core-d-tricolour.md`). UHF needs the same 3a check with
    `firstpass_UHF.yaml`.
- **AOFlagger.** CARACal's shipped `.rfis` strategies (`firstpass_QUV.rfis`
  and others) have no UHF variant. rang ships none; `flag.strategy` is
  required.
- **Research flaggers.** F2's simulator (`f2flag_sim.py:26-27`) and F3's tile
  windows (`f3flag.py`) are L band. F3's network has seen only L band.
  Landman: weights are per observatory and band. **Not usable at UHF without
  retraining** (out of scope here).

### 2.3 Beam

- `beam_holography.py`:
  - L only: `L_BAND_URL`, line 39; `COMPARISON_BAND_HZ = (900e6, 1650e6)`,
    line 56;
  - "frequency outside the holography band", line 438;
  - KatBeam hard-coded to `MKAT-AA-L-JIM-2020`, lines 452-467;
  - EIDOS coefficients L only, lines 488-535.
- `beams.py:51-60, 209-215`: KatBeam L only. **BREAK at UHF.**
- The pipeline (`rang-core run`, gemclean) applies no primary-beam
  correction. Its Gaussian beam (`src/lib.rs:178`) scales with frequency.
  **OK.**
- **Upstream:**
  - de Villiers (2023) UHF holography, `MeerKAT_U_band_primary_beam.npz`,
    34.9 GB. It is in both the RATT bucket (`MeerKATbeams/`) and SARAO's
    DOI 10.48479/wdb0-h061, CC BY-NC 4.0. Its metrics file (28 MB) is on
    nash.
  - Whether katbeam's installed version has a UHF model was not checked
    (section 9).
  - Adding a band switch is code for the next leg.

### 2.4 The MeerKAT boundary

- `meerkat.py` reads frequencies from katdal and has no band check. Its
  `write_synthetic_mvf` test fixture is L only (`856e6`, `c856M4k`,
  lines 538-555), so **no UHF fixture exists**.
- `core_pipeline.py:243-300` warns on non-MeerKAT, and refuses more than one
  spectral window and circular feeds. It does not check the band.
- The research drivers refuse UHF by design: `core_prospective.py:68-73`,
  `history/python/flagging*.py`, and their tests.
- **Docs disagree with code:**
  - `docs/limits.md:21` and `docs/howto/image-your-ms.md:12-14` say UHF is
    not supported.
  - A UHF MS runs with no refusal.
  - The next leg either adds an explicit refusal or warning until UHF passes
    its gate, or changes the docs (owner decision D6).

### 2.5 Bandpass and leakage

- **Bandpass.**
  - The rang estimators are band-free.
  - What changes is the model (2.1): the solution is only as good as the
    1934−638 field model.
  - `fillgaps` and the smoothing windows are in channels. A 4k UHF channel
    is 0.64 of an L-band channel in frequency, so the same channel counts
    span less frequency.
- **Delay.** K is solved over the band. UHF's band is 0.64 of L band's
  width, so the same delay gives 0.64 of the total phase across the band.
  The KCROSS and K limits (A0 6.2, in ns) carry over unchanged.
- **Leakage (Df).**
  - Hugo (2021) finds second-order leakage limits dynamic range next to
    strong sources at −30 to −40 dB. CASA's linearised Df does not model
    it; CubiCal's full 2×2 per-channel solutions do.
  - At UHF 1934−638 is fainter (9.5-15.0 Jy across the band, Reynolds) and
    its field carries more of the flux (2.1), so the error budget next to it
    changes.
  - E2-B's leakage gate (≤ 0.3 % peak QUV/I on 1934−638) is an L-band
    number. Whether it holds at UHF is unmeasured; it must be re-frozen with
    a reason, not copied (D5).
- **Cross-hand phase and 3C 286.** 3C 286's fraction is lower at UHF, so the
  Xf signal is weaker. The A0 Xf limits (median ≤ 0.5°, p95 ≤ 2°) are
  estimator agreement limits and carry over. The χ transfer row does not
  (2.6).

### 2.6 Ionosphere and RM

- No ionospheric RM correction exists (no ALBUS or RMextract; only a model
  `rotmeas`, default 0, `calmodels.py:224`).
- Δχ = RM λ². A 2 rad m⁻² change, which A0 allowed at L band as 5.3° at
  1.4 GHz, is:
  - 15.5° at 816 MHz;
  - 34.8° at 544 MHz.
- **So E2-B's 3C 286 χ-transfer row (|χ − 33.1°| ≤ 7°) cannot be copied to
  UHF.** Options are a GNSS-derived RM correction (the Polcal-Primer README
  compares TrigNET and IGS RM with a Moon fit at UHF), or a χ row limited to
  the top of the band. This is owner decision D5.
- Differential ionospheric phase across a wider field grows as λ. Direction-
  dependent effects are #15, not this issue.

### 2.7 w-terms, field of view and imaging defaults

- gemclean and the wgridder take the frequencies from the MS, so uv scaling
  and w-terms follow (`core_imaging.py:442`, ε `1e-4`, `core_config.py:432`).
  **OK.**
- The primary beam is 1.57 times wider at the band centre than at L band's
  centre, and 2.36 times wider at 544 MHz (section 1). So the w-term matters more for a given image size, and so does
  bandwidth smearing at fixed channel averaging (A0 E2-A's inner 0.7° rule
  was set for L band).
- `image.size` and `image.scale` have no default (`core_config.py:394-395`).
  The E2-A geometry (4,096 × 3″) covers 3.4°, which is about 2.1 primary-beam
  FWHM at 816 MHz and 1.4 at 544 MHz, against 3.4 at L band. **A UHF geometry has to be frozen**
  (proposal: 4,096 × 4.5″ or 6,144 × 3″; D5).
- CARACal's shipped values are L-tuned:
  - `meerkat-defaults.yml`: `img_npix: 4096`, `img_cell: 1.3`;
  - an L-band `chans` flag of `856~880MHz`, which would flag good UHF data;
  - `restfreq` HI.

## 3. Oracles and gates to carry over

**Oracles** (pinned versions as A0 5.8):

- CASA 6.7.6.14: K, G, B, F, Gpol, KCROSS, Xf, Df, `setjy` (manual model
  for 0408−65), `applycal`.
- QuartiCal 0.2.7: class A.
- WSClean 3.7: imaging, `-predict` of the field models.
- Tricolour 0.2.1 with `firstpass_UHF.yaml`: 3a.
- CARACal `8f7bb363` with a UHF configuration frozen by us (D4).
- The UHF holography beam (de Villiers 2023), for any beam work.

**Gates carried over unchanged** (A0 sections 5 and 6, with the reasons
there):

- Rules 1-8 of A0 section 5: order, one shot, same inputs, noise from data,
  gauge-free products, one scorer, cost and pinned versions.
- Gates 1, 2a-c, 3a, 3b with classes A, B, C and T, and 3c.
- The term limits of A0 6.2 in their own units.
- E3's reading words ("comparable" within 20 %, flux within 2 %, speed
  within a factor of 1.5).

**Gates that need new numbers before any UHF run** (frozen in the next
leg's note, with reasons, not copied):

- Flux scale against the model, per 100 MHz:
  - A0 has 2 % for SR2016 at L band.
  - At UHF the model itself is uncertain by 3-7 % (Hugo 2021).
  - The gate compares arms against the same model, so 2 % may stand. But
    the model choice (Reynolds point, the DOI field model or CARACal's) is
    D3.
- 1934−638 leakage (≤ 0.3 % at L band): see 2.5.
- 3C 286 p and χ transfer: see 2.6. The p window [9.0, 10.1] % is an L-band
  value.
- Image geometry and the scorer's field limit: see 2.7.

## 4. Data candidates (metadata only)

Read before the freeze, and disclosed:
- bucket listings (RATT `ratt-public-data`; SARAO `archive-gw-1.kat.ac.za/public`);
- DOI landing pages;
- the Polcal-Primer README and its file list, from the GitHub API, without
  downloading the tarball;
- Zenodo record metadata;
- two `listobs` text files in DOI 10.48479/sbtr-k883;
- three 8-24 byte zarr chunks of G330's SPECTRAL_WINDOW (`REF_FREQUENCY`,
  `TOTAL_BANDWIDTH`, `NUM_CHAN`);
- the public `metadata.json` and calibration report of one capture block.

No visibility, flag or weight value of any candidate was read.

| # | Candidate | Where | Band (how known) | Calibrators | Shape | Size | Terms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | Polcal-Primer `moon_uhf_100MHz_mkcore.tar.gz` | github.com/africalim/Polcal-Primer `data/` (repo GPL-2.0) | UHF, 100 MHz of it (README) | J1939-6342 (1934−638), J1331+3030 (3C 286), J1733-1304, the Moon (`recipe.casa.py`) | core antennas only, "substantially averaged" (README) | 92.1 MB | "wholly owned by SARAO and distributed with intent of teaching purposes", MeerKAT data policy 4.2.2.2; full data "on request" as `EXT-20220902-BH-01`. The owner's LUNO permission (finish-plan item 6) names LUNO only |
| C2 | MeerSOLAR sample, `1718013481_splited.ms.tar.gz` | Zenodo 16068486 (DOI 10.5281/zenodo.16068485) | not stated; MeerSOLAR covers UHF and L (arXiv:2508.17983) | not stated | solar observation with receiver attenuation (paper) | 2.64 GB | CC BY-NC-ND 4.0, and the PyPI page asks users not to publish with it without the developer's permission |
| C3 | RATT public bucket | `ratt-public-data.s3.af-south-1` | ESO137, LUNO and G330 are L band (G330: 2,048 channels from 856 MHz over 856 MHz, decoded here) | – | – | – | no UHF visibilities; holds the UHF holography beam |
| C4 | SARAO DOI repository, 43 releases | `archive-gw-1.kat.ac.za/public/repository/10.48479/` | UHF products, but none of them visibilities | – | – | – | CC BY-NC 4.0: UHF field models (`hhhy-4r55`, `ez63-vx81`), holography (`wdb0-h061`), MeerKLASS UHF DR1 images (`h9k3-7295`, OTF scanning), G357.2 UHF image (`q20r-hb79`) |
| C5 | Capture block `1775040570` in the same public bucket (`dlm-eXX7O05XIO6/`) | anonymous MVF: RDB and chunks | not established (calibration report: 512 channels) | "Source list: Unknown" | 8 antennas, 8 s | – | engineering proposal `ENG-20260820-RS-01`, observer "Test User"; no terms |
| C6 | SARAO archive, public UHF capture blocks | archive.sarao.ac.za, katdal with a per-block link | UHF where chosen | the owner picks a block with 1934−638 and/or 0408−65 and a polcal | full array, 4k or 32k channels, 8 s or 2 s | about 0.5-1 TB for a 4 h 4k track | public after the proprietary period ("available to anyone", guidelines 4.1); acknowledgement 7.2. **Needs a new link from the owner** |
| C7 | Named UHF tracks without a public copy | Hugo (2021): a dedicated 1934−638 and 0407−65 UHF track, 2019-09-22; Polcal-Primer's full `EXT-20220902-BH-01`; a PKS 1830−211 UHF science-verification set (arXiv:2101.00188; size about 3.1 TB per a web-search summary, not read in the paper) | UHF | 1934−638, 0407−65; 3C 286 (EXT) | – | – | commissioning, SV or EXT classes: policy 4.2.2.2, "contact SARAO" |

Notes:
- **C5 is anonymous MVF in a public bucket.** That contradicts
  `mk1-katdal.md`'s "no public MVF exists". It is an engineering test with
  no source or terms and is not used. It may be useful as a small katdal
  smoke input, but only if SARAO confirms the bucket is meant to be public.
  This is for the coordinator.
- AWS Open Data has one MeerKAT entry, ESO137 (L band).
- Zenodo searches ("MeerKAT UHF", "… measurement set", "… visibilities") found
  no MeerKAT visibility release other than C2, whose band is not
  established.
- The archive's GraphQL schema is public, but `observations` and
  `proposals` both need authentication. So capture block IDs cannot be
  listed without an account.

## 5. Selection rule (frozen before any visibility was read)

Disclosure: the rule was written with every candidate's metadata (section 4)
already in hand. It was not written blind to the candidates. What it
precedes is any read of visibilities and the choice of scans.

A candidate is **eligible** only if all of these hold, judged from published
text and metadata, never from visibilities:

- **R1 Band.** UHF visibilities: channel centres inside 544-1088 MHz, stated
  by the publisher or the archive record.
- **R2 Access.** Obtainable without the owner's account: either anonymous
  download, or the E2-N route (a public archive block through a per-block
  link the owner issues). The candidate is eligible under R2 once that link
  exists.
- **R3 Terms.** Written terms that allow research use **and publication of
  results** by ra-ng:
  - CC BY or CC BY-NC (ra-ng is non-commercial research), or public SARAO
    archive data;
  - a teaching-only notice, a "contact the owner before publishing" clause
    or an unconfirmed class 4.2.2.2 dataset fails R3 until the owner
    records permission, as LUNO's was recorded.
- **R4 Calibrators.** At least one scan of 1934−638 or 0408−65.
- **R5 Array.** At least 40 antennas, four correlations, at least 1,024
  channels over the full band.

Among eligible candidates:

- **Development set:** the one with a polarisation calibrator (3C 286 or
  3C 138). Ties go to unprocessed (native) data, then to the smallest on
  disk. It must stay under 2 TB on nash without a note.
- **Held-out set:**
  - a second eligible candidate from a **different scheduling block**,
    chosen by the same order;
  - if only one block is eligible, a scan split fixed from its scan table
    before any visibility is read. Every calibrator scan of the first half
    of the track is development; every calibrator scan of the second half,
    and the target scans bracketed by them, are held out. Held-out scans
    are read only by the frozen run, as A0 section 4.
- **No eligible candidate:** nothing with visibilities is fetched. The leg
  stays open, and the archive route goes to the owner as D1.

## 6. Result of the rule

### 6.1 The candidates against R1-R5

| # | R1 | R2 | R3 | R4 | R5 | Eligible |
| --- | --- | --- | --- | --- | --- | --- |
| C1 Polcal-Primer | yes | yes | **no** (teaching only) | yes | **no** (core only, 100 MHz) | no |
| C2 MeerSOLAR | **not established** | yes | **no** (ND, publication clause) | not established | not established | no |
| C3 RATT bucket | **no** | – | – | – | – | no |
| C4 DOI repository | **no** (no visibilities) | – | – | – | – | no |
| C5 `1775040570` | not established | yes | **no** | **no** | **no** (8 antennas) | no |
| C6 archive | yes | **only with a new link** | yes | depends on the block | yes | **not yet** |
| C7 named tracks | yes | **no copy** | **no** (4.2.2.2) | yes | yes | no |

**No candidate is eligible.** By section 5, no visibilities were fetched and
the leg stays open (D1). C1 could become a quick development set only if
the owner records permission and accepts R5's failure for a smoke test, not
an acceptance gate (D2).

### 6.2 What is on nash

`~/rang-data/uhf/reference/` on nash, fetched 2026-11-17 with `curl` under
`nice -n 19 ionice -c3` from `archive-gw-1.kat.ac.za/public/repository/10.48479/`.
It holds 9 files, 39,235,200 B, wall 4.2 s, with load 10.0 before and 9.6
after. `SHA256SUMS` sits beside them:

| File | SHA-256 | Release, licence |
| --- | --- | --- |
| `hhhy-4r55/fitted.PKS1934.UBand.wsclean.cat.txt` | `376179423b04feb13c7899c20e7563ba10f1fbbca840ee9e2a7019d6d1faeec5` | Hugo (2021), DOI 10.48479/hhhy-4r55, CC BY-NC 4.0 |
| `hhhy-4r55/fitted.PKS1934.LBand.wsclean.cat.txt` | `b277bc6d4095bb22798cc70547d9563a56460eb6e450474854b93117534b1fb9` | as above |
| `hhhy-4r55/Memorandum.pdf` | `081aec14b8a55eebf5aeb8281d3fcb6e1d43f2c4366660d93b9da39bb23e9d48` | M2600-0000-043 rev C |
| `ez63-vx81/fitted.PKS0407.UBand.wsclean.cat.txt` | `bcd806d4fb3f86e79727bdc0ca95ee0500f6d82bbea4cb00f4d0a4627a70bf55` | DOI 10.48479/ez63-vx81, CC BY-NC 4.0 |
| `ez63-vx81/fitted.PKS0407.LBand.wsclean.cat.txt` | `2079515bb9db61da60f6bf3f217a329d47c3729c4b4d0f4d839037a3c0974ff9` | as above |
| `wdb0-h061/MeerKAT_U_band_primary_beam_metrics.npz` | `535dab11eaa5b925f2a4ca36f92b35f9000d9e4589747fa3cbb3af86de33452c` | de Villiers (2023), DOI 10.48479/wdb0-h061, CC BY-NC 4.0 |
| `*/index.html` (3) | in `SHA256SUMS` | the landing pages, for the licence text |

These are reference products, not acceptance data: the field models for the
oracles' `-predict` and the beam's metrics. The full UHF beam (34.9 GB) was
not fetched; nothing needs it before the beam band switch exists. The
CARACal copies sit in nash's `~/Github/caracal` at `8f7bb363`:
- `1934-collapsed-uhf-cat.txt`, `30e4b6ff7dddb2fa20b4aaea51b32a29cffe4600693bdd023af3cd0a7a21b32e`;
- `0407-collapsed-uhf-cat.txt`, `6fb50a9812a8d77bbf5f5180eb42efd1a34797c7da280753b2a12e161b5327b7`.

**Not run:** `rang-core listobs` and `rang-core config check` on a
development set, since none exists (section 5's "no candidate" branch).

## 7. What the owner would pick in the archive (for D1)

Under R1-R5, a block qualifies if it:

- is UHF in 4k (or 32k averaged to 4k) mode;
- has the full array (≥ 58 antennas);
- has 1934−638 and, ideally, 0408−65 (both have published UHF field models);
- has 3C 286 or 3C 138;
- has a target bracketed by a gain calibrator;
- is public (proprietary period over);
- has QA "Good".

**Two blocks**, or one long track split as in section 5. Disk:
- a 4 h 4k UHF track is about 0.5 TB of visibilities (E2-N's L-band 5.25 h
  at 1k was 151 GB; 4k is four times that per dump);
- the MS with the chain's columns is about 2.3 times that.

Two tracks fit under the 2 TB guideline on nash only if the target scans
are subset as E2-N did. The link goes in `~/rang-data/sarao-link-uhf*.txt`
(mode 600). It is used only by E2-N's `e2n_fetch.py` and `e2n_meta.py`,
which read the token into memory and scrub it from every log.

## 8. Owner decisions

- **D1 Data.** Pick one or two public UHF archive blocks and issue per-block
  links, or keep the leg open. Recommendation: one 1934−638 + 0408−65 +
  3C 286 track as development, and a second block as held out.
- **D2 Polcal-Primer UHF (C1).** Ask SARAO or the observer (B. Hugo) for
  research use, as was done for LUNO, or leave it out. Even with permission
  it is 100 MHz of the core and averaged: a smoke and tutorial set, not an
  acceptance set.
- **D3 Calibrator models.** Choose:
  - which UHF 1934−638 model rang uses and ships: the Reynolds point, the
    DOI field model, or CARACal's catalogue. They are different files, and
    their central components agree to about 2 % (2.1);
  - whether CC BY-NC models and beams may be shipped in the GPL-3.0
    package, or fetched at run time instead;
  - the 0408−65 model below 843 MHz.
- **D4 CARACal arm.** CARACal ships no UHF configuration. Approve freezing
  ours:
  - `firstpass_UHF.yaml`;
  - `meerkat_skymodel: false` with `meerkat_crystalball_skymodel: true`, so
    the UHF crystal models are used rather than the L-band lsm;
  - UHF `chans`, `img_npix` and `img_cell`.
- **D5 New gate numbers.** The leakage limit, the 3C 286 p and χ transfer
  rows (with or without an RM correction), and the image geometry and field
  limit, frozen in the next leg's note.
- **D6 Docs versus code.** Add a UHF warning or refusal until #11's gate
  passes, or reword `docs/limits.md`.
- **D7 The public capture block C5.** Ask SARAO whether `dlm-eXX7O05XIO6/`
  is meant to be public before anything uses it.
- **D8 SARAO policy 4.2.3 and 4.2.4.** Calibrator data used "for scientific
  purposes" and data used "for technical purposes (e.g. development of
  imaging algorithms)" say "discuss with SARAO". E2-N relied on the
  general public-data clause (4.1). Decide whether ra-ng asks SARAO once,
  for all bands.

## 9. Not checked

- Reynolds' cubic against Hugo's UHF fit: Figure 5 of the memo was not read
  numerically.
- C2's band and fields (not opened).
- katbeam's UHF model against the holography beam.
- Whether `firstpass_UHF.yaml` is used by any public CARACal run.
- 3C 286's and 3C 138's polarisation fraction and angle across 544-1088 MHz
  (Perley-Butler 2013 tables).
- Whether katbeam has a UHF model, and how it compares with the holography
  beam.
- Which RFI allocations are active at the site below 915 MHz.
- The off-axis components of the DOI and CARACal UHF field models.

## For the coordinator

- Branch `uhf-scope`: this note, a STATE paragraph, a README entry and a
  timing row. No code changes.
- No visibilities fetched; nash holds 39 MB of UHF reference products.
- The next step is D1. The first code step after it (band switch for beams
  and masks, 0408−65 model, a UHF MVF test fixture) waits for the data,
  per the issue.

## Coordinator decisions, 2026-11-17

- D3, in part: no CC BY-NC material ships in the GPL package or the repository. The NC terms conflict with GPL-3.0's freedom to use the material for any purpose. UHF calibrator models are either taken from an openly licensed source, or derived by ra-ng from data it may use, or read at run time from a path the user supplies.
- D6: the code warns. Any stage that is given UHF frequencies (or S-band ones) logs a warning saying that only L band is validated and naming `docs/limits.md`. This is a small code change, to be made with the v0.3.0 readiness work.
- D4 and D5 wait for data: they are frozen only once a development set exists.
- D1, D2, D7 and D8 are the owner's: they involve archive access on the owner's account or contact with SARAO.
- The anonymous MVF capture block found in passing is recorded only. It is not fetched, until D7 is answered.

## Coordinator decisions, 2026-11-26 (data in hand; owner: "do whatever is best")

D1 was taken by the owner on 2026-11-26: four public blocks, two UHF and two S
band ([uhf-s-fetch.md](uhf-s-fetch.md)). For the rest of section 8 the owner
delegated; these are taken by the coordinator's task `uhf-s-fetch`, on this
note's own recommendations, after reading the four blocks' metadata only.

- **D2 Polcal-Primer (C1): left out.** No one is asked. Public archive blocks
  now meet section 5, so a teaching-only, core-only, 100 MHz set adds nothing to
  the gate.
- **D3 Calibrator models:**
  - 1934-638 at UHF: the DOI field model (Hugo 2021, `hhhy-4r55`) in every
    rang and CASA arm, read at run time from nash; CARACal's arm keeps its own
    shipped catalogue and E3 reports the difference
    ([uhf-gate.md](uhf-gate.md) section 3).
  - Shipping: unchanged from 2026-11-17 (no CC BY-NC material in the package).
  - 0408-65 below 843 MHz: not used in any solve. On the held-out block it is a
    check source; its flux against CARACal's cubic and the DOI component is
    reported, not gated.
- **D4 CARACal arm: approved as recommended:** `firstpass_UHF.yaml`,
  `meerkat_skymodel: false` with `meerkat_crystalball_skymodel: true`, no
  L-band `chans` flag or mask. Frozen as `results/uhf-gate/caracal-uhf.yml`.
- **D5 New gate numbers: frozen in [uhf-gate.md](uhf-gate.md) section 5:**
  - J0408-6545 leakage ≤ 0.5 % (held-out block);
  - J0408-6545 flux transfer, rang against CASA, within 1 %;
  - a model row at 1e-5;
  - the geometry, 6,144 × 3″, and the scorer's field limit, 1.0°.
  - The 3C 286 transfer is reported only: one scan per block, and no RM
    correction.
- **D6 stands** (the warning, 2026-11-17).
- **D7 C5: not used, and SARAO is not asked now.** Nothing in the gate needs
  it. Recorded only.
- **D8 SARAO policy 4.2.3 and 4.2.4: for the owner.** These data are used
  exactly as 4.2.4 describes ("for technical purposes (e.g. development of
  imaging algorithms)"). The task proceeds under the public-data clause 4.1,
  with the acknowledgement, as E2-N did. **Recommendation: the owner asks SARAO
  once, for all bands, before results from these blocks are published.** The
  same message can ask SARAO to restage the four blocks (uhf-s-fetch.md 3.1).
  Nothing was sent.
