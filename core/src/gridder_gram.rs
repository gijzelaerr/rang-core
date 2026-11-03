//! The w-aware normal operator without visibilities: a sum of Toeplitz
//! operators, one per w-node, each applied by FFTs on the `2n` grid.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The Gram matrix of the measurement is
//! `G(l, l') = Re Σ_p W_p exp(2πi (u_p·(l − l') + w_p (x(l) − x(l'))))`,
//! `x = n − 1`, which depends on `l − l'` and on `x(l) − x(l')`. Replace the
//! exponential in `w` by a short expansion over fixed nodes,
//! `exp(2πi w ξ) ≈ Σ_k ψ_k(w) exp(2πi w_k ξ)` for `|ξ| ≤ X`, `X` the range of
//! `x` over the image. Then
//! `G̃ m = Re Σ_k e_k · (K_k ⊛ (ē_k · m))`, `e_k(l) = exp(2πi w_k x(l))`,
//! `K_k(δ) = Σ_p W_p ψ_k(w_p) exp(2πi u_p·δ)`,
//! the single-sum form of Fessler et al. (2005, IEEE TSP 53, 3393, eqs 24-26)
//! with `w` for time and `x` for the off-resonance map. Each `K_k` is needed
//! at `|δ| < n` only, so it lives on the `2n` grid; its transform is real.
//! See `research/gridder-theory.md`. A prototype behind a flag of the gemclean
//! binary; the default path does not use it.
//!
//! `ψ` has compact support of `stencil` nodes, the regularised least-squares
//! fit over `|ξ| ≤ X`, so setting up costs `stencil` 2-D gridding passes over
//! the visibilities rather than one per node. The fit needs no correction
//! function: a correction `c(ξ)` would have to be a function of `x(l) − x(l')`
//! and would not separate into a factor per pixel.

use crate::clean_certified::{Complex, Measurement};
use crate::wgridder::{self, C_LIGHT, Options, Real, VisData};
use rayon::prelude::*;
use rustfft::{Fft, FftPlanner};
use std::f64::consts::PI;
use std::sync::Arc;

/// Fractional positions of the coefficient table per unit node spacing.
const TABLE_BINS: usize = 8192;
/// Columns per task of the column pass.
const COLUMN_BLOCK: usize = 16;

/// The compact w-expansion: `stencil` nodes spaced `theta / (2π X)` apart.
#[derive(Clone, Debug)]
pub struct WExpansion {
    pub stencil: usize,
    pub theta: f64,
    /// `table[b * stencil + j]`: `ψ_j(s)` at `s = -1/2 + b / TABLE_BINS`.
    table: Vec<f64>,
    /// The largest `|exp(iθξs) − Σ_j ψ_j(s) exp(iθξ t_j)|` on a dense grid in
    /// `s` and `ξ` (sampled, so a measured value, not a theorem).
    pub sup_error: f64,
    /// `max_s Σ_j |ψ_j(s)|`, which multiplies the error of the gridded `K_k`.
    pub lebesgue: f64,
}

/// The lower Cholesky factor of a symmetric positive definite matrix.
fn cholesky_factor(a: &[f64], n: usize) -> Vec<f64> {
    let mut l = a.to_vec();
    for j in 0..n {
        for k in 0..j {
            let f = l[j * n + k];
            for i in j..n {
                l[i * n + j] -= l[i * n + k] * f;
            }
        }
        let d = l[j * n + j].sqrt();
        for i in j..n {
            l[i * n + j] /= d;
        }
    }
    l
}

/// Solve `L Lᵀ x = c` in place.
fn cholesky_solve(l: &[f64], n: usize, c: &mut [f64]) {
    for i in 0..n {
        for k in 0..i {
            c[i] -= l[i * n + k] * c[k];
        }
        c[i] /= l[i * n + i];
    }
    for i in (0..n).rev() {
        for k in i + 1..n {
            c[i] -= l[k * n + i] * c[k];
        }
        c[i] /= l[i * n + i];
    }
}

