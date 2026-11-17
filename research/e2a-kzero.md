# E2-A with `calibrate.k_zero_start`: a development reading

Status 2026-11-17: **protocol frozen** (sections 1-7) before any rang run
of this note. Results are added below it; anything decided after a result
is read is dated and labelled post hoc. Follows the coordinator decisions
of [calchain-floor.md](calchain-floor.md) (2026-11-17): E2-A, now
development data, is measured with the key on before its default is
decided; E2-N follows. No reading here changes E2-A's frozen verdict
(e2-acceptance.md 9.13, 9.14: not passed). The reserve (scans 12, 11, 13)
is not fetched, read or touched.

## 1. Question

`calibrate.k_zero_start` (default off) runs each K solve a second time from
zero delays and keeps, per solution interval, the run with the lower
weighted residual. On E2-A's archived run one K1 solution is wrong in both
tools: ID 50 (m053), K1 interval 7, 2,335.1 / 2,291.4 ns (X / Y) in rang
and 2,365.3 / 2,380.8 ns in CASA, against 0.11 / 0.09 ns in its other
intervals (calchain-floor 13). On e2a-3b-k's real subset the key moves it to
0.121 / 0.094 ns and nothing else by more than 1e-3 ns (calchain-floor 15).
Does the key, run end to end on E2-A, fix that outlier without a
regression elsewhere, alone and together with
`calibrate.bandpass_model_divided` (opt-in, e2a-3b-diag)?

## 2. Arms

| Arm | Configuration | Stages | Where |
| --- | --- | --- | --- |
| **B**, baseline | `e2a-rerun.yaml` as archived | the whole chain | E2-A's run, Windows, frozen wheel (2026-11-11), `D:\rang\outputs\e2a-20261115`; tables also in `~/rang-data/outputs/e2a-3b-k-20261117/f0win/rang-run/calibrate` on nash; readings 9.13, e2a-3b-k step F |
| **OFF**, key-off control | `e2a-kzero-off.yaml`: `e2a-rerun.yaml`, `run.stages: [flag, calibrate]` | flag, calibrate | nash, this build |
| **ZS** | `e2a-kzero-zs.yaml`: `e2a-rerun.yaml` + `calibrate.k_zero_start: true` | the whole chain | nash, this build |
| **ZSD** | `e2a-kzero-zsd.yaml`: ZS + `calibrate.bandpass_model_divided: true` | the whole chain | nash, this build |

The configurations are in `results/e2a-kzero/`; each differs from
`e2a-rerun.yaml` only in its header and the lines named (checked by
`diff`). OFF exists because B ran on another host with another build:
e2a-3b-k measured rang U on nash against Windows' T-T at p95 1.0e-2 on the
subset (A0's flags differ), so differences from B alone cannot be given to
the key. OFF runs flag and calibrate only (cost), so the gate rows below
have B as their only baseline.

**Build.** Nash worktree `~/Worktrees/rang/e2a-kzero`, its own venv
`.venv` (Python 3.14.10) with the wheel
`dist/rang_core-0.2.0-cp310-abi3-manylinux_2_35_x86_64.whl`, sha256
`35d14f2413a18cf08b8b47cc4d1440a4082978475057f1874000ba5ec9eb222e`,
built by `maturin build --release` (398 s, 4 slots) from `b44cbfa2`
(main; the key merged at `37d8d43`). This note's commit changes only
`research/`, so the wheel is the code of every commit of this branch. The
venv's packages are in `results/e2a-kzero/receipts/freeze-nash.txt`.
Nash's main checkout is used only for `tools/heavy_lock.py`.

**Data.** Three copies of `~/rang-data/e3-input/e2a.ms` (read only; 194
GiB, the E3 agent's build, flag hash `1aec438d…` equal to 9.1) into
`~/rang-data/outputs/e2a-kzero-20261117/{zs,zsd,off}/e2a.ms`, made before
21:30 SAST. Control C-copy: each copy's FLAG and FLAG_ROW hashes equal
`flaghash-input.json`'s (`1aec438d…`, `b528098a…`) before its run; a copy
that fails is not run.

## 3. Measures

**M1, gate 3b's composite against CASA** (KGB1 = the arm's K1 G1 B1
applied, `J_p J_q*`, every 8th time, pooled field map:
`e2avg_common.composite` through `k_score.Comp`, unchanged), on E2-A's
field-0 rows (`f0.ms`, e2a-3b-k step F: all 61 antennas, scans 9 and 11).
CASA 6.7.6.14 (`rang-o-casa_6.7.6.14.sif`, apptainer) runs step F's two
constructions, `k_run.f0casa` unchanged, on a copy of `f0.ms` per arm with
**that arm's own** flags:
- **own K** (`tf`): CASA's full K G B, A-less, K G B; pass 0 on the arm's
  flag-stage FLAG, pass 1 on its FLAG after A0;
- **rang's K** (`k`, T-K3's construction): CASA's G0 B0 G1 B1 on the arm's
  K0 and K1, the same flags.
