"""One-screen digest of e1b result files (CASA arm, or rang's under e1b_score),
in e1-chain.md 7.2's form.

    python e1b_casa_brief.py RESULT.json [RESULT.json ...]
"""

import json
import sys


def g(d, *keys):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def f(x, fmt=".3g"):
    return "-" if x is None else format(x, fmt)


def brief(path):
    with open(path, encoding="utf-8") as fh:
        r = json.load(fh)
    t = r.get("terms", {})
    twin = r.get("mode") == "twin"
    lines = [f"== {path} ({r.get('mode')}, refant {','.join(r.get('refant', []))})"]
    if twin:
        lines.append(f"K max {f(g(t, 'K', 'max_abs_e_ns'))} ns; target composite median "
                     f"{f(g(t, 'composite', 'target_1gc', 'abs_rel_error', 'median'))} p95 "
                     f"{f(g(t, 'composite', 'target_1gc', 'abs_rel_error', 'p95'))} max "
                     f"{f(g(t, 'composite', 'target_1gc', 'abs_rel_error', 'max'))}; "
                     f"cross-hand max {f(g(t, 'crosshand', 'combined', 'max_abs_rad'))} rad; "
                     f"KCROSS max {f(g(t, 'crosshand', 'kcross', 'max_abs_ns'))} ns; "
                     f"Xf max {f(g(t, 'crosshand', 'xf', 'max_abs_rad'))} rad; "
                     f"Df max {f(g(t, 'Df', 'max_abs'))}")  # fmt: skip
    else:

        def rg(*k):
            d = g(t, *k)
            if not d:
                return "-"
            return (
                f"{f(d.get('median_abs_over_s'))} (median |e| "
                f"{f(g(d, 'abs_e', 'median'))}, s {f(g(d, 's', 'median'))})"
            )

        lines.append(f"K {rg('K')}; target 1GC {rg('composite', 'target_1gc')}; "
                     f"cross-hand {rg('crosshand', 'combined')} p95 |e| "
                     f"{f(g(t, 'crosshand', 'combined', 'abs_e', 'p95'))}; "
                     f"KCROSS {rg('crosshand', 'kcross')}; Xf {rg('crosshand', 'xf')}; "
                     f"Df {rg('Df')}")  # fmt: skip
    kc = g(t, "crosshand", "kcross_ns")
    if kc:
        lines.append(
            "KCROSS - tau_eff per scan (ns): " + ", ".join(f"{v:+.3f}" for v in kc)
        )
    rgauge = g(t, "crosshand", "refant_gauge")
    if rgauge:
        lines.append(f"refant gauge: detected {rgauge.get('refant_per_channel_detected')}, "
                     f"used {list(rgauge.get('refants_used', {}))}")  # fmt: skip
    for fld in ("J1939-6342", "SIM-GCAL", "3C286-SIM"):
        v = g(t, "composite", fld, "abs_rel_error", "median")
        lines.append(f"  composite {fld} median {f(v)}")
    fs = g(t, "F", "fluxscale", "SIM-GCAL", "fitted_flux_jy")
    lines.append(
        f"F SIM-GCAL {f(fs, '.4f')} Jy (truth {f(g(t, 'F', 'truth_gcal_jy_at_1284mhz'), '.4f')})"
    )
    p = r.get("polarisation")
    if p:
        for col, o in p["columns"].items():
            comps = {c["index"]: c for c in o["components"]}
            gl = []
            for k in p["gated_polarised"]:
                c = comps.get(k)
                if c:
                    gl.append(
                        f"{k}: dp {100 * c['dp']:+.2f} pt, dchi {c['dchi_deg']:+.2f} deg"
                    )
            lines.append(f"pol {col}: " + "; ".join(gl) + f" -> {o['polarised_pass']}")
            lk = [c["leak"] for c in o["components"] if c.get("p_true") == 0]
            if lk:
                lines.append(
                    f"  target points leakage {100 * min(lk):.2f}-{100 * max(lk):.2f} %"
                )
        lines.append(f"SIM-GCAL leakage median {100 * p['gcal_leak']['median']:.3f} % "
                     f"p95 {100 * p['gcal_leak']['p95']:.2f} %; 3C286 p "
                     f"{p['xcal_reported']['p_median']:.4f} |chi-33| median "
                     f"{p['xcal_reported']['abs_chi_minus_33']['median']:.2f}; "
                     f"J1939 leak median {100 * p['fcal_leak_reported']['median']:.2f} %")  # fmt: skip
    v = r.get("vs_rang")
    if v:
        lines.append(f"vs rang: K raw median {f(g(v, 'K_ns', 'raw', 'median'))} p95 "
                     f"{f(g(v, 'K_ns', 'raw', 'p95'))} max {f(g(v, 'K_ns', 'raw', 'max'))} ns; "
                     f"Xf median {f(g(v, 'Xf_rad', 'median'))} max {f(g(v, 'Xf_rad', 'max'))} rad; "
                     f"Df median {f(g(v, 'Df_abs', 'median'))} max {f(g(v, 'Df_abs', 'max'))}")  # fmt: skip
        lines.append(f"  KCROSS rang {[round(x, 3) for x in v['Kcross_ns_per_scan']['rang']]} "
                     f"casa {[round(x, 3) for x in v['Kcross_ns_per_scan']['casa']]}")  # fmt: skip
    return "\n".join(lines)


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(brief(path))
