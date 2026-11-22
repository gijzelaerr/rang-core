"""F5 section 2f: the cross-host check (quality on nash, cost on glacier).

Usage:
  python examples/f5_crosshost.py save OUT.npz --set luno:MAIN_7 [--data-root R] [--ao-sif S] [--with-a]
  python examples/f5_crosshost.py compare A.npz B.npz OUT.json [--cached-t T.npy] [--cached-a A.npy]

save: W3, T and U5's logits (level 0, d 2, init seed 0) on a validation set,
and A when asked. compare: T flags differ on at most 1e-6 of cells; logits
within the parity bars (p99.9 1e-4, max 1e-3, flag disagreement 1e-5 of
eligible cells at 0); against glacier's cached T (and A) as well.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from rang import f3flag as f3
from rang import f5flag as f5
from rang import f5net


def save(a):
    if a.data_root:
        f5.use_data_root(a.data_root)
    if a.ao_sif:
        f5.AO_SIF = a.ao_sif
    scan = f5.load(a.set)
    w3 = f3.w3_flags(scan)
    t = f3.t_flags(scan)
    w = f5net.flat_from_arrays(f5net.init_arrays(0, 33, True))
    logit = f5.rust_logits(scan, w3, w, 0, 2)
    out = {"w3": w3, "t": t, "logit": logit}
    if a.with_a:
        out["a"], _ = f5.a_flags(scan, w3, Path(a.out).parent / "aoflag-crosshost")
    np.savez_compressed(a.out, **out)
    print(json.dumps({k: list(v.shape) for k, v in out.items()}))


def compare(a):
    x, y = np.load(a.a), np.load(a.b)
    el = ~x["w3"]
    d = np.abs(x["logit"] - y["logit"])[el]
    rec = {
        "w3_diff": int((x["w3"] != y["w3"]).sum()),
        "T_diff_frac": float((x["t"] != y["t"]).mean()),
        "logit_p999": float(np.quantile(d, 0.999)),
        "logit_max": float(d.max()),
        "flag_disagreement": float(((x["logit"] > 0) != (y["logit"] > 0))[el].mean()),
    }
    if a.cached_t:
        c = np.load(a.cached_t)
        rec["T_vs_cached_frac"] = {
            k: float((z["t"] != c).mean()) for k, z in (("A", x), ("B", y))
        }
    if a.cached_a:
        c = np.load(a.cached_a)
        rec["A_vs_cached_frac"] = {
            k: float((z["a"] != c).mean())
            for k, z in (("A", x), ("B", y))
            if "a" in z.files
        }
    rec["pass"] = (
        rec["w3_diff"] == 0
        and rec["T_diff_frac"] <= 1e-6
        and rec["logit_p999"] <= 1e-4
        and rec["logit_max"] <= 1e-3
        and rec["flag_disagreement"] <= 1e-5
        and all(v <= 1e-6 for v in rec.get("T_vs_cached_frac", {}).values())
    )
    Path(a.out).write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("save", "compare"))
    p.add_argument("a")
    p.add_argument("b", nargs="?")
    p.add_argument("out", nargs="?")
    p.add_argument("--set", default="luno:MAIN_7")
    p.add_argument("--data-root")
    p.add_argument("--ao-sif")
    p.add_argument("--with-a", action="store_true")
    p.add_argument("--cached-t")
    p.add_argument("--cached-a")
    a = p.parse_args()
    if a.mode == "save":
        a.out = a.a
        save(a)
    else:
        compare(a)


if __name__ == "__main__":
    main()
