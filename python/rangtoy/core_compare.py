"""Field-by-field comparison of a core result with an archived result.

A caller supplies `classify(path) -> class`, where path is the list of keys and
list indices from the root. Classes:

- "excluded": not compared (wall times, paths, MS audits, ...);
- "exact": equal values (strings, integers, booleans, None, decisions);
- "float": relative difference within `float_tol` (absolute if the oracle is 0);
- "difference": within `float_tol` relative or `difference_abs` absolute, for
  differences of nearly equal quantities;
- "reported": the difference is recorded but never fails.

Every archived field must exist in the core result unless it is excluded.
"""

import math


def _numeric(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check(cls, archived, core, float_tol, difference_abs):
    if archived is None or core is None:
        return archived is None and core is None, None
    if cls == "exact" or not (_numeric(archived) and _numeric(core)):
        return archived == core, None
    if not (math.isfinite(archived) and math.isfinite(core)):
        return archived == core, None
    diff = abs(core - archived)
    rel = diff / abs(archived) if archived else diff
    if cls == "reported":
        return True, rel
    if cls == "difference":
        return rel <= float_tol or diff <= difference_abs, rel
    return rel <= float_tol, rel


def compare(archived, core, classify, *, float_tol=1e-9, difference_abs=1e-12, root=()):
    """Return {"classes": {...}, "excluded": n, "failures": [...]}."""
    report = {"classes": {}, "excluded": 0, "failures": []}

    def walk(a, c, path):
        cls = classify(path) if path else "exact"
        if cls == "excluded":
            report["excluded"] += 1
            return
        if isinstance(a, dict):
            if not isinstance(c, dict):
                report["failures"].append({"path": path, "reason": "not a dict"})
                return
            for key, value in a.items():
                if key not in c:
                    if classify([*path, key]) == "excluded":
                        report["excluded"] += 1
                    else:
                        report["failures"].append(
                            {"path": [*path, key], "reason": "missing"}
                        )
                    continue
                walk(value, c[key], [*path, key])
            return
        if isinstance(a, list) and not (cls != "exact" and all(_numeric(x) for x in a)):
            if not isinstance(c, list) or len(c) != len(a):
                report["failures"].append(
                    {"path": path, "reason": "list length differs"}
                )
                return
            for i, (x, y) in enumerate(zip(a, c, strict=True)):
                walk(x, y, [*path, i])
            return
        if isinstance(a, list):
            good = isinstance(c, list) and len(c) == len(a)
            rels = []
            if good:
                for x, y in zip(a, c, strict=True):
                    ok, rel = _check(cls, x, y, float_tol, difference_abs)
                    good &= ok
                    if rel is not None:
                        rels.append(rel)
            ok, rel = good, (max(rels) if rels else None)
        else:
            ok, rel = _check(cls, a, c, float_tol, difference_abs)
        stats = report["classes"].setdefault(cls, {"compared": 0, "max_rel": 0.0})
        stats["compared"] += 1
        if rel is not None:
            stats["max_rel"] = max(stats["max_rel"], rel)
        if not ok:
            report["failures"].append(
                {"path": path, "class": cls, "archived": a, "core": c}
            )

    walk(archived, core, list(root))
    return report


def key_and_parent(path):
    """The innermost string key and its nearest string ancestor."""
    keys = [p for p in path if isinstance(p, str)]
    return (keys[-1] if keys else None), (keys[-2] if len(keys) > 1 else None)
