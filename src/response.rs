//! Gauge-aware, real full-Jones TRAIN normal equations and deletion response.
//!
//! Parameters are antenna-major XX/XY/YX/YY, adjacent real/imaginary; each
//! station has eight parameters. Visibility rows use the same adjacent order.
//! These are Gauss--Newton approximations, not a replacement for QuartiCal.

use crate::linalg::{Matrix, eigen_ql, zeros};

pub const PARAMETERS: usize = 32;
pub const DIAGNOSTICS: usize = 10;
pub type NormalBlocks = (Vec<f64>, Vec<f64>, Vec<usize>);

#[derive(Clone, Copy, Default)]
struct Complex {
    re: f64,
    im: f64,
}

impl Complex {
    fn add(self, other: Self) -> Self {
        Self {
            re: self.re + other.re,
            im: self.im + other.im,
        }
    }
    fn mul(self, other: Self) -> Self {
        Self {
            re: self.re * other.re - self.im * other.im,
            im: self.re * other.im + self.im * other.re,
        }
    }
    fn conjugate(self) -> Self {
        Self {
            re: self.re,
            im: -self.im,
        }
    }
}

type Jones = [Complex; 4];

fn unpack(input: &[f64]) -> Jones {
    std::array::from_fn(|i| Complex {
        re: input[2 * i],
        im: input[2 * i + 1],
    })
}

fn multiply(a: &Jones, b: &Jones) -> Jones {
    std::array::from_fn(|entry| {
        let (row, col) = (entry / 2, entry % 2);
        a[2 * row].mul(b[col]).add(a[2 * row + 1].mul(b[2 + col]))
    })
}

fn adjoint(a: &Jones) -> Jones {
    std::array::from_fn(|entry| a[2 * (entry % 2) + entry / 2].conjugate())
}

/// One baseline's eight real output rows and sixteen local real parameters.
/// In particular, the imaginary q derivative has a MINUS sign from conjugation.
pub fn jacobian(gp: &[f64], gq: &[f64], model: &[f64]) -> Result<Vec<f64>, &'static str> {
    if gp.len() != 8
        || gq.len() != 8
        || model.len() != 8
        || !gp.iter().chain(gq).chain(model).all(|x| x.is_finite())
    {
        return Err("finite 2x2 complex Jones matrices required");
    }
    let (gp, gq, model) = (unpack(gp), unpack(gq), unpack(model));
    let left = multiply(&gp, &model);
    let right = multiply(&model, &adjoint(&gq));
    let mut out = vec![0.; 8 * 16];
    for entry in 0..4 {
        let mut basis = [Complex::default(); 4];
        basis[entry].re = 1.;
        let derivatives = [multiply(&basis, &right), multiply(&left, &adjoint(&basis))];
        for (station, derivative) in derivatives.iter().enumerate() {
            for (output, value) in derivative.iter().enumerate() {
                let column = station * 8 + entry * 2;
                out[2 * output * 16 + column] = value.re;
                out[(2 * output + 1) * 16 + column] = value.im;
                let sign = if station == 0 { 1. } else { -1. };
                out[2 * output * 16 + column + 1] = -sign * value.im;
                out[(2 * output + 1) * 16 + column + 1] = sign * value.re;
            }
        }
    }
    Ok(out)
}

