"""Compare a core imaging replay with the archived imaging result
(research/core-i-imaging-replay.md).

    python examples/compare_core_imaging.py RESULT ORACLE RECEIPT.json
        [--images CANDIDATE_DIR REFERENCE_DIR]

RESULT is a core replay ``result.json`` (or, for the comparator precondition,
the host reproduction's ``result.json``); ORACLE is
``research/results/gain-tv-next-imaging.json`` (its ``raw_result`` is
compared) or any raw ``result.json``. Fields are compared leaf by leaf under
``rangtoy.core_imaging.classify_replay`` with task A's tolerances. With
``--images`` the dirty and PSF FITS of CANDIDATE_DIR are compared pixel by
pixel with REFERENCE_DIR. Exit status 1 when anything fails.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from rangtoy.core_imaging import compare_replay, pixel_comparison


def load(path):
    payload = json.loads(Path(path).read_text())
    return payload.get("raw_result", payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("result")
    parser.add_argument("oracle")
    parser.add_argument("receipt")
    parser.add_argument("--images", nargs=2, metavar=("CANDIDATE", "REFERENCE"))
    args = parser.parse_args(argv)
    report = compare_replay(load(args.oracle), load(args.result))
    report["result"] = args.result
    report["oracle"] = args.oracle
    passed = report["passed"]
    for cls, stats in sorted(report["classes"].items()):
        print(
            f"{cls:20s} compared {stats['compared']:5d} worst {stats['worst']:.3e}"
            f" at {'/'.join(map(str, stats['worst_path'] or []))}"
        )
    print(f"excluded {report['excluded']} failures {len(report['failures'])}")
    for failure in report["failures"][:20]:
        print("  FAIL", failure)
    if args.images:
        pixels = pixel_comparison(args.images[1], args.images[0])
        report["pixels"] = pixels
        passed &= pixels["passed"]
        for label, job in pixels["jobs"].items():
            for kind in ("dirty", "psf"):
                r = job[kind]
                print(
                    f"{label:28s} {kind:5s} max|d| {r['max_abs_difference']:.3e} "
                    f"rms {r['rms_difference']:.3e} peak {r['reference_peak']:.4g} "
                    f"max|d|/peak {r['max_relative_to_peak']:.3e} "
                    f"central/border rms {r['central_rms_difference']:.2e}/"
                    f"{r['border_rms_difference']:.2e} wcs {r['wcs_equal']}"
                )
        print("pixels", json.dumps(pixels["summary"]), "passed", pixels["passed"])
    report["passed"] = bool(passed)
    Path(args.receipt).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("passed", report["passed"])
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
