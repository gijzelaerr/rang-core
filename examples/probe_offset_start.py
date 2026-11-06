"""Task C2c (research/c2c-bandpass.md), post hoc after run -03: why does
`delay_and_offset` land 1.67 ns off on a few field-2 intervals of the
delay50 twin (the first sidelobe of a uniform 856 MHz band's delay response,
1.43 / 856 MHz)? Hypothesis, written before this probe ran: the FFT
estimate is on the main lobe, and Gauss-Newton started from a zero offset
walks to the sidelobe when the true offset is large; starting the offset at
the phase of the FFT peak keeps it on the main lobe.

    python examples/probe_offset_start.py <run>
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_bandpass as cb
import check_gain as cg
from rang import cal_delay, cal_gain


def fft_estimate(data, flag, a1, a2, tb, refant, nchan, delta):
    """numpy transcription of `Delay.init_term` per interval: delays (s) and
    the phase of the FFT peak for antennas on baselines to the refant."""
    n = int(np.ceil(2**15 / nchan)) * nchan
    out = {}
    for t in np.unique(tb):
        sel = (tb == t) & ((a1 == refant) | (a2 == refant)) & (a1 != a2)
        for row in np.flatnonzero(sel):
            ant = a2[row] if a1[row] == refant else a1[row]
            out.setdefault((t, ant), []).append(row)
    est = {}
    freq = np.fft.fftshift(np.fft.fftfreq(n, delta))
    for (t, ant), rows in out.items():
        d = np.where(flag[rows][..., None], 0, data[rows]).mean(0)
        for h, c in ((0, 0), (1, 3)):
            spec = np.fft.fftshift(np.fft.fft(d[:, c], n))
            k = int(np.argmax(np.abs(spec)))
            sign = -1 if a1[rows[0]] == refant else 1
            est[(int(t), int(ant), h)] = (sign * freq[k], float(np.angle(spec[k])))
    return est


def main(argv):
    run = Path(argv[1])
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    p = cb.paths(argv)
    ms, truth, _, _, btab, _ = cb.sources(p)["d50twin"]
    tr = dict(np.load(truth))
    dtrue = tr["raw_tau_ns"] - tr["raw_tau_ns"][0][None]
    cdata, cmodel, _, flag = cb.prepared(ms, truth, None, [btab], [2], "K")
    c = cg.columns(ms, ["FIELD_ID", "TIME", "SCAN_NUMBER", "ANTENNA1", "ANTENNA2",
                        "WEIGHT_SPECTRUM", "FLAG_ROW"])  # fmt: skip
    rows = np.flatnonzero(c["FIELD_ID"] == 2)
    freq = cg.chan_freq(ms)
    tb, _ = cal_gain.solint_bins(
        c["TIME"][rows], c["SCAN_NUMBER"][rows], c["FIELD_ID"][rows], "int"
    )
    a1, a2 = c["ANTENNA1"][rows], c["ANTENNA2"][rows]
    est = fft_estimate(cdata[rows], flag[rows].any(-1), a1, a2, tb, 0, freq.size,
                       freq[1] - freq[0])  # fmt: skip
    sol = cal_delay.solve(
        cdata[rows], cmodel[rows], c["WEIGHT_SPECTRUM"][rows], flag[rows],
        c["FLAG_ROW"][rows], a1, a2, tb, nant=16, chan_freq=freq, refant=0,
        **cb.TWIN,
    )  # fmt: skip
    out = {"bad": []}
    err = sol.delays[:, 0] - dtrue[None]
    for t, a, h in np.argwhere(np.abs(err) > 0.01):
        e_tau, _phase = est.get((int(t), int(a), int(h)), (np.nan, np.nan))
        out["bad"].append({
            "interval": int(t), "antenna": int(a), "hand": int(h),
            "solved_error_ns": float(err[t, a, h]),
            "fft_estimate_error_ns": float(e_tau * 1e9 - dtrue[a, h]),
            "solved_offset_deg": float(np.degrees(sol.offsets[t, 0, a, h])),
        })  # fmt: skip
    est_err = np.array([v[0] * 1e9 - dtrue[a, h] for (t, a, h), v in est.items()])
    out["fft_estimate_abs_error_ns"] = {"median": float(np.median(np.abs(est_err))),
                                        "max": float(np.abs(est_err).max())}  # fmt: skip
    out["seconds"] = time.perf_counter() - started
    cg.write(run / "probe.json", out)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
