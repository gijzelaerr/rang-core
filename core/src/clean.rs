//! Högbom CLEAN as greedy coordinate descent on the sampling-weighted
//! least-squares misfit: the kernels behind `research/clean-theory.md`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The formalism. The data live in the real inner-product space of weighted
//! visibilities, `⟨x, y⟩ = Σ_k w_k (Re x_k Re y_k + Im x_k Im y_k)`. Every
//! pixel `p` has an atom `a_p`, the visibilities of a unit point source at
//! that pixel, and `‖a_p‖² = Σ_k w_k = 1` once the weights are normalised. For
//! a pixel model `m` the residual is `e(m) = V − Σ_p m_p a_p`, the misfit is
//! `Q(m) = ½‖e(m)‖²`, the residual dirty image is its negative gradient,
//! `r_p(m) = ⟨e(m), a_p⟩`, and the point-spread function is the Gram matrix
//! `B_pq = ⟨a_p, a_q⟩ = b(x_p − x_q)`. One CLEAN step at `p` with gain `γ`
//! replaces `m_p` by `m_p + γ r_p` and lowers `Q` by exactly
//! `γ(2−γ)/2 · r_p²` (Schwarz 1978, eq. 6 of his 1984 summary), as long as the
//! beam that is subtracted from the residual image is this Gram matrix. The
//! positivity condition of the classical statement is then automatic; it
//! fails only when the subtracted beam is not the Gram of the measurement
//! (a truncated patch, a beam on a smaller grid, approximate gridding).
//!
//! `research/clean-theory.md` states and proves the theorems and
//! `formal/RangFormal/Clean.lean` checks the core of them in Lean; the
//! example `clean_theory` measures them on MeerKAT sampling.

use rayon::prelude::*;
use std::f64::consts::PI;

/// Weighted `(u, v)` sampling in wavelengths, one entry per visibility. The
/// Hermitian partner of each sample is implicit: a real image only sees
/// `Σ_k w_k cos(2π u_k · Δx)`.
#[derive(Clone, Debug, Default)]
pub struct Sampling {
    pub u: Vec<f64>,
    pub v: Vec<f64>,
    pub w: Vec<f64>,
}

impl Sampling {
    pub fn len(&self) -> usize {
        self.u.len()
    }

    pub fn is_empty(&self) -> bool {
        self.u.is_empty()
    }

    /// Scale the weights to sum to one, so that every atom has unit norm and
    /// the PSF peak is one.
    pub fn normalise(&mut self) {
        let total: f64 = self.w.iter().sum();
        if total > 0.0 {
            for w in &mut self.w {
                *w /= total;
            }
        }
    }
}

/// A square pixel grid: `n` pixels a side and `cell` radians per pixel. Pixel
/// `p = ix + n * iy` sits at direction cosines `((ix − n/2) cell, (iy − n/2) cell)`.
#[derive(Clone, Copy, Debug)]
pub struct Grid {
    pub n: usize,
    pub cell: f64,
}

impl Grid {
    pub fn pixels(&self) -> usize {
        self.n * self.n
    }

    pub fn lm(&self, p: usize) -> (f64, f64) {
        let half = (self.n / 2) as f64;
        let ix = (p % self.n) as f64;
        let iy = (p / self.n) as f64;
        ((ix - half) * self.cell, (iy - half) * self.cell)
    }

    pub fn index(&self, ix: usize, iy: usize) -> usize {
        ix + self.n * iy
    }
}

/// A complex visibility as `(re, im)`.
pub type Vis = (f64, f64);

/// The point-spread function over every offset two pixels of an `n`-grid can
/// have: `(2n−1)²` values of `b(Δ) = Σ_k w_k cos(2π(u_k Δl + v_k Δm))`, so
/// `b(0) = Σ_k w_k`. Holding the full offset range is what makes subtraction
/// exact for components anywhere in the image.
#[derive(Clone, Debug)]
pub struct Psf {
    pub n: usize,
    pub values: Vec<f64>,
}

impl Psf {
    fn width(&self) -> usize {
        2 * self.n - 1
    }

    /// `b(dx, dy)` for `|dx|, |dy| ≤ n − 1`.
    pub fn at(&self, dx: isize, dy: isize) -> f64 {
        let off = (self.n - 1) as isize;
        self.values[(dx + off) as usize + self.width() * (dy + off) as usize]
    }

    /// The peak value `b(0)` (one for normalised weights).
    pub fn peak(&self) -> f64 {
        self.at(0, 0)
    }

    /// The coherence of the atom dictionary: the largest `|b(Δ)| / b(0)` over
    /// nonzero offsets, i.e. the peak absolute sidelobe within the image.
    pub fn coherence(&self) -> f64 {
        let off = (self.n - 1) as isize;
        let mut worst = 0.0_f64;
        for dy in -off..=off {
            for dx in -off..=off {
                if dx != 0 || dy != 0 {
                    worst = worst.max(self.at(dx, dy).abs());
                }
            }
        }
        worst / self.peak()
    }

    /// The largest `|b(Δ)| / b(0)` over offsets outside the `±patch` square:
    /// the part of the beam a truncated subtraction ignores.
    pub fn outside_patch(&self, patch: usize) -> f64 {
        let off = (self.n - 1) as isize;
        let h = patch as isize;
        let mut worst = 0.0_f64;
        for dy in -off..=off {
            for dx in -off..=off {
                if dx.abs() > h || dy.abs() > h {
                    worst = worst.max(self.at(dx, dy).abs());
                }
            }
        }
        worst / self.peak()
    }
}