impl WExpansion {
    /// The fit for `stencil` (even) nodes at phase step `theta`, regularised
    /// by `ridge` relative to the diagonal.
    pub fn new(stencil: usize, theta: f64, ridge: f64) -> Result<WExpansion, String> {
        if stencil < 2 || !stencil.is_multiple_of(2) {
            return Err("the w stencil must be even and at least 2".into());
        }
        if !(theta > 0.0 && theta < PI) {
            return Err("the w phase step must lie in (0, π)".into());
        }
        let t: Vec<f64> = (0..stencil)
            .map(|j| j as f64 - (stencil as f64 - 1.0) / 2.0)
            .collect();
        // Chebyshev-distributed samples of ξ on [-1, 1]: enough to resolve
        // cos(θ ξ (S/2)) many times over.
        let m = 64 * stencil;
        let xi: Vec<f64> = (0..m)
            .map(|i| (PI * (i as f64 + 0.5) / m as f64).cos())
            .collect();
        let kernel = |d: f64| xi.iter().map(|x| (theta * x * d).cos()).sum::<f64>() / m as f64;
        let mut normal = vec![0.0; stencil * stencil];
        for i in 0..stencil {
            for j in 0..stencil {
                normal[i * stencil + j] = kernel(t[i] - t[j]);
            }
            normal[i * stencil + i] *= 1.0 + ridge;
        }
        let factor = cholesky_factor(&normal, stencil);
        let bins = TABLE_BINS + 1;
        let mut table = vec![0.0; bins * stencil];
        table
            .par_chunks_mut(stencil)
            .enumerate()
            .for_each(|(b, row)| {
                let s = -0.5 + b as f64 / TABLE_BINS as f64;
                for (j, r) in row.iter_mut().enumerate() {
                    *r = kernel(s - t[j]);
                }
                cholesky_solve(&factor, stencil, row);
            });
        let lebesgue = table
            .chunks(stencil)
            .map(|r| r.iter().map(|v| v.abs()).sum::<f64>())
            .fold(0.0, f64::max);
        let mut out = WExpansion {
            stencil,
            theta,
            table,
            sup_error: 0.0,
            lebesgue,
        };
        out.sup_error = out.measure_sup(&t);
        Ok(out)
    }

    fn measure_sup(&self, t: &[f64]) -> f64 {
        let mut coeff = vec![0.0; self.stencil];
        let mut sup = 0.0_f64;
        for sb in 0..=256 {
            let s = -0.5 + sb as f64 / 256.0 + if sb < 256 { 0.5 / 8192.0 } else { 0.0 };
            for (j, c) in coeff.iter_mut().enumerate() {
                *c = self.coefficient(s, j);
            }
            for xb in 0..=512 {
                let xi = xb as f64 / 512.0;
                let (mut re, mut im) = ((self.theta * xi * s).cos(), (self.theta * xi * s).sin());
                for (c, tj) in coeff.iter().zip(t) {
                    re -= c * (self.theta * xi * tj).cos();
                    im -= c * (self.theta * xi * tj).sin();
                }
                sup = sup.max(re.hypot(im));
            }
        }
        sup
    }

    /// `ψ_j(s)` by linear interpolation in the table, `s ∈ [-1/2, 1/2]`.
    #[inline(always)]
    pub fn coefficient(&self, s: f64, j: usize) -> f64 {
        let f = (s + 0.5) * TABLE_BINS as f64;
        let b = (f as usize).min(TABLE_BINS - 1);
        let a = f - b as f64;
        let lo = self.table[b * self.stencil + j];
        let hi = self.table[(b + 1) * self.stencil + j];
        lo + a * (hi - lo)
    }
}

/// `n − 1` of a pixel.
fn nm1(l: f64, m: f64) -> f64 {
    let r2 = l * l + m * m;
    -r2 / ((1.0 - r2).max(0.0).sqrt() + 1.0)
}

/// What the setup cost and holds.
#[derive(Clone, Copy, Debug, Default)]
pub struct Stats {
    pub planes: usize,
    pub stencil: usize,
    pub theta: f64,
    /// Range of `w` in wavelengths after folding to `w ≥ 0`.
    pub wmin: f64,
    pub wmax: f64,
    /// Range of `n − 1` over the image.
    pub x_range: f64,
    pub sup_error: f64,
    pub lebesgue: f64,
    /// Non-zero (node, visibility) pairs gridded by the setup.
    pub active_pairs: u64,
    /// Bytes of the stored spectra.
    pub cube_bytes: u64,
    pub setup_grid_seconds: f64,
    pub setup_fft_seconds: f64,
    /// Fraction of spectral cells with `|K̂| < 1e-7 max|K̂|`, per node on average.
    pub spectral_sparsity: f64,
    /// Largest imaginary part of a `K̂` over its largest real part (a check).
    pub hermitian_check: f64,
}

