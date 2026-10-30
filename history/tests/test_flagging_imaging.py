import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from rangtoy import flagging_imaging as imaging

# The frozen flagging modules size their writes with os.stat_result.st_blocks,
# which Windows lacks; they cannot change (research/p8-history.md), so these
# tests are skipped there (research/x1-crossplatform.md, task P7).
needs_st_blocks = pytest.mark.skipif(
    sys.platform == "win32", reason="frozen module reads st_blocks (absent on Windows)"
)


@pytest.fixture
def fixture():
    rng = np.random.default_rng(137)
    shape = (6, 64, 4)
    original = np.zeros(shape, bool)
    original[0, 0, 1] = True
    rows = np.zeros(6, bool)
    rows[4] = True
    p, q = np.array([0, 0, 1, 1, 0, 0]), np.array([1, 2, 2, 2, 1, 0])
    support = ~original.any(axis=-1) & ~rows[:, None] & (p != q)[:, None]
    train, test = support.copy(), support.copy()
    train[:, 48:] = False
    test[:, :48] = False
    state = {
        "original_flags": original,
        "original_rows": rows,
        "window": np.ones(64, bool),
        "antenna1": p,
        "antenna2": q,
        "times": np.repeat(np.arange(3), 2),
        "frequencies": np.linspace(1.2e9, 1.3e9, 64),
        "weights": np.ones(shape),
        "train": train,
        "test": test,
        "validation": np.zeros(shape[:2], bool),
    }
    gains = np.broadcast_to(np.eye(2), (2, 2, 3, 2, 2)).astype(complex).copy()
    gains += 0.1 * (rng.normal(size=gains.shape) + 1j * rng.normal(size=gains.shape))
    diag = {"gains": gains, "gain_valid": np.ones(gains.shape[:3], bool)}
    sky = rng.normal(size=(6, 64, 2, 2)) + 1j * rng.normal(size=(6, 64, 2, 2))
    tm, fm = state["times"] // 2, np.arange(64) // 32
    gp, gq = (
        gains[tm[:, None], fm[None], p[:, None]],
        gains[tm[:, None], fm[None], q[:, None]],
    )
    state["data"] = (gp @ sky @ gq.conj().swapaxes(-1, -2)).reshape(shape)
    return state, diag, sky


def test_general_full_jones_inverse_conjugation(fixture):
    state, diag, sky = fixture
    corrected, valid = imaging.corrected_visibilities(state, diag, state["test"])
    assert np.array_equal(valid, state["test"])
    np.testing.assert_allclose(
        corrected[valid].reshape(-1, 2, 2), sky[valid], atol=2e-14
    )
    assert np.all(corrected[~valid] == 0)


@pytest.mark.parametrize("alpha", [-0.5, -0.9])
def test_saved_already_spectral_unit_template_embedded_exactly_once(fixture, alpha):
    state, _, _ = fixture
    support = state["test"]
    reference = 1.25e9
    spatial = np.exp(1j * np.arange(support.size).reshape(support.shape) / 31)
    # Independent provenance convention: response._predict saves this product,
    # not the spatial factor alone. The unit image must forward THIS exact array.
    spectral = spatial * (state["frequencies"][None] / reference) ** alpha
    unit = imaging.unit_template_visibilities(state, spectral, support)
    np.testing.assert_array_equal(unit[..., 0][support], spectral[support])
    np.testing.assert_array_equal(unit[..., 3][support], spectral[support])
    assert not unit[..., 1:3].any() and not unit[~support].any()
    twice = spectral * (state["frequencies"][None] / reference) ** alpha
    assert np.max(np.abs(unit[..., 0][support] - twice[support])) > 1e-3
    low, high = 48, 63
    amplitude_ratio = np.abs(unit[0, high, 0] / spatial[0, high]) / np.abs(
        unit[0, low, 0] / spatial[0, low]
    )
    measured_alpha = np.log(amplitude_ratio) / np.log(
        state["frequencies"][high] / state["frequencies"][low]
    )
    assert measured_alpha == pytest.approx(alpha, abs=1e-13)


def test_unit_template_support_protection_and_nonfinite_heldout_invariance(fixture):
    state, _, _ = fixture
    support = state["test"]
    template = np.ones(support.shape, complex)
    expected = imaging.unit_template_visibilities(state, template, support)
    template[~support] = complex(np.nan, np.inf)
    np.testing.assert_array_equal(
        imaging.unit_template_visibilities(state, template, support), expected
    )
    template[0, 48] = np.nan
    with pytest.raises(ValueError, match="already-spectral"):
        imaging.unit_template_visibilities(state, template, support)
    bad = support.copy()
    bad[0, 0] = True
    with pytest.raises(ValueError, match="original flags"):
        imaging.unit_template_visibilities(state, np.ones(support.shape), bad)


