//! How many major cycles does CLEAN need? MeerKAT simulations for
//! `research/clean-major-cycles.md`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Run from the repository root:
//! `cargo run --release --manifest-path core/Cargo.toml --example clean_major_cycles -- OUTDIR`.
//! Writes `OUTDIR/clean-major-cycles.json` and prints the tables of the note.
//!
//! MeerKAT's 64 antennas (`data/meerkat.itrf.txt`), 1.4 GHz, one channel, a
//! 4 h track (hour angle −2 h … +2 h every 120 s) at declination −30° and at
//! −70°, natural and Briggs 0 weights, through the exact gridder
//! (`WgridMeasurement`, w-gridding on, ε below). Skies on grid pixels: 50
//! point sources with fluxes log-uniform over two decades (the brightest
//! 1 Jy), the same plus a Gaussian disc of FWHM 20 px and 1 Jy, and 500
//! sources; complex visibility noise scaled to an image rms of 5 mJy
//! (0.5 % of the brightest source). Threshold 3σ = 15 mJy, gain 0.1. Every
//! seed is fixed. Schemes: WSClean's (image-size PSF, mgain 0.8) and the
//! variants of `rang_core::clean_major`. Optional environment variables:
//! `CLEAN_MAJOR_CG` (CG iterations for `Q_∞`, default 20), `CLEAN_MAJOR_WIDE=0`
//! to skip the 1024² field. `CLEAN_MAJOR_TIMING=1` instead runs only the FFT
//! crossover and four schemes on one crowded sky, for a thread-count
//! comparison under `RAYON_NUM_THREADS` (writes `timing-<threads>.json`).

use rang_core::clean::Psf;
use rang_core::clean_certified::{
    Measurement, WgridMeasurement, psf_from_double, psf_from_image, truncation_bound,
};
use rang_core::clean_major::{
    Beams, CycleRule, CycleRun, CycleSettings, FftConvolver, OptPhase, Subtraction, mean_abs_w,
    run_cycles, w_term_bound,
};
use rang_core::weights::{WeightClass, WeightSettings, imaging_weights, padded_size};
use rang_core::wgridder::Options;
use rustfft::num_complex::Complex;
use std::f64::consts::PI;
use std::path::Path;
use std::time::Instant;

const C: f64 = 299_792_458.0;
const FREQUENCY: f64 = 1.4e9;
const EPSILON: f64 = 1e-7;
const GAIN: f64 = 0.1;
const NOISE_RMS: f64 = 0.005;
const THRESHOLD: f64 = 3.0 * NOISE_RMS;

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

/// Baseline ENU to (u, v, w) in metres at hour angle `h` and declination `dec`.
fn uvw(d: [f64; 3], lat: f64, h: f64, dec: f64) -> [f64; 3] {
    let x = -d[1] * lat.sin() + d[2] * lat.cos();
    let y = d[0];
    let z = d[1] * lat.cos() + d[2] * lat.sin();
    let (sh, ch) = h.sin_cos();
    let (sd, cd) = dec.sin_cos();
    [
        sh * x + ch * y,
        -sd * ch * x + sd * sh * y + cd * z,
        cd * ch * x - cd * sh * y + sd * z,
    ]
}

/// The 4 h track: `nrow × 3` uvw in metres.
fn track(dec_deg: f64) -> Vec<f64> {
    let (positions, lat) = enu(&antennas());
    let dec = dec_deg.to_radians();
    let mut out = Vec::new();
    for t in 0..=120 {
        let h = (-2.0 + t as f64 / 30.0) * PI / 12.0;
        for p in 0..positions.len() {
            for q in p + 1..positions.len() {
                let d = [
                    positions[p][0] - positions[q][0],
                    positions[p][1] - positions[q][1],
                    positions[p][2] - positions[q][2],
                ];
                out.extend_from_slice(&uvw(d, lat, h, dec));
            }
        }
    }
    out
}

