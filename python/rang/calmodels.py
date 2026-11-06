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
- `Manual`: `setjy(standard='manual', scalebychan=True)` Stokes I,
  `S0 (nu/nu0)^(sum_k spix_k log10(nu/nu0)^k)`; the polarised parameters
  (`polindex`, `polangle`, `rotmeas`) are C1 step 8 (task C7a) and refused;
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
    "polarised calibrator models (polindex, polangle, rotmeas, or nonzero Q, U, "
    "V) are C1 step 8 (task C7a) and not implemented in C3a"
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


@dataclass(frozen=True)
class Manual:
    """CASA's `standard='manual'` Stokes I (spix in log10, CASA's convention)."""

    fluxdensity: float
    reffreq_hz: float
    spix: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "fluxdensity", float(self.fluxdensity))
        object.__setattr__(self, "reffreq_hz", parse_frequency(self.reffreq_hz))
        spix = np.atleast_1d(np.asarray(self.spix, float))
        object.__setattr__(self, "spix", tuple(float(a) for a in spix))
        if not (math.isfinite(self.fluxdensity) and self.fluxdensity > 0):
            raise ValueError("manual fluxdensity must be a positive Stokes I in Jy")

    def stokes(self, freq_hz, field_name=None):
        nu = np.asarray(freq_hz, float)
        out = np.zeros(nu.shape + (4,))
        out[..., 0] = fluxstd.manual(nu, self.fluxdensity, self.reffreq_hz, self.spix)
        return out

    def describe(self, field_name=None):
        return {
            "kind": "manual",
            "fluxdensity": self.fluxdensity,
            "reffreq_hz": self.reffreq_hz,
            "spix": list(self.spix),
        }


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
                f"{self.path}: components {polarised[:5]} carry Q, U or V; "
                "core.predict_components predicts Stokes I only, and " + C7A
            )
        return sources

    def describe(self, field_name=None):
        data = Path(self.path).read_bytes()
        return {
            "kind": "skymodel",
            "path": str(self.path),
            "sha256": hashlib.sha256(data).hexdigest(),
        }


def _scalar_flux(value):
    """I from CASA's fluxdensity (a number or [I, Q, U, V])."""
    values = np.atleast_1d(np.asarray(value, float))
    if values.size > 4 or np.any(values[1:] != 0):
        raise NotImplementedError(C7A)
    return float(values[0])


def spec_from_config(config):
    """A model spec from a config mapping (W2's `calibrate`):

    - `{"standard": "Stevens-Reynolds 2016", "source": "J1939-6342"}`
      (`source` optional: the field name); aliases as `fluxstd` (SR2016,
      PB2010, Baars, PB2017);
    - `{"standard": "manual", "fluxdensity": S, "reffreq": "1.4GHz",
      "spix": [...]}`;
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
            for key in ("polindex", "polangle", "rotmeas"):
                value = cfg.pop(key, None)
                if value is not None and np.any(np.asarray(value, float) != 0):
                    raise NotImplementedError(C7A)
            if "fluxdensity" not in cfg or "reffreq" not in cfg:
                raise ValueError("a manual model needs fluxdensity and reffreq")
            spec = Manual(
                _scalar_flux(cfg.pop("fluxdensity")),
                cfg.pop("reffreq"),
                cfg.pop("spix", ()),
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
            {"spw": s, "freq_hz": freqs[s], "corr_type": corr[p]}
            for s, p in zip(spw, pol)
        ],
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
    sky_args = None
    point, spectra = {}, {}
    if isinstance(spec, SkyModel):
        from .formats import sky

        sources = spec.sources()
        sky_args = {
            f: sky.components(sources, tuple(meta["phase_centres"][f])) for f in fields
        }
    else:
        for f in fields:
            for d in ddids:
                dd = meta["ddid"][d]
                stokes = spec.stokes(dd["freq_hz"], meta["field_names"][f])
                spectra[f, d] = stokes[:, 0]
                point[f, d] = correlations(stokes, dd["corr_type"]).astype(np.complex64)
    receipt = {
        "ms": str(ms),
        "column": column,
        "spec": spec.describe(meta["field_names"][fields[0]]),
        "fields": {},
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
                    "stokes_i_jy": spectra[f, d][pick].tolist(),
                }
            entry["spectral_windows"] = per
        else:
            entry["components"] = len(sky_args[f]["flux"])
            entry["phase_centre_rad"] = meta["phase_centres"][f].tolist()
        receipt["fields"][name] = entry
    return receipt


__all__ = [
    "Manual",
    "PointStokes",
    "SkyModel",
    "Standard",
    "correlations",
    "metadata",
    "parse_frequency",
    "set_model",
    "spec_from_config",
]
