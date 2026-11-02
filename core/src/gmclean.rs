//! gmclean: a reference CLEAN whose every minor step is a certified descent
//! step on the image-domain Gram model, with lazy exact corrections.
//! Research note: `research/gmclean.md`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The certified driver of [`crate::clean_certified`] bounds the error of a
//! truncated minor-cycle beam by the worst case `f Σ|c_j|` (Theorem 6 of
//! `research/clean-theory.md`) and therefore hands back to the major cycle
//! after one to four components. gmclean computes the error exactly at the
//! one pixel it is about to clean instead:
//!
//! 1. **Exact beam.** The PSF on the `2n × 2n` grid holds `b(Δ)` for every
//!    offset two image pixels can have, so subtracting it is the exact Gram
//!    matrix `B` of the gridded measurement without the w-term (the beam is
//!    the one at the phase centre). Its FFT is cached in a [`Convolver`].
//! 2. **Lazy exact Högbom minor cycle.** A working map `r̃` is updated with
//!    the beam within `±P` pixels only. The candidate is `p = argmax |r̃|`;
//!    its exact value is
//!    `r_p = r̃_p − Σ_{j: ‖x_p − x_j‖_∞ > P} c_j b(x_p − x_j)`
//!    over the components since the working map was last exact (one beam
//!    lookup per component, a gather). The component is `c = γ r_p / b(0)`,
//!    so the misfit falls by exactly `γ(2−γ)/2 · r_p² / b(0)` (Theorem 1,
//!    `Clean.misfit_step`). With `e = f b(0) Σ|c_j|` bounding the stale error
//!    anywhere in the map, the pick is `τ_k`-weak greedy with
//!    `τ_k = |r_p| / (max|r̃| + e)`. When the drift `|r_p − r̃_p|` exceeds a
//!    fraction of `|r̃_p|`, when `τ_k < τ_min`, or every `K` components, the
//!    working map is made exact again by one FFT pair on the `2n` grid,
//!    `r̃ = r_major − B (m − m_major)` (a *resync*; no visibilities are
//!    touched). The minor cycle ends on exact values only: when the exact
//!    `|r_p|` is below the threshold, it resyncs and goes on if a peak above
//!    the threshold reappears.
//! 3. **Major cycles** run the model through the measurement (degrid and
//!    grid) when the minor cycle has removed a fraction `φ` of the misfit, or
//!    at the end, and record the realised Gram gap (exact `ΔQ` minus the
//!    image-domain prediction): what the image-domain model cannot know, the
//!    w-term and the gridder's accuracy. When `|gap| > (1 − θ) |predicted|`
//!    the fraction is halved (an inexact-Newton forcing rule), otherwise it
//!    returns towards its initial value.
//!
//! "Exact" therefore means exact for the image-domain beam at the phase
//! centre; the per-step certificate is not a statement about the
//! visibility-space misfit, whose departure the major cycle measures.

pub mod fits;
pub mod input;
pub mod kernels;

use crate::clean::{CleanStep, argmax_abs};
use crate::clean_certified::Measurement;
use kernels::Level;
use rayon::prelude::*;
use rustfft::num_complex::Complex;
use rustfft::{Fft, FftPlanner};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

type C64 = Complex<f64>;

const ZERO: C64 = Complex { re: 0.0, im: 0.0 };

// ---------------------------------------------------------------------------
// The 2n FFT convolver.

/// Linear convolution of an `n × n` image with a kernel given on the
/// `2n × 2n` grid centred on pixel `(n, n)`, by one FFT pair on the `2n`
/// grid: `out(y, x) = Σ in(y', x') k(y − y', x − x')` for every output pixel
/// of the `n × n` image (offsets up to `±(n − 1)` never wrap). Row-major,
/// rows are the slow index (`dy`).
pub struct Convolver {
    n: usize,
    /// The kernel spectrum, transposed (`[kx][ky]`).
    spectrum: Vec<C64>,
    forward: Arc<dyn Fft<f64>>,
    inverse: Arc<dyn Fft<f64>>,
}

/// `out[i][j] = src[j][i]` for `i < rows`, `j < m`; `src` is `m × m`.
fn transpose(src: &[C64], m: usize, rows: usize) -> Vec<C64> {
    const BLOCK: usize = 16;
    let mut out = vec![ZERO; rows * m];
    out.par_chunks_mut(BLOCK * m)
        .enumerate()
        .for_each(|(block, chunk)| {
            let i0 = block * BLOCK;
            let h = chunk.len() / m;
            for j in 0..m {
                let s = &src[j * m + i0..j * m + i0 + h];
                for (di, v) in s.iter().enumerate() {
                    chunk[di * m + j] = *v;
                }
            }
        });
    out
}

fn rows_fft(data: &mut [C64], m: usize, rows: usize, fft: &Arc<dyn Fft<f64>>) {
    let scratch = fft.get_inplace_scratch_len();
    data.par_chunks_mut(m).take(rows).for_each_init(
        || vec![ZERO; scratch],
        |s, row| fft.process_with_scratch(row, s),
    );
}

impl Convolver {
    /// `kernel` is `2n × 2n`, centred on `(n, n)`.
    pub fn new(n: usize, kernel: &[f64]) -> Result<Convolver, String> {
        let m = 2 * n;
        if n == 0 || kernel.len() != m * m {
            return Err("the kernel must be 2n × 2n".into());
        }
        let mut planner = FftPlanner::new();
        let forward = planner.plan_fft_forward(m);
        let inverse = planner.plan_fft_inverse(m);
        // Shift the centre to index 0: a[r][c] = kernel[(r + n) % m][(c + n) % m].
        let mut a = vec![ZERO; m * m];
        a.par_chunks_mut(m).enumerate().for_each(|(r, row)| {
            let src = ((r + n) % m) * m;
            for (c, v) in row.iter_mut().enumerate() {
                *v = Complex::new(kernel[src + (c + n) % m], 0.0);
            }
        });
        rows_fft(&mut a, m, m, &forward);
        let mut t = transpose(&a, m, m);
        drop(a);
        rows_fft(&mut t, m, m, &forward);
        Ok(Convolver {
            n,
            spectrum: t,
            forward,
            inverse,
        })
    }

    pub fn side(&self) -> usize {
        self.n
    }

