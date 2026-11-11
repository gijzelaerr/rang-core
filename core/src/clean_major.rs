// SPDX-License-Identifier: GPL-3.0-or-later
//! Major and minor cycles of CLEAN as inexact Newton on the misfit: a driver
//! whose visibility passes are scheduled by a provable rule, an exact
//! FFT-batched subtraction on the double-size grid, and an optimisation phase
//! on each cycle's support. Research note: `research/clean-major-cycles.md`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The misfit is a quadratic with Hessian the Gram matrix `B` of the atoms:
//! for an increment `Δ`, `Q(m + Δ) − Q(m) = −⟨r, Δ⟩ + ½ Δᵀ B Δ` exactly. A minor
//! cycle believes the same change with the beam `b̃` it subtracts; summed over
//! its steps the belief is `dQ̃ = Σ_j (−c_j r̃_j + ½ c_j² b̃(0))` and the
//! difference, the Gram gap, is `Σ_{i<j} c_i c_j D(x_j, x_i) + ½ Σ_j c_j² D(x_j, x_j)`
//! with `D = B − b̃`. If `|D(q, p)| ≤ f(p)` for every target `q`, the gap is at
//! most `Σ_j |c_j| Σ_{i<j} |c_i| f(p_i)` (the diagonal vanishes when
//! `b̃(0) = B_pp`), a number the minor cycle can keep as it goes. Hence:
//!
//! - [`CycleRule::Provable`], Theorem 6 with a per-component bound: continue
//!   while `Σ_{i<j} |c_i| f(p_i) < (1 − γ/2) |r̃_p|`; every step descends;
//! - [`CycleRule::Cycle`]`(θ)`, the cycle-level rule: continue while the gap
//!   bound stays below `(1 − θ) |dQ̃|`; the whole cycle then lowers `Q` by at
//!   least `θ |dQ̃|` (individual steps may rise);
//! - [`CycleRule::Threshold`]: run the minor cycle to the threshold (one
//!   visibility pass per cycle; exact when `b̃` is the Gram matrix);
//! - [`CycleRule::MajorGain`]: WSClean's `-mgain`, for comparison.
//!
//! `f(p)` has two parts: a uniform truncation bound (the beam against the
//! double-size beam, [`crate::clean_certified::truncation_bound`]) and the
//! w-term of the double-size beam, [`w_term_bound`]: the double-size PSF is
//! the Gram column of the phase centre, and for a component at `x_p` the true
//! Gram differs from it by at most `2π Σ_k W_k |w_k| · |n_q − n_p − n(x_q − x_p)|`
//! (`n = √(1 − l² − m²) − 1`), zero at the phase centre.
//!
//! [`FftConvolver`] applies the double-size beam to a batch of components by
//! one forward and one inverse FFT on the `2n × 2n` grid: circular
//! convolution there equals the linear convolution on the `n × n` image
//! because the offsets `−(n−1)…(n−1)` fall on distinct residues modulo `2n`.
//! [`Subtraction::Batched`] uses it for Clark-style batches whose picks are
//! exact on an active set and whose full image is corrected exactly after
//! each batch, so the only inexactness left for the visibility pass is the
//! w-term (and the gridder's ε).

use crate::clean::{CleanStep, Psf, argmax_abs, subtract};
use crate::clean_certified::{Measurement, MinorStop, StopReason, WgridMeasurement};
use rayon::prelude::*;
use rustfft::num_complex::Complex;
use rustfft::{Fft, FftPlanner};
use std::sync::Arc;
use std::time::Instant;

const C_LIGHT: f64 = 299_792_458.0;

/// `n − 1 = √(1 − l² − m²) − 1`, computed without cancellation.
fn nm1(l: f64, m: f64) -> f64 {
    let s = l * l + m * m;
    -s / ((1.0 - s).max(0.0).sqrt() + 1.0)
}

/// `Σ_k W_k |w_k|` in wavelengths over every row and channel, with the
/// measurement's normalised weights: the weighted mean |w|.
pub fn mean_abs_w(m: &WgridMeasurement) -> f64 {
    let nchan = m.freq.len();
    let mut total = 0.0;
    for (row, w) in m.uvw.chunks_exact(3).map(|c| c[2]).enumerate() {
        for (ch, &f) in m.freq.iter().enumerate() {
            total += m.wgt[row * nchan + ch] * (w * f / C_LIGHT).abs();
        }
    }
    total
}

