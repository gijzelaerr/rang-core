//! The measured half of `research/gmclean.md`: a simulated MeerKAT
//! Measurement Set, and gmclean against the certified driver's provable rule
//! and a Clark-rule run on the same data.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! ```text
//! cargo run --release --manifest-path core/Cargo.toml --example gmclean_sim -- write OUTDIR
//! core/target/release/gmclean -name OUTDIR/bin -size 1024 1024 -scale 2asec -weight briggs 0 \
//!     -niter 100000 -abs-threshold 1e-3 -patch 64 OUTDIR/sim.ms
//! cargo run --release --manifest-path core/Cargo.toml --example gmclean_sim -- bench OUTDIR
//! cargo run --release --manifest-path core/Cargo.toml --example gmclean_sim -- compare OUTDIR
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
//! writes `OUTDIR/gmclean.json`; it embeds `OUTDIR/bin-report.json` when it
//! exists.

use rang_core::clean::Psf;
use rang_core::clean_certified::{
    self, Certified, DriverSettings, Measurement, MinorRule, WgridMeasurement, psf_from_double,
};
use rang_core::gmclean::host::{Measured, Probe, min_median};
use rang_core::gmclean::input::{self, MsArrays, Selection};
use rang_core::gmclean::json::{arr, num, obj, text};
use rang_core::gmclean::kernels::{self, Level};
use rang_core::gmclean::{self, Beam, Outcome, Settings};
use rang_core::weights::WeightClass;
use rang_core::wgridder::Options;
use rustfft::num_complex::Complex;
use std::f64::consts::PI;
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
const FLUX_MIN: f64 = 0.01;
const FLUX_MAX: f64 = 1.0;
const NOISE_FRACTION: f64 = 0.005;
const THRESHOLD: f64 = 1e-3;
const GAIN: f64 = 0.1;
const MAX_COMPONENTS: usize = 200_000;
const TIMING_STATUS: &str = "PROVISIONAL: measured on a shared, loaded host; read with the recorded machine load; no final speedup is stated";

struct Rng(u64);

impl Rng {
    fn uniform(&mut self) -> f64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0 >> 11) as f64 / (1u64 << 53) as f64
    }

    fn normal(&mut self) -> f64 {
        let u = self.uniform().max(1e-300);
        let v = self.uniform();
        (-2.0 * u.ln()).sqrt() * (2.0 * PI * v).cos()
    }
}

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

/// ITRF to east-north-up about the array centroid, and its latitude.
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

/// Baseline east-north-up to `(u, v, w)` metres at hour angle `h`.
fn baseline_uvw(d: [f64; 3], lat: f64, h: f64, dec: f64) -> [f64; 3] {
    let x = -d[1] * lat.sin() + d[2] * lat.cos();
    let y = d[0];
    let z = d[1] * lat.cos() + d[2] * lat.sin();
    [
        h.sin() * x + h.cos() * y,
        -dec.sin() * h.cos() * x + dec.sin() * h.sin() * y + dec.cos() * z,
        dec.cos() * h.cos() * x - dec.cos() * h.sin() * y + dec.sin() * z,
    ]
}

fn opts() -> Options {
    Options {
        flip_v: true,
        flip_w: true,
        ..Options::default()
    }
}

fn cell() -> f64 {
    (CELL_ARCSEC / 3600.0).to_radians()
}

fn truth_sources() -> Vec<(usize, usize, f64)> {
    let mut rng = Rng(SEED);
    let margin = SIDE / 20;
    let span = (SIDE - 2 * margin) as f64;
    (0..SOURCES)
        .map(|_| {
            let i = margin + (rng.uniform() * span) as usize;
            let j = margin + (rng.uniform() * span) as usize;
            let flux = FLUX_MIN * (FLUX_MAX / FLUX_MIN).powf(rng.uniform());
            (i, j, flux)
        })
        .collect()
}