    /// The kernel convolved with `input` (`n × n`), on the `n × n` image.
    pub fn apply(&self, input: &[f64]) -> Vec<f64> {
        let n = self.n;
        let m = 2 * n;
        assert_eq!(input.len(), n * n, "input must be n × n");
        let scratch = self
            .forward
            .get_inplace_scratch_len()
            .max(self.inverse.get_inplace_scratch_len());
        let mut a = vec![ZERO; m * m];
        // Rows n..2n of the padded input are zero and stay zero.
        a.par_chunks_mut(m).take(n).enumerate().for_each_init(
            || vec![ZERO; scratch],
            |s, (y, row)| {
                for (x, v) in row.iter_mut().take(n).enumerate() {
                    *v = Complex::new(input[y * n + x], 0.0);
                }
                self.forward.process_with_scratch(row, s);
            },
        );
        let mut t = transpose(&a, m, m);
        drop(a);
        let scale = 1.0 / (m * m) as f64;
        t.par_chunks_mut(m)
            .zip(self.spectrum.par_chunks(m))
            .for_each_init(
                || vec![ZERO; scratch],
                |s, (row, spec)| {
                    self.forward.process_with_scratch(row, s);
                    for (v, k) in row.iter_mut().zip(spec) {
                        *v *= k * scale;
                    }
                    self.inverse.process_with_scratch(row, s);
                },
            );
        // Only the first n rows of the result are needed.
        let mut b = transpose(&t, m, n);
        drop(t);
        let mut out = vec![0.0; n * n];
        b.par_chunks_mut(m)
            .zip(out.par_chunks_mut(n))
            .for_each_init(
                || vec![ZERO; scratch],
                |s, (row, o)| {
                    self.inverse.process_with_scratch(row, s);
                    for (x, v) in o.iter_mut().enumerate() {
                        *v = row[x].re;
                    }
                },
            );
        out
    }
}

// ---------------------------------------------------------------------------
// The beam.

/// The exact image-domain beam of gmclean: the patch `±P` subtracted every
/// step, the exterior (the beam outside the patch) for the exact
/// corrections, and the FFT of the whole beam for resyncs.
pub struct Beam {
    pub n: usize,
    /// `b(0)`.
    pub peak: f64,
    /// The patch half-width `P` (at most `n − 1`).
    pub patch: usize,
    patch_values: Vec<f64>,
    /// `(2n − 1)²` values, `[dy + n − 1][dx + n − 1]`, zero inside the patch.
    exterior: Vec<f64>,
    /// `max |b(Δ)| / b(0)` outside the patch (Theorem 6's `f`).
    pub f: f64,
    convolver: Convolver,
}

impl Beam {
    /// From a PSF image on the `2n × 2n` grid centred on `(n, n)` (row-major,
    /// rows the slow offset `dy`; [`crate::clean_certified::WgridMeasurement::psf_image`]
    /// with side `2n`).
    pub fn from_double(n: usize, psf2n: &[f64], patch: usize) -> Result<Beam, String> {
        let m = 2 * n;
        if n < 2 || psf2n.len() != m * m {
            return Err("the PSF must be 2n × 2n with n ≥ 2".into());
        }
        let patch = patch.min(n - 1);
        let at = |dx: isize, dy: isize| {
            psf2n[(n as isize + dy) as usize * m + (n as isize + dx) as usize]
        };
        let peak = at(0, 0);
        if !(peak > 0.0 && peak.is_finite()) {
            return Err(format!("the PSF peak must be positive, not {peak}"));
        }
        let w = 2 * n - 1;
        let off = (n - 1) as isize;
        let h = patch as isize;
        let mut exterior = vec![0.0; w * w];
        exterior
            .par_chunks_mut(w)
            .enumerate()
            .for_each(|(row, out)| {
                let dy = row as isize - off;
                for (col, v) in out.iter_mut().enumerate() {
                    let dx = col as isize - off;
                    if dx.abs() > h || dy.abs() > h {
                        *v = at(dx, dy);
                    }
                }
            });
        let pw = 2 * patch + 1;
        let mut patch_values = vec![0.0; pw * pw];
        for dy in -h..=h {
            for dx in -h..=h {
                patch_values[(dy + h) as usize * pw + (dx + h) as usize] = at(dx, dy);
            }
        }
        let f = exterior.iter().fold(0.0_f64, |a, v| a.max(v.abs())) / peak;
        let convolver = Convolver::new(n, psf2n)?;
        Ok(Beam {
            n,
            peak,
            patch,
            patch_values,
            exterior,
            f,
            convolver,
        })
    }

    /// The whole beam `b(dx, dy)`, `|dx|, |dy| ≤ n − 1`.
    pub fn at(&self, dx: isize, dy: isize) -> f64 {
        let h = self.patch as isize;
        if dx.abs() <= h && dy.abs() <= h {
            let pw = 2 * self.patch + 1;
            self.patch_values[(dy + h) as usize * pw + (dx + h) as usize]
        } else {
            let w = 2 * self.n - 1;
            let off = (self.n - 1) as isize;
            self.exterior[(dy + off) as usize * w + (dx + off) as usize]
        }
    }

    /// `B x` for an `n × n` image (one FFT pair on the `2n` grid).
    pub fn convolve(&self, x: &[f64]) -> Vec<f64> {
        self.convolver.apply(x)
    }

    /// The gather key of pixel `q`: the exterior index of `b(x_p − x_q)` is
    /// `base(p) − key(q)`.
    fn key(&self, q: usize) -> i64 {
        let w = (2 * self.n - 1) as i64;
        (q % self.n) as i64 + w * (q / self.n) as i64
    }

    fn base(&self, p: usize) -> i64 {
        let w = (2 * self.n - 1) as i64;
        let off = (self.n - 1) as i64;
        (p % self.n) as i64 + off + w * ((p / self.n) as i64 + off)
    }
}

// ---------------------------------------------------------------------------
// The working map with cached tile maxima.

const TILE: usize = 32;

fn better(a: (f64, usize), b: (f64, usize)) -> bool {
    a.0 > b.0 || (a.0 == b.0 && a.1 < b.1)
}

/// The working residual and the first argmax of `|r̃|` in each `32 × 32`
/// tile, so a step rescans only the tiles its patch touched.
struct Working {
    n: usize,
    r: Vec<f64>,
    tiles: usize,
    best: Vec<(f64, usize)>,
    level: Level,
}

