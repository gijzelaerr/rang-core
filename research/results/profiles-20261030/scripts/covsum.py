import json
import sys

cov = json.load(open(sys.argv[1]))
out = sys.argv[2]
groups = {
    "core": lambda m: m.startswith("core"),
    "frozen_imported_by_core": lambda m: m in {
        "flagging", "flagging_workflow", "flagging_actions", "flagging_injections", "flagging_prospective",
        "flagging_signal", "flagging_signal_guard", "flagging_response", "flagging_trend", "flagging_structured",
        "flagging_structured_proposals", "flagging_caracal", "flagging_balanced", "flagging_equivariance",
        "flagging_influence", "flagging_imaging", "flagging_next", "flagging_comparators", "flagging_prepared",
        "imaging_sensitivity", "projector"},
    "frozen_recipe_only": lambda m: m in {
        "flagging_concurrent", "flagging_parallel", "flagging_provenance", "flagging_public",
        "flagging_transfer", "flagging_uncertainty", "flagging_sky"},
    "pointing": lambda m: m in {"pointing", "beams", "blocked", "observability", "gauge", "uncertainty", "__init__"},
}
files = {}
for path, rec in cov["files"].items():
    m = path.split("/")[-1][:-3]
    s = rec["summary"]
    files[m] = {"statements": s["num_statements"], "executed": s["covered_lines"]}
summary = {}
for g, pred in groups.items():
    st = sum(v["statements"] for k, v in files.items() if pred(k))
    ex = sum(v["executed"] for k, v in files.items() if pred(k))
    summary[g] = {"statements": st, "executed": ex, "fraction": round(ex / st, 3) if st else None}
json.dump({"chains": ["K replay", "K precondition", "K checker", "section 6", "actions", "injections",
                      "prospective", "signal", "trend mirror", "trend", "imaging replay", "Tricolour controls"],
           "groups": summary, "files": files}, open(out, "w"), indent=1)
print(json.dumps(summary, indent=1))
