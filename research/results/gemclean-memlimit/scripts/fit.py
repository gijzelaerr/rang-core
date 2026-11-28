# SPDX-License-Identifier: MIT
"""Fit and gate Q of research/gemclean-memlimit.md.

    fit.py OUT_ROOT [--fixed K.json]

Fit: from the binary's F*-bin reports (heap phases of its counting allocator), the fixed part per
pixel of each phase that `core/src/gemclean/memlimit.rs` adds to its exact terms, the largest over the
two fit cases of each precision. Gate Q: E recomputed from each extension case's recorded inputs
with those fixed parts (the same formulas as memlimit.rs), against the case's peak_memory_bytes.
Writes OUT_ROOT/fit.json.
"""

import json
import sys
from pathlib import Path

MARGIN = 1.03
GIB = 2**30


def report(root, tag):
    return json.loads((root / "img" / tag / "image-report.json").read_text())


def exact(i):
    """The exact terms of each phase (memlimit.rs) without the fixed parts, and the base `rest`."""
    t, c, a = i["real"], i["kept_cells"], i["weighted"]
    n2 = i["n"] ** 2
    psf2 = 4 * n2
    dense = 16 * c + i["uvw_bytes"]
    dense_m = (8 + t) * c + i["uvw_bytes"]
    return {
        "dense": dense,
        "measurement": dense + (4 * c if t == 4 else 0),
        "psf": dense_m + i["grid_2n"] + psf2 * t + (8 + 2 * t) * a,
        "beam": dense_m + psf2 * 8 + 8 * a + (8 + t) * a,
        "clean": i["uvw_bytes"] + (20 + 3 * t) * a + i["grid_n"],
        "n2": n2,
        "psf2": psf2,
    }


def heap_phases(rep):
    ph = rep["memory"]["phases"]
    lab = [p["label"] for p in ph]
    k = lab.index("compact")
    live = ph[k]["heap_end_bytes"]
    psf = ph[lab.index("psf 2n")]["heap_peak_bytes"]
    beam = max(
        ph[lab.index(x)]["heap_peak_bytes"] for x in ("plan", "beam", "compacted")
    )
    i0 = lab.index("compacted") + 1
    clean = max(p["heap_peak_bytes"] for p in ph[i0:] if p["label"] != "write")
    return live, psf, beam, clean


def estimate(i, k):
    x = exact(i)
    rest = max(i["resident"] - x["dense"], 0)
    phases = {
        "read and weights": i["resident_peak"],
        "measurement": rest + x["measurement"],
        "psf 2n": rest + x["psf"] + k["k_psf"] * x["psf2"],
        "plan, beam and compaction": rest + x["beam"] + k["k_beam"] * x["n2"],
        "major and minor cycles": rest + x["clean"] + k["k_clean"] * x["n2"],
    }
    top = max(phases, key=phases.get)
    extra = 16 * 2**20 * max(0, i.get("threads", 8) - 8)
    return phases[top] * MARGIN + extra, top, phases


def main():
    root = Path(sys.argv[1])
    fits = {}
    for real, tags in ((8, ("F1-bin", "F2-bin")), (4, ("F3-bin", "F4-bin"))):
        ks = []
        for tag in tags:
            rep = report(root, tag)
            i = rep["memory_estimate"]["inputs"]
            x = exact(i)
            live, psf, beam, clean = heap_phases(rep)
            rest = live - x["dense"]
            ks.append(
                {
                    "case": tag,
                    "heap_rest": rest,
                    "k_psf": (psf - rest - x["psf"]) / x["psf2"],
                    "k_beam": (beam - rest - x["beam"]) / x["n2"],
                    "k_clean": (clean - rest - x["clean"]) / x["n2"],
                    "heap": {"check": live, "psf": psf, "beam": beam, "clean": clean},
                }
            )
        fits[real] = {
            "cases": ks,
            "fixed": {k: max(c[k] for c in ks) for k in ("k_psf", "k_beam", "k_clean")},
        }
    if "--fixed" in sys.argv:
        given = json.loads(Path(sys.argv[sys.argv.index("--fixed") + 1]).read_text())
        for real, fit in fits.items():
            fit["fixed"] = given[str(real)]
    rows = []
    for tag in ("F1", "F2", "F3", "F4", "V1", "V2", "V3", "V4", "V5"):
        p = root / "img" / tag / "image-report.json"
        if not p.exists():
            rows.append({"case": tag, "missing": True})
            continue
        rep = json.loads(p.read_text())
        i = rep["memory_estimate"]["inputs"]
        e, phase, phases = estimate(i, fits[i["real"]]["fixed"])
        m = rep["peak_memory_bytes"]
        rows.append(
            {
                "case": tag,
                "n": i["n"],
                "real": i["real"],
                "weighted": i["weighted"],
                "kept_cells": i["kept_cells"],
                "M_bytes": m,
                "E_bytes": round(e),
                "E_over_M": e / m,
                "E_gib": e / GIB,
                "M_gib": m / GIB,
                "phase": phase,
                "binary_E_gib": rep["memory_estimate"]["gib"],
                "lower": e >= m,
                "upper": e <= 1.15 * m,
                "phases_gib": {k: v / GIB for k, v in phases.items()},
            }
        )
    out = {"fits": fits, "Q": rows}
    (root / "fit.json").write_text(json.dumps(out, indent=1))
    for r in rows:
        if r.get("missing"):
            print(r["case"], "missing")
            continue
        print(
            f"{r['case']} n {r['n']} t {r['real']} A {r['weighted']} M {r['M_gib']:.3f} "
            f"E {r['E_gib']:.3f} E/M {r['E_over_M']:.4f} {r['phase']} lower {r['lower']} upper {r['upper']}"
        )
    print(json.dumps({k: v["fixed"] for k, v in fits.items()}))


if __name__ == "__main__":
    main()
