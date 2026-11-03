//! The measured half of `research/gemclean.md`: a simulated MeerKAT
//! Measurement Set, and gemclean against the certified driver's provable rule
//! and a Clark-rule run on the same data.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! ```text
//! cargo run --release --manifest-path core/Cargo.toml --example gemclean_sim -- write OUTDIR
//! core/target/release/gemclean -name OUTDIR/bin -size 1024 1024 -scale 2asec -weight briggs 0 \
//!     -niter 100000 -abs-threshold 1e-3 -patch 64 OUTDIR/sim.ms
//! cargo run --release --manifest-path core/Cargo.toml --example gemclean_sim -- bench OUTDIR
//! cargo run --release --manifest-path core/Cargo.toml --example gemclean_sim -- compare OUTDIR
//! ```
//!
//! `bench OUTDIR [repeats]` is the timing pass alone, one command (it writes
//! the MS if needed): repeats default 5, variants interleaved, with wall
//! time, CPU time and machine load per repeat, minimum and median.
//!
//! `write` makes `OUTDIR/sim.ms` (64 antennas of `data/meerkat.itrf.txt`, a
//! 2 h track of 60 s dumps, 8 channels, 50 point sources log-uniform over
//! 0.01-1 Jy, fixed seed) and `OUTDIR/truth.json`. The visibilities come from
//! `dirty2vis` on the pixel grid with the same flips the imager uses: an
//! inverse crime by construction, sources on pixels, kept because this
//! experiment measures the deconvolver's arithmetic and cost, not its
//! recovery of off-grid emission. The noise is Gaussian with σ = 0.5 % of the
//! brightest source per real and imaginary part of each correlation.
//!
//! `compare` reads the MS back through the imager's own input path and
//! writes `OUTDIR/gemclean.json`; it embeds `OUTDIR/bin-report.json` when it
//! exists.

use rang_core::clean::Psf;
use rang_core::clean_certified::{
    self, Certified, DriverSettings, Measurement, MinorRule, WgridMeasurement, psf_from_double,
};
use rang_core::gemclean::host::{Measured, Probe, min_median};
use rang_core::gemclean::input::{self, Selection};
use rang_core::gemclean::json::{arr, num, obj, text};
use rang_core::gemclean::kernels::{self, Level};
use rang_core::gemclean::measure::GridMeasurement;
use rang_core::gemclean::sim::{self, SimSpec, Sky};
use rang_core::gemclean::{self, Beam, Outcome, Settings};
use rang_core::weights::WeightClass;
use rang_core::wgridder::Options;
use std::path::Path;
use std::time::Instant;

const SEED: u64 = 20261102;
const SIDE: usize = 1024;
const CELL_ARCSEC: f64 = 2.0;
const NCHAN: usize = 8;
const DUMPS: usize = 120;
const DUMP_SECONDS: f64 = 60.0;
const DEC_DEG: f64 = -30.0;
const RA_RAD: f64 = 0.5;
const SOURCES: usize = 50;
const NOISE_SIGMA: f64 = 0.005;
const THRESHOLD: f64 = 1e-3;
const GAIN: f64 = 0.1;
const MAX_COMPONENTS: usize = 200_000;
const TIMING_STATUS: &str = "PROVISIONAL: measured on a shared, loaded host; read with the recorded machine load; no final speedup is stated";

fn opts() -> Options {
    sim::imaging_options()
}

fn cell() -> f64 {
    (CELL_ARCSEC / 3600.0).to_radians()
}

fn truth_sources() -> Vec<(usize, usize, f64)> {
    sim::point_sources(SIDE, SOURCES, SEED)
}

fn default_spec() -> SimSpec {
    SimSpec {
        sky: Sky::Point { count: SOURCES },
        side: SIDE,
        cell_arcsec: CELL_ARCSEC,
        dumps: DUMPS,
        dump_seconds: DUMP_SECONDS,
        nchan: NCHAN,
        hours: 2.0,
        first_freq: 1.2e9,
        channel_width: 25e6,
        dec_deg: DEC_DEG,
        ra_rad: RA_RAD,
        noise_sigma: NOISE_SIGMA,
        seed: SEED,
    }
}

