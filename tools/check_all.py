# SPDX-License-Identifier: GPL-3.0-or-later
"""The full local check from any worktree, set up correctly, under the heavy lock.

    python tools/check_all.py            # the full check (python -m rang.check)
    python tools/check_all.py --quick    # lint, clippy, Rust tests, the diff's pytest, the gate
    python tools/check_all.py --dry-run  # show what would run
    python tools/check_all.py -- --only ruff,pytest   # extra rang.check arguments

Any Python 3.10+ starts it, from PowerShell, cmd or Git Bash; it re-runs
itself with the worktree's own venv. In order (research/speedup-tools.md):

1. **venv**: `<worktree>/.venv`; if missing, `uv venv` and the dependencies
   of every extra the check uses (`--extras`), without the package itself,
   which the check's `ext-build` step installs (`maturin develop --release`
   into this venv, with `VIRTUAL_ENV` forced to it so an outer venv never
   receives the extension).
2. **heavy lock**: the main checkout's `tools/heavy_lock.py`, shared,
   `--slots 8 --mem 12` (`--quick`: 4 and 8), `--priority normal`. Cargo gets
   `CARGO_BUILD_JOBS` equal to the slots. Under the heavy lock the check's own
   one-at-a-time lock is off (`RANG_CHECKALL_LOCKED=1`): the slots already
   account for the load, and that lock let a waiting check sit on 8 slots
   for hours behind another (2026-11-13). Do not wrap this script in
   `heavy_lock.py run`: it locks itself. If it starts inside a hold anyway
   (`RANG_HEAVY_LOCK_HELD` set by `heavy_lock.py run`), it runs inside that
   hold without queueing again, with a warning when it wants more than the
   hold (2026-11-14: the wrapped check sat at the back of the queue for five
   hours while its own wrapper held 4 slots idle).
3. **toolchain**: each target directory (`target`, `core/target`,
   `core/target/feature-gpu`, `core/py/target`) carries a stamp of
   `rustc +1.93 -vV`; a directory whose stamp differs, or that has no stamp
   and whose `.rustc_info.json` names only other compilers, is removed
   before the check. If the check still fails with E0514 (a crate compiled
   by an incompatible rustc), every target directory is removed and the
   check runs once more.
4. **archive**: `RANG_ARCHIVE_OUTPUTS` is repaired or defaulted by
   `rang.check` itself (`archive_outputs`), so the gate finds the archive
   whichever shell started the check.
5. **log**: `<worktree>/outputs/check/<UTC time>-<full|quick>.log` and
   `.json` (rang.check's per-step record); the last line is
   `check_all: PASS` or `check_all: FAIL`, with the log path.

`--quick` (for a session before it pushes; CI runs the rest): every step
except the two gpu steps, and pytest only on the test files the diff
against `origin/main` touches (`quick_tests`); the gain-hash gate stays.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN = "1.93"
TARGETS = ("target", "core/target", "core/target/feature-gpu", "core/py/target")
STAMP = ".rang-rustc-vV"
EXTRAS = "pointing,beam,test,imaging,formats,casacure,docs,notebook,mcp"
GPU_STEPS = ("core-clippy-gpu", "core-test-gpu")
INDEX = "https://pypi.org/simple"
HELD_VAR = "RANG_HEAVY_LOCK_HELD"  # set by heavy_lock.py run for its child


def venv_python(root: Path = ROOT) -> Path:
    win = root / ".venv" / "Scripts" / "python.exe"
    return win if os.name == "nt" else root / ".venv" / "bin" / "python"


def main_checkout(root: Path = ROOT) -> Path:
    """The main checkout of this worktree's repository (its common git dir's parent)."""
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return root
    return Path(common).parent


def heavy_lock_script(root: Path = ROOT) -> Path:
    main = main_checkout(root) / "tools" / "heavy_lock.py"
    return main if main.is_file() else root / "tools" / "heavy_lock.py"


def ensure_venv(root: Path, extras: str, dry_run: bool) -> Path:
    py = venv_python(root)
    if py.exists():
        return py
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit(f"check_all: {py} missing and uv not on PATH")
    commands = [
        [uv, "venv", str(root / ".venv")],
        [uv, "pip", "install", "--python", str(py), "--index-url", INDEX]
        + ["-r", str(root / "pyproject.toml")]
        + [a for e in extras.split(",") if e for a in ("--extra", e)]
        + ["ruff", "maturin"],
    ]
    for command in commands:
        print("check_all: " + " ".join(command), flush=True)
        if not dry_run:
            subprocess.run(command, cwd=root, check=True)
    return py


# --- toolchain stamps -------------------------------------------------------


def rustc_vv(env: dict | None = None) -> str:
    return subprocess.run(
        ["rustc", f"+{TOOLCHAIN}", "-vV"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _commit(vv: str) -> str | None:
    m = re.search(r"^commit-hash: (\S+)", vv, re.MULTILINE)
    return m.group(1) if m else None


def stale_reason(target: Path, want: str) -> str | None:
    """Why `target` was built by another compiler, or None if it was not."""
    if not target.is_dir():
        return None
    stamp = target / STAMP
    if stamp.is_file():
        have = stamp.read_text(encoding="utf-8")
        if have != want:
            return f"stamp {_commit(have)} != {_commit(want)}"
        return None
    try:
        info = json.loads((target / ".rustc_info.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    seen = {
        _commit(out.get("stdout", ""))
        for out in info.get("outputs", {}).values()
        if "commit-hash:" in out.get("stdout", "")
    }
    if seen and _commit(want) not in seen:
        return f"built only by {sorted(c for c in seen if c)}"
    return None


def clear_stale(root: Path, want: str, dry_run: bool = False) -> list[str]:
    removed = []
    for rel in TARGETS:
        why = stale_reason(root / rel, want)
        if why:
            print(f"check_all: removing {rel} ({why})", flush=True)
            removed.append(rel)
            if not dry_run:
                shutil.rmtree(root / rel, ignore_errors=True)
    return removed


def write_stamps(root: Path, want: str) -> None:
    for rel in TARGETS:
        if (root / rel).is_dir():
            (root / rel / STAMP).write_text(want, encoding="utf-8", newline="\n")


# --- the quick check's pytest selection --------------------------------------


def changed_files(root: Path) -> list[str]:
    """Files changed since the nearer of the merge bases with origin/main and
    main (the coordinator's local main is often ahead of origin), committed
    or not, plus untracked files."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True, text=True
        ).stdout

    bases = []
    for ref in ("origin/main", "main"):
        try:
            b = git("merge-base", "HEAD", ref).strip()
        except subprocess.CalledProcessError:
            continue
        bases.append((int(git("rev-list", "--count", f"{b}..HEAD")), b))
    base = min(bases)[1] if bases else None
    names = set(git("diff", "--name-only", base).split()) if base else set()
    names |= set(git("ls-files", "--others", "--exclude-standard").split())
    return sorted(names)