/// The operator.
pub struct GramOperator<T: Real> {
    n: usize,
    w0: f64,
    dw: f64,
    /// `n − 1` per pixel of the `n × n` image.
    x: Vec<f64>,
    /// Column-major real `K̂_k`, `(2n)²` each, already scaled by `1/(2n)²`.
    spectra: Vec<Vec<T>>,
    /// The no-w PSF on the `2n` grid, `Σ_k Re K_k`, centred on `(n, n)`.
    pub psf_no_w: Vec<f64>,
    forward: Arc<dyn Fft<T>>,
    inverse: Arc<dyn Fft<T>>,
    pub stats: Stats,
}

impl<T: Real + Send + Sync> GramOperator<T> {
    /// `wgt` is `nrow × nchan` and is used as given; `opts` is the imaging
    /// options (flips, cell) with `nx = ny = n`.
    pub fn new(
        opts: &Options,
        uvw: &[f64],
        freq: &[f64],
        wgt: &[f64],
        expansion: &WExpansion,
        epsilon: f64,
    ) -> Result<GramOperator<T>, String> {
        let n = opts.nx;
        if opts.ny != n || !n.is_multiple_of(2) {
            return Err("the Gram operator needs a square image of even side".into());
        }
        if opts.divide_by_n || opts.center_x != 0.0 || opts.center_y != 0.0 {
            return Err("the Gram operator handles divide_by_n = false, no shift".into());
        }
        let nrow = uvw.len() / 3;
        let nchan = freq.len();
        if wgt.len() != nrow * nchan {
            return Err("wgt must be nrow * nchan".into());
        }
        // Fold to w' ≥ 0: the real part of the Gram matrix does not change.
        let fw = if opts.flip_w { -1.0 } else { 1.0 };
        let mut folded = uvw.to_vec();
        let mut abs_w = vec![0.0; nrow];
        for (row, c) in folded.chunks_exact_mut(3).enumerate() {
            let w = fw * c[2];
            if w < 0.0 {
                c[0] = -c[0];
                c[1] = -c[1];
                c[2] = -c[2];
            }
            abs_w[row] = w.abs();
        }
        let (fmin, fmax) = (freq[0] / C_LIGHT, freq[nchan - 1] / C_LIGHT);
        let mut wmin = f64::INFINITY;
        let mut wmax = 0.0_f64;
        for &w in &abs_w {
            wmin = wmin.min(w * fmin);
            wmax = wmax.max(w * fmax);
        }
        // Pixels and the range of x.
        let half = (n / 2) as f64;
        let mut x = vec![0.0; n * n];
        x.par_chunks_mut(n).enumerate().for_each(|(i, row)| {
            let l = (i as f64 - half) * opts.pixsize_x;
            for (j, v) in row.iter_mut().enumerate() {
                *v = nm1(l, (j as f64 - half) * opts.pixsize_y);
            }
        });
        let xmin = x.par_iter().cloned().reduce(|| 0.0, f64::min);
        let xmax = x.par_iter().cloned().reduce(|| -2.0, f64::max);
        let x_range = (xmax - xmin).max(1e-300);
        let s = expansion.stencil;
        let dw = expansion.theta / (2.0 * PI * x_range);
        let cells = ((wmax - wmin) / dw).floor() as usize;
        let planes = cells + s;
        // Node k sits at w0 + k dw; a visibility in cell c uses nodes c..c + s.
        let w0 = wmin - (s / 2 - 1) as f64 * dw;

        let big = 2 * n;
        let mut planner = FftPlanner::<T>::new();
        let forward = planner.plan_fft_forward(big);
        let inverse = planner.plan_fft_inverse(big);
        let gridder = Options {
            nx: big,
            ny: big,
            do_wgridding: false,
            epsilon,
            ..*opts
        };
        // The constant visibility 1 − i: the real output is then
        // Σ W (cos θ + sin θ), whose even and odd parts are the real and
        // imaginary parts of K.
        let unit = vec![Complex::<f32>::new(1.0, -1.0); nrow * nchan];
        let scale = 1.0 / (big * big) as f64;
        let mut spectra = Vec::with_capacity(planes);
        let mut psf_no_w = vec![0.0; big * big];
        let mut stats = Stats {
            planes,
            stencil: s,
            theta: expansion.theta,
            wmin,
            wmax,
            x_range,
            sup_error: expansion.sup_error,
            lebesgue: expansion.lebesgue,
            ..Stats::default()
        };
        let mut plane_wgt = vec![T::of(0.0); nrow * nchan];
        let mut dirty = vec![T::of(0.0); big * big];
        let mut k_grid = vec![Complex::new(T::of(0.0), T::of(0.0)); big * big];
        let mut sparse_cells = 0u64;
        let f_over_c: Vec<f64> = freq.iter().map(|f| f / C_LIGHT).collect();
        for k in 0..planes {
            let t = std::time::Instant::now();
            // The weights of node k.
            let active: u64 = plane_wgt
                .par_chunks_mut(nchan)
                .zip(wgt.par_chunks(nchan))
                .zip(abs_w.par_iter())
                .map(|((out, row_wgt), &w_row)| {
                    let mut count = 0u64;
                    for ((o, &weight), &foc) in out.iter_mut().zip(row_wgt).zip(&f_over_c) {
                        *o = T::of(0.0);
                        if weight == 0.0 {
                            continue;
                        }
                        let p = (w_row * foc - wmin) / dw;
                        let cell = (p.floor().max(0.0) as usize).min(cells);
                        if k >= cell && k < cell + s {
                            let frac = (p - cell as f64 - 0.5).clamp(-0.5, 0.5);
                            *o = T::of(weight * expansion.coefficient(frac, k - cell));
                            count += 1;
                        }
                    }
                    count
                })
                .sum();
            stats.active_pairs += active;
            if active == 0 {
                dirty.fill(T::of(0.0));
            } else {
                wgridder::vis2dirty_multi(
                    &gridder,
                    &folded,
                    freq,
                    VisData::C64(&unit),
                    T::weights(&plane_wgt),
                    None,
                    Some(&mut dirty),
                    None,
                )?;
            }
            stats.setup_grid_seconds += t.elapsed().as_secs_f64();
            let t = std::time::Instant::now();
            // K at δ = (i − n, j − n), stored at δ mod 2n. The row and column
            // δ = −n are never used (|δ| < n) and have no mirror: zero.
            let dirty_ref = &dirty;
            k_grid
                .par_chunks_mut(big)
                .enumerate()
                .for_each(|(ki, row)| {
                    let i = (ki + n) % big;
                    for (kj, o) in row.iter_mut().enumerate() {
                        let j = (kj + n) % big;
                        *o = if i == 0 || j == 0 {
                            Complex::new(T::of(0.0), T::of(0.0))
                        } else {
                            let a = dirty_ref[i * big + j];
                            let b = dirty_ref[(big - i) * big + (big - j)];
                            let half = T::of(0.5);
                            Complex::new((a + b) * half, (a - b) * half)
                        };
                    }
                });
            for (ki, row) in k_grid.chunks(big).enumerate() {
                let i = (ki + n) % big;
                for (kj, v) in row.iter().enumerate() {
                    let j = (kj + n) % big;
                    psf_no_w[i * big + j] += v.re.to();
                }
            }
            let (spectrum, max_im, cells_small) =
                real_spectrum::<T>(&mut k_grid, big, &forward, scale);
            stats.hermitian_check = stats.hermitian_check.max(max_im);
            sparse_cells += cells_small;
            spectra.push(spectrum);
            stats.setup_fft_seconds += t.elapsed().as_secs_f64();
        }
        stats.cube_bytes = (planes * big * big * std::mem::size_of::<T>()) as u64;
        stats.spectral_sparsity = sparse_cells as f64 / (planes * big * big) as f64;
        Ok(GramOperator {
            n,
            w0,
            dw,
            x,
            spectra,
            psf_no_w,
            forward,
            inverse,
            stats,
        })
    }

