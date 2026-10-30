"""Render the task A sensitivity result as Markdown tables for the research file.

Usage: summarize_imaging_sensitivity.py OUTPUT_DIR  (the directory holding
result.json and variants/<name>/result.json written by run_imaging_sensitivity.py)
"""

import json
import sys
from pathlib import Path

from rangtoy.core_sensitivity import FITTED_JOBS


def _e(value, digits=2):
    if value is None:
        return "–"
    return f"{value:.{digits}e}"


def main(argv):
    root = Path(argv[1])
    summary = json.loads((root / "result.json").read_text())
    spread = summary["spread"]
    print(
        "| Variant | kernel | oversampling | w-layers | flux rel. | response abs. | dirty L∞ / peak | dirty L∞ Jy/beam | PSF L∞ | RMS rel. | beam rel. | closures Jy/beam | weights equal | s |"
    )
    print(
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |"
    )
    for name, settings in summary["variants"].items():
        if name == "default":
            print(
                f"| default | {settings['kernel_size']} | {settings['oversampling']} | {settings['w_layers']} "
                f"| 0 | 0 | 0 | 0 | 0 | 0 | 0 | {_e(summary['criterion_3_closures']['default']['omitted'])}, {_e(summary['criterion_3_closures']['default']['complete'])} | – | {summary['seconds_per_variant']['default']:.0f} |"
            )
            continue
        row = spread[name]
        closures = row["closures_jy_per_beam"]
        print(
            f"| {name} | {settings['kernel_size']} | {settings['oversampling']} | {settings['w_layers']} "
            f"| {_e(row['max_relative_flux_change'])} | {_e(row['max_absolute_response_change'])} "
            f"| {_e(row['max_dirty_linf_relative_to_peak'])} | {_e(row['max_dirty_linf_jy_per_beam'])} "
            f"| {_e(row['max_psf_linf'])} | {_e(row['max_offsource_rms_relative_change'])} "
            f"| {_e(row['max_beam_relative_change'])} | {_e(closures['omitted'])}, {_e(closures['complete'])} "
            f"| {'yes' if row['weight_headers_equal_default'] else 'NO'} | {summary['seconds_per_variant'][name]:.0f} |"
        )
    print()
    print("Reference-fit coefficients (mJy) and omitted-total responses per variant:")
    print()
    print(
        "| Variant | compact ref | extended ref | omitted-total compact | omitted-total extended | complete-total compact | complete-total extended |"
    )
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for name in summary["variants"]:
        result = json.loads((root / "variants" / name / "result.json").read_text())
        ref = result["reference_fit"]["coefficients_jy"]
        o = result["jobs"]["omitted-total"]["conditional_response_vs_fixedG0"]
        c = result["jobs"]["complete-total"]["conditional_response_vs_fixedG0"]
        print(
            f"| {name} | {ref[0] * 1e3:.5f} | {ref[1] * 1e3:.5f} | {o[0]:.6f} | {o[1]:.6f} | {c[0]:.6f} | {c[1]:.6f} |"
        )
    print()
    print("Proposed tolerances:")
    print()
    for key, value in summary["proposed_tolerances"].items():
        if isinstance(value, float):
            print(f"- {key}: {_e(value, 3)}")
        elif isinstance(value, dict):
            print(f"- {key}: " + ", ".join(f"{k} {_e(v, 3)}" for k, v in value.items()))
        else:
            print(f"- {key}: {value}")
    print()
    print(f"Fitted jobs: {', '.join(FITTED_JOBS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
