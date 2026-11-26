# SPDX-License-Identifier: GPL-3.0-or-later
"""CARACal's cross-calibration chain in C1's order (research/c1-calibration-chain.md).

`primary(ms, ...)` (task C2c, research/c2c-bandpass.md part 3; C1 section
1.3, solve steps 1-3) solves, on one field:

1. K by `rang.cal_delay.gaincal` (`delay_and_offset` by default), nothing
   pre-applied and no `uvrange` (CARACal passes `uvrange` to G, B and
   polcal only);
2. G (`calmode='ap'`) by `rang.cal_gain.gaincal` with K pre-applied;
3. B by `rang.cal_bandpass.bandpass` with K and G pre-applied;

each with `interp='linear'`, and returns the three tables with their
solutions. The K table holds the delays only; G absorbs K's phase offsets.
This is CASA-style sequential calibration: no joint solve of the chain.

`run(ms, terms, ...)` (task C2e, research/c2e-calibrate.md) runs a whole
sequence of terms, as `rang-core calibrate` does and as CARACal's
`crosscal_worker.solve` orders them (C1 steps 1 to 8): K, G, B and F solves,
each with its listed tables pre-applied, and A steps. Every term is a dict
(`run`'s docstring); a term with several fields is solved per field and the
tables appended, as CASA's iteration over fields. F is CARACal's: G on the
secondary fields against `smodel`, appended to a copy of a primary G table,
then `fluxscale(reference=<that table's fields>, transfer='')`
(`rang.cal_fluxscale.bootstrap`). A is CARACal's `auto_flagging` with C1's
replacement O1: the section's last table of each type applied to its fields
(`rang.applycal.applycal`, `calflag`, CORRECTED_DATA), then the Tricolour
port on CORRECTED_DATA of those fields, its flags OR'd into FLAG.
`a_tables(...)` is CARACal's choice of tables for an A step
(`get_caltab_final` and `get_last_gain`).

Task C6w (research/c6w-polwire.md): `run` also solves CARACal's strategy-1
polarisation terms Gpol, KCROSS, Xf and Df (`rang.cal_pol`), Df's table
clipped as CARACal's `flagdata(mode='clip')`.

K tables hold delays only (C2c decision 2): a K table applied without a G
or F after it leaves K's phase offsets in the data, and `run` records a
warning wherever that happens.
"""

import copy
import hashlib
from pathlib import Path

import numpy as np

from . import (
    applycal,
    cal_bandpass,
    cal_delay,
    cal_fluxscale,
    cal_gain,
    cal_pol,
    core_flag,
    core_ms,
    core_writeback,
)
from .formats import caltable

SOLVED = ("K", "G", "B", "F")
POLARISATION = ("Gpol", "KCROSS", "Xf", "Df")  # task C6w, `rang.cal_pol`
K_ALONE = (
    "K applied without a later G or F: rang's K table holds the delays only and "
    "its phase offsets are left for G (research/c2c-bandpass.md, decision 2)"
)


# The solve types `run`'s `solve_calwt` takes (task calwt-terms).
CALWT_TYPES = frozenset({"K", "G", "Gpol", "KCROSS", "Df"})


def primary(
    ms,
    *,
    field_id=0,
    refant=0,
    k_solint="inf",
    g_solint="inf",
    b_solint="inf",
    k_combine="",
    g_combine="",
    b_combine="scan",
    uvrange="",
    minsnr=3.0,
    minblperant=4,
    fillgaps=0,
    refantmode="flex",
    k_kind="delay_and_offset",
    model_column="MODEL_DATA",
    model=None,
    max_iterations=50,
    stop_criterion=1e-7,
    stop_fraction=0.99,
):
    """K, G, B on one field of `ms`: returns `{"K": (table, sol, info),
    "G": ..., "B": ...}`. `uvrange` reaches G and B only."""
    common = {
        "field_id": field_id,
        "refant": refant,
        "model_column": model_column,
        "model": model,
        "max_iterations": max_iterations,
        "stop_criterion": stop_criterion,
        "stop_fraction": stop_fraction,
    }
    k = cal_delay.gaincal(ms, solint=k_solint, combine=k_combine, kind=k_kind, **common)
    g = cal_gain.gaincal(
        ms, solint=g_solint, combine=g_combine, calmode="ap", refantmode=refantmode,
        minsnr=minsnr, minblperant=minblperant, uvrange=uvrange, gaintable=[k[0]],
        interp="linear", **common,
    )  # fmt: skip
    b = cal_bandpass.bandpass(
        ms, solint=b_solint, combine=b_combine, refantmode=refantmode, minsnr=minsnr,
        minblperant=minblperant, fillgaps=fillgaps, uvrange=uvrange,
        gaintable=[k[0], g[0]], interp="linear", **common,
    )  # fmt: skip
    return {"K": k, "G": g, "B": b}


