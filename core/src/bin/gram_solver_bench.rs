// SPDX-License-Identifier: GPL-3.0-or-later
//! Measurements for the proximal solver on the visibility-free normal operator
//! (`research/gram-solver.md`). Reads the prepared arrays of
//! `examples/gemclean_bench_compare.py prepare`, so its misfit is the scorer's.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! ```text
//! gram_solver_bench PREP OUT NAME MODE [key=value ...]
//!   read                     read only (the baseline of perf)
//!   setup                    set the backend up
//!   apply                    set up, then reps= applies of a test model
//!   spectrum                 set up, then power= and lanczos= on the backend
//!   solve                    run the solver, write NAME.jsonl, NAME.json, FITS
//!   eval                     files=A,B... : exact certificate of raw f64 models
//! ```
//! Keys: `backend=exact|gram|psf`, `eps`, `s`, `theta`, `single`, `eval_eps`,
//! `lambda`, `prior=l1|l1signed|sara`, `delta`, `levels`, `bases`, `dual`, `reweights`,
//! `iters`, `momentum`, `restart`, `gap`, `kkt`, `xtol`, `every`, `step_factor`,
//! `lmax` (given, no power iteration), `power`, `lanczos`, `x0`, `checkpoints`,
//! `stride`, `cycles`, `gamma`, `outer_kkt`, `reps`, `cont`, `cont_start`, `cont_ratio`,
//! `cont_iters`, `cont_kkt`, `cont_rounds`, `cg`, `cg_fista`, `cg_rounds`, `admm`
//! (the penalty), `relax`, `outer_s`, `outer_theta`, `outer_same`. `prior=l1signed` allows
//! negative pixels, as CLEAN does. Times are CPU and wall of this process.

use rang_core::clean_certified::{Complex, Measurement, WgridMeasurement};
use rang_core::gemclean::fits::{self, Card};
use rang_core::gridder_gram::{GramMeasurement, GramOperator, WExpansion};
use rang_core::prox_solver::{
    self, ActiveSet, Admm, Counted, L1Prior, OuterRecord, OuterSchedule, Prior, Problem, Record,
    Settings,
};
use rang_core::sara::Sara;
use rang_core::wgridder::{Options, Real};
use std::collections::HashMap;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::Instant;

fn cpu_seconds() -> f64 {
    let stat = std::fs::read_to_string("/proc/self/stat").unwrap_or_default();
    let after = stat.rsplit(')').next().unwrap_or("");
    let f: Vec<&str> = after.split_whitespace().collect();
    let ticks = |i: usize| f.get(i).and_then(|v| v.parse::<f64>().ok()).unwrap_or(0.0);
    (ticks(11) + ticks(12)) / 100.0
}

fn status_gb(key: &str) -> f64 {
    let status = std::fs::read_to_string("/proc/self/status").unwrap_or_default();
    status
        .lines()
        .find(|l| l.starts_with(key))
        .and_then(|l| l.split_whitespace().nth(1))
        .and_then(|v| v.parse::<f64>().ok())
        .map_or(0.0, |kb| kb / 1024.0 / 1024.0)
}

fn load() -> f64 {
    std::fs::read_to_string("/proc/loadavg")
        .unwrap_or_default()
        .split_whitespace()
        .next()
        .and_then(|v| v.parse().ok())
        .unwrap_or(f64::NAN)
}

fn read_f64(path: &Path) -> Result<Vec<f64>, String> {
    let bytes = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    Ok(bytes
        .chunks_exact(8)
        .map(|c| f64::from_le_bytes(c.try_into().unwrap()))
        .collect())
}

fn write_f64(path: &Path, x: &[f64]) -> Result<(), String> {
    let mut bytes = Vec::with_capacity(x.len() * 8);
    for v in x {
        bytes.extend_from_slice(&v.to_le_bytes());
    }
    std::fs::write(path, bytes).map_err(|e| format!("{}: {e}", path.display()))
}

/// The number after `"key":` at the top level of a JSON text of known shape.
fn json_number(text: &str, key: &str) -> Result<f64, String> {
    let needle = format!("\"{key}\":");
    let start = text
        .find(&needle)
        .ok_or_else(|| format!("no {key} in meta.json"))?
        + needle.len();
    let rest = text[start..].trim_start();
    let end = rest
        .find(|c: char| c == ',' || c == '}' || c.is_whitespace())
        .unwrap_or(rest.len());
    rest[..end]
        .parse()
        .map_err(|_| format!("{key}: not a number"))
}

