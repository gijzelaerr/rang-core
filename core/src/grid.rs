//! W-stacking gridder, ported from WSClean 3.6-1.
//!
//! A Rust translation of the inversion path of `gridding/wstackinggridder.cpp`,
//! `gridding/wsmsgridder.cpp`, `gridding/msgridderdata.h`,
//! `gridding/msprovidercollection.cpp` and the PSF normalisation in
//! `main/wsclean.cpp` of WSClean 3.6 (André Offringa and contributors,
//! GPL-3.0; <https://gitlab.com/aroffringa/wsclean>), as read from the verified
//! Debian source in `outputs/wsclean-3.6-1-source-20261029/`. The translation
//! is part of Rang (GPL-3.0-or-later). Validation protocol:
//! `research/core-c-gridder.md` (wave 1 task C); the layer-parallel
//! structure is big-plan task P2 (`research/p2-gridder.md`).
//!
//! Differences from the original, fixed in the protocols: the grid, the FFT
//! and the kernel correction are double precision (WSClean grids in single
//! precision with FFTW); the kernel correction is a direct type-III DCT sum.
//! Samples are bucketed by w-layer once; the dirty image and the PSF are
//! gridded, transformed and projected in the same pass over each layer; the
//! layers run in parallel (rayon, `RAYON_NUM_THREADS`), each into its own
//! projected image, and the projected images are added to the result in
//! layer order, so the sum is the serial one and the result does not depend
//! on the thread count. Only the real (non-complex) image path, one
//! polarization and one pass are ported, which is how rang runs WSClean.

use rayon::prelude::*;
use std::f64::consts::PI;

/// Speed of light as casacore and aocommon use it.
pub const C_LIGHT: f64 = 299792458.0;

/// Kaiser–Bessel window parameter of WSClean's default kernel.
const KB_ALPHA: f64 = 8.6;

/// Layers whose projected images are held at once before they are added in
/// layer order; fixed, so memory is bounded and independent of threads.
const LAYER_BATCH: usize = 16;

#[derive(Clone, Copy, Debug, PartialEq)]
struct C64 {
    re: f64,
    im: f64,
}

impl C64 {
    const ZERO: C64 = C64 { re: 0.0, im: 0.0 };
    fn new(re: f64, im: f64) -> C64 {
        C64 { re, im }
    }
    fn mul(self, o: C64) -> C64 {
        C64::new(
            self.re * o.re - self.im * o.im,
            self.re * o.im + self.im * o.re,
        )
    }
    fn add(self, o: C64) -> C64 {
        C64::new(self.re + o.re, self.im + o.im)
    }
    fn sub(self, o: C64) -> C64 {
        C64::new(self.re - o.re, self.im - o.im)
    }
    fn conj(self) -> C64 {
        C64::new(self.re, -self.im)
    }
    fn expi(theta: f64) -> C64 {
        let (s, c) = theta.sin_cos();
        C64::new(c, s)
    }
}

/// Image and kernel settings, as `WStackingGridder`'s constructor takes them.
#[derive(Clone, Copy, Debug)]
pub struct Settings {
    pub width: usize,
    pub height: usize,
    /// Pixel size in radians (`-scale`).
    pub pixel_size_x: f64,
    pub pixel_size_y: f64,
    /// Full kernel width in pixels (7).
    pub kernel_size: usize,
    /// Number of sub-cell kernels (1023).
    pub oversampling: usize,
    /// `-wstack-nwlayers`.
    pub n_w_layers: usize,
    /// `-padding` (1.2 by default): the gridder works on an image enlarged by
    /// this factor, rounded up to a multiple of four pixels, and the result is
    /// trimmed back to `width` x `height` (`Settings::paddedImageWidth`,
    /// `Image::Trim`).
    pub padding: f64,
}

impl Settings {
    /// The padded inversion size, as `main/settings.cpp` computes it.
    pub fn padded_size(&self) -> (usize, usize) {
        let pad = |n: usize| {
            let mut padded = (n as f64 * self.padding).ceil() as usize;
            padded += (4 - padded % 4) % 4;
            padded
        };
        (pad(self.width), pad(self.height))
    }
}

/// `aocommon::Image::Trim`: the centred `out_width` x `out_height` cut.
fn trim(
    input: &[f64],
    in_width: usize,
    in_height: usize,
    out_width: usize,
    out_height: usize,
) -> Vec<f64> {
    let start_x = (in_width - out_width) / 2;
    let start_y = (in_height - out_height) / 2;
    let mut output = Vec::with_capacity(out_width * out_height);
    for y in start_y..start_y + out_height {
        output
            .extend_from_slice(&input[y * in_width + start_x..y * in_width + start_x + out_width]);
    }
    output
}

