// SPDX-License-Identifier: GPL-3.0-or-later
//! Forward-backward and FISTA for `½‖y − Φ m‖²_W + R(m)` with `m ≥ 0`, over any
//! [`Measurement`]: the exact gridder or the visibility-free Gram operator.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The weights are normalised, so the gradient at `x` is `G x − d` with
//! `d = Φᴴ W y` and `G = Φᴴ W Φ`, and the misfit is
//! `Q(x) = Q₀ − ⟨d, x⟩ + ½⟨x, G x⟩`. FISTA applies `G` at the extrapolated point
//! only; because `y = (1 + β) x − β x₋₁`, the product `G x` follows by linearity
//! with no second apply, so every iteration has the objective, the duality gap
//! and the optimality residual of `x` for one apply. See
//! `research/gram-solver.md`.

use crate::clean_certified::Measurement;
use rayon::prelude::*;
use std::sync::atomic::{AtomicU64, Ordering};

/// The regulariser and its proximal operator, with `m ≥ 0` inside it.
pub trait Prior {
    /// `argmin_{x ≥ 0} ½‖x − z‖² + step · R(x)`.
    fn prox(&mut self, z: &[f64], step: f64, out: &mut [f64]);
    /// `R(x)`.
    fn value(&mut self, x: &[f64]) -> f64;
    /// `R(x) = Σ λ_i x_i` on `x ≥ 0` when the thresholds are per pixel: the
    /// duality gap and the optimality residual then exist.
    fn thresholds(&self) -> Option<Thresholds<'_>> {
        None
    }
    /// One round of reweighting at `x`.
    fn reweight(&mut self, x: &[f64]);
    /// Change the regularisation weight (continuation).
    fn set_lambda(&mut self, lambda: f64);
}

/// Per-pixel thresholds: `lambda` times a factor per pixel, or times one.
#[derive(Clone, Copy)]
pub struct Thresholds<'a> {
    pub lambda: f64,
    pub factors: Option<&'a [f64]>,
    /// Pixels may be negative: `Σ λ_i |x_i|` without `x ≥ 0`.
    pub signed: bool,
}

impl Thresholds<'_> {
    #[inline]
    fn at(&self, i: usize) -> f64 {
        self.lambda * self.factors.map_or(1.0, |w| w[i])
    }
}

/// `λ ‖x‖₁`, with `x ≥ 0` unless `signed`, optionally reweighted by
/// `δ / (δ + |x_i|)`.
pub struct L1Prior {
    pub lambda: f64,
    pub delta: f64,
    pub signed: bool,
    factors: Option<Vec<f64>>,
}

impl L1Prior {
    pub fn new(lambda: f64, delta: f64) -> L1Prior {
        L1Prior {
            lambda,
            delta,
            signed: false,
            factors: None,
        }
    }

    pub fn signed(lambda: f64, delta: f64) -> L1Prior {
        L1Prior {
            signed: true,
            ..L1Prior::new(lambda, delta)
        }
    }
}

impl Prior for L1Prior {
    fn prox(&mut self, z: &[f64], step: f64, out: &mut [f64]) {
        let tau = step * self.lambda;
        let signed = self.signed;
        let shrink = move |v: f64, t: f64| {
            if signed {
                v.signum() * (v.abs() - t).max(0.0)
            } else {
                (v - t).max(0.0)
            }
        };
        match &self.factors {
            None => out
                .par_iter_mut()
                .zip(z.par_iter())
                .for_each(|(o, v)| *o = shrink(*v, tau)),
            Some(w) => out
                .par_iter_mut()
                .zip(z.par_iter())
                .zip(w.par_iter())
                .for_each(|((o, v), w)| *o = shrink(*v, tau * w)),
        }
    }

    fn value(&mut self, x: &[f64]) -> f64 {
        let sum: f64 = match &self.factors {
            None => x.par_iter().map(|v| v.abs()).sum(),
            Some(w) => x
                .par_iter()
                .zip(w.par_iter())
                .map(|(v, w)| v.abs() * w)
                .sum(),
        };
        self.lambda * sum
    }

    fn thresholds(&self) -> Option<Thresholds<'_>> {
        Some(Thresholds {
            lambda: self.lambda,
            factors: self.factors.as_deref(),
            signed: self.signed,
        })
    }

    fn reweight(&mut self, x: &[f64]) {
        let delta = self.delta;
        self.factors = Some(x.par_iter().map(|v| delta / (delta + v.abs())).collect());
    }

    fn set_lambda(&mut self, lambda: f64) {
        self.lambda = lambda;
    }
}

/// A [`Measurement`] that counts its applies.
pub struct Counted<'a, M: ?Sized> {
    pub inner: &'a M,
    pub applies: AtomicU64,
}

impl<'a, M: Measurement + ?Sized> Counted<'a, M> {
    pub fn new(inner: &'a M) -> Self {
        Counted {
            inner,
            applies: AtomicU64::new(0),
        }
    }

    pub fn count(&self) -> u64 {
        self.applies.load(Ordering::Relaxed)
    }
}

impl<M: Measurement + ?Sized> Measurement for Counted<'_, M> {
    fn side(&self) -> usize {
        self.inner.side()
    }
    fn residual(&self, model: &[f64]) -> Result<(Vec<f64>, f64), String> {
        self.applies.fetch_add(1, Ordering::Relaxed);
        self.inner.residual(model)
    }
    fn gram_apply(&self, x: &[f64]) -> Result<Vec<f64>, String> {
        self.applies.fetch_add(1, Ordering::Relaxed);
        self.inner.gram_apply(x)
    }
}

/// The data side of the problem: taken once, shared by every backend.
#[derive(Clone, Copy)]
pub struct Problem<'a> {
    pub dirty: &'a [f64],
    pub q0: f64,
}

/// Settings of [`solve`].
#[derive(Clone, Debug)]
pub struct Settings {
    /// The step, normally `1 / L`.
    pub step: f64,
    pub max_iterations: usize,
    /// FISTA when true, plain forward-backward when false.
    pub momentum: bool,
    /// O'Donoghue and Candès's gradient restart of the momentum.
    pub restart: bool,
    /// Stop at a duality gap at or below this (absolute, `Jy²`).
    pub gap_tolerance: Option<f64>,
    /// Stop at an optimality residual at or below this (absolute, `Jy`).
    pub kkt_tolerance: Option<f64>,
    /// Stop at `‖x₊ − x‖ ≤ tol ‖x₊‖`.
    pub step_tolerance: Option<f64>,
    /// Evaluate `R(x)` every this many iterations (it can cost transforms).
    pub objective_every: usize,
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            step: 1.0,
            max_iterations: 100,
            momentum: true,
            restart: true,
            gap_tolerance: None,
            kkt_tolerance: None,
            step_tolerance: None,
            objective_every: 1,
        }
    }
}

