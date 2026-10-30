"""Reader for Tigger ASCII local sky models (`.lsm` text files).

The format is the one of Tigger's ASCII loader (astro-tigger-lsm,
`Tigger/Models/Formats/ASCII.py`): an optional first line
`#format: <field names>` names the whitespace-separated columns, every other
line starting with `#` is a comment. Conventions (research/l1-model-completeness.md):

- RA from `ra_h ra_m ra_s` (hours), `ra_d` (degrees) or `ra_rad`; Dec from
  `dec_d dec_m dec_s` or `dec_rad`, its sign taken from the `dec_d` string so
  that -0 degrees keeps its sign.
- `i` (and `q`, `u`, `v` when present) in Jy at `freq0` (Hz).
- Spectrum `S(nu) = S0 (nu/nu0)^(spi + spi2 L + spi3 L^2 + ...)` with
  `L = ln(nu/nu0)`, i.e. `S0 exp(spi L + spi2 L^2 + ...)`.
- `emaj`/`emin` are full widths at half maximum; `pa` is the position angle
  east of north. A source is Gaussian if either extent is non-zero.
- `*_err` columns are kept as errors and never used; unknown columns are kept
  as strings.

No dependency on Tigger.
"""

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DEFAULT_FORMAT = (
    "name ra_h ra_m ra_s dec_d dec_m dec_s i q u v spi rm emaj_s emin_s pa_d freq0"
)
ANGLE_UNITS = {
    "rad": 1.0,
    "d": math.pi / 180,
    "m": math.pi / 180 / 60,
    "s": math.pi / 180 / 3600,
}
MAX_SPI_TERMS = 9


@dataclass
class Source:
    """One sky-model component; angles in radians, fluxes in Jy."""

    name: str
    ra: float
    dec: float
    i: float
    q: float = 0.0
    u: float = 0.0
    v: float = 0.0
    freq0: float | None = None
    spi: tuple = ()
    emaj: float = 0.0
    emin: float = 0.0
    pa: float = 0.0
    errors: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    @property
    def gaussian(self):
        return self.emaj != 0.0 or self.emin != 0.0

    def flux(self, frequency):
        """Stokes I at `frequency` (Hz, scalar or array) by Tigger's rule."""
        frequency = np.asarray(frequency, float)
        if not self.spi:
            return np.full(frequency.shape, self.i) if frequency.ndim else self.i
        log = np.log(frequency / self.freq0)
        exponent = sum(c * log ** (k + 1) for k, c in enumerate(self.spi))
        return self.i * np.exp(exponent)


def _float(text):
    return float(text)


def parse_format(line):
    """Column index by field name from a `#format:` line (or DEFAULT_FORMAT)."""
    text = line.removeprefix("#format:")
    names = text.split()
    if not names:
        raise ValueError("empty lsm format line")
    columns = {}
    for index, name in enumerate(names):
        name = name.removesuffix("...")
        if name in columns:
            raise ValueError(f"duplicate lsm column {name!r}")
        columns[name] = index
    return columns


def _ra(fields, columns):
    if "ra_h" in columns:
        hours = _float(fields[columns["ra_h"]])
        hours += _float(fields[columns["ra_m"]]) / 60 if "ra_m" in columns else 0.0
        hours += _float(fields[columns["ra_s"]]) / 3600 if "ra_s" in columns else 0.0
        return math.radians(hours * 15.0)
    if "ra_d" in columns:
        return math.radians(_float(fields[columns["ra_d"]]))
    if "ra_rad" in columns:
        return _float(fields[columns["ra_rad"]])
    raise ValueError("lsm format lacks an RA column (ra_h, ra_d or ra_rad)")


def _dec(fields, columns):
    if "dec_d" in columns:
        text = fields[columns["dec_d"]]
        degrees = abs(_float(text))
        degrees += _float(fields[columns["dec_m"]]) / 60 if "dec_m" in columns else 0.0
        degrees += (
            _float(fields[columns["dec_s"]]) / 3600 if "dec_s" in columns else 0.0
        )
        sign_text = fields[columns["dec_sign"]] if "dec_sign" in columns else text
        return math.radians(-degrees if sign_text.startswith("-") else degrees)
    if "dec_rad" in columns:
        return _float(fields[columns["dec_rad"]])
    raise ValueError("lsm format lacks a Dec column (dec_d or dec_rad)")


def _extent(fields, columns, base):
    for unit, scale in ANGLE_UNITS.items():
        key = f"{base}_{unit}"
        if key in columns:
            return _float(fields[columns[key]]) * scale
    return 0.0


