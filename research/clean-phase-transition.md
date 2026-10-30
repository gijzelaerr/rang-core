# Rang: when CLEAN recovers point sources exactly, on four real arrays

Research question 2 of the CLEAN programme ([clean-theory.md](clean-theory.md)),
2026-10-30, branch `clean-phase-transition`: a sharp statement of when
Högbom CLEAN recovers point sources exactly, as a function of source
separation, sidelobe level and uv coverage, measured across real arrays.
Every claim is labelled proposed, implemented or measured. Code:
[`core/src/clean.rs`](../core/src/clean.rs) (`support_coefficients`,
`separated_sums`, `anchored_bound`, with unit tests),
[`core/examples/clean_phase_transition.rs`](../core/examples/clean_phase_transition.rs)
(the measurement). Archive:
[`results/clean-phase-transition.json`](results/clean-phase-transition.json);
the full tables of the run are in
`outputs/clean-phase-transition-20261030/stdout.md` (ignored). The formalism,
Theorem 4, the exact recovery coefficient (ERC) and Proposition 4' are those
of [clean-theory.md](clean-theory.md) §2.

## 1. Answer in brief

- **Two sources, gain one: an exact condition (proven, Proposition 9).**
  Recovery holds if and only if the dirty-image peak lies on a source (F) and
  `max_q ‖B_SS⁻¹ B_{S,q}‖_∞ < 1` (L). The ERC asks for the ℓ1 norm
  instead. The rule predicted the outcome of all 40,000 two-source trials
  (14,400 random placements, 25,600 at fixed separation). Over every pair
  geometry of the grid, the worst-case separation is set by the first pick
  (F) on all 16 configurations. (L) alone holds from 1-6 pixels on the 12
  configurations other than the WSRT and KAT-7 snapshots.
- **A sharper sufficient condition (proven, Theorems 7 and 8).** Theorem 7
  replaces the counting terms `(k−1)μ_d` of Proposition 4' by worst sums
  over separated configurations. Two sums are needed: off-support `Σ_d(k)`
  and in-support `Σ°_d(k−1)`. It is never weaker than Proposition 4' but
  certifies nothing more on these arrays (the same 3 of 80 (configuration,
  `k`) cases), because the term `μ_1` of a competitor next to a source,
  0.61-0.97 on the non-degenerate configurations, is divided by `1 − α`. Theorem 8 anchors that term instead
  and keeps the sidelobe cancellation the ERC has.
  - It certifies 14 of the 80 cases.
  - For two sources it reaches the exact two-source worst-case separation on
    7 of the 9 configurations it certifies.
  - It certifies `k = 8` sources at `d = 16` on the VLA-C track.
- **The measured transition (measured, table in §5.1).** `d*(k)` is the
  smallest minimum separation with ≥ 95 % noiseless recovery there and
  beyond.
  - On the MeerKAT and VLA-C uniform-weight tracks it is 1, 1, 1, 2-3, 3
    for `k = 2, 4, 8, 16, 32`. The KAT-7 tracks give 1, 1, 1, 3 and none
    for `k = 32`.
  - With natural weights it is 1-12 pixels for `k = 8`. For `k = 32` there
    is no transition except on the VLA-C track (4 pixels): none within the
    range the grid can hold, which is 8 pixels for 32 sources.
  - The random placement hardly constrains two sources. Their transition
    comes from the fixed-separation experiment: 3-7 pixels on the 12
    configurations other than the WSRT and KAT-7 snapshots.
  - Every sufficient condition, the new ones included, sits well above the
    measured transition for `k ≥ 4`. CLEAN recovered 32 sources at 3 pixels
    separation in 100 of 100 trials on the MeerKAT and VLA-C uniform tracks,
    while `η(S) < 1` held in 0 and 1 of them.
- **Degenerate and floor-limited coverage.**
  - The WSRT snapshot is an east-west line, so `μ_d = 1.0000` at every
    distance and recovery never succeeds: 0 of 8,023 placed trials and 0 of
    3,200 pairs.
  - The KAT-7 snapshot (21 baselines, sidelobes of 0.87 at every distance)
    has no transition: `k = 2` recovers in 88-95 % at any separation and
    `k ≥ 8` never does.
- **A universal curve: partly.**
  - `η(S) < 1` gives 100 % success on every array (it is a theorem), and
    `η` is the best single predictor of noiseless success (pooled AUC 0.935).
  - Above one, the curves do not collapse. The per-configuration 95 % point
    of `η` ranges over 0.99-1.41, the 50 % point over 1.11-1.93, and the
    success rates of different arrays in the same `η` bin differ by up to
    68 percentage points.
  - No other statistic does better on both counts. `η₁` is equivalent
    (AUC 0.934). `max_q ‖B_{S,q}‖₁` has a smaller worst-bin spread (55
    points) but a lower AUC (0.928) and a larger mean spread. The
    Gershgorin sum, the in-support radius `α(S)` and the cell-level bounds
    `Σ` and `θ` all do worse (AUC 0.76-0.92).
  - In short, the ERC threshold is the universal *sufficient* line, and how
    far beyond it CLEAN still works depends on the array.
- **With 1 % noise (measured).**
  - No configuration reaches 95 % exact-support recovery at any separation.
  - Exact support depends on the PSF and `k`, hardly on `d`: for `k = 2` it
    is 15-33 % on natural-weight MeerKAT and WSRT and 86-97 % on the KAT-7
    and VLA-C uniform tracks.
  - The fraction of components on the support stays 0.91-1.00 for `k = 2`.
  - This is E2c's adjacent-pixel mechanism, unchanged across arrays.

## 2. Theory (proposed; proved here; implemented and checked numerically)

### 2.1 Notation

Weights are normalised so that `b(0) = 1`. Distances between pixels and
offsets are Chebyshev distances `|Δ| = max(|Δx|, |Δy|)`. `μ_d` is the peak
`|b(Δ)|` over `|Δ| ≥ d` within the PSF table (offsets up to ±63 on the
64-pixel grid), so `μ_1` is the coherence of [clean-theory.md](clean-theory.md).
A support `S` of `k` pixels is *`d`-separated* if its pixels are pairwise at
distance `≥ d`. For `q ∉ S` write `β_q = B_{S,q} = (b(x_i − q))_{i∈S}` and
`x_q = B_SS⁻¹ β_q`, so that for every residual in the span of the support
atoms `r_q = x_q · r_S` (Tropp; clean-theory §2.2). Then

