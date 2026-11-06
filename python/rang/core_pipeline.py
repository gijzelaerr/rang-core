"""The stages of `rang-core flag | calibrate | apply | image | selfcal | run`
on a user's Measurement Set (task W2, research/w2-commands.md).

    from rang import core_config, core_pipeline
    config = core_config.validate_file("config.yaml", ["flag", "calibrate"])
    core_pipeline.execute(config, "config.yaml", "my.ms", ["flag", "calibrate"])

A run directory (default `<ms>.rang-run` beside the MS) holds `state.json`:
for each stage its status (`running`, `done`, `failed`, `stale`), the hash of
the configuration sections it depends on (`core_config.stage_hash`), times,
the flag version saved before it wrote, a summary and any error. `execute`
skips a finished stage whose hash is unchanged, refuses one whose
configuration changed unless it is forced, and runs a failed, interrupted or
stale one again. A stage that finishes marks every later finished stage
stale. The directory is bound to one MS and locked (fcntl, POSIX only) while
a command runs.

Flag backups: before the first write ever made to the MS, its flags are
saved as the CASA flag version `rang_original`; before each writing stage
writes, its flags are saved again as `rang_<stage>_<UTC time>`
(`core_writeback.WriteBack`). A stage that ran before and is run again (it
failed, was killed, or is forced) first gets the flags back from the version
its last attempt saved, so its input is the same each time.

What runs: `flag` (the Tricolour port, per field, data description and scan,
as Tricolour groups rows), `calibrate` (calibrator models into MODEL_DATA
through `rang.calmodels` when `model.source` is setjy, manual or lsm; then
either the `complex` term, `core.solve_complex`, one solve per field and
scan, written as a QuartiCal gain store, or CARACal's K, G, B, A and F terms
in C1's order through `rang.cal_chain.run`, written as CASA tables, with
the A steps writing CORRECTED_DATA and FLAG of the calibrators; task C2e,
research/c2e-calibrate.md), `apply` (the complex terms on their own
solution bins, `rang.applycal.apply_complex`, or the CASA tables through
`rang.applycal.applycal`, into CORRECTED_DATA with FLAG OR'd; tasks W2b and
C2e) and `image` (`gemclean` on a data column). `selfcal` is refused by
`core_config.refusals` (C5 and G6).

Data a stage cannot run on (task W4, research/w4-unsupported.md) is refused
by `check_data` and `preflight` before anything is written, every problem at
once: several data descriptions in use, circular or single correlations, two
correlations for calibrate and apply, missing FLAG or FLAG_ROW, missing
weights, FIELD_IDs without a FIELD row, empty selections, ambiguous image
fields, and image when `data.scans` leaves out a scan of an imaged field or
on a data description other than 0.
Autocorrelations are flagged and corrected but left out of the solve.
"""

import datetime as _dt
import hashlib
import json
import os
import shutil
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from . import cal_chain, core, core_config, core_flag, core_ms, core_writeback
from .formats import flagversions, quartical_store

STATE_SCHEMA = "rang.run-state"
STATE_VERSION = 1
LINEAR = (9, 10, 11, 12)  # CORR_TYPE XX, XY, YX, YY
ORIGINAL = core_writeback.DEFAULT_BACKUP


class StageFailed(RuntimeError):
    """A stage ran and failed; the state file records it."""


class Refused(RuntimeError):
    """The data, the run directory or the configuration cannot be run."""


def _now():
    return _dt.datetime.now(_dt.timezone.utc)


def _iso(t=None):
    return (t or _now()).isoformat(timespec="seconds")


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path, payload):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True, default=str)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def default_run_dir(ms):
    ms = Path(ms).resolve()
    return ms.with_name(ms.name + ".rang-run")


# -- the Measurement Set ---------------------------------------------------------


UNSUPPORTED = "(unsupported data, task W4: research/w4-unsupported.md)"
CORR_NAMES = {
    1: "I",
    2: "Q",
    3: "U",
    4: "V",
    5: "RR",
    6: "RL",
    7: "LR",
    8: "LL",
    9: "XX",
    10: "XY",
    11: "YX",
    12: "YY",
}
ALL_STAGES = frozenset(core_config.STAGES)
ROW_COLUMNS = ("FIELD_ID", "DATA_DESC_ID", "SCAN_NUMBER", "ANTENNA1", "ANTENNA2")


def _cell_defined(table, name, cell):
    """Whether row 0 of column `name` holds a `cell`-shaped array. A declared
    column whose cells were never written reads as no array or a
    one-element one, and is taken as absent."""
    try:
        value = np.asarray(table.getcol(name, 0, 1))
    except (OSError, ValueError):  # undefined cells
        return False
    return tuple(value.shape[1:]) == tuple(cell)


def corr_names(corr):
    return ", ".join(CORR_NAMES.get(int(c), str(int(c))) for c in corr)


def inspect_ms(ms):
    """What the stages need to know of `ms`. Refused only for what no stage
    can read (not an MS, no rows, no DATA, DATA cells of different shapes);
    what some stages cannot run is reported by `check_data`."""
    ms = Path(ms)
    if not (ms / "table.dat").is_file():
        raise Refused(f"{ms} is not a Measurement Set (no table.dat)")
    try:
        layout = core_writeback.layout(ms)
    except core_writeback.UnsupportedLayout as exc:
        raise Refused(f"{exc} {UNSUPPORTED}") from exc
    present = set(layout["columns"])
    with core_ms.open_table(ms) as t:
        rows = {name: np.asarray(t.getcol(name)) for name in ROW_COLUMNS}
        weight_spectrum = "WEIGHT_SPECTRUM" in present and _cell_defined(
            t, "WEIGHT_SPECTRUM", layout["cell"]
        )
    ddids = np.unique(rows["DATA_DESC_ID"])
    with core_ms.open_table(ms / "DATA_DESCRIPTION") as dd:
        spw_of = [int(s) for s in dd.getcol("SPECTRAL_WINDOW_ID")]
    ddid = int(ddids[0])
    spw = spw_of[ddid]
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as sw:
        chan_freq = np.asarray(sw.getcol("CHAN_FREQ", spw, 1)[0], np.float64)
        chan_width = np.asarray(sw.getcol("CHAN_WIDTH", spw, 1)[0], np.float64)
    with core_ms.open_table(ms / "ANTENNA") as an:
        positions = np.asarray(an.getcol("POSITION"), np.float64)
        antennas = [str(n) for n in an.getcol("NAME")]
    with core_ms.open_table(ms / "FIELD") as fd:
        names = [str(n) for n in fd.getcol("NAME")]
    corr = tuple(int(c) for c in layout["corr_type"])
    auto = rows["ANTENNA1"] == rows["ANTENNA2"]
    return {
        "ms": ms,
        "nrows": layout["nrows"],
        "cell": layout["cell"],
        "columns": sorted(present),
        "ddid": ddid,
        "ddids": ddids.tolist(),
        "spws": sorted({spw_of[int(d)] for d in ddids}),
        "spw": spw,
        "chan_freq": chan_freq,
        "chan_width": chan_width,
        "corr_type": np.asarray(corr, np.int32),
        "antenna_position": positions,
        "antennas": antennas,
        "fields": names,
        "field_ids_in_use": np.unique(rows["FIELD_ID"]).tolist(),
        "scans": np.unique(rows["SCAN_NUMBER"]).tolist(),
        "weight_spectrum": weight_spectrum,
        "autocorrelations": int(auto.sum()),
        "rows": rows,
    }


