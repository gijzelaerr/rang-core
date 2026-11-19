# SPDX-License-Identifier: MIT
"""The swap contract of learned stages (task DL1, research/dl1-contract.md;
research/dl-plan.md section 4).

Every stage section of the configuration has a `learned` key::

    learned: {mode: off, weights: null, force: false}

`off` (the default) leaves the stage exactly as it was: no receipt entry,
no change to the stage hash. Another mode needs a weights file: ONNX, with
the provenance header (`Header`) as JSON in `metadata_props` under
`rang.learned`, read by the Rust core without PyTorch or the `onnx`
package. A mode is refused unless the file records that it passed that
mode's gates, unless `force`; outside the file's validity envelope mode
`propose` falls back to the classical path and `settings` and `replace`
refuse unless `force`.

The registry (`register`, `Tenant`) names, per stage, the architectures
that can run there and whether the stage driver calls them (`pipeline`).
PyTorch lives in `rang.learned_torch` only (extra `learned-train`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import core

MODES = ("off", "propose", "settings", "replace")
FORMAT = "rang.learned/1"
HEADER_KEY = "rang.learned"
# The configuration stages that carry the key (rang.core_config.STAGES).
STAGES = ("flag", "calibrate", "apply", "image", "selfcal")
DATA_CLASSES = ("calibrator", "target", "any")
ENVELOPE_KEYS = ("antennas", "baseline_m", "channel_width_hz", "dump_s", "band_hz")
HEADER_FIELDS = (
    "format",
    "stage",
    "data_class",
    "telescope",
    "band",
    "architecture",
    "inputs",
    "outputs",
    "normalisation",
    "training",
    "gates",
    "envelope",
    "licence",
    "source",
)


class Refused(ValueError):
    """A learned mode that may not run, with the reason."""


# -- the header -------------------------------------------------------------------


@dataclass(frozen=True)
class Header:
    stage: str
    data_class: str
    telescope: str
    band: str
    architecture: dict
    inputs: dict
    outputs: dict
    normalisation: dict
    training: dict
    gates: dict
    envelope: dict
    licence: str
    source: str

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            raise Refused("header: not a JSON object")
        if d.get("format") != FORMAT:
            raise Refused(
                f"header: format {d.get('format')!r}, this rang reads {FORMAT}"
            )
        missing = [k for k in HEADER_FIELDS if k not in d]
        if missing:
            raise Refused("header: missing " + ", ".join(missing))
        unknown = sorted(set(d) - set(HEADER_FIELDS))
        if unknown:
            raise Refused("header: unknown fields " + ", ".join(unknown))
        if d["stage"] not in STAGES:
            raise Refused(f"header: stage {d['stage']!r} is not one of {list(STAGES)}")
        if d["data_class"] not in DATA_CLASSES:
            raise Refused(
                f"header: data_class {d['data_class']!r} is not one of {list(DATA_CLASSES)}"
            )
        arch = d["architecture"]
        if not (
            isinstance(arch, dict)
            and isinstance(arch.get("id"), str)
            and isinstance(arch.get("hyperparameters"), dict)
        ):
            raise Refused("header: architecture must be {id, hyperparameters}")
        gates = d["gates"]
        if not isinstance(gates, dict):
            raise Refused("header: gates must map modes to {passed, rule, scores}")
        for mode, g in gates.items():
            if mode not in MODES[1:]:
                raise Refused(f"header: gates for unknown mode {mode!r}")
            if not (isinstance(g, dict) and isinstance(g.get("passed"), bool)):
                raise Refused(f"header: gates.{mode}.passed must be true or false")
        env = d["envelope"]
        if not isinstance(env, dict):
            raise Refused("header: envelope must be a mapping")
        for k, v in env.items():
            if k not in ENVELOPE_KEYS:
                raise Refused(
                    f"header: envelope key {k!r} not one of {list(ENVELOPE_KEYS)}"
                )
            if not (
                isinstance(v, list)
                and len(v) == 2
                and all(isinstance(x, (int, float)) for x in v)
                and v[0] <= v[1]
            ):
                raise Refused(f"header: envelope.{k} must be [lo, hi]")
        for k in ("inputs", "outputs", "normalisation", "training"):
            if not isinstance(d[k], dict):
                raise Refused(f"header: {k} must be a mapping")
        return cls(**{k: d[k] for k in HEADER_FIELDS if k != "format"})

    def passed(self, mode):
        return bool(self.gates.get(mode, {}).get("passed", False))


@dataclass(frozen=True)
class WeightsFile:
    path: str
    sha256: str
    header: Header
    inputs: tuple
    outputs: tuple
    ops: tuple
    payload: bytes = field(repr=False)


def load(path):
    """Read and check a weights file (ONNX with the `rang.learned` header)."""
    path = Path(path)
    try:
        payload = path.read_bytes()
    except OSError as e:
        raise Refused(f"weights {path}: {e.strerror or e}") from e
    try:
        meta, inputs, outputs, ops = core.extension().learned_onnx_metadata(payload)
    except ValueError as e:
        raise Refused(f"weights {path}: {e}") from e
    text = dict(meta).get(HEADER_KEY)
    if text is None:
        raise Refused(f"weights {path}: no {HEADER_KEY} header in metadata_props")
    try:
        header = Header.from_dict(json.loads(text))
    except json.JSONDecodeError as e:
        raise Refused(f"weights {path}: header is not JSON ({e})") from e
    except Refused as e:
        raise Refused(f"weights {path}: {e}") from e
    return WeightsFile(
        str(path),
        hashlib.sha256(payload).hexdigest(),
        header,
        tuple(inputs),
        tuple(outputs),
        tuple(ops),
        payload,
    )


# -- the registry -----------------------------------------------------------------


@dataclass(frozen=True)
class Tenant:
    """A learned implementation of one stage.

    `architectures` maps an architecture id to `accepts(hyperparameters) ->
    str | None` (None: accepted; else why not). `run(decision, *args)` is
    the forward. `pipeline`: whether the stage driver of `rang-core` calls
    it; a non-off mode on a stage with no pipeline tenant is a configuration
    refusal. `approximate`: the tenant's product is labelled approximate in
    its receipt, which mode `replace` requires (dl-plan decision 3). Training
    fields (features, loss, teacher runner, gates) are added by the tenants
    that train (DL6, research/dl-plan.md section 4 item 6)."""

    name: str
    stage: str
    architectures: dict
    run: object
    modes: tuple = ("propose",)
    pipeline: bool = False
    approximate: bool = False
    doc: str = ""


_REGISTRY: dict = {}


def register(tenant):
    if tenant.stage not in STAGES:
        raise ValueError(f"tenant {tenant.name}: stage {tenant.stage!r}")
    if not set(tenant.modes) <= set(MODES[1:]):
        raise ValueError(f"tenant {tenant.name}: modes {tenant.modes}")
    _REGISTRY[tenant.name] = tenant
    return tenant


def tenants(stage=None):
    return [t for t in _REGISTRY.values() if stage is None or t.stage == stage]


def tenant_for(stage, header):
    """The tenant that runs `header`'s architecture on `stage`, or Refused."""
    arch = header.architecture
    why = []
    for t in tenants(stage):
        accepts = t.architectures.get(arch["id"])
        if accepts is None:
            continue
        reason = accepts(arch["hyperparameters"])
        if reason is None:
            return t
        why.append(f"{t.name}: {reason}")
    raise Refused(
        f"no tenant of stage {stage} runs architecture {arch['id']}"
        + (f" ({'; '.join(why)})" if why else "")
    )


