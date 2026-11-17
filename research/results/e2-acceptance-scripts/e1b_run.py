"""E1b's runs (research/e2-acceptance.md, part 1): E1's chain rerun after item 27.

    python e1b_run.py prepare RUN SRC_MS {auto|m000} [--twin]
    python e1b_run.py control RUN

`prepare` copies SRC_MS to RUN/ms/, writes RUN/config.yaml from E1's frozen
configuration (research/results/e1-chain-scripts/e1_config.yaml) with only the
item 27 changes, copies the strategy file and snapshots the code to RUN/.code/:

- `auto`: both `refant: m000` lines removed, so calibrate takes the new default
  `refant: auto` (CARACal's choice) and selfcal resolves auto to its first
  antenna;
- `m000`: E1's refants kept (the arm that separates the other changes);
- both: `image.niter` is not set in E1's configuration, so the new default
  1,000,000 applies (it was 100,000).

`control` is E1's control (CORRECTED_TRUTH and its image with the chain's
gemclean arguments), unchanged.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
E1 = HERE.parent / "e1-chain-scripts"
ROOT = HERE.parents[2]
sys.path.insert(0, str(E1))
sys.path.insert(0, str(ROOT / "python"))

import e1_run


def config_text(variant, twin):
    text = (E1 / "e1_config.yaml").read_text(encoding="utf-8")
    if variant == "auto":
        assert text.count("  refant: m000\n") == 2
        text = text.replace("  refant: m000\n", "")
    elif variant != "m000":
        raise SystemExit(f"unknown variant {variant}")
    assert "niter" not in text
    if twin:
        text = text.replace("      - {type: A, name: Asec}\n", "")
        text = text.replace(
            "  stages: [flag, calibrate, apply, selfcal]",
            "  stages: [calibrate, apply]",
        )
        assert "Asec" not in text and "[calibrate, apply]" in text
    head = (
        f"# E1b ({variant}{', twin' if twin else ''}), research/e2-acceptance.md: "
        "E1's frozen configuration with item 27's changes only.\n"
    )
    return head + text


def snapshot(run):
    code = Path(run) / ".code"
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
    for d in (HERE, E1):
        shutil.copytree(d, code / d.name, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(
        ROOT / "python" / "rang",
        code / "rang",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyd", "*.so", "*.pdb"),
    )


def prepare(run, src, variant, twin=False):
    run = Path(run)
    (run / "ms").mkdir(parents=True, exist_ok=True)
    dst = run / "ms" / Path(src).name
    if dst.exists():
        raise SystemExit(f"{dst} exists")
    shutil.copytree(src, dst)
    shutil.copy2(e1_run.STRATEGY, run / e1_run.STRATEGY.name)
    (run / "config.yaml").write_text(config_text(variant, twin), encoding="utf-8")
    snapshot(run)
    print(dst)


def control(run, version):
    """E1's control, run with G8's gemclean: since G8 `find_gemclean('auto')`
    returns the command `python -m rang.gemclean`, which E1's script passes as
    one token (`str(binary)`); here that token is expanded to the command's
    argv. Nothing else of E1's control changes. A partial control directory
    from a failed attempt is removed first."""
    out = Path(run) / "control"
    if out.exists():
        shutil.rmtree(out)
    real = e1_run.core_pipeline.run_gemclean

    def run_gemclean(binary, argv, log):
        if argv and argv[0] == str(binary) and hasattr(binary, "argv"):
            argv = [*binary.argv, *argv[1:]]
        return real(binary, argv, log)

    e1_run.core_pipeline.run_gemclean = run_gemclean
    try:
        e1_run.control(run, version)
    finally:
        e1_run.core_pipeline.run_gemclean = real


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("prepare")
    s.add_argument("run")
    s.add_argument("src")
    s.add_argument("variant", choices=("auto", "m000"))
    s.add_argument("--twin", action="store_true")
    s = sub.add_parser("control")
    s.add_argument("run")
    s.add_argument("--version", default="full")
    a = p.parse_args(argv)
    if a.cmd == "prepare":
        prepare(a.run, a.src, a.variant, a.twin)
    else:
        control(a.run, a.version)


if __name__ == "__main__":
    main()