def check_data(config, info, stages):
    """[message] for every property of the MS that one of `stages` cannot
    run on (task W4, research/w4-unsupported.md), all at once."""
    stages = [s for s in core_config.STAGES if s in stages]
    ms, out = info["ms"], []

    def no(which, text):
        hit = [s for s in stages if s in which]
        if hit:
            out.append(f"{', '.join(hit)}: {text} {UNSUPPORTED}")

    columns = set(info["columns"])
    for name in ("FLAG", "FLAG_ROW"):
        if name not in columns:
            no(
                ALL_STAGES,
                f"{ms} has no {name} column; it is required by the Measurement Set "
                "definition, every stage reads it and every flag version saves it",
            )
    nfield = len(info["fields"])
    stray = [f for f in info["field_ids_in_use"] if not 0 <= f < nfield]
    if stray:
        counts = [int((info["rows"]["FIELD_ID"] == f).sum()) for f in stray]
        no(
            ALL_STAGES,
            f"FIELD_ID {', '.join(map(str, stray))} ({sum(counts)} rows) has no FIELD "
            f"row (the FIELD table has {nfield} rows)",
        )
    if len(info["ddids"]) > 1:
        no(
            ALL_STAGES,
            f"{ms} uses {len(info['ddids'])} data descriptions {info['ddids']} "
            f"(spectral windows {info['spws']}); rang-core reads one: write-back, the "
            "solves and gemclean take one window and one correlation setup. Split one "
            "window out first, for example with CASA split or mstransform (spw=...)",
        )
    corr = tuple(int(c) for c in info["corr_type"])
    names = corr_names(corr)
    if any(c in (5, 6, 7, 8) for c in corr):
        no(
            ALL_STAGES,
            f"correlations {names}: circular feeds; rang-core handles MeerKAT's "
            "linear feeds only (research/meerkat-scope.md)",
        )
    elif len(corr) == 1:
        no(
            ALL_STAGES,
            f"one correlation ({names}): the flagger needs polarised intensity and "
            "Stokes I needs XX and YY",
        )
    elif sorted(corr) == list(LINEAR) and corr != LINEAR:
        no(
            ALL_STAGES,
            f"correlations in the order {names}; rang-core needs the order "
            "XX, XY, YX, YY",
        )
    elif corr == (9, 12):
        no(
            ("calibrate", "apply"),
            f"correlations {names}: the solves and the apply kernel take four "
            "correlations (XX, XY, YX, YY), including the diagonal K, G and B "
            "terms",
        )
    elif corr != LINEAR:
        no(
            ALL_STAGES,
            f"correlations {names}: rang-core needs XX, XY, YX, YY (flag and image "
            "also take XX, YY)",
        )
    weights = info["weight_spectrum"] or "WEIGHT" in columns
    if not weights and config["data"]["weights"] == "as_is":
        no(
            ("calibrate",),
            f"{ms} has no WEIGHT_SPECTRUM or WEIGHT (data.weights: as_is reads them); "
            "set data.weights: uniform to solve with unit weights",
        )
    if not weights:
        no(
            ("image",),
            f"{ms} has no WEIGHT_SPECTRUM or WEIGHT, and gemclean reads them",
        )
    elif "WEIGHT_SPECTRUM" in columns and not info["weight_spectrum"]:
        no(
            ("image",),
            f"{ms} declares WEIGHT_SPECTRUM but row 0 has no cells of {info['cell']} "
            "written; gemclean would read the column anyway (it tests only that row 0 "
            "can be read). Write it, or remove the column so WEIGHT is used",
        )
    if len(info["ddids"]) == 1 and info["ddid"] != 0:
        no(
            ("image",),
            f"every row is on DATA_DESC_ID {info['ddid']}; gemclean images data "
            "description 0 only",
        )
    scans = config["data"]["scans"]
    if scans and "image" in stages:
        try:
            ids = resolve_fields(config["image"]["fields"], config, info, "image")
        except Refused:  # reported by preflight
            ids = []
        rows = info["rows"]
        for f in ids:
            mine = rows["FIELD_ID"] == f
            left = sorted(
                set(np.unique(rows["SCAN_NUMBER"][mine]).tolist()) - set(scans)
            )
            if left:
                no(
                    ("image",),
                    f"data.scans {scans} leaves out scans {left} of field "
                    f"{info['fields'][f]!r}, but gemclean has no scan selection and "
                    "would image them too; leave data.scans out for image, or split "
                    "the scans out first",
                )
    return out


def resolve_fields(tokens, config, info, where):
    """FIELD ids of a list of tokens: `all`, role names (expanded through
    `fields`), FIELD names or ids."""
    out, missing = set(), []
    names = info["fields"]
    for token in tokens or []:
        if token == "all":
            out.update(range(len(names)))
        elif isinstance(token, str) and token in core_config.ROLES:
            members = config["fields"][token]
            if token == "bpcal" and not members:
                members = config["fields"]["fcal"]
            if not members:
                missing.append(f"role {token!r} has no fields (set fields.{token})")
            for member in members:
                out.update(resolve_fields([member], config, info, where))
        elif isinstance(token, int):
            if 0 <= token < len(names):
                out.add(token)
            else:
                missing.append(f"field id {token} (the MS has {len(names)})")
        elif token in names:
            out.update(i for i, n in enumerate(names) if n == token)
        else:
            missing.append(f"field {token!r} (the MS has {names})")
    if missing:
        raise Refused(f"{where}: " + "; ".join(missing))
    return sorted(out)


def _leaves(tokens, config):
    """Each FIELD name or id a field list names, roles expanded (not `all`)."""
    for token in tokens or []:
        if token == "all":
            continue
        if isinstance(token, str) and token in core_config.ROLES:
            members = config["fields"][token]
            if token == "bpcal" and not members:
                members = config["fields"]["fcal"]
            yield from _leaves(members, config)
        else:
            yield token


def count_rows(info, field_ids, scans=(), cross=False):
    """Rows of `field_ids` (in `scans`, when given; cross-correlations only
    with `cross`)."""
    rows = info["rows"]
    keep = np.isin(rows["FIELD_ID"], list(field_ids))
    if scans:
        keep &= np.isin(rows["SCAN_NUMBER"], list(scans))
    if cross:
        keep &= rows["ANTENNA1"] != rows["ANTENNA2"]
    return int(keep.sum())


