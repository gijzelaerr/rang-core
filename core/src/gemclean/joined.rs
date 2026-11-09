//! Joined-channel deconvolution for gemclean: WSClean's `-join-channels`
//! with GeMClean's minor step (`research/g3-spectral.md`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! As in radler's `GenericClean::ExecuteMajorIteration` and
//! `SubMinorLoop::Run` (WSClean 3.7), the peak is found on the integrated
//! residual, the weighted mean of the channel residuals with the channel
//! weights (`ImageSet::GetLinearIntegratedWithNormalChannels`); each channel's
//! component is the gain times its own residual at the peak (here its exact
//! value for its own beam, over that beam's peak), replaced by the spectral fit
//! when there is one (`PerformSpectralFit`), and each channel subtracts its
//! own beam. The threshold, the major-cycle rule, `τ`, the drift and the
//! measured stale level read the integrated values. Each channel keeps its
//! working map and its components since the last resync, so that its exact
//! value at the pick is the same gather as in [`super::run`]; with one channel
//! of weight one the picks and components are those of [`super::run`].

use super::spectral::PolynomialFit;
use super::{
    Beam, Cycle, CycleStop, MinorStop, Outcome, Resyncs, Settings, Since, StopReason, Timings,
    Work, Working, effective_threshold, kernels, memory,
};
use crate::clean::{CleanStep, argmax_abs};
use crate::clean_certified::Measurement;
use kernels::Level;
use rayon::prelude::*;
use std::time::Instant;

/// The outcome of [`run_joined`].
#[derive(Clone, Debug)]
pub struct Joined {
    /// The integrated run: its images are the weighted means of the channels'
    /// (dirty, model, residual), its misfits the weighted means of theirs, its
    /// steps the integrated exact peaks.
    pub integrated: Outcome,
    /// Per channel.
    pub dirty: Vec<Vec<f64>>,
    pub model: Vec<Vec<f64>>,
    pub residual: Vec<Vec<f64>>,
    pub q_final: Vec<f64>,
}

/// `Σ a_k x_k` per pixel, in channel order.
fn integrate(images: &[Vec<f64>], a: &[f64]) -> Vec<f64> {
    let mut out = vec![0.0; images[0].len()];
    out.par_iter_mut().enumerate().for_each(|(i, o)| {
        let mut s = 0.0;
        for (img, &ak) in images.iter().zip(a) {
            s += ak * img[i];
        }
        *o = s;
    });
    out
}

/// `r −= c b(· − x_p)` within the patch, on a plain map.
fn subtract_patch(level: Level, r: &mut [f64], n: usize, beam: &Beam, p: usize, c: f64) {
    let h = beam.patch;
    let (px, py) = (p % n, p / n);
    let (y0, y1) = (py.saturating_sub(h), (py + h).min(n - 1));
    let (x0, x1) = (px.saturating_sub(h), (px + h).min(n - 1));
    let pw = 2 * h + 1;
    let len = x1 - x0 + 1;
    for y in y0..=y1 {
        let b0 = (y + h - py) * pw + (x0 + h - px);
        kernels::sub_scaled(
            level,
            &mut r[y * n + x0..y * n + x0 + len],
            &beam.patch_values[b0..b0 + len],
            c,
        );
    }
}

struct State<'a> {
    beams: Vec<&'a Beam>,
    a: Vec<f64>,
    buffers: [Vec<f64>; 2],
}

impl State<'_> {
    /// Every channel's map made exact, `r̃_k = r_k − B_k (m_k − m_k,major)`,
    /// then the integrated map from them.
    #[allow(clippy::too_many_arguments)]
    fn resync(
        &mut self,
        work: &mut Working,
        maps: &mut [Vec<f64>],
        since: &mut [Since],
        models: &[Vec<f64>],
        models_major: &[Vec<f64>],
        residuals: &[Vec<f64>],
    ) {
        let [delta, conv] = &mut self.buffers;
        for k in 0..maps.len() {
            delta.resize(models[k].len(), 0.0);
            conv.resize(models[k].len(), 0.0);
            delta
                .par_iter_mut()
                .zip(&models[k])
                .zip(&models_major[k])
                .for_each(|((d, a), b)| *d = a - b);
            self.beams[k].convolver.apply_into(delta, conv);
            maps[k]
                .par_iter_mut()
                .zip(&residuals[k])
                .zip(conv.par_iter())
                .for_each(|((w, r), c)| *w = r - c);
            since[k].clear();
        }
        work.r = integrate(maps, &self.a);
        work.refresh_all();
    }
}

