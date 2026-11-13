# SPDX-License-Identifier: GPL-3.0-or-later
"""The full local checks, portable: `rang-core check` = `python -m rang.check`
(task P9, research/p9-cli.md; design in research/x1-crossplatform.md).

    python -m rang.check [--rust | --python | --all] [--only STEP,...]
                            [--skip STEP,...] [--json PATH]

The steps of `tools/check-all.sh` (which is now a thin wrapper of this
module), cheap ones first since task check-speed (research/check-speed.md:
fmt, ruff and `git diff --check`, then the builds and tests, pytest and the
gain-hash gate last), with the same output: a `## <step>`
line before each step, the step's own output (for the Rust tests only the
first `test result` line, and the whole log on failure; for pytest the
last two lines), `FAILED: <command>` after a failing step, no stopping at
the first failure, and `## overall: PASS|FAIL` with exit status 0 or 1.
Every step is an argument list (no shell): cargo with `+1.93`, the Python
tools as `<this interpreter> -m ruff|maturin|pytest`, so it runs unchanged
on Windows (`.venv\\Scripts\\python -m rang.check`).

The core crate's `gpu` feature (task X2, research/x2-wgpu.md) has its own
clippy and test steps, `core-clippy-gpu` and `core-test-gpu` (task W4-7);
its GPU tests skip without an adapter. `--skip core-clippy-gpu,core-test-gpu`
leaves them out.

`--rust` runs the root and core crate steps and the extension's clippy and
fmt; `--python` runs the extension build, ruff, ruff format, `git diff
--check` and pytest; `--all` (the default) runs both, in the shell
script's order. `--json PATH` writes each step's command, exit status and
wall time. `--fail-fast` stops after the first failing step (by default
every step runs).

Two speed-ups keep the coverage (research/check-speed.md): pytest runs on
PYTEST_WORKERS processes when pytest-xdist (the `test` extra) is
installed, and `ext-build` does not rerun `maturin develop` when a stamp in
the venv, written after its last successful run, records the same inputs
(every tracked or untracked-unignored file of the crates, the lock files,
`.cargo/` and the package metadata, the toolchain's `rustc -vV`, the
argument list, the interpreter and the CARGO*, RUST*, PYO3_*, MATURIN*
variables) and the same installed extension and `rang-core` metadata.
`--rebuild` reruns it regardless.

One check at a time on a shared host (research/p10-tests.md): the lock file
`~/.rang-checkall-v2.lock` (`RANG_CHECKALL_LOCK` overrides) is taken with
`flock` on POSIX (the same lock as `flock(1)` in the shell wrapper) and
`msvcrt.locking` on Windows, unless `RANG_CHECKALL_LOCKED` is set (the
shell wrapper sets it after taking the lock). Refuses to run outside a
checkout. Never imports `rang.core`: on Windows `maturin develop` cannot
replace a loaded extension.

`RANG_ARCHIVE_OUTPUTS`, the gain-hash gate's archive (research/speedup-tools.md):
a UNC value that lost one of its two leading backslashes (Git Bash's path
conversion) is repaired, and on Windows an unset value defaults to the
development host's WSL checkout (`DEV_HOST_ARCHIVE`) when that directory
exists, so elsewhere the gate still reports the archive absent.
`--pytest-paths` runs pytest on the given test files only (the quick check of
`tools/check_all.py`).
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
GPU_TARGET = "feature-gpu"
PYTEST_WORKERS = max(1, min(8, os.cpu_count() or 1))
PYTEST_LABEL = "bash -c set -o pipefail; .venv/bin/python -m pytest -q 2>&1 | tail -2"
ARCHIVE_ENV = "RANG_ARCHIVE_OUTPUTS"
# The development host's archive: the WSL checkout's outputs (CONTRIBUTING.md).
DEV_HOST_ARCHIVE = r"\\wsl.localhost\Ubuntu\home\gijsm\Github\rang\outputs"
_HALF_UNC = re.compile(r"^[\\/](?![\\/])(wsl\.localhost|wsl\$)[\\/]", re.IGNORECASE)


def repair_unc(value):
    r"""A WSL UNC path (`\\wsl.localhost\...`, `\\wsl$\...`) that lost one of
    its two leading backslashes gets it back; anything else is unchanged."""
    if _HALF_UNC.match(value):
        return "\\" + value.replace("/", "\\")
    return value


def archive_outputs(env, default=DEV_HOST_ARCHIVE, exists=os.path.isdir):
    """(value, why): what `RANG_ARCHIVE_OUTPUTS` should be in `env`; `why` is
    "set", "repaired", "default", or None when it stays unset."""
    value = env.get(ARCHIVE_ENV)
    if value:
        fixed = repair_unc(value)
        return fixed, ("set" if fixed == value else "repaired")
    if os.name == "nt" and default and exists(default):
        return default, "default"
    return None, None


def steps(python=None, pytest_paths=None):
    """(name, group, kind, argv, extra environment, FAILED label) in order.

    The labels are the shell script's words, so a failure reads as before.
    `pytest_paths` limits pytest to those test files.
    """
    py = python or sys.executable
    core = ["--manifest-path", "core/Cargo.toml"]
    ext = ["--manifest-path", "core/py/Cargo.toml"]
    gpu = ["--features", "gpu"]
    build = [*CARGO, "build", "--offline", "--release", "-q"]
    clippy = [*CARGO, "clippy", "--offline", "--all-targets", "-q"]
    fmt = [*CARGO, "fmt", "--check"]
    test = [*CARGO, "test", "--offline", "--release", "-q"]
    maturin = [py, "-m", "maturin", "develop", "--release", "--offline", "-q"]
    if importlib.util.find_spec("pip") is None and shutil.which("uv"):
        # A venv made by `uv venv` has no pip (research/x1-crossplatform.md).
        maturin.append("--uv")
    toolchain = {"RUSTUP_TOOLCHAIN": TOOLCHAIN}
    # The gpu steps build in their own target directory: sharing core/target
    # with the feature-less steps made every run rebuild the core's binaries
    # and tests twice, about 590 s warm (research/check-speed.md).
    gpu_target = {"CARGO_TARGET_DIR": str(Path("core") / "target" / GPU_TARGET)}
    pytest = [py, "-m", "pytest", "-q"]
    if importlib.util.find_spec("xdist") is not None:
        # pytest-xdist (the `test` extra, research/check-speed.md): the same
        # tests on PYTEST_WORKERS processes; without it the suite runs serially.
        workers = PYTEST_WORKERS
        if pytest_paths:
            workers = max(1, min(workers, len(pytest_paths)))
        pytest += ["-n", str(workers)]
    if pytest_paths:
        pytest += list(pytest_paths)
    # The cheap steps (fmt, ruff, `git diff --check`) run first, so a lint
    # failure shows within seconds (and ends a `--fail-fast` run); pytest and
    # the gate stay after the builds they need (core-build's gemclean binary,
    # ext-build's extension; research/check-speed.md).
    return [
        ("root-fmt", "rust", "plain", fmt, {}, " ".join(fmt)),
        ("core-fmt", "rust", "plain", [*fmt, *core], {}, " ".join([*fmt, *core])),
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
        (
            "core-clippy-gpu",
            "rust",
            "plain",
            [*clippy, *core, *gpu, "--", "-D", "warnings"],
            gpu_target,
            " ".join([*clippy, *core, *gpu, "--", "-D", "warnings"]),
        ),
        (
            "core-test-gpu",
            "rust",
            "rust_test",
            [*test, *core, *gpu],
            gpu_target,
            "rust_test " + " ".join([*core, *gpu]),
        ),
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
        ("pytest", "python", "tail2", pytest, {}, PYTEST_LABEL),
        # Task C2a: the archived `complex` solves gate every C-stream merge
        # (research/c2a-gain.md; C1 section 4, rule 2).
        (
            "gain-hashes",
            "python",
            "plain",
            [py, "tools/gain_hash_gate.py"],
            {},
            ".venv/bin/python tools/gain_hash_gate.py",
        ),
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
    the reinstall fails with "Access is denied". Each launcher is renamed to
    `<name>.<pid>.old` and copied back under its own name, so the venv keeps
    a working launcher even if the reinstall fails. Launchers set aside by
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
        try:
            launcher.rename(target)
        except OSError:
            continue
        shutil.copy2(target, launcher)
        moved.append(target)
    return moved


# The inputs of `maturin develop` (research/check-speed.md): the three crates
# (the core depends on the root crate rang-sim), the lock files, the cargo
# configuration and the package metadata maturin writes into the install.
EXT_INPUTS = (
    "Cargo.toml",
    "Cargo.lock",
    "src",
    "core",
    ".cargo",
    "pyproject.toml",
    "rust-toolchain",
    "rust-toolchain.toml",
    "README.md",
    "LICENSE",
    "data",  # include_str! of data/meerkat.itrf.txt (core/src/gemclean/sim.rs)
)
EXT_ENV = re.compile(r"^(CARGO|RUST|PYO3_|MATURIN)")
# cargo's dep-info of the extension: every file the compiler read.
EXT_DEP_INFO = Path("core") / "py" / "target" / "release" / "rang_core_py.d"


def ext_uncovered(root, dep_info=None):
    """The checkout's files that cargo's dep-info lists for the extension but
    EXT_INPUTS does not cover, as POSIX paths relative to `root`; None when
    there is no dep-info. A nonempty answer means the stamp could miss a
    change, so `write_ext_stamp` refuses to write one."""
    root = Path(root).resolve()
    try:
        text = Path(dep_info or root / EXT_DEP_INFO).read_text(encoding="utf-8")
    except OSError:
        return None
    found = set()
    for line in text.splitlines():
        if ": " not in line:
            continue
        for dep in re.split(r"(?<!\\) ", line.split(": ", 1)[1]):
            dep = dep.replace("\\ ", " ").strip()
            if not dep:
                continue
            try:
                rel = Path(dep).resolve().relative_to(root).as_posix()
            except ValueError:
                continue  # the toolchain or the cargo registry
            if rel.split("/")[0] in ("target",) or "/target/" in f"/{rel}":
                continue  # build products (e.g. a build script's OUT_DIR)
            if not any(rel == i or rel.startswith(f"{i}/") for i in EXT_INPUTS):
                found.add(rel)
    return sorted(found)


def _sha256(path):
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def ext_inputs(root, argv, env):
    """A digest of everything `ext-build` reads, or None when it cannot be
    taken (no git): tracked and untracked-unignored files under EXT_INPUTS
    with their contents, the toolchain's `rustc -vV`, the argument list, the
    interpreter and the build environment's CARGO*, RUST*, PYO3_*, MATURIN*
    variables."""
    import hashlib

    root = Path(root)
    try:
        listed = subprocess.run(
            [
                "git",
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
                "--",
                *EXT_INPUTS,
            ],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8", errors="surrogateescape")
        rustc = subprocess.run(
            ["rustc", f"+{TOOLCHAIN}", "-vV"],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
        ).stdout.decode()
    except (OSError, subprocess.CalledProcessError):
        return None
    from importlib import metadata

    try:
        maturin = metadata.version("maturin")
    except metadata.PackageNotFoundError:
        maturin = None
    digest = hashlib.sha256()
    for name in sorted({n for n in listed.split("\0") if n}):
        path = root / name
        if path.is_file():  # a tracked file deleted in the tree is skipped
            digest.update(f"{name}\0{_sha256(path)}\n".encode())
    meta = {
        "root": root.resolve().as_posix(),
        "argv": list(argv),
        "maturin": maturin,
        "rustc": rustc,
        "python": [sys.version, sys.prefix],
        "env": {k: v for k, v in sorted(env.items()) if EXT_ENV.match(k)},
    }
    digest.update(json.dumps(meta, sort_keys=True).encode())
    return digest.hexdigest()


def ext_installed(root):
    """A digest of the installed extension (`python/rang/_core*`) and the
    `rang-core` distribution's metadata in this interpreter, or None when
    either is missing."""
    import hashlib
    from importlib import metadata

    built = sorted((Path(root) / "python" / "rang").glob("_core*"))
    try:
        dist = metadata.distribution("rang-core")
    except metadata.PackageNotFoundError:
        return None
    if not built:
        return None
    digest = hashlib.sha256()
    for path in built:
        digest.update(f"{path.name}\0{_sha256(path)}\n".encode())
    # importlib.metadata reads its own files as UTF-8 (not the host's code
    # page), so the encoding lint of tests/test_w4_6_portability.py does not apply.
    metadata_file = dist.read_text
    for name in ("METADATA", "direct_url.json", "entry_points.txt", "RECORD"):
        digest.update(f"{name}\0{metadata_file(name)}\n".encode())
    return digest.hexdigest()


def ext_stamp_path():
    """The ext-build stamp of this interpreter's environment."""
    return Path(sys.prefix) / "rang-check-ext-build.json"


