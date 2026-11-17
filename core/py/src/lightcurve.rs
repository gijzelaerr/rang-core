// SPDX-License-Identifier: MIT
//! `rang._core.lightcurve_dft`: the forced-photometry DFT of
//! `rang_core::lightcurve` (task TS-P1, `research/ts-p1.md`), for
//! `rang.lightcurve`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! `uvw` is float64 `(nrow, 3)`, `freq` float64 `(nchan,)`, `vis` complex64
//! `(nrow, nchan)`, `weight` float32 `(nrow, nchan)` and `lm` float64
//! `(nsrc, 2)`, all C-contiguous. A bad argument raises ValueError.

use crate::{Ro, c_slice, detach};
use numpy::Complex32;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rang_core::lightcurve::dft_sums;

/// The DFT sums of one interval: (numerator per position, weight sum,
/// samples with a nonzero weight).
#[pyfunction]
pub fn lightcurve_dft(
    py: Python<'_>,
    uvw: Ro<'_, f64>,
    freq: Ro<'_, f64>,
    vis: Ro<'_, Complex32>,
    weight: Ro<'_, f32>,
    lm: Ro<'_, f64>,
) -> PyResult<(Vec<f64>, f64, u64)> {
    let uvw = c_slice(&uvw, "uvw")?;
    let freq = c_slice(&freq, "freq")?;
    let vis = c_slice(&vis, "vis")?;
    let weight = c_slice(&weight, "weight")?;
    let lm = c_slice(&lm, "lm")?;
    // SAFETY: Complex32 is two f32 in re, im order (repr(C)).
    let flat: &[f32] =
        unsafe { std::slice::from_raw_parts(vis.as_ptr() as *const f32, 2 * vis.len()) };
    let sums =
        detach(py, || dft_sums(uvw, freq, flat, weight, lm)).map_err(PyValueError::new_err)?;
    Ok((sums.numerator, sums.weight_sum, sums.samples))
}
