//! Certified CLEAN on the LUNO 1934−638 four-station slice
//! (`research/clean-certified-imaging.md`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Run from the repository root, after `examples/clean_certified_export.py`:
//! `cargo run --release --manifest-path core/Cargo.toml --example clean_certified -- INPUTS OUTDIR [threshold]`.
//!
//! `INPUTS` holds the raw arrays of the export (`uvw.f64`, `freq.f64`,
//! `vis.c128`, `wgt.f64`) and optionally WSClean PSF images in the gridder's
//! layout (`wsclean-psf-<name>.f64`, 512 × 512). The run computes the exact
//! beam on a 1024² grid, `Q_∞` by conjugate gradients, then one certified
//! CLEAN per configuration (gain 0.1, the given absolute threshold, default
//! 0.05 Jy), and writes `OUTDIR/clean-certified.json` with the per-cycle
//! diagnostics and `OUTDIR/<config>-{model,residual}.npy` (gridder layout:
//! `[i, j]` with `i` along `l`; the transpose is WSClean's FITS order).

use rang_core::clean::Psf;
use rang_core::clean_certified::{
    Certified, DriverSettings, Measurement, MinorRule, WgridMeasurement, erc_certificate,
    misfit_floor, psf_from_image, run,
};
use rang_core::wgridder::Options;
use rustfft::num_complex::Complex;
use std::path::Path;
use std::time::Instant;

const SIDE: usize = 512;
const CELL_ARCSEC: f64 = 8.0;
const EPSILON: f64 = 1e-9;
const GAIN: f64 = 0.1;
const MGAIN: f64 = 0.8;
const MAX_COMPONENTS: usize = 100_000;
const CG_ITERATIONS: usize = 200;
const ERC_MAX_K: usize = 4000;