/// The state of one iterate `x_k`, all on the given backend.
#[derive(Clone, Copy, Debug, Default)]
pub struct Record {
    pub iteration: usize,
    pub objective: f64,
    pub misfit: f64,
    pub penalty: f64,
    /// `P − D`, or NaN when the prior has no per-pixel thresholds.
    pub gap: f64,
    /// `max` over pixels of the violation of the optimality conditions, in the
    /// units of the residual image; NaN as for `gap`.
    pub kkt: f64,
    pub nonzero: usize,
    pub flux: f64,
    /// `⟨Δy, G Δy⟩ / ‖Δy‖²` between consecutive applies; NaN at the first.
    pub curvature: f64,
    /// `‖x_k − x_{k−1}‖ / ‖x_k‖`.
    pub relative_step: f64,
    pub restarted: bool,
}

/// How [`solve`] ended and what it saw on the way.
#[derive(Clone, Debug, Default)]
pub struct Outcome {
    pub x: Vec<f64>,
    /// `G x` of the returned `x`.
    pub gx: Vec<f64>,
    pub last: Record,
    pub iterations: usize,
    pub stop: String,
    pub restarts: usize,
    /// Consecutive iterates with a rise of the objective, among those evaluated.
    pub objective_rises: usize,
    pub largest_rise: f64,
    pub negative_curvatures: usize,
    pub min_curvature: f64,
    pub max_curvature: f64,
}

fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.par_iter().zip(b.par_iter()).map(|(x, y)| x * y).sum()
}

/// `Q`, `D` and the optimality residual of `x` from `G x`.
fn certificate(
    problem: &Problem,
    x: &[f64],
    gx: &[f64],
    thresholds: Option<Thresholds>,
    penalty: Option<f64>,
) -> (f64, f64, f64, f64) {
    let d_x = dot(problem.dirty, x);
    let misfit = problem.q0 - d_x + 0.5 * dot(x, gx);
    let Some(t) = thresholds else {
        return (misfit, penalty.unwrap_or(f64::NAN), f64::NAN, f64::NAN);
    };
    let dirty = problem.dirty;
    let (pen, kkt, scale_max) = (0..x.len())
        .into_par_iter()
        .map(|i| {
            let r = dirty[i] - gx[i];
            let lam = t.at(i);
            let viol = if x[i] > 0.0 {
                (r - lam).abs()
            } else if x[i] < 0.0 {
                (r + lam).abs()
            } else if t.signed {
                (r.abs() - lam).max(0.0)
            } else {
                (r - lam).max(0.0)
            };
            let excess = if t.signed { r.abs() } else { r };
            let bound = if excess > 0.0 {
                lam / excess
            } else {
                f64::INFINITY
            };
            (lam * x[i].abs(), viol, bound)
        })
        .reduce(
            || (0.0, 0.0, f64::INFINITY),
            |a, b| (a.0 + b.0, a.1.max(b.1), a.2.min(b.2)),
        );
    // The dual point s e, e = y − Φ x: ⟨y, e⟩ = 2 Q₀ − ⟨d, x⟩, ‖e‖² = 2 Q.
    let y_e = 2.0 * problem.q0 - d_x;
    let e_e = 2.0 * misfit;
    let s = (y_e / e_e.max(1e-300)).clamp(0.0, scale_max);
    let dual = s * y_e - 0.5 * s * s * e_e;
    let gap = misfit + pen - dual;
    (misfit, pen, gap, kkt)
}

/// FISTA or forward-backward from `x0`. `observer` sees every iterate.
pub fn solve<M: Measurement + ?Sized, P: Prior + ?Sized>(
    op: &M,
    problem: &Problem,
    prior: &mut P,
    settings: &Settings,
    x0: Vec<f64>,
    observer: &mut dyn FnMut(&Record, &[f64]),
) -> Result<Outcome, String> {
    let n2 = x0.len();
    let mut x = x0;
    let mut x_prev = x.clone();
    let mut y = x.clone();
    let mut y_prev = vec![0.0; n2];
    let mut g_y_prev = vec![0.0; n2];
    let mut g_x_prev = vec![0.0; n2];
    let mut z = vec![0.0; n2];
    let mut x_next = vec![0.0; n2];
    let mut t = 1.0_f64;
    let mut beta = 0.0_f64;
    let mut out = Outcome {
        min_curvature: f64::INFINITY,
        max_curvature: f64::NEG_INFINITY,
        ..Outcome::default()
    };
    let mut last_objective = f64::INFINITY;
    let mut restarted = false;
    let every = settings.objective_every.max(1);
    for k in 0..=settings.max_iterations {
        let g_y = op.gram_apply(&y)?;
        // G x = (G y + β G x₋₁) / (1 + β), from y = (1 + β) x − β x₋₁.
        let g_x: Vec<f64> = if beta == 0.0 {
            g_y.clone()
        } else {
            g_y.par_iter()
                .zip(g_x_prev.par_iter())
                .map(|(a, b)| (a + beta * b) / (1.0 + beta))
                .collect()
        };
        let curvature = if k == 0 {
            f64::NAN
        } else {
            let (mut num, mut den) = (0.0, 0.0);
            for i in 0..n2 {
                let d = y[i] - y_prev[i];
                num += d * (g_y[i] - g_y_prev[i]);
                den += d * d;
            }
            if den > 0.0 { num / den } else { f64::NAN }
        };
        if curvature.is_finite() {
            out.min_curvature = out.min_curvature.min(curvature);
            out.max_curvature = out.max_curvature.max(curvature);
            if curvature < 0.0 {
                out.negative_curvatures += 1;
            }
        }
        let thresholds = prior.thresholds();
        let evaluate = thresholds.is_some() || k % every == 0 || k == settings.max_iterations;
        let penalty = if thresholds.is_some() || !evaluate {
            None
        } else {
            Some(prior.value(&x))
        };
        let thresholds = prior.thresholds();
        let (misfit, pen, gap, kkt) = certificate(problem, &x, &g_x, thresholds, penalty);
        let (mut change, mut norm) = (0.0, 0.0);
        for (a, b) in x.iter().zip(&x_prev) {
            change += (a - b) * (a - b);
            norm += a * a;
        }
        let relative_step = change.sqrt() / norm.sqrt().max(1e-300);
        let record = Record {
            iteration: k,
            objective: misfit + pen,
            misfit,
            penalty: pen,
            gap,
            kkt,
            nonzero: x.par_iter().filter(|v| **v != 0.0).count(),
            flux: x.par_iter().sum(),
            curvature,
            relative_step,
            restarted,
        };
        observer(&record, &x);
        if record.objective.is_finite() {
            if record.objective > last_objective {
                out.objective_rises += 1;
                out.largest_rise = out.largest_rise.max(record.objective - last_objective);
            }
            last_objective = record.objective;
        }
        out.last = record;
        out.iterations = k;
        let converged = settings.gap_tolerance.is_some_and(|tol| gap <= tol)
            || settings.kkt_tolerance.is_some_and(|tol| kkt <= tol)
            || (k > 0
                && settings
                    .step_tolerance
                    .is_some_and(|tol| relative_step <= tol));
        if converged || k == settings.max_iterations {
            out.stop = if converged { "converged" } else { "iterations" }.into();
            out.gx = g_x;
            out.x = x;
            return Ok(out);
        }
        // The forward-backward step from y.
        let step = settings.step;
        z.par_iter_mut()
            .zip(y.par_iter())
            .zip(problem.dirty.par_iter().zip(g_y.par_iter()))
            .for_each(|((o, a), (d, g))| *o = a + step * (d - g));
        prior.prox(&z, step, &mut x_next);
        let mut next_beta = 0.0;
        restarted = false;
        if settings.momentum {
            let inner: f64 = (0..n2)
                .into_par_iter()
                .map(|i| (y[i] - x_next[i]) * (x_next[i] - x[i]))
                .sum();
            if settings.restart && inner > 0.0 {
                t = 1.0;
                restarted = true;
                out.restarts += 1;
            } else {
                let t_next = 0.5 * (1.0 + (1.0 + 4.0 * t * t).sqrt());
                next_beta = (t - 1.0) / t_next;
                t = t_next;
            }
        }
        std::mem::swap(&mut y, &mut y_prev);
        g_y_prev.copy_from_slice(&g_y);
        g_x_prev.copy_from_slice(&g_x);
        std::mem::swap(&mut x_prev, &mut x);
        std::mem::swap(&mut x, &mut x_next);
        y.par_iter_mut()
            .zip(x.par_iter().zip(x_prev.par_iter()))
            .for_each(|(o, (a, b))| *o = a + next_beta * (a - b));
        beta = next_beta;
    }
    unreachable!("the loop returns at max_iterations")
}