/// H=Re(J^H W J), b=Re(J^H W r), no invented or renormalized weights.
#[allow(clippy::too_many_arguments)]
pub fn normals(
    gain_bins: usize,
    gains: &[f64],
    models: &[f64],
    residuals: &[f64],
    weights: &[f64],
    p: &[usize],
    q: &[usize],
    bins: &[usize],
) -> Result<NormalBlocks, &'static str> {
    let samples = bins.len();
    if gain_bins == 0
        || gain_bins.checked_mul(PARAMETERS) != Some(gains.len())
        || samples.checked_mul(8) != Some(models.len())
        || residuals.len() != models.len()
        || samples.checked_mul(4) != Some(weights.len())
        || p.len() != samples
        || q.len() != samples
        || !models.iter().chain(residuals).all(|x| x.is_finite())
        || !weights.iter().all(|x| x.is_finite() && *x > 0.)
    {
        return Err("invalid TRAIN normal-equation inputs");
    }
    let size = gain_bins
        .checked_mul(PARAMETERS * PARAMETERS)
        .ok_or("normal-equation size overflow")?;
    let mut h = vec![0.; size];
    let mut b = vec![0.; gain_bins * PARAMETERS];
    let mut counts = vec![0; gain_bins];
    for sample in 0..samples {
        let (bin, p, q) = (bins[sample], p[sample], q[sample]);
        if bin >= gain_bins || p >= 4 || q >= 4 || p == q {
            return Err("invalid cross-baseline/bin");
        }
        let gain = &gains[bin * PARAMETERS..(bin + 1) * PARAMETERS];
        let j = jacobian(
            &gain[p * 8..(p + 1) * 8],
            &gain[q * 8..(q + 1) * 8],
            &models[sample * 8..(sample + 1) * 8],
        )?;
        let columns: [usize; 16] =
            std::array::from_fn(|i| if i < 8 { p * 8 + i } else { q * 8 + i - 8 });
        for output in 0..8 {
            let weight = weights[4 * sample + output / 2];
            let residual = residuals[8 * sample + output];
            for (i, &column) in columns.iter().enumerate() {
                let value = j[output * 16 + i];
                b[bin * PARAMETERS + column] += weight * value * residual;
                for (k, &other) in columns.iter().enumerate() {
                    h[(bin * PARAMETERS + column) * PARAMETERS + other] +=
                        weight * value * j[output * 16 + k];
                }
            }
        }
        counts[bin] += 1;
    }
    if !h.iter().chain(&b).all(|x| x.is_finite()) {
        return Err("normal-equation overflow");
    }
    Ok((h, b, counts))
}

fn gauge_basis(gains: &[f64], active: &[u8]) -> Result<Matrix, &'static str> {
    let mut skew = [[Complex::default(); 4]; 4];
    skew[0][0].im = 1.;
    skew[1][3].im = 1.;
    skew[2][1].re = 1.;
    skew[2][2].re = -1.;
    skew[3][1].im = 1.;
    skew[3][2].im = 1.;
    let mut basis: Matrix = Vec::new();
    for generator in &skew {
        let mut column = vec![0.; PARAMETERS];
        for antenna in 0..4 {
            if active[antenna] == 0 {
                continue;
            }
            let tangent = multiply(&unpack(&gains[antenna * 8..(antenna + 1) * 8]), generator);
            for (entry, value) in tangent.iter().enumerate() {
                column[antenna * 8 + 2 * entry] = value.re;
                column[antenna * 8 + 2 * entry + 1] = value.im;
            }
        }
        let initial = column.iter().map(|x| x * x).sum::<f64>().sqrt();
        // Reorthogonalized modified Gram--Schmidt, only four gauge vectors.
        for _ in 0..2 {
            for previous in &basis {
                let product: f64 = column.iter().zip(previous).map(|(a, b)| a * b).sum();
                for (x, q) in column.iter_mut().zip(previous) {
                    *x -= product * q;
                }
            }
        }
        let norm = column.iter().map(|x| x * x).sum::<f64>().sqrt();
        if !norm.is_finite() || norm <= 1e-12 * initial.max(1e-30) {
            return Err("singular U(2) gauge basis");
        }
        for x in &mut column {
            *x /= norm;
        }
        basis.push(column);
    }
    Ok(basis)
}

type Solver = fn(&Matrix) -> Option<(Vec<f64>, Matrix)>;

/// Householder + implicit QL (task P4, research/p4-eigen.md); the classical
/// Jacobi solver `linalg::eigen` is kept for the pointing toy and the A/B.
fn checked_eigen(h: &Matrix) -> Result<(Vec<f64>, Matrix), &'static str> {
    checked_eigen_with(h, eigen_ql)
}

fn checked_eigen_with(h: &Matrix, solver: Solver) -> Result<(Vec<f64>, Matrix), &'static str> {
    let (values, vectors) = solver(h).ok_or("eigensystem residual failed")?;
    let scale = h
        .iter()
        .flatten()
        .fold(0.0_f64, |a, b| a.max(b.abs()))
        .max(1e-30);
    for (k, &value) in values.iter().enumerate() {
        for (i, row) in h.iter().enumerate() {
            let actual: f64 = row.iter().enumerate().map(|(j, x)| x * vectors[j][k]).sum();
            if (actual - value * vectors[i][k]).abs() > 1e-9 * scale {
                return Err("eigensystem residual failed");
            }
        }
    }
    Ok((values, vectors))
}

