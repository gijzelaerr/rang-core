//! Tightness and hypothesis measurements of `research/stop-rule-theorem.md`.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! ```text
//! cargo run --release --manifest-path core/Cargo.toml --example stop_rule_probe -- \
//!     PREP_DIR OUT.json UNIFORM_SAMPLES EXACT_COLUMNS [THRESHOLD]
//! ```
//!
//! `PREP_DIR` is a directory of `examples/gemclean_bench_compare.py prepare`.
//! Runs the default rule, then measures per cycle the true beam error
//! `E Δm = (G − B) Δm` at the end of the cycle and at checkpoints inside it,
//! against the candidate bounds of the note: `Δ ‖Δm‖₁`, `Σ_j |Δm_j| f(|x_j|)`,
//! the envelope `(|Δm| ⋆ g)(q)`, and the exact column maxima of the brightest
//! pixels. Prints the table, the exact columns against it, and writes JSON.

use rang_core::clean_certified::{Complex, Measurement};
use rang_core::gemclean::json::{arr, num, obj};
use rang_core::gemclean::measure::GridMeasurement;
use rang_core::gemclean::stale_bound::{BoundKind, StaleBound, StopBound};
use rang_core::gemclean::{self, Beam, Convolver, CycleStop, Settings};
use rang_core::wgridder::Options;
use std::path::Path;
use std::time::Instant;

fn read_f64(path: &Path) -> Result<Vec<f64>, String> {
    let bytes = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    Ok(bytes
        .chunks_exact(8)
        .map(|b| f64::from_le_bytes(b.try_into().expect("eight bytes")))
        .collect())
}

fn number_after(text: &str, key: &str) -> Result<f64, String> {
    let at = text.find(key).ok_or_else(|| format!("no {key}"))? + key.len();
    let rest = text[at..].trim_start_matches([' ', ':', '\n', '"']);
    let end = rest
        .find(|c: char| !(c.is_ascii_digit() || matches!(c, '.' | 'e' | 'E' | '-' | '+')))
        .unwrap_or(rest.len());
    rest[..end].parse().map_err(|e| format!("{key}: {e}"))
}

fn linf(x: &[f64]) -> (usize, f64) {
    let mut best = (0, 0.0);
    for (i, v) in x.iter().enumerate() {
        if v.abs() > best.1 {
            best = (i, v.abs());
        }
    }
    best
}

/// Flux in model pixels farther than `radius` pixels from every source of the
/// catalogue: the score's "false" flux. Gridder pixels `(p % n, p / n)` are the
/// FITS `(y, x)` of the catalogue's `dy`, `dx`.
fn false_flux(model: &[f64], n: usize, sources: &[(f64, f64)], radius: f64) -> (f64, usize) {
    let half = (n / 2) as f64;
    let (mut total, mut count) = (0.0, 0);
    for (p, &c) in model.iter().enumerate() {
        if c == 0.0 {
            continue;
        }
        let (y, x) = ((p % n) as f64 - half, (p / n) as f64 - half);
        let near = sources
            .iter()
            .any(|(dx, dy)| ((x - dx).powi(2) + (y - dy).powi(2)).sqrt() <= radius);
        if !near {
            total += c.abs();
            count += 1;
        }
    }
    (total, count)
}

fn catalogue_offsets(path: &Path) -> Result<Vec<(f64, f64)>, String> {
    let text = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    let mut out = Vec::new();
    for piece in text.split("\"dx\"").skip(1) {
        let dx = number_after(piece, "")?;
        let dy = number_after(piece, "\"dy\"")?;
        out.push((dx, dy));
    }
    Ok(out)
}

