# UHF, second leg: data-free pieces and the gate (issue #11)

Branch `uhf-11` from main `e071bdab`, 2026-11-23. Follows
[uhf-scope.md](uhf-scope.md), which stays frozen. That note's section numbers
are cited here as "scope 2.2" and so on.

**Status: proposal, frozen 2026-11-23 before any code of this leg and before
the port-check run.**
- Nothing UHF has been measured.
- Sections 3-6 are proposed. Their measured outcomes go in section 8.
- Changes after this commit are dated amendments, labelled post hoc.

## 1. Data: still blocked on D1

- **No UHF visibilities are available to ra-ng.** Checked 2026-11-23:
  - all ten SARAO links on nash are L band: `sarao-link.txt` is E2-N's block,
    and `sarao-links-dl.txt` holds DL2's nine blocks, all
    856-1711.8 MHz per `results/dl2-data/meta/*.json`;
  - no `sarao-link-uhf*.txt` exists;
  - the coordinator's 2026-11-17 decisions leave D1 (archive blocks) to the
    owner.
- So **the gate in section 7 is not run in this leg.** By scope section 5's
  "no candidate" branch, nothing with UHF visibilities is fetched.
- **Candidate capture blocks for D1, with sources.** These are metadata
  from papers only, read 2026-11-23. Whether each is public, and its QA,
  is behind the archive login and not checked.

  | Block | Source | Bandpass cal | Gain cal | Notes |
  | --- | --- | --- | --- | --- |
  | 1676657789, 1678122565, 1678295187, 1680626188 | MeerKLASS UHF DR1, arXiv:2512.11964, Table 1 | J0408-6545 | J1051-2023 or J1058+0133 | 4,096 ch, 2 s dumps, about 1.5 h of on-the-fly target per block, calibrated with CARACal (KGBAKGB) |
  | 1688399183, 1689003684, 1689090392, 1689176790 | same table | J1331+3030 | J1058+0133 | same |
  | project SSV-20221103-SA-01 | arXiv:2408.07727 | not read | not read | UHF and L science verification, 2022-11-04/05 |
  | schedule block 20220329-0020 | arXiv:2507.07549 | not read | not read | UHF science verification |

  - The MeerKLASS targets are scanned on the fly, so their target scans
    are not a tracked imaging field. Their calibrator scans are about 5 min
    on J0408-6545 or 3C 286.
  - A 2 s dump makes a 4k block about four times E2-N's per-hour volume.
  - None of these blocks lists PKS 1934-638 tracking.
  - Scope section 7's wish list still applies: 1934-638 and 0408-65, a
    polarisation calibrator, a target bracketed by a gain calibrator, and
    the full array.

## 2. What this leg builds, and what it does not

Built here, each with its own check (sections 3-6):

| Piece | Check |
| --- | --- |
| PKS 0408-65 flux model (scope 2.1: BREAK) | equals its own manual-model conversion; range guard below 843 MHz |
| MeerKAT band detection behind the boundary (`meerkat.py`) | unit tests; the warning names the band |
| UHF synthetic MVF fixture (scope 2.4: none exists) | katdal opens it; channel centres inside 544-1088 MHz |
| Tricolour port with CARACal's `firstpass_UHF.yaml` (scope 2.2) | **port check P1** against Tricolour 0.2.1 on L-band calibrator scans |
| CARACal UHF configuration and CASA script for the gate (D4) | drafted, **not run, not frozen** |

Not built here:
- beam band switch (scope 2.3; nothing in the pipeline applies a beam);
- 1934-638 field model (D3: no CC BY-NC material in the package, so it is
  read at run time from a user path, which `calmodels` already allows);
- 3C 286 polarisation below 1 GHz and the RM correction (scope 2.5-2.6);
- gate numbers (D5).

Those need the development set, or the owner.

**Static masks are not changed.** Scope 2.2 lists "both masks always OR'd"
as possibly SILENT. On reading the oracle, rang matches Tricolour here:
- Tricolour's `apply_static_mask` collects every `*.staticmask` in its
  package (`collect_masks`, used by `examples/oracle_tricolour.py`), and the
  port ORs the same two files;
