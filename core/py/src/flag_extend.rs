//! `rang._core.flag_extend`: CASA's `flagdata(mode='extend')` of
//! `rang_core::flag_extend` (task E0, `research/e0-refant-extend.md`), for
//! `rang.flag_extend`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! `flag` is a C-contiguous uint8 `(row, chan, corr)` array, extended in
//! place; `order` and `starts` are uint64. A bad argument raises ValueError.

use crate::{Ro, Rw, c_slice, c_slice_mut, detach};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use rang_core::flag_extend::{Settings, extend};

/// Extend `flag` in place over the segments `order[starts[k]:starts[k+1]]`
/// and return the cells each rule added, as a dict.
#[pyfunction]
#[pyo3(signature = (
    flag, nchan, npol, order, starts, growtime, growfreq, growaround,
    flagneartime, flagnearfreq, extendpols
))]
#[allow(clippy::too_many_arguments)]
pub fn flag_extend<'py>(
    py: Python<'py>,
    mut flag: Rw<'py, u8>,
    nchan: usize,
    npol: usize,
    order: Ro<'py, u64>,
    starts: Ro<'py, u64>,
    growtime: f64,
    growfreq: f64,
    growaround: bool,
    flagneartime: bool,
    flagnearfreq: bool,
    extendpols: bool,
) -> PyResult<Bound<'py, PyDict>> {
    let settings = Settings {
        growtime,
        growfreq,
        growaround,
        flagneartime,
        flagnearfreq,
        extendpols,
    };
    let order = c_slice(&order, "order")?;
    let starts = c_slice(&starts, "starts")?;
    let flag = c_slice_mut(&mut flag, "flag")?;
    let counts = detach(py, || extend(flag, nchan, npol, order, starts, &settings))
        .map_err(PyValueError::new_err)?;
    let out = PyDict::new(py);
    out.set_item("neartime", counts.neartime)?;
    out.set_item("nearfreq", counts.nearfreq)?;
    out.set_item("growaround", counts.growaround)?;
    out.set_item("grown", counts.grown)?;
    out.set_item("growfreq", counts.growfreq)?;
    out.set_item("growtime", counts.growtime)?;
    out.set_item("extendpols", counts.extendpols)?;
    Ok(out)
}
