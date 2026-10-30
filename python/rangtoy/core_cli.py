"""Core-native command line and Stimela cab functions for the phase 3 stages.

One entry point for the stages that run on the Rust core with no Measurement
Set, no container and no solver subprocess (research/core-h-recipes.md):

    python -m rangtoy.core_cli injections <run-dir> <prepared-dir> [--seed 19]
        [--strengths 3 10] [--patterns narrowband time-burst antenna-local]
        [--iterations 50]
    python -m rangtoy.core_cli actions <run-dir> <prepared-dir> [--seed 29]
        [--action-count 16] [--iterations 50]
    python -m rangtoy.core_cli prospective <run-dir> <inputs-dir> [--iterations 50]
    python -m rangtoy.core_cli signal <run-dir> <inputs-dir> <uvw-dir> [--iterations 50]
    python -m rangtoy.core_cli trend-mirror <mirror-dir> <source-dir>
    python -m rangtoy.core_cli trend <run-dir> <mirror-dir>
    python -m rangtoy.core_cli environment <run-dir>
    python -m rangtoy.core_cli compare <stage> <result> <oracle> <receipt>
        [--posthoc-slope-scale]

Each stage calls the phase 3 driver unchanged (`core_injections`,
`core_actions`, `core_prospective`, `core_signal`; the trend mirror makes the
seven core baseline solves of `examples/build_core_trend_mirror.py`, and the
trend ablation is the frozen `flagging_trend.run`) and writes the side-effect
audit of `examples/run_core_campaign.py` as `side-effects.json`. `compare`
runs the stage's phase 3 comparator script unchanged and records its SHA256.
`environment` records whether the frozen solver package is present in any form.
The functions are also the commands of the python-flavour cabs in
`recipes/core-*.yaml`.
"""

import argparse
import importlib.metadata
import importlib.util
import json
import os
import runpy
import shutil
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

from . import core, core_actions, core_injections, core_prospective, core_signal
from .core_trend import run as trend_run
from .core_workflow import core_solve
from .flagging_equivariance import CASES
from .flagging_injections import PATTERNS
from .flagging_workflow import load_state

ROOT = Path(__file__).resolve().parents[2]
COMPARATORS = {
    "injections": "compare_core_injections.py",
    "actions": "compare_core_actions.py",
    "prospective": "compare_core_prospective.py",
    "signal": "compare_core_signal.py",
    "trend": "compare_core_trend.py",
    "imaging": "compare_core_imaging.py",
    "campaign": "check_luno_campaign.py",
}
TREND_GRID = (2, 32)
TREND_ITERATIONS = 50


def _snapshot(inputs):
    inputs = Path(inputs)
    return {
        p.relative_to(inputs).as_posix(): [p.stat().st_size, p.stat().st_mtime_ns]
        for p in sorted(inputs.rglob("*"))
        if p.is_file() and p.name != "table.lock"
    }


def _git_status():
    try:
        return subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, default=str) + "\n")


def _audited(stage, run_dir, inputs, action):
    """Run `action` and write the side-effect audit next to its result."""
    run_dir, inputs = Path(run_dir), [Path(p) for p in inputs]
    before = [_snapshot(p) for p in inputs]
    status_before = _git_status()
    started = time.perf_counter()
    result = action()
    seconds = time.perf_counter() - started
    after = [_snapshot(p) for p in inputs]
    written = sorted(p.name for p in run_dir.iterdir())
    audit = {
        "stage": stage,
        "inputs": [str(p) for p in inputs],
        "input_files_checked": sum(len(b) for b in before),
        "inputs_unchanged": all(b == a for b, a in zip(before, after)),
        "git_status_unchanged": status_before == _git_status(),
        "run_dir_files": written,
        "only_result_written": written == ["result.json"],
        "seconds": seconds,
    }
    _write_json(run_dir / "side-effects.json", audit)
    summary = {
        "stage": stage,
        "seconds": seconds,
        "seconds_total": result.get("seconds_total"),
        "solves": result.get("actual_QC_solves", result.get("solves")),
        **{k: v for k, v in audit.items() if k not in ("stage", "run_dir_files")},
    }
    print(json.dumps(summary))
    return summary


