// SPDX-License-Identifier: MIT
//! `rang._core.reweight_variances`: per-block visibility variances for the
//! re-weighting stage (`rang_core::reweight`, issue #55,
//! `research/apply-reweight.md`), for `rang.reweight`.

use crate::{Ro, Rw, c_slice, c_slice_mut, detach};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rang_core::reweight::{self, Statistic};

/// Write `var` (float64, `ngroup * nblock`; NaN where a block has fewer than
/// `minsamp` valid samples) and `count` (uint64, the same shape): `values`
/// float32 view of complex64 `(row, chan)`, `valid` uint8 `(row, chan)`,
/// `group` uint32 per row; `statistic` "classic" (CASA statwt's), "mad" or "clipped".
#[pyfunction]
#[pyo3(signature = (nchan, chanbin, ngroup, values, valid, group, statistic, minsamp, var, count))]
#[allow(clippy::too_many_arguments)]
pub fn reweight_variances(
    py: Python<'_>,
    nchan: usize,
    chanbin: usize,
    ngroup: usize,
    values: Ro<'_, f32>,
    valid: Ro<'_, u8>,
    group: Ro<'_, u32>,
    statistic: &str,
    minsamp: usize,
    mut var: Rw<'_, f64>,
    mut count: Rw<'_, u64>,
) -> PyResult<()> {
    let statistic = match statistic {
        "classic" => Statistic::Classic,
        "mad" => Statistic::Mad,
        "clipped" => Statistic::Clipped,
        _ => {
            return Err(PyValueError::new_err(
                "statistic must be classic, mad or clipped",
            ));
        }
    };
    let (values, valid, group) = (
        c_slice(&values, "values")?,
        c_slice(&valid, "valid")?,
        c_slice(&group, "group")?,
    );
    let (v, c) = detach(py, || {
        reweight::variances(
            values, valid, group, ngroup, nchan, chanbin, statistic, minsamp,
        )
    })
    .map_err(PyValueError::new_err)?;
    let var = c_slice_mut(&mut var, "var")?;
    let count = c_slice_mut(&mut count, "count")?;
    if var.len() != v.len() || count.len() != c.len() {
        return Err(PyValueError::new_err(
            "var and count must be ngroup * nblock",
        ));
    }
    var.copy_from_slice(&v);
    count.copy_from_slice(&c);
    Ok(())
}