/// One outer cycle of [`defect_correction`], on the exact backend.
#[derive(Clone, Copy, Debug, Default)]
pub struct OuterRecord {
    pub outer: usize,
    pub objective: f64,
    pub misfit: f64,
    pub gap: f64,
    pub kkt: f64,
    pub inner_iterations: usize,
    /// `‖(G − G̃) x‖_∞` at the start of the cycle.
    pub defect_sup: f64,
}

/// Conjugate gradients on the support of `x` for the quadratic
/// `½⟨x, G x⟩ − ⟨d − λ, x⟩`: the subspace step of FPC_AS (Wen, Yin, Goldfarb and
/// Zhang 2010). Pixels may go negative during CG; at the end they are clipped,
/// `G x` is recomputed (one more apply) and the step is kept only if the objective
/// fell. Costs one apply per CG iteration. Returns the applies and the number of
/// directions with `⟨p, G p⟩ ≤ 0`, on which it stops: negative curvature.
pub fn active_set_cg<M: Measurement + ?Sized, P: Prior + ?Sized>(
    op: &M,
    problem: &Problem,
    prior: &P,
    x: &mut Vec<f64>,
    gx: &mut Vec<f64>,
    iterations: usize,
    tolerance: f64,
) -> Result<(usize, usize), String> {
    let Some(t) = prior.thresholds() else {
        return Ok((0, 0));
    };
    let n2 = x.len();
    let (q_start, pen_start, _, _) = certificate(problem, x, gx, Some(t), None);
    let start = (x.clone(), gx.clone());
    let active: Vec<bool> = x.par_iter().map(|v| *v > 0.0).collect();
    let mut r: Vec<f64> = (0..n2)
        .into_par_iter()
        .map(|i| {
            if active[i] {
                problem.dirty[i] - gx[i] - t.at(i)
            } else {
                0.0
            }
        })
        .collect();
    let mut p = r.clone();
    let mut rr = dot(&r, &r);
    let mut used = 0;
    let mut negative = 0;
    for _ in 0..iterations {
        let sup = r.par_iter().map(|v| v.abs()).reduce(|| 0.0, f64::max);
        if sup <= tolerance || rr == 0.0 {
            break;
        }
        let gp = op.gram_apply(&p)?;
        used += 1;
        let pgp = dot(&p, &gp);
        if pgp <= 0.0 {
            negative += 1;
            break;
        }
        let alpha = rr / pgp;
        x.par_iter_mut()
            .zip(p.par_iter())
            .for_each(|(a, b)| *a += alpha * *b);
        gx.par_iter_mut()
            .zip(gp.par_iter())
            .for_each(|(a, b)| *a += alpha * *b);
        r.par_iter_mut()
            .zip(gp.par_iter().zip(active.par_iter()))
            .for_each(|(a, (b, on))| {
                if *on {
                    *a -= alpha * *b;
                }
            });
        let next = dot(&r, &r);
        let beta = next / rr;
        rr = next;
        p.par_iter_mut()
            .zip(r.par_iter())
            .for_each(|(a, b)| *a = *b + beta * *a);
    }
    if x.par_iter().any(|v| *v < 0.0) {
        x.par_iter_mut().for_each(|v| *v = v.max(0.0));
        *gx = op.gram_apply(x)?;
        used += 1;
    }
    let (q_end, pen_end, _, _) = certificate(problem, x, gx, Some(t), None);
    if q_end + pen_end > q_start + pen_start {
        *x = start.0;
        *gx = start.1;
    }
    Ok((used, negative))
}

/// Settings of [`solve_active_set`].
#[derive(Clone, Copy, Debug)]
pub struct ActiveSet {
    /// Forward-backward iterations between CG phases: they find the support.
    pub fista_iterations: usize,
    pub cg_iterations: usize,
    /// Rounds at most.
    pub rounds: usize,
    /// Stop at this optimality residual.
    pub kkt: f64,
}

/// What [`solve_active_set`] did.
#[derive(Clone, Debug, Default)]
pub struct ActiveOutcome {
    pub x: Vec<f64>,
    pub gx: Vec<f64>,
    pub last: Record,
    pub rounds: usize,
    pub fista_applies: usize,
    pub cg_applies: usize,
    pub negative_curvatures: usize,
    pub converged: bool,
}

