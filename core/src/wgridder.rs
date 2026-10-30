//! Exact w-gridder and degridder, a port of ducc0's wgridder.
//!
//! A Rust translation of the algorithm of Arras, Reinecke, Westermann and
//! Enßlin (2021, A&A 646, A58) as implemented in ducc0 0.42.0 by Martin
//! Reinecke (Max-Planck-Society; GPL-2.0-or-later): `wgridder_impl.h`
//! (`Wgridder`: `scanData`, `getNuNv`, `countRanges`, `getpix`, the
//! gridding and degridding helpers, `grid2dirty_post2`, `dirty2grid_pre2`,
//! `apply_global_corrections`), `gridding_kernel.{h,cc}` (`KernelDB`,
//! `esknew`, `FunctionApproximator`, `GLFullCorrection`,
//! `getAvailableKernels`), `gl_integrator` and `fft.h` (`good_size_cmplx`),
//! read from tag `ducc0_0_42_0` (commit `42ce8ab5`). The translation is part
//! of Rang (GPL-3.0-or-later). Validation protocol: `research/df1-wgridder.md`
//! (big-plan task DF1).
//!
//! Conventions are rang's direct Fourier transform's: pixel `(i, j)` of an
//! `nx * ny` image stored at `i * ny + j` lies at
//! `l = lshift + (i - nx/2) dx`, `m = mshift + (j - ny/2) dy`;
//! `vis2dirty` computes `sum_k wgt_k Re[V_k exp(+2 pi i (u l + v m + w (n-1)))]`
//! and `dirty2vis` its adjoint `V_k = wgt_k sum I exp(-2 pi i (...))`, uvw in
//! metres times `f / c`. This is ducc0 with `flip_w = true`; the `flip_w`
//! option here flips w relative to rang's convention.
//!
//! Differences from the original, fixed in the protocol: the kernel and
//! grid choice uses ducc0's cost model with one thread and a SIMD width of
//! eight, so it does not depend on the host or the thread count (an
//! explicit choice overrides it); the grid is complex in both modes (ducc0
//! uses Hartley transforms without w-gridding; the transforms agree); the
//! FFT is `rustfft`'s; every kernel tap is evaluated by Horner's rule from
//! its own polynomial (ducc0 evaluates the mirrored half from the even and
//! odd parts); w-planes run in parallel (rayon), each gridded, transformed
//! and projected by one task, and the plane terms are added in plane order,
//! so the result does not depend on the thread count. No BDA, no facets, no
//! tiling or locking.

use rayon::prelude::*;
use rustfft::num_complex::Complex;
use rustfft::num_traits::Float;
use rustfft::{Fft, FftNum, FftPlanner};
use std::f64::consts::PI;
use std::sync::Arc;

/// Speed of light as ducc0 uses it.
pub const C_LIGHT: f64 = 299_792_458.0;

/// SIMD width of the cost model (ducc0's `mysimdlen`, capped at 8; the
/// x86-64-v4 profile of the ducc0 0.42.0 wheel uses 8 for both precisions).
pub const COST_VLEN: usize = 8;

/// The working precision: grid, FFT, kernel and phases.
pub trait Real:
    FftNum + Float + Default + std::panic::RefUnwindSafe + std::panic::UnwindSafe
{
    /// True for `f32` (selects ducc0's single-precision kernels).
    const SINGLE: bool;
    /// Largest kernel support for this precision (`Wmax<T>`).
    const WMAX: usize;
    fn of(x: f64) -> Self;
    fn to(self) -> f64;
    /// Visibilities of this precision as gridder input.
    fn vis_data(v: &[Complex<Self>]) -> VisData<'_>;
    /// Weights of this precision as gridder input.
    fn weights(w: &[Self]) -> Weights<'_>;
}

impl Real for f32 {
    const SINGLE: bool = true;
    const WMAX: usize = 8;
    fn of(x: f64) -> f32 {
        x as f32
    }
    fn to(self) -> f64 {
        self as f64
    }
    fn vis_data(v: &[Complex<f32>]) -> VisData<'_> {
        VisData::C64(v)
    }
    fn weights(w: &[f32]) -> Weights<'_> {
        Weights::F32(w)
    }
}

impl Real for f64 {
    const SINGLE: bool = false;
    const WMAX: usize = 16;
    fn of(x: f64) -> f64 {
        x
    }
    fn to(self) -> f64 {
        self
    }
    fn vis_data(v: &[Complex<f64>]) -> VisData<'_> {
        VisData::C128(v)
    }
    fn weights(w: &[f64]) -> Weights<'_> {
        Weights::F64(w)
    }
}

// ------------------------------------------------------------- kernel table

/// One row of ducc0's `KernelDB`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct KernelParams {
    /// Support in grid cells.
    pub w: usize,
    /// Oversampling factor sigma.
    pub ofactor: f64,
    /// Accuracy reached.
    pub epsilon: f64,
    /// `beta / W` (the kernel uses `beta * W`).
    pub beta: f64,
    pub e0: f64,
    pub ndim: usize,
    pub singleprec: bool,
}

/// Number of table rows (ndim 2 and 3).
pub fn kernel_count() -> usize {
    KERNEL_ROWS.len()
}

/// Row `index` of the table, or `None` past its end.
pub fn kernel_row(index: usize) -> Option<KernelParams> {
    KERNEL_ROWS.get(index).map(
        |&(w, ofactor, epsilon, beta, e0, ndim, singleprec)| KernelParams {
            w,
            ofactor,
            epsilon,
            beta,
            e0,
            ndim,
            singleprec,
        },
    )
}

/// `getAvailableKernels<T>`: per support the row with the smallest
/// oversampling reaching `epsilon`, supports in increasing order.
pub fn available_kernels(
    epsilon: f64,
    ndim: usize,
    singleprec: bool,
    ofactor_min: f64,
    ofactor_max: f64,
) -> Result<Vec<usize>, String> {
    let wlim = if singleprec { 8 } else { 16 };
    let mut ofc = [ofactor_max; 20];
    let mut idx = [usize::MAX; 20];
    for (i, row) in (0..kernel_count()).filter_map(|i| kernel_row(i).map(|r| (i, r))) {
        if row.ndim == ndim
            && row.singleprec == singleprec
            && row.w <= wlim
            && row.epsilon <= epsilon
            && row.ofactor <= ofc[row.w]
            && row.ofactor >= ofactor_min
        {
            ofc[row.w] = row.ofactor;
            idx[row.w] = i;
        }
    }
    let res: Vec<usize> = idx.iter().copied().filter(|&v| v != usize::MAX).collect();
    if res.is_empty() {
        return Err("no appropriate kernel for this epsilon, sigma range and precision".into());
    }
    Ok(res)
}

/// `good_size_cmplx`: the smallest `2^a 3^b 5^c 7^d 11^e >= n` (n itself
/// for n <= 12).
pub fn good_size_complex(n: usize) -> usize {
    if n <= 12 {
        return n;
    }
    let mut best = 2 * n;
    let mut f11 = 1;
    while f11 < best {
        let mut f117 = f11;
        while f117 < best {
            let mut f1175 = f117;
            while f1175 < best {
                let mut x = f1175;
                while x < n {
                    x *= 2;
                }
                loop {
                    if x < n {
                        x *= 3;
                    } else if x > n {
                        if x < best {
                            best = x;
                        }
                        if x & 1 != 0 {
                            break;
                        }
                        x >>= 1;
                    } else {
                        return n;
                    }
                }
                f1175 *= 5;
            }
            f117 *= 7;
        }
        f11 *= 11;
    }
    best
}

/// `esknew`: the ES kernel `exp(beta ((1 - v^2)^e0 - 1))` on `[-1, 1]`.
pub fn es_kernel(v: f64, beta: f64, e0: f64) -> f64 {
    let tmp = (1.0 - v) * (1.0 + v);
    if tmp >= 0.0 {
        (beta * (tmp.powf(e0) - 1.0)).exp()
    } else {
        0.0
    }
}

/// Gauss–Legendre abscissas and weights for `n` points: the non-negative
/// abscissas (ascending from the centre as ducc0's `coordsSymmetric`) and
/// the weights doubled for positive abscissas (`weightsSymmetric`).
pub fn gauss_legendre_symmetric(n: usize) -> (Vec<f64>, Vec<f64>) {
    let m = n.div_ceil(2);
    let mut x = vec![0.0; m];
    let mut w = vec![0.0; m];
    for i in 0..m {
        // Root i counted from the largest.
        let mut z = (PI * (i as f64 + 0.75) / (n as f64 + 0.5)).cos();
        let mut pp = 0.0;
        for iter in 0..100 {
            let mut p1 = 1.0;
            let mut p2 = 0.0;
            for j in 1..=n {
                let p3 = p2;
                p2 = p1;
                p1 = ((2 * j - 1) as f64 * z * p2 - (j - 1) as f64 * p3) / j as f64;
            }
            pp = n as f64 * (z * p1 - p2) / (z * z - 1.0);
            let dz = p1 / pp;
            z -= dz;
            if dz.abs() <= 1e-16 * z.abs().max(1.0) && iter > 0 {
                break;
            }
        }
        let k = m - 1 - i;
        x[k] = z;
        w[k] = 2.0 / ((1.0 - z * z) * pp * pp);
    }
    if n % 2 == 1 {
        x[0] = 0.0;
        w[0] *= 0.5;
    }
    for v in w.iter_mut() {
        *v *= 2.0;
    }
    (x, w)
}

/// One ES kernel: the polynomial approximation used for gridding and the
/// Gauss–Legendre correction function.
#[derive(Clone, Debug)]
pub struct EsKernel {
    pub index: usize,
    pub support: usize,
    /// `beta * W` as `esknew` takes it.
    pub beta: f64,
    pub e0: f64,
    /// Polynomial degree (`W + 3`).
    pub degree: usize,
    /// `W * (degree + 1)` monomial coefficients, highest degree first, one
    /// polynomial per tap on `[-1, 1]` (`FunctionApproximator`).
    pub coeff: Vec<f64>,
    corr_x: Vec<f64>,
    corr_w: Vec<f64>,
}

impl EsKernel {
    pub fn new(index: usize) -> Result<EsKernel, String> {
        let row = kernel_row(index).ok_or("kernel index out of range")?;
        let supp = row.w;
        let beta = row.beta * supp as f64;
        let e0 = row.e0;
        let degree = supp + 3;
        let coeff = approximate(supp, degree, |v| es_kernel(v, beta, e0));
        // GLFullCorrection: p = 1.5 W + 2, 2p nodes.
        let p = (1.5 * supp as f64) as usize + 2;
        let (mut x, mut w) = gauss_legendre_symmetric(2 * p);
        for (xi, wi) in x.iter_mut().zip(w.iter_mut()) {
            *wi *= es_kernel(*xi, beta, e0) * supp as f64 * 0.5;
            *xi *= PI * supp as f64;
        }
        Ok(EsKernel {
            index,
            support: supp,
            beta,
            e0,
            degree,
            coeff,
            corr_x: x,
            corr_w: w,
        })
    }

    /// The kernel itself at `v` in `[-1, 1]`.
    pub fn phi(&self, v: f64) -> f64 {
        es_kernel(v, self.beta, self.e0)
    }

    /// The polynomial approximation at `v` in `[-1, 1]` (ducc0's
    /// `PolynomialKernel::eval`).
    pub fn eval(&self, v: f64) -> f64 {
        if v.abs() >= 1.0 {
            return 0.0;
        }
        let w = self.support;
        let xrel = w as f64 * 0.5 * (v + 1.0);
        let nth = (xrel as usize).min(w - 1);
        let locx = ((xrel - nth as f64) - 0.5) * 2.0;
        let c = &self.coeff[nth * (self.degree + 1)..][..self.degree + 1];
        let mut res = c[0];
        for &ci in &c[1..] {
            res = res * locx + ci;
        }
        res
    }

    /// `corfunc`: the inverse of the kernel's Fourier transform at `v`
    /// (cycles per grid cell times the support, as ducc0 scales it).
    pub fn corfunc(&self, v: f64) -> f64 {
        let mut tmp = 0.0;
        for (x, w) in self.corr_x.iter().zip(&self.corr_w) {
            tmp += w * (x * v).cos();
        }
        1.0 / tmp
    }

    /// `corfunc(n, dx)`: `corfunc(i dx)` for `i < n`.
    pub fn corfunc_table(&self, n: usize, dx: f64) -> Vec<f64> {
        (0..n).map(|i| self.corfunc(i as f64 * dx)).collect()
    }
}

/// `FunctionApproximator::getCoeffs` on `[-1, 1]`: `w` pieces, degree `d`.
fn approximate(w: usize, d: usize, func: impl Fn(f64) -> f64) -> Vec<f64> {
    let (lo, hi) = (-1.0_f64, 1.0_f64);
    let mut coeff = vec![0.0; w * (d + 1)];
    let chebroot: Vec<f64> = (0..=d)
        .map(|i| ((2 * i + 1) as f64 * PI / (2 * d + 2) as f64).cos())
        .collect();
    let mut cmat = vec![0.0; (d + 1) * (d + 1)];
    cmat[0] = 1.0;
    if d >= 1 {
        cmat[(d + 1) + 1] = 1.0;
    }
    for j in 2..=d {
        cmat[j * (d + 1)] = -cmat[(j - 2) * (d + 1)];
        for k in 1..=j {
            cmat[j * (d + 1) + k] =
                2.0 * cmat[(j - 1) * (d + 1) + k - 1] - cmat[(j - 2) * (d + 1) + k];
        }
    }
    for i in 0..w {
        let l = -1.0 + 2.0 * i as f64 / w as f64;
        let r = -1.0 + 2.0 * (i + 1) as f64 / w as f64;
        let mut y: Vec<f64> = chebroot
            .iter()
            .map(|&c| {
                let loc = ((c * (r - l) * 0.5 + (r + l) * 0.5) + 1.0) * 0.5 * (hi - lo) + lo;
                func(loc)
            })
            .collect();
        let avg = y.iter().sum::<f64>() / (d + 1) as f64;
        for v in y.iter_mut() {
            *v -= avg;
        }
        let mut lcf = vec![0.0; d + 1];
        for (j, value) in lcf.iter_mut().enumerate() {
            for (k, yk) in y.iter().enumerate() {
                *value += 2.0 / (d + 1) as f64
                    * yk
                    * ((j * (2 * k + 1)) as f64 * PI / (2 * d + 2) as f64).cos();
            }
        }
        lcf[0] *= 0.5;
        let mut lcf2 = vec![0.0; d + 1];
        for (j, lj) in lcf.iter().enumerate() {
            for (k, value) in lcf2.iter_mut().enumerate() {
                *value += cmat[j * (d + 1) + k] * lj;
            }
        }
        lcf2[0] += avg;
        for j in 0..=d {
            coeff[i * (d + 1) + j] = lcf2[d - j];
        }
    }
    coeff
}

// ------------------------------------------------------------------ options

/// Explicit kernel row and grid size, overriding the cost model.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct KernelChoice {
    pub index: usize,
    pub nu: usize,
    pub nv: usize,
}

/// The arguments of ducc0's `vis2dirty`/`dirty2vis` besides the arrays.
#[derive(Clone, Copy, Debug)]
pub struct Options {
    pub nx: usize,
    pub ny: usize,
    pub pixsize_x: f64,
    pub pixsize_y: f64,
    pub epsilon: f64,
    pub do_wgridding: bool,
    pub divide_by_n: bool,
    pub flip_u: bool,
    pub flip_v: bool,
    /// Flip w relative to rang's convention (ducc0's `flip_w` negated).
    pub flip_w: bool,
    pub center_x: f64,
    pub center_y: f64,
    pub allow_nshift: bool,
    pub sigma_min: f64,
    pub sigma_max: f64,
    pub kernel: Option<KernelChoice>,
}

impl Default for Options {
    fn default() -> Options {
        Options {
            nx: 0,
            ny: 0,
            pixsize_x: 0.0,
            pixsize_y: 0.0,
            epsilon: 1e-6,
            do_wgridding: true,
            divide_by_n: false,
            flip_u: false,
            flip_v: false,
            flip_w: false,
            center_x: 0.0,
            center_y: 0.0,
            allow_nshift: true,
            sigma_min: 1.1,
            sigma_max: 2.6,
            kernel: None,
        }
    }
}

/// What the gridder chose and found (ducc0's `verbosity=1` report).
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Plan {
    pub kernel_index: usize,
    pub supp: usize,
    pub nu: usize,
    pub nv: usize,
    /// Zero without w-gridding.
    pub nplanes: usize,
    pub nvis: usize,
    pub wmin_d: f64,
    pub wmax_d: f64,
    pub nm1min: f64,
    pub nm1max: f64,
    pub nshift: f64,
    pub dw: f64,
    pub wmin: f64,
    pub ofactor: f64,
}

/// Number of doubles `Plan::to_array` writes.
pub const N_INFO: usize = 14;

impl Plan {
    pub fn to_array(&self) -> [f64; N_INFO] {
        [
            self.kernel_index as f64,
            self.supp as f64,
            self.nu as f64,
            self.nv as f64,
            self.nplanes as f64,
            self.nvis as f64,
            self.wmin_d,
            self.wmax_d,
            self.nm1min,
            self.nm1max,
            self.nshift,
            self.dw,
            self.wmin,
            self.ofactor,
        ]
    }
}

// ---------------------------------------------------------------- geometry

/// The gridder's fixed geometry for one call.
struct Setup {
    nx: usize,
    ny: usize,
    pixsize_x: f64,
    pixsize_y: f64,
    lshift: f64,
    mshift: f64,
    lmshift: bool,
    shifting: bool,
    r_l: f64,
    r_m: f64,
    nshift: f64,
    do_wgridding: bool,
    divide_by_n: bool,
    nu: usize,
    nv: usize,
    supp: usize,
    ushift: f64,
    vshift: f64,
    maxiu0: i64,
    maxiv0: i64,
    kernel: EsKernel,
    nplanes: usize,
    wmin: f64,
    dw: f64,
    xdw: f64,
    wshift: f64,
    plan: Plan,
}

/// Rows and channels with uvw and frequency checks (`Baselines`).
struct Baselines {
    coord: Vec<[f64; 3]>,
    f_over_c: Vec<f64>,
}

impl Baselines {
    fn new(
        uvw: &[f64],
        freq: &[f64],
        flips: [bool; 3],
        r_l: f64,
        r_m: f64,
    ) -> Result<Self, String> {
        if freq.is_empty() || freq[0] <= 0.0 {
            return Err("channel frequencies must be positive".into());
        }
        if freq.windows(2).any(|p| p[1] < p[0]) {
            return Err("channel frequencies must be sorted in ascending order".into());
        }
        let fac = |f: bool| if f { -1.0 } else { 1.0 };
        let (fu, fv, fw) = (fac(flips[0]), fac(flips[1]), fac(flips[2]));
        let coord = uvw
            .as_chunks::<3>()
            .0
            .iter()
            .map(|c| {
                let (tu, tv, tw) = (fu * c[0], fv * c[1], fw * c[2]);
                [tu + r_l * tw, tv + r_m * tw, tw]
            })
            .collect();
        let f_over_c = freq.iter().map(|f| f / C_LIGHT).collect();
        Ok(Baselines { coord, f_over_c })
    }
}

/// `UVW::FixW`: flip so that w >= 0; returns the coordinates and the sign.
fn fix_w(c: [f64; 3]) -> ([f64; 3], f64) {
    let res = 1.0 - 2.0 * f64::from(u8::from(c[2] < 0.0));
    ([c[0] * res, c[1] * res, c[2] * res], res)
}

/// `nm1` as ducc0's `phase` forms it, with the recentring terms.
fn nm1_of(x: f64, y: f64, r_l: f64, r_m: f64) -> f64 {
    let xsq = x * x;
    let ysq = y * y;
    let tmp = 1.0 - xsq - ysq;
    let nm1 = if tmp >= 0.0 {
        (-xsq - ysq) / (tmp.sqrt() + 1.0)
    } else {
        -(-tmp).sqrt() - 1.0
    };
    nm1 + r_l * x + r_m * y
}

impl Setup {
    /// `Wgridder`'s constructor up to `countRanges`.
    #[allow(clippy::too_many_arguments)]
    fn new<T: Real>(
        opts: &Options,
        nvis: usize,
        wmin_d: f64,
        wmax_d: f64,
        r_l: f64,
        r_m: f64,
        gridding: bool,
    ) -> Result<Setup, String> {
        let (nx, ny) = (opts.nx, opts.ny);
        let (px, py) = (opts.pixsize_x, opts.pixsize_y);
        let lshift = if opts.flip_u {
            -opts.center_x
        } else {
            opts.center_x
        };
        let mshift = if opts.flip_v {
            -opts.center_y
        } else {
            opts.center_y
        };
        let lmshift = lshift != 0.0 || mshift != 0.0;
        // getNuNv: n-1 extremes over the corners (and the centre).
        let xmin = lshift - 0.5 * nx as f64 * px;
        let xmax = xmin + (nx as f64 - 1.0) * px;
        let ymin = mshift - 0.5 * ny as f64 * py;
        let ymax = ymin + (ny as f64 - 1.0) * py;
        let mut xext = vec![xmin, xmax];
        let mut yext = vec![ymin, ymax];
        if r_l != 0.0 || r_m != 0.0 {
            xext.push(lshift);
            yext.push(mshift);
        } else {
            if xmin * xmax < 0.0 {
                xext.push(0.0);
            }
            if ymin * ymax < 0.0 {
                yext.push(0.0);
            }
        }
        let mut nm1min = 1e300_f64;
        let mut nm1max = -1e300_f64;
        for &xc in &xext {
            for &yc in &yext {
                let tmp = xc * xc + yc * yc;
                let mut nval = if tmp <= 1.0 {
                    (1.0 - tmp).sqrt() - 1.0
                } else {
                    -(tmp - 1.0).sqrt() - 1.0
                };
                nval += r_l * xc + r_m * yc;
                nm1min = nm1min.min(nval);
                nm1max = nm1max.max(nval);
            }
        }
        let wgrid = opts.do_wgridding;
        let nshift = if !opts.allow_nshift || !wgrid {
            0.0
        } else {
            -0.5 * (nm1max + nm1min)
        };
        let shifting = lmshift || nshift != 0.0;
        let (kidx, nu, nv) = match opts.kernel {
            Some(k) => {
                let row = kernel_row(k.index).ok_or("kernel index out of range")?;
                if row.w > T::WMAX {
                    return Err("kernel support too large for this precision".into());
                }
                (k.index, k.nu, k.nv)
            }
            None => {
                choose_kernel::<T>(opts, nvis, wmin_d, wmax_d, nm1min, nm1max, nshift, gridding)?
            }
        };
        if nu >> 4 >= 1 << 16 || nv >> 4 >= 1 << 16 {
            return Err("grid too large".into());
        }
        let kernel = EsKernel::new(kidx)?;
        let supp = kernel.support;
        let nsafe = supp.div_ceil(2);
        if nu < 2 * nsafe || nv < 2 * nsafe {
            return Err("grid too small".into());
        }
        if nx % 2 != 0 || ny % 2 != 0 || nu % 2 != 0 || nv % 2 != 0 {
            return Err("image and grid sizes must be even".into());
        }
        let ofactor = (nu as f64 / nx as f64).min(nv as f64 / ny as f64);
        let ushift = supp as f64 * (-0.5) + 1.0 + nu as f64;
        let vshift = supp as f64 * (-0.5) + 1.0 + nv as f64;
        let maxiu0 = (nu + nsafe) as i64 - supp as i64;
        let maxiv0 = (nv + nsafe) as i64 - supp as i64;
        // countRanges
        let (nplanes, wmin, dw, xdw, wshift) = if wgrid {
            let dw = 0.5 / ofactor / (nm1max + nshift).abs().max((nm1min + nshift).abs());
            let xdw = 1.0 / dw;
            let nplanes = ((wmax_d - wmin_d) / dw + supp as f64) as usize;
            if nplanes >= 1 << 16 {
                return Err("too many w planes".into());
            }
            let wmin = (wmin_d + wmax_d) * 0.5 - 0.5 * (nplanes as f64 - 1.0) * dw;
            let wshift = dw - (0.5 * supp as f64 * dw) - wmin;
            (nplanes, wmin, dw, xdw, wshift)
        } else {
            (0, 0.0, 0.0, 0.0, 0.0)
        };
        let plan = Plan {
            kernel_index: kidx,
            supp,
            nu,
            nv,
            nplanes,
            nvis,
            wmin_d,
            wmax_d,
            nm1min,
            nm1max,
            nshift,
            dw,
            wmin,
            ofactor,
        };
        Ok(Setup {
            nx,
            ny,
            pixsize_x: px,
            pixsize_y: py,
            lshift,
            mshift,
            lmshift,
            shifting,
            r_l,
            r_m,
            nshift,
            do_wgridding: wgrid,
            divide_by_n: opts.divide_by_n,
            nu,
            nv,
            supp,
            ushift,
            vshift,
            maxiu0,
            maxiv0,
            kernel,
            nplanes,
            wmin,
            dw,
            xdw,
            wshift,
            plan,
        })
    }

