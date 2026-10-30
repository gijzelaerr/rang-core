"""python-casacore side of the casacure evaluation (research/casacure-evaluation.md).

Runs in the `rang-ms-reader:local` image (python-casacore 3.8.1), with the
repository's `outputs` mounted at /outputs and `examples` at /examples:

    python /examples/eval_casacure_oracle.py describe <out.json> <ms> [<ms> ...]
    python /examples/eval_casacure_oracle.py bigendian <out-dir> <ms> [<ms> ...]
    python /examples/eval_casacure_oracle.py taql <out.json> <ms>
    python /examples/eval_casacure_oracle.py putflag <ms>
    python /examples/eval_casacure_oracle.py info <out.json> <table> [<table> ...]
    python /examples/eval_casacure_oracle.py measures <out.json> <cases.json>
    python /examples/eval_casacure_oracle.py perf <out.json> <ms>

`describe` writes column descriptions, data-manager info and keywords;
`bigendian` deep-copies each MS (with subtables) as a big-endian table;
`taql` runs the frozen selections; `putflag` writes the frozen FLAG pattern
into an existing table (interop criterion W3); `info` reports the table
type and subtype python-casacore sees; `measures` converts the frozen cases;
`perf` reads every column of the main table and every subtable once and
reports wall and peak RSS from inside the process.
"""

import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
from casacore.tables import table

SUBTABLES = ("ANTENNA", "FIELD", "SPECTRAL_WINDOW", "POLARIZATION")


def plain(value):
    """JSON-safe copy of a casacore record."""
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def describe_table(path):
    with table(str(path), readonly=True, ack=False) as t:
        cols = {}
        for name in t.colnames():
            cols[name] = {
                "desc": plain(t.getcoldesc(name)),
                "keywords": plain(t.getcolkeywords(name)),
            }
        return {
            "nrows": t.nrows(),
            "keywords": plain(t.getkeywords()),
            "dminfo": plain(t.getdminfo()),
            "info": plain(t.info()),
            "columns": cols,
        }


def describe(out, mss):
    result = {}
    for ms in mss:
        result[ms] = {"main": describe_table(ms)}
        for sub in SUBTABLES:
            result[ms][sub] = describe_table(Path(ms) / sub)
    Path(out).write_text(json.dumps(result, indent=1, default=str) + "\n")


def bigendian(out, mss):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    receipt = {}
    for index, ms in enumerate(mss):
        target = out / f"ms{index}-big.ms"
        with table(ms, readonly=True, ack=False) as t:
            copy = t.copy(str(target), deep=True, valuecopy=True, endian="big")
            copy.close()
        with table(str(target), readonly=True, ack=False) as t:
            receipt[str(target)] = {
                "source": ms,
                "endian": t.endianformat() if hasattr(t, "endianformat") else None,
                "dminfo": plain(t.getdminfo()),
            }
        for sub in SUBTABLES:
            with table(str(target / sub), readonly=True, ack=False) as s:
                receipt[str(target / sub)] = {
                    "endian": s.endianformat() if hasattr(s, "endianformat") else None
                }
    (out / "bigendian-receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")


def taql_queries(t):
    """The frozen selections of criterion R7 (also used by the casacure side)."""
    scan = int(t.getcol("SCAN_NUMBER", 0, 1)[0])
    times = t.getcol("TIME")
    unique = np.unique(times)
    t0, t1 = float(unique[0]), float(unique[min(2, len(unique) - 1)])
    # The five frozen selections, then two added after the first run
    # (post hoc, reported): the bare `SELECT FROM` form and a strict subset.
    return {
        "field1": "SELECT * FROM $t WHERE FIELD_ID == 1",
        "cross": "SELECT * FROM $t WHERE ANTENNA1 != ANTENNA2",
        "scan_sorted": (
            f"SELECT * FROM $t WHERE SCAN_NUMBER == {scan} "
            "ORDERBY TIME, ANTENNA1, ANTENNA2"
        ),
        "time_range": f"SELECT * FROM $t WHERE TIME BETWEEN {t0!r} AND {t1!r}",
        "unique_ant1": "SELECT UNIQUE ANTENNA1 FROM $t",
        "posthoc_bare_select": "SELECT FROM $t WHERE FIELD_ID == 1",
        "posthoc_ant1_desc": "SELECT * FROM $t WHERE ANTENNA1 == 1 ORDERBY DESC TIME",
    }


def taql(out, ms):
    from casacore.tables import taql as run

    result = {}
    with table(ms, readonly=True, ack=False) as t:
        for label, query in taql_queries(t).items():
            try:
                sel = run(query.replace("$t", "$1"), tables=[t])
                entry = {"query": query, "nrows": sel.nrows()}
                entry["rownumbers"] = np.asarray(sel.rownumbers(t)).tolist()
                cols = (
                    ["ANTENNA1"]
                    if label == "unique_ant1"
                    else ["TIME", "ANTENNA1", "ANTENNA2"]
                )
                for col in cols:
                    entry[col] = (
                        np.asarray(sel.getcol(col)).tolist() if sel.nrows() else []
                    )
                sel.close()
            except Exception as error:  # noqa: BLE001 - reported, not fatal
                entry = {"query": query, "error": f"{type(error).__name__}: {error}"}
            result[label] = entry
    Path(out).write_text(json.dumps(result, indent=1) + "\n")