def injections(
    run_dir,
    prepared_dir,
    seed=19,
    strengths=(3.0, 10.0),
    patterns=PATTERNS,
    iterations=50,
):
    """Injection campaign on the core (research/core-phase3.md)."""
    return _audited(
        "injections",
        run_dir,
        [prepared_dir],
        lambda: core_injections.run(
            run_dir,
            prepared_dir,
            seed=int(seed),
            strengths=tuple(float(s) for s in strengths),
            patterns=tuple(patterns),
            iterations=int(iterations),
        ),
    )


def actions(run_dir, prepared_dir, seed=29, action_count=16, iterations=50):
    """Patch-removal actions stage on the core (research/core-phase3-actions.md)."""
    return _audited(
        "actions",
        run_dir,
        [prepared_dir],
        lambda: core_actions.run(
            run_dir,
            prepared_dir,
            seed=int(seed),
            action_count=int(action_count),
            iterations=int(iterations),
        ),
    )


def prospective(run_dir, inputs_dir, iterations=50):
    """Prospective track on the core (research/core-phase3b.md)."""
    return _audited(
        "prospective",
        run_dir,
        [inputs_dir],
        lambda: core_prospective.run(run_dir, inputs_dir, iterations=int(iterations)),
    )


def signal(run_dir, inputs_dir, uvw_dir, iterations=50):
    """Signal track on the core (research/core-phase3c-b.md)."""
    return _audited(
        "signal",
        run_dir,
        [inputs_dir, uvw_dir],
        lambda: core_signal.run(
            run_dir, inputs_dir, uvw_dir, iterations=int(iterations), ported=True
        ),
    )


def build_trend_mirror(source_dir, mirror_dir):
    """Core-solved mirror of the concurrent suite (research/core-phase3-trend.md).

    The seven baselines of `examples/build_core_trend_mirror.py`: `state.npz`
    and `manifest.json` copied byte for byte, `trials/baseline/diagnostics.npz`
    and `metrics.json` from `core_solve`, and `mirror-receipt.json` with the
    phase 3 criterion 1 comparison against the archived saved baselines.
    """
    source, mirror = Path(source_dir), Path(mirror_dir)
    if mirror.exists():
        raise FileExistsError(f"mirror directory exists: {mirror}")
    started = time.perf_counter()
    receipt = {"source": str(source), "cases": {}}
    for case in CASES:
        src = source / "experiments" / case
        dst = mirror / "experiments" / case
        (dst / "trials/baseline").mkdir(parents=True)
        for name in ("state.npz", "manifest.json"):
            shutil.copy2(src / name, dst / name)
        manifest = json.loads((dst / "manifest.json").read_text())
        if manifest["split_gain_intervals"] != list(TREND_GRID):
            raise ValueError("frozen 2x32 grid required")
        state = load_state(dst)
        metrics, _, _, _, diagnostics = core_solve(
            state,
            np.zeros_like(state["train"]),
            *TREND_GRID,
            TREND_ITERATIONS,
            trial="baseline",
        )
        np.savez_compressed(dst / "trials/baseline/diagnostics.npz", **diagnostics)
        solver = metrics.pop("solver")
        (dst / "trials/baseline/metrics.json").write_text(
            json.dumps(metrics, indent=2) + "\n"
        )
        with np.load(src / "trials/baseline/diagnostics.npz") as saved:
            qc_gains, qc_valid = saved["gains"], saved["gain_valid"]
        valid = diagnostics["gain_valid"]
        receipt["cases"][case] = {
            "state_sha256_equal": sha256((src / "state.npz").read_bytes()).hexdigest()
            == sha256((dst / "state.npz").read_bytes()).hexdigest(),
            "gain_valid_equal": bool(np.array_equal(valid, qc_valid)),
            "max_abs_gain_diff": float(
                np.max(np.abs(diagnostics["gains"] - qc_gains)[qc_valid])
            ),
            "solver": solver,
            "seconds": metrics["seconds"],
        }
    receipt["solves"] = len(CASES)
    receipt["seconds_total"] = time.perf_counter() - started
    receipt["criterion_1_pass"] = all(
        c["state_sha256_equal"]
        and c["gain_valid_equal"]
        and c["max_abs_gain_diff"] <= 1e-6
        for c in receipt["cases"].values()
    )
    _write_json(mirror / "mirror-receipt.json", receipt)
    return receipt


