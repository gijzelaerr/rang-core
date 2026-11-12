// SPDX-License-Identifier: GPL-3.0-or-later
//! Multiscale CLEAN for gemclean: WSClean 3.7's `-multiscale`, radler's
//! `MultiScaleAlgorithm` with its sub-minor loop (`research/g5-multiscale.md`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! What follows radler (`cpp/algorithms/multiscale_algorithm.cc`,
//! `subminor_loop.cc`, `multiscale/multiscale_transforms.h`, WSClean `v3.7`,
//! radler `76fe447`):
//!
//! - **Scales.** Without a list: 0, then `4b, 8b, …` below half the image side,
//!   `b` the theoretic beam (`1 / max |uvw|/λ`) in pixels, at most
//!   `max_scales` of them (`InitializeScales`). A list is sorted, duplicates kept.
//! - **Shapes.** The tapered quadratic (a Hann-windowed `1 − r²/s²` on
//!   `2⌈s/2⌉ + 1` pixels) or a Gaussian of `σ = 3s/16` on a 12σ box capped at the
//!   image side, both normalised to unit sum (`MakeShapeFunction`).
//! - **Bias and gain.** `bias = scale_bias^(−log2(s / 2b))` (1 for scale 0 or a
//!   single scale); the component gain is `gain / psf_peak(s)`, the peak of the
//!   integrated PSF convolved with the shape (`ConvolvePsfs`).
//! - **The minor loop** (`ExecuteMajorIteration`): every scale active at the
//!   start of a major cycle; the scale with the largest `|peak · bias|` of the
//!   scale-convolved integrated residual (border `⌈s/2⌉`) is chosen; a sub-minor
//!   loop at that scale runs on the pixels whose convolved integrated value is at
//!   least `max(peak·bias·(1 − sub_minor_gain), level) / bias`, with the
//!   twice-convolved `n × n` PSF and the component values `gain_s ·` each
//!   channel's convolved residual at the pick (spectrally fitted when asked);
//!   then the scale-convolved components join the model, scales are activated
//!   or deactivated (`ActivateScales`) and the peaks found again. The countdown
//!   of `max(8, 3·scales/2)` sub-minor loops near the level, and radler's
//!   divergence limit (4), are kept.
//!
//! What is gemclean's, not radler's:
//!
//! - **The residual after each sub-minor loop is exact for the image-domain
//!   beam**: `r̃ = r_major − B (m − m_major)` with each channel's `2n` beam (one
//!   FFT pair per channel), where radler subtracts the components convolved with
//!   the `n × n` PSF on a padded grid (`CorrectResidualDirty`). The predicted
//!   misfit change of a cycle is `−½ Σ a_k ⟨Δ_k, r_k + r̃_k⟩`, exact for that beam.
//! - **Convolutions with a shape are linear** (zero outside the image), where
//!   radler's `MultiScaleTransforms::Transform` is circular on the `n × n` image.
//!   The model is the shape-convolved components cut at the image edge, and the
//!   residual is updated with exactly that model.
//! - **The level at which a cycle hands back** is gemclean's [`CycleStop`] rule
//!   applied to the biased peak: `PeakFraction(g)` is WSClean's `-mgain`;
//!   `MeasuredStale` ends a later cycle at `max(ρ δ Σ|c|, floor · first peak)`,
//!   with `δ` measured by the previous major cycle as in [`super::run`]. The
//!   level is read at the start of every sub-minor loop.
//! - A major cycle starts only while the largest biased peak over all scales
//!   is at least the threshold; a cycle that cleans nothing ends the run.
//! - Arithmetic is `f64` throughout (radler's is `f32`).

use super::joined::Joined;
use super::spectral::PolynomialFit;
use super::{
    Beam, Convolver, Cycle, CycleStop, MinorStop, Outcome, Resyncs, Settings, StopReason, Timings,
    Work, effective_threshold, kernels, memory,
};
use crate::clean::CleanStep;
use crate::clean_certified::Measurement;
use rayon::prelude::*;
use std::time::Instant;

/// The shape function of the scales (`-multiscale-shape`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Shape {
    /// radler's default: `tapered-quadratic`.
    TaperedQuadratic,
    Gaussian,
}

impl Shape {
    pub fn name(&self) -> &'static str {
        match self {
            Shape::TaperedQuadratic => "tapered-quadratic",
            Shape::Gaussian => "gaussian",
        }
    }
}

/// WSClean's multiscale options, with its defaults.
#[derive(Clone, Debug, PartialEq)]
pub struct MultiscaleSettings {
    /// `-multiscale-scales` in pixels; empty: the automatic scales.
    pub scales: Vec<f64>,
    /// `-multiscale-max-scales` (0: as many as fit).
    pub max_scales: usize,
    /// `-multiscale-scale-bias` (0.6).
    pub scale_bias: f64,
    /// `-multiscale-shape`.
    pub shape: Shape,
    /// `-multiscale-gain`: how far a sub-minor loop takes its scale's peak
    /// down, as a fraction (0.2). Not the component gain.
    pub sub_minor_gain: f64,
    /// radler's `divergence_limit` (4; 0: off).
    pub divergence_limit: f64,
}

impl Default for MultiscaleSettings {
    fn default() -> MultiscaleSettings {
        MultiscaleSettings {
            scales: Vec::new(),
            max_scales: 0,
            scale_bias: 0.6,
            shape: Shape::TaperedQuadratic,
            sub_minor_gain: 0.2,
            divergence_limit: 4.0,
        }
    }
}

/// radler's shape function for `scale` pixels: the side `k` (odd) and the
/// `k × k` values, normalised to unit sum (`MakeShapeFunction`); `max_side`
/// caps a Gaussian's box (the image side).
///
/// The arithmetic is radler's `float` (`f32`) where radler's is, the sum
/// accumulated in order, so that the kernel has radler's values (post hoc,
/// research/g5-multiscale.md: an `f64` kernel moved the PSF peak of the
/// 922-pixel scale by 3e-4, the size of radler's `f32` sum error).
pub fn shape_function(scale: f64, max_side: usize, shape: Shape) -> (usize, Vec<f64>) {
    // radler passes the scale as `float`.
    let scale = f64::from(scale as f32);
    match shape {
        Shape::TaperedQuadratic => {
            let k = ((scale * 0.5).ceil() * 2.0) as usize + 1;
            if scale == 0.0 {
                let mut v = vec![0.0; k * k];
                v[0] = 1.0;
                return (k, v);
            }
            let mut v = vec![0.0_f32; k * k];
            let mut sum = 0.0_f32;
            let hann = |r: f32| -> f32 {
                if f64::from(r) * 2.0 <= (k + 1) as f64 {
                    (0.5 * (1.0
                        + (2.0 * std::f64::consts::PI * f64::from(r) / (k + 1) as f64).cos()))
                        as f32
                } else {
                    0.0
                }
            };
            let quadratic = |q: f32| -> f32 {
                if q < 1.0 {
                    (1.0 - f64::from(q) * f64::from(q)) as f32
                } else {
                    0.0
                }
            };
            for y in 0..k {
                let dy = (y as f64 - 0.5 * (k as f64 - 1.0)) as f32;
                let dydy = dy * dy;
                for x in 0..k {
                    let dx = (x as f64 - 0.5 * (k as f64 - 1.0)) as f32;
                    let r = (dx * dx + dydy).sqrt();
                    let value = hann(r) * quadratic((f64::from(r) / scale) as f32);
                    v[y * k + x] = value;
                    sum += value;
                }
            }
            let norm = (1.0 / f64::from(sum)) as f32;
            (k, v.iter().map(|&x| f64::from(x * norm)).collect())
        }
        Shape::Gaussian => {
            let mut sigma = (scale * (3.0 / 16.0)) as f32;
            let mut k = ((f64::from(sigma) * 12.0 / 2.0).ceil() as usize) * 2 + 1;
            if k > max_side {
                k = max_side;
                if k.is_multiple_of(2) && k > 0 {
                    k -= 1;
                }
            }
            if k < 1 {
                k = 1;
            }
            if sigma == 0.0 {
                sigma = 1.0;
                k = 1;
            }
            let mu = (k / 2) as f32;
            let two_s2 = (2.0 * f64::from(sigma) * f64::from(sigma)) as f32;
            let g: Vec<f32> = (0..k)
                .map(|i| {
                    let d = i as f32 - mu;
                    (-d * d / two_s2).exp()
                })
                .collect();
            let mut v = vec![0.0_f32; k * k];
            let mut sum = 0.0_f32;
            for y in 0..k {
                for x in 0..k {
                    v[y * k + x] = g[x] * g[y];
                    sum += v[y * k + x];
                }
            }
            let norm = (1.0 / f64::from(sum)) as f32;
            (k, v.iter().map(|&x| f64::from(x * norm)).collect())
        }
    }
}