    /// The operator without the w-term: one node, `G̃ m = K ⊛ m`, `K(δ) =
    /// Σ_p W_p cos 2π u_p·δ`. A translation-invariant PSF, as the Hessian
    /// approximation of pfb-imaging (Bester et al. 2024): one gridding pass to
    /// set up, one FFT pair per apply, and not the normal operator of the
    /// measurement away from the phase centre.
    pub fn no_w(
        opts: &Options,
        uvw: &[f64],
        freq: &[f64],
        wgt: &[f64],
        epsilon: f64,
    ) -> Result<GramOperator<T>, String> {
        let n = opts.nx;
        if opts.ny != n || !n.is_multiple_of(2) {
            return Err("the Gram operator needs a square image of even side".into());
        }
        let big = 2 * n;
        let mut planner = FftPlanner::<T>::new();
        let forward = planner.plan_fft_forward(big);
        let inverse = planner.plan_fft_inverse(big);
        let gridder = Options {
            nx: big,
            ny: big,
            do_wgridding: false,
            epsilon,
            ..*opts
        };
        let plane_wgt: Vec<T> = wgt.iter().map(|&w| T::of(w)).collect();
        let mut psf = vec![T::of(0.0); big * big];
        let t = std::time::Instant::now();
        wgridder::vis2dirty_multi(
            &gridder,
            uvw,
            freq,
            VisData::Unit,
            T::weights(&plane_wgt),
            None,
            None::<&mut [T]>,
            Some(&mut psf),
        )?;
        let setup_grid_seconds = t.elapsed().as_secs_f64();
        let t = std::time::Instant::now();
        let mut k_grid = vec![Complex::new(T::of(0.0), T::of(0.0)); big * big];
        let mut psf_no_w = vec![0.0; big * big];
        for ki in 0..big {
            let i = (ki + n) % big;
            for kj in 0..big {
                let j = (kj + n) % big;
                if i != 0 && j != 0 {
                    let v = psf[i * big + j];
                    k_grid[ki * big + kj] = Complex::new(v, T::of(0.0));
                    psf_no_w[i * big + j] = v.to();
                }
            }
        }
        let scale = 1.0 / (big * big) as f64;
        let (spectrum, _, _) = real_spectrum::<T>(&mut k_grid, big, &forward, scale);
        Ok(GramOperator {
            n,
            w0: 0.0,
            dw: 0.0,
            x: vec![0.0; n * n],
            spectra: vec![spectrum],
            psf_no_w,
            forward,
            inverse,
            stats: Stats {
                planes: 1,
                cube_bytes: (big * big * std::mem::size_of::<T>()) as u64,
                setup_grid_seconds,
                setup_fft_seconds: t.elapsed().as_secs_f64(),
                ..Stats::default()
            },
        })
    }