impl Working {
    fn new(r: Vec<f64>, n: usize, level: Level) -> Working {
        let tiles = n.div_ceil(TILE);
        let mut w = Working {
            n,
            r,
            tiles,
            best: Vec::new(),
            level,
        };
        w.refresh_all();
        w
    }

    fn tile_best(r: &[f64], n: usize, tiles: usize, t: usize, level: Level) -> (f64, usize) {
        let (ty, tx) = (t / tiles, t % tiles);
        let (y0, y1) = (ty * TILE, ((ty + 1) * TILE).min(n));
        let (x0, x1) = (tx * TILE, ((tx + 1) * TILE).min(n));
        let mut best = (-1.0, usize::MAX);
        for y in y0..y1 {
            let (i, v) = kernels::max_abs(level, &r[y * n + x0..y * n + x1]);
            // Rows ascend, so a later equal value has a larger index.
            if v > best.0 {
                best = (v, y * n + x0 + i);
            }
        }
        best
    }

    fn refresh_all(&mut self) {
        let (r, n, tiles, level) = (&self.r, self.n, self.tiles, self.level);
        self.best = (0..tiles * tiles)
            .into_par_iter()
            .map(|t| Self::tile_best(r, n, tiles, t, level))
            .collect();
    }

    /// Rescan the tiles meeting rows `y0..=y1`, columns `x0..=x1`.
    fn refresh_rect(&mut self, y0: usize, y1: usize, x0: usize, x1: usize) {
        for ty in y0 / TILE..=y1 / TILE {
            for tx in x0 / TILE..=x1 / TILE {
                let t = ty * self.tiles + tx;
                self.best[t] = Self::tile_best(&self.r, self.n, self.tiles, t, self.level);
            }
        }
    }

    /// The first pixel of the largest `|r̃|` and its value.
    fn argmax(&self) -> (usize, f64) {
        let mut b = self.best[0];
        for &c in &self.best[1..] {
            if better(c, b) {
                b = c;
            }
        }
        (b.1, self.r[b.1])
    }

    /// `r̃ −= c b(· − x_p)` within the patch.
    fn subtract_patch(&mut self, beam: &Beam, p: usize, c: f64) {
        let n = self.n;
        let h = beam.patch;
        let (px, py) = (p % n, p / n);
        let (y0, y1) = (py.saturating_sub(h), (py + h).min(n - 1));
        let (x0, x1) = (px.saturating_sub(h), (px + h).min(n - 1));
        let pw = 2 * h + 1;
        let len = x1 - x0 + 1;
        for y in y0..=y1 {
            let b0 = (y + h - py) * pw + (x0 + h - px);
            kernels::sub_scaled(
                self.level,
                &mut self.r[y * n + x0..y * n + x0 + len],
                &beam.patch_values[b0..b0 + len],
                c,
            );
        }
        self.refresh_rect(y0, y1, x0, x1);
    }
}

/// The components since the working map was last exact, aggregated per
/// pixel, as gather keys and fluxes.
#[derive(Default)]
struct Since {
    index: HashMap<usize, usize>,
    keys: Vec<i64>,
    flux: Vec<f64>,
    /// `Σ |c_j|` over the steps (an upper bound on the aggregated sum).
    abs_sum: f64,
    steps: usize,
}

impl Since {
    fn add(&mut self, p: usize, key: i64, c: f64) {
        match self.index.get(&p) {
            Some(&j) => self.flux[j] += c,
            None => {
                self.index.insert(p, self.keys.len());
                self.keys.push(key);
                self.flux.push(c);
            }
        }
        self.abs_sum += c.abs();
        self.steps += 1;
    }

    fn clear(&mut self) {
        self.index.clear();
        self.keys.clear();
        self.flux.clear();
        self.abs_sum = 0.0;
        self.steps = 0;
    }
}

// ---------------------------------------------------------------------------
// The driver.

/// Settings of a gmclean run.
#[derive(Clone, Copy, Debug)]
pub struct Settings {
    /// The loop gain `γ` (`0 < γ < 2`).
    pub gain: f64,
    /// The initial fraction `φ` of the reducible misfit a minor cycle removes
    /// before a major cycle (WSClean's `-mgain` in spirit; here a misfit
    /// fraction, not a peak ratio).
    pub major_fraction: f64,
    /// Absolute threshold on the exact peak (Jy/beam).
    pub threshold: f64,
    /// Threshold in units of the residual's robust σ (`1.4826 MAD`),
    /// re-estimated every major cycle; the larger of the two applies.
    pub auto_threshold: Option<f64>,
    pub max_components: usize,
    pub max_major: usize,
    /// The forcing parameter `θ`: halve `φ` when the realised gap exceeds
    /// `(1 − θ)` of the predicted decrease.
    pub theta: f64,
    /// Resync when `|r_p − r̃_p| > drift · |r̃_p|`.
    pub drift: f64,
    /// Resync when the weak-greedy certificate `τ_k` falls below this.
    pub tau_min: f64,
    /// Resync after this many components without one.
    pub resync_every: usize,
    /// Recompute every `r_p` by brute force (the full beam over the model
    /// change since the major cycle) and record the largest difference.
    pub audit: bool,
    /// The SIMD level (`None`: [`kernels::level`]).
    pub level: Option<Level>,
}

impl Default for Settings {
    fn default() -> Settings {
        Settings {
            gain: 0.1,
            major_fraction: 0.8,
            threshold: 0.0,
            auto_threshold: None,
            max_components: 100_000,
            max_major: 20,
            theta: 0.5,
            drift: 0.1,
            tau_min: 0.5,
            resync_every: 2000,
            audit: false,
            level: None,
        }
    }
}

/// Why a minor cycle ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MinorStop {
    /// The exact image-domain peak is below the threshold.
    Threshold,
    /// The fraction `φ` of the reducible misfit was removed.
    MajorFraction,
    /// The component budget is spent.
    Budget,
}

/// Why the run ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StopReason {
    /// The exact (measurement) residual peak is below the threshold.
    Threshold,
    Components,
    MajorCycles,
}

/// Resyncs by cause.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Resyncs {
    pub drift: usize,
    pub tau: usize,
    pub every: usize,
    /// Before deciding that the exact peak is below the threshold.
    pub threshold: usize,
}

impl Resyncs {
    pub fn total(&self) -> usize {
        self.drift + self.tau + self.every + self.threshold
    }
}

