//! Measurements for the visibility-free normal operator
//! (`research/gridder-theory.md`). One JSON object per line on stdout.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! ```text
//! gridder_gram_bench MS SIZE SCALE_ASEC ROBUST MODE [ARGS]
//!   read                           read and weight only (the baseline of perf)
//!   pass EPS single|double REPS    REPS grid+degrid passes of the sparse model
//!   build S THETA single|double EPS    set the operator up
//!   apply S THETA single|double EPS REPS   set up, then REPS applications
//!   accuracy EPS_LIST CONFIGS      errors against the gridder at 1e-10
//!   budget                         weight-aware support and averaging counts
//! ```
//! `ROBUST` is a number, or `natural`. CONFIGS is `S:THETA:EPS:P,...` with P
//! `s` or `d`.

use rang_core::clean_certified::{Complex, Measurement};
use rang_core::gmclean::input::{self, Selection};
use rang_core::gmclean::measure::GridMeasurement;
use rang_core::gridder_gram::{GramOperator, WExpansion};
use rang_core::weights::WeightClass;
use rang_core::wgridder::{self, C_LIGHT, Options, Real};
use std::time::Instant;

struct Input {
    uvw: Vec<f64>,
    freq: Vec<f64>,
    vis: Vec<Complex<f64>>,
    wgt: Vec<f64>,
    n: usize,
    cell: f64,
    interval: f64,
}

fn cpu_seconds() -> f64 {
    let stat = std::fs::read_to_string("/proc/self/stat").unwrap_or_default();
    let after = stat.rsplit(')').next().unwrap_or("");
    let f: Vec<&str> = after.split_whitespace().collect();
    let ticks = |i: usize| f.get(i).and_then(|v| v.parse::<f64>().ok()).unwrap_or(0.0);
    (ticks(11) + ticks(12)) / 100.0
}

fn peak_rss_gb() -> f64 {
    let status = std::fs::read_to_string("/proc/self/status").unwrap_or_default();
    status
        .lines()
        .find(|l| l.starts_with("VmHWM"))
        .and_then(|l| l.split_whitespace().nth(1))
        .and_then(|v| v.parse::<f64>().ok())
        .map_or(0.0, |kb| kb / 1024.0 / 1024.0)
}

fn load() -> String {
    std::fs::read_to_string("/proc/loadavg")
        .unwrap_or_default()
        .split_whitespace()
        .next()
        .unwrap_or("?")
        .to_string()
}

fn read_input(ms: &str, n: usize, cell: f64, robust: &str) -> Result<Input, String> {
    let selection = Selection {
        data_column: "DATA".into(),
        ..Selection::default()
    };
    let data = input::read_ms(std::path::Path::new(ms), &selection)?;
    let class = if robust == "natural" {
        WeightClass::Natural
    } else {
        WeightClass::Briggs(robust.parse().map_err(|_| "robust")?)
    };
    let weights = input::gridding_weights(&data, class, n, cell)?;
    let nchan = data.freq.len();
    let (mut uvw, mut vis, mut wgt) = (Vec::new(), Vec::new(), Vec::new());
    let stride: usize = std::env::var("GRAM_STRIDE")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(1);
    for row in (0..data.rows()).step_by(stride) {
        let w = &weights.weights[row * nchan..(row + 1) * nchan];
        if w.iter().any(|&x| x != 0.0) {
            uvw.extend_from_slice(&data.uvw[3 * row..3 * row + 3]);
            vis.extend_from_slice(&data.vis[row * nchan..(row + 1) * nchan]);
            wgt.extend_from_slice(w);
        }
    }
    let sum: f64 = wgt.iter().sum();
    for w in &mut wgt {
        *w /= sum;
    }
    Ok(Input {
        uvw,
        freq: data.freq.clone(),
        vis,
        wgt,
        n,
        cell,
        interval: 0.0,
    })
}

fn options(inp: &Input, epsilon: f64) -> Options {
    Options {
        nx: inp.n,
        ny: inp.n,
        pixsize_x: inp.cell,
        pixsize_y: inp.cell,
        epsilon,
        flip_v: true,
        flip_w: true,
        ..Options::default()
    }
}

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> f64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0 >> 11) as f64 / (1u64 << 53) as f64
    }
}

/// 200 random components over the whole image and all four corners.
fn sparse_model(n: usize) -> Vec<f64> {
    let mut rng = Rng(20261102);
    let mut m = vec![0.0; n * n];
    for _ in 0..200 {
        let (i, j) = (
            (rng.next() * n as f64) as usize,
            (rng.next() * n as f64) as usize,
        );
        m[i * n + j] = (rng.next() * 4.0 - 3.0).exp();
    }
    for (i, j) in [(0, 0), (0, n - 1), (n - 1, 0), (n - 1, n - 1)] {
        m[i * n + j] = 1.0;
    }
    m
}

