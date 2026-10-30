"""Receipts for the O-CASA oracle (research/o-casa.md). Host python3, stdlib only.

receipt.py inputs <out.json>              check both archived receipt.txt files
receipt.py final <run> <image> <out.json> hashes of inputs, code, outputs; image; timings
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RECEIPTS = (
    "outputs/luno-support-20261029-01/slice/receipt.txt",
    "outputs/luno-solve-20261029-02/inputs/receipt.txt",
)
CODE = (
    "examples/build_luno_ms.py",
    "tools/oracles/casa/Dockerfile",
    "tools/oracles/casa/requirements.lock",
    "tools/oracles/casa/build.sh",
    "tools/oracles/casa/run.sh",
    "tools/oracles/casa/crosscal.py",
    "tools/oracles/casa/inspect_tables.py",
    "tools/oracles/casa/compare.py",
    "tools/oracles/casa/receipt.py",
    "python/rangtoy/core_campaign.py",
    "examples/prototype_section6.py",
)
# Files that carry time stamps, process ids or host paths; hashed but not compared.
VOLATILE = ("table.lock", ".log", "receipt.json", "timing")


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_inputs(out):
    report = {}
    ok = True
    for receipt in RECEIPTS:
        path = ROOT / receipt
        base = path.parent
        lines = [
            line.split(maxsplit=2)
            for line in path.read_text().splitlines()
            if line.strip()
        ]
        bad = []
        for size, sha, rel in lines:
            target = base / rel
            if (
                not target.exists()
                or target.stat().st_size != int(size)
                or file_sha256(target) != sha
            ):
                bad.append(rel)
        report[receipt] = {
            "lines": len(lines),
            "mismatches": bad,
            "receipt_sha256": file_sha256(path),
        }
        ok &= not bad
    report["all_match"] = ok
    Path(out).write_text(json.dumps(report, indent=1) + "\n")
    print(
        json.dumps({"all_match": ok, "lines": [report[r]["lines"] for r in RECEIPTS]})
    )
    return 0 if ok else 1


def timings(run):
    rows = []
    for path in sorted((Path(run) / "timing").glob("*.txt")):
        wall, rss_kb, code = path.read_text().split()[:3]
        rows.append(
            {
                "step": path.stem,
                "wall_seconds": float(wall),
                "max_rss_mb": int(rss_kb) / 1024,
                "exit": int(code),
            }
        )
    return rows


def final(run, image, out):
    run = Path(run)
    inspect = json.loads(
        subprocess.run(
            ["docker", "image", "inspect", image],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )[0]
    outputs = {}
    for path in sorted(p for p in run.rglob("*") if p.is_file()):
        rel = path.relative_to(run).as_posix()
        if rel == Path(out).name:
            continue
        outputs[rel] = file_sha256(path)
    receipt = {
        "run": run.name,
        "image": {
            "tag": image,
            "id": inspect["Id"],
            "size_bytes": inspect["Size"],
            "created": inspect["Created"],
        },
        "code_sha256": {c: file_sha256(ROOT / c) for c in CODE},
        "inputs_check": json.loads((run / "inputs-check.json").read_text()),
        "outputs_sha256": outputs,
        "volatile_patterns": VOLATILE,
        "timings": timings(run),
        "settings": {"OMP_NUM_THREADS": 4, "network": "none", "split_seed": 7},
    }
    Path(out).write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"outputs": len(outputs), "timings": len(receipt["timings"])}))
    return 0


def main(argv):
    if argv[1] == "inputs":
        return check_inputs(argv[2])
    if argv[1] == "final":
        return final(argv[2], argv[3], argv[4])
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
