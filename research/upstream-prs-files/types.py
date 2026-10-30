"""Per CARACal strategy file: the Python type of each float parameter in every sum_threshold step.
A file whose steps disagree compiles _get_flags_impl more than once (tricolour #111)."""
import glob
import sys

import yaml

FLOATS = ("outlier_nsigma", "background_reject", "spike_width_time", "spike_width_freq",
          "flag_all_time_frac", "flag_all_freq_frac", "rho")
for path in sorted(glob.glob(sys.argv[1] + "/*.yaml")):
    doc = yaml.safe_load(open(path))
    steps = [s for s in doc.get("strategies", []) if s.get("task") == "sum_threshold"]
    if not steps:
        continue
    sigs = []
    for s in steps:
        kw = s.get("kwargs", {})
        sigs.append(tuple(type(kw[k]).__name__ if k in kw else "-" for k in FLOATS))
    distinct = sorted(set(sigs))
    ints = {FLOATS[i] for sig in sigs for i, t in enumerate(sig) if t == "int"}
    print(f"{path.split('/')[-1]:55s} steps={len(steps)} signatures={len(distinct)} int-valued={sorted(ints)}")
