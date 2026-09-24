"""Frozen signed-source/sky-completeness/full-Jones gain-flexibility controls.

Known sky is used only in explicitly labelled diagnostic calibration controls
and evaluation. There is no flag-policy search, selection or deployment here.
"""

import json
import os
import shutil
from contextlib import contextmanager
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

import numpy as np

from .flagging import fixed_support_tv
from .flagging_prepared import reject_nested_paths, validate_prepared_state
from .flagging_signal import REFERENCE_HZ, corrected_intensity, spatial_templates
from .flagging_workflow import load_state, solve, tree_digest

SOURCES = (
    {
        "name": "compact",
        "flux_jy": 0.06,
        "l_arcmin": 9.0,
        "m_arcmin": -6.0,
        "fwhm_arcmin": 0.0,
        "spectral_index": -0.5,
    },
    {
        "name": "extended",
        "flux_jy": 0.12,
        "l_arcmin": -12.0,
        "m_arcmin": -14.0,
        "fwhm_arcmin": 8.0,
        "spectral_index": -0.9,
    },
)
GRIDS = ((2, 32), (14, 128))
SIGNS = (("positive", 1), ("negative", -1))
SKIES = ("omitted", "complete-diagnostic")
CONTROL_COLUMN = "RANG_RESPONSE_MODEL"
ALLOCATION_BYTES = 3 * 1024**3 // 2
RESERVE_BYTES = 8 * 1024**3
SOLVE_RESERVATION_BYTES = 80 * 1024**2
CONDITION_LIMIT = 1e8
NATIVE_COLUMNS = ("WEIGHT", "WEIGHT_SPECTRUM", "SIGMA", "SIGMA_SPECTRUM")