def flag_pattern(shape):
    """The frozen FLAG pattern for the write criteria: every 7th cell set."""
    return (np.arange(int(np.prod(shape))) % 7 == 0).reshape(shape)


def putflag(ms):
    with table(ms, readonly=False, ack=False) as t:
        shape = t.getcol("FLAG").shape
        t.putcol("FLAG", ~flag_pattern(shape))
        t.flush()


def info(out, tables):
    result = {}
    for path in tables:
        try:
            with table(path, readonly=True, ack=False) as t:
                result[path] = {
                    "info": plain(t.info()),
                    "keywords": plain(t.getkeywords()),
                    "dminfo": plain(t.getdminfo()),
                    "nrows": t.nrows(),
                    "columns": {
                        c: plain(t.getcol(c))
                        if c not in ("CPARAM",)
                        else {
                            "real": t.getcol(c).real.tolist(),
                            "imag": t.getcol(c).imag.tolist(),
                        }
                        for c in t.colnames()
                    },
                }
        except Exception as error:  # noqa: BLE001 - reported
            result[path] = {"error": f"{type(error).__name__}: {error}"}
    Path(out).write_text(json.dumps(result, indent=1, default=str) + "\n")


def measures(out, cases_path):
    from casacore.measures import measures as make
    from casacore.quanta import quantity

    cases = json.loads(Path(cases_path).read_text())
    dm = make()
    result = []
    for case in cases:
        entry = dict(case)
        try:
            pos = dm.position("ITRF", *(quantity(v, "m") for v in case["itrf_m"]))
            epoch = dm.epoch("UTC", quantity(case["mjd_utc"], "d"))
            dm.do_frame(pos)
            dm.do_frame(epoch)
            src = dm.direction(
                "J2000",
                quantity(case["ra_rad"], "rad"),
                quantity(case["dec_rad"], "rad"),
            )
            for ref in ("AZEL", "AZELGEO"):
                azel = dm.measure(src, ref)
                entry[f"casacore_{ref}_az_deg"] = float(np.degrees(azel["m0"]["value"]))
                entry[f"casacore_{ref}_el_deg"] = float(np.degrees(azel["m1"]["value"]))
            zenith = dm.direction("AZEL", quantity(0, "deg"), quantity(90, "deg"))
            entry["casacore_parangle_deg"] = float(
                dm.posangle(src, zenith).get_value("deg")
            )
            zgeo = dm.direction("AZELGEO", quantity(0, "deg"), quantity(90, "deg"))
            entry["casacore_parangle_geo_deg"] = float(
                dm.posangle(src, zgeo).get_value("deg")
            )
            wgs = dm.measure(pos, "WGS84")
            entry["casacore_wgs84_lon_deg"] = float(np.degrees(wgs["m0"]["value"]))
            entry["casacore_wgs84_lat_deg"] = float(np.degrees(wgs["m1"]["value"]))
            entry["casacore_wgs84_h_m"] = float(wgs["m2"]["value"])
            for ref in ("TAI", "TT", "UT1"):
                entry[f"casacore_{ref}_mjd"] = float(
                    dm.measure(epoch, ref)["m0"]["value"]
                )
        except Exception as error:  # noqa: BLE001 - reported (measures data may be absent)
            entry["casacore_error"] = f"{type(error).__name__}: {error}"
        result.append(entry)
    Path(out).write_text(json.dumps(result, indent=1) + "\n")


def perf(out, ms):
    started = time.perf_counter()
    nbytes = 0
    for path in [Path(ms)] + sorted(
        p for p in Path(ms).iterdir() if (p / "table.dat").exists()
    ):
        with table(str(path), readonly=True, ack=False) as t:
            for name in t.colnames():
                try:
                    value = t.getcol(name)
                except RuntimeError:
                    continue
                nbytes += getattr(value, "nbytes", 0)
    wall = time.perf_counter() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    Path(out).write_text(
        json.dumps({"wall_s": wall, "peak_rss_mb": rss, "bytes": nbytes}) + "\n"
    )


def perf_data(out, ms):
    started = time.perf_counter()
    with table(ms, readonly=True, ack=False) as t:
        value = t.getcol("DATA")
    wall = time.perf_counter() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    Path(out).write_text(
        json.dumps({"wall_s": wall, "peak_rss_mb": rss, "bytes": value.nbytes}) + "\n"
    )


def main():
    command, args = sys.argv[1], sys.argv[2:]
    if command == "describe":
        describe(args[0], args[1:])
    elif command == "bigendian":
        bigendian(args[0], args[1:])
    elif command == "taql":
        taql(args[0], args[1])
    elif command == "putflag":
        putflag(args[0])
    elif command == "info":
        info(args[0], args[1:])
    elif command == "measures":
        measures(args[0], args[1])
    elif command == "perf":
        perf(args[0], args[1])
    elif command == "perf-data":
        perf_data(args[0], args[1])
    else:
        raise SystemExit(f"unknown command {command}")


if __name__ == "__main__":
    main()
