//! The measured half of `research/clean-implicit-objective.md`: small-gain
//! Högbom CLEAN against incremental forward stagewise (FS_ε), the lasso and
//! the non-negative lasso, on MeerKAT sampling.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Run from the repository root:
//! `cargo run --release --manifest-path core/Cargo.toml --example clean_implicit -- OUTDIR`.
//! Writes `OUTDIR/clean-implicit-objective.json` and prints the tables of the
//! note.
//!
//! Everything runs in the image domain on the exact PSF (the Gram matrix of
//! the atoms), so the misfit of a model is `Q = Q_0 − ½ m·(d + r)` and a step
//! of `c` at pixel `p` changes it by exactly `−c r_p + c²/2`. Scenes are
//! noiseless: the Gaussian disc of E6 (FWHM 12 px) and the six-source scene of
//! E1 without its noise, on the track-uniform and snapshot-natural
//! configurations of `clean_theory` (same geometry, same seeds). Paths are
//! compared at matched misfit `Q/Q_0 ∈ {0.1, 0.01, 0.001, 1e-4, 1e-5}`, the
//! crossing located inside the step (or homotopy segment) that crosses it.

use rang_core::clean::{Grid, Psf, Sampling, argmax_abs, convolve, gram, min_eigenvalue, psf};
use std::f64::consts::PI;
use std::fmt::Write as _;
use std::time::Instant;

const C: f64 = 299_792_458.0;
const FREQUENCY: f64 = 1.4e9;
const DECLINATION_DEG: f64 = -30.0;
const N: usize = 64;
/// 2 arcsec pixels, as in `clean_theory`.
const CELL: f64 = 2.0 / 3600.0 * PI / 180.0;
/// Matched misfits: the three of the task and two deeper ones, where E6 saw
/// the small-gain snapshot model go negative.
const LEVELS: [f64; 5] = [0.1, 0.01, 0.001, 1e-4, 1e-5];
const GAINS: [f64; 6] = [1.0, 0.3, 0.1, 0.03, 0.01, 0.003];
/// FS increments as fractions of the dirty-image peak: the reference and two
/// coarser ones that measure the reference's own discretisation error.
const FS_FRACTIONS: [f64; 3] = [3e-5, 1.2e-4, 4.8e-4];

/// xorshift64* as in `clean_theory` (only `uniform` and `below` are needed
/// for the noiseless scenes; `normal` keeps the draw sequence identical).
struct Rng(u64);

impl Rng {
    fn uniform(&mut self) -> f64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0.wrapping_mul(0x2545_F491_4F6C_DD1D) >> 11) as f64 / (1u64 << 53) as f64
    }

    fn below(&mut self, n: usize) -> usize {
        ((self.uniform() * n as f64) as usize).min(n - 1)
    }
}

/// MeerKAT antenna positions (ITRF metres) from `data/meerkat.itrf.txt`.
fn antennas() -> Vec<[f64; 3]> {
    include_str!("../../data/meerkat.itrf.txt")
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| {
            let f: Vec<f64> = line
                .split_whitespace()
                .take(3)
                .map(|v| v.parse().expect("ITRF coordinate"))
                .collect();
            [f[0], f[1], f[2]]
        })
        .collect()
}

/// ITRF to east-north-up about the array centroid, and the centroid latitude.
fn enu(itrf: &[[f64; 3]]) -> (Vec<[f64; 3]>, f64) {
    let n = itrf.len() as f64;
    let c = itrf.iter().fold([0.0; 3], |acc, p| {
        [acc[0] + p[0] / n, acc[1] + p[1] / n, acc[2] + p[2] / n]
    });
    let lon = c[1].atan2(c[0]);
    let lat = c[2].atan2((c[0] * c[0] + c[1] * c[1]).sqrt());
    let (sl, cl) = lon.sin_cos();
    let (sp, cp) = lat.sin_cos();
    let positions = itrf
        .iter()
        .map(|p| {
            let d = [p[0] - c[0], p[1] - c[1], p[2] - c[2]];
            [
                -sl * d[0] + cl * d[1],
                -sp * cl * d[0] - sp * sl * d[1] + cp * d[2],
                cp * cl * d[0] + cp * sl * d[1] + sp * d[2],
            ]
        })
        .collect();
    (positions, lat)
}

/// Baseline ENU to (u, v) in metres for hour angle `hour` and declination `dec`.
fn uv(east: f64, north: f64, up: f64, lat: f64, hour: f64, dec: f64) -> (f64, f64) {
    let x = -north * lat.sin() + up * lat.cos();
    let y = east;
    let z = north * lat.cos() + up * lat.sin();
    (
        hour.sin() * x + hour.cos() * y,
        -dec.sin() * hour.cos() * x + dec.sin() * hour.sin() * y + dec.cos() * z,
    )
}

struct Config {
    name: &'static str,
    hours: Vec<f64>,
    uniform: bool,
}

