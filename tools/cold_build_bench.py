# SPDX-License-Identifier: GPL-3.0-or-later
"""Wall-time a cold Rust build of a fresh checkout, with and without sccache.

    python tools/heavy_lock.py run -- python tools/cold_build_bench.py \
        --base ~/Build/tmp/20261113-rang-coldbench [--arms A,B,C] [--commit HEAD]

The protocol is frozen in research/speedup-tools.md section 3. Each arm
exports the same commit (`git archive`) to a new directory under `--base`, so
every arm builds at its own absolute path with empty target directories, and
runs the full check's cargo commands, with `cargo test --no-run` in place of
running the tests:

- A: no compiler wrapper;
- B: sccache with an empty cache of its own (`<base>/sccache`, own port);
- C: sccache warm from B, at a third path.

`CARGO_INCREMENTAL=0` in every arm. Results go to `<base>/bench.json` and a
table on stdout; the exports are deleted afterwards unless `--keep`. Take an
exclusive heavy-lock hold around the whole run: it is a timing run.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN = "1.93"
PORT = "4232"  # not sccache's default 4226, so the user's own server is untouched


def commands() -> list[tuple[str, list[str], dict[str, str]]]:
    cargo = ["cargo", f"+{TOOLCHAIN}"]
    core = ["--manifest-path", "core/Cargo.toml"]
    build = [*cargo, "build", "--offline", "--release", "-q"]
    gpu_target = {"CARGO_TARGET_DIR": str(Path("core") / "target" / "feature-gpu")}
    return [
        ("root-build", build, {}),
        ("core-build", [*build, *core], {}),
        (
            "core-test",
            [*cargo, "test", "--offline", "--release", "--no-run", "-q", *core],
            {},
        ),
        (
            "core-clippy",
            [*cargo, "clippy", "--offline", "--all-targets", "-q", *core],
            {},
        ),
        (
            "core-test-gpu",
            [
                *cargo,
                "test",
                "--offline",
                "--release",
                "--no-run",
                "-q",
                *core,
                "--features",
                "gpu",
            ],
            gpu_target,
        ),
        ("ext-build", [*build, "--manifest-path", "core/py/Cargo.toml"], {}),
    ]


def export(commit: str, dest: Path) -> None:
    if dest.exists():
        raise SystemExit(f"{dest} exists: every arm needs a fresh directory")
    dest.mkdir(parents=True)
    tar = subprocess.run(
        ["git", "archive", "--format=tar", commit],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
        archive.extractall(dest, filter="data")


def sccache(args: list[str], env: dict[str, str]) -> str:
    return subprocess.run(
        ["sccache", *args], env=env, check=False, capture_output=True, text=True
    ).stdout


def arm(name: str, commit: str, base: Path, env: dict[str, str]) -> dict:
    tree = base / f"arm-{name}"
    export(commit, tree)
    steps = []
    started = time.perf_counter()
    for step, argv, extra in commands():
        t0 = time.perf_counter()
        status = subprocess.run(
            argv, cwd=tree, env={**env, **extra}, check=False
        ).returncode
        wall = time.perf_counter() - t0
        steps.append({"step": step, "status": status, "wall_seconds": round(wall, 1)})
        print(f"{name} {step}: {wall:.1f} s (status {status})", flush=True)
    total = time.perf_counter() - started
    return {
        "arm": name,
        "tree": str(tree),
        "steps": steps,
        "total_seconds": round(total, 1),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--commit", default="HEAD")
    p.add_argument("--arms", default="A,B,C")
    p.add_argument("--keep", action="store_true", help="keep the exported trees")
    a = p.parse_args(argv)
    base = a.base.expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(
        ["git", "rev-parse", a.commit],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    plain = {
        k: v for k, v in os.environ.items() if k not in ("RUSTC_WRAPPER", "SCCACHE_DIR")
    }
    plain["CARGO_INCREMENTAL"] = "0"
    plain["PATH"] = os.pathsep.join(
        [str(Path.home() / ".cargo" / "bin"), plain.get("PATH", "")]
    )
    cache = base / "sccache"
    wrapped = {
        **plain,
        "RUSTC_WRAPPER": "sccache",
        "SCCACHE_DIR": str(cache),
        "SCCACHE_SERVER_PORT": PORT,
        "SCCACHE_CACHE_SIZE": "30G",
    }
    rustc = subprocess.run(
        ["rustc", f"+{TOOLCHAIN}", "-V"],
        env=plain,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    result = {
        "commit": commit,
        "rustc": rustc,
        "sccache": sccache(["--version"], plain).strip(),
        "arms": [],
    }
    for name in a.arms.split(","):
        if name == "A":
            result["arms"].append(arm("A", commit, base, plain))
            continue
        if name == "B" and cache.exists():
            raise SystemExit(f"{cache} exists: arm B needs an empty cache")
        sccache(["--stop-server"], wrapped)
        sccache(["--start-server"], wrapped)
        sccache(["--zero-stats"], wrapped)
        record = arm(name, commit, base, wrapped)
        record["sccache_stats"] = sccache(["--show-stats"], wrapped)
        print(record["sccache_stats"], flush=True)
        result["arms"].append(record)
    sccache(["--stop-server"], wrapped)
    (base / "bench.json").write_text(
        json.dumps(result, indent=1) + "\n", encoding="utf-8"
    )
    print("\narm  " + "  ".join(f"{s[0]:>13}" for s in commands()) + "      total")
    for r in result["arms"]:
        cells = "  ".join(f"{s['wall_seconds']:>13.1f}" for s in r["steps"])
        print(f"{r['arm']:<4} {cells}  {r['total_seconds']:>9.1f}")
    if not a.keep:
        for r in result["arms"]:
            shutil.rmtree(r["tree"], ignore_errors=True)
    return 0 if all(s["status"] == 0 for r in result["arms"] for s in r["steps"]) else 1


if __name__ == "__main__":
    sys.exit(main())
