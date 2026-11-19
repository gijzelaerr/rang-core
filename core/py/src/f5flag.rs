// SPDX-License-Identifier: MIT
//! `rang._core.f5flag_features`, `f5flag_logits` and `f5flag_anomaly`: the
//! F5 flagger (`rang_core::f5flag`, task F5, `research/f5-flagger.md`), for
//! `rang.f5flag`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.

use crate::{Ro, Rw, c_slice, c_slice_mut, detach};
use pyo3::prelude::*;
use rang_core::f5flag::{self, Inputs};

#[allow(clippy::too_many_arguments)]
fn inputs<'a>(
    nchan: usize,
    nbl: usize,
    ntime: usize,
    nant: usize,
    data: &'a Ro<'_, f32>,
    flags: &'a Ro<'_, u8>,
    baseline: &'a Ro<'_, u32>,
    time: &'a Ro<'_, u32>,
    ant1: &'a Ro<'_, u32>,
    ant2: &'a Ro<'_, u32>,
) -> PyResult<Inputs<'a>> {
    Ok(Inputs {
        nchan,
        nbl,
        ntime,
        nant,
        data: c_slice(data, "data")?,
        flags: c_slice(flags, "flags")?,
        baseline: c_slice(baseline, "baseline")?,
        time: c_slice(time, "time")?,
        ant1: c_slice(ant1, "ant1")?,
        ant2: c_slice(ant2, "ant2")?,
    })
}

/// Input planes `(nsel, ntime, nchan, n)` float32 of the baselines `select`
/// into `out`, n = 33, 29 or 21 for ladder level 0, 1 or 2; `degree` the fit
/// degree (1-3). Arrays as `f4flag_features`. Returns 0, 1 for bad sizes, 2
/// for an index out of range, 3 for a bad level or degree.
#[pyfunction]
#[pyo3(signature = (nchan, nbl, ntime, nant, data, flags, baseline, time, ant1, ant2, level, degree, select, out))]
#[allow(clippy::too_many_arguments)]
pub fn f5flag_features(
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
    level: usize,
    degree: usize,
    select: Ro<'_, u32>,
    mut out: Rw<'_, f32>,
) -> PyResult<i32> {
    let inp = inputs(
        nchan, nbl, ntime, nant, &data, &flags, &baseline, &time, &ant1, &ant2,
    )?;
    let select = c_slice(&select, "select")?;
    let out = c_slice_mut(&mut out, "out")?;
    Ok(detach(py, || {
        f5flag::features(&inp, level, degree, select, out)
    }))
}

/// Logits `(row, chan)` float32 into `out`; `weights` float32 in
/// `rang.f5net`'s flat order (3,201 at level 0). Returns as
/// `f5flag_features`.
#[pyfunction]
#[pyo3(signature = (nchan, nbl, ntime, nant, data, flags, baseline, time, ant1, ant2, level, degree, weights, out))]
#[allow(clippy::too_many_arguments)]
pub fn f5flag_logits(
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
    level: usize,
    degree: usize,
    weights: Ro<'_, f32>,
    mut out: Rw<'_, f32>,
) -> PyResult<i32> {
    let inp = inputs(
        nchan, nbl, ntime, nant, &data, &flags, &baseline, &time, &ant1, &ant2,
    )?;
    let weights = c_slice(&weights, "weights")?;
    let out = c_slice_mut(&mut out, "out")?;
    Ok(detach(py, || {
        f5flag::logits(&inp, level, degree, weights, out)
    }))
}

/// W4's per-cell anomaly `(row, chan)` float32 into `out` (NaN where
/// undefined). Returns as `f5flag_features`.
#[pyfunction]
#[pyo3(signature = (nchan, nbl, ntime, nant, data, flags, baseline, time, ant1, ant2, level, degree, out))]
#[allow(clippy::too_many_arguments)]
pub fn f5flag_anomaly(
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
    level: usize,
    degree: usize,
    mut out: Rw<'_, f32>,
) -> PyResult<i32> {
    let inp = inputs(
        nchan, nbl, ntime, nant, &data, &flags, &baseline, &time, &ant1, &ant2,
    )?;
    let out = c_slice_mut(&mut out, "out")?;
    Ok(detach(py, || f5flag::anomaly(&inp, level, degree, out)))
}

/// Block shape `(nta, nja, ntv, njv)` of `f5flag_antenna`'s arrays.
#[pyfunction]
pub fn f5flag_antenna_shape(ntime: usize, nchan: usize) -> (usize, usize, usize, usize) {
    f5flag::antenna_shape(ntime, nchan)
}

/// The per-antenna quantities (sections 2c-2d) into float64 `z`, `q`
/// (`(nta, nja, 2, nant)`) and `tt`, `tf` (`(ntv, njv, nant)`). Returns as
/// `f5flag_features`.
#[pyfunction]
#[pyo3(signature = (nchan, nbl, ntime, nant, data, flags, baseline, time, ant1, ant2, level, degree, z, q, tt, tf))]
#[allow(clippy::too_many_arguments)]
pub fn f5flag_antenna(
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
    level: usize,
    degree: usize,
    mut z: Rw<'_, f64>,
    mut q: Rw<'_, f64>,
    mut tt: Rw<'_, f64>,
    mut tf: Rw<'_, f64>,
) -> PyResult<i32> {
    let inp = inputs(
        nchan, nbl, ntime, nant, &data, &flags, &baseline, &time, &ant1, &ant2,
    )?;
    let z = c_slice_mut(&mut z, "z")?;
    let q = c_slice_mut(&mut q, "q")?;
    let tt = c_slice_mut(&mut tt, "tt")?;
    let tf = c_slice_mut(&mut tf, "tf")?;
    Ok(detach(py, || {
        f5flag::antenna_arrays(&inp, level, degree, z, q, tt, tf)
    }))
}

/// Logits and W4's anomaly `(row, chan)` float32 from one preparation pass.
/// Returns as `f5flag_features`.
#[pyfunction]
#[pyo3(signature = (nchan, nbl, ntime, nant, data, flags, baseline, time, ant1, ant2, level, degree, weights, logit, anomaly))]
#[allow(clippy::too_many_arguments)]
pub fn f5flag_logits_anomaly(
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
    level: usize,
    degree: usize,
    weights: Ro<'_, f32>,
    mut logit: Rw<'_, f32>,
    mut anomaly: Rw<'_, f32>,
) -> PyResult<i32> {
    let inp = inputs(
        nchan, nbl, ntime, nant, &data, &flags, &baseline, &time, &ant1, &ant2,
    )?;
    let weights = c_slice(&weights, "weights")?;
    let logit = c_slice_mut(&mut logit, "logit")?;
    let anomaly = c_slice_mut(&mut anomaly, "anomaly")?;
    Ok(detach(py, || {
        f5flag::logits_anomaly(&inp, level, degree, weights, logit, anomaly)
    }))
}