/// The scales in pixels, as radler's `InitializeScales` chooses them for a
/// theoretic beam of `beam` pixels on an `n × n` image.
pub fn scale_list(beam: f64, n: usize, settings: &MultiscaleSettings) -> Vec<f64> {
    if !settings.scales.is_empty() {
        let mut s = settings.scales.clone();
        s.sort_by(|a, b| a.total_cmp(b));
        return s;
    }
    let mut out = Vec::new();
    let mut scale = beam * 2.0;
    let mut index = 0usize;
    loop {
        out.push(if index == 0 { 0.0 } else { scale });
        scale *= 2.0;
        index += 1;
        if !(scale < n as f64 * 0.5 && (settings.max_scales == 0 || index < settings.max_scales)) {
            break;
        }
    }
    out
}

/// radler's scale bias factor: `scale_bias^(−log2(s / 2b))`.
pub fn bias_factor(scale: f64, beam: f64, count: usize, scale_bias: f64) -> f64 {
    let exponent = if scale == 0.0 || count < 2 {
        0.0
    } else {
        (scale / (beam * 2.0)).log2()
    };
    scale_bias.powf(-exponent)
}

/// WSClean's theoretic beam in radians, `1 / max |uvw|/λ` (`MsGridder::
/// CalculateOverallMetaData`, `CalculateMsLimits`): over the visibilities with
/// nonzero imaging weight whose `u` falls inside the `n`-pixel grid (WSClean
/// tests `u` on both axes, and so does this). `uvw` in metres, row-major
/// `[u, v, w]`; `weights` row-major by channel. `None` without such a visibility.
pub fn theoretic_beam(
    uvw: &[f64],
    freq: &[f64],
    weights: &[f64],
    n: usize,
    pixel: f64,
) -> Option<f64> {
    const C: f64 = 299_792_458.0;
    let nchan = freq.len();
    let half = 0.5 * n as f64;
    let rows = uvw.len() / 3;
    let best = (0..rows)
        .into_par_iter()
        .map(|row| {
            let (u, v, w) = (uvw[3 * row], uvw[3 * row + 1], uvw[3 * row + 2]);
            let length = (u * u + v * v + w * w).sqrt();
            let mut best = 0.0_f64;
            for (c, &f) in freq.iter().enumerate() {
                if weights[row * nchan + c] == 0.0 {
                    continue;
                }
                let wavelength = C / f;
                let x = u / wavelength * pixel * n as f64;
                if x.floor() > -half && x.ceil() < half {
                    best = best.max(length / wavelength);
                }
            }
            best
        })
        .reduce(|| 0.0, f64::max);
    (best > 0.0).then(|| 1.0 / best)
}

/// One scale: its shape and radler's per-scale numbers.
struct Scale {
    scale: f64,
    kernel_side: usize,
    kernel: Vec<f64>,
    kernel_peak: f64,
    bias: f64,
    psf_peak: f64,
    gain: f64,
    active: bool,
    /// Signed peak of the convolved integrated residual, and its pixel.
    value: f64,
    pixel: usize,
    components: usize,
    flux: f64,
}

/// Bytes the shapes' convolvers may hold together, and as many again the
/// twice-convolved PSFs. What does not fit is rebuilt when needed; a rebuilt
/// convolver or PSF has the same bits, so the budget changes no image.
pub const CACHE_BYTES: usize = 2_000_000_000;

/// A least-recently-used cache of per-scale values.
struct Cache<T> {
    items: Vec<Option<T>>,
    order: Vec<usize>,
    capacity: usize,
    built: u64,
}

impl<T> Cache<T> {
    fn new(len: usize, capacity: usize) -> Cache<T> {
        Cache {
            items: (0..len).map(|_| None).collect(),
            order: Vec::new(),
            capacity: capacity.max(1),
            built: 0,
        }
    }

    /// Make room for item `i` and mark it used; true when it must be made.
    fn reserve(&mut self, i: usize) -> bool {
        self.order.retain(|&j| j != i);
        let missing = self.items[i].is_none();
        if missing {
            while self.order.len() >= self.capacity {
                let old = self.order.remove(0);
                self.items[old] = None;
            }
        }
        self.order.push(i);
        missing
    }
}

/// What a scale did, for the report.
#[derive(Clone, Debug)]
pub struct ScaleReport {
    pub scale: f64,
    pub kernel_side: usize,
    pub kernel_peak: f64,
    pub bias: f64,
    pub psf_peak: f64,
    pub gain: f64,
    pub components: usize,
    pub flux: f64,
}

/// Why the multiscale run ended, beyond [`StopReason`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MultiscaleEnd {
    /// As [`Outcome::stop`] says.
    Normal,
    /// A minor cycle cleaned nothing above the threshold (no pixel selected).
    Stalled,
    /// radler's divergence limit was passed.
    Diverged,
}

/// The outcome of [`run_multiscale`].
#[derive(Clone, Debug)]
pub struct Multiscale {
    /// Per channel and integrated, as [`super::joined::run_joined`] gives them;
    /// one channel of weight one is the plain run.
    pub joined: Joined,
    pub beam_pixels: f64,
    pub scales: Vec<ScaleReport>,
    pub end: MultiscaleEnd,
    /// Sub-minor loops run.
    pub sub_minor_loops: usize,
    /// Convolutions with a shape, and the beam convolutions after the
    /// sub-minor loops.
    pub convolutions: u64,
    /// Shape convolvers and twice-convolved PSF sets built (the cache).
    pub convolvers_built: u64,
    pub twice_built: u64,
}

fn embed_kernel(n: usize, side: usize, values: &[f64]) -> Vec<f64> {
    let m = 2 * n;
    let h = (side / 2) as isize;
    let mut k = vec![0.0; m * m];
    for y in 0..side {
        for x in 0..side {
            let (dy, dx) = (y as isize - h, x as isize - h);
            k[(n as isize + dy) as usize * m + (n as isize + dx) as usize] = values[y * side + x];
        }
    }
    k
}