/// Per-visibility inputs: one Stokes sample and two weights per (row, channel).
pub struct Inputs<'a> {
    /// `nrow * 3` metres, MS convention.
    pub uvw: &'a [f64],
    /// `nchan` Hz.
    pub frequencies: &'a [f64],
    /// `nrow * nchan` interleaved complex singles (the reader's Stokes sample).
    pub data: &'a [f32],
    /// `nrow * nchan` visibility weights as the reader delivers them
    /// (zero where flagged).
    pub weights: &'a [f32],
    /// `nrow * nchan` imaging weights (`IMAGING_WEIGHT_SPECTRUM`).
    pub imaging_weights: &'a [f32],
}

/// Counters that WSClean logs or writes to the FITS header.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Stats {
    /// `total_weight_` = `WSCIMGWG` = `WSCNORMF` for one polarization.
    pub image_weight: f64,
    /// `gridded_visibility_count_` (`WSCNVIS`).
    pub gridded_count: u64,
    /// `visibility_weight_sum_` (`WSCVWSUM`).
    pub visibility_weight_sum: f64,
    pub max_gridded_weight: f64,
    pub min_w: f64,
    pub max_w: f64,
    /// `1 / PSF[centre]` before normalisation (`psfNormalizationFactor`).
    pub psf_normalization: f64,
}

/// Dirty image and PSF, `width * height` each in `[x + y * width]` order,
/// which is FITS pixel order.
pub struct Products {
    pub dirty: Vec<f64>,
    pub psf: Vec<f64>,
    pub stats: Stats,
}

/// `bessel0`: unnormalised modified Bessel function of order zero by series.
fn bessel0(x: f64, precision: f64) -> f64 {
    let mut d = 0.0;
    let mut ds = 1.0;
    let mut sum = 1.0;
    loop {
        d += 2.0;
        ds *= x * x / (d * d);
        sum += ds;
        if ds <= sum * precision {
            break;
        }
    }
    sum
}

/// `makeKaiserBesselKernel` with `withSinc = true`: the oversampled 1-D
/// kernel of `kernel_size * oversampling` doubles.
pub fn kaiser_bessel_kernel(kernel_size: usize, oversampling: usize) -> Vec<f64> {
    let n = kernel_size * oversampling;
    let mid = n / 2;
    let mut kernel = vec![0.0; n];
    let filter_ratio = 1.0 / oversampling as f64;
    let mut sinc = vec![0.0; mid + 1];
    sinc[0] = filter_ratio;
    for (i, value) in sinc.iter_mut().enumerate().skip(1) {
        let x = i as f64;
        *value = (PI * filter_ratio * x).sin() / (PI * x);
    }
    let norm = oversampling as f64 / bessel0(KB_ALPHA, 1e-8);
    for i in 0..=mid {
        let term = i as f64 / mid as f64;
        kernel[mid + i] = sinc[i] * bessel0(KB_ALPHA * (1.0 - term * term).sqrt(), 1e-8) * norm;
    }
    for i in 0..mid {
        kernel[i] = kernel[n - 1 - i];
    }
    kernel
}

/// The `oversampling` sub-cell kernels of `kernel_size` taps, indexed as
/// WSClean's `_griddingKernels` (reversed order), stored flat:
/// kernel `k`, tap `x` at `k * kernel_size + x`.
fn gridding_kernels(kernel_1d: &[f64], kernel_size: usize, oversampling: usize) -> Vec<f64> {
    let mut kernels = vec![0.0; kernel_size * oversampling];
    for i in 0..oversampling {
        let start = (oversampling - i - 1) * kernel_size;
        for (x, value) in kernels[start..start + kernel_size].iter_mut().enumerate() {
            *value = kernel_1d[x * oversampling + i];
        }
    }
    kernels
}

fn is_power_of_two(n: usize) -> bool {
    n != 0 && n & (n - 1) == 0
}

/// A precomputed 1-D transform of one length and sign: radix-2 for powers of
/// two, Bluestein's algorithm (over a power-of-two convolution) otherwise.
/// `sign` is +1 for the unnormalised backward transform (FFTW
/// `FFTW_BACKWARD`) and -1 for the forward one.
struct FftPlan {
    n: usize,
    /// `expi(sign * 2 pi k / n)` for radix-2 lengths.
    twiddles: Vec<C64>,
    bluestein: Option<Bluestein>,
}

struct Bluestein {
    m: usize,
    chirp: Vec<C64>,
    /// Forward transform of the symmetric conjugate chirp, length `m`.
    b_fft: Vec<C64>,
    forward: Box<FftPlan>,
    backward: Box<FftPlan>,
}

impl FftPlan {
    fn new(n: usize, sign: f64) -> FftPlan {
        if n <= 1 || is_power_of_two(n) {
            let twiddles = (0..n / 2)
                .map(|k| C64::expi(sign * 2.0 * PI * k as f64 / n as f64))
                .collect();
            return FftPlan {
                n,
                twiddles,
                bluestein: None,
            };
        }
        let mut m = 1;
        while m < 2 * n - 1 {
            m <<= 1;
        }
        let chirp: Vec<C64> = (0..n)
            .map(|k| C64::expi(sign * PI * ((k * k) % (2 * n)) as f64 / n as f64))
            .collect();
        let forward = Box::new(FftPlan::new(m, -1.0));
        let backward = Box::new(FftPlan::new(m, 1.0));
        let mut b = vec![C64::ZERO; m];
        for k in 0..n {
            b[k] = chirp[k].conj();
            if k > 0 {
                b[m - k] = chirp[k].conj();
            }
        }
        forward.radix2(&mut b);
        FftPlan {
            n,
            twiddles: Vec::new(),
            bluestein: Some(Bluestein {
                m,
                chirp,
                b_fft: b,
                forward,
                backward,
            }),
        }
    }