/// The PSF of `s` on `grid`, by direct summation (parallel over rows).
pub fn psf(s: &Sampling, grid: &Grid) -> Psf {
    let n = grid.n;
    let width = 2 * n - 1;
    let off = (n - 1) as isize;
    let mut values = vec![0.0; width * width];
    values
        .par_chunks_mut(width)
        .enumerate()
        .for_each(|(row, out)| {
            let dy = row as isize - off;
            let dm = dy as f64 * grid.cell;
            for (col, value) in out.iter_mut().enumerate() {
                let dx = col as isize - off;
                let dl = dx as f64 * grid.cell;
                let mut sum = 0.0;
                for k in 0..s.len() {
                    sum += s.w[k] * (2.0 * PI * (s.u[k] * dl + s.v[k] * dm)).cos();
                }
                *value = sum;
            }
        });
    Psf { n, values }
}

/// The visibilities of a unit point source at direction cosines `(l, m)`:
/// `exp(−2πi (u l + v m))`.
pub fn point_vis(s: &Sampling, l: f64, m: f64) -> Vec<Vis> {
    (0..s.len())
        .map(|k| {
            let phase = -2.0 * PI * (s.u[k] * l + s.v[k] * m);
            (phase.cos(), phase.sin())
        })
        .collect()
}

/// Add `c` times the atom of pixel `p` to `vis` in place.
pub fn add_atom(s: &Sampling, grid: &Grid, p: usize, c: f64, vis: &mut [Vis]) {
    let (l, m) = grid.lm(p);
    for (k, v) in vis.iter_mut().enumerate() {
        let phase = -2.0 * PI * (s.u[k] * l + s.v[k] * m);
        v.0 += c * phase.cos();
        v.1 += c * phase.sin();
    }
}

/// The visibilities of a pixel model, summed over its nonzero pixels.
pub fn predict(s: &Sampling, grid: &Grid, model: &[f64]) -> Vec<Vis> {
    let mut vis = vec![(0.0, 0.0); s.len()];
    for (p, &c) in model.iter().enumerate() {
        if c != 0.0 {
            add_atom(s, grid, p, c, &mut vis);
        }
    }
    vis
}

/// The dirty image `d_p = Σ_k w_k Re(V_k exp(+2πi u_k · x_p)) = ⟨V, a_p⟩`:
/// the gradient map of the misfit (parallel over pixels).
pub fn dirty(s: &Sampling, grid: &Grid, vis: &[Vis]) -> Vec<f64> {
    (0..grid.pixels())
        .into_par_iter()
        .map(|p| {
            let (l, m) = grid.lm(p);
            let mut sum = 0.0;
            for (k, v) in vis.iter().enumerate() {
                let phase = 2.0 * PI * (s.u[k] * l + s.v[k] * m);
                sum += s.w[k] * (v.0 * phase.cos() - v.1 * phase.sin());
            }
            sum
        })
        .collect()
}

/// The misfit `Q = ½ Σ_k w_k |V_k − V̂_k|²`.
pub fn misfit(s: &Sampling, vis: &[Vis], model_vis: &[Vis]) -> f64 {
    let mut q = 0.0;
    for k in 0..s.len() {
        let re = vis[k].0 - model_vis[k].0;
        let im = vis[k].1 - model_vis[k].1;
        q += s.w[k] * (re * re + im * im);
    }
    0.5 * q
}

/// `B m`: the model convolved with the full PSF, summed over nonzero pixels.
pub fn convolve(psf: &Psf, model: &[f64]) -> Vec<f64> {
    let mut image = vec![0.0; model.len()];
    for (p, &c) in model.iter().enumerate() {
        if c != 0.0 {
            subtract(&mut image, psf, p, -c, None);
        }
    }
    image
}

/// The least-squares model: `B m = d` solved by conjugate gradients on the
/// PSF Gram matrix, from zero. Returns the model, the iterations used and the
/// final relative residual `‖d − B m‖ / ‖d‖`. Its misfit is `Q_∞`, the part
/// of `Q_0` that no pixel model can remove and that the CLEAN sequence
/// approaches from above.
pub fn least_squares_model(
    psf: &Psf,
    dirty: &[f64],
    iterations: usize,
    tolerance: f64,
) -> (Vec<f64>, usize, f64) {
    conjugate_gradients(|p| Ok(convolve(psf, p)), dirty, iterations, tolerance)
        .expect("convolution cannot fail")
}

/// Conjugate gradients for `B x = rhs` with a symmetric positive
/// semidefinite operator `apply(x) = B x`, from zero: the solver behind
/// [`least_squares_model`] for any measurement operator (the certified
/// driver applies `Aᴴ W A` through the gridder). Returns the solution, the
/// iterations used and `‖rhs − B x‖ / ‖rhs‖`.
pub fn conjugate_gradients<F>(
    mut apply: F,
    rhs: &[f64],
    iterations: usize,
    tolerance: f64,
) -> Result<(Vec<f64>, usize, f64), String>
where
    F: FnMut(&[f64]) -> Result<Vec<f64>, String>,
{
    let dirty = rhs;
    let dot = |x: &[f64], y: &[f64]| x.iter().zip(y).map(|(a, b)| a * b).sum::<f64>();
    let norm_d = dot(dirty, dirty).sqrt();
    let mut x = vec![0.0; dirty.len()];
    let mut r = dirty.to_vec();
    let mut p = r.clone();
    let mut rr = dot(&r, &r);
    let mut used = 0;
    while used < iterations && rr.sqrt() > tolerance * norm_d {
        let ap = apply(&p)?;
        let pap = dot(&p, &ap);
        if pap <= 0.0 {
            break;
        }
        let alpha = rr / pap;
        for ((xi, ri), (pi, api)) in x.iter_mut().zip(&mut r).zip(p.iter().zip(&ap)) {
            *xi += alpha * pi;
            *ri -= alpha * api;
        }
        let rr_next = dot(&r, &r);
        let beta = rr_next / rr;
        for (pi, ri) in p.iter_mut().zip(&r) {
            *pi = ri + beta * *pi;
        }
        rr = rr_next;
        used += 1;
    }
    Ok((x, used, rr.sqrt() / norm_d))
}

