"""FS1: compare rang.fluxstd with the CASA setjy oracle and write the archive.

Usage (from the checkout, host venv):

    python examples/check_fluxstd.py outputs/fs1-20261030-01 outputs/fs1-20261030-03 \
        outputs/o-casa-20261030-01 outputs/fs1-20261030-06 outputs/fs1-20261030-04 \
        research/results/fs1-flux-standards.json

Inputs: the main oracle run (`oracle_setjy.py`), the dense 1934-638 run
(`--dense-1934`), the O-CASA run (its `fs-*-stokes-i.npy`, `chan-freq.npy`),
the re-read of O-CASA's `fs-*.ms` MODEL_DATA (`--reread-ocasa`) and a rerun
of the main oracle (hashes compared). Reads only; writes
the compact archive (research/fs1-flux-standards.md, "Acceptance").

FS2 (research/fs2-casarundata.md):

    python examples/check_fluxstd.py --fs2 outputs/fs2-20261102-01 \
        outputs/fs2-20261102-02 outputs/fs1-20261030-01 \
        /mnt/d/rang/data/casarundata-standards \
        research/results/fs2-casarundata.json
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from rang import fluxstd

TAGS = {
    "Perley-Butler_2010": "Perley-Butler 2010",
    "Baars": "Baars",
    "Stevens-Reynolds_2016": "Stevens-Reynolds 2016",
}
DECIMATE = 50  # L-band channels kept in the archive (every 50th, 21 of 1001)


def rel(a, b):
    return float(np.max(np.abs(np.asarray(a) / np.asarray(b) - 1)))


def ulps(casa32, port):
    port32 = np.asarray(port).astype(np.float32)
    diff = np.abs(casa32.astype(np.float64) - port32.astype(np.float64))
    return float(np.max(diff / np.spacing(port32)))


def compare_oracle(run, archive):
    rec = json.loads((run / "oracle.json").read_text())
    lband = rec["spw"]["name"].index("L")
    nu_l = np.array(rec["spw"]["chan"][lband])
    archive["lband_freq_hz"] = nu_l[::DECIMATE].tolist()
    rows, refusals = [], []
    for tag, std in TAGS.items():
        for call in rec["standards"][tag]["calls"]:
            field = call["field"]
            if call["not_recognized"]:
                try:
                    fluxstd.flux(field, [1.4e9], std)
                    refused = False
                except ValueError:
                    refused = True
                refusals.append(
                    {
                        "standard": std,
                        "field": field,
                        "casa": "1 Jy, SEVERE not recognized",
                        "port_refuses": refused,
                    }
                )
                continue
            d = np.load(run / "arrays" / f"{tag}--{field}--doubles.npy")
            nu, casa = d[:, 0], d[:, 1:]
            m = fluxstd.model(field, std)
            port = fluxstd.flux(field, nu, std, extrapolate=True)
            inside = (nu >= m.valid_hz[0]) & (nu <= m.valid_hz[1])
            model = np.load(run / "arrays" / f"{tag}--{field}--lband-model.npy")
            i_casa = model[:, 0].real  # XX == YY (checked), so I = XX in float32
            port_l = fluxstd.flux(field, nu_l, std)[:, 0]
            row = {
                "standard": std,
                "field": field,
                "canonical": m.source,
                "n_doubles": len(nu),
                "max_rel_doubles_in_range": rel(port[inside, 0], casa[inside, 0]),
                "max_rel_doubles_all": rel(port[:, 0], casa[:, 0]),
                "casa_quv_zero": bool(np.all(casa[:, 1:] == 0)),
                "lband_xx_eq_yy": bool(np.array_equal(model[:, 0], model[:, 3])),
                "lband_cross_zero": bool(np.all(model[:, 1:3] == 0)),
                "lband_imag_zero": bool(np.all(model[:, [0, 3]].imag == 0)),
                "lband_max_ulps": ulps(i_casa, port_l),
                "lband_exact_fraction": float(
                    np.mean(i_casa == port_l.astype(np.float32))
                ),
                "lband_max_rel": rel(port_l, i_casa),
            }
            rows.append(row)
            if field == m.source:  # one copy per canonical source in the archive
                archive["oracle"].setdefault(std, {})[m.source] = {
                    "freq_hz": nu.tolist(),
                    "casa_fluxd_i": casa[:, 0].tolist(),
                    "lband_casa_i_f32": i_casa[::DECIMATE].astype(float).tolist(),
                }
    # manual (CARACal's 1934-638 model)
    call = rec["standards"]["manual"]["calls"][0]
    d = np.load(run / "arrays" / "manual--1934-638--doubles.npy")
    model = np.load(run / "arrays" / "manual--1934-638--lband-model.npy")
    port = fluxstd.manual(d[:, 0], **fluxstd.CARACAL_1934)
    port_l = fluxstd.manual(nu_l, **fluxstd.CARACAL_1934)
    rows.append({
        "standard": "manual (CARACal 1934-638)", "field": call["field"], "canonical": "1934-638",
        "n_doubles": len(d), "max_rel_doubles_in_range": rel(port, d[:, 1]),
        "max_rel_doubles_all": rel(port, d[:, 1]), "casa_quv_zero": bool(np.all(d[:, 2:] == 0)),
        "lband_xx_eq_yy": bool(np.array_equal(model[:, 0], model[:, 3])),
        "lband_cross_zero": bool(np.all(model[:, 1:3] == 0)),
        "lband_imag_zero": bool(np.all(model[:, [0, 3]].imag == 0)),
        "lband_max_ulps": ulps(model[:, 0].real, port_l),
        "lband_exact_fraction": float(np.mean(model[:, 0].real == port_l.astype(np.float32))),
        "lband_max_rel": rel(port_l, model[:, 0].real),
    })  # fmt: skip
    archive["oracle"]["manual"] = {
        "1934-638": {
            "freq_hz": d[:, 0].tolist(),
            "casa_fluxd_i": d[:, 1].tolist(),
            "lband_casa_i_f32": model[::DECIMATE, 0].real.astype(float).tolist(),
        }
    }
    pending = {
        tag: sorted({c["field"] for c in rec["standards"][tag]["calls"] if c["empty"]})
        for tag in ("Perley-Butler_2017", "Perley-Butler_2013")
    }
    frame = {
        label: {
            f: rel(
                np.array(v[f])[:, 1], np.array(rec["frame_check"]["topo-2020"][f])[:, 1]
            )
            for f in ("3C286", "1934-638")
        }
        | {"meas_freq_ref": v["meas_freq_ref"]}
        for label, v in rec["frame_check"].items()
    }
    return rows, refusals, pending, frame, rec


def compare_dense(run, archive):
    rec = json.loads((run / "oracle.json").read_text())
    out = {}
    for tag in ("Stevens-Reynolds_2016", "Perley-Butler_2010"):
        d = np.load(run / "arrays" / f"{tag}--1934-638--doubles.npy")
        port = fluxstd.flux("1934-638", d[:, 0], TAGS[tag])[:, 0]
        out[TAGS[tag]] = {"n": len(d), "max_rel": rel(port, d[:, 1])}
        archive["dense_1934"][TAGS[tag]] = {
            "freq_hz": d[:, 0].tolist(),
            "casa_fluxd_i": d[:, 1].tolist(),
        }
    out["timing_s"] = rec["timing"]
    return out


def compare_ocasa(ocasa, reread):
    freq = np.load(ocasa / "chan-freq.npy")
    out = {"per_row_reread": json.loads((reread / "ocasa-reread.json").read_text())}
    if not np.array_equal(np.load(reread / "arrays/ocasa--chan-freq.npy"), freq):
        raise RuntimeError("O-CASA channel frequencies differ between runs")
    port = fluxstd.flux("1934-638", freq, "Stevens-Reynolds 2016")[:, 0]
    for label in ("fs-sr2016", "fs-pb2010"):
        row0 = np.load(reread / f"arrays/ocasa--{label}--xx-row0.npy")
        out["per_row_reread"][label]["row0_vs_port_ulps_max"] = ulps(row0, port)
        out["per_row_reread"][label]["row0_vs_port_double_max_rel"] = rel(row0, port)
    # The setjy-equivalent 1934-638 arm: lsm source -> core predictor, complex64.
    src = fluxstd.lsm_source(
        "J1939-6342", "SR2016", 0.0, 0.0, 1.284e9, (freq[0], freq[-1])
    )
    from rang import core, lsm

    vis = core.predict_components(
        np.array([[0.0, 0.0, 0.0], [120.0, -40.0, 3.0]]),
        freq,
        **lsm.components([src], (0.0, 0.0)),
    ).astype(np.complex64)
    row0 = np.load(reread / "arrays/ocasa--fs-sr2016--xx-row0.npy")
    out["setjy_arm_predictor"] = {
        "vs_casa_rows_ulps_max": ulps(row0, vis.real.astype(np.float64)[0]),
        "vs_casa_rows_ulps_max_row1": ulps(row0, vis.real.astype(np.float64)[1]),
        "max_abs_imag": float(np.abs(vis.imag).max()),
        "port_i_at_1p4ghz": float(fluxstd.flux("1934-638", [1.4e9], "SR2016")[0, 0]),
        "stored_model_i_at_1p4ghz_ocasa": 14.9028,
    }  # fmt: skip
    out["setjy_arm_predictor"]["port_over_stored_at_1p4ghz"] = (
        out["setjy_arm_predictor"]["port_i_at_1p4ghz"] / 14.9028 - 1
    )
    reynolds_mhz = 10 ** np.polynomial.polynomial.polyval(
        np.log10(freq / 1e6), fluxstd.REYNOLDS_1994_MHZ
    )
    nrow = out["per_row_reread"]["fs-sr2016"]["nrow"]
    for std, label in (
        ("Stevens-Reynolds 2016", "sr2016"),
        ("Perley-Butler 2010", "pb2010"),
    ):
        saved = np.load(ocasa / f"fs-{label}-stokes-i.npy")
        p = fluxstd.flux("1934-638", freq, std)[:, 0]
        cell = np.tile(p.astype(np.float32).astype(np.complex64), (nrow, 1))
        # O-CASA's reduction (inspect_tables.py): 0.5 * (XX + YY).real.mean(axis=0), float32
        replay = 0.5 * (cell + cell).real.mean(axis=0)
        out[label] = {
            "saved_vs_port_max_rel": rel(saved, p),
            "saved_vs_reynolds_mhz_max_rel": rel(saved, reynolds_mhz),
            "port_vs_reynolds_mhz_max_rel": rel(p, reynolds_mhz),
            "replay_of_ocasa_reduction_bit_identical": bool(
                np.array_equal(replay, saved)
            ),
        }
    out["sr2016_eq_pb2010_below_10ghz"] = bool(
        np.array_equal(port, fluxstd.flux("1934-638", freq, "Perley-Butler 2010")[:, 0])
    )
    return out


def rust_parity(archive):
    start = time.time()
    lib = fluxstd.rust_library()
    freqs = np.unique(np.concatenate(
        [np.array(v["freq_hz"]) for s in archive["oracle"].values() for v in s.values()]
        + [np.array(archive["lband_freq_hz"]), np.geomspace(0.05e9, 50e9, 997)]
    ))  # fmt: skip
    worst = 0.0
    for m in fluxstd.MODELS.values():
        for p in m.pieces:
            py = fluxstd.log10_poly(p.coeffs, p.unit_hz, freqs)
            rs = fluxstd.rust_log10_poly(lib, p.coeffs, p.unit_hz, freqs)
            worst = max(worst, rel(rs, py))
    return {"models": len(fluxstd.MODELS), "frequencies": len(freqs), "max_rel": worst,
            "wall_s_incl_build": round(time.time() - start, 2)}  # fmt: skip


def manual_vs_standards():
    """CARACal's manual 1934-638 model against SR2016 (= PB2010 below 10 GHz)."""
    bands = {
        "UHF 0.544-1.088 GHz": (0.544e9, 1.088e9),
        "L 0.856-1.712 GHz": (0.856e9, 1.712e9),
        "S 1.75-3.5 GHz": (1.75e9, 3.5e9),
        "11.15-50 GHz": (11.15e9, 50e9),
    }
    out = {}
    for name, (lo, hi) in bands.items():
        nu = np.linspace(lo, hi, 4001)
        man = fluxstd.manual(nu, **fluxstd.CARACAL_1934)
        sr = fluxstd.flux("1934-638", nu, "SR2016")[:, 0]
        pb = fluxstd.flux("1934-638", nu, "PB2010")[:, 0]
        out[name] = {
            "manual_vs_sr2016_max_rel": rel(man, sr),
            "manual_vs_pb2010_max_rel": rel(man, pb),
        }
    return out


