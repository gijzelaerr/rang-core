"""Build one Measurement Set from dask-ms zarr groups of the public stores, and
verify it cell for cell (research/e2-acceptance.md, part 2).

    python e2_convert.py build OUT.ms STORE:GROUP [STORE:GROUP ...] [--chan A:B] [--rows N]
    python e2_convert.py verify OUT.ms STORE:GROUP [...] [--chan A:B] [--rows N] --json OUT.json

STORE is a local copy of a store (the fetcher's output, e.g.
D:\\rang\\data\\e2-b\\LBAND_LUNO_CALIBRATORS.zarr), GROUP a MAIN group (MAIN_16).
`--chan` and `--rows` (first N rows of each group) are for development tests;
`--no-cubes` writes the row columns and subtables only, leaving DATA, FLAG and
WEIGHT_SPECTRUM at zero and unread (a preflight MS for `rang-core config check`
and the refant choice, allowed before the protocol: A0 section 4).

What it writes, through rang's table writer (`rang.core_ms_write`, the writer
A1's MS were made with and CASA reads):
- MAIN: DATA, FLAG, WEIGHT_SPECTRUM (tiled) and the row columns, the groups in
  order of their first TIME, each group's rows in stored order; FIELD_ID,
  SCAN_NUMBER and DATA_DESC_ID from each group's attributes (FIELD_ID and
  STATE_ID remapped to the merged tables), FLAG_ROW, WEIGHT, SIGMA as stored.
- Subtables ANTENNA, SPECTRAL_WINDOW, POLARIZATION, DATA_DESCRIPTION,
  OBSERVATION from the first store (the others must agree on ANTENNA positions
  and CHAN_FREQ); FIELD and STATE merged over the stores, rows the groups use;
  FEED: the stores hold one row (ANTENNA_ID 0, SPECTRAL_WINDOW_ID -1), which is
  expanded to one row per antenna with that row's values (CASA and rang look up
  a feed per antenna). Not written: POINTING, HISTORY, FLAG_CMD, SOURCE.
- Strings: json2 object arrays decoded as JSON; pickled ones (ESO137) only
  through `history/python/flagging_provenance.recognize_strings`, a bounded
  pickletools opcode walk that never reconstructs an object. Any other object
  codec is refused.

Cube cells are copied bit for bit (no arithmetic). `verify` re-reads every
written cell and compares bytes with the zarr; it prints counts only.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "python"))

from rang import core_ms, core_zarr
from rang import core_ms_write as tables

from history.python.flagging_provenance import recognize_strings

CUBES = {"DATA": ("<c8", 0j, "complex"), "WEIGHT_SPECTRUM": ("<f4", 0.0, "float"),
         "FLAG": ("|b1", False, None)}  # fmt: skip
ROWCOLS = ("TIME", "TIME_CENTROID", "INTERVAL", "EXPOSURE", "ANTENNA1", "ANTENNA2",
           "FEED1", "FEED2", "UVW", "FLAG_ROW", "WEIGHT", "SIGMA", "ARRAY_ID",
           "OBSERVATION_ID", "PROCESSOR_ID", "STATE_ID")  # fmt: skip
BATCH = 2000  # rows per write: 2000 x 4096 x 4 complex64 = 262 MB


def meta(d):
    return json.loads((Path(d) / ".zarray").read_text(encoding="utf-8"))


def read_array(d):
    """A whole zarr array (any chunking), numeric or string."""
    d = Path(d)
    m = meta(d)
    shape, chunks = m["shape"], m["chunks"]
    if 0 in shape:
        return np.zeros(shape, object if m["dtype"] == "|O" else m["dtype"])
    if m["dtype"] == "|O":
        ids = [f["id"] for f in m["filters"] or []]
        if any(s > c for s, c in zip(shape, chunks)):
            raise ValueError(f"{d}: multi-chunk string array")
        raw = core_zarr.read_chunk(d / ".".join("0" for _ in shape))
        if ids == ["json2"]:
            items = json.loads(raw.decode("utf-8"))
            return np.array(items[:-2], dtype=object).reshape(items[-1])
        if ids == ["pickle"]:
            got = recognize_strings(raw, tuple(shape))
            return np.array(got["strings"], dtype=object).reshape(got["shape"])
        raise ValueError(f"{d}: object codec {ids} refused")
    core_zarr.check_meta(m, str(d))
    out = np.empty(shape, m["dtype"])
    grid = [range(-(-s // c)) for s, c in zip(shape, chunks)]
    for idx in np.ndindex(*[len(g) for g in grid]):
        raw = core_zarr.read_chunk(d / ".".join(str(i) for i in idx))
        full = np.frombuffer(raw, m["dtype"]).reshape(chunks)
        sl = tuple(
            slice(i * c, min((i + 1) * c, s)) for i, c, s in zip(idx, chunks, shape)
        )
        out[sl] = full[tuple(slice(0, x.stop - x.start) for x in sl)]
    return out


def table_dict(store, name):
    d = Path(store) / name / f"{name}_0"
    return {
        c.name: read_array(c) for c in sorted(d.iterdir()) if (c / ".zarray").exists()
    }


class Group:
    def __init__(self, spec, rows=None):
        store, group = spec.rsplit(":", 1)
        self.store, self.name = Path(store), group
        self.dir = self.store / "MAIN" / group
        self.attrs = json.loads((self.dir / ".zattrs").read_text(encoding="utf-8"))
        self.nrow_all = meta(self.dir / "TIME")["shape"][0]
        self.nrow = self.nrow_all if rows is None else min(rows, self.nrow_all)
        self.time0 = float(read_array(self.dir / "TIME")[0])

    def rowcol(self, col):
        return read_array(self.dir / col)[: self.nrow]

    def cube(self, col, start, n, c0, c1):
        """Rows start:start+n, channels c0:c1 of a cube column, as stored."""
        d = self.dir / col
        m = meta(d)
        core_zarr.check_meta(m, str(d))
        rc, cc, ncorr = m["chunks"]
        dt = np.dtype(m["dtype"])
        out = np.empty((n, c1 - c0, ncorr), dt)
        for r0 in range((start // rc) * rc, start + n, rc):
            lo, hi = max(start, r0), min(start + n, r0 + rc, m["shape"][0])
            rows = np.arange(lo - r0, hi - r0)
            for j in range(c0 // cc, -(-c1 // cc)):
                key = d / f"{r0 // rc}.{j}.0"
                width = min(cc, m["shape"][1] - j * cc)
                buf, _ = core_zarr.read_rows(key, cc * ncorr * dt.itemsize, rows)
                block = np.frombuffer(buf, dt).reshape(len(rows), cc, ncorr)[:, :width]
                a, b = max(c0, j * cc), min(c1, j * cc + width)
                out[lo - start : hi - start, a - c0 : b - c0] = block[
                    :, a - j * cc : b - j * cc
                ]
        return out


def parse_chan(text, nchan):
    if not text:
        return 0, nchan
    a, b = (int(x) for x in text.split(":"))
    return a, b


def create(path, nrow, nchan):
    desc = [
        tables.makearrcoldesc("DATA", 0j, shape=[nchan, 4], valuetype="complex"),
        tables.makearrcoldesc(
            "WEIGHT_SPECTRUM", 0.0, shape=[nchan, 4], valuetype="float"
        ),
        tables.makearrcoldesc("FLAG", False, shape=[nchan, 4]),
        tables.makearrcoldesc("WEIGHT", 0.0, shape=[4], valuetype="float"),
        tables.makearrcoldesc("SIGMA", 0.0, shape=[4], valuetype="float"),
    ]
    per_tile = max(1, 32768 // (nchan * 4))
    dminfo = {
        f"*{i}": {"TYPE": "TiledColumnStMan", "NAME": f"Tiled{c}", "COLUMNS": [c],
                  "SPEC": {"DEFAULTTILESHAPE": [4, nchan, per_tile * k]}}
        for i, (c, k) in enumerate((("DATA", 1), ("WEIGHT_SPECTRUM", 1), ("FLAG", 8)), 1)
    }  # fmt: skip
    t = tables.default_ms(str(path), desc, dminfo)
    t.addrows(nrow)
    return t


def put_table(ms, name, cols, nrow, skip=("ROWID",)):
    with tables.table(str(Path(ms) / name), readonly=False) as t:
        if nrow:
            t.addrows(nrow)
        have = set(t.colnames())
        for col, v in cols.items():
            if col in skip or col not in have or nrow == 0:
                continue
            v = np.asarray(v)
            if v.dtype == object:
                v = v.astype(str)
            if v.ndim == 1:
                t.putcol(col, v)
            else:
                for i in range(nrow):
                    t.putcell(col, i, v[i])


def merged(groups):
    """FIELD and STATE rows the groups use, over the stores; per group the maps."""
    fields, states, fmap, smap = [], [], {}, {}
    for g in groups:
        f = table_dict(g.store, "FIELD")
        s = table_dict(g.store, "STATE")
        fid = int(g.attrs["FIELD_ID"])
        key = (str(f["NAME"][fid]), tuple(np.ravel(f["PHASE_DIR"][fid])))
        names = [(str(x["NAME"]), tuple(np.ravel(x["PHASE_DIR"]))) for x in fields]
        if key not in names:
            fields.append({k: v[fid] for k, v in f.items()})
            names.append(key)
        fmap[g.name, str(g.store)] = names.index(key)
        sm = {}
        for i in range(len(s["OBS_MODE"])):
            row = {k: v[i] for k, v in s.items()}
            modes = [str(x["OBS_MODE"]) for x in states]
            if str(row["OBS_MODE"]) not in modes:
                states.append(row)
                modes.append(str(row["OBS_MODE"]))
            sm[i] = modes.index(str(row["OBS_MODE"]))
        smap[g.name, str(g.store)] = sm
    stack = lambda rows: {k: np.array([r[k] for r in rows]) for k in rows[0]}
    return stack(fields), stack(states), fmap, smap


def build(a):
    started = time.time()
    groups = sorted((Group(s, a.rows) for s in a.groups), key=lambda g: g.time0)
    first = groups[0].store
    spw = table_dict(first, "SPECTRAL_WINDOW")
    ant = table_dict(first, "ANTENNA")
    for g in groups[1:]:
        o = table_dict(g.store, "ANTENNA")
        assert np.array_equal(o["POSITION"], ant["POSITION"]), "ANTENNA differs"
        assert list(o["NAME"]) == list(ant["NAME"]), "ANTENNA names differ"
        assert np.array_equal(
            table_dict(g.store, "SPECTRAL_WINDOW")["CHAN_FREQ"], spw["CHAN_FREQ"]
        )
    nchan_all = spw["CHAN_FREQ"].shape[1]
    c0, c1 = parse_chan(a.chan, nchan_all)
    nchan = c1 - c0
    nrow = sum(g.nrow for g in groups)
    out = Path(a.ms)
    if out.exists():
        raise SystemExit(f"{out} exists")
    t = create(out, nrow, nchan)
    fields, states, fmap, smap = merged(groups)
    record = {"groups": [], "nrow": nrow, "chan": [c0, c1], "no_cubes": a.no_cubes}
    start = 0
    for g in groups:
        n = g.nrow
        cols = {c: g.rowcol(c) for c in ROWCOLS if (g.dir / c / ".zarray").exists()}
        cols["STATE_ID"] = np.array([smap[g.name, str(g.store)].get(int(s), -1) for s in cols["STATE_ID"]], np.int32) if "STATE_ID" in cols else None  # fmt: skip
        for c, v in cols.items():
            if v is not None:
                t.putcol(c, v, startrow=start, nrow=n)
        t.putcol(
            "FIELD_ID",
            np.full(n, fmap[g.name, str(g.store)], np.int32),
            startrow=start,
            nrow=n,
        )
        t.putcol(
            "SCAN_NUMBER",
            np.full(n, int(g.attrs["SCAN_NUMBER"]), np.int32),
            startrow=start,
            nrow=n,
        )
        t.putcol(
            "DATA_DESC_ID",
            np.full(n, int(g.attrs["DATA_DESC_ID"]), np.int32),
            startrow=start,
            nrow=n,
        )
        for r in range(0, n if not a.no_cubes else 0, BATCH):
            k = min(BATCH, n - r)
            for c in CUBES:
                t.putcol(c, g.cube(c, r, k, c0, c1), startrow=start + r, nrow=k)
        record["groups"].append({"store": str(g.store), "group": g.name, "rows": n,
                                 "first_row": start, "attrs": {k: v for k, v in g.attrs.items() if not k.startswith("__")}})  # fmt: skip
        start += n
        print(f"{g.name}: {n} rows, {time.time() - started:.0f} s", flush=True)
    t.close()
    sw = dict(spw)
    for c in ("CHAN_FREQ", "CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"):
        sw[c] = spw[c][:, c0:c1]
    sw["NUM_CHAN"] = np.array([nchan], np.int32)
    sw["TOTAL_BANDWIDTH"] = np.array([float(np.sum(sw["CHAN_WIDTH"]))])
    put_table(out, "SPECTRAL_WINDOW", sw, 1)
    put_table(out, "ANTENNA", ant, len(ant["NAME"]))
    for name in ("POLARIZATION", "DATA_DESCRIPTION", "OBSERVATION"):
        d = table_dict(first, name)
        put_table(out, name, d, len(next(iter(d.values()))))
    put_table(out, "FIELD", fields, len(fields["NAME"]))
    put_table(out, "STATE", states, len(states["OBS_MODE"]))
    feed = table_dict(first, "FEED")
    assert len(feed["ANTENNA_ID"]) == 1, "FEED: one row expected"
    nant = len(ant["NAME"])
    rep = {k: np.repeat(v, nant, axis=0) for k, v in feed.items()}
    rep["ANTENNA_ID"] = np.arange(nant, dtype=np.int32)
    put_table(out, "FEED", rep, nant)
    record["fields"] = [str(x) for x in fields["NAME"]]
    record["antennas"] = nant
    record["seconds"] = time.time() - started
    (out.parent / f"{out.name}.convert.json").write_text(
        json.dumps(record, indent=1), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: record[k] for k in ("nrow", "chan", "fields", "antennas", "seconds")}
        )
    )


def verify(a):
    groups = sorted((Group(s, a.rows) for s in a.groups), key=lambda g: g.time0)
    ms = Path(a.ms)
    spw = table_dict(groups[0].store, "SPECTRAL_WINDOW")
    c0, c1 = parse_chan(a.chan, spw["CHAN_FREQ"].shape[1])
    res = {"cells_compared": {}, "cells_differ": {}, "rowcols_differ": {}}
    start = 0
    with core_ms.open_table(ms) as t:
        for g in groups:
            for c in ROWCOLS:
                if c == "STATE_ID" or not (g.dir / c / ".zarray").exists():
                    continue
                got = np.asarray(t.getcol(c, start, g.nrow))
                want = g.rowcol(c)
                same = got.tobytes() == want.astype(
                    got.dtype
                ).tobytes() and np.array_equal(got, want)
                res["rowcols_differ"][c] = res["rowcols_differ"].get(c, 0) + (
                    0 if same else 1
                )
            for r in range(0, g.nrow, BATCH):
                k = min(BATCH, g.nrow - r)
                for c in CUBES:
                    want = g.cube(c, r, k, c0, c1)
                    got = np.asarray(t.getcol(c, start + r, k))
                    if c == "DATA":
                        bad = int(
                            np.count_nonzero(
                                got.view(np.uint64) != want.view(np.uint64)
                            )
                        )
                    else:
                        bad = int(
                            np.count_nonzero(
                                got.view(np.uint8 if c == "FLAG" else np.uint32)
                                != want.view(np.uint8 if c == "FLAG" else np.uint32)
                            )
                        )
                    res["cells_compared"][c] = (
                        res["cells_compared"].get(c, 0) + want.size
                    )
                    res["cells_differ"][c] = res["cells_differ"].get(c, 0) + bad
            start += g.nrow
    res["equal"] = not any(res["cells_differ"].values()) and not any(
        res["rowcols_differ"].values()
    )
    Path(a.json).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res))
    return 0 if res["equal"] else 1


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("build", "verify"))
    p.add_argument("ms")
    p.add_argument("groups", nargs="+")
    p.add_argument("--chan", default="")
    p.add_argument("--rows", type=int, default=None)
    p.add_argument("--json", default=None)
    p.add_argument("--no-cubes", action="store_true",
                   help="metadata only: cube columns left at zero, never read (preflight)")  # fmt: skip
    a = p.parse_args(argv)
    if a.mode == "build":
        build(a)
        return 0
    return verify(a)


if __name__ == "__main__":
    sys.exit(main())
