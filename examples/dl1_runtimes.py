# SPDX-License-Identifier: MIT
"""Run DL1's runtime comparison (research/dl1-contract.md, section 7) from
the builds in tools/dl1_runtimes/bin/<arm>/ and write one JSON archive.

    python examples/dl1_runtimes.py OUT.json [--label provisional|final]

Each arm's bench.exe runs at 1, 2, 4, 8 and 16 threads (one process each);
`tract-mt` also sets tract's own executor to the same count. Records the
G6 size of each arm's cdylib against the kernel's, the licences of each
arm's dependency closure (cargo tree), the host and the label.
"""

import argparse
import json
import os
import platform
import re
import socket
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "tools" / "dl1_runtimes"
OUT = ROOT / "outputs" / "dl1"
ARMS = ("kernel", "tract", "tract-mt", "candle", "burn")
RUNTIME = {"tract-mt": "tract"}
THREADS = (1, 2, 4, 8, 16)
# G4: licences compatible with GPL-3.0-only (SPDX ids, any of an OR).
GPL_OK = {
    "MIT",
    "Apache-2.0",
    "Apache-2.0 WITH LLVM-exception",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "Zlib",
    "Unicode-3.0",
    "Unicode-DFS-2016",
    "MPL-2.0",
    "0BSD",
    "CC0-1.0",
    "Unlicense",
    "BSL-1.0",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
}


def licence_ok(expr):
    """True if any alternative of an SPDX OR expression is all compatible."""
    if not expr:
        return False
    expr = expr.replace("/", " OR ").replace("(", "").replace(")", "")
    for alt in re.split(r"\s+OR\s+", expr):
        parts = [p.strip() for p in re.split(r"\s+AND\s+", alt)]
        if all(p in GPL_OK for p in parts):
            return True
    return False


def licences(feature):
    out = subprocess.run(
        [
            "cargo",
            "tree",
            "-e",
            "normal",
            "--features",
            feature,
            "--prefix",
            "none",
            "-f",
            "{p}\t{l}",
        ],
        check=False,
        cwd=BENCH,
        capture_output=True,
        text=True,
        env={**os.environ, "DL1_ONNX": str(OUT / "f3-calibrator-seed3.onnx")},
    )
    seen = {}
    for line in out.stdout.splitlines():
        if "\t" not in line:
            continue
        pkg, lic = line.split("\t", 1)
        seen[pkg.replace(" (*)", "").strip()] = lic.strip()
    bad = {p: lic for p, lic in seen.items() if not licence_ok(lic)}
    return {"crates": len(seen), "incompatible": bad, "ok": not bad and bool(seen)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--label", default="provisional")
    ap.add_argument("--arms", default=",".join(ARMS))
    args = ap.parse_args()
    onnx = OUT / "f3-calibrator-seed3.onnx"
    planes, torch_a = OUT / "planes_a.bin", OUT / "torch_a.bin"
    result = {
        "label": args.label,
        "host": socket.gethostname(),
        "cpu": platform.processor(),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "onnx": str(onnx),
        "arms": {},
    }
    arms = [a for a in args.arms.split(",") if a]
    for arm in arms:
        exe = BENCH / "bin" / arm / "bench.exe"
        entry = {"runs": [], "built": exe.is_file()}
        if exe.is_file():
            dll = BENCH / "bin" / arm / "dl1_runtimes.dll"
            entry["cdylib_bytes"] = dll.stat().st_size if dll.is_file() else None
            for n in THREADS:
                env = dict(os.environ)
                if arm == "tract-mt":
                    env["DL1_TRACT_MT"] = "1"
                t0 = time.perf_counter()
                p = subprocess.run(
                    [
                        str(exe),
                        RUNTIME.get(arm, arm),
                        str(onnx),
                        str(planes),
                        str(torch_a),
                        str(n),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                run = {
                    "threads": n,
                    "rc": p.returncode,
                    "wall_s": time.perf_counter() - t0,
                }
                if p.returncode == 0:
                    run.update(json.loads(p.stdout.strip().splitlines()[-1]))
                else:
                    run["stderr"] = p.stderr[-2000:]
                entry["runs"].append(run)
                print(arm, json.dumps(run), flush=True)
            ok = [r for r in entry["runs"] if r["rc"] == 0]
            if ok:
                entry["identical_across_threads"] = {
                    "a": len({r["hash_a"] for r in ok}) == 1,
                    "b": len({r["hash_b"] for r in ok}) == 1,
                }
        feature = {"tract-mt": "tract-mt"}.get(arm, arm)
        entry["licences"] = licences(feature)
        result["arms"][arm] = entry
    k = result["arms"].get("kernel", {}).get("cdylib_bytes")
    for entry in result["arms"].values():
        b = entry.get("cdylib_bytes")
        entry["g6_delta_bytes"] = None if (b is None or k is None) else b - k
    result["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
