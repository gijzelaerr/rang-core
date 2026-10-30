//! Certified CLEAN: a Cotton-Schwab major/minor-cycle driver over the
//! kernels of [`crate::clean`], instrumented with the four diagnostics of
//! `research/clean-theory.md` §6. Research note:
//! `research/clean-certified-imaging.md`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The driver separates the two operators every CLEAN mixes:
//!
//! - the **measurement**, a [`Measurement`] that turns a pixel model into the
//!   exact residual image `r = Aᴴ W (V − A m)` and misfit
//!   `Q = ½ ‖V − A m‖²_W` (weights normalised to `Σ w = 1`, so the PSF peak is
//!   one and `Q` is in Jy²). A major cycle calls it once. Two are provided:
//!   [`DftMeasurement`] (the direct sums of `clean`, for tests and the
//!   simulated scenes) and [`WgridMeasurement`] (the exact gridder and
//!   degridder of `wgridder`, for Measurement Sets);
//! - the **minor-cycle beam**, a [`Psf`] subtracted from a working residual,
//!   optionally only within `±patch` pixels (Clark), or a beam computed on
//!   the image grid as WSClean does.
//!
//! Theorem 1 of the note holds step by step only when the minor-cycle beam is
//! the Gram matrix of the measurement. The diagnostics measure how far that
//! fails and what it costs:
//!
//! 1. **Gram-consistency gap**, per major cycle: the exact change of `Q`
//!    (from the model visibilities) minus `Σ_j (−c_j r̃_j + ½ c_j² b̃(0))`,
//!    which is `−γ(2−γ)/2 Σ r̃²` for a unit-peak beam, reported in units of
//!    `Q` at the start of the cycle. Zero to rounding when the beam is the
//!    Gram matrix. Exactly, with `D = b − b̃` the beam the minor cycle
//!    ignores, `gap = Σ_{i<j} c_i c_j D(x_j − x_i) + ½ Σ_j c_j² D(0)`, a
//!    quadratic form in the cycle's components with an indefinite kernel:
//!    its sign is not fixed (both signs occur in the tests).
//! 2. **Misfit floor** `Q_∞` by conjugate gradients on the measurement's
//!    normal operator ([`misfit_floor`]), and the stopping rule
//!    `(Q − Q_∞)/(Q_0 − Q_∞) < tol`.
//! 3. **ERC certificate** `η(S)` of the final component positions
//!    ([`erc_certificate`]): one Cholesky factorisation of `B_SS`
//!    (`k³/3`) and two triangular solves per pixel outside `S` (`k² N`).
//! 4. **Provable minor-cycle rule** (Theorem 6): continue while
//!    `f Σ_j |c_j| < (1 − γ/2) |r̃_p|`, with `f` the largest difference between
//!    the Gram beam and the subtracted beam ([`truncation_bound`]). Every rule
//!    takes the first step of a cycle, which is exact because the working
//!    residual was just reset.

use crate::clean::{self, CleanStep, Grid, Psf, Sampling, Vis, argmax_abs, subtract};
use crate::wgridder::{self, Options, VisData, Weights};
use rayon::prelude::*;
use rustfft::num_complex::Complex;
use std::time::Instant;

/// What a major cycle needs from the data.
pub trait Measurement {
    /// Pixels on a side of the (square) image.
    fn side(&self) -> usize;
    /// The exact residual image and misfit of `model` (`side²` pixels).
    fn residual(&self, model: &[f64]) -> Result<(Vec<f64>, f64), String>;
    /// The normal operator `Aᴴ W A x`: the image of the visibilities of `x`.
    fn gram_apply(&self, x: &[f64]) -> Result<Vec<f64>, String>;
}

/// The direct-sum measurement of [`crate::clean`] (normalised weights).
pub struct DftMeasurement<'a> {
    pub sampling: &'a Sampling,
    pub grid: Grid,
    pub vis: &'a [Vis],
}

impl Measurement for DftMeasurement<'_> {
    fn side(&self) -> usize {
        self.grid.n
    }

    fn residual(&self, model: &[f64]) -> Result<(Vec<f64>, f64), String> {
        let predicted = clean::predict(self.sampling, &self.grid, model);
        let q = clean::misfit(self.sampling, self.vis, &predicted);
        let e: Vec<Vis> = self
            .vis
            .iter()
            .zip(&predicted)
            .map(|(a, b)| (a.0 - b.0, a.1 - b.1))
            .collect();
        Ok((clean::dirty(self.sampling, &self.grid, &e), q))
    }

    fn gram_apply(&self, x: &[f64]) -> Result<Vec<f64>, String> {
        let v = clean::predict(self.sampling, &self.grid, x);
        Ok(clean::dirty(self.sampling, &self.grid, &v))
    }
}

