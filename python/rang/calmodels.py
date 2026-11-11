# SPDX-License-Identifier: GPL-3.0-or-later
"""Calibrator models into MODEL_DATA, as CASA `setjy` writes them.

Task C3a (research/c3a-models.md), step 1 of the calibration chain
(research/c1-calibration-chain.md, term T0). The entry point is::

    from rang import calmodels

    receipt = calmodels.set_model(ms, "J1939-6342", calmodels.Standard())
    receipt = calmodels.set_model(ms, "3C286", {"standard": "manual",
        "fluxdensity": 14.7172, "reffreq": "1.47GHz",
        "spix": [-0.4507, -0.1798, 0.0357]})
    receipt = calmodels.set_model(ms, "J1939-6342", {"skymodel": "pks1934-638.lsm"})

Model specifications:

- `Standard`: a flux-density standard of `rang.fluxstd` (Stokes I with the
  standard's spectrum; Q = U = V = 0), a point at the field's phase centre,
  as `setjy(standard=..., scalebychan=True)`;
- `Manual`: `setjy(standard='manual', scalebychan=True)`: Stokes I
  `S0 (nu/nu0)^(sum_k spix_k log10(nu/nu0)^k)`, and (task C7a,
  research/c7a-polmodels.md) Q, U from `polindex`, `polangle` and `rotmeas`
  or from `fluxdensity=[I, Q, U, V]`, V as a constant fraction of I, in
  CASA's operation order; `NRAO_XCAL` and `caracal_xcal` hold CARACal's
  3C286 and 3C138 models;
- `PointStokes`: any per-channel (I, Q, U, V) of a point at the phase centre,
  mapped to the correlations (the groundwork of C1's T7);
- `SkyModel`: a component list (Tigger `.lsm`, `.lsm.html`, a WSClean source
  list) predicted by the core's `predict_components` with each row's UVW and
  its field's phase centre; Stokes I only.

Correlations are formed in the sky frame from Stokes (C1 1.1): `XX = I+Q`,
`XY = U+iV`, `YX = U-iV`, `YY = I-Q`; `RR = I+V`, `RL = Q+iU`, `LR = Q-iU`,
`LL = I-V`; in float64, cast once to complex64. Channel frequencies are
`CHAN_FREQ` as stored (CASA evaluates there, FS1). Rows of fields and
windows not selected are left as they are; a missing column is added and
initialised by `rang.core_writeback` (1 on the parallel hands, 0 on the cross
hands). All writes go through `core_writeback.WriteBack`.
"""

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import core_ms, fluxstd
from . import core_writeback as wb

C7A = (
    "polarised sky-model components are not implemented (task C7a implements "
    "polarised point models, Manual; core.predict_components is Stokes I only)"
)
# CORR_TYPE codes (casacore Stokes enum) this writer forms.
CORR_NAMES = {
    1: "I",
    2: "Q",
    3: "U",
    4: "V",
    5: "RR",
    6: "RL",
    7: "LR",
    8: "LL",
    9: "XX",
    10: "XY",
    11: "YX",
    12: "YY",
}
_UNITS = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9, "thz": 1e12}


def parse_frequency(value):
    """Hz from a number (Hz) or a CASA quantity string such as '1.4GHz'.
    The value is multiplied by the unit's factor in double, as casacore
    converts a quantity."""
    if isinstance(value, (int, float, np.integer, np.floating)):
        hz = float(value)
    else:
        match = re.fullmatch(r"\s*([-+0-9.eE]+)\s*([a-zA-Z]*)\s*", str(value))
        if not match or match.group(2).lower() not in _UNITS | {"": 1.0}:
            raise ValueError(f"cannot read a frequency from {value!r}")
        hz = float(match.group(1)) * _UNITS.get(match.group(2).lower(), 1.0)
    if not (math.isfinite(hz) and hz > 0):
        raise ValueError(f"frequency must be positive and finite, not {value!r}")
    return hz


