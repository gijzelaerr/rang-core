"""Pytest plugin for testing the installed wheel from the source tree.

    PYTHONPATH=tools/wheel python -m pytest -p pytest_wheel -o pythonpath= \
        tests/test_core_backends.py tests/test_toy.py tests/test_p7_architecture.py

(tools/wheel/test.py and test.sh run this.) Fails the session unless rangtoy
and `rangtoy._core` are imported from the venv's site-packages (not the
checkout's `python/`, which pyproject's `pythonpath` would otherwise put
first; `-o pythonpath=` clears it). Before task P7 it also pointed the ctypes
half of the backend tests at a C ABI library built beside the wheel; that
half is gone (research/p7-architecture.md), so `RANG_WHEEL_CTYPES_LIB` and
`RANG_WHEEL_NO_CTYPES` are ignored.
"""

import sysconfig
from pathlib import Path

import pytest

SITE = Path(sysconfig.get_paths()["purelib"]).resolve()


def pytest_configure(config):
    import rangtoy
    from rangtoy import _core

    for name, module in (("rangtoy", rangtoy), ("rangtoy._core", _core)):
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(SITE):
            raise pytest.UsageError(f"{name} imported from {path}, not {SITE}")
    print(f"\nwheel: {Path(_core.__file__).resolve()}")
