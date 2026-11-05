# C1: the calibration chain rang-core will implement

Task C1 of [finish-plan.md](finish-plan.md), written 2026-11-05 on branch `fp-c1-chain` from main `a81999b`.
**Status: proposed specification, frozen for C2 to C7 once the coordinator merges it. Nothing here is implemented. No new measurement was made;
every number comes from an earlier report named beside it.** Tolerances are proposals for C2 to C7. The acceptance protocol's tolerances belong to A0
(`research/a0-acceptance.md`, not yet written when this was frozen).

Three findings change what the plan assumed:

1. **CARACal's order is delay, gain, bandpass (K, G, B), not delay, bandpass, gain.** G is solved with K applied and B with K and G applied. The cross-hand order is delay, phase, then leakage.
2. **CARACal's shipped self-calibration is not phase then amplitude.** Its configs use CubiCal `Fslope`, a delay self-calibration. C5 as planned would not match it, and no CubiCal oracle exists here. Owner decision 1, section 8.
3. **`fluxscale` is on the chain.** O-CASA skipped it only because its slice had one field. Any acceptance set with a separate secondary runs it.

## 0. Provenance

Inspected for this report, not recalled. The sources are in the ignored `outputs/c1-sources-20261105/`.

| Source | Version | Local path under that folder |
| --- | --- | --- |
| CARACal workers, schemas, sample configs, `nrao_xcal.yml`, `pks1934-638.lsm` | master `8f7bb363876f5f0daecbf2167c36bb597c7e5160` | `caracal-8f7bb363/` |
| QuartiCal gain terms, config schema | 0.2.7, from image `rang-formats-oracle:20261030` (`sha256:6ddf0359…`) | `quartical-0.2.7/` |
| CASA C++ sources | third-party mirror `dic-case-studies/casa6` `9269a52` (2023-01-18). **Older than the oracle.** | `casa6-mirror/` |
| CASA Python tasks (signatures, `task_polcal.py`, `task_applycal.py`) | casatasks 6.7.6.14 in image `rang-o-casa:6.7.6.14` (`sha256:24822b40…`) | read in the image |

Labels used below:

- **[M]** read in the 2023 mirror, so to be confirmed against 6.7.6.14 by that term's gate.
- **[T]** read in the 6.7.6.14 Python tasks.
- **[C]** read in CARACal at the pinned commit.
- **[Q]** read in QuartiCal 0.2.7.
- **[measured: report]** measured earlier in that report.

## 1. The sequence

### 1.1 Measurement equation and conventions

Linear feeds, correlations row-major `XX, XY, YX, YY`, as `core/src/jones.rs`. Per baseline `pq`, time `t`, channel `ν`:

```
V_pq = J_p M_pq J_q^H        J_p = B_p K_p G_p D_p X_p P_p
```

- `M_pq` is the model coherency in the sky frame (`XX = I+Q`, `YY = I−Q`, `XY = U+iV`, `YX = U−iV`, so `(XX+YY)/2 = I`, which is how O-CASA read `setjy`).
- The factor order is CASA's `VisCal::Type` enum, `B, K, G, J, D, X, C, P, E, T, F` (`VisCal.h:62`) [M]. `VisEquation::setapply` sorts by that key, and `correct2` applies from the left, so B first [M].
- While solving a term, DATA is corrected by every applied term of lower type and MODEL is corrupted by every applied term of equal or higher type (`VisEquation::collapse2`) [M].
- `KCROSS` has type K (`KcrossJones : KJones`) [M], so it sits **before** D, not beside X. Ties between K and KCROSS do not matter because both are diagonal.
- `P` is applied whenever `parang=True`. `polcal` always adds it (`mycb.setapply(type='P')`, `task_polcal.py`) [T].

### 1.2 CARACal's configurations differ; C1 covers the union

A0 owns the choice. The term list below covers all three [C]:

| Setting | Schema examples (the defaults when a config is silent) | `meerkat-defaults.yml` (`meerkat-continuum-defaults.yml` has the same crosscal steps) | `meerkat-fullStokes-continuum-defaults.yml` |
| --- | --- | --- | --- |
| `refant` | `auto` | `'0'` | `auto` (not set) |
| `uvrange` | `>50` | `>150` | `>150` |
| `set_model` | point (`meerkat_skymodel: False`) | `meerkat_skymodel: true` | `meerkat_skymodel: true` |
| primary `order` | `KGB` | `KGBAKGB` | `KGB` |
| primary `solint` | `120s, 120s, inf` | `inf, inf, inf, –, 60s, 60s, inf` | `inf, inf, inf` |
| primary `combine` | `'', '', scan` | `'', '', '', –, '', '', scan` | `'', '', ''` |
| secondary `order`, `apply` | `KGAF`, `B` | `KGAKF`, `B` | `GAF`, `KB` |
| secondary `solint` | `120s, inf, –, 120s` | `inf, inf, –, inf, inf` | `inf, –, inf` |
| `polcal` | not run unless configured | absent | on: `xcal` + `fcal`, `feed_angle_rotation: -90`, `extendflags: true`, `gain_solint: 60s`, `time_solint: inf`, `uvrange: >150`, `nrao_model: true` |
| `selfcal` | `Fslope, Fslope`, `gsols_timeslots: 2`, `cal_niter: 2` | `gsols_timeslots: [120]`, `cal_timeslots_chunk: 240` | `Fslope, Fslope`, `gsols_timeslots: [4]`, `cal_timeslots_chunk: 4`, `cal_niter: 2` |
| `prep.specweights` | `uniform` when enabled | `uniform` | `uniform` |

The `calmode` entry for K is ignored: the worker passes `calmode` only for G and F (`do_KGBF`) [C]. `uvrange` reaches G, F, B and every polcal solve, but not K [C].

### 1.3 The frozen term list

"Solve axes" are antenna, time, frequency and polarisation. Reference antenna `r`. All Jones matrices are 2×2.