def test_actual_response_template_producer_returns_already_spectral_units(
    fixture, monkeypatch
):
    from rangtoy import flagging_response as response

    state, _, _ = fixture
    uvw = np.zeros((len(state["data"]), 3))

    class Table:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def getcol(self, key):
            assert key == "UVW"
            return uvw

    def table(*args, **kwargs):
        assert kwargs["readonly"] and kwargs["lockoptions"] == "autonoread"
        return Table()

    def predict(
        uvw, lm, kinds, flux, coefficients, logarithmic, reference, shape, frequencies
    ):
        # Zero-baseline point/Gaussian Fourier values are one, independently of
        # the production spatial helper. This isolates actual producer spectra.
        values = sum(
            flux[i] * (frequencies / reference[i]) ** coefficients[i, 0]
            for i in range(len(flux))
        )
        return np.broadcast_to(
            values[None, :, None], (len(uvw), len(frequencies), 1)
        ).copy()

    tables = SimpleNamespace(table=table)
    rime = SimpleNamespace(wsclean_predict=predict)
    monkeypatch.setitem(sys.modules, "casacore", SimpleNamespace(tables=tables))
    monkeypatch.setitem(sys.modules, "casacore.tables", tables)
    monkeypatch.setitem(sys.modules, "africanus", SimpleNamespace(rime=rime))
    monkeypatch.setitem(sys.modules, "africanus.rime", rime)
    templates, predicted, error = response._predict(state, Path("readonly-source"))
    expected = np.broadcast_to(
        np.array(
            [
                (state["frequencies"] / response.REFERENCE_HZ)
                ** source["spectral_index"]
                for source in response.SOURCES
            ]
        )[:, None],
        templates.shape,
    )
    np.testing.assert_array_equal(templates, expected)
    assert error < 1e-12 and predicted.shape == state["data"].shape[:2]
    for index in range(2):
        unit = imaging.unit_template_visibilities(
            state, templates[index], state["test"]
        )
        np.testing.assert_array_equal(
            unit[..., 0][state["test"]], expected[index][state["test"]]
        )


def test_right_unitary_corrected_trace_invariance(fixture):
    state, diag, _ = fixture
    unitary = np.array([[1, 1j], [1j, 1]]) / np.sqrt(2)
    rotated = {**diag, "gains": diag["gains"] @ unitary}
    a, mask = imaging.corrected_visibilities(state, diag, state["test"])
    b, _ = imaging.corrected_visibilities(state, rotated, state["test"])
    np.testing.assert_allclose(
        (a[..., 0] + a[..., 3])[mask], (b[..., 0] + b[..., 3])[mask], atol=2e-14
    )


@pytest.mark.parametrize("bad", ["flag", "singular", "nonfinite", "condition"])
def test_invalid_gain_support_is_missing_not_manufactured(fixture, bad):
    state, diag, _ = fixture
    diag = copy.deepcopy(diag)
    if bad == "flag":
        diag["gain_valid"][0, 1, 0] = False
    elif bad == "singular":
        diag["gains"][0, 1, 0] = 0
    elif bad == "condition":
        diag["gains"][0, 1, 0] = np.diag([1, 1e-10])
    else:
        diag["gains"][0, 1, 0, 0, 0] = np.nan
    corrected, valid = imaging.corrected_visibilities(state, diag, state["test"])
    assert valid.sum() < state["test"].sum()
    assert np.all(corrected[~valid] == 0)


def test_only_explicit_support_values_are_used(fixture):
    state, diag, _ = fixture
    result, _ = imaging.corrected_visibilities(state, diag, state["test"])
    changed = copy.deepcopy(state)
    changed["data"][~state["test"]] = np.nan
    changed["weights"][~state["test"]] = -1
    actual, valid = imaging.corrected_visibilities(changed, diag, state["test"])
    assert np.array_equal(actual, result)
    assert np.array_equal(valid, state["test"])


@pytest.mark.parametrize("key", ["original_flags", "original_rows", "window"])
def test_original_bool_metadata_cannot_be_coerced(fixture, key):
    state, _, _ = fixture
    state = copy.deepcopy(state)
    state[key] = state[key].astype(int)
    with pytest.raises(ValueError, match="bool"):
        imaging.image_flags(state, state["test"])