- `η(S) = max_q ‖x_q‖₁` (the ERC),
- `α(S) = max_{i∈S} Σ_{j≠i} |B_ij|` (the Gershgorin radius of `B_SS`),
- `γ(S) = max_q ‖β_q‖₁` (the largest off-support column sum).

For a set of offsets, three worst-case sums of `m` values of `|b|` over
offsets that are pairwise `≥ d` apart:

- `Σ_d(m)`: all offsets nonzero (the competitor `q` is the origin);
- `Σ°_d(m)`: all offsets at distance `≥ d` from the origin (the origin is
  itself a source; the *pointed* sum);
- `Σ_d^{≥R}(m)`: all offsets at distance `≥ R` from the origin.

These are what the task called `S_d(k)`; there are two of them, not one,
because the off-support sum may put one source next to `q` while the
in-support sum may not.

**Lemma (computable bounds).** (a) *Greedy lower bound:* taking offsets in
decreasing `|b|`, keeping each that is `≥ d` from all kept ones and keeps the
whole set (with the origin) inside a 64-pixel span, gives a realisable
configuration, so its sum is `≤ Σ_d(m)`. (b) *Tile upper bound:* cover the
offset plane with `d × d` squares; two offsets in one square are `< d` apart,
so a `d`-separated set has at most one offset per square, and its sum is at
most the sum of the `m` largest square maxima. Each of the `d²` placements of
the tiling gives a valid bound; their minimum is the bound used. (c) The
tiling whose central square contains the offsets within `⌈d/2⌉ − 1` of the
origin shows `Σ_d(m) ≤ μ_1 + (m−1) μ_{⌈d/2⌉}` and `Σ°_d(m) ≤ m μ_d`: the
tile bound is never worse than the counting bounds of Proposition 4'.
Proof: (a) and (b) as stated; for (c), the central square of that tiling
contains every offset of norm `< ⌈d/2⌉` (for odd `d` it spans
`[−(d−1)/2, (d−1)/2]`, for even `d` the shifted `[−d/2+1, d/2]`), so every
other square holds only offsets of norm `≥ ⌈d/2⌉`, whose `|b|` is at most
`μ_{⌈d/2⌉}`, and the central square's maximum is at most `μ_1`. ∎
Implemented as `clean::separated_sums` (both bounds); the unit test
`separated_sum_bounds_bracket_the_exact_value` checks lower ≤ brute-force
maximum ≤ upper ≤ counting bound on a random PSF.

### 2.2 Theorem 7: the separated-sum condition

**Theorem 7.** If `Σ_d(k) + Σ°_d(k−1) < 1`, every `d`-separated support of
`k` pixels has `η(S) < 1`; hence noiseless Högbom CLEAN with any gain in
`(0, 2)` puts every component on the support and converges to the true
model (the induction of clean-theory Theorem 4).

Proof. (i) For `i ∈ S` the offsets `x_j − x_i`, `j ≠ i`, are `≥ d` from the
origin and pairwise `≥ d`, so `α(S) ≤ Σ°_d(k−1) < 1`. (ii) `B_SS = I + H`
with `H` the off-diagonal part; `‖H‖_{1→1}` is the largest column sum of
`|H|`, which is `α(S)` by symmetry, so the Neumann series gives
`‖B_SS⁻¹‖_{1→1} ≤ 1 / (1 − α(S))`. (iii) For `q ∉ S` the offsets `x_i − q`
are nonzero and pairwise `≥ d`, so `‖β_q‖₁ ≤ Σ_d(k)`. (iv)
`‖x_q‖₁ ≤ ‖B_SS⁻¹‖_{1→1} ‖β_q‖₁ ≤ Σ_d(k) / (1 − Σ°_d(k−1)) < 1`. ∎

By Lemma (c), Proposition 4' implies the hypothesis of Theorem 7, which is
therefore never weaker; the run asserts this for every configuration,
`d ≤ 32` and `k`. The per-support quantity behind it, `γ(S) + α(S) < 1`
(called `G` in the tables), is also sufficient for `η(S) < 1` by the same
steps.

### 2.3 Theorem 8: the anchored condition

Theorem 7 is still dominated by one term: a competitor `q` next to a source
sees `|b(u)|` up to `μ_1`, 0.61-0.97 on the non-degenerate configurations here, and step (iv) divides
that term by `1 − α`. The ERC does not pay this price because `x_q` keeps the
cancellation between what `q` and the neighbouring source see. The following
bound keeps it.

**Theorem 8.** For `0 < |u|` and `m ≥ 0` let

- `W_{d,u}(m)` be the largest `Σ_j |b(v_j − u) − b(u) b(v_j)|` over `m`
  offsets `v_j ≠ u`, pairwise `≥ d` and `≥ d` from the origin;
- `A_d(u, m) = |b(u)| + W_{d,u}(m) / (1 − Σ°_d(m))`;
- `F_d(R, k) = Σ_d^{≥R}(k) / (1 − Σ°_d(k−1))`.

If `Σ°_d(k−1) < 1`, every `d`-separated support of `k` pixels satisfies

`η(S) ≤ θ_d(k) := min_{R ≥ 1} max( max_{0<|u|<R} A_d(u, k−1), F_d(R, k) )`,

and `θ_d(k) < 1` gives exact recovery as in Theorem 7.

Proof. Fix `q ∉ S` and `R ≥ 1`. *Case A:* some source lies at distance
`< R` from `q`; let `i` be one, `u = q − x_i ≠ 0`, `v_j = x_j − x_i`. Let
`e_i` be the unit vector of `i` in `ℝ^S` and `H = B_SS − I`. From
`B_SS e_i = e_i + H e_i` follows `B_SS⁻¹ e_i = e_i − B_SS⁻¹ H e_i`, and
splitting `β_q = b(u) e_i + β'` (`β'` vanishes at `i`; `b` is even, so
`b(x_i − q) = b(u)`):

`x_q = b(u) e_i + B_SS⁻¹ y`, `y = β' − b(u) H e_i`,
`y_j = b(v_j − u) − b(u) b(v_j)` for `j ≠ i`, `y_i = 0`.