/// The geometric factor `max_q |n_q − n_p − n(x_q − x_p)|` for pixel `p` of a
/// `side × side` image with `cell` radians per pixel (gridder layout, pixel
/// `(i, j)` at `((i − side/2) cell, (j − side/2) cell)`), maximised over the
/// image boundary. To second order the quantity is `|x_p · (x_q − x_p)|`,
/// linear in `x_q`, so its maximum over the square is on the boundary; the
/// unit test checks this against the full maximum.
fn w_geometry(side: usize, cell: f64, p: usize) -> f64 {
    let half = (side / 2) as f64;
    let (pi, pj) = ((p / side) as f64 - half, (p % side) as f64 - half);
    let (lp, mp) = (pi * cell, pj * cell);
    let np = nm1(lp, mp);
    let mut worst = 0.0_f64;
    let mut visit = |qi: f64, qj: f64| {
        let (lq, mq) = ((qi - half) * cell, (qj - half) * cell);
        let g = (nm1(lq, mq) - np - nm1(lq - lp, mq - mp)).abs();
        worst = worst.max(g);
    };
    let last = (side - 1) as f64;
    for t in 0..side {
        let t = t as f64;
        visit(0.0, t);
        visit(last, t);
        visit(t, 0.0);
        visit(t, last);
    }
    worst
}

/// The per-pixel w-term bound of the double-size beam:
/// `f_w(p) = 2π w̄ max_q |n_q − n_p − n(x_q − x_p)|`, with `w̄ = Σ_k W_k |w_k|`
/// ([`mean_abs_w`]). Every entry of the true Gram column of pixel `p` is
/// within `f_w(p)` of the double-size beam shifted to `p`, because the
/// `u · Δx` phases cancel and `|cos a − cos b| ≤ |a − b|`. Capped at 2, the
/// bound from `|cos| ≤ 1` and `Σ_k W_k = 1`.
pub fn w_term_bound(side: usize, cell: f64, mean_abs_w: f64) -> Vec<f64> {
    (0..side * side)
        .into_par_iter()
        .map(|p| (2.0 * std::f64::consts::PI * mean_abs_w * w_geometry(side, cell, p)).min(2.0))
        .collect()
}

/// Applies a [`Psf`] (offsets `±(n−1)`) to a sparse set of components by FFT
/// on the `2n × 2n` grid: `out(x) = Σ_p c_p b(x − x_p)` on the `n × n` image,
/// in the orientation of [`subtract`] (`dx` along the fast axis).
pub struct FftConvolver {
    n: usize,
    /// FFT of the wrapped kernel, transposed (row = fast-axis frequency).
    kernel: Vec<Complex<f64>>,
    forward: Arc<dyn Fft<f64>>,
    inverse: Arc<dyn Fft<f64>>,
}

fn rows_fft(data: &mut [Complex<f64>], len: usize, fft: &Arc<dyn Fft<f64>>) {
    let scratch = fft.get_inplace_scratch_len();
    data.par_chunks_mut(len).for_each_init(
        || vec![Complex::new(0.0, 0.0); scratch],
        |s, row| fft.process_with_scratch(row, s),
    );
}

fn transpose(src: &[Complex<f64>], len: usize) -> Vec<Complex<f64>> {
    let mut out = vec![Complex::new(0.0, 0.0); len * len];
    out.par_chunks_mut(len).enumerate().for_each(|(c, row)| {
        for (r, value) in row.iter_mut().enumerate() {
            *value = src[r * len + c];
        }
    });
    out
}

impl FftConvolver {
    pub fn new(psf: &Psf) -> FftConvolver {
        let n = psf.n;
        let l = 2 * n;
        let mut planner = FftPlanner::<f64>::new();
        let forward = planner.plan_fft_forward(l);
        let inverse = planner.plan_fft_inverse(l);
        let off = (n - 1) as isize;
        let mut k = vec![Complex::new(0.0, 0.0); l * l];
        for dy in -off..=off {
            for dx in -off..=off {
                let r = (dy + l as isize) as usize % l;
                let c = (dx + l as isize) as usize % l;
                k[r * l + c] = Complex::new(psf.at(dx, dy), 0.0);
            }
        }
        rows_fft(&mut k, l, &forward);
        let mut kt = transpose(&k, l);
        rows_fft(&mut kt, l, &forward);
        FftConvolver {
            n,
            kernel: kt,
            forward,
            inverse,
        }
    }

    pub fn side(&self) -> usize {
        self.n
    }

    /// `Σ_p c_p b(· − x_p)` on the `n × n` image for components `(p, c_p)`.
    pub fn apply(&self, components: &[(usize, f64)]) -> Vec<f64> {
        let n = self.n;
        let l = 2 * n;
        let mut g = vec![Complex::new(0.0, 0.0); l * l];
        for &(p, c) in components {
            g[(p / n) * l + (p % n)] += c;
        }
        // Rows n..2n are zero: transform only the first n rows.
        rows_fft(&mut g[..n * l], l, &self.forward);
        let mut t = transpose(&g, l);
        rows_fft(&mut t, l, &self.forward);
        t.par_iter_mut()
            .zip(self.kernel.par_iter())
            .for_each(|(a, k)| *a *= k);
        rows_fft(&mut t, l, &self.inverse);
        let mut g = transpose(&t, l);
        rows_fft(&mut g[..n * l], l, &self.inverse);
        let scale = 1.0 / (l * l) as f64;
        let mut out = vec![0.0; n * n];
        out.par_chunks_mut(n).enumerate().for_each(|(y, row)| {
            for (x, value) in row.iter_mut().enumerate() {
                *value = g[y * l + x].re * scale;
            }
        });
        out
    }
}

