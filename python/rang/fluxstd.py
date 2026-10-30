"""Flux-density standards for calibrators, as CASA `setjy` applies them.

Task FS1 (research/fs1-flux-standards.md). This module is canonical: it holds
the coefficient tables, source names, piece breaks, validity ranges and
refusals. The Rust kernel `core/src/fluxstd.rs` evaluates one polynomial
piece per channel and is tested against this module.

Every standard is a log-polynomial `log10 S = sum_k a_k x^k`,
`x = log10(nu / unit)`, S in Jy, possibly piecewise in frequency:

- **Perley-Butler 2010** and **Baars** and **Stevens-Reynolds 2016** are
  compiled into casatools. Their coefficients here are the short decimals
  CASA uses, identified by fitting `setjy`'s double-precision outputs (for
  PKS 1934-638 below 10 GHz: Reynolds 1994 converted exactly to GHz and
  rounded to six decimals); CASA stores them as float32, and so does this
  table (`_f32`). With that, the port equals `setjy` to 2e-14 relative on
  0.05-50 GHz (FS1 oracle run
  `outputs/fs1-20261030-01`, `-03`).
- **manual** is `setjy(standard='manual')`:
  `S = S0 (nu/nu0)^(sum_k spix_k log10(nu/nu0)^k)`, all in double.
- **Perley-Butler 2017** is transcribed from Perley & Butler (2017, ApJS
  230, 7, Table 5). CASA's table for it is not in the oracle image, so it is
  *not verified against CASA*; `flux` refuses it unless `unverified_ok=True`.

Stokes Q, U and V are zero for every standard here (as `setjy` writes for
them). Outside a model's range `flux` refuses unless `extrapolate=True`,
which evaluates the polynomial as CASA does (CASA extrapolates silently).
Unknown sources are refused; CASA writes 1 Jy with a SEVERE log line.
"""

import math
from dataclasses import dataclass
from math import comb

import numpy as np

GHZ = 1e9
MHZ = 1e6
LN10 = math.log(10.0)


def _f32(values):
    """CASA's compiled coefficients are float32; reproduce that storage."""
    return tuple(float(np.float32(v)) for v in values)


@dataclass(frozen=True)
class Piece:
    """`log10 S = sum_k coeffs[k] log10(nu/unit_hz)^k` for lo_hz <= nu < hi_hz."""

    lo_hz: float
    hi_hz: float
    unit_hz: float
    coeffs: tuple


@dataclass(frozen=True)
class Model:
    standard: str
    source: str
    pieces: tuple
    valid_hz: tuple  # (lo, hi): outside, `flux` refuses unless extrapolate=True
    range_note: str
    provenance: str
    verified: bool  # equal to CASA setjy within the FS1 acceptance

    def stokes_i(self, freq_hz):
        nu = np.asarray(freq_hz, dtype=float)
        out = np.empty(nu.shape)
        for p in self.pieces:
            sel = (nu >= p.lo_hz) & (nu < p.hi_hz)
            out[sel] = log10_poly(p.coeffs, p.unit_hz, nu[sel])
        return out


def log10_poly(coeffs, unit_hz, freq_hz):
    """10 ** (Horner in log10(nu/unit)); the same arithmetic as fluxstd.rs."""
    x = np.log10(np.asarray(freq_hz, dtype=float) / unit_hz)
    acc = np.zeros_like(x)
    for a in reversed(coeffs):
        acc = acc * x + a
    return 10.0**acc


INF = math.inf
ALL = (0.0, INF)

# --- PKS 1934-638 ---------------------------------------------------------
# Reynolds (1994, ATNF memo AT/39.3/040) as CARACal carries it, log10 nu/MHz.
REYNOLDS_1994_MHZ = (-30.7667, 26.4908, -7.0977, 0.605334)


def mhz_to_ghz(coeffs):
    """Exact re-expansion of a log10(nu/MHz) polynomial in log10(nu/GHz)."""
    n = len(coeffs)
    return tuple(
        sum(coeffs[k] * comb(k, j) * 3.0 ** (k - j) for k in range(j, n))
        for j in range(n)
    )