/// Wall time by phase, in seconds.
#[derive(Clone, Copy, Debug, Default)]
pub struct Timings {
    /// The first residual (the dirty image).
    pub initial: f64,
    /// Minor-cycle work: argmax, patch subtraction, corrections.
    pub minor: f64,
    /// The exact corrections alone (part of `minor`).
    pub correction: f64,
    pub resync: f64,
    pub major: f64,
    pub total: f64,
}

/// One major cycle's record.
#[derive(Clone, Debug)]
pub struct Cycle {
    pub index: usize,
    pub components: usize,
    pub resyncs: Resyncs,
    pub stop: MinorStop,
    /// Exact peak at the start of the cycle and the threshold used.
    pub peak_start: f64,
    pub threshold: f64,
    /// The fraction `φ` in force.
    pub fraction: f64,
    pub q_before: f64,
    pub q_after: f64,
    /// From the model visibilities.
    pub dq_exact: f64,
    /// `−Σ γ(2−γ)/2 · r_p² / b(0)`, exact for the image-domain beam.
    pub dq_predicted: f64,
    pub gap: f64,
    /// `gap / q_before`.
    pub gap_relative: f64,
    /// The exact misfit rose over the cycle.
    pub ascending: bool,
    pub tau_min: f64,
    pub timings: Timings,
}

/// The outcome of [`run`].
#[derive(Clone, Debug)]
pub struct Outcome {
    /// The residual of the empty model.
    pub dirty: Vec<f64>,
    pub model: Vec<f64>,
    /// The exact residual of the final model (from the measurement).
    pub residual: Vec<f64>,
    pub q0: f64,
    pub q_final: f64,
    /// Pixel and exact `r_p` of every component.
    pub steps: Vec<CleanStep>,
    /// The weak-greedy certificate of every component.
    pub taus: Vec<f64>,
    pub cycles: Vec<Cycle>,
    pub stop: StopReason,
    pub f: f64,
    pub patch: usize,
    pub resyncs: Resyncs,
    pub timings: Timings,
    /// Gathered beam terms over all corrections.
    pub correction_terms: u64,
    /// Largest `|r_p(lazy) − r_p(brute force)|` (audit only).
    pub audit_max_error: Option<f64>,
    pub level: Level,
}

impl Outcome {
    /// `(min, 1 %, 10 %, median)` of the `τ_k`.
    pub fn tau_quantiles(&self) -> Option<(f64, f64, f64, f64)> {
        if self.taus.is_empty() {
            return None;
        }
        let mut t = self.taus.clone();
        t.sort_by(|a, b| a.total_cmp(b));
        let q = |f: f64| t[((t.len() - 1) as f64 * f).round() as usize];
        Some((t[0], q(0.01), q(0.1), q(0.5)))
    }
}

/// Minimal JSON helpers for the reports (hand-written, as the examples do).
pub mod json {
    pub fn num(x: f64) -> String {
        if x.is_finite() {
            format!("{x:e}")
        } else {
            "null".into()
        }
    }

    pub fn opt(x: Option<f64>) -> String {
        x.map_or("null".into(), num)
    }

    pub fn text(s: &str) -> String {
        let mut out = String::from("\"");
        for ch in s.chars() {
            match ch {
                '"' => out.push_str("\\\""),
                '\\' => out.push_str("\\\\"),
                c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
                c => out.push(c),
            }
        }
        out.push('"');
        out
    }

    pub fn obj(fields: &[(&str, String)]) -> String {
        let inner: Vec<String> = fields
            .iter()
            .map(|(k, v)| format!("{}: {v}", text(k)))
            .collect();
        format!("{{{}}}", inner.join(", "))
    }

    pub fn arr(items: &[String]) -> String {
        format!("[{}]", items.join(", "))
    }
}

fn timings_json(t: &Timings) -> String {
    use json::*;
    obj(&[
        ("initial_dirty", num(t.initial)),
        ("minor", num(t.minor)),
        ("correction", num(t.correction)),
        ("resync", num(t.resync)),
        ("major", num(t.major)),
        ("total", num(t.total)),
    ])
}

fn resyncs_json(r: &Resyncs) -> String {
    use json::*;
    obj(&[
        ("drift", r.drift.to_string()),
        ("tau", r.tau.to_string()),
        ("every", r.every.to_string()),
        ("threshold", r.threshold.to_string()),
        ("total", r.total().to_string()),
    ])
}

impl Outcome {
    /// The run as a JSON object: summary, `τ` statistics, timings and one
    /// record per major cycle; `q_floor` adds `(Q − Q_∞)/(Q_0 − Q_∞)`.
    pub fn to_json(&self, q_floor: Option<f64>) -> String {
        use json::*;
        let reducible = |q: f64| q_floor.map(|f| (q - f) / (self.q0 - f));
        let cycles: Vec<String> = self
            .cycles
            .iter()
            .map(|c| {
                obj(&[
                    ("index", c.index.to_string()),
                    ("components", c.components.to_string()),
                    ("stop", text(&format!("{:?}", c.stop))),
                    ("resyncs", resyncs_json(&c.resyncs)),
                    ("peak_start", num(c.peak_start)),
                    ("threshold", num(c.threshold)),
                    ("fraction", num(c.fraction)),
                    ("q_before", num(c.q_before)),
                    ("q_after", num(c.q_after)),
                    ("dq_exact", num(c.dq_exact)),
                    ("dq_predicted", num(c.dq_predicted)),
                    ("gap", num(c.gap)),
                    ("gap_relative", num(c.gap_relative)),
                    ("ascending", c.ascending.to_string()),
                    ("tau_min", num(c.tau_min)),
                    ("reducible_after", opt(reducible(c.q_after))),
                    ("seconds", timings_json(&c.timings)),
                ])
            })
            .collect();
        let tau = self.tau_quantiles();
        let tau_mean = if self.taus.is_empty() {
            None
        } else {
            Some(self.taus.iter().sum::<f64>() / self.taus.len() as f64)
        };
        let corr_per_step = if self.steps.is_empty() {
            None
        } else {
            Some(self.timings.correction / self.steps.len() as f64)
        };
        obj(&[
            ("components", self.steps.len().to_string()),
            (
                "model_pixels",
                self.model.iter().filter(|&&c| c != 0.0).count().to_string(),
            ),
            ("model_flux", num(self.model.iter().sum())),
            ("major_cycles", self.cycles.len().to_string()),
            ("stop", text(&format!("{:?}", self.stop))),
            ("patch", self.patch.to_string()),
            ("f_outside_patch", num(self.f)),
            ("q0", num(self.q0)),
            ("q_final", num(self.q_final)),
            ("q_final_over_q0", num(self.q_final / self.q0)),
            ("q_floor", opt(q_floor)),
            ("reducible_final", opt(reducible(self.q_final))),
            (
                "residual_peak_abs",
                num(self.residual.iter().fold(0.0_f64, |a, r| a.max(r.abs()))),
            ),
            ("residual_mad_sigma", num(mad_sigma(&self.residual))),
            (
                "ascending_major_cycles",
                self.cycles
                    .iter()
                    .filter(|c| c.ascending)
                    .count()
                    .to_string(),
            ),
            (
                "max_abs_gap_relative",
                num(self
                    .cycles
                    .iter()
                    .fold(0.0_f64, |a, c| a.max(c.gap_relative.abs()))),
            ),
            ("resyncs", resyncs_json(&self.resyncs)),
            (
                "tau",
                obj(&[
                    ("min", opt(tau.map(|t| t.0))),
                    ("p01", opt(tau.map(|t| t.1))),
                    ("p10", opt(tau.map(|t| t.2))),
                    ("median", opt(tau.map(|t| t.3))),
                    ("mean", opt(tau_mean)),
                ]),
            ),
            ("correction_terms", self.correction_terms.to_string()),
            ("correction_seconds_per_step", opt(corr_per_step)),
            ("audit_max_error", opt(self.audit_max_error)),
            ("simd", text(self.level.name())),
            ("seconds", timings_json(&self.timings)),
            ("cycles", arr(&cycles)),
        ])
    }
}

