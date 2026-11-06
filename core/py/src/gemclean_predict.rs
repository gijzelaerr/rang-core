//! `rang._core.gemclean_*`: gemclean's model prediction
//! (`rang_core::gemclean::predict`, `research/g6-predict.md`) for
//! `rang.core_model` (the `rang-core image` path through W1's `WriteBack`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The caller reads UVW through its write-back session and passes the rows
//! in the binary's blocks (`gemclean_block_rows`), so both paths call the
//! gridder on the same rows and give the same bits.

use crate::{Ro, Rw, c_slice, c_slice_mut, detach};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rang_core::gemclean::predict::{self, Predictor};

/// Selected rows per gridder call for `nchan` channels.
#[pyfunction]
pub fn gemclean_block_rows(nchan: usize) -> usize {
    predict::block_rows(nchan)
}

/// The output channel of each channel (in the MS's order), -1 where none.
#[pyfunction]
#[pyo3(signature = (freq, channels_out, channel_range, average_channels))]
pub fn gemclean_channel_map(
    freq: Ro<'_, f64>,
    channels_out: usize,
    channel_range: Option<(usize, usize)>,
    average_channels: usize,
) -> PyResult<Vec<i64>> {
    let freq = c_slice(&freq, "freq")?;
    let map = predict::channel_map(freq, channel_range, average_channels, channels_out)
        .map_err(PyValueError::new_err)?;
    Ok(map
        .into_iter()
        .map(|k| k.map_or(-1, |k| k as i64))
        .collect())
}

/// Predict `name`'s model images (`<name>-model.fits` or
/// `<name>-000k-model.fits`) at the rows `uvw` (`rows × 3`) and channels
/// `freq` into `out` (`rows × nchan` complex64; zero in channels without a
/// model), after checking the image centre against `phase_dir` (radians).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature = (name, channels_out, channel_range, average_channels, epsilon, wgridding, single, phase_dir, uvw, freq, out))]
pub fn gemclean_predict(
    py: Python<'_>,
    name: String,
    channels_out: usize,
    channel_range: Option<(usize, usize)>,
    average_channels: usize,
    epsilon: f64,
    wgridding: bool,
    single: bool,
    phase_dir: (f64, f64),
    uvw: Ro<'_, f64>,
    freq: Ro<'_, f64>,
    mut out: Rw<'_, numpy::Complex32>,
) -> PyResult<()> {
    let uvw = c_slice(&uvw, "uvw")?;
    let freq = c_slice(&freq, "freq")?;
    let out = c_slice_mut(&mut out, "out")?;
    if uvw.len() % 3 != 0 || out.len() != uvw.len() / 3 * freq.len() {
        return Err(PyValueError::new_err(
            "uvw must be rows × 3 and out rows × nchan",
        ));
    }
    let result = detach(py, || -> Result<(), String> {
        let pred = Predictor::from_files(
            &name,
            freq,
            channels_out,
            channel_range,
            average_channels,
            epsilon,
            wgridding,
            single,
        )?;
        pred.check_centre(phase_dir)?;
        let vis = pred.predict(uvw, freq)?;
        for (o, v) in out.iter_mut().zip(vis) {
            *o = numpy::Complex32::new(v.re, v.im);
        }
        Ok(())
    });
    result.map_err(PyValueError::new_err)
}
