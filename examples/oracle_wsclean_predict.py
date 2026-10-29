"""Africanus oracle for the Rang core component predictor (research/core-phase3c-a.md).

Run once in rang-flagging:local (python-casacore and codex-africanus pinned):
    python examples/oracle_wsclean_predict.py <work.ms> <catalogue> <fresh-output-dir>

Writes oracle.npz (inputs and africanus visibilities and spectra for the
response, catalogue and stress component sets) and receipt.json. Read only on
the MS and catalogue.
"""

import json
import sys
import time
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

import numpy as np
from africanus.model.wsclean.spec_model import spectra
from africanus.rime import wsclean_predict
from casacore.tables import table

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/flagging/sky"))
sys.path.insert(0, str(ROOT / "python"))
from rangtoy.flagging_response import REFERENCE_HZ, SOURCES
from verify_prediction import read_catalog

ARCMIN = np.pi / 10800
CHANNELS = slice(1024, 3072)
SEED = 20261029


def lm_from_radec(radec, phase):
    """Direction cosines as in flagging_sky.point_catalog_predict."""
    ra, dec = radec.T
    ra0, dec0 = phase
    difference = ra - ra0
    l = np.cos(dec) * np.sin(difference)
    m = np.sin(dec) * np.cos(dec0) - np.cos(dec) * np.sin(dec0) * np.cos(difference)
    return np.stack((l, m), axis=1)


def response_set():
    return {
        "lm": np.array([[s["l_arcmin"], s["m_arcmin"]] for s in SOURCES]) * ARCMIN,
        "types": np.array([0 if s["fwhm_arcmin"] == 0 else 1 for s in SOURCES]),
        "flux": np.array([s["flux_jy"] for s in SOURCES], float),
        "coeffs": np.array([[s["spectral_index"]] for s in SOURCES], float),
        "log_poly": np.ones(len(SOURCES), bool),
        "ref_freq": np.full(len(SOURCES), float(REFERENCE_HZ)),
        "gauss_shape": np.array(
            [[s["fwhm_arcmin"] * ARCMIN] * 2 + [0.0] for s in SOURCES], float
        ),
    }


def catalogue_set(path, phase):
    sources = read_catalog(path)
    lengths = {len(s[3]) for s in sources}
    if len(lengths) != 1:
        raise ValueError("catalogue coefficients must have one length")
    radec = np.array([s[:2] for s in sources])
    n = len(sources)
    return {
        "lm": lm_from_radec(radec, phase),
        "types": np.zeros(n, int),
        "flux": np.array([s[2] for s in sources], float),
        "coeffs": np.array([s[3] for s in sources], float),
        "log_poly": np.zeros(n, bool),
        "ref_freq": np.array([s[4] for s in sources], float),
        "gauss_shape": np.zeros((n, 3)),
    }


def stress_set():
    rng = np.random.default_rng(SEED)
    n = 64
    types = np.arange(n) % 2
    major = rng.uniform(0.5, 5.0, n) * ARCMIN
    minor = major * rng.uniform(0.2, 1.0, n)
    angle = rng.uniform(0, np.pi, n)
    log_poly = (np.arange(n) // 2) % 2 == 0
    coeffs = rng.normal(0, 1, (n, 3)) * np.where(log_poly, 0.5, 0.05)[:, None]
    return {
        "lm": rng.uniform(-1, 1, (n, 2)) * np.deg2rad(1.0),
        "types": types,
        "flux": rng.uniform(0.1, 2.0, n),
        "coeffs": coeffs,
        "log_poly": log_poly,
        "ref_freq": np.full(n, 1.284e9),
        "gauss_shape": np.where(
            types[:, None] == 1, np.stack((major, minor, angle), axis=1), 0.0
        ),
    }


def predict(components, uvw, frequency):
    names = np.array(["POINT", "GAUSSIAN"])[components["types"]]
    args = (
        uvw,
        components["lm"],
        names,
        components["flux"],
        components["coeffs"],
        components["log_poly"],
        components["ref_freq"],
        components["gauss_shape"],
        frequency,
    )
    started = time.perf_counter()
    vis = wsclean_predict(*args)[..., 0]
    first = time.perf_counter() - started
    started = time.perf_counter()
    again = wsclean_predict(*args)[..., 0]
    second = time.perf_counter() - started
    if not np.array_equal(vis, again):
        raise RuntimeError("africanus prediction is not repeatable")
    spec = spectra(
        components["flux"],
        components["coeffs"],
        components["log_poly"],
        components["ref_freq"],
        frequency,
    )
    return vis, spec, first, second


def main():
    ms, catalogue, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=False)
    with table(str(ms), readonly=True, ack=False, lockoptions="autonoread") as t:
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        rows = np.flatnonzero(a1 != a2)
        uvw = np.ascontiguousarray(t.getcol("UVW")[rows])
    with table(
        str(ms / "FIELD"), readonly=True, ack=False, lockoptions="autonoread"
    ) as t:
        phase = t.getcol("PHASE_DIR")[0, 0]
    with table(
        str(ms / "SPECTRAL_WINDOW"), readonly=True, ack=False, lockoptions="autonoread"
    ) as t:
        frequency = np.ascontiguousarray(t.getcol("CHAN_FREQ")[0, CHANNELS])
    sets = {
        "response": response_set(),
        "catalogue": catalogue_set(catalogue, phase),
        "stress": stress_set(),
    }
    arrays = {"uvw": uvw, "frequency": frequency, "rows": rows, "phase": phase}
    timing = {}
    for name, components in sets.items():
        vis, spec, first, second = predict(components, uvw, frequency)
        for key, value in components.items():
            arrays[f"{name}_{key}"] = value
        arrays[f"{name}_vis"] = vis
        arrays[f"{name}_spectra"] = spec
        timing[name] = {"first_call_seconds": first, "second_call_seconds": second}
    np.savez(out / "oracle.npz", **arrays)
    receipt = {
        "ms": str(ms),
        "catalogue": str(catalogue),
        "catalogue_sha256": sha256(catalogue.read_bytes()).hexdigest(),
        "oracle_sha256": sha256((out / "oracle.npz").read_bytes()).hexdigest(),
        "rows": len(rows),
        "channels": [1024, 3072],
        "components": {k: len(v["flux"]) for k, v in sets.items()},
        "timing": timing,
        "versions": {n: version(n) for n in ("codex-africanus", "numba", "numpy")},
        "seed": SEED,
    }
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