Read: median and p95 of KGB1 against each, with and without ID 50; KGB0
reported. Class B as frozen (7e-4 / 3e-3) is reported, not used in the
rule (it fails on CASA's K, e2a-3b-k).
- Baseline B (`score-f0.json`): own K 3.12e-3 / 2.29e-2; rang's K
  1.79e-3 / 1.93e-2. With `bandpass_model_divided` only a **patched** arm
  was measured (archived K1, G1 with D3's re-solved B1): 2.24e-3 / 1.45e-2
  and 4.1e-5 / 4.0e-3. It is not an end-to-end run: on the subset the real
  averaged-divided arm D also moved through A0's flags and K1 (e2a-3b-k
  12), so ZSD's figures are compared with OFF and ZS, and with the patched
  ones as context only.
- **Control S (scorer):** `kz_score.py` on B's tables and e2a-3b-k's CASA
  tables reproduces `score-f0.json`'s two KGB1 rows (median, p95) to 1e-6
  relative. If not, nothing else is read until it does.

**M2, K1 outliers.** In the arm's K1 table: the number of unflagged
solutions, counted per (antenna, interval, hand), with |τ| > 10 ns, each
listed. B's expected count is 2 (ID 50, interval 7, X and Y); the scorer
counts B's table too. Also: ID 50's interval-7 delays against the median of
its other intervals, and the same count in CASA's own K1 (`tf`) of each arm.
**Fixed** means: count 0 and ID 50's interval 7 within 0.05 ns of its other
intervals' median in both hands.

**M3, the other gates, read as in E2-A's frozen protocol** (6.5, 9.9-9.11;
the scripts in `results/e2-acceptance-scripts`, unchanged, run through
`results/e2a-kzero/kz_nash.py`), development reading only, on ZS and ZSD:

| Gate / row | Reading | B (9.13) |
| --- | --- | --- |
| 1 | `rang-core run` once, rc 0, every stage done in one attempt, one receipt (`e2_post.gate1`) | met |
| 2a | FLAG and FLAG_ROW restored from `rang_original` equal `flaghash-input.json` | met |
| 2b | casacore; CASA `listobs`, `flagmanager`; CASA applycal in place against rang's apply output (class C); WSClean `-niter 0` on both columns; dask-ms | met |
| 2c | astropy WCS of every FITS | met |
| Flux | scan 9's K1 G1 B1 (the arm's configuration, `data.scans: [9]`) on scan 11; per 100 MHz bin with ≥ 10 % unflagged, median I / SR2016 within 2 % | met: 0.9967, 0.9896, 0.9838, 0.9910 |
| Target noise, DR | off-source rms rang / oracle ≤ 1.2; dynamic range ≥ 0.8 × | met: 1.011, 0.990 |
| Self-calibration rms | final over image 1 ≤ 1.02 | met: 0.440 |
| Self-calibration gains (9.10's amended form) | QuartiCal 0.2.7 on the averaged inputs, class B against rang's stored gains | met |

Not read: gate 3a (Tricolour), gate 3c and the target compact row (their
WSClean images cost about 10 h per arm and are a documented limitation,
9.14); gate 3b's full-MS CASA arm (`e2_casa3b_a`), replaced by M1's
field-0 constructions.

## 4. Deviations from E2-A's run, named

- Host nash, apptainer for docker (E2-N's shim, `kz_nash.py`), native Linux
  paths; the main checkout's lock; `nice -n 19 ionice -c3`.
- Gate 2b's WSClean `-niter 0`: KERN WSClean 3.7 in the CASA image
  (`rang-wsclean-native` stops with "Illegal instruction" on nash, E2-N's
  build check); its `-j 8` and every container's thread pools capped at
  the step's slots.
- Shared lock, 4 slots per arm run (E2-A: exclusive, 16 threads): wall
  times are not comparable with 9.13's.
- **The target oracle is reused**: rows "target noise, DR" read the arm's
  image-stage image against E2-A's archived oracle image (`oracle-a`, CASA's
  archived K1 G1 B1 applied to the target, WSClean 3.7), copied to nash. The
  oracle depends on the rang arm only through the fcal FLAG after A0 that
  CASA solved on; the target's FLAG is the flag stage's. Control C-flag
  (below) says whether the flag stage is the same; if it is not, the rows
  are labelled "oracle not matched".
- **C-flag:** the arm's flag-stage FLAG (the version saved before
  calibrate), on field 0's rows against e2a-3b-k's export of E2-A's
  (bitwise, `kz_f0.py flags`), and over every row against E2-A's version on
  `D:` (sha256 of FLAG and FLAG_ROW, read only).

