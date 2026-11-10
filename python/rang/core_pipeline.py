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
C2e), `image` (`gemclean` on a data column) and `selfcal` (task C5,
research/c5-selfcal.md: CARACal's rounds of image, model into MODEL_DATA,
solve and apply, one Sp, Sa or Sd term per round through
`rang.cal_selfcal`, then a final image).

Data a stage cannot run on (task W4, research/w4-unsupported.md) is refused
by `check_data` and `preflight` before anything is written, every problem at
once: several data descriptions in use, circular or single correlations, two
correlations for calibrate and apply, missing FLAG or FLAG_ROW, missing
weights, FIELD_IDs without a FIELD row, empty selections, ambiguous image
fields, and image when `data.scans` leaves out a scan of an imaged field or
on a data description other than 0.
Autocorrelations are flagged and corrected but left out of the solve.

Memory (task W3, research/w3-chunking.md): `flag`, `calibrate` and `apply`
read no visibility column whole. Chunk sizes follow from
`data.memory_limit_gb` (`rang.core_chunks`): `flag` takes blocks of
baselines of a group on the group's time grid, the `complex` solve chunks of
whole solution intervals with the stop test replayed (bit-identical to one
call), `apply` and the models row chunks. A limit below the smallest chunk is
refused by `preflight` (`memory_problems`) before anything is written.
"""

import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from . import (
    cal_chain,
    cal_refant,
    core,
    core_chunks,
    core_config,
    core_flag,
    core_model,
    core_ms,
    core_writeback,
)
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
# Read whole by `inspect_ms` and kept for the stages (TIME for the solve
# grids and the flagger's time axis, task W3): counted in core_chunks.ROW_BYTES.
ROW_COLUMNS = (
    "FIELD_ID",
    "DATA_DESC_ID",
    "SCAN_NUMBER",
    "ANTENNA1",
    "ANTENNA2",
    "TIME",
)


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
            ("calibrate", "apply", "selfcal"),
            f"correlations {names}: the solves and the apply kernel take four "
            "correlations (XX, XY, YX, YY), including the diagonal K, G and B "
            "terms",
        )
        try:
            pols = core_config.parse_pol(config["image"]["pol"])
        except ValueError:
            pols = []
        if {"U", "V"} & set(pols):
            no(
                ("image",),
                f"correlations {names}: image.pol {config['image']['pol']!r} needs "
                "XY and YX for Stokes U and V (task G9)",
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
    # gemclean reads WEIGHT where row 0 of WEIGHT_SPECTRUM holds no cell, as
    # WSClean does, and no weights with data.weights: uniform (task W6).
    if not weights and config["data"]["weights"] == "as_is":
        no(
            ("image", "selfcal"),
            f"{ms} has no WEIGHT_SPECTRUM or WEIGHT (data.weights: as_is reads them); "
            "set data.weights: uniform to image with unit weights",
        )
    if len(info["ddids"]) == 1 and info["ddid"] != 0:
        no(
            ("image", "selfcal"),
            f"every row is on DATA_DESC_ID {info['ddid']}; gemclean images data "
            "description 0 only",
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
        if stage == "image" and scans:
            # One image per field: each needs cross-correlation rows in the scans.
            for f in ids:
                if not count_rows(info, [f], scans, cross=True):
                    problems.append(
                        f"{where}, data.scans: no rows of field {info['fields'][f]!r} "
                        f"in scans {scans} (the MS has scans {info['scans']})"
                    )
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
    if "image" in stages or "selfcal" in stages:  # selfcal images (task C5)
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
        if not problems:
            problems += _polcal_problems(config, info)
        if not problems and uses_chain(config):
            problems += cal_refant.problems(config, info["ms"])  # task E0
    if not problems:
        problems += memory_problems(config, info, stages)
    if problems:
        raise Refused("\n".join(problems))


def _polcal_problems(config, info):
    """The polcal model's names and column, before anything is written
    (task C6w)."""
    from . import calmodels

    pm = config["calibrate"]["polcal"]["model"]
    out = []
    fields = polcal_fields(config, info)
    if not fields:
        return out
    if pm["source"] == "column" and pm["column"] not in info["columns"]:
        out.append(f"calibrate.polcal.model.column: {info['ms']} has no {pm['column']}")
    for field, name in polcal_models(config, info):
        key = calmodels.NRAO_XCAL_ALIASES.get(name, name)
        if key not in calmodels.NRAO_XCAL:
            out.append(
                f"calibrate.polcal.model: field {info['fields'][field]!r} has no NRAO "
                f"model under the name {name!r}; set calibrate.polcal.model.name to "
                f"one of {sorted(calmodels.NRAO_XCAL)} (or an alias "
                f"{sorted(calmodels.NRAO_XCAL_ALIASES)}), or use source: column"
            )
    return out


def memory_problems(config, info, stages):
    """[message] for each stage whose smallest chunk does not fit
    `data.memory_limit_gb` (task W3, research/w3-chunking.md): the process
    and its row metadata, one baseline of a flag group, one row of apply and
    of the models, one solution interval of a solve."""
    plan = core_chunks.budget(config, info)
    where = "data.memory_limit_gb"
    try:
        _ = plan.chunk_bytes
    except core_chunks.MemoryLimitError as exc:
        return [f"{', '.join(stages)}: {exc}"]
    out = []
    checks = {
        "flag": "flag",
        "apply": "apply",
        "calibrate": "model",
        "selfcal": "apply",
    }
    for stage, kind in checks.items():
        if stage in stages:
            try:
                plan.rows(kind)
            except core_chunks.MemoryLimitError as exc:
                out.append(f"{stage}: {exc}")
    if out:
        return out
    rows = info["rows"]
    if "flag" in stages:
        fields = resolve_fields(config["flag"]["fields"], config, info, "flag.fields")
        selected = _selected_rows(rows, fields, config["data"]["scans"])
        max_rows = plan.rows("flag", capped=False)
        for (field, _, scan), idx in _groups(rows, selected).items():
            # The smallest flag block is one baseline on the group's times.
            ntime = len(np.unique(rows["TIME"][idx]))
            if ntime > max_rows:
                out.append(
                    f"flag: field {info['fields'][field]!r} scan {scan} has {ntime} "
                    f"times, and one baseline of it needs "
                    f"{plan.need_gb('flag', ntime * np.prod(info['cell'])):.2f} GiB; "
                    f"raise {where}"
                )
    if "calibrate" in stages:
        max_cells = plan.cells("calibrate", capped=False)
        ncorr = info["cell"][1]
        for section in core_config.CALIBRATE_SECTIONS:
            for i, term in enumerate(config["calibrate"][section]["terms"]):
                if term["type"] != "complex":
                    continue
                _, selected = solve_rows(config, info, section, term)
                for (field, _, scan), idx in _groups(rows, selected).items():
                    _, tb, fb, _, _ = partition_grid(info, idx, term)
                    chunks, largest = core_chunks.solve_chunks(tb, fb, max_cells, ncorr)
                    if chunks is None:
                        out.append(
                            f"calibrate.{section}.terms[{i}] ({term['name']}): one "
                            f"solution interval of field {info['fields'][field]!r} "
                            f"scan {scan} holds {largest} visibility cells and needs "
                            f"{plan.need_gb('calibrate', largest):.3f} GiB, above "
                            f"{where} {plan.limit_gb:g}; raise the limit, or use a "
                            "shorter solint or a smaller freqint (a solution interval "
                            "is solved whole)"
                        )
        out += chain_memory_problems(config, info, plan)
    return out


# The chain terms solved per interval and channel (task W3b): their smallest
# chunk is one channel of one interval.
PER_CHANNEL_TERMS = ("B", "Xf", "Df")


def chain_chunk_plans(config, info, plan):
    """[(where, term, field, chunks or MemoryLimitError)] for every K, G,
    B, F, Gpol, KCROSS, Xf and Df solve (one per field) of the chain (task
    W3b, research/w3b-chainchunks.md): the chunks `rang.cal_chunks.plan`
    gives that solve under `plan` (a `core_chunks.Budget`), as the library
    computes them."""
    from . import cal_chunks, cal_gain

    out, rows = [], info["rows"]
    chain = plan.chain()
    for section in core_config.CALIBRATE_SECTIONS:
        block = config["calibrate"][section]
        for i, term in enumerate(block["terms"]):
            if term["type"] not in core_config.CHAIN_TERMS or term["type"] == "A":
                continue
            fields = resolve_fields(
                term["field"] or block["field"], config, info, f"calibrate.{section}"
            )
            where = f"calibrate.{section}.terms[{i}] ({term['name']}, {term['type']})"
            for f in fields:
                idx = _selected_rows(rows, [f], config["data"]["scans"])
                if not len(idx):
                    continue
                tb, _ = cal_gain.solint_bins(
                    rows["TIME"][idx], rows["SCAN_NUMBER"][idx], rows["FIELD_ID"][idx],
                    term["solint"] or "inf", term["combine"] or "",
                )  # fmt: skip
                try:
                    chunks, _ = cal_chunks.plan(
                        tb, info["cell"][0], info["cell"][1], chain,
                        per_channel=term["type"] in PER_CHANNEL_TERMS,
                        what=f"field {info['fields'][f]!r}",
                    )  # fmt: skip
                except core_chunks.MemoryLimitError as exc:
                    chunks = exc
                out.append((where, term, f, chunks))
    return out


def chain_memory_problems(config, info, plan):
    """[message] for each chain term (tasks C2e, C6w) whose smallest unit
    does not fit `data.memory_limit_gb` (task W3b): one solution interval
    of a field with all its channels (K, G, F, Gpol, KCROSS), one channel
    of one interval and one whole row (B, Xf, Df), or one baseline of an A
    step's flag group on its time grid. Everything else runs in chunks."""
    out = []
    try:
        plan.chain()
    except core_chunks.MemoryLimitError as exc:
        return [f"calibrate: {exc}"]
    for where, _, _, chunks in chain_chunk_plans(config, info, plan):
        if isinstance(chunks, core_chunks.MemoryLimitError):
            out.append(f"{where}: {chunks}")
    rows = info["rows"]
    max_rows = plan.rows("flag", capped=False)
    for section in core_config.CALIBRATE_SECTIONS:
        block = config["calibrate"][section]
        for i, term in enumerate(block["terms"]):
            if term["type"] != "A":
                continue
            fields = resolve_fields(
                term["field"] or block["field"], config, info, f"calibrate.{section}"
            )
            selected = _selected_rows(rows, fields, config["data"]["scans"])
            for (field, _, scan), idx in _groups(rows, selected).items():
                ntime = len(np.unique(rows["TIME"][idx]))
                if ntime > max_rows:
                    out.append(
                        f"calibrate.{section}.terms[{i}] ({term['name']}, A): field "
                        f"{info['fields'][field]!r} scan {scan} has {ntime} times, and "
                        "one baseline of it needs "
                        f"{plan.need_gb('flag', ntime * np.prod(info['cell'])):.2f} GiB; "
                        "raise data.memory_limit_gb"
                    )
    return out


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
        rows = core_chunks.budget(ctx["config"], ctx["info"]).rows("rows")
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
    journal = core_writeback.read_journal(ms)
    if journal and journal.get("state") in ("open", "failed"):
        raise Refused(f"{ms}: an unfinished write-back must be restored first")
    rows = core_chunks.budget(ctx["config"], ctx["info"]).rows("rows")
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
    columns = info["rows"]
    rows = _selected_rows(columns, fields, config["data"]["scans"])
    plan = core_chunks.budget(config, info)
    max_rows = plan.rows("flag")
    cells = int(np.prod(info["cell"]))
    groups, blocks, flagged_before = [], [], 0
    with writeback_session(ctx, "flag") as (w, written):
        for (field, ddid, scan), idx in _groups(columns, rows).items():
            # One group is one Tricolour window; when it does not fit, blocks
            # of its baselines on the group's time grid (research/w3-chunking.md).
            time_grid = np.unique(columns["TIME"][idx])
            ubl = core_flag.unique_baselines(
                columns["ANTENNA1"][idx], columns["ANTENNA2"][idx]
            )
            if len(idx) <= max_rows:
                parts = [idx]
            else:
                lookup = {(int(a), int(b)): k for k, (a, b) in enumerate(ubl)}
                bl = np.array(
                    [
                        lookup[(int(a), int(b))]
                        for a, b in zip(
                            columns["ANTENNA1"][idx], columns["ANTENNA2"][idx]
                        )
                    ],
                    np.int64,
                )
                parts = [
                    idx[np.isin(bl, chosen)]
                    for chosen in core_chunks.baseline_blocks(bl, len(ubl), max_rows)
                ]
            before = after = 0
            seconds = 0.0
            for block in parts:
                data = core_chunks.read_rows(w, cfg["column"], block)
                flag = core_chunks.read_rows(w, "FLAG", block)
                result = core_flag.flag_rows(
                    data,
                    flag,
                    columns["ANTENNA1"][block],
                    columns["ANTENNA2"][block],
                    columns["TIME"][block],
                    info["antenna_position"],
                    info["chan_freq"],
                    info["chan_width"],
                    info["corr_type"],
                    strategies,
                    masks=masks,
                    want_intensity=False,
                    want_stages=False,
                    time_grid=time_grid,
                )
                del data
                out = result["flags"]
                new = out if cfg["write"] == "replace" else (flag | out)
                before += int(flag.sum())
                after += int(new.sum())
                seconds += result["seconds"]
                core_chunks.write_rows(w, "FLAG", block, new)
                del flag, new, out, result
            blocks.append(len(parts))
            flagged_before += before
            groups.append(
                {
                    "field_id": field,
                    "field": info["fields"][field],
                    "ddid": ddid,
                    "scan": scan,
                    "rows": len(idx),
                    "flagged_before": before / (len(idx) * cells),
                    "flagged_after": after / (len(idx) * cells),
                    "core_seconds": seconds,
                }
            )
    # The whole FLAG in row order, read back: its hash and the fractions.
    selected = np.zeros(info["nrows"], bool)
    selected[rows] = True
    digest = hashlib.sha256()
    total_after = unselected = 0
    with core_ms.open_table(ms) as t:
        for start, n in flagversions.spans(info["nrows"], plan.rows("rows")):
            part = np.ascontiguousarray(t.getcol("FLAG", start, n))
            digest.update(part.tobytes())
            total_after += int(part.sum())
            unselected += int(part[~selected[start : start + n]].sum())
            del part
    total_before = unselected + flagged_before
    total_cells = info["nrows"] * cells
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
        "flagged_before": total_before / total_cells,
        "flagged_after": total_after / total_cells,
        "flag_sha256": digest.hexdigest(),
        **written,
        "chunking": {**plan.describe(), "blocks": blocks},
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