/// `1.4826 · median |x − median x|`: a robust noise estimate.
pub fn mad_sigma(x: &[f64]) -> f64 {
    if x.is_empty() {
        return 0.0;
    }
    let median = |v: &mut Vec<f64>| {
        let mid = v.len() / 2;
        let (_, m, _) = v.select_nth_unstable_by(mid, |a, b| a.total_cmp(b));
        *m
    };
    let mut v = x.to_vec();
    let med = median(&mut v);
    let mut dev: Vec<f64> = x.iter().map(|a| (a - med).abs()).collect();
    1.4826 * median(&mut dev)
}

fn effective_threshold(residual: &[f64], s: &Settings) -> f64 {
    let mut t = s.threshold;
    if let Some(k) = s.auto_threshold {
        t = t.max(k * mad_sigma(residual));
    }
    t
}

/// Make the working map exact: `r̃ = r_major − B (m − m_major)`.
fn resync(
    work: &mut Working,
    since: &mut Since,
    beam: &Beam,
    model: &[f64],
    model_major: &[f64],
    r_major: &[f64],
) {
    let delta: Vec<f64> = model
        .par_iter()
        .zip(model_major)
        .map(|(a, b)| a - b)
        .collect();
    let conv = beam.convolve(&delta);
    work.r
        .par_iter_mut()
        .zip(r_major)
        .zip(&conv)
        .for_each(|((w, r), c)| *w = r - c);
    work.refresh_all();
    since.clear();
}

/// gmclean on `measurement` with `beam` (from the measurement's `2n` PSF);
/// `q_floor`, an estimate of `Q_∞`, makes `φ` a fraction of `Q − Q_∞`.
pub fn run<M: Measurement>(
    measurement: &M,
    beam: &Beam,
    settings: &Settings,
    q_floor: Option<f64>,
) -> Result<Outcome, String> {
    let start = Instant::now();
    let s = settings;
    let n = measurement.side();
    if beam.n != n {
        return Err("the beam must match the image side".into());
    }
    if !(s.gain > 0.0 && s.gain < 2.0) {
        return Err("the gain must be in (0, 2)".into());
    }
    let level = s.level.unwrap_or_else(kernels::level);
    let mut timings = Timings::default();
    let mut model = vec![0.0; n * n];
    let t = Instant::now();
    let (mut residual, q0) = measurement.residual(&model)?;
    timings.initial = t.elapsed().as_secs_f64();
    let dirty = residual.clone();
    let mut q = q0;
    let mut fraction = s.major_fraction;
    let mut steps: Vec<CleanStep> = Vec::new();
    let mut taus = Vec::new();
    let mut cycles: Vec<Cycle> = Vec::new();
    let mut resyncs_all = Resyncs::default();
    let mut correction_terms = 0u64;
    let mut audit_max: Option<f64> = s.audit.then_some(0.0);
    let decrease = s.gain * (2.0 - s.gain) / 2.0;
    let stop = loop {
        let threshold = effective_threshold(&residual, s);
        let (_, peak) = argmax_abs(&residual);
        if peak.abs() < threshold {
            break StopReason::Threshold;
        }
        if steps.len() >= s.max_components {
            break StopReason::Components;
        }
        if cycles.len() >= s.max_major {
            break StopReason::MajorCycles;
        }
        let mut ct = Timings::default();
        let model_major = model.clone();
        let mut work = Working::new(residual.clone(), n, level);
        let mut since = Since::default();
        let mut delta: HashMap<usize, f64> = HashMap::new();
        let mut predicted = 0.0;
        let mut resyncs = Resyncs::default();
        let mut tau_min = f64::INFINITY;
        let goal = fraction * (q - q_floor.unwrap_or(0.0)).max(0.0);
        let taken_before = steps.len();
        let minor_start = Instant::now();
        let minor_stop = loop {
            let (p, rt) = work.argmax();
            let tc = Instant::now();
            // A patch covering every offset leaves no exterior to correct.
            let corr = if since.keys.is_empty() || beam.f == 0.0 {
                0.0
            } else {
                correction_terms += since.keys.len() as u64;
                kernels::gather_sum(
                    level,
                    &beam.exterior,
                    beam.base(p),
                    &since.keys,
                    &since.flux,
                )
            };
            ct.correction += tc.elapsed().as_secs_f64();
            let r = rt - corr;
            if let Some(worst) = audit_max.as_mut() {
                let (px, py) = ((p % n) as isize, (p / n) as isize);
                let mut brute = residual[p];
                for (&j, &c) in &delta {
                    let (jx, jy) = ((j % n) as isize, (j / n) as isize);
                    brute -= c * beam.at(px - jx, py - jy);
                }
                *worst = worst.max((r - brute).abs());
            }
            if r.abs() < threshold || r == 0.0 {
                if since.steps == 0 {
                    break MinorStop::Threshold;
                }
                let tr = Instant::now();
                resync(&mut work, &mut since, beam, &model, &model_major, &residual);
                ct.resync += tr.elapsed().as_secs_f64();
                resyncs.threshold += 1;
                continue;
            }
            let e = beam.f * beam.peak * since.abs_sum;
            let tau = r.abs() / (rt.abs() + e);
            if tau < s.tau_min {
                let tr = Instant::now();
                resync(&mut work, &mut since, beam, &model, &model_major, &residual);
                ct.resync += tr.elapsed().as_secs_f64();
                resyncs.tau += 1;
                continue;
            }
            if steps.len() >= s.max_components {
                break MinorStop::Budget;
            }
            let c = s.gain * r / beam.peak;
            model[p] += c;
            predicted -= decrease * r * r / beam.peak;
            work.subtract_patch(beam, p, c);
            since.add(p, beam.key(p), c);
            if s.audit {
                *delta.entry(p).or_insert(0.0) += c;
            }
            steps.push(CleanStep { pixel: p, peak: r });
            taus.push(tau);
            tau_min = tau_min.min(tau);
            if goal > 0.0 && -predicted >= goal {
                break MinorStop::MajorFraction;
            }
            let drifted = (r - rt).abs() > s.drift * rt.abs();
            if drifted || since.steps >= s.resync_every {
                let tr = Instant::now();
                resync(&mut work, &mut since, beam, &model, &model_major, &residual);
                ct.resync += tr.elapsed().as_secs_f64();
                if drifted {
                    resyncs.drift += 1;
                } else {
                    resyncs.every += 1;
                }
            }
        };
        ct.minor = minor_start.elapsed().as_secs_f64() - ct.resync;
        let tm = Instant::now();
        let (next, q_next) = measurement.residual(&model)?;
        ct.major = tm.elapsed().as_secs_f64();
        let dq_exact = q_next - q;
        let gap = dq_exact - predicted;
        cycles.push(Cycle {
            index: cycles.len(),
            components: steps.len() - taken_before,
            resyncs,
            stop: minor_stop,
            peak_start: peak.abs(),
            threshold,
            fraction,
            q_before: q,
            q_after: q_next,
            dq_exact,
            dq_predicted: predicted,
            gap,
            gap_relative: gap / q,
            ascending: dq_exact > 0.0,
            tau_min,
            timings: ct,
        });
        timings.minor += ct.minor;
        timings.correction += ct.correction;
        timings.resync += ct.resync;
        timings.major += ct.major;
        resyncs_all.drift += resyncs.drift;
        resyncs_all.tau += resyncs.tau;
        resyncs_all.every += resyncs.every;
        resyncs_all.threshold += resyncs.threshold;
        if predicted < 0.0 {
            if gap.abs() > (1.0 - s.theta) * predicted.abs() {
                fraction *= 0.5;
            } else {
                fraction = (fraction * 2.0).min(s.major_fraction);
            }
        }
        residual = next;
        q = q_next;
    };
    timings.total = start.elapsed().as_secs_f64();
    Ok(Outcome {
        dirty,
        model,
        residual,
        q0,
        q_final: q,
        steps,
        taus,
        cycles,
        stop,
        f: beam.f,
        patch: beam.patch,
        resyncs: resyncs_all,
        timings,
        correction_terms,
        audit_max_error: audit_max,
        level,
    })
}

