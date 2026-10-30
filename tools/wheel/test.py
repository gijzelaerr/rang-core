"""Test an installed rangtoy wheel on the current OS, cargo absent.

Usage:
    python tools/wheel/test.py WHEEL_OR_BUILD_DIR OUT_DIR
        [--python VERSION_OR_PATH] [--ctypes-lib PATH] [--no-ctypes]

Cross-platform companion of tools/wheel/test.sh (research/x1-crossplatform.md)
and the test step of .github/workflows/wheels.yml on Linux, macOS and
Windows. WHEEL_OR_BUILD_DIR is a .whl or a directory from
tools/wheel/build.py (its dist/*.whl and ctypes/ library are used). Steps,
logs in OUT_DIR (which must not exist), wall times in OUT_DIR/timings.tsv:

  venv     a fresh venv: `uv venv` and `uv pip install` from public PyPI when
           uv is on PATH, else `python -m venv` and pip
  install  the wheel with its test and imaging extras
  import   `import rangtoy._core, rangtoy.core` in isolated mode (-I) from
           OUT_DIR, with an environment whose PATH has every directory that
           holds cargo removed (asserted) and no RANG_*, PYTHONPATH or
           VIRTUAL_ENV
  smoke    tools/wheel/smoke.py in the same environment: the extension from
           site-packages is the backend and a fused pass runs
  pytest   tests/test_core_backends.py from the source tree against the
           installed wheel through tools/wheel/pytest_wheel.py, the same
           environment; the ctypes half uses the C ABI library named by
           --ctypes-lib (or found in the build directory). With --no-ctypes
           the tests that need it skip with "no C ABI library"; any other
           skip than that one and the missing MS oracle fails the step.

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
ALLOWED_SKIPS = re.compile(r"MS (oracle|fixture) not present|fixture MS not present")
NO_CTYPES_SKIP = re.compile(r"no C ABI library")


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
    parser.add_argument("--ctypes-lib", type=Path, default=None)
    parser.add_argument("--no-ctypes", action="store_true")
    args = parser.parse_args()
    source = args.wheel.resolve()
    if source.is_dir():
        wheels = sorted((source / "dist").glob("*.whl")) or sorted(source.glob("*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"expected one wheel in {source}, found {wheels}")
        wheel = wheels[0]
        found = (
            sorted((source / "ctypes").glob("*"))
            if (source / "ctypes").is_dir()
            else []
        )
        if args.ctypes_lib is None and found:
            args.ctypes_lib = found[0]
    else:
        wheel = source
    ctypes_lib = None if args.no_ctypes else args.ctypes_lib
    if not args.no_ctypes and (ctypes_lib is None or not ctypes_lib.is_file()):
        raise SystemExit("pass --ctypes-lib PATH (core's C ABI library) or --no-ctypes")
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
    else:
        interpreter = args.python or sys.executable
        ok = run("venv", [interpreter, "-m", "venv", venv], base_env)
        install = [python, "-m", "pip", "install", "-q"]
        install += ["--index-url", base_env["UV_INDEX_URL"]]
    if not ok:
        return 1
    if not run("install", install + [f"{wheel}[test,imaging]"], base_env):
        return 1
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
                "import sys, rangtoy._core, rangtoy.core as c; "
                "print(sys.version.split()[0], c.backend_name(), c.library_path())"
            ),
        ],
        clean,
    )
    run("smoke", [python, "-I", ROOT / "tools" / "wheel" / "smoke.py"], clean)

    def skips(text):
        allowed = ALLOWED_SKIPS
        if ctypes_lib is None:
            allowed = re.compile(f"{ALLOWED_SKIPS.pattern}|{NO_CTYPES_SKIP.pattern}")
        bad = [
            line
            for line in text.splitlines()
            if line.startswith("SKIPPED") and not allowed.search(line)
        ]
        return "unexpected skips:\n" + "\n".join(bad) if bad else None

    env = dict(clean)
    env["PYTHONPATH"] = str(ROOT / "tools" / "wheel")
    if ctypes_lib is not None:
        env["RANG_WHEEL_CTYPES_LIB"] = str(ctypes_lib.resolve())
    else:
        env["RANG_WHEEL_NO_CTYPES"] = "1"
    run(
        "pytest",
        [python, "-m", "pytest", "-p", "pytest_wheel", "-p", "no:cacheprovider"]
        + ["-o", "pythonpath=", "-rs", "-q", "tests/test_core_backends.py"],
        env,
        cwd=ROOT,
        check_output=skips,
    )
    print("## overall:", "FAIL " + ", ".join(failed) if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