def partition_grid(info, idx, term):
    """Rows `idx` of one partition sorted stably by TIME, and their
    `solution_grid`: (order, time_bin, freq_bin, gain_time, gain_freq)."""
    times = info["rows"]["TIME"]
    order = idx[np.argsort(times[idx], kind="stable")]
    grid = solution_grid(
        times[order],
        info["cell"][0],
        info["chan_freq"],
        term["solint"],
        term["freqint"],
    )
    return (order, *grid)


def weight_column(info, weights_mode):
    """The weight column `calibrate` reads, or None for `uniform`:
    WEIGHT_SPECTRUM when row 0 has a cell of the DATA shape, else WEIGHT
    (gemclean tests only that row 0 reads; check_data refuses image then)."""
    if weights_mode == "uniform":
        return None
    return "WEIGHT_SPECTRUM" if info["weight_spectrum"] else "WEIGHT"


def _solve_inputs(source, rows, chans, info, weights_mode, model_source, model_column):
    """DATA, weights, FLAG, FLAG_ROW and the model of `rows` (in that order)
    and channels `chans` (a slice), read from `source` (a reader)."""
    nchan_all = info["cell"][0]
    whole = chans.start == 0 and chans.stop == nchan_all
    cut = None if whole else chans
    # Read in blocks so only the kept channels are held (core_chunks).
    block = (
        None if whole else max(1, len(rows) * (chans.stop - chans.start) // nchan_all)
    )
    data = core_chunks.read_rows(source, "DATA", rows, cut, block)
    column = weight_column(info, weights_mode)
    if column is None:
        weights = np.ones(data.shape, np.float32)
    elif column == "WEIGHT_SPECTRUM":
        weights = core_chunks.read_rows(source, column, rows, cut, block)
    else:
        per_row = core_chunks.read_rows(source, "WEIGHT", rows)
        weights = np.repeat(per_row[:, None, :], data.shape[1], axis=1)
        del per_row
    out = {
        "data": data,
        "weights": weights,
        "flag": core_chunks.read_rows(source, "FLAG", rows, cut, block),
        "flag_row": core_chunks.read_rows(source, "FLAG_ROW", rows),
    }
    if model_source == "column":
        out["model"] = core_chunks.read_rows(source, model_column, rows, cut, block)
    else:
        out["scalar_model"] = np.ones(data.shape[1], np.float64)
    return out


def _complex(inputs, info, rows, time_bin, freq_bin, ntime, nfreq, term, **settings):
    model = (
        {"model": inputs["model"]}
        if "model" in inputs
        else {"scalar_model": inputs["scalar_model"]}
    )
    a = info["rows"]
    return core.solve_complex(
        inputs["data"],
        inputs["weights"],
        inputs["flag"],
        inputs["flag_row"],
        a["ANTENNA1"][rows],
        a["ANTENNA2"][rows],
        time_bin,
        freq_bin,
        ntime_bins=ntime,
        nfreq_bins=nfreq,
        nant=len(info["antennas"]),
        stop_criterion=term["stop_criterion"],
        **{
            "max_iterations": term["max_iterations"],
            "stop_fraction": term["stop_fraction"],
            **settings,
        },
        **model,
    )


# A stop fraction no converged fraction reaches: the loop runs to its
# maximum (pass 1 and 2 of a chunked solve, research/w3-chunking.md 1.3).
NO_STOP = 2.0


def solve_partition(
    source,
    idx,
    info,
    term,
    weights_mode,
    model_source,
    model_column,
    max_cells=None,
    hard_cells=None,
):
    """One `complex` solve on rows `idx` of one field and scan, read from
    `source` (a reader). Rows are sorted stably by TIME first. Within
    `max_cells` cells (None: no limit; `hard_cells` the memory limit when
    `max_cells` is a `chunk_rows` cap) the partition is one solve; otherwise
    chunks of whole solution intervals (`core_chunks.solve_chunks`) are solved
    twice to replay the global stop test (pass 1 with the trace, pass 2 to the
    stop iteration), which gives the one-call result bit for bit. Returns
    (solution, time_bin, freq_bin, gain_time, gain_freq, chunking record)."""
    order, time_bin, freq_bin, gain_time, gain_freq = partition_grid(info, idx, term)
    ntime, nfreq = len(gain_time), len(gain_freq)
    nchan, ncorr = info["cell"]
    nant = len(info["antennas"])
    read = (info, weights_mode, model_source, model_column)
    if max_cells is None or len(order) * nchan * ncorr <= max_cells:
        inputs = _solve_inputs(source, order, slice(0, nchan), *read)
        solution = _complex(inputs, info, order, time_bin, freq_bin, ntime, nfreq, term)
        record = {"chunks": 1, "passes": 1}
        return solution, time_bin, freq_bin, gain_time, gain_freq, record
    chunks, largest = core_chunks.solve_chunks(
        time_bin, freq_bin, max_cells, ncorr, hard_cells
    )
    if chunks is None:
        raise core_chunks.MemoryLimitError(
            f"one solution interval holds {largest} cells, more than a chunk of "
            f"{max_cells}"
        )
    options = core.solve_options(None)
    if options.stop != "gain":
        raise StageFailed(
            f"a chunked solve replays the stop test 'gain' only; RANG_SOLVE_OPTIONS "
            f"sets stop={options.stop} (research/w3-chunking.md 1.3)"
        )

    def run(chunk, **settings):
        rows = order[chunk.rows]
        inputs = _solve_inputs(source, rows, chunk.chans, *read)
        sol = _complex(
            inputs,
            info,
            rows,
            time_bin[chunk.rows] - chunk.t0,
            freq_bin[chunk.chans] - chunk.f0,
            chunk.t1 - chunk.t0,
            chunk.f1 - chunk.f0,
            term,
            **settings,
        )
        del inputs
        return sol

    import tempfile

    totals = None
    with tempfile.TemporaryDirectory(prefix="rang-w3-trace-") as tmp:
        trace = Path(tmp) / "trace.json"
        for chunk in chunks:
            run(chunk, stop_fraction=NO_STOP, trace=str(trace))
            counts = np.array(core_chunks.trace_counts(trace), np.int64)
            trace.unlink()
            if counts.shape != (term["max_iterations"], 2):
                raise StageFailed(
                    f"chunked solve: the trace has {len(counts)} iterations, not "
                    f"{term['max_iterations']}"
                )
            totals = counts if totals is None else totals + counts
    stop, fraction = core_chunks.replay_stop(
        [tuple(int(v) for v in t) for t in totals],
        ntime * nfreq * nant,
        term["stop_fraction"],
    )
    gains = np.empty((ntime, nfreq, nant, 2, 2), np.complex128)
    flags = np.empty((ntime, nfreq, nant), np.int8)
    for chunk in chunks:
        sol = run(chunk, stop_fraction=NO_STOP, max_iterations=stop + 1, trace="")
        gains[chunk.t0 : chunk.t1, chunk.f0 : chunk.f1] = sol.gains
        flags[chunk.t0 : chunk.t1, chunk.f0 : chunk.f1] = sol.flags
    solution = core.ComplexSolution(gains, flags, stop + 1, fraction, options, None)
    record = {"chunks": len(chunks), "passes": 2, "largest_interval_cells": largest}
    return solution, time_bin, freq_bin, gain_time, gain_freq, record


def model_spec(model, config_path):
    """The `rang.calmodels` spec of `calibrate.model` (setjy, manual, lsm)."""
    from . import calmodels

    if model["source"] == "setjy":
        return calmodels.Standard(standard=model["standard"] or "Stevens-Reynolds 2016")
    if model["source"] == "manual":
        # I, Q, U, V and the polarisation keys as CASA's setjy (task C7a).
        return calmodels.Manual(
            list(model["flux_jy"]),
            float(model["reffreq_hz"]),
            tuple(model["spix"] or ()),
            polindex=model["polindex"] or (),
            polangle=model["polangle"] or (),
            rotmeas=model["rotmeas"] or 0.0,
        )
    return calmodels.SkyModel(str(_resolve_path(model["lsm"], config_path)))


def write_models(ctx):
    """MODEL_DATA of the primary section's fields from `calibrate.model`
    (C3a's `calmodels.set_model`, one session and flag backup). Returns the
    receipts, or None for unity and column models."""
    from . import calmodels

    config, info, ms = ctx["config"], ctx["info"], ctx["ms"]
    model = config["calibrate"]["model"]
    polcal = polcal_models(config, info)
    if model["source"] not in core_config.MODEL_SOURCES and not polcal:
        return None
    plan = core_chunks.budget(config, info)
    out = None
    with writeback_session(ctx, "calibrate") as (w, written):
        if model["source"] in core_config.MODEL_SOURCES:
            block = config["calibrate"]["primary"]
            fields = set()
            for term in block["terms"]:
                fields.update(
                    resolve_fields(
                        term["field"] or block["field"],
                        config,
                        info,
                        "calibrate.primary",
                    )
                )
            spec = model_spec(model, ctx["config_path"])
            receipt = calmodels.set_model(
                ms, sorted(fields), spec, session=w, chunk_rows=plan.rows("model")
            )
            out = {"spec": repr(spec), "fields": sorted(fields), "receipt": receipt}
        if polcal:
            # Task C6w: CARACal's nrao_xcal.yml model on the polcal fields
            # (Gpol, KCROSS, Xf), one field at a time.
            records = []
            for field, name in polcal:
                spec = calmodels.caracal_xcal(name)
                receipt = calmodels.set_model(
                    ms, [field], spec, session=w, chunk_rows=plan.rows("model")
                )
                records.append(
                    {
                        "field": field,
                        "name": name,
                        "spec": repr(spec),
                        "receipt": receipt,
                    }
                )
            out = dict(out or {}, polcal=records)
        out.update(written)
    return out


def polcal_fields(config, info):
    """FIELD ids of the polcal section's Gpol, KCROSS and Xf terms (the
    polarised calibrator; Df solves on the leakage calibrator)."""
    block = config["calibrate"]["polcal"]
    fields = set()
    for term in block["terms"]:
        if term["type"] in ("Gpol", "KCROSS", "Xf"):
            fields.update(
                resolve_fields(
                    term["field"] or block["field"], config, info, "calibrate.polcal"
                )
            )
    return sorted(fields)


def polcal_models(config, info):
    """[(field id, NRAO_XCAL name)] written by calibrate for
    `calibrate.polcal.model.source: nrao` (task C6w), else []."""
    pm = config["calibrate"]["polcal"]["model"]
    if pm["source"] != "nrao":
        return []
    return [(f, pm["name"] or info["fields"][f]) for f in polcal_fields(config, info)]


def solve_rows(config, info, section, term):
    """The rows a term solves on: its fields, `data.scans`, cross-correlations
    only (autocorrelations are left out of the solve, task W4, as C2a's)."""
    block = config["calibrate"][section]
    fields = resolve_fields(
        term["field"] or block["field"], config, info, f"calibrate.{section}"
    )
    columns = info["rows"]
    rows = _selected_rows(columns, fields, config["data"]["scans"])
    return fields, rows[columns["ANTENNA1"][rows] != columns["ANTENNA2"][rows]]


def uses_chain(config):
    """Whether calibrate runs CASA-style terms (K, G, B, A, F; task C2e)."""
    return any(
        term["type"] in core_config.CHAIN_TERMS
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
    terms += polcal_terms(config, info, types, primary_model)
    return terms


# The table kind each term writes (`caltable.CalTable.kind`), for the
# interpolation defaults of a polarisation term's pre-applied tables.
TABLE_KIND = {
    "K": "K",
    "G": "G",
    "B": "B",
    "F": "G",
    "Gpol": "G",
    "KCROSS": "Kcross",
    "Xf": "Xf",
    "Df": "Df",
}


def polcal_terms(config, info, types, primary_model):
    """`rang.cal_chain.run`'s terms for `calibrate.polcal` (task C6w,
    research/c6w-polwire.md): Gpol, KCROSS, Xf and Df in the order given,
    with CASA's defaults where the configuration is silent (`minsnr` 3,
    `minblperant` 4, `refantmode` flex), `uvrange` to all four (CARACal),
    `parang` true, Df's clip CARACal's 0.6 and KCROSS CASA's estimator. A
    pre-applied table without an `interp` gets CARACal's
    (`cal_apply.CARACAL_INTERP`: K, G, B, F, Gpol linear; KCROSS, Xf, Df
    nearest). Gpol, KCROSS and Xf solve against the polcal model
    (`calibrate.polcal.model`), Df against the primary's (the leakage
    calibrator is a primary field)."""
    from . import cal_apply

    cal = config["calibrate"]
    block = cal["polcal"]
    pm = block["model"]
    pol_column = "MODEL_DATA" if pm["source"] == "nrao" else pm["column"]
    angle = block["feed_angle_rotation"]
    receptor = None if angle is None else float(np.deg2rad(angle))
    primary_fields = set()
    for term in cal["primary"]["terms"]:
        primary_fields.update(
            resolve_fields(
                term["field"] or cal["primary"]["field"],
                config,
                info,
                "calibrate.primary",
            )
        )
    out = []
    for i, term in enumerate(block["terms"]):
        kind, name = term["type"], term["name"]
        fields = resolve_fields(
            term["field"] or block["field"], config, info, "calibrate.polcal"
        )

        def pick(key, default, term=term):
            value = term.get(key)
            if value is None:
                value = cal.get(key)
            return default if value is None else value

        interp = list(term["interp"]) or [
            cal_apply.CARACAL_INTERP[TABLE_KIND[types[n]]] for n in term["preapply"]
        ]
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
            "uvrange": pick("uvrange", ""),
            "preapply": list(term["preapply"]),
            "interp": interp,
            "parang": True if term.get("parang") is None else bool(term["parang"]),
            "frame": block["frame"],
            "receptor_angle": receptor,
        }
        if kind == "Df":
            written = cal["model"]["source"] in core_config.MODEL_SOURCES
            if written and not set(fields) <= primary_fields:
                raise Refused(
                    f"calibrate.polcal.terms[{i}] ({name}): Df solves on the leakage "
                    "calibrator against the primary's model, which is on the "
                    f"primary fields {sorted(primary_fields)}; give field: fcal"
                )
            spec["model"] = primary_model
            clip = term["clip"]
            spec["clip"] = 0.6 if clip is None else (float(clip[1]) if clip else None)
            spec["min_data_fraction"] = term["min_data_fraction"]
        else:
            spec["model"] = "column"
            spec["model_column"] = pol_column
        if kind == "KCROSS":
            spec["estimator"] = term["estimator"] or "casa"
        out.append(spec)
        types[name] = kind
    if block["extendflags"]:
        # Task E0: CARACal's flagdata mode=extend before the polcal solves, on
        # pol_calib (the Gpol, KCROSS, Xf fields), then leakage_calib (Df's).
        pol = [f for s in out if s["type"] != "Df" for f in s["fields"]]
        leak = [f for s in out if s["type"] == "Df" for f in s["fields"]]
        fields = list(dict.fromkeys(pol + [f for f in leak if f not in pol]))
        out.insert(0, {"type": "extend", "name": "extendflags", "fields": fields})
    return out


def stage_calibrate_chain(ctx):
    """calibrate with K, G, B, A and F terms (task C2e): models into
    MODEL_DATA on the primary fields, then `rang.cal_chain.run`, every write
    through the attempt's flag version."""
    config, info, ms, run = ctx["config"], ctx["info"], ctx["ms"], ctx["run"]
    # Task E0: refant auto becomes CARACal's names before anything is written.
    config, refant_auto = cal_refant.resolve_config(config, ms)
    cal = config["calibrate"]
    terms = chain_terms(config, info, ctx["config_path"])
    restored = restore_before(ms, ctx["entry"])
    out_dir = run.stage_dir("calibrate", fresh=True)
    models = write_models(ctx)
    written = cal["model"]["source"] in core_config.MODEL_SOURCES
    model_column = "MODEL_DATA" if written else cal["model"]["column"]
    if config["flag"]["static_masks"] == "tricolour":
        masks = [core_flag.load_static_mask(p) for p in core_flag.static_mask_files()]
    else:
        masks = []
    scans = config["data"]["scans"] or None
    version = stage_version(ctx, "calibrate")
    plan = core_chunks.budget(config, info)
    result = cal_chain.run(
        ms,
        terms,
        out_dir=out_dir,
        model_column=model_column,
        weight_column=chain_weight_column(config, info),
        scan=scans,
        masks=masks,
        chunk_rows=plan.rows("apply"),
        flag_backup=version,
        stage="calibrate",
        budget=plan,  # task W3b: chunks of whole solution intervals
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
        "chunking": {
            **plan.describe(),
            "solves": [
                {
                    "term": term["name"],
                    "field": info["fields"][f],
                    "chunks": len(chunks),
                    "channel_chunks": sum(not c.whole for c in chunks),
                }
                for _, term, f, chunks in chain_chunk_plans(config, info, plan)
            ],
        },
    }
    if refant_auto is not None:
        summary["refant_auto"] = refant_auto
    if cal["polcal"]["terms"]:
        summary["polcal"] = {
            "frame": cal["polcal"]["frame"],
            "feed_angle_rotation": cal["polcal"]["feed_angle_rotation"],
            "model": cal["polcal"]["model"],
            "defaults": "provisional (research/c6w-polwire.md): KCROSS per scan and "
            "CASA's estimator; Df's clip 0.6, no data-fraction rule",
        }
    _write_json(out_dir / "summary.json", summary)
    return summary


def stage_calibrate(ctx):
    config, info, ms, run = ctx["config"], ctx["info"], ctx["ms"], ctx["run"]
    if uses_chain(config):
        return stage_calibrate_chain(ctx)
    cal = config["calibrate"]
    plan = core_chunks.budget(config, info)
    max_cells = (plan.cells("calibrate"), plan.cells("calibrate", capped=False))
    restored = restore_before(ms, ctx["entry"])
    out_dir = run.stage_dir("calibrate", fresh=True)
    models = write_models(ctx)
    source, model_column = cal["model"]["source"], cal["model"]["column"]
    if models is not None:
        source, model_column = "column", "MODEL_DATA"
    tables, chunking = [], []
    reader = core_ms.open_table(ms)
    try:
        for section in core_config.CALIBRATE_SECTIONS:
            for term in cal[section]["terms"]:
                tables.append(
                    _solve_term(
                        ctx,
                        reader,
                        section,
                        term,
                        source,
                        model_column,
                        max_cells,
                        out_dir,
                        chunking,
                    )
                )
    finally:
        reader.close()
    summary = {
        "weights": config["data"]["weights"],
        "model": cal["model"]["source"],
        "models_written": models,
        "restored_before": restored,
        "tables": tables,
    }
    if models is not None:
        summary["flag_version"] = models["flag_version"]
    summary["chunking"] = {**plan.describe(), "partitions": chunking}
    _write_json(out_dir / "summary.json", summary)
    return summary


def _solve_term(
    ctx, reader, section, term, source, model_column, max_cells, out_dir, chunking
):
    """Solve one term on each of its partitions and write its gain store."""
    config, info = ctx["config"], ctx["info"]
    fields, rows = solve_rows(config, info, section, term)
    if not len(rows):
        raise StageFailed(f"calibrate.{section}: no rows in fields {fields}")
    parts, records = [], []
    for (field, ddid, scan), idx in _groups(info["rows"], rows).items():
        solution, _, _, gain_time, gain_freq, chunked = solve_partition(
            reader,
            idx,
            info,
            term,
            config["data"]["weights"],
            source,
            model_column,
            *max_cells,
        )
        chunking.append(
            {"term": term["name"], "field_id": field, "scan": scan, **chunked}
        )
        valid = (solution.flags == 0) & np.isfinite(solution.gains).all(axis=(-1, -2))
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
    return {
        "section": section,
        "name": term["name"],
        "type": term["type"],
        "store": str(store),
        "solint": term["solint"],
        "freqint": term["freqint"],
        "partitions": records,
    }


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
    plan = core_chunks.budget(config, info)
    # Task C6w: P after the tables (CASA's applycal parang=True), in the frame
    # and with the receptor angle the polarisation terms were solved with.
    parang = {}
    if cfg["parang"]:
        angle = config["calibrate"]["polcal"]["feed_angle_rotation"]
        parang = {
            "parang": True,
            "frame": config["calibrate"]["polcal"]["frame"],
            "receptor_angle": None if angle is None else float(np.deg2rad(angle)),
        }
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
                    chunk_rows=plan.rows("apply"),
                    scan=scans,
                    **parang,
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
                    chunk_rows=plan.rows("apply"),
                    input_column="DATA" if k == 0 else cfg["column"],
                )
                applied.append(result)
    summary = {
        "chunking": plan.describe(),
        "column": cfg["column"],
        "applymode": cfg["applymode"],
        "calwt": cfg["calwt"],
        "calwt_note": "a complex (general Jones) term does not scale weights, as CASA; "
        "of the CASA tables only G, B and T do (rang.applycal)",
        "parang": bool(cfg["parang"]),
        "restored_before": restored,
        "applied": applied,
        "warnings": warnings,
        **written,
    }
    _write_json(run.stage_dir("apply", fresh=True) / "summary.json", summary)
    return summary


