"""`rang-core`: one command line for every core stage, comparator and check
(research/p9-cli.md; before task P9, research/core-h-recipes.md).

    rang-core [--receipt PATH | --no-receipt] [--no-pin-threads] STAGE VERB ARGS...
    rang-core STAGE -h          # the verbs of a stage
    rang-core check [--rust | --python | --all]

Stages and verbs (`STAGES`): every stage has `compare` (its comparator) and
most have `run` and `archive`. `compare` of injections, actions, prospective,
signal, trend, imaging, flags, weights, gridder and backends runs the
comparator engine `rang.core_compare` in this process with the arguments
of the frozen `examples/compare_core_<stage>.py`, and prints, writes and
exits exactly as that script does. Verbs of kind "script" run the named
driver in `examples/` unchanged (a checkout is needed); the others call the
package. `rang-core STAGE archive RUN OUT.json` writes a `rang.archive`
(version 1) that every comparator accepts as an oracle.

Every invocation writes a `rang.receipt` (version 2): command, commit,
environment (interpreter, platform, the extension and every thread setting),
inputs and outputs with hashes, timings, exit status and, for `compare`, the
verdict (`check` writes one only with `--receipt PATH`). By default it is
written beside the primary output as `<output>.<verb>.rang-receipt.json`:
beside a stage's run directory for `run` (so the side-effect audit's
`only_result_written` is unaffected), beside the comparator's receipt for
`compare`, which may be inside a run directory; the backends comparator
skips these files when it compares two suites.

Before NumPy, SciPy or JAX is imported, the CLI caps the BLAS and XLA thread
pools as `tests/conftest.py` does (an explicit environment setting wins;
`--no-pin-threads` or `RANG_PIN_THREADS=0` turns the caps off). The Rust
core's `RAYON_NUM_THREADS` is left alone and recorded.

The legacy forms still work: `rang-core injections RUN PREPARED ...` (the
verb `run` is implied), `rang-core trend-mirror MIRROR SOURCE` and
`rang-core compare STAGE RESULT ORACLE RECEIPT [--posthoc-slope-scale]`,
which adds the `comparator` record to the receipt as before. The stage
functions below are also the commands of the python-flavour cabs in
`recipes/core-*.yaml` (signatures unchanged); `environment` records whether
the frozen solver package is present in any form.
"""

import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import runpy
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECEIPT_SCHEMA = "rang.receipt"
# Version 2 (task P12, research/p12-rename.md): environment.rangtoy became
# environment.rang_core when the package was renamed; nothing else changed.
RECEIPT_VERSION = 2
ARCHIVE_SCHEMA = "rang.archive"
ARCHIVE_VERSION = 1
# The cab `compare` (legacy form): stage -> comparator script in examples/.
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
# tests/conftest.py's caps (research/p10-tests.md), applied at CLI entry.
THREAD_CAPS = {
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "XLA_FLAGS": "--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1",
}
THREAD_VARIABLES = (*THREAD_CAPS, "RAYON_NUM_THREADS", "NUMBA_NUM_THREADS")


def pin_threads(environ=None):
    """Apply THREAD_CAPS where unset; return the names this call set."""
    environ = os.environ if environ is None else environ
    pinned = []
    for name, value in THREAD_CAPS.items():
        if name not in environ:
            environ[name] = value
            pinned.append(name)
    return pinned


def __getattr__(name):
    # Heavy imports stay out of module import so that `main` can cap the
    # thread pools before NumPy loads; these names are kept for callers.
    if name == "PATTERNS":
        from .core_injection_model import PATTERNS

        return PATTERNS
    if name == "trend_run":
        from .core_trend import run

        return run
    raise AttributeError(name)


def _snapshot(inputs):
    inputs = Path(inputs)
    return {
        p.relative_to(inputs).as_posix(): [p.stat().st_size, p.stat().st_mtime_ns]
        for p in sorted(inputs.rglob("*"))
        if p.is_file() and p.name != "table.lock"
    }


def _git(*args):
    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _git_status():
    return _git("status", "--porcelain")


def _write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=1, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )


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
        "inputs": [p.as_posix() for p in inputs],
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


# ---------------------------------------------------------------------------
# Stage functions (also the python-flavour cabs of recipes/core-*.yaml).


