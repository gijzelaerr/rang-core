"""DRAFT, NOT RUN, NOT FROZEN (research/uhf-11.md section 7; D4, D5).

The UHF gate's CASA 6.7.6.14 arm: examples like e2-acceptance-scripts/e1b_casa.py,
with the UHF changes only. Field names, refant and the scan split come from the
development set's listobs at freeze time; nothing here has seen UHF data.
"""

FCAL = "J0408-6545"  # or J1939-6342 if the chosen block has it
# rang.fluxstd.CARACAL_0408: CARACal 8f7bb363's setjy manual model for 0408-65.
# Below 843 MHz it extrapolates the 2016 cubic (rang refuses there unless
# extrapolate=True; CASA evaluates silently).
M0408 = {"fluxdensity": [15.523235461976729, 0.0, 0.0, 0.0], "reffreq": "1.4GHz",
         "spix": [-1.1345095964241985, -0.3089551282372074, 0.08610004964581237,
                  1.8195423333847356e-07]}  # fmt: skip
UVRANGE = ">150"


def calls(ms, refant, t="/run/casa"):
    common = {"vis": ms, "refant": refant, "minsnr": 3.0, "minblperant": 4}
    return [
        {"task": "setjy", "args": {"vis": ms, "field": FCAL, "standard": "manual",
         **M0408, "scalebychan": True, "usescratch": True}},
        {"task": "gaincal", "args": {**common, "caltable": f"{t}/K", "field": FCAL,
         "gaintype": "K", "solint": "inf"}},
        {"task": "gaincal", "args": {**common, "caltable": f"{t}/G", "field": FCAL,
         "gaintype": "G", "calmode": "ap", "solint": "inf", "uvrange": UVRANGE,
         "gaintable": [f"{t}/K"]}},
        {"task": "bandpass", "args": {**common, "caltable": f"{t}/B", "field": FCAL,
         "solint": "inf", "combine": "scan", "fillgaps": 70, "uvrange": UVRANGE,
         "gaintable": [f"{t}/K", f"{t}/G"]}},
        # secondary G, fluxscale and applycal as e1b_casa.casa_calls, unchanged
    ]  # fmt: skip
