"""Finite Gaussian gauge and non-Gaussian beam identifiability controls."""

import hashlib
import json
import platform
import sys
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from rang import core, toy_output
from rang.gauge import gaussian_gauge, predict_channels
from rang.observability import sky_locked_information
from rang.pointing import Observation, component_list


def gauge_svg(orbit):
    """Two equivalent trajectories and the roundoff-sized prediction difference."""
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="620" viewBox="0 0 1000 620" role="img" aria-labelledby="title desc">',
        '<title id="title">Different pointing trajectories, identical Gaussian-beam visibilities</title>',
        '<desc id="desc">Two smooth models for toy antenna m000 differ in both pointing coordinates. Across a continuous gauge sweep their maximum visibility difference remains at floating-point roundoff.</desc>',
        '<rect width="1000" height="620" fill="white"/>',
        '<g font-family="sans-serif" fill="#172b4d">',
        '<text x="50" y="32" font-size="22">Different pointing. Identical predicted data.</text>',
        '<text x="50" y="55" font-size="13">Rotating elliptical Gaussian beam · eight-antenna toy · not two fitted estimates</text>',
    ]

    def panel(
        left, top, width, height, xvalues, curves, ymin, ymax, title, yticks, xticks
    ):
        parts.append(f'<text x="{left}" y="{top - 12}" font-size="15">{title}</text>')
        for value in yticks:
            y = top + height * (ymax - value) / (ymax - ymin)
            parts.append(f'<path d="M {left} {y} h {width}" stroke="#dce3ed"/>')
            parts.append(
                f'<text x="{left - 8}" y="{y + 4}" text-anchor="end" font-size="11">{value:g}</text>'
            )
        for value, label in xticks:
            x = left + width * (value - xvalues[0]) / (xvalues[-1] - xvalues[0])
            parts.append(
                f'<text x="{x}" y="{top + height + 20}" text-anchor="middle" font-size="11">{label}</text>'
            )
        for values, color, dash in curves:
            points = " ".join(
                f"{left + width * (x - xvalues[0]) / (xvalues[-1] - xvalues[0]):.3f},{top + height * (ymax - y) / (ymax - ymin):.3f}"
                for x, y in zip(xvalues, values, strict=True)
            )
            parts.append(
                f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5" stroke-dasharray="{dash}"/>'
            )

    before, after = (
        np.asarray(orbit["antenna0_before_arcsec"]),
        np.asarray(orbit["antenna0_after_arcsec"]),
    )
    limit = 10 * np.ceil(max(np.max(np.abs(before)), np.max(np.abs(after))) / 10)
    for axis in range(2):
        panel(
            65 + axis * 485,
            105,
            390,
            190,
            orbit["hours"],
            [(before[:, axis], "#247a92", "none"), (after[:, axis], "#b05a24", "7 4")],
            -limit,
            limit,
            f"m000: {'x' if axis == 0 else 'y'} pointing (arcsec)",
            [-limit, 0, limit],
            [(0, "0 h"), (3, "3 h"), (6, "6 h")],
        )
    parts.append(
        '<text x="65" y="342" font-size="13" fill="#247a92">Solid: model A</text>'
    )
    parts.append(
        '<text x="220" y="342" font-size="13" fill="#b05a24">Dashed: gauge-equivalent model B; sky and gains also change</text>'
    )
    differences = np.maximum(orbit["max_visibility_difference_jy"], 1e-18)
    panel(
        65,
        402,
        875,
        135,
        orbit["amplitude"],
        [(np.log10(differences), "#247a92", "none")],
        -18,
        -14,
        "Maximum complex visibility difference: log10(Jy)",
        [-18, -16, -14],
        [(-1, "-1"), (0, "0"), (1, "1")],
    )
    parts.append(
        '<text x="400" y="579" font-size="12">Gauge amplitude (dimensionless)</text>'
    )
    parts.append(
        '<text x="65" y="607" font-size="11">Zero difference at amplitude 0 is displayed at 10^-18 Jy. Numerical noise is not physical information.</text>'
    )
    return "\n".join(parts + ["</g></svg>"]) + "\n"


