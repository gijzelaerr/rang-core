"""python-casacore side of the O-CASA oracle (research/o-casa.md).

Runs with the image's system python3 (KERN python3-casacore 3.7.1), in a
process separate from CASA. Commands (inside the container):
  equal <archived.ms> <rebuilt.ms> <out.json>  column-by-column equality gate
  prepare <run>                                arm copies, stored model, holdout flags
  restore <run> <arm>                          put the pre-holdout FLAG back (checked)
  summarize <run>                              caltable/MS/flag/image summaries and exports
"""

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from casacore.tables import makearrcoldesc, maketabdesc, table

ARMS = ("a", "b", "d", "c", "ch", "sh")
HOLDOUT_ARMS = ("ch", "sh")
SETJY_ARMS = ("a", "b", "d", "c", "ch")
FS_STANDARDS = ("Stevens-Reynolds 2016", "Perley-Butler 2010")
CALTABLE_COLUMNS = (
    "CPARAM",
    "FPARAM",
    "FLAG",
    "SNR",
    "PARAMERR",
    "TIME",
    "ANTENNA1",
    "SPECTRAL_WINDOW_ID",
)


def array_sha256(value):
    value = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(value.dtype).encode())
    digest.update(str(value.shape).encode())
    digest.update(value.tobytes())
    return digest.hexdigest()


def tree_sha256(root, exclude=("table.lock",)):
    """SHA256 over sorted POSIX relative paths and each file's SHA256."""
    root = Path(root)
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name in exclude:
            continue
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n")
    return digest.hexdigest()


