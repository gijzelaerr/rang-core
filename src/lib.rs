//! A deliberately small scalar RIME experiment, not an operational calibrator.

mod linalg;
pub mod projector;
pub mod response;
pub mod trend;
pub mod tv;
use linalg::{Matrix, dot, eigen, mv, solve, zeros};
use std::f64::consts::PI;

const C: f64 = 299_792_458.0;
const ARCMIN: f64 = PI / (180.0 * 60.0);
const NANT: usize = 8;
const NPAR: usize = 2 * NANT;
const NTIME: usize = 24;
const FREQUENCIES: [f64; 4] = [0.95e9, 1.15e9, 1.35e9, 1.55e9];
// Rounded published horizontal positions, not survey-quality coordinates.
// Jonas & MeerKAT Team, Table 1, https://pos.sissa.it/277/001/pdf.
// Heights are set to zero. See data/README.md for provenance and limitations.
pub const ANTENNAS: [(&str, f64, f64); NANT] = [
    ("m000", -8.0, 27.0),
    ("m004", -124.0, -19.0),
    ("m008", -93.0, -302.0),
    ("m012", 140.0, -135.0),
    ("m016", 288.0, 49.0),
    ("m020", 97.0, -66.0),
    ("m024", -351.0, 386.0),
    ("m028", -51.0, 148.0),
];

#[derive(Clone, Debug)]
pub struct Config {
    pub seed: u64,
    /// Noise standard deviation per real/imaginary visibility component, Jy.
    pub noise: f64,
    /// Standard deviation per pointing axis, arcminutes.
    pub pointing: f64,
    /// Fractional true beam width error relative to the fitting model.
    pub beam_error: f64,
    pub budget: f64,
    pub target_flux: f64,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            seed: 7,
            noise: 0.01,
            pointing: 0.6,
            beam_error: 0.0,
            budget: 0.01,
            target_flux: 0.02,
        }
    }
}

impl Config {
    pub fn validate(&self) -> Result<(), String> {
        if !self.noise.is_finite() || self.noise < 0.0 || self.noise > 1.0 {
            return Err("noise must be finite and between 0 and 1 Jy".into());
        }
        if !self.pointing.is_finite() || !(0.0..=3.0).contains(&self.pointing) {
            return Err("pointing must be between 0 and 3 arcmin".into());
        }
        if !self.beam_error.is_finite() || self.beam_error.abs() > 0.1 {
            return Err("beam-error must be between -0.1 and 0.1".into());
        }
        if !self.budget.is_finite() || !(0.0..=1.0).contains(&self.budget) {
            return Err("budget must be between 0 and 1".into());
        }
        if !self.target_flux.is_finite() || !(0.0..=1.0).contains(&self.target_flux) {
            return Err("target-flux must be between 0 and 1 Jy".into());
        }
        Ok(())
    }
}

#[derive(Clone, Copy)]
struct Source {
    l: f64,
    m: f64,
    flux: f64,
    alpha: f64,
}

fn source(l_deg: f64, m_deg: f64, flux: f64) -> Source {
    Source {
        l: l_deg.to_radians().sin(),
        m: m_deg.to_radians().sin(),
        flux,
        alpha: -0.7,
    }
}

fn bright_sky() -> Vec<Source> {
    vec![
        source(0.0, 0.0, 1.0),
        source(0.35, 0.18, 0.7),
        source(-0.4, 0.2, 0.5),
        source(0.2, -0.42, 0.3),
    ]
}

/// Extended science template, discretized as an incoherent sum of point sources.
/// Truth uses 15x15 samples; inference uses 11x11. Both resolve the finest fringe.
fn science_sky(side: usize, shift: f64) -> Vec<Source> {
    let mut sky = Vec::new();
    let half = (side / 2) as f64;
    for i in 0..side {
        for j in 0..side {
            let x = (i as f64 - half) / half;
            let y = (j as f64 - half) / half;
            let weight = (-4.5 * (x * x + y * y)).exp();
            sky.push(source(0.35 + shift + 0.025 * x, 0.18 + 0.025 * y, weight));
        }
    }
    let norm: f64 = sky.iter().map(|s| s.flux).sum();
    for s in &mut sky {
        s.flux /= norm;
    }
    sky
}