/// The sampling of `clean_theory`, unchanged.
fn sampling(config: &Config, grid: &Grid) -> Sampling {
    let (positions, lat) = enu(&antennas());
    let dec = DECLINATION_DEG.to_radians();
    let mut s = Sampling::default();
    for &hour in &config.hours {
        let ha = hour * PI / 12.0;
        for p in 0..positions.len() {
            for q in p + 1..positions.len() {
                let d = [
                    positions[p][0] - positions[q][0],
                    positions[p][1] - positions[q][1],
                    positions[p][2] - positions[q][2],
                ];
                let (u, v) = uv(d[0], d[1], d[2], lat, ha, dec);
                s.u.push(u * FREQUENCY / C);
                s.v.push(v * FREQUENCY / C);
                s.w.push(1.0);
            }
        }
    }
    if config.uniform {
        let du = 1.0 / (grid.n as f64 * grid.cell);
        let mut counts = std::collections::HashMap::new();
        let cells: Vec<(i64, i64)> = (0..s.len())
            .map(|k| {
                let (u, v) = if s.v[k] < 0.0 || (s.v[k] == 0.0 && s.u[k] < 0.0) {
                    (-s.u[k], -s.v[k])
                } else {
                    (s.u[k], s.v[k])
                };
                ((u / du).round() as i64, (v / du).round() as i64)
            })
            .collect();
        for &cell in &cells {
            *counts.entry(cell).or_insert(0usize) += 1;
        }
        for k in 0..s.len() {
            s.w[k] = 1.0 / counts[&cells[k]] as f64;
        }
    }
    s.normalise();
    s
}

/// Hand-written JSON, as in `clean_theory`.
struct Json(String);

impl Json {
    fn key(&mut self, name: &str) {
        let _ = write!(self.0, "\"{name}\": ");
    }
    fn num(&mut self, name: &str, value: f64) {
        self.key(name);
        if value.is_finite() {
            let _ = write!(self.0, "{value:e}, ");
        } else {
            self.0.push_str("null, ");
        }
    }
    fn int(&mut self, name: &str, value: usize) {
        self.key(name);
        let _ = write!(self.0, "{value}, ");
    }
    fn boolean(&mut self, name: &str, value: bool) {
        self.key(name);
        let _ = write!(self.0, "{value}, ");
    }
    fn text(&mut self, name: &str, value: &str) {
        self.key(name);
        let _ = write!(self.0, "\"{value}\", ");
    }
    fn open_list(&mut self, name: &str) {
        self.key(name);
        self.0.push_str("[ ");
    }
    fn item(&mut self) {
        self.0.push_str("{ ");
    }
    fn close(&mut self) {
        self.trim_comma();
        self.0.push_str(" }, ");
    }
    fn close_list(&mut self) {
        self.trim_comma();
        self.0.push_str(" ], ");
    }
    fn trim_comma(&mut self) {
        let t = self.0.trim_end().trim_end_matches(',').to_string();
        self.0 = t;
    }
    fn finish(mut self) -> String {
        self.trim_comma();
        self.0.push_str(" }\n");
        self.0
    }
}

/// `residual −= c · b(· − x_p)` over the whole image, row slices at a time
/// (the same arithmetic as `clean::subtract` with no patch, vectorisable).
fn sub(residual: &mut [f64], b: &Psf, p: usize, c: f64) {
    let n = b.n;
    let w = 2 * n - 1;
    let px = p % n;
    let py = p / n;
    for y in 0..n {
        let start = (n - 1 - px) + w * (y + n - 1 - py);
        let beam = &b.values[start..start + n];
        for (r, bv) in residual[y * n..(y + 1) * n].iter_mut().zip(beam) {
            *r -= c * bv;
        }
    }
}

fn dot(x: &[f64], y: &[f64]) -> f64 {
    x.iter().zip(y).map(|(a, b)| a * b).sum()
}

fn rms_diff(x: &[f64], y: &[f64]) -> f64 {
    (x.iter().zip(y).map(|(a, b)| (a - b).powi(2)).sum::<f64>() / x.len() as f64).sqrt()
}

fn l1(x: &[f64]) -> f64 {
    x.iter().map(|v| v.abs()).sum()
}

fn min_value(x: &[f64]) -> f64 {
    x.iter().cloned().fold(0.0, f64::min)
}

/// A noiseless scene in the image domain: truth, dirty image `d = B x` and
/// `Q_0 = ½ ‖v‖² = ½ x·d`.
struct Scene {
    name: &'static str,
    truth: Vec<f64>,
    dirty: Vec<f64>,
    q0: f64,
}

fn make_scene(name: &'static str, truth: Vec<f64>, b: &Psf) -> Scene {
    let dirty = convolve(b, &truth);
    let q0 = 0.5 * dot(&truth, &dirty);
    Scene {
        name,
        truth,
        dirty,
        q0,
    }
}

/// The E6 disc: a Gaussian of FWHM 12 pixels and unit peak at the centre.
fn disc(grid: &Grid) -> Vec<f64> {
    let sigma = 12.0 / (8.0 * 2f64.ln()).sqrt();
    let centre = (grid.n / 2) as f64;
    (0..grid.pixels())
        .map(|p| {
            let dx = (p % grid.n) as f64 - centre;
            let dy = (p / grid.n) as f64 - centre;
            (-(dx * dx + dy * dy) / (2.0 * sigma * sigma)).exp()
        })
        .collect()
}