def _times_i(z):
    """1j * z without the signed zeros of complex multiplication."""
    out = np.empty(np.shape(z), np.complex128)
    out.real = -np.imag(z)
    out.imag = np.real(z)
    return out


def correlations(stokes, corr_type):
    """Correlations (..., ncorr) complex128 from Stokes (..., 4) I, Q, U, V
    (real spectra or complex visibilities), for the CORR_TYPE codes given."""
    s = np.asarray(stokes)
    if s.shape[-1] != 4:
        raise ValueError("stokes must end in an axis of 4 (I, Q, U, V)")
    i, q, u, v = (s[..., k].astype(np.complex128) for k in range(4))
    forms = {
        1: lambda: i,
        2: lambda: q,
        3: lambda: u,
        4: lambda: v,
        5: lambda: i + v,
        6: lambda: q + _times_i(u),
        7: lambda: q - _times_i(u),
        8: lambda: i - v,
        9: lambda: i + q,
        10: lambda: u + _times_i(v),
        11: lambda: u - _times_i(v),
        12: lambda: i - q,
    }
    out = np.empty(s.shape[:-1] + (len(corr_type),), np.complex128)
    for k, code in enumerate(corr_type):
        if int(code) not in forms:
            raise ValueError(f"CORR_TYPE {code} is not handled")
        out[..., k] = forms[int(code)]()
    return out


# -- model specifications -----------------------------------------------------------


@dataclass(frozen=True)
class Standard:
    """A `rang.fluxstd` standard; `source` defaults to the field's name."""

    source: str = None
    standard: str = "Stevens-Reynolds 2016"
    extrapolate: bool = False
    unverified_ok: bool = False

    def stokes(self, freq_hz, field_name):
        return fluxstd.flux(
            self.source or field_name,
            freq_hz,
            self.standard,
            extrapolate=self.extrapolate,
            unverified_ok=self.unverified_ok,
        )

    def describe(self, field_name=None):
        m = fluxstd.model(self.source or field_name, self.standard)
        return {
            "kind": "standard",
            "standard": m.standard,
            "source": m.source,
            "provenance": m.provenance,
            "extrapolate": self.extrapolate,
        }


C_LIGHT = 299792458.0  # casacore C::c
MEAS_FREQ_LSRK, MEAS_FREQ_TOPO = 1, 5


def lsrk_over_topo(time_utc_s, ra_rad, dec_rad, itrf_xyz_m):
    """f_LSRK / f_TOPO for a source at (ra, dec) seen from `itrf_xyz_m` at MS
    TIME `time_utc_s`: 1 - v/c, v the topocentric-to-LSRK radial-velocity
    correction (astropy's barycentric correction plus the Sun's LSRK
    velocity projected on the source; IERS download off, as rang.measures).
    Task C7a, post hoc (research/c7a-polmodels.md section 9)."""
    from astropy.coordinates import ICRS, LSRK

    from . import measures

    units, _, _, SkyCoord, Time = measures._astropy()
    when = Time(time_utc_s / measures.MJD_SECONDS, format="mjd", scale="utc")
    source = SkyCoord(ra_rad * units.rad, dec_rad * units.rad, frame="icrs")
    v_bary = source.radial_velocity_correction(
        "barycentric", obstime=when, location=measures.location(itrf_xyz_m)
    ).to_value(units.m / units.s)
    kms, masyr = units.km / units.s, units.mas / units.yr
    at_rest = ICRS(
        ra=0 * units.deg, dec=0 * units.deg, distance=1 * units.pc,
        pm_ra_cosdec=0 * masyr, pm_dec=0 * masyr, radial_velocity=0 * kms,
    )  # fmt: skip
    vel = at_rest.transform_to(LSRK()).velocity.d_xyz.to_value(units.m / units.s)
    n = np.array(
        [math.cos(dec_rad) * math.cos(ra_rad), math.cos(dec_rad) * math.sin(ra_rad),
         math.sin(dec_rad)]
    )  # fmt: skip
    return 1.0 - (float(v_bary) + float(np.asarray(vel) @ n)) / C_LIGHT


