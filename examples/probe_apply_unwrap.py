"""Post-hoc probe of task C4a (research/c4a-apply.md section 7): CASA's
unwrapped B phases, read off `applycal` one antenna at a time.

    python examples/probe_apply_unwrap.py <run>

Writes a B table on every 4th channel of O-CASA's `c.ms` in which antenna 0
has the held-out run -04's random phases (seed 20261108, `hBgaps`, with its
flagged gap) and antennas 1-3 have gain 1, applies it with `applycal`, and
compares CASA's implied antenna-0 gain on baseline 0-1 (DATA / CORRECTED_DATA
on XX and YY, on-grid channels) with emulations of the frequency unwrap.
"""

import json
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_apply as ca
import check_formats as cf
from rang.formats import caltable

TAU = 2 * np.pi


def unwrap_casa(y):
    y = np.asarray(y, np.float32).copy()
    for i in range(1, len(y)):
        while float(np.float32(y[i] - y[i - 1])) > np.pi:
            y[i] = np.float32(float(y[i]) - TAU)
        while float(np.float32(y[i] - y[i - 1])) < -np.pi:
            y[i] = np.float32(float(y[i]) + TAU)
    return y


def unwrap_f64(y):
    z = np.asarray(y, np.float64).copy()
    for i in range(1, len(z)):
        while z[i] - z[i - 1] > np.pi:
            z[i] -= TAU
        while z[i] - z[i - 1] < -np.pi:
            z[i] += TAU
    return z.astype(np.float32)


def main(argv):
    run = Path(argv[1]).resolve()
    run.mkdir(parents=True, exist_ok=False)
    outputs = Path.home() / "Github/rang/outputs"
    ms = outputs / "o-casa-20261030-01" / "c.ms"
    cols = cf.ms_columns(ms)
    fid = cf.field_index(ms)
    sel = cols["FIELD_ID"] == fid
    nant = 4
    tabs = ca.heldout_tables(ms, nant, cols["TIME"][sel], fid, 20261108)
    src = tabs["hBgaps"]
    p = np.asarray(src.params).reshape(nant, -1, 2).copy()
    f = np.asarray(src.flags).reshape(nant, -1, 2).copy()
    p[1:] = 1.0
    f[1:] = False
    gaps = ca.coarse_subtables(ms, 4)
    table = caltable.from_gains(
        "B",
        [float(np.mean(cols["TIME"][sel]))],
        list(range(nant)),
        p[None],
        f[None],
        subtables=gaps,
        field_id=fid,
        refant=0,
        ms_name="c.ms",
    )
    caltable.write(table, run / "probe.B")
    cf.docker(
        cf.CASA_IMAGE,
        [
            "sh",
            "-c",
            (
                "cp -r /o/c.ms /run/probe.ms && /opt/casa/bin/python -I /ex/oracle_apply.py "
                "/run /run/probe.ms linear /run/probe.B"
            ),
        ],
        [(run, "/run", "rw"), (HERE, "/ex", "ro"), (ms, "/o/c.ms", "ro")],
        "casa applycal probe",
    )
    c = cf.ms_columns(run / "probe.ms")
    s = (c["FIELD_ID"] == fid) & (c["ANTENNA1"] == 0) & (c["ANTENNA2"] == 1)
    data, corr, flag = c["DATA"][s], c["CORRECTED_DATA"][s], c["FLAG"][s]
    shutil.rmtree(run / "probe.ms")
    result = {}
    for r, k in ((0, 0), (1, 3)):
        good = ~f[0, :, r]
        sol = np.flatnonzero(good)
        raw = np.angle(p[0, good, r]).astype(np.float32)
        variants = {"casa-f32": unwrap_casa(raw), "f64-cast": unwrap_f64(raw)}
        counts = {v: 0 for v in variants}
        n = 0
        ulp_dev = {v: [] for v in variants}
        for j, sc in enumerate(sol):
            ch = 4 * sc
            ok = ~flag[:, ch, k]
            if not ok.any():
                continue
            g = data[ok, ch, k].astype(complex) / corr[ok, ch, k].astype(complex)
            implied = np.angle(np.mean(g / np.abs(g)))
            n += 1
            for v, u in variants.items():
                d = np.angle(np.exp(1j * (implied - float(u[j]))))
                ulp = float(np.spacing(np.float32(abs(u[j]))))
                ulp_dev[v].append(d / ulp)
                counts[v] += int(abs(d) < 0.25 * ulp)
        result[f"receptor {r}"] = {
            "channels": n,
            "within a quarter ulp": counts,
            "dev_in_ulps_max": {
                v: float(np.max(np.abs(x))) for v, x in ulp_dev.items()
            },
        }
    (run / "probe.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