So `‖x_q‖₁ ≤ |b(u)| + ‖y‖₁ / (1 − α(S))`. The `v_j` are pairwise `≥ d`,
`≥ d` from the origin and differ from `u` (since `x_j ≠ q`), so
`‖y‖₁ ≤ W_{d,u}(k−1)` and `α(S) ≤ Σ°_d(k−1)`, giving
`‖x_q‖₁ ≤ A_d(u, k−1)` with `0 < |u| < R`. *Case B:* every source is at
distance `≥ R` from `q`; then the offsets `x_i − q` are pairwise `≥ d` and
`≥ R` from the origin, and steps (ii)-(iv) of Theorem 7 give
`‖x_q‖₁ ≤ F_d(R, k)`. Every `q` falls in one case, so `η(S)` is at most the
maximum of the two case bounds for each `R`, hence at most their minimum
over `R`. ∎

At `R = 1` case A is empty and `θ_d(k) ≤ Σ_d(k) / (1 − Σ°_d(k−1))`, which is
below one exactly when Theorem 7's hypothesis holds: Theorem 8 is never
weaker than Theorem 7. What it gains: the anchor `|b(u)|` enters undivided,
and `W` measures how much the sidelobe pattern seen from `q` differs from
the one seen from the anchoring source, scaled by `b(u)`.

*Implemented* as `clean::anchored_bound`: `R` runs over `1, …, r_max` with
`r_max = ⌈d/2⌉ + 1` clamped to `[3, 6]` (cost), every `W_{d,u}` and
`Σ_d^{≥R}` by the tile bound over at most nine placements of the tiling
(any placement is a valid upper bound), `Σ°_d` over all `d²` placements. The
unit test `anchored_bound_dominates_the_erc` checks `η(S) ≤ θ_d(k)` on random
separated supports of a random PSF; the run counts every trial whose cell has
`θ_d(k) < 1` but whose support has `η ≥ 1` (none, §5.6).

### 2.4 Proposition 9: two sources, gain one, in closed form

**Proposition 9.** Let `S = {x_1, x_2}`, `ρ = b(x_1 − x_2)` with
`0 < |ρ| < 1`, fluxes `f_1, f_2 ≠ 0`, and for `q ∉ S` write
`a_q = b(q − x_1)`, `c_q = b(q − x_2)`. Barring exact ties, noiseless
Högbom CLEAN with gain one picks only `x_1` and `x_2` (for as long as it
runs, at least three picks) if and only if

- (F) `max_q |a_q f_1 + c_q f_2| < max(|f_1 + ρ f_2|, |ρ f_1 + f_2|)` (the
  first pick), and
- (L) `max_q max(|a_q − ρ c_q|, |c_q − ρ a_q|) < 1 − ρ²` (every later pick).

Since `x_q = (a_q − ρ c_q, c_q − ρ a_q) / (1 − ρ²)`, (L) reads
`max_q ‖x_q‖_∞ < 1`, while the ERC asks `max_q ‖x_q‖₁ < 1`.

Proof. Write `φ_1, φ_2` for the two atoms (unit point sources at `x_1`,
`x_2` in visibility space). The dirty image is `r_p = f_1 b(x_1 − p) +
f_2 b(x_2 − p)`; the first pick lies in `S` iff (F). Say it is `x_i`, and let
`j` be the other source. Gain one adds `r_i = f_i + ρ f_j` to the model,
leaving the residual `e = (f_i − r_i) φ_i + f_j φ_j = f_j (φ_j − ρ φ_i)`,
for which `r_i = 0`, `r_j = f_j (1 − ρ²)` and
`r_q = f_j (β_{q,j} − ρ β_{q,i})`. The second pick lies in `S` iff
`|β_{q,j} − ρ β_{q,i}| < 1 − ρ²` for all `q`, i.e. `|(x_q)_j| < 1`. Picking
`x_j` adds `f_j (1 − ρ²)` there and leaves `e = −ρ f_j (φ_i − ρ φ_j)`, the
same form with `i` and `j` exchanged and the amplitude multiplied by `−ρ`. The picks therefore alternate `i, j, i, …`, the
residual never vanishes (`ρ ≠ 0`) and shrinks by `ρ²` per pair, a pick at
`x_i` needs `|(x_q)_i| < 1` and one at `x_j` needs `|(x_q)_j| < 1`; both are
needed once there are three picks, and together with (F) they suffice. ∎

Consequences. (L) is a flux-free **necessary** condition for two-source
recovery with gain one, (F) a flux-dependent one; both are exact. With
`ρ = 0` the run ends after two picks and (F) alone decides. Neither
condition is the ERC. The gap between `‖·‖_∞` (what gain-one CLEAN needs
after the first pick) and `‖·‖₁` (what the ERC demands for every residual
sign pattern) is the whole difference between them for two sources.

*The single-source case.* For `k = 1` the residual is `f a_x` at every step,
and the first pick (hence every pick) lies on the source if and only if
`|b(x − q)| < 1` for every in-image `q ≠ x`. Over all placements this is
`μ_1 < 1` on the offsets the image allows, which is the necessary condition
"no neighbour beats a lone atom". It always holds for a Gram matrix of
distinct atoms, except when two pixels have identical atoms. That happens
on the WSRT snapshot: an east-west array at hour angle 0 samples only the
`u` axis, so `b(0, Δy) = 1.0000` to four digits. Every pixel in a
source's column then matches the source to rounding, and recovery failed in all 8,023 placed trials and all
3,200 pairs (§5.1).

*Implemented* twice: per trial (first pick on `S` and
`eta_max < 1`, from `support_coefficients`), and as a scan over every pair
offset `Δ` of the grid with every competitor whose offsets to both sources
lie in the PSF table (a superset of the competitors of any placement in the
image, so a pass in the scan is a pass in the image) and the 81 flux pairs of
a `0.2, 0.3, …, 1.0` grid; the unit test `gain_one_selection_rules` checks
the rule against Högbom runs on a random PSF.

### 2.5 Proposition 10: the gain-one coefficient

**Proposition 10.** With gain one, if the first pick lies in `S` and
`η₁(S) = max_q (‖x_q‖₁ − min_i |(x_q)_i|) < 1`, every pick lies in `S`.

