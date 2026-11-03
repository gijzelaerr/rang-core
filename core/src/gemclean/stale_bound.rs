//! A sampled upper bound on the error of the phase-centre beam, for the
//! certified minor-cycle stop rule (`research/stop-rule-theorem.md`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The true Gram matrix and the beam of the `2n` PSF differ only through the
//! w-term. With `ñ(x) = √(1 − |x|²) − 1`, `Δ = x_q − x_j` and
//! `η(q, j) = ñ(x_q) − ñ(x_j) − ñ(Δ)`,
//!
//! `E(q, j) = G(q, j) − b(Δ) = Φ(Δ, η(q, j))`,
//! `Φ(Δ, η) = Σ_k W_k [cos(φ_k(Δ) + 2π w_k η) − cos φ_k(Δ)]`,
//!
//! `φ_k(Δ) = 2π (u_k·Δ + w_k ñ(Δ))`. So `E` is a function of three variables,
//! and for one `η` the map `Δ ↦ Φ(Δ, η)` is one PSF-sized gridder call with
//! the visibilities `exp(2πi w_k η)`. The range of `η` follows from the
//! component's radius: `|η(q, j)| ≤ |x_j| |Δ| (1 + ζ)` (the note, §3, on paper).
//!
//! The table [`StaleBound::f`] holds `sup |Φ|` over the admissible `(Δ, η)` per
//! radius of the component. Below a small range the supremum in `η` comes from the
//! proved moment bound `|Φ(Δ, η)| ≤ 2π|η| |S(Δ)| + 2π²η² M₂` (`StopRule.lean`, with
//! `S(Δ) = Σ_k W_k w_k sin φ_k(Δ)`). Above it there are two forms.
//!
//! * **Chebyshev nodes** (`uniform = 0`, the default of the rule). On `|η| ≤ H_i`,
//!   `Φ(Δ, H_i t)` is a polynomial in `t` of degree `D` up to the Jacobi-Anger tail
//!   `ε = 2 Σ_{k>D} a^k / (2^k k!)`, `a = 2π w_max H_i`, for every `Δ` at once, and
//!   a polynomial is bounded by its values on the nodes `cos(jπ/N)` over
//!   `cos(πD/(2N))` (Ehlich and Zeller 1964). So the supremum is bounded, on
//!   paper, by `(max_j |Φ_j| + ε) / cos(πD/(2N)) + ε`, up to the gridder's accuracy.
//! * **Uniform samples** (`uniform > 0`). Cheaper, with the outer bracket of the
//!   samples. A sampled supremum is a measured value, not a bound:
//!   [`Sampling::gap_bound`] reports what a rigorous remainder would add.

use super::kernels::{self, Level};
use super::{Beam, Convolver, Since};
use crate::clean_certified::Complex;
use crate::wgridder::{C_LIGHT, Options, Prepared, VisData, Weights};
use rayon::prelude::*;
use std::f64::consts::PI;

/// The moments of `|w|` under the normalised weights (wavelengths).
#[derive(Clone, Copy, Debug, Default)]
pub struct WMoments {
    /// `Σ W_k |w_k|`.
    pub m1: f64,
    /// `Σ W_k w_k²`.
    pub m2: f64,
    /// The largest `|w_k|` of nonzero weight.
    pub max: f64,
    /// `Σ W_k`.
    pub sum: f64,
}

/// The moments of `w`; `wgt` is `nrow × nchan`, `uvw` `nrow × 3`.
pub fn w_moments(uvw: &[f64], freq: &[f64], wgt: &[f64]) -> WMoments {
    let nchan = freq.len();
    let mut out = WMoments::default();
    for (row, w_row) in uvw.chunks_exact(3).map(|r| r[2]).enumerate() {
        for (chan, f) in freq.iter().enumerate() {
            let weight = wgt[row * nchan + chan];
            if weight != 0.0 {
                let w = (w_row * f / C_LIGHT).abs();
                out.m1 += weight * w;
                out.m2 += weight * w * w;
                out.max = out.max.max(w);
                out.sum += weight;
            }
        }
    }
    out
}