/// Natural (all one) or Briggs 0 imaging weights on the padded grid.
fn weights(uvw: &[f64], side: usize, cell: f64, briggs: bool) -> Vec<f64> {
    let nrow = uvw.len() / 3;
    if !briggs {
        return vec![1.0; nrow];
    }
    let padded = padded_size(side, 1.2);
    let settings = WeightSettings {
        class: WeightClass::Briggs(0.0),
        width: padded,
        height: padded,
        scale_x: cell,
        scale_y: cell,
        super_weight: 1.0,
        rank_filter_level: 0.0,
        rank_filter_size: 0,
    };
    let ones = vec![1.0f32; nrow];
    let (w, _) =
        imaging_weights(&settings, uvw, &[C / FREQUENCY], &ones, &vec![true; nrow]).unwrap();
    w.iter().map(|&x| x as f64).collect()
}

struct Sky {
    name: &'static str,
    truth: Vec<f64>,
    sources: usize,
}

fn sky(name: &'static str, side: usize, seed: u64) -> Sky {
    let mut rng = Rng(seed);
    let mut truth = vec![0.0; side * side];
    let count = if name == "crowded" { 500 } else { 50 };
    let margin = 4;
    for k in 0..count {
        let flux = if k == 0 {
            1.0
        } else {
            10f64.powf(-2.0 * rng.uniform())
        };
        loop {
            let i = margin + rng.below(side - 2 * margin);
            let j = margin + rng.below(side - 2 * margin);
            let p = i * side + j;
            if truth[p] == 0.0 {
                truth[p] = flux;
                break;
            }
        }
    }
    if name == "disc" {
        // A Gaussian of FWHM 20 px and 1 Jy, off centre (the w-term grows
        // with distance from the phase centre).
        let sigma = 20.0 / (8.0 * 2f64.ln()).sqrt();
        let (ci, cj) = (side as f64 * 0.72, side as f64 * 0.32);
        let mut disc = vec![0.0; side * side];
        let mut total = 0.0;
        for (p, value) in disc.iter_mut().enumerate() {
            let di = (p / side) as f64 - ci;
            let dj = (p % side) as f64 - cj;
            let r2 = di * di + dj * dj;
            if r2 < 9.0 * 400.0 {
                *value = (-0.5 * r2 / (sigma * sigma)).exp();
                total += *value;
            }
        }
        for (t, d) in truth.iter_mut().zip(&disc) {
            *t += d / total;
        }
    }
    Sky {
        name,
        truth,
        sources: count,
    }
}

fn num(x: f64) -> String {
    if x.is_finite() {
        format!("{x:e}")
    } else {
        "null".into()
    }
}

fn opt(x: Option<f64>) -> String {
    x.map_or("null".into(), num)
}

fn text(s: &str) -> String {
    format!("\"{s}\"")
}

fn obj(fields: &[(&str, String)]) -> String {
    let inner: Vec<String> = fields
        .iter()
        .map(|(k, v)| format!("\"{k}\": {v}"))
        .collect();
    format!("{{{}}}", inner.join(", "))
}

fn arr(items: &[String]) -> String {
    format!("[{}]", items.join(", "))
}

fn median(mut v: Vec<f64>) -> f64 {
    if v.is_empty() {
        return f64::NAN;
    }
    v.sort_by(|a, b| a.total_cmp(b));
    v[v.len() / 2]
}

#[derive(Clone, Copy, PartialEq)]
enum BeamKind {
    Image,
    Double,
}

/// Which per-pixel bound on the w-term the rules use.
#[derive(Clone, Copy, PartialEq)]
enum Bound {
    /// `w_term_bound`: a certificate.
    Analytic,
    /// Twice the deviation measured at the probe columns, scaled with the
    /// distance from the phase centre: not a certificate.
    Measured,
}

#[derive(Clone, Copy)]
struct Scheme {
    name: &'static str,
    beam: BeamKind,
    rule: CycleRule,
    subtraction: Subtraction,
    bound: Bound,
    /// Minor cycles stop at 0.9 of the threshold.
    margin: bool,
    opt: bool,
    /// Data and operator without the w-term (the control).
    planar: bool,
}

