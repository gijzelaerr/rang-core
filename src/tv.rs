//! Mask-aware anisotropic full-Jones TV. Four complex entries use eight doubles.

pub fn edges(
    gains: &[f64],
    valid: &[u8],
    shape: [usize; 3],
    time_weights: &[f64],
    freq_weights: &[f64],
) -> Result<Vec<f64>, &'static str> {
    let [nt, nf, na] = shape;
    let n = nt
        .checked_mul(nf)
        .and_then(|v| v.checked_mul(na))
        .ok_or("shape overflow")?;
    if n == 0
        || n.checked_mul(8) != Some(gains.len())
        || valid.len() != n
        || time_weights.len() != nt - 1
        || freq_weights.len() != nf - 1
        || !time_weights
            .iter()
            .chain(freq_weights)
            .all(|w| w.is_finite() && *w >= 0.0)
    {
        return Err("invalid TV buffers or weights");
    }
    for i in 0..n {
        if valid[i] > 0 && !gains[8 * i..8 * i + 8].iter().all(|v| v.is_finite()) {
            return Err("nonfinite valid gain");
        }
    }
    let mut out = vec![f64::NAN; 2 * n];
    for (t, &tw) in time_weights.iter().chain(std::iter::once(&0.0)).enumerate() {
        for (f, &fw) in freq_weights.iter().chain(std::iter::once(&0.0)).enumerate() {
            for a in 0..na {
                let i = (t * nf + f) * na + a;
                let mut difference = |j: usize, weight: f64, output: usize| {
                    if valid[i] == 0 || valid[j] == 0 || weight == 0.0 {
                        return;
                    }
                    // hypot avoids intermediate overflow from squaring.
                    let norm = (0..8).fold(0.0_f64, |norm, k| {
                        norm.hypot(gains[8 * j + k] - gains[8 * i + k])
                    });
                    out[output] = weight * norm;
                };
                if t + 1 < nt {
                    difference(i + nf * na, tw, i);
                }
                if f + 1 < nf {
                    difference(i + na, fw, n + i);
                }
            }
        }
    }
    if out.iter().any(|v| v.is_infinite()) {
        return Err("TV overflow");
    }
    Ok(out)
}

/// Write time edges then frequency edges, each with nt*nf*na entries.
/// Missing edges are NaN; zero weights explicitly break scan/band gaps.
/// Returns 0 on success, 1 on invalid arguments, 2 on panic.
///
/// # Safety
/// Gains and valid must contain 8*n doubles and n bytes respectively.
/// Weight buffers contain nt-1 and nf-1 doubles, output contains 2*n doubles.
/// All buffers must be aligned, live and nonoverlapping for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_gain_tv(
    nt: usize,
    nf: usize,
    na: usize,
    gains: *const f64,
    valid: *const u8,
    time_weights: *const f64,
    freq_weights: *const f64,
    output: *mut f64,
) -> i32 {
    let Some(n) = nt.checked_mul(nf).and_then(|v| v.checked_mul(na)) else {
        return 1;
    };
    if n == 0
        || n > isize::MAX as usize / (8 * size_of::<f64>())
        || [gains, time_weights, freq_weights, output.cast_const()]
            .iter()
            .any(|p| p.is_null())
        || valid.is_null()
    {
        return 1;
    }
    let result = std::panic::catch_unwind(|| {
        // SAFETY: sizes were bounded above; buffer validity is the caller's contract.
        unsafe {
            edges(
                std::slice::from_raw_parts(gains, 8 * n),
                std::slice::from_raw_parts(valid, n),
                [nt, nf, na],
                std::slice::from_raw_parts(time_weights, nt - 1),
                std::slice::from_raw_parts(freq_weights, nf - 1),
            )
        }
    });
    match result {
        Ok(Ok(edges)) => {
            // SAFETY: output has 2*n entries and does not overlap inputs.
            unsafe { std::ptr::copy_nonoverlapping(edges.as_ptr(), output, edges.len()) };
            0
        }
        Ok(Err(_)) => 1,
        Err(_) => 2,
    }
}

#[cfg(test)]
mod tests {
    use super::edges;

    #[test]
    fn full_matrix_norm_and_masked_gaps() {
        let mut gains = vec![0.0; 4 * 8];
        gains[8] = 3.0;
        gains[9] = 4.0;
        gains[16 + 6] = 12.0; // Off-diagonal/complex entries participate.
        let actual = edges(&gains, &[1, 1, 1, 0], [2, 2, 1], &[2.0], &[1.0]).unwrap();
        assert_eq!(actual[0], 24.0);
        assert_eq!(actual[4], 5.0);
        assert!(actual[1].is_nan());
        let broken = edges(&gains, &[1; 4], [2, 2, 1], &[0.0], &[1.0]).unwrap();
        assert!(broken[..4].iter().all(|v| v.is_nan()));
    }

    #[test]
    fn invalid_cells_are_not_interpolated() {
        let gains = [f64::NAN; 8];
        assert!(edges(&gains, &[0], [1, 1, 1], &[], &[]).is_ok());
        assert!(edges(&gains, &[1], [1, 1, 1], &[], &[]).is_err());
        assert!(edges(&[], &[], [0, 1, 1], &[], &[]).is_err());
    }
}