/// The exact-gridder measurement: `vis2dirty` and its adjoint `dirty2vis`
/// of [`crate::wgridder`] in double precision. Images are `side × side`,
/// pixel `(i, j)` stored at `i * side + j` with `i` along `l` (the
/// gridder's layout; [`Psf::at`] then takes `dx = Δj`, `dy = Δi`).
pub struct WgridMeasurement {
    pub uvw: Vec<f64>,
    pub freq: Vec<f64>,
    pub vis: Vec<Complex<f64>>,
    /// Gridding weights normalised to sum to one.
    pub wgt: Vec<f64>,
    /// The weight sum before normalisation.
    pub weight_sum: f64,
    pub opts: Options,
}

impl WgridMeasurement {
    /// `uvw` is `nrow × 3` metres, `freq` Hz, `vis` and `wgt` `nrow × nchan`;
    /// `cell` is the pixel size in radians. Visibilities with zero weight
    /// are ignored. Errors when every weight is zero.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        uvw: Vec<f64>,
        freq: Vec<f64>,
        vis: Vec<Complex<f64>>,
        wgt: Vec<f64>,
        side: usize,
        cell: f64,
        epsilon: f64,
        opts: Options,
    ) -> Result<WgridMeasurement, String> {
        let nrow = uvw.len() / 3;
        if vis.len() != nrow * freq.len() || wgt.len() != vis.len() {
            return Err("vis and wgt must be nrow * nchan".into());
        }
        let weight_sum: f64 = wgt.iter().sum();
        if weight_sum <= 0.0 || weight_sum.is_nan() {
            return Err("weights must have a positive sum".into());
        }
        let wgt = wgt.iter().map(|w| w / weight_sum).collect();
        let opts = Options {
            nx: side,
            ny: side,
            pixsize_x: cell,
            pixsize_y: cell,
            epsilon,
            ..opts
        };
        Ok(WgridMeasurement {
            uvw,
            freq,
            vis,
            wgt,
            weight_sum,
            opts,
        })
    }

    fn sized(&self, side: usize) -> Options {
        Options {
            nx: side,
            ny: side,
            ..self.opts
        }
    }

    /// The model visibilities `A m` (no weights).
    pub fn predict(&self, model: &[f64]) -> Result<Vec<Complex<f64>>, String> {
        let mut out = vec![Complex::new(0.0, 0.0); self.vis.len()];
        if model.iter().any(|&c| c != 0.0) {
            wgridder::dirty2vis(
                &self.opts, &self.uvw, &self.freq, model, None, None, &mut out,
            )?;
        }
        Ok(out)
    }

    /// The image `Aᴴ W v`.
    pub fn image(&self, vis: &[Complex<f64>]) -> Result<Vec<f64>, String> {
        let mut out = vec![0.0; self.opts.nx * self.opts.ny];
        wgridder::vis2dirty(
            &self.opts,
            &self.uvw,
            &self.freq,
            vis,
            Some(&self.wgt),
            None,
            &mut out,
        )?;
        Ok(out)
    }

    /// The PSF image of unit visibilities on a `side × side` grid of the
    /// same cell, centred on pixel `(side/2, side/2)`.
    pub fn psf_image(&self, side: usize) -> Result<Vec<f64>, String> {
        let mut out = vec![0.0; side * side];
        wgridder::vis2dirty_multi(
            &self.sized(side),
            &self.uvw,
            &self.freq,
            VisData::Unit,
            Weights::F64(&self.wgt),
            None,
            None::<&mut [f64]>,
            Some(&mut out),
        )?;
        Ok(out)
    }

    /// The beam over every offset two image pixels can have, from a PSF on
    /// a grid twice the image size: exact subtraction anywhere in the image
    /// (up to the w-term, which makes the true Gram matrix depend on
    /// position as well as offset when w-gridding is on).
    pub fn psf(&self) -> Result<Psf, String> {
        let n = self.opts.nx;
        Ok(psf_from_double(n, &self.psf_image(2 * n)?))
    }
}

impl Measurement for WgridMeasurement {
    fn side(&self) -> usize {
        self.opts.nx
    }

    fn residual(&self, model: &[f64]) -> Result<(Vec<f64>, f64), String> {
        let predicted = self.predict(model)?;
        let mut q = 0.0;
        let e: Vec<Complex<f64>> = self
            .vis
            .iter()
            .zip(&predicted)
            .zip(&self.wgt)
            .map(|((v, p), &w)| {
                let d = v - p;
                q += w * d.norm_sqr();
                d
            })
            .collect();
        Ok((self.image(&e)?, 0.5 * q))
    }

