"""flag-residual (#51): a run configuration from a frozen one.

    python fr_cfg.py IN.yaml OUT.yaml off|calibrators [MEMORY_LIMIT_GB]

`run.stages: [calibrate, apply]` (the flag stage is not rerun: the inputs
carry the flag stage's flags, or only online flags for A1), and
`flag.residual.mode` as given; everything else unchanged.
"""

import sys

import yaml


def main(src, dst, mode, memory=None):
    cfg = yaml.safe_load(open(src, encoding="utf-8"))
    if memory is not None:
        cfg.setdefault("data", {})["memory_limit_gb"] = float(memory)
    cfg.setdefault("run", {})["stages"] = ["calibrate", "apply"]
    cfg.setdefault("flag", {})["residual"] = {"mode": mode}
    with open(dst, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, sort_keys=False)


if __name__ == "__main__":
    main(*sys.argv[1:5])
