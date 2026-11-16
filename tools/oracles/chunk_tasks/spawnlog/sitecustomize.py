# SPDX-License-Identifier: GPL-3.0-or-later
"""Timing hook for research/chunk-task-api.md section 5 (the spawn overhead).

On PYTHONPATH with RANG_CTA_TASKLOG set, it wraps rang.core_tasks.run when the
module is imported, in the parent and in every spawned worker (they inherit
the environment), and appends "pid unix_time stage kind" to the log at each
process's first task. Nothing else changes: the wrapper calls the original.
"""

import os
import sys
import time

_LOG = os.environ.get("RANG_CTA_TASKLOG")

if _LOG:
    import importlib.abc
    import importlib.machinery

    class _Hook(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name != "rang.core_tasks":
                return None
            spec = importlib.machinery.PathFinder.find_spec(name, path)
            if spec is None:
                return None
            sys.meta_path.remove(self)
            exec_orig = spec.loader.exec_module

            def exec_module(module):
                exec_orig(module)
                run = module.run
                first = [True]

                def wrapped(spec_, source=None):
                    if first[0]:
                        first[0] = False
                        with open(_LOG, "a", encoding="utf-8") as f:
                            f.write(
                                f"{os.getpid()} {time.time():.6f} "
                                f"{spec_.stage} {spec_.kind}\n"
                            )
                    return run(spec_, source)

                wrapped.__module__ = run.__module__
                wrapped.__name__ = run.__name__
                wrapped.__qualname__ = run.__qualname__
                wrapped.__doc__ = run.__doc__
                module.run = wrapped

            spec.loader.exec_module = exec_module
            return spec

    sys.meta_path.insert(0, _Hook())