fn project(h: &Matrix, b: &[f64], q: &Matrix) -> (Matrix, Vec<f64>) {
    let mut p = zeros(PARAMETERS, PARAMETERS);
    for (i, row) in p.iter_mut().enumerate() {
        row[i] = 1.;
        for (j, x) in row.iter_mut().enumerate() {
            *x -= q.iter().map(|v| v[i] * v[j]).sum::<f64>();
        }
    }
    let mut hp = zeros(PARAMETERS, PARAMETERS);
    for (i, row) in h.iter().enumerate() {
        for (j, x) in hp[i].iter_mut().enumerate() {
            *x = row.iter().enumerate().map(|(k, a)| a * p[k][j]).sum();
        }
    }
    let mut out = zeros(PARAMETERS, PARAMETERS);
    let mut pb = vec![0.; PARAMETERS];
    for (i, row) in p.iter().enumerate() {
        pb[i] = row.iter().zip(b).map(|(a, b)| a * b).sum();
        for (j, x) in out[i].iter_mut().enumerate() {
            *x = row.iter().enumerate().map(|(k, a)| a * hp[k][j]).sum();
        }
    }
    for i in 0..PARAMETERS {
        let (earlier, current) = out.split_at_mut(i);
        for (j, previous) in earlier.iter_mut().enumerate() {
            let mean = (current[0][j] + previous[i]) * 0.5;
            current[0][j] = mean;
            previous[i] = mean;
        }
    }
    (out, pb)
}

/// Anchored kept-minus-full GN response in the baseline horizontal gauge.
/// Fixed damping=1e-6 and rank cutoff=1e-10 times the full largest eigenvalue.
pub fn anchored_step(
    full_h: &[f64],
    full_b: &[f64],
    drop_h: &[f64],
    drop_b: &[f64],
    gains: &[f64],
    active: &[u8],
) -> Result<(Vec<f64>, [f64; DIAGNOSTICS]), &'static str> {
    if full_h.len() != PARAMETERS * PARAMETERS
        || drop_h.len() != full_h.len()
        || full_b.len() != PARAMETERS
        || drop_b.len() != PARAMETERS
        || gains.len() != PARAMETERS
        || active.len() != 4
        || !full_h
            .iter()
            .chain(drop_h)
            .chain(full_b)
            .chain(drop_b)
            .chain(gains)
            .all(|x| x.is_finite())
        || active.iter().any(|x| *x > 1)
    {
        return Err("invalid response block");
    }
    let n_active = active.iter().filter(|x| **x != 0).count();
    if n_active < 2 {
        return Err("underidentified full curvature");
    }
    let full: Matrix = full_h
        .chunks_exact(PARAMETERS)
        .map(|r| r.to_vec())
        .collect();
    let kept: Matrix = full_h
        .chunks_exact(PARAMETERS)
        .zip(drop_h.chunks_exact(PARAMETERS))
        .map(|(a, b)| a.iter().zip(b).map(|(a, b)| a - b).collect())
        .collect();
    let scale = full_h
        .iter()
        .fold(0.0_f64, |a, b| a.max(b.abs()))
        .max(1e-30);
    for h in [&full, &kept] {
        for (i, row) in h.iter().enumerate() {
            for (j, previous) in h.iter().take(i).enumerate() {
                if (row[j] - previous[i]).abs() > 1e-10 * scale {
                    return Err("asymmetric curvature");
                }
            }
        }
    }
    let q = gauge_basis(gains, active)?;
    let mut gauge_null = 0.0_f64;
    for v in &q {
        for row in &full {
            let value: f64 = row.iter().zip(v).map(|(a, b)| a * b).sum();
            gauge_null = gauge_null.max(value.abs() / scale);
        }
    }
    if gauge_null > 1e-8 {
        return Err("model does not admit common U(2) gauge");
    }
    let kept_b: Vec<f64> = full_b.iter().zip(drop_b).map(|(a, b)| a - b).collect();
    let (full, pfull) = project(&full, full_b, &q);
    let (kept, pkept) = project(&kept, &kept_b, &q);
    let (fv, fu) = checked_eigen(&full)?;
    let (kv, ku) = checked_eigen(&kept)?;
    let largest = fv[0];
    if !largest.is_finite() || largest <= 0. {
        return Err("underidentified full curvature");
    }
    let cutoff = 1e-10 * largest;
    let damping = 1e-6 * largest;
    if fv.iter().chain(&kv).any(|v| *v < -cutoff) {
        return Err("nonpositive retained curvature");
    }
    let full_rank = fv.iter().filter(|v| **v > cutoff).count();
    let kept_rank = kv.iter().filter(|v| **v > cutoff).count();
    if full_rank != 8 * n_active - 4 {
        return Err("underidentified full curvature");
    }
    if kept_rank < full_rank {
        return Err("retained curvature loses rank");
    }
    let solve = |values: &[f64], vectors: &Matrix, b: &[f64]| {
        let mut out = vec![0.; PARAMETERS];
        for (k, &value) in values.iter().enumerate() {
            if value <= cutoff {
                continue;
            }
            let coefficient = b
                .iter()
                .enumerate()
                .map(|(i, b)| b * vectors[i][k])
                .sum::<f64>()
                / (value + damping);
            for (i, x) in out.iter_mut().enumerate() {
                *x += coefficient * vectors[i][k];
            }
        }
        out
    };
    let a = solve(&fv, &fu, &pfull);
    let b = solve(&kv, &ku, &pkept);
    let delta: Vec<f64> = b.iter().zip(&a).map(|(b, a)| b - a).collect();
    let mut relative = 0.0_f64;
    for (antenna, &is_active) in active.iter().enumerate() {
        if is_active == 0 {
            continue;
        }
        let start = antenna * 8;
        let norm = gains[start..start + 8]
            .iter()
            .map(|x| x * x)
            .sum::<f64>()
            .sqrt();
        let change = delta[start..start + 8]
            .iter()
            .map(|x| x * x)
            .sum::<f64>()
            .sqrt();
        if norm <= 1e-30 {
            return Err("singular station gain");
        }
        relative = relative.max(change / norm);
    }
    if !delta.iter().all(|x| x.is_finite()) {
        return Err("response overflow");
    }
    let smallest = kv
        .iter()
        .copied()
        .filter(|v| *v > cutoff)
        .fold(f64::INFINITY, f64::min);
    Ok((
        delta,
        [
            full_rank as f64,
            kept_rank as f64,
            4.,
            largest,
            smallest,
            largest / smallest,
            damping,
            relative,
            pfull.iter().map(|x| x * x).sum::<f64>().sqrt(),
            gauge_null,
        ],
    ))
}

