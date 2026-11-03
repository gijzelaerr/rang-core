//! `gemclean`: a reference CLEAN imager for Measurement Sets with WSClean-like
//! flags (`research/gemclean.md`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! ```text
//! gemclean -name out -size 1024 1024 -scale 2asec -weight briggs 0 \
//!     -niter 100000 -gain 0.1 -mgain 0.8 -auto-threshold 3 obs.ms
//! ```
//!
//! Reads the MS with the core reader, forms Stokes I and WSClean's imaging
//! weights, images with the exact `wgridder` (w-gridding, f64), runs the
//! gemclean minor/major loop and writes `-dirty`, `-psf`, `-model`,
//! `-residual` and `-image` FITS files in WSClean's orientation, plus
//! `-report.json`.

use rang_core::clean_certified::{Complex, Measurement, misfit_floor};
use rang_core::gemclean::fits::{self, Card, Value, card};
use rang_core::gemclean::input::{self, Selection};
use rang_core::gemclean::json::{arr, num, obj, opt, text};
use rang_core::gemclean::kernels::{self, Level};
use rang_core::gemclean::measure::GridMeasurement;
use rang_core::gemclean::stale_bound::{BoundKind, StaleBound, StopBound};
use rang_core::gemclean::{self, Beam, CycleStop, Settings};
use rang_core::gridder_gram::{GramMeasurement, GramOperator, WExpansion};
use rang_core::weights::WeightClass;
use rang_core::wgridder::{Options, Real};

#[cfg(all(target_os = "linux", target_pointer_width = "64"))]
#[global_allocator]
static ALLOCATOR: rang_core::gemclean::host::HugePageAlloc =
    rang_core::gemclean::host::HugePageAlloc;
use std::path::{Path, PathBuf};
use std::time::Instant;

const USAGE: &str = "usage: gemclean [options] <ms>

  -name <prefix>            output prefix (default gemclean)
  -size <width> <height>    image size in pixels (square, even)
  -scale <angle>            pixel size: 8asec, 1.5amin, 0.002deg, 500mas (plain number: degrees)
  -weight <mode> [robust]   natural | uniform | briggs <robust> (default uniform)
  -niter <n>                maximum number of components (default 0: dirty image only)
  -gain <g>                 loop gain (default 0.1)
  -mgain <g>                end every minor cycle at (1 - g) of its first peak, as WSClean's -mgain
                            (without it: the measured rule below, with g = 0.95 for the first cycle)
  -mgain-misfit <f>         end it instead when a fraction f of the misfit has gone (with the forcing rule)
  -stale-rule <rho>         end it at rho times the pointwise error measured by the last major cycle,
                            per unit of flux cleaned (default 1; the first cycle uses -mgain as g);
                            wins over -mgain as a rule, whatever the order
  -stop-rule <rule>         certified: end a cycle at the proved rule, kappa |r_p| <= the bound on
                            the beam error at the pick (research/stop-rule-theorem.md); wins over
                            the other rules. The default is the rules above
  -stop-rule-kappa <k>      kappa of -stop-rule certified (default 0.5; descent needs k < 1 - gain/2)
  -stop-rule-samples <n>    0: the bound on Chebyshev nodes, a supremum in eta on paper (default);
                            n > 0: n uniform samples of eta, cheaper and only measured
  -stop-rule-bound <kind>   envelope (default) or radial, the cheaper and looser form
  -minor-to-threshold       never hand back before the threshold
  -nmiter <n>               maximum number of major cycles (default 20)
  -threshold <Jy>           absolute stopping threshold (alias -abs-threshold)
  -auto-threshold <sigma>   stopping threshold in robust sigma (1.4826 MAD) of the residual
  -patch <pixels>           half-width of the beam patch subtracted per step (default 64)
  -theta <t>                forcing parameter of the major-cycle rule (default 0.5)
  -drift <d>                resync when |r_p - r~_p| > d |r~_p| (default 0.1)
  -tau-min <t>              resync when the weak-greedy certificate falls below t (default 0.5)
  -resync-every <k>         resync after k components (default 2000)
  -data-column <name>       default CORRECTED_DATA if present, else DATA
  -field <id>               field id (default 0)
  -j <threads>              worker threads (default: all cores)
  -wgridder-accuracy <eps>  gridder accuracy (default 1e-6, double precision)
  -no-wgridding             disable the w-term
  -single                   grid in single precision (default double)
  -gram-operator S,THETA    major cycles without visibilities: the w-node Toeplitz
                            operator of research/gridder-theory.md, S stencil nodes
                            at phase step THETA; prototype, off by default; the final
                            residual is still one exact pass through the gridder
  -no-plan-reuse            replan every gridder call (same images, for comparison)
  -beam-no-w                the 2n beam without the w-term (the major cycle keeps it)
  -floor-iterations <n>     estimate Q_inf by n conjugate-gradient iterations (default 0: off)
  -audit                    recompute every exact peak by brute force and report the largest error
  -simd <level>             cap the kernels at scalar | avx2 | avx512
  -bitpix <32|64>           FITS sample format (default 32)
  -tile <pixels>            tile side of the argmax (default 64)
  -eager-tiles              rescan every tile a patch touches (same picks, for comparison)
  -no-restore               do not write the restored image";

