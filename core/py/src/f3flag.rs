//! `rang._core.f3flag_features` and `f3flag_logits`: the F3 flagger
//! (`rang_core::f3flag`, task F3, `research/f3-flagger.md`), for
//! `rang.f3flag`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.

use crate::{Ro, Rw, c_slice, c_slice_mut, detach};
use pyo3::prelude::*;
use rang_core::f3flag::{self, Inputs};

/// Input planes `(nsel, ntime, nchan, 15)` float32 of the baselines
/// `select` into `out`: `data` float32 view of complex64 `(row, chan, 4)`,
/// `flags` uint8 `(row, chan)`, `baseline` and `time` uint32 per row,
/// `ant1`, `ant2` uint32 per baseline. Returns 0, 1 for bad sizes, 2 for an
/// index out of range.
#[pyfunction]
#[pyo3(signature = (nchan, nbl, ntime, nant, data, flags, baseline, time, ant1, ant2, select, out))]
#[allow(clippy::too_many_arguments)]
pub fn f3flag_features(
    py: Python<'_>,
    nchan: usize,
    nbl: usize,
    ntime: usize,
    nant: usize,
    data: Ro<'_, f32>,
    flags: Ro<'_, u8>,
    baseline: Ro<'_, u32>,
    time: Ro<'_, u32>,
    ant1: Ro<'_, u32>,
    ant2: Ro<'_, u32>,
    select: Ro<'_, u32>,
    mut out: Rw<'_, f32>,
) -> PyResult<i32> {
    let inp = Inputs {
        nchan,
        nbl,
        ntime,
        nant,
        data: c_slice(&data, "data")?,
        flags: c_slice(&flags, "flags")?,
        baseline: c_slice(&baseline, "baseline")?,
        time: c_slice(&time, "time")?,
        ant1: c_slice(&ant1, "ant1")?,
        ant2: c_slice(&ant2, "ant2")?,
    };
    let select = c_slice(&select, "select")?;
    let out = c_slice_mut(&mut out, "out")?;
    Ok(detach(py, || f3flag::features(&inp, select, out)))
}

/// Logits `(row, chan)` float32 into `out`; `weights` float32 (3,433).
/// Returns 0, 1 for bad sizes, 2 for an index out of range.
#[pyfunction]
#[pyo3(signature = (nchan, nbl, ntime, nant, data, flags, baseline, time, ant1, ant2, weights, out))]
#[allow(clippy::too_many_arguments)]
pub fn f3flag_logits(
    py: Python<'_>,
    nchan: usize,
    nbl: usize,
    ntime: usize,
    nant: usize,
    data: Ro<'_, f32>,
    flags: Ro<'_, u8>,
    baseline: Ro<'_, u32>,
    time: Ro<'_, u32>,
    ant1: Ro<'_, u32>,
    ant2: Ro<'_, u32>,
    weights: Ro<'_, f32>,
    mut out: Rw<'_, f32>,
) -> PyResult<i32> {
    let inp = Inputs {
        nchan,
        nbl,
        ntime,
        nant,
        data: c_slice(&data, "data")?,
        flags: c_slice(&flags, "flags")?,
        baseline: c_slice(&baseline, "baseline")?,
        time: c_slice(&time, "time")?,
        ant1: c_slice(&ant1, "ant1")?,
        ant2: c_slice(&ant2, "ant2")?,
    };
    let weights = c_slice(&weights, "weights")?;
    let out = c_slice_mut(&mut out, "out")?;
    Ok(detach(py, || f3flag::logits(&inp, weights, out)))
}