    /// The circulant preconditioner of a one-node operator: this operator's
    /// spectrum `K̂` replaced by `1 / (max(K̂, 0) + rho)`.
    pub fn inverse_filter(&self, rho: f64) -> Result<GramOperator<T>, String> {
        if self.spectra.len() != 1 || rho <= 0.0 || rho.is_nan() {
            return Err("the filter needs a one-node operator and a positive rho".into());
        }
        let big = 2 * self.n;
        let norm = (big * big) as f64;
        let spectrum = self.spectra[0]
            .par_iter()
            .map(|v| T::of(1.0 / norm / ((v.to() * norm).max(0.0) + rho)))
            .collect();
        Ok(GramOperator {
            n: self.n,
            w0: 0.0,
            dw: 0.0,
            x: self.x.clone(),
            spectra: vec![spectrum],
            psf_no_w: Vec::new(),
            forward: self.forward.clone(),
            inverse: self.inverse.clone(),
            stats: self.stats,
        })
    }

    /// Transforms of length `2n` one apply runs: rows forward, columns both
    /// ways, rows inverse, per node, before skipping empty rows.
    pub fn ffts_per_apply(&self) -> u64 {
        (self.spectra.len() * 6 * self.n) as u64
    }

    /// `G̃ m`, real, `n × n`.
    pub fn apply(&self, m: &[f64]) -> Result<Vec<f64>, String> {
        let n = self.n;
        if m.len() != n * n {
            return Err("model size".into());
        }
        let big = 2 * n;
        let zero = Complex::new(T::of(0.0), T::of(0.0));
        let mut rows = vec![zero; n * big];
        let mut cols = vec![zero; big * n];
        let mut out = vec![0.0_f64; n * n];
        let row_nonzero: Vec<bool> = m
            .par_chunks(n)
            .map(|r| r.iter().any(|&v| v != 0.0))
            .collect();
        // The screens exp(2πi w_k x), advanced by a recurrence plane to plane.
        let mut screen: Vec<Complex<f64>> = self
            .x
            .par_iter()
            .map(|&x| Complex::from_polar(1.0, 2.0 * PI * self.w0 * x))
            .collect();
        let step: Vec<Complex<f64>> = self
            .x
            .par_iter()
            .map(|&x| Complex::from_polar(1.0, 2.0 * PI * self.dw * x))
            .collect();
        let scratch_len = self
            .forward
            .get_inplace_scratch_len()
            .max(self.inverse.get_inplace_scratch_len());
        let row_nonzero = &row_nonzero;
        for spectrum in &self.spectra {
            // Rows forward: only the first n rows hold data.
            let screen_ref = &screen;
            rows.par_chunks_mut(big).enumerate().for_each_init(
                || vec![zero; scratch_len],
                |scratch, (i, row)| {
                    if !row_nonzero[i] {
                        return;
                    }
                    let (left, right) = row.split_at_mut(n);
                    let mr = &m[i * n..(i + 1) * n];
                    let sr = &screen_ref[i * n..(i + 1) * n];
                    for ((o, &v), s) in left.iter_mut().zip(mr).zip(sr) {
                        // z = m · conj(e_k)
                        *o = if v == 0.0 {
                            zero
                        } else {
                            Complex::new(T::of(v * s.re), T::of(-v * s.im))
                        };
                    }
                    right.fill(zero);
                    self.forward.process_with_scratch(row, scratch);
                },
            );
            // Columns forward, K̂, columns inverse, in one pass per block;
            // the rows beyond n are neither stored nor read back.
            let rows_ref = &rows;
            cols.par_chunks_mut(COLUMN_BLOCK * n)
                .enumerate()
                .for_each_init(
                    || (vec![zero; COLUMN_BLOCK * big], vec![zero; scratch_len]),
                    |(tmp, scratch), (block, out_block)| {
                        let j0 = block * COLUMN_BLOCK;
                        let width = out_block.len() / n;
                        for i in 0..n {
                            if !row_nonzero[i] {
                                for c in 0..width {
                                    tmp[c * big + i] = zero;
                                }
                                continue;
                            }
                            let row = &rows_ref[i * big + j0..i * big + j0 + width];
                            for (c, v) in row.iter().enumerate() {
                                tmp[c * big + i] = *v;
                            }
                        }
                        for c in 0..width {
                            let col = &mut tmp[c * big..(c + 1) * big];
                            col[n..].fill(zero);
                            self.forward.process_with_scratch(col, scratch);
                            let kk = &spectrum[(j0 + c) * big..(j0 + c + 1) * big];
                            for (v, &g) in col.iter_mut().zip(kk) {
                                *v = Complex::new(v.re * g, v.im * g);
                            }
                            self.inverse.process_with_scratch(col, scratch);
                            out_block[c * n..(c + 1) * n].copy_from_slice(&col[..n]);
                        }
                    },
                );
            // Rows inverse, and the real part times e_k.
            let cols_ref = &cols;
            rows.par_chunks_mut(big)
                .zip(out.par_chunks_mut(n))
                .enumerate()
                .for_each_init(
                    || vec![zero; scratch_len],
                    |scratch, (i, (row, o))| {
                        for (j, v) in row.iter_mut().enumerate() {
                            *v = cols_ref[j * n + i];
                        }
                        self.inverse.process_with_scratch(row, scratch);
                        let sr = &screen_ref[i * n..(i + 1) * n];
                        for ((o, y), s) in o.iter_mut().zip(row.iter()).zip(sr) {
                            *o += y.re.to() * s.re - y.im.to() * s.im;
                        }
                    },
                );
            screen
                .par_iter_mut()
                .zip(step.par_iter())
                .for_each(|(s, d)| *s *= *d);
        }
        Ok(out)
    }