Proof. A gain-one step at `x_i` sets `r_i = 0`. By induction the residual
stays in the span of the support atoms, so after any step at `x_i`,
`|r_q| = |Σ_{l≠i} (x_q)_l r_l| ≤ (‖x_q‖₁ − |(x_q)_i|) ‖r_S‖_∞ ≤ η₁(S) ‖r_S‖_∞
< ‖r_S‖_∞`. ∎ `η₁ ≤ η`, and for two sources `η₁ = max_q ‖x_q‖_∞`, so
Proposition 10 contains Proposition 9's sufficiency. It is a modest
refinement for `k > 2` (one term of the ℓ1 sum dropped); §5.5 measures how
little it gains.

### 2.6 What is proven, what is checked

Proven here, in prose: the Lemma, Theorems 7 and 8, Propositions 9 and 10.
None is machine-checked in Lean (they are finite algebra on top of the
Neumann series, like Proposition 4', which is not formalised either).
Checked numerically: unit tests on random PSFs (§2.1-2.5), and in the run
the chain of implications Proposition 4' ⇒ Theorem 7 ⇒ Theorem 8 at the cell
level (asserted for every configuration, `d ≤ 32` and `k`), and per trial
`G < 1 ⇒ η < 1`, `η < 1 ⇒` all picks on the support,
`θ_d(k) < 1 ⇒ η < 1`, and Proposition 10's rule `⇒` all picks on the
support; all violation counts are zero (§5.6).

## 3. Arrays and sampling (implemented)

Four real layouts, all from the simms repository (provenance, commits and
checksums in [`data/README.md`](../data/README.md); not survey-grade
geometry). Each array gets one declination it observes well, 1.4 GHz,
one channel, a snapshot at hour angle 0, and a 13-sample ±2 h track. The
64 × 64 cell is set from the longest projected baseline over the track:
2.8 pixels per fringe. The exception is MeerKAT, which keeps the 2″ cell of
[clean-theory.md](clean-theory.md) (2.87 pixels per fringe) so that its
rows repeat E2's settings. The geometry code is that of `clean_theory`:
ITRF to ENU about the centroid, then the uv projection.

| array | antennas | dec | longest projected baseline over the track | cell | visibilities, snapshot / track |
| --- | ---: | ---: | ---: | ---: | ---: |
| MeerKAT | 64 | −30° | 35,947 λ | 2.000″ | 2,016 / 26,208 |
| VLA-C (27 pads, 3.4 km) | 27 | +40° | 15,819 λ | 4.657″ | 351 / 4,563 |
| WSRT (14 dishes, east-west) | 14 | +60° | 12,608 λ | 5.843″ | 91 / 1,183 |
| KAT-7 | 7 | −30° | 846 λ | 87.03″ | 21 / 273 |

Sidelobe profiles (measured; `μ_d` = peak `|b|` at distance `≥ d`):

| configuration | μ_1 | μ_2 | μ_4 | μ_8 | μ_16 |
| --- | ---: | ---: | ---: | ---: | ---: |
| meerkat-snapshot-natural | 0.932 | 0.770 | 0.504 | 0.391 | 0.184 |
| meerkat-snapshot-uniform | 0.801 | 0.378 | 0.219 | 0.219 | 0.219 |
| meerkat-track-natural | 0.931 | 0.768 | 0.503 | 0.377 | 0.149 |
| meerkat-track-uniform | 0.680 | 0.130 | 0.076 | 0.076 | 0.066 |
| vla-c-snapshot-natural | 0.811 | 0.444 | 0.323 | 0.323 | 0.323 |
| vla-c-snapshot-uniform | 0.750 | 0.327 | 0.327 | 0.327 | 0.327 |
| vla-c-track-natural | 0.809 | 0.439 | 0.134 | 0.082 | 0.036 |
| vla-c-track-uniform | 0.614 | 0.112 | 0.088 | 0.070 | 0.070 |
| wsrt-snapshot-natural | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| wsrt-snapshot-uniform | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| wsrt-track-natural | 0.966 | 0.875 | 0.634 | 0.364 | 0.262 |
| wsrt-track-uniform | 0.913 | 0.690 | 0.193 | 0.128 | 0.128 |
| kat7-snapshot-natural | 0.871 | 0.871 | 0.871 | 0.871 | 0.871 |
| kat7-snapshot-uniform | 0.871 | 0.871 | 0.871 | 0.871 | 0.871 |
| kat7-track-natural | 0.702 | 0.289 | 0.289 | 0.289 | 0.289 |
| kat7-track-uniform | 0.637 | 0.247 | 0.247 | 0.247 | 0.247 |

The MeerKAT values repeat clean-theory §5 (0.9315, 0.8008, 0.9308, 0.6803).
Three cases need care.

- **WSRT snapshot.** It is degenerate: at hour angle 0 an east-west array
  samples only the `u` axis, so `b(0, Δy) = 1` to four digits and atoms in
  one column are indistinguishable.
- **KAT-7 snapshot.** Uniform and natural weights coincide: the 21
  baselines evidently fall in distinct uv cells (the two PSFs agree to
  four digits in every `μ_d`). The two configurations differ only in their
  trial seeds.
- **Far sidelobes.** On several PSFs the far sidelobe level (0.22-0.33,
  0.87 for the KAT-7 snapshot) persists to the edge of the image. That is
  why `μ_d` stops falling, and why no separation helps there.

## 4. Protocol (implemented)

For each of the 16 configurations (4 arrays × snapshot or 13-sample ±2 h
track × natural or uniform weights; uniform weights as in `clean_theory`,
one over the count per uv cell of the 64-pixel image):

1. The PSF over the full `127 × 127` offset range (so subtraction is exact
   anywhere in the image), `μ_d` for `d = 1..32`.
2. For `d = 1..32` and `k ∈ {2, 4, 8, 16, 32}`: the greedy and tile bounds
   on `Σ_d(k)` and `Σ°_d(k−1)`, Theorem 7's sum, Theorem 8's `θ_d(k)` and
   Proposition 4''s sum; the predicted transition of each is the smallest
   `d ≤ 32` where it falls below one.
3. The two-source scan of Proposition 9 over all 8,064 pair offsets of the
   half plane: the worst-case `d` of (F) and (L) together, of each alone and
   of the ERC (`(|a − ρc| + |c − ρa|) / (1 − ρ²) < 1` for every competitor),
   and the predicted success for uniformly placed pairs at separation
   `≥ d` and exactly `d` (placement weight `(64 − |Δx|)(64 − |Δy|)`, flux
   pairs on the 9 × 9 grid).
4. Recovery trials, 100 per cell for `k ∈ {2, 4, 8, 16, 32}` and minimum
   pairwise separation `d ∈ {1, 2, 3, 4, 6, 8, 12, 16, 24}`: positions by
   random sequential placement with up to 20 restarts of `400 k` draws (a
   cell is "grid full" when `⌈64/d⌉² < k`; a trial whose placement fails is
   dropped, and cells with fewer than 100 placed trials are reported but
   left out of `d*`; near-saturated cells are lattice-like samples), fluxes
   uniform in `[0.2, 1]`. On the same sources: (a) noiseless, gain 1, run
   to `|r| < 1e-9` or 20,000 components; success means every component on
   the support and the model within 1e-6 of the truth at every pixel
   (runs that hit the cap are counted separately and fail unless they meet
   both); (b) 1 % image noise (a random 64 × 64 window of one of eight
   128 × 128 dirty images of white visibility noise, which is a valid
   realisation because the dirty noise is stationary; measured σ
   0.0095-0.0103), gain 0.1, stop at `|r| < 5σ`; "exact support" means
   every source has a component and no other pixel does; the fraction of
   components on the support is recorded. For every trial `η(S)`, `η₁(S)`,
   `max_q ‖x_q‖_∞`, `γ(S)`, `α(S)` are computed (one inversion of `B_SS`,
   then one product per pixel).
5. Two sources at separation exactly `d = 1..16`, 100 trials per `d`,
   noiseless, gain 1 (first source uniform, offset uniform on the ring of
   radius `d`, rejected if outside), against the scan's prediction and the
   per-trial rule of Proposition 9.
6. `d*(k)`: the smallest `d` with at least 95 % success there and at every
   larger fully placed `d`.

Seeds: every trial is seeded by splitmix64 from (configuration, `k`, `d`,
trial), noise by configuration, and results are collected in order. The
output is therefore independent of the rayon schedule by construction, and
was checked: two 10-trial runs gave identical archives once the timing
fields were removed. The collapse analysis pools all trials of (4) and bins success by a
statistic; spreads between arrays are taken over bins where at least two
arrays have at least 30 trials; a logistic fit of success on the logarithm
of the statistic gives the 50 % and 95 % points; the AUC is the probability
that a successful trial has a smaller statistic than a failed one.

## 5. Results (measured, 2026-10-30, Windows workstation, one run of 301 s)

### 5.1 The transition table

Entries are `d` for `k = 2, 4, 8, 16, 32`. "–" means no `d` qualifies:
none measured up to 24 pixels or the grid limit, or no bound below one up
to 32 pixels. "Measured" is `d*(k)`. The certified columns give the
smallest `d` at which each sufficient condition holds for every
`d`-separated support. The two-source columns are from §4 (5) and from the
scan: the smallest separation from which every pair geometry recovers with
gain one, and from which every pair has ERC < 1.

| configuration | measured `d*(k)` | Theorem 8, certified | Theorem 7, certified | Theorem 7 with greedy sums | Proposition 4' | two sources at exactly `d`, measured | two-source worst case, gain 1 | two-source worst case, ERC |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| meerkat-snapshot-natural | 1, 3, 12, –, – | 18, –, –, –, – | – | – | – | 5 | 15 | 15 |
| meerkat-snapshot-uniform | 1, 1, 3, 4, – | 4, –, –, –, – | – | – | – | 4 | 4 | 4 |
| meerkat-track-natural | 1, 1, 4, 8, – | 18, 29, –, –, – | – | 26, –, –, –, – | – | 5 | 5 | 5 |
| meerkat-track-uniform | 1, 1, 1, 3, 3 | 3, 4, –, –, – | 3, –, –, –, – | 3, –, –, –, – | 3, –, –, –, – | 3 | 3 | 3 |
| vla-c-snapshot-natural | 1, 2, 2, –, – | – | – | – | – | 3 | 4 | 4 |
| vla-c-snapshot-uniform | 1, 1, 3, 4, – | – | – | – | – | 3 | 3 | 3 |
| vla-c-track-natural | 1, 1, 2, 3, 4 | 4, 8, 16, –, – | 12, –, –, –, – | 8, 31, 32, 32, 32 | 12, –, –, –, – | 3 | 4 | 4 |
| vla-c-track-uniform | 1, 1, 1, 2, 3 | 3, 4, –, –, – | 3, –, –, –, – | 3, –, –, –, – | 3, –, –, –, – | 3 | 3 | 3 |
| wsrt-snapshot-natural | – | – | – | – | – | – | none | none |
| wsrt-snapshot-uniform | – | – | – | – | – | – | none | none |
| wsrt-track-natural | 1, 6, 12, –, – | – | – | – | – | 7 | 11 | 11 |
| wsrt-track-uniform | 1, 1, 6, –, – | 6, –, –, –, – | – | – | – | 6 | 6 | 6 |
| kat7-snapshot-natural | – | – | – | – | – | 14 (to 16 only) | none | none |
| kat7-snapshot-uniform | – | – | – | – | – | 16 (to 16 only) | none | none |
| kat7-track-natural | 1, 1, 1, 3, – | 3, –, –, –, – | – | – | – | 3 | 3 | 3 |
| kat7-track-uniform | 1, 1, 1, 3, – | 3, –, –, –, – | – | – | – | 3 | 3 | 3 |

("none": some pair at every separation the 64-pixel image allows fails.)
The noisy exact-support `d*` is "–" for every configuration and `k`.

The task's literal definition, the smallest `d` with ≥ 95 % success, is
archived as `dstar_first_95`. The table uses the stable variant, ≥ 95 % at
that `d` and every larger one. They differ in two cells:

- vla-c-snapshot-natural, `k = 16`: literal 6, stable – (94 at `d = 12`);
- kat7-snapshot-natural, `k = 2`: literal 3, stable – (91-95 above it).

Reading the table:

- For `k = 2`, random placement with minimum separation `d` almost never
  puts two sources close (`d* = 1`). The fixed-separation experiment
  measures the two-source transition: 3-7 pixels on the 12 configurations other than
  the WSRT and KAT-7 snapshots, always at or below the worst-case separation.
- Theorem 8 certifies two sources at the worst-case separation itself on
  7 configurations. The exceptions:
  - the MeerKAT natural-weight PSFs, where the bound gives 18 against the
    worst case of 15 and 5;
  - the VLA-C snapshots and the natural WSRT track, where it certifies
    nothing.
- For `k ≥ 4` the gap between measured and certified is large. On the
  VLA-C track with natural weights, CLEAN needs 1, 2 and 3 pixels for 4, 8
  and 16 sources, while Theorem 8 certifies 8 and 16 pixels for 4 and 8
  sources and nothing for 16.

Success counts behind `d*`, `k = 16` and `k = 32` (of 100; at `d = 16`,
`k = 16`, of the trials that could be placed). `d = 12` for `k = 32`
could not be placed by random sequential placement.

| configuration | `k = 16`, d = 1, 2, 3, 4, 6, 8, 12, 16 | `k = 32`, d = 1, 2, 3, 4, 6, 8 |
| --- | --- | --- |
| meerkat-snapshot-natural | 6, 7, 9, 22, 32, 47, 80, 17/19 | 0, 0, 0, 0, 0, 0 |
| meerkat-snapshot-uniform | 64, 66, 94, 100, 100, 100, 100, 12/12 | 6, 18, 58, 86, 92, 93 |
| meerkat-track-natural | 26, 37, 50, 71, 93, 97, 100, 20/20 | 0, 0, 0, 4, 5, 30 |
| meerkat-track-uniform | 92, 93, 100, 100, 100, 100, 100, 19/19 | 50, 76, 100, 100, 100, 100 |
| vla-c-snapshot-natural | 54, 69, 89, 90, 97, 96, 94, 11/11 | 1, 3, 12, 15, 30, 26 |
| vla-c-snapshot-uniform | 60, 74, 93, 99, 100, 95, 100, 13/14 | 2, 10, 31, 39, 49, 45 |
| vla-c-track-natural | 40, 72, 96, 100, 100, 100, 100, 18/18 | 14, 31, 77, 100, 100, 100 |
| vla-c-track-uniform | 94, 95, 100, 100, 100, 100, 100, 23/23 | 43, 76, 100, 100, 100, 100 |
| wsrt-track-natural | 1, 2, 1, 3, 15, 19, 33, 8/13 | 0 at every d |
| wsrt-track-uniform | 28, 36, 57, 57, 75, 75, 84, 11/11 | 0, 0, 0, 0, 1, 0 |
| kat7-track-natural | 68, 82, 99, 99, 100, 99, 100, 13/13 | 2, 4, 13, 12, 14, 22 |
| kat7-track-uniform | 79, 86, 100, 99, 100, 99, 100, 9/10 | 7, 11, 18, 19, 36, 40 |

A pattern visible here (measured, not proven): for many sources the
**far** sidelobe level decides. The configurations whose `μ_d` decays
(MeerKAT and VLA-C tracks: `μ_16` 0.04-0.15) reach 100 % for 32 sources
at 3-4 pixels where the uniform weights hold the near sidelobes down.
Those with a floor of 0.22-0.33 that persists to the image edge (MeerKAT
uniform snapshot, VLA-C snapshots, KAT-7 tracks) saturate at 22-93 %
however far apart the sources are. With 31 other sources each contributing
up to the floor, the in-support sum `α(S)` exceeds one, and separation
cannot reduce it. For few sources the near sidelobes `μ_1, μ_2` decide.

### 5.2 Two sources: the closed form against the runs

Proposition 9's per-trial rule (first pick on the support and
`max_q ‖x_q‖_∞ < 1`) agreed with the observed outcome "all picks on the
support" in **all 40,000** two-source trials: 14,400 with random placement
and 25,600 at fixed separation, 16 configurations. The ERC is far stricter.
At fixed separation, success and `η < 1` (of 100), with the scan's
predicted success (pairs placed uniformly, nine flux values in the infinite
image superset), for `d = 1..6`:

| configuration | success | `η < 1` | predicted success |
| --- | --- | --- | --- |
| meerkat-snapshot-natural | 0, 15, 57, 91, 100, 100 | 0, 0, 16, 81, 100, 100 | 0.00, 0.17, 0.65, 0.93, 1.00, 1.00 |
| meerkat-track-uniform | 77, 85, 100, 100, 100, 100 | 19, 58, 100, 100, 100, 100 | 0.75, 0.88, 1.00, 1.00, 1.00, 1.00 |
| vla-c-track-natural | 44, 56, 95, 100, 100, 100 | 0, 0, 72, 100, 100, 100 | 0.50, 0.57, 0.95, 1.00, 1.00, 1.00 |
| wsrt-track-natural | 85, 50, 88, 85, 84, 91 | 0, 0, 55, 41, 63, 70 | 0.75, 0.60, 0.86, 0.85, 0.85, 0.90 |
| kat7-snapshot-natural | 73, 83, 88, 92, 91, 94 | 0, 50, 46, 61, 48, 71 | 0.50, 0.79, 0.76, 0.70, 0.79, 0.87 |

- The scan's prediction matches the runs within sampling noise wherever
  the image edge is irrelevant. It underestimates the KAT-7 snapshot,
  whose 87″ pixels put the decisive far sidelobes outside a real image;
  the scan counts those competitors. The prediction is therefore an
  approximate lower bound: the competitor set is a superset, but the
  9 × 9 flux grid only approximates the uniform flux draw, and two cells
  fall below it. Those are meerkat-snapshot-natural at `d = 3` (57 against
  0.65) and wsrt-track-natural at `d = 2` (50 against 0.60).