fn write(outdir: &Path, spec: &SimSpec) -> Result<(), String> {
    std::fs::create_dir_all(outdir).map_err(|e| e.to_string())?;
    let wall = Instant::now();
    let path = outdir.join("sim.ms");
    let out = sim::simulate(&path, spec)?;
    let pixels = out.model.iter().filter(|&&c| c != 0.0).count();
    let items: Vec<String> = match spec.sky {
        Sky::Point { count } => sim::point_sources(spec.side, count, spec.seed)
            .iter()
            .map(|&(i, j, f)| {
                obj(&[
                    ("i", i.to_string()),
                    ("j", j.to_string()),
                    ("flux_jy", num(f)),
                ])
            })
            .collect(),
        _ => Vec::new(),
    };
    let meta = obj(&[
        ("sky", text(&spec.sky.name())),
        ("seed", spec.seed.to_string()),
        ("side", spec.side.to_string()),
        ("cell_arcsec", num(spec.cell_arcsec)),
        ("rows", out.rows.to_string()),
        ("channels", spec.nchan.to_string()),
        ("dumps", spec.dumps.to_string()),
        ("dump_seconds", num(spec.dump_seconds)),
        ("hours", num(spec.hours)),
        ("dec_deg", num(spec.dec_deg)),
        (
            "noise_sigma_jy_per_part_per_correlation",
            num(spec.noise_sigma),
        ),
        (
            "predict",
            text("dirty2vis on pixel positions, epsilon 1e-9, flip_v, flip_w"),
        ),
        ("model_pixels", pixels.to_string()),
        ("model_flux_jy", num(out.model.iter().sum())),
        ("sources", arr(&items)),
        ("seconds_predict", num(out.seconds_predict)),
        ("seconds_write_ms", num(out.seconds_write)),
        ("seconds_wall", num(wall.elapsed().as_secs_f64())),
    ]);
    std::fs::write(outdir.join("truth.json"), meta + "\n").map_err(|e| e.to_string())?;
    println!(
        "wrote {} ({} rows, {} channels, {pixels} model pixels): predict {:.2} s, MS {:.2} s; wall {:.2} s",
        path.display(),
        out.rows,
        spec.nchan,
        out.seconds_predict,
        out.seconds_write,
        wall.elapsed().as_secs_f64()
    );
    Ok(())
}

/// Model and residual statistics against the truth.
fn quality(model: &[f64], residual: &[f64]) -> Vec<(&'static str, String)> {
    let n = SIDE;
    let sources = truth_sources();
    let mut near = vec![false; n * n];
    let mut sum2 = 0.0;
    let mut recovered = 0.0;
    let mut truth_flux = 0.0;
    let mut worst = 0.0_f64;
    for &(i, j, flux) in &sources {
        let mut got = 0.0;
        for a in i.saturating_sub(2)..=(i + 2).min(n - 1) {
            for b in j.saturating_sub(2)..=(j + 2).min(n - 1) {
                got += model[a * n + b];
                near[a * n + b] = true;
            }
        }
        let e = (got - flux) / flux;
        sum2 += e * e;
        worst = worst.max(e.abs());
        recovered += got;
        truth_flux += flux;
    }
    let spurious: f64 = model
        .iter()
        .zip(&near)
        .filter(|(_, is_near)| !**is_near)
        .map(|(c, _)| c.abs())
        .sum();
    let rms = (residual.iter().map(|r| r * r).sum::<f64>() / residual.len() as f64).sqrt();
    let peak = residual.iter().fold(0.0_f64, |a, r| a.max(r.abs()));
    vec![
        ("model_flux_total", num(model.iter().sum())),
        ("truth_flux", num(truth_flux)),
        ("flux_near_sources", num(recovered)),
        ("flux_abs_away_from_sources", num(spurious)),
        (
            "source_flux_rms_relative_error",
            num((sum2 / sources.len() as f64).sqrt()),
        ),
        ("source_flux_worst_relative_error", num(worst)),
        ("residual_rms", num(rms)),
        ("residual_peak_abs", num(peak)),
    ]
}

fn gemclean_entry(name: &str, out: &Outcome) -> String {
    let t = out.tau_quantiles();
    println!(
        "{name:<28} {:>7} comps {:>3} major {:>5} resyncs ({} drift, {} tau, {} every, {} thr) stop {:?}; Q/Q0 {:.4e}, max|gap|/Q {:.2e}, tau min {:.3} med {:.3}; minor {:.3} s (corr {:.3}), resync {:.3} s, major {:.3} s, total {:.3} s",
        out.steps.len(),
        out.cycles.len(),
        out.resyncs.total(),
        out.resyncs.drift,
        out.resyncs.tau,
        out.resyncs.every,
        out.resyncs.threshold,
        out.stop,
        out.q_final / out.q0,
        out.cycles
            .iter()
            .fold(0.0_f64, |a, c| a.max(c.gap_relative.abs())),
        t.map_or(f64::NAN, |x| x.0),
        t.map_or(f64::NAN, |x| x.3),
        out.timings.minor,
        out.timings.correction,
        out.timings.resync,
        out.timings.major,
        out.timings.total,
    );
    let mut fields = vec![("name", text(name)), ("run", out.to_json(None))];
    fields.extend(quality(&out.model, &out.residual));
    obj(&fields)
}

fn driver_entry(name: &str, out: &Certified, settings: &DriverSettings) -> String {
    let max_gap = out
        .cycles
        .iter()
        .fold(0.0_f64, |a, c| a.max(c.gap_relative.abs()));
    let major_time: f64 = out.cycles.iter().map(|c| c.seconds).sum();
    let per_cycle: Vec<f64> = out.cycles.iter().map(|c| c.components as f64).collect();
    let mean_cycle = per_cycle.iter().sum::<f64>() / per_cycle.len().max(1) as f64;
    println!(
        "{name:<28} {:>7} comps {:>5} major stop {:?}; Q/Q0 {:.4e}, max|gap|/Q {:.2e}, ascending {}, {:.3} s ({:.1} comps/cycle)",
        out.steps.len(),
        out.cycles.len(),
        out.stop,
        out.q_final / out.q0,
        max_gap,
        out.ascending_steps(),
        out.seconds,
        mean_cycle,
    );
    let mut fields = vec![
        ("name", text(name)),
        ("rule", text(&settings.rule.name())),
        (
            "patch",
            settings.patch.map_or("null".into(), |p| p.to_string()),
        ),
        ("audit", settings.audit.to_string()),
        ("components", out.steps.len().to_string()),
        ("major_cycles", out.cycles.len().to_string()),
        ("components_per_cycle_mean", num(mean_cycle)),
        ("stop", text(&format!("{:?}", out.stop))),
        ("f", num(out.f)),
        ("q_final_over_q0", num(out.q_final / out.q0)),
        ("max_abs_gap_relative", num(max_gap)),
        ("ascending_steps", out.ascending_steps().to_string()),
        ("seconds_total", num(out.seconds)),
        ("seconds_in_cycles", num(major_time)),
    ];
    fields.extend(quality(&out.model, &out.residual));
    obj(&fields)
}