struct Args(HashMap<String, String>);

impl Args {
    fn f(&self, key: &str, default: f64) -> f64 {
        self.0
            .get(key)
            .and_then(|v| v.parse().ok())
            .unwrap_or(default)
    }
    fn u(&self, key: &str, default: usize) -> usize {
        self.0
            .get(key)
            .and_then(|v| v.parse().ok())
            .unwrap_or(default)
    }
    fn s(&self, key: &str, default: &str) -> String {
        self.0.get(key).cloned().unwrap_or_else(|| default.into())
    }
    fn opt(&self, key: &str) -> Option<f64> {
        self.0.get(key).and_then(|v| v.parse().ok())
    }
    fn flag(&self, key: &str, default: bool) -> bool {
        self.0.get(key).map_or(default, |v| v == "1" || v == "true")
    }
}

/// Read the prepared arrays and keep every `stride`-th row.
fn load_exact(prep: &Path, eps: f64, stride: usize) -> Result<WgridMeasurement, String> {
    let meta = std::fs::read_to_string(prep.join("meta.json")).map_err(|e| e.to_string())?;
    let nrow = json_number(&meta, "nrow")? as usize;
    let nchan = json_number(&meta, "nchan")? as usize;
    let side = json_number(&meta, "size")? as usize;
    let scale = json_number(&meta, "scale_arcsec")?;
    let cell = scale * std::f64::consts::PI / (180.0 * 3600.0);
    let uvw = read_f64(&prep.join("uvw.f64"))?;
    let freq = read_f64(&prep.join("freq.f64"))?;
    let wgt = read_f64(&prep.join("wgt.f64"))?;
    let raw = read_f64(&prep.join("vis.c128"))?;
    if uvw.len() != nrow * 3 || wgt.len() != nrow * nchan || raw.len() != 2 * nrow * nchan {
        return Err("prepared array sizes do not match meta.json".into());
    }
    let (mut u, mut v, mut w) = (Vec::new(), Vec::new(), Vec::new());
    for row in (0..nrow).step_by(stride.max(1)) {
        u.extend_from_slice(&uvw[row * 3..row * 3 + 3]);
        for c in 0..nchan {
            let at = row * nchan + c;
            v.push(Complex::new(raw[2 * at], raw[2 * at + 1]));
            w.push(wgt[at]);
        }
    }
    let opts = Options {
        flip_v: true,
        flip_w: true,
        ..Options::default()
    };
    WgridMeasurement::new(u, freq, v, w, side, cell, eps, opts)
}

/// A reproducible test model: 200 positive pixels of the inner field.
fn test_model(n: usize) -> Vec<f64> {
    let mut state = 20261103u64;
    let mut next = || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state
    };
    let mut m = vec![0.0; n * n];
    for _ in 0..200 {
        let (a, b) = (next() as usize % n, next() as usize % n);
        m[a * n + b] = 1e-3 * ((next() % 1000) as f64 + 1.0);
    }
    m
}

/// `grid` in FITS order with the scorer's axes.
fn write_fits(path: &Path, n: usize, grid: &[f64], cards: &[Card]) -> Result<(), String> {
    fits::write(path, n, n, &fits::gridder_to_fits(n, grid), -64, cards)
}

struct Job {
    out: PathBuf,
    name: String,
    n: usize,
    t0: Instant,
    jsonl: std::fs::File,
    filter: Option<GramMeasurement<f64>>,
}

fn checkpoints(args: &Args) -> Vec<usize> {
    args.s("checkpoints", "")
        .split(',')
        .filter_map(|v| v.parse().ok())
        .collect()
}

fn record_line(r: &Record, round: usize, wall: f64, applies: u64) -> String {
    format!(
        "{{\"k\":{},\"round\":{},\"F\":{:.15e},\"Q\":{:.15e},\"pen\":{:.10e},\"gap\":{:.6e},\"kkt\":{:.6e},\"nnz\":{},\"flux\":{:.10},\"curv\":{:.8e},\"dx\":{:.4e},\"restart\":{},\"applies\":{},\"wall\":{:.2}}}",
        r.iteration, round, r.objective, r.misfit, r.penalty, r.gap, r.kkt, r.nonzero, r.flux,
        r.curvature, r.relative_step, r.restarted as u8, applies, wall
    )
    .replace("NaN", "null")
    .replace("inf", "null")
}

