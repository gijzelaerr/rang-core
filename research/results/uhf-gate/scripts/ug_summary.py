# SPDX-License-Identifier: MIT
"""The UHF gate's rows (research/uhf-gate.md section 5) read from one block's
result directory, against the frozen tolerances; nothing is rescored here, every
number comes from the step's own JSON.

    python ug_summary.py R BLOCK      -> R/summary.json, markdown rows on stdout

A row whose JSON is missing reads "not checked" (section 9: never met).
"""

import json
import sys
from pathlib import Path


def load(r, name):
    p = Path(r) / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def verdict(ok):
    return {True: "met", False: "**not met**", None: "not checked"}[ok]


def rows(r, block):
    out = []

    def add(gate, reading, tol, ok):
        out.append({"gate": gate, "reading": reading, "tolerance": tol, "met": ok})

    g1 = load(r, "gate1.json")
    add("1", "rc 0, every stage in the receipt" if g1 else "-", "as A0",
        None if g1 is None else bool(g1["met"]))  # fmt: skip
    for name, label in (("g2a.json", "2a after g2a"), ("g3a-restore.json", "2a after g3a-restore"),
                        ("final-restore.json", "2a after final-restore")):  # fmt: skip
        d = load(r, name)
        add(label, "FLAG, FLAG_ROW hashes" if d else "-", "equal",
            None if d is None else bool(d.get("met")))  # fmt: skip
    for name in ("casacore", "casa-ro", "wsclean", "daskms"):
        d = load(r, f"g2b-{name}.json")
        add(f"2b {name}", "-" if d is None else "exit 0" if d.get("met") else "see json", "exit 0",
            None if d is None else bool(d.get("met")))  # fmt: skip
    d = load(r, "g2b-applycal.json")
    add("2b applycal vs rang (in place)",
        "-" if d is None else f"{d['compared_cells']:,} cells, {d['cells_over_class_c']} over class C "
        f"(max {d['max_eps_of_cell_max']:.2f} eps), flags {d['flag_elements_differ']} differ",
        "class C", None if d is None else bool(d["met"]))  # fmt: skip
    d = load(r, "g2c.json")
    add(
        "2c",
        "astropy WCS" if d else "-",
        "valid",
        None if d is None else bool(d["met"]),
    )
    d = load(r, "g3a.json")
    add("3a", "-" if d is None else f"{d['cells_differ']:,} of {d['cells']:,} cells differ "
        f"({d['rang_only']} rang only, {d['tricolour_only']} Tricolour only)",
        "0 cells, or the chunk-edge rule", None if d is None else d["cells_differ"] == 0)  # fmt: skip
    b = load(r, "g3b.json")
    if b is None:
        add("3b", "-", "section 5", None)
    else:
        t = b["terms"]

        def stat(term, key):
            return t[term][key]

        k = stat("K", "abs_ns")
        add("3b K", f"median {k['median']:.3g} ns, p95 {k['p95']:.3g} ns (n {k['n']})",
            "<= 0.01, <= 0.03 ns", k["median"] <= 0.01 and k["p95"] <= 0.03)  # fmt: skip
        kc = stat("Kcross", "abs_ns")
        add("3b KCROSS", f"max {kc['max']:.3g} ns (n {kc['n']})", "<= 0.02 ns",
            kc["max"] <= 0.02)  # fmt: skip
        x = stat("Xf", "abs_deg")
        add("3b Xf", f"median {x['median']:.3g} deg, p95 {x['p95']:.3g} deg (n {x['n']})",
            "<= 0.5, <= 2 deg", x["median"] <= 0.5 and x["p95"] <= 2.0)  # fmt: skip
        df = stat("Df", "abs")
        add("3b Df", f"median {df['median']:.3g}, p95 {df['p95']:.3g} (n {df['n']})",
            "<= 1e-3, <= 5e-3", df["median"] <= 1e-3 and df["p95"] <= 5e-3)  # fmt: skip
        gp = stat("Gpol", "abs_deg")
        add("3b Gpol", f"median {gp['median']:.3g} deg (n {gp['n']})", "<= 0.1 deg",
            gp["median"] <= 0.1)  # fmt: skip
        for key, label in (
            ("composite_fcal_KGB", "fcal K G B"),
            ("composite_gcal_KFB", "gcal K F B"),
        ):
            c = b[key]
            add(f"3b {label} composite", f"median {c['median']:.3g}, p95 {c['p95']:.3g} "
                f"(n {c['n']:,}, flags {c['flags_differ']:,} differ)", "median 7e-4, p95 3e-3",
                c["median"] <= 7e-4 and c["p95"] <= 3e-3)  # fmt: skip
    g = load(r, "g3c.json")
    if g is None:
        add("3c", "-", "section 5", None)
    else:
        add("3c dirty L-inf / peak", f"{g['dirty']['max_over_peak']:.3g}", "<= 1e-6",
            bool(g["dirty"]["met"]))  # fmt: skip
        c = g["compact"]["gated"]
        add("3c compact (inner 1.0 deg)", f"n {c['n']}, median {c.get('median', float('nan')):.4f}, "
            f"robust scatter {100 * c.get('robust_scatter', float('nan')):.2f} %",
            "within 0.5 %, <= 1 %", c["met"])  # fmt: skip
    w = load(r, "rows.json")
    for key, label, tol in (("secondary", "Secondary", "I 1 %, |dp| 0.1 point, |dchi| 1 deg"),
                            ("parity", "3C 286 parity", "|dp| 0.1 point, |dchi| 0.5 deg"),
                            ("leak_flux", "J0408-6545 flux transfer", "I within 1 %")):  # fmt: skip
        if key == "leak_flux" and block == "D":
            continue
        x = (w or {}).get(key)
        if x is None:
            add(label, "-", tol, None)
            continue
        dp = x["max_abs_dp"]
        reading = (f"{x['bins_scored']} bins scored; max |dI| "
                   f"{100 * (x['max_abs_dI_rel'] or 0):.3f} %"
                   + ("" if key == "leak_flux" else
                      f", max |dp| {100 * (dp or 0):.3f} point, max |dchi| {x['max_abs_dchi_deg'] or 0:.3f} deg"))  # fmt: skip
        add(label, reading, tol, bool(x["met"]))
    t = load(r, "row-target.json")
    if t is None:
        add("Target compact", "-", "median 1 %, scatter 1.5 %", None)
        add("Target noise, dynamic range", "-", "rms <= 1.2 x, peak/rms >= 0.8 x", None)
    else:
        c = t["compact"]["gated_within_limit"]
        add("Target compact (inner 1.0 deg)", f"n {c['n']}, median {c.get('median', float('nan')):.4f}, "
            f"robust scatter {100 * c.get('robust_scatter', float('nan')):.2f} %",
            "within 1 %, <= 1.5 %", c["met"])  # fmt: skip
        n = t["noise_dynamic_range"]
        add("Target noise, dynamic range", f"rms {n['rms_ratio']:.3f} x, peak/rms "
            f"{n['dynamic_range_ratio']:.3f} x", "<= 1.2 x; >= 0.8 x", bool(n["met"]))  # fmt: skip
    s = load(r, "row-selfcal.json")
    add("Self-calibration rms", "-" if s is None else f"after/before {s['ratio_after_before']:.3f}",
        "<= 1.02", None if s is None else bool(s["met"]))  # fmt: skip
    q = load(r, "qc-selfcal.json")
    if q is None:
        add("Self-calibration gains vs QuartiCal", "-", "class B", None)
    else:
        rd = q["rounds"]
        add("Self-calibration gains vs QuartiCal (averaged form, labelled)",
            "; ".join(f"{x['term']['name']}: median {x['median']:.2g}, p95 {x['p95']:.2g}" for x in rd),
            "class B (7e-4, 3e-3)", all(bool(x["pass"]) for x in rd))  # fmt: skip
    m = load(r, "model-row.json")
    add("Model row", "-" if m is None else f"max {m['max_abs_diff_over_peak']:.3g} of the peak "
        f"({m['rows']} rows x {m['channels']} ch x 4 corr)", "<= 1e-5",
        None if m is None else bool(m["met"]))  # fmt: skip
    if block != "D":
        lk = load(r, "row-leakage.json")
        add("J0408-6545 leakage", "-" if lk is None else ", ".join(
            f"{p} rang {100 * lk[p]['rang']:.3f} % / CASA {100 * lk[p]['casa']:.3f} %" for p in "QUV"),
            "each <= 0.5 %, rang <= 1.2 x CASA", None if lk is None else bool(lk["met"]))  # fmt: skip
    return out


def main(r, block):
    out = rows(r, block)
    Path(r, "summary.json").write_text(
        json.dumps(out, indent=1) + "\n", encoding="utf-8"
    )
    print("| Gate | Reading | Tolerance | Outcome |\n| --- | --- | --- | --- |")
    for x in out:
        cells = [x["gate"], x["reading"], x["tolerance"], verdict(x["met"])]
        print("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