def builder_check():
    from rang import lsm

    nu = np.linspace(0.856e9, 1.712e9, 4096)
    out = {}
    for src, std in (("1934-638", "Stevens-Reynolds 2016"), ("1934-638", "Perley-Butler 2010"),
                     ("3C286", "Perley-Butler 2010"), ("3C286", "Baars")):  # fmt: skip
        s = fluxstd.lsm_source(src, std, 0.0, 0.0, 1.284e9, (nu[0], nu[-1]))
        out[f"{std} {src}"] = {
            "spi_terms": len(s.spi),
            "max_rel": rel(s.flux(nu), fluxstd.flux(src, nu, std)[:, 0]),
        }
    s = fluxstd.manual_lsm_source(0.0, 0.0, **fluxstd.CARACAL_1934)
    out["manual CARACal 1934-638"] = {
        "spi_terms": len(s.spi),
        "max_rel": rel(s.flux(nu), fluxstd.manual(nu, **fluxstd.CARACAL_1934)),
    }
    comps = lsm.components([s], (0.0, 0.0))
    try:
        from rang import core

        vis = core.predict_components(np.array([[100.0, 50.0, 0.0]]), nu, **comps)
        out["core_predict_manual_max_rel"] = rel(
            vis[0].real, fluxstd.manual(nu, **fluxstd.CARACAL_1934)
        )
    except (ImportError, RuntimeError, AttributeError) as error:
        out["core_predict_manual_max_rel"] = f"skipped: {error}"
    return out


