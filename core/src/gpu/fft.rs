//! The mixed-radix Stockham autosort FFT of the GPU path: the plan (radix
//! passes and the twiddle table) shared by the WGSL kernel and a host
//! transcription of the same index scheme, which the unit tests check
//! against a direct DFT so the scheme is verified on hosts without an
//! adapter.
//!
//! One pass of radix `r` with `ns` = the product of the earlier radices
//! (`ns` = 1 for the first pass), for every `j < n / r` (E. Bainville's
//! formulation of Stockham's algorithm): with `k = j mod ns`, load
//! `v[q] = src[j + q n/r] * w^(q k n/(ns r))` for `q < r`, take the
//! radix-`r` DFT `u[s] = sum_q v[q] w^((q s mod r) n/r)` and store
//! `dst[(j / ns) ns r + k + s ns] = u[s]`, where `w = exp(+2 pi i / n)` (the
//! backward sign of FFTW and of the CPU path; no scaling). After the last
//! pass `dst` holds the transform in natural order.

use std::f64::consts::PI;

/// Largest radix the WGSL kernel accepts (its private array length).
pub(crate) const MAX_RADIX: usize = 16;

/// Radix passes for a length: fours first, then a two, then the odd
/// primes in increasing order. `None` when a prime factor exceeds
/// `MAX_RADIX`.
pub(crate) fn radices(n: usize) -> Option<Vec<usize>> {
    let mut rest = n;
    let mut out = Vec::new();
    while rest.is_multiple_of(4) {
        out.push(4);
        rest /= 4;
    }
    if rest.is_multiple_of(2) {
        out.push(2);
        rest /= 2;
    }
    let mut p = 3;
    while rest > 1 {
        if p > MAX_RADIX {
            return None;
        }
        while rest.is_multiple_of(p) {
            out.push(p);
            rest /= p;
        }
        p += 2;
    }
    Some(out)
}

/// `exp(+2 pi i q / n)` for `q < n`, as (re, im), computed as `rustfft`
/// computes its twiddles (`cos`, `sin` of the f64 angle).
pub(crate) fn twiddles(n: usize) -> Vec<[f64; 2]> {
    (0..n)
        .map(|q| {
            let angle = 2.0 * PI * q as f64 / n as f64;
            [angle.cos(), angle.sin()]
        })
        .collect()
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct Pass {
    pub(crate) radix: usize,
    pub(crate) ns: usize,
}

/// The passes of a length-`n` transform, `None` when unsupported.
pub(crate) fn plan(n: usize) -> Option<Vec<Pass>> {
    let mut ns = 1;
    let mut passes = Vec::new();
    for radix in radices(n)? {
        passes.push(Pass { radix, ns });
        ns *= radix;
    }
    Some(passes)
}

#[cfg(test)]
fn cmul(a: [f64; 2], b: [f64; 2]) -> [f64; 2] {
    [a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0]]
}

#[cfg(test)]
/// The host transcription of one pass of the WGSL kernel (same index
/// arithmetic and the same order of operations).
fn pass(src: &[[f64; 2]], dst: &mut [[f64; 2]], n: usize, p: Pass, tw: &[[f64; 2]]) {
    let (r, ns) = (p.radix, p.ns);
    let m = n / r;
    let tw_step = n / (ns * r);
    let mut v = [[0.0; 2]; MAX_RADIX];
    for j in 0..m {
        let k = j % ns;
        for (q, slot) in v.iter_mut().enumerate().take(r) {
            *slot = cmul(src[j + q * m], tw[q * k * tw_step]);
        }
        let base = (j / ns) * ns * r + k;
        for s in 0..r {
            let mut acc = [0.0, 0.0];
            for (q, value) in v.iter().enumerate().take(r) {
                let t = cmul(*value, tw[((q * s) % r) * m]);
                acc[0] += t[0];
                acc[1] += t[1];
            }
            dst[base + s * ns] = acc;
        }
    }
}

/// Unnormalised backward 1-D transform of `data` through the pass scheme.
#[cfg(test)]
pub(crate) fn stockham_reference(data: &[[f64; 2]]) -> Option<Vec<[f64; 2]>> {
    let n = data.len();
    let tw = twiddles(n);
    let mut a = data.to_vec();
    let mut b = vec![[0.0; 2]; n];
    for p in plan(n)? {
        pass(&a, &mut b, n, p, &tw);
        std::mem::swap(&mut a, &mut b);
    }
    Some(a)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn naive(data: &[[f64; 2]]) -> Vec<[f64; 2]> {
        let n = data.len();
        (0..n)
            .map(|k| {
                let mut acc = [0.0, 0.0];
                for (j, x) in data.iter().enumerate() {
                    let angle = 2.0 * PI * ((j * k) % n) as f64 / n as f64;
                    let t = cmul(*x, [angle.cos(), angle.sin()]);
                    acc[0] += t[0];
                    acc[1] += t[1];
                }
                acc
            })
            .collect()
    }

    #[test]
    fn radices_cover_the_comparator_sizes() {
        assert_eq!(radices(616), Some(vec![4, 2, 7, 11]));
        assert_eq!(radices(1232), Some(vec![4, 4, 7, 11]));
        assert_eq!(radices(1), Some(vec![]));
        assert_eq!(radices(17 * 4), None);
        assert_eq!(radices(13 * 9 * 5), Some(vec![3, 3, 5, 13]));
    }

    #[test]
    fn stockham_scheme_matches_a_direct_dft() {
        // Factors 2, 3, 4, 5, 7, 11, 13 and lengths 1, 2, 16, 616.
        for n in [
            1, 2, 3, 4, 5, 7, 8, 11, 13, 16, 12, 30, 44, 77, 120, 143, 616,
        ] {
            let data: Vec<[f64; 2]> = (0..n)
                .map(|i| [(i as f64 * 0.7).sin(), (i as f64 * 0.31).cos()])
                .collect();
            let fast = stockham_reference(&data).unwrap();
            let slow = naive(&data);
            let scale = slow
                .iter()
                .map(|v| v[0].abs().max(v[1].abs()))
                .fold(1.0_f64, f64::max);
            for (a, b) in fast.iter().zip(&slow) {
                assert!(
                    (a[0] - b[0]).abs() <= 1e-12 * scale && (a[1] - b[1]).abs() <= 1e-12 * scale,
                    "n = {n}: {a:?} vs {b:?}"
                );
            }
        }
    }
}