/// The same data as the operator with the kept plan (weights already
/// normalised, so normalising again changes nothing).
fn grid_measurement(m: &WgridMeasurement) -> Result<GridMeasurement<f64>, String> {
    GridMeasurement::new(
        m.uvw.clone(),
        m.freq.clone(),
        m.vis.clone(),
        m.wgt.clone(),
        m.opts.nx,
        m.opts.pixsize_x,
        m.opts.epsilon,
        m.opts,
    )
}

/// The rows of the first `nant` antennas (the row order of [`write`]), with
/// natural weights.
fn sparse_subset(
    data: &input::StokesI,
    nant: usize,
    side: usize,
    cell: f64,
) -> Result<WgridMeasurement, String> {
    let total = sim::antennas().len();
    let nchan = data.freq.len();
    let (mut uvw, mut vis, mut wgt) = (Vec::new(), Vec::new(), Vec::new());
    let mut row = 0;
    for _ in 0..DUMPS {
        for p in 0..total {
            for q in p + 1..total {
                if q < nant {
                    uvw.extend_from_slice(&data.uvw[3 * row..3 * row + 3]);
                    vis.extend_from_slice(&data.vis[row * nchan..(row + 1) * nchan]);
                    for &w in &data.weight[row * nchan..(row + 1) * nchan] {
                        wgt.push(f64::from(w));
                    }
                }
                row += 1;
            }
        }
    }
    WgridMeasurement::new(uvw, data.freq.clone(), vis, wgt, side, cell, 1e-6, opts())
}