def main():
    jax.config.update("jax_enable_x64", True)
    binary = core.library_path()
    fixture_bytes = toy_output("--pointing-full-reference").encode()
    fixture = json.loads(fixture_bytes)
    rows, sources = np.asarray(fixture["rows"]), np.asarray(fixture["sources"])
    sky = component_list(sources[:, 0], sources[:, 1], sources[:, 2], sources[:, 3])
    obs = Observation(
        jnp.asarray(rows[:, :3]),
        jnp.asarray(rows[:, 3]),
        *(jnp.asarray(rows[:, i], dtype=int) for i in (4, 5, 6)),
        jnp.asarray(rows[:, 7]),
    )
    rng = np.random.default_rng(61)
    time = np.linspace(0, 2 * np.pi, 24)
    offsets = rng.normal(0, 0.3, (1, 8, 2)) + 0.2 * np.sin(
        time[:, None, None] + rng.uniform(0, 6, (1, 8, 2))
    )
    flux = np.asarray(sky.flux_jy)[None, :] * rng.uniform(0.8, 1.2, (4, 4))
    gains = np.exp(
        rng.normal(0, 0.03, (24, 8, 4)) + 1j * rng.normal(0, 0.1, (24, 8, 4))
    )
    baseline = np.asarray(predict_channels(sky, obs, offsets, flux, gains, 1.1))
    noise = np.random.default_rng(72)
    data = baseline + 0.001 * (
        noise.normal(size=len(rows)) + 1j * noise.normal(size=len(rows))
    )
    orbit = {
        "amplitude": np.linspace(-1, 1, 21).tolist(),
        "max_visibility_difference_jy": [],
        "chi_squared": [],
        "hours": np.linspace(0, 6, 24).tolist(),
        "antenna0_before_arcsec": (60 * offsets[:, 0]).tolist(),
        "noise_seed": 72,
        "noise_jy_per_component": 0.001,
    }
    for amplitude in orbit["amplitude"]:
        changed = gaussian_gauge(
            obs, sky, offsets, flux, gains, amplitude * np.array([0.7, -0.4]), 1.1
        )
        value = np.asarray(
            predict_channels(
                sky,
                obs,
                changed["offsets_arcmin"],
                changed["channel_flux_jy"],
                changed["antenna_gains"],
                1.1,
            )
        )
        orbit["max_visibility_difference_jy"].append(
            float(np.max(np.abs(value - baseline)))
        )
        orbit["chi_squared"].append(float(np.sum(np.abs(value - data) ** 2) / 0.001**2))
    orbit["antenna0_after_arcsec"] = (60 * changed["offsets_arcmin"][:, 0]).tolist()
    finite, audits = [], []
    for ratio in (1.0, 1.1):
        changed = gaussian_gauge(obs, sky, offsets, flux, gains, [0.7, -0.4], ratio)
        for quartic in (0.0, 0.01, 0.1):
            before = np.asarray(
                predict_channels(sky, obs, offsets, flux, gains, ratio, quartic)
            )
            after = np.asarray(
                predict_channels(
                    sky,
                    obs,
                    changed["offsets_arcmin"],
                    changed["channel_flux_jy"],
                    changed["antenna_gains"],
                    ratio,
                    quartic,
                )
            )
            row = {
                "axis_ratio": ratio,
                "quartic": quartic,
                "max_visibility_difference_jy": float(np.max(np.abs(after - before))),
                "rms_difference_jy_per_component": float(
                    np.sqrt(np.mean(np.abs(after - before) ** 2) / 2)
                ),
                "pointing_change_rms_arcsec": float(
                    60 * np.sqrt(np.mean(changed["common_shift_arcmin"] ** 2))
                ),
            }
            finite.append(row)
            print(json.dumps(row), flush=True)
            audit = sky_locked_information(
                sky,
                obs,
                8,
                noise_jy=0.001,
                beam_axis_ratio=ratio,
                beam_quartic=quartic,
                gain_model="per_time_channel",
                differential_pointing=True,
                common_time_variation=True,
            )
            audits.append(audit)
            print(json.dumps(audit), flush=True)
    anchors = []
    for fixed_sources in ([], [0], [0, 1], [0, 1, 2]):
        audit = sky_locked_information(
            sky,
            obs,
            8,
            noise_jy=0.001,
            beam_axis_ratio=1.1,
            gain_model="per_time_channel",
            differential_pointing=True,
            common_time_variation=True,
            fixed_flux_sources=fixed_sources,
        )
        anchors.append(audit)
        print(json.dumps(audit), flush=True)
    result = {
        "provenance": {
            "python": platform.python_version(),
            "jax": jax.__version__,
            "numpy": np.__version__,
            "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
            "rust_binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "source_sha256": {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in [
                    "examples/gaussian_gauge.py",
                    "python/rang/gauge.py",
                    "python/rang/pointing.py",
                    "python/rang/observability.py",
                ]
            },
        },
        "seed": 61,
        "complex_rows": len(rows),
        "shift_parameter_arcmin": [0.7, -0.4],
        "finite_transformations": finite,
        "local_audits": audits,
        "flux_anchor_audits": anchors,
        "gauge_orbit": orbit,
    }
    output = ROOT / "outputs/gaussian-gauge"
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "gauge-orbit.svg").write_text(gauge_svg(orbit))


if __name__ == "__main__":
    main()