    /// The number of spectra.
    pub fn planes(&self) -> usize {
        self.spectra.len()
    }
}

/// The 2-D forward FFT of `grid` (destroyed), its real part in column-major
/// order times `scale`, the largest imaginary part over the largest real
/// part, and the number of cells below `1e-7` of the largest.
fn real_spectrum<T: Real + Send + Sync>(
    grid: &mut [Complex<T>],
    big: usize,
    forward: &Arc<dyn Fft<T>>,
    scale: f64,
) -> (Vec<T>, f64, u64) {
    let zero = Complex::new(T::of(0.0), T::of(0.0));
    let scratch_len = forward.get_inplace_scratch_len();
    grid.par_chunks_mut(big).for_each_init(
        || vec![zero; scratch_len],
        |scratch, row| forward.process_with_scratch(row, scratch),
    );
    let grid_ref: &[Complex<T>] = grid;
    let mut out = vec![T::of(0.0); big * big];
    let per_col: Vec<(f64, f64)> = out
        .par_chunks_mut(big)
        .enumerate()
        .map_init(
            || (vec![zero; big], vec![zero; scratch_len]),
            |(col, scratch), (j, o)| {
                for (i, c) in col.iter_mut().enumerate() {
                    *c = grid_ref[i * big + j];
                }
                forward.process_with_scratch(col, scratch);
                let (mut re_max, mut im_max) = (0.0_f64, 0.0_f64);
                for (v, c) in o.iter_mut().zip(col.iter()) {
                    re_max = re_max.max(c.re.to().abs());
                    im_max = im_max.max(c.im.to().abs());
                    *v = T::of(c.re.to() * scale);
                }
                (re_max, im_max)
            },
        )
        .collect();
    let re_max = per_col.iter().fold(0.0_f64, |a, c| a.max(c.0));
    let im_max = per_col.iter().fold(0.0_f64, |a, c| a.max(c.1));
    let floor = 1e-7 * re_max * scale;
    let small = out.par_iter().filter(|v| v.to().abs() < floor).count() as u64;
    (out, im_max / re_max.max(1e-300), small)
}

