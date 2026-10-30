"""Retrospective, read-only reproduction of the native-support research archive.

Small Jacobians below are algebra checks, not a production calibration kernel.
No download, remote object decoding, flag write, weight fit or solver occurs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import numpy as np

QUANTILES = [0, 0.05, 0.25, 0.5, 0.75, 0.95, 1]
CORRELATIONS = ["XX", "XY", "YX", "YY"]


def _q(values, levels=QUANTILES):
    return np.quantile(values, levels).tolist()


def support_graph(a, b, mask, n_antennas):
    adjacency = [set() for _ in range(n_antennas)]
    for p, q in zip(a[mask], b[mask], strict=True):
        adjacency[int(p)].add(int(q))
        adjacency[int(q)].add(int(p))
    seen, components, nonbipartite = set(), 0, 0
    for p in range(n_antennas):
        if not adjacency[p] or p in seen:
            continue
        components += 1
        seen.add(p)
        queue, colors, bipartite = [p], {p: 0}, True
        for u in queue:
            for v in adjacency[u]:
                if v not in colors:
                    colors[v] = 1 - colors[u]
                    seen.add(v)
                    queue.append(v)
                elif colors[v] == colors[u]:
                    bipartite = False
        nonbipartite += not bipartite
    return {
        "antennas": sum(bool(x) for x in adjacency),
        "edges": sum(map(len, adjacency)) // 2,
        "components": components,
        "bipartite": nonbipartite == 0,
        "unsupported_native_ids": [i for i, x in enumerate(adjacency) if not x],
    }


def sigma_diagnostic(state, scan, pilot_sha256, n_antennas=61):
    a, b, t = state["ANTENNA1"], state["ANTENNA2"], state["TIME"]
    d, s, w = state["DATA"], state["SIGMA_SPECTRUM"], state["WEIGHT_SPECTRUM"]
    flags, rows = state["FLAG"], state["FLAG_ROW"]
    if (
        d.ndim != 3
        or d.shape[-1] != 4
        or any(x.shape != d.shape for x in (s, w, flags))
        or any(x.shape != (len(d),) for x in (a, b, t, rows))
        or flags.dtype != bool
        or rows.dtype != bool
        or np.any(a < 0)
        or np.any(b < 0)
        or np.any(a >= n_antennas)
        or np.any(b >= n_antennas)
    ):
        raise ValueError("Invalid four-correlation native diagnostic layout")
    good = (
        (a != b)[:, None]
        & ~rows[:, None]
        & ~flags.any(-1)
        & np.isfinite(d).all(-1)
        & np.isfinite(s).all(-1)
        & (s > 0).all(-1)
    )
    pairs = good[:, :-1] & good[:, 1:]
    if not good.any() or not pairs.any():
        raise ValueError("No original-protected native sigma/adjacent support")
    baselines = list(zip(*np.triu_indices(n_antennas, 1), strict=True))
    ratios = {}
    for c in (0, 3):
        ratio = w[..., c] * s[..., c] ** 2
        bm = []
        for p, q in baselines:
            selection = (a == p) & (b == q)
            samples = ratio[selection][good[selection]]
            if samples.size:
                bm.append(float(np.median(samples)))
        cm = [
            float(np.median(ratio[:, ch][good[:, ch]]))
            for ch in range(d.shape[1])
            if good[:, ch].any()
        ]
        name = CORRELATIONS[c]
        ratios.update(
            {
                name + "_cell_quantiles": _q(ratio[good]),
                name + "_baseline_median_quantiles": _q(bm),
                name + "_channel_median_quantiles": _q(cm),
                "baseline_medians_count": len(bm),
                "channel_medians_count": len(cm),
            }
        )
    ratios["XY_YX_exact_values"] = np.unique(w[..., 1:3] * s[..., 1:3] ** 2).tolist()
    scales, rms, br, bi, counts = [], [], [], [], []
    for c in range(4):
        delta = d[:, 1:, c] - d[:, :-1, c]
        denominator = np.sqrt(s[:, 1:, c] ** 2 + s[:, :-1, c] ** 2)
        with np.errstate(invalid="ignore", divide="ignore"):
            normalized = delta / denominator
        values = normalized[pairs]
        scales.append(
            [
                float(1.4826 * np.median(np.abs(x - np.median(x))))
                for x in (values.real, values.imag)
            ]
        )
        rms.append(float(np.sqrt(np.mean(np.abs(values) ** 2))))
        baseline_scales = []
        for p, q in baselines:
            selection = (a == p) & (b == q)
            v = normalized[selection][pairs[selection]]
            if v.size >= 16:
                baseline_scales.append(
                    [
                        1.4826 * np.median(np.abs(x - np.median(x)))
                        for x in (v.real, v.imag)
                    ]
                )
        if not baseline_scales:
            raise ValueError("No baseline has the predefined minimum16 adjacent pairs")
        baseline_scales = np.asarray(baseline_scales)
        counts.append(len(baseline_scales))
        br.append(_q(baseline_scales[:, 0], [0.05, 0.5, 0.95]))
        bi.append(_q(baseline_scales[:, 1], [0.05, 0.5, 0.95]))
    if len(set(counts)) != 1:
        raise ValueError("Correlation support unexpectedly differs")
    graph_counts = {
        "total": len(np.unique(t)) * d.shape[1],
        "empty": 0,
        "one_nonbipartite_component": 0,
        "other_nonempty": 0,
        "all60_one_nonbipartite_component": 0,
    }
    for time in np.unique(t):
        for ch in range(d.shape[1]):
            graph = support_graph(a, b, (t == time) & good[:, ch], n_antennas)
            connected = graph["components"] == 1 and not graph["bipartite"]
            label = (
                "empty"
                if graph["antennas"] == 0
                else "one_nonbipartite_component"
                if connected
                else "other_nonempty"
            )
            graph_counts[label] += 1
            graph_counts["all60_one_nonbipartite_component"] += int(
                graph["antennas"] == 60 and connected
            )
    return {
        "scan": scan,
        "pilot_sha256": pilot_sha256,
        "original_unflagged_cross_cells": int(good.sum()),
        "adjacent_pair_count_per_correlation": int(pairs.sum()),
        "sigma_XY_YX_arrays_identical": bool(np.array_equal(s[..., 1], s[..., 2])),
        "sigma_XY_over_YX_quantiles": _q((s[..., 1] / s[..., 2])[good]),
        "WS_times_sigma_squared": ratios,
        "normalized_component_scaledMAD_real_imag_by_corr": scales,
        "normalized_complex_RMS_by_corr": rms,
        "baseline_scaledMAD_minimum_adjacent_pairs": 16,
        "baseline_scaledMAD_count": counts[0],
        "baseline_scaledMAD_real_p5_p50_p95_by_corr": br,
        "baseline_scaledMAD_imag_p5_p50_p95_by_corr": bi,
        "original_support_graph_union": support_graph(a, b, good.any(-1), n_antennas),
        "native_time_channel_graphs": graph_counts,
    }


def _prediction(g, correlations):
    values = (
        np.stack(
            [
                g[p] @ g[q].conj().T
                for p, q in zip(*np.triu_indices(len(g), 1), strict=True)
            ]
        )
        .reshape(-1, 4)[:, correlations]
        .reshape(-1)
    )
    return np.r_[values.real, values.imag]


def gain_jacobian(g, correlations):
    """Analytic tiny diagnostic, not a calibration/simulation production kernel."""
    baselines = list(zip(*np.triu_indices(len(g), 1), strict=True))
    result = np.empty((2 * len(baselines) * len(correlations), 8 * len(g)))
    for k in range(result.shape[1]):
        perturbation = np.zeros_like(g)
        perturbation.reshape(-1)[k // 2] = 1 if k % 2 == 0 else 1j
        delta = (
            np.stack(
                [
                    perturbation[p] @ g[q].conj().T + g[p] @ perturbation[q].conj().T
                    for p, q in baselines
                ]
            )
            .reshape(-1, 4)[:, correlations]
            .reshape(-1)
        )
        result[:, k] = np.r_[delta.real, delta.imag]
    return result


def rank_diagnostic():
    rng, checks = np.random.default_rng(271828), []
    for n in (4, 8):
        generic = rng.normal(size=(n, 2, 2)) + 1j * rng.normal(size=(n, 2, 2))
        identity = np.broadcast_to(np.eye(2), (n, 2, 2)).copy().astype(complex)
        for name, gains in (("identity", identity), ("generic", generic)):
            for correlations in ([0, 3], [0, 1, 2, 3]):
                analytic = gain_jacobian(gains, correlations)
                singular = np.linalg.svd(analytic, compute_uv=False)
                rank = int((singular > 1e-10 * singular[0]).sum())
                finite = np.empty_like(analytic)
                for k in range(8 * n):
                    delta = np.zeros_like(gains)
                    delta.reshape(-1)[k // 2] = 1e-6 if k % 2 == 0 else 1e-6j
                    finite[:, k] = (
                        _prediction(gains + delta, correlations)
                        - _prediction(gains - delta, correlations)
                    ) / 2e-6
                checks.append(
                    {
                        "antennas": n,
                        "parameters": 8 * n,
                        "jones": name,
                        "correlations": correlations,
                        "rank": rank,
                        "nullity": 8 * n - rank,
                        "analytic_central_max_error": float(
                            np.abs(analytic - finite).max()
                        ),
                    }
                )
    return checks


def gauge_diagnostic():
    from rangtoy.core_policy import gain_tv, polar_gauge

    library = os.environ.get("RANG_TOY_LIB")
    if not library or not Path(library).is_file():
        raise ValueError(
            "Set RANG_TOY_LIB to the existing checked Rust library; no build"
        )
    original = np.broadcast_to(np.eye(2), (4, 2, 4, 2, 2)).copy().astype(complex)
    changed, valid = original.copy(), np.ones((4, 2, 4), bool)
    theta = np.array([0.0, 0.3, 0.6, 0.9])
    changed[..., 0, 0] = np.cos(theta)[:, None, None]
    changed[..., 0, 1] = np.sin(theta)[:, None, None]
    predictions = []
    for gains in (original, changed):
        predictions.append(
            np.stack(
                [
                    gains[:, :, p] @ gains[:, :, q].conj().swapaxes(-1, -2)
                    for p, q in zip(*np.triu_indices(4, 1), strict=True)
                ]
            )
        )
    delta = predictions[0] - predictions[1]
    times, frequencies = np.arange(4, dtype=float), np.array([1.07e9, 1.071e9])
    totals = []
    for gains in (original, changed):
        fixed, fixed_valid = polar_gauge(gains, valid)
        if not fixed_valid.all():
            raise ValueError("Diagnostic lost gain support")
        totals.append(gain_tv(fixed, fixed_valid, times, frequencies, scale=1)["total"])
    return {
        "max_parallel_prediction_difference": float(
            np.abs(delta[..., np.arange(2), np.arange(2)]).max()
        ),
        "max_crosshand_prediction_difference": float(np.abs(delta[..., 0, 1]).max()),
        "original_polar_gauge_native_Rust_TV": totals[0],
        "transformed_polar_gauge_native_Rust_TV": totals[1],
        "native_library_sha256": sha256(Path(library).read_bytes()).hexdigest(),
    }


def native_scan_diagnostic(path):
    from casacore.tables import table

    scan = re.fullmatch(r"1672727931_sdp_l0_scan_(\d+)\.ms", path.name)
    if not scan:
        raise ValueError("Unexpected original public scan name")
    with table(str(path), readonly=True, ack=False, lockoptions="autonoread") as source:
        weights, flags, rows = (
            source.getcol("WEIGHT_SPECTRUM"),
            source.getcol("FLAG"),
            source.getcol("FLAG_ROW"),
        )
        if "MODEL_DATA" in source.colnames():
            raise ValueError("Original fixture unexpectedly acquired MODEL_DATA")
        return {
            "scan": int(scan.group(1)),
            "rows": source.nrows(),
            "positive_spectral_weights_per_corr": (weights > 0).sum((0, 1)).tolist(),
            "spectral_zero_or_nonfinite_count": int(
                ((weights == 0) | ~np.isfinite(weights)).sum()
            ),
            "received_flag_fraction": float(flags.mean()),
            "received_FLAG_ROW_count": int(rows.sum()),
        }


def regenerate(template, pilot_dir, native_ms_dir):
    report = deepcopy(template)
    groups = []
    for entry in template["native_sigma_diagnostic"]["groups"]:
        path = pilot_dir / f"scan-{entry['scan']}.npz"
        digest = sha256(path.read_bytes()).hexdigest()
        if digest != entry["pilot_sha256"]:
            raise ValueError("Pinned original pilot digest mismatch")
        with np.load(path, allow_pickle=False) as state:
            groups.append(sigma_diagnostic(state, entry["scan"], digest))
    report["native_sigma_diagnostic"]["groups"] = groups
    report["partial_Jones_identifiability"]["numeric_diagnostic"]["checks"] = (
        rank_diagnostic()
    )
    report["partial_Jones_identifiability"][
        "common_polar_gauge_TV_counterexample"
    ].update(gauge_diagnostic())
    expected = template["candidates"][1]["scans"]
    paths = [native_ms_dir / f"1672727931_sdp_l0_scan_{x['scan']}.ms" for x in expected]
    report["candidates"][1]["scans"] = [native_scan_diagnostic(path) for path in paths]
    report["retrospective_regeneration"] = {
        "implementation_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "implementation_after_original_adhoc_diagnostics": True,
        "static_source_provenance_research_fields_retained_not_requeried": True,
        "solver_or_dataset_mutation": False,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--native-ms-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = regenerate(
        json.loads(args.template.read_bytes()), args.pilot_dir, args.native_ms_dir
    )
    payload = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x") as stream:
            stream.write(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
