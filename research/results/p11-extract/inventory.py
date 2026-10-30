"""P11 inventory: per frozen module, which top-level definitions the live chains
execute (coverage) and which the extraction copies (closure), and where to.

Usage: python inventory.py REPO extract-report.json OUT.json COVERAGE.json [COVERAGE.json ...]
"""
import ast
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
report = json.load(open(sys.argv[2]))
out = sys.argv[3]
executed = {}
for cpath in sys.argv[4:]:
    cov = json.load(open(cpath))
    for path, rec in cov["files"].items():
        name = Path(path).name
        executed.setdefault(name, set()).update(rec["executed_lines"])
        executed.setdefault(name + ":statements", set()).update(
            rec["executed_lines"] + rec["missing_lines"]
        )

FROZEN = sorted([p.stem for p in (repo / "python/rangtoy").glob("flagging*.py")] + ["imaging_sensitivity"])
rows = {}
totals = {"statements": 0, "executed": 0}
for m in FROZEN:
    path = repo / "python/rangtoy" / f"{m}.py"
    tree = ast.parse(path.read_text())
    ex = executed.get(f"{m}.py", set())
    st = executed.get(f"{m}.py:statements", set())
    totals["statements"] += len(st)
    totals["executed"] += len(ex)
    info = report["modules"].get(m, {"dest": None, "definitions": []})
    defs = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            if isinstance(node, ast.ClassDef):
                # method bodies only: def lines run at import
                body = set()
                for child in node.body:
                    if isinstance(child, ast.FunctionDef):
                        body |= set(range(child.body[0].lineno, child.end_lineno + 1))
            else:
                body = set(range(node.body[0].lineno, node.end_lineno + 1))
            run = sorted(body & ex)
            defs.append(
                {
                    "name": node.name,
                    "lines": [node.lineno, node.end_lineno],
                    "statements": len(body & st),
                    "executed_statements": len(run),
                    "executed": bool(run),
                    "extracted": node.name in info["definitions"],
                }
            )
    rows[m] = {
        "dest": info["dest"],
        "statements": len(st),
        "executed_statements": len(ex),
        "functions_executed": sorted(d["name"] for d in defs if d["executed"]),
        "functions_extracted_not_executed": sorted(
            d["name"] for d in defs if d["extracted"] and not d["executed"]
        ),
        "functions_executed_not_extracted": sorted(
            d["name"] for d in defs if d["executed"] and not d["extracted"]
        ),
        "constants_extracted": sorted(
            set(info["definitions"]) - {d["name"] for d in defs}
        ),
        "definitions": defs,
    }
json.dump({"totals": totals, "modules": rows}, open(out, "w"), indent=1)
print(totals)
for m, r in rows.items():
    print(
        f"{m:30s} -> {str(r['dest']):22s} stmts {r['statements']:4d} exec {r['executed_statements']:4d}; "
        f"executed fns {len(r['functions_executed'])}; extracted-not-executed {r['functions_extracted_not_executed']}; "
        f"EXECUTED-NOT-EXTRACTED {r['functions_executed_not_extracted']}"
    )
