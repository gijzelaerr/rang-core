"""9.18's scorer: C10, then gate 3c's dirty measure at eps 1e-6 with
WSClean -no-small-inversion on the three fields.

    python a5_score.py c10 OUT_JSON
    python a5_score.py score OUT_JSON
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from a4_score import FIELDS, R, TOL, linf  # noqa: E402

P = Path("D:/rang/outputs/e2b-close-20261115/a5")


def _drop(d):
    d.pop("per_image")
    return d


def c10(out_json):
    tag = "J1833m2103"
    new = P / "default" / f"{tag}-eps0.0001"
    old = R / "wsclean3c-unit"
    res = {"tolerance": TOL, "wsclean_ext4_copy_vs_archived": _drop(linf(
        lambda c, p: new / f"{tag}-dirty-{c}-{p}-dirty.fits",
        lambda c, p: old / f"{tag}-dirty-{c}-{p}-dirty.fits",
        lambda c: old / f"{tag}-dirty-{c}-I-dirty.fits"))}  # fmt: skip
    res["met"] = res["wsclean_ext4_copy_vs_archived"]["max"] <= TOL
    Path(out_json).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


def score(out_json):
    res = {"tolerance": TOL, "eps": "1e-06", "fields": {}}
    for name, tag in FIELDS:
        r = P / "rang" / f"{tag}-eps1e-06"
        n = P / "nosi" / f"{tag}-eps1e-06"
        f = _drop(linf(
            lambda c, p, r=r: r / f"image-{c}-{p}-dirty.fits",
            lambda c, p, n=n, tag=tag: n / f"{tag}-dirty-{c}-{p}-dirty.fits",
            lambda c, n=n, tag=tag: n / f"{tag}-dirty-{c}-I-dirty.fits"))  # fmt: skip
        f["met"] = f["max"] <= TOL
        res["fields"][name] = f
    res["met_all"] = all(v["met"] for v in res["fields"].values())
    Path(out_json).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"c10": c10, "score": score}[sys.argv[1]](sys.argv[2])