@pytest.mark.parametrize("cell", [(0, 0), (4, 50), (5, 50)])
def test_image_mask_rejects_original_cells_rows_and_autos(fixture, cell):
    state, _, _ = fixture
    mask = state["test"].copy()
    mask[cell] = True
    with pytest.raises(ValueError, match="original flags/rows/autos/window"):
        imaging.image_flags(state, mask)


def test_flags_keep_originals_and_exact_frozen_support(fixture):
    state, _, _ = fixture
    flags, rows = imaging.image_flags(state, state["test"])
    assert np.all(flags[state["original_flags"]])
    assert np.all(flags[state["original_rows"]])
    assert np.all(rows[state["original_rows"]])
    assert np.array_equal(~flags.any(axis=-1), state["test"])


def test_additions_cannot_flag_heldout_values(fixture):
    state, _, _ = fixture
    with pytest.raises(ValueError, match="TRAIN-only"):
        imaging.image_flags(state, state["test"], state["test"])


def test_wide_decomposition_and_no_source_mutation(fixture):
    state, diag, _ = fixture
    original = copy.deepcopy(state)
    injected = state["data"].astype(np.complex64)
    injected[state["test"]] += np.complex64(0.003 + 0.004j)
    changed = {**diag, "gains": diag["gains"] * 1.003}
    parts, closure = imaging.paired_decomposition(
        state, injected, diag, changed, state["test"]
    )
    assert closure <= imaging.VISIBILITY_CLOSURE_JY
    np.testing.assert_allclose(
        parts["total"], parts["direct"] + parts["adaptation"], atol=2e-14
    )
    assert parts["direct"].dtype == np.complex128
    assert all(np.array_equal(state[k], original[k]) for k in state)


def test_decomposition_refuses_lost_support(fixture):
    state, diag, _ = fixture
    changed = copy.deepcopy(diag)
    changed["gain_valid"][0, 1, 0] = False
    with pytest.raises(ValueError, match="identical complete TEST"):
        imaging.paired_decomposition(state, state["data"], diag, changed, state["test"])


@pytest.mark.parametrize("coeff", [[0.06, 0.12], [-0.06, -0.12], [0, 0]])
def test_known_family_image_fit_is_unrestricted(coeff):
    rng = np.random.default_rng(9)
    templates = rng.normal(size=(2, 8, 8))
    target = np.einsum("s,syx->yx", coeff, templates)
    fit = imaging.linear_image_fit(target, templates)
    assert fit["available"] and fit["rank"] == 2
    np.testing.assert_allclose(fit["coefficients_jy"], coeff, atol=1e-14)
    assert not fit["blind_flux_or_morphology_recovery"]


def test_rank_deficient_image_family_is_unavailable():
    fit = imaging.linear_image_fit(np.ones((8, 8)), np.ones((2, 8, 8)))
    assert not fit["available"] and fit["coefficients_jy"] is None


