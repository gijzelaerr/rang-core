# SPDX-License-Identifier: GPL-3.0-or-later
"""Write V8a's edge-case MS with rang's table writer (research/v8a-listobs.md,
amendment 1).

Usage: listobs_edges.py OUT.ms

6 baselines x 16 times, 8 s apart, 8 channels. Times 0-3: scan 1, field 0.
Times 4-7: scan 2, field 1 for times 4-5 then field 0 (a field change inside
a scan). Times 8-11: scan 3, field 2, state 0 then state 1 from time 10 (a
state change inside a scan). Times 12-15: scan 4, field 0, the two data
descriptions alternating by time (two spectral windows). FIELD has a fourth
row with no data. STATE has two rows; SOURCE is absent.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
from rang import core_ms_write

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "w1_writeback", ROOT / "examples/w1_writeback.py"
)
w1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w1)

FIELDS = (
    ("J1939-6342", 5.146179, -1.111986),
    ("3C286", 3.539258, 0.532485),
    ("GCAL", 5.2, -0.6),
    ("UNUSED", 1.0, 0.1),
)
ANTENNAS = (
    (5109271.49735416, 2006808.89302781, -3239130.73614072),
    (5109284.85407754, 2006824.22172353, -3239100.12646042),
    (5109272.19934272, 2006783.54604955, -3239145.33004218),
    (5109294.92858478, 2006755.50985424, -3239126.26625021),
)


def build(path):
    nbl, ntime, nchan = 6, 16, 8
    nrow = nbl * ntime
    ms = w1.make_ms(path, nrow, nchan)
    step = np.arange(nrow) // nbl
    field = np.select(
        [step <= 3, step <= 5, step <= 7, step <= 11], [0, 1, 0, 2], 0
    ).astype(np.int32)
    scan = (step // 4 + 1).astype(np.int32)
    state = ((step >= 10) & (step <= 11)).astype(np.int32)
    ddid = np.where(step >= 12, step % 2, 0).astype(np.int32)
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("FIELD_ID", field)
        t.putcol("SCAN_NUMBER", scan)
        t.putcol("STATE_ID", state)
        t.putcol("DATA_DESC_ID", ddid)
    with core_ms_write.open_table(ms / "FIELD", readonly=False) as t:
        t.addrows(len(FIELDS))
        t.putcol("NAME", [f[0] for f in FIELDS])
        t.putcol("CODE", ["T"] * len(FIELDS))
        for k, (_, ra, dec) in enumerate(FIELDS):
            for col in ("PHASE_DIR", "DELAY_DIR", "REFERENCE_DIR"):
                t.putcell(col, k, np.array([[ra, dec]]))
    with core_ms_write.open_table(ms / "ANTENNA", readonly=False) as t:
        t.addrows(len(ANTENNAS))
        t.putcol("NAME", [f"m00{a}" for a in range(len(ANTENNAS))])
        t.putcol("STATION", [f"m00{a}" for a in range(len(ANTENNAS))])
        t.putcol("TYPE", ["GROUND-BASED"] * len(ANTENNAS))
        t.putcol("MOUNT", ["ALT-AZ"] * len(ANTENNAS))
        t.putcol("DISH_DIAMETER", np.full(len(ANTENNAS), 13.5))
        for a, xyz in enumerate(ANTENNAS):
            t.putcell("POSITION", a, np.array(xyz))
            t.putcell("OFFSET", a, np.zeros(3))
    with core_ms_write.open_table(ms / "SPECTRAL_WINDOW", readonly=False) as t:
        t.addrows(1)
        freq = 1.5e9 + 104492.1875 * np.arange(nchan)
        t.putcell("CHAN_FREQ", 1, freq)
        for col in ("CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"):
            t.putcell(col, 1, np.full(nchan, 104492.1875))
        t.putcell("REF_FREQUENCY", 1, freq[0])
        t.putcell("NUM_CHAN", 1, np.int32(nchan))
        t.putcell("TOTAL_BANDWIDTH", 1, 104492.1875 * nchan)
        t.putcell("MEAS_FREQ_REF", 1, np.int32(5))
        t.putcell("NAME", 1, "upper")
        t.putcell("NET_SIDEBAND", 1, np.int32(1))
        t.putcell("FLAG_ROW", 1, False)
    with core_ms_write.open_table(ms / "DATA_DESCRIPTION", readonly=False) as t:
        t.addrows(1)
        t.putcell("SPECTRAL_WINDOW_ID", 1, np.int32(1))
        t.putcell("POLARIZATION_ID", 1, np.int32(0))
        t.putcell("FLAG_ROW", 1, False)
    with core_ms_write.open_table(ms / "STATE", readonly=False) as t:
        t.addrows(2)
        t.putcol("OBS_MODE", ["CALIBRATE_PHASE", "TARGET"])
        t.putcol("SUB_SCAN", np.zeros(2, np.int32))
        t.putcol("FLAG_ROW", np.zeros(2, bool))
    with core_ms_write.open_table(ms / "OBSERVATION", readonly=False) as t:
        t.addrows(1)
        t.putcol("TELESCOPE_NAME", ["MeerKAT"])
        t.putcol("OBSERVER", ["V8a edge cases"])
        t.putcol("PROJECT", ["v8a-listobs"])
        t.putcell("TIME_RANGE", 0, np.array([5.0e9 - 4, 5.0e9 + 8 * 15 + 4]))
    return ms


if __name__ == "__main__":
    build(sys.argv[1])
