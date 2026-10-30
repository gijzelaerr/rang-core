//! The measured half of `research/clean-phase-transition.md`: when does
//! Högbom CLEAN recover point sources exactly, as a function of source
//! count, separation, sidelobes and uv coverage, on four real arrays.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Run from the repository root:
//! `cargo run --release --manifest-path core/Cargo.toml --example clean_phase_transition -- OUTDIR [TRIALS]`.
//! Writes `OUTDIR/clean-phase-transition.json` and prints the tables of the
//! note. `TRIALS` (default 100) is the number of trials per cell.
//!
//! For each array (MeerKAT, VLA-C, WSRT, KAT-7) × coverage (snapshot, 4 h
//! track) × weighting (natural, uniform): the PSF, its sidelobe profile
//! `μ_d`, bounds on the separated sums `Σ_d(k)` that enter the new
//! sufficient condition, the closed-form two-source scan, and recovery
//! trials for k ∈ {2, 4, 8, 16, 32} and minimum separations
//! d ∈ {1, 2, 3, 4, 6, 8, 12, 16, 24}: noiseless with gain 1, and with 1 %
//! image noise and gain 0.1, on the same source configurations. Every trial
//! is seeded from (configuration, k, d, trial), so the run is deterministic
//! under rayon.

use rang_core::clean::{
    CleanSettings, Grid, Psf, Sampling, SupportCoefficients, Vis, anchored_bound, argmax_abs,
    convolve, dirty, hogbom, psf, separated_sums, support_coefficients,
};
use rayon::prelude::*;
use std::f64::consts::PI;
use std::fmt::Write as _;
use std::time::Instant;

const C: f64 = 299_792_458.0;
const N: usize = 64;
const KS: [usize; 5] = [2, 4, 8, 16, 32];
const DS: [usize; 9] = [1, 2, 3, 4, 6, 8, 12, 16, 24];
/// Separations scanned for the predicted transitions (μ_d is defined to 32).
const D_SCAN: usize = 32;
/// Pixels per fringe of the longest projected baseline over the track,
/// for every array but MeerKAT, which keeps the 2″ cell of `clean_theory`.
const PX_PER_FRINGE: f64 = 2.8;
const NOISE_REALISATIONS: usize = 8;
const SIGMA_IMAGE: f64 = 0.01;
const MAX_STEPS: usize = 20_000;

struct ArrayDef {
    name: &'static str,
    table: &'static str,
    declination_deg: f64,
    frequency_hz: f64,
    fixed_cell: Option<f64>,
}

fn arrays() -> Vec<ArrayDef> {
    vec![
        ArrayDef {
            name: "meerkat",
            table: include_str!("../../data/meerkat.itrf.txt"),
            declination_deg: -30.0,
            frequency_hz: 1.4e9,
            fixed_cell: Some(2.0 / 3600.0 * PI / 180.0),
        },
        ArrayDef {
            name: "vla-c",
            table: include_str!("../../data/vla-c.itrf.txt"),
            declination_deg: 40.0,
            frequency_hz: 1.4e9,
            fixed_cell: None,
        },
        ArrayDef {
            name: "wsrt",
            table: include_str!("../../data/wsrt.itrf.txt"),
            declination_deg: 60.0,
            frequency_hz: 1.4e9,
            fixed_cell: None,
        },
        ArrayDef {
            name: "kat7",
            table: include_str!("../../data/kat7.itrf.txt"),
            declination_deg: -30.0,
            frequency_hz: 1.4e9,
            fixed_cell: None,
        },
    ]
}