    fn len(&self) -> usize {
        self.n
    }

    /// In-place radix-2 transform with the precomputed twiddles.
    fn radix2(&self, data: &mut [C64]) {
        let n = data.len();
        let mut j = 0;
        for i in 1..n {
            let mut bit = n >> 1;
            while j & bit != 0 {
                j ^= bit;
                bit >>= 1;
            }
            j |= bit;
            if i < j {
                data.swap(i, j);
            }
        }
        let mut len = 2;
        while len <= n {
            let step = n / len;
            for start in (0..n).step_by(len) {
                for k in 0..len / 2 {
                    let w = self.twiddles[k * step];
                    let a = data[start + k];
                    let b = data[start + k + len / 2].mul(w);
                    data[start + k] = a.add(b);
                    data[start + k + len / 2] = a.sub(b);
                }
            }
            len <<= 1;
        }
    }

    /// Transform `data` (length `n`) in place; `scratch` is reused.
    fn execute(&self, data: &mut [C64], scratch: &mut Vec<C64>) {
        debug_assert_eq!(data.len(), self.n);
        if self.n <= 1 {
            return;
        }
        match &self.bluestein {
            None => self.radix2(data),
            Some(b) => {
                scratch.clear();
                scratch.resize(b.m, C64::ZERO);
                for k in 0..self.n {
                    scratch[k] = data[k].mul(b.chirp[k]);
                }
                b.forward.radix2(scratch);
                for (value, factor) in scratch.iter_mut().zip(&b.b_fft) {
                    *value = value.mul(*factor);
                }
                b.backward.radix2(scratch);
                let scale = 1.0 / b.m as f64;
                for k in 0..self.n {
                    let value = scratch[k].mul(b.chirp[k]);
                    data[k] = C64::new(value.re * scale, value.im * scale);
                }
            }
        }
    }
}

#[cfg(test)]
fn fft(data: &mut [C64], sign: f64) {
    let plan = FftPlan::new(data.len(), sign);
    plan.execute(data, &mut Vec::new());
}

/// Unnormalised 2-D backward transform of a `[x + y * width]` grid, as
/// `fftw_plan_dft_2d(height, width, ..., FFTW_BACKWARD)`.
struct Fft2 {
    plan_x: FftPlan,
    plan_y: FftPlan,
}

impl Fft2 {
    fn new(width: usize, height: usize) -> Fft2 {
        Fft2 {
            plan_x: FftPlan::new(width, 1.0),
            plan_y: FftPlan::new(height, 1.0),
        }
    }

    #[inline(never)]
    fn backward(&self, grid: &mut [C64], ws_column: &mut [C64], scratch: &mut Vec<C64>) {
        let (width, height) = (self.plan_x.len(), self.plan_y.len());
        for row in grid.chunks_mut(width) {
            self.plan_x.execute(row, scratch);
        }
        let column = &mut ws_column[..height];
        for x in 0..width {
            for y in 0..height {
                column[y] = grid[x + y * width];
            }
            self.plan_y.execute(column, scratch);
            for y in 0..height {
                grid[x + y * width] = column[y];
            }
        }
    }
}

/// FFTW `REDFT01` (DCT-III) of length `n` of a right-half kernel, evaluated
/// for `k < count`: `Y_k = X_0 + 2 sum_{j>=1} X_j cos(pi j (k + 1/2) / n)`.
fn dct3_prefix(input: &[f64], n: usize, count: usize) -> Vec<f64> {
    (0..count)
        .map(|k| {
            let kk = k as f64 + 0.5;
            let mut sum = input[0];
            for (j, value) in input.iter().enumerate().skip(1) {
                sum += 2.0 * value * (PI * j as f64 * kk / n as f64).cos();
            }
            sum
        })
        .collect()
}

/// One visibility as the gridder adds it, after `AddDataSample`'s
/// conjugation of negative-w samples, its rounding to a cell (wrapped into
/// the grid) and its choice of sub-cell kernels. The weighted Stokes sample
/// and the PSF weight stay single precision: both are the `f32` products the
/// reader forms, so storing them rounds nothing.
#[derive(Clone, Copy, Debug, Default)]
struct Sample {
    x: i32,
    y: i32,
    x_kernel: u16,
    y_kernel: u16,
    re: f32,
    im: f32,
    weight: f32,
}

/// Per-layer working memory of one rayon task.
struct Workspace {
    dirty: Vec<C64>,
    psf: Vec<C64>,
    column: Vec<C64>,
    scratch: Vec<C64>,
}

