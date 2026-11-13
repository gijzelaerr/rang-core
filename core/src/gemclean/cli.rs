// SPDX-License-Identifier: GPL-3.0-or-later
//! The command line of `gemclean`, a reference CLEAN imager for Measurement
//! Sets with WSClean-like flags (`research/gemclean.md`). One code for both
//! front ends (task G8, `research/g8-wheel.md`): the source build's binary
//! (`src/bin/gemclean.rs`) and the wheel's console script through the
//! extension (`rang._core.gemclean_main`).
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

use crate::clean_certified::{Complex, Measurement, misfit_floor};
use crate::gemclean::fits::{self, Card, Value, card};
use crate::gemclean::input::{self, Selection};
use crate::gemclean::joined::{run_joined, run_joined_masked, run_joined_pols};
use crate::gemclean::json::{arr, num, obj, opt, text};
use crate::gemclean::kernels::{self, Level};
use crate::gemclean::mask::{self, AutoMask, Masking};
use crate::gemclean::measure::GridMeasurement;
use crate::gemclean::memory::{self, bytes_of};
use crate::gemclean::multiscale::{self, MultiscaleSettings};
use crate::gemclean::predict;
use crate::gemclean::spectral::{self, PolynomialFit};
use crate::gemclean::stale_bound::{BoundKind, StaleBound, StopBound};
use crate::gemclean::stokes::{self, Pol};
use crate::gemclean::{self, Beam, CycleStop, Settings};
use crate::gridder_gram::{GramMeasurement, GramOperator, WExpansion};
use crate::weights::{UvTapers, WeightClass};
use crate::wgridder::{Options, Real};

use std::path::{Path, PathBuf};
use std::time::Instant;