# --- FS2: PB2017 and PB2013 against setjy with CASA's tables -----------------
RELEASE = {
    "url": "https://casa.nrao.edu/download/casaconfig/data/casarundata-2026.10.27-1.tar.gz",
    "bytes": 352724572,
    "md5_published_and_measured": "9095d076fe11af3a4da72225fd8afe36",
    "sha256": "e372fef14a74749a912274dc6334d4bdc38088070086b1f821c73f8ef43adbef",
}
RSYNC = "rsync://casa-rsync.nrao.edu/casa-data/nrao/VLA/standards/"
PAPER = {
    "url": "https://arxiv.org/pdf/1609.05940",
    "version": "v1",
    "bytes": 2311277,
    "sha256": "975c2018426f1c53f34d50cacfa04cfb03f4709d8ead313ef385475e53afc72a",
}
# Table column (without _coeffs) for each name the oracle tried.
FS2_COLUMN = {
    "Fornax A": "FORNAX_A", "Pictor A": "PICTOR_A", "Taurus A": "TAURUS_A",
    "Hydra A": "HYDRA_A", "Virgo A": "VIRGO_A", "Hercules A": "HERCULES_A",
    "Cygnus A": "CYGNUS_A", "Cassiopeia A": "CASSIOPEIA_A",
}  # fmt: skip
FS2_SOURCE = {v: k for k, v in FS2_COLUMN.items()} | {
    "3C144": "Taurus A", "3C218": "Hydra A", "3C274": "Virgo A",
    "3C348": "Hercules A", "3C405": "Cygnus A", "3C461": "Cassiopeia A",
}  # fmt: skip
FS2_EPOCH_YEAR = {"topo-2000": 2000.0, "topo-2010": 2010.0, "topo-2020": 2020.0, "lsrk-2020": 2020.0}  # fmt: skip