def _selection_problems(config, info, lists):
    """Empty selections and ambiguous image fields (task W4): a named field
    with no rows, a stage or term whose fields have no rows in `data.scans`,
    and a FIELD name of several fields in image.fields."""
    problems = []
    scans = config["data"]["scans"]
    for where, tokens, stage in lists:
        for leaf in _leaves(tokens, config):
            ids = resolve_fields([leaf], config, info, where)
            if not count_rows(info, ids):
                problems.append(f"{where}: field {leaf!r} has no rows")
            elif stage == "image" and isinstance(leaf, str) and len(ids) > 1:
                problems.append(
                    f"{where}: the name {leaf!r} is used by field ids {ids}; give the "
                    "field id (one image per field)"
                )
        ids = resolve_fields(tokens, config, info, where)
        if stage in ("flag", "calibrate") and ids and scans:
            cross = stage == "calibrate"
            if not count_rows(info, ids, scans, cross=cross):
                names = [info["fields"][f] for f in ids]
                problems.append(
                    f"{where}, data.scans: no rows of fields {names} in scans {scans} "
                    f"(the MS has scans {info['scans']})"
                )
    return problems


def preflight(config, info, stages):
    """Check the data for the stages (`check_data`) and resolve every field
    list they use, before anything is written."""
    problems = check_data(config, info, stages)
    lists = []
    if "flag" in stages:
        lists.append(("flag.fields", config["flag"]["fields"], "flag"))
    if "calibrate" in stages:
        for section in core_config.CALIBRATE_SECTIONS:
            block = config["calibrate"][section]
            for i, term in enumerate(block["terms"]):
                lists.append(
                    (
                        f"calibrate.{section}.terms[{i}].field",
                        term["field"] or block["field"],
                        "calibrate",
                    )
                )
    if "image" in stages:
        lists.append(("image.fields", config["image"]["fields"], "image"))
    if "apply" in stages:
        for i, target in enumerate(config["apply"]["targets"]):
            lists.append((f"apply.targets[{i}].field", target["field"], "apply"))
    resolved = []
    for item in lists:
        try:
            resolve_fields(item[1], config, info, item[0])
        except Refused as exc:
            problems.append(str(exc))
        else:
            resolved.append(item)
    problems += _selection_problems(config, info, resolved)
    if "apply" in stages and not problems:
        solved = complex_fields(config, info)
        for i, target in enumerate(config["apply"]["targets"]):
            fields = resolve_fields(
                target["field"], config, info, f"apply.targets[{i}].field"
            )
            for name in target["tables"]:
                if name not in solved:
                    continue
                other = [info["fields"][f] for f in fields if f not in solved[name]]
                if other:
                    problems.append(
                        f"apply.targets[{i}]: the complex term {name!r} is not solved "
                        f"on {other}; a complex term is applied only where it was "
                        "solved (research/c4b-apply-ms.md, owner decision 2): solve "
                        "G and F terms to transfer gains"
                    )
    if "calibrate" in stages:
        model = config["calibrate"]["model"]
        if model["source"] == "column" and model["column"] not in info["columns"]:
            problems.append(
                f"calibrate.model.column: {info['ms']} has no {model['column']} "
                "(write a calibrator model with model.source setjy, manual or lsm; "
                "MODEL_DATA from the imager is task G6)"
            )
    if problems:
        raise Refused("\n".join(problems))


def complex_fields(config, info):
    """{term name: FIELD ids it is solved on} for the complex terms."""
    out = {}
    for section in core_config.CALIBRATE_SECTIONS:
        block = config["calibrate"][section]
        for term in block["terms"]:
            if term["type"] == "complex":
                out[term["name"]] = set(
                    resolve_fields(
                        term["field"] or block["field"],
                        config,
                        info,
                        f"calibrate.{section}",
                    )
                )
    return out


def _read_columns(ms, names, nrows, chunk_rows=None):
    """Whole columns read in row chunks into one array each (W3 chunks the
    stages themselves)."""
    out = {}
    with core_ms.open_table(ms) as t:
        for name in names:
            first = t.getcol(name, 0, 1)
            array = np.empty((nrows, *first.shape[1:]), first.dtype)
            rows = chunk_rows or max(
                1, core_writeback.chunk_rows_for(first.shape[1:] or (1,))
            )
            for start, n in flagversions.spans(nrows, rows):
                array[start : start + n] = t.getcol(name, start, n)
            out[name] = array
    return out


def _groups(columns, rows):
    """{(field, ddid, scan): row indices} of the selected rows, in row order."""
    keys = np.stack(
        [
            columns["FIELD_ID"][rows],
            columns["DATA_DESC_ID"][rows],
            columns["SCAN_NUMBER"][rows],
        ],
        axis=1,
    )
    unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    return {
        tuple(int(v) for v in key): rows[inverse == i] for i, key in enumerate(unique)
    }


def _selected_rows(columns, field_ids, scans):
    keep = np.isin(columns["FIELD_ID"], field_ids)
    if scans:
        keep &= np.isin(columns["SCAN_NUMBER"], scans)
    return np.flatnonzero(keep)


# -- the run directory -----------------------------------------------------------


class RunDir:
    """The run directory of one MS: `state.json`, a lock, stage outputs."""

    def __init__(self, path, ms):
        self.path = Path(path)
        self.ms = Path(ms).resolve()
        self.state_path = self.path / "state.json"
        self.state = None
        self._lock = None

    @contextmanager
    def locked(self):
        self.path.mkdir(parents=True, exist_ok=True)
        with open(self.path / "lock", "a+", encoding="utf-8", newline="\n") as handle:
            try:
                import fcntl
            except ImportError:  # Windows: no lock (research/w2-commands.md)
                fcntl = None
            if fcntl is not None:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise Refused(
                        f"{self.path} is in use by another rang-core command"
                    ) from exc
            self.state = self.load()
            yield self

    def load(self):
        if not self.state_path.is_file():
            return {
                "schema": STATE_SCHEMA,
                "version": STATE_VERSION,
                "ms": str(self.ms),
                "created": _iso(),
                "stages": {},
            }
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if state.get("schema") != STATE_SCHEMA or state.get("version") != STATE_VERSION:
            raise Refused(f"{self.state_path} is not a {STATE_SCHEMA} version 1 file")
        if state["ms"] != str(self.ms):
            raise Refused(
                f"{self.path} belongs to {state['ms']}, not {self.ms}; give --run-dir"
            )
        return state

    def save(self):
        self.state["updated"] = _iso()
        _write_json(self.state_path, self.state)

    def stage_dir(self, stage, fresh=False):
        path = self.path / stage
        if fresh and path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        return path


# -- flags -----------------------------------------------------------------------


