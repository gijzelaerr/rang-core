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
    let dot = |x: &[f64], y: &[f64]| x.iter().zip(y).map(|(a, b)| a * b).sum::<f64>();
    let norm_d = dot(dirty, dirty).sqrt();
    let mut x = vec![0.0; dirty.len()];
    let mut r = dirty.to_vec();
    let mut p = r.clone();
    let mut rr = dot(&r, &r);
    let mut used = 0;
    while used < iterations && rr.sqrt() > tolerance * norm_d {
        let ap = convolve(psf, &p);
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
    (x, used, rr.sqrt() / norm_d)
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
/// `None` when the support Gram matrix is singular.
pub fn erc(psf: &Psf, grid: &Grid, support: &[usize]) -> Option<f64> {
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
        let norm: f64 = x.iter().map(|v| v.abs()).sum();
        worst = worst.max(norm);
    }
    Some(worst)
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