// ---------------------------------------------------------------------------
// Restoring.

/// An elliptical Gaussian `exp(−(a X² + b X Y + c Y²))` in pixels of the FITS
/// frame (`X` along FITS axis 1, the gridder's slow index; `Y` along axis 2,
/// the fast index), with its FWHM axes and position angle.
#[derive(Clone, Copy, Debug)]
pub struct RestoringBeam {
    pub a: f64,
    pub b: f64,
    pub c: f64,
    /// FWHM in pixels.
    pub major: f64,
    pub minor: f64,
    /// Position angle of the major axis, radians from +Y (north) towards −X
    /// (east, as `CDELT1 < 0`), in `(−π/2, π/2]`.
    pub pa: f64,
    /// Main-lobe pixels used in the fit.
    pub pixels: usize,
}

impl RestoringBeam {
    fn from_quadratic(a: f64, b: f64, c: f64, pixels: usize) -> RestoringBeam {
        let mean = 0.5 * (a + c);
        let radius = (0.25 * (a - c) * (a - c) + 0.25 * b * b).sqrt();
        let (lmin, lmax) = (mean - radius, mean + radius);
        let fwhm = |l: f64| 2.0 * (std::f64::consts::LN_2 / l).sqrt();
        // The quadratic form is largest along ½ atan2(b, a − c): the minor axis.
        let minor_dir = 0.5 * b.atan2(a - c);
        let major_dir = minor_dir + std::f64::consts::FRAC_PI_2;
        let (x, y) = (major_dir.cos(), major_dir.sin());
        let mut pa = (-x).atan2(y);
        while pa > std::f64::consts::FRAC_PI_2 {
            pa -= std::f64::consts::PI;
        }
        while pa <= -std::f64::consts::FRAC_PI_2 {
            pa += std::f64::consts::PI;
        }
        RestoringBeam {
            a,
            b,
            c,
            major: fwhm(lmin),
            minor: fwhm(lmax),
            pa,
            pixels,
        }
    }

    /// A circular beam of the given FWHM in pixels.
    pub fn circular(fwhm: f64) -> RestoringBeam {
        let a = 4.0 * std::f64::consts::LN_2 / (fwhm * fwhm);
        RestoringBeam::from_quadratic(a, 0.0, a, 0)
    }

    pub fn value(&self, x: f64, y: f64) -> f64 {
        (-(self.a * x * x + self.b * x * y + self.c * y * y)).exp()
    }

    /// The Gaussian on the `2n × 2n` grid centred on `(n, n)`, gridder layout
    /// (row = `X`, column = `Y`), for a [`Convolver`].
    pub fn kernel_double(&self, n: usize) -> Vec<f64> {
        let m = 2 * n;
        let mut k = vec![0.0; m * m];
        k.par_chunks_mut(m).enumerate().for_each(|(r, row)| {
            let x = r as f64 - n as f64;
            for (col, v) in row.iter_mut().enumerate() {
                *v = self.value(x, col as f64 - n as f64);
            }
        });
        k
    }
}