| # | Term | Jones form | Solve axes | Reference and gauge | Solution interval |
| --- | --- | --- | --- | --- | --- |
| T0 | Model, flux scale (`setjy`) | none; sets `M_pq` | per row, channel | absolute | none |
| T1 | **K** delay | `diag(exp(2πi τ_x (ν−ν₀)), exp(2πi τ_y (ν−ν₀)))`, `ν₀ = CHAN_FREQ[nchan//2]` of the table's window [M; measured: dfio-formats] | antenna; time per `solint`; one per window; X and Y | `τ_r = 0`, r not flagged; each hand separately | as config (1.2) |
| T2 | **G** gain, `calmode='ap'` | `diag(g_x, g_y)` | antenna; time; one per window; X and Y | per solution and hand, all antennas divided by `g_r/|g_r|`; flex or strict | as config |
| T3 | **B** bandpass | `diag(b_x(ν), b_y(ν))` | antenna; one per `solint`, `combine`; per channel; X and Y | as G, per channel; `solnorm=False`; `fillgaps=70` | as config |
| T4 | **A** flag on corrected calibrator | none; flags | see section 5 | none | none |
| T5 | **F** secondary gain and flux transfer | as G, appended to a **copy** of the primary G; then `fluxscale` rescales | antenna; time; X and Y | as G; scale from `reference=fcal` | as config, `smodel=[1,0,0,0]` |
| T6 | **P** parallactic angle | `[[cos a, sin a], [−sin a, cos a]]`, `a = q + RECEPTOR_ANGLE` [M] | per time; not solved | none; CARACal sets RECEPTOR_ANGLE to −90° on both receptors | per row |
| T7 | Polarised calibrator model (`setjy` manual) | none; sets `M_pq` | per row, channel | absolute | none |
| T8 | **Gpol** `calmode='p'` on xcal | `diag(e^{iφ_x}, e^{iφ_y})` | antenna; `gain_solint`; one per window; X and Y | as G, `parang=True` | `60s`, `combine=''` |
| T9 | **KCROSS** cross-hand delay | `diag(exp(2πi τ_c (ν−ν₀)), 1)`; one value for the array | one per `time_solint`; one per window; X only | no antenna reference; depends on the `r` of T1 to T8 | `inf`, `combine=''` |
| T10 | **Xf** cross-hand phase | `diag(x(ν), 1)`, `|x| = 1`; one value for the array | `time_solint`, `combine=scan`; per channel | CASA forces refant to none; depends on the `r` of T1 to T8 | `inf`, `combine=scan`, `preavg=300` default |
| T11 | **Df** leakage on an unpolarised calibrator | `[[1, d_x(ν)], [d_y(ν), 1]]`, applied linearised | antenna; `time_solint`, `combine=scan`; per channel | subtractive: `d_x,p −= d_x,r`, `d_y,p += conj(d_x,r)`, so `d_x,r = 0` (`applyRefAnt`, `case D`) [M] | `inf`, `combine=scan` |
| T12a | **Sd** self-cal delay and offset (CARACal's `Fslope`) | `diag(exp(i(φ_x + 2π τ_x (ν−ν₀))), same for y)` | antenna; time per `gsols_timeslots`; whole band | QuartiCal `reference_params`; CubiCal's not read | timeslots, config |
| T12b | **Sp** self-cal phase | `diag(e^{iφ_x}, e^{iφ_y})` | antenna; time; frequency chunks | as G | configurable |
| T12c | **Sa** self-cal amplitude and phase | `diag(g_x, g_y)` | antenna; time; frequency chunks | as G | configurable |

**Solve sequence (frozen).** Each row solves one term with the listed tables pre-applied. This is CASA-style sequential calibration: **no joint solve of a chain of terms**, because CARACal has none.

| Step | Field | Solve | Pre-applied, with `interp` | Model |
| --- | --- | --- | --- | --- |
| 0 | fcal | T0 | – | `setjy` or `.lsm` |
| 1 | fcal | K | – (or last G, B in a second round) | as step 0 |
| 2 | fcal | G | K `linear` | as step 0 |
| 3 | fcal | B | K, G `linear` | as step 0 |
| 4 | fcal | A, then steps 1 to 3 again if the order has a second round | last other terms (`get_last_gain` excludes the term being solved) | as step 0 |
| 5 | gcal | K (if in the order) | B from fcal | `smodel=[1,0,0,0]` |
| 6 | gcal | G | K, B | `smodel=[1,0,0,0]` |
| 7 | gcal | A, K again if ordered | K, G, B | `smodel=[1,0,0,0]` |
| 8 | gcal | F, then `fluxscale(reference=fcal, transfer='')` | K, B | `smodel=[1,0,0,0]` |
| 9 | all | Apply K, G or F, B to calibrators | section 3 | – |
| 10 | – | Set RECEPTOR_ANGLE (T6); extend flags on xcal and fcal (`flagdata mode=extend`, `growtime=80`, `growfreq=80`, `growaround`, `flagnearfreq`, `flagneartime`, `ntime=60s`, `combinescans`) | – | – |
| 11 | xcal | T7 | – | manual polarised |
| 12 | xcal | Gpol (T8), `parang=True` | crosscal tables | T7 |
| 13 | xcal | KCROSS (T9), `parang=True` | crosscal, Gpol `linear` | T7 |
| 14 | xcal | Xf (T10); then `flagdata tfcrop` on the Xf table (section 5) | crosscal, Gpol `linear`, KCROSS `nearest`; `P` | T7 |
| 15 | fcal | Df (T11); then clip the table to `[−0.6, 0.6]` | crosscal, KCROSS `nearest`, Xf `nearest`; `P`; **not Gpol** | T0 |
| 16 | all | Apply with `parang=True` | section 3 | – |
| 17 | target | Image with GeMClean, write `MODEL_DATA` (G6) | – | – |
| 18 | target | Sd or Sp, then Sa, `cal_niter` rounds; each solves `CORRECTED_DATA` against `MODEL_DATA` | none (data already corrected) | `MODEL_DATA` |

Steps 10 to 16 are CARACal's strategy 1, `xcal_model_fcal_leak`, which is the only one the full-Stokes sample config runs [C]. With `pol_calib: none`, steps 12 to 14 drop out and Df is solved alone (`calib_only_leakage`) [C]; this falls out of the same code.

### 1.4 The solve of each term, as an equation

Weights are `WEIGHT_SPECTRUM` where it exists (`w`). `R` is data corrected by lower terms; `M'` is the model corrupted by higher terms.

- **T1 K (CASA).** Per baseline to `r` only and per parallel hand, FFT the 8× zero-padded weighted spectrum, take the peak with parabolic refinement, delay = `(peak − N/2)/N/Δν` [M]. Not a network solve. `τ_r = 0`. **K (rang, proposed):** the same FFT as the initial estimate (`K.initial_estimate` in QuartiCal is this method on the reference baselines [Q]), followed by QuartiCal's `delay` Gauss-Newton over all baselines. It meets QuartiCal exactly, and CASA within the K tolerance. If the owner wants CASA's estimator instead, that is one flag on the kernel.
- **T2 G.** `min Σ w |R − g_p M' g_q^*|²` on parallel hands; `phandonly` zeroes the cross-hand weights. CASA pre-averages (the `normalizable` terms use full `preavg` when it is negative), divides by the model, adjusts the weight by `|M|²` (`divideCorrByModel`), averages in frequency and then runs `VisCalSolver2` with its chi-squared stop [M; measured: l5c-casa-gaincal]. Post-solve: `applySNRThreshold`, `minsnr=3`; `minblperant=4`; then `applyRefAnt` [M]. QuartiCal's `diag_complex` solves the same objective without pre-averaging [Q].
- **T3 B.** T2's objective per channel; then flagged channels up to 70 wide are filled by interpolation and unflagged (`fillChanGaps`, in the table) [M].
- **T5 F.** T2, with `fluxscale` (`SolvableVisJones::fluxscale`) [M, read in part]: per secondary field, the scale is the mean over antennas of the ratio of its gain amplitudes to the reference's, after median-based cuts. `S_field = 1/scale²`, and the amplitudes of the secondary's table are divided by the scale. C2 fixes the exact weighting from the source and the gate.
- **T8 Gpol.** T2 with `apmode='P'`: `enforceAPonData` divides each datum by its amplitude and multiplies its weight by `amp²` [M].
- **T9 KCROSS.** All baselines, one FFT of the sum `w₁ V_XY + conj(w₂ V_YX)` over baselines, per channel normalised by `Σw`, 8× padded; parabolic peak; the delay goes into the X parameter of all antennas [M]. `phandonly` is false. The cross hands are divided by the polarised model first when the term is `normalizable`; C6 confirms this for KCROSS.
- **T10 Xf.** Per channel `x(ν) = (Σ w̄ V_XY + conj(Σ w̄ V_YX)) / |…|`, `w̄ = (w_XY + w_YX)/2`, where both cross hands are unflagged, over all baselines [M]. `XJones` is `normalizable`, so data are divided by the corrupted model first (`VisEquation.cc:536`) [M]. A closed form: it needs no iteration.
- **T11 Df.** `VisCalSolver2` on the cross hands with the linearised model: `V_XY,pq − M_XY = d_x,p M_YY + conj(d_y,q) M_XX`, and likewise for YX [M]. For an unpolarised source X and P cancel from the model, since `X P I P^H X^H = I`, so the term does not depend on them. Rang: QuartiCal's `leakage` kernel [Q] followed by CASA's subtractive reference; the problem is linear, so its unique solution modulo the gauge in section 2.1 is reached whichever kernel is used.
- **T12.** QuartiCal `delay_and_offset`, `phase`, `diag_complex` kernels [Q], one term at a time. Gains are clipped to `[0.5, 2.0]` in amplitude (`cal_gain_cliplow`, `cal_gain_cliphigh`), and solutions on baselines shorter than `minuvw_m` are not used, as CARACal passes them [C].

**Solution intervals (semantics, frozen).** Times are CASA's `solint`: `inf` (to the scan boundary, across it with `combine='scan'`), `int` (each integration), or seconds. CASA's second-based bins are not a fixed grid: `16s` gave times up to 8 s off the pair centres and `12s` gave 21 bins for 16 pairs, and a solution's `TIME` is its weighted centroid of unflagged data [measured: l5c-casa-gaincal, smokes 1 and 2]. So:

- `solint` maps to a row-to-bin table computed in Python (Rust only sees `time_bin`, as `solve.rs` does).
- The grouping rule is ported from CASA's iterator and gated on CASA's own rows and times in step 3 (section 6).
- `gaincal` ignores a frequency part in `solint` for G and T [measured: l5c, smoke 1]. A frequency chunk (T12b, T12c) is therefore rang's own option and has no CASA equivalent.
- A time-bin grid matched to the oracle uses L5-C's method: relabel `SCAN_NUMBER` on a copy and pass `solint='inf'`.

**Reference antenna, frozen.** `refant` is a name or index; a list is allowed. `refantmode='flex'` is CASA's default and CARACal strategy 1's; `strict` is implemented too. Flex follows `applyRefAnt`: keep the phase continuous with the alternate used last when `r` is flagged [M]. The same `r` must be used for every term from T1 to T11, because the X-Y phase of `r` is what T9 and T10 absorb. `refant: auto` is CARACal's rule (within `maxdist`, all baselines at least `minbase`, sorted by flagged fraction) [C]. Where that rule returns nothing, rang **refuses with a clear error**: CARACal instead logs an error and passes `refant=''`, and then K stops [measured: o-casa].

## 2. Oracles

### 2.1 What each comparison compares, and the gauge

| Term | QuartiCal 0.2.7 | CASA 6.7.6.14 | Gauge-free quantity compared |
| --- | --- | --- | --- |
| T0 | – | `setjy` | absolute, per row, channel |
| T1 K | `delay` | `gaincal(gaintype='K')` | `τ_p,a − τ_r,a`, one hand at a time. **Pivots differ:** QuartiCal `(min+max)/2` [Q], CASA `CHAN_FREQ[nchan//2]`. They do not change `τ`, but the raw K phases differ by a constant, which the next term absorbs: compare applied products only after G. |
| T2 G, T8, T12c | `diag_complex` (0.2.7 references it to `solver.reference_antenna` [Q]) | `gaincal(gaintype='G')` | parallel-hand baseline products `g_p,a conj(g_q,a)`, observed pairs, as L5-C. Same `r` on both: phases directly as a check. |
| T3 B | `diag_complex`, `freq_interval=1` | `bandpass` | products per channel. Per channel the phase has a free constant per hand. |
| T5 F | `diag_complex` on each field | `gaincal` + `fluxscale` | amplitudes are not gauge-free across fields only by the scale; compare `fluxd` per field and the scale factor. |
| T6 P | `parallactic_angle` term (no solver) as a second reading | `applycal(parang=True)`, no tables | absolute: the angle `a` per row. |
| T9 KCROSS | **none: CASA only** | `gaincal(gaintype='KCROSS', parang=True)` | `τ_c`, absolute given the same `r`. No QuartiCal term fits a delay on the cross hands. Second check: simulated truth. |
| T10 Xf | `crosshand_phase` with **`solve_per=array`** | `polcal(poltype='Xf')` | absolute per channel, given the same `r`. Compare the composite `arg[k_c(ν) x(ν)]` so that a different KCROSS split does not count; report `x(ν)` too. QuartiCal's form is the same, `diag(e^{iφ}, 1)` [Q]. |
| T11 Df | `leakage` | `polcal(poltype='Df')` | For an unpolarised calibrator, one complex number per channel is free: `d_x,p + z`, `d_y,q − conj(z)`. The gauge-free quantities are `d_x,p + conj(d_y,q)` and `d_y,p + conj(d_x,q)` per baseline. Also compare the tables after both are referenced by CASA's subtractive rule. |
| T12 Sd, Sp, Sa | `delay_and_offset`, `phase`, `diag_complex` | not CARACal's tool. **CubiCal is CARACal's oracle and it is not in any image here, so QuartiCal is a substitute**, labelled so. | products; applied per cell. Simulated truth. |

Gains on one side only are excluded. A flag difference is **reported, not gated**, within a factor of 2 of `minsnr` or at `minblperant`, because the SNR calculation is the solver's own. Elsewhere flags must agree.

### 2.2 The actual calls

All in existing images, under O-CASA's container conventions (`--user`, `--network none`, `--tmpfs /tmp`, `OMP_NUM_THREADS=4`, inputs read-only). Python tasks in `/opt/casa` of `rang-o-casa:6.7.6.14`; QuartiCal in `/opt/qc` of `rang-formats-oracle:20261030`. Parameters not listed take the 6.7.6.14 defaults (`minsnr=3`, `minblperant=4`, `refantmode='flex'`, `solnorm=False`); `polcal` has `preavg=300` and `combine='obs,scan'` unless set [T]. Solve-time settings below are CARACal's, and the configuration chosen by A0 overrides `solint` and `uvrange`.

```python
# CASA, in order (settings from crosscal_worker.py and polcal_worker.py at 8f7bb363)
setjy(vis, field=F, standard='manual', fluxdensity=S, reffreq=REF, spix=SPIX, scalebychan=True, usescratch=True)
gaincal(vis, K, field=F, gaintype='K', solint=SK, combine=CK, refant=R, spw='', scan='')
gaincal(vis, G, field=F, gaintype='G', calmode='ap', solint=SG, combine=CG, uvrange=UV, refant=R,
        gaintable=[K], interp=['linear'], gainfield=[F])
bandpass(vis, B, field=F, bandtype='B', solint=SB, combine=CB, solnorm=False, fillgaps=70, uvrange=UV, refant=R,
         gaintable=[K, G], interp=['linear', 'linear'], gainfield=[F, F])
# secondary (order KGAF, for example)
gaincal(vis, Kg, field=GC, gaintype='K', smodel=[1, 0, 0, 0], gaintable=[B], gainfield=[F], interp=['linear'], ...)
gaincal(vis, Gcopy, append=True, field=GC, gaintype='G', calmode='ap', smodel=[1, 0, 0, 0], uvrange=UV, ...)
fluxscale(vis, caltable=Gcopy, fluxtable=Ftab, reference=F, transfer='')
applycal(vis, field=FLD, applymode='calflag', gaintable=TABLES, interp=['linear'] * n, gainfield=FIELDS,
         calwt=[False], parang=False, flagbackup=False)
# polarisation (strategy 1; CARACal first writes RECEPTOR_ANGLE = -90 deg on both receptors of a copy)
flagdata(vis, mode='extend', field=X, ntime='60s', combinescans=True, growtime=80.0, growfreq=80.0,
         growaround=True, flagnearfreq=True, flagneartime=True, flagbackup=False)
setjy(vis, field=X, standard='manual', fluxdensity=[14.7172], spix=[-0.4507, -0.1798, 0.0357], reffreq='1.47GHz',
      polindex=[0.098], polangle=[0.575959], rotmeas=0.0, usescratch=True)              # 3C286, nrao_xcal.yml
gaincal(vis, Gpol, field=X, gaintype='G', calmode='p', solint='60s', combine='', parang=True, uvrange=UV, refant=R,
        gaintable=CC, gainfield=CCF, interp=CCI)
gaincal(vis, Kc, field=X, gaintype='KCROSS', solint='inf', combine='', parang=True, uvrange=UV, refant=R,
        gaintable=CC + [Gpol], gainfield=CCF + [''], interp=CCI + ['linear'])
polcal(vis, Xf, field=X, poltype='Xf', solint='inf', combine='scan', refant=R, uvrange=UV,
       gaintable=CC + [Gpol, Kc], gainfield=CCF + ['', ''], interp=CCI + ['linear', 'nearest'])
flagdata(vis=Xf, mode='tfcrop', ntime='60s', combinescans=True, datacolumn='CPARAM', usewindowstats='both', flagbackup=False)
polcal(vis, Df, field=F, poltype='Df', solint='inf', combine='scan', refant=R, uvrange=UV,
       gaintable=CCL + [Kc, Xf], gainfield=CCLF + ['', ''], interp=CCLI + ['nearest', 'nearest'])
flagdata(vis=Df, mode='clip', clipminmax=[-0.6, 0.6], datacolumn='CPARAM', flagbackup=False)
applycal(vis, field=FLD, gaintable=CC + PC, gainfield=..., interp=..., calwt=CW, parang=True)   # applymode '' = calflag
```

`CC` holds the crosscal tables from CARACal's callib for xcal, `CCL` the same for the leakage calibrator; `PC` is `[Gpol, Kc, Xf, Df]` with `Gpol` on xcal only and `calwt=[True, False, False, False]`.

```bash
# QuartiCal: one term per process, on a copy whose data column holds CASA's pre-corrected data for
# that term; on CASA's table grid via the L5-C SCAN_NUMBER relabelling when intervals must match.
goquartical input_ms.path=$MS input_ms.data_column=$PRE input_ms.weight_column=WEIGHT_SPECTRUM \
  input_model.recipe=$MODEL solver.terms=[T] solver.iter_recipe=[$N] solver.reference_antenna=$R \
  solver.convergence_criteria=1e-7 solver.robust=false mad_flags.enable=false output.flags=false \
  dask.threads=1 solver.threads=1 dask.scheduler=single-threaded $TERM
#   K   T.type=delay T.time_interval=$t T.freq_interval=0 T.initial_estimate=true
#   G   T.type=diag_complex T.time_interval=$t T.freq_interval=0
#   B   T.type=diag_complex T.time_interval=0 T.freq_interval=1
#   Xf  T.type=crosshand_phase T.solve_per=array T.time_interval=0 T.freq_interval=1 input_model.apply_p_jones=true
#   Df  T.type=leakage T.time_interval=0 T.freq_interval=1
#   Sd  T.type=delay_and_offset T.time_interval=$t T.freq_interval=0
#   Sp  T.type=phase T.time_interval=$t T.freq_interval=$f
#   Sa  T.type=diag_complex T.time_interval=$t T.freq_interval=$f
```

The base flags are rang's archived command (`history/python/flagging_workflow.py`). QuartiCal is used only as a **single-term kernel oracle** here; its joint chain is not on the frozen sequence.

**Versions to watch.** QuartiCal 0.2.8-dev moves results (#452, fixed in rang by `qp_weights=transposed`, measured to 1.2e-15 in RV1) and references `complex` by default. The oracle stays 0.2.7 until RV3 reports otherwise, and new-term kernels should be read once more against the release if it appears before C2 merges.

## 3. Interpolation, apply and tables

### 3.1 CASA's apply, as rang will do it

| Item | Rule | Source |
| --- | --- | --- |
| Order | Sort by type: B, K (and KCROSS), G, D, X, P. Each term corrects `V ← J_p⁻¹ V J_q⁻ᴴ`. | [M] |
| Time `linear` | Per (antenna, window): amplitude and tracked phase in float32, times relative to `floor(t₀−1)`; nearest slot outside the range; the flag of either bracketing slot flags the result. | `caltable.py`; [measured: dfio-formats] |
| Time `nearest` | The slot whose float32 relative time is closest, tie to the earlier; that slot's value and flag. The tie rule is untested. | [measured: l5c-casa-gaincal] |
| Frequency, no `flag` suffix | Flagged solution channels are **bridged, not flagged**; per float parameter over unflagged channels, phase unwrapped, nearest beyond the first and last unflagged channel, linear between, GHz abscissae. An entirely flagged parameter stays flagged. | `CTPatchedInterp::resampleInFreq`; [measured: dfio-formats] |
| `interp='nearest'` | Nearest in time; `linear` in frequency when frequency matters. | `applycal` docstring [T] |
| K | Evaluated in every data channel with the caltable's pivot. Time-interpolated in float32. | [M; measured: dfio-formats] |
| Df | Linear approximation: `XY −= d_x,p YY + conj(d_y,q) XX`, `YX −= d_y,p XX + conj(d_x,q) YY`; parallel hands unchanged; a flagged parameter flags all four. Dflls is a General Jones with a full inverse (strategies 2 and 3, not in this list). | `caltable.py` |
| Xf, KCROSS | Diagonal with `1` on Y. CASA's flagging of a diagonal term flags only the correlations of the flagged receptor. Xf flags are a per-channel array flag. | [M]; C6 gate |
| P | Rotation; never flags. | [M] |
| Field map | `gainfield=''`: every field in the table. A name: that field. `nearest`: the sky-nearest field in the table per MS field (a unique nearest) [M]. CARACal's apply to a target uses `nearest` for the secondary's tables and the flux calibrator for B [C]. | [M], [C] |
| `applymode='calflag'` | Writes CORRECTED_DATA and FLAG. `calflagstrict` also flags where no table covers the data. No flags are removed. | [M] |

**Cell values under a flag.** `caltable.correct` leaves the cell without this term's division where the term is flagged. I did not establish whether DF-IO's gates covered the values of flagged cells. C4 adds a gate on them, because downstream tools read them.

**Failed solutions.** A flagged or absent slot: `linear` flags rows between it and a neighbour; `nearest` flags rows mapped to it; `calonly`-style passing through is not used. A chunk for which `gaincal` wrote no table is not an error in CASA, which returns normally [measured: o-casa, arms D to F]. **Rang refuses:** a solve that writes no solutions is an error, naming the step, so the failure does not surface later at apply.

### 3.2 What is written

- **CORRECTED_DATA.** Starts from DATA (`setVisCubeCorrected(visCube)`) and is complex64 [M]. Written in full for the selected fields and channels; `applycal` with a channel selection writes only those channels [measured: l5c, smoke 4]. W1 owns the column write.
- **FLAG.** OR of the old and new flags. `FLAG_ROW` is untouched by this path; C4 records what CASA does to it. Original flags stay recoverable (`formats/flagversions.py`, W1).
- **WEIGHT, WEIGHT_SPECTRUM.** `correct2` first calls `resetWeightsUsingSigma()` in memory, but weights are **written only if `calwt` is true**, and then, with spectrum weights, `WEIGHT` becomes their channel-axis median [M]. With `calwt=False` (crosscal) they stay as they were. With `calwt=True`: `w_ab ← w⁰_ab s_p,a s_q,b`, where `w⁰` comes from SIGMA and `s` is the term's weight scale, for scalar and diagonal Jones only (`updateWt2`), and K, X and D force `calWt` false [M]. Gpol's amplitude is 1, so `calwt=True` on it leaves only the reset, which is why this needs a measurement. **C4 gate:** on an input where `WEIGHT ≠ 1/SIGMA²`, measure WEIGHT and WEIGHT_SPECTRUM written by `applycal` with `calwt` false and true.
- **`prep.specweights: uniform`** in the MeerKAT default and full-Stokes configs sets `WEIGHT_SPECTRUM` to 1 before crosscal [C]. Rang: a config option `weights: as_is | uniform`, recorded in the receipt; which is the default is A0's for the matched arm and the owner's for release.
- **Self-calibration.** CARACal splits the target into a new MS, so its DATA is 1GC-corrected, then CubiCal writes CORRECTED_DATA [C]. Rang works in place (finish line, item 2). 1GC-corrected data go into a new column `CORRECTED_1GC` **(proposed)**, and T12 solves that column against `MODEL_DATA`; `CORRECTED_DATA` then holds `S_p⁻¹ CORRECTED_1GC S_q⁻ᴴ`. This puts S after P, which CASA's type order cannot express, so T12 is applied as a separate stage and its tables record that. Target flags and memory follow W1 and W3.

### 3.3 Table formats

Through `formats/caltable.py` and `core_ms_write.create_caltable`, as F1 verified. Main columns for all: `TIME` (weighted centroid), `FIELD_ID`, `SPECTRAL_WINDOW_ID`, `ANTENNA1`, `ANTENNA2` (reference, −1 for none), `INTERVAL`, `SCAN_NUMBER`, `OBSERVATION_ID`, the parameter column, `PARAMERR`, `FLAG`, `SNR`, `WEIGHT` (undefined). Keywords `ParType`, `MSName`, `VisCal`, `PolBasis`, `CASA_Version`. Subtables `OBSERVATION`, `ANTENNA`, `FIELD`, `SPECTRAL_WINDOW`, `HISTORY`.

| Term | `VisCal` | Column, per row | `ANTENNA2` | Window in the table | Supported now? |
| --- | --- | --- | --- | --- | --- |
| K | `K Jones` | `FPARAM` `(1, 2)`, ns | r | one channel | yes |
| G, Gpol, Sp, Sa | `G Jones` | `CPARAM` `(1, 2)` | r | one channel | yes |
| F | `G Jones`, after `fluxscale` | as G, several fields | r | one channel | yes in format; `fluxscale` is new |
| B | `B Jones` | `CPARAM` `(nchan, 2)` | r | per channel | yes |
| KCROSS | `Kcross Jones` | `FPARAM` `(1, 2)`, second parameter 0 | to read from CASA's table | one channel | **no** |
| Xf | `Xf Jones` | `CPARAM` `(nchan, 1)` by `nPar` [M]; to confirm | −1 expected | per channel | **no** |
| Df | `Df Jones` | `CPARAM` `(nchan, 2)` | r | per channel | yes |
| Sd | `K Jones` plus `G Jones` (offset) **(proposed)**, so that CASA can read it | – | r | – | format exists |

Sp and Sa with frequency chunks have no CASA `G` form; they are written as `B Jones` on a chunked window (**proposed**). The first task touching a type must add a read-write gate against a table CASA itself made (F1's *CT-read*, *CT-write-identity*). `TYPES = ("B", "K", "G", "D", "T")` in `caltable.py` extends additively to `B, K, G, D, X, T`. T9 and T10 write `PolBasis` as CASA writes it.

## 4. Reuse

**Unchanged, as is.**

- `core/src/solve.rs`: `solve_complex`, `Problem`, `Settings`, `Options`, the Anderson and stop options. Rang's chain does not use it unless a user asks for a full `complex` term. It stays the archived comparator.
- `core/src/jones.rs`, `core/src/correct.rs`.
- `python/rang/fluxstd.py`: PB2010, SR2016, Reynolds and `manual` for Stokes I, at 0 ulps from `setjy` in MODEL_DATA on L-band [measured: fs1-flux-standards], so T0's point models need only a row writer.
- `predict_components` for the `.lsm` route: Stokes I, `(row, chan)`.
- `formats/caltable.py`: `read`, `write`, `from_gains`, `jones_terms`, `correct`, kept as the tested Python reference for the new Rust kernel. `rang.measures` as a reference for P. `rang.formats` Tigger reader for `pks1934-638.lsm` (196 rows, Gaussians and up to `spi3`).

**New Rust (proposed, one file per concern under `core/src/cal/`).**

| Module | Contents | Licence source |
| --- | --- | --- |
| `cal/apply.rs` | Corrupt and correct a chunk by a list of per-antenna terms; diagonal, GenLinear and rotation; flags and weights. Time and frequency interpolation from `caltable.py` | rang |
| `cal/diag.rs` | `diag_complex`, `phase`, `amplitude` kernels; intervals from `time_bin`, `freq_bin` | Translation of QuartiCal (MIT notice kept, as `solve.rs`) |
| `cal/delay.rs` | FFT estimate; `delay`, `delay_and_offset` | QuartiCal (MIT) |
| `cal/crosshand.rs` | KCROSS FFT, Xf closed form; `solve_per=array` | Written from the equations in 1.4; CASA is not copied |
| `cal/leakage.rs` | `leakage` kernel; CASA's subtractive reference | QuartiCal (MIT) |
| `cal/reference.rs` | `applyRefAnt` flex and strict rule; `minsnr`, `minblperant` post-solve; `fillgaps` | Written from the rule in 1.4 |
| `cal/parang.rs` | Parallactic angle closed form, no IERS | rang |

**New Python.** `core.solve_term`, a chain driver, config, tables; orchestration only.

**Keeping the archived comparators bit-identical (frozen rule).**

1. New terms go in new modules. No edit to `solve.rs`, `jones.rs`, `correct.rs` or to `core.solve_complex`'s signature, default or `RANG_SOLVE_OPTIONS` handling. A diff touching them is a review stop. Shared helpers are copied or moved only by a separate commit with the gate below.
2. **Gate on every C-stream merge:** the core's gains hash to `4ed2aa89…` (core K `original`, slice) and `7b370c13…` (L5's D, fixture), and the core-phase2 criteria hold (LUNO 0.9833234067897558 converged fraction, 389/43/592 rank survey). Add them to `tools/check-all.sh` if a replay does not yet run there, with the fixtures it needs.
3. `caltable.correct` keeps its output for its existing tests. New types add branches; existing ones stay byte-for-byte in behaviour.
4. The Rust `apply` kernel must agree with `caltable.correct` on F1's CT-synthetic cases before it replaces it in any live path; research chains keep their own.

## 5. What is left out of CARACal's sequence

**Left out or replaced (with reasons). Few, and stated in the E3 report.**

| # | Item | Treatment | Reason |
| --- | --- | --- | --- |
| O1 | `A`: `flagdata tfcrop` on the corrected calibrator (`flag.col: corrected`, `timecutoff=4`, `freqcutoff=3`) | **Replaced** by the Tricolour port (`core_flag.flag_rows`) on CORRECTED_DATA of the field, at the same place in the order | The finish line's flag oracle is Tricolour; no tfcrop port exists. It is a real difference: tfcrop on O-CASA's slice added 1.49 % of unflagged cells against Tricolour's first pass at 0.14 % [measured: o-casa], so E3 reports the flagged fractions per step. |
| O2 | `flagdata tfcrop` on the Xf table | **Left out, on a measured condition.** C6 runs CASA's chain with and without it on the polarised calibrator. If corrected Q and U change beyond T10's tolerance, this comes back as a task. | Same missing tfcrop. A CASA-side flag on solutions; bridging fills the gaps. |
| O3 | Strategies 2 and 3 (`xcal_model_xcal_leak`, `xcal_from_pa_xcal_leak`: `Dflls`, `Xfparang+QU`, `polfromgain`) | Left out; rang refuses `leakage_calib: xcal` | The full-Stokes sample config runs strategy 1, and the plan requires an unpolarised calibrator. They need parallactic coverage and a QU fit. |
| O4 | `freqsel`: `Xref`, `Dref` | Left out; schema default off | Not used in the shipped configs. |
| O5 | CubiCal `madmax` flags (`flag_madmax: True`, thresholds `0, 10`) in self-calibration | Left out for v0.2.0; the fraction of cells CARACal flags is reported in E3 | QuartiCal's `mad_flags` were not ported (core-phase2). Port only if E3 shows it matters. |
| O6 | Meqtrees as a calibrator; CubiCal `Gain2x2`, second matrix, `cal_bjones` | Left out | Off by default. Direction-dependent and 2×2 self-calibration are outside the finish line. |
| O7 | `b_smoothwindow > 1`, `reuse_existing_gains`, `scanselection` | Smoothing refused (default 1). Reuse is W2's resume. Selection through config. | Not shipped except `reuse_existing_gains`. |
| O8 | Splitting (`transform`, `mstransform`) and on-the-fly apply; `fixvis` | Left out: rang writes in place and does not rephase | Finish-line item 2. A0 sets the same averaging by input, if any. |
| O9 | Crystalball UHF model; the `0408` local model (the schema says it is not well tested) | Left out | UHF is outside the finish line. The L-band `pks1934-638.lsm` is kept. |
| O10 | `ragavi` plots, `flagstats`, HTML reports, `inspect` worker, `aimfast` | Left out | Diagnostics only; receipts replace them. `aimfast`, when on, can stop self-calibration early; whether a shipped config turns it on is for A0 to read. |
| O11 | Direction-dependent calibration (`ddcal`), `mosaic`, `line` | Left out | Outside the finish line. |
| O12 | `set_model_leakage` when the leakage calibrator has a separate MS | Not needed | Rang works on one MS, so MODEL_DATA persists. |

**Kept, though easy to overlook:** the local `.lsm` model of 1934−638 (`meerkat_skymodel: true` in the MeerKAT default and full-Stokes configs, though O-CASA used the point model); the copy of primary G for `F`; `extendflags`; `Df` clip; `fillgaps`; `uvrange`.

**Known hazards inherited, not fixed by copying.** The `get_last_gain` table order depends on string hashing, which is harmless for diagonal terms [measured: o-casa]. CARACal's `polangle` and `rotmeas` are constant in frequency; its model is a statement of its own, and the angle gate (C7) uses it and also reports against the published value A0 names.

## 6. Order of implementation

Every step is separately mergeable, with its tolerance written into its own note before the first comparison. "Slice" is O-CASA's four-station 1934−638 slice (present, about 0.75 GB). "Array" is 56 stations of the same observation, about 4.9 GB fetched per 16 tiles. Sizes are estimates.

**Tolerance classes (proposed):**

- **A, same algorithm as QuartiCal:** flags exact; entries and products ≤ 1e-6; iterations equal; as core-phase2, which measured about 1e-15.
- **B, CASA's estimator differs:** products median ≤ 5e-4, p95 ≤ 2e-3, relative; held-out parallel-hand MSE within 1e-4 relative, reported as both ratio and sign. Basis: CASA G against the core on matched intervals gave 4.9e-4 / 2.0e-3 on the fixture and 7.5e-5 / 2.1e-4 on the slice, with held-out differences of +1.23e-4 and +7.6e-5 [measured: l5c-casa-gaincal]. Both sides are diagonal here, so these should be easier than L5-C's; the outer limit stays at the worse measured set. A max is reported, not gated, since 1.6e-2 occurred on underconstrained intervals.
- **C, apply:** per cell ≤ 1e-6 relative, or ≤ 11 float32 epsilons of the cell's largest correlation; flags exact [measured: dfio-formats, up to 10.3].
- **T, simulated truth, A1's data:** noise-free, products within 1e-5. With noise, per-term median error at most 3 standard errors of the expected thermal error, so that no bias shows.

| Step | Plan task | Scope | Data | Done when (proposed) | Heavy? |
| --- | --- | --- | --- | --- | --- |
| 1 | C3a | T0: point and `manual` Stokes I written to MODEL_DATA; `.lsm` through `predict_components` | Slice MS; 1 small simulated MS | Point and manual: **0 ulps** from `setjy` on 1934−638 as FS1. `.lsm` against Crystalball 0.4.3 (`/opt/sky`) on the same converted list: ≤ 1e-6 of the peak per cell. | no |
| 2 | C4a | `cal/apply.rs`: chunks corrected and corrupted by K, G, B, Df, interpolation, flags. Needed by C2's pre-apply, so **it precedes C2**; W1 is needed only for step 7 | F1's five tables, slice | **Class C** against `applycal` and against `caltable.correct`. Throughput recorded. | no |
| 3 | C2a | `cal/diag.rs`, `reference.rs`; G, `solint` bins, `uvrange`, `minsnr`, `minblperant`, flex and strict | Slice, fixture, simulated 16 antennas × 256 channels × 60 integrations (about 60 MB) | **A** against `diag_complex`; **B** against `gaincal`. Bin edges and solution times equal CASA's table rows on `inf`, `60s`, `120s`. Refant-flagged cases on simulated data equal CASA. | yes |
| 4 | C2b | `cal/delay.rs`; K | Slice (delays ±0.011 ns [measured: o-casa]), simulated with delays up to ±50 ns | **A** against `delay`. CASA `K`: `|Δτ|` median ≤ 0.01 ns, about 1.5° at the band edge, p95 ≤ 0.03 ns. **T**. | yes |
| 5 | C2c | B, `fillgaps`, chain K, G, B | Slice, whole array for one scan (about 9 GB as an MS, under `/mnt/d/rang`) | **A**, **B** per channel. Applied chain against arm C of O-CASA: **B** on the composite products. Flags of filled channels equal CASA's. | yes |
| 6 | C2d | F, `fluxscale`, secondary order, Tricolour step (O1) | A secondary: LUNO 1830−211 or A0's data; simulated two-field | `fluxd` per field within 1e-3 relative of `fluxscale`; scale factors within 1e-3. | yes |
| 7 | C4b | `applycal` to an MS, CORRECTED_DATA, FLAG, weights gate (3.2), target by `nearest`; tables CASA can read | Needs W1. Slice, simulated two-field | **C**, on flagged cells too; WEIGHT behaviour for `calwt` both ways equals CASA's. | no |
| 8 | C6a, C7a | P: `cal/parang.rs`, RECEPTOR_ANGLE handling. Polarised `manual` model: Q, U, V rows | Simulated polarised; 3C286 field in LUNO if A0 confirms | Angle against `applycal(parang=True)` with no tables, `DATA/CORRECTED`: ≤ 1e-3 rad, the frame fixed first (open check, section 8). Model: per-channel ≤ 1e-6 of `|I|` from `setjy`. | no |
| 9 | C6b | Gpol, KCROSS, Xf; table types, `extendflags` with its flags gate | Simulated with known `τ_c`, `x(ν)`, then a polarised calibrator scan (about 1 to 5 GB) | Gpol: **B**, phase median ≤ 0.1°. KCROSS: `|Δτ_c|` ≤ 0.02 ns against CASA; **T**. Xf: composite phase median ≤ 0.5°, p95 ≤ 2° per channel against CASA, **A** on `crosshand_phase` per channel with `solve_per=array`. `extend` flags equal `flagdata`'s. O2's measurement. | yes |
| 10 | C6c | Df, clip | Simulated; 1934−638 scan | Gauge-free combinations: median `|Δ|` ≤ 1e-3, p95 ≤ 5e-3 against CASA (leakage magnitudes about 0.006 [measured: o-casa]). **A** against `leakage`. **T**. | yes |
| 11 | C7b | Full apply with `parang=True` | Polarised calibrator; held-out scan | **C** against `applycal`. Then calibrated 3C286: fractional polarisation and angle against `nrao_xcal.yml` (9.8 %, 33°) within limits **A0 sets**. Unpolarised 1934−638: residual cross-hand power reported. | no |
| 12 | C5a | Sp, Sa, gain clip, in-place stage, solint config | Needs G6. Simulated truth with a gridded model | **A** against `phase`, `diag_complex`; **T**, gains recovered; a round on a perfect model leaves the data unchanged within **C**. | yes |
| 13 | C5b | Sd, as owner decision 1 sets | Same | **A** against `delay_and_offset`; **T**. CubiCal not compared, stated in the report. | yes |

Plan reorder needed: C4's kernel (step 2) goes before C2, and C3 stays first. See "For the coordinator".

## 7. Risks a later task should watch

- **Refant continuity feeds polarisation.** A flex change of refant shifts X-Y phase for the rows that use it, and Xf assumes it is constant. C6 reports how many solutions used an alternate. If there are any on the xcal scan, it should report the impact rather than hide it. CARACal's strategy 3 passes `refantmode='strict'`; strategy 1 does not.
- **CASA's K FFT is a local estimator.** On strongly flagged bands a sidelobe wins, and its failure mode differs from Gauss-Newton's. A mismatch against CASA there is not proof of a rang error; simulated truth decides.
- **`setjy` `spix` is log10** [measured: o-casa]; `nrao_xcal.yml` passes its coefficients the same way. Strategy 2's own use of `numpy.log` in `normfreq` is a different reading [C], one more reason to leave it out.
- **The 40-60 × thermal floor** on the pilot may mask polarised-chain errors in E2, as the plan states.

## 8. What only the owner can decide, and open checks

**Owner decisions.**

1. **Self-calibration term (blocks C5 only).** CARACal ships `Fslope` (delay self-cal) through CubiCal, while the plan says phase then amplitude. Options:
   - (a) rang's default is Sp then Sa as the plan says, with Sd available, and E3 states that the arms differ. **Proposed.**
   - (b) rang's default is Sd, to match CARACal.
   - Either way QuartiCal substitutes for CubiCal as the oracle, unless the owner wants a CubiCal image added.
2. **Whether O1 (Tricolour for tfcrop inside crosscal) stands.** It keeps the plan's flag oracle, but it is the largest departure from CARACal in the chain.
3. **The K estimator.** Proposed: FFT then Gauss-Newton, to agree exactly with QuartiCal and within tolerance with CASA. The alternative is CASA's FFT alone.

**For A0, not the owner.** Which of the three configurations is the matched CARACal arm; `weights: as_is | uniform`; whether LUNO's 3C 286 scan satisfies the polarisation data requirement. `flagging-luno-candidate.md` lists 3C 286, 1934−638 and 1830−211, and O-CASA's FIELD table has `J1331+3030`. I did not check how many 3C 286 visibilities exist, whether the store's flags and processing allow it, or its parallactic coverage.

**Open checks, for the named step.**

- **P's frame (step 8).** E2 found casacore `AZEL` uses the geocentric horizon and `AZELGEO` agrees with astropy to ≤ 1.3″; rang's frozen convention is geodetic with astropy. Which one `vb.feedPa` uses in CASA 6.7.6, and whether it is per antenna, is **not established**. The gate's value decides. If it is the geocentric frame, parity with CASA needs it, and that differs from `rang.measures`' convention by up to about 0.2°.
- **The MeerKAT sign and feed conventions (steps 8 and 11).** CARACal overwrites RECEPTOR_ANGLE with −90° for both receptors. ESO137's FEED table already holds −π/2 on both, not an orthogonal pair [measured: b1-2-identifiability]. How this reconciles with QuartiCal's `feed_flip` and `parallactic_angle` terms was not worked out here; for WSClean's reading of Stokes after derotation, see G9. The 3C286 angle at step 11 is the deciding test. Rang applies the angle from its config, records it in the receipt, and changes the FEED table only on request (**proposed**).
- **KCROSS and model division (step 9).** `XJones` is `normalizable`; whether `KcrossJones` is, and the exact row-level use, is not established.
- **`fluxscale`'s exact weighting and cuts (step 6).** Read only in part.

## 9. What was not checked

- **Nothing was run.** No CASA, QuartiCal or rang solve; only a version check in the images and fetching sources.
- **The CASA C++ is from a 2023 mirror.** Everything marked [M] is unconfirmed for 6.7.6.14 until its gate passes. Earlier reports found it right for K, G, B, T and Df apply.
- **CubiCal's sources and `f-slope` form were not read.** T12a's equation is QuartiCal's `delay_and_offset`, and whether it equals `f-slope` is a working assumption.
- CARACal's selfcal worker was read only at its calibration calls (2,574 lines; imaging, masks and PyBDSF were skimmed). `flag_worker` and `inspect` were not reread here.
- Sizes and per-step data estimates are estimates. `a0-acceptance.md` did not exist yet, so nothing here is reconciled with A0.

## For the coordinator

Do not apply until merged. All text below is proposed.

**`research/STATE.md`, new top entry:**

> C1, 2026-11-05 (specified; nothing implemented, nothing measured). [c1-calibration-chain.md](c1-calibration-chain.md) freezes the calibration chain for C2 to C7, read from CARACal `8f7bb363`, QuartiCal 0.2.7 and CASA's sources. CARACal's order is K, G, B (with `fluxscale` for a secondary), then Gpol, KCROSS, Xf, Df, parallactic angle, then self-calibration. Its shipped self-calibration is CubiCal `Fslope`, not phase then amplitude (owner decision). QuartiCal has no cross-hand delay term, so KCROSS has CASA as its only oracle. Twelve items of CARACal's sequence are left out or replaced, with reasons. Thirteen mergeable steps.

**`research/README.md`, index line:**

> [C1, the calibration chain](c1-calibration-chain.md): the frozen term list, order, equations, oracles, gauge handling, apply rules and implementation steps for C2 to C7.

**`research/finish-plan.md`, proposed edits:**

- C1 row: done, link this report.
- Section 4: "C4's Rust apply kernel (C1 step 2) comes before C2, because C2 pre-applies tables; C4's write-back part stays after C2 and W1."
- C2 row: add "F and `fluxscale`" and the order K, G, B.
- C5 row: "phase, then amplitude" stays only if owner decision 1 is (a); name QuartiCal as a substitute oracle.
- C6 row: "cross-hand delay, cross-hand phase, leakage; parallactic angle throughout".
- Section 7: add C1's owner decisions 1 to 3.

**For A0:** choose among the three CARACal configurations in section 1.2; decide `weights`; name the published 3C286 values and C7's limits; check LUNO's 3C 286 scan. C1's per-term tolerances do not replace A0's.

**Not removed.** `outputs/c1-sources-20261105/` (sources, about 1 MB, ignored by git) should stay for C2 to C7, or be fetched again from the commits named in section 0. `outputs/status/fp-c1.md` can go after merge.

**Timing.** Three source fetches and two short `docker run --rm` version and file checks. No tool run worth a row in `tool-timings.md`.