class Gemclean:
    """The gemclean to run: `argv` (the command before gemclean's options),
    `path` (the file whose sha256 the receipt records) and `label`."""

    def __init__(self, argv, path, label):
        self.argv, self.path, self.label = list(argv), Path(path), label

    def __str__(self):
        return self.label


def find_gemclean(setting):
    """The gemclean to run (task G8, research/g8-wheel.md): `auto` is the
    extension's entry, `python -m rang.gemclean` of this interpreter, run as
    a subprocess and recorded by the sha256 of `rang._core`; any other value
    is the path of a gemclean binary (a source build). There is no search of
    PATH or of the checkout's core/target: a stale binary found silently
    would break the provenance."""
    if setting != "auto":
        path = Path(setting).expanduser()
        if not path.is_file():
            raise StageFailed(f"image.gemclean: {path} not found")
        return Gemclean([str(path)], path, str(path))
    if not hasattr(core.extension(), "gemclean_main"):
        raise StageFailed(
            f"image: the extension {core.library_path()} has no gemclean (built before "
            "task G8); rebuild it, or set image.gemclean to a gemclean binary"
        )
    argv = [sys.executable, "-m", "rang.gemclean"]
    return Gemclean(argv, core.library_path(), " ".join(argv))


def _safe(name):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def gemclean_arguments(img, column, field_id, prefix, ms, scans=(), unit_weights=False):
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
    if img["average_channels"] > 1:
        args += ["-average-channels", str(img["average_channels"])]
    if img["channels_out"] > 1:
        args += ["-channels-out", str(img["channels_out"])]
    if img["join_channels"]:
        args.append("-join-channels")
    if img["fit_spectral_pol"] is not None:
        args += ["-fit-spectral-pol", str(img["fit_spectral_pol"])]
    # Task G9: only when not the default, so earlier argv stay as they were.
    if img["pol"] != "I":
        args += ["-pol", img["pol"]]
    if img["join_polarizations"]:
        args.append("-join-polarizations")
    # Task G4 (research/g4-masks.md): only when set, so earlier argv stay as they were.
    for key, flag in (
        ("taper_gaussian", "-taper-gaussian"),
        ("taper_tukey", "-taper-tukey"),
        ("taper_inner_tukey", "-taper-inner-tukey"),
        ("minuv_l", "-minuv-l"),
        ("maxuv_l", "-maxuv-l"),
        ("minuvw_m", "-minuvw-m"),
        ("maxuvw_m", "-maxuvw-m"),
        ("fits_mask", "-fits-mask"),
        ("auto_mask", "-auto-mask"),
        ("abs_auto_mask", "-abs-auto-mask"),
        ("auto_mask_nmiter", "-auto-mask-nmiter"),
    ):
        if img.get(key) is not None:
            args += [flag, str(img[key])]
    if img["multiscale"]:
        args.append("-multiscale")
        if img["multiscale_scales"] is not None:
            scales = ",".join(repr(float(v)) for v in img["multiscale_scales"])
            args += ["-multiscale-scales", scales]
        for key, flag in (
            ("multiscale_max_scales", "-multiscale-max-scales"),
            ("multiscale_scale_bias", "-multiscale-scale-bias"),
            ("multiscale_gain", "-multiscale-gain"),
        ):
            if img[key] is not None:
                args += [flag, str(img[key])]
        if img["multiscale_shape"] != "tapered-quadratic":
            args += ["-multiscale-shape", img["multiscale_shape"]]
    args += ["-data-column", column, "-field", str(field_id)]
    # data.scans and data.weights: uniform (task W6, research/w6-imaging-inputs.md).
    if scans:
        args += ["-scans", ",".join(str(int(s)) for s in scans)]
    if unit_weights:
        args.append("-unit-weights")
    # gemclean never writes the MS itself here: MODEL_DATA, when asked for,
    # goes through WriteBack after it (task G6, research/g6-predict.md).
    args.append("-no-update-model-required")
    args += list(img["extra_args"])
    return [*args, str(ms)]