    /// `getpix`: fractional grid position and first tap of one coordinate.
    fn getpix(&self, uin: f64, vin: f64) -> (f64, f64, i64, i64) {
        let mut u = uin * self.pixsize_x;
        u = (u - u.floor()) * self.nu as f64;
        let iu0 = ((u + self.ushift) as i64 - self.nu as i64).min(self.maxiu0);
        u -= iu0 as f64;
        let mut v = vin * self.pixsize_y;
        v = (v - v.floor()) * self.nv as f64;
        let iv0 = ((v + self.vshift) as i64 - self.nv as i64).min(self.maxiv0);
        v -= iv0 as f64;
        (u, v, iu0, iv0)
    }

    /// The first w-plane of a visibility (`get_uvwidx`).
    fn minplane(&self, w: f64) -> usize {
        if self.do_wgridding {
            ((w + self.wshift) * self.xdw).max(0.0) as usize
        } else {
            0
        }
    }

    fn x0(&self) -> f64 {
        self.lshift - 0.5 * self.nx as f64 * self.pixsize_x
    }

    fn y0(&self) -> f64 {
        self.mshift - 0.5 * self.ny as f64 * self.pixsize_y
    }

    /// Pixels whose phase and correction are computed: all of them with an
    /// l/m shift, else the quarter `i <= nx/2, j <= ny/2` (mirrored).
    fn table_dims(&self) -> (usize, usize) {
        if self.lmshift {
            (self.nx, self.ny)
        } else {
            (self.nx / 2 + 1, self.ny / 2 + 1)
        }
    }

    /// Index into a `table_dims` table for pixel `(i, j)`.
    fn table_index(&self, i: usize, j: usize, tny: usize) -> usize {
        if self.lmshift {
            i * tny + j
        } else {
            i.min(self.nx - i) * tny + j.min(self.ny - j)
        }
    }

    /// `nm1 + nshift` per table pixel (the w-screen's argument over w).
    fn screen_table(&self) -> Vec<f64> {
        let (tnx, tny) = self.table_dims();
        let (x0, y0) = (self.x0(), self.y0());
        let mut out = Vec::with_capacity(tnx * tny);
        for i in 0..tnx {
            let x = x0 + i as f64 * self.pixsize_x;
            for j in 0..tny {
                let y = y0 + j as f64 * self.pixsize_y;
                out.push(nm1_of(x, y, self.r_l, self.r_m) + self.nshift);
            }
        }
        out
    }

    /// `apply_global_corrections`: the u, v and w correction functions and
    /// the optional division by n, per table pixel.
    fn global_corrections(&self) -> Vec<f64> {
        let (tnx, tny) = self.table_dims();
        let cfu = self
            .kernel
            .corfunc_table(self.nx / 2 + 1, 1.0 / self.nu as f64);
        let cfv = self
            .kernel
            .corfunc_table(self.ny / 2 + 1, 1.0 / self.nv as f64);
        let (x0, y0) = (self.x0(), self.y0());
        let mut out = Vec::with_capacity(tnx * tny);
        for i in 0..tnx {
            let x = x0 + i as f64 * self.pixsize_x;
            let xsq = x * x;
            let iu = self.nx / 2 - i.min(self.nx - i);
            for j in 0..tny {
                let y = y0 + j as f64 * self.pixsize_y;
                let ysq = y * y;
                let tmp = 1.0 - xsq - ysq;
                let mut fct = if tmp >= 0.0 {
                    let nm1 = (-xsq - ysq) / (tmp.sqrt() + 1.0);
                    let mut f = self
                        .kernel
                        .corfunc((nm1 + self.r_l * x + self.r_m * y + self.nshift) * self.dw);
                    if self.divide_by_n {
                        f /= nm1 + 1.0;
                    }
                    f
                } else if self.divide_by_n {
                    0.0
                } else {
                    self.kernel
                        .corfunc((-(-tmp).sqrt() - 1.0 + self.nshift) * self.dw)
                };
                let iv = self.ny / 2 - j.min(self.ny - j);
                fct *= cfu[iu] * cfv[iv];
                out.push(fct);
            }
        }
        out
    }

    /// Grid correction without w-gridding (`grid2dirty_post`).
    fn uv_corrections(&self) -> (Vec<f64>, Vec<f64>) {
        (
            self.kernel
                .corfunc_table(self.nx / 2 + 1, 1.0 / self.nu as f64),
            self.kernel
                .corfunc_table(self.ny / 2 + 1, 1.0 / self.nv as f64),
        )
    }
}

/// `getNuNv`'s choice with one thread and `COST_VLEN`.
#[allow(clippy::too_many_arguments)]
fn choose_kernel<T: Real>(
    opts: &Options,
    nvis: usize,
    wmin_d: f64,
    wmax_d: f64,
    nm1min: f64,
    nm1max: f64,
    nshift: f64,
    gridding: bool,
) -> Result<(usize, usize, usize), String> {
    let _ = gridding; // Tacc == Tcalc: the gridding cost factor is one.
    let ndim = if opts.do_wgridding { 3 } else { 2 };
    let idx = available_kernels(
        opts.epsilon,
        ndim,
        T::SINGLE,
        opts.sigma_min,
        opts.sigma_max,
    )?;
    const NREF_FFT: f64 = 2048.0;
    const COSTREF_FFT: f64 = 0.0693;
    let vlen = COST_VLEN;
    let mut mincost = 1e300;
    let mut best = (usize::MAX, 0, 0);
    for &i in &idx {
        let krn = kernel_row(i).ok_or("kernel index out of range")?;
        let supp = krn.w;
        let nvec = supp.div_ceil(vlen);
        let ofactor = krn.ofactor;
        let nu = (2 * good_size_complex((opts.nx as f64 * ofactor * 0.5) as usize + 1)).max(16);
        let nv = (2 * good_size_complex((opts.ny as f64 * ofactor * 0.5) as usize + 1)).max(16);
        let logterm = ((nu * nv) as f64).ln() / (NREF_FFT * NREF_FFT).ln();
        let mut fftcost = nu as f64 / NREF_FFT * nv as f64 / NREF_FFT * logterm * COSTREF_FFT;
        let mut gridcost = 2.2e-10
            * nvis as f64
            * ((supp * nvec * vlen) as f64 + ((2 * nvec + 1) * (supp + 3) * vlen) as f64);
        if opts.do_wgridding {
            let dw = 0.5 / ofactor / (nm1max + nshift).abs().max((nm1min + nshift).abs());
            let nplanes = ((wmax_d - wmin_d) / dw + supp as f64) as usize;
            fftcost *= nplanes as f64;
            gridcost *= supp as f64;
        }
        // nthreads = 1: no scaling of either term (sigmoid(1, ...) = 1).
        let cost = fftcost + gridcost;
        if cost < mincost {
            mincost = cost;
            best = (i, nu, nv);
        }
    }
    Ok(best)
}

// ------------------------------------------------------------------- inputs

/// Visibility values of a gridding call, borrowed in the caller's precision
/// and converted to the working precision on reading (exact widening, or
/// rounding to nearest as NumPy's cast).
#[derive(Clone, Copy, Debug)]
pub enum VisData<'a> {
    /// Unit visibilities (a PSF), not materialised.
    Unit,
    C64(&'a [Complex<f32>]),
    C128(&'a [Complex<f64>]),
}

impl VisData<'_> {
    fn len(&self) -> Option<usize> {
        match self {
            VisData::Unit => None,
            VisData::C64(v) => Some(v.len()),
            VisData::C128(v) => Some(v.len()),
        }
    }

    #[inline(always)]
    fn get<T: Real>(&self, i: usize) -> Complex<T> {
        match self {
            VisData::Unit => Complex::new(T::one(), T::zero()),
            VisData::C64(v) => Complex::new(T::of(f64::from(v[i].re)), T::of(f64::from(v[i].im))),
            VisData::C128(v) => Complex::new(T::of(v[i].re), T::of(v[i].im)),
        }
    }
}

/// Weights of a call, borrowed in either precision.
#[derive(Clone, Copy, Debug)]
pub enum Weights<'a> {
    None,
    F32(&'a [f32]),
    F64(&'a [f64]),
}

impl Weights<'_> {
    fn len(&self) -> Option<usize> {
        match self {
            Weights::None => None,
            Weights::F32(w) => Some(w.len()),
            Weights::F64(w) => Some(w.len()),
        }
    }

    #[inline(always)]
    fn get<T: Real>(&self, i: usize) -> Option<T> {
        match self {
            Weights::None => None,
            Weights::F32(w) => Some(T::of(f64::from(w[i]))),
            Weights::F64(w) => Some(T::of(w[i])),
        }
    }
}

/// Which visibilities a call grids (ducc0's `scanData`): nonzero
/// `|vis|^2 wgt mask` when gridding data, nonzero `wgt mask` when
/// degridding or gridding unit visibilities.
#[derive(Clone, Copy)]
struct Activity<'a> {
    vis: Option<VisData<'a>>,
    wgt: Weights<'a>,
    mask: Option<&'a [u8]>,
}

impl Activity<'_> {
    #[inline(always)]
    fn active<T: Real>(&self, idx: usize) -> bool {
        let tnorm = match self.vis {
            Some(v) => v.get::<T>(idx).norm_sqr().to(),
            None => 1.0,
        };
        let twgt = self.wgt.get::<T>(idx).map_or(1.0, |w| w.to());
        let tmask = self.mask.map_or(1.0, |m| f64::from(m[idx]));
        tnorm * twgt * tmask != 0.0
    }
}

// ------------------------------------------------------------------- scan

/// Rows per task of the scans. Fixed, so that nothing depends on the
/// number of threads.
const ROW_CHUNK: usize = 256;

/// Number of active visibilities and their w range.
fn scan<T: Real>(bl: &Baselines, act: &Activity) -> (usize, f64, f64) {
    let nchan = bl.f_over_c.len();
    bl.coord
        .par_chunks(ROW_CHUNK)
        .enumerate()
        .map(|(c, rows)| {
            let mut n = 0usize;
            let mut lo = 1e300_f64;
            let mut hi = -1e300_f64;
            for (r, coord) in rows.iter().enumerate() {
                let row = c * ROW_CHUNK + r;
                for (ch, f) in bl.f_over_c.iter().enumerate() {
                    if act.active::<T>(row * nchan + ch) {
                        n += 1;
                        let w = (coord[2] * f).abs();
                        lo = lo.min(w);
                        hi = hi.max(w);
                    }
                }
            }
            (n, lo, hi)
        })
        .reduce(
            || (0, 1e300, -1e300),
            |a, b| (a.0 + b.0, a.1.min(b.1), a.2.max(b.2)),
        )
}

/// The recentring of an l/m shift with w-gridding (ducc0's constructor).
fn recentring(opts: &Options) -> (f64, f64) {
    let lshift = if opts.flip_u {
        -opts.center_x
    } else {
        opts.center_x
    };
    let mshift = if opts.flip_v {
        -opts.center_y
    } else {
        opts.center_y
    };
    if opts.do_wgridding && (lshift != 0.0 || mshift != 0.0) {
        let xext = lshift.abs() + 0.5 * opts.nx as f64 * opts.pixsize_x;
        let yext = mshift.abs() + 0.5 * opts.ny as f64 * opts.pixsize_y;
        if xext * xext + yext * yext < 1.0 {
            let n0 = (1.0 - lshift * lshift - mshift * mshift).sqrt();
            return (lshift / n0, mshift / n0);
        }
    }
    (0.0, 0.0)
}

fn check_common(opts: &Options, nrow: usize, nchan: usize, uvw: &[f64]) -> Result<(), String> {
    if opts.nx == 0 || opts.ny == 0 {
        return Err("image dimensions must be positive".into());
    }
    if opts.epsilon.is_nan() || opts.epsilon <= 0.0 {
        return Err("epsilon must be positive".into());
    }
    if opts.pixsize_x.is_nan()
        || opts.pixsize_y.is_nan()
        || opts.pixsize_x <= 0.0
        || opts.pixsize_y <= 0.0
    {
        return Err("pixel sizes must be positive".into());
    }
    if uvw.len() != nrow * 3 || nchan == 0 {
        return Err("uvw must have three values per row".into());
    }
    if nrow >= 1 << 32 || nchan >= 1 << 32 {
        return Err("too many rows or channels".into());
    }
    Ok(())
}

// ------------------------------------------------------------------ layout

/// One active visibility: its row and channel (its first w-plane is its
/// block's).
#[derive(Clone, Copy, Debug, Default)]
struct VisRef {
    row: u32,
    ch: u32,
}

/// Coordinates in wavelengths after `FixW`, and the sign it took.
#[inline(always)]
fn uvw_of(bl: &Baselines, r: VisRef) -> ([f64; 3], f64) {
    let (c, imflip) = fix_w(bl.coord[r.row as usize]);
    let f = bl.f_over_c[r.ch as usize];
    ([c[0] * f, c[1] * f, c[2] * f], imflip)
}

/// The tiles of the grid. A visibility belongs to the tile holding its
/// first tap in shifted grid coordinates `(i + n/2) mod n`, so that the
/// seam where tiles wrap lies at the grid's edge (the longest baselines),
/// not at u = 0. A tile's buffer covers `tile + supp - 1` cells per axis
/// from the tile's origin. Tiles that do not wrap and differ by two in an
/// index never share a cell, so the four parity classes are gridded in
/// turn, the tiles of one class in parallel; wrapping tiles come last, in
/// order. The layout depends only on the grid and the support.
#[derive(Clone, Copy, Debug)]
struct Tiling {
    log2: u32,
    ntu: usize,
    ntv: usize,
    su: usize,
    sv: usize,
}

impl Tiling {
    fn new<T: Real>(setup: &Setup) -> Tiling {
        // ducc0's tile sizes (`log2tile`): 32 cells in f32, 16 in f64.
        let log2 = if T::SINGLE { 5 } else { 4 };
        let tile = 1usize << log2;
        Tiling {
            log2,
            ntu: setup.nu.div_ceil(tile),
            ntv: setup.nv.div_ceil(tile),
            su: tile + setup.supp - 1,
            sv: tile + setup.supp - 1,
        }
    }
}

/// Shifted coordinate of a first tap.
#[inline(always)]
fn shifted(i0: i64, n: usize) -> usize {
    (i0 + (n / 2) as i64).rem_euclid(n as i64) as usize
}

/// Offset of a first tap inside the buffer whose shifted origin is `base`.
#[inline(always)]
fn offset(i0: i64, n: usize, base: usize) -> usize {
    let n = n as i64;
    let mut d = i0 + n / 2 - base as i64;
    if d < 0 {
        d += n;
    } else if d >= n {
        d -= n;
    }
    d as usize
}

/// A run of visibilities of one tile with the same first plane.
#[derive(Clone, Copy, Debug)]
struct Block {
    minplane: usize,
    start: usize,
    end: usize,
}

/// A tile holding visibilities: its indices, its blocks and its planes.
#[derive(Clone, Copy, Debug)]
struct Tile {
    tu: usize,
    tv: usize,
    blocks: (usize, usize),
    plo: usize,
    phi: usize,
    edge: bool,
}

/// Active visibilities sorted by (tile, first plane, row, channel).
struct Layout {
    tiling: Tiling,
    refs: Vec<VisRef>,
    blocks: Vec<Block>,
    tiles: Vec<Tile>,
}

impl Setup {
    /// Tile index and first plane of one active visibility.
    #[inline(always)]
    fn locate(&self, tiling: &Tiling, bl: &Baselines, row: usize, ch: usize) -> (usize, usize) {
        let r = VisRef {
            row: row as u32,
            ch: ch as u32,
        };
        let ([u, v, w], _) = uvw_of(bl, r);
        let (_, _, iu0, iv0) = self.getpix(u, v);
        let tu = shifted(iu0, self.nu) >> tiling.log2;
        let tv = shifted(iv0, self.nv) >> tiling.log2;
        let nbuckets = self.nplanes.max(1);
        (tu * tiling.ntv + tv, self.minplane(w).min(nbuckets - 1))
    }
}

/// Counting sort of the active visibilities by tile over fixed row chunks
/// (each chunk's visibilities placed in row-channel order), then a stable
/// sort by first plane within each tile.
fn layout<T: Real>(setup: &Setup, bl: &Baselines, act: &Activity) -> Layout {
    let tiling = Tiling::new::<T>(setup);
    let nrow = bl.coord.len();
    let nchan = bl.f_over_c.len();
    let ntiles = tiling.ntu * tiling.ntv;
    // At most 2^22 chunk-tile counters.
    let rows_per_chunk = ROW_CHUNK.max((nrow * ntiles) >> 22).max(1);
    let nchunks = nrow.div_ceil(rows_per_chunk).max(1);
    let chunk_rows = |c: usize| (c * rows_per_chunk)..((c + 1) * rows_per_chunk).min(nrow);
    let counts: Vec<Vec<usize>> = (0..nchunks)
        .into_par_iter()
        .map(|c| {
            let mut cnt = vec![0usize; ntiles];
            for row in chunk_rows(c) {
                for ch in 0..nchan {
                    if act.active::<T>(row * nchan + ch) {
                        cnt[setup.locate(&tiling, bl, row, ch).0] += 1;
                    }
                }
            }
            cnt
        })
        .collect();
    let mut tile_start = vec![0usize; ntiles + 1];
    let mut starts = vec![vec![0usize; ntiles]; nchunks];
    let mut acc = 0usize;
    for t in 0..ntiles {
        tile_start[t] = acc;
        for c in 0..nchunks {
            starts[c][t] = acc;
            acc += counts[c][t];
        }
    }
    tile_start[ntiles] = acc;
    drop(counts);
    let mut refs = vec![VisRef::default(); acc];
    let out = SyncPtr(refs.as_mut_ptr());
    starts.into_par_iter().enumerate().for_each(|(c, mut pos)| {
        for row in chunk_rows(c) {
            for ch in 0..nchan {
                if act.active::<T>(row * nchan + ch) {
                    let t = setup.locate(&tiling, bl, row, ch).0;
                    // SAFETY: every chunk writes its own disjoint slots.
                    unsafe {
                        out.get().add(pos[t]).write(VisRef {
                            row: row as u32,
                            ch: ch as u32,
                        })
                    };
                    pos[t] += 1;
                }
            }
        }
    });
    // Per tile: a stable sort by first plane, and the runs of equal first
    // plane as (first plane, length).
    let mut parts = Vec::new();
    {
        let mut rest = &mut refs[..];
        for tile in 0..ntiles {
            let (a, b) = rest.split_at_mut(tile_start[tile + 1] - tile_start[tile]);
            if !a.is_empty() {
                parts.push((tile, a));
            }
            rest = b;
        }
    }
    let runs: Vec<(usize, Vec<(usize, usize)>)> = parts
        .into_par_iter()
        .map(|(tile, part)| {
            let mp = |r: &VisRef| setup.locate(&tiling, bl, r.row as usize, r.ch as usize).1;
            part.sort_by_cached_key(mp);
            let mut runs: Vec<(usize, usize)> = Vec::new();
            for r in part.iter() {
                let m = mp(r);
                match runs.last_mut() {
                    Some(last) if last.0 == m => last.1 += 1,
                    _ => runs.push((m, 1)),
                }
            }
            (tile, runs)
        })
        .collect();
    let mut blocks = Vec::new();
    let mut tiles = Vec::new();
    for (t, tile_runs) in runs {
        let b0 = blocks.len();
        let mut start = tile_start[t];
        for (minplane, len) in tile_runs {
            blocks.push(Block {
                minplane,
                start,
                end: start + len,
            });
            start += len;
        }
        let (tu, tv) = (t / tiling.ntv, t % tiling.ntv);
        let edge = (tu << tiling.log2) + tiling.su > setup.nu
            || (tv << tiling.log2) + tiling.sv > setup.nv;
        tiles.push(Tile {
            tu,
            tv,
            blocks: (b0, blocks.len()),
            plo: blocks[b0].minplane,
            phi: blocks[blocks.len() - 1].minplane,
            edge,
        });
    }
    Layout {
        tiling,
        refs,
        blocks,
        tiles,
    }
}

/// A raw pointer shared by tasks writing disjoint elements.
#[derive(Clone, Copy)]
struct SyncPtr<T>(*mut T);
// SAFETY: used only for writes to disjoint elements (documented per use).
unsafe impl<T: Send> Send for SyncPtr<T> {}
// SAFETY: as above.
unsafe impl<T: Send> Sync for SyncPtr<T> {}

impl<T> SyncPtr<T> {
    /// The pointer (a method, so that closures capture the whole wrapper).
    #[inline(always)]
    fn get(self) -> *mut T {
        self.0
    }
}

/// The per-visibility phase of the shift (`compute_phases`).
fn shift_phase<T: Real>(setup: &Setup, bl: &Baselines, r: VisRef, sign: f64) -> Complex<T> {
    let (bcoord, imflip) = fix_w(bl.coord[r.row as usize]);
    let fct = sign
        * imflip
        * (bcoord[0] * setup.lshift + bcoord[1] * setup.mshift + bcoord[2] * setup.nshift);
    let tmp = fct * bl.f_over_c[r.ch as usize];
    let ang = if T::SINGLE {
        T::of(2.0 * PI * (tmp - tmp.floor()))
    } else {
        T::of(2.0 * PI * tmp)
    };
    let (sn, cs) = Float::sin_cos(ang);
    Complex::new(cs, sn)
}

/// The unit visibility's gridded value: the phase of the shift times the
/// weight, the imaginary part times the `FixW` sign (DF1's value of a unit
/// visibility).
#[inline(always)]
fn unit_value<T: Real>(setup: &Setup, bl: &Baselines, r: VisRef, w: Option<T>) -> Complex<T> {
    let mut v = Complex::new(T::one(), T::zero());
    if setup.shifting {
        v = v * shift_phase::<T>(setup, bl, r, 1.0);
    }
    if let Some(w) = w {
        v = v * w;
    }
    let (_, imflip) = fix_w(bl.coord[r.row as usize]);
    Complex::new(v.re, v.im * T::of(imflip))
}

/// The gridded value of visibility `v` from its unit value `p`: `v` times
/// the phase and weight, the imaginary part times the sign. The dirty
/// image is formed this way with or without a PSF, so the two agree bit
/// for bit; the product order differs from DF1's `(v * phase) * w` by
/// rounding.
#[inline(always)]
fn data_value<T: Real>(v: Complex<T>, p: Complex<T>, imflip: T) -> Complex<T> {
    let d = v * Complex::new(p.re, p.im * imflip);
    Complex::new(d.re, d.im * imflip)
}

/// Stored value per sorted visibility: the unit value (with a PSF) or the
/// data value (a dirty image alone).
fn values<T: Real>(
    setup: &Setup,
    bl: &Baselines,
    refs: &[VisRef],
    data: Option<VisData>,
    wgt: Weights,
) -> Vec<Complex<T>> {
    let nchan = bl.f_over_c.len();
    refs.par_iter()
        .map(|&r| {
            let idx = r.row as usize * nchan + r.ch as usize;
            let p = unit_value::<T>(setup, bl, r, wgt.get::<T>(idx));
            match data {
                Some(d) => {
                    let (_, imflip) = fix_w(bl.coord[r.row as usize]);
                    data_value(d.get::<T>(idx), p, T::of(imflip))
                }
                None => p,
            }
        })
        .collect()
}

// ---------------------------------------------------------------- kernels

/// Kernel coefficients split into even and odd powers (ducc0's
/// `TemplateKernel`): each tap's polynomial `p(x) = Pe(x^2) + x Po(x^2)`,
/// the degree padded to odd. Layout: `ne` rows of `W` even coefficients,
/// highest power first, then `ne` rows of odd ones (`c[k * W + i]` and
/// `c[(ne + k) * W + i]` for tap `i`), so that Horner's rule in `x^2` runs
/// across taps in fixed-size arrays the compiler vectorises.
fn coeff_even_odd<T: Real>(kernel: &EsKernel) -> Vec<T> {
    let w = kernel.support;
    let d = kernel.degree;
    let d1 = d + 1;
    let dodd = d | 1;
    let ne = dodd.div_ceil(2);
    // Coefficient of x^m of tap i (zero above the degree).
    let a = |i: usize, m: usize| {
        if m > d {
            0.0
        } else {
            kernel.coeff[i * d1 + (d - m)]
        }
    };
    let mut out = vec![T::zero(); 2 * ne * w];
    for i in 0..w {
        for k in 0..ne {
            out[k * w + i] = T::of(a(i, dodd - 1 - 2 * k));
            out[(ne + k) * w + i] = T::of(a(i, dodd - 2 * k));
        }
    }
    out
}

/// The `S` u taps at `x` and v taps at `y`. The first `ceil(S / 2)` taps
/// are evaluated by Horner's rule in `x^2` (one fused multiply-add per
/// step); the others are their mirror images (`p_{S-1-i}(x) = p_i(-x)`,
/// the kernel being symmetric), as ducc0 does.
#[inline(always)]
fn eval_taps2<T: Real, const S: usize>(c: &[T], x: T, y: T) -> ([T; S], [T; S]) {
    let h = S.div_ceil(2);
    let ne = c.len() / (2 * S);
    let (x2, y2) = (x * x, y * y);
    let first: &[T; S] = c[..S].try_into().unwrap();
    let (mut ex, mut ey) = (*first, *first);
    let firsto: &[T; S] = c[ne * S..(ne + 1) * S].try_into().unwrap();
    let (mut ox, mut oy) = (*firsto, *firsto);
    for k in 1..ne {
        let ce: &[T; S] = c[k * S..(k + 1) * S].try_into().unwrap();
        let co: &[T; S] = c[(ne + k) * S..(ne + k + 1) * S].try_into().unwrap();
        for i in 0..h {
            ex[i] = ex[i].mul_add(x2, ce[i]);
            ey[i] = ey[i].mul_add(y2, ce[i]);
            ox[i] = ox[i].mul_add(x2, co[i]);
            oy[i] = oy[i].mul_add(y2, co[i]);
        }
    }
    let mut ru = [T::zero(); S];
    let mut rv = [T::zero(); S];
    for i in 0..h {
        ru[i] = ox[i].mul_add(x, ex[i]);
        rv[i] = oy[i].mul_add(y, ey[i]);
    }
    for i in 0..S - h {
        ru[S - 1 - i] = ox[i].mul_add(-x, ex[i]);
        rv[S - 1 - i] = oy[i].mul_add(-y, ey[i]);
    }
    (ru, rv)
}