# -- the whole sequence (task C2e) --------------------------------------------------


def a_tables(history):
    """The tables an A step applies, as CARACal's `get_caltab_final` with
    `get_last_gain`: from `history`, the `(name, type)` pairs of the tables
    the section has pre-applied or solved so far in order, the last of each
    type; of G and F only the later one. Returns names in `history` order."""
    last = {}
    for i, (_, kind) in enumerate(history):
        last[kind] = i
    if "G" in last and "F" in last:
        del last["G" if last["F"] > last["G"] else "F"]
    return [history[i][0] for i in sorted(last.values())]


def k_alone(kinds):
    """Whether a list of applied table types holds K but no G or F."""
    kinds = set(kinds)
    return "K" in kinds and not ({"G", "F"} & kinds)


def _sha(table):
    """SHA-256 of a table's main cells (for summaries; gates read the files)."""
    digest = hashlib.sha256()
    for name in sorted(table.main):
        digest.update(name.encode())
        for cell in table.main[name]:
            if cell is None:
                digest.update(b"-")
            else:
                digest.update(np.ascontiguousarray(cell).tobytes())
    return digest.hexdigest()


def _rows_of(ms, field_id, scan):
    nrow, nchan = cal_fluxscale._field_rows(ms, field_id, 0, scan)
    return nrow, nchan


def _solve_one(ms, term, field_id, tables, common):
    """One K, G or B solve on one field: `(CalTable, solution, info)`."""
    kind = term["type"]
    kwargs = dict(common)
    kwargs.update(
        field_id=field_id,
        solint=term["solint"],
        combine=term["combine"],
        refant=term["refant"],
        refantmode=term["refantmode"],
        minsnr=term["minsnr"],
        minblperant=term["minblperant"],
        uvrange=term["uvrange"],
        gaintable=[tables[n]["table"] for n in term["preapply"]],
        interp=list(term["interp"]) or "linear",
        max_iterations=term["max_iterations"],
        stop_criterion=term["stop_criterion"],
        stop_fraction=term["stop_fraction"],
    )
    if term["model"] == "unit":
        nrow, nchan = _rows_of(ms, field_id, common.get("scan"))
        kwargs["model"] = cal_fluxscale.smodel_view(nrow, nchan)
    if kind != "G":
        kwargs.pop("average_freq", None)  # task E2: G-type solves only
        kwargs.pop("casa_phase_weights", None)  # task A3: G-type solves only
    kwargs.pop("xf_calwt", None)  # task xf-gap: Xf solves only
    if kind in kwargs.pop("solve_calwt", ()):
        kwargs["solve_calwt"] = True  # task calwt-terms: K and G solves
    if kind != "B":
        kwargs.pop("model_divided", None)  # task e2a-3b-diag: B solves only
    if kind != "K":
        kwargs.pop("zero_start", None)  # calchain-floor: K solves only
    if not kwargs["gaintable"]:
        kwargs["gaintable"] = ()
        kwargs["interp"] = "linear"
    if kind == "K":
        return cal_delay.gaincal(
            ms, kind=term.get("kind", "delay_and_offset"), **kwargs
        )
    if kind == "G":
        return cal_gain.gaincal(ms, calmode=term["calmode"], **kwargs)
    if kind == "B":
        return cal_bandpass.bandpass(ms, fillgaps=term["fillgaps"], **kwargs)
    raise ValueError(f"not a solved term: {kind}")


