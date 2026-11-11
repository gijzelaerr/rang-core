## 5. E2 protocol — DRAFT, NOT FROZEN (2026-11-11; to be finalised and committed into e2-acceptance.md before any E2 cube is decoded)

Written after E1b's chain runs and before any E2-A or E2-B cube cell was
decoded. Everything read of the E2 groups so far: the fetched bytes (not
decoded), row columns, subtables and group attributes (A0 section 4 allows
these), through the metadata-only preflight MSs of 5.1.

### 5.1 What the metadata preflight found, and the fix (before the protocol)

`e2_convert.py build --no-cubes` writes the row columns and subtables of the
E2 groups with DATA, FLAG and WEIGHT_SPECTRUM left at zero and never read
(`D:\rang\outputs\e2-20261110-10-preflight\e2a-meta.ms`, `e2b-meta.ms`).
`rang-core config check` on them refused the CARACal chains at the default
`data.memory_limit_gb: 8`: W3b solves one solution interval whole, and at
4,096 channels K and G `inf` need 145-176 GiB, KCROSS `inf` 174 GiB, Gpol
`60s` 19 GiB, Gsec and F 26 GiB, K1 and G1 `60s` 23 GiB (the host has 30 GB).
`rang-core selfcal` has no preflight; its Sp and Sa at solint 120 on the
E2-A target would need 333 GiB per interval at 4,096 channels and 42 GiB at
512 ([e2-average-time.md](e2-average-time.md) 4.3). **As frozen in A0, both
legs would have failed gate 1 with a refusal; that was found from metadata
only, so the fix below is pre-registration, not post hoc.**

The fix is CASA's own estimator ([e2-average-time.md](e2-average-time.md),
branch `fp-e2-averaging`, merged here before this protocol):
`calibrate.average_time` and `selfcal.average_time` (default false; off is
byte-identical to before, stage hashes unchanged): every K, G, B, F, Gpol,
KCROSS, Xf, Df solve, and selfcal's Sp and Sa, on data and model averaged in
time within each solution interval after the pre-applies and P. Its
validation on development data (A1 small; LUNO scans 1 and 2 against CASA
6.7.6.14 at class B) is in that note. Self-calibration with it is not
CubiCal's estimator (which solves every sample); that is an owner decision
(section 9).

### 5.2 The Measurement Sets (exact paths; built after this commit)

| Leg | Built by | Groups, in time order | MS |
| --- | --- | --- | --- |
| E2-B | `e2_convert.py build` then `verify` | LUNO MAIN_16 (scan 17, J1331+3030), MAIN_17 (18, J1939-6342), MAIN_18, MAIN_19 (19, 20, J1833-2103) of `D:\rang\data\e2-b\LBAND_LUNO_CALIBRATORS.zarr`: 272,916 rows, 56 antennas, 4,096 channels | `D:\rang\data\e2-b\e2b.ms` |
| E2-A | the same | ESO137 `ms1_primary.zarr` MAIN_4 (scan 9), `ms1_target.zarr` MAIN_4 (scan 10, ESO137-001), `ms1_primary.zarr` MAIN_5 (scan 11) under `D:\rang\data\e2-a\ESO137`: 1,047,614 rows, 61 antennas, 4,096 channels | `D:\rang\data\e2-a\e2a.ms` |