/// The step: given, or from a power iteration on this backend.
fn largest_eigenvalue<M: Measurement + ?Sized>(
    op: &M,
    args: &Args,
) -> Result<(f64, usize, f64), String> {
    if let Some(l) = args.opt("lmax") {
        return Ok((l, 0, 0.0));
    }
    let t = Instant::now();
    let (l, used) = prox_solver::power_iteration(
        op,
        20261103,
        args.f("power_tol", 1e-4),
        args.u("power", 200),
    )?;
    Ok((l, used, t.elapsed().as_secs_f64()))
}

fn make_prior(args: &Args, n: usize) -> Result<Box<dyn Prior>, String> {
    let lambda = args.f("lambda", 1e-4);
    let delta = args.f("delta", lambda);
    match args.s("prior", "l1").as_str() {
        "l1" => Ok(Box::new(L1Prior::new(lambda, delta))),
        "l1signed" => Ok(Box::new(L1Prior::signed(lambda, delta))),
        "sara" => {
            let mut s = Sara::new(
                n,
                args.u("levels", 4),
                args.u("bases", 8),
                lambda,
                args.u("dual", 5),
                delta,
            )?;
            s.dual_tolerance = args.f("dual_tol", 1e-4);
            Ok(Box::new(s))
        }
        other => Err(format!("prior {other}")),
    }
}

