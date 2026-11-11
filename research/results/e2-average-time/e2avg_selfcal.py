"""Item 3 of research/e2-average-time.md: what `rang-core selfcal`'s solve
(`rang.cal_selfcal.solve` through `cal_gain._solve_gain_field`, budget
`core_chunks.budget(config, info).chain()`) needs on E2-A's target, from the
metadata-only preflight MS only (no visibility is read): the smallest unit
(one solution interval with all its channels) under the current planner, at
4096 channels and at CARACal's 8x channel average (512), with and without
time pre-averaging within the interval.

    python e2avg_selfcal.py OUT.json
"""

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import e2avg_common as C
from rang import cal_chunks, cal_selfcal, core_chunks, core_config
from rang import core_pipeline as pipe

MS = Path(r"D:\rang\outputs\e2-20261110-10-preflight\e2a-meta.ms")
CONFIG = C.ROOT / "research" / "results" / "e2-acceptance-scripts" / "e2a.yaml"


def main(out):
    raw = core_config.load(CONFIG)
    config = core_config.validate(raw, ["calibrate"])
    info = pipe.inspect_ms(MS)
    rows = info["rows"]
    target = info["fields"].index("ESO137-001")
    idx = pipe._selected_rows(rows, [target], config["data"]["scans"])
    plan = core_chunks.budget(config, info)
    chain = plan.chain()
    rec = {"ms": str(MS), "target_rows": len(idx), "limit_gb": plan.limit_gb,
           "scans": sorted({int(s) for s in rows["SCAN_NUMBER"][idx]}),
           "antennas": int(max(rows["ANTENNA1"].max(), rows["ANTENNA2"].max()) + 1),
           "times": len(np.unique(rows["TIME"][idx])), "terms": {}}  # fmt: skip
    for term in raw["selfcal"]["terms"]:
        tb, _, _ = cal_selfcal.time_bins(rows["TIME"][idx], rows["SCAN_NUMBER"][idx],
                                         rows["FIELD_ID"][idx], term["solint"])  # fmt: skip
        per = np.bincount(tb)
        avg = cal_chunks.Average(tb, rows["ANTENNA1"][idx], rows["ANTENNA2"][idx],
                                 np.zeros(len(idx), bool))  # fmt: skip
        r = {"intervals": len(per), "rows_per_interval_max": int(per.max()),
             "averaged_rows_per_interval_max": int(np.bincount(avg.time_bin).max())}  # fmt: skip
        for nchan in (4096, 512):
            for mode, a in (("rows", None), ("time_averaged", avg)):
                bins = tb if a is None else a.time_bin
                key = f"{mode}_{nchan}ch"
                try:
                    chunks, _ = cal_chunks.plan(bins, nchan, 4, chain, per_channel=False,
                                                what="selfcal", average=a)  # fmt: skip
                    r[key] = {"fits": True, "chunks": len(chunks)}
                except core_chunks.MemoryLimitError as exc:
                    r[key] = {"fits": False, "message": str(exc)}
        rec["terms"][f"{term['type']} solint {term['solint']}"] = r
    C.write(out, rec)
    print(C.json.dumps(rec, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