const USAGE: &str = "usage: gemclean [options] <ms>
       gemclean -version

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
  -stale-floor <f>          also end a later cycle at f of its first peak, under the measured rule
                            (default 0.01; 0: no floor; research/stale-floor.md)
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
  -scans <list>             only the rows of these scans, comma-separated (rang's own;
                            also the rows the model column gets; research/w6-imaging-inputs.md)
  -unit-weights             every correlation weighs 1 in place of WEIGHT_SPECTRUM or WEIGHT,
                            flags still applied (rang's own; not -weight uniform)
  -j <threads>              worker threads (default: all cores)
  -wgridder-accuracy <eps>  gridder accuracy (default 1e-4; research/g7-defaults.md)
  -no-wgridding             disable the w-term
  -single                   grid in single precision (the default when the accuracy is 1e-5 or
                            coarser, so 1e-4 by default; research/g7-defaults.md)
  -double                   grid in double precision (the default for an accuracy finer than
                            1e-5; -wgridder-accuracy 1e-6 alone gives the form before G7)
  -gram-operator S,THETA    major cycles without visibilities: the w-node Toeplitz
                            operator of research/gridder-theory.md, S stencil nodes
                            at phase step THETA; prototype, off by default; the final
                            residual is still one exact pass through the gridder
  -no-plan-reuse            replan every gridder call (same images, for comparison)
  -beam-no-w                the 2n beam without the w-term (the major cycle keeps it)
  -beam-band                resyncs use the beam's spectrum only as far as the longest baseline and
                            the w-term reach; what is left out is logged
  -floor-iterations <n>     estimate Q_inf by n conjugate-gradient iterations (default 0: off)
  -audit                    recompute every exact peak by brute force and report the largest error
  -simd <level>             cap the kernels at scalar | avx2 | avx512
  -bitpix <32|64>           FITS sample format (default 32)
  -tile <pixels>            tile side of the argmax (default 64)
  -eager-tiles              rescan every tile a patch touches (same picks, for comparison)
  -no-restore               do not write the restored image
  -memory-report            print the heap held per phase and the main buffers' sizes
                            (always in -report.json)

Model column (research/g6-predict.md; WSClean's options):
  -update-model-required    after imaging, predict the model images just written into the
                            model column of the selected rows (the default)
  -no-update-model-required do not write the Measurement Set
  -predict                  no imaging: predict the existing <name>-model.fits (with
                            -channels-out n, <name>-0000-model.fits ...) into the model column
  -model-column <name>      the column written (default MODEL_DATA; added if missing); never
                            DATA, nor the column being imaged

Channels (research/g3-spectral.md; WSClean's options):
  -channels-out <n>         image n output channels, <name>-0000-<kind>.fits and the
                            weighted MFS images <name>-MFS-<kind>.fits (default 1)
  -join-channels            deconvolve the output channels together: peaks on the
                            weighted sum, a component in every channel
  -fit-spectral-pol <n>     fit an n-term polynomial in nu/nu_ref - 1 to every
                            component's channel values (needs -join-channels)
  -channel-range <s> <e>    image the channels s to e - 1 (ascending frequency)
  -average-channels <n>     average n adjacent channels before imaging (rang's own:
                            Stokes I weighted means, the weights summed)
  -mf-weighting             one weight grid for all output channels (the default
                            with -join-channels)
  -no-mf-weighting          weights per output channel (the default without it)

Polarisations (research/g9-stokes.md; WSClean's options, linear feeds):
  -pol <list>               I, Q, U, V, XX, YY in any combination (default I), as WSClean
                            parses it (iquv, xx,yy); several write <name>[-0000]-<pol>-<kind>.fits
                            and one <name>[-0000]-psf.fits from the first polarisation
  -join-polarizations       deconvolve the polarisations together: peaks on their
                            normalised sum (WSClean 3.7's default loop), a component in each

Multiscale (research/g5-multiscale.md; WSClean's options and defaults):
  -multiscale               clean on several scales (radler's multiscale algorithm with
                            its sub-minor loop); takes -mgain, the measured rule or
                            -minor-to-threshold
  -multiscale-scales <list> scales in pixels, comma-separated (default: 0, then 4, 8, 16, ...
                            times the theoretic beam, below half the image)
  -multiscale-max-scales <n> at most n automatic scales (default 0: all that fit)
  -multiscale-scale-bias <b> bias towards larger scales, lower is stronger (default 0.6)
  -multiscale-shape <shape> tapered-quadratic (default) or gaussian
  -multiscale-gain <g>      a sub-minor loop takes its scale's peak down by g (default 0.2)

Selection and masks (research/g4-masks.md; WSClean's options):
  -taper-gaussian <angle>   Gaussian taper of the weights, beam size (plain number: asec)
  -taper-tukey <lambda>     Tukey transition below -maxuv-l
  -taper-inner-tukey <l>    Tukey transition above -minuv-l
  -taper-edge <lambda>      zero the weights within lambda of the uv grid's edge
  -taper-edge-tukey <l>     Tukey transition inside the edge
  -minuv-l / -maxuv-l <l>   uv distance range in wavelengths (on the weight grid's cells)
  -minuvw-m / -maxuvw-m <m> baseline |uvw| range in metres (rows)
  -fits-mask <file>         clean only where the FITS image (same size, one plane) is nonzero
  -auto-mask <sigma>        radler's automatic mask: clean to sigma times the noise, then
                            on inside the mask of what was found, to the final threshold;
                            takes -mgain or -minor-to-threshold
  -abs-auto-mask <Jy>       the same with an absolute mask threshold
  -auto-mask-nmiter <n>     major cycles after the mask is made (default 2)
  -major-iteration-mode dual  radler's default (the only mode implemented)";

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
    beam_band: bool,
    lazy_bounds: bool,
    memory_report: bool,
    channels_out: usize,
    join_channels: bool,
    fit_spectral_pol: Option<usize>,
    channel_range: Option<(usize, usize)>,
    average_channels: usize,
    mf_weighting: Option<bool>,
    pols: Vec<Pol>,
    join_pols: bool,
    predict: bool,
    update_model: bool,
    model_column: String,
    scans: Vec<i32>,
    unit_weights: bool,
    multiscale: Option<MultiscaleSettings>,
    /// Task G4: tapers and uv cuts of the weights, the |uvw| row range,
    /// the masks (the FITS file is read in `run`).
    tapers: UvTapers,
    min_uvw_m: f64,
    max_uvw_m: f64,
    fits_mask: Option<PathBuf>,
    auto_mask: Option<AutoMask>,
    masking: Masking,
}

/// An angle with WSClean's units, in radians, a plain number in arcseconds
/// (`Angle::Parse(..., kArcseconds)`, as `-taper-gaussian` reads it).
fn parse_angle_asec(s: &str) -> Result<f64, String> {
    match s.trim().parse::<f64>() {
        Ok(v) => Ok((v / 3600.0).to_radians()),
        Err(_) => parse_angle(s),
    }
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
    // -single or -double; otherwise single precision for an accuracy of 1e-5
    // or coarser (task G7, research/g7-defaults.md).
    let mut precision: Option<bool> = None;
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
        cycle_stop: CycleStop::MeasuredStale {
            rho: 1.0,
            g: 0.95,
            floor: 0.01,
        },
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
        epsilon: 1e-4,
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
        beam_band: false,
        lazy_bounds: true,
        memory_report: false,
        channels_out: 1,
        join_channels: false,
        fit_spectral_pol: None,
        channel_range: None,
        average_channels: 1,
        mf_weighting: None,
        pols: vec![Pol::I],
        join_pols: false,
        predict: false,
        update_model: true,
        model_column: "MODEL_DATA".into(),
        scans: Vec::new(),
        unit_weights: false,
        multiscale: None,
        tapers: UvTapers::default(),
        min_uvw_m: 0.0,
        max_uvw_m: 0.0,
        fits_mask: None,
        auto_mask: None,
        masking: Masking::default(),
    };
    let (mut am_sigma, mut am_abs, mut am_nmiter) = (None::<f64>, None::<f64>, 2usize);
    let mut ms = MultiscaleSettings::default();
    let (mut ms_on, mut ms_option) = (false, None::<&str>);
    let mut i = 0;
    let mut positional = Vec::new();
    let (mut mgain_given, mut misfit_given, mut to_threshold) = (false, false, false);
    let (mut certified, mut kappa) = (false, 0.5);
    let mut stale_rho: Option<f64> = None;
    let mut floor = 0.01;
    let value = |i: &mut usize| -> Result<String, String> {
        *i += 1;
        raw.get(*i)
            .cloned()
            .ok_or_else(|| format!("{} needs a value", raw[*i - 1]))
    };
    fn number<T: std::str::FromStr>(flag: &str, s: String) -> Result<T, String> {
        s.parse().map_err(|_| format!("{flag}: cannot read {s:?}"))
    }
    // WSClean's `ParseDouble(..., 0.0, ...)`: finite and not below zero.
    fn non_negative(flag: &str, s: String) -> Result<f64, String> {
        let v: f64 = number(flag, s)?;
        if !v.is_finite() || v < 0.0 {
            return Err(format!(
                "Parameter value for {flag} was {v} but is not allowed to be smaller than 0"
            ));
        }
        Ok(v)
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
            "-stale-floor" => floor = number(flag, value(&mut i)?)?,
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
            // A NaN threshold never stops the minor cycle; finite and not below
            // zero, as -auto-mask (research/correctness-audit-2026-11-13.md).
            "-threshold" | "-abs-threshold" => a.threshold = non_negative(flag, value(&mut i)?)?,
            "-auto-threshold" => a.auto_threshold = Some(non_negative(flag, value(&mut i)?)?),
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
            "-memory-report" => a.memory_report = true,
            "-tile" => a.tile = number(flag, value(&mut i)?)?,
            "-eager-tiles" => a.lazy_bounds = false,
            "-single" => precision = Some(true),
            "-double" => precision = Some(false),
            "-gram-operator" => {
                let v = value(&mut i)?;
                let (s, t) = v.split_once(',').ok_or("-gram-operator takes S,THETA")?;
                a.gram_operator =
                    Some((number(flag, s.to_string())?, number(flag, t.to_string())?));
            }
            "-no-plan-reuse" => a.plan_reuse = false,
            "-beam-no-w" => a.beam_no_w = true,
            "-beam-band" => a.beam_band = true,
            "-channels-out" => a.channels_out = number(flag, value(&mut i)?)?,
            "-join-channels" => a.join_channels = true,
            "-fit-spectral-pol" => a.fit_spectral_pol = Some(number(flag, value(&mut i)?)?),
            "-channel-range" => {
                let start: usize = number(flag, value(&mut i)?)?;
                let end: usize = number(flag, value(&mut i)?)?;
                a.channel_range = Some((start, end));
            }
            "-average-channels" => a.average_channels = number(flag, value(&mut i)?)?,
            "-mf-weighting" => a.mf_weighting = Some(true),
            "-no-mf-weighting" => a.mf_weighting = Some(false),
            "-pol" => a.pols = stokes::parse_list(&value(&mut i)?)?,
            "-join-polarizations" => a.join_pols = true,
            "-link-polarizations" => {
                return Err(
                    "-link-polarizations is not implemented (research/g9-stokes.md)".into(),
                );
            }
            "-scans" => {
                let v = value(&mut i)?;
                a.scans = v
                    .split(',')
                    .map(|x| number::<i32>(flag, x.trim().to_string()))
                    .collect::<Result<_, _>>()?;
                if a.scans.is_empty() {
                    return Err("-scans needs at least one scan number".into());
                }
            }
            "-unit-weights" => a.unit_weights = true,
            "-predict" => a.predict = true,
            "-update-model-required" => a.update_model = true,
            "-no-update-model-required" => a.update_model = false,
            "-model-column" => a.model_column = value(&mut i)?,
            "-fit-spectral-log-pol" => {
                return Err("-fit-spectral-log-pol is not implemented (WSClean's non-linear                     power-law fitter is not ported; research/g3-spectral.md): use -fit-spectral-pol"
                    .into());
            }
            "-taper-gaussian" => a.tapers.gaussian_beam = parse_angle_asec(&value(&mut i)?)?,
            "-taper-tukey" => a.tapers.tukey = non_negative(flag, value(&mut i)?)?,
            "-taper-inner-tukey" => a.tapers.inner_tukey = non_negative(flag, value(&mut i)?)?,
            "-taper-edge" => a.tapers.edge = non_negative(flag, value(&mut i)?)?,
            "-taper-edge-tukey" => a.tapers.edge_tukey = non_negative(flag, value(&mut i)?)?,
            "-minuv-l" => a.tapers.min_uv_l = non_negative(flag, value(&mut i)?)?,
            "-maxuv-l" => a.tapers.max_uv_l = non_negative(flag, value(&mut i)?)?,
            "-minuvw-m" => a.min_uvw_m = non_negative(flag, value(&mut i)?)?,
            "-maxuvw-m" => a.max_uvw_m = non_negative(flag, value(&mut i)?)?,
            "-fits-mask" => a.fits_mask = Some(PathBuf::from(value(&mut i)?)),
            "-auto-mask" => am_sigma = Some(non_negative(flag, value(&mut i)?)?),
            "-abs-auto-mask" => am_abs = Some(non_negative(flag, value(&mut i)?)?),
            "-auto-mask-nmiter" => am_nmiter = number(flag, value(&mut i)?)?,
            "-major-iteration-mode" => {
                let v = value(&mut i)?;
                if v != "dual" {
                    return Err(format!(
                        "-major-iteration-mode {v} is not implemented: only radler's default, \
                         dual (research/g4-masks.md)"
                    ));
                }
            }
            "-local-rms"
            | "-local-rms-strength"
            | "-local-rms-window"
            | "-local-rms-image"
            | "-local-rms-method"
            | "-casa-mask"
            | "-horizon-mask"
            | "-clean-border" => {
                return Err(format!(
                    "{flag} is not implemented (research/g4-masks.md; CARACal's selfcal leaves \
                     -local-rms off by default)"
                ));
            }
            "-multiscale" => ms_on = true,
            "-multiscale-scales" => {
                let v = value(&mut i)?;
                ms.scales = v
                    .split(',')
                    .map(|s| number(flag, s.trim().to_string()))
                    .collect::<Result<Vec<f64>, String>>()?;
                ms_option = Some(flag);
            }
            "-multiscale-max-scales" => {
                ms.max_scales = number(flag, value(&mut i)?)?;
                ms_option = Some(flag);
            }
            "-multiscale-scale-bias" => {
                ms.scale_bias = number(flag, value(&mut i)?)?;
                ms_option = Some(flag);
            }
            "-multiscale-gain" => {
                ms.sub_minor_gain = number(flag, value(&mut i)?)?;
                ms_option = Some(flag);
            }
            "-multiscale-shape" => {
                ms.shape = match value(&mut i)?.as_str() {
                    "tapered-quadratic" => multiscale::Shape::TaperedQuadratic,
                    "gaussian" => multiscale::Shape::Gaussian,
                    other => return Err(format!("-multiscale-shape: unknown shape {other}")),
                };
                ms_option = Some(flag);
            }
            "-multiscale-convolution-padding" | "-no-multiscale-fast-subminor" => {
                return Err(format!(
                    "{flag} is not implemented: gemclean's shape convolutions are linear and \
                     its multiscale loop is the sub-minor one (research/g5-multiscale.md)"
                ));
            }
            "-deconvolution-channels"
            | "-squared-channel-joining"
            | "-channel-division-frequencies"
            | "-divide-channels-by-gaps" => {
                return Err(format!(
                    "{flag} is not implemented (research/g3-spectral.md, owner decision 4)"
                ));
            }
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
        CycleStop::MeasuredStale {
            rho,
            g: a.mgain,
            floor,
        }
    } else if mgain_given {
        CycleStop::PeakFraction(a.mgain)
    } else {
        CycleStop::MeasuredStale {
            rho: 1.0,
            g: a.mgain,
            floor,
        }
    };
    match positional.as_slice() {
        [ms] => a.ms = PathBuf::from(ms),
        _ => return Err(format!("exactly one Measurement Set is needed\n\n{USAGE}")),
    }
    // -predict takes the size and scale from the model images (and checks
    // them against -size and -scale when given).
    if !(a.predict && a.size == 0) && (a.size < 2 || !a.size.is_multiple_of(2)) {
        return Err("-size must be an even number of pixels".into());
    }
    if !(a.predict && a.scale == 0.0)
        && a.scale.partial_cmp(&0.0) != Some(std::cmp::Ordering::Greater)
    {
        return Err("-scale must be positive".into());
    }
    if a.channels_out == 0 || a.average_channels == 0 {
        return Err("-channels-out and -average-channels must be at least 1".into());
    }
    if let Some(terms) = a.fit_spectral_pol {
        if terms == 0 {
            return Err("-fit-spectral-pol needs at least one term".into());
        }
        if !a.join_channels || a.channels_out < 2 {
            return Err(
                "-fit-spectral-pol needs -join-channels and -channels-out of 2 or more".into(),
            );
        }
    }
    if a.channels_out > 1
        && (matches!(a.cycle_stop, CycleStop::Certified { .. })
            || a.gram_operator.is_some()
            || a.floor_iterations > 0
            || a.audit)
    {
        return Err(
            "-channels-out takes neither -stop-rule certified, -gram-operator,              -floor-iterations nor -audit (research/g3-spectral.md)"
                .into(),
        );
    }
    if a.pols != [Pol::I] && (a.predict || a.update_model) {
        return Err(
            "MODEL_DATA (-predict, and the model update after imaging) is written for Stokes I \
             only; a model of other polarisations is a follow-up of research/g9-stokes.md, not \
             implemented: add -no-update-model-required"
                .into(),
        );
    }
    if (a.predict || a.update_model)
        && let Some(e) = model_column_error(&a.model_column, a.data_column.as_deref())
    {
        return Err(e);
    }
    if a.join_pols && a.pols.len() < 2 {
        return Err(
            "Joined/linked polarization deconvolution requested, but only one polarization is \
             being imaged. Specify multiple polarizations, or do not request to join the \
             polarizations."
                .into(),
        );
    }
    if a.pols.len() > 1
        && (matches!(a.cycle_stop, CycleStop::Certified { .. })
            || a.gram_operator.is_some()
            || a.floor_iterations > 0
            || a.audit)
    {
        return Err(
            "several polarisations take neither -stop-rule certified, -gram-operator, \
             -floor-iterations nor -audit (research/g9-stokes.md)"
                .into(),
        );
    }
    if ms_on && a.pols.len() > 1 {
        return Err(
            "-multiscale with several polarisations is not implemented (a follow-up of \
             research/g9-stokes.md, section 12); image one polarisation at a time"
                .into(),
        );
    }
    if am_sigma.is_some() || am_abs.is_some() {
        if a.auto_threshold.zip(am_sigma).is_some_and(|(t, m)| t >= m) {
            return Err("The auto-masking threshold was smaller or equal to the \
                 auto-threshold. This does not make sense. Did you accidentally reverse \
                 the auto-mask and auto-threshold values?"
                .into());
        }
        gemclean::auto_mask_mgain(a.cycle_stop)?;
        a.auto_mask = Some(AutoMask {
            sigma: am_sigma,
            absolute: am_abs,
            nmiter: am_nmiter,
        });
    }
    if (a.auto_mask.is_some() || a.fits_mask.is_some())
        && (a.pols.len() > 1
            || a.gram_operator.is_some()
            || a.audit
            || matches!(a.cycle_stop, CycleStop::Certified { .. }))
    {
        return Err(
            "-fits-mask and -auto-mask take one polarisation and neither -gram-operator, -audit \
             nor -stop-rule certified (research/g4-masks.md)"
                .into(),
        );
    }
    if let Some(flag) = ms_option.filter(|_| !ms_on) {
        return Err(format!("{flag} needs -multiscale"));
    }
    if ms_on {
        if matches!(
            a.cycle_stop,
            CycleStop::Certified { .. } | CycleStop::MisfitFraction
        ) || a.gram_operator.is_some()
            || a.floor_iterations > 0
            || a.audit
        {
            return Err(
                "-multiscale takes neither -stop-rule certified, -mgain-misfit, -gram-operator, \
                 -floor-iterations nor -audit (research/g5-multiscale.md)"
                    .into(),
            );
        }
        let valid = ms.sub_minor_gain > 0.0 && ms.sub_minor_gain <= 1.0 && ms.scale_bias > 0.0;
        if !valid {
            return Err(
                "-multiscale-gain must be in (0, 1] and -multiscale-scale-bias positive".into(),
            );
        }
        a.multiscale = Some(ms);
    }
    a.single = precision.unwrap_or(a.epsilon >= 1e-5);
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
    /// The PSF on the `n × n` image, cropped from the `2n` PSF.
    psf: Vec<f64>,
    beam: Beam,
    restoring: gemclean::RestoringBeam,
    outcome: gemclean::Outcome,
    floor_json: String,
    q_floor: Option<f64>,
    t_psf: f64,
    t_beam: f64,
    /// The multiscale part of the report (`-multiscale` only).
    multiscale: Option<String>,
}

/// The gridder-precision-dependent part of the run.
fn deconvolve<T: Real + Send + Sync>(
    args: &Args,
    uvw: Vec<f64>,
    freq: &[f64],
    vis: Vec<Complex<f32>>,
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
    // WSClean's theoretic beam: the start of the restoring-beam fit, and the
    // multiscale scales.
    let theoretic_raw = multiscale::theoretic_beam(&uvw, freq, &wgt, n, args.scale);
    let fit_estimate =
        gemclean::beam_fit_estimate(theoretic_raw, args.scale, args.tapers.gaussian_beam);
    let theoretic = args
        .multiscale
        .as_ref()
        .and(theoretic_raw)
        .map(|b| b.max(args.tapers.gaussian_beam));
    // The plan of the image grid is made after the 2n PSF, which does not use it.
    let measurement: GridMeasurement<T> = GridMeasurement::from_single_unprepared(
        uvw,
        freq.to_vec(),
        vis,
        wgt,
        n,
        args.scale,
        args.epsilon,
        opts,
    )?;
    memory::mark("measurement");
    let t = Instant::now();
    // With the operator and -beam-no-w the PSF needs no gridding pass of its own.
    let psf2n = match (&gram_operator, args.beam_no_w) {
        (Some(op), true) => op.psf_no_w.clone(),
        _ => measurement.psf_image_with(2 * n, args.wgridding && !args.beam_no_w)?,
    };
    let t_psf = t.elapsed().as_secs_f64();
    memory::mark("psf 2n");
    let measurement = if args.plan_reuse {
        measurement.prepare()?
    } else {
        measurement.without_plan_reuse()
    };
    memory::mark("plan");
    let t = Instant::now();
    let columns = if args.beam_band {
        measurement.band_columns(2 * n)
    } else {
        n + 1
    };
    let beam = Beam::from_double_band(n, &psf2n, args.patch, columns)?;
    let t_beam = t.elapsed().as_secs_f64();
    let restoring = gemclean::fit_restoring_beam(n, &psf2n, fit_estimate);
    memory::mark("beam");
    let scale_deg = args.scale.to_degrees();
    println!(
        "beam: peak {:.12}, patch ±{}, f {:.4e} outside the patch; {} of {} spectrum columns, {:.2e} left out; restoring beam {:.3}\" × {:.3}\" PA {:.2}° ({} pixels fitted); PSF {:.2} s, FFT {:.2} s",
        beam.peak,
        beam.patch,
        beam.f,
        beam.columns().0,
        beam.columns().1,
        beam.dropped_rms(),
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
    // Nothing reads the 2n PSF from here on but the PSF image written at the end.
    let mut psf = vec![0.0; n * n];
    for i in 0..n {
        for j in 0..n {
            psf[i * n + j] = psf2n[(i + n / 2) * 2 * n + j + n / 2];
        }
    }
    let psf2n_bytes = bytes_of(&psf2n);
    drop(psf2n);
    let masking = args.masking.is_active().then_some(&args.masking);
    if let Some(ms) = &args.multiscale {
        let out = multiscale::run_multiscale_masked(
            &[(&measurement, &beam, &psf[..])],
            &[1.0],
            None,
            &settings,
            ms,
            theoretic.map_or(0.0, |b| b / args.scale),
            masking,
        )?;
        print_multiscale(&out, theoretic);
        report_masking(args, &[out.joined.auto.as_ref()], &[&out.joined.integrated])?;
        memory::mark("clean: end");
        memory::note("psf 2n image (freed before the run)", psf2n_bytes);
        memory::note("psf n x n crop", bytes_of(&psf));
        for (label, bytes) in measurement.memory().into_iter().chain(beam.memory()) {
            memory::note(label, bytes);
        }
        return Ok(Cleaned {
            psf,
            beam,
            restoring,
            multiscale: Some(out.to_json(ms, theoretic)),
            outcome: out.joined.integrated,
            floor_json,
            q_floor,
            t_psf,
            t_beam,
        });
    }
    let outcome = match gram_operator {
        None if masking.is_some() => {
            let (o, auto) = gemclean::run_masked(
                &measurement,
                &beam,
                &settings,
                q_floor,
                stop_bound.as_ref(),
                masking,
            )?;
            report_masking(args, &[auto.as_ref()], &[&o])?;
            o
        }
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
    memory::mark("clean: end");
    memory::note("psf 2n image (freed before the run)", psf2n_bytes);
    memory::note("psf n x n crop", bytes_of(&psf));
    for (label, bytes) in measurement.memory().into_iter().chain(beam.memory()) {
        memory::note(label, bytes);
    }
    let image = n * n * std::mem::size_of::<f64>();
    memory::note("one n x n f64 image", image);
    Ok(Cleaned {
        psf,
        beam,
        restoring,
        outcome,
        floor_json,
        q_floor,
        t_psf,
        t_beam,
        multiscale: None,
    })
}

/// The masks of a run (task G4): one log line per auto-masked major cycle
/// and `<name>-mask.json` (nothing without a mask).
fn report_masking(
    args: &Args,
    autos: &[Option<&mask::AutoState>],
    outcomes: &[&gemclean::Outcome],
) -> Result<(), String> {
    if !args.masking.is_active() {
        return Ok(());
    }
    // Picks outside the FITS mask (meaningful without the automatic mask,
    // whose phase 2 the FITS mask does not bind in multiscale).
    let fits_outside = args.masking.fits.as_ref().map(|m| {
        outcomes
            .iter()
            .flat_map(|o| o.steps.iter())
            .filter(|s| !m[s.pixel])
            .count()
    });
    let pixels = args
        .masking
        .fits
        .as_ref()
        .map(|m| m.iter().filter(|&&v| v).count());
    if let Some(p) = pixels {
        println!("fits mask: {p} pixels");
    }
    let mut runs = Vec::new();
    for a in autos.iter().flatten() {
        for c in &a.cycles {
            println!(
                "auto-mask: major iteration {}, sigma {:.6e} Jy, threshold {:.6e} Jy{}{}",
                c.index,
                c.sigma,
                c.threshold,
                if c.phase2 { ", in the mask" } else { "" },
                match c.continued {
                    Some(k) => format!(
                        "; continued in the mask at gain {:.4}, threshold {:.6e} Jy",
                        k.gain, k.threshold
                    ),
                    None => String::new(),
                }
            );
        }
        if let Some(i) = a.finishing {
            println!("auto-mask: threshold reached in major iteration {i}");
        }
        runs.push(a.to_json());
    }
    let json = obj(&[
        ("fits_mask_pixels", opt(pixels.map(|p| p as f64))),
        ("fits_outside_picks", opt(fits_outside.map(|p| p as f64))),
        (
            "picks",
            outcomes
                .iter()
                .map(|o| o.steps.len())
                .sum::<usize>()
                .to_string(),
        ),
        ("auto", arr(&runs)),
    ]);
    let path = format!("{}-mask.json", args.name);
    std::fs::write(&path, json + "\n").map_err(|e| format!("{path}: {e}"))
}

/// WSClean's theoretic beam and the multiscale summary.
fn print_multiscale(out: &multiscale::Multiscale, theoretic: Option<f64>) {
    println!(
        "multiscale: theoretic beam {:.4}\" ({:.4} pixels), {} scales, {} sub-minor loops, end {:?}",
        theoretic.map_or(f64::NAN, |b| b.to_degrees() * 3600.0),
        out.beam_pixels,
        out.scales.len(),
        out.sub_minor_loops,
        out.end
    );
    out.print_scales();
}

fn run(raw: &[String]) -> Result<(), String> {
    let wall = Instant::now();
    if raw.iter().any(|a| a == "-version" || a == "--version") {
        println!("gemclean {}", env!("CARGO_PKG_VERSION"));
        return Ok(());
    }
    let mut args = parse_args(raw)?;
    if let Some(p) = &args.fits_mask {
        args.masking.fits = Some(mask::read_fits_mask(p, args.size)?);
    }
    args.masking.auto = args.auto_mask;
    if let Some(t) = args.threads {
        let global = rayon::ThreadPoolBuilder::new()
            .num_threads(t)
            .build_global();
        if global.is_err() {
            // The global pool exists already (a second run in one process,
            // through the extension): this run gets a pool of its own.
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(t)
                .build()
                .map_err(|e| e.to_string())?;
            return pool.install(|| run_parsed(args, raw, wall));
        }
    }
    run_parsed(args, raw, wall)
}

fn run_parsed(args: Args, raw: &[String], wall: Instant) -> Result<(), String> {
    if args.predict {
        return predict_only(&args, raw, wall);
    }
    let n = args.size;
    let column = match &args.data_column {
        Some(c) => c.clone(),
        None => {
            let main = crate::ms::Table::open(&args.ms).map_err(|e| e.to_string())?;
            if main.column("CORRECTED_DATA").is_ok() {
                "CORRECTED_DATA".into()
            } else {
                "DATA".into()
            }
        }
    };
    // The input column may only now be known (CORRECTED_DATA when the MS has
    // it): refuse before anything is read or written (E5-02).
    if args.update_model
        && let Some(e) = model_column_error(&args.model_column, Some(&column))
    {
        return Err(e);
    }
    let t = Instant::now();
    let selection = Selection {
        data_column: column.clone(),
        field: args.field,
        polarization: args.pols[0],
        scans: args.scans.clone(),
        unit_weights: args.unit_weights,
        min_uvw_m: args.min_uvw_m,
        max_uvw_m: args.max_uvw_m,
        ..Selection::default()
    };
    if args.pols.len() > 1 {
        return run_polarizations(&args, raw, &selection, &column, wall);
    }
    let mut data = input::read_ms(&args.ms, &selection)?;
    // Channel selection and averaging come before the weights, as WSClean's
    // -channel-range does; without them the data are as read.
    let spectral = args.channel_range.is_some() || args.average_channels > 1;
    let mut widths = Vec::new();
    if spectral || args.channels_out > 1 {
        widths = input::channel_widths(&args.ms, &selection)?;
        if widths.len() != data.freq.len() {
            return Err("CHAN_WIDTH and CHAN_FREQ differ in length".into());
        }
    }
    if spectral {
        (data, widths) = select_and_average(data, widths, &args)?;
    }
    if args.channels_out > 1 {
        let t_read = t.elapsed().as_secs_f64();
        return run_channels(&args, raw, data, &widths, &column, wall, t_read);
    }
    let t_read = t.elapsed().as_secs_f64();
    memory::mark("read");
    memory::note("read: Stokes I visibilities", bytes_of(&data.vis));
    memory::note("read: Stokes I weights", bytes_of(&data.weight));
    memory::note(
        "read: uvw and row flags",
        bytes_of(&data.uvw) + bytes_of(&data.flag_row),
    );
    let t = Instant::now();
    let mut weights =
        input::gridding_weights_tapered(&data, args.weight, n, args.scale, &args.tapers)?;
    let t_weights = t.elapsed().as_secs_f64();
    memory::mark("weights");
    memory::note("weights: gridding weights", bytes_of(&weights.weights));
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
    // Keep the rows that carry weight, in place: the rows kept move down over
    // the rows dropped, so no second copy of the visibilities is held, and the
    // gridding weights are not kept beside the copy the measurement takes.
    let nchan = data.freq.len();
    let rows = data.rows();
    let phase_dir = data.phase_dir;
    let input::StokesI {
        mut uvw,
        freq,
        mut vis,
        weight,
        flag_row,
        ..
    } = data;
    drop((weight, flag_row));
    let mut wgt = std::mem::take(&mut weights.weights);
    let mut kept_rows = 0;
    for row in 0..rows {
        let (a, b) = (row * nchan, (row + 1) * nchan);
        if wgt[a..b].iter().any(|&x| x != 0.0) {
            if kept_rows != row {
                uvw.copy_within(3 * row..3 * row + 3, 3 * kept_rows);
                vis.copy_within(a..b, kept_rows * nchan);
                wgt.copy_within(a..b, kept_rows * nchan);
            }
            kept_rows += 1;
        }
    }
    uvw.truncate(3 * kept_rows);
    vis.truncate(kept_rows * nchan);
    wgt.truncate(kept_rows * nchan);
    uvw.shrink_to_fit();
    vis.shrink_to_fit();
    wgt.shrink_to_fit();
    memory::mark("compact");
    memory::note("compact: visibilities", bytes_of(&vis));
    memory::note("compact: weights", bytes_of(&wgt));
    memory::note("compact: uvw", bytes_of(&uvw));
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
        psf,
        beam,
        restoring,
        outcome,
        floor_json,
        q_floor,
        t_psf,
        t_beam,
        multiscale: multiscale_json,
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
    if args.pols[0] != Pol::I {
        stokes::set_stokes_card(&mut base, args.pols[0]);
    }
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
    memory::mark("write");
    let model_json = update_model(&args)?;
    if args.update_model {
        memory::mark("model");
    }
    let phases = memory::phases();
    let buffers = memory::buffers();
    let gb = |b: usize| b as f64 / 1e9;
    if args.memory_report && memory::counting() {
        println!(
            "memory by phase (heap GB: held at the end, most during; RSS GB: at the end, peak so far; swap GB):"
        );
        for p in &phases {
            println!(
                "  {:<26} held {:>7.3}  most {:>7.3}  rss {:>7.3}  peak rss {:>7.3}  swap {:>6.3}",
                p.label,
                gb(p.live),
                gb(p.peak),
                p.rss.map_or(f64::NAN, |b| b as f64 / 1e9),
                p.hwm.map_or(f64::NAN, |b| b as f64 / 1e9),
                p.swap.map_or(f64::NAN, |b| b as f64 / 1e9)
            );
        }
        println!("memory by buffer (GB):");
        for (label, bytes) in &buffers {
            println!("  {label:<44} {:>8.3}", gb(*bytes));
        }
    }
    let memory_json = if memory::counting() {
        obj(&[
            (
                "phases",
                arr(&phases
                    .iter()
                    .map(|p| {
                        obj(&[
                            ("label", text(&p.label)),
                            ("heap_end_bytes", p.live.to_string()),
                            ("heap_peak_bytes", p.peak.to_string()),
                            ("rss_bytes", p.rss.map_or("null".into(), |b| b.to_string())),
                            (
                                "swap_bytes",
                                p.swap.map_or("null".into(), |b| b.to_string()),
                            ),
                            (
                                "rss_peak_bytes",
                                p.hwm.map_or("null".into(), |b| b.to_string()),
                            ),
                        ])
                    })
                    .collect::<Vec<_>>()),
            ),
            (
                "buffers",
                arr(&buffers
                    .iter()
                    .map(|(l, b)| obj(&[("label", text(l)), ("bytes", b.to_string())]))
                    .collect::<Vec<_>>()),
            ),
        ])
    } else {
        "null".into()
    };

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
            "scans",
            if args.scans.is_empty() {
                "null".into()
            } else {
                arr(&args.scans.iter().map(|x| x.to_string()).collect::<Vec<_>>())
            },
        ),
        ("unit_weights", args.unit_weights.to_string()),
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
                ("fit_pixels", restoring.pixels.to_string()),
            ]),
        ),
        ("floor", floor_json),
        ("model_update", model_json),
        (
            "multiscale",
            multiscale_json.unwrap_or_else(|| "null".into()),
        ),
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
        ("memory", memory_json),
    ]);
    std::fs::write(format!("{prefix}-report.json"), report + "\n").map_err(|e| e.to_string())?;
    println!("wall {:.2} s", wall.elapsed().as_secs_f64());
    Ok(())
}

/// `-channel-range` (on the channels in ascending frequency), then
/// `-average-channels`; `widths` follow (summed when averaged).
fn select_and_average(
    data: input::StokesI,
    widths: Vec<f64>,
    args: &Args,
) -> Result<(input::StokesI, Vec<f64>), String> {
    let keep = spectral::channel_groups(&data.freq, args.channel_range, 1)?.remove(0);
    let widths: Vec<f64> = keep.iter().map(|&k| widths[k]).collect();
    let data = spectral::select_channels(data, &keep);
    let a = args.average_channels;
    let widths = widths.chunks(a).map(|c| c.iter().sum()).collect();
    Ok((spectral::average_channels(data, a), widths))
}

/// One output channel: its data, weights and header counters.
struct ChannelData {
    /// Input channels (indices into the read channels, ascending frequency).
    channels: Vec<usize>,
    freq: Vec<f64>,
    low: f64,
    high: f64,
    uvw: Vec<f64>,
    vis: Vec<Complex<f32>>,
    wgt: Vec<f64>,
    rows: usize,
    /// `WSCNVIS`, `WSCIMGWG`, `WSCVWSUM`.
    count: u64,
    total: f64,
    visibility_weight_sum: f64,
}

impl ChannelData {
    fn central(&self) -> f64 {
        0.5 * (self.low + self.high)
    }
}

/// Split `data` into the output channels, with MF weights (one weight grid
/// for all) or weights per output channel, and keep in each the rows with
/// weight there.
fn split_channels(
    data: input::StokesI,
    widths: &[f64],
    args: &Args,
    mf: bool,
) -> Result<Vec<ChannelData>, String> {
    let groups = spectral::channel_groups(&data.freq, None, args.channels_out)?;
    let nchan = data.freq.len();
    let rows = data.rows();
    let full = if mf {
        Some(input::gridding_weights_tapered(
            &data,
            args.weight,
            args.size,
            args.scale,
            &args.tapers,
        )?)
    } else {
        None
    };
    let mut out = Vec::with_capacity(groups.len());
    for (k, group) in groups.into_iter().enumerate() {
        let freq: Vec<f64> = group.iter().map(|&c| data.freq[c]).collect();
        let low = group
            .iter()
            .map(|&c| data.freq[c] - 0.5 * widths[c])
            .fold(f64::INFINITY, f64::min);
        let high = group
            .iter()
            .map(|&c| data.freq[c] + 0.5 * widths[c])
            .fold(f64::NEG_INFINITY, f64::max);
        let m = group.len();
        let mut vis = Vec::with_capacity(rows * m);
        let mut weight = Vec::with_capacity(rows * m);
        for row in 0..rows {
            for &c in &group {
                vis.push(data.vis[row * nchan + c]);
                weight.push(data.weight[row * nchan + c]);
            }
        }
        let mut wgt = match &full {
            Some(w) => {
                let mut g = Vec::with_capacity(rows * m);
                for row in 0..rows {
                    for &c in &group {
                        g.push(w.weights[row * nchan + c]);
                    }
                }
                g
            }
            None => {
                let sub = input::StokesI {
                    uvw: data.uvw.clone(),
                    freq: freq.clone(),
                    vis: Vec::new(),
                    weight: weight.clone(),
                    flag_row: data.flag_row.clone(),
                    phase_dir: data.phase_dir,
                    rows_total: data.rows_total,
                    correlations: data.correlations.clone(),
                    weight_spectrum: data.weight_spectrum,
                };
                input::gridding_weights_tapered(
                    &sub,
                    args.weight,
                    args.size,
                    args.scale,
                    &args.tapers,
                )?
                .weights
            }
        };
        // WSClean's counters over this channel's visibilities (flagged rows
        // carry zero gridding weight).
        let (mut count, mut total, mut vsum) = (0u64, 0.0, 0.0);
        for (g, w) in wgt.iter().zip(&weight) {
            if *g != 0.0 {
                count += 1;
                total += g;
                vsum += f64::from(*w);
            }
        }
        if total <= 0.0 {
            return Err(format!("output channel {k} has no weighted visibilities"));
        }
        drop(weight);
        let mut uvw = data.uvw.clone();
        let mut kept_rows = 0;
        for row in 0..rows {
            let (a, b) = (row * m, (row + 1) * m);
            if wgt[a..b].iter().any(|&x| x != 0.0) {
                if kept_rows != row {
                    uvw.copy_within(3 * row..3 * row + 3, 3 * kept_rows);
                    vis.copy_within(a..b, kept_rows * m);
                    wgt.copy_within(a..b, kept_rows * m);
                }
                kept_rows += 1;
            }
        }
        uvw.truncate(3 * kept_rows);
        vis.truncate(kept_rows * m);
        wgt.truncate(kept_rows * m);
        uvw.shrink_to_fit();
        vis.shrink_to_fit();
        wgt.shrink_to_fit();
        out.push(ChannelData {
            channels: group,
            freq,
            low,
            high,
            uvw,
            vis,
            wgt,
            rows: kept_rows,
            count,
            total,
            visibility_weight_sum: vsum,
        });
    }
    Ok(out)
}

/// The deconvolved output channels.
struct ChannelImages {
    psf: Vec<Vec<f64>>,
    restoring: Vec<gemclean::RestoringBeam>,
    /// The start of each channel's restoring-beam fit, pixels (WSClean's MFS
    /// fit starts from the smallest).
    fit_estimates: Vec<f64>,
    beam_peak: Vec<f64>,
    beam_f: Vec<f64>,
    dirty: Vec<Vec<f64>>,
    model: Vec<Vec<f64>>,
    residual: Vec<Vec<f64>>,
    /// The joined run (integrated), or one run per channel.
    joined: Option<gemclean::Outcome>,
    separate: Vec<gemclean::Outcome>,
    reference_frequency: Option<f64>,
    t_psf: f64,
    /// The multiscale part of the report (`-multiscale` only).
    multiscale: Option<String>,
}

fn deconvolve_channels<T: Real + Send + Sync>(
    args: &Args,
    chans: Vec<ChannelData>,
    weights: &[f64],
    central: &[f64],
    opts: Options,
) -> Result<ChannelImages, String> {
    let n = args.size;
    let t = Instant::now();
    let mut measurements: Vec<GridMeasurement<T>> = Vec::with_capacity(chans.len());
    let mut beams = Vec::with_capacity(chans.len());
    let mut restoring = Vec::with_capacity(chans.len());
    let mut psfs = Vec::with_capacity(chans.len());
    // WSClean's theoretic beam per channel: the start of its restoring-beam
    // fit; the multiscale scales use the smallest (`minTheoreticalBeamSize`).
    let theoretic_raw: Vec<Option<f64>> = chans
        .iter()
        .map(|c| multiscale::theoretic_beam(&c.uvw, &c.freq, &c.wgt, n, args.scale))
        .collect();
    let fit_estimates: Vec<f64> = theoretic_raw
        .iter()
        .map(|&b| gemclean::beam_fit_estimate(b, args.scale, args.tapers.gaussian_beam))
        .collect();
    let theoretic = args.multiscale.as_ref().and_then(|_| {
        theoretic_raw
            .iter()
            .flatten()
            .map(|b| b.max(args.tapers.gaussian_beam))
            .reduce(f64::min)
    });
    for (k, c) in chans.into_iter().enumerate() {
        let m: GridMeasurement<T> = GridMeasurement::from_single_unprepared(
            c.uvw,
            c.freq,
            c.vis,
            c.wgt,
            n,
            args.scale,
            args.epsilon,
            opts,
        )?;
        let psf2n = m.psf_image_with(2 * n, args.wgridding && !args.beam_no_w)?;
        let m = if args.plan_reuse {
            m.prepare()?
        } else {
            m.without_plan_reuse()
        }
        .releasing_grids();
        let columns = if args.beam_band {
            m.band_columns(2 * n)
        } else {
            n + 1
        };
        beams.push(Beam::from_double_band(n, &psf2n, args.patch, columns)?);
        restoring.push(gemclean::fit_restoring_beam(n, &psf2n, fit_estimates[k]));
        let mut psf = vec![0.0; n * n];
        for i in 0..n {
            for j in 0..n {
                psf[i * n + j] = psf2n[(i + n / 2) * 2 * n + j + n / 2];
            }
        }
        psfs.push(psf);
        measurements.push(m);
        memory::mark(&format!("channel {}: psf and beam", measurements.len() - 1));
    }
    let t_psf = t.elapsed().as_secs_f64();
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
    let beam_peak = beams.iter().map(|b| b.peak).collect();
    let beam_f = beams.iter().map(|b| b.f).collect();
    let masking = args.masking.is_active().then_some(&args.masking);
    if let Some(ms) = &args.multiscale {
        let beam_pixels = theoretic.map_or(0.0, |b| b / args.scale);
        let fit = args
            .fit_spectral_pol
            .filter(|_| args.join_channels)
            .map(|terms| PolynomialFit::new(terms, central.to_vec(), weights.to_vec()));
        let mut runs = Vec::new();
        if args.join_channels {
            let triples: Vec<(&GridMeasurement<T>, &Beam, &[f64])> = measurements
                .iter()
                .zip(&beams)
                .zip(&psfs)
                .map(|((m, b), p)| (m, b, &p[..]))
                .collect();
            runs.push(multiscale::run_multiscale_masked(
                &triples,
                weights,
                fit.as_ref(),
                &settings,
                ms,
                beam_pixels,
                masking,
            )?);
        } else {
            for ((m, b), p) in measurements.iter().zip(&beams).zip(&psfs) {
                runs.push(multiscale::run_multiscale_masked(
                    &[(m, b, &p[..])],
                    &[1.0],
                    None,
                    &settings,
                    ms,
                    beam_pixels,
                    masking,
                )?);
                memory::mark(&format!("channel {}: clean", runs.len() - 1));
            }
        }
        memory::mark("clean: end");
        for r in &runs {
            print_multiscale(r, theoretic);
        }
        report_masking(
            args,
            &runs
                .iter()
                .map(|r| r.joined.auto.as_ref())
                .collect::<Vec<_>>(),
            &runs
                .iter()
                .map(|r| &r.joined.integrated)
                .collect::<Vec<_>>(),
        )?;
        let json = arr(&runs
            .iter()
            .map(|r| r.to_json(ms, theoretic))
            .collect::<Vec<_>>());
        let (mut dirty, mut model, mut residual) = (Vec::new(), Vec::new(), Vec::new());
        let (mut joined, mut separate) = (None, Vec::new());
        for r in runs {
            let j = r.joined;
            dirty.extend(j.dirty);
            model.extend(j.model);
            residual.extend(j.residual);
            if args.join_channels {
                joined = Some(j.integrated);
            } else {
                separate.push(j.integrated);
            }
        }
        return Ok(ChannelImages {
            psf: psfs,
            restoring,
            fit_estimates,
            beam_peak,
            beam_f,
            dirty,
            model,
            residual,
            joined,
            separate,
            reference_frequency: fit.map(|f| f.reference),
            t_psf,
            multiscale: Some(json),
        });
    }
    if args.join_channels {
        let pairs: Vec<(&GridMeasurement<T>, &Beam)> = measurements.iter().zip(&beams).collect();
        let fit = args
            .fit_spectral_pol
            .map(|terms| PolynomialFit::new(terms, central.to_vec(), weights.to_vec()));
        let j = if masking.is_some() {
            run_joined_masked(&pairs, 1, weights, 1.0, fit.as_ref(), &settings, masking)?
        } else {
            run_joined(&pairs, weights, fit.as_ref(), &settings)?
        };
        report_masking(args, &[j.auto.as_ref()], &[&j.integrated])?;
        memory::mark("clean: end");
        Ok(ChannelImages {
            psf: psfs,
            restoring,
            fit_estimates,
            beam_peak,
            beam_f,
            dirty: j.dirty,
            model: j.model,
            residual: j.residual,
            joined: Some(j.integrated),
            separate: Vec::new(),
            reference_frequency: fit.map(|f| f.reference),
            t_psf,
            multiscale: None,
        })
    } else {
        let mut separate = Vec::with_capacity(measurements.len());
        let mut autos = Vec::new();
        for (m, b) in measurements.iter().zip(&beams) {
            if masking.is_some() {
                let (o, auto) = gemclean::run_masked(m, b, &settings, None, None, masking)?;
                separate.push(o);
                autos.push(auto);
            } else {
                separate.push(gemclean::run(m, b, &settings, None)?);
            }
            memory::mark(&format!("channel {}: clean", separate.len() - 1));
        }
        report_masking(
            args,
            &autos.iter().map(|a| a.as_ref()).collect::<Vec<_>>(),
            &separate.iter().collect::<Vec<_>>(),
        )?;
        Ok(ChannelImages {
            psf: psfs,
            restoring,
            fit_estimates,
            beam_peak,
            beam_f,
            dirty: separate.iter().map(|o| o.dirty.clone()).collect(),
            model: separate.iter().map(|o| o.model.clone()).collect(),
            residual: separate.iter().map(|o| o.residual.clone()).collect(),
            joined: None,
            separate,
            reference_frequency: None,
            t_psf,
            multiscale: None,
        })
    }
}

/// The weighted mean of `images` with `weights` (WSClean's `MakeMFSImage`).
fn weighted_mean(images: &[Vec<f64>], weights: &[f64]) -> Vec<f64> {
    let sum: f64 = weights.iter().sum();
    let mut out = vec![0.0; images[0].len()];
    for (img, &w) in images.iter().zip(weights) {
        for (o, v) in out.iter_mut().zip(img) {
            *o += v * w;
        }
    }
    for o in &mut out {
        *o /= sum;
    }
    out
}

/// An `n × n` PSF placed at the centre of a zero `2n × 2n` grid, for the
/// restoring-beam fit (whose main lobe lies well inside the crop).
fn embed_double(n: usize, psf: &[f64]) -> Vec<f64> {
    let mut out = vec![0.0; 4 * n * n];
    for i in 0..n {
        for j in 0..n {
            out[(i + n / 2) * 2 * n + j + n / 2] = psf[i * n + j];
        }
    }
    out
}

fn beam_cards(r: &gemclean::RestoringBeam, scale_deg: f64) -> Vec<Card> {
    vec![
        card(
            "BMAJ",
            Value::Float(r.major * scale_deg),
            "fitted restoring beam (deg)",
        ),
        card("BMIN", Value::Float(r.minor * scale_deg), ""),
        card("BPA", Value::Float(r.pa.to_degrees()), ""),
    ]
}

#[allow(clippy::too_many_arguments)]
fn write_set(
    prefix: &str,
    n: usize,
    bitpix: i32,
    base: &[Card],
    images: [&[f64]; 4],
    restoring: &gemclean::RestoringBeam,
    restore: bool,
) -> Result<(), String> {
    let path = |kind: &str| PathBuf::from(format!("{prefix}-{kind}.fits"));
    let [dirty, psf, model, residual] = images;
    write_image(&path("dirty"), n, dirty, bitpix, base, &[])?;
    write_image(&path("psf"), n, psf, bitpix, base, &[])?;
    let mut model_cards: Vec<Card> = base
        .iter()
        .filter(|(k, _, _)| k != "BUNIT")
        .cloned()
        .collect();
    model_cards.push(card("BUNIT", Value::Str("JY/PIXEL".into()), ""));
    write_image(&path("model"), n, model, bitpix, &model_cards, &[])?;
    write_image(&path("residual"), n, residual, bitpix, base, &[])?;
    if restore {
        let image = gemclean::restore(n, model, residual, restoring);
        write_image(&path("image"), n, &image, bitpix, base, &[])?;
    }
    Ok(())
}

/// An output channel's input channels, band edges, `WSCNVIS`, `WSCIMGWG`,
/// `WSCVWSUM` and rows gridded.
type ChannelMeta = (Vec<usize>, f64, f64, u64, f64, f64, usize);

/// More than one output channel: split, deconvolve (joined or one by one),
/// write each channel and the MFS images, as WSClean names them.
fn run_channels(
    args: &Args,
    raw: &[String],
    data: input::StokesI,
    widths: &[f64],
    column: &str,
    wall: Instant,
    t_read: f64,
) -> Result<(), String> {
    let n = args.size;
    let mf = args.mf_weighting.unwrap_or(args.join_channels);
    let phase_dir = data.phase_dir;
    let rows_read = data.rows();
    let nchan_read = data.freq.len();
    memory::mark("read");
    let t = Instant::now();
    let chans = split_channels(data, widths, args, mf)?;
    let t_weights = t.elapsed().as_secs_f64();
    memory::mark("weights");
    let weights: Vec<f64> = chans.iter().map(|c| c.total).collect();
    let central: Vec<f64> = chans.iter().map(ChannelData::central).collect();
    let meta: Vec<ChannelMeta> = chans
        .iter()
        .map(|c| {
            (
                c.channels.clone(),
                c.low,
                c.high,
                c.count,
                c.total,
                c.visibility_weight_sum,
                c.rows,
            )
        })
        .collect();
    println!(
        "{}: {} rows ({column}, field {}), {} channels into {} output channels, {} weighting{}, {:.2} s read, {:.2} s weights",
        args.ms.display(),
        rows_read,
        args.field,
        nchan_read,
        chans.len(),
        if mf { "MF" } else { "per-channel" },
        if args.join_channels { ", joined" } else { "" },
        t_read,
        t_weights
    );
    let opts = Options {
        flip_v: true,
        flip_w: true,
        do_wgridding: args.wgridding,
        ..Options::default()
    };
    let out = if args.single {
        deconvolve_channels::<f32>(args, chans, &weights, &central, opts)?
    } else {
        deconvolve_channels::<f64>(args, chans, &weights, &central, opts)?
    };
    let scale_deg = args.scale.to_degrees();
    let prefix = &args.name;
    let t = Instant::now();
    let components: Vec<usize> = match &out.joined {
        Some(j) => vec![j.steps.len(); meta.len()],
        None => out.separate.iter().map(|o| o.steps.len()).collect(),
    };
    let majors: Vec<usize> = match &out.joined {
        Some(j) => vec![j.cycles.len(); meta.len()],
        None => out.separate.iter().map(|o| o.cycles.len()).collect(),
    };
    for (k, (_, low, high, count, total, vsum, _)) in meta.iter().enumerate() {
        let mut base = fits::wcs_cards_band(phase_dir.0, phase_dir.1, n, args.scale, *low, *high);
        if args.pols[0] != Pol::I {
            stokes::set_stokes_card(&mut base, args.pols[0]);
        }
        base.extend(beam_cards(&out.restoring[k], scale_deg));
        base.extend([
            card(
                "WSCNVIS",
                Value::Float(*count as f64),
                "visibilities with nonzero weight",
            ),
            card(
                "WSCIMGWG",
                Value::Float(*total),
                "sum of the gridding weights",
            ),
            card("WSCVWSUM", Value::Float(*vsum), ""),
            card("WSCNITER", Value::Float(components[k] as f64), "components"),
            card("WSCMAJOR", Value::Float(majors[k] as f64), "major cycles"),
            card("ORIGIN", Value::Str("gemclean (rang-core)".into()), ""),
        ]);
        write_set(
            &format!("{prefix}-{k:04}"),
            n,
            args.bitpix,
            &base,
            [&out.dirty[k], &out.psf[k], &out.model[k], &out.residual[k]],
            &out.restoring[k],
            args.restore,
        )?;
    }
    // MFS: weighted means; the restoring beam fitted on the MFS PSF.
    let psf_mfs = weighted_mean(&out.psf, &weights);
    let mfs_estimate = out
        .fit_estimates
        .iter()
        .copied()
        .fold(f64::INFINITY, f64::min);
    let restoring_mfs = gemclean::fit_restoring_beam(n, &embed_double(n, &psf_mfs), mfs_estimate);
    let low = meta.iter().map(|m| m.1).fold(f64::INFINITY, f64::min);
    let high = meta.iter().map(|m| m.2).fold(f64::NEG_INFINITY, f64::max);
    let mut base = fits::wcs_cards_band(phase_dir.0, phase_dir.1, n, args.scale, low, high);
    if args.pols[0] != Pol::I {
        stokes::set_stokes_card(&mut base, args.pols[0]);
    }
    base.extend(beam_cards(&restoring_mfs, scale_deg));
    base.extend([
        card(
            "WSCNVIS",
            Value::Float(meta.iter().map(|m| m.3).sum::<u64>() as f64),
            "visibilities with nonzero weight",
        ),
        card(
            "WSCIMGWG",
            Value::Float(weights.iter().sum()),
            "sum of the gridding weights",
        ),
        card("WSCVWSUM", Value::Float(meta.iter().map(|m| m.5).sum()), ""),
        card(
            "WSCNITER",
            Value::Float(components.iter().sum::<usize>() as f64),
            "components",
        ),
        card(
            "WSCMAJOR",
            Value::Float(majors.iter().copied().max().unwrap_or(0) as f64),
            "major cycles",
        ),
        card("ORIGIN", Value::Str("gemclean (rang-core)".into()), ""),
    ]);
    let dirty_mfs = weighted_mean(&out.dirty, &weights);
    let model_mfs = weighted_mean(&out.model, &weights);
    let residual_mfs = weighted_mean(&out.residual, &weights);
    write_set(
        &format!("{prefix}-MFS"),
        n,
        args.bitpix,
        &base,
        [&dirty_mfs, &psf_mfs, &model_mfs, &residual_mfs],
        &restoring_mfs,
        args.restore,
    )?;
    let t_write = t.elapsed().as_secs_f64();
    memory::mark("write");
    let beam_json = |r: &gemclean::RestoringBeam| {
        obj(&[
            ("bmaj_deg", num(r.major * scale_deg)),
            ("bmin_deg", num(r.minor * scale_deg)),
            ("bpa_deg", num(r.pa.to_degrees())),
            ("fit_pixels", r.pixels.to_string()),
        ])
    };
    let channels_json: Vec<String> = meta
        .iter()
        .enumerate()
        .map(|(k, (input, low, high, count, total, _, rows))| {
            obj(&[
                ("index", k.to_string()),
                (
                    "input_channels",
                    arr(&input.iter().map(|c| c.to_string()).collect::<Vec<_>>()),
                ),
                ("band_low_hz", num(*low)),
                ("band_high_hz", num(*high)),
                ("central_hz", num(central[k])),
                ("weight_sum", num(*total)),
                ("visibilities_weighted", count.to_string()),
                ("rows_gridded", rows.to_string()),
                ("beam_peak", num(out.beam_peak[k])),
                ("f_outside_patch", num(out.beam_f[k])),
                ("restoring_beam", beam_json(&out.restoring[k])),
                (
                    "run",
                    out.separate
                        .get(k)
                        .map_or("null".into(), |o| o.to_json(None)),
                ),
            ])
        })
        .collect();
    if let Some(j) = &out.joined {
        println!(
            "joined: {} components, {} major cycles, {} resyncs, stop {:?}; Q/Q0 {:.4e}",
            j.steps.len(),
            j.cycles.len(),
            j.resyncs.total(),
            j.stop,
            j.q_final / j.q0
        );
    } else {
        for (k, o) in out.separate.iter().enumerate() {
            println!(
                "channel {k}: {} components, {} major cycles, stop {:?}; Q/Q0 {:.4e}",
                o.steps.len(),
                o.cycles.len(),
                o.stop,
                o.q_final / o.q0
            );
        }
    }
    let model_json = update_model(args)?;
    let argv: Vec<String> = raw.iter().map(|s| text(s)).collect();
    let report = obj(&[
        ("tool", text("gemclean")),
        ("version", text(env!("CARGO_PKG_VERSION"))),
        ("argv", arr(&argv)),
        ("ms", text(&args.ms.display().to_string())),
        ("data_column", text(column)),
        ("model_update", model_json),
        ("field", args.field.to_string()),
        (
            "scans",
            if args.scans.is_empty() {
                "null".into()
            } else {
                arr(&args.scans.iter().map(|x| x.to_string()).collect::<Vec<_>>())
            },
        ),
        ("unit_weights", args.unit_weights.to_string()),
        ("channels_read", nchan_read.to_string()),
        ("channels_out", meta.len().to_string()),
        ("join_channels", args.join_channels.to_string()),
        ("mf_weighting", mf.to_string()),
        (
            "fit_spectral_pol",
            args.fit_spectral_pol
                .map_or("null".into(), |t| t.to_string()),
        ),
        ("reference_frequency_hz", opt(out.reference_frequency)),
        ("average_channels", args.average_channels.to_string()),
        (
            "channel_range",
            args.channel_range
                .map_or("null".into(), |(a, b)| arr(&[a.to_string(), b.to_string()])),
        ),
        ("size", n.to_string()),
        ("scale_arcsec", num(args.scale.to_degrees() * 3600.0)),
        ("gridder_single", args.single.to_string()),
        ("wgridder_accuracy", num(args.epsilon)),
        ("phase_dir_rad", arr(&[num(phase_dir.0), num(phase_dir.1)])),
        ("channels", arr(&channels_json)),
        (
            "multiscale",
            out.multiscale.clone().unwrap_or_else(|| "null".into()),
        ),
        ("mfs_restoring_beam", beam_json(&restoring_mfs)),
        (
            "run",
            out.joined
                .as_ref()
                .map_or("null".into(), |j| j.to_json(None)),
        ),
        (
            "seconds",
            obj(&[
                ("read", num(t_read)),
                ("weights", num(t_weights)),
                ("psf_and_beams", num(out.t_psf)),
                ("write", num(t_write)),
                ("wall", num(wall.elapsed().as_secs_f64())),
            ]),
        ),
        ("threads", rayon::current_num_threads().to_string()),
        (
            "peak_memory_bytes",
            gemclean::peak_memory_bytes().map_or("null".into(), |b| b.to_string()),
        ),
    ]);
    std::fs::write(format!("{prefix}-report.json"), report + "\n").map_err(|e| e.to_string())?;
    println!("wall {:.2} s", wall.elapsed().as_secs_f64());
    Ok(())
}

// ---------------------------------------------------------------------------
// Several polarisations (task G9, research/g9-stokes.md).

/// One imaged output channel and polarisation: its rows with weight, the
/// gridding weights and WSClean's counters.
struct PolEntry {
    uvw: Vec<f64>,
    vis: Vec<Complex<f32>>,
    wgt: Vec<f64>,
    rows: usize,
    /// `WSCNVIS`, `WSCIMGWG`, `WSCVWSUM`.
    count: u64,
    total: f64,
    visibility_weight_sum: f64,
}

/// The weight sources and channel group (MF: usize::MAX) of an imaging-weight grid.
type WeightKey = (Vec<usize>, usize);

/// The images of a polarisation run, per entry (channel-major).
struct PolImages {
    psf: Vec<Vec<f64>>,
    restoring: Vec<gemclean::RestoringBeam>,
    /// The start of each channel's restoring-beam fit, pixels.
    fit_estimates: Vec<f64>,
    /// Per entry: the index of its beam, and whether it is the first
    /// polarisation's of its channel.
    shared_beam: Vec<bool>,
    dirty: Vec<Vec<f64>>,
    model: Vec<Vec<f64>>,
    residual: Vec<Vec<f64>>,
    /// Components and major cycles per entry.
    components: Vec<usize>,
    majors: Vec<usize>,
    runs_json: Vec<String>,
    reference_frequency: Option<f64>,
    t_psf: f64,
}

fn clean_settings(args: &Args) -> Settings {
    Settings {
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
    }
}

#[allow(clippy::too_many_arguments)]
fn deconvolve_pols<T: Real + Send + Sync>(
    args: &Args,
    entries: Vec<PolEntry>,
    freqs: &[Vec<f64>],
    central: &[f64],
    opts: Options,
) -> Result<PolImages, String> {
    let n = args.size;
    let npol = args.pols.len();
    let kout = freqs.len();
    let t = Instant::now();
    let totals: Vec<f64> = entries.iter().map(|e| e.total).collect();
    let mut measurements: Vec<GridMeasurement<T>> = Vec::with_capacity(entries.len());
    let mut beams: Vec<Beam> = Vec::new();
    let mut beam_of = Vec::with_capacity(entries.len());
    let mut shared_beam = Vec::with_capacity(entries.len());
    let mut restoring = Vec::with_capacity(kout);
    let mut fit_estimates = Vec::with_capacity(kout);
    let mut psfs = Vec::with_capacity(kout);
    // The rows and gridding weights of the channel's earlier polarisations,
    // with their beams.
    let mut earlier: Vec<(Vec<f64>, Vec<f64>, usize)> = Vec::new();
    for (e, c) in entries.into_iter().enumerate() {
        let (k, p) = (e / npol, e % npol);
        if p == 0 {
            earlier.clear();
        }
        // A beam is shared with an earlier polarisation's only where the
        // gridding weights and rows are the same, bit for bit: GeMClean's
        // exact values need each measurement's own PSF.
        let same = earlier
            .iter()
            .find(|(u, w, _)| *u == c.uvw && *w == c.wgt)
            .map(|x| x.2);
        if npol > 1 && same.is_none() && p + 1 < npol {
            earlier.push((c.uvw.clone(), c.wgt.clone(), beams.len()));
        }
        if p == 0 {
            let b = multiscale::theoretic_beam(&c.uvw, &freqs[k], &c.wgt, n, args.scale);
            fit_estimates.push(gemclean::beam_fit_estimate(
                b,
                args.scale,
                args.tapers.gaussian_beam,
            ));
        }
        let m: GridMeasurement<T> = GridMeasurement::from_single_unprepared(
            c.uvw,
            freqs[k].clone(),
            c.vis,
            c.wgt,
            n,
            args.scale,
            args.epsilon,
            opts,
        )?;
        let psf2n = if p == 0 || same.is_none() {
            Some(m.psf_image_with(2 * n, args.wgridding && !args.beam_no_w)?)
        } else {
            None
        };
        let m = if args.plan_reuse {
            m.prepare()?
        } else {
            m.without_plan_reuse()
        }
        .releasing_grids();
        match psf2n {
            Some(psf2n) => {
                let columns = if args.beam_band {
                    m.band_columns(2 * n)
                } else {
                    n + 1
                };
                beams.push(Beam::from_double_band(n, &psf2n, args.patch, columns)?);
                if p == 0 {
                    restoring.push(gemclean::fit_restoring_beam(n, &psf2n, fit_estimates[k]));
                    let mut psf = vec![0.0; n * n];
                    for i in 0..n {
                        for j in 0..n {
                            psf[i * n + j] = psf2n[(i + n / 2) * 2 * n + j + n / 2];
                        }
                    }
                    psfs.push(psf);
                }
                beam_of.push(beams.len() - 1);
                shared_beam.push(p == 0);
            }
            None => {
                beam_of.push(same.unwrap_or(beam_of[e - p]));
                shared_beam.push(same == Some(beam_of[e - p]));
            }
        }
        measurements.push(m);
        memory::mark(&format!("entry {e}: psf and beam"));
    }
    drop(earlier);
    let t_psf = t.elapsed().as_secs_f64();
    let settings = clean_settings(args);
    let pair = |e: usize| (&measurements[e], &beams[beam_of[e]]);
    let ne = measurements.len();
    let mut dirty = vec![Vec::new(); ne];
    let mut model = vec![Vec::new(); ne];
    let mut residual = vec![Vec::new(); ne];
    let mut components = vec![0; ne];
    let mut majors = vec![0; ne];
    let mut runs_json = Vec::new();
    let mut reference_frequency = None;
    let joined_channels = args.join_channels && kout > 1;
    // Groups of entries deconvolved together, with their channel weights
    // (radler's `image_weight` of each channel's first entry in the group).
    let mut groups: Vec<(Vec<usize>, usize)> = Vec::new(); // (entries, npol in group)
    if args.join_pols {
        if joined_channels || kout == 1 {
            groups.push(((0..ne).collect(), npol));
        } else {
            for k in 0..kout {
                groups.push(((k * npol..(k + 1) * npol).collect(), npol));
            }
        }
    } else {
        for p in 0..npol {
            if joined_channels {
                groups.push(((0..kout).map(|k| k * npol + p).collect(), 1));
            } else {
                for k in 0..kout {
                    groups.push((vec![k * npol + p], 1));
                }
            }
        }
    }
    for (members, gpol) in groups {
        if members.len() == 1 {
            let e = members[0];
            let (m, b) = pair(e);
            let o = gemclean::run(m, b, &settings, None)?;
            components[e] = o.steps.len();
            majors[e] = o.cycles.len();
            runs_json.push(o.to_json(None));
            dirty[e] = o.dirty;
            model[e] = o.model;
            residual[e] = o.residual;
        } else {
            let pairs: Vec<(&GridMeasurement<T>, &Beam)> =
                members.iter().map(|&e| pair(e)).collect();
            let nch = members.len() / gpol;
            let w: Vec<f64> = (0..nch).map(|k| totals[members[k * gpol]]).collect();
            let cen: Vec<f64> = (0..nch)
                .map(|k| central[members[k * gpol] / npol])
                .collect();
            let fit = args
                .fit_spectral_pol
                .filter(|_| nch > 1)
                .map(|terms| PolynomialFit::new(terms, cen, w.clone()));
            let norm = if gpol > 1 {
                stokes::normalisation(&args.pols)
            } else {
                1.0
            };
            let j = run_joined_pols(&pairs, gpol, &w, norm, fit.as_ref(), &settings)?;
            if let Some(f) = &fit {
                reference_frequency = Some(f.reference);
            }
            runs_json.push(j.integrated.to_json(None));
            for ((e, d), (m, r)) in members
                .iter()
                .zip(j.dirty)
                .zip(j.model.into_iter().zip(j.residual))
            {
                components[*e] = j.integrated.steps.len();
                majors[*e] = j.integrated.cycles.len();
                dirty[*e] = d;
                model[*e] = m;
                residual[*e] = r;
            }
        }
        memory::mark(&format!("group of {}: clean", runs_json.len()));
    }
    Ok(PolImages {
        psf: psfs,
        restoring,
        fit_estimates,
        shared_beam,
        dirty,
        model,
        residual,
        components,
        majors,
        runs_json,
        reference_frequency,
        t_psf,
    })
}

/// Several polarisations: read each, weight them as WSClean's cache does
/// ([`stokes::weight_sources`]), deconvolve (joined or not, with or without
/// joined channels) and write WSClean's file names and header counters.
fn run_polarizations(
    args: &Args,
    raw: &[String],
    selection: &Selection,
    column: &str,
    wall: Instant,
) -> Result<(), String> {
    let n = args.size;
    let npol = args.pols.len();
    let t = Instant::now();
    let spectral_sel = args.channel_range.is_some() || args.average_channels > 1;
    let mut data = Vec::with_capacity(npol);
    let mut widths = Vec::new();
    for &p in &args.pols {
        let sel = Selection {
            polarization: p,
            ..selection.clone()
        };
        let mut d = input::read_ms(&args.ms, &sel)?;
        let mut w = input::channel_widths(&args.ms, &sel)?;
        if w.len() != d.freq.len() {
            return Err("CHAN_WIDTH and CHAN_FREQ differ in length".into());
        }
        if spectral_sel {
            (d, w) = select_and_average(d, w, args)?;
        }
        widths = w;
        data.push(d);
    }
    let t_read = t.elapsed().as_secs_f64();
    memory::mark("read");
    let t = Instant::now();
    let nchan = data[0].freq.len();
    let rows = data[0].rows();
    let phase_dir = data[0].phase_dir;
    let groups: Vec<Vec<usize>> = if args.channels_out > 1 {
        spectral::channel_groups(&data[0].freq, None, args.channels_out)?
    } else {
        vec![(0..nchan).collect()]
    };
    let kout = groups.len();
    let mf = args.mf_weighting.unwrap_or(args.join_channels);
    let all: Vec<usize> = (0..nchan).collect();
    // Imaging weights per (source set, channel group), computed once each.
    let mut cache: Vec<(WeightKey, Vec<f32>)> = Vec::new();
    let mut entries = Vec::with_capacity(kout * npol);
    let mut freqs = Vec::with_capacity(kout);
    let mut bands = Vec::with_capacity(kout);
    for (k, group) in groups.iter().enumerate() {
        let freq: Vec<f64> = group.iter().map(|&c| data[0].freq[c]).collect();
        let low = group
            .iter()
            .map(|&c| data[0].freq[c] - 0.5 * widths[c])
            .fold(f64::INFINITY, f64::min);
        let high = group
            .iter()
            .map(|&c| data[0].freq[c] + 0.5 * widths[c])
            .fold(f64::NEG_INFINITY, f64::max);
        let m = group.len();
        for p in 0..npol {
            let sources = stokes::weight_sources(
                npol,
                p,
                mf,
                args.join_pols,
                args.join_channels,
                args.channels_out,
            );
            // MF: one grid of all channels, sliced; else the group's own.
            let key = (sources.clone(), if mf { usize::MAX } else { k });
            if !cache.iter().any(|(c, _)| *c == key) {
                let src: Vec<&input::StokesI> = sources.iter().map(|&s| &data[s]).collect();
                let chans = if mf { &all } else { group };
                let w =
                    stokes::imaging_weights(&src, chans, args.weight, n, args.scale, &args.tapers)?;
                cache.push((key.clone(), w));
            }
            let imaging = &cache.iter().find(|(c, _)| *c == key).unwrap().1;
            let d = &data[p];
            let (mut vis, mut wgt) = (Vec::with_capacity(rows * m), Vec::with_capacity(rows * m));
            let (mut count, mut total, mut vsum) = (0u64, 0.0, 0.0);
            for row in 0..rows {
                for (j, &c) in group.iter().enumerate() {
                    vis.push(d.vis[row * nchan + c]);
                    let im = if mf {
                        imaging[row * nchan + c]
                    } else {
                        imaging[row * m + j]
                    };
                    let w = d.weight[row * nchan + c];
                    let g = if d.flag_row[row] {
                        0.0
                    } else {
                        f64::from(w) * f64::from(im)
                    };
                    if g != 0.0 {
                        count += 1;
                        total += g;
                        vsum += f64::from(w);
                    }
                    wgt.push(g);
                }
            }
            if total <= 0.0 {
                return Err(format!(
                    "output channel {k}, polarisation {}: no weighted visibilities",
                    args.pols[p]
                ));
            }
            let mut uvw = d.uvw.clone();
            let mut kept = 0;
            for row in 0..rows {
                let (a, b) = (row * m, (row + 1) * m);
                if wgt[a..b].iter().any(|&x| x != 0.0) {
                    if kept != row {
                        uvw.copy_within(3 * row..3 * row + 3, 3 * kept);
                        vis.copy_within(a..b, kept * m);
                        wgt.copy_within(a..b, kept * m);
                    }
                    kept += 1;
                }
            }
            uvw.truncate(3 * kept);
            vis.truncate(kept * m);
            wgt.truncate(kept * m);
            uvw.shrink_to_fit();
            vis.shrink_to_fit();
            wgt.shrink_to_fit();
            entries.push(PolEntry {
                uvw,
                vis,
                wgt,
                rows: kept,
                count,
                total,
                visibility_weight_sum: vsum,
            });
        }
        freqs.push(freq);
        bands.push((low, high));
    }
    drop(cache);
    let freq_all = data[0].freq.clone();
    drop(data);
    let t_weights = t.elapsed().as_secs_f64();
    memory::mark("weights");
    let meta: Vec<(u64, f64, f64, usize)> = entries
        .iter()
        .map(|e| (e.count, e.total, e.visibility_weight_sum, e.rows))
        .collect();
    let central: Vec<f64> = bands.iter().map(|(l, h)| 0.5 * (l + h)).collect();
    println!(
        "{}: {} rows ({column}, field {}), {} channels into {} output channels, polarisations {}{}, {} weighting{}, {:.2} s read, {:.2} s weights",
        args.ms.display(),
        rows,
        args.field,
        nchan,
        kout,
        args.pols
            .iter()
            .map(|p| p.name())
            .collect::<Vec<_>>()
            .join(","),
        if args.join_pols { " joined" } else { "" },
        if mf { "MF" } else { "per-channel" },
        if args.join_channels {
            ", channels joined"
        } else {
            ""
        },
        t_read,
        t_weights
    );
    let opts = Options {
        flip_v: true,
        flip_w: true,
        do_wgridding: args.wgridding,
        ..Options::default()
    };
    let out = if args.single {
        deconvolve_pols::<f32>(args, entries, &freqs, &central, opts)?
    } else {
        deconvolve_pols::<f64>(args, entries, &freqs, &central, opts)?
    };
    let t = Instant::now();
    let scale_deg = args.scale.to_degrees();
    let prefix = &args.name;
    let chan = |k: usize| {
        if kout > 1 {
            format!("-{k:04}")
        } else {
            String::new()
        }
    };
    // Header counters: dirty images their own entry's, the PSF the first
    // polarisation's, model, residual and restored image those of the last
    // entry imaged in the channel by the end of its deconvolution group
    // (WSClean's per-channel `OutputChannelInfo` holds it).
    let counters = |e: usize, components: usize, majors: usize| -> Vec<Card> {
        let (count, total, vsum, _) = meta[e];
        vec![
            card(
                "WSCNVIS",
                Value::Float(count as f64),
                "visibilities with nonzero weight",
            ),
            card(
                "WSCIMGWG",
                Value::Float(total),
                "sum of the gridding weights",
            ),
            card("WSCVWSUM", Value::Float(vsum), ""),
            card("WSCNITER", Value::Float(components as f64), "components"),
            card("WSCMAJOR", Value::Float(majors as f64), "major cycles"),
            card("ORIGIN", Value::Str("gemclean (rang-core)".into()), ""),
        ]
    };
    let jy_pixel = |cards: &[Card]| -> Vec<Card> {
        let mut c: Vec<Card> = cards
            .iter()
            .filter(|(k, _, _)| k != "BUNIT")
            .cloned()
            .collect();
        c.push(card("BUNIT", Value::Str("JY/PIXEL".into()), ""));
        c
    };
    for (k, band) in bands.iter().enumerate() {
        let wcs = if kout > 1 {
            fits::wcs_cards_band(phase_dir.0, phase_dir.1, n, args.scale, band.0, band.1)
        } else {
            fits::wcs_cards(phase_dir.0, phase_dir.1, n, args.scale, &freq_all)
        };
        let header = |e: usize, pol: Pol| {
            let mut b = wcs.clone();
            stokes::set_stokes_card(&mut b, pol);
            b.extend(beam_cards(&out.restoring[k], scale_deg));
            b.extend(counters(e, out.components[e], out.majors[e]));
            b
        };
        let first = k * npol;
        let last = first + npol - 1;
        write_image(
            &PathBuf::from(format!("{prefix}{}-psf.fits", chan(k))),
            n,
            &out.psf[k],
            args.bitpix,
            &header(first, args.pols[0]),
            &[],
        )?;
        for (p, &pol) in args.pols.iter().enumerate() {
            let e = first + p;
            let path = |kind: &str| PathBuf::from(format!("{prefix}{}-{pol}-{kind}.fits", chan(k)));
            write_image(
                &path("dirty"),
                n,
                &out.dirty[e],
                args.bitpix,
                &header(e, pol),
                &[],
            )?;
            // WSClean writes these at the end of the deconvolution group: with
            // joined polarisations after the last entry of the channel is
            // imaged, otherwise after the entry itself.
            let mut late = header(if args.join_pols { last } else { e }, pol);
            // The iteration counters are the entry's own.
            late.retain(|(key, _, _)| key != "WSCNITER" && key != "WSCMAJOR");
            late.extend([
                card(
                    "WSCNITER",
                    Value::Float(out.components[e] as f64),
                    "components",
                ),
                card(
                    "WSCMAJOR",
                    Value::Float(out.majors[e] as f64),
                    "major cycles",
                ),
            ]);
            write_image(
                &path("model"),
                n,
                &out.model[e],
                args.bitpix,
                &jy_pixel(&late),
                &[],
            )?;
            write_image(
                &path("residual"),
                n,
                &out.residual[e],
                args.bitpix,
                &late,
                &[],
            )?;
            if args.restore {
                let image =
                    gemclean::restore(n, &out.model[e], &out.residual[e], &out.restoring[k]);
                write_image(&path("image"), n, &image, args.bitpix, &late, &[])?;
            }
        }
    }
    let mut restoring_mfs = None;
    if kout > 1 {
        // MFS: every polarisation's means use the channel weights WSClean's
        // per-channel info holds at the end, the last polarisation's.
        let wl: Vec<f64> = (0..kout).map(|k| meta[k * npol + npol - 1].1).collect();
        let psf_mfs = weighted_mean(&out.psf, &wl);
        let mfs_estimate = out
            .fit_estimates
            .iter()
            .copied()
            .fold(f64::INFINITY, f64::min);
        let r_mfs = gemclean::fit_restoring_beam(n, &embed_double(n, &psf_mfs), mfs_estimate);
        let low = bands.iter().map(|b| b.0).fold(f64::INFINITY, f64::min);
        let high = bands.iter().map(|b| b.1).fold(f64::NEG_INFINITY, f64::max);
        let lasts: Vec<usize> = (0..kout).map(|k| k * npol + npol - 1).collect();
        let header = |pol: Pol, components: usize, majors: usize| {
            let mut b = fits::wcs_cards_band(phase_dir.0, phase_dir.1, n, args.scale, low, high);
            stokes::set_stokes_card(&mut b, pol);
            b.extend(beam_cards(&r_mfs, scale_deg));
            b.extend([
                card(
                    "WSCNVIS",
                    Value::Float(lasts.iter().map(|&e| meta[e].0).sum::<u64>() as f64),
                    "visibilities with nonzero weight",
                ),
                card(
                    "WSCIMGWG",
                    Value::Float(wl.iter().sum()),
                    "sum of the gridding weights",
                ),
                card(
                    "WSCVWSUM",
                    Value::Float(lasts.iter().map(|&e| meta[e].2).sum()),
                    "",
                ),
                card("WSCNITER", Value::Float(components as f64), "components"),
                card("WSCMAJOR", Value::Float(majors as f64), "major cycles"),
                card("ORIGIN", Value::Str("gemclean (rang-core)".into()), ""),
            ]);
            b
        };
        write_image(
            &PathBuf::from(format!("{prefix}-MFS-psf.fits")),
            n,
            &psf_mfs,
            args.bitpix,
            &header(args.pols[0], 0, 0),
            &[],
        )?;
        for (p, &pol) in args.pols.iter().enumerate() {
            let pick = |v: &[Vec<f64>]| -> Vec<Vec<f64>> {
                (0..kout).map(|k| v[k * npol + p].clone()).collect()
            };
            let comps: usize = (0..kout).map(|k| out.components[k * npol + p]).sum();
            let majors = (0..kout)
                .map(|k| out.majors[k * npol + p])
                .max()
                .unwrap_or(0);
            let h = header(pol, comps, majors);
            let path = |kind: &str| PathBuf::from(format!("{prefix}-MFS-{pol}-{kind}.fits"));
            let dirty = weighted_mean(&pick(&out.dirty), &wl);
            write_image(&path("dirty"), n, &dirty, args.bitpix, &h, &[])?;
            let model = weighted_mean(&pick(&out.model), &wl);
            let residual = weighted_mean(&pick(&out.residual), &wl);
            write_image(&path("model"), n, &model, args.bitpix, &jy_pixel(&h), &[])?;
            write_image(&path("residual"), n, &residual, args.bitpix, &h, &[])?;
            if args.restore {
                let image = gemclean::restore(n, &model, &residual, &r_mfs);
                write_image(&path("image"), n, &image, args.bitpix, &h, &[])?;
            }
        }
        restoring_mfs = Some(r_mfs);
    }
    let t_write = t.elapsed().as_secs_f64();
    memory::mark("write");
    let beam_json = |r: &gemclean::RestoringBeam| {
        obj(&[
            ("bmaj_deg", num(r.major * scale_deg)),
            ("bmin_deg", num(r.minor * scale_deg)),
            ("bpa_deg", num(r.pa.to_degrees())),
            ("fit_pixels", r.pixels.to_string()),
        ])
    };
    let entries_json: Vec<String> = meta
        .iter()
        .enumerate()
        .map(|(e, (count, total, _, rows))| {
            obj(&[
                ("channel", (e / npol).to_string()),
                ("polarization", text(args.pols[e % npol].name())),
                ("weight_sum", num(*total)),
                ("visibilities_weighted", count.to_string()),
                ("rows_gridded", rows.to_string()),
                ("beam_of_first_polarization", out.shared_beam[e].to_string()),
                ("components", out.components[e].to_string()),
                ("major_cycles", out.majors[e].to_string()),
            ])
        })
        .collect();
    let argv: Vec<String> = raw.iter().map(|s| text(s)).collect();
    let report = obj(&[
        ("tool", text("gemclean")),
        ("version", text(env!("CARGO_PKG_VERSION"))),
        ("argv", arr(&argv)),
        ("ms", text(&args.ms.display().to_string())),
        ("data_column", text(column)),
        ("field", args.field.to_string()),
        (
            "polarizations",
            arr(&args.pols.iter().map(|p| text(p.name())).collect::<Vec<_>>()),
        ),
        ("join_polarizations", args.join_pols.to_string()),
        (
            "polarization_normalisation",
            num(stokes::normalisation(&args.pols)),
        ),
        ("channels_read", nchan.to_string()),
        ("channels_out", kout.to_string()),
        ("join_channels", args.join_channels.to_string()),
        ("mf_weighting", mf.to_string()),
        (
            "fit_spectral_pol",
            args.fit_spectral_pol
                .map_or("null".into(), |t| t.to_string()),
        ),
        ("reference_frequency_hz", opt(out.reference_frequency)),
        ("size", n.to_string()),
        ("scale_arcsec", num(args.scale.to_degrees() * 3600.0)),
        ("gridder_single", args.single.to_string()),
        ("wgridder_accuracy", num(args.epsilon)),
        ("phase_dir_rad", arr(&[num(phase_dir.0), num(phase_dir.1)])),
        ("entries", arr(&entries_json)),
        (
            "restoring_beams",
            arr(&out.restoring.iter().map(beam_json).collect::<Vec<_>>()),
        ),
        (
            "mfs_restoring_beam",
            restoring_mfs.as_ref().map_or("null".into(), beam_json),
        ),
        ("runs", arr(&out.runs_json)),
        (
            "seconds",
            obj(&[
                ("read", num(t_read)),
                ("weights", num(t_weights)),
                ("psf_and_beams", num(out.t_psf)),
                ("write", num(t_write)),
                ("wall", num(wall.elapsed().as_secs_f64())),
            ]),
        ),
        ("threads", rayon::current_num_threads().to_string()),
        (
            "peak_memory_bytes",
            gemclean::peak_memory_bytes().map_or("null".into(), |b| b.to_string()),
        ),
    ]);
    std::fs::write(format!("{prefix}-report.json"), report + "\n").map_err(|e| e.to_string())?;
    println!(
        "{} groups deconvolved; wall {:.2} s",
        out.runs_json.len(),
        wall.elapsed().as_secs_f64()
    );
    Ok(())
}

/// Predict `-name`'s model images into the model column (research/g6-predict.md).
fn write_model(args: &Args) -> Result<(predict::Written, f64), String> {
    let t = Instant::now();
    let sel = Selection {
        field: args.field,
        scans: args.scans.clone(),
        min_uvw_m: args.min_uvw_m,
        max_uvw_m: args.max_uvw_m,
        ..Selection::default()
    };
    let band = input::band(&args.ms, &sel)?;
    let pred = predict::Predictor::from_files(
        &args.name,
        &band.freq,
        args.channels_out,
        args.channel_range,
        args.average_channels,
        args.epsilon,
        args.wgridding,
        args.single,
    )?;
    let m = &pred.models[0];
    if args.size != 0 && m.n != args.size {
        return Err(format!(
            "{}: {} pixels, but -size {}",
            m.path.display(),
            m.n,
            args.size
        ));
    }
    if args.scale > 0.0 && (m.scale - args.scale).abs() > 1e-9 * args.scale {
        return Err(format!(
            "{}: pixels of {:.6} asec, but -scale {:.6} asec",
            m.path.display(),
            m.scale.to_degrees() * 3600.0,
            args.scale.to_degrees() * 3600.0
        ));
    }
    let w = predict::write_model_column(&args.ms, &sel, &args.model_column, &pred)?;
    let seconds = t.elapsed().as_secs_f64();
    println!(
        "{}: {} of {} rows predicted into {} ({}{} channels from {} model image(s), {} blocks, {:.2} s)",
        args.ms.display(),
        w.rows_selected,
        w.rows_total,
        w.column,
        if w.added { "column added; " } else { "" },
        w.channels_predicted,
        pred.models.len(),
        w.blocks,
        seconds
    );
    Ok((w, seconds))
}

fn written_json(w: &predict::Written, seconds: f64) -> String {
    obj(&[
        ("column", text(&w.column)),
        ("added", w.added.to_string()),
        ("rows_selected", w.rows_selected.to_string()),
        ("rows_total", w.rows_total.to_string()),
        ("channels_predicted", w.channels_predicted.to_string()),
        ("blocks", w.blocks.to_string()),
        ("seconds", num(seconds)),
    ])
}

/// Why `-model-column` may not be written, if it may not (E5-02,
/// research/e5-final.md): gemclean never writes DATA, the column the
/// observation came in, and never writes the column it images, which the
/// model would overwrite. `data` is the column being imaged, when known.
fn model_column_error(model: &str, data: Option<&str>) -> Option<String> {
    if model == "DATA" {
        return Some(
            "-model-column DATA: gemclean never writes the DATA column (the model column is \
             written after imaging unless -no-update-model-required, and by -predict); name \
             another column, such as MODEL_DATA"
                .into(),
        );
    }
    if data == Some(model) {
        return Some(format!(
            "-model-column {model} is the column being imaged (-data-column, or CORRECTED_DATA \
             when the MS has it), so the model would overwrite it; name another column, such as \
             MODEL_DATA, or add -no-update-model-required"
        ));
    }
    None
}

/// After imaging: the model column, unless -no-update-model-required.
fn update_model(args: &Args) -> Result<String, String> {
    if !args.update_model {
        return Ok("null".into());
    }
    let (w, seconds) = write_model(args)?;
    Ok(written_json(&w, seconds))
}

/// `-predict`: the model column from existing model images, no imaging.
fn predict_only(args: &Args, raw: &[String], wall: Instant) -> Result<(), String> {
    let (w, seconds) = write_model(args)?;
    let argv: Vec<String> = raw.iter().map(|s| text(s)).collect();
    let report = obj(&[
        ("tool", text("gemclean")),
        ("version", text(env!("CARGO_PKG_VERSION"))),
        ("argv", arr(&argv)),
        ("ms", text(&args.ms.display().to_string())),
        ("field", args.field.to_string()),
        (
            "scans",
            if args.scans.is_empty() {
                "null".into()
            } else {
                arr(&args.scans.iter().map(|x| x.to_string()).collect::<Vec<_>>())
            },
        ),
        ("unit_weights", args.unit_weights.to_string()),
        ("predict", written_json(&w, seconds)),
        ("wgridder_accuracy", num(args.epsilon)),
        ("gridder_single", args.single.to_string()),
        ("threads", rayon::current_num_threads().to_string()),
        (
            "peak_memory_bytes",
            gemclean::peak_memory_bytes().map_or("null".into(), |b| b.to_string()),
        ),
    ]);
    std::fs::write(format!("{}-predict-report.json", args.name), report + "\n")
        .map_err(|e| e.to_string())?;
    println!("wall {:.2} s", wall.elapsed().as_secs_f64());
    Ok(())
}

fn data_rows_total(ms: &Path) -> Option<u64> {
    crate::ms::Table::open(ms).ok().map(|t| t.nrows)
}

/// Run gemclean with `args` (without the program name); returns the exit
/// code: 0, or 2 after `gemclean: <error>` on stderr. A panic unwinds out
/// of it (the binary then exits with 101). Rust's stdout is flushed.
pub fn main(args: &[String]) -> i32 {
    crate::wgridder::set_default_plane_group(crate::wgridder::PLANE_GROUP);
    let code = match run(args) {
        Ok(()) => 0,
        Err(e) => {
            eprintln!("gemclean: {e}");
            2
        }
    };
    let _ = std::io::Write::flush(&mut std::io::stdout());
    code
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
                CycleStop::MeasuredStale {
                    rho: 1.0,
                    g: 0.95,
                    floor: 0.01,
                },
            ),
            (
                "-size 64 64 -scale 2asec -stale-floor 0 x.ms",
                CycleStop::MeasuredStale {
                    rho: 1.0,
                    g: 0.95,
                    floor: 0.0,
                },
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
                CycleStop::MeasuredStale {
                    rho: 2.0,
                    g: 0.8,
                    floor: 0.01,
                },
            ),
            (
                "-size 64 64 -scale 2asec -mgain 0.8 -stale-rule 2 x.ms",
                CycleStop::MeasuredStale {
                    rho: 2.0,
                    g: 0.8,
                    floor: 0.01,
                },
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

    #[test]
    fn the_model_column_is_never_data_nor_the_imaged_column() {
        // E5-02 (research/e5-final.md): refused at parsing, naming the option.
        let parse = |line: &str| {
            let raw: Vec<String> = line.split(' ').map(String::from).collect();
            parse_args(&raw)
        };
        for line in [
            "-size 64 64 -scale 2asec -model-column DATA x.ms",
            "-size 64 64 -scale 2asec -predict -model-column DATA x.ms",
            "-size 64 64 -scale 2asec -data-column CORRECTED_DATA -model-column CORRECTED_DATA x.ms",
        ] {
            let e = parse(line)
                .err()
                .unwrap_or_else(|| panic!("accepted: {line}"));
            assert!(e.starts_with("-model-column "), "{line}: {e}");
        }
        for line in [
            "-size 64 64 -scale 2asec x.ms",
            "-size 64 64 -scale 2asec -model-column MODEL_2 x.ms",
            "-size 64 64 -scale 2asec -data-column DATA -model-column MODEL_DATA x.ms",
            // Nothing is written without the model update.
            "-size 64 64 -scale 2asec -no-update-model-required -model-column DATA x.ms",
        ] {
            assert!(parse(line).is_ok(), "{line}");
        }
        // The column chosen at run time (CORRECTED_DATA when present).
        assert!(model_column_error("CORRECTED_DATA", Some("CORRECTED_DATA")).is_some());
        assert!(model_column_error("MODEL_DATA", Some("CORRECTED_DATA")).is_none());
    }

    #[test]
    fn gridder_precision_defaults() {
        // Task G7 (research/g7-defaults.md): 1e-4 in single precision by default;
        // a finer accuracy alone gives double; -single and -double win.
        let parse = |line: &str| {
            let raw: Vec<String> = line.split(' ').map(String::from).collect();
            parse_args(&raw).unwrap()
        };
        let a = parse("-size 64 64 -scale 2asec x.ms");
        assert!(a.single && a.epsilon == 1e-4);
        let a = parse("-size 64 64 -scale 2asec -wgridder-accuracy 1e-6 x.ms");
        assert!(!a.single && a.epsilon == 1e-6);
        assert!(!parse("-size 64 64 -scale 2asec -double x.ms").single);
        assert!(parse("-size 64 64 -scale 2asec -wgridder-accuracy 1e-6 -single x.ms").single);
        assert!(!parse("-size 64 64 -scale 2asec -single -double x.ms").single);
    }

    #[test]
    fn thresholds_are_finite_and_not_negative() {
        // Correctness audit 2026-11-13: a NaN threshold never ends the minor
        // cycle; NaN, infinite and negative thresholds are refused.
        let parse = |line: &str| {
            let raw: Vec<String> = line.split(' ').map(String::from).collect();
            parse_args(&raw)
        };
        for flag in ["-threshold", "-abs-threshold", "-auto-threshold"] {
            for bad in ["nan", "-1", "inf"] {
                assert!(parse(&format!("-size 64 64 -scale 2asec {flag} {bad} x.ms")).is_err());
            }
            assert!(parse(&format!("-size 64 64 -scale 2asec {flag} 0.5 x.ms")).is_ok());
        }
    }

    #[test]
    fn multiscale_flags() {
        let parse = |line: &str| {
            let raw: Vec<String> = line.split(' ').map(String::from).collect();
            parse_args(&raw)
        };
        assert!(
            parse("-size 64 64 -scale 2asec x.ms")
                .unwrap()
                .multiscale
                .is_none()
        );
        let a = parse("-size 64 64 -scale 2asec -multiscale x.ms").unwrap();
        assert_eq!(a.multiscale, Some(MultiscaleSettings::default()));
        let a = parse(
            "-size 64 64 -scale 2asec -multiscale -multiscale-scales 0,5,12.5 \
             -multiscale-scale-bias 0.7 -multiscale-shape gaussian -multiscale-gain 0.1 \
             -multiscale-max-scales 3 -mgain 0.8 x.ms",
        )
        .unwrap();
        let ms = a.multiscale.unwrap();
        assert_eq!(ms.scales, vec![0.0, 5.0, 12.5]);
        assert_eq!(ms.scale_bias, 0.7);
        assert_eq!(ms.shape, multiscale::Shape::Gaussian);
        assert_eq!(ms.sub_minor_gain, 0.1);
        assert_eq!(ms.max_scales, 3);
        assert_eq!(a.cycle_stop, CycleStop::PeakFraction(0.8));
        for line in [
            "-size 64 64 -scale 2asec -multiscale-scales 0,5 x.ms",
            "-size 64 64 -scale 2asec -multiscale -multiscale-shape disc x.ms",
            "-size 64 64 -scale 2asec -multiscale -no-multiscale-fast-subminor x.ms",
            "-size 64 64 -scale 2asec -multiscale -multiscale-convolution-padding 1.2 x.ms",
            "-size 64 64 -scale 2asec -multiscale -stop-rule certified x.ms",
            "-size 64 64 -scale 2asec -multiscale -mgain-misfit 0.5 x.ms",
            "-size 64 64 -scale 2asec -multiscale -multiscale-gain 0 x.ms",
        ] {
            assert!(parse(line).is_err(), "{line}");
        }
    }
}