def _floats(value):
    if value is None:
        return ()
    return tuple(float(a) for a in np.atleast_1d(np.asarray(value, float)))


def _horner(coeffs, x):
    """casacore `Polynomial<Double>::eval`: Horner from the highest term."""
    accum = coeffs[-1]
    for c in reversed(coeffs[:-1]):
        accum *= x
        accum += c
    return accum


@dataclass(frozen=True)
class Manual:
    """CASA's `setjy(standard='manual', scalebychan=True)` (task C7a,
    research/c7a-polmodels.md section 2): Stokes I from `fluxdensity`,
    `reffreq` and `spix` (log10, CASA's convention); linear polarisation from
    `polindex` and `polangle` (ordinary polynomials in (f - f0)/f0, angle in
    rad) or from Q and U, rotated by `rotmeas` relative to `reffreq`;
    V = I(f) * V/I. `fluxdensity` may be I or [I, Q, U, V]."""

    fluxdensity: float
    reffreq_hz: float
    spix: tuple = ()
    q: float = 0.0
    u: float = 0.0
    v: float = 0.0
    polindex: tuple = ()
    polangle: tuple = ()
    rotmeas: float = 0.0

    def __post_init__(self):
        flux = _floats(self.fluxdensity)
        if not 1 <= len(flux) <= 4:
            raise ValueError("manual fluxdensity is I or [I, Q, U, V]")
        quv = [self.q, self.u, self.v]
        if len(flux) > 1:
            if any(float(x) != 0 for x in quv):
                raise ValueError("give Q, U, V in fluxdensity or as q, u, v, not both")
            quv = list(flux[1:]) + [0.0] * (4 - len(flux))
        set_ = object.__setattr__
        set_(self, "fluxdensity", flux[0])
        set_(self, "q", float(quv[0]))
        set_(self, "u", float(quv[1]))
        set_(self, "v", float(quv[2]))
        set_(self, "reffreq_hz", parse_frequency(self.reffreq_hz))
        set_(self, "spix", _floats(self.spix))
        set_(self, "polindex", _floats(self.polindex))
        set_(self, "polangle", _floats(self.polangle))
        set_(self, "rotmeas", float(self.rotmeas or 0.0))
        values = (self.q, self.u, self.v, self.rotmeas)
        values += self.spix + self.polindex + self.polangle
        if not all(math.isfinite(x) for x in values):
            raise ValueError("manual model parameters must be finite")
        if not (math.isfinite(self.fluxdensity) and self.fluxdensity > 0):
            raise ValueError("manual fluxdensity must be a positive Stokes I in Jy")
        if self.q == 0 and self.u == 0 and bool(self.polindex) != bool(self.polangle):
            raise ValueError(
                "polindex and polangle must be given together (with only one, "
                "CASA's setjy silently writes no linear polarisation)"
            )

    @property
    def polarised(self):
        return bool(self.q or self.u or self.v or (self.polindex and self.polangle))

    @property
    def casa_path(self):
        """Which `setjy` model CASA builds (section 2, items 1 and 7)."""
        tab = len(self.spix) > 1 or len(self.polindex) > 1 or len(self.polangle) > 1
        if tab:
            return "tabular"
        return "spectral-index-channel0" if self.polarised else "spectral-index"

    def _linear(self):
        """Polynomial coefficients of p and chi after CASA's Q, U override
        (`sjy_setmanualflux`, item 4); () when there is no linear part."""
        pi, pa = list(self.polindex), list(self.polangle)
        if self.q != 0 or self.u != 0:
            pi0 = math.sqrt(self.q * self.q + self.u * self.u) / self.fluxdensity
            pa0 = 0.5 * math.atan2(self.u, self.q)
            if not pi or not pa:
                pi, pa = [0.0], [0.0]
            pi[0], pa[0] = pi0, pa0
        return (tuple(pi), tuple(pa)) if pi and pa else ((), ())

    def _tabular(self, nu, i_flux):
        """(nchan, 4) as `sjy_setmanualflux` fills its per-channel fluxes."""
        out = np.zeros(nu.shape + (4,))
        out[:, 0] = i_flux
        pi, pa = self._linear()
        f0, rm = self.reffreq_hz, self.rotmeas
        i_list = np.asarray(i_flux, float).tolist()
        for k, f in enumerate(nu.tolist()):
            if pi:
                x = (f - f0) / f0
                ipi, ipa = _horner(pi, x), _horner(pa, x)
                qv = ipi * i_list[k] * math.cos(2.0 * ipa)
                uv = ipi * i_list[k] * math.sin(2.0 * ipa)
                if rm != 0.0:
                    rot = (
                        2
                        * rm
                        * C_LIGHT
                        * C_LIGHT
                        * (f0 * f0 - f * f)
                        / (f * f * f0 * f0)
                    )
                    out[k, 1] = qv * math.cos(rot) - uv * math.sin(rot)
                    out[k, 2] = qv * math.sin(rot) + uv * math.cos(rot)
                else:
                    out[k, 1], out[k, 2] = qv, uv
            if self.v != 0.0:
                out[k, 3] = i_list[k] * (self.v / self.fluxdensity)
        return out

    def stokes(self, freq_hz, field_name=None, ch0_frame_ratio=1.0):
        """(nchan, 4) I, Q, U, V. `ch0_frame_ratio` is f(ch0) in `reffreq`'s
        frame (LSRK) over f(ch0) as stored; it matters only on CASA's
        polarised SpectralIndex path (post hoc, research/c7a-polmodels.md
        section 9), where `set_model` supplies it."""
        nu = np.asarray(freq_hz, float)
        i_flux = fluxstd.manual(nu, self.fluxdensity, self.reffreq_hz, self.spix)
        if not self.polarised:
            out = np.zeros(nu.shape + (4,))
            out[..., 0] = i_flux
            return out
        if nu.ndim != 1:
            raise ValueError("a polarised manual model needs a 1-d channel axis")
        path = self.casa_path
        if path == "tabular":
            return self._tabular(nu, i_flux)
        # SpectralIndex: channel 0's (I, Q, U, V) become the component's flux
        # at reference channel 0; `SpectralIndex::sampleStokes` scales and
        # rotates from there (stokes index [spix, 0, RM, 0]).
        # `sjy_setmanualflux` evaluates channel 0's I at the channel-0
        # frequency converted to reffreq's frame (`cvt`, Imager.cc 5468-5494),
        # Q and U at the stored one.
        i_ch0 = i_flux[:1]
        if ch0_frame_ratio != 1.0:
            i_ch0 = fluxstd.manual(
                nu[:1] * ch0_frame_ratio, self.fluxdensity, self.reffreq_hz, self.spix
            )
        i0, q0, u0, v0 = self._tabular(nu[:1], i_ch0)[0].tolist()
        # The component's flux goes Stokes -> linear (`predictVis`) -> Stokes
        # (`SkyCompRep::visibility`, `Flux::value`) before it is scaled; U and
        # V survive exactly, I and Q as (XX + YY)/2 and (XX - YY)/2.
        xx, yy = i0 + q0, i0 - q0
        ref = ((xx + yy) / 2, (xx - yy) / 2, u0, v0)
        alpha = self.spix[0] if self.spix else 0.0
        nu0, rm = float(nu[0]), self.rotmeas
        out = np.zeros(nu.shape + (4,))
        for k, f in enumerate(nu.tolist()):
            r = f / nu0
            out[k, 0] = ref[0] * math.pow(r, alpha)
            out[k, 3] = ref[3] * math.pow(r, alpha + 0.0)
            out[k, 1] = ref[1] * math.pow(r, alpha + 0.0)
            out[k, 2] = ref[2] * math.pow(r, alpha + 0.0)
            if rm != 0.0:
                two = (
                    2
                    * rm
                    * C_LIGHT
                    * C_LIGHT
                    * (nu0 * nu0 - f * f)
                    / (f * f * nu0 * nu0)
                )
                c2, s2 = math.cos(two), math.sin(two)
                qv = c2 * out[k, 1] - s2 * out[k, 2]
                out[k, 2] = s2 * out[k, 1] + c2 * out[k, 2]
                out[k, 1] = qv
        return out

    def describe(self, field_name=None):
        out = {
            "kind": "manual",
            "fluxdensity": self.fluxdensity,
            "reffreq_hz": self.reffreq_hz,
            "spix": list(self.spix),
        }
        if self.polarised:
            out.update(
                q=self.q,
                u=self.u,
                v=self.v,
                polindex=list(self.polindex),
                polangle=list(self.polangle),
                rotmeas=self.rotmeas,
                casa_path=self.casa_path,
            )
        return out


