//! The measured half of `research/clean-theory.md`: Högbom CLEAN on MeerKAT
//! sampling, checked against the theorems of the note.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Run from the repository root:
//! `cargo run --release --manifest-path core/Cargo.toml --example clean_theory -- OUTDIR`.
//! Writes `OUTDIR/clean-theory.json` and prints the tables of the note.
//!
//! Experiments (all seeds fixed; every number is deterministic):
//! E1 the one-step misfit identity and the gain window `0 < γ < 2`, exact and
//!    truncated beams; E2 exact support recovery against the coherence bound
//!    and the exact recovery coefficient; E3 the greedy ratio that sets the
//!    rate; E4 an off-grid source; E5 the Clark minor-cycle descent
//!    condition; E6 extended emission and the gain dependence of the limit;
//!    E2c recovery with noise; E7 the coherence of a multi-scale dictionary.

use rang_core::clean::{
    CleanSettings, Grid, Psf, Sampling, Vis, add_atom, argmax_abs, convolve, dirty, erc, gram,
    hogbom, least_squares_model, min_eigenvalue, misfit, point_vis, predict, psf, subtract,
};
use std::f64::consts::PI;
use std::fmt::Write as _;
use std::time::Instant;

const C: f64 = 299_792_458.0;
const FREQUENCY: f64 = 1.4e9;
const DECLINATION_DEG: f64 = -30.0;
const N: usize = 64;
/// 2 arcsec pixels: about 2.8 pixels per fringe of the longest baseline.
const CELL: f64 = 2.0 / 3600.0 * PI / 180.0;

/// xorshift64* with Box–Muller normals; fixed seeds make every run identical.
struct Rng(u64);

