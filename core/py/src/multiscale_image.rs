// SPDX-License-Identifier: MIT
//! `rang._core.multiscale_image`: GeMClean's multi-scale minor cycle
//! (`rang_core::gemclean::multiscale`, `research/g5-multiscale.md`) on a
//! residual image with an image-domain measurement, for DD12's loop
//! (`research/dd12-msclean.md`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
//! see `LICENSES/MIT.txt`.
//!
//! The measurement is the image: `residual(m) = dirty − B m`, `B` the
//! convolution with the `2n` PSF (`gemclean::Beam`, one FFT pair on the `2n`
//! grid, linear). Its misfit is `⟨m, B m⟩ − 2⟨m, dirty⟩`, the visibility
//! misfit up to a constant, so the multi-scale run's predicted and exact
//! misfit changes are those of the visibilities.

use crate::{Ro, Rw, c_slice, c_slice_mut, detach};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use rang_core::clean_certified::Measurement;
use rang_core::gemclean::mask::Masking;
use rang_core::gemclean::multiscale::{
    self, BiasReference, MultiscaleEnd, MultiscaleSettings, Shape,
};
use rang_core::gemclean::{Beam, CycleStop, Settings, StopReason};

/// The residual image as a measurement of the model.
struct ImageMeasurement<'a> {
    dirty: &'a [f64],
    beam: &'a Beam,
    n: usize,
}

impl Measurement for ImageMeasurement<'_> {
    fn side(&self) -> usize {
        self.n
    }

    fn residual(&self, model: &[f64]) -> Result<(Vec<f64>, f64), String> {
        let bm = self.beam.convolve(model);
        let mut q = 0.0;
        let r: Vec<f64> = self
            .dirty
            .iter()
            .zip(&bm)
            .zip(model)
            .map(|((d, b), m)| {
                q += m * (b - 2.0 * d);
                d - b
            })
            .collect();
        Ok((r, q))
    }

    fn gram_apply(&self, x: &[f64]) -> Result<Vec<f64>, String> {
        Ok(self.beam.convolve(x))
    }
}

fn stop_name(stop: StopReason) -> &'static str {
    match stop {
        StopReason::Threshold => "threshold",
        StopReason::Components => "components",
        StopReason::MajorCycles => "major cycles",
    }
}

fn end_name(end: MultiscaleEnd) -> &'static str {
    match end {
        MultiscaleEnd::Normal => "normal",
        MultiscaleEnd::Stalled => "stalled",
        MultiscaleEnd::Diverged => "diverged",
    }
}

