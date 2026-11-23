# DD3b: pinning each facet's flux scale in the DD self-calibration loop

Issue #15, follow-up to [dd3-selfcal-loop.md](dd3-selfcal-loop.md), on
branch `dd3b-pin`. The coordinator decided on 2026-11-23 to test two pins
on the simulation before DD4. Sections 1-4 are frozen 2026-11-23, before any
code that tests them; later changes are dated amendments.

Status: **measured 2026-11-23: neither pin works.** Arm N matches the oracle cycle for cycle, but it pins each facet at the convention (mean |g| = 1), not at the truth (T1 8.6e-3, d2 bright flux 1.025). Arm P fails parity: QuartiCal's DD `phase` does not converge and diverges chaotically after about 20 iterations. Its rang-only variant P′ converges but fails T1 and T3. DD3's unpinned loop (T1 3.89e-3) is better than both (section 5).

## 1. Why

DD3's loop matched QuartiCal and WSClean cycle for cycle. Both arms failed
the truth gate the same way:

- In facet d3, the gain amplitudes rose 2.46 % while the model flux fell
  2.2 %. That is the per-direction degeneracy between `|g|²` and the facet
  model's flux.
- The median gain error was 3.89e-3 against a limit of 3.72e-3, and d3's
  bright source came out at 0.978.

DD3b tests two ways to pin that scale. Each runs in rang (arm R) and in
QuartiCal + WSClean (arm O), with DD3's loop, gates and tolerances
otherwise unchanged.

## 2. Arms (frozen)