def quick_tests(root: Path, changed: list[str]) -> list[str]:
    """The test files a diff touches: changed tests, tests that name a changed
    file's path, module, tool or example, tests of `rang.core` when Rust
    changed, and the docs tests when docs or notebooks changed. A change to
    `python/rang/__init__.py` selects every test that names `rang`."""
    tests = sorted((root / "tests").glob("test_*.py"))
    texts = {t: t.read_text(encoding="utf-8", errors="replace") for t in tests}
    patterns: list[re.Pattern] = []
    chosen: set[Path] = set()
    for name in changed:
        p = Path(name)
        # Any test that names the changed file by its path reads or checks it.
        patterns.append(re.compile(re.escape(p.as_posix())))
        if (
            p.parts[:1] == ("tests",)
            and p.name.startswith("test_")
            and p.suffix == ".py"
        ):
            if (root / p).exists():
                chosen.add(root / p)
        elif p.parts[:2] == ("python", "rang") and p.suffix == ".py":
            dotted = ".".join(p.with_suffix("").parts[1:])
            dotted = dotted.removesuffix(".__init__")
            leaf = dotted.rsplit(".", 1)[-1]
            parent = dotted.rsplit(".", 1)[0]
            patterns.append(re.compile(rf"\b{re.escape(dotted)}\b"))
            patterns.append(
                re.compile(
                    rf"from {re.escape(parent)} import [^\n]*\b{re.escape(leaf)}\b"
                )
            )
        elif p.parts[:1] in (("tools",), ("examples",)) and p.suffix in (".py", ".sh"):
            patterns.append(re.compile(re.escape(p.name)))
        elif p.parts[:1] in (("core",), ("src",)) or p.name in (
            "Cargo.toml",
            "Cargo.lock",
        ):
            patterns.append(
                re.compile(r"\brang\._?core\b|from rang import [^\n]*\bcore\b")
            )
        elif p.parts[:1] in (("docs",), ("notebooks",)):
            chosen |= {t for t in tests if re.search(r"docs|notebook", t.name)}
    for t, text in texts.items():
        if any(pat.search(text) for pat in patterns):
            chosen.add(t)
    return sorted(t.relative_to(root).as_posix() for t in chosen)


# --- running -----------------------------------------------------------------


def check_args(a: argparse.Namespace, root: Path) -> list[str]:
    args = list(a.check_args)
    if a.quick:
        paths = quick_tests(root, changed_files(root))
        skip = list(GPU_STEPS) + ([] if paths else ["pytest"])
        args += ["--skip", ",".join(skip)]
        if paths:
            args += ["--pytest-paths", ",".join(paths)]
    return args