/// `residual −= c · b(· − x_p)`; with `patch = Some(h)` only offsets within
/// `±h` pixels are touched (Clark's minor cycle, or a beam that was computed
/// on a smaller grid), which is no longer the Gram matrix of the atoms.
pub fn subtract(residual: &mut [f64], psf: &Psf, p: usize, c: f64, patch: Option<usize>) {
    let n = psf.n;
    let px = (p % n) as isize;
    let py = (p / n) as isize;
    let h = patch.map(|h| h as isize).unwrap_or(n as isize);
    let y0 = (py - h).max(0);
    let y1 = (py + h).min(n as isize - 1);
    let x0 = (px - h).max(0);
    let x1 = (px + h).min(n as isize - 1);
    for y in y0..=y1 {
        let row = &mut residual[(y as usize) * n..(y as usize + 1) * n];
        for x in x0..=x1 {
            row[x as usize] -= c * psf.at(x - px, y - py);
        }
    }
}

/// The pixel with the largest `|r|` and its value (the first on ties).
pub fn argmax_abs(r: &[f64]) -> (usize, f64) {
    let mut best = 0;
    for (p, &value) in r.iter().enumerate() {
        if value.abs() > r[best].abs() {
            best = p;
        }
    }
    (best, r[best])
}

/// Settings of a CLEAN run.
#[derive(Clone, Copy, Debug)]
pub struct CleanSettings {
    /// The loop gain `γ`; descent is guaranteed for `0 < γ < 2`.
    pub gain: f64,
    /// At most this many components.
    pub iterations: usize,
    /// Stop once the peak absolute residual falls below this.
    pub threshold: f64,
    /// Subtract only within `±patch` pixels of the component (`None`: exact).
    pub patch: Option<usize>,
}

/// One recorded component: the pixel and the residual value there before
/// the step (so the component is `gain * peak`).
#[derive(Clone, Copy, Debug)]
pub struct CleanStep {
    pub pixel: usize,
    pub peak: f64,
}

/// The outcome of [`hogbom`].
#[derive(Clone, Debug)]
pub struct CleanResult {
    pub model: Vec<f64>,
    pub residual: Vec<f64>,
    pub steps: Vec<CleanStep>,
}

/// Högbom CLEAN on a dirty image: find `argmax |r|`, add `γ r_p` to the
/// model at `p` and subtract `γ r_p b(· − x_p)` from the residual.
pub fn hogbom(dirty: &[f64], psf: &Psf, settings: &CleanSettings) -> CleanResult {
    let mut residual = dirty.to_vec();
    let mut model = vec![0.0; dirty.len()];
    let mut steps = Vec::with_capacity(settings.iterations);
    for _ in 0..settings.iterations {
        let (p, peak) = argmax_abs(&residual);
        if peak.abs() < settings.threshold {
            break;
        }
        let c = settings.gain * peak;
        model[p] += c;
        subtract(&mut residual, psf, p, c, settings.patch);
        steps.push(CleanStep { pixel: p, peak });
    }
    CleanResult {
        model,
        residual,
        steps,
    }
}

/// The Gram matrix `B_SS` of the atoms on `support` (row-major `k × k`).
pub fn gram(psf: &Psf, support: &[usize]) -> Vec<f64> {
    let n = psf.n as isize;
    let k = support.len();
    let mut g = vec![0.0; k * k];
    for (i, &p) in support.iter().enumerate() {
        for (j, &q) in support.iter().enumerate() {
            let dx = (p as isize % n) - (q as isize % n);
            let dy = (p as isize / n) - (q as isize / n);
            g[i * k + j] = psf.at(dx, dy) / psf.peak();
        }
    }
    g
}

/// Solve `A x = b` for a dense `k × k` matrix by Gaussian elimination with
/// partial pivoting; `None` when singular to working precision.
pub fn solve_dense(a: &[f64], b: &[f64]) -> Option<Vec<f64>> {
    let k = b.len();
    let mut m = a.to_vec();
    let mut x = b.to_vec();
    for col in 0..k {
        let pivot = (col..k)
            .max_by(|&i, &j| m[i * k + col].abs().total_cmp(&m[j * k + col].abs()))
            .unwrap();
        if m[pivot * k + col].abs() < 1e-14 {
            return None;
        }
        if pivot != col {
            for j in 0..k {
                m.swap(col * k + j, pivot * k + j);
            }
            x.swap(col, pivot);
        }
        for row in col + 1..k {
            let f = m[row * k + col] / m[col * k + col];
            if f != 0.0 {
                for j in col..k {
                    m[row * k + j] -= f * m[col * k + j];
                }
                x[row] -= f * x[col];
            }
        }
    }
    for col in (0..k).rev() {
        let mut sum = x[col];
        for j in col + 1..k {
            sum -= m[col * k + j] * x[j];
        }
        x[col] = sum / m[col * k + col];
    }
    Some(x)
}

/// The smallest eigenvalue of a symmetric `k × k` matrix by cyclic Jacobi
/// rotations (adequate for the small supports used here).
pub fn min_eigenvalue(a: &[f64], k: usize) -> f64 {
    let mut m = a.to_vec();
    for _sweep in 0..100 {
        let mut off = 0.0;
        for i in 0..k {
            for j in 0..k {
                if i != j {
                    off += m[i * k + j] * m[i * k + j];
                }
            }
        }
        if off < 1e-30 {
            break;
        }
        for p in 0..k {
            for q in p + 1..k {
                let apq = m[p * k + q];
                if apq.abs() < 1e-300 {
                    continue;
                }
                let theta = (m[q * k + q] - m[p * k + p]) / (2.0 * apq);
                let t = theta.signum() / (theta.abs() + (theta * theta + 1.0).sqrt());
                let t = if theta == 0.0 { 1.0 } else { t };
                let c = 1.0 / (t * t + 1.0).sqrt();
                let s = t * c;
                for r in 0..k {
                    let arp = m[r * k + p];
                    let arq = m[r * k + q];
                    m[r * k + p] = c * arp - s * arq;
                    m[r * k + q] = s * arp + c * arq;
                }
                for r in 0..k {
                    let apr = m[p * k + r];
                    let aqr = m[q * k + r];
                    m[p * k + r] = c * apr - s * aqr;
                    m[q * k + r] = s * apr + c * aqr;
                }
            }
        }
    }
    (0..k).map(|i| m[i * k + i]).fold(f64::INFINITY, f64::min)
}