def injections(
    run_dir,
    prepared_dir,
    seed=19,
    strengths=(3.0, 10.0),
    patterns=None,
    iterations=50,
):
    """Injection campaign on the core (research/core-phase3.md); `patterns`
    defaults to all of `flagging_injections.PATTERNS`."""
    from . import core_injections
    from .core_injection_model import PATTERNS

    patterns = PATTERNS if patterns is None else patterns
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
    from . import core_actions

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
    from . import core_prospective

    return _audited(
        "prospective",
        run_dir,
        [inputs_dir],
        lambda: core_prospective.run(run_dir, inputs_dir, iterations=int(iterations)),
    )


def signal(run_dir, inputs_dir, uvw_dir, iterations=50):
    """Signal track on the core (research/core-phase3c-b.md)."""
    from . import core_signal

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
    import numpy as np

    from .core_cases import CASES
    from .core_state import load_state
    from .core_workflow import core_solve

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
    from .core_trend import run as trend_run

    return _audited(
        "trend", run_dir, [mirror_dir], lambda: trend_run(run_dir, mirror_dir)
    )


def _rang_modules():
    modules = {}
    for name, module in sorted(sys.modules.items()):
        file = getattr(module, "__file__", None)
        if (name == "rang" or name.startswith("rang.")) and file:
            # The extension module rang._core is a binary
            # (research/core-j-packaging.md): recorded, not read as text.
            binary = Path(file).suffix != ".py"
            text = "" if binary else Path(file).read_text(encoding="utf-8").lower()
            modules[name] = {
                "file": Path(file).relative_to(ROOT).as_posix()
                if Path(file).is_relative_to(ROOT)
                else file,
                "quartical_references": text.count("quartical"),
            }
            if binary:
                modules[name]["binary"] = True
    return modules


def environment(run_dir):
    """Record the interpreter and whether QuartiCal is present in any form."""
    from . import core

    distributions = sorted(
        f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions()
    )
    modules = _rang_modules()
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
        "rang_modules_imported": modules,
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


def imaging(run_dir, archive_dir=None, export_dir=None, gridder="wstack"):
    """The imaging track replay on the core (task I, `rang.core_imaging`);
    `gridder="wgrid"` uses the exact gridder (research/df2b-wgrid.md)."""
    from . import core_imaging

    return core_imaging.run(
        run_dir,
        archive_dir=archive_dir or core_imaging.DEFAULT_ARCHIVE,
        export_dir=export_dir or core_imaging.DEFAULT_EXPORT,
        gridder=gridder,
    )


def campaign(run_dir, precondition=None, workers=8):
    """The LUNO campaign on the core (task K, `rang.core_campaign`)."""
    from . import core_campaign

    result = core_campaign.run(run_dir, workers=workers, precondition_dir=precondition)
    environment(run_dir)
    return result


def _run_script(script, argv):
    """Run `examples/<script>` unchanged with `argv`; return its exit status."""
    path = ROOT / "examples" / script
    if not path.is_file():
        raise SystemExit(f"{path.as_posix()} not found: this verb needs a checkout")
    saved = sys.argv
    sys.argv = [str(path), *[str(a) for a in argv]]
    code = 0
    try:
        runpy.run_path(str(path), run_name="__main__")
    except SystemExit as exc:
        if exc.code is None or isinstance(exc.code, int):
            code = exc.code or 0
        else:
            print(exc.code, file=sys.stderr)
            code = 1
    finally:
        sys.argv = saved
    return code