- the L-band mask's entries below 1088 MHz are site RFI, not receiver
  artefacts. They are 915.8-960 MHz (GSM), 1029.7-1030.5 MHz and
  1085.7-1088.4 MHz (aviation transponder bands), and the 1040 and 1051 MHz
  lines (DME). They apply to UHF data as much as to L-band data.

Choosing a mask per band would depart from the oracle. Under-masking below
915 MHz stays an open question for the development set.

## 3. PKS 0408-65 flux model

- **Source.** CARACal `8f7bb363` `caracal/data/southern_calibrators.txt`,
  entry `name=0408-65 epoch=2016`:
  - `log10 S = a + b x + c x^2 + d x^3`, with `x = log10(nu/MHz)` and S in Jy;
  - `a=-0.9790, b=3.3662, c=-1.1216, d=0.0861`.
  - Its header: "Generally valid from 843MHz (SUMSS) to 20GHz (ATCA)".
  - The coefficients are facts. The file is GPL-2.0, but nothing from it
    is copied except the four numbers, each cited.
- **In rang.** A new `fluxstd` standard, `CARACal 2016` (alias `caracal`),
  with one source, `0408-65` (aliases `J0408-6545`, `PKS0408-65`, `0408-658`).
  - Validity 843 MHz-20 GHz.
  - Below 843 MHz, `flux` refuses unless `extrapolate=True`. That is
    544-843 MHz of UHF, 55 % of the band, so a UHF user has to opt in.
  - `verified` is True: the model is exactly what CARACal hands CASA
    `setjy(standard='manual')`, a log polynomial with no CASA-compiled
    counterpart.
- **Check (frozen).** Three comparisons over 0.544-20 GHz, each to 1e-12
  relative:
  - `fluxstd.flux` against a direct evaluation of the four coefficients;
  - `fluxstd.manual` (FS1 validated it against `setjy`) with the exact
    manual-spix conversion at 1.284 GHz;
  - the conversion at 816 MHz.

  A CASA `setjy` run is not repeated: FS1 already pins `manual` to `setjy`.
- Hugo's SARAO memo is the reference for the 1934-638 scale. A
  0408-65-to-1934-638 cross-check at UHF needs data (D1).

## 4. Band detection

- `meerkat.band(chan_freq)` returns `"UHF"`, `"L"` or `"S"` when every
  channel centre lies in one nominal band, otherwise None. It allows 1 kHz
  of slack.
  - UHF is 544-1088 MHz and L is 856-1712 MHz. They overlap at 856-1088
    MHz, so the band is decided by the lowest and highest channel: a set
    entirely inside the overlap counts as L, the band rang is validated on.
  - S band is 1750-3500 MHz (SARAO S-band receiver, used only for naming
    here).
- `core_pipeline.band_warning` keeps its condition (anything outside L
  band warns) and names the detected band in the text. Decision D6 stands
  until the gate passes.
- Tests: L, UHF, S, a mixed set and an empty set; the warning text for a
  UHF set.

## 5. UHF MVF fixture

`meerkat.write_synthetic_mvf(..., band="UHF")` writes the same synthetic
MVF with:
- `centre_freq` 816 MHz;
- bandwidth 544 MHz;
- 4,096 channels of 132.8125 kHz;
- the band name `u` in the subarray product.

L stays the default and is byte-for-byte unchanged. Test: katdal opens the
UHF fixture, and the channel centres span 544-1088 MHz. L-band fixture
tests unchanged.

## 6. Port check P1: `firstpass_UHF.yaml` (frozen)

**Question.** Does rang's Tricolour port equal Tricolour 0.2.1 with CARACal's
UHF strategy? That strategy has three properties the L-band controls never
ran:
- `outlier_nsigma: 30`;
- three major iterations;
- `apply_static_mask` with `uvrange: "0~700"` and no `uvcontsub` pass.