/// Tropp's exact recovery coefficient of `support`,
/// `η(S) = max_{q ∉ S} ‖B_SS⁻¹ B_{S,q}‖₁`; selection stays inside `S` for
/// every residual in the span of the support atoms when `η(S) < 1`.
/// `None` when the support Gram matrix is singular. Costs `k³ + k² N`
/// (one inversion, then one product per pixel).
pub fn erc(psf: &Psf, grid: &Grid, support: &[usize]) -> Option<f64> {
    support_coefficients(psf, grid, support).map(|c| c.eta)
}

/// The inverse of a dense `k × k` matrix by Gauss-Jordan elimination with
/// partial pivoting; `None` when a pivot falls below 1e-14 (the threshold of
/// [`solve_dense`]).
pub fn invert_dense(a: &[f64], k: usize) -> Option<Vec<f64>> {
    let mut m = a.to_vec();
    let mut inv = vec![0.0; k * k];
    for i in 0..k {
        inv[i * k + i] = 1.0;
    }
    for col in 0..k {
        let pivot = (col..k)
            .max_by(|&i, &j| m[i * k + col].abs().total_cmp(&m[j * k + col].abs()))
            .unwrap();
        if m[pivot * k + col].abs() < 1e-14 {
            return None;
        }
        if pivot != col {
            for j in 0..k {
                m.swap(col * k + j, pivot * k + j);
                inv.swap(col * k + j, pivot * k + j);
            }
        }
        let scale = 1.0 / m[col * k + col];
        for j in 0..k {
            m[col * k + j] *= scale;
            inv[col * k + j] *= scale;
        }
        for row in 0..k {
            if row == col {
                continue;
            }
            let f = m[row * k + col];
            if f != 0.0 {
                for j in 0..k {
                    m[row * k + j] -= f * m[col * k + j];
                    inv[row * k + j] -= f * inv[col * k + j];
                }
            }
        }
    }
    Some(inv)
}

/// The coefficients of a support `S` that decide or bound where greedy
/// selection can go, all from `x_q = B_SS⁻¹ B_{S,q}` for pixels `q ∉ S`
/// (`research/clean-phase-transition.md` §2).
#[derive(Clone, Copy, Debug)]
pub struct SupportCoefficients {
    /// Tropp's ERC `η(S) = max_q ‖x_q‖₁`: below one, every residual in the
    /// span of the support atoms peaks inside `S`.
    pub eta: f64,
    /// `η₁(S) = max_q (‖x_q‖₁ − min_i |x_{q,i}|)`: below one, every residual
    /// in the span that vanishes at one support pixel peaks inside `S`; this
    /// is what gain-one CLEAN needs after its first pick.
    pub eta_gain_one: f64,
    /// `max_q ‖x_q‖_∞`: for two sources and gain one, below one (with a first
    /// pick on `S`) is necessary and sufficient for exact recovery.
    pub eta_max: f64,
    /// `max_q ‖B_{S,q}‖₁`, the largest off-support column sum of the PSF.
    pub cross: f64,
    /// `max_{i∈S} Σ_{j≠i} |B_ij|`, the Gershgorin radius of `B_SS`.
    pub radius: f64,
}

/// [`SupportCoefficients`] of `support` on `grid` (pixels outside the support
/// only); `None` when `B_SS` is singular.
pub fn support_coefficients(
    psf: &Psf,
    grid: &Grid,
    support: &[usize],
) -> Option<SupportCoefficients> {
    let n = psf.n as isize;
    let k = support.len();
    let g = gram(psf, support);
    let inv = invert_dense(&g, k)?;
    let radius = (0..k)
        .map(|i| {
            (0..k)
                .filter(|&j| j != i)
                .map(|j| g[i * k + j].abs())
                .sum::<f64>()
        })
        .fold(0.0, f64::max);
    let mut in_support = vec![false; grid.pixels()];
    for &p in support {
        in_support[p] = true;
    }
    let peak = psf.peak();
    let mut out = SupportCoefficients {
        eta: 0.0,
        eta_gain_one: 0.0,
        eta_max: 0.0,
        cross: 0.0,
        radius,
    };
    let mut b = vec![0.0; k];
    for (q, _) in in_support
        .iter()
        .enumerate()
        .filter(|(_, inside)| !**inside)
    {
        let qx = q as isize % n;
        let qy = q as isize / n;
        let mut cross = 0.0;
        for (bi, &p) in b.iter_mut().zip(support) {
            *bi = psf.at(p as isize % n - qx, p as isize / n - qy) / peak;
            cross += bi.abs();
        }
        let mut l1 = 0.0;
        let mut smallest = f64::INFINITY;
        let mut largest = 0.0_f64;
        for i in 0..k {
            let row = &inv[i * k..(i + 1) * k];
            let xi = row.iter().zip(&b).map(|(a, c)| a * c).sum::<f64>().abs();
            l1 += xi;
            smallest = smallest.min(xi);
            largest = largest.max(xi);
        }
        out.eta = out.eta.max(l1);
        out.eta_gain_one = out.eta_gain_one.max(l1 - smallest);
        out.eta_max = out.eta_max.max(largest);
        out.cross = out.cross.max(cross);
    }
    Some(out)
}