fn compare(outdir: &Path) -> Result<(), String> {
    let wall = Instant::now();
    let ms = outdir.join("sim.ms");
    let t = Instant::now();
    let data = input::read_ms(&ms, &Selection::default())?;
    let t_read = t.elapsed().as_secs_f64();
    let t = Instant::now();
    let weights = input::gridding_weights(&data, WeightClass::Briggs(0.0), SIDE, cell())?;
    let t_weights = t.elapsed().as_secs_f64();
    println!(
        "read {} rows in {t_read:.2} s, Briggs 0 weights in {t_weights:.2} s; {} visibilities, weight sum {:.3}",
        data.rows(),
        weights.count,
        weights.total
    );
    let m = WgridMeasurement::new(
        data.uvw.clone(),
        data.freq.clone(),
        data.vis.clone(),
        weights.weights.clone(),
        SIDE,
        cell(),
        1e-6,
        opts(),
    )?;
    let t = Instant::now();
    let psf2n = m.psf_image(2 * SIDE)?;
    let t_psf = t.elapsed().as_secs_f64();
    let t = Instant::now();
    let (_, q0) = m.residual(&vec![0.0; SIDE * SIDE])?;
    let t_residual = t.elapsed().as_secs_f64();
    let exact: Psf = psf_from_double(SIDE, &psf2n);
    println!(
        "2n PSF {t_psf:.2} s, one residual {t_residual:.2} s; Q0 {q0:.5e}; coherence {:.4}, outside ±16 {:.4}, ±64 {:.4}, ±256 {:.4}",
        exact.coherence(),
        exact.outside_patch(16),
        exact.outside_patch(64),
        exact.outside_patch(256),
    );
    let base = Settings {
        gain: GAIN,
        threshold: THRESHOLD,
        max_components: MAX_COMPONENTS,
        ..Settings::default()
    };

    // The patch size.
    let mut patch_runs = Vec::new();
    for patch in [8, 16, 32, 64, 128, 256, SIDE - 1] {
        let t = Instant::now();
        let beam = Beam::from_double(SIDE, &psf2n, patch)?;
        let t_beam = t.elapsed().as_secs_f64();
        let out = gemclean::run(&m, &beam, &base, None)?;
        let name = format!("gemclean-patch{patch}");
        patch_runs.push(obj(&[
            ("beam_setup_seconds", num(t_beam)),
            ("entry", gemclean_entry(&name, &out)),
        ]));
    }

    let beam = Beam::from_double(SIDE, &psf2n, 64)?;

    // Audited, shallower: lazy against brute force at every step.
    let audited = gemclean::run(
        &m,
        &beam,
        &Settings {
            audit: true,
            ..base
        },
        None,
    )?;
    let audit_entry = gemclean_entry("gemclean-patch64-audit", &audited);

    // The whole loop at each SIMD level.
    let mut level_runs = Vec::new();
    let mut steps_reference: Option<Vec<(usize, f64)>> = None;
    for level in [Level::Scalar, Level::Avx2, Level::Avx512] {
        if level > kernels::detected() {
            continue;
        }
        let out = gemclean::run(
            &m,
            &beam,
            &Settings {
                level: Some(level),
                ..base
            },
            None,
        )?;
        let steps: Vec<(usize, f64)> = out.steps.iter().map(|s| (s.pixel, s.peak)).collect();
        let same = match &steps_reference {
            None => {
                steps_reference = Some(steps.clone());
                true
            }
            Some(r) => r.len() == steps.len() && r.iter().zip(&steps).all(|(a, b)| a.0 == b.0),
        };
        let name = format!("gemclean-patch64-{}", level.name());
        level_runs.push(obj(&[
            ("level", text(level.name())),
            ("same_picks_as_scalar", same.to_string()),
            ("entry", gemclean_entry(&name, &out)),
        ]));
    }

    // The major-cycle fraction, and a deeper threshold.
    let mut fraction_runs = Vec::new();
    for fraction in [0.5, 0.9, 0.99, 1.0] {
        let out = gemclean::run(
            &m,
            &beam,
            &Settings {
                cycle_stop: gemclean::CycleStop::MisfitFraction,
                major_fraction: fraction,
                ..base
            },
            None,
        )?;
        fraction_runs.push(gemclean_entry(
            &format!("gemclean-fraction{fraction}"),
            &out,
        ));
    }
    let deep = gemclean::run(
        &m,
        &beam,
        &Settings {
            threshold: THRESHOLD / 10.0,
            max_components: 500_000,
            ..base
        },
        None,
    )?;
    let deep_entry = gemclean_entry("gemclean-deep-1e-4", &deep);

    // A hard beam: the baselines of the first antennas of the same MS
    // (natural weights), where the sidelobes stay high to the image edge.
    let mut sparse_runs = Vec::new();
    for (nant, threshold, budget) in [(4usize, 0.05, 3000usize), (16, 0.005, 10_000)] {
        let sub = sparse_subset(&data, nant, SIDE, cell())?;
        let psf = sub.psf_image(2 * SIDE)?;
        let full = psf_from_double(SIDE, &psf);
        let beam = Beam::from_double(SIDE, &psf, 64)?;
        println!(
            "sparse {nant} antennas: f(±64) {:.4}, coherence {:.4}",
            beam.f,
            full.coherence()
        );
        let out = gemclean::run(
            &sub,
            &beam,
            &Settings {
                threshold,
                max_components: budget,
                max_major: 40,
                ..base
            },
            None,
        )?;
        let lazy = gemclean_entry(&format!("sparse{nant}-gemclean-patch64"), &out);
        let driver = DriverSettings {
            gain: GAIN,
            threshold,
            max_components: budget,
            max_major: 200,
            max_minor: usize::MAX,
            patch: Some(64),
            rule: MinorRule::Provable,
            floor_tolerance: None,
            audit: false,
            divergence_limit: 0.0,
        };
        let provable = clean_certified::run(&sub, &full, &full, &driver, None)?;
        let clark_settings = DriverSettings {
            rule: MinorRule::Clark,
            ..driver
        };
        let clark = clean_certified::run(&sub, &full, &full, &clark_settings, None)?;
        sparse_runs.push(obj(&[
            ("antennas", nant.to_string()),
            ("threshold_jy", num(threshold)),
            ("f_outside_64", num(beam.f)),
            ("coherence", num(full.coherence())),
            ("gemclean", lazy),
            (
                "provable",
                driver_entry(&format!("sparse{nant}-provable"), &provable, &driver),
            ),
            (
                "clark",
                driver_entry(&format!("sparse{nant}-clark"), &clark, &clark_settings),
            ),
        ]));
    }

    // The plain certified driver on the same data, same gain and threshold.
    let t = Instant::now();
    let mut driver_runs = Vec::new();
    let run_driver = |name: &str, settings: DriverSettings| -> Result<String, String> {
        let out = clean_certified::run(&m, &exact, &exact, &settings, None)?;
        Ok(driver_entry(name, &out, &settings))
    };
    let driver = DriverSettings {
        gain: GAIN,
        threshold: THRESHOLD,
        max_components: MAX_COMPONENTS,
        max_major: 200,
        max_minor: usize::MAX,
        patch: Some(64),
        rule: MinorRule::Provable,
        floor_tolerance: None,
        audit: false,
        divergence_limit: 0.0,
    };
    driver_runs.push(run_driver("driver-provable-patch64", driver)?);
    driver_runs.push(run_driver(
        "driver-clark-patch64",
        DriverSettings {
            rule: MinorRule::Clark,
            ..driver
        },
    )?);
    driver_runs.push(run_driver(
        "driver-mgain0.8-patch64",
        DriverSettings {
            rule: MinorRule::MajorGain(0.8),
            ..driver
        },
    )?);
    driver_runs.push(run_driver(
        "driver-mgain0.8-fullbeam",
        DriverSettings {
            rule: MinorRule::MajorGain(0.8),
            patch: None,
            ..driver
        },
    )?);
    // An audited short Clark run counts ascending steps (one full-image
    // subtraction per step).
    driver_runs.push(run_driver(
        "driver-clark-patch64-audit",
        DriverSettings {
            rule: MinorRule::Clark,
            audit: true,
            max_components: 2000,
            ..driver
        },
    )?);
    let t_driver = t.elapsed().as_secs_f64();

    let read_json = |name: &str| {
        std::fs::read_to_string(outdir.join(name))
            .map(|s| s.trim().to_string())
            .unwrap_or_else(|_| "null".into())
    };
    let json = obj(&[
        (
            "experiment",
            text("gemclean on a simulated MeerKAT MS (research/gemclean.md)"),
        ),
        ("timing_status", text(TIMING_STATUS)),
        ("truth", read_json("truth.json")),
        ("threads", rayon::current_num_threads().to_string()),
        ("simd_detected", text(kernels::detected().name())),
        (
            "weighting",
            text("briggs 0, padded grid, rank filter 3 over 16"),
        ),
        ("wgridder_accuracy", num(1e-6)),
        ("gain", num(GAIN)),
        ("threshold_jy", num(THRESHOLD)),
        ("q0", num(q0)),
        (
            "beam",
            obj(&[
                ("coherence", num(exact.coherence())),
                ("outside_16", num(exact.outside_patch(16))),
                ("outside_64", num(exact.outside_patch(64))),
                ("outside_256", num(exact.outside_patch(256))),
            ]),
        ),
        (
            "seconds",
            obj(&[
                ("read", num(t_read)),
                ("weights", num(t_weights)),
                ("psf_2n", num(t_psf)),
                ("one_residual", num(t_residual)),
                ("driver_runs", num(t_driver)),
                ("wall", num(wall.elapsed().as_secs_f64())),
            ]),
        ),
        ("patch_sweep", arr(&patch_runs)),
        ("audit", audit_entry),
        ("simd_levels", arr(&level_runs)),
        ("fraction_sweep", arr(&fraction_runs)),
        ("deep", deep_entry),
        ("sparse", arr(&sparse_runs)),
        ("certified_driver", arr(&driver_runs)),
        ("binary_report", read_json("bin-report.json")),
        ("benchmark", read_json("gemclean-bench.json")),
    ]);
    std::fs::write(outdir.join("gemclean.json"), json + "\n").map_err(|e| e.to_string())?;
    println!("wall {:.1} s", wall.elapsed().as_secs_f64());
    Ok(())
}

