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
as Tricolour groups rows), `calibrate` (the `complex` term,
`core.solve_complex`, one solve per field and scan, written as a QuartiCal
gain store) and `image` (`gemclean` on a data column). `apply` and `selfcal`
are refused by `core_config.refusals` (C4, C5 and G6).
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

from . import core, core_config, core_flag, core_ms, core_writeback
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


def inspect_ms(ms):
    """What the stages need to know of `ms`, or Refused naming W4 for a
    layout W2 does not handle."""
    ms = Path(ms)
    if not (ms / "table.dat").is_file():
        raise Refused(f"{ms} is not a Measurement Set (no table.dat)")
    try:
        layout = core_writeback.layout(ms)
    except core_writeback.UnsupportedLayout as exc:
        raise Refused(f"{exc} (unsupported layouts are task W4)") from exc
    with core_ms.open_table(ms) as t:
        ddids = np.unique(t.getcol("DATA_DESC_ID"))
        field_ids = np.unique(t.getcol("FIELD_ID"))
        scans = np.unique(t.getcol("SCAN_NUMBER"))
    if len(ddids) != 1:
        raise Refused(
            f"{ms} uses {len(ddids)} data descriptions {ddids.tolist()}; W2 reads "
            "one spectral window and polarisation setup (task W4)"
        )
    corr = tuple(int(c) for c in layout["corr_type"])
    if corr != LINEAR:
        raise Refused(
            f"{ms} has correlations {list(corr)}; W2 needs XX, XY, YX, YY (task W4)"
        )
    ddid = int(ddids[0])
    with core_ms.open_table(ms / "DATA_DESCRIPTION") as dd:
        spw = int(dd.getcol("SPECTRAL_WINDOW_ID")[ddid])
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as sw:
        chan_freq = np.asarray(sw.getcol("CHAN_FREQ", spw, 1)[0], np.float64)
        chan_width = np.asarray(sw.getcol("CHAN_WIDTH", spw, 1)[0], np.float64)
    with core_ms.open_table(ms / "ANTENNA") as an:
        positions = np.asarray(an.getcol("POSITION"), np.float64)
        antennas = [str(n) for n in an.getcol("NAME")]
    with core_ms.open_table(ms / "FIELD") as fd:
        names = [str(n) for n in fd.getcol("NAME")]
    return {
        "ms": ms,
        "nrows": layout["nrows"],
        "cell": layout["cell"],
        "columns": sorted(layout["columns"]),
        "ddid": ddid,
        "spw": spw,
        "chan_freq": chan_freq,
        "chan_width": chan_width,
        "corr_type": np.asarray(corr, np.int32),
        "antenna_position": positions,
        "antennas": antennas,
        "fields": names,
        "field_ids_in_use": field_ids.tolist(),
        "scans": scans.tolist(),
    }


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


def preflight(config, info, stages):
    """Resolve every field list the stages use before anything is written."""
    problems = []
    lists = []
    if "flag" in stages:
        lists.append(("flag.fields", config["flag"]["fields"]))
    if "calibrate" in stages:
        for section in core_config.CALIBRATE_SECTIONS:
            block = config["calibrate"][section]
            for i, term in enumerate(block["terms"]):
                lists.append(
                    (
                        f"calibrate.{section}.terms[{i}].field",
                        term["field"] or block["field"],
                    )
                )
    if "image" in stages:
        lists.append(("image.fields", config["image"]["fields"]))
    for where, tokens in lists:
        try:
            resolve_fields(tokens, config, info, where)
        except Refused as exc:
            problems.append(str(exc))
    if "calibrate" in stages:
        model = config["calibrate"]["model"]
        if model["source"] == "column" and model["column"] not in info["columns"]:
            problems.append(
                f"calibrate.model.column: {info['ms']} has no {model['column']} "
                "(calibrator models are task C3a, MODEL_DATA from the imager G6)"
            )
    if problems:
        raise Refused("\n".join(problems))


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
        names.append(
            "WEIGHT_SPECTRUM" if "WEIGHT_SPECTRUM" in info["columns"] else "WEIGHT"
        )
    model = config["calibrate"]["model"]
    if model["source"] == "column":
        names.append(model["column"])
    return names


def stage_calibrate(ctx):
    config, info, ms, run = ctx["config"], ctx["info"], ctx["ms"], ctx["run"]
    cal = config["calibrate"]
    out_dir = run.stage_dir("calibrate", fresh=True)
    columns = _read_columns(ms, calibration_columns(info, config), info["nrows"])
    tables = []
    for section in core_config.CALIBRATE_SECTIONS:
        block = cal[section]
        for term in block["terms"]:
            fields = resolve_fields(
                term["field"] or block["field"], config, info, f"calibrate.{section}"
            )
            rows = _selected_rows(columns, fields, config["data"]["scans"])
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
                    cal["model"]["source"],
                    cal["model"]["column"],
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
        "tables": tables,
    }
    _write_json(out_dir / "summary.json", summary)
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
    if column not in info["columns"]:
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
    "apply": _refused_stage("C4"),
    "image": stage_image,
    "selfcal": _refused_stage("C5a"),
}
WRITES_FLAGS = frozenset({"flag", "apply", "selfcal"})


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