def trend_mirror(mirror_dir, source_dir):
    """Build the trend mirror with the side-effect audit."""
    return _audited(
        "trend-mirror",
        mirror_dir,
        [source_dir],
        lambda: build_trend_mirror(source_dir, mirror_dir),
    )


def trend(run_dir, mirror_dir):
    """The frozen `flagging_trend.run`, unedited, on a core-solved mirror."""
    return _audited(
        "trend", run_dir, [mirror_dir], lambda: trend_run(run_dir, mirror_dir)
    )


def _rangtoy_modules():
    modules = {}
    for name, module in sorted(sys.modules.items()):
        file = getattr(module, "__file__", None)
        if name.startswith("rangtoy") and file:
            # The extension module rangtoy._core is a binary
            # (research/core-j-packaging.md): recorded, not read as text.
            binary = Path(file).suffix != ".py"
            text = "" if binary else Path(file).read_text().lower()
            modules[name] = {
                "file": str(Path(file).relative_to(ROOT))
                if Path(file).is_relative_to(ROOT)
                else file,
                "quartical_references": text.count("quartical"),
            }
            if binary:
                modules[name]["binary"] = True
    return modules


def environment(run_dir):
    """Record the interpreter and whether QuartiCal is present in any form."""
    distributions = sorted(
        f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions()
    )
    modules = _rangtoy_modules()
    record = {
        "python": sys.version,
        "executable": sys.executable,
        "rang_core_lib": os.environ.get("RANG_CORE_LIB"),
        "rang_core_backend": core.backend_name(),
        "rang_core_library": str(core.library_path()),
        "rang_toy_lib": os.environ.get("RANG_TOY_LIB"),
        "distributions": distributions,
        "quartical_distribution_installed": any(
            d.lower().startswith("quartical==") for d in distributions
        ),
        "quartical_importable": importlib.util.find_spec("quartical") is not None,
        "quartical_modules_loaded": sorted(
            m for m in sys.modules if m.split(".")[0] == "quartical"
        ),
        "goquartical_on_path": shutil.which("goquartical"),
        "rangtoy_modules_imported": modules,
        "modules_with_quartical_references": sorted(
            m for m, v in modules.items() if v["quartical_references"]
        ),
    }
    _write_json(Path(run_dir) / "environment.json", record)
    print(
        json.dumps(
            {
                k: record[k]
                for k in (
                    "quartical_distribution_installed",
                    "quartical_importable",
                    "goquartical_on_path",
                    "modules_with_quartical_references",
                )
            }
        )
    )
    return record


def imaging(run_dir, archive_dir=None, export_dir=None):
    """The imaging track replay on the core (task I, `rangtoy.core_imaging`)."""
    from . import core_imaging

    return core_imaging.run(
        run_dir,
        archive_dir=archive_dir or core_imaging.DEFAULT_ARCHIVE,
        export_dir=export_dir or core_imaging.DEFAULT_EXPORT,
    )


def campaign(run_dir, precondition=None, workers=8):
    """The LUNO campaign on the core (task K, `rangtoy.core_campaign`)."""
    from . import core_campaign

    result = core_campaign.run(run_dir, workers=workers, precondition_dir=precondition)
    environment(run_dir)
    return result


