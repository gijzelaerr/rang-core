<!-- SPDX-License-Identifier: MIT -->
# calwt weights for the other solves (K, G, Gpol, KCROSS, Df)

Task calwt-terms (follow-up of issue #33 and `research/xf-gap.md`).
Status: **proposal, frozen 2026-11-18** before any code, data or solve of
this task. Results go in dated sections below the line.

## 1. Background and what is claimed

xf-gap (section 8) found that CASA 6.7.6.14's `polcal` Xf weights each cell
by the pre-applied tables' `calwt` factor (|G|² times the channel mean of
|B|², per antenna and hand), and rang did not; `calibrate.xf_calwt` (opt-in)
closes the rang-CASA Xf gap but moves rang slightly away from simulated
truth, so it stays off (coordinator decisions, 2026-11-17). This task asks
the same question for rang's other solves that run with tables pre-applied,
under a frozen rule in which **truth decides any default**: matching a
biased oracle is not a gain (`research/e2a-3b-k.md`, coordinator decision 3:
a chain whose oracle may be biased is gated against truth on simulation and
against the oracle with shared upstream terms).

Not claimed: any change of default (every key stays off whatever the
outcome; a default is an owner decision), novelty, any performance gain.
Real data are not read here (no real-data oracle leg; section 8 names it as
the next step if a key earns a default).

## 2. Which solves get a factor (the definition, frozen)