/// Multi-scale CLEAN of the `n × n` `dirty` image (row-major) with the
/// `2n × 2n` PSF `psf2n` centred on `(n, n)`, component centres confined to
/// `mask` (`n × n`, nonzero: allowed), down to the absolute `threshold`
/// (no hand-back: `CycleStop::Threshold`). `scales` empty: radler's
/// automatic list for `beam_pixels`, at most `max_scales` (0: all that fit).
/// Writes the model and the exact residual of the measurement; returns a
/// dict of the run's record.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn multiscale_image<'py>(
    py: Python<'py>,
    n: usize,
    dirty: Ro<'py, f64>,
    psf2n: Ro<'py, f64>,
    mask: Ro<'py, u8>,
    threshold: f64,
    gain: f64,
    max_components: usize,
    max_major: usize,
    scales: Vec<f64>,
    max_scales: usize,
    scale_bias: f64,
    sub_minor_gain: f64,
    beam_pixels: f64,
    patch: usize,
    mut model: Rw<'py, f64>,
    mut residual: Rw<'py, f64>,
) -> PyResult<Bound<'py, PyDict>> {
    let dirty = c_slice(&dirty, "dirty")?;
    let psf2n = c_slice(&psf2n, "psf2n")?;
    let mask = c_slice(&mask, "mask")?;
    let model = c_slice_mut(&mut model, "model")?;
    let residual = c_slice_mut(&mut residual, "residual")?;
    let nn = n * n;
    if n < 2
        || dirty.len() != nn
        || mask.len() != nn
        || model.len() != nn
        || residual.len() != nn
        || psf2n.len() != 4 * nn
    {
        return Err(PyValueError::new_err(
            "dirty, mask, model and residual must be n × n, psf2n 2n × 2n",
        ));
    }
    let settings = Settings {
        gain,
        cycle_stop: CycleStop::Threshold,
        threshold,
        auto_threshold: None,
        max_components,
        max_major,
        ..Settings::default()
    };
    let ms = MultiscaleSettings {
        scales,
        max_scales,
        scale_bias,
        shape: Shape::TaperedQuadratic,
        sub_minor_gain,
        divergence_limit: 4.0,
        bias_reference: BiasReference::Theoretic,
        point_cap: None,
        allow_negative: true,
    };
    let masking = Masking {
        fits: Some(mask.iter().map(|&v| v != 0).collect()),
        auto: None,
    };
    let out = detach(py, || -> Result<_, String> {
        let beam = Beam::from_double(n, psf2n, patch)?;
        // The n × n PSF crop centred on (n/2, n/2), as GeMClean's command line.
        let mut psf = vec![0.0; nn];
        for i in 0..n {
            for j in 0..n {
                psf[i * n + j] = psf2n[(i + n / 2) * 2 * n + j + n / 2];
            }
        }
        let meas = ImageMeasurement {
            dirty,
            beam: &beam,
            n,
        };
        multiscale::run_multiscale_masked(
            &[(&meas, &beam, &psf[..])],
            &[1.0],
            None,
            &settings,
            &ms,
            beam_pixels,
            Some(&masking),
        )
    })
    .map_err(PyValueError::new_err)?;
    let o = &out.joined.integrated;
    model.copy_from_slice(&o.model);
    residual.copy_from_slice(&o.residual);
    let d = PyDict::new(py);
    d.set_item("components", o.steps.len())?;
    d.set_item("major_cycles", o.cycles.len())?;
    d.set_item("stop", stop_name(o.stop))?;
    d.set_item("end", end_name(out.end))?;
    d.set_item("sub_minor_loops", out.sub_minor_loops)?;
    d.set_item("convolutions", out.convolutions)?;
    d.set_item("beam_pixels", out.beam_pixels)?;
    d.set_item("seconds", o.timings.total)?;
    d.set_item("q_final", o.q_final)?;
    let sc: Vec<(f64, usize, f64, f64, f64, usize, f64)> = out
        .scales
        .iter()
        .map(|s| {
            (
                s.scale,
                s.kernel_side,
                s.bias,
                s.psf_peak,
                s.gain,
                s.components,
                s.flux,
            )
        })
        .collect();
    d.set_item("scales", sc)?;
    d.set_item("dropped_scales", out.dropped.clone())?;
    let peaks: Vec<(f64, f64, usize)> = o
        .cycles
        .iter()
        .map(|c| (c.peak_start, c.threshold, c.components))
        .collect();
    d.set_item("cycles", peaks)?;
    Ok(d)
}

/// WSClean's theoretic beam in radians (`multiscale::theoretic_beam`):
/// `uvw` metres, `nrow × 3`; `weights` `nrow × nchan`; `None` without a
/// visibility inside the `n`-pixel grid of `pixel` radians.
#[pyfunction]
pub fn multiscale_theoretic_beam(
    py: Python<'_>,
    uvw: Ro<'_, f64>,
    freq: Ro<'_, f64>,
    weights: Ro<'_, f64>,
    n: usize,
    pixel: f64,
) -> PyResult<Option<f64>> {
    let uvw = c_slice(&uvw, "uvw")?;
    let freq = c_slice(&freq, "freq")?;
    let weights = c_slice(&weights, "weights")?;
    if uvw.len() % 3 != 0 || weights.len() != uvw.len() / 3 * freq.len() {
        return Err(PyValueError::new_err(
            "uvw must be nrow × 3 and weights nrow × nchan",
        ));
    }
    Ok(detach(py, || {
        multiscale::theoretic_beam(uvw, freq, weights, n, pixel)
    }))
}