/// White noise in every pixel: the operator on the least sparse input.
fn dense_model(n: usize) -> Vec<f64> {
    let mut rng = Rng(424242);
    (0..n * n).map(|_| rng.next() - 0.5).collect()
}

fn errors(want: &[f64], got: &[f64], m: &[f64]) -> (f64, f64) {
    let l1: f64 = m.iter().map(|v| v.abs()).sum();
    let (mut sup, mut e2, mut r2) = (0.0_f64, 0.0, 0.0);
    for (a, b) in want.iter().zip(got) {
        sup = sup.max((a - b).abs());
        e2 += (a - b) * (a - b);
        r2 += a * a;
    }
    (sup / l1, (e2 / r2).sqrt())
}

fn pass<T: Real + Send + Sync>(inp: &Input, epsilon: f64, reps: usize) -> Result<(), String> {
    let t = Instant::now();
    let measure: GridMeasurement<T> = GridMeasurement::new(
        inp.uvw.clone(),
        inp.freq.clone(),
        vec![Complex::new(0.0, 0.0); inp.vis.len()],
        inp.wgt.clone(),
        inp.n,
        inp.cell,
        epsilon,
        options(inp, epsilon),
    )?;
    let prepare = t.elapsed().as_secs_f64();
    let m = sparse_model(inp.n);
    let (cpu0, t) = (cpu_seconds(), Instant::now());
    for _ in 0..reps {
        std::hint::black_box(measure.gram_apply(&m)?);
    }
    let plan = wgridder::plan::<T>(
        &options(inp, epsilon),
        &inp.uvw,
        &inp.freq,
        None,
        Some(&inp.wgt.iter().map(|w| T::of(*w)).collect::<Vec<T>>()),
        None,
    )?;
    println!(
        "{{\"mode\":\"pass\",\"eps\":{epsilon:e},\"bits\":{},\"reps\":{reps},\"prepare_s\":{prepare:.3},\"wall_s_per_pass\":{:.3},\"cpu_s_per_pass\":{:.3},\"peak_rss_gb\":{:.2},\"load\":{},\"supp\":{},\"nu\":{},\"nv\":{},\"nplanes\":{},\"nvis\":{},\"wmin\":{:.2},\"wmax\":{:.2},\"nm1min\":{:e},\"nm1max\":{:e},\"dw\":{:.3}}}",
        8 * std::mem::size_of::<T>(),
        t.elapsed().as_secs_f64() / reps as f64,
        (cpu_seconds() - cpu0) / reps as f64,
        peak_rss_gb(),
        load(),
        plan.supp,
        plan.nu,
        plan.nv,
        plan.nplanes,
        plan.nvis,
        plan.wmin_d,
        plan.wmax_d,
        plan.nm1min,
        plan.nm1max,
        plan.dw,
    );
    Ok(())
}

fn build_operator<T: Real + Send + Sync>(
    inp: &Input,
    stencil: usize,
    theta: f64,
    epsilon: f64,
) -> Result<GramOperator<T>, String> {
    let ridge = 1e-3 * (epsilon * epsilon).max(1e-14);
    let ex = WExpansion::new(stencil, theta, ridge)?;
    GramOperator::<T>::new(
        &options(inp, epsilon),
        &inp.uvw,
        &inp.freq,
        &inp.wgt,
        &ex,
        epsilon,
    )
}

fn stats_json<T: Real + Send + Sync>(op: &GramOperator<T>) -> String {
    let s = op.stats;
    format!(
        "\"planes\":{},\"stencil\":{},\"theta\":{},\"wmin\":{:.2},\"wmax\":{:.2},\"x_range\":{:e},\"sup_error\":{:e},\"lebesgue\":{:.3},\"active_pairs\":{},\"cube_gb\":{:.3},\"setup_grid_s\":{:.2},\"setup_fft_s\":{:.2},\"sparsity_1e7\":{:.3},\"hermitian\":{:e},\"ffts_per_apply\":{}",
        s.planes,
        s.stencil,
        s.theta,
        s.wmin,
        s.wmax,
        s.x_range,
        s.sup_error,
        s.lebesgue,
        s.active_pairs,
        s.cube_bytes as f64 / 1e9,
        s.setup_grid_seconds,
        s.setup_fft_seconds,
        s.spectral_sparsity,
        s.hermitian_check,
        op.ffts_per_apply(),
    )
}

