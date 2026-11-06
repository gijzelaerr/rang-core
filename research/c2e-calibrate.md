# C2e: K, G, B, A and F in `rang-core calibrate`

Task C2e of [finish-plan.md](finish-plan.md): wire the library terms of C2a to C2d into `rang-core calibrate` in
C1's frozen order ([c1-calibration-chain.md](c1-calibration-chain.md), section 1.3), with CARACal's A step and
secondary models from `fluxscale`, and re-point the refusals that still named C2a to C2d. Branch `fp-c2e-wiring`, from
main `5a6bd70`.
**Status: implemented and measured.** Gates 1, 2 and 4 are met. Gate 3 is met on E2-A and not on E2-B, where
`refant: auto` has no owner (section 7). The protocol (sections 0 to 5) was committed (`2d8830f`) before the first
comparison. Results are below it; this status line is the only edit above section 6.

## 0. What was read before this protocol

- C2a to C2d's notes, W2's and W4's, C1, and `rang.cal_chain.primary` (C2c).
- CARACal `8f7bb363` `crosscal_worker.py` (in the ignored `outputs/c1-sources-20261105/`), at its calls:
  - `solve()` builds each section's table list in order, starting with the tables the section applies from the
    previous one (`prev["apply"]`), and pre-applies `get_last_gain(gaintables, my_term)`: the last table of each type
    except the type being solved; for G and F, neither G nor F.
  - The secondary solves K, G and F against `smodel=[1,0,0,0]` unless an imaging step came first.
  - F copies the primary's last G table (`primary_G`), runs `gaincal(append=True)` into the copy on the secondary,
    then `fluxscale(reference=<fcal>, transfer='')`.
  - A (`do_IA`) first runs `applycal(calflag)` on the section's fields with `get_caltab_final`: the last table of each
    type, and of G and F only the later one, with the fields each was solved on. It then runs `flagdata
    mode=tfcrop` on the corrected column. C1's O1 replaces tfcrop with the Tricolour port.
  - `manage_antennas.get_refant` (`refant: auto`): flagstats per antenna, antennas within `maxdist` of the array
    centre whose baselines are all at least `minbase`, sorted by flagged fraction, the first three.
- `rang.applycal` (C4b), `rang.cal_fluxscale.bootstrap` (C2d), `rang.core_writeback` (W1) and the W2 stages
  (`core_pipeline.py`).

## 1. Design (implemented in the working tree on the protocol commit; runs snapshot it in `.code/`)

**The sequence is in the library.** `rang.cal_chain.run(ms, terms, ...)` runs a list of K, G, B, F and A terms in
order:

- K, G and B are solved per field with `cal_delay.gaincal` (default `delay_and_offset`), `cal_gain.gaincal` and
  `cal_bandpass.bandpass`. Each pre-applies the tables its `preapply` lists, with their `interp`. Tables of several
  fields are appended (`cal_fluxscale.append`).
- F is `cal_fluxscale.bootstrap` on a copy of a primary G table. The merged table is written as `<name>.append`.
- A is `applycal.applycal(calflag, CORRECTED_DATA)` of its tables, then `cal_chain.flag_corrected`: the Tricolour
  port on CORRECTED_DATA of the section's fields, grouped by field, data description and scan as `rang-core flag`
  does, with the result OR'd into FLAG.
- `cal_chain.a_tables` is CARACal's table choice for A.

Every table is written as a CASA table under `<run>/calibrate/<name>`.

**The command translates and manages the MS.** `core_pipeline.chain_terms(config, ...)` turns
`calibrate.primary` and `calibrate.secondary` into `run`'s terms:

- Defaults where the configuration is silent are CASA 6.7.6.14's: `minsnr` 3, `minblperant` 4, `calmode` ap,
  `fillgaps` 0, `refantmode` flex.
- `uvrange` reaches G, B and F, not K (CARACal does not pass it to K).
- Primary terms solve against the model column (written by `rang.calmodels` for setjy, manual and lsm), or a unit
  point for `model.source: unity`.
- Secondary terms solve against CASA's unit point (`smodel`), as CARACal. Their flux density comes from
  `fluxscale` and is recorded in the stage summary.
