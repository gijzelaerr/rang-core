# C2e: K, G, B, A and F in `rang-core calibrate`

Task C2e of [finish-plan.md](finish-plan.md): wire the library terms of C2a to C2d into `rang-core calibrate` in
C1's frozen order ([c1-calibration-chain.md](c1-calibration-chain.md), section 1.3), with CARACal's A step and
secondary models from `fluxscale`, and re-point the refusals that still named C2a to C2d. Branch `fp-c2e-wiring`, from
main `5a6bd70`.
**Status: protocol (sections 0 to 5) frozen before the first comparison; nothing measured yet.**

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