/// Run the solver with reweighting rounds, or defect correction, on `op`.
fn solve_on<M: Measurement + ?Sized>(
    op: &M,
    exact: Option<&dyn Measurement>,
    dirty: &[f64],
    q0: f64,
    job: &mut Job,
    args: &Args,
    header: String,
) -> Result<(), String> {
    let counted = Counted::new(op);
    let (lmax, power_applies, power_seconds) = largest_eigenvalue(&counted, args)?;
    let step = args.f("step_factor", 1.0) / (args.f("lmax_margin", 1.01) * lmax);
    let lanczos = args.u("lanczos", 0);
    let spectrum = if lanczos > 0 {
        Some(prox_solver::lanczos_extremes(&counted, 20261104, lanczos)?)
    } else {
        None
    };
    let settings = Settings {
        step,
        max_iterations: args.u("iters", 200),
        momentum: args.flag("momentum", true),
        restart: args.flag("restart", true),
        gap_tolerance: args.opt("gap"),
        kkt_tolerance: args.opt("kkt"),
        step_tolerance: args.opt("xtol"),
        objective_every: args.u("every", 1),
    };
    let x0 = match args.0.get("x0") {
        Some(p) => read_f64(Path::new(p))?,
        None => vec![0.0; job.n * job.n],
    };
    let mut prior = make_prior(args, job.n)?;
    let problem = Problem { dirty, q0 };
    let setup_applies = counted.count();
    let wants = checkpoints(args);
    let rss_loop = status_gb("VmRSS");
    let cpu_before = cpu_seconds();
    let t_loop = Instant::now();
    let reweights = args.u("reweights", 0);
    let cycles = args.u("cycles", 0);
    let (out, rounds_iters) = if args.0.contains_key("admm") {
        let filter = job.filter.take().ok_or("admm needs the filter")?;
        let t0 = job.t0;
        let jsonl = &mut job.jsonl;
        let counted_ref = &counted;
        let verbose = args.u("print_every", 50).max(1);
        let mut observer = |r: &Record, _: &[f64]| {
            let line = record_line(r, 0, t0.elapsed().as_secs_f64(), counted_ref.count());
            if r.iteration.is_multiple_of(verbose) {
                println!("{line}");
            }
            let _ = writeln!(jsonl, "{line}");
        };
        let plan = Admm {
            rho: args.f("admm", 1.0),
            relaxation: args.f("relax", 1.5),
            cg_iterations: args.u("cg", 3),
            max_outer: args.u("iters", 200),
            check_every: args.u("every", 5),
            kkt: args.f("kkt", 2e-6),
        };
        let solved = prox_solver::solve_admm(
            &counted,
            &filter,
            &problem,
            prior.as_mut(),
            &plan,
            x0,
            &mut observer,
        )?;
        (
            prox_solver::Outcome {
                iterations: solved.rounds,
                stop: if solved.converged {
                    "converged"
                } else {
                    "iterations"
                }
                .into(),
                x: solved.x,
                gx: solved.gx,
                last: solved.last,
                negative_curvatures: solved.negative_curvatures,
                min_curvature: f64::NAN,
                max_curvature: f64::NAN,
                ..prox_solver::Outcome::default()
            },
            vec![solved.fista_applies, solved.cg_applies],
        )
    } else if cycles > 0 {
        let exact = exact.ok_or("defect correction needs the exact backend")?;
        let exact_counted = Counted::new(exact);
        let t0 = job.t0;
        let jsonl = &mut job.jsonl;
        let mut observer = |r: &OuterRecord, _: &[f64]| {
            let line = format!(
                "{{\"outer\":{},\"F\":{:.15e},\"Q\":{:.15e},\"gap\":{:.6e},\"kkt\":{:.6e},\"inner\":{},\"defect_sup\":{:.6e},\"wall\":{:.2}}}",
                r.outer,
                r.objective,
                r.misfit,
                r.gap,
                r.kkt,
                r.inner_iterations,
                r.defect_sup,
                t0.elapsed().as_secs_f64()
            );
            println!("{line}");
            let _ = writeln!(jsonl, "{line}");
        };
        let out = prox_solver::defect_correction(
            &exact_counted,
            &counted,
            &problem,
            prior.as_mut(),
            &settings,
            &OuterSchedule {
                cycles,
                kkt: args.f("outer_kkt", 1e-6),
                lambda: args.f("lambda", 1e-4),
                gamma: args.f("gamma", 0.0),
            },
            x0,
            &mut observer,
        )?;
        let exact_applies = exact_counted.count();
        eprintln!("exact applies {exact_applies}");
        job.jsonl
            .write_all(format!("{{\"exact_applies\":{exact_applies}}}\n").as_bytes())
            .map_err(|e| e.to_string())?;
        (out, vec![])
    } else {
        let mut x = x0;
        let mut iters = Vec::new();
        let mut round = 0;
        let mut total = 0usize;
        // Continuation: from `cont_start` of the dirty peak down to λ by
        // `cont_ratio`, each stage warm-started and solved loosely.
        let lambda = args.f("lambda", 1e-4);
        let stages: Vec<f64> = if args.flag("cont", false) {
            let peak = dirty.iter().cloned().fold(0.0, f64::max);
            let ratio = args.f("cont_ratio", 0.5);
            let mut level = args.f("cont_start", 0.5) * peak;
            let mut all = Vec::new();
            while level > lambda {
                all.push(level);
                level *= ratio;
            }
            all
        } else {
            Vec::new()
        };
        let active = (args.u("cg", 0) > 0).then(|| ActiveSet {
            fista_iterations: args.u("cg_fista", 10),
            cg_iterations: args.u("cg", 0),
            rounds: args.u("cg_rounds", 50),
            kkt: args.f("kkt", 2e-6),
        });
        let mut negative_cg = 0;
        let stage_settings = |level: f64| Settings {
            max_iterations: args.u("cont_iters", 50),
            kkt_tolerance: Some(args.f("cont_kkt", 0.1) * level),
            gap_tolerance: None,
            ..settings.clone()
        };
        for level in &stages {
            prior.set_lambda(*level);
            let t0 = job.t0;
            let jsonl = &mut job.jsonl;
            let counted_ref = &counted;
            let mut observer = |r: &Record, _: &[f64]| {
                let line = record_line(r, 0, t0.elapsed().as_secs_f64(), counted_ref.count());
                let _ = writeln!(jsonl, "{{\"stage\":{level:.6e},{}", &line[1..]);
            };
            let (next, last, iterations) = if let Some(plan) = active {
                let plan = ActiveSet {
                    kkt: args.f("cont_kkt", 0.5) * level,
                    rounds: args.u("cont_rounds", 6),
                    ..plan
                };
                let this = prox_solver::solve_active_set(
                    &counted,
                    &problem,
                    prior.as_mut(),
                    &settings,
                    &plan,
                    x,
                    &mut observer,
                )?;
                negative_cg += this.negative_curvatures;
                (this.x, this.last, this.fista_applies + this.cg_applies)
            } else {
                let this = prox_solver::solve(
                    &counted,
                    &problem,
                    prior.as_mut(),
                    &stage_settings(*level),
                    x,
                    &mut observer,
                )?;
                (this.x, this.last, this.iterations)
            };
            println!(
                "{{\"stage\":{level:.6e},\"iterations\":{iterations},\"kkt\":{:.3e},\"nnz\":{},\"F\":{:.9e},\"applies\":{},\"wall\":{:.1}}}",
                last.kkt,
                last.nonzero,
                last.objective,
                counted.count(),
                job.t0.elapsed().as_secs_f64()
            );
            total += iterations;
            x = next;
        }
        prior.set_lambda(lambda);
        loop {
            let t0 = job.t0;
            let jsonl = &mut job.jsonl;
            let job_out = job.out.clone();
            let name = job.name.clone();
            let counted_ref = &counted;
            let wants_ref = &wants;
            let verbose = args.u("print_every", 50).max(1);
            let base = total;
            let mut observer = |r: &Record, x: &[f64]| {
                let line = record_line(r, round, t0.elapsed().as_secs_f64(), counted_ref.count());
                if r.iteration.is_multiple_of(verbose) {
                    println!("{line}");
                }
                let _ = writeln!(jsonl, "{line}");
                let k = base + r.iteration;
                if wants_ref.contains(&k) {
                    let _ = write_f64(&job_out.join(format!("{name}-x{k}.f64")), x);
                }
            };
            let this = if let Some(plan) = active {
                let solved = prox_solver::solve_active_set(
                    &counted,
                    &problem,
                    prior.as_mut(),
                    &settings,
                    &plan,
                    x,
                    &mut observer,
                )?;
                negative_cg += solved.negative_curvatures;
                prox_solver::Outcome {
                    iterations: solved.fista_applies + solved.cg_applies,
                    stop: if solved.converged {
                        "converged"
                    } else {
                        "rounds"
                    }
                    .into(),
                    x: solved.x,
                    gx: solved.gx,
                    last: solved.last,
                    negative_curvatures: negative_cg,
                    min_curvature: f64::NAN,
                    max_curvature: f64::NAN,
                    ..prox_solver::Outcome::default()
                }
            } else {
                prox_solver::solve(
                    &counted,
                    &problem,
                    prior.as_mut(),
                    &settings,
                    x,
                    &mut observer,
                )?
            };
            iters.push(this.iterations);
            total += this.iterations;
            if round == reweights {
                break (this, iters);
            }
            prior.reweight(&this.x);
            x = this.x;
            round += 1;
        }
    };
    let loop_wall = t_loop.elapsed().as_secs_f64();
    let loop_cpu = cpu_seconds() - cpu_before;
    let n = job.n;
    let path = |kind: &str| job.out.join(format!("{}-{kind}", job.name));
    write_f64(&path("x.f64"), &out.x)?;
    let residual: Vec<f64> = dirty.iter().zip(&out.gx).map(|(d, g)| d - g).collect();
    write_fits(&path("model.fits"), n, &out.x, &[])?;
    write_fits(&path("residual.fits"), n, &residual, &[])?;
    let (lo, hi) = spectrum.unwrap_or((f64::NAN, f64::NAN));
    let summary = format!(
        "{{{header},\"lmax\":{lmax:.10e},\"power_applies\":{power_applies},\"power_seconds\":{power_seconds:.2},\"ritz_min\":{lo:.6e},\"ritz_max\":{hi:.6e},\"setup_applies\":{setup_applies},\"solver_applies\":{},\"rounds\":{rounds_iters:?},\"iterations\":{},\"stop\":\"{}\",\"objective\":{:.15e},\"misfit\":{:.15e},\"gap\":{:.6e},\"kkt\":{:.6e},\"nonzero\":{},\"flux\":{:.10},\"restarts\":{},\"objective_rises\":{},\"largest_rise\":{:.6e},\"negative_curvatures\":{},\"min_curvature\":{:.6e},\"max_curvature\":{:.6e},\"loop_wall\":{loop_wall:.2},\"loop_cpu\":{loop_cpu:.2},\"rss_loop_gb\":{rss_loop:.3},\"peak_gb\":{:.3},\"load_end\":{},\"wall\":{:.2},\"cpu\":{:.2}}}",
        counted.count() - setup_applies,
        out.iterations,
        out.stop,
        out.last.objective,
        out.last.misfit,
        out.last.gap,
        out.last.kkt,
        out.last.nonzero,
        out.last.flux,
        out.restarts,
        out.objective_rises,
        out.largest_rise,
        out.negative_curvatures,
        out.min_curvature,
        out.max_curvature,
        status_gb("VmHWM"),
        load(),
        job.t0.elapsed().as_secs_f64(),
        cpu_seconds(),
    );
    let summary = summary.replace("NaN", "null").replace("inf", "null");
    println!("{summary}");
    std::fs::write(job.out.join(format!("{}.json", job.name)), summary).map_err(|e| e.to_string())
}

