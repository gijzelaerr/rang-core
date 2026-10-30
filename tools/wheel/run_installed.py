"""Run an example driver against the installed rangtoy wheel.

    python tools/wheel/run_installed.py SCRIPT [ARGS...]

Some drivers put the checkout's `python/` first on `sys.path`; importing
rangtoy here first pins the installed package in `sys.modules`, so their
later imports resolve to the wheel. Refuses to run unless rangtoy and the
extension backend come from site-packages, before and after the driver
(research/wheel.md).

With RANG_WHEEL_CHECKOUT set to the checkout, the modules that locate the
checkout from their own file (`ROOT = Path(__file__).parents[2]`, and
`core.core_root()` for the Tricolour static masks in core/data) are pointed
at it: every module-level Path under the package's would-be root is
rewritten to the same relative path under the checkout. Code and kernels
still come from the wheel; the rewritten names are printed, and
research/wheel.md lists which steps need this.
"""

import importlib
import os
import runpy
import sys
import sysconfig
from pathlib import Path

import rangtoy
from rangtoy import core

SITE = Path(sysconfig.get_paths()["purelib"]).resolve()
CHECKOUT_MODULES = ("core_imaging", "core_campaign", "core_cli")


def check():
    package = Path(rangtoy.__file__).resolve()
    if not package.is_relative_to(SITE):
        raise SystemExit(f"rangtoy imported from {package}, not {SITE}")
    if core.backend_name() != "extension":
        raise SystemExit(f"backend is {core.backend_name()}, not the extension")
    library = core.library_path()
    if not library.is_relative_to(SITE):
        raise SystemExit(f"extension loaded from {library}, not {SITE}")
    return library


def point_at_checkout(checkout):
    checkout = Path(checkout).resolve()
    core.core_root = lambda: checkout / "core"
    print(f"shim: rangtoy.core.core_root -> {checkout / 'core'}")
    for name in CHECKOUT_MODULES:
        try:
            module = importlib.import_module(f"rangtoy.{name}")
        except ImportError as exc:  # an extra the driver does not need
            print(f"shim: rangtoy.{name} not importable ({exc}); left alone")
            continue
        old = Path(module.__file__).resolve().parents[2]
        for key, value in list(vars(module).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                setattr(module, key, checkout / value.relative_to(old))
                print(f"shim: rangtoy.{name}.{key} -> {getattr(module, key)}")
    # The frozen trend ablation hashes the source tree into its receipt
    # (`flagging_next.source_receipts`, found from the module's own file): hash
    # the checkout's tree instead, plus the extension that actually runs
    # (task P7; the kernels are the wheel's).
    try:
        from rangtoy import flagging_next, projector
    except ImportError as exc:
        print(f"shim: rangtoy.flagging_next not importable ({exc}); left alone")
        return
    from hashlib import sha256

    def source_receipts():
        paths = list((checkout / "python/rangtoy").glob("*.py"))
        paths += list((checkout / "src").glob("*.rs"))
        paths += list((checkout / "recipes").glob("tv-flagging*.yaml"))
        paths += [
            p
            for p in (checkout / "tools/flagging").rglob("*")
            if p.is_file()
            and (p.suffix in (".py", ".sh", ".txt") or p.name == "Dockerfile")
        ]
        paths += [checkout / n for n in ("Cargo.toml", "Cargo.lock", "pyproject.toml")]
        paths.append(Path(projector._native_library()._name).resolve())
        return {str(p): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

    flagging_next.source_receipts = source_receipts
    print(f"shim: rangtoy.flagging_next.source_receipts -> the tree of {checkout}")


if __name__ == "__main__":
    print(f"wheel: rangtoy {Path(rangtoy.__file__).parent} extension {check()}")
    if os.environ.get("RANG_WHEEL_CHECKOUT"):
        point_at_checkout(os.environ["RANG_WHEEL_CHECKOUT"])
    script = sys.argv[1]
    sys.argv = sys.argv[1:]
    sys.path.insert(0, str(Path(script).resolve().parent))
    try:
        runpy.run_path(script, run_name="__main__")
    finally:
        print(f"wheel after the run: extension {check()}")