# CARACal's shipped polarisation-calibrator models (`caracal/data/nrao_xcal.yml`
# at 8f7bb363; NRAO's 2019 values at 1.47 GHz), with the aliases its polcal
# worker adds (`polcal_worker.py` lines 1424-1427).
NRAO_XCAL = {
    "3C138": {
        "fluxdensity": 8.33843,
        "spix": (-0.4981, -0.1552, -0.0102, 0.0223),
        "reffreq_hz": 1.47e9,
        "polindex": (0.078,),
        "polangle": (-0.16755,),
        "rotmeas": 0.0,
    },
    "3C286": {
        "fluxdensity": 14.7172,
        "spix": (-0.4507, -0.1798, 0.0357),
        "reffreq_hz": 1.47e9,
        "polindex": (0.098,),
        "polangle": (0.575959,),
        "rotmeas": 0.0,
    },
}
NRAO_XCAL_ALIASES = {"J1331+3030": "3C286", "J0521+1638": "3C138"}


def caracal_xcal(name):
    """CARACal's `nrao_xcal.yml` model of 3C286 or 3C138 (or an alias) as a
    `Manual`."""
    key = NRAO_XCAL_ALIASES.get(str(name), str(name))
    if key not in NRAO_XCAL:
        raise ValueError(
            f"no CARACal polarisation model for {name!r}; have "
            f"{sorted(NRAO_XCAL) + sorted(NRAO_XCAL_ALIASES)}"
        )
    return Manual(**NRAO_XCAL[key])


