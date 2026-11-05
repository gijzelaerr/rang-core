"""Task W4-6 (research/w4-6-portability.md): text files in `python/rang` name
their encoding, whatever the locale of the host.

Ruff's PLW1514 recognises `Path(...)` literals, not `path.read_text()` on a
variable, hence this AST check.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "python" / "rang"

# `.open` methods of these names are not text files.
NOT_FILES = {"fits", "katdal", "os"}  # os.open returns a descriptor, no text

# Verbatim P11 extracts, file -> calls left as they are. tests/test_p11_extract.py
# compares these segments, text for text, with history/python, and history/ is
# frozen. Each one handles JSON from `json.dump(s)`, which is ASCII, so the code
# page does not change a character; on Windows the two writers end lines with CRLF.
VERBATIM = {
    "python/rang/core_response.py": 1,
    "python/rang/core_state.py": 1,
    "python/rang/core_trend_run.py": 1,
}


def _is_binary(mode):
    if isinstance(mode, ast.IfExp):
        return _is_binary(mode.body) and _is_binary(mode.orelse)
    return isinstance(mode, ast.Constant) and "b" in str(mode.value)


def _mode(call):
    """The mode argument of `open(...)` or `path.open(...)`, or None."""
    for keyword in call.keywords:
        if keyword.arg == "mode":
            return keyword.value
    index = 1 if isinstance(call.func, ast.Name) else 0
    return call.args[index] if len(call.args) > index else None


def _writes(mode):
    if mode is None:
        return False
    return not isinstance(mode, ast.Constant) or bool(
        set(str(mode.value)) & set("wax+")
    )


def offenders(source):
    """(line, problem) for each text read or write that leaves its encoding, or
    its line ending when writing, to the host."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        keywords = {k.arg for k in node.keywords}
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "read_text":
            writes = False
        elif isinstance(func, ast.Attribute) and func.attr == "write_text":
            writes = True
        elif (isinstance(func, ast.Name) and func.id == "open") or (
            isinstance(func, ast.Attribute)
            and func.attr == "open"
            and not (isinstance(func.value, ast.Name) and func.value.id in NOT_FILES)
        ):
            mode = _mode(node)
            if _is_binary(mode):
                continue
            writes = _writes(mode)
        else:
            continue
        if "encoding" not in keywords:
            found.append((node.lineno, "no encoding"))
        if writes and "newline" not in keywords:
            found.append((node.lineno, "no newline"))
    return found


def _tree():
    out = {}
    for path in sorted(PKG.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        found = offenders(path.read_bytes())
        if found:
            out[rel] = found
    return out


def test_every_text_read_and_write_names_its_encoding():
    found = _tree()
    verbatim = {rel: found.pop(rel, []) for rel in VERBATIM}
    assert found == {}
    # Only the verbatim sites remain, and no more of them.
    for rel, count in VERBATIM.items():
        lines = {line for line, _ in verbatim[rel]}
        assert len(lines) == count, (rel, verbatim[rel])
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "Verbatim extract of the frozen" in text


def test_the_check_sees_what_ruff_misses():
    bad = {
        "path.read_text()": 1,
        "Path('x').read_text()": 1,
        "path.write_text('x')": 2,
        "path.write_text('x', encoding='utf-8')": 1,
        "open('x')": 1,
        "open('x', 'w')": 2,
        "path.open()": 1,
        "path.open('a')": 2,
        "path.open('x', encoding='utf-8')": 1,
        "open('x', mode='r')": 1,
    }
    for source, count in bad.items():
        assert len(offenders(source)) == count, source
    good = (
        "path.read_text(encoding='utf-8')",
        "path.write_text('x', encoding='utf-8', newline='\\n')",
        "path.read_bytes()",
        "open('x', 'rb')",
        "path.open('wb' if replace else 'xb')",
        "path.open('w', encoding='utf-8', newline='\\n')",
        "path.open(encoding='utf-8')",
        "fits.open('x')",
        "katdal.open('x')",
    )
    for source in good:
        assert offenders(source) == [], source


def test_sky_model_reads_utf8_in_a_non_utf8_locale(tmp_path):
    """The behaviour: a non-ASCII source name survives a load and a save with
    UTF-8 mode off (ASCII under LC_ALL=C on Linux, the code page on Windows)."""
    path = tmp_path / "model.txt"
    name = "J0408-6545\N{LATIN SMALL LETTER E WITH ACUTE}"
    path.write_text(
        "Format = Name, Type, Ra, Dec, I, SpectralIndex, LogarithmicSI, "
        "ReferenceFrequency='1000000000.0'\n"
        f"{name},POINT,04:08:20.0,-65.45.09.0,1.0,[],true,1000000000.0\n",
        encoding="utf-8",
        newline="\n",
    )
    script = (
        "import sys\n"
        "from rang.formats import sky\n"
        "sources = sky.load_wsclean(sys.argv[1])\n"
        "assert sys.flags.utf8_mode == 0\n"
        "print(ascii(sources[0].name))\n"
    )
    env = dict(os.environ, PYTHONUTF8="0", PYTHONCOERCECLOCALE="0", LC_ALL="C")
    env.pop("PYTHONIOENCODING", None)
    run = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert run.returncode == 0, run.stderr[-2000:]
    assert run.stdout.strip() == ascii(name)
