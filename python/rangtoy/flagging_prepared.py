"""Read-only boundary validation before any copied prepared-MS flag writes.

The actual immutable original is authoritative for original flags and weights;
the saved state is never sufficient evidence of Observatory flag preservation.
Documented injections may change working DATA, but not flags, weights or splits.
"""

from pathlib import Path

import numpy as np

from .flagging import require_meerkat_lband


def reject_nested_paths(run_dir, prepared_dir):
    """Reject either ancestor relationship, including equality, before mkdir."""
    output, source = Path(run_dir).resolve(), Path(prepared_dir).resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("prepared input and output paths must not be nested")
    return output, source


def _equal(left, right):
    left, right = np.asarray(left), np.asarray(right)
    if left.shape != right.shape:
        return False
    if left.dtype.kind in "fc" and right.dtype.kind in "fc":
        return bool(np.array_equal(left, right, equal_nan=True))
    return bool(np.array_equal(left, right))


def _require_equal(left, right, label):
    if not _equal(left, right):
        raise ValueError(f"prepared boundary mismatch: {label}")


def _bool_shape(value, shape, label):
    value = np.asarray(value)
    if value.dtype != np.bool_ or value.shape != shape:
        raise ValueError(f"prepared {label} requires bool shape {shape}")
    return value


def validate_prepared_arrays(state, original, work, metadata):
    """Pure boundary validator, usable without casacore.

    ``original``/``work`` have data, flags, rows, weights, times, antenna1/2;
    ``work`` also has model. Metadata maps original/work to telescope,
    frequencies, names, correlations and spw_rows read from their actual MS.
    Original DATA can differ from state/work DATA after a recorded injection.
    """
    data = np.asarray(state["data"])
    if data.ndim != 3 or data.shape[-1] != 4 or not np.iscomplexobj(data):
        raise ValueError("prepared DATA requires row/channel/four complex correlations")
    row_channel = data.shape[:2]
    flags = _bool_shape(state["original_flags"], data.shape, "original flags")
    rows = _bool_shape(state["original_rows"], (len(data),), "original rows")
    _require_equal(original["flags"], flags, "original FLAG")
    _require_equal(original["rows"], rows, "original FLAG_ROW")
    original_data = np.asarray(original["data"])
    if original_data.shape != data.shape:
        raise ValueError("prepared original DATA shape differs")
    _require_equal(work["data"], data, "working DATA")
    work_flags = _bool_shape(work["flags"], data.shape, "working flags")
    work_rows = _bool_shape(work["rows"], (len(data),), "working rows")
    if np.any(flags & ~work_flags) or np.any(rows & ~work_rows):
        raise ValueError("prepared working flags violate original protection")
    weights = np.asarray(state["weights"])
    if weights.shape != data.shape or weights.dtype.kind not in "fi":
        raise ValueError("prepared native weights require full-correlation real shape")
    _require_equal(original["weights"], weights, "original native weights")
    _require_equal(work["weights"], weights, "working native weights")
    model = np.asarray(state["model"])
    if model.shape != data.shape or not np.isfinite(model).all():
        raise ValueError("prepared model requires finite four-correlation shape")
    _require_equal(work["model"], model, "working model")
    if not (
        np.allclose(model[..., 1:3], 0) and np.allclose(model[..., 0], model[..., 3])
    ):
        raise ValueError("prepared polar gauge requires an unpolarized scalar model")
    frequencies = np.asarray(state["frequencies"])
    if frequencies.shape != (data.shape[1],):
        raise ValueError("prepared frequency shape differs from DATA")
    names = np.asarray(state["names"])
    if names.ndim != 1 or not len(names) or len(np.unique(names)) != len(names):
        raise ValueError("prepared antenna names must be nonempty and unique")
    scopes = {}
    for label, actual in (("original", original), ("work", work)):
        observed = metadata[label]
        scopes[label] = require_meerkat_lband(
            observed["telescope"], observed["frequencies"]
        )
        if observed["spw_rows"] != 1 or not _equal(
            observed["correlations"], [[9, 10, 11, 12]]
        ):
            raise ValueError(
                "prepared full-Jones input requires one SPW and XX XY YX YY"
            )
        _require_equal(observed["frequencies"], frequencies, f"{label} frequencies")
        _require_equal(observed["names"], names, f"{label} antenna names")
        for field in ("times", "antenna1", "antenna2"):
            if np.asarray(state[field]).shape != (len(data),):
                raise ValueError(f"prepared {field} row shape differs")
            _require_equal(actual[field], state[field], f"{label} {field}")
        for field in ("scan", "field", "descriptor"):
            # Pure callers may omit partition metadata. The MS wrapper always
            # supplies it; QuartiCal's mapping assumes a single partition.
            if field in actual and len(np.unique(actual[field])) != 1:
                raise ValueError(
                    "prepared input requires one scan, field and descriptor"
                )
    times = np.asarray(state["times"])
    p, q = np.asarray(state["antenna1"]), np.asarray(state["antenna2"])
    if not np.isfinite(times).all() or any(
        antenna.dtype.kind not in "iu"
        or np.any(antenna < 0)
        or np.any(antenna >= len(names))
        for antenna in (p, q)
    ):
        raise ValueError("prepared time/antenna coordinates are invalid")
    window = _bool_shape(state["window"], (data.shape[1],), "channel window")
    masks = {
        key: _bool_shape(state[key], row_channel, f"{key} split")
        for key in ("train", "validation", "test")
    }
    if np.any(
        (masks["train"] & (masks["validation"] | masks["test"]))
        | (masks["validation"] & masks["test"])
    ):
        raise ValueError("prepared train/validation/test masks overlap")
    eligible = ~flags.any(axis=-1) & ~rows[:, None] & (p != q)[:, None]
    eligible &= window[None] & np.isfinite(data).all(axis=-1)
    eligible &= np.isfinite(original_data).all(axis=-1)
    eligible &= np.isfinite(weights).all(axis=-1) & (weights > 0).all(axis=-1)
    for key, mask in masks.items():
        if np.any(mask & ~eligible):
            raise ValueError(
                f"prepared {key} split includes protected/ineligible samples"
            )
        if not mask.any():
            raise ValueError(f"prepared {key} split is empty")
    return {
        "validated": True,
        "actual_scope": scopes["original"],
        "original_flags_and_rows_match": True,
        "original_and_work_native_weights_match": True,
        "work_data_matches_state": True,
        "work_model_matches_state": True,
        "model_scalar_unpolarized": True,
        "split_masks_disjoint_and_eligible": True,
        "split_counts": {key: int(mask.sum()) for key, mask in masks.items()},
        "working_data_differs_from_original": not _equal(original["data"], data),
    }