def _extra_flag(extra, flag, count=0):
    """The values of `flag` in gemclean's extra arguments (the last use),
    True for a flag without values, or None."""
    found = None
    for i, a in enumerate(extra):
        if a == flag:
            found = True if count == 0 else tuple(extra[i + 1 : i + 1 + count])
    return found


def _gridder_single(img, extra):
    """gemclean's gridder precision (task G7, research/g7-defaults.md): the
    last of -single and -double in the extra arguments, else single for an
    accuracy of 1e-5 or coarser."""
    last = None
    for a in extra:
        if a in ("-single", "-double"):
            last = a
    if last is not None:
        return last == "-single"
    return float(img["wgridder_accuracy"]) >= 1e-5


def write_model(img, ms, field_id, prefix, scans=()):
    """MODEL_DATA from the model images gemclean wrote for `field_id`
    (task G6): the binary's predictor, written through WriteBack."""
    extra = [str(a) for a in img["extra_args"]]
    rng = _extra_flag(extra, "-channel-range", 2)
    return core_model.write_model_data(
        ms,
        prefix,
        field_id,
        channels_out=img["channels_out"],
        channel_range=None if rng is None else (int(rng[0]), int(rng[1])),
        average_channels=img["average_channels"],
        epsilon=float(img["wgridder_accuracy"]),
        wgridding=_extra_flag(extra, "-no-wgridding") is None,
        single=_gridder_single(img, extra),
        scans=list(scans) or None,
        stage="image",
    )


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
        scans = config["data"]["scans"] or ()
        unit = config["data"]["weights"] == "uniform"
        argv = [
            *binary.argv,
            *gemclean_arguments(img, column, field, prefix, ms, scans, unit),
        ]
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
        model = None
        if img["write_model"]:
            started = time.perf_counter()
            model = write_model(img, ms, field, prefix, scans)
            model["wall_seconds"] = time.perf_counter() - started
        images.append(
            {
                "field_id": field,
                "field": name,
                "argv": argv,
                "wall_seconds": seconds,
                "files": {p.name: _sha256_file(p) for p in files},
                "model": model,
            }
        )
    summary = {
        "gemclean": str(binary),
        "gemclean_sha256": _sha256_file(binary.path),
        "column": column,
        "images": images,
    }
    _write_json(out_dir / "summary.json", summary)
    return summary


