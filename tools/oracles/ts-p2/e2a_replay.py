# SPDX-License-Identifier: MIT
"""TS-P2 real track (research/ts-p2.md 4.2, steps 2-4): E2-A's chain replayed
on this task's own copy of `e2a.ms` from E2-A's archived products, so that
CORRECTED_DATA is E2-A's final self-calibrated data again.

    python tools/oracles/ts-p2/e2a_replay.py MS RANG_RUN OUT_JSON

MS is the copy (`e2a-replay.ms`, with its `.flagversions`); RANG_RUN is
E2-A's run directory (`D:/rang/outputs/e2a-20261115/rang-run`), only read.
Steps, each recorded in OUT_JSON with its check:

2. restore FLAG to `rang_selfcal_20261115T161755Z`; count flagged cells in
   the MS (10,747,830,624 expected) and in ESO137-001 (7,843,952,228);
3. apply K1, G1, B1 as E2-A's apply stage (`rang.applycal.applycal`, the
   configuration's interp and gainfield) into CORRECTED_DATA;
4. self-calibration round 2's store (Sa, solint 120) applied in place with
   `rang.cal_selfcal.apply`, its rows and bins rebuilt by
   `cal_selfcal.time_bins` (bin times must equal the store's exactly);
   ESO137-001's flagged cells then 8,082,693,644 (E2-A's round 1 added no
   flag, so round 1 is only read and recorded).
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from rang import applycal, cal_selfcal, core_ms, core_writeback

VERSION = "rang_selfcal_20261115T161755Z"
EXPECT_MS, EXPECT_FIELD, EXPECT_AFTER = 10_747_830_624, 7_843_952_228, 8_082_693_644
FIELD = 1  # ESO137-001
CHUNK = 20_000


def flag_counts(ms):
    total = field = 0
    with core_ms.open_table(ms) as t:
        for start in range(0, t.nrows, CHUNK):
            n = min(CHUNK, t.nrows - start)
            f = np.asarray(t.getcol("FLAG", start, n), bool)
            per_row = f.reshape(n, -1).sum(axis=1)
            total += int(per_row.sum())
            field += int(per_row[t.getcol("FIELD_ID", start, n) == FIELD].sum())
    return total, field


def solution(ms, store, name, rows, times, scans, nchan):
    gains, flags, gain_time, gain_freq, bin_scan = cal_selfcal.read_store(store, name)
    # read_store gives flags per (time, freq, antenna); the solution keeps
    # them per hand.
    flags = np.repeat(np.asarray(flags, bool)[..., None], gains.shape[-1], -1)
    tb, b_scan, g_time = cal_selfcal.time_bins(times, scans, FIELD, 120)
    same = bool(np.array_equal(g_time, gain_time)) and bool(
        np.array_equal(b_scan, bin_scan)
    )
    sol = cal_selfcal.SelfcalSolution(
        name=name,
        type=name,
        gains=gains,
        flags=flags,
        rows=rows,
        time_bin=tb,
        freq_bin=np.zeros(nchan, np.int64),
        bin_scan=b_scan,
        gain_time=g_time,
        gain_freq=gain_freq,
        field_id=FIELD,
        iterations=0,
        converged_fraction=1.0,
        clipped=0,
    )
    return sol, {
        "store": str(store),
        "bins": len(g_time),
        "gain_time_equal": same,
        "max_gain_time_diff_s": float(np.max(np.abs(g_time - gain_time)))
        if len(g_time) == len(gain_time)
        else None,
        "invalid_antenna_bins": int((~sol.valid()).sum()),
    }


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    selfcal_only = "--selfcal-only" in argv  # resume at step 4 (steps 2-3 done)
    argv = [x for x in argv if x != "--selfcal-only"]
    ms, run, out = (Path(a) for a in argv)
    rec = {"ms": str(ms), "rang_run": str(run), "steps": {}}
    if selfcal_only:
        return selfcal_step(ms, run, out, rec)
    t0 = time.perf_counter()
    core_writeback.restore_flags(ms, VERSION)
    total, field = flag_counts(ms)
    rec["steps"]["2_restore"] = {
        "version": VERSION,
        "flagged_ms": total,
        "flagged_field": field,
        "check": total == EXPECT_MS and field == EXPECT_FIELD,
        "seconds": time.perf_counter() - t0,
    }
    print(json.dumps(rec["steps"]["2_restore"]), flush=True)
    if not rec["steps"]["2_restore"]["check"]:
        out.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
        raise SystemExit("step 2 check failed")
    t0 = time.perf_counter()
    cal = run / "calibrate"
    with core_writeback.WriteBack(
        ms, flag_backup="tsp2_replay_apply", stage="tsp2-replay-apply"
    ) as w:
        applied = applycal.applycal(
            ms,
            [str(cal / n) for n in ("K1", "G1", "B1")],
            interp=["linear", "linear", "linear"],
            gainfield=["nearest", "nearest", "J1939-6342"],
            calwt=[False],
            applymode="calflag",
            column="CORRECTED_DATA",
            session=w,
            scan=[9, 10, 11],
        )
    rec["steps"]["3_apply"] = {
        "cells_flagged_before": applied.get("cells_flagged_before"),
        "cells_flagged_after": applied.get("cells_flagged_after"),
        "check": applied.get("cells_flagged_after") == EXPECT_MS,
        "seconds": time.perf_counter() - t0,
    }
    print(json.dumps(rec["steps"]["3_apply"]), flush=True)
    return selfcal_step(ms, run, out, rec)


def selfcal_step(ms, run, out, rec):
    t0 = time.perf_counter()
    journal = core_writeback.read_journal(ms)
    if core_writeback.flags_unfinished(journal):
        # A failed earlier attempt of this step (it raised before any write):
        # back to the flags saved before it.
        core_writeback.restore_flags(ms, journal["flag_backup"])
        rec["restored_from"] = journal["flag_backup"]
    with core_ms.open_table(ms) as t:
        fid = t.getcol("FIELD_ID")
        rows = np.flatnonzero(fid == FIELD)
        times = t.getcol("TIME")[rows]
        scans = t.getcol("SCAN_NUMBER")[rows]
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as sw:
        nchan = len(sw.getcol("CHAN_FREQ", 0, 1)[0])
    base = run / "selfcal" / "ESO137-001"
    _, info1 = solution(ms, base / "round-1/gains.qc", "Sp", rows, times, scans, nchan)
    sol2, info2 = solution(
        ms, base / "round-2/gains.qc", "Sa", rows, times, scans, nchan
    )
    with core_writeback.WriteBack(
        ms, flag_backup="tsp2_replay_selfcal", stage="tsp2-replay-selfcal"
    ) as w:
        done = cal_selfcal.apply(
            w, sol2, input_column="CORRECTED_DATA", output_column="CORRECTED_DATA"
        )
    total, field = flag_counts(ms)
    rec["steps"]["4_selfcal"] = {
        "round1": info1,
        "round2": info2,
        "apply": done,
        "flagged_field": field,
        "flagged_ms": total,
        "check": bool(
            info1["gain_time_equal"]
            and info2["gain_time_equal"]
            and field == EXPECT_AFTER
        ),
        "seconds": time.perf_counter() - t0,
    }
    print(json.dumps(rec["steps"]["4_selfcal"]), flush=True)
    out.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    return 0 if all(s["check"] for s in rec["steps"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
