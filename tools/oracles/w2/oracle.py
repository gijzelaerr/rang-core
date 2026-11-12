# SPDX-License-Identifier: GPL-3.0-or-later
"""W2 oracles (research/w2-commands.md, criteria 2 and 3).

    python oracle.py seed MS SEED            # seed FLAG (10 %) and FLAG_ROW (5 %) with casacure
    python oracle.py flag MS STRATEGY OUT.npz
    python oracle.py calibrate MS FIELD SOLINT FREQINT OUT_STORE
    python oracle.py hashes MS OUT.json      # SHA-256 of every column, casacure

The MS is read with casacure (python-casacore's API; not rang's reader).
`flag` makes the call `examples/run_core_flags.py` makes, per (FIELD_ID,
DATA_DESC_ID, SCAN_NUMBER) group in row order: `core_flag.flag_rows` with
the strategy parsed by `parse_strategy` and the two static masks loaded by
`load_static_mask`; FLAG becomes the result in the group's rows (Tricolour
writes the window flags). `calibrate` solves the `complex` term with
`core.solve_complex` per field and scan, rows sorted stably by TIME, on the
QuartiCal-style grid, and writes the gains with `quartical_store`.
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from casacure.tables import table
from rang import core, core_flag
from rang.formats import quartical_store


def read(ms, names):
    with table(str(ms), readonly=True, ack=False) as t:
        return {n: np.ascontiguousarray(t.getcol(n)) for n in names}


def sub(ms, name, col):
    with table(f"{ms}/{name}", readonly=True, ack=False) as t:
        return t.getcol(col)


def groups(cols, rows):
    keys = {}
    for r in rows:
        key = (
            int(cols["FIELD_ID"][r]),
            int(cols["DATA_DESC_ID"][r]),
            int(cols["SCAN_NUMBER"][r]),
        )
        keys.setdefault(key, []).append(r)
    return {k: np.asarray(v) for k, v in sorted(keys.items())}


def seed(ms, value):
    rng = np.random.default_rng(int(value))
    with table(str(ms), readonly=False, ack=False) as t:
        flag = t.getcol("FLAG")
        t.putcol("FLAG", rng.random(flag.shape) < 0.10)
        t.putcol("FLAG_ROW", rng.random(flag.shape[0]) < 0.05)
    return {"seed": int(value)}


def flag(ms, strategy_path, out):
    names = ["DATA", "FLAG", "ANTENNA1", "ANTENNA2", "TIME", "FIELD_ID"]
    cols = read(ms, [*names, "DATA_DESC_ID", "SCAN_NUMBER"])
    position = sub(ms, "ANTENNA", "POSITION")
    chan_freq = sub(ms, "SPECTRAL_WINDOW", "CHAN_FREQ")[0]
    chan_width = sub(ms, "SPECTRAL_WINDOW", "CHAN_WIDTH")[0]
    corr_type = sub(ms, "POLARIZATION", "CORR_TYPE")[0]
    strategies = core_flag.parse_strategy(
        Path(strategy_path).read_text(encoding="utf-8")
    )
    masks = [core_flag.load_static_mask(p) for p in core_flag.static_mask_files()]
    final = cols["FLAG"].copy()
    for _, idx in groups(cols, range(len(cols["TIME"]))).items():
        result = core_flag.flag_rows(
            cols["DATA"][idx],
            cols["FLAG"][idx],
            cols["ANTENNA1"][idx],
            cols["ANTENNA2"][idx],
            cols["TIME"][idx],
            position,
            chan_freq,
            chan_width,
            corr_type,
            strategies,
            masks=masks,
        )
        final[idx] = result["flags"]
    np.savez(out, FLAG=final, INPUT_FLAG=cols["FLAG"])
    return {
        "flagged_before": float(cols["FLAG"].mean()),
        "flagged_after": float(final.mean()),
    }


def bins(times, nchan, freqs, solint, freqint):
    unique, inverse = np.unique(times, return_inverse=True)
    st = len(unique) if solint == "inf" else (1 if solint == "int" else int(solint))
    sf = nchan if freqint == "inf" else int(freqint)
    tb = (inverse.reshape(-1) // st).astype(np.uint32)
    fb = (np.arange(nchan) // sf).astype(np.uint32)
    gt = np.array([np.mean(unique[i : i + st]) for i in range(0, len(unique), st)])
    gf = np.array([np.mean(freqs[i : i + sf]) for i in range(0, nchan, sf)])
    return tb, fb, gt, gf


def calibrate(ms, field_name, solint, freqint, out):
    names = ["DATA", "FLAG", "FLAG_ROW", "ANTENNA1", "ANTENNA2", "TIME", "FIELD_ID"]
    cols = read(ms, [*names, "DATA_DESC_ID", "SCAN_NUMBER", "WEIGHT_SPECTRUM"])
    fields = list(sub(ms, "FIELD", "NAME"))
    antennas = [str(a) for a in sub(ms, "ANTENNA", "NAME")]
    freqs = sub(ms, "SPECTRAL_WINDOW", "CHAN_FREQ")[0]
    fid = fields.index(field_name)
    rows = np.flatnonzero(cols["FIELD_ID"] == fid)
    parts, record = [], []
    nchan = cols["DATA"].shape[1]
    for (field, ddid, scan), idx in groups(cols, rows).items():
        order = idx[np.argsort(cols["TIME"][idx], kind="stable")]
        tb, fb, gt, gf = bins(cols["TIME"][order], nchan, freqs, solint, freqint)
        s = core.solve_complex(
            cols["DATA"][order],
            cols["WEIGHT_SPECTRUM"][order],
            cols["FLAG"][order],
            cols["FLAG_ROW"][order],
            cols["ANTENNA1"][order],
            cols["ANTENNA2"][order],
            tb,
            fb,
            ntime_bins=len(gt),
            nfreq_bins=len(gf),
            nant=len(antennas),
            scalar_model=np.ones(nchan, np.float64),
            max_iterations=50,
            stop_criterion=1e-7,
            stop_fraction=0.99,
        )
        parts.append(
            quartical_store.complex_partition(
                s.gains[:, :, :, None],
                s.flags[:, :, :, None],
                gt,
                gf,
                antennas,
                name="complex",
                field_id=field,
                field_name=fields[field],
                scan=scan,
                ddid=ddid,
            )
        )
        record.append(
            {
                "scan": scan,
                "gains_sha256": hashlib.sha256(
                    np.ascontiguousarray(s.gains).tobytes()
                ).hexdigest(),
                "iterations": s.iterations,
            }
        )
    quartical_store.write({"complex": parts}, out)
    return {"partitions": record}


def hashes(ms, out):
    result = {}
    with table(str(ms), readonly=True, ack=False) as t:
        for name in t.colnames():
            try:
                values = t.getcol(name)
            except RuntimeError as exc:
                result[name] = f"unreadable: {exc}"
                continue
            result[name] = hashlib.sha256(
                np.ascontiguousarray(values).tobytes()
            ).hexdigest()
    Path(out).write_text(
        json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"columns": len(result)}


def main(argv):
    action, *args = argv
    out = {"seed": seed, "flag": flag, "calibrate": calibrate, "hashes": hashes}[
        action
    ](*args)
    print(json.dumps({action: out}))


if __name__ == "__main__":
    main(sys.argv[1:])
