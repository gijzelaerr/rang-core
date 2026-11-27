# DD14: QP12's facet flux scale when the true facet amplitudes are not 1

Issue #15. Follows [dd13-absorb.md](dd13-absorb.md) (DD13),
[dd12-msclean.md](dd12-msclean.md) and [dd11-start.md](dd11-start.md).
Branch `dd14-flux-scale`. Coordinator brief 2026-11-27. Sections 1-9 are
frozen 2026-11-27, before the code that runs them, before the simulation is
generated and before any measurement. Later changes are dated amendments,
committed before the reading they affect, and labelled post hoc where they
follow a reading.

Status: **frozen, not run.**

## 1. Question

DD13's QP12 (unit-amplitude trusted gains in every cycle's images, rule U,
Högbom searching d1-d3's pin boxes from cycle 2, 12 cycles) closes the loop
on O: d1 0.116 against Q12's 0.207 and the truth control AT12's 0.093. It
takes each facet's flux scale from the convention that the image gains have
unit amplitude, where Q12 takes it from the catalogue pins. On O the
convention is right by construction: O's truth amplitudes average to 1 per
facet (mean log-amplitude −0.002, +0.005, −0.005 in d1-d3; d0 exactly 1).

**DD14's question.** When the true facet amplitudes do not average to 1,
does QP12 carry the offset into the facet flux scale, and does a variant
that fixes the per-facet flux-gain degeneracy another way keep both the
loop's gain accuracy and the flux scale?

**The degeneracy.** For one facet, multiplying every gain by a real a_f and
the facet's sky by 1/a_f² leaves the data unchanged. A constant per-facet
offset is therefore invisible to any solve; only the convention decides
where it goes. The test is the mismatch between the units of the start
model and pins and what each arm's image rule assumes. Per-antenna and
per-time structure in the offset (section 2) breaks the pure scalar case a
little; the per-facet mean is what the flux scale sees.

## 2. Convention and the simulation OB

**What M₀ᶜ's fluxes are.** DD4's catalogue step (`tools/oracles/dd4/
catalogue.py`) sets every component's flux to `S_app = S_1043 × B(ρ)`, the
RACS flux interpolated to 1043.15 MHz times the Mauch et al. (2020)
cosine-squared power beam with θ_b = 82.68′. M₀ᶜ, its pins and RM are
apparent fluxes through that nominal, circular beam. In the real recipe the
beam is therefore in the model, and the true facet amplitudes differ from 1
only by the beam model's own error (plus anything else in the gains).

**The simulation answers two cases at once.** OB reads O's sky (`sky.npy`)
and M₀ᶜ (start model and pins) as **intrinsic** fluxes and puts a realistic
MeerKAT L-band power beam into the truth gains. So:
- **QP12 on OB** is the case the brief names: unit-amplitude images with
  the beam in the gains, not in the model.
- **QPN12 on OB** (section 3: unit amplitude times the nominal beam) is the
  real recipe's case: the nominal beam carries the facet scale, and the
  remaining offset is the true beam's departure from the nominal one.
  On real data, with an apparent catalogue model, QP12's rules *are*
  QPN12's rules (the model already holds B_nom), up to signal-to-noise.

**What changes against O.** `DATA` and `truth.npz` change; `sky.npy`,
M₀ᶜ, the pins, the facets, the weights, the flags, the noise draw and the
PSF do not.
- `DATA = n + Σ_f G'_f predict(sky O|f) G'_fᴴ`, with n DD7's noise
  regenerated (`dd7.regen_noise`, seed 5501) and the predict DD8's
  `facet_vis`.
- `G'_{b,a,f,h} = G^O_{b,a,f,h} × √B_true(b, a, f)`, the voltage factor,
  the same for both hands (Stokes I beam), per truth block b (4 × 8 s),
  antenna a and facet f (all four, d0 included).