/// A measurement on the operator: the dirty image and `Q(0)` are taken once
/// from the data, and every later residual is `d − G̃ m`, without visibilities.
pub struct GramMeasurement<T: Real> {
    pub operator: GramOperator<T>,
    dirty: Vec<f64>,
    q0: f64,
}

impl<T: Real + Send + Sync> GramMeasurement<T> {
    pub fn new(operator: GramOperator<T>, dirty: Vec<f64>, q0: f64) -> Self {
        GramMeasurement {
            operator,
            dirty,
            q0,
        }
    }
}

impl<T: Real + Send + Sync> Measurement for GramMeasurement<T> {
    fn side(&self) -> usize {
        self.operator.n
    }

    fn residual(&self, model: &[f64]) -> Result<(Vec<f64>, f64), String> {
        if !model.par_iter().any(|&c| c != 0.0) {
            return Ok((self.dirty.clone(), self.q0));
        }
        let g = self.operator.apply(model)?;
        let d_m: f64 = self.dirty.iter().zip(model).map(|(a, b)| a * b).sum();
        let m_g_m: f64 = g.iter().zip(model).map(|(a, b)| a * b).sum();
        let r = self.dirty.iter().zip(&g).map(|(a, b)| a - b).collect();
        Ok((r, self.q0 - d_m + 0.5 * m_g_m))
    }