def inner(a: argparse.Namespace) -> int:
    """The part under the heavy lock, run by the worktree's venv."""
    root = Path(a.root)
    py = Path(sys.executable)
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(
        [str(Path.home() / ".cargo" / "bin"), env.get("PATH", "")]
    )
    env["VIRTUAL_ENV"] = str(py.parent.parent)
    env["CARGO_BUILD_JOBS"] = str(a.slots)
    if not a.no_lock:
        env["RANG_CHECKALL_LOCKED"] = "1"
    log = Path(a.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    want = rustc_vv(env)
    clear_stale(root, want)
    args = check_args(a, root) + ["--json", str(log.with_suffix(".json"))]
    command = [str(py), str(root / "tools" / "check.py"), *args]
    started = time.perf_counter()
    with open(log, "w", encoding="utf-8", newline="\n") as out:
        status, text = _tee(command, root, env, out)
        if status and "E0514" in text:
            print(
                "check_all: E0514, removing every target directory and rerunning",
                flush=True,
            )
            out.write(
                "check_all: E0514, removing every target directory and rerunning\n"
            )
            for rel in TARGETS:
                shutil.rmtree(root / rel, ignore_errors=True)
            status, text = _tee(command, root, env, out)
        if status == 0 or "E0514" not in text:
            write_stamps(root, want)
        wall = time.perf_counter() - started
        verdict = "PASS" if status == 0 else "FAIL"
        line = f"check_all: {verdict} in {wall:.0f} s (lock wait excluded); log {log}"
        out.write(line + "\n")
    print(line, flush=True)
    return 0 if status == 0 else 1


def _tee(command: list[str], root: Path, env: dict, out) -> tuple[int, str]:
    out.write("$ " + " ".join(command) + "\n")
    out.flush()
    proc = subprocess.Popen(
        command,
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    seen = []
    # A console in a legacy code page (cp1252) cannot print every character a
    # build writes (maturin prints emoji); never let the echo end the check.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.decode("utf-8", errors="replace")
        sys.stdout.write(line)
        sys.stdout.flush()
        out.write(line)
        out.flush()
        seen.append(line)
    return proc.wait(), "".join(seen)


def _held(value: str) -> tuple[int, float] | None:
    """`RANG_HEAVY_LOCK_HELD` (`<slots>:<mem GB>`) parsed, or None."""
    try:
        slots, mem = value.split(":")
        return int(slots), float(mem)
    except ValueError:
        return None


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--quick", action="store_true", help="the pre-push check (see above)"
    )
    p.add_argument(
        "--slots", type=int, help="heavy-lock threads (default 8, --quick 4)"
    )
    p.add_argument("--mem", type=float, help="heavy-lock GB (default 12, --quick 8)")
    p.add_argument("--priority", choices=("normal", "critical"), default="normal")
    p.add_argument("--no-lock", action="store_true", help="run without the heavy lock")
    p.add_argument("--extras", default=EXTRAS, help="extras for a new venv")
    p.add_argument("--dry-run", action="store_true", help="print what would run")
    p.add_argument("--inner", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    p.add_argument("--log", help=argparse.SUPPRESS)
    p.add_argument("check_args", nargs="*", help="after --: extra rang.check arguments")
    return p


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    a.slots = a.slots or (4 if a.quick else 8)
    a.mem = a.mem or (8.0 if a.quick else 12.0)
    if a.inner:
        return inner(a)
    root = Path(a.root)
    py = ensure_venv(root, a.extras, a.dry_run)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log = root / "outputs" / "check" / f"{stamp}-{'quick' if a.quick else 'full'}.log"
    me = [str(py), str(Path(__file__).resolve()), "--inner", "--root", str(root)]
    me += ["--log", str(log), "--slots", str(a.slots), "--mem", str(a.mem)]
    me += ["--quick"] if a.quick else []
    me += ["--no-lock"] if a.no_lock else []
    if a.check_args:
        me += ["--", *a.check_args]
    lock = [sys.executable, str(heavy_lock_script(root)), "run"]
    lock += ["--slots", str(a.slots), "--mem", f"{a.mem:g}"]
    if a.priority != "normal":  # helpers older than the priority lane lack the flag
        lock += ["--priority", a.priority]
    lock += ["--"]
    nested = not a.no_lock and _held(os.environ.get(HELD_VAR, "")) is not None
    command = me if a.no_lock or nested else lock + me
    if a.dry_run:
        print(" ".join(command))
        if a.quick:
            print("rang.check " + " ".join(check_args(a, root)))
        want = rustc_vv()
        for rel in TARGETS:
            why = stale_reason(root / rel, want)
            print(f"{rel}: {'stale, ' + why if why else 'kept'}")
        return 0
    if nested:
        slots, mem = _held(os.environ[HELD_VAR])
        print(
            f"check_all: already inside a heavy-lock hold ({slots} slots, {mem:g} GB, "
            f"{HELD_VAR}); running without queueing again (do not wrap check_all, "
            "it locks itself)",
            flush=True,
        )
        if a.slots > slots or a.mem > mem:
            print(
                f"check_all: warning: wants {a.slots} slots, {a.mem:g} GB, more than "
                "the hold; running anyway",
                flush=True,
            )
    print(f"check_all: log {log}", flush=True)
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    sys.exit(main())
