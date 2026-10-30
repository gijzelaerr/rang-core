"""P11: write the verbatim extracts `python/rangtoy/core_<x>.py` of the frozen modules.

Usage: python gen_extract.py REPO closure.json COMMIT [--write]

For every frozen module with needed names (closure.json "live"), the extract
holds, in source order, every top-level definition that binds a needed name,
copied byte for byte (decorators and the comment lines directly above
included). Only import statements differ: frozen modules are replaced by
their extracts, unused names are dropped (a needed name that the module only
re-exports is kept). In-body imports of frozen modules are rewritten in place
and listed.
"""

import ast
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from p11map import MAP  # noqa: E402

repo = Path(sys.argv[1])
closure = json.load(open(sys.argv[2]))["closure"]["live"]
commit = sys.argv[3]
write = "--write" in sys.argv
pkg = repo / "python" / "rangtoy"

need = {}
for item in closure:
    m, n = item.split(".", 1)
    need.setdefault(m, set()).add(n)


def bound_names(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)}
    return set()


def segment(lines, node):
    start = node.lineno
    if getattr(node, "decorator_list", None):
        start = min(d.lineno for d in node.decorator_list)
    while start > 1 and lines[start - 2].lstrip().startswith("#"):
        start -= 1
    return "".join(lines[start - 1 : node.end_lineno])


def rewrite_module(name):
    return MAP.get(name) if name in MAP else name


report = {"commit": commit, "modules": {}}
for src, dest in MAP.items():
    names = need.get(src, set())
    path = pkg / f"{src}.py"
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    if not dest:
        assert not names - {"np"}, (src, names)
        continue
    selected = []
    odd = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and node is tree.body[0]:
            continue
        b = bound_names(node)
        if not b:
            odd.append(f"{type(node).__name__} line {node.lineno}")
            continue
        if b & names:
            selected.append(node)
    used = set()
    for node in selected:
        for n in ast.walk(node):
            if isinstance(n, ast.Name):
                used.add(n.id)
    # import header
    header_imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            keep = [a for a in node.names if (a.asname or a.name).split(".")[0] in used | names]
            if keep:
                header_imports.append(
                    "import " + ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in keep)
                )
        elif isinstance(node, ast.ImportFrom):
            keep = [a for a in node.names if (a.asname or a.name) in used | names]
            if not keep:
                continue
            if node.level == 0:
                header_imports.append(
                    f"from {node.module} import "
                    + ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in keep)
                )
            elif node.module is None:
                for a in keep:
                    if a.name in MAP:
                        assert MAP[a.name], (src, a.name)
                        header_imports.append(f"from . import {MAP[a.name]} as {a.asname or a.name}")
                    else:
                        header_imports.append(
                            f"from . import {a.name}" + (f" as {a.asname}" if a.asname else "")
                        )
            else:
                mod = rewrite_module(node.module)
                assert mod, (src, node.module)
                # a needed name the copies do not use is a re-export
                plain = [a for a in keep if a.asname or a.name in used]
                reexport = [a for a in keep if not a.asname and a.name not in used]
                if plain:
                    header_imports.append(
                        f"from .{mod} import "
                        + ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in plain)
                    )
                for a in reexport:
                    header_imports.append(f"from .{mod} import {a.name}  # noqa: F401 (re-export)")
    # in-body imports of frozen modules
    rewrites = []
    bodies = []
    for node in selected:
        seg = segment(lines, node)
        for n in ast.walk(node):
            if isinstance(n, ast.ImportFrom) and n.level and n.module in MAP:
                old = f"from .{n.module} import"
                new = f"from .{MAP[n.module]} import"
                assert old in seg
                seg = seg.replace(old, new)
                rewrites.append({"definition": sorted(bound_names(node)), "old": old, "new": new})
            if isinstance(n, ast.ImportFrom) and n.level and n.module is None:
                assert not any(a.name in MAP for a in n.names), (src, n.lineno)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and any(
                f"{m}.py" in n.value or f"rangtoy.{m}" in n.value for m in MAP
            ):
                rewrites.append({"definition": sorted(bound_names(node)), "string": n.value})
        bodies.append(seg)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    doc = ast.get_docstring(tree) or ""
    first = doc.strip().splitlines()[0] if doc.strip() else ""
    defined = sorted(set().union(*(bound_names(n) for n in selected)))
    header = (
        f'"""{first}\n\n'
        f"Verbatim extract of the frozen `rangtoy.{src}` (big plan task P11,\n"
        f"research/p11-extract.md): the definitions the live chains use, copied\n"
        f"byte for byte in source order from python/rangtoy/{src}.py at commit\n"
        f"{commit} (now history/python/{src}.py),\n"
        f"sha256 {digest}.\n"
        f"Only import statements differ: frozen modules are replaced by their core\n"
        f"extracts. tests/test_p11_extract.py checks every definition against the\n"
        f"history copy.\n"
        f'"""\n'
    )
    out = header + "\n" + "\n".join(header_imports) + "\n\n\n" + "\n\n".join(b.rstrip("\n") + "\n" for b in bodies)
    # two blank lines between top-level definitions
    out = header + "\n" + "\n".join(header_imports) + "\n\n\n" + "\n\n\n".join(b.rstrip("\n") for b in bodies) + "\n"
    target = pkg / f"{dest}.py"
    if write:
        target.write_text(out)
    report["modules"][src] = {
        "dest": dest,
        "source_sha256": digest,
        "source_lines": len(lines),
        "extract_lines": out.count("\n"),
        "definitions": defined,
        "needed": sorted(names),
        "in_body_rewrites": rewrites,
        "skipped_top_level": odd,
    }
    print(f"{src:32s} -> {dest:22s} {len(lines):5d} -> {out.count(chr(10)):5d} lines, {len(defined)} defs"
          + (f"  rewrites={rewrites}" if rewrites else "") + (f"  odd={odd}" if odd else ""))
json.dump(report, open(Path(sys.argv[2]).with_name("extract-report.json"), "w"), indent=1)