def _solve_pol(ms, term, field_id, tables, common):
    """One Gpol, KCROSS, Xf or Df solve on one field (task C6w,
    `rang.cal_pol`): `(CalTable, record)`."""
    kind = term["type"]
    gaintable = [tables[n]["table"] for n in term["preapply"]]
    kwargs = {
        "field_id": field_id,
        "solint": term["solint"],
        "combine": term["combine"],
        "uvrange": term["uvrange"],
        "gaintable": gaintable or (),
        "interp": (list(term["interp"]) or "linear") if gaintable else "linear",
        "frame": term.get("frame", "casa"),
        "receptor_angle": term.get("receptor_angle"),
        "model_column": term.get("model_column", common["model_column"]),
        "weight_column": common["weight_column"],
    }
    if "scan" in common:
        kwargs["scan"] = common["scan"]
    if common.get("budget") is not None:
        kwargs["budget"] = common["budget"]
    if common.get("average_time"):
        kwargs["average_time"] = True
    if kind == "Gpol" and common.get("average_freq"):
        kwargs["average_freq"] = True  # task E2: G-type solves only
    if kind == "Gpol" and common.get("casa_phase_weights"):
        kwargs["casa_phase_weights"] = True  # task A3: calmode p only
    if kind == "Xf" and common.get("xf_calwt"):
        kwargs["calwt"] = True  # task xf-gap: CASA's calwt solve weights
    if kind in common.get("solve_calwt", ()):
        kwargs["solve_calwt"] = True  # task calwt-terms: Gpol, KCROSS, Df
    if term["model"] == "unit":
        nrow, nchan = _rows_of(ms, field_id, common.get("scan"))
        kwargs["model"] = cal_fluxscale.smodel_view(nrow, nchan)
    record = {"field_id": int(field_id)}
    if kind == "Gpol":
        table, sol, info = cal_pol.gpol(
            ms,
            refant=term["refant"],
            refantmode=term["refantmode"],
            minsnr=term["minsnr"],
            minblperant=term["minblperant"],
            parang=term.get("parang", True),
            **kwargs,
        )
        record.update(_solution_record(sol, info, field_id))
        return table, record
    kwargs["parang"] = term.get("parang", True)
    if kind == "KCROSS":
        table, sol, ld = cal_pol.kcross(
            ms,
            refant=term["refant"],
            estimator=term.get("estimator", "casa"),
            **kwargs,
        )
        record.update(
            rows=len(ld.rows),
            intervals=len(ld.keys),
            delay_ns=[float(v) for v in sol.delay_ns],
            err_ns=[float(v) for v in sol.err_ns],
            estimator=sol.settings["estimator"],
        )
        return table, record
    if kind == "Xf":
        table, sol, ld = cal_pol.xf(ms, **kwargs)
        record.update(
            rows=len(ld.rows),
            intervals=len(ld.keys),
            flagged_fraction=float((~sol.ok).mean()),
        )
        return table, record
    if kind == "Df":
        table, sol, ld = cal_pol.df(
            ms,
            refant=term["refant"],
            minsnr=term["minsnr"],
            minblperant=term["minblperant"],
            min_data_fraction=term.get("min_data_fraction"),
            **kwargs,
        )
        record.update(
            rows=len(ld.rows),
            intervals=len(ld.keys),
            flagged_fraction=float(sol.flags.mean()),
            gauge_fixed=sol.gauge_fixed,
            data_fraction_flagged_channels=sol.settings.get(
                "data_fraction_flagged_channels", 0
            ),
        )
        return table, record
    raise ValueError(f"not a polarisation term: {kind}")


def _solution_record(sol, info, field_id):
    flags = np.asarray(sol.flags)
    out = {
        "field_id": int(field_id),
        "rows": int(info["rows"]),
        "intervals": len(info["intervals"]),
        "flagged_fraction": float(flags.mean()),
    }
    for key in ("iterations", "converged_fraction", "used_alternate_refant"):
        if hasattr(sol, key):
            value = getattr(sol, key)
            out[key] = value if isinstance(value, (bool, int, float)) else str(value)
    if "solver_flags" in info:  # issue #58
        out["solver_flags"] = info["solver_flags"]
    settings = getattr(sol, "settings", None) or {}
    if "zero_start_intervals" in settings:  # research/k-ambiguity.md
        out["zero_start_intervals"] = [int(i) for i in settings["zero_start_intervals"]]
    if settings.get("half_period_delays"):  # research/k-ambiguity.md
        out["half_period_delays"] = settings["half_period_delays"]
    return out


