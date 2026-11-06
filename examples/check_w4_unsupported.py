"""W4 (research/w4-unsupported.md): build one small MS per case from A1's
small MS and run `rang-core config check`, `flag`, `calibrate`, `apply` and
`image` on each, against the expectations frozen in section 3 of the note
and the comparisons of section 4.

    python examples/check_w4_unsupported.py <run> [--gemclean PATH] [--strategy PATH]
        [--case ID ...] [--keep]

Writes `<run>/w4.json` and `<run>/<case>/` (the MS, its run directories,
configs and logs). The MS copies are removed at the end unless `--keep`.
The case builders also take W2's synthetic MS (tests/test_w4_unsupported.py).
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_ms, core_ms_write
from rang.formats import flagversions, quartical_store

A1_SMALL = Path("/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms")
STRATEGY = (
    Path.home()
    / "Github/rang/outputs/caracal-strategy-inputs-8f7bb363"
    / "mk_rfi_flagging_calibrator_fields_firstpass.yaml"
)
GEMCLEAN = Path.home() / "Github/rang/core/target/release/gemclean"
SEED = 20261106
FCAL, TARGET = "J1939-6342", "SIM-TARGET"
STAGES = ("flag", "calibrate", "apply", "image")
IMAGES = ("image-image", "image-model", "image-residual", "image-dirty")


# -- case builders (each edits an MS in place; `fresh` ones write a new one) ----


def _table(ms, sub=None):
    return core_ms_write.open_table(Path(ms) / sub if sub else ms, readonly=False)


def _getcol(ms, name, sub=None):
    with core_ms.open_table(Path(ms) / sub if sub else ms) as t:
        return t.getcol(name)


def _field_id(ms, name):
    return list(_getcol(ms, "NAME", "FIELD")).index(name)


def add_window(ms, nchan, used_by=None, same_spw=False):
    """A second SPECTRAL_WINDOW row of `nchan` channels above the first (or,
    with `same_spw`, none), and, when `used_by` is a FIELD name or "all", a
    second DATA_DESCRIPTION row (on the new window, or window 0) that those
    rows use."""
    if not same_spw:
        freq = _getcol(ms, "CHAN_FREQ", "SPECTRAL_WINDOW")[0]
        width = float(_getcol(ms, "CHAN_WIDTH", "SPECTRAL_WINDOW")[0][0])
        new = freq[-1] + width * (1 + np.arange(nchan))
        with _table(ms, "SPECTRAL_WINDOW") as t:
            t.addrows(1)
            t.putcell("CHAN_FREQ", 1, new)
            for col in ("CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"):
                t.putcell(col, 1, np.full(nchan, width))
            t.putcol("NUM_CHAN", np.array([len(freq), nchan], np.int32))
            t.putcell("REF_FREQUENCY", 1, float(new[nchan // 2]))
            t.putcell("TOTAL_BANDWIDTH", 1, width * nchan)
    if used_by is None:
        return
    with _table(ms, "DATA_DESCRIPTION") as t:
        t.addrows(1)
        t.putcol("SPECTRAL_WINDOW_ID", np.array([0, 0 if same_spw else 1], np.int32))
        t.putcol("POLARIZATION_ID", np.array([0, 0], np.int32))
    ddid = _getcol(ms, "DATA_DESC_ID")
    if used_by == "all":
        ddid[:] = 1
    else:
        ddid[_getcol(ms, "FIELD_ID") == _field_id(ms, used_by)] = 1
    with _table(ms) as t:
        t.putcol("DATA_DESC_ID", ddid.astype(np.int32))


def rename_field(ms, field_id, name):
    names = [str(n) for n in _getcol(ms, "NAME", "FIELD")]
    names[field_id] = name
    with _table(ms, "FIELD") as t:
        t.putcol("NAME", names)


def stray_field_id(ms, field, scan, new_id):
    """Rows of `field` (a name) in `scan` get FIELD_ID `new_id`."""
    fid = _getcol(ms, "FIELD_ID")
    pick = (fid == _field_id(ms, field)) & (_getcol(ms, "SCAN_NUMBER") == scan)
    fid[pick] = new_id
    with _table(ms) as t:
        t.putcol("FIELD_ID", fid.astype(np.int32))
    return int(pick.sum())


def add_empty_field(ms, name):
    """A FIELD row `name` (a copy of row 0's directions where they are
    defined) with no data rows."""
    cells = {}
    with core_ms.open_table(Path(ms) / "FIELD") as t:
        n = t.nrows
        for c in ("PHASE_DIR", "DELAY_DIR", "REFERENCE_DIR"):
            try:
                cells[c] = t.getcol(c, 0, 1)[0]
            except OSError:  # an undefined cell (W2's synthetic MS)
                pass
    with _table(ms, "FIELD") as t:
        t.addrows(1)
        names = list(t.getcol("NAME"))
        names[n] = name
        t.putcol("NAME", names)
        for c, v in cells.items():
            t.putcell(c, n, v)


def no_rows(src, dst):
    """A new MS at `dst` with `src`'s columns and subtables and no rows
    (tiled columns cannot remove rows, as in casacore)."""
    ncorr = len(_getcol(src, "CORR_TYPE", "POLARIZATION")[0])
    reshape_corr(src, dst, list(range(ncorr)), rows=[])


def flag_field(ms, name):
    flag = _getcol(ms, "FLAG")
    flag[_getcol(ms, "FIELD_ID") == _field_id(ms, name)] = True
    with _table(ms) as t:
        t.putcol("FLAG", flag)


def add_autos(ms, seed=SEED):
    """One autocorrelation row per antenna for every (TIME, FIELD_ID,
    SCAN_NUMBER, DATA_DESC_ID) of the MS, appended after the existing rows:
    XX and YY 15 + noise, XY and YX noise, FLAG false, UVW 0, the other
    columns copied from that integration's first row. Returns the old row
    count."""
    rng = np.random.default_rng(seed)
    with core_ms.open_table(ms) as t:
        nrow = t.nrows
        names = [n for n in dict(t.columns) if n != "FLAG_CATEGORY"]
        cols = {n: t.getcol(n) for n in names}
    with core_ms.open_table(Path(ms) / "ANTENNA") as t:
        nant = t.nrows
    keys = np.stack(
        [cols["TIME"], cols["FIELD_ID"], cols["SCAN_NUMBER"], cols["DATA_DESC_ID"]], 1
    )
    _, first = np.unique(keys, axis=0, return_index=True)
    first = np.sort(first)
    src = np.repeat(first, nant)
    ant = np.tile(np.arange(nant, dtype=np.int32), len(first))
    new = {n: np.array(v[src]) for n, v in cols.items()}
    new["ANTENNA1"] = new["ANTENNA2"] = ant
    new["UVW"] = np.zeros_like(new["UVW"])
    new["FLAG"] = np.zeros_like(new["FLAG"])
    new["FLAG_ROW"] = np.zeros_like(new["FLAG_ROW"])
    shape = new["DATA"].shape
    data = (rng.standard_normal(shape) + 1j * rng.standard_normal(shape)) * 0.1
    corr = _getcol(ms, "CORR_TYPE", "POLARIZATION")[0]
    for c, code in enumerate(corr):
        if code in (9, 12):
            data[..., c] = 15.0 + rng.standard_normal(shape[:2]) * 0.1
    new["DATA"] = data.astype(new["DATA"].dtype)
    with _table(ms) as t:
        t.addrows(len(src))
        for n, v in new.items():
            for start, k in flagversions.spans(len(src), 4096):
                t.putcol(n, v[start : start + k], nrow + start)
    return nrow


def remove_columns(ms, names):
    import casacure.tables as ct

    t = ct.table(str(ms), readonly=False, ack=False)
    t.removecols(list(names))
    t.flush()
    t.close()


def undefined_weight_spectrum(ms):
    """WEIGHT_SPECTRUM removed and declared again with no cells written."""
    import casacure.tables as ct

    remove_columns(ms, ["WEIGHT_SPECTRUM"]) if "WEIGHT_SPECTRUM" in _columns(
        ms
    ) else None
    t = ct.table(str(ms), readonly=False, ack=False)
    t.addcols(ct.makearrcoldesc("WEIGHT_SPECTRUM", 0.0, ndim=2, valuetype="float"))
    t.flush()
    t.close()


def _columns(ms):
    with core_ms.open_table(ms) as t:
        return set(dict(t.columns))


def relabel_corr(ms, codes):
    with _table(ms, "POLARIZATION") as t:
        t.putcell("CORR_TYPE", 0, np.array(codes, np.int32))


PRODUCTS = {9: [0, 0], 10: [0, 1], 11: [1, 0], 12: [1, 1]}


def reshape_corr(src, dst, keep, rows=None):
    """A new MS at `dst` with correlations `keep` (indices) of `src`'s: the
    main columns copied (correlation axes sliced; only `rows` when given), the
    subtables copied, and POLARIZATION rewritten."""
    src, dst = Path(src), Path(dst)
    with core_ms.open_table(src) as t:
        names = [n for n in dict(t.columns) if n != "FLAG_CATEGORY"]
        cols = {n: t.getcol(n) for n in names}
    if rows is not None:
        cols = {n: v[np.asarray(rows, int)] for n, v in cols.items()}
    nrow = len(cols["DATA"])
    nchan, k = cols["DATA"].shape[1], len(keep)
    desc = [
        core_ms_write.makearrcoldesc("DATA", 0j, shape=[nchan, k], valuetype="complex"),
        core_ms_write.makearrcoldesc("FLAG", False, shape=[nchan, k]),
        core_ms_write.makearrcoldesc("WEIGHT", 0.0, shape=[k], valuetype="float"),
        core_ms_write.makearrcoldesc("SIGMA", 0.0, shape=[k], valuetype="float"),
    ]
    if "WEIGHT_SPECTRUM" in cols:
        desc.append(
            core_ms_write.makearrcoldesc(
                "WEIGHT_SPECTRUM", 0.0, shape=[nchan, k], valuetype="float"
            )
        )
    tile = max(1, 32768 // (nchan * k))
    dminfo = {
        "*1": {
            "TYPE": "TiledColumnStMan",
            "NAME": "TiledData",
            "COLUMNS": ["DATA"],
            "SPEC": {"DEFAULTTILESHAPE": [k, nchan, tile]},
        }
    }
    with core_ms_write.default_ms(str(dst), desc, dminfo) as t:
        if nrow:
            t.addrows(nrow)
        have = set(t.colnames())
        for n, v in cols.items():
            if n not in have or not nrow:
                continue
            if n in ("DATA", "FLAG", "WEIGHT_SPECTRUM"):
                v = np.ascontiguousarray(v[:, :, keep])
            elif n in ("WEIGHT", "SIGMA"):
                v = np.ascontiguousarray(v[:, keep])
            for start, m in flagversions.spans(nrow, 2048):
                t.putcol(n, v[start : start + m], start)
            t.flush()
    for sub in sorted(p for p in src.iterdir() if (p / "table.dat").is_file()):
        if (dst / sub.name).is_dir():
            shutil.rmtree(dst / sub.name)
            shutil.copytree(sub, dst / sub.name)
    corr = _getcol(src, "CORR_TYPE", "POLARIZATION")[0][keep]
    with _table(dst, "POLARIZATION") as t:
        t.putcol("NUM_CORR", np.array([k], np.int32))
        t.putcell("CORR_TYPE", 0, np.asarray(corr, np.int32))
        t.putcell(
            "CORR_PRODUCT",
            0,
            np.array([PRODUCTS.get(int(c), [0, 0]) for c in corr], np.int32),
        )


# -- the cases (section 3) ----------------------------------------------------

W, R, F = "works", "refused", "fails"


def same(words):
    return {s: (R, words) for s in STAGES}


def _copy(src, dst):
    shutil.copytree(src, dst)


def case_list():
    """[(id, build(src, dst) -> notes, steps)]; a step is (command,
    variant, tag, (kind, words)); variant is a dict merged into the config,
    tag names the run directory."""

    def plain(edit=None):
        def build(src, dst):
            _copy(src, dst)
            return edit(dst) if edit else None

        return build

    def std(outcomes, extra=()):
        return [(s, {}, "run", outcomes.get(s, (W, ()))) for s in STAGES] + list(extra)

    def two(nchan, used_by, same_spw=False):
        return plain(lambda ms: add_window(ms, nchan, used_by, same_spw))

    many = ["2 data descriptions"]
    corr4 = ["four correlations"]
    out = [
        ("base", plain(), [("image", {}, "pristine", (W, ()))] + std({})),
        ("spw-unused", two(32, None), std({})),
        (
            "spw-two",
            two(64, TARGET),
            std(same([*many, "spectral windows [0, 1]", "split"])),
        ),
        ("spw-widths", two(32, TARGET), std(same(["differ in shape"]))),
        ("dd-same-spw", two(64, TARGET, same_spw=True), std(same(many))),
        (
            "dd-one",
            two(64, "all", same_spw=True),
            std(
                {"image": (R, ["DATA_DESC_ID 1", "gemclean images data description 0"])}
            ),
        ),
        (
            "field-dup",
            plain(lambda ms: rename_field(ms, 2, TARGET)),
            std(
                {"image": (R, [TARGET, "field ids [2, 3]", "give the field id"])},
                [("image", {"image": {"fields": [3]}}, "by-id", (W, ()))],
            ),
        ),
        (
            "field-norow",
            plain(lambda ms: stray_field_id(ms, TARGET, 20, 4)),
            std(same(["FIELD_ID 4", "no FIELD row"])),
        ),
        (
            "field-empty",
            plain(lambda ms: add_empty_field(ms, "EMPTY")),
            std(
                {},
                [
                    (
                        "image",
                        {"image": {"fields": ["EMPTY"]}},
                        "v-image",
                        (R, ["EMPTY", "no rows"]),
                    ),
                    (
                        "calibrate",
                        {"fields": {"fcal": ["EMPTY"]}},
                        "v-cal",
                        (R, ["EMPTY", "no rows"]),
                    ),
                    (
                        "flag",
                        {"flag": {"fields": ["EMPTY"]}},
                        "v-flag",
                        (R, ["EMPTY", "no rows"]),
                    ),
                ],
            ),
        ),
        (
            "field-unknown",
            plain(),
            [
                ("image", {"image": {"fields": ["NOPE"]}}, "v-name", (R, ["NOPE"])),
                ("image", {"image": {"fields": [9]}}, "v-id", (R, ["field id 9"])),
            ],
        ),
        (
            "scans-none",
            plain(),
            [
                (
                    "flag",
                    {"data": {"scans": [99]}},
                    "run",
                    (R, ["scans [99]", "no rows"]),
                ),
                (
                    "calibrate",
                    {"data": {"scans": [99]}},
                    "run",
                    (R, ["scans [99]", "no rows"]),
                ),
                (
                    "calibrate",
                    {
                        "data": {"scans": [99]},
                        "calibrate": {"model": {"source": "setjy"}},
                    },
                    "setjy",
                    (R, ["scans [99]", "no rows"]),
                ),
                (
                    "apply",
                    {"data": {"scans": [99]}},
                    "run",
                    (F, ["finished calibrate"]),
                ),
                (
                    "image",
                    {"data": {"scans": [99]}},
                    "run",
                    (R, ["data.scans", "no scan selection"]),
                ),
            ],
        ),
        (
            "scans-other",
            plain(),
            [
                ("flag", {"data": {"scans": [4]}}, "run", (W, ())),
                (
                    "calibrate",
                    {"data": {"scans": [4]}},
                    "run",
                    (R, [FCAL, "scans [4]", "no rows"]),
                ),
                ("apply", {"data": {"scans": [4]}}, "run", (F, ["finished calibrate"])),
                (
                    "image",
                    {"data": {"scans": [4]}},
                    "run",
                    (R, ["data.scans", "no scan selection"]),
                ),
            ],
        ),
        ("rows-zero", no_rows, std(same(["no rows"]))),
        (
            "field-flagged",
            plain(lambda ms: flag_field(ms, FCAL)),
            std(
                {
                    "calibrate": (F, ["no valid solution"]),
                    "apply": (F, ["finished calibrate"]),
                }
            ),
        ),
        ("autos", plain(add_autos), std({})),
        ("no-ws", plain(lambda ms: remove_columns(ms, ["WEIGHT_SPECTRUM"])), std({})),
        ("ws-undefined", plain(undefined_weight_spectrum), std({})),
        ("no-weight", plain(lambda ms: remove_columns(ms, ["WEIGHT"])), std({})),
        (
            "no-weights",
            plain(lambda ms: remove_columns(ms, ["WEIGHT", "WEIGHT_SPECTRUM"])),
            [
                ("flag", {}, "run", (W, ())),
                (
                    "calibrate",
                    {},
                    "run",
                    (R, ["WEIGHT_SPECTRUM or WEIGHT", "data.weights: uniform"]),
                ),
                ("calibrate", {"data": {"weights": "uniform"}}, "uniform", (W, ())),
                ("apply", {"data": {"weights": "uniform"}}, "uniform", (W, ())),
                ("image", {}, "run", (R, ["WEIGHT_SPECTRUM or WEIGHT", "gemclean"])),
            ],
        ),
        ("no-sigma", plain(lambda ms: remove_columns(ms, ["SIGMA"])), std({})),
        (
            "uniform-image",
            plain(),
            [
                (
                    "image",
                    {"data": {"weights": "uniform"}},
                    "run",
                    (R, ["data.weights", "task W4", "WEIGHT_SPECTRUM"]),
                )
            ],
        ),
        (
            "no-flag-row",
            plain(lambda ms: remove_columns(ms, ["FLAG_ROW"])),
            std(same(["FLAG_ROW", "required"])),
        ),
        (
            "no-flag",
            plain(lambda ms: remove_columns(ms, ["FLAG"])),
            std(same(["FLAG", "required"])),
        ),
        (
            "corr-2",
            lambda src, dst: reshape_corr(src, dst, [0, 3]),
            [("image", {}, "pristine", (W, ()))]
            + std(
                {"calibrate": (R, ["XX, YY", *corr4]), "apply": (R, ["XX, YY", *corr4])}
            )[:3],
        ),
        (
            "corr-circ",
            plain(lambda ms: relabel_corr(ms, [5, 6, 7, 8])),
            std(same(["circular", "linear"])),
        ),
        (
            "corr-circ-2",
            lambda src, dst: (
                reshape_corr(src, dst, [0, 3]),
                relabel_corr(dst, [5, 8]),
            ),
            std(same(["circular", "linear"])),
        ),
        (
            "corr-1",
            lambda src, dst: reshape_corr(src, dst, [0]),
            std(same(["one correlation"])),
        ),
        (
            "corr-order",
            plain(lambda ms: relabel_corr(ms, [9, 12, 10, 11])),
            std(same(["order", "XX, XY, YX, YY"])),
        ),
    ]
    return out


# -- running -------------------------------------------------------------------


def base_config(strategy, gemclean):
    return {
        "schema": "rang-config",
        "version": 1,
        "fields": {"fcal": [FCAL], "target": [TARGET]},
        "flag": {"strategy": str(strategy)},
        "calibrate": {
            "primary": {"terms": [{"type": "complex", "solint": "int", "freqint": 16}]}
        },
        "image": {
            "gemclean": str(gemclean),
            "size": [512, 512],
            "scale": "2asec",
            "niter": 2000,
            "threads": 1,
        },
    }


def merge(base, extra):
    out = json.loads(json.dumps(base))
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def fingerprint(ms):
    """SHA-256 of every column of MAIN, the flag versions and the columns."""
    out = {}
    with core_ms.open_table(ms) as t:
        nrow = t.nrows
        for name in sorted(dict(t.columns)):
            digest = hashlib.sha256()
            try:
                for start, n in flagversions.spans(nrow, 2048):
                    digest.update(
                        np.ascontiguousarray(t.getcol(name, start, n)).tobytes()
                    )
                out[name] = digest.hexdigest()
            except Exception as exc:  # noqa: BLE001 (undefined cells)
                out[name] = f"unreadable: {type(exc).__name__}"
    out["flag_versions"] = [v for v, _ in flagversions.versions(ms)]
    return out


def rang_core(python):
    return [
        python,
        "-c",
        "import sys; from rang.core_cli import main; sys.exit(main())",
    ]


def run_step(case_dir, ms, config, command, tag, python, hashed=True):
    """One command; with `hashed` the MS is fingerprinted before and after
    (only steps expected to be refused need it)."""
    path = case_dir / f"config-{command}-{tag}.yaml"
    import yaml

    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    run_dir = case_dir / f"run-{tag}"
    if command == "check":
        argv = ["config", "check", str(path), str(ms)]
        argv += [a for s in STAGES for a in ("--stage", s)]
    else:
        argv = [command, str(path), str(ms), "--run-dir", str(run_dir)]
    state_before = _state(run_dir)
    before = fingerprint(ms) if hashed and ms.exists() else None
    started = time.perf_counter()
    done = subprocess.run(
        ["nice", "-n", "10", *rang_core(python), *argv],
        capture_output=True,
        text=True,
        check=False,
    )
    seconds = time.perf_counter() - started
    after = fingerprint(ms) if hashed and ms.exists() else None
    log = case_dir / f"{command}-{tag}.log"
    log.write_text(done.stdout + done.stderr, encoding="utf-8")
    return {
        "command": command,
        "tag": tag,
        "argv": argv,
        "exit": done.returncode,
        "seconds": round(seconds, 2),
        "message": (done.stderr.strip().splitlines() or [""])[-12:],
        "unchanged": before == after,
        "state_unchanged": state_before == _state(run_dir),
        "changed_columns": sorted(
            k for k in (after or {}) if (before or {}).get(k) != after.get(k)
        ),
    }


def _state(run_dir):
    path = run_dir / "state.json"
    if not path.is_file():
        return None
    stages = json.loads(path.read_text(encoding="utf-8")).get("stages", {})
    return {k: (v.get("status"), v.get("started")) for k, v in stages.items()}


def verdict(record, kind, words):
    text = "\n".join(record["message"])
    code = {W: 0, F: 1, R: 2}[kind]
    ok = record["exit"] == code
    missing = [w for w in words if w not in text]
    ok &= not missing
    if kind == R:
        ok &= record["unchanged"] and record["state_unchanged"]
    record.update(
        expected=kind, words=list(words), missing_words=missing, passed=bool(ok)
    )
    return record


# -- comparisons (section 4) ----------------------------------------------------


def _flag(ms):
    return _getcol(ms, "FLAG")


def _store(run_dir):
    path = run_dir / "calibrate" / "complex.qc"
    return path if path.exists() else None


def compare_store(a, b, files=True):
    pa = sorted(quartical_store.read_term(a, "complex"), key=lambda p: p.name)
    pb = sorted(quartical_store.read_term(b, "complex"), key=lambda p: p.name)
    gains = len(pa) == len(pb) and all(
        np.array_equal(x["gains"], y["gains"])
        and np.array_equal(x["gain_flags"], y["gain_flags"])
        for x, y in zip(pa, pb)
    )
    out = {"partitions": [len(pa), len(pb)], "gains_and_flags_identical": bool(gains)}
    if files:
        fa = {p.relative_to(a): p for p in a.rglob("*") if p.is_file()}
        fb = {p.relative_to(b): p for p in b.rglob("*") if p.is_file()}
        out["files"] = [len(fa), len(fb)]
        out["files_identical"] = fa.keys() == fb.keys() and all(
            fa[k].read_bytes() == fb[k].read_bytes() for k in fa
        )
    return out


def compare_images(a, b):
    from astropy.io import fits

    out = {}
    for name in IMAGES:
        pa, pb = a / f"{name}.fits", b / f"{name}.fits"
        if pa.exists() or pb.exists():
            if not (pa.exists() and pb.exists()):
                out[name] = False
                continue
            out[name] = bool(np.array_equal(fits.getdata(pa), fits.getdata(pb)))
    return out


def port_flags(ms, strategy):
    """Criterion 5: `core_flag.flag_rows` per (field, ddid, scan) on arrays
    read with casacure, as W2 criterion 2."""
    import casacure.tables as ct
    from rang import core_flag

    strategies = core_flag.parse_strategy(Path(strategy).read_text(encoding="utf-8"))
    masks = [core_flag.load_static_mask(p) for p in core_flag.static_mask_files()]
    t = ct.table(str(ms), ack=False)
    c = {
        n: t.getcol(n)
        for n in (
            "DATA",
            "FLAG",
            "ANTENNA1",
            "ANTENNA2",
            "TIME",
            "FIELD_ID",
            "DATA_DESC_ID",
            "SCAN_NUMBER",
        )
    }
    t.close()
    sub = {}
    for name, cols in (
        ("ANTENNA", ["POSITION"]),
        ("SPECTRAL_WINDOW", ["CHAN_FREQ", "CHAN_WIDTH"]),
        ("POLARIZATION", ["CORR_TYPE"]),
    ):
        s = ct.table(str(Path(ms) / name), ack=False)
        for col in cols:
            sub[col] = s.getcol(col)
        s.close()
    out = c["FLAG"].copy()
    keys = np.stack([c["FIELD_ID"], c["DATA_DESC_ID"], c["SCAN_NUMBER"]], 1)
    _, inv = np.unique(keys, axis=0, return_inverse=True)
    for g in range(inv.max() + 1):
        idx = np.flatnonzero(inv.reshape(-1) == g)
        res = core_flag.flag_rows(
            c["DATA"][idx],
            c["FLAG"][idx],
            c["ANTENNA1"][idx],
            c["ANTENNA2"][idx],
            c["TIME"][idx],
            sub["POSITION"],
            sub["CHAN_FREQ"][0],
            sub["CHAN_WIDTH"][0],
            sub["CORR_TYPE"][0],
            strategies,
            masks=masks,
            want_intensity=False,
            want_stages=False,
        )
        out[idx] = res["flags"]
    return out


def comparisons(root, results, strategy):
    """Section 4 against the base case."""
    base = root / "base"
    if not (base / "a.ms").exists():
        return {"error": "the base case is missing"}
    bflag = _flag(base / "a.ms")
    bcorr = _getcol(base / "a.ms", "CORRECTED_DATA")
    bstore = _store(base / "run-run")
    out = {}
    equal_cases = (
        "spw-unused",
        "dd-one",
        "field-dup",
        "field-empty",
        "autos",
        "no-ws",
        "ws-undefined",
        "no-weight",
        "no-weights",
        "no-sigma",
    )
    for case in equal_cases:
        d = root / case
        ms = d / "a.ms"
        if not ms.exists():
            continue
        rec = {}
        n = len(bflag)
        flag = _flag(ms)
        rec["flag_equal_on_shared_rows"] = bool(np.array_equal(flag[:n], bflag))
        store = _store(d / "run-run") or _store(d / "run-uniform")
        if store is not None and case != "no-weights":
            rec["store"] = compare_store(store, bstore, files=case != "dd-one")
        cols = _columns(ms)
        if "CORRECTED_DATA" in cols and case != "no-weights":
            corr = _getcol(ms, "CORRECTED_DATA")
            rec["corrected_equal_on_shared_rows"] = bool(
                np.array_equal(corr[:n], bcorr)
            )
            if case == "autos":
                data = _getcol(ms, "DATA")[n:]
                fid = _getcol(ms, "FIELD_ID")[n:]
                cal = fid == 0
                rec["auto_rows"] = len(data)
                rec["auto_corrected_finite"] = bool(np.isfinite(corr[n:]).all())
                rec["auto_cal_rows_changed_fraction"] = float(
                    (corr[n:][cal] != data[cal]).any(axis=(1, 2)).mean()
                )
                rec["auto_other_rows_equal_data"] = bool(
                    np.array_equal(corr[n:][~cal], data[~cal])
                )
        img = d / "run-run" / "image" / TARGET
        if case == "field-dup":
            img = d / "run-by-id" / "image" / TARGET
        if img.is_dir():
            rec["image"] = compare_images(img, base / "run-run" / "image" / TARGET)
        out[case] = rec
    corr2 = root / "corr-2"
    if (corr2 / "a.ms").exists():
        rec = {}
        img = corr2 / "run-pristine" / "image" / TARGET
        if img.is_dir():
            rec["image_pristine"] = compare_images(
                img, base / "run-pristine" / "image" / TARGET
            )
        pristine = corr2 / "pristine.ms"
        if pristine.exists():
            rec["flag_equals_port"] = bool(
                np.array_equal(_flag(corr2 / "a.ms"), port_flags(pristine, strategy))
            )
        out["corr-2"] = rec
    scans = root / "scans-none" / "a.ms"
    if scans.exists():
        out["scans-none"] = {
            "model_data_absent": "MODEL_DATA" not in _columns(scans),
            "flag_versions": [v for v, _ in flagversions.versions(scans)],
        }
    return out


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("run")
    p.add_argument("--gemclean", default=str(GEMCLEAN))
    p.add_argument("--strategy", default=str(STRATEGY))
    p.add_argument("--source", default=str(A1_SMALL))
    p.add_argument("--case", action="append", default=[])
    p.add_argument("--keep", action="store_true")
    args = p.parse_args(argv)
    root = Path(args.run)
    root.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    gem = Path(args.gemclean)
    config0 = base_config(args.strategy, gem)
    results = {
        "source": args.source,
        "gemclean": str(gem),
        "gemclean_sha256": hashlib.sha256(gem.read_bytes()).hexdigest(),
        "strategy": args.strategy,
        "strategy_sha256": hashlib.sha256(Path(args.strategy).read_bytes()).hexdigest(),
        "commit": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[1],
            check=False,
        ).stdout.strip(),
        "dirty": bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                capture_output=True,
                text=True,
                cwd=Path(__file__).resolve().parents[1],
                check=False,
            ).stdout.strip()
        ),
        "cases": {},
    }
    started = time.perf_counter()
    for case, build, steps in case_list():
        if args.case and case not in args.case:
            continue
        d = root / case
        if d.exists():
            shutil.rmtree(d)
        d.mkdir()
        ms = d / "a.ms"
        t0 = time.perf_counter()
        try:
            notes = build(Path(args.source), ms)
            if case == "corr-2":
                reshape_corr(args.source, d / "pristine.ms", [0, 3])
        except Exception as exc:  # noqa: BLE001 (recorded, not hidden)
            results["cases"][case] = {"build_error": f"{type(exc).__name__}: {exc}"}
            continue
        rec = {
            "build_seconds": round(time.perf_counter() - t0, 2),
            "notes": notes,
            "steps": [],
        }
        # config check of the base variant: refused iff a base-variant stage is.
        base_steps = [s for s in steps if not s[1] and s[2] in ("run",)]
        refused = [s for s in base_steps if s[3][0] == R]
        words = sorted({w for s in refused for w in s[3][1]})
        if base_steps:
            r = run_step(d, ms, config0, "check", "check", python, hashed=bool(refused))
            rec["steps"].append(verdict(r, R if refused else W, words))
        for command, variant, tag, (kind, ws) in steps:
            config = merge(config0, variant)
            r = run_step(d, ms, config, command, tag, python, hashed=kind == R)
            rec["steps"].append(verdict(r, kind, ws))
        rec["passed"] = all(s["passed"] for s in rec["steps"])
        results["cases"][case] = rec
        print(
            f"{case}: {'pass' if rec['passed'] else 'FAIL'} "
            + " ".join(f"{s['command']}[{s['tag']}]={s['exit']}" for s in rec["steps"]),
            flush=True,
        )
    results["comparisons"] = comparisons(root, results, args.strategy)
    results["seconds"] = round(time.perf_counter() - started, 1)
    (root / "w4.json").write_text(
        json.dumps(results, indent=1, default=str) + "\n", encoding="utf-8"
    )
    if not args.keep:
        for ms in root.glob("*/*.ms"):
            shutil.rmtree(ms)
            fv = ms.with_name(ms.name + ".flagversions")
            if fv.exists():
                shutil.rmtree(fv)
    print(json.dumps(results["comparisons"], indent=1, default=str))
    return results


if __name__ == "__main__":
    main()