@dataclass(frozen=True)
class PointStokes:
    """A point at the phase centre with per-channel `stokes(freq_hz)` ->
    (nchan, 4) I, Q, U, V in Jy (any polarisation; C1's T7 groundwork)."""

    stokes_fn: object
    name: str = "point"

    def stokes(self, freq_hz, field_name=None):
        nu = np.asarray(freq_hz, float)
        s = np.asarray(self.stokes_fn(nu), float)
        if s.shape != nu.shape + (4,):
            raise ValueError(f"stokes_fn returned {s.shape}, need {nu.shape + (4,)}")
        return s

    def describe(self, field_name=None):
        return {"kind": "point-stokes", "name": self.name}


@dataclass(frozen=True)
class SkyModel:
    """A component list predicted by `core.predict_components` (Stokes I)."""

    path: str

    def sources(self):
        from .formats import sky

        sources = sky.load_any(self.path)
        if not sources:
            raise ValueError(f"{self.path}: no components")
        polarised = [s.name for s in sources if s.q or s.u or s.v]
        if polarised:
            raise NotImplementedError(
                f"{self.path}: components {polarised[:5]} carry Q, U or V; " + C7A
            )
        return sources

    def describe(self, field_name=None):
        data = Path(self.path).read_bytes()
        return {
            "kind": "skymodel",
            "path": str(self.path),
            "sha256": hashlib.sha256(data).hexdigest(),
        }