def flag_corrected(
    ms,
    fields,
    strategies,
    *,
    masks=None,
    scan=None,
    column="CORRECTED_DATA",
    chunk_rows=None,
    flag_backup=core_writeback.DEFAULT_BACKUP,
    stage="calibrate",
    max_rows=None,
):
    """C1's O1: the Tricolour port (`core_flag.flag_rows`) on `column` of the
    rows of `fields` (and `scan`), per field, data description and scan as
    Tricolour groups them; the result OR'd into FLAG. Returns a summary.
    `max_rows` (task W3b, research/w3b-chainchunks.md): a group with more
    rows is flagged in blocks of consecutive baselines on the group's time
    grid, as `rang-core flag` (task W3), with the same flags."""
    from . import core_chunks

    ms = Path(ms)
    lay = core_writeback.layout(ms)
    with core_ms.open_table(ms / "ANTENNA") as t:
        positions = np.asarray(t.getcol("POSITION"), np.float64)
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        chan_freq = np.asarray(t.getcol("CHAN_FREQ", 0, 1)[0], np.float64)
        chan_width = np.asarray(t.getcol("CHAN_WIDTH", 0, 1)[0], np.float64)
    corr = np.asarray(lay["corr_type"], np.int32)
    cells = int(np.prod(lay["cell"]))
    names = ("FIELD_ID", "DATA_DESC_ID", "SCAN_NUMBER", "ANTENNA1", "ANTENNA2", "TIME")
    groups, blocks = [], []
    total_before = total_after = 0
    with core_writeback.WriteBack(
        ms, flag_backup=flag_backup, stage=stage, chunk_rows=chunk_rows
    ) as w:
        spans = list(w.chunks(chunk_rows))
        meta = {k: np.concatenate([w.read(k, s, n) for s, n in spans]) for k in names}
        keep = np.isin(meta["FIELD_ID"], list(fields))
        if scan is not None:
            keep &= np.isin(meta["SCAN_NUMBER"], [int(s) for s in np.atleast_1d(scan)])
        rows = np.flatnonzero(keep)
        key = np.stack(
            [
                meta["FIELD_ID"][rows],
                meta["DATA_DESC_ID"][rows],
                meta["SCAN_NUMBER"][rows],
            ],
            axis=1,
        )
        uniq, inverse = (
            np.unique(key, axis=0, return_inverse=True)
            if len(rows)
            else (np.zeros((0, 3), int), np.zeros(0, int))
        )
        inverse = np.asarray(inverse).reshape(-1)
        for i, (fid, ddid, sc) in enumerate(uniq):
            idx = rows[inverse == i]
            time_grid = None
            if max_rows is None or len(idx) <= max_rows:
                parts = [idx]
            else:
                time_grid = np.unique(meta["TIME"][idx])
                ubl = core_flag.unique_baselines(
                    meta["ANTENNA1"][idx], meta["ANTENNA2"][idx]
                )
                lookup = {(int(a), int(b)): k for k, (a, b) in enumerate(ubl)}
                bl = np.array(
                    [
                        lookup[(int(a), int(b))]
                        for a, b in zip(meta["ANTENNA1"][idx], meta["ANTENNA2"][idx])
                    ],
                    np.int64,
                )
                parts = [
                    idx[np.isin(bl, chosen)]
                    for chosen in core_chunks.baseline_blocks(bl, len(ubl), max_rows)
                ]
            before = after = 0
            for block in parts:
                data = core_chunks.read_rows(w, column, block)
                flag = np.asarray(core_chunks.read_rows(w, "FLAG", block), bool)
                result = core_flag.flag_rows(
                    data,
                    flag,
                    meta["ANTENNA1"][block],
                    meta["ANTENNA2"][block],
                    meta["TIME"][block],
                    positions,
                    chan_freq,
                    chan_width,
                    corr,
                    strategies,
                    masks=masks,
                    want_intensity=False,
                    want_stages=False,
                    time_grid=time_grid,
                )
                del data
                new = flag | result["flags"]
                before += int(flag.sum())
                after += int(new.sum())
                core_chunks.write_rows(w, "FLAG", block, new)
                del flag, new, result
            blocks.append(len(parts))
            total_before += before
            total_after += after
            groups.append(
                {
                    "field_id": int(fid),
                    "ddid": int(ddid),
                    "scan": int(sc),
                    "rows": len(idx),
                    "flagged_before": before / (len(idx) * cells),
                    "flagged_after": after / (len(idx) * cells),
                }
            )
    # FLAG of the selected rows in row order, read back after the write: the
    # hash of the flags written (task W3b; before, of the array in memory).
    digest = hashlib.sha256()
    step = max(1, int(chunk_rows or len(rows) or 1))
    with core_ms.open_table(ms) as t:
        for b in range(0, len(rows), step):
            for start, n in core_chunks.runs(rows[b : b + step]):
                digest.update(
                    np.ascontiguousarray(t.getcol("FLAG", start, n)).tobytes()
                )
    n_cells = len(rows) * cells
    out = {
        "column": column,
        "fields": sorted(int(f) for f in fields),
        "rows": len(rows),
        "flagged_before": total_before / n_cells if len(rows) else 0.0,
        "flagged_after": total_after / n_cells if len(rows) else 0.0,
        "groups": groups,
        "flag_sha256": digest.hexdigest(),
    }
    if max_rows is not None:
        out["chunking"] = {"max_rows": int(max_rows), "blocks": blocks}
    return out