struct Args {
    ms: PathBuf,
    name: String,
    size: usize,
    scale: f64,
    weight: WeightClass,
    niter: usize,
    gain: f64,
    mgain: f64,
    mgain_misfit: f64,
    cycle_stop: CycleStop,
    stop_samples: usize,
    stop_bound: BoundKind,
    nmiter: usize,
    threshold: f64,
    auto_threshold: Option<f64>,
    patch: usize,
    theta: f64,
    drift: f64,
    tau_min: f64,
    resync_every: usize,
    data_column: Option<String>,
    field: i32,
    threads: Option<usize>,
    epsilon: f64,
    wgridding: bool,
    floor_iterations: usize,
    audit: bool,
    simd: Option<Level>,
    bitpix: i32,
    restore: bool,
    tile: usize,
    single: bool,
    gram_operator: Option<(usize, f64)>,
    plan_reuse: bool,
    beam_no_w: bool,
    lazy_bounds: bool,
}

/// An angle with WSClean's units, in radians (plain numbers are degrees).
fn parse_angle(s: &str) -> Result<f64, String> {
    let units = [
        ("mas", 1.0 / 3_600_000.0),
        ("masec", 1.0 / 3_600_000.0),
        ("asec", 1.0 / 3600.0),
        ("arcsec", 1.0 / 3600.0),
        ("amin", 1.0 / 60.0),
        ("arcmin", 1.0 / 60.0),
        ("deg", 1.0),
    ];
    let mut best: Option<(&str, f64)> = None;
    for (suffix, factor) in units {
        if s.ends_with(suffix) && best.is_none_or(|(b, _)| suffix.len() > b.len()) {
            best = Some((suffix, factor));
        }
    }
    let (number, factor) = match best {
        Some((suffix, factor)) => (&s[..s.len() - suffix.len()], factor),
        None => (s, 1.0),
    };
    let v: f64 = number
        .trim()
        .parse()
        .map_err(|_| format!("cannot read the angle {s:?}"))?;
    Ok((v * factor).to_radians())
}