impl Rng {
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

/// ITRF to east-north-up about the array centroid; returns the ENU
/// positions and the geocentric latitude of the centroid.
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
        // Uniform weighting: one over the number of samples in the uv cell
        // of this image (cell 1 / (n · pixel)), Hermitian pairs counted once.
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

/// Text accumulated for `clean-theory.json` (hand-written JSON, as the
/// crate has no serialiser).
struct Json(String);

impl Json {
    fn key(&mut self, name: &str) {
        let _ = write!(self.0, "\"{name}\": ");
    }
    fn num(&mut self, name: &str, value: f64) {
        self.key(name);
        let _ = write!(self.0, "{value:e}, ");
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

struct Scene {
    vis: Vec<Vis>,
    dirty: Vec<f64>,
    truth: Vec<f64>,
}

/// Six point sources, one two pixels from the left edge, plus visibility
/// noise of 0.5 per sample (image noise about 0.5 / sqrt(2 M)).
fn scene(s: &Sampling, grid: &Grid, rng: &mut Rng) -> Scene {
    let mut truth = vec![0.0; grid.pixels()];
    let fluxes = [1.0, 0.7, 0.5, 0.3, 0.2];
    for &f in &fluxes {
        loop {
            let p = grid.index(4 + rng.below(grid.n - 8), 4 + rng.below(grid.n - 8));
            if truth[p] == 0.0 {
                truth[p] = f;
                break;
            }
        }
    }
    truth[grid.index(2, grid.n / 2)] = 0.8;
    let mut vis = predict(s, grid, &truth);
    for v in &mut vis {
        v.0 += 0.5 * rng.normal();
        v.1 += 0.5 * rng.normal();
    }
    let d = dirty(s, grid, &vis);
    Scene {
        vis,
        dirty: d,
        truth,
    }
}

/// A CLEAN run that also tracks the misfit through the model visibilities.
/// Returns per-step (peak, Q after the step); `patch` truncates the beam
/// used for the working residual while Q is always exact.
fn tracked_run(
    s: &Sampling,
    grid: &Grid,
    b: &Psf,
    scene: &Scene,
    gain: f64,
    iterations: usize,
    patch: Option<usize>,
) -> (f64, Vec<(f64, f64)>) {
    let mut residual = scene.dirty.clone();
    let mut model_vis = vec![(0.0, 0.0); s.len()];
    let q0 = misfit(s, &scene.vis, &model_vis);
    let mut out = Vec::with_capacity(iterations);
    for _ in 0..iterations {
        let (p, peak) = argmax_abs(&residual);
        let c = gain * peak;
        subtract(&mut residual, b, p, c, patch);
        add_atom(s, grid, p, c, &mut model_vis);
        out.push((peak, misfit(s, &scene.vis, &model_vis)));
    }
    (q0, out)
}

fn main() {
    let outdir = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "outputs/clean-theory".to_string());
    std::fs::create_dir_all(&outdir).expect("output directory");
    let started = Instant::now();
    let grid = Grid { n: N, cell: CELL };
    let configs = [
        Config {
            name: "snapshot-natural",
            hours: vec![0.0],
            uniform: false,
        },
        Config {
            name: "snapshot-uniform",
            hours: vec![0.0],
            uniform: true,
        },
        Config {
            name: "track-natural",
            hours: (0..13).map(|i| -2.0 + i as f64 / 3.0).collect(),
            uniform: false,
        },
        Config {
            name: "track-uniform",
            hours: (0..13).map(|i| -2.0 + i as f64 / 3.0).collect(),
            uniform: true,
        },
    ];
    let mut json = Json(String::from("{ "));
    json.text("date", "2026-10-30");
    json.int("n", N);
    json.num("cell_rad", CELL);
    json.num("frequency_hz", FREQUENCY);
    json.num("declination_deg", DECLINATION_DEG);
    json.open_list("configs");
    println!("| config | M | mu | k* = floor((1+1/mu)/2) | PSF s | outside ±8 | outside ±16 |");
    println!("| --- | ---: | ---: | ---: | ---: | ---: | ---: |");
    for config in &configs {
        let t = Instant::now();
        let s = sampling(config, &grid);
        let b = psf(&s, &grid);
        let psf_seconds = t.elapsed().as_secs_f64();
        let mu = b.coherence();
        let k_star = ((1.0 + 1.0 / mu) / 2.0 - 1e-12).floor() as usize;
        println!(
            "| {} | {} | {:.4} | {} | {:.2} | {:.4} | {:.4} |",
            config.name,
            s.len(),
            mu,
            k_star,
            psf_seconds,
            b.outside_patch(8),
            b.outside_patch(16)
        );
        json.item();
        json.text("name", config.name);
        json.int("visibilities", s.len());
        json.num("coherence", mu);
        json.int("k_star", k_star);
        json.num("psf_seconds", psf_seconds);
        json.num("outside_8", b.outside_patch(8));
        json.num("outside_16", b.outside_patch(16));
        // Peak |PSF| at Chebyshev distance >= d, and the largest k the
        // separated-source proposition allows: (k-1)(μ_{ceil(d/2)} + μ_d) < 1 - μ_1.
        json.open_list("separation");
        let mut sep_line = String::new();
        for d in [1usize, 2, 3, 4, 6, 8, 12, 16, 24, 32] {
            let mu_d = b.outside_patch(d - 1);
            let k_sep = if d >= 2 {
                // All but the nearest source are at least ceil(d/2) from any
                // competitor pixel, so the off-support column sum is at most
                // μ_1 + (k−1) μ_{ceil(d/2)}.
                let denom = b.outside_patch(d.div_ceil(2) - 1) + mu_d;
                let room = 1.0 - mu;
                if denom <= 0.0 {
                    99
                } else {
                    ((room / denom - 1e-12).ceil() as usize).max(1)
                }
            } else {
                1
            };
            let _ = write!(sep_line, "d={d}: μ_d={mu_d:.3} k_sep={k_sep}; ");
            json.item();
            json.int("d", d);
            json.num("mu_d", mu_d);
            json.int("k_sep", k_sep);
            json.close();
        }
        json.close_list();
        println!("    separation: {sep_line}");
        let mut rng = Rng(0x9E37_79B9_7F4A_7C15 ^ config.name.len() as u64);
        let sc = scene(&s, &grid, &mut rng);
        e1_identity(&s, &grid, &b, &sc, &mut json);
        e2_recovery(&grid, &b, &mut rng, 0, "e2", &mut json);
        e2_recovery(&grid, &b, &mut rng, 8, "e2_separated", &mut json);
        e3_greedy_ratio(&s, &grid, &b, &sc, &mut rng, &mut json);
        e4_offgrid(&s, &grid, &b, &mut json);
        e5_clark(&s, &grid, &b, &sc, &mut json);
        e6_extended(&s, &grid, &b, &mut json);
        e2c_noisy(&s, &grid, &b, &mut rng, &mut json);
        e7_multiscale(&b, &mut json);
        json.close();
    }
    json.close_list();
    json.num("total_seconds", started.elapsed().as_secs_f64());
    let text = json.finish();
    std::fs::write(format!("{outdir}/clean-theory.json"), text).expect("write json");
    println!("\ntotal {:.1} s", started.elapsed().as_secs_f64());
}

/// E1: `Q_{k+1} − Q_k = −γ(2−γ)/2 · r_k²` to rounding for every gain with the
/// exact beam; the sign flips above γ = 2; truncated beams break it.
fn e1_identity(s: &Sampling, grid: &Grid, b: &Psf, sc: &Scene, json: &mut Json) {
    println!("\nE1 one-step identity, 400 steps (deviation = max |ΔQ − predicted| / Q_k)");
    println!("| gain | beam | max deviation | steps with ΔQ > 0 | Q_400 / Q_0 | max |r| end |");
    println!("| ---: | --- | ---: | ---: | ---: | ---: |");
    json.open_list("e1");
    let cases: Vec<(f64, Option<usize>, &str)> = vec![
        (0.1, None, "exact"),
        (0.5, None, "exact"),
        (1.0, None, "exact"),
        (1.5, None, "exact"),
        (1.9, None, "exact"),
        (2.1, None, "exact"),
        (1.0, Some(32), "±32 (same-size grid)"),
        (1.0, Some(16), "±16"),
        (1.0, Some(8), "±8"),
        (0.1, Some(8), "±8"),
    ];
    for (gain, patch, label) in cases {
        let (q0, steps) = tracked_run(s, grid, b, sc, gain, 400, patch);
        let mut q = q0;
        let mut deviation = 0.0_f64;
        let mut rises = 0;
        for &(peak, q_next) in &steps {
            let predicted = q - gain * (2.0 - gain) / 2.0 * peak * peak;
            deviation = deviation.max((q_next - predicted).abs() / q);
            if q_next > q {
                rises += 1;
            }
            q = q_next;
        }
        let end_peak = steps.last().map(|x| x.0.abs()).unwrap_or(0.0);
        println!(
            "| {gain} | {label} | {deviation:.2e} | {rises} | {:.4e} | {end_peak:.3e} |",
            q / q0
        );
        json.item();
        json.num("gain", gain);
        json.text("beam", label);
        json.num("max_deviation", deviation);
        json.int("rises", rises);
        json.num("q_ratio", q / q0);
        json.num("end_peak", end_peak);
        json.close();
    }
    json.close_list();
}

/// E2: noiseless k-sparse skies on the grid; does every component land on
/// the true support? Against the coherence bound and Tropp's ERC.
fn e2_recovery(grid: &Grid, b: &Psf, rng: &mut Rng, separation: usize, key: &str, json: &mut Json) {
    let trials = 100;
    let mu = b.coherence();
    println!(
        "\nE2 exact support recovery, {trials} noiseless trials per k, gain 1, stop at |r| < 1e-9, sources at least {separation} px apart"
    );
    println!(
        "| k | bound 2μk < 1+μ | success | ERC < 1 | success given ERC | failures given ERC | min λ_min(B_SS) | mean steps |"
    );
    println!("| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |");
    json.open_list(key);
    for k in 1..=12 {
        let bound = 2.0 * mu * k as f64 <= 1.0 + mu;
        let mut success = 0;
        let mut erc_ok = 0;
        let mut both = 0;
        let mut erc_but_fail = 0;
        let mut min_lambda = f64::INFINITY;
        let mut steps_total = 0usize;
        for _ in 0..trials {
            let mut support = Vec::with_capacity(k);
            while support.len() < k {
                let p = rng.below(grid.pixels());
                let far = support.iter().all(|&q| {
                    let dx = (p % grid.n) as isize - (q % grid.n) as isize;
                    let dy = (p / grid.n) as isize - (q / grid.n) as isize;
                    dx.abs().max(dy.abs()) as usize >= separation.max(1)
                });
                if far {
                    support.push(p);
                }
            }
            let mut truth = vec![0.0; grid.pixels()];
            for &p in &support {
                truth[p] = 0.2 + 0.8 * rng.uniform();
            }
            let d = convolve(b, &truth);
            let result = hogbom(
                &d,
                b,
                &CleanSettings {
                    gain: 1.0,
                    iterations: 4000,
                    threshold: 1e-9,
                    patch: None,
                },
            );
            let on_support = result.steps.iter().all(|st| support.contains(&st.pixel));
            let close = (0..grid.pixels()).all(|p| (result.model[p] - truth[p]).abs() < 1e-6);
            let ok = on_support && close;
            let eta = erc(b, grid, &support);
            let lambda = min_eigenvalue(&gram(b, &support), k);
            min_lambda = min_lambda.min(lambda);
            steps_total += result.steps.len();
            if ok {
                success += 1;
            }
            if eta.is_some_and(|eta| eta < 1.0) {
                erc_ok += 1;
                if ok {
                    both += 1;
                } else {
                    erc_but_fail += 1;
                }
            }
        }
        println!(
            "| {k} | {} | {success} | {erc_ok} | {both} | {erc_but_fail} | {min_lambda:.3} | {:.0} |",
            if bound { "yes" } else { "no" },
            steps_total as f64 / trials as f64
        );
        json.item();
        json.int("k", k);
        json.boolean("bound_holds", bound);
        json.int("trials", trials);
        json.int("success", success);
        json.int("erc_holds", erc_ok);
        json.int("success_given_erc", both);
        json.int("failures_given_erc", erc_but_fail);
        json.num("min_lambda", min_lambda);
        json.num("mean_steps", steps_total as f64 / trials as f64);
        json.close();
    }
    json.close_list();
}

/// E3: the greedy ratio `κ_k = r_k² / (2 Q_k)`, which sets the per-step
/// contraction `Q_{k+1}/Q_k = 1 − γ(2−γ) κ_k` exactly; on the sparse scene,
/// on pure noise, and on noiseless supports against the bound `λ_min(B_SS)/k`.
fn e3_greedy_ratio(s: &Sampling, grid: &Grid, b: &Psf, sc: &Scene, rng: &mut Rng, json: &mut Json) {
    println!("\nE3 greedy ratio κ = r²/(2Q) (exact contraction 1 − γ(2−γ)κ per step)");
    println!("| case | steps | κ first | κ median | κ last | note |");
    println!("| --- | ---: | ---: | ---: | ---: | --- |");
    json.open_list("e3");
    let report = |name: &str, kappas: &[f64], note: &str, json: &mut Json| {
        let mut sorted = kappas.to_vec();
        sorted.sort_by(|a, b| a.total_cmp(b));
        let median = sorted[sorted.len() / 2];
        println!(
            "| {name} | {} | {:.3e} | {median:.3e} | {:.3e} | {note} |",
            kappas.len(),
            kappas[0],
            kappas[kappas.len() - 1]
        );
        json.item();
        json.text("case", name);
        json.int("steps", kappas.len());
        json.num("first", kappas[0]);
        json.num("median", median);
        json.num("last", kappas[kappas.len() - 1]);
        json.num("min", sorted[0]);
        json.text("note", note);
        json.close();
    };
    // Sparse scene with noise, gain 0.1; κ against the total and against
    // the reducible misfit Q − Q_∞ (Q_∞ from the least-squares model).
    let q_inf_of = |scene: &Scene| {
        let t = Instant::now();
        let (model, used, rel) = least_squares_model(b, &scene.dirty, 400, 1e-7);
        let q_inf = misfit(s, &scene.vis, &predict(s, grid, &model));
        (q_inf, used, rel, t.elapsed().as_secs_f64())
    };
    let (q0, steps) = tracked_run(s, grid, b, sc, 0.1, 1000, None);
    let (q_inf, used, rel, cg_s) = q_inf_of(sc);
    let mut q = q0;
    let mut kappas = Vec::new();
    let mut kappas_rel = Vec::new();
    for &(peak, q_next) in &steps {
        kappas.push(peak * peak / (2.0 * q));
        kappas_rel.push(peak * peak / (2.0 * (q - q_inf).max(1e-300)));
        q = q_next;
    }
    report(
        "six sources + noise, γ 0.1",
        &kappas,
        "six sources; 1/6 = 0.167",
        json,
    );
    report(
        "same, κ relative to Q − Q_∞",
        &kappas_rel,
        &format!(
            "Q_∞/Q_0 = {:.4} (CG {used} it, rel {rel:.1e}, {cg_s:.1} s); Q_1000/Q_0 = {:.4}",
            q_inf / q0,
            steps.last().unwrap().1 / q0
        ),
        json,
    );
    // Pure noise, gain 1.
    let mut noise_vis: Vec<Vis> = (0..s.len()).map(|_| (rng.normal(), rng.normal())).collect();
    let noise_scene = Scene {
        dirty: dirty(s, grid, &noise_vis),
        vis: std::mem::take(&mut noise_vis),
        truth: vec![],
    };
    let (q0, steps) = tracked_run(s, grid, b, &noise_scene, 1.0, 2000, None);
    let (q_inf, used, rel, cg_s) = q_inf_of(&noise_scene);
    let mut q = q0;
    let mut kappas = Vec::new();
    let mut kappas_rel = Vec::new();
    for &(peak, q_next) in &steps {
        kappas.push(peak * peak / (2.0 * q));
        kappas_rel.push(peak * peak / (2.0 * (q - q_inf).max(1e-300)));
        q = q_next;
    }
    let note = format!(
        "pixels N = {}; Q_2000/Q_0 = {:.3}",
        grid.pixels(),
        steps.last().unwrap().1 / q0
    );
    report("pure noise, γ 1", &kappas, &note, json);
    report(
        "same, κ relative to Q − Q_∞",
        &kappas_rel,
        &format!(
            "Q_∞/Q_0 = {:.4} (CG {used} it, rel {rel:.1e}, {cg_s:.1} s); 1/N = {:.2e}",
            q_inf / q0,
            1.0 / grid.pixels() as f64
        ),
        json,
    );
    // Noiseless supports: measured minimum κ against λ_min(B_SS)/k.
    for k in [2usize, 4, 6] {
        let mut support = Vec::new();
        while support.len() < k {
            let p = rng.below(grid.pixels());
            if !support.contains(&p) {
                support.push(p);
            }
        }
        let mut truth = vec![0.0; grid.pixels()];
        for &p in &support {
            truth[p] = 0.2 + 0.8 * rng.uniform();
        }
        let scene_k = Scene {
            vis: predict(s, grid, &truth),
            dirty: convolve(b, &truth),
            truth,
        };
        let (q0, steps) = tracked_run(s, grid, b, &scene_k, 1.0, 200, None);
        let mut q = q0;
        let mut kappas = Vec::new();
        for &(peak, q_next) in &steps {
            if q <= 1e-24 * q0 {
                break;
            }
            kappas.push(peak * peak / (2.0 * q));
            q = q_next;
        }
        let lambda = min_eigenvalue(&gram(b, &support), k);
        let eta = erc(b, grid, &support).unwrap_or(f64::NAN);
        let note = format!(
            "bound λ_min/k = {:.3e} (λ_min {:.3}); ERC {:.3}; min κ / bound = {:.2}",
            lambda / k as f64,
            lambda,
            eta,
            kappas.iter().cloned().fold(f64::INFINITY, f64::min) / (lambda / k as f64)
        );
        report(
            &format!("{k} sources, noiseless, γ 1"),
            &kappas,
            &note,
            json,
        );
    }
    json.close_list();
}

/// E4: one unit source 0.5 and 0.3 pixels off the grid centre of a pixel;
/// the misfit still converges, the model is no longer sparse.
fn e4_offgrid(s: &Sampling, grid: &Grid, b: &Psf, json: &mut Json) {
    println!("\nE4 off-grid unit source at (+0.5, +0.3) pixels, noiseless, stop at |r| < 1e-4");
    println!("| gain | steps | nonzero pixels | model flux | Q_end / Q_0 | max |r| end |");
    println!("| ---: | ---: | ---: | ---: | ---: | ---: |");
    json.open_list("e4");
    let (l0, m0) = grid.lm(grid.index(grid.n / 2 + 5, grid.n / 2 - 7));
    let vis = point_vis(s, l0 + 0.5 * grid.cell, m0 + 0.3 * grid.cell);
    let d = dirty(s, grid, &vis);
    for gain in [0.1, 1.0] {
        let result = hogbom(
            &d,
            b,
            &CleanSettings {
                gain,
                iterations: 20000,
                threshold: 1e-4,
                patch: None,
            },
        );
        let model_vis = predict(s, grid, &result.model);
        let q_end = misfit(s, &vis, &model_vis);
        let q0 = misfit(s, &vis, &vec![(0.0, 0.0); s.len()]);
        let nonzero = result.model.iter().filter(|&&v| v != 0.0).count();
        let flux: f64 = result.model.iter().sum();
        let end_peak = argmax_abs(&result.residual).1.abs();
        println!(
            "| {gain} | {} | {nonzero} | {flux:.4} | {:.3e} | {end_peak:.2e} |",
            result.steps.len(),
            q_end / q0
        );
        json.item();
        json.num("gain", gain);
        json.int("steps", result.steps.len());
        json.int("nonzero", nonzero);
        json.num("flux", flux);
        json.num("q_ratio", q_end / q0);
        json.num("end_peak", end_peak);
        json.close();
    }
    json.close_list();
}

/// E5: Clark's minor cycle with a `±h` beam patch. The working residual
/// drifts from the true one; a step descends iff `r_p / r̃_p > γ/2`. Count
/// violations with and without Clark's stopping rule, and run a full
/// major/minor loop.
fn e5_clark(s: &Sampling, grid: &Grid, b: &Psf, sc: &Scene, json: &mut Json) {
    println!("\nE5 Clark minor cycle (200 steps from the exact residual): steps that raise Q");
    println!(
        "| gain | patch | f = max |b| outside | rises in 200 | first rise | rises under Clark's stop | steps under Clark's stop | rises under the provable stop | steps under the provable stop |"
    );
    println!("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |");
    json.open_list("e5");
    for gain in [0.1, 1.0] {
        for h in [4usize, 8, 16] {
            let f = b.outside_patch(h);
            let mut working = sc.dirty.clone();
            let mut truth = sc.dirty.clone();
            let peak0 = argmax_abs(&working).1.abs();
            let mut rises = 0;
            let mut first = None;
            let mut rises_clark = 0;
            let mut steps_clark = 0;
            let mut clark_active = true;
            // The provable rule: continue while f · Σ|c_j| < (1 − γ/2) |r̃_p|,
            // since the truncation error is at most f times the cleaned flux.
            let mut cleaned = 0.0;
            let mut provable_active = true;
            let mut rises_provable = 0;
            let mut steps_provable = 0;
            for step in 0..200 {
                let (p, peak) = argmax_abs(&working);
                if clark_active && peak.abs() < f * peak0 {
                    clark_active = false;
                }
                if provable_active && f * cleaned >= (1.0 - gain / 2.0) * peak.abs() {
                    provable_active = false;
                }
                let c = gain * peak;
                let true_r = truth[p];
                // Exact change of Q for a component c at p: −c r_p + c²/2.
                let dq = -c * true_r + 0.5 * c * c;
                if dq > 0.0 {
                    rises += 1;
                    first.get_or_insert(step);
                    if clark_active {
                        rises_clark += 1;
                    }
                }
                if clark_active {
                    steps_clark += 1;
                }
                if provable_active {
                    steps_provable += 1;
                    if dq > 0.0 {
                        rises_provable += 1;
                    }
                }
                cleaned += c.abs();
                subtract(&mut working, b, p, c, Some(h));
                subtract(&mut truth, b, p, c, None);
            }
            println!(
                "| {gain} | ±{h} | {f:.4} | {rises} | {} | {rises_clark} | {steps_clark} | {rises_provable} | {steps_provable} |",
                first.map(|v| v.to_string()).unwrap_or_else(|| "–".into())
            );
            json.item();
            json.num("gain", gain);
            json.int("patch", h);
            json.num("outside", f);
            json.int("rises", rises);
            json.int("first_rise", first.unwrap_or(usize::MAX));
            json.int("rises_clark", rises_clark);
            json.int("steps_clark", steps_clark);
            json.int("rises_provable", rises_provable);
            json.int("steps_provable", steps_provable);
            json.close();
        }
    }
    json.close_list();
    // Major/minor loop: 100 minor steps on a ±8 patch, then an exact residual.
    println!(
        "\nE5b major/minor loop, ±8 patch, 100 minor steps per major cycle, gain 0.1: Q after each major cycle / Q_0"
    );
    let mut model = vec![0.0; grid.pixels()];
    let mut model_vis = vec![(0.0, 0.0); s.len()];
    let q0 = misfit(s, &sc.vis, &model_vis);
    let mut line = String::new();
    json.open_list("e5b_q_ratio");
    for _major in 0..12 {
        let residual_vis: Vec<Vis> = sc
            .vis
            .iter()
            .zip(&model_vis)
            .map(|(v, m)| (v.0 - m.0, v.1 - m.1))
            .collect();
        let d = dirty(s, grid, &residual_vis);
        let minor = hogbom(
            &d,
            b,
            &CleanSettings {
                gain: 0.1,
                iterations: 100,
                threshold: 0.0,
                patch: Some(8),
            },
        );
        for (p, (total, &c)) in model.iter_mut().zip(&minor.model).enumerate() {
            if c != 0.0 {
                *total += c;
                add_atom(s, grid, p, c, &mut model_vis);
            }
        }
        let q = misfit(s, &sc.vis, &model_vis) / q0;
        let _ = write!(line, "{q:.4} ");
        let _ = write!(json.0, "{q:e}, ");
    }
    json.close_list();
    println!("{line}");
    let error: f64 = model
        .iter()
        .zip(&sc.truth)
        .map(|(m, t)| (m - t).abs())
        .fold(0.0, f64::max);
    println!("max |model − truth| after 12 major cycles: {error:.4}");
    json.num("e5b_max_error", error);
}

/// E6: a Gaussian disc (FWHM 12 pixels), noiseless; every gain drives Q to
/// zero, but the limit model depends on the gain.
fn e6_extended(s: &Sampling, grid: &Grid, b: &Psf, json: &mut Json) {
    println!("\nE6 Gaussian disc FWHM 12 px, noiseless, stop at |r| < 1e-3 or 30000 steps");
    println!(
        "| gain | steps | Q_end / Q_0 | rms(model − truth) in FWHM / peak | most negative model pixel | rms(model_γ − model_0.01) |"
    );
    println!("| ---: | ---: | ---: | ---: | ---: | ---: |");
    json.open_list("e6");
    let sigma = 12.0 / (8.0 * 2f64.ln()).sqrt();
    let centre = (grid.n / 2) as f64;
    let truth: Vec<f64> = (0..grid.pixels())
        .map(|p| {
            let dx = (p % grid.n) as f64 - centre;
            let dy = (p / grid.n) as f64 - centre;
            (-(dx * dx + dy * dy) / (2.0 * sigma * sigma)).exp()
        })
        .collect();
    let vis = predict(s, grid, &truth);
    let d = convolve(b, &truth);
    let q0 = misfit(s, &vis, &vec![(0.0, 0.0); s.len()]);
    let mut reference: Option<Vec<f64>> = None;
    for gain in [0.01, 0.1, 1.0] {
        let result = hogbom(
            &d,
            b,
            &CleanSettings {
                gain,
                iterations: 30000,
                threshold: 1e-3,
                patch: None,
            },
        );
        let q_end = misfit(s, &vis, &predict(s, grid, &result.model));
        let mut inside = 0usize;
        let mut sum_sq = 0.0;
        for (p, (found, expected)) in result.model.iter().zip(&truth).enumerate() {
            let dx = (p % grid.n) as f64 - centre;
            let dy = (p / grid.n) as f64 - centre;
            if dx * dx + dy * dy <= 36.0 {
                inside += 1;
                sum_sq += (found - expected).powi(2);
            }
        }
        let rms = (sum_sq / inside as f64).sqrt();
        let most_negative = result.model.iter().cloned().fold(0.0, f64::min);
        let drift = match &reference {
            Some(r) => {
                let sq: f64 = r
                    .iter()
                    .zip(&result.model)
                    .map(|(a, b)| (a - b).powi(2))
                    .sum();
                (sq / grid.pixels() as f64).sqrt()
            }
            None => 0.0,
        };
        if reference.is_none() {
            reference = Some(result.model.clone());
        }
        println!(
            "| {gain} | {} | {:.3e} | {rms:.4} | {most_negative:.4} | {drift:.4} |",
            result.steps.len(),
            q_end / q0
        );
        json.item();
        json.num("gain", gain);
        json.int("steps", result.steps.len());
        json.num("q_ratio", q_end / q0);
        json.num("rms_in_fwhm", rms);
        json.num("most_negative", most_negative);
        json.num("rms_against_gain_0_01", drift);
        json.close();
    }
    json.close_list();
}

/// E2c: recovery with noise. Sources at least 8 pixels apart, fluxes 0.2-1,
/// image noise 0.01 (one per cent of a unit source), gain 0.1, stop at
/// `|r| < 5σ`. Counts picks on the support, exact supports (every source
/// found, no false pixel) and the flux error, against the ERC.
fn e2c_noisy(s: &Sampling, grid: &Grid, b: &Psf, rng: &mut Rng, json: &mut Json) {
    let trials = 100;
    let sigma_img = 0.01;
    let sum_w2: f64 = s.w.iter().map(|w| w * w).sum();
    let sigma_vis = sigma_img / sum_w2.sqrt();
    let noise: Vec<Vec<f64>> = (0..5)
        .map(|_| {
            let vis: Vec<Vis> = (0..s.len())
                .map(|_| (sigma_vis * rng.normal(), sigma_vis * rng.normal()))
                .collect();
            dirty(s, grid, &vis)
        })
        .collect();
    let measured_sigma =
        (noise[0].iter().map(|v| v * v).sum::<f64>() / noise[0].len() as f64).sqrt();
    println!(
        "\nE2c recovery with noise, {trials} trials per k, sources ≥ 8 px apart, image noise {sigma_img} (measured {measured_sigma:.4}), gain 0.1, stop at |r| < 5σ"
    );
    println!(
        "| k | all picks on support | exact support | mean picks on support | mean false pixels | rms flux error / σ | ERC < 1 | exact support given ERC |"
    );
    println!("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |");
    json.open_list("e2c");
    for k in [2usize, 4, 6, 8, 12] {
        let mut all_on = 0;
        let mut exact = 0;
        let mut frac_sum = 0.0;
        let mut false_sum = 0.0;
        let mut err_sum = 0.0;
        let mut erc_ok = 0;
        let mut exact_given_erc = 0;
        for trial in 0..trials {
            let mut support: Vec<usize> = Vec::with_capacity(k);
            while support.len() < k {
                let p = rng.below(grid.pixels());
                let far = support.iter().all(|&q| {
                    let dx = (p % grid.n) as isize - (q % grid.n) as isize;
                    let dy = (p / grid.n) as isize - (q / grid.n) as isize;
                    dx.abs().max(dy.abs()) >= 8
                });
                if far {
                    support.push(p);
                }
            }
            let mut truth = vec![0.0; grid.pixels()];
            for &p in &support {
                truth[p] = 0.2 + 0.8 * rng.uniform();
            }
            let mut d = convolve(b, &truth);
            for (v, n) in d.iter_mut().zip(&noise[trial % noise.len()]) {
                *v += n;
            }
            let result = hogbom(
                &d,
                b,
                &CleanSettings {
                    gain: 0.1,
                    iterations: 5000,
                    threshold: 5.0 * sigma_img,
                    patch: None,
                },
            );
            let on = result
                .steps
                .iter()
                .filter(|st| support.contains(&st.pixel))
                .count();
            let total = result.steps.len().max(1);
            let found = support.iter().all(|&p| result.model[p] != 0.0);
            let false_pixels = result
                .model
                .iter()
                .enumerate()
                .filter(|&(p, &v)| v != 0.0 && !support.contains(&p))
                .count();
            let err = (support
                .iter()
                .map(|&p| (result.model[p] - truth[p]).powi(2))
                .sum::<f64>()
                / k as f64)
                .sqrt()
                / sigma_img;
            let is_exact = found && false_pixels == 0;
            if on == result.steps.len() {
                all_on += 1;
            }
            if is_exact {
                exact += 1;
            }
            frac_sum += on as f64 / total as f64;
            false_sum += false_pixels as f64;
            err_sum += err;
            if erc(b, grid, &support).is_some_and(|eta| eta < 1.0) {
                erc_ok += 1;
                if is_exact {
                    exact_given_erc += 1;
                }
            }
        }
        let n = trials as f64;
        println!(
            "| {k} | {all_on} | {exact} | {:.3} | {:.2} | {:.2} | {erc_ok} | {exact_given_erc} |",
            frac_sum / n,
            false_sum / n,
            err_sum / n
        );
        json.item();
        json.int("k", k);
        json.int("trials", trials);
        json.int("all_picks_on_support", all_on);
        json.int("exact_support", exact);
        json.num("mean_pick_fraction", frac_sum / n);
        json.num("mean_false_pixels", false_sum / n);
        json.num("rms_flux_error_sigma", err_sum / n);
        json.int("erc_holds", erc_ok);
        json.int("exact_given_erc", exact_given_erc);
        json.close();
    }
    json.num("e2c_measured_sigma", measured_sigma);
    json.close_list();
}

/// A Gaussian blob kernel of the given FWHM in pixels (a delta for 0),
/// as (half-width, values over the (2h+1)² square).
fn blob(fwhm: f64) -> (isize, Vec<f64>) {
    if fwhm <= 0.0 {
        return (0, vec![1.0]);
    }
    let sigma = fwhm / (8.0 * 2f64.ln()).sqrt();
    let h = (3.5 * sigma).ceil() as isize;
    let w = (2 * h + 1) as usize;
    let mut g = vec![0.0; w * w];
    for j in -h..=h {
        for i in -h..=h {
            g[(i + h) as usize + w * (j + h) as usize] =
                (-((i * i + j * j) as f64) / (2.0 * sigma * sigma)).exp();
        }
    }
    (h, g)
}

/// `⟨A, C⟩` for a blob atom `A` at the origin and a blob atom `C` at offset
/// `(dx, dy)`: `Σ_{p∈A} Σ_{q∈C} g_A(p) g_C(q) b(p − q − (dx, dy))`.
fn blob_inner(b: &Psf, a: &(isize, Vec<f64>), c: &(isize, Vec<f64>), dx: isize, dy: isize) -> f64 {
    let (ha, ga) = a;
    let (hc, gc) = c;
    let wa = (2 * ha + 1) as usize;
    let wc = (2 * hc + 1) as usize;
    let mut sum = 0.0;
    for j in -ha..=*ha {
        for i in -ha..=*ha {
            let g1 = ga[(i + ha) as usize + wa * (j + ha) as usize];
            for l in -hc..=*hc {
                for k in -hc..=*hc {
                    let g2 = gc[(k + hc) as usize + wc * (l + hc) as usize];
                    sum += g1 * g2 * b.at(i - k - dx, j - l - dy);
                }
            }
        }
    }
    sum
}

/// E7: coherence of a multi-scale dictionary (delta and Gaussians of FWHM
/// 2, 4, 8 pixels) under the same PSF: the largest normalised inner product
/// between distinct atoms over offsets `(dx, 0)` and `(dx, dx)`, `dx ≤ 16`.
fn e7_multiscale(b: &Psf, json: &mut Json) {
    let scales = [0.0, 2.0, 4.0, 8.0];
    let kernels: Vec<(isize, Vec<f64>)> = scales.iter().map(|&f| blob(f)).collect();
    let norms: Vec<f64> = kernels
        .iter()
        .map(|k| blob_inner(b, k, k, 0, 0).sqrt())
        .collect();
    println!("\nE7 multi-scale dictionary coherence (delta, Gaussian FWHM 2, 4, 8 px)");
    println!("| scale A | scale C | max |⟨A,C⟩| / norms | at offset | within-scale, unit offset |");
    println!("| ---: | ---: | ---: | --- | ---: |");
    json.open_list("e7");
    let mut overall = 0.0_f64;
    for ia in 0..scales.len() {
        for ic in ia..scales.len() {
            let mut best = 0.0_f64;
            let mut at = (0, 0);
            for dx in 0..=16isize {
                for &dy in &[0isize, dx] {
                    if ia == ic && dx == 0 && dy == 0 {
                        continue;
                    }
                    let v = blob_inner(b, &kernels[ia], &kernels[ic], dx, dy).abs()
                        / (norms[ia] * norms[ic]);
                    if v > best {
                        best = v;
                        at = (dx, dy);
                    }
                }
            }
            let unit = if ia == ic {
                blob_inner(b, &kernels[ia], &kernels[ic], 1, 0).abs() / (norms[ia] * norms[ic])
            } else {
                f64::NAN
            };
            overall = overall.max(best);
            println!(
                "| {} | {} | {best:.4} | ({}, {}) | {} |",
                scales[ia],
                scales[ic],
                at.0,
                at.1,
                if unit.is_nan() {
                    "–".to_string()
                } else {
                    format!("{unit:.4}")
                }
            );
            json.item();
            json.num("scale_a", scales[ia]);
            json.num("scale_c", scales[ic]);
            json.num("max_coherence", best);
            json.int("at_dx", at.0 as usize);
            json.int("at_dy", at.1 as usize);
            json.num("unit_offset", unit);
            json.close();
        }
    }
    json.close_list();
    json.num("e7_overall_coherence", overall);
    println!("overall multi-scale coherence {overall:.4}");
}