fn expansion(args: &Args, eps: f64) -> Result<WExpansion, String> {
    let ridge = 1e-3 * (eps * eps).max(1e-14);
    WExpansion::new(args.u("s", 8), args.f("theta", 0.69), ridge)
}

fn stats_json<T: Real + Send + Sync>(op: &GramOperator<T>) -> String {
    let s = op.stats;
    format!(
        "\"planes\":{},\"stencil\":{},\"theta\":{},\"wmax\":{:.3},\"x_range\":{:.6e},\"sup_error\":{:.4e},\"lebesgue\":{:.3},\"cube_gb\":{:.3},\"setup_grid_s\":{:.2},\"setup_fft_s\":{:.2}",
        op.planes(),
        s.stencil,
        s.theta,
        s.wmax,
        s.x_range,
        s.sup_error,
        s.lebesgue,
        s.cube_bytes as f64 / (1u64 << 30) as f64,
        s.setup_grid_seconds,
        s.setup_fft_seconds
    )
}

/// The mode, on a Gram operator of precision `T`.
fn run_gram<T: Real + Send + Sync>(
    exact: WgridMeasurement,
    dirty: Vec<f64>,
    q0: f64,
    mode: &str,
    job: &mut Job,
    args: &Args,
) -> Result<(), String> {
    let eps = args.f("eps", 1e-6);
    let t = Instant::now();
    let op = if args.s("backend", "gram") == "psf" {
        GramOperator::<T>::no_w(&exact.opts, &exact.uvw, &exact.freq, &exact.wgt, eps)?
    } else {
        let ex = expansion(args, eps)?;
        GramOperator::<T>::new(&exact.opts, &exact.uvw, &exact.freq, &exact.wgt, &ex, eps)?
    };
    let setup_seconds = t.elapsed().as_secs_f64();
    let header = format!(
        "\"backend\":\"{}\",\"precision_bytes\":{},{},\"setup_s\":{setup_seconds:.2},\"eps\":{eps}",
        args.s("backend", "gram"),
        std::mem::size_of::<T>(),
        stats_json(&op)
    );
    // Outer cycles on the exact gridder, or with outer_s on a Gram operator: the
    // visibilities can then go.
    let mut outer_gram = None;
    let mut header = header;
    if args.u("cycles", 0) > 0
        && let Some(s) = args.0.get("outer_s")
    {
        let stencil: usize = s.parse().map_err(|_| "outer_s")?;
        let theta = args.f("outer_theta", 0.69);
        let ridge = 1e-3 * (eps * eps).max(1e-14);
        let ex = WExpansion::new(stencil, theta, ridge)?;
        let t = Instant::now();
        let outer =
            GramOperator::<T>::new(&exact.opts, &exact.uvw, &exact.freq, &exact.wgt, &ex, eps)?;
        header.push_str(&format!(
                ",\"outer_setup_s\":{:.2},\"outer_planes\":{},\"outer_cube_gb\":{:.3},\"outer_sup_error\":{:.4e}",
                t.elapsed().as_secs_f64(),
                outer.planes(),
                outer.stats.cube_bytes as f64 / (1u64 << 30) as f64,
                outer.stats.sup_error
            ));
        outer_gram = Some(GramMeasurement::new(outer, Vec::new(), 0.0));
    }
    // outer_same=1: the outer cycles use the inner operator, so the correction is
    // zero and the cycles only step λ down: the whole solve is on this operator.
    let outer_same = args.flag("outer_same", false);
    let keep_exact = args.u("cycles", 0) > 0 && outer_gram.is_none() && !outer_same;
    let exact = if keep_exact {
        Some(exact)
    } else {
        drop(exact);
        None
    };
    let measurement = GramMeasurement::new(op, dirty.clone(), q0);
    let outer: Option<&dyn Measurement> = match (&outer_gram, &exact) {
        _ if outer_same => Some(&measurement as &dyn Measurement),
        (Some(g), _) => Some(g as &dyn Measurement),
        (None, Some(e)) => Some(e as &dyn Measurement),
        _ => None,
    };
    finish(&measurement, outer, &dirty, q0, mode, job, args, header)
}