/// A sample with its minimum and median.
fn sample_json(sample: &[f64]) -> String {
    let stats = min_median(sample);
    let values: Vec<String> = sample.iter().map(|&v| num(v)).collect();
    obj(&[
        ("min", stats.map_or("null".into(), |s| num(s.0))),
        ("median", stats.map_or("null".into(), |s| num(s.1))),
        ("samples", arr(&values)),
    ])
}

/// Repeated wall time, CPU time and machine load of one variant.
#[derive(Default)]
struct Timed {
    name: String,
    wall: Vec<f64>,
    cpu: Vec<f64>,
    load: Vec<f64>,
    components: usize,
    major_cycles: usize,
}

impl Timed {
    fn push(&mut self, m: Measured) {
        self.wall.push(m.wall);
        self.cpu.extend(m.cpu);
        self.load.extend(m.load);
    }

    fn json(&self) -> String {
        let (wall_min, wall_median) = min_median(&self.wall).unwrap_or((f64::NAN, f64::NAN));
        let load = min_median(&self.load).map_or(f64::NAN, |s| s.1);
        println!(
            "{:<30} wall min {wall_min:8.3} s median {wall_median:8.3} s; median machine load {load:5.1}",
            self.name
        );
        obj(&[
            ("name", text(&self.name)),
            ("components", self.components.to_string()),
            ("major_cycles", self.major_cycles.to_string()),
            ("wall_seconds", sample_json(&self.wall)),
            ("cpu_seconds", sample_json(&self.cpu)),
            ("machine_load_cores", sample_json(&self.load)),
        ])
    }
}