/// Tap `i` alone at `x` (the w kernel of one plane), mirrored as the u
/// and v taps.
#[inline(always)]
fn eval_tap<T: Real, const S: usize>(c: &[T], i: usize, x: T) -> T {
    let h = S.div_ceil(2);
    let (i, x) = if i < h { (i, x) } else { (S - 1 - i, -x) };
    let ne = c.len() / (2 * S);
    let x2 = x * x;
    let mut e = c[i];
    let mut o = c[ne * S + i];
    for k in 1..ne {
        e = e.mul_add(x2, c[k * S + i]);
        o = o.mul_add(x2, c[(ne + k) * S + i]);
    }
    o.mul_add(x, e)
}

/// The kernel taps of one visibility on one plane (DF1's `taps`): `ku`
/// times the w factor, `kv`, and the first taps' grid indices.
#[inline(always)]
fn taps<T: Real, const S: usize>(
    setup: &Setup,
    coeff: &[T],
    u: f64,
    v: f64,
    plane: Option<(usize, f64, f64)>,
) -> ([T; S], [T; S], i64, i64) {
    let (ufrac, vfrac, iu0, iv0) = setup.getpix(u, v);
    let x0 = T::of(-ufrac * 2.0 + (S as f64 - 1.0));
    let y0 = T::of(-vfrac * 2.0 + (S as f64 - 1.0));
    let (mut ku, kv) = eval_taps2::<T, S>(coeff, x0, y0);
    if let Some((nth, w0, w)) = plane {
        let z = T::of(setup.xdw * (w0 - w));
        let locz = (z - T::of(nth as f64)) * T::of(2.0) + T::of(S as f64 - 1.0);
        let kw = eval_tap::<T, S>(coeff, nth, locz);
        for k in ku.iter_mut() {
            *k = *k * kw;
        }
    }
    (ku, kv, iu0, iv0)
}

/// Instruction set of the gridding loops: 2 AVX-512 with FMA, 1 AVX2 with
/// FMA, 0 the build's baseline (`RANG_WGRIDDER_SIMD` = `avx512`, `avx2` or
/// `baseline` caps it). Every level performs the same IEEE operations
/// lane by lane (FMA is exactly rounded everywhere; no reductions across
/// lanes), so the results do not depend on it, only the speed.
fn simd_level() -> u8 {
    static LEVEL: std::sync::OnceLock<u8> = std::sync::OnceLock::new();
    *LEVEL.get_or_init(|| {
        let cap = match std::env::var("RANG_WGRIDDER_SIMD").as_deref() {
            Ok("baseline") => 0,
            Ok("avx2") => 1,
            _ => 2,
        };
        #[cfg(target_arch = "x86_64")]
        {
            let fma = std::is_x86_feature_detected!("fma") && std::is_x86_feature_detected!("avx2");
            let avx512 = fma
                && std::is_x86_feature_detected!("avx512f")
                && std::is_x86_feature_detected!("avx512vl");
            let level = if avx512 {
                2
            } else if fma {
                1
            } else {
                0
            };
            level.min(cap)
        }
        #[cfg(not(target_arch = "x86_64"))]
        {
            let _ = cap;
            0
        }
    })
}

/// Call `$body` (a method of `$obj` with const generic `S`) through the
/// instruction-set variant of `simd_level`.
macro_rules! simd_dispatch {
    ($obj:expr, $avx512:ident, $avx2:ident, $body:ident, $s:ident, $($arg:expr),*) => {{
        #[cfg(target_arch = "x86_64")]
        {
            match simd_level() {
                // SAFETY: the level was detected at run time.
                2 => unsafe { $obj.$avx512::<$s>($($arg),*) },
                // SAFETY: as above.
                1 => unsafe { $obj.$avx2::<$s>($($arg),*) },
                _ => $obj.$body::<$s>($($arg),*),
            }
        }
        #[cfg(not(target_arch = "x86_64"))]
        {
            $obj.$body::<$s>($($arg),*)
        }
    }};
}

// ---------------------------------------------------------------- the FFTs

struct Ffts<T: FftNum> {
    u_inv: Arc<dyn Fft<T>>,
    v_inv: Arc<dyn Fft<T>>,
    u_fwd: Arc<dyn Fft<T>>,
    v_fwd: Arc<dyn Fft<T>>,
    scratch: usize,
}

impl<T: Real> Ffts<T> {
    fn new(nu: usize, nv: usize) -> Ffts<T> {
        let mut planner = FftPlanner::<T>::new();
        let u_inv = planner.plan_fft_inverse(nu);
        let v_inv = planner.plan_fft_inverse(nv);
        let u_fwd = planner.plan_fft_forward(nu);
        let v_fwd = planner.plan_fft_forward(nv);
        let scratch = [&u_inv, &v_inv, &u_fwd, &v_fwd]
            .iter()
            .map(|f| f.get_inplace_scratch_len())
            .max()
            .unwrap_or(0);
        Ffts {
            u_inv,
            v_inv,
            u_fwd,
            v_fwd,
            scratch,
        }
    }
}

/// Columns of the grid that hold image pixels: `jx` for `j < ny`.
fn image_cols(setup: &Setup) -> Vec<usize> {
    (0..setup.ny)
        .map(|j| (setup.nv - setup.ny / 2 + j) % setup.nv)
        .collect()
}

fn image_rows(setup: &Setup) -> Vec<usize> {
    (0..setup.nx)
        .map(|i| (setup.nu - setup.nx / 2 + i) % setup.nu)
        .collect()
}

const COL_BLOCK: usize = 8;

fn czero<T: Real>() -> Complex<T> {
    Complex::new(T::zero(), T::zero())
}

/// Optional phase-timing report on stderr (`RANG_WGRIDDER_TIMING` set).
struct Timer {
    on: bool,
    t0: std::time::Instant,
    parts: Vec<(&'static str, f64)>,
}

impl Timer {
    fn new() -> Timer {
        Timer {
            on: std::env::var_os("RANG_WGRIDDER_TIMING").is_some(),
            t0: std::time::Instant::now(),
            parts: Vec::new(),
        }
    }

    fn lap(&mut self, name: &'static str) {
        if self.on {
            let now = std::time::Instant::now();
            let dt = (now - self.t0).as_secs_f64();
            match self.parts.iter_mut().find(|p| p.0 == name) {
                Some(p) => p.1 += dt,
                None => self.parts.push((name, dt)),
            }
            self.t0 = now;
        }
    }

    fn report(&self, what: &str) {
        if self.on {
            let total: f64 = self.parts.iter().map(|p| p.1).sum();
            let parts: Vec<String> = self
                .parts
                .iter()
                .map(|(n, t)| format!("{n} {t:.4}"))
                .collect();
            eprintln!("wgridder {what}: total {total:.4} s: {}", parts.join(", "));
        }
    }
}

// ---------------------------------------------------------------- vis2dirty

/// Grid rows whose v transform is needed on plane `p`: the buffer rows of
/// the tiles active there.
fn tile_rows(setup: &Setup, lay: &Layout, active: &[usize]) -> Vec<bool> {
    let mut rows = vec![false; setup.nu];
    for &ti in active {
        let base = lay.tiles[ti].tu << lay.tiling.log2;
        for i in 0..lay.tiling.su {
            rows[(base + i + setup.nu / 2) % setup.nu] = true;
        }
    }
    rows
}

/// Tiles active on plane `p`, split into the four parity classes (index
/// 0..4) and the wrapping tiles (index 4).
fn plane_tiles(setup: &Setup, lay: &Layout, p: usize) -> ([Vec<usize>; 5], Vec<usize>) {
    let mut classes: [Vec<usize>; 5] = Default::default();
    let mut all = Vec::new();
    for (i, t) in lay.tiles.iter().enumerate() {
        if setup.do_wgridding && !(t.plo <= p && p < t.phi + setup.supp) {
            continue;
        }
        all.push(i);
        let c = if t.edge {
            4
        } else {
            (t.tu & 1) * 2 + (t.tv & 1)
        };
        classes[c].push(i);
    }
    (classes, all)
}

/// Per-task tile buffers (real and imaginary parts apart, as ducc0).
struct TileBuf<T> {
    re: Vec<T>,
    im: Vec<T>,
}

impl<T: Real> TileBuf<T> {
    fn new(tiling: &Tiling) -> TileBuf<T> {
        let n = tiling.su * tiling.sv;
        TileBuf {
            re: vec![T::zero(); n],
            im: vec![T::zero(); n],
        }
    }
}

/// Grid cell index of buffer cell `(i, j)` of the tile with shifted origin
/// `(bu, bv)`.
#[inline(always)]
fn cell(setup: &Setup, bu: usize, bv: usize, i: usize, j: usize) -> usize {
    let r = (bu + i + setup.nu / 2) % setup.nu;
    let c = (bv + j + setup.nv / 2) % setup.nv;
    r * setup.nv + c
}

/// Add a tile buffer into the grid.
///
/// # Safety
/// No other task may touch the tile's cells meanwhile.
unsafe fn dump<T: Real>(
    setup: &Setup,
    tiling: &Tiling,
    t: &Tile,
    buf: &TileBuf<T>,
    grid: SyncPtr<Complex<T>>,
) {
    let (bu, bv) = (t.tu << tiling.log2, t.tv << tiling.log2);
    let sv = tiling.sv;
    let c0 = (bv + setup.nv / 2) % setup.nv;
    let contiguous = c0 + sv <= setup.nv;
    for i in 0..tiling.su {
        let re = &buf.re[i * sv..(i + 1) * sv];
        let im = &buf.im[i * sv..(i + 1) * sv];
        if contiguous {
            let start = cell(setup, bu, bv, i, 0);
            // SAFETY: the caller owns these cells for the duration.
            let row = unsafe { std::slice::from_raw_parts_mut(grid.get().add(start), sv) };
            for ((g, r), m) in row.iter_mut().zip(re.iter()).zip(im.iter()) {
                g.re = g.re + *r;
                g.im = g.im + *m;
            }
        } else {
            for j in 0..sv {
                // SAFETY: as above.
                let g = unsafe { &mut *grid.get().add(cell(setup, bu, bv, i, j)) };
                g.re = g.re + re[j];
                g.im = g.im + im[j];
            }
        }
    }
}

/// Visibilities per gridding task. Fixed, so that the summation order
/// does not depend on the number of threads.
const CHUNK: usize = 2048;

/// One task: a tile and runs `(nth, start, end)` of its visibilities on
/// one plane (`nth` = plane minus first plane), at most `CHUNK` in all.
struct Task {
    tile: usize,
    runs: Vec<(usize, usize, usize)>,
}

/// The tasks of plane `p` over `tiles`, in tile order, each tile's
/// visibilities cut into consecutive chunks.
fn plane_tasks(setup: &Setup, lay: &Layout, tiles: &[usize], p: usize) -> Vec<Task> {
    let mut tasks = Vec::new();
    for &ti in tiles {
        let t = &lay.tiles[ti];
        let mut cur = Task {
            tile: ti,
            runs: Vec::new(),
        };
        let mut n = 0;
        for b in &lay.blocks[t.blocks.0..t.blocks.1] {
            if setup.do_wgridding && !(b.minplane <= p && p < b.minplane + setup.supp) {
                continue;
            }
            let nth = if setup.do_wgridding {
                p - b.minplane
            } else {
                0
            };
            let mut s = b.start;
            while s < b.end {
                let e = b.end.min(s + CHUNK - n);
                cur.runs.push((nth, s, e));
                n += e - s;
                s = e;
                if n == CHUNK {
                    let next = Task {
                        tile: ti,
                        runs: Vec::new(),
                    };
                    tasks.push(std::mem::replace(&mut cur, next));
                    n = 0;
                }
            }
        }
        if n > 0 {
            tasks.push(cur);
        }
    }
    tasks
}

/// Add `val` times the taps to a tile buffer at offset `(ou, ov)`.
#[inline(always)]
fn accumulate<T: Real, const S: usize>(
    buf: &mut TileBuf<T>,
    val: Complex<T>,
    ku: &[T; S],
    kv: &[T; S],
    ou: usize,
    ov: usize,
    sv: usize,
) {
    for (cu, &kuc) in ku.iter().enumerate() {
        let tr = val.re * kuc;
        let ti = val.im * kuc;
        let base = (ou + cu) * sv + ov;
        let br: &mut [T; S] = (&mut buf.re[base..base + S]).try_into().unwrap();
        // Real and imaginary parts in two loops, so that each vectorises.
        for cv in 0..S {
            br[cv] = tr.mul_add(kv[cv], br[cv]);
        }
        let bi: &mut [T; S] = (&mut buf.im[base..base + S]).try_into().unwrap();
        for cv in 0..S {
            bi[cv] = ti.mul_add(kv[cv], bi[cv]);
        }
    }
}

/// Everything a gridding plane reads.
struct GridIn<'a, T: Real> {
    setup: &'a Setup,
    bl: &'a Baselines,
    lay: &'a Layout,
    /// Stored value per visibility (`values`): the only output's, or with
    /// both outputs the PSF's (the second output).
    stored: &'a [Complex<T>],
    /// With both outputs: the data, from which the dirty value (the first
    /// output) is formed per plane.
    data: Option<VisData<'a>>,
    coeff: &'a [T],
}

impl<T: Real> GridIn<'_, T> {
    /// Grid one task into `bufs` (one per output, zeroed).
    fn grid_task<const S: usize>(&self, task: &Task, w0: f64, bufs: &mut [TileBuf<T>]) {
        simd_dispatch!(
            self,
            grid_task_avx512,
            grid_task_avx2,
            grid_task_body,
            S,
            task,
            w0,
            bufs
        )
    }

    #[cfg(target_arch = "x86_64")]
    #[target_feature(enable = "avx512f,avx512vl,avx2,fma")]
    unsafe fn grid_task_avx512<const S: usize>(
        &self,
        task: &Task,
        w0: f64,
        bufs: &mut [TileBuf<T>],
    ) {
        self.grid_task_body::<S>(task, w0, bufs)
    }

    #[cfg(target_arch = "x86_64")]
    #[target_feature(enable = "avx2,fma")]
    unsafe fn grid_task_avx2<const S: usize>(&self, task: &Task, w0: f64, bufs: &mut [TileBuf<T>]) {
        self.grid_task_body::<S>(task, w0, bufs)
    }

    #[inline(always)]
    fn grid_task_body<const S: usize>(&self, task: &Task, w0: f64, bufs: &mut [TileBuf<T>]) {
        let nchan = self.bl.f_over_c.len();
        let s = self.setup;
        let lay = self.lay;
        let tiling = &lay.tiling;
        let sv = tiling.sv;
        let t = &lay.tiles[task.tile];
        let (bu, bv) = (t.tu << tiling.log2, t.tv << tiling.log2);
        for &(nth, start, end) in &task.runs {
            for k in start..end {
                let r = lay.refs[k];
                let ([u, v, w], imflip) = uvw_of(self.bl, r);
                let plane = s.do_wgridding.then_some((nth, w0, w));
                let (ku, kv, iu0, iv0) = taps::<T, S>(s, self.coeff, u, v, plane);
                let ou = offset(iu0, s.nu, bu);
                let ov = offset(iv0, s.nv, bv);
                let st = self.stored[k];
                match self.data {
                    Some(data) => {
                        let idx = r.row as usize * nchan + r.ch as usize;
                        let d = data_value(data.get::<T>(idx), st, T::of(imflip));
                        let (b0, b1) = bufs.split_at_mut(1);
                        accumulate::<T, S>(&mut b0[0], d, &ku, &kv, ou, ov, sv);
                        accumulate::<T, S>(&mut b1[0], st, &ku, &kv, ou, ov, sv);
                    }
                    None => accumulate::<T, S>(&mut bufs[0], st, &ku, &kv, ou, ov, sv),
                }
            }
        }
    }

    /// Grid plane `p` into `grids` (zeroed by the caller): per parity
    /// class, every task into its own buffer in parallel, then the buffers
    /// added to the grid tile by tile in task order (tiles of a class in
    /// parallel; wrapping tiles in order).
    fn grid_plane<const S: usize>(&self, p: usize, grids: &mut [Vec<Complex<T>>]) -> Vec<bool> {
        let s = self.setup;
        let lay = self.lay;
        let w0 = s.wmin + p as f64 * s.dw;
        let (classes, all) = plane_tiles(s, lay, p);
        let ptrs: Vec<SyncPtr<Complex<T>>> =
            grids.iter_mut().map(|g| SyncPtr(g.as_mut_ptr())).collect();
        let nout = if self.data.is_some() { 2 } else { 1 };
        for (ci, class) in classes.iter().enumerate() {
            let tasks = plane_tasks(s, lay, class, p);
            let bufs: Vec<Vec<TileBuf<T>>> = tasks
                .par_iter()
                .map(|task| {
                    let mut b: Vec<TileBuf<T>> =
                        (0..nout).map(|_| TileBuf::new(&lay.tiling)).collect();
                    self.grid_task::<S>(task, w0, &mut b);
                    b
                })
                .collect();
            let mut groups = Vec::new();
            let mut i = 0;
            while i < tasks.len() {
                let mut j = i + 1;
                while j < tasks.len() && tasks[j].tile == tasks[i].tile {
                    j += 1;
                }
                groups.push((i, j));
                i = j;
            }
            let merge = |&(a, b): &(usize, usize)| {
                for k in a..b {
                    for (buf, &grid) in bufs[k].iter().zip(&ptrs) {
                        // SAFETY: tiles of one parity class never share a
                        // cell; wrapping tiles are merged one at a time.
                        unsafe { dump(s, &lay.tiling, &lay.tiles[tasks[k].tile], buf, grid) };
                    }
                }
            };
            if ci < 4 {
                groups.par_iter().for_each(merge);
            } else {
                groups.iter().for_each(merge);
            }
        }
        tile_rows(s, lay, &all)
    }
}

/// Dispatch on the support (ducc0's `SUPP` template recursion).
macro_rules! with_supp {
    ($supp:expr, $call:ident, $obj:expr, $($arg:expr),*) => {
        match $supp {
            4 => $obj.$call::<4>($($arg),*),
            5 => $obj.$call::<5>($($arg),*),
            6 => $obj.$call::<6>($($arg),*),
            7 => $obj.$call::<7>($($arg),*),
            8 => $obj.$call::<8>($($arg),*),
            9 => $obj.$call::<9>($($arg),*),
            10 => $obj.$call::<10>($($arg),*),
            11 => $obj.$call::<11>($($arg),*),
            12 => $obj.$call::<12>($($arg),*),
            13 => $obj.$call::<13>($($arg),*),
            14 => $obj.$call::<14>($($arg),*),
            15 => $obj.$call::<15>($($arg),*),
            16 => $obj.$call::<16>($($arg),*),
            _ => unreachable!("kernel support outside 4..=16"),
        }
    };
}

/// The w-screens of one plane, per table pixel (parallel, per pixel as
/// `Setup::screen`).
fn screen_par<T: Real>(table: &[f64], w: f64, adjoint: bool, out: &mut Vec<Complex<T>>) {
    out.resize(table.len(), czero());
    out.par_iter_mut()
        .zip(table.par_iter())
        .for_each(|(o, &s)| {
            let mut phs = w * s;
            if adjoint {
                phs *= -1.0;
            }
            let ang = if T::SINGLE {
                T::of(2.0 * PI * (phs - phs.floor()))
            } else {
                T::of(2.0 * PI * phs)
            };
            let (sn, cs) = Float::sin_cos(ang);
            *o = Complex::new(cs, sn);
        });
}

/// The v transforms of the touched rows, then the u transforms of the
/// image columns, projected and added to `image` (plane order is the
/// caller's).
#[allow(clippy::too_many_arguments)]
fn grid_to_image<T: Real>(
    setup: &Setup,
    ffts: &Ffts<T>,
    grid: &mut [Complex<T>],
    touched: &[bool],
    screen: &[Complex<T>],
    rows: &[usize],
    cols: &[usize],
    image: &mut [T],
) {
    let (nu, nv, ny) = (setup.nu, setup.nv, setup.ny);
    grid.par_chunks_exact_mut(nv).enumerate().for_each_init(
        || vec![czero::<T>(); ffts.scratch],
        |scratch, (r, row)| {
            if touched[r] {
                ffts.v_inv.process_with_scratch(row, scratch);
            }
        },
    );
    let grid: &[Complex<T>] = grid;
    let (_, tny) = setup.table_dims();
    let out = SyncPtr(image.as_mut_ptr());
    cols.par_chunks(COL_BLOCK).enumerate().for_each_init(
        || {
            (
                vec![czero::<T>(); nu * COL_BLOCK],
                vec![czero::<T>(); ffts.scratch],
            )
        },
        |(colbuf, scratch), (block, jblock)| {
            for (c, &jx) in jblock.iter().enumerate() {
                let col = &mut colbuf[c * nu..(c + 1) * nu];
                for (r, value) in col.iter_mut().enumerate() {
                    *value = grid[r * nv + jx];
                }
                ffts.u_inv.process_with_scratch(col, scratch);
            }
            for c in 0..jblock.len() {
                let j = block * COL_BLOCK + c;
                for (i, &ix) in rows.iter().enumerate() {
                    let g = colbuf[c * nu + ix];
                    let term = if setup.do_wgridding {
                        let ph = screen[setup.table_index(i, j, tny)];
                        g.re * ph.re - g.im * ph.im
                    } else {
                        g.re
                    };
                    // SAFETY: each task writes its own columns `j`.
                    unsafe {
                        let d = out.get().add(i * ny + j);
                        *d = *d + term;
                    }
                }
            }
        },
    );
}

/// Global corrections of a finished image (`apply_global_corrections` or
/// `grid2dirty_post`), in place, per pixel.
fn correct_image<T: Real>(
    setup: &Setup,
    image: &mut [T],
    corr: &[f64],
    cfuv: &(Vec<f64>, Vec<f64>),
) {
    let (nx, ny) = (setup.nx, setup.ny);
    let (_, tny) = setup.table_dims();
    image
        .par_chunks_exact_mut(ny)
        .enumerate()
        .for_each(|(i, row)| {
            if setup.do_wgridding {
                for (j, d) in row.iter_mut().enumerate() {
                    let f = corr[setup.table_index(i, j, tny)];
                    *d = *d * T::of(f);
                }
            } else {
                let iu = nx / 2 - i.min(nx - i);
                for (j, d) in row.iter_mut().enumerate() {
                    let iv = ny / 2 - j.min(ny - j);
                    *d = T::of(d.to() * cfuv.0[iu] * cfuv.1[iv]);
                }
            }
        });
}

