import json, sys
for p in sys.argv[1:]:
    r = json.load(open(p))
    f = lambda xs: ", ".join("nan" if x != x else f"{x:.3g}" for x in xs)
    print(p.split("/")[-1][:-5], "| frac", f(r["perdir_converged"]), "| step med", f([s["median"] or 0 for s in r["step_stats"]]),
          "| e/ehat", f(r["e_over_ehat"]), "| flag", r["flagged_per_direction"], "| d0 ph", round(r["phase_std_rad"][0], 3), "| it", r["iterations"])