    fn gram_apply(&self, x: &[f64]) -> Result<Vec<f64>, String> {
        self.image(&self.predict(x)?)
    }
}

/// A [`Psf`] over offsets `±(n−1)` from a `2n × 2n` PSF image centred on
/// pixel `(n, n)` (row-major, rows are the slow offset `dy`).
pub fn psf_from_double(n: usize, image: &[f64]) -> Psf {
    let width = 2 * n - 1;
    let mut values = vec![0.0; width * width];
    for r in 1..2 * n {
        for c in 1..2 * n {
            values[(c - 1) + width * (r - 1)] = image[r * 2 * n + c];
        }
    }
    Psf { n, values }
}

/// A [`Psf`] from an `n × n` PSF image centred on pixel `(n/2, n/2)`, zero
/// for offsets the image does not hold: the beam a deconvolver computed on
/// the image grid subtracts (truncated for components away from the centre).
pub fn psf_from_image(n: usize, image: &[f64]) -> Psf {
    let width = 2 * n - 1;
    let off = (n - 1) as isize;
    let half = (n / 2) as isize;
    let mut values = vec![0.0; width * width];
    for dy in -off..=off {
        for dx in -off..=off {
            let r = half + dy;
            let c = half + dx;
            if (0..n as isize).contains(&r) && (0..n as isize).contains(&c) {
                values[(dx + off) as usize + width * (dy + off) as usize] =
                    image[r as usize * n + c as usize];
            }
        }
    }
    Psf { n, values }
}

/// The constant `f` of Theorem 6: the largest `|b(Δ) − b̃(Δ)| / b(0)` over all
/// offsets, where `b` is the Gram beam and `b̃` the beam the minor cycle
/// subtracts (`minor` within `±patch`, zero outside). For `minor = exact`
/// this is [`Psf::outside_patch`].
pub fn truncation_bound(exact: &Psf, minor: &Psf, patch: Option<usize>) -> f64 {
    let n = exact.n;
    let off = (n - 1) as isize;
    let h = patch.map(|h| h as isize).unwrap_or(n as isize);
    let mut worst = 0.0_f64;
    for dy in -off..=off {
        for dx in -off..=off {
            let used = if dx.abs() <= h && dy.abs() <= h {
                minor.at(dx, dy)
            } else {
                0.0
            };
            worst = worst.max((exact.at(dx, dy) - used).abs());
        }
    }
    worst / exact.peak()
}

/// When a minor cycle hands back to the major cycle.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum MinorRule {
    /// Clark: stop when the working peak falls below `f` times the cycle's
    /// first peak.
    Clark,
    /// Theorem 6: continue while `f Σ_j |c_j| < (1 − γ/2) |r̃_p|`; every step
    /// lowers the true misfit.
    Provable,
    /// WSClean's `-mgain`: stop when the working peak falls below
    /// `(1 − mgain)` times the cycle's first peak.
    MajorGain(f64),
}

impl MinorRule {
    pub fn name(&self) -> String {
        match self {
            MinorRule::Clark => "clark".into(),
            MinorRule::Provable => "provable".into(),
            MinorRule::MajorGain(g) => format!("mgain-{g}"),
        }
    }
}

/// Settings of a certified CLEAN run.
#[derive(Clone, Copy, Debug)]
pub struct DriverSettings {
    /// The loop gain `γ`.
    pub gain: f64,
    /// Stop once the peak absolute residual falls below this (Jy/beam).
    pub threshold: f64,
    /// At most this many components in all.
    pub max_components: usize,
    /// At most this many major cycles.
    pub max_major: usize,
    /// At most this many components per minor cycle.
    pub max_minor: usize,
    /// Subtract the minor-cycle beam only within `±patch` pixels.
    pub patch: Option<usize>,
    pub rule: MinorRule,
    /// Stop once `(Q − Q_∞)/(Q_0 − Q_∞)` falls below this (needs `Q_∞`).
    pub floor_tolerance: Option<f64>,
    /// Keep an exact-beam residual beside the working one and count the
    /// minor steps that raise the true misfit (one full-image subtraction
    /// per step).
    pub audit: bool,
    /// Radler's divergence check (WSClean's default 4): end the minor cycle,
    /// and the run after its major cycle, when the working peak exceeds this
    /// many times the cycle's first peak. Zero disables it.
    pub divergence_limit: f64,
}

impl Default for DriverSettings {
    fn default() -> DriverSettings {
        DriverSettings {
            gain: 0.1,
            threshold: 0.0,
            max_components: 10_000,
            max_major: 100,
            max_minor: usize::MAX,
            patch: None,
            rule: MinorRule::MajorGain(0.8),
            floor_tolerance: None,
            audit: false,
            divergence_limit: 4.0,
        }
    }
}

