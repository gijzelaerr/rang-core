# DD3b: pinning each facet's flux scale in the DD self-calibration loop

Issue #15, follow-up to [dd3-selfcal-loop.md](dd3-selfcal-loop.md), on
branch `dd3b-pin`. The coordinator decided on 2026-11-23 to test two pins
on the simulation before DD4. Sections 1-4 are frozen 2026-11-23, before any
code that tests them; later changes are dated amendments.

Status: **proposed**.

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

Not yet measured.

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
