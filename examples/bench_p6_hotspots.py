"""Task P6 A/B helper (research/p6-python-hotspots.md).

Usage:
    python examples/bench_p6_hotspots.py trend <frozen|ported> <run-dir> <mirror-dir>
    python examples/bench_p6_hotspots.py identity <trend|signal> <base-run> <new-run> <out.json>

`trend` runs the frozen `flagging_trend.run` or `core_trend.run` (the same
frozen run with ported candidates) and prints the wall time. The signal arms
are `rang-core signal` with `RANG_P6` unset or `RANG_P6=1`. `identity` checks
criteria 1 and 2: trend `result.json` and every checkpoint byte-equal, signal
`result.json` equal after removing the wall-time fields `seconds_total` and
`seconds` and `acceptance_digest_core` (a SHA256 over the acceptance records
including their solve `seconds`, so it differs between any two runs); the
acceptance records themselves are compared without their `seconds`.
"""

import json
import sys
import time
from pathlib import Path


def trend(implementation, run_dir, mirror_dir):
    if implementation == "frozen":
        from rangtoy.flagging_trend import run
    elif implementation == "ported":
        from rangtoy.core_trend import run
    else:
        raise SystemExit("implementation must be frozen or ported")
    started = time.perf_counter()
    run(run_dir, mirror_dir)
    print(
        json.dumps({"trend": implementation, "seconds": time.perf_counter() - started})
    )


def _drop(value, keys):
    if isinstance(value, dict):
        return {k: _drop(v, keys) for k, v in value.items() if k not in keys}
    if isinstance(value, list):
        return [_drop(v, keys) for v in value]
    return value


def identity(stage, base, new, out):
    base, new = Path(base), Path(new)
    report = {"stage": stage, "base": str(base), "new": str(new), "files": {}}
    if stage == "trend":
        names = sorted(p.name for p in base.glob("*.json"))
        if names != sorted(p.name for p in new.glob("*.json")):
            report["files"]["listing"] = False
        for name in names:
            report["files"][name] = (base / name).read_bytes() == (
                new / name
            ).read_bytes()
    elif stage == "signal":
        dropped = {"seconds_total", "seconds", "acceptance_digest_core"}
        left = _drop(json.loads((base / "result.json").read_text()), dropped)
        right = _drop(json.loads((new / "result.json").read_text()), dropped)
        report["dropped_keys"] = sorted(dropped)
        report["files"]["result.json"] = left == right
    else:
        raise SystemExit("stage must be trend or signal")
    report["pass"] = bool(report["files"]) and all(report["files"].values())
    Path(out).write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({"stage": stage, "pass": report["pass"]}))
    return 0 if report["pass"] else 1


def main():
    command, *args = sys.argv[1:]
    if command == "trend":
        return trend(*args)
    if command == "identity":
        return identity(*args)
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