/// The E1 six-source scene of `clean_theory`, same seed and draw order,
/// without the visibility noise (which is drawn after the positions).
fn six_sources(grid: &Grid, config_name: &str) -> Vec<f64> {
    let mut rng = Rng(0x9E37_79B9_7F4A_7C15 ^ config_name.len() as u64);
    let mut truth = vec![0.0; grid.pixels()];
    for &f in &[1.0, 0.7, 0.5, 0.3, 0.2] {
        loop {
            let p = grid.index(4 + rng.below(grid.n - 8), 4 + rng.below(grid.n - 8));
            if truth[p] == 0.0 {
                truth[p] = f;
                break;
            }
        }
    }
    truth[grid.index(2, grid.n / 2)] = 0.8;
    truth
}

#[derive(Clone, Copy)]
enum Rule {
    /// Fixed increment `ε`.
    Fs(f64),
    /// CLEAN: increment `γ |r_p|`.
    Clean(f64),
}

/// The state of a path at a matched misfit.
#[derive(Clone)]
struct Snapshot {
    model: Vec<f64>,
    residual: Vec<f64>,
    arc: f64,
    negative_arc: f64,
    steps: usize,
    /// Pixels within `2h` of the peak residual and the smallest eigenvalue
    /// of their Gram matrix (zero if dependent to working precision).
    tied: usize,
    tied_lambda_min: f64,
    q_ratio: f64,
}

struct PathRun {
    snapshots: Vec<Option<Snapshot>>,
    steps: usize,
    seconds: f64,
    /// Largest relative gap between the incrementally tracked misfit and
    /// `Q_0 − ½ m·(d + r)` at the snapshots.
    drift: f64,
}

/// FS or CLEAN from the empty model until the last level is reached, the
/// step budget is spent, or a step would raise `Q` (FS once `φ < ε/2`).
fn stagewise(scene: &Scene, b: &Psf, rule: Rule, max_steps: usize, ties: bool) -> PathRun {
    let t0 = Instant::now();
    let q0 = scene.q0;
    let mut r = scene.dirty.clone();
    let mut m = vec![0.0; r.len()];
    let mut q = q0;
    let mut arc = 0.0;
    let mut negative = 0.0;
    let mut snapshots: Vec<Option<Snapshot>> = vec![None; LEVELS.len()];
    let mut level = 0;
    let mut steps = 0;
    let mut drift = 0.0_f64;
    while level < LEVELS.len() && steps < max_steps {
        let (p, rp) = argmax_abs(&r);
        if rp == 0.0 {
            break;
        }
        let h = match rule {
            Rule::Fs(e) => e,
            Rule::Clean(g) => g * rp.abs(),
        };
        let c = h * rp.signum();
        let dq = -h * rp.abs() + 0.5 * h * h;
        if dq >= 0.0 {
            break;
        }
        while level < LEVELS.len() && q + dq <= LEVELS[level] * q0 {
            // Q(t) = q − t h|r_p| + t² h²/2 = target, smaller root in (0, 1].
            let target = LEVELS[level] * q0;
            let (qa, qb, qc) = (0.5 * h * h, h * rp.abs(), q - target);
            let t = ((qb - (qb * qb - 4.0 * qa * qc).max(0.0).sqrt()) / (2.0 * qa)).clamp(0.0, 1.0);
            let mut model = m.clone();
            model[p] += t * c;
            let mut residual = r.clone();
            sub(&mut residual, b, p, t * c);
            let exact = q0 - 0.5 * (dot(&model, &scene.dirty) + dot(&model, &residual));
            drift = drift.max((exact - target).abs() / target);
            let (tied, tied_lambda_min) = if ties {
                let phi = residual.iter().fold(0.0_f64, |a, v| a.max(v.abs()));
                let tied_set: Vec<usize> = (0..residual.len())
                    .filter(|&j| residual[j].abs() >= phi - 2.0 * h)
                    .collect();
                (tied_set.len(), smallest_eigenvalue(b, &tied_set))
            } else {
                (0, f64::NAN)
            };
            snapshots[level] = Some(Snapshot {
                model,
                residual,
                arc: arc + t * h,
                negative_arc: negative + if c < 0.0 { t * h } else { 0.0 },
                steps: steps + 1,
                tied,
                tied_lambda_min,
                q_ratio: exact / q0,
            });
            level += 1;
        }
        m[p] += c;
        sub(&mut r, b, p, c);
        q += dq;
        arc += h;
        if c < 0.0 {
            negative += h;
        }
        steps += 1;
    }
    PathRun {
        snapshots,
        steps,
        seconds: t0.elapsed().as_secs_f64(),
        drift,
    }
}

