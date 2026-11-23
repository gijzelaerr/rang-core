# DD4b: the DD loop on ESO 137-006 with a raised iteration cap, an extended start model and DI0 as the baseline

Issue #15, follow-up of [dd4-eso137.md](dd4-eso137.md) (DD4). Branch
`dd4-eso137`. Owner decisions 2026-11-23, relayed by the coordinator.
Sections 1-4 are frozen 2026-11-23, before the code that runs them; later
changes are dated amendments. Section 3's d1 test is post hoc: its guess
came from DD4's provisional numbers.

Status: **proposed.**

## 1. What changes from DD4, and what stays on record

- **Cap:** DD4's frozen cap of 150 iterations stopped every DD solve with a
  converged fraction of 0.25, which is the pinned direction d0 only. Here
  the cap is **500** (stop criterion 1e-7 and fraction 0.99 unchanged).
- **Baseline:** **DI0** is frozen here as the DI baseline. It is one
  direction, pinned, so the gains stay at the publisher's DI calibration,
  and only the deconvolution loop runs (DD4 amendment A3). DD4's frozen DI
  arm (one free direction) diverged and stays on record as diverged; it is
  not used here.
- **Unchanged:** the data subset, catalogue, directions d0-d3, facets,
  pins, grid, minor cycle, five major cycles plus a final solve, the PSF
  and every measure of DD4 section 5.
- DD4's runs (R and DI0 at cap 150, run `D:/rang/outputs/dd4-20261123/run-02`)
  stay on record unchanged. New arms are written to the same run root
  under new names.
- **No oracle.** Arm O is blocked by DD4 A4's failed facet-imaging control.
  So everything here is rang only, not checked against QuartiCal and WSClean,
  and no DD gain is claimed from it.

## 2. Arms

| Arm | Directions | Cap | Start model |
| --- | --- | --- | --- |
| **R500** | d0-d3, d0 pinned (as DD4 R) | 500 | M₀ (DD4 section 4) |
| **DI0** | one, pinned (DD4 A3, already run; the cap does not act on a pinned direction) | – | M₀ |
| **R500x** (post hoc, section 3) | d0-d3, d0 pinned | 500 | M_x |
| **DI0x** (post hoc, section 3) | one, pinned | – | M_x |

**M_x, the extended start model:** DI0's model entering its final cycle
(`DI0/cycle-4/model.npy`, DD4 run-02). It is M₀ plus every clean component
DI0's minor cycles 0-3 found, including ESO 137-006's extended emission
deconvolved with the publisher's DI gains. Pins are unchanged: DI0's minor
cycle excluded ±2 pixels around them, so d1-d3 still hold their catalogue
fluxes.

## 3. Measures and decision rules (frozen)

All measures are DD4 section 5's, on each arm's final cycle (cycle 4).

**Convergence (R500).** The solver's converged fraction counts solution
cells over all directions, and d0 (pinned) is 1/4 of them. The off-axis
converged fraction is `(f − 0.25) / 0.75`.
- **Converges:** the off-axis fraction is ≥ 0.99 in every cycle, at fewer
  than 500 iterations.
- **Partly:** it rises above 0.10 in at least one cycle but does not meet
  the first rule.
- **Does not converge:** it stays at or below 0.10 in every cycle.

**DD against DI0 (R500 against DI0; decision measure).** `q₀` is the median
over d1-d3 of rms(R500) / rms(DI0). The thresholds are DD4 section 5's:
- **DD helps (rang only):** `q₀ ≤ 0.90` and DR(R500) ≥ DR(DI0);
- **Null:** `0.90 < q₀ < 1.05`, or `q₀ ≤ 0.90` with DR(R500) < DR(DI0);
- **DD worse:** `q₀ ≥ 1.05`.

**The d1 test (post hoc).** DD4 found rms near d1 3.6 × worse in R than in
DI0, and guessed that d1's gains absorb ESO 137-006's extended emission,
which M₀ lacks. Let `ρ = rms_d1(R500x) / rms_d1(DI0x)`.
- **Guess supported:** `ρ ≤ 1.0` and rms_d1(R500x) ≤ 0.5 × rms_d1(R500).
- **Guess not supported:** `ρ ≥ 2.0`.
- **Inconclusive:** anything else.

Also reported, not gated: R500x against DI0x by the `q₀` rule; the
per-direction median `|g|` and its spread; the iterations used per cycle;
the gain-product change between R (cap 150) and R500 in cycle 0.

## 4. Runs (planned)

- `python tools/oracles/dd4/dd4.py rang RUN --cap 500 --name R500`
- `python tools/oracles/dd4/dd4.py rang RUN --cap 500 --name R500x --model0 RUN/DI0/cycle-4/model.npy`
- `python tools/oracles/dd4/dd4.py rang RUN --di0 --name DI0x --model0 RUN/DI0/cycle-4/model.npy`
- `python tools/oracles/dd4/dd4.py scoreb RUN`

Each run goes through the host lock (8 slots shared, about 16 GB); the
results go to `research/results/dd4b-eso137/`.

## 5. Measured result

Not yet run.
