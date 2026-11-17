"""df5o_l2.py: relative L2 on DF5-O's field (research/rml-gap.md, section 4: b = 11.58 px; amendment
A2's CPU basis), written to $O/df5o/measures/l2.json.

For each arm: ||B * M - B * T|| / ||B * T|| over the image, with B the circular Gaussian of FWHM b,
M the band mean of the arm's 16-channel model and T the band mean of DF5-O's truth cube (on the
grid, so B * T is an FFT convolution). For U (pfb sara) also every major cycle's MFS model,
oriented by DF5-O's P2 orientation, with its cumulative wall and CPU seconds (CPU as in A2: init +
grid + sara's CPU x the fraction of sara's wall elapsed), and the last cycle within 5 x G's wall
and 5 x G's CPU.
"""

import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "examples"))
import compare_df5o as cd
import rml_gap_score as rs

D = Path("D:/rang/outputs/rml-gap-20261113/df5o")
B_PX = 11.58


def rel_l2(model, bt):
    return float(np.linalg.norm(rs.model_on_beam(model, B_PX) - bt) / np.linalg.norm(bt))


def cpu(time_v):
    return (time_v.get("user_s") or 0.0) + (time_v.get("system_s") or 0.0)


def main():
    _, _, arrays = cd.load_field(D / "field")
    bt = rs.model_on_beam(arrays["truth_cube"].mean(0), B_PX)
    orientation = json.loads((D / "ref" / "p2.json").read_text())["pfb"]["orientation"]
    out = {"b_px": B_PX, "arms": {}}
    for arm in ("ws-G", "ws-Gd", "ws-W"):
        d = D / f"{arm}-r1"
        run = json.loads((d / "run.json").read_text(encoding="utf-8"))
        models, _, _ = cd.wsclean_outputs(d, arm)
        out["arms"][arm] = {"relative_l2": rel_l2(models.mean(0), bt),
                            "wall_s": run["docker_wall_s"], "cpu_s": cpu(run["time_v"])}  # fmt: skip
    g = out["arms"]["ws-G"]
    d = D / "pfb-sara-U-a-r1"
    run = json.loads((d / "run.json").read_text(encoding="utf-8"))
    models, _, _ = cd.pfb_outputs(d, orientation)
    steps = {s["step"]: s for s in run["steps"]}
    sara = steps["sara"]
    off = sara["start"] - run["start"]
    pre = cpu(steps["init"]["time_v"]) + cpu(steps["grid"]["time_v"])
    its = []
    for f, t in run["file_seconds_since_start"].items():
        m = re.fullmatch(r"pfb_I_main_model_(\d+)\.fits", f)
        if not m:
            continue
        img = cd.orient(cd.plane(cd.read_fits(d / f)[0]), orientation)
        frac = min(max((t - off) / sara["docker_wall_s"], 0.0), 1.0)
        its.append({"cycle": int(m.group(1)), "seconds": t,
                    "cpu_s": pre + cpu(sara["time_v"]) * frac, "relative_l2": rel_l2(img, bt)})  # fmt: skip
    its.sort(key=lambda r: r["cycle"])
    u = {"relative_l2": rel_l2(models.mean(0), bt), "wall_s": run["docker_wall_s"],
         "cpu_s": pre + cpu(sara["time_v"]), "iterates": its}  # fmt: skip
    for key, lim, basis in (("within_5g", 5 * g["wall_s"], "seconds"),
                            ("within_5g_cpu", 5 * g["cpu_s"], "cpu_s")):  # fmt: skip
        ok = [r for r in its if r[basis] <= lim]
        u[key] = ok[-1] if ok else None
    u["r"] = u["relative_l2"] / g["relative_l2"]
    for key in ("within_5g", "within_5g_cpu"):
        u[f"r5{key[9:]}"] = u[key]["relative_l2"] / g["relative_l2"] if u[key] else None
    out["arms"]["pfb-sara-U-a"] = u
    (D / "measures" / "l2.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    brief = {a: {k: v for k, v in r.items() if k != "iterates"} for a, r in out["arms"].items()}
    print(json.dumps(brief, indent=1, default=str))


if __name__ == "__main__":
    main()