/// The signed value of the largest `|x|` inside the border, and its pixel;
/// the first in raster order on ties.
fn peak(x: &[f64], n: usize, border: usize) -> Option<(f64, usize)> {
    if 2 * border >= n {
        return None;
    }
    let (lo, hi) = (border, n - border);
    let (_, p) = (lo..hi)
        .into_par_iter()
        .map(|row| {
            let mut best = (-1.0_f64, usize::MAX);
            for col in lo..hi {
                let v = x[row * n + col].abs();
                if v > best.0 {
                    best = (v, row * n + col);
                }
            }
            best
        })
        .reduce(
            || (-1.0, usize::MAX),
            |a, b| {
                if b.0 > a.0 || (b.0 == a.0 && b.1 < a.1) {
                    b
                } else {
                    a
                }
            },
        );
    (p != usize::MAX).then(|| (x[p], p))
}

/// [`peak`] inside `mask` (radler's `FindWithMask`); `None` when the mask
/// has no pixel inside the border.
fn peak_masked(x: &[f64], n: usize, border: usize, mask: &[bool]) -> Option<(f64, usize)> {
    if 2 * border >= n {
        return None;
    }
    let (lo, hi) = (border, n - border);
    let mut best = (-1.0_f64, usize::MAX);
    for row in lo..hi {
        for col in lo..hi {
            let p = row * n + col;
            if mask[p] && x[p].abs() > best.0 {
                best = (x[p].abs(), p);
            }
        }
    }
    (best.1 != usize::MAX).then(|| (x[best.1], best.1))
}

/// `Σ_d k(d) psf(c − d)` at the centre `c = (n/2, n/2)`, the PSF periodic on
/// the `n × n` image (radler's circular convolution, at one pixel).
fn circular_peak(psf: &[f64], n: usize, kernel: &[f64], side: usize) -> f64 {
    let h = (side / 2) as isize;
    let c = (n / 2) as isize;
    let m = n as isize;
    let rows: Vec<f64> = (0..side)
        .into_par_iter()
        .map(|ky| {
            let row = (c - (ky as isize - h)).rem_euclid(m) as usize;
            let mut s = 0.0;
            for kx in 0..side {
                let col = (c - (kx as isize - h)).rem_euclid(m) as usize;
                s += kernel[ky * side + kx] * psf[row * n + col];
            }
            s
        })
        .collect();
    rows.iter().sum()
}

fn integrate(images: &[Vec<f64>], a: &[f64]) -> Vec<f64> {
    let mut out = vec![0.0; images[0].len()];
    out.par_iter_mut().enumerate().for_each(|(i, o)| {
        let mut s = 0.0;
        for (img, &ak) in images.iter().zip(a) {
            s += ak * img[i];
        }
        *o = s;
    });
    out
}

struct Run<'a> {
    n: usize,
    beams: Vec<&'a Beam>,
    psfs: Vec<&'a [f64]>,
    scales: Vec<Scale>,
    convolvers: Cache<Convolver>,
    twice: Cache<Vec<Vec<f64>>>,
    convolutions: u64,
    /// The FITS mask (task G4); ignored while the scale masks are used.
    clean: Option<Vec<bool>>,
    /// radler's per-scale automatic masks: the component centres cleaned at
    /// each scale while tracking (empty without `-auto-mask`).
    masks: Vec<Vec<bool>>,
    track: bool,
    use_masks: bool,
}

impl Run<'_> {
    /// The shape of scale `s` convolved with `x` (linear; scale 0: `x`).
    fn convolve(&mut self, s: usize, x: &[f64]) -> Result<Vec<f64>, String> {
        if self.scales[s].scale == 0.0 {
            return Ok(x.to_vec());
        }
        if self.convolvers.reserve(s) {
            let sc = &self.scales[s];
            let kernel = embed_kernel(self.n, sc.kernel_side, &sc.kernel);
            self.convolvers.items[s] = Some(Convolver::new(self.n, &kernel)?);
            self.convolvers.built += 1;
        }
        self.convolutions += 1;
        Ok(self.convolvers.items[s]
            .as_ref()
            .expect("made above")
            .apply(x))
    }

    /// The mask scale `s` may clean in (task G4): its own automatic mask when
    /// those are used, else the FITS mask, else none.
    fn mask_of(&self, s: usize) -> Option<&[bool]> {
        if self.use_masks {
            Some(&self.masks[s])
        } else {
            self.clean.as_deref()
        }
    }

    /// `FindActiveScaleConvolvedMaxima` on the integrated working map.
    fn find_maxima(&mut self, integrated: &[f64]) -> Result<(), String> {
        let n = self.n;
        for s in 0..self.scales.len() {
            if !self.scales[s].active {
                continue;
            }
            let border = (self.scales[s].scale * 0.5).ceil() as usize;
            let conv = self.convolve(s, integrated)?;
            let found = match self.mask_of(s) {
                None => peak(&conv, n, border),
                Some(m) => peak_masked(&conv, n, border, m),
            };
            let (value, pixel) = found.unwrap_or((0.0, 0));
            self.scales[s].value = value;
            self.scales[s].pixel = pixel;
        }
        Ok(())
    }

    /// `SelectMaximumScale`: the active scale of largest `|value · bias|`, the
    /// lowest on ties.
    fn select(&self) -> Option<usize> {
        let mut best: Option<(f64, usize)> = None;
        for (i, s) in self.scales.iter().enumerate() {
            if s.active {
                let v = (s.value * s.bias).abs();
                if best.is_none_or(|(b, _)| v > b) {
                    best = Some((v, i));
                }
            }
        }
        best.map(|b| b.1)
    }

    /// `ActivateScales` with the values found before the sub-minor loop.
    fn activate(&mut self, last: usize, minor_gain: f64) {
        let reference =
            (self.scales[last].value).abs() * (1.0 - minor_gain) * self.scales[last].bias;
        for i in 0..self.scales.len() {
            let on = i == last || self.scales[i].value.abs() * self.scales[i].bias > reference;
            self.scales[i].active = on;
        }
    }

    /// The twice-convolved `n × n` PSF of every channel at scale `s` (scale 0:
    /// the PSF), taken out of the cache; [`Run::put_twice`] returns it.
    fn take_twice(&mut self, s: usize) -> Result<Vec<Vec<f64>>, String> {
        if self.twice.reserve(s) {
            let psfs: Vec<Vec<f64>> = self.psfs.iter().map(|p| p.to_vec()).collect();
            let mut out = Vec::with_capacity(psfs.len());
            for p in psfs {
                let once = self.convolve(s, &p)?;
                out.push(self.convolve(s, &once)?);
            }
            self.twice.built += 1;
            return Ok(out);
        }
        Ok(self.twice.items[s].take().expect("held"))
    }

    fn put_twice(&mut self, s: usize, t: Vec<Vec<f64>>) {
        self.twice.items[s] = Some(t);
    }
}

/// `argmax |Σ a_k v_k[i]|` over the selected pixels with radler's
/// `GetMaxComponent` order; the signed integrated value.
fn sub_max(values: &[Vec<f64>], a: &[f64], scratch: &mut [f64]) -> (usize, f64) {
    for (i, s) in scratch.iter_mut().enumerate() {
        let mut t = 0.0;
        for (v, &ak) in values.iter().zip(a) {
            t += ak * v[i];
        }
        *s = t;
    }
    let mut best = 0usize;
    let mut max = scratch[0];
    for (i, &v) in scratch.iter().enumerate() {
        if v.abs() > max {
            best = i;
            max = v.abs();
        }
    }
    (best, scratch[best])
}

