//! `rang._core.cal_fluxscale_*`: CASA's `fluxscale` statistics of
//! `rang_core::cal::fluxscale` (task C2d, `research/c2d-fluxscale.md`), for
//! `rang.cal_fluxscale`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Every array must be C-contiguous with the stated length (a ValueError
//! names it); CASA's errors raise ValueError with CASA's message.

use crate::{Ro, c_slice};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use rang_core::cal::fluxscale::{self, Rows, Settings};

fn exact<'a, T: numpy::Element>(a: &'a Ro<'_, T>, name: &str, len: usize) -> PyResult<&'a [T]> {
    let s = c_slice(a, name)?;
    if s.len() != len {
        return Err(PyValueError::new_err(format!(
            "{name} must hold {len} elements, not {}",
            s.len()
        )));
    }
    Ok(s)
}

fn indices(a: &[u32]) -> Vec<usize> {
    a.iter().map(|&v| v as usize).collect()
}

/// The flux scale of `rang_core::cal::fluxscale::scale`: `amp` float32 and
/// `flag` uint8 `(row, npar)`, `field`, `spw`, `antenna` uint32 per row.
/// Returns a dict of flat lists: `(spw, field)` for `fd`, `fderr`, `fdrms`,
/// `mgratio`, `mgrms`, `mgerr`, `numsol`, `ok`; `(field, spw)` for
/// `median_gain`; `(field, ant, spw)` for `used` and `unflagged`.
#[pyfunction]
#[pyo3(signature = (
    amp, flag, field, spw, antenna, npar, nant, nspw, nfield,
    reference, transfer, refspwmap, gainthreshold
))]
#[allow(clippy::too_many_arguments)]
pub fn cal_fluxscale_scale<'py>(
    py: Python<'py>,
    amp: Ro<'py, f32>,
    flag: Ro<'py, u8>,
    field: Ro<'py, u32>,
    spw: Ro<'py, u32>,
    antenna: Ro<'py, u32>,
    npar: usize,
    nant: usize,
    nspw: usize,
    nfield: usize,
    reference: Vec<usize>,
    transfer: Vec<usize>,
    refspwmap: Vec<usize>,
    gainthreshold: f32,
) -> PyResult<Bound<'py, PyDict>> {
    let nrow = c_slice(&field, "field")?.len();
    let amp = exact(&amp, "amp", nrow * npar)?;
    let flag: Vec<bool> = exact(&flag, "flag", nrow * npar)?
        .iter()
        .map(|&f| f != 0)
        .collect();
    let field = indices(exact(&field, "field", nrow)?);
    let spw = indices(exact(&spw, "spw", nrow)?);
    let antenna = indices(exact(&antenna, "antenna", nrow)?);
    let rows = Rows {
        amp,
        flag: &flag,
        field: &field,
        spw: &spw,
        antenna: &antenna,
        npar,
        nant,
        nspw,
        nfield,
    };
    let settings = Settings {
        reference,
        transfer,
        refspwmap,
        gainthreshold,
    };
    let out = fluxscale::scale(&rows, &settings).map_err(PyValueError::new_err)?;
    let d = PyDict::new(py);
    d.set_item("fd", out.fd)?;
    d.set_item("fderr", out.fderr)?;
    d.set_item("fdrms", out.fdrms)?;
    d.set_item("mgratio", out.mgratio)?;
    d.set_item("mgrms", out.mgrms)?;
    d.set_item("mgerr", out.mgerr)?;
    d.set_item("numsol", out.numsol)?;
    d.set_item("ok", out.ok)?;
    d.set_item("median_gain", out.median_gain)?;
    d.set_item("used", out.used)?;
    d.set_item("unflagged", out.unflagged)?;
    Ok(d)
}

/// CASA's spectral fit (`rang_core::cal::fluxscale::spectral_fit`) of one
/// field's valid windows. Returns a dict: `order`, `coeffs`, `errors`,
/// `covar` (flat, row-major), `flux`, `flux_err`, `ref_freq`.
#[pyfunction]
pub fn cal_fluxscale_fit<'py>(
    py: Python<'py>,
    freq: Vec<f64>,
    fd: Vec<f64>,
    fderr: Vec<f64>,
    fitorder: usize,
) -> PyResult<Bound<'py, PyDict>> {
    let fit =
        fluxscale::spectral_fit(&freq, &fd, &fderr, fitorder).map_err(PyValueError::new_err)?;
    let d = PyDict::new(py);
    d.set_item("order", fit.order)?;
    d.set_item("coeffs", fit.coeffs)?;
    d.set_item("errors", fit.errors)?;
    d.set_item("covar", fit.covar)?;
    d.set_item("flux", fit.flux)?;
    d.set_item("flux_err", fit.flux_err)?;
    d.set_item("ref_freq", fit.ref_freq)?;
    Ok(d)
}