/// Alternate short FISTA runs and CG on the support, to an optimality residual.
pub fn solve_active_set<M: Measurement + ?Sized, P: Prior + ?Sized>(
    op: &M,
    problem: &Problem,
    prior: &mut P,
    settings: &Settings,
    active: &ActiveSet,
    x0: Vec<f64>,
    observer: &mut dyn FnMut(&Record, &[f64]),
) -> Result<ActiveOutcome, String> {
    let mut out = ActiveOutcome::default();
    let mut x = x0;
    let inner = Settings {
        max_iterations: active.fista_iterations,
        kkt_tolerance: Some(active.kkt),
        gap_tolerance: None,
        step_tolerance: None,
        ..settings.clone()
    };
    for round in 0..active.rounds {
        let solved = solve(op, problem, prior, &inner, x, observer)?;
        out.fista_applies += solved.iterations + 1;
        out.negative_curvatures += solved.negative_curvatures;
        out.last = solved.last;
        out.rounds = round + 1;
        x = solved.x;
        let mut gx = solved.gx;
        if solved.last.kkt <= active.kkt {
            out.converged = true;
            out.x = x;
            out.gx = gx;
            return Ok(out);
        }
        let (used, negative) = active_set_cg(
            op,
            problem,
            prior,
            &mut x,
            &mut gx,
            active.cg_iterations,
            0.25 * active.kkt,
        )?;
        out.cg_applies += used;
        out.negative_curvatures += negative;
    }
    // The last CG phase has not been certified: one apply does it.
    let g = op.gram_apply(&x)?;
    out.fista_applies += 1;
    let (misfit, pen, gap, kkt) = certificate(problem, &x, &g, prior.thresholds(), None);
    out.last.misfit = misfit;
    out.last.penalty = pen;
    out.last.objective = misfit + pen;
    out.last.gap = gap;
    out.last.kkt = kkt;
    out.last.nonzero = x.par_iter().filter(|v| **v != 0.0).count();
    out.last.flux = x.par_iter().sum();
    out.converged = kkt <= active.kkt;
    out.x = x;
    out.gx = g;
    Ok(out)
}

/// Settings of [`solve_admm`].
#[derive(Clone, Copy, Debug)]
pub struct Admm {
    /// The penalty `ρ` of `x = z`.
    pub rho: f64,
    /// Over-relaxation, in `[1, 2)`.
    pub relaxation: f64,
    /// Preconditioned CG iterations per x-update, warm-started.
    pub cg_iterations: usize,
    pub max_outer: usize,
    /// Apply `G` at `z` for the certificate every this many outer iterations.
    pub check_every: usize,
    /// Stop at this optimality residual of `z`.
    pub kkt: f64,
}

/// ADMM on `x = z`: `x` solves `(G + ρ) x = d + ρ (z − u)` by preconditioned CG,
/// `z` is the proximal point of the prior at `x + u` with step `1/ρ`. The
/// conditioning of the data term goes into CG and its preconditioner, as in the
/// Newton-type major cycle of pfb-imaging (Bester et al. 2024), rather than into
/// the step of the proximal iteration. The returned model is `z`.
pub fn solve_admm<M, F, P>(
    op: &M,
    filter: &F,
    problem: &Problem,
    prior: &mut P,
    settings: &Admm,
    z0: Vec<f64>,
    observer: &mut dyn FnMut(&Record, &[f64]),
) -> Result<ActiveOutcome, String>
where
    M: Measurement + ?Sized,
    F: Measurement + ?Sized,
    P: Prior + ?Sized,
{
    let n2 = z0.len();
    let rho = settings.rho;
    let mut z = z0;
    let mut x = z.clone();
    let mut u = vec![0.0; n2];
    let mut out = ActiveOutcome::default();
    let mut gx = if x.par_iter().any(|v| *v != 0.0) {
        out.cg_applies += 1;
        op.gram_apply(&x)?
    } else {
        vec![0.0; n2]
    };
    let mut z_next = vec![0.0; n2];
    let mut v = vec![0.0; n2];
    for k in 0..=settings.max_outer {
        // Certificate of z.
        if k % settings.check_every.max(1) == 0 || k == settings.max_outer {
            let gz = op.gram_apply(&z)?;
            out.fista_applies += 1;
            let (misfit, pen, gap, kkt) = certificate(problem, &z, &gz, prior.thresholds(), None);
            let record = Record {
                iteration: k,
                objective: misfit + pen,
                misfit,
                penalty: pen,
                gap,
                kkt,
                nonzero: z.par_iter().filter(|v| **v != 0.0).count(),
                flux: z.par_iter().sum(),
                curvature: f64::NAN,
                relative_step: f64::NAN,
                restarted: false,
            };
            observer(&record, &z);
            out.last = record;
            out.rounds = k;
            if kkt <= settings.kkt || k == settings.max_outer {
                out.converged = kkt <= settings.kkt;
                out.gx = gz;
                out.x = z;
                return Ok(out);
            }
        }
        // x-update.
        let b: Vec<f64> = (0..n2)
            .into_par_iter()
            .map(|i| problem.dirty[i] + rho * (z[i] - u[i]))
            .collect();
        let mut r: Vec<f64> = (0..n2)
            .into_par_iter()
            .map(|i| b[i] - gx[i] - rho * x[i])
            .collect();
        let mut s = filter.gram_apply(&r)?;
        let mut p = s.clone();
        let mut rs = dot(&r, &s);
        for _ in 0..settings.cg_iterations {
            let gp = op.gram_apply(&p)?;
            out.cg_applies += 1;
            let pgp = dot(&p, &gp);
            if pgp <= 0.0 {
                out.negative_curvatures += 1;
            }
            let pap = pgp + rho * dot(&p, &p);
            if pap <= 0.0 || rs <= 0.0 {
                break;
            }
            let alpha = rs / pap;
            x.par_iter_mut()
                .zip(p.par_iter())
                .for_each(|(a, b)| *a += alpha * *b);
            gx.par_iter_mut()
                .zip(gp.par_iter())
                .for_each(|(a, b)| *a += alpha * *b);
            r.par_iter_mut()
                .zip(gp.par_iter().zip(p.par_iter()))
                .for_each(|(a, (g, q))| *a -= alpha * (*g + rho * *q));
            s = filter.gram_apply(&r)?;
            let next = dot(&r, &s);
            let beta = next / rs;
            rs = next;
            p.par_iter_mut()
                .zip(s.par_iter())
                .for_each(|(a, b)| *a = *b + beta * *a);
        }
        // z-update and the multiplier, over-relaxed.
        let relax = settings.relaxation;
        v.par_iter_mut().enumerate().for_each(|(i, o)| {
            *o = relax * x[i] + (1.0 - relax) * z[i] + u[i];
        });
        prior.prox(&v, 1.0 / rho, &mut z_next);
        u.par_iter_mut().enumerate().for_each(|(i, o)| {
            *o = v[i] - z_next[i];
        });
        std::mem::swap(&mut z, &mut z_next);
    }
    unreachable!("the loop returns at max_outer")
}

