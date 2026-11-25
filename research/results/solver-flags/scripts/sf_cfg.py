"""solver-flags (#58, #59): an arm's run configuration from a frozen one
(research/solver-flags.md section 5).

    python sf_cfg.py IN.yaml OUT.yaml R|M0|M1|M2 [MEMORY_LIMIT_GB]

Every arm: `run.stages: [flag, calibrate, apply]`. R keeps the frozen flag
strategy; M0-M2 use the mild strategy (copied next to OUT.yaml) and the
MeerKAT L-band known-RFI preset; M1 adds `calibrate.solver_flags`, M2
`flag.residual` (#51's settings). Everything else unchanged.
"""

import sys

import yaml

MILD = "mk_rfi_flagging_mild.yaml"


def main(src, dst, arm, memory=None):
    cfg = yaml.safe_load(open(src, encoding="utf-8"))
    if memory is not None:
        cfg.setdefault("data", {})["memory_limit_gb"] = float(memory)
    cfg.setdefault("run", {})["stages"] = ["flag", "calibrate", "apply"]
    flag = cfg.setdefault("flag", {})
    if arm != "R":
        flag["strategy"] = MILD
        flag["known_rfi"] = "meerkat_l"
    if arm == "M1":
        cfg.setdefault("calibrate", {})["solver_flags"] = {
            "mode": "quartical",
            "terms": ["G", "B"],
            "rounds": 2,
            "guard": 0.8,
        }
    if arm == "M2":
        flag["residual"] = {"mode": "calibrators", "method": "rang"}
    if arm not in ("R", "M0", "M1", "M2"):
        raise SystemExit(f"unknown arm {arm}")
    with open(dst, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, sort_keys=False)


if __name__ == "__main__":
    main(*sys.argv[1:5])
