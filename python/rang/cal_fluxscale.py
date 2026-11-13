# SPDX-License-Identifier: GPL-3.0-or-later
# Follows CASA's C++ source in part (Copyright (C) Associated
# Universities, Inc. Washington DC, USA; (L)GPL version 2 or later):
# notices in THIRD-PARTY-NOTICES.txt.
"""The flux-scale term F: CASA's `fluxscale` and the secondary-calibrator
sequence CARACal runs before it (task C2d, research/c2d-fluxscale.md; C1
step 6, research/c1-calibration-chain.md).

Layers, each usable alone:

- `smodel_array(nrow, nchan, stokes)`: the point model CASA's
  `gaincal(smodel=[I, Q, U, V])` solves against (`XX = I+Q`, `XY = U+iV`,
  `YX = U-iV`, `YY = I-Q`).
- `append(base, *tables)`: CASA's `gaincal(append=True)` on CalTables: the
  new rows after the old ones.
- `fluxscale(caltable, reference=..., transfer=...)`: CASA `fluxscale` on a
  `G Jones` (or `T Jones`) CalTable, with the statistics in the Rust core
  (`core/src/cal/fluxscale.rs`): returns the flux-scaled table (the F table,
  `incremental=False`) and a record shaped as CASA's return value, plus
  rang's own `rang` entry (scales, medians, counts). The rules, read from
  `SolvableVisJones::fluxscale` of casa6 6.7.6.14, are listed in the note's
  section 0.1.
- `bootstrap(ms, primary, secondary)`: the CARACal `F` step: G on each
  secondary field (and window) against a unit point model with
  `rang.cal_gain.gaincal`, appended to a copy of the primary's G table, then
  `fluxscale(reference=<primary fields>, transfer='')`.

Not here: `antenna`, `timerange` and `scan` selection, `incremental=True`,
`display` and `listfile` (refused), `fitorder < 0` (refused: CASA would
write past its coefficient matrix).
"""

import copy
import math
from pathlib import Path

import numpy as np

from . import cal_gain, core_ms
from .formats import caltable as _caltable

SMODEL_UNIT = (1.0, 0.0, 0.0, 0.0)
FLUXSCALE_TYPES = ("G Jones", "T Jones")


def _extension():
    from . import _core

    return _core


def smodel_array(nrow, nchan, stokes=SMODEL_UNIT):
    """The `(nrow, nchan, 4)` complex64 point model of CASA's `smodel`."""
    i, q, u, v = (float(s) for s in stokes)
    corr = np.array([i + q, u + 1j * v, u - 1j * v, i - q], np.complex64)
    return np.broadcast_to(corr, (int(nrow), int(nchan), 4)).copy()


def smodel_view(nrow, nchan, stokes=SMODEL_UNIT):
    """`smodel_array` as a read-only broadcast view, no copy (task W3b: a
    chunked solve copies only its chunk's rows)."""
    i, q, u, v = (float(s) for s in stokes)
    corr = np.array([i + q, u + 1j * v, u - 1j * v, i - q], np.complex64)
    return np.broadcast_to(corr, (int(nrow), int(nchan), 4))


def append(base, *tables):
    """CASA's `append=True`: a copy of `base` with every row of `tables`
    after its own (the subtables and keywords of `base`)."""
    out = copy.deepcopy(base)
    for t in tables:
        if t.vis_cal != base.vis_cal:
            raise ValueError(f"cannot append {t.vis_cal} to {base.vis_cal}")
        for name in ("ANTENNA", "SPECTRAL_WINDOW", "FIELD"):
            if len(t.subtables[name]["NAME"]) != len(base.subtables[name]["NAME"]):
                raise ValueError(f"{name} differs between the tables")
        for col, cells in out.main.items():
            cells.extend(copy.deepcopy(t.main[col]))
    return out


def _field_ids(selection, names, what):
    """CASA field selection: names or ids, comma separated or a list."""
    if (
        selection is None
        or selection == ""
        or (isinstance(selection, (list, tuple)) and not selection)
    ):
        return []
    items = (
        [s.strip() for s in selection.split(",") if s.strip()]
        if isinstance(selection, str)
        else list(np.atleast_1d(selection))
    )
    out = []
    for item in items:
        if isinstance(item, (int, np.integer)) or str(item).isdigit():
            idx = int(item)
            if not 0 <= idx < len(names):
                raise ValueError(f"{what}: no field {idx}")
        elif item in names:
            idx = names.index(item)
        else:
            raise ValueError(f"{what}: no field named {item!r}")
        out.append(idx)
    return out


