# E2 helper: `calibrate.average_time`, CASA's time pre-averaging in the chain solves

Part of task E2 ([finish-plan.md](finish-plan.md)). Branch `fp-e2-averaging` from `fp-e2-acceptance` `f11fdd1`.
Interface and estimator work for real 4096-channel MeerKAT scans; no novelty claimed.

**Status:** implemented and measured (2026-11-11). A1: on equals off to float32. LUNO against CASA: class B met on K, KCROSS, Xf, Df and the fcal composite, **not met on Gpol** (0.25° against 0.1°; not the averaging, section 4.2).

## 0. Problem (metadata only)

`rang-core config check` refuses E2's chain on the metadata-only preflight MSs
(`D:\rang\outputs\e2-20261110-10-preflight\e2a-meta.ms`, `e2b-meta.ms`; cubes zero, never read) at
`data.memory_limit_gb: 8`, because W3b solves one solution interval whole (research/w3b-chainchunks.md 6):
e2b (LUNO, 56 antennas, 8 s) K and G `inf` 176.0 GiB, KCROSS `inf` 173.7, Gpol `60s` 19.4, Gsec and F 26.4;
e2a (ESO137, 61 antennas) K0/G0 `inf` 144.8, K1/G1 `60s` 23.0.

## 1. What is implemented

Configuration key `calibrate.average_time` (bool, default false). With it on, every K, G, B, F, Gpol, KCROSS,
Xf and Df solve is on its data and model **averaged in time within each solution interval**, CASA's
estimator (its solvers average the VisBuffers of a solution interval before solving):

- `rang.cal_chunks.Average`: one averaged row per (interval, ANTENNA1, ANTENNA2) of the field's
  cross-correlation rows, ordered by (interval, ANTENNA1, ANTENNA2). Source rows with FLAG_ROW, outside
  `uvrange`, or autocorrelations contribute nothing (uvrange is applied per source row, so a baseline crossing
  the limit within an interval keeps only its rows inside it); an averaged row with no contributing row is
  flagged as a row.
- `rang.cal_chunks.load_averaged`: the source rows of a chunk of averaged rows are read in blocks of whole
  rows, each block passed through the solve's existing `prepare` (the pre-applied tables with their
  interpolation, per row; for KCROSS, Xf, Df and Gpol the model rotated by P per row, `parang: true`),
  then cut to the chunk's channels and accumulated in float64 per (averaged row, channel, correlation):
  `sum(w d)`, `sum(w m)`, `sum(w)` over unflagged cells. Data and model become the weighted means (complex64),
  the weight `sum(w)`; a cell with `sum(w) = 0` (no unflagged sample of positive weight) is flagged, data and
  model 0. Weights are `prepare`'s: `1/SIGMA^2` when tables are pre-applied, else `data.weights`.
  P rotates the model, not the data, in every rang term (`cal_pol.prepare`, `gpol`), so the model is
  rotated before it is averaged and the data/model ratio does not decorrelate.
