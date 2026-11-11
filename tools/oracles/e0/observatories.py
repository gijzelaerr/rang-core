# SPDX-License-Identifier: GPL-3.0-or-later
"""Dump casacore's observatory table as `me.observatory` returns it (task E0,
research/e0-refant-extend.md). Run in the O-CASA image with its system
python-casacore and casacore-data:

    docker run --rm -v $PWD/tools/oracles/e0:/e0:ro rang-o-casa:6.7.6.14 \
        python3 -I /e0/observatories.py > python/rang/data/casacore_observatories.json
"""

import json
import subprocess

import casacore.measures

me = casacore.measures.measures()
out = []
for name in me.obslist():
    pos = me.observatory(name)
    out.append(
        {
            "name": str(name),
            "refer": pos["refer"],
            "m0": float(pos["m0"]["value"]),
            "m1": float(pos["m1"]["value"]),
            "m2": float(pos["m2"]["value"]),
            "units": [pos["m0"]["unit"], pos["m1"]["unit"], pos["m2"]["unit"]],
        }
    )
version = subprocess.run(
    ["dpkg-query", "-W", "-f", "${Version}", "casacore-data"],
    capture_output=True,
    text=True,
    check=False,
).stdout
print(
    json.dumps(
        {
            "source": "casacore-data "
            + version
            + ", me.observatory() in rang-o-casa:6.7.6.14",
            "observatories": out,
        },
        indent=1,
    )
)