#[allow(clippy::too_many_arguments)]
fn finish<M: Measurement + ?Sized>(
    op: &M,
    exact: Option<&dyn Measurement>,
    dirty: &[f64],
    q0: f64,
    mode: &str,
    job: &mut Job,
    args: &Args,
    header: String,
) -> Result<(), String> {
    let n = job.n;
    match mode {
        "setup" => {
            println!(
                "{{{header},\"peak_gb\":{:.3},\"wall\":{:.2},\"cpu\":{:.2},\"load\":{}}}",
                status_gb("VmHWM"),
                job.t0.elapsed().as_secs_f64(),
                cpu_seconds(),
                load()
            );
            Ok(())
        }
        "apply" => {
            let m = match args.0.get("x0") {
                Some(p) => read_f64(Path::new(p))?,
                None => test_model(n),
            };
            let reps = args.u("reps", 3);
            let t = Instant::now();
            let cpu = cpu_seconds();
            for _ in 0..reps {
                let _ = op.gram_apply(&m)?;
            }
            println!(
                "{{{header},\"reps\":{reps},\"per_apply_wall\":{:.3},\"per_apply_cpu\":{:.3},\"peak_gb\":{:.3},\"load\":{}}}",
                t.elapsed().as_secs_f64() / reps.max(1) as f64,
                (cpu_seconds() - cpu) / reps.max(1) as f64,
                status_gb("VmHWM"),
                load()
            );
            Ok(())
        }
        "spectrum" => {
            let t = Instant::now();
            let (l, used) = prox_solver::power_iteration(op, 20261103, 1e-5, args.u("power", 200))?;
            let t_power = t.elapsed().as_secs_f64();
            let (lo, hi) = prox_solver::lanczos_extremes(op, 20261104, args.u("lanczos", 60))?;
            println!(
                "{{{header},\"lmax\":{l:.10e},\"power_applies\":{used},\"power_s\":{t_power:.1},\"ritz_min\":{lo:.6e},\"ritz_max\":{hi:.6e},\"lanczos\":{},\"wall\":{:.1},\"load\":{}}}",
                args.u("lanczos", 60),
                job.t0.elapsed().as_secs_f64(),
                load()
            );
            Ok(())
        }
        "solve" => solve_on(op, exact, dirty, q0, job, args, header),
        other => Err(format!("mode {other}")),
    }
}

