"""P11: repoint import statements of frozen modules at their extracts.

Usage: python rewire.py REPO FILE [FILE ...]   (rewrites in place)
       python rewire.py --check REPO BASE_REF FILE [FILE ...]
         checks that each file differs from BASE_REF only inside import statements

Only Import/ImportFrom statements that name a frozen module are rewritten;
`from . import flagging_x` becomes `from . import core_y as flagging_x` so that
the importing body does not change.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from p11map import MAP  # noqa: E402


def rewrite(text):
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    edits = []
    for node in ast.walk(tree):
        new = None
        indent = " " * node.col_offset if hasattr(node, "col_offset") else ""
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            dots = "." * node.level
            short = mod[len("rangtoy."):] if mod.startswith("rangtoy.") else mod
            if short in MAP and (node.level or mod.startswith("rangtoy.")):
                prefix = dots + ("rangtoy." if mod.startswith("rangtoy.") else "")
                names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in node.names)
                new = f"from {prefix}{MAP[short]} import {names}"
            elif (node.level and not mod) or mod == "rangtoy":
                if any(a.name in MAP for a in node.names):
                    prefix = dots if node.level else "rangtoy"
                    parts = []
                    for a in node.names:
                        if a.name in MAP:
                            parts.append(f"{MAP[a.name]} as {a.asname or a.name}")
                        else:
                            parts.append(a.name + (f" as {a.asname}" if a.asname else ""))
                    new = f"from {prefix} import {', '.join(parts)}"
        elif isinstance(node, ast.Import):
            if any(a.name.startswith("rangtoy.") and a.name[8:] in MAP for a in node.names):
                parts = []
                for a in node.names:
                    if a.name.startswith("rangtoy.") and a.name[8:] in MAP:
                        assert a.asname, "plain `import rangtoy.flagging_x` would change the bound name"
                        parts.append(f"rangtoy.{MAP[a.name[8:]]} as {a.asname}")
                    else:
                        parts.append(a.name + (f" as {a.asname}" if a.asname else ""))
                new = "import " + ", ".join(parts)
        if new is not None:
            edits.append((node.lineno, node.end_lineno, indent + new + "\n"))
    for start, end, new in sorted(edits, reverse=True):
        lines[start - 1 : end] = [new]
    return "".join(lines), len(edits)


def strip_imports(text):
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    drop = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            drop.update(range(node.lineno, node.end_lineno + 1))
    return "".join(line for i, line in enumerate(lines, 1) if i not in drop)


if __name__ == "__main__":
    if sys.argv[1] == "--check":
        repo, base, files = Path(sys.argv[2]), sys.argv[3], sys.argv[4:]
        bad = 0
        for f in files:
            old = subprocess.run(["git", "-C", str(repo), "show", f"{base}:{f}"], capture_output=True, text=True, check=True).stdout
            new = (repo / f).read_text()
            same = strip_imports(old) == strip_imports(new)
            bad += not same
            print(("ok   " if same else "DIFF ") + f)
        sys.exit(1 if bad else 0)
    repo = Path(sys.argv[1])
    for f in sys.argv[2:]:
        p = repo / f
        text, n = rewrite(p.read_text())
        p.write_text(text)
        print(f"{n:2d} import statements  {f}")
