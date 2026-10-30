"""Compare dense and blocked information calculations on identical inputs."""

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

import jax
import jax.numpy as jnp
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from rang import toy_output
from rang.beams import load_katbeam, make_beam_predictor
from rang.blocked import audit_blocked_design, prepare_blocked_design
from rang.observability import sky_locked_information
from rang.pointing import Observation, component_list


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    jax.config.update("jax_enable_x64", True)
    f = json.loads(toy_output("--pointing-full-reference").encode())
    r, s = np.asarray(f["rows"]), np.asarray(f["sources"])
    obs = Observation(
        jnp.asarray(r[:, :3]),
        jnp.asarray(r[:, 3]),
        *(jnp.asarray(r[:, i], dtype=int) for i in (4, 5, 6)),
        jnp.asarray(r[:, 7]),
    )
    sky = component_list(s[:, 0], s[:, 1], s[:, 2], s[:, 3])
    table, metadata = load_katbeam()
    predictor = make_beam_predictor(table, metadata=metadata)
    covariance = 0.01**2 * np.eye(16)

    def dense():
        return sky_locked_information(
            sky,
            obs,
            8,
            noise_jy=0.001,
            predictor=predictor,
            gain_model="per_time_channel",
            differential_pointing=True,
            common_time_variation=True,
            log_flux_prior_covariance=covariance,
        )

    def blocked(backend, frequency_blocking=False):
        return audit_blocked_design(
            prepare_blocked_design(
                sky,
                obs,
                8,
                noise_jy=0.001,
                predictor=predictor,
                backend=backend,
                frequency_blocking=frequency_blocking,
            ),
            log_flux_prior_covariance=covariance,
        )

    results = []
    reference = None
    for name, run in [
        ("dense", dense),
        ("blocked_rust", lambda: blocked("rust")),
        ("blocked_numpy", lambda: blocked("numpy")),
        ("frequency_blocked_rust", lambda: blocked("rust", True)),
        ("frequency_blocked_numpy", lambda: blocked("numpy", True)),
    ]:
        run()  # Warm up compilation and shared-library loading, recorded runs follow.
        elapsed = []
        for _ in range(args.repeats):
            start = perf_counter()
            result = run()
            elapsed.append(perf_counter() - start)
        information = np.asarray(result["information_budget"]["total_information"])
        if reference is None:
            reference = information
        row = {
            "method": name,
            "seconds": elapsed,
            "median_seconds": float(np.median(elapsed)),
            "max_information_difference": float(
                np.max(np.abs(information - reference))
            ),
            "data_sigma_arcsec": result["local_crlb_arcsec"],
            "constrained_sigma_arcsec": result["information_budget"][
                "local_sigma_arcsec"
            ],
        }
        results.append(row)
        print(json.dumps(row), flush=True)
    payload = {
        "repeats": args.repeats,
        "warmup_runs_per_method": 1,
        "timing_scope": "Jacobian preparation, nuisance elimination and one prior audit; per-process warmup excluded",
        "results": results,
        "matrix_sizes": {
            "dense_nuisance": [5376, 1934],
            "largest_local_nuisance": [224, 78],
            "frequency_local_gains": [56, 16],
            "compressed_global": [432, 64],
        },
    }
    out = ROOT / "outputs/blocked-benchmark"
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