fn operator_run<T: Real + Send + Sync>(
    inp: &Input,
    stencil: usize,
    theta: f64,
    epsilon: f64,
    reps: usize,
) -> Result<(), String> {
    let (cpu0, t) = (cpu_seconds(), Instant::now());
    let op = build_operator::<T>(inp, stencil, theta, epsilon)?;
    let (build_wall, build_cpu) = (t.elapsed().as_secs_f64(), cpu_seconds() - cpu0);
    let m = sparse_model(inp.n);
    let (cpu0, t) = (cpu_seconds(), Instant::now());
    for _ in 0..reps {
        std::hint::black_box(op.apply(&m)?);
    }
    println!(
        "{{\"mode\":\"operator\",\"eps\":{epsilon:e},\"bits\":{},\"reps\":{reps},\"build_wall_s\":{build_wall:.2},\"build_cpu_s\":{build_cpu:.2},\"wall_s_per_apply\":{:.3},\"cpu_s_per_apply\":{:.3},\"peak_rss_gb\":{:.2},\"load\":{},{}}}",
        8 * std::mem::size_of::<T>(),
        t.elapsed().as_secs_f64() / reps.max(1) as f64,
        (cpu_seconds() - cpu0) / reps.max(1) as f64,
        peak_rss_gb(),
        load(),
        stats_json(&op),
    );
    Ok(())
}

fn accuracy(inp: &Input, eps_list: &str, configs: &str) -> Result<(), String> {
    let (sparse, dense) = (sparse_model(inp.n), dense_model(inp.n));
    let reference: GridMeasurement<f64> = GridMeasurement::new(
        inp.uvw.clone(),
        inp.freq.clone(),
        vec![Complex::new(0.0, 0.0); inp.vis.len()],
        inp.wgt.clone(),
        inp.n,
        inp.cell,
        1e-10,
        options(inp, 1e-10),
    )?;
    let want_sparse = reference.gram_apply(&sparse)?;
    let want_dense = reference.gram_apply(&dense)?;
    drop(reference);
    let report = |name: String, s: &[f64], d: &[f64]| {
        let (a, b) = errors(&want_sparse, s, &sparse);
        let (c, e) = errors(&want_dense, d, &dense);
        println!(
            "{{\"mode\":\"accuracy\",\"name\":\"{name}\",\"sparse_sup_over_l1\":{a:e},\"sparse_rel_l2\":{b:e},\"dense_sup_over_l1\":{c:e},\"dense_rel_l2\":{e:e},\"load\":{}}}",
            load()
        );
    };
    for token in eps_list.split(',').filter(|t| !t.is_empty()) {
        let (e, p) = token.split_once(':').ok_or("EPS:P")?;
        let epsilon: f64 = e.parse().map_err(|_| "eps")?;
        if p == "s" {
            let g: GridMeasurement<f32> = GridMeasurement::new(
                inp.uvw.clone(),
                inp.freq.clone(),
                vec![Complex::new(0.0, 0.0); inp.vis.len()],
                inp.wgt.clone(),
                inp.n,
                inp.cell,
                epsilon,
                options(inp, epsilon),
            )?;
            report(
                format!("gridder f32 eps {e}"),
                &g.gram_apply(&sparse)?,
                &g.gram_apply(&dense)?,
            );
        } else {
            let g: GridMeasurement<f64> = GridMeasurement::new(
                inp.uvw.clone(),
                inp.freq.clone(),
                vec![Complex::new(0.0, 0.0); inp.vis.len()],
                inp.wgt.clone(),
                inp.n,
                inp.cell,
                epsilon,
                options(inp, epsilon),
            )?;
            report(
                format!("gridder f64 eps {e}"),
                &g.gram_apply(&sparse)?,
                &g.gram_apply(&dense)?,
            );
        }
    }
    for token in configs.split(',').filter(|t| !t.is_empty()) {
        let f: Vec<&str> = token.split(':').collect();
        let (stencil, theta, epsilon): (usize, f64, f64) = (
            f[0].parse().map_err(|_| "S")?,
            f[1].parse().map_err(|_| "theta")?,
            f[2].parse().map_err(|_| "eps")?,
        );
        macro_rules! row {
            ($t:ty) => {{
                let t = Instant::now();
                let op = build_operator::<$t>(inp, stencil, theta, epsilon)?;
                let build = t.elapsed().as_secs_f64();
                let t = Instant::now();
                let s = op.apply(&sparse)?;
                let apply = t.elapsed().as_secs_f64();
                let d = op.apply(&dense)?;
                println!(
                    "{{\"mode\":\"config\",\"token\":\"{token}\",\"build_s\":{build:.2},\"apply_s\":{apply:.3},{}}}",
                    stats_json(&op)
                );
                report(format!("gram {token}"), &s, &d);
            }};
        }
        if f[3] == "s" {
            row!(f32);
        } else {
            row!(f64);
        }
    }
    Ok(())
}