/// How a minor cycle updates its working residual.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Subtraction {
    /// Högbom: argmax over the image and a full-image beam subtraction per
    /// component (`n²` per step).
    Direct,
    /// Clark-style batches: picks on the `active` largest pixels, updated
    /// exactly with the beam (`active` per step); a batch ends when the
    /// active peak falls below the largest pixel left outside, and the whole
    /// image is then corrected by one [`FftConvolver::apply`].
    Batched { active: usize },
}

/// When a minor cycle hands back to a visibility pass.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum CycleRule {
    /// WSClean's `-mgain`: stop when the working peak falls below
    /// `(1 − mgain)` of the cycle's first peak.
    MajorGain(f64),
    /// Theorem 6 with per-component bounds: continue while
    /// `Σ_{i<j} |c_i| f(p_i) < (1 − γ/2) |r̃_p|`.
    Provable,
    /// The cycle-level rule: continue while the gap bound stays below
    /// `(1 − θ) |dQ̃|`.
    Cycle(f64),
    /// Run to the threshold.
    Threshold,
}

impl CycleRule {
    pub fn name(&self) -> String {
        match self {
            CycleRule::MajorGain(g) => format!("mgain-{g}"),
            CycleRule::Provable => "provable".into(),
            CycleRule::Cycle(t) => format!("cycle-{t}"),
            CycleRule::Threshold => "threshold".into(),
        }
    }
}

/// The optimisation phase: after a cycle's greedy picks, the exact
/// least-squares fit of the cycle's increment on its support, by conjugate
/// gradients on the (symmetrised) beam Gram matrix `B̃_TT`, started at the
/// greedy increment, so the model misfit can only fall.
#[derive(Clone, Copy, Debug)]
pub struct OptPhase {
    /// Skip the phase when the cycle touched more distinct pixels.
    pub max_support: usize,
    pub iterations: usize,
}

/// Settings of [`run_cycles`].
#[derive(Clone, Copy, Debug)]
pub struct CycleSettings {
    pub gain: f64,
    /// Stop once the exact residual peak falls below this.
    pub threshold: f64,
    /// The minor cycles' own threshold (default `threshold`): a margin below
    /// it absorbs the gap of the last cycle, so that its visibility pass
    /// usually lands below `threshold` and ends the run.
    pub minor_threshold: Option<f64>,
    pub max_components: usize,
    pub max_major: usize,
    pub rule: CycleRule,
    pub subtraction: Subtraction,
    /// A uniform bound on `|B − b̃|` besides the per-pixel one (a beam
    /// truncation, [`crate::clean_certified::truncation_bound`]).
    pub uniform_bound: f64,
    pub opt_phase: Option<OptPhase>,
    /// Radler's divergence limit; zero disables it.
    pub divergence_limit: f64,
    /// Stop once `(Q − Q_∞)/(Q_0 − Q_∞)` falls below this.
    pub floor_tolerance: Option<f64>,
}

impl Default for CycleSettings {
    fn default() -> CycleSettings {
        CycleSettings {
            gain: 0.1,
            threshold: 0.0,
            minor_threshold: None,
            max_components: 100_000,
            max_major: 100,
            rule: CycleRule::MajorGain(0.8),
            subtraction: Subtraction::Direct,
            uniform_bound: 0.0,
            opt_phase: None,
            divergence_limit: 4.0,
            floor_tolerance: None,
        }
    }
}

/// The beams of a run.
#[derive(Clone, Copy)]
pub struct Beams<'a> {
    /// The beam the minor cycle subtracts.
    pub minor: &'a Psf,
    /// Its FFT convolver (required for [`Subtraction::Batched`]).
    pub fft: Option<&'a FftConvolver>,
    /// A reference beam for the step audit (the double-size beam when the
    /// minor beam is truncated): a step "ascends" when it raises the misfit
    /// of the reference quadratic. `O(J²)` per cycle of `J` steps.
    pub reference: Option<&'a Psf>,
    /// The per-pixel bound `f(p)` on `|B − b̃|` (the w-term), if any.
    pub pixel_bound: Option<&'a [f64]>,
}