/// `ζ` of `|η(q, j)| ≤ |x_j| |Δ| (1 + ζ)` on a square field of half-diagonal
/// `r_max`: `|x_j| ≤ r_max`, `|Δ| ≤ 2 r_max`, so `|x_j|² + |Δ|² ≤ 5 r_max²`
/// bounds every argument of `g(s) = 1 − √(1 − s)` in the proof (the note, §3).
pub fn eta_margin(r_max: f64) -> f64 {
    let s = 5.0 * r_max * r_max;
    let first = 1.0 / (1.0 - s).sqrt();
    let second = r_max * 2.0 * r_max / (4.0 * (1.0 - s).powf(1.5));
    first + second - 1.0
}

/// The sampling of `η`.
#[derive(Clone, Debug)]
pub struct Sampling {
    /// Uniform samples on `[−H, H]`, spacing `2H / uniform`.
    pub uniform: usize,
    /// The largest admissible `|η|`.
    pub h: f64,
    /// The first sample: below it the moment bound applies.
    pub h0: f64,
    /// All positive magnitudes in increasing order, each with the magnitude
    /// before it, from which it is the outer bracket of the range.
    pub magnitudes: Vec<(f64, f64)>,
    /// The Chebyshev levels (empty for uniform samples), widest first.
    pub levels: Vec<ChebyshevLevel>,
}

/// One range of `η` on Chebyshev nodes.
#[derive(Clone, Copy, Debug)]
pub struct ChebyshevLevel {
    /// The range `|η| ≤ range`, for offsets whose range exceeds `lower`.
    pub range: f64,
    pub lower: f64,
    /// The degree `D` of the polynomial and the nodes `cos(jπ/N)`, `j = 0..=N`.
    pub degree: usize,
    pub nodes: usize,
    /// The Jacobi-Anger tail `ε`.
    pub tail: f64,
    /// `1 / cos(πD/(2N))`.
    pub factor: f64,
}

/// `2 Σ_{k>D} (a/2)^k / k!`, which bounds the Chebyshev tail of `exp(i a t)` on
/// `|t| ≤ 1`, as `|J_k(a)| ≤ (a/2)^k / k!`.
pub fn jacobi_anger_tail(a: f64, degree: usize) -> f64 {
    let mut term = 1.0;
    for k in 1..=degree + 1 {
        term *= (a / 2.0) / k as f64;
    }
    let (mut sum, mut k) = (0.0, degree + 1);
    while term > 1e-300 && k < degree + 200 {
        sum += term;
        k += 1;
        term *= (a / 2.0) / k as f64;
    }
    2.0 * sum
}

impl Sampling {
    /// `level` is the moment bound's second-order term allowed at `h0`.
    pub fn new(uniform: usize, h: f64, m2: f64, level: f64) -> Sampling {
        let step = 2.0 * h / uniform.max(2) as f64;
        let h0 = (level / (2.0 * PI * PI * m2.max(1e-30)))
            .sqrt()
            .min(step)
            .min(h);
        let mut values = Vec::new();
        let mut g = h0;
        while g < step {
            values.push(g);
            g *= 1.5;
        }
        let mut k = 1;
        while (k as f64) * step <= h * (1.0 + 1e-12) {
            values.push(k as f64 * step);
            k += 1;
        }
        values.sort_by(f64::total_cmp);
        values.dedup_by(|a, b| (*a - *b).abs() < 1e-3 * *b);
        let mut magnitudes = Vec::with_capacity(values.len());
        let mut before = h0;
        for v in values {
            magnitudes.push((v, before));
            before = v;
        }
        Sampling {
            uniform,
            h,
            h0,
            magnitudes,
            levels: Vec::new(),
        }
    }

