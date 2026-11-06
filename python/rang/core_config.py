"""The configuration of `rang-core flag | calibrate | apply | image | selfcal |
run` (task W2, research/w2-commands.md).

One YAML file, schema `rang-config`, version 1. Every key has a default,
written here once (`SCHEMA`) and printed, with its comment, by
`rang-core config defaults`. `validate` reports every problem at once, in
two classes:

- **schema errors**: an unknown key, a wrong type, a value outside its
  choices, a missing required key or a wrong version;
- **not yet implemented**: a value the schema can express, such as the
  self-calibration terms of research/c1-calibration-chain.md, that rang
  cannot run yet. Each refusal names the finish-plan task that will add it.

Since task C2e (research/c2e-calibrate.md) calibrate runs CARACal's K, G,
B, A and F terms in C1's order through `rang.cal_chain.run`, and apply
applies their CASA tables through `rang.applycal`. Since task C6w
(research/c6w-polwire.md) the polcal section's Gpol, KCROSS, Xf and Df
(CARACal's strategy 1, `rang.cal_pol`) run there too, and apply corrects
by the parallactic angle (`apply.parang`).

Refusals are computed only for the stages that will run, so a configuration
of the whole C1 chain parses today and states what is missing.
"""

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

SCHEMA_NAME = "rang-config"
VERSION = 1
STAGES = ("flag", "calibrate", "apply", "image", "selfcal")
ROLES = ("fcal", "bpcal", "gcal", "xcal", "target")

# The finish-plan task that adds each not-yet-implemented feature
# (research/finish-plan.md; C1's steps in research/c1-calibration-chain.md, 6).
TASKS = {
    "C5a": "phase and amplitude self-calibration (Sp, Sa)",
    "C5b": "delay self-calibration (Sd, CARACal's Fslope)",
    "C7a": "polarised calibrator models (polindex, polangle, rotmeas; Q, U, V)",
    "G4": "masks, tapers and an imaging uv range",
    "G5": "multiscale CLEAN",
    "G6": "MODEL_DATA from the imager",
    "G9": "Stokes Q, U and V and joined polarisations",
    "W4": "uniform imaging weights: WEIGHT_SPECTRUM = 1 written into the MS, or a "
    "gemclean option that ignores the MS weights (an owner decision, "
    "research/w4-unsupported.md)",
}

TERM_TYPES = (
    "complex",
    "K",
    "G",
    "B",
    "A",
    "F",
    "Gpol",
    "KCROSS",
    "Xf",
    "Df",
    "Sd",
    "Sp",
    "Sa",
)
# CASA-style terms run by calibrate since task C2e (`rang.cal_chain.run`).
CASA_TERMS = ("K", "G", "B", "A", "F")
# The polarisation terms of the polcal section, since task C6w (`rang.cal_pol`
# through `rang.cal_chain.run`; CARACal's strategy 1).
POL_TERMS = ("Gpol", "KCROSS", "Xf", "Df")
CHAIN_TERMS = CASA_TERMS + POL_TERMS
TERM_TASKS = {
    "Sd": "C5b",
    "Sp": "C5a",
    "Sa": "C5a",
}
SELFCAL_TYPES = ("Sd", "Sp", "Sa", "complex")
CALIBRATE_SECTIONS = ("primary", "secondary", "polcal")


class ConfigError(ValueError):
    """A configuration that cannot run: every schema error and refusal."""

    def __init__(self, errors, refusals=(), source=None):
        self.errors = list(errors)
        self.refusals = list(refusals)
        self.source = source
        super().__init__(self.report())

    def report(self):
        where = f"{self.source}: " if self.source else ""
        lines = []
        if self.errors:
            lines.append(f"{where}{len(self.errors)} configuration error(s):")
            lines += [f"  {path}: {text}" for path, text in self.errors]
        if self.refusals:
            lines.append(f"{where}not implemented yet ({len(self.refusals)}):")
            lines += [
                f"  {r.path}: {r.text} (task {r.task}: {TASKS[r.task]})"
                for r in self.refusals
            ]
        return "\n".join(lines)


@dataclass(frozen=True)
class Refusal:
    path: str
    task: str
    text: str


@dataclass(frozen=True)
class Key:
    """One configuration key: its default, kind and comment."""

    default: object
    kind: str
    doc: str
    choices: tuple = ()
    required: bool = False


def _k(default, kind, doc, choices=(), required=False):
    return Key(default, kind, doc, tuple(choices), required)