/// One cycle (minor cycle, optional optimisation phase, visibility pass).
#[derive(Clone, Debug)]
pub struct CycleRecord {
    pub index: usize,
    pub components: usize,
    /// FFT corrections in the cycle ([`Subtraction::Batched`]).
    pub batches: usize,
    pub peak_start: f64,
    pub peak_working_end: f64,
    pub q_before: f64,
    pub q_after: f64,
    pub dq_exact: f64,
    /// `dQ̃`, the minor cycle's belief (including the optimisation phase).
    pub dq_predicted: f64,
    pub gap: f64,
    pub gap_relative: f64,
    /// The running bound `Σ_j |c_j| Σ_{i<j} |c_i| f(p_i)` on `|gap|` of the
    /// greedy part.
    pub gap_bound: f64,
    pub abs_flux: f64,
    /// Steps that raise the reference quadratic (audit; zero without one).
    pub ascending_steps: usize,
    pub audited: bool,
    /// Distinct pixels of the optimisation phase (zero when skipped).
    pub opt_support: usize,
    pub opt_iterations: usize,
    /// The optimisation phase's change of the model quadratic (≤ 0).
    pub opt_dq_model: f64,
    pub kappa: Option<f64>,
    pub reducible: Option<f64>,
    pub stop: MinorStop,
    pub minor_seconds: f64,
    pub opt_seconds: f64,
    pub major_seconds: f64,
}

/// The outcome of [`run_cycles`].
#[derive(Clone, Debug)]
pub struct CycleRun {
    pub model: Vec<f64>,
    pub residual: Vec<f64>,
    pub q0: f64,
    pub q_final: f64,
    pub steps: Vec<CleanStep>,
    pub cycles: Vec<CycleRecord>,
    pub stop: StopReason,
    pub seconds: f64,
    /// The visibility passes, the initial residual included.
    pub major_seconds: f64,
    pub minor_seconds: f64,
    pub opt_seconds: f64,
}

impl CycleRun {
    pub fn ascending_steps(&self) -> usize {
        self.cycles.iter().map(|c| c.ascending_steps).sum()
    }

    /// Cycles whose exact change of `Q` is positive.
    pub fn ascending_cycles(&self) -> usize {
        self.cycles.iter().filter(|c| c.dq_exact > 0.0).count()
    }
}

/// The bookkeeping of one minor cycle.
struct Ledger<'a> {
    gain: f64,
    b0: f64,
    first_peak: f64,
    predicted: f64,
    abs_flux: f64,
    /// `Σ_{i<j} |c_i| f(p_i)`: the bound on `|r − r̃|` at the next pick.
    err: f64,
    gap_bound: f64,
    taken: usize,
    comps: Vec<(usize, f64)>,
    ascending: usize,
    uniform: f64,
    pixel: Option<&'a [f64]>,
    minor: &'a Psf,
    reference: Option<&'a Psf>,
}

impl Ledger<'_> {
    /// Whether the rule ends the cycle before a step at working value `value`.
    fn rule_stops(&self, rule: CycleRule, value: f64) -> bool {
        if self.taken == 0 {
            return false;
        }
        let c = self.gain * value / self.b0;
        match rule {
            CycleRule::MajorGain(g) => value.abs() < (1.0 - g) * self.first_peak,
            CycleRule::Provable => self.err >= (1.0 - self.gain / 2.0) * value.abs(),
            CycleRule::Cycle(theta) => {
                let pred = self.predicted - c * value + 0.5 * c * c * self.b0;
                let bound = self.gap_bound + c.abs() * self.err;
                bound > (1.0 - theta) * (-pred)
            }
            CycleRule::Threshold => false,
        }
    }

    /// Take the step at pixel `p` with working value `value`; returns `c`.
    fn take(&mut self, p: usize, value: f64, n: usize) -> f64 {
        let c = self.gain * value / self.b0;
        self.predicted += -c * value + 0.5 * c * c * self.b0;
        self.gap_bound += c.abs() * self.err;
        let f = self.uniform + self.pixel.map_or(0.0, |b| b[p]);
        self.err += c.abs() * f;
        self.abs_flux += c.abs();
        if let Some(reference) = self.reference {
            // r_true(p) = r̃(p) − Σ_i c_i (b_ref − b̃)(x_p − x_i)
            let (px, py) = ((p % n) as isize, (p / n) as isize);
            let mut r_true = value;
            for &(q, cq) in &self.comps {
                let (dx, dy) = (px - (q % n) as isize, py - (q / n) as isize);
                r_true -= cq * (reference.at(dx, dy) - self.minor.at(dx, dy));
            }
            if -c * r_true + 0.5 * c * c * reference.peak() > 0.0 {
                self.ascending += 1;
            }
        }
        self.comps.push((p, c));
        self.taken += 1;
        c
    }
}

/// The top `active` pixels of `|w|` and the largest `|w|` left outside.
fn select_active(w: &[f64], active: usize) -> (Vec<usize>, f64) {
    if active >= w.len() {
        return ((0..w.len()).collect(), 0.0);
    }
    let mut idx: Vec<usize> = (0..w.len()).collect();
    idx.select_nth_unstable_by(active, |&i, &j| w[j].abs().total_cmp(&w[i].abs()));
    let outside = w[idx[active]].abs();
    idx.truncate(active);
    (idx, outside)
}

/// What the optimisation phase found.
struct Refit {
    increments: Vec<(usize, f64)>,
    /// The change of the model quadratic.
    dq: f64,
    iterations: usize,
}