    /// Chebyshev levels `H, H/4, H/16, ...` down to the range where the moment
    /// bound's second-order term is `level`; `nodes = oversample × degree`.
    pub fn chebyshev(
        h: f64,
        m2: f64,
        w_max: f64,
        level: f64,
        tail: f64,
        oversample: f64,
    ) -> Sampling {
        let h0_target = (level / (2.0 * PI * PI * m2.max(1e-30))).sqrt();
        let mut levels = Vec::new();
        let mut range = h;
        while range > h0_target {
            let a = 2.0 * PI * w_max * range;
            let mut degree = 2;
            while jacobi_anger_tail(a, degree) > tail {
                degree += 1;
            }
            let nodes = ((oversample * degree as f64).ceil() as usize).max(degree + 1);
            levels.push(ChebyshevLevel {
                range,
                lower: range / 4.0,
                degree,
                nodes,
                tail: jacobi_anger_tail(a, degree),
                factor: 1.0 / (PI * degree as f64 / (2.0 * nodes as f64)).cos(),
            });
            range /= 4.0;
        }
        Sampling {
            uniform: 0,
            h,
            h0: range,
            magnitudes: Vec::new(),
            levels,
        }
    }

    /// Gridder calls: both signs of every magnitude and the first moment.
    pub fn calls(&self) -> usize {
        // A level's node at t = 0 needs no call: Φ(Δ, 0) = 0.
        let nodes: usize = self
            .levels
            .iter()
            .map(|l| l.nodes + 1 - (l.nodes % 2 == 0) as usize)
            .sum();
        2 * self.magnitudes.len() + nodes + 1
    }

    /// The rigorous remainder of interpolating linearly between samples:
    /// `h²/8 · (2π)² M₂` at the coarsest spacing. What the sampled supremum
    /// would need to add to be a theorem.
    pub fn gap_bound(&self, m2: f64) -> f64 {
        let spacing = self
            .magnitudes
            .iter()
            .map(|&(v, before)| v - before)
            .fold(self.h0, f64::max);
        spacing * spacing / 8.0 * (2.0 * PI).powi(2) * m2
    }
}

/// The bound on the beam error per radius of the component.
#[derive(Clone, Debug)]
pub struct StaleBound {
    pub n: usize,
    pub cell: f64,
    /// `radii[b]`: the upper edge of the radial bin `b` (radians).
    pub radii: Vec<f64>,
    /// `f[b]`: the sampled `sup |E(q, j)|` over `|x_j| ≤ radii[b]`,
    /// nondecreasing.
    pub f: Vec<f64>,
    /// `sup |E|` per offset over every admissible `η`, on the `2n` grid.
    pub envelope: Vec<f64>,
    pub moments: WMoments,
    pub sampling: Sampling,
    pub seconds: f64,
}

/// Radial bins of the table.
const BINS: usize = 64;

struct Geometry {
    n: isize,
    cell: f64,
    half: f64,
    r_max: f64,
    dr: f64,
    margin: f64,
}

impl Geometry {
    fn new(n: usize, cell: f64) -> Geometry {
        let half = n as f64 * cell / 2.0;
        let r_max = half * std::f64::consts::SQRT_2;
        Geometry {
            n: n as isize,
            cell,
            half,
            r_max,
            dr: r_max / BINS as f64,
            margin: 1.0 + eta_margin(r_max),
        }
    }

    /// The smallest radius a component needs for this offset to stay in the image.
    fn min_radius(&self, dx: isize, dy: isize) -> f64 {
        let reach = dx.abs().max(dy.abs()) as f64 * self.cell;
        (reach - self.half).max(0.0)
    }

    fn bin(&self, radius: f64) -> usize {
        ((radius / self.dr).ceil() as usize)
            .saturating_sub(1)
            .min(BINS - 1)
    }
}

fn merge_tables(table: &mut [f64], local: &[f64]) {
    table
        .iter_mut()
        .zip(local)
        .for_each(|(x, y)| *x = x.max(*y));
}

