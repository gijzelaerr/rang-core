"""Post hoc (after luno-score.json, 2026-11-11): rang's and CASA's Gpol on
LUNO scan 1, the phase difference per (interval, antenna, hand) with and
without its per-(interval, hand) median over antennas removed (the refant
gauge); per-interval medians; the refant's phase in each table. Reads the
two tables only.  python e2avg_gpol_gauge.py RUN"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import e2avg_common as C
import e2avg_luno as L


def main(run):
    run = Path(run)
    own, casa_ms = L.ms_paths(run)
    r = C.table(Path(str(own) + ".rang-run") / "calibrate" / "Gpol")
    c = C.table(casa_ms.parent / "Gpol")
    ka, kb = C.keyed(r), C.keyed(c)
    common = sorted(set(ka) & set(kb))
    ti = np.array([k[0] for k in common]); an = np.array([k[1] for k in common])
    pa = r.params[[ka[k] for k in common]][:, 0, :]
    pb = c.params[[kb[k] for k in common]][:, 0, :]
    fa = r.flags[[ka[k] for k in common]][:, 0, :]
    fb = c.flags[[kb[k] for k in common]][:, 0, :]
    ok = ~fa & ~fb
    d = np.angle(pa / np.where(pb == 0, 1, pb))
    g = d.copy()
    per_int = []
    for t in np.unique(ti):
        for h in range(d.shape[1]):
            m = (ti == t) & ok[:, h]
            if m.any():
                med = np.angle(np.median(np.exp(1j * d[m, h]).real) + 1j * np.median(np.exp(1j * d[m, h]).imag))
                g[ti == t, h] = np.angle(np.exp(1j * (d[ti == t, h] - med)))
                per_int.append([int(t), h, float(np.degrees(med)),
                                float(np.degrees(np.median(np.abs(g[m, h]))))])
    refa = {}
    for name, tab, p in (("rang", r, pa), ("casa", c, pb)):
        z = np.abs(np.angle(p)) < 1e-6
        refa[name] = {int(a): int(n) for a, n in zip(*np.unique(an[z.all(1)], return_counts=True))}
    out = {
        "raw_abs_deg": C.stats(np.degrees(np.abs(d[ok]))),
        "gauge_free_abs_deg": C.stats(np.degrees(np.abs(g[ok]))),
        "interval_offsets_deg": C.stats(np.abs([p[2] for p in per_int])),
        "per_interval": per_int,
        "zero_phase_antennas": refa,
        "n_intervals": int(len(np.unique(ti))),
    }
    C.write(run / "luno-gpol-gauge.json", out)
    print(json.dumps({k: v for k, v in out.items() if k != "per_interval"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