/// Multiscale deconvolution of `channels` (a measurement, the beam from its
/// `2n` PSF and the `n × n` PSF crop each), joined with channel weights
/// `weights` (one channel of weight one: a plain run), the polynomial `fit`
/// applied to every component's channel values when given. `beam_pixels` is
/// the theoretic beam in pixels (at most 0 or not finite: one pixel, as radler).
pub fn run_multiscale<M: Measurement>(
    channels: &[(&M, &Beam, &[f64])],
    weights: &[f64],
    fit: Option<&PolynomialFit>,
    settings: &Settings,
    ms: &MultiscaleSettings,
    beam_pixels: f64,
) -> Result<Multiscale, String> {
    run_multiscale_masked(channels, weights, fit, settings, ms, beam_pixels, None)
}

/// [`run_multiscale`] with clean masks (task G4, `research/g4-masks.md`):
/// the FITS mask confines the scale peaks and the sub-minor loops' pixels;
/// the automatic mask follows radler's stages with one mask per scale.
pub fn run_multiscale_masked<M: Measurement>(
    channels: &[(&M, &Beam, &[f64])],
    weights: &[f64],
    fit: Option<&PolynomialFit>,
    settings: &Settings,
    ms: &MultiscaleSettings,
    beam_pixels: f64,
    masking: Option<&super::mask::Masking>,
) -> Result<Multiscale, String> {
    use super::mask;
    let start = Instant::now();
    let s = settings;
    let kc = channels.len();
    if kc == 0 || weights.len() != kc {
        return Err("one weight per channel is needed".into());
    }
    if weights.iter().any(|&w| !(w > 0.0 && w.is_finite())) {
        return Err("every channel needs a positive weight".into());
    }
    if fit.is_some_and(|f| f.frequencies.len() != kc) {
        return Err("the fit needs one frequency per channel".into());
    }
    let n = channels[0].0.side();
    if channels
        .iter()
        .any(|(m, b, p)| m.side() != n || b.n != n || p.len() != n * n)
    {
        return Err("every channel's measurement, beam and PSF must have the image side".into());
    }
    if !(s.gain > 0.0 && s.gain < 2.0) {
        return Err("the gain must be in (0, 2)".into());
    }
    if !(ms.sub_minor_gain > 0.0 && ms.sub_minor_gain <= 1.0) {
        return Err("-multiscale-gain must be in (0, 1]".into());
    }
    if !(ms.scale_bias > 0.0 && ms.scale_bias.is_finite()) {
        return Err("-multiscale-scale-bias must be positive".into());
    }
    if ms.scales.iter().any(|&v| !(v >= 0.0 && v.is_finite())) {
        return Err("-multiscale-scales must be non-negative".into());
    }
    match s.cycle_stop {
        CycleStop::PeakFraction(_) | CycleStop::MeasuredStale { .. } | CycleStop::Threshold => {}
        _ => {
            return Err(
                "-multiscale takes -mgain, the measured rule or -minor-to-threshold \
                 (research/g5-multiscale.md)"
                    .into(),
            );
        }
    }
    if s.audit {
        return Err("-multiscale does not take -audit".into());
    }
    let beam = if beam_pixels > 0.0 && beam_pixels.is_finite() {
        beam_pixels
    } else {
        1.0
    };
    let wsum: f64 = weights.iter().sum();
    let a: Vec<f64> = weights.iter().map(|w| w / wsum).collect();
    let level = s.level.unwrap_or_else(kernels::level);
    // The scales, their shapes and radler's numbers on the integrated PSF.
    let values = scale_list(beam, n, ms);
    let psf_int = integrate(
        &channels.iter().map(|c| c.2.to_vec()).collect::<Vec<_>>(),
        &a,
    );
    let mut scales = Vec::with_capacity(values.len());
    for (i, &v) in values.iter().enumerate() {
        let (side, kernel) = shape_function(v, n, ms.shape);
        if side > 2 * n - 1 {
            return Err(format!("the scale {v} needs a shape wider than the image"));
        }
        // radler logs the automatic scale 0's kernel peak at 2b.
        let logged = if ms.scales.is_empty() && i == 0 {
            beam * 2.0
        } else {
            v
        };
        let (ks, kv) = shape_function(logged, n, ms.shape);
        scales.push(Scale {
            scale: v,
            kernel_side: side,
            kernel,
            kernel_peak: kv[ks / 2 + (ks / 2) * ks],
            bias: bias_factor(v, beam, values.len(), ms.scale_bias),
            psf_peak: 0.0,
            gain: 0.0,
            active: true,
            value: 0.0,
            pixel: 0,
            components: 0,
            flux: 0.0,
        });
    }
    // One convolver holds a (n + 1) × 2n half spectrum and an n × (n + 1)
    // work space, complex; a twice-convolved PSF is n × n per channel.
    let convolver_bytes = 3 * n * (n + 1) * 16;
    let twice_bytes = kc * n * n * 8;
    let count = scales.len();
    let mut run = Run {
        n,
        beams: channels.iter().map(|c| c.1).collect(),
        psfs: channels.iter().map(|c| c.2).collect(),
        scales,
        convolvers: Cache::new(count, CACHE_BYTES / convolver_bytes),
        twice: Cache::new(count, CACHE_BYTES / twice_bytes),
        convolutions: 0,
        clean: masking.and_then(|m| m.fits.clone()),
        masks: Vec::new(),
        track: false,
        use_masks: false,
    };
    let mut auto = match masking.and_then(|m| m.auto) {
        Some(am) => Some(mask::AutoState::new(
            am,
            s.auto_threshold,
            s.threshold,
            super::auto_mask_mgain(s.cycle_stop)?,
        )),
        None => None,
    };
    let auto_mgain = match auto.as_ref() {
        Some(am) => am.mgain,
        None => 0.0,
    };
    if auto.is_some() {
        run.masks = vec![vec![false; n * n]; count];
    }
    let mut another_prev = true;
    for i in 0..count {
        // radler's `Transform` is circular on the n × n PSF: the shape summed
        // with the PSF wrapped around its edges, at the centre. Post hoc
        // (research/g5-multiscale.md): the linear sum missed radler's by 3e-4
        // at the 922-pixel scale of S2.
        let sc = &run.scales[i];
        let psf_peak = circular_peak(&psf_int, n, &sc.kernel, sc.kernel_side);
        if !(psf_peak > 0.0 && psf_peak.is_finite()) {
            return Err(format!(
                "the PSF convolved with scale {} has no positive peak",
                run.scales[i].scale
            ));
        }
        run.scales[i].psf_peak = psf_peak;
        run.scales[i].gain = s.gain / psf_peak;
    }
    drop(psf_int);
    memory::mark("multiscale: scales");
    let mut timings = Timings::default();
    let mut models = vec![vec![0.0; n * n]; kc];
    let t = Instant::now();
    let mut residuals = Vec::with_capacity(kc);
    let mut qs = Vec::with_capacity(kc);
    for (k, (m, _, _)) in channels.iter().enumerate() {
        let (r, q) = m.residual(&models[k])?;
        residuals.push(r);
        qs.push(q);
    }
    timings.initial = t.elapsed().as_secs_f64();
    let dirty = residuals.clone();
    let mut residual_int = integrate(&residuals, &a);
    let dirty_int = residual_int.clone();
    let weighted = |q: &[f64]| q.iter().zip(&a).map(|(q, a)| a * q).sum::<f64>();
    let q0 = weighted(&qs);
    let mut q = q0;
    let mut stale_per_flux = 0.0_f64;
    let mut steps: Vec<CleanStep> = Vec::new();
    let mut cycles: Vec<Cycle> = Vec::new();
    let mut end = MultiscaleEnd::Normal;
    let mut sub_minor_loops = 0usize;
    let mut conv_buf = vec![0.0; n * n];
    let mut values_ch = vec![0.0; kc];
    let stop = loop {
        let index = cycles.len() + 1;
        let mut gain = s.gain;
        let mut threshold = match auto.as_mut() {
            None => effective_threshold(&residual_int, s),
            Some(am) => {
                if !another_prev {
                    break StopReason::Threshold;
                }
                let c = am.begin(index, &residual_int);
                if c.gain_doubled {
                    gain = (2.0 * s.gain).min(1.0);
                }
                // Phase 1 tracks the scale masks, phase 2 cleans inside them.
                run.use_masks = c.use_auto;
                run.track = !c.use_auto;
                for sc in &mut run.scales {
                    sc.gain = gain / sc.psf_peak;
                }
                c.threshold
            }
        };
        for sc in &mut run.scales {
            sc.active = true;
        }
        run.find_maxima(&residual_int)?;
        let Some(mut sel) = run.select() else {
            end = MultiscaleEnd::Stalled;
            break StopReason::Threshold;
        };
        let mut first_peak = (run.scales[sel].value * run.scales[sel].bias).abs();
        if auto.is_none() && (first_peak < threshold || first_peak == 0.0) {
            break StopReason::Threshold;
        }
        if steps.len() >= s.max_components {
            break StopReason::Components;
        }
        if cycles.len() >= s.max_major {
            break StopReason::MajorCycles;
        }
        let mut ct = Timings::default();
        let models_major = models.clone();
        let mut maps = residuals.clone();
        let mut work_int = residual_int.clone();
        let taken_before = steps.len();
        let stale_used = stale_per_flux;
        let mut abs_flux = 0.0_f64;
        let first_cycle = cycles.is_empty();
        let mut stop_rule = s.cycle_stop;
        let cycle_level = |abs_flux: f64, first_peak: f64, rule: CycleStop| -> f64 {
            match rule {
                CycleStop::PeakFraction(g) => (1.0 - g) * first_peak,
                CycleStop::MeasuredStale { rho, g, floor } => {
                    if first_cycle {
                        (1.0 - g) * first_peak
                    } else {
                        (rho * stale_used * abs_flux).max(floor * first_peak)
                    }
                }
                _ => 0.0,
            }
        };
        // radler's `isFinalThreshold`: when the threshold is the cycle's level
        // from the start, the run ends with this cycle (post hoc, research/
        // g5-multiscale.md: on S2 the exact checks after it added 17 cycles of
        // a few components each just above the threshold).
        let is_final = s.cycle_stop != CycleStop::Threshold
            && threshold > cycle_level(0.0, first_peak, stop_rule);
        let mut countdown = 8usize.max(run.scales.len() * 3 / 2);
        let mut diverging = false;
        let mut minor_stop = MinorStop::PeakRule;
        let minor_start = Instant::now();
        let mut stage = 0;
        'stages: loop {
            loop {
                let level_now = cycle_level(abs_flux, first_peak, stop_rule).max(threshold);
                let sc_peak = (run.scales[sel].value * run.scales[sel].bias).abs();
                if steps.len() >= s.max_components {
                    minor_stop = MinorStop::Budget;
                    break;
                }
                let below = sc_peak <= level_now;
                if below || countdown == 0 || diverging {
                    minor_stop = if below && level_now <= threshold {
                        MinorStop::Threshold
                    } else {
                        MinorStop::PeakRule
                    };
                    break;
                }
                // The convolved channel residuals at this scale, and its twice-
                // convolved PSFs.
                let mut conv: Vec<Vec<f64>> = Vec::with_capacity(kc);
                for map in &maps {
                    conv.push(run.convolve(sel, map)?);
                }
                let bias = run.scales[sel].bias;
                let gain_s = run.scales[sel].gain;
                let sub_gain_level = sc_peak * (1.0 - ms.sub_minor_gain);
                let mut first_sub = sub_gain_level;
                if level_now > first_sub {
                    first_sub = level_now;
                    countdown -= 1;
                }
                let thr = first_sub / bias;
                let border = (run.scales[sel].scale * 0.5).ceil() as usize;
                // The selected pixels (`findPeakPositions`).
                let lo = border;
                let hi = n.saturating_sub(border).max(lo);
                let mut positions: Vec<usize> = Vec::new();
                for row in lo..hi {
                    for col in lo..hi {
                        let p = row * n + col;
                        let mut v = 0.0;
                        for k in 0..kc {
                            v += a[k] * conv[k][p];
                        }
                        if v.abs() >= thr && run.mask_of(sel).is_none_or(|m| m[p]) {
                            positions.push(p);
                        }
                    }
                }
                if positions.is_empty() {
                    end = MultiscaleEnd::Stalled;
                    minor_stop = MinorStop::PeakRule;
                    break;
                }
                sub_minor_loops += 1;
                let np = positions.len();
                let mut vals: Vec<Vec<f64>> = (0..kc)
                    .map(|k| positions.iter().map(|&p| conv[k][p]).collect())
                    .collect();
                drop(conv);
                let mut sub_model: Vec<Vec<f64>> = vec![vec![0.0; np]; kc];
                let mut scratch = vec![0.0; np];
                let (mut mc, mut maxv) = sub_max(&vals, &a, &mut scratch);
                let start_value = maxv.abs();
                let twice = run.take_twice(sel)?;
                let half = (n / 2) as isize;
                let pos_xy: Vec<(isize, isize)> = positions
                    .iter()
                    .map(|&p| ((p % n) as isize, (p / n) as isize))
                    .collect();
                while maxv.abs() > thr && steps.len() < s.max_components && !diverging {
                    for k in 0..kc {
                        values_ch[k] = vals[k][mc] * gain_s;
                    }
                    if let Some(f) = fit {
                        f.fit_and_evaluate(&mut values_ch);
                    }
                    let (mx, my) = pos_xy[mc];
                    for k in 0..kc {
                        let c = values_ch[k];
                        sub_model[k][mc] += c;
                        abs_flux += a[k] * c.abs();
                        let t = &twice[k];
                        let v = &mut vals[k];
                        v.par_iter_mut()
                            .zip(pos_xy.par_iter())
                            .for_each(|(val, &(x, y))| {
                                let (px, py) = (x - mx + half, y - my + half);
                                if px >= 0 && px < n as isize && py >= 0 && py < n as isize {
                                    *val -= t[py as usize * n + px as usize] * c;
                                }
                            });
                    }
                    let mut integrated = 0.0;
                    for k in 0..kc {
                        integrated += a[k] * values_ch[k];
                    }
                    run.scales[sel].flux += integrated;
                    run.scales[sel].components += 1;
                    steps.push(CleanStep {
                        pixel: positions[mc],
                        peak: maxv,
                    });
                    if let Some(am) = auto.as_mut() {
                        am.record_pick(run.mask_of(sel), positions[mc]);
                    }
                    (mc, maxv) = sub_max(&vals, &a, &mut scratch);
                    if ms.divergence_limit != 0.0 {
                        diverging = maxv.abs() > start_value * ms.divergence_limit;
                    }
                }
                run.put_twice(sel, twice);
                if run.track {
                    for (i, &p) in positions.iter().enumerate() {
                        if sub_model.iter().any(|m| m[i] != 0.0) {
                            run.masks[sel][p] = true;
                        }
                    }
                }
                if ms.divergence_limit != 0.0 && maxv.abs() > first_peak * ms.divergence_limit {
                    diverging = true;
                }
                if diverging {
                    end = MultiscaleEnd::Diverged;
                }
                // The components, convolved with the shape, join the model; the
                // working maps are made exact for each channel's beam.
                let tr = Instant::now();
                for k in 0..kc {
                    conv_buf.fill(0.0);
                    for (i, &p) in positions.iter().enumerate() {
                        conv_buf[p] = sub_model[k][i];
                    }
                    let delta = run.convolve(sel, &conv_buf)?;
                    models[k]
                        .par_iter_mut()
                        .zip(delta.par_iter())
                        .for_each(|(m, d)| *m += d);
                    let diff: Vec<f64> = models[k]
                        .par_iter()
                        .zip(models_major[k].par_iter())
                        .map(|(m, b)| m - b)
                        .collect();
                    let bd = run.beams[k].convolve(&diff);
                    run.convolutions += 1;
                    maps[k]
                        .par_iter_mut()
                        .zip(residuals[k].par_iter())
                        .zip(bd.par_iter())
                        .for_each(|((w, r), b)| *w = r - b);
                }
                work_int = integrate(&maps, &a);
                ct.resync += tr.elapsed().as_secs_f64();
                run.activate(sel, gain);
                run.find_maxima(&work_int)?;
                match run.select() {
                    Some(next) => sel = next,
                    None => {
                        end = MultiscaleEnd::Stalled;
                        break;
                    }
                }
                if diverging {
                    break;
                }
            }
            // The automatic mask (task G4): radler's decision after the first
            // minor loop and the continued one, inside the scale masks.
            if let Some(am) = auto.as_mut().filter(|_| stage == 0) {
                stage = 1;
                let radler_final = threshold > (1.0 - auto_mgain) * first_peak;
                let end_peak = (run.scales[sel].value * run.scales[sel].bias).abs();
                let stage_end = mask::StageEnd {
                    another: !radler_final
                        && !diverging
                        && end != MultiscaleEnd::Stalled
                        && steps.len() < s.max_components,
                    start_peak: first_peak,
                    end_peak,
                };
                let (another, cont) = am.end_stage(
                    index,
                    stage_end,
                    index < s.max_major,
                    steps.len() < s.max_components,
                );
                another_prev = another;
                if let Some(k) = cont {
                    run.use_masks = true;
                    run.track = false;
                    for sc in &mut run.scales {
                        sc.active = true;
                    }
                    run.find_maxima(&work_int)?;
                    if let Some(next) = run.select() {
                        sel = next;
                        first_peak = (run.scales[sel].value * run.scales[sel].bias).abs();
                        threshold = k.threshold;
                        stop_rule = CycleStop::PeakFraction(k.gain);
                        countdown = 8usize.max(run.scales.len() * 3 / 2);
                        continue 'stages;
                    }
                }
            }
            break;
        }
        ct.minor = minor_start.elapsed().as_secs_f64() - ct.resync;
        memory::mark(&format!("cycle {}: minor", cycles.len() + 1));
        // The predicted misfit change, exact for the image-domain beams.
        let mut predicted = 0.0;
        for k in 0..kc {
            let dot: f64 = models[k]
                .par_iter()
                .zip(models_major[k].par_iter())
                .zip(residuals[k].par_iter().zip(maps[k].par_iter()))
                .map(|((m, b), (r, w))| (m - b) * (r + w))
                .sum();
            predicted -= 0.5 * a[k] * dot;
        }
        let tm = Instant::now();
        let mut next = Vec::with_capacity(kc);
        for (k, (m, _, _)) in channels.iter().enumerate() {
            let (r, qk) = m.residual(&models[k])?;
            next.push(r);
            qs[k] = qk;
        }
        ct.major = tm.elapsed().as_secs_f64();
        let next_int = integrate(&next, &a);
        let q_next = weighted(&qs);
        let stale_linf = next_int
            .par_iter()
            .zip(work_int.par_iter())
            .map(|(x, y)| (x - y).abs())
            .reduce(|| 0.0, f64::max);
        if abs_flux > 0.0 {
            stale_per_flux = stale_linf / abs_flux;
        }
        let components = steps.len() - taken_before;
        let dq_exact = q_next - q;
        let gap = dq_exact - predicted;
        cycles.push(Cycle {
            index: cycles.len(),
            components,
            resyncs: Resyncs::default(),
            stop: minor_stop,
            peak_start: first_peak,
            threshold,
            fraction: 0.0,
            q_before: q,
            q_after: q_next,
            dq_exact,
            dq_predicted: predicted,
            gap,
            gap_relative: gap / q,
            ascending: dq_exact > 0.0,
            abs_flux,
            stale_linf,
            stale_per_flux_used: stale_used,
            bound_linf: 0.0,
            bound_violations: 0,
            tau_min: f64::NAN,
            timings: ct,
        });
        timings.minor += ct.minor;
        timings.resync += ct.resync;
        timings.major += ct.major;
        residuals = next;
        residual_int = next_int;
        q = q_next;
        if auto.is_some() {
            if end == MultiscaleEnd::Diverged {
                break StopReason::Threshold;
            }
            continue;
        }
        if components == 0 {
            end = MultiscaleEnd::Stalled;
            break StopReason::Threshold;
        }
        if is_final {
            break StopReason::Threshold;
        }
        if end == MultiscaleEnd::Diverged {
            break StopReason::Threshold;
        }
    };
    timings.total = start.elapsed().as_secs_f64();
    let model_int = integrate(&models, &a);
    let f = channels.iter().map(|c| c.1.f).fold(0.0, f64::max);
    let scales = run
        .scales
        .iter()
        .map(|sc| ScaleReport {
            scale: sc.scale,
            kernel_side: sc.kernel_side,
            kernel_peak: sc.kernel_peak,
            bias: sc.bias,
            psf_peak: sc.psf_peak,
            gain: sc.gain,
            components: sc.components,
            flux: sc.flux,
        })
        .collect();
    Ok(Multiscale {
        joined: Joined {
            integrated: Outcome {
                dirty: dirty_int,
                model: model_int,
                residual: residual_int,
                q0,
                q_final: q,
                steps,
                taus: Vec::new(),
                cycles,
                stop,
                f,
                patch: channels[0].1.patch,
                resyncs: Resyncs::default(),
                timings,
                correction_terms: 0,
                work: Work::default(),
                audit_max_error: None,
                level,
            },
            dirty,
            model: models,
            residual: residuals,
            q_final: qs,
            auto,
        },
        beam_pixels: beam,
        scales,
        end,
        sub_minor_loops,
        convolutions: run.convolutions,
        convolvers_built: run.convolvers.built,
        twice_built: run.twice.built,
    })
}