def _json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def allocated_bytes(path):
    """Actual allocated filesystem blocks, not a compressed-size forecast."""
    path = Path(path)
    if not path.exists():
        return 0
    total = 0
    for item in (path, *path.rglob("*")):
        if item.is_symlink():
            raise ValueError("symlinks are not allowed in a response output tree")
        stat = item.stat()
        total += getattr(stat, "st_blocks", (stat.st_size + 511) // 512) * 512
    return total


def copy_bound(path):
    """Conservative copy storage including filesystem-block/metadata overhead."""
    path = Path(path)
    total = 0
    for item in (path, *path.rglob("*")) if path.is_dir() else (path,):
        if item.is_symlink():
            raise ValueError("source-copy symlinks are not allowed")
        total += ((item.stat().st_size + 4095) // 4096 + 4) * 4096
    return total


class Budget:
    """Checked allocation budget, NOT an OS-enforced filesystem quota.

    Every local write/copy has a conservative reservation. Shared solve() and
    its native QC writes are a single pre-reserved batch, checked afterwards.
    A breach stops further work; existing/failed artifacts are never erased.
    """

    def __init__(self, root):
        self.root = Path(root).resolve()

    def check(self, needed=0):
        used = allocated_bytes(self.root)
        if needed < 0 or used + needed > ALLOCATION_BYTES:
            raise ValueError("response1.5GiB checked allocation budget exceeded")
        ancestor = self.root
        while not ancestor.exists():
            ancestor = ancestor.parent
        if shutil.disk_usage(ancestor).free < RESERVE_BYTES + needed:
            raise ValueError("response operation would violate8GiB disk reserve")
        return used

    @contextmanager
    def operation(self, needed, label):
        before = self.check(needed)
        yield
        after = self.check()
        if after - before > needed:
            raise ValueError(f"{label} exceeded its reserved allocation; stop work")

    def _target(self, path):
        path = Path(path)
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError("response writes must remain in the exclusive run tree")
        return path

    def mkdir(self, path):
        path = self._target(path)
        with self.operation(64 * 1024, "directory creation"):
            path.mkdir(parents=True, exist_ok=False)

    def copy(self, source, target):
        target = self._target(target)
        with self.operation(copy_bound(source), "copy/backup"):
            if Path(source).is_dir():
                shutil.copytree(source, target)
            else:
                if target.exists():
                    raise ValueError("backup/copy target must be exclusive")
                shutil.copy2(source, target)

    def json(self, path, value):
        path = self._target(path)
        payload = (
            json.dumps(value, indent=2, allow_nan=False, default=_json_default) + "\n"
        )
        with (
            self.operation(len(payload.encode()) + 64 * 1024, "JSON checkpoint"),
            path.open("x") as stream,
        ):
            stream.write(payload)

    def npz(self, path, *, replace_backed_up=False, **arrays):
        path = self._target(path)
        # ZIP/header/DEFLATE expansion, plus filesystem metadata, is reserved.
        needed = int(sum(np.asarray(a).nbytes for a in arrays.values()) * 1.01)
        needed += (len(arrays) + 8) * 8192
        with (
            self.operation(needed, "array checkpoint"),
            path.open("wb" if replace_backed_up else "xb") as stream,
        ):
            np.savez_compressed(stream, **arrays)


def grid_support(state, grid):
    ti, fi = grid
    if any(type(x) is not int or x < 1 for x in grid):
        raise ValueError("positive integer gain grid required")
    times, inverse = np.unique(state["times"], return_inverse=True)
    row, channel = np.where(state["train"])
    if not len(row):
        raise ValueError("TRAIN support must not be empty")
    nf = (len(state["frequencies"]) + fi - 1) // fi
    nt = (len(times) + ti - 1) // ti
    cells = (inverse[row] // ti) * nf + channel // fi
    counts = np.bincount(cells, minlength=nt * nf)
    n_ant = len(state["names"])
    antenna = np.zeros((nt * nf, n_ant), bool)
    antenna[cells, state["antenna1"][row]] = True
    antenna[cells, state["antenna2"][row]] = True
    supported = counts > 0
    return {
        "grid": list(grid),
        "total_time_frequency_bins": nt * nf,
        "TRAIN_time_frequency_bins": int(supported.sum()),
        "TRAIN_antenna_bins": int(antenna.sum()),
        "TRAIN_row_channel_count_min_max": [
            int(counts[supported].min()),
            int(counts[supported].max()),
        ],
        "TRAIN_bins_with_all_antennas": int(
            np.count_nonzero(supported & antenna.all(axis=1))
        ),
        "rank_or_connectivity_certified": False,
    }


def linear_response(intensity, templates, weights, mask):
    """Evaluation-only real coefficients for frozen unit-Jy spectral templates.

    No positivity/bounds, sample rejection, slope fitting, confidence intervals
    or truth-dependent ranking. Rank-deficient flux estimates are unavailable.
    """
    intensity, templates = np.asarray(intensity), np.asarray(templates)
    weights, mask = np.asarray(weights, float), np.asarray(mask)
    if (
        mask.dtype != np.bool_
        or mask.shape != intensity.shape
        or weights.shape != intensity.shape
        or templates.ndim != intensity.ndim + 1
        or templates.shape[1:] != intensity.shape
        or not len(templates)
        or mask.sum() < len(templates)
    ):
        raise ValueError(
            "matched templates/intensity/weights and nonempty bool support"
        )
    if (
        not np.isfinite(intensity[mask]).all()
        or not np.isfinite(templates[:, mask]).all()
        or not np.isfinite(weights[mask]).all()
        or (weights[mask] <= 0).any()
    ):
        raise ValueError("invalid evaluation samples must not be silently discarded")
    design = templates[:, mask].T * np.sqrt(weights[mask, None])
    target = intensity[mask] * np.sqrt(weights[mask])
    matrix = np.concatenate((design.real, design.imag), axis=0)
    vector = np.r_[target.real, target.imag]
    flux, _, rank, singular = np.linalg.lstsq(matrix, vector, rcond=1e-10)
    condition = (
        float(singular[0] / singular[-1])
        if singular.size and singular[-1] > 0
        else None
    )
    available = bool(
        rank == len(templates)
        and condition is not None
        and condition <= CONDITION_LIMIT
    )
    residual = vector - matrix @ flux
    norm = float(vector @ vector)
    return {
        "available": available,
        "rank": int(rank),
        "condition": condition,
        "sample_count": int(mask.sum()),
        "flux_jy": flux.tolist() if available else [None] * len(templates),
        "weighted_mse_proxy": float(residual @ residual / mask.sum()),
        "unexplained_weighted_response_energy_fraction": float(
            residual @ residual / norm
        )
        if norm > 0
        else None,
        "spectral_indices": "fixed evaluation family; not fitted",
        "positivity_or_parameter_bounds": False,
        "confidence_intervals": "not claimed; shared noisy DATA and estimated gains",
    }


def _diagnostics(directory):
    with np.load(Path(directory) / "diagnostics.npz", allow_pickle=False) as saved:
        return {name: saved[name] for name in ("gains", "gain_valid", "edges")}


def _jones_samples(state, diagnostics, grid, row, channel):
    ti, fi = grid
    time = np.unique(state["times"], return_inverse=True)[1][row] // ti
    frequency = channel // fi
    p, q = state["antenna1"][row], state["antenna2"][row]
    gains, valid = diagnostics["gains"], diagnostics["gain_valid"]
    return (
        gains[time, frequency, p],
        gains[time, frequency, q],
        valid[time, frequency, p] & valid[time, frequency, q],
    )


def _correct(data, weights, jones):
    gp, gq, good = jones
    values = corrected_intensity(
        data[:, None], gp[:, None], gq[:, None], good[:, None], weights[:, None]
    )
    return tuple(value[:, 0] for value in values)


def _clone(source, destination, budget):
    budget.mkdir(destination)
    for name in ("manifest.json", "state.npz", "original.ms", "work.ms"):
        budget.copy(source / name, destination / name)
    state = load_state(destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    validate_prepared_state(destination, state, manifest)
    return state, manifest


def _audit_native(directory, state, base_column):
    from casacore.tables import table

    options = {"readonly": True, "ack": False, "lockoptions": "autonoread"}
    with (
        table(str(directory / "original.ms"), **options) as original,
        table(str(directory / "work.ms"), **options) as work,
    ):
        checks = {
            "FLAG_exact_original": np.array_equal(
                work.getcol("FLAG"), original.getcol("FLAG")
            ),
            "FLAG_ROW_exact_original": np.array_equal(
                work.getcol("FLAG_ROW"), original.getcol("FLAG_ROW")
            ),
            "DATA_exact_documented_state": np.array_equal(
                work.getcol("DATA"), state["data"], equal_nan=True
            ),
            "base_model_column_exact": np.array_equal(
                work.getcol(base_column), state["model"], equal_nan=True
            ),
            "native_weight_sigma_exact": all(
                np.array_equal(original.getcol(name), work.getcol(name), equal_nan=True)
                for name in NATIVE_COLUMNS
                if name in original.colnames()
            ),
        }
    if not all(checks.values()):
        raise RuntimeError(f"response native audit failed: {checks}")
    return checks


def _restore_flags(directory, state, budget):
    from casacore.tables import table

    with table(str(directory / "work.ms"), readonly=False, ack=False) as work:
        budget.npz(
            directory / "backups/final-before-flags.npz",
            FLAG=work.getcol("FLAG"),
            FLAG_ROW=work.getcol("FLAG_ROW"),
        )
        with budget.operation(state["original_flags"].nbytes + 1024**2, "flag restore"):
            work.putcol("FLAG", state["original_flags"])
            work.putcol("FLAG_ROW", state["original_rows"])
            work.flush()


def _predict(state, directory):
    from africanus.rime import wsclean_predict
    from casacore.tables import table

    with table(
        str(directory / "work.ms"), readonly=True, ack=False, lockoptions="autonoread"
    ) as work:
        uvw = work.getcol("UVW")
    spatial = spatial_templates(uvw, state["frequencies"], SOURCES)
    spectra = np.asarray(
        [(state["frequencies"] / REFERENCE_HZ) ** s["spectral_index"] for s in SOURCES]
    )
    templates = spatial * spectra[:, None]
    reference = np.sum(
        np.asarray([s["flux_jy"] for s in SOURCES])[:, None, None] * templates, axis=0
    )
    arcmin = np.pi / 10800
    predicted = wsclean_predict(
        uvw,
        np.asarray([[s["l_arcmin"], s["m_arcmin"]] for s in SOURCES]) * arcmin,
        np.asarray(["POINT", "GAUSSIAN"]),
        np.asarray([s["flux_jy"] for s in SOURCES]),
        np.asarray([[s["spectral_index"]] for s in SOURCES]),
        np.ones(len(SOURCES), bool),
        np.full(len(SOURCES), REFERENCE_HZ),
        np.asarray([[s["fwhm_arcmin"] * arcmin] * 2 + [0] for s in SOURCES]),
        state["frequencies"],
    )[..., 0]
    np.testing.assert_allclose(predicted, reference, rtol=1e-11, atol=1e-12)
    return templates, predicted, float(np.max(np.abs(predicted - reference)))


def _inject(source, directory, sign, predicted, reference_gains, budget):
    from casacore.tables import table

    state, manifest = _clone(source, directory, budget)
    budget.mkdir(directory / "backups")
    budget.copy(directory / "work.ms", directory / "backups/work-before-DATA.ms")
    budget.copy(directory / "state.npz", directory / "backups/state-before-DATA.npz")
    eligible = state["train"] | state["validation"] | state["test"]
    row, channel = np.where(eligible)
    gp, gq, good = _jones_samples(state, reference_gains, GRIDS[0], row, channel)
    if not good.all():
        raise ValueError(
            "fine reference gains must support every frozen injection cell"
        )
    delta = (
        gp
        @ (sign * predicted[row, channel, None, None] * np.eye(2))
        @ gq.conj().swapaxes(-1, -2)
    ).reshape(len(row), 4)
    original_data = state["data"]
    new_data = original_data.copy()
    new_data[row, channel] = original_data[row, channel] + delta
    # Difference the two STORED native values in wide precision. Subtracting in
    # complex64 first loses small components and breaks the exact linear
    # inverse-Jones decomposition, even after subsequently casting to complex128.
    actual_delta = np.zeros_like(original_data, dtype=np.complex128)
    actual_delta[row, channel] = new_data[row, channel].astype(
        np.complex128
    ) - original_data[row, channel].astype(np.complex128)
    with table(str(directory / "work.ms"), readonly=False, ack=False) as work:
        before = (work.getcol("FLAG"), work.getcol("FLAG_ROW"))
        budget.npz(
            directory / "backups/DATA-before-flags.npz",
            FLAG=before[0],
            FLAG_ROW=before[1],
        )
        with budget.operation(new_data.nbytes + 1024**2, "DATA injection"):
            work.putcol("DATA", new_data)
            work.flush()
        state["data"] = work.getcol("DATA")
        after = (work.getcol("FLAG"), work.getcol("FLAG_ROW"))
        if not all(np.array_equal(a, b) for a, b in zip(before, after)):
            raise RuntimeError("DATA injection changed flags")
        budget.npz(
            directory / "backups/DATA-after-flags.npz", FLAG=after[0], FLAG_ROW=after[1]
        )
    if not np.array_equal(
        state["data"][~eligible], original_data[~eligible], equal_nan=True
    ):
        raise RuntimeError("DATA injection changed protected samples")
    budget.npz(directory / "state.npz", replace_backed_up=True, **state)
    budget.npz(
        directory / "rounded-injection.npz",
        actual_delta=actual_delta,
        injected=eligible,
    )
    budget.json(
        directory / "injection.json",
        {
            "sign": sign,
            "amplitude": 1.0,
            "eligible_cells": int(eligible.sum()),
            "negative_sign_role": "finite perturbation, not physical negative source flux",
            "reference": "clean fine-grid empirical DI gains, not physical telescope truth",
            "DATA_rounding_linf_jy": float(
                np.max(np.abs(actual_delta[row, channel] - delta))
            ),
            "actual_delta_dtype": str(actual_delta.dtype),
            "actual_delta_precision": "cast stored native DATA values before subtraction",
            "backed_up_before_DATA_write": True,
        },
    )
    validate_prepared_state(directory, state, manifest)
    return state, manifest, actual_delta


def _complete_model(directory, state, manifest, scalar, sign, budget):
    from casacore.tables import makearrcoldesc, maketabdesc, table

    budget.copy(directory / "state.npz", directory / "backups/state-before-model.npz")
    with table(str(directory / "work.ms"), readonly=False, ack=False) as work:
        if CONTROL_COLUMN in work.colnames():
            raise ValueError("complete-sky model column must be new and exclusive")
        budget.json(
            directory / "backups/model-before-schema.json",
            {
                "columns": work.colnames(),
                "table_description": work.getdesc(),
                "base_column": manifest["model_column"],
                "new_column": CONTROL_COLUMN,
            },
        )
        budget.npz(
            directory / "backups/model-before.npz",
            MODEL=work.getcol(manifest["model_column"]),
            FLAG=work.getcol("FLAG"),
            FLAG_ROW=work.getcol("FLAG_ROW"),
        )
        unrounded = state["model"].astype(np.complex128)
        unrounded[..., 0] += sign * scalar
        unrounded[..., 3] += sign * scalar
        expected = unrounded.astype(state["model"].dtype)
        with budget.operation(2 * expected.nbytes + 8 * 1024**2, "new model column"):
            work.addcols(
                maketabdesc(
                    makearrcoldesc(
                        CONTROL_COLUMN,
                        0j,
                        ndim=2,
                        valuetype="complex",
                        datamanagertype="StandardStMan",
                        datamanagergroup=CONTROL_COLUMN,
                    )
                )
            )
            work.putcol(CONTROL_COLUMN, expected)
            work.flush()
        actual = work.getcol(CONTROL_COLUMN)
        if not np.array_equal(work.getcol(manifest["model_column"]), state["model"]):
            raise RuntimeError("complete control changed original calibration model")
    complete_state, complete_manifest = dict(state), dict(manifest)
    complete_state["model"] = actual
    complete_manifest["model_column"] = CONTROL_COLUMN
    complete_manifest["response_control"] = (
        "truth-complete diagnostic, not deployable policy"
    )
    budget.npz(directory / "complete-model.npz", MODEL=actual)
    budget.json(directory / "complete-model-manifest.json", complete_manifest)
    budget.json(
        directory / "model-control.json",
        {
            "role": "truth-complete calibration diagnostic, not deployable policy",
            "original_model_column_unchanged": True,
            "base_model_column": manifest["model_column"],
            "new_model_column": CONTROL_COLUMN,
            "addition_rounding_linf_jy": float(np.max(np.abs(actual - unrounded))),
            "base_model_array_sha256": sha256(state["model"].tobytes()).hexdigest(),
            "complete_model_array_sha256": sha256(actual.tobytes()).hexdigest(),
            "schema_data_and_state_backed_up_before_new_column": True,
        },
    )
    validate_prepared_state(directory, complete_state, complete_manifest)
    return complete_state, complete_manifest


def _solve(directory, state, manifest, trial, grid, budget, scale=None):
    with budget.operation(SOLVE_RESERVATION_BYTES, "QuartiCal solve batch"):
        metrics, tv, _, _ = solve(
            directory,
            state,
            manifest,
            np.zeros_like(state["train"]),
            trial,
            *grid,
            50,
            scale=scale,
        )
    return metrics, tv


def _product_distance(jones, reference, weights, mask):
    gp, gq, _ = jones
    rp, rq, _ = reference
    operator = gp[mask] @ gq[mask].conj().swapaxes(-1, -2)
    target = rp[mask] @ rq[mask].conj().swapaxes(-1, -2)
    error = np.sum(np.abs(operator - target) ** 2, axis=(-1, -2))
    norm = np.sum(np.abs(target) ** 2, axis=(-1, -2))
    denominator = float(np.sum(weights[mask] * norm))
    return (
        float(np.sqrt(np.sum(weights[mask] * error) / denominator))
        if denominator > 0
        else None
    )


def run(run_dir, prepared_dir, iterations=50):
    """Ten frozen actual QC controls; exclusive copies, no policy selection."""
    if type(iterations) is not int or iterations != 50:
        raise ValueError("frozen50-iteration budget required")
    root, source = reject_nested_paths(run_dir, prepared_dir)
    if root.exists() or Path(run_dir).is_symlink():
        raise ValueError("choose a fresh exclusive response run")
    source_state = load_state(source)
    source_manifest = json.loads((source / "manifest.json").read_text())
    boundary = validate_prepared_state(source, source_state, source_manifest)
    if boundary["working_data_differs_from_original"]:
        raise ValueError("response controls require clean, uninjected prepared DATA")
    _audit_native(source, source_state, source_manifest["model_column"])
    times = np.unique(source_state["times"])
    if len(times) != 14 or tuple(source_manifest["split_gain_intervals"]) != GRIDS[0]:
        raise ValueError("frozen14-integration input/fine split grid required")
    for name in ("original.ms", "work.ms", "state.npz", "manifest.json"):
        copy_bound(source / name)
    from casacore.tables import table

    with table(
        str(source / "work.ms"), readonly=True, ack=False, lockoptions="autonoread"
    ) as work:
        if CONTROL_COLUMN in work.colnames():
            raise ValueError("prepared input already has the diagnostic model column")
    budget = Budget(root)
    budget.check(ALLOCATION_BYTES)
    digest = tree_digest(source)
    config = {
        "frozen_before_solve": True,
        "prepared_dir": str(source),
        "prepared_digest": digest,
        "prepared_boundary": boundary,
        "raw_source": source_manifest["source"],
        "raw_source_digest": source_manifest["source_digest"],
        "sources": list(SOURCES),
        "reference_frequency_hz": REFERENCE_HZ,
        "signs": dict(SIGNS),
        "amplitude": 1.0,
        "random_seed": None,
        "split_seed": source_manifest["seed"],
        "grids": [list(g) for g in GRIDS],
        "iterations_budget": iterations,
        "integration_count": len(times),
        "integration_centre_span_seconds": float(times[-1] - times[0]),
        "integration_separations_seconds": np.diff(times),
        "TRAIN_support": [grid_support(source_state, g) for g in GRIDS],
        "planned_QC_solves": 10,
        "added_flags": 0,
        "policy_search_or_selection": False,
        "sky_controls": list(SKIES),
        "complete_control_column": CONTROL_COLUMN,
        "original_model_column_preserved": source_manifest["model_column"],
        "complete_sky_role": "truth-assisted calibration diagnostic, NOT deployable selector",
        "negative_sign_role": "finite perturbation, not physical negative source flux",
        "injection_scope": "intrinsic unpolarized sky, fixed fine-grid empirical DI corruption; no beam/pointing/DDE",
        "evaluation": "fixed-spectrum unrestricted real linear template fit, one commonTEST and fixed fineG0 inverse-Jones nativeweight variance",
        "decomposition": "corrected injected delta + gain-induced correction of SAME original noisy DATA = total paired response",
        "allocation_bytes": ALLOCATION_BYTES,
        "disk_reserve_bytes": RESERVE_BYTES,
        "solver_write_reservation_bytes": SOLVE_RESERVATION_BYTES,
        "quota_semantics": "checked reservations, not OS-enforced quota; stop on observed breach, never erase failed artifacts",
        "module_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "helper_sha256": {
            name: sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
            for name in (
                "flagging.py",
                "flagging_signal.py",
                "flagging_workflow.py",
                "flagging_prepared.py",
            )
        },
        "suite_image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
        "rust_library_sha256": sha256(
            Path(os.environ["RANG_TOY_LIB"]).read_bytes()
        ).hexdigest(),
        "versions": {
            name: version(name)
            for name in (
                "quartical",
                "stimela",
                "numpy",
                "codex-africanus",
                "python-casacore",
            )
        },
    }
    budget.mkdir(root)
    budget.json(root / "response-config.json", config)
    clean_dir = root / "clean"
    clean, manifest = _clone(source, clean_dir, budget)
    baselines = {}
    scale = None
    for grid in GRIDS:
        trial = f"clean-t{grid[0]}-f{grid[1]}"
        metrics, tv = _solve(clean_dir, clean, manifest, trial, grid, budget, scale)
        if scale is None:
            scale = metrics["scale"]
        baselines[grid] = {
            "trial": trial,
            "metrics": metrics,
            "edges": tv["edges"],
            "diagnostics": _diagnostics(clean_dir / "trials" / trial),
        }
    reference_gains = baselines[GRIDS[0]]["diagnostics"]
    templates, predicted, error = _predict(clean, clean_dir)
    budget.npz(root / "spectral-templates.npz", templates=templates)
    budget.json(
        root / "prediction.json",
        {
            "Africanus_vs_bounded_reference_linf_jy": error,
            "fixed_gain_scale": scale,
            "sources": list(SOURCES),
        },
    )
    cases, records = {}, []
    for case_name, sign in SIGNS:
        directory = root / case_name
        state, case_manifest, delta = _inject(
            source, directory, sign, predicted, reference_gains, budget
        )
        cases[case_name] = {
            "state": state,
            "manifest": case_manifest,
            "delta": delta,
            "sign": sign,
        }
        for sky in SKIES:
            control_state, control_manifest = state, case_manifest
            if sky == "complete-diagnostic":
                control_state, control_manifest = _complete_model(
                    directory, state, case_manifest, predicted, sign, budget
                )
            for grid in GRIDS:
                trial = f"{sky}-t{grid[0]}-f{grid[1]}"
                metrics, tv = _solve(
                    directory,
                    control_state,
                    control_manifest,
                    trial,
                    grid,
                    budget,
                    scale,
                )
                record = {
                    "case": case_name,
                    "sign": sign,
                    "sky": sky,
                    "grid": list(grid),
                    "trial": trial,
                    "clean_trial": baselines[grid]["trial"],
                    "metrics": metrics,
                    "fixed_baseline_edge_TV": fixed_support_tv(
                        tv["edges"], baselines[grid]["edges"]
                    ),
                    "diagnostic_only": True,
                    "selected_for_deployment": False,
                }
                budget.json(directory / f"checkpoint-{trial}.json", record)
                records.append(record)
    # All ten arms are complete, without inspecting evaluation losses to choose one.
    budget.json(
        root / "frozen-controls.json",
        {
            "arms": [
                {k: r[k] for k in ("case", "sky", "grid", "trial")} for r in records
            ],
            "policy_search_or_selection": False,
            "test_or_source_truth_used_to_select": False,
        },
    )
    row, channel = np.where(clean["test"])
    native_weights = clean["weights"][row, channel]
    original_data = clean["data"][row, channel]
    ref_jones = _jones_samples(clean, reference_gains, GRIDS[0], row, channel)
    reference = {
        name: _correct(case["delta"][row, channel], native_weights, ref_jones)
        for name, case in cases.items()
    }
    clean_responses = {}
    common = np.ones(len(row), bool)
    for grid, baseline in baselines.items():
        jones = _jones_samples(clean, baseline["diagnostics"], grid, row, channel)
        clean_responses[grid] = {
            "jones": jones,
            "values": _correct(original_data, native_weights, jones),
        }
        common &= clean_responses[grid]["values"][2]
    for value in reference.values():
        common &= value[2]
    evaluated = []
    for record in records:
        grid, case = tuple(record["grid"]), cases[record["case"]]
        jones = _jones_samples(
            case["state"],
            _diagnostics(root / record["case"] / "trials" / record["trial"]),
            grid,
            row,
            channel,
        )
        injected_values = _correct(
            case["state"]["data"][row, channel], native_weights, jones
        )
        direct = _correct(case["delta"][row, channel], native_weights, jones)
        original_under_injected_gains = _correct(original_data, native_weights, jones)
        clean_values = clean_responses[grid]["values"]
        valid = (
            injected_values[2]
            & direct[2]
            & original_under_injected_gains[2]
            & clean_values[2]
        )
        common &= valid
        evaluated.append(
            {
                "record": record,
                "jones": jones,
                "valid": valid,
                "total": injected_values[0] - clean_values[0],
                "direct": direct[0],
                "adaptation": original_under_injected_gains[0] - clean_values[0],
                "variance_ratio": injected_values[1] / clean_values[1],
            }
        )
    if common.sum() < 2 * len(SOURCES):
        raise ValueError(
            "insufficient commonTEST; do not change frozen template family"
        )
    ref_weights = np.where(
        reference["positive"][2], 1 / reference["positive"][1], np.nan
    )
    sample_templates = templates[:, row, channel]
    reference_fits = {
        name: linear_response(values[0], sample_templates, ref_weights, common)
        for name, values in reference.items()
    }
    reports = []
    for evaluated_case in evaluated:
        record = evaluated_case["record"]
        fits = {
            term: linear_response(
                evaluated_case[term], sample_templates, ref_weights, common
            )
            for term in ("total", "direct", "adaptation")
        }
        closure = float(
            np.max(
                np.abs(
                    (
                        evaluated_case["total"]
                        - evaluated_case["direct"]
                        - evaluated_case["adaptation"]
                    )[common]
                )
            )
        )
        if closure > 1e-10:
            raise RuntimeError(
                "inverse-Jones response decomposition failed numerical closure"
            )
        denominator = reference_fits[record["case"]]["flux_jy"]
        fractions = [
            value / control if value is not None and control not in (None, 0) else None
            for value, control in zip(fits["total"]["flux_jy"], denominator)
        ]
        flux_closure = (
            max(
                abs(t - d - a)
                for t, d, a in zip(
                    fits["total"]["flux_jy"],
                    fits["direct"]["flux_jy"],
                    fits["adaptation"]["flux_jy"],
                )
            )
            if all(f["available"] for f in fits.values())
            else None
        )
        if flux_closure is not None and flux_closure > 1e-10:
            raise RuntimeError("linear-template response decomposition failed closure")
        reports.append(
            {
                **record,
                "fits": fits,
                "response_fraction_vs_fixedG0": fractions,
                "visibility_decomposition_closure_linf_jy": closure,
                "linear_fit_decomposition_closure_linf_jy": flux_closure,
                "unsupported_original_TEST_samples": int(
                    (~evaluated_case["valid"]).sum()
                ),
                "corrected_variance_ratio_median": float(
                    np.median(evaluated_case["variance_ratio"][common])
                ),
                "baseline_Jones_product_relative_drift_vs_same_grid_clean": _product_distance(
                    evaluated_case["jones"],
                    clean_responses[tuple(record["grid"])]["jones"],
                    ref_weights,
                    common,
                ),
                "baseline_Jones_product_relative_error_vs_empirical_fineG0": _product_distance(
                    evaluated_case["jones"], ref_jones, ref_weights, common
                ),
            }
        )
    audits = {}
    for name, state, case_manifest in (
        ("clean", clean, manifest),
        *((name, case["state"], case["manifest"]) for name, case in cases.items()),
    ):
        directory = root / name
        _restore_flags(directory, state, budget)
        audits[name] = {
            **_audit_native(directory, state, manifest["model_column"]),
            "prepared_boundary": validate_prepared_state(
                directory, state, case_manifest
            ),
        }
        if name != "clean":
            with (
                table(
                    str(directory / "work.ms"),
                    readonly=True,
                    ack=False,
                    lockoptions="autonoread",
                ) as work,
                np.load(
                    directory / "complete-model.npz", allow_pickle=False
                ) as snapshot,
            ):
                unchanged = np.array_equal(
                    work.getcol(CONTROL_COLUMN), snapshot["MODEL"]
                )
            if not unchanged:
                raise RuntimeError("native solve changed complete diagnostic model")
            audits[name]["complete_model_column_exact_snapshot"] = True
    source_checks = {
        "prepared_source_unchanged": tree_digest(source) == digest,
        "raw_source_unchanged": tree_digest(source_manifest["source"])
        == source_manifest["source_digest"],
        "module_unchanged": sha256(Path(__file__).read_bytes()).hexdigest()
        == config["module_sha256"],
        "all_helper_modules_unchanged": all(
            sha256((Path(__file__).parent / name).read_bytes()).hexdigest() == expected
            for name, expected in config["helper_sha256"].items()
        ),
        "native_library_unchanged": sha256(
            Path(os.environ["RANG_TOY_LIB"]).read_bytes()
        ).hexdigest()
        == config["rust_library_sha256"],
    }
    if not all(source_checks.values()):
        raise RuntimeError("response source tree changed")
    result = {
        "status": "measured conditional signed-source calibration-response diagnostic; no deployment/images",
        "configuration": config,
        "baselines": [
            {"grid": list(g), "trial": b["trial"], "metrics": b["metrics"]}
            for g, b in baselines.items()
        ],
        "reference_fits": reference_fits,
        "methods": reports,
        "common_TEST_samples": int(common.sum()),
        "original_TEST_samples": len(row),
        "lost_common_TEST_samples": int((~common).sum()),
        "actual_QC_diagnostic_solves": 10,
        "native_flagger_solves": 0,
        "added_flags": 0,
        "policy_search_or_selection": False,
        "audit": {**source_checks, "copies": audits},
        "imaging": "not measured; visibility-template and gain-product diagnostics only",
        "limitations": [
            "four-antenna dedicated pointing fixture and reused split, not independent transfer",
            "empirical fineG0 DI injection without beam/pointing/DDE or independent noise",
            "negative sign is a finite perturbation, not a physical negative source",
            "complete sky uses known injection truth as a calibration diagnostic, not a deployable selector",
            "known source locations/extents/spectra constrain evaluation; no blind imaging/flux/CI claim",
            "coarse grid may underfit legitimate gains; cross-grid rawTV is not matched-support quality",
            "allocation is checked, not an OS-enforced quota; emulated timings are not native cost",
        ],
    }
    budget.json(root / "response-audit.json", result["audit"])
    budget.json(root / "result.json", result)
    budget.check()
    print(
        f"Response controls complete:10QC, commonTEST={common.sum()}, no added flags/images",
        flush=True,
    )
    return result