def selfcal_refant(config, info):
    """The reference antenna of selfcal (task C5): `selfcal.refant`, else
    `calibrate.refant`, else what an unset calibrate.refant means
    (`cal_refant.default_choice`), as an antenna index. `auto` is the first
    antenna of CARACal's choice (`cal_refant.caracal_refant`, which reads
    only the ANTENNA and OBSERVATION tables), so it is calibrate's first."""
    refant = config["selfcal"]["refant"] or config["calibrate"]["refant"]
    if refant is None:  # calibrate.refant unset: auto, else antenna 0 (task E2)
        refant = cal_refant.default_choice(config, info["ms"])[0][:1]
    if cal_refant.is_auto(refant):
        cal = config["calibrate"]
        try:
            choice = cal_refant.caracal_refant(
                info["ms"], cal["refant_maxdist"], cal["refant_minbase"]
            )
        except ValueError as exc:
            raise StageFailed(f"selfcal.refant: {exc}") from exc
        refant = [choice.names[0]]
    first = refant[0]
    if isinstance(first, str):
        if first not in info["antennas"]:
            raise StageFailed(f"selfcal.refant: no antenna named {first!r}")
        return info["antennas"].index(first)
    if not 0 <= int(first) < len(info["antennas"]):
        raise StageFailed(f"selfcal.refant: no antenna {first}")
    return int(first)