impl Multiscale {
    /// The multiscale part of the report.
    pub fn to_json(&self, settings: &MultiscaleSettings, beam_rad: Option<f64>) -> String {
        use super::json::*;
        let scales: Vec<String> = self
            .scales
            .iter()
            .map(|s| {
                obj(&[
                    ("scale_pixels", num(s.scale)),
                    ("kernel_side", s.kernel_side.to_string()),
                    ("kernel_peak", num(s.kernel_peak)),
                    ("bias_factor", num(s.bias)),
                    ("psf_peak", num(s.psf_peak)),
                    ("gain", num(s.gain)),
                    ("components", s.components.to_string()),
                    ("flux", num(s.flux)),
                ])
            })
            .collect();
        obj(&[
            ("shape", text(settings.shape.name())),
            ("scale_bias", num(settings.scale_bias)),
            ("sub_minor_gain", num(settings.sub_minor_gain)),
            ("max_scales", settings.max_scales.to_string()),
            (
                "scales_given",
                arr(&settings.scales.iter().map(|&v| num(v)).collect::<Vec<_>>()),
            ),
            ("divergence_limit", num(settings.divergence_limit)),
            ("theoretic_beam_rad", opt(beam_rad)),
            ("beam_pixels", num(self.beam_pixels)),
            ("end", text(&format!("{:?}", self.end))),
            ("sub_minor_loops", self.sub_minor_loops.to_string()),
            ("convolutions", self.convolutions.to_string()),
            ("convolvers_built", self.convolvers_built.to_string()),
            ("twice_convolved_psfs_built", self.twice_built.to_string()),
            ("cache_bytes", CACHE_BYTES.to_string()),
            ("scales", arr(&scales)),
        ])
    }

