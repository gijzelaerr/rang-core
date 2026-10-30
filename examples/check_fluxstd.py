"""FS1: compare rangtoy.fluxstd with the CASA setjy oracle and write the archive.

Usage (from the checkout, host venv):

    python examples/check_fluxstd.py outputs/fs1-20261030-01 outputs/fs1-20261030-03 \
        outputs/o-casa-20261030-01 outputs/fs1-20261030-02/ocasa-model-check.json \
        research/results/fs1-flux-standards.json

Inputs: the main oracle run (`oracle_setjy.py`), the dense 1934-638 run
(`--dense-1934`), the O-CASA run (its `fs-*-stokes-i.npy`, `chan-freq.npy`)
and the per-row re-read of O-CASA's `fs-*.ms` MODEL_DATA. Reads only; writes
the compact archive (research/fs1-flux-standards.md, "Acceptance").
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from rangtoy import fluxstd

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


def compare_ocasa(ocasa, check_json):
    freq = np.load(ocasa / "chan-freq.npy")
    out = {"per_row_reread": json.loads(Path(check_json).read_text())}
    port = fluxstd.flux("1934-638", freq, "Stevens-Reynolds 2016")[:, 0]
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


def builder_check():
    from rangtoy import lsm

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
        from rangtoy import core

        vis = core.predict_components(np.array([[100.0, 50.0, 0.0]]), nu, **comps)
        out["core_predict_manual_max_rel"] = rel(
            vis[0].real, fluxstd.manual(nu, **fluxstd.CARACAL_1934)
        )
    except (ImportError, RuntimeError, AttributeError) as error:
        out["core_predict_manual_max_rel"] = f"skipped: {error}"
    return out


def main(argv):
    run, dense, ocasa = (Path(a) for a in argv[1:4])
    check_json, out_path = argv[4], Path(argv[5])
    archive = {"oracle": {}, "dense_1934": {}}
    rows, refusals, pending, frame, rec = compare_oracle(run, archive)
    result = {
        "task": "FS1 flux standards (research/fs1-flux-standards.md)",
        "oracle_runs": {
            "main": str(run),
            "dense_1934": str(dense),
            "ocasa": str(ocasa),
        },
        "casatools": rec["casatools"],
        "image_id": (run / "image-id.txt").read_text().strip(),
        "array_sha256": rec["array_sha256"],
        "comparison": rows,
        "unrecognised": refusals,
        "pending_no_table": pending,
        "frame_epoch_check": frame,
        "dense_1934": compare_dense(dense, archive),
        "ocasa_1934": compare_ocasa(ocasa, check_json),
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