def _selfcal_input(ctx):
    """What makes `selfcal.input_column` hold the 1GC-corrected data (task
    C5), decided before anything is written: after this run's apply
    (finished since the last copy, or never copied) `apply.column` is to be
    copied into it; otherwise an existing column is used as it is (raises
    when there is none). Returns `(copy, record)`."""
    config, ms, run = ctx["config"], ctx["ms"], ctx["run"]
    source = config["apply"]["column"]
    target = config["selfcal"]["input_column"]
    columns = core_writeback.layout(ms)["columns"]
    apply_entry = run.state["stages"].get("apply", {})
    marker = run.path / "selfcal-input.json"
    copied = None
    if marker.is_file():
        copied = json.loads(marker.read_text(encoding="utf-8"))
    stamp = apply_entry.get("finished")
    fresh = apply_entry.get("status") == "done" and (
        target not in columns
        or copied is None
        or copied.get("apply_finished") != stamp
        or copied.get("column") != target
    )
    if fresh and source != target:
        if source not in columns:
            raise StageFailed(f"selfcal: {ms} has no {source} to copy into {target}")
        return True, {"column": target, "copied_from": source, "apply_finished": stamp}
    if target not in columns:
        raise StageFailed(
            f"selfcal.input_column: {ms} has no {target}; run apply in this run "
            f"directory (it is copied from {source}) or name an existing column"
        )
    return False, {"column": target, "previous_copy": copied}


