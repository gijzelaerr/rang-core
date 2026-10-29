"""Comparator for the Tricolour port (research/core-d-tricolour.md).

Usage:
    python examples/compare_core_flags.py archive-host <archive.json> <host-run> outputs/<fresh>
    python examples/compare_core_flags.py run <core-run> <host-run> <oracle-dir> outputs/<fresh>

`archive-host` is the protocol precondition: the archived control records in
`research/results/gain-tv-caracal.json` must agree with the host reproduction
`outputs/tv-caracal-wsl-20261029-01` before the host's flag snapshots are used
as the oracle. `run` applies the frozen criteria 1-5 to a core run. Both write
`result.json` into a fresh directory and exit non-zero on failure.
"""

import json
import sys
from hashlib import sha256
from pathlib import Path

import numpy as np

CONTROLS = (
    "strategy-00-operational",
    "strategy-00-holdout_masked",
    "strategy-01-operational",
    "strategy-01-holdout_masked",
)
EXACT = (
    ("native", "returncode"),
    ("native", "audit"),
    ("metrics", "added_count"),
    ("metrics", "added_fraction"),
    ("metrics", "valid_gain_fraction"),
    ("metrics", "invalid_predictions"),
    ("guard_reasons",),
    ("guard_pass",),
    ("strategy",),
    ("artificial_holdout_input_flags",),
)
FLOAT = (
    ("metrics", "tv"),
    ("metrics", "raw_tv"),
    ("metrics", "time_tv"),
    ("metrics", "frequency_tv"),
    ("metrics", "scale"),
    ("fixed_support_tv",),
    ("objective",),
)
FLOAT_REL = 1e-9


def _get(record, path):
    for key in path:
        record = record[key]
    return record


def _close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= FLOAT_REL * max(abs(a), abs(b), 1e-300)


def tree_sha256(path):
    files = sorted(
        p for p in Path(path).rglob("*") if p.is_file() and p.name != "table.lock"
    )
    digest = sha256()
    for p in files:
        digest.update(str(p.relative_to(path)).encode())
        digest.update(p.read_bytes())
    return digest.hexdigest()


def archive_host(archive_path, host_run, out):
    archive = json.loads(Path(archive_path).read_text())["result"]
    host = json.loads((Path(host_run) / "result.json").read_text())
    failures, compared = [], 0
    pairs = list(zip(archive["controls"], host["controls"])) + [
        (archive["baseline"], host["baseline"])
    ]
    if len(archive["controls"]) != 4 or len(host["controls"]) != 4:
        failures.append("expected four controls on both sides")
    for index, (a, h) in enumerate(pairs):
        label = a.get("native", {}).get("label", "baseline")
        for path in EXACT + FLOAT:
            try:
                va, vh = _get(a, path), _get(h, path)
            except KeyError:
                continue
            compared += 1
            same = _close(va, vh) if path in FLOAT else va == vh
            if not same:
                failures.append(f"{label}: {'.'.join(path)} archive={va!r} host={vh!r}")
        if index < 4 and label != CONTROLS[index]:
            failures.append(f"control {index} is {label}, expected {CONTROLS[index]}")
    snapshots = {}
    for label in CONTROLS:
        directory = Path(host_run) / "native" / label
        before = np.load(directory / "before-native.npz")
        after = np.load(directory / "after-native.npz")
        if not np.array_equal(before["FLAG_ROW"], after["FLAG_ROW"]):
            failures.append(f"{label}: FLAG_ROW changed by the native run")
        if not np.all(after["FLAG"] == after["FLAG"][..., :1]):
            failures.append(f"{label}: after-native flags differ between correlations")
        snapshots[label] = {
            "before_sha256": sha256(
                (directory / "before-native.npz").read_bytes()
            ).hexdigest(),
            "after_sha256": sha256(
                (directory / "after-native.npz").read_bytes()
            ).hexdigest(),
            "before_fraction": float(before["FLAG"].mean()),
            "after_fraction": float(after["FLAG"].mean()),
        }
    return {
        "mode": "archive-host",
        "archive": str(archive_path),
        "host_run": str(host_run),
        "fields_compared": compared,
        "failures": failures,
        "snapshots": snapshots,
        "pass": not failures,
    }