/// The w-stacking gridder state for one inversion.
pub struct Gridder {
    settings: Settings,
    fft: Fft2,
    kernel_1d: Vec<f64>,
    kernels: Vec<f64>,
    min_w: f64,
    max_w: f64,
    sqrt_lm: Vec<f64>,
}

impl Gridder {
    pub fn new(settings: Settings, min_w: f64, max_w: f64) -> Gridder {
        let kernel_1d = kaiser_bessel_kernel(settings.kernel_size, settings.oversampling);
        let kernels = gridding_kernels(&kernel_1d, settings.kernel_size, settings.oversampling);
        // PrepareWLayers: avoid a zero w range.
        let max_w = if min_w == max_w { max_w + 1.0 } else { max_w };
        let mut gridder = Gridder {
            settings,
            fft: Fft2::new(settings.width, settings.height),
            kernel_1d,
            kernels,
            min_w,
            max_w,
            sqrt_lm: Vec::new(),
        };
        gridder.initialize_sqrt_lm();
        gridder
    }

    /// `WToLayer` for the real-image case; `None` where WSClean's `size_t`
    /// would wrap (rounded value below zero).
    pub fn w_to_layer(&self, w_in_lambda: f64) -> Option<usize> {
        let n = self.settings.n_w_layers;
        if n == 1 {
            return Some(0);
        }
        let value =
            ((w_in_lambda.abs() - self.min_w) * (n - 1) as f64 / (self.max_w - self.min_w)).round();
        if value < 0.0 {
            None
        } else {
            Some(value as usize)
        }
    }

    /// `IsInLayerRange` for a single pass over all layers.
    pub fn is_in_layer_range(&self, w_in_lambda: f64) -> bool {
        matches!(self.w_to_layer(w_in_lambda), Some(layer) if layer < self.settings.n_w_layers)
    }

    /// `LayerToW`.
    pub fn layer_to_w(&self, layer: usize) -> f64 {
        let n = self.settings.n_w_layers;
        if n == 1 {
            0.0
        } else {
            layer as f64 * (self.max_w - self.min_w) / (n - 1) as f64 + self.min_w
        }
    }

    /// `initializeSqrtLMLookupTable`.
    fn initialize_sqrt_lm(&mut self) {
        let (w, h) = (self.settings.width, self.settings.height);
        let mut table = Vec::with_capacity(w * h);
        for y in 0..h {
            let mut y_src = (h - y) + h / 2;
            if y_src >= h {
                y_src -= h;
            }
            let m = (y_src as f64 - (h / 2) as f64) * self.settings.pixel_size_y;
            for x in 0..w {
                let mut x_src = x + w / 2;
                if x_src >= w {
                    x_src -= w;
                }
                let l = ((w / 2) as f64 - x_src as f64) * self.settings.pixel_size_x;
                table.push(if l * l + m * m < 1.0 {
                    (1.0 - l * l - m * m).sqrt() - 1.0
                } else {
                    0.0
                });
            }
        }
        self.sqrt_lm = table;
    }

    /// The cell and sub-cell kernels `AddDataSample` chooses for one sample
    /// (`uvw` in wavelengths), or `None` where it drops the sample: outside
    /// every layer or outside the grid. `re`, `im` are the weighted Stokes
    /// sample and `weight` the PSF weight.
    fn place(
        &self,
        re: f32,
        im: f32,
        weight: f32,
        u: f64,
        v: f64,
        w: f64,
    ) -> Option<(usize, Sample)> {
        let layer = self.w_to_layer(w)?;
        if layer >= self.settings.n_w_layers {
            return None;
        }
        let (mut u, mut v, mut im) = (u, v, im);
        if w < 0.0 {
            u = -u;
            v = -v;
            im = -im;
        }
        let s = &self.settings;
        let (width, height) = (s.width as i64, s.height as i64);
        let ovs = s.oversampling as i64;
        let x_exact = u * s.pixel_size_x * s.width as f64;
        let y_exact = v * s.pixel_size_y * s.height as f64;
        let mut x = x_exact.round() as i64;
        let mut y = y_exact.round() as i64;
        let mut x_kernel = ((x_exact - x as f64) * s.oversampling as f64).round() as i64;
        let mut y_kernel = ((y_exact - y as f64) * s.oversampling as f64).round() as i64;
        x_kernel = (x_kernel + (ovs * 3) / 2) % ovs;
        y_kernel = (y_kernel + (ovs * 3) / 2) % ovs;
        if !(x > -width / 2 && y > -height / 2 && x <= width / 2 && y <= height / 2) {
            return None;
        }
        if x < 0 {
            x += width;
        }
        if y < 0 {
            y += height;
        }
        Some((
            layer,
            Sample {
                x: x as i32,
                y: y as i32,
                x_kernel: x_kernel as u16,
                y_kernel: y_kernel as u16,
                re,
                im,
                weight,
            },
        ))
    }

