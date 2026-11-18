"""E2-N follow-up, coordinator item 3 (research/e2n-followup.md 2.3): per-step
flags of rang's flagger and Tricolour 0.2.1 on m007-m050, scan 7 (J1744-5144,
14 dumps), where 68 of 3a's 73 cells are.

    python fu_flagsteps.py MS R ANT1 ANT2 SCAN

1. A one-baseline MS: the rows of SCAN and ANT1-ANT2 from MS (FLAG = rang_original,
   the native flags), every subtable copied (casacore deep copy of the selection).
2. For k = 1..K (K = the strategy's steps before combine_with_input_flags): the
   strategy truncated to its first k steps, plus combine_with_input_flags; Tricolour
   (E2-N's argv, e2_post.docker) and `rang-core flag` (e2n.yaml with only that
   strategy and stage) each on its own fresh copy.
3. FLAG of each arm after each k -> R/flagsteps/flagsteps.npz and .json.

Control: at k = K both arms must equal their full-MS FLAG on that baseline
(R/fu-3a-planes.npz); otherwise the one-baseline runs do not stand for the full run.
Runs with the follow-up venv's python-casacore-free stack plus casacore from
CASA_PY (a venv with python-casacore) for step 1.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / "research" / "results" / "e2n-scripts"),
                str(ROOT / "research" / "results" / "e2-acceptance-scripts")]  # fmt: skip

import e2_post as P
import e2n_nash  # noqa: F401  (patches e2_post.docker to apptainer)

N = ROOT / "research" / "results" / "e2n-scripts"
STRATEGY = N / "mk_rfi_flagging_calibrator_fields_firstpass.yaml"
CONFIG = N / "e2n.yaml"
CASA_PY = Path.home() / "Build" / "tmp" / "20261116-e2n" / "venv" / "bin" / "python"

MINI_PY = """
import sys
from casacore.tables import table
ms, out, a1, a2, scan, version = sys.argv[1:7]
t = table(ms, ack=False)
names = list(table(ms + "::ANTENNA", ack=False).getcol("NAME"))
i1, i2 = names.index(a1), names.index(a2)
s = t.query(f"SCAN_NUMBER=={scan} && ANTENNA1=={i1} && ANTENNA2=={i2}", sortlist="TIME")
s.copy(out, deep=True)
s.close()
m = table(out, readonly=False, ack=False)
rows = t.query(f"SCAN_NUMBER=={scan} && ANTENNA1=={i1} && ANTENNA2=={i2}", sortlist="TIME",
               columns="ROWNUMBER() AS R").getcol("R")
fv = table(ms + ".flagversions/flags." + version, ack=False)
import numpy as np
f = np.stack([fv.getcell("FLAG", int(r)) for r in rows])
m.putcol("FLAG", f)
m.close()
print(len(rows))
"""


def strategies(k):
    s = yaml.safe_load(STRATEGY.read_text())
    steps = s["strategies"]
    combine = [x for x in steps if x["task"] == "combine_with_input_flags"]
    body = [x for x in steps if x["task"] != "combine_with_input_flags"]
    return {"strategies": body[:k] + combine}, len(body), [x["name"] for x in body]


def main(ms, r, a1, a2, scan):
    from rang import core_ms

    ms, r = Path(ms), Path(r)
    d = r / "flagsteps"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    mini = d / "mini.ms"
    (d / "mini.py").write_text(MINI_PY, encoding="utf-8")
    out = subprocess.run([str(CASA_PY), str(d / "mini.py"), str(ms), str(mini), a1, a2, scan,
                          "rang_original"], capture_output=True, text=True, check=True)  # fmt: skip
    nrows = int(out.stdout.strip().splitlines()[-1])
    _, K, names = strategies(1)
    cfg = yaml.safe_load(CONFIG.read_text())
    flags = {"rang": [], "tricolour": []}
    rcs = []
    for k in range(1, K + 1):
        strat, _, _ = strategies(k)
        sp = d / f"strategy-{k:02d}.yaml"
        sp.write_text(yaml.safe_dump(strat, sort_keys=False), encoding="utf-8")
        # Tricolour
        tm = d / f"tri-{k:02d}.ms"
        shutil.copytree(mini, tm)
        shutil.copy(sp, d / "tricolour-strategy.yaml")
        rc_t = P.docker(d, P.TRICOLOUR_IMAGE, [(d, "/ms"), (d, "/p")],
                        f"tricolour -c /p/tricolour-strategy.yaml -fs polarisation -dc DATA -dpm "
                        f"/ms/{tm.name}", f"tri-{k:02d}", 2)  # fmt: skip
        # rang
        rm = d / f"rang-{k:02d}.ms"
        shutil.copytree(mini, rm)
        c = dict(cfg)
        c["flag"] = {"strategy": str(sp)}
        c["run"] = {"stages": ["flag"]}
        cp = d / f"rang-{k:02d}.yaml"
        cp.write_text(yaml.safe_dump(c, sort_keys=False), encoding="utf-8")
        with open(d / f"rang-{k:02d}.out", "w", encoding="utf-8") as fh:
            rc_r = subprocess.run([sys.executable, "-m", "rang.core_cli", "flag", str(cp), str(rm)],
                                  stdout=fh, stderr=subprocess.STDOUT, check=False).returncode  # fmt: skip
        rcs.append(
            {"k": k, "step": names[k - 1], "tricolour_exit": rc_t, "rang_exit": rc_r}
        )
        for arm, m in (("tricolour", tm), ("rang", rm)):
            with core_ms.open_table(m) as t:
                flags[arm].append(np.asarray(t.getcol("FLAG"), bool))
        shutil.rmtree(tm)
        shutil.rmtree(rm)
        shutil.rmtree(rm.with_name(rm.name + ".rang-run"), ignore_errors=True)
        shutil.rmtree(rm.with_name(rm.name + ".flagversions"), ignore_errors=True)
    fr, ft = np.array(flags["rang"]), np.array(flags["tricolour"])
    np.savez_compressed(d / "flagsteps.npz", rang=fr, tricolour=ft)
    z = np.load(r / "fu-3a-planes.npz")
    idx = [e for e in json.loads((r / "fu-3a-planes.json").read_text())
           if e["scan"] == int(scan) and e["ant1"] == a1 and e["ant2"] == a2][0]["index"]  # fmt: skip
    full_r, full_t = z[f"p{idx}_rang"], z[f"p{idx}_tricolour"]
    per = []
    for i, row in enumerate(rcs):
        cr, ct = fr[i].any(-1), ft[i].any(-1)
        dif = cr != ct
        per.append({**row, "rang_flagged": int(cr.sum()), "tricolour_flagged": int(ct.sum()),
                    "cells_differ": int(dif.sum()), "rang_only": int((cr & ~ct).sum()),
                    "tricolour_only": int((~cr & ct).sum()),
                    "channels_differ": [int(c) for c in np.nonzero(dif.any(0))[0]]})  # fmt: skip
    control = {"rows": nrows,
               "rang_equals_full_run": bool((fr[-1] == full_r).all()),
               "tricolour_equals_full_run": bool((ft[-1] == full_t).all())}  # fmt: skip
    P.write(d / "flagsteps.json", {"ms": str(ms), "baseline": f"{a1}-{a2}", "scan": int(scan),
                                   "control": control, "per_k": per})  # fmt: skip
    shutil.rmtree(mini)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:6]))
