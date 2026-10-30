"""P11: per test function of the frozen-module tests, which frozen names it uses
and whether all of them are in the extraction set.

Usage: python testsplit.py REPO closure.json
"""
import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
repo = Path(sys.argv[1])
closure = set(json.load(open(sys.argv[2]))["closure"]["live"])
FROZEN = json.load(open(sys.argv[2]))["frozen"]
files = sorted({repo / f"tests/test_{m}.py" for m in FROZEN} | {repo / "tests/test_flagging_trend_review.py"})


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


summary = {}
for f in files:
    if not f.exists():
        continue
    tree = ast.parse(f.read_text())
    imap = imap_of(tree)
    top_helpers = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}

    def used(node, seen=None):
        seen = seen or set()
        out = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and n.id in imap and imap[n.id][1] is not None:
                out.add(".".join(imap[n.id]))
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in imap and imap[n.value.id][1] is None:
                out.add(f"{imap[n.value.id][0]}.{n.attr}")
            if isinstance(n, ast.Name) and n.id in top_helpers and n.id not in seen and not n.id.startswith("test_"):
                seen.add(n.id)
                out |= used(top_helpers[n.id], seen)
        return out

    rows = {}
    for name, node in top_helpers.items():
        if not name.startswith("test_"):
            continue
        u = used(node)
        missing = sorted(x for x in u if x not in closure)
        rows[name] = missing
    keep = [k for k, v in rows.items() if not v]
    move = [k for k, v in rows.items() if v]
    summary[f.name] = {"keep": keep, "move": {k: rows[k] for k in move}}
    print(f"{f.name}: {len(keep)} live-only, {len(move)} need frozen-only names")
json.dump(summary, open(Path(sys.argv[2]).with_name("testsplit.json"), "w"), indent=1)