# -- chunk tasks of the chain (research/chunk-task-api-1b.md 1.2) -------------------

SOLVERS = {"solve_one": "_solve_one", "solve_pol": "_solve_pol"}


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return [_jsonable(v) for v in sorted(value)]
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def recipe(fn, ms, term, field_id, tables, common):
    """A JSON-able description of one `_solve_one` or `_solve_pol` call (`fn`
    `solve_one` or `solve_pol`) that a worker runs with the parent's code:
    the term, the field, the earlier tables by their paths (every table is
    written before the next term starts) and `common` with its
    `ChainBudget` as numbers. None when the call cannot be described so (a
    pre-applied table without a path, or a term or setting that does not
    survive JSON unchanged)."""
    import dataclasses
    import json

    used = {n: tables[n] for n in term.get("preapply", ())}
    if any(not t.get("path") for t in used.values()):
        return None
    common = dict(common)
    budget = common.pop("budget", None)
    out = {
        "fn": fn,
        "ms": str(ms),
        "term": _jsonable(term),
        "field": int(field_id),
        "tables": {
            n: {"path": str(t["path"]), "type": t["type"]} for n, t in used.items()
        },
        "common": _jsonable(common),
        "budget": None if budget is None else dataclasses.asdict(budget),
        "solve_calwt": "solve_calwt" in common,
    }
    # The worker must see what the parent sees: values that JSON changes
    # (tuples become lists, non-string keys strings) are refused here.
    if json.loads(json.dumps(out["term"])) != term or (
        json.loads(json.dumps(out["common"]))
        != {k: (sorted(v) if k == "solve_calwt" else v) for k, v in common.items()}
    ):
        return None
    return out


def from_recipe(r, read_table):
    """`(fn, ms, term, field_id, tables, common)` of a recipe; `read_table`
    reads a table from its path."""
    from . import core_chunks

    common = dict(r["common"])
    if r["solve_calwt"]:
        common["solve_calwt"] = frozenset(common["solve_calwt"])
    if r["budget"] is not None:
        common["budget"] = core_chunks.ChainBudget(**r["budget"])
    tables = {
        n: {"table": read_table(t["path"]), "type": t["type"], "path": t["path"]}
        for n, t in r["tables"].items()
    }
    fn = globals()[SOLVERS[r["fn"]]]
    return fn, Path(r["ms"]), r["term"], int(r["field"]), tables, common


