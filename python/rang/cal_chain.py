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
        kwargs["model"] = cal_fluxscale.smodel_array(nrow, nchan)
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
    if term["model"] == "unit":
        nrow, nchan = _rows_of(ms, field_id, common.get("scan"))
        kwargs["model"] = cal_fluxscale.smodel_array(nrow, nchan)
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
):
    """C1's O1: the Tricolour port (`core_flag.flag_rows`) on `column` of the
    rows of `fields` (and `scan`), per field, data description and scan as
    Tricolour groups them; the result OR'd into FLAG. Returns a summary."""
    ms = Path(ms)
    lay = core_writeback.layout(ms)
    with core_ms.open_table(ms / "ANTENNA") as t:
        positions = np.asarray(t.getcol("POSITION"), np.float64)
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        chan_freq = np.asarray(t.getcol("CHAN_FREQ", 0, 1)[0], np.float64)
        chan_width = np.asarray(t.getcol("CHAN_WIDTH", 0, 1)[0], np.float64)
    corr = np.asarray(lay["corr_type"], np.int32)
    names = ("FIELD_ID", "DATA_DESC_ID", "SCAN_NUMBER", "ANTENNA1", "ANTENNA2", "TIME")
    with core_writeback.WriteBack(
        ms, flag_backup=flag_backup, stage=stage, chunk_rows=chunk_rows
    ) as w:
        spans = list(w.chunks(chunk_rows))
        meta = {k: np.concatenate([w.read(k, s, n) for s, n in spans]) for k in names}
        keep = np.isin(meta["FIELD_ID"], list(fields))
        if scan is not None:
            keep &= np.isin(meta["SCAN_NUMBER"], [int(s) for s in np.atleast_1d(scan)])
        rows = np.flatnonzero(keep)
        data = np.empty((len(rows), *lay["cell"]), np.complex64)
        flag = np.empty((len(rows), *lay["cell"]), bool)
        for s, n in spans:
            pick = (rows >= s) & (rows < s + n)
            if pick.any():
                local = rows[pick] - s
                data[pick] = w.read(column, s, n)[local]
                flag[pick] = w.read("FLAG", s, n)[local]
        new = flag.copy()
        groups = []
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
            idx = np.flatnonzero(inverse == i)
            r = rows[idx]
            result = core_flag.flag_rows(
                data[idx],
                flag[idx],
                meta["ANTENNA1"][r],
                meta["ANTENNA2"][r],
                meta["TIME"][r],
                positions,
                chan_freq,
                chan_width,
                corr,
                strategies,
                masks=masks,
                want_intensity=False,
                want_stages=False,
            )
            new[idx] = flag[idx] | result["flags"]
            groups.append(
                {
                    "field_id": int(fid),
                    "ddid": int(ddid),
                    "scan": int(sc),
                    "rows": len(idx),
                    "flagged_before": float(flag[idx].mean()),
                    "flagged_after": float(new[idx].mean()),
                }
            )
        for s, n in spans:
            pick = (rows >= s) & (rows < s + n)
            if not pick.any():
                continue
            out = w.read("FLAG", s, n)
            out[rows[pick] - s] = new[pick]
            w.write_flags(s, out)
    return {
        "column": column,
        "fields": sorted(int(f) for f in fields),
        "rows": len(rows),
        "flagged_before": float(flag.mean()) if len(rows) else 0.0,
        "flagged_after": float(new.mean()) if len(rows) else 0.0,
        "groups": groups,
        "flag_sha256": hashlib.sha256(np.ascontiguousarray(new).tobytes()).hexdigest(),
    }


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
    and `min_data_fraction`. `weight_column` (None for unit weights) and `scan`
    reach every solve and A step. Every MS write goes through
    `core_writeback.WriteBack` with `flag_backup` (saved once, before the
    first write). Returns `{"tables": {name: {...}}, "steps": [...]}`."""
    ms = Path(ms)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    say = log or (lambda text: None)
    tables, steps = {}, []
    common = {"model_column": model_column, "weight_column": weight_column}
    if scan is not None:
        common["scan"] = [int(s) for s in np.atleast_1d(scan)]
    for term in terms:
        kind, name = term["type"], term["name"]
        say(f"{kind} {name} on fields {term['fields']}")
        step = {"type": kind, "name": name, "fields": list(term["fields"])}
        if kind in ("K", "G", "B"):
            made, records = [], []
            for f in term["fields"]:
                table, sol, info = _solve_one(ms, term, f, tables, common)
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
        elif kind in POLARISATION:
            made, records = [], []
            for f in term["fields"]:
                table, record = _solve_pol(ms, term, f, tables, common)
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