fn schemes() -> Vec<Scheme> {
    let s = |name, beam, rule, subtraction, bound, margin, opt, planar| Scheme {
        name,
        beam,
        rule,
        subtraction,
        bound,
        margin,
        opt,
        planar,
    };
    let mg = CycleRule::MajorGain(0.8);
    let cyc = CycleRule::Cycle(0.5);
    let thr = CycleRule::Threshold;
    let batched = Subtraction::Batched { active: 4096 };
    use BeamKind::*;
    use Bound::*;
    use Subtraction::Direct;
    vec![
        s("wsclean", Image, mg, Direct, Analytic, false, false, false),
        s(
            "image-provable",
            Image,
            CycleRule::Provable,
            Direct,
            Analytic,
            false,
            false,
            false,
        ),
        s(
            "double-mgain",
            Double,
            mg,
            Direct,
            Analytic,
            false,
            false,
            false,
        ),
        s(
            "double-provable",
            Double,
            CycleRule::Provable,
            Direct,
            Analytic,
            false,
            false,
            false,
        ),
        s(
            "double-cycle",
            Double,
            cyc,
            Direct,
            Analytic,
            false,
            false,
            false,
        ),
        s(
            "double-cycle-measured",
            Double,
            cyc,
            Direct,
            Measured,
            false,
            false,
            false,
        ),
        s(
            "double-threshold",
            Double,
            thr,
            Direct,
            Analytic,
            false,
            false,
            false,
        ),
        s(
            "double-threshold-margin",
            Double,
            thr,
            Direct,
            Analytic,
            true,
            false,
            false,
        ),
        s(
            "fft-cycle-measured",
            Double,
            cyc,
            batched,
            Measured,
            false,
            false,
            false,
        ),
        s(
            "fft-threshold-margin",
            Double,
            thr,
            batched,
            Analytic,
            true,
            false,
            false,
        ),
        s(
            "opt-mgain",
            Double,
            mg,
            Direct,
            Analytic,
            false,
            true,
            false,
        ),
        s(
            "planar-threshold",
            Double,
            thr,
            Direct,
            Analytic,
            false,
            false,
            true,
        ),
    ]
}

/// Everything that depends on the operator but not on the sky.
struct Operator {
    m: WgridMeasurement,
    double: Psf,
    image: Psf,
    fft: FftConvolver,
    f_trunc: f64,
    mean_w: f64,
    pixel_bound: Vec<f64>,
    measured_bound: Vec<f64>,
    seconds_psf: f64,
}

fn operator(uvw: &[f64], wgt: &[f64], side: usize, cell: f64, wgridding: bool) -> Operator {
    let t = Instant::now();
    let m = WgridMeasurement::new(
        uvw.to_vec(),
        vec![FREQUENCY],
        vec![Complex::new(0.0, 0.0); wgt.len()],
        wgt.to_vec(),
        side,
        cell,
        EPSILON,
        Options {
            do_wgridding: wgridding,
            ..Options::default()
        },
    )
    .unwrap();
    let double = psf_from_double(side, &m.psf_image(2 * side).unwrap());
    let image = psf_from_image(side, &m.psf_image(side).unwrap());
    let f_trunc = truncation_bound(&double, &image, None);
    let mean_w = mean_abs_w(&m);
    let pixel_bound = if wgridding {
        w_term_bound(side, cell, mean_w)
    } else {
        vec![0.0; side * side]
    };
    let fft = FftConvolver::new(&double);
    Operator {
        m,
        double,
        image,
        fft,
        f_trunc,
        mean_w,
        measured_bound: vec![0.0; side * side],
        pixel_bound,
        seconds_psf: t.elapsed().as_secs_f64(),
    }
}