/// # Safety
/// The caller provides 8 readable doubles for each Jones input and 128 writable
/// doubles for output; output must not overlap inputs.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_response_jacobian(
    gp: *const f64,
    gq: *const f64,
    model: *const f64,
    output: *mut f64,
) -> i32 {
    if gp.is_null() || gq.is_null() || model.is_null() || output.is_null() {
        return 1;
    }
    let result = std::panic::catch_unwind(|| {
        let j = jacobian(
            unsafe { std::slice::from_raw_parts(gp, 8) },
            unsafe { std::slice::from_raw_parts(gq, 8) },
            unsafe { std::slice::from_raw_parts(model, 8) },
        )?;
        unsafe {
            std::ptr::copy_nonoverlapping(j.as_ptr(), output, j.len());
        }
        Ok::<(), &str>(())
    });
    match result {
        Ok(Ok(())) => 0,
        Ok(Err(_)) => 1,
        Err(_) => 2,
    }
}

/// # Safety
/// Input lengths: gains=32*bins, model/residual=8*samples, weights=4*samples,
/// p/q/bin_index=samples. Outputs: h=1024*bins,b=32*bins,counts=bins.
/// All pointers must be valid and output buffers must not overlap any inputs.
#[unsafe(no_mangle)]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn rang_response_normals(
    samples: usize,
    gain_bins: usize,
    gains: *const f64,
    models: *const f64,
    residuals: *const f64,
    weights: *const f64,
    p: *const usize,
    q: *const usize,
    bins: *const usize,
    h: *mut f64,
    b: *mut f64,
    counts: *mut usize,
) -> i32 {
    if gain_bins == 0
        || gains.is_null()
        || h.is_null()
        || b.is_null()
        || counts.is_null()
        || (samples > 0
            && (models.is_null()
                || residuals.is_null()
                || weights.is_null()
                || p.is_null()
                || q.is_null()
                || bins.is_null()))
    {
        return 1;
    }
    if gain_bins
        .checked_mul(1024)
        .is_none_or(|n| n > isize::MAX as usize / 8)
        || samples
            .checked_mul(8)
            .is_none_or(|n| n > isize::MAX as usize / 8)
    {
        return 1;
    }
    let result = std::panic::catch_unwind(|| {
        let real = |pointer: *const f64, len: usize| {
            if len == 0 {
                &[][..]
            } else {
                unsafe { std::slice::from_raw_parts(pointer, len) }
            }
        };
        let integer = |pointer: *const usize| {
            if samples == 0 {
                &[][..]
            } else {
                unsafe { std::slice::from_raw_parts(pointer, samples) }
            }
        };
        let (hh, bb, cc) = normals(
            gain_bins,
            real(gains, gain_bins * 32),
            real(models, samples * 8),
            real(residuals, samples * 8),
            real(weights, samples * 4),
            integer(p),
            integer(q),
            integer(bins),
        )?;
        unsafe {
            std::ptr::copy_nonoverlapping(hh.as_ptr(), h, hh.len());
            std::ptr::copy_nonoverlapping(bb.as_ptr(), b, bb.len());
            std::ptr::copy_nonoverlapping(cc.as_ptr(), counts, cc.len());
        }
        Ok::<(), &str>(())
    });
    match result {
        Ok(Ok(())) => 0,
        Ok(Err(_)) => 1,
        Err(_) => 2,
    }
}