#[derive(Clone)]
struct Sample {
    p: usize,
    q: usize,
    uvw: [f64; 3],
    angle: f64,
    freq: f64,
    train: bool,
}

/// ENU basis in equatorial coordinates at local sidereal angle zero.
/// Projection onto the source tangent triad is exact for the supplied baseline.
fn uvw(east: f64, north: f64, up: f64, hour: f64, dec: f64) -> [f64; 3] {
    let lat = (-30.713_f64).to_radians();
    let x = -north * lat.sin() + up * lat.cos();
    let y = east;
    let z = north * lat.cos() + up * lat.sin();
    [
        hour.sin() * x + hour.cos() * y,
        -dec.sin() * hour.cos() * x + dec.sin() * hour.sin() * y + dec.cos() * z,
        dec.cos() * hour.cos() * x - dec.cos() * hour.sin() * y + dec.sin() * z,
    ]
}

fn samples() -> Vec<Sample> {
    let mut result = Vec::new();
    let dec = (-45.0_f64).to_radians();
    let lat = (-30.713_f64).to_radians();
    for t in 0..NTIME {
        let hour = (-3.0 + 6.0 * t as f64 / (NTIME - 1) as f64) * PI / 12.0;
        let angle = hour
            .sin()
            .atan2(lat.tan() * dec.cos() - dec.sin() * hour.cos());
        for freq in FREQUENCIES {
            for (p, ap) in ANTENNAS.iter().enumerate() {
                for (q, aq) in ANTENNAS.iter().enumerate().skip(p + 1) {
                    let metres = uvw(ap.1 - aq.1, ap.2 - aq.2, 0.0, hour, dec);
                    result.push(Sample {
                        p,
                        q,
                        uvw: metres.map(|v| v * freq / C),
                        angle,
                        freq,
                        train: t < 18,
                    });
                }
            }
        }
    }
    result
}

/// Gaussian *voltage* beam: its squared response has FWHM 1.02 lambda / D.
fn voltage(x: f64, y: f64, dx: f64, dy: f64, freq: f64, width_error: f64) -> f64 {
    let fwhm = 1.02 * C / freq / 13.5 * (1.0 + width_error);
    (-2.0 * 2.0_f64.ln() * ((x - dx * ARCMIN).powi(2) + (y - dy * ARCMIN).powi(2)) / fwhm.powi(2))
        .exp()
}

/// Cached source fringes and beam coordinates; output stacks real, imaginary.
struct Operator {
    samples: Vec<Sample>,
    sky: Vec<Source>,
    cache: Vec<Vec<[f64; 4]>>,
}

impl Operator {
    fn new(samples: &[Sample], sky: Vec<Source>) -> Self {
        let cache = samples
            .iter()
            .map(|sample| {
                sky.iter()
                    .map(|s| {
                        let n = (1.0 - s.l * s.l - s.m * s.m).sqrt();
                        let phase = -2.0
                            * PI
                            * (sample.uvw[0] * s.l
                                + sample.uvw[1] * s.m
                                + sample.uvw[2] * (n - 1.0));
                        let (sin, cos) = sample.angle.sin_cos();
                        let flux = s.flux * (sample.freq / 1.28e9).powf(s.alpha);
                        [
                            cos * s.l + sin * s.m,
                            -sin * s.l + cos * s.m,
                            flux * phase.cos(),
                            flux * phase.sin(),
                        ]
                    })
                    .collect()
            })
            .collect();
        Self {
            samples: samples.to_vec(),
            sky,
            cache,
        }
    }

