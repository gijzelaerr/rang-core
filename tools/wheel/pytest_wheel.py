"""Pytest plugin for testing the installed wheel from the source tree.

    PYTHONPATH=tools/wheel RANG_WHEEL_CTYPES_LIB=.../librang_core.so \
        python -m pytest -p pytest_wheel -o pythonpath= tests/test_core_backends.py

(tools/wheel/test.py runs this on every OS; RANG_WHEEL_NO_CTYPES=1 instead of
the library makes the comparisons against ctypes skip.)

1. Fails the session unless rangtoy and `rangtoy._core` are imported from the
   venv's site-packages (not the checkout's `python/`, which pyproject's
   `pythonpath` would otherwise put first; `-o pythonpath=` clears it).
2. The ctypes half of the backend tests deletes RANG_CORE_LIB and calls
   `core.build_core()`, which builds `core/` next to the package, a path that
   does not exist under site-packages. This plugin points `build_core` at the
   C ABI library named by RANG_WHEEL_CTYPES_LIB, built from the same commit
   with the same toolchain in the same container as the wheel
   (tools/wheel/build.sh), so the comparison is wheel extension against an
   independently linked C ABI, and cargo is not needed (research/wheel.md).
"""

import os
import sysconfig
from pathlib import Path

import pytest

SITE = Path(sysconfig.get_paths()["purelib"]).resolve()


def pytest_configure(config):
    import rangtoy
    from rangtoy import _core, core

    for name, module in (("rangtoy", rangtoy), ("rangtoy._core", _core)):
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(SITE):
            raise pytest.UsageError(f"{name} imported from {path}, not {SITE}")
    if os.environ.get("RANG_WHEEL_NO_CTYPES") == "1":
        # No C ABI library on this runner (tools/wheel/test.py --no-ctypes):
        # the tests that compare against ctypes skip, the rest run.
        def no_library():
            pytest.skip("no C ABI library (RANG_WHEEL_NO_CTYPES=1)")

        core.build_core = no_library
        print(f"\nwheel: {Path(_core.__file__).resolve()}\nctypes: none")
        return
    library = os.environ.get("RANG_WHEEL_CTYPES_LIB")
    if not library or not Path(library).is_file():
        raise pytest.UsageError(
            "set RANG_WHEEL_CTYPES_LIB to the C ABI library of core/ "
            "(librang_core.so, librang_core.dylib or rang_core.dll), "
            "or RANG_WHEEL_NO_CTYPES=1"
        )
    core.build_core = lambda: Path(library).resolve()
    print(f"\nwheel: {Path(_core.__file__).resolve()}\nctypes: {library}")
