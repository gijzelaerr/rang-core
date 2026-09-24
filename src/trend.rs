//! Robust scalar phase-gradient guidance, not a physical Jones decomposition.

fn median(values: &mut [f64]) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    values.sort_by(f64::total_cmp);
    let n = values.len();
    Some(if n.is_multiple_of(2) {
        0.5 * values[n / 2 - 1] + 0.5 * values[n / 2]
    } else {
        values[n / 2]
    })
}

fn determinant_phase(g: &[f64]) -> Option<f64> {
    let scale = g.iter().copied().map(f64::abs).fold(0.0, f64::max);
    if !scale.is_finite() || scale == 0.0 || !g.iter().all(|x| x.is_finite()) {
        return None;
    }
    let x: [f64; 8] = std::array::from_fn(|k| g[k] / scale);
    let real = x[0] * x[6] - x[1] * x[7] - x[2] * x[4] + x[3] * x[5];
    let imag = x[0] * x[7] + x[1] * x[6] - x[2] * x[5] - x[3] * x[4];
    (real.hypot(imag) > 1e-10).then(|| imag.atan2(real))
}

/// Median adjacent half-determinant phase gradients, time then frequency.
/// Scalar phase steps must be unaliased: |delta phase| < pi/2. This assumption
/// cannot be certified from wrapped Jones determinants alone. Unsupported fits
/// are NaN, never silently filled. Gap edges >3 median spacings are excluded.
pub fn slopes(
    gains: &[f64],
    valid: &[u8],
    shape: [usize; 3],
    times: &[f64],
    frequencies: &[f64],
) -> Result<(Vec<f64>, Vec<usize>), &'static str> {
    let [nt, nf, na] = shape;
    let n = nt.checked_mul(nf).and_then(|n| n.checked_mul(na));
    if n == Some(0)
        || n.and_then(|n| n.checked_mul(8)) != Some(gains.len())
        || n != Some(valid.len())
        || times.len() != nt
        || frequencies.len() != nf
        || valid.iter().any(|x| *x > 1)
        || [times, frequencies].iter().any(|x| {
            !x.iter().all(|v| v.is_finite())
                || x.windows(2)
                    .any(|p| p[1] <= p[0] || !(p[1] - p[0]).is_finite())
        })
    {
        return Err("invalid trend buffers/coordinates");
    }
    let mut phases = Vec::with_capacity(valid.len());
    for (i, v) in valid.iter().enumerate() {
        phases.push(if *v == 1 {
            determinant_phase(&gains[8 * i..8 * i + 8])
        } else {
            None
        });
    }
    let mut result = vec![f64::NAN; 2 * na];
    let mut counts = vec![0; 2 * na];
    for (axis, coordinates) in [times, frequencies].iter().enumerate() {
        let mut gaps: Vec<_> = coordinates.windows(2).map(|p| p[1] - p[0]).collect();
        let Some(spacing) = median(&mut gaps) else {
            continue;
        };
        for a in 0..na {
            let mut gradients = Vec::new();
            for t in 0..nt {
                for f in 0..nf {
                    let k = if axis == 0 { t } else { f };
                    if k + 1 == coordinates.len() {
                        continue;
                    }
                    let gap = coordinates[k + 1] - coordinates[k];
                    if gap > 3.0 * spacing {
                        continue;
                    }
                    let i = (t * nf + f) * na + a;
                    let j = i + if axis == 0 { nf * na } else { na };
                    if let (Some(left), Some(right)) = (phases[i], phases[j]) {
                        let delta = right - left;
                        let gradient = 0.5 * delta.sin().atan2(delta.cos()) / gap;
                        if gradient.is_finite() {
                            gradients.push(gradient);
                        }
                    }
                }
            }
            counts[2 * a + axis] = gradients.len();
            if gradients.len() >= if axis == 0 { 2 } else { 4 } {
                result[2 * a + axis] = median(&mut gradients).unwrap();
            }
        }
    }
    Ok((result, counts))
}

/// # Safety
/// Nonoverlapping aligned buffers: gains8*nt*nf*na, validnt*nf*na, timesnt,
/// frequenciesnf, output2*na doubles, counts2*na usize; caller owns lifetimes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_trend_slopes(
    nt: usize,
    nf: usize,
    na: usize,
    gains: *const f64,
    valid: *const u8,
    times: *const f64,
    frequencies: *const f64,
    output: *mut f64,
    counts: *mut usize,
) -> i32 {
    let Some(n) = nt.checked_mul(nf).and_then(|n| n.checked_mul(na)) else {
        return 1;
    };
    if n == 0
        || n > isize::MAX as usize / (8 * size_of::<f64>())
        || [gains, times, frequencies, output.cast_const()]
            .iter()
            .any(|p| p.is_null())
        || valid.is_null()
        || counts.is_null()
    {
        return 1;
    }
    let result = std::panic::catch_unwind(|| {
        // SAFETY: bounded sizes above, live nonoverlapping buffers are caller contract.
        unsafe {
            slopes(
                std::slice::from_raw_parts(gains, 8 * n),
                std::slice::from_raw_parts(valid, n),
                [nt, nf, na],
                std::slice::from_raw_parts(times, nt),
                std::slice::from_raw_parts(frequencies, nf),
            )
        }
    });
    match result {
        Ok(Ok((values, samples))) => {
            // SAFETY: output/count lengths2*na and nonoverlap are caller contract.
            unsafe {
                std::ptr::copy_nonoverlapping(values.as_ptr(), output, 2 * na);
                std::ptr::copy_nonoverlapping(samples.as_ptr(), counts, 2 * na);
            }
            0
        }
        Ok(Err(_)) => 1,
        Err(_) => 2,
    }
}

#[cfg(test)]
mod tests {
    use super::slopes;

    #[test]
    fn recovers_unaliased_scalar_trend_with_complex_leakage() {
        let mut gains = Vec::new();
        for t in 0..3 {
            for f in 0..6 {
                let phase = 0.2 * t as f64 + 0.12 * f as f64;
                for (r, i) in [(1., 0.), (0.1, 0.02), (0.1, -0.02), (1.2, 0.)] {
                    gains.extend([
                        r * phase.cos() - i * phase.sin(),
                        r * phase.sin() + i * phase.cos(),
                    ]);
                }
            }
        }
        let (fit, counts) = slopes(
            &gains,
            &[1; 18],
            [3, 6, 1],
            &[0., 1., 2.],
            &[0., 1., 2., 3., 4., 5.],
        )
        .unwrap();
        assert!((fit[0] - 0.2).abs() < 1e-14);
        assert!((fit[1] - 0.12).abs() < 1e-14);
        assert_eq!(counts, [12, 15]);
    }

    #[test]
    fn missing_singular_and_gap_support_are_not_interpolated() {
        let gains = vec![0.; 18 * 8];
        let (fit, counts) = slopes(
            &gains,
            &[1; 18],
            [3, 6, 1],
            &[0., 1., 100.],
            &[0., 1., 2., 3., 4., 5.],
        )
        .unwrap();
        assert!(fit.iter().all(|x| x.is_nan()));
        assert_eq!(counts, [0, 0]);
        assert!(slopes(&[], &[], [0, 0, 0], &[], &[]).is_err());
    }
}