/// `vis2dirty` with borrowed inputs and an optional PSF in the same pass:
/// `dirty` grids `data`, `psf` grids unit visibilities, both with the
/// weights `wgt` and the mask. With a PSF both use the plan of the PSF's
/// active set (`wgt mask != 0`); a dirty image alone uses
/// `|vis|^2 wgt mask != 0` as ducc0. At least one output is required.
#[allow(clippy::too_many_arguments)]
pub fn vis2dirty_multi<T: Real>(
    opts: &Options,
    uvw: &[f64],
    freq: &[f64],
    data: VisData,
    wgt: Weights,
    mask: Option<&[u8]>,
    mut dirty: Option<&mut [T]>,
    mut psf: Option<&mut [T]>,
) -> Result<Plan, String> {
    let mut timer = Timer::new();
    let nchan = freq.len();
    let nrow = uvw.len() / 3;
    check_common(opts, nrow, nchan, uvw)?;
    let n = nrow * nchan;
    if (dirty.is_none() && psf.is_none())
        || data.len().is_some_and(|l| l != n)
        || wgt.len().is_some_and(|l| l != n)
        || mask.is_some_and(|m| m.len() != n)
        || dirty.as_ref().is_some_and(|d| d.len() != opts.nx * opts.ny)
        || psf.as_ref().is_some_and(|d| d.len() != opts.nx * opts.ny)
    {
        return Err("array lengths disagree".into());
    }
    let (r_l, r_m) = recentring(opts);
    let flips = [opts.flip_u, opts.flip_v, !opts.flip_w];
    let bl = Baselines::new(uvw, freq, flips, r_l, r_m)?;
    let act = Activity {
        vis: if psf.is_some() { None } else { Some(data) },
        wgt,
        mask,
    };
    let (nvis, wmin_d, wmax_d) = scan::<T>(&bl, &act);
    for out in [dirty.as_deref_mut(), psf.as_deref_mut()]
        .into_iter()
        .flatten()
    {
        out.fill(T::zero());
    }
    if nvis == 0 {
        return Ok(Plan::default());
    }
    let setup = Setup::new::<T>(opts, nvis, wmin_d, wmax_d, r_l, r_m, true)?;
    timer.lap("scan");
    let lay = layout::<T>(&setup, &bl, &act);
    timer.lap("layout");
    // A dirty image alone stores data values; a PSF (alone or with the
    // dirty image) stores unit values, the dirty value formed per plane.
    let both = dirty.is_some() && psf.is_some();
    let stored_data = (psf.is_none()).then_some(data);
    let stored = values::<T>(&setup, &bl, &lay.refs, stored_data, wgt);
    timer.lap("values");
    let ffts = Ffts::<T>::new(setup.nu, setup.nv);
    let coeff = coeff_even_odd::<T>(&setup.kernel);
    let table = if setup.do_wgridding {
        setup.screen_table()
    } else {
        Vec::new()
    };
    let rows = image_rows(&setup);
    let cols = image_cols(&setup);
    let input = GridIn {
        setup: &setup,
        bl: &bl,
        lay: &lay,
        stored: &stored,
        data: both.then_some(data),
        coeff: &coeff,
    };
    let mut images: Vec<&mut [T]> = [dirty.as_deref_mut(), psf.as_deref_mut()]
        .into_iter()
        .flatten()
        .collect();
    let mut grids: Vec<Vec<Complex<T>>> = (0..images.len())
        .map(|_| vec![czero::<T>(); setup.nu * setup.nv])
        .collect();
    let mut screen = Vec::new();
    timer.lap("setup");
    for p in 0..setup.nplanes.max(1) {
        if setup.do_wgridding
            && !lay
                .tiles
                .iter()
                .any(|t| t.plo <= p && p < t.phi + setup.supp)
        {
            continue;
        }
        for g in grids.iter_mut() {
            g.par_chunks_mut(setup.nv).for_each(|r| r.fill(czero()));
        }
        timer.lap("zero");
        let touched = with_supp!(setup.supp, grid_plane, input, p, &mut grids);
        timer.lap("grid");
        let w0 = setup.wmin + p as f64 * setup.dw;
        if setup.do_wgridding {
            screen_par(&table, w0, true, &mut screen);
        }
        timer.lap("screen");
        for (g, img) in grids.iter_mut().zip(images.iter_mut()) {
            grid_to_image(&setup, &ffts, g, &touched, &screen, &rows, &cols, img);
        }
        timer.lap("fft");
    }
    drop(grids);
    let corr = if setup.do_wgridding {
        setup.global_corrections()
    } else {
        Vec::new()
    };
    let cfuv = if setup.do_wgridding {
        (Vec::new(), Vec::new())
    } else {
        setup.uv_corrections()
    };
    for img in images.iter_mut() {
        correct_image(&setup, img, &corr, &cfuv);
    }
    timer.lap("corrections");
    timer.report("vis2dirty");
    Ok(setup.plan)
}

/// `vis2dirty`: visibilities `vis` (`nrow * nchan`, row-major) with optional
/// weights and mask to the dirty image `dirty` (`nx * ny`, first axis l).
#[allow(clippy::too_many_arguments)]
pub fn vis2dirty<T: Real>(
    opts: &Options,
    uvw: &[f64],
    freq: &[f64],
    vis: &[Complex<T>],
    wgt: Option<&[T]>,
    mask: Option<&[u8]>,
    dirty: &mut [T],
) -> Result<Plan, String> {
    vis2dirty_multi(
        opts,
        uvw,
        freq,
        T::vis_data(vis),
        wgt.map_or(Weights::None, T::weights),
        mask,
        Some(dirty),
        None,
    )
}

// ---------------------------------------------------------------- dirty2vis

/// Everything a degridding plane reads.
struct DegridIn<'a, T: Real> {
    setup: &'a Setup,
    bl: &'a Baselines,
    lay: &'a Layout,
    coeff: &'a [T],
}

impl<T: Real> DegridIn<'_, T> {
    /// Add plane `p`'s contribution to every visibility it touches (`out`
    /// in visibility order; each visibility is written by one task).
    fn degrid_plane<const S: usize>(
        &self,
        p: usize,
        grid: &[Complex<T>],
        out: SyncPtr<Complex<T>>,
    ) {
        let s = self.setup;
        let lay = self.lay;
        let tiling = &lay.tiling;
        let w0 = s.wmin + p as f64 * s.dw;
        let (_, all) = plane_tiles(s, lay, p);
        let tasks = plane_tasks(s, lay, &all, p);
        tasks.par_iter().for_each_init(
            || TileBuf::<T>::new(tiling),
            |buf, task| self.degrid_task::<S>(task, w0, grid, buf, out),
        );
    }

    /// Degrid one task, adding to `out`.
    fn degrid_task<const S: usize>(
        &self,
        task: &Task,
        w0: f64,
        grid: &[Complex<T>],
        buf: &mut TileBuf<T>,
        out: SyncPtr<Complex<T>>,
    ) {
        simd_dispatch!(
            self,
            degrid_task_avx512,
            degrid_task_avx2,
            degrid_task_body,
            S,
            task,
            w0,
            grid,
            buf,
            out
        )
    }

    #[cfg(target_arch = "x86_64")]
    #[target_feature(enable = "avx512f,avx512vl,avx2,fma")]
    unsafe fn degrid_task_avx512<const S: usize>(
        &self,
        task: &Task,
        w0: f64,
        grid: &[Complex<T>],
        buf: &mut TileBuf<T>,
        out: SyncPtr<Complex<T>>,
    ) {
        self.degrid_task_body::<S>(task, w0, grid, buf, out)
    }

    #[cfg(target_arch = "x86_64")]
    #[target_feature(enable = "avx2,fma")]
    unsafe fn degrid_task_avx2<const S: usize>(
        &self,
        task: &Task,
        w0: f64,
        grid: &[Complex<T>],
        buf: &mut TileBuf<T>,
        out: SyncPtr<Complex<T>>,
    ) {
        self.degrid_task_body::<S>(task, w0, grid, buf, out)
    }

    #[inline(always)]
    fn degrid_task_body<const S: usize>(
        &self,
        task: &Task,
        w0: f64,
        grid: &[Complex<T>],
        buf: &mut TileBuf<T>,
        out: SyncPtr<Complex<T>>,
    ) {
        let s = self.setup;
        let lay = self.lay;
        let tiling = &lay.tiling;
        let (su, sv) = (tiling.su, tiling.sv);
        let nchan = self.bl.f_over_c.len();
        let ti = task.tile;
        let t = &lay.tiles[ti];
        let (bu, bv) = (t.tu << tiling.log2, t.tv << tiling.log2);
        for i in 0..su {
            for j in 0..sv {
                let g = grid[cell(s, bu, bv, i, j)];
                buf.re[i * sv + j] = g.re;
                buf.im[i * sv + j] = g.im;
            }
        }
        for &(nth, start, end) in &task.runs {
            for k in start..end {
                let r = lay.refs[k];
                let ([u, v, w], imflip) = uvw_of(self.bl, r);
                let plane = s.do_wgridding.then_some((nth, w0, w));
                let (ku, kv, iu0, iv0) = taps::<T, S>(s, self.coeff, u, v, plane);
                let ou = offset(iu0, s.nu, bu);
                let ov = offset(iv0, s.nv, bv);
                let mut rr = T::zero();
                let mut ri = T::zero();
                for (cu, &kuc) in ku.iter().enumerate() {
                    let base = (ou + cu) * sv + ov;
                    let gr: &[T; S] = (&buf.re[base..base + S]).try_into().unwrap();
                    let gi: &[T; S] = (&buf.im[base..base + S]).try_into().unwrap();
                    let mut tr = T::zero();
                    let mut tim = T::zero();
                    for cv in 0..S {
                        tr = kv[cv].mul_add(gr[cv], tr);
                        tim = kv[cv].mul_add(gi[cv], tim);
                    }
                    rr = kuc.mul_add(tr, rr);
                    ri = kuc.mul_add(tim, ri);
                }
                let c = Complex::new(rr, ri * T::of(imflip));
                let idx = r.row as usize * nchan + r.ch as usize;
                // SAFETY: each visibility belongs to one tile.
                unsafe {
                    let o = out.get().add(idx);
                    *o = c + *o;
                }
            }
        }
    }
}

/// The corrected image placed on the grid with this plane's w-screen,
/// transformed along u for the image columns, then along v for `needed`
/// rows.
#[allow(clippy::too_many_arguments)]
fn image_to_grid<T: Real>(
    setup: &Setup,
    ffts: &Ffts<T>,
    image: &[T],
    screen: &[Complex<T>],
    inv_rows: &[usize],
    cols: &[usize],
    needed: &[bool],
    grid: &mut [Complex<T>],
) {
    let (nu, nv, ny) = (setup.nu, setup.nv, setup.ny);
    let (_, tny) = setup.table_dims();
    grid.par_chunks_exact_mut(nv)
        .enumerate()
        .for_each(|(r, row)| {
            row.fill(czero());
            let i = inv_rows[r];
            if i != usize::MAX {
                for (j, &jx) in cols.iter().enumerate() {
                    let d = image[i * ny + j];
                    row[jx] = if setup.do_wgridding {
                        let ph = screen[setup.table_index(i, j, tny)];
                        Complex::new(d * ph.re, d * ph.im)
                    } else {
                        Complex::new(d, T::zero())
                    };
                }
            }
        });
    let g = SyncPtr(grid.as_mut_ptr());
    cols.par_chunks(COL_BLOCK).for_each_init(
        || (vec![czero::<T>(); nu], vec![czero::<T>(); ffts.scratch]),
        |(col, scratch), jblock| {
            for &jx in jblock {
                // SAFETY: each task reads and writes its own columns `jx`.
                unsafe {
                    for (r, value) in col.iter_mut().enumerate() {
                        *value = *g.get().add(r * nv + jx);
                    }
                    ffts.u_fwd.process_with_scratch(col, scratch);
                    for (r, value) in col.iter().enumerate() {
                        *g.get().add(r * nv + jx) = *value;
                    }
                }
            }
        },
    );
    grid.par_chunks_exact_mut(nv).enumerate().for_each_init(
        || vec![czero::<T>(); ffts.scratch],
        |scratch, (r, row)| {
            if needed[r] {
                ffts.v_fwd.process_with_scratch(row, scratch);
            }
        },
    );
}

/// `dirty2vis` with borrowed weights: the image `dirty` (`nx * ny`, first
/// axis l) to visibilities `vis` (`nrow * nchan`), times the weights; zero
/// where the weight or mask is zero.
#[allow(clippy::too_many_arguments)]
pub fn dirty2vis_multi<T: Real>(
    opts: &Options,
    uvw: &[f64],
    freq: &[f64],
    dirty: &[T],
    wgt: Weights,
    mask: Option<&[u8]>,
    vis: &mut [Complex<T>],
) -> Result<Plan, String> {
    let mut timer = Timer::new();
    let nchan = freq.len();
    let nrow = uvw.len() / 3;
    check_common(opts, nrow, nchan, uvw)?;
    let n = nrow * nchan;
    if vis.len() != n
        || wgt.len().is_some_and(|l| l != n)
        || mask.is_some_and(|m| m.len() != n)
        || dirty.len() != opts.nx * opts.ny
    {
        return Err("array lengths disagree".into());
    }
    let (r_l, r_m) = recentring(opts);
    let flips = [opts.flip_u, opts.flip_v, !opts.flip_w];
    let bl = Baselines::new(uvw, freq, flips, r_l, r_m)?;
    let act = Activity {
        vis: None,
        wgt,
        mask,
    };
    let (nvis, wmin_d, wmax_d) = scan::<T>(&bl, &act);
    vis.par_iter_mut().for_each(|v| *v = czero());
    if nvis == 0 {
        return Ok(Plan::default());
    }
    let setup = Setup::new::<T>(opts, nvis, wmin_d, wmax_d, r_l, r_m, false)?;
    timer.lap("scan");
    let lay = layout::<T>(&setup, &bl, &act);
    timer.lap("layout");
    let (nx, ny) = (setup.nx, setup.ny);
    // The corrected copy of the image (dirty2grid_pre / apply_global_corrections).
    let mut image: Vec<T> = dirty.to_vec();
    let corr = if setup.do_wgridding {
        setup.global_corrections()
    } else {
        Vec::new()
    };
    let (_, tny) = setup.table_dims();
    let cfuv = if setup.do_wgridding {
        (Vec::new(), Vec::new())
    } else {
        setup.uv_corrections()
    };
    image
        .par_chunks_exact_mut(ny)
        .enumerate()
        .for_each(|(i, row)| {
            if setup.do_wgridding {
                for (j, d) in row.iter_mut().enumerate() {
                    *d = *d * T::of(corr[setup.table_index(i, j, tny)]);
                }
            } else {
                let iu = nx / 2 - i.min(nx - i);
                for (j, d) in row.iter_mut().enumerate() {
                    let iv = ny / 2 - j.min(ny - j);
                    *d = *d * T::of(cfuv.0[iu] * cfuv.1[iv]);
                }
            }
        });
    let ffts = Ffts::<T>::new(setup.nu, setup.nv);
    let coeff = coeff_even_odd::<T>(&setup.kernel);
    let table = if setup.do_wgridding {
        setup.screen_table()
    } else {
        Vec::new()
    };
    let rows = image_rows(&setup);
    let mut inv_rows = vec![usize::MAX; setup.nu];
    for (i, &ix) in rows.iter().enumerate() {
        inv_rows[ix] = i;
    }
    let cols = image_cols(&setup);
    let input = DegridIn {
        setup: &setup,
        bl: &bl,
        lay: &lay,
        coeff: &coeff,
    };
    let mut grid = vec![czero::<T>(); setup.nu * setup.nv];
    let mut screen = Vec::new();
    let out = SyncPtr(vis.as_mut_ptr());
    timer.lap("setup");
    for p in 0..setup.nplanes.max(1) {
        let (_, all) = plane_tiles(&setup, &lay, p);
        if all.is_empty() {
            continue;
        }
        let needed = tile_rows(&setup, &lay, &all);
        let w0 = setup.wmin + p as f64 * setup.dw;
        if setup.do_wgridding {
            screen_par(&table, w0, false, &mut screen);
        }
        timer.lap("screen");
        image_to_grid(
            &setup, &ffts, &image, &screen, &inv_rows, &cols, &needed, &mut grid,
        );
        timer.lap("fft");
        with_supp!(setup.supp, degrid_plane, input, p, &grid, out);
        timer.lap("degrid");
    }
    let nchan = bl.f_over_c.len();
    lay.refs.par_iter().for_each(|&r| {
        let idx = r.row as usize * nchan + r.ch as usize;
        let twgt = wgt.get::<T>(idx).unwrap_or(T::one());
        // SAFETY: each visibility index appears once in `refs`.
        unsafe {
            let o = out.get().add(idx);
            *o = if setup.shifting {
                let ph = shift_phase::<T>(&setup, &bl, r, -1.0);
                *o * Complex::new(ph.re * twgt, ph.im * twgt)
            } else {
                *o * twgt
            };
        }
    });
    timer.lap("phases");
    timer.report("dirty2vis");
    Ok(setup.plan)
}

/// `dirty2vis`: the image `dirty` (`nx * ny`, first axis l) to visibilities
/// `vis` (`nrow * nchan`), times the optional weights; zero where the
/// weight or mask is zero.
#[allow(clippy::too_many_arguments)]
pub fn dirty2vis<T: Real>(
    opts: &Options,
    uvw: &[f64],
    freq: &[f64],
    dirty: &[T],
    wgt: Option<&[T]>,
    mask: Option<&[u8]>,
    vis: &mut [Complex<T>],
) -> Result<Plan, String> {
    dirty2vis_multi(
        opts,
        uvw,
        freq,
        dirty,
        wgt.map_or(Weights::None, T::weights),
        mask,
        vis,
    )
}

/// The kernel and grid the gridder would choose, without gridding.
#[allow(clippy::too_many_arguments)]
pub fn plan<T: Real>(
    opts: &Options,
    uvw: &[f64],
    freq: &[f64],
    vis: Option<&[Complex<T>]>,
    wgt: Option<&[T]>,
    mask: Option<&[u8]>,
) -> Result<Plan, String> {
    let nchan = freq.len();
    let nrow = uvw.len() / 3;
    check_common(opts, nrow, nchan, uvw)?;
    let (r_l, r_m) = recentring(opts);
    let flips = [opts.flip_u, opts.flip_v, !opts.flip_w];
    let bl = Baselines::new(uvw, freq, flips, r_l, r_m)?;
    let act = Activity {
        vis: vis.map(T::vis_data),
        wgt: wgt.map_or(Weights::None, T::weights),
        mask,
    };
    let (nvis, wmin_d, wmax_d) = scan::<T>(&bl, &act);
    if nvis == 0 {
        return Ok(Plan::default());
    }
    Ok(Setup::new::<T>(opts, nvis, wmin_d, wmax_d, r_l, r_m, vis.is_some())?.plan)
}

// ------------------------------------------------------------- KernelDB data