def sha256_tree(root):
    return {
        str(f.relative_to(root)): {
            "bytes": f.stat().st_size,
            "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
        }
        for f in sorted(root.rglob("*"))
        if f.is_file()
    }


def fs2_rounds_to(table, printed):
    """Does the table's value round to the value Table 5 prints?"""
    decimals = len(
        repr(printed).split(".")[1]
    )  # 0.030 counts as 0.03: looser, never tighter
    return (
        abs(table - printed) <= 0.5 * 10.0**-decimals + 2.5e-7
    )  # a float32 ulp, for ties


def fs2_table_summary(dump):
    """Per PB2017 source: the table against the paper's Table 5 (the core's decimals)."""
    columns = dump["PerleyButler2017Coeffs"]["columns"]
    out = {}
    for source, (paper, (lo, hi)) in fluxstd._PB2017.items():
        col = columns[FS2_COLUMN.get(source, source) + "_coeffs"]
        rows = np.array(col["values"])
        last = rows[-1]
        padded = list(paper) + [0.0] * (len(last) - len(paper))
        f32_equal = bool(np.array_equal(last, np.array(_f32_list(padded))))
        rounds = all(fs2_rounds_to(float(t), c) for t, c in zip(last, padded))
        varies = bool(not np.all(rows == rows[0]))
        rng = col["keywords"]["ValidFreqRange"]
        table_hi = float(rng.split("[")[1].split("]")[0].split(",")[1])
        table_lo = float(rng.split("[")[1].split("]")[0].split(",")[0])
        if varies:
            kind = "model: epoch rows"
        elif not rounds:
            kind = "table differs from Table 5"
        elif not f32_equal:
            kind = "table has more digits than Table 5"
        else:
            kind = "same decimals, float32 storage"
        out[source] = {
            "kind": kind,
            "epoch_rows_vary": varies,
            "last_row_equals_float32_of_table5": f32_equal,
            "last_row_rounds_to_table5": rounds,
            "max_abs_table_minus_table5": float(np.max(np.abs(last - padded))),
            "table_range_ghz": [table_lo, table_hi],
            "table5_range_ghz": [lo, hi],
            "range_agrees": bool(table_lo == lo and table_hi == hi),
        }
    return out


