//! SIMD kernels of the gemclean minor cycle, with runtime dispatch.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! Three kernels carry the minor cycle: the patch subtraction
//! `row −= c · beam` (one call per patch row), the first index of the
//! largest `|x|` in a slice (the per-tile argmax) and the exact correction
//! `Σ_j flux_j · table[base − key_j]` (a gather over the components found
//! since the last resync). Each has a scalar body and, on x86-64, an AVX2
//! and an AVX-512 body selected at run time, as `wgridder` selects its
//! gridding loops. The patch subtraction uses a separate multiply and
//! subtract (never a fused multiply-add), so every level gives the scalar
//! result bit for bit; the argmax compares exact absolute values, so it is
//! bit-identical too and resolves ties to the lowest index; the gather sum
//! adds in a different order per level and agrees to rounding.
//!
//! `RANG_GEMCLEAN_SIMD` = `scalar`, `avx2` or `avx512` caps the level of the
//! process (default: the best the CPU has).

#[cfg(target_arch = "x86_64")]
use std::arch::x86_64::*;

/// An instruction-set level of the kernels.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Level {
    Scalar,
    Avx2,
    Avx512,
}

impl Level {
    pub fn name(self) -> &'static str {
        match self {
            Level::Scalar => "scalar",
            Level::Avx2 => "avx2",
            Level::Avx512 => "avx512",
        }
    }
}

/// The best level this CPU supports (AVX2 needs FMA too, AVX-512 needs F
/// and VL, as in `wgridder`).
pub fn detected() -> Level {
    #[cfg(target_arch = "x86_64")]
    {
        let avx2 = std::is_x86_feature_detected!("avx2") && std::is_x86_feature_detected!("fma");
        let avx512 = avx2
            && std::is_x86_feature_detected!("avx512f")
            && std::is_x86_feature_detected!("avx512vl");
        if avx512 {
            Level::Avx512
        } else if avx2 {
            Level::Avx2
        } else {
            Level::Scalar
        }
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        Level::Scalar
    }
}

/// The level of this process: [`detected`] capped by `RANG_GEMCLEAN_SIMD`.
pub fn level() -> Level {
    static LEVEL: std::sync::OnceLock<Level> = std::sync::OnceLock::new();
    *LEVEL.get_or_init(|| {
        let cap = match std::env::var("RANG_GEMCLEAN_SIMD").as_deref() {
            Ok("scalar") | Ok("baseline") => Level::Scalar,
            Ok("avx2") => Level::Avx2,
            _ => Level::Avx512,
        };
        detected().min(cap)
    })
}

/// `level` lowered to what the CPU has, so a request can never reach an
/// instruction the CPU lacks.
fn effective(level: Level) -> Level {
    level.min(detected())
}

// ---------------------------------------------------------------------------
// row −= c · beam

/// `row[i] −= c · beam[i]` for `i < row.len()` (`beam` at least as long).
pub fn sub_scaled(level: Level, row: &mut [f64], beam: &[f64], c: f64) {
    let beam = &beam[..row.len()];
    match effective(level) {
        #[cfg(target_arch = "x86_64")]
        // SAFETY: `effective` returned this level only if the CPU has
        // AVX-512F/VL (resp. AVX2 and FMA), and both slices have `row.len()`
        // elements.
        Level::Avx512 => unsafe { sub_scaled_avx512(row, beam, c) },
        #[cfg(target_arch = "x86_64")]
        // SAFETY: as above, for AVX2.
        Level::Avx2 => unsafe { sub_scaled_avx2(row, beam, c) },
        _ => sub_scaled_scalar(row, beam, c),
    }
}