/// The worst violation of the lasso optimality conditions, relative to `λ`.
fn kkt(lambda: f64, nonneg: bool, m: &[f64], r: &[f64]) -> f64 {
    let mut worst = 0.0_f64;
    for (mp, rp) in m.iter().zip(r) {
        let v = if *mp != 0.0 {
            (rp - lambda * mp.signum()).abs()
        } else if nonneg {
            (rp - lambda).max(0.0)
        } else {
            (rp.abs() - lambda).max(0.0)
        };
        worst = worst.max(v);
    }
    worst / lambda
}

/// A lasso solution at a matched misfit.
struct LassoPoint {
    lambda: f64,
    q_ratio: f64,
    active: usize,
    arc: f64,
    model: Vec<f64>,
    residual: Vec<f64>,
}

/// The exact lasso (or non-negative lasso) path from `λ_max` down to the last
/// level, and what it says about monotonicity.
struct Homotopy {
    matched: Vec<Option<LassoPoint>>,
    events: usize,
    joins: usize,
    drops: usize,
    /// Joins after which the new pixel's coefficient would move against its
    /// sign (a degenerate tie); should be zero.
    wrong_sign_joins: usize,
    /// Segments, before the last level, on which some active coefficient
    /// moves towards zero (`s_j (B_AA⁻¹ s)_j < 0`, HTTW's condition (36)
    /// failing on that active set): the path is not monotone there.
    shrinking_segments: usize,
    first_shrink_q_ratio: f64,
    max_active: usize,
    stop: &'static str,
    seconds: f64,
}

/// Cholesky factor of the Gram matrix of the active pixels, rows of a lower
/// triangle, with appends and Givens-rotation deletions.
struct Cholesky {
    rows: Vec<Vec<f64>>,
}

impl Cholesky {
    /// Append pixel `q` given its Gram column `g` against the active set and
    /// `B_qq`; `false` if the new pivot is not positive (the active atoms
    /// would be linearly dependent to working precision).
    fn push(&mut self, g: &[f64], bqq: f64) -> bool {
        let k = self.rows.len();
        let mut y = vec![0.0; k + 1];
        for i in 0..k {
            let row = &self.rows[i];
            let s: f64 = (0..i).map(|j| row[j] * y[j]).sum();
            y[i] = (g[i] - s) / row[i];
        }
        let d2 = bqq - y[..k].iter().map(|v| v * v).sum::<f64>();
        if d2 <= 1e-10 * bqq {
            return false;
        }
        y[k] = d2.sqrt();
        self.rows.push(y);
        true
    }

    /// Delete position `i` (row and column of the Gram matrix).
    fn remove(&mut self, i: usize) {
        self.rows.remove(i);
        let k = self.rows.len();
        for j in i..k {
            let a = self.rows[j][j];
            let x = self.rows[j][j + 1];
            let r = a.hypot(x);
            let (c, s) = (a / r, x / r);
            for row in &mut self.rows[j..k] {
                let (p, q) = (row[j], row[j + 1]);
                row[j] = c * p + s * q;
                row[j + 1] = -s * p + c * q;
            }
            self.rows[j].truncate(j + 1);
        }
    }

    /// Solve `L Lᵀ w = s`.
    fn solve(&self, s: &[f64]) -> Vec<f64> {
        let k = self.rows.len();
        let mut z = vec![0.0; k];
        for i in 0..k {
            let row = &self.rows[i];
            let acc: f64 = (0..i).map(|j| row[j] * z[j]).sum();
            z[i] = (s[i] - acc) / row[i];
        }
        let mut w = vec![0.0; k];
        for i in (0..k).rev() {
            let mut acc = z[i];
            for (m, row) in self.rows.iter().enumerate().skip(i + 1) {
                acc -= row[i] * w[m];
            }
            w[i] = acc / self.rows[i][i];
        }
        w
    }
}

fn psf_between(b: &Psf, p: usize, q: usize) -> f64 {
    let n = b.n as isize;
    let dx = (p as isize % n) - (q as isize % n);
    let dy = (p as isize / n) - (q as isize / n);
    b.at(dx, dy)
}

/// The smallest eigenvalue of the Gram matrix of `set`: Jacobi for small
/// sets, otherwise inverse power iteration on a Cholesky factor (zero when the
/// factorisation finds the atoms dependent to working precision).
fn smallest_eigenvalue(b: &Psf, set: &[usize]) -> f64 {
    if set.len() <= 60 {
        return min_eigenvalue(&gram(b, set), set.len());
    }
    let mut chol = Cholesky { rows: Vec::new() };
    for (k, &q) in set.iter().enumerate() {
        let g: Vec<f64> = set[..k].iter().map(|&i| psf_between(b, i, q)).collect();
        if !chol.push(&g, b.peak()) {
            return 0.0;
        }
    }
    let mut x: Vec<f64> = (0..set.len()).map(|i| 1.0 + (i % 7) as f64 * 0.1).collect();
    let mut mu = 0.0;
    for _ in 0..300 {
        let norm = x.iter().map(|v| v * v).sum::<f64>().sqrt();
        for v in &mut x {
            *v /= norm;
        }
        let y = chol.solve(&x);
        mu = dot(&x, &y);
        x = y;
    }
    1.0 / mu
}

