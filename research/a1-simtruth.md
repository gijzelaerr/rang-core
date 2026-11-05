# A1: simulated truth for E1 and C2 to C7

Task A1 of [finish-plan.md](finish-plan.md), on branch `fp-a1-simtruth` from
main `9423f13`, 2026-11-06.

**Status: tolerances frozen (section 5) before any comparison; nothing
compared yet.** The design, the code and the small version exist; results
are added below the protocol in section 7, and section 5 changes only by a
dated, labelled amendment.

## 1. What it is

A simulated MeerKAT L-band observation in full polarisation, with known sky,
Jones terms, RFI and thermal noise, written as a Measurement Set through
rang's own casacore table writer (`rang.core_ms_write`). It meets A0's A1
requirements (`a0-acceptance.md`, "For the coordinator"):

| A0 requirement | Here |
| --- | --- |
| Full polarisation, linear feeds, MeerKAT 64-antenna geometry, 856–1712 MHz, ≥ 256 channels | XX, XY, YX, YY; `data/meerkat.itrf.txt` (64 dishes); 256 channels of 3.34375 MHz from 856 to 1712 MHz (small version: 16 antennas, 64 channels) |
| Per-antenna delays ±(1–10) ns; a bandpass with structure | \|τ\| uniform 1–10 ns, random sign, per antenna and hand; B with a level, slope, 25–60 MHz ripple, smooth terms, band-edge roll-off to 0.3 and phase ripple |
| KCROSS of a few ns; Xf of tens of degrees varying with frequency; Df 1–3 % per antenna, frequency-dependent | τ_c = 3.0 ns raw (array value); x(ν) phase 35° + 20° sin(…) + 8° x² + smooth (30° to 62° across the band in the full version); \|d\| in [1, 3] % per antenna and hand, smooth in frequency with a 40° phase wander |
| Unpolarised flux calibrator; polarised calibrator (3C 286-like, p 9.5 %, χ 33°) with ≥ 90° parallactic rotation over ≥ 3 scans | J1939−6342 with the SR2016 model (point); `3C286-SIM`: CARACal's `nrao_xcal.yml` Stokes I for 3C 286, p 9.5 %, χ 33°, RM 0, placed at Dec −20° so that its four scans span about 115° of parallactic angle (scan means −121°, −141°, 168°, 124° in the small version) |
| A gain calibrator; a target with compact and extended sources, some polarised | `SIM-GCAL` (4 Jy at 1.4 GHz, α −0.6, unpolarised); `SIM-TARGET` with 40 points (1–500 mJy), 5 Gaussians (20–120″) and an arc of 10 Gaussians (0.3 Jy); 5 points and 1 Gaussian polarised (p 2–15 %, RM −60 to 60 rad m⁻²) |
| RFI with a known mask | 6 persistent and 2 intermittent narrowband transmitters and broadband bursts, bit masks per cell |
| Thermal noise from which σ follows exactly | σ = SEFD / √(2 Δν Δt), SEFD 420 Jy, per real and imaginary part, every correlation (0.0574 Jy full, 0.0287 Jy small) |
| Seeds and provenance | section 4 and each run's `provenance.json` |

**Not simulated**, by design: primary beam (fluxes are apparent), time and
bandwidth smearing (point evaluation at channel and integration centres),
autocorrelations, w-projection effects beyond the exact DFT phase, ionospheric
Faraday rotation, second-order leakage (section 2.4) and any flags in the
input (FLAG is all false).

## 2. Conventions (the truth's measurement equation)

### 2.1 Chain

C1's equation (`c1-calibration-chain.md`, 1.1) in CASA's type order, with
KCROSS in the K slot, ahead of D:

```
V_pq = J_p M_pq J_q^H,    J_p = B_p K_p Kc G_p S_p D_p X P_p     (p = ANTENNA1)
```

- `M`: sky-frame coherency, `XX = I+Q`, `XY = U+iV`, `YX = U−iV`, `YY = I−Q`.
- `P_p = [[cos a, sin a], [−sin a, cos a]]`, `a = q_p(t) + RECEPTOR_ANGLE`.
  `q_p` is the geodetic parallactic angle at antenna p (`rang.measures`,
  astropy) and `RECEPTOR_ANGLE = −π/2` on both receptors, written to FEED, as
  CARACal sets it (`feed_angle_rotation: -90`). So E1 runs in E2-B's frame.
- `X = diag(x(ν), 1)` (Xf) and `Kc = diag(exp(2πi τ_c (ν − ν₀)), 1)`
  (KCROSS): one value for the array.