/// ducc0 0.42.0 `KernelDB` rows with ndim 2 and 3, verbatim from
/// `src/ducc0/math/gridding_kernel.cc` at tag `ducc0_0_42_0` (braces made
/// parentheses): `(W, ofactor, epsilon, beta, e0, ndim, singleprec)`.
/// SHA256 of the rows' text, one per line: recorded in
/// `research/df1-wgridder.md` (criterion 5).
#[rustfmt::skip]
#[allow(clippy::excessive_precision, clippy::approx_constant)]
const KERNEL_ROWS: &[(usize, f64, f64, f64, f64, usize, bool)] = &[
// KERNEL_ROWS_BEGIN
(4, 1.20,   0.027638471, 1.30709338717990464, 0.588199361165364421, 2,  true),
(4, 1.25,   0.017179163, 1.33188061184353357, 0.594018046061197902, 2,  true),
(4, 1.30,   0.011473319, 1.36280729505750875, 0.596257019042968683, 2,  true),
(4, 1.35,  0.0085024842, 1.38681869506835920, 0.598430379231771004, 2,  true),
(4, 1.40,  0.0066874095, 1.42907129923502607, 0.595376586914062478, 2,  true),
(4, 1.45,  0.0056239728, 1.48220782809787344, 0.588401285807291785, 2,  true),
(4, 1.50,  0.0047698072, 1.55200220743815076, 0.577678934733072857, 2,  true),
(4, 1.55,  0.0040717361, 1.61562355889214393, 0.568545023600260491, 2,  true),
(4, 1.60,  0.0034281853, 1.66557473076714380, 0.562941996256510202, 2,  true),
(4, 1.65,  0.0029479114, 1.70882788764105853, 0.558200836181640403, 2,  true),
(4, 1.70,   0.002512611, 1.75829043918185701, 0.552664438883463616, 2,  true),
(4, 1.75,  0.0021231746, 1.78472069634331620, 0.551698048909505245, 2,  true),
(4, 1.80,   0.001819194, 1.81566416422526022, 0.549645741780599106, 2,  true),
(4, 1.85,  0.0015552516, 1.82287784152560750, 0.551604970296223796, 2,  true),
(4, 1.90,  0.0013487471, 1.84992726643880223, 0.550009918212890803, 2,  true),
(4, 1.95,  0.0011799293, 1.88333621554904518, 0.547602589925130112, 2,  true),
(4, 2.00,   0.001038997, 1.90694291856553799, 0.546800994873046786, 2,  true),
(4, 2.05, 0.00094331549, 1.92870330810546897, 0.545942433675130068, 2,  true),
(4, 2.10, 0.00086063741, 1.94683447943793375, 0.545642852783203014, 2,  true),
(4, 2.15, 0.00079978431, 1.95983327229817705, 0.545700836181640558, 2,  true),
(4, 2.20,  0.0007352812, 1.97344377305772567, 0.546037038167317745, 2,  true),
(4, 2.25, 0.00068776638, 1.98338402642144063, 0.546487172444661384, 2,  true),
(4, 2.30, 0.00064537642, 1.99225379096137201, 0.547050221761067768, 2,  true),
(4, 2.35, 0.00060763777, 2.00018734402126697, 0.547697194417317679, 2,  true),
(4, 2.40, 0.00058055746, 2.00592770046658009, 0.548258209228515314, 2,  true),
(4, 2.45, 0.00055028377, 2.01244015163845535, 0.548992156982421986, 2,  true),
(4, 2.50,  0.0005287527, 2.01718461778428892, 0.549589284261067679, 2,  true),
(5, 1.20,  0.0091081213, 1.47271143595377563, 0.547661844889323124, 2,  true),
(5, 1.25,  0.0051393036, 1.51477381388346322, 0.547609456380208193, 2,  true),
(5, 1.30,  0.0029950485, 1.56042251586914049, 0.546399434407552009, 2,  true),
(5, 1.35,  0.0018668854, 1.59968931410047732, 0.545594278971354263, 2,  true),
(5, 1.40,  0.0011678541, 1.62376225789388040, 0.547126770019531361, 2,  true),
(5, 1.45, 0.00083949653, 1.67027257283528652, 0.544658406575520782, 2,  true),
(5, 1.50, 0.00064510114, 1.71065928141276036, 0.543058522542317568, 2,  true),
(5, 1.55, 0.00051838121, 1.74115142822265612, 0.542447662353515714, 2,  true),
(5, 1.60, 0.00042394497, 1.76781667073567705, 0.542211151123046964, 2,  true),
(5, 1.65, 0.00036339906, 1.80731658935546857, 0.539609527587890825, 2,  true),
(5, 1.70, 0.00030426196, 1.83974456787109331, 0.537987009684244954, 2,  true),
(5, 1.75, 0.00024801871, 1.87821875678168393, 0.535735321044921831, 2,  true),
(5, 1.80, 0.00020379638, 1.92916208902994835, 0.531913503011067768, 2,  true),
(5, 1.85, 0.00017221407, 1.97668134901258674, 0.528661346435546742, 2,  true),
(5, 1.90, 0.00015103689, 2.01164194742838554, 0.526721445719401160, 2,  true),
(5, 1.95, 0.00013246567, 2.04016469319661509, 0.525634002685546831, 2,  true),
(5, 2.00,  0.0001160673, 2.06404741075303821, 0.525147755940755356, 2,  true),
(5, 2.05, 0.00010362875, 2.08155195448133679, 0.525099436442057366, 2,  true),
(5, 2.10, 9.2543096e-05, 2.09675140380859348, 0.525319671630859353, 2,  true),
(5, 2.15,  8.431446e-05, 2.10787777370876706, 0.525670623779296853, 2,  true),
(5, 2.20, 7.5533655e-05, 2.11950395372178768, 0.526264699300130090, 2,  true),
(5, 2.25, 6.9114106e-05, 2.12779930962456554, 0.526887766520182321, 2,  true),
(5, 2.30, 6.3452285e-05, 2.13487870958116410, 0.527610015869140359, 2,  true),
(5, 2.35,  5.852956e-05, 2.14067128499348991, 0.528427378336588482, 2,  true),
(5, 2.40, 5.5120029e-05, 2.14426320393880232, 0.529153188069661606, 2,  true),
(5, 2.45, 5.1575852e-05, 2.14864959716796866, 0.530002593994140625, 2,  true),
(5, 2.50, 4.9135627e-05, 2.15946265326605946, 0.529833730061848529, 2,  true),
(6, 1.20,  0.0018267494, 1.48702875773111987, 0.543441772460937278, 2,  true),
(6, 1.25,  0.0010812568, 1.55846243964301179, 0.538631693522135246, 2,  true),
(6, 1.30, 0.00063328686, 1.62978795369466178, 0.533901977539062544, 2,  true),
(6, 1.35, 0.00038126795, 1.67900339762369777, 0.531911468505859464, 2,  true),
(6, 1.40, 0.00022540405, 1.72446373833550348, 0.530658213297526271, 2,  true),
(6, 1.45, 0.00015329233, 1.77476925320095469, 0.528379058837890714, 2,  true),
(6, 1.50, 0.00011089008, 1.81697709825303821, 0.527150217692057388, 2,  true),
(6, 1.55, 8.3901712e-05, 1.84778255886501697, 0.526968638102213394, 2,  true),
(6, 1.60, 6.4776566e-05, 1.87210167778862835, 0.527448781331380290, 2,  true),
(6, 1.65, 5.3697783e-05, 1.89141523573133630, 0.527762095133463505, 2,  true),
(6, 1.70, 4.4299041e-05, 1.93276146782769054, 0.525681813557942856, 2,  true),
(6, 1.75, 3.5391822e-05, 1.96848670111762192, 0.524261728922526204, 2,  true),
(6, 1.80, 2.8212779e-05, 1.99691992865668366, 0.523411814371744888, 2,  true),
(6, 1.85, 2.1992397e-05, 2.02382388644748223, 0.522790781656901182, 2,  true),
(6, 1.90, 1.8350135e-05, 2.06700524224175330, 0.520410919189453147, 2,  true),
(6, 1.95, 1.5972068e-05, 2.08590850830078134, 0.520696258544921631, 2,  true),
(6, 2.00, 1.3859999e-05, 2.10745629204644125, 0.520621490478515692, 2,  true),
(6, 2.05, 1.2116191e-05, 2.13673621283637205, 0.519232940673827970, 2,  true),
(6, 2.10, 1.0516966e-05, 2.16247270372178901, 0.518196360270182232, 2,  true),
(6, 2.15, 9.3851633e-06, 2.17432640923394116, 0.518426767985025960, 2,  true),
(6, 2.20, 8.1990803e-06, 2.18673960367838571, 0.518857574462890714, 2,  true),
(6, 2.25, 7.3319484e-06, 2.19571753607855902, 0.519317881266276093, 2,  true),
(6, 2.30, 6.5752637e-06, 2.20337880452473955, 0.519864654541015603, 2,  true),
(6, 2.35, 5.9298948e-06, 2.20968983968098920, 0.520482126871744888, 2,  true),
(6, 2.40, 5.4904875e-06, 2.21353166368272536, 0.521029408772786695, 2,  true),
(6, 2.45, 5.0308227e-06, 2.23052520751953054, 0.520584869384765669, 2,  true),
(6, 2.50,  4.625964e-06, 2.25309499104817679, 0.519467417399088638, 2,  true),
(7, 1.20,  0.0007571742, 1.57580659654405375, 0.528578694661458459, 2,  true),
(7, 1.25,  0.0003367945, 1.63487184312608536, 0.526731363932291696, 2,  true),
(7, 1.30, 0.00017840443, 1.68659379747178795, 0.525407663981120043, 2,  true),
(7, 1.35, 0.00010456205, 1.73841366238064232, 0.523535919189453192, 2,  true),
(7, 1.40, 5.9581163e-05, 1.78485124376085036, 0.522390492757161540, 2,  true),
(7, 1.45, 3.5499217e-05, 1.81957685682508630, 0.522037506103515625, 2,  true),
(7, 1.50,  2.341159e-05, 1.87820756700303804, 0.519385019938150894, 2,  true),
(7, 1.55, 1.6709902e-05, 1.91922556559244817, 0.518272145589192657, 2,  true),
(7, 1.60, 1.2162659e-05, 1.95363786485460023, 0.517866770426432477, 2,  true),
(7, 1.65, 9.3333251e-06, 1.97871042887369786, 0.517832692464192723, 2,  true),
(7, 1.70, 7.2180318e-06, 2.00276845296223982, 0.517857615152994666, 2,  true),
(7, 1.75, 5.6180048e-06, 2.02892269558376759, 0.517637888590494311, 2,  true),
(7, 1.80, 4.4823027e-06, 2.06023915608723929, 0.516692860921223907, 2,  true),
(7, 1.85, 3.6615236e-06, 2.09614715576171839, 0.515417734781901116, 2,  true),
(7, 1.90, 3.1044253e-06, 2.09791141086154465, 0.517407989501953436, 2,  true),
(7, 1.95, 2.6579785e-06, 2.11293928358289929, 0.518028004964192657, 2,  true),
(7, 2.00,  2.292283e-06, 2.13445349799262107, 0.517974090576171942, 2,  true),
(7, 2.05, 2.0048563e-06, 2.20160708957248241, 0.512737274169921653, 2,  true),
(7, 2.10, 1.7431904e-06, 2.22028656005859348, 0.512581634521484086, 2,  true),
(7, 2.15, 1.5434754e-06, 2.23297949896918402, 0.512734731038411162, 2,  true),
(7, 2.20, 1.3478827e-06, 2.24713083902994715, 0.512998199462890270, 2,  true),
(7, 2.25, 1.2005263e-06, 2.25832807752821108, 0.513249460856119444, 2,  true),
(7, 2.30, 1.0711768e-06, 2.26957007514105769, 0.513472747802734553, 2,  true),
(7, 2.35,  9.585121e-07, 2.28155059814453098, 0.513612620035807321, 2,  true),
(7, 2.40, 8.7454818e-07, 2.29392649332682330, 0.513477325439453236, 2,  true),
(7, 2.45, 7.9380344e-07, 2.30712670220269001, 0.513562774658203103, 2,  true),
(7, 2.50, 7.3427447e-07, 2.31122216118706580, 0.514211273193359131, 2,  true),
(8, 1.20, 0.00073262844, 1.66550945705837661, 0.516498819986978996, 2,  true),
(8, 1.25, 0.00026113174, 1.71241234673394072, 0.516673533121744799, 2,  true),
(8, 1.30,  0.0001097567, 1.74426591661241281, 0.518212127685547030, 2,  true),
(8, 1.35, 5.7327797e-05, 1.78767852783203129, 0.517631785074869954, 2,  true),
(8, 1.40, 3.1679034e-05, 1.83155364990234371, 0.516968027750650871, 2,  true),
(8, 1.45, 1.9085793e-05, 1.87205691867404500, 0.516137440999349106, 2,  true),
(8, 1.50, 1.2356395e-05, 1.92130686442057286, 0.514534759521484197, 2,  true),
(8, 1.55, 8.3078466e-06, 1.96372358534071156, 0.513400522867838327, 2,  true),
(8, 1.60, 5.9643915e-06, 2.00066104465060768, 0.512841542561849106, 2,  true),
(8, 1.65, 4.4710511e-06, 2.02756873236762081, 0.512707773844401027, 2,  true),
(8, 1.70, 3.4523033e-06, 2.05249209933810794, 0.512742869059244599, 2,  true),
(8, 1.75, 2.7373352e-06, 2.07740800645616330, 0.512746938069661429, 2,  true),
(8, 1.80, 2.2109254e-06, 2.10268198649088545, 0.512466684977213371, 2,  true),
(8, 1.85, 1.8013756e-06, 2.13499806722005214, 0.511604054768880157, 2,  true),
(8, 1.90, 1.5252763e-06, 2.16502397325303830, 0.510731252034505090, 2,  true),
(8, 1.95, 1.3043269e-06, 2.19154747856987875, 0.510195668538411362, 2,  true),
(8, 2.00, 1.1225258e-06, 2.21735483805338607, 0.509709421793619666, 2,  true),
(8, 2.05,  9.913048e-07, 2.23568742540147580, 0.509645334879556988, 2,  true),
(8, 2.10, 8.7847996e-07, 2.25366193983290009, 0.509593963623046542, 2,  true),
(8, 2.15,  7.863896e-07, 2.26725006103515625, 0.509669240315754779, 2,  true),
(8, 2.20, 7.1103723e-07, 2.28289710150824599, 0.509803517659505046, 2,  true),
(8, 2.25,  6.487745e-07, 2.29611223008897580, 0.509888966878255023, 2,  true),
(8, 2.30,  5.937697e-07, 2.31027103000217027, 0.509893544514973596, 2,  true),
(8, 2.35, 5.4509224e-07, 2.32824554443359366, 0.509586842854817479, 2,  true),
(8, 2.40, 5.0481753e-07, 2.34016638861762161, 0.509583791097005245, 2,  true),
(8, 2.45, 4.7251724e-07, 2.35166948106553786, 0.509892018636067701, 2,  true),
(8, 2.50, 4.4514883e-07, 2.35677575005425410, 0.510489654541015692, 2,  true),
(4, 1.20,    0.04150764, 1.30709338717990464, 0.588199361165364421, 3,  true),
(4, 1.25,   0.025790962, 1.33188061184353357, 0.594018046061197902, 3,  true),
(4, 1.30,   0.017221092, 1.36280729505750875, 0.596257019042968683, 3,  true),
(4, 1.35,   0.012760142, 1.38681869506835920, 0.598430379231771004, 3,  true),
(4, 1.40,   0.010034843, 1.42907129923502607, 0.595376586914062478, 3,  true),
(4, 1.45,  0.0084382415, 1.48220782809787344, 0.588401285807291785, 3,  true),
(4, 1.50,  0.0071561917, 1.55200220743815076, 0.577678934733072857, 3,  true),
(4, 1.55,  0.0061085655, 1.61562355889214393, 0.568545023600260491, 3,  true),
(4, 1.60,  0.0051429525, 1.66557473076714380, 0.562941996256510202, 3,  true),
(4, 1.65,  0.0044223467, 1.70882788764105853, 0.558200836181640403, 3,  true),
(4, 1.70,  0.0037692633, 1.75829043918185701, 0.552664438883463616, 3,  true),
(4, 1.75,  0.0031850242, 1.78472069634331620, 0.551698048909505245, 3,  true),
(4, 1.80,  0.0027289867, 1.81566416422526022, 0.549645741780599106, 3,  true),
(4, 1.85,  0.0023330248, 1.82287784152560750, 0.551604970296223796, 3,  true),
(4, 1.90,  0.0020232305, 1.84992726643880223, 0.550009918212890803, 3,  true),
(4, 1.95,  0.0017699727, 1.88333621554904518, 0.547602589925130112, 3,  true),
(4, 2.00,  0.0015585499, 1.90694291856553799, 0.546800994873046786, 3,  true),
(4, 2.05,    0.00141501, 1.92870330810546897, 0.545942433675130068, 3,  true),
(4, 2.10,  0.0012909783, 1.94683447943793375, 0.545642852783203014, 3,  true),
(4, 2.15,  0.0011996866, 1.95983327229817705, 0.545700836181640558, 3,  true),
(4, 2.20,   0.001102923, 1.97344377305772567, 0.546037038167317745, 3,  true),
(4, 2.25,  0.0010316431, 1.98338402642144063, 0.546487172444661384, 3,  true),
(4, 2.30, 0.00096805153, 1.99225379096137201, 0.547050221761067768, 3,  true),
(4, 2.35, 0.00091143774, 2.00018734402126697, 0.547697194417317679, 3,  true),
(4, 2.40, 0.00087081226, 2.00592770046658009, 0.548258209228515314, 3,  true),
(4, 2.45, 0.00082539805, 2.01244015163845535, 0.548992156982421986, 3,  true),
(4, 2.50, 0.00079309819, 2.01718461778428892, 0.549589284261067679, 3,  true),
(5, 1.20,   0.013925114, 1.47271143595377563, 0.547661844889323124, 3,  true),
(5, 1.25,  0.0078059267, 1.51477381388346322, 0.547609456380208193, 3,  true),
(5, 1.30,  0.0045340779, 1.56053441365559875, 0.546380106608072791, 3,  true),
(5, 1.35,   0.002821534, 1.59968931410047732, 0.545594278971354263, 3,  true),
(5, 1.40,  0.0017635314, 1.62376225789388018, 0.547126770019531250, 3,  true),
(5, 1.45,  0.0012659595, 1.67027257283528652, 0.544658406575520782, 3,  true),
(5, 1.50, 0.00097191815, 1.71065928141276036, 0.543058522542317568, 3,  true),
(5, 1.55, 0.00078030659, 1.74115142822265612, 0.542447662353515714, 3,  true),
(5, 1.60, 0.00063781753, 1.76781667073567705, 0.542211151123046964, 3,  true),
(5, 1.65, 0.00054641212, 1.80731658935546857, 0.539609527587890825, 3,  true),
(5, 1.70,  0.0004573431, 1.83974456787109331, 0.537987009684244954, 3,  true),
(5, 1.75, 0.00037273199, 1.87821875678168393, 0.535735321044921831, 3,  true),
(5, 1.80,  0.0003062092, 1.92916208902994835, 0.531913503011067768, 3,  true),
(5, 1.85, 0.00025869826, 1.97668134901258674, 0.528661346435546742, 3,  true),
(5, 1.90, 0.00022684339, 2.01164194742838554, 0.526721445719401160, 3,  true),
(5, 1.95, 0.00019891815, 2.04016469319661509, 0.525634002685546831, 3,  true),
(5, 2.00, 0.00017426706, 2.06404741075303821, 0.525147755940755356, 3,  true),
(5, 2.05, 0.00015557231, 2.08155195448133679, 0.525099436442057366, 3,  true),
(5, 2.10, 0.00013891336, 2.09675140380859348, 0.525319671630859353, 3,  true),
(5, 2.15, 0.00012654554, 2.10787777370876706, 0.525670623779296853, 3,  true),
(5, 2.20, 0.00011335614, 2.11950395372178768, 0.526264699300130090, 3,  true),
(5, 2.25,  0.0001037115, 2.12779930962456554, 0.526887766520182321, 3,  true),
(5, 2.30, 9.5205561e-05, 2.13487870958116410, 0.527610015869140359, 3,  true),
(5, 2.35, 8.7810064e-05, 2.14067128499348991, 0.528427378336588482, 3,  true),
(5, 2.40, 8.2686012e-05, 2.14426320393880232, 0.529153188069661606, 3,  true),
(5, 2.45, 7.7362661e-05, 2.14864959716796866, 0.530002593994140625, 3,  true),
(5, 2.50, 7.3695816e-05, 2.15946265326605946, 0.529833730061848529, 3,  true),
(6, 1.20,  0.0045594551, 1.50582012600368942, 0.540683492024739643, 3,  true),
(6, 1.25,  0.0021050185, 1.56927736070421009, 0.537108357747395737, 3,  true),
(6, 1.30,  0.0011154959, 1.62996512518988745, 0.533878580729166607, 3,  true),
(6, 1.35, 0.00064507169, 1.67900339762369777, 0.531911468505859464, 3,  true),
(6, 1.40, 0.00037315221, 1.72458309597439219, 0.530643971761067812, 3,  true),
(6, 1.45, 0.00024824541, 1.77476925320095469, 0.528379058837890714, 3,  true),
(6, 1.50, 0.00017724061, 1.81697709825303821, 0.527150217692057388, 3,  true),
(6, 1.55,  0.0001324623, 1.84778255886501697, 0.526968638102213394, 3,  true),
(6, 1.60, 0.00010158561, 1.87210167778862835, 0.527448781331380290, 3,  true),
(6, 1.65, 8.3583491e-05, 1.89237382676866250, 0.527660369873046875, 3,  true),
(6, 1.70, 6.8551138e-05, 1.93276146782769054, 0.525681813557942856, 3,  true),
(6, 1.75, 5.4616423e-05, 1.96848670111762192, 0.524261728922526204, 3,  true),
(6, 1.80, 4.3449372e-05, 1.99702436659071147, 0.523401641845703258, 3,  true),
(6, 1.85, 3.3827605e-05, 2.02382388644748223, 0.522790781656901182, 3,  true),
(6, 1.90, 2.8156339e-05, 2.06700524224175330, 0.520410919189453147, 3,  true),
(6, 1.95, 2.4445725e-05, 2.08590850830078134, 0.520696258544921631, 3,  true),
(6, 2.00, 2.1164377e-05, 2.10745629204644125, 0.520621490478515692, 3,  true),
(6, 2.05, 1.8468148e-05, 2.13673621283637205, 0.519232940673827970, 3,  true),
(6, 2.10, 1.6005415e-05, 2.16247270372178857, 0.518196360270182121, 3,  true),
(6, 2.15, 1.4258813e-05, 2.17432640923394116, 0.518426767985025960, 3,  true),
(6, 2.20, 1.2444461e-05, 2.18673960367838571, 0.518857574462890714, 3,  true),
(6, 2.25, 1.1114558e-05, 2.19571753607855946, 0.519317881266276093, 3,  true),
(6, 2.30, 9.9546958e-06, 2.20337880452473955, 0.519864654541015603, 3,  true),
(6, 2.35,  8.965476e-06, 2.20968983968098920, 0.520482126871744888, 3,  true),
(6, 2.40, 8.2885097e-06, 2.21353166368272536, 0.521029408772786695, 3,  true),
(6, 2.45, 7.5852234e-06, 2.23052520751953054, 0.520584869384765669, 3,  true),
(6, 2.50, 6.9655517e-06, 2.25309499104817679, 0.519467417399088638, 3,  true),
(7, 1.30,  0.0008254969, 1.74045766194661389, 0.518593088785807343, 3,  true),
(7, 1.35, 0.00038442438, 1.76697370741102411, 0.520175933837890514, 3,  true),
(7, 1.40, 0.00018937161, 1.80296749538845447, 0.520410919189453147, 3,  true),
(7, 1.45, 0.00010361285, 1.82994232177734317, 0.521003468831379934, 3,  true),
(7, 1.50,  6.235019e-05, 1.87820756700303826, 0.519385019938151005, 3,  true),
(7, 1.55, 4.0294879e-05, 1.91923302544487862, 0.518271636962890581, 3,  true),
(7, 1.60, 2.7808874e-05, 1.95363786485460067, 0.517866770426432477, 3,  true),
(7, 1.65,  2.026018e-05, 1.97871042887369786, 0.517832692464192612, 3,  true),
(7, 1.70, 1.5136149e-05, 2.00276845296224026, 0.517857615152994666, 3,  true),
(7, 1.75,  1.151624e-05, 2.02899729410807383, 0.517629750569661207, 3,  true),
(7, 1.80, 8.9463191e-06, 2.06023915608723929, 0.516692860921223907, 3,  true),
(7, 1.85, 7.0887638e-06, 2.09950408935546839, 0.515063222249348862, 3,  true),
(7, 1.90, 5.8925966e-06, 2.11824323866102393, 0.515318044026692790, 3,  true),
(7, 1.95, 4.9355286e-06, 2.13582611083984419, 0.515685272216796831, 3,  true),
(7, 2.00, 4.1417575e-06, 2.18169674343532982, 0.512996164957682188, 3,  true),
(7, 2.05, 3.5555298e-06, 2.20350562201605849, 0.512531789143879868, 3,  true),
(7, 2.10, 3.0496661e-06, 2.22028656005859348, 0.512581634521484086, 3,  true),
(7, 2.15, 2.6606782e-06, 2.23297949896918446, 0.512734731038411162, 3,  true),
(7, 2.20,  2.303615e-06, 2.24713083902994715, 0.512998199462890270, 3,  true),
(7, 2.25, 2.0304322e-06, 2.25832807752821108, 0.513249460856119444, 3,  true),
(7, 2.30, 1.7924162e-06, 2.26957007514105769, 0.513472747802734553, 3,  true),
(7, 2.35, 1.5860954e-06, 2.28171844482421804, 0.513596852620442856, 3,  true),
(7, 2.40, 1.4287925e-06, 2.29392649332682330, 0.513477325439453236, 3,  true),
(7, 2.45, 1.2852443e-06, 2.30712670220269001, 0.513562774658203103, 3,  true),
(7, 2.50, 1.1779738e-06, 2.31585845947265678, 0.513826243082682321, 3,  true),
(8, 1.65, 1.9452728e-05, 2.05627424452040009, 0.509817759195963283, 3,  true),
(8, 1.70, 1.3629565e-05, 2.07524464925130303, 0.510539499918619577, 3,  true),
(8, 1.75, 9.9866112e-06, 2.09811655680338527, 0.510826365152994732, 3,  true),
(8, 1.80, 7.4765723e-06, 2.12325252956814214, 0.510612742106119621, 3,  true),
(8, 1.85, 5.6599612e-06, 2.14303978814019125, 0.510897064208984397, 3,  true),
(8, 1.90, 4.4795853e-06, 2.16549021402994812, 0.510690053304036273, 3,  true),
(8, 1.95, 3.5909836e-06, 2.19277462429470438, 0.510074615478515847, 3,  true),
(8, 2.00, 2.9123621e-06, 2.21736975775824741, 0.509707895914713438, 3,  true),
(8, 2.05, 2.4525224e-06, 2.23633270263671724, 0.509581756591796942, 3,  true),
(8, 2.10, 2.0782745e-06, 2.25366566975911509, 0.509593454996744688, 3,  true),
(8, 2.15, 1.7816567e-06, 2.26725006103515581, 0.509669240315755001, 3,  true),
(8, 2.20, 1.5571862e-06, 2.28289710150824643, 0.509803517659505379, 3,  true),
(8, 2.25, 1.3738399e-06, 2.29649641248914893, 0.509857432047526093, 3,  true),
(8, 2.30, 1.2158171e-06, 2.31117740207248312, 0.509815724690755201, 3,  true),
(8, 2.35, 1.0793857e-06, 2.32826419406467000, 0.509585316975911473, 3,  true),
(8, 2.40, 9.6672011e-07, 2.34473554823133679, 0.509188588460286473, 3,  true),
(8, 2.45, 8.8091041e-07, 2.36683909098307277, 0.508585357666015647, 3,  true),
(8, 2.50, 8.0898294e-07, 2.38400794135199634, 0.508149464925130023, 3,  true),
(4, 1.20,   0.027630814, 1.30709338717990464, 0.588199361165364421, 2, false),
(5, 1.20,  0.0090862909, 1.47271143595377563, 0.547661844889323124, 2, false),
(6, 1.20,  0.0017482142, 1.48702875773111987, 0.543441772460937278, 2, false),
(7, 1.20,  0.0005429861, 1.57363950941297781, 0.528833516438802165, 2, false),
(8, 1.20, 0.00015606381, 1.62251086764865415, 0.521761576334635269, 2, false),
(9, 1.20, 4.4719474e-05, 1.65120146009657076, 0.517889404296875133, 2, false),
(10, 1.20,  1.188814e-05, 1.69237518310546853, 0.513090769449869866, 2, false),
(11, 1.20, 3.5428437e-06, 1.70876074896918384, 0.511258697509765381, 2, false),
(12, 1.20, 1.0588976e-06, 1.72945437961154469, 0.508924102783202992, 2, false),
(13, 1.20, 3.2352583e-07, 1.74369896782769063, 0.507493845621744821, 2, false),
(14, 1.20, 9.5676077e-08, 1.74225175645616304, 0.507634226481119666, 2, false),
(15, 1.20, 2.9601364e-08, 1.75197194417317714, 0.506649017333984153, 2, false),
(16, 1.20, 1.4565997e-08, 1.76991288926866353, 0.504910532633463305, 2, false),
(4, 1.25,   0.017174497, 1.33188061184353357, 0.594018046061197902, 2, false),
(5, 1.25,  0.0051277154, 1.51477381388346322, 0.547609456380208193, 2, false),
(6, 1.25,  0.0010483893, 1.55846243964301179, 0.538631693522135246, 2, false),
(7, 1.25, 0.00025201815, 1.62363544040256103, 0.528018188476562345, 2, false),
(8, 1.25, 5.5083153e-05, 1.68515777587890647, 0.519925181070963416, 2, false),
(9, 1.25, 1.6071961e-05, 1.71001400417751714, 0.516446685791015603, 2, false),
(10, 1.25, 4.0641604e-06, 1.74668290879991273, 0.512401072184244577, 2, false),
(11, 1.25, 1.0790185e-06, 1.76964806450737866, 0.509976450602213416, 2, false),
(12, 1.25, 2.7728809e-07, 1.78036787245008643, 0.508847300211588749, 2, false),
(13, 1.25, 7.5207271e-08, 1.78752933078341969, 0.508087921142578502, 2, false),
(14, 1.25, 1.9707719e-08, 1.79297129313150982, 0.507515716552734419, 2, false),
(15, 1.25, 5.1856713e-09, 1.79311303032769098, 0.507442982991536562, 2, false),
(16, 1.25, 2.0137551e-09, 1.80572391086154527, 0.506224822998046720, 2, false),
(4, 1.30,   0.011470229, 1.36280729505750875, 0.596257019042968683, 2, false),
(5, 1.30,  0.0029882132, 1.56042251586914049, 0.546399434407552009, 2, false),
(6, 1.30, 0.00061703186, 1.62978795369466201, 0.533901977539062544, 2, false),
(7, 1.30, 0.00014050797, 1.68304663764105911, 0.525806935628255534, 2, false),
(8, 1.30,  2.694353e-05, 1.74423607720269080, 0.518215688069661340, 2, false),
(9, 1.30, 6.5033751e-06, 1.77520938449435794, 0.514374542236327836, 2, false),
(10, 1.30, 1.5292703e-06, 1.80346357557508630, 0.511223093668619510, 2, false),
(11, 1.30, 3.7760627e-07, 1.82270626491970456, 0.509227244059244799, 2, false),
(12, 1.30, 8.8621514e-08, 1.82085249159071205, 0.509485626220703036, 2, false),
(13, 1.30, 2.0473021e-08, 1.82708892822265589, 0.508758290608723796, 2, false),
(14, 1.30, 4.6605257e-09, 1.83420189751519080, 0.507956695556640692, 2, false),
(15, 1.30, 1.1935629e-09, 1.85243004692925317, 0.506316375732421831, 2, false),
(16, 1.30, 3.7888952e-10, 1.85057254367404500, 0.506397755940754979, 2, false),
(4, 1.35,  0.0085002328, 1.38681869506835920, 0.598430379231771004, 2, false),
(5, 1.35,  0.0018623488, 1.59968931410047732, 0.545594278971354263, 2, false),
(6, 1.35,   0.000371556, 1.67900339762369777, 0.531911468505859464, 2, false),
(7, 1.35, 8.4007064e-05, 1.73462778727213518, 0.523948923746745066, 2, false),
(8, 1.35, 1.5072283e-05, 1.78767479790581585, 0.517632293701171697, 2, false),
(9, 1.35, 3.2987001e-06, 1.82514563666449625, 0.513285064697265758, 2, false),
(10, 1.35, 7.0409638e-07, 1.84514923095703098, 0.511175282796223707, 2, false),
(11, 1.35, 1.5471886e-07, 1.85591006808810710, 0.509974924723307299, 2, false),
(12, 1.35, 3.4242213e-08, 1.86972944471571201, 0.508644358317057343, 2, false),
(13, 1.35, 7.2998086e-09, 1.86772647433810768, 0.508736928304036495, 2, false),
(14, 1.35, 1.3963203e-09, 1.86868506537543366, 0.508473968505859464, 2, false),
(15, 1.35, 3.2543842e-10, 1.88662601047091982, 0.506844838460286384, 2, false),
(16, 1.35, 9.9868928e-11, 1.90032229953342013, 0.505679066975911473, 2, false),
(4, 1.40,  0.0066857449, 1.42907129923502607, 0.595376586914062478, 2, false),
(5, 1.40,  0.0011646611, 1.62376225789388040, 0.547126770019531361, 2, false),
(6, 1.40, 0.00021925238, 1.72446373833550348, 0.530658213297526271, 2, false),
(7, 1.40, 4.7562085e-05, 1.78181135389539902, 0.522699228922526182, 2, false),
(8, 1.40, 8.5117152e-06, 1.82943505181206612, 0.517185719807942368, 2, false),
(9, 1.40, 1.7177338e-06, 1.87064327663845464, 0.512637074788411362, 2, false),
(10, 1.40, 3.4480399e-07, 1.89010603162977397, 0.510741933186848796, 2, false),
(11, 1.40,  6.531871e-08, 1.88815528021918388, 0.510795338948567546, 2, false),
(12, 1.40, 1.3161431e-08, 1.90691307915581620, 0.508948008219400894, 2, false),
(13, 1.40, 2.6549019e-09, 1.91943817138671879, 0.507719167073567790, 2, false),
(14, 1.40, 5.0362062e-10, 1.91767764621310755, 0.507796478271484331, 2, false),
(15, 1.40, 9.6086651e-11, 1.92086300320095482, 0.507323964436848907, 2, false),
(16, 1.40, 2.7093353e-11, 1.93481665717230888, 0.506169382731119777, 2, false),
(4, 1.45,  0.0056226916, 1.48220782809787344, 0.588401285807291785, 2, false),
(5, 1.45, 0.00083718611, 1.67027257283528652, 0.544658406575520782, 2, false),
(6, 1.45, 0.00014913901, 1.77476925320095469, 0.528379058837890714, 2, false),
(7, 1.45, 2.7747197e-05, 1.81916283501519116, 0.522077687581380068, 2, false),
(8, 1.45, 5.1709622e-06, 1.87167646620008665, 0.516175079345702947, 2, false),
(9, 1.45, 9.8345236e-07, 1.90793134901258621, 0.512265777587890381, 2, false),
(10, 1.45, 1.8930947e-07, 1.93040042453342009, 0.510135142008463660, 2, false),
(11, 1.45,  3.332952e-08, 1.91693539089626719, 0.511350250244140492, 2, false),
(12, 1.45, 5.9975333e-09, 1.93405948215060786, 0.509625498453776027, 2, false),
(13, 1.45, 1.0866241e-09, 1.95315670437283018, 0.507810211181640714, 2, false),
(14, 1.45,  2.094927e-10, 1.96645389133029469, 0.506643422444661429, 2, false),
(15, 1.45, 3.9230381e-11, 1.90479821099175362, 0.512058766682942590, 2, false),
(16, 1.45, 9.8637235e-12, 1.96671498616536478, 0.506378936767577725, 2, false),
(4, 1.50,  0.0047687786, 1.55200220743815076, 0.577678934733072857, 2, false),
(5, 1.50, 0.00064330903, 1.71065928141276036, 0.543058522542317568, 2, false),
(6, 1.50, 0.00010783361, 1.81697709825303821, 0.527150217692057388, 2, false),
(7, 1.50, 1.8133663e-05, 1.87820756700303804, 0.519385019938151005, 2, false),
(8, 1.50, 3.2470879e-06, 1.91592831081814241, 0.515136464436848796, 2, false),
(9, 1.50, 5.6665064e-07, 1.94864722357855880, 0.511623891194661340, 2, false),
(10, 1.50, 1.0317417e-07, 1.96809505886501723, 0.509795888264973684, 2, false),
(11, 1.50, 1.7828823e-08, 1.95902014838324612, 0.510626475016276227, 2, false),
(12, 1.50, 3.0067838e-09, 1.97183990478515603, 0.509373728434244777, 2, false),
(13, 1.50, 4.4817001e-10, 1.97394731309678861, 0.508898671468098862, 2, false),
(14, 1.50, 8.1249349e-11, 1.99085879855685755, 0.507420094807942590, 2, false),
(15, 1.50, 1.4508907e-11, 2.00304073757595535, 0.506375376383463305, 2, false),
(16, 1.50, 3.9889501e-12, 2.01239166259765634, 0.505605824788411429, 2, false),
(4, 1.55,  0.0040709003, 1.61562355889214393, 0.568545023600260491, 2, false),
(5, 1.55, 0.00051697223, 1.74115142822265612, 0.542447662353515714, 2, false),
(6, 1.55,   8.16119e-05, 1.84778255886501697, 0.526968638102213394, 2, false),
(7, 1.55,  1.298829e-05, 1.91922556559244795, 0.518272145589192546, 2, false),
(8, 1.55, 2.2042444e-06, 1.96090749104817696, 0.513719431559244599, 2, false),
(9, 1.55, 3.4974148e-07, 1.96196679009331620, 0.513517506917317901, 2, false),
(10, 1.55, 5.8935855e-08, 1.99232838948567714, 0.510506439208984419, 2, false),
(11, 1.55, 9.7079011e-09, 2.00348086886935883, 0.509428660074869644, 2, false),
(12, 1.55, 1.6246975e-09, 2.01106753879123179, 0.508689626057942546, 2, false),
(13, 1.55, 2.3132914e-10, 1.99755028618706554, 0.509466298421224040, 2, false),
(14, 1.55,  3.699667e-11, 2.01643490261501634, 0.507848358154296964, 2, false),
(15, 1.55, 5.7787035e-12, 2.02789323594835080, 0.506847381591796986, 2, false),
(16, 1.55, 1.6329489e-12, 2.04246605767144107, 0.505713144938151005, 2, false),
(4, 1.60,  0.0034274729, 1.66557473076714380, 0.562941996256510202, 2, false),
(5, 1.60, 0.00042277921, 1.76781667073567705, 0.542211151123046964, 2, false),
(6, 1.60, 6.2948983e-05, 1.87210167778862813, 0.527448781331380179, 2, false),
(7, 1.60, 9.3309104e-06, 1.95363786485460023, 0.517866770426432477, 2, false),
(8, 1.60, 1.5172399e-06, 1.99141828748914929, 0.513874053955077903, 2, false),
(9, 1.60, 2.2268699e-07, 1.98512217203776031, 0.514410654703776005, 2, false),
(10, 1.60, 3.4085262e-08, 2.01318240695529616, 0.511495717366536540, 2, false),
(11, 1.60, 5.1758982e-09, 2.03020952012803813, 0.509832000732421853, 2, false),
(12, 1.60, 8.3392806e-10, 2.04782223171657973, 0.508222198486328103, 2, false),
(13, 1.60, 1.2339824e-10, 2.05101131863064312, 0.507862599690754979, 2, false),
(14, 1.60, 1.8857143e-11, 2.05649431016710116, 0.507271575927734197, 2, false),
(15, 1.60, 2.8427489e-12, 2.01824018690321161, 0.510732269287109242, 2, false),
(16, 1.60, 7.7510717e-13, 2.02804056803385357, 0.509260559082031272, 2, false),
(4, 1.65,  0.0029472944, 1.70882788764105853, 0.558200836181640403, 2, false),
(5, 1.65, 0.00036242937, 1.80731658935546857, 0.539609527587890825, 2, false),
(6, 1.65, 5.2206998e-05, 1.89124738905164880, 0.527779897054036606, 2, false),
(7, 1.65, 7.1130088e-06, 1.97871042887369786, 0.517832692464192723, 2, false),
(8, 1.65, 1.1062443e-06, 2.02737477620442652, 0.512729136149088327, 2, false),
(9, 1.65, 1.5997431e-07, 2.01524505615234384, 0.514055633544921897, 2, false),
(10, 1.65, 2.2485549e-08, 2.03220876057942634, 0.512120819091796853, 2, false),
(11, 1.65, 3.1531336e-09, 2.05390947129991286, 0.510055287679036407, 2, false),
(12, 1.65, 4.7229812e-10, 2.07090674506293437, 0.508435312906900916, 2, false),
(13, 1.65, 6.8253405e-11, 2.08033972846137116, 0.507582346598307255, 2, false),
(14, 1.65, 1.0291321e-11, 2.09127587212456634, 0.506627146402994555, 2, false),
(15, 1.65, 1.5733668e-12, 2.09200320773654447, 0.506441497802734397, 2, false),
(16, 1.65, 4.1632968e-13, 2.05187852647569402, 0.510007731119791474, 2, false),
(4, 1.70,  0.0025120672, 1.75829043918185701, 0.552664438883463616, 2, false),
(5, 1.70, 0.00030343068, 1.83974456787109331, 0.537987009684244954, 2, false),
(6, 1.70, 4.3060189e-05, 1.92978871663411455, 0.525992584228515692, 2, false),
(7, 1.70, 5.4198612e-06, 2.00241783989800304, 0.517897796630859220, 2, false),
(8, 1.70, 8.0384636e-07, 2.05249209933810794, 0.512742869059244488, 2, false),
(9, 1.70, 1.1563827e-07, 2.04652421739366375, 0.513499704996744466, 2, false),
(10, 1.70, 1.5519101e-08, 2.05339101155599080, 0.512527211507161184, 2, false),
(11, 1.70, 1.9888918e-09, 2.06418914794921893, 0.511281077067057388, 2, false),
(12, 1.70, 2.7076896e-10, 2.08515879313151054, 0.509268951416015692, 2, false),
(13, 1.70, 3.7243447e-11, 2.10078718397352437, 0.507962799072265603, 2, false),
(14, 1.70, 5.2817391e-12, 2.11506161159939232, 0.506755828857421986, 2, false),
(15, 1.70, 8.2091438e-13, 2.12537112765841929, 0.505952707926431988, 2, false),
(16, 1.70, 2.2836638e-13, 2.13444417317708313, 0.505234781901041763, 2, false),
(4, 1.75,  0.0021226826, 1.78472069634331620, 0.551698048909505245, 2, false),
(5, 1.75, 0.00024729283, 1.87821875678168393, 0.535735321044921831, 2, false),
(6, 1.75,    3.4347e-05, 1.96848670111762192, 0.524261728922526204, 2, false),
(7, 1.75, 4.1139339e-06, 2.02892269558376803, 0.517637888590494311, 2, false),
(8, 1.75, 5.8062743e-07, 2.07719167073567679, 0.512768809000650916, 2, false),
(9, 1.75, 8.0747826e-08, 2.10331607394748143, 0.510445404052734530, 2, false),
(10, 1.75, 1.0896265e-08, 2.10092146131727464, 0.510645294189453258, 2, false),
(11, 1.75,  1.394523e-09, 2.10065290662977411, 0.510514068603515558, 2, false),
(12, 1.75, 1.6685807e-10, 2.10685204399956616, 0.509598541259765669, 2, false),
(13, 1.75, 2.1709563e-11, 2.12432301839192705, 0.508163706461588482, 2, false),
(14, 1.75, 2.8187972e-12, 2.14311438666449705, 0.506678517659505223, 2, false),
(15, 1.75, 4.3021724e-13, 2.15020870632595518, 0.506039174397786340, 2, false),
(16, 1.75, 1.3786536e-13, 2.16093410915798634, 0.505217488606770959, 2, false),
(4, 1.80,  0.0018187471, 1.81566416422526022, 0.549645741780599106, 2, false),
(5, 1.80, 0.00020316124, 1.92916208902994835, 0.531913503011067768, 2, false),
(6, 1.80, 2.7310863e-05, 1.99691992865668366, 0.523411814371744888, 2, false),
(7, 1.80, 3.2184975e-06, 2.06023915608723929, 0.516692860921223907, 2, false),
(8, 1.80, 4.3416853e-07, 2.10110795762803804, 0.512618255615234109, 2, false),
(9, 1.80,  5.790666e-08, 2.12062293158637161, 0.510943349202474084, 2, false),
(10, 1.80, 7.6499403e-09, 2.13734046088324670, 0.509422047932942657, 2, false),
(11, 1.80, 9.9331646e-10, 2.13370751274956616, 0.509656016031900805, 2, false),
(12, 1.80,   1.18188e-10, 2.12671017116970473, 0.509776560465494577, 2, false),
(13, 1.80, 1.4808048e-11, 2.14630347357855955, 0.508229319254557166, 2, false),
(14, 1.80, 1.7205951e-12, 2.10544586181640581, 0.512052663167317790, 2, false),
(15, 1.80, 2.7112982e-13, 2.13324873182508590, 0.508927663167317745, 2, false),
(16, 1.80, 9.2432339e-14, 2.17575683593749947, 0.505806477864583326, 2, false),
(4, 1.85,  0.0015548405, 1.82287784152560750, 0.551604970296223796, 2, false),
(5, 1.85, 0.00017165273, 1.97668134901258674, 0.528661346435546742, 2, false),
(6, 1.85, 2.1207259e-05, 2.02382388644748223, 0.522790781656901182, 2, false),
(7, 1.85, 2.5830842e-06, 2.08198835584852526, 0.516882069905598818, 2, false),
(8, 1.85, 3.2721534e-07, 2.11999257405599018, 0.513011932373046986, 2, false),
(9, 1.85, 4.1561054e-08, 2.13356204562717044, 0.511795806884765447, 2, false),
(10, 1.85, 5.2201064e-09, 2.15372229682074634, 0.509919484456380134, 2, false),
(11, 1.85, 6.6801813e-10, 2.16671735975477509, 0.508801015218098618, 2, false),
(12, 1.85, 7.9198356e-11, 2.17137230767144151, 0.508251190185546764, 2, false),
(13, 1.85, 9.9653524e-12, 2.18463965521918491, 0.507171376546223907, 2, false),
(14, 1.85, 1.1454323e-12, 2.18464338514539991, 0.506948089599609020, 2, false),
(15, 1.85, 1.6940164e-13, 2.19788648817274268, 0.505950419108072702, 2, false),
(16, 1.85, 6.0166976e-14, 2.21154920789930598, 0.504844156901041563, 2, false),
(4, 1.90,  0.0013483663, 1.84992726643880223, 0.550009918212890803, 2, false),
(5, 1.90,  0.0001505286, 2.01164194742838554, 0.526721445719401160, 2, false),
(6, 1.90, 1.7657942e-05, 2.06700524224175330, 0.520410919189453147, 2, false),
(7, 1.90, 2.1583209e-06, 2.09541609022352526, 0.517656707763671786, 2, false),
(8, 1.90,  2.571808e-07, 2.12510257297092009, 0.514389292399088371, 2, false),
(9, 1.90, 3.1078146e-08, 2.15220421685112884, 0.511920928955078125, 2, false),
(10, 1.90, 3.7085363e-09, 2.17061513264973893, 0.510152435302734353, 2, false),
(11, 1.90, 4.6189212e-10, 2.18844790988498250, 0.508651479085286296, 2, false),
(12, 1.90,  5.283541e-11, 2.19517669677734384, 0.507954661051432166, 2, false),
(13, 1.90, 6.5567471e-12, 2.20817175971137170, 0.506905364990234530, 2, false),
(14, 1.90, 7.4876468e-13, 2.21245371500651000, 0.506451670328776249, 2, false),
(15, 1.90, 1.0987385e-13, 2.22502916124131955, 0.505518595377604019, 2, false),
(16, 1.90, 4.3904399e-14, 2.23213840060763902, 0.504876708984374867, 2, false),
(4, 1.95,   0.001179576, 1.88333621554904518, 0.547602589925130112, 2, false),
(5, 1.95, 0.00013200207, 2.04016469319661509, 0.525634002685546831, 2, false),
(6, 1.95, 1.5350804e-05, 2.08590850830078134, 0.520696258544921631, 2, false),
(7, 1.95, 1.8204167e-06, 2.10214114718967027, 0.519080352783203303, 2, false),
(8, 1.95, 2.0378929e-07, 2.13631846110026080, 0.515235646565755157, 2, false),
(9, 1.95, 2.3559792e-08, 2.16356930202907982, 0.512669626871744888, 2, false),
(10, 1.95, 2.6355058e-09, 2.18178999159071196, 0.510828908284505112, 2, false),
(11, 1.95, 3.1844565e-10, 2.20117441813151027, 0.509173838297526049, 2, false),
(12, 1.95, 3.4490979e-11, 2.21349809434678813, 0.508074696858723862, 2, false),
(13, 1.95, 4.1900745e-12, 2.22576209174262019, 0.507048288981119866, 2, false),
(14, 1.95,  4.685642e-13, 2.23883175320095473, 0.506095631917317768, 2, false),
(15, 1.95, 6.9809174e-14, 2.24861907958984375, 0.505327606201171675, 2, false),
(16, 1.95, 3.2796943e-14, 2.25592041015625044, 0.504429117838541607, 2, false),
(4, 2.00,  0.0010386672, 1.90694291856553799, 0.546800994873046786, 2, false),
(5, 2.00, 0.00011564198, 2.06404741075303821, 0.525147755940755356, 2, false),
(6, 2.00, 1.3300245e-05, 2.10745629204644125, 0.520621490478515692, 2, false),
(7, 2.00, 1.5542971e-06, 2.13151058620876643, 0.518270619710286762, 2, false),
(8, 2.00,  1.639799e-07, 2.14249894883897563, 0.516482289632161362, 2, false),
(9, 2.00, 1.8236273e-08, 2.17356550428602446, 0.513518524169921942, 2, false),
(10, 2.00, 1.9345023e-09, 2.20186072455512116, 0.510932668050130157, 2, false),
(11, 2.00, 2.2406492e-10, 2.21397179497612839, 0.509688568115234331, 2, false),
(12, 2.00, 2.4541257e-11, 2.24148000081380294, 0.507639821370442501, 2, false),
(13, 2.00, 2.7515159e-12, 2.24892120361328107, 0.506914011637369821, 2, false),
(14, 2.00, 3.2435552e-13, 2.25044860839843697, 0.506738789876302165, 2, false),
(15, 2.00, 4.8048055e-14, 2.24747585720486143, 0.506626383463541607, 2, false),
(16, 2.00, 2.5131751e-14, 2.27874009874131955, 0.504424031575520848, 2, false),
(4, 2.05, 0.00094300395, 1.92870330810546897, 0.545942433675130068, 2, false),
(5, 2.05, 0.00010323212, 2.08155195448133679, 0.525099436442057366, 2, false),
(6, 2.05, 1.1604287e-05, 2.13673621283637205, 0.519232940673827970, 2, false),
(7, 2.05, 1.3523573e-06, 2.17350582546657956, 0.515741221110026071, 2, false),
(8, 2.05, 1.3910749e-07, 2.15772077772352455, 0.516779327392578147, 2, false),
(9, 2.05, 1.5021906e-08, 2.17791086832682312, 0.514518483479817657, 2, false),
(10, 2.05, 1.5416572e-09, 2.21550852457682268, 0.511269378662109308, 2, false),
(11, 2.05, 1.7225099e-10, 2.23040584988064206, 0.509801991780599040, 2, false),
(12, 2.05, 1.8457297e-11, 2.25799238416883696, 0.507725779215494555, 2, false),
(13, 2.05, 2.0229806e-12, 2.26661597357855804, 0.506922658284505112, 2, false),
(14, 2.05,   2.32967e-13, 2.22743123372395901, 0.509872436523437389, 2, false),
(15, 2.05, 3.4057151e-14, 2.24851837158203072, 0.508230336507161429, 2, false),
(16, 2.05, 2.1135293e-14, 2.28975830078124964, 0.504876708984374867, 2, false),
(4, 2.10, 0.00086034219, 1.94683447943793375, 0.545642852783203014, 2, false),
(5, 2.10, 9.2171972e-05, 2.09675140380859348, 0.525319671630859353, 2, false),
(6, 2.10, 1.0046516e-05, 2.16241302490234455, 0.518203481038411518, 2, false),
(7, 2.10, 1.1500953e-06, 2.21955549452039946, 0.512659962972005001, 2, false),
(8, 2.10, 1.1993242e-07, 2.17143944634331598, 0.517146046956380223, 2, false),
(9, 2.10, 1.2863021e-08, 2.21104380289713598, 0.513404083251952970, 2, false),
(10, 2.10, 1.2525514e-09, 2.22412465413411553, 0.511929066975911451, 2, false),
(11, 2.10, 1.3751342e-10, 2.23974558512369804, 0.510313161214192568, 2, false),
(12, 2.10,  1.404097e-11, 2.26767900254991339, 0.508244578043619777, 2, false),
(13, 2.10, 1.5104659e-12, 2.22048051622178777, 0.511962127685547053, 2, false),
(14, 2.10, 1.7622925e-13, 2.24638112386067634, 0.509975433349609375, 2, false),
(15, 2.10, 2.5917971e-14, 2.26238810221354081, 0.508665974934895848, 2, false),
(16, 2.10,  1.760438e-14, 2.34405483669704839, 0.502705383300781405, 2, false),
(4, 2.15, 0.00079950354, 1.95983327229817705, 0.545700836181640558, 2, false),
(5, 2.15,  8.396576e-05, 2.10787777370876706, 0.525670623779296853, 2, false),
(6, 2.15, 8.9487914e-06, 2.17432640923394116, 0.518426767985025960, 2, false),
(7, 2.15, 1.0003671e-06, 2.23297949896918446, 0.512734731038411051, 2, false),
(8, 2.15, 1.0650838e-07, 2.19627329508463598, 0.516251881917317523, 2, false),
(9, 2.15, 1.1203551e-08, 2.22688106960720544, 0.513256072998046653, 2, false),
(10, 2.15, 1.0775494e-09, 2.22816043429904509, 0.512646738688151027, 2, false),
(11, 2.15, 1.1697725e-10, 2.25718299018012170, 0.510106658935546631, 2, false),
(12, 2.15, 1.1534164e-11, 2.27178565131293375, 0.508858489990234419, 2, false),
(13, 2.15,  1.240233e-12, 2.23387468126085098, 0.512366485595703081, 2, false),
(14, 2.15, 1.3126925e-13, 2.30832027859157973, 0.506116994222005290, 2, false),
(15, 2.15, 2.1176376e-14, 2.31364474826388866, 0.505541992187499734, 2, false),
(16, 2.15, 1.5296998e-14, 2.37511206732855928, 0.501588694254557321, 2, false),
(4, 2.20,  0.0007350119, 1.97344377305772567, 0.546037038167317745, 2, false),
(5, 2.20, 7.5202537e-05, 2.11950395372178768, 0.526264699300130090, 2, false),
(6, 2.20, 7.7892284e-06, 2.18673960367838571, 0.518857574462890714, 2, false),
(7, 2.20, 8.4352514e-07, 2.24713083902994715, 0.512998199462890270, 2, false),
(8, 2.20, 8.7514764e-08, 2.26494496663411438, 0.511482493082681899, 2, false),
(9, 2.20, 9.1481001e-09, 2.27114783393012099, 0.510934702555338682, 2, false),
(10, 2.20, 9.0383263e-10, 2.27525821261935723, 0.510403188069661562, 2, false),
(11, 2.20, 9.1548702e-11, 2.29960717095269063, 0.508342234293619577, 2, false),
(12, 2.20, 8.9714426e-12, 2.30357954237196205, 0.507871754964192901, 2, false),
(13, 2.20, 9.8235294e-13, 2.25579172770182224, 0.511590830485025849, 2, false),
(14, 2.20,  9.336502e-14, 2.33169013129340330, 0.505726114908854329, 2, false),
(15, 2.20, 1.7775364e-14, 2.30224236382378411, 0.507592264811198013, 2, false),
(16, 2.20, 1.3178514e-14, 2.39444240993923652, 0.501569620768229085, 2, false),
(4, 2.25, 0.00068750745, 1.98338402642144063, 0.546487172444661384, 2, false),
(5, 2.25, 6.8798741e-05, 2.12779930962456554, 0.526887766520182321, 2, false),
(6, 2.25, 6.9455833e-06, 2.19571753607855902, 0.519317881266276093, 2, false),
(7, 2.25, 7.3013089e-07, 2.25832807752821108, 0.513249460856119444, 2, false),
(8, 2.25, 7.3740572e-08, 2.28025631374782956, 0.511336008707682144, 2, false),
(9, 2.25, 7.5516948e-09, 2.29882388644748259, 0.509762827555338527, 2, false),
(10, 2.25, 7.3294518e-10, 2.30602637396918420, 0.509100596110026005, 2, false),
(11, 2.25, 7.1811192e-11, 2.31697370741102437, 0.508083852132161451, 2, false),
(12, 2.25, 6.8554541e-12, 2.32586585150824599, 0.507328033447265736, 2, false),
(13, 2.25, 6.4327647e-13, 2.33827904595269054, 0.506330617268880179, 2, false),
(14, 2.25, 6.7026174e-14, 2.34635993109808982, 0.505700174967447791, 2, false),
(15, 2.25, 1.3819742e-14, 2.34157443576388857, 0.505541992187499845, 2, false),
(16, 2.25, 1.1356449e-14, 2.38293185763888937, 0.502848307291666519, 2, false),
(4, 2.30, 0.00064512709, 1.99225379096137201, 0.547050221761067768, 2, false),
(5, 2.30, 6.3151377e-05, 2.13487870958116410, 0.527610015869140359, 2, false),
(6, 2.30, 6.2102127e-06, 2.20337880452473955, 0.519864654541015603, 2, false),
(7, 2.30, 6.3153623e-07, 2.26955888536241268, 0.513473765055338482, 2, false),
(8, 2.30, 6.2047829e-08, 2.28904028998480946, 0.511767323811848751, 2, false),
(9, 2.30, 6.1846265e-09, 2.31326989067925348, 0.509712473551432010, 2, false),
(10, 2.30, 5.8562634e-10, 2.32252756754557277, 0.508909352620442790, 2, false),
(11, 2.30,  5.540074e-11, 2.33217688666449563, 0.507999928792317590, 2, false),
(12, 2.30, 5.1582894e-12, 2.34049835205078072, 0.507298533121744888, 2, false),
(13, 2.30, 4.9934178e-13, 2.34607832166883634, 0.506789906819661407, 2, false),
(14, 2.30, 5.2186506e-14, 2.35365193684895768, 0.506177775065104196, 2, false),
(15, 2.30, 1.2169554e-14, 2.33074832492404438, 0.507601674397786695, 2, false),
(16, 2.30, 1.0068399e-14, 2.41578504774305580, 0.500638834635416696, 2, false),
(4, 2.35, 0.00060739736, 2.00018734402126697, 0.547697194417317679, 2, false),
(5, 2.35, 5.8241938e-05, 2.14067128499348991, 0.528427378336588482, 2, false),
(6, 2.35, 5.5842265e-06, 2.20968983968098920, 0.520482126871744888, 2, false),
(7, 2.35, 5.4670414e-07, 2.28155059814453187, 0.513612620035807210, 2, false),
(8, 2.35, 5.2037551e-08, 2.30517968071831536, 0.511560312906900849, 2, false),
(9, 2.35, 5.0507342e-09, 2.32373233371310839, 0.509988657633463127, 2, false),
(10, 2.35, 4.6415656e-10, 2.33070356580946259, 0.509332529703776182, 2, false),
(11, 2.35, 4.2968707e-11, 2.35038265652126777, 0.507772572835286540, 2, false),
(12, 2.35, 4.1935249e-12, 2.35220659044053804, 0.507554880777994710, 2, false),
(13, 2.35,  3.966966e-13, 2.34172736273871562, 0.508011372884114687, 2, false),
(14, 2.35, 4.0098276e-14, 2.35412190755208384, 0.507126871744791652, 2, false),
(15, 2.35, 1.0354054e-14, 2.34626668294270768, 0.507597859700520737, 2, false),
(16, 2.35, 9.1074408e-15, 2.42102186414930598, 0.502773030598958393, 2, false),
(4, 2.40, 0.00058032523, 2.00592770046658009, 0.548258209228515314, 2, false),
(5, 2.40, 5.4844492e-05, 2.14426320393880232, 0.529153188069661606, 2, false),
(6, 2.40, 5.1622563e-06, 2.21353166368272536, 0.521029408772786695, 2, false),
(7, 2.40, 4.8790471e-07, 2.29392649332682330, 0.513477325439453236, 2, false),
(8, 2.40, 4.5271076e-08, 2.30989430745442670, 0.512092336018880268, 2, false),
(9, 2.40, 4.2974268e-09, 2.33141225179036482, 0.510267893473307144, 2, false),
(10, 2.40, 3.9051113e-10, 2.34538455539279589, 0.509139251708984220, 2, false),
(11, 2.40, 3.6729918e-11, 2.36717105441623232, 0.507470448811848884, 2, false),
(12, 2.40, 3.5077579e-12, 2.37904713948567714, 0.506586964925130334, 2, false),
(13, 2.40, 3.1702584e-13, 2.33895043267144098, 0.509288279215494799, 2, false),
(14, 2.40, 3.1695681e-14, 2.35107828776041705, 0.508315022786458126, 2, false),
(15, 2.40, 9.7154883e-15, 2.34058973524305536, 0.508540852864583282, 2, false),
(16, 2.40, 8.1910843e-15, 2.43121202256944402, 0.503002929687500155, 2, false),
(4, 2.45, 0.00055005788, 2.01244015163845535, 0.548992156982421986, 2, false),
(5, 2.45, 5.1309599e-05, 2.14864959716796866, 0.530002593994140625, 2, false),
(6, 2.45, 4.7168978e-06, 2.23052520751953054, 0.520584869384765669, 2, false),
(7, 2.45,  4.259801e-07, 2.30423973931206483, 0.513812510172525938, 2, false),
(8, 2.45, 3.8130691e-08, 2.31863352457682304, 0.512532806396484242, 2, false),
(9, 2.45,  3.521746e-09, 2.33694373236762143, 0.510904693603515647, 2, false),
(10, 2.45, 3.2442404e-10, 2.36320241292317723, 0.508957163492838260, 2, false),
(11, 2.45, 2.9870495e-11, 2.38042721218533027, 0.507595062255859042, 2, false),
(12, 2.45, 2.7880605e-12, 2.38868526882595456, 0.506927235921224018, 2, false),
(13, 2.45, 2.5450194e-13, 2.33679080539279571, 0.511076100667317568, 2, false),
(14, 2.45, 2.4696607e-14, 2.35007866753472294, 0.509834798177083215, 2, false),
(15, 2.45, 8.6673822e-15, 2.34827524820963562, 0.509776051839192723, 2, false),
(16, 2.45, 7.9794978e-15, 2.35947808159722250, 0.511319986979166585, 2, false),
(4, 2.50,  0.0005285327, 2.01718461778428892, 0.549589284261067679, 2, false),
(5, 2.50, 4.8878353e-05, 2.15946265326605946, 0.529833730061848529, 2, false),
(6, 2.50, 4.3256521e-06, 2.25309499104817679, 0.519467417399088638, 2, false),
(7, 2.50, 3.8329434e-07, 2.30846947564019045, 0.514437103271484064, 2, false),
(8, 2.50, 3.3575942e-08, 2.33213212754991250, 0.512434641520182366, 2, false),
(9, 2.50, 3.0536485e-09, 2.35149417453342036, 0.510761769612630090, 2, false),
(10, 2.50, 2.8011519e-10, 2.37159847683376723, 0.509220123291015292, 2, false),
(11, 2.50, 2.5250917e-11, 2.38795047336154509, 0.507892100016275494, 2, false),
(12, 2.50, 2.3449365e-12, 2.39123280843099018, 0.507511138916015181, 2, false),
(13, 2.50,  2.155162e-13, 2.39824133978949661, 0.506931304931640403, 2, false),
(14, 2.50, 2.2253421e-14, 2.37836642795138831, 0.508345540364583459, 2, false),
(15, 2.50, 8.2349925e-15, 2.35148111979166652, 0.509773763020833326, 2, false),
(16, 2.50, 7.1866641e-15, 2.35853814019097285, 0.512795003255208326, 2, false),
(4, 1.20,   0.041446222, 1.30709338717990464, 0.588199361165364421, 3, false),
(5, 1.20,   0.013629436, 1.47271143595377563, 0.547661844889323124, 3, false),
(6, 1.20,  0.0026223213, 1.48702875773111987, 0.543441772460937278, 3, false),
(7, 1.20, 0.00081447916, 1.57363950941297781, 0.528833516438802165, 3, false),
(8, 1.20, 0.00023409579, 1.62251086764865415, 0.521761576334635269, 3, false),
(9, 1.20, 6.7079641e-05, 1.65120146009657076, 0.517889404296875133, 3, false),
(10, 1.20, 1.7834137e-05, 1.69237518310546853, 0.513090769449869866, 3, false),
(11, 1.20, 5.3241984e-06, 1.70876074896918384, 0.511258697509765381, 3, false),
(12, 1.20, 1.6365303e-06, 1.72945437961154491, 0.508924102783202881, 3, false),
(13, 1.20, 7.1906035e-07, 1.74623904758029513, 0.507221730550130090, 3, false),
(4, 1.25,   0.025761745, 1.33188061184353357, 0.594018046061197902, 3, false),
(5, 1.25,  0.0076915731, 1.51477381388346322, 0.547609456380208193, 3, false),
(6, 1.25,  0.0015725839, 1.55846243964301179, 0.538631693522135246, 3, false),
(7, 1.25, 0.00037802722, 1.62363544040256103, 0.528018188476562345, 3, false),
(8, 1.25, 8.2624744e-05, 1.68515777587890647, 0.519925181070963416, 3, false),
(9, 1.25, 2.4108007e-05, 1.71001400417751714, 0.516446685791015603, 3, false),
(10, 1.25, 6.0964926e-06, 1.74668290879991273, 0.512401072184244577, 3, false),
(11, 1.25, 1.6195385e-06, 1.76964806450737866, 0.509976450602213416, 3, false),
(12, 1.25, 4.2023445e-07, 1.78036787245008643, 0.508847300211588749, 3, false),
(13, 1.25,  1.306458e-07, 1.79408654106987808, 0.507438913981120066, 3, false),
(14, 1.25, 9.9033504e-08, 1.81174401177300304, 0.505699920654296808, 3, false),
(4, 1.30,   0.017205343, 1.36280729505750875, 0.596257019042968683, 3, false),
(5, 1.30,  0.0044823198, 1.56042251586914049, 0.546399434407552009, 3, false),
(6, 1.30,  0.0009255478, 1.62978795369466201, 0.533901977539062544, 3, false),
(7, 1.30, 0.00021076195, 1.68304663764105911, 0.525806935628255534, 3, false),
(8, 1.30, 4.0415299e-05, 1.74423607720269080, 0.518215688069661340, 3, false),
(9, 1.30, 9.7550762e-06, 1.77520938449435794, 0.514374542236327836, 3, false),
(10, 1.30, 2.2939521e-06, 1.80346357557508630, 0.511223093668619510, 3, false),
(11, 1.30, 5.6657229e-07, 1.82270626491970456, 0.509227244059244799, 3, false),
(12, 1.30, 1.3356139e-07, 1.82085249159071205, 0.509485626220703036, 3, false),
(13, 1.30, 3.3045491e-08, 1.83200497097439241, 0.508312733968098729, 3, false),
(14, 1.30, 1.4550131e-08, 1.85990854899088531, 0.505644480387369533, 3, false),
(4, 1.35,   0.012750349, 1.38681869506835920, 0.598430379231771004, 3, false),
(5, 1.35,  0.0027935232, 1.59968931410047732, 0.545594278971354263, 3, false),
(6, 1.35,   0.000557334, 1.67900339762369777, 0.531911468505859464, 3, false),
(7, 1.35,  0.0001260106, 1.73462778727213518, 0.523948923746745066, 3, false),
(8, 1.35, 2.2608425e-05, 1.78767479790581585, 0.517632293701171697, 3, false),
(9, 1.35, 4.9480543e-06, 1.82514563666449625, 0.513285064697265758, 3, false),
(10, 1.35, 1.0561576e-06, 1.84514923095703098, 0.511175282796223707, 3, false),
(11, 1.35, 2.3212036e-07, 1.85591006808810710, 0.509974924723307299, 3, false),
(12, 1.35, 5.1494208e-08, 1.86972944471571201, 0.508644358317057343, 3, false),
(13, 1.35,  1.138375e-08, 1.87267608642578098, 0.508304595947265625, 3, false),
(14, 1.35, 3.5079381e-09, 1.88038957383897576, 0.507539621988932210, 3, false),
(4, 1.40,   0.010028617, 1.42907129923502607, 0.595376586914062478, 3, false),
(5, 1.40,  0.0017469917, 1.62376225789388040, 0.547126770019531361, 3, false),
(6, 1.40, 0.00032887857, 1.72446373833550348, 0.530658213297526271, 3, false),
(7, 1.40, 7.1343128e-05, 1.78181135389539902, 0.522699228922526182, 3, false),
(8, 1.40, 1.2767573e-05, 1.82943505181206612, 0.517185719807942368, 3, false),
(9, 1.40, 2.5766022e-06, 1.87064327663845464, 0.512637074788411362, 3, false),
(10, 1.40, 5.1721007e-07, 1.89010603162977397, 0.510741933186848796, 3, false),
(11, 1.40, 9.7990407e-08, 1.88815528021918388, 0.510795338948567546, 3, false),
(12, 1.40, 1.9775866e-08, 1.90691307915581620, 0.508948008219400894, 3, false),
(13, 1.40, 4.0756893e-09, 1.91943817138671879, 0.507719167073567790, 3, false),
(14, 1.40, 1.0288549e-09, 1.92299652099609353, 0.507370249430338593, 3, false),
(15, 1.40, 8.0851857e-10, 1.96251508924696161, 0.503927357991536318, 3, false),
(4, 1.45,  0.0084340373, 1.48220782809787344, 0.588401285807291785, 3, false),
(5, 1.45,  0.0012557792, 1.67027257283528652, 0.544658406575520782, 3, false),
(6, 1.45, 0.00022370851, 1.77476925320095469, 0.528379058837890714, 3, false),
(7, 1.45, 4.1620796e-05, 1.81916283501519116, 0.522077687581380068, 3, false),
(8, 1.45, 7.7564435e-06, 1.87167646620008665, 0.516175079345702947, 3, false),
(9, 1.45, 1.4751791e-06, 1.90793134901258621, 0.512265777587890381, 3, false),
(10, 1.45, 2.8396575e-07, 1.93040042453342009, 0.510135142008463660, 3, false),
(11, 1.45, 4.9998671e-08, 1.91693539089626719, 0.511350250244140492, 3, false),
(12, 1.45, 9.0073681e-09, 1.93405948215060786, 0.509625498453776027, 3, false),
(13, 1.45, 1.6571393e-09, 1.95315670437283018, 0.507810211181640714, 3, false),
(14, 1.45, 3.8188569e-10, 1.96678585476345469, 0.506616465250650960, 3, false),
(15, 1.45, 2.2273757e-10, 1.99709150526258683, 0.504047902425130090, 3, false),
(4, 1.50,   0.007153168, 1.55200220743815076, 0.577678934733072857, 3, false),
(5, 1.50, 0.00096496355, 1.71065928141276036, 0.543058522542317568, 3, false),
(6, 1.50, 0.00016175042, 1.81697709825303821, 0.527150217692057388, 3, false),
(7, 1.50, 2.7200495e-05, 1.87820756700303804, 0.519385019938151005, 3, false),
(8, 1.50,  4.870632e-06, 1.91592831081814241, 0.515136464436848796, 3, false),
(9, 1.50, 8.4997625e-07, 1.94864722357855880, 0.511623891194661340, 3, false),
(10, 1.50, 1.5476196e-07, 1.96809505886501723, 0.509795888264973684, 3, false),
(11, 1.50,  2.674505e-08, 1.95902014838324612, 0.510626475016276227, 3, false),
(12, 1.50, 4.5144856e-09, 1.97183990478515603, 0.509373728434244777, 3, false),
(13, 1.50, 6.8283968e-10, 1.97394731309678861, 0.508898671468098862, 3, false),
(14, 1.50, 1.4599734e-10, 1.99087371826171844, 0.507419077555338438, 3, false),
(15, 1.50, 7.5296568e-11, 2.02536807590060741, 0.504684193929036407, 3, false),
(4, 1.55,  0.0061063505, 1.61562355889214393, 0.568545023600260491, 3, false),
(5, 1.55, 0.00077545834, 1.74115142822265612, 0.542447662353515714, 3, false),
(6, 1.55, 0.00012241785, 1.84778255886501697, 0.526968638102213394, 3, false),
(7, 1.55, 1.9482436e-05, 1.91922556559244795, 0.518272145589192546, 3, false),
(8, 1.55, 3.3063667e-06, 1.96090749104817696, 0.513719431559244599, 3, false),
(9, 1.55, 5.2461237e-07, 1.96196679009331620, 0.513517506917317901, 3, false),
(10, 1.55, 8.8404119e-08, 1.99232838948567714, 0.510506439208984419, 3, false),
(11, 1.55, 1.4562607e-08, 2.00348086886935883, 0.509428660074869644, 3, false),
(12, 1.55, 2.4387385e-09, 2.01106753879123179, 0.508689626057942546, 3, false),
(13, 1.55, 3.5106362e-10, 1.99755028618706554, 0.509466298421224040, 3, false),
(14, 1.55, 6.4089206e-11, 2.01755388047960027, 0.507781219482421942, 3, false),
(15, 1.55, 2.6815991e-11, 2.04735599093966991, 0.505527496337890736, 3, false),
(4, 1.60,  0.0051412093, 1.66557473076714380, 0.562941996256510202, 3, false),
(5, 1.60, 0.00063416881, 1.76781667073567705, 0.542211151123046964, 3, false),
(6, 1.60, 9.4423474e-05, 1.87210167778862813, 0.527448781331380179, 3, false),
(7, 1.60, 1.3996366e-05, 1.95363786485460023, 0.517866770426432477, 3, false),
(8, 1.60, 2.2758598e-06, 1.99141828748914929, 0.513874053955077903, 3, false),
(9, 1.60, 3.3403057e-07, 1.98512217203776031, 0.514410654703776005, 3, false),
(10, 1.60,  5.112808e-08, 2.01318240695529616, 0.511495717366536540, 3, false),
(11, 1.60, 7.7642371e-09, 2.03020952012803813, 0.509832000732421853, 3, false),
(12, 1.60, 1.2516932e-09, 2.04782223171657973, 0.508222198486328103, 3, false),
(13, 1.60, 1.8679518e-10, 2.05101131863064312, 0.507862599690754979, 3, false),
(14, 1.60,  3.183807e-11, 2.05666961669921911, 0.507260386149088527, 3, false),
(15, 1.60, 1.1402462e-11, 2.07673661973741330, 0.505748240152994688, 3, false),
(4, 1.65,  0.0044209415, 1.70882788764105853, 0.558200836181640403, 3, false),
(5, 1.65, 0.00054364405, 1.80731658935546857, 0.539609527587890825, 3, false),
(6, 1.65, 7.8310497e-05, 1.89124738905164880, 0.527779897054036606, 3, false),
(7, 1.65, 1.0669513e-05, 1.97871042887369786, 0.517832692464192723, 3, false),
(8, 1.65, 1.6593665e-06, 2.02737477620442652, 0.512729136149088327, 3, false),
(9, 1.65, 2.3996152e-07, 2.01524505615234384, 0.514055633544921897, 3, false),
(10, 1.65, 3.3728431e-08, 2.03220876057942634, 0.512120819091796853, 3, false),
(11, 1.65, 4.7299116e-09, 2.05390947129991286, 0.510055287679036407, 3, false),
(12, 1.65, 7.0886193e-10, 2.07090674506293437, 0.508435312906900916, 3, false),
(13, 1.65, 1.0319888e-10, 2.08033972846137116, 0.507582346598307255, 3, false),
(14, 1.65, 1.7030402e-11, 2.09127587212456634, 0.506627146402994555, 3, false),
(15, 1.65, 5.4556804e-12, 2.10138024224175401, 0.505838775634765425, 3, false),
(4, 1.70,  0.0037681007, 1.75829043918185701, 0.552664438883463616, 3, false),
(5, 1.70, 0.00045514602, 1.83974456787109331, 0.537987009684244954, 3, false),
(6, 1.70, 6.4590283e-05, 1.92978871663411455, 0.525992584228515692, 3, false),
(7, 1.70, 8.1297918e-06, 2.00241783989800304, 0.517897796630859220, 3, false),
(8, 1.70, 1.2057696e-06, 2.05249209933810794, 0.512742869059244488, 3, false),
(9, 1.70, 1.7345744e-07, 2.04652421739366375, 0.513499704996744466, 3, false),
(10, 1.70, 2.3278718e-08, 2.05339101155599080, 0.512527211507161184, 3, false),
(11, 1.70, 2.9834657e-09, 2.06418914794921893, 0.511281077067057388, 3, false),
(12, 1.70, 4.0639272e-10, 2.08515879313151054, 0.509268951416015692, 3, false),
(13, 1.70, 5.6310644e-11, 2.10078718397352437, 0.507962799072265603, 3, false),
(14, 1.70, 8.7517377e-12, 2.11526675754123383, 0.506744130452474129, 3, false),
(15, 1.70, 2.7541776e-12, 2.12576276991102464, 0.505927785237630157, 3, false),
(4, 1.75,  0.0031840239, 1.78472069634331620, 0.551698048909505245, 3, false),
(5, 1.75, 0.00037093925, 1.87821875678168393, 0.535735321044921831, 3, false),
(6, 1.75,   5.15205e-05, 1.96848670111762192, 0.524261728922526204, 3, false),
(7, 1.75, 6.1709009e-06, 2.02892269558376803, 0.517637888590494311, 3, false),
(8, 1.75, 8.7094116e-07, 2.07719167073567679, 0.512768809000650916, 3, false),
(9, 1.75, 1.2112176e-07, 2.10331607394748143, 0.510445404052734530, 3, false),
(10, 1.75, 1.6344439e-08, 2.10092146131727464, 0.510645294189453258, 3, false),
(11, 1.75, 2.0918625e-09, 2.10065290662977411, 0.510514068603515558, 3, false),
(12, 1.75, 2.5043281e-10, 2.10685204399956616, 0.509598541259765669, 3, false),
(13, 1.75, 3.2824997e-11, 2.12432301839192705, 0.508163706461588482, 3, false),
(14, 1.75, 4.6873557e-12, 2.14312557644314250, 0.506677500406901293, 3, false),
(15, 1.75, 1.4671295e-12, 2.15334370930989483, 0.505855814615885357, 3, false),
(4, 1.80,  0.0027281206, 1.81566416422526022, 0.549645741780599106, 3, false),
(5, 1.80, 0.00030474186, 1.92916208902994835, 0.531913503011067768, 3, false),
(6, 1.80, 4.0966294e-05, 1.99691992865668366, 0.523411814371744888, 3, false),
(7, 1.80, 4.8277462e-06, 2.06023915608723929, 0.516692860921223907, 3, false),
(8, 1.80,  6.512528e-07, 2.10110795762803804, 0.512618255615234109, 3, false),
(9, 1.80, 8.6860004e-08, 2.12062293158637161, 0.510943349202474084, 3, false),
(10, 1.80, 1.1474937e-08, 2.13734046088324670, 0.509422047932942657, 3, false),
(11, 1.80, 1.4900238e-09, 2.13370751274956616, 0.509656016031900805, 3, false),
(12, 1.80, 1.7737321e-10, 2.12671017116970473, 0.509776560465494577, 3, false),
(13, 1.80, 2.2386587e-11, 2.14743737114800304, 0.508159637451171986, 3, false),
(14, 1.80, 2.8892214e-12, 2.10544586181640536, 0.512052663167317790, 3, false),
(15, 1.80, 8.5791121e-13, 2.17534840901692661, 0.505950164794921720, 3, false),
(4, 1.85,  0.0023322608, 1.82287784152560750, 0.551604970296223796, 3, false),
(5, 1.85, 0.00025747909, 1.97668134901258674, 0.528661346435546742, 3, false),
(6, 1.85, 3.1810889e-05, 2.02382388644748223, 0.522790781656901182, 3, false),
(7, 1.85, 3.8746264e-06, 2.08198835584852526, 0.516882069905598818, 3, false),
(8, 1.85, 4.9082302e-07, 2.11999257405599018, 0.513011932373046986, 3, false),
(9, 1.85, 6.2341591e-08, 2.13356204562717044, 0.511795806884765447, 3, false),
(10, 1.85, 7.8301776e-09, 2.15372229682074634, 0.509919484456380134, 3, false),
(11, 1.85, 1.0020588e-09, 2.16671735975477509, 0.508801015218098618, 3, false),
(12, 1.85, 1.1885262e-10, 2.17137230767144151, 0.508251190185546764, 3, false),
(13, 1.85, 1.5041179e-11, 2.18463965521918491, 0.507171376546223907, 3, false),
(14, 1.85, 1.8789625e-12, 2.18464338514539991, 0.506948089599609020, 3, false),
(15, 1.85, 5.1887707e-13, 2.20492858886718768, 0.505540466308593617, 3, false),
(16, 1.85, 4.9637721e-13, 2.24612935384114509, 0.502656555175781339, 3, false),
(4, 1.90,  0.0020225494, 1.84992726643880223, 0.550009918212890803, 3, false),
(5, 1.90,  0.0002257929, 2.01164194742838554, 0.526721445719401160, 3, false),
(6, 1.90, 2.6486913e-05, 2.06700524224175330, 0.520410919189453147, 3, false),
(7, 1.90, 3.2374813e-06, 2.09541609022352526, 0.517656707763671786, 3, false),
(8, 1.90, 3.8577121e-07, 2.12510257297092009, 0.514389292399088371, 3, false),
(9, 1.90, 4.6617227e-08, 2.15220421685112884, 0.511920928955078125, 3, false),
(10, 1.90, 5.5628174e-09, 2.17061513264973893, 0.510152435302734353, 3, false),
(11, 1.90, 6.9286019e-10, 2.18844790988498250, 0.508651479085286296, 3, false),
(12, 1.90, 7.9290365e-11, 2.19517669677734384, 0.507954661051432166, 3, false),
(13, 1.90, 9.8965337e-12, 2.20817175971137170, 0.506905364990234530, 3, false),
(14, 1.90, 1.2251775e-12, 2.21245371500651000, 0.506451670328776249, 3, false),
(15, 1.90, 3.2863528e-13, 2.22906494140624956, 0.505279541015624778, 3, false),
(16, 1.90, 3.1562028e-13, 2.26889309353298607, 0.502519734700520915, 3, false),
(4, 1.95,   0.001769364, 1.88333621554904518, 0.547602589925130112, 3, false),
(5, 1.95,  0.0001980031, 2.04016469319661509, 0.525634002685546831, 3, false),
(6, 1.95, 2.3026206e-05, 2.08590850830078134, 0.520696258544921631, 3, false),
(7, 1.95,  2.730625e-06, 2.10214114718967027, 0.519080352783203303, 3, false),
(8, 1.95, 3.0568394e-07, 2.13631846110026080, 0.515235646565755157, 3, false),
(9, 1.95, 3.5339694e-08, 2.16356930202907982, 0.512669626871744888, 3, false),
(10, 1.95, 3.9532683e-09, 2.18178999159071196, 0.510828908284505112, 3, false),
(11, 1.95,  4.776842e-10, 2.20117441813151027, 0.509173838297526049, 3, false),
(12, 1.95, 5.1762217e-11, 2.21349809434678813, 0.508074696858723862, 3, false),
(13, 1.95, 6.3266466e-12, 2.22576209174262019, 0.507048288981119866, 3, false),
(14, 1.95, 7.6885514e-13, 2.23883175320095473, 0.506095631917317768, 3, false),
(15, 1.95, 2.0931511e-13, 2.24868621826171866, 0.505333709716796697, 3, false),
(16, 1.95,  2.050985e-13, 2.28954569498697902, 0.502578226725260535, 3, false),
(4, 2.00,  0.0015580009, 1.90694291856553799, 0.546800994873046786, 3, false),
(5, 2.00, 0.00017346297, 2.06404741075303821, 0.525147755940755356, 3, false),
(6, 2.00, 1.9950367e-05, 2.10745629204644125, 0.520621490478515692, 3, false),
(7, 2.00, 2.3314457e-06, 2.13151058620876643, 0.518270619710286762, 3, false),
(8, 2.00, 2.4596985e-07, 2.14249894883897563, 0.516482289632161362, 3, false),
(9, 2.00, 2.7354414e-08, 2.17356550428602446, 0.513518524169921942, 3, false),
(10, 2.00, 2.9017603e-09, 2.20186072455512116, 0.510932668050130157, 3, false),
(11, 2.00,  3.361087e-10, 2.21397179497612839, 0.509688568115234331, 3, false),
(12, 2.00, 3.6829545e-11, 2.24148000081380294, 0.507639821370442501, 3, false),
(13, 2.00, 4.1553645e-12, 2.24892120361328107, 0.506914011637369821, 3, false),
(14, 2.00, 5.2930439e-13, 2.25466528998480920, 0.506470998128255023, 3, false),
(15, 2.00, 1.4040047e-13, 2.25586632622612848, 0.506162770589192568, 3, false),
(16, 2.00, 1.3802599e-13, 2.30979546440972205, 0.502591959635416807, 3, false),
(4, 2.05,  0.0014145059, 1.92870330810546897, 0.545942433675130068, 3, false),
(5, 2.05, 0.00015484818, 2.08155195448133679, 0.525099436442057366, 3, false),
(6, 2.05, 1.7406431e-05, 2.13673621283637205, 0.519232940673827970, 3, false),
(7, 2.05,  2.028536e-06, 2.17350582546657956, 0.515741221110026071, 3, false),
(8, 2.05, 2.0866124e-07, 2.15772077772352455, 0.516779327392578147, 3, false),
(9, 2.05, 2.2532863e-08, 2.17791086832682312, 0.514518483479817657, 3, false),
(10, 2.05,  2.312491e-09, 2.21550852457682268, 0.511269378662109308, 3, false),
(11, 2.05,   2.58385e-10, 2.23040584988064206, 0.509801991780599040, 3, false),
(12, 2.05, 2.7699008e-11, 2.25799238416883696, 0.507725779215494555, 3, false),
(13, 2.05, 3.0548308e-12, 2.26661597357855804, 0.506922658284505112, 3, false),
(14, 2.05, 3.8241342e-13, 2.22907613118489589, 0.509736633300781228, 3, false),
(15, 2.05, 1.0054434e-13, 2.24838222927517339, 0.508189392089843595, 3, false),
(16, 2.05, 9.8986316e-14, 2.32577260335286473, 0.502707163492838727, 3, false),
(4, 2.10,  0.0012905133, 1.94683447943793375, 0.545642852783203014, 3, false),
(5, 2.10, 0.00013825796, 2.09675140380859348, 0.525319671630859353, 3, false),
(6, 2.10, 1.5069774e-05, 2.16241302490234455, 0.518203481038411518, 3, false),
(7, 2.10,  1.725143e-06, 2.21955549452039946, 0.512659962972005001, 3, false),
(8, 2.10, 1.7989863e-07, 2.17143944634331598, 0.517146046956380223, 3, false),
(9, 2.10, 1.9294534e-08, 2.21104380289713598, 0.513404083251952970, 3, false),
(10, 2.10, 1.8788313e-09, 2.22412465413411553, 0.511929066975911451, 3, false),
(11, 2.10, 2.0627664e-10, 2.23974558512369804, 0.510313161214192568, 3, false),
(12, 2.10, 2.1071284e-11, 2.26767900254991339, 0.508244578043619777, 3, false),
(13, 2.10, 2.2821409e-12, 2.22048051622178777, 0.511962127685547053, 3, false),
(14, 2.10, 2.8772368e-13, 2.25465596516927080, 0.509201558430989576, 3, false),
(15, 2.10, 7.4977376e-14, 2.26222398546006831, 0.508659871419270826, 3, false),
(16, 2.10, 7.2698728e-14, 2.35554487440321170, 0.501833343505859286, 3, false),
(4, 2.15,  0.0011992553, 1.95983327229817705, 0.545700836181640558, 3, false),
(5, 2.15, 0.00012594864, 2.10787777370876706, 0.525670623779296853, 3, false),
(6, 2.15, 1.3423187e-05, 2.17432640923394116, 0.518426767985025960, 3, false),
(7, 2.15, 1.5005507e-06, 2.23297949896918446, 0.512734731038411051, 3, false),
(8, 2.15, 1.5976257e-07, 2.19627329508463598, 0.516251881917317523, 3, false),
(9, 2.15, 1.6805329e-08, 2.22688106960720544, 0.513256072998046653, 3, false),
(10, 2.15, 1.6163274e-09, 2.22816043429904509, 0.512646738688151027, 3, false),
(11, 2.15, 1.7547081e-10, 2.25718299018012170, 0.510106658935546631, 3, false),
(12, 2.15, 1.7308758e-11, 2.27178565131293375, 0.508858489990234419, 3, false),
(13, 2.15, 1.8724472e-12, 2.23387468126085098, 0.512366485595703081, 3, false),
(14, 2.15, 2.1326748e-13, 2.30832027859157973, 0.506116994222005290, 3, false),
(15, 2.15, 5.6503445e-14, 2.31436089409722179, 0.505541992187499734, 3, false),
(16, 2.15, 5.4697116e-14, 2.37556152343749982, 0.501582845052083282, 3, false),
(4, 2.20,  0.0011025179, 1.97344377305772567, 0.546037038167317745, 3, false),
(5, 2.20, 0.00011280381, 2.11950395372178768, 0.526264699300130090, 3, false),
(6, 2.20, 1.1683843e-05, 2.18673960367838571, 0.518857574462890714, 3, false),
(7, 2.20, 1.2652877e-06, 2.24713083902994715, 0.512998199462890270, 3, false),
(8, 2.20, 1.3127215e-07, 2.26494496663411438, 0.511482493082681899, 3, false),
(9, 2.20, 1.3722152e-08, 2.27114783393012099, 0.510934702555338682, 3, false),
(10, 2.20, 1.3557514e-09, 2.27525821261935723, 0.510403188069661562, 3, false),
(11, 2.20, 1.3732683e-10, 2.29960717095269063, 0.508342234293619577, 3, false),
(12, 2.20, 1.3462918e-11, 2.30357954237196205, 0.507871754964192901, 3, false),
(13, 2.20, 1.4828143e-12, 2.25579172770182224, 0.511590830485025849, 3, false),
(14, 2.20, 1.5240984e-13, 2.33169013129340330, 0.505726114908854329, 3, false),
(15, 2.20, 4.2666582e-14, 2.34941474066840250, 0.504525756835937589, 3, false),
(4, 2.25,  0.0010312612, 1.98338402642144063, 0.546487172444661384, 3, false),
(5, 2.25, 0.00010319811, 2.12779930962456554, 0.526887766520182321, 3, false),
(6, 2.25, 1.0418375e-05, 2.19571753607855902, 0.519317881266276093, 3, false),
(7, 2.25, 1.0951963e-06, 2.25832807752821108, 0.513249460856119444, 3, false),
(8, 2.25, 1.1061086e-07, 2.28025631374782956, 0.511336008707682144, 3, false),
(9, 2.25, 1.1327543e-08, 2.29882388644748259, 0.509762827555338527, 3, false),
(10, 2.25, 1.0994197e-09, 2.30602637396918420, 0.509100596110026005, 3, false),
(11, 2.25, 1.0771979e-10, 2.31697370741102437, 0.508083852132161451, 3, false),
(12, 2.25, 1.0287677e-11, 2.32586585150824599, 0.507328033447265736, 3, false),
(13, 2.25, 9.7149266e-13, 2.33827904595269054, 0.506330617268880179, 3, false),
(14, 2.25, 1.1007942e-13, 2.34637485080295116, 0.505700174967447791, 3, false),
(15, 2.25, 3.4634308e-14, 2.34067925347222205, 0.505843098958333126, 3, false),
(4, 2.30, 0.00096769063, 1.99225379096137201, 0.547050221761067768, 3, false),
(5, 2.30, 9.4727065e-05, 2.13487870958116410, 0.527610015869140359, 3, false),
(6, 2.30, 9.3153191e-06, 2.20337880452473955, 0.519864654541015603, 3, false),
(7, 2.30, 9.4730434e-07, 2.26955888536241268, 0.513473765055338482, 3, false),
(8, 2.30, 9.3071744e-08, 2.28904028998480946, 0.511767323811848751, 3, false),
(9, 2.30, 9.2769408e-09, 2.31326989067925348, 0.509712473551432010, 3, false),
(10, 2.30, 8.7844109e-10, 2.32252756754557277, 0.508909352620442790, 3, false),
(11, 2.30, 8.3103511e-11, 2.33217688666449563, 0.507999928792317590, 3, false),
(12, 2.30, 7.7409942e-12, 2.34049835205078072, 0.507298533121744888, 3, false),
(13, 2.30, 7.5421465e-13, 2.34607832166883634, 0.506789906819661407, 3, false),
(14, 2.30, 8.5861563e-14, 2.35363701714409723, 0.506177775065104196, 3, false),
(15, 2.30, 2.7909572e-14, 2.38203667534722197, 0.504256184895833348, 3, false),
(4, 2.35, 0.00091109603, 2.00018734402126697, 0.547697194417317679, 3, false),
(5, 2.35, 8.7362907e-05, 2.14067128499348991, 0.528427378336588482, 3, false),
(6, 2.35, 8.3763398e-06, 2.20968983968098920, 0.520482126871744888, 3, false),
(7, 2.35, 8.2005622e-07, 2.28155059814453187, 0.513612620035807210, 3, false),
(8, 2.35, 7.8056328e-08, 2.30517968071831536, 0.511560312906900849, 3, false),
(9, 2.35, 7.5761021e-09, 2.32373233371310839, 0.509988657633463127, 3, false),
(10, 2.35, 6.9623612e-10, 2.33070356580946259, 0.509332529703776182, 3, false),
(11, 2.35, 6.4454973e-11, 2.35038265652126777, 0.507772572835286540, 3, false),
(12, 2.35, 6.2931201e-12, 2.35220659044053804, 0.507554880777994710, 3, false),
(13, 2.35, 5.9923646e-13, 2.34172736273871562, 0.508011372884114687, 3, false),
(14, 2.35, 6.6065931e-14, 2.35412190755208384, 0.507126871744791652, 3, false),
(15, 2.35, 2.4012349e-14, 2.35584513346354107, 0.507138061523437322, 3, false),
(4, 2.40, 0.00087048784, 2.00592770046658009, 0.548258209228515314, 3, false),
(5, 2.40, 8.2266738e-05, 2.14426320393880232, 0.529153188069661606, 3, false),
(6, 2.40, 7.7433845e-06, 2.21353166368272536, 0.521029408772786695, 3, false),
(7, 2.40, 7.3185707e-07, 2.29392649332682330, 0.513477325439453236, 3, false),
(8, 2.40, 6.7906614e-08, 2.30989430745442670, 0.512092336018880268, 3, false),
(9, 2.40, 6.4461408e-09, 2.33141225179036482, 0.510267893473307144, 3, false),
(10, 2.40, 5.8576773e-10, 2.34538455539279589, 0.509139251708984220, 3, false),
(11, 2.40, 5.5096404e-11, 2.36717105441623232, 0.507470448811848884, 3, false),
(12, 2.40, 5.2638546e-12, 2.37904713948567714, 0.506586964925130334, 3, false),
(13, 2.40, 4.7890714e-13, 2.33895043267144098, 0.509288279215494799, 3, false),
(14, 2.40, 5.2262697e-14, 2.35107828776041705, 0.508315022786458126, 3, false),
(15, 2.40, 2.0930731e-14, 2.37529296874999973, 0.505843098958333126, 3, false),
(16, 2.40, 2.0700099e-14, 2.42124565972222161, 0.504003906250000133, 3, false),
(4, 2.45, 0.00082508682, 2.01244015163845535, 0.548992156982421986, 3, false),
(5, 2.45, 7.6964398e-05, 2.14864959716796866, 0.530002593994140625, 3, false),
(6, 2.45, 7.0753467e-06, 2.23052520751953054, 0.520584869384765669, 3, false),
(7, 2.45, 6.3897015e-07, 2.30423973931206483, 0.513812510172525938, 3, false),
(8, 2.45, 5.7196036e-08, 2.31863352457682304, 0.512532806396484242, 3, false),
(9, 2.45, 5.2826195e-09, 2.33694373236762143, 0.510904693603515647, 3, false),
(10, 2.45, 4.8663691e-10, 2.36320241292317723, 0.508957163492838260, 3, false),
(11, 2.45, 4.4807014e-11, 2.38042721218533027, 0.507595062255859042, 3, false),
(12, 2.45, 4.1839375e-12, 2.38868526882595456, 0.506927235921224018, 3, false),
(13, 2.45,  3.845637e-13, 2.33679080539279571, 0.511076100667317568, 3, false),
(14, 2.45, 4.0956394e-14, 2.35007866753472294, 0.509834798177083215, 3, false),
(15, 2.45, 1.8479256e-14, 2.34827524820963562, 0.509776051839192723, 3, false),
(16, 2.45, 1.7927619e-14, 2.45225253634982643, 0.503007507324218950, 3, false),
(4, 2.50, 0.00079279905, 2.01718461778428892, 0.549589284261067679, 3, false),
(5, 2.50, 7.3317529e-05, 2.15946265326605946, 0.529833730061848529, 3, false),
(6, 2.50, 6.4884782e-06, 2.25309499104817679, 0.519467417399088638, 3, false),
(7, 2.50,  5.749415e-07, 2.30846947564019045, 0.514437103271484064, 3, false),
(8, 2.50, 5.0363914e-08, 2.33213212754991250, 0.512434641520182366, 3, false),
(9, 2.50, 4.5804732e-09, 2.35149417453342036, 0.510761769612630090, 3, false),
(10, 2.50,  4.201735e-10, 2.37159847683376723, 0.509220123291015292, 3, false),
(11, 2.50, 3.7877442e-11, 2.38795047336154509, 0.507892100016275494, 3, false),
(12, 2.50, 3.5189578e-12, 2.39123280843099018, 0.507511138916015181, 3, false),
(13, 2.50, 3.2547081e-13, 2.39824133978949661, 0.506931304931640403, 3, false),
(14, 2.50, 3.6529298e-14, 2.37836642795138831, 0.508345540364583459, 3, false),
(15, 2.50, 1.6499646e-14, 2.43243543836805465, 0.504073079427083348, 3, false),
(16, 2.50, 1.6277483e-14, 2.46149902343749982, 0.503055826822916718, 3, false),
// KERNEL_ROWS_END
];