**This is a port check on L-band data, not the UHF gate.** The strategy is
written in channels and windows and does not read frequency (scope 2.2), so
L-band data exercise every code path it has.

- **Strategy:** CARACal `8f7bb363` `caracal/data/meerkat_files/firstpass_UHF.yaml`,
  SHA-256 `4c336933bd6c4ad2c075945394d76e270665ce301b8353b7974601e3a0459856`.
  It is fetched into the run root, not committed (GPL-2.0).
- **Scans:** DL2 **train** block calibrator scans only (none held out, so no
  DL2 held-out set is read). They are listed here before the run:
  - 1735892129 scan 1: J1939-6342, 74 dumps, 1,024 ch, MS hash `e73c1bd2…3ad9`;
  - 1735892129 scan 3: J1744-5144, 14 dumps, 1,024 ch, `c610a145…888b`;
  - 1611426666 scan 4: J0538-4405, 15 dumps, 4,096 ch, `ae72509e…49da2`.
- **Inputs:** each frozen MS (under
  `~/rang-data/outputs/dl2-data-20261119/ms/`) is copied twice into this leg's
  own run root, `~/rang-data/outputs/uhf11-p1-20261123/`. Each teacher
  writes FLAG in its own copy, so both start from the native flags.
- **Tricolour:** `rang-tricolour_0.2.1-e1.sif` (SHA-256 `1fec3916…c2c4e1`),
  with DL2's argv: `tricolour -c strategy.yaml -fs polarisation -dc DATA -dpm
  -nw 4`.
- **rang:** `rang-core flag` with `flag.strategy: firstpass_UHF.yaml`, from
  nash's `~/Worktrees/rang/release-040` venv (rang-core 0.4.0, commit
  `3582566c`). This branch changes no flag code.
- **Host:** nash, under `tools/heavy_lock.py run --slots 4 --mem 24`, with
  `nice -n 19 ionice -c3`.
- **Criterion, per scan:**
  - FLAG cells where the two differ, divided by all cells, **≤ 1e-6**;
  - FLAG_ROW equal.

  DL2 measured the same port against the same image at 0 and 4.9e-8 with the
  calibrator strategy (dl2-data.md section 12), so 1e-6 is a 20-fold margin
  over the worst seen.
- **Outcomes:** pass (all three scans), or fail (any scan). A fail is
  recorded with the differing cells by strategy step where they can be
  localised, and the port is not changed in this leg without a new note.
- **Reported, not gated:** flagged fractions of both, wall times, and the
  fraction against the calibrator strategy's DL2 labels for the same scans.

## 7. The gate (proposed; not frozen, not run)

The coordinator ruled (2026-11-17) that D4 and D5 are frozen only once a
development set exists. What is proposed:

- **Arms:**
  - rang `rang-core run` (flag with `firstpass_UHF.yaml`, then K, G, B, F,
    then image);
  - CARACal `8f7bb363` with the drafted UHF configuration
    `results/uhf-11/caracal-uhf-draft.yml`;
  - CASA 6.7.6.14 `setjy`, `gaincal`, `bandpass` and `fluxscale` with
    `results/uhf-11/casa-uhf-draft.py`.

  All three run on the same development MS.
- **Carried over unchanged** (scope section 3): A0 rules 1-8, gates 1,
  2a-c, 3a-c, A0 6.2 term limits, and E3's reading words.
- **New numbers, proposed for D5:**
  - flux scale against the same model per 100 MHz, 2 % (arm against arm,
    same model);
  - leakage not gated at UHF until the development set shows the
    second-order floor;
  - χ transfer only above 900 MHz without an RM correction;
  - image geometry 6,144 × 3″.
- **Drafted, unrun.** The CARACal draft sets:
  - `meerkat_skymodel: false` and `meerkat_crystalball_skymodel: true`
    (scope 0.5);
  - `firstpass_UHF.yaml` for the calibrator flag worker;
  - no L-band `chans` flag;
  - `img_npix: 6144`, `img_cell: 3`.

## 8. Measured outcomes

(Filled in after the runs; nothing below this line was known when sections
1-7 were frozen.)

### 8.1 Port check P1: **pass**, flag for flag (2026-11-23)

Run root `~/rang-data/outputs/uhf11-p1-20261123/` on nash; scripts
[p1_run.sh](results/uhf-11/p1_run.sh), [p1_compare.py](results/uhf-11/p1_compare.py);
result [p1-result.json](results/uhf-11/p1-result.json), timings
[p1-timings.txt](results/uhf-11/p1-timings.txt).

| Scan | Cells | Differ | FLAG_ROW | Flagged (both) | DL2 calibrator strategy, same scan |
| --- | ---: | ---: | --- | ---: | ---: |
| 1735892129 scan 3 (J1744-5144, 1k) | 108,437,504 | 0 | equal | 0.4607 | 0.5072 |
| 1735892129 scan 1 (J1939-6342, 1k) | 573,169,664 | 0 | equal | 0.6603 | 0.5797 |
| 1611426666 scan 4 (J0538-4405, 4k) | 495,452,160 | 0 | equal | 0.5786 | 0.4898 |

- **Final flags are identical on all three scans** (0 of 1.18e9 cells). The
  frozen limit was 1e-6, so the port reproduces Tricolour 0.2.1 with
  `outlier_nsigma` 30, three major iterations and the `uvrange 0~700`
  static mask.
- Fractions include the native flags, so they are not RFI fractions. The
  UHF strategy flags more than the L-band calibrator strategy on two of the
  three scans. Read on L-band data, this says nothing about UHF RFI.
- **Wall (Tricolour / rang):** 311/231 s, 609/362 s and 615/322 s. Both
  had 4 threads on a shared host. Not a timing run.
- **Setup failures before the run.** Three attempts failed before any
  teacher's flags were extracted:
  - the DL2 MSs are frozen read-only, and `cp -a` kept the mode;
  - the release-040 venv has no python-casacore, so extraction now uses
    the system python3.

  The criteria were not touched.

### 8.2 PKS 0408-65

- rang's cubic against CARACal's setjy manual fit (`CARACAL_0408`, made by
  CARACal's own `convert_pb_to_casaspi` on nash at `8f7bb363`):
  - 4.5e-9 relative over 544-843 MHz;
  - 4.2e-11 over 843-1712 MHz;
  - 9.2e-7 over 1.7-20 GHz.
- The same run reproduced `CARACAL_1934`'s digits.
- Values: 39.69 Jy at 544 MHz (extrapolated), 26.61 Jy at 843 MHz and
  12.29 Jy at 1712 MHz.
- Tests: `tests/test_fluxstd.py` (0408 tests).

### 8.3 Band detection and the UHF fixture

- `meerkat.band` and the band-naming warning pass their tests.
- The UHF fixture opens in katdal 0.24 with channel centres 544.0-1065.3
  MHz (24 channels of 22.67 MHz).
- `tests/test_mk1_meerkat.py`: 11 passed, 1 skipped (mvftoms needs
  casacore). These ran in a scratch venv with the `[meerkat]` extra. CI has
  no katdal, so it skips them.
- Not checked: whether CARACal's flag worker accepts `flagger: tricolour`
  with `strategy: firstpass_UHF.yaml` as drafted in
  [caracal-uhf-draft.yml](results/uhf-11/caracal-uhf-draft.yml).

### 8.4 The gate

Not run. On 2026-11-23 the owner was asked for UHF archive links
(`~/rang-data/sarao-link-uhf*.txt`). A watcher waits for them; the scope
section 5 rule then applies before any visibility is read.

## For the coordinator

- Branch `uhf-11`. Data-free pieces implemented and checked. P1 passes
  bit for bit. The gate is unrun, blocked on D1 (links requested
  2026-11-23).
- Merge is safe without the gate. L-band behaviour is unchanged:
  - masks are untouched;
  - the warning's condition is the same;
  - the L fixture is the default.
