"""Separate visibility information from uncertain external flux constraints."""

import json
import sys
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from rangtoy import toy_output
from rangtoy.observability import sky_locked_information
from rangtoy.pointing import Observation, component_list


def main():
    jax.config.update("jax_enable_x64", True)
    fixture = json.loads(toy_output("--pointing-full-reference").encode())
    rows, sources = np.asarray(fixture["rows"]), np.asarray(fixture["sources"])
    sky = component_list(sources[:, 0], sources[:, 1], sources[:, 2], sources[:, 3])
    obs = Observation(
        jnp.asarray(rows[:, :3]),
        jnp.asarray(rows[:, 3]),
        *(jnp.asarray(rows[:, i], dtype=int) for i in (4, 5, 6)),
        jnp.asarray(rows[:, 7]),
    )
    scenarios = {
        "independent_1pct": 0.01**2 * np.eye(16),
        "independent_5pct": 0.05**2 * np.eye(16),
        "1pct_plus_common_scale_5pct": 0.01**2 * np.eye(16)
        + 0.05**2 * np.ones((16, 16)),
        "1pct_correlated_channels": 0.01**2
        * (0.05 * np.eye(16) + 0.95 * np.kron(np.ones((4, 4)), np.eye(4))),
    }
    results = []
    for quartic in (0.0, 0.1):
        for name, covariance in scenarios.items():
            result = sky_locked_information(
                sky,
                obs,
                8,
                noise_jy=0.001,
                beam_axis_ratio=1.1,
                gain_model="per_time_channel",
                differential_pointing=True,
                common_time_variation=True,
                beam_quartic=quartic,
                log_flux_prior_covariance=covariance,
            )
            result["scenario"] = name
            result["log_flux_prior_covariance"] = covariance.tolist()
            results.append(result)
            print(
                json.dumps(
                    {
                        "scenario": name,
                        "quartic": quartic,
                        "sigma_arcsec": result["information_budget"][
                            "local_sigma_arcsec"
                        ],
                        "data_only_fraction": result["information_budget"][
                            "data_only_fraction_eigenvalues"
                        ],
                    }
                ),
                flush=True,
            )
    output = ROOT / "outputs/information-budget"
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
