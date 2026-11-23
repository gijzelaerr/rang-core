// SPDX-License-Identifier: GPL-3.0-or-later AND LGPL-3.0-only
//! Multiscale CLEAN for gemclean: WSClean 3.7's `-multiscale`, radler's
//! `MultiScaleAlgorithm` with its sub-minor loop (`research/g5-multiscale.md`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//! Parts follow radler 76fe4474 (LGPL-3.0-only, `// SPDX-License-Identifier:
//! LGPL-3.0-only` in each file read), conveyed under the GPL, version 3, as
//! LGPL-3.0 section 2(b) allows: notice in THIRD-PARTY-NOTICES.txt.
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

/// The beam the scale bias is referenced to (`-multiscale-bias-reference`,
/// issue #23 step 4, `research/multiscale-flux-fix.md`).
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum BiasReference {
    /// radler's: the theoretic beam `b`, `bias = β^(−log2(s / 2b))`, also for a
    /// given scale list.
    Theoretic,
    /// The first non-zero scale `α₁` taken as radler's first automatic scale
    /// `4b`: `bias = β^(−log2(s / (α₁/2)))`, so `α₁` gets `1/β` (Offringa &
    /// Smirnov 2017, eq. 3). Without a non-zero scale: as `Theoretic`.
    FirstScale,
    /// `b` given in pixels (for example the fitted PSF FWHM).
    Pixels(f64),
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
    /// What the scale bias is referenced to (GeMClean's; default radler's).
    pub bias_reference: BiasReference,
    /// `-multiscale-point-cap c`: every non-zero scale's bias is at most
    /// `c / psf_peak(s)`, so that a bare point is selected at scale 0 when
    /// `c < 1` (GeMClean's; default none).
    pub point_cap: Option<f64>,
    /// `false` with `-no-negative`: radler's `allow_negative_components =
    /// false` (signed peaks, positions at or above the threshold, the signed
    /// sub-minor maximum).
    pub allow_negative: bool,
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
            bias_reference: BiasReference::Theoretic,
            point_cap: None,
            allow_negative: true,
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

/// The bias factor of every scale in `values` (sorted, as [`scale_list`]
/// gives them) with `psf_peaks` their integrated PSF peaks: radler's
/// [`bias_factor`] on the beam [`BiasReference`] chooses, then the point cap.
/// The defaults give radler's factors exactly.
pub fn scale_biases(
    values: &[f64],
    beam: f64,
    psf_peaks: &[f64],
    settings: &MultiscaleSettings,
) -> Vec<f64> {
    let reference = match settings.bias_reference {
        BiasReference::Theoretic => beam,
        BiasReference::FirstScale => values
            .iter()
            .copied()
            .find(|&v| v > 0.0)
            .map_or(beam, |a1| a1 / 4.0),
        BiasReference::Pixels(p) => p,
    };
    values
        .iter()
        .zip(psf_peaks)
        .map(|(&v, &peak)| {
            let b = bias_factor(v, reference, values.len(), settings.scale_bias);
            match settings.point_cap {
                Some(c) if v != 0.0 && values.len() > 1 => b.min(c / peak),
                _ => b,
            }
        })
        .collect()
}

/// WSClean's theoretic beam in radians, `1 / max |uvw|/λ` (`MsGridder::
/// CalculateOverallMetaData`, `CalculateMsLimits`): over the visibilities with
/// nonzero imaging weight whose `(u, v)` falls inside the `n × n`-pixel grid.
/// WSClean 3.5-3.7 tested `u` on both axes (#208); this follows the fix in
/// !1068 (commit ca23d835, squashed into master as 53e25d59; not yet
/// released), `y = v * pixel_size_y * image_height`, so it differs from 3.7
/// only when the grid cuts `v` differently from `u`. `uvw` in metres, row-major
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
                let y = v / wavelength * pixel * n as f64;
                if x.floor() > -half && x.ceil() < half && y.floor() > -half && y.ceil() < half {
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
    /// Scales dropped because the PSF convolved with them has no positive
    /// peak (issue #54): (scale in pixels, that peak).
    pub dropped: Vec<(f64, f64)>,
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
fn peak(x: &[f64], n: usize, border: usize, negative: bool) -> Option<(f64, usize)> {
    if 2 * border >= n {
        return None;
    }
    let (lo, hi) = (border, n - border);
    let (_, p) = (lo..hi)
        .into_par_iter()
        .map(|row| {
            let mut best = (f64::NEG_INFINITY, usize::MAX);
            for col in lo..hi {
                let v = if negative {
                    x[row * n + col].abs()
                } else {
                    x[row * n + col]
                };
                if v > best.0 {
                    best = (v, row * n + col);
                }
            }
            best
        })
        .reduce(
            || (f64::NEG_INFINITY, usize::MAX),
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
fn peak_masked(
    x: &[f64],
    n: usize,
    border: usize,
    mask: &[bool],
    negative: bool,
) -> Option<(f64, usize)> {
    if 2 * border >= n {
        return None;
    }
    let (lo, hi) = (border, n - border);
    let mut best = (f64::NEG_INFINITY, usize::MAX);
    for row in lo..hi {
        for col in lo..hi {
            let p = row * n + col;
            let v = if negative { x[p].abs() } else { x[p] };
            if mask[p] && v > best.0 {
                best = (v, p);
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
    /// radler's `allow_negative_components` (`-no-negative`: false).
    negative: bool,
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
                None => peak(&conv, n, border, self.negative),
                Some(m) => peak_masked(&conv, n, border, m, self.negative),
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
/// `GetMaxComponent` order (`argmax Σ a_k v_k[i]` without negative
/// components); the signed integrated value.
fn sub_max(values: &[Vec<f64>], a: &[f64], scratch: &mut [f64], negative: bool) -> (usize, f64) {
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
        let v = if negative { v.abs() } else { v };
        if v > max {
            best = i;
            max = v;
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
    if ms.point_cap.is_some_and(|c| !(c > 0.0 && c.is_finite())) {
        return Err("-multiscale-point-cap must be positive".into());
    }
    if let BiasReference::Pixels(p) = ms.bias_reference
        && !(p > 0.0 && p.is_finite())
    {
        return Err("-multiscale-bias-reference must be positive pixels".into());
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
            bias: 1.0,
            psf_peak: 0.0,
            gain: 0.0,
            active: true,
            value: 0.0,
            pixel: 0,
            components: 0,
            flux: 0.0,
        });
    }
    // radler's `Transform` is circular on the n × n PSF: the shape summed
    // with the PSF wrapped around its edges, at the centre. Post hoc
    // (research/g5-multiscale.md): the linear sum missed radler's by 3e-4
    // at the 922-pixel scale of S2. Issue #54 (research/gemclean-54.md): a
    // scale whose convolved PSF has no positive peak (the largest automatic
    // scale on sparse coverage, about n / 2.5 pixels) is dropped with a
    // warning; radler keeps it with gain `g / peak`. Scale 0, or no scale
    // left, is still an error. A run that drops nothing is unchanged.
    let mut dropped = Vec::new();
    let mut kept_values = Vec::with_capacity(values.len());
    let mut kept = Vec::with_capacity(scales.len());
    for (mut sc, &v) in scales.into_iter().zip(&values) {
        let psf_peak = circular_peak(&psf_int, n, &sc.kernel, sc.kernel_side);
        if psf_peak > 0.0 && psf_peak.is_finite() {
            sc.psf_peak = psf_peak;
            kept.push(sc);
            kept_values.push(v);
        } else if v == 0.0 {
            return Err(format!(
                "the PSF convolved with scale {v} has no positive peak"
            ));
        } else {
            dropped.push((v, psf_peak));
        }
    }
    if kept.is_empty() {
        return Err("no multiscale scale has a PSF with a positive peak".into());
    }
    let scales = kept;
    let values = kept_values;
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
        negative: ms.allow_negative,
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
    for sc in run.scales.iter_mut() {
        sc.gain = s.gain / sc.psf_peak;
    }
    let peaks: Vec<f64> = run.scales.iter().map(|sc| sc.psf_peak).collect();
    for (sc, b) in run
        .scales
        .iter_mut()
        .zip(scale_biases(&values, beam, &peaks, ms))
    {
        sc.bias = b;
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
                        let v = if run.negative { v.abs() } else { v };
                        if v >= thr && run.mask_of(sel).is_none_or(|m| m[p]) {
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
                let (mut mc, mut maxv) = sub_max(&vals, &a, &mut scratch, run.negative);
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
                    (mc, maxv) = sub_max(&vals, &a, &mut scratch, run.negative);
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
        super::progress(cycles.len(), first_peak, threshold, steps.len(), start);
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
            // Multiscale keeps one mask per scale (task G4).
            auto_mask: None,
        },
        beam_pixels: beam,
        scales,
        end,
        sub_minor_loops,
        convolutions: run.convolutions,
        convolvers_built: run.convolvers.built,
        twice_built: run.twice.built,
        dropped,
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
        // Issue #23 step 4's options, only when set (the default report is unchanged).
        let mut extra: Vec<(&str, String)> = Vec::new();
        match settings.bias_reference {
            BiasReference::Theoretic => {}
            BiasReference::FirstScale => extra.push(("bias_reference", text("first-scale"))),
            BiasReference::Pixels(p) => extra.push(("bias_reference_pixels", num(p))),
        }
        if let Some(c) = settings.point_cap {
            extra.push(("point_cap", num(c)));
        }
        if !settings.allow_negative {
            extra.push(("allow_negative", "false".to_string()));
        }
        // Issue #54, only when a scale was dropped (the default report is unchanged).
        if !self.dropped.is_empty() {
            let d: Vec<String> = self
                .dropped
                .iter()
                .map(|&(v, p)| obj(&[("scale_pixels", num(v)), ("psf_peak", num(p))]))
                .collect();
            extra.push(("dropped_scales", arr(&d)));
        }
        let mut fields = vec![
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
        ];
        fields.extend(extra);
        obj(&fields)
    }

    /// WSClean's scale lines (`ConvolvePsfs`) and summary.
    pub fn print_scales(&self) {
        for &(v, p) in &self.dropped {
            println!(
                "warning: multiscale scale {v} px dropped: the PSF convolved with it has no positive peak ({p:e})"
            );
        }
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

    /// Issue #23 step 4 (research/multiscale-flux-fix.md, section 3): the
    /// bias references and the point cap on DF5-O's numbers.
    #[test]
    fn bias_references_and_the_point_cap() {
        let values = [0.0, 24.0, 48.0, 96.0, 192.0];
        let peaks = [1.0, 0.5026, 0.326273, 0.157188, 0.0511696];
        let beam = 2.47;
        let def = MultiscaleSettings::default();
        // The default is radler's bias, unchanged.
        let b = scale_biases(&values, beam, &peaks, &def);
        for (&v, &bv) in values.iter().zip(&b) {
            assert_eq!(bv, bias_factor(v, beam, values.len(), 0.6));
        }
        // The first scale as radler's 4b: 1, 1/β, 1/β², ...
        let first = MultiscaleSettings {
            bias_reference: BiasReference::FirstScale,
            ..def.clone()
        };
        let b = scale_biases(&values, beam, &peaks, &first);
        for (k, &bv) in b.iter().enumerate() {
            assert!((bv - 0.6_f64.powi(-(k as i32))).abs() < 1e-12, "{k} {bv}");
        }
        // Without a non-zero scale the first-scale reference is the beam.
        assert_eq!(scale_biases(&[0.0], beam, &[1.0], &first), vec![1.0]);
        let pixels = MultiscaleSettings {
            bias_reference: BiasReference::Pixels(11.58),
            ..def.clone()
        };
        let b = scale_biases(&values, beam, &peaks, &pixels);
        assert!((b[1] - 0.6_f64.powf(-(24.0_f64 / 23.16).log2())).abs() < 1e-12);
        // The cap: min(radler's, c / psf_peak), never on scale 0.
        let cap = MultiscaleSettings {
            point_cap: Some(0.9),
            ..def.clone()
        };
        let b = scale_biases(&values, beam, &peaks, &cap);
        assert_eq!(b[0], 1.0);
        assert!((b[1] - 0.9 / 0.5026).abs() < 1e-12);
        assert!((b[3] - 0.9 / 0.157188).abs() < 1e-12);
        assert_eq!(b[4], bias_factor(192.0, beam, 5, 0.6));
        for (bv, p) in b.iter().zip(&peaks).skip(1) {
            assert!(bv * p <= 0.9 + 1e-12);
        }
    }

    /// A lone point: radler's bias on a narrow theoretic beam takes it at the
    /// larger scales first; with the point cap every component is at scale 0;
    /// both recover the flux.
    #[test]
    fn the_point_cap_cleans_a_point_at_scale_zero() {
        let n = 64;
        let mut sky = vec![0.0; n * n];
        sky[30 * n + 33] = 1.0;
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
            threshold: 1e-3,
            max_components: 20_000,
            cycle_stop: CycleStop::PeakFraction(0.8),
            ..Settings::default()
        };
        let ms = MultiscaleSettings {
            scales: vec![0.0, 4.0, 8.0],
            ..MultiscaleSettings::default()
        };
        let run = |ms: &MultiscaleSettings| {
            run_multiscale(&[(&m, &beam, &psf[..])], &[1.0], None, &settings, ms, 0.1).unwrap()
        };
        let plain = run(&ms);
        let capped = run(&MultiscaleSettings {
            point_cap: Some(0.9),
            ..ms.clone()
        });
        let products: Vec<f64> = plain.scales.iter().map(|s| s.bias * s.psf_peak).collect();
        assert!(products[1] > 1.0, "{products:?}");
        assert!(plain.scales.iter().skip(1).any(|s| s.components > 0));
        let why = format!("{:?}", capped.scales);
        assert!(
            capped.scales.iter().skip(1).all(|s| s.components == 0),
            "{why}"
        );
        for out in [&plain, &capped] {
            let total: f64 = out.joined.model[0].iter().sum();
            assert!((total - 1.0).abs() < 0.01, "{total}");
        }
    }

    /// Issue #54: a scale whose PSF-convolved peak is not positive (here the
    /// PSF lowered by a constant, as sparse coverage without short spacings
    /// does at the largest automatic scale) is dropped with a warning; the run
    /// cleans on the others and reports the dropped scale.
    #[test]
    fn a_scale_without_a_positive_psf_peak_is_dropped() {
        let n = 64;
        let mut sky = vec![0.0; n * n];
        sky[30 * n + 33] = 1.0;
        let m = measurement(n, &sky);
        let psf2n = m.psf_image(2 * n).unwrap();
        let beam = Beam::from_double(n, &psf2n, 16).unwrap();
        let mut psf = vec![0.0; n * n];
        for i in 0..n {
            for j in 0..n {
                psf[i * n + j] = psf2n[(i + n / 2) * 2 * n + j + n / 2] - 0.02;
            }
        }
        let shape = MultiscaleSettings::default().shape;
        let peak = |v: f64| {
            let (side, kernel) = shape_function(v, n, shape);
            circular_peak(&psf, n, &kernel, side)
        };
        assert!(
            peak(4.0) > 0.0 && peak(24.0) <= 0.0,
            "{} {}",
            peak(4.0),
            peak(24.0)
        );
        let settings = Settings {
            threshold: 1e-3,
            max_components: 2_000,
            cycle_stop: CycleStop::PeakFraction(0.8),
            ..Settings::default()
        };
        let ms = MultiscaleSettings {
            scales: vec![0.0, 4.0, 24.0],
            ..MultiscaleSettings::default()
        };
        let out =
            run_multiscale(&[(&m, &beam, &psf[..])], &[1.0], None, &settings, &ms, 0.1).unwrap();
        let kept: Vec<f64> = out.scales.iter().map(|s| s.scale).collect();
        assert_eq!(kept, vec![0.0, 4.0]);
        assert_eq!(out.dropped.len(), 1);
        assert_eq!(out.dropped[0].0, 24.0);
        assert!(out.dropped[0].1 <= 0.0);
        assert!(out.scales.iter().map(|s| s.components).sum::<usize>() > 0);
        let json = out.to_json(&ms, None);
        assert!(json.contains("\"dropped_scales\""), "{json}");
        // Scale 0 with no positive peak is still an error.
        let flat = vec![-1.0; n * n];
        let err = run_multiscale(&[(&m, &beam, &flat[..])], &[1.0], None, &settings, &ms, 0.1)
            .unwrap_err();
        assert!(err.contains("scale 0 has no positive peak"), "{err}");
    }

    /// `-no-negative`: every component, and so the model, is non-negative.
    #[test]
    fn no_negative_components() {
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
            allow_negative: false,
            ..MultiscaleSettings::default()
        };
        let out =
            run_multiscale(&[(&m, &beam, &psf[..])], &[1.0], None, &settings, &ms, 1.0).unwrap();
        let model = &out.joined.model[0];
        let low = model.iter().copied().fold(f64::INFINITY, f64::min);
        assert!(low >= -1e-12, "{low}");
        assert!(out.joined.integrated.steps.iter().all(|s| s.peak > 0.0));
        let sum: f64 = model.iter().sum();
        assert!((sum - 1.5).abs() < 0.05, "{sum}");
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

    #[test]
    fn theoretic_beam_tests_v_on_the_second_axis() {
        // WSClean #208, fixed by !1068 (ca23d835, master 53e25d59): the y bound is v, not u.
        // Asymmetric coverage, max |u| = 500 m, max |v| = 9000 m. Row 1 has a
        // small u and a v outside the grid: v/λ at 1 GHz = 30,021, y = 30,021 ·
        // 2e-5 · 1024 = 615 > 512. The u-for-both rule kept it (9000 m baseline).
        let freq = [1.0e9];
        let uvw = [500.0, 0.0, 0.0, 10.0, 9000.0, 0.0];
        let w = [1.0, 1.0];
        let lambda = 299_792_458.0 / 1e9;
        let got = theoretic_beam(&uvw, &freq, &w, 1024, 2e-5).unwrap();
        let want = 1.0 / (500.0 / lambda);
        assert!((got - want).abs() < 1e-15 * want, "{got} {want}");
        // The same rows transposed (u outside, v small) were excluded before too.
        let uvw = [0.0, 500.0, 0.0, 9000.0, 10.0, 0.0];
        let got = theoretic_beam(&uvw, &freq, &w, 1024, 2e-5).unwrap();
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

    /// Issue #35 (`research/gemclean-ms-mask.md` section 6): extended emission
    /// inside a FITS mask and outside it. At every scale the component centres
    /// stay inside the mask, single and joined channels, with and without the
    /// automatic mask. The model reaches outside the mask only within the
    /// largest used shape's half-side (radler's behaviour: the shapes are not
    /// clipped), and the blob outside stays in the residual.
    #[test]
    fn a_fits_mask_confines_the_centres_at_every_scale() {
        use crate::gemclean::mask::{AutoMask, Masking};
        let n = 96;
        let mut sky = vec![0.0; n * n];
        let mut blob = |cx: f64, cy: f64, sigma: f64, flux: f64| {
            let mut w = vec![0.0; n * n];
            for y in 0..n {
                for x in 0..n {
                    let r2 = (x as f64 - cx).powi(2) + (y as f64 - cy).powi(2);
                    w[y * n + x] = (-0.5 * r2 / (sigma * sigma)).exp();
                }
            }
            let s: f64 = w.iter().sum();
            for (v, wi) in sky.iter_mut().zip(&w) {
                *v += flux * wi / s;
            }
        };
        blob(26.0, 30.0, 1.5, 0.5);
        blob(34.0, 38.0, 5.0, 1.0);
        blob(66.0, 62.0, 5.0, 1.0);
        sky[28 * n + 38] += 0.3;
        let m = measurement(n, &sky);
        let (dirty, _) = m.residual(&vec![0.0; n * n]).unwrap();
        let psf2n = m.psf_image(2 * n).unwrap();
        let beam = Beam::from_double(n, &psf2n, 16).unwrap();
        let mut psf = vec![0.0; n * n];
        for i in 0..n {
            for j in 0..n {
                psf[i * n + j] = psf2n[(i + n / 2) * 2 * n + j + n / 2];
            }
        }
        // A box around the first two blobs and the point only.
        let (x0, x1, y0, y1) = (18isize, 45isize, 21isize, 48isize);
        let mut fits = vec![false; n * n];
        for y in y0..y1 {
            for x in x0..x1 {
                fits[y as usize * n + x as usize] = true;
            }
        }
        let settings = Settings {
            threshold: 2e-3,
            max_components: 20_000,
            cycle_stop: CycleStop::PeakFraction(0.8),
            ..Settings::default()
        };
        let ms = MultiscaleSettings {
            scales: vec![0.0, 4.0, 8.0, 16.0],
            ..MultiscaleSettings::default()
        };
        let auto = AutoMask {
            sigma: None,
            absolute: Some(0.02),
            nmiter: 2,
        };
        let channels = [(&m, &beam, &psf[..]), (&m, &beam, &psf[..])];
        for (k, auto) in [(1, None), (2, None), (1, Some(auto)), (2, Some(auto))] {
            let masking = Masking {
                fits: Some(fits.clone()),
                auto,
            };
            let out = run_multiscale_masked(
                &channels[..k],
                &vec![1.0; k],
                None,
                &settings,
                &ms,
                1.0,
                Some(&masking),
            )
            .unwrap();
            let case = format!("{k} channel(s), auto mask {}", auto.is_some());
            let steps = &out.joined.integrated.steps;
            assert!(!steps.is_empty(), "{case}");
            let outside = steps.iter().filter(|st| !fits[st.pixel]).count();
            assert_eq!(outside, 0, "{case}: centres outside the mask");
            let used: Vec<&ScaleReport> = out
                .scales
                .iter()
                .filter(|s| s.scale > 0.0 && s.components > 0)
                .collect();
            assert!(used.len() >= 2, "{case}: {:?}", out.scales);
            // The model outside the mask lies within the largest used shape's
            // half-side of the box (FFT round-off aside).
            let reach = used.iter().map(|s| s.kernel_side / 2).max().unwrap() as isize;
            let model = &out.joined.integrated.model;
            let peak = model.iter().fold(0.0_f64, |a, v| a.max(v.abs()));
            for y in 0..n as isize {
                for x in 0..n as isize {
                    let p = y as usize * n + x as usize;
                    if model[p].abs() <= 1e-9 * peak || fits[p] {
                        continue;
                    }
                    let near = (x0 - reach..x1 + reach).contains(&x)
                        && (y0 - reach..y1 + reach).contains(&y);
                    assert!(near, "{case}: model {} at ({x}, {y})", model[p]);
                }
            }
            for r in &out.joined.residual {
                assert!(r[62 * n + 66] > 0.5 * dirty[62 * n + 66], "{case}");
            }
        }
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