def compare(stage, result, oracle, receipt, posthoc_slope_scale=False):
    """The stage's comparator on (result, oracle), with the record
    `comparator` added to its receipt (the python-flavour cab
    `rang-core-compare`).

    The phase 3 comparators run in `rang.core_compare` (task P9): the
    record keeps the wrapper script's path, names the engine and gives the
    engine module's SHA256. `campaign` runs the K checker script unchanged
    and records that script's SHA256, as before P9. Exits nonzero, as the
    comparator does, when the comparison fails.
    """
    from . import core_compare

    argv = [str(result), str(oracle), str(receipt)]
    if posthoc_slope_scale:
        argv.append("--posthoc-slope-scale")
    script = ROOT / "examples" / COMPARATORS[stage]
    if stage in core_compare.COMPARATORS:
        code = core_compare.main(stage, argv)
        record = {
            "script": script.relative_to(ROOT).as_posix(),
            "engine": "rang.core_compare",
            "sha256": sha256(Path(core_compare.__file__).read_bytes()).hexdigest(),
        }
    else:
        code = _run_script(COMPARATORS[stage], argv)
        record = {
            "script": script.relative_to(ROOT).as_posix(),
            "sha256": sha256(script.read_bytes()).hexdigest(),
        }
    report = json.loads(Path(receipt).read_text(encoding="utf-8"))
    report["comparator"] = {
        **record,
        "exit": code,
        "posthoc_slope_scale": bool(posthoc_slope_scale),
    }
    _write_json(receipt, report)
    if code:
        raise SystemExit(code)
    return report["comparator"]


def archive(stage, run_dir, out, status=None, comparisons=()):
    """Write a `rang.archive` (version 1) of a run directory.

    `result` is the run's `result.json`; the run's `side-effects.json`,
    `environment.json` and `receipt.json` and the CLI receipts beside the
    run directory are kept when present, and every comparator receipt named
    in `comparisons` is stored under its file name. The comparators accept
    the file as an oracle (`core_compare.unwrap`). Never overwrites.
    """
    run_dir, out = Path(run_dir), Path(out)
    if out.exists():
        raise SystemExit(f"{out.as_posix()} exists; an archive is never overwritten")
    result_path = run_dir / "result.json"
    payload = {
        "schema": ARCHIVE_SCHEMA,
        "version": ARCHIVE_VERSION,
        "stage": stage,
        "status": status,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": _commit(),
        "run_dir": run_dir.as_posix(),
        "result_sha256": _file_sha256(result_path),
        "result": json.loads(result_path.read_text(encoding="utf-8")),
        "run_files": {},
        "comparisons": {},
    }
    for name in ("side-effects.json", "environment.json", "receipt.json"):
        if (run_dir / name).is_file():
            payload["run_files"][name] = json.loads(
                (run_dir / name).read_text(encoding="utf-8")
            )
    for path in sorted(run_dir.parent.glob(f"{run_dir.name}.*.rang-receipt.json")):
        payload["run_files"][path.name] = json.loads(path.read_text(encoding="utf-8"))
    for path in map(Path, comparisons):
        payload["comparisons"][path.name] = json.loads(path.read_text(encoding="utf-8"))
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_json(out, payload)
    print(json.dumps({"archive": out.as_posix(), "stage": stage, "status": status}))
    return payload


# ---------------------------------------------------------------------------
# The receipt (rang.receipt version 2).


def _commit():
    """HEAD and whether tracked files differ from it (untracked files such as
    a worktree's `outputs` link do not make a tree dirty)."""
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=no")
    return {
        "head": head.strip() if head else None,
        "dirty": bool(status.strip()) if status is not None else None,
    }


def _file_sha256(path):
    digest = sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _path_record(path, content):
    """A path as a receipt entry: a file by its content SHA256; a directory
    by a SHA256 over the POSIX relative path and either the content SHA256
    (`tree_sha256`, with `content`) or the size and mtime (`listing_sha256`)
    of every file, sorted by path."""
    path = Path(path)
    record = {"path": path.as_posix()}
    if path.is_file():
        record.update(kind="file", bytes=path.stat().st_size, sha256=_file_sha256(path))
        return record
    files = sorted(
        (p for p in path.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(path).as_posix(),
    )
    digest = sha256()
    for p in files:
        digest.update(p.relative_to(path).as_posix().encode())
        if content:
            digest.update(_file_sha256(p).encode())
        else:
            stat = p.stat()
            digest.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode())
    record.update(
        kind="directory",
        files=len(files),
        bytes=sum(p.stat().st_size for p in files),
    )
    record["tree_sha256" if content else "listing_sha256"] = digest.hexdigest()
    return record


def _extension():
    try:
        spec = importlib.util.find_spec("rang._core")
    except (ImportError, ValueError):
        spec = None
    if spec is None or not spec.origin:
        return None
    origin = Path(spec.origin)
    return {"path": origin.as_posix(), "sha256": _file_sha256(origin)}