// ------------------------------------------------------------------- tests

#[cfg(test)]
mod tests {
    use super::*;

    fn lcg(seed: &mut u64) -> f64 {
        *seed = seed
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        ((*seed >> 11) as f64) / ((1u64 << 53) as f64)
    }

    struct Case {
        uvw: Vec<f64>,
        freq: Vec<f64>,
        vis: Vec<Complex<f64>>,
        wgt: Vec<f64>,
        opts: Options,
    }

    fn case(nx: usize, ny: usize, field: f64, wmax: f64, nrow: usize, seed: u64) -> Case {
        let mut s = seed;
        let freq = vec![1.0e9, 1.2e9, 1.4e9];
        let dx = field / nx as f64;
        let lam = 1.4e9 / C_LIGHT;
        let mut uvw = Vec::new();
        for _ in 0..nrow {
            uvw.push((lcg(&mut s) - 0.5) * 0.9 / dx / lam);
            uvw.push((lcg(&mut s) - 0.5) * 0.9 / dx / lam);
            uvw.push((lcg(&mut s) - 0.5) * 2.0 * wmax / lam);
        }
        let n = nrow * freq.len();
        let vis = (0..n)
            .map(|_| Complex::new(lcg(&mut s) - 0.5, lcg(&mut s) - 0.5))
            .collect();
        let wgt = (0..n).map(|_| 0.5 + lcg(&mut s)).collect();
        let opts = Options {
            nx,
            ny,
            pixsize_x: dx,
            pixsize_y: dx,
            epsilon: 1e-9,
            ..Options::default()
        };
        Case {
            uvw,
            freq,
            vis,
            wgt,
            opts,
        }
    }

