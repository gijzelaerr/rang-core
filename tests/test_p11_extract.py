"""Task P11 (research/p11-extract.md): the `core_*` extracts of the frozen
campaign modules are verbatim, and no live code imports a frozen module.

The frozen modules are in `history/python/`, which is on no import path; these
tests read them as text.
"""

import ast
import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "python" / "rang"
HISTORY = ROOT / "history" / "python"
SOURCE = re.compile(
    r"from python/rangtoy/(\w+)\.py at commit\s+(\w+)\s+\(now history/python/(\w+)\.py\),"
    r"\s+sha256 ([0-9a-f]{64})\."
)
FROZEN = re.compile(r"^(flagging\w*|imaging_sensitivity)$")


def _extracts():
    out = {}
    for path in sorted(PKG.glob("core_*.py")):
        match = SOURCE.search(path.read_text(encoding="utf-8"))
        if match and "Verbatim extract of the frozen" in path.read_text(
            encoding="utf-8"
        ):
            out[path.stem] = match.groups()
    return out


EXTRACTS = _extracts()
INVERSE = {dest: source for dest, (source, *_rest) in EXTRACTS.items()}


def _segments(text):
    """name -> (index, source text with decorators and leading comments)."""
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    out, others = {}, []
    for index, node in enumerate(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [
                n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)
            ]
        else:
            others.append(node)
            continue
        start = node.lineno
        if getattr(node, "decorator_list", None):
            start = min(d.lineno for d in node.decorator_list)
        while start > 1 and lines[start - 2].lstrip().startswith("#"):
            start -= 1
        for name in names:
            out[name] = (index, "".join(lines[start - 1 : node.end_lineno]))
    return out, others, tree


def test_every_frozen_module_has_one_extract_or_none():
    assert len(EXTRACTS) == 20
    sources = [source for source, *_ in EXTRACTS.values()]
    assert len(set(sources)) == len(sources)
    for source, commit, history, _digest in EXTRACTS.values():
        assert source == history and commit == "2da566c"
        assert (HISTORY / f"{source}.py").is_file()
        assert not (PKG / f"{source}.py").exists() or source == "flagging"


@pytest.mark.parametrize("dest", sorted(EXTRACTS))
def test_extract_is_verbatim_copy_of_history(dest):
    source, _commit, _history, digest = EXTRACTS[dest]
    frozen = (HISTORY / f"{source}.py").read_bytes()
    assert hashlib.sha256(frozen).hexdigest() == digest
    original, _, _ = _segments(frozen.decode())
    text = (PKG / f"{dest}.py").read_text(encoding="utf-8")
    copied, others, tree = _segments(text)
    # Only the docstring and import statements besides the copies.
    assert isinstance(others[0], ast.Expr) and others[0] is tree.body[0]
    assert all(isinstance(n, (ast.Import, ast.ImportFrom)) for n in others[1:])
    assert copied
    order = []
    for name, (_, segment) in copied.items():
        # The in-body imports of frozen modules are the only rewritten lines.
        for new, old in INVERSE.items():
            segment = segment.replace(f"from .{new} import", f"from .{old} import")
        # Task P12 renamed the package directory (research/p12-rename.md): the
        # one copied line that names it is mapped back like the imports.
        segment = segment.replace('(root / "python/rang")', '(root / "python/rangtoy")')
        assert name in original, name
        assert segment == original[name][1], name
        order.append(original[name][0])
    assert order == sorted(order)
    # Imports name extracts, never a frozen module.
    for node in others[1:]:
        if isinstance(node, ast.ImportFrom):
            assert not FROZEN.match((node.module or "").split(".")[-1])
            assert not any(FROZEN.match(a.name) for a in node.names)


def _frozen_imports(path):
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            module = (node.module or "").removeprefix("rang.")
            if FROZEN.match(module.split(".")[-1]) and (
                node.level or node.module.startswith("rang.")
            ):
                found.append(node.lineno)
            if (node.level or node.module == "rang") and any(
                FROZEN.match(a.name) for a in node.names
            ):
                found.append(node.lineno)
        elif isinstance(node, ast.Import):
            if any(
                FROZEN.match(a.name.removeprefix("rang."))
                for a in node.names
                if a.name.startswith("rang.")
            ):
                found.append(node.lineno)
    return found


