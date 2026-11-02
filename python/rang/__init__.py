"""Run Rust calibration experiments from Python.

Rust owns the numerical work; Python owns configuration, campaigns, tables and
plotting. Every kernel, the pointing toy included, is in the compiled
extension `rang._core` (research/p7-architecture.md): importing this
package or calling a kernel never runs Cargo. `run_experiment` and
`toy_output` call the pointing toy's command line inside the extension; its
output is byte-identical to the `rang-toy` binary's stdout, which remains for
command-line use (pass `binary=` or set RANG_TOY_BIN to run a binary instead).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path


def _version() -> str:
    """The installed distribution's version, else (a checkout on
    `sys.path` with no install) the `[project]` version of the checkout's
    pyproject.toml; pyproject.toml is the one source (research/w4-5-release.md)."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("rang-core")
    except PackageNotFoundError:
        pass
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    # A regex, not tomllib: Python 3.10 has no tomllib.
    project = re.search(
        r"^\[project\]\n(.*?)(?=^\[|\Z)", text, re.MULTILINE | re.DOTALL
    )
    if project and re.search(r'^name = "rang-core"$', project.group(1), re.MULTILINE):
        found = re.search(r'^version = "([^"]+)"$', project.group(1), re.MULTILINE)
        if found:
            return found.group(1)
    return "unknown"


__version__ = _version()


def toy_output(*args: str) -> str:
    """What `rang-toy ARGS...` prints on stdout (with its final newline),
    computed in the extension; e.g. `toy_output("--pointing-reference")`."""
    from .core import extension

    ok, text = extension().toy_cli([str(a) for a in args])
    if not ok:
        raise RuntimeError(f"rang-toy: {text}")
    return text + "\n"


def run_experiment(
    *,
    seed: int = 7,
    noise: float = 0.01,
    pointing: float = 0.6,
    beam_error: float = 0.0,
    budget: float = 0.01,
    target_flux: float = 0.02,
    binary: str | Path | None = None,
) -> dict:
    """Return one reproducible experiment as a dictionary.

    noise: Jy per real/imaginary component. pointing: sigma per axis in arcmin.
    beam_error: fractional true beam width mismatch. budget: local operator-norm
    distortion bound, not an image accuracy guarantee. See examples/README.md.
    `command[0]` and `binary_sha256` name the binary that ran: the extension,
    or the `rang-toy` executable when one is given.
    """
    args = []
    for key, value in {
        "seed": seed,
        "noise": noise,
        "pointing": pointing,
        "beam-error": beam_error,
        "budget": budget,
        "target-flux": target_flux,
    }.items():
        args.extend([f"--{key}", str(value)])
    configured = binary or os.environ.get("RANG_TOY_BIN")
    started = time.perf_counter()
    if configured:
        executable = Path(configured).resolve()
        completed = subprocess.run(
            [str(executable), *args], capture_output=True, text=True, check=False
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or "Rust experiment failed")
        stdout = completed.stdout
    else:
        from .core import library_path

        executable = library_path()
        stdout = toy_output(*args)
    result = json.loads(stdout)
    result["execution_seconds"] = time.perf_counter() - started
    result["binary_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    result["command"] = [str(executable), *args]
    return result


__all__ = ["__version__", "run_experiment", "toy_output"]