/// `Clean.pixel_flux_le` against a certified run, summed over the false pixels
/// of each cycle: the net flux at `q` against
/// `max(0, |r₀(q)| + |S(q)| − L) + C(q)`, with `L = (1 − κ) T`, `C` the largest step
/// at `q` and `S` the other components' change at `q` at the end of the cycle. The
/// theorem takes `S` over the whole cycle; a major cycle measures its end only.
fn pixel_flux_check(
    measurement: &GridMeasurement<f64>,
    run: &gemclean::Outcome,
    sources: &[(f64, f64)],
    radius: f64,
    level: f64,
) -> Result<String, String> {
    let n = measurement.side();
    let half = (n / 2) as f64;
    let is_false = |p: usize| {
        let (y, x) = ((p % n) as f64 - half, (p / n) as f64 - half);
        !sources
            .iter()
            .any(|(dx, dy)| ((x - dx).powi(2) + (y - dy).powi(2)).sqrt() <= radius)
    };
    let gain = 0.1;
    let mut model = vec![0.0; n * n];
    let (mut r0, _) = measurement.residual(&model)?;
    let mut at = 0;
    let mut rows = Vec::new();
    for (index, cycle) in run.cycles.iter().enumerate() {
        let mut placed = std::collections::HashMap::<usize, (f64, f64)>::new();
        for step in &run.steps[at..at + cycle.components] {
            let c = gain * step.peak;
            model[step.pixel] += c;
            if is_false(step.pixel) {
                let e = placed.entry(step.pixel).or_insert((0.0, 0.0));
                e.0 += c;
                e.1 = e.1.max(c.abs());
            }
        }
        at += cycle.components;
        let (r1, _) = measurement.residual(&model)?;
        let (mut flux, mut bound, mut excess) = (0.0, 0.0, 0.0);
        let mut over = 0usize;
        for (&q, &(net, step)) in &placed {
            // r₁ = r₀ − net − S, so S from the two exact residuals.
            let others = r0[q] - net - r1[q];
            let e = (r0[q].abs() + others.abs() - level).max(0.0);
            flux += net.abs();
            excess += e;
            bound += e + step;
            if net.abs() > e + step {
                over += 1;
            }
        }
        println!(
            "pixel flux, cycle {index}: {} false pixels, net flux {:.3e}, excess {excess:.3e}, bound {bound:.3e}, over {over}",
            placed.len(),
            flux
        );
        rows.push(obj(&[
            ("index", index.to_string()),
            ("false_pixels", placed.len().to_string()),
            ("net_flux", num(flux)),
            ("excess", num(excess)),
            ("bound", num(bound)),
            ("pixels_over_bound", over.to_string()),
        ]));
        r0 = r1;
    }
    Ok(arr(&rows))
}