def spec_from_config(config):
    """A model spec from a config mapping (W2's `calibrate`):

    - `{"standard": "Stevens-Reynolds 2016", "source": "J1939-6342"}`
      (`source` optional: the field name); aliases as `fluxstd` (SR2016,
      PB2010, Baars, PB2017);
    - `{"standard": "manual", "fluxdensity": S or [I, Q, U, V],
      "reffreq": "1.4GHz", "spix": [...], "polindex": [...],
      "polangle": [...], "rotmeas": RM}` (the last three optional);
    - `{"skymodel": "path"}`.

    `scalebychan` may be given only as True and `usescratch` is ignored
    (both are CASA's). Unknown keys are refused."""
    if isinstance(config, (Standard, Manual, PointStokes, SkyModel)):
        return config
    cfg = dict(config)
    if cfg.pop("scalebychan", True) is not True:
        raise NotImplementedError("only scalebychan=True is implemented")
    cfg.pop("usescratch", None)
    if "skymodel" in cfg:
        spec = SkyModel(str(cfg.pop("skymodel")))
    else:
        if "standard" not in cfg:
            raise ValueError("a model needs 'standard' or 'skymodel'")
        standard = str(cfg.pop("standard"))
        if standard.lower() == "manual":
            if "fluxdensity" not in cfg or "reffreq" not in cfg:
                raise ValueError("a manual model needs fluxdensity and reffreq")
            spec = Manual(
                cfg.pop("fluxdensity"),
                cfg.pop("reffreq"),
                cfg.pop("spix", ()),
                polindex=cfg.pop("polindex", ()),
                polangle=cfg.pop("polangle", ()),
                rotmeas=cfg.pop("rotmeas", 0.0),
            )
        else:
            spec = Standard(
                source=cfg.pop("source", None),
                standard=standard,
                extrapolate=bool(cfg.pop("extrapolate", False)),
                unverified_ok=bool(cfg.pop("unverified_ok", False)),
            )
    if cfg:
        raise ValueError(f"unknown model keys {sorted(cfg)}")
    return spec


# -- the MS -------------------------------------------------------------------------


def metadata(ms):
    """Field names and phase centres, and per data description its window,
    channel frequencies and CORR_TYPE (subtables only, so it is safe while a
    write session holds the MS's lock)."""
    ms = Path(ms)
    with core_ms.open_table(ms / "FIELD") as t:
        names = [str(x) for x in t.getcol("NAME")]
        phase = np.asarray(t.getcol("PHASE_DIR"), float)
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freqs = [
            np.asarray(t.getcol("CHAN_FREQ", i, 1)[0], float) for i in range(t.nrows)
        ]
        frames = (
            [int(x) for x in t.getcol("MEAS_FREQ_REF")]
            if "MEAS_FREQ_REF" in t.colnames()
            else [None] * t.nrows
        )
    centroid = None
    if (ms / "ANTENNA").exists():
        with core_ms.open_table(ms / "ANTENNA") as t:
            if t.nrows and "POSITION" in t.colnames():
                centroid = np.asarray(t.getcol("POSITION"), float).mean(axis=0)
    with core_ms.open_table(ms / "POLARIZATION") as t:
        corr = [
            tuple(int(c) for c in t.getcol("CORR_TYPE", i, 1)[0])
            for i in range(t.nrows)
        ]
    with core_ms.open_table(ms / "DATA_DESCRIPTION") as t:
        spw = [int(x) for x in t.getcol("SPECTRAL_WINDOW_ID")]
        pol = [int(x) for x in t.getcol("POLARIZATION_ID")]
    return {
        "field_names": names,
        "phase_centres": phase.reshape(len(names), -1, 2)[:, 0, :],
        "ddid": [
            {
                "spw": s,
                "freq_hz": freqs[s],
                "corr_type": corr[p],
                "meas_freq_ref": frames[s],
            }
            for s, p in zip(spw, pol)
        ],
        "array_centroid_itrf_m": centroid,
    }


