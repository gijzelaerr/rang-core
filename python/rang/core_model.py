"""MODEL_DATA from gemclean's model images through W1's write-back (task G6).

`rang-core image` with `image.write_model: true` runs gemclean with
`-no-update-model-required` (so the binary does not write the MS) and then
calls `write_model_data`, which predicts the model images gemclean wrote
with the same Rust predictor the binary uses (`rang._core.gemclean_predict`,
`rang_core::gemclean::predict`) and writes the column through
`core_writeback.WriteBack` (its lock, journal and flag backup;
research/w1-writeback.md). The rows, blocks and cells are the binary's, so
both paths write the same bits (research/g6-predict.md):

- rows: the field, data description 0, cross-correlations (and the scans of
  `scans`, task W6); flags play no part, as in WSClean;
- cells: XX = YY = I, XY = YX = 0 in every channel with a model; channels
  outside `channel_range` and rows outside the selection keep their values;
- a column added here starts at zero in every row (WSClean's choice, not
  clearcal's unity).
"""

from pathlib import Path

import numpy as np

from . import _core, core_ms, core_writeback

__all__ = ["band", "selected_rows", "write_model_data"]

SELECT_CHUNK = 1 << 20


def band(ms, field, data_desc=0):
    """CHAN_FREQ (the MS's order), CORR_TYPE and the field's PHASE_DIR."""
    ms = Path(ms)
    with core_ms.open_table(ms / "DATA_DESCRIPTION") as dd:
        spw = int(dd.getcol("SPECTRAL_WINDOW_ID")[data_desc])
        pol = int(dd.getcol("POLARIZATION_ID")[data_desc])
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as sw:
        freq = np.ascontiguousarray(sw.getcol("CHAN_FREQ", spw, 1)[0], np.float64)
    with core_ms.open_table(ms / "POLARIZATION") as po:
        corr = [int(c) for c in po.getcol("CORR_TYPE", pol, 1)[0]]
    with core_ms.open_table(ms / "FIELD") as fd:
        if not 0 <= field < fd.nrows:
            raise ValueError(f"field {field} does not exist ({fd.nrows} fields)")
        direction = np.asarray(fd.getcol("PHASE_DIR", field, 1), np.float64).ravel()
    return freq, corr, (float(direction[0]), float(direction[1]))


def selected_rows(ms, field, data_desc=0, scans=None):
    """Rows of `field` on `data_desc` that are cross-correlations (and in
    `scans` when given), in row order: gemclean's selection."""
    out = []
    with core_ms.open_table(ms) as t:
        for start in range(0, t.nrows, SELECT_CHUNK):
            n = min(SELECT_CHUNK, t.nrows - start)
            keep = (
                (t.getcol("FIELD_ID", start, n) == field)
                & (t.getcol("ANTENNA1", start, n) != t.getcol("ANTENNA2", start, n))
                & (t.getcol("DATA_DESC_ID", start, n) == data_desc)
            )
            if scans:
                keep &= np.isin(t.getcol("SCAN_NUMBER", start, n), list(scans))
            out.append(start + np.flatnonzero(keep))
    return np.concatenate(out) if out else np.zeros(0, np.int64)


def _hands(corr):
    def find(codes):
        return next((i for i, c in enumerate(corr) if c in codes), None)

    a, b = find((9, 5)), find((12, 8))
    if a is not None and b is not None:
        return a, b
    i = find((1,))
    if i is not None:
        return i, i
    raise ValueError(f"no XX/YY, RR/LL or I correlations in {corr}")