/// Merge one sample `Φ(·, η)` into the table and the envelope; `before` is the
/// range from which the sample brackets it.
fn merge_sample(
    geometry: &Geometry,
    psf2n: &[f64],
    image: &[f64],
    before: f64,
    table: &mut [f64],
    envelope: &mut [f64],
) {
    let m = 2 * geometry.n as usize;
    let n = geometry.n;
    let local = envelope
        .par_chunks_mut(m)
        .enumerate()
        .map(|(row, env)| {
            let dy = row as isize - n;
            let mut t = vec![0.0_f64; BINS];
            for (col, e) in env.iter_mut().enumerate() {
                let dx = col as isize - n;
                if dx == 0 && dy == 0 {
                    continue;
                }
                let at = row * m + col;
                let value = (image[at] - psf2n[at]).abs();
                let distance = ((dx * dx + dy * dy) as f64).sqrt() * geometry.cell;
                let need = before / (distance * geometry.margin);
                if need <= geometry.r_max {
                    let radius = need.max(geometry.min_radius(dx, dy));
                    let bin = geometry.bin(radius);
                    t[bin] = t[bin].max(value);
                    *e = e.max(value);
                }
            }
            t
        })
        .reduce(
            || vec![0.0_f64; BINS],
            |mut a, b| {
                merge_tables(&mut a, &b);
                a
            },
        );
    merge_tables(table, &local);
}

/// Merge one node of a Chebyshev level: the offsets whose range of `η` falls in
/// this level, with the level's factor and tail.
fn merge_node(
    geometry: &Geometry,
    psf2n: &[f64],
    image: &[f64],
    level: &ChebyshevLevel,
    table: &mut [f64],
    envelope: &mut [f64],
) {
    let m = 2 * geometry.n as usize;
    let n = geometry.n;
    let local = envelope
        .par_chunks_mut(m)
        .enumerate()
        .map(|(row, env)| {
            let dy = row as isize - n;
            let mut t = vec![0.0_f64; BINS];
            for (col, e) in env.iter_mut().enumerate() {
                let dx = col as isize - n;
                if dx == 0 && dy == 0 {
                    continue;
                }
                let at = row * m + col;
                let value =
                    ((image[at] - psf2n[at]).abs() + level.tail) * level.factor + level.tail;
                let scale = ((dx * dx + dy * dy) as f64).sqrt() * geometry.cell * geometry.margin;
                // Radii whose range for this offset falls in the level.
                let low = (level.lower / scale).max(geometry.min_radius(dx, dy));
                let high = level.range / scale;
                if low <= high && low <= geometry.r_max {
                    let bin = geometry.bin(low);
                    t[bin] = t[bin].max(value);
                }
                let full = geometry.r_max * scale;
                if full > level.lower && full <= level.range {
                    *e = e.max(value);
                }
            }
            t
        })
        .reduce(
            || vec![0.0_f64; BINS],
            |mut a, b| {
                merge_tables(&mut a, &b);
                a
            },
        );
    merge_tables(table, &local);
}

/// Merge the moment bound, for the ranges below the first sample.
fn merge_moment(
    geometry: &Geometry,
    first_moment: &[f64],
    h0: f64,
    m2: f64,
    table: &mut [f64],
    envelope: &mut [f64],
) {
    let m = 2 * geometry.n as usize;
    let n = geometry.n;
    let local = envelope
        .par_chunks_mut(m)
        .enumerate()
        .map(|(row, env)| {
            let dy = row as isize - n;
            let mut t = vec![0.0_f64; BINS];
            for (col, e) in env.iter_mut().enumerate() {
                let dx = col as isize - n;
                if dx == 0 && dy == 0 {
                    continue;
                }
                let s = first_moment[row * m + col].abs();
                let distance = ((dx * dx + dy * dy) as f64).sqrt() * geometry.cell;
                let bound = |range: f64| 2.0 * PI * range * s + 2.0 * PI * PI * range * range * m2;
                let reach = geometry.min_radius(dx, dy);
                for (b, slot) in t.iter_mut().enumerate() {
                    let radius = (b + 1) as f64 * geometry.dr;
                    if radius < reach {
                        continue;
                    }
                    let range = radius * distance * geometry.margin;
                    *slot = slot.max(bound(range.min(h0)));
                    if range >= h0 {
                        break;
                    }
                }
                let full = geometry.r_max * distance * geometry.margin;
                *e = e.max(bound(full.min(h0)));
            }
            t
        })
        .reduce(
            || vec![0.0_f64; BINS],
            |mut a, b| {
                merge_tables(&mut a, &b);
                a
            },
        );
    merge_tables(table, &local);
}

