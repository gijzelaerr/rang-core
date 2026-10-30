"""Check the section 6 prototype against its oracles (research/core-section6.md).

Usage:
    python examples/check_section6.py <prototype-run> <chunk-oracle-dir> <max_rss_mb> outputs/<fresh-check>

Reruns the pass in this process (untimed), compares with every oracle and
writes result.json in the fresh check directory.
"""

import json
import sys
from hashlib import sha256
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prototype_section6 import GRID, ingest, section6_pass
from rangtoy import core
from rangtoy.core_policy import gain_tv, policy_mask, residual_features
from rangtoy.core_workflow import core_solve

ROOT = Path(__file__).resolve().parents[1]
QC = ROOT / "outputs/luno-solve-20261029-02/solve"
MS_ARRAYS = ROOT / "outputs/core-phase2-inputs-20261029-01/arrays.npz"
FIXTURE = ROOT / "outputs/tv-response-wsl-20261029-01/clean"
QC_CHI2 = 0.26823507037914956  # phase 2 archive: fused loss at QuartiCal's gains


def main():
    run, oracle_dir, rss_mb, out = (
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        float(sys.argv[3]),
        Path(sys.argv[4]),
    )
    out.mkdir(parents=True, exist_ok=False)
    proto = json.loads((run / "result.json").read_text())
    receipt = json.loads((run / "receipt.json").read_text())
    checks, passed = {}, {}
    # Criterion 11: ingest.
    oracle = json.loads((oracle_dir / "receipt.json").read_text())["chunks"]
    mismatched = [
        key
        for key, rec in oracle.items()
        if sha256(
            core.blosc_decode(Path(rec["path"].replace("/workspace/", "")).read_bytes())
        ).hexdigest()
        != rec["decoded_sha256"]
    ]
    arrays, _ = ingest()
    with np.load(MS_ARRAYS) as saved:
        ms = {k: saved[k] for k in saved.files}
    equal = {k: bool(np.array_equal(arrays[k], ms[k])) for k in ms}
    checks["11_ingest"] = {
        "chunk_hash_mismatches": mismatched,
        "arrays_equal_ms_built": equal,
    }
    passed["11_ingest"] = not mismatched and all(equal.values())
    products, _ = section6_pass(arrays)
    solution = products["solution"]
    # Criterion 1: gain flags.
    qc_gains = np.load(QC / "gains.npy").astype(np.complex128)
    qc_flagged = np.load(QC / "gain_flags.npy") != 0
    passed["1_gain_flags"] = bool(np.array_equal(solution.flags != 0, qc_flagged))
    # Criterion 2: baseline products on unflagged pairs (stricter than
    # "intervals QuartiCal marks converged", which QuartiCal does not export).
    keep = ~qc_flagged
    worst = 0.0
    for p in range(4):
        for q in range(p + 1, 4):
            pair = keep[..., p] & keep[..., q]
            a = solution.gains[..., p, :, :] @ solution.gains[
                ..., q, :, :
            ].conj().swapaxes(-1, -2)
            b = qc_gains[..., p, :, :] @ qc_gains[..., q, :, :].conj().swapaxes(-1, -2)
            if pair.any():
                worst = max(worst, float(np.abs(a - b)[pair].max()))
    gain_worst = float(np.abs(solution.gains - qc_gains)[keep].max())
    checks["2_gains"] = {"max_product_diff": worst, "max_gain_entry_diff": gain_worst}
    passed["2_gains"] = worst <= 1e-6
    # Criterion 3: chi-squared.
    checks["3_chi2"] = {
        "core": products["chi2"],
        "at_quartical_gains": QC_CHI2,
        "limit": 0.275,
        "logged": 0.27,
    }
    passed["3_chi2"] = products["chi2"] <= 0.275
    # Criterion 4: rank survey.
    survey = products["survey"]
    checks["4_survey"] = survey
    passed["4_survey"] = (
        survey["fully_identified"] == 389
        and survey["underidentified"] == 43
        and survey["no_train"] == 592
        and survey["no_solved_gain"] == 0
        and survey["status"]
        == {"fully_identified status0": 389, "underidentified status3": 43}
    )
    # Criterion 5: antenna-diagonal blocks against the existing full normals.
    nt, nf = products["bins"][2:]
    diag = products["fused"].diag_h.reshape(nt * nf, 4, 8, 8)
    full = products["normals_full"]
    full_diag = np.stack(
        [full[:, 8 * a : 8 * a + 8, 8 * a : 8 * a + 8] for a in range(4)], 1
    )
    scale = float(np.abs(full_diag).max())
    rel5 = float(np.abs(diag - full_diag).max() / scale)
    checks["5_normals"] = {"diag_h_rel": rel5}
    passed["5_normals"] = rel5 <= 1e-13
    # Criterion 6: TV by construction; MAD scores and policy masks for real.
    weights = arrays["WEIGHT_SPECTRUM"]
    p, q = arrays["ANTENNA1"], arrays["ANTENNA2"]
    z_ref = residual_features(
        products["fused"].residuals * np.sqrt(weights), products["train"], p, q
    )
    zdiff = float(np.abs(products["fused"].scores - z_ref).max())
    masks_equal = {
        key: bool(
            np.array_equal(
                mask,
                policy_mask(
                    z_ref,
                    products["guidance"],
                    products["train"],
                    threshold=float(key.split("-")[0][3:]),
                    tv_weight=float(key.split("-")[1][5:]),
                    max_fraction=0.02,
                ),
            )
        )
        for key, mask in products["masks"].items()
    }
    checks["6_tv_mad_policy"] = {
        "tv": "computed by the existing Rust kernel in both paths; equal by construction",
        "max_score_diff": zdiff,
        "masks_equal": masks_equal,
        "mask_counts": {k: int(v.sum()) for k, v in products["masks"].items()},
    }
    passed["6_mad_and_policy"] = zdiff <= 1e-12 and all(masks_equal.values())
    # Criterion 7: fixture clean case (gains as criterion 2, TV vs archive).
    with np.load(FIXTURE / "state.npz") as z:
        state = {k: z[k] for k in z.files}
    with np.load(FIXTURE / "trials/clean-t2-f32/diagnostics.npz") as z:
        fdiag = {
            k: z[k] for k in ("gains", "gain_valid", "gain_times", "gain_frequencies")
        }
    metrics = json.loads((FIXTURE / "trials/clean-t2-f32/metrics.json").read_text())
    fmetrics, _, _, _, fd = core_solve(
        state, np.zeros_like(state["train"]), *GRID, 50, scale=metrics["scale"]
    )
    fkeep = fdiag["gain_valid"]
    fgain = float(np.abs(fd["gains"] - fdiag["gains"])[fkeep].max())
    ftv_rel = abs(fmetrics["tv"] - metrics["tv"]) / metrics["tv"]
    raw = gain_tv(
        fd["gains"],
        fd["gain_valid"],
        fdiag["gain_times"],
        fdiag["gain_frequencies"],
        scale=metrics["scale"],
    )
    checks["7_fixture"] = {
        "gain_valid_equal": bool(np.array_equal(fd["gain_valid"], fkeep)),
        "max_gain_diff": fgain,
        "tv_rel_to_archive": ftv_rel,
        "raw_tv_rel_to_archive": abs(raw["total"] - metrics["raw_tv"])
        / metrics["raw_tv"],
    }
    passed["7_fixture"] = (
        bool(np.array_equal(fd["gain_valid"], fkeep)) and fgain <= 1e-6
    )
    # Criterion 8: runtime excluding decode, peak RSS of the whole pass process.
    checks["8_cost"] = {
        "wall_seconds": proto["wall_seconds"],
        "decode_seconds": proto["decode_seconds"],
        "wall_excluding_decode": proto["wall_seconds_excluding_decode"],
        "max_rss_mb": rss_mb,
        "limits": [2.0, 200.0],
    }
    passed["8_cost"] = proto["wall_seconds_excluding_decode"] <= 2.0 and rss_mb <= 200.0
    # Criterion 9: only the result, the gain export and the receipt.
    files = sorted(x.name for x in run.iterdir())
    checks["9_outputs"] = files
    passed["9_outputs"] = files == ["gains.npz", "receipt.json", "result.json"]
    # Criterion 10: receipt contents.
    passed["10_receipt"] = (
        all(
            k in receipt
            for k in (
                "input_chunk_sha256",
                "code_sha256",
                "settings",
                "oracle_gains_sha256",
            )
        )
        and len(receipt["input_chunk_sha256"]) == 68
    )
    result = {
        "protocol": "research/core-section6.md",
        "passed": passed,
        "all_passed": all(passed.values()),
        "checks": checks,
    }
    (out / "result.json").write_text(json.dumps(result, indent=1, default=float) + "\n")
    print(json.dumps({"all_passed": result["all_passed"], **passed}))
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