/// The timing benchmark, one command: every variant `repeats` times,
/// interleaved round by round, with wall time, CPU time and machine load per
/// repeat, and the minimum and median. Writes the simulated MS first when it
/// is not there; writes `OUTDIR/gemclean-bench.json`.
fn bench(outdir: &Path, repeats: usize) -> Result<(), String> {
    let wall = Instant::now();
    if !outdir.join("sim.ms").join("table.dat").exists() {
        write(outdir, &default_spec())?;
    }
    let data = input::read_ms(&outdir.join("sim.ms"), &Selection::default())?;
    let weights = input::gridding_weights(&data, WeightClass::Briggs(0.0), SIDE, cell())?;
    let m = WgridMeasurement::new(
        data.uvw.clone(),
        data.freq.clone(),
        data.vis.clone(),
        weights.weights.clone(),
        SIDE,
        cell(),
        1e-6,
        opts(),
    )?;
    let psf2n = m.psf_image(2 * SIDE)?;
    let exact = psf_from_double(SIDE, &psf2n);
    let sparse = sparse_subset(&data, 16, SIDE, cell())?;
    let sparse_psf = sparse.psf_image(2 * SIDE)?;
    let sparse_exact = psf_from_double(SIDE, &sparse_psf);
    let sparse_beam = Beam::from_double(SIDE, &sparse_psf, 64)?;
    let patches = [8, 32, 64, 128, SIDE - 1];
    let beams: Vec<Beam> = patches
        .iter()
        .map(|&p| Beam::from_double(SIDE, &psf2n, p))
        .collect::<Result<_, _>>()?;
    let beam64 = &beams[2];
    let base = Settings {
        gain: GAIN,
        threshold: THRESHOLD,
        max_components: MAX_COMPONENTS,
        ..Settings::default()
    };
    let driver = DriverSettings {
        gain: GAIN,
        threshold: THRESHOLD,
        max_components: MAX_COMPONENTS,
        max_major: 200,
        max_minor: usize::MAX,
        patch: Some(64),
        rule: MinorRule::Provable,
        floor_tolerance: None,
        audit: false,
        divergence_limit: 0.0,
    };
    // gemclean runs on the operator with the kept plan, as the binary does.
    let gm = grid_measurement(&m)?;
    let gm_sparse = grid_measurement(&sparse)?;
    let lazy = |measurement: &GridMeasurement<f64>, beam: &Beam, settings: Settings| {
        gemclean::run(measurement, beam, &settings, None).map(|o| (o.steps.len(), o.cycles.len()))
    };
    let plain = |measurement: &WgridMeasurement, psf: &Psf, settings: DriverSettings| {
        clean_certified::run(measurement, psf, psf, &settings, None)
            .map(|o| (o.steps.len(), o.cycles.len()))
    };
    type Variant<'a> = (String, Box<dyn Fn() -> Result<(usize, usize), String> + 'a>);
    let mut variants: Vec<Variant> = Vec::new();
    for (patch, beam) in patches.iter().zip(&beams) {
        let (lazy, m) = (&lazy, &gm);
        variants.push((
            format!("gemclean-patch{patch}"),
            Box::new(move || lazy(m, beam, base)),
        ));
    }
    for level in [Level::Scalar, Level::Avx2, Level::Avx512] {
        if level <= kernels::detected() {
            let (lazy, m) = (&lazy, &gm);
            variants.push((
                format!("gemclean-patch64-{}", level.name()),
                Box::new(move || {
                    lazy(
                        m,
                        beam64,
                        Settings {
                            level: Some(level),
                            ..base
                        },
                    )
                }),
            ));
        }
    }
    {
        let (lazy, m) = (&lazy, &gm);
        variants.push((
            "gemclean-fraction0.8".into(),
            Box::new(move || {
                lazy(
                    m,
                    beam64,
                    Settings {
                        cycle_stop: gemclean::CycleStop::MisfitFraction,
                        major_fraction: 0.8,
                        ..base
                    },
                )
            }),
        ));
    }
    let rules = [
        ("driver-provable-patch64", MinorRule::Provable, Some(64)),
        (
            "driver-mgain0.8-patch64",
            MinorRule::MajorGain(0.8),
            Some(64),
        ),
        ("driver-mgain0.8-fullbeam", MinorRule::MajorGain(0.8), None),
    ];
    for (name, rule, patch) in rules {
        let (plain, m, exact) = (&plain, &m, &exact);
        variants.push((
            name.into(),
            Box::new(move || {
                plain(
                    m,
                    exact,
                    DriverSettings {
                        rule,
                        patch,
                        ..driver
                    },
                )
            }),
        ));
    }
    {
        let (lazy, sparse_gm, sparse, sparse_beam) = (&lazy, &gm_sparse, &sparse, &sparse_beam);
        variants.push((
            "sparse16-gemclean-patch64".into(),
            Box::new(move || {
                lazy(
                    sparse_gm,
                    sparse_beam,
                    Settings {
                        threshold: 0.005,
                        max_components: 10_000,
                        max_major: 40,
                        ..base
                    },
                )
            }),
        ));
        let (plain, sparse_exact) = (&plain, &sparse_exact);
        variants.push((
            "sparse16-driver-provable-patch64".into(),
            Box::new(move || {
                plain(
                    sparse,
                    sparse_exact,
                    DriverSettings {
                        threshold: 0.005,
                        max_components: 10_000,
                        ..driver
                    },
                )
            }),
        ));
    }
    let mut timed: Vec<Timed> = variants
        .iter()
        .map(|(name, _)| Timed {
            name: name.clone(),
            ..Timed::default()
        })
        .collect();
    let levels: Vec<Level> = [Level::Scalar, Level::Avx2, Level::Avx512]
        .into_iter()
        .filter(|&l| l <= kernels::detected())
        .collect();
    let mut kernel_samples = vec![(Vec::new(), Vec::new(), Vec::new(), Vec::new()); levels.len()];
    let mut kernel_load = Vec::new();
    for repeat in 0..repeats {
        println!("round {} of {repeats}", repeat + 1);
        for ((_, run), record) in variants.iter().zip(&mut timed) {
            let probe = Probe::start();
            let (components, cycles) = run()?;
            record.push(probe.stop());
            record.components = components;
            record.major_cycles = cycles;
        }
        let probe = Probe::start();
        let result = gemclean::kernel_benchmark(1024, 64, 2000, 200, 1);
        kernel_load.extend(probe.stop().load);
        for (k, samples) in result.iter().zip(&mut kernel_samples) {
            samples.0.push(k.patch_ns_per_pixel);
            samples.1.push(k.argmax_ns_per_pixel);
            samples.2.push(k.gather_ns_per_term);
            samples.3.push(k.patch_f32_ns_per_pixel);
        }
    }
    let runs: Vec<String> = timed.iter().map(Timed::json).collect();
    let kernel_json: Vec<String> = levels
        .iter()
        .zip(&kernel_samples)
        .map(|(level, s)| {
            let median = |x: &[f64]| min_median(x).map_or(f64::NAN, |v| v.1);
            println!(
                "kernels {:<8} median patch {:.3} ns/px (f32 map {:.3}), tile argmax {:.3} ns/px, gather {:.3} ns/term",
                level.name(),
                median(&s.0),
                median(&s.3),
                median(&s.1),
                median(&s.2)
            );
            obj(&[
                ("level", text(level.name())),
                ("patch_ns_per_pixel", sample_json(&s.0)),
                ("tile_argmax_ns_per_pixel", sample_json(&s.1)),
                ("gather_ns_per_term", sample_json(&s.2)),
                ("patch_f32_ns_per_pixel", sample_json(&s.3)),
            ])
        })
        .collect();
    let json = obj(&[
        ("timing_status", text(TIMING_STATUS)),
        ("repeats", repeats.to_string()),
        ("order", text("interleaved: every variant once per round")),
        ("threads", rayon::current_num_threads().to_string()),
        (
            "logical_cpus",
            std::thread::available_parallelism()
                .map_or(0, |n| n.get())
                .to_string(),
        ),
        ("simd_detected", text(kernels::detected().name())),
        ("os", text(std::env::consts::OS)),
        ("runs", arr(&runs)),
        ("kernels", arr(&kernel_json)),
        ("kernels_machine_load_cores", sample_json(&kernel_load)),
        ("wall_seconds", num(wall.elapsed().as_secs_f64())),
    ]);
    std::fs::write(outdir.join("gemclean-bench.json"), json + "\n").map_err(|e| e.to_string())?;
    println!("wall {:.1} s", wall.elapsed().as_secs_f64());
    Ok(())
}