- **Adjacent sources.** At `d = 1` the outcome ranges from never
  (natural-weight MeerKAT) to 77-100 % (the MeerKAT, VLA-C and KAT-7
  uniform tracks). Every success and failure is the one Proposition 9
  predicts.

### 5.3 How tight are the sufficient conditions

Of the 80 (configuration, `k`) cases:

| condition | certified somewhere `≤ 32` | of which `k ≥ 4` |
| --- | ---: | ---: |
| Proposition 4' | 3 | 0 |
| Theorem 7 (tile bound) | 3 | 0 |
| Theorem 7 with the greedy (achievable) sums | 8 | 4 |
| Theorem 8 (anchored) | 14 | 5 |

- **Theorem 7 has little room left.** The greedy sums are achievable by
  configurations, so an exact evaluation of `Σ_d` and `Σ°_d` could certify
  at most the greedy row. That row adds five cases, all at 26-32 pixels:
  `k = 2` on the MeerKAT natural track, and `k = 4..32` on the VLA-C
  natural track. The weakness lies in the triangle-inequality route, not
  in the tile bound.
- **Where Theorem 8 gains.** It certifies 4 and 8 sources (MeerKAT tracks,
  VLA-C tracks) where nothing else does. It certifies nothing for
  `k ≥ 16`.
  - Where the far-sidelobe floor is high (the MeerKAT uniform, VLA-C,
    WSRT and KAT-7 snapshots, the KAT-7 tracks, the WSRT natural track),
    the in-support bound `Σ°_d(k−1)` alone exceeds one for `k ≥ 8`; on the
    WSRT uniform track it does so for `k ≥ 16`.
  - Where the sidelobes decay (the MeerKAT natural snapshot, the MeerKAT
    and VLA-C tracks), `Σ°` stays at 0.2-0.8 for `k = 16`, and the anchored
    remainder `W` keeps `θ` above one: the minimum of `θ` over `d ≤ 32` at
    `k = 16` is 1.3-6.2.