/// The lasso path by homotopy (Osborne, Presnell and Turlach 2000; Efron et
/// al. 2004, LARS with the lasso modification), exact up to rounding: on a
/// segment with active set `A` and signs `s`, `m_A` moves by `δ B_AA⁻¹ s` and
/// the residual image by `−δ B_{·A} B_AA⁻¹ s` as `λ` falls by `δ`, until a
/// pixel joins (`|r_j| = λ`) or an active coefficient reaches zero. The
/// non-negative lasso is the same with `s = 1` and positive joins only.
/// Matched misfits are located inside the segment that crosses them.
fn homotopy(scene: &Scene, b: &Psf, nonneg: bool) -> Homotopy {
    let t0 = Instant::now();
    let n = scene.dirty.len();
    let d = &scene.dirty;
    let mut c = d.clone();
    let mut beta = vec![0.0; n];
    let mut is_active = vec![false; n];
    let mut active: Vec<usize> = Vec::new();
    let mut signs: Vec<f64> = Vec::new();
    let mut chol = Cholesky { rows: Vec::new() };
    let mut out = Homotopy {
        matched: (0..LEVELS.len()).map(|_| None).collect(),
        events: 0,
        joins: 0,
        drops: 0,
        wrong_sign_joins: 0,
        shrinking_segments: 0,
        first_shrink_q_ratio: f64::NAN,
        max_active: 0,
        stop: "levels",
        seconds: 0.0,
    };
    let (p0, v0) = if nonneg {
        let (p, v) =
            c.iter().enumerate().fold(
                (0, f64::NEG_INFINITY),
                |acc, (p, &v)| if v > acc.1 { (p, v) } else { acc },
            );
        (p, v)
    } else {
        argmax_abs(&c)
    };
    let mut lambda = v0.abs();
    let bpeak = b.peak();
    chol.push(&[], bpeak);
    active.push(p0);
    signs.push(if nonneg { 1.0 } else { v0.signum() });
    is_active[p0] = true;
    out.joins = 1;
    let mut just_joined = Some(p0);
    let mut arc = 0.0;
    let mut level = 0;
    let q0 = scene.q0;
    loop {
        let w = chol.solve(&signs);
        if let Some(j) = just_joined {
            let k = active.iter().position(|&a| a == j).unwrap();
            if w[k] * signs[k] < 0.0 {
                out.wrong_sign_joins += 1;
            }
        }
        let mut u = vec![0.0; n];
        for (k, &i) in active.iter().enumerate() {
            sub(&mut u, b, i, -w[k]);
        }
        let shrinking = active
            .iter()
            .enumerate()
            .any(|(k, _)| w[k] * signs[k] < 0.0);
        // The next event.
        let mut delta = lambda;
        let mut event: Option<(bool, usize, f64)> = None; // (join?, pixel or position, sign)
        for j in 0..n {
            if is_active[j] {
                continue;
            }
            if 1.0 - u[j] > 1e-14 {
                let t = ((lambda - c[j]) / (1.0 - u[j])).max(0.0);
                if t < delta {
                    delta = t;
                    event = Some((true, j, 1.0));
                }
            }
            if !nonneg && 1.0 + u[j] > 1e-14 {
                let t = ((lambda + c[j]) / (1.0 + u[j])).max(0.0);
                if t < delta {
                    delta = t;
                    event = Some((true, j, -1.0));
                }
            }
        }
        for (k, &i) in active.iter().enumerate() {
            if beta[i] != 0.0 && w[k] * beta[i] < 0.0 {
                let t = -beta[i] / w[k];
                if t < delta {
                    delta = t;
                    event = Some((false, k, 0.0));
                }
            }
        }
        // Misfit along the segment: Q(δ) = Q_0 − ½ (β + δw)·(d + r − δu).
        let (mut bd, mut wd, mut bu, mut wu) = (0.0, 0.0, 0.0, 0.0);
        let mut wl1 = 0.0;
        for (k, &i) in active.iter().enumerate() {
            bd += beta[i] * (d[i] + c[i]);
            wd += w[k] * (d[i] + c[i]);
            bu += beta[i] * u[i];
            wu += w[k] * u[i];
            wl1 += w[k].abs();
        }
        let q_at = |t: f64| q0 - 0.5 * (bd + t * (wd - bu) - t * t * wu);
        while level < LEVELS.len() && q_at(delta) <= LEVELS[level] * q0 {
            let target = LEVELS[level] * q0;
            let (mut lo, mut hi) = (0.0, delta);
            for _ in 0..200 {
                let mid = 0.5 * (lo + hi);
                if q_at(mid) > target {
                    lo = mid;
                } else {
                    hi = mid;
                }
            }
            let t = hi;
            let mut model = beta.clone();
            for (k, &i) in active.iter().enumerate() {
                model[i] += t * w[k];
            }
            let residual: Vec<f64> = c.iter().zip(&u).map(|(cj, uj)| cj - t * uj).collect();
            out.matched[level] = Some(LassoPoint {
                lambda: lambda - t,
                q_ratio: q_at(t) / q0,
                active: active.len(),
                arc: arc + t * wl1,
                model,
                residual,
            });
            level += 1;
        }
        if shrinking && level < LEVELS.len() {
            out.shrinking_segments += 1;
            if out.first_shrink_q_ratio.is_nan() {
                out.first_shrink_q_ratio = q_at(0.0) / q0;
            }
        }
        if level == LEVELS.len() {
            break;
        }
        // Advance to the event.
        arc += delta * wl1;
        for (k, &i) in active.iter().enumerate() {
            beta[i] += delta * w[k];
        }
        for (cj, uj) in c.iter_mut().zip(&u) {
            *cj -= delta * uj;
        }
        lambda -= delta;
        out.events += 1;
        just_joined = None;
        match event {
            Some((true, j, sign)) => {
                let g: Vec<f64> = active.iter().map(|&i| psf_between(b, i, j)).collect();
                if !chol.push(&g, bpeak) {
                    out.stop = "singular active Gram";
                    break;
                }
                active.push(j);
                signs.push(if nonneg { 1.0 } else { sign });
                is_active[j] = true;
                out.joins += 1;
                just_joined = Some(j);
            }
            Some((false, k, _)) => {
                let i = active[k];
                beta[i] = 0.0;
                is_active[i] = false;
                active.remove(k);
                signs.remove(k);
                chol.remove(k);
                out.drops += 1;
            }
            None => {
                out.stop = "λ reached zero";
                break;
            }
        }
        out.max_active = out.max_active.max(active.len());
        if out.events > 60_000 {
            out.stop = "event budget";
            break;
        }
    }
    out.seconds = t0.elapsed().as_secs_f64();
    out
}