/// Bounds on `Σ_d(m)`, the largest sum of `m` values `|b(Δ)| / b(0)` over
/// offsets `Δ ≠ 0` that are pairwise at Chebyshev distance `≥ d` and fit in
/// the image together with the origin. With `pointed`, the origin is itself
/// one of the points, so every offset is also `≥ d` from it.
#[derive(Clone, Debug)]
pub struct SeparatedSums {
    /// `lower[m]`: a realisable configuration found greedily (largest `|b|`
    /// first), so `lower[m] ≤ Σ_d(m)`. Stays flat once no further offset fits.
    pub lower: Vec<f64>,
    /// `upper[m] ≥ Σ_d(m)`: tile the offset plane with `d × d` squares (at
    /// most one point per square, since two points in one square are closer
    /// than `d`), add the `m` largest square maxima, minimise over the `d²`
    /// placements of the tiling.
    pub upper: Vec<f64>,
    /// How many offsets the greedy configuration reached.
    pub placed: usize,
}

/// [`SeparatedSums`] for `m = 0..=m_max` at separation `d ≥ 1`.
pub fn separated_sums(psf: &Psf, d: usize, m_max: usize, pointed: bool) -> SeparatedSums {
    separated_sums_beyond(psf, d, m_max, if pointed { d } else { 1 })
}

/// [`SeparatedSums`] with every offset at Chebyshev distance `≥ min_radius`
/// from the origin (`1`: any nonzero offset; `d`: the pointed sums).
pub fn separated_sums_beyond(
    psf: &Psf,
    d: usize,
    m_max: usize,
    min_radius: usize,
) -> SeparatedSums {
    let n = psf.n as isize;
    let off = n - 1;
    let d_i = d.max(1) as isize;
    let r_i = min_radius.max(1) as isize;
    let peak = psf.peak();
    let mut offsets: Vec<(isize, isize, f64)> = Vec::new();
    for dy in -off..=off {
        for dx in -off..=off {
            if dx.abs().max(dy.abs()) < r_i {
                continue;
            }
            offsets.push((dx, dy, psf.at(dx, dy).abs() / peak));
        }
    }
    // Greedy lower bound: a realisable configuration (the points and the
    // origin span at most n − 1 pixels on each axis).
    let mut sorted = offsets.clone();
    sorted.sort_by(|a, b| b.2.total_cmp(&a.2));
    let mut chosen: Vec<(isize, isize)> = Vec::new();
    let (mut x0, mut x1, mut y0, mut y1) = (0isize, 0isize, 0isize, 0isize);
    let mut lower = vec![0.0; m_max + 1];
    for &(dx, dy, value) in &sorted {
        if chosen.len() == m_max {
            break;
        }
        let far = chosen
            .iter()
            .all(|&(cx, cy)| (cx - dx).abs().max((cy - dy).abs()) >= d_i);
        let fits = x1.max(dx) - x0.min(dx) <= off && y1.max(dy) - y0.min(dy) <= off;
        if far && fits {
            chosen.push((dx, dy));
            x0 = x0.min(dx);
            x1 = x1.max(dx);
            y0 = y0.min(dy);
            y1 = y1.max(dy);
            lower[chosen.len()] = lower[chosen.len() - 1] + value;
        }
    }
    let placed = chosen.len();
    for m in placed + 1..=m_max {
        lower[m] = lower[placed];
    }
    let upper = tile_upper(off, &offsets, d, m_max, true);
    SeparatedSums {
        lower,
        upper,
        placed,
    }
}

/// The tile upper bound on the largest sum of `m` weights over points that
/// are pairwise at Chebyshev distance `≥ d`: `d × d` squares hold at most one
/// point each, so the sum is at most the `m` largest square maxima. Every
/// placement of the tiling gives a valid bound; with `all_shifts` the
/// minimum over all `d²` placements is taken, otherwise over at most nine
/// spread placements. Offsets lie in `[−off, off]²`.
fn tile_upper(
    off: isize,
    offsets: &[(isize, isize, f64)],
    d: usize,
    m_max: usize,
    all_shifts: bool,
) -> Vec<f64> {
    let d_i = d.max(1) as isize;
    let shifts: Vec<isize> = if all_shifts || d_i <= 3 {
        (0..d_i).collect()
    } else {
        vec![0, d_i / 3, (2 * d_i) / 3]
    };
    let tiles_per_axis = ((2 * off + d_i) / d_i + 1) as usize;
    let mut upper = vec![f64::INFINITY; m_max + 1];
    let mut maxima = vec![0.0_f64; tiles_per_axis * tiles_per_axis];
    for &sy in &shifts {
        for &sx in &shifts {
            maxima.iter_mut().for_each(|v| *v = 0.0);
            for &(dx, dy, value) in offsets {
                let tx = ((dx + off + sx) / d_i) as usize;
                let ty = ((dy + off + sy) / d_i) as usize;
                let slot = &mut maxima[tx + tiles_per_axis * ty];
                *slot = slot.max(value);
            }
            let mut top = maxima.clone();
            top.sort_by(|a, b| b.total_cmp(a));
            let mut sum = 0.0;
            for (m, bound) in upper.iter_mut().enumerate() {
                if m > 0 {
                    sum += top.get(m - 1).copied().unwrap_or(0.0);
                }
                *bound = bound.min(sum);
            }
        }
    }
    upper
}