/// Fit an elliptical Gaussian to the PSF main lobe: linear least squares of
/// `−ln(b/b(0))` on the pixels connected to the centre with `b ≥ b(0)/2`.
/// `psf2n` is the `2n × 2n` PSF in gridder layout, centred on `(n, n)`. A
/// main lobe of fewer than six pixels gives a circular one-pixel beam.
pub fn fit_restoring_beam(n: usize, psf2n: &[f64]) -> RestoringBeam {
    let m = 2 * n;
    let centre = n * m + n;
    let peak = psf2n[centre];
    let mut seen = vec![false; m * m];
    let mut queue = vec![centre];
    seen[centre] = true;
    let mut normal = [[0.0; 3]; 3];
    let mut rhs = [0.0; 3];
    let mut count = 0;
    while let Some(p) = queue.pop() {
        let (r, c) = (p / m, p % m);
        let v = psf2n[p] / peak;
        let x = r as f64 - n as f64;
        let y = c as f64 - n as f64;
        let row = [x * x, x * y, y * y];
        for i in 0..3 {
            for j in 0..3 {
                normal[i][j] += row[i] * row[j];
            }
            rhs[i] += row[i] * (-v.ln());
        }
        count += 1;
        for (dr, dc) in [(-1isize, 0isize), (1, 0), (0, -1), (0, 1)] {
            let (rr, cc) = (r as isize + dr, c as isize + dc);
            if rr < 0 || cc < 0 || rr >= m as isize || cc >= m as isize {
                continue;
            }
            let q = rr as usize * m + cc as usize;
            if !seen[q] && psf2n[q] >= 0.5 * peak {
                seen[q] = true;
                queue.push(q);
            }
        }
    }
    let flat: Vec<f64> = normal.iter().flatten().copied().collect();
    match (count >= 6)
        .then(|| crate::clean::solve_dense(&flat, &rhs))
        .flatten()
    {
        Some(s) if s[0] > 0.0 && s[2] > 0.0 && 4.0 * s[0] * s[2] > s[1] * s[1] => {
            RestoringBeam::from_quadratic(s[0], s[1], s[2], count)
        }
        _ => RestoringBeam {
            pixels: count,
            ..RestoringBeam::circular(1.0)
        },
    }
}

/// The restored image `residual + model ⊛ G` with the Gaussian at unit peak.
pub fn restore(n: usize, model: &[f64], residual: &[f64], beam: &RestoringBeam) -> Vec<f64> {
    let conv = Convolver::new(n, &beam.kernel_double(n)).expect("valid kernel size");
    let smooth = conv.apply(model);
    smooth.iter().zip(residual).map(|(s, r)| s + r).collect()
}

/// The peak resident set size (Linux `VmHWM`), when the platform reports it.
pub fn peak_memory_bytes() -> Option<u64> {
    let status = std::fs::read_to_string("/proc/self/status").ok()?;
    let line = status.lines().find(|l| l.starts_with("VmHWM:"))?;
    let kb: u64 = line.split_whitespace().nth(1)?.parse().ok()?;
    Some(kb * 1024)
}

// ---------------------------------------------------------------------------
// Kernel micro-benchmark.

/// Nanoseconds per pixel (patch subtraction, argmax) and per term (gather)
/// of one SIMD level.
#[derive(Clone, Copy, Debug)]
pub struct KernelTiming {
    pub level: Level,
    pub patch_ns_per_pixel: f64,
    pub argmax_ns_per_pixel: f64,
    pub gather_ns_per_term: f64,
}