/// The outer loop of [`defect_correction`].
#[derive(Clone, Copy, Debug)]
pub struct OuterSchedule {
    pub cycles: usize,
    /// Stop when the exact optimality residual at the target `lambda` is here.
    pub kkt: f64,
    /// The target regularisation.
    pub lambda: f64,
    /// A cycle solves at `max(lambda, gamma · peak residual)`; 0 keeps `lambda`.
    pub gamma: f64,
}

/// Solve on a cheap operator with its error at `x_j` moved into the data:
/// `min ½⟨x, G̃ x⟩ − ⟨d − (G − G̃) x_j, x⟩ + R(x)`. At a fixed point `G̃`'s error
/// cancels, so the limit is the exact problem's solution, whatever `G̃` is, if
/// the iteration converges. Each cycle costs one apply of each operator more
/// than the inner solve. With the no-w PSF as `G̃` this is a major cycle.
#[allow(clippy::too_many_arguments)]
pub fn defect_correction<E, C, P>(
    exact: &E,
    cheap: &C,
    problem: &Problem,
    prior: &mut P,
    inner: &Settings,
    schedule: &OuterSchedule,
    x0: Vec<f64>,
    observer: &mut dyn FnMut(&OuterRecord, &[f64]),
) -> Result<Outcome, String>
where
    E: Measurement + ?Sized,
    C: Measurement + ?Sized,
    P: Prior + ?Sized,
{
    let mut x = x0;
    let mut out = Outcome::default();
    let mut inner_iterations = 0;
    let cycles = schedule.cycles;
    let outer_kkt = schedule.kkt;
    for j in 0..=cycles {
        let g = exact.gram_apply(&x)?;
        prior.set_lambda(schedule.lambda);
        let penalty = if prior.thresholds().is_none() {
            Some(prior.value(&x))
        } else {
            None
        };
        let thresholds = prior.thresholds();
        let (misfit, pen, gap, kkt) = certificate(problem, &x, &g, thresholds, penalty);
        let g_cheap = cheap.gram_apply(&x)?;
        let mut defect_sup = 0.0_f64;
        let corrected: Vec<f64> = (0..x.len())
            .map(|i| {
                let c = g[i] - g_cheap[i];
                defect_sup = defect_sup.max(c.abs());
                problem.dirty[i] - c
            })
            .collect();
        observer(
            &OuterRecord {
                outer: j,
                objective: misfit + pen,
                misfit,
                gap,
                kkt,
                inner_iterations,
                defect_sup,
            },
            &x,
        );
        out.last.objective = misfit + pen;
        out.last.misfit = misfit;
        out.last.gap = gap;
        out.last.kkt = kkt;
        if kkt <= outer_kkt || j == cycles {
            out.stop = if kkt <= outer_kkt {
                "converged"
            } else {
                "cycles"
            }
            .into();
            out.gx = g;
            out.x = x;
            out.iterations = inner_iterations;
            return Ok(out);
        }
        // Like a major cycle: this cycle goes down to a fraction of the peak.
        let signed = thresholds.is_some_and(|t| t.signed);
        let peak = (0..x.len())
            .into_par_iter()
            .map(|i| {
                let r = problem.dirty[i] - g[i];
                if signed { r.abs() } else { r }
            })
            .reduce(|| 0.0, f64::max);
        prior.set_lambda(schedule.lambda.max(schedule.gamma * peak));
        let shifted = Problem {
            dirty: &corrected,
            q0: problem.q0,
        };
        // The inner objective is not of least-squares form, so its gap has no
        // meaning: it stops on its optimality residual or on the iterations.
        let settings = Settings {
            gap_tolerance: None,
            ..inner.clone()
        };
        let solved = solve(cheap, &shifted, prior, &settings, x, &mut |_, _| {})?;
        inner_iterations += solved.iterations;
        out.restarts += solved.restarts;
        out.negative_curvatures += solved.negative_curvatures;
        x = solved.x;
    }
    unreachable!("the loop returns at the last cycle")
}

fn seeded(n: usize, seed: u64) -> Vec<f64> {
    let mut state = seed.max(1);
    (0..n)
        .map(|_| {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / (1u64 << 53) as f64 - 0.5
        })
        .collect()
}

/// The largest eigenvalue by power iteration from a seeded start: the
/// estimate and the applies used. Stops at a relative change below `tolerance`.
pub fn power_iteration<M: Measurement + ?Sized>(
    op: &M,
    seed: u64,
    tolerance: f64,
    max_iterations: usize,
) -> Result<(f64, usize), String> {
    let n = op.side();
    let mut v = seeded(n * n, seed);
    let norm = dot(&v, &v).sqrt();
    v.par_iter_mut().for_each(|a| *a /= norm);
    let mut value = 0.0;
    for k in 1..=max_iterations {
        let mut g = op.gram_apply(&v)?;
        let next = dot(&g, &g).sqrt();
        g.par_iter_mut().for_each(|a| *a /= next.max(1e-300));
        v = g;
        if k > 1 && (next - value).abs() <= tolerance * next {
            return Ok((next, k));
        }
        value = next;
    }
    Ok((value, max_iterations))
}

/// Sturm count: eigenvalues of the tridiagonal `(a, b)` below `x`.
fn sturm(a: &[f64], b: &[f64], x: f64) -> usize {
    let mut count = 0;
    let mut q = a[0] - x;
    if q < 0.0 {
        count += 1;
    }
    for i in 1..a.len() {
        let denom = if q == 0.0 { 1e-300 } else { q };
        q = a[i] - x - b[i - 1] * b[i - 1] / denom;
        if q < 0.0 {
            count += 1;
        }
    }
    count
}