/// The w-term deviation of the double-size beam: the true Gram column of
/// probe pixels against the beam shifted there, and the bound `f_w(p)`.
fn w_probes(op: &Operator, side: usize) -> (String, f64, f64) {
    let n = side;
    let probes = [
        ("centre", n / 2, n / 2),
        ("corner-00", 0, 0),
        ("corner-0n", 0, n - 1),
        ("corner-n0", n - 1, 0),
        ("corner-nn", n - 1, n - 1),
        ("edge-l", 0, n / 2),
        ("edge-m", n / 2, 0),
        ("edge-l+", n - 1, n / 2),
        ("edge-m+", n / 2, n - 1),
        ("quarter", n / 4, n / 4),
        ("three-quarter", 3 * n / 4, n / 4),
    ];
    let mut rows = Vec::new();
    let mut worst = 0.0_f64;
    let mut worst_ratio = 0.0_f64;
    for (name, i, j) in probes {
        let p = i * n + j;
        let mut delta = vec![0.0; n * n];
        delta[p] = 1.0;
        let column = op.m.gram_apply(&delta).unwrap();
        let mut shifted = vec![0.0; n * n];
        rang_core::clean::subtract(&mut shifted, &op.double, p, -1.0, None);
        let mut dev = 0.0_f64;
        let mut sq = 0.0;
        for (a, e) in column.iter().zip(&shifted) {
            dev = dev.max((a - e).abs());
            sq += (a - e) * (a - e);
        }
        let bound = op.pixel_bound[p];
        worst = worst.max(dev);
        if bound > 0.0 {
            worst_ratio = worst_ratio.max(dev / bound);
        }
        rows.push(obj(&[
            ("probe", text(name)),
            ("pixel", p.to_string()),
            ("max_abs_deviation", num(dev)),
            ("rms_deviation", num((sq / (n * n) as f64).sqrt())),
            ("bound_f_w", num(bound)),
        ]));
    }
    (arr(&rows), worst, worst_ratio)
}

struct Outcome {
    json: String,
    row: String,
}

