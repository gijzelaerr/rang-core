"""Check whether known beam asymmetry breaks a common-pointing/sky ambiguity."""

import json
import sys
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from rang import toy_output
from rang.observability import sky_locked_information
from rang.pointing import Observation, component_list


def main():
    jax.config.update("jax_enable_x64", True)
    fixture = json.loads(toy_output("--pointing-reference").encode())
    rows, sources = np.asarray(fixture["rows"]), np.asarray(fixture["sources"])
    sky = component_list(sources[:, 0], sources[:, 1], sources[:, 2], sources[:, 3])
    obs = Observation(
        jnp.asarray(rows[:, :3]),
        jnp.asarray(rows[:, 3]),
        *(jnp.asarray(rows[:, i], dtype=int) for i in (4, 5, 6)),
        jnp.asarray(rows[:, 7]),
    )
    results = []
    for ratio, rotate in [
        (1, True),
        (1.02, True),
        (1.1, True),
        (1.2, True),
        (1.1, False),
    ]:
        selected = (
            obs
            if rotate
            else obs._replace(beam_angle_rad=jnp.zeros_like(obs.beam_angle_rad))
        )
        row = sky_locked_information(
            sky, selected, 8, noise_jy=0.001, beam_axis_ratio=ratio
        )
        row["beam_rotation"] = rotate
        results.append(row)
    for gain_model in ("constant", "per_time"):
        row = sky_locked_information(
            sky, obs, 8, noise_jy=0.001, beam_axis_ratio=1.1, gain_model=gain_model
        )
        row["beam_rotation"] = True
        results.append(row)
    output = ROOT / "outputs/observability"
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