- **Per trial (measured).** The ERC was below one in 0-2 % of the
  `k = 32` trials that CLEAN recovered on the uniform tracks. The
  per-support Gershgorin condition `G < 1` held even less often. No
  configuration-free condition of Tropp type can describe the measured
  `d*(k)` for `k ≥ 8`.

### 5.4 With noise

Exact support (every source found, no false pixel) and the fraction of
components on the support at `d = 8`, 1 % image noise, gain 0.1, `5σ`
stop:

| configuration | exact, `k = 2` | exact, `k = 8` | on-support fraction, `k = 2` / `k = 8` |
| --- | ---: | ---: | --- |
| meerkat-snapshot-natural | 32 | 0 | 0.95 / 0.90 |
| meerkat-snapshot-uniform | 58 | 15 | 0.98 / 0.98 |
| meerkat-track-natural | 21 | 0 | 0.93 / 0.91 |
| meerkat-track-uniform | 82 | 48 | 0.99 / 0.99 |
| vla-c-snapshot-natural | 73 | 12 | 0.99 / 0.98 |
| vla-c-snapshot-uniform | 81 | 19 | 0.99 / 0.99 |
| vla-c-track-natural | 73 | 20 | 0.99 / 0.99 |
| vla-c-track-uniform | 91 | 72 | 1.00 / 1.00 |
| wsrt-track-natural | 28 | 0 | 0.93 / 0.92 |
| wsrt-track-uniform | 43 | 0 | 0.96 / 0.96 |
| kat7-snapshot-natural | 12 | 0 | 0.92 / 0.15 |
| kat7-track-natural | 92 | 39 | 1.00 / 0.99 |
| kat7-track-uniform | 94 | 53 | 1.00 / 0.99 |

- Across `d = 1..24` the `k = 2` exact-support rate of each configuration
  varies by about ±10 points without trend. Noise failures are not a
  separation effect.
- They track `μ_1`, the correlation of adjacent pixels: E2c's mechanism,
  a component one pixel off the source. The ranking follows `μ_1` roughly:
  `μ_1` 0.61-0.71 gives 82-94 % and 0.93-0.97 gives 21-32 %. The KAT-7
  snapshot, with its sidelobe floor of 0.87, is the exception at 12 %.
- No configuration reaches 95 % exact support. The best is 97 % (KAT-7
  uniform track, `k = 2`, `d = 3`), not stable in `d`.
- The fraction of picks on the support (0.91-1.00 for `k = 2`) shows CLEAN
  still finds the sources; exact support is the wrong success criterion
  with noise at this sampling.
- WSRT snapshots: 0.01-0.06 of picks on the support.

### 5.5 Is there a universal curve?

Pooled success of all noiseless trials of §4 (4) against `η(S)`, by array
(percent, trials in parentheses; bins below 0.6 are empty):

| `η` | [0.6, 0.9) | [0.9, 1) | [1, 1.1) | [1.1, 1.25) | [1.25, 1.5) | [1.5, 2) | [2, 3) | ≥ 3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MeerKAT | 100 (4,520) | 100 (5,429) | 94 (1,785) | 78 (1,694) | 30 (1,198) | 21 (1,151) | 0 (258) | 0 (25) |
| VLA-C | 100 (9,098) | 100 (1,930) | 99 (1,621) | 87 (1,341) | 64 (691) | 24 (1,212) | 1 (164) | 0 (2) |
| WSRT | – | 100 (3,433) | 31 (5,307) | 32 (1,433) | 6 (954) | 0 (1,128) | 0 (516) | 0 (3,268) |
| KAT-7 | 100 (3,859) | 100 (1,937) | 93 (1,190) | 59 (512) | 58 (2,568) | 9 (595) | 7 (2,705) | 0 (2,681) |

| statistic | pooled AUC | worst / mean spread between arrays in a bin (points) | per-configuration 95 % point | per-configuration 50 % point |
| --- | ---: | --- | --- | --- |
| `η(S)` (ERC) | 0.935 | 68 / 23 | 0.99-1.41 | 1.12-1.93 |
| `η₁(S)` (Prop. 10) | 0.934 | 70 / 23 | 0.83-1.40 | 1.09-1.92 |
| `max_q ‖B_{S,q}‖₁` | 0.928 | 55 / 26 | 1.02-1.81 | 1.30-2.50 |
| `γ(S) + α(S)` | 0.911 | 55 / 29 | 1.09-2.64 | 1.59-3.99 |
| `α(S)` (in-support radius) | 0.878 | 66 / 39 | 0.08-0.85 | 0.26-1.48 |
| cell bound `Σ_d(k) + Σ°_d(k−1)` | 0.917 | 64 / 34 | 2.4-9.1 | 4.4-16.0 |
| cell bound `Σ°_d(k−1)` | 0.919 | 82 / 28 | 0.80-3.99 | 1.73-7.34 |
| cell bound `θ_d(k)` | 0.763 | 61 / 39 | – (mostly infinite) | – |

