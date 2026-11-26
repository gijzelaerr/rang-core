"""solver-flags-2 (#58): an arm's run configuration from a frozen one
(research/solver-flags-2.md section 4).

    python sf2_cfg.py IN.yaml OUT.yaml P0|PB|PG|PBG [MEMORY_LIMIT_GB]

Every arm: `run.stages: [flag, calibrate, apply]`; the flag stage on fcal and
gcal only, with the preset-only strategy (copied next to OUT.yaml) and
`flag.known_rfi: meerkat_l`; PB, PG, PBG add `calibrate.solver_flags`
(`quartical`, rounds 2, guard 0.8: the first note's M1) on B, Gsec or both.
Everything else unchanged.
"""

import sys

import yaml

STRATEGY = "sf2_preset_only.yaml"
TERMS = {"P0": None, "PB": ["B"], "PG": ["Gsec"], "PBG": ["B", "Gsec"]}


def main(src, dst, arm, memory=None):
    if arm not in TERMS:
        raise SystemExit(f"unknown arm {arm}")
    with open(src, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if memory is not None:
        cfg.setdefault("data", {})["memory_limit_gb"] = float(memory)
    cfg.setdefault("run", {})["stages"] = ["flag", "calibrate", "apply"]
    flag = cfg.setdefault("flag", {})
    flag["strategy"] = STRATEGY
    flag["known_rfi"] = "meerkat_l"
    flag["fields"] = ["fcal", "gcal"]
    if TERMS[arm]:
        cfg.setdefault("calibrate", {})["solver_flags"] = {
            "mode": "quartical",
            "terms": TERMS[arm],
            "rounds": 2,
            "guard": 0.8,
        }
    with open(dst, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, sort_keys=False)


if __name__ == "__main__":
    main(*sys.argv[1:5])
