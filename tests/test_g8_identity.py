"""G8 (research/g8-wheel.md): the console script against the source build.

Checkout only (not in the wheel's subset): needs core/target/release/gemclean,
which `rang.check` builds (step core-build) beside the extension (ext-build).
Both are built from the same commit with the same flags, so the FITS files
must be byte-identical, the exit codes equal and the output equal line by
line except for times."""

import os
import re
import sys
from pathlib import Path

import pytest
from test_g8_gemclean import FILES, SMALL, run, script, tiny_ms

ROOT = Path(__file__).resolve().parents[1]
BINARY = (
    ROOT / "core/target/release" / ("gemclean.exe" if os.name == "nt" else "gemclean")
)

pytestmark = pytest.mark.skipif(not BINARY.is_file(), reason=f"no {BINARY}")

TIMES = re.compile(r"\d+(\.\d+)? ?(s|ms|min)\b|\d+\.\d+ GB|\d+ MB")


def lines(text):
    return [TIMES.sub("#", ln) for ln in text.splitlines()]


def test_the_files_and_output_equal_the_source_builds(tmp_path):
    ms = tiny_ms(tmp_path / "x.ms")
    # The same relative -name in two directories, so the output can match.
    for d in ("b", "s"):
        (tmp_path / d).mkdir()
    a = run([BINARY, "-name", "g", *SMALL, "-j", "2", ms], cwd=tmp_path / "b")
    b = run([script(), "-name", "g", *SMALL, "-j", "2", ms], cwd=tmp_path / "s")
    assert a.returncode == b.returncode == 0, a.stderr + b.stderr
    for kind in FILES:
        x = (tmp_path / "b" / f"g-{kind}.fits").read_bytes()
        assert x == (tmp_path / "s" / f"g-{kind}.fits").read_bytes(), kind
    assert lines(a.stdout) == lines(b.stdout)
    assert a.stderr == b.stderr
    for argv in (["-version"], [], ["-nope", "x.ms"]):
        x, y = run([BINARY, *argv]), run([sys.executable, "-m", "rang.gemclean", *argv])
        assert (x.returncode, x.stdout, x.stderr) == (y.returncode, y.stdout, y.stderr)