fn run_scheme(
    scheme: &Scheme,
    op: &Operator,
    data: &WgridMeasurement,
    truth: &[f64],
    q_floor: Option<f64>,
    label: &str,
) -> Outcome {
    let minor = match scheme.beam {
        BeamKind::Image => &op.image,
        BeamKind::Double => &op.double,
    };
    let uniform = if scheme.beam == BeamKind::Image {
        op.f_trunc
    } else {
        0.0
    };
    let beams = Beams {
        minor,
        fft: Some(&op.fft),
        reference: Some(&op.double),
        pixel_bound: Some(match scheme.bound {
            Bound::Analytic => &op.pixel_bound,
            Bound::Measured => &op.measured_bound,
        }),
    };
    let settings = CycleSettings {
        gain: GAIN,
        threshold: THRESHOLD,
        minor_threshold: scheme.margin.then_some(0.9 * THRESHOLD),
        max_components: 300_000,
        max_major: 30,
        rule: scheme.rule,
        subtraction: scheme.subtraction,
        uniform_bound: uniform,
        opt_phase: scheme.opt.then_some(OptPhase {
            max_support: 3000,
            iterations: 50,
        }),
        divergence_limit: 4.0,
        floor_tolerance: None,
    };
    let out: CycleRun = run_cycles(data, beams, &settings, q_floor).unwrap();
    let rel: Vec<f64> = out.cycles.iter().map(|c| c.gap_relative.abs()).collect();
    let max_gap = rel.iter().fold(0.0_f64, |a, &g| a.max(g));
    let med_gap = median(rel.clone());
    let max_bound = out
        .cycles
        .iter()
        .map(|c| c.gap_bound / c.q_before)
        .fold(0.0_f64, f64::max);
    let rms = (out.residual.iter().map(|r| r * r).sum::<f64>() / out.residual.len() as f64).sqrt();
    let peak = out.residual.iter().fold(0.0_f64, |a, r| a.max(r.abs()));
    let flux: f64 = out.model.iter().sum();
    let truth_flux: f64 = truth.iter().sum();
    let red = q_floor.map(|qf| (out.q_final - qf) / (out.q0 - qf));
    let batches: usize = out.cycles.iter().map(|c| c.batches).sum();
    let audited = out.cycles.iter().any(|c| c.audited);
    let cycles: Vec<String> = out
        .cycles
        .iter()
        .map(|c| {
            obj(&[
                ("index", c.index.to_string()),
                ("components", c.components.to_string()),
                ("batches", c.batches.to_string()),
                ("peak_start", num(c.peak_start)),
                ("peak_working_end", num(c.peak_working_end)),
                ("q_before", num(c.q_before)),
                ("q_after", num(c.q_after)),
                ("dq_exact", num(c.dq_exact)),
                ("dq_predicted", num(c.dq_predicted)),
                ("gap", num(c.gap)),
                ("gap_relative", num(c.gap_relative)),
                ("gap_bound", num(c.gap_bound)),
                ("abs_flux", num(c.abs_flux)),
                ("ascending_steps", c.ascending_steps.to_string()),
                ("opt_support", c.opt_support.to_string()),
                ("opt_iterations", c.opt_iterations.to_string()),
                ("opt_dq_model", num(c.opt_dq_model)),
                ("kappa", opt(c.kappa)),
                ("reducible", opt(c.reducible)),
                ("stop", text(&format!("{:?}", c.stop))),
                ("minor_seconds", num(c.minor_seconds)),
                ("opt_seconds", num(c.opt_seconds)),
                ("major_seconds", num(c.major_seconds)),
            ])
        })
        .collect();
    let json = obj(&[
        ("scheme", text(scheme.name)),
        (
            "beam",
            text(if scheme.beam == BeamKind::Image {
                "image"
            } else {
                "double"
            }),
        ),
        ("rule", text(&scheme.rule.name())),
        ("subtraction", text(&format!("{:?}", scheme.subtraction))),
        ("opt_phase", scheme.opt.to_string()),
        (
            "bound",
            text(if scheme.bound == Bound::Analytic {
                "analytic"
            } else {
                "measured"
            }),
        ),
        (
            "minor_threshold",
            num(settings.minor_threshold.unwrap_or(THRESHOLD)),
        ),
        ("planar", scheme.planar.to_string()),
        ("major_cycles", out.cycles.len().to_string()),
        ("components", out.steps.len().to_string()),
        ("batches", batches.to_string()),
        ("stop", text(&format!("{:?}", out.stop))),
        ("q0", num(out.q0)),
        ("q_final", num(out.q_final)),
        ("q_final_over_q0", num(out.q_final / out.q0)),
        ("reducible_final", opt(red)),
        ("max_abs_gap_relative", num(max_gap)),
        ("median_abs_gap_relative", num(med_gap)),
        ("max_gap_bound_relative", num(max_bound)),
        (
            "ascending_steps_audited",
            if audited {
                out.ascending_steps().to_string()
            } else {
                "null".into()
            },
        ),
        ("ascending_cycles", out.ascending_cycles().to_string()),
        ("residual_rms", num(rms)),
        ("residual_peak_abs", num(peak)),
        ("model_flux", num(flux)),
        ("truth_flux", num(truth_flux)),
        (
            "model_flux_error_relative",
            num((flux - truth_flux) / truth_flux),
        ),
        ("seconds", num(out.seconds)),
        ("minor_seconds", num(out.minor_seconds)),
        ("major_seconds", num(out.major_seconds)),
        ("opt_seconds", num(out.opt_seconds)),
        ("cycles", arr(&cycles)),
    ]);
    let row = format!(
        "| {label} | {} | {} | {} | {:?} | {:.2e} | {:.2e} | {} | {} | {:.3e} | {} | {:.2} | {:.2} | {:+.2} % | {:.2} | {:.2} | {:.2} |",
        scheme.name,
        out.cycles.len(),
        out.steps.len(),
        out.stop,
        max_gap,
        med_gap,
        if audited {
            out.ascending_steps().to_string()
        } else {
            "–".into()
        },
        out.ascending_cycles(),
        out.q_final / out.q0,
        red.map_or("–".into(), |r| format!("{r:.2e}")),
        rms * 1e3,
        peak * 1e3,
        100.0 * (flux - truth_flux) / truth_flux,
        out.seconds,
        out.minor_seconds + out.opt_seconds,
        out.major_seconds,
    );
    Outcome { json, row }
}