fn read_f64(path: &Path) -> Vec<f64> {
    let bytes = std::fs::read(path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
    bytes
        .chunks_exact(8)
        .map(|b| f64::from_le_bytes(b.try_into().unwrap()))
        .collect()
}

fn write_npy(path: &Path, data: &[f64], rows: usize, cols: usize) {
    let mut header =
        format!("{{'descr': '<f8', 'fortran_order': False, 'shape': ({rows}, {cols}), }}");
    while (10 + header.len() + 1) % 64 != 0 {
        header.push(' ');
    }
    header.push('\n');
    let mut out = Vec::with_capacity(10 + header.len() + data.len() * 8);
    out.extend_from_slice(b"\x93NUMPY\x01\x00");
    out.extend_from_slice(&(header.len() as u16).to_le_bytes());
    out.extend_from_slice(header.as_bytes());
    for v in data {
        out.extend_from_slice(&v.to_le_bytes());
    }
    std::fs::write(path, out).unwrap();
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

/// Model and residual statistics in the conventions of the comparison.
fn summarise(out: &Certified, n: usize) -> Vec<(&'static str, String)> {
    let total: f64 = out.model.iter().sum();
    let positive: f64 = out.model.iter().filter(|&&c| c > 0.0).sum();
    let negative: f64 = out.model.iter().filter(|&&c| c < 0.0).sum();
    let half = (n / 2) as isize;
    let mut central = 0.0;
    for (p, &c) in out.model.iter().enumerate() {
        let i = (p / n) as isize - half;
        let j = (p % n) as isize - half;
        if i.abs() <= 32 && j.abs() <= 32 {
            central += c;
        }
    }
    let rms = (out.residual.iter().map(|r| r * r).sum::<f64>() / out.residual.len() as f64).sqrt();
    let peak = out.residual.iter().fold(0.0_f64, |a, r| a.max(r.abs()));
    let nonzero = out.model.iter().filter(|&&c| c != 0.0).count();
    vec![
        ("components", out.steps.len().to_string()),
        ("model_pixels", nonzero.to_string()),
        ("model_flux_total", num(total)),
        ("model_flux_positive", num(positive)),
        ("model_flux_negative", num(negative)),
        ("model_flux_central_65px", num(central)),
        ("residual_rms", num(rms)),
        ("residual_peak_abs", num(peak)),
        ("q0", num(out.q0)),
        ("q_final", num(out.q_final)),
        ("q_final_over_q0", num(out.q_final / out.q0)),
        ("f_truncation_bound", num(out.f)),
        ("major_cycles", out.cycles.len().to_string()),
        ("ascending_steps", out.ascending_steps().to_string()),
        ("stop", text(&format!("{:?}", out.stop))),
        ("seconds", num(out.seconds)),
    ]
}

fn cycles_json(out: &Certified) -> String {
    let items: Vec<String> = out
        .cycles
        .iter()
        .map(|c| {
            obj(&[
                ("index", c.index.to_string()),
                ("components", c.components.to_string()),
                ("peak_start", num(c.peak_start)),
                ("peak_working_end", num(c.peak_working_end)),
                ("q_before", num(c.q_before)),
                ("q_after", num(c.q_after)),
                ("dq_exact", num(c.dq_exact)),
                ("dq_predicted", num(c.dq_predicted)),
                ("gap", num(c.gap)),
                ("gap_relative", num(c.gap_relative)),
                ("dq_audit", num(c.dq_audit)),
                ("ascending_steps", c.ascending_steps.to_string()),
                ("abs_flux", num(c.abs_flux)),
                ("kappa", opt(c.kappa)),
                ("reducible", opt(c.reducible)),
                ("stop", text(&format!("{:?}", c.stop))),
                ("seconds", num(c.seconds)),
            ])
        })
        .collect();
    arr(&items)
}

struct Config {
    name: String,
    wgridding: bool,
    beam: String,
    patch: Option<usize>,
    rule: MinorRule,
    threshold: f64,
    floor_tolerance: Option<f64>,
    max_major: usize,
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: clean_certified INPUTS OUTDIR [threshold]");
        std::process::exit(2);
    }
    let inputs = Path::new(&args[1]);
    let outdir = Path::new(&args[2]);
    let threshold: f64 = args.get(3).map_or(0.05, |t| t.parse().unwrap());
    std::fs::create_dir_all(outdir).unwrap();
    let wall = Instant::now();

    let uvw = read_f64(&inputs.join("uvw.f64"));
    let freq = read_f64(&inputs.join("freq.f64"));
    let raw = read_f64(&inputs.join("vis.c128"));
    let vis: Vec<Complex<f64>> = raw
        .chunks_exact(2)
        .map(|c| Complex::new(c[0], c[1]))
        .collect();
    let wgt = read_f64(&inputs.join("wgt.f64"));
    let nrow = uvw.len() / 3;
    let nchan = freq.len();
    let active = wgt.iter().filter(|&&w| w != 0.0).count();
    println!("inputs: {nrow} rows, {nchan} channels, {active} weighted visibilities");
    let cell = CELL_ARCSEC / 3600.0 * std::f64::consts::PI / 180.0;
    // WSClean's FITS orientation is the gridder's image with v and w
    // flipped, transposed (research/df1-wgridder.md, item 0).
    let base = Options {
        flip_v: true,
        flip_w: true,
        ..Options::default()
    };
    let make = |wgridding: bool| {
        WgridMeasurement::new(
            uvw.clone(),
            freq.clone(),
            vis.clone(),
            wgt.clone(),
            SIDE,
            cell,
            EPSILON,
            Options {
                do_wgridding: wgridding,
                ..base
            },
        )
        .unwrap()
    };
    let with_w = make(true);
    let without_w = make(false);

    let t = Instant::now();
    let (dirty, q0) = with_w.residual(&vec![0.0; SIDE * SIDE]).unwrap();
    let t_residual = t.elapsed().as_secs_f64();
    let t = Instant::now();
    let _ = with_w.gram_apply(&dirty).unwrap();
    let t_gram = t.elapsed().as_secs_f64();
    let t = Instant::now();
    let exact_w = with_w.psf().unwrap();
    let exact_nw = without_w.psf().unwrap();
    let t_psf = t.elapsed().as_secs_f64();
    let image_beam = psf_from_image(SIDE, &with_w.psf_image(SIDE).unwrap());
    let dirty_peak = dirty.iter().fold(0.0_f64, |a, r| a.max(r.abs()));
    println!(
        "Q0 {q0:.6e} Jy², dirty peak {dirty_peak:.6} Jy/beam, weight sum {:.6}; residual {t_residual:.2} s, Gram {t_gram:.2} s, two 1024² PSFs {t_psf:.2} s",
        with_w.weight_sum
    );
    println!(
        "beam: peak {:.12}, coherence {:.6}, outside ±16 {:.4}, ±64 {:.4}, ±128 {:.4}",
        exact_w.peak(),
        exact_w.coherence(),
        exact_w.outside_patch(16),
        exact_w.outside_patch(64),
        exact_w.outside_patch(128)
    );
    let mut beams: Vec<(String, Psf)> = vec![
        ("exact".into(), exact_w.clone()),
        ("exact-now".into(), exact_nw.clone()),
        ("image".into(), image_beam),
    ];
    for name in ["recorded", "nominres"] {
        let path = inputs.join(format!("wsclean-psf-{name}.f64"));
        if path.exists() {
            let img = read_f64(&path);
            beams.push((format!("wsclean-{name}"), psf_from_image(SIDE, &img)));
        }
    }
    let beam_json: Vec<String> = beams
        .iter()
        .map(|(name, b)| {
            obj(&[
                ("name", text(name)),
                ("peak", num(b.peak())),
                (
                    "f_vs_exact_full",
                    num(rang_core::clean_certified::truncation_bound(
                        &exact_w, b, None,
                    )),
                ),
            ])
        })
        .collect();

    // The misfit floor once, on the w-gridded operator.
    let (floor, _) = misfit_floor(&with_w, &dirty, CG_ITERATIONS, 1e-12).unwrap();
    println!(
        "Q_inf <= {:.6e} ({:.4e} of Q0), CG {} iterations, relative residual {:.3e}, {:.1} s",
        floor.q_floor,
        floor.q_floor / q0,
        floor.iterations,
        floor.relative_residual,
        floor.seconds
    );

    let mgain = MinorRule::MajorGain(MGAIN);
    let mut configs = vec![
        Config {
            name: "now-exact-mgain".into(),
            wgridding: false,
            beam: "exact-now".into(),
            patch: None,
            rule: mgain,
            threshold,
            floor_tolerance: None,
            max_major: 1000,
        },
        Config {
            name: "exact-mgain".into(),
            wgridding: true,
            beam: "exact".into(),
            patch: None,
            rule: mgain,
            threshold,
            floor_tolerance: None,
            max_major: 1000,
        },
        Config {
            name: "image-mgain".into(),
            wgridding: true,
            beam: "image".into(),
            patch: None,
            rule: mgain,
            threshold,
            floor_tolerance: None,
            max_major: 1000,
        },
    ];
    for name in ["wsclean-recorded", "wsclean-nominres"] {
        if beams.iter().any(|(b, _)| b == name) {
            configs.push(Config {
                name: format!("{name}-mgain"),
                wgridding: true,
                beam: name.into(),
                patch: None,
                rule: mgain,
                threshold,
                floor_tolerance: None,
                max_major: 1000,
            });
        }
    }
    for patch in [16, 64] {
        for rule in [MinorRule::Clark, MinorRule::Provable] {
            configs.push(Config {
                name: format!("patch{patch}-{}", rule.name()),
                wgridding: true,
                beam: "exact".into(),
                patch: Some(patch),
                rule,
                threshold,
                floor_tolerance: None,
                max_major: 3000,
            });
        }
    }
    configs.push(Config {
        name: "exact-mgain-floor".into(),
        wgridding: true,
        beam: "exact".into(),
        patch: None,
        rule: mgain,
        threshold: 0.0,
        floor_tolerance: Some(1e-3),
        max_major: 1000,
    });

    // A smoke run may cap every configuration's major cycles.
    if let Ok(cap) = std::env::var("CLEAN_CERTIFIED_MAX_MAJOR") {
        let cap: usize = cap.parse().unwrap();
        for config in &mut configs {
            config.max_major = config.max_major.min(cap);
        }
    }
    let mut runs = Vec::new();
    for config in &configs {
        let measurement = if config.wgridding {
            &with_w
        } else {
            &without_w
        };
        let exact = if config.wgridding {
            &exact_w
        } else {
            &exact_nw
        };
        let minor = &beams.iter().find(|(b, _)| *b == config.beam).unwrap().1;
        let settings = DriverSettings {
            gain: GAIN,
            threshold: config.threshold,
            max_components: MAX_COMPONENTS,
            max_major: config.max_major,
            max_minor: usize::MAX,
            patch: config.patch,
            rule: config.rule,
            floor_tolerance: config.floor_tolerance,
            audit: true,
            divergence_limit: 4.0,
        };
        let out = run(measurement, minor, exact, &settings, Some(floor.q_floor)).unwrap();
        let support = out.support();
        let erc = erc_certificate(exact, &support, ERC_MAX_K);
        let gaps: Vec<f64> = out.cycles.iter().map(|c| c.gap_relative).collect();
        let max_gap = gaps.iter().fold(0.0_f64, |a, g| a.max(g.abs()));
        println!(
            "{:<24} {:>6} comps, {:>4} cycles, stop {:?}, Q/Q0 {:.4e}, max |gap|/Q {:.3e}, ascending {}, f {:.4}, ERC k {} eta {:?} ({:.1} s), {:.1} s",
            config.name,
            out.steps.len(),
            out.cycles.len(),
            out.stop,
            out.q_final / out.q0,
            max_gap,
            out.ascending_steps(),
            out.f,
            erc.k,
            erc.eta,
            erc.seconds,
            out.seconds
        );
        write_npy(
            &outdir.join(format!("{}-model.npy", config.name)),
            &out.model,
            SIDE,
            SIDE,
        );
        write_npy(
            &outdir.join(format!("{}-residual.npy", config.name)),
            &out.residual,
            SIDE,
            SIDE,
        );
        let mut fields = vec![
            ("name", text(&config.name)),
            ("wgridding", config.wgridding.to_string()),
            ("beam", text(&config.beam)),
            (
                "patch",
                config.patch.map_or("null".into(), |p| p.to_string()),
            ),
            ("rule", text(&config.rule.name())),
            ("gain", num(GAIN)),
            ("threshold", num(config.threshold)),
            ("floor_tolerance", opt(config.floor_tolerance)),
            ("max_components", MAX_COMPONENTS.to_string()),
            ("max_major", config.max_major.to_string()),
            ("max_abs_gap_relative", num(max_gap)),
        ];
        fields.extend(summarise(&out, SIDE));
        fields.push((
            "erc",
            obj(&[
                ("k", erc.k.to_string()),
                ("eta", opt(erc.eta)),
                (
                    "worst_pixel",
                    erc.worst_pixel.map_or("null".into(), |p| p.to_string()),
                ),
                ("min_pivot", num(erc.min_pivot)),
                ("skipped", erc.skipped.to_string()),
                ("cost_multiply_adds", num(erc.cost)),
                ("seconds", num(erc.seconds)),
            ]),
        ));
        fields.push(("cycles", cycles_json(&out)));
        runs.push(obj(&fields));
    }

    let threads = std::thread::available_parallelism().map_or(0, |n| n.get());
    let json = obj(&[
        ("inputs", text(&inputs.display().to_string())),
        ("nrow", nrow.to_string()),
        ("nchan", nchan.to_string()),
        ("active_visibilities", active.to_string()),
        ("weight_sum", num(with_w.weight_sum)),
        ("side", SIDE.to_string()),
        ("cell_arcsec", num(CELL_ARCSEC)),
        ("epsilon", num(EPSILON)),
        (
            "orientation",
            text("gridder layout, flip_v and flip_w; transpose for WSClean FITS"),
        ),
        ("q0", num(q0)),
        ("dirty_peak", num(dirty_peak)),
        (
            "beam",
            obj(&[
                ("peak", num(exact_w.peak())),
                ("coherence", num(exact_w.coherence())),
                ("outside_16", num(exact_w.outside_patch(16))),
                ("outside_64", num(exact_w.outside_patch(64))),
                ("outside_128", num(exact_w.outside_patch(128))),
                (
                    "now_vs_w_max_abs_difference",
                    num(rang_core::clean_certified::truncation_bound(
                        &exact_w, &exact_nw, None,
                    )),
                ),
            ]),
        ),
        ("beams", arr(&beam_json)),
        (
            "floor",
            obj(&[
                ("q_floor", num(floor.q_floor)),
                ("q_floor_over_q0", num(floor.q_floor / q0)),
                ("iterations", floor.iterations.to_string()),
                ("relative_residual", num(floor.relative_residual)),
                ("seconds", num(floor.seconds)),
            ]),
        ),
        (
            "seconds",
            obj(&[
                ("residual_eval", num(t_residual)),
                ("gram_apply", num(t_gram)),
                ("two_psfs_1024", num(t_psf)),
                ("wall", num(wall.elapsed().as_secs_f64())),
            ]),
        ),
        ("threads", threads.to_string()),
        ("runs", arr(&runs)),
    ]);
    std::fs::write(outdir.join("clean-certified.json"), json + "\n").unwrap();
    println!("wall {:.1} s", wall.elapsed().as_secs_f64());
}