def _copy_column(w, source, target):
    """`target` := `source` in every row, in chunks (task C5)."""

    def init(start, n):
        return np.asarray(w.read(source, start, n), np.complex64)

    if not w.ensure_column(target, init=init):
        for start, n in w.chunks():
            w.write(target, start, init(start, n))


def run_gemclean(binary, argv, log):
    """Run gemclean with `argv` (its first element the binary), its output
    in `log`; returns the wall time. Raises StageFailed on failure."""
    started = time.perf_counter()
    with log.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(" ".join(argv) + "\n")
        fh.flush()
        done = subprocess.run(argv, stdout=fh, stderr=subprocess.STDOUT, check=False)
    if done.returncode:
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
        raise StageFailed(
            f"gemclean exited {done.returncode}; {log}: " + " | ".join(tail)
        )
    return time.perf_counter() - started


def selfcal_round_term(config, k):
    """The term of round `k` (1-based): `selfcal.terms[k - 1]`, the last
    repeating (CARACal's `gain_matrix_type[num - 1 if len >= num else -1]`)."""
    terms = config["selfcal"]["terms"]
    return terms[min(k, len(terms)) - 1]


_GEMCLEAN_STOP = re.compile(
    r"(\d+) components, (\d+) major cycles,(?: \d+ resyncs,)? stop (\w+)"
)