/// A measurement frozen at its first residual, so a run is one minor cycle and
/// no gridding: the engineering comparison of the minor loop alone.
struct Frozen {
    side: usize,
    dirty: Vec<f64>,
    q0: f64,
    calls: std::sync::atomic::AtomicUsize,
}

impl Measurement for Frozen {
    fn side(&self) -> usize {
        self.side
    }

    fn residual(&self, _model: &[f64]) -> Result<(Vec<f64>, f64), String> {
        use std::sync::atomic::Ordering;
        if self.calls.fetch_add(1, Ordering::Relaxed) == 0 {
            Ok((self.dirty.clone(), self.q0))
        } else {
            Ok((vec![0.0; self.dirty.len()], self.q0))
        }
    }

    fn gram_apply(&self, _x: &[f64]) -> Result<Vec<f64>, String> {
        Err("not available".into())
    }
}

/// `minor MS SIDE CELL_ARCSEC THRESHOLD [repeats]`: the minor cycle alone on
/// one sky, its variants interleaved, with work counts and the science checks.
fn minor(args: &[String]) -> Result<(), String> {
    let field = |i: usize| -> Result<f64, String> {
        args.get(i)
            .and_then(|a| a.parse().ok())
            .ok_or_else(|| "minor MS SIDE CELL_ARCSEC THRESHOLD [repeats]".to_string())
    };
    let ms = Path::new(args.get(2).ok_or("minor needs an MS")?);
    let (side, cell_arcsec, threshold) = (field(3)? as usize, field(4)?, field(5)?);
    let repeats = args.get(6).and_then(|r| r.parse().ok()).unwrap_or(5);
    let cell = (cell_arcsec / 3600.0).to_radians();
    let data = input::read_ms(ms, &Selection::default())?;
    let weights = input::gridding_weights(&data, WeightClass::Briggs(0.0), side, cell)?;
    let m = WgridMeasurement::new(
        data.uvw.clone(),
        data.freq.clone(),
        data.vis.clone(),
        weights.weights.clone(),
        side,
        cell,
        1e-6,
        opts(),
    )?;
    drop(data);
    let (dirty, q0) = m.residual(&vec![0.0; side * side])?;
    let psf2n = m.psf_image(2 * side)?;
    drop(m);
    let patches = [32usize, 64, 96, 128];
    let beams: Vec<Beam> = patches
        .iter()
        .map(|&p| Beam::from_double(side, &psf2n, p))
        .collect::<Result<_, _>>()?;
    let base = Settings {
        gain: GAIN,
        threshold,
        max_components: 2_000_000,
        cycle_stop: gemclean::CycleStop::Threshold,
        max_major: 1,
        ..Settings::default()
    };
    let beam_of = |p: usize| patches.iter().position(|&q| q == p).unwrap();
    let variants: Vec<(String, usize, Settings)> = vec![
        ("p64-t32-lazy-k2000".into(), 64, base),
        (
            "p64-t32-eager-k2000".into(),
            64,
            Settings {
                lazy_bounds: false,
                ..base
            },
        ),
        (
            "p64-t64-lazy-k2000".into(),
            64,
            Settings { tile: 64, ..base },
        ),
        (
            "p64-t64-eager-k2000".into(),
            64,
            Settings {
                tile: 64,
                lazy_bounds: false,
                ..base
            },
        ),
        (
            "p64-t128-lazy-k2000".into(),
            64,
            Settings { tile: 128, ..base },
        ),
        (
            "p64-t256-lazy-k2000".into(),
            64,
            Settings { tile: 256, ..base },
        ),
        (
            "p64-t64-lazy-k8000".into(),
            64,
            Settings {
                tile: 64,
                resync_every: 8000,
                ..base
            },
        ),
        (
            "p64-t64-lazy-k32000".into(),
            64,
            Settings {
                tile: 64,
                resync_every: 32000,
                ..base
            },
        ),
        (
            "p32-t64-lazy-k8000".into(),
            32,
            Settings {
                tile: 64,
                resync_every: 8000,
                ..base
            },
        ),
        (
            "p96-t64-lazy-k8000".into(),
            96,
            Settings {
                tile: 64,
                resync_every: 8000,
                ..base
            },
        ),
        (
            "p64-t64-scalar".into(),
            64,
            Settings {
                tile: 64,
                level: Some(Level::Scalar),
                ..base
            },
        ),
        (
            "p64-t64-avx2".into(),
            64,
            Settings {
                tile: 64,
                level: Some(Level::Avx2),
                ..base
            },
        ),
    ];
    let mut samples: Vec<(Vec<f64>, Vec<f64>, Vec<f64>)> =
        vec![(Vec::new(), Vec::new(), Vec::new()); variants.len()];
    let mut last: Vec<Option<Outcome>> = vec![None; variants.len()];
    for _ in 0..repeats {
        for (i, (_, patch, settings)) in variants.iter().enumerate() {
            let frozen = Frozen {
                side,
                dirty: dirty.clone(),
                q0,
                calls: std::sync::atomic::AtomicUsize::new(0),
            };
            let out = gemclean::run(&frozen, &beams[beam_of(*patch)], settings, None)?;
            samples[i].0.push(out.timings.minor);
            samples[i].1.push(out.timings.resync);
            samples[i].2.push(out.timings.correction);
            last[i] = Some(out);
        }
    }
    println!("{q0:e} Q0; {repeats} repeats, interleaved; minimum seconds");
    let reference = last[0].as_ref().unwrap();
    let flux = |o: &Outcome| o.model.iter().sum::<f64>();
    for (i, (name, _, _)) in variants.iter().enumerate() {
        let o = last[i].as_ref().unwrap();
        let (minor_min, minor_median) = min_median(&samples[i].0).unwrap();
        let same = o.steps.len() == reference.steps.len()
            && o.steps
                .iter()
                .zip(&reference.steps)
                .all(|(a, b)| a.pixel == b.pixel);
        println!(
            "{name:<22} minor {minor_min:7.3} / {minor_median:7.3} corr {:6.3} resync {:6.3} | comps {:>7} resyncs {:>4} terms {:>11} px {:>11} rescanned {:>11} same-picks {same} flux {:.6} dQ {:.6e}",
            min_median(&samples[i].2).unwrap().0,
            min_median(&samples[i].1).unwrap().0,
            o.steps.len(),
            o.resyncs.total(),
            o.correction_terms,
            o.work.pixels_subtracted,
            o.work.pixels_rescanned,
            flux(o),
            o.cycles[0].dq_predicted,
        );
    }
    Ok(())
}