/// ITRF positions (metres) from a simms-format table; `#` lines are skipped.
fn antennas(table: &str) -> Vec<[f64; 3]> {
    table
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
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

/// ITRF to east-north-up about the array centroid, as in `clean_theory`.
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

fn track_hours() -> Vec<f64> {
    (0..13).map(|i| -2.0 + i as f64 / 3.0).collect()
}

/// Unweighted (u, v) samples in wavelengths for the given hour angles.
fn raw_uv(array: &ArrayDef, hours: &[f64]) -> Sampling {
    let (positions, lat) = enu(&antennas(array.table));
    let dec = array.declination_deg.to_radians();
    let scale = array.frequency_hz / C;
    let mut s = Sampling::default();
    for &hour in hours {
        let ha = hour * PI / 12.0;
        for p in 0..positions.len() {
            for q in p + 1..positions.len() {
                let d = [
                    positions[p][0] - positions[q][0],
                    positions[p][1] - positions[q][1],
                    positions[p][2] - positions[q][2],
                ];
                let (u, v) = uv(d[0], d[1], d[2], lat, ha, dec);
                s.u.push(u * scale);
                s.v.push(v * scale);
                s.w.push(1.0);
            }
        }
    }
    s
}

/// Natural or uniform weights (uniform: one over the count in the uv cell
/// of this image, Hermitian pairs counted once, as in `clean_theory`).
fn weighted(mut s: Sampling, grid: &Grid, uniform: bool) -> Sampling {
    if uniform {
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

/// splitmix64: per-trial seeds from (configuration, k, d, trial).
fn splitmix(mut z: u64) -> u64 {
    z = z.wrapping_add(0x9E37_79B9_7F4A_7C15);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

/// xorshift64* with Box–Muller normals, as in `clean_theory`.
struct Rng(u64);

impl Rng {
    fn seeded(seed: u64) -> Rng {
        Rng(splitmix(seed) | 1)
    }

    fn uniform(&mut self) -> f64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0.wrapping_mul(0x2545_F491_4F6C_DD1D) >> 11) as f64 / (1u64 << 53) as f64
    }

    fn normal(&mut self) -> f64 {
        let u1 = self.uniform().max(1e-300);
        let u2 = self.uniform();
        (-2.0 * u1.ln()).sqrt() * (2.0 * PI * u2).cos()
    }

    fn below(&mut self, n: usize) -> usize {
        ((self.uniform() * n as f64) as usize).min(n - 1)
    }
}

/// Hand-written JSON, as the crate has no serialiser (same helper as
/// `clean_theory`).
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
    fn opts(&mut self, name: &str, values: &[Option<usize>]) {
        self.key(name);
        self.0.push_str("[ ");
        for v in values {
            match v {
                Some(d) => {
                    let _ = write!(self.0, "{d}, ");
                }
                None => self.0.push_str("null, "),
            }
        }
        self.trim_comma();
        self.0.push_str(" ], ");
    }
    fn boolean(&mut self, name: &str, value: bool) {
        self.key(name);
        let _ = write!(self.0, "{value}, ");
    }
    fn text(&mut self, name: &str, value: &str) {
        self.key(name);
        let _ = write!(self.0, "\"{value}\", ");
    }
    fn nums(&mut self, name: &str, values: &[f64]) {
        self.key(name);
        self.0.push_str("[ ");
        for v in values {
            if v.is_finite() {
                let _ = write!(self.0, "{v:e}, ");
            } else {
                self.0.push_str("null, ");
            }
        }
        self.trim_comma();
        self.0.push_str(" ], ");
    }
    fn ints(&mut self, name: &str, values: &[usize]) {
        self.key(name);
        self.0.push_str("[ ");
        for v in values {
            let _ = write!(self.0, "{v}, ");
        }
        self.trim_comma();
        self.0.push_str(" ], ");
    }
    fn open_list(&mut self, name: &str) {
        self.key(name);
        self.0.push_str("[ ");
    }
    fn open_object(&mut self, name: &str) {
        self.key(name);
        self.0.push_str("{ ");
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

/// The two-source closed form scanned over every pair offset `Δ` of the
/// grid, with every competitor `q` whose offsets to both sources lie in the
/// PSF table (a superset of the pixels of any real 64 × 64 placement, so a
/// pass here is a pass in the image).
struct PairScan {
    /// Smallest d such that every pair at Chebyshev separation ≥ d passes
    /// both the flux-free rule and the first pick for all 81 flux pairs.
    d_worst: usize,
    /// The same for the flux-free rule `max(|a − ρc|, |c − ρa|) < 1 − ρ²` only.
    d_worst_later: usize,
    /// The same for the first pick only.
    d_worst_first: usize,
    /// Smallest d such that every pair at separation ≥ d has ERC < 1
    /// (`(|a − ρc| + |c − ρa|) / (1 − ρ²) < 1` for every competitor).
    d_worst_erc: usize,
    /// Predicted success at minimum separation d (index d, 1..=D_SCAN) for
    /// uniformly placed pairs and fluxes on the 9 × 9 grid of [0.2, 1].
    predicted: Vec<f64>,
    /// The same at separation exactly d.
    predicted_exact: Vec<f64>,
}

/// Per pair offset: (Chebyshev separation, later picks pass, passing flux
/// pairs, placement weight, ERC < 1).
type PairRow = (usize, bool, usize, f64, bool);

fn pair_scan(b: &Psf) -> PairScan {
    let off = (b.n - 1) as isize;
    let peak = b.peak();
    let fluxes: Vec<f64> = (0..9).map(|i| 0.2 + 0.1 * i as f64).collect();
    let mut ratios: Vec<f64> = Vec::new();
    for &f1 in &fluxes {
        for &f2 in &fluxes {
            let t = f2 / f1;
            if !ratios.iter().any(|&r| (r - t).abs() < 1e-12) {
                ratios.push(t);
            }
        }
    }
    let pairs: Vec<(f64, f64, usize)> = fluxes
        .iter()
        .flat_map(|&f1| {
            let ratios = &ratios;
            fluxes.iter().map(move |&f2| {
                let t = f2 / f1;
                let idx = ratios.iter().position(|&r| (r - t).abs() < 1e-12).unwrap();
                (f1, f2, idx)
            })
        })
        .collect();
    // Half plane of offsets: Δ and −Δ describe the same pair (the flux grid
    // is symmetric under swapping the two sources).
    let mut deltas = Vec::new();
    for ey in 0..=off {
        for ex in -off..=off {
            if ey > 0 || ex > 0 {
                deltas.push((ex, ey));
            }
        }
    }
    // Per Δ: (Chebyshev separation, later-picks pass, passing flux pairs,
    // weight, ERC < 1).
    let rows: Vec<PairRow> = deltas
        .par_iter()
        .map(|&(ex, ey)| {
            let rho = b.at(ex, ey) / peak;
            let mut later = 0.0_f64;
            let mut erc = 0.0_f64;
            let mut rhs = vec![0.0_f64; ratios.len()];
            for qy in (-off).max(ey - off)..=off.min(ey + off) {
                for qx in (-off).max(ex - off)..=off.min(ex + off) {
                    if (qx == 0 && qy == 0) || (qx == ex && qy == ey) {
                        continue;
                    }
                    let a = b.at(qx, qy) / peak;
                    let c = b.at(qx - ex, qy - ey) / peak;
                    let (x1, x2) = ((a - rho * c).abs(), (c - rho * a).abs());
                    later = later.max(x1).max(x2);
                    erc = erc.max(x1 + x2);
                    for (r, &t) in rhs.iter_mut().zip(&ratios) {
                        *r = r.max((a + c * t).abs());
                    }
                }
            }
            let later_ok = rho.abs() < 1.0 && later < 1.0 - rho * rho;
            let erc_ok = rho.abs() < 1.0 && erc < 1.0 - rho * rho;
            let first_ok = pairs
                .iter()
                .filter(|&&(f1, f2, idx)| {
                    let lhs = (f1 + rho * f2).abs().max((rho * f1 + f2).abs());
                    lhs > f1 * rhs[idx]
                })
                .count();
            let cheb = ex.unsigned_abs().max(ey.unsigned_abs());
            let weight = ((b.n as isize - ex.abs()) * (b.n as isize - ey.abs())) as f64;
            (cheb, later_ok, first_ok, weight, erc_ok)
        })
        .collect();
    let total_pairs = pairs.len();
    let worst = |fail: &dyn Fn(&PairRow) -> bool| {
        rows.iter()
            .filter(|r| fail(r))
            .map(|r| r.0 + 1)
            .max()
            .unwrap_or(1)
    };
    let d_worst = worst(&|r| !r.1 || r.2 < total_pairs);
    let d_worst_later = worst(&|r| !r.1);
    let d_worst_first = worst(&|r| r.2 < total_pairs);
    let d_worst_erc = worst(&|r| !r.4);
    let average = |keep: &dyn Fn(usize) -> bool| {
        let mut num = 0.0;
        let mut den = 0.0;
        for r in rows.iter().filter(|r| keep(r.0)) {
            den += r.3;
            if r.1 {
                num += r.3 * r.2 as f64 / total_pairs as f64;
            }
        }
        if den > 0.0 { num / den } else { f64::NAN }
    };
    let predicted: Vec<f64> = (0..=D_SCAN)
        .map(|d| {
            if d == 0 {
                f64::NAN
            } else {
                average(&|c| c >= d)
            }
        })
        .collect();
    let predicted_exact: Vec<f64> = (0..=D_SCAN)
        .map(|d| {
            if d == 0 {
                f64::NAN
            } else {
                average(&|c| c == d)
            }
        })
        .collect();
    PairScan {
        d_worst,
        d_worst_later,
        d_worst_first,
        d_worst_erc,
        predicted,
        predicted_exact,
    }
}

/// Bounds per separation d (index 1..=D_SCAN) and source count (index into KS).
struct Conditions {
    mu: Vec<f64>,
    /// Σ_out upper/lower (m = k) and Σ_in upper/lower (m = k − 1).
    out_upper: Vec<[f64; 5]>,
    out_lower: Vec<[f64; 5]>,
    in_upper: Vec<[f64; 5]>,
    in_lower: Vec<[f64; 5]>,
    /// Greedy configuration sizes for the off-support sum (diagnostic).
    out_placed: Vec<usize>,
    /// The anchored bound of Theorem 8 (`clean::anchored_bound`).
    anchored: Vec<[f64; 5]>,
}

impl Conditions {
    fn anchored(&self, d: usize, ki: usize) -> f64 {
        self.anchored[d][ki]
    }
    fn new_upper(&self, d: usize, ki: usize) -> f64 {
        self.out_upper[d][ki] + self.in_upper[d][ki]
    }
    fn new_lower(&self, d: usize, ki: usize) -> f64 {
        self.out_lower[d][ki] + self.in_lower[d][ki]
    }
    /// Proposition 4': μ_1 + (k − 1)(μ_⌈d/2⌉ + μ_d); at d = 1 it is the
    /// coherence condition (2k − 1)μ < 1 of Theorem 4.
    fn prop4(&self, d: usize, ki: usize) -> f64 {
        let k = KS[ki] as f64;
        self.mu[1] + (k - 1.0) * (self.mu[d.div_ceil(2)] + self.mu[d])
    }
    /// Smallest d in 1..=D_SCAN with `value(d) < 1`.
    fn first_below(&self, ki: usize, value: impl Fn(&Self, usize, usize) -> f64) -> Option<usize> {
        (1..=D_SCAN).find(|&d| value(self, d, ki) < 1.0)
    }
}

fn conditions(b: &Psf) -> Conditions {
    let mu: Vec<f64> = (0..=D_SCAN)
        .map(|d| if d == 0 { 1.0 } else { b.outside_patch(d - 1) })
        .collect();
    let per_d: Vec<_> = (1..=D_SCAN)
        .into_par_iter()
        .map(|d| {
            let out = separated_sums(b, d, 32, false);
            let inn = separated_sums(b, d, 31, true);
            let anc = anchored_bound(b, d, 32);
            let mut ou = [0.0; 5];
            let mut ol = [0.0; 5];
            let mut iu = [0.0; 5];
            let mut il = [0.0; 5];
            let mut an = [0.0; 5];
            for (ki, &k) in KS.iter().enumerate() {
                ou[ki] = out.upper[k];
                ol[ki] = out.lower[k];
                iu[ki] = inn.upper[k - 1];
                il[ki] = inn.lower[k - 1];
                an[ki] = anc[k];
            }
            (ou, ol, iu, il, out.placed, an)
        })
        .collect();
    let mut c = Conditions {
        mu,
        out_upper: vec![[0.0; 5]],
        out_lower: vec![[0.0; 5]],
        in_upper: vec![[0.0; 5]],
        in_lower: vec![[0.0; 5]],
        out_placed: vec![0],
        anchored: vec![[f64::INFINITY; 5]],
    };
    for (ou, ol, iu, il, placed, an) in per_d {
        c.out_upper.push(ou);
        c.out_lower.push(ol);
        c.in_upper.push(iu);
        c.in_lower.push(il);
        c.out_placed.push(placed);
        c.anchored.push(an);
    }
    // The new condition is never weaker than Proposition 4' (term by term).
    for d in 1..=D_SCAN {
        for (ki, &k) in KS.iter().enumerate() {
            assert!(
                c.new_upper(d, ki) <= c.prop4(d, ki) + 1e-12,
                "tile bound above the counting bound at d {d}, k {}",
                k
            );
            assert!(
                c.new_upper(d, ki) >= 1.0 || c.anchored(d, ki) < 1.0,
                "anchored bound weaker than the separated-sum condition at d {d}, k {}",
                k
            );
        }
    }
    c
}

/// Random positions at pairwise Chebyshev separation ≥ d by random
/// sequential placement with restarts; `None` when it does not succeed.
fn place(rng: &mut Rng, k: usize, d: usize) -> Option<Vec<usize>> {
    for _restart in 0..20 {
        let mut support: Vec<usize> = Vec::with_capacity(k);
        for _draw in 0..400 * k {
            let p = rng.below(N * N);
            let far = support.iter().all(|&q| {
                let dx = (p % N) as isize - (q % N) as isize;
                let dy = (p / N) as isize - (q / N) as isize;
                dx.abs().max(dy.abs()) as usize >= d.max(1)
            });
            if far {
                support.push(p);
                if support.len() == k {
                    return Some(support);
                }
            }
        }
    }
    None
}

fn min_separation(support: &[usize]) -> usize {
    let mut best = usize::MAX;
    for (i, &p) in support.iter().enumerate() {
        for &q in &support[i + 1..] {
            let dx = (p % N) as isize - (q % N) as isize;
            let dy = (p / N) as isize - (q / N) as isize;
            best = best.min(dx.abs().max(dy.abs()) as usize);
        }
    }
    best
}

#[derive(Clone)]
struct Trial {
    min_sep: usize,
    coeff: Option<SupportCoefficients>,
    // Noiseless, gain 1.
    first_pick_on: bool,
    on_support: bool,
    first_off: Option<usize>,
    capped: bool,
    success: bool,
    k2_predicted: Option<bool>,
    // 1 % noise, gain 0.1, stop at 5σ.
    noisy_exact: bool,
    noisy_found_all: bool,
    noisy_fraction: f64,
    noisy_false: usize,
    noisy_capped: bool,
}

impl Trial {
    fn eta(&self) -> f64 {
        self.coeff.map(|c| c.eta).unwrap_or(f64::INFINITY)
    }
    fn eta_gain_one(&self) -> f64 {
        self.coeff.map(|c| c.eta_gain_one).unwrap_or(f64::INFINITY)
    }
    fn cross(&self) -> f64 {
        self.coeff.map(|c| c.cross).unwrap_or(f64::INFINITY)
    }
    fn gershgorin(&self) -> f64 {
        self.coeff
            .map(|c| c.cross + c.radius)
            .unwrap_or(f64::INFINITY)
    }
    fn radius(&self) -> f64 {
        self.coeff.map(|c| c.radius).unwrap_or(f64::INFINITY)
    }
}

/// One trial on one support: noiseless gain-1 CLEAN and noisy gain-0.1
/// CLEAN on the same sources.
fn run_trial(
    b: &Psf,
    grid: &Grid,
    noise: &[Vec<f64>],
    k: usize,
    d: usize,
    seed: u64,
) -> Option<Trial> {
    let mut rng = Rng::seeded(seed);
    let support = place(&mut rng, k, d)?;
    let mut truth = vec![0.0; grid.pixels()];
    for &p in &support {
        truth[p] = 0.2 + 0.8 * rng.uniform();
    }
    let coeff = support_coefficients(b, grid, &support);
    let clean = convolve(b, &truth);
    let first_pick_on = support.contains(&argmax_abs(&clean).0);
    let run = hogbom(
        &clean,
        b,
        &CleanSettings {
            gain: 1.0,
            iterations: MAX_STEPS,
            threshold: 1e-9,
            patch: None,
        },
    );
    let first_off = run.steps.iter().position(|st| !support.contains(&st.pixel));
    let on_support = first_off.is_none();
    let capped = run.steps.len() == MAX_STEPS;
    let close = run
        .model
        .iter()
        .zip(&truth)
        .all(|(m, t)| (m - t).abs() < 1e-6);
    let k2_predicted = if k == 2 {
        coeff.map(|c| first_pick_on && c.eta_max < 1.0)
    } else {
        None
    };
    // Noise: a random 64 × 64 window of a 128 × 128 dirty-noise realisation
    // (stationary, so every window is a valid realisation).
    let which = rng.below(noise.len());
    let ox = rng.below(N + 1);
    let oy = rng.below(N + 1);
    let big = &noise[which];
    let mut noisy = clean;
    for y in 0..N {
        for x in 0..N {
            noisy[x + N * y] += big[(x + ox) + 2 * N * (y + oy)];
        }
    }
    let nrun = hogbom(
        &noisy,
        b,
        &CleanSettings {
            gain: 0.1,
            iterations: MAX_STEPS,
            threshold: 5.0 * SIGMA_IMAGE,
            patch: None,
        },
    );
    let on = nrun
        .steps
        .iter()
        .filter(|st| support.contains(&st.pixel))
        .count();
    let found_all = support.iter().all(|&p| nrun.model[p] != 0.0);
    let false_pixels = nrun
        .model
        .iter()
        .enumerate()
        .filter(|&(p, &v)| v != 0.0 && !support.contains(&p))
        .count();
    Some(Trial {
        min_sep: min_separation(&support),
        coeff,
        first_pick_on,
        on_support,
        first_off,
        capped,
        success: on_support && close,
        k2_predicted,
        noisy_exact: found_all && false_pixels == 0,
        noisy_found_all: found_all,
        noisy_fraction: on as f64 / nrun.steps.len().max(1) as f64,
        noisy_false: false_pixels,
        noisy_capped: nrun.steps.len() == MAX_STEPS,
    })
}

/// Separations of the two-source experiment at exactly `d`.
const PAIR_DS: usize = 16;

/// Outcome of a two-source trial at Chebyshev separation exactly `d`:
/// (success, on support, two-source rule prediction, ERC < 1).
fn run_pair(b: &Psf, grid: &Grid, d: usize, seed: u64) -> (bool, bool, bool, bool) {
    let mut rng = Rng::seeded(seed);
    let ring: Vec<(isize, isize)> = {
        let di = d as isize;
        let mut v = Vec::new();
        for y in -di..=di {
            for x in -di..=di {
                if x.abs().max(y.abs()) == di {
                    v.push((x, y));
                }
            }
        }
        v
    };
    // First source uniform, offset uniform on the ring, rejected if the
    // second falls outside: the placement weights of `pair_scan`.
    let (p1, p2) = loop {
        let p1 = rng.below(N * N);
        let (ex, ey) = ring[rng.below(ring.len())];
        let x = (p1 % N) as isize + ex;
        let y = (p1 / N) as isize + ey;
        if (0..N as isize).contains(&x) && (0..N as isize).contains(&y) {
            break (p1, x as usize + N * y as usize);
        }
    };
    let support = [p1, p2];
    let mut truth = vec![0.0; grid.pixels()];
    for &p in &support {
        truth[p] = 0.2 + 0.8 * rng.uniform();
    }
    let clean = convolve(b, &truth);
    let first_pick_on = support.contains(&argmax_abs(&clean).0);
    let coeff = support_coefficients(b, grid, &support);
    let run = hogbom(
        &clean,
        b,
        &CleanSettings {
            gain: 1.0,
            iterations: MAX_STEPS,
            threshold: 1e-9,
            patch: None,
        },
    );
    let on = run.steps.iter().all(|st| support.contains(&st.pixel));
    let close = run
        .model
        .iter()
        .zip(&truth)
        .all(|(m, t)| (m - t).abs() < 1e-6);
    let predicted = coeff.is_some_and(|c| first_pick_on && c.eta_max < 1.0);
    let erc_ok = coeff.is_some_and(|c| c.eta < 1.0);
    (on && close, on, predicted, erc_ok)
}

/// Aggregates of one (configuration, k, d) cell.
#[derive(Default, Clone)]
struct Cell {
    feasible: bool,
    placed: usize,
    success: usize,
    on_support: usize,
    capped: usize,
    first_pick_failures: usize,
    erc: usize,
    gershgorin: usize,
    gain_one: usize,
    k2_agree: usize,
    k2_total: usize,
    median_eta: f64,
    median_cross: f64,
    min_sep_min: usize,
    noisy_exact: usize,
    noisy_found_all: usize,
    noisy_fraction: f64,
    noisy_false: f64,
    noisy_capped: usize,
}

fn median(mut v: Vec<f64>) -> f64 {
    if v.is_empty() {
        return f64::NAN;
    }
    v.sort_by(|a, b| a.total_cmp(b));
    v[v.len() / 2]
}

/// One pooled per-trial record for the collapse analysis.
struct Record {
    config: usize,
    array: usize,
    success: bool,
    stats: [f64; 8],
}

const STAT_NAMES: [&str; 8] = [
    "eta",
    "eta_gain_one",
    "cross",
    "gershgorin",
    "cell_separated_sum_bound",
    "cell_anchored_bound",
    "radius",
    "cell_in_support_bound",
];
const EDGES: [f64; 17] = [
    0.0,
    0.2,
    0.4,
    0.6,
    0.7,
    0.8,
    0.9,
    1.0,
    1.1,
    1.25,
    1.5,
    2.0,
    3.0,
    5.0,
    10.0,
    100.0,
    f64::INFINITY,
];

fn bin_of(x: f64) -> usize {
    // Infinite values (singular B_SS) go to the last bin.
    let mut i = 0;
    while i + 2 < EDGES.len() && x >= EDGES[i + 1] {
        i += 1;
    }
    i
}

/// Logistic regression of success on ln(statistic) by Newton's method;
/// returns (a, b, converged) with P(success) = 1 / (1 + exp(−a − b ln x)).
fn logistic(points: &[(f64, bool)]) -> (f64, f64, bool) {
    let successes = points.iter().filter(|p| p.1).count();
    if successes == 0 || successes == points.len() {
        return (f64::NAN, f64::NAN, false);
    }
    let xs: Vec<(f64, f64)> = points
        .iter()
        .map(|&(x, y)| (x.clamp(1e-3, 1e6).ln(), if y { 1.0 } else { 0.0 }))
        .collect();
    let (mut a, mut b) = (0.0_f64, 0.0_f64);
    for _ in 0..200 {
        let (mut g0, mut g1, mut h00, mut h01, mut h11) = (0.0, 0.0, 1e-9, 0.0, 1e-9);
        for &(x, y) in &xs {
            let p = 1.0 / (1.0 + (-(a + b * x)).exp());
            g0 += y - p;
            g1 += (y - p) * x;
            let w = p * (1.0 - p);
            h00 += w;
            h01 += w * x;
            h11 += w * x * x;
        }
        let det = h00 * h11 - h01 * h01;
        let da = (h11 * g0 - h01 * g1) / det;
        let db = (h00 * g1 - h01 * g0) / det;
        a += da;
        b += db;
        if da.abs() + db.abs() < 1e-10 {
            return (a, b, true);
        }
    }
    (a, b, false)
}

/// Area under the ROC curve for "smaller statistic means success":
/// P(stat of a success < stat of a failure), ties counted one half.
fn auc(points: &[(f64, bool)]) -> f64 {
    let mut sorted: Vec<(f64, bool)> = points.to_vec();
    sorted.sort_by(|a, b| a.0.total_cmp(&b.0));
    let n_s = sorted.iter().filter(|p| p.1).count() as f64;
    let n_f = sorted.len() as f64 - n_s;
    if n_s == 0.0 || n_f == 0.0 {
        return f64::NAN;
    }
    // Count, for each failure, the successes strictly below plus half the ties.
    let mut below = 0.0;
    let mut acc = 0.0;
    let mut i = 0;
    while i < sorted.len() {
        let mut j = i;
        let (mut s, mut f) = (0.0, 0.0);
        while j < sorted.len() && sorted[j].0 == sorted[i].0 {
            if sorted[j].1 {
                s += 1.0;
            } else {
                f += 1.0;
            }
            j += 1;
        }
        acc += f * (below + 0.5 * s);
        below += s;
        i = j;
    }
    acc / (n_s * n_f)
}

struct ConfigDef {
    array: usize,
    coverage: &'static str,
    uniform: bool,
}

fn main() {
    let outdir = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "outputs/clean-phase-transition".to_string());
    let trials: usize = std::env::args()
        .nth(2)
        .map(|v| v.parse().expect("trials"))
        .unwrap_or(100);
    std::fs::create_dir_all(&outdir).expect("output directory");
    let started = Instant::now();
    let arrays = arrays();
    let mut configs = Vec::new();
    for array in 0..arrays.len() {
        for coverage in ["snapshot", "track"] {
            for uniform in [false, true] {
                configs.push(ConfigDef {
                    array,
                    coverage,
                    uniform,
                });
            }
        }
    }
    let mut json = Json(String::from("{ "));
    json.text("date", "2026-10-30");
    json.int("n", N);
    json.int("trials_per_cell", trials);
    json.ints("k", &KS);
    json.ints("d", &DS);
    json.num("px_per_fringe_target", PX_PER_FRINGE);
    json.num("sigma_image", SIGMA_IMAGE);
    json.int("max_steps", MAX_STEPS);
    json.int("noise_realisations", NOISE_REALISATIONS);
    json.open_list("arrays");
    let mut cells_of_array = Vec::new();
    for a in &arrays {
        let ants = antennas(a.table);
        let track = raw_uv(a, &track_hours());
        let max_uv = (0..track.len())
            .map(|k| track.u[k].hypot(track.v[k]))
            .fold(0.0, f64::max);
        let cell = a.fixed_cell.unwrap_or(1.0 / (PX_PER_FRINGE * max_uv));
        cells_of_array.push(cell);
        let ppf = 1.0 / (max_uv * cell);
        println!(
            "array {}: {} antennas, dec {:+}°, {:.2} GHz, max |uv| over the track {:.0} λ, cell {:.3}″ ({:.2} px per fringe)",
            a.name,
            ants.len(),
            a.declination_deg,
            a.frequency_hz / 1e9,
            max_uv,
            cell * 180.0 / PI * 3600.0,
            ppf
        );
        json.item();
        json.text("name", a.name);
        json.int("antennas", ants.len());
        json.num("declination_deg", a.declination_deg);
        json.num("frequency_hz", a.frequency_hz);
        json.num("max_uv_track", max_uv);
        json.num("cell_arcsec", cell * 180.0 / PI * 3600.0);
        json.num("px_per_fringe", ppf);
        json.close();
    }
    json.close_list();
    json.open_list("configs");
    let mut records: Vec<Record> = Vec::new();
    let mut dstar_rows: Vec<String> = Vec::new();
    let mut config_names = Vec::new();
    let mut violations_total = [0usize; 6];
    for (ci, cfg) in configs.iter().enumerate() {
        let t_config = Instant::now();
        let a = &arrays[cfg.array];
        let grid = Grid {
            n: N,
            cell: cells_of_array[cfg.array],
        };
        let name = format!(
            "{}-{}-{}",
            a.name,
            cfg.coverage,
            if cfg.uniform { "uniform" } else { "natural" }
        );
        config_names.push(name.clone());
        let hours = if cfg.coverage == "snapshot" {
            vec![0.0]
        } else {
            track_hours()
        };
        let s = weighted(raw_uv(a, &hours), &grid, cfg.uniform);
        let t = Instant::now();
        let b = psf(&s, &grid);
        let psf_s = t.elapsed().as_secs_f64();
        let t = Instant::now();
        let cond = conditions(&b);
        let cond_s = t.elapsed().as_secs_f64();
        let t = Instant::now();
        let scan = pair_scan(&b);
        let scan_s = t.elapsed().as_secs_f64();
        // Dirty-noise realisations on a 128 × 128 grid of the same cell.
        let t = Instant::now();
        let big = Grid {
            n: 2 * N,
            cell: grid.cell,
        };
        let sum_w2: f64 = s.w.iter().map(|w| w * w).sum();
        let sigma_vis = SIGMA_IMAGE / sum_w2.sqrt();
        let mut nrng = Rng::seeded(0xC1EA_0000 ^ ci as u64);
        let noise: Vec<Vec<f64>> = (0..NOISE_REALISATIONS)
            .map(|_| {
                let vis: Vec<Vis> = (0..s.len())
                    .map(|_| (sigma_vis * nrng.normal(), sigma_vis * nrng.normal()))
                    .collect();
                dirty(&s, &big, &vis)
            })
            .collect();
        let measured_sigma = (noise
            .iter()
            .flat_map(|im| im.iter())
            .map(|v| v * v)
            .sum::<f64>()
            / (NOISE_REALISATIONS * big.pixels()) as f64)
            .sqrt();
        let noise_s = t.elapsed().as_secs_f64();
        // Trials, in parallel over (k, d, trial).
        let t = Instant::now();
        let jobs: Vec<(usize, usize, usize)> = (0..KS.len())
            .flat_map(|ki| {
                (0..DS.len()).flat_map(move |di| (0..trials).map(move |tr| (ki, di, tr)))
            })
            .collect();
        let results: Vec<Option<Trial>> = jobs
            .par_iter()
            .map(|&(ki, di, tr)| {
                let (k, d) = (KS[ki], DS[di]);
                if N.div_ceil(d).pow(2) < k {
                    return None;
                }
                let seed =
                    ((ci as u64) << 48) ^ ((k as u64) << 32) ^ ((d as u64) << 16) ^ tr as u64;
                run_trial(&b, &grid, &noise, k, d, seed)
            })
            .collect();
        let trials_s = t.elapsed().as_secs_f64();
        // Two sources at separation exactly d, noiseless, gain 1.
        let t = Instant::now();
        let pair_jobs: Vec<(usize, usize)> = (1..=PAIR_DS)
            .flat_map(|d| (0..trials).map(move |tr| (d, tr)))
            .collect();
        let pair_results: Vec<(bool, bool, bool, bool)> = pair_jobs
            .par_iter()
            .map(|&(d, tr)| {
                let seed = ((ci as u64) << 48) ^ (0xAB << 32) ^ ((d as u64) << 16) ^ tr as u64;
                run_pair(&b, &grid, d, seed)
            })
            .collect();
        let pairs_s = t.elapsed().as_secs_f64();
        // Per d: (success, on support, rule agrees with on support, ERC < 1).
        let pair_rows: Vec<(usize, usize, usize, usize)> = (0..PAIR_DS)
            .map(|i| {
                let chunk = &pair_results[i * trials..(i + 1) * trials];
                (
                    chunk.iter().filter(|r| r.0).count(),
                    chunk.iter().filter(|r| r.1).count(),
                    chunk.iter().filter(|r| r.2 == r.1).count(),
                    chunk.iter().filter(|r| r.3).count(),
                )
            })
            .collect();
        let pair_dstar =
            (1..=PAIR_DS).find(|&d| pair_rows[d - 1..].iter().all(|r| 100 * r.0 >= 95 * trials));
        // Aggregate.
        let mut cells = vec![vec![Cell::default(); DS.len()]; KS.len()];
        let mut violations = [0usize; 6];
        for (ki, &k) in KS.iter().enumerate() {
            for (di, &d) in DS.iter().enumerate() {
                let cell = &mut cells[ki][di];
                cell.feasible = N.div_ceil(d).pow(2) >= k;
                let base = (ki * DS.len() + di) * trials;
                let mine: Vec<&Trial> = results[base..base + trials]
                    .iter()
                    .filter_map(|r| r.as_ref())
                    .collect();
                cell.placed = mine.len();
                let new_ok = cond.new_upper(d, ki) < 1.0;
                let prop_ok = cond.prop4(d, ki) < 1.0;
                let anchored_ok = cond.anchored(d, ki) < 1.0;
                cell.min_sep_min = mine.iter().map(|t| t.min_sep).min().unwrap_or(0);
                for t in &mine {
                    cell.success += usize::from(t.success);
                    cell.on_support += usize::from(t.on_support);
                    cell.capped += usize::from(t.capped);
                    cell.first_pick_failures += usize::from(t.first_off == Some(0));
                    let erc_ok = t.eta() < 1.0;
                    let g_ok = t.gershgorin() < 1.0;
                    let one_ok = t.first_pick_on && t.eta_gain_one() < 1.0;
                    cell.erc += usize::from(erc_ok);
                    cell.gershgorin += usize::from(g_ok);
                    cell.gain_one += usize::from(one_ok);
                    // Implication checks: each is a theorem; a count is a bug.
                    violations[0] += usize::from(erc_ok && !t.on_support);
                    violations[1] += usize::from(g_ok && !erc_ok);
                    violations[2] += usize::from(new_ok && !g_ok);
                    violations[3] += usize::from(prop_ok && !new_ok);
                    violations[4] += usize::from(one_ok && !t.on_support);
                    violations[5] += usize::from(anchored_ok && !erc_ok);
                    if let Some(pred) = t.k2_predicted {
                        cell.k2_total += 1;
                        cell.k2_agree += usize::from(pred == t.on_support);
                    }
                    cell.noisy_exact += usize::from(t.noisy_exact);
                    cell.noisy_found_all += usize::from(t.noisy_found_all);
                    cell.noisy_fraction += t.noisy_fraction;
                    cell.noisy_false += t.noisy_false as f64;
                    cell.noisy_capped += usize::from(t.noisy_capped);
                    records.push(Record {
                        config: ci,
                        array: cfg.array,
                        success: t.success,
                        stats: [
                            t.eta(),
                            t.eta_gain_one(),
                            t.cross(),
                            t.gershgorin(),
                            cond.new_upper(d, ki),
                            cond.anchored(d, ki),
                            t.radius(),
                            cond.in_upper[d][ki],
                        ],
                    });
                }
                if cell.placed > 0 {
                    cell.noisy_fraction /= cell.placed as f64;
                    cell.noisy_false /= cell.placed as f64;
                }
                cell.median_eta = median(mine.iter().map(|t| t.eta()).collect());
                cell.median_cross = median(mine.iter().map(|t| t.cross()).collect());
            }
        }
        for (total, v) in violations_total.iter_mut().zip(&violations) {
            *total += v;
        }
        let config_s = t_config.elapsed().as_secs_f64();
        // Report.
        println!(
            "\n## {name}: M = {}, μ_1 = {:.4}, μ_2 = {:.4}, μ_4 = {:.4}, μ_8 = {:.4}, μ_16 = {:.4}, μ_32 = {:.4}; noise σ measured {measured_sigma:.4}",
            s.len(),
            cond.mu[1],
            cond.mu[2],
            cond.mu[4],
            cond.mu[8],
            cond.mu[16],
            cond.mu[32]
        );
        println!(
            "timings: PSF {psf_s:.2} s, bounds {cond_s:.2} s, pair scan {scan_s:.2} s, noise {noise_s:.2} s, trials {trials_s:.2} s, pairs {pairs_s:.2} s, total {config_s:.2} s"
        );
        println!(
            "two-source scan: worst-case d {} (later picks {}, first pick {}, ERC {}); violations [ERC⇒on, G⇒ERC, cell⇒G, P4'⇒cell, η₁⇒on, anchored⇒ERC] = {violations:?}",
            scan.d_worst, scan.d_worst_later, scan.d_worst_first, scan.d_worst_erc
        );
        println!(
            "two sources at separation exactly d (d = 1..{PAIR_DS}): success / on support / rule agrees / ERC < 1 / predicted success (scan, exactly d)"
        );
        let mut line = String::new();
        for (i, r) in pair_rows.iter().enumerate() {
            let _ = write!(
                line,
                "d={}: {}/{}/{}/{}/{:.2}; ",
                i + 1,
                r.0,
                r.1,
                r.2,
                r.3,
                scan.predicted_exact[i + 1]
            );
        }
        println!("    {line}");
        println!(
            "    measured two-source d* (exactly d, ≥ 95 % from there to {PAIR_DS}): {}",
            pair_dstar
                .map(|d| d.to_string())
                .unwrap_or_else(|| "–".into())
        );
        println!(
            "| k | d | placed | success | on support | capped | first-pick fails | ERC<1 | G<1 | η₁ rule | med η | med cross | Σ bound (lower..upper) | P4' | noisy exact | noisy found all | noisy pick frac | noisy false px |"
        );
        println!(
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |"
        );
        for (ki, &k) in KS.iter().enumerate() {
            for (di, &d) in DS.iter().enumerate() {
                let c = &cells[ki][di];
                if !c.feasible || c.placed == 0 {
                    println!(
                        "| {k} | {d} | {} | – | – | – | – | – | – | – | – | – | – | – | – | – | – | – |",
                        if c.feasible { "0" } else { "grid full" }
                    );
                    continue;
                }
                println!(
                    "| {k} | {d} | {} | {} | {} | {} | {} | {} | {} | {} | {:.3} | {:.3} | {:.3}..{:.3} | {:.3} | {} | {} | {:.3} | {:.2} |",
                    c.placed,
                    c.success,
                    c.on_support,
                    c.capped,
                    c.first_pick_failures,
                    c.erc,
                    c.gershgorin,
                    c.gain_one,
                    c.median_eta,
                    c.median_cross,
                    cond.new_lower(d, ki),
                    cond.new_upper(d, ki),
                    cond.prop4(d, ki),
                    c.noisy_exact,
                    c.noisy_found_all,
                    c.noisy_fraction,
                    c.noisy_false
                );
            }
        }
        // Transitions. d* = smallest d with ≥ 95 % success there and at every
        // larger fully placed d; cells not fully placed are skipped.
        let full = |c: &Cell| c.feasible && c.placed == trials;
        let mut dstar = Vec::new();
        let mut dstar_first = Vec::new();
        let mut dstar_noisy = Vec::new();
        for (ki, row) in cells.iter().enumerate() {
            let ok = |c: &Cell| 100 * c.success >= 95 * c.placed;
            let ok_noisy = |c: &Cell| 100 * c.noisy_exact >= 95 * c.placed;
            let measured: Vec<(usize, &Cell)> = DS
                .iter()
                .zip(row)
                .filter(|(_, c)| full(c))
                .map(|(&d, c)| (d, c))
                .collect();
            let stable = |pred: &dyn Fn(&Cell) -> bool| {
                let mut found = None;
                for (i, &(d, _)) in measured.iter().enumerate() {
                    if measured[i..].iter().all(|(_, c)| pred(c)) {
                        found = Some(d);
                        break;
                    }
                }
                found
            };
            dstar.push(stable(&ok));
            dstar_noisy.push(stable(&ok_noisy));
            dstar_first.push(measured.iter().find(|(_, c)| ok(c)).map(|&(d, _)| d));
            let _ = ki;
        }
        let pred_new: Vec<Option<usize>> = (0..KS.len())
            .map(|ki| cond.first_below(ki, Conditions::new_upper))
            .collect();
        let pred_greedy: Vec<Option<usize>> = (0..KS.len())
            .map(|ki| cond.first_below(ki, Conditions::new_lower))
            .collect();
        let pred_prop: Vec<Option<usize>> = (0..KS.len())
            .map(|ki| cond.first_below(ki, Conditions::prop4))
            .collect();
        let pred_anchored: Vec<Option<usize>> = (0..KS.len())
            .map(|ki| cond.first_below(ki, Conditions::anchored))
            .collect();
        let show = |v: &Option<usize>| v.map(|d| d.to_string()).unwrap_or_else(|| "–".into());
        let fmt_row = |v: &[Option<usize>]| v.iter().map(show).collect::<Vec<_>>().join(", ");
        println!(
            "d*(k) measured (stable) {}; first d ≥ 95 % {}; noisy exact-support d* {}; anchored (certified) {}; separated sums (certified) {}; separated sums, greedy {}; Proposition 4' {}; two-source worst case {} (ERC {}); two-source exactly-d measured {}",
            fmt_row(&dstar),
            fmt_row(&dstar_first),
            fmt_row(&dstar_noisy),
            fmt_row(&pred_anchored),
            fmt_row(&pred_new),
            fmt_row(&pred_greedy),
            fmt_row(&pred_prop),
            scan.d_worst,
            scan.d_worst_erc,
            show(&pair_dstar)
        );
        dstar_rows.push(format!(
            "| {name} | {} | {} | {} | {} | {} | {} | {} | {} | {} |",
            fmt_row(&dstar),
            fmt_row(&pred_anchored),
            fmt_row(&pred_new),
            fmt_row(&pred_greedy),
            fmt_row(&pred_prop),
            show(&pair_dstar),
            scan.d_worst,
            scan.d_worst_erc,
            fmt_row(&dstar_noisy)
        ));
        // JSON for this configuration.
        json.item();
        json.text("name", &name);
        json.text("array", a.name);
        json.text("coverage", cfg.coverage);
        json.text("weighting", if cfg.uniform { "uniform" } else { "natural" });
        json.int("visibilities", s.len());
        json.nums("mu_d", &cond.mu[1..]);
        json.num("noise_sigma_measured", measured_sigma);
        json.open_object("seconds");
        json.num("psf", psf_s);
        json.num("bounds", cond_s);
        json.num("pair_scan", scan_s);
        json.num("noise", noise_s);
        json.num("trials", trials_s);
        json.num("pairs", pairs_s);
        json.num("total", config_s);
        json.close();
        json.open_list("separated_sums");
        for d in 1..=D_SCAN {
            json.item();
            json.int("d", d);
            json.nums("out_lower", &cond.out_lower[d]);
            json.nums("out_upper", &cond.out_upper[d]);
            json.nums("in_lower", &cond.in_lower[d]);
            json.nums("in_upper", &cond.in_upper[d]);
            json.int("out_greedy_placed", cond.out_placed[d]);
            let p4: Vec<f64> = (0..KS.len()).map(|ki| cond.prop4(d, ki)).collect();
            json.nums("prop4", &p4);
            json.nums("anchored", &cond.anchored[d]);
            json.close();
        }
        json.close_list();
        json.open_object("pair_scan");
        json.int("d_worst", scan.d_worst);
        json.int("d_worst_later_picks", scan.d_worst_later);
        json.int("d_worst_first_pick", scan.d_worst_first);
        json.int("d_worst_erc", scan.d_worst_erc);
        json.nums("predicted_success_min_separation", &scan.predicted[1..]);
        json.nums(
            "predicted_success_exact_separation",
            &scan.predicted_exact[1..],
        );
        json.close();
        json.open_object("pairs_exact_separation");
        let col = |f: fn(&(usize, usize, usize, usize)) -> usize| -> Vec<usize> {
            pair_rows.iter().map(f).collect()
        };
        json.int("trials_per_d", trials);
        json.ints("success", &col(|r| r.0));
        json.ints("on_support", &col(|r| r.1));
        json.ints("rule_agrees", &col(|r| r.2));
        json.ints("erc_holds", &col(|r| r.3));
        json.opts("dstar", &[pair_dstar]);
        json.close();
        json.open_object("transition");
        json.opts("dstar_measured", &dstar);
        json.opts("dstar_first_95", &dstar_first);
        json.opts("dstar_noisy_exact", &dstar_noisy);
        json.opts("d_anchored_certified", &pred_anchored);
        json.opts("d_new_certified", &pred_new);
        json.opts("d_new_greedy", &pred_greedy);
        json.opts("d_prop4", &pred_prop);
        json.close();
        json.ints("violations", &violations);
        json.open_list("cells");
        for (ki, &k) in KS.iter().enumerate() {
            for (di, &d) in DS.iter().enumerate() {
                let c = &cells[ki][di];
                json.item();
                json.int("k", k);
                json.int("d", d);
                json.boolean("feasible", c.feasible);
                json.int("placed", c.placed);
                if c.placed > 0 {
                    json.int("success", c.success);
                    json.int("on_support", c.on_support);
                    json.int("capped", c.capped);
                    json.int("first_pick_failures", c.first_pick_failures);
                    json.int("erc_holds", c.erc);
                    json.int("gershgorin_holds", c.gershgorin);
                    json.int("gain_one_rule_holds", c.gain_one);
                    if c.k2_total > 0 {
                        json.int("k2_rule_agrees", c.k2_agree);
                        json.int("k2_rule_trials", c.k2_total);
                    }
                    json.num("median_eta", c.median_eta);
                    json.num("median_cross", c.median_cross);
                    json.int("min_separation_achieved", c.min_sep_min);
                    json.int("noisy_exact", c.noisy_exact);
                    json.int("noisy_found_all", c.noisy_found_all);
                    json.num("noisy_pick_fraction", c.noisy_fraction);
                    json.num("noisy_false_pixels", c.noisy_false);
                    json.int("noisy_capped", c.noisy_capped);
                }
                json.close();
            }
        }
        json.close_list();
        json.close();
    }
    json.close_list();
    println!("\n## Transition table d*(k) for k = 2, 4, 8, 16, 32");
    println!(
        "| config | measured d* (≥ 95 %, stable) | anchored bound, certified | separated sums, certified | separated sums, greedy | Proposition 4' | two sources at exactly d, measured | two-source worst case, gain 1 | two-source worst case, ERC | noisy exact support d* |"
    );
    println!("| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |");
    for row in &dstar_rows {
        println!("{row}");
    }
    println!(
        "\nimplication violations over all trials [ERC⇒on support, G⇒ERC, cell bound⇒G, P4'⇒cell bound, η₁ rule⇒on support, anchored⇒ERC] = {violations_total:?}"
    );
    // Collapse analysis: pooled success against per-trial statistics.
    json.ints("violations_total", &violations_total);
    json.nums("bin_edges", &EDGES);
    json.open_list("collapse");
    println!("\n## Collapse: success against per-trial statistics, all configurations pooled");
    for (si, stat) in STAT_NAMES.iter().enumerate() {
        let points: Vec<(f64, bool)> = records.iter().map(|r| (r.stats[si], r.success)).collect();
        let pooled_auc = auc(&points);
        let nb = EDGES.len() - 1;
        let mut pooled = vec![(0usize, 0usize); nb];
        let mut per_array = vec![vec![(0usize, 0usize); nb]; arrays.len()];
        let mut per_config = vec![vec![(0usize, 0usize); nb]; configs.len()];
        for r in &records {
            let bi = bin_of(r.stats[si]);
            pooled[bi].0 += 1;
            pooled[bi].1 += usize::from(r.success);
            per_array[r.array][bi].0 += 1;
            per_array[r.array][bi].1 += usize::from(r.success);
            per_config[r.config][bi].0 += 1;
            per_config[r.config][bi].1 += usize::from(r.success);
        }
        // Spread across arrays in bins where at least two arrays have ≥ 30 trials.
        let spread = |groups: &[Vec<(usize, usize)>]| {
            let mut worst = 0.0_f64;
            let mut weighted = 0.0;
            let mut weight = 0.0;
            for bi in 0..nb {
                let rates: Vec<f64> = groups
                    .iter()
                    .filter(|g| g[bi].0 >= 30)
                    .map(|g| g[bi].1 as f64 / g[bi].0 as f64)
                    .collect();
                if rates.len() >= 2 {
                    let hi = rates.iter().cloned().fold(f64::MIN, f64::max);
                    let lo = rates.iter().cloned().fold(f64::MAX, f64::min);
                    worst = worst.max(hi - lo);
                    weighted += (hi - lo) * pooled[bi].0 as f64;
                    weight += pooled[bi].0 as f64;
                }
            }
            (
                worst,
                if weight > 0.0 {
                    weighted / weight
                } else {
                    f64::NAN
                },
            )
        };
        let (spread_arrays, mean_spread_arrays) = spread(&per_array);
        let (spread_configs, mean_spread_configs) = spread(&per_config);
        // Logistic fits per configuration.
        let mut fits = Vec::new();
        for c in 0..configs.len() {
            let pts: Vec<(f64, bool)> = records
                .iter()
                .filter(|r| r.config == c)
                .map(|r| (r.stats[si], r.success))
                .collect();
            let fails = pts.iter().filter(|p| !p.1).count();
            let succ = pts.len() - fails;
            let (a, b, conv) = logistic(&pts);
            let x50 = (-a / b).exp();
            let x95 = ((19f64.ln() - a) / b).exp();
            fits.push((c, succ, fails, a, b, conv, x50, x95));
        }
        let (pa, pb, pconv) = logistic(&points);
        println!(
            "\n### {stat}: pooled AUC {pooled_auc:.4}; pooled logistic x50 {:.3}, x95 {:.3}{}; max |Δ success| across arrays per bin {spread_arrays:.3} (trial-weighted mean {mean_spread_arrays:.3}); across configurations {spread_configs:.3} (mean {mean_spread_configs:.3})",
            (-pa / pb).exp(),
            ((19f64.ln() - pa) / pb).exp(),
            if pconv { "" } else { " (not converged)" }
        );
        let header: Vec<String> = (0..nb)
            .map(|bi| format!("[{}, {})", EDGES[bi], EDGES[bi + 1]))
            .collect();
        println!("| group | {} |", header.join(" | "));
        println!("| --- |{}", " ---: |".repeat(nb));
        let row = |label: &str, g: &[(usize, usize)]| {
            let cells: Vec<String> = g
                .iter()
                .map(|&(n, s)| {
                    if n == 0 {
                        "–".to_string()
                    } else {
                        format!("{:.0} % ({n})", 100.0 * s as f64 / n as f64)
                    }
                })
                .collect();
            println!("| {label} | {} |", cells.join(" | "));
        };
        row("pooled", &pooled);
        for (ai, g) in per_array.iter().enumerate() {
            row(arrays[ai].name, g);
        }
        println!("per-configuration logistic fits (x50, x95 of the statistic):");
        for &(c, succ, fails, _, _, conv, x50, x95) in &fits {
            println!(
                "  {}: {succ} successes, {fails} failures, x50 {x50:.3}, x95 {x95:.3}{}",
                config_names[c],
                if conv { "" } else { " (not converged)" }
            );
        }
        json.item();
        json.text("statistic", stat);
        json.num("pooled_auc", pooled_auc);
        json.num("pooled_logistic_a", pa);
        json.num("pooled_logistic_b", pb);
        json.num("spread_across_arrays_max", spread_arrays);
        json.num("spread_across_arrays_mean", mean_spread_arrays);
        json.num("spread_across_configs_max", spread_configs);
        json.num("spread_across_configs_mean", mean_spread_configs);
        let flat = |g: &[(usize, usize)]| -> (Vec<usize>, Vec<usize>) {
            (
                g.iter().map(|x| x.0).collect(),
                g.iter().map(|x| x.1).collect(),
            )
        };
        let (n, s) = flat(&pooled);
        json.ints("pooled_trials", &n);
        json.ints("pooled_successes", &s);
        json.open_list("per_array");
        for (ai, g) in per_array.iter().enumerate() {
            let (n, s) = flat(g);
            json.item();
            json.text("array", arrays[ai].name);
            json.ints("trials", &n);
            json.ints("successes", &s);
            json.close();
        }
        json.close_list();
        json.open_list("per_config");
        for (c, g) in per_config.iter().enumerate() {
            let (n, s) = flat(g);
            let f = fits[c];
            json.item();
            json.text("config", &config_names[c]);
            json.ints("trials", &n);
            json.ints("successes", &s);
            json.num("logistic_a", f.3);
            json.num("logistic_b", f.4);
            json.boolean("logistic_converged", f.5);
            json.num("x50", f.6);
            json.num("x95", f.7);
            json.close();
        }
        json.close_list();
        json.close();
    }
    json.close_list();
    let total = started.elapsed().as_secs_f64();
    json.num("total_seconds", total);
    let text = json.finish();
    std::fs::write(format!("{outdir}/clean-phase-transition.json"), text).expect("write json");
    println!("\ntotal {total:.1} s");
}
