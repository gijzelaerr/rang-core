"""Execute the tutorial notebooks for the documentation site (task D1).

    python docs/execute_notebooks.py [--out DIR] [--timing PATH]

Runs every notebook in `notebooks/` with papermill, one after another, from
the `notebooks/` directory, and writes the executed copies to DIR (default
`docs/tutorials/notebooks/`, ignored), where `docs/conf.py` renders them.
The committed notebooks are never written. Any cell error fails the run
(exit 1) after all notebooks have been tried.

The kernel inherits the environment. The documentation workflow sets
`RANG_FIXTURE` to a fixture verified by `rang.notebook.data.download_fixture`,
`RANG_NOTEBOOK_LUNO=0` and `RANG_NOTEBOOK_CACHE`; without `RANG_STRATEGY_DIR`
the comparator sections fall back to the teaching strategy.
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"
DEFAULT_OUT = ROOT / "docs" / "tutorials" / "notebooks"


def execute(source, target, timeout):
    import papermill

    papermill.execute_notebook(
        str(source),
        str(target),
        cwd=str(NOTEBOOKS),
        kernel_name="python3",
        progress_bar=False,
        request_save_on_cell_execute=False,
        execution_timeout=timeout,
        # A kernel that hangs at shutdown must not hold the build
        # (research/d2-notebook.md, open items).
        shutdown_kernel="immediate",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--timing", type=Path, help="write per-notebook seconds as JSON"
    )
    parser.add_argument("--timeout", type=int, default=600, help="seconds per cell")
    args = parser.parse_args(argv)

    from papermill.exceptions import PapermillExecutionError

    args.out.mkdir(parents=True, exist_ok=True)
    timings, failed = {}, []
    for source in sorted(NOTEBOOKS.glob("*.ipynb")):
        target = args.out / source.name
        start = time.perf_counter()
        try:
            execute(source, target, args.timeout)
        # A cell error, a cell timeout or a dead kernel: report every
        # notebook, then fail.
        except (PapermillExecutionError, TimeoutError, RuntimeError) as error:
            failed.append(source.name)
            print(f"FAILED {source.name}: {type(error).__name__}: {error}", flush=True)
        timings[source.name] = round(time.perf_counter() - start, 1)
        print(f"{source.name}: {timings[source.name]} s", flush=True)
    if args.timing:
        args.timing.write_text(json.dumps(timings, indent=1) + "\n")
    print(f"total: {round(sum(timings.values()), 1)} s; failed: {failed or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