def _environment_record(pinned):
    try:
        version = importlib.metadata.version("rang-core")
    except importlib.metadata.PackageNotFoundError:
        version = None
    return {
        "python": sys.version,
        "executable": Path(sys.executable).as_posix(),
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "rang_core": version,
        "extension": _extension(),
        "threads": {name: os.environ.get(name) for name in THREAD_VARIABLES},
        "threads_pinned_by_cli": pinned,
    }


class Receipt:
    """Snapshot a command's path arguments, then write its receipt.

    An argument that names an existing path before the command is an input
    (recorded by `listing_sha256`, cheap for large trees); one that exists
    only afterwards is an output (content hashes); an input that changed is
    also listed as an output with `modified`.
    """

    def __init__(self, command, stage, verb, paths, pinned):
        self.command, self.stage, self.verb = command, stage, verb
        self.pinned = pinned
        self.paths = [str(a) for a in paths if a and not str(a).startswith("-")]
        self.before = {
            p: _path_record(p, content=False) for p in self.paths if Path(p).exists()
        }
        self.started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.clock = time.perf_counter()

    def record(self, exit_code, verdict=None):
        from . import rusage

        wall = time.perf_counter() - self.clock
        inputs, outputs = [], []
        for p in dict.fromkeys(self.paths):
            if not Path(p).exists():
                continue
            if p not in self.before:
                outputs.append(_path_record(p, content=True))
                continue
            inputs.append(self.before[p])
            if _path_record(p, content=False) != self.before[p]:
                outputs.append({**_path_record(p, content=True), "modified": True})
        return {
            "schema": RECEIPT_SCHEMA,
            "version": RECEIPT_VERSION,
            "command": self.command,
            "stage": self.stage,
            "verb": self.verb,
            "started_utc": self.started,
            "commit": _commit(),
            "environment": _environment_record(self.pinned),
            "inputs": inputs,
            "outputs": outputs,
            "timings": {
                "wall_seconds": wall,
                "cpu_seconds": rusage.cpu_seconds(),
                "peak_rss_mb": rusage.peak_rss_mb(),
            },
            "exit": exit_code,
            "verdict": verdict,
        }

    def write(self, path, exit_code, verdict=None):
        receipt = self.record(exit_code, verdict)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(path, receipt)
        print(f"rang-core: receipt {path.as_posix()}", file=sys.stderr)
        return receipt


def default_receipt(primary, verb):
    """`<primary>.<verb>.rang-receipt.json` beside the primary output (a
    directory, or a file without its suffix): beside, not inside, a run
    directory that the command creates."""
    primary = Path(primary)
    stem = primary.stem if primary.suffix and not primary.is_dir() else primary.name
    return primary.parent / f"{stem}.{verb}.rang-receipt.json"


# ---------------------------------------------------------------------------
# The stage table.


def _positional(argv):
    return [a for a in argv if not a.startswith("-")]


def _first(argv):
    return _positional(argv)[0]


def _last(argv):
    return _positional(argv)[-1]


def _third(argv):
    return _positional(argv)[2]


def _function(function, configure):
    """A verb that calls a stage function with argparse-parsed arguments."""
    return {"kind": "function", "function": function, "configure": configure}


def _engine(name, primary):
    """`compare` through `rang.core_compare` (the script's arguments)."""
    return {"kind": "engine", "name": name, "primary": primary}


def _script(script, primary=_last, note=None):
    """A driver in examples/ run unchanged (the script's arguments)."""
    return {"kind": "script", "script": script, "primary": primary, "note": note}


def _configure_injections(p):
    from .core_injection_model import PATTERNS

    p.add_argument("run_dir")
    p.add_argument("prepared_dir")
    p.add_argument("--seed", type=int, default=19)
    p.add_argument("--strengths", type=float, nargs="+", default=[3.0, 10.0])
    p.add_argument("--patterns", nargs="+", default=list(PATTERNS))
    p.add_argument("--iterations", type=int, default=50)


def _configure_actions(p):
    p.add_argument("run_dir")
    p.add_argument("prepared_dir")
    p.add_argument("--seed", type=int, default=29)
    p.add_argument("--action-count", type=int, default=16)
    p.add_argument("--iterations", type=int, default=50)


