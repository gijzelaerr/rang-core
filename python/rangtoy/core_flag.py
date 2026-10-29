"""Tricolour-strategy flagging on the Rang core (research/core-d-tricolour.md).

Runs Tricolour 0.2.1's `polarisation` flagging strategy, ported to Rust in
`core/src/sumthreshold.rs`, on in-memory arrays: a strategy YAML of the kind
CARACAL ships, the two static masks copied into `core/data/`, and the rows,
flags and metadata of one field/scan group. The Measurement Set edge stays
outside this module. The library is the same `librang_core` as `core.py`;
this module registers its own ctypes symbols as `core_zarr.py` does.
"""

import ctypes
import math
import re
import time

import numpy as np

from . import core

STEP_WIDTH = 32
TASK_CODES = {
    "flag_nans_zeros": 0,
    "apply_static_mask": 1,
    "sum_threshold": 2,
    "uvcontsub_flagger": 3,
    "flag_autos": 4,
    "combine_with_input_flags": 5,
    "unflag": 6,
}
SUM_THRESHOLD_DEFAULTS = {
    "outlier_nsigma": 4.5,
    "windows_time": [1, 2, 4, 8],
    "windows_freq": [1, 2, 4, 8],
    "background_reject": 2.0,
    "background_iterations": 1,
    "spike_width_time": 12.5,
    "spike_width_freq": 10.0,
    "time_extend": 3,
    "freq_extend": 3,
    "freq_chunks": 10,
    "average_freq": 1,
    "flag_all_time_frac": 0.6,
    "flag_all_freq_frac": 0.8,
    "rho": 1.3,
    "num_major_iterations": 5,
}
UVCONTSUB_DEFAULTS = {
    "major_cycles": 5,
    "or_original_from_cycle": 1,
    "taylor_degrees": 20,
    "sigma": 5,
}
STATIC_MASK_FILES = ("4k_lband_meerkat.staticmask", "4k_uhfband_meerkat.staticmask")


class _FlagInputs(ctypes.Structure):
    _fields_ = [
        ("nrow", ctypes.c_size_t),
        ("nchan", ctypes.c_size_t),
        ("ncorr", ctypes.c_size_t),
        ("nant", ctypes.c_size_t),
        ("nbl", ctypes.c_size_t),
        ("ntime", ctypes.c_size_t),
        ("nmasks", ctypes.c_size_t),
        ("nsteps", ctypes.c_size_t),
        ("data", ctypes.POINTER(ctypes.c_float)),
        ("flags", ctypes.POINTER(ctypes.c_uint8)),
        ("baseline_index", ctypes.POINTER(ctypes.c_uint32)),
        ("time_index", ctypes.POINTER(ctypes.c_uint32)),
        ("baselines", ctypes.POINTER(ctypes.c_uint32)),
        ("antenna_position", ctypes.POINTER(ctypes.c_double)),
        ("chan_freq", ctypes.POINTER(ctypes.c_double)),
        ("chan_width", ctypes.POINTER(ctypes.c_double)),
        ("corr_type", ctypes.POINTER(ctypes.c_int32)),
        ("mask_freqs", ctypes.POINTER(ctypes.c_double)),
        ("mask_offsets", ctypes.POINTER(ctypes.c_size_t)),
        ("steps", ctypes.POINTER(ctypes.c_double)),
    ]


class _FlagOutputs(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.POINTER(ctypes.c_uint8)),
        ("intensity", ctypes.POINTER(ctypes.c_float)),
        ("stages", ctypes.POINTER(ctypes.c_uint8)),
    ]


def _lib():
    lib = core.library()
    if not getattr(lib, "_rang_flag_ready", False):
        lib.rang_core_flag_rows.argtypes = [
            ctypes.POINTER(_FlagInputs),
            ctypes.POINTER(_FlagOutputs),
        ]
        lib.rang_core_flag_rows.restype = ctypes.c_int
        lib._rang_flag_ready = True
    return lib


def _ptr(array, kind):
    return array.ctypes.data_as(ctypes.POINTER(kind))


def static_mask_files():
    """The two Tricolour 0.2.1 static masks copied into `core/data/`."""
    return [core.core_root() / "data" / name for name in STATIC_MASK_FILES]


def load_static_mask(path):
    """Masked channel centre frequencies in Hz, as `tricolour.mask.load_mask`."""
    mask = np.load(path, allow_pickle=False)
    if mask.dtype[0] != bool or mask.dtype[1] != np.float64:
        raise ValueError(f"{path} is not a static mask with dtype (bool, float64)")
    channels = mask["chans"][1]
    flags = mask["mask"][0]
    return np.ascontiguousarray(channels[flags], dtype=np.float64)


def _scalar(text):
    text = text.strip()
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [_scalar(item) for item in inner.split(",")] if inner else []
    if re.fullmatch(r"[-+]?\d+", text):
        return int(text)
    if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?", text):
        return float(text)
    return text


