"""The full local checks, portable: `rang-core check` = `python -m rangtoy.check`
(task P9, research/p9-cli.md; design in research/x1-crossplatform.md).

    python -m rangtoy.check [--rust | --python | --all] [--only STEP,...]
                            [--skip STEP,...] [--json PATH]

The fifteen steps of `tools/check-all.sh` (which is now a thin wrapper of
this module), in the same order and with the same output: a `## <step>`
line before each step, the step's own output (for the Rust tests only the
first `test result` line, and the whole log on failure; for pytest the
last two lines), `FAILED: <command>` after a failing step, no stopping at
the first failure, and `## overall: PASS|FAIL` with exit status 0 or 1.
Every step is an argument list (no shell): cargo with `+1.93`, the Python
tools as `<this interpreter> -m ruff|maturin|pytest`, so it runs unchanged
on Windows (`.venv\\Scripts\\python -m rangtoy.check`).

`--rust` runs the root and core crate steps and the extension's clippy and
fmt; `--python` runs the extension build, ruff, ruff format, `git diff
--check` and pytest; `--all` (the default) runs both, in the shell
script's order. `--json PATH` writes each step's command, exit status and
wall time.

One check at a time on a shared host (research/p10-tests.md): the lock file
`~/.rang-checkall-v2.lock` (`RANG_CHECKALL_LOCK` overrides) is taken with
`flock` on POSIX (the same lock as `flock(1)` in the shell wrapper) and
`msvcrt.locking` on Windows, unless `RANG_CHECKALL_LOCKED` is set (the
shell wrapper sets it after taking the lock). Refuses to run outside a
checkout. Never imports `rangtoy.core`: on Windows `maturin develop` cannot
replace a loaded extension.
"""

import argparse
import contextlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TOOLCHAIN = "1.93"
CARGO = ["cargo", f"+{TOOLCHAIN}"]
PYTEST_LABEL = "bash -c set -o pipefail; .venv/bin/python -m pytest -q 2>&1 | tail -2"


def steps(python=None):
    """(name, group, kind, argv, extra environment, FAILED label) in order.

    The labels are the shell script's words, so a failure reads as before.
    """
    py = python or sys.executable
    core = ["--manifest-path", "core/Cargo.toml"]
    ext = ["--manifest-path", "core/py/Cargo.toml"]
    build = [*CARGO, "build", "--offline", "--release", "-q"]
    clippy = [*CARGO, "clippy", "--offline", "--all-targets", "-q"]
    fmt = [*CARGO, "fmt", "--check"]
    test = [*CARGO, "test", "--offline", "--release", "-q"]
    maturin = [py, "-m", "maturin", "develop", "--release", "--offline", "-q"]
    if importlib.util.find_spec("pip") is None and shutil.which("uv"):
        # A venv made by `uv venv` has no pip (research/x1-crossplatform.md).
        maturin.append("--uv")
    toolchain = {"RUSTUP_TOOLCHAIN": TOOLCHAIN}
    return [
        ("root-build", "rust", "plain", build, {}, " ".join(build)),
        ("root-test", "rust", "rust_test", test, {}, "rust_test"),
        (
            "root-clippy",
            "rust",
            "plain",
            [*clippy, "--", "-D", "warnings"],
            {},
            " ".join([*clippy, "--", "-D", "warnings"]),
        ),
        ("root-fmt", "rust", "plain", fmt, {}, " ".join(fmt)),
        ("core-build", "rust", "plain", [*build, *core], {}, " ".join([*build, *core])),
        (
            "core-test",
            "rust",
            "rust_test",
            [*test, *core],
            {},
            "rust_test " + " ".join(core),
        ),
        (
            "core-clippy",
            "rust",
            "plain",
            [*clippy, *core, "--", "-D", "warnings"],
            {},
            " ".join([*clippy, *core, "--", "-D", "warnings"]),
        ),
        ("core-fmt", "rust", "plain", [*fmt, *core], {}, " ".join([*fmt, *core])),
        (
            "ext-build",
            "python",
            "plain",
            maturin,
            toolchain,
            f"env RUSTUP_TOOLCHAIN={TOOLCHAIN} .venv/bin/maturin develop --release --offline -q",
        ),
        (
            "ext-clippy",
            "rust",
            "plain",
            [*clippy, *ext, "--", "-D", "warnings"],
            {},
            " ".join([*clippy, *ext, "--", "-D", "warnings"]),
        ),
        ("ext-fmt", "rust", "plain", [*fmt, *ext], {}, " ".join([*fmt, *ext])),
        (
            "ruff",
            "python",
            "plain",
            [py, "-m", "ruff", "check", "python", "examples", "tests"],
            {},
            ".venv/bin/ruff check python examples tests",
        ),
        (
            "ruff-format",
            "python",
            "plain",
            [py, "-m", "ruff", "format", "--check", "python", "examples", "tests"],
            {},
            ".venv/bin/ruff format --check python examples tests",
        ),
        (
            "diff-check",
            "python",
            "plain",
            ["git", "diff", "--check"],
            {},
            "git diff --check",
        ),
        ("pytest", "python", "tail2", [py, "-m", "pytest", "-q"], {}, PYTEST_LABEL),
    ]