def gemclean_stop(log):
    """The components, major cycles and stop reason of gemclean's last
    summary line in `log` (task C5b; reported, not acted on), or None."""
    found = None
    for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
        m = _GEMCLEAN_STOP.search(line)
        if m:
            found = {
                "components": int(m.group(1)),
                "major_cycles": int(m.group(2)),
                "stop": m.group(3),
            }
    return found


def _selfcal_image(ctx, binary, column, field, where, k):
    """Image `k` (1-based; rounds + 1 is the final image) of `field` from
    `column` in directory `where` (task C5), with that image's settings
    (`core_config.selfcal_image_settings`, task C5b): `(prefix, record)`."""
    config, ms = ctx["config"], ctx["ms"]
    img = core_config.selfcal_image_settings(config, k, ctx["info"]["fields"][field])
    scans = config["data"]["scans"] or ()
    unit = config["data"]["weights"] == "uniform"
    where.mkdir()
    prefix = where / img["name"]
    argv = [
        *binary.argv,
        *gemclean_arguments(img, column, field, prefix, ms, scans, unit),
    ]
    log = where / "gemclean.log"
    try:
        seconds = run_gemclean(binary, argv, log)
    except StageFailed as exc:
        name = ctx["info"]["fields"][field]
        raise StageFailed(f"selfcal: field {name}: {exc}") from exc
    files = sorted(p for p in where.iterdir() if p.is_file() and p != log)
    return prefix, {
        "image": k,
        "column": column,
        "argv": argv,
        "auto_threshold": img["auto_threshold"],
        "auto_mask": img["auto_mask"],
        "fits_mask": img["fits_mask"],
        "clean": gemclean_stop(log),
        "wall_seconds": seconds,
        "files": {p.name: _sha256_file(p) for p in files},
    }


def _selfcal_model(ctx, field, prefix, chunk_rows):
    """`selfcal.model_column` from the model images at `prefix` (task C5),
    with the predictor settings `write_model` takes from the image section."""
    config = ctx["config"]
    img = config["image"]
    extra = [str(a) for a in img["extra_args"]]
    rng = _extra_flag(extra, "-channel-range", 2)
    started = time.perf_counter()
    model = core_model.write_model_data(
        ctx["ms"],
        prefix,
        field,
        column=config["selfcal"]["model_column"],
        channels_out=img["channels_out"],
        channel_range=None if rng is None else (int(rng[0]), int(rng[1])),
        average_channels=img["average_channels"],
        epsilon=float(img["wgridder_accuracy"]),
        wgridding=_extra_flag(extra, "-no-wgridding") is None,
        single=_gridder_single(img, extra),
        scans=list(config["data"]["scans"]) or None,
        stage="selfcal",
        chunk_rows=chunk_rows,
    )
    model["wall_seconds"] = time.perf_counter() - started
    return model


def stage_selfcal(ctx):
    """CARACal's self-calibration rounds (task C5, research/c5-selfcal.md)
    on every field of `image.fields`: round k images (the input column in
    round 1, the output column after), predicts the model images into
    `selfcal.model_column` (`core_model.write_model_data`), solves round
    k's term on the input column against it (`rang.cal_selfcal.solve`,
    chunked within `data.memory_limit_gb`) and writes the output column
    from the input column corrected by it; a final image of the output
    column follows. Solutions are written as QuartiCal gain stores."""
    from . import cal_selfcal

    config, info, ms, run = ctx["config"], ctx["info"], ctx["ms"], ctx["run"]
    sc, img = config["selfcal"], config["image"]
    binary = find_gemclean(img["gemclean"])
    refant = selfcal_refant(config, info)
    scans = config["data"]["scans"] or ()
    weights = weight_column(info, config["data"]["weights"])
    plan = core_chunks.budget(config, info)
    copy, source = _selfcal_input(ctx)
    restored = restore_before(ms, ctx["entry"])
    out_dir = run.stage_dir("selfcal", fresh=True)
    written = {}
    if copy:
        with writeback_session(ctx, "selfcal") as (w, written):
            _copy_column(w, source["copied_from"], source["column"])
        _write_json(run.path / "selfcal-input.json", source)
    source["copied_now"] = copy
    fields = []
    for field in resolve_fields(img["fields"], config, info, "image.fields"):
        name = info["fields"][field]
        rows = _selected_rows(info["rows"], [field], scans)
        field_dir = out_dir / _safe(name)
        field_dir.mkdir()
        rounds = []

        for k in range(1, sc["rounds"] + 1):
            where = field_dir / f"round-{k}"
            column = sc["input_column"] if k == 1 else sc["output_column"]
            prefix, imaged = _selfcal_image(ctx, binary, column, field, where, k)
            model = _selfcal_model(ctx, field, prefix, plan.rows("model"))
            term = selfcal_round_term(config, k)
            started = time.perf_counter()
            sol = cal_selfcal.solve(
                ms,
                term,
                rows=rows,
                field_id=field,
                input_column=sc["input_column"],
                model_column=sc["model_column"],
                weight_column=weights,
                refant=refant,
                minuvw_m=sc["minuvw_m"],
                gain_clip=sc["gain_clip"],
                budget=plan.chain(),
            )
            solved = sol.summary()
            solved["wall_seconds"] = time.perf_counter() - started
            store = where / "gains.qc"
            cal_selfcal.to_store(sol, store, info["antennas"], field_name=name)
            started = time.perf_counter()
            with writeback_session(ctx, "selfcal") as (w, written):
                applied = cal_selfcal.apply(
                    w,
                    sol,
                    input_column=sc["input_column"],
                    output_column=sc["output_column"],
                    chunk_rows=plan.rows("apply"),
                )
            applied["wall_seconds"] = time.perf_counter() - started
            rounds.append(
                {
                    "round": k,
                    "image": imaged,
                    "model": model,
                    "term": dict(term),
                    "solve": solved,
                    "store": str(store),
                    "apply": applied,
                }
            )
        _, final = _selfcal_image(
            ctx,
            binary,
            sc["output_column"],
            field,
            field_dir / "final",
            sc["rounds"] + 1,
        )
        fields.append(
            {"field_id": field, "field": name, "rounds": rounds, "final_image": final}
        )
    summary = {
        "gemclean": str(binary),
        "gemclean_sha256": _sha256_file(binary.path),
        "chunking": plan.describe(),
        "rounds": sc["rounds"],
        "refant": refant,
        "input": source,
        "input_column": sc["input_column"],
        "model_column": sc["model_column"],
        "output_column": sc["output_column"],
        "restored_before": restored,
        "fields": fields,
        **written,
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
    "selfcal": stage_selfcal,
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