fn parse_args(raw: &[String]) -> Result<Args, String> {
    let mut a = Args {
        ms: PathBuf::new(),
        name: "gemclean".into(),
        size: 0,
        scale: 0.0,
        weight: WeightClass::Uniform,
        niter: 0,
        gain: 0.1,
        mgain: 0.95,
        mgain_misfit: 0.8,
        cycle_stop: CycleStop::MeasuredStale { rho: 1.0, g: 0.95 },
        stop_samples: 0,
        stop_bound: BoundKind::Envelope,
        nmiter: 20,
        threshold: 0.0,
        auto_threshold: None,
        patch: 64,
        theta: 0.5,
        drift: 0.1,
        tau_min: 0.5,
        resync_every: 2000,
        data_column: None,
        field: 0,
        threads: None,
        epsilon: 1e-6,
        wgridding: true,
        floor_iterations: 0,
        audit: false,
        simd: None,
        bitpix: -32,
        restore: true,
        tile: 64,
        single: false,
        gram_operator: None,
        plan_reuse: true,
        beam_no_w: false,
        lazy_bounds: true,
    };
    let mut i = 0;
    let mut positional = Vec::new();
    let (mut mgain_given, mut misfit_given, mut to_threshold) = (false, false, false);
    let (mut certified, mut kappa) = (false, 0.5);
    let mut stale_rho: Option<f64> = None;
    let value = |i: &mut usize| -> Result<String, String> {
        *i += 1;
        raw.get(*i)
            .cloned()
            .ok_or_else(|| format!("{} needs a value", raw[*i - 1]))
    };
    fn number<T: std::str::FromStr>(flag: &str, s: String) -> Result<T, String> {
        s.parse().map_err(|_| format!("{flag}: cannot read {s:?}"))
    }
    while i < raw.len() {
        let flag = raw[i].as_str();
        match flag {
            "-h" | "-help" | "--help" => return Err(USAGE.into()),
            "-name" => a.name = value(&mut i)?,
            "-size" => {
                let w: usize = number(flag, value(&mut i)?)?;
                let h: usize = number(flag, value(&mut i)?)?;
                if w != h {
                    return Err("gemclean images square fields: -size W H needs W = H".into());
                }
                a.size = w;
            }
            "-scale" => a.scale = parse_angle(&value(&mut i)?)?,
            "-weight" => {
                a.weight = match value(&mut i)?.as_str() {
                    "natural" => WeightClass::Natural,
                    "uniform" => WeightClass::Uniform,
                    "briggs" => WeightClass::Briggs(number(flag, value(&mut i)?)?),
                    other => return Err(format!("-weight: unknown mode {other}")),
                }
            }
            "-niter" => a.niter = number(flag, value(&mut i)?)?,
            "-gain" => a.gain = number(flag, value(&mut i)?)?,
            "-mgain" => {
                a.mgain = number(flag, value(&mut i)?)?;
                mgain_given = true;
            }
            "-mgain-misfit" => {
                a.mgain_misfit = number(flag, value(&mut i)?)?;
                misfit_given = true;
            }
            "-stale-rule" => stale_rho = Some(number(flag, value(&mut i)?)?),
            "-minor-to-threshold" => to_threshold = true,
            "-stop-rule" => match value(&mut i)?.as_str() {
                "certified" => certified = true,
                other => return Err(format!("-stop-rule: unknown rule {other}")),
            },
            "-stop-rule-kappa" => kappa = number(flag, value(&mut i)?)?,
            "-stop-rule-samples" => a.stop_samples = number(flag, value(&mut i)?)?,
            "-stop-rule-bound" => {
                a.stop_bound = match value(&mut i)?.as_str() {
                    "envelope" => BoundKind::Envelope,
                    "radial" => BoundKind::Radial,
                    other => return Err(format!("-stop-rule-bound: unknown kind {other}")),
                }
            }
            "-nmiter" => a.nmiter = number(flag, value(&mut i)?)?,
            "-threshold" | "-abs-threshold" => a.threshold = number(flag, value(&mut i)?)?,
            "-auto-threshold" => a.auto_threshold = Some(number(flag, value(&mut i)?)?),
            "-patch" => a.patch = number(flag, value(&mut i)?)?,
            "-theta" => a.theta = number(flag, value(&mut i)?)?,
            "-drift" => a.drift = number(flag, value(&mut i)?)?,
            "-tau-min" => a.tau_min = number(flag, value(&mut i)?)?,
            "-resync-every" => a.resync_every = number(flag, value(&mut i)?)?,
            "-data-column" => a.data_column = Some(value(&mut i)?),
            "-field" => a.field = number(flag, value(&mut i)?)?,
            "-j" => a.threads = Some(number(flag, value(&mut i)?)?),
            "-wgridder-accuracy" => a.epsilon = number(flag, value(&mut i)?)?,
            "-no-wgridding" => a.wgridding = false,
            "-floor-iterations" => a.floor_iterations = number(flag, value(&mut i)?)?,
            "-audit" => a.audit = true,
            "-simd" => {
                a.simd = Some(match value(&mut i)?.as_str() {
                    "scalar" => Level::Scalar,
                    "avx2" => Level::Avx2,
                    "avx512" => Level::Avx512,
                    other => return Err(format!("-simd: unknown level {other}")),
                })
            }
            "-bitpix" => {
                a.bitpix = match value(&mut i)?.as_str() {
                    "32" | "-32" => -32,
                    "64" | "-64" => -64,
                    other => return Err(format!("-bitpix: {other} is not 32 or 64")),
                }
            }
            "-no-restore" => a.restore = false,
            "-tile" => a.tile = number(flag, value(&mut i)?)?,
            "-eager-tiles" => a.lazy_bounds = false,
            "-single" => a.single = true,
            "-gram-operator" => {
                let v = value(&mut i)?;
                let (s, t) = v.split_once(',').ok_or("-gram-operator takes S,THETA")?;
                a.gram_operator =
                    Some((number(flag, s.to_string())?, number(flag, t.to_string())?));
            }
            "-no-plan-reuse" => a.plan_reuse = false,
            "-beam-no-w" => a.beam_no_w = true,
            s if s.starts_with('-') && s.len() > 1 => {
                return Err(format!("unknown option {s}\n\n{USAGE}"));
            }
            _ => positional.push(raw[i].clone()),
        }
        i += 1;
    }
    // The rule does not depend on the order of the flags.
    a.cycle_stop = if certified {
        CycleStop::Certified { kappa }
    } else if to_threshold {
        CycleStop::Threshold
    } else if misfit_given {
        CycleStop::MisfitFraction
    } else if let Some(rho) = stale_rho {
        CycleStop::MeasuredStale { rho, g: a.mgain }
    } else if mgain_given {
        CycleStop::PeakFraction(a.mgain)
    } else {
        CycleStop::MeasuredStale {
            rho: 1.0,
            g: a.mgain,
        }
    };
    match positional.as_slice() {
        [ms] => a.ms = PathBuf::from(ms),
        _ => return Err(format!("exactly one Measurement Set is needed\n\n{USAGE}")),
    }
    if a.size < 2 || !a.size.is_multiple_of(2) {
        return Err("-size must be an even number of pixels".into());
    }
    if a.scale.partial_cmp(&0.0) != Some(std::cmp::Ordering::Greater) {
        return Err("-scale must be positive".into());
    }
    Ok(a)
}

