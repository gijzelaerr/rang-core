"""F3 run wrapper (scratch): D:\\rang\\outputs\\<name> with .code/, .log, .time.

Usage: python f3-run.py NAME [--lock] -- COMMAND ...
Sets RUN_DIR. Logs start, end, rc to the status file.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(r"D:\rang\outputs")
# The main checkout's lock queues first come, first served (main bd15126);
# older copies in branches poll and can jump the queue.
LOCK = Path("C:/Users/gijsm/Github/rang/tools/heavy_lock.py")
STATUS = Path(r"C:\Users\gijsm\Github\rang\outputs\status\f4-flagger.md")


def status(line):
    lines = STATUS.read_text(encoding="utf-8").splitlines() if STATUS.exists() else []
    lines.append(f"- {time.strftime('%H:%M')} {line}")
    head, rest = lines[:1], lines[1:]
    STATUS.write_text("\n".join(head + rest[-13:]) + "\n", encoding="utf-8")


def main():
    argv = sys.argv[1:]
    k = argv.index("--")
    name, opts, cmd = argv[0], argv[1:k], argv[k + 1 :]
    run = OUT / name
    run.mkdir(parents=True, exist_ok=True)
    code = OUT / f"{name}.code"
    if code.exists():
        shutil.rmtree(code)
    code.mkdir()
    head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (code / "HEAD").write_text(head + "\n")
    diff = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    (code / "diff.patch").write_text(diff, encoding="utf-8")
    (code / "command").write_text(" ".join(cmd) + "\n", encoding="utf-8")
    for pat in (
        "python/rang/f3*.py",
        "python/rang/f4*.py",
        "examples/f3_*.py",
        "examples/f4_*.py",
        "core/src/f3flag.rs",
        "core/src/f4flag.rs",
        "tools/oracles/aoflagger/f3_*.py",
    ):
        for p in ROOT.glob(pat):
            (code / p.parent.name).mkdir(exist_ok=True)
            shutil.copy2(p, code / p.parent.name / p.name)
    env = dict(os.environ, RUN_DIR=str(run))
    if "--lock" in opts:
        cmd = [sys.executable, str(LOCK), "run", "--", *cmd]
    start = time.time()
    status(f"start {name}")
    with open(OUT / f"{name}.log", "ab") as log:
        rc = subprocess.call(
            cmd, stdout=log, stderr=subprocess.STDOUT, env=env, cwd=ROOT
        )
    wall = time.time() - start
    (OUT / f"{name}.time").write_text(
        json.dumps(
            {
                "start": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(start)),
                "wall_s": round(wall, 1),
                "rc": rc,
                "command": cmd,
            }
        )
        + "\n"
    )
    status(f"end {name} rc {rc} {wall / 60:.1f} min")
    sys.exit(rc)


if __name__ == "__main__":
    main()