FIELD_DOC = "FIELD names or ids"
# The schema, section by section, in the order `defaults` prints it.
SCHEMA = {
    "schema": _k(SCHEMA_NAME, "const", "always rang-config"),
    "version": _k(
        VERSION,
        "version",
        "required: the schema version; this rang-core reads 1",
        required=True,
    ),
    "fields": {
        "fcal": _k([], "fields", f"flux calibrators: {FIELD_DOC}"),
        "bpcal": _k(
            [], "fields", f"bandpass calibrators (empty: the fcal fields): {FIELD_DOC}"
        ),
        "gcal": _k([], "fields", f"gain (secondary) calibrators: {FIELD_DOC}"),
        "xcal": _k([], "fields", f"polarisation-angle calibrators: {FIELD_DOC}"),
        "target": _k([], "fields", f"targets: {FIELD_DOC}"),
    },
    "data": {
        "weights": _k(
            "as_is",
            "choice",
            "as_is: WEIGHT_SPECTRUM, else WEIGHT per channel; uniform: 1 (CARACal's "
            "prep.specweights), used in memory by calibrate",
            ("as_is", "uniform"),
        ),
        "scans": _k([], "ints", "SCAN_NUMBERs to use (empty: every scan)"),
        "memory_limit_gb": _k(
            8.0,
            "float",
            "peak resident memory a stage may use, GiB; flag, calibrate and apply "
            "chunk by time and row to stay within it (research/w3-chunking.md)",
        ),
        "chunk_rows": _k(
            None,
            "int?",
            "a cap on the rows of every chunk (null: what memory_limit_gb allows); "
            "a solve chunk still holds one solution interval",
        ),
    },
    "flag": {
        "flagger": _k(
            "tricolour",
            "choice",
            "the Tricolour 0.2.1 port (research/core-d-tricolour.md)",
            ("tricolour",),
        ),
        "strategy": _k(
            None,
            "path",
            "required: a Tricolour strategy YAML, such as CARACal's "
            "mk_rfi_flagging_calibrator_fields_firstpass.yaml (relative to this file)",
        ),
        "fields": _k(["all"], "fields", f"fields to flag: all, roles or {FIELD_DOC}"),
        "column": _k("DATA", "column", "the visibilities flagged"),
        "static_masks": _k(
            "tricolour",
            "choice",
            "tricolour: the two masks shipped with Tricolour 0.2.1; none",
            ("tricolour", "none"),
        ),
        "write": _k(
            "replace",
            "choice",
            "replace: FLAG becomes the strategy's flags, as Tricolour writes them; "
            "or: OR with the flags already there",
            ("replace", "or"),
        ),
    },
    "calibrate": {
        "model": {
            "source": _k(
                "unity",
                "choice",
                "unity: a 1 Jy point at the phase centre; column: an existing column; "
                "setjy, manual, lsm: written to MODEL_DATA on the primary fields "
                "(rang.calmodels), then solved against",
                ("unity", "column", "setjy", "manual", "lsm"),
            ),
            "column": _k("MODEL_DATA", "column", "the model column for source: column"),
            "standard": _k(
                None, "str?", "setjy flux standard, such as Stevens-Reynolds 2016"
            ),
            "flux_jy": _k(
                None, "floats?", "manual: Stokes I, Q, U, V in Jy at reffreq_hz"
            ),
            "spix": _k(None, "floats?", "manual: spectral index coefficients (log10)"),
            "reffreq_hz": _k(None, "float?", "manual: the reference frequency"),
            "polindex": _k(None, "floats?", "manual: fractional polarisation"),
            "polangle": _k(None, "floats?", "manual: polarisation angle, radians"),
            "rotmeas": _k(None, "float?", "manual: rotation measure, rad m^-2"),
            "lsm": _k(
                None, "path?", "a Tigger .lsm sky model, such as pks1934-638.lsm"
            ),
        },
        "refant": _k(
            None, "refant", "reference antenna: a name, an id, a list or auto"
        ),
        "refantmode": _k(
            "flex", "choice", "flex or strict, as CASA", ("flex", "strict")
        ),
        "uvrange": _k(
            "", "str", "baselines used by G, B, F and polcal solves, such as >150"
        ),
        "minsnr": _k(None, "float?", "solutions below this SNR are flagged (CASA: 3)"),
        "minblperant": _k(None, "int?", "baselines per antenna needed (CASA: 4)"),
        "primary": {
            "field": _k(["fcal"], "fields", "fields of the primary solves"),
            "terms": _k([{"type": "complex"}], "terms", "terms solved in order"),
        },
        "secondary": {
            "field": _k(["gcal"], "fields", "fields of the secondary solves"),
            "terms": _k([], "terms", "terms solved in order, such as G, A, F"),
        },
        "polcal": {
            "field": _k(["xcal"], "fields", "fields of the polarisation solves"),
            "terms": _k([], "terms", "Gpol, KCROSS, Xf on xcal; Df with field: fcal"),
            "model": {
                "source": _k(
                    "nrao",
                    "choice",
                    "the model Gpol, KCROSS and Xf solve against: nrao, CARACal's "
                    "nrao_xcal.yml (3C286, 3C138; rang.calmodels.NRAO_XCAL) written "
                    "to MODEL_DATA on their fields; column: an existing column",
                    ("nrao", "column"),
                ),
                "name": _k(
                    None,
                    "str?",
                    "nrao: 3C286, 3C138 or an alias such as J1331+3030 (null: the "
                    "field's name)",
                ),
                "column": _k("MODEL_DATA", "column", "the model column for column"),
            },
            "frame": _k(
                "casa",
                "choice",
                "the parallactic-angle frame (rang.cal_pol; C6's provisional owner "
                "decision 1): casa, CASA's parang=True; rang, geodetic and ICRS north",
                ("casa", "rang"),
            ),
            "feed_angle_rotation": _k(
                None,
                "float?",
                "degrees: the RECEPTOR_ANGLE of both receptors of every antenna used "
                "for P, in memory (CARACal writes it into FEED; MeerKAT: -90); null: "
                "FEED's",
            ),
            "extendflags": _k(
                False, "bool", "flagdata mode=extend on xcal and fcal first"
            ),
        },
    },
    "apply": {
        "column": _k("CORRECTED_DATA", "column", "the column written"),
        "applymode": _k(
            "calflag", "choice", "as CASA applycal", ("calflag", "calflagstrict")
        ),
        "calwt": _k(
            False,
            "bool",
            "scale the weights by the gains (CASA: G, T and B only; no effect on "
            "complex)",
        ),
        "parang": _k(
            False,
            "bool",
            "correct by the parallactic angle after the tables, in "
            "calibrate.polcal.frame (needed when Gpol, KCROSS, Xf or Df are applied)",
        ),
        "targets": _k(
            [],
            "targets",
            "what is applied to which fields (empty: every complex term to the "
            "fields it was solved on)",
        ),
    },
    "image": {
        "imager": _k("gemclean", "choice", "the imager", ("gemclean",)),
        "gemclean": _k(
            "auto",
            "str",
            "the gemclean binary; auto: gemclean on PATH, then core/target/"
            "{release,gemclean}/gemclean of the checkout",
        ),
        "fields": _k(["target"], "fields", "one image per field"),
        "column": _k(
            "auto",
            "column",
            "auto: CORRECTED_DATA once this run's apply has finished, else DATA",
        ),
        "name": _k("image", "str", "the file prefix in <run>/image/<field>/"),
        "size": _k(None, "size", "required: width and height in pixels, even"),
        "scale": _k(None, "str", "required: pixel size, such as 2asec"),
        "weight": _k(
            "briggs",
            "choice",
            "natural, uniform or briggs",
            ("natural", "uniform", "briggs"),
        ),
        "robust": _k(0.0, "float", "Briggs robustness"),
        "niter": _k(100000, "int", "maximum number of components"),
        "auto_threshold": _k(
            3.0, "float?", "stop at this many robust sigma of the residual"
        ),
        "threshold": _k(None, "float?", "stop at this many Jy"),
        "gain": _k(None, "float?", "loop gain (null: gemclean's 0.1)"),
        "mgain": _k(
            None, "float?", "major-cycle gain (null: gemclean's measured rule)"
        ),
        "nmiter": _k(None, "int?", "maximum major cycles (null: gemclean's 20)"),
        "threads": _k(
            None, "int?", "worker threads (null: gemclean's default, all cores)"
        ),
        "wgridder_accuracy": _k(1e-6, "float", "gridder accuracy"),
        "extra_args": _k([], "strs", "more gemclean options, passed as given"),
        "channels_out": _k(1, "int", "output channels"),
        "join_channels": _k(False, "bool", "join the output channels"),
        "fit_spectral_pol": _k(
            None, "int?", "terms of the polynomial fit across joined channels"
        ),
        "average_channels": _k(
            1, "int", "adjacent channels averaged before imaging (rang's own)"
        ),
        "auto_mask": _k(None, "float?", "automatic mask at this many sigma"),
        "fits_mask": _k(None, "path?", "a FITS mask"),
        "taper_gaussian": _k(None, "str?", "a Gaussian taper, such as 10asec"),
        "uvrange": _k("", "str", "baselines imaged"),
        "multiscale": _k(False, "bool", "multiscale CLEAN"),
        "pol": _k("I", "str", "polarisations, such as I or IQUV"),
        "join_polarizations": _k(False, "bool", "join the polarisations"),
        "write_model": _k(False, "bool", "predict the model into MODEL_DATA"),
    },
    "selfcal": {
        "rounds": _k(2, "int", "calibration rounds (CARACal's cal_niter)"),
        "terms": _k(
            [{"type": "Sp"}, {"type": "Sa"}],
            "terms",
            "phase then amplitude (owner decision 1 of C1); Sd is CARACal's Fslope",
        ),
        "input_column": _k("CORRECTED_1GC", "column", "the 1GC-corrected data solved"),
        "model_column": _k("MODEL_DATA", "column", "the model solved against"),
        "output_column": _k("CORRECTED_DATA", "column", "the column written"),
        "gain_clip": _k([0.5, 2.0], "floats", "gain amplitudes kept"),
        "minuvw_m": _k(0.0, "float", "baselines shorter than this are not used"),
    },
    "run": {
        "stages": _k(
            ["flag", "calibrate", "image"],
            "stages",
            "stages of rang-core run, executed in the order flag, calibrate, apply, "
            "image, selfcal",
        ),
    },
}