def _ids(selection, names, what):
    if selection is None:
        return list(range(len(names)))
    items = (
        [selection]
        if isinstance(selection, (str, int, np.integer))
        else list(selection)
    )
    out = []
    for item in items:
        if isinstance(item, (int, np.integer)):
            if not 0 <= int(item) < len(names):
                raise ValueError(f"{what} {item} does not exist ({len(names)} rows)")
            out.append(int(item))
        else:
            found = [k for k, n in enumerate(names) if n == str(item)]
            if not found:
                raise ValueError(f"no {what} named {item!r}; have {names}")
            out.extend(found)
    return sorted(set(out))


def _channel0_frames(ms, spec, meta, fields, ddids, session):
    """(TIME of main-table row 0, {(field, ddid): f_LSRK/f_stored of channel
    0}) for a `Manual` on CASA's polarised SpectralIndex path, which
    evaluates channel 0's I at that converted frequency (`Imager.cc` 4705,
    5466-5494; post hoc, research/c7a-polmodels.md section 9). Empty for
    every other model. TOPO is converted, LSRK is the identity, other frames
    are refused on this path."""
    if not (isinstance(spec, Manual) and spec.casa_path == "spectral-index-channel0"):
        return None, {}
    frames = {meta["ddid"][d]["meas_freq_ref"] for d in ddids}
    if not frames <= {MEAS_FREQ_TOPO, MEAS_FREQ_LSRK}:
        raise NotImplementedError(
            f"MEAS_FREQ_REF {sorted(frames, key=str)}: a polarised manual model with "
            "one spix term follows CASA's channel-0 frame conversion, implemented "
            "for TOPO and LSRK windows only"
        )
    if MEAS_FREQ_TOPO in frames and meta["array_centroid_itrf_m"] is None:
        raise ValueError("no ANTENNA positions for the TOPO-to-LSRK conversion")
    if MEAS_FREQ_TOPO in frames:
        import importlib.util

        if importlib.util.find_spec("astropy") is None:
            raise NotImplementedError(
                "a polarised manual model with one spix term needs astropy "
                "(pip install 'rang-core[imaging]') for CASA's channel-0 LSRK "
                "conversion"
            )
    if session is not None:
        time0 = float(np.asarray(session.read("TIME", 0, 1))[0])
    else:
        with core_ms.open_table(ms) as t:
            time0 = float(np.asarray(t.getcol("TIME", 0, 1))[0])
    out = {}
    for f in fields:
        ra, dec = (float(x) for x in meta["phase_centres"][f])
        for d in ddids:
            if meta["ddid"][d]["meas_freq_ref"] == MEAS_FREQ_LSRK:
                out[f, d] = 1.0
            else:
                out[f, d] = lsrk_over_topo(
                    time0, ra, dec, meta["array_centroid_itrf_m"]
                )
    return time0, out


