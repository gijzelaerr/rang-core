# SPDX-License-Identifier: MIT
"""Diagnosis for M1 (research/msv4-interop.md section 7, M1 run 05; post hoc,
not a measure).

The xarray-ms arm checked against the MSv2 reference with its
autocorrelation rows removed, plus the baseline counts of each store. Run as
`python m1_diag_autos.py research/results/msv4-interop OUT.json` (the
harness directory, then the output); the stores are those of `convert-01`.
"""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = "D:/rang/outputs/msv4-20261116"


def main(harness_dir, out_path):
    sys.path.insert(0, harness_dir)
    import msv4_interop as h
    import xarray as xr

    out = {}
    for case, ms in h.case_paths(ROOT).items():
        ref = h._ms_reference(ms)
        auto = ref["ANTENNA1"] == ref["ANTENNA2"]
        path = h.store(ROOT, "xms", case)
        tree = xr.open_datatree(str(path), engine="zarr", chunks=None)
        parts = {n: c.ds for n, c in tree.children.items() if "data_groups" in c.attrs}
        store_autos = sum(
            int(
                (
                    ds.baseline_antenna1_name.values == ds.baseline_antenna2_name.values
                ).sum()
            )
            for ds in parts.values()
        )
        keep = ~auto
        cross = dict(ref)
        for k in ("TIME", "ANTENNA1", "ANTENNA2", "DATA_DESC_ID", "UVW"):
            cross[k] = ref[k][keep]
        cross["cells"] = {}
        for ddid, cells in ref["cells"].items():
            k = keep[np.flatnonzero(ref["DATA_DESC_ID"] == ddid)]
            cross["cells"][ddid] = {c: v[k] for c, v in cells.items()}
        arm = h.check_arm(ms, path, cross)
        out[case] = {
            "ms_rows": len(auto),
            "ms_auto_rows": int(auto.sum()),
            "store_baselines": {
                n: int(ds.sizes["baseline_id"]) for n, ds in parts.items()
            },
            "store_auto_baselines": store_autos,
            "outcome_cross_only": arm["outcome"],
            "measures": arm["measures"],
            "loader_rows": arm["loader_rows"],
            "pads": arm["pads"],
        }
        print(case, out[case], flush=True)
    Path(out_path).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
