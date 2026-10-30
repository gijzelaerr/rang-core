"""P11: the live test copies equal their source test functions (imports aside).

Usage: python check_tests.py REPO testsplit-report.json SOURCE_DIR
SOURCE_DIR holds the original test files (tests/ before the move, history/tests after).
"""
import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from p11map import MAP  # noqa: E402
from rewire import strip_imports  # noqa: E402

repo, report, src_dir = Path(sys.argv[1]), json.load(open(sys.argv[2])), Path(sys.argv[3])


def segs(text):
    text = strip_imports(text)
    lines = text.splitlines(keepends=True)
    out = {}
    for node in ast.parse(text).body:
        name = getattr(node, "name", None) or ",".join(
            n.id for t in getattr(node, "targets", []) for n in ast.walk(t) if isinstance(n, ast.Name))
        if not name:
            continue
        start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        out[name] = "".join(lines[start - 1 : node.end_lineno])
    return out


bad = 0
total = 0
for src, info in report.items():
    if not info.get("kept") or not info["dest"]:
        continue
    a = segs((src_dir / src).read_text())
    b = segs((repo / "tests" / info["dest"]).read_text())
    for name, seg in b.items():
        total += 1
        orig = a.get(name)
        for m, d in MAP.items():
            if d:
                seg = seg.replace(f"rangtoy.{d}", f"rangtoy.{m}")
        if orig is None or seg != orig:
            bad += 1
            print("DIFF", info["dest"], name)
print(f"{total} definitions checked, {bad} differ")
sys.exit(1 if bad else 0)