def set_model(
    ms,
    field,
    model,
    *,
    spw=None,
    column="MODEL_DATA",
    session=None,
    chunk_rows=None,
):
    """Write `model` (a spec or a config mapping, see `spec_from_config`)
    into `column` for the rows of `field` (a name, index or list) and `spw`
    (window ids; default all). Rows of other fields and windows keep their
    values. `session` is an open `core_writeback.WriteBack` on `ms` to write
    through (W2 passes one); without it a session is opened (stage
    'setjy'), which saves the original flags first as W1 does. Returns a
    receipt (dict)."""
    ms = Path(ms)
    spec = spec_from_config(model)
    meta = metadata(ms)
    fields = _ids(field, meta["field_names"], "field")
    spws = (
        None
        if spw is None
        else set(
            _ids(
                spw,
                [str(i) for i in range(1 + max(d["spw"] for d in meta["ddid"]))],
                "spw",
            )
        )
    )
    ddids = [k for k, d in enumerate(meta["ddid"]) if spws is None or d["spw"] in spws]
    if not ddids:
        raise ValueError(f"no data description has spectral window {sorted(spws)}")
    sky_args, time0, frame = None, None, {}
    point, spectra = {}, {}
    if isinstance(spec, SkyModel):
        from .formats import sky

        sources = spec.sources()
        sky_args = {
            f: sky.components(sources, tuple(meta["phase_centres"][f])) for f in fields
        }
    else:
        time0, frame = _channel0_frames(ms, spec, meta, fields, ddids, session)
        for f in fields:
            for d in ddids:
                dd = meta["ddid"][d]
                kw = {"ch0_frame_ratio": frame[f, d]} if (f, d) in frame else {}
                stokes = spec.stokes(dd["freq_hz"], meta["field_names"][f], **kw)
                spectra[f, d] = stokes
                point[f, d] = correlations(stokes, dd["corr_type"]).astype(np.complex64)
    receipt = {
        "ms": str(ms),
        "column": column,
        "spec": spec.describe(meta["field_names"][fields[0]]),
        "fields": {},
    }
    if sky_args is None and frame:
        centroid = meta["array_centroid_itrf_m"]
        receipt["channel0_frame"] = {
            "epoch_time_utc_s": time0,
            "array_centroid_itrf_m": None if centroid is None else centroid.tolist(),
            "lsrk_over_topo": {
                f"{meta['field_names'][f]}/spw{meta['ddid'][d]['spw']}": v
                for (f, d), v in frame.items()
            },
        }
    own = session is None
    w = wb.WriteBack(ms, stage="setjy") if own else session
    error = None
    try:
        if own:
            w.begin()
        init = "default" if column in wb.DEFAULT_INIT else "unity"
        receipt["column_added"] = bool(w.ensure_column(column, init=init))
        rows_written = dict.fromkeys(fields, 0)
        for start, n in w.chunks(chunk_rows):
            fid = np.asarray(w.read("FIELD_ID", start, n))
            did = np.asarray(w.read("DATA_DESC_ID", start, n))
            sel = np.isin(fid, fields) & np.isin(did, ddids)
            if not sel.any():
                continue
            values = w.read(column, start, n)
            uvw = w.read("UVW", start, n) if sky_args is not None else None
            for f in fields:
                for d in ddids:
                    rows = sel & (fid == f) & (did == d)
                    if not rows.any():
                        continue
                    if sky_args is None:
                        values[rows] = point[f, d]
                    else:
                        from . import core

                        dd = meta["ddid"][d]
                        vis = core.predict_components(
                            uvw[rows], dd["freq_hz"], **sky_args[f]
                        )
                        stokes = np.zeros(vis.shape + (4,), np.complex128)
                        stokes[..., 0] = vis
                        values[rows] = correlations(stokes, dd["corr_type"]).astype(
                            np.complex64
                        )
                    rows_written[f] += int(rows.sum())
            w.write(column, start, values)
    except BaseException as exc:
        error = exc
        raise
    finally:
        if own:
            w.close(error=error)
    for f in fields:
        name = meta["field_names"][f]
        entry = {"field_id": f, "rows": rows_written[f]}
        if sky_args is None:
            per = {}
            for d in ddids:
                dd = meta["ddid"][d]
                nu = dd["freq_hz"]
                pick = [0, len(nu) // 2, len(nu) - 1]
                per[str(dd["spw"])] = {
                    "freq_hz": nu[pick].tolist(),
                    "stokes_i_jy": spectra[f, d][pick, 0].tolist(),
                }
                if np.any(spectra[f, d][:, 1:] != 0):
                    per[str(dd["spw"])]["stokes_iquv_jy"] = spectra[f, d][pick].tolist()
            entry["spectral_windows"] = per
        else:
            entry["components"] = len(sky_args[f]["flux"])
            entry["phase_centre_rad"] = meta["phase_centres"][f].tolist()
        receipt["fields"][name] = entry
    return receipt


__all__ = [
    "NRAO_XCAL",
    "NRAO_XCAL_ALIASES",
    "Manual",
    "PointStokes",
    "SkyModel",
    "Standard",
    "caracal_xcal",
    "correlations",
    "metadata",
    "parse_frequency",
    "set_model",
    "spec_from_config",
]