- `verify` must report 0 differing cells and row-column values (it prints
  counts only); otherwise the leg stops and the converter is fixed (not a
  gate). Right after `verify`, the SHA-256 of FLAG and FLAG_ROW is recorded
  (gate 2a's reference).
- Conversion deviations, fixed now: FEED's single row is expanded to one per
  antenna; POINTING, HISTORY, FLAG_CMD, SOURCE are not written; FIELD and
  STATE are merged over the two ESO137 stores. RECEPTOR_ANGLE stays as
  stored (LUNO 0, ESO137 −90°); E2-B's rang arm rotates it in memory
  (`feed_angle_rotation: -90`), and every CASA or CARACal copy of `e2b.ms`
  gets RECEPTOR_ANGLE −90° written, as CARACal's `set_receptor_angle` does.
- Each leg's rang arm runs on this MS itself (gate 1: `rang-core run config.yaml
  my.ms`). Oracle arms run afterwards on the same file after FLAG is restored
  from `rang_original` and rang's added columns are dropped, or on a fresh
  build from the zarr (A0 amendment 1 item 3: one copy at a time).

### 5.3 The configurations (frozen)

[results/e2-acceptance-scripts/e2a.yaml](results/e2-acceptance-scripts/e2a.yaml)
and [e2b.yaml](results/e2-acceptance-scripts/e2b.yaml), as committed with
this section, with the strategy file
`mk_rfi_flagging_calibrator_fields_firstpass.yaml` (CARACal `8f7bb363`) beside
them. Beyond their header comments:

- `calibrate.average_time: true` in both, `selfcal.average_time: true` in
  E2-A (5.1); `data.memory_limit_gb` the default 8.
- A0 amendment 1 item 3, decided now on G2's measured number: GeMClean's
  peak on the pilot at 512 channels is 19.72 GB, below 24 GB, so E2-A images
  at 512 channels (`average_channels: 8`) and the scorer keeps the inner 0.7°.
- refant: `auto` in both; on the preflight MSs it resolves to m022, m023, m024
  on both legs (it reads ANTENNA and OBSERVATION only).
- E2-B images: no automatic mask (rang refuses one on joined IQUV images);
  the oracle arm does the same.

### 5.4 The run (gate 1) and its cost

- **Wheel:** `maturin build --release` at this branch's head (the commit that
  carries this section), installed with `uv pip install` into a fresh venv
  `~/Build/tmp/20261111-e2-wheel` (Python 3.14, plus psutil for the timer);
  its SHA-256 goes in the result. `rang-core run CONFIG MS` from that venv,
  the strategy file beside the configuration.
- **Timing method:** `e2_timed.py` around the one command: wall time end to
  end, peak resident set summed over the process tree sampled every second,
  host CPU load before and during; per stage the receipt's own times. Under
  `tools/heavy_lock.py` (no other heavy job on the host); the load at start
  is recorded. Peak disk: `du` of the MS and its run directory after the run.
- One shot per leg (A0 rule 2).

### 5.5 Gates and how each is computed

A0's gates are copied verbatim in appendix A (A0 sections 5, 6.1 rows 1-3,
6.2, 6.3's E2-A and E2-B, 6.5, 6.6). How each is computed here:

| Gate | E2-B | E2-A |
| --- | --- | --- |
| 1 | exit 0, every stage of `run.stages` in the receipt, no hand step | the same |
| 2a | FLAG and FLAG_ROW restored from `rang_original` equal the hashes of 5.2 | the same |
| 2b | python-casacore (`rang-formats-oracle`) opens every table and column; CASA `listobs`, `flagmanager(mode='list')`, and `applycal` with rang's tables on a copy against rang's CORRECTED_DATA (class C); WSClean `-niter 0` on CORRECTED_DATA and MODEL_DATA; QuartiCal reads the MS through dask-ms | the same, on E2-A's tables |
| 2c | astropy WCS parses every FITS rang wrote | the same |
| 3a | Tricolour 0.2.1 (`rang-tricolour:0.2.1-e1`), the same strategy, `-fs polarisation`, `-dc DATA`, input flags as converted, on the restored MS; cells against rang's flag stage | the same, with rang's `flag.fields` (fcal and target) |
| 3b | CASA 6.7.6.14 runs CARACal's full-Stokes sequence (as `e1b_casa.py`, with `average_time` not applicable: CASA pre-averages itself) on a copy with rang's FLAG after its calibrate stage, the same refant list and models; per term class B / the term limits on gauge-free composites (K, KCROSS, Xf, Df with the refant as in A0 rule 5) | CASA K, G, B by CARACal's KGBAKGB on the primaries, rang's flags after calibrate, same refant |
| 3c | WSClean 3.7 dirty and cleaned images of rang's CORRECTED_DATA with matched settings (2048 × 2″, robust 0, 8 joined channels, IQUV joined, no mask, 3σ); dirty L∞ / peak; cleaned through the scorer | WSClean of rang's CORRECTED_DATA at the image stage's settings (multiscale, auto-mask 5, threshold 3, 512 channels); dirty L∞; compact-source ratios through the scorer (inner 0.7°) |
| E2-B rows | 3C 286 parity: p and χ per 100 MHz (1.0-1.65 GHz, ≥ 10 % unflagged) in the visibility domain (mean over unflagged cells of the calibrated cross hands after derotation to the sky frame) from rang's and CASA's calibrated scan 17. Transfer: the development half's tables, solved by the same configuration's calibrate on LUNO scans 1 and 2 (`D:\rang\data\e2-d`, converted the same way) with Gpol (p, 60 s, parang) solved on scan 17, applied to scan 17 (rang library apply), p and χ at 1.3-1.5 GHz; both arms (CASA likewise). 1934−638 leakage: development Df applied to scan 18; peak of the Q, U, V MFS images over I. 1830−211: I, p, χ against CASA after the full chain | – |
| E2-A rows | – | Flux scale: K, G, B solved on scan 9 only (same configuration, `data.scans: [9]` for calibrate), applied to scan 11, 1934−638's Stokes I per 100 MHz against SR2016. Target: ≥ 10σ isolated sources in rang's and the oracle's image-stage images (CASA-corrected data, WSClean): ratio, robust scatter; off-source rms and dynamic range. Self-calibration: off-source rms of selfcal's image 1 (from CORRECTED_1GC) and of its final image (after ≤ 1.02 × before); gains class B against QuartiCal 0.2.7 on the same MODEL_DATA and solint, unaveraged (stated) |

Images go through E1b's scorer convention (2.3) where a truth is not
available: compact sources are fitted with a Gaussian fixed to each image's
PSF-fitted beam, matched between arms by position (within 0.5 beam).

**Anything not run is reported as "not checked", never as met.** Where an
oracle cannot run on this host (memory, disk), the reason is recorded.

### 5.6 Failure rules (A0 6.5, verbatim in appendix A)

E2-A failure: recorded as frozen; after a fix, one rerun on the reserve
(scans 12, 11, 13), which needs the owner-approved reserve fetch (164 GB):
fetched only then, and the reason recorded. E2-B failure: recorded; a rerun
after a fix is labelled "seen". Nothing here is retuned against E2 data and
presented as a pass.