def parse_line(line, columns, default_freq0=None):
    fields = line.split()
    if len(fields) < max(columns.values()) + 1:
        raise ValueError(f"lsm line has {len(fields)} fields, format needs more")
    name = fields[columns["name"]] if "name" in columns else ""
    if "i" not in columns:
        raise ValueError("lsm format lacks the flux column i")
    values = {k: 0.0 for k in ("q", "u", "v")}
    for key in values:
        if key in columns:
            values[key] = _float(fields[columns[key]])
    freq0 = _float(fields[columns["freq0"]]) if "freq0" in columns else default_freq0
    spi = []
    for k in range(1, MAX_SPI_TERMS + 1):
        key = "spi" if k == 1 else f"spi{k}"
        spi.append(_float(fields[columns[key]]) if key in columns else 0.0)
    while spi and spi[-1] == 0.0:
        spi.pop()
    if spi and freq0 is None:
        raise ValueError(f"source {name!r} has a spectral index but no freq0")
    errors = {
        key[: -len("_err")]: _float(fields[index])
        for key, index in columns.items()
        if key.endswith("_err")
    }
    known = {
        "name",
        "ra_h",
        "ra_m",
        "ra_s",
        "ra_d",
        "ra_rad",
        "dec_d",
        "dec_m",
        "dec_s",
        "dec_rad",
        "dec_sign",
        "i",
        "q",
        "u",
        "v",
        "freq0",
    }
    known |= {"spi"} | {f"spi{k}" for k in range(2, MAX_SPI_TERMS + 1)}
    known |= {f"{b}_{u}" for b in ("emaj", "emin", "pa") for u in ANGLE_UNITS}
    extra = {
        key: fields[index]
        for key, index in columns.items()
        if key not in known and not key.endswith("_err") and index < len(fields)
    }
    return Source(
        name=name,
        ra=_ra(fields, columns),
        dec=_dec(fields, columns),
        i=_float(fields[columns["i"]]),
        q=values["q"],
        u=values["u"],
        v=values["v"],
        freq0=freq0,
        spi=tuple(spi),
        emaj=_extent(fields, columns, "emaj"),
        emin=_extent(fields, columns, "emin"),
        pa=_extent(fields, columns, "pa"),
        errors=errors,
        extra=extra,
    )


def loads(text, default_freq0=None):
    """Parse lsm text; returns the list of `Source`."""
    columns = None
    sources = []
    for number, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if number == 0 or columns is None:
            if line.startswith("#format:"):
                columns = parse_format(line)
                continue
            if columns is None:
                columns = parse_format(DEFAULT_FORMAT)
        if not line or line.startswith("#"):
            continue
        try:
            sources.append(parse_line(line, columns, default_freq0))
        except (ValueError, IndexError) as error:
            raise ValueError(f"lsm line {number + 1}: {error}") from error
    return sources


def load(path, default_freq0=None):
    return loads(Path(path).read_text(), default_freq0)


def direction_cosines(ra, dec, ra0, dec0):
    """SIN-projection (l, m) of (ra, dec) about the phase centre (ra0, dec0)."""
    ra, dec = np.asarray(ra, float), np.asarray(dec, float)
    delta = ra - ra0
    l = np.cos(dec) * np.sin(delta)
    m = np.sin(dec) * np.cos(dec0) - np.cos(dec) * np.sin(dec0) * np.cos(delta)
    return l, m


def components(sources, phase_centre):
    """Arguments of `core.predict_components` for Stokes I.

    Returns a dict with lm, kind, flux, coeffs, log_poly, ref_freq and
    gauss_shape. A source without a spectrum gets a zero coefficient and its
    own (or 1 Hz) reference frequency, which predicts a flat spectrum.
    """
    if not sources:
        raise ValueError("no sources")
    ra0, dec0 = phase_centre
    ncoeff = max(1, max(len(s.spi) for s in sources))
    coeffs = np.zeros((len(sources), ncoeff))
    for k, s in enumerate(sources):
        coeffs[k, : len(s.spi)] = s.spi
    l, m = direction_cosines(
        [s.ra for s in sources], [s.dec for s in sources], ra0, dec0
    )
    return {
        "lm": np.stack([l, m], 1),
        "kind": np.array([1 if s.gaussian else 0 for s in sources], np.uint8),
        "flux": np.array([s.i for s in sources], float),
        "coeffs": coeffs,
        "log_poly": np.ones(len(sources), bool),
        "ref_freq": np.array([s.freq0 or 1.0 for s in sources], float),
        "gauss_shape": np.array([[s.emaj, s.emin, s.pa] for s in sources], float),
    }


def summary(sources):
    """A JSON-ready description of a source list."""
    flux = np.array([s.i for s in sources])
    return {
        "components": len(sources),
        "gaussians": sum(s.gaussian for s in sources),
        "polarised": sum(bool(s.q or s.u or s.v) for s in sources),
        "reference_frequencies_hz": sorted({s.freq0 for s in sources if s.freq0}),
        "max_spectral_terms": max((len(s.spi) for s in sources), default=0),
        "total_flux_jy_at_freq0": float(flux.sum()),
        "brightest": sources[int(np.argmax(flux))].name if sources else None,
    }


__all__ = [
    "DEFAULT_FORMAT",
    "Source",
    "components",
    "direction_cosines",
    "load",
    "loads",
    "parse_format",
    "parse_line",
    "summary",
]