def find_root(start=None):
    """The checkout holding Cargo.toml, core/Cargo.toml and pyproject.toml,
    searched upwards from `start` (the working directory) and then from this
    module's own location; None outside a checkout."""
    candidates = [Path(start or Path.cwd()).resolve()]
    candidates.append(Path(__file__).resolve().parents[2])
    for candidate in candidates:
        for directory in (candidate, *candidate.parents):
            if all(
                (directory / name).is_file()
                for name in ("Cargo.toml", "core/Cargo.toml", "pyproject.toml")
            ):
                return directory
    return None


@contextlib.contextmanager
def host_lock(path=None):
    """Hold the shared check lock unless RANG_CHECKALL_LOCKED is set."""
    if os.environ.get("RANG_CHECKALL_LOCKED"):
        yield None
        return
    path = Path(
        path
        or os.environ.get("RANG_CHECKALL_LOCK")
        or Path.home() / ".rang-checkall-v2.lock"
    )
    with open(path, "a+b") as stream:
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:  # LK_LOCK gives up after ten seconds
                    continue
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        os.environ["RANG_CHECKALL_LOCKED"] = "1"
        try:
            yield path
        finally:
            os.environ.pop("RANG_CHECKALL_LOCKED", None)
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _run_captured(argv, cwd, env):
    """Run with stdout and stderr in one temporary log; return (status, text)."""
    with tempfile.TemporaryFile() as log:
        try:
            status = subprocess.run(
                argv,
                check=False,
                cwd=cwd,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            ).returncode
        except OSError as exc:
            return 127, f"{argv[0]}: {exc}\n"
        log.seek(0)
        return status, log.read().decode("utf-8", errors="replace")


def run_step(kind, argv, cwd, env):
    """Run one step as the shell script did; return its exit status."""
    if kind == "plain":
        try:
            return subprocess.run(argv, check=False, cwd=cwd, env=env).returncode
        except OSError as exc:
            print(f"{argv[0]}: {exc}", flush=True)
            return 127
    status, text = _run_captured(argv, cwd, env)
    if kind == "rust_test":
        first = next(
            (line for line in text.splitlines() if re.match(r"^test result", line)),
            None,
        )
        if first is not None:
            print(first)
        if status:
            sys.stdout.write(text)
    else:  # tail2: `2>&1 | tail -2`
        lines = text.splitlines()
        if lines:
            print("\n".join(lines[-2:]))
    sys.stdout.flush()
    return status


def set_aside_launchers(scripts=None):
    """Windows only: rename the venv's `rang-core*.exe` launchers out of the
    way before `maturin develop` reinstalls the package.

    A running `.exe` cannot be replaced or deleted on Windows but can be
    renamed, and `rang-core check` runs inside `rang-core.exe`; without this
    the reinstall fails with "Access is denied". Launchers set aside by
    earlier runs are deleted when no longer in use. Returns the new names.
    """
    if os.name != "nt" and scripts is None:
        return []
    scripts = Path(scripts or Path(sys.prefix) / "Scripts")
    for stale in scripts.glob("rang-core*.exe.*.old"):
        with contextlib.suppress(OSError):
            stale.unlink()
    moved = []
    for launcher in scripts.glob("rang-core*.exe"):
        target = launcher.with_name(f"{launcher.name}.{os.getpid()}.old")
        with contextlib.suppress(OSError):
            launcher.rename(target)
            moved.append(target)
    return moved


def _parser():
    parser = argparse.ArgumentParser(
        prog="rang-core check", description=__doc__.splitlines()[0]
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--rust", action="store_true", help="the Rust steps only")
    group.add_argument("--python", action="store_true", help="the Python steps only")
    group.add_argument("--all", action="store_true", help="every step (default)")
    parser.add_argument("--only", default="", help="comma-separated step names")
    parser.add_argument("--skip", default="", help="comma-separated step names")
    parser.add_argument("--json", help="write each step's status and wall time")
    return parser


def select(args, table):
    names = [s[0] for s in table]
    only = [n for n in args.only.split(",") if n]
    skip = [n for n in args.skip.split(",") if n]
    unknown = sorted(set(only + skip) - set(names))
    if unknown:
        raise SystemExit(f"unknown step(s) {unknown}; steps: {names}")
    group = "rust" if args.rust else "python" if args.python else None
    return [
        s
        for s in table
        if (group is None or s[1] == group)
        and (not only or s[0] in only)
        and s[0] not in skip
    ]


def main(argv=None, runner=run_step, root=None):
    args = _parser().parse_args(argv)
    root = Path(root) if root else find_root()
    if root is None:
        raise SystemExit("rang-core check: not inside a rang checkout")
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(
        [str(Path.home() / ".cargo" / "bin"), env.get("PATH", "")]
    )
    if sys.prefix != sys.base_prefix:
        env.setdefault("VIRTUAL_ENV", sys.prefix)
    chosen = select(args, steps())
    records = []
    fail = 0
    with host_lock():
        env["RANG_CHECKALL_LOCKED"] = "1"
        for name, _, kind, command, extra, label in chosen:
            print(f"## {name}", flush=True)
            if name == "ext-build" and runner is run_step:
                set_aside_launchers()
            started = time.perf_counter()
            status = runner(kind, command, root, {**env, **extra})
            records.append(
                {
                    "step": name,
                    "argv": command,
                    "status": status,
                    "wall_seconds": time.perf_counter() - started,
                }
            )
            if status:
                print(f"FAILED: {label}", flush=True)
                fail = 1
    print(f"## overall: {'FAIL' if fail else 'PASS'}", flush=True)
    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {"root": root.as_posix(), "steps": records, "pass": not fail}, indent=1
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return fail


if __name__ == "__main__":
    sys.exit(main())