- F appends to the primary's last G.
- An A step's strategy defaults to `flag.strategy`. Its tables are `a_tables` of the section's history: tables
  pre-applied by the section's terms, then those it solved. Each table gets the field it was solved on, or `nearest`
  when it has several, such as an F table.
- `data.scans` reaches every solve and apply, through a new `scan` argument (CASA's name).
- `data.weights: uniform` sets unit weights where a solve would read WEIGHT_SPECTRUM. With pre-applied tables the
  solves keep SIGMA's weights, as C2a measured CASA does. **This is rang's reading of CARACal's `prep.specweights`
  and was not checked against CASA.**
- `as_is` reads WEIGHT_SPECTRUM, or WEIGHT repeated over channels when it is absent.

**Writes and resume.** calibrate now writes FLAG (A steps), CORRECTED_DATA (A steps) and MODEL_DATA. It joins
`WRITES_FLAGS`.

- Each attempt saves one flag version `rang_calibrate_<time>` before its first write. Every write session of the
  attempt (models, each A step's apply and flags) passes that same name to `WriteBack`, which saves it once.
- A rerun restores it first (`restore_before`). A rerun therefore starts from the stage's input, not from a state
  between two A steps.
- The apply stage applies CASA tables through `applycal.applycal`, with `apply.targets`' `interp`, `gainfield`,
  `calwt`, `applymode` and `data.scans`.
- `apply.targets` is required when K, G, B or F are solved.

**K offsets (C2c decision 2).** K tables hold delays only, and G absorbs K's phase offsets. Wherever an A step or an
apply target applies K without G or F, the step's summary carries the warning `cal_chain.K_ALONE`. `rang-core config
defaults` and the calibrate summary say so too.

**Library edits, additive.** `scan=None` was added to `cal_gain.gaincal`, `cal_delay.gaincal`, `cal_bandpass.bandpass`
and `applycal.applycal`; `cal_fluxscale.bootstrap` passes it on. `weight_column=None` gives unit weights. A 2-D
weight column (WEIGHT) is repeated over channels. With the defaults, every path is unchanged. Run `-00` checks this: it computes K, G, B and
F tables with main's code (`5a6bd70`) and with this branch on the same inputs, and compares their hashes. A unit test
checks that an explicit selection of every scan, and WEIGHT_SPECTRUM holding WEIGHT, give the default's tables. `solve.rs`, `jones.rs`, `correct.rs` and `core.solve_complex` are not touched.

**Refusals re-pointed** (`core_config.py`, `core_pipeline.py`, `docs/cli.md`):

- `TASKS` loses C2a to C4a.
- `TERM_TASKS` keeps only the polarisation terms (C6b, C6c) and self-calibration (C5a, C5b).
- What the complex term will never take (seconds `solint`, `combine`, `refant`, `uvrange`, `minsnr`,
  `minblperant`, `refantmode`, `preapply`, `interp` on apply, transfer to another field) is now a configuration
  error that points to the K, G and B terms, not a refusal naming C2a or C4a.
- The secondary-model refusal is gone. A complex term on the secondary with a written model is an error: models are
  written on the primary only.
- Still refused, with their real owners: polarisation terms and `feed_angle_rotation`, `extendflags`, `apply.parang`
  (C6a, C6b, C6c); polarised models (C7a); self-calibration (C5a, C5b, G6).
- New errors with no owner task (section 9): `refant: auto`, `solnorm: true`, `calmode: a`, a term `gainfield` in a
  solve, and complex and CASA terms mixed in one calibrate.

## 2. Data

- **slice:** O-CASA's `outputs/o-casa-20261030-01/work.ms` (LUNO 1934-638, four stations, one scan of 32
  integrations, 2048 channels, its stored MODEL_DATA), copied per run, read-only source. One field only, so no F.
- **a1:** A1 small (`/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms`, 16 antennas, 64 channels,
  fields J1939-6342 (0), 3C286-SIM (1), SIM-GCAL (2), SIM-TARGET (3)). For the CASA comparison it is prepared as C2d
  prepared it: RFI mask (`any`) OR'd into FLAG, and MODEL_DATA of field 0 from `truth.npz`'s calibrator model
  (`check_gain.a1_model`), both written by CASA in the container. For the identity gate it is used as stored, with
  `model.source: setjy`.
- **Held-out, `holdout128` (frozen here, generated only after the frozen cases have run):** a new
  `rang.simtruth.design` version: A1 small's antennas and schedule, **128 channels**, delays uniform in 1-30 ns,
  seeds **jones 20261146, sky 20261147, rfi 20261148, noise 20261149**. These were checked against every seed in
  `research/`, `python/` and `examples/`: no seed from 20261140 up is used. holdout256 and C2d's held-out set both
  used 20261136-39. It is generated by `examples/a1_simtruth.py generate holdout128` with noise, and prepared as a1.
  The other versions' `as_json` are unchanged (A1's regeneration test).
- Images: `rang-o-casa:6.7.6.14` (CASA). Container conventions as O-CASA's (`check_formats.docker`: `--network none`,
  `--user`, `--tmpfs /tmp`, `OMP_NUM_THREADS=4`). Runs under `/mnt/d/rang/outputs/c2e-20261106-NN`, each with a
  `.code/` snapshot (`head.txt`, `diff.patch`, `untracked.tgz`), heavy steps under `flock ~/.rang-heavy.lock`.

## 3. Gates (frozen)

### Gate 1: the command equals the library, bit for bit

`rang-core run` (stages calibrate and apply, through the console script, in a subprocess) on one copy is compared with
a hand-written reference on a second copy with the same basename in another directory. The reference calls
`rang.calmodels.set_model`, then `rang.cal_chain.run` with term dicts written out in the script (not produced by
`chain_terms`), then `rang.applycal.applycal`. On I-slice it also calls `rang.cal_chain.primary` for the first K, G, B
round, before any A step has changed FLAG. `primary` has no `scan` or weight arguments, so I-a1 cannot use it.

| Case | Data | Configuration |
| --- | --- | --- |
| I-slice | slice | `model.source: column`; `refant: m000`; `minblperant: 3`; primary K0 (`inf`), G0 (`inf`, K0), B0 (`inf`, `combine: scan`, `fillgaps: 70`, K0 G0), A0 (Tricolour first-pass strategy), K1 (`int`, G0 B0), G1 (`int`, K1 B0), B1 (`inf`, `scan`, `fillgaps: 70`, K1 G1), i.e. KGBAKGB; apply K1, G1, B1 to the field |
| I-a1 | a1 as stored | `model.source: setjy` (Stevens-Reynolds 2016); `refant: m000`; `uvrange: ">150"`; `data.scans` every scan of the MS but the last; `data.weights: uniform`; primary K, G (`inf`), B (`inf`, `scan`, `fillgaps: 70`), A; secondary on SIM-GCAL: G (`60s`, K B), A, F (`inf`, K B); apply fcal K, G, B; SIM-GCAL and SIM-TARGET K, F, B with `gainfield [J1939-6342, nearest, J1939-6342]` |

**Pass** when all of the following hold:

- every table either side writes (K, G, B, F and `F.append`) has every main-table cell and keyword equal, and every
  subtable equal (`caltable.read`). Whether the table directories are byte-identical as files is reported.
- on I-slice, `cal_chain.primary`'s K, G and B equal `run`'s K0, G0 and B0 in the same way.
- MODEL_DATA, CORRECTED_DATA, FLAG, FLAG_ROW, WEIGHT, WEIGHT_SPECTRUM and SIGMA have equal SHA-256 over the whole
  column on both copies.
- the flag version `rang_original` holds the same FLAG as the input.

### Gate 2: the chain against CASA's chain, on the composite and on CORRECTED_DATA

CASA side, in one container and in CARACal's order with CARACal's arguments (C1 section 2.2, `oracle_fluxscale.py
steps`):

1. `gaincal` K (`gaintype='K'`, no `uvrange`);
2. `gaincal` G (`calmode='ap'`, `gaintable=[K]`);
3. `bandpass` (`bandtype='B'`, `solnorm=False`, `fillgaps=70`, `gaintable=[K, G]`);
4. with a secondary: copy G, then `gaincal` (`append=True`, `smodel=[1,0,0,0]`, `gaintable=[K, B]`,
   `gainfield=[fcal, fcal]`) on it, then `fluxscale(reference=fcal, transfer='')`;
5. `applycal(calflag, calwt=False, parang=False, flagbackup=False, interp='linear')`: on fcal K, G, B
   (`gainfield ''`); on the secondary K, F, B (`gainfield [fcal, nearest, fcal]`).

Every call gets `refant='m000'`, `minsnr=3`, `refantmode='flex'` and the case's `solint`, `combine`, `uvrange` and
`minblperant`. Rang side: `rang-core run` (calibrate, apply) with the same settings on a copy of the same prepared
MS.

**No A step on either side:** CASA's A is tfcrop, rang's is Tricolour (C1 O1), so they differ by design. A is
covered by gate 1, and by the check that `flag_corrected` equals `core_flag.flag_rows` on the library's corrected data.
Term-by-term agreement is not gated (C2c section 8.2: the K estimators split phase differently between K, G and B).

| Case | Data | `solint` K / G / B (/ F) | Other |
| --- | --- | --- | --- |
| C-slice | slice | `inf` / `inf` / `inf` | B `combine=''`, `minblperant=3`, `uvrange=''`; fcal only |
| C-a1 | a1 prepared | `inf` / `inf` / `inf` / `inf` | B `combine='scan'`, `minblperant=4`, `uvrange='>150'` for G, B, F; secondary SIM-GCAL |
| H-h128 (held out) | holdout128 prepared | as C-a1 | as C-a1 |

Tolerances, frozen from C2a to C2d's measured agreement. Class B is median `<= 7e-4` and p95 `<= 3e-3` relative. C2c's
chain composites measured median 6e-6 to 5.3e-4 and p95 5e-5 to 2.8e-3. C2d's B class measured `fluxd` within 3.9e-4.

- **Composite, fcal:** per row (cross-correlations), channel and parallel hand, `J_p J_q^*` of each side's K, G, B
  (each side's tables through `rang.cal_apply` on a unit model, as C2c). Over cells both leave unflagged: relative
  difference median `<= 7e-4`, p95 `<= 3e-3`; maximum reported. Composite flags exact.
- **Composite, secondary:** the same with K, F, B. Each side's composite is multiplied by its own `fluxd` before
  comparing, because F carries `1/scale` per antenna, so the product carries `1/fd`. The gate is the same class B,
  with flags exact.
- **Flux scale:** rang's `fluxd` (fitted flux, one window) within `1e-3` relative of CASA's (C2d class B). `numSol`
  equal.
- **CORRECTED_DATA:** on the applied fields, parallel hands, cross-correlations, cells both leave unflagged:
  `|c_rang - c_casa| / |c_casa|` median `<= 7e-4`, p95 `<= 3e-3`. On the secondary, each side is divided by its own
  `fluxd` first (CORRECTED there is proportional to `fd`). Cross hands and the maximum are reported, not gated.
- **FLAG after apply:** exact on the applied fields. If any cell differs, the difference is reported per solution with
  C1's exemption: solutions with either side's SNR within a factor 2 of `minsnr`, or at `minblperant`, are exempt.
  The gate then reads "exact outside the exemption".

### Gate 3: E2's calibrate stage

On the repository's `tests/data/w2/e2a.yaml` and `e2b.yaml`, `core_config.validate(..., ["calibrate"])`:

- **E2-A:** no schema error, no refusal, no configuration error.
- **E2-B:** every refusal names C6a, C6b or C6c. E2-B also sets `refant: auto`, which has no owner task. If that
  error remains, gate 3 is **not met on E2-B** for that stated reason, and the owner decides (section 9).

### Gate 4: one held-out case

H-h128, frozen above (data, seeds, settings, tolerances), runs once after C-slice and C-a1 have been evaluated. Its
verdict stands as it comes out. Any code change after a frozen result is labelled **post hoc**, and further held-out
evidence is needed before it is claimed.

## 4. Also checked (not gates)

- `check-all` (`bash tools/check-all.sh`): the gain-hash gate (`4ed2aa89…`, `7b370c13…`, LUNO phase 2), unchanged.
- Unit tests: the default library paths give the same tables as before the edits; config refusals and errors name
  their owners; a small MS end to end through `rang-core run` with K, G, B, A, F equals `cal_chain.run` called
  directly; a forced rerun of calibrate restores its input flags first.

## 5. Rules for failures

These follow C2a to C4b. A failed frozen case stays failed in the results table. A cause found afterwards is
described, and a fix is labelled post hoc. Where CARACal's or CASA's behaviour is unclear, the code follows their
sources (file and function cited).

## 6. Results (measured 2026-11-06)

Every run below used the working tree on the protocol commit `2d8830f`, snapshotted in its `.code/`.

- **Runs up to `-11`:** while the worktree's own venv build waited behind other agents' work on `~/.rang-heavy.lock`,
  the interpreter was main's venv Python 3.14 (`~/Github/rang/.venv`), with `PYTHONPATH` set to the worktree's
  `python/`. `rang._core` was copied from main's build of `5a6bd70`, and `C2E_RANG_CORE` pointed the gate scripts at
  that venv's `rang-core`. No Rust file differs between this branch and `5a6bd70`.
- **Runs `-13` and `-14`:** the worktree's own venv.

The only edits to the working tree between runs were to the gate scripts (`examples/check_c2e.py`, setup fixes listed
below) and formatting.

### 6.1 Run -00: the library defaults did not move

`c2e-20261106-00-defaults` (`examples/probe_c2e_defaults.py`; main 20.3 s, branch 19.0 s) hashed every main-table
cell of `cal_chain.primary`'s K, G and B on the slice (field 1) and of `cal_gain.gaincal` G, `cal_fluxscale.bootstrap`
F, the merged table and `fluxd` on A1 small. It ran once with main's code (`~/Github/rang`, `5a6bd70`) and once with
this branch: **all seven equal**.

### 6.2 Gate 1: the command equals the library, bit for bit: **met**

Runs `-01` and `-02` stopped before any comparison. `check_c2e.py`'s copy deleted `table.lock`, which rang's writer
needs. Their MS copies are deleted and their logs kept.

| Case | Run | Tables equal (cells, keywords, subtables) | Table files byte-identical | MS columns equal | `rang_original` = input FLAG | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| I-slice | `-03` (93.8 s) | K0, G0, B0, K1, G1, B1; and `cal_chain.primary`'s K, G, B = K0, G0, B0 | all | all eight (DATA, MODEL_DATA, CORRECTED_DATA, FLAG, FLAG_ROW, WEIGHT, WEIGHT_SPECTRUM, SIGMA) | yes | **pass** |
| I-a1 | `-04` (230.1 s) | K, G, B, Gsec, F, F.append | all | all eight | yes | **pass** |

Seen, not gated:

- **The A step flags a lot on A1.** On A1 small, the A step (CARACal's first-pass calibrator strategy on corrected
  data) took field 0 from 0 to **62.6 %** of cells flagged, and SIM-GCAL to 49.4 %. A1's RFI covers far less than
  that. On the slice, A0 added only 0.07 % (70.10 % to 70.18 %; the slice is already heavily flagged).
- **Probe `-08-probe-a`** ran `core_flag.flag_rows` directly on field 0, with the same strategy and masks:
  - on run -04's CORRECTED_DATA, scan 1 (the field's only scan in `data.scans`) gives the A step's 62.6 % to every
    printed digit;
  - on DATA as stored it gives 34.2 % over all of field 0's scans;
  - A1's RFI mask covers 11.9 %;
  - Tricolour's static masks alone flag 57.8 % of A1's 64 channels at the first `apply_static_mask` step. A later
    `uvcontsub_flagger` step resets that, and the static mask is applied again.
- **What this shows.** Rang's A step is the Tricolour port on corrected data, as designed. The strategy flags more on
  corrected data than on raw data, and far more than the injected RFI. That points to how CARACal's first-pass
  strategy behaves on A1's data (64 channels, simulated noise), not to the wiring. The cause was not established. It is outside gate 1, which is about identity. **E1 should
  look at it before it relies on the A step** (section 10).
- F on I-a1 (setjy's Stevens-Reynolds model of J1939 against A1's own model) gave SIM-GCAL 4.29 Jy.

### 6.3 Gate 2: against CASA's chain, frozen cases: **met**

Three runs stopped at setup, before any comparison. Their MS copies are deleted and their logs and step records kept:

- `-06` and `-07`: CASA's `bandpass` takes no `refantmode`, so the script now leaves it out of that call only.
- `-10`: the copy `qc-copy` makes has no `table.lock`. On the slice no CASA edit step recreated it. The edit step now
  always runs.

The gated runs:

- `-11` (C-a1, 94.4 s) used main's venv, like the earlier runs.
- `-13` (C-slice, 28.3 s) used the worktree's own venv, built from this branch's tree (184 s).

CASA's tasks took 0.3-2.0 s each.

| Case | Run | Composite fcal median / p95 / max | CORRECTED fcal median / p95 / max | Composite gcal (× own `fd`) median / p95 / max | CORRECTED gcal (÷ own `fd`) median / p95 / max | `fluxd` rang / CASA, rel | Flags after apply | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C-slice | `-13` | 1.9e-5 / 2.4e-4 / 1.2e-3 | 1.1e-5 / 5.3e-5 / 2.4e-4 | – | – | – | exact (composite and FLAG) | **pass** |
| C-a1 | `-11` | 1.6e-4 / 7.5e-4 / 1.5e-2 | 1.5e-4 / 6.7e-4 / 1.5e-2 | 1.2e-4 / 5.1e-4 / 1.5e-2 | 1.2e-4 / 4.5e-4 / 1.4e-2 | 4.30049 / 4.30060 Jy, 2.7e-5 | exact (composite and FLAG) | **pass** |

The cross hands of CORRECTED_DATA (reported) were 1.3e-5 / 8.0e-5 on the slice and 1.4e-4 / 7.4e-4 on A1. The fcal
composite on C-a1 repeats C2c's C-a1-f0 (1.6e-4 / 7.5e-4 / 1.5e-2) to the digits shown: the command's K, G, B is C2c's
chain.

### 6.4 Gate 4: the held-out case H-h128: **met**

- **Data.** `c2e-20261106-h128/holdout128` was generated after `-11` and `-13` had been evaluated:
  `a1_simtruth.py generate holdout128`, 3.2 s, seeds 20261146-49, with noise and RFI.
- **Code.** No change was made to code that `rang-core` runs between the frozen runs and this one.
- **Run `-14`** (108.4 s, the worktree venv) ran once:

| Composite fcal | CORRECTED fcal | Composite gcal | CORRECTED gcal | `fluxd` rang / CASA, rel | Flags | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| 1.7e-4 / 1.03e-3 / 5.4e-2 | 1.6e-4 / 9.4e-4 / 5.4e-2 | 2.0e-4 / 1.43e-3 / 5.4e-2 | 2.0e-4 / 1.43e-3 / 5.3e-2 | 4.31708 / 4.31712 Jy, 9.8e-6 | exact | **pass** |

Values are median / p95 / max. The held-out maxima, 5.4e-2, are larger than the frozen cases' 1.5e-2. They are
reported, not gated, as C2c's chain maxima were (2.3e-2 on holdout256). The p95 is about half the limit.

### 6.5 Gate 3: E2's calibrate stage: **met on E2-A; not met on E2-B, for the stated reason**

Run `c2e-20261106-05-gate3` (`result.json`, `c2e_gate3.py` copied there):

- **E2-A:** `validate(["calibrate"])` passes: no error, no refusal.
- **E2-B:** six refusals, all naming C6a (`feed_angle_rotation`) or C6b and C6c (`extendflags`, Gpol, KCROSS, Xf,
  Df). There are also five configuration errors: `refant: auto` on each K, G, B and F term, which has no owner task
  (section 9).

## 7. Verdict against the frozen gates

| Gate | Verdict |
| --- | --- |
| 1. Command = library, bit for bit (slice, A1) | **met** (`-03`, `-04`) |
| 2. Against CASA's chain on the composite and CORRECTED_DATA (slice, A1) | **met** (`-13`, `-11`) |
| 3. E2's calibrate stage no longer refused | **met on E2-A**; **not met on E2-B**: its remaining refusals are all C6's, but `refant: auto` has no owner (section 9, decision 1) |
| 4. One held-out case | **met** (`-14`, holdout128) |

**What this establishes.**

- `rang-core calibrate` and `apply` run the K, G, B, A, F sequence exactly as the library does.
- Without A, they match CASA 6.7.6.14's chain as CARACal calls it, within class B on the applied calibration and on
  CORRECTED_DATA, with exact flags and `fluxd` within 3e-5. This is a port with oracles; no novelty is claimed.
- The A step is compared only with itself (gate 1), because CASA's A is tfcrop.

## 8. What changed after a result

Only the gate scripts changed after a result, all at setup, before any comparison:

- the `table.lock` copy;
- CASA `bandpass` without `refantmode`;
- the edit step always run.

No tolerance moved. No code that `rang-core` runs changed after the protocol commit apart from formatting
(`ruff format`, after check-all run 1).

## 9. What only the owner can decide

1. **`refant: auto`.** CARACal's `manage_antennas.get_refant` (section 0) is not ported, and no finish-plan task owns
   it. E2-B uses it, so E2-B's calibrate is refused for it. Options:
   - port it (a flagstats-based choice: antennas within `maxdist` of the array centre, every baseline at least
     `minbase`, fewest flags, the first three; a small task, proposed as C2f or part of E2's preparation);
   - or set an antenna in E2-B's configuration.
2. **`data.weights: uniform` in the solves.** Rang uses unit weights where a solve reads WEIGHT_SPECTRUM, and SIGMA's
   weights when tables are pre-applied, as C2a measured CASA. This was not compared with CASA after CARACal's
   `prep.specweights`. Proposed: keep, and E3 compares the CARACal arm directly.
3. **The A step's flagging on simulated data** (section 6.2): 63 % of A1's calibrator cells, against 12 % injected
   RFI. Not a C2e question, but E1's: either CARACal's first-pass strategy is the wrong one for corrected calibrator
   data on A1's band, or its static masks dominate at 64 channels. Proposed: E1 reports A's flagged fractions per
   step and checks the second-pass strategy too.
4. **Not ported, no owner** (configuration errors that say so): `solnorm: true`, `calmode: a`, a `gainfield` on a
   solve's pre-applied tables, and complex terms mixed with CASA terms. None is in CARACal's shipped configurations.
5. **C7a's decision 5** (models on the polcal field): C2e removed the C2d refusal of a written model when secondary or
   polcal terms exist. Models are still written on the primary fields only, as CARACal writes `setjy` on the flux
   calibrator. Writing the 3C286 model on the polcal field, and using it, is C6's wiring, since the polcal terms are
   still refused naming C6.

## 10. What was not checked

- **The A step against CASA's tfcrop:** not comparable by design (C1 O1).
- **A second round (KGBAKGB) against CASA:** only gate 1 has one, on the slice.
- **`data.scans`, `uniform` and setjy in the CASA comparison:** gate 2 used `as_is` weights, all scans and the column
  model, so these paths were checked for identity only (I-a1).
- **The secondary's own K term (CARACal's KGAF) and `Gsec` against CASA:** the CASA comparison's secondary is F only.
- **E2-A's calibrate on the ESO137 data:** only validated; nothing was run on E2 data (E2's job).
- **Several primary fields, several windows, `combine='obs'`:** not exercised. Several windows are refused (W4).
- **Timing:** no timing claims; the wall times above are records.
- **Cross-hand CORRECTED_DATA:** reported only. Diagonal terms leave the cross hands' ratio as the parallel hands'.

## 11. Files, runs, provenance

**Code.**

- `python/rang/cal_chain.py`: `run`, `a_tables`, `k_alone`, `flag_corrected`; `primary` unchanged.
- `python/rang/core_pipeline.py`: `chain_terms`, `stage_calibrate_chain`, `stage_version`; CASA tables in
  `stage_apply`; calibrate in `WRITES_FLAGS`.
- `python/rang/core_config.py`: `_chain_refusals`, `CASA_TERMS`, re-pointed refusals.
- The `scan` and `weight_column=None` arguments in `cal_gain.py`, `cal_delay.py`, `cal_bandpass.py`,
  `cal_fluxscale.py` and `applycal.py`; messages re-pointed there.
- `python/rang/simtruth.py` (`holdout128`), `examples/a1_simtruth.py`.
- `examples/check_c2e.py`, `examples/probe_c2e_defaults.py`; `bandpass` added to `examples/oracle_fluxscale.py`.
- `tests/test_c2e_calibrate.py` (6 tests); `tests/test_w2_commands.py` (expected tasks).
- `docs/cli.md` and `docs/gen_cli.py`; `CHANGELOG.md`.
- Not touched: `solve.rs`, `jones.rs`, `correct.rs`, `core.solve_complex`, any Rust file.

**Runs** under `/mnt/d/rang/outputs/`, each with `.code/` and `.log`:

| Run | What |
| --- | --- |
| `c2e-20261106-00-defaults` | before/after hashes |
| `-01`, `-02` | setup failures; logs only |
| `-03` | I-slice |
| `-04` | I-a1 |
| `-05-gate3` | gate 3 |
| `-06`, `-07`, `-10` | setup failures; step records and logs |
| `-08-probe-a` | A step flag fractions |
| `-11` | C-a1 |
| `-13` | C-slice |
| `-h128` | holdout128: MS, truth, RFI mask, provenance |
| `-14` | H-h128 |
| `c2e-20261106-checkall-*.log` | check-all logs |

**Inputs and images.**

- Inputs read in place: O-CASA's `work.ms` and A1 small (MS, `truth.npz`, RFI mask, `casa-small/truth.K`,
  `truth.B` for run -00).
- Seeds: holdout128's 20261146-49; tests 7.
- Image: `rang-o-casa:6.7.6.14`. Nothing was downloaded.
- Timings are in [tool-timings.md](tool-timings.md).

## For the coordinator

Do not apply until merged; all text proposed.

**`research/STATE.md`, new top entry:**

> C2e, 2026-11-06 (implemented; measured; gates 1, 2 and 4 met, gate 3 met on E2-A).
> [c2e-calibrate.md](c2e-calibrate.md): `rang-core calibrate` runs CARACal's K, G, B, A and F terms in C1's order
> through `rang.cal_chain.run`, and `rang-core apply` applies their CASA tables (`rang.applycal`).
> - **Identity:** the command equals the library chain bit for bit on the slice (KGBAKGB) and on A1 (with secondary,
>   F, two A steps, `data.scans`, uniform weights): tables, MODEL_DATA, CORRECTED_DATA and FLAG.
> - **Against CASA:** CASA's `gaincal` K, G, `bandpass`, `fluxscale` and `applycal`, as CARACal runs them, agree
>   within class B on the composite and on CORRECTED_DATA (median ≤ 2e-4, p95 ≤ 1.4e-3), with exact flags and
>   `fluxd` within 3e-5, on the slice, A1 and a new held-out set, `holdout128`.
> - **Still refused:** E2-B's calibrate is refused for C6's terms and for `refant: auto`, which no task owns (owner
>   decision).
> - **For E1:** CARACal's first-pass Tricolour strategy, used as the A step, flags 63 % of A1's corrected calibrator
>   cells.

**`research/README.md`, index line:**

> [C2e, K, G, B, A and F in rang-core calibrate](c2e-calibrate.md): the calibration terms wired into the commands in
> C1's order, bit-identical to the library and within class B of CASA's chain, with a held-out set (`holdout128`).

**`research/finish-plan.md`:**

- C2e row: done (this note).
- Section 7: add section 9's decisions 1 to 3 as item 14. Decision 5 answers C7a's decision 5: C6 writes and uses the
  polcal model.

**Merge notes.** This branch edits:

- `core_config.py`, `core_pipeline.py` and `tests/test_w2_commands.py`, which C7a also touched; main `4daf85a` is
  merged in (section 12);
- `cal_gain.py`, `cal_delay.py`, `cal_bandpass.py`, `cal_fluxscale.py` and `applycal.py` (additive arguments);
- `simtruth.py` (one more version), `examples/oracle_fluxscale.py` (`bandpass`), `docs/cli.md` and `CHANGELOG.md`.

**Not removed:** `/mnt/d/rang/outputs/c2e-20261106-*` (MS copies in `-03`, `-04`, `-11`, `-13` and `-14` can go;
keep `-h128` as a held-out set). `~/Github/rang/outputs/status/fp-c2e.md` can go after merge.