    /// WSClean's scale lines (`ConvolvePsfs`) and summary.
    pub fn print_scales(&self) {
        for s in &self.scales {
            println!(
                "multiscale: scale {} px, bias factor {:.4}, psf peak {:.6}, gain {:.6}, kernel peak {:.6e}, {} components, {:.6} Jy",
                s.scale.round(),
                s.bias,
                s.psf_peak,
                s.gain,
                s.kernel_peak,
                s.components,
                s.flux
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::clean_certified::{Complex, WgridMeasurement};

    #[test]
    fn shapes_have_radlers_sides_and_unit_sum() {
        // Tapered quadratic: 2 ceil(s/2) + 1 pixels; Gaussian: a 12 sigma box.
        for (s, side) in [(0.0, 1), (4.0, 5), (5.0, 7), (9.6, 11), (40.0, 41)] {
            let (k, v) = shape_function(s, 1024, Shape::TaperedQuadratic);
            assert_eq!(k, side, "scale {s}");
            // radler's f32 kernel: unit sum to f32 rounding.
            assert!((v.iter().sum::<f64>() - 1.0).abs() < 1e-5);
            // Symmetric under both flips and the transpose.
            for y in 0..k {
                for x in 0..k {
                    assert!((v[y * k + x] - v[x * k + y]).abs() < 1e-15);
                    assert!((v[y * k + x] - v[(k - 1 - y) * k + x]).abs() < 1e-15);
                }
            }
        }
        let (k, v) = shape_function(16.0, 1024, Shape::Gaussian);
        // sigma = 3, box ceil(18) * 2 + 1 = 37.
        assert_eq!(k, 37);
        assert!((v.iter().sum::<f64>() - 1.0).abs() < 1e-5);
        let c = v[18 * k + 18];
        let one = v[18 * k + 19];
        assert!((one / c - (-1.0_f64 / 18.0).exp()).abs() < 1e-6);
        // Capped at the image side, odd.
        assert_eq!(shape_function(400.0, 64, Shape::Gaussian).0, 63);
        assert_eq!(shape_function(0.0, 64, Shape::Gaussian).0, 1);
        // The tapered quadratic's corners are outside the Hann window.
        let (k, v) = shape_function(10.0, 1024, Shape::TaperedQuadratic);
        assert_eq!(v[0], 0.0);
        assert!(v[(k / 2) * k + k / 2] > v[(k / 2) * k + k / 2 + 2]);
    }

    #[test]
    fn scales_and_bias_follow_radler() {
        let ms = MultiscaleSettings::default();
        // b = 2.5 pixels on 2048: 0, 10, 20, ..., 640 (1280 is not below 1024).
        let s = scale_list(2.5, 2048, &ms);
        assert_eq!(s, vec![0.0, 10.0, 20.0, 40.0, 80.0, 160.0, 320.0, 640.0]);
        let s = scale_list(
            2.5,
            2048,
            &MultiscaleSettings {
                max_scales: 3,
                ..ms.clone()
            },
        );
        assert_eq!(s, vec![0.0, 10.0, 20.0]);
        let s = scale_list(
            2.5,
            2048,
            &MultiscaleSettings {
                scales: vec![12.5, 0.0, 5.0, 5.0],
                ..ms.clone()
            },
        );
        assert_eq!(s, vec![0.0, 5.0, 5.0, 12.5]);
        // The first automatic scale is 4b: exponent log2(4b / 2b) = 1.
        assert_eq!(bias_factor(0.0, 2.5, 8, 0.6), 1.0);
        assert!((bias_factor(10.0, 2.5, 8, 0.6) - 1.0 / 0.6).abs() < 1e-15);
        assert!((bias_factor(20.0, 2.5, 8, 0.6) - 1.0 / 0.36).abs() < 1e-12);
        assert_eq!(bias_factor(10.0, 2.5, 1, 0.6), 1.0);
    }

    #[test]
    fn theoretic_beam_is_the_longest_weighted_baseline() {
        let freq = [1.0e9, 2.0e9];
        let uvw = [100.0, 0.0, 0.0, 300.0, 400.0, 0.0, 9000.0, 0.0, 0.0];
        // Row 1 channel 1 carries no weight; row 2 falls outside a small grid.
        let w = [1.0, 1.0, 1.0, 0.0, 1.0, 1.0];
        let lambda = |f: f64| 299_792_458.0 / f;
        let pixel = 1e-5;
        let got = theoretic_beam(&uvw, &freq, &w, 1024, pixel).unwrap();
        // Row 2: u/λ at 2 GHz = 60,000; x = 60,000 · 1e-5 · 1024 = 614 > 512.
        // At 1 GHz: 30,000 → 307, inside. Row 1 at 1 GHz: 500 m / λ.
        let want = 1.0 / (9000.0 / lambda(1e9)).max(500.0 / lambda(1e9));
        assert!((got - want).abs() < 1e-15 * want, "{got} {want}");
    }

    fn measurement(n: usize, model: &[f64]) -> WgridMeasurement {
        let mut state = 11u64;
        let mut next = move || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / (1u64 << 53) as f64 - 0.5
        };
        let nrow = 3000;
        let uvw: Vec<f64> = (0..3 * nrow)
            .map(|i| next() * if i % 3 == 2 { 20.0 } else { 6000.0 })
            .collect();
        let cell = 4e-5;
        let opts = crate::gemclean::sim::imaging_options();
        let empty = WgridMeasurement::new(
            uvw.clone(),
            vec![1.2e9],
            vec![Complex::new(0.0, 0.0); nrow],
            vec![1.0; nrow],
            n,
            cell,
            1e-9,
            opts,
        )
        .unwrap();
        let vis = empty.predict(model).unwrap();
        WgridMeasurement::new(uvw, vec![1.2e9], vis, vec![1.0; nrow], n, cell, 1e-9, opts).unwrap()
    }

    /// An extended Gaussian and a point: multiscale recovers both fluxes and
    /// cleans the Gaussian on its larger scales.
    #[test]
    fn recovers_an_extended_source() {
        let n = 64;
        let mut sky = vec![0.0; n * n];
        let (cx, cy, sigma) = (40.0, 24.0, 3.0);
        for y in 0..n {
            for x in 0..n {
                let d2 = (x as f64 - cx).powi(2) + (y as f64 - cy).powi(2);
                sky[y * n + x] = (-d2 / (2.0 * sigma * sigma)).exp();
            }
        }
        let total: f64 = sky.iter().sum();
        for v in &mut sky {
            *v *= 1.0 / total;
        }
        sky[18 * n + 14] += 0.5;
        let m = measurement(n, &sky);
        let psf2n = m.psf_image(2 * n).unwrap();
        let beam = Beam::from_double(n, &psf2n, 16).unwrap();
        let mut psf = vec![0.0; n * n];
        for i in 0..n {
            for j in 0..n {
                psf[i * n + j] = psf2n[(i + n / 2) * 2 * n + j + n / 2];
            }
        }
        let settings = Settings {
            threshold: 2e-4,
            max_components: 20_000,
            cycle_stop: CycleStop::PeakFraction(0.8),
            ..Settings::default()
        };
        let ms = MultiscaleSettings {
            scales: vec![0.0, 4.0, 8.0],
            ..MultiscaleSettings::default()
        };
        let out =
            run_multiscale(&[(&m, &beam, &psf[..])], &[1.0], None, &settings, &ms, 1.0).unwrap();
        let model = &out.joined.model[0];
        let near = |px: f64, py: f64, r: f64| {
            let mut s = 0.0;
            for y in 0..n {
                for x in 0..n {
                    if (x as f64 - px).hypot(y as f64 - py) <= r {
                        s += model[y * n + x];
                    }
                }
            }
            s
        };
        let g = near(cx, cy, 10.0);
        let p = near(14.0, 18.0, 3.0);
        let total: f64 = model.iter().sum();
        let report: Vec<(f64, usize, f64)> = out
            .scales
            .iter()
            .map(|s| (s.scale, s.components, s.flux))
            .collect();
        let why = format!(
            "Gaussian {g}, point {p}, total {total}, scales {report:?}, cycles {}",
            out.joined.integrated.cycles.len()
        );
        assert!((g - 1.0).abs() < 0.03, "{why}");
        assert!((p - 0.5).abs() < 0.02, "{why}");
        assert!(out.scales.iter().skip(1).any(|s| s.components > 0));
        assert_eq!(out.joined.integrated.stop, StopReason::Threshold);
        // One channel of weight one: the integrated run is the channel's.
        assert_eq!(out.joined.integrated.model, out.joined.model[0]);
        assert_eq!(out.joined.integrated.residual, out.joined.residual[0]);
        // The image-domain prediction of the first cycle is close to exact.
        let c = &out.joined.integrated.cycles[0];
        assert!(c.gap_relative.abs() < 1e-3, "{}", c.gap_relative);
    }

    /// Two points and a box mask around one (task G4): Högbom and multiscale
    /// put every component inside the box, and the point outside stays in
    /// the residual.
    #[test]
    fn a_fits_mask_confines_the_components() {
        use crate::gemclean::mask::Masking;
        let n = 64;
        let mut sky = vec![0.0; n * n];
        sky[20 * n + 40] = 1.0;
        sky[44 * n + 18] = 0.6;
        let m = measurement(n, &sky);
        let psf2n = m.psf_image(2 * n).unwrap();
        let beam = Beam::from_double(n, &psf2n, 16).unwrap();
        let mut psf = vec![0.0; n * n];
        for i in 0..n {
            for j in 0..n {
                psf[i * n + j] = psf2n[(i + n / 2) * 2 * n + j + n / 2];
            }
        }
        // An asymmetric box around the first point only.
        let mut fits = vec![false; n * n];
        for y in 16..27 {
            for x in 35..43 {
                fits[y * n + x] = true;
            }
        }
        let masking = Masking {
            fits: Some(fits.clone()),
            auto: None,
        };
        let settings = Settings {
            threshold: 1e-3,
            max_components: 5_000,
            cycle_stop: CycleStop::PeakFraction(0.8),
            ..Settings::default()
        };
        let (h, _) =
            crate::gemclean::run_masked(&m, &beam, &settings, None, None, Some(&masking)).unwrap();
        assert!(!h.steps.is_empty());
        assert!(h.steps.iter().all(|st| fits[st.pixel]));
        let flux: f64 = h.model.iter().sum();
        assert!((flux - 1.0).abs() < 0.2, "{flux}");
        assert!(h.residual[44 * n + 18].abs() > 0.4);
        let ms = MultiscaleSettings {
            scales: vec![0.0, 4.0],
            ..MultiscaleSettings::default()
        };
        let out = run_multiscale_masked(
            &[(&m, &beam, &psf[..])],
            &[1.0],
            None,
            &settings,
            &ms,
            1.0,
            Some(&masking),
        )
        .unwrap();
        let steps = &out.joined.integrated.steps;
        assert!(!steps.is_empty() && steps.iter().all(|st| fits[st.pixel]));
        assert!(out.joined.residual[0][44 * n + 18].abs() > 0.4);
    }

    /// The automatic mask: phase 1 cleans to the mask threshold, the switch
    /// is recorded, phase 2 cleans deeper inside the mask only.
    #[test]
    fn the_auto_mask_switches_and_stays_inside() {
        use crate::gemclean::mask::{AutoMask, Masking};
        let n = 64;
        let mut sky = vec![0.0; n * n];
        sky[20 * n + 40] = 1.0;
        sky[44 * n + 18] = 0.05;
        let m = measurement(n, &sky);
        let psf2n = m.psf_image(2 * n).unwrap();
        let beam = Beam::from_double(n, &psf2n, 16).unwrap();
        let masking = Masking {
            fits: None,
            auto: Some(AutoMask {
                sigma: None,
                absolute: Some(0.1),
                nmiter: 2,
            }),
        };
        let settings = Settings {
            threshold: 1e-3,
            max_components: 5_000,
            cycle_stop: CycleStop::PeakFraction(0.8),
            ..Settings::default()
        };
        let (h, auto) =
            crate::gemclean::run_masked(&m, &beam, &settings, None, None, Some(&masking)).unwrap();
        let auto = auto.unwrap();
        let fin = auto.finishing.expect("the mask threshold is reached");
        // The 0.05 Jy point is below the mask threshold: never cleaned.
        let far = h
            .steps
            .iter()
            .filter(|st| {
                let (x, y) = (st.pixel % n, st.pixel / n);
                (x as isize - 18).abs() < 4 && (y as isize - 44).abs() < 4
            })
            .count();
        assert_eq!(far, 0);
        assert!(h.cycles.len() <= fin + 2);
        assert!((h.model.iter().sum::<f64>() - 1.0).abs() < 0.01);
    }
}
