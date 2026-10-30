"""Test an installed rang wheel on the current OS, cargo absent.

Usage:
    python tools/wheel/test.py WHEEL_OR_BUILD_DIR OUT_DIR
        [--python VERSION_OR_PATH] [--fixture-cache DIR]

Cross-platform companion of tools/wheel/test.sh (research/x1-crossplatform.md)
and the test step of .github/workflows/wheels.yml on Linux, macOS and
Windows. WHEEL_OR_BUILD_DIR is a .whl or a directory from
tools/wheel/build.py (its dist/*.whl is used). Steps,
logs in OUT_DIR (which must not exist), wall times in OUT_DIR/timings.tsv:

  venv     a fresh venv: `uv venv` and `uv pip install` from public PyPI when
           uv is on PATH, else `python -m venv` and pip
  install  the wheel with its test, imaging and casacure extras (the
           casacure sdist is never built: the extra's marker lists the
           platforms with wheels, and the install refuses to build it)
  fixture  with --fixture-cache DIR only: the public fixture outer_scans.zip
           (45 MB, SHA256 verified) through
           rang.notebook.data.download_fixture(DIR) in the venv; nothing is
           downloaded when a verified copy is there (research/t1-casacure-ci.md)
  import   `import rang._core, rang.core` in isolated mode (-I) from
           OUT_DIR, with an environment whose PATH has every directory that
           holds cargo removed (asserted) and no RANG_*, PYTHONPATH or
           VIRTUAL_ENV
  smoke    tools/wheel/smoke.py in the same environment: the extension from
           site-packages is the backend and a fused pass runs
  pytest   tests/test_core_backends.py tests/test_toy.py tests/test_p7_architecture.py
           tests/test_p12_rename.py tests/test_t1_casacure_oracle.py
           from the source tree against the installed wheel through
           tools/wheel/pytest_wheel.py, the same environment: the extension
           against the archive of the retired ctypes oracle, the pointing
           toy against the binary's archived output, and P7's no-cargo, GIL
           and panic checks (research/p7-architecture.md), and casacure as
           the second oracle of the core's table reader and writer (T1).
           With --fixture-cache the step gets RANG_FIXTURE=<the zip> (the one
           RANG_* variable set on purpose) and any skip fails it except
           casacure's frozen no-wheel cells (macOS x86_64, macOS arm64 on
           3.10); without it the skips for a missing MS or fixture are
           allowed too. `--ctypes-lib` and
           `--no-ctypes` are still accepted and change nothing.

Exit status 1 when a step fails.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = (
    "tests/test_core_backends.py tests/test_toy.py tests/test_p7_architecture.py"
    " tests/test_p12_rename.py tests/test_t1_casacure_oracle.py"
)
EXTRAS = "test,imaging,casacure"
# Always allowed: the toy bytes elsewhere (P7); the cells where casacure
# 3.8.35 has no wheel (T1, decided in tests/test_t1_casacure_oracle.py).
ALLOWED_SKIPS = re.compile(
    r"archived on Linux x86_64|casacure 3\.8\.35 has no wheel for this platform"
)
# Allowed only without --fixture-cache (no fixture, no MS oracle).
FIXTURE_SKIPS = re.compile(r"MS (oracle|fixture) not present|fixture MS not present")
FIXTURE_CODE = (
    "import sys; from rang.notebook.data import download_fixture; "
    "print(download_fixture(sys.argv[1]))"
)


def venv_python(venv):
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def without_cargo(environ):
    """A copy of `environ` without cargo on PATH and without rang settings."""
    env = {
        k: v
        for k, v in environ.items()
        if not k.startswith("RANG_")
        and k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_PREFIX")
    }
    key = next((k for k in env if k.upper() == "PATH"), "PATH")
    kept = [
        d
        for d in env.get(key, "").split(os.pathsep)
        if d and shutil.which("cargo", path=d) is None
    ]
    env[key] = os.pathsep.join(kept)
    if shutil.which("cargo", path=env[key]) is not None:
        raise SystemExit("could not remove cargo from PATH")
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("wheel", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--python", default=None, help="uv version or interpreter")
    parser.add_argument("--ctypes-lib", type=Path, default=None, help="no effect")
    parser.add_argument("--no-ctypes", action="store_true", help="no effect")
    parser.add_argument(
        "--fixture-cache",
        type=Path,
        default=None,
        help="download (or reuse) outer_scans.zip here and run the MS tests on it",
    )
    args = parser.parse_args()
    source = args.wheel.resolve()
    if source.is_dir():
        wheels = sorted((source / "dist").glob("*.whl")) or sorted(source.glob("*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"expected one wheel in {source}, found {wheels}")
        wheel = wheels[0]
    else:
        wheel = source
    out = args.out.resolve()
    if out.exists():
        raise SystemExit(f"{out} exists")
    out.mkdir(parents=True)
    venv = out / "venv"
    python = venv_python(venv)
    uv = shutil.which("uv")
    base_env = dict(os.environ)
    base_env.setdefault("UV_INDEX_URL", "https://pypi.org/simple")
    base_env.pop("VIRTUAL_ENV", None)
    clean = without_cargo(os.environ)
    timings = (out / "timings.tsv").open("w", encoding="utf-8")
    timings.write("step\tseconds\tstatus\n")
    failed = []

    def run(name, command, env, cwd=out, check_output=None):
        print(f"## {name}", flush=True)
        start = time.perf_counter()
        completed = subprocess.run(
            [str(c) for c in command],
            check=False,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        seconds = time.perf_counter() - start
        text = completed.stdout + completed.stderr
        (out / f"{name}.log").write_text(text, encoding="utf-8")
        status = completed.returncode
        if status == 0 and check_output is not None:
            problem = check_output(text)
            if problem:
                text += f"\n{problem}\n"
                status = 1
        timings.write(f"{name}\t{seconds:.2f}\t{status}\n")
        timings.flush()
        print("\n".join(text.strip().splitlines()[-3:]))
        print(f"   {seconds:.2f} s, exit {status}", flush=True)
        if status:
            failed.append(name)
        return status == 0

    if uv:
        target = args.python or sys.executable
        ok = run("venv", [uv, "venv", "-q", "-p", target, venv], base_env)
        install = [uv, "pip", "install", "--python", python]
        install += ["--no-build-package", "casacure"]
    else:
        interpreter = args.python or sys.executable
        ok = run("venv", [interpreter, "-m", "venv", venv], base_env)
        install = [python, "-m", "pip", "install", "-q"]
        install += ["--index-url", base_env["UV_INDEX_URL"]]
        install += ["--only-binary", "casacure"]
    if not ok:
        return 1
    if not run("install", install + [f"{wheel}[{EXTRAS}]"], base_env):
        return 1
    fixture = None
    if args.fixture_cache is not None:
        cache = args.fixture_cache.resolve()
        if not run("fixture", [python, "-I", "-c", FIXTURE_CODE, cache], clean):
            return 1
        fixture = cache / "outer_scans.zip"
    run(
        "freeze",
        [uv, "pip", "freeze", "--python", python]
        if uv
        else [python, "-m", "pip", "freeze"],
        base_env,
    )
    run(
        "import",
        [
            python,
            "-I",
            "-c",
            (
                "import sys, rang._core, rang.core as c; "
                "print(sys.version.split()[0], c.backend_name(), c.library_path())"
            ),
        ],
        clean,
    )
    run("smoke", [python, "-I", ROOT / "tools" / "wheel" / "smoke.py"], clean)

    def skips(text):
        bad = [
            line
            for line in text.splitlines()
            if line.startswith("SKIPPED")
            and not ALLOWED_SKIPS.search(line)
            and (fixture is not None or not FIXTURE_SKIPS.search(line))
        ]
        return "unexpected skips:\n" + "\n".join(bad) if bad else None

    env = dict(clean)
    env["PYTHONPATH"] = str(ROOT / "tools" / "wheel")
    if fixture is not None:
        env["RANG_FIXTURE"] = str(fixture)
    run(
        "pytest",
        [python, "-m", "pytest", "-p", "pytest_wheel", "-p", "no:cacheprovider"]
        + ["-o", "pythonpath=", "-rs", "-q", *TESTS.split()],
        env,
        cwd=ROOT,
        check_output=skips,
    )
    print("## overall:", "FAIL " + ", ".join(failed) if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