# Keys of a calibration term (each refers to research/c1-calibration-chain.md,
# 1.3). `None` means the term type's own default.
TERM_KEYS = {
    "type": _k(None, "choice", "the term", TERM_TYPES, required=True),
    "name": _k(None, "str?", "the table name (default: the type)"),
    "field": _k(None, "fields?", "fields solved (default: the section's)"),
    "solint": _k("inf", "solint", "inf, int, N integrations, or Ns (CASA seconds)"),
    "freqint": _k("inf", "solint", "complex, Sp, Sa: inf or N channels per solution"),
    "combine": _k("", "str", "CASA combine, such as scan"),
    "calmode": _k(None, "choice?", "ap, p or a", ("ap", "p", "a")),
    "refant": _k(None, "refant", "overrides calibrate.refant"),
    "refantmode": _k(None, "choice?", "flex or strict", ("flex", "strict")),
    "uvrange": _k(None, "str?", "overrides calibrate.uvrange"),
    "minsnr": _k(None, "float?", "overrides calibrate.minsnr"),
    "minblperant": _k(None, "int?", "overrides calibrate.minblperant"),
    "preapply": _k([], "strs", "terms applied while solving, by name"),
    "interp": _k([], "strs", "per pre-applied term: linear or nearest"),
    "gainfield": _k([], "strs", "per pre-applied term: a field, nearest or empty"),
    "fillgaps": _k(None, "int?", "B: channels bridged (CARACal: 70)"),
    "solnorm": _k(None, "bool?", "B: normalise"),
    "smodel": _k(None, "floats?", "F: a point model, such as [1, 0, 0, 0]"),
    "parang": _k(
        None, "bool?", "apply the parallactic angle while solving (default true)"
    ),
    "preavg": _k(None, "float?", "Xf, Df: pre-averaging in seconds (not ported)"),
    "clip": _k(
        None,
        "floats?",
        "Df: amplitude range kept, [-a, a] (default CARACal's [-0.6, 0.6]; [] for "
        "none)",
    ),
    "estimator": _k(
        None,
        "choice?",
        "KCROSS: casa (CASA's FFT and parabola, the default) or refined (then "
        "Newton steps, which remove the parabola's bias)",
        ("casa", "refined"),
    ),
    "min_data_fraction": _k(
        None,
        "float?",
        "Df: flag channels whose unflagged cross-hand fraction is below this "
        "(rang's rule, CASA has none; default off)",
    ),
    "strategy": _k(None, "path?", "A: a Tricolour strategy for the corrected data"),
    "max_iterations": _k(50, "int", "complex, Sp, Sa: solver iterations"),
    "stop_criterion": _k(1e-7, "float", "complex, Sp, Sa: convergence criterion"),
    "stop_fraction": _k(0.99, "float", "complex, Sp, Sa: fraction converged to stop"),
}
_CASA = {
    "type",
    "name",
    "field",
    "solint",
    "combine",
    "refant",
    "refantmode",
    "uvrange",
    "minsnr",
    "minblperant",
    "preapply",
    "interp",
    "gainfield",
}
_SOLVER = {"freqint", "max_iterations", "stop_criterion", "stop_fraction"}
ALLOWED_TERM_KEYS = {
    "complex": _CASA | _SOLVER,
    "K": _CASA,
    "G": _CASA | {"calmode"},
    "B": _CASA | {"fillgaps", "solnorm"},
    "A": {"type", "name", "field", "strategy"},
    "F": _CASA | {"calmode", "smodel"},
    "Gpol": _CASA | {"calmode", "parang"},
    "KCROSS": _CASA | {"parang", "estimator"},
    "Xf": _CASA | {"parang", "preavg"},
    "Df": _CASA | {"parang", "preavg", "clip", "min_data_fraction"},
    "Sd": {
        "type",
        "name",
        "solint",
        "max_iterations",
        "stop_criterion",
        "stop_fraction",
    },
    "Sp": {"type", "name", "solint"} | _SOLVER,
    "Sa": {"type", "name", "solint"} | _SOLVER,
}
TARGET_KEYS = {
    "field": _k(None, "fields", "fields corrected", required=True),
    "tables": _k(None, "strs", "terms applied, by name, in order", required=True),
    "gainfield": _k([], "strs", "per table: a field, nearest or empty"),
    "interp": _k([], "strs", "per table: linear or nearest"),
}