/// # Safety
/// full_h/drop_h=1024 doubles,full_b/drop_b/gains=32 doubles,active=4 bytes;
/// delta=32 and diagnostics=10 writable doubles. Outputs do not overlap inputs.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_response_step(
    full_h: *const f64,
    full_b: *const f64,
    drop_h: *const f64,
    drop_b: *const f64,
    gains: *const f64,
    active: *const u8,
    delta: *mut f64,
    diagnostics: *mut f64,
) -> i32 {
    if full_h.is_null()
        || full_b.is_null()
        || drop_h.is_null()
        || drop_b.is_null()
        || gains.is_null()
        || active.is_null()
        || delta.is_null()
        || diagnostics.is_null()
    {
        return 1;
    }
    let result = std::panic::catch_unwind(|| {
        let real = |p: *const f64, n| unsafe { std::slice::from_raw_parts(p, n) };
        let (d, info) = anchored_step(
            real(full_h, 1024),
            real(full_b, 32),
            real(drop_h, 1024),
            real(drop_b, 32),
            real(gains, 32),
            unsafe { std::slice::from_raw_parts(active, 4) },
        )?;
        unsafe {
            std::ptr::copy_nonoverlapping(d.as_ptr(), delta, 32);
            std::ptr::copy_nonoverlapping(info.as_ptr(), diagnostics, 10);
        }
        Ok::<(), &str>(())
    });
    match result {
        Ok(Ok(())) => 0,
        Ok(Err(message)) => match message {
            "underidentified full curvature" => 3,
            "retained curvature loses rank" => 4,
            "nonpositive retained curvature" => 5,
            "model does not admit common U(2) gauge" => 6,
            _ => 1,
        },
        Err(_) => 2,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn imaginary_q_derivative_has_conjugate_sign() {
        let id = [1., 0., 0., 0., 0., 0., 1., 0.];
        let j = jacobian(&id, &id, &id).unwrap();
        assert_eq!(j[16 + 1], 1.);
        assert_eq!(j[16 + 9], -1.);
    }
    #[test]
    fn empty_normals_are_zero_and_bad_weights_rejected() {
        assert!(
            normals(1, &[0.; 32], &[], &[], &[], &[], &[], &[])
                .unwrap()
                .0
                .iter()
                .all(|x| *x == 0.)
        );
        assert!(normals(1, &[0.; 32], &[0.; 8], &[0.; 8], &[0.; 4], &[0], &[1], &[0]).is_err());
    }
    #[test]
    fn thirty_two_dimensional_eigen_residual() {
        let mut h = zeros(32, 32);
        for (i, row) in h.iter_mut().enumerate() {
            for (j, x) in row.iter_mut().enumerate() {
                *x = if i == j {
                    3. + i as f64 / 32.
                } else {
                    0.01 * ((i + j) as f64).sin()
                };
            }
        }
        assert!(checked_eigen(&h).is_ok());
    }

    fn jacobi(h: &Matrix) -> Option<(Vec<f64>, Matrix)> {
        Some(crate::linalg::eigen(h))
    }

    struct Lcg(u64);
    impl Lcg {
        fn next(&mut self) -> f64 {
            self.0 = self
                .0
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            ((self.0 >> 11) as f64 / (1u64 << 53) as f64) * 2.0 - 1.0
        }
    }

    /// Survey-like block: TRAIN normals of a scalar (gauge-preserving) model
    /// at a random gain point, `stations` active, `samples` per baseline.
    fn survey_block(
        rng: &mut Lcg,
        stations: usize,
        samples: usize,
    ) -> (Vec<f64>, Vec<f64>, [u8; 4]) {
        let mut gains = vec![0.; PARAMETERS];
        for antenna in 0..4 {
            for (k, x) in gains[antenna * 8..antenna * 8 + 8].iter_mut().enumerate() {
                *x = if k == 0 || k == 6 { 1. } else { 0. } + 0.1 * rng.next();
            }
        }
        let (mut models, mut p, mut q) = (Vec::new(), Vec::new(), Vec::new());
        for a in 0..stations {
            for b in a + 1..stations {
                for _ in 0..samples {
                    let (re, im) = (1. + 0.5 * rng.next(), 0.5 * rng.next());
                    models.extend([re, im, 0., 0., 0., 0., re, im]);
                    p.push(a);
                    q.push(b);
                }
            }
        }
        let n = p.len();
        let (h, _, _) = normals(
            1,
            &gains,
            &models,
            &vec![0.; 8 * n],
            &vec![1.; 4 * n],
            &p,
            &q,
            &vec![0; n],
        )
        .unwrap();
        let mut active = [0u8; 4];
        active[..stations].fill(1);
        (h, gains, active)
    }

    fn rank_and_margins(values: &[f64]) -> (usize, f64, f64) {
        let cutoff = 1e-10 * values[0];
        let rank = values.iter().filter(|v| **v > cutoff).count();
        let above = values
            .iter()
            .filter(|v| **v > cutoff)
            .fold(f64::INFINITY, |a, v| a.min(v / cutoff));
        let below = values
            .iter()
            .filter(|v| **v <= cutoff)
            .fold(0.0_f64, |a, v| a.max(v.abs() / cutoff));
        (rank, above, below)
    }

    #[test]
    fn projected_survey_blocks_have_identical_rank_and_spectrum_under_ql() {
        let mut rng = Lcg(20261030);
        for stations in 2..=4 {
            for samples in [1, 2, 5] {
                let (h, gains, active) = survey_block(&mut rng, stations, samples);
                let full: Matrix = h.chunks_exact(PARAMETERS).map(|r| r.to_vec()).collect();
                let basis = gauge_basis(&gains, &active).unwrap();
                let (projected, _) = project(&full, &[0.; PARAMETERS], &basis);
                let (dq, _) = checked_eigen(&projected).unwrap();
                let (dj, _) = checked_eigen_with(&projected, jacobi).unwrap();
                let (rq, aq, bq) = rank_and_margins(&dq);
                let (rj, _, _) = rank_and_margins(&dj);
                assert_eq!(rq, rj);
                // A scalar model leaves two stations at rank 8 against the
                // required 12 (research/flagging-luno-support.md).
                let required = 8 * stations - 4;
                let zero = [0.; PARAMETERS];
                let step = anchored_step(&h, &zero, &[0.; 1024], &zero, &gains, &active);
                if stations == 2 {
                    assert_eq!(rq, 8);
                    assert_eq!(step.unwrap_err(), "underidentified full curvature");
                } else {
                    assert_eq!(rq, required);
                    assert_eq!(step.unwrap().1[0], required as f64);
                }
                assert!(aq > 1e3 && bq < 1e-3, "margins {aq} {bq}");
                assert!(
                    dq.iter()
                        .zip(&dj)
                        .all(|(a, b)| (a - b).abs() <= 1e-12 * dj[0])
                );
            }
        }
    }

    /// Task P4 bin-for-bin audit on recorded calls (research/p4-eigen.md).
    /// P4_DUMP holds records of 2084 little-endian f64 (full_h 1024, drop_h
    /// 1024, gains 32, active 4); one TSV row per record is written to P4_OUT.
    /// Margins are factors relative to the cutoff 1e-10 times Jacobi's
    /// largest full eigenvalue, over both solvers and both matrices.
    #[test]
    #[ignore]
    fn p4_dump_audit() {
        let (Ok(dump), Ok(out)) = (std::env::var("P4_DUMP"), std::env::var("P4_OUT")) else {
            return;
        };
        let bytes = std::fs::read(dump).unwrap();
        let values: Vec<f64> = bytes
            .chunks_exact(8)
            .map(|b| f64::from_le_bytes(b.try_into().unwrap()))
            .collect();
        let mut rows = vec![
            [
                "index",
                "path",
                "full_rank_jacobi",
                "full_rank_ql",
                "kept_rank_jacobi",
                "kept_rank_ql",
                "max_eig_diff_rel",
                "min_retained_over_cutoff",
                "max_discarded_over_cutoff",
                "min_eig_over_cutoff",
            ]
            .join("\t"),
        ];
        let empty = "\t".repeat(8);
        for (index, record) in values.chunks_exact(2084).enumerate() {
            let (full_h, rest) = record.split_at(1024);
            let (drop_h, rest) = rest.split_at(1024);
            let (gains, active) = rest.split_at(32);
            let active: Vec<u8> = active.iter().map(|x| *x as u8).collect();
            let full: Matrix = full_h
                .chunks_exact(PARAMETERS)
                .map(|r| r.to_vec())
                .collect();
            let kept: Matrix = full_h
                .chunks_exact(PARAMETERS)
                .zip(drop_h.chunks_exact(PARAMETERS))
                .map(|(a, b)| a.iter().zip(b).map(|(a, b)| a - b).collect())
                .collect();
            let n_active = active.iter().filter(|x| **x != 0).count();
            let scale = full_h
                .iter()
                .fold(0.0_f64, |a, b| a.max(b.abs()))
                .max(1e-30);
            let basis = if n_active < 2 {
                Err("too few stations")
            } else {
                gauge_basis(gains, &active)
            };
            let Ok(basis) = basis else {
                rows.push(format!("{index}\tbefore_eigen{empty}"));
                continue;
            };
            let mut gauge_null = 0.0_f64;
            for v in &basis {
                for row in &full {
                    let value: f64 = row.iter().zip(v).map(|(a, b)| a * b).sum();
                    gauge_null = gauge_null.max(value.abs() / scale);
                }
            }
            if gauge_null > 1e-8 {
                rows.push(format!("{index}\tgauge_null{empty}"));
                continue;
            }
            let (full, _) = project(&full, &[0.; PARAMETERS], &basis);
            let (kept, _) = project(&kept, &[0.; PARAMETERS], &basis);
            let fj = crate::linalg::eigen(&full).0;
            let kj = crate::linalg::eigen(&kept).0;
            let (Some((fq, _)), Some((kq, _))) = (eigen_ql(&full), eigen_ql(&kept)) else {
                rows.push(format!("{index}\tql_failed{empty}"));
                continue;
            };
            let rank = |v: &[f64], largest: f64| v.iter().filter(|x| **x > 1e-10 * largest).count();
            let diff = fj
                .iter()
                .zip(&fq)
                .chain(kj.iter().zip(&kq))
                .fold(0.0_f64, |a, (x, y)| a.max((x - y).abs()))
                / fj[0].abs().max(1e-300);
            let cutoff = 1e-10 * fj[0];
            let all = || fj.iter().chain(&kj).chain(&fq).chain(&kq);
            let above = all()
                .filter(|v| **v > cutoff)
                .fold(f64::INFINITY, |a, v| a.min(v / cutoff));
            let below = all()
                .filter(|v| **v <= cutoff)
                .fold(0.0_f64, |a, v| a.max(v.abs() / cutoff));
            let lowest = all().fold(f64::INFINITY, |a, v| a.min(v / cutoff));
            rows.push(format!(
                "{index}\teigen\t{}\t{}\t{}\t{}\t{diff:e}\t{above:e}\t{below:e}\t{lowest:e}",
                rank(&fj, fj[0]),
                rank(&fq, fq[0]),
                rank(&kj, fj[0]),
                rank(&kq, fq[0]),
            ));
        }
        std::fs::write(out, rows.join("\n") + "\n").unwrap();
    }
}
