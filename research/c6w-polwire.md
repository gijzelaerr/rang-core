# C6w and C7b: the polarisation terms in `rang-core calibrate` and `apply`, applied end to end

Tasks C6w and C7b of [finish-plan.md](finish-plan.md) (rows C6w and C7; section 7 items 14 to 17). C6w wires C6's
library ([c6-polterms.md](c6-polterms.md), `rang.cal_pol`) into the commands as that note's "Proposed wiring"
(steps 1 to 5) describes. C7b applies the polarisation solutions end to end on C6's `poldx` truth, with C7a's
3C286 model ([c7a-polmodels.md](c7a-polmodels.md)) on the polcal field, against the truth and against CASA
6.7.6.14's `applycal` of CASA's own chain. Branch `fp-c6w-polwire`, from main `02024bd` (W3 merged).
**Status: implemented and measured; every frozen gate met on `poldx` (run -01) and on the held-out `polholdout`
(run -02); gate 3 met (E2-B's remaining items are `refant: auto` and `extendflags`, both without an owner task).**
The protocol (sections 1 to 7) was committed (`fb03e2e`) before the first comparison; results are in sections 8 to
10, and this status line is the only edit above them.

## 1. What was read before this protocol

- C6's note (sections 1-11 and "For the coordinator"), C7a's (sections 2, 3, 6, 8, 10), C2e's, W3's section 5.3,
  C1's sections 1.3 and 2.2, and the finish plan's section 7 items 14-17.
- CARACal `8f7bb363` `polcal_worker.py` (C1's copy in `~/Github/rang/outputs/c1-sources-20261105/`):
  - `xcal_model_fcal_leak`: Gpol `gaincal(gaintype='G', calmode='p', solint=gain_solint, combine='',
    parang=True)` with the crosscal `caltablelist` (the field's `otfcal` callib); KCROSS and Xf add Gpol (`linear`)
    and KCROSS (`nearest`); Df on the leakage calibrator with the crosscal tables, KCROSS and Xf (`nearest`).
  - The apply interps: Gpol `linear`, KCROSS, Xf, Df `nearest`.
  - `feed_angle_rotation` (lines 1486-1505): `ang[:, 0] = ang[:, 1] = deg2rad(FAR)` on FEED of the MS, i.e. it
    **sets** RECEPTOR_ANGLE, it does not add to it. rang's schema text said "added"; corrected here.
  - `extendflags` (lines 1600-1641): `flagdata(mode='extend', ntime='60s', combinescans=True, growtime=80,
    growfreq=80, growaround=True, flagnearfreq=True, flagneartime=True)` on the polcal and leakage fields.
- CASA (C1's 2023 mirror) for C6's decision 3: `SolvableVisCal::verifyConstraints` (SDBList, line 3741:
  `minblperant` per antenna), `VisCalSolver2::solve` ("Insufficient unflagged antennas", iteration limit,
  `converged`), `DJones`. **No data-fraction rule exists**: CASA's Df flags in RFI-heavy channels come from
  `minblperant`, the solver's `parOK` and SNR, i.e. from its iterative solver on poorly sampled data. A rule matching
  CASA cannot be derived from its source, so rang's solutions stay the default (section 3, decision 3).

## 2. Design (implemented in the working tree on the protocol commit)

**Configuration (`core_config`).**

- `Gpol`, `KCROSS`, `Xf`, `Df` leave `TERM_TASKS`; `POL_TERMS` and `CHAIN_TERMS = CASA_TERMS + POL_TERMS` are new.
  The four run in the polcal section only (elsewhere a configuration error), and K, G, B, A, F stay out of it.
  `TASKS` loses C6a, C6b and C6c: nothing refers to them any more.
- New keys: `calibrate.polcal.model` (`source: nrao` (default), CARACal's `nrao_xcal.yml` through
  `calmodels.caracal_xcal`, looked up by `name` or the field's name; `source: column`, an existing column),
  `calibrate.polcal.frame` (`casa` default, `rang`), KCROSS `estimator` (`casa` default, `refined`), Df
  `min_data_fraction` (default off).
- `feed_angle_rotation` (degrees) now **sets** the receptor angle of both receptors of every antenna for P, in
  memory (`rang.cal_pol.row_angles(receptor_angle=...)`); FEED is not rewritten (rang writes only through W1's
  `WriteBack`, and FEED is not among its columns). On a MeerKAT MS whose FEED holds 0 this gives CARACal's result;
  where FEED already holds −π/2 (A1, `poldx`) −90 changes nothing.
- `apply.parang` is accepted; applying a Gpol, KCROSS, Xf or Df table without it is a configuration error (CASA
  solved them with P; applying them without would be silently wrong), and so is `apply.parang` with a complex
  table or with no `apply.targets`.
- Configuration errors with no owner task: Gpol `calmode` other than `p`; `parang: false` on Xf or Df (polcal
  always applies P); `preavg` (not ported; rang solves the cells, C6 section 1); a `clip` other than
  `[low <= 0, high > 0]`; an unknown NRAO model name; **`extendflags: true`** (CASA's `flagdata mode=extend` is
  not ported, and no finish-plan task owns it: an owner decision, section 7).
- `refant` is required for Gpol and Df, as for K, G, B, F; KCROSS (recorded only) and Xf (CASA ignores it) do not
  need it. `refant: auto` stays an error (C2e's owner decision).

**Terms (`core_pipeline.chain_terms`, new `polcal_terms`).** After the primary and secondary terms, the polcal
section's terms in the order given, each with CASA's defaults where silent (`minsnr` 3, `minblperant` 4,
`refantmode` flex), `uvrange` reaching all four (CARACal), `parang` true, the frame and the receptor angle. A
pre-applied table without an `interp` gets CARACal's (`cal_apply.CARACAL_INTERP`: K, G, B, F, Gpol `linear`;
KCROSS, Xf, Df `nearest`). Gpol, KCROSS and Xf solve against the polcal model; Df against the primary's model
(the leakage calibrator must then be a primary field when the model is written, else a refusal before any
write).

**Models (`write_models`).** In calibrate's one `WriteBack` session with the attempt's flag version (C2e, W3 5.3):
the primary model as before, then, for `source: nrao`, `calmodels.set_model` of `caracal_xcal(name)` on each
polcal field of Gpol, KCROSS and Xf (C7a's tabular `setjy` path, 0 ulps against CASA). Without polcal terms the
path is C2e's.

**Library (`cal_chain.run`, `_solve_pol`).** Gpol by `cal_pol.gpol`, KCROSS by `cal_pol.kcross`, Xf by
`cal_pol.xf`, Df by `cal_pol.df` then `cal_pol.clip_df` (the table written is the clipped one, as CARACal clips
in place; the step records the count). Several fields are appended (`cal_fluxscale.append`), as for K, G, B.
`scan`, `weight_column` (None: unit weights) and `model_column` reach them. **Additive library arguments**
(defaults unchanged): `cal_pol.load`/`gpol` `scan`, `receptor_angle`, `weight_column=None`; `row_angles`
`receptor_angle`; `kcross` `estimator`; `df` `min_data_fraction`; new `cal_pol.kcross_refine`,
`cal_pol.data_fraction`.

**Apply (`applycal.applycal`, `stage_apply`).** `parang=True` corrects by P after the tables (CASA's order,
`cal_pol.apply`), in the polcal frame with the receptor angle. Each field's angles are computed once, by
`cal_pol.row_angles` over **all** rows of the field, before the chunk loop, and indexed per chunk: the angles,
and so CORRECTED_DATA, do not depend on `data.chunk_rows` (unit test: chunks of 7 rows against one chunk, and
both against `cal_pol.apply`, bit for bit). With no table and `parang=True`, applycal applies P alone.

**Memory (W3 5.3).** The polarisation terms read a whole field at once, as C2e's terms do: they join
`chain_memory_problems`, the preflight refusal above `data.memory_limit_gb`. Chunking them is W3b.

Unit tests: `tests/test_c6w_polwire.py` (configuration, the specs `chain_terms` gives, applycal's P against
`cal_pol.apply` across chunkings and with the receptor angle in memory against FEED, the KCROSS refinement);
the C2e and W2 tests that expected C6 refusals now expect none (`refant: auto` and `extendflags` remain errors).
Not touched: `solve.rs`, `jones.rs`, `correct.rs`, `core.solve_complex`, any Rust file.

## 3. Defaults (C6's open decisions 3-5; all provisional, owner decisions in section 7)

| Decision | Default | Option | Why |
| --- | --- | --- | --- |
| 3. Df on RFI-heavy channels | rang's least-squares solutions (no extra flags) | `min_data_fraction: f` flags a channel whose unflagged cross-hand fraction is below `f` (rang's rule) | CASA has no such rule (section 1); its flags come from its iterative solver |
| 4. KCROSS combine | per scan, `combine: ''` (CARACal's) | `combine: scan` | CARACal's setting; C6 found the per-scan delay ill-conditioned on a scan whose cross hands vanish |
| 5. KCROSS estimator | `casa`: CASA's FFT and parabola | `refined`: Newton steps on `|Σ S_c e^{-2πiν_cτ}|` from CASA's value | CASA's estimator; the bias is up to 2.2e-4 ns |
| Df clip | CARACal's `[-0.6, 0.6]` | `clip: [-a, a]` or `[]` | CARACal |
| Parallactic frame | `casa` (C6 decision 1) | `rang` | CASA's `parang=True` |

## 4. Gates (frozen before the first comparison)

### Gate 1: `rang-core calibrate` equals C6's library chain, bit for bit

`rang-core calibrate` (console script, subprocess) on one prepared copy, and a hand-written reference on a second
copy with the same basename (`examples/check_c6w.py reference`): `calmodels.set_model` (Stevens-Reynolds 2016 on
J1939-6342; `caracal_xcal("3C286")` on 3C286-SIM), `cal_chain.run` with hand-written K, G, B, F terms (C2e's
library), then `cal_pol.gpol`, `kcross`, `xf`, `df`, `clip_df(0.6)` called with their arguments written out
(none produced by `chain_terms`). **Pass** when every table either side writes (K, G, B, F, F.append, Gpol,
Kcross, Xf, Df) has every main cell, keyword and subtable cell equal; DATA, MODEL_DATA, FLAG, FLAG_ROW, WEIGHT,
WEIGHT_SPECTRUM and SIGMA after calibrate have equal SHA-256 on both copies; and `rang_original` holds the input
FLAG. File byte-identity is reported.

### Gate 2: `rang-core apply` equals `cal_pol.apply`, bit for bit

`rang-core apply` (with `data.chunk_rows: 700`, so the 1,440-6,720-row fields are applied in several chunks)
against `cal_pol.apply(DATA, FLAG, ..., tables, angles=cal_pol.row_angles(field's rows), interp, table_fields)`
on the reference copy with the reference's tables, per field: CORRECTED_DATA bit-identical (`uint32` view) and
FLAG identical on every row of every applied field (all four fields are applied).

### Gate 3: E2's calibrate stage

`core_config.validate(..., ["calibrate"])` on `tests/data/w2/e2a.yaml` passes; on `e2b.yaml` **no refusal names
a task** (none names C6a, C6b or C6c). E2-B's remaining items are configuration errors without an owner task:
`refant: auto` on every term (C2e's decision) and `extendflags: true` (section 7). Gate 3 is met when that is so;
those two are reported as owner decisions, not as a failure of this task.

### Gate 4 (C7b): the applied calibration against the truth and against CASA

**Data:** `poldx` noisy (`/mnt/d/rang/outputs/c6-20261106-sets/poldx/a1-poldx.ms`), the RFI mask (`any`) OR'd into
FLAG by CASA on one copy (`oracle_pol.py edit`), then copied for CASA, the command and the reference. CASA only on
the noisy set (C6: CASA dropped a noise-free Gpol interval).

**Both sides, CARACal's chain in C1's order** (refant m000, `minsnr` 3, `minblperant` 4, `refantmode` flex,
`uvrange '>150'` for G, B, F and all polarisation terms, none for K), no A step on either side:

- models: `setjy` Stevens-Reynolds 2016 on J1939-6342; `setjy` manual on 3C286-SIM with CARACal's `nrao_xcal.yml`
  3C286 (I 14.7172 Jy at 1.47 GHz, `spix` 3 terms, `polindex [0.098]`, `polangle [0.575959]`, RM 0; rang:
  `polcal.model: {source: nrao, name: 3C286}`);
- K (`inf`), G (`ap`, `inf`, K), B (`inf`, `combine scan`, `fillgaps 70`, K G); F on SIM-GCAL (`inf`, K B,
  CASA: copy of G, `gaincal(append=True)`, `fluxscale`);
- Gpol (`60s`, K G B), KCROSS (`inf`, per scan, CASA's estimator, K G B Gpol), Xf (`inf`, `combine scan`,
  K G B Gpol KCROSS), Df (J1939-6342, `inf`, `combine scan`, K G B KCROSS Xf), Df clipped at 0.6; interps
  CARACal's; `feed_angle_rotation -90` on rang's side (FEED holds −π/2 already, so CASA needs no rewrite);
- apply with `parang=True`, `calflag`, `calwt=False`: 3C286-SIM K G B Gpol KCROSS Xf Df; J1939-6342 K G B KCROSS
  Xf Df; SIM-GCAL and SIM-TARGET K F B KCROSS Xf Df with `gainfield [J1939-6342, nearest, J1939-6342, '', '',
  '']`.

**Statistics.** Polcal source (a point at the phase centre): per channel, the mean of each correlation over the
field's unflagged cross-correlation cells (all scans; and per scan, reported), then `I = Re(XX+YY)/2`,
`Q = Re(XX−YY)/2`, `U = Re(XY+YX)/2`, `p = sqrt(Q²+U²)/I`, `χ = atan2(U, Q)/2`. Truth: p = 0.095, χ = 33°, RM 0
(`simtruth.XCAL`). The model's p is 9.8 %: Strategy 1 solves no amplitude from the polcal model, so the
calibrated p should be the truth's, and the p gate is tighter than the 0.3-point gap. Polarised target components
(the truth's six): per channel, CORRECTED_DATA minus the truth's sky-frame model of every other target component
(`simtruth.target_coherency`), fitted with the component's own I visibility shape `T` (`a = Σ T* S / Σ |T|²` for
S = I, Q, U visibilities, real parts); `z_c = (a_Q + i a_U) e^{−2iχ_t(ν_c)}` with the truth's `χ_t = χ0 + RM λ²`
(simtruth's λ = 0 reference); band estimate `R = Σ w z / Σ w` with `w = Σ |T|²`; `Δχ = arg(R)/2`, `p = |R| / ā_I`;
the thermal error `σ_R` from the scatter of `z_c` (`Σ w² |z − R|² / (Σ w)²`), `σ_χ = σ_R / 2|R|`.

**Tolerances, derived from C6's measured chain-against-truth error** (run -06: strategy 1 on the twin with the
truth's crosscal, χ error median 0.58°, p95 1.11°, p 0.0947 for 0.095, `|Δ(Q+iU)|/|Q+iU|` median 2.5 %; the
thermal error of the per-channel polcal estimate is about 0.02°, negligible):

| Item | Gate |
| --- | --- |
| Polcal χ against the truth | per-channel `|χ_c − 33°|`: median ≤ 1.11° (C6's p95), p95 ≤ 2.22° |
| Polcal p against the truth | `|median_c p_c − 0.095|` ≤ 0.0015 (C6 measured 0.0003; half the model's 0.003 offset) |
| Polcal against CASA's chain | cells both leave unflagged: per-channel `|χ_rang − χ_casa|` median ≤ 0.21°, p95 ≤ 0.90°; `|p_rang/p_casa − 1|` median ≤ 7.4e-3, p95 ≤ 3.2e-2. Derived from class B: a relative error ε of I on the cross hands moves χ by at most ε/(2p) and p by ε/p, with ε = 7e-4 (median) and 3e-3 (p95) |
| CORRECTED_DATA against CASA (class B) | on 3C286-SIM and SIM-TARGET, per cell and correlation `|V_rang − V_casa| / max_k |V_casa,k|` (C6 4.2's metric), cells both leave unflagged: median ≤ 7e-4, p95 ≤ 3e-3. J1939-6342 and SIM-GCAL reported. Flags reported, not gated: Df's flags are known to differ on RFI-heavy channels (C6 decision 3, kept as rang's default) |
| Target components against the truth | each component with `σ_χ ≤ 0.2°` is gated: `|Δχ| ≤ 1.11° + 3σ_χ` and `|p/p_t − 1| ≤ 0.05 + 3σ_R/|R|` (0.05: twice C6's 2.5 %); the others are reported. At least one component must be gated |
| Target components against CASA | each gated component: `|Δχ_rang − Δχ_casa| ≤ 3e-3/(2 p_t)` rad and `|p_rang/p_casa − 1| ≤ 3e-3/p_t` (class B's p95 relative to the component's own I), on cells both leave unflagged |

Reported, not gated: the per-scan polcal values (KCROSS per scan; C6's scan 22 with vanishing cross hands), the
KCROSS delays of both sides and the truth's `τ_c`, `fluxscale`'s flux densities, the Df flag counts, MODEL_DATA
rang against CASA on both calibrators, and the model's p and χ against C7a's published 3C286 values
(Perley & Butler 2013 at 1.05, 1.45, 1.64 GHz; NRAO 2019 at 1.02, 1.47 GHz).

### Gate 5: held-out

**`polholdout`**, frozen here: C6's held-out truth (seeds 20261156-20261159, `τ_c` −3.7 ns), not in any other
`simtruth.SEEDS` entry. C6's library-level held-out results on it are published (C6 section 9); this task has not
run anything on it. It runs **once**, with gates 1, 2 and 4 exactly as above (the same script, `--version
polholdout`), after the `poldx` run has been evaluated. Any change after a frozen result is labelled post hoc.

## 5. Cases and runs

| Case | Data | Gates |
| --- | --- | --- |
| I/A/T-poldx | `poldx` noisy, one run: CASA chain, `rang-core calibrate`, `rang-core apply`, the reference | 1, 2, 4 |
| G3 | `e2a.yaml`, `e2b.yaml` | 3 |
| H-polholdout | `polholdout` noisy, the same | 1, 2, 4, held out |

Runs `/mnt/d/rang/outputs/c6w-20261106-NN`, each with a `.code/` snapshot and a `.log`; CASA steps under
`flock ~/.rang-heavy.lock`. `examples/check_c6w.py run <run> --version V`.

## 6. Rules for failures

As C2e and C6: a failed frozen case stays failed in the results; a cause found afterwards is described; a fix is
labelled post hoc and needs further held-out evidence. A setup failure before any comparison (a script error) is
fixed and rerun, and recorded.

## 7. Owner decisions (open; defaults provisional)

1. **Df on RFI-heavy channels** (C6 decision 3): rang's solutions are kept; `min_data_fraction` exists but is off,
   because CASA has no such rule to copy.
2. **KCROSS per scan** (C6 decision 4): CARACal's per-scan default; `combine: scan` available.
3. **KCROSS's estimator bias** (C6 decision 5): CASA's estimator by default; `estimator: refined` available.
4. **`extendflags`** (CASA `flagdata mode=extend`, CARACal's growtime and growfreq 80): not ported, no task owns
   it; E2-B sets it. Port it (with CASA as an exact-flags oracle; for E2's preparation or a new task), or drop it
   from E2-B.
5. **`feed_angle_rotation` in memory**: rang uses the angle for P but does not write FEED, so CASA reading a
   rang-calibrated MS whose FEED holds 0 would apply a different P (`parang=True`) than rang did.

## 8. Results on `poldx`, run -01 (measured 2026-11-06, the protocol commit's code)

Archive: [results/c6w-polwire.json](results/c6w-polwire.json) (both runs' `result.json` and gate 3).

`/mnt/d/rang/outputs/c6w-20261106-01` (`.code/` snapshot of `fb03e2e`, clean tree; `.log`; `result.json`), under
`flock ~/.rang-heavy.lock`, 357 s wall including the lock wait. CASA's container step (prepare, the 18 CASA calls,
the export) 51.0 s, CASA's tasks 0.2-4.3 s each; `rang-core calibrate` 56.3 s, `apply` 62.0 s (with
`data.chunk_rows: 700`, on `/mnt/d`), the reference 34.7 s. No CASA task raised.

**Gate 1, met.** All nine tables (K, G, B, F, F.append, Gpol, Kcross, Xf, Df) equal cell for cell, keywords and
subtables, and their files are byte-identical; DATA, MODEL_DATA, FLAG, FLAG_ROW, WEIGHT, WEIGHT_SPECTRUM and SIGMA
after calibrate have equal SHA-256; `rang_original` holds the input FLAG. KCROSS per scan: 3.178, 3.134, 3.241,
3.218 ns on both; Df's clip at 0.6 flagged no parameter (Df's own flags: 8).

**Gate 2, met.** CORRECTED_DATA bit-identical and FLAG identical against `cal_pol.apply` on every row of the four
fields (1,920, 1,440, 2,400, 6,720 rows), applied in chunks of 700 rows.

**Gate 4 (C7b), met.**

| Item | rang | CASA | Gate |
| --- | --- | --- | --- |
| 3C286-SIM `|χ_c − 33°|` median / p95 / max | 0.550° / 0.620° / 0.80° | 0.553° / 0.618° / 0.82° | ≤ 1.11° / ≤ 2.22°: pass |
| 3C286-SIM median p (truth 0.095, model 0.098) | 0.09446 | 0.09446 | `|Δ|` 0.00054 ≤ 0.0015: pass |
| 3C286-SIM `|χ_rang − χ_casa|` median / p95 | 0.0027° / 0.028° | – | ≤ 0.21° / ≤ 0.90°: pass |
| 3C286-SIM `|p_rang/p_casa − 1|` median / p95 | 2.4e-5 / 3.9e-4 | – | ≤ 7.4e-3 / ≤ 3.2e-2: pass |
| CORRECTED_DATA class B, 3C286-SIM median / p95 / max | 2.2e-4 / 1.1e-3 / 6.1e-2 | – | pass |
| CORRECTED_DATA class B, SIM-TARGET | 2.1e-4 / 1.3e-3 / 7.2e-2 | – | pass |
| CORRECTED_DATA class B, J1939-6342 and SIM-GCAL (reported) | 1.5e-4 / 6.4e-4; 1.7e-4 / 1.3e-3 | – | – |
| Target component 0 (0.5 Jy point, p 0.127, RM −30.3): Δχ, p/p_t (σ_χ 0.050°) | +0.513°, 0.9987 | +0.514°, 0.9988 | ≤ 1.26°, ≤ 0.055: pass; against CASA −0.0018°, 0.99995: pass |

Flags after apply are **exact** on all four fields, although the Df tables' flags differ (rang 8 parameters, CASA
736; C6 decision 3). rang's `apply.rs` copies CASA's Df rule, under which a flagged leakage does not flag the data
(C4a decision 7). So the two sides differ only in the corrected values of those channels, and that difference is
inside class B.

Per scan (reported):
- χ error median 0.38°, 0.86°, 0.03°, 0.96° on scans 2, 8, 14, 22 (CASA 0.39°, 0.85°, 0.03°, 0.96°); p 0.0934-0.0951.
  The spread between scans is strategy 1's, the same in rang and CASA. C6 run -06 traced it: the unobservable
  `d_x,r` gives an error of about `2 d_x,r Q`, which rotates with the parallactic angle.
- Scan 22, where C6 found the per-scan KCROSS ill-conditioned: χ within 0.005° of CASA's (median).
- The KCROSS delays (3.13-3.24 ns) sit above the truth's effective cross-hand delay (`τ_c + τ_x,r − τ_y,r` = 3.09 ns).
  KCROSS takes up the linear part of Xf, as C6 found.
- `fluxscale`: SIM-GCAL 4.30025 Jy (rang), 4.30038 Jy (CASA), 2.9e-5 relative.

The other five polarised target components are ungated: their `σ_χ` (1.6-11.8°) is above the 0.2° the gate needs.
- Against CASA, all five agree within their class-B tolerances.
- Against the truth, four pass the (ungated) tolerance. Component 37 does not (1.7 mJy, p 0.073, polarised flux
  0.13 mJy): p/p_t 3.96, with CASA's chain at 3.97.
- The cause is not established. Because CASA's chain gives the same value, it lies in the estimator on such a faint
  component, not in either calibration. A likely candidate: the truth's other components are subtracted without the
  uncalibrated direction-independent self-cal term that the target carries.

**The model against the published 3C286 values (reported; C7a's T2).** rang's MODEL_DATA on 3C286-SIM is C7a's
`NRAO_XCAL`, with constant p 9.8 % and χ 33.00002°.
- Δp against Perley & Butler 2013: +1.20, +0.30, −0.10 points at 1.05, 1.45, 1.64 GHz.
- Δp against NRAO 2019: +1.20, 0.00 points at 1.02, 1.47 GHz.
- Δχ: +0.00002°.

This repeats C7a's T2 to the digit. It measures CARACal's model, not the calibration: with strategy 1 the calibrated
p comes from the data (0.0945, truth 0.095), not from the model.

**MODEL_DATA, rang against CASA's `setjy` (reported).** `result.json` gives `max_rel 0` and `bit_identical: false`
for both calibrators. The second is a reporting artefact: casatools exports MODEL_DATA as complex128, and the script
compared `uint32` views of different widths. Cast to complex64, CASA's MODEL_DATA is bit-identical to rang's on both
fields. This was checked after the run on the same arrays, with no code change.

## 9. Held-out results, `polholdout`, run -02 (run once, unchanged code)

`/mnt/d/rang/outputs/c6w-20261106-02` (`.code/` of `fb03e2e`, clean): 858 s wall including about 10 min of lock
wait. CASA's container step took 45.9 s, `calibrate` 42.7 s, `apply` 58.3 s and the reference 33.1 s. No code or
tolerance changed between -01 and -02.

| Gate | Result |
| --- | --- |
| 1 | met: nine tables equal, files byte-identical; seven columns equal; `rang_original` = input |
| 2 | met: CORRECTED_DATA bit-identical and FLAG identical on all four fields |
| 4, 3C286-SIM against the truth | `|χ_c − 33°|` median 0.383°, p95 0.554° (rang); p 0.0954 (`|Δ|` 0.0004): pass |
| 4, 3C286-SIM against CASA | χ median 0.0023°, p95 0.021°; p median 2.2e-5, p95 2.2e-4: pass |
| 4, CORRECTED_DATA class B | 3C286-SIM 1.4e-4 / 6.5e-4; SIM-TARGET 1.5e-4 / 9.3e-4: pass (J1939 1.3e-4 / 6.7e-4, SIM-GCAL 1.1e-4 / 4.8e-4); flags exact on all four |
| 4, target component 0 (0.5 Jy, p 0.117, RM +54.6) | Δχ −0.198°, p/p_t 1.0046 (CASA −0.198°, 1.0046): pass, and against CASA 0.0004°, 1.0000: pass |

Also measured:
- KCROSS per scan: −3.356, −3.391, −3.338, −3.378 ns, with CASA within 1.7e-4 ns (truth effective −3.46 ns).
- Df flags: rang 0, CASA 1,024 (C6's 32 RFI channels). Flags after apply are exact.
- `fluxscale`: 4.29030 Jy on both sides.
- Ungated components: five. Component 7 (21 mJy, p 0.114) has p/p_t 1.20 against an ungated tolerance of 0.17,
  with CASA's chain at 1.2043. The others pass. As in run -01, CASA's chain gives the same value.

## 10. Verdict against the frozen gates

| Gate | Verdict |
| --- | --- |
| 1. `rang-core calibrate` = C6's library chain, bit for bit | **met** on `poldx` (-01) and `polholdout` (-02) |
| 2. `rang-core apply` = `cal_pol.apply`, bit for bit | **met** (-01, -02), applied in chunks |
| 3. E2's calibrate stage | **met** (`c6w-20261106-03-gate3`): E2-A validates; E2-B has no refusal naming a task. Its configuration errors: `refant: auto` on all nine terms (C2e's owner decision) and `extendflags: true` (section 7, decision 4) |
| 4. C7b: χ and p against the truth, and against CASA's chain within class B | **met** (-01) |
| 5. Held-out | **met** (-02) |

**What this establishes.** `rang-core calibrate` and `apply` run CARACal's strategy 1 (Gpol, KCROSS, Xf, Df, with
P) exactly as `rang.cal_pol` does. End to end on two simulated truths with a leaking reference antenna, with
CARACal's 3C286 model, rang's chain and CASA 6.7.6.14's chain give the same calibrated polarisation:
- χ within 0.003° median;
- p within 3e-5;
- CORRECTED_DATA within class B, with exact flags.

Both are 0.4-0.6° (median) from the truth's χ, which is strategy 1's limit on such a truth (C6), and recover the
truth's p (9.45-9.54 % for 9.5 %), not the model's 9.8 %. This is a port with oracles. No novelty is claimed, and
no timing.

## 11. What was not checked

- Real data: no LUNO or native 3C286 scan was run (E2's job). E2-B was only validated.
- `feed_angle_rotation` on an MS whose FEED holds 0 (the slice): unit-tested only (`applycal` with the angle in memory
  equals FEED holding it), not run against CASA with a rewritten FEED.
- The options away from the defaults (`estimator: refined`, `min_data_fraction`, KCROSS `combine: scan`,
  `frame: rang`, `polcal.model.source: column`): unit-tested or exercised by construction. They were not compared
  with CASA, which has no equivalent for the first two.
- `data.scans` and `data.weights: uniform` with polarisation terms: passed through to the solves, not run here.
- Several polcal fields, the Df field outside the primary fields with a column model, `combine='obs'`, and the
  memory refusal of a polarisation term above the limit (by construction through `chain_memory_problems`, not run).
- The faint target components that miss the truth (sections 8 and 9): not traced.
- Timing: no claims; wall times are in `tool-timings.md`.

## 12. Files and runs

**Code.**
- `python/rang/core_config.py`: `POL_TERMS`, `CHAIN_TERMS`, polcal `model` and `frame`, `estimator`,
  `min_data_fraction`, `_pol_term_errors`, the re-pointed refusals.
- `python/rang/core_pipeline.py`: `polcal_terms`, `polcal_fields`, `polcal_models`, `_polcal_problems`, the polcal
  model in `write_models`, P in `stage_apply`, `chain_memory_problems` on `CHAIN_TERMS`.
- `python/rang/cal_chain.py`: `_solve_pol` and the polarisation branch of `run`.
- `python/rang/cal_pol.py`: the additive arguments, `kcross_refine`, `data_fraction`.
- `python/rang/applycal.py`: `parang`, `frame`, `receptor_angle`, `_field_angles`.
- `examples/check_c6w.py`; `tests/test_c6w_polwire.py` (5 tests); `tests/test_c2e_calibrate.py` and
  `tests/test_w2_commands.py` (expectations); `docs/cli.md` (regenerated); `CHANGELOG.md`.
- Not touched: `solve.rs`, `jones.rs`, `correct.rs`, `core.solve_complex`, any Rust file.

**Runs** under `/mnt/d/rang/outputs/`, each with `.code/` and `.log`:

| Run | What |
| --- | --- |
| `c6w-20261106-01` | poldx: gates 1, 2, 4 (MS copies, 1.2 GB) |
| `c6w-20261106-02` | polholdout, held out: gates 1, 2, 4 |
| `c6w-20261106-03-gate3` | gate 3 |
| `c6w-20261106-checkall-*.log` | check-all logs |

Inputs and provenance:
- Inputs read in place: C6's `c6-20261106-sets/{poldx,polholdout}` (noisy MS, RFI mask, truth).
- Seeds: those of C6's two truths (poldx 20261146-49, polholdout 20261156-59); no new seed.
- Image: `rang-o-casa:6.7.6.14`. Nothing was downloaded.
- Before the protocol commit, the command and the reference were run once on a scratch copy of the `poldx` twin (not
  a gated case), to check that they run. Nothing was compared (`~/Build/tmp/20261106-c6w-smoke`, deleted).

## For the coordinator

Do not apply until merged; all text proposed.

**`research/STATE.md`, new top entry:**

> C6w and C7b, 2026-11-06 (implemented; measured; every frozen gate met, held-out `polholdout` included).
> [c6w-polwire.md](c6w-polwire.md): `rang-core calibrate` runs the polcal section's Gpol, KCROSS, Xf and Df
> (CARACal's strategy 1, `rang.cal_pol`), and `rang-core apply` corrects by the parallactic angle
> (`apply.parang`).
> - **Identity:** bit for bit against C6's library chain, on all tables, columns and CORRECTED_DATA, with apply in chunks.
> - **Against CASA:** with CARACal's 3C286 model, the calibrated polcal source matches CASA 6.7.6.14's own chain
>   (`applycal(parang=True)`) to χ 0.003° and p 3e-5 (median). CORRECTED_DATA is within class B on the polcal field
>   and the target, flags exact.
> - **Against the truth:** χ is 0.4-0.6° from the truth (strategy 1's limit with a leaking refant), and p is the
>   truth's 9.5 %, not the model's 9.8 %.
> - **Defaults:** C6's decisions 3-5 are provisional: rang's Df solutions, KCROSS per scan, CASA's estimator. CASA has
>   no data-fraction rule to copy.
> - **Still open:** E2-B fails only on `refant: auto` and `extendflags` (no owner).

**`research/README.md`, index line:**

> [C6w and C7b, polarisation in the commands](c6w-polwire.md): Gpol, KCROSS, Xf, Df and P in `rang-core
> calibrate` and `apply`, bit-identical to `rang.cal_pol`, and the applied calibration against the truth and
> CASA's chain on `poldx` and held-out `polholdout`.

**`research/finish-plan.md`:**
- C6w row: done (this note).
- C7 row: C7b done (this note). The model-to-published comparison repeats C7a's T2: CARACal's constant 9.8 % is 1.2
  points above PB2013 at 1.05 GHz.
- Section 7: add section 7's decisions 1-5 as a new item. They answer C6's decisions 3-5 provisionally and add
  `extendflags` and the in-memory feed angle.
- W3b's row already includes the polarisation terms.

**Merge notes.** This branch edits:
- `core_config.py`, `core_pipeline.py`, `cal_chain.py`, `cal_pol.py` and `applycal.py`. All additive, except:
  - the refusals: C6a-c are gone;
  - the calibrate stage resolves `chain_terms` before restoring flags and writing models;
  - the apply summary has a `parang` key.
- `tests/test_c2e_calibrate.py` and `tests/test_w2_commands.py` (expectations), `docs/cli.md` and `CHANGELOG.md`.

`test_every_note_is_in_the_research_index` fails until the README line is applied.

**Left on disk:**
- `/mnt/d/rang/outputs/c6w-20261106-01` and `-02`: about 1.2 GB each (the prepared MS and its copies). They can go
  after review; `result.json` and the logs are small.
- `-03-gate3` and the check-all logs: small.
- `~/Github/rang/outputs/status/fp-c6w.md`: can go after merge.
- The worktree venv.