# CASA's 1934-638 low-frequency piece: the Reynolds polynomial in GHz, rounded
# to six decimals (1.170418, 0.248618, -1.649694, 0.605334), stored float32.
REYNOLDS_GHZ_CASA = _f32(round(c, 6) for c in mhz_to_ghz(REYNOLDS_1994_MHZ))
# High-frequency pieces as CASA evaluates them (recovered from setjy doubles):
STEVENS_CUBIC_GHZ = _f32((-2.5739, 10.0707, -10.0595, 2.9372))  # PB2010, > 10 GHz
STEVENS_2016_GHZ = _f32((1.7581, -1.3763))  # SR2016 power law, above the crossing
BAARS_1934_MHZ = _f32((-23.839, 19.569, -4.8168, 0.35836))  # CASA "Baars" 1934-638


def _crossing(lo, hi):
    """Frequency where the Reynolds piece and the SR2016 power law cross.

    CASA's SR2016 takes the Reynolds polynomial below and the power law above
    a break between 11.14 and 11.15 GHz (dense oracle run -03); the two
    curves cross at 11.1496 GHz, so the model is continuous there and the
    exact comparator at the break cannot matter.
    """

    def g(f):
        x = math.log10(f / GHZ)
        r = sum(a * x**k for k, a in enumerate(REYNOLDS_GHZ_CASA))
        s = sum(a * x**k for k, a in enumerate(STEVENS_2016_GHZ))
        return r - s

    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if g(lo) * g(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


SR2016_BREAK_HZ = _crossing(11.0 * GHZ, 11.3 * GHZ)
# PB2010: Reynolds up to and including 10 GHz, the cubic above (oracle -03:
# 10.000000 GHz is Reynolds, 10.000001 GHz the cubic).
PB2010_BREAK_HZ = float(np.nextafter(10.0 * GHZ, INF))

ORACLE_RANGE = (0.05 * GHZ, 50.0 * GHZ)
ORACLE_NOTE = (
    "no published range in hand; the range sampled by the FS1 setjy oracle "
    "(CASA itself evaluates any frequency without a warning)"
)

_PB2010 = {  # log10 nu/GHz, cubic; CASA's compiled values (float32)
    "3C48": (1.3197, -0.7253, -0.2023, 0.0540),
    "3C138": (1.0053, -0.4384, -0.1855, 0.0511),
    "3C147": (1.4428, -0.6300, -0.3142, 0.1032),
    "3C286": (1.2361, -0.4127, -0.1864, 0.0294),
    "3C295": (1.4605, -0.7043, -0.3951, 0.0815),
    "3C196": (1.2753, -0.7971, -0.2255, 0.0380),
}
_BAARS = {  # Baars et al. 1977, log10 nu/MHz, quadratic (CASA float32)
    "3C48": (2.345, 0.071, -0.138),
    "3C138": (2.009, -0.07176, -0.0862),
    "3C147": (1.766, 0.447, -0.184),
    "3C286": (1.480, 0.292, -0.124),
    "3C295": (1.485, 0.759, -0.255),
}
# Perley & Butler 2017 (ApJS 230, 7; arXiv:1609.05940 Table 5), log10 nu/GHz,
# with each source's range of validity in GHz. Not verified against CASA.
_PB2017 = {
    "J0133-3629": ((1.0440, -0.662, -0.225), (0.2, 4)),
    "3C48": ((1.3253, -0.7553, -0.1914, 0.0498), (0.05, 50)),
    "Fornax A": ((2.218, -0.661), (0.2, 0.5)),
    "3C123": ((1.8017, -0.7884, -0.1035, -0.0248, 0.0090), (0.05, 50)),
    "J0444-2809": ((0.9710, -0.894, -0.118), (0.2, 2.0)),
    "3C138": ((1.0088, -0.4981, -0.155, -0.010, 0.022), (0.2, 50)),
    "Pictor A": ((1.9380, -0.7470, -0.074), (0.2, 4.0)),
    "Taurus A": ((2.9516, -0.217, -0.047, -0.067), (0.05, 4.0)),
    "3C147": ((1.4516, -0.6961, -0.201, 0.064, -0.046, 0.029), (0.05, 50)),
    "3C196": ((1.2872, -0.8530, -0.153, -0.0200, 0.0201), (0.050, 50)),
    "Hydra A": ((1.7795, -0.9176, -0.084, -0.0139, 0.030), (0.050, 12)),
    "Virgo A": ((2.4466, -0.8116, -0.048), (0.05, 3)),
    "3C286": ((1.2481, -0.4507, -0.1798, 0.0357), (0.05, 50)),
    "3C295": ((1.4701, -0.7658, -0.2780, -0.0347, 0.0399), (0.05, 50)),
    "Hercules A": ((1.8298, -1.0247, -0.0951), (0.2, 12)),
    "3C353": ((1.8627, -0.6938, -0.100, -0.032), (0.2, 4)),
    "3C380": ((1.2320, -0.791, 0.095, 0.098, -0.18, -0.16), (0.05, 50)),
    "Cygnus A": ((3.3498, -1.0022, -0.225, 0.023, 0.043), (0.05, 12)),
    "3C444": ((1.1064, -1.005, -0.075, -0.077), (0.2, 12)),
    "Cassiopeia A": ((3.3584, -0.7518, -0.035, -0.071), (0.2, 4)),
}

# Names CASA 6.7.6 recognised in the oracle (each alias gave identical values).
ALIASES = {
    "0137+331": "3C48",
    "0521+166": "3C138",
    "0542+498": "3C147",
    "1331+305": "3C286",
    "J1331+3030": "3C286",
    "J1939-6342": "1934-638",
    "PKS1934-638": "1934-638",
}
STANDARD_ALIASES = {
    "PB2010": "Perley-Butler 2010",
    "Perley-Butler 2010": "Perley-Butler 2010",
    "Baars": "Baars",
    "SR2016": "Stevens-Reynolds 2016",
    "Stevens-Reynolds 2016": "Stevens-Reynolds 2016",
    "PB2017": "Perley-Butler 2017",
    "Perley-Butler 2017": "Perley-Butler 2017",
}


def _models():
    models = {}
    casa = "CASA 6.7.6 compiled value (float32), identified from setjy doubles"
    for src, c in _PB2010.items():
        models["Perley-Butler 2010", src] = Model(
            "Perley-Butler 2010", src, (Piece(0.0, INF, GHZ, _f32(c)),),
            ORACLE_RANGE, ORACLE_NOTE, casa, True,
        )  # fmt: skip
    models["Perley-Butler 2010", "1934-638"] = Model(
        "Perley-Butler 2010",
        "1934-638",
        (
            Piece(0.0, PB2010_BREAK_HZ, GHZ, REYNOLDS_GHZ_CASA),
            Piece(PB2010_BREAK_HZ, INF, GHZ, STEVENS_CUBIC_GHZ),
        ),
        ORACLE_RANGE,
        ORACLE_NOTE,
        "Reynolds 1994 in GHz to <= 10 GHz, a cubic above; " + casa,
        True,
    )
    for src, c in _BAARS.items():
        models["Baars", src] = Model(
            "Baars", src, (Piece(0.0, INF, MHZ, _f32(c)),),
            (408 * MHZ, 15 * GHZ), "408 MHz-15 GHz (CASA docs, Baars et al. 1977)",
            "Baars et al. 1977 (A&A 61, 99) form; CASA 6.7.6 compiled digits (float32)", True,
        )  # fmt: skip
    models["Baars", "1934-638"] = Model(
        "Baars", "1934-638", (Piece(0.0, INF, MHZ, BAARS_1934_MHZ),),
        (408 * MHZ, 15 * GHZ), "408 MHz-15 GHz (CASA's Baars range)",
        "not in Baars et al. 1977; " + casa, True,
    )  # fmt: skip
    models["Stevens-Reynolds 2016", "1934-638"] = Model(
        "Stevens-Reynolds 2016",
        "1934-638",
        (
            Piece(0.0, SR2016_BREAK_HZ, GHZ, REYNOLDS_GHZ_CASA),
            Piece(SR2016_BREAK_HZ, INF, GHZ, STEVENS_2016_GHZ),
        ),
        ORACLE_RANGE,
        ORACLE_NOTE,
        "Reynolds 1994 in GHz below 11.1496 GHz, a power law above; " + casa,
        True,
    )
    for src, (c, (lo, hi)) in _PB2017.items():
        models["Perley-Butler 2017", src] = Model(
            "Perley-Butler 2017", src, (Piece(0.0, INF, GHZ, tuple(c)),),
            (lo * GHZ, hi * GHZ), f"{lo}-{hi} GHz (Perley & Butler 2017, Table 5)",
            "Perley & Butler 2017 Table 5 (paper-transcribed; CASA oracle pending)", False,
        )  # fmt: skip
    return models


MODELS = _models()


def standards():
    return sorted({s for s, _ in MODELS})


def sources(standard):
    standard = STANDARD_ALIASES.get(standard, standard)
    return sorted(src for s, src in MODELS if s == standard)


def model(source, standard):
    std = STANDARD_ALIASES.get(standard)
    if std is None:
        raise ValueError(f"unknown standard {standard!r}; known: {standards()}")
    src = ALIASES.get(source, source)
    found = MODELS.get((std, src))
    if found is None:
        raise ValueError(
            f"{source!r} is not in {std} (CASA would write 1 Jy); known: {sources(std)}"
        )
    return found


def _check_range(m, nu, extrapolate):
    if not np.all(np.isfinite(nu) & (nu > 0)):
        raise ValueError("frequencies must be positive and finite")
    lo, hi = m.valid_hz
    if not extrapolate and (np.any(nu < lo) or np.any(nu > hi)):
        raise ValueError(
            f"{m.source} under {m.standard}: frequencies outside {lo / GHZ:g}-"
            f"{hi / GHZ:g} GHz ({m.range_note}); pass extrapolate=True to "
            "evaluate the polynomial there as CASA does"
        )


def flux(
    source,
    freq_hz,
    standard="Perley-Butler 2010",
    *,
    extrapolate=False,
    unverified_ok=False,
):
    """Stokes (I, Q, U, V) in Jy, shape `freq_hz.shape + (4,)`."""
    m = model(source, standard)
    if not m.verified and not unverified_ok:
        raise ValueError(
            f"{m.standard} is not verified against CASA ({m.provenance}); "
            "pass unverified_ok=True to use it anyway"
        )
    nu = np.asarray(freq_hz, dtype=float)
    _check_range(m, nu, extrapolate)
    out = np.zeros(nu.shape + (4,))
    out[..., 0] = m.stokes_i(nu)
    return out


def manual(freq_hz, fluxdensity, reffreq_hz, spix):
    """`setjy(standard='manual', scalebychan=True)` Stokes I (CASA: log10 spix)."""
    nu = np.asarray(freq_hz, dtype=float)
    x = np.log10(nu / reffreq_hz)
    exponent = np.zeros_like(x)
    for a in reversed(tuple(spix)):
        exponent = exponent * x + a
    return fluxdensity * (nu / reffreq_hz) ** exponent


# CARACal's frozen manual model for PKS 1934-638 (research/o-casa.md).
CARACAL_1934 = {
    "fluxdensity": 14.907688923,
    "reffreq_hz": 1.4e9,
    "spix": (-0.19473727, -1.38432520, 0.60533435, 1.43e-06),
}


def tigger_spi(coeffs, unit_hz, ref_freq_hz):
    """(S(ref), spi) with S = S(ref) exp(sum_j spi[j-1] ln(nu/ref)^j) exactly
    equal to `10 ** sum_k coeffs[k] log10(nu/unit)^k` (Tigger/lsm convention)."""
    x0 = math.log10(ref_freq_hz / unit_hz)
    n = len(coeffs)
    b = [
        sum(coeffs[k] * comb(k, j) * x0 ** (k - j) for k in range(j, n)) / LN10**j
        for j in range(n)
    ]
    return 10.0 ** b[0], tuple(LN10 * bj for bj in b[1:])


def lsm_source(
    source,
    standard,
    ra,
    dec,
    ref_freq_hz,
    band_hz,
    *,
    name=None,
    extrapolate=False,
    unverified_ok=False,
):
    """A `rang.lsm.Source` (point, Stokes I) carrying the standard's spectrum.

    The band must lie in one piece of the standard (SR2016 breaks at
    11.1496 GHz, PB2010 1934-638 at 10 GHz) and, unless `extrapolate`, inside
    its range. `lsm.components` then feeds `core.predict_components`.
    """
    from rang import lsm

    lo, hi = band_hz
    flux(source, [lo, hi, ref_freq_hz], standard, extrapolate=extrapolate,
         unverified_ok=unverified_ok)  # fmt: skip
    m = model(source, standard)
    piece = [
        p
        for p in m.pieces
        if p.lo_hz <= min(lo, ref_freq_hz) and max(hi, ref_freq_hz) < p.hi_hz
    ]
    if not piece:
        raise ValueError(f"band {lo:g}-{hi:g} Hz crosses a piece break of {m.standard}")
    p = piece[0]
    i0, spi = tigger_spi(p.coeffs, p.unit_hz, ref_freq_hz)
    return lsm.Source(
        name=name or m.source, ra=ra, dec=dec, i=i0, freq0=ref_freq_hz, spi=spi,
        extra={"flux_standard": m.standard, "provenance": m.provenance},
    )  # fmt: skip


def manual_lsm_source(ra, dec, fluxdensity, reffreq_hz, spix, *, name="manual"):
    """CASA's manual model as an lsm.Source, exact (log10 spix to Tigger ln spi)."""
    from rang import lsm

    coeffs = (math.log10(fluxdensity),) + tuple(spix)
    i0, spi = tigger_spi(coeffs, reffreq_hz, reffreq_hz)
    return lsm.Source(name=name, ra=ra, dec=dec, i=i0, freq0=reffreq_hz, spi=spi)


# --- The Rust kernel ------------------------------------------------------
# Until core/src/lib.rs lists `fluxstd` (the coordinator's step), the two Rust
# files build as a standalone cdylib in core/target/fs1-standalone, as P5 and
# DF1 did. No dependencies, so no lock file is needed.


def standalone_dir():
    from rang import core

    return core.core_root() / "target" / "fs1-standalone"


def write_standalone():
    from rang import core

    src = core.core_root() / "src"
    out = standalone_dir()
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "Cargo.toml": "[package]\n"
        'name = "rang-fs1-core"\nversion = "0.1.0"\nedition = "2024"\n'
        'license = "GPL-3.0-or-later"\npublish = false\n\n[lib]\n'
        'name = "rang_fs1_core"\npath = "root.rs"\n'
        'crate-type = ["rlib", "cdylib"]\n\n[workspace]\n',
        "root.rs": "//! Standalone build of FS1 until core/src/lib.rs lists it.\n"
        + "".join(
            f'#[path = "{(src / f"{m}.rs").as_posix()}"]\npub mod {m};\n'
            for m in ("fluxstd", "ffi_fluxstd")
        ),
    }
    for name, text in files.items():
        path = out / name
        if not path.is_file() or path.read_text() != text:
            path.write_text(text)
    return out