# -- selection, refusal, receipts ---------------------------------------------------


@dataclass
class Decision:
    stage: str
    mode: str
    weights: WeightsFile
    tenant: Tenant
    forced: list
    envelope_violations: list
    fallback: bool
    runtime: str = "kernel"

    def receipt(self):
        """The stage receipt's `learned` entry (research/dl1-contract.md, 4)."""
        h = self.weights.header
        return {
            "mode": self.mode,
            "tenant": self.tenant.name,
            "weights": self.weights.path,
            "weights_sha256": self.weights.sha256,
            "architecture": h.architecture,
            "data_class": h.data_class,
            "gates_passed": h.passed(self.mode),
            "envelope": {
                "ok": not self.envelope_violations,
                "violations": list(self.envelope_violations),
            },
            "forced": list(self.forced),
            "fallback": self.fallback,
            "approximate": self.mode == "replace" and not self.fallback,
            "runtime": self.runtime,
        }


def settings_of(config, stage):
    """The stage's `learned` settings from a resolved configuration."""
    return config[stage]["learned"]


def is_off(settings):
    return settings is None or settings.get("mode", "off") == "off"


def envelope_violations(header, observation):
    """[text] for each envelope bound the observation breaks; quantities
    the observation does not give are not checked. `observation` maps
    ENVELOPE_KEYS to a number or (lo, hi)."""
    out = []
    for key, (lo, hi) in header.envelope.items():
        v = (observation or {}).get(key)
        if v is None:
            continue
        vlo, vhi = (v, v) if isinstance(v, (int, float)) else (min(v), max(v))
        if vlo < lo or vhi > hi:
            got = vlo if vlo == vhi else [vlo, vhi]
            out.append(f"{key} {got} outside [{lo}, {hi}]")
    return out