/// Why a minor cycle ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MinorStop {
    Threshold,
    Rule,
    MaxMinor,
    Budget,
    Diverged,
}

/// Why the run ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StopReason {
    /// The exact residual peak is below the threshold.
    Threshold,
    /// `(Q − Q_∞)/(Q_0 − Q_∞)` is below the floor tolerance.
    Floor,
    /// The component budget is spent.
    Components,
    /// The major-cycle budget is spent.
    MajorCycles,
    /// A minor cycle tripped the divergence limit.
    Diverged,
}

/// One major cycle's record.
#[derive(Clone, Debug)]
pub struct MajorCycle {
    pub index: usize,
    pub components: usize,
    /// Exact residual peak at the start of the cycle.
    pub peak_start: f64,
    /// Working residual peak when the minor cycle stopped.
    pub peak_working_end: f64,
    pub q_before: f64,
    pub q_after: f64,
    /// `q_after − q_before`, from the model visibilities.
    pub dq_exact: f64,
    /// `Σ (−c r̃ + ½ c² b̃(0))` over the minor cycle.
    pub dq_predicted: f64,
    /// `dq_exact − dq_predicted`.
    pub gap: f64,
    /// `gap / q_before`.
    pub gap_relative: f64,
    /// Sum of the per-step true changes from the exact-beam residual (audit).
    pub dq_audit: f64,
    /// Minor steps whose true change of `Q` is positive (audit).
    pub ascending_steps: usize,
    /// `Σ |c_j|` of the cycle.
    pub abs_flux: f64,
    /// Greedy ratio `r_peak² / (2 (Q − Q_∞))` at the start (needs `Q_∞`).
    pub kappa: Option<f64>,
    /// `(Q − Q_∞)/(Q_0 − Q_∞)` at the start (needs `Q_∞`).
    pub reducible: Option<f64>,
    pub stop: MinorStop,
    pub seconds: f64,
}

/// The outcome of [`run`].
#[derive(Clone, Debug)]
pub struct Certified {
    pub model: Vec<f64>,
    /// The exact residual image of the final model.
    pub residual: Vec<f64>,
    pub q0: f64,
    pub q_final: f64,
    pub steps: Vec<CleanStep>,
    pub cycles: Vec<MajorCycle>,
    pub stop: StopReason,
    /// The constant `f` of Theorem 6 for the beams and patch used.
    pub f: f64,
    pub seconds: f64,
}

impl Certified {
    pub fn ascending_steps(&self) -> usize {
        self.cycles.iter().map(|c| c.ascending_steps).sum()
    }

    /// The component pixels without repeats, in first-pick order.
    pub fn support(&self) -> Vec<usize> {
        let mut seen = std::collections::HashSet::new();
        self.steps
            .iter()
            .filter(|s| seen.insert(s.pixel))
            .map(|s| s.pixel)
            .collect()
    }
}

