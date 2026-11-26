# S band: scope sketch and data (issue #18)

Branch `uhf-s-fetch`, 2026-11-26. A scoping note, not a protocol: nothing S-band
is built or frozen here. It follows the pattern of [uhf-scope.md](uhf-scope.md)
and uses the two S-band blocks inventoried in [uhf-s-fetch.md](uhf-s-fetch.md).
Everything below is a reading of metadata, code and documents (proposed, not
measured); no S-band visibility, flag or weight was read.

## 1. The band and the blocks

MeerKAT's S-band receiver covers 1750-3500 MHz and is digitised in 875 MHz
sub-bands (S0-S4, centres 2187.5, 2406.25, 2625, 2843.75 and 3062.5 MHz). One
stream holds one sub-band.

| | L (for scale) | S1, 1690097605 | S4, 1729932377 |
| --- | --- | --- | --- |
| Channels (4k) | 856-1712 MHz, 209.0 kHz | 1968.75-2843.54 MHz, 213.6 kHz | 2625.00-3499.79 MHz, 213.6 kHz |
| Centre | 1284 MHz | 2406 MHz | 3062 MHz |
| Primary beam FWHM, `1.02 λ/13.5 m` | 1.01° | 0.54° | 0.42° |
| Nyquist pixel at the top channel (7.7 km) | 2.4″ | 1.41″ | 1.15″ |
| λ² at the centre | 0.055 m² | 0.0155 m² | 0.0096 m² |
| Flux calibrator | – | PKS 0408-658: scans 0 and 42 (3.2 h apart) | J1939-6342: scans 0 and 24 (2.5 h apart) |
| Polarisation calibrator | – | 3C 138: scan 2 | 3C 286: scan 2 |
| Gain calibrator, targets | – | J0825-5010 (7 scans); NGC2442, NGC1566 alternating | J1427-4206, then J1733-1304; CirX1, SwiftJ1727 |

Both blocks pass the frozen data rule (uhf-s-fetch.md section 2), with "full
band" read against the 875 MHz stream. The 4k channel width (213.6 kHz) is
within 2.2 % of L band's (209.0 kHz), so strategies written in channels keep
almost the same width in Hz.

## 2. What changes, stage by stage (from code and documents)

- **Flux models.**
  - 1934-638: SR2016 below 11 GHz is the Reynolds cubic, fitted over 1.4-8.6
    GHz: S band is inside its range. **OK.**
  - 0408-65: CARACal's 2016 cubic is stated valid from 843 MHz to 20 GHz
    (branch `uhf-11` adds it to `fluxstd`). Inside its range; not validated
    against data at S band here.
  - 3C 286, 3C 138 Stokes I: PB2017. **OK.**
  - **Polarisation: SILENT.** `NRAO_XCAL` holds the 1.47 GHz fraction and angle
    flat (uhf-scope 2.1). 3C 286's fraction rises with frequency, so a flat
    9.8 % is wrong at S band. 3C 138 is variable in flux and polarisation, so a
    fixed model needs a date-matched value (VLA monitoring), not checked here.
  - Field models: off-axis flux inside a 0.4-0.5° beam is smaller than at L
    band, so a point 1934-638 may suffice; that is an expectation, not checked.
- **Flagging.** Neither of Tricolour 0.2.1's static masks has an entry above
  1.7 GHz, so `static_masks: tricolour` masks nothing at S band. CARACal ships no
  S-band strategy; the L-band calibrator first pass runs unchanged (windows in
  channels). Site RFI at 2-3.5 GHz was not looked up.
- **Beam.** Every rang beam model is L only and refuses S-band frequencies
  (uhf-scope 2.3). The pipeline applies no primary beam, and its Gaussian scales
  with frequency. **BREAK** only for beam work.
- **Pointing.** The beam is 2.4 times narrower than at L band at S4, so a
  pointing error costs more gain at the half-power point. Beam and pointing are
  closed as null at L band (b1-3-pointing-selfcal.md); S band is where that
  question would be sharper.
- **Ionosphere.** A 2 rad m⁻² RM change moves χ by 1.1° at 3062 MHz and 1.8° at
  2406 MHz, against 5.3° at 1.4 GHz. So E2-B's 3C 286 χ-transfer row
  (|χ − 33.1°| ≤ 7°) can carry over in form, with S-band values of p and χ.
- **Imaging.** Pixels must be at or below 1.15″ (S4) and 1.41″ (S1). A field of
  three primary-beam FWHM is 1.3° (S4) and 1.6° (S1): for example 4,096 × 1″
  (1.14°) at S4 and 6,144 × 1″ (1.7°) at S1.
- **The band warning** (coordinator D6, 2026-11-17) already covers S band: any
  stage given channels outside L band warns.

## 3. A gate sketch for #18

- **No cross-block held-out set exists.** The two blocks are different
  sub-bands, so a band-specific row on one says nothing about the other.
  uhf-scope section 5's single-block branch applies per block: every
  calibrator scan of the first half is development, every calibrator scan of
  the second half (and the target scans bracketed by them) is held out, fixed
  from the scan table before anything is read.
- **That split gives real transfers here, which UHF lacks:**
  - S4 (1729932377): 1934-638 at scans 0 and 24. Solve K, G, B and Df on scan 0;
    apply to scan 24: E2-A's flux-scale row and E2-B's 1934-638 leakage row,
    both non-circular. 3C 286 has one scan (2), so its χ is same-scan only.
  - S1 (1690097605): 0408-65 at scans 0 and 42 (unpolarised): the same flux and
    leakage transfers, with the 0408-65 cubic as the model. 3C 138 has one scan.
- **Carry over unchanged:** A0 rules 1-8, gates 1, 2a-c, 3a, 3b, 3c and the
  term limits, the secondary row and the 3C 286 parity row, as the UHF gate
  does ([uhf-gate.md](uhf-gate.md) section 5).
- **New numbers to freeze before any S-band run:** the leakage limit (L band's
  0.3 % is a candidate, since the second-order floor Hugo found is a UHF
  result); 3C 286's p window at S band from Perley-Butler 2013; the geometry
  and field limit above; and 3C 138 handled as parity only unless a dated model
  exists.
- **Oracles:** the same pinned set. CARACal has no S-band configuration, as at
  UHF; an S-band CARACal arm would be ours (`flag_spw` and the L-band mask off,
  `meerkat_skymodel` off).

## 4. Decisions this leaves for later

- Which S-band block goes first (suggestion: S4, 1729932377: 1934-638 twice and
  3C 286, the smaller at 276.5 GB).
- Whether to ask for a second block per sub-band, for a cross-block held-out set.
- The S-band polarisation models of 3C 286 and 3C 138.

## For the coordinator

- Nothing built or run. Both S blocks pass the data rule; neither is on the
  archive's object store yet (uhf-s-fetch.md 3.1).
- S band, unlike UHF, gives non-circular flux and leakage transfers within each
  block (two scans of the primary). Its χ transfer is circular as at UHF (one
  polarisation-calibrator scan per block), but the ionosphere is no longer the
  limit.
