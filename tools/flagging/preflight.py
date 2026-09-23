"""Read-only stdlib namespace checks before Docker, caches or Stimela logs."""

import argparse
import sys
from pathlib import Path


def validate_paths(root, run, prepared, extra_sources=()):
    root = Path(root).resolve()
    output_root = root / "outputs"
    raw_run = root / run
    raw_log = Path(str(raw_run) + "-logs")
    run_path, log_path = raw_run.resolve(), raw_log.resolve()
    sources = [(root / source).resolve() for source in (prepared, *extra_sources)]
    for path in (run_path, log_path, *sources):
        if output_root not in path.parents:
            raise ValueError("resolved paths must remain strictly beneath outputs/")
    if raw_run.exists() or raw_run.is_symlink():
        raise ValueError("choose a fresh run directory")
    if raw_log.exists() or raw_log.is_symlink():
        raise ValueError("choose a fresh log directory as well as a fresh run")
    for source in sources:
        if not source.is_dir():
            raise ValueError(f"prepared/strategy source directory is missing: {source}")
        for destination in (run_path, log_path):
            if (
                destination == source
                or destination in source.parents
                or source in destination.parents
            ):
                raise ValueError("run/log directories and sources must not be nested")
    return {"run": run_path, "log": log_path, "sources": sources}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("run")
    parser.add_argument("prepared")
    parser.add_argument("extra_sources", nargs="*")
    args = parser.parse_args()
    try:
        validate_paths(args.root, args.run, args.prepared, args.extra_sources)
    except (ValueError, OSError, RuntimeError) as error:
        print(f"Flagging preflight: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