# Task C1's branch imports these three names from `.flagging` in this one file;
# `python/rang/flagging.py` re-exports them from `core_policy` until the
# coordinator switches that line at C1's merge (research/p11-extract.md).
C1_FILE = "python/rang/core_campaign_closure.py"
C1_NAMES = {"fixed_support_tv", "gain_tv", "polar_gauge"}


def _c1_allowed(rel, path, lineno):
    if rel != C1_FILE:
        return False
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.lineno == lineno:
            return (
                node.level == 1
                and node.module == "flagging"
                and {a.name for a in node.names} <= C1_NAMES
            )
    return False


def test_no_live_file_imports_a_frozen_module():
    files = [
        p
        for tree in ("python/rang", "examples", "tools", "tests")
        for p in (ROOT / tree).rglob("*.py")
        if p != PKG / "flagging.py"  # the C1 re-export itself
    ]
    offenders = {}
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        lines = [n for n in _frozen_imports(p) if not _c1_allowed(rel, p, n)]
        if lines:
            offenders[rel] = lines
    assert offenders == {}
    # Import statements inside script strings (subprocess and recorder tests).
    pattern = re.compile(
        r"^\s*[\"']?(from|import)\s+rang\.(flagging\w*|imaging_sensitivity)\b"
        r"|^\s*[\"']?from\s+rang\s+import\s+(flagging\w*|imaging_sensitivity)\b",
        re.MULTILINE,
    )
    strings = {
        p.relative_to(ROOT).as_posix()
        for p in files
        if p != Path(__file__) and pattern.search(p.read_text(encoding="utf-8"))
    }
    assert strings == set()
    # Code that hashes or opens a frozen module by file name (campaign
    # CODE_FILES, core_imaging.MODULES) must name the extract instead.
    by_name = re.compile(
        r"[\"'](python/rang/)?(flagging\w*|imaging_sensitivity)(\.py)?[\"']"
    )
    named = {
        p.relative_to(ROOT).as_posix()
        for p in files
        if p.is_relative_to(PKG) and by_name.search(p.read_text(encoding="utf-8"))
    }
    assert named == set()


BLOCKED = r"""
import importlib, pkgutil, sys
class Block:
    def find_spec(self, name, path=None, target=None):
        last = name.rsplit(".", 1)[-1]
        if name == "rang.flagging":  # the C1 re-export, checked below
            return None
        if name.startswith("rang.") and (last.startswith("flagging") or last == "imaging_sensitivity"):
            raise ImportError(f"frozen module imported: {name}")
sys.meta_path.insert(0, Block())
import rang, rang.notebook
names = [i.name for i in pkgutil.iter_modules(rang.__path__, "rang.") if i.name.startswith("rang.core")]
names += [i.name for i in pkgutil.iter_modules(rang.notebook.__path__, "rang.notebook.")]
skipped = []
for name in names:
    try:
        importlib.import_module(name)
    except ModuleNotFoundError as exc:  # an optional third-party extra
        if exc.name and exc.name.split(".")[0] != "rang":
            skipped.append(name)
        else:
            raise
frozen = [m for m in sys.modules if m.startswith("rang.flagging") or m == "rang.imaging_sensitivity"]
assert set(frozen) <= {"rang.flagging"}, frozen
if frozen:  # only C1's file may import the re-export, and it is core_policy's
    from pathlib import Path
    import rang.core_policy as policy, rang.flagging as shim
    assert Path(shim.__file__).name == "flagging.py"
    assert Path(shim.__file__).parent == Path(policy.__file__).parent
    for n in ("fixed_support_tv", "gain_tv", "polar_gauge"):
        assert getattr(shim, n) is getattr(policy, n), n
print("ok", len(names), len(skipped))
"""


def test_core_and_notebook_import_without_frozen_modules():
    run = subprocess.run(
        [sys.executable, "-c", BLOCKED],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert run.returncode == 0, run.stderr[-2000:]
    assert run.stdout.startswith("ok")
