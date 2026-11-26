# SPDX-License-Identifier: MIT
"""Fast checks before a push, run by tools/githooks/pre-push.

They cover the failures that turned most branch CI runs red in November 2026,
in about a second with the standard library only:

- every note `research/*.md` is linked from `research/README.md`
  (tests/test_w4_8_docs.py::test_every_note_is_in_the_research_index);
- every tracked source file under python/rang, core/src, src and tools carries
  an SPDX line in its first three lines (tests/test_spdx_headers.py);
- every tracked source file under python/rang, core/src, core/py/src, src
  and tools has a row in the provenance register
  research/results/mit-relicense-audit/files.csv, and every row a file
  (tests/test_licence_register.py);
- `ruff check` and `ruff format --check` on python, examples and tests, as CI,
  when ruff is installed.

Exit 1 with a list of what to fix. Skip it once with `git push --no-verify`
only when the push is meant to show a red run."""

import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPDX_DIRS = ("python/rang", "core/src", "src", "tools")
SPDX_SUFFIXES = {".py", ".sh", ".rs", ".cc"}
RUFF_PATHS = ("python", "examples", "tests")  # as .github/workflows/tests.yml
SPDX = re.compile(r"SPDX-License-Identifier: \S")
REGISTER = ROOT / "research" / "results" / "mit-relicense-audit" / "files.csv"
REGISTER_DIRS = ("python/rang", "core/src", "core/py/src", "src", "tools")
REGISTER_SUFFIXES = {".py", ".sh", ".rs", ".cc", ".wgsl"}


def unindexed_notes() -> list[str]:
    research = ROOT / "research"
    index = (research / "README.md").read_text(encoding="utf-8")
    linked = {t.split("#")[0] for t in re.findall(r"\]\(([^)\s]+)", index)}
    notes = {p.name for p in research.glob("*.md")} - {"README.md"}
    return sorted(notes - linked)


def missing_spdx() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", *SPDX_DIRS],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    bad = []
    for name in out.split():
        p = ROOT / name
        if p.suffix not in SPDX_SUFFIXES or not p.exists():
            continue
        with open(p, "rb") as fh:
            head = b"\n".join(fh.read(4096).split(b"\n")[:3])
        if not SPDX.search(head.decode("utf-8", "replace")):
            bad.append(name)
    return bad


def register_gaps(tracked=None) -> tuple[list[str], list[str]]:
    """(files in scope without a row in files.csv, rows without a file)."""
    if tracked is None:
        tracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", *REGISTER_DIRS],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    files = {p for p in tracked if Path(p).suffix in REGISTER_SUFFIXES}
    with open(REGISTER, newline="", encoding="utf-8") as fh:
        rows = {r["path"] for r in csv.DictReader(fh)}
    gone = sorted(p for p in rows if not (ROOT / p).is_file())
    return sorted(files - rows), gone


def ruff() -> list[str]:
    exe = shutil.which("ruff")
    venv = ROOT / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
    for cand in (venv / "ruff.exe", venv / "ruff"):
        if cand.exists():
            exe = str(cand)
    if exe is None:
        return []
    problems = []
    for args in (["check", "-q"], ["format", "--check", "-q"]):
        args = [*args, *RUFF_PATHS]
        r = subprocess.run(
            [exe, *args],
            check=False,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode != 0:
            problems.append(f"ruff {args[0]}:\n{(r.stdout + r.stderr).strip()}")
    return problems


def main() -> int:
    failures = []
    notes = unindexed_notes()
    if notes:
        failures.append(
            "notes missing from research/README.md (add an index line in the "
            "same commit as the note): " + ", ".join(notes)
        )
    spdx = missing_spdx()
    if spdx:
        failures.append(
            "files without an SPDX line in their first three lines "
            "(new own code: `SPDX-License-Identifier: MIT`): " + ", ".join(spdx)
        )
    unregistered, gone = register_gaps()
    if unregistered:
        failures.append(
            "files without a row in research/results/mit-relicense-audit/files.csv "
            "(own new code: `<path>,<lines>,a,-,-,-,0,-,-`; derived code: its "
            "upstream, version, licence and pieces, CONTRIBUTING.md): "
            + ", ".join(unregistered)
        )
    if gone:
        failures.append(
            "rows in research/results/mit-relicense-audit/files.csv for files "
            "that no longer exist (remove or rename the row): " + ", ".join(gone)
        )
    failures += ruff()
    if failures:
        print("pre-push check failed; CI would go red:", file=sys.stderr)
        for f in failures:
            print(f"- {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