**The true beam (frozen rule, seed 1401).** B_true is the Mauch et al.
(2020) beam shape `B = [cos(πx) / (1 − 4x²)]²`, `x = 1.189 ρ_eff / θ_b`,
θ_b = 82.68′ (catalogue.py's value at 1043.15 MHz), with the two
departures that de Villiers & Cotton (2022, arXiv 2202.02101) measure with
holography and the circular model leaves out:
- **Ellipticity:** the Stokes I beam is elongated along the antenna's
  vertical (elevation) axis with about 4 % ellipticity: widths θ_b(1 + 0.02)
  along elevation and θ_b(1 − 0.02) along azimuth. The beam is fixed to the
  alt-az mount, so on the sky it turns with the parallactic angle q(t).
- **Pointing:** the system pointing accuracy is σ = 0.64′. Each antenna gets
  a static offset (p_el, p_az), each axis N(0, 0.64′/√2), drawn with
  `numpy.random.default_rng(1401)` in antenna order, elevation then
  azimuth.
- Geometry: facet centre f at (l_f, m_f) from DD7's `setup.json`, offset
  ρ_f = asin(√(l² + m²)) and position angle ψ_f = atan2(l_f, m_f) (east of
  north). In antenna a's frame at block b: Δ_el = ρ_f cos(ψ_f − q_b) −
  p_el,a, Δ_az = ρ_f sin(ψ_f − q_b) − p_az,a, and
  `ρ_eff² = (Δ_el / 1.02)² + (Δ_az / 0.98)²`.
- q_b: the parallactic angle of the phase centre (RA 243.7966°,
  Dec −60.9058° from `PHASE_DIR`) at the mean `TIME` of block b, for the
  MeerKAT site (latitude −30.7130°, longitude 21.4430° E; from recall),
  with GMST = 280.46061837° + 360.98564736629° × (JD − 2451545.0) and
  `q = atan2(sin H, tan φ cos δ − sin δ cos H)`.
- Not simulated: the beam's frequency dependence over the 64 channels, its
  variation across a facet, sidelobes, and the H/V difference. The DD gains
  have one value per interval for all channels, and so does the truth.

**Nominal beam (the variant's, frozen).** B_nom,f = the circular Mauch beam
at ρ_f, no pointing error: **0.9175, 0.8129, 0.3607** for d1-d3 (√: 0.958,
0.902, 0.601), 1 for d0. The per-facet means of B_true over antennas and
blocks are computed by the rule and recorded in `beam.json` before the MS
is written; they are expected within a few per cent of B_nom.

**Gate GB (build, blocking; frozen).**
1. DD8's unchanged `dd8.insert` rebuilds O in `gate/O` (DD13's setup gate:
   GO passes, `build.json` equal to DD10's to 1e-9 relative, `sky.npy` with
   DD8's SHA-256).
2. DD14's builder with B_true ≡ 1 gives `gate/O`'s `DATA` to ≤ 1e-3 Jy
   absolute on every unflagged cell (GO's tolerance; complex64 sums in a
   different order).
3. OB's `DATA − n − Σ G' predict G'ᴴ` ≤ 1e-3 Jy (GO's check on OB).
4. The PSF of OB equals DD13's PSF of O (peak to 1e-9 relative).
Fail: no loop runs; the miss is reported.

**Gate R14 (driver reproduction, blocking; frozen).** On `gate/O`, DD14's
loop code with QP12's rule, from DD13's QP12 cycle-11 gains and M₁₁
(DD13's `QP12/cycle-10/next_model.npy`), gives DD13's QP12
`cycle-11/next_model.npy` (M₁₂) bitwise (one image and one released
Högbom; no solve). Fail: no loop runs. `gate/O` is deleted after both gates.

## 3. Arms

All on OB, every arm from cycle 0 (no DD12 or DD13 prefix carries over:
the data differ). Cycle, Högbom, rule U (trusted gain amplitudes in
[1/3, 3], absolute, unchanged; the untrusted share is recorded), stops and
scored point are DD13's (sections 4-5 there), with DD13's stage stop
(after M₆, a loop arm with solves that reads "hurts" against Q6 stops; the
truth controls never stop).

| Arm | Image gains (trusted cells; untrusted → the arm's untrusted value) | Clean mask | Untrusted value | Eligible |
| --- | --- | --- | --- | --- |
| **Q12** (control) | g/\|g\| in cycles 0-1, g after | pins excluded | 1 | baseline |
| **QP12** (DD13's, frozen there) | g/\|g\| every cycle | pins released from cycle 2 | 1 | yes |
| **QPN12** (variant N) | √B_nom,f · g/\|g\| every cycle | pins released from cycle 2 | √B_nom,f | yes |
| **QPC12** (variant C, zero solves) | QP12's loop; at its final N, section 3's renormalisation | - | - | yes |
| **AT12** (control) | OB's truth | pins excluded | - | no |
| **ATP12** (control) | OB's truth | pins released from cycle 2 | - | no |
| **AX** (reference) | one scored solve with sky O as the model | - | - | no |

- **Shared prefixes on OB:** QP12's cycles 0-1 and cycle-2 solve are
  Q12's (DD13's relation, same code); QPN12's cycle-0 solve is Q12's (same
  model M₀ᶜ, same data); ATP12's cycles 0-1 are AT12's.
- **QPC12's renormalisation (frozen, truth-free).** It anchors each facet's
  scale to the catalogue flux of its pinned source when the loop's own model
  says that source is compact.
  - On QP12's final model M_N, per facet d1-d3, F_box is the flux in the
    pin's 5 × 5 box and F_ring the flux in the disc of radius 16 px round
    the pin.
  - The pin source is **compact** if F_box ≥ 0.8 F_ring and F_ring > 0.
  - Compact: r_f = S_pin / F_box, where S_pin is the pin's M₀ᶜ flux (the
    catalogue's S_app: 0.965, 0.098, 0.083 Jy). The facet's model is scaled
    by r_f and its scored gains by 1/√r_f.
  - Not compact, or no pin: r_f = 1 (QP12's convention stays, reported).
  - DD13 found d1's pin source resolved on O (box 0.66, ring 1.53 Jy in
    QP12's M₁₂), so d1 is expected to keep r = 1. That is a prediction
    from DD13's reading, not a rule input.
  - QPC12 changes neither the loop nor its solves. Its raw e_d is
    recomputed from the scaled gains; its scale-removed e_d (section 4)
    equals QP12's.
- **Not run:** anchoring the mean amplitude to the direction-independent
  solution. d0's truth amplitude is 1 in O and √B_true(ρ≈0) ≈ 1 in OB, so
  the anchor equals QP12's convention and cannot discriminate here.

## 4. Metrics

At every scored point (M₆ and M₁₂; a stopped arm at M₆):
- **DD13's set:** e_d (all unflagged cells), G_d, e on converged cells,
  e/ê, per-direction fractions, d3 |g| p99 and max, diagnostic D
  (amplitude bias b_d, phase-only e), untrusted shares, Högbom components
  and stop per cycle, and Γ against Q12 and the arm's matched truth control.
- **Scale-removed error (frozen).** The raw e_d carries any facet scale s
  as about |s − 1|, so it cannot read "closes" when the scale is the
  question.
  - Per direction d: `s_d = median(|P| / |P̄|)` over the unflagged cells,
    pairs and hands. P are the solved gain products and P̄ the truth
    products, as in DD5's e_d.
  - `e_d^sr = median(|P / s_d − P̄| / |P̄|)`.
  - Recorded: s_d, e_d^sr, and G^sr_d with A0's and AX's e^sr as references.
- **Facet flux scale (frozen).**
  - **Apertures.** From sky O only, before any run, per facet d1-d3:
    - discs of radius 16 px (48″);
    - centres at local maxima of sky O's 16 px disc-sum map (33 × 33
      maximum filter);
    - each disc inside the facet's interior, with a sky-O disc sum of at
      least 20 mJy;
    - taken brightest first, dropping any centre closer than 33 px to one
      already taken.
    - The disc that holds the pin pixel is the **pin aperture**; the rest
      are **non-pin**. The list goes into `apertures.json` with its SHA-256.
  - `F_f(M) = Σ` of model M over facet f's apertures.
  - **Raw error:** `ε_f(X) = F_f(M_X) / F_f(sky O) − 1`, reported.
  - **Offset response:** `κ_f(X) = F_f(M_X on OB) / F_f(M_X⁰ on O) − 1` at
    the same N, where X⁰ is the same arm on O from DD12's and DD13's kept
    models (zero solves): Q12 → DD12's Q12; QP12 → DD13's QP12; QPN12 →
    DD13's QP12 (with B ≡ 1 its rule is QP12's); QPC12 → QPC on DD13's
    QP12; AT12 and ATP12 → DD13's AT12 and ATP12. κ cancels the
    incompleteness and the pin error that the arm already has at a = 1.
  - **Flux-scale error (decision quantity):** `φ_f(X) = κ_f(X) − κ_f(C)`,
    where C is X's matched truth control: ATP12 for the released arms
    (QP12, QPN12, QPC12), AT12 for Q12. It is reported for all apertures
    (primary) and for the non-pin apertures alone.
  - **Expected, not a rule input:** QP12's κ ≈ B_f − 1 (−0.08, −0.19,
    −0.64); QPN12's ≈ B_true/B_nom − 1.

## 5. Readings (frozen)

- **Per-arm reading** (DD10's, on e^sr with OB's own A0 and AX): harm: e^sr_d
  > 1.2 e^sr_A0,d in d2 or d3; closes: G^sr_d1 ≥ 0.5 and no harm; partly:
  0.2 ≤ G^sr_d1 < 0.5 and no harm; moves the error: G^sr_d1 ≥ 0.2 with
  harm; no: G^sr_d1 < 0.2.
- **Effect against Q12** (DD12's rule on e^sr at matched N): helps, hurts,
  no effect, marginal, as DD13 section 6.
- **Criterion G (gains):** the arm at its final N reads closes or partly,
  and helps (marginal or not) against Q at the same N.
- **Criterion F (flux):** |φ_f| ≤ 0.05 in each of d1, d2 and d3 (primary
  apertures) at the arm's final N. The 5 % is about RACS's own flux-scale
  uncertainty (from recall: about 6 % for RACS-low): a recipe must not add
  a flux-scale error larger than the catalogue's. A facet whose truth
  control has F_f(M_C) ≤ 0.2 F_f(sky O) cannot be read and counts as a fail.

**DD14's answer (frozen), on OB:**

| Condition | Reading |
| --- | --- |
| QPN12 meets G and F | **in, with the beam in the model: QP12's rules go into the real DD recipe whose catalogue model is apparent through the nominal beam** (QPN12 represents it; section 2) |
| QPN12 fails F, QPC12 meets G and F | **in, with the catalogue renormalisation (QPC)** |
| QP12 meets G and F | also recorded: **the convention survives without the beam in the model** (not expected) |
| none of QPN12, QPC12 meets G and F | **out: QP12's convention moves the facet flux scale (φ given) or breaks the loop under the offset; the pinned rule stays in the recipe** |

QP12's own reading on F is reported in every case. If it fails F, that
confirms that the beam must be in the model for the unit-amplitude
convention. The real flux check (section 6) runs only on an "in" reading,
for the arm that gave it.

## 6. Real-data flux check (frozen before any look)

Only if section 5 reads "in". It is read-only scoring with zero solves, on
DD7's real subset field (ESO 137-006, the field DD11-DD13 used) and the
kept models:
- **Models.** RM, the start (d1-d3 equal to the catalogue by construction:
  a code check, ε = 0 to 1e-9). DD11's R-Q6 M₆ (pinned;
  `dd11-20261126/loop/R-Q6/cycle-5/next_model.npy`). DD13's R-QP12 M₁₂
  (`dd13-20261127/loop/R-QP12/cycle-11/next_model.npy`). For "in with QPC",
  QPC's renormalisation is applied to R-QP12's M₁₂ by section 3's rule.
- **Catalogue.** The model components in
  `results/dd4-eso137/catalogue-selection.json`, with their S_app.
- **Apertures.** Per facet d1-d3, 16 px discs at the pixel of each catalogue
  component with S_app ≥ 20 mJy whose disc lies in the facet's interior.
  Components brightest first; a component within 33 px of a taken one is
  merged into it (its S_app is added). The pin component's disc is the pin
  aperture.
- **Statistic.** `ε_f^real(M) = Σ M over the non-pin apertures / Σ S_app −
  1`, and the same for the pin aperture alone.
- **Matched resolution.** Integrated flux in 48″ discs. That is more than
  two RACS beams (RACS-low about 25″, RACS-mid about 10-15″, from recall),
  so the comparison is of integrated fluxes at the catalogue's resolution
  or coarser, not of peaks. Clean components are integrated flux already.
  The residual is not added: R-QP12 kept none.
- **Not blind.** The d1 pin aperture was read in DD13 (0.965 to 0.684 Jy),
  so the pin apertures are reported and not read. The reading uses the
  non-pin apertures only.
- **Reading (frozen).**
  - Per facet with at least one non-pin aperture: **agrees with the
    catalogue** if |ε^real_f(R-QP12)| ≤ 0.10. The 0.10 allows RACS's scale
    (about 6 %), the α interpolation and the loop's incompleteness.
  - **Agrees with the pinned loop** if |ε^real_f(R-QP12) − ε^real_f(R-Q6)|
    ≤ 0.05.
  - **Real check passes** if every readable facet agrees with the catalogue.
  - Otherwise: **the real facet flux scale differs from the catalogue** in
    the facets named. QP12's rules then wait for the cause (catalogue,
    beam or loop), whatever O and OB say.