- The solution times and scans are those of the unaveraged rows (each source row's weight sum, as now), so
  every table's TIME and INTERVAL are unchanged by the key. CASA's averaged-row time (the weighted mean) is
  then not needed by any kernel.
- The memory plan uses the averaged size: `cal_chunks.plan(..., average=...)` plans chunks of averaged rows
  (one interval of averaged rows is the smallest unit: baselines x channels x 4, or one channel of it for B,
  Xf, Df), the budget half for the chunk and half for a read block of source rows, of which
  `AVERAGE_BLOCK_SHARE` (0.5) in rows (the rest for the accumulation's temporaries). `preflight`
  (`chain_chunk_plans`) and the calibrate summary's `chunking` use the same plan. The replayed stop test of
  W3b runs unchanged over chunks of averaged rows (each pass re-reads and re-averages its chunk; a
  polarisation field of one chunk is averaged once).
- Solvers and kernels are unchanged (no Rust change; `solve.rs`, `jones.rs`, `correct.rs`,
  `core.solve_complex` untouched). The A step is unchanged.
- Off (the default) runs the code path of `f11fdd1`: the key enters no call (`average_time` keywords are
  passed only when true), and `core_config.stage_hash` leaves `calibrate.average_time` out at its default
  (`HASH_DEFAULTS`), so existing configurations keep their stage hashes.
- `calibrate.average_time: true` with a `complex` term is refused (`complex` has no pre-averaging).

Files: `python/rang/cal_chunks.py` (`Average`, `load_averaged`, `plan(average=)`), `cal_gain.py`
(`_Field.averaged`, `_solve_gain_field(average=)`, `gaincal(average_time=)`), `cal_delay.py`, `cal_bandpass.py`,
`cal_pol.py` (`_PolField.chunks(average=)`, `chunk_loaded`, `_chunked`, `kcross`, `xf`, `df`), `cal_chain.py`
(`run(average_time=)`, `_solve_pol`), `core_config.py` (key, `HASH_DEFAULTS`, refusal), `core_pipeline.py`;
`docs/cli.md` regenerated; `tests/test_e2_average_time.py`.

Semantics stated, not CASA-verified: averaging is per correlation, while the kernels flag a whole cell when
any correlation is flagged; Df's `min_data_fraction` and its gauge test see the averaged cells.

## 2. Protocol (written before the first comparison)

Development data only. Outputs `D:\rang\outputs\e2-20261110-11-avg` (`.code/` snapshot). Scripts in
[results/e2-average-time/](results/e2-average-time/).

1. **Averaged against unaveraged, A1 small** (`fp-a1-20261106-simtruth/small/a1-small.ms`), C2e's I-a1 chain
   (calibrate only; `e2avg_a1.py`): K, G, B, Gsec, F tables and the fcal (K G B) and gcal (K F B) composites
   of the key on against off. Reported, not gated (the estimator changes by design); class B's numbers are
   given for scale.
2. **LUNO development scans 1 and 2** (`D:\rang\data\e2-d\LBAND_LUNO_CALIBRATORS.zarr`, MAIN_0 = 3C286 scan 1,
   MAIN_1 = PKS 1934-638 scan 2), built with `e2_convert.py build` and `verify`. Readability before CASA:
   CASA `listobs` exits 0, python-casacore opens every table, and two DATA chunks decoded independently with
   numcodecs equal the MS bytes. rang: `rang-core run`, calibrate only, e2b-like, restricted to the two
   fields: K, G (`inf`), B (`inf`, combine scan) on J1939-6342; Gpol (`60s`, p, parang), KCROSS (`inf`), Xf
   (`inf`, combine scan) on J1331+3030; Df (`inf`, combine scan, clip 0.6) on J1939-6342; no secondary, no
   `extendflags` (neither arm), no flag stage (both arms see the converted MS's flags);
   `feed_angle_rotation: -90`, `refant: auto`, `uvrange: >150`, `data.weights: uniform`,
   `calibrate.average_time: true`, `data.memory_limit_gb: 8`. Peak memory and wall recorded.
   CASA 6.7.6.14 (`rang-o-casa`) on a copy of the same converted MS with FEED RECEPTOR_ANGLE set to -90 deg
   on both receptors (CARACal's `set_receptor_angle`), the same refant list (rang's resolved auto), CARACal's
   calls: setjy SR2016 (1934) and the NRAO manual 3C286 model, gaincal K, G, bandpass, gaincal Gpol (p, 60s,
   parang), KCROSS, polcal Xf and Df (combine scan), Df clip 0.6.
   **Gates, A0 class B** (research/a0-acceptance.md 6.2): fcal composite K G B relative difference median
   <= 7e-4, p95 <= 3e-3; K |dtau| median <= 0.01 ns, p95 <= 0.03; KCROSS <= 0.02 ns; Gpol phase median <= 0.1
   deg; Xf median <= 0.5 deg, p95 <= 2 deg; Df gauge-free (differences of leakages between antennas, d_p - d_q
   of matched channels) median <= 1e-3, p95 <= 5e-3.
3. **Self-calibration** (`rang-core selfcal`, Sp/Sa solint 120 integrations, 4096 channels, ESO137 target scan
   of 850,950 rows, 61 antennas): what the current planner needs, from code and `e2a-meta.ms` only (the e2-a
   visibilities are held out and not read).

## 3. Tests

`tests/test_e2_average_time.py`: off equals the call without the key (tables byte-identical); the stage hash
is unchanged at the default and changes when true; the key is refused with a complex term; `Average`'s rows
and sources; G and K (solint inf, int, 30 s; a pre-applied K; `uvrange`), B (channel chunks) and F, Gpol,
KCROSS, Xf and Df (degenerate and not) equal a NumPy group-by reference fed to the unchanged solvers, chunked
and not; solint int averages to itself; the plan uses the averaged size; e2a and e2b pass the 8 GiB preflight
with the key and are refused without (skipped where the preflight MSs are absent).

## 4. Results

Code: the worktree diff on `f11fdd1` (`.code/worktree.diff` in the run directory). The A1 run and the
development dry runs used an extension copied from `fp-e2-acceptance` (built from the same Rust, which this
branch does not change); the LUNO run and check-all used this worktree's own `maturin develop --release`.

### 4.1 A1 small, key on against off (`a1.json`)

C2e's I-a1 chain, calibrate only, both exit 0 (3.7 / 3.3 s). Flags identical in every table and composite.

| Compared | Median | p95 | Max |
| --- | ---: | ---: | ---: |
| K \|dtau\| (ns) | 6.0e-7 | 3.2e-6 | 4.8e-6 |
| G relative | 5.6e-8 | 4.7e-7 | 6.4e-7 |
| B relative | 5.3e-7 | 4.7e-6 | 1.3e-5 |
| Gsec (60 s) relative | 3.6e-8 | 4.8e-7 | 7.8e-7 |
| F relative | 4.7e-8 | 4.9e-7 | 8.1e-7 |
| fcal composite K G B | 6.4e-8 | 1.7e-7 | 3.8e-7 |
| gcal composite K F B | 9.0e-8 | 2.5e-7 | 6.5e-7 |

fluxscale SIM-GCAL 4.2946896884 Jy off, 4.2946897145 Jy on. On A1 (gains constant within each scan, a point
model) the averaged estimator is the unaveraged one to float32 rounding, as expected.

A development dry run on the LUNO slice (first 15,960 rows of each scan, channels 0-255, mostly flagged band
edge; `dry/`, `dry-off/`) found rang's differences from CASA the same with and without the key (K median
0.1747 / 0.1752 ns, fcal composite median 0.0201 / 0.0201, Xf 0.015 / 0.021 deg, Df gauge-free 5.0e-5 both):
on that slice the averaging is not what separates rang from CASA. That slice is not the protocol's case and is
not gated.

### 4.2 LUNO development scans 1 and 2 (`luno-score.json`, 2026-11-11)

Build 133 s and `verify` 130 s: 3,870,031,872 cells of DATA, WEIGHT_SPECTRUM and
FLAG, 0 differ, every row column equal. Readability: CASA `listobs` exit 0,
python-casacore exit 0, the numcodecs chunks equal the MS (`luno-readable.stdout`).
rang `rang-core run` (calibrate only, `average_time: true`, 8 GiB): rc 0, 1,807 s
wall, 2,178 s CPU, peak RSS 2.87 GB (`luno/rang-run.json`). CASA 6.7.6.14: 11
calls, no error, 2,357 s (third attempt, started 2026-11-11 12:33 from call 0 on
the same copy; every table was rewritten, `casa/` timestamps 12:44-13:12).
refant m022, m023, m024 in both (rang's `auto`).

| Term (gate, class B) | median | p95 | max | Gate |
| --- | ---: | ---: | ---: | --- |
| K \|Δτ\| (≤ 0.01, ≤ 0.03 ns) | 0.0032 ns | 0.0093 | 0.012 | **met** |
| KCROSS \|Δτ\| (≤ 0.02 ns) | 0.00086 ns (rang −0.00742, CASA −0.00656) | – | 0.00086 | **met** |
| Gpol phase (median ≤ 0.1°) | **0.250°** | 2.03° | 3.19° | **not met** |
| Xf, first unflagged channel phase (≤ 0.5°, ≤ 2°) | 0.064° | 0.60° | 6.7° | **met** |
| Df gauge-free \|d_p + d_q* difference\| (≤ 1e-3, ≤ 5e-3) | 2.7e-5 | 2.2e-4 | 0.017 | **met** (flags 172,212 / 177,682) |
| fcal composite K G B relative (≤ 7e-4, ≤ 3e-3) | 4.5e-5 | 2.2e-3 | 0.052 | **met**, 0 flags differ |
| G (reported) relative; phase | 4.3e-4; 0.025° | 1.8e-3; 0.11° | 2.5e-3; 0.14° | – |
| B (reported) relative; phase | 2.6e-3; 0.15° | 0.015; 0.83° | 0.053; 3.0° | – (K, G and B trade a gauge; their product is gated) |

**Verdict as frozen: class B not met, on Gpol alone.** Every other gated term
is met.

**Where Gpol's difference comes from (post hoc, labelled; scripts
`e2avg_gpol_gauge.py`, `e2avg_gpol_ones.py`, `e2avg_gpol_freqavg.py`, outputs
`luno-gpol-*.json`):**
- Not the refant gauge: with each interval's median over antennas removed the
  difference is 0.221° (p95 2.14°); both tables reference m022.
- Per antenna, it is nearly constant over the 10 intervals and equal in both
  hands, and it grows with distance from the array centre. It is largest on
  the outer antennas (m049, m055-m059, m062, m063: 1.0-3.0°, 1.2-4.1 km
  out); below 0.25° on the core.
- Not the averaging: on the development dry slice (channels 0-255) Gpol
  agrees with CASA to 0.017° with the key on and off alike (4.1).
- Not the weights: CASA's Gpol after `initweights(wtmode='ones')` equals its
  own to 1.4e-4° (p95). LUNO's SIGMA is 1, so rang solves with unit weights;
  WEIGHT_SPECTRUM varies 2-4 % over channels on scan 1.
- Not the model: MODEL_DATA is bit-equal between the arms (a point at the
  phase centre; PHASE_DIR = DELAY_DIR = REFERENCE_DIR).
- **Partly CASA's frequency pre-averaging.** CASA's G-type solves average the
  window's channels before solving; rang's kernel takes each channel as a
  sample of one frequency bin. `cal_pol.gpol` rerun as the chain called it
  reproduces the frozen table (max 1.5e-6°). With the kernel's input first
  averaged over channels (weighted, per row and correlation) it differs from
  CASA by a median of **0.108°** (p95 0.94°, max 1.42°), from 0.250°
  (p95 2.03°). The two estimators agree for an unresolved source. On
  3C 286's long baselines, where the source is partly resolved and the model
  is a point, they weight the band differently. The remaining 0.1° is not
  traced. This is an emulation in a script; rang's G solve is unchanged.

Consequence for E2: E2-B's gate 3b compares Gpol at class B. As the code
stands it is expected to miss there for the same reason. K, G and B on
1934−638 (E2-A's terms, unresolved) are met here.

### 4.4 `selfcal.average_time` (added 2026-11-11)

`selfcal.average_time` (bool, default false, out of the stage hash at its
default) passes `average=True` to Sp and Sa's `_solve_gain_field`; refused
with Sd. Test: `test_selfcal_average_time_gives_the_gains_back` (noiseless
perfect model, averaged equals unaveraged within 1e-5). Uncommitted, with the
rest of this branch, until check-all runs.

### 4.3 Self-calibration under the current planner (`selfcal-plan.json`, metadata only)

`rang-core selfcal` solves through `cal_gain._solve_gain_field` with `budget.chain()`, one solution interval
whole, and has **no preflight**: a refusal comes at the solve, after round 1's image. On `e2a-meta.ms`'s
target (ESO137-001, scan 10, 850,950 rows, 450 integrations, 61 antennas, 1,891 rows per integration with the
autocorrelations), `Sp` and `Sa` at solint 120 integrations give 4 intervals of up to 226,920 rows:

| Channels | Every row (current) | Time-averaged (1,830 rows per interval) |
| --- | --- | --- |
| 4096 | 3.72e9 cells, **333.3 GiB**: refused at 8 GiB | fits, 4 chunks (one interval each) |
| 512 (CARACal's 8x split) | 4.65e8 cells, **42.4 GiB**: refused | fits, 1 chunk |

The largest solint that fits 8 GiB unaveraged is 2 integrations at 4096 channels and 20 at 512. So the 8x
channel average CARACal self-calibrates on is necessary but not sufficient: solint 120 needs a 42 GiB host
or time pre-averaging. Time pre-averaging is not CubiCal's estimator (CubiCal solves every sample of the
interval) and is not wired into selfcal here (`average_time` reaches the chain solves only). With gains
constant over the interval `mean(w d) = g mean(w m) g^H` exactly, so the averaged solve is consistent; it
differs from CubiCal's where the gains vary within the interval and through the noise weighting, and on a
field model the averaged model decorrelates (the visibilities rotate over 120 x 8 s), lowering the averaged
rows' signal. Whether selfcal should take `average_time`, a smaller solint, or channel averaging plus a larger
limit is an owner decision (section 6).