def _configure_prospective(p):
    p.add_argument("run_dir")
    p.add_argument("inputs_dir")
    p.add_argument("--iterations", type=int, default=50)


def _configure_signal(p):
    p.add_argument("run_dir")
    p.add_argument("inputs_dir")
    p.add_argument("uvw_dir")
    p.add_argument("--iterations", type=int, default=50)


def _configure_mirror(p):
    p.add_argument("mirror_dir")
    p.add_argument("source_dir")


def _configure_trend(p):
    p.add_argument("run_dir")
    p.add_argument("mirror_dir")


def _configure_imaging(p):
    p.add_argument("run_dir")
    p.add_argument("--archive-dir")
    p.add_argument("--export-dir")
    p.add_argument("--gridder", choices=("wstack", "wgrid"), default="wstack")


def _configure_campaign(p):
    p.add_argument("run_dir")
    p.add_argument("--precondition")
    p.add_argument("--workers", type=int, default=8)


def _configure_environment(p):
    p.add_argument("run_dir")


def _configure_archive(p):
    p.add_argument("run_dir", help="the run directory holding result.json")
    p.add_argument("out", help="the archive file to write (never overwritten)")
    p.add_argument("--status", help="the archive's status line")
    p.add_argument(
        "--compare",
        dest="comparisons",
        action="append",
        default=[],
        metavar="RECEIPT",
        help="a comparator receipt to keep (repeatable)",
    )


ARCHIVE = {"kind": "archive", "configure": _configure_archive}