def ext_build_fresh(inputs, root, stamp=None):
    """True when the stamp written after the last successful `ext-build`
    records these inputs and the extension installed now."""
    if inputs is None:
        return False
    try:
        saved = json.loads(Path(stamp or ext_stamp_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return saved.get("inputs") == inputs and saved.get("installed") == ext_installed(
        root
    )


def write_ext_stamp(inputs, root, stamp=None):
    """Record a successful `ext-build`: its inputs (taken before the build)
    and the extension it installed. No stamp (so the next run rebuilds) when
    cargo's dep-info names a checkout file outside EXT_INPUTS, or is absent."""
    installed = ext_installed(root)
    path = Path(stamp or ext_stamp_path())
    uncovered = ext_uncovered(root)
    if uncovered:
        print(
            f"ext-build: no stamp written; inputs outside EXT_INPUTS: {uncovered}",
            flush=True,
        )
    if inputs is None or installed is None or uncovered is None or uncovered:
        with contextlib.suppress(OSError):
            path.unlink()
        return
    path.write_text(
        json.dumps({"inputs": inputs, "installed": installed}, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )


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
    parser.add_argument(
        "--fail-fast", action="store_true", help="stop after the first failing step"
    )
    parser.add_argument(
        "--pytest-paths",
        default="",
        help="comma-separated test files: pytest runs only these",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="run ext-build even when its inputs and the installed extension "
        "are those of the last successful build",
    )
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
    archive, why = archive_outputs(env)
    if why in ("repaired", "default"):
        env[ARCHIVE_ENV] = archive
        print(f"{ARCHIVE_ENV} {why}: {archive}", flush=True)
    paths = [n for n in args.pytest_paths.split(",") if n]
    chosen = select(args, steps(pytest_paths=paths))
    records = []
    fail = 0
    with host_lock():
        env["RANG_CHECKALL_LOCKED"] = "1"
        for name, _, kind, command, extra, label in chosen:
            print(f"## {name}", flush=True)
            started = time.perf_counter()
            step_env = {**env, **extra}
            cached = False
            if name == "ext-build" and runner is run_step:
                inputs = ext_inputs(root, command, step_env)
                cached = not args.rebuild and ext_build_fresh(inputs, root)
                if cached:
                    print(
                        "ext-build: inputs and installed extension unchanged "
                        f"since the last build ({ext_stamp_path()}); not rebuilt",
                        flush=True,
                    )
                    status = 0
                else:
                    set_aside_launchers()
                    status = runner(kind, command, root, step_env)
                    if status:
                        with contextlib.suppress(OSError):
                            ext_stamp_path().unlink()
                    else:
                        write_ext_stamp(inputs, root)
            else:
                status = runner(kind, command, root, step_env)
            records.append(
                {
                    "step": name,
                    "argv": command,
                    "status": status,
                    "wall_seconds": time.perf_counter() - started,
                    "cached": cached,
                }
            )
            if status:
                print(f"FAILED: {label}", flush=True)
                fail = 1
                if args.fail_fast:
                    break
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