/// The batch size at which one FFT pair beats direct subtraction, and four
/// schemes on the crowded sky, at the current rayon thread count.
fn timing(outdir: &str) {
    let threads = rayon::current_num_threads();
    let mut sizes = Vec::new();
    for (side, cell_arcsec) in [(512usize, 2.0f64), (1024, 4.0)] {
        let cell = cell_arcsec / 3600.0 * PI / 180.0;
        let uvw = track(-30.0);
        let wgt = weights(&uvw, side, cell, false);
        let op = operator(&uvw, &wgt, side, cell, true);
        let mut rng = Rng(5);
        let comps: Vec<(usize, f64)> = (0..64)
            .map(|_| (rng.below(side * side), rng.uniform() - 0.5))
            .collect();
        let mut image = vec![0.0; side * side];
        let t = Instant::now();
        for &(p, c) in &comps {
            rang_core::clean::subtract(&mut image, &op.double, p, c, None);
        }
        let direct = t.elapsed().as_secs_f64() / comps.len() as f64;
        let t = Instant::now();
        let mut peak = 0.0;
        for _ in 0..comps.len() {
            peak += rang_core::clean::argmax_abs(&image).1;
        }
        let argmax = t.elapsed().as_secs_f64() / comps.len() as f64;
        let t = Instant::now();
        for _ in 0..8 {
            peak += op.fft.apply(&comps)[0];
        }
        let fft = t.elapsed().as_secs_f64() / 8.0;
        println!(
            "{side}: threads {threads}, direct {:.3} ms, argmax {:.3} ms per component; FFT pair {:.2} ms; crossover K {:.0} ({:.0} with argmax) [{peak:.1e}]",
            direct * 1e3,
            argmax * 1e3,
            fft * 1e3,
            fft / direct,
            fft / (direct + argmax)
        );
        sizes.push(obj(&[
            ("side", side.to_string()),
            ("direct_subtract_seconds", num(direct)),
            ("argmax_seconds", num(argmax)),
            ("fft_pair_seconds", num(fft)),
            ("crossover_components", num(fft / direct)),
            ("crossover_with_argmax", num(fft / (direct + argmax))),
        ]));
    }
    let side = 512;
    let cell = 2.0 / 3600.0 * PI / 180.0;
    let uvw = track(-30.0);
    let wgt = weights(&uvw, side, cell, false);
    let mut op = operator(&uvw, &wgt, side, cell, true);
    let sky = sky("crowded", side, 1002);
    let mut noise_rng = Rng(79);
    let noise: Vec<Complex<f64>> = (0..wgt.len())
        .map(|_| Complex::new(noise_rng.normal(), noise_rng.normal()))
        .collect();
    let image = op.m.image(&noise).unwrap();
    let rms = (image.iter().map(|x| x * x).sum::<f64>() / image.len() as f64).sqrt();
    let clean = op.m.predict(&sky.truth).unwrap();
    op.m.vis = clean
        .iter()
        .zip(&noise)
        .map(|(c, e)| c + e * (NOISE_RMS / rms))
        .collect();
    let mut runs = Vec::new();
    for scheme in schemes() {
        if !matches!(
            scheme.name,
            "wsclean" | "double-mgain" | "double-threshold" | "fft-threshold-margin"
        ) {
            continue;
        }
        let outcome = run_scheme(&scheme, &op, &op.m, &sky.truth, None, "crowded");
        println!("{}", outcome.row);
        runs.push(outcome.json);
    }
    let json = obj(&[
        ("threads", threads.to_string()),
        ("sizes", arr(&sizes)),
        ("runs", arr(&runs)),
    ]);
    std::fs::write(
        Path::new(outdir).join(format!("timing-{threads}.json")),
        json + "
",
    )
    .unwrap();
}

