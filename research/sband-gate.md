# The S-band gate: frozen protocol (issue #18, step 1)

Branch `sband-gate` from main `59e590a8`, 2026-11-27. Follows
[sband-scope.md](sband-scope.md) (the scope sketch; cited as "scope 2" and so
on), [uhf-gate.md](uhf-gate.md) (the UHF gate, whose structure this copies;
"UHF 5" and so on), [uhf-s-fetch.md](uhf-s-fetch.md) (the data, amendment 2)
and [a0-acceptance.md](a0-acceptance.md) (A0).

**Status: protocol, frozen 2026-11-27 before any S-band visibility, flag or
weight value was read by anyone in this project.** What was read before the
freeze: the two blocks' RDB metadata (uhf-s-fetch.md amendment 2,
[results/uhf-s-fetch/meta/](results/uhf-s-fetch/meta/)), the conversion
receipts (MS maps: SCAN_NUMBER, FIELD, row and dump counts, times;
RECEPTOR_ANGLE; channel range; byte counts), the flux standards evaluated by
`rang.fluxstd` from code, and Perley and Butler (2013). Changes after this
commit are dated amendments below section 10, labelled post hoc for anything
they could have seen. Nothing here is measured. No result here is a novelty
claim (AGENTS.md): the gate is parity with oracles plus transfers.

**Disclosure:** the half rule of section 2 is uhf-scope.md section 5's
single-block branch, but its tie-breaks (how a scan straddling the midpoint is
classed, which target is imaged) were written with the scan tables in hand.

## 1. The band and the blocks

The two S-band blocks on nash are the online replacements of uhf-s-fetch.md
amendment 2, not sband-scope.md's tape blocks (1729932377, 1690097605, never
fetched). Both are S band, both pass the frozen data rule, both were converted
whole and hashed (uhf-s-fetch status on nash, 2026-11-27).

| | L (for scale) | **S0, 1747682474** | **S1, 1680455600** |
| --- | --- | --- | --- |
| Proposal, description | – | SCI-20241102-GD-01, "A3528S S0band" | SSV-20230209-AD-01, NGC 2997 and NGC 4945 (Part 1) |
| Start (UTC), track | – | 2025-05-19 19:24, 4.22 h | 2023-04-02 17:16, 3.58 h |
| Antennas, baselines | 64 | 58, 1,653 | 57, 1,596 |
| Channels (4k), width | 856-1712 MHz, 209.0 kHz | 1750.00-2624.79 MHz, 213.6 kHz | 1968.75-2843.54 MHz, 213.6 kHz |
| Centre | 1284 MHz | 2187.4 MHz | 2406.1 MHz |
| Primary beam FWHM `1.02 λ/13.5 m` (bottom, centre, top) | 1.01° (centre) | 0.742°, 0.593°, 0.494° | 0.659°, 0.539°, 0.456° |
| Nyquist pixel at the top channel (7.7 km) | 2.4″ | 1.53″ | 1.41″ |
| λ² (bottom, centre) | 0.055 m² | 0.0293, 0.0188 m² | 0.0232, 0.0155 m² |
| χ shift for a 2 rad m⁻² RM change (bottom, centre) | 6.3° | 3.4°, 2.2° | 2.7°, 1.8° |
| Primary (flux, bandpass, leakage) | – | J1939-6342 (1934-638): katdal 1, 17, 35 | PKS 0408-658 (0408-65): katdal 3, 43 |
| Polarisation calibrator | – | J1331+3030 (3C 286): katdal 3 | 3C138: katdal 1 |
| Gain calibrator | – | J1311-2216 (3C283): 5, 9, 13, 19, 23, 27, 31 | J0825-5010: 5, 11, ..., 41 (7 scans) |
| Targets | – | A3528S: 7, 11, 15, 21, 25, 29 (224 dumps), 33 (45) | NGC4945: 7, 13, ..., 37; NGC2997: 9, 15, ..., 39 (100-101 each) |
| MS (whole block), rows | – | 592.3 GB, 2,948,952 | 465.4 GB, 2,317,392 |
| Flux model at the band (code) | – | SR2016: 13.87 Jy at 1750, 10.70 at 2625 MHz | CARACal 2016 cubic: 10.38 Jy at 1969, 6.54 at 2840 MHz |