/// Support needed at each accuracy for the oversampling closest to `sigma`.
fn kernel_curve(sigma: f64) -> Vec<(usize, f64, f64)> {
    let mut best: Vec<(usize, f64, f64)> = Vec::new();
    for i in 0..wgridder::kernel_count() {
        let row = wgridder::kernel_row(i).expect("row");
        if row.ndim != 2 || row.singleprec || (row.ofactor - sigma).abs() > 0.13 {
            continue;
        }
        match best.iter_mut().find(|b| b.0 == row.w) {
            Some(b) if row.epsilon < b.1 => {
                b.1 = row.epsilon;
                b.2 = row.ofactor;
            }
            Some(_) => {}
            None => best.push((row.w, row.epsilon, row.ofactor)),
        }
    }
    best.sort_by_key(|b| b.0);
    best
}

/// Weight-aware budget: minimise `Σ_q S_q^3` under `Σ_q W_q ε(S_q)^k ≤ ε^k`
/// (`Σ W = 1`) by a Lagrange sweep over the histogram of weights. `k = 1` is
/// the triangle bound on `⟨e, a_p⟩`; `k = 2` is the weighted norm `‖e‖_W`,
/// which Cauchy-Schwarz puts above it, so its savings cannot exceed those of
/// `k = 1`. `S³` counts w-kernel, u and v taps.
fn budget(inp: &Input) -> Result<(), String> {
    let nvis = inp.wgt.iter().filter(|w| **w != 0.0).count() as f64;
    let mean = 1.0 / nvis;
    // Histogram of log10(W / mean).
    const BINS: usize = 400;
    let edge = |b: usize| -8.0 + 16.0 * b as f64 / BINS as f64;
    let mut count = vec![0.0; BINS];
    let mut total = vec![0.0; BINS];
    let mut r2 = 0.0;
    for &w in &inp.wgt {
        if w == 0.0 {
            continue;
        }
        let x = (w / mean).log10();
        let b = (((x + 8.0) / 16.0 * BINS as f64) as usize).min(BINS - 1);
        count[b] += 1.0;
        total[b] += w;
        r2 += (w / mean) * (w / mean);
    }
    let centre: Vec<f64> = (0..BINS)
        .map(|b| 10f64.powf(0.5 * (edge(b) + edge(b + 1))))
        .collect();
    let spread: Vec<(f64, f64)> = {
        let mut cum = 0.0;
        let mut q = Vec::new();
        for b in 0..BINS {
            cum += count[b] / nvis;
            q.push((cum, centre[b]));
        }
        q
    };
    let quant = |f: f64| spread.iter().find(|c| c.0 >= f).map_or(0.0, |c| c.1);
    println!(
        "{{\"mode\":\"weights\",\"nvis\":{nvis},\"w_over_mean_p01\":{:.3},\"p50\":{:.3},\"p99\":{:.3},\"mean_r2\":{:.3},\"neff_over_n\":{:.3}}}",
        quant(0.01),
        quant(0.5),
        quant(0.99),
        r2 / nvis,
        nvis / r2
    );
    for (sigma, power) in [(1.5, 1), (2.0, 1), (1.5, 2), (2.0, 2)] {
        let curve = kernel_curve(sigma);
        for target in [1e-3, 1e-4, 1e-6] {
            // Global: smallest support at or below the target.
            let Some(global) = curve.iter().find(|c| c.1 <= target) else {
                continue;
            };
            let cost_global = (global.0 as f64).powi(3);
            // Lagrange sweep: each bin picks argmin S³/(W count) ... + λ ε(S).
            let (mut lo, mut hi) = (1e-6_f64, 1e24_f64);
            let mut best = (cost_global, target);
            for _ in 0..80 {
                let lam = (lo * hi).sqrt();
                let (mut cost, mut err) = (0.0, 0.0);
                for b in 0..BINS {
                    if count[b] == 0.0 {
                        continue;
                    }
                    let (mut bc, mut be, mut bj) = (f64::INFINITY, 0.0, f64::INFINITY);
                    for c in &curve {
                        let s3 = (c.0 as f64).powi(3);
                        let cost_e = c.1.powi(power);
                        let j = count[b] * s3 + lam * total[b] * cost_e;
                        if j < bj {
                            bj = j;
                            bc = count[b] * s3;
                            be = total[b] * cost_e;
                        }
                    }
                    cost += bc;
                    err += be;
                }
                if err <= f64::powi(target, power) {
                    hi = lam;
                    best = (cost / nvis, err.powf(1.0 / f64::from(power)));
                } else {
                    lo = lam;
                }
            }
            println!(
                "{{\"mode\":\"budget\",\"norm\":{power},\"sigma\":{sigma},\"target\":{target:e},\"global_supp\":{},\"global_eps\":{:e},\"global_s3\":{cost_global},\"aware_s3\":{:.2},\"aware_err\":{:e},\"s3_ratio\":{:.4}}}",
                global.0,
                global.1,
                best.0,
                best.1,
                best.0 / cost_global
            );
        }
    }
    // Averaging under a Gram bound. Averaging a block of phase spread δ at the
    // image corner changes an atom by about δ²/24, so a block is admissible
    // when δ²/24 ≤ ε. Count the factor in time for every baseline, taking the
    // uvw difference of consecutive rows on the same baseline as the rate is
    // not available here: earth rotation at 7.29e-5 rad/s times |uv|.
    let nchan = inp.freq.len();
    let half_n = inp.n as f64 / 2.0;
    let r_max = 2f64.sqrt() * half_n * inp.cell;
    let interval = if inp.interval > 0.0 {
        inp.interval
    } else {
        1.0
    };
    for &eps in &[1e-6_f64, 1e-4, 1e-3] {
        let delta = (24.0 * eps).sqrt();
        let mut merged = 0.0;
        for c in inp.uvw.chunks(3) {
            let b = (c[0] * c[0] + c[1] * c[1]).sqrt();
            for f in &inp.freq {
                let rate = 7.29e-5 * b * f / C_LIGHT;
                let per_second = 2.0 * std::f64::consts::PI * rate * r_max;
                let block = (delta / per_second.max(1e-30) / interval).floor().max(1.0);
                merged += 1.0 / block;
            }
        }
        println!(
            "{{\"mode\":\"averaging\",\"eps\":{eps:e},\"interval_s\":{interval},\"nchan\":{nchan},\"after_over_before\":{:.4}}}",
            merged / (inp.uvw.len() / 3 * nchan) as f64
        );
    }
    Ok(())
}

