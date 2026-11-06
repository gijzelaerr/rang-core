"""Task C2a (research/c2a-gain.md): CASA reads and applies a table rang wrote.

`applycal` (`rang-o-casa:6.7.6.14`, `interp='linear'`, `calwt=False`,
`applymode='calflag'`) on a fresh copy of the slice with `c.K0` and run
-05's `B-slice-60s.rang.G`, against `rang.cal_apply` with the same tables;
class C of research/c4a-apply.md, flags exact.

    python examples/probe_gain_readback.py <run> <run-05>
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_formats as cf
import check_gain as cg
from rang import cal_apply
from rang.formats import caltable


def main(argv):
    run, src = Path(argv[1]), Path(argv[2])
    run.mkdir(parents=True, exist_ok=False)
    p = cg.paths(argv)
    started = time.perf_counter()
    table = src / "casa" / "B-slice-60s.rang.G"
    script = run / "apply.py"
    script.write_text(
        "from casatasks import applycal\n"
        "applycal(vis='/run/slice.ms', field='1', gaintable=['/src/c.K0', '/src/rang.G'],\n"
        "         interp=['linear', 'linear'], calwt=[False, False], applymode='calflag',\n"
        "         parang=False, flagbackup=False)\n"
    )
    cf.TIMINGS.clear()
    cf.docker(
        cf.CASA_IMAGE,
        [
            "sh",
            "-c",
            f"cp -r /src/slice.ms /run/slice.ms && {cg.CASA} -I /run/apply.py",
        ],
        [
            (run, "/run", "rw"),
            (p["slice"], "/src/slice.ms", "ro"),
            (p["k0"], "/src/c.K0", "ro"),
            (table, "/src/rang.G", "ro"),
        ],
        "casa applycal of a rang G table",
    )
    c = cg.columns(
        run / "slice.ms",
        ["DATA", "CORRECTED_DATA", "FLAG", "TIME", "ANTENNA1", "ANTENNA2"],
    )
    orig = cg.columns(p["slice"], ["FLAG"])["FLAG"]
    tabs = [caltable.read(p["k0"]), caltable.read(table)]
    ours, flags = cal_apply.apply(
        c["DATA"],
        orig,
        c["TIME"],
        c["ANTENNA1"],
        c["ANTENNA2"],
        cg.chan_freq(p["slice"]),
        tabs,
        interp="linear",
        field_id=1,
    )
    ok = ~flags & ~c["FLAG"]
    result = {
        "class_c": cal_apply.class_c(ours, c["CORRECTED_DATA"], ok),
        "flags_exact": bool(np.array_equal(flags, c["FLAG"])),
        "timings": cf.TIMINGS,
        "seconds": time.perf_counter() - started,
    }
    result["pass"] = bool(result["class_c"]["pass"] and result["flags_exact"])
    cg.write(run / "readback.json", result)
    print(json.dumps(result, indent=1))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