impl StaleBound {
    /// Build the table with `uniform` uniform samples of `η`, or on Chebyshev
    /// nodes for `uniform = 0`; `wgt` normalised, `psf2n` the PSF of the beam on
    /// the `2n` grid, `opts` the imager's.
    #[allow(clippy::too_many_arguments)]
    pub fn compute(
        n: usize,
        cell: f64,
        opts: &Options,
        uvw: &[f64],
        freq: &[f64],
        wgt: &[f64],
        psf2n: &[f64],
        epsilon: f64,
        uniform: usize,
    ) -> Result<StaleBound, String> {
        let start = std::time::Instant::now();
        let half_diagonal = n as f64 * cell * std::f64::consts::FRAC_1_SQRT_2;
        if 5.0 * half_diagonal * half_diagonal >= 0.5 {
            return Err("the stop bound assumes a field below 18 degrees in radius".into());
        }
        let m = 2 * n;
        let moments = w_moments(uvw, freq, wgt);
        let geometry = Geometry::new(n, cell);
        // |x_j| ≤ half-diagonal, |Δ| ≤ twice that: the largest |η|.
        let h = geometry.r_max * 2.0 * geometry.r_max * geometry.margin;
        let sampling = if uniform == 0 {
            Sampling::chebyshev(h, moments.m2, moments.max, 1e-5, 1e-6, 2.0)
        } else {
            Sampling::new(uniform, h, moments.m2, 1e-5)
        };
        let double = Options {
            nx: m,
            ny: m,
            pixsize_x: cell,
            pixsize_y: cell,
            epsilon,
            ..*opts
        };
        let prepared = Prepared::<f64>::new(&double, uvw, freq, Weights::F64(wgt))?;
        let nchan = freq.len();
        let mut vis = vec![Complex::new(0.0, 0.0); wgt.len()];
        let mut image = vec![0.0; m * m];
        let mut table = vec![0.0_f64; BINS];
        let mut envelope = vec![0.0_f64; m * m];
        // The first moment: the visibilities i w_k.
        vis.par_chunks_mut(nchan)
            .zip(uvw.par_chunks_exact(3))
            .for_each(|(row, r)| {
                for (v, f) in row.iter_mut().zip(freq) {
                    *v = Complex::new(0.0, r[2] * f / C_LIGHT);
                }
            });
        prepared.vis2dirty(VisData::C128(&vis), Weights::F64(wgt), &mut image)?;
        merge_moment(
            &geometry,
            &image,
            sampling.h0,
            moments.m2,
            &mut table,
            &mut envelope,
        );
        for &(magnitude, before) in &sampling.magnitudes {
            for sign in [1.0, -1.0] {
                let eta = sign * magnitude;
                vis.par_chunks_mut(nchan)
                    .zip(uvw.par_chunks_exact(3))
                    .for_each(|(row, r)| {
                        for (v, f) in row.iter_mut().zip(freq) {
                            let phase = 2.0 * PI * r[2] * f / C_LIGHT * eta;
                            *v = Complex::new(phase.cos(), phase.sin());
                        }
                    });
                prepared.vis2dirty(VisData::C128(&vis), Weights::F64(wgt), &mut image)?;
                merge_sample(&geometry, psf2n, &image, before, &mut table, &mut envelope);
            }
        }
        for level in &sampling.levels {
            for j in 0..=level.nodes {
                if 2 * j == level.nodes {
                    continue;
                }
                let t = (PI * j as f64 / level.nodes as f64).cos();
                let eta = level.range * t;
                vis.par_chunks_mut(nchan)
                    .zip(uvw.par_chunks_exact(3))
                    .for_each(|(row, r)| {
                        for (v, f) in row.iter_mut().zip(freq) {
                            let phase = 2.0 * PI * r[2] * f / C_LIGHT * eta;
                            *v = Complex::new(phase.cos(), phase.sin());
                        }
                    });
                prepared.vis2dirty(VisData::C128(&vis), Weights::F64(wgt), &mut image)?;
                merge_node(&geometry, psf2n, &image, level, &mut table, &mut envelope);
            }
        }
        // The images come from a gridder of relative accuracy `epsilon`, against a
        // Gram matrix of unit diagonal: allow it twice, for the column and the beam.
        let accuracy = 2.0 * epsilon;
        envelope.par_iter_mut().for_each(|e| *e += accuracy);
        let mut f = table;
        f[0] += accuracy;
        for b in 1..BINS {
            f[b] = (f[b] + accuracy).max(f[b - 1]);
        }
        Ok(StaleBound {
            n,
            cell,
            radii: (0..BINS).map(|b| (b + 1) as f64 * geometry.dr).collect(),
            f,
            envelope,
            moments,
            sampling,
            seconds: start.elapsed().as_secs_f64(),
        })
    }

