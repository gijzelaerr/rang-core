//! C ABI for the flux-standard kernel (`fluxstd.rs`, task FS1). Every pointer
//! has an explicit length; the return code is 0 on success and 1 on bad
//! input (null pointer, empty coefficients, non-positive frequency or unit).

use crate::fluxstd;

/// `out[k] = 10^(sum_j coeffs[j] * log10(freq[k] / unit_hz)^j)` for
/// `k < nfreq`.
///
/// # Safety
/// `coeffs` must point to `ncoeff` doubles, `freq` and `out` to `nfreq`
/// doubles each, `out` not aliasing the inputs.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rang_core_fluxstd_eval(
    ncoeff: usize,
    coeffs: *const f64,
    unit_hz: f64,
    nfreq: usize,
    freq: *const f64,
    out: *mut f64,
) -> i32 {
    if coeffs.is_null() || (nfreq > 0 && (freq.is_null() || out.is_null())) {
        return 1;
    }
    // SAFETY: the caller guarantees the lengths and that `out` is unaliased.
    let (coeffs, freq) = unsafe {
        (
            std::slice::from_raw_parts(coeffs, ncoeff),
            if nfreq == 0 {
                &[][..]
            } else {
                std::slice::from_raw_parts(freq, nfreq)
            },
        )
    };
    match fluxstd::log10_poly(coeffs, unit_hz, freq) {
        Ok(values) => {
            if nfreq > 0 {
                // SAFETY: as above.
                unsafe { std::slice::from_raw_parts_mut(out, nfreq) }.copy_from_slice(&values);
            }
            0
        }
        Err(_) => 1,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn evaluates_and_rejects() {
        let coeffs = [1.2481, -0.4507, -0.1798, 0.0357];
        let freq = [1e9, 1.4e9];
        let mut out = [0.0; 2];
        let rc = unsafe {
            rang_core_fluxstd_eval(4, coeffs.as_ptr(), 1e9, 2, freq.as_ptr(), out.as_mut_ptr())
        };
        assert_eq!(rc, 0);
        assert!((out[0] - 10f64.powf(1.2481)).abs() < 1e-12);
        let bad = [0.0];
        let rc = unsafe {
            rang_core_fluxstd_eval(4, coeffs.as_ptr(), 1e9, 1, bad.as_ptr(), out.as_mut_ptr())
        };
        assert_eq!(rc, 1);
        let rc = unsafe {
            rang_core_fluxstd_eval(0, coeffs.as_ptr(), 1e9, 1, freq.as_ptr(), out.as_mut_ptr())
        };
        assert_eq!(rc, 1);
        let rc = unsafe {
            rang_core_fluxstd_eval(4, std::ptr::null(), 1e9, 1, freq.as_ptr(), out.as_mut_ptr())
        };
        assert_eq!(rc, 1);
    }
}
