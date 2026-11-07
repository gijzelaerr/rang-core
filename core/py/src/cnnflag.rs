//! `rang._core.cnnflag_logits`: the F2 flagger's inference
//! (`rang_core::cnnflag`, task F2, `research/f2-flagger.md`), for
//! `rang.f2flag`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.

use crate::{Ro, Rw, c_slice, c_slice_mut, detach};
use pyo3::prelude::*;
use rang_core::cnnflag::{self, Inputs};

/// Logits `(row, chan)` float32 into `out`: `data` float32 view of
/// complex64 `(row, chan, 4)`, `flags` uint8 `(row, chan)`, `baseline` and
/// `time` uint32 per row, `weights` float32 (2,785). Returns 0, or 1 for bad
/// sizes, 2 for an index out of range.
#[pyfunction]
#[pyo3(signature = (nchan, nbl, ntime, data, flags, baseline, time, weights, out))]
#[allow(clippy::too_many_arguments)]
pub fn cnnflag_logits(
    py: Python<'_>,
    nchan: usize,
    nbl: usize,
    ntime: usize,
    data: Ro<'_, f32>,
    flags: Ro<'_, u8>,
    baseline: Ro<'_, u32>,
    time: Ro<'_, u32>,
    weights: Ro<'_, f32>,
    mut out: Rw<'_, f32>,
) -> PyResult<i32> {
    let inp = Inputs {
        nchan,
        nbl,
        ntime,
        data: c_slice(&data, "data")?,
        flags: c_slice(&flags, "flags")?,
        baseline: c_slice(&baseline, "baseline")?,
        time: c_slice(&time, "time")?,
        weights: c_slice(&weights, "weights")?,
    };
    let out = c_slice_mut(&mut out, "out")?;
    Ok(detach(py, || cnnflag::logits(&inp, out)))
}
