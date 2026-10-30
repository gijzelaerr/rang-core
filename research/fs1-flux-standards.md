# FS1: flux-density standards in the core, with CASA `setjy` as the oracle

Protocol frozen 2026-10-30 on branch `fs1-flux-standards` (from `56248df`),
before any flux-standard code. Task FS1 of the ecosystem survey
([ecosystem-survey.md](ecosystem-survey.md), section "Flux standards in the
core"), with the O-CASA oracle ([o-casa.md](o-casa.md)) as its precondition.
Status at freeze: proposed; nothing implemented, one probe run (below).

**Status now: implemented and measured** ([Measured results](#measured-results-2026-10-30)).
Perley-Butler 2010 (7 sources), Baars (6) and Stevens-Reynolds 2016
(1934−638) equal CASA 6.7.6 `setjy` to ≤ 1.6e-14 relative on 0.05–50 GHz
and bit-for-bit in float32 MODEL_DATA; so does CARACal's `manual` model.
CASA stores its compiled coefficients as float32 and evaluates in double;
the port does the same. O-CASA's 2.7e-6 "coincidence" is not CASA's: it is
the float32 mean over 192 rows in O-CASA's own reduction, replayed
bit-identically here; CASA's MODEL_DATA differs from the Reynolds 1994
polynomial by ≤ 6e-8. Perley-Butler 2017 is transcribed from the paper but
**not verified** (CASA's coefficient table is not in the image).

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

## Measured results (2026-10-30)

Everything below is post-freeze. Oracle: `rang-o-casa:6.7.6.14` (image
`sha256:24822b4038c5…`), casatools 6.7.6-14, `--network none`, Ubuntu
`casacore-data` measures (no casarundata). Runs:

- `outputs/fs1-20261030-01`: the protocol's oracle (`oracle_setjy.py`), 18
  field names × 5 standards + `manual` + the frame/epoch check; 85
  single-channel SPWs over 0.05–50 GHz and one 1001-channel 0.8–1.8 GHz SPW;
  114 arrays, hashed in `oracle.json` (sha256 `a40c377c…`).
- `outputs/fs1-20261030-03`: `--dense-1934`, post-hoc after run 01 showed
  piece breaks for 1934−638 between sample points: 303 SPWs over
  9.6–12.1 GHz (10 MHz steps, each 0.1 GHz value ±1 kHz), SR2016 and PB2010
  (`oracle.json` sha256 `0336d724…`).
- `outputs/fs1-20261030-04`: an unintended full rerun of run 01 (a
  `--reread-ocasa` edit had not been saved); kept as a reproducibility
  check: all 114 array hashes are identical to run 01.
- `outputs/fs1-20261030-05`, `-06`: `--reread-ocasa`, post-hoc, the per-row
  re-read of O-CASA's `fs-sr2016.ms`/`fs-pb2010.ms` MODEL_DATA (O-CASA run
  mounted read-only). Run 05 compared complex rows and reported them as not
  identical because of 1.8e-12 imaginary parts (row phases on the real
  array); run 06 compares the real parts (identical) and records the
  imaginary maximum. Run 06 is the evidence. (A first python-casacore
  re-read with the same result, `fs1-20261030-02/ocasa-model-check.json`,
  came from a scratch script and is superseded by run 06.)
- `outputs/fs1-20261030-02`: the check-all log.
- Comparison: `examples/check_fluxstd.py` → `research/results/fs1-flux-standards.json`
  (compact: the doubles per canonical source, every 50th L-band channel of
  the float32 MODEL_DATA, all comparison rows, hashes; no MS data).

Commands (from the worktree; `$RUN` a fresh run directory, `$O` the O-CASA
run `outputs/o-casa-20261030-01`):

```bash
docker image inspect --format '{{.Id}}' rang-o-casa:6.7.6.14 > $RUN/image-id.txt
docker run --rm --user $(id -u):$(id -g) --network none --tmpfs /tmp -e HOME=/tmp \
  -v $PWD/examples:/code:ro -v $RUN:/run -w /run rang-o-casa:6.7.6.14 \
  /usr/bin/time -f "%e %M %x" -o /run/time-inner.txt \
  /opt/casa/bin/python -I /code/oracle_setjy.py /run            # runs 01, 04
#   ... oracle_setjy.py /run --dense-1934                      # run 03
#   add -v $(realpath $O):/ocasa:ro and: ... /run --reread-ocasa /ocasa   # run 06
python examples/check_fluxstd.py outputs/fs1-20261030-01 outputs/fs1-20261030-03 \
  $O outputs/fs1-20261030-06 outputs/fs1-20261030-04 research/results/fs1-flux-standards.json
```

### What CASA does (identified from the oracle)

| Standard | Source (aliases recognised) | CASA's model | Unit |
| --- | --- | --- | --- |
| PB2010 | 3C48 (0137+331) | 1.3197, −0.7253, −0.2023, 0.0540 | log10 ν/GHz |
| PB2010 | 3C138 (0521+166) | 1.0053, −0.4384, −0.1855, 0.0511 | GHz |
| PB2010 | 3C147 (0542+498) | 1.4428, −0.6300, −0.3142, 0.1032 | GHz |
| PB2010 | 3C286 (1331+305, J1331+3030) | 1.2361, −0.4127, −0.1864, 0.0294 | GHz |
| PB2010 | 3C295 | 1.4605, −0.7043, −0.3951, 0.0815 | GHz |
| PB2010 | 3C196 | 1.2753, −0.7971, −0.2255, 0.0380 | GHz |
| PB2010 | 1934−638 (J1939-6342, PKS1934-638) | ν ≤ 10 GHz: Reynolds in GHz 1.170418, 0.248618, −1.649694, 0.605334; ν > 10 GHz: −2.5739, 10.0707, −10.0595, 2.9372 | GHz |
| Baars | 3C48 | 2.345, 0.071, −0.138 | log10 ν/MHz |
| Baars | 3C138 | 2.009, −0.07176, −0.0862 | MHz |
| Baars | 3C147 | 1.766, 0.447, −0.184 | MHz |
| Baars | 3C286 | 1.480, 0.292, −0.124 | MHz |
| Baars | 3C295 | 1.485, 0.759, −0.255 | MHz |
| Baars | 1934−638 | −23.839, 19.569, −4.8168, 0.35836 (not from Baars et al. 1977) | MHz |
| SR2016 | 1934−638 only | ν < 11.1496 GHz: Reynolds in GHz as PB2010; above: power law 1.7581, −1.3763 | GHz |
| manual | CARACal 1934−638 | `S0 (ν/ν0)^(Σ spix_k log10(ν/ν0)^k)`, all double | — |

- **Float32 coefficients, double arithmetic.** Each compiled set is a
  short decimal stored as float32: fitting `setjy`'s returned doubles in the
  stated form gives e.g. 1.236099958 for 3C286's a0, which is
  `float32(1.2361)`; with the float32 values the port reproduces every
  double to ≤ 1.6e-14 (one or two double ulps from Horner versus CASA's
  order). With the decimals in double precision instead, the residuals are
  up to 3.1e-7 (PB2010 and Baars, sources other than 1934−638). The Baars
  sets are stored in MHz form, PB2010 and the 1934−638 pieces in GHz form
  (each recovers short decimals only in its own unit). The Baars et al.
  (1977) text was not in hand, so the agreement of these digits with the
  paper is not checked here.
- **1934−638 low piece.** Reynolds 1994 (log10 ν/MHz) re-expanded exactly to
  GHz is (1.170418, 0.248618, −1.649694, 0.605334) to 15 digits; CASA uses
  these six-decimal values in float32. Against the MHz polynomial in double
  the effect is ≤ 2.5e-7 on 0.05–11 GHz and ≤ 6.0e-8 on O-CASA's
  1.07–1.50 GHz.
- **Piece breaks.** PB2010 takes Reynolds up to and including 10.000000 GHz
  and the cubic from 10.000001 GHz (a 0.04 % step at 10 GHz). SR2016
  switches between 11.14 and 11.15 GHz, where the Reynolds piece and the
  power law cross (11.1496 GHz): the model is continuous there and is the
  smaller of the two pieces everywhere on 0.05–50 GHz. CASA's documentation
  says "below 11 GHz"; the measured switch is the crossing. The port puts
  the SR2016 break at the crossing (bisection on the float32 pieces).
- **No range handling in CASA.** Every standard is evaluated on all of
  0.05–50 GHz without a warning or clamp; Baars outside 408 MHz–15 GHz and
  PB2010/SR2016 far outside their data are silent extrapolations.
- **Unrecognised names.** CASA writes 1 Jy and logs SEVERE "… is not
  recognized by …" without raising (24 (standard, name) cases, including
  3C123, 3C380, 3C444 and J0408−6545 everywhere, 3C196 under Baars, and
  every non-1934 name under SR2016). Recognised aliases give identical values.
- **No frame or epoch dependence.** TOPO 2020, LSRK 2020 (MEAS_FREQ_REF
  rewritten) and TOPO 2010 give bit-identical `fluxd` at the stored channel
  frequencies; CASA evaluates at CHAN_FREQ as stored.
- **Stokes.** Q = U = V = 0 in the returned `fluxd` and in MODEL_DATA
  (XY = YX = 0, XX = YY, imaginary parts 0 on the synthetic MS) for every
  source under PB2010, Baars, SR2016 and `manual`. Unverified for PB2017
  until its table exists (the paper itself gives Stokes I only).
- **PB2017/PB2013.** `setjy` returns `{}` (table missing) for every name it
  accepts, without raising, so a pipeline that does not check the return
  value keeps the previous MODEL_DATA. J0408−6545 is "not recognized" before
  the table lookup; 1934−638 is *not* rejected at that stage under PB2017
  or PB2013, which this run cannot resolve further (the survey says 1934−638
  is not in either table).

### Acceptance (as frozen)

| Criterion | Result |
| --- | --- |
| 1. Doubles ≤ 1e-6 relative in range | **pass**: max 1.6e-14 (Baars 1934−638); all other sets ≤ 3.1e-15 |
| 2. Float32 MODEL_DATA within 1 ulp | **pass**: 0 ulps, every channel of 1001, every source and alias (31 rows) |
| 3. 1934−638 coincidence | **frozen premise falsified.** The criterion assumed CASA differs from Reynolds 1994 by 2.7e-6; it differs by ≤ 6.0e-8 on O-CASA's band. In its place: SR2016 and PB2010 bit-identical below 10 GHz (as in O-CASA); CASA's per-row MODEL_DATA in O-CASA's `fs-*.ms` equals the port to 0 ulps on all 2048 channels × 192 rows (run 06); and O-CASA's saved arrays are reproduced *bit-identically* by replaying its float32 reduction on the port's values (see below) |
| 4. Manual model | **pass**: 2.3e-15 on the doubles, 0 ulps on L-band |
| 5. Out of range | CASA extrapolates silently; the port refuses by default and with `extrapolate=True` meets criterion 1 on all of 0.05–50 GHz (max 1.6e-14). Unknown names: CASA 1 Jy, port refuses (24/24) |
| 6. Rust ↔ Python | **pass**: 34 models' pieces on 1100 frequencies, max 1.6e-14 (≤ 1e-13); the archived oracle values are also Rust unit tests |
| PB2017 | **not assessed**: oracle pending (no CASA table) |

Maximum relative error against CASA per standard and canonical source (max
over recognised aliases; doubles on 0.05–50 GHz / L-band float32 ulps):

| Standard | 3C48 | 3C138 | 3C147 | 3C286 | 3C295 | 3C196 | 1934−638 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Perley-Butler 2010 | 5.6e-16 / 0 | 2.2e-16 / 0 | 6.7e-16 / 0 | 6.7e-16 / 0 | 5.6e-16 / 0 | 1.6e-15 / 0 | 3.1e-15 (dense) / 0 |
| Baars | 3.1e-15 / 0 | 2.0e-15 / 0 | 1.6e-15 / 0 | 1.6e-15 / 0 | 2.7e-15 / 0 | refused (CASA: 1 Jy) | 1.6e-14 / 0 |
| Stevens-Reynolds 2016 | refused | refused | refused | refused | refused | refused | 1.1e-15 (dense) / 0 |
| manual (CARACal) | | | | | | | 2.3e-15 / 0 |
| Perley-Butler 2017 | pending | pending | pending | pending | pending | pending | not in PB2017 (paper) |

### The 2.7e-6 of O-CASA, attributed

O-CASA reported SR2016 = PB2010 = Reynolds 1994 "to 2.7e-6 relative" from
`fs-{sr2016,pb2010}-stokes-i.npy`. Those arrays are
`0.5 * (XX + YY).real.mean(axis=0)` over 192 rows in float32
(`tools/oracles/casa/inspect_tables.py`). Re-reading the MS per row: all
192 rows are identical and equal to the port in float32 to 0 ulps on every
channel; the float64 mean is 3.2e-8 from the port in double (float32
storage); the float32 mean over rows is 2.65e-6 off. Replaying that float32
reduction on the port's values gives O-CASA's arrays bit for bit. So the
residual O-CASA measured is its reduction's float32 accumulation, and the
CASA/Reynolds difference is ≤ 6.0e-8 on that band (coefficient rounding).
The same reduction produced O-CASA's "CARACal manual fit to 4.8e-6": the
manual model and SR2016 differ by ≤ 5.6e-8 (UHF, 0.544–1.088 GHz),
6.3e-8 (L, 0.856–1.712 GHz) and 6.4e-8 (S, 1.75–3.5 GHz). They diverge
only above 11.15 GHz (up to 140 % against SR2016's power law and 21 %
against PB2010's cubic by 50 GHz), where the manual model has no
high-frequency piece. For MeerKAT bands the choice among CARACal's manual
model, SR2016 and PB2010 (CASA's fallback, bit-identical to SR2016 below
10 GHz) is immaterial. Follow-ups outside FS1's files: an erratum in
`research/o-casa.md` and STATE.md ("to 3e-6"), and `inspect_tables.py`
should average with `dtype=np.float64`.

**A setjy-equivalent 1934−638 arm, measured.** `lsm_source("J1939-6342",
"SR2016", ...)` → `lsm.components` → `core.predict_components` (point
source at the phase centre, O-CASA's 2048 channel frequencies), cast to
complex64, equals CASA's MODEL_DATA rows to 0 ulps (imaginary part 0;
CASA's rows carry ≤ 1.8e-12). The stored MODEL_DATA the core campaigns
used is 14.9028 Jy at 1.4 GHz (O-CASA); the standard gives 14.9077 Jy,
0.033 % higher.

### Implementation

- `python/rangtoy/fluxstd.py` (canonical): the tables above with
  provenance, `flux(source, freq_hz, standard, *, extrapolate=False,
  unverified_ok=False)` → `(..., 4)` I, Q, U, V; `manual(...)` and
  `CARACAL_1934`; `model`, `standards`, `sources`; `lsm_source(...)` and
  `manual_lsm_source(...)`, exact re-expansions of the log10 polynomials in
  Tigger's natural-log `spi` about a reference frequency (≤ 9e-16 against
  `flux` on 0.856–1.712 GHz; through `core.predict_components` the manual
  model's point-source visibilities equal `manual` to 4.4e-16). Ranges:
  Baars 408 MHz–15 GHz (CASA docs); PB2017 per source from the paper;
  PB2010 and SR2016 have no range in hand and use the oracle's 0.05–50 GHz.
- `core/src/fluxstd.rs`: `log10_flux`, `log10_poly`, `piecewise`;
  `core/src/ffi_fluxstd.rs`: `rang_core_fluxstd_eval`. Until `lib.rs`
  lists them they build as a standalone cdylib (`core/target/fs1-standalone`,
  `fluxstd.rust_library()`), as P5 and DF1 did.
- Tests: 9 Rust unit tests (one checks six archived CASA doubles to 1e-13),
  `tests/test_fluxstd.py` (12 tests on the archive, refusals, aliases, the
  component builder and Rust parity).

### Rejected and open

- Rejected: evaluating PB2010/Baars in double from the decimals (residual
  up to 3.1e-7, not CASA's); a hard SR2016 break at 11 GHz (contradicted by the
  dense run); reproducing CASA's 1 Jy for unknown names.
- Open: PB2017 and PB2013 against CASA need `casarundata`'s
  `nrao/VLA/standards/PerleyButler2017Coeffs` (and `…2013Coeffs`), a
  download for the user to approve. Then mount the table directories
  read-only and run `oracle_setjy.py /run --tables /tables`; inspect the
  table's columns for epoch terms first. Until then PB2017 is opt-in only.
- Open: whether CASA's PB2017 accepts 1934−638 by name (above).
- Open: Stevens-Reynolds 2016's published text (the power law's source) and
  the Reynolds memo's own validity range were not in hand.

### Tool runs

| Date | Tool | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-30 | `setjy` probe (6 standards × 2 fields) | `rang-o-casa:6.7.6.14`, 11-channel MS | ~5 s | – | found PB2013/PB2017/SH2012 tables missing; SR2016 3C286 → 1 Jy |
| 2026-10-30 | `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` | worktree, public PyPI | 63.4 s | 891 MB | |
| 2026-10-30 | `oracle_setjy.py` (docker) | run `fs1-20261030-01` | 166.1 s (inside 165.7 s; build 31 s, PB2010 46 s, Baars 42 s, SR2016 11 s, frame check 28 s) | 295 MB (container) | 114 arrays |
| 2026-10-30 | `oracle_setjy.py --dense-1934` (docker) | run `fs1-20261030-03` | 29.8 s (inside 29.2 s) | 282 MB | 303 SPWs, 2 standards |
| 2026-10-30 | O-CASA MS re-read (scratch script, python-casacore in the image) | `o-casa-20261030-01/fs-*.ms` | ~1 s | – | `fs1-20261030-02/ocasa-model-check.json`, superseded by run 06 |
| 2026-10-30 | `oracle_setjy.py` (docker), unintended rerun | run `fs1-20261030-04` | 146.2 s (inside 145.9 s) | 293 MB | 114 arrays bit-identical to run 01 |
| 2026-10-30 | `oracle_setjy.py --reread-ocasa` (docker) | runs `fs1-20261030-05`, `-06` | 1.8 s, 1.6 s (inside 1.5, 1.3 s) | 351 MB | 05 compared complex rows (1.8e-12 imaginary parts); 06 real parts, the evidence |
| 2026-10-30 | `cargo test` / `clippy -D warnings` / `build --release` standalone | `fs1-standalone` | 0.3 / 0.1 / 0.3 s | 145 / 122 / 121 MB | 9 passed; clean |
| 2026-10-30 | `check_fluxstd.py` | runs 01, 03, 04, 06, O-CASA | 0.1 s | 46 MB | all acceptance true (final archive) |
| 2026-10-30 | `pytest tests/test_fluxstd.py` | archive | 0.2 s | 54 MB | 12 passed |
| 2026-10-30 | `bash tools/check-all.sh`, once before the final commit | branch at `e3436aa` + the FS1 files (log `outputs/fs1-20261030-02/check-all.log`) | 333.5 s (pytest 698 passed, 5 skipped in 152.8 s) | 1.67 GB | PASS |
| 2026-10-30 | `bash tools/check-all.sh`, before the second commit | branch at `eb88550` + the re-read, arm and manual-comparison changes (log `outputs/fs1-20261030-06/check-all.log`) | 214.8 s (pytest 698 passed, 5 skipped in 99.2 s) | 1.59 GB | PASS |