    /// `AddDataSample` of every sample of one layer, into the dirty grid
    /// (the weighted Stokes sample) and the PSF grid (the weight), in the
    /// samples' order.
    #[inline(never)]
    fn grid_layer(&self, samples: &[Sample], dirty: &mut [C64], psf: &mut [C64]) {
        let s = &self.settings;
        let (width, height) = (s.width as i64, s.height as i64);
        let ksize = s.kernel_size;
        let mid = (ksize / 2) as i64;
        for sample in samples {
            let (x, y) = (sample.x as i64, sample.y as i64);
            let xk = &self.kernels[sample.x_kernel as usize * ksize..][..ksize];
            let yk = &self.kernels[sample.y_kernel as usize * ksize..][..ksize];
            let (re, im) = (sample.re as f64, sample.im as f64);
            let weight = sample.weight as f64;
            if x < mid || x + mid + 1 >= width || y < mid || y + mid + 1 >= height {
                for (j, &ky) in yk.iter().enumerate() {
                    let cy = ((y + j as i64 + height - mid) % height) * width;
                    for (i, &kx) in xk.iter().enumerate() {
                        let cx = (x + i as i64 + width - mid) % width;
                        let k = ky * kx;
                        let index = (cx + cy) as usize;
                        let cell = &mut dirty[index];
                        cell.re += re * k;
                        cell.im += im * k;
                        // The PSF sample is real: its imaginary part adds
                        // signed zeros to a +0 cell, which stays +0.
                        psf[index].re += weight * k;
                    }
                }
            } else {
                let x0 = x - mid;
                for (j, &ky) in yk.iter().enumerate() {
                    let base = (x0 + (y - mid + j as i64) * width) as usize;
                    let row_d = &mut dirty[base..base + ksize];
                    let row_p = &mut psf[base..base + ksize];
                    for ((cell, cell_p), &kx) in row_d.iter_mut().zip(row_p.iter_mut()).zip(xk) {
                        let k = ky * kx;
                        cell.re += re * k;
                        cell.im += im * k;
                        cell_p.re += weight * k;
                    }
                }
            }
        }
    }

    /// `projectOnImageAndCorrect<false>` of one transformed layer, for the
    /// dirty and the PSF grid with the same phasor: each output pixel is
    /// written once, so the result is this layer's term of the sum.
    #[inline(never)]
    fn project(
        &self,
        dirty_grid: &[C64],
        psf_grid: &[C64],
        w: f64,
        dirty: &mut [f64],
        psf: &mut [f64],
    ) {
        let (width, height) = (self.settings.width, self.settings.height);
        let two_pi_w = -2.0 * PI * w;
        let mut index = 0;
        for y in 0..height {
            let mut y_src = (height - y) + height / 2;
            if y_src >= height {
                y_src -= height;
            }
            for x in 0..width {
                let mut x_src = x + width / 2;
                if x_src >= width {
                    x_src -= width;
                }
                let rad = two_pi_w * self.sqrt_lm[index];
                let (sn, cs) = rad.sin_cos();
                let target = x_src + y_src * width;
                let value = dirty_grid[index];
                dirty[target] = value.re * cs - value.im * sn;
                let value = psf_grid[index];
                psf[target] = value.re * cs - value.im * sn;
                index += 1;
            }
        }
    }

    /// Grid, transform and project one layer; returns its dirty and PSF terms.
    fn layer_terms(
        &self,
        samples: &[Sample],
        layer: usize,
        ws: &mut Workspace,
    ) -> (Vec<f64>, Vec<f64>) {
        ws.dirty.fill(C64::ZERO);
        ws.psf.fill(C64::ZERO);
        self.grid_layer(samples, &mut ws.dirty, &mut ws.psf);
        self.fft
            .backward(&mut ws.dirty, &mut ws.column, &mut ws.scratch);
        self.fft
            .backward(&mut ws.psf, &mut ws.column, &mut ws.scratch);
        let pixels = self.settings.width * self.settings.height;
        let mut dirty = vec![0.0; pixels];
        let mut psf = vec![0.0; pixels];
        self.project(
            &ws.dirty,
            &ws.psf,
            self.layer_to_w(layer),
            &mut dirty,
            &mut psf,
        );
        (dirty, psf)
    }

    fn workspace(&self) -> Workspace {
        let (width, height) = (self.settings.width, self.settings.height);
        Workspace {
            dirty: vec![C64::ZERO; width * height],
            psf: vec![C64::ZERO; width * height],
            column: vec![C64::ZERO; width.max(height)],
            scratch: Vec::new(),
        }
    }