    fn dft_dirty(c: &Case) -> Vec<f64> {
        let (nx, ny) = (c.opts.nx, c.opts.ny);
        let mut out = vec![0.0; nx * ny];
        let nchan = c.freq.len();
        for i in 0..nx {
            let l = (i as f64 - (nx / 2) as f64) * c.opts.pixsize_x;
            for j in 0..ny {
                let m = (j as f64 - (ny / 2) as f64) * c.opts.pixsize_y;
                let nm1 = (1.0 - l * l - m * m).sqrt() - 1.0;
                let mut acc = 0.0;
                for (r, row) in c.uvw.as_chunks::<3>().0.iter().enumerate() {
                    for (ch, f) in c.freq.iter().enumerate() {
                        let k = f / C_LIGHT;
                        let ph = 2.0 * PI * k * (row[0] * l + row[1] * m + row[2] * nm1);
                        let v = c.vis[r * nchan + ch] * c.wgt[r * nchan + ch];
                        acc += v.re * ph.cos() - v.im * ph.sin();
                    }
                }
                out[i * ny + j] = acc;
            }
        }
        out
    }

    fn rel_linf(a: &[f64], b: &[f64]) -> f64 {
        let peak = b.iter().fold(0.0_f64, |m, x| m.max(x.abs()));
        a.iter()
            .zip(b)
            .fold(0.0_f64, |m, (x, y)| m.max((x - y).abs()))
            / peak
    }

