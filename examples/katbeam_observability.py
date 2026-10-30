"""Ablate chromatic shape, squint and profile in a holography-informed beam."""

import json
import sys
from hashlib import sha256
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from rang import toy_output
from rang.beams import beam_table, load_katbeam, make_beam_predictor
from rang.observability import sky_locked_information
from rang.pointing import Observation, component_list


def main():
    jax.config.update("jax_enable_x64", True)
    fixture_bytes = toy_output("--pointing-full-reference").encode()
    fixture = json.loads(fixture_bytes)
    r, s = np.asarray(fixture["rows"]), np.asarray(fixture["sources"])
    obs = Observation(
        jnp.asarray(r[:, :3]),
        jnp.asarray(r[:, 3]),
        *(jnp.asarray(r[:, i], dtype=int) for i in (4, 5, 6)),
        jnp.asarray(r[:, 7]),
    )
    sky = component_list(s[:, 0], s[:, 1], s[:, 2], s[:, 3])
    results = []
    for pol in ("H", "V"):
        table, metadata = load_katbeam(pol)
        width = np.asarray(table.fwhm_rad)
        geometric = np.sqrt(np.prod(width, axis=1))
        reference_width = np.array(
            [np.interp(1.284e9, table.frequency_hz, width[:, i]) for i in range(2)]
        )
        ratio = reference_width[1] / reference_width[0]
        no_squint = beam_table(
            table.frequency_hz, np.zeros_like(table.squint_rad), width
        )
        fixed_ratio = beam_table(
            table.frequency_hz,
            np.zeros_like(table.squint_rad),
            geometric[:, None] * np.array([1 / np.sqrt(ratio), np.sqrt(ratio)]),
        )
        circular = beam_table(
            table.frequency_hz,
            np.zeros_like(table.squint_rad),
            np.repeat(geometric[:, None], 2, axis=1),
        )
        cases = [
            ("native", table, "cosine", True),
            ("no_squint", no_squint, "cosine", True),
            ("fixed_axis_ratio", fixed_ratio, "cosine", True),
            ("chromatic_gaussian", no_squint, "gaussian", True),
            ("fixed_shape_gaussian", fixed_ratio, "gaussian", True),
            ("circular_cosine", circular, "cosine", True),
            ("native_without_rotation", table, "cosine", False),
        ]
        for name, selected, profile, rotate in cases:
            selected_obs = (
                obs
                if rotate
                else obs._replace(beam_angle_rad=jnp.zeros_like(obs.beam_angle_rad))
            )
            predictor = make_beam_predictor(
                selected, profile, dict(metadata, ablation=name)
            )
            result = sky_locked_information(
                sky,
                selected_obs,
                8,
                noise_jy=0.001,
                gain_model="per_time_channel",
                differential_pointing=True,
                common_time_variation=True,
                predictor=predictor,
                log_flux_prior_covariance=0.01**2 * np.eye(16)
                if name == "native"
                else None,
            )
            result["beam_rotation"] = rotate
            result["fixed_reference_axis_ratio"] = float(ratio)
            results.append(result)
            print(
                json.dumps(
                    {
                        "polarization": pol,
                        "case": name,
                        "modes": result["observable_common_modes"],
                        "data_sigma_arcsec": result["local_crlb_arcsec"],
                        "constrained_sigma_arcsec": result.get(
                            "information_budget", {}
                        ).get("local_sigma_arcsec"),
                    }
                ),
                flush=True,
            )
    output = ROOT / "outputs/katbeam-observability"
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "fixture_sha256": sha256(fixture_bytes).hexdigest(),
        "complex_rows": len(r),
        "jax_version": jax.__version__,
        "numpy_version": np.__version__,
        "results": results,
    }
    (output / "results.json").write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