- `D`: CASA's linearised Df operator at D's place (2.4).
- `G_p = diag(g_x, g_y)(t)`, `S_p` a scalar on the target only (2.3).
- `K_p = diag(exp(2πi τ (ν − ν₀)))`, `ν₀ = CHAN_FREQ[nchan // 2]`
  (1285.67 MHz full, 1290.69 MHz small), as CASA's K table pivot; τ in ns.
- `B_p = diag(b_x(ν), b_y(ν))`, constant in time.

DATA = c64(V + RFI + noise): RFI and noise are added after corruption.

### 2.2 Geometry and time

- Epoch 2024-08-18, track 19:09–22:20 UTC (LST 18.4–21.6 h). The date lies
  inside both astropy's IERS tables (astropy-iers-data 0.2026.11.2) and the
  CASA image's `IERSeop2000` (to MJD 60854), so neither extrapolates.
- 23 scans, `FXGTGTGXGTGTGXGTGTGTGXF` (F flux, X polarised, G gain
  calibrator, T target), 8 s integrations, 24 s slews. Full lengths:
  F 45, X 30, G 15, T 150 integrations (1,410 in all, 3.28 h). The small
  version keeps each scan's start time and its first 6, 4, 2 and 8
  integrations (104 in all), so it keeps the parallactic coverage.
- UVW in the ICRS axes from each antenna's GCRS position (astropy),
  `uvw = uvw(ANTENNA1) − uvw(ANTENNA2)`, visibility phase
  `+2π(ul + vm + w(n−1))ν/c`, as the gemclean simulator and rang's imaging.
- STATE rows carry MeerKAT-style intents; FIELD has the four fields.

### 2.3 Time behaviour of the gains (why it is shaped like this)

Class T asks noise-free solutions within 1e-5 of truth, so the truth has to
lie inside the solve's model:

- **G amplitude** constant per antenna and hand over the track.
- **G phase** constant within each calibrator scan (a random walk of 25°
  common and 5° per hand from scan to scan). On the target it is linear in
  time between the neighbouring gain-calibrator scans' mean times (CASA's
  `linear`), nearest before the first and after the last.
- **S** (the self-calibration residual, target only): a scalar per antenna,
  phase 5–15° in two sinusoids, amplitude 0.5–2 %, constant over blocks of 8
  integrations from each target scan start. Scalars commute with every
  term, so S's place in the chain does not matter.
- K, B, KCROSS, Xf and Df are constant in time.

### 2.4 Leakage

CASA's Df apply is first order (`caltable.py`, `JonesGenLin`). The truth
uses the same operator, so `applycal` inverts it exactly:

```
XY += d_x,p YY + conj(d_y,q) XX      YX += d_y,p XX + conj(d_x,q) YY      (XX, YY unchanged)
```

applied to `X P M Pᴴ Xᴴ`. The full matrix `[[1, d_x], [d_y, 1]]` would add
d × (cross hands) to the parallel hands and second-order terms: about
d·p·I, up to 0.3 % of I on the polarised calibrator. **Those are absent by
construction**; a test bounds the difference (`test_linear_leakage_against_matrix_chain`).

### 2.5 Gauge and reference antenna

Raw truth has no gauge. `rang.simtruth.casa_gauge(truth, refant, ν, ν₀)`
returns it in CASA's gauge:

- K, G and B are referenced per hand: `τ_r = 0`, phases divided by the
  refant's.
- The removed common factor `diag(u_x, u_y)` is moved right through D:
  `d_x → e d_x`, `d_y → conj(e) d_y`, with `e = u_x conj(u_y)`.
- Its part linear in frequency from K goes to KCROSS:
  `τ_c' = τ_c + τ_x,r − τ_y,r`. The rest, the refant's B and G X−Y phase,
  goes to Xf.
- Then CASA's subtractive Df reference is applied:
  `d_x,p −= d_x,r`, `d_y,p += conj(d_x,r)`.

**This split of the cross-hand phase is an assumption.** KCROSS sits before
D and Xf after it, so D in CASA's gauge depends on the split.

The reference antenna is **m000 (index 0)**. Its truth is built so that its
gauge is clean:

- its B and G phases are equal in X and Y, so referencing moves only its
  X−Y delay (−0.057 ns full, −1.18 ns small) into KCROSS;
- its `d_x` is zero, so the subtractive Df reference is the identity.