def validate_prepared_manifest(state, manifest):
    """Require manifest channel/split/grid provenance to describe actual state."""
    integer = lambda value: (
        isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_))
    )
    intervals = manifest.get("split_gain_intervals", ())
    if len(intervals) != 2 or any(not integer(x) or x < 1 for x in intervals):
        raise ValueError("prepared gain intervals require two positive integers")
    window = np.asarray(state["window"])
    if window.ndim != 1 or window.dtype != np.bool_:
        raise ValueError("prepared channel window requires a one-dimensional bool mask")
    channels = manifest.get("channels", ())
    if (
        len(channels) != 2
        or any(not integer(x) for x in channels)
        or not 0 <= channels[0] < channels[1] <= len(window)
    ):
        raise ValueError("prepared manifest channels require valid integer bounds")
    expected_window = np.zeros_like(window)
    expected_window[channels[0] : channels[1]] = True
    _require_equal(window, expected_window, "manifest channel window")
    counts = manifest.get("split_counts", {})
    if set(counts) != {"train", "validation", "test"}:
        raise ValueError(
            "prepared manifest requires train/validation/test split counts"
        )
    for key, count in counts.items():
        if not integer(count) or count != np.count_nonzero(state[key]):
            raise ValueError(f"prepared manifest {key} split count differs from state")
    return {
        "manifest_channels_and_split_counts_match": True,
        "positive_gain_intervals_validated": True,
    }


def _read_measurement_set(path, model_column=None):
    """Read actual boundaries without writable table handles or locking writes."""
    from casacore.tables import table

    path = Path(path)
    options = {"readonly": True, "ack": False, "lockoptions": "autonoread"}
    with table(str(path), **options) as main:
        arrays = {
            key: main.getcol(column)
            for key, column in (
                ("data", "DATA"),
                ("flags", "FLAG"),
                ("rows", "FLAG_ROW"),
                ("times", "TIME"),
                ("antenna1", "ANTENNA1"),
                ("antenna2", "ANTENNA2"),
                ("scan", "SCAN_NUMBER"),
                ("field", "FIELD_ID"),
                ("descriptor", "DATA_DESC_ID"),
            )
        }
        arrays["weights"] = (
            main.getcol("WEIGHT_SPECTRUM")
            if "WEIGHT_SPECTRUM" in main.colnames()
            else np.broadcast_to(main.getcol("WEIGHT")[:, None], arrays["data"].shape)
        )
        if model_column is not None:
            arrays["model"] = main.getcol(model_column)
    with table(str(path / "OBSERVATION"), **options) as observation:
        telescope = observation.getcol("TELESCOPE_NAME")
    with table(str(path / "SPECTRAL_WINDOW"), **options) as spw:
        spw_rows = spw.nrows()
        if spw_rows != 1:
            raise ValueError("prepared full-Jones input requires one SPW")
        frequencies = spw.getcol("CHAN_FREQ")[0]
    with table(str(path / "ANTENNA"), **options) as antennas:
        names = antennas.getcol("NAME")
    with table(str(path / "POLARIZATION"), **options) as polarization:
        correlations = polarization.getcol("CORR_TYPE")
    return arrays, {
        "telescope": telescope,
        "frequencies": frequencies,
        "names": names,
        "correlations": correlations,
        "spw_rows": spw_rows,
    }


def validate_prepared_state(run_dir, state, manifest):
    """Lazy-casacore, read-only boundary audit before any solve/flag writes."""
    from .flagging_workflow import tree_digest

    run_dir = Path(run_dir).resolve()
    original_digest = tree_digest(run_dir / "original.ms")
    if original_digest != manifest["original_copy_digest"]:
        raise ValueError("prepared original MS digest differs from manifest")
    manifest_audit = validate_prepared_manifest(state, manifest)
    original, original_metadata = _read_measurement_set(run_dir / "original.ms")
    work, work_metadata = _read_measurement_set(
        run_dir / "work.ms", manifest["model_column"]
    )
    audit = validate_prepared_arrays(
        state,
        original,
        work,
        {"original": original_metadata, "work": work_metadata},
    )
    return {
        **audit,
        **manifest_audit,
        "original_copy_digest_verified": True,
        "original_copy_digest": original_digest,
    }