STAGES = {
    "injections": {
        "help": "injection campaign (research/core-phase3.md)",
        "run": _function(injections, _configure_injections),
        "compare": _engine("injections", _third),
        "archive": ARCHIVE,
    },
    "actions": {
        "help": "patch-removal actions stage (research/core-phase3-actions.md)",
        "run": _function(actions, _configure_actions),
        "compare": _engine("actions", _third),
        "archive": ARCHIVE,
    },
    "prospective": {
        "help": "prospective track (research/core-phase3b.md)",
        "run": _function(prospective, _configure_prospective),
        "compare": _engine("prospective", _third),
        "archive": ARCHIVE,
    },
    "signal": {
        "help": "signal track (research/core-phase3c-b.md)",
        "run": _function(signal, _configure_signal),
        "compare": _engine("signal", _third),
        "archive": ARCHIVE,
    },
    "trend": {
        "help": "trend track on a core-solved mirror (research/core-phase3-trend.md)",
        "mirror": _function(trend_mirror, _configure_mirror),
        "run": _function(trend, _configure_trend),
        "compare": _engine("trend", _third),
        "archive": ARCHIVE,
    },
    "imaging": {
        "help": "imaging track replay, task I (research/core-i-imaging-replay.md)",
        "run": _function(imaging, _configure_imaging),
        "replay": _script("run_core_imaging.py", _first, "run plus both comparisons"),
        "compare": _engine("imaging", _third),
        "archive": ARCHIVE,
        "legacy-archive": _script("archive_core_imaging.py"),
    },
    "campaign": {
        "help": "LUNO campaign, task K (research/core-k-luno-campaign.md)",
        "run": _function(campaign, _configure_campaign),
        "precondition": _script("precondition_luno_campaign.py"),
        "compare": _script("check_luno_campaign.py", note="the K checker"),
        "archive": ARCHIVE,
        "legacy-archive": _script("archive_luno_campaign.py"),
    },
    "campaign-array": {
        "help": "LUNO whole-array campaign, task L1 (research/luno-array-campaign.md)",
        "run": _script("run_luno_array.py", _first),
        "precondition": _script("precondition_luno_array.py"),
        "compare": _script("check_luno_array.py", note="the L1 checker"),
        "archive": ARCHIVE,
        "legacy-archive": _script("archive_luno_array.py"),
    },
    "campaign-1830": {
        "help": "PKS 1830 campaign, task L2 (research/luno-1830-campaign.md)",
        "fetch": _script("fetch_luno_1830.py", _first),
        "run": _script("run_luno_1830.py", _first),
        "precondition": _script("precondition_luno_1830.py"),
        "compare": _script("check_luno_1830.py", note="the L2 checker"),
        "archive": ARCHIVE,
        "legacy-archive": _script("archive_luno_1830.py"),
    },
    "campaign-fieldmodel": {
        "help": "PKS 1934-638 field-model arms, task L1-M (research/l1-model-completeness.md)",
        "fetch": _script("fetch_l1m.py", _first),
        "run": _script("run_l1m.py", _first),
        "compare": _script("check_l1m.py", _first, "the L1-M checker"),
        "archive": ARCHIVE,
        "legacy-archive": _script("archive_l1m.py"),
    },
    "wgridder": {
        "help": "exact w-gridder ported from ducc0, task DF1 (research/df1-wgridder.md)",
        # Modes item0 | gates | threads put the output first or second: pass
        # --receipt PATH until the comparator is on the engine (P11 follow-up).
        "compare": _script("compare_core_wgridder.py", note="item0 | gates | threads"),
        "archive": ARCHIVE,
    },
    "flags": {
        "help": "Tricolour strategies, task D (research/core-d-tricolour.md)",
        "run": _script("run_core_flags.py"),
        "compare": _engine("flags", _last),
        "archive": ARCHIVE,
    },
    "weights": {
        "help": "imaging weights and Stokes I, task B (research/core-b-weighting.md)",
        "compare": _engine("weights", _first),
    },
    "gridder": {
        "help": "w-stacking gridder, task C (research/core-c-gridder.md)",
        "run": _script("run_core_gridder.py"),
        "compare": _engine("gridder", _third),
        "archive": ARCHIVE,
    },
    "ms": {
        "help": "Measurement Set reader, task E (research/core-e-ms-reader.md)",
        "compare": _script("check_ms_reader.py", note="the E checker"),
    },
    "section6": {
        "help": "zarr-to-survey chain (research/core-section6.md)",
        "run": _script("prototype_section6.py"),
        "compare": _script("check_section6.py", note="the section 6 checker"),
        "archive": ARCHIVE,
    },
    "backends": {
        "help": "two suite directories, file by file (research/core-j-packaging.md)",
        "compare": _engine("backends", _third),
    },
    "bench": {
        "help": "benchmarks (research/core-f-performance.md, p1-p6)",
        "f": _script("bench_core_f.py"),
        "p1": _script("bench_p1_solver.py"),
        "p2": _script("bench_p2_gridder.py"),
        "p3": _script("bench_p3_flags.py"),
        "p4": _script("bench_p4_eigen.py"),
        "p5": _script("bench_p5_memory.py"),
        "p6": _script("bench_p6_hotspots.py"),
    },
}
# Commands without verbs.
TOP_LEVEL = {
    "environment": "RUN_DIR: record the interpreter and the frozen solver's absence",
    "check": "[--rust | --python | --all]: the full local checks, portable",
    "compare": "STAGE RESULT ORACLE RECEIPT: legacy form (adds `comparator`)",
    "trend-mirror": "MIRROR SOURCE: legacy form of `trend mirror`",
    "formats": "check PATH | convert IN OUT: read and write the tools' formats",
}
# The stage functions that `run` (and `trend mirror`) call, looked up at call
# time; the cabs call the same functions.
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


def usage():
    lines = [
        "usage: rang-core [--receipt PATH | --no-receipt] [--no-pin-threads]"
        + " STAGE VERB ARGS...",
        "",
        "stages and verbs:",
    ]
    for stage, entry in STAGES.items():
        verbs = " | ".join(v for v in entry if v != "help")
        lines += [f"  {stage:15s} {verbs}", f"  {'':15s} {entry['help']}"]
    lines += ["", "other commands:"]
    lines += [f"  {name:15s} {text}" for name, text in TOP_LEVEL.items()]
    lines += [
        "",
        "`rang-core STAGE -h` describes a stage's verbs. `compare` takes the",
        "arguments of examples/compare_core_<stage>.py or of the stage's checker.",
    ]
    return "\n".join(lines)