def _f32_list(values):
    return [float(np.float32(v)) for v in values]


def fs2_row(run, tag, call, nu_l, table_rows):
    """Paper decimals, float32 of them, the port and the table against setjy."""
    field = call["field"]
    d = np.load(run / "arrays" / f"{tag}--{field}--doubles.npy")
    nu, casa = d[:, 0], d[:, 1:]
    model = np.load(run / "arrays" / f"{tag}--{field}--lband-model.npy")
    i_l = model[:, 0].real
    row = {
        "field": field,
        "n_doubles": len(nu),
        "casa_quv_zero": bool(np.all(casa[:, 1:] == 0)),
        "lband_cross_zero": bool(np.all(model[:, 1:3] == 0)),
        "lband_xx_eq_yy": bool(np.array_equal(model[:, 0], model[:, 3])),
        "n_warnings": len(call["log"]),
    }
    last = [float(c) for c in table_rows[-1]]
    table_nu = fluxstd.log10_poly(last, 1e9, nu)
    row["table_max_rel_all"] = rel(table_nu, casa[:, 0])
    # The table path returns float32 values in `fluxd` (post-hoc finding).
    row["fluxd_is_float32"] = bool(np.array_equal(casa[:, 0].astype(np.float32).astype(float), casa[:, 0]))  # fmt: skip
    row["table_fluxd_max_ulps"] = ulps(casa[:, 0].astype(np.float32), table_nu)
    row["table_lband_max_ulps"] = ulps(i_l, fluxstd.log10_poly(last, 1e9, nu_l))
    return row, nu, casa, i_l


def fs2_compare(run, nu_l, summary, dump, archive):
    columns = dump["PerleyButler2017Coeffs"]["columns"]
    rec = json.loads((run / "oracle.json").read_text())
    rows = []
    calls = rec["standards"]["Perley-Butler_2017"]["calls"]
    calls = calls + rec["secondary"]["Perley-Butler_2017"]["calls"]
    outcomes = {"not_recognized": [], "not_in_table": []}
    for call in calls:
        field = call["field"]
        if call["not_recognized"]:
            outcomes["not_recognized"].append(field)
            continue
        if call["empty"]:
            outcomes["not_in_table"].append({"field": field, "log": call["log"][:1]})
            continue
        src = fluxstd.ALIASES.get(field, FS2_SOURCE.get(field, field))
        paper, (lo, hi) = fluxstd._PB2017[src]
        col = columns[FS2_COLUMN.get(src, src) + "_coeffs"]["values"]
        row, nu, casa, i_l = fs2_row(run, "Perley-Butler_2017", call, nu_l, col)
        inside = (nu >= lo * 1e9) & (nu <= hi * 1e9)
        paper_nu = fluxstd.log10_poly(paper, 1e9, nu)
        paper32 = _f32_list(paper)
        port = fluxstd.flux(src, nu, "PB2017", extrapolate=True, unverified_ok=True)[
            :, 0
        ]
        port_l = fluxstd.flux(
            src, nu_l, "PB2017", extrapolate=True, unverified_ok=True
        )[:, 0]
        row |= {
            "source": src,
            "as_frozen_decimals_max_rel_in_range": rel(paper_nu[inside], casa[inside, 0]),
            "as_frozen_decimals_lband_max_ulps": ulps(i_l, fluxstd.log10_poly(paper, 1e9, nu_l)),
            "float32_of_table5_max_rel_in_range": rel(
                fluxstd.log10_poly(paper32, 1e9, nu)[inside], casa[inside, 0]
            ),
            "float32_of_table5_lband_max_ulps": ulps(i_l, fluxstd.log10_poly(paper32, 1e9, nu_l)),
            "port_max_rel_in_range": rel(port[inside], casa[inside, 0]),
            "port_max_rel_all": rel(port, casa[:, 0]),
            "port_lband_max_ulps": ulps(i_l, port_l),
            "port_lband_exact_fraction": float(np.mean(i_l == port_l.astype(np.float32))),
        }  # fmt: skip
        rows.append(row)
        if field == src or (field in FS2_COLUMN.values() and FS2_SOURCE[field] == src):
            entry = {"freq_hz": nu.tolist(), "casa_fluxd_i": casa[:, 0].tolist()}
            entry["lband_casa_i_f32"] = i_l[::DECIMATE].astype(float).tolist()
            archive["pb2017"][src] = entry
    # PB2013: setjy against its own table; the core has no PB2013.
    columns13 = dump["PerleyButler2013Coeffs"]["columns"]
    rows13, out13 = [], {"not_recognized": [], "not_in_table": []}
    for call in rec["standards"]["Perley-Butler_2013"]["calls"] + rec["secondary"]["Perley-Butler_2013"]["calls"]:  # fmt: skip
        field = call["field"]
        if call["not_recognized"]:
            out13["not_recognized"].append(field)
        elif call["empty"]:
            out13["not_in_table"].append(field)
        else:
            src = fluxstd.ALIASES.get(field, field)
            col = columns13[src + "_coeffs"]["values"]
            row, nu, casa, i_l = fs2_row(run, "Perley-Butler_2013", call, nu_l, col)
            rows13.append(row | {"source": src})
            if field == src:
                archive["pb2013"][src] = {"freq_hz": nu.tolist(), "casa_fluxd_i": casa[:, 0].tolist()}  # fmt: skip
    return rec, rows, outcomes, rows13, out13