(95 % and 50 % points from logistic fits on the logarithm of the
statistic, 14 non-degenerate configurations; the WSRT snapshots have no
successes.)

What this says:

- **One universal statement holds.** `η(S) < 1` means recovery on every
  array: all 30,206 pooled trials with `η < 1` succeeded.
- **Above one, there is no single curve.** At `η ∈ [1, 1.1)`, MeerKAT,
  VLA-C and KAT-7 still recover 93-99 %, WSRT 31 %. The per-configuration
  95 % point lies between 0.99 (KAT-7 snapshot, WSRT natural track) and
  1.41 (KAT-7 uniform track).
- **The ERC threshold is nearly tight for the worst PSFs and up to 40 %
  conservative for the best.** No statistic built from the PSF and the
  positions alone tightens the spread. The residual dependence is on the
  dynamics, which sign patterns CLEAN actually visits, and on whether the
  first pick fails: 45 % of the noiseless failures outside the WSRT
  snapshots fail at the first component.
- **Verdict.** The universal-curve hypothesis is **rejected** in its strong
  form and holds only as the one-sided threshold `η = 1`.

### 5.6 Checks

- **Implications (each a theorem; a count would be a bug).** Over all
  64,205 placed trials: `η < 1 ⇒` all picks on the support; `G < 1 ⇒ η < 1`;
  Theorem 7 cell condition `⇒ G < 1`; Proposition 4' `⇒` Theorem 7;
  Proposition 10's rule `⇒` all picks on the support; `θ_d(k) < 1 ⇒ η < 1`.
  All six counts are 0.
- **Asserted for every configuration, `d ≤ 32` and `k`.** The tile bounds
  are never above the counting bounds, and Theorem 8 is never weaker than
  Theorem 7.
- **Cross-check with E2.** On MeerKAT at `d = 8`, success for `k = 2, 4, 8`
  is 100, 100, 94 (natural snapshot; E2: 100, 100, 97), 100, 100, 100
  (uniform snapshot), 100, 100, 99 (natural track) and 100, 100, 100
  (uniform track). This agrees with E2 within sampling (different seeds,
  20,000- rather than 4,000-component cap).
- **Iteration cap.** 6,737 of the 13,588 noiseless failures outside the
  WSRT snapshots hit the 20,000-component cap. Every capped failure also
  had an off-support pick, because success requires all picks on the
  support, and the success counts equal the on-support counts in every
  cell. The cap therefore never turned an on-support run into a failure.

## 6. Proven, implemented, measured

| claim | status |
| --- | --- |
| Lemma (greedy and tile bounds on separated sums; tile ≤ counting) | proven (prose); unit-tested |
| Theorem 7 (separated-sum condition), never weaker than Proposition 4' | proven (prose); asserted in the run |
| Theorem 8 (anchored condition), never weaker than Theorem 7 | proven (prose); unit-tested; 0 violations in the run |
| Proposition 9 (two sources, gain one, exact; (L) necessary) | proven (prose); 40,000 / 40,000 trials agree |
| Proposition 10 (gain-one coefficient `η₁`) | proven (prose); unit-tested; 0 violations; measured gain over `η` negligible |
| `d*(k)` per array, coverage, weighting (§5.1) | measured (100 trials per cell; 95 % criterion) |
| far-sidelobe floor decides large `k` | measured pattern, not proven |
| no universal success curve beyond `η = 1` | measured (negative result) |
| no 95 % exact-support transition with 1 % noise | measured (negative result) |

Nothing here is formalised in Lean. Novelty, in the sense of AGENTS.md:
this is an understanding result about CLEAN's recovery regime, not an
imaging-quality or cost claim. The ERC and Neumann-series bounds are
standard (Tropp 2004). As far as the searches of
[clean-theory.md](clean-theory.md) reach, three things are new:

- the anchored bound;
- the exact two-source gain-one condition;
- the measured transition table across real arrays.

## 7. Reproduction and timings

```bash
cargo test --release --manifest-path core/Cargo.toml clean::
cargo run --release --manifest-path core/Cargo.toml --example clean_phase_transition -- outputs/clean-phase-transition-20261030 100
```

Timings (Windows workstation, 16 threads, 2026-10-30):

- **Full run:** 301.1 s. The two WSRT snapshots take 77 s each (every
  trial runs to the cap); the other configurations take 1.4-22 s. Per
  configuration: PSF 0.00-0.40 s, bounds 0.40-0.52 s, pair scan 0.1 s,
  noise images 0.01-4.6 s.
- **Pilot (10 trials per cell):** 48.0 s.
- **Builds and tests:** `cargo test --release` of the crate 2 min 9 s and
  3 min 41 s (both mostly compilation; the tests themselves take 0.4-0.9 s);
  clippy and fmt a few seconds.

Figures were not made: matplotlib is not installed in the repository's
`.venv`. The archive holds every binned count needed to draw the success
curves and the collapse plot.

## 8. Limitations and next steps

- **Scope of the measurement.**
  - One grid size (64 × 64), one pixel scale per array (2.8-2.87 pixels per
    fringe), one declination per array.
  - On-grid sources only.
  - Random sequential placement cannot fill cells near saturation (32
    sources at `d ≥ 12`, 16 at `d = 16`); those cells are reported but not
    used.
- **Two-source scan.** It uses a superset of competitors, so its
  worst-case separations are upper bounds for a 64-pixel image.
- **Proposed next steps.**
  - A sufficient condition that uses the trajectory: CLEAN's residual sign
    patterns, as Proposition 9 does for two sources. This is the only
    route to the measured `d*(k)` for `k ≥ 8`.
  - A noise-margin version of Proposition 9 (clean-theory §9).
  - Lean proofs of Theorem 7 and Proposition 9, both finite algebra.
  - Measuring the far-sidelobe-floor law (success against `(k−1)·μ_∞`)
    with more arrays and grid sizes.