class _Blocks:
    """Predictions of the selected rows, one block of the binary's size at
    a time, in row order."""

    def __init__(self, w, rows, predict, nchan):
        self.w, self.rows, self.predict = w, rows, predict
        self.size = int(_core.gemclean_block_rows(nchan))
        self.index = -1
        self.block = np.zeros(0, np.int64)
        self.vis = None

    def _load(self, index):
        block = self.rows[index * self.size : (index + 1) * self.size]
        lo, hi = int(block[0]), int(block[-1]) + 1
        uvw = np.ascontiguousarray(
            self.w.read("UVW", lo, hi - lo)[block - lo], np.float64
        )
        self.vis = self.predict(uvw)
        self.block, self.index = block, index

    def rows_in(self, start, n):
        """(rows within [start, start + n), their predictions), loading the
        blocks they are in."""
        lo = np.searchsorted(self.rows, start)
        hi = np.searchsorted(self.rows, start + n)
        rows, values = [], []
        i = lo
        while i < hi:
            index = i // self.size
            if index != self.index:
                self._load(index)
            end = min(hi, (index + 1) * self.size)
            a, b = i - index * self.size, end - index * self.size
            rows.append(self.block[a:b])
            values.append(self.vis[a:b])
            i = end
        if not rows:
            return np.zeros(0, np.int64), None
        return np.concatenate(rows), np.concatenate(values)


def write_model_data(
    ms,
    name,
    field,
    *,
    column="MODEL_DATA",
    data_desc=0,
    scans=None,
    channels_out=1,
    channel_range=None,
    average_channels=1,
    epsilon=1e-6,
    wgridding=True,
    single=False,
    stage="image",
    chunk_rows=None,
):
    """Predict `name`'s model images (`<name>-model.fits`, or
    `<name>-000k-model.fits` with `channels_out` > 1) into `column` of `ms`
    for gemclean's selection, through `WriteBack`. Returns a summary."""
    ms = Path(ms)
    freq, corr, phase_dir = band(ms, field, data_desc)
    a, b = _hands(corr)
    nchan, ncorr = len(freq), len(corr)
    cmap = np.asarray(
        _core.gemclean_channel_map(
            freq,
            int(channels_out),
            None if channel_range is None else tuple(int(v) for v in channel_range),
            int(average_channels),
        )
    )
    mapped = np.flatnonzero(cmap >= 0)
    rows = selected_rows(ms, field, data_desc, scans)
    rng = None if channel_range is None else tuple(int(v) for v in channel_range)

    def predict(uvw):
        out = np.zeros((uvw.shape[0], nchan), np.complex64)
        _core.gemclean_predict(
            str(name),
            int(channels_out),
            rng,
            int(average_channels),
            float(epsilon),
            bool(wgridding),
            bool(single),
            phase_dir,
            uvw,
            freq,
            out,
        )
        return out

    def fill(values, start, n, blocks):
        sel, vis = blocks.rows_in(start, n)
        if vis is None:
            return values, 0
        r = sel - start
        cells = values[r[:, None], mapped[None, :], :]
        cells[...] = 0
        cells[..., a] = vis[:, mapped]
        cells[..., b] = vis[:, mapped]
        values[r[:, None], mapped[None, :], :] = cells
        return values, len(r)

    # Read the images and check their centre before anything is written.
    predict(np.zeros((0, 3), np.float64))
    written = 0
    with core_writeback.WriteBack(ms, stage=stage, chunk_rows=chunk_rows) as w:
        blocks = _Blocks(w, rows, predict, nchan)
        added = column not in w.colnames()
        if added:

            def init(start, n):
                nonlocal written
                values = np.zeros((n, nchan, ncorr), np.complex64)
                values, k = fill(values, start, n, blocks)
                written += k
                return values

            w.ensure_column(column, init=init)
        else:
            w.ensure_column(column, init=None)  # checks type and cell shape
            for start, n in w.chunks():
                lo = np.searchsorted(rows, start)
                if lo == len(rows) or rows[lo] >= start + n:
                    continue
                values = np.array(w.read(column, start, n), np.complex64)
                values, k = fill(values, start, n, blocks)
                written += k
                w.write(column, start, values)
    return {
        "column": column,
        "added": bool(added),
        "rows_selected": len(rows),
        "rows_written": int(written),
        "channels_predicted": len(mapped),
        "model_images": int(channels_out),
        "name": str(name),
        "field": int(field),
        "scans": list(scans) if scans else None,
    }