fn run() -> Result<(), String> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 6 {
        return Err("gridder_gram_bench MS SIZE SCALE_ASEC ROBUST MODE [ARGS]".into());
    }
    let n: usize = args[2].parse().map_err(|_| "size")?;
    let cell = args[3].parse::<f64>().map_err(|_| "scale")? * std::f64::consts::PI / 180.0 / 3600.0;
    let mode = args[5].as_str();
    let t = Instant::now();
    let mut inp = read_input(&args[1], n, cell, &args[4])?;
    if let Ok(v) = std::env::var("GRAM_INTERVAL") {
        inp.interval = v.parse().unwrap_or(0.0);
    }
    println!(
        "{{\"mode\":\"read\",\"seconds\":{:.2},\"rows\":{},\"nchan\":{},\"load\":{}}}",
        t.elapsed().as_secs_f64(),
        inp.uvw.len() / 3,
        inp.freq.len(),
        load()
    );
    let num = |i: usize| -> Result<f64, String> {
        args.get(i)
            .and_then(|v| v.parse().ok())
            .ok_or_else(|| format!("argument {i}"))
    };
    match mode {
        "read" => Ok(()),
        "pass" => {
            let (eps, reps) = (num(6)?, num(8)? as usize);
            if args[7] == "single" {
                pass::<f32>(&inp, eps, reps)
            } else {
                pass::<f64>(&inp, eps, reps)
            }
        }
        "build" | "apply" => {
            let (s, theta, eps) = (num(6)? as usize, num(7)?, num(9)?);
            let reps = if mode == "apply" {
                num(10)? as usize
            } else {
                0
            };
            if args[8] == "single" {
                operator_run::<f32>(&inp, s, theta, eps, reps)
            } else {
                operator_run::<f64>(&inp, s, theta, eps, reps)
            }
        }
        "accuracy" => accuracy(&inp, &args[6], &args[7]),
        "budget" => budget(&inp),
        _ => Err("unknown mode".into()),
    }
}

fn main() {
    if let Err(e) = run() {
        eprintln!("gridder_gram_bench: {e}");
        std::process::exit(2);
    }
}