/// The optimisation phase on the distinct pixels of `comps`, or `None` when
/// the support exceeds the limit.
fn optimise(
    working: &[f64],
    beam: &Psf,
    comps: &[(usize, f64)],
    opt: &OptPhase,
) -> Result<Option<Refit>, String> {
    let mut support: Vec<usize> = comps.iter().map(|&(p, _)| p).collect();
    support.sort_unstable();
    support.dedup();
    let k = support.len();
    if k == 0 || k > opt.max_support {
        return Ok(None);
    }
    let n = beam.n as isize;
    let mut g = vec![0.0; k * k];
    g.par_chunks_mut(k).enumerate().for_each(|(i, row)| {
        let p = support[i] as isize;
        for (j, value) in row.iter_mut().enumerate() {
            let q = support[j] as isize;
            let (dx, dy) = (p % n - q % n, p / n - q / n);
            *value = 0.5 * (beam.at(dx, dy) + beam.at(-dx, -dy));
        }
    });
    let rhs: Vec<f64> = support.iter().map(|&p| working[p]).collect();
    let apply = |x: &[f64]| -> Result<Vec<f64>, String> {
        Ok(g.par_chunks(k)
            .map(|row| row.iter().zip(x).map(|(a, b)| a * b).sum())
            .collect())
    };
    let (y, used, _) = crate::clean::conjugate_gradients(apply, &rhs, opt.iterations, 1e-12)?;
    let gy = apply(&y)?;
    let dq: f64 = y
        .iter()
        .zip(&rhs)
        .zip(&gy)
        .map(|((yi, ri), gi)| -yi * ri + 0.5 * yi * gi)
        .sum();
    Ok(Some(Refit {
        increments: support.into_iter().zip(y).collect(),
        dq,
        iterations: used,
    }))
}