def rust_library():
    """ctypes handle on the standalone kernel, built offline on demand."""
    import ctypes
    import subprocess
    import sys

    out = write_standalone()
    subprocess.run(
        ["cargo", "build", "--offline", "--release", "-q"], cwd=out, check=True
    )
    lib = ctypes.CDLL(
        str(
            out
            / "target"
            / "release"
            / {"win32": "rang_fs1_core.dll", "darwin": "librang_fs1_core.dylib"}.get(
                sys.platform, "librang_fs1_core.so"
            )
        )
    )
    dptr = ctypes.POINTER(ctypes.c_double)
    fn = lib.rang_core_fluxstd_eval
    fn.argtypes = [ctypes.c_size_t, dptr, ctypes.c_double, ctypes.c_size_t, dptr, dptr]
    fn.restype = ctypes.c_int
    return lib


def rust_log10_poly(lib, coeffs, unit_hz, freq_hz):
    """`log10_poly` through the Rust kernel (`rang_core_fluxstd_eval`)."""
    import ctypes

    c = np.ascontiguousarray(coeffs, dtype=float)
    f = np.ascontiguousarray(freq_hz, dtype=float).ravel()
    out = np.empty_like(f)
    dptr = ctypes.POINTER(ctypes.c_double)
    rc = lib.rang_core_fluxstd_eval(
        len(c), c.ctypes.data_as(dptr), unit_hz, len(f),
        f.ctypes.data_as(dptr), out.ctypes.data_as(dptr),
    )  # fmt: skip
    if rc != 0:
        raise ValueError("rang_core_fluxstd_eval rejected its input")
    return out.reshape(np.shape(freq_hz))


def core_log10_poly(coeffs, unit_hz, freq_hz):
    """The Rust kernel through the extension once the coordinator binds
    `rang._core.fluxstd_eval(coeffs, unit_hz, freq) -> ndarray`; until then
    the standalone cdylib (needs cargo)."""
    try:
        from rang import _core
    except ImportError:
        _core = None
    if _core is not None and hasattr(_core, "fluxstd_eval"):
        freq = np.ascontiguousarray(freq_hz, dtype=float)
        coeffs = np.ascontiguousarray(coeffs, dtype=float)
        return np.asarray(_core.fluxstd_eval(coeffs, unit_hz, freq.ravel())).reshape(
            freq.shape
        )
    return rust_log10_poly(rust_library(), coeffs, unit_hz, freq_hz)