/// One method's state at one matched level, compared with the FS reference.
fn report_row(
    json: &mut Json,
    label: &str,
    model: &[f64],
    residual: &[f64],
    extra: (f64, f64, usize, f64),
    reference: &Snapshot,
    truth: &[f64],
) {
    let (arc, negative_arc, steps, q_ratio) = extra;
    let dm = rms_diff(model, &reference.model);
    let dr = rms_diff(residual, &reference.residual);
    let truth_rms = rms_diff(model, truth);
    println!(
        "| {label} | {q_ratio:.4e} | {} | {:.3} | {} | {:.4} | {} | {dm:.3e} | {dr:.3e} | {truth_rms:.4} | {steps} |",
        if arc.is_nan() {
            "–".to_string()
        } else {
            format!("{arc:.3}")
        },
        l1(model),
        if arc.is_nan() {
            "–".to_string()
        } else {
            format!("{:.3}", arc - l1(model))
        },
        min_value(model),
        if negative_arc.is_nan() {
            "–".to_string()
        } else {
            format!("{negative_arc:.3}")
        },
    );
    json.item();
    json.text("method", label);
    json.num("q_ratio", q_ratio);
    json.num("arc_length", arc);
    json.num("l1_norm", l1(model));
    json.num("most_negative", min_value(model));
    json.num("negative_arc", negative_arc);
    json.num("rms_model_vs_fs_ref", dm);
    json.num("rms_residual_vs_fs_ref", dr);
    json.num("rms_model_vs_truth", truth_rms);
    json.int("steps", steps);
    json.close();
}

