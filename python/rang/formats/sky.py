"""Sky-model formats (research/dfio-formats.md, F3; was `rang.lsm`).

One `Source` list for every text format:

- Tigger ASCII `.lsm`/`.txt`: `loads`/`load` (below) and `dumps_ascii`;
- Tigger `.lsm.html`: `loads_html`/`load_html` (a safe parser: values are
  read with `ast.literal_eval`, never `eval` as Tigger does) and
  `dumps_html`, rendered as Tigger's `ModelHTML.save` renders a model;
- WSClean/Crystalball source lists: `loads_wsclean`/`load_wsclean` and
  `dumps_wsclean` (`Format = Name, Type, Ra, Dec, I, SpectralIndex,
  LogarithmicSI, ReferenceFrequency, MajorAxis, MinorAxis, Orientation`;
  axes FWHM in arcsec, orientation in degrees);
- BBS (`makesourcedb`/LSMTool) `.skymodel`: `loads_bbs`/`load_bbs`
  (read only);
- DDFacet `DicoModel` (read only, a restricted unpickler; never on
  untrusted files) and DDFacet/killMS `ClusterCat` `.npy` (read and write).

`load_any`/`save_any` dispatch on the file name.

The Tigger ASCII reader follows Tigger's ASCII loader (astro-tigger-lsm,
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

import ast
import html.parser
import math
import pickle
import re
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
    # WSClean's LogarithmicSI: False for an ordinary polynomial spectrum
    # S0 + sum c_k (nu/nu0 - 1)^(k+1) (WSClean lists only).
    log_si: bool = True

    @property
    def gaussian(self):
        return self.emaj != 0.0 or self.emin != 0.0

    def flux(self, frequency):
        """Stokes I at `frequency` (Hz, scalar or array) by Tigger's rule
        (or WSClean's ordinary polynomial when `log_si` is False)."""
        frequency = np.asarray(frequency, float)
        if not self.spi:
            return np.full(frequency.shape, self.i) if frequency.ndim else self.i
        if not self.log_si:
            x = frequency / self.freq0 - 1
            return self.i + sum(c * x ** (k + 1) for k, c in enumerate(self.spi))
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
        "log_poly": np.array([s.log_si for s in sources], bool),
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


# -- Tigger .lsm.html ----------------------------------------------------------

_TIGGER_ATOMS = {"bool", "int", "float", "complex", "str", "NoneType"}


class _TiggerParser(html.parser.HTMLParser):
    """Tigger's `ModelIndexParser` without `eval`: objects are (type, args,
    kwargs) tuples, inline values are read with `ast.literal_eval`."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.stack, self.top = [], [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append([tag, None])
        mdltype = attrs.get("mdltype")
        if not mdltype:
            return
        attr, val = attrs.get("mdlattr"), attrs.get("mdlval")
        if val is not None:
            if mdltype not in _TIGGER_ATOMS:
                raise ValueError(f"inline value for non-atomic Tigger type {mdltype}")
            value = None if mdltype == "NoneType" else ast.literal_eval(val)
            if mdltype == "float":
                value = float(value)
            self._add(attr, value)
        else:
            self.tags[-1][1] = len(self.stack)
            self.stack.append([attr, mdltype, [], {}])

    def handle_endtag(self, endtag):
        while self.tags:
            tag, nobj = self.tags.pop()
            if nobj is not None:
                attr, mdltype, args, kws = self.stack.pop()
                if mdltype in ("list", "tuple"):
                    obj = list(args)
                elif mdltype == "dict":
                    obj = dict(kws)
                else:
                    obj = (mdltype, args, kws)
                self._add(attr, obj)
            if tag == endtag:
                break

    def _add(self, attr, obj):
        if not self.stack:
            if not attr:
                self.top.append(obj)
            return
        if attr:
            self.stack[-1][3][attr] = obj
        else:
            self.stack[-1][2].append(obj)


def _named(obj, names):
    """A Tigger object's attributes by name (mandatory then keywords)."""
    _, args, kws = obj
    out = dict(zip(names, args))
    out.update(kws)
    return out


def _tigger_source(obj):
    s = _named(obj, ["name", "pos", "flux"])
    pos = _named(s.pop("pos"), ["ra", "dec"])
    fl = s.pop("flux")
    flux = _named(
        fl,
        ["I", "Q", "U", "V", "rm", "freq0"]
        if fl[0] == "PolarizationWithRM"
        else ["I", "Q", "U", "V"],
    )
    errors, extra = {}, {}
    for k in ("I", "Q", "U", "V"):
        if f"{k}_err" in flux:
            errors[k.lower()] = flux[f"{k}_err"]
    for k in ("ra", "dec"):
        if pos.get(f"{k}_err") is not None:
            errors[k] = pos[f"{k}_err"]
    freq0, spi = None, ()
    spectrum = s.pop("spectrum", None)
    if spectrum is not None:
        sp = _named(spectrum, ["spi", "freq0"])
        freq0 = sp.get("freq0")
        spi = tuple(
            float(x)
            for x in (sp["spi"] if isinstance(sp["spi"], list) else [sp["spi"]])
        )
        if "spi_err" in sp:
            e = sp["spi_err"] if isinstance(sp["spi_err"], list) else [sp["spi_err"]]
            for k, x in enumerate(e):
                errors["spi" if k == 0 else f"spi{k + 1}"] = x
    emaj = emin = pa = 0.0
    shape = s.pop("shape", None)
    if shape is not None:
        if shape[0] != "Gaussian":
            raise ValueError(f"unsupported Tigger shape {shape[0]}")
        sh = _named(shape, ["ex", "ey", "pa"])
        emaj, emin, pa = float(sh["ex"]), float(sh["ey"]), float(sh["pa"])
        for k, n in (("ex", "emaj"), ("ey", "emin"), ("pa", "pa")):
            if sh.get(f"{k}_err") is not None:
                errors[n] = sh[f"{k}_err"]
    name = s.pop("name")
    extra.update(s)
    if "rm" in flux:
        extra["rm"] = flux["rm"]
    return Source(
        name=name,
        ra=float(pos["ra"]),
        dec=float(pos["dec"]),
        i=float(flux["I"]),
        q=float(flux.get("Q", 0.0)),
        u=float(flux.get("U", 0.0)),
        v=float(flux.get("V", 0.0)),
        freq0=None if freq0 is None else float(freq0),
        spi=spi,
        emaj=emaj,
        emin=emin,
        pa=pa,
        errors=errors,
        extra=extra,
    )


@dataclass
class Model:
    """A source list with Tigger's model-level attributes."""

    sources: list
    freq0: float | None = None
    ra0: float | None = None
    dec0: float | None = None
    name: str | None = None
    attributes: dict = field(default_factory=dict)


def loads_html(text):
    """A Tigger `.lsm.html` model as a `Model` (sources in file order)."""
    parser = _TiggerParser()
    parser.feed(text)
    parser.close()
    if not parser.top or parser.top[0][0] != "SkyModel":
        raise ValueError("no Tigger SkyModel in the file")
    _, args, kws = parser.top[0]
    sources = [
        _tigger_source(o) for o in args if isinstance(o, tuple) and o[0] == "Source"
    ]
    known = {"freq0", "ra0", "dec0", "name", "plotstyles", "pbexp"}
    return Model(
        sources,
        freq0=kws.get("freq0"),
        ra0=kws.get("ra0"),
        dec0=kws.get("dec0"),
        name=kws.get("name"),
        attributes={k: v for k, v in kws.items() if k not in known},
    )


def load_html(path):
    return loads_html(Path(path).read_text())


def _resolve(tags):
    if not tags:
        return "A", "</A> ", None
    if isinstance(tags, str):
        tag, rest = tags, None
    else:
        tag, rest = tags[0], list(tags[1:])
    if tag.endswith("\n"):
        tag = tag[:-1]
        return tag, f"</{tag}>\n", rest
    return tag, f"</{tag}> ", rest


def _type_name(value):
    if isinstance(value, bool):
        return "bool"
    return type(value).__name__


def _attr_markup(attr, value, tags=None, verbose=None, mandatory=False):
    """Tigger's `ModelItem.renderAttrMarkup` for atoms, lists and dicts."""
    if isinstance(value, _Item):
        return value.markup(tags, None if mandatory else attr)
    tag, endtag, tags = _resolve(tags)
    if isinstance(value, np.integer):
        value = int(value)
    elif isinstance(value, np.floating):
        value = float(value)
    markup = f"<{tag} mdltype={_type_name(value)} "
    if not mandatory:
        markup += f'mdlattr="{attr}" '
    if verbose is None:
        verbose = attr
    comment = "<TD bgcolor=yellow>%s</TD>" if tag == "TR" else "<A>%s</A> "
    if isinstance(value, (list, tuple)):
        markup += ">"
        if verbose:
            markup += comment % (verbose + ":")
        for i, item in enumerate(value):
            markup += _attr_markup(str(i), item, tags, mandatory=True)
    elif isinstance(value, dict):
        markup += ">"
        if verbose:
            markup += comment % (verbose + ":")
        for key, item in sorted(value.items()):
            markup += _attr_markup(key, item, tags)
    else:
        if isinstance(value, str):
            escaped = value.replace('"', '\\"').replace("'", "\\'")
            markup += f"mdlval=\"'{escaped}'\">"
        else:
            markup += f'mdlval="{value!r}">'
        if verbose is attr:
            markup += comment % ":".join((attr, str(value)))
        else:
            markup += comment % "".join((verbose, str(value)))
    return markup + endtag


class _Item:
    """A Tigger ModelItem: type name, mandatory and optional attributes."""

    def __init__(self, kind, mandatory, optional=(), extra=()):
        self.kind, self.mandatory = kind, list(mandatory)
        self.optional, self.extra = sorted(optional), list(extra)

    def markup(self, tags=None, attrname=None):
        tag, endtag, tags = _resolve(tags)
        out = f"<{tag} mdltype={self.kind} "
        if attrname is not None:
            out += f'mdlattr="{attrname}" '
        out += ">"
        if attrname:
            out += (
                f"<TD bgcolor=yellow>{attrname}</TD>"
                if tag == "TR"
                else f"<A>{attrname}:</A> "
            )
        for attr, value in self.mandatory:
            out += _attr_markup(attr, value, tags, mandatory=True)
        for attr, value in self.optional:
            out += _attr_markup(attr, value, tags)
        for attr, value in self.extra:
            out += _attr_markup(attr, value, tags)
        return out + endtag


def _source_item(s):
    err = s.errors
    flux_opt = [(f"{k.upper()}_err", err[k]) for k in ("i", "q", "u", "v") if k in err]
    flux = _Item(
        "Polarization", [("I", s.i), ("Q", s.q), ("U", s.u), ("V", s.v)], flux_opt
    )
    pos_opt = [(f"{k}_err", err[k]) for k in ("ra", "dec") if k in err]
    optional = []
    if s.gaussian:
        shape_opt = [
            (f"{t}_err", err[n])
            for t, n in (("ex", "emaj"), ("ey", "emin"), ("pa", "pa"))
            if n in err
        ]
        optional.append(
            (
                "shape",
                _Item(
                    "Gaussian",
                    [("ex", s.emaj), ("ey", s.emin), ("pa", s.pa)],
                    shape_opt,
                ),
            )
        )
    if s.spi:
        spi = list(s.spi) if len(s.spi) > 1 else s.spi[0]
        keys = ["spi"] + [f"spi{k}" for k in range(2, len(s.spi) + 1)]
        spi_opt = []
        if all(k in err for k in keys):
            e = [err[k] for k in keys]
            spi_opt = [("spi_err", e if len(e) > 1 else e[0])]
        optional.append(
            (
                "spectrum",
                _Item("SpectralIndex", [("spi", spi), ("freq0", s.freq0)], spi_opt),
            )
        )
    extra = sorted((k, v) for k, v in s.extra.items() if k != "rm")
    return _Item(
        "Source",
        [
            ("name", s.name),
            ("pos", _Item("Position", [("ra", s.ra), ("dec", s.dec)], pos_opt)),
            ("flux", flux),
        ],
        optional,
        extra,
    )


def dumps_html(sources, freq0=None, ra0=None, dec0=None, name=None):
    """A Tigger `.lsm.html` model, rendered as `ModelHTML.save` renders one
    (extra attributes in sorted order; Tigger takes them from a set)."""
    out = ["<HTML><BODY mdltype=SkyModel>\n"]
    if name is not None:
        out.append(_attr_markup("name", name, "TITLE", "Sky model: ") + "\n")
    out.append(
        "<H1>Source list</H1>\n<TABLE BORDER=1 FRAME=box RULES=all CELLPADDING=5>\n"
    )
    for s in sources:
        out.append(_source_item(s).markup(["TR\n", "TD"]) + "\n")
    out.append("</TABLE>\n")
    out.append(
        "<H1>Plot styles</H1>\n<TABLE BORDER=1 FRAME=box RULES=all CELLPADDING=5>\n"
    )
    out.append(_attr_markup("plotstyles", {}, ["A", "TR\n", "TD"], ""))
    out.append("</TABLE>\n")
    out.append("\n<H1>Other properties</H1>\n")
    if freq0 is not None:
        out.append(
            "<P>"
            + _attr_markup("freq0", freq0, "A", "Reference frequency, Hz: ")
            + "</P>\n"
        )
    if ra0 is not None or dec0 is not None:
        out.append(
            "<P>"
            + _attr_markup("ra0", ra0, "A", "Field centre ra: ")
            + _attr_markup("dec0", dec0, "A", "dec: ")
            + "</P>\n"
        )
    out.append("</BODY></HTML>\n")
    return "".join(out)


# -- Tigger ASCII (write) -------------------------------------------------------


def dumps_ascii(sources):
    """Tigger ASCII with exact (`repr`) radians: `#format: name ra_rad
    dec_rad i q u v spi spi2 ... freq0 emaj_rad emin_rad pa_rad`."""
    nspi = max((len(s.spi) for s in sources), default=0)
    spi_cols = ["spi"] + [f"spi{k}" for k in range(2, nspi + 1)] if nspi else []
    cols = [
        "name",
        "ra_rad",
        "dec_rad",
        "i",
        "q",
        "u",
        "v",
        *spi_cols,
        "freq0",
        "emaj_rad",
        "emin_rad",
        "pa_rad",
    ]
    lines = ["#format: " + " ".join(cols)]
    for s in sources:
        spi = list(s.spi) + [0.0] * (nspi - len(s.spi))
        values = [
            s.ra,
            s.dec,
            s.i,
            s.q,
            s.u,
            s.v,
            *spi,
            s.freq0 or 0.0,
            s.emaj,
            s.emin,
            s.pa,
        ]
        if " " in s.name or not s.name:
            raise ValueError(
                f"source name {s.name!r} cannot be written as Tigger ASCII"
            )
        lines.append(" ".join([s.name] + [repr(float(v)) for v in values]))
    return "\n".join(lines) + "\n"


# -- WSClean / Crystalball source lists -------------------------------------------

WSCLEAN_FORMAT = (
    "Format = Name, Type, Ra, Dec, I, SpectralIndex, LogarithmicSI, "
    "ReferenceFrequency, MajorAxis, MinorAxis, Orientation"
)


def _hms(rad, places=10):
    hours = (rad % (2 * math.pi)) * 12 / math.pi
    h = int(hours)
    m = int((hours - h) * 60)
    s = ((hours - h) * 60 - m) * 60
    text = f"{s:0{places + 3}.{places}f}"
    if float(text) >= 60:  # rounding carried
        text, m = f"{0:0{places + 3}.{places}f}", m + 1
        if m == 60:
            m, h = 0, (h + 1) % 24
    return f"{h:02d}:{m:02d}:{text}"


def _dms(rad, places=9):
    sign = "-" if rad < 0 or (rad == 0 and math.copysign(1, rad) < 0) else "+"
    deg = abs(rad) * 180 / math.pi
    d = int(deg)
    m = int((deg - d) * 60)
    s = ((deg - d) * 60 - m) * 60
    text = f"{s:0{places + 3}.{places}f}"
    if float(text) >= 60:
        text, m = f"{0:0{places + 3}.{places}f}", m + 1
        if m == 60:
            m, d = 0, d + 1
    return f"{sign}{d:02d}.{m:02d}.{text}"


def _ra_hms(text):
    sign = -1 if text.strip().startswith("-") else 1
    h, m, s = text.strip().lstrip("+-").split(":")
    value = float(h) / 24.0 + float(m) / (24.0 * 60.0) + float(s) / (24.0 * 60.0 * 60.0)
    return sign * 2.0 * math.pi * value


def _dec_dms(text):
    t = text.strip()
    sign = -1 if t.startswith("-") else 1
    d, m, s = t.lstrip("+-").split(".", 2)
    value = (
        float(d) / 360.0 + float(m) / (360.0 * 60.0) + float(s) / (360.0 * 60.0 * 60.0)
    )
    return sign * 2.0 * math.pi * value


def _exact_text(value, forward, back):
    """The decimal text of `forward(value)` whose reading `back(float(text))`
    gives `value` back exactly (searched over neighbouring floats), else
    the plain `repr`."""
    x = forward(value)
    candidates = [x]
    lo = hi = x
    for _ in range(64):
        lo, hi = math.nextafter(lo, -math.inf), math.nextafter(hi, math.inf)
        candidates += [lo, hi]
    for c in candidates:
        if back(float(repr(c))) == value:
            return repr(c)
    return repr(x)


def _arcsec_text(rad):
    """Arcsec text that WSClean's readers (africanus: deg2rad(x / 3600))
    turn back into `rad` exactly (post hoc, research/dfio-formats.md)."""
    return _exact_text(
        rad, lambda r: math.degrees(r) * 3600, lambda x: math.radians(x / 3600.0)
    )


def _degree_text(rad):
    return _exact_text(rad, math.degrees, math.radians)


def dumps_wsclean(sources, pad_spectra=True):
    """A WSClean source list (Crystalball's input): RA h:m:s and Dec d.m.s
    with 1e-10 s and 1e-9 arcsec digits, fluxes and spectral terms as
    `repr`, axes FWHM in arcsec, orientation in degrees. With
    `pad_spectra` every SpectralIndex list is padded with zero terms to
    the longest one (the same spectra): Crystalball 0.4.3 stacks the
    lists into one array and refuses lists of different lengths."""
    lines = [WSCLEAN_FORMAT]
    nspi = max((len(s.spi) for s in sources), default=0) if pad_spectra else 0
    for s in sources:
        if "," in s.name:
            raise ValueError(f"source name {s.name!r} contains a comma")
        kind = "GAUSSIAN" if s.gaussian else "POINT"
        terms = list(s.spi) + [0.0] * max(0, nspi - len(s.spi))
        spi = "[" + ",".join(repr(float(c)) for c in terms) + "]"
        shape = (
            [_arcsec_text(s.emaj), _arcsec_text(s.emin), _degree_text(s.pa)]
            if s.gaussian
            else ["", "", ""]
        )
        lines.append(
            ",".join(
                [
                    s.name,
                    kind,
                    _hms(s.ra),
                    _dms(s.dec),
                    repr(float(s.i)),
                    spi,
                    "true" if s.log_si else "false",
                    repr(float(s.freq0 or 0.0)),
                    *shape,
                ]
            )
        )
    return "\n".join(lines) + "\n"


_COMMA = re.compile(r",\s*(?=[^\]]*(?:\[|$))")
_HEADER_FIELD = re.compile(r"^\s*?(?P<name>.*?)(\s*?=\s*?'(?P<default>.*?)'\s*?){0,1}$")


def _header_fields(text):
    names, defaults = [], []
    for part in text.split(","):
        m = _HEADER_FIELD.search(part.strip())
        names.append(m.group("name").strip())
        defaults.append(m.group("default"))
    return names, defaults


def loads_wsclean(text):
    """A WSClean source list (as WSClean writes it, `-save-source-list`)."""
    lines = [
        ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")
    ]
    if not lines:
        raise ValueError("empty WSClean source list")
    head, _, desc = lines[0].partition("=")
    if head.strip().lower() != "format":
        raise ValueError("not a WSClean source list (no Format line)")
    names, defaults = _header_fields(desc)
    sources = []
    for number, line in enumerate(lines[1:], 2):
        parts = [p.strip() for p in _COMMA.split(line)]
        if len(parts) != len(names):
            raise ValueError(
                f"WSClean line {number} has {len(parts)} fields, expected {len(names)}"
            )
        row = {}
        for name, value, default in zip(names, parts, defaults):
            row[name] = value if value else (default or "")
        spi_text = row.get("SpectralIndex", "").strip("[] ")
        spi = tuple(float(c) for c in spi_text.split(",")) if spi_text else ()
        while spi and spi[-1] == 0.0:  # trailing zero terms, as Tigger drops them
            spi = spi[:-1]
        gaussian = row.get("Type", "POINT").upper() == "GAUSSIAN"

        def arcsec(key, row=row):
            return math.radians(float(row.get(key) or 0.0) / 3600.0)

        extra = {k: v for k, v in row.items() if k not in WSCLEAN_FORMAT and v}
        sources.append(
            Source(
                name=row.get("Name", ""),
                ra=_ra_hms(row["Ra"]),
                dec=_dec_dms(row["Dec"]),
                i=float(row["I"]),
                freq0=float(row["ReferenceFrequency"])
                if row.get("ReferenceFrequency")
                else None,
                spi=spi,
                emaj=arcsec("MajorAxis") if gaussian else 0.0,
                emin=arcsec("MinorAxis") if gaussian else 0.0,
                pa=math.radians(float(row.get("Orientation") or 0.0))
                if gaussian
                else 0.0,
                extra=extra,
                log_si=row.get("LogarithmicSI", "true").strip().lower() == "true",
            )
        )
    return sources


def load_wsclean(path):
    return loads_wsclean(Path(path).read_text())


# -- BBS (read) -------------------------------------------------------------------


def _bbs_angle(text, hours):
    """A BBS angle: `hh:mm:ss.s` (hours for RA, degrees for Dec) or
    `dd.mm.ss.s` (degrees), or a plain number of degrees."""
    t = text.strip()
    sign = -1.0 if t.startswith("-") else 1.0
    body = t.lstrip("+-")
    if ":" in body:
        a, b, c = body.split(":")
        scale = 15.0 if hours else 1.0
    elif body.count(".") >= 2:
        a, b, c = body.split(".", 2)
        scale = 1.0
    else:
        return sign * math.radians(float(body))
    return sign * math.radians(scale * (float(a) + float(b) / 60.0 + float(c) / 3600.0))


def loads_bbs(text):
    """A BBS sky model (`makesourcedb` format, as DP3 and LSMTool read it):
    a `format` line (`# (Name, Type, ...) = format` or `FORMAT = ...`),
    comma-separated rows, patch rows (no name) skipped; MajorAxis and
    MinorAxis in arcsec (FWHM), Orientation in degrees, SpectralIndex a
    list, LogarithmicSI default true."""
    names = defaults = None
    sources = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if names is None:
            m = re.match(r"#?\s*\((.+)\)\s*=\s*format", line, re.IGNORECASE)
            if m:
                names, defaults = _header_fields(m.group(1))
                continue
            m = re.match(r"format\s*=\s*(.+)$", line, re.IGNORECASE)
            if m:
                names, defaults = _header_fields(m.group(1))
                continue
            if line.startswith("#"):
                continue
            raise ValueError("BBS sky model lacks a format line")
        if line.startswith("#"):
            continue
        parts = [p.strip() for p in _COMMA.split(line)]
        row = {
            n: (v if v else (d or ""))
            for n, v, d in zip(names, parts + [""] * len(names), defaults)
        }
        if not row.get("Name"):
            continue
        kind = row.get("Type", "POINT").upper()
        spi_text = row.get("SpectralIndex", "").strip("[] ")
        spi = tuple(float(c) for c in spi_text.split(",")) if spi_text else ()
        numbered = sorted(
            (int(k.split(":", 1)[1]), v)
            for k, v in row.items()
            if k.startswith("SpectralIndex:")
        )
        if numbered and not spi:
            terms = []
            for _, v in numbered:
                v = v.strip("[] ")
                terms += [float(c) for c in v.split(",")] if v else []
            spi = tuple(terms)
        while spi and spi[-1] == 0.0:
            spi = spi[:-1]
        gaussian = kind == "GAUSSIAN"

        def num(key, row=row):
            return float(row.get(key) or 0.0)

        patch = row.get("Patch", "")
        sources.append(
            Source(
                name=f"{patch}:{row['Name']}" if patch else row["Name"],
                ra=_bbs_angle(row["Ra"], hours=True),
                dec=_bbs_angle(row["Dec"], hours=False),
                i=num("I"),
                q=num("Q"),
                u=num("U"),
                v=num("V"),
                freq0=num("ReferenceFrequency") or None,
                spi=spi,
                emaj=math.radians(num("MajorAxis") / 3600.0) if gaussian else 0.0,
                emin=math.radians(num("MinorAxis") / 3600.0) if gaussian else 0.0,
                pa=math.radians(num("Orientation")) if gaussian else 0.0,
                extra={"Patch": patch} if patch else {},
                log_si=row.get("LogarithmicSI", "true").lower() != "false",
            )
        )
    return sources


def load_bbs(path):
    return loads_bbs(Path(path).read_text())


# -- DDFacet DicoModel (read only) and ClusterCat ------------------------------------

DICOMODEL_GLOBALS = {
    ("numpy._core.multiarray", "_reconstruct"),
    ("numpy._core.multiarray", "scalar"),
    ("numpy.core.multiarray", "_reconstruct"),
    ("numpy.core.multiarray", "scalar"),
    ("numpy", "ndarray"),
    ("numpy", "dtype"),
    ("collections", "OrderedDict"),
}


class RestrictedUnpickler(pickle.Unpickler):
    """Unpickles only NumPy arrays, scalars, dtypes and OrderedDicts (with
    the builtin containers and atoms). Still not safe for untrusted files:
    NumPy's reconstructors are trusted here; use it only on files your own
    tools wrote."""

    allowed = DICOMODEL_GLOBALS

    def find_class(self, module, name):
        if (module, name) not in self.allowed:
            raise pickle.UnpicklingError(f"global {module}.{name} is not allowed")
        return super().find_class(module, name)


def restricted_load(stream):
    return RestrictedUnpickler(stream).load()


def load_dicomodel(path):
    """A DDFacet `DicoModel` (a pickled dict: `Type`, `Comp`, `RefFreq`,
    `ModelShape`, `ListScales`, `GD`, ...). Read only; never on untrusted
    files."""
    with open(path, "rb") as f:
        return restricted_load(f)


def dicomodel_summary(d):
    comp = d.get("Comp", {})
    return {
        "type": d.get("Type"),
        "ref_freq": float(d["RefFreq"]) if "RefFreq" in d else None,
        "model_shape": [int(x) for x in d.get("ModelShape", [])],
        "components": len(comp),
        "keys": sorted(str(k) for k in d),
    }


CLUSTERCAT_DTYPE = np.dtype(
    [
        ("Name", "S200"),
        ("ra", "<f8"),
        ("dec", "<f8"),
        ("SumI", "<f8"),
        ("Cluster", "<i8"),
        ("l", "<f8"),
        ("m", "<f8"),
    ]
)


def read_clustercat(path):
    """A DDFacet/killMS cluster catalogue (`.npy` record array), without
    pickle."""
    return np.load(path, allow_pickle=False)


def write_clustercat(path, records):
    """A cluster catalogue as `np.save` writes it (`records` of
    `CLUSTERCAT_DTYPE`, or anything convertible)."""
    arr = np.asarray(records)
    if arr.dtype.names is None:
        raise ValueError("a cluster catalogue is a record array")
    with open(path, "wb") as f:
        np.lib.format.write_array(f, np.ascontiguousarray(arr), allow_pickle=False)


def clustercat_from_sources(sources, phase_centre, cluster=None):
    ra0, dec0 = phase_centre
    l, m = direction_cosines(
        [s.ra for s in sources], [s.dec for s in sources], ra0, dec0
    )
    out = np.zeros(len(sources), CLUSTERCAT_DTYPE)
    out["Name"] = [s.name.encode() for s in sources]
    out["ra"] = [s.ra for s in sources]
    out["dec"] = [s.dec for s in sources]
    out["SumI"] = [s.i for s in sources]
    out["Cluster"] = np.arange(len(sources)) if cluster is None else cluster
    out["l"], out["m"] = l, m
    return out


# -- dispatch ----------------------------------------------------------------------

READERS = {
    ".lsm.html": lambda p: load_html(p).sources,
    ".html": lambda p: load_html(p).sources,
    ".skymodel": load_bbs,
    ".bbs": load_bbs,
    ".wsclean": load_wsclean,
}


def kind_of(path):
    name = str(path).lower()
    if name.endswith((".lsm.html", ".html")):
        return "tigger-html"
    if name.endswith((".skymodel", ".bbs", ".sky")):
        return "bbs"
    if name.endswith(".wsclean"):
        return "wsclean"
    if name.endswith((".lsm", ".lsm.txt")):
        return "tigger-ascii"
    if name.endswith(".txt"):
        head = (
            Path(path).read_text().lstrip()[:80].lower() if Path(path).exists() else ""
        )
        return "wsclean" if head.startswith("format") else "tigger-ascii"
    raise ValueError(f"unknown sky-model format for {path}")


def load_any(path):
    kind = kind_of(path)
    if kind == "tigger-html":
        return load_html(path).sources
    if kind == "bbs":
        return load_bbs(path)
    if kind == "wsclean":
        return load_wsclean(path)
    return load(path)


def save_any(sources, path, kind=None):
    kind = kind or kind_of(path)
    if kind == "tigger-html":
        freq0 = next((s.freq0 for s in sources if s.freq0), None)
        text = dumps_html(sources, freq0=freq0)
    elif kind == "tigger-ascii":
        text = dumps_ascii(sources)
    elif kind == "wsclean":
        text = dumps_wsclean(sources)
    else:
        raise ValueError(f"{kind} is read only")
    Path(path).write_text(text)
    return Path(path)


__all__ = [
    "CLUSTERCAT_DTYPE",
    "DEFAULT_FORMAT",
    "WSCLEAN_FORMAT",
    "Model",
    "RestrictedUnpickler",
    "Source",
    "clustercat_from_sources",
    "components",
    "dicomodel_summary",
    "direction_cosines",
    "dumps_ascii",
    "dumps_html",
    "dumps_wsclean",
    "kind_of",
    "load",
    "load_any",
    "load_bbs",
    "load_dicomodel",
    "load_html",
    "load_wsclean",
    "loads",
    "loads_bbs",
    "loads_html",
    "loads_wsclean",
    "parse_format",
    "parse_line",
    "read_clustercat",
    "restricted_load",
    "save_any",
    "summary",
    "write_clustercat",
]