    fn evaluate(&self, theta: &[f64], width_error: f64, derivatives: bool) -> (Vec<f64>, Matrix) {
        // Optional shared log-width, in percent units. This keeps the width
        // positive and gives its parameter a scale comparable to pointing.
        let width_scale = (theta.get(NPAR).copied().unwrap_or(0.0) / 100.0).exp();
        let width_error = (1.0 + width_error) * width_scale - 1.0;
        let mut model = vec![0.0; 2 * self.samples.len()];
        let mut jac = if derivatives {
            zeros(model.len(), theta.len())
        } else {
            Vec::new()
        };
        for (i, sample) in self.samples.iter().enumerate() {
            let fwhm = 1.02 * C / sample.freq / 13.5 * (1.0 + width_error);
            let k = 4.0 * 2.0_f64.ln() * ARCMIN / fwhm.powi(2);
            for j in 0..self.sky.len() {
                let [x, y, re, im] = self.cache[i][j];
                let gain = voltage(
                    x,
                    y,
                    theta[2 * sample.p],
                    theta[2 * sample.p + 1],
                    sample.freq,
                    width_error,
                ) * voltage(
                    x,
                    y,
                    theta[2 * sample.q],
                    theta[2 * sample.q + 1],
                    sample.freq,
                    width_error,
                );
                for (component, fringe) in [re, im].iter().enumerate() {
                    let row = 2 * i + component;
                    let value = gain * fringe;
                    model[row] += value;
                    if derivatives {
                        for ant in [sample.p, sample.q] {
                            jac[row][2 * ant] += value * k * (x - theta[2 * ant] * ARCMIN);
                            jac[row][2 * ant + 1] += value * k * (y - theta[2 * ant + 1] * ARCMIN);
                            if theta.len() > NPAR {
                                let radius2 = (x - theta[2 * ant] * ARCMIN).powi(2)
                                    + (y - theta[2 * ant + 1] * ARCMIN).powi(2);
                                jac[row][NPAR] += value * k / ARCMIN * radius2 / 100.0;
                            }
                        }
                    }
                }
            }
        }
        (model, jac)
    }
}