def test_invalid_image_pixels_are_not_silently_dropped():
    target = np.zeros((8, 8))
    target[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite image"):
        imaging.linear_image_fit(target, np.ones((2, 8, 8)))


def test_frozen_command_is_actual_dirty_only_wstacking():
    command = imaging.wsclean_command("/usr/bin/wsclean", "copy.ms", "image", "temp")
    for key, value in (
        ("-niter", "0"),
        ("-gridder", "wstacking"),
        ("-wstack-nwlayers", "64"),
        ("-j", "1"),
        ("-data-column", "CORRECTED_DATA"),
        ("-abs-mem", "0.5"),
    ):
        assert command[command.index(key) + 1] == value
    assert (
        "-no-update-model-required" in command and "-no-min-grid-resolution" in command
    )
    assert not any(
        key in command
        for key in ("-nwlayers", "-datacolumn", "-absmem", "-no-small-inversion")
    )
    assert command[-1] == "copy.ms" and "-predict" not in command


@pytest.mark.parametrize(
    "returncode,output",
    [
        (0, "dry run completed"),
        (1, "Unknown parameter: datacolumn"),
        (0, "Unknown parameter: datacolumn"),
    ],
)
def test_real_parser_preflight_is_dry_only_and_failure_prevents_ms_mutation(
    tmp_path, monkeypatch, returncode, output
):
    ms = tmp_path / "readonly-input.ms"
    ms.mkdir()
    marker = ms / "original-data"
    marker.write_text("must survive")
    calls = []

    def run(command, **kwargs):
        assert "-dry-run" in command
        assert kwargs == {"capture_output": True, "text": True, "check": False}
        calls.append(command)
        return SimpleNamespace(returncode=returncode, stdout=output, stderr="")

    monkeypatch.setattr(imaging.subprocess, "run", run)
    monkeypatch.setattr(
        imaging,
        "_write_column",
        lambda *a, **k: pytest.fail("MS write during parser preflight"),
    )
    monkeypatch.setattr(
        imaging.Budget,
        "copy",
        lambda *a, **k: pytest.fail("MS copy during parser preflight"),
    )
    if returncode or "Unknown parameter:" in output:
        with pytest.raises(RuntimeError, match="before MS copy/write"):
            imaging.parser_preflight("/usr/bin/wsclean", ms)
    else:
        receipt = imaging.parser_preflight("/usr/bin/wsclean", ms)
        assert receipt["returncode"] == 0 and receipt["dry_run_only"]
        assert receipt["precedes_any_MS_copy_or_write"]
    assert len(calls) == 1 and marker.read_text() == "must survive"


def test_run_parser_failure_precedes_state_load_copy_write_and_output_creation(
    tmp_path, monkeypatch
):
    project = tmp_path / "project"
    response, caracal = project / "outputs/response", project / "outputs/caracal"
    response.mkdir(parents=True)
    caracal.mkdir()
    destination = project / "outputs/fresh"
    monkeypatch.setattr(
        imaging, "__file__", str(project / "python/rangtoy/flagging_imaging.py")
    )
    monkeypatch.setattr(
        imaging.shutil, "disk_usage", lambda _: SimpleNamespace(free=20 * 1024**3)
    )
    monkeypatch.setattr(imaging, "_tool_receipt", lambda: ("/usr/bin/wsclean", {}))
    monkeypatch.setattr(imaging, "_runtime", dict)
    monkeypatch.setattr(imaging, "tree_digest", lambda _: "unchanged")
    monkeypatch.setattr(
        imaging.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=1, stdout="Unknown parameter: datacolumn", stderr=""
        ),
    )
    monkeypatch.setattr(
        imaging,
        "load_state",
        lambda *a, **k: pytest.fail("state loaded after failed parser"),
    )
    monkeypatch.setattr(
        imaging,
        "_write_column",
        lambda *a, **k: pytest.fail("MS write after failed parser"),
    )
    monkeypatch.setattr(
        imaging.Budget,
        "copy",
        lambda *a, **k: pytest.fail("MS copy after failed parser"),
    )
    with pytest.raises(RuntimeError, match="before MS copy/write"):
        imaging.run(destination, response, caracal)
    assert not destination.exists()


def test_fixed_dirty_offsource_diagnostic_is_not_thermal_noise():
    a = imaging.image_diagnostics(np.ones((512, 512)))
    assert a["dirty_offsource_RMS_jy_per_beam"] == 1
    assert a["dirty_offsource_std_jy_per_beam"] == 0
    assert a["fixed_offsource_pixels"] > 100
    assert "not independent thermal" in a["RMS_role"]


@needs_st_blocks
def test_budget_refuses_symlinks_and_reserve(tmp_path, monkeypatch, symlink):
    budget = imaging.Budget(tmp_path)
    monkeypatch.setattr(imaging.shutil, "disk_usage", lambda _: SimpleNamespace(free=1))
    with pytest.raises(RuntimeError, match="8GiB"):
        budget.check()
    monkeypatch.setattr(
        imaging.shutil, "disk_usage", lambda _: SimpleNamespace(free=20 * 1024**3)
    )
    symlink(tmp_path / "bad", tmp_path / "missing")
    with pytest.raises(RuntimeError, match="symlinks"):
        budget.check()