    /// Grid, transform and project every layer of the bucketed samples
    /// (`offsets[layer]..offsets[layer + 1]`), layers in parallel, terms
    /// added in layer order; then `FinalizeImage(1 / image_weight)` of both.
    fn invert(
        &self,
        samples: &[Sample],
        offsets: &[usize],
        image_weight: f64,
    ) -> (Vec<f64>, Vec<f64>) {
        let pixels = self.settings.width * self.settings.height;
        let mut dirty = vec![0.0; pixels];
        let mut psf = vec![0.0; pixels];
        let layers: Vec<usize> = (0..self.settings.n_w_layers)
            .filter(|&layer| offsets[layer + 1] > offsets[layer])
            .collect();
        for batch in layers.chunks(LAYER_BATCH) {
            let terms: Vec<(Vec<f64>, Vec<f64>)> = batch
                .par_iter()
                .map_init(
                    || self.workspace(),
                    |ws, &layer| {
                        self.layer_terms(&samples[offsets[layer]..offsets[layer + 1]], layer, ws)
                    },
                )
                .collect();
            for (term_d, term_p) in &terms {
                for (value, term) in dirty.iter_mut().zip(term_d) {
                    *value += term;
                }
                for (value, term) in psf.iter_mut().zip(term_p) {
                    *value += term;
                }
            }
        }
        let factor = 1.0 / image_weight;
        for value in dirty.iter_mut().chain(psf.iter_mut()) {
            *value *= factor;
        }
        self.correct_for_kernel(&mut dirty, &mut psf);
        (dirty, psf)
    }

    /// `correctImageForKernel<false>`: divide by the kernel's image response.
    fn correct_for_kernel(&self, dirty: &mut [f64], psf: &mut [f64]) {
        let s = &self.settings;
        let half = s.kernel_size * s.oversampling / 2;
        let right = &self.kernel_1d[half..=half + s.kernel_size * s.oversampling / 2];
        let out_x = dct3_prefix(right, s.width * s.oversampling / 2, s.width / 2 + 1);
        let out_y = if s.width == s.height {
            out_x.clone()
        } else {
            dct3_prefix(right, s.height * s.oversampling / 2, s.height / 2 + 1)
        };
        let norm = 1.0 / (s.oversampling as f64 * s.oversampling as f64);
        let mut index = 0;
        for y in 0..s.height {
            let y_val = if y >= s.height / 2 {
                out_y[y - s.height / 2]
            } else {
                out_y[s.height / 2 - y]
            };
            for x in 0..s.width {
                let x_val = if x >= s.width / 2 {
                    out_x[x - s.width / 2]
                } else {
                    out_x[s.width / 2 - x]
                };
                let divisor = x_val * y_val * norm;
                dirty[index] /= divisor;
                psf[index] /= divisor;
                index += 1;
            }
        }
    }
}

/// `CalculateMsLimits` over rows and channels: the w range of samples with
/// nonzero visibility and imaging weight whose grid cell lies inside the
/// image. Returns `(min_w, max_w)` in wavelengths; `(0, 0)` with no sample.
pub fn w_limits(settings: &Settings, inputs: &Inputs) -> (f64, f64) {
    let nchan = inputs.frequencies.len();
    let nrow = inputs.uvw.len() / 3;
    let half_width = 0.5 * settings.width as f64;
    let half_height = 0.5 * settings.height as f64;
    let mut min_w = 1e100_f64;
    let mut max_w = 0.0_f64;
    for row in 0..nrow {
        let (um, _vm, wm) = (
            inputs.uvw[row * 3],
            inputs.uvw[row * 3 + 1],
            inputs.uvw[row * 3 + 2],
        );
        for ch in 0..nchan {
            let index = row * nchan + ch;
            if inputs.weights[index] == 0.0 {
                continue;
            }
            let wavelength = C_LIGHT / inputs.frequencies[ch];
            let u = um / wavelength;
            let w = wm / wavelength;
            // WSClean 3.6 computes both bounds from u (ported as written).
            let x = u * settings.pixel_size_x * settings.width as f64;
            let y = u * settings.pixel_size_y * settings.height as f64;
            if inputs.imaging_weights[index] != 0.0
                && x.floor() > -half_width
                && x.ceil() < half_width
                && y.floor() > -half_height
                && y.ceil() < half_height
            {
                max_w = max_w.max(w.abs());
                min_w = min_w.min(w.abs());
            }
        }
    }
    if min_w == 1e100 {
        (0.0, 0.0)
    } else {
        (min_w, max_w)
    }
}