struct Rng(u64);
impl Rng {
    fn uniform(&mut self) -> f64 {
        self.0 = self.0.wrapping_add(0x9e3779b97f4a7c15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
        z ^= z >> 31;
        ((z >> 11) as f64 + 0.5) / ((1u64 << 53) as f64)
    }
    fn normal(&mut self) -> f64 {
        (-2.0 * self.uniform().ln()).sqrt() * (2.0 * PI * self.uniform()).cos()
    }
}

struct Problem {
    bright: Operator,
    target: Operator,
    truth_target: Operator,
    probe: Operator,
}
impl Problem {
    fn new() -> Self {
        let samples = samples();
        Self {
            bright: Operator::new(&samples, bright_sky()),
            target: Operator::new(&samples, science_sky(11, 0.0)),
            truth_target: Operator::new(&samples, science_sky(15, 0.0)),
            probe: Operator::new(&samples, science_sky(15, -0.18)),
        }
    }
    fn train(&self, vector: &[f64]) -> Vec<f64> {
        vector
            .iter()
            .enumerate()
            .filter(|(i, _)| self.bright.samples[i / 2].train)
            .map(|(_, &v)| v)
            .collect()
    }
    fn jac_train(&self, matrix: &Matrix) -> Matrix {
        matrix
            .iter()
            .enumerate()
            .filter(|(i, _)| self.bright.samples[i / 2].train)
            .map(|(_, v)| v.clone())
            .collect()
    }
}

#[derive(Clone, Copy, PartialEq)]
enum Method {
    Fixed,
    Pointing,
    Joint,
    JointBeam,
    Protected,
    Oracle,
}

fn gram(jac: &Matrix) -> Matrix {
    let n = jac[0].len();
    let mut f = zeros(n, n);
    for row in jac {
        for p in 0..n {
            for q in 0..n {
                f[p][q] += row[p] * row[q];
            }
        }
    }
    f
}

fn jt(jac: &Matrix, y: &[f64]) -> Vec<f64> {
    let mut result = vec![0.0; jac[0].len()];
    for (row, &value) in jac.iter().zip(y) {
        for (out, &j) in result.iter_mut().zip(row) {
            *out += j * value;
        }
    }
    result
}

struct Geometry {
    f: Matrix,
    f0: Matrix,
    cross: Vec<f64>,
    denom: f64,
    norm: f64,
}
fn geometry(jac: &Matrix, target: &[f64], sky_ridge: f64, joint: bool) -> Geometry {
    let f0 = gram(jac);
    let cross = jt(jac, target);
    let norm = dot(target, target);
    let denom = norm + sky_ridge;
    let mut f = f0.clone();
    if joint {
        for p in 0..cross.len() {
            for q in 0..cross.len() {
                f[p][q] -= cross[p] * cross[q] / denom;
            }
        }
    }
    Geometry {
        f,
        f0,
        cross,
        denom,
        norm,
    }
}

/// Generalized modes F v = eta F0 v, dropping numerically unobservable modes.
fn modes(g: &Geometry) -> Vec<Vec<f64>> {
    let (values, vectors) = eigen(&g.f0);
    let keep: Vec<_> = (0..g.f.len())
        .filter(|&k| values[k] > values[0] * 1e-10)
        .collect();
    let basis: Vec<Vec<f64>> = keep
        .iter()
        .map(|&k| {
            (0..g.f.len())
                .map(|i| vectors[i][k] / values[k].sqrt())
                .collect()
        })
        .collect();
    let projected: Matrix = basis
        .iter()
        .map(|v| basis.iter().map(|w| dot(v, &mv(&g.f, w))).collect())
        .collect();
    let (eta, rot) = eigen(&projected);
    (0..eta.len())
        .filter(|&k| eta[k] >= 0.05)
        .map(|k| {
            (0..g.f.len())
                .map(|i| (0..basis.len()).map(|j| basis[j][i] * rot[j][k]).sum())
                .collect()
        })
        .collect()
}

fn full_basis(n: usize) -> Vec<Vec<f64>> {
    (0..n)
        .map(|i| (0..n).map(|j| if i == j { 1.0 } else { 0.0 }).collect())
        .collect()
}

fn reduced_solve(g: &Geometry, rhs: &[f64], basis: &[Vec<f64>], ridge: f64) -> Vec<f64> {
    if basis.is_empty() {
        return vec![0.0; g.f.len()];
    }
    let matrix: Matrix = basis
        .iter()
        .map(|v| {
            basis
                .iter()
                .map(|w| dot(v, &mv(&g.f, w)) + ridge * dot(v, w))
                .collect()
        })
        .collect();
    let b: Vec<_> = basis.iter().map(|v| dot(v, rhs)).collect();
    let x = solve(&matrix, &b);
    (0..g.f.len())
        .map(|i| basis.iter().zip(&x).map(|(v, a)| v[i] * a).sum())
        .collect()
}

fn local_loss(g: &Geometry, basis: &[Vec<f64>], ridge: f64, joint: bool) -> f64 {
    let factor = if joint { 1.0 - g.norm / g.denom } else { 1.0 };
    let rhs: Vec<_> = g.cross.iter().map(|x| x * factor / g.norm.sqrt()).collect();
    let response = reduced_solve(g, &rhs, basis, ridge);
    dot(&response, &mv(&g.f0, &response)).max(0.0).sqrt()
}

fn choose_basis(g: &Geometry, ridge: f64, method: Method, budget: f64) -> Vec<Vec<f64>> {
    if method != Method::Protected {
        return full_basis(g.f.len());
    }
    let mut basis = modes(g);
    // Greedy pruning checks the combined response, not just individual modes.
    while !basis.is_empty() && local_loss(g, &basis, ridge, true) > budget {
        let index = (0..basis.len())
            .min_by(|&a, &b| {
                let without = |skip| {
                    basis
                        .iter()
                        .enumerate()
                        .filter(|(i, _)| *i != skip)
                        .map(|(_, v)| v.clone())
                        .collect::<Vec<_>>()
                };
                local_loss(g, &without(a), ridge, true).total_cmp(&local_loss(
                    g,
                    &without(b),
                    ridge,
                    true,
                ))
            })
            .unwrap();
        basis.remove(index);
    }
    basis
}

struct Fit {
    theta: Vec<f64>,
    flux: f64,
    iterations: usize,
    retained: usize,
    loss: f64,
    termination: &'static str,
}

fn fit(problem: &Problem, data: &[f64], config: &Config, method: Method, truth: &[f64]) -> Fit {
    let joint = matches!(
        method,
        Method::Joint | Method::JointBeam | Method::Protected
    );
    // Fixed priors: 1 arcmin pointing, 0.1 Jy science flux, and (when fitted)
    // 1 percent log beam width. Width recovery is therefore prior-dependent.
    // A tiny variance floor keeps the noiseless diagnostic regularized.
    let variance = config.noise.max(1e-6).powi(2);
    let ridge = variance;
    let sky_ridge = variance / 0.1_f64.powi(2);
    let y = problem.train(data);
    let mut theta = if method == Method::Oracle {
        truth.to_vec()
    } else {
        vec![0.0; NPAR + usize::from(method == Method::JointBeam)]
    };
    let mut iterations = 0;
    let mut retained = 0;
    let mut loss = 0.0;
    let mut termination = "not_fitted";
    if !matches!(method, Method::Fixed | Method::Oracle) {
        termination = "iteration_limit";
        for iteration in 0..30 {
            iterations = iteration + 1;
            let (model, mut jac) = problem.bright.evaluate(&theta, 0.0, true);
            let (target, target_jac) = problem.target.evaluate(&theta, 0.0, true);
            let m = problem.train(&model);
            let t = problem.train(&target);
            let r: Vec<_> = y.iter().zip(&m).map(|(y, m)| y - m).collect();
            let flux = if joint {
                dot(&t, &r) / (dot(&t, &t) + sky_ridge)
            } else {
                0.0
            };
            for (row, tr) in jac.iter_mut().zip(target_jac) {
                for (j, tj) in row.iter_mut().zip(tr) {
                    *j += flux * tj;
                }
            }
            let jac = problem.jac_train(&jac);
            let g = geometry(&jac, &t, sky_ridge, joint);
            let residual: Vec<_> = r.iter().zip(&t).map(|(r, t)| r - flux * t).collect();
            let mut rhs = jt(&jac, &residual);
            if joint {
                // Include the sky prior gradient in the block elimination.
                let sky_rhs = dot(&t, &residual) - sky_ridge * flux;
                for (i, value) in rhs.iter_mut().enumerate() {
                    *value -= g.cross[i] * sky_rhs / g.denom;
                }
            }
            for (i, value) in rhs.iter_mut().enumerate() {
                *value -= ridge * theta[i];
            }
            let basis = choose_basis(&g, ridge, method, config.budget);
            retained = basis.len();
            loss = local_loss(&g, &basis, ridge, joint);
            let step = reduced_solve(&g, &rhs, &basis, ridge);
            let cost = |th: &[f64]| {
                let m = problem.train(&problem.bright.evaluate(th, 0.0, false).0);
                let t = problem.train(&problem.target.evaluate(th, 0.0, false).0);
                let r: Vec<_> = y.iter().zip(m).map(|(y, m)| y - m).collect();
                let a = if joint {
                    dot(&t, &r) / (dot(&t, &t) + sky_ridge)
                } else {
                    0.0
                };
                r.iter()
                    .zip(t)
                    .map(|(r, t)| (r - a * t).powi(2))
                    .sum::<f64>()
                    + sky_ridge * a * a
                    + ridge * dot(th, th)
            };
            let old_cost = cost(&theta);
            let mut scale = 1.0;
            let mut accepted = false;
            for _ in 0..15 {
                let candidate: Vec<_> = theta
                    .iter()
                    .zip(&step)
                    .map(|(t, d)| t + scale * d)
                    .collect();
                if cost(&candidate) < old_cost {
                    theta = candidate;
                    accepted = true;
                    break;
                }
                scale *= 0.5;
            }
            if !accepted {
                termination = if dot(&step, &step).sqrt() < 1e-6 {
                    "small_step"
                } else {
                    "no_descent"
                };
                break;
            }
            if scale * dot(&step, &step).sqrt() < 1e-6 {
                termination = "small_step";
                break;
            }
        }
    }
    // Recover science flux for every method with the same unpenalized estimator.
    let model = problem.train(&problem.bright.evaluate(&theta, 0.0, false).0);
    let template = problem.train(&problem.target.evaluate(&theta, 0.0, false).0);
    let residual: Vec<_> = y.iter().zip(model).map(|(y, m)| y - m).collect();
    let flux = dot(&residual, &template) / dot(&template, &template);
    Fit {
        theta,
        flux,
        iterations,
        retained,
        loss,
        termination,
    }
}

pub struct ResultRow {
    pub name: &'static str,
    pub flux: f64,
    pub pointing_rmse: f64,
    pub test_rms: f64,
    pub template_transfer: f64,
    pub off_template_transfer: f64,
    pub template_distortion: f64,
    pub off_template_distortion: f64,
    pub local_loss: f64,
    pub retained: usize,
    pub iterations: usize,
    pub theta: Vec<f64>,
    pub termination: &'static str,
}

pub struct Experiment {
    pub config: Config,
    pub truth: Vec<f64>,
    pub rows: Vec<ResultRow>,
    pub max_w: f64,
}

pub fn run(config: Config) -> Result<Experiment, String> {
    config.validate()?;
    let problem = Problem::new();
    let mut pointing_rng = Rng(config.seed ^ 0x12345678);
    let truth: Vec<_> = (0..NPAR)
        .map(|_| config.pointing * pointing_rng.normal())
        .collect();
    let b = problem.bright.evaluate(&truth, config.beam_error, false).0;
    let t = problem
        .truth_target
        .evaluate(&truth, config.beam_error, false)
        .0;
    let probe = problem.probe.evaluate(&truth, config.beam_error, false).0;
    let mut noise_rng = Rng(config.seed ^ 0xabcdef01);
    let data: Vec<_> = b
        .iter()
        .zip(&t)
        .map(|(b, t)| b + config.target_flux * t + config.noise * noise_rng.normal())
        .collect();
    let injection = 0.002; // Jy, finite perturbation with complete recalibration.
    let mut rows = Vec::new();
    for (method, name) in [
        (Method::Fixed, "fixed_beam"),
        (Method::Pointing, "pointing_only"),
        (Method::Joint, "joint_sky"),
        (Method::JointBeam, "joint_beam"),
        (Method::Protected, "protected_modes"),
        (Method::Oracle, "known_pointing"),
    ] {
        let fitted = fit(&problem, &data, &config, method, &truth);
        let m = problem.bright.evaluate(&fitted.theta, 0.0, false).0;
        let target_model = problem.target.evaluate(&fitted.theta, 0.0, false).0;
        let test_residual: Vec<_> = data
            .iter()
            .enumerate()
            .filter(|(i, _)| !problem.bright.samples[i / 2].train)
            .map(|(i, y)| y - m[i] - fitted.flux * target_model[i])
            .collect();
        // Difference of residuals after bright-model subtraction, evaluated in a
        // common truth visibility frame. This is NOT a deconvolved image metric.
        let transfer = |signal: &[f64]| {
            let injected: Vec<_> = data
                .iter()
                .zip(signal)
                .map(|(y, s)| y + injection * s)
                .collect();
            let f2 = fit(&problem, &injected, &config, method, &truth);
            let m2 = problem.bright.evaluate(&f2.theta, 0.0, false).0;
            let delta: Vec<_> = signal
                .iter()
                .enumerate()
                .map(|(i, s)| s - (m2[i] - m[i]) / injection)
                .collect();
            let distortion: f64 = delta.iter().zip(signal).map(|(a, b)| (a - b).powi(2)).sum();
            (
                dot(signal, &delta) / dot(signal, signal),
                (distortion / dot(signal, signal)).sqrt(),
            )
        };
        let (template_transfer, template_distortion) = transfer(&t);
        let (off_template_transfer, off_template_distortion) = transfer(&probe);
        rows.push(ResultRow {
            name,
            flux: fitted.flux,
            pointing_rmse: fitted
                .theta
                .iter()
                .zip(&truth)
                .map(|(x, t)| (x - t).powi(2))
                .sum::<f64>()
                .sqrt()
                / (NPAR as f64).sqrt(),
            test_rms: (dot(&test_residual, &test_residual) / test_residual.len() as f64).sqrt(),
            template_transfer,
            off_template_transfer,
            template_distortion,
            off_template_distortion,
            local_loss: fitted.loss,
            retained: fitted.retained,
            iterations: fitted.iterations,
            theta: fitted.theta,
            termination: fitted.termination,
        });
    }
    let max_w = problem
        .bright
        .samples
        .iter()
        .map(|s| s.uvw[2].abs())
        .fold(0.0_f64, f64::max);
    Ok(Experiment {
        config,
        truth,
        rows,
        max_w,
    })
}

/// Deterministic cross-language fixture; no random noise or fitted solutions.
pub fn pointing_reference_json() -> String {
    pointing_reference_with_stride(5)
}

/// Complete baseline coverage for calibration identifiability experiments.
pub fn pointing_full_reference_json() -> String {
    pointing_reference_with_stride(1)
}

fn pointing_reference_with_stride(stride: usize) -> String {
    let samples: Vec<_> = samples().into_iter().step_by(stride).collect();
    let theta: Vec<_> = (0..NPAR).map(|i| 0.4 * (i as f64).sin()).collect();
    let sky = bright_sky();
    let op = Operator::new(&samples, sky.clone());
    let (model, jac) = op.evaluate(&theta, 0.0, true);
    let rows = samples
        .iter()
        .enumerate()
        .map(|(i, s)| {
            numbers(&[
                s.uvw[0] * C / s.freq,
                s.uvw[1] * C / s.freq,
                s.uvw[2] * C / s.freq,
                s.freq,
                s.p as f64,
                s.q as f64,
                (i * stride / (FREQUENCIES.len() * NANT * (NANT - 1) / 2)) as f64,
                s.angle,
            ])
        })
        .collect::<Vec<_>>()
        .join(",");
    let sources = sky
        .iter()
        .map(|s| numbers(&[s.l, s.m, s.flux, s.alpha]))
        .collect::<Vec<_>>()
        .join(",");
    let jac = jac
        .iter()
        .map(|row| numbers(row))
        .collect::<Vec<_>>()
        .join(",");
    format!(
        "{{\"rows\":[{rows}],\"sources\":[{sources}],\"pointing_arcmin\":{},\"vis_re_im\":{},\"jacobian\":[{jac}],\"antenna_count\":{NANT},\"time_count\":{NTIME}}}",
        numbers(&theta),
        numbers(&model)
    )
}

fn numbers(values: &[f64]) -> String {
    format!(
        "[{}]",
        values
            .iter()
            .map(|v| format!("{v:.12e}"))
            .collect::<Vec<_>>()
            .join(",")
    )
}

impl Experiment {
    /// Stable JSON interface used by the Python wrapper; no external crates.
    pub fn json(&self) -> String {
        let cfg = &self.config;
        let rows = self.rows.iter().map(|r| format!(
            "{{\"method\":\"{}\",\"flux_jy\":{},\"pointing_rmse_arcmin\":{},\"heldout_rms_jy\":{},\"template_transfer\":{},\"off_template_transfer\":{},\"local_loss\":{},\"retained_modes\":{},\"iterations\":{},\"pointing_arcmin\":{},\"template_distortion\":{},\"off_template_distortion\":{},\"termination\":\"{}\",\"fitted_beam_width_error\":{}}}",
            r.name, r.flux, r.pointing_rmse, r.test_rms, r.template_transfer, r.off_template_transfer,
            r.local_loss, r.retained, r.iterations, numbers(&r.theta[..NPAR]), r.template_distortion,
            r.off_template_distortion, r.termination,
            (r.theta.get(NPAR).copied().unwrap_or(0.0) / 100.0).exp() - 1.0)).collect::<Vec<_>>().join(",");
        format!(
            "{{\"schema_version\":1,\"seed\":{},\"noise_jy\":{},\"pointing_sigma_arcmin\":{},\"beam_width_error\":{},\"budget\":{},\"true_flux_jy\":{},\"antenna_count\":{},\"visibility_count\":{},\"training_time_samples\":18,\"test_time_samples\":6,\"max_abs_w\":{},\"true_pointing_arcmin\":{},\"results\":[{}]}}",
            cfg.seed,
            cfg.noise,
            cfg.pointing,
            cfg.beam_error,
            cfg.budget,
            cfg.target_flux,
            NANT,
            NTIME * FREQUENCIES.len() * NANT * (NANT - 1) / 2,
            self.max_w,
            numbers(&self.truth),
            rows
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shared_width_derivative_matches_finite_difference() {
        let op = Operator::new(&samples()[..12], bright_sky());
        let mut theta = vec![0.3; NPAR + 1];
        theta[NPAR] = 2.0;
        let (_, jac) = op.evaluate(&theta, 0.0, true);
        let h = 1e-4;
        theta[NPAR] += h;
        let plus = op.evaluate(&theta, 0.0, false).0;
        theta[NPAR] -= 2.0 * h;
        let minus = op.evaluate(&theta, 0.0, false).0;
        for i in 0..plus.len() {
            assert!(((plus[i] - minus[i]) / (2.0 * h) - jac[i][NPAR]).abs() < 1e-9);
        }
    }

    #[test]
    fn beam_half_power_convention() {
        let freq = 1.28e9;
        let radius = 0.5 * 1.02 * C / freq / 13.5;
        assert!((voltage(radius, 0.0, 0.0, 0.0, freq, 0.0).powi(2) - 0.5).abs() < 1e-12);
    }

    #[test]
    fn uvw_rotation_preserves_baseline_length() {
        let out = uvw(100.0, -300.0, 4.0, 0.8, -0.6);
        assert!((dot(&out, &out) - (100.0_f64.powi(2) + 300.0_f64.powi(2) + 16.0)).abs() < 1e-8);
    }

    #[test]
    fn analytic_pointing_derivatives_match_finite_difference() {
        let samples = samples();
        let op = Operator::new(&samples[..28], bright_sky());
        let mut theta = vec![0.2; NPAR];
        let (_, jac) = op.evaluate(&theta, 0.0, true);
        let h = 1e-4;
        for k in 0..NPAR {
            theta[k] += h;
            let plus = op.evaluate(&theta, 0.0, false).0;
            theta[k] -= 2.0 * h;
            let minus = op.evaluate(&theta, 0.0, false).0;
            theta[k] += h;
            for i in 0..plus.len() {
                assert!(((plus[i] - minus[i]) / (2.0 * h) - jac[i][k]).abs() < 1e-9);
            }
        }
    }

    #[test]
    fn phase_centre_and_baseline_reversal() {
        let mut s = samples()[0].clone();
        let theta = vec![0.0; NPAR];
        let centre = Operator::new(&[s.clone()], vec![source(0.0, 0.0, 1.0)])
            .evaluate(&theta, 0.0, false)
            .0;
        assert!(centre[1].abs() < 1e-14);
        let sky = vec![source(0.4, -0.3, 1.0)];
        let forward = Operator::new(&[s.clone()], sky.clone())
            .evaluate(&theta, 0.0, false)
            .0;
        std::mem::swap(&mut s.p, &mut s.q);
        s.uvw = s.uvw.map(|v| -v);
        let reverse = Operator::new(&[s], sky).evaluate(&theta, 0.0, false).0;
        assert!((forward[0] - reverse[0]).abs() < 1e-14);
        assert!((forward[1] + reverse[1]).abs() < 1e-14);
    }

    #[test]
    fn protected_basis_respects_frozen_linear_budget() {
        let p = Problem::new();
        let theta = vec![0.0; NPAR];
        let jac = p.jac_train(&p.bright.evaluate(&theta, 0.0, true).1);
        let target = p.train(&p.target.evaluate(&theta, 0.0, false).0);
        let g = geometry(&jac, &target, 10.0, true);
        for budget in [0.0, 1e-5, 0.01, 1.0] {
            let basis = choose_basis(&g, 1e-4, Method::Protected, budget);
            assert!(local_loss(&g, &basis, 1e-4, true) <= budget + 1e-12);
        }
    }

    #[test]
    fn recover_noiseless_pointing_with_complete_sky() {
        let p = Problem::new();
        let truth: Vec<_> = (0..NPAR).map(|i| 0.3 * (i as f64).sin()).collect();
        let data = p.bright.evaluate(&truth, 0.0, false).0;
        let config = Config {
            noise: 0.0,
            target_flux: 0.0,
            ..Config::default()
        };
        let fit = fit(&p, &data, &config, Method::Pointing, &truth);
        assert!(
            fit.theta
                .iter()
                .zip(truth)
                .all(|(a, b)| (a - b).abs() < 1e-5)
        );
    }

    #[test]
    fn extended_source_quadrature_agrees_with_finer_reference() {
        let p = Problem::new();
        let theta = vec![0.3; NPAR];
        let fitted_template = p.target.evaluate(&theta, 0.0, false).0;
        let fine = Operator::new(&p.bright.samples, science_sky(31, 0.0))
            .evaluate(&theta, 0.0, false)
            .0;
        let difference: Vec<_> = fitted_template
            .iter()
            .zip(&fine)
            .map(|(a, b)| a - b)
            .collect();
        let relative_error = (dot(&difference, &difference) / dot(&fine, &fine)).sqrt();
        assert!(relative_error < 0.005, "quadrature error {relative_error}");
    }
}