def _version_name(ms, stage):
    base = f"rang_{stage}_{_now().strftime('%Y%m%dT%H%M%SZ')}"
    name, i = base, 1
    while (
        flagversions.exists(ms, name)
        or (flagversions.root(ms) / f"flags.{name}").exists()
    ):
        i += 1
        name = f"{base}_{i}"
    return name


def restore_before(ms, entry):
    """Give the MS back the flags saved before this stage's last attempt
    (when it saved any), so a rerun starts from the same input. Returns the
    version restored, or None."""
    journal = core_writeback.read_journal(ms)
    prior = entry.get("flag_version")
    unfinished = journal and journal.get("state") in ("open", "failed")
    if unfinished and (not prior or journal.get("flag_backup") != prior):
        raise Refused(
            f"an earlier write-back on {ms} (stage {journal.get('stage')!r}) did "
            "not finish and was not made by this run directory; call "
            f"rang.core_writeback.restore_flags({str(ms)!r}, "
            f"{journal.get('flag_backup')!r}) first"
        )
    if prior and flagversions.exists(ms, prior):
        core_writeback.restore_flags(ms, prior)
        return prior
    return None


def stage_version(ctx, stage):
    """The flag version every write of this attempt of `stage` saves before
    its first write (`rang_<stage>_<time>`, recorded in the state entry so a
    rerun restores it), with `rang_original` saved first if absent. One per
    attempt, so a stage with several write sessions (calibrate's model, A
    steps) is restored to its input, not to a state between them."""
    if ctx.get("flag_version") is None:
        ms, run = ctx["ms"], ctx["run"]
        journal = core_writeback.read_journal(ms)
        if journal and journal.get("state") in ("open", "failed"):
            raise Refused(f"{ms}: an unfinished write-back must be restored first")
        rows = ctx["config"]["data"]["chunk_rows"] or core_writeback.chunk_rows_for(
            ctx["info"]["cell"]
        )
        ctx["original_saved_now"] = core_writeback.backup_flags(
            ms, ORIGINAL, comment="rang: flags before the first write", chunk_rows=rows
        )
        version = _version_name(ms, stage)
        run.state["stages"][stage]["flag_version"] = version
        run.save()
        ctx["flag_version"] = version
    return ctx["flag_version"]


@contextmanager
def writeback_session(ctx, stage):
    """A `WriteBack` session for a writing stage: `rang_original` saved if
    absent, then the attempt's `rang_<stage>_<time>` (`stage_version`) saved
    by the session before its first write."""
    ms = ctx["ms"]
    chunk_rows = ctx["config"]["data"]["chunk_rows"]
    journal = core_writeback.read_journal(ms)
    if journal and journal.get("state") in ("open", "failed"):
        raise Refused(f"{ms}: an unfinished write-back must be restored first")
    rows = chunk_rows or core_writeback.chunk_rows_for(ctx["info"]["cell"])
    version = stage_version(ctx, stage)
    saved = ctx["original_saved_now"]
    with core_writeback.WriteBack(
        ms,
        flag_backup=version,
        stage=stage,
        comment=f"rang: flags before {stage}",
        chunk_rows=rows,
    ) as w:
        yield w, {"flag_version": version, "rang_original_saved_now": saved}


def write_flags(run, ms, stage, flag, chunk_rows=None):
    """Save `rang_original` if absent and `rang_<stage>_<time>`, then write
    FLAG (rows, nchan, ncorr) in chunks. FLAG_ROW is not written."""
    journal = core_writeback.read_journal(ms)
    if journal and journal.get("state") in ("open", "failed"):
        raise Refused(f"{ms}: an unfinished write-back must be restored first")
    rows = chunk_rows or core_writeback.chunk_rows_for(flag.shape[1:])
    saved = core_writeback.backup_flags(
        ms, ORIGINAL, comment="rang: flags before the first write", chunk_rows=rows
    )
    version = _version_name(ms, stage)
    entry = run.state["stages"][stage]
    entry["flag_version"] = version
    run.save()
    with core_writeback.WriteBack(
        ms,
        flag_backup=version,
        stage=stage,
        comment=f"rang: flags before {stage}",
        chunk_rows=rows,
    ) as w:
        for start, n in w.chunks():
            w.write_flags(start, flag[start : start + n])
    return {"flag_version": version, "rang_original_saved_now": saved}


# -- the stages ------------------------------------------------------------------


def _resolve_path(value, config_path):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(config_path).resolve().parent / path
    return path


def stage_flag(ctx):
    config, info, ms = ctx["config"], ctx["info"], ctx["ms"]
    cfg = config["flag"]
    strategy_path = _resolve_path(cfg["strategy"], ctx["config_path"])
    if not strategy_path.is_file():
        raise StageFailed(f"flag.strategy: {strategy_path} not found")
    text = strategy_path.read_text(encoding="utf-8")
    strategies = core_flag.parse_strategy(text)
    if cfg["static_masks"] == "tricolour":
        mask_files = core_flag.static_mask_files()
        masks = [core_flag.load_static_mask(p) for p in mask_files]
    else:
        mask_files, masks = [], []
    restored = restore_before(ms, ctx["entry"])
    fields = resolve_fields(cfg["fields"], config, info, "flag.fields")
    names = ["FIELD_ID", "DATA_DESC_ID", "SCAN_NUMBER", "ANTENNA1", "ANTENNA2", "TIME"]
    columns = _read_columns(ms, [*names, cfg["column"], "FLAG"], info["nrows"])
    data, flag = columns[cfg["column"]], columns["FLAG"]
    rows = _selected_rows(columns, fields, config["data"]["scans"])
    new = flag.copy()
    groups = []
    for (field, ddid, scan), idx in _groups(columns, rows).items():
        result = core_flag.flag_rows(
            data[idx],
            flag[idx],
            columns["ANTENNA1"][idx],
            columns["ANTENNA2"][idx],
            columns["TIME"][idx],
            info["antenna_position"],
            info["chan_freq"],
            info["chan_width"],
            info["corr_type"],
            strategies,
            masks=masks,
            want_intensity=False,
            want_stages=False,
        )
        out = result["flags"]
        new[idx] = out if cfg["write"] == "replace" else (flag[idx] | out)
        groups.append(
            {
                "field_id": field,
                "field": info["fields"][field],
                "ddid": ddid,
                "scan": scan,
                "rows": len(idx),
                "flagged_before": float(flag[idx].mean()),
                "flagged_after": float(new[idx].mean()),
                "core_seconds": result["seconds"],
            }
        )
    del data, columns
    written = write_flags(
        ctx["run"], ms, "flag", new, chunk_rows=config["data"]["chunk_rows"]
    )
    summary = {
        "strategy": str(strategy_path),
        "strategy_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "steps": len(strategies),
        "static_masks": {p.name: _sha256_file(p) for p in mask_files},
        "write": cfg["write"],
        "column": cfg["column"],
        "restored_before": restored,
        "groups": groups,
        "rows_flagged": len(rows),
        "flagged_before": float(flag.mean()),
        "flagged_after": float(new.mean()),
        "flag_sha256": hashlib.sha256(np.ascontiguousarray(new).tobytes()).hexdigest(),
        **written,
    }
    _write_json(ctx["run"].stage_dir("flag") / "summary.json", summary)
    return summary


