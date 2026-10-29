"""Validate the Rust component predictor (research/core-phase3c-a.md).

Usage: python examples/validate_core_phase3c_a.py <oracle-dir> outputs/<fresh-run>

Compares the core predictor with the africanus oracle produced by
examples/oracle_wsclean_predict.py, and with rang's NumPy templates, by the
frozen criteria. Writes only result.json in the fresh run directory.
"""

import json
import re
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np
from rangtoy import core
from rangtoy.flagging_response import SOURCES as RESPONSE_SOURCES
from rangtoy.flagging_signal import spatial_templates
from rangtoy.flagging_sky import point_catalog_predict

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "outputs/flagging-sky-inputs/fitted.PKS1934.LBand.wsclean.cat.txt"
TOL, SPECTRA_TOL = 1e-12, 1e-13
SETS = ("response", "catalogue", "stress")


def components(oracle, name):
    keys = ("lm", "types", "flux", "coeffs", "log_poly", "ref_freq", "gauss_shape")
    return [oracle[f"{name}_{k}"] for k in keys]


def bound(spectra):
    """Per-channel 1e-12 x sum of absolute component fluxes."""
    return TOL * np.sum(np.abs(spectra), axis=0)


def parse_catalogue(path):
    """Host-side parse of the pinned POINT/ordinary catalogue (radec, flux, ...)."""
    sources = []
    for line in Path(path).read_text().splitlines()[1:]:
        fields = re.sub(r"\[([^\]]*)\]", lambda x: x[0].replace(",", ";"), line).split(
            ","
        )
        hour, minute, second = map(float, fields[2].split(":"))
        ra = np.deg2rad(15 * (hour + minute / 60 + second / 3600))
        degree, minute, second = map(float, fields[3].split(".", 2))
        dec = np.deg2rad(np.sign(degree) * (abs(degree) + minute / 60 + second / 3600))
        coefficients = list(map(float, fields[5][1:-1].split(";")))
        sources.append((ra, dec, float(fields[4]), coefficients, float(fields[7])))
    return sources


def snapshot(paths):
    stats = {str(p): [p.stat().st_size, p.stat().st_mtime_ns] for p in paths}
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return stats, status


def main():
    oracle_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    if not str(out).startswith("outputs/") or out.exists():
        raise SystemExit("run directory must be new and beneath outputs/")
    out.mkdir(parents=True)
    inputs = [oracle_dir / "oracle.npz", oracle_dir / "receipt.json", CATALOGUE]
    before = snapshot(inputs)
    with np.load(oracle_dir / "oracle.npz") as z:
        oracle = {k: z[k] for k in z.files}
    uvw, freq = oracle["uvw"], oracle["frequency"]
    result = {"protocol": "research/core-phase3c-a.md", "sets": {}, "passed": {}}
    rust = {}
    for name in SETS:
        args = components(oracle, name)
        started = time.perf_counter()
        vis, spec = core.predict_components(uvw, freq, *args, spectra=True)
        seconds = time.perf_counter() - started
        rust[name] = (vis, spec)
        limit = bound(oracle[f"{name}_spectra"])
        diff = np.abs(vis - oracle[f"{name}_vis"])
        scaled = diff / limit[None, :]
        spec_rel = np.abs(spec - oracle[f"{name}_spectra"]) / np.maximum(
            np.abs(oracle[f"{name}_spectra"]), 1e-300
        )
        result["sets"][name] = {
            "components": len(args[2]),
            "max_abs_diff_jy": float(diff.max()),
            "max_diff_over_bound": float(scaled.max()),
            "max_spectra_rel": float(spec_rel.max()),
            "rust_seconds": seconds,
        }
        result["passed"][f"1_africanus_{name}"] = bool(scaled.max() <= 1.0)
        result["passed"][f"3_spectra_{name}"] = bool(spec_rel.max() <= SPECTRA_TOL)
    # Criterion 2, response set: per-source NumPy templates times spectra.
    # Fixed after the frozen run -01, which passed the signal-stage default
    # source list here instead of the response sources the oracle used.
    templates = spatial_templates(uvw, freq, RESPONSE_SOURCES)
    _, spec = rust["response"]
    per_source = []
    for s in range(len(templates)):
        args = [a[s : s + 1] for a in components(oracle, "response")]
        single = core.predict_components(uvw, freq, *args)
        expected = templates[s] * spec[s][None, :]
        per_source.append(
            float(np.max(np.abs(single - expected) / bound(spec[s : s + 1])))
        )
    result["sets"]["response"]["numpy_template_max_over_bound"] = max(per_source)
    result["passed"]["2_numpy_response"] = bool(max(per_source) <= 1.0)
    # Criterion 2, catalogue set: point_catalog_predict on three cross rows.
    sources = parse_catalogue(CATALOGUE)
    radec = np.array([s[:2] for s in sources])
    lm_ok = np.allclose(
        np.stack(
            (
                np.cos(radec[:, 1]) * np.sin(radec[:, 0] - oracle["phase"][0]),
                np.sin(radec[:, 1]) * np.cos(oracle["phase"][1])
                - np.cos(radec[:, 1])
                * np.sin(oracle["phase"][1])
                * np.cos(radec[:, 0] - oracle["phase"][0]),
            ),
            axis=1,
        ),
        oracle["catalogue_lm"],
        rtol=0,
        atol=0,
    )
    rows = np.array([0, len(uvw) // 2, len(uvw) - 1])
    numpy_vis = point_catalog_predict(
        uvw[rows],
        radec,
        oracle["phase"],
        freq,
        np.array([s[2] for s in sources]),
        np.array([s[3] for s in sources]),
        np.array([s[4] for s in sources]),
    )
    cat_scaled = (
        np.abs(rust["catalogue"][0][rows] - numpy_vis)
        / bound(rust["catalogue"][1])[None, :]
    )
    result["sets"]["catalogue"]["numpy_three_rows_max_over_bound"] = float(
        cat_scaled.max()
    )
    result["sets"]["catalogue"]["host_parsed_lm_equals_oracle"] = bool(lm_ok)
    result["passed"]["2_numpy_catalogue"] = bool(cat_scaled.max() <= 1.0)
    after = snapshot(inputs)
    result["side_effects"] = {
        "inputs_unchanged": before[0] == after[0],
        "git_status_unchanged": before[1] == after[1],
        "run_dir_empty_before_receipt": sorted(p.name for p in out.iterdir()) == [],
    }
    result["passed"]["4_no_side_effects"] = all(result["side_effects"].values())
    result["all_passed"] = all(result["passed"].values())
    result["oracle_receipt"] = json.loads((oracle_dir / "receipt.json").read_text())
    result["oracle_sha256"] = sha256(
        (oracle_dir / "oracle.npz").read_bytes()
    ).hexdigest()
    result["library_sha256"] = sha256(core.library_path().read_bytes()).hexdigest()
    (out / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({"all_passed": result["all_passed"], **result["passed"]}))
    print(json.dumps(result["sets"]))
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