def run(core_run, host_run, oracle_dir, out):
    core_run, host_run, oracle_dir = Path(core_run), Path(host_run), Path(oracle_dir)
    receipt = json.loads((core_run / "receipt.json").read_text())
    oracle = json.loads((oracle_dir / "receipt.json").read_text())
    criteria = {str(k): {"pass": True, "detail": {}} for k in range(1, 6)}
    for label in CONTROLS:
        core = np.load(core_run / label / "flags.npz")
        after = np.load(host_run / "native" / label / "after-native.npz")
        proposal = np.load(host_run / "native" / label / "frozen-proposal.npz")
        stages = np.load(core_run / label / "stages.npz")
        oracle_stages = np.load(oracle_dir / label / "stages.npz")
        # 1. Final flags, exact.
        differ = int(np.count_nonzero(core["FLAG"] != after["FLAG"]))
        criteria["1"]["detail"][label] = {
            "differences": differ,
            "elements": int(after["FLAG"].size),
            "core_fraction": float(core["FLAG"].mean()),
            "host_fraction": float(after["FLAG"].mean()),
        }
        if differ:
            criteria["1"]["pass"] = False
        # 2. Training proposal.
        added_equal = bool(np.array_equal(core["added"], proposal["added"]))
        added_count = int(np.count_nonzero(core["added"]))
        archive_count = receipt["archive_added_count"][label]
        criteria["2"]["detail"][label] = {
            "added_equal": added_equal,
            "added_count": added_count,
            "archive_added_count": archive_count,
        }
        if not added_equal or added_count != archive_count:
            criteria["2"]["pass"] = False
        # 3. Stage windows, exact.
        stage_detail = {}
        for name in oracle_stages.files:
            if name not in stages.files:
                stage_detail[name] = "missing"
                criteria["3"]["pass"] = False
                continue
            diff = int(np.count_nonzero(stages[name] != oracle_stages[name]))
            stage_detail[name] = diff
            if diff:
                criteria["3"]["pass"] = False
        criteria["3"]["detail"][label] = stage_detail
        # 4. Polarised intensity, bit-equal with NaNs equal.
        pol_core = np.load(core_run / label / "intensity.npz")["intensity"]
        pol_oracle = np.load(oracle_dir / label / "intensity.npz")["intensity"]
        pol_equal = pol_core.dtype == pol_oracle.dtype and bool(
            np.array_equal(pol_core.view(np.uint32), pol_oracle.view(np.uint32))
        )
        criteria["4"]["detail"][label] = {"bit_equal": pol_equal}
        if not pol_equal:
            criteria["4"]["pass"] = False
    # 5. No side effects on the host inputs.
    hashes = {}
    for label in CONTROLS:
        directory = host_run / "native" / label
        hashes[label] = {
            "before-native.npz": sha256(
                (directory / "before-native.npz").read_bytes()
            ).hexdigest(),
            "after-native.npz": sha256(
                (directory / "after-native.npz").read_bytes()
            ).hexdigest(),
            "diagnostic.ms": tree_sha256(directory / "diagnostic.ms"),
        }
    expected = oracle["host_hashes"]
    criteria["5"]["detail"] = {
        "hashes_equal_to_oracle_record": hashes == expected,
        "hashes_equal_to_core_record": hashes == receipt["host_hashes"],
    }
    criteria["5"]["pass"] = hashes == expected and hashes == receipt["host_hashes"]
    return {
        "mode": "run",
        "core_run": str(core_run),
        "host_run": str(host_run),
        "oracle_dir": str(oracle_dir),
        "criteria": criteria,
        "timings": {"core": receipt.get("timings"), "oracle": oracle.get("timings")},
        "pass": all(c["pass"] for c in criteria.values()),
    }


def main():
    mode = sys.argv[1]
    out = Path(sys.argv[-1])
    out.mkdir(parents=True, exist_ok=False)
    if mode == "archive-host":
        result = archive_host(sys.argv[2], sys.argv[3], out)
    elif mode == "run":
        result = run(sys.argv[2], sys.argv[3], sys.argv[4], out)
    else:
        raise SystemExit(f"unknown mode {mode}")
    (out / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("snapshots",)}, indent=1
        )
    )
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