def parse_strategy(text):
    """Read a Tricolour strategy YAML (the subset CARACAL's files use).

    Returns the `strategies` list of dicts with `name`, `task` and `kwargs`.
    Handles comments, blank lines, `-` item markers, scalar values, quoted
    strings and flow lists; nothing else is needed by the shipped files.
    """
    strategies = []
    current = None
    kwargs = None
    kwargs_indent = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        body = line.strip()
        if body == "strategies:":
            continue
        if body == "-" or body.startswith("- "):
            current = {"kwargs": {}}
            strategies.append(current)
            kwargs = None
            body = body[1:].strip()
            if not body:
                continue
        if current is None:
            raise ValueError(f"unexpected line outside a strategy: {raw!r}")
        key, _, value = body.partition(":")
        key = key.strip()
        if key == "kwargs" and not value.strip():
            kwargs = current["kwargs"]
            kwargs_indent = indent
            continue
        if kwargs is not None and indent > kwargs_indent:
            kwargs[key] = _scalar(value)
        else:
            kwargs = None
            current[key] = _scalar(value)
    return strategies


def casa_style_range(value):
    """`tricolour.util.casa_style_range` for metres: `""` or `"a~b[m]"`."""
    if not isinstance(value, str):
        raise TypeError("uvrange must be a string")
    text = value.strip()
    if text in ("", "*"):
        return (0.0, math.inf)
    match = re.fullmatch(
        r"(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?~(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\s*m?",
        text,
    )
    if not match:
        raise ValueError(f"uvrange {value!r} must be a range or blank")
    low, high = text.replace(" ", "").replace("m", "").split("~")
    return (float(low), float(high))


def encode_steps(strategies):
    """Flatten strategy steps into the `(nsteps, STEP_WIDTH)` table."""
    table = np.zeros((len(strategies), STEP_WIDTH), dtype=np.float64)
    for row, strategy in zip(table, strategies):
        task = strategy["task"]
        kwargs = dict(strategy.get("kwargs") or {})
        row[0] = TASK_CODES[task]
        if task == "apply_static_mask":
            mode = str(kwargs.pop("accumulation_mode", "or")).strip()
            if mode not in ("or", "override"):
                raise ValueError(f"accumulation_mode {mode!r}")
            low, high = casa_style_range(kwargs.pop("uvrange", ""))
            row[1:4] = (mode == "or", low, high)
        elif task == "sum_threshold":
            params = dict(SUM_THRESHOLD_DEFAULTS)
            params.update(kwargs)
            kwargs = {
                k: v for k, v in kwargs.items() if k not in SUM_THRESHOLD_DEFAULTS
            }
            windows_time = list(params["windows_time"])
            windows_freq = list(params["windows_freq"])
            if len(windows_time) > 8 or len(windows_freq) > 8:
                raise ValueError("at most eight windows per axis")
            row[1] = params["outlier_nsigma"]
            row[2] = len(windows_time)
            row[3 : 3 + len(windows_time)] = windows_time
            row[11] = len(windows_freq)
            row[12 : 12 + len(windows_freq)] = windows_freq
            row[20:32] = [
                params["background_reject"],
                params["background_iterations"],
                params["spike_width_time"],
                params["spike_width_freq"],
                params["time_extend"],
                params["freq_extend"],
                params["freq_chunks"],
                params["average_freq"],
                params["flag_all_time_frac"],
                params["flag_all_freq_frac"],
                params["rho"],
                params["num_major_iterations"],
            ]
        elif task == "uvcontsub_flagger":
            params = dict(UVCONTSUB_DEFAULTS)
            params.update(kwargs)
            kwargs = {k: v for k, v in kwargs.items() if k not in UVCONTSUB_DEFAULTS}
            row[1:5] = [
                params["major_cycles"],
                params["or_original_from_cycle"],
                params["taylor_degrees"],
                params["sigma"],
            ]
        if kwargs:
            raise ValueError(f"unused kwargs for {task}: {sorted(kwargs)}")
    return table


def unique_baselines(antenna1, antenna2):
    """Tricolour's baseline order: unique pairs sorted as 64-bit (a1, a2) words."""
    stacked = np.stack([antenna1, antenna2], axis=1).astype(np.int32)
    ubl = np.unique(np.ascontiguousarray(stacked).view(np.int64)).view(np.int32)
    return ubl.reshape(-1, 2)


