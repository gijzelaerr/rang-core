"""Post-hoc probe of task C2a (research/c2a-gain.md, after run -03): which
weights CASA's `gaincal` solves with when tables are pre-applied.

Run -03's minsnr case scaled WEIGHT_SPECTRUM and WEIGHT of m007's rows by
1e-10, and CASA's SNR of m007 did not change. The hypothesis is that the
pre-apply resets the weights from SIGMA (`resetWeightsUsingSigma`, C1
section 3.2). Three copies of A1's small MS (model and RFI flags as run
-03), field 0, `solint='inf'`, `refant='m000'`, `minsnr=3`:

- `w-noapply`: WEIGHT_SPECTRUM, WEIGHT of m007 x 1e-10, no gaintable;
- `s-apply`: SIGMA of m007 x 1e5 (weights unchanged), gaintable truth K, B;
- `s-noapply`: the same SIGMA edit, no gaintable.

Predicted under the hypothesis: m007 flagged in `w-noapply` and `s-apply`,
not in `s-noapply`.

    python examples/probe_gain_weights.py <run>
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
from rang.formats import caltable


def main(argv):
    run = Path(argv[1])
    run.mkdir(parents=True, exist_ok=False)
    p = cg.paths(argv)
    started = time.perf_counter()
    truth = dict(np.load(p["truth"]))
    edits = run / "edits"
    edits.mkdir()
    rows, values = cg.a1_model(p["a1"], truth, [0, 2])
    np.savez(edits / "a1-model.npz", rows=rows, values=values)
    ac = cg.columns(p["a1"], ["ANTENNA1", "ANTENNA2", "FIELD_ID", "DATA"])
    rfi = cg.rfi_flags(p["a1"], p["rfi"], ac["DATA"].shape[1])
    np.savez(edits / "a1-rfi.npz", rows=np.arange(len(rfi)), flag=rfi)
    a1, a2, fld = ac["ANTENNA1"], ac["ANTENNA2"], ac["FIELD_ID"]
    m007 = np.flatnonzero((fld == 0) & ((a1 == 7) | (a2 == 7))).tolist()
    base = {"model": "/run/edits/a1-model.npz", "flag": "/run/edits/a1-rfi.npz"}
    specs = {
        "w-noapply": {**base, "weight_scale": [[m007, 1e-10]]},
        "s-apply": {**base, "sigma_scale": [[m007, 1e5]]},
        "s-noapply": {**base, "sigma_scale": [[m007, 1e5]]},
    }
    tables = {
        "w-noapply": [],
        "s-apply": ["/src/truth.K", "/src/truth.B"],
        "s-noapply": [],
    }
    steps, calls = [], []
    (run / "casa").mkdir()
    for name, spec in specs.items():
        cg.write(edits / f"{name}.json", spec)
        steps += [
            f"cp -r /src/a1.ms /run/casa/{name}.ms",
            f"{cg.CASA} -I /ex/oracle_gain.py casa-edit /run/casa/{name}.ms /run/edits/{name}.json",
        ]
        calls.append(
            {
                "vis": f"/run/casa/{name}.ms",
                "caltable": f"/run/casa/{name}.G",
                "field": "0",
                "gaintype": "G",
                "calmode": "ap",
                "solint": "inf",
                "refant": "m000",
                "minsnr": 3.0,
                "minblperant": 4,
                "gaintable": tables[name],
                "interp": ["linear"] * len(tables[name]),
            }
        )
    cg.write(run / "gaincal-spec.json", calls)
    steps.append(
        f"{cg.CASA} -I /ex/oracle_gain.py casa-gaincal /run/gaincal-spec.json /run/gaincal.json"
    )
    cf.TIMINGS.clear()
    cf.docker(
        cf.CASA_IMAGE,
        ["sh", "-c", " && ".join(steps)],
        [
            (run, "/run", "rw"),
            (HERE, "/ex", "ro"),
            (p["a1"], "/src/a1.ms", "ro"),
            (p["a1k"], "/src/truth.K", "ro"),
            (p["a1b"], "/src/truth.B", "ro"),
        ],
        "casa weight probe",
    )
    out = {}
    for name in specs:
        t = caltable.read(run / "casa" / f"{name}.G")
        a = t.column("ANTENNA1")
        out[name] = {
            "m007_snr": t.snr[a == 7, 0].tolist(),
            "m007_flag": t.flags[a == 7, 0].tolist(),
            "m006_snr": t.snr[a == 6, 0].tolist(),
        }
    out["timings"] = cf.TIMINGS
    out["seconds"] = time.perf_counter() - started
    cg.write(run / "probe.json", out)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