fn run_case(config: &Config, scene: &Scene, b: &Psf, json: &mut Json) {
    let case_t = Instant::now();
    let peak = scene.dirty.iter().fold(0.0_f64, |a, v| a.max(v.abs()));
    println!(
        "\n## {} / {}: Q_0 = {:.4e}, dirty peak {:.4}, truth ℓ1 {:.3}",
        config.name,
        scene.name,
        scene.q0,
        peak,
        l1(&scene.truth)
    );
    json.item();
    json.text("config", config.name);
    json.text("scene", scene.name);
    json.num("q0", scene.q0);
    json.num("dirty_peak", peak);
    json.num("truth_l1", l1(&scene.truth));

    // FS at three increments (the finest is the reference) and CLEAN.
    let mut fs_runs = Vec::new();
    for &fraction in &FS_FRACTIONS {
        let eps = fraction * peak;
        let run = stagewise(scene, b, Rule::Fs(eps), 20_000_000, true);
        println!(
            "FS ε = {fraction:.1e}·peak: {} steps, {:.2} s, misfit drift {:.1e}, levels reached {}",
            run.steps,
            run.seconds,
            run.drift,
            run.snapshots.iter().filter(|s| s.is_some()).count()
        );
        fs_runs.push((fraction, eps, run));
    }
    let mut clean_runs = Vec::new();
    for &gain in &GAINS {
        let run = stagewise(scene, b, Rule::Clean(gain), 5_000_000, false);
        println!(
            "CLEAN γ = {gain}: {} steps, {:.2} s, misfit drift {:.1e}",
            run.steps, run.seconds, run.drift
        );
        clean_runs.push((gain, run));
    }
    // Lasso and non-negative lasso, exact paths by homotopy.
    let lasso = homotopy(scene, b, false);
    let nn = homotopy(scene, b, true);
    for (label, h) in [("lasso", &lasso), ("non-negative lasso", &nn)] {
        println!(
            "{label}: {} events ({} joins, {} drops), max active {}, {:.2} s, stop: {}",
            h.events, h.joins, h.drops, h.max_active, h.seconds, h.stop
        );
    }

    json.open_list("fs_runs");
    for (fraction, eps, run) in &fs_runs {
        json.item();
        json.num("fraction_of_peak", *fraction);
        json.num("epsilon", *eps);
        json.int("steps", run.steps);
        json.num("seconds", run.seconds);
        json.num("misfit_drift", run.drift);
        json.close();
    }
    json.close_list();
    json.open_list("clean_runs");
    for (gain, run) in &clean_runs {
        json.item();
        json.num("gain", *gain);
        json.int("steps", run.steps);
        json.num("seconds", run.seconds);
        json.num("misfit_drift", run.drift);
        json.close();
    }
    json.close_list();

    json.open_list("levels");
    for (li, &level) in LEVELS.iter().enumerate() {
        let Some(reference) = fs_runs[0].2.snapshots[li].clone() else {
            println!("level {level}: FS reference did not reach it");
            continue;
        };
        let coarse = fs_runs[1].2.snapshots[li].as_ref();
        println!(
            "\nQ/Q_0 = {level}: FS reference arc length {:.4}, tied pixels {} (λ_min of their Gram {:.3e}); at 4ε: {} ({:.3e})",
            reference.arc,
            reference.tied,
            reference.tied_lambda_min,
            coarse.map(|c| c.tied).unwrap_or(0),
            coarse.map(|c| c.tied_lambda_min).unwrap_or(f64::NAN)
        );
        println!(
            "| method | Q/Q_0 | arc length L | ‖m‖₁ | L − ‖m‖₁ | most negative | negative arc | rms(m − m_FS) | rms(r − r_FS) | rms(m − truth) | steps |"
        );
        println!("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |");
        json.item();
        json.num("level", level);
        json.int("fs_tied", reference.tied);
        json.num("fs_tied_lambda_min", reference.tied_lambda_min);
        json.int("fs_4eps_tied", coarse.map(|c| c.tied).unwrap_or(0));
        json.num(
            "fs_4eps_tied_lambda_min",
            coarse.map(|c| c.tied_lambda_min).unwrap_or(f64::NAN),
        );
        json.open_list("rows");
        for (fraction, _, run) in &fs_runs {
            if let Some(s) = &run.snapshots[li] {
                report_row(
                    json,
                    &format!("FS ε={fraction:.1e}·peak"),
                    &s.model,
                    &s.residual,
                    (s.arc, s.negative_arc, s.steps, s.q_ratio),
                    &reference,
                    &scene.truth,
                );
            }
        }
        for (gain, run) in &clean_runs {
            if let Some(s) = &run.snapshots[li] {
                report_row(
                    json,
                    &format!("CLEAN γ={gain}"),
                    &s.model,
                    &s.residual,
                    (s.arc, s.negative_arc, s.steps, s.q_ratio),
                    &reference,
                    &scene.truth,
                );
            }
        }
        for (label, result, nonneg) in [("lasso", &lasso, false), ("non-negative lasso", &nn, true)]
        {
            if let Some(point) = &result.matched[li] {
                let violation = kkt(point.lambda, nonneg, &point.model, &point.residual);
                report_row(
                    json,
                    &format!(
                        "{label} (λ={:.3e}, |A|={}, KKT {:.0e})",
                        point.lambda, point.active, violation
                    ),
                    &point.model,
                    &point.residual,
                    (point.arc, f64::NAN, 0, point.q_ratio),
                    &reference,
                    &scene.truth,
                );
            }
        }
        json.close_list();
        json.close();
    }
    json.close_list();

    // Convergence summary: distance to the FS reference against γ, and the
    // log-log slope between γ = 0.03 and γ = 0.003.
    println!(
        "
convergence to the FS reference: rms(m − m_FS) / rms(r − r_FS)"
    );
    println!(
        "| Q/Q_0 | γ=1 | γ=0.3 | γ=0.1 | γ=0.03 | γ=0.01 | γ=0.003 | slope, model | slope, residual | FS 4ε | FS 16ε |"
    );
    println!("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |");
    json.open_list("convergence");
    for (li, &level) in LEVELS.iter().enumerate() {
        let Some(reference) = fs_runs[0].2.snapshots[li].as_ref() else {
            continue;
        };
        let pair = |s: Option<&Snapshot>| {
            s.map(|s| {
                (
                    rms_diff(&s.model, &reference.model),
                    rms_diff(&s.residual, &reference.residual),
                )
            })
            .unwrap_or((f64::NAN, f64::NAN))
        };
        let clean: Vec<(f64, f64)> = clean_runs
            .iter()
            .map(|(_, run)| pair(run.snapshots[li].as_ref()))
            .collect();
        let slope = |a: f64, b: f64| (a / b).ln() / (0.03f64 / 0.003).ln();
        let slope_m = slope(clean[3].0, clean[5].0);
        let slope_r = slope(clean[3].1, clean[5].1);
        let fs4 = pair(fs_runs[1].2.snapshots[li].as_ref());
        let fs16 = pair(fs_runs[2].2.snapshots[li].as_ref());
        let mut line = format!("| {level:e} |");
        for (m, r) in &clean {
            let _ = write!(line, " {m:.2e} / {r:.2e} |");
        }
        let _ = write!(
            line,
            " {slope_m:.2} | {slope_r:.2} | {:.2e} / {:.2e} | {:.2e} / {:.2e} |",
            fs4.0, fs4.1, fs16.0, fs16.1
        );
        println!("{line}");
        json.item();
        json.num("level", level);
        json.open_list("gains");
        for (k, (m, r)) in clean.iter().enumerate() {
            json.item();
            json.num("gain", GAINS[k]);
            json.num("rms_model", *m);
            json.num("rms_residual", *r);
            json.close();
        }
        json.close_list();
        json.num("slope_model_0_03_to_0_003", slope_m);
        json.num("slope_residual_0_03_to_0_003", slope_r);
        json.num("fs_4eps_rms_model", fs4.0);
        json.num("fs_4eps_rms_residual", fs4.1);
        json.num("fs_16eps_rms_model", fs16.0);
        json.num("fs_16eps_rms_residual", fs16.1);
        json.close();
    }
    json.close_list();

    // Is the lasso path monotone here? (Then lasso and monotone lasso agree.)
    println!(
        "
lasso path monotonicity down to Q/Q_0 = {} (exact path)",
        LEVELS[LEVELS.len() - 1]
    );
    println!(
        "| path | events | joins | drops (zero crossings) | segments with a shrinking coefficient | first at Q/Q_0 | arc / ‖m‖₁ at the last level | wrong-sign joins | stop |"
    );
    println!("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |");
    json.open_list("monotonicity");
    for (label, h) in [("lasso", &lasso), ("non-negative lasso", &nn)] {
        let ratio = h.matched[LEVELS.len() - 1]
            .as_ref()
            .map(|p| p.arc / l1(&p.model))
            .unwrap_or(f64::NAN);
        println!(
            "| {label} | {} | {} | {} | {} | {:.3e} | {ratio:.4} | {} | {} |",
            h.events,
            h.joins,
            h.drops,
            h.shrinking_segments,
            h.first_shrink_q_ratio,
            h.wrong_sign_joins,
            h.stop
        );
        json.item();
        json.text("path", label);
        json.int("events", h.events);
        json.int("joins", h.joins);
        json.int("drops", h.drops);
        json.int("shrinking_segments", h.shrinking_segments);
        json.num("first_shrink_q_ratio", h.first_shrink_q_ratio);
        json.num("arc_over_norm_at_last_level", ratio);
        json.int("wrong_sign_joins", h.wrong_sign_joins);
        json.int("max_active", h.max_active);
        json.num("seconds", h.seconds);
        json.text("stop", h.stop);
        json.boolean("monotone", h.drops == 0 && h.shrinking_segments == 0);
        json.close();
    }
    json.close_list();
    json.num("case_seconds", case_t.elapsed().as_secs_f64());
    json.close();
    println!("case {:.1} s", case_t.elapsed().as_secs_f64());
}