def solution_grid(times, nchan, chan_freq, solint, freqint):
    """QuartiCal-style bins for one partition: `solint` is inf (one bin),
    int (one per integration) or N integrations; `freqint` inf or N
    channels. Returns time_bin per row, freq_bin per channel and the bin
    centres (the mean of the times and frequencies in each bin, as
    `core_workflow.gain_grid`)."""
    unique, inverse = np.unique(times, return_inverse=True)
    inverse = inverse.reshape(-1)
    step_t = len(unique) if solint == "inf" else (1 if solint == "int" else int(solint))
    step_f = nchan if freqint == "inf" else (1 if freqint == "int" else int(freqint))
    time_bin = (inverse // step_t).astype(np.uint32)
    freq_bin = (np.arange(nchan) // step_f).astype(np.uint32)
    gain_time = np.array(
        [np.mean(unique[i : i + step_t]) for i in range(0, len(unique), step_t)]
    )
    gain_freq = np.array(
        [np.mean(chan_freq[i : i + step_f]) for i in range(0, nchan, step_f)]
    )
    return time_bin, freq_bin, gain_time, gain_freq


def solve_partition(columns, idx, info, term, weights_mode, model_source, model_column):
    """One `complex` solve on rows `idx` of one field and scan. Rows are
    sorted stably by TIME first. Returns (solution, time_bin, freq_bin,
    gain_time, gain_freq)."""
    order = idx[np.argsort(columns["TIME"][idx], kind="stable")]
    nchan = info["cell"][0]
    time_bin, freq_bin, gain_time, gain_freq = solution_grid(
        columns["TIME"][order],
        nchan,
        info["chan_freq"],
        term["solint"],
        term["freqint"],
    )
    data = columns["DATA"][order]
    if weights_mode == "uniform":
        weights = np.ones(data.shape, np.float32)
    elif "WEIGHT_SPECTRUM" in columns:
        weights = columns["WEIGHT_SPECTRUM"][order]
    else:
        weights = np.repeat(columns["WEIGHT"][order][:, None, :], nchan, axis=1)
    kwargs = {}
    if model_source == "column":
        kwargs["model"] = columns[model_column][order]
    else:
        kwargs["scalar_model"] = np.ones(nchan, np.float64)
    solution = core.solve_complex(
        data,
        weights,
        columns["FLAG"][order],
        columns["FLAG_ROW"][order],
        columns["ANTENNA1"][order],
        columns["ANTENNA2"][order],
        time_bin,
        freq_bin,
        ntime_bins=len(gain_time),
        nfreq_bins=len(gain_freq),
        nant=len(info["antennas"]),
        max_iterations=term["max_iterations"],
        stop_criterion=term["stop_criterion"],
        stop_fraction=term["stop_fraction"],
        **kwargs,
    )
    return solution, time_bin, freq_bin, gain_time, gain_freq


def calibration_columns(info, config):
    names = ["FIELD_ID", "DATA_DESC_ID", "SCAN_NUMBER", "ANTENNA1", "ANTENNA2", "TIME"]
    names += ["DATA", "FLAG", "FLAG_ROW"]
    if config["data"]["weights"] == "as_is":
        # WEIGHT_SPECTRUM when row 0 has a cell of the DATA shape, else WEIGHT
        # (gemclean tests only that row 0 reads; check_data refuses image then).
        names.append("WEIGHT_SPECTRUM" if info["weight_spectrum"] else "WEIGHT")
    model = config["calibrate"]["model"]
    if model["source"] == "column":
        names.append(model["column"])
    elif model["source"] in core_config.MODEL_SOURCES:
        names.append("MODEL_DATA")
    return names


def model_spec(model, config_path):
    """The `rang.calmodels` spec of `calibrate.model` (setjy, manual, lsm)."""
    from . import calmodels

    if model["source"] == "setjy":
        return calmodels.Standard(standard=model["standard"] or "Stevens-Reynolds 2016")
    if model["source"] == "manual":
        return calmodels.Manual(
            model["flux_jy"][0], float(model["reffreq_hz"]), tuple(model["spix"] or ())
        )
    return calmodels.SkyModel(str(_resolve_path(model["lsm"], config_path)))


def write_models(ctx):
    """MODEL_DATA of the primary section's fields from `calibrate.model`
    (C3a's `calmodels.set_model`, one session and flag backup). Returns the
    receipts, or None for unity and column models."""
    from . import calmodels

    config, info, ms = ctx["config"], ctx["info"], ctx["ms"]
    model = config["calibrate"]["model"]
    if model["source"] not in core_config.MODEL_SOURCES:
        return None
    block = config["calibrate"]["primary"]
    fields = set()
    for term in block["terms"]:
        fields.update(
            resolve_fields(
                term["field"] or block["field"], config, info, "calibrate.primary"
            )
        )
    spec = model_spec(model, ctx["config_path"])
    with writeback_session(ctx, "calibrate") as (w, written):
        receipt = calmodels.set_model(
            ms, sorted(fields), spec, session=w, chunk_rows=config["data"]["chunk_rows"]
        )
    return {"spec": repr(spec), "fields": sorted(fields), "receipt": receipt, **written}


def uses_chain(config):
    """Whether calibrate runs CASA-style terms (K, G, B, A, F; task C2e)."""
    return any(
        term["type"] in core_config.CASA_TERMS
        for section in core_config.CALIBRATE_SECTIONS
        for term in config["calibrate"][section]["terms"]
    )


def _table_gainfield(fields):
    """The field map an A step gives a table solved on `fields`: that field,
    or the nearest on the sky when it has several (an F table holds the
    primary's and the secondary's rows)."""
    return str(fields[0]) if len(fields) == 1 else "nearest"


def chain_weight_column(config, info):
    """The weights the K, G, B and F solves read where no table is pre-applied
    (with one they use SIGMA, as CASA was measured to; research/c2a-gain.md
    section 6): None (unit weights) for `data.weights: uniform`, else
    WEIGHT_SPECTRUM, or WEIGHT per channel when it is absent."""
    if config["data"]["weights"] == "uniform":
        return None
    return "WEIGHT_SPECTRUM" if info["weight_spectrum"] else "WEIGHT"


def chain_terms(config, info, config_path):
    """`rang.cal_chain.run`'s terms for the K, G, B, A, F sequence of
    `calibrate.primary` and `calibrate.secondary` (task C2e). Defaults are
    CASA 6.7.6.14's where the configuration is silent (`minsnr` 3,
    `minblperant` 4, `calmode` ap, `fillgaps` 0); `uvrange` reaches G, B and
    F but not K, as CARACal passes it; primary terms solve against the model
    column (or a unit point for model source unity), secondary terms
    against CASA's unit point model (`smodel=[1,0,0,0]`), as CARACal."""
    cal = config["calibrate"]
    model = cal["model"]
    primary_model = "unit" if model["source"] == "unity" else "column"
    types, fields_of, terms = {}, {}, []
    primary_g = [t["name"] for t in cal["primary"]["terms"] if t["type"] == "G"]
    for section in ("primary", "secondary"):
        block = cal[section]
        history = []
        for term in block["terms"]:
            fields = resolve_fields(
                term["field"] or block["field"], config, info, f"calibrate.{section}"
            )
            kind, name = term["type"], term["name"]
            if kind == "A":
                names = cal_chain.a_tables(history)
                strategy = _resolve_path(
                    term["strategy"] or config["flag"]["strategy"], config_path
                )
                if not strategy.is_file():
                    raise StageFailed(
                        f"calibrate {name}: strategy {strategy} not found"
                    )
                text = strategy.read_text(encoding="utf-8")
                terms.append(
                    {
                        "type": "A",
                        "name": name,
                        "fields": fields,
                        "tables": names,
                        "gainfield": [_table_gainfield(fields_of[n]) for n in names],
                        "strategies": core_flag.parse_strategy(text),
                        "strategy": str(strategy),
                        "strategy_sha256": hashlib.sha256(
                            text.encode("utf-8")
                        ).hexdigest(),
                    }
                )
                continue
            for pre in term["preapply"]:
                if (pre, types[pre]) not in history:
                    history.append((pre, types[pre]))

            def pick(key, default, term=term):
                value = term.get(key)
                if value is None:
                    value = cal.get(key)
                return default if value is None else value

            spec = {
                "type": kind,
                "name": name,
                "fields": fields,
                "solint": term["solint"],
                "combine": term["combine"],
                "refant": pick("refant", None),
                "refantmode": pick("refantmode", "flex"),
                "minsnr": float(pick("minsnr", 3.0)),
                "minblperant": int(pick("minblperant", 4)),
                "uvrange": (term["uvrange"] or "")
                if kind == "K"
                else pick("uvrange", ""),
                "preapply": list(term["preapply"]),
                "interp": list(term["interp"]),
                "max_iterations": 50,
                "stop_criterion": 1e-7,
                "stop_fraction": 0.99,
                "model": primary_model if section == "primary" else "unit",
            }
            if kind in ("G", "F"):
                spec["calmode"] = term["calmode"] or "ap"
            if kind == "B":
                spec["fillgaps"] = int(term["fillgaps"] or 0)
            if kind == "F":
                spec["base"] = primary_g[-1]
                spec["smodel"] = list(term["smodel"] or [1.0, 0.0, 0.0, 0.0])
            terms.append(spec)
            types[name] = kind
            fields_of[name] = fields
            history.append((name, kind))
            if kind == "F":
                fields_of[name] = sorted(set(fields) | set(fields_of[spec["base"]]))
    return terms


def stage_calibrate_chain(ctx):
    """calibrate with K, G, B, A and F terms (task C2e): models into
    MODEL_DATA on the primary fields, then `rang.cal_chain.run`, every write
    through the attempt's flag version."""
    config, info, ms, run = ctx["config"], ctx["info"], ctx["ms"], ctx["run"]
    cal = config["calibrate"]
    restored = restore_before(ms, ctx["entry"])
    out_dir = run.stage_dir("calibrate", fresh=True)
    models = write_models(ctx)
    model_column = "MODEL_DATA" if models is not None else cal["model"]["column"]
    terms = chain_terms(config, info, ctx["config_path"])
    if config["flag"]["static_masks"] == "tricolour":
        masks = [core_flag.load_static_mask(p) for p in core_flag.static_mask_files()]
    else:
        masks = []
    scans = config["data"]["scans"] or None
    version = stage_version(ctx, "calibrate")
    result = cal_chain.run(
        ms,
        terms,
        out_dir=out_dir,
        model_column=model_column,
        weight_column=chain_weight_column(config, info),
        scan=scans,
        masks=masks,
        chunk_rows=config["data"]["chunk_rows"],
        flag_backup=version,
        stage="calibrate",
    )
    steps = result["steps"]
    for step, term in zip(steps, terms):
        if term["type"] == "A":
            step["strategy"] = term["strategy"]
            step["strategy_sha256"] = term["strategy_sha256"]
    tables = [
        {
            "section": "chain",
            "name": name,
            "type": entry["type"],
            "format": "casa",
            "path": entry["path"],
            "fields": entry["fields"],
        }
        for name, entry in result["tables"].items()
    ]
    summary = {
        "weights": config["data"]["weights"],
        "weight_column": chain_weight_column(config, info) or "unit",
        "scans": scans,
        "model": cal["model"]["source"],
        "models_written": models,
        "restored_before": restored,
        "tables": tables,
        "steps": steps,
        "flag_version": version,
        "k_offsets": cal_chain.K_ALONE.split(":")[1].strip(),
    }
    _write_json(out_dir / "summary.json", summary)
    return summary


def stage_calibrate(ctx):
    config, info, ms, run = ctx["config"], ctx["info"], ctx["ms"], ctx["run"]
    if uses_chain(config):
        return stage_calibrate_chain(ctx)
    cal = config["calibrate"]
    restored = restore_before(ms, ctx["entry"])
    out_dir = run.stage_dir("calibrate", fresh=True)
    models = write_models(ctx)
    source, model_column = cal["model"]["source"], cal["model"]["column"]
    if models is not None:
        source, model_column = "column", "MODEL_DATA"
    columns = _read_columns(ms, calibration_columns(info, config), info["nrows"])
    tables = []
    for section in core_config.CALIBRATE_SECTIONS:
        block = cal[section]
        for term in block["terms"]:
            fields = resolve_fields(
                term["field"] or block["field"], config, info, f"calibrate.{section}"
            )
            rows = _selected_rows(columns, fields, config["data"]["scans"])
            # Autocorrelations are left out of the solve (task W4), as C2a's.
            rows = rows[columns["ANTENNA1"][rows] != columns["ANTENNA2"][rows]]
            if not len(rows):
                raise StageFailed(f"calibrate.{section}: no rows in fields {fields}")
            parts, records = [], []
            for (field, ddid, scan), idx in _groups(columns, rows).items():
                solution, _, _, gain_time, gain_freq = solve_partition(
                    columns,
                    idx,
                    info,
                    term,
                    config["data"]["weights"],
                    source,
                    model_column,
                )
                valid = (solution.flags == 0) & np.isfinite(solution.gains).all(
                    axis=(-1, -2)
                )
                where = f"{term['name']} on field {info['fields'][field]} scan {scan}"
                if not valid.any():
                    raise StageFailed(f"calibrate: {where} gave no valid solution")
                parts.append(
                    quartical_store.complex_partition(
                        solution.gains[:, :, :, None],
                        solution.flags[:, :, :, None],
                        gain_time,
                        gain_freq,
                        info["antennas"],
                        name=term["name"],
                        field_id=field,
                        field_name=info["fields"][field],
                        scan=scan,
                        ddid=ddid,
                    )
                )
                records.append(
                    {
                        "field_id": field,
                        "field": info["fields"][field],
                        "scan": scan,
                        "ddid": ddid,
                        "rows": len(idx),
                        "time_bins": len(gain_time),
                        "freq_bins": len(gain_freq),
                        "iterations": solution.iterations,
                        "converged_fraction": solution.converged_fraction,
                        "valid_fraction": float(valid.mean()),
                        "gains_sha256": hashlib.sha256(
                            np.ascontiguousarray(solution.gains).tobytes()
                        ).hexdigest(),
                    }
                )
            store = out_dir / f"{term['name']}.qc"
            quartical_store.write({term["name"]: parts}, store)
            tables.append(
                {
                    "section": section,
                    "name": term["name"],
                    "type": term["type"],
                    "store": str(store),
                    "solint": term["solint"],
                    "freqint": term["freqint"],
                    "partitions": records,
                }
            )
    summary = {
        "weights": config["data"]["weights"],
        "model": cal["model"]["source"],
        "models_written": models,
        "restored_before": restored,
        "tables": tables,
    }
    if models is not None:
        summary["flag_version"] = models["flag_version"]
    _write_json(out_dir / "summary.json", summary)
    return summary


def apply_targets(config, info, solved):
    """[(field ids, [table names], target)]: `apply.targets`, or every
    complex term applied to the fields it is solved on."""
    targets = config["apply"]["targets"]
    if targets:
        return [
            (
                resolve_fields(t["field"], config, info, f"apply.targets[{i}].field"),
                list(t["tables"]),
                t,
            )
            for i, t in enumerate(targets)
        ]
    return [(sorted(fields), [name], None) for name, fields in solved.items()]


def stage_apply(ctx):
    """The complex terms of this run's calibrate stage applied on their own
    solution bins (task W2b, research/c4b-apply-ms.md), into `apply.column`
    with FLAG OR'd, in one write-back session."""
    from . import applycal

    config, info, ms, run = ctx["config"], ctx["info"], ctx["ms"], ctx["run"]
    cfg = config["apply"]
    cal = run.state["stages"].get("calibrate", {})
    summary_path = run.path / "calibrate" / "summary.json"
    if cal.get("status") != "done" or not summary_path.is_file():
        raise StageFailed("apply needs the tables of a finished calibrate stage")
    made = {
        t["name"]: t
        for t in json.loads(summary_path.read_text(encoding="utf-8"))["tables"]
    }
    solved = complex_fields(config, info)
    targets = apply_targets(config, info, solved)
    for fields, names, _ in targets:
        for name in names:
            if name not in made:
                raise StageFailed(f"apply: calibrate wrote no table {name!r}")
    restored = restore_before(ms, ctx["entry"])
    applied, warnings = [], []
    scans = config["data"]["scans"] or None
    with writeback_session(ctx, "apply") as (w, written):
        for i, (fields, names, target) in enumerate(targets):
            if all(made[n].get("format") == "casa" for n in names):
                kinds = [made[n]["type"] for n in names]
                result = applycal.applycal(
                    ms,
                    [made[n]["path"] for n in names],
                    interp=list(target["interp"]) or ["linear"],
                    gainfield=list(target["gainfield"]) or [""],
                    calwt=[cfg["calwt"]],
                    field=fields,
                    applymode=cfg["applymode"],
                    column=cfg["column"],
                    session=w,
                    chunk_rows=config["data"]["chunk_rows"],
                    scan=scans,
                )
                result["tables_applied"] = names
                if cal_chain.k_alone(kinds):
                    result["warning"] = cal_chain.K_ALONE
                    warnings.append(f"apply.targets[{i}]: {cal_chain.K_ALONE}")
                applied.append(result)
                continue
            for k, name in enumerate(names):
                table = made[name]
                result = applycal.apply_complex(
                    ms,
                    table["store"],
                    name,
                    (table["solint"], table["freqint"]),
                    fields=fields,
                    column=cfg["column"],
                    session=w,
                    chunk_rows=config["data"]["chunk_rows"],
                    input_column="DATA" if k == 0 else cfg["column"],
                )
                applied.append(result)
    summary = {
        "column": cfg["column"],
        "applymode": cfg["applymode"],
        "calwt": cfg["calwt"],
        "calwt_note": "a complex (general Jones) term does not scale weights, as CASA; "
        "of the CASA tables only G, B and T do (rang.applycal)",
        "restored_before": restored,
        "applied": applied,
        "warnings": warnings,
        **written,
    }
    _write_json(run.stage_dir("apply", fresh=True) / "summary.json", summary)
    return summary


def find_gemclean(setting):
    """The gemclean binary: the configured path, else `gemclean` on PATH,
    else the checkout's core/target/{release,gemclean}/gemclean."""
    if setting != "auto":
        path = Path(setting).expanduser()
        if not path.is_file():
            raise StageFailed(
                f"image.gemclean: {path} not found (gemclean joins the wheel in task G8)"
            )
        return path
    found = shutil.which("gemclean")
    if found:
        return Path(found)
    root = core.checkout_root()
    if root is not None:
        for profile in ("release", "gemclean"):
            path = root / "core" / "target" / profile / "gemclean"
            if path.is_file():
                return path
    raise StageFailed(
        "image: no gemclean binary found (PATH, core/target/release, core/target/gemclean); "
        "build it with cargo build --release --manifest-path core/Cargo.toml or set "
        "image.gemclean (it joins the wheel in task G8)"
    )


def _safe(name):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def gemclean_arguments(img, column, field_id, prefix, ms):
    args = ["-name", str(prefix), "-size", *[str(v) for v in img["size"]]]
    args += ["-scale", img["scale"], "-weight", img["weight"]]
    if img["weight"] == "briggs":
        args.append(repr(float(img["robust"])))
    args += ["-niter", str(img["niter"])]
    for key, flag in (
        ("gain", "-gain"),
        ("mgain", "-mgain"),
        ("nmiter", "-nmiter"),
        ("threshold", "-threshold"),
        ("auto_threshold", "-auto-threshold"),
        ("threads", "-j"),
    ):
        if img[key] is not None:
            args += [flag, str(img[key])]
    args += ["-wgridder-accuracy", repr(float(img["wgridder_accuracy"]))]
    args += ["-data-column", column, "-field", str(field_id)]
    args += list(img["extra_args"])
    return [*args, str(ms)]


def stage_image(ctx):
    config, info, ms, run = ctx["config"], ctx["info"], ctx["ms"], ctx["run"]
    img = config["image"]
    binary = find_gemclean(img["gemclean"])
    column = img["column"]
    if column == "auto":
        applied = run.state["stages"].get("apply", {}).get("status") == "done"
        column = "CORRECTED_DATA" if applied else "DATA"
    if column not in core_writeback.layout(ms)["columns"]:  # apply may add it
        raise StageFailed(f"image.column: {ms} has no {column}")
    out_dir = run.stage_dir("image", fresh=True)
    images = []
    for field in resolve_fields(img["fields"], config, info, "image.fields"):
        name = info["fields"][field]
        field_dir = out_dir / _safe(name)
        field_dir.mkdir()
        prefix = field_dir / img["name"]
        argv = [str(binary), *gemclean_arguments(img, column, field, prefix, ms)]
        log = field_dir / "gemclean.log"
        started = time.perf_counter()
        with log.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(" ".join(argv) + "\n")
            fh.flush()
            done = subprocess.run(
                argv, stdout=fh, stderr=subprocess.STDOUT, check=False
            )
        seconds = time.perf_counter() - started
        if done.returncode:
            tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
            raise StageFailed(
                f"image: gemclean exited {done.returncode} on field {name}; "
                f"{log}: " + " | ".join(tail)
            )
        files = sorted(p for p in field_dir.iterdir() if p.is_file() and p != log)
        images.append(
            {
                "field_id": field,
                "field": name,
                "argv": argv,
                "wall_seconds": seconds,
                "files": {p.name: _sha256_file(p) for p in files},
            }
        )
    summary = {
        "gemclean": str(binary),
        "gemclean_sha256": _sha256_file(binary),
        "column": column,
        "images": images,
    }
    _write_json(out_dir / "summary.json", summary)
    return summary


def _refused_stage(task):
    def stage(ctx):  # validation refuses these first; this is a second guard
        raise Refused(f"this stage is not implemented yet (task {task})")

    return stage


STAGE_FUNCTIONS = {
    "flag": stage_flag,
    "calibrate": stage_calibrate,
    "apply": stage_apply,
    "image": stage_image,
    "selfcal": _refused_stage("C5a"),
}
WRITES_FLAGS = frozenset({"flag", "calibrate", "apply", "selfcal"})


# -- running ---------------------------------------------------------------------


def _alive(entry):
    """Whether the process that marked a stage `running` still runs. POSIX
    only: on Windows `os.kill(pid, 0)` would terminate the process, so a
    stage left `running` there is taken as interrupted."""
    if os.name != "posix" or entry.get("host") != socket.gethostname():
        return False
    try:
        pid = int(entry.get("pid") or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def execute(config, config_path, ms, stages, run_dir=None, force=(), log=print):
    """Run `stages` (in the order of `core_config.STAGES`) on `ms`, resuming
    from the run directory. Returns the state. Raises Refused before
    anything runs, or StageFailed with the state saved."""
    ms = Path(ms).resolve()
    stages = [s for s in core_config.STAGES if s in stages]
    force = set(core_config.STAGES if "all" in force else force)
    info = inspect_ms(ms)
    preflight(config, info, stages)
    run = RunDir(run_dir or default_run_dir(ms), ms)
    with run.locked():
        state = run.state
        state["config_path"] = str(Path(config_path).resolve())
        conflicts = []
        for stage in stages:  # before anything runs
            entry = state["stages"].get(stage, {})
            status = entry.get("status")
            if status == "running" and _alive(entry):
                raise Refused(f"{stage} is running in process {entry['pid']}")
            if (
                status == "done"
                and stage not in force
                and entry.get("config_sha256") != core_config.stage_hash(config, stage)
            ):
                conflicts.append(
                    f"{stage} finished with a different configuration "
                    f"({STAGE_SECTIONS_TEXT[stage]}); pass --force {stage} to run it "
                    "again"
                    + (
                        ", which first restores the flags saved before it"
                        if stage in WRITES_FLAGS
                        else ""
                    )
                )
        if conflicts:
            raise Refused("\n".join(conflicts))
        _write_json(run.path / "config.resolved.json", config)
        run.save()
        for stage in stages:
            entry = state["stages"].get(stage, {})
            digest = core_config.stage_hash(config, stage)
            status = entry.get("status")
            if status == "done" and stage not in force:
                log(f"rang-core: {stage}: done {entry.get('finished')}, skipped")
                continue
            attempt = {
                "status": "running",
                "config_sha256": digest,
                "sections": list(core_config.STAGE_SECTIONS[stage]),
                "started": _iso(),
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "previous": status,
                "attempts": int(entry.get("attempts", 0)) + 1,
            }
            if entry.get("flag_version"):
                attempt["flag_version"] = entry["flag_version"]
            state["stages"][stage] = attempt
            run.save()
            log(f"rang-core: {stage}: running" + (f" (was {status})" if status else ""))
            started = time.perf_counter()
            ctx = {
                "config": config,
                "config_path": config_path,
                "info": info,
                "ms": ms,
                "run": run,
                "entry": attempt,
            }
            try:
                summary = STAGE_FUNCTIONS[stage](ctx)
            except Exception as exc:
                attempt.update(
                    status="failed",
                    finished=_iso(),
                    seconds=time.perf_counter() - started,
                    error=f"{type(exc).__name__}: {exc}",
                )
                run.save()
                if isinstance(exc, (StageFailed, Refused)):
                    raise StageFailed(f"{stage}: {exc}") from exc
                raise
            attempt.update(
                status="done",
                finished=_iso(),
                seconds=time.perf_counter() - started,
                summary=_brief(summary),
            )
            later = core_config.STAGES[core_config.STAGES.index(stage) + 1 :]
            for other in later:
                if state["stages"].get(other, {}).get("status") == "done":
                    state["stages"][other]["status"] = "stale"
                    state["stages"][other]["stale_since"] = (
                        f"{stage} {attempt['finished']}"
                    )
            run.save()
            log(f"rang-core: {stage}: done in {attempt['seconds']:.1f} s")
        return state


STAGE_SECTIONS_TEXT = {
    s: "sections " + ", ".join(v) for s, v in core_config.STAGE_SECTIONS.items()
}


def _brief(summary):
    """The state file keeps the scalar parts of a stage's summary; the full
    summary is `<run>/<stage>/summary.json`."""
    return {k: v for k, v in summary.items() if not isinstance(v, (list, dict))}


__all__ = [
    "Refused",
    "RunDir",
    "StageFailed",
    "check_data",
    "count_rows",
    "default_run_dir",
    "execute",
    "find_gemclean",
    "gemclean_arguments",
    "inspect_ms",
    "resolve_fields",
    "restore_before",
    "solution_grid",
    "solve_partition",
    "write_flags",
]