/// The exact certificate of raw models, and optionally the operator's error at each.
fn evaluate(exact: &WgridMeasurement, args: &Args, n: usize) -> Result<(), String> {
    let lambda = args.f("lambda", 1e-4);
    let (dirty, q0) = exact.residual(&vec![0.0; n * n])?;
    let operator = if args.0.contains_key("s") {
        let eps = args.f("eps", 1e-6);
        let ex = expansion(args, eps)?;
        Some(GramOperator::<f64>::new(
            &exact.opts,
            &exact.uvw,
            &exact.freq,
            &exact.wgt,
            &ex,
            eps,
        )?)
    } else {
        None
    };
    for file in args.s("files", "").split(',').filter(|f| !f.is_empty()) {
        let x = read_f64(Path::new(file))?;
        let g = exact.gram_apply(&x)?;
        let mut prior = if args.s("prior", "l1") == "l1signed" {
            L1Prior::signed(lambda, 1.0)
        } else {
            L1Prior::new(lambda, 1.0)
        };
        let problem = Problem { dirty: &dirty, q0 };
        let settings = Settings {
            step: 0.0,
            max_iterations: 0,
            ..Settings::default()
        };
        let fixed = Fixed { g: &g, n };
        let c = prox_solver::solve(
            &fixed,
            &problem,
            &mut prior,
            &settings,
            x.clone(),
            &mut |_, _| {},
        )?;
        let l1: f64 = x.iter().map(|v| v.abs()).sum();
        let mut extra = String::new();
        if let Some(op) = &operator {
            let gt = op.apply(&x)?;
            let (mut sup, mut sum, mut quad) = (0.0_f64, 0.0, 0.0);
            for ((a, b), m) in g.iter().zip(&gt).zip(&x) {
                sup = sup.max((a - b).abs());
                sum += (a - b) * (a - b);
                quad += m * (b - a);
            }
            extra = format!(
                ",\"gram_sup_err\":{sup:.6e},\"gram_l2_err\":{:.6e},\"gram_half_quad_err\":{:.6e},\"sup_error\":{:.4e},\"planes\":{}",
                sum.sqrt(),
                0.5 * quad,
                op.stats.sup_error,
                op.planes()
            );
        }
        println!(
            "{{\"file\":\"{file}\",\"lambda\":{lambda},\"eval_eps\":{},\"F\":{:.15e},\"Q\":{:.15e},\"gap\":{:.6e},\"kkt\":{:.6e},\"l1\":{l1:.10},\"nnz\":{},\"q0\":{q0:.15e}{extra}}}",
            exact.opts.epsilon,
            c.last.objective,
            c.last.misfit,
            c.last.gap,
            c.last.kkt,
            c.last.nonzero
        );
    }
    Ok(())
}