fn sub_scaled_scalar(row: &mut [f64], beam: &[f64], c: f64) {
    for (r, b) in row.iter_mut().zip(beam) {
        *r -= c * b;
    }
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2,fma")]
fn sub_scaled_avx2(row: &mut [f64], beam: &[f64], c: f64) {
    let n = row.len();
    let cv = _mm256_set1_pd(c);
    let mut i = 0;
    while i + 4 <= n {
        // SAFETY: `i + 4 <= n` and both slices hold `n` values.
        unsafe {
            let r = _mm256_loadu_pd(row.as_ptr().add(i));
            let b = _mm256_loadu_pd(beam.as_ptr().add(i));
            _mm256_storeu_pd(
                row.as_mut_ptr().add(i),
                _mm256_sub_pd(r, _mm256_mul_pd(cv, b)),
            );
        }
        i += 4;
    }
    sub_scaled_scalar(&mut row[i..], &beam[i..], c);
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx512f,avx512vl,avx2,fma")]
fn sub_scaled_avx512(row: &mut [f64], beam: &[f64], c: f64) {
    let n = row.len();
    let cv = _mm512_set1_pd(c);
    let mut i = 0;
    while i + 8 <= n {
        // SAFETY: `i + 8 <= n` and both slices hold `n` values.
        unsafe {
            let r = _mm512_loadu_pd(row.as_ptr().add(i));
            let b = _mm512_loadu_pd(beam.as_ptr().add(i));
            _mm512_storeu_pd(
                row.as_mut_ptr().add(i),
                _mm512_sub_pd(r, _mm512_mul_pd(cv, b)),
            );
        }
        i += 8;
    }
    sub_scaled_scalar(&mut row[i..], &beam[i..], c);
}

// ---------------------------------------------------------------------------
// first argmax of |x|

/// The first index of the largest `|x[i]|` and that absolute value; `x`
/// must not be empty. Values are assumed finite (a NaN is never picked by
/// the scalar path; the SIMD paths do not define what it does).
pub fn max_abs(level: Level, x: &[f64]) -> (usize, f64) {
    let best = max_abs_value(level, x);
    // The maximum is exact, so its first occurrence is the scalar answer.
    let index = x.iter().position(|v| v.abs() == best).unwrap_or(0);
    (index, best)
}

/// The largest `|x[i]|`; `x` must not be empty. The per-tile scan calls this
/// per row and locates the value only once.
pub fn max_abs_value(level: Level, x: &[f64]) -> f64 {
    assert!(!x.is_empty(), "max_abs of an empty slice");
    match effective(level) {
        #[cfg(target_arch = "x86_64")]
        // SAFETY: the CPU has AVX-512F/VL (see `effective`).
        Level::Avx512 => unsafe { max_abs_value_avx512(x) },
        #[cfg(target_arch = "x86_64")]
        // SAFETY: the CPU has AVX2 (see `effective`).
        Level::Avx2 => unsafe { max_abs_value_avx2(x) },
        _ => max_abs_scalar(x).1,
    }
}

fn max_abs_scalar(x: &[f64]) -> (usize, f64) {
    let mut index = 0;
    let mut best = x[0].abs();
    for (i, v) in x.iter().enumerate().skip(1) {
        if v.abs() > best {
            best = v.abs();
            index = i;
        }
    }
    (index, best)
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2,fma")]
fn max_abs_value_avx2(x: &[f64]) -> f64 {
    let n = x.len();
    let sign = _mm256_set1_pd(-0.0);
    let mut m = _mm256_setzero_pd();
    let mut i = 0;
    while i + 4 <= n {
        // SAFETY: `i + 4 <= n`.
        let v = unsafe { _mm256_loadu_pd(x.as_ptr().add(i)) };
        m = _mm256_max_pd(m, _mm256_andnot_pd(sign, v));
        i += 4;
    }
    let mut lanes = [0.0; 4];
    // SAFETY: `lanes` holds four values.
    unsafe { _mm256_storeu_pd(lanes.as_mut_ptr(), m) };
    let mut best = lanes.iter().fold(0.0_f64, |a, &b| a.max(b));
    for v in &x[i..] {
        best = best.max(v.abs());
    }
    best
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx512f,avx512vl,avx2,fma")]
fn max_abs_value_avx512(x: &[f64]) -> f64 {
    let n = x.len();
    let mut m = _mm512_setzero_pd();
    let mut i = 0;
    while i + 8 <= n {
        // SAFETY: `i + 8 <= n`.
        let v = unsafe { _mm512_loadu_pd(x.as_ptr().add(i)) };
        m = _mm512_max_pd(m, _mm512_abs_pd(v));
        i += 8;
    }
    let mut best = _mm512_reduce_max_pd(m);
    for v in &x[i..] {
        best = best.max(v.abs());
    }
    best
}

// ---------------------------------------------------------------------------
// Σ_j flux_j · table[base − key_j]

/// `Σ_j flux[j] · table[base − keys[j]]`.
///
/// The caller guarantees `0 ≤ base − keys[j] < table.len()` for every `j`
/// (the scalar path checks it; the SIMD paths gather without a check, so a
/// violation there would read out of bounds). `gemclean` builds `base` and
/// the keys from pixel indices of the image, for which the offset index
/// into the `(2n − 1)²` beam table is always valid.
pub(crate) fn gather_sum(
    level: Level,
    table: &[f64],
    base: i64,
    keys: &[i64],
    flux: &[f64],
) -> f64 {
    assert_eq!(keys.len(), flux.len());
    debug_assert!(
        keys.iter()
            .all(|&k| base - k >= 0 && ((base - k) as usize) < table.len())
    );
    match effective(level) {
        #[cfg(target_arch = "x86_64")]
        // SAFETY: the CPU has AVX-512F/VL; the indices are in bounds by the
        // caller's guarantee and `keys`, `flux` have equal lengths.
        Level::Avx512 => unsafe { gather_sum_avx512(table, base, keys, flux) },
        #[cfg(target_arch = "x86_64")]
        // SAFETY: as above, for AVX2.
        Level::Avx2 => unsafe { gather_sum_avx2(table, base, keys, flux) },
        _ => gather_sum_scalar(table, base, keys, flux),
    }
}

fn gather_sum_scalar(table: &[f64], base: i64, keys: &[i64], flux: &[f64]) -> f64 {
    let mut sum = 0.0;
    for (&k, &c) in keys.iter().zip(flux) {
        sum += c * table[(base - k) as usize];
    }
    sum
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2,fma")]
unsafe fn gather_sum_avx2(table: &[f64], base: i64, keys: &[i64], flux: &[f64]) -> f64 {
    let n = keys.len();
    let basev = _mm256_set1_epi64x(base);
    let mut acc = _mm256_setzero_pd();
    let mut i = 0;
    while i + 4 <= n {
        // SAFETY: `i + 4 <= n` for the loads; the gathered indices are in
        // bounds by the caller's guarantee.
        unsafe {
            let k = _mm256_loadu_si256(keys.as_ptr().add(i) as *const __m256i);
            let idx = _mm256_sub_epi64(basev, k);
            let g = _mm256_i64gather_pd::<8>(table.as_ptr(), idx);
            let f = _mm256_loadu_pd(flux.as_ptr().add(i));
            acc = _mm256_fmadd_pd(g, f, acc);
        }
        i += 4;
    }
    let mut lanes = [0.0; 4];
    // SAFETY: `lanes` holds four values.
    unsafe { _mm256_storeu_pd(lanes.as_mut_ptr(), acc) };
    let mut sum = (lanes[0] + lanes[1]) + (lanes[2] + lanes[3]);
    sum += gather_sum_scalar(table, base, &keys[i..], &flux[i..]);
    sum
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx512f,avx512vl,avx2,fma")]
unsafe fn gather_sum_avx512(table: &[f64], base: i64, keys: &[i64], flux: &[f64]) -> f64 {
    let n = keys.len();
    let basev = _mm512_set1_epi64(base);
    let mut acc = _mm512_setzero_pd();
    let mut i = 0;
    while i + 8 <= n {
        // SAFETY: `i + 8 <= n` for the loads; the gathered indices are in
        // bounds by the caller's guarantee.
        unsafe {
            let k = _mm512_loadu_si512(keys.as_ptr().add(i) as *const __m512i);
            let idx = _mm512_sub_epi64(basev, k);
            let g = _mm512_i64gather_pd::<8>(idx, table.as_ptr());
            let f = _mm512_loadu_pd(flux.as_ptr().add(i));
            acc = _mm512_fmadd_pd(g, f, acc);
        }
        i += 8;
    }
    let mut sum = _mm512_reduce_add_pd(acc);
    sum += gather_sum_scalar(table, base, &keys[i..], &flux[i..]);
    sum
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Rng(u64);

    impl Rng {
        fn next(&mut self) -> f64 {
            self.0 ^= self.0 << 13;
            self.0 ^= self.0 >> 7;
            self.0 ^= self.0 << 17;
            (self.0 >> 11) as f64 / (1u64 << 53) as f64
        }
    }

    fn levels() -> Vec<Level> {
        [Level::Scalar, Level::Avx2, Level::Avx512]
            .into_iter()
            .filter(|&l| l <= detected())
            .collect()
    }

    #[test]
    fn patch_subtraction_is_bit_identical_across_levels() {
        let mut rng = Rng(3);
        for len in [1, 3, 4, 7, 8, 9, 31, 129, 1000] {
            let base: Vec<f64> = (0..len).map(|_| rng.next() - 0.5).collect();
            let beam: Vec<f64> = (0..len + 5).map(|_| rng.next() - 0.3).collect();
            let c = rng.next() * 3.0 - 1.0;
            let mut want = base.clone();
            sub_scaled_scalar(&mut want, &beam[..len], c);
            for level in levels() {
                let mut got = base.clone();
                sub_scaled(level, &mut got, &beam, c);
                assert!(
                    got.iter()
                        .zip(&want)
                        .all(|(a, b)| a.to_bits() == b.to_bits()),
                    "{level:?}, length {len}"
                );
            }
        }
    }

    #[test]
    fn argmax_is_bit_identical_and_takes_the_first_tie() {
        let mut rng = Rng(5);
        for len in [1, 2, 5, 8, 13, 64, 257] {
            let mut x: Vec<f64> = (0..len).map(|_| rng.next() - 0.5).collect();
            // A tie of opposite signs, the later one negative.
            if len > 4 {
                x[len / 3] = 0.75;
                x[len - 1] = -0.75;
            }
            let want = max_abs_scalar(&x);
            let reference = crate::clean::argmax_abs(&x);
            assert_eq!(want.0, reference.0);
            for level in levels() {
                let got = max_abs(level, &x);
                assert_eq!(got.0, want.0, "{level:?}, length {len}");
                assert_eq!(got.1.to_bits(), want.1.to_bits());
            }
        }
    }

    #[test]
    fn gather_sum_agrees_to_rounding() {
        let mut rng = Rng(11);
        let table: Vec<f64> = (0..5000).map(|_| rng.next() - 0.5).collect();
        for count in [0, 1, 3, 4, 5, 8, 17, 1000] {
            let base = 4999;
            let keys: Vec<i64> = (0..count).map(|_| (rng.next() * 4999.0) as i64).collect();
            let flux: Vec<f64> = (0..count).map(|_| rng.next() - 0.5).collect();
            let want = gather_sum_scalar(&table, base, &keys, &flux);
            let scale: f64 = keys
                .iter()
                .zip(&flux)
                .map(|(&k, &c)| (c * table[(base - k) as usize]).abs())
                .sum();
            for level in levels() {
                let got = gather_sum(level, &table, base, &keys, &flux);
                assert!(
                    (got - want).abs() <= 1e-12 * scale.max(f64::MIN_POSITIVE),
                    "{level:?}, count {count}: {got} against {want}"
                );
            }
        }
    }
}