/// `sim OUTDIR SKY SIDE CELL_ARCSEC DUMPS NCHAN HOURS`.
fn sim_args(args: &[String]) -> Result<SimSpec, String> {
    let field = |i: usize| -> Result<f64, String> {
        args.get(i)
            .and_then(|a| a.parse().ok())
            .ok_or_else(|| "sim OUTDIR SKY SIDE CELL_ARCSEC DUMPS NCHAN HOURS".to_string())
    };
    let (dumps, nchan, hours) = (field(6)?, field(7)?, field(8)?);
    Ok(SimSpec {
        sky: Sky::parse(args.get(3).map_or("", String::as_str))?,
        side: field(4)? as usize,
        cell_arcsec: field(5)?,
        dumps: dumps as usize,
        dump_seconds: hours * 3600.0 / dumps,
        nchan: nchan as usize,
        hours,
        // The same 200 MHz whatever the channel count.
        channel_width: 200e6 / nchan,
        ..default_spec()
    })
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let result = match (args.get(1).map(String::as_str), args.get(2)) {
        (Some("write"), Some(out)) => write(Path::new(out), &default_spec()),
        (Some("sim"), Some(out)) => sim_args(&args).and_then(|spec| write(Path::new(out), &spec)),
        (Some("compare"), Some(out)) => compare(Path::new(out)),
        (Some("minor"), Some(_)) => minor(&args),
        (Some("bench"), Some(out)) => {
            let repeats = args.get(3).and_then(|r| r.parse().ok()).unwrap_or(5);
            bench(Path::new(out), repeats)
        }
        _ => Err("usage: gemclean_sim write|compare OUTDIR, or bench OUTDIR [repeats]".to_string()),
    };
    if let Err(e) = result {
        eprintln!("gemclean_sim: {e}");
        std::process::exit(2);
    }
}