    #[test]
    fn table_and_sizes() {
        assert_eq!(kernel_count(), 939);
        let first = kernel_row(0).unwrap();
        assert_eq!((first.w, first.ndim, first.singleprec), (4, 2, true));
        assert_eq!(first.epsilon, 0.027638471);
        let last = kernel_row(938).unwrap();
        assert_eq!((last.w, last.ndim, last.singleprec), (16, 3, false));
        assert_eq!(good_size_complex(13), 14);
        assert_eq!(good_size_complex(97), 98);
        assert_eq!(good_size_complex(181), 189);
        assert_eq!(good_size_complex(1025), 1029);
        assert_eq!(good_size_complex(7), 7);
    }

    #[test]
    fn gauss_legendre_integrates_polynomials() {
        let (x, w) = gauss_legendre_symmetric(10);
        // Even polynomial x^8 over [-1, 1] = 2/9.
        let integral: f64 = x.iter().zip(&w).map(|(x, w)| w * x.powi(8)).sum();
        assert!((integral - 2.0 / 9.0).abs() < 1e-14, "{integral}");
        let total: f64 = w.iter().sum();
        assert!((total - 2.0).abs() < 1e-14);
    }

    #[test]
    fn polynomial_kernel_matches_es() {
        for &index in &[0usize, 200, 500, 938] {
            let k = EsKernel::new(index).unwrap();
            let mut worst = 0.0_f64;
            for i in 0..2001 {
                let v = -1.0 + 2.0 * i as f64 / 2000.0;
                worst = worst.max((k.eval(v) - k.phi(v)).abs());
            }
            let eps = kernel_row(index).unwrap().epsilon;
            assert!(worst < eps.max(1e-13), "index {index}: {worst}");
        }
    }

    #[test]
    fn vis2dirty_matches_dft() {
        for (nx, ny, field, wmax) in [(32, 32, 0.2, 500.0), (32, 16, 0.05, 50.0)] {
            let c = case(nx, ny, field, wmax, 60, 7);
            let mut dirty = vec![0.0; nx * ny];
            vis2dirty(
                &c.opts,
                &c.uvw,
                &c.freq,
                &c.vis,
                Some(&c.wgt),
                None,
                &mut dirty,
            )
            .unwrap();
            let err = rel_linf(&dirty, &dft_dirty(&c));
            assert!(err < 1e-8, "{nx}x{ny}: {err}");
        }
    }

    #[test]
    fn adjoint_and_thread_independent() {
        let c = case(32, 32, 0.25, 800.0, 50, 11);
        let mut s = 3u64;
        let x: Vec<f64> = (0..32 * 32).map(|_| lcg(&mut s) - 0.5).collect();
        let mut ax = vec![Complex::new(0.0, 0.0); c.vis.len()];
        dirty2vis(&c.opts, &c.uvw, &c.freq, &x, Some(&c.wgt), None, &mut ax).unwrap();
        let mut aty = vec![0.0; 32 * 32];
        vis2dirty(
            &c.opts,
            &c.uvw,
            &c.freq,
            &c.vis,
            Some(&c.wgt),
            None,
            &mut aty,
        )
        .unwrap();
        let lhs: f64 = ax.iter().zip(&c.vis).map(|(a, y)| (a.conj() * y).re).sum();
        let rhs: f64 = x.iter().zip(&aty).map(|(a, b)| a * b).sum();
        let na = ax.iter().map(|a| a.norm_sqr()).sum::<f64>().sqrt();
        let ny = c.vis.iter().map(|a| a.norm_sqr()).sum::<f64>().sqrt();
        assert!((lhs - rhs).abs() / (na * ny) < 1e-13, "{lhs} {rhs}");
        let run = |threads: usize| {
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()
                .unwrap();
            pool.install(|| {
                let mut d = vec![0.0; 32 * 32];
                vis2dirty(&c.opts, &c.uvw, &c.freq, &c.vis, Some(&c.wgt), None, &mut d).unwrap();
                let mut v = vec![Complex::new(0.0, 0.0); c.vis.len()];
                dirty2vis(&c.opts, &c.uvw, &c.freq, &x, Some(&c.wgt), None, &mut v).unwrap();
                (d, v)
            })
        };
        let (d1, v1) = run(1);
        let (d3, v3) = run(3);
        assert!(d1.iter().zip(&d3).all(|(a, b)| a.to_bits() == b.to_bits()));
        assert!(
            v1.iter()
                .zip(&v3)
                .all(|(a, b)| a.re.to_bits() == b.re.to_bits() && a.im.to_bits() == b.im.to_bits())
        );
    }

    #[test]
    fn single_precision_matches_dft() {
        let c = case(32, 32, 0.2, 400.0, 60, 5);
        let vis: Vec<Complex<f32>> = c
            .vis
            .iter()
            .map(|v| Complex::new(v.re as f32, v.im as f32))
            .collect();
        let wgt: Vec<f32> = c.wgt.iter().map(|&w| w as f32).collect();
        let opts = Options {
            epsilon: 1e-4,
            ..c.opts
        };
        let mut dirty = vec![0.0_f32; 32 * 32];
        vis2dirty(&opts, &c.uvw, &c.freq, &vis, Some(&wgt), None, &mut dirty).unwrap();
        let d: Vec<f64> = dirty.iter().map(|&x| x as f64).collect();
        let err = rel_linf(&d, &dft_dirty(&c));
        assert!(err < 1e-3, "{err}");
    }

    #[test]
    fn rejects_bad_input() {
        let c = case(32, 32, 0.2, 400.0, 10, 1);
        let mut dirty = vec![0.0; 31 * 32];
        let opts = Options { nx: 31, ..c.opts };
        assert!(vis2dirty(&opts, &c.uvw, &c.freq, &c.vis, None, None, &mut dirty).is_err());
        let mut dirty = vec![0.0; 32 * 32];
        let freq = vec![1.4e9, 1.2e9, 1.0e9];
        assert!(vis2dirty(&c.opts, &c.uvw, &freq, &c.vis, None, None, &mut dirty).is_err());
    }
}
