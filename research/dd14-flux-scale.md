# DD14: QP12's facet flux scale when the true facet amplitudes are not 1

Issue #15. Follows [dd13-absorb.md](dd13-absorb.md) (DD13),
[dd12-msclean.md](dd12-msclean.md) and [dd11-start.md](dd11-start.md).
Branch `dd14-flux-scale`. Coordinator brief 2026-11-27. Sections 1-8 are
frozen 2026-11-27, before the code that runs them, before the simulation is
generated and before any measurement. Later changes are dated amendments,
committed before the reading they affect, and labelled post hoc where they
follow a reading.

Status: **measured 2026-11-28.**
- **Frozen answer: "out".** No arm meets criteria G and F at N = 12, so
  the pinned rule stays in the recipe. Section 6's real flux check does not
  run.
- **d3 decides the reading.** On OB (B_nom 0.36) no arm calibrates d3, the
  truth controls included: e^sr_d3 is 0.89-1.25 against AX's 0.145. Every
  arm, AT12 and ATP12 among them, reads "hurts" against Q12 only through
  the d3 clause.
- **In d1 and d2 (reported post hoc, A3) the degeneracy behaves as
  predicted.**
  - QP12's facet scale takes the beam. Its gain scale s is 1.093 and 1.212,
    so the model scale 1/s is 0.915 and 0.825, against B 0.918 and 0.813.
    Its pin aperture flux is −9 % and −18 % against QP12 on O.
  - QPN12 (the nominal beam in the image gains, the real recipe's case)
    holds the scale: s 0.994 and 0.983, pin aperture −1 % and −3 %.
  - QPN12 keeps QP12's gain win: d1 e^sr 0.141 against Q12's 0.356,
    G^sr 0.70.
- **QPN12's released d3 pin builds a spurious excess.** Its pin aperture
  holds 0.114 Jy at M₆ and 0.262 Jy at M₁₂, against the sky's 0.088 Jy.
  QPN6 met G and F; QPN12 does not.

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

## 9. Measured result

Run root `D:/rang/outputs/dd14-20261127/`. Host glacier, shared, under the
main checkout's `heavy_lock.py`; two lanes, every loop 8 slots, 20 GB
booked. Archive `results/dd14-flux-scale/`: `score.json`, `beam.json`,
`apertures.json`, the gates, per-cycle `info.json`, `times.log` and the
scripts.

**Setup and gates, all pass.**
- **Beam rule** (`beam.json`, written before the MS):
  - Per-facet means of B_true/B_nom: d1 0.998, d2 1.006, d3 1.004.
  - Per antenna and block, p5-p95: 0.988-1.007 (d1), 0.992-1.022 (d2),
    0.968-1.037 (d3).
  - Parallactic angle −65.0° to −46.9° over the track.
  - Truth amplitude geometric means d0-d3: 1.000, 0.955, 0.909, 0.599.
- **GB 1:** DD8's O rebuilt. `build.json` equals DD13's and the sky
  SHA-256 is DD8's.
- **GB 2:** at B ≡ 1, DD14's builder differs from `gate/O` by at most
  7.6e-6 Jy.
- **GB 3:** OB's DATA minus n minus the predict is at most 2.7e-6 Jy.
- **GB 4:** the PSF peak is 1.0, equal to DD13's.
- **R14:** DD13's QP12 cycle-11 image and released Högbom reproduce DD13's
  M₁₂ bit for bit (150 components). The QN rule at B ≡ 1 is bitwise the QA
  rule.
- No arm stopped at the stage rule.

**References on OB** (for AX, e^sr equals the raw e to 1e-3):
- A0 (Q12's cycle-0 solve): e 0.354, 0.634, 1.019; e^sr 0.451, 0.663,
  1.366; s 0.842, 0.912, 0.242; 81 % of d3's gains untrusted.
- AX: 0.0086, 0.041, 0.145. On O it was 0.0078, 0.033 and 0.052, so d3 is
  worse by about 1/B_d3.

### The arms (d1, d2, d3; truth s = 1)

| Point | e d1-d3 (raw) | e^sr d1-d3 | s d1-d3 | G^sr d1 | Reading (sr) | Against Q (sr) | φ d1-d3 (all apertures) | G | F |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Q6 | 0.339, 0.308, 1.312 | 0.359, 0.307, 1.091 | 0.977, 1.003, 1.382 | 0.209 | partly | - | −0.127, 0.044, −0.491 | - | no |
| Q12 | 0.315, 0.328, 1.318 | 0.356, 0.282, 0.886 | 0.959, 1.082, 1.787 | 0.215 | partly | - | −0.075, 0.191, −0.466 | - | no |
| QP6 | 0.169, 0.418, 1.428 | 0.125, 0.295, 1.222 | 1.093, 1.197, 1.310 | 0.736 | closes | helps (0.35 ×) | 0.015, −0.016, −0.764 | yes | no |
| **QP12** | 0.147, 0.424, 1.721 | **0.099**, 0.285, 1.067 | **1.093, 1.212**, 1.939 | 0.795 | closes | **hurts** (d1 0.28 ×, d3 1.20 ×) | 0.050, 0.047, −0.722 | **no** | **no** |
| QPC6 | 0.169, 0.296, 1.014 | as QP6 | 1.093, 1.003, 0.454 | 0.736 | closes | helps (0.35 ×) | 0.015, 0.153, −0.314 | yes | no |
| **QPC12** | 0.147, 0.289, 1.721 | as QP12 | 1.093, 1.009, 1.939 | 0.795 | closes | **hurts** (as QP12) | 0.050, 0.234, −0.722 | **no** | **no** |
| QPN6 | 0.148, 0.318, 1.048 | 0.149, 0.322, 1.288 | 0.996, 0.982, 0.496 | 0.683 | closes | helps (0.42 ×) | −0.020, −0.027, 0.029 | yes | yes |
| **QPN12** | 0.140, 0.308, 1.136 | 0.141, 0.312, 1.249 | **0.994, 0.983**, 0.806 | 0.700 | closes | **hurts** (d1 0.40 ×, d3 1.41 ×) | −0.031, −0.054, **1.057** | **no** | **no** |
| AT6 (control) | 0.125, 0.271, 1.002 | 0.151, 0.274, 1.220 | 0.943, 0.980, 0.312 | 0.678 | closes | helps (0.42 ×) | - | - | - |
| AT12 (control) | 0.113, 0.252, 0.999 | 0.135, 0.254, 1.158 | 0.952, 0.990, 0.387 | 0.715 | closes | hurts (d3 1.31 ×) | - | - | - |
| ATP6 (control) | 0.085, 0.217, 1.002 | 0.091, 0.212, 1.225 | 0.980, 1.029, 0.317 | 0.814 | closes | helps (0.25 ×) | - | - | - |
| ATP12 (control) | 0.084, 0.214, 1.001 | 0.090, 0.210, 1.216 | 0.980, 1.031, 0.325 | 0.817 | closes | hurts (d3 1.37 ×) | - | - | - |

QPC's factors r (d1, d2, d3):
- at M₆: 1 (d1 resolved), 1.193, and 2.888 for d3 (box 0.029 Jy against
  S_pin 0.083 Jy);
- at M₁₂: 1, 1.202, 1 (d3 not compact: box 0.028 Jy, disc 0.039 Jy);
- on O: 1, 0.985, 1.

**Frozen readings.**
- **Criterion G fails at N = 12** for QP12, QPC12 and QPN12. Each reads
  "closes" on e^sr, but "hurts" against Q12 through the d3 clause: e^sr_d3
  is 1.067, 1.067 and 1.249 against Q12's 0.886, with the bar at 1.2 ×.
- **Criterion F fails** for all three on d3 (φ −0.722, −0.722, +1.057).
  QPN12 also misses on d2, by 0.004 (−0.054); QPC12 fails on d2 (0.234).
- d3 is readable: the truth controls hold 0.43 and 0.38 of sky O's
  aperture flux.
- **Answer (frozen table): "out: QP12's convention moves the facet flux
  scale or breaks the loop under the offset; the pinned rule stays in the
  recipe."** QP12 does not survive without the beam in the model, and
  section 6 does not run.
- QPN6 met G and F at N = 6, but the frozen final N is 12.

### Reading the result (post hoc, A3; changes no frozen reading)

- **d3 on OB is below what this loop can calibrate.** Its apparent signal
  is 0.36 of O's.
  - e^sr_d3 is 0.89-1.25 for every arm and control (A0 1.37), against
    0.27-0.32 on O.
  - AX's d3 error rises from 0.052 to 0.145, and d3's e/ê is 9-24.
  - Even the truth-gain loops end at s_d3 0.33-0.39.
  - For A0 and both controls e^sr_d3 exceeds the raw e_d3: where s is far
    from 1 because the solve failed, dividing by s amplifies the error. G's
    d3 clause therefore compares values set by s.
  - **The truth controls could not pass criterion G at 12 either**, so the
    clause cannot separate the arms on OB.
- **φ is not a clean scale measure in d1 and d2.** It mixes scale with
  completeness: at the lower signal-to-noise the controls lose faint flux.
  - ATP12's κ is −0.09 and −0.20 while its gain scale s is 0.98 and 1.03.
  - QP12's small φ in d1 and d2 (0.050, 0.047) is a coincidence of the two
    losses, not a right scale.
  - The images are amplitude-corrected (`dd2.correction` mode `a` divides
    by the row-weighted mean of |g_p|²|g_q|²), so the truth images are in
    intrinsic units; that was checked.
- **Two clean scale measures**, both recorded quantities (s in section 4,
  the pin aperture in `flux.pin`):
  - **Gain scale s** (truth = 1):
    - QP12: 1.093 and 1.212 in d1 and d2. 1/s is 0.915 and 0.825, which is
      the beam (0.918, 0.813).
    - QPN12: 0.994 and 0.983.
    - ATP12: 0.980 and 1.031.
    - QPC12: d2 1.009, renormalised by d2's compact pin. d1 keeps QP12's
      value because its pin is resolved, as DD13 predicted.
  - **Pin aperture κ** (bright sources, against the same arm on O): QP12
    −0.089 and −0.180; QPN12 −0.014 and −0.033; ATP12 −0.004 and −0.010.
  - The non-pin (faint) apertures are dominated by completeness: ATP12
    −0.30 and −0.26.
- **In d1 and d2, then:**
  - unit-amplitude images put the beam into the flux scale exactly, as the
    degeneracy says (−8 % and −19 %);
  - with the nominal beam in the image gains (QPN12) the scale is within
    1-3 % of the truth, inside the 5 % bar;
  - QP12's gain win survives: d1 e^sr 0.141, against Q12's 0.356 and
    ATP12's 0.090.
- **QPN12's d3 grows a spurious pin excess.**
  - The released d3 pin aperture holds 0.114 Jy at M₆ and 0.262 Jy at M₁₂,
    against the sky's 0.088 Jy and QP12-on-O's 0.106 Jy.
  - Over the same cycles d3's s climbs from 0.24 to 0.81, and its untrusted
    share falls from 81 % to 39 %.
  - Högbom adds 1,000-1,400 components in cycles 8-9, and d3's net flux
    goes from 0.243 to 0.376 Jy. d3 had not converged at 12.
  - Releasing a pin in a facet on the beam's flank, with the scale held only
    by the image-gain convention, lets the gains and the compact model trade
    there. For the recipe this is a finding, not noise.
  - QP12 (no beam) loses d3's pin flux instead (0.031 Jy).
- **QPC's compactness test is unstable at this signal-to-noise:** d3 is
  compact at M₆ (r 2.89) and not at M₁₂.

**Cost.** Loop walls, 8 slots booked, lock waits included:

| Run | Wall (s) |
| --- | --- |
| Q12 | 15,164 |
| QP12 | 10,841 |
| QPN12 | 12,359 |
| AT12 | 5,971 |
| ATP12 | 4,170 |
| AX | 694 |

- Prep: 491 s in all (beam 1, apertures 7, GB 1 238, build 96, PSF 37,
  R14 112).
- Solves used: Q12 15, QP12 12, QPN12 14, AT12 4, ATP12 4, AX 1. That is 50
  against the cap of 52.

## 10. For the coordinator

- **Frozen answer: "out".** On DD14's evidence QP12's rules do not go into
  the real DD recipe, and the real flux check (section 6) does not run.
  d3 decides it: on OB (B 0.36) no arm calibrates d3, the truth controls
  included, so G's d3 clause and F's d3 term fail everywhere.
- **What it does show (post hoc).** In d1 and d2 the unit-amplitude
  convention moves the facet scale by exactly the beam: QP12's 1/s is 0.915
  and 0.825, against B 0.918 and 0.813.
- **The nominal beam in the image gains holds it.** QPN12, the case of the
  recipe's apparent catalogue model, stays within 1-3 % and keeps the d1
  gain win.
- **QPN12's released d3 pin grows a 3 × compact excess** by M₁₂. Pin
  release needs a guard in facets at low beam response.
- **The frozen metric φ mixes completeness with scale.** A successor should
  read the gain scale s and the bright (pin) apertures.
- **Recommended next step: DD15**, frozen before it runs:
  - QPN-style rules (nominal beam in the image gains, pins released) only
    in facets with B_nom ≥ 0.5, the pin kept where B_nom is lower;
  - the scale read from s and the pin apertures;
  - G's d3 clause replaced by a rule the truth control can pass;
  - then section 6's real check.

  The alternative is to close #15's convention question as "beam in the
  model required; release pins only where the beam response is high". That
  choice is the owner's or the coordinator's.

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

**A2, 2026-11-28, a data-path fix in `score`, plus a header typo. Neither
changes a rule.**
- The first score run crashed before it wrote anything (`rc=1` in
  `times.log`). DD13's run root holds no copies of DD12's Q12 and AT12
  models, only DD13's own arms. Section 4 already names DD12's Q12 as Q12's
  reference. AT12's reference is now also read from DD12's root, where
  DD13's bitwise copy came from (DD13's `reuse.json`).
- The header said "sections 1-9 are frozen". The frozen sections are 1-8,
  and section 9 is the measurement.

**A3, 2026-11-28, post hoc diagnostics, after the frozen reading. They
change no frozen reading.** The pin and non-pin κ were printed separately,
`cycles_QPN12` was read, and `dd2.correction` mode `a` was checked.
Section 9's "Reading the result" reports them.
