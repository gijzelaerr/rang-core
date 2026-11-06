# C6w and C7b: the polarisation terms in `rang-core calibrate` and `apply`, applied end to end

Tasks C6w and C7b of [finish-plan.md](finish-plan.md) (rows C6w and C7; section 7 items 14 to 17). C6w wires C6's
library ([c6-polterms.md](c6-polterms.md), `rang.cal_pol`) into the commands as that note's "Proposed wiring"
(steps 1 to 5) describes. C7b applies the polarisation solutions end to end on C6's `poldx` truth, with C7a's
3C286 model ([c7a-polmodels.md](c7a-polmodels.md)) on the polcal field, against the truth and against CASA
6.7.6.14's `applycal` of CASA's own chain. Branch `fp-c6w-polwire`, from main `02024bd` (W3 merged).
**Status: protocol frozen (sections 1 to 6); nothing measured yet.**

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