fn write_image(
    path: &Path,
    n: usize,
    grid: &[f64],
    bitpix: i32,
    base: &[Card],
    extra: &[Card],
) -> Result<(), String> {
    let mut cards = base.to_vec();
    cards.extend_from_slice(extra);
    fits::write(path, n, n, &fits::gridder_to_fits(n, grid), bitpix, &cards)
}

/// The beam, the fitted restoring beam and the CLEAN run.
struct Cleaned {
    psf2n: Vec<f64>,
    beam: Beam,
    restoring: gemclean::RestoringBeam,
    outcome: gemclean::Outcome,
    floor_json: String,
    q_floor: Option<f64>,
    t_psf: f64,
    t_beam: f64,
}

/// The gridder-precision-dependent part of the run.
fn deconvolve<T: Real + Send + Sync>(
    args: &Args,
    uvw: Vec<f64>,
    freq: &[f64],
    vis: Vec<Complex<f64>>,
    wgt: Vec<f64>,
    opts: Options,
) -> Result<Cleaned, String> {
    let n = args.size;
    let gram_operator = match args.gram_operator {
        Some((stencil, theta)) => {
            let t = Instant::now();
            let sum: f64 = wgt.iter().sum();
            let normalised: Vec<f64> = wgt.iter().map(|w| w / sum).collect();
            let ridge = 1e-3 * (args.epsilon * args.epsilon).max(1e-14);
            let expansion = WExpansion::new(stencil, theta, ridge)?;
            let op = GramOperator::<T>::new(
                &Options {
                    nx: n,
                    ny: n,
                    pixsize_x: args.scale,
                    pixsize_y: args.scale,
                    epsilon: args.epsilon,
                    ..opts
                },
                &uvw,
                freq,
                &normalised,
                &expansion,
                args.epsilon,
            )?;
            println!(
                "gram operator: {} nodes, stencil {}, theta {}, w {:.1}-{:.1}, n-1 range {:.3e}, expansion error {:.2e}, Lebesgue {:.2}, cube {:.2} GB, {:.1} s (grid {:.1} s, FFT {:.1} s)",
                op.stats.planes,
                op.stats.stencil,
                op.stats.theta,
                op.stats.wmin,
                op.stats.wmax,
                op.stats.x_range,
                op.stats.sup_error,
                op.stats.lebesgue,
                op.stats.cube_bytes as f64 / 1e9,
                t.elapsed().as_secs_f64(),
                op.stats.setup_grid_seconds,
                op.stats.setup_fft_seconds
            );
            Some(op)
        }
        None => None,
    };
    // The bound of the certified rule reads the same uvw and weights.
    let certified = matches!(args.cycle_stop, CycleStop::Certified { .. });
    if certified && (args.beam_no_w || gram_operator.is_some() || !args.wgridding) {
        return Err("-stop-rule certified needs the default beam and gridder".into());
    }
    let keep = certified.then(|| (uvw.clone(), wgt.clone()));
    let measurement: GridMeasurement<T> = GridMeasurement::new(
        uvw,
        freq.to_vec(),
        vis,
        wgt,
        n,
        args.scale,
        args.epsilon,
        opts,
    )?;
    let measurement = if args.plan_reuse {
        measurement
    } else {
        measurement.without_plan_reuse()
    };
    let t = Instant::now();
    // With the operator and -beam-no-w the PSF needs no gridding pass of its own.
    let psf2n = match (&gram_operator, args.beam_no_w) {
        (Some(op), true) => op.psf_no_w.clone(),
        _ => measurement.psf_image_with(2 * n, args.wgridding && !args.beam_no_w)?,
    };
    let t_psf = t.elapsed().as_secs_f64();
    let t = Instant::now();
    let beam = Beam::from_double(n, &psf2n, args.patch)?;
    let t_beam = t.elapsed().as_secs_f64();
    let restoring = gemclean::fit_restoring_beam(n, &psf2n);
    let scale_deg = args.scale.to_degrees();
    println!(
        "beam: peak {:.12}, patch ±{}, f {:.4e} outside the patch; restoring beam {:.3}\" × {:.3}\" PA {:.2}° ({} main-lobe pixels); PSF {:.2} s, FFT {:.2} s",
        beam.peak,
        beam.patch,
        beam.f,
        restoring.major * scale_deg * 3600.0,
        restoring.minor * scale_deg * 3600.0,
        restoring.pa.to_degrees(),
        restoring.pixels,
        t_psf,
        t_beam
    );
    let mut floor_json = "null".to_string();
    let mut q_floor = None;
    if args.floor_iterations > 0 {
        let (dirty, _) = measurement.residual(&vec![0.0; n * n])?;
        let (floor, _) = misfit_floor(&measurement, &dirty, args.floor_iterations, 1e-12)?;
        println!(
            "Q_inf <= {:.6e} after {} CG iterations ({:.1} s)",
            floor.q_floor, floor.iterations, floor.seconds
        );
        q_floor = Some(floor.q_floor);
        floor_json = obj(&[
            ("q_floor", num(floor.q_floor)),
            ("iterations", floor.iterations.to_string()),
            ("relative_residual", num(floor.relative_residual)),
            ("seconds", num(floor.seconds)),
        ]);
    }
    let settings = Settings {
        gain: args.gain,
        cycle_stop: args.cycle_stop,
        major_fraction: args.mgain_misfit,
        threshold: args.threshold,
        auto_threshold: args.auto_threshold,
        max_components: args.niter,
        max_major: args.nmiter,
        theta: args.theta,
        drift: args.drift,
        tau_min: args.tau_min,
        resync_every: args.resync_every,
        audit: args.audit,
        level: args.simd.map(|l| l.min(kernels::level())),
        tile: args.tile,
        lazy_bounds: args.lazy_bounds,
    };
    let stop_bound = match keep {
        Some((uvw, wgt)) => {
            let sum: f64 = wgt.iter().sum();
            let normalised: Vec<f64> = wgt.iter().map(|w| w / sum).collect();
            let table = StaleBound::compute(
                n,
                args.scale,
                &opts,
                &uvw,
                freq,
                &normalised,
                &psf2n,
                args.epsilon,
                args.stop_samples,
            )?;
            println!(
                "stop bound: {} gridder calls, {:.1} s; largest |E| {:.3e}; first samples below {:.2e} from the moment bound; w mean {:.1} rms {:.1} max {:.1}",
                table.sampling.calls(),
                table.seconds,
                table.delta(),
                table.sampling.h0,
                table.moments.m1,
                table.moments.m2.sqrt(),
                table.moments.max
            );
            Some(StopBound::new(&table, args.stop_bound)?)
        }
        None => None,
    };
    let outcome = match gram_operator {
        None => {
            gemclean::run_with_bound(&measurement, &beam, &settings, q_floor, stop_bound.as_ref())?
        }
        Some(op) => {
            let (dirty, q0) = measurement.residual(&vec![0.0; n * n])?;
            let gram = GramMeasurement::new(op, dirty, q0);
            let mut outcome = gemclean::run(&gram, &beam, &settings, q_floor)?;
            // The score of the run comes from the gridder, not from the operator.
            let t = Instant::now();
            let (exact, q_exact) = measurement.residual(&outcome.model)?;
            let gap = exact
                .iter()
                .zip(&outcome.residual)
                .map(|(a, b)| (a - b).abs())
                .fold(0.0, f64::max);
            println!(
                "gram operator: last residual against the gridder, L-inf {:.3e}; Q {:.10e} operator, {:.10e} gridder; exact pass {:.2} s; major cycles were {:.2} s",
                gap,
                outcome.q_final,
                q_exact,
                t.elapsed().as_secs_f64(),
                outcome.timings.major
            );
            outcome.residual = exact;
            outcome.q_final = q_exact;
            outcome
        }
    };
    Ok(Cleaned {
        psf2n,
        beam,
        restoring,
        outcome,
        floor_json,
        q_floor,
        t_psf,
        t_beam,
    })
}

