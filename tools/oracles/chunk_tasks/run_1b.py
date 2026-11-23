# SPDX-License-Identifier: MIT
"""The identity runs of research/chunk-task-api-1b.md (sections 2 and 3).

    python run_1b.py arm RUN CASE ARM    # one arm: fresh MS copy, stages, hashes
    python run_1b.py verdict RUN         # every arm against U, criteria 1-6

Cases C, P, M, W and arms U, P1, P4, P2T as section 2 freezes them. Stage 1's
harness (`run.py`) does the work: this module sets its cases, sources and
configurations, and adds criterion 6 (tasks went through the pool). U runs
main e071bdab's Python (`RANG_CTA_ORACLE`, a detached worktree whose
`python/rang` holds this checkout's `_core` build).
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import run as base  # stage 1's harness

SOURCES = {
    "C": base.SOURCES["C"],
    "P": base.SOURCES["P"],
    "M": base.SOURCES["C"],
    "W": base.SOURCES["W"],
}
STAGES = {c: ("calibrate", "apply") for c in SOURCES}
ARMS_OF = {c: ("U", "P1", "P4", "P2T") for c in SOURCES}
ARMS_OF["W"] = ("U", "P1", "P4")

# Case M: case C with a G term of two fields before F (`chain-field`), and
# calwt in apply.
TWO_FIELDS = """\
      - {type: G, name: G2, field: [J1939-6342, SIM-GCAL], solint: int,
         preapply: [K, B], interp: [linear, linear]}
      - {type: F, name: F, solint: inf, preapply: [K, B], interp: [linear, linear]}
"""
F_TERM = (
    "      - {type: F, name: F, solint: inf, preapply: [K, B], "
    "interp: [linear, linear]}\n"
)
# Case W: W3b's whole-array chain (tools/oracles/w3b/compare.py WHOLE).
WHOLE = """\
version: 1
fields: {fcal: [J1939-6342]}
%(data)scalibrate:
  model: {source: setjy}
  refant: m000
  primary:
    terms:
      - {type: K, name: K, solint: int}
      - {type: G, name: G, solint: int, preapply: [K], interp: [linear]}
      - {type: B, name: B, solint: inf, combine: scan, preapply: [K, G],
         interp: [linear, linear]}
"""


def config_text(case, arm, ms):
    lines = base.ARMS[arm]
    if case in ("C", "P"):
        return base.config_text(case, arm, ms)
    if case == "M":
        text = base.config_text("C", arm, ms)
        assert F_TERM in text, "case C's F term moved"
        text = text.replace(F_TERM, TWO_FIELDS)
        return text.replace("apply:\n  targets:", "apply:\n  calwt: true\n  targets:")
    block = ("data:\n" + "".join(f"  {d}\n" for d in lines)) if lines else ""
    return WHOLE % {"data": block}


def install():
    base.SOURCES = SOURCES
    base.STAGES = STAGES
    base.ARMS_OF = ARMS_OF
    base.config_text = config_text


def tasks_check(run):
    """Criterion 6: in P4 and P2T, chain-chunk tasks on C, P and W,
    chain-field tasks on M, apply-casa tasks on every case."""
    run = Path(run)
    out, ok = {}, True
    for case in SOURCES:
        for arm in ("P4", "P2T"):
            d = run / f"{case}-{arm}"
            if arm not in ARMS_OF[case] or not (d / "done.json").is_file():
                continue
            got = {}
            for stage in ("calibrate", "apply"):
                path = d / "work.ms.rang-run" / stage / "summary.json"
                summary = json.loads(path.read_text(encoding="utf-8"))
                got[stage] = summary.get("chunking", {}).get("tasks", {})
            want = {"apply": "apply-casa"}
            want["calibrate"] = "chain-field" if case == "M" else "chain-chunk"
            good = all(got[s].get(k, 0) > 0 for s, k in want.items())
            ok &= good
            out[f"{case}-{arm}"] = {"tasks": got, "pass": good}
    return out, ok


def main(argv):
    install()
    if argv[0] == "arm":
        base.arm(*argv[1:4])
    elif argv[0] == "verdict":
        base.verdict(argv[1])
        report = json.loads((Path(argv[1]) / "verdict.json").read_text())
        tasks, ok = tasks_check(argv[1])
        report["criterion 6"] = tasks
        report["pass"] = bool(report["pass"] and ok)
        text = json.dumps(report, indent=1)
        (Path(argv[1]) / "verdict.json").write_text(text + "\n", encoding="utf-8")
        print(text)
        print("verdict:", "PASS" if report["pass"] else "FAIL")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