fn main() {
    let outdir = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "outputs/clean-major-cycles".to_string());
    std::fs::create_dir_all(&outdir).expect("output directory");
    if std::env::var("CLEAN_MAJOR_TIMING").is_ok() {
        timing(&outdir);
        return;
    }
    let wall = Instant::now();
    let cg_iterations: usize = std::env::var("CLEAN_MAJOR_CG")
        .ok()
        .map_or(20, |v| v.parse().unwrap());
    let wide = std::env::var("CLEAN_MAJOR_WIDE").map_or(true, |v| v != "0");
    let threads = std::thread::available_parallelism().map_or(0, |n| n.get());
    let mut datasets = Vec::new();
    let mut gap_table = Vec::new();
    let mut rows = Vec::new();
    // (side, cell arcsec, run the skies)
    let mut fields = vec![(512usize, 2.0f64, true)];
    if wide {
        fields.push((1024, 4.0, true));
    }
    for &(side, cell_arcsec, _) in &fields {
        let cell = cell_arcsec / 3600.0 * PI / 180.0;
        for dec in [-30.0, -70.0] {
            let uvw = track(dec);
            let nrow = uvw.len() / 3;
            for briggs in [false, true] {
                let wname = if briggs { "briggs0" } else { "natural" };
                let wgt = weights(&uvw, side, cell, briggs);
                let mut op = operator(&uvw, &wgt, side, cell, true);
                let mut planar = operator(&uvw, &wgt, side, cell, false);
                let (probes, worst, worst_ratio) = w_probes(&op, side);
                // The measured bound: twice the worst probe deviation, scaled
                // with the distance from the phase centre (the first-order
                // w-term is linear in it); not a certificate.
                let rmax = (2.0f64).sqrt() * (side / 2) as f64;
                op.measured_bound = (0..side * side)
                    .map(|p| {
                        let di = (p / side) as f64 - (side / 2) as f64;
                        let dj = (p % side) as f64 - (side / 2) as f64;
                        2.0 * worst * (di * di + dj * dj).sqrt() / rmax
                    })
                    .collect();
                let max_fw = op.pixel_bound.iter().fold(0.0_f64, |a, &b| a.max(b));
                let field = format!("{side}x{cell_arcsec}\"");
                println!(
                    "{field} dec {dec} {wname}: {nrow} vis, mean |w| {:.1} λ, f_trunc {:.4}, f_w max {:.4}, measured w deviation max {:.3e} ({:.3} of the bound), PSFs {:.1} s",
                    op.mean_w, op.f_trunc, max_fw, worst, worst_ratio, op.seconds_psf
                );
                gap_table.push(format!(
                    "| {field} | {dec} | {wname} | {:.0} | {:.4} | {:.4} | {:.3e} | {:.3} |",
                    op.mean_w, op.f_trunc, max_fw, worst, worst_ratio
                ));
                // The full scheme set on the 512² field; the wide field runs
                // the point-source sky with natural weights only.
                let skies: Vec<&'static str> = if side == 512 {
                    vec!["points", "disc", "crowded"]
                } else if !briggs {
                    vec!["points"]
                } else {
                    vec![]
                };
                let mut runs = Vec::new();
                for (k, sky_name) in skies.iter().enumerate() {
                    let sky = sky(sky_name, side, 1000 + k as u64);
                    let mut noise_rng = Rng(77 + k as u64);
                    let noise: Vec<Complex<f64>> = (0..nrow)
                        .map(|_| Complex::new(noise_rng.normal(), noise_rng.normal()))
                        .collect();
                    let t = Instant::now();
                    let image = op.m.image(&noise).unwrap();
                    let rms =
                        (image.iter().map(|x| x * x).sum::<f64>() / image.len() as f64).sqrt();
                    let scale = NOISE_RMS / rms;
                    let make = |m: &mut WgridMeasurement| {
                        let clean = m.predict(&sky.truth).unwrap();
                        m.vis = clean
                            .iter()
                            .zip(&noise)
                            .map(|(c, e)| c + e * scale)
                            .collect();
                    };
                    make(&mut op.m);
                    make(&mut planar.m);
                    let (dirty, q0) = op.m.residual(&vec![0.0; side * side]).unwrap();
                    let (floor, _) = rang_core::clean_certified::misfit_floor(
                        &op.m,
                        &dirty,
                        cg_iterations,
                        1e-12,
                    )
                    .unwrap();
                    let dirty_peak = dirty.iter().fold(0.0_f64, |a, r| a.max(r.abs()));
                    println!(
                        "  sky {sky_name}: {} sources, noise scale {scale:.4e}, dirty peak {dirty_peak:.4}, Q0 {q0:.4e}, Q_inf <= {:.4e} ({:.3e} of Q0, CG {} it, {:.1} s); data {:.1} s",
                        sky.sources,
                        floor.q_floor,
                        floor.q_floor / q0,
                        floor.iterations,
                        floor.seconds,
                        t.elapsed().as_secs_f64()
                    );
                    let label = format!("{field} {dec} {wname} {}", sky.name);
                    let mut run_json = Vec::new();
                    for scheme in schemes() {
                        if side != 512
                            && !matches!(
                                scheme.name,
                                "wsclean"
                                    | "double-mgain"
                                    | "double-threshold"
                                    | "double-threshold-margin"
                                    | "fft-threshold-margin"
                                    | "double-cycle-measured"
                                    | "planar-threshold"
                            )
                        {
                            continue;
                        }
                        let (o, data, qf) = if scheme.planar {
                            (&planar, &planar.m, None)
                        } else {
                            (&op, &op.m, Some(floor.q_floor))
                        };
                        let outcome = run_scheme(&scheme, o, data, &sky.truth, qf, &label);
                        println!("{}", outcome.row);
                        rows.push(outcome.row);
                        run_json.push(outcome.json);
                    }
                    runs.push(obj(&[
                        ("sky", text(sky.name)),
                        ("sources", sky.sources.to_string()),
                        ("noise_scale", num(scale)),
                        ("dirty_peak", num(dirty_peak)),
                        ("q0", num(q0)),
                        ("q_floor", num(floor.q_floor)),
                        ("q_floor_over_q0", num(floor.q_floor / q0)),
                        ("cg_iterations", floor.iterations.to_string()),
                        ("cg_relative_residual", num(floor.relative_residual)),
                        ("cg_seconds", num(floor.seconds)),
                        ("runs", arr(&run_json)),
                    ]));
                }
                datasets.push(obj(&[
                    ("side", side.to_string()),
                    ("cell_arcsec", num(cell_arcsec)),
                    ("declination_deg", num(dec)),
                    ("weights", text(wname)),
                    ("visibilities", nrow.to_string()),
                    ("real_data_2m", (2 * nrow).to_string()),
                    ("pixels", (side * side).to_string()),
                    ("mean_abs_w_wavelengths", num(op.mean_w)),
                    ("image_psf_truncation_f", num(op.f_trunc)),
                    ("double_psf_coherence", num(op.double.coherence())),
                    ("f_w_max", num(max_fw)),
                    ("w_deviation_max", num(worst)),
                    ("w_deviation_over_bound_max", num(worst_ratio)),
                    ("w_probes", probes),
                    ("psf_seconds", num(op.seconds_psf + planar.seconds_psf)),
                    ("skies", arr(&runs)),
                ]));
            }
        }
    }
    println!(
        "\n| field | dec | weights | mean abs w (λ) | f_trunc (image PSF) | f_w max (bound) | measured max deviation | measured / bound |"
    );
    println!("| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |");
    for r in &gap_table {
        println!("{r}");
    }
    println!(
        "\n| dataset | scheme | major cycles | components | stop | max gap/Q | median gap/Q | ascending steps | ascending cycles | Q/Q0 | (Q−Q∞)/(Q0−Q∞) | rms (mJy) | peak (mJy) | flux error | wall (s) | minor (s) | major (s) |"
    );
    println!(
        "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    );
    for r in &rows {
        println!("{r}");
    }
    let json = obj(&[
        ("date", text("2026-11-02")),
        (
            "timing_status",
            text("PROVISIONAL unless the host was idle: wall times only, no CPU time or load"),
        ),
        ("frequency_hz", num(FREQUENCY)),
        (
            "track",
            text("hour angle -2 h to +2 h every 120 s, 121 times, 2016 baselines"),
        ),
        ("epsilon", num(EPSILON)),
        ("gain", num(GAIN)),
        ("noise_image_rms", num(NOISE_RMS)),
        ("threshold", num(THRESHOLD)),
        ("cg_iterations", cg_iterations.to_string()),
        ("threads", threads.to_string()),
        ("datasets", arr(&datasets)),
        ("wall_seconds", num(wall.elapsed().as_secs_f64())),
    ]);
    std::fs::write(
        Path::new(&outdir).join("clean-major-cycles.json"),
        json + "\n",
    )
    .unwrap();
    println!("wall {:.1} s", wall.elapsed().as_secs_f64());
}