/// Time the three kernels at every level the CPU has, on a synthetic
/// `n × n` map, `±patch` beam patches and `terms` gathered components.
pub fn kernel_benchmark(n: usize, patch: usize, terms: usize, reps: usize) -> Vec<KernelTiming> {
    let mut state = 0x9e37_79b9_7f4a_7c15u64;
    let mut next = || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        (state >> 11) as f64 / (1u64 << 53) as f64 - 0.5
    };
    let map: Vec<f64> = (0..n * n).map(|_| next()).collect();
    let pw = 2 * patch + 1;
    let beam: Vec<f64> = (0..pw).map(|_| next()).collect();
    let w = 2 * n - 1;
    let table: Vec<f64> = (0..w * w).map(|_| next()).collect();
    let base = (w * w - 1) as i64;
    let keys: Vec<i64> = (0..terms)
        .map(|_| ((next() + 0.5) * (w * w - 1) as f64) as i64)
        .collect();
    let flux: Vec<f64> = (0..terms).map(|_| next()).collect();
    let mut out = Vec::new();
    for level in [Level::Scalar, Level::Avx2, Level::Avx512] {
        if level > kernels::detected() {
            continue;
        }
        let mut work = map.clone();
        let t = Instant::now();
        for rep in 0..reps {
            for row in 0..pw.min(n) {
                let r = &mut work[row * n..row * n + pw.min(n)];
                kernels::sub_scaled(level, r, &beam, 1e-3 * rep as f64);
            }
        }
        let patch_ns = t.elapsed().as_secs_f64() * 1e9 / (reps * pw.min(n) * pw.min(n)) as f64;
        let t = Instant::now();
        let mut sink = 0usize;
        for _ in 0..reps {
            for row in work.chunks(TILE) {
                sink = sink.wrapping_add(kernels::max_abs(level, row).0);
            }
        }
        let argmax_ns = t.elapsed().as_secs_f64() * 1e9 / (reps * n * n) as f64;
        let t = Instant::now();
        let mut total = 0.0;
        for _ in 0..reps {
            total += kernels::gather_sum(level, &table, base, &keys, &flux);
        }
        let gather_ns = t.elapsed().as_secs_f64() * 1e9 / (reps * terms.max(1)) as f64;
        std::hint::black_box((sink, total));
        out.push(KernelTiming {
            level,
            patch_ns_per_pixel: patch_ns,
            argmax_ns_per_pixel: argmax_ns,
            gather_ns_per_term: gather_ns,
        });
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::clean::{self, Grid, Psf, Sampling, Vis};
    use crate::clean_certified::DftMeasurement;

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
        truth[GRID.index(15, 0)] = 0.3;
        let mut vis = clean::predict(s, &GRID, &truth);
        for v in &mut vis {
            v.0 += 0.05 * (rng.next() - 0.5);
            v.1 += 0.05 * (rng.next() - 0.5);
        }
        vis
    }

    /// The `2n × 2n` PSF image of a direct-sum beam (row and column 0, the
    /// offset −n, are never used and stay zero).
    fn double(psf: &Psf) -> Vec<f64> {
        let n = psf.n;
        let m = 2 * n;
        let mut out = vec![0.0; m * m];
        for r in 1..m {
            for c in 1..m {
                out[r * m + c] = psf.at(c as isize - n as isize, r as isize - n as isize);
            }
        }
        out
    }

    #[test]
    fn convolver_equals_direct_subtraction() {
        let s = sampling(150, 4);
        let psf = clean::psf(&s, &GRID);
        let conv = Convolver::new(GRID.n, &double(&psf)).unwrap();
        let mut rng = Rng(8);
        let mut model = vec![0.0; GRID.pixels()];
        for p in [
            GRID.index(0, 0),
            GRID.index(15, 2),
            GRID.index(3, 15),
            77,
            200,
        ] {
            model[p] = rng.next() - 0.3;
        }
        let fast = conv.apply(&model);
        let direct = clean::convolve(&psf, &model);
        for (a, b) in fast.iter().zip(&direct) {
            assert!((a - b).abs() < 1e-12, "{a} against {b}");
        }
    }

    #[test]
    fn tiled_argmax_follows_the_raster_argmax() {
        let mut rng = Rng(21);
        for n in [5, 32, 33, 70] {
            let r: Vec<f64> = (0..n * n).map(|_| rng.next() - 0.5).collect();
            let mut w = Working::new(r.clone(), n, kernels::level());
            assert_eq!(w.argmax().0, clean::argmax_abs(&r).0);
            // A tie across tiles resolves to the lower index.
            let v = 2.0;
            w.r[n * n - 1] = -v;
            w.r[n + 1] = v;
            w.refresh_all();
            assert_eq!(w.argmax().0, n + 1);
        }
    }

    #[test]
    fn exact_steps_audit_and_gap_on_the_direct_measurement() {
        for (seed, patch) in [(3u64, 2usize), (5, 4), (9, 1), (12, 15)] {
            let s = sampling(160, seed);
            let vis = data(&s, seed);
            let m = DftMeasurement {
                sampling: &s,
                grid: GRID,
                vis: &vis,
            };
            let psf = clean::psf(&s, &GRID);
            let beam = Beam::from_double(GRID.n, &double(&psf), patch).unwrap();
            let settings = Settings {
                gain: 0.2,
                threshold: 1e-3,
                max_components: 600,
                max_major: 6,
                audit: true,
                resync_every: 50,
                ..Settings::default()
            };
            let out = run(&m, &beam, &settings, None).unwrap();
            assert!(out.steps.len() > 20, "seed {seed}: {}", out.steps.len());
            let audit = out.audit_max_error.unwrap();
            assert!(audit < 1e-12, "seed {seed}, patch {patch}: audit {audit}");
            for c in &out.cycles {
                assert!(
                    c.gap.abs() <= 1e-11 * c.q_before,
                    "seed {seed}, cycle {}: gap {}",
                    c.index,
                    c.gap
                );
                assert!(c.dq_exact < 0.0 && !c.ascending);
            }
            for t in &out.taus {
                assert!(*t >= settings.tau_min && *t <= 1.0 + 1e-12);
            }
            if patch == GRID.n - 1 {
                assert_eq!(out.f, 0.0);
                assert_eq!(out.correction_terms, 0);
            } else {
                assert!(out.f > 0.0 && out.correction_terms > 0);
            }
        }
    }

    #[test]
    fn simd_and_scalar_runs_agree() {
        let s = sampling(160, 31);
        let vis = data(&s, 31);
        let m = DftMeasurement {
            sampling: &s,
            grid: GRID,
            vis: &vis,
        };
        let psf = clean::psf(&s, &GRID);
        let beam = Beam::from_double(GRID.n, &double(&psf), 3).unwrap();
        let mut settings = Settings {
            threshold: 1e-3,
            max_components: 300,
            ..Settings::default()
        };
        settings.level = Some(Level::Scalar);
        let a = run(&m, &beam, &settings, None).unwrap();
        settings.level = Some(kernels::detected());
        let b = run(&m, &beam, &settings, None).unwrap();
        assert_eq!(a.steps.len(), b.steps.len());
        for (x, y) in a.steps.iter().zip(&b.steps) {
            assert_eq!(x.pixel, y.pixel);
            assert!((x.peak - y.peak).abs() <= 1e-12 * x.peak.abs().max(1e-3));
        }
    }

    #[test]
    fn gaussian_fit_recovers_a_rotated_beam() {
        let n = 40;
        let truth = RestoringBeam::from_quadratic(0.05, 0.03, 0.012, 0);
        let psf = truth.kernel_double(n);
        let fit = fit_restoring_beam(n, &psf);
        assert!((fit.a - truth.a).abs() < 1e-10);
        assert!((fit.b - truth.b).abs() < 1e-10);
        assert!((fit.c - truth.c).abs() < 1e-10);
        assert!((fit.major - truth.major).abs() < 1e-8 && fit.major > fit.minor);
        assert!((fit.pa - truth.pa).abs() < 1e-8);
        // A beam elongated along +Y (north) has PA 0; along X, ±90°.
        let north = RestoringBeam::from_quadratic(0.1, 0.0, 0.01, 0);
        assert!(north.pa.abs() < 1e-12);
        let east = RestoringBeam::from_quadratic(0.01, 0.0, 0.1, 0);
        assert!((east.pa.abs() - std::f64::consts::FRAC_PI_2).abs() < 1e-12);
        // Elongated towards −X when going +Y (north-east): positive PA.
        let ne = RestoringBeam::from_quadratic(0.05, 0.08, 0.05, 0);
        assert!(
            (ne.pa - std::f64::consts::FRAC_PI_4).abs() < 1e-12,
            "{}",
            ne.pa
        );
        // Restoring a point gives the flux at its pixel.
        let mut model = vec![0.0; n * n];
        model[7 * n + 30] = 2.5;
        let restored = restore(n, &model, &vec![0.0; n * n], &fit);
        assert!((restored[7 * n + 30] - 2.5).abs() < 1e-10);
    }

    #[test]
    fn mad_sigma_of_a_known_sample() {
        let x: Vec<f64> = (0..101).map(|i| i as f64).collect();
        // median 50, deviations 0..50 with median 25.
        assert!((mad_sigma(&x) - 1.4826 * 25.0).abs() < 1e-12);
    }
}
