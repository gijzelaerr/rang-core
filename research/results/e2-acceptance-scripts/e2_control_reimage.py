"""E2 (owner decision, finish-plan 7 item 27): re-image E1's control column
(CORRECTED_TRUTH of run e1-20261109-03) with the current GeMClean, which fits
the restoring beam as WSClean 3.7 does (G7), and with exactly E1's imaging
arguments (`core_pipeline.gemclean_arguments` on E1's resolved config; the
argv is checked against E1's recorded one, binary and -name aside).

    python e2_control_reimage.py E1_RUN OUT_DIR

Writes OUT_DIR/.code (commit, status, diff, these scripts), OUT_DIR/image,
OUT_DIR/reimage.json. Run under tools/heavy_lock.py.
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(HERE.parent / "e1-chain-scripts"))

import e1_run
from rang import core_pipeline


def snapshot(out):
    code = out / ".code"
    if code.exists():
        shutil.rmtree(code)
    code.mkdir(parents=True)

    def git(*a):
        return subprocess.run(
            ["git", "-C", str(ROOT), *a], capture_output=True, text=True, check=True
        ).stdout

    (code / "commit.txt").write_text(git("rev-parse", "HEAD"), encoding="utf-8")
    (code / "status.txt").write_text(git("status", "--porcelain"), encoding="utf-8")
    (code / "diff.patch").write_text(git("diff", "HEAD"), encoding="utf-8")
    shutil.copytree(HERE, code / "e2-acceptance-scripts",
                    ignore=shutil.ignore_patterns("__pycache__"))  # fmt: skip


def main():
    run, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    snapshot(out)
    ms = e1_run.ms_of(run)
    config = json.loads(
        (ms.parent / f"{ms.name}.rang-run" / "config.resolved.json").read_text(
            encoding="utf-8"
        )
    )
    img = config["image"]
    fid = e1_run.field_id(ms, e1_run.TARGET)
    where = out / "image"
    if where.exists():
        shutil.rmtree(where)
    where.mkdir()
    binary = core_pipeline.find_gemclean("auto")
    args = core_pipeline.gemclean_arguments(
        img, e1_run.CONTROL_COLUMN, fid, where / img["name"], ms,
        config["data"]["scans"] or (), config["data"]["weights"] == "uniform",
    )  # fmt: skip
    old = json.loads((run / "control" / "control.json").read_text(encoding="utf-8"))
    old_args = old["argv"][1:]
    i = old_args.index("-name")
    j = args.index("-name")
    same = old_args[:i] + old_args[i + 2 :] == args[:j] + args[j + 2 :]
    if not same:
        raise SystemExit(f"argv differs from E1's: {args} vs {old_args}")
    version = subprocess.run([*binary.argv, "-version"], capture_output=True,
                             text=True, check=False).stdout.strip()  # fmt: skip
    argv = [*binary.argv, *args]
    t0 = time.perf_counter()
    seconds = core_pipeline.run_gemclean(binary, argv, where / "gemclean.log")
    record = {"e1_run": str(run), "argv": argv, "argv_equals_e1": same,
              "gemclean_version": version, "extension": str(binary.path),
              "image_seconds": seconds,
              "wall_seconds": time.perf_counter() - t0}  # fmt: skip
    e1_run.write_json(out / "reimage.json", record)
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
