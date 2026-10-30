"""P11: which top-level names of the frozen modules live code needs (AST closure).

Usage: python closure.py REPO OUT.json
"""
import ast
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
pkg = repo / "python" / "rangtoy"
FROZEN = sorted(
    [p.stem for p in pkg.glob("flagging*.py")] + ["imaging_sensitivity"]
)


def top_defs(tree):
    """name -> node for top-level definitions (functions, classes, assignments, imports)."""
    defs = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        defs[n.id] = node
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                defs[(a.asname or a.name).split(".")[0]] = node
    return defs


def frozen_import_map(tree, here_is_pkg):
    """alias -> (module, name or None) for imports of frozen modules in a file."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level and here_is_pkg:
                base = mod
            elif node.level == 2:
                base = mod
            elif mod.startswith("rangtoy."):
                base = mod[len("rangtoy."):]
            elif mod == "rangtoy":
                base = ""
            elif node.level:
                base = mod
            else:
                continue
            for a in node.names:
                if base == "":
                    if a.name in FROZEN:
                        out[a.asname or a.name] = (a.name, None)
                elif base in FROZEN:
                    out[a.asname or a.name] = (base, a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("rangtoy.") and a.name[8:] in FROZEN:
                    out[a.asname or a.name] = (a.name[8:], None)
    return out


def uses(tree, imap):
    """set of (module, name) used through the import map."""
    need = set()
    for alias, (mod, name) in imap.items():
        if name is not None:
            need.add((mod, name))
    mod_alias = {a: m for a, (m, n) in imap.items() if n is None}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in mod_alias:
                need.add((mod_alias[node.value.id], node.attr))
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
            # rangtoy.flagging_x.name
            v = node.value
            if isinstance(v.value, ast.Name) and v.value.id == "rangtoy" and v.attr in FROZEN:
                need.add((v.attr, node.attr))
    return need


trees = {m: ast.parse((pkg / f"{m}.py").read_text()) for m in FROZEN}
defs = {m: top_defs(t) for m, t in trees.items()}
imaps = {m: frozen_import_map(t, True) for m, t in trees.items()}


def deps(mod, name):
    node = defs[mod].get(name)
    if node is None:
        return set()
    out = set()
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        if name in imaps[mod]:
            m2, n2 = imaps[mod][name]
            if n2 is not None:
                out.add((m2, n2))
        return out
    names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    for n in names:
        if n in imaps[mod]:
            m2, n2 = imaps[mod][n]
            if n2 is None:
                for a in ast.walk(node):
                    if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) and a.value.id == n:
                        out.add((m2, a.attr))
            else:
                out.add((m2, n2))
        elif n in defs[mod] and n != name:
            out.add((mod, n))
    return out


live_roots = {}
skip_tests = set()
for p in sorted(list(pkg.rglob("*.py")) + list((repo / "examples").glob("*.py"))
                + list((repo / "tests").glob("*.py")) + list((repo / "tools").rglob("*.py"))):
    rel = p.relative_to(repo).as_posix()
    if p.parent == pkg and p.stem in FROZEN:
        continue
    tree = ast.parse(p.read_text())
    imap = frozen_import_map(tree, rel.startswith("python/rangtoy"))
    if not imap:
        continue
    live_roots[rel] = sorted(f"{m}.{n}" for m, n in uses(tree, imap))

MOVED_TESTS = {f"tests/test_{m}.py" for m in FROZEN} | {"tests/test_flagging_trend_review.py"}
EXCLUDE = set(sys.argv[3].split(",")) if len(sys.argv) > 3 and sys.argv[3] else set()
result = {}
for scope in ("core", "live"):
    roots = set()
    for rel, names in live_roots.items():
        if scope == "core" and not rel.startswith("python/rangtoy"):
            continue
        if rel in MOVED_TESTS or rel in EXCLUDE:
            continue
        for s in names:
            m, n = s.split(".", 1)
            roots.add((m, n))
    seen = set()
    stack = list(roots)
    while stack:
        item = stack.pop()
        if item in seen:
            continue
        seen.add(item)
        stack.extend(deps(*item) - seen)
    result[scope] = sorted(f"{m}.{n}" for m, n in seen)
json.dump({"frozen": FROZEN, "roots": live_roots, "closure": result}, open(sys.argv[2], "w"), indent=1)
for scope, items in result.items():
    by = {}
    for s in items:
        m, n = s.split(".", 1)
        by.setdefault(m, []).append(n)
    print("==", scope)
    for m in FROZEN:
        lines = sum(getattr(defs[m][n], "end_lineno", 0) - getattr(defs[m][n], "lineno", 0) + 1 for n in set(by.get(m, [])) if n in defs[m] and not isinstance(defs[m][n], (ast.Import, ast.ImportFrom)))
        print(f"  {m}: {len(by.get(m, []))}/{len(defs[m])} ~{lines} lines  {' '.join(by.get(m, []))}")
