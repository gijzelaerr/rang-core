"""Build the native rangtoy wheel on the current OS, without docker.

Usage:
    python tools/wheel/build.py OUT_DIR [--sdist] [--no-ctypes]

Cross-platform companion of tools/wheel/build.sh (research/x1-crossplatform.md).
build.sh stays the way to build the distributable manylinux_2_28 wheels on
Linux; this script builds the wheel of the host platform (win_amd64,
macosx_*_arm64/x86_64, or a Linux wheel tagged for the host glibc) with
`maturin build --release --locked`, the pinned toolchain (rustup's
RUSTUP_TOOLCHAIN, default 1.93.1) and maturin (`uv tool run`, default
1.16.0, public PyPI), and RUSTFLAGS set to the target's baseline CPU, which
overrides the x86-64-v3 of .cargo/config.toml as the CI wheels do.

Writes OUT_DIR/dist/*.whl (and the sdist with --sdist),
OUT_DIR/ctypes/<C ABI library of core/> for the backend tests of
tools/wheel/test.py (unless --no-ctypes), build.log, sha256.txt and the wall
time of every step in OUT_DIR/timings.tsv. The cargo target directory is
OUT_DIR/target (removed afterwards unless KEEP_TARGET=1), so the checkout's
own target directories are not touched. OUT_DIR must not exist.
"""

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CTYPES_NAME = {
    "win32": "rang_core.dll",
    "darwin": "librang_core.dylib",
}.get(sys.platform, "librang_core.so")


def baseline_cpu():
    """The distributable baseline of the host target (research/wheel.md)."""
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86-64"
    if sys.platform == "darwin":
        return "apple-m1"  # the default of aarch64-apple-darwin
    return "generic"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--sdist", action="store_true")
    parser.add_argument("--no-ctypes", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        sys.exit(f"{out} exists")
    (out / "dist").mkdir(parents=True)
    toolchain = os.environ.get("RUST_VERSION", "1.93.1")
    maturin_version = os.environ.get("MATURIN_VERSION", "1.16.0")
    env = dict(os.environ)
    env["RUSTUP_TOOLCHAIN"] = toolchain
    env["RUSTFLAGS"] = f"-C target-cpu={baseline_cpu()}"
    env["CARGO_TARGET_DIR"] = str(out / "target")
    env.setdefault("UV_INDEX_URL", "https://pypi.org/simple")
    maturin = (
        ["uv", "tool", "run", "--from", f"maturin=={maturin_version}", "maturin"]
        if shutil.which("uv")
        else [sys.executable, "-m", "maturin"]
    )
    log = (out / "build.log").open("w", encoding="utf-8")
    timings = (out / "timings.tsv").open("w", encoding="utf-8")
    timings.write("step\tseconds\tstatus\n")

    def step(name, command, cwd=ROOT):
        print(f"## {name}: {' '.join(command)}", flush=True)
        log.write(f"## {name}: {' '.join(command)}\n")
        log.flush()
        start = time.perf_counter()
        status = subprocess.run(
            command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, check=False
        ).returncode
        seconds = time.perf_counter() - start
        timings.write(f"{name}\t{seconds:.1f}\t{status}\n")
        timings.flush()
        print(f"   {seconds:.1f} s, exit {status}", flush=True)
        if status:
            sys.exit(f"{name} failed; see {out / 'build.log'}")

    for name, command in (
        ("source-commit", ["git", "rev-parse", "HEAD"]),
        ("source-status", ["git", "status", "--short"]),
    ):
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False
        )
        (out / f"{name}.txt").write_text(result.stdout, encoding="utf-8")
    info = (
        f"python {platform.python_version()} {sys.platform} {platform.machine()} "
        f"rust {toolchain} maturin {maturin_version} RUSTFLAGS={env['RUSTFLAGS']}"
    )
    print(info)
    log.write(info + "\n")
    step("rustc", ["rustc", "--version"])
    step(
        "wheel",
        maturin
        + ["build", "--release", "--locked", "--out", str(out / "dist")]
        + ["--interpreter", sys.executable],
    )
    if args.sdist:
        step("sdist", maturin + ["sdist", "--out", str(out / "dist")])
    if not args.no_ctypes:
        manifest = ROOT / "core" / "Cargo.toml"
        step(
            "ctypes",
            [
                "cargo",
                "build",
                "--release",
                "--locked",
                "--manifest-path",
                str(manifest),
            ],
        )
        (out / "ctypes").mkdir()
        shutil.copy2(out / "target" / "release" / CTYPES_NAME, out / "ctypes")
    if os.environ.get("KEEP_TARGET") != "1":
        shutil.rmtree(out / "target", ignore_errors=True)
    lines = []
    for path in sorted((out / "dist").iterdir()) + sorted(
        (out / "ctypes").glob("*") if (out / "ctypes").exists() else []
    ):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(
            f"{digest}  {path.relative_to(out).as_posix()}  {path.stat().st_size}"
        )
    (out / "sha256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