/// `counter PREP CATALOGUE CENTRE_JY SAMPLES KAPPA OUT.json`: the data plus a
/// source of `CENTRE_JY` at the phase centre, imaged by the default, by the peak
/// fraction 0.95 and, for `KAPPA > 0`, by the certified rule.
fn counter(args: &[String]) -> Result<(), String> {
    let prep = Path::new(&args[2]);
    let mut sources = catalogue_offsets(Path::new(&args[3]))?;
    sources.push((0.0, 0.0));
    let centre: f64 = args[4].parse().map_err(|_| "CENTRE_JY")?;
    let uniform: usize = args[5].parse().map_err(|_| "SAMPLES")?;
    let kappa: f64 = args[6].parse().map_err(|_| "KAPPA")?;
    let meta = std::fs::read_to_string(prep.join("meta.json")).map_err(|e| e.to_string())?;
    let n = number_after(&meta, "\"size\"")? as usize;
    let scale = number_after(&meta, "\"scale_arcsec\"")?.to_radians() / 3600.0;
    let uvw = read_f64(&prep.join("uvw.f64"))?;
    let freq = read_f64(&prep.join("freq.f64"))?;
    let wgt = read_f64(&prep.join("wgt.f64"))?;
    let raw = read_f64(&prep.join("vis.c128"))?;
    let vis: Vec<Complex<f64>> = raw
        .chunks_exact(2)
        .map(|c| Complex::new(c[0] + centre, c[1]))
        .collect();
    drop(raw);
    let opts = Options {
        flip_v: true,
        flip_w: true,
        do_wgridding: true,
        ..Options::default()
    };
    let sum: f64 = wgt.iter().sum();
    let normalised: Vec<f64> = wgt.iter().map(|w| w / sum).collect();
    let epsilon = 1e-9;
    let measurement =
        GridMeasurement::<f64>::new(uvw.clone(), freq.clone(), vis, wgt, n, scale, epsilon, opts)?;
    let psf2n = measurement.psf_image(2 * n)?;
    let beam = Beam::from_double(n, &psf2n, 64)?;
    let settings = Settings {
        threshold: 1e-4,
        max_components: 1_000_000,
        max_major: 1000,
        ..Settings::default()
    };
    let radius = 2.0 * 10.76 / 1.5;
    let report = |name: &str, o: &gemclean::Outcome| {
        let (flux, pixels) = false_flux(&o.model, n, &sources, radius);
        println!(
            "{name}: {} components, {} cycles, {:?}, Q/Q0 {:.6e}, false flux {:.3} mJy in {pixels} pixels",
            o.steps.len(),
            o.cycles.len(),
            o.stop,
            o.q_final / o.q0,
            flux * 1e3
        );
        let mut rows = Vec::new();
        for c in &o.cycles {
            println!(
                "  {} K={} {:?} peak {:.3e} flux {:.4} stale {:.3e} delta {:.3e} used {:.3e} bound {:.3e} violations {}",
                c.index,
                c.components,
                c.stop,
                c.peak_start,
                c.abs_flux,
                c.stale_linf,
                c.stale_linf / c.abs_flux.max(1e-300),
                c.stale_per_flux_used,
                c.bound_linf,
                c.bound_violations
            );
            rows.push(obj(&[
                ("components", c.components.to_string()),
                ("peak_start", num(c.peak_start)),
                ("abs_flux", num(c.abs_flux)),
                ("stale_linf", num(c.stale_linf)),
                ("delta_used", num(c.stale_per_flux_used)),
                ("bound_linf", num(c.bound_linf)),
                ("bound_violations", c.bound_violations.to_string()),
            ]));
        }
        obj(&[
            ("components", o.steps.len().to_string()),
            ("major_cycles", o.cycles.len().to_string()),
            ("q_over_q0", num(o.q_final / o.q0)),
            ("false_flux", num(flux)),
            ("false_pixels", pixels.to_string()),
            ("cycles", arr(&rows)),
        ])
    };
    let default_run = gemclean::run(&measurement, &beam, &settings, None)?;
    let default_json = report("default", &default_run);
    drop(default_run);
    // WSClean's rule on the same data, which reads no measurement.
    let peak_run = gemclean::run(
        &measurement,
        &beam,
        &Settings {
            cycle_stop: CycleStop::PeakFraction(0.95),
            ..settings
        },
        None,
    )?;
    let peak_json = report("peak fraction 0.95", &peak_run);
    drop(peak_run);
    if kappa <= 0.0 {
        let out = obj(&[
            ("centre_jy", num(centre)),
            ("default", default_json),
            ("peak_fraction_095", peak_json),
        ]);
        return std::fs::write(&args[7], out).map_err(|e| e.to_string());
    }
    let opts_plain = Options {
        pixsize_x: scale,
        pixsize_y: scale,
        ..opts
    };
    let table = StaleBound::compute(
        n,
        scale,
        &opts_plain,
        &uvw,
        &freq,
        &normalised,
        &psf2n,
        epsilon,
        uniform,
    )?;
    let bound = StopBound::new(&table, BoundKind::Envelope)?;
    let certified = gemclean::run_with_bound(
        &measurement,
        &beam,
        &Settings {
            cycle_stop: CycleStop::Certified { kappa },
            ..settings
        },
        None,
        Some(&bound),
    )?;
    let certified_json = report("certified", &certified);
    let pixel_json = pixel_flux_check(
        &measurement,
        &certified,
        &sources,
        radius,
        (1.0 - kappa) * settings.threshold,
    )?;
    let out = obj(&[
        ("centre_jy", num(centre)),
        ("kappa", num(kappa)),
        ("default", default_json),
        ("peak_fraction_095", peak_json),
        ("certified", certified_json),
        ("pixel_flux", pixel_json),
    ]);
    std::fs::write(&args[7], out).map_err(|e| e.to_string())
}