def stage_usage(stage):
    entry = STAGES[stage]
    lines = [f"usage: rang-core {stage} VERB ARGS...", "", entry["help"], ""]
    for verb, spec in entry.items():
        if verb == "help":
            continue
        if spec["kind"] == "script":
            text = f"examples/{spec['script']}, unchanged"
            if spec["note"]:
                text += f" ({spec['note']})"
        elif spec["kind"] == "engine":
            text = (
                f"rang.core_compare {spec['name']!r}: the arguments of "
                f"examples/compare_core_{spec['name']}.py"
            )
        elif spec["kind"] == "archive":
            text = "RUN_DIR OUT.json [--status S] [--compare RECEIPT]: a rang.archive"
        else:
            text = f"rang.core_cli.{spec['function'].__name__} (-h for arguments)"
        lines.append(f"  {verb:15s} {text}")
    return "\n".join(lines)


def _global_options(argv):
    """Pop the global options from the front of argv."""
    options = {"receipt": None, "no_receipt": False, "pin": True}
    while argv and argv[0].startswith("--") and argv[0] != "--help":
        flag = argv.pop(0)
        if flag == "--no-pin-threads":
            options["pin"] = False
        elif flag == "--no-receipt":
            options["no_receipt"] = True
        elif flag == "--receipt" and argv:
            options["receipt"] = argv.pop(0)
        elif flag.startswith("--receipt="):
            options["receipt"] = flag.split("=", 1)[1]
        else:
            raise SystemExit(f"rang-core: unknown option {flag}\n\n{usage()}")
    if os.environ.get("RANG_PIN_THREADS") == "0":
        options["pin"] = False
    return options


def _legacy(argv):
    """Map the pre-P9 forms onto STAGE VERB ARGS."""
    if argv[0] == "trend-mirror":
        return ["trend", "mirror", *argv[1:]]
    stage = argv[0]
    if (
        stage in STAGES
        and "run" in STAGES[stage]
        and len(argv) > 1
        and argv[1] not in STAGES[stage]
        and argv[1] not in ("-h", "--help")
    ):
        return [stage, "run", *argv[1:]]
    return argv


def _parse(prog, configure, args):
    parser = argparse.ArgumentParser(prog=prog)
    configure(parser)
    return vars(parser.parse_args(args))


def _finish(options, receipt, primary, verb, code, verdict=None):
    if options["no_receipt"] or not (options["receipt"] or primary):
        return
    receipt.write(options["receipt"] or default_receipt(primary, verb), code, verdict)


def _call(options, receipt, primary, verb, function, kwargs):
    """Call a package function, writing the receipt whatever happens."""
    try:
        result = function(**kwargs)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        _finish(options, receipt, primary, verb, code)
        raise
    except BaseException as exc:
        _finish(options, receipt, primary, verb, f"exception: {type(exc).__name__}")
        raise
    _finish(options, receipt, primary, verb, 0)
    return result


def _legacy_compare(argv, options, pinned):
    parser = argparse.ArgumentParser(prog="rang-core compare")
    parser.add_argument("compare_stage", choices=sorted(COMPARATORS))
    parser.add_argument("result")
    parser.add_argument("oracle")
    parser.add_argument("receipt")
    parser.add_argument("--posthoc-slope-scale", action="store_true")
    args = parser.parse_args(argv)
    receipt = Receipt(
        ["rang-core", "compare", *argv],
        args.compare_stage,
        "compare",
        [args.result, args.oracle, args.receipt],
        pinned,
    )
    return _call(
        options,
        receipt,
        args.receipt,
        "compare",
        compare,
        {
            "stage": args.compare_stage,
            "result": args.result,
            "oracle": args.oracle,
            "receipt": args.receipt,
            "posthoc_slope_scale": args.posthoc_slope_scale,
        },
    )