def select(stage, settings, observation=None, weights_base=None):
    """None for mode off; else the Decision, or Refused with the reason.
    Order (research/dl1-contract.md, section 3): gates, header match,
    envelope."""
    if is_off(settings):
        return None
    mode = settings["mode"]
    force = bool(settings.get("force", False))
    if mode not in MODES:
        raise Refused(f"{stage}.learned.mode {mode!r} is not one of {list(MODES)}")
    path = settings.get("weights")
    if not path:
        raise Refused(f"{stage}.learned.weights: mode {mode} needs a weights file")
    path = Path(path).expanduser()
    if weights_base is not None and not path.is_absolute():
        path = Path(weights_base) / path
    w = load(path)
    h = w.header
    forced = []
    if not h.passed(mode):
        if not force:
            raise Refused(
                f"{stage}.learned: {path.name} has not passed the gates of mode {mode}"
                " (set force: true for an experiment)"
            )
        forced.append("gates")
    if h.stage != stage:
        raise Refused(
            f"{stage}.learned: {path.name} is a weights file of stage {h.stage}"
        )
    tenant = tenant_for(stage, h)
    if mode not in tenant.modes:
        raise Refused(f"{stage}.learned: tenant {tenant.name} has no mode {mode}")
    if mode == "replace" and not tenant.approximate:
        raise Refused(
            f"{stage}.learned: mode replace needs a product labelled approximate; "
            f"{tenant.name}'s is not"
        )
    bad = envelope_violations(h, observation)
    fallback = False
    if bad:
        if mode == "propose":
            fallback = True
        elif force:
            forced.append("envelope")
        else:
            raise Refused(
                f"{stage}.learned: outside the envelope of {path.name}: "
                + "; ".join(bad)
                + " (set force: true for an experiment)"
            )
    return Decision(stage, mode, w, tenant, forced, bad, fallback)


def hash_part(settings, weights_base=None):
    """What the stage hash takes from `learned`: None for off (so that no
    existing hash changes), else {mode, force, weights_sha256}."""
    if is_off(settings):
        return None
    path = settings.get("weights")
    sha = None
    if path:
        p = Path(path).expanduser()
        if weights_base is not None and not p.is_absolute():
            p = Path(weights_base) / p
        try:
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            sha = None
    return {
        "mode": settings["mode"],
        "force": bool(settings.get("force", False)),
        "weights_sha256": sha,
    }