def fs2_epoch(run_records, dump):
    """`fluxd` per epoch and frame against 2020 TOPO, and the table row it equals."""
    out = {}
    for run_name, rec in run_records:
        for std, tab in (("Perley-Butler 2017", "PerleyButler2017Coeffs"),
                         ("Perley-Butler 2013", "PerleyButler2013Coeffs")):  # fmt: skip
            columns = dump[tab]["columns"]
            epochs = columns["Epoch"]["values"]
            base = rec["epoch_check"]["topo-2020"][std]
            for field in base:
                ref = np.array(base[field])[:, 1]
                src = FS2_SOURCE.get(field, field)
                key = FS2_COLUMN.get(src, src) + "_coeffs"
                entry = {"run": run_name}
                for label, year in FS2_EPOCH_YEAR.items():
                    d = np.array(rec["epoch_check"][label][std][field])
                    if np.all(np.isnan(d[:, 1])):
                        entry[label] = {"no_value": True}
                        continue
                    item = {"max_rel_vs_topo2020": rel(d[:, 1], ref)}
                    if key in columns:
                        errs = [rel(fluxstd.log10_poly(c, 1e9, d[:, 0]), d[:, 1])
                                for c in columns[key]["values"]]  # fmt: skip
                        k = int(np.argmin(errs))
                        item |= {"nearest_row_rel": errs[int(np.argmin(np.abs(np.array(epochs) - year)))],
                                 "best_row_rel": errs[k]}  # fmt: skip
                    entry[label] = item
                out.setdefault(std, {}).setdefault(field, []).append(entry)
    return out


def fs2_no_epoch_motion(epoch, field):
    entries = epoch["Perley-Butler 2017"].get(field, [])
    if not entries:
        return False
    return all(
        v.get("max_rel_vs_topo2020") == 0.0
        for e in entries
        for k, v in e.items()
        if k != "run"
    )