/// Cotton-Schwab CLEAN with the diagnostics: `minor` is the beam the minor
/// cycles subtract (within `settings.patch`), `exact` the Gram beam of the
/// measurement (for `f` and the audit), `q_floor` an estimate of `Q_∞`.
pub fn run<M: Measurement>(
    measurement: &M,
    minor: &Psf,
    exact: &Psf,
    settings: &DriverSettings,
    q_floor: Option<f64>,
) -> Result<Certified, String> {
    let start = Instant::now();
    let n = measurement.side();
    if minor.n != n || exact.n != n {
        return Err("beams must match the image side".into());
    }
    let gain = settings.gain;
    let f = truncation_bound(exact, minor, settings.patch);
    let mut model = vec![0.0; n * n];
    let (mut residual, q0) = measurement.residual(&model)?;
    let mut q = q0;
    let mut steps = Vec::new();
    let mut cycles = Vec::new();
    let reducible = |q: f64| q_floor.map(|qf| (q - qf) / (q0 - qf));
    let stop = loop {
        let (_, peak) = argmax_abs(&residual);
        if peak.abs() < settings.threshold {
            break StopReason::Threshold;
        }
        if let (Some(tol), Some(red)) = (settings.floor_tolerance, reducible(q))
            && red < tol
        {
            break StopReason::Floor;
        }
        if steps.len() >= settings.max_components {
            break StopReason::Components;
        }
        if cycles.len() >= settings.max_major {
            break StopReason::MajorCycles;
        }
        let cycle_start = Instant::now();
        let mut working = residual.clone();
        let mut audit = if settings.audit {
            Some(residual.clone())
        } else {
            None
        };
        let first_peak = peak.abs();
        let mut abs_flux = 0.0;
        let mut predicted = 0.0;
        let mut dq_audit = 0.0;
        let mut ascending = 0;
        let mut taken = 0;
        let mut last_peak;
        let minor_stop = loop {
            let (p, value) = argmax_abs(&working);
            last_peak = value.abs();
            if value.abs() < settings.threshold {
                break MinorStop::Threshold;
            }
            if settings.divergence_limit > 0.0
                && value.abs() > settings.divergence_limit * first_peak
            {
                break MinorStop::Diverged;
            }
            if taken > 0 {
                let stop_here = match settings.rule {
                    MinorRule::Clark => value.abs() < f * first_peak,
                    MinorRule::Provable => f * abs_flux >= (1.0 - gain / 2.0) * value.abs(),
                    MinorRule::MajorGain(g) => value.abs() < (1.0 - g) * first_peak,
                };
                if stop_here {
                    break MinorStop::Rule;
                }
            }
            if taken >= settings.max_minor {
                break MinorStop::MaxMinor;
            }
            if steps.len() >= settings.max_components {
                break MinorStop::Budget;
            }
            let c = gain * value / minor.peak();
            predicted += -c * value + 0.5 * c * c * minor.peak();
            if let Some(true_r) = audit.as_mut() {
                let dq = -c * true_r[p] + 0.5 * c * c * exact.peak();
                dq_audit += dq;
                if dq > 0.0 {
                    ascending += 1;
                }
                subtract(true_r, exact, p, c, None);
            }
            model[p] += c;
            subtract(&mut working, minor, p, c, settings.patch);
            abs_flux += c.abs();
            steps.push(CleanStep {
                pixel: p,
                peak: value,
            });
            taken += 1;
        };
        let (next, q_next) = measurement.residual(&model)?;
        let dq_exact = q_next - q;
        let gap = dq_exact - predicted;
        cycles.push(MajorCycle {
            index: cycles.len(),
            components: taken,
            peak_start: first_peak,
            peak_working_end: last_peak,
            q_before: q,
            q_after: q_next,
            dq_exact,
            dq_predicted: predicted,
            gap,
            gap_relative: gap / q,
            dq_audit,
            ascending_steps: ascending,
            abs_flux,
            kappa: q_floor.map(|qf| first_peak * first_peak / (2.0 * (q - qf))),
            reducible: reducible(q),
            stop: minor_stop,
            seconds: cycle_start.elapsed().as_secs_f64(),
        });
        // A cycle can end before its first step only on the component
        // budget, which the next pass reports.
        residual = next;
        q = q_next;
        if minor_stop == MinorStop::Diverged {
            break StopReason::Diverged;
        }
    };
    Ok(Certified {
        model,
        residual,
        q0,
        q_final: q,
        steps,
        cycles,
        stop,
        f,
        seconds: start.elapsed().as_secs_f64(),
    })
}

/// The misfit floor `Q_∞` (an upper bound): conjugate gradients on
/// `Aᴴ W A m = d` from zero, and the exact misfit of the result.
#[derive(Clone, Debug)]
pub struct Floor {
    /// `Q` of the CG model, from its visibilities: an upper bound on `Q_∞`.
    pub q_floor: f64,
    pub iterations: usize,
    /// `‖d − B m‖ / ‖d‖` at the end.
    pub relative_residual: f64,
    pub seconds: f64,
}

/// `Q_∞` by `iterations` CG steps (or until the relative residual is below
/// `tolerance`); `dirty` is the residual image of the empty model.
pub fn misfit_floor<M: Measurement>(
    measurement: &M,
    dirty: &[f64],
    iterations: usize,
    tolerance: f64,
) -> Result<(Floor, Vec<f64>), String> {
    let start = Instant::now();
    let (x, used, rel) =
        clean::conjugate_gradients(|p| measurement.gram_apply(p), dirty, iterations, tolerance)?;
    let (_, q) = measurement.residual(&x)?;
    Ok((
        Floor {
            q_floor: q,
            iterations: used,
            relative_residual: rel,
            seconds: start.elapsed().as_secs_f64(),
        },
        x,
    ))
}

/// The exact recovery coefficient of a component list.
#[derive(Clone, Debug)]
pub struct ErcReport {
    /// Distinct component positions.
    pub k: usize,
    /// `η(S) = max_{q ∉ S} ‖B_SS⁻¹ B_{S,q}‖₁`; `None` when `B_SS` is singular
    /// to working precision or `k` exceeds the limit.
    pub eta: Option<f64>,
    /// The pixel attaining `η`.
    pub worst_pixel: Option<usize>,
    /// Smallest Cholesky pivot of `B_SS` (squared), relative to `b(0)`.
    pub min_pivot: f64,
    /// `k > max_k`: not computed.
    pub skipped: bool,
    /// `k³/3 + k² (N − k)` multiply-adds.
    pub cost: f64,
    pub seconds: f64,
}