/// Invert `inputs` to a dirty image and a PSF, normalised as WSClean writes
/// them (`FinalizeImage(1 / ImageWeight)`, then both scaled so that the PSF
/// centre is one).
pub fn invert(settings: &Settings, inputs: &Inputs) -> Result<Products, String> {
    let nchan = inputs.frequencies.len();
    let nrow = inputs.uvw.len() / 3;
    if settings.width == 0
        || settings.height == 0
        || settings.kernel_size == 0
        || settings.oversampling == 0
        || settings.n_w_layers == 0
        || settings.kernel_size.is_multiple_of(2)
        || settings.padding.is_nan()
        || settings.padding < 1.0
        || settings.oversampling > usize::from(u16::MAX)
    {
        return Err("invalid image or kernel settings".into());
    }
    if inputs.uvw.len() != nrow * 3
        || inputs.data.len() != nrow * nchan * 2
        || inputs.weights.len() != nrow * nchan
        || inputs.imaging_weights.len() != nrow * nchan
    {
        return Err("input lengths disagree".into());
    }
    let (padded_width, padded_height) = settings.padded_size();
    if padded_width > i32::MAX as usize || padded_height > i32::MAX as usize {
        return Err("image too large".into());
    }
    let padded = Settings {
        width: padded_width,
        height: padded_height,
        ..*settings
    };
    let (min_w, max_w) = w_limits(&padded, inputs);
    let gridder = Gridder::new(padded, min_w, max_w);
    let mut stats = Stats {
        min_w,
        max_w,
        ..Stats::default()
    };
    // One pass in row-channel order: the counters (in WSClean's summation
    // order) and the gridded samples with their layers. Samples whose
    // weighted value and weight are both zero add only signed zeros to the
    // grids and are not kept.
    let mut placed = Vec::new();
    let mut layers = Vec::new();
    let mut counts = vec![0usize; settings.n_w_layers];
    for row in 0..nrow {
        let (um, vm, wm) = (
            inputs.uvw[row * 3],
            inputs.uvw[row * 3 + 1],
            inputs.uvw[row * 3 + 2],
        );
        for ch in 0..nchan {
            let index = row * nchan + ch;
            let wavelength = C_LIGHT / inputs.frequencies[ch];
            let (u, v, w) = (um / wavelength, vm / wavelength, wm / wavelength);
            // Samples outside every layer get zero weight before the sums.
            let weight = if gridder.is_in_layer_range(w) {
                inputs.weights[index]
            } else {
                0.0
            };
            let cum_weight: f32 = weight * inputs.imaging_weights[index];
            let has_weight = cum_weight != 0.0;
            if has_weight {
                stats.visibility_weight_sum += weight as f64;
                stats.gridded_count += 1;
            }
            stats.max_gridded_weight = stats.max_gridded_weight.max(cum_weight as f64);
            stats.image_weight += cum_weight as f64;
            let re = inputs.data[index * 2] * cum_weight;
            let im = inputs.data[index * 2 + 1] * cum_weight;
            if cum_weight == 0.0 && re == 0.0 && im == 0.0 {
                continue;
            }
            if let Some((layer, sample)) = gridder.place(re, im, cum_weight, u, v, w) {
                placed.push(sample);
                layers.push(layer as u32);
                counts[layer] += 1;
            }
        }
    }
    if stats.image_weight == 0.0 {
        return Err("no visibility carries weight".into());
    }
    // Stable counting sort by layer: within a layer the samples keep their
    // row-channel order, the order in which WSClean grids them.
    let mut offsets = vec![0usize; settings.n_w_layers + 1];
    for (layer, count) in counts.iter().enumerate() {
        offsets[layer + 1] = offsets[layer] + count;
    }
    let mut cursor = offsets.clone();
    let mut samples = vec![Sample::default(); placed.len()];
    for (sample, &layer) in placed.iter().zip(&layers) {
        samples[cursor[layer as usize]] = *sample;
        cursor[layer as usize] += 1;
    }
    drop(placed);
    drop(layers);
    let (mut dirty, mut psf) = gridder.invert(&samples, &offsets, stats.image_weight);
    drop(samples);
    if (padded_width, padded_height) != (settings.width, settings.height) {
        dirty = trim(
            &dirty,
            padded_width,
            padded_height,
            settings.width,
            settings.height,
        );
        psf = trim(
            &psf,
            padded_width,
            padded_height,
            settings.width,
            settings.height,
        );
    }
    let centre = settings.width / 2 + (settings.height / 2) * settings.width;
    stats.psf_normalization = if psf[centre] != 0.0 {
        1.0 / psf[centre]
    } else {
        0.0
    };
    for value in dirty.iter_mut() {
        *value *= stats.psf_normalization;
    }
    for value in psf.iter_mut() {
        *value *= stats.psf_normalization;
    }
    Ok(Products { dirty, psf, stats })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn naive_dft(data: &[C64], sign: f64) -> Vec<C64> {
        let n = data.len();
        (0..n)
            .map(|k| {
                let mut sum = C64::ZERO;
                for (j, value) in data.iter().enumerate() {
                    sum =
                        sum.add(value.mul(C64::expi(sign * 2.0 * PI * (j * k) as f64 / n as f64)));
                }
                sum
            })
            .collect()
    }

    #[test]
    fn fft_matches_naive_dft_for_both_lengths() {
        for n in [8usize, 12, 1, 7, 616, 262, 45] {
            let data: Vec<C64> = (0..n)
                .map(|i| C64::new((i as f64).sin(), (i as f64 * 0.3).cos()))
                .collect();
            for sign in [1.0, -1.0] {
                let mut fast = data.clone();
                fft(&mut fast, sign);
                let slow = naive_dft(&data, sign);
                for (a, b) in fast.iter().zip(&slow) {
                    assert!(
                        (a.re - b.re).abs() < 1e-10 && (a.im - b.im).abs() < 1e-10,
                        "n={n}"
                    );
                }
            }
        }
    }

    #[test]
    fn padded_size_follows_wsclean() {
        let settings = Settings {
            width: 512,
            height: 100,
            pixel_size_x: 1.0,
            pixel_size_y: 1.0,
            kernel_size: 7,
            oversampling: 1023,
            n_w_layers: 1,
            padding: 1.2,
        };
        assert_eq!(settings.padded_size(), (616, 120));
        assert_eq!(
            trim(&[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0], 3, 3, 1, 1),
            vec![5.0]
        );
    }

    #[test]
    fn kernel_is_symmetric_and_peaks_at_one() {
        let kernel = kaiser_bessel_kernel(7, 1023);
        let mid = kernel.len() / 2;
        assert!((kernel[mid] - 1.0).abs() < 1e-12);
        for i in 0..mid {
            assert_eq!(kernel[i], kernel[kernel.len() - 1 - i]);
        }
    }

    #[test]
    fn dct3_prefix_matches_definition() {
        let input = [1.0, 0.5, 0.25];
        let out = dct3_prefix(&input, 8, 3);
        for (k, value) in out.iter().enumerate() {
            let kk = k as f64 + 0.5;
            let expected = 1.0
                + 2.0 * 0.5 * (PI * 1.0 * kk / 8.0).cos()
                + 2.0 * 0.25 * (PI * 2.0 * kk / 8.0).cos();
            assert!((value - expected).abs() < 1e-12);
        }
    }

    /// A point source at (l, m) = (5, -3) pixels, positive MS phase
    /// convention, on a small array with w terms.
    fn point_source(settings: &Settings) -> (Vec<f64>, Vec<f64>, Vec<f32>, Vec<f32>) {
        let l = 5.0 * settings.pixel_size_x;
        let m = -3.0 * settings.pixel_size_y;
        let n = (1.0 - l * l - m * m).sqrt();
        let frequencies = vec![1.0e9, 1.2e9];
        let mut uvw = Vec::new();
        let mut data = Vec::new();
        let mut weights = Vec::new();
        for i in 0..60 {
            let angle = i as f64 * 0.37;
            let r = 20.0 + (i % 7) as f64 * 15.0;
            let (u, v, w) = (r * angle.cos(), r * angle.sin(), 3.0 * (angle * 1.7).sin());
            uvw.extend_from_slice(&[u, v, w]);
            for &freq in &frequencies {
                let lambda = C_LIGHT / freq;
                let phase = 2.0 * PI * (u * l + v * m + w * (n - 1.0)) / lambda;
                data.push(phase.cos() as f32);
                data.push(phase.sin() as f32);
                // One flagged sample per row exercises the skipped zeros.
                weights.push(if i % 5 == 0 && freq > 1.1e9 { 0.0 } else { 1.0 });
            }
        }
        (uvw, frequencies, data, weights)
    }

    fn small_settings(n_w_layers: usize) -> Settings {
        Settings {
            width: 32,
            height: 32,
            pixel_size_x: 1e-3,
            pixel_size_y: 1e-3,
            kernel_size: 7,
            oversampling: 1023,
            n_w_layers,
            padding: 1.2,
        }
    }

    #[test]
    fn point_source_lands_at_wsclean_pixel() {
        // The peak must be at x = W/2 - 5, y = H/2 - 3.
        let settings = small_settings(4);
        let (uvw, frequencies, data, weights) = point_source(&settings);
        let imaging = vec![1.0f32; weights.len()];
        let inputs = Inputs {
            uvw: &uvw,
            frequencies: &frequencies,
            data: &data,
            weights: &weights,
            imaging_weights: &imaging,
        };
        let products = invert(&settings, &inputs).unwrap();
        let (mut best, mut best_value) = (0, f64::MIN);
        for (i, &value) in products.dirty.iter().enumerate() {
            if value > best_value {
                best = i;
                best_value = value;
            }
        }
        assert_eq!((best % 32, best / 32), (16 - 5, 16 - 3));
        // `x * (1 / x)` is one to within an ulp, as in WSClean.
        let centre = 16 + 16 * 32;
        assert!((products.psf[centre] - 1.0).abs() <= 2.0 * f64::EPSILON);
        assert!((best_value - 1.0).abs() < 0.05, "peak {best_value}");
        assert_eq!(products.stats.gridded_count, 108);
    }

    #[test]
    fn result_does_not_depend_on_the_thread_count() {
        let settings = small_settings(40);
        let (uvw, frequencies, data, weights) = point_source(&settings);
        let imaging: Vec<f32> = (0..weights.len()).map(|i| 0.5 + (i % 3) as f32).collect();
        let inputs = Inputs {
            uvw: &uvw,
            frequencies: &frequencies,
            data: &data,
            weights: &weights,
            imaging_weights: &imaging,
        };
        let run = |threads: usize| {
            rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()
                .unwrap()
                .install(|| invert(&settings, &inputs).unwrap())
        };
        let one = run(1);
        for threads in [2, 3, 8] {
            let many = run(threads);
            assert_eq!(one.stats, many.stats);
            for (a, b) in one.dirty.iter().zip(&many.dirty) {
                assert_eq!(a.to_bits(), b.to_bits());
            }
            for (a, b) in one.psf.iter().zip(&many.psf) {
                assert_eq!(a.to_bits(), b.to_bits());
            }
        }
    }
}