**Arm P (CARACal's dE pattern):** phase-only DD solves in cycles 0 and 1
(k = 2), then amplitude and phase (`diag_complex`) in cycles 2, 3 and the
final solve 4.

- **Phase-only on the rang side:** a new `phase` kind of
  `core/src/cal/diag_dd.rs`. It is QuartiCal 0.2.7's `phase` kernel
  (`gains/phase/kernel.py`) with a direction axis:
  - the data are scaled to the summed model's amplitude
    (`absv1_idiv_absv2` on `v = Σ_d G_p,d M_d G_q,d^H`);
  - each direction's residual is normalised by its own `|J|²`;
  - conjugate gradients run on the real 2 × 2 normal equations,
    warm-started;
  - no halving (QuartiCal's `phase` `finalize_update` has none, DD or not);
  - numbness 1e9;
  - parameter flags;
  - parameters referenced per direction to antenna 0.
- **Phase-only on the oracle side:** QuartiCal `G.type=phase`, with
  `G.direction_dependent=true` and the same cap (150, 1e-7, 0.99).

**Arm N (normalised amplitudes):** amplitude and phase in every cycle. Each
solve is followed by a scale per direction,
`g_d ← g_d / s_d` with `s_d` the mean of `|g|` over the direction's
unflagged gains (all intervals, antennas and hands). The scale is applied
after referencing, on both sides by the same Python function: on rang's
gains, and on QuartiCal's gains read from its store. The scaled gains are
the ones written to the H5parm, used in the residual and scored.

The data, start model M₀, grid, facets, shared Högbom rule (DD3 amendment
A1 included), cycle count, H5parm and WSClean settings
(`-feather-size 0`, `<name>-model-pb.fits`) are all DD3's.

## 3. Gates (DD3's, unchanged)

- **L, loop parity, per cycle and arm:** identical component lists, fluxes
  within `1e-5 + 1e-4 |f|`; gain products within 1e-5; equal flags;
  residual within 1e-3 of the peak.
- **T1:** the median relative gain-product error is at most 3.72e-3.
- **T2:** the four bright sources' model flux within 2 %; sources of at
  least 30 mJy within 10 %.
- **T3:** false flux at most 1 %.

Reported, not gated:
- per-direction T1 and amplitude bias (median `|P|/|P_true|`);
- the start model's T;
- in arm N, the truth's own per-direction mean `|g|` (the scale that
  normalising to 1 cannot recover).

## 4. Decision rule (named before any result)

Per arm:

- **Pin works:** L holds and T1-T3 pass.
- **Pin insufficient:** L holds and T fails. Which gate fails, and the d3
  bias, are recorded.
  - In arm N, a bias equal to the truth's own mean `|g|` per direction is
    expected from the convention and is named as such.
- **Parity failure:** L fails. In arm P, a failure in cycle 0 or 1 is a
  failure of the phase-only port and is recorded with the first differing
  quantity.
- **Setup:** a tool refuses an input. Fix it as an amendment before any
  gate is read.

If both arms work, the owner chooses between them for DD4. If one works,
it is the candidate. If neither works, the free scale stays an open
problem for DD4. Pinning it with the start model's catalogue fluxes is the
remaining option, and it is not tested here.

## 5. Measured result

Runs `D:/rang/outputs/dd3b-20261123-{P,Pown,N}` (each with `R/`, and `O/`
for P and N, cycles 0-4, `compare.json`), plus the phase diagnostic
`dd3b-20261123-P/diag-qcp/`.
- Rang is this branch (`0cd2476a`, the worktree's own build). QuartiCal
  0.2.7 and WSClean 3.7 as in DD3.
- Archive: [results/dd3b-flux-pin/](results/dd3b-flux-pin/).

**Arm N (normalised): L passes at every cycle. T fails in both arms with
identical numbers.**

| | cycle 0 | 1 | 2 | 3 | 4 |
| --- | --- | --- | --- | --- | --- |
| components (R = O) | 69 | 102 | 141 | 38 | – |
| max \|ΔP\| gains | 1.6e-6 | 1.2e-6 | 1.4e-6 | 1.3e-6 | 1.2e-6 |
| residual (rel.) | 1.8e-6 | 9.7e-6 | 4.5e-5 | 1.2e-4 | 1.4e-4 |

- **T1:** 8.64e-3. **Fail** (limit 3.72e-3; DD3 unpinned 3.89e-3).
  - Per direction: 6.8e-3, 7.0e-3, 2.6e-2 and 1.1e-2.
- **T2:** bright 1.0055, 1.0064, **1.0247**, 1.0055. **Fail**.
  - Faint sources 1.006-1.055, within the 10 % limit.
- **T3:** 0.41 %. Pass.
- **As section 4 named:** the truth's own mean `|g|` per direction is
  1.0031, 1.0034, **1.0129** and 1.0017.
  - Normalising to 1 puts `|g|²` of d2 1.0129² ≈ 1.026 low. The model
    flux of d2's bright source comes out 1.025 high to compensate.
  - The pin fixes the scale at the convention, not at the truth. Its error
    is the truth's departure from mean `|g|` = 1.
  - After the scale, the solved scales are 1.0003-1.0010, so the loop
    itself barely moves them.

**Arm P (phase-only first, QuartiCal's kernel): L fails at cycle 0. T fails
in both arms.**
- **Cycles 0 and 1:** both codes stop at the 150 cap with a converged
  fraction of 0. The gain products differ by 6.3e-2 at cycle 0 and by 2.0
  at cycle 1. The component lists differ from cycle 0 on (173 against 135).
- **Post hoc diagnostic** (`diag-qcp`: QuartiCal `G.type=phase` on DD1's
  true models at 1, 5, 20 and 150 iterations, against rang's `phase` kind):
  - at 1, 5 and 20 iterations the products agree to 1.3e-15, 9.4e-16 and
    5.0e-15, with equal flags;
  - at 150 they differ by 2.0, with flags differing.
- **So the port is exact.** QuartiCal's DD phase iteration does not
  converge on this layout and amplifies rounding until the two
  trajectories part. A1's last-direction gain is the likely cause:
  - with each direction's own gain (`phase_last_direction_gain=False`) the
    same solve converges in 67 iterations, at a fraction of 0.9925;
  - with QuartiCal's choice it reaches 150 iterations at a fraction of 0.
- **T, final:**
  - R: T1 5.6e-2, bright 0.927-0.979, false flux 14.9 %;
  - O: T1 2.7e-2, bright 0.974-0.996, false flux 8.8 %;
  - all of T1, T2 and T3 fail in both arms.
- **Outcome:** a parity failure under section 4. The cause is the
  oracle's non-converging phase kernel, not the port (exact to 20
  iterations).

**Arm P′ (rang only, each direction's own gain; reported, not gated):**
- the phase cycles converge (67 and 65 iterations);
- T1 1.35e-2 fails (per direction 1.1e-2, 9.1e-3, 1.5e-2 and 1.8e-2);
- T2 passes (bright 0.986-1.012);
- **T3 fails at 11.8 %**: the Högbom rule absorbed the
  phase-only cycles' amplitude errors into spurious components that the
  later amplitude-and-phase cycles did not remove.

**Outcome under section 4.**
- **N:** pin insufficient. Its bias is the convention bias named in
  section 4.
- **P:** parity failure, caused by QuartiCal's DD `phase`.
- **P′:** pin insufficient.
- **Neither pin works**, and the unpinned DD3 loop is closer to the truth
  on T1 than every arm here. The free scale remains open for DD4. The
  catalogue-flux pin (hold the start model's fluxes fixed) is the untested
  option.

**Cost (indicative):**
- rang about 5 min per arm;
- QuartiCal + WSClean about 10 min per arm;
- QuartiCal's phase cycles about 150 s each at the 150 cap (149 s in cycle 0).

## 6. For the coordinator

- Mergeable: the DD `phase` kind of `diag_dd.rs`. It matches QuartiCal to
  5e-15 for as long as QuartiCal's iteration stays bounded, has
  `phase_last_direction_gain` (QuartiCal's default) and is exposed through
  `solve_dd(calmode="p")`. Also mergeable: the arm options of
  `tools/oracles/dd3/dd3.py`.
- Owner decisions:
  - **DD4's flux pin:** the catalogue-flux pin, as a DD3c on the same
    simulation, or accept the unpinned loop (T1 3.9e-3).
  - **Upstream report (not filed):** QuartiCal 0.2.7's DD `phase` uses the
    last direction's gain in every direction's `J^H r`, and on this
    simulation it then does not converge.

## Amendments

**A1, 2026-11-23, setup, before any loop ran (source reading).** QuartiCal
0.2.7's `phase` kernel fills `gains_p[active_term]` inside the direction
loop of `compute_jhj_jhr` (`gains/phase/kernel.py`). After the loop that
variable holds the **last** direction's gains, and it is then passed to
`compute_jhwj_jhwr_elem` for **every** direction, where `J^H r` uses
`-i conj(g)`. So every direction's phase update is computed with direction
`n_dir − 1`'s gain.

- `diag_complex` does not use the gain there, so DD1-DD3 are unaffected.
- With one direction the two agree. A unit test shows the DD `phase` kernel
  then equals rang's DI `phase` solve bit for bit.
- Rang's `phase` kind keeps this behaviour by default
  (`phase_last_direction_gain=True`), so that gate L compares like with
  like. The setting `False` uses each direction's own gain.
- Arm P is run as frozen (QuartiCal's behaviour). A rang-only arm **P′**,
  with each direction's own gain, is added. It is reported against T, not
  gated.
- The upstream report is not filed; that is an owner decision.
