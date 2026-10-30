//! `rang._core.clean_certified`: the certified CLEAN driver of
//! `rang_core::clean_certified` on the exact wgridder
//! (`research/clean-certified-imaging.md`), for `rang.core_clean`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Inputs are borrowed NumPy arrays, outputs caller-owned arrays (the model
//! and the exact residual, `side × side` in the gridder layout; one row of
//! `CYCLE_COLUMNS` per major cycle; a `SUMMARY`-long summary). Returns 0, or
//! 1 when an array has the wrong length; a driver error raises `ValueError`.

use crate::{Ro, Rw, detach};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rang_core::clean_certified::{
    Complex, DriverSettings, Measurement, MinorRule, MinorStop, StopReason, WgridMeasurement,
    erc_certificate, misfit_floor, psf_from_image, run,
};
use rang_core::wgridder::Options;

/// Values per major-cycle row (see `rang.core_clean.CYCLE_FIELDS`).
pub const CYCLE_COLUMNS: usize = 17;
/// Summary values (see `rang.core_clean.SUMMARY_FIELDS`).
pub const SUMMARY: usize = 16;

fn minor_code(stop: MinorStop) -> f64 {
    match stop {
        MinorStop::Threshold => 0.0,
        MinorStop::Rule => 1.0,
        MinorStop::MaxMinor => 2.0,
        MinorStop::Budget => 3.0,
        MinorStop::Diverged => 4.0,
    }
}

fn stop_code(stop: StopReason) -> f64 {
    match stop {
        StopReason::Threshold => 0.0,
        StopReason::Floor => 1.0,
        StopReason::Components => 2.0,
        StopReason::MajorCycles => 3.0,
        StopReason::Diverged => 4.0,
    }
}

/// Certified CLEAN of `vis` (`nrow × nchan` complex128 viewed as float64
/// pairs) with gridding weights `wgt`: `rule` 0 Clark, 1 provable, 2 mgain;
/// `beam` 0 exact (a `2 side` PSF), 1 image-size; `patch < 0` for none;
/// `floor_iterations = 0` skips `Q_∞`; `floor_tolerance ≤ 0` turns the floor
/// rule off; `max_minor = 0` for no limit.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn clean_certified(
    py: Python<'_>,
    nrow: usize,
    nchan: usize,
    uvw: Ro<'_, f64>,
    freq: Ro<'_, f64>,
    vis: Ro<'_, f64>,
    wgt: Ro<'_, f64>,
    side: usize,
    cell: f64,
    epsilon: f64,
    wgridding: bool,
    flip_v: bool,
    flip_w: bool,
    gain: f64,
    threshold: f64,
    max_components: usize,
    max_major: usize,
    max_minor: usize,
    rule: u8,
    mgain: f64,
    patch: i64,
    beam: u8,
    floor_iterations: usize,
    floor_tolerance: f64,
    divergence_limit: f64,
    audit: bool,
    erc_max_k: usize,
    mut model: Rw<'_, f64>,
    mut residual: Rw<'_, f64>,
    mut cycles: Rw<'_, f64>,
    mut summary: Rw<'_, f64>,
) -> PyResult<i32> {
    let Some(n) = nrow.checked_mul(nchan) else {
        return Ok(1);
    };
    let (uvw, freq, vis, wgt) = (
        uvw.as_slice()?,
        freq.as_slice()?,
        vis.as_slice()?,
        wgt.as_slice()?,
    );
    let (model, residual) = (model.as_slice_mut()?, residual.as_slice_mut()?);
    let (cycles, summary) = (cycles.as_slice_mut()?, summary.as_slice_mut()?);
    let rule = match rule {
        0 => MinorRule::Clark,
        1 => MinorRule::Provable,
        2 => MinorRule::MajorGain(mgain),
        _ => return Ok(1),
    };
    if side == 0
        || uvw.len() != 3 * nrow
        || freq.len() != nchan
        || vis.len() != 2 * n
        || wgt.len() != n
        || model.len() != side * side
        || residual.len() != side * side
        || cycles.len() != max_major * CYCLE_COLUMNS
        || summary.len() != SUMMARY
        || beam > 1
    {
        return Ok(1);
    }
    let result = detach(py, || -> Result<(), String> {
        let visibilities: Vec<Complex<f64>> = vis
            .chunks_exact(2)
            .map(|c| Complex::new(c[0], c[1]))
            .collect();
        let measurement = WgridMeasurement::new(
            uvw.to_vec(),
            freq.to_vec(),
            visibilities,
            wgt.to_vec(),
            side,
            cell,
            epsilon,
            Options {
                do_wgridding: wgridding,
                flip_v,
                flip_w,
                ..Options::default()
            },
        )?;
        let exact = measurement.psf()?;
        let minor = if beam == 0 {
            exact.clone()
        } else {
            psf_from_image(side, &measurement.psf_image(side)?)
        };
        let floor = if floor_iterations > 0 {
            let (dirty, _) = measurement.residual(&vec![0.0; side * side])?;
            Some(misfit_floor(&measurement, &dirty, floor_iterations, 1e-14)?.0)
        } else {
            None
        };
        let settings = DriverSettings {
            gain,
            threshold,
            max_components,
            max_major,
            max_minor: if max_minor == 0 {
                usize::MAX
            } else {
                max_minor
            },
            patch: usize::try_from(patch).ok(),
            rule,
            floor_tolerance: (floor_tolerance > 0.0).then_some(floor_tolerance),
            audit,
            divergence_limit,
        };
        let out = run(
            &measurement,
            &minor,
            &exact,
            &settings,
            floor.as_ref().map(|f| f.q_floor),
        )?;
        let erc = erc_certificate(&exact, &out.support(), erc_max_k);
        model.copy_from_slice(&out.model);
        residual.copy_from_slice(&out.residual);
        for (row, c) in cycles.chunks_exact_mut(CYCLE_COLUMNS).zip(&out.cycles) {
            row.copy_from_slice(&[
                c.index as f64,
                c.components as f64,
                c.peak_start,
                c.peak_working_end,
                c.q_before,
                c.q_after,
                c.dq_exact,
                c.dq_predicted,
                c.gap,
                c.gap_relative,
                c.dq_audit,
                c.ascending_steps as f64,
                c.abs_flux,
                c.kappa.unwrap_or(f64::NAN),
                c.reducible.unwrap_or(f64::NAN),
                minor_code(c.stop),
                c.seconds,
            ]);
        }
        summary.copy_from_slice(&[
            out.q0,
            out.q_final,
            out.steps.len() as f64,
            out.cycles.len() as f64,
            stop_code(out.stop),
            out.f,
            out.seconds,
            out.ascending_steps() as f64,
            erc.k as f64,
            erc.eta.unwrap_or(f64::NAN),
            erc.min_pivot,
            floor.as_ref().map_or(f64::NAN, |f| f.q_floor),
            floor.as_ref().map_or(0.0, |f| f.iterations as f64),
            floor.as_ref().map_or(f64::NAN, |f| f.relative_residual),
            measurement.weight_sum,
            erc.seconds,
        ]);
        Ok(())
    });
    result.map_err(PyValueError::new_err)?;
    Ok(0)
}