def test_bidirectional_nesting_rejected_before_tool_or_writes(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(
        imaging,
        "_tool_receipt",
        lambda: pytest.fail("tool invoked before nesting preflight"),
    )
    with pytest.raises(ValueError, match="nested|overlap|disjoint"):
        imaging.run(source / "child", source, source)
    assert not (source / "child").exists()
    with pytest.raises(ValueError, match="nested|overlap|disjoint"):
        imaging.run(tmp_path, source, source)


@needs_st_blocks
def test_every_native_column_write_has_exclusive_previous_backup(
    fixture, tmp_path, monkeypatch
):
    state, _, _ = fixture
    root = tmp_path
    (root / "backups").mkdir()
    (root / "checkpoints").mkdir()
    old = np.full(state["data"].shape, 0.02, np.complex64)
    columns = {
        "DATA": state["data"].copy(),
        "FLAG": state["original_flags"].copy(),
        "FLAG_ROW": state["original_rows"].copy(),
        "CORRECTED_DATA": old.copy(),
    }

    class Table:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def colnames(self):
            return list(columns)

        def getcol(self, key):
            return columns[key].copy()

        def putcol(self, key, value):
            assert (root / "backups/job-before.npz").exists()
            assert (root / "backups/job-schema.json").exists()
            assert key != "DATA"
            columns[key] = value.copy()

        def flush(self):
            pass

    tables = SimpleNamespace(
        table=lambda *args, **kwargs: Table(),
        makearrcoldesc=lambda *a, **k: None,
        maketabdesc=lambda x: x,
    )
    monkeypatch.setitem(sys.modules, "casacore", SimpleNamespace(tables=tables))
    monkeypatch.setitem(sys.modules, "casacore.tables", tables)
    budget = imaging.Budget(root)
    wide = np.zeros_like(state["data"])
    wide[state["test"]] = 0.06 + 1e-10j
    audit = imaging._write_column(
        root / "copied.ms", state, wide, state["test"], None, "job", root, budget
    )
    assert audit["original_flags_rows_preserved"]
    assert np.array_equal(columns["DATA"], state["data"])
    with np.load(root / "backups/job-before.npz", allow_pickle=False) as backup:
        assert np.array_equal(backup["CORRECTED_DATA"], old)
        assert np.array_equal(backup["FLAG"], state["original_flags"])
    with pytest.raises(FileExistsError):
        imaging._write_column(
            root / "copied.ms", state, wide, state["test"], None, "job", root, budget
        )


@pytest.mark.parametrize("change", [None, "CDELT1", "CTYPE2", "CRVAL1", "missing"])
def test_image_geometry_frozen_scale_and_axes(change):
    header = {
        "CRPIX1": 257.0,
        "CRPIX2": 257.0,
        "CRVAL1": 0.0,
        "CRVAL2": -30.0,
        "CDELT1": -8 / 3600,
        "CDELT2": 8 / 3600,
        "CTYPE1": "RA---SIN",
        "CTYPE2": "DEC--SIN",
    }
    if change is None:
        assert imaging.image_geometry(header) == header
        return
    if change == "missing":
        del header["CRPIX1"]
    else:
        header[change] = {"CDELT1": -4 / 3600, "CTYPE2": "DEC--TAN", "CRVAL1": np.nan}[
            change
        ]
    with pytest.raises(RuntimeError, match="WCS|scale/axes"):
        imaging.image_geometry(header)


@needs_st_blocks
@pytest.mark.parametrize(
    "change",
    [
        None,
        "CORRECTED_DATA",
        "FLAG",
        "FLAG_ROW",
        "DATA",
        "RANG_MODEL_DATA",
        "WEIGHT_SPECTRUM",
    ],
)
def test_post_wsclean_checks_exact_written_arrays_and_native_columns(
    fixture, tmp_path, monkeypatch, change
):
    state, _, _ = fixture
    original = {
        "DATA": state["data"].copy(),
        "RANG_MODEL_DATA": state["data"].copy(),
        "WEIGHT_SPECTRUM": state["weights"].copy(),
        "FLAG": state["original_flags"].copy(),
        "FLAG_ROW": state["original_rows"].copy(),
    }
    work = copy.deepcopy(original)
    work["FLAG"], work["FLAG_ROW"] = imaging.image_flags(state, state["test"])
    work["CORRECTED_DATA"] = np.zeros_like(state["data"], np.complex64)
    checkpoint = tmp_path / "written.npz"
    imaging.Budget(tmp_path).npz(
        checkpoint, **{key: work[key] for key in ("CORRECTED_DATA", "FLAG", "FLAG_ROW")}
    )
    if change:
        if change == "FLAG":
            work[change][0, 48, 0] = True
        elif change == "FLAG_ROW":
            work[change][0] = True
        else:
            work[change].flat[0] += 1

    class Table:
        def __init__(self, values):
            self.values = values

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def colnames(self):
            return list(self.values)

        def getcol(self, key):
            return self.values[key].copy()

    def table(path, **kwargs):
        assert kwargs["readonly"] and kwargs["lockoptions"] == "autonoread"
        return Table(work if path == "work.ms" else original)

    tables = SimpleNamespace(table=table)
    monkeypatch.setitem(sys.modules, "casacore", SimpleNamespace(tables=tables))
    monkeypatch.setitem(sys.modules, "casacore.tables", tables)
    if change:
        with pytest.raises(RuntimeError, match="imaging changed"):
            imaging._table_audit(
                "work.ms", "input.ms", state, "RANG_MODEL_DATA", checkpoint
            )
    else:
        assert all(
            imaging._table_audit(
                "work.ms", "input.ms", state, "RANG_MODEL_DATA", checkpoint
            ).values()
        )