def _check(args, options, pinned):
    """`rang-core check`: `rang.check`, plus a receipt only when
    `--receipt PATH` is given (a check has no output to sit beside); its
    verdict counts each step's exit status."""
    import tempfile

    from . import check

    if not options["receipt"] or options["no_receipt"]:
        code = check.main(args)
        if code:
            raise SystemExit(code)
        return None
    receipt = Receipt(["rang-core", "check", *args], "check", None, [], pinned)
    scratch = None
    if "--json" in args:
        steps_json = Path(args[args.index("--json") + 1])
    else:
        handle, scratch = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        steps_json = Path(scratch)
        args = [*args, "--json", scratch]
    try:
        code = check.main(args)
    except SystemExit as exc:
        receipt.write(options["receipt"], exc.code)
        raise
    finally:
        steps = (
            json.loads(steps_json.read_text(encoding="utf-8"))["steps"]
            if steps_json.is_file() and steps_json.stat().st_size
            else []
        )
        if scratch:
            Path(scratch).unlink(missing_ok=True)
    verdict = {
        "passed": code == 0,
        "failures": sum(1 for s in steps if s["status"]),
        "counts": {
            "steps": {s["step"]: s["status"] for s in steps},
            "wall_seconds": {s["step"]: s["wall_seconds"] for s in steps},
        },
    }
    receipt.write(options["receipt"], code, verdict)
    if code:
        raise SystemExit(code)
    return verdict


def main(argv=None):
    """The `rang-core` console script: 0, or SystemExit with the status."""
    dispatch(argv)
    return 0


def dispatch(argv=None):
    """Run one command line; return what the command returned (a stage
    function's summary or record, a comparator's verdict)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    options = _global_options(argv)
    # Before NumPy: nothing above imports it.
    pinned = pin_threads() if options["pin"] else []
    if not argv or argv[0] in ("-h", "--help"):
        print(usage())
        return None
    if argv[0] == "check":
        return _check(argv[1:], options, pinned)
    if argv[0] == "compare":
        return _legacy_compare(argv[1:], options, pinned)
    if argv[0] == "formats":
        from .formats import cli as formats_cli

        return formats_cli.main(argv[1:])
    command = ["rang-core", *argv]
    if argv[0] == "environment":
        args = _parse("rang-core environment", _configure_environment, argv[1:])
        receipt = Receipt(command, "environment", None, [args["run_dir"]], pinned)
        return _call(
            options,
            receipt,
            args["run_dir"],
            "environment",
            COMMANDS["environment"],
            args,
        )
    argv = _legacy(argv)
    stage = argv[0]
    if stage not in STAGES:
        raise SystemExit(f"rang-core: unknown stage {stage!r}\n\n{usage()}")
    if len(argv) == 1 or argv[1] in ("-h", "--help"):
        print(stage_usage(stage))
        if len(argv) == 1:
            raise SystemExit(2)
        return None
    verb, rest = argv[1], argv[2:]
    if verb == "help" or verb not in STAGES[stage]:
        raise SystemExit(
            f"rang-core: {stage} has no verb {verb!r}\n\n{stage_usage(stage)}"
        )
    spec = STAGES[stage][verb]
    prog = f"rang-core {stage} {verb}"
    if spec["kind"] == "function":
        args = _parse(prog, spec["configure"], rest)
        key = "trend-mirror" if verb == "mirror" else stage
        function = COMMANDS.get(key, spec["function"])
        primary = next(iter(args.values()))
        paths = [v for v in args.values() if isinstance(v, str)]
        receipt = Receipt(command, stage, verb, paths, pinned)
        return _call(options, receipt, primary, verb, function, args)
    if spec["kind"] == "archive":
        args = _parse(prog, spec["configure"], rest)
        paths = [args["run_dir"], args["out"], *args["comparisons"]]
        receipt = Receipt(command, stage, verb, paths, pinned)
        return _call(
            options, receipt, args["out"], verb, archive, {"stage": stage, **args}
        )
    try:
        primary = spec["primary"](rest)
    except IndexError:
        primary = None
    receipt = Receipt(command, stage, verb, rest, pinned)
    try:
        if spec["kind"] == "engine":
            from . import core_compare

            verdict = core_compare.run(spec["name"], rest)
            code = verdict["exit"]
        else:
            code = _run_script(spec["script"], rest)
            judged = verb in ("compare", "precondition")
            verdict = {"exit": code, "passed": code == 0} if judged else None
    except SystemExit as exc:
        _finish(options, receipt, primary, verb, exc.code)
        raise
    except BaseException as exc:
        _finish(options, receipt, primary, verb, f"exception: {type(exc).__name__}")
        raise
    _finish(options, receipt, primary, verb, code, verdict)
    if code:
        raise SystemExit(code)
    return verdict


if __name__ == "__main__":
    sys.exit(main())