def fs2_main(argv):
    run, run2, fs1_run, tables, out_path = (Path(a) for a in argv)
    dump = json.loads((run / "table-dump.json").read_text())
    rec_main = json.loads((run / "oracle.json").read_text())
    nu_l = np.array(rec_main["spw"]["chan"][rec_main["spw"]["name"].index("L")])
    archive = {"lband_freq_hz": nu_l[::DECIMATE].tolist(), "pb2017": {}, "pb2013": {}}
    summary = fs2_table_summary(dump)
    rec, rows, outcomes, rows13, out13 = fs2_compare(run, nu_l, summary, dump, archive)
    rec2 = json.loads((run2 / "oracle.json").read_text())
    epoch = fs2_epoch([(run.name, rec), (run2.name, rec2)], dump)
    fs1_hashes = json.loads((fs1_run / "oracle.json").read_text())["array_sha256"]
    control = {k: v for k, v in rec["array_sha256"].items() if k.startswith("Perley-Butler_2010")}  # fmt: skip
    rsync_tree = sha256_tree(tables / "rsync-20261102")
    release_tree = sha256_tree(
        tables / "release-2026.10.27-1/casarundata-2026.10.27-1/nrao/VLA/standards"
    )
    # The frozen rule, evaluated on float32(Table 5), independent of the module's flags.
    verdicts = {}
    for src, info in summary.items():
        mine = [r for r in rows if r["source"] == src]
        col = FS2_COLUMN.get(src, src)
        c1 = bool(mine) and all(
            r["float32_of_table5_max_rel_in_range"] <= 1e-6 for r in mine
        )
        c2 = bool(mine) and all(
            r["float32_of_table5_lband_max_ulps"] <= 1 for r in mine
        )
        quv = all(r["casa_quv_zero"] and r["lband_cross_zero"] for r in mine)
        flat = fs2_no_epoch_motion(epoch, col) and not info["epoch_rows_vary"]
        verdicts[src] = {
            "criterion_1": c1, "criterion_2": c2, "quv_zero": quv,
            "epoch_arm_flat": flat, "regular_by_rule": bool(c1 and c2 and quv and flat),
            "kind": info["kind"],
        }  # fmt: skip
    regular = sorted(s for s, v in verdicts.items() if v["regular_by_rule"])
    flagged = sorted(s for (std, s), m in fluxstd.MODELS.items() if std == "Perley-Butler 2017" and m.verified)  # fmt: skip
    rust = rust_parity({"oracle": {"pb2017": archive["pb2017"]}, "lband_freq_hz": archive["lband_freq_hz"]})  # fmt: skip
    acceptance = {
        "pb2010_control_hashes_equal_fs1": all(fs1_hashes.get(k) == v for k, v in control.items()) and len(control) > 0,
        "rsync_tree_identical_to_release": rsync_tree == release_tree,
        "setjy_equals_its_table_pb2017": all(r["fluxd_is_float32"] and r["table_fluxd_max_ulps"] <= 1 and r["table_lband_max_ulps"] == 0 for r in rows),
        "setjy_equals_its_table_pb2013": all(r["fluxd_is_float32"] and r["table_fluxd_max_ulps"] <= 1 and r["table_lband_max_ulps"] == 0 for r in rows13),
        "regular_sources_are_the_rule_set": regular == flagged,
        "regular_sources_port_within_criteria": all(
            r["port_max_rel_in_range"] <= 1e-6 and r["port_lband_max_ulps"] <= 1
            for r in rows if r["source"] in flagged
        ),
        "rust_python_1e-13": rust["max_rel"] <= 1e-13,
        "pb2013_refused": _refuses("3C286", "Perley-Butler 2013"),
    }  # fmt: skip
    result = {
        "task": "FS2 (research/fs2-casarundata.md)",
        "oracle_runs": {"main": str(run), "epoch_post_hoc": str(run2), "fs1_control": str(fs1_run)},
        "casatools": rec["casatools"],
        "image_id": (run / "image-id.txt").read_text().strip(),
        "source": {"rsync": RSYNC, "rsync_files": rsync_tree, "release": RELEASE,
                   "release_version": "casarundata-2026.10.27-1", "paper": PAPER,
                   "table_keywords": {k: v["keywords"] for k, v in dump.items()},
                   "table_rows": {k: v["nrows"] for k, v in dump.items()}},
        "acceptance": acceptance,
        "verdict_pb2017": verdicts,
        "regular_sources": regular,
        "table_vs_table5": summary,
        "comparison_pb2017": rows,
        "outcomes_pb2017": outcomes,
        "comparison_pb2013": rows13,
        "outcomes_pb2013": out13,
        "epoch_frame": epoch,
        "rust_python": rust,
        "array_sha256": rec["array_sha256"],
        "oracle_timing_s": rec["timing"],
        "archive": archive,
    }  # fmt: skip
    out_path.write_text(json.dumps(result, separators=(",", ":")) + "\n")
    print(json.dumps(acceptance, indent=1))
    print("regular by rule:", regular, "flagged in module:", flagged)
    print(
        f"{'source':14s} {'kind':38s} c1 c2 flat | decimals rel/ulps | f32 rel/ulps | port rel/ulps | table rel | range"
    )
    for src, v in verdicts.items():
        mine = [r for r in rows if r["source"] == src]
        if not mine:
            print(src, v["kind"], "no recognised field")
            continue

        def m(key, rows=mine):
            return max(r[key] for r in rows)

        print(
            f"{src:14s} {v['kind']:38s} {v['criterion_1']:d}  {v['criterion_2']:d}  {v['epoch_arm_flat']:d}"
            f" | {m('as_frozen_decimals_max_rel_in_range'):.1e} {m('as_frozen_decimals_lband_max_ulps'):.3g}"
            f" | {m('float32_of_table5_max_rel_in_range'):.1e} {m('float32_of_table5_lband_max_ulps'):.3g}"
            f" | {m('port_max_rel_in_range'):.1e} {m('port_lband_max_ulps'):.3g}"
            f" | {m('table_max_rel_all'):.1e} {m('table_fluxd_max_ulps'):.3g} {m('table_lband_max_ulps'):.3g} {min(r['fluxd_is_float32'] for r in mine):d}"
            f" | {summary[src]['table_range_ghz']} {summary[src]['max_abs_table_minus_table5']:.5f}"
        )
    for r in rows13:
        print(
            "PB2013",
            r["field"],
            f"{r['table_max_rel_all']:.1e} {r['table_fluxd_max_ulps']:.3g} {r['table_lband_max_ulps']:.3g}",
        )
    print(out13)
    print(outcomes)
    return 0 if all(acceptance.values()) else 1