def config_refusals(config, stages, weights_base=None):
    """[(path, text)] for every stage in `stages` whose learned mode is not
    off and cannot run: no pipeline tenant, a missing or bad weights file,
    a failed gate without force, a header of another stage."""
    out = []
    for stage in stages:
        s = config.get(stage, {}).get("learned")
        if is_off(s):
            continue
        where = f"{stage}.learned"
        live = [t for t in tenants(stage) if t.pipeline]
        if not live:
            names = [t.name for t in tenants(stage)]
            out.append(
                (
                    f"{where}.mode",
                    f"no learned tenant runs in the {stage} stage of rang-core yet"
                    + (
                        f" (registered for the Python API only: {', '.join(names)})"
                        if names
                        else ""
                    ),
                )
            )
            continue
        try:
            d = select(stage, s, None, weights_base)
        except Refused as e:
            out.append((where, str(e)))
            continue
        if not d.tenant.pipeline:
            out.append(
                (where, f"tenant {d.tenant.name} does not run in rang-core {stage}")
            )
    return out


# -- tenants: dilated-cnn/1 (F3, F4; F5 when it ships) --------------------------------

DILATED_CNN = "dilated-cnn/1"
# Feature sets the Rust kernels compute, by input-plane count.
_DILATED_FEATURES = {15: "f3flag", 23: "f4flag"}


def _dilated_accepts(hp):
    inputs = hp.get("inputs")
    if inputs not in _DILATED_FEATURES:
        return f"inputs {inputs!r}: kernels exist for {sorted(_DILATED_FEATURES)}"
    if hp.get("hidden") != 8 or list(hp.get("dilations", ())) != [1, 2, 4, 8, 16]:
        return "the Rust kernels take hidden 8 and dilations [1, 2, 4, 8, 16]"
    return None


def dilated_cnn_weights(weights):
    """The flat float32 weights of a dilated-cnn/1 file in the kernels'
    order, copied from the ONNX initializers."""
    hp = weights.header.architecture["hyperparameters"]
    return core.extension().learned_dilated_cnn_weights(
        weights.payload, int(hp["inputs"]), int(hp["hidden"]), list(hp["dilations"])
    )


def run_dilated_cnn(decision, scan, flagged, data=None):
    """(row, chan) float32 logits of a dilated-cnn/1 flagger on one scan
    (`rang.f3flag`'s scan dict), by the Rust kernel of its feature set."""
    w = decision.weights
    flat = dilated_cnn_weights(w)
    inputs = int(w.header.architecture["hyperparameters"]["inputs"])
    if _DILATED_FEATURES[inputs] == "f3flag":
        from . import f3flag as mod
    else:
        from . import f4flag as mod
    return mod.rust_logits(scan, flagged, flat, data)


register(
    Tenant(
        name="dilated-cnn-flag",
        stage="flag",
        architectures={DILATED_CNN: _dilated_accepts},
        run=run_dilated_cnn,
        modes=("propose", "replace"),
        pipeline=False,
        approximate=True,
        doc="F3/F4's per-baseline network (research/f3-flagger.md, f4-flagger.md); "
        "Python API only: no weights file has passed its gates",
    )
)


__all__ = [
    "DATA_CLASSES",
    "DILATED_CNN",
    "ENVELOPE_KEYS",
    "FORMAT",
    "HEADER_KEY",
    "MODES",
    "STAGES",
    "Decision",
    "Header",
    "Refused",
    "Tenant",
    "WeightsFile",
    "config_refusals",
    "dilated_cnn_weights",
    "envelope_violations",
    "hash_part",
    "is_off",
    "load",
    "register",
    "run_dilated_cnn",
    "select",
    "tenant_for",
    "tenants",
]