/// The anchored sufficient bound on the ERC of every support of `k` sources
/// pairwise `≥ d` apart (`research/clean-phase-transition.md`, Theorem 8):
/// `bound[k] ≥ η(S)` for all such supports, `k = 0..=k_max`.
///
/// For a pixel `q ∉ S` with a source `i` at offset `u = q − x_i`, writing
/// `B_SS⁻¹ e_i = e_i − B_SS⁻¹ H e_i` (`H` the off-diagonal part) gives
/// `B_SS⁻¹ B_{S,q} = b(u) e_i + B_SS⁻¹ y` with
/// `y_j = b(v_j − u) − b(u) b(v_j)`, `v_j = x_j − x_i`, so
/// `η_q ≤ |b(u)| + ‖y‖₁ / (1 − α)`, `α` the Gershgorin radius of `B_SS`.
/// The anchor term `|b(u)|` (up to `μ_1`) is no longer divided by `1 − α`,
/// and `y` keeps the cancellation between the sidelobes seen from `q` and
/// from `x_i`. For each radius `R`: pixels with a source closer than `R` use
/// this anchored form (worst case over `0 < |u| < R`, with `‖y‖₁` bounded by
/// a tile sum of `|b(v − u) − b(u) b(v)|` over `v` pairwise `≥ d` and `≥ d`
/// from the origin); pixels with every source at least `R` away use
/// `Σ_d^{≥R}(k) / (1 − α)`. `α ≤` the pointed tile sum of `k − 1` values.
/// The minimum over `R` (including `R = 1`, the plain separated-sum
/// condition) is returned; `∞` where `α`'s bound reaches one.
pub fn anchored_bound(psf: &Psf, d: usize, k_max: usize) -> Vec<f64> {
    let n = psf.n as isize;
    let off = n - 1;
    let d_i = d.max(1) as isize;
    let peak = psf.peak();
    let b = |x: isize, y: isize| psf.at(x, y) / peak;
    let m_max = k_max.saturating_sub(1);
    let alpha = separated_sums_beyond(psf, d, m_max, d).upper;
    let denom = |m: usize| {
        let a = alpha[m.min(m_max)];
        if a < 1.0 { 1.0 - a } else { 0.0 }
    };
    let plain = separated_sums_beyond(psf, d, k_max, 1).upper;
    let mut best: Vec<f64> = (0..=k_max)
        .map(|k| {
            let m = k.saturating_sub(1);
            if denom(m) > 0.0 {
                plain[k] / denom(m)
            } else {
                f64::INFINITY
            }
        })
        .collect();
    // Radii 2..=r_max, r_max = ⌈d/2⌉ + 1 clamped to [3, 6] (cost).
    let r_max = (d_i.div_euclid(2) + d_i % 2 + 1).clamp(3, 6);
    // Anchor terms A_u[m] = |b(u)| + W_u(m) / (1 − α(m)) for 0 < |u| < r_max.
    let mut anchors: Vec<(isize, Vec<f64>)> = Vec::new();
    for uy in -(r_max - 1)..=(r_max - 1) {
        for ux in -(r_max - 1)..=(r_max - 1) {
            if ux == 0 && uy == 0 {
                continue;
            }
            let bu = b(ux, uy);
            let mut weights = Vec::new();
            for vy in -off..=off {
                for vx in -off..=off {
                    if vx.abs().max(vy.abs()) < d_i || (vx == ux && vy == uy) {
                        continue;
                    }
                    let (wx, wy) = (vx - ux, vy - uy);
                    if wx.abs() > off || wy.abs() > off {
                        continue;
                    }
                    weights.push((vx, vy, (b(wx, wy) - bu * b(vx, vy)).abs()));
                }
            }
            let w = tile_upper(off, &weights, d, m_max, false);
            let a: Vec<f64> = (0..=m_max)
                .map(|m| {
                    if denom(m) > 0.0 {
                        bu.abs() + w[m] / denom(m)
                    } else {
                        f64::INFINITY
                    }
                })
                .collect();
            anchors.push((ux.abs().max(uy.abs()), a));
        }
    }
    for r in 2..=r_max {
        let mut beyond = Vec::new();
        for vy in -off..=off {
            for vx in -off..=off {
                if vx.abs().max(vy.abs()) >= r {
                    beyond.push((vx, vy, b(vx, vy).abs()));
                }
            }
        }
        let far = tile_upper(off, &beyond, d, k_max, false);
        for (k, slot) in best.iter_mut().enumerate().skip(1) {
            let m = k - 1;
            if denom(m) <= 0.0 {
                continue;
            }
            let near = anchors
                .iter()
                .filter(|(cheb, _)| *cheb < r)
                .map(|(_, a)| a[m])
                .fold(0.0, f64::max);
            let bound = near.max(far[k] / denom(m));
            *slot = slot.min(bound);
        }
    }
    best
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

    fn grid() -> Grid {
        Grid {
            n: 16,
            cell: 1.0e-4,
        }
    }

    #[test]
    fn psf_is_symmetric_with_unit_peak() {
        let s = sampling(150, 7);
        let g = grid();
        let b = psf(&s, &g);
        assert!((b.peak() - 1.0).abs() < 1e-12);
        for dy in -3..=3 {
            for dx in -3..=3 {
                assert!((b.at(dx, dy) - b.at(-dx, -dy)).abs() < 1e-12);
            }
        }
        assert!(b.coherence() < 1.0);
    }

    #[test]
    fn psf_is_the_gram_matrix_of_the_atoms() {
        let s = sampling(150, 11);
        let g = grid();
        let b = psf(&s, &g);
        let mut model = vec![0.0; g.pixels()];
        model[g.index(3, 5)] = 1.0;
        model[g.index(12, 9)] = -0.4;
        model[g.index(0, 15)] = 0.7;
        let by_vis = dirty(&s, &g, &predict(&s, &g, &model));
        let by_psf = convolve(&b, &model);
        for (p, (a, b)) in by_vis.iter().zip(&by_psf).enumerate() {
            assert!((a - b).abs() < 1e-10, "pixel {p}");
        }
    }

    /// Theorem 1: `Q(m') = Q(m) − γ(2−γ)/2 · r_p²` for every gain, exactly.
    #[test]
    fn one_step_misfit_identity() {
        let s = sampling(200, 3);
        let g = grid();
        let b = psf(&s, &g);
        let mut rng = Rng(99);
        let mut vis: Vec<Vis> = (0..s.len())
            .map(|_| (rng.next() - 0.5, rng.next() - 0.5))
            .collect();
        let mut truth = vec![0.0; g.pixels()];
        truth[g.index(8, 8)] = 1.0;
        truth[g.index(2, 13)] = 0.5;
        let signal = predict(&s, &g, &truth);
        for k in 0..s.len() {
            vis[k].0 += signal[k].0;
            vis[k].1 += signal[k].1;
        }
        for &gain in &[0.1, 0.5, 1.0, 1.5, 1.9, 2.3] {
            let mut residual = dirty(&s, &g, &vis);
            let mut model_vis = vec![(0.0, 0.0); s.len()];
            let mut q = misfit(&s, &vis, &model_vis);
            let mut rose = false;
            for _ in 0..40 {
                let (p, peak) = argmax_abs(&residual);
                let c = gain * peak;
                subtract(&mut residual, &b, p, c, None);
                add_atom(&s, &g, p, c, &mut model_vis);
                let q_next = misfit(&s, &vis, &model_vis);
                let predicted = q - gain * (2.0 - gain) / 2.0 * peak * peak;
                assert!(
                    (q_next - predicted).abs() < 1e-12 * q.max(1.0),
                    "gain {gain}: {q_next} against {predicted}"
                );
                rose |= q_next > q;
                q = q_next;
            }
            assert_eq!(rose, gain > 2.0, "gain {gain}");
        }
    }

    /// Theorem 4 in its coherence form: below `k < (1 + 1/μ)/2` every pick
    /// lands on the true support and the model converges to the truth.
    #[test]
    fn coherence_bound_gives_exact_recovery() {
        let s = sampling(400, 5);
        let g = grid();
        let b = psf(&s, &g);
        let mu = b.coherence();
        let k_max = ((1.0 + 1.0 / mu) / 2.0 - 1e-9).floor() as usize;
        assert!(k_max >= 1, "coherence {mu}");
        let support: Vec<usize> = (0..k_max).map(|i| g.index(1 + 3 * i, 2 + i)).collect();
        let mut truth = vec![0.0; g.pixels()];
        for (i, &p) in support.iter().enumerate() {
            truth[p] = 1.0 - 0.1 * i as f64;
        }
        let d = convolve(&b, &truth);
        let result = hogbom(
            &d,
            &b,
            &CleanSettings {
                gain: 0.7,
                iterations: 5000,
                threshold: 1e-12,
                patch: None,
            },
        );
        assert!(result.steps.iter().all(|s| support.contains(&s.pixel)));
        for (found, expected) in result.model.iter().zip(&truth) {
            assert!((found - expected).abs() < 1e-9);
        }
        assert!(erc(&b, &g, &support).unwrap() < 1.0);
    }

    /// The ERC by one dense solve per pixel, as first implemented.
    fn erc_by_solves(psf: &Psf, grid: &Grid, support: &[usize]) -> Option<f64> {
        let n = psf.n as isize;
        let g = gram(psf, support);
        let mut worst = 0.0_f64;
        for q in 0..grid.pixels() {
            if support.contains(&q) {
                continue;
            }
            let b: Vec<f64> = support
                .iter()
                .map(|&p| {
                    let dx = (p as isize % n) - (q as isize % n);
                    let dy = (p as isize / n) - (q as isize / n);
                    psf.at(dx, dy) / psf.peak()
                })
                .collect();
            let x = solve_dense(&g, &b)?;
            worst = worst.max(x.iter().map(|v| v.abs()).sum());
        }
        Some(worst)
    }

    fn random_support(rng: &mut Rng, g: &Grid, k: usize) -> Vec<usize> {
        let mut support = Vec::new();
        while support.len() < k {
            let p = ((rng.next() * g.pixels() as f64) as usize).min(g.pixels() - 1);
            if !support.contains(&p) {
                support.push(p);
            }
        }
        support
    }

    #[test]
    fn inverse_and_fast_erc_match_direct_solves() {
        let s = sampling(300, 17);
        let g = grid();
        let b = psf(&s, &g);
        let mut rng = Rng(4242);
        for k in 1..=6 {
            for _ in 0..5 {
                let support = random_support(&mut rng, &g, k);
                let gm = gram(&b, &support);
                let inv = invert_dense(&gm, k).unwrap();
                for i in 0..k {
                    for j in 0..k {
                        let e: f64 = (0..k).map(|l| gm[i * k + l] * inv[l * k + j]).sum();
                        assert!((e - if i == j { 1.0 } else { 0.0 }).abs() < 1e-9);
                    }
                }
                let c = support_coefficients(&b, &g, &support).unwrap();
                let slow = erc_by_solves(&b, &g, &support).unwrap();
                assert!(
                    (c.eta - slow).abs() < 1e-9 * slow.max(1.0),
                    "{} {slow}",
                    c.eta
                );
                assert!(c.eta_max <= c.eta_gain_one + 1e-12 || k == 1);
                assert!(c.eta_gain_one <= c.eta + 1e-12);
                // The Neumann bound: η ≤ cross / (1 − radius) when radius < 1.
                if c.radius < 1.0 {
                    assert!(c.eta <= c.cross / (1.0 - c.radius) + 1e-9);
                }
            }
        }
    }

    #[test]
    fn separated_sum_bounds_bracket_the_exact_value() {
        let s = sampling(120, 23);
        let g = Grid { n: 8, cell: 1.0e-4 };
        let b = psf(&s, &g);
        let off = 7isize;
        let mu = |d: isize| b.outside_patch((d - 1).max(0) as usize);
        for d in 1..=5usize {
            for pointed in [false, true] {
                let sums = separated_sums(&b, d, 4, pointed);
                let di = d as isize;
                // Exact maximum over pairs by brute force (m = 2).
                let mut cands = Vec::new();
                for dy in -off..=off {
                    for dx in -off..=off {
                        let c = dx.abs().max(dy.abs());
                        if c > 0 && (!pointed || c >= di) {
                            cands.push((dx, dy, b.at(dx, dy).abs()));
                        }
                    }
                }
                let mut exact2 = 0.0_f64;
                for (i, a) in cands.iter().enumerate() {
                    exact2 = exact2.max(a.2);
                    for c in &cands[i + 1..] {
                        let sep = (a.0 - c.0).abs().max((a.1 - c.1).abs());
                        let span = (a.0.max(c.0).max(0) - a.0.min(c.0).min(0) <= off)
                            && (a.1.max(c.1).max(0) - a.1.min(c.1).min(0) <= off);
                        if sep >= di && span {
                            exact2 = exact2.max(a.2 + c.2);
                        }
                    }
                }
                assert!(sums.lower[2] <= exact2 + 1e-12);
                assert!(exact2 <= sums.upper[2] + 1e-12);
                for m in 1..=4usize {
                    assert!(sums.lower[m] <= sums.upper[m] + 1e-12);
                    // Never worse than the counting bounds of Proposition 4'.
                    let counting = if pointed {
                        m as f64 * mu(di)
                    } else {
                        mu(1) + (m as f64 - 1.0) * mu(di.div_euclid(2) + di % 2)
                    };
                    assert!(sums.upper[m] <= counting + 1e-12, "d {d} m {m} {pointed}");
                }
            }
        }
    }

    /// Theorem 8: the anchored bound dominates the ERC of every support with
    /// the given separation, and is never above the plain separated-sum bound.
    #[test]
    fn anchored_bound_dominates_the_erc() {
        let s = sampling(400, 41);
        let g = Grid {
            n: 12,
            cell: 1.0e-4,
        };
        let b = psf(&s, &g);
        let mut rng = Rng(9001);
        let mut finite = 0;
        for d in 1..=5usize {
            let bound = anchored_bound(&b, d, 4);
            let alpha = separated_sums(&b, d, 3, true).upper;
            let plain = separated_sums(&b, d, 4, false).upper;
            for k in 1..=4usize {
                if alpha[k - 1] < 1.0 {
                    assert!(bound[k] <= plain[k] / (1.0 - alpha[k - 1]) + 1e-12);
                }
                if !bound[k].is_finite() {
                    continue;
                }
                finite += 1;
                for _ in 0..40 {
                    let mut support: Vec<usize> = Vec::new();
                    let mut tries = 0;
                    while support.len() < k && tries < 10_000 {
                        tries += 1;
                        let p = ((rng.next() * g.pixels() as f64) as usize).min(g.pixels() - 1);
                        let far = support.iter().all(|&q| {
                            let dx = (p % g.n) as isize - (q % g.n) as isize;
                            let dy = (p / g.n) as isize - (q / g.n) as isize;
                            dx.abs().max(dy.abs()) as usize >= d
                        });
                        if far {
                            support.push(p);
                        }
                    }
                    if support.len() < k {
                        continue;
                    }
                    let c = support_coefficients(&b, &g, &support).unwrap();
                    assert!(
                        c.eta <= bound[k] + 1e-9,
                        "d {d} k {k}: {} > {}",
                        c.eta,
                        bound[k]
                    );
                }
            }
        }
        assert!(finite > 5, "{finite}");
    }

    /// Two sources, gain one: the picks stay on the support exactly when the
    /// first pick does and `max_q ‖B_SS⁻¹ B_{S,q}‖_∞ < 1`; with more sources,
    /// a first pick on the support and `η₁ < 1` suffice.
    #[test]
    fn gain_one_selection_rules() {
        // Few, short baselines: a broad main lobe and high sidelobes, so
        // that both outcomes occur.
        let mut s = sampling(12, 31);
        for (u, v) in s.u.iter_mut().zip(s.v.iter_mut()) {
            *u *= 0.3;
            *v *= 0.3;
        }
        let g = grid();
        let b = psf(&s, &g);
        let mut rng = Rng(777);
        let mut seen = [0usize; 2];
        for k in 2..=4 {
            for _ in 0..150 {
                let support = random_support(&mut rng, &g, k);
                let mut truth = vec![0.0; g.pixels()];
                for &p in &support {
                    truth[p] = 0.2 + 0.8 * rng.next();
                }
                let d = convolve(&b, &truth);
                let first = support.contains(&argmax_abs(&d).0);
                let c = support_coefficients(&b, &g, &support).unwrap();
                let run = hogbom(
                    &d,
                    &b,
                    &CleanSettings {
                        gain: 1.0,
                        iterations: 400,
                        threshold: 1e-12,
                        patch: None,
                    },
                );
                let on = run.steps.iter().all(|st| support.contains(&st.pixel));
                if k == 2 && (c.eta_max - 1.0).abs() > 1e-9 {
                    assert_eq!(on, first && c.eta_max < 1.0, "{support:?}");
                    seen[usize::from(on)] += 1;
                }
                if first && c.eta_gain_one < 1.0 {
                    assert!(on);
                }
            }
        }
        // Both outcomes occur, so the two-source rule was tested both ways.
        assert!(seen[0] > 0 && seen[1] > 0, "{seen:?}");
    }

    #[test]
    fn dense_solver_and_eigenvalues() {
        let a = vec![4.0, 1.0, 0.0, 1.0, 3.0, 1.0, 0.0, 1.0, 2.0];
        let x = solve_dense(&a, &[1.0, 2.0, 3.0]).unwrap();
        let back: Vec<f64> = (0..3)
            .map(|i| (0..3).map(|j| a[i * 3 + j] * x[j]).sum::<f64>())
            .collect();
        for (i, expected) in [1.0, 2.0, 3.0].iter().enumerate() {
            assert!((back[i] - expected).abs() < 1e-12);
        }
        // Characteristic polynomial roots of the matrix above: 1.26795, 3, 4.73205.
        assert!((min_eigenvalue(&a, 3) - (3.0 - 3f64.sqrt())).abs() < 1e-9);
    }
}