/// [`clean::erc`] at the cost the note states: `B_SS = L Lᵀ` once, then two
/// triangular solves per pixel outside `S` (parallel over pixels). `support`
/// may repeat pixels; `n` is the image side (the PSF's `n`).
pub fn erc_certificate(psf: &Psf, support: &[usize], max_k: usize) -> ErcReport {
    let start = Instant::now();
    let mut s: Vec<usize> = support.to_vec();
    s.sort_unstable();
    s.dedup();
    let k = s.len();
    let n = psf.n;
    let pixels = n * n;
    let cost = (k as f64).powi(3) / 3.0 + (k as f64).powi(2) * (pixels - k) as f64;
    let mut report = ErcReport {
        k,
        eta: None,
        worst_pixel: None,
        min_pivot: f64::NAN,
        skipped: k > max_k,
        cost,
        seconds: 0.0,
    };
    if k == 0 || k > max_k {
        report.seconds = start.elapsed().as_secs_f64();
        return report;
    }
    let mut l = clean::gram(psf, &s);
    let mut min_pivot = f64::INFINITY;
    for j in 0..k {
        let mut d = l[j * k + j];
        for t in 0..j {
            d -= l[j * k + t] * l[j * k + t];
        }
        min_pivot = min_pivot.min(d);
        if d <= 1e-13 {
            report.min_pivot = d;
            report.seconds = start.elapsed().as_secs_f64();
            return report;
        }
        let d = d.sqrt();
        l[j * k + j] = d;
        for i in j + 1..k {
            let mut v = l[i * k + j];
            for t in 0..j {
                v -= l[i * k + t] * l[j * k + t];
            }
            l[i * k + j] = v / d;
        }
    }
    report.min_pivot = min_pivot;
    let nn = n as isize;
    let peak = psf.peak();
    let in_s = {
        let mut mask = vec![false; pixels];
        for &p in &s {
            mask[p] = true;
        }
        mask
    };
    let (eta, worst) = (0..pixels)
        .into_par_iter()
        .filter(|&q| !in_s[q])
        .map_init(
            || vec![0.0; k],
            |y, q| {
                for (i, &p) in s.iter().enumerate() {
                    let dx = (p as isize % nn) - (q as isize % nn);
                    let dy = (p as isize / nn) - (q as isize / nn);
                    let mut v = psf.at(dx, dy) / peak;
                    for t in 0..i {
                        v -= l[i * k + t] * y[t];
                    }
                    y[i] = v / l[i * k + i];
                }
                let mut norm = 0.0;
                for i in (0..k).rev() {
                    let mut v = y[i];
                    for t in i + 1..k {
                        v -= l[t * k + i] * y[t];
                    }
                    y[i] = v / l[i * k + i];
                    norm += y[i].abs();
                }
                (norm, q)
            },
        )
        .reduce(
            || (0.0, usize::MAX),
            |a, b| {
                if b.0 > a.0 || (b.0 == a.0 && b.1 < a.1) {
                    b
                } else {
                    a
                }
            },
        );
    report.eta = Some(eta);
    report.worst_pixel = (worst != usize::MAX).then_some(worst);
    report.seconds = start.elapsed().as_secs_f64();
    report
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Rng(u64);

    impl Rng {
        fn next(&mut self) -> f64 {
            self.0 ^= self.0 << 13;
            self.0 ^= self.0 >> 7;
            self.0 ^= self.0 << 17;
            (self.0 >> 11) as f64 / (1u64 << 53) as f64
        }
    }

    fn sampling(count: usize, seed: u64) -> Sampling {
        let mut rng = Rng(seed);
        let mut s = Sampling::default();
        for _ in 0..count {
            s.u.push((rng.next() - 0.5) * 10000.0);
            s.v.push((rng.next() - 0.5) * 10000.0);
            s.w.push(0.5 + rng.next());
        }
        s.normalise();
        s
    }

    const GRID: Grid = Grid {
        n: 16,
        cell: 1.0e-4,
    };

    /// Three sources and white visibility noise on `s`.
    fn data(s: &Sampling, seed: u64) -> Vec<Vis> {
        let mut rng = Rng(seed ^ 0x9e37_79b9_7f4a_7c15);
        let mut truth = vec![0.0; GRID.pixels()];
        truth[GRID.index(4, 5)] = 1.0;
        truth[GRID.index(11, 9)] = -0.6;
        truth[GRID.index(1 + (seed as usize % 13), 13)] = 0.4;
        let mut vis = clean::predict(s, &GRID, &truth);
        for v in &mut vis {
            v.0 += 0.05 * (rng.next() - 0.5);
            v.1 += 0.05 * (rng.next() - 0.5);
        }
        vis
    }

    fn settings(rule: MinorRule, patch: Option<usize>) -> DriverSettings {
        DriverSettings {
            gain: 0.1,
            threshold: 1e-6,
            max_components: 400,
            max_major: 20,
            max_minor: 60,
            patch,
            rule,
            floor_tolerance: None,
            audit: true,
            divergence_limit: 0.0,
        }
    }

    #[test]
    fn gram_gap_is_zero_with_the_exact_beam() {
        let s = sampling(120, 21);
        let vis = data(&s, 21);
        let m = DftMeasurement {
            sampling: &s,
            grid: GRID,
            vis: &vis,
        };
        let b = clean::psf(&s, &GRID);
        let out = run(&m, &b, &b, &settings(MinorRule::MajorGain(0.5), None), None).unwrap();
        assert!(out.cycles.len() >= 3);
        assert_eq!(out.f, 0.0);
        for c in &out.cycles {
            assert!(
                c.gap.abs() <= 1e-11 * c.q_before,
                "cycle {}: {}",
                c.index,
                c.gap
            );
            assert!(c.dq_exact < 0.0);
            assert_eq!(c.ascending_steps, 0);
        }
    }

    #[test]
    fn gram_gap_is_nonzero_with_a_patch_and_equals_its_closed_form() {
        let (mut positive, mut negative) = (0, 0);
        for seed in 1..=8u64 {
            let s = sampling(120, seed);
            let vis = data(&s, seed);
            let m = DftMeasurement {
                sampling: &s,
                grid: GRID,
                vis: &vis,
            };
            let b = clean::psf(&s, &GRID);
            let patch = 2;
            let out = run(
                &m,
                &b,
                &b,
                &settings(MinorRule::MajorGain(0.9), Some(patch)),
                None,
            )
            .unwrap();
            let largest = out
                .cycles
                .iter()
                .map(|c| c.gap_relative.abs())
                .fold(0.0, f64::max);
            assert!(
                largest > 1e-6,
                "seed {seed}: largest relative gap {largest}"
            );
            // gap = Σ_{i<j} c_i c_j D(p_j − p_i) with D the beam outside the
            // patch, exactly (the beam's own peak is inside the patch).
            let n = GRID.n as isize;
            let outside = |dx: isize, dy: isize| {
                if dx.abs() > patch as isize || dy.abs() > patch as isize {
                    b.at(dx, dy)
                } else {
                    0.0
                }
            };
            let mut first = 0;
            for c in &out.cycles {
                let comps = &out.steps[first..first + c.components];
                first += c.components;
                let mut closed = 0.0;
                for j in 0..comps.len() {
                    for i in 0..j {
                        let (pi, pj) = (comps[i].pixel as isize, comps[j].pixel as isize);
                        let d = outside(pj % n - pi % n, pj / n - pi / n);
                        closed += 0.1 * comps[i].peak * 0.1 * comps[j].peak * d;
                    }
                }
                assert!(
                    (closed - c.gap).abs() <= 1e-10 * c.q_before,
                    "seed {seed}, cycle {}: {closed} against {}",
                    c.index,
                    c.gap
                );
                // The audit reproduces the exact change of Q to rounding.
                assert!((c.dq_audit - c.dq_exact).abs() <= 1e-10 * c.q_before);
                if c.gap > 1e-6 * c.q_before {
                    positive += 1;
                } else if c.gap < -1e-6 * c.q_before {
                    negative += 1;
                }
            }
        }
        // Both signs occur: the gap is a quadratic form in the components
        // with the indefinite exterior beam, not a one-sided error.
        assert!(
            positive > 0 && negative > 0,
            "{positive} positive, {negative} negative"
        );
    }

    #[test]
    fn provable_rule_never_ascends() {
        let mut clark_rises = 0;
        for seed in 1..=24u64 {
            let s = sampling(120, seed);
            let vis = data(&s, seed);
            let m = DftMeasurement {
                sampling: &s,
                grid: GRID,
                vis: &vis,
            };
            let b = clean::psf(&s, &GRID);
            for patch in [1, 2, 4] {
                let provable = run(
                    &m,
                    &b,
                    &b,
                    &settings(MinorRule::Provable, Some(patch)),
                    None,
                )
                .unwrap();
                assert_eq!(provable.ascending_steps(), 0, "seed {seed}, patch {patch}");
                for c in &provable.cycles {
                    assert!(c.dq_exact <= 0.0, "seed {seed}, patch {patch}");
                }
                let long = run(
                    &m,
                    &b,
                    &b,
                    &settings(MinorRule::MajorGain(0.99), Some(patch)),
                    None,
                )
                .unwrap();
                clark_rises += long.ascending_steps();
            }
        }
        // The property is not vacuous: long minor cycles on the same patches
        // do raise the misfit.
        assert!(clark_rises > 0);
    }

    #[test]
    fn floor_and_stopping_rule() {
        let s = sampling(60, 5);
        let vis = data(&s, 5);
        let m = DftMeasurement {
            sampling: &s,
            grid: GRID,
            vis: &vis,
        };
        let b = clean::psf(&s, &GRID);
        let (d, q0) = m.residual(&vec![0.0; GRID.pixels()]).unwrap();
        let (floor, _) = misfit_floor(&m, &d, 400, 1e-12).unwrap();
        assert!(floor.q_floor >= -1e-12 && floor.q_floor < q0);
        let mut set = settings(MinorRule::MajorGain(0.8), None);
        set.max_components = 100_000;
        set.max_major = 1000;
        set.max_minor = 200;
        set.floor_tolerance = Some(0.05);
        let out = run(&m, &b, &b, &set, Some(floor.q_floor)).unwrap();
        assert_eq!(out.stop, StopReason::Floor);
        assert!((out.q_final - floor.q_floor) / (q0 - floor.q_floor) < 0.05);
        assert!(out.q_final >= floor.q_floor - 1e-9 * q0);
    }

    #[test]
    fn erc_certificate_matches_the_direct_erc() {
        let s = sampling(300, 9);
        let b = clean::psf(&s, &GRID);
        let support = vec![
            GRID.index(2, 3),
            GRID.index(9, 4),
            GRID.index(13, 12),
            GRID.index(9, 4),
        ];
        let fast = erc_certificate(&b, &support, 100);
        let mut unique = support.clone();
        unique.sort_unstable();
        unique.dedup();
        let direct = clean::erc(&b, &GRID, &unique).unwrap();
        assert_eq!(fast.k, 3);
        assert!((fast.eta.unwrap() - direct).abs() < 1e-10);
        assert!(erc_certificate(&b, &support, 2).skipped);
        // Adjacent pixels on an oversampled beam: still factorisable here,
        // and the certificate fails.
        let close = vec![GRID.index(8, 8), GRID.index(9, 8)];
        assert!(erc_certificate(&b, &close, 10).eta.unwrap() >= 0.0);
    }

    #[test]
    fn wgridder_measurement_is_consistent_with_its_beam() {
        // A small random array: uvw in metres, one channel at the speed of
        // light so that metres are wavelengths.
        let mut rng = Rng(77);
        let nrow = 300;
        let mut uvw = Vec::new();
        for _ in 0..nrow {
            uvw.push((rng.next() - 0.5) * 4000.0);
            uvw.push((rng.next() - 0.5) * 4000.0);
            uvw.push((rng.next() - 0.5) * 50.0);
        }
        let freq = vec![299_792_458.0];
        let wgt: Vec<f64> = (0..nrow).map(|_| 0.5 + rng.next()).collect();
        let vis = vec![Complex::new(0.0, 0.0); nrow];
        let n = 32;
        let opts = Options {
            do_wgridding: false,
            ..Options::default()
        };
        let m = WgridMeasurement::new(uvw, freq, vis, wgt, n, 1.0e-4, 1e-12, opts).unwrap();
        let b = m.psf().unwrap();
        assert!((b.peak() - 1.0).abs() < 1e-10);
        // A point off centre, asymmetric in both axes.
        let p = 5 * n + 23;
        let mut model = vec![0.0; n * n];
        model[p] = 1.0;
        let image = m.gram_apply(&model).unwrap();
        let mut expected = vec![0.0; n * n];
        subtract(&mut expected, &b, p, -1.0, None);
        for (a, e) in image.iter().zip(&expected) {
            assert!((a - e).abs() < 1e-9, "{a} against {e}");
        }
        // And CLEAN on its visibilities: the gap is rounding.
        let mut data = WgridMeasurement { ..m };
        data.vis = data.predict(&model).unwrap();
        let out = run(
            &data,
            &b,
            &b,
            &settings(MinorRule::MajorGain(0.5), None),
            None,
        )
        .unwrap();
        for c in &out.cycles {
            assert!(c.gap.abs() <= 1e-8 * c.q_before);
        }
        let small = psf_from_image(n, &data.psf_image(n).unwrap());
        assert!((small.at(0, 0) - b.at(0, 0)).abs() < 1e-10);
        assert_eq!(small.at(n as isize - 1, 0), 0.0);
        assert!(truncation_bound(&b, &small, None) > 0.0);
    }
}