def compare(stage, result, oracle, receipt, posthoc_slope_scale=False):
    """Run the stage's phase 3 comparator script unchanged; record its SHA256.

    Exits nonzero, as the script does, when the comparison fails.
    """
    script = ROOT / "examples" / COMPARATORS[stage]
    argv = [str(script), str(result), str(oracle), str(receipt)]
    if posthoc_slope_scale:
        argv.append("--posthoc-slope-scale")
    saved = sys.argv
    sys.argv = argv
    code = 0
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.argv = saved
    report = json.loads(Path(receipt).read_text())
    report["comparator"] = {
        "script": script.relative_to(ROOT).as_posix(),
        "sha256": sha256(script.read_bytes()).hexdigest(),
        "exit": code,
        "posthoc_slope_scale": bool(posthoc_slope_scale),
    }
    _write_json(receipt, report)
    if code:
        raise SystemExit(code)
    return report["comparator"]


def _parser():
    parser = argparse.ArgumentParser(
        prog="python -m rangtoy.core_cli",
        description="Phase 3 stages on the Rust core, without the frozen solver.",
    )
    sub = parser.add_subparsers(dest="stage", required=True)

    p = sub.add_parser("injections", help="injection campaign")
    p.add_argument("run_dir")
    p.add_argument("prepared_dir")
    p.add_argument("--seed", type=int, default=19)
    p.add_argument("--strengths", type=float, nargs="+", default=[3.0, 10.0])
    p.add_argument("--patterns", nargs="+", default=list(PATTERNS))
    p.add_argument("--iterations", type=int, default=50)

    p = sub.add_parser("actions", help="patch-removal actions stage")
    p.add_argument("run_dir")
    p.add_argument("prepared_dir")
    p.add_argument("--seed", type=int, default=29)
    p.add_argument("--action-count", type=int, default=16)
    p.add_argument("--iterations", type=int, default=50)

    p = sub.add_parser("prospective", help="prospective track")
    p.add_argument("run_dir")
    p.add_argument("inputs_dir")
    p.add_argument("--iterations", type=int, default=50)

    p = sub.add_parser("signal", help="signal track")
    p.add_argument("run_dir")
    p.add_argument("inputs_dir")
    p.add_argument("uvw_dir")
    p.add_argument("--iterations", type=int, default=50)

    p = sub.add_parser("trend-mirror", help="core-solved mirror for the trend track")
    p.add_argument("mirror_dir")
    p.add_argument("source_dir")

    p = sub.add_parser("trend", help="frozen trend ablation on a mirror")
    p.add_argument("run_dir")
    p.add_argument("mirror_dir")

    p = sub.add_parser("imaging", help="imaging track replay")
    p.add_argument("run_dir")
    p.add_argument("--archive-dir")
    p.add_argument("--export-dir")

    p = sub.add_parser("campaign", help="LUNO campaign on the core")
    p.add_argument("run_dir")
    p.add_argument("--precondition")
    p.add_argument("--workers", type=int, default=8)

    p = sub.add_parser("environment", help="record the environment")
    p.add_argument("run_dir")

    p = sub.add_parser("compare", help="run a phase 3 comparator")
    p.add_argument("compare_stage", choices=sorted(COMPARATORS))
    p.add_argument("result")
    p.add_argument("oracle")
    p.add_argument("receipt")
    p.add_argument("--posthoc-slope-scale", action="store_true")
    return parser


COMMANDS = {
    "injections": injections,
    "actions": actions,
    "prospective": prospective,
    "signal": signal,
    "trend-mirror": trend_mirror,
    "trend": trend,
    "environment": environment,
    "imaging": imaging,
    "campaign": campaign,
}


def main(argv=None):
    args = vars(_parser().parse_args(argv))
    stage = args.pop("stage")
    if stage == "compare":
        return compare(
            args["compare_stage"],
            args["result"],
            args["oracle"],
            args["receipt"],
            posthoc_slope_scale=args["posthoc_slope_scale"],
        )
    return COMMANDS[stage](**args)


if __name__ == "__main__":
    main()
