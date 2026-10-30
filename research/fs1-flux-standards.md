# FS1: flux-density standards in the core, with CASA `setjy` as the oracle

Protocol frozen 2026-10-30 on branch `fs1-flux-standards` (from `56248df`),
before any flux-standard code. Task FS1 of the ecosystem survey
([ecosystem-survey.md](ecosystem-survey.md), section "Flux standards in the
core"), with the O-CASA oracle ([o-casa.md](o-casa.md)) as its precondition.
Status at freeze: proposed; nothing implemented, one probe run (below).

## Why

The core predicts component models (`core/src/predict.rs`, `rangtoy.lsm`)
but has no flux-density standards: a calibrator's flux per channel comes from
a stored MODEL_DATA of unknown origin or an ad hoc fit. CARACal sets it with
CASA `setjy`. FS1 ports the standards `setjy` uses for the MeerKAT
calibrators and checks them against `setjy` itself.

## What the image can and cannot oracle (probe, 2026-10-30)

A probe in `rang-o-casa:6.7.6.14` (`--network none`) on a two-antenna
simulated MS (casatools `simulator`), fields 3C286 and 1934-638, one
11-channel 0.8–1.8 GHz SPW, `setjy(..., scalebychan=True, usescratch=True)`:

| `standard` | 3C286 | 1934-638 |
| --- | --- | --- |
| `Perley-Butler 2010` | 18.8069 Jy at 0.8 GHz | 13.4983 Jy |
| `Baars` | 19.1707 Jy | 13.9289 Jy |
| `Stevens-Reynolds 2016` | **1.0 Jy**, SEVERE "3C286 is not recognized by Stevens-Reynolds 2016", no exception | 13.4983 Jy |
| `Perley-Butler 2013` | returns `{}`, SEVERE "coefficient data ... PerleyButler2013Coeffs is not found in the current directory or in datapath/measurespath", no exception | same |
| `Perley-Butler 2017` | same with `PerleyButler2017Coeffs` | same |
| `Scaife-Heald 2012` | same with `ScaifeHeald2012Coeffs` | same |

PB2010, Baars and SR2016 are compiled into casatools (CASA docs, "Flux
Calibrator Models": "hard-coded in the code"); PB2013, PB2017 and SH2012 are
CASA tables in `casarundata` (`nrao/VLA/standards/`), which the image does not
carry: its measures path is Ubuntu's `casacore-data` (ephemerides and
geodetic only). A bounded search of the WSL home and `/mnt/c/Users/gijsm`
found no copy. Fetching `casarundata` is a download the user has to approve;
the image is network-none by design. So:

- **Oracled now:** PB2010, Baars, SR2016, and `standard='manual'` (CARACal's
  Reynolds 1994 model).
- **Oracle pending (blocked on the user):** PB2017 and PB2013. The unblock
  step needs no rebuild: CASA also searches the *current directory*, so the
  `PerleyButler2017Coeffs` / `PerleyButler2013Coeffs` table directories are
  mounted read-only into the container's working directory and
  `examples/oracle_setjy.py` runs its pending arms unchanged. Their columns
  are inspected then (epoch-dependent terms for the variable sources are
  possible in CASA's table and are not assumed absent or present).

## Standards and polynomials

Notation: `x = log10(ν / GHz)`, `y = log10(ν / MHz) = x + 3`. Logarithms base
10 throughout unless stated; S in Jy.

1. **Reynolds 1994** (ATNF memo AT/39.3/040), PKS 1934−638, as carried by
   CARACal (`southern_calibrators.txt`, `PKS1934-63 epoch=1994`):
   `log10 S = −30.7667 + 26.4908 y − 7.0977 y² + 0.605334 y³`. Validity: the
   memo's fit range (about 0.4–9 GHz); CASA documents SR2016 as using
   "Reynolds" below 11 GHz.
2. **CARACal manual model** (`setjy standard='manual'`), O-CASA's frozen
   values: `S(ν) = S0 (ν/ν0)^(Σ_k spix_k log10(ν/ν0)^k)`, i.e.
   `log10 S = log10 S0 + Σ_k spix_k log10(ν/ν0)^(k+1)`, with
   S0 = 14.907688923 Jy, ν0 = 1.4 GHz, spix = [−0.19473727, −1.38432520,
   0.60533435, 1.43e−06] (O-CASA measured CASA's `spix` to be log10).
   No range; it is a polynomial in log frequency everywhere.
3. **Stevens-Reynolds 2016** (CASA; one source, 1934−638): the Reynolds
   polynomial below 11 GHz and Stevens' higher-frequency polynomial above
   (CASA docs). O-CASA measured it equal to (1.) to 2.7e-6 relative on
   0.86–1.71 GHz and bit-identical to PB2010 there. The coefficients CASA
   uses are compiled in; FS1 does not copy casatools source. They are
   **recovered** from `setjy`'s double-precision `fluxd` values (below) by a
   least-squares fit of the stated form, expected to land on short decimals;
   the low piece is compared with (1.) and the 2.7e-6 residual must be
   reproduced, not tightened. The Stevens piece's published text is not in
   hand; its coefficients are recorded as CASA's, with that provenance.
4. **Perley-Butler 2010** (VLA; CASA compiled): `log10 S = Σ_k a_k x^k`
   (form per CASA docs), coefficients per source recovered as in (3.); the
   sources are whatever `setjy` recognises among the names tried (3C48,
   3C138, 3C147, 3C286, 3C295, 3C196, 3C123, 3C380, 1934−638 and aliases).
5. **Baars et al. 1977** (A&A 61, 99): `log10 S = a + b y + c y²` (ν in MHz),
   valid 408 MHz–15 GHz per CASA docs; coefficients recovered as in (3.). CASA
   also answers for 1934−638 under "Baars", which Baars et al. did not
   publish; recorded as CASA behaviour, not as a paper value.
6. **Perley & Butler 2017** (ApJS 230, 7; arXiv:1609.05940, Table 5, text in
   hand from the arXiv PDF): `log10 S = Σ_k a_k x^k`, coefficients as printed:

   | Source | a0 | a1 | a2 | a3 | a4 | a5 | range (GHz) |
   | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
   | J0133−3629 | 1.0440 | −0.662 | −0.225 | | | | 0.2–4 |
   | 3C48 | 1.3253 | −0.7553 | −0.1914 | 0.0498 | | | 0.05–50 |
   | Fornax A | 2.218 | −0.661 | | | | | 0.2–0.5 |
   | 3C123 | 1.8017 | −0.7884 | −0.1035 | −0.0248 | 0.0090 | | 0.05–50 |
   | J0444−2809 | 0.9710 | −0.894 | −0.118 | | | | 0.2–2.0 |
   | 3C138 | 1.0088 | −0.4981 | −0.155 | −0.010 | 0.022 | | 0.2–50 |
   | Pictor A | 1.9380 | −0.7470 | −0.074 | | | | 0.2–4.0 |
   | Taurus A | 2.9516 | −0.217 | −0.047 | −0.067 | | | 0.05–4.0 |
   | 3C147 | 1.4516 | −0.6961 | −0.201 | 0.064 | −0.046 | 0.029 | 0.05–50 |
   | 3C196 | 1.2872 | −0.8530 | −0.153 | −0.0200 | 0.0201 | | 0.050–50 |
   | Hydra A | 1.7795 | −0.9176 | −0.084 | −0.0139 | 0.030 | | 0.050–12 |
   | Virgo A | 2.4466 | −0.8116 | −0.048 | | | | 0.05–3 |
   | 3C286 | 1.2481 | −0.4507 | −0.1798 | 0.0357 | | | 0.05–50 |
   | 3C295 | 1.4701 | −0.7658 | −0.2780 | −0.0347 | 0.0399 | | 0.05–50 |
   | Hercules A | 1.8298 | −1.0247 | −0.0951 | | | | 0.2–12 |
   | 3C353 | 1.8627 | −0.6938 | −0.100 | −0.032 | | | 0.2–4 |
   | 3C380 | 1.2320 | −0.791 | 0.095 | 0.098 | −0.18 | −0.16 | 0.05–50 |
   | Cygnus A | 3.3498 | −1.0022 | −0.225 | 0.023 | 0.043 | | 0.05–12 |
   | 3C444 | 1.1064 | −1.005 | −0.075 | −0.077 | | | 0.2–12 |
   | Cassiopeia A | 3.3584 | −0.7518 | −0.035 | −0.071 | | | 0.2–4 |

   The paper gives Stokes I only (one coefficient set per source, no epoch
   terms; it notes 3C48, 3C138, 3C147 and 3C380 vary). Status: **paper-
   transcribed, CASA oracle pending**; no acceptance is claimed and the API
   refuses it unless the caller opts in (`unverified_ok=True`). Polarisation
   (Q/U/V) for 3C286 and 3C138 is not part of PB2017 or of what `setjy`
   writes under a flux standard (the probe's PB2010 returns Q = U = V = 0);
   it is not ported (CASA's polarised models need `standard='manual'` with
   `polindex`/`polangle`).
7. **Perley-Butler 2013** (ApJS 204, 19): optional; not ported unless its
   table and paper text become available.

## Oracle

`examples/oracle_setjy.py`, run inside `rang-o-casa:6.7.6.14` with
`--network none --user $(id -u):$(id -g)`, into a fresh
`outputs/fs1-20261030-NN`:

- **MS.** casatools `simulator`: two antennas, one 10 s integration per field
  and SPW at epoch 2020-01-01 UTC, TOPO frequencies. SPWs: (a) one
  single-channel SPW per sample frequency — 64 log-spaced points over
  0.05–50 GHz, plus dense points around 0.408, 1.0, 11, 15 GHz and the PB2017
  edges — so `setjy`'s returned `fluxd` is unambiguously the value at that
  frequency, in double precision; (b) one 0.8–1.8 GHz SPW of 1001 channels
  (1 MHz), whose MODEL_DATA (complex float32) gives per-channel I, Q, U, V
  from the linear correlations (I = (XX+YY)/2, Q = (XX−YY)/2,
  U = Re(XY+YX)/2, V = Im(XY−YX)/2).
- **Fields.** 3C48, 3C138, 3C147, 3C286, 3C295, 3C196, 3C123, 3C380, 3C444,
  1934-638 and aliases (J1939-6342, PKS1934-638, 1331+305, J1331+3030,
  0137+331, 0521+166, 0542+498), and PKS 0408−65 (J0408-6545).
- **Calls.** One fresh copy of the template MS per standard;
  `setjy(field=<f>, standard=<s>, scalebychan=True, usescratch=True)` per
  field, one CASA log per call; an empty return dict, a "not recognized"
  line or any SEVERE/WARN line is recorded per (standard, field). Standards:
  `Perley-Butler 2010`, `Baars`, `Stevens-Reynolds 2016`, and `manual` with
  CARACal's values on 1934-638; `Perley-Butler 2017` and `2013` are attempted
  and recorded as pending if their tables are absent.
- **Frame/epoch check.** The single-channel SPWs are repeated on a copy with
  MEAS_FREQ_REF set to LSRK and another observed at 2010-01-01. If `fluxd`
  moves, the port must model CASA's frequency conversion; if not, residuals
  are coefficient rounding.
- **Outputs** (in the run directory, not committed): per (standard, field)
  the doubles and the float32 per-channel Stokes arrays as `.npy`, the logs,
  and `oracle.json` with SHA-256 of every array, image ID, casatools version,
  wall times. A compact copy of the doubles (and decimated float32 values)
  goes to `research/results/fs1-flux-standards.json` for the tests.

## Acceptance (per oracled standard and recognised source)

1. **Doubles:** the port's `flux(source, ν, standard)` equals `setjy`'s
   `fluxd` to **1e-6 relative** at every single-channel SPW inside the
   standard's stated range.
2. **Float32 MODEL_DATA:** the port's per-channel I, rounded to float32,
   equals CASA's MODEL_DATA I to within one float32 ulp (|Δ| ≤ 2⁻²³ × |S|,
   allowing for the (XX+YY)/2 formation), and Q = U = V = 0 where CASA writes
   zeros.
3. **1934−638 coincidence:** SR2016 and PB2010 agree with each other as
   CASA's do (bit-identical in O-CASA) and differ from the Reynolds 1994
   polynomial (1.) by CASA's 2.7e-6 (reproduced to within 0.2e-6 on the
   O-CASA channels, `outputs/o-casa-20261030-01/chan-freq.npy`), and the
   port reproduces O-CASA's `fs-{sr2016,pb2010}-stokes-i.npy` to criterion 2.
4. **Manual model:** the port's CARACal manual model equals `setjy
   standard='manual'` to criteria 1–2.
5. **Out of range:** outside a standard's stated range CASA's behaviour
   (extrapolation, warning, clamping, or 1 Jy) is recorded from the doubles
   and logs. The port **refuses** by default (ValueError naming the range)
   and reproduces CASA's value only with `extrapolate=True`, which must then
   meet criterion 1 where CASA extrapolates. Unrecognised sources: CASA
   writes 1 Jy with a SEVERE log; the port refuses (deliberate difference).
6. **Rust ↔ Python:** the Python module is canonical (tables, names, ranges,
   refusals); the Rust kernel `fluxstd.rs` evaluates the log-polynomials per
   channel and must equal the Python values to 1e-13 relative on every
   oracle frequency.

A coefficient set recovered from the doubles that needs more than the
published/decimal digits to meet criterion 1, or a frame/epoch dependence,
is reported as a finding, not tuned away.

## API

- `rangtoy.fluxstd.flux(source, freq_hz, standard="Perley-Butler 2010", *,
  extrapolate=False, unverified_ok=False) -> ndarray` of shape `(..., 4)`
  (I, Q, U, V; Q = U = V = 0 for every ported standard).
- `rangtoy.fluxstd.manual(freq_hz, fluxdensity, reffreq_hz, spix)`, CASA's
  `standard='manual'` Stokes I.
- `rangtoy.fluxstd.lsm_source(source, standard, ra, dec, ref_freq_hz,
  band_hz)`: an `rangtoy.lsm.Source` whose Tigger spectrum (natural-log
  `spi`) is the exact re-expansion of the standard's log10 polynomial about
  `ref_freq_hz`, so `lsm.components` feeds `core.predict_components`
  unchanged; refuses a band that crosses a piecewise break (SR2016 at
  11 GHz) or leaves the range.
- Rust: `fluxstd::log10_poly(coeffs, x0_hz_unit, freq_hz) -> Vec<f64>` and a
  C entry `rang_core_fluxstd_eval` in `ffi_fluxstd.rs`.

## Files

`core/src/fluxstd.rs`, `core/src/ffi_fluxstd.rs`, `python/rangtoy/fluxstd.py`,
`examples/oracle_setjy.py`, `examples/check_fluxstd.py`,
`tests/test_fluxstd.py`, `research/results/fs1-flux-standards.json`, this
report.