def _solve_fields(fn_name, ms, term, tables, common, executor):
    """The results of `fn_name` (`solve_one` or `solve_pol`) on every field of
    `term`, in field order: here, each field's replayed solve sent to
    `executor` by chunk (`cal_chunks.Dispatch`); or, for two fields or more
    and an executor that is not inline, each field one `chain-field` task."""
    from . import cal_chunks, core_tasks

    fn = globals()[SOLVERS[fn_name]]
    fields = list(term["fields"])
    pooled = executor is not None and not executor.inline
    recipes = [
        recipe(fn_name, ms, term, f, tables, common) if pooled else None for f in fields
    ]
    if pooled and len(fields) > 1 and all(r is not None for r in recipes):
        specs = [core_tasks.chain_field_spec(r, i) for i, r in enumerate(recipes)]
        return list(executor.map(specs))
    out = []
    for f, r in zip(fields, recipes):
        d = None if r is None else cal_chunks.Dispatch(executor, r)
        with cal_chunks.dispatching(d):
            out.append(fn(ms, term, f, tables, common))
    return out


def run(
    ms,
    terms,
    *,
    out_dir,
    model_column="MODEL_DATA",
    weight_column="WEIGHT_SPECTRUM",
    scan=None,
    masks=None,
    chunk_rows=None,
    flag_backup=core_writeback.DEFAULT_BACKUP,
    stage="calibrate",
    log=None,
    budget=None,
    average_time=False,
    average_freq=False,
    casa_phase_weights=False,
    bandpass_model_divided=False,
    k_zero_start=False,
    xf_calwt=False,
    solve_calwt=(),
    executor=None,
    solver_flags=None,
):
    """Run `terms` in order on `ms`, writing each table to `out_dir/<name>`.

    Every term is a dict with `type` (K, G, B, F or A), `name`, `fields`
    (MS field ids) and, for K, G, B and F: `solint`, `combine`, `refant`,
    `refantmode`, `minsnr`, `minblperant`, `uvrange`, `preapply` (names of
    earlier terms), `interp` (one per pre-applied table, or empty for
    linear), `max_iterations`, `stop_criterion`, `stop_fraction` and
    `model` (`"column"`: `model_column`; `"unit"`: CASA's `smodel=[1,0,0,0]`);
    G and F `calmode`; B `fillgaps`; K optionally `kind`; F `base` (the G
    table copied, CARACal's primary G) and `smodel`. A has `tables` (names,
    see `a_tables`), `gainfield` (one per table) and `strategies` (parsed
    Tricolour steps). Gpol, KCROSS, Xf and Df (task C6w, `rang.cal_pol`,
    research/c6w-polwire.md) have the K, G, B keys (KCROSS and Xf ignore
    `refant`, Xf `minsnr` and `minblperant`) and `parang`, `frame`,
    `receptor_angle` and optionally `model_column` (overrides
    `model_column`); KCROSS `estimator`; Df `clip` (an amplitude, or None)
    and `min_data_fraction`. An `extend` term (task E0, `rang.flag_extend`)
    has `fields` and optionally `settings`. `weight_column` (None for unit weights) and `scan`
    reach every solve and A step. Every MS write goes through
    `core_writeback.WriteBack` with `flag_backup` (saved once, before the
    first write). `budget` (task W3b, research/w3b-chainchunks.md): a
    `core_chunks.Budget`; every solve then reads its field in chunks of
    whole solution intervals and every A step flags in blocks of baselines
    within it, with the result of the one-call run. `average_time` (task
    E2, `calibrate.average_time`): every K, G, B, F, Gpol, KCROSS, Xf and
    Df solve is on its data and model averaged in time within each solution
    interval (CASA's pre-averaging, `rang.cal_chunks.load_averaged`); the A
    steps are unchanged. `average_freq` (task E2, `calibrate.average_freq`):
    every G, F and Gpol solve is on its data and model averaged over the
    window's channels (`rang.cal_gain.frequency_averaged`, CASA's G-type
    estimator); K, B, KCROSS, Xf and Df are unchanged.
    `casa_phase_weights` (task A3, `calibrate.casa_phase_weights`, needs
    `average_freq`): every calmode `p` G and Gpol solve uses CASA's
    phase-only datum (`rang.cal_gain.gaincal`). `bandpass_model_divided`
    (task e2a-3b-diag, `calibrate.bandpass_model_divided`,
    research/e2a-3b-diag.md): every B solve divides the pre-applied data by
    the (corrupted) model before any average (`rang.cal_bandpass.bandpass`
    `model_divided`). `k_zero_start` (`calibrate.k_zero_start`,
    research/calchain-floor.md section 12): every K solve also runs from a
    zero start and keeps, per interval, the run with the lower residual
    (`rang.cal_delay.solve` `zero_start`). `xf_calwt` (`calibrate.xf_calwt`,
    research/xf-gap.md section 7): every Xf solve weights its cells as
    CASA's `calwt` scales them by the pre-applied tables
    (`rang.cal_pol.load`'s `calwt`). `solve_calwt` (task calwt-terms,
    research/calwt-terms.md; `calibrate.k_calwt`, `g_calwt`, `gpol_calwt`,
    `kcross_calwt`, `df_calwt`): the solve types of `CALWT_TYPES` whose
    weights are scaled by CASA's `calwt` factor of the tables that correct
    their data (`rang.cal_gain.calwt_factor`; F is not). `executor` (a
    `rang.core_tasks.Executor`; default inline): the K, G, B and
    polarisation solves go through it by chunk or by field
    (research/chunk-task-api-1b.md 1.2), with the same tables.
    `solver_flags` (issue #58, `calibrate.solver_flags`, research/solver-flags.md):
    when its mode is not off, every G and B solve of the types in its
    `terms` runs flag passes on its residual and re-solves
    (`rang.solver_flags.rounds`), the flags OR-ed into FLAG as the solve
    goes; each solution record carries the passes. Returns
    `{"tables": {name: {...}}, "steps": [...]}`."""
    ms = Path(ms)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    say = log or (lambda text: None)
    tables, steps = {}, []
    common = {"model_column": model_column, "weight_column": weight_column}
    if scan is not None:
        common["scan"] = [int(s) for s in np.atleast_1d(scan)]
    if budget is not None:
        common["budget"] = budget.chain()
    if average_time:
        common["average_time"] = True
    if average_freq:
        common["average_freq"] = True
    if casa_phase_weights:
        if not average_freq:
            raise ValueError("casa_phase_weights needs average_freq")
        common["casa_phase_weights"] = True
    if bandpass_model_divided:
        common["model_divided"] = True
    if k_zero_start:
        common["zero_start"] = True
    if xf_calwt:
        common["xf_calwt"] = True
    solve_calwt = frozenset(solve_calwt)
    if solve_calwt - CALWT_TYPES:
        raise ValueError(f"solve_calwt takes {sorted(CALWT_TYPES)}")
    if solve_calwt:
        common["solve_calwt"] = solve_calwt
    sf = None
    if solver_flags is not None and solver_flags.get("mode", "off") != "off":
        from . import solver_flags as _sf

        if executor is not None and not executor.inline:
            raise ValueError("solver_flags: data.processes 1 only")
        sf = {
            "cfg": dict(solver_flags),
            "write": _sf.or_writer(
                ms, flag_backup=flag_backup, stage=stage, chunk_rows=chunk_rows
            ),
        }
    for term in terms:
        kind, name = term["type"], term["name"]
        say(f"{kind} {name} on fields {term['fields']}")
        step = {"type": kind, "name": name, "fields": list(term["fields"])}
        if kind in ("K", "G", "B"):
            made, records = [], []
            use = common
            if sf is not None and _sf.selects(sf["cfg"]["terms"], kind, name):
                use = {**common, "solver_flags": sf}
            solved = _solve_fields("solve_one", ms, term, tables, use, executor)
            for f, (table, sol, info) in zip(term["fields"], solved):
                made.append(table)
                records.append(_solution_record(sol, info, f))
            table = (
                cal_fluxscale.append(made[0], *made[1:]) if len(made) > 1 else made[0]
            )
            step["solutions"] = records
        elif kind == "F":
            base = copy.deepcopy(tables[term["base"]]["table"])
            kwargs = dict(common)
            kwargs.update(
                solint=term["solint"],
                combine=term["combine"],
                calmode=term["calmode"],
                refant=term["refant"],
                refantmode=term["refantmode"],
                minsnr=term["minsnr"],
                minblperant=term["minblperant"],
                uvrange=term["uvrange"],
                gaintable=[tables[n]["table"] for n in term["preapply"]] or (),
                interp=list(term["interp"]) or "linear",
                max_iterations=term["max_iterations"],
                stop_criterion=term["stop_criterion"],
                stop_fraction=term["stop_fraction"],
            )
            kwargs.pop("model_column")
            kwargs.pop("model_divided", None)  # task e2a-3b-diag: B solves only
            kwargs.pop("zero_start", None)  # calchain-floor: K solves only
            kwargs.pop("xf_calwt", None)  # task xf-gap: Xf solves only
            kwargs.pop("solve_calwt", None)  # task calwt-terms: not F
            table, record, merged = cal_fluxscale.bootstrap(
                ms,
                base,
                term["fields"],
                smodel=tuple(term.get("smodel") or cal_fluxscale.SMODEL_UNIT),
                **kwargs,
            )
            caltable.write(merged, out_dir / f"{name}.append")
            step["base"] = term["base"]
            step["fluxscale"] = cal_fluxscale.summary(record)
            step["append_table"] = str(out_dir / f"{name}.append")
        elif kind == "A":
            names = list(term["tables"])
            applied = [tables[n]["table"] for n in names]
            kinds = [tables[n]["type"] for n in names]
            summary = applycal.applycal(
                ms,
                applied,
                interp=["linear"] * len(applied),
                gainfield=list(term["gainfield"]),
                calwt=[False],
                field=list(term["fields"]),
                applymode="calflag",
                column="CORRECTED_DATA",
                chunk_rows=chunk_rows,
                flag_backup=flag_backup,
                stage=stage,
                scan=common.get("scan"),
            )
            flagged = flag_corrected(
                ms,
                term["fields"],
                term["strategies"],
                masks=masks,
                scan=common.get("scan"),
                chunk_rows=chunk_rows,
                flag_backup=flag_backup,
                stage=stage,
                max_rows=None if budget is None else budget.rows("flag"),
            )
            step.update(
                tables=names,
                gainfield=list(term["gainfield"]),
                applied=summary,
                flagged=flagged,
            )
            if k_alone(kinds):
                step["warning"] = K_ALONE
            steps.append(step)
            continue
        elif kind == "extend":
            # Task E0: CARACal's flagdata mode=extend (rang.flag_extend).
            from . import flag_extend

            step["extended"] = flag_extend.extend_ms(
                ms,
                term["fields"],
                scans=common.get("scan"),
                settings=term.get("settings"),
                chunk_rows=chunk_rows,
                flag_backup=flag_backup,
                stage=stage,
            )
            steps.append(step)
            continue
        elif kind in POLARISATION:
            made, records = [], []
            solved = _solve_fields("solve_pol", ms, term, tables, common, executor)
            for table, record in solved:
                made.append(table)
                records.append(record)
            table = (
                cal_fluxscale.append(made[0], *made[1:]) if len(made) > 1 else made[0]
            )
            step["solutions"] = records
            step["frame"] = term.get("frame", "casa")
            if kind == "Df" and term.get("clip") is not None:
                table, clipped = cal_pol.clip_df(table, term["clip"])
                step["clip"] = term["clip"]
                step["clipped"] = clipped
        else:
            raise ValueError(f"term {name}: type {kind} is not run by cal_chain.run")
        path = out_dir / name
        caltable.write(table, path)
        tables[name] = {
            "table": table,
            "type": kind,
            "fields": list(term["fields"]),
            "path": str(path),
        }
        step.update(
            path=str(path), table_sha256=_sha(table), rows=len(table.main["TIME"])
        )
        steps.append(step)
    return {"tables": tables, "steps": steps}


__all__ = [
    "K_ALONE",
    "POLARISATION",
    "SOLVED",
    "a_tables",
    "flag_corrected",
    "k_alone",
    "primary",
    "run",
]