fn main() -> Result<(), String> {
    let args: Vec<String> = std::env::args().collect();
    if args.get(1).is_some_and(|a| a == "counter") {
        return counter(&args);
    }
    if args.len() < 5 {
        return Err("usage: PREP_DIR OUT.json UNIFORM_SAMPLES EXACT_COLUMNS [THRESHOLD]".into());
    }
    let prep = Path::new(&args[1]);
    let uniform: usize = args[3].parse().map_err(|_| "UNIFORM_SAMPLES")?;
    let top: usize = args[4].parse().map_err(|_| "EXACT_COLUMNS")?;
    let threshold: f64 = args
        .get(5)
        .map_or(Ok(1e-4), |t| t.parse())
        .map_err(|_| "THRESHOLD")?;
    let meta = std::fs::read_to_string(prep.join("meta.json")).map_err(|e| e.to_string())?;
    let n = number_after(&meta, "\"size\"")? as usize;
    let scale = number_after(&meta, "\"scale_arcsec\"")?.to_radians() / 3600.0;
    let uvw = read_f64(&prep.join("uvw.f64"))?;
    let freq = read_f64(&prep.join("freq.f64"))?;
    let wgt = read_f64(&prep.join("wgt.f64"))?;
    let raw = read_f64(&prep.join("vis.c128"))?;
    let vis: Vec<Complex<f64>> = raw
        .chunks_exact(2)
        .map(|c| Complex::new(c[0], c[1]))
        .collect();
    drop(raw);
    let opts = Options {
        flip_v: true,
        flip_w: true,
        do_wgridding: true,
        ..Options::default()
    };
    let sum: f64 = wgt.iter().sum();
    let normalised: Vec<f64> = wgt.iter().map(|w| w / sum).collect();
    let epsilon = 1e-9;
    let measurement =
        GridMeasurement::<f64>::new(uvw.clone(), freq.clone(), vis, wgt, n, scale, epsilon, opts)?;
    let t = Instant::now();
    let psf2n = measurement.psf_image(2 * n)?;
    let t_psf = t.elapsed().as_secs_f64();
    let beam = Beam::from_double(n, &psf2n, 64)?;
    println!(
        "n {n} cell {scale:.4e} rad; PSF {t_psf:.1} s; beam peak {:.12}",
        beam.peak
    );

    let t = Instant::now();
    let outcome = gemclean::run(
        &measurement,
        &beam,
        &Settings {
            threshold,
            max_components: 1_000_000,
            max_major: 1000,
            ..Settings::default()
        },
        None,
    )?;
    println!(
        "default run: {} components, {} major cycles, {:.1} s",
        outcome.steps.len(),
        outcome.cycles.len(),
        t.elapsed().as_secs_f64()
    );

    let opts_plain = Options {
        pixsize_x: scale,
        pixsize_y: scale,
        ..opts
    };
    let bound = StaleBound::compute(
        n,
        scale,
        &opts_plain,
        &uvw,
        &freq,
        &normalised,
        &psf2n,
        epsilon,
        uniform,
    )?;
    println!(
        "table: {} gridder calls, {:.1} s; moments m1 {:.1} rms {:.1} max {:.1} sum {:.9}; H {:.3e} h0 {:.3e}; Delta {:.3e}; rigorous remainder at this sampling {:.3e}",
        bound.sampling.calls(),
        bound.seconds,
        bound.moments.m1,
        bound.moments.m2.sqrt(),
        bound.moments.max,
        bound.moments.sum,
        bound.sampling.h,
        bound.sampling.h0,
        bound.delta(),
        if uniform == 0 {
            0.0
        } else {
            bound.sampling.gap_bound(bound.moments.m2)
        }
    );
    for l in &bound.sampling.levels {
        println!(
            "  level: range {:.3e} degree {} nodes {} tail {:.2e} factor {:.3}",
            l.range, l.degree, l.nodes, l.tail, l.factor
        );
    }
    for b in (7..bound.f.len()).step_by(8) {
        println!("  f(R ≤ {:.5} rad) = {:.3e}", bound.radii[b], bound.f[b]);
    }
    let envelope = Convolver::new(n, &bound.envelope)?;
    let (env_at, env_max) = linf(&bound.envelope);
    let m = 2 * n;
    let far = |lo: f64| {
        let mut best = 0.0_f64;
        for (i, v) in bound.envelope.iter().enumerate() {
            let (dx, dy) = ((i % m) as f64 - n as f64, (i / m) as f64 - n as f64);
            if (dx * dx + dy * dy).sqrt() >= lo {
                best = best.max(*v);
            }
        }
        best
    };
    println!(
        "envelope: max {env_max:.3e} at offset ({}, {}); beyond 16 px {:.3e}, 64 px {:.3e}, 256 px {:.3e}, 1024 px {:.3e}",
        (env_at % m) as isize - n as isize,
        (env_at / m) as isize - n as isize,
        far(16.0),
        far(64.0),
        far(256.0),
        far(1024.0)
    );

    // The exact columns of the brightest model pixels.
    let t = Instant::now();
    let mut order: Vec<usize> = (0..n * n).filter(|&i| outcome.model[i] != 0.0).collect();
    order.sort_by(|&a, &b| outcome.model[b].abs().total_cmp(&outcome.model[a].abs()));
    order.truncate(top);
    let mut exact = vec![None; n * n];
    let mut columns = Vec::new();
    let mut delta_e = vec![0.0; n * n];
    for &j in &order {
        delta_e[j] = 1.0;
        let g = measurement.gram_apply(&delta_e)?;
        delta_e[j] = 0.0;
        let (jx, jy) = ((j % n) as isize, (j / n) as isize);
        let mut best = (0.0_f64, 0_isize, 0_isize);
        for qy in 0..n as isize {
            for qx in 0..n as isize {
                let e = g[qy as usize * n + qx as usize] - beam.at(qx - jx, qy - jy);
                if e.abs() > best.0 {
                    best = (e.abs(), qx - jx, qy - jy);
                }
            }
        }
        exact[j] = Some(best.0);
        let table = bound.at_pixel(j);
        columns.push(obj(&[
            ("x", (jx - n as isize / 2).to_string()),
            ("y", (jy - n as isize / 2).to_string()),
            ("flux", num(outcome.model[j])),
            ("column_sup", num(best.0)),
            ("offset_x", best.1.to_string()),
            ("offset_y", best.2.to_string()),
            ("table", num(table)),
            ("table_over_exact", num(table / best.0)),
        ]));
        println!(
            "column ({:5},{:5}) flux {:.4}: sup |E| {:.3e} at offset ({},{}); table {:.3e} ({:.2}x)",
            jx - n as isize / 2,
            jy - n as isize / 2,
            outcome.model[j],
            best.0,
            best.1,
            best.2,
            table,
            table / best.0
        );
    }
    let t_columns = t.elapsed().as_secs_f64();

    // Per cycle, at the end and at checkpoints.
    let gain = 0.1;
    let mut cycles_json = Vec::new();
    let mut at = 0usize;
    let mut delta_previous = 0.0_f64;
    for (index, cycle) in outcome.cycles.iter().enumerate() {
        let steps = &outcome.steps[at..at + cycle.components];
        let mut delta_m = vec![0.0; n * n];
        let mut sum_abs = 0.0;
        let mut e_radial = 0.0;
        let k = steps.len();
        let fractions = [0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.7, 0.85, 1.0];
        let marks: Vec<usize> = fractions
            .iter()
            .map(|f| ((k as f64 * f).ceil() as usize).clamp(1, k))
            .collect();
        let mut checkpoints = Vec::new();
        let mut last_ratio = 0.0;
        let mut end_row = String::new();
        for (t, step) in steps.iter().enumerate() {
            let c = gain * step.peak / beam.peak;
            delta_m[step.pixel] += c;
            sum_abs += c.abs();
            e_radial += c.abs() * bound.at_pixel(step.pixel);
            let done = t + 1;
            if !marks.contains(&done) {
                continue;
            }
            let g = measurement.gram_apply(&delta_m)?;
            let b = beam.convolve(&delta_m);
            let e: Vec<f64> = g.iter().zip(&b).map(|(a, b)| a - b).collect();
            let (worst_at, worst) = linf(&e);
            let l1: f64 = delta_m.iter().map(|x| x.abs()).sum();
            let abs_m: Vec<f64> = delta_m.iter().map(|x| x.abs()).collect();
            let env = envelope.apply(&abs_m);
            let (_, env_linf) = linf(&env);
            let radial_net: f64 = delta_m
                .iter()
                .enumerate()
                .filter(|&(_, c)| *c != 0.0)
                .map(|(j, c)| c.abs() * bound.at_pixel(j))
                .sum();
            let mixed: f64 = delta_m
                .iter()
                .enumerate()
                .filter(|&(_, c)| *c != 0.0)
                .map(|(j, c)| c.abs() * exact[j].unwrap_or_else(|| bound.at_pixel(j)))
                .sum();
            // The next pick of this cycle: what the rule's step would see.
            let next = steps.get(done);
            let (kappa, sign_ok, env_at_pick) = match next {
                Some(s) => (
                    e[s.pixel].abs() / s.peak.abs(),
                    (s.peak - e[s.pixel]).signum() == s.peak.signum(),
                    env[s.pixel],
                ),
                None => (f64::NAN, true, f64::NAN),
            };
            let ratio = worst / l1;
            last_ratio = ratio;
            let peak_next = next.map_or(f64::NAN, |s| s.peak.abs());
            println!(
                "cycle {index} t {done}/{k}: |Ec|inf {worst:.3e} at {worst_at}; |c|1 {l1:.4} ratio {ratio:.3e} (prev delta {delta_previous:.3e}); X: Delta {:.1} radial {:.1} mixed {:.1} envelope {:.1}; pick peak {peak_next:.3e} kappa {kappa:.3e} sign_ok {sign_ok}; env at pick {env_at_pick:.3e}",
                bound.delta() * l1 / worst,
                radial_net / worst,
                mixed / worst,
                env_linf / worst,
            );
            let row = obj(&[
                ("t", done.to_string()),
                ("stale_linf", num(worst)),
                ("net_l1", num(l1)),
                ("sum_abs", num(sum_abs)),
                ("ratio", num(ratio)),
                ("x_delta", num(bound.delta() * l1 / worst)),
                ("x_radial", num(radial_net / worst)),
                ("x_radial_steps", num(e_radial / worst)),
                ("x_mixed", num(mixed / worst)),
                ("x_envelope", num(env_linf / worst)),
                ("next_peak", num(peak_next)),
                ("kappa_true", num(kappa)),
                ("sign_ok", sign_ok.to_string()),
                ("envelope_at_pick", num(env_at_pick)),
            ]);
            if done == k {
                end_row = row.clone();
            }
            checkpoints.push(row);
        }
        let row = obj(&[
            ("index", index.to_string()),
            ("components", k.to_string()),
            ("peak_start", num(cycle.peak_start)),
            ("abs_flux", num(cycle.abs_flux)),
            ("stale_linf_report", num(cycle.stale_linf)),
            ("delta_used", num(cycle.stale_per_flux_used)),
            ("end", end_row),
            ("checkpoints", arr(&checkpoints)),
        ]);
        cycles_json.push(row);
        delta_previous = last_ratio;
        at += k;
    }
    let out = obj(&[
        ("prep", format!("{:?}", prep.display().to_string())),
        ("size", n.to_string()),
        ("uniform_samples", uniform.to_string()),
        ("gridder_calls", bound.sampling.calls().to_string()),
        ("table_seconds", num(bound.seconds)),
        ("columns_seconds", num(t_columns)),
        ("m1", num(bound.moments.m1)),
        ("m2", num(bound.moments.m2)),
        ("w_max", num(bound.moments.max)),
        ("h", num(bound.sampling.h)),
        ("h0", num(bound.sampling.h0)),
        (
            "rigorous_remainder",
            num(bound.sampling.gap_bound(bound.moments.m2)),
        ),
        ("delta", num(bound.delta())),
        (
            "radii",
            arr(&bound.radii.iter().map(|x| num(*x)).collect::<Vec<_>>()),
        ),
        (
            "f",
            arr(&bound.f.iter().map(|x| num(*x)).collect::<Vec<_>>()),
        ),
        ("envelope_max", num(env_max)),
        ("envelope_beyond_16", num(far(16.0))),
        ("envelope_beyond_64", num(far(64.0))),
        ("envelope_beyond_256", num(far(256.0))),
        ("envelope_beyond_1024", num(far(1024.0))),
        ("columns", arr(&columns)),
        ("cycles", arr(&cycles_json)),
    ]);
    std::fs::write(&args[2], out).map_err(|e| e.to_string())?;
    Ok(())
}