fn main() {
    let outdir = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "outputs/clean-implicit".to_string());
    std::fs::create_dir_all(&outdir).expect("output directory");
    let started = Instant::now();
    let grid = Grid { n: N, cell: CELL };
    let configs = [
        Config {
            name: "track-uniform",
            hours: (0..13).map(|i| -2.0 + i as f64 / 3.0).collect(),
            uniform: true,
        },
        Config {
            name: "snapshot-natural",
            hours: vec![0.0],
            uniform: false,
        },
    ];
    let mut json = Json(String::from("{ "));
    json.text("date", "2026-10-30");
    json.int("n", N);
    json.num("cell_rad", CELL);
    json.num("frequency_hz", FREQUENCY);
    json.num("declination_deg", DECLINATION_DEG);
    json.open_list("levels");
    for level in LEVELS {
        let _ = write!(json.0, "{level:e}, ");
    }
    json.close_list();
    json.open_list("cases");
    for config in &configs {
        let s = sampling(config, &grid);
        let b = psf(&s, &grid);
        println!(
            "\n# {}: {} visibilities, PSF peak {:.6}, coherence {:.4}",
            config.name,
            s.len(),
            b.peak(),
            b.coherence()
        );
        let scenes = [
            make_scene("disc-fwhm12", disc(&grid), &b),
            make_scene("six-sources", six_sources(&grid, config.name), &b),
        ];
        for scene in &scenes {
            run_case(config, scene, &b, &mut json);
        }
    }
    json.close_list();
    json.num("total_seconds", started.elapsed().as_secs_f64());
    let text = json.finish();
    std::fs::write(format!("{outdir}/clean-implicit-objective.json"), text).expect("write json");
    println!("\ntotal {:.1} s", started.elapsed().as_secs_f64());
}