`test_casa_gauge_is_the_same_chain` checks that corrupting with the
gauge-transformed terms gives the same visibilities to 1e-10.

A consequence for E1: with an unpolarised leakage calibrator (CARACal's
strategy 1), any `d_x,r ≠ 0` is unobservable and leaves an error of about
`2 d_x,r Q` in the cross hands of polarised sources. With m000 as refant the
truth has `d_x,r = 0`, so E1 tests implementation rather than that known
limit. Another refant reintroduces it (about 0.2 points of p on 3C 286 for
`|d_x,r|` = 2 %).

## 3. Files

Under `/mnt/d/rang/outputs/fp-a1-20261106-simtruth/` (ignored, on D:):

| Path | Contents |
| --- | --- |
| `small/a1-small.ms`, `small/a1-small-twin.ms` | 16 antennas, 64 channels, 104 integrations; the twin is noise- and RFI-free |
| `full/a1-full.ms` | 64 antennas, 256 channels, 1,410 integrations |
| `full/a1-full-twin.ms` | noise- and RFI-free subset of the full version (section 6) |
| `*/truth.npz`, `*/truth.json` | the truth (below) |
| `*/<name>.rfi_mask.npz` | `any` and `above_5sigma`: `np.packbits(mask[row, chan], axis=1)` in MS row order, `nchan`, `row_tindex` |
| `*/<name>.provenance.json` | seeds, argv, commit, versions, timings, size, RFI fractions, parallactic and elevation ranges, SHA-256 of the truth files (and of every MS file for the small version) |
| `casa-*/` | CASA's tables made from the truth, logs, exports, timings |

**`truth.npz`** (all float64 / complex128):

| Key | Shape | Meaning |
| --- | --- | --- |
| `raw_tau_ns` | (ant, 2) | K delays, X and Y |
| `raw_k` | (ant, chan, 2) | K phasors with ν₀ |
| `raw_bandpass` | (ant, chan, 2) | B |
| `raw_gain` | (int, ant, 2) | G per integration (all integrations of the version) |
| `raw_selfcal` | (int, ant) | S (1 off the target) |
| `raw_selfcal_block` | (int,) | S block per integration (−1 off the target) |
| `raw_gain_phase_scan`, `raw_scan_time` | (scan, ant, 2), (scan,) | per-scan phases (rad) and mean scan times |
| `raw_kcross` | (chan,) | `exp(2πi τ_c (ν − ν₀))` |
| `raw_xf` | (chan,) | x(ν) |
| `raw_leakage` | (ant, chan, 2) | d_x, d_y |
| `gauge0_*` | as above | the same in CASA's gauge for m000 (`tau_ns`, `k`, `bandpass`, `gain` with S folded in, `kcross`, `xf`, `leakage`) |
| `time`, `scan`, `field`, `within_scan` | (int,) | schedule |
| `parallactic_angle` | (int, ant) | q_p (rad), without the receptor angle |
| `receptor_angle` | (2,) | −π/2, −π/2 |
| `uvw_antenna` | (int, ant, 3) | per-antenna UVW (m) |
| `elevation_deg` | (int,) | at the array centre |
| `freq_hz`, `nu0_hz`, `sigma_jy`, `antenna_index` | | |
| `calibrator_stokes` | (field, chan, 4) | I, Q, U, V of the three calibrators |

**`truth.json`**: the design, fields, calibrator models, every target
component (l, m, RA, Dec, flux at 1.284 GHz, α, FWHM, p, χ₀, RM), every RFI
event (channels, per-integration amplitude, baseline cut-off and decay,
direction, polarisation), antenna names, the module's conventions text and
the gauge facts.

**CASA tables of the truth**: `casa-*/truth.{K,B,G,Kcross,Xf,Df}`, raw
truth. Each is a table CASA made by a template solve, with every parameter
overwritten (`examples/a1_simtruth_casa.py`). G has one row per integration
and S folded in.

## 4. Seeds and regeneration

| Version | jones | sky | rfi | noise |
| --- | --- | --- | --- | --- |
| full | 20261106 | 20261107 | 20261108 | 20261109 |
| small | 20261116 | 20261117 | 20261118 | 20261119 |

Noise is drawn per integration from `default_rng([noise seed, integration
index])`, so any subset of integrations reproduces the same noise rows. RFI
amplitudes are per-integration arrays fixed by the rfi seed. On this host:

```sh
.venv/bin/python examples/a1_simtruth.py size full
.venv/bin/python examples/a1_simtruth.py generate small OUT/small --hash-ms
.venv/bin/python examples/a1_simtruth.py generate small OUT/small --noiseless --hash-ms
flock ~/.rang-heavy.lock .venv/bin/python examples/a1_simtruth.py generate full OUT/full --workers 8
flock ~/.rang-heavy.lock .venv/bin/python examples/a1_simtruth.py generate full OUT/full --noiseless --scans 1,2,3,4 --max-per-scan 16
```

Bit-identical regeneration on another host is not claimed: the DFT and the
trigonometry go through libm. The SHA-256 values in `provenance.json` are for
this host.

## 5. Checks and tolerances (frozen before any comparison)

Written and committed before the first comparison. ε₃₂ = 2⁻²³ ≈ 1.19e-7.

1. **Round trip, class C (C1, adopted by A0).** On the noiseless twin, CASA
   6.7.6.14 runs `applycal` with the six truth tables:
   - `interp` nearest, `calwt=False`, `parang=False`, `applymode='calflag'`.
   - The reference is `P_p M P_qᵀ` in float64, from the sky model and the
     saved angles, not from rang's `correct`.
   - Pass when **every element** (row, channel, correlation) satisfies
     `|CORRECTED − ref| ≤ max(1e-6·|ref|, 11·ε₃₂·max over the cell's four correlations of |ref|)`.
     The second clause covers the zero cross hands of unpolarised sources.
   - **Flags exact:** CASA's FLAG equals the input's (all false).
   - CASA's DATA is unchanged, bit for bit, from the twin's.
   - Run on the small twin (every row) and on the full twin (section 6).
2. **Parallactic frame (an extra, for C1's open P check).** The same with
   `parang=True` against `M`:
   - on the flux calibrator, where P cancels, class C as in 1;
   - on the polarised calibrator, the implied angle error
     `δ = median |Δ(Q′ + iU′)| / (2 |Q′ + iU′|)` over its cells, from the
     cross hands, must be ≤ 0.3°. The bound covers astropy's geodetic frame
     against CASA's measures (up to about 0.2°, C1 section 8) and per-antenna
     against array-centre angles (≤ 0.07° at 8 km). A wrong sign or receptor
     angle gives tens of degrees.

   This tests the truth's P against CASA's, not rang.
3. **`listobs`.** CASA's `listobs` exits 0 on the small and the full MS and
   lists 23 scans, 4 fields, 4 correlations and the version's channel count.
4. **Noise.** On `DATA − twin DATA`, over the cells outside the RFI `any`
   mask, pooling real and imaginary parts of all four correlations (N
   values):
   - the sample standard deviation s gives `z = (s − σ) / (σ / √(2(N−1)))`;
   - the mean gives `z_μ = mean / (σ / √N)`.

   Pass when `|z| ≤ 3` and `|z_μ| ≤ 3`; both are reported, whatever they are.
   Three standard errors, not one: an honest draw fails a 1-SE gate about 32 %
   of the time. This is the bound A0's class T uses.
5. **Twin consistency.** On the twin's rows, the full or small MS's DATA
   equals `c64(V + RFI + noise)` recomputed from the truth and the seeds:
   - maximum absolute difference 0;
   - and the twin's DATA equals `c64(V)` with difference 0.
6. **Self-checks** (`tests/test_a1_simtruth.py`, NumPy, every check-all):
   - corrupt then exact correct: ≤ 1e-12 relative;
   - the gauge chain against the raw chain: ≤ 1e-10;
   - linear Df against the full matrix: within the first-order cross-hand
     and second-order bound;
   - the target prediction against a NumPy DFT: ≤ 1e-9;
   - noise keyed by integration, its σ within 4 SE;
   - RFI only in its events' channels;
   - the polarised calibrator spans ≥ 90° over ≥ 3 scans.

## 6. Size (stated before writing the full version)

| Version | Rows | Channels | Estimate as written (DATA, WEIGHT_SPECTRUM, FLAG, row columns) | With MODEL_DATA and CORRECTED_DATA added by a chain |
| --- | ---: | ---: | ---: | ---: |
| full | 2,842,560 (2,016 baselines × 1,410) | 256 | **38.3 GB** | 84.9 GB |
| small | 12,480 (120 × 104) | 64 | 43.5 MB | 94.6 MB |

The full version is under 150 GB, so the time sampling is not reduced. The
full twin is scans 1 to 4 (one of each field) with their first 16
integrations each: 64 integrations, 129,024 rows, about 1.7 GB.

## 7. Results

None yet.

## For the coordinator

To be completed with the results.