    /// The largest `|E|`.
    pub fn delta(&self) -> f64 {
        self.f.last().copied().unwrap_or(0.0)
    }

    /// `f` for a component at pixel `p` of the `n × n` image (row-major), from
    /// the next bin up.
    pub fn at_pixel(&self, p: usize) -> f64 {
        let n = self.n as isize;
        let (x, y) = ((p % self.n) as isize - n / 2, (p / self.n) as isize - n / 2);
        let radius = ((x * x + y * y) as f64).sqrt() * self.cell;
        let bin = ((radius / self.radii[0]).ceil() as usize)
            .saturating_sub(1)
            .min(self.f.len() - 1);
        self.f[bin]
    }
}

/// Which bound the certified rule evaluates at the pick.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BoundKind {
    /// `Σ_j |c_j| g(p − j)`: the error by offset.
    Envelope,
    /// `Σ_j |c_j| f(|x_j|)`: one number per component, whatever the target.
    Radial,
}

/// A [`StaleBound`] prepared for the minor cycle.
pub struct StopBound {
    pub kind: BoundKind,
    n: usize,
    /// `f` per pixel of the image.
    radial: Vec<f64>,
    /// The envelope in the layout of the beam's exterior.
    gather: Vec<f64>,
    /// `g` on the `2n` grid, by FFT.
    convolver: Convolver,
}

impl StopBound {
    pub fn new(bound: &StaleBound, kind: BoundKind) -> Result<StopBound, String> {
        let n = bound.n;
        let (w, m) = (2 * n - 1, 2 * n);
        let mut gather = vec![0.0; w * w];
        gather.par_chunks_mut(w).enumerate().for_each(|(row, out)| {
            for (col, v) in out.iter_mut().enumerate() {
                *v = bound.envelope[(row + 1) * m + col + 1];
            }
        });
        Ok(StopBound {
            kind,
            n,
            radial: (0..n * n)
                .into_par_iter()
                .map(|p| bound.at_pixel(p))
                .collect(),
            gather,
            convolver: Convolver::new(n, &bound.envelope)?,
        })
    }

    /// The bound per pixel for the model change `model − base`.
    pub(super) fn map_of(&self, model: &[f64], base: &[f64]) -> Vec<f64> {
        let change: Vec<f64> = model
            .par_iter()
            .zip(base)
            .map(|(a, b)| (a - b).abs())
            .collect();
        match self.kind {
            BoundKind::Envelope => self.convolver.apply(&change),
            BoundKind::Radial => {
                let sum: f64 = change
                    .par_iter()
                    .zip(&self.radial)
                    .map(|(c, f)| c * f)
                    .sum();
                vec![sum; self.n * self.n]
            }
        }
    }

    /// The bound at pixel `p`: the map as of the last resync (empty before the
    /// first), plus the components since. The error is linear in the
    /// components, so the two parts add.
    pub(super) fn at_pick(
        &self,
        level: Level,
        beam: &Beam,
        p: usize,
        map: &[f64],
        since: &Since,
    ) -> f64 {
        let held = map.get(p).copied().unwrap_or(0.0);
        match self.kind {
            BoundKind::Envelope => {
                held + kernels::gather_sum(
                    level,
                    &self.gather,
                    beam.base(p),
                    &since.keys,
                    &since.abs_flux,
                )
            }
            BoundKind::Radial => {
                held + since
                    .index
                    .iter()
                    .map(|(&j, &at)| self.radial[j] * since.abs_flux[at])
                    .sum::<f64>()
            }
        }
    }
}
