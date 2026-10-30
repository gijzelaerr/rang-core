"""Inventory of the rang checkout for the S1 review (read-only).

Usage: python inventory.py <checkout> <out.json>
"""

import ast
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])


def lines(p):
    return sum(1 for _ in p.open(encoding="utf-8", errors="replace"))


def py_imports(p):
    tree = ast.parse(p.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level and p.parent.name == "rangtoy":
                if mod:
                    names.add(mod.split(".")[0])
                else:
                    names.update(a.name for a in node.names)
            elif mod.startswith("rangtoy"):
                parts = mod.split(".")
                if len(parts) > 1:
                    names.add(parts[1])
                else:
                    names.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("rangtoy."):
                    names.add(a.name.split(".")[1])
    # importlib strings: "rangtoy.core_x"
    names.update(re.findall(r"rangtoy\.([a-z_0-9]+)", p.read_text(encoding="utf-8")))
    return names


pkg = root / "python/rangtoy"
modules = sorted(p.stem for p in pkg.glob("*.py") if p.stem != "__init__")
modules_all = modules + ["__init__"]
users = {m: {"python": [], "examples": [], "tests": [], "recipes": [], "tools": []} for m in modules_all}
mod_imports = {}
for p in sorted(pkg.glob("*.py")):
    imp = {m for m in py_imports(p) if m in users and m != p.stem}
    mod_imports[p.stem] = sorted(imp)
    for m in imp:
        users[m]["python"].append(p.stem)
for group in ("examples", "tests"):
    for p in sorted((root / group).glob("*.py")):
        for m in py_imports(p):
            if m in users:
                users[m][group].append(p.name)
for p in sorted((root / "recipes").glob("*.yaml")):
    for m in set(re.findall(r"rangtoy\.([a-z_0-9]+)", p.read_text())):
        if m in users:
            users[m]["recipes"].append(p.name)
for p in sorted((root / "tools").rglob("*")):
    if p.is_file() and p.suffix in ("", ".sh", ".py") or p.name == "Dockerfile":
        try:
            text = p.read_text()
        except Exception:
            continue
        for m in set(re.findall(r"rangtoy[./]([a-z_0-9]+)", text)):
            if m in users:
                users[m]["tools"].append(str(p.relative_to(root)))


# transitive closure of what the core_* modules need
def closure(starts):
    seen, stack = set(), list(starts)
    while stack:
        m = stack.pop()
        if m in seen:
            continue
        seen.add(m)
        stack.extend(mod_imports.get(m, []))
    return seen


core_live = closure([m for m in modules if m.startswith("core")])
pymods = {}
for p in sorted(pkg.glob("*.py")):
    pymods[p.stem] = {
        "lines": lines(p),
        "imports": mod_imports[p.stem],
        "used_by": users[p.stem],
        "needed_by_core_closure": p.stem in core_live,
    }

rust = {}
for p in sorted(list((root / "src").glob("*.rs")) + list((root / "core/src").glob("*.rs")) + [root / "core/py/src/lib.rs"]):
    text = p.read_text()
    rust[str(p.relative_to(root))] = {
        "lines": lines(p),
        "extern_c": re.findall(r'extern "C" fn ([a-z_0-9]+)', text),
        "pyfunctions": len(re.findall(r"#\[pyfunction\]", text)),
        "tests": len(re.findall(r"#\[test\]", text)),
    }

recipes = {}
for p in sorted((root / "recipes").glob("*.yaml")):
    text = p.read_text()
    recipes[p.name] = {
        "lines": lines(p),
        "goquartical": "goquartical" in text or "quartical" in text.lower(),
        "images": sorted(set(re.findall(r"rang-[a-z-]+:local", text))),
        "rangtoy_modules": sorted(set(re.findall(r"rangtoy\.([a-z_0-9]+)", text))),
        "wsclean": "wsclean" in text.lower(),
        "tricolour": "tricolour" in text.lower(),
    }

examples = {p.name: {"lines": lines(p), "imports": sorted(m for m in py_imports(p) if m in users)} for p in sorted((root / "examples").glob("*.py"))}
tests = {p.name: {"lines": lines(p), "imports": sorted(m for m in py_imports(p) if m in users)} for p in sorted((root / "tests").glob("*.py"))}
tools = {str(p.relative_to(root)): lines(p) for p in sorted((root / "tools").rglob("*")) if p.is_file()}
dockerfiles = [str(p.relative_to(root)) for p in sorted(root.rglob("Dockerfile")) if "outputs" not in p.parts and ".venv" not in p.parts and "target" not in p.parts]
research = {p.name: lines(p) for p in sorted((root / "research").glob("*.md"))}
results = sorted(p.name for p in (root / "research/results").glob("*.json"))

summary = {
    "python_modules": len(pymods),
    "python_lines": sum(v["lines"] for v in pymods.values()),
    "python_core_lines": sum(v["lines"] for k, v in pymods.items() if k.startswith("core")),
    "python_flagging_lines": sum(v["lines"] for k, v in pymods.items() if k.startswith("flagging")),
    "core_closure": sorted(core_live),
    "rust_files": len(rust),
    "rust_lines": sum(v["lines"] for v in rust.values()),
    "examples": len(examples),
    "example_lines": sum(v["lines"] for v in examples.values()),
    "tests": len(tests),
    "test_lines": sum(v["lines"] for v in tests.values()),
    "recipes": len(recipes),
    "recipes_quartical": sorted(k for k, v in recipes.items() if v["goquartical"]),
    "dockerfiles": dockerfiles,
    "research_md": len(research),
    "research_md_lines": sum(research.values()),
    "results_json": len(results),
}
out.write_text(json.dumps({"summary": summary, "python": pymods, "rust": rust, "recipes": recipes,
                           "examples": examples, "tests": tests, "tools": tools}, indent=1) + "\n")
print(json.dumps(summary, indent=1))
