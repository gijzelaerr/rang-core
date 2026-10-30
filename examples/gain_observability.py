"""Audit frequency-dependent gains with complete versus thinned baseline coverage."""

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
    results = []
    for complete in (False, True):
        flag = "--pointing-full-reference" if complete else "--pointing-reference"
        fixture = json.loads(toy_output(flag).encode())
        rows, sources = np.asarray(fixture["rows"]), np.asarray(fixture["sources"])
        sky = component_list(sources[:, 0], sources[:, 1], sources[:, 2], sources[:, 3])
        obs = Observation(
            jnp.asarray(rows[:, :3]),
            jnp.asarray(rows[:, 3]),
            *(jnp.asarray(rows[:, i], dtype=int) for i in (4, 5, 6)),
            jnp.asarray(rows[:, 7]),
        )
        for gains, differential in [
            ("fixed", False),
            ("per_time_channel", False),
            ("per_time_channel", True),
        ]:
            result = sky_locked_information(
                sky,
                obs,
                fixture["antenna_count"],
                noise_jy=0.001,
                beam_axis_ratio=1.1,
                gain_model=gains,
                differential_pointing=differential,
            )
            result["complete_baselines"] = complete
            result["complex_rows"] = len(rows)
            results.append(result)
            print(json.dumps(result), flush=True)
    output = ROOT / "outputs/gain-observability"
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