/// Cotton-Schwab CLEAN with scheduled visibility passes: minor cycles
/// subtract `beams.minor` (directly or in FFT batches), stop by
/// `settings.rule`, optionally refit their support, and hand back to one
/// exact residual evaluation of `measurement`.
pub fn run_cycles<M: Measurement>(
    measurement: &M,
    beams: Beams<'_>,
    settings: &CycleSettings,
    q_floor: Option<f64>,
) -> Result<CycleRun, String> {
    let start = Instant::now();
    let n = measurement.side();
    let minor = beams.minor;
    if minor.n != n {
        return Err("beam must match the image side".into());
    }
    if let Subtraction::Batched { .. } = settings.subtraction
        && beams.fft.is_none_or(|f| f.side() != n)
    {
        return Err("batched subtraction needs an FFT convolver of the image side".into());
    }
    if beams.pixel_bound.is_some_and(|b| b.len() != n * n) {
        return Err("pixel bound must have one entry per pixel".into());
    }
    let reference = beams
        .reference
        .filter(|r| r.n == n && settings.uniform_bound > 0.0);
    let b0 = minor.peak();
    let t = Instant::now();
    let mut model = vec![0.0; n * n];
    let (mut residual, q0) = measurement.residual(&model)?;
    let mut major_seconds = t.elapsed().as_secs_f64();
    let (mut minor_seconds, mut opt_seconds) = (0.0, 0.0);
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
        let t_minor = Instant::now();
        let mut ledger = Ledger {
            gain: settings.gain,
            b0,
            first_peak: peak.abs(),
            predicted: 0.0,
            abs_flux: 0.0,
            err: 0.0,
            gap_bound: 0.0,
            taken: 0,
            comps: Vec::new(),
            ascending: 0,
            uniform: settings.uniform_bound,
            pixel: beams.pixel_bound,
            minor,
            reference,
        };
        let mut working = residual.clone();
        let mut batches = 0;
        let mut last_peak: f64;
        // The checks every rule shares, before a step at working value v.
        let minor_threshold = settings.minor_threshold.unwrap_or(settings.threshold);
        let shared = |ledger: &Ledger, v: f64, total: usize| -> Option<MinorStop> {
            if v.abs() < minor_threshold {
                Some(MinorStop::Threshold)
            } else if settings.divergence_limit > 0.0
                && v.abs() > settings.divergence_limit * ledger.first_peak
            {
                Some(MinorStop::Diverged)
            } else if ledger.rule_stops(settings.rule, v) {
                Some(MinorStop::Rule)
            } else if total >= settings.max_components {
                Some(MinorStop::Budget)
            } else {
                None
            }
        };
        let minor_stop = match settings.subtraction {
            Subtraction::Direct => loop {
                let (p, v) = argmax_abs(&working);
                last_peak = v.abs();
                if let Some(s) = shared(&ledger, v, steps.len()) {
                    break s;
                }
                let c = ledger.take(p, v, n);
                model[p] += c;
                subtract(&mut working, minor, p, c, None);
                steps.push(CleanStep { pixel: p, peak: v });
            },
            Subtraction::Batched { active } => {
                let fft = beams.fft.expect("checked above");
                loop {
                    let (set, outside) = select_active(&working, active);
                    let mut vals: Vec<f64> = set.iter().map(|&q| working[q]).collect();
                    let mut batch: Vec<(usize, f64)> = Vec::new();
                    let stop = loop {
                        let (k, v) = argmax_abs(&vals);
                        last_peak = v.abs();
                        if let Some(s) = shared(&ledger, v, steps.len()) {
                            // The active peak can understate the image peak
                            // (pixels outside the set are stale): a value
                            // rule ends only the batch, and the next batch
                            // decides on the exactly corrected image.
                            let value_rule = matches!(s, MinorStop::Threshold | MinorStop::Rule);
                            if value_rule && !batch.is_empty() {
                                break None;
                            }
                            break Some(s);
                        }
                        if !batch.is_empty() && v.abs() < outside {
                            break None;
                        }
                        let p = set[k];
                        let c = ledger.take(p, v, n);
                        model[p] += c;
                        let (px, py) = ((p % n) as isize, (p / n) as isize);
                        vals.par_iter_mut()
                            .zip(set.par_iter())
                            .for_each(|(val, &q)| {
                                let (dx, dy) = ((q % n) as isize - px, (q / n) as isize - py);
                                *val -= c * minor.at(dx, dy);
                            });
                        batch.push((p, c));
                        steps.push(CleanStep { pixel: p, peak: v });
                    };
                    if !batch.is_empty() {
                        let correction = fft.apply(&batch);
                        working
                            .par_iter_mut()
                            .zip(correction.par_iter())
                            .for_each(|(w, c)| *w -= c);
                        batches += 1;
                    }
                    if let Some(s) = stop {
                        break s;
                    }
                }
            }
        };
        minor_seconds += t_minor.elapsed().as_secs_f64();
        let minor_elapsed = t_minor.elapsed().as_secs_f64();
        let mut opt_support = 0;
        let mut opt_iterations = 0;
        let mut opt_dq = 0.0;
        let t_opt = Instant::now();
        if let Some(opt) = settings.opt_phase.as_ref()
            && let Some(refit) = optimise(&working, minor, &ledger.comps, opt)?
        {
            opt_support = refit.increments.len();
            opt_iterations = refit.iterations;
            opt_dq = refit.dq;
            for (p, y) in refit.increments {
                model[p] += y;
            }
        }
        let opt_elapsed = t_opt.elapsed().as_secs_f64();
        opt_seconds += opt_elapsed;
        let t_major = Instant::now();
        let (next, q_next) = measurement.residual(&model)?;
        let major_elapsed = t_major.elapsed().as_secs_f64();
        major_seconds += major_elapsed;
        let predicted = ledger.predicted + opt_dq;
        let dq_exact = q_next - q;
        let gap = dq_exact - predicted;
        cycles.push(CycleRecord {
            index: cycles.len(),
            components: ledger.taken,
            batches,
            peak_start: ledger.first_peak,
            peak_working_end: last_peak,
            q_before: q,
            q_after: q_next,
            dq_exact,
            dq_predicted: predicted,
            gap,
            gap_relative: gap / q,
            gap_bound: ledger.gap_bound,
            abs_flux: ledger.abs_flux,
            ascending_steps: ledger.ascending,
            audited: reference.is_some(),
            opt_support,
            opt_iterations,
            opt_dq_model: opt_dq,
            kappa: q_floor.map(|qf| ledger.first_peak * ledger.first_peak / (2.0 * (q - qf))),
            reducible: reducible(q),
            stop: minor_stop,
            minor_seconds: minor_elapsed,
            opt_seconds: opt_elapsed,
            major_seconds: major_elapsed,
        });
        residual = next;
        q = q_next;
        if minor_stop == MinorStop::Diverged {
            break StopReason::Diverged;
        }
    };
    Ok(CycleRun {
        model,
        residual,
        q0,
        q_final: q,
        steps,
        cycles,
        stop,
        seconds: start.elapsed().as_secs_f64(),
        major_seconds,
        minor_seconds,
        opt_seconds,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::clean::{self, Grid, Sampling, Vis};
    use crate::clean_certified::{DftMeasurement, psf_from_double};
    use crate::wgridder::Options;

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

    fn data(s: &Sampling, seed: u64) -> Vec<Vis> {
        let mut rng = Rng(seed ^ 0x9e37_79b9_7f4a_7c15);
        let mut truth = vec![0.0; GRID.pixels()];
        truth[GRID.index(4, 5)] = 1.0;
        truth[GRID.index(11, 9)] = -0.6;
        truth[GRID.index(1 + (seed as usize % 13), 13)] = 0.4;
        truth[GRID.index(14, 1)] = 0.3;
        let mut vis = clean::predict(s, &GRID, &truth);
        for v in &mut vis {
            v.0 += 0.05 * (rng.next() - 0.5);
            v.1 += 0.05 * (rng.next() - 0.5);
        }
        vis
    }

    fn settings(rule: CycleRule, subtraction: Subtraction) -> CycleSettings {
        CycleSettings {
            gain: 0.1,
            threshold: 1e-3,
            minor_threshold: None,
            max_components: 20_000,
            max_major: 30,
            rule,
            subtraction,
            uniform_bound: 0.0,
            opt_phase: None,
            divergence_limit: 0.0,
            floor_tolerance: None,
        }
    }

    #[test]
    fn fft_batch_equals_direct_subtraction() {
        for (count, n) in [(120usize, 16usize), (80, 13), (200, 24)] {
            let s = sampling(count, n as u64);
            let grid = Grid { n, cell: 1.0e-4 };
            let b = clean::psf(&s, &grid);
            let fft = FftConvolver::new(&b);
            let mut rng = Rng(7 + n as u64);
            let comps: Vec<(usize, f64)> = (0..25)
                .map(|_| {
                    (
                        ((rng.next() * (n * n) as f64) as usize).min(n * n - 1),
                        rng.next() - 0.5,
                    )
                })
                .collect();
            let mut direct = vec![0.0; n * n];
            for &(p, c) in &comps {
                subtract(&mut direct, &b, p, -c, None);
            }
            let fast = fft.apply(&comps);
            let scale: f64 = comps.iter().map(|c| c.1.abs()).sum();
            for (a, e) in fast.iter().zip(&direct) {
                assert!((a - e).abs() < 1e-12 * scale, "n {n}: {a} against {e}");
            }
        }
    }

    #[test]
    fn exact_beam_cycle_gap_is_rounding_and_one_pass_suffices() {
        let s = sampling(150, 3);
        let vis = data(&s, 3);
        let m = DftMeasurement {
            sampling: &s,
            grid: GRID,
            vis: &vis,
        };
        let b = clean::psf(&s, &GRID);
        let fft = FftConvolver::new(&b);
        let beams = Beams {
            minor: &b,
            fft: Some(&fft),
            reference: None,
            pixel_bound: None,
        };
        for sub in [Subtraction::Direct, Subtraction::Batched { active: 24 }] {
            let out = run_cycles(&m, beams, &settings(CycleRule::Threshold, sub), None).unwrap();
            // With the Gram matrix as beam the minor cycle is exact: one
            // visibility pass after the threshold is reached, and it agrees.
            assert_eq!(out.cycles.len(), 1, "{sub:?}");
            assert_eq!(out.stop, StopReason::Threshold);
            let c = &out.cycles[0];
            assert!(c.gap.abs() <= 1e-11 * c.q_before, "{sub:?}: {}", c.gap);
            assert!(c.dq_exact < 0.0);
            if let Subtraction::Batched { .. } = sub {
                assert!(c.batches > 1);
            }
        }
    }

    #[test]
    fn gap_identity_and_bound_with_a_truncated_beam() {
        for seed in 1..=6u64 {
            let s = sampling(120, seed);
            let vis = data(&s, seed);
            let m = DftMeasurement {
                sampling: &s,
                grid: GRID,
                vis: &vis,
            };
            let b = clean::psf(&s, &GRID);
            // The beam a deconvolver computes on the image grid.
            let mut small = vec![0.0; GRID.pixels()];
            let h = (GRID.n / 2) as isize;
            for i in 0..GRID.n {
                for j in 0..GRID.n {
                    small[i * GRID.n + j] = b.at(j as isize - h, i as isize - h);
                }
            }
            let image = crate::clean_certified::psf_from_image(GRID.n, &small);
            let f = crate::clean_certified::truncation_bound(&b, &image, None);
            let beams = Beams {
                minor: &image,
                fft: None,
                reference: Some(&b),
                pixel_bound: None,
            };
            let mut set = settings(CycleRule::MajorGain(0.9), Subtraction::Direct);
            set.uniform_bound = f;
            set.max_major = 6;
            let out = run_cycles(&m, beams, &set, None).unwrap();
            let mut first = 0;
            for c in &out.cycles {
                let comps = &out.steps[first..first + c.components];
                first += c.components;
                let n = GRID.n as isize;
                let mut closed = 0.0;
                for j in 0..comps.len() {
                    for i in 0..j {
                        let (pi, pj) = (comps[i].pixel as isize, comps[j].pixel as isize);
                        let (dx, dy) = (pj % n - pi % n, pj / n - pi / n);
                        let d = b.at(dx, dy) - image.at(dx, dy);
                        closed += 0.1 * comps[i].peak * 0.1 * comps[j].peak * d;
                    }
                }
                assert!(
                    (closed - c.gap).abs() <= 1e-10 * c.q_before.max(c.gap.abs()),
                    "seed {seed}, cycle {}: {closed} against {}",
                    c.index,
                    c.gap
                );
                assert!(c.gap.abs() <= c.gap_bound + 1e-12 * c.q_before.max(c.gap.abs()));
            }
            // The cycle rule then never lets a cycle lose more than (1 − θ).
            set.rule = CycleRule::Cycle(0.5);
            let out = run_cycles(&m, beams, &set, None).unwrap();
            for c in &out.cycles {
                assert!(
                    c.dq_exact <= 0.5 * c.dq_predicted + 1e-12 * c.q_before,
                    "seed {seed}"
                );
            }
            set.rule = CycleRule::Provable;
            let out = run_cycles(&m, beams, &set, None).unwrap();
            assert_eq!(out.ascending_steps(), 0, "seed {seed}");
        }
    }

    #[test]
    fn optimisation_phase_lowers_the_misfit_on_the_same_support() {
        for seed in 1..=6u64 {
            let s = sampling(150, seed);
            let vis = data(&s, seed);
            let m = DftMeasurement {
                sampling: &s,
                grid: GRID,
                vis: &vis,
            };
            let b = clean::psf(&s, &GRID);
            let beams = Beams {
                minor: &b,
                fft: None,
                reference: None,
                pixel_bound: None,
            };
            let mut set = settings(CycleRule::MajorGain(0.8), Subtraction::Direct);
            set.max_major = 1;
            let greedy = run_cycles(&m, beams, &set, None).unwrap();
            set.opt_phase = Some(OptPhase {
                max_support: 256,
                iterations: 200,
            });
            let refit = run_cycles(&m, beams, &set, None).unwrap();
            let support = |model: &[f64]| -> Vec<usize> {
                (0..model.len()).filter(|&p| model[p] != 0.0).collect()
            };
            let (g, r) = (&greedy.cycles[0], &refit.cycles[0]);
            assert_eq!(support(&greedy.model), support(&refit.model));
            assert!(r.opt_support > 0 && r.opt_dq_model < 0.0);
            assert!(refit.q_final < greedy.q_final, "seed {seed}");
            // Exact Gram: the model change is the true change.
            assert!(r.gap.abs() <= 1e-10 * r.q_before);
            assert!((g.dq_exact + r.opt_dq_model - r.dq_exact).abs() <= 1e-10 * r.q_before);
        }
    }

    #[test]
    fn w_term_bound_holds_for_the_double_size_beam() {
        let mut rng = Rng(91);
        let nrow = 400;
        let mut uvw = Vec::new();
        for _ in 0..nrow {
            uvw.push((rng.next() - 0.5) * 400.0);
            uvw.push((rng.next() - 0.5) * 400.0);
            uvw.push((rng.next() - 0.5) * 400.0);
        }
        let freq = vec![C_LIGHT];
        let wgt: Vec<f64> = (0..nrow).map(|_| 0.5 + rng.next()).collect();
        let vis = vec![Complex::new(0.0, 0.0); nrow];
        let n = 32;
        let cell = 1.0e-3;
        let m = WgridMeasurement::new(
            uvw,
            freq,
            vis,
            wgt,
            n,
            cell,
            1e-12,
            Options {
                do_wgridding: true,
                ..Options::default()
            },
        )
        .unwrap();
        let b = psf_from_double(n, &m.psf_image(2 * n).unwrap());
        let bound = w_term_bound(n, cell, mean_abs_w(&m));
        // The boundary maximum equals the full maximum.
        let half = (n / 2) as f64;
        for p in [0, n - 1, 5 * n + 9, n * n - 1, (n / 2) * n + n / 2 + 3] {
            let (pi, pj) = ((p / n) as f64 - half, (p % n) as f64 - half);
            let np = nm1(pi * cell, pj * cell);
            let mut full = 0.0_f64;
            for q in 0..n * n {
                let (qi, qj) = ((q / n) as f64 - half, (q % n) as f64 - half);
                let g = nm1(qi * cell, qj * cell) - np - nm1((qi - pi) * cell, (qj - pj) * cell);
                full = full.max(g.abs());
            }
            assert!((full - w_geometry(n, cell, p)).abs() <= 1e-9 * full.max(1e-30));
        }
        let mut corner_dev = 0.0;
        for p in [
            (n / 2) * n + n / 2,
            0,
            n - 1,
            n * n - 1,
            n * (n - 1),
            3 * n + 20,
        ] {
            let mut delta = vec![0.0; n * n];
            delta[p] = 1.0;
            let column = m.gram_apply(&delta).unwrap();
            let mut shifted = vec![0.0; n * n];
            subtract(&mut shifted, &b, p, -1.0, None);
            let dev = column
                .iter()
                .zip(&shifted)
                .map(|(a, e)| (a - e).abs())
                .fold(0.0, f64::max);
            assert!(
                dev <= bound[p] + 1e-9,
                "pixel {p}: {dev} against {}",
                bound[p]
            );
            if p == (n / 2) * n + n / 2 {
                assert!(dev < 1e-9, "centre {dev}");
                assert_eq!(bound[p], 0.0);
            } else if p == 0 {
                corner_dev = dev;
            }
        }
        // Not vacuous: the w-term moves the corner column measurably.
        assert!(corner_dev > 1e-4, "{corner_dev}");
    }
}
