"""G6 (research/g6-predict.md): MODEL_DATA from model images through W1's
write-back, with the predictor the gemclean binary uses. The MS and the
model image are written inside the test."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from rang import core_model, core_ms, core_ms_write, core_writeback

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "w1_writeback", ROOT / "examples/w1_writeback.py"
)
w1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w1)

pytestmark = pytest.mark.skipif(
    not core_ms_write.has_creator(), reason="extension built without the table writer"
)

NROW, NCHAN = 60, 8
CENTRE = (0.5, -0.6)


def make_ms(path):
    ms = w1.make_ms(path, NROW, NCHAN, flag="tiled")
    with core_ms_write.open_table(ms / "FIELD", readonly=False) as t:
        t.addrows(2)
        t.putcol("NAME", ["TGT", "OTHER"])
        t.putcol("PHASE_DIR", np.array([[list(CENTRE)], [[0.1, -1.0]]]))
    with core_ms_write.open_table(ms, readonly=False) as t:
        t.putcol("FIELD_ID", (np.arange(NROW) % 3 == 2).astype(np.int32))
    return ms


def write_fits(path, image, scale_deg, centre):
    """A four-axis model image as gemclean writes it (FITS order [y][x])."""
    n = image.shape[0]
    cards = [
        ("SIMPLE", "T"),
        ("BITPIX", "-64"),
        ("NAXIS", "4"),
        ("NAXIS1", str(n)),
        ("NAXIS2", str(n)),
        ("NAXIS3", "1"),
        ("NAXIS4", "1"),
        ("CTYPE1", "'RA---SIN'"),
        ("CRPIX1", f"{n // 2 + 1:.1f}"),
        ("CRVAL1", f"{np.rad2deg(centre[0]):.15E}"),
        ("CDELT1", f"{-scale_deg:.15E}"),
        ("CTYPE2", "'DEC--SIN'"),
        ("CRPIX2", f"{n // 2 + 1:.1f}"),
        ("CRVAL2", f"{np.rad2deg(centre[1]):.15E}"),
        ("CDELT2", f"{scale_deg:.15E}"),
    ]
    text = "".join(f"{k:<8}= {v:>20}".ljust(80) for k, v in cards) + "END".ljust(80)
    text += " " * (-len(text) % 2880)
    data = image.astype(">f8").tobytes()
    data += b"\0" * (-len(data) % 2880)
    Path(path).write_bytes(text.encode() + data)


def model_column(ms, name="MODEL_DATA"):
    with core_ms.open_table(ms) as t:
        return t.getcol(name)


def test_a_centred_point_fills_the_parallel_hands_of_the_field(tmp_path):
    ms = make_ms(tmp_path / "x.ms")
    n = 64
    image = np.zeros((n, n))
    image[n // 2, n // 2] = 2.5
    write_fits(tmp_path / "m-model.fits", image, 2.0 / 3600, CENTRE)
    s = core_model.write_model_data(ms, tmp_path / "m", 0, stage="test")
    assert s["added"] and s["rows_selected"] == s["rows_written"] == 40
    m = model_column(ms)
    field = np.arange(NROW) % 3 == 2  # field 1 rows
    assert np.all(m[field] == 0)  # a column added here starts at zero
    t = m[~field]
    assert np.array_equal(t[..., 0], t[..., 3])
    assert np.all(t[..., 1:3] == 0)
    assert np.allclose(t[..., 0], 2.5, atol=1e-5)
    # Written through WriteBack: a flag backup and a closed journal.
    assert core_writeback.read_journal(ms)["state"] == "closed"
    # Into the existing column again: the same bits, other rows kept.
    with core_writeback.WriteBack(ms, stage="test") as w:
        w.write("MODEL_DATA", 0, np.full((NROW, NCHAN, 4), 7 + 7j, np.complex64))
    core_model.write_model_data(ms, tmp_path / "m", 0, stage="test")
    again = model_column(ms)
    assert np.array_equal(again[~field], t)
    assert np.all(again[field] == 7 + 7j)


def test_channel_range_and_centre_refusal(tmp_path):
    ms = make_ms(tmp_path / "x.ms")
    n = 32
    image = np.zeros((n, n))
    image[n // 2, n // 2] = 1.0
    for k in range(2):
        write_fits(
            tmp_path / f"m-{k:04d}-model.fits", image * (k + 1), 2.0 / 3600, CENTRE
        )
    s = core_model.write_model_data(
        ms, tmp_path / "m", 0, channels_out=2, channel_range=(2, 6), stage="test"
    )
    assert s["channels_predicted"] == 4
    m = model_column(ms)[np.arange(NROW) % 3 != 2]
    assert np.all(m[:, [0, 1, 6, 7]] == 0)
    assert np.allclose(m[:, 2:4, 0], 1.0, atol=1e-5)
    assert np.allclose(m[:, 4:6, 0], 2.0, atol=1e-5)
    write_fits(tmp_path / "far-model.fits", image, 2.0 / 3600, (0.5, -0.5))
    with pytest.raises(ValueError, match="phase centre"):
        core_model.write_model_data(ms, tmp_path / "far", 0, stage="test")