    fn gram_apply(&self, x: &[f64]) -> Result<Vec<f64>, String> {
        self.operator.apply(x)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Case {
        uvw: Vec<f64>,
        freq: Vec<f64>,
        wgt: Vec<f64>,
        opts: Options,
    }

    fn case(n: usize, nrow: usize, wmax: f64, flip: bool) -> Case {
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
            .map(|i| next() * 2.0 * if i % 3 == 2 { wmax } else { umax / 1.05 })
            .collect();
        let raw: Vec<f64> = (0..2 * nrow).map(|_| 0.2 + next().abs()).collect();
        let sum: f64 = raw.iter().sum();
        let wgt = raw.iter().map(|w| w / sum).collect();
        let opts = Options {
            nx: n,
            ny: n,
            pixsize_x: cell,
            pixsize_y: cell,
            epsilon: 1e-9,
            flip_v: flip,
            flip_w: flip,
            ..Options::default()
        };
        Case {
            uvw,
            freq,
            wgt,
            opts,
        }
    }

    /// The direct sum of the Gram matrix, in the gridder's conventions.
    fn direct(c: &Case, m: &[f64]) -> Vec<f64> {
        let n = c.opts.nx;
        let half = (n / 2) as f64;
        let fv = if c.opts.flip_v { -1.0 } else { 1.0 };
        let fw = if c.opts.flip_w { -1.0 } else { 1.0 };
        let cell = c.opts.pixsize_x;
        let pix: Vec<(usize, f64, f64, f64)> = (0..n * n)
            .filter(|&q| m[q] != 0.0)
            .map(|q| {
                let l = ((q / n) as f64 - half) * cell;
                let mm = ((q % n) as f64 - half) * cell;
                (q, l, mm, nm1(l, mm))
            })
            .collect();
        (0..n * n)
            .into_par_iter()
            .map(|q| {
                let l = ((q / n) as f64 - half) * cell;
                let mm = ((q % n) as f64 - half) * cell;
                let x = nm1(l, mm);
                let mut sum = 0.0;
                for (row, chunk) in c.uvw.chunks(3).enumerate() {
                    for (ch, f) in c.freq.iter().enumerate() {
                        let foc = f / C_LIGHT;
                        let (u, v, w) = (chunk[0] * foc, fv * chunk[1] * foc, fw * chunk[2] * foc);
                        let wt = c.wgt[row * c.freq.len() + ch];
                        for &(p, lp, mp, xp) in &pix {
                            let phase = 2.0 * PI * (u * (l - lp) + v * (mm - mp) + w * (x - xp));
                            sum += wt * m[p] * phase.cos();
                        }
                    }
                }
                sum
            })
            .collect()
    }

    fn test_model(n: usize) -> Vec<f64> {
        let mut m = vec![0.0; n * n];
        m[0] = 1.0; // a corner: the largest x difference
        m[n * n - 1] = -0.5;
        m[(n / 2) * n + n / 2] = 0.75;
        m[5 * n + (n - 3)] = 0.25;
        m
    }

    #[test]
    fn matches_the_direct_sum_within_the_stated_bound() {
        for (flip, wmax) in [(false, 400.0), (true, 2000.0)] {
            let n = 32;
            let c = case(n, 800, wmax, flip);
            let m = test_model(n);
            let want = direct(&c, &m);
            let l1: f64 = m.iter().map(|v| v.abs()).sum();
            let mut last = 0.0;
            for (s, theta) in [(6, 1.2), (8, 1.2), (10, 1.0), (12, 0.9)] {
                let ex = WExpansion::new(s, theta, 1e-13).unwrap();
                let op =
                    GramOperator::<f64>::new(&c.opts, &c.uvw, &c.freq, &c.wgt, &ex, 1e-10).unwrap();
                let got = op.apply(&m).unwrap();
                let err = want
                    .iter()
                    .zip(&got)
                    .map(|(a, b)| (a - b).abs())
                    .fold(0.0, f64::max);
                // ‖(G − G̃) m‖_∞ ≤ (ε_w + Λ ε_uv) ‖W‖₁ ‖m‖₁.
                let bound = (ex.sup_error + ex.lebesgue * 1e-9) * l1;
                assert!(err <= bound, "s {s} err {err} bound {bound}");
                assert!(op.stats.hermitian_check < 1e-9);
                last = err;
            }
            assert!(last < 1e-5, "last {last}");
        }
    }

    #[test]
    fn symmetric_and_the_misfit_identity_holds() {
        let n = 32;
        let c = case(n, 500, 800.0, true);
        let ex = WExpansion::new(10, 1.0, 1e-13).unwrap();
        let op = GramOperator::<f64>::new(&c.opts, &c.uvw, &c.freq, &c.wgt, &ex, 1e-10).unwrap();
        let a = test_model(n);
        let mut b = vec![0.0; n * n];
        b[100] = 2.0;
        b[700] = -1.0;
        let ga = op.apply(&a).unwrap();
        let gb = op.apply(&b).unwrap();
        let ab: f64 = a.iter().zip(&gb).map(|(x, y)| x * y).sum();
        let ba: f64 = b.iter().zip(&ga).map(|(x, y)| x * y).sum();
        assert!((ab - ba).abs() < 1e-9, "{ab} {ba}");
        // With single-precision spectra the result is close, at a floor.
        let op32 = GramOperator::<f32>::new(&c.opts, &c.uvw, &c.freq, &c.wgt, &ex, 1e-5).unwrap();
        let g32 = op32.apply(&a).unwrap();
        let err = ga
            .iter()
            .zip(&g32)
            .map(|(x, y)| (x - y).abs())
            .fold(0.0, f64::max);
        assert!(err < 1e-3, "f32 {err}");
    }

    #[test]
    fn expansion_error_shrinks_with_the_stencil() {
        let coarse = WExpansion::new(8, 1.21, 1e-11).unwrap();
        let fine = WExpansion::new(12, 1.0, 1e-13).unwrap();
        assert!(coarse.sup_error < 2e-4, "{}", coarse.sup_error);
        assert!(fine.sup_error < 3e-6, "{}", fine.sup_error);
        assert!(coarse.lebesgue < 20.0 && fine.lebesgue < 50.0);
    }
}