fn run() -> Result<(), String> {
    let wall = Instant::now();
    let raw: Vec<String> = std::env::args().skip(1).collect();
    let args = parse_args(&raw)?;
    if let Some(t) = args.threads {
        rayon::ThreadPoolBuilder::new()
            .num_threads(t)
            .build_global()
            .map_err(|e| e.to_string())?;
    }
    let n = args.size;
    let column = match &args.data_column {
        Some(c) => c.clone(),
        None => {
            let main = rang_core::ms::Table::open(&args.ms).map_err(|e| e.to_string())?;
            if main.column("CORRECTED_DATA").is_ok() {
                "CORRECTED_DATA".into()
            } else {
                "DATA".into()
            }
        }
    };
    let t = Instant::now();
    let selection = Selection {
        data_column: column.clone(),
        field: args.field,
        ..Selection::default()
    };
    let data = input::read_ms(&args.ms, &selection)?;
    let t_read = t.elapsed().as_secs_f64();
    let t = Instant::now();
    let weights = input::gridding_weights(&data, args.weight, n, args.scale)?;
    let t_weights = t.elapsed().as_secs_f64();
    println!(
        "{}: {} of {} rows selected (field {}, {column}), {} channels {:.4}-{:.4} MHz, {} visibilities weighted, weight sum {:.6} ({:.2} s read, {:.2} s weights)",
        args.ms.display(),
        data.rows(),
        data.rows_total,
        args.field,
        data.freq.len(),
        data.freq.first().copied().unwrap_or(0.0) / 1e6,
        data.freq.last().copied().unwrap_or(0.0) / 1e6,
        weights.count,
        weights.total,
        t_read,
        t_weights
    );
    // Keep the rows that carry weight.
    let nchan = data.freq.len();
    let mut uvw = Vec::new();
    let mut vis = Vec::new();
    let mut wgt = Vec::new();
    for row in 0..data.rows() {
        let w = &weights.weights[row * nchan..(row + 1) * nchan];
        if w.iter().any(|&x| x != 0.0) {
            uvw.extend_from_slice(&data.uvw[3 * row..3 * row + 3]);
            vis.extend_from_slice(&data.vis[row * nchan..(row + 1) * nchan]);
            wgt.extend_from_slice(w);
        }
    }
    let kept_rows = uvw.len() / 3;
    let freq = data.freq.clone();
    let phase_dir = data.phase_dir;
    drop(data);
    let opts = Options {
        flip_v: true,
        flip_w: true,
        do_wgridding: args.wgridding,
        ..Options::default()
    };
    let cleaned = if args.single {
        deconvolve::<f32>(&args, uvw, &freq, vis, wgt, opts)?
    } else {
        deconvolve::<f64>(&args, uvw, &freq, vis, wgt, opts)?
    };
    let Cleaned {
        psf2n,
        beam,
        restoring,
        outcome,
        floor_json,
        q_floor,
        t_psf,
        t_beam,
    } = cleaned;
    let scale_deg = args.scale.to_degrees();
    let tq = outcome.tau_quantiles();
    println!(
        "{} components, {} major cycles, {} resyncs, stop {:?}; Q/Q0 {:.4e}; tau min {:.3} median {:.3}; minor {:.2} s (corrections {:.3} s), resync {:.2} s, major {:.2} s",
        outcome.steps.len(),
        outcome.cycles.len(),
        outcome.resyncs.total(),
        outcome.stop,
        outcome.q_final / outcome.q0,
        tq.map_or(f64::NAN, |t| t.0),
        tq.map_or(f64::NAN, |t| t.3),
        outcome.timings.minor,
        outcome.timings.correction,
        outcome.timings.resync,
        outcome.timings.major
    );

    let t = Instant::now();
    let mut base = fits::wcs_cards(phase_dir.0, phase_dir.1, n, args.scale, &freq);
    base.extend([
        card(
            "BMAJ",
            Value::Float(restoring.major * scale_deg),
            "fitted restoring beam (deg)",
        ),
        card("BMIN", Value::Float(restoring.minor * scale_deg), ""),
        card("BPA", Value::Float(restoring.pa.to_degrees()), ""),
        card(
            "WSCNVIS",
            Value::Float(weights.count as f64),
            "visibilities with nonzero weight",
        ),
        card(
            "WSCIMGWG",
            Value::Float(weights.total),
            "sum of the gridding weights",
        ),
        card("WSCVWSUM", Value::Float(weights.visibility_weight_sum), ""),
        card(
            "WSCNITER",
            Value::Float(outcome.steps.len() as f64),
            "components",
        ),
        card(
            "WSCMAJOR",
            Value::Float(outcome.cycles.len() as f64),
            "major cycles",
        ),
        card("ORIGIN", Value::Str("gemclean (rang-core)".into()), ""),
    ]);
    let jy_pixel = [card("BUNIT", Value::Str("JY/PIXEL".into()), "")];
    let prefix = &args.name;
    let path = |kind: &str| PathBuf::from(format!("{prefix}-{kind}.fits"));
    write_image(&path("dirty"), n, &outcome.dirty, args.bitpix, &base, &[])?;
    let mut psf = vec![0.0; n * n];
    for i in 0..n {
        for j in 0..n {
            psf[i * n + j] = psf2n[(i + n / 2) * 2 * n + j + n / 2];
        }
    }
    write_image(&path("psf"), n, &psf, args.bitpix, &base, &[])?;
    let mut model_cards: Vec<Card> = base
        .iter()
        .filter(|(k, _, _)| k != "BUNIT")
        .cloned()
        .collect();
    model_cards.extend_from_slice(&jy_pixel);
    write_image(
        &path("model"),
        n,
        &outcome.model,
        args.bitpix,
        &model_cards,
        &[],
    )?;
    write_image(
        &path("residual"),
        n,
        &outcome.residual,
        args.bitpix,
        &base,
        &[],
    )?;
    let t_restore = Instant::now();
    if args.restore {
        let image = gemclean::restore(n, &outcome.model, &outcome.residual, &restoring);
        write_image(&path("image"), n, &image, args.bitpix, &base, &[])?;
    }
    let t_restore = t_restore.elapsed().as_secs_f64();
    let t_write = t.elapsed().as_secs_f64() - t_restore;

    let threads = rayon::current_num_threads();
    let argv: Vec<String> = raw.iter().map(|s| text(s)).collect();
    let report = obj(&[
        ("tool", text("gemclean")),
        ("version", text(env!("CARGO_PKG_VERSION"))),
        ("argv", arr(&argv)),
        ("ms", text(&args.ms.display().to_string())),
        ("data_column", text(&column)),
        ("field", args.field.to_string()),
        (
            "rows_total",
            data_rows_total(&args.ms).map_or("null".into(), |r| r.to_string()),
        ),
        ("rows_gridded", kept_rows.to_string()),
        ("channels", nchan.to_string()),
        ("visibilities_weighted", weights.count.to_string()),
        ("weight_sum", num(weights.total)),
        ("weight_grid_padded", weights.padded.to_string()),
        ("size", n.to_string()),
        ("scale_arcsec", num(args.scale.to_degrees() * 3600.0)),
        ("wgridding", args.wgridding.to_string()),
        ("gridder_single", args.single.to_string()),
        ("wgridder_accuracy", num(args.epsilon)),
        ("phase_dir_rad", arr(&[num(phase_dir.0), num(phase_dir.1)])),
        (
            "settings",
            obj(&[
                ("gain", num(args.gain)),
                ("mgain", num(args.mgain)),
                ("cycle_stop", text(&format!("{:?}", args.cycle_stop))),
                ("niter", args.niter.to_string()),
                ("nmiter", args.nmiter.to_string()),
                ("threshold", num(args.threshold)),
                ("auto_threshold", opt(args.auto_threshold)),
                ("patch", args.patch.to_string()),
                ("theta", num(args.theta)),
                ("drift", num(args.drift)),
                ("tau_min", num(args.tau_min)),
                ("resync_every", args.resync_every.to_string()),
                ("audit", args.audit.to_string()),
            ]),
        ),
        (
            "beam",
            obj(&[
                ("peak", num(beam.peak)),
                ("f_outside_patch", num(beam.f)),
                ("bmaj_deg", num(restoring.major * scale_deg)),
                ("bmin_deg", num(restoring.minor * scale_deg)),
                ("bpa_deg", num(restoring.pa.to_degrees())),
                ("main_lobe_pixels", restoring.pixels.to_string()),
            ]),
        ),
        ("floor", floor_json),
        ("run", outcome.to_json(q_floor)),
        (
            "seconds",
            obj(&[
                ("read", num(t_read)),
                ("weights", num(t_weights)),
                ("psf_2n", num(t_psf)),
                ("beam_fft", num(t_beam)),
                ("clean", num(outcome.timings.total)),
                ("restore", num(t_restore)),
                ("write", num(t_write)),
                ("wall", num(wall.elapsed().as_secs_f64())),
            ]),
        ),
        ("threads", threads.to_string()),
        ("simd_detected", text(kernels::detected().name())),
        (
            "peak_memory_bytes",
            gemclean::peak_memory_bytes().map_or("null".into(), |b| b.to_string()),
        ),
    ]);
    std::fs::write(format!("{prefix}-report.json"), report + "\n").map_err(|e| e.to_string())?;
    println!("wall {:.2} s", wall.elapsed().as_secs_f64());
    Ok(())
}