- **S0 and S1 overlap over 1968.75-2624.79 MHz** (656 MHz), unlike the tape
  pair. The per-block split below stays (the issue's step 1); the overlap is
  used only for one reported cross-block row (section 5).
- S2-S4 (2625-3500 MHz above S1's top) are **not covered** by any block here.
- RECEPTOR_ANGLE is −π/2 in both MSs; both mvftoms logs carry no token.

## 2. The split, per block (from the scan tables only)

**Rule** (uhf-scope.md section 5, single-block branch, made exact here): a
track scan belongs to the first half when its centre time is before the
midpoint of the block's track time (first track dump to last track dump), else
to the second. First-half calibrator scans are development; second-half
calibrator scans are held out; target scans bracketed by two calibrator scans
of the same half belong to that half; a target scan bracketed by one scan of
each half is **untouched**. Second-half target scans are the **reserve**
(converted only if a fix is tested on target rows).

**S0, 1747682474** (track 19:24:01-23:37:17 UTC, midpoint 21:30:39):
- the 1934-638 scan katdal 17 runs 21:28:19-21:38:12; its centre 21:32:15 is
  after the midpoint, so it is **held out** (by start time it would be
  development; the centre rule decides, stated now);
- **development** `1,3,5,7,9,11,13`: 1934-638 1 (74 dumps); 3C 286 3 (74);
  J1311-2216 5, 9, 13; A3528S 7, 11 (224 each); 639 dumps, about 212 GB;
- **held out (transfer rows)** `17,35`: 1934-638, 74 dumps each, 2.0 h and 4.1 h
  after the development scan;
- **reserve:** A3528S 21, 25, 29, 33 with J1311-2216 19, 23, 27, 31;
  **untouched:** A3528S 15 (between J1311-2216 13 and 1934-638 17).

**S1, 1680455600** (track 17:15:45-20:50:40 UTC, midpoint 19:03:13):
- NGC2997 katdal 21 (centre 18:58:24) is in the first half but bracketed by
  J0825-5010 17 (development) and 23 (centre 19:07:29, held out): untouched;
- **development** `1,3,5,9,11,15,17`: 3C138 1 (39); PKS 0408-658 3 (37);
  J0825-5010 5, 11, 17; NGC2997 9, 15 (101 each); 333 dumps, about 107 GB;
- **held out (transfer rows)** `43`: PKS 0408-658, 37 dumps, 3.4 h after scan 3;
- **reserve:** J0825-5010 23-41 with the NGC2997 and NGC4945 scans between
  them; **untouched:** NGC4945 7, 13, 19 and NGC2997 21.
- **One target is imaged, NGC2997** (stated now, from the literature only):
  NGC 4945 is a bright edge-on starburst whose disc would make the compact
  and dynamic-range rows measure deconvolution of extended emission;
  NGC 2997 is a face-on spiral of lower surface brightness.

**Physical selection (UHF amendment 1).** Each half is its own MS, made by
`mvftoms.py -f -a --flags static,cam,data_lost,ingest_rfi,predicted_rfi
--scans <list>` from the kept MVF chunks into the run root
`~/rang-data/outputs/sband-gate-20261127/<block>/`, then E2-N's prep step and
the FLAG and FLAG_ROW hashes (gate 2a's reference per MS). The development MSs
are made first; the held-out MSs are made only after every development row of
that block is recorded. The whole-block MSs in `~/rang-data/uhf-s/ms/` are not
read.

**Why held-out rows are transfers only.** Neither second half has a
polarisation-calibrator scan, so the full-Stokes chain cannot run on a held-out
MS alone. Held-out rows are therefore E2-A's and E2-B's transfers (scope 3):
development tables applied to the held-out primary scans. The carried-over
parity rows (gates 1-3c, the secondary, the polarisation calibrator, the
target) are read on the development run only.

## 3. Calibrator models

| Source | Role | Model in every rang and CASA solve | Reason |
| --- | --- | --- | --- |
| 1934-638 (S0) | fcal, bpcal, leakage | `setjy` Stevens-Reynolds 2016, a point (as E2-N); MODEL_DATA written by rang and used by the CASA arm (A0 rule 3) | SR2016 is fitted over 1.4-8.6 GHz (scope 2): S0 is inside. Off-axis field flux is **not modelled**: a named risk for the B and flux rows, smaller than at L band (primary beam 0.5-0.74°) and identical in both arms |
| PKS 0408-65 (S1) | fcal, bpcal, leakage | `setjy` `CARACal 2016` (CARACal 8f7bb363's cubic; `rang.fluxstd`, marked verified as an exact conversion); MODEL_DATA written by rang and used by the CASA arm (CASA has no 0408-65 standard) | stated valid 843 MHz-20 GHz, not validated against data at S band. The MS names the field `PKS0408-658`, which `rang.fluxstd` does not resolve today (checked 2026-11-27: "not in CARACal 2016"); an alias is added after this freeze (section 4) |
| 3C 286 (S0) | xcal (Gpol, KCROSS, Xf) | **`pb2013`**, new, frozen here (below); CASA `setjy` manual with the same numbers | NRAO_XCAL's flat 9.8 % at 1.47 GHz is 0.2-0.7 points below 3C 286 at 1.75-2.62 GHz |
| 3C 138 (S1) | xcal | `nrao` (NRAO_XCAL, flat 7.8 %, −9.6°); CASA `setjy` manual with the same numbers | **parity only**: 3C 138 flared from 2003 and is variable (PB2013 section 5); no model dated near 2023-04-02 is in hand. It sets the frame the parity rows compare in, not a claim about 3C 138 |

**The `pb2013` 3C 286 model (frozen).** Perley, R. A. and Butler, B. J. (2013),
ApJS 206, 16, "Integrated Polarization Properties of 3C48, 3C138, 3C147, and
3C286", arXiv:1302.6662, **Table 3** (VLA, December 2010), read from the arXiv
PDF page 8: 3C 286 p = 9.5, 9.9, 10.1, 10.5, 10.8, 10.9, 11.1 % at 1.450,
1.640, 1.950, 2.450, 2.950, 3.250, 3.750 GHz; χ = 33° at every one of them.
Their χ of 33° from 1 to 8.8 GHz is an **adopted** value (their Table 4: RM 0,
χ₀ 33°), not a per-frequency measurement. The journal version was not opened.

- p: the least-squares quadratic in x = (ν − 1.47 GHz)/1.47 GHz through those
  seven rows, coefficients **(0.096101, 0.016379, −0.004472)**, the CASA
  `polindex` convention (`rang.calmodels.Manual`); largest residual 0.106
  points (their stated accuracy is about 0.1 %). It gives 9.91 % at 1.75 GHz,
  10.62 % at 2.625 GHz and 11.02 % at 3.5 GHz.
- χ: `polangle` (0.575959,) rad (33.0°), `rotmeas` 0.
- I: NRAO_XCAL's 3C 286 I unchanged (14.7172 Jy at 1.47 GHz, spix
  (−0.4507, −0.1798, 0.0357)), so the new model changes only Q and U.
- `reffreq` 1.47 GHz. **Valid 1.45-3.75 GHz**; rang refuses it on channels
  outside that range ("behind the band"). `name` must be 3C286 or an alias.
- Secular change: Table 5 gives +0.77 to +1.0 points per century at 1.5-4.9
  GHz, so by 2025 p is about 0.11-0.15 points above the 2010 table; not
  modelled, and inside the window below.
- CASA arm: `setjy(standard='manual', fluxdensity=[14.7172,0,0,0],
  spix=[-0.4507,-0.1798,0.0357], reffreq='1.47GHz',
  polindex=[0.096101,0.016379,-0.004472], polangle=[0.575959], rotmeas=0)`.

## 4. Configuration (frozen)

Files in [results/sband-gate/](results/sband-gate/):
[s0-dev.yaml](results/sband-gate/s0-dev.yaml),
[s0-dev-3c.yaml](results/sband-gate/s0-dev-3c.yaml),
[s1-dev.yaml](results/sband-gate/s1-dev.yaml),
[s1-dev-3c.yaml](results/sband-gate/s1-dev-3c.yaml), and the CARACal arm's
[caracal-s0-dev.yml](results/sband-gate/caracal-s0-dev.yml),
[caracal-s1-dev.yml](results/sband-gate/caracal-s1-dev.yml).
`rang-core config check` (main 59e590a8, Windows, without an MS): `s1-dev.yaml`
"valid for flag, calibrate, apply, image, selfcal", `s1-dev-3c.yaml` "valid for
image"; `s0-dev.yaml` is refused (`calibrate.polcal.model.source` has no
`pb2013` yet), as expected before the code commit. Every file must pass
against its development MS with the frozen wheel before the run (section 8).

They are E2-N's `e2n.yaml` with these changes only:

| Key | S-band gate | E2-N | Reason |
| --- | --- | --- | --- |
| roles | S0: fcal = bpcal J1939-6342, gcal J1311-2216, xcal J1331+3030, target A3528S. S1: fcal = bpcal PKS0408-658, gcal J0825-5010, xcal 3C138, target NGC2997 | this track's | the blocks' calibrators; Df on fcal (both primaries are unpolarised) |
| J0408-6545 check field | none | corrected like the secondary | no such scan in either half |
| `flag.strategy` | the L-band calibrator first pass `mk_rfi_flagging_calibrator_fields_firstpass.yaml` (CARACal 8f7bb363, SHA-256 `ce9ac66a…1774`, the copy in `results/e2n-scripts/`) | the same | CARACal ships no S-band strategy; its windows are in channels, and the 4k channel width differs from L band's by 2.2 % (scope 1). No static mask: neither Tricolour mask has an entry above 1.7 GHz (scope 2) |
| `calibrate.model` | S0 `setjy` SR2016; S1 `setjy` `CARACal 2016` | `setjy` SR2016 | section 3 |
| `calibrate.polcal.model` | S0 `{source: pb2013, name: 3C286}`; S1 `{source: nrao, name: 3C138}` | `nrao` 3C286 | section 3 |
| `image.size`, `scale` | 6,144², 1″ (1.71°) | 4,096², 3″ | section 5's geometry row |
| `image.average_channels` | 4 (1,024 channels of 854.5 kHz; Δν/ν 4.9e-4 at 1750 MHz) | 2 | below E2-N's 1.3e-3 and UHF's 6.5e-4; the image-stage image is reported; gate 3c and the target rows use the unaveraged `*-3c.yaml` |

Everything else is E2-N's (as UHF 4): `weights: uniform`, `refant: auto`,
`uvrange >150`, `average_time`, `average_freq` and `casa_phase_weights` on,
the full-Stokes chain (K, G, B; Gsec, Asec, F; Gpol, KCROSS, Xf, Df with
`extendflags`), `feed_angle_rotation: −90`, `parang`, Briggs 0.5, 8 joined
channels, 2-term fit, mask 5σ, clean to 3σ, multiscale, two selfcal rounds (Sp,
Sa at solint 120, `average_time`).

**Code after this freeze (a separate commit, with tests; it implements the
numbers above and nothing else):**
1. `rang.calmodels`: the `pb2013` 3C 286 model of section 3, refused outside
   1.45-3.75 GHz; `calibrate.polcal.model.source: pb2013` in the schema. The
   default (`nrao`) and every L-band output are unchanged (tested).
2. `rang.fluxstd.ALIASES`: `PKS0408-658` (and `PKS 0408-658`) → `0408-65`.

**Wheel.** A Linux wheel built on nash by `tools/wheel/build.py` from this
branch after it has merged origin/main containing "Merge predict-par" and the
code commit. Its SHA-256 and commit go in the result. One venv, made fresh.

## 5. Gates and tolerances (frozen)

### 5.1 Development run, per block (carried over from UHF 5 unchanged)

Gate 1, 2a, 2b, 2c, 3a (Tricolour 0.2.1 with the strategy of section 4,
`-fs polarisation -dc DATA -dpm`, native input flags, every field), 3b (CASA
6.7.6.14 on e2n-followup's flag states; K, KCROSS, Xf, Df, Gpol by their
limits; class B composites), 3c (WSClean 3.7 against GeMClean on CORRECTED_1GC,
both unaveraged, same argv: dirty L∞ ≤ 1e-6 of the peak; compact median within
0.5 %, robust scatter ≤ 1 %), the secondary row (J1311-2216 on S0, J0825-5010
on S1: I within 1 %, |Δp| ≤ 0.1 point, |Δχ| ≤ 1° per bin, rang against CASA),
the **polarisation-calibrator parity row** (3C 286 on S0, 3C 138 on S1: p and χ
per bin, sky frame, rang against CASA: |Δp| ≤ 0.1 point, |Δχ| ≤ 0.5°), the
target compact-source row (median within 1 %, robust scatter ≤ 1.5 %), the
target noise and dynamic-range row (rms ≤ 1.2 ×, peak/rms ≥ 0.8 × the oracle's)
and the self-calibration row, each with the tolerance and method of UHF 5. A0
rule 1: none is loosened.

### 5.2 New rows, with their reasons

| Row | Where | Measure | Tolerance | Reason |
| --- | --- | --- | --- | --- |
| Primary model | dev | rang's MODEL_DATA on the primary against an independent float64 evaluation of the same standard (numpy, a point at the phase centre: I per channel on XX and YY, 0 on XY, YX), 2,000 rows at a fixed stride, every channel | per cell ≤ 1e-5 of the peak | UHF 5's model row; the standard's code path is new at S band |
| 3C 286 model (S0) | dev | rang's MODEL_DATA on the 3C 286 scan against CASA `setjy` manual's with section 3's numbers, the same 2,000-row rule | per cell ≤ 1e-5 of the peak | the `pb2013` code is new; CASA's setjy is its oracle |
| Image geometry | dev | 6,144² × 1″ | – | 1″ is below the Nyquist pixel at both tops (1.53″, 1.41″), so no visibility is dropped (gate3c-rerun's finding); 1.71° is 2.9 FWHM at S0's centre, 2.3 at its bottom, 3.2 at S1's centre |
| Field limit of the scorer | dev | inner **0.4°** radius | – | the primary beam sets it: 0.4° is 0.67 (S0) and 0.74 (S1) of the centre FWHM, as L band's 0.7° was 0.69 of 1.01°. Unaveraged bandwidth smearing at 0.4°: β = 1.2e-4 × 1440″ / 3.1″ = 0.06 |
| **Flux transfer** | held out | the development run's K, G, B (primary section) applied to each held-out primary scan's cross rows in memory (rang's library apply, interp linear: one solution, so constant), flags after rang's flag stage with the frozen strategy on the held-out MS; per 100 MHz bin, the median over channels of I / the model of section 3 | within **2 %** in every bin with ≥ 10 % unflagged | A0's E2-A flux-scale row unchanged; the same model on both scans, so model errors cancel and the row measures the transfer over 2.0 h, 4.1 h (S0) and 3.4 h (S1) |
| Flux transfer, rang against CASA | held out | CASA's development K, G, B applied by `applycal` to the same scan and flags; per-bin I, rang against CASA | within **1 %** per bin | the secondary row's 1 % (UHF 5's 0408 row) |
| **Leakage** | held out | the development run's K, B, Kcross, Xf and Df, with a phase-only G solved on the held-out scan itself (E2-B's `leak18p` case), parang on; WSClean 3.7 Q, U, V and I MFS images of that scan, 2,048² × 1″, unit weights; the peak of each of |Q|, |U|, |V| within the inner **0.2°** over the peak of I; both arms | each ≤ **0.3 %**; rang's each ≤ 1.2 × CASA's | A0's L-band 0.3 % (four times the publisher's 0.08 %); scope 3's candidate. Hugo's second-order floor is a UHF result and no S-band leakage floor is published that I found, so L band's number is kept. The 1.2 × is A0 3c's QUV bound (UHF 5). Inner 0.2° is UHF's 0.5° scaled by the beam (0.34 of the centre FWHM). Not circular: Df was solved on another scan, 2-4 h earlier |

The held-out rows are read on every held-out scan (S0: 17 and 35; S1: 43); each
scan must meet each row.

### 5.3 Frequency bins

S0: 1750-1850, ..., 2450-2550 MHz (eight bins; the top 75 MHz is not binned).
S1: 1970-2070, ..., 2670-2770 MHz (eight bins; 1968.75-1970 and the top 74 MHz
are not binned). A bin is scored when ≥ 10 % of its cells are unflagged in both
arms.

### 5.4 Reported, not gated

- **3C 286 against PB2013 (S0).** p and χ per bin from rang's corrected 3C 286
  scan, sky frame, beside the `pb2013` model and PB2013's table, labelled
  "same scan, not a transfer": Xf (and through Gpol in part p) are solved on
  this scan against this model, so the row is circular. Frozen reading words:
  "inside the window" when |p − p_model(ν)| ≤ 0.6 point and |χ − 33°| ≤ 5° in
  every scored bin; "outside" otherwise. 0.6 point is A0's L-band window
  half-width ([9.0, 10.1] around 9.5-9.8) plus the 0.11-0.15 point secular rise;
  5° is a 2 rad m⁻² RM at 1750 MHz (3.4°) plus A0's 1.7° for calibration.
  p_model per bin centre: 9.96, 10.05, 10.14, 10.23, 10.31, 10.39, 10.47,
  10.54 %. A sign error would move χ by about 87°.
- **3C 138 (S1)** p and χ per bin beside PB2013's December 2010 values (9.0 %,
  −10° at 1.95; 10.4 %, −9° at 2.45; 10.7 %, −10° at 2.95 GHz), labelled
  "variable source, 2010 epoch, not a check".
- The **ap own-G leakage** case (E2-B's `leak18ap`) beside the gated phase-only
  case; the flux transfer with the full run's tables, as context.
- **Overlap, cross-block (1968.75-2624.79 MHz).** The blocks observe different
  sources, so the only cross-block reading is the Df amplitude per antenna of
  both development runs in the overlap bins, side by side (an instrumental
  quantity, if stable over two years). Not gated.
- Absolute flux of the secondaries from `fluxscale`; native size of K, KCROSS
  and Xf; the DATA-state probe (section 8); flag fractions after each stage;
  the image-stage (averaged) image against the unaveraged one; E3 (section 6).

## 6. Oracles (A0 rule 8, pinned; on nash under apptainer, as UHF 6)

- **CASA 6.7.6.14** (`rang-o-casa_6.7.6.14.sif`): K, G, B, Gsec, F,
  fluxscale, Gpol, KCROSS, Xf, Df, `setjy` manual for 3C 286 (S0, section 3) and
  3C 138 (S1, NRAO_XCAL's numbers), `applycal`.
- **WSClean 3.7** (the KERN build inside the CASA image, as UHF 6).
- **Tricolour 0.2.1** (`rang-tricolour_0.2.1-e1.sif`) with the L-band
  calibrator first pass.
- **QuartiCal 0.2.7** (`rang-formats-oracle_20261030.sif`), self-calibration.
- **CARACal 8f7bb363, reported only** (sband-scope 3: ours, `flag_spw` and the
  L-band mask off, `meerkat_skymodel` off): `caracal-s{0,1}-dev.yml`, on each
  development MS, read with E3's frozen words ("comparable": every quality
  measure within 20 % and flux within 2 %; speed within a factor of 1.5); no
  pass bar. CARACal's own 3C 286 model is NRAO's flat one (its `nrao_model`),
  and its primary model is its setjy route; both differences are reported. Run
  only when cores allow (the UHF gate has priority); otherwise "not run" with
  the reason.

## 7. The CASA arm

UHF 7 unchanged: E2-N's `e2n_casa3b.py` calls with e2n-followup's flag-state
rule; the primary from rang's MODEL_DATA (section 3); the polarisation
calibrator by `setjy` manual; field names and scans from section 2. For the
held-out rows, E2-B's `e2_casa_xfer.py` route: CASA's development tables
applied to the held-out scans. Scripts are adapted in names and paths only,
and each runs once on development data or A1 before it reads a held-out scan.

## 8. Smoke, order and stop rules

1. **Before anything reads a visibility:** each development MS's map against
   section 2's lists; `rang-core config check` of each file against its MS with
   the frozen wheel (the verdicts of section 4, all four valid); the token
   search.
2. **DATA-state probe** (UHF 8.2), on each development MS's primary and
   polarisation-calibrator scans, channels 2,048-2,079, the first 800 rows;
   reported first; every gate is read as frozen in either state.
3. **Dry run:** the adapted chain on A1 small (UHF 8.3's route); its scores
   are not read. A failure is fixed and recorded before S0 runs.
4. **Order:** S0 development run and its post chain; S0's development rows
   recorded; then S0's held-out MS is made and its transfer rows are read
   **once**; then S1 the same way. A miss on a development row allows one fix
   by a dated amendment, rerun on that development MS, before that block's
   held-out rows are read; a row met only after a fix is labelled so.
5. **Disk:** every MS write inside `e2_diskguard.py` with a 2,000 GiB floor on
   nash's /home. **Cores:** the UHF gate (#11) has priority. Every S-band job
   runs under `nice -n 19 ionice -c3`, pinned with `taskset -c` to a core set
   the coordinator approved, with `RAYON_NUM_THREADS` and `OMP_NUM_THREADS` at
   that set's size, and is paused or stopped at a clean point when the UHF gate
   needs the cores. Wall times on a shared host are indicative and go to
   [tool-timings.md](tool-timings.md).

## 9. Decision rule (what each outcome means for v0.5.0)

Each gated row of section 5 is read met, not met, or not checked (an oracle or
step that cannot run, with the reason; never read as met). Nothing is retuned
against a held-out scan; a fix found on a held-out row is tested on the
reserve or labelled "seen".

| Outcome | When | v0.5.0 |
| --- | --- | --- |
| **A: in, supported (S0 and S1 sub-bands)** | on both blocks every gated row of 5.1 and 5.2 is met, development rows at their first read | release notes: "S band validated for 1750-2844 MHz (sub-bands S0 and S1)"; S2-S4 named as untested; the band warning's wording for S0/S1 is the coordinator's decision |
| **B: in, as a known limitation** | gate 1, 2a and 2b met on every block that ran, and any of: a row not met, a row met only after a fix, a row not checked, or only one block measured by release time | release notes: "S band runs; not validated", the misses by row and block (as E2-N's wording); the band warning stays |
| **C: out** | gate 1, 2a or 2b not met on a block that ran, or no block measured by release time | S band not claimed in v0.5.0; the band warning stays; #18 stays open with the reason |

The S-band gate is not on v0.5.0's critical path (the UHF gate is): the
release does not wait for it, and its outcome on the day is read by this table.

## 10. Not checked before the freeze

- The DATA state of either block (native, unphased or observatory-phased).
- Site RFI at 1.75-2.85 GHz and how much the L-band first pass flags there
  (reported through flag fractions).
- Whether a point 1934-638 or 0408-65 biases B at S band (both arms share it).
- How long a full chain takes on 212 GB (S0) with the cores left by the UHF
  gate; the setjy point predict is cheap (no 7,779-component model).
- Whether CARACal's cabs run its setjy route for 0408-65 at S band.
- katbeam or holography beams: nothing in the chain applies a primary beam.

## Run log (records only; the protocol above is unchanged)

**2026-11-27, development MSs made (section 2), nothing read.** Frozen at
`d9a275b8`, code `a5d49085`, branch pushed with `tools/check_all.py --quick`
PASS and CI green; origin/main with "Merge predict-par" merged at `6c4ee849`
(quick check PASS, pushed). On nash, `scripts/sg_convert.sh` (heavy lock 2
slots, 12 GB, nice 19 / ionice idle) into
`~/rang-data/outputs/sband-gate-20261127/<block>/dev/`; receipts in
[results/sband-gate/](results/sband-gate/) (`ms-map.json`,
`flaghash-input.json`, the scan list, bytes). The token search found nothing.

| Block | katdal scans | MS scans (field, dumps) | Rows | Bytes | FLAG / FLAG_ROW SHA-256 (gate 2a) |
| --- | --- | --- | ---: | ---: | --- |
| S0 1747682474 | 1,3,5,7,9,11,13 | 1 J1939-6342 (74), 2 J1331+3030 (74), 3 J1311-2216 (15), 4 A3528S (224), 5 J1311-2216 (14), 6 A3528S (224), 7 J1311-2216 (14) | 1,056,267 | 212,146,857,001 | `7ec2b54c…` / `583ef237…` |
| S1 1680455600 | 1,3,5,9,11,15,17 | 1 3C138 (39), 2 PKS0408-658 (37), 3 J0825-5010 (18), 4 NGC2997 (101), 5 J0825-5010 (18), 6 NGC2997 (101), 7 J0825-5010 (19) | 531,468 | 106,747,821,621 | `20997ab6…` / `fc75fac9…` |

Both maps match section 2's lists. The full chain waits for cores: the UHF
gate (#11, the release's critical path) holds nash. The coordinator's
answer, 2026-11-27: start only after the UHF D CARACal arm has finished,
on 4-8 cores from 20-35 that the coordinator approves.

## For the coordinator

- Frozen: this note and `results/sband-gate/` (four rang files, two CARACal
  files). Code follows in its own commit: the `pb2013` 3C 286 model and the
  `PKS0408-658` alias.
- New numbers: leakage 0.3 % (held out, each primary scan), flux transfer 2 %
  against the model and 1 % against CASA, the two model rows 1e-5, geometry
  6,144 × 1″, field limit 0.4°, leakage region 0.2°, 3C 286 window ±0.6
  point and ±5° (reported).
- Open: core sets on nash for the runs (the UHF gate first); whether a second
  block per sub-band is asked for later, for a cross-block held-out set.