- A facet with no qualifying non-pin component is reported as not readable.

## 7. Literature and novelty

- The flux-gain degeneracy per direction, and the need to fix each
  direction's flux scale by a model or a constraint, is standard in DD
  calibration (killMS/DDFacet, Tasse et al. 2018, A&A 611, A87; SAGECal;
  from recall). Applying the primary beam to the sky model is the usual way
  the scale is held.
- The MeerKAT L-band beam: Mauch et al. 2020, ApJ 888, 61 (the
  cosine-squared model). de Villiers & Cotton 2022, arXiv 2202.02101
  (holography; Stokes I elongated about 4 %; pointing σ 0.64′ giving power
  errors above 1 % near half power; verified by search 2026-11-27).
- No novelty is claimed. DD14 asks whether DD13's convention is safe for
  rang's recipe; it is a parity and safety step.

## 8. Implementation, host and cost

- `tools/oracles/dd14/dd14.py` (new, MIT) holds `beam`, `gates`, `insert`,
  `psf`, `apertures`, `loop` (Q12, QP12, QPN12, AT12, ATP12), `ax`, `diag`,
  `flux`, `score` and `real`. It imports DD13's, DD12's and DD11's drivers
  for the context, solves, images, `hogbom_fast` and scores. The loop is
  DD13's loop with the arm table above and the nominal-beam rule. There is
  no solver or library change.