def _refspwmap(refspwmap, nspw):
    m = list(range(nspw))
    given = [int(r) for r in np.atleast_1d(refspwmap if refspwmap is not None else -1)]
    if given[0] > -1:
        if len(given) == 1:
            m = [given[0]] * nspw
        else:
            for i, r in enumerate(given[:nspw]):
                if r > -1 and r != i:
                    m[i] = r
    if any(not 0 <= r < nspw for r in m):
        raise ValueError(f"refspwmap {given}: windows 0 to {nspw - 1}")
    return m


def _rows_of(table, keep):
    """A copy of `table` with only the rows where `keep`."""
    out = copy.deepcopy(table)
    idx = np.flatnonzero(keep)
    out.main = {c: [v[i] for i in idx] for c, v in table.main.items()}
    return out


def fluxscale(
    caltable,
    *,
    reference,
    transfer="",
    refspwmap=(-1,),
    gainthreshold=-1.0,
    fitorder=1,
    antenna="",
    timerange="",
    scan="",
    incremental=False,
    listfile="",
    display=False,
):
    """CASA `fluxscale` on `caltable` (a CalTable or a path): returns
    `(F CalTable, record)`. `reference` and `transfer` are field names or
    ids (comma-separated strings or lists); `transfer=''` means every field
    of the table that is not a reference."""
    for name, value in (
        ("antenna", antenna),
        ("timerange", timerange),
        ("scan", scan),
        ("listfile", listfile),
    ):
        if value:
            raise ValueError(
                f"fluxscale: {name} selection is not ported (research/c2d-fluxscale.md, 1)"
            )
    if incremental:
        raise ValueError(
            "fluxscale: incremental=True is not ported (research/c2d-fluxscale.md, 1)"
        )
    if display:
        raise ValueError(
            "fluxscale: display is not ported (research/c2d-fluxscale.md, 1)"
        )
    if int(fitorder) < 0:
        raise ValueError("fluxscale: fitorder must be >= 0")
    table = (
        caltable
        if isinstance(caltable, _caltable.CalTable)
        else _caltable.read(caltable)
    )
    if table.vis_cal not in FLUXSCALE_TYPES:
        raise ValueError(f"Type {table.vis_cal} not supported in fluxscale.")
    if table.nrows < 1:
        raise ValueError("SVJ:fluxscale: Empty or absent caltable specified")
    names = [str(n) for n in table.subtables["FIELD"]["NAME"]]
    spw_names = [str(n) for n in table.subtables["SPECTRAL_WINDOW"]["NAME"]]
    nspw = len(spw_names)
    nant = len(table.subtables["ANTENNA"]["NAME"])
    ref_given = _field_ids(reference, names, "reference")
    if not ref_given:
        raise ValueError("A reference field must be specified!")
    tran_given = _field_ids(transfer, names, "transfer")
    # Calibrater::fluxscale: with transfer fields given, only the reference
    # and transfer fields' rows enter the calculation. Every row is written
    # (measured against CASA, post hoc after run -02: the note's section 0.1
    # item 1 read the selection as dropping the others from the output).
    full = table
    if tran_given:
        keep = np.isin(table.column("FIELD_ID"), ref_given + tran_given)
        table = _rows_of(table, keep)
    field = table.column("FIELD_ID").astype(int)
    spw = table.column("SPECTRAL_WINDOW_ID").astype(int)
    ant = table.column("ANTENNA1").astype(int)
    times = table.column("TIME").astype(float)
    keys = set()
    for k in zip(spw, times, field, ant):
        if k in keys:
            raise ValueError(
                "Found multiple gain solutions in a single timestamp for "
                f"fieldid={k[2]}. Please check the input Caltable."
            )
        keys.add(k)
    present = sorted(set(field.tolist()))
    nfield = max(present) + 1
    refs = sorted(set(ref_given))
    tran = sorted(set(tran_given) - set(refs))
    ref_ok = [f for f in refs if f in present]
    if not ref_ok:
        raise ValueError(" Cannot find specified reference field(s)")
    implicit_tran = [f for f in present if f not in refs]
    if not implicit_tran:
        raise ValueError(" Cannot find solutions for transfer field(s)")
    warnings = []
    if len(ref_ok) < len(refs):
        warnings.append(
            "reference fields without solutions: "
            + ", ".join(names[f] for f in refs if f not in ref_ok)
        )
        refs = ref_ok
    if not tran:
        tran = implicit_tran
    else:
        missing = [f for f in tran if f not in present]
        if missing:
            warnings.append(
                "transfer fields without solutions: "
                + ", ".join(names[f] for f in missing)
            )
            for f in missing:
                if f < nfield:
                    raise ValueError(
                        "The input selections results in empy data selection for the "
                        f"transfer field={f}"
                    )
    params = table.params  # (row, chan, par) complex64
    if params.shape[1] != 1:
        raise ValueError("fluxscale needs one solution channel per row")
    npar = params.shape[2]
    # CASA's amplitude is float32(sqrt(re^2 + im^2)) evaluated in float64, not
    # the float32 hypot: post hoc after run -02 (the note's section 8), the
    # rule that reproduces CASA's fluxd exactly on every case.
    p = params[:, 0, :]
    amp = np.sqrt(
        p.real.astype(np.float64) ** 2 + p.imag.astype(np.float64) ** 2
    ).astype(np.float32)
    flags = table.flags[:, 0, :]
    out = _extension().cal_fluxscale_scale(
        np.ascontiguousarray(amp.ravel()),
        np.ascontiguousarray(flags.ravel().astype(np.uint8)),
        np.ascontiguousarray(field.astype(np.uint32)),
        np.ascontiguousarray(spw.astype(np.uint32)),
        np.ascontiguousarray(ant.astype(np.uint32)),
        npar,
        nant,
        nspw,
        nfield,
        refs,
        tran,
        _refspwmap(refspwmap, nspw),
        float(gainthreshold),
    )
    shape = (nspw, nfield)
    fd = np.reshape(out["fd"], shape)
    fderr = np.reshape(out["fderr"], shape)
    numsol = np.reshape(out["numsol"], shape)
    ok = np.reshape(out["ok"], shape)
    mgratio = np.reshape(out["mgratio"], shape)
    # The frequency of each window seen in the table: CHAN_FREQ[nchan // 2]
    # of the caltable's window (one channel for G).
    freq = np.full(nspw, -1.0)
    for w in sorted(set(spw.tolist())):
        f = table.solution_frequencies(w)
        freq[w] = float(f[len(f) // 2])
    record = {"freq": freq, "spwID": np.arange(nspw), "spwName": np.array(spw_names)}
    fits = {}
    for f in tran:
        valid = [w for w in range(nspw) if ok[w, f]]
        entry = {"fieldName": names[f]}
        for w in range(nspw):
            entry[str(w)] = {
                "fluxd": np.array([fd[w, f], 0.0, 0.0, 0.0]),
                "fluxdErr": np.array([fderr[w, f], 0.0, 0.0, 0.0]),
                "numSol": np.array([numsol[w, f], 0, 0, 0]),
            }
        coeffs = np.zeros(int(fitorder) + 1)
        errors = np.zeros(int(fitorder) + 1)
        covar = np.zeros((0, 0))
        fit_flux, fit_err, fit_ref = 0.0, 0.0, 0.0
        if valid:
            fit = _extension().cal_fluxscale_fit(
                [freq[w] for w in valid],
                [float(fd[w, f]) for w in valid],
                [float(fderr[w, f]) for w in valid],
                int(fitorder),
            )
            n = len(fit["coeffs"])
            coeffs[:n] = fit["coeffs"]
            errors[:n] = fit["errors"]
            if n:
                covar = np.reshape(fit["covar"], (n, n))
            fit_flux, fit_err, fit_ref = fit["flux"], fit["flux_err"], fit["ref_freq"]
            fits[f] = fit
        entry.update(
            fitFluxd=fit_flux,
            fitFluxdErr=fit_err,
            fitRefFreq=fit_ref,
            spidx=coeffs,
            spidxerr=errors,
            covarMat=covar,
        )
        record[str(f)] = entry
    # The F table: every row of a (window, transfer field) with a scale
    # divided by Float(mgratio), per component in float32.
    ftable = copy.deepcopy(full)
    cparam = ftable.main["CPARAM"]
    fspw = full.column("SPECTRAL_WINDOW_ID").astype(int)
    ffield = full.column("FIELD_ID").astype(int)
    for r in range(full.nrows):
        w, f = fspw[r], ffield[r]
        if f in tran and f < nfield and ok[w, f]:
            s = np.float32(mgratio[w, f])
            c = np.asarray(cparam[r], np.complex64)
            cparam[r] = (c.real / s + 1j * (c.imag / s)).astype(np.complex64)
    record["rang"] = {
        "reference": refs,
        "transfer": tran,
        "mgratio": mgratio,
        "mgrms": np.reshape(out["mgrms"], shape),
        "mgerr": np.reshape(out["mgerr"], shape),
        "ok": ok,
        "median_gain": np.reshape(out["median_gain"], (nfield, nspw)),
        "used": np.reshape(out["used"], (nfield, nant, nspw)),
        "unflagged": np.reshape(out["unflagged"], (nfield, nant, nspw)),
        "fit_order": {f: fits[f]["order"] for f in fits},
        "warnings": warnings,
    }
    return ftable, record


def _field_rows(ms, field_id, spw, scan=None):
    ms = Path(ms)
    with core_ms.open_table(ms / "DATA_DESCRIPTION") as t:
        dd_spw = np.asarray(t.getcol("SPECTRAL_WINDOW_ID"))
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        nchan = int(np.asarray(t.getcol("NUM_CHAN"))[spw])
    with core_ms.open_table(ms) as t:
        fields = t.getcol("FIELD_ID")
        ddid = t.getcol("DATA_DESC_ID")
    keep = cal_gain._scan_keep(ms, scan, (fields == field_id) & (dd_spw[ddid] == spw))
    return int(keep.sum()), nchan


def _windows(ms):
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        return len(t.getcol("NUM_CHAN"))


def bootstrap(
    ms,
    primary,
    secondary,
    *,
    reference=None,
    smodel=SMODEL_UNIT,
    fitorder=1,
    gainthreshold=-1.0,
    **gaincal_kwargs,
):
    """CARACal's F step on `ms`: for every window and secondary field id in
    `secondary`, `rang.cal_gain.gaincal` against the point model `smodel`
    (`gaincal_kwargs` as for `gaincal`, e.g. `gaintable`, `solint`,
    `refant`), appended to a copy of `primary` (a G CalTable or a path);
    then `fluxscale(reference=<primary's fields or reference>, transfer='')`.
    Returns `(F CalTable, record, merged G CalTable)`."""
    base = (
        primary if isinstance(primary, _caltable.CalTable) else _caltable.read(primary)
    )
    nspw = _windows(ms)
    new = []
    for f in np.atleast_1d(secondary):
        for w in range(nspw):
            nrow, nchan = _field_rows(ms, int(f), w, gaincal_kwargs.get("scan"))
            if not nrow:
                continue
            table, _, _ = cal_gain.gaincal(
                ms,
                field_id=int(f),
                model=smodel_view(nrow, nchan, smodel),
                spw=w if nspw > 1 else None,
                **gaincal_kwargs,
            )
            new.append(table)
    if not new:
        raise ValueError("no rows of the secondary fields")
    merged = append(base, *new)
    if reference is None:
        reference = sorted({int(f) for f in base.main["FIELD_ID"]})
    ftable, record = fluxscale(
        merged,
        reference=reference,
        transfer="",
        fitorder=fitorder,
        gainthreshold=gainthreshold,
    )
    return ftable, record, merged


def summary(record):
    """The fitted flux density and spectral index of each transfer field,
    as plain numbers (for receipts and logs)."""
    out = {}
    for key, entry in record.items():
        if not key.isdigit():
            continue
        spix = np.asarray(entry["spidx"], float)
        out[entry["fieldName"]] = {
            "fitted_flux_jy": float(entry["fitFluxd"]),
            "fitted_flux_err_jy": float(entry["fitFluxdErr"]),
            "reference_frequency_hz": float(entry["fitRefFreq"]),
            "spectral_index": float(spix[1]) if len(spix) > 1 else math.nan,
            "per_window_flux_jy": [
                float(entry[str(w)]["fluxd"][0]) for w in record["spwID"]
            ],
        }
    return out


__all__ = [
    "SMODEL_UNIT",
    "append",
    "bootstrap",
    "fluxscale",
    "smodel_array",
    "smodel_view",
    "summary",
]