# The configuration sections each stage depends on: a finished stage is
# skipped only while the hash of these is unchanged.
STAGE_SECTIONS = {
    "flag": ("fields", "data", "flag"),
    "calibrate": ("fields", "data", "calibrate"),
    "apply": ("fields", "data", "calibrate", "apply"),
    "image": ("fields", "data", "image"),
    "selfcal": ("fields", "data", "image", "selfcal"),
}


# -- reading -------------------------------------------------------------------


def _yaml():
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - a dependency of rang-core
        raise ConfigError([("", "PyYAML is needed to read a configuration")]) from exc
    return yaml


def load(path):
    """The YAML of `path` as a mapping (schema errors raise ConfigError)."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError([("", f"cannot read {path}: {exc}")], source=path) from exc
    return loads(text, source=path)


def loads(text, source=None):
    yaml = _yaml()
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError([("", f"not valid YAML: {exc}")], source=source) from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError([("", "the configuration must be a mapping")], source=source)
    return raw


# -- schema --------------------------------------------------------------------

_SECONDS = re.compile(r"^\d+(\.\d*)?s$")


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v):
    return (isinstance(v, (int, float))) and not isinstance(v, bool)


# PyYAML reads 1e-7 (no dot) as a string; such a string is taken as the number.
_FLOAT_TEXT = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)[eE][-+]?\d+$")


def _number(v):
    if isinstance(v, str) and _FLOAT_TEXT.match(v.strip()):
        return float(v)
    return v


def _check(path, key, value, errors):
    """Check one value against its Key; returns the value to keep."""
    kind = key.kind
    optional = kind.endswith("?")
    base = kind.rstrip("?")
    if base in ("float", "floats"):
        value = (
            [_number(v) for v in value] if isinstance(value, list) else _number(value)
        )
    if value is None:
        if optional or key.default is None:
            return None
        errors.append((path, "must not be null"))
        return value

    def bad(what):
        errors.append((path, f"must be {what}, not {value!r}"))
        return value

    if base == "const":
        return value if value == key.default else bad(repr(key.default))
    if base == "version":
        if value != VERSION:
            errors.append(
                (path, f"version {value!r}: this rang-core reads version {VERSION}")
            )
        return value
    if base in ("str", "column", "path"):
        if not isinstance(value, str):
            return bad("a string")
        auto = key.default == "auto" and value == "auto"
        if (
            base == "column"
            and not auto
            and not re.fullmatch(r"[A-Z][A-Z0-9_]*", value)
        ):
            return bad("a column name in capitals, such as DATA")
        return value
    if base == "int":
        return value if _is_int(value) else bad("an integer")
    if base == "float":
        return float(value) if _is_num(value) else bad("a number")
    if base == "bool":
        return value if isinstance(value, bool) else bad("true or false")
    if base == "choice":
        return value if value in key.choices else bad(f"one of {list(key.choices)}")
    if base in ("ints", "strs", "floats"):
        test = {
            "ints": _is_int,
            "strs": lambda v: isinstance(v, str),
            "floats": _is_num,
        }
        if isinstance(value, list) and all(test[base](v) for v in value):
            return [float(v) for v in value] if base == "floats" else list(value)
        return bad(
            {
                "ints": "a list of integers",
                "strs": "a list of strings",
                "floats": "a list of numbers",
            }[base]
        )
    if base == "fields":
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            value = [value]
        if isinstance(value, list) and all(
            isinstance(v, str) or _is_int(v) for v in value
        ):
            return list(value)
        return bad("a field name or id, or a list of them")
    if base == "refant":
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return [value]
        if (
            isinstance(value, list)
            and value
            and all(isinstance(v, str) or _is_int(v) for v in value)
        ):
            return list(value)
        return bad("an antenna name or id, a list of them, or auto")
    if base == "size":
        if (
            isinstance(value, list)
            and len(value) == 2
            and all(_is_int(v) and v > 0 and v % 2 == 0 for v in value)
        ):
            return list(value)
        if _is_int(value) and value > 0 and value % 2 == 0:
            return [value, value]
        return bad("an even pixel count or [width, height]")
    if base == "solint":
        if value in ("inf", "int") or (
            isinstance(value, str) and _SECONDS.match(value)
        ):
            return value
        if _is_int(value) and value > 0:
            return value
        return bad("inf, int, a positive integer or seconds such as 60s")
    if base == "stages":
        if isinstance(value, list) and all(v in STAGES for v in value):
            if len(set(value)) != len(value):
                errors.append((path, "a stage is listed twice"))
            return list(value)
        return bad(f"a list of stages from {list(STAGES)}")
    if base == "terms":
        return _terms(path, value, errors)
    if base == "targets":
        return _targets(path, value, errors)
    raise AssertionError(f"unknown kind {kind}")


def _section(path, spec, raw, errors):
    """Merge `raw` over the defaults of `spec`, checking every key."""
    out = {}
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        errors.append((path or "(top)", "must be a mapping"))
        raw = {}
    for name in raw:
        if name not in spec:
            known = ", ".join(spec)
            errors.append((_join(path, name), f"unknown key (known: {known})"))
    for name, item in spec.items():
        where = _join(path, name)
        if isinstance(item, dict):
            out[name] = _section(where, item, raw.get(name), errors)
            continue
        if name in raw:
            out[name] = _check(where, item, raw[name], errors)
        else:
            if item.required:
                errors.append((where, f"required (default {item.default!r})"))
            out[name] = copy.deepcopy(item.default)
            if item.kind in ("terms", "targets"):
                out[name] = _check(where, item, out[name], errors)
    return out


def _join(path, name):
    return f"{path}.{name}" if path else str(name)


def _terms(path, value, errors):
    if not isinstance(value, list):
        errors.append((path, "must be a list of terms, such as [{type: complex}]"))
        return []
    out = []
    for i, raw in enumerate(value):
        where = f"{path}[{i}]"
        if isinstance(raw, str):
            raw = {"type": raw}
        if not isinstance(raw, dict):
            errors.append((where, "a term is a mapping with a type"))
            continue
        kind = raw.get("type")
        if kind not in TERM_TYPES:
            errors.append(
                (f"{where}.type", f"must be one of {list(TERM_TYPES)}, not {kind!r}")
            )
            continue
        allowed = ALLOWED_TERM_KEYS[kind]
        term = {}
        for name in raw:
            if name not in TERM_KEYS:
                errors.append((f"{where}.{name}", "unknown term key"))
            elif name not in allowed:
                errors.append((f"{where}.{name}", f"not a key of a {kind} term"))
        for name in sorted(allowed, key=list(TERM_KEYS).index):
            key = TERM_KEYS[name]
            if name in raw:
                term[name] = _check(f"{where}.{name}", key, raw[name], errors)
            else:
                term[name] = copy.deepcopy(key.default)
        if term.get("name") is None:
            term["name"] = kind
        for name in ("interp", "gainfield"):
            if name in term and term[name] and len(term[name]) != len(term["preapply"]):
                errors.append((f"{where}.{name}", "needs one entry per preapply entry"))
        out.append(term)
    return out


def _targets(path, value, errors):
    if not isinstance(value, list):
        errors.append((path, "must be a list of {field, tables} mappings"))
        return []
    out = []
    for i, raw in enumerate(value):
        where = f"{path}[{i}]"
        if not isinstance(raw, dict):
            errors.append((where, "an apply target is a mapping"))
            continue
        for name in raw:
            if name not in TARGET_KEYS:
                errors.append((f"{where}.{name}", "unknown key"))
        target = {}
        for name, key in TARGET_KEYS.items():
            if name in raw:
                target[name] = _check(f"{where}.{name}", key, raw[name], errors)
            elif key.required:
                errors.append((f"{where}.{name}", "required"))
                target[name] = []
            else:
                target[name] = copy.deepcopy(key.default)
        out.append(target)
    return out


def resolve(raw):
    """(config with every default filled in, [schema errors])."""
    errors = []
    config = _section("", SCHEMA, raw, errors)
    data = config["data"]
    if _is_num(data["memory_limit_gb"]) and not data["memory_limit_gb"] > 0:
        errors.append(("data.memory_limit_gb", "must be above 0"))
    if _is_int(data["chunk_rows"]) and data["chunk_rows"] < 1:
        errors.append(("data.chunk_rows", "must be at least 1"))
    names = {}
    for section in CALIBRATE_SECTIONS:
        for i, term in enumerate(config["calibrate"][section]["terms"]):
            where = f"calibrate.{section}.terms[{i}]"
            if term["type"] in ("Sd", "Sp", "Sa"):
                errors.append(
                    (f"{where}.type", "self-calibration terms belong in selfcal")
                )
            if term["name"] in names:
                errors.append(
                    (f"{where}.name", f"{term['name']!r} is also {names[term['name']]}")
                )
            names[term["name"]] = where
    for i, term in enumerate(config["selfcal"]["terms"]):
        if term["type"] not in SELFCAL_TYPES:
            errors.append(
                (f"selfcal.terms[{i}].type", f"must be one of {list(SELFCAL_TYPES)}")
            )
    for section in CALIBRATE_SECTIONS:
        for i, term in enumerate(config["calibrate"][section]["terms"]):
            for j, name in enumerate(term.get("preapply", [])):
                if name not in names:
                    errors.append(
                        (
                            f"calibrate.{section}.terms[{i}].preapply[{j}]",
                            f"no term named {name!r}",
                        )
                    )
    for i, target in enumerate(config["apply"]["targets"]):
        for j, name in enumerate(target.get("tables") or []):
            if name not in names:
                errors.append(
                    (f"apply.targets[{i}].tables[{j}]", f"no term named {name!r}")
                )
    return config, errors


# -- what is not implemented yet --------------------------------------------------


def refusals(config, stages):
    """[Refusal] for every value the given stages cannot run yet."""
    out = []

    def no(path, task, text):
        out.append(Refusal(path, task, text))

    stages = set(stages)
    if "flag" in stages and config["flag"]["strategy"] is None:
        out.append(Refusal("flag.strategy", "", "required"))
    if "calibrate" in stages:
        cal = config["calibrate"]
        model = cal["model"]
        _model_refusals(model, cal, no, out)
        _chain_refusals(config, out)
        name = cal["polcal"]["model"]["name"]
        if cal["polcal"]["model"]["source"] == "nrao" and name is not None:
            from . import calmodels

            if name not in calmodels.NRAO_XCAL and name not in (
                calmodels.NRAO_XCAL_ALIASES
            ):
                out.append(
                    Refusal(
                        "calibrate.polcal.model.name",
                        "",
                        f"no NRAO model for {name!r}; have "
                        f"{sorted(calmodels.NRAO_XCAL)} and "
                        f"{sorted(calmodels.NRAO_XCAL_ALIASES)}",
                    )
                )
        any_term = False
        for section in CALIBRATE_SECTIONS:
            block = cal[section]
            if section == "polcal" and block["extendflags"]:
                out.append(
                    Refusal(
                        "calibrate.polcal.extendflags",
                        "",
                        "CASA's flagdata mode=extend (CARACal's growtime and growfreq "
                        "80) is not ported and no task owns it (an owner decision, "
                        "research/c6w-polwire.md); set false",
                    )
                )
            for i, term in enumerate(block["terms"]):
                any_term = True
                _term_refusals(f"calibrate.{section}.terms[{i}]", term, cal, no)
        if not any_term:
            out.append(Refusal("calibrate", "", "no term to solve"))
    if "apply" in stages:
        types = {
            term["name"]: term["type"]
            for section in CALIBRATE_SECTIONS
            for term in config["calibrate"][section]["terms"]
        }
        casa = [k for k in types.values() if k in CHAIN_TERMS and k != "A"]
        if casa and not config["apply"]["targets"]:
            out.append(
                Refusal(
                    "apply.targets",
                    "",
                    "required when calibrate solves K, G, B, F or polarisation terms "
                    "(which tables go to which fields, as CARACal's callib)",
                )
            )
        if config["apply"]["parang"] and not config["apply"]["targets"]:
            out.append(
                Refusal(
                    "apply.parang",
                    "",
                    "needs apply.targets: P is applied with the CASA tables of each "
                    "target (rang.applycal)",
                )
            )
        for i, target in enumerate(config["apply"]["targets"]):
            where = f"apply.targets[{i}]"
            kinds = [types.get(name) for name in target["tables"] or []]
            if "complex" in kinds and any(k in CHAIN_TERMS for k in kinds):
                out.append(
                    Refusal(
                        f"{where}.tables",
                        "",
                        "complex and CASA tables (K, G, B, F, Gpol, KCROSS, Xf, Df) "
                        "cannot be applied together",
                    )
                )
            if "complex" in kinds and config["apply"]["parang"]:
                out.append(
                    Refusal(
                        f"{where}.tables",
                        "",
                        "apply.parang with a complex table: P is applied with CASA "
                        "tables only (rang.applycal)",
                    )
                )
            if any(k in POL_TERMS for k in kinds) and not config["apply"]["parang"]:
                out.append(
                    Refusal(
                        f"{where}.tables",
                        "",
                        "polarisation tables are solved with the parallactic angle "
                        "and need apply.parang: true (CARACal's applycal "
                        "parang=True)",
                    )
                )
            for j, name in enumerate(target["tables"] or []):
                kind = types.get(name)
                if kind is None:
                    continue  # a schema error, reported by resolve
                if kind == "A":
                    out.append(
                        Refusal(f"{where}.tables[{j}]", "", "an A step writes no table")
                    )
                    continue
                if kind in TERM_TASKS:
                    no(
                        f"{where}.tables[{j}]",
                        TERM_TASKS[kind],
                        f"applying term {kind}",
                    )
                    continue
                if kind != "complex":
                    continue  # K, G, B, F (C2e) and the pol terms (C6w): applycal
                if j < len(target["interp"]) and target["interp"][j]:
                    out.append(
                        Refusal(
                            f"{where}.interp[{j}]",
                            "",
                            "interp on a complex table: it applies on its own "
                            "solution bins; use a G term to interpolate",
                        )
                    )
    if "image" in stages:
        img = config["image"]
        if config["data"]["weights"] == "uniform":
            no(
                "data.weights",
                "W4",
                "uniform weights for imaging: gemclean reads the MS weights, so "
                "WEIGHT_SPECTRUM = 1 would have to be written into the MS",
            )
        for key in ("channels_out", "average_channels"):
            if img[key] < 1:
                out.append(Refusal(f"image.{key}", "", "must be at least 1"))
        if img["fit_spectral_pol"] is not None and (
            img["fit_spectral_pol"] < 1
            or not img["join_channels"]
            or img["channels_out"] < 2
        ):
            out.append(
                Refusal(
                    "image.fit_spectral_pol",
                    "",
                    "needs at least one term, join_channels and channels_out of 2 or more",
                )
            )
        for key, default, task in (
            ("auto_mask", None, "G4"),
            ("fits_mask", None, "G4"),
            ("taper_gaussian", None, "G4"),
            ("uvrange", "", "G4"),
            ("multiscale", False, "G5"),
            ("join_polarizations", False, "G9"),
            ("write_model", False, "G6"),
        ):
            if img[key] != default:
                no(f"image.{key}", task, f"{key}: {img[key]!r}")
        if img["pol"] != "I":
            no("image.pol", "G9", f"pol: {img['pol']!r}")
        for key in ("size", "scale"):
            if img[key] is None:
                out.append(Refusal(f"image.{key}", "", "required"))
    if "selfcal" in stages:
        no("selfcal", "C5a", "self-calibration (it also needs G6's MODEL_DATA)")
        no("selfcal", "G6", "MODEL_DATA written by the imager")
        for i, term in enumerate(config["selfcal"]["terms"]):
            task = TERM_TASKS.get(term["type"], "C5a")
            no(f"selfcal.terms[{i}]", task, f"term {term['type']}")
    return out


MODEL_SOURCES = ("setjy", "manual", "lsm")  # written by rang.calmodels (C3a)


def _model_refusals(model, cal, no, out):
    """What calibrate cannot do yet with `calibrate.model` (task W2b): a
    polarised manual model (I, Q, U, V, polindex, polangle, rotmeas) is
    written as CASA's setjy does (C7a). The model is written on the primary
    fields only; the secondary's K, G and F solve against CASA's unit point
    model (`smodel`) and its flux density comes from fluxscale (task C2e),
    so a complex term on secondary fields with a written model is an
    error."""
    source = model["source"]
    pol_keys = [k for k in ("polindex", "polangle", "rotmeas") if model[k] is not None]
    if source != "manual":
        for key in pol_keys:
            out.append(
                Refusal(f"calibrate.model.{key}", "", "only with source: manual")
            )
    if source not in MODEL_SOURCES:
        return
    if source == "manual":
        flux = model["flux_jy"]
        if not flux:
            out.append(Refusal("calibrate.model.flux_jy", "", "required for manual"))
        elif len(flux) > 4:
            out.append(Refusal("calibrate.model.flux_jy", "", "I or I, Q, U, V"))
        if model["reffreq_hz"] is None:
            out.append(Refusal("calibrate.model.reffreq_hz", "", "required for manual"))
        linear = bool(flux) and any(float(v) != 0 for v in flux[1:3])
        if not linear and (model["polindex"] is None) != (model["polangle"] is None):
            out.append(
                Refusal(
                    "calibrate.model.polindex",
                    "",
                    "polindex and polangle go together (CASA's setjy writes no "
                    "linear polarisation with only one)",
                )
            )
        # CASA's one-term-spix polarised path converts channel 0 to LSRK
        # (c7a-polmodels.md section 9), which needs astropy.
        polarised = (bool(flux) and any(float(v) != 0 for v in flux[1:4])) or (
            model["polindex"] is not None and model["polangle"] is not None
        )
        lengths = [
            len(v) if isinstance(v, (list, tuple)) else int(v is not None)
            for v in (model[k] for k in ("spix", "polindex", "polangle"))
        ]
        if polarised and max(lengths) <= 1:
            import importlib.util

            if importlib.util.find_spec("astropy") is None:
                out.append(
                    Refusal(
                        "calibrate.model.spix",
                        "",
                        "a polarised manual model with one spix term needs astropy "
                        "(pip install 'rang-core[imaging]') for CASA's channel-0 "
                        "LSRK conversion",
                    )
                )
    if source == "lsm" and model["lsm"] is None:
        out.append(Refusal("calibrate.model.lsm", "", "required for lsm"))
    for section in ("secondary", "polcal"):
        if any(t["type"] == "complex" for t in cal[section]["terms"]):
            out.append(
                Refusal(
                    f"calibrate.{section}",
                    "",
                    f"a complex term with model source {source}: the model is "
                    "written on the primary fields only; solve the secondary with "
                    "G and F terms (CASA's unit point model, then fluxscale)",
                )
            )


COMPLEX_HAS_NO = (
    "the complex term solves QuartiCal bins (solint inf, int or N integrations; "
    "freqint) with no CASA rules; use K, G and B terms for {what}"
)


def _term_refusals(where, term, cal, no):
    kind = term["type"]
    if kind in TERM_TASKS:
        no(f"{where}.type", TERM_TASKS[kind], f"term {kind}")
        return
    if kind != "complex":
        return  # K, G, B, A, F and the pol terms: `_chain_refusals`
    errors = []
    if isinstance(term["solint"], str) and term["solint"].endswith("s"):
        errors.append(("solint", f"solint {term['solint']} (CASA's seconds bins)"))
    if term["combine"]:
        errors.append(("combine", f"combine {term['combine']!r}"))
    for name, default in (
        ("refant", None),
        ("uvrange", ""),
        ("minsnr", None),
        ("minblperant", None),
    ):
        value = term[name] if term[name] is not None else cal[name]
        if value != default and value is not None:
            errors.append((name, f"{name} {value!r}"))
    if term["refantmode"] is not None:
        errors.append(("refantmode", "refantmode"))
    if term["preapply"]:
        errors.append(("preapply", "tables pre-applied while solving"))
    for name, what in errors:
        no(f"{where}.{name}", "", COMPLEX_HAS_NO.format(what=what))


SOLVED_TERMS = ("K", "G", "B", "F")
# CASA's combine axes the solves take (`rang.cal_gain.solint_bins`).
COMBINE_OK = {"scan", "obs"}


def _chain_refusals(config, out):
    """Errors in a K, G, B, A, F sequence (task C2e, research/c2e-calibrate.md):
    what `rang.cal_chain.run` cannot run as written. None names a task: each
    is a configuration mistake or a choice recorded as an owner decision in
    that note."""
    cal = config["calibrate"]

    def bad(path, text):
        out.append(Refusal(path, "", text))

    seen = {}  # name -> (section, type), in solve order
    kinds_used = set()
    primary_g = [t["name"] for t in cal["primary"]["terms"] if t["type"] == "G"]
    for section in CALIBRATE_SECTIONS:
        solved_here = False
        for i, term in enumerate(cal[section]["terms"]):
            where = f"calibrate.{section}.terms[{i}]"
            kind = term["type"]
            kinds_used.add(kind)
            if kind not in CHAIN_TERMS:
                seen[term["name"]] = (section, kind)
                continue
            if kind in POL_TERMS:
                if section != "polcal":
                    bad(f"{where}.type", f"a {kind} term belongs in polcal")
                _pol_term_errors(where, term, bad)
            elif section == "polcal":
                bad(f"{where}.type", f"a {kind} term belongs in primary or secondary")
            if kind == "F" and section != "secondary":
                bad(f"{where}.type", "F is solved on the secondary (CARACal's order)")
            if kind == "F" and not primary_g:
                bad(
                    f"{where}.type",
                    "F appends to a copy of the primary's last G: the primary has no "
                    "G term",
                )
            if kind == "A":
                preapplied = any(
                    seen.get(n, ("", ""))[1] in SOLVED_TERMS
                    for t in cal[section]["terms"][:i]
                    for n in t.get("preapply", [])
                )
                if not (solved_here or preapplied):
                    bad(
                        f"{where}.type",
                        "an A step needs a solved or pre-applied table before it "
                        "(CARACal refuses this order)",
                    )
                if term["strategy"] is None and config["flag"]["strategy"] is None:
                    bad(
                        f"{where}.strategy",
                        "required (a Tricolour strategy; flag.strategy is used "
                        "when set)",
                    )
                seen[term["name"]] = (section, kind)
                continue
            solved_here = True
            refant = term["refant"] if term["refant"] is not None else cal["refant"]
            if refant is None and kind not in ("KCROSS", "Xf"):
                bad(
                    f"{where}.refant",
                    "required for K, G, B, F, Gpol and Df (calibrate.refant)",
                )
            elif refant is not None and any(str(r).lower() == "auto" for r in refant):
                bad(
                    f"{where}.refant",
                    "refant auto (CARACal's manage_antennas rule) is not ported; "
                    "give antenna names or ids (an owner decision, "
                    "research/c2e-calibrate.md)",
                )
            if _is_int(term["solint"]):
                bad(
                    f"{where}.solint",
                    "an integer is N integrations, a complex-term interval; CASA "
                    "terms take inf, int or seconds such as 60s",
                )
            combine = {c.strip() for c in str(term["combine"]).split(",") if c.strip()}
            if combine - COMBINE_OK:
                bad(
                    f"{where}.combine",
                    f"combine {sorted(combine - COMBINE_OK)}: one field and one "
                    "window per solve (scan and obs are taken)",
                )
            if term.get("calmode") == "a":
                bad(f"{where}.calmode", "calmode a (amplitude only) is not ported")
            if term.get("solnorm"):
                bad(f"{where}.solnorm", "solnorm true is not ported (CARACal: false)")
            if term["gainfield"] and any(term["gainfield"]):
                bad(
                    f"{where}.gainfield",
                    "pre-applied tables use the rows of the solved field, or of "
                    "every field when the table has none of it; other field maps "
                    "are applied by apply.targets only",
                )
            for j, name in enumerate(term["preapply"]):
                if name not in seen:
                    bad(
                        f"{where}.preapply[{j}]",
                        f"{name!r} is not an earlier term (terms solve in order: "
                        "primary, secondary, polcal)",
                    )
                elif seen[name][1] not in SOLVED_TERMS + POL_TERMS:
                    bad(
                        f"{where}.preapply[{j}]",
                        f"{name!r} is a {seen[name][1]} term; K, G, B, F and "
                        "polarisation tables are pre-applied",
                    )
            seen[term["name"]] = (section, kind)
    if "complex" in kinds_used and kinds_used & set(CHAIN_TERMS):
        bad(
            "calibrate",
            "complex terms and CASA terms (K, G, B, A, F and the polarisation "
            "terms) cannot be mixed in one calibrate",
        )


def _pol_term_errors(where, term, bad):
    """What `rang.cal_pol` cannot run as written in a Gpol, KCROSS, Xf or
    Df term (task C6w, research/c6w-polwire.md)."""
    kind = term["type"]
    if kind == "Gpol" and term.get("calmode") not in (None, "p"):
        bad(
            f"{where}.calmode",
            "Gpol is phase-only (CARACal's gaincal calmode p); use a G term for "
            "amplitudes",
        )
    if kind in ("Xf", "Df") and term.get("parang") is False:
        bad(
            f"{where}.parang",
            "polcal always applies the parallactic angle (CASA's polcal has no "
            "parang argument)",
        )
    if term.get("preavg") is not None:
        bad(
            f"{where}.preavg",
            "pre-averaging is not ported: rang solves the cells, which gives "
            "polcal's answer for a model constant over the interval "
            "(research/c6-polterms.md section 1); leave it out",
        )
    clip = term.get("clip")
    if clip and (len(clip) != 2 or not clip[0] <= 0 < clip[1]):
        bad(
            f"{where}.clip",
            "[low, high] with low <= 0 < high: the leakage amplitude is clipped "
            "at high (CARACal's flagdata clipminmax [-0.6, 0.6])",
        )
    frac = term.get("min_data_fraction")
    if frac is not None and not 0 <= frac <= 1:
        bad(f"{where}.min_data_fraction", "must be between 0 and 1")


def validate(raw, stages, source=None):
    """The resolved configuration, or ConfigError with every schema error
    and every refusal for `stages`."""
    config, errors = resolve(raw)
    refused = [] if errors else refusals(config, stages)
    required = [(r.path, r.text) for r in refused if not r.task]
    refused = [r for r in refused if r.task]
    if errors or required or refused:
        raise ConfigError(errors + required, refused, source=source)
    return config


def validate_file(path, stages):
    return validate(load(path), stages, source=Path(path))


# Keys that set chunk sizes only: results do not depend on them (task W3,
# research/w3-chunking.md), so changing them does not make a stage "changed".
RESOURCE_KEYS = {"data": ("memory_limit_gb", "chunk_rows")}


def stage_hash(config, stage):
    """SHA-256 of the sections `stage` depends on (STAGE_SECTIONS), without
    the RESOURCE_KEYS."""
    part = {}
    for name in STAGE_SECTIONS[stage]:
        section = config[name]
        if name in RESOURCE_KEYS:
            section = {k: v for k, v in section.items() if k not in RESOURCE_KEYS[name]}
        part[name] = section
    text = json.dumps(part, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- the defaults, written down ----------------------------------------------------


def _flow(value):
    text = json.dumps(value)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        mantissa, e, exponent = repr(value).partition("e")
        return f"{mantissa}.0e{exponent}" if e and "." not in mantissa else repr(value)
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return (
            "["
            + ", ".join(
                "{" + ", ".join(f"{k}: {v}" for k, v in item.items()) + "}"
                for item in value
            )
            + "]"
        )
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\-/]*", value):
        return value if value not in ("null", "true", "false", "inf", "int") else text
    return text


def defaults_yaml():
    """Every key with its default and comment, as YAML (`rang-core config
    defaults`)."""
    lines = [
        "# rang-core configuration, every key at its default.",
        "# Required: flag.strategy (for flag), image.size and image.scale (for image).",
    ]

    def emit(spec, indent):
        for name, item in spec.items():
            pad = "  " * indent
            if isinstance(item, dict):
                lines.append(f"{pad}{name}:")
                emit(item, indent + 1)
                continue
            lines.append(f"{pad}{name}: {_flow(item.default)}  # {item.doc}")

    emit(SCHEMA, 0)
    lines.append("# A calibration term (calibrate.*.terms, selfcal.terms):")
    for name, item in TERM_KEYS.items():
        lines.append(f"#   {name}: {_flow(item.default)}  # {item.doc}")
    lines.append("# Term types: " + ", ".join(TERM_TYPES) + ".")
    lines.append(
        "# Implemented: complex, "
        + ", ".join(CASA_TERMS)
        + " (C2e), "
        + ", ".join(POL_TERMS)
        + " (C6w). Not yet: "
        + ", ".join(f"{t} ({TERM_TASKS[t]})" for t in TERM_TYPES if t in TERM_TASKS)
        + "."
    )
    return "\n".join(lines) + "\n"


__all__ = [
    "CASA_TERMS",
    "CHAIN_TERMS",
    "POL_TERMS",
    "SCHEMA",
    "STAGES",
    "TASKS",
    "TERM_TYPES",
    "VERSION",
    "ConfigError",
    "Refusal",
    "defaults_yaml",
    "load",
    "loads",
    "refusals",
    "resolve",
    "stage_hash",
    "validate",
    "validate_file",
]