CASA scales weights only where it corrects data (`correct2`/`updateWt2`),
only for scalar and diagonal Jones of type G, T and B (K, KCROSS, X and D
force `calWt` off; `research/c1-calibration-chain.md` 3.2,
`research/c4b-apply-ms.md`). In a solve, tables of a lower VisCal type
correct the data and the others corrupt the model (`cal_gain._pre_apply`,
`TYPE_ORDER = B, K, Kcross, G, J, Df, Xf, ...`). **Definition (frozen):**
the calwt factor of a solve is, per row and correlation (h, h'),
F(p, h) F(q, h'), with F(a, h) the product, over the pre-applied tables
that correct the data (lower type) and are of kind G, T or B, of CASA's
`calcWtScale`: |g(a, h)|² for G and T at the row's time (time-interpolated
as the apply; 1 under a flag), and for B the mean of |B(a, h)|² over the
solution channels unflagged after time interpolation (1 when none;
`rang.applycal._b_scale`'s rule). No "all pre-applied tables" variant is
run. The solves of CARACal's MeerKAT chains
(`research/c1-calibration-chain.md` section 1.5, steps 1-15;
`meerkat-defaults.yml` primary `KGBAKGB`, secondary `KGAKF` with B;
`meerkat-fullStokes-continuum-defaults.yml` primary `KGB`, secondary `GAF`
with K, B; polcal strategy 1):

| Solve (CARACal step) | Pre-applied | Lower, weight kinds | Factor |
| --- | --- | --- | --- |
| K, fcal (1) | – | – | none (no key needed) |
| G, fcal (2) | K | K (forced off) | 1: structural no-op |
| B, fcal (3) | K, G | none (B is the lowest type) | 1: structural no-op |
| K2, fcal, second round (4) | G, B | B | mean\|B\|² |
| G2, fcal, second round (4) | K2, B | B | mean\|B\|² |
| B2, fcal, second round (4) | K2, G2 | none | 1: structural no-op |
| Kg, gcal (5, 7) | B | B | mean\|B\|² |
| Gg, gcal (6) | Kg, B | B | mean\|B\|² |
| Gpol, xcal (12) | K, G, B | B (G is not lower than G) | mean\|B\|² |
| KCROSS, xcal (13) | K, G, B, Gpol | B | mean\|B\|² |
| Xf (14) | K, G, B, Gpol, KCROSS | B, G | done in xf-gap (`xf_calwt`) |
| Df, fcal (15) | K, G, B, KCROSS, Xf | B, G | \|G\|² mean\|B\|² |

F (fluxscale's gcal G) is not keyed here. B has no key: the factor is 1 by
definition; it is a control (C1).

## 3. Keys (implementation, frozen before the code)

New `calibrate` keys, bool, default false, out of the stage hash at their
default (`HASH_DEFAULTS`, as `xf_calwt`), each enabling the factor for one
solve type: `k_calwt` (K), `g_calwt` (G, calmode ap or p; not F),
`gpol_calwt` (Gpol), `kcross_calwt` (KCROSS), `df_calwt` (Df).
- The factor is a Rust kernel (`core/src/cal/apply.rs`, through
  `ffi_apply.rs` and the extension): per row and correlation from the packed
  lower tables, with per-(antenna, time) scales computed once per unique
  time; memory O(rows × 4 + times × antennas × 2), no cell-sized
  allocation (the bound xf-gap's open item asks for).
- It enters `cal_gain._Field.prepare` (K, G) and `cal_pol._PolField.prepare`
  (Gpol, KCROSS, Df) after the SIGMA reset and before the row weights (so
  the solution TIME centroid uses the scaled weights, as `xf_calwt` and
  CASA's `aggregateTimeCentroid` on solve weights), `model_divided`,
  `phase_only` (`casa_phase_weights`), frequency and time averaging: every
  load path, chunked or whole.
- `xf_calwt` keeps its Python path unchanged (byte-identical); a test
  compares it with the kernel on an Xf case.
- Keys off: byte-identical tables and stage hash (tests; the quick check's
  gain-hash gate).

## 4. Hypotheses (per key)

- **H-K** (`k_calwt`; K2, Kg): with B pre-applied, weighting the
  B-corrected data by mean|B|² brings rang's K nearer CASA's on shared
  upstream tables, and nearer truth with noise (the corrected data's noise
  is σ/|B_p B_q|, so the factor is the right weight up to its channel mean).
- **H-G** (`g_calwt`; G2, Gg): as H-K for G.
- **H-Gpol** (`gpol_calwt`): as H-K for Gpol (phase-only).
- **H-Kc** (`kcross_calwt`): as H-K for the cross-hand delay.
- **H-Df** (`df_calwt`): as H-K for the leakage, factor |G|² mean|B|².
- **Structural no-ops** (G, B, B2): any key on leaves their tables
  byte-identical (control C1).

## 5. Data

`simtruth_ms generate poldx` (16 antennas, 256 channels, small schedule
`FXGTGTGXGTGTGXGTGTGTGXF`: fields J1939-6342, 3C286-SIM, SIM-GCAL,
SIM-TARGET), FEED −90° in CASA's copy (`sim_chi.SET_FEED`),
`feed_angle_rotation: -90` in rang, as xf-gap.

- **Noisy sets (thermal noise as generated, σ per component as the design;
  RFI as generated).** Seeds `--seeds s0,s0+1,s0+2,s0+3` (jones, sky, rfi,
  noise); checked against every value in `rang.simtruth.SEEDS` (115
  values, computed families included) and a repository grep: no clash.
  - development: **D1** s0 = 20261881;
  - **held-out: H1-H4**, s0 = 20261891, 20261901, 20261911, 20261921, read
    once, after the scripts that score them are committed.
  - On every copy, before any solve on either side, FLAG is set to the
    generator's RFI mask (`<name>.rfi_mask.npz`, `any`), so both sides
    solve on the same unflagged cells; if a design writes no RFI, FLAG is
    left as written. truth.npz (raw and `casa_gauge` terms) is the truth.
- **Noiseless sets** of xf-gap (`dev`, `held`, `held4`; default seeds and
  20261751-4, 3C286-SIM 4 or 90 × 8 s): already read by xf-gap with this
  weighting for Xf, so **development data here**; used for the oracle read
  only (no truth.npz on noiseless generations), and only for the misfit
  terms (Gpol, KCROSS, Df), since noiseless K and G fit their exact model
  under any weighting. CASA's Gpol rows are counted on every CASA arm
  (coordinator decision): a dropped interval is logged and Gpol is compared
  on the intervals both sides have.

## 6. The chains (rang and CASA, frozen)

One chain that contains every keyed solve in its CARACal context (a union
of the two MeerKAT configurations above; `solint inf`, `combine ''` unless
stated; refant m000; `uvrange >150` except K; `minsnr 3`,
`minblperant 4`; `average_time` false; `data.weights: uniform`):

- fcal (J1939-6342, model Stevens-Reynolds 2016): K; G (ap) [K]; B [K, G];
  K2 [G, B]; G2 (ap) [K2, B]; B2 [K2, G2].
- gcal (SIM-GCAL, unit model `smodel [1,0,0,0]`): Kg [B2]; Gg (ap) [Kg, B2].
- xcal (3C286-SIM, nrao 3C286 / CASA manual setjy as `sim_chi`): Gpol
  (p, 60s, parang) [K2, G2, B2]; KCROSS [+ Gpol]; Xf (combine scan)
  [+ KCROSS]; Df on fcal (combine scan, clip ±0.6) [K2, G2, B2, KCROSS, Xf].
- interp linear except KCROSS and Xf `nearest` (as `sim_chi`).

CASA: the same calls in 6.7.6.14 (`rang-o-casa:6.7.6.14` under WSL docker
on glacier, `examples/oracle_pol.py tasks`), `sim_chi.casa_calls`' settings
for the terms it has, `gaincal` / `bandpass` for K2, G2, B2, Kg, Gg; a copy
of the MS after `setjy` (`model.ms`) for the shared-upstream reads.

**Arms.** rang `off` (all keys off), one arm per key with that key alone on
(`k`, `g`, `gpol`, `kcross`, `df`), `all` (the five keys and `xf_calwt`);
CASA `casa`. On every noisy set; on the noiseless sets `off` and `casa`.

## 7. Measures

**Shared-upstream oracle read (S).** For each keyed solve T: rang's T
solved as the pipeline solves it (`cal_chain._solve_one` /
`_solve_pol` with the pipeline's terms, xf-gap's harness), on CASA's
`model.ms`, with CASA's tables for every term before T, key off and on,
against CASA's T. Per set, median over antennas (refant excluded),
hands, intervals and channels where both are unflagged of:
K2, Kg |Δτ| (ns); G2, Gg |g_r/g_c − 1|; Gpol |arg(g_r/g_c)| (deg);
KCROSS |Δτ_c| (ns); Df |q_r − q_c| with the gauge-free q_pq = d_x,p +
conj(d_y,q), p ≠ q. Controls G, B, B2 likewise (off only, and on = off).

**Truth read (T), noisy sets.** On each rang arm's own chain (and CASA's,
reported), against truth.npz:
- **C_F, C_G, C_X** (parallel hands, fcal, gcal, xcal): per baseline p < q,
  hand h, channel ν and scan (the scan's middle integration), r =
  P_rang / P_truth with P = J_p,h J_q,h* the composite of the applied terms
  (fcal: K2, G2, B2; gcal: Kg, Gg, B2; xcal: K2, G2, B2, Gpol; evaluated by
  `rang.cal_apply.apply` on unit cells, `corrupt`), truth P from raw K, B, G.
  r is divided by its complex median over baselines and hands per (scan,
  channel), which removes what the model leaves free (gcal's unit model);
  E = median |r/r̃ − 1| over unflagged cells.
- **C_XH** (cross hand): arg of the KCROSS × Xf composite over the truth's
  in CASA's gauge (`casa_gauge` kcross × xf) per channel, minus its circular
  mean; E = median |·| (deg).
- **C_D**: median over p ≠ q and channels of |q_rang − q_truth|, q as above,
  truth in CASA's gauge.

Per key the gating composites: `k`, `g`: C_F and C_G; `gpol`: C_X;
`kcross`: C_XH; `df`: C_D. Every other composite of every arm is reported.

## 8. Controls and decision rule (frozen)

**Controls** (each before any number of section 7 is read for a key; a
failure stops that key's reads and is recorded):
- **C0:** keys off: byte-identical solves and stage hash (tests: each
  solver with the key absent and false; the stage hash of a configuration
  without the keys) and the quick check's gain-hash gate (archived
  outputs of `main`).
- **C1:** with every key on, the tables of G, B, B2 (fcal) are
  byte-identical to `off`'s on every set.
- **C2 (harness):** the harness with rang's own tables (read back) on the
  `off` arm's calibrate-only MS reproduces each keyed term's table within
  1e-6 relative (gains), 1e-6 ns (delays), 1e-6 (leakage) on D1 and `dev`.
- **C3:** CASA's Gpol row count against rang's on every CASA arm, logged.
- **C4:** the Rust factor equals `applycal`'s weight scale product and
  `xf_calwt`'s `calwt_factor` to 1e-6 relative on a test case without
  solution flags (tests).

**Oracle outcome per keyed solve** (S, key on against off, on H1-H4;
the noiseless sets are reported only): **O+** if the median
over sets of on ≤ 0.8 × that of off and on < off in at least all but one
set; **O−** if off ≤ 0.8 × on likewise; otherwise **O0**.

**Truth outcome per key** (T on H1-H4, mean over the four sets of E,
paired on against off): **T+** if for at least one gating composite on ≤
0.8 × off with on < off in ≥ 3 of 4 sets, and for none off ≤ 0.8 × on;
**T−** if for any gating composite off ≤ 0.8 × on with off < on in ≥ 3 of
4 sets; otherwise **T0** (within 20 %, a tie, as e2a-3b-k).

**Outcomes per key (every one named):**
1. **T+** (any O): the key is nearer truth: a default candidate for the
   owner (needs a real-data oracle leg with shared upstream terms first,
   e2a-3b-k decision 3). The default stays off here.
2. **T0 with O+**: a CASA-equivalence switch, like `xf_calwt`: stays
   opt-in, documented.
3. **T0 with O0 or O−**: null: the key stays opt-in, documented as no
   effect at these SNRs.
4. **T−**: further from truth: stays off; recorded with its O.
5. **T+ with O−** is read as outcome 1 with CASA's estimator named as the
   biased one, as e2a-3b-k's K1.
A control failure (C0-C4) is outcome **X** for the affected keys: no
outcome is read for them until a dated amendment.

**Reported, not gating:** the `all` arm against `off` and CASA on every
composite; the noiseless sets' S reads for K2, G2, Kg, Gg; each key's effect
on the downstream composites; CASA's composites against truth.

**Cost:** wall time per arm from the shared runs (heavy lock, 4 slots,
not exclusive): reported, labelled not a timing; no cost claim.

## 9. Records

Host glacier (this Windows host, 16 threads, 63 GB), shared heavy lock
(`~/Github/rang/tools/heavy_lock.py run --slots 4 --mem 12`; no exclusive
or timing run, so no 21:00 window is needed), no GPU. CASA in WSL docker.
Run root `D:\rang\outputs\calwt-terms-20261118\`. Scripts in
`research/results/calwt-terms/` (imports `sim_chi`, `xf_preavg` and
xf-gap's harness unchanged where they fit); compact receipts in
`research/results/calwt-terms/receipts/`; status in
`outputs/status/calwt-terms.md`; wall times in `research/tool-timings.md`.
Order: note (this commit) → keys and tests → scripts → development reads
(D1, `dev`) → controls → held-out reads (H1-H4, then `held`, `held4`) →
Measured result.

---

(Results below this line, dated.)

Keys and tests committed in `d27f84b`; the measurement script
`research/results/calwt-terms/calwt_terms.py` before any held-out set was
generated.

## 10. Amendment, 2026-11-18 07:30 (after the development reads D1 and `dev`, before any held-out set was generated)

- **C1 as frozen cannot hold for B2 in a chain.** B2 is solved after K2
  and G2, so with `k_calwt` or `g_calwt` on it moves with them (D1: G and
  B byte-identical in every arm; B2 differs in `k`, `g`, `all` only). C1
  is read as: (a) in the chains, G and B byte-identical to `off` in every
  arm; (b) in the shared-upstream harness (identical inputs), G, B and B2
  solved with every key on byte-identical to off. Both are the structural
  no-op the note means.
- **Reported, not gating (post hoc):** C_XH after a fit of a constant and
  a slope in frequency (xf-gap's truth measure). On D1 rang `off` and
  CASA share a −0.024 ns slope against the truth (residual after the fit
  0.07°), which makes C_XH (constant only) about 2° on both sides; C_XH
  stays the gating measure as frozen.
- The harness solves a term with every key on (`cal_chain.CALWT_TYPES`);
  only that term is solved, so this is its own key.

## 11. Measured result (2026-11-18, glacier)

Code `74e3bb0` (keys `d27f84b`); run root `D:\rang\outputs\calwt-terms-20261118\`
(18 GB with the MS copies); receipts `research/results/calwt-terms/receipts/`
(`results.json` from `summarise.py`, `score-<set>.json`, `calwt_terms.log`).
Seeds as section 5 (H1-H4 s0 = 20261891, 20261901, 20261911, 20261921; D1
20261881). Every step rc 0; held-out sets generated and read once.

**Controls.** C0: keys off byte-identical (tests `tests/test_calwt_terms.py`;
quick check below). C1 (amendment 10): G and B byte-identical to `off` in
every arm of every set; G, B and B2 with every key on byte-identical to off
in the harness on every set. C2: the harness reproduces the pipeline's K2,
Kg, G2, Gg, Gpol, KCROSS and Df byte-identically on D1 and `dev`. C3: CASA's
Gpol rows equal rang's on D1, H1-H4 and `held4` (64); CASA drops intervals
on noiseless `dev` (48 of 64) and `held` (656 of 768), reported only. C4:
the kernel equals `xf_calwt`'s factor and the cell-level |G|² mean|B|² to
1e-6 relative (tests).

**Oracle read (S, shared CASA upstream, H1-H4; median per set, then over
sets; ratio on/off).**

| Key | Solve | off | on | on/off | O |
| --- | --- | --- | --- | --- | --- |
| `k_calwt` | K2 | 2.79e-4 ns | 2.79e-4 ns | 0.999 | O0 |
| `k_calwt` | Kg | 8.20e-4 ns | 8.18e-4 ns | 0.997 | O0 |
| `g_calwt` | G2 | 2.71e-6 | 4.36e-7 | 0.161 | O+ (4/4) |
| `g_calwt` | Gg | 4.59e-6 | 8.16e-7 | 0.178 | O+ (4/4) |
| `gpol_calwt` | Gpol | 4.28e-3° | 4.32e-3° | 1.009 | O0 |
| `kcross_calwt` | KCROSS | 1.24e-4 ns | 4.86e-6 ns | 0.039 | O+ (4/4) |
| `df_calwt` | Df (gauge-free) | 1.48e-4 | 1.37e-5 | 0.093 | O+ (4/4) |

Noiseless sets (reported): the same pattern for KCROSS (`held` 7.6e-5 →
5.1e-6 ns, `held4` 8.3e-5 → 2.5e-6) and Df (`held` 6.7e-7 → 2.7e-7,
`held4` 4.9e-6 → 1.1e-6); K2, Kg, G2, Gpol unchanged there (exact model).

**Truth read (T, H1-H4, mean of the per-set medians; off → on, sets
with on < off).**

| Key | Composite | off | on | on/off | T |
| --- | --- | --- | --- | --- | --- |
| `k_calwt` | C_F / C_G | 1.0530e-3 / 3.2207e-3 | 1.0530e-3 / 3.2207e-3 | 1.000 / 1.000 | T0 |
| `g_calwt` | C_F / C_G | 1.0530e-3 / 3.2207e-3 | 1.0531e-3 / 3.2222e-3 | 1.000 / 1.0004 (1 of 4) | T0 |
| `gpol_calwt` | C_X | 1.5612e-3 | 1.5605e-3 | 0.9996 (4 of 4) | T0 |
| `kcross_calwt` | C_XH | 1.4536° | 1.4587° | 1.0035 (1 of 4) | T0 |
| `df_calwt` | C_D | 3.4118e-3 | 3.4029e-3 | 0.9974 (4 of 4) | T0 |

Reported: the `all` arm (five keys and `xf_calwt`) C_F 1.0530e-3, C_G
3.2222e-3, C_X 1.5604e-3, C_XH 1.4709°, C_XH after constant and slope
0.0874° (off 0.0898°), C_D 3.401e-3; CASA's chain C_G 3.781e-3, C_XH
1.4706°, fit 0.0929°, C_D 3.251e-3. rang and CASA share a per-set
cross-hand slope against truth (−0.005 to 0.044 ns), the leakage bias of
solving KCROSS and Xf before Df. Full chain against CASA (mean over H1-H4,
`off` → `all`): KCROSS 2.09e-4 → 1.78e-4 ns, Df 1.46e-4 → 1.52e-5, G2 and Gg
unchanged at 2.3e-4 / 3.0e-4 (upstream K differences dominate there).

**Outcomes (section 8):** `g_calwt`, `kcross_calwt` and `df_calwt`:
**outcome 2**, a CASA-equivalence switch (CASA's gaincal G, KCROSS and
polcal Df weight by the pre-applied tables' calwt factor; with the key
rang moves 5.6-26× nearer CASA on shared inputs) with no truth difference
at these SNRs. `k_calwt` and `gpol_calwt`: **outcome 3**, null (rang moves
by < 1 % against CASA: CASA's K and phase-only Gpol estimators do not show
the weighting, or are not sensitive to it here). No key is nearer truth
(T0 everywhere, every change < 0.5 %); **every default stays off**.

**Cost (shared lock, 4 threads, not a timing):** rang chain arm 6.0-6.3 s
with or without the keys on the noisy sets (19.6 s on `held`); CASA chain
37-38 s (106 s on `held`).

**Not checked:** real data (no shared-upstream real-data leg); B and F
(no key); the factor's effect with `average_time` or `average_freq` on;
the CASA mechanism for K and Gpol (whether CASA applies the factor there
and it does not matter, or does not apply it) was not separated.
