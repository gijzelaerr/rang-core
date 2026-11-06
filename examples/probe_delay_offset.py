"""Task C2b (research/c2b-delay.md), post hoc after the phase probe (run
-03): does a delay model with a free phase offset per antenna and hand
(QuartiCal 0.2.7's `delay_and_offset`, FFT initial estimate, Gauss-Newton)
meet CASA's K where `delay` does not? QuartiCal only; nothing of rang's is
solved. CASA's tables are run -02's.

    python examples/probe_delay_offset.py <run> <run-02>
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_delay as cd
import check_formats as cf
import check_gain as cg
from rang.formats import caltable

# name, source, field, time interval, CASA table of run -02
CASES = [
    ("O-slice-t0", "slice", None, 0, "B-slice-inf.K"),
    ("O-slice-t1", "slice", None, 1, "B-slice-int.K"),
    ("O-a1-noapply-f0-t0", "a1", 0, 0, "B-a1-noapply-inf-f0.K"),
]


def main(argv):
    run, r02 = Path(argv[1]), Path(argv[2])
    run.mkdir(parents=True, exist_ok=False)
    p = cd.paths(argv)
    started = time.perf_counter()
    # A1 field 0: raw DATA, A1's parallactic model (no G, no B), RFI flags.
    tr = dict(np.load(p["truth"]))
    rows, values = cg.a1_model(p["a1"], tr, [0], parang=True)
    c = cg.columns(p["a1"], ["DATA"])
    model = np.zeros_like(c["DATA"])
    model[rows] = values
    np.savez(run / "a1-cmodel.npz", values=model.astype(np.complex64))
    np.savez(run / "a1-rfi.npz", values=cg.rfi_flags(p["a1"], p["rfi"], model.shape[1]))
    steps = [
        f"{cg.QC} -I /ex/oracle_gain.py qc-copy /src/slice.ms /run/qc/slice.ms",
        (
            f"{cg.QC} -I /ex/oracle_gain.py qc-copy /src/a1.ms /run/qc/a1.ms "
            "/run/a1-cmodel.npz CMODEL /run/a1-rfi.npz FLAG"
        ),
    ]
    opts = [o.replace("K.type=delay", "K.type=delay_and_offset") for o in cd.QC_OPTIONS]
    for name, key, fld, ti, _ in CASES:
        model_col = "MODEL_DATA" if key == "slice" else "CMODEL"
        o = ["input_ms.data_column=DATA", f"input_model.recipe={model_col}",
             f"K.time_interval={ti}", *opts]  # fmt: skip
        if fld is not None:
            o.append(f"input_ms.select_fields=[{fld}]")
        steps.append(
            f"{cg.QC} -I /ex/oracle_gain.py qc-solve /run/qc/{key}.ms /run/qc/{name} "
            + " ".join(o)
        )
    (run / "qc").mkdir()
    cf.TIMINGS.clear()
    cf.docker(
        cf.FORMATS_IMAGE,
        ["sh", "-c", " && ".join(steps)],
        [
            (run, "/run", "rw"),
            (HERE, "/ex", "ro"),
            (p["slice"], "/src/slice.ms", "ro"),
            (p["a1"], "/src/a1.ms", "ro"),
        ],
        "quartical delay_and_offset x3",
        env={"NUMBA_CACHE_DIR": "/run/numba"},
    )
    out = {}
    for name, _, _, _, ctab in CASES:
        q = run / "qc" / name
        summary = json.loads((q / "summary.json").read_text())
        names = summary["param_names"]
        params = np.load(q / "params.npy")
        pflags = np.load(q / "param_flags.npy") != 0
        idx = [names.index(n) for n in names if n.startswith("delay")]
        qd = params[:, 0][..., idx] * 1e9  # (time, ant, 2) ns
        qf = np.repeat(pflags[:, 0][..., None], 2, -1)
        tab = caltable.read(r02 / "casa" / ctab)
        nant = qd.shape[1]
        _, d, f, _ = cd.k_table(tab, nant)
        r = {"param_names": names, "iterations": summary["conv_iter"],
             "shape": list(qd.shape), "casa_shape": list(d.shape)}  # fmt: skip
        if qd.shape == d.shape:
            r["delays"] = cd.delay_compare(qd, qf, d, f, 0)
        out[name] = r
    out["timings"] = cf.TIMINGS
    out["seconds"] = time.perf_counter() - started
    cg.write(run / "probe.json", out)
    print(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