/// A backend that returns a fixed `G x`: [`prox_solver::solve`] with no
/// iterations is then the certificate of `x`.
struct Fixed<'a> {
    g: &'a [f64],
    n: usize,
}

impl Measurement for Fixed<'_> {
    fn side(&self) -> usize {
        self.n
    }
    fn residual(&self, _: &[f64]) -> Result<(Vec<f64>, f64), String> {
        Err("not used".into())
    }
    fn gram_apply(&self, _: &[f64]) -> Result<Vec<f64>, String> {
        Ok(self.g.to_vec())
    }
}

fn run() -> Result<(), String> {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    if argv.len() < 4 {
        return Err("usage: gram_solver_bench PREP OUT NAME MODE [key=value ...]".into());
    }
    let (prep, out, name, mode) = (
        PathBuf::from(&argv[0]),
        PathBuf::from(&argv[1]),
        argv[2].clone(),
        argv[3].clone(),
    );
    let args = Args(
        argv[4..]
            .iter()
            .filter_map(|kv| kv.split_once('='))
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect(),
    );
    std::fs::create_dir_all(&out).map_err(|e| e.to_string())?;
    let t0 = Instant::now();
    let backend = args.s("backend", "gram");
    let eps_data = args.f("eval_eps", args.f("eps", 1e-6));
    let exact = load_exact(&prep, eps_data, args.u("stride", 1))?;
    let n = exact.opts.nx;
    let vis_count = exact.vis.len();
    if mode == "read" {
        println!(
            "{{\"mode\":\"read\",\"vis\":{vis_count},\"peak_gb\":{:.3},\"wall\":{:.2},\"cpu\":{:.2},\"load\":{}}}",
            status_gb("VmHWM"),
            t0.elapsed().as_secs_f64(),
            cpu_seconds(),
            load()
        );
        return Ok(());
    }
    if mode == "eval" {
        return evaluate(&exact, &args, n);
    }
    let jsonl =
        std::fs::File::create(out.join(format!("{name}.jsonl"))).map_err(|e| e.to_string())?;
    // The preconditioner of ADMM: one no-w gridding pass, whatever the backend.
    let filter = match args.opt("admm") {
        Some(rho) => {
            let psf = GramOperator::<f64>::no_w(
                &exact.opts,
                &exact.uvw,
                &exact.freq,
                &exact.wgt,
                args.f("eps", 1e-6),
            )?;
            Some(GramMeasurement::new(
                psf.inverse_filter(rho)?,
                Vec::new(),
                0.0,
            ))
        }
        None => None,
    };
    let mut job = Job {
        out,
        name,
        n,
        t0,
        jsonl,
        filter,
    };
    // The data side comes once from the gridder, whatever the backend.
    let (dirty, q0) = exact.residual(&vec![0.0; n * n])?;
    let opening = format!(
        "\"name\":\"{}\",\"vis\":{vis_count},\"threads\":{},\"load_start\":{},\"q0\":{q0:.15e},\"args\":\"{}\"",
        job.name,
        rayon::current_num_threads(),
        load(),
        argv[4..].join(" ")
    );
    match backend.as_str() {
        "exact" => {
            let header = format!("{opening},\"backend\":\"exact\",\"eps\":{eps_data}");
            finish(&exact, None, &dirty, q0, &mode, &mut job, &args, header)
        }
        "gram" | "psf" => {
            let run = |exact, dirty, job: &mut Job| {
                if args.flag("single", false) {
                    run_gram::<f32>(exact, dirty, q0, &mode, job, &args)
                } else {
                    run_gram::<f64>(exact, dirty, q0, &mode, job, &args)
                }
            };
            run(exact, dirty, &mut job)
        }
        other => Err(format!("backend {other}")),
    }
}

fn main() {
    if let Err(e) = run() {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}