/// Joined deconvolution of `channels` (a measurement and the beam from its
/// `2n` PSF each) with channel weights `weights` (WSClean's image weights),
/// and with the polynomial fit `fit` applied to every component's channel
/// values when given.
pub fn run_joined<M: Measurement>(
    channels: &[(&M, &Beam)],
    weights: &[f64],
    fit: Option<&PolynomialFit>,
    settings: &Settings,
) -> Result<Joined, String> {
    run_joined_pols(channels, 1, weights, 1.0, fit, settings)
}

/// [`run_joined`] over output channels and polarisations together
/// (`-join-polarizations`, task G9, `research/g9-stokes.md`): `entries` are
/// channel-major, `npol` polarisations per channel, `weights` one per channel.
/// As radler's `GetLinearIntegrated` with linked polarisations (the peak
/// finding of WSClean 3.7's default sub-minor loop), the integrated residual
/// is `norm Σ_k a_k Σ_p r_kp` with `a_k` the channel weights over their sum and
/// `norm` the polarisation normalisation ([`super::stokes::normalisation`]);
/// each entry's component is the gain times its own exact value over its
/// beam's peak, the fit is applied per polarisation over the channels, and
/// each entry subtracts its own beam. With one polarisation and `norm = 1`
/// this is [`run_joined`]'s arithmetic, operation for operation.
pub fn run_joined_pols<M: Measurement>(
    entries: &[(&M, &Beam)],
    npol: usize,
    weights: &[f64],
    norm: f64,
    fit: Option<&PolynomialFit>,
    settings: &Settings,
) -> Result<Joined, String> {
    let channels = entries;
    if npol == 0 || entries.len() != weights.len() * npol {
        return Err("one weight per channel and npol entries per channel are needed".into());
    }
    let start = Instant::now();
    let s = settings;
    let kc = channels.len();
    let nch = weights.len();
    if kc == 0 {
        return Err("one weight per channel is needed".into());
    }
    if weights.iter().any(|&w| !(w > 0.0 && w.is_finite())) {
        return Err("every joined channel needs a positive weight".into());
    }
    if fit.is_some_and(|f| f.frequencies.len() != nch) {
        return Err("the fit needs one frequency per channel".into());
    }
    let n = channels[0].0.side();
    if channels.iter().any(|(m, b)| m.side() != n || b.n != n) {
        return Err("every channel's measurement and beam must have the image side".into());
    }
    if !(s.gain > 0.0 && s.gain < 2.0) {
        return Err("the gain must be in (0, 2)".into());
    }
    if matches!(s.cycle_stop, CycleStop::Certified { .. }) || s.audit {
        return Err("joined channels do not take the certified rule or -audit".into());
    }
    let wsum: f64 = weights.iter().sum();
    // One coefficient per entry: the channel's share times the polarisation
    // normalisation (exactly the share when npol = 1 and norm = 1).
    let a: Vec<f64> = (0..kc)
        .map(|e| {
            let share = weights[e / npol] / wsum;
            if norm == 1.0 { share } else { share * norm }
        })
        .collect();
    let level = s.level.unwrap_or_else(kernels::level);
    let mut st = State {
        beams: channels.iter().map(|c| c.1).collect(),
        a: a.clone(),
        buffers: [Vec::new(), Vec::new()],
    };
    let mut timings = Timings::default();
    let mut models = vec![vec![0.0; n * n]; kc];
    let t = Instant::now();
    let mut residuals = Vec::with_capacity(kc);
    let mut qs = Vec::with_capacity(kc);
    for (k, (m, _)) in channels.iter().enumerate() {
        let (r, q) = m.residual(&models[k])?;
        residuals.push(r);
        qs.push(q);
    }
    timings.initial = t.elapsed().as_secs_f64();
    let dirty = residuals.clone();
    let mut residual_int = integrate(&residuals, &a);
    let dirty_int = residual_int.clone();
    let weighted = |q: &[f64]| q.iter().zip(&a).map(|(q, a)| a * q).sum::<f64>();
    let q0 = weighted(&qs);
    let mut q = q0;
    let mut fraction = s.major_fraction;
    let mut stale_per_flux = 0.0_f64;
    let mut steps: Vec<CleanStep> = Vec::new();
    let mut taus = Vec::new();
    let mut cycles: Vec<Cycle> = Vec::new();
    let mut resyncs_all = Resyncs::default();
    let mut correction_terms = 0u64;
    let mut work_all = Work::default();
    let mut values = vec![0.0; kc];
    let mut exact = vec![0.0; kc];
    let stop = loop {
        let threshold = effective_threshold(&residual_int, s);
        let (_, peak) = argmax_abs(&residual_int);
        if peak.abs() < threshold {
            break StopReason::Threshold;
        }
        if steps.len() >= s.max_components {
            break StopReason::Components;
        }
        if cycles.len() >= s.max_major {
            break StopReason::MajorCycles;
        }
        let mut ct = Timings::default();
        let models_major = models.clone();
        let mut work = Working::new(residual_int.clone(), n, level, s.tile, s.lazy_bounds);
        let mut maps = residuals.clone();
        let mut since: Vec<Since> = (0..kc).map(|_| Since::default()).collect();
        let mut predicted = 0.0;
        let mut resyncs = Resyncs::default();
        let mut tau_min = f64::INFINITY;
        let mut abs_flux = 0.0_f64;
        let goal = fraction * q.max(0.0);
        let first_peak = peak.abs();
        let stale_used = stale_per_flux;
        let taken_before = steps.len();
        let minor_start = Instant::now();
        macro_rules! resync {
            () => {{
                let tr = Instant::now();
                st.resync(
                    &mut work,
                    &mut maps,
                    &mut since,
                    &models,
                    &models_major,
                    &residuals,
                );
                ct.resync += tr.elapsed().as_secs_f64();
            }};
        }
        let minor_stop = loop {
            let (p, rt) = work.argmax();
            let tc = Instant::now();
            let mut r = 0.0;
            for k in 0..kc {
                let (beam, sk) = (channels[k].1, &since[k]);
                let corr = if sk.keys.is_empty() || beam.f == 0.0 {
                    0.0
                } else {
                    correction_terms += sk.keys.len() as u64;
                    kernels::gather_sum(level, &beam.exterior, beam.base(p), &sk.keys, &sk.flux)
                };
                exact[k] = maps[k][p] - corr;
                r += a[k] * exact[k];
            }
            ct.correction += tc.elapsed().as_secs_f64();
            let pending = since[0].steps;
            if r.abs() < threshold || r == 0.0 {
                if pending == 0 {
                    break MinorStop::Threshold;
                }
                resync!();
                resyncs.threshold += 1;
                continue;
            }
            let mut e = 0.0;
            for k in 0..kc {
                let beam = channels[k].1;
                e += a[k] * (beam.f * beam.peak * since[k].abs_sum);
            }
            let tau = r.abs() / (rt.abs() + e);
            if tau < s.tau_min {
                resync!();
                resyncs.tau += 1;
                continue;
            }
            if steps.len() >= s.max_components {
                break MinorStop::Budget;
            }
            if steps.len() > taken_before {
                let stop_here = match s.cycle_stop {
                    CycleStop::PeakFraction(g) => r.abs() < (1.0 - g) * first_peak,
                    CycleStop::MeasuredStale { rho, g, floor } => {
                        if cycles.is_empty() {
                            r.abs() < (1.0 - g) * first_peak
                        } else {
                            r.abs() <= (rho * stale_used * abs_flux).max(floor * first_peak)
                        }
                    }
                    CycleStop::Certified { .. }
                    | CycleStop::MisfitFraction
                    | CycleStop::Threshold => false,
                };
                if stop_here {
                    break MinorStop::PeakRule;
                }
            }
            for k in 0..kc {
                values[k] = s.gain * exact[k] / channels[k].1.peak;
            }
            if let Some(f) = fit {
                if npol == 1 {
                    f.fit_and_evaluate(&mut values);
                } else {
                    for p in 0..npol {
                        let mut one: Vec<f64> = (0..nch).map(|k| values[k * npol + p]).collect();
                        f.fit_and_evaluate(&mut one);
                        for (k, v) in one.into_iter().enumerate() {
                            values[k * npol + p] = v;
                        }
                    }
                }
            }
            for k in 0..kc {
                let (beam, c) = (channels[k].1, values[k]);
                abs_flux += a[k] * c.abs();
                models[k][p] += c;
                // The misfit change of the step, −c r + c² b(0)/2, in general form:
                // after a fit c is no longer γ r / b(0).
                predicted -= a[k] * (c * exact[k] - 0.5 * c * c * beam.peak);
                subtract_patch(level, &mut maps[k], n, beam, p, c);
                work.subtract_patch(beam, p, a[k] * c);
                since[k].add(p, beam.key(p), c);
            }
            steps.push(CleanStep { pixel: p, peak: r });
            taus.push(tau);
            tau_min = tau_min.min(tau);
            if s.cycle_stop == CycleStop::MisfitFraction && goal > 0.0 && -predicted >= goal {
                break MinorStop::MajorFraction;
            }
            let drifted = (r - rt).abs() > s.drift * rt.abs();
            if drifted || since[0].steps >= s.resync_every {
                resync!();
                if drifted {
                    resyncs.drift += 1;
                } else {
                    resyncs.every += 1;
                }
            }
        };
        if since[0].steps > 0 {
            resync!();
        }
        ct.minor = minor_start.elapsed().as_secs_f64() - ct.resync;
        work_all.add(&work.work);
        memory::mark(&format!("cycle {}: minor", cycles.len() + 1));
        let tm = Instant::now();
        let mut next = Vec::with_capacity(kc);
        for (k, (m, _)) in channels.iter().enumerate() {
            let (r, qk) = m.residual(&models[k])?;
            next.push(r);
            qs[k] = qk;
        }
        ct.major = tm.elapsed().as_secs_f64();
        let next_int = integrate(&next, &a);
        let q_next = weighted(&qs);
        let stale_linf = next_int
            .par_iter()
            .zip(work.r.par_iter())
            .map(|(x, y)| (x - y).abs())
            .reduce(|| 0.0, f64::max);
        if abs_flux > 0.0 {
            stale_per_flux = stale_linf / abs_flux;
        }
        let dq_exact = q_next - q;
        let gap = dq_exact - predicted;
        cycles.push(Cycle {
            index: cycles.len(),
            components: steps.len() - taken_before,
            resyncs,
            stop: minor_stop,
            peak_start: peak.abs(),
            threshold,
            fraction,
            q_before: q,
            q_after: q_next,
            dq_exact,
            dq_predicted: predicted,
            gap,
            gap_relative: gap / q,
            ascending: dq_exact > 0.0,
            abs_flux,
            stale_linf,
            stale_per_flux_used: stale_used,
            bound_linf: 0.0,
            bound_violations: 0,
            tau_min,
            timings: ct,
        });
        timings.minor += ct.minor;
        timings.correction += ct.correction;
        timings.resync += ct.resync;
        timings.major += ct.major;
        resyncs_all.drift += resyncs.drift;
        resyncs_all.tau += resyncs.tau;
        resyncs_all.every += resyncs.every;
        resyncs_all.threshold += resyncs.threshold;
        if predicted < 0.0 {
            if gap.abs() > (1.0 - s.theta) * predicted.abs() {
                fraction *= 0.5;
            } else {
                fraction = (fraction * 2.0).min(s.major_fraction);
            }
        }
        residuals = next;
        residual_int = next_int;
        q = q_next;
    };
    timings.total = start.elapsed().as_secs_f64();
    let model_int = integrate(&models, &a);
    let f = channels.iter().map(|c| c.1.f).fold(0.0, f64::max);
    Ok(Joined {
        integrated: Outcome {
            dirty: dirty_int,
            model: model_int,
            residual: residual_int,
            q0,
            q_final: q,
            steps,
            taus,
            cycles,
            stop,
            f,
            patch: channels[0].1.patch,
            resyncs: resyncs_all,
            timings,
            correction_terms,
            work: work_all,
            audit_max_error: None,
            level,
        },
        dirty,
        model: models,
        residual: residuals,
        q_final: qs,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::clean_certified::{Complex, WgridMeasurement};
    use crate::gemclean::run;

    fn measurement(seed: u64, freq: f64, n: usize, sky: &[(usize, f64)]) -> WgridMeasurement {
        let mut state = seed;
        let mut next = move || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / (1u64 << 53) as f64 - 0.5
        };
        let nrow = 900;
        let uvw: Vec<f64> = (0..3 * nrow)
            .map(|i| next() * if i % 3 == 2 { 30.0 } else { 2400.0 })
            .collect();
        let cell = 4e-5;
        let opts = crate::gemclean::sim::imaging_options();
        let freqs = vec![freq];
        let empty = WgridMeasurement::new(
            uvw.clone(),
            freqs.clone(),
            vec![Complex::new(0.0, 0.0); nrow],
            vec![1.0; nrow],
            n,
            cell,
            1e-9,
            opts,
        )
        .unwrap();
        let mut model = vec![0.0; n * n];
        for &(p, f) in sky {
            model[p] = f;
        }
        let vis = empty.predict(&model).unwrap();
        let wgt: Vec<f64> = (0..nrow).map(|_| 1.0 + next()).collect();
        WgridMeasurement::new(uvw, freqs, vis, wgt, n, cell, 1e-9, opts).unwrap()
    }

    fn settings() -> Settings {
        Settings {
            threshold: 1e-3,
            max_components: 400,
            ..Settings::default()
        }
    }

    /// One channel of weight one: the picks, components and residual of
    /// [`run`], bit for bit.
    #[test]
    fn one_channel_is_the_single_run() {
        let n = 32;
        let m = measurement(5, 1.2e9, n, &[(10 * n + 12, 1.0), (20 * n + 7, -0.4)]);
        let beam = Beam::from_double(n, &m.psf_image(2 * n).unwrap(), 8).unwrap();
        let single = run(&m, &beam, &settings(), None).unwrap();
        let joined = run_joined(&[(&m, &beam)], &[2.5], None, &settings()).unwrap();
        assert_eq!(single.model, joined.model[0]);
        assert_eq!(single.model, joined.integrated.model);
        assert_eq!(single.residual, joined.residual[0]);
        assert_eq!(single.steps.len(), joined.integrated.steps.len());
        for (a, b) in single.steps.iter().zip(&joined.integrated.steps) {
            assert_eq!((a.pixel, a.peak), (b.pixel, b.peak));
        }
        assert_eq!(single.cycles.len(), joined.integrated.cycles.len());
        assert_eq!(single.stop, joined.integrated.stop);
    }

    /// Two polarisations of one channel joined (task G9): every
    /// polarisation's model recovers its own sky, a negative Q included,
    /// from components at the shared picks.
    #[test]
    fn two_polarisations_joined_recover_each_sky() {
        let n = 32;
        let (p1, p2) = (10 * n + 12, 21 * n + 20);
        let i = measurement(11, 1.2e9, n, &[(p1, 1.0), (p2, 0.4)]);
        let q = measurement(11, 1.2e9, n, &[(p1, -0.3), (p2, 0.2)]);
        let b = Beam::from_double(n, &i.psf_image(2 * n).unwrap(), 8).unwrap();
        let s = Settings {
            max_components: 2000,
            ..settings()
        };
        let j = run_joined_pols(&[(&i, &b), (&q, &b)], 2, &[1.0], 1.0, None, &s).unwrap();
        assert_eq!(j.integrated.stop, StopReason::Threshold);
        let flux = |m: &[f64], p: usize| {
            let (x, y) = ((p % n) as isize, (p / n) as isize);
            let mut sum = 0.0;
            for dy in -2..=2 {
                for dx in -2..=2 {
                    sum += m[((y + dy) as usize) * n + (x + dx) as usize];
                }
            }
            sum
        };
        for (m, want) in [(&j.model[0], [1.0, 0.4]), (&j.model[1], [-0.3, 0.2])] {
            assert!(
                (flux(m, p1) - want[0]).abs() < 0.02,
                "{} {}",
                flux(m, p1),
                want[0]
            );
            assert!(
                (flux(m, p2) - want[1]).abs() < 0.02,
                "{} {}",
                flux(m, p2),
                want[1]
            );
        }
        // Every Q component sits on a pick shared with I.
        assert!(
            j.model[0]
                .iter()
                .zip(&j.model[1])
                .all(|(a, b)| *b == 0.0 || *a != 0.0)
        );
        // One polarisation through run_joined_pols is run_joined.
        let one = run_joined_pols(&[(&i, &b)], 1, &[2.5], 1.0, None, &settings()).unwrap();
        let plain = run_joined(&[(&i, &b)], &[2.5], None, &settings()).unwrap();
        assert_eq!(one.model, plain.model);
        assert_eq!(one.residual, plain.residual);
    }

    /// Two channels of one sky with a spectral slope: the joined run finds
    /// both sources in both channels, the fitted values lie on one line of
    /// the channel frequencies, and the integrated residual falls below the
    /// threshold.
    #[test]
    fn two_channels_with_a_linear_fit() {
        let n = 32;
        let (p1, p2) = (10 * n + 12, 21 * n + 20);
        let lo = measurement(7, 1.0e9, n, &[(p1, 1.2), (p2, 0.5)]);
        let hi = measurement(8, 1.5e9, n, &[(p1, 0.8), (p2, 0.6)]);
        let b_lo = Beam::from_double(n, &lo.psf_image(2 * n).unwrap(), 8).unwrap();
        let b_hi = Beam::from_double(n, &hi.psf_image(2 * n).unwrap(), 8).unwrap();
        let fit = PolynomialFit::new(2, vec![1.0e9, 1.5e9], vec![1.0, 1.0]);
        let s = Settings {
            max_components: 2000,
            ..settings()
        };
        let j = run_joined(&[(&lo, &b_lo), (&hi, &b_hi)], &[1.0, 1.0], Some(&fit), &s).unwrap();
        assert_eq!(j.integrated.stop, StopReason::Threshold);
        let flux = |m: &[f64], p: usize| {
            let (x, y) = ((p % n) as isize, (p / n) as isize);
            let mut sum = 0.0;
            for dy in -2..=2 {
                for dx in -2..=2 {
                    sum += m[((y + dy) as usize) * n + (x + dx) as usize];
                }
            }
            sum
        };
        for (p, want_lo, want_hi) in [(p1, 1.2, 0.8), (p2, 0.5, 0.6)] {
            let (got_lo, got_hi) = (flux(&j.model[0], p), flux(&j.model[1], p));
            assert!((got_lo - want_lo).abs() < 0.02, "{got_lo} {want_lo}");
            assert!((got_hi - want_hi).abs() < 0.02, "{got_hi} {want_hi}");
        }
        // Two channels and two terms: every component is fitted exactly, so the
        // models of the two channels are each other's linear images.
        assert!(
            j.model[0]
                .iter()
                .zip(&j.model[1])
                .all(|(a, b)| (a == &0.0) == (b == &0.0))
        );
    }
}