- `tests/test_dd14.py` covers the beam rule (B ≡ 1 with zero ellipticity
  and zero pointing; the nominal values), the QN rule (√B_nom ≡ 1 reduces
  to QA bitwise), the aperture rule and QPC's renormalisation on small
  inputs.
- Python is this worktree's own `.venv` with its extension. Run root:
  `D:/rang/outputs/dd14-20261127/`.
- glacier, shared, under the main checkout's `tools/heavy_lock.py`:
  - loops 8 slots, 20 GB (DD13's figure);
  - the builds 2 slots, 16 GB; PSF 4 slots, 10 GB; gate R14 4 slots, 16 GB;
  - at most two loops at once. No exclusive or timing runs.
- **Run cap (Rust solves, one-longer solves counted):** Q12 15 (13 + 2), QP12
  12 (cycles 3-12, + 2), QPN12 14 (cycles 1-12, + 2), AT12 4, ATP12 4, AX 1:
  50, plus one spare per class (arms, controls): 52. A stopped arm uses
  fewer.
- Expected: a GS solve 520-800 s, Högbom 200-300 s per cycle; about 45,000 s
  of jobs, 6-8 h in two lanes. Wall times go into
  [tool-timings.md](tool-timings.md). The OB MS, `gate/O` and the PSF array
  are deleted at the end; records stay in the run root, a compact archive
  in `results/dd14-flux-scale/`.

## Amendments

**A1, 2026-11-27, clarifications found while writing the code, before the
simulation was generated and before any run. They change no decision
quantity's meaning.**
- **ρ_f** is catalogue.py's `hypot(l, m)` (radians to arcmin), not
  `asin(...)`. The frozen B_nom values (0.9175, 0.8129, 0.3607) are
  catalogue.py's, and the pins' S_app were made with them. The difference
  at d3 is 3e-5 in B.
- **The stage stop** reads DD12's effect rule on e^sr against Q12's cycle-6
  e^sr, the same quantity as section 5's effect. On OB the raw e_d carries
  the facet scale, so a raw stop would stop QP12 for the scale alone.
- **Section 6's catalogue flux per aperture** is the sum of S_app of every
  catalogue model component whose pixel lies inside the disc, at any flux.
  Components of at least 20 mJy only place and merge the centres. This
  makes RM's code check exact: RM holds every component at S_app in
  d1-d3.
- **Section 4's apertures:** on a plateau of the disc-sum map, the first
  maximum in row-major order is taken. Any maximum on a plateau encloses
  the same sky flux.