def _canonical(value):
    if isinstance(value, np.ndarray):
        return {
            "dtype": str(value.dtype),
            "shape": list(value.shape),
            "v": value.tolist(),
        }
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def column_hash(tab, name):
    """SHA256 of a column's values; numeric arrays by bytes, others canonically."""
    try:
        value = tab.getcol(name)
    except Exception:  # noqa: BLE001 - fall back to per-cell reads
        value = None
    if isinstance(value, np.ndarray) and value.dtype != object:
        return array_sha256(value)
    try:
        cells = tab.getvarcol(name)
    except Exception as error:  # noqa: BLE001 - an undefined column is recorded
        return f"unreadable: {type(error).__name__}"
    text = json.dumps(_canonical(cells), sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def table_hashes(path):
    out = {}
    with table(str(path), ack=False) as tab:
        out[""] = {c: column_hash(tab, c) for c in sorted(tab.colnames())}
        out[""]["_nrows"] = tab.nrows()
        subtables = [
            k
            for k, v in tab.getkeywords().items()
            if isinstance(v, str) and v.startswith("Table: ")
        ]
    for name in sorted(subtables):
        with table(f"{path}/{name}", ack=False) as sub:
            out[name] = {c: column_hash(sub, c) for c in sorted(sub.colnames())}
            out[name]["_nrows"] = sub.nrows()
    return out


def equal(archived, rebuilt, out):
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "archived.ms"
        shutil.copytree(archived, copy)
        old = table_hashes(copy)
    new = table_hashes(rebuilt)
    differences = []
    for name in sorted(set(old) | set(new)):
        a, b = old.get(name, {}), new.get(name, {})
        for column in sorted(set(a) | set(b)):
            if a.get(column) != b.get(column):
                differences.append(
                    {
                        "table": name or "MAIN",
                        "column": column,
                        "archived": a.get(column),
                        "rebuilt": b.get(column),
                    }
                )
    result = {
        "identical": not differences,
        "differences": differences,
        "tables": len(new),
        "columns": sum(len(v) - 1 for v in new.values()),
        "main_hashes": new[""],
    }
    Path(out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(
        json.dumps({"identical": result["identical"], "differences": len(differences)})
    )
    return 0 if result["identical"] else 1


def add_stored_model(ms):
    with table(str(ms), readonly=False, ack=False) as tab:
        model = tab.getcol("MODEL_DATA")
        nchan, ncorr = model.shape[1:]
        tab.addcols(
            maketabdesc(
                [
                    makearrcoldesc(
                        "MODEL_STORED",
                        0j,
                        ndim=2,
                        shape=[nchan, ncorr],
                        valuetype="complex",
                    )
                ]
            )
        )
        tab.putcol("MODEL_STORED", model)


def prepare(run):
    run = Path(run)
    work = run / "work.ms"
    split = np.load(run / "split.npz")
    with table(str(work), ack=False) as tab:
        rows = {c: tab.getcol(c) for c in ("ANTENNA1", "ANTENNA2", "TIME")}
        flag = tab.getcol("FLAG")
    gate = {c: bool(np.array_equal(rows[c], split[c])) for c in rows}
    holdout = split["validation"] | split["test"]
    report = {
        "row_gate": gate,
        "holdout_cells": int(holdout.sum()),
        "holdout_already_flagged": int((flag.any(axis=-1) & holdout).sum()),
    }
    if not all(gate.values()):
        (run / "prepare.json").write_text(json.dumps(report, indent=1) + "\n")
        raise SystemExit("row gate failed: MS rows differ from build_state arrays")
    for arm in ARMS + ("tfcrop", "rflag", "fs-sr2016", "fs-pb2010"):
        shutil.copytree(work, run / f"{arm}.ms")
    for arm in ARMS:
        add_stored_model(run / f"{arm}.ms")
    for arm in HOLDOUT_ARMS:
        ms = run / f"{arm}.ms"
        np.save(run / f"{arm}-flag-original.npy", flag)
        with table(str(ms), readonly=False, ack=False) as tab:
            tab.putcol("FLAG", flag | holdout[..., None])
        report[f"{arm}_flag_original_sha256"] = array_sha256(flag)
    (run / "prepare.json").write_text(
        json.dumps(report, indent=1, sort_keys=True) + "\n"
    )
    print(json.dumps(report))
    return 0


def restore(run, arm):
    run = Path(run)
    original = np.load(run / f"{arm}-flag-original.npy")
    with table(str(run / f"{arm}.ms"), readonly=False, ack=False) as tab:
        tab.putcol("FLAG", original)
        back = tab.getcol("FLAG")
    ok = bool(np.array_equal(back, original))
    (run / f"{arm}-restore.json").write_text(
        json.dumps({"restored_identical": ok, "sha256": array_sha256(back)}) + "\n"
    )
    print(json.dumps({"arm": arm, "restored_identical": ok}))
    return 0 if ok else 1


def stokes_i_per_channel(model, flag):
    """Mean real (XX+YY)/2 per channel over rows unflagged in both hands."""
    ok = ~(flag[..., 0] | flag[..., 3])
    value = 0.5 * (model[..., 0] + model[..., 3]).real
    count = ok.sum(axis=0)
    mean = np.where(count > 0, (value * ok).sum(axis=0) / np.maximum(count, 1), np.nan)
    return mean, count


def model_summary(model, flag, freq):
    # The point model is the same on every row; use all rows (flags do not change a model).
    value = 0.5 * (model[..., 0] + model[..., 3]).real
    per_channel = value.mean(axis=0)
    spread = float(np.max(np.abs(value - per_channel)))
    at = float(np.interp(1.4e9, freq, per_channel))
    slope, intercept = np.polyfit(np.log10(freq / 1.4e9), np.log10(per_channel), 1)
    probes = {
        f"{f / 1e6:.1f}": float(per_channel[i])
        for i, f in zip((0, 512, 1024, 1536, 2047), freq[[0, 512, 1024, 1536, 2047]])
    }
    return {
        "stokes_i_at_1400mhz": at,
        "spectral_index_loglog": float(slope),
        "log10_s_at_1400mhz_fit": float(intercept),
        "stokes_i_channels_mhz": probes,
        "max_row_spread": spread,
        "imag_max_abs": float(
            np.max(np.abs(0.5 * (model[..., 0] + model[..., 3]).imag))
        ),
        "cross_hand_max_abs": float(np.max(np.abs(model[..., [1, 2]]))),
        "sha256": array_sha256(model),
    }


def manual_readings(manual, freq):
    """The CARACal manual model under log10 and natural-log readings of spix."""
    s0, spix = manual["fluxdensity"], manual["spix"]
    x = freq / 1.4e9
    out = {}
    for label, log in (("log10", np.log10), ("ln", np.log)):
        lx = log(x)
        exponent = sum(c * lx**i for i, c in enumerate(spix))
        out[label] = s0 * x**exponent
    return out


def caltable_summary(path, names):
    path = Path(path)
    if not path.exists():
        return {"exists": False}
    with table(str(path), ack=False) as tab:
        info = tab.info()
        keywords = tab.getkeywords()
        columns = tab.colnames()
        hashes = {c: column_hash(tab, c) for c in CALTABLE_COLUMNS if c in columns}
        par = "FPARAM" if keywords.get("ParType") == "Float" else "CPARAM"
        values = tab.getcol(par)
        flags = tab.getcol("FLAG")
        snr = tab.getcol("SNR")
        ant = tab.getcol("ANTENNA1")
        times = tab.getcol("TIME")
    out = {
        "exists": True,
        "type": keywords.get("VisCal"),
        "table_type": info.get("type"),
        "par_column": par,
        "shape": list(values.shape),
        "n_times": int(np.unique(times).size),
        "flagged_fraction": float(flags.mean()),
        "snr_median": float(np.median(snr[~flags])) if (~flags).any() else None,
        "column_sha256": hashes,
        "tree_sha256": tree_sha256(path),
        "per_antenna": {},
    }
    for i, name in enumerate(names):
        mine = ant == i
        entry = {}
        for p in range(values.shape[-1]):
            v = values[mine][..., p]
            f = flags[mine][..., p]
            good = v[~f]
            if good.size == 0:
                entry[f"pol{p}"] = {"valid": 0}
                continue
            if par == "FPARAM":
                entry[f"pol{p}"] = {
                    "valid": int(good.size),
                    "delay_ns_median": float(np.median(good)),
                    "delay_ns_min": float(good.min()),
                    "delay_ns_max": float(good.max()),
                }
            else:
                amp, phase = np.abs(good), np.degrees(np.angle(good))
                entry[f"pol{p}"] = {
                    "valid": int(good.size),
                    "amp_median": float(np.median(amp)),
                    "amp_min": float(amp.min()),
                    "amp_max": float(amp.max()),
                    "phase_median_deg": float(np.median(phase)),
                    "phase_std_deg": float(np.std(phase)),
                }
        out["per_antenna"][name] = entry
    return out


def read_fits(path):
    raw = Path(path).read_bytes()
    header = {}
    offset = 0
    while True:
        block = raw[offset : offset + 2880].decode("ascii")
        offset += 2880
        done = False
        for i in range(0, 2880, 80):
            card = block[i : i + 80]
            key = card[:8].strip()
            if key == "END":
                done = True
                break
            if card[8:10] == "= ":
                header[key] = card[10:].split("/")[0].strip().strip("'").strip()
        if done:
            break
    bitpix = int(header["BITPIX"])
    shape = [int(header[f"NAXIS{i}"]) for i in range(int(header["NAXIS"]), 0, -1)]
    dtype = {-32: ">f4", -64: ">f8"}[bitpix]
    data = np.frombuffer(
        raw, dtype=dtype, count=int(np.prod(shape)), offset=offset
    ).reshape(shape)
    return header, data.astype(np.float64).squeeze()


def image_metrics(dirty, psf, peak_box=9, offsource_box=64):
    ny, nx = dirty.shape
    cy, cx = ny // 2, nx // 2
    h = peak_box // 2
    centre = dirty[cy - h : cy + h + 1, cx - h : cx + h + 1]
    iy, ix = np.unravel_index(np.argmax(centre), centre.shape)
    peak = float(centre[iy, ix])
    o = offsource_box // 2
    mask = np.ones_like(dirty, bool)
    mask[cy - o : cy + o, cx - o : cx + o] = False
    psf_mask = np.ones_like(psf, bool)
    psf_mask[cy - h : cy + h + 1, cx - h : cx + h + 1] = False
    residual = dirty - peak * psf / psf[cy, cx]
    return {
        "peak_jy_per_beam": peak,
        "peak_pixel": [int(cy - h + iy), int(cx - h + ix)],
        "psf_centre": float(psf[cy, cx]),
        "psf_max_sidelobe": float(psf[psf_mask].max()),
        "offsource_rms": float(np.sqrt(np.mean(dirty[mask] ** 2))),
        "residual_rms": float(np.sqrt(np.mean(residual**2))),
        "residual_rms_offsource": float(np.sqrt(np.mean(residual[mask] ** 2))),
        "dirty_pixels_sha256": array_sha256(dirty),
        "psf_pixels_sha256": array_sha256(psf),
    }


def summarize(run):
    run = Path(run)
    with table(str(run / "work.ms/ANTENNA"), ack=False) as tab:
        names = list(tab.getcol("NAME"))
    with table(str(run / "work.ms/SPECTRAL_WINDOW"), ack=False) as tab:
        freq = tab.getcol("CHAN_FREQ")[0]
    with table(str(run / "work.ms"), ack=False) as tab:
        flag0 = tab.getcol("FLAG")
        stored = tab.getcol("MODEL_DATA")
    summary = {
        "antennas": names,
        "frequency_mhz": [float(freq[0] / 1e6), float(freq[-1] / 1e6)],
        "original_flag_fraction": float(flag0.mean()),
        "stored_model": model_summary(stored, flag0, freq),
        "arms": {},
    }
    for arm in ARMS:
        ms = run / f"{arm}.ms"
        entry = {
            "tables": {t: caltable_summary(run / f"{arm}.{t}0", names) for t in "KGB"}
        }
        with table(str(ms), ack=False) as tab:
            columns = tab.colnames()
            model = tab.getcol("MODEL_DATA")
            flag = tab.getcol("FLAG")
            entry["model"] = model_summary(model, flag0, freq)
            entry["flag_sha256"] = array_sha256(flag)
            entry["flag_fraction_after_apply"] = float(flag.mean())
            entry["new_flags_vs_original"] = int((flag & ~flag0).sum())
            entry["original_flags_kept"] = bool(np.all(flag[flag0]))
            if "CORRECTED_DATA" in columns:
                corrected = tab.getcol("CORRECTED_DATA")
                entry["corrected_sha256"] = array_sha256(corrected)
                ok = ~flag
                si = 0.5 * (corrected[..., 0] + corrected[..., 3])
                both = ok[..., 0] & ok[..., 3]
                entry["corrected"] = {
                    "unflagged_fraction": float(ok.mean()),
                    "stokes_i_real_mean": float(si.real[both].mean())
                    if both.any()
                    else None,
                    "stokes_i_real_std": float(si.real[both].std())
                    if both.any()
                    else None,
                    "stokes_i_imag_std": float(si.imag[both].std())
                    if both.any()
                    else None,
                    "stokes_i_over_model_mean": float(
                        (
                            si.real[both]
                            / (0.5 * (model[..., 0] + model[..., 3]).real[both])
                        ).mean()
                    )
                    if both.any()
                    else None,
                    "cross_hand_abs_mean": float(
                        np.abs(corrected[..., [1, 2]][ok[..., [1, 2]]]).mean()
                    )
                    if ok[..., [1, 2]].any()
                    else None,
                }
                if arm in ("c", "ch", "sh"):
                    np.savez(
                        run / f"export-{arm}.npz",
                        DATA=tab.getcol("DATA"),
                        CORRECTED_DATA=corrected,
                        FLAG=flag,
                        MODEL_DATA=model,
                        WEIGHT_SPECTRUM=tab.getcol("WEIGHT_SPECTRUM"),
                        ANTENNA1=tab.getcol("ANTENNA1"),
                        ANTENNA2=tab.getcol("ANTENNA2"),
                        TIME=tab.getcol("TIME"),
                        CHAN_FREQ=freq,
                    )
        solve_log = run / "casa" / f"{arm}-solve.json"
        if solve_log.exists():
            log = json.loads(solve_log.read_text())
            entry["refant"] = log.get("refant")
            if "manual_model" in log:
                readings = manual_readings(log["manual_model"], freq)
                per_channel = 0.5 * (model[..., 0] + model[..., 3]).real.mean(axis=0)
                entry["setjy_vs_caracal_reading"] = {
                    k: {
                        "max_rel_diff": float(np.max(np.abs(per_channel / v - 1))),
                        "at_1070mhz_model": float(v[0]),
                    }
                    for k, v in readings.items()
                }
                entry["setjy_at_1070mhz"] = float(per_channel[0])
        summary["arms"][arm] = entry
    flags = {}
    for mode in ("tfcrop", "rflag"):
        with table(str(run / f"{mode}.ms"), ack=False) as tab:
            flag = tab.getcol("FLAG")
        new = flag & ~flag0
        unflagged = ~flag0
        flags[mode] = {
            "flag_fraction_before": float(flag0.mean()),
            "flag_fraction_after": float(flag.mean()),
            "new_flags": int(new.sum()),
            "new_fraction_of_unflagged": float(new.sum() / unflagged.sum()),
            "new_cells_any_corr": int(new.any(axis=-1).sum()),
            "uniform_over_corr": bool(np.all(new.any(axis=-1) == new.all(axis=-1))),
            "original_kept": bool(np.all(flag[flag0])),
            "flag_sha256": array_sha256(flag),
        }
    summary["flagdata"] = flags
    fs = {}
    for label, standard in zip(("fs-sr2016", "fs-pb2010"), FS_STANDARDS):
        with table(str(run / f"{label}.ms"), ack=False) as tab:
            model = tab.getcol("MODEL_DATA")
        fs[standard] = model_summary(model, flag0, freq)
        per_channel = 0.5 * (model[..., 0] + model[..., 3]).real.mean(axis=0)
        np.save(run / f"{label}-stokes-i.npy", per_channel)
    np.save(run / "chan-freq.npy", freq)
    summary["flux_standards"] = fs
    images = {}
    dirty, psf = run / "wsclean/c-dirty.fits", run / "wsclean/c-psf.fits"
    if dirty.exists() and psf.exists():
        hd, d = read_fits(dirty)
        _, p = read_fits(psf)
        images["c"] = image_metrics(d, p)
        images["c"]["header"] = {
            k: hd.get(k)
            for k in (
                "CDELT1",
                "CDELT2",
                "CRVAL1",
                "CRVAL2",
                "BUNIT",
                "NAXIS1",
                "NAXIS2",
                "CRVAL3",
            )
        }
        images["c"]["model_stokes_i_mean"] = summary["arms"]["c"]["model"][
            "stokes_i_at_1400mhz"
        ]
    summary["images"] = images
    (run / "summary.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True) + "\n"
    )
    print(json.dumps({"summary": str(run / "summary.json")}))
    return 0


def main(argv):
    command = argv[1]
    if command == "equal":
        return equal(*argv[2:5])
    if command == "prepare":
        return prepare(argv[2])
    if command == "restore":
        return restore(argv[2], argv[3])
    if command == "summarize":
        return summarize(argv[2])
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