def flag_rows(
    data,
    flags,
    antenna1,
    antenna2,
    times,
    antenna_position,
    chan_freq,
    chan_width,
    corr_type,
    strategies,
    masks=None,
    want_intensity=True,
    want_stages=True,
):
    """Flag one field/scan group as `tricolour --flagging-strategy polarisation`.

    `data` is `(row, chan, corr)` complex64, `flags` the same shape bool;
    `strategies` is the list from `parse_strategy`; `masks` defaults to the
    two shipped static masks. Returns a dict with `flags` (every correlation
    carries the window flag), `intensity` (complex64 window
    `(bl, 1, time, chan)`), `stages` (window flags after each step, keyed
    `NN-task`), `ubl`, `time_inv` and `seconds` (the core call only).
    """
    data = np.require(data, dtype=np.complex64, requirements=["C", "A"])
    nrow, nchan, ncorr = data.shape
    flags = np.require(flags, dtype=bool, requirements=["C", "A"])
    if flags.shape != data.shape:
        raise ValueError("flags must match data")
    antenna1 = np.asarray(antenna1, dtype=np.int32)
    antenna2 = np.asarray(antenna2, dtype=np.int32)
    ubl = unique_baselines(antenna1, antenna2)
    lookup = {(int(a1), int(a2)): b for b, (a1, a2) in enumerate(ubl)}
    baseline_index = np.array(
        [lookup[(int(a1), int(a2))] for a1, a2 in zip(antenna1, antenna2)],
        dtype=np.uint32,
    )
    _, time_inv = np.unique(np.asarray(times, dtype=np.float64), return_inverse=True)
    time_inv = np.ascontiguousarray(time_inv.reshape(-1), dtype=np.uint32)
    ntime, nbl = int(time_inv.max()) + 1, ubl.shape[0]
    antenna_position = np.require(antenna_position, np.float64, ["C", "A"])
    nant = antenna_position.shape[0]
    if antenna_position.shape != (nant, 3):
        raise ValueError("antenna_position must be (nant, 3)")
    chan_freq = np.require(chan_freq, np.float64, ["C", "A"])
    chan_width = np.require(chan_width, np.float64, ["C", "A"])
    if chan_freq.shape != (nchan,) or chan_width.shape != (nchan,):
        raise ValueError("chan_freq and chan_width must have nchan entries")
    corr_type = np.require(corr_type, np.int32, ["C", "A"])
    if masks is None:
        masks = [load_static_mask(path) for path in static_mask_files()]
    masks = [np.require(m, np.float64, ["C", "A"]).reshape(-1) for m in masks]
    mask_freqs = (np.concatenate(masks) if masks else np.zeros(0, np.float64)).astype(
        np.float64
    )
    mask_offsets = np.zeros(len(masks) + 1, dtype=np.uintp)
    mask_offsets[1:] = np.cumsum([m.size for m in masks], dtype=np.uintp)
    steps = encode_steps(strategies)
    baselines = np.ascontiguousarray(ubl, dtype=np.uint32)
    out_flags = np.zeros((nrow, nchan, ncorr), dtype=np.uint8)
    intensity = (
        np.zeros((nbl, 1, ntime, nchan), dtype=np.complex64) if want_intensity else None
    )
    stages = (
        np.zeros((len(strategies), nbl, 1, ntime, nchan), dtype=np.uint8)
        if want_stages
        else None
    )
    inputs = _FlagInputs(
        nrow=nrow,
        nchan=nchan,
        ncorr=ncorr,
        nant=nant,
        nbl=nbl,
        ntime=ntime,
        nmasks=len(masks),
        nsteps=len(strategies),
        data=_ptr(data.view(np.float32), ctypes.c_float),
        flags=_ptr(flags.view(np.uint8), ctypes.c_uint8),
        baseline_index=_ptr(baseline_index, ctypes.c_uint32),
        time_index=_ptr(time_inv, ctypes.c_uint32),
        baselines=_ptr(baselines, ctypes.c_uint32),
        antenna_position=_ptr(antenna_position, ctypes.c_double),
        chan_freq=_ptr(chan_freq, ctypes.c_double),
        chan_width=_ptr(chan_width, ctypes.c_double),
        corr_type=_ptr(corr_type, ctypes.c_int32),
        mask_freqs=_ptr(mask_freqs, ctypes.c_double),
        mask_offsets=_ptr(mask_offsets, ctypes.c_size_t),
        steps=_ptr(steps, ctypes.c_double),
    )
    outputs = _FlagOutputs(
        flags=_ptr(out_flags, ctypes.c_uint8),
        intensity=_ptr(intensity.view(np.float32), ctypes.c_float)
        if want_intensity
        else None,
        stages=_ptr(stages, ctypes.c_uint8) if want_stages else None,
    )
    lib = _lib()
    started = time.perf_counter()
    code = lib.rang_core_flag_rows(ctypes.byref(inputs), ctypes.byref(outputs))
    seconds = time.perf_counter() - started
    if code:
        raise RuntimeError(f"rang_core_flag_rows failed with code {code}")
    names = [f"{i:02d}-{s['task']}" for i, s in enumerate(strategies)]
    return {
        "flags": out_flags.astype(bool),
        "intensity": intensity,
        "stages": {name: stages[i].astype(bool) for i, name in enumerate(names)}
        if want_stages
        else None,
        "ubl": ubl,
        "time_inv": time_inv,
        "seconds": seconds,
    }