def _refuses(source, standard):
    try:
        fluxstd.flux(source, [1.4e9], standard, unverified_ok=True)
    except ValueError:
        return True
    return False


def main(argv):
    if argv[1] == "--fs2":
        return fs2_main(argv[2:])
    run, dense, ocasa = (Path(a) for a in argv[1:4])
    reread, rerun, out_path = Path(argv[4]), Path(argv[5]), Path(argv[6])
    archive = {"oracle": {}, "dense_1934": {}}
    rows, refusals, pending, frame, rec = compare_oracle(run, archive)
    again = json.loads((rerun / "oracle.json").read_text())["array_sha256"]
    result = {
        "task": "FS1 flux standards (research/fs1-flux-standards.md)",
        "oracle_runs": {
            "main": str(run),
            "dense_1934": str(dense),
            "ocasa": str(ocasa),
            "ocasa_reread": str(reread),
            "rerun_of_main": str(rerun),
        },
        "rerun_arrays_bit_identical": again == rec["array_sha256"],
        "manual_vs_standards_1934": manual_vs_standards(),
        "casatools": rec["casatools"],
        "image_id": (run / "image-id.txt").read_text().strip(),
        "array_sha256": rec["array_sha256"],
        "comparison": rows,
        "unrecognised": refusals,
        "pending_no_table": pending,
        "frame_epoch_check": frame,
        "dense_1934": compare_dense(dense, archive),
        "ocasa_1934": compare_ocasa(ocasa, reread),
        "rust_python": rust_parity(archive),
        "component_builder": builder_check(),
        "breaks_hz": {
            "SR2016": fluxstd.SR2016_BREAK_HZ,
            "PB2010_1934_last_reynolds": 10e9,
        },
        "oracle_timing_s": rec["timing"],
        "archive": archive,
    }
    acceptance = {
        "doubles_1e-6": all(r["max_rel_doubles_in_range"] <= 1e-6 for r in rows),
        "doubles_all_1e-6_with_extrapolate": all(r["max_rel_doubles_all"] <= 1e-6 for r in rows),
        "lband_float32_within_1ulp": all(r["lband_max_ulps"] <= 1 for r in rows),
        "quv_zero": all(r["casa_quv_zero"] and r["lband_cross_zero"] for r in rows),
        "dense_1934_1e-6": all(v["max_rel"] <= 1e-6 for k, v in result["dense_1934"].items() if k != "timing_s"),
        "ocasa_replay_bit_identical": all(result["ocasa_1934"][k]["replay_of_ocasa_reduction_bit_identical"] for k in ("sr2016", "pb2010")),
        "unrecognised_refused": all(r["port_refuses"] for r in refusals),
        "rust_python_1e-13": result["rust_python"]["max_rel"] <= 1e-13,
        "ocasa_rows_port_0_ulps": all(result["ocasa_1934"]["per_row_reread"][k]["row0_vs_port_ulps_max"] == 0 and result["ocasa_1934"]["per_row_reread"][k]["real_rows_identical"] for k in ("fs-sr2016", "fs-pb2010")),
        "rerun_bit_identical": result["rerun_arrays_bit_identical"],
    }  # fmt: skip
    result["acceptance"] = acceptance
    out_path.write_text(json.dumps(result, separators=(",", ":")) + "\n")
    summary = {}
    for r in rows:
        k = (r["standard"], r["canonical"])
        prev = summary.get(k, (0, 0, 0))
        summary[k] = tuple(
            max(a, b)
            for a, b in zip(
                prev,
                (
                    r["max_rel_doubles_in_range"],
                    r["max_rel_doubles_all"],
                    r["lband_max_ulps"],
                ),
            )
        )
    for (std, src), (a, b, c) in sorted(summary.items()):
        print(
            f"{std:26s} {src:9s} doubles in-range {a:.1e} all {b:.1e} lband ulps {c:g}"
        )
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "acceptance",
                    "dense_1934",
                    "rust_python",
                    "component_builder",
                    "frame_epoch_check",
                )
            },
            indent=1,
        )
    )
    print(
        json.dumps(
            {k: v for k, v in result["ocasa_1934"].items() if k != "per_row_reread"},
            indent=1,
        )
    )
    return 0 if all(acceptance.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