fn write(outdir: &Path) -> Result<(), String> {
    std::fs::create_dir_all(outdir).map_err(|e| e.to_string())?;
    let wall = Instant::now();
    let itrf = antennas();
    let (positions, lat) = enu(&itrf);
    let dec = DEC_DEG.to_radians();
    let freq: Vec<f64> = (0..NCHAN).map(|c| 1.2e9 + 25e6 * c as f64).collect();
    let mut uvw = Vec::new();
    let mut ant1 = Vec::new();
    let mut ant2 = Vec::new();
    let mut time = Vec::new();
    for t in 0..DUMPS {
        let hours = (t as f64 + 0.5) / DUMPS as f64 * 2.0 - 1.0;
        let h = hours * PI / 12.0;
        for p in 0..positions.len() {
            for q in p + 1..positions.len() {
                let d = [
                    positions[p][0] - positions[q][0],
                    positions[p][1] - positions[q][1],
                    positions[p][2] - positions[q][2],
                ];
                uvw.extend_from_slice(&baseline_uvw(d, lat, h, dec));
                ant1.push(p as i32);
                ant2.push(q as i32);
                time.push(5.0e9 + DUMP_SECONDS * t as f64);
            }
        }
    }
    let nrow = ant1.len();
    let mut truth = vec![0.0; SIDE * SIDE];
    let sources = truth_sources();
    for &(i, j, flux) in &sources {
        truth[i * SIDE + j] += flux;
    }
    let vis0 = vec![Complex::new(0.0, 0.0); nrow * NCHAN];
    let wgt = vec![1.0; nrow * NCHAN];
    let m = WgridMeasurement::new(
        uvw.clone(),
        freq.clone(),
        vis0,
        wgt,
        SIDE,
        cell(),
        1e-9,
        opts(),
    )?;
    let t = Instant::now();
    let predicted = m.predict(&truth)?;
    println!(
        "predicted {} visibilities in {:.2} s",
        predicted.len(),
        t.elapsed().as_secs_f64()
    );
    let mut rng = Rng(SEED ^ 0x5555_aaaa_5555_aaaa);
    let sigma = NOISE_FRACTION * FLUX_MAX;
    let mut data = vec![0.0f32; 2 * nrow * NCHAN * 4];
    for (k, v) in predicted.iter().enumerate() {
        let cell = k * 4;
        for corr in 0..4 {
            let parallel = corr == 0 || corr == 3;
            let (re, im) = if parallel { (v.re, v.im) } else { (0.0, 0.0) };
            data[2 * (cell + corr)] = (re + sigma * rng.normal()) as f32;
            data[2 * (cell + corr) + 1] = (im + sigma * rng.normal()) as f32;
        }
    }
    let weight = vec![1.0f32; nrow * NCHAN * 4];
    let path = outdir.join("sim.ms");
    let t = Instant::now();
    input::write_ms(
        &path,
        &MsArrays {
            uvw: &uvw,
            antenna1: &ant1,
            antenna2: &ant2,
            time: &time,
            interval: DUMP_SECONDS,
            freq: &freq,
            data: &data,
            weight_spectrum: &weight,
            antennas: &itrf,
            dish_diameter: 13.5,
            phase_dir: (RA_RAD, dec),
        },
    )?;
    let t_write = t.elapsed().as_secs_f64();
    let items: Vec<String> = sources
        .iter()
        .map(|&(i, j, f)| {
            obj(&[
                ("i", i.to_string()),
                ("j", j.to_string()),
                ("flux_jy", num(f)),
            ])
        })
        .collect();
    let meta = obj(&[
        ("seed", SEED.to_string()),
        ("side", SIDE.to_string()),
        ("cell_arcsec", num(CELL_ARCSEC)),
        ("rows", nrow.to_string()),
        ("channels", NCHAN.to_string()),
        ("dumps", DUMPS.to_string()),
        ("dump_seconds", num(DUMP_SECONDS)),
        ("dec_deg", num(DEC_DEG)),
        ("noise_sigma_jy_per_part_per_correlation", num(sigma)),
        (
            "predict",
            text("dirty2vis on pixel positions, epsilon 1e-9, flip_v, flip_w"),
        ),
        ("sources", arr(&items)),
        ("seconds_write_ms", num(t_write)),
        ("seconds_wall", num(wall.elapsed().as_secs_f64())),
    ]);
    std::fs::write(outdir.join("truth.json"), meta + "\n").map_err(|e| e.to_string())?;
    println!(
        "wrote {} ({nrow} rows, {NCHAN} channels) in {t_write:.2} s; wall {:.2} s",
        path.display(),
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

fn gmclean_entry(name: &str, out: &Outcome) -> String {
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

/// The rows of the first `nant` antennas (the row order of [`write`]), with
/// natural weights.
fn sparse_subset(
    data: &input::StokesI,
    nant: usize,
    side: usize,
    cell: f64,
) -> Result<WgridMeasurement, String> {
    let total = antennas().len();
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
        let out = gmclean::run(&m, &beam, &base, None)?;
        let name = format!("gmclean-patch{patch}");
        patch_runs.push(obj(&[
            ("beam_setup_seconds", num(t_beam)),
            ("entry", gmclean_entry(&name, &out)),
        ]));
    }

    let beam = Beam::from_double(SIDE, &psf2n, 64)?;

    // Audited, shallower: lazy against brute force at every step.
    let audited = gmclean::run(
        &m,
        &beam,
        &Settings {
            audit: true,
            ..base
        },
        None,
    )?;
    let audit_entry = gmclean_entry("gmclean-patch64-audit", &audited);

    // The whole loop at each SIMD level.
    let mut level_runs = Vec::new();
    let mut steps_reference: Option<Vec<(usize, f64)>> = None;
    for level in [Level::Scalar, Level::Avx2, Level::Avx512] {
        if level > kernels::detected() {
            continue;
        }
        let out = gmclean::run(
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
        let name = format!("gmclean-patch64-{}", level.name());
        level_runs.push(obj(&[
            ("level", text(level.name())),
            ("same_picks_as_scalar", same.to_string()),
            ("entry", gmclean_entry(&name, &out)),
        ]));
    }

    // The major-cycle fraction, and a deeper threshold.
    let mut fraction_runs = Vec::new();
    for fraction in [0.5, 0.9, 0.99, 1.0] {
        let out = gmclean::run(
            &m,
            &beam,
            &Settings {
                major_fraction: fraction,
                ..base
            },
            None,
        )?;
        fraction_runs.push(gmclean_entry(&format!("gmclean-fraction{fraction}"), &out));
    }
    let deep = gmclean::run(
        &m,
        &beam,
        &Settings {
            threshold: THRESHOLD / 10.0,
            max_components: 500_000,
            ..base
        },
        None,
    )?;
    let deep_entry = gmclean_entry("gmclean-deep-1e-4", &deep);

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
        let out = gmclean::run(
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
        let lazy = gmclean_entry(&format!("sparse{nant}-gmclean-patch64"), &out);
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
            ("gmclean", lazy),
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
            text("gmclean on a simulated MeerKAT MS (research/gmclean.md)"),
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
        ("benchmark", read_json("gmclean-bench.json")),
    ]);
    std::fs::write(outdir.join("gmclean.json"), json + "\n").map_err(|e| e.to_string())?;
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
/// is not there; writes `OUTDIR/gmclean-bench.json`.
fn bench(outdir: &Path, repeats: usize) -> Result<(), String> {
    let wall = Instant::now();
    if !outdir.join("sim.ms").join("table.dat").exists() {
        write(outdir)?;
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
    let lazy = |measurement: &WgridMeasurement, beam: &Beam, settings: Settings| {
        gmclean::run(measurement, beam, &settings, None).map(|o| (o.steps.len(), o.cycles.len()))
    };
    let plain = |measurement: &WgridMeasurement, psf: &Psf, settings: DriverSettings| {
        clean_certified::run(measurement, psf, psf, &settings, None)
            .map(|o| (o.steps.len(), o.cycles.len()))
    };
    type Variant<'a> = (String, Box<dyn Fn() -> Result<(usize, usize), String> + 'a>);
    let mut variants: Vec<Variant> = Vec::new();
    for (patch, beam) in patches.iter().zip(&beams) {
        let (lazy, m) = (&lazy, &m);
        variants.push((
            format!("gmclean-patch{patch}"),
            Box::new(move || lazy(m, beam, base)),
        ));
    }
    for level in [Level::Scalar, Level::Avx2, Level::Avx512] {
        if level <= kernels::detected() {
            let (lazy, m) = (&lazy, &m);
            variants.push((
                format!("gmclean-patch64-{}", level.name()),
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
        let (lazy, m) = (&lazy, &m);
        variants.push((
            "gmclean-fraction1".into(),
            Box::new(move || {
                lazy(
                    m,
                    beam64,
                    Settings {
                        major_fraction: 1.0,
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
        let (lazy, sparse, sparse_beam) = (&lazy, &sparse, &sparse_beam);
        variants.push((
            "sparse16-gmclean-patch64".into(),
            Box::new(move || {
                lazy(
                    sparse,
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
    let mut kernel_samples = vec![(Vec::new(), Vec::new(), Vec::new()); levels.len()];
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
        let result = gmclean::kernel_benchmark(1024, 64, 2000, 200, 1);
        kernel_load.extend(probe.stop().load);
        for (k, samples) in result.iter().zip(&mut kernel_samples) {
            samples.0.push(k.patch_ns_per_pixel);
            samples.1.push(k.argmax_ns_per_pixel);
            samples.2.push(k.gather_ns_per_term);
        }
    }
    let runs: Vec<String> = timed.iter().map(Timed::json).collect();
    let kernel_json: Vec<String> = levels
        .iter()
        .zip(&kernel_samples)
        .map(|(level, s)| {
            let median = |x: &[f64]| min_median(x).map_or(f64::NAN, |v| v.1);
            println!(
                "kernels {:<8} median patch {:.3} ns/px, tile argmax {:.3} ns/px, gather {:.3} ns/term",
                level.name(),
                median(&s.0),
                median(&s.1),
                median(&s.2)
            );
            obj(&[
                ("level", text(level.name())),
                ("patch_ns_per_pixel", sample_json(&s.0)),
                ("tile_argmax_ns_per_pixel", sample_json(&s.1)),
                ("gather_ns_per_term", sample_json(&s.2)),
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
    std::fs::write(outdir.join("gmclean-bench.json"), json + "\n").map_err(|e| e.to_string())?;
    println!("wall {:.1} s", wall.elapsed().as_secs_f64());
    Ok(())
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let result = match (args.get(1).map(String::as_str), args.get(2)) {
        (Some("write"), Some(out)) => write(Path::new(out)),
        (Some("compare"), Some(out)) => compare(Path::new(out)),
        (Some("bench"), Some(out)) => {
            let repeats = args.get(3).and_then(|r| r.parse().ok()).unwrap_or(5);
            bench(Path::new(out), repeats)
        }
        _ => Err("usage: gmclean_sim write|compare OUTDIR, or bench OUTDIR [repeats]".to_string()),
    };
    if let Err(e) = result {
        eprintln!("gmclean_sim: {e}");
        std::process::exit(2);
    }
}
