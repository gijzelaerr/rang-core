"""P11: live copies of the frozen-module tests that use only extracted names.

Usage: python gen_tests.py REPO closure.json COMMIT [--write]

For each frozen test file (tests/test_<frozen>.py), the test functions whose
frozen names are all extracted are copied verbatim, with the module-level
helpers, fixtures and constants they use (source order), into
tests/test_<extract>.py. Import statements are repointed at the extracts (the
same rule as rewire.py); in-body imports and `"rangtoy.<frozen>"` strings in
copied code are repointed too and listed. Top-level expressions other than the
docstring (for example `pytest.importorskip`) and `pytestmark` are kept.
"""

import ast
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from p11map import MAP  # noqa: E402
from rewire import rewrite  # noqa: E402

repo = Path(sys.argv[1])
data = json.load(open(sys.argv[2]))
closure = set(data["closure"]["live"])
FROZEN = data["frozen"]
commit = sys.argv[3]
write = "--write" in sys.argv

SOURCES = {f"test_{m}.py": f"test_{MAP[m]}.py" for m in FROZEN if MAP[m]}
SOURCES["test_flagging_trend_review.py"] = "test_core_trend_run_review.py"
SOURCES["test_flagging_comparators.py"] = None


def imap_of(tree):
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            if mod == "rangtoy":
                for a in node.names:
                    if a.name in FROZEN:
                        out[a.asname or a.name] = (a.name, None)
            elif mod.startswith("rangtoy.") and mod[8:] in FROZEN:
                for a in node.names:
                    out[a.asname or a.name] = (mod[8:], a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("rangtoy.") and a.name[8:] in FROZEN:
                    out[a.asname or a.name] = (a.name[8:], None)
    return out


def bound(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)}
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {(a.asname or a.name).split(".")[0] for a in node.names}
    return set()


def names_in(node):
    out = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        out |= {a.arg for a in node.args.args + node.args.kwonlyargs}  # fixtures
    return out


def segment(lines, node):
    start = node.lineno
    if getattr(node, "decorator_list", None):
        start = min(d.lineno for d in node.decorator_list)
    while start > 1 and lines[start - 2].lstrip().startswith("#"):
        start -= 1
    return "".join(lines[start - 1 : node.end_lineno])


report = {}
for src, dest in SOURCES.items():
    path = repo / "tests" / src
    if not path.exists():
        continue
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    imap = imap_of(tree)
    defs = {}
    for node in tree.body:
        for b in bound(node):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                defs.setdefault(b, node)

    def frozen_used(node, seen):
        out = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and n.id in imap and imap[n.id][1] is not None:
                out.add(".".join(imap[n.id]))
            if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                    and n.value.id in imap and imap[n.value.id][1] is None):
                out.add(f"{imap[n.value.id][0]}.{n.attr}")
        for name in names_in(node):
            if name in defs and name not in seen:
                seen.add(name)
                out |= frozen_used(defs[name], seen)
        # in-body imports of frozen modules
        for n in ast.walk(node):
            if isinstance(n, ast.ImportFrom) and n.module and n is not node:
                inner = imap_of(ast.Module(body=[n], type_ignores=[]))
                for alias, (m, nm) in inner.items():
                    if nm is not None:
                        out.add(f"{m}.{nm}")
                    else:
                        for a in ast.walk(node):
                            if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) and a.value.id == alias:
                                out.add(f"{m}.{a.attr}")
        return out

    tests = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name.startswith(("test_", "Test"))]
    keep, move = [], {}
    for t in tests:
        used = frozen_used(t, set())
        missing = sorted(u for u in used if u not in closure)
        if missing:
            move[t.name] = missing
        else:
            keep.append(t)
    report[src] = {"dest": dest, "tests": len(tests), "kept": [t.name for t in keep], "moved_only": move}
    if not keep or not dest:
        print(f"{src}: 0 kept, {len(move)} history only")
        continue
    # helpers needed by kept tests (transitively)
    needed = set()
    stack = [t for t in keep]
    seen_nodes = set()
    while stack:
        node = stack.pop()
        if id(node) in seen_nodes:
            continue
        seen_nodes.add(id(node))
        for name in names_in(node):
            if name in defs and not name.startswith("test_"):
                needed.add(id(defs[name]))
                stack.append(defs[name])
    body_nodes = []
    for node in tree.body:
        if node in keep or id(node) in needed:
            body_nodes.append(node)
        elif isinstance(node, ast.Expr) and node is not tree.body[0]:
            body_nodes.append(node)
        elif isinstance(node, ast.Assign) and "pytestmark" in bound(node):
            body_nodes.append(node)
    used_names = set()
    for node in body_nodes:
        used_names |= names_in(node)
        for n in ast.walk(node):
            if isinstance(n, ast.Attribute):
                pass
    imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            keep_alias = [a for a in node.names if (a.asname or a.name).split(".")[0] in used_names]
            if keep_alias:
                imports.append("import " + ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in keep_alias))
        elif isinstance(node, ast.ImportFrom):
            keep_alias = [a for a in node.names if (a.asname or a.name) in used_names]
            if keep_alias:
                dots = "." * node.level
                imports.append(f"from {dots}{node.module or ''} import "
                               + ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in keep_alias))
    import_block = rewrite("\n".join(imports) + "\n")[0]
    rewrites = []
    segs = []
    for node in body_nodes:
        seg = segment(lines, node)
        new_seg, n = rewrite(seg) if any(isinstance(x, (ast.Import, ast.ImportFrom)) for x in ast.walk(node)) else (seg, 0)
        if new_seg != seg:
            rewrites.append({"definition": sorted(bound(node)) or [type(node).__name__], "kind": "in-body import"})
        for m in sorted(MAP, key=len, reverse=True):
            if MAP[m] and re.search(rf"rangtoy\.{m}\b", new_seg):
                new_seg = re.sub(rf"rangtoy\.{m}\b", f"rangtoy.{MAP[m]}", new_seg)
                rewrites.append({"definition": sorted(bound(node)), "kind": f"string rangtoy.{m}"})
        segs.append(new_seg.rstrip("\n"))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    doc = ast.get_docstring(tree) or ""
    first = doc.strip().splitlines()[0] if doc.strip() else f"Tests of the {dest[5:-3]} extract."
    header = (
        f'"""{first}\n\n'
        f"Live part of tests/{src} at commit {commit}\n"
        f"(now history/tests/{src},\n"
        f"sha256 {digest}):\n"
        f"the test functions that use only extracted names, with the helpers they\n"
        f"use, copied verbatim in source order; only import statements point at\n"
        f"the extracts (big plan task P11, research/p11-extract.md).\n"
        f'"""\n'
    )
    out = header + "\n" + import_block + "\n\n" + "\n\n\n".join(segs) + "\n"
    report[src].update({"source_sha256": digest, "rewrites": rewrites, "lines": out.count("\n")})
    if write:
        (repo / "tests" / dest).write_text(out)
    print(f"{src}: {len(keep)} kept -> {dest}, {len(move)} history only" + (f"  rewrites={rewrites}" if rewrites else ""))
json.dump(report, open(Path(sys.argv[2]).with_name("testsplit-report.json"), "w"), indent=1)