/// The smallest and largest Ritz values after `steps` Lanczos steps. A negative
/// smallest value proves negative curvature; a positive one proves nothing.
/// No reorthogonalisation: ghosts copy eigenvalues but do not invent extremes.
pub fn lanczos_extremes<M: Measurement + ?Sized>(
    op: &M,
    seed: u64,
    steps: usize,
) -> Result<(f64, f64), String> {
    let n = op.side();
    let mut v = seeded(n * n, seed);
    let norm = dot(&v, &v).sqrt();
    v.par_iter_mut().for_each(|a| *a /= norm);
    let mut v_prev = vec![0.0; n * n];
    let (mut alpha, mut beta) = (Vec::new(), Vec::new());
    let mut b = 0.0;
    for _ in 0..steps {
        let mut w = op.gram_apply(&v)?;
        let a = dot(&w, &v);
        alpha.push(a);
        w.par_iter_mut()
            .zip(v.par_iter().zip(v_prev.par_iter()))
            .for_each(|(o, (p, q))| *o -= a * p + b * q);
        b = dot(&w, &w).sqrt();
        beta.push(b);
        if b < 1e-14 {
            break;
        }
        w.par_iter_mut().for_each(|o| *o /= b);
        v_prev = v;
        v = w;
    }
    let m = alpha.len();
    let bound = alpha
        .iter()
        .enumerate()
        .map(|(i, a)| {
            a.abs()
                + beta.get(i).copied().unwrap_or(0.0).abs()
                + if i > 0 { beta[i - 1].abs() } else { 0.0 }
        })
        .fold(0.0, f64::max);
    let off = &beta[..m - 1];
    let (mut lo, mut hi) = (-bound - 1.0, bound + 1.0);
    for _ in 0..200 {
        let mid = 0.5 * (lo + hi);
        if sturm(&alpha, off, mid) >= 1 {
            hi = mid;
        } else {
            lo = mid;
        }
    }
    let smallest = 0.5 * (lo + hi);
    let (mut lo, mut hi) = (-bound - 1.0, bound + 1.0);
    for _ in 0..200 {
        let mid = 0.5 * (lo + hi);
        if sturm(&alpha, off, mid) >= m {
            hi = mid;
        } else {
            lo = mid;
        }
    }
    Ok((smallest, 0.5 * (lo + hi)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::clean_certified::{Complex, WgridMeasurement};
    use crate::gridder_gram::{GramMeasurement, GramOperator, WExpansion};
    use crate::wgridder::{C_LIGHT, Options};

    /// `G = Aᵀ A` for a dense `A`, on an `n × n` image.
    struct Dense {
        n: usize,
        a: Vec<f64>,
        rows: usize,
        scale: f64,
    }

    impl Dense {
        fn new(n: usize, rows: usize, seed: u64) -> Dense {
            Dense {
                n,
                a: seeded(rows * n * n, seed),
                rows,
                scale: 1.0,
            }
        }
        fn forward(&self, x: &[f64]) -> Vec<f64> {
            self.a
                .chunks(self.n * self.n)
                .map(|r| r.iter().zip(x).map(|(p, q)| p * q).sum())
                .collect()
        }
        fn back(&self, v: &[f64]) -> Vec<f64> {
            let mut out = vec![0.0; self.n * self.n];
            for (r, c) in self.a.chunks(self.n * self.n).zip(v) {
                for (o, p) in out.iter_mut().zip(r) {
                    *o += p * c;
                }
            }
            out
        }
    }

    impl Measurement for Dense {
        fn side(&self) -> usize {
            self.n
        }
        fn residual(&self, _: &[f64]) -> Result<(Vec<f64>, f64), String> {
            Err("not used".into())
        }
        fn gram_apply(&self, x: &[f64]) -> Result<Vec<f64>, String> {
            let g = self.back(&self.forward(x));
            Ok(g.iter().map(|v| v * self.scale).collect())
        }
    }

    fn dense_problem(n: usize, rows: usize) -> (Dense, Vec<f64>, Vec<f64>, f64) {
        let op = Dense::new(n, rows, 21);
        let mut truth = vec![0.0; n * n];
        truth[3] = 2.0;
        truth[n * n / 2 + 1] = 1.0;
        truth[n * n - 2] = 0.5;
        let noise = seeded(op.rows, 99);
        let y: Vec<f64> = op
            .forward(&truth)
            .iter()
            .zip(&noise)
            .map(|(a, b)| a + 0.02 * b)
            .collect();
        let d = op.back(&y);
        let q0 = 0.5 * y.iter().map(|v| v * v).sum::<f64>();
        (op, truth, d, q0)
    }

    #[test]
    fn the_proximal_operator_is_the_shifted_positive_part() {
        let mut p = L1Prior::new(2.0, 1.0);
        let mut out = [0.0; 3];
        p.prox(&[3.0, 1.0, -1.0], 0.5, &mut out);
        assert_eq!(out, [2.0, 0.0, 0.0]);
        assert_eq!(p.value(&[1.0, 0.0, 2.0]), 6.0);
        p.reweight(&[1.0, 0.0, 3.0]);
        p.prox(&[3.0, 1.0, -1.0], 0.5, &mut out);
        assert_eq!(out, [2.5, 0.0, 0.0]);
    }

    #[test]
    fn fista_closes_the_gap_and_the_linear_trick_is_exact() {
        let (op, _, d, q0) = dense_problem(6, 20);
        let (lmax, _) = power_iteration(&op, 3, 1e-8, 2000).unwrap();
        let problem = Problem { dirty: &d, q0 };
        let mut prior = L1Prior::new(0.02, 1.0);
        let settings = Settings {
            step: 1.0 / (1.01 * lmax),
            max_iterations: 20000,
            gap_tolerance: Some(1e-11),
            ..Settings::default()
        };
        let mut worst = 0.0_f64;
        let out = solve(
            &op,
            &problem,
            &mut prior,
            &settings,
            vec![0.0; 36],
            &mut |r, x| {
                let g = op.gram_apply(x).unwrap();
                let want = q0 - dot(&d, x) + 0.5 * dot(x, &g);
                worst = worst.max((want - r.misfit).abs());
            },
        )
        .unwrap();
        assert_eq!(out.stop, "converged");
        assert!(worst < 1e-10, "linearity {worst}");
        assert!(out.last.kkt < 1e-3, "kkt {}", out.last.kkt);
        assert!(
            out.last.gap >= -1e-12,
            "a gap cannot be negative: {}",
            out.last.gap
        );
        assert!(out.min_curvature >= -1e-10);
        assert!(out.max_curvature <= lmax * (1.0 + 1e-6));
        // Forward-backward descends and reaches the same objective.
        let settings = Settings {
            momentum: false,
            max_iterations: 200000,
            gap_tolerance: Some(1e-11),
            ..settings
        };
        let fb = solve(
            &op,
            &problem,
            &mut prior,
            &settings,
            vec![0.0; 36],
            &mut |_, _| {},
        )
        .unwrap();
        assert!(fb.largest_rise < 1e-12, "{}", fb.largest_rise);
        assert!((fb.last.objective - out.last.objective).abs() < 1e-9);
        assert!(fb.iterations > out.iterations);
    }

    #[test]
    fn the_active_set_solver_reaches_the_fista_solution_in_fewer_applies() {
        let (op, _, d, q0) = dense_problem(6, 20);
        let (lmax, _) = power_iteration(&op, 3, 1e-8, 2000).unwrap();
        let problem = Problem { dirty: &d, q0 };
        let mut prior = L1Prior::new(0.02, 1.0);
        let settings = Settings {
            step: 1.0 / (1.01 * lmax),
            max_iterations: 20000,
            kkt_tolerance: Some(1e-8),
            ..Settings::default()
        };
        let fista = solve(
            &op,
            &problem,
            &mut prior,
            &settings,
            vec![0.0; 36],
            &mut |_, _| {},
        )
        .unwrap();
        let active = ActiveSet {
            fista_iterations: 5,
            cg_iterations: 10,
            rounds: 200,
            kkt: 1e-8,
        };
        let a = solve_active_set(
            &op,
            &problem,
            &mut prior,
            &settings,
            &active,
            vec![0.0; 36],
            &mut |_, _| {},
        )
        .unwrap();
        assert!(a.converged);
        assert!((a.last.objective - fista.last.objective).abs() < 1e-9);
        assert!(a.fista_applies + a.cg_applies < fista.iterations);
        assert_eq!(a.negative_curvatures, 0);
        let g = op.gram_apply(&a.x).unwrap();
        let err = g
            .iter()
            .zip(&a.gx)
            .map(|(p, q)| (p - q).abs())
            .fold(0.0, f64::max);
        assert!(err < 1e-9, "{err}");
    }

    #[test]
    fn admm_reaches_the_fista_solution() {
        struct Identity;
        impl Measurement for Identity {
            fn side(&self) -> usize {
                6
            }
            fn residual(&self, _: &[f64]) -> Result<(Vec<f64>, f64), String> {
                Err("not used".into())
            }
            fn gram_apply(&self, x: &[f64]) -> Result<Vec<f64>, String> {
                Ok(x.to_vec())
            }
        }
        let (op, _, d, q0) = dense_problem(6, 20);
        let (lmax, _) = power_iteration(&op, 3, 1e-8, 2000).unwrap();
        let problem = Problem { dirty: &d, q0 };
        let mut prior = L1Prior::new(0.02, 1.0);
        let settings = Settings {
            step: 1.0 / (1.01 * lmax),
            max_iterations: 20000,
            kkt_tolerance: Some(1e-8),
            ..Settings::default()
        };
        let fista = solve(
            &op,
            &problem,
            &mut prior,
            &settings,
            vec![0.0; 36],
            &mut |_, _| {},
        )
        .unwrap();
        let plan = Admm {
            rho: 1.0,
            relaxation: 1.5,
            cg_iterations: 5,
            max_outer: 5000,
            check_every: 1,
            kkt: 1e-8,
        };
        let a = solve_admm(
            &op,
            &Identity,
            &problem,
            &mut prior,
            &plan,
            vec![0.0; 36],
            &mut |_, _| {},
        )
        .unwrap();
        assert!(a.converged);
        assert!((a.last.objective - fista.last.objective).abs() < 1e-8);
        assert!(a.x.iter().all(|v| *v >= 0.0));
    }

    #[test]
    fn signed_l1_closes_its_gap_below_the_nonnegative_objective() {
        let (op, _, d, q0) = dense_problem(6, 20);
        let (lmax, _) = power_iteration(&op, 3, 1e-8, 2000).unwrap();
        let problem = Problem { dirty: &d, q0 };
        let settings = Settings {
            step: 1.0 / (1.01 * lmax),
            max_iterations: 50000,
            gap_tolerance: Some(1e-11),
            ..Settings::default()
        };
        let mut signed = L1Prior::signed(0.02, 1.0);
        let a = solve(
            &op,
            &problem,
            &mut signed,
            &settings,
            vec![0.0; 36],
            &mut |_, _| {},
        )
        .unwrap();
        assert_eq!(a.stop, "converged");
        assert!(a.last.kkt < 1e-3);
        let mut nonneg = L1Prior::new(0.02, 1.0);
        let b = solve(
            &op,
            &problem,
            &mut nonneg,
            &settings,
            vec![0.0; 36],
            &mut |_, _| {},
        )
        .unwrap();
        assert!(a.last.objective <= b.last.objective + 1e-10);
        assert!(b.x.iter().all(|v| *v >= 0.0));
    }

    #[test]
    fn power_and_lanczos_find_a_known_spectrum() {
        struct Diag(Vec<f64>);
        impl Measurement for Diag {
            fn side(&self) -> usize {
                4
            }
            fn residual(&self, _: &[f64]) -> Result<(Vec<f64>, f64), String> {
                Err("not used".into())
            }
            fn gram_apply(&self, x: &[f64]) -> Result<Vec<f64>, String> {
                Ok(self.0.iter().zip(x).map(|(a, b)| a * b).collect())
            }
        }
        let mut d: Vec<f64> = (1..=16).map(|i| i as f64 / 16.0).collect();
        d[0] = -0.25;
        let op = Diag(d);
        let (l, _) = power_iteration(&op, 5, 1e-10, 5000).unwrap();
        assert!((l - 1.0).abs() < 1e-6, "{l}");
        let (lo, hi) = lanczos_extremes(&op, 5, 16).unwrap();
        assert!((lo + 0.25).abs() < 1e-6, "{lo}");
        assert!((hi - 1.0).abs() < 1e-6, "{hi}");
    }

    #[test]
    fn defect_correction_reaches_the_exact_problem_from_a_wrong_operator() {
        let (op, _, d, q0) = dense_problem(6, 20);
        let (lmax, _) = power_iteration(&op, 3, 1e-8, 2000).unwrap();
        // Off by 20 %: alone it would give a clearly different solution.
        let wrong = Dense {
            scale: 1.2,
            ..Dense::new(6, 20, 21)
        };
        let problem = Problem { dirty: &d, q0 };
        let mut prior = L1Prior::new(0.02, 1.0);
        let inner = Settings {
            step: 1.0 / (1.3 * lmax),
            max_iterations: 400,
            kkt_tolerance: Some(1e-7),
            ..Settings::default()
        };
        let mut cycles = 0;
        let out = defect_correction(
            &op,
            &wrong,
            &problem,
            &mut prior,
            &inner,
            &OuterSchedule {
                cycles: 60,
                kkt: 1e-6,
                lambda: 0.02,
                gamma: 0.0,
            },
            vec![0.0; 36],
            &mut |_, _| cycles += 1,
        )
        .unwrap();
        assert_eq!(out.stop, "converged");
        let direct = solve(
            &op,
            &problem,
            &mut prior,
            &Settings {
                step: 1.0 / (1.01 * lmax),
                max_iterations: 20000,
                gap_tolerance: Some(1e-12),
                ..Settings::default()
            },
            vec![0.0; 36],
            &mut |_, _| {},
        )
        .unwrap();
        assert!((out.last.objective - direct.last.objective).abs() < 1e-7);
        let wrong_alone = solve(
            &wrong,
            &problem,
            &mut prior,
            &Settings {
                step: 1.0 / (1.3 * lmax),
                max_iterations: 20000,
                kkt_tolerance: Some(1e-7),
                ..Settings::default()
            },
            vec![0.0; 36],
            &mut |_, _| {},
        )
        .unwrap();
        let diff: f64 = wrong_alone
            .x
            .iter()
            .zip(&direct.x)
            .map(|(a, b)| (a - b).abs())
            .fold(0.0, f64::max);
        assert!(
            diff > 1e-2,
            "the wrong operator should move the solution: {diff}"
        );
        assert!(cycles > 1);
    }

    struct Small {
        exact: WgridMeasurement,
        opts: Options,
    }

    fn small(n: usize, nrow: usize) -> (Small, Vec<f64>) {
        let mut state = 77u64;
        let mut next = || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / (1u64 << 53) as f64 - 0.5
        };
        let freq = vec![C_LIGHT, 1.05 * C_LIGHT];
        let cell = 8e-3;
        let umax = 0.45 / cell;
        let uvw: Vec<f64> = (0..3 * nrow)
            .map(|i| next() * 2.0 * if i % 3 == 2 { 400.0 } else { umax / 1.05 })
            .collect();
        let wgt: Vec<f64> = (0..2 * nrow).map(|_| 0.2 + next().abs()).collect();
        let opts = Options {
            flip_v: true,
            flip_w: true,
            ..Options::default()
        };
        let vis = vec![Complex::new(0.0, 0.0); 2 * nrow];
        let mut exact = WgridMeasurement::new(uvw, freq, vis, wgt, n, cell, 1e-9, opts).unwrap();
        let mut truth = vec![0.0; n * n];
        truth[3 * n + 5] = 1.0;
        truth[20 * n + 11] = 0.5;
        let mut vis = exact.predict(&truth).unwrap();
        for v in &mut vis {
            *v += Complex::new(0.02 * next(), 0.02 * next());
        }
        exact.vis = vis;
        let opts = exact.opts;
        (Small { exact, opts }, truth)
    }

    #[test]
    fn both_backends_reach_one_solution_within_the_operator_bound() {
        let n = 32;
        let (s, _) = small(n, 800);
        let (d, q0) = s.exact.residual(&vec![0.0; n * n]).unwrap();
        let ex = WExpansion::new(10, 1.0, 1e-13).unwrap();
        let op = GramOperator::<f64>::new(
            &s.opts,
            &s.exact.uvw,
            &s.exact.freq,
            &s.exact.wgt,
            &ex,
            1e-9,
        )
        .unwrap();
        let eta = ex.sup_error + ex.lebesgue * 1e-9;
        let gram = GramMeasurement::new(op, d.clone(), q0);
        let (lmax, _) = power_iteration(&gram, 3, 1e-8, 500).unwrap();
        let problem = Problem { dirty: &d, q0 };
        let settings = Settings {
            step: 1.0 / (1.01 * lmax),
            max_iterations: 5000,
            kkt_tolerance: Some(1e-9),
            ..Settings::default()
        };
        let mut prior = L1Prior::new(1e-3, 1.0);
        let a = solve(
            &s.exact,
            &problem,
            &mut prior,
            &settings,
            vec![0.0; n * n],
            &mut |_, _| {},
        )
        .unwrap();
        let b = solve(
            &gram,
            &problem,
            &mut prior,
            &settings,
            vec![0.0; n * n],
            &mut |_, _| {},
        )
        .unwrap();
        assert_eq!(a.stop, "converged");
        assert_eq!(b.stop, "converged");
        let l1 = |x: &[f64]| x.iter().map(|v| v.abs()).sum::<f64>();
        // On the exact objective, b is suboptimal by at most
        // η (‖a‖₁² + ‖b‖₁²) / 2 from gram_quadratic_bound.
        let g_b = s.exact.gram_apply(&b.x).unwrap();
        let (q_b, pen_b, _, kkt_b) = certificate(&problem, &b.x, &g_b, prior.thresholds(), None);
        let f_b = q_b + pen_b;
        let sub = f_b - a.last.objective;
        let bound = 0.5 * eta * (l1(&a.x).powi(2) + l1(&b.x).powi(2));
        assert!(sub <= bound, "{sub} above {bound}");
        // And b meets the exact optimality conditions within η ‖b‖₁.
        assert!(kkt_b <= 1e-9 + eta * l1(&b.x), "{kkt_b}");
    }

    #[test]
    fn the_no_w_operator_is_the_toeplitz_psf() {
        let n = 32;
        let (s, _) = small(n, 500);
        let op =
            GramOperator::<f64>::no_w(&s.opts, &s.exact.uvw, &s.exact.freq, &s.exact.wgt, 1e-10)
                .unwrap();
        let mut m = vec![0.0; n * n];
        m[0] = 1.0;
        m[n * n - 1] = -0.5;
        m[n * n / 2 + 7] = 0.25;
        let got = op.apply(&m).unwrap();
        let exact_no_w = WgridMeasurement {
            opts: Options {
                do_wgridding: false,
                epsilon: 1e-11,
                ..s.opts
            },
            uvw: s.exact.uvw.clone(),
            freq: s.exact.freq.clone(),
            vis: s.exact.vis.clone(),
            wgt: s.exact.wgt.clone(),
            weight_sum: 1.0,
        };
        let want = exact_no_w.gram_apply(&m).unwrap();
        let err = got
            .iter()
            .zip(&want)
            .map(|(a, b)| (a - b).abs())
            .fold(0.0, f64::max);
        assert!(err < 1e-8, "{err}");
        assert_eq!(op.planes(), 1);
    }
}