fn data_rows_total(ms: &Path) -> Option<u64> {
    rang_core::ms::Table::open(ms).ok().map(|t| t.nrows)
}

fn main() {
    rang_core::wgridder::set_default_plane_group(rang_core::wgridder::PLANE_GROUP);
    if let Err(e) = run() {
        eprintln!("gemclean: {e}");
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn angles_and_flags() {
        let asec = std::f64::consts::PI / 180.0 / 3600.0;
        assert!((parse_angle("8asec").unwrap() - 8.0 * asec).abs() < 1e-18);
        assert!((parse_angle("1.5amin").unwrap() - 90.0 * asec).abs() < 1e-16);
        assert!((parse_angle("500mas").unwrap() - 0.5 * asec).abs() < 1e-18);
        assert!((parse_angle("0.01").unwrap() - 36.0 * asec).abs() < 1e-16);
        let raw: Vec<String> = "-size 64 64 -scale 2asec -weight briggs -0.5 -niter 10 x.ms"
            .split(' ')
            .map(String::from)
            .collect();
        let a = parse_args(&raw).unwrap();
        assert_eq!(a.size, 64);
        assert_eq!(a.weight, WeightClass::Briggs(-0.5));
        assert_eq!(a.niter, 10);
        for (line, want) in [
            (
                "-size 64 64 -scale 2asec x.ms",
                CycleStop::MeasuredStale { rho: 1.0, g: 0.95 },
            ),
            (
                "-size 64 64 -scale 2asec -mgain 0.8 x.ms",
                CycleStop::PeakFraction(0.8),
            ),
            (
                "-size 64 64 -scale 2asec -stop-rule certified -mgain 0.8 x.ms",
                CycleStop::Certified { kappa: 0.5 },
            ),
            (
                "-size 64 64 -scale 2asec -stop-rule-kappa 0.9 -stop-rule certified x.ms",
                CycleStop::Certified { kappa: 0.9 },
            ),
            (
                "-size 64 64 -scale 2asec -stale-rule 2 -mgain 0.8 x.ms",
                CycleStop::MeasuredStale { rho: 2.0, g: 0.8 },
            ),
            (
                "-size 64 64 -scale 2asec -mgain 0.8 -stale-rule 2 x.ms",
                CycleStop::MeasuredStale { rho: 2.0, g: 0.8 },
            ),
            (
                "-size 64 64 -scale 2asec -mgain-misfit 0.5 -mgain 0.8 x.ms",
                CycleStop::MisfitFraction,
            ),
        ] {
            let raw: Vec<String> = line.split(' ').map(String::from).collect();
            assert_eq!(parse_args(&raw).unwrap().cycle_stop, want, "{line}");
        }
        let bad: Vec<String> = "-size 64 32 -scale 2asec x.ms"
            .split(' ')
            .map(String::from)
            .collect();
        assert!(parse_args(&bad).is_err());
    }
}