## 5. Tolerance and decision rule

**No regression, gate rows (M3), against B:** a gate B met stays met, and
- flux: every counted bin within ±0.005 of B's ratio;
- target: rms ratio ≤ 1.031 and dynamic-range ratio ≥ 0.970 (B ± 0.02);
- self-calibration rms ratio ≤ 0.460 (B + 0.02).
A value outside these is a **regression not separated from host and build
drift** (no key-off full chain on nash exists).

**3b (M1, M2), against OFF (same host, same build):**
- (i) the outlier is **fixed** (M2) in ZS;
- (ii) ZS's KGB1 against CASA on rang's K: median ≤ 1.1 × OFF's and
  p95 ≤ 1.2 × OFF's. The own-K composite has no rule: CASA's own K1 holds the
  same wrong solution, so a rang K1 that is right there is expected to move
  the own-K composite up on ID 50's baselines (reported with and without
  ID 50).
- OFF against B (rang against rang, KGB1) is reported as the host/build
  drift; OFF's composites against B's say how far B's 3b figures carry to
  nash.

**Recommendation for the default** (a recommendation only: the
coordinator decides after E2-N's reading):
- **on**, if ZS meets (i) and (ii) and every gate row is within tolerance;
- **stay opt-in**, if (i) or (ii) fails;
- **not yet**, if (i) and (ii) hold and only a gate row is outside
  tolerance: a key-off full chain on nash is then needed to separate the
  key from host drift.
ZSD is read by the same words and reported as "both keys"; this note
proposes no default for `bandpass_model_divided`.

**Expected (written before any run):** ZS fixes the outlier (0.12 / 0.09
ns, as on the subset) and changes no other K1 solution by > 1e-3 ns; its
KGB1 against CASA on rang's K drops below OFF's, since CASA's G1 and B1
then see a right K1 for ID 50 (e2a-3b-k's 1.1e-3 subset part sat
downstream of that solution, calchain-floor 13, inferred); the own-K
composite rises on ID 50's baselines and is about unchanged without them.
The gate rows move by less than their tolerances: only fcal solutions
change, and the target is corrected by K1 G1 B1 of the nearest scans.

## 6. Runs and records

On nash, `~/rang-data/outputs/e2a-kzero-20261117/` (O). Driver
`results/e2a-kzero/nash/drive.sh` (detached, log `O/drive.log`, last line
`ALL DONE zs=RC zsd=RC 3b=RC`):
- `kz_chain.sh ARM` for ZS and ZSD at once: C-copy, columns, config check,
  `rang-core run` (one invocation, 4 slots, 48 GB, `e2_timed.py`), the key
  check (`kz_score.py configs`: both keys as named in each arm's
  `config.resolved.json`), E2-A's in-place post steps for gates 1, 2a-c and
  the self-calibration gains, `restore`, then the rows (self-calibration,
  target, flux) and `final-restore`. Every step at most 4 slots: the two
  arms hold 8, the most allowed from 21:30 to 06:00 SAST. Log
  `O/ARM/R/chain-steps.log`, last line `ARM DONE`.
- `kz_3b.sh`, waits for ZS's and ZSD's calibrate; every step starts only
  between 06:00 and a start that ends, by its estimate, before 21:30. One
  branch per arm at once: for OFF first its C-copy, run (8 slots) and key
  check; for every arm `kz_f0.py flags` and `prep`, then CASA `tf` and `k`
  (4 slots each); then `kz_score.py score`. Log `O/3b-steps.log`, last line
  `3B DONE`.
- Every job through the main checkout's `tools/heavy_lock.py`, slots equal
  to the threads it is allowed, inside `e2_diskguard.py` (floor 1,000 GiB on
  `/home`). Wall times per step in `O/timings.tsv`, copied to
  `research/tool-timings.md` (host nash). Status
  `~/Github/rang/outputs/status/e2a-kzero.md`, rewritten every 30 min by the
  driver.
- Compact receipts to `results/e2a-kzero/receipts/`; MS copies, images and
  CASA tables stay on nash.

## 7. What a failure does

A failed step stops its chain; it is rerun from that step (`kz_chain.sh ARM
STEP`, `kz_3b.sh STEP`) after the cause is found and named. A reading that
cannot be made is "not checked", never met. A scorer bug found on these data
is fixed with a test and both readings are reported, labelled.

## 8. Progress (2026-11-17 16:50 SAST, interim)

Read so far, controls only (no arm result):
- **Control S met:** `kz_score.py` on B's tables and e2a-3b-k's CASA arms
  gives KGB1 3.1248e-3 / 2.2885e-2 (own K) and 1.7927e-3 / 1.9323e-2
  (rang's K), equal to `score-f0.json` to the last digit
  (`receipts/score-control-s.json`). B's K1 outlier count is **2**: ID 50,
  interval 7, X 2,335.0 ns and Y 2,291.4 ns, nothing else above 10 ns.
- **C-copy met** for ZS and ZSD (hashes `1aec438d…`, `b528098a…`); OFF's is
  the first step of its branch. The config check confirms the keys
  (ZS: `k_zero_start` true, `bandpass_model_divided` false; ZSD: both true),
  and both runs' `config.resolved.json` carry them.
- B's flag-stage FLAG over every row (`D:`, read only): sha256
  `09edd31e…` (`receipts/flag-stage-hash-archived.json`), for C-flag.

Running on nash since 16:49:58 SAST: `rang-core run` of ZS and ZSD (4 slots
each), driver `O/drive.log` (started at `08125c2`). Found before any arm
ran and fixed in the scripts (commit `328ca51`): `e2avg_common` and
`e1b_score` put the checkout's `python/` (no extension) on `sys.path`;
`kz_*.py` now import the installed wheel's `rang` first and refuse any
other.

## For the coordinator (interim)

- Nothing read yet beyond the controls above. Expected order: ZS's and ZSD's
  calibrate finish tonight (after 21:30, so their 3b branches wait for
  06:00); OFF, the CASA arms and `score-kz.json` tomorrow during the day;
  each arm's chain (image, selfcal, post, rows) ends about a day after
  its start at 4 slots.
- A fresh agent scores from `O/score-kz.json` (M1, M2), `O/{zs,zsd}/R/`
  (`gate1.json`, `g2a.json`, `g2b-*.json`, `g2c.json`, `qc-selfcal.json`,
  `row-selfcal.json`, `row-target.json`, `row-flux.json`,
  `flag-stage-hash.json`) and `O/{zs,zsd,off}/f0/f0win/flags.json` (C-flag),
  by sections 3-5. `O` = `~/rang-data/outputs/e2a-kzero-20261117` on nash.
- Disk on nash: three 194 GiB copies plus three 37 GiB `f0.ms` copies
  (about 700 GiB), deletable after the reading.
