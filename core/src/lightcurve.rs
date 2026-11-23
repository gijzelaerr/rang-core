// SPDX-License-Identifier: MIT
//! Forced photometry by the exact direct Fourier transform, for the residual
//! snapshot light curves of task TS-P1 (`research/ts-p1.md`, section 3).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
//! see `LICENSES/MIT.txt`.
//!
//! For each position (l, m), with n = sqrt(1 - l² - m²), the flux of one
//! interval is
//!
//! ```text
//! S = Σ w Re[I exp(-2πi (u l + v m + w (n - 1)) ν / c)] / Σ w
//! ```
//!
//! over the rows and channels given, in float64, with no division by n: the
//! value of a dirty image pixel at (l, m) with natural weighting, as WSClean
//! and the exact gridder (`divide_by_n = false`) make it, and the inverse of
//! the component predictor (`crate::predict`, positive Fourier phase). The
//! sums run over fixed blocks of rows in parallel and are added in block
//! order, so the result does not depend on the thread count.

use rayon::prelude::*;

/// Speed of light in m/s.
pub const SPEED_OF_LIGHT: f64 = 299_792_458.0;
/// Rows per block of the parallel sum (fixed: results are bit-identical at
/// any thread count).
const BLOCK_ROWS: usize = 64;

/// The sums of one interval: `numerator[s] = Σ w Re[...]` per position, the
/// weight sum and the count of samples with a nonzero weight.
#[derive(Clone, Debug, PartialEq)]
pub struct DftSums {
    pub numerator: Vec<f64>,
    pub weight_sum: f64,
    pub samples: u64,
}

impl DftSums {
    /// The fluxes `numerator / weight_sum` (NaN when no sample has weight).
    pub fn fluxes(&self) -> Vec<f64> {
        self.numerator
            .iter()
            .map(|n| {
                if self.weight_sum > 0.0 {
                    n / self.weight_sum
                } else {
                    f64::NAN
                }
            })
            .collect()
    }
}

/// The DFT sums of `nrow` rows: `uvw` (nrow × 3, metres), `freq` (nchan, Hz),
/// `vis` (nrow × nchan complex, interleaved re, im), `weight` (nrow × nchan;
/// zero for a flagged or unselected sample) and `lm` (nsrc × 2, direction
/// cosines). A non-finite visibility with a nonzero weight is an error.
pub fn dft_sums(
    uvw: &[f64],
    freq: &[f64],
    vis: &[f32],
    weight: &[f32],
    lm: &[f64],
) -> Result<DftSums, String> {
    let nchan = freq.len();
    if !uvw.len().is_multiple_of(3) {
        return Err("uvw must hold nrow × 3 values".into());
    }
    let nrow = uvw.len() / 3;
    if vis.len() != 2 * nrow * nchan || weight.len() != nrow * nchan {
        return Err(format!(
            "vis must hold 2 × {nrow} × {nchan} and weight {nrow} × {nchan} values"
        ));
    }
    if !lm.len().is_multiple_of(2) {
        return Err("lm must hold nsrc × 2 values".into());
    }
    let nsrc = lm.len() / 2;
    let mut nm1 = Vec::with_capacity(nsrc);
    for s in 0..nsrc {
        let (l, m) = (lm[2 * s], lm[2 * s + 1]);
        let r2 = l * l + m * m;
        if !(l.is_finite() && m.is_finite()) || r2 >= 1.0 {
            return Err(format!("position {s}: l² + m² must be below one"));
        }
        // n - 1 without cancellation.
        nm1.push(-r2 / ((1.0 - r2).sqrt() + 1.0));
    }
    let scale: Vec<f64> = freq
        .iter()
        .map(|f| -2.0 * std::f64::consts::PI * f / SPEED_OF_LIGHT)
        .collect();
    let blocks: Vec<Result<DftSums, String>> = (0..nrow.div_ceil(BLOCK_ROWS))
        .into_par_iter()
        .map(|b| {
            let mut out = DftSums {
                numerator: vec![0.0; nsrc],
                weight_sum: 0.0,
                samples: 0,
            };
            for r in b * BLOCK_ROWS..((b + 1) * BLOCK_ROWS).min(nrow) {
                let (u, v, w) = (uvw[3 * r], uvw[3 * r + 1], uvw[3 * r + 2]);
                let base: Vec<f64> = (0..nsrc)
                    .map(|s| u * lm[2 * s] + v * lm[2 * s + 1] + w * nm1[s])
                    .collect();
                for (c, sc) in scale.iter().enumerate() {
                    let k = r * nchan + c;
                    let wt = weight[k] as f64;
                    if wt == 0.0 {
                        continue;
                    }
                    let (re, im) = (vis[2 * k] as f64, vis[2 * k + 1] as f64);
                    if !(re.is_finite() && im.is_finite() && wt.is_finite()) {
                        return Err(format!("row {r} channel {c}: non-finite sample"));
                    }
                    out.weight_sum += wt;
                    out.samples += 1;
                    for (s, b) in base.iter().enumerate() {
                        let (sin, cos) = (sc * b).sin_cos();
                        out.numerator[s] += wt * (re * cos - im * sin);
                    }
                }
            }
            Ok(out)
        })
        .collect();
    let mut total = DftSums {
        numerator: vec![0.0; nsrc],
        weight_sum: 0.0,
        samples: 0,
    };
    for block in blocks {
        let block = block?;
        for (t, n) in total.numerator.iter_mut().zip(&block.numerator) {
            *t += n;
        }
        total.weight_sum += block.weight_sum;
        total.samples += block.samples;
    }
    Ok(total)
}

/// The DFT sums of one interval per channel group (task TS-P2,
/// `research/ts-p2.md` section 2): `numerator[s * groups + g]` per position s
/// and group g, `weight_sum[g]` and `samples[g]`. Group g holds the channels
/// g·K to (g + 1)·K − 1, K = nchan / groups (`groups` must divide nchan).
#[derive(Clone, Debug, PartialEq)]
pub struct GroupedSums {
    pub groups: usize,
    pub numerator: Vec<f64>,
    pub weight_sum: Vec<f64>,
    pub samples: Vec<u64>,
}

impl GroupedSums {
    /// `(nsrc × groups)` fluxes, row-major by position (NaN where a group has
    /// no weighted sample).
    pub fn fluxes(&self) -> Vec<f64> {
        self.numerator
            .iter()
            .enumerate()
            .map(|(k, n)| {
                let w = self.weight_sum[k % self.groups];
                if w > 0.0 { n / w } else { f64::NAN }
            })
            .collect()
    }
}

/// `dft_sums` per channel group: the same arguments plus `groups`, the sums
/// over fixed blocks of rows in parallel, added in block order (bit-identical
/// at any thread count). `dft_sums` itself is unchanged, so P1's outputs do
/// not move.
pub fn dft_sums_grouped(
    uvw: &[f64],
    freq: &[f64],
    vis: &[f32],
    weight: &[f32],
    lm: &[f64],
    groups: usize,
) -> Result<GroupedSums, String> {
    let nchan = freq.len();
    if groups == 0 || nchan == 0 || !nchan.is_multiple_of(groups) {
        return Err(format!(
            "channel groups ({groups}) must divide the channels ({nchan})"
        ));
    }
    if !uvw.len().is_multiple_of(3) {
        return Err("uvw must hold nrow × 3 values".into());
    }
    let nrow = uvw.len() / 3;
    if vis.len() != 2 * nrow * nchan || weight.len() != nrow * nchan {
        return Err(format!(
            "vis must hold 2 × {nrow} × {nchan} and weight {nrow} × {nchan} values"
        ));
    }
    if !lm.len().is_multiple_of(2) {
        return Err("lm must hold nsrc × 2 values".into());
    }
    let nsrc = lm.len() / 2;
    let per = nchan / groups;
    let mut nm1 = Vec::with_capacity(nsrc);
    for s in 0..nsrc {
        let (l, m) = (lm[2 * s], lm[2 * s + 1]);
        let r2 = l * l + m * m;
        if !(l.is_finite() && m.is_finite()) || r2 >= 1.0 {
            return Err(format!("position {s}: l² + m² must be below one"));
        }
        nm1.push(-r2 / ((1.0 - r2).sqrt() + 1.0));
    }
    let scale: Vec<f64> = freq
        .iter()
        .map(|f| -2.0 * std::f64::consts::PI * f / SPEED_OF_LIGHT)
        .collect();
    let empty = || GroupedSums {
        groups,
        numerator: vec![0.0; nsrc * groups],
        weight_sum: vec![0.0; groups],
        samples: vec![0; groups],
    };
    let blocks: Vec<Result<GroupedSums, String>> = (0..nrow.div_ceil(BLOCK_ROWS))
        .into_par_iter()
        .map(|b| {
            let mut out = empty();
            for r in b * BLOCK_ROWS..((b + 1) * BLOCK_ROWS).min(nrow) {
                let (u, v, w) = (uvw[3 * r], uvw[3 * r + 1], uvw[3 * r + 2]);
                let base: Vec<f64> = (0..nsrc)
                    .map(|s| u * lm[2 * s] + v * lm[2 * s + 1] + w * nm1[s])
                    .collect();
                for (c, sc) in scale.iter().enumerate() {
                    let k = r * nchan + c;
                    let wt = weight[k] as f64;
                    if wt == 0.0 {
                        continue;
                    }
                    let (re, im) = (vis[2 * k] as f64, vis[2 * k + 1] as f64);
                    if !(re.is_finite() && im.is_finite() && wt.is_finite()) {
                        return Err(format!("row {r} channel {c}: non-finite sample"));
                    }
                    let g = c / per;
                    out.weight_sum[g] += wt;
                    out.samples[g] += 1;
                    for (s, b) in base.iter().enumerate() {
                        let (sin, cos) = (sc * b).sin_cos();
                        out.numerator[s * groups + g] += wt * (re * cos - im * sin);
                    }
                }
            }
            Ok(out)
        })
        .collect();
    let mut total = empty();
    for block in blocks {
        let block = block?;
        for (t, n) in total.numerator.iter_mut().zip(&block.numerator) {
            *t += n;
        }
        for (t, n) in total.weight_sum.iter_mut().zip(&block.weight_sum) {
            *t += n;
        }
        for (t, n) in total.samples.iter_mut().zip(&block.samples) {
            *t += n;
        }
    }
    Ok(total)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn grouped_sums_add_up_to_the_ungrouped_ones_and_follow_the_spectrum() {
        let freq: Vec<f64> = (0..8).map(|k| 0.9e9 + 0.1e9 * k as f64).collect();
        let uvw = uvw(200);
        let (l, m) = (0.003, 0.002);
        // A source whose flux doubles in the upper half of the band.
        let lo = predicted(&uvw, &freq, l, m, 1.0);
        let hi = predicted(&uvw, &freq, l, m, 2.0);
        let vis: Vec<f32> = (0..lo.len())
            .map(|k| if (k / 2) % 8 < 4 { lo[k] } else { hi[k] })
            .collect();
        let mut weight = vec![1.0f32; 200 * 8];
        weight[5] = 0.0;
        let lm = [l, m, 0.0, 0.0];
        let g = dft_sums_grouped(&uvw, &freq, &vis, &weight, &lm, 2).unwrap();
        let f = g.fluxes();
        assert!(
            (f[0] - 1.0).abs() < 1e-6 && (f[1] - 2.0).abs() < 1e-6,
            "{f:?}"
        );
        let one = dft_sums(&uvw, &freq, &vis, &weight, &lm).unwrap();
        assert_eq!(g.samples.iter().sum::<u64>(), one.samples);
        assert_eq!(g.weight_sum.iter().sum::<f64>(), one.weight_sum);
        for s in 0..2 {
            let num: f64 = g.numerator[2 * s] + g.numerator[2 * s + 1];
            let scale = one.numerator[s].abs().max(1.0);
            assert!((num - one.numerator[s]).abs() <= 1e-9 * scale);
        }
        let single = dft_sums_grouped(&uvw, &freq, &vis, &weight, &lm, 1).unwrap();
        assert_eq!(single.weight_sum[0], one.weight_sum);
    }

    #[test]
    fn grouped_sums_refuse_a_bad_grouping_and_leave_an_empty_group_nan() {
        let freq = [1.0e9, 1.1e9, 1.2e9, 1.3e9];
        let uvw = uvw(10);
        let vis = predicted(&uvw, &freq, 0.0, 0.0, 1.0);
        let mut weight = vec![1.0f32; 40];
        assert!(dft_sums_grouped(&uvw, &freq, &vis, &weight, &[0.0, 0.0], 3).is_err());
        assert!(dft_sums_grouped(&uvw, &freq, &vis, &weight, &[0.0, 0.0], 0).is_err());
        for r in 0..10 {
            weight[4 * r + 2] = 0.0;
            weight[4 * r + 3] = 0.0;
        }
        let g = dft_sums_grouped(&uvw, &freq, &vis, &weight, &[0.0, 0.0], 2).unwrap();
        let f = g.fluxes();
        assert!((f[0] - 1.0).abs() < 1e-6 && f[1].is_nan(), "{f:?}");
        assert_eq!(g.samples, vec![20, 0]);
    }

    #[test]
    fn grouped_sums_independent_of_the_thread_count() {
        let freq = [1.0e9, 1.3e9, 1.5e9, 1.7e9];
        let uvw = uvw(1000);
        let vis: Vec<f32> = (0..8000)
            .map(|k| ((k * 7919) % 1000) as f32 * 1e-3)
            .collect();
        let weight = vec![1.0f32; 4000];
        let lm = [0.01, 0.002, -0.003, 0.004];
        let run = |n| {
            rayon::ThreadPoolBuilder::new()
                .num_threads(n)
                .build()
                .unwrap()
                .install(|| dft_sums_grouped(&uvw, &freq, &vis, &weight, &lm, 2).unwrap())
        };
        assert_eq!(run(1), run(4));
    }

    /// A point source of flux `s` at (l, m) as the predictor writes it.
    fn predicted(uvw: &[f64], freq: &[f64], l: f64, m: f64, s: f64) -> Vec<f32> {
        let n = (1.0 - l * l - m * m).sqrt();
        let mut out = Vec::new();
        for r in 0..uvw.len() / 3 {
            for f in freq {
                let p = 2.0 * std::f64::consts::PI * f / SPEED_OF_LIGHT
                    * (uvw[3 * r] * l + uvw[3 * r + 1] * m + uvw[3 * r + 2] * (n - 1.0));
                out.push((s * p.cos()) as f32);
                out.push((s * p.sin()) as f32);
            }
        }
        out
    }

    fn uvw(nrow: usize) -> Vec<f64> {
        (0..nrow)
            .flat_map(|r| {
                let a = r as f64 * 0.7;
                [3000.0 * a.cos(), 2500.0 * a.sin(), 40.0 * (r as f64 - 20.0)]
            })
            .collect()
    }

    #[test]
    fn recovers_a_predicted_point_source_and_nothing_elsewhere_on_average() {
        let freq = [0.9e9, 1.2e9, 1.6e9];
        let uvw = uvw(300);
        let (l, m) = (0.004, -0.007);
        let vis = predicted(&uvw, &freq, l, m, 2.5);
        let weight = vec![1.0f32; 300 * 3];
        let sums = dft_sums(&uvw, &freq, &vis, &weight, &[l, m, 0.0, 0.0]).unwrap();
        let flux = sums.fluxes();
        assert!((flux[0] - 2.5).abs() < 1e-6, "{flux:?}");
        assert!(flux[1].abs() < 0.5, "{flux:?}");
        assert_eq!(sums.samples, 900);
        assert_eq!(sums.weight_sum, 900.0);
    }

    #[test]
    fn weights_and_flags_enter_the_sums() {
        let freq = [1.0e9, 1.4e9];
        let uvw = uvw(10);
        let mut vis = predicted(&uvw, &freq, 0.0, 0.0, 1.0);
        let mut weight = vec![2.0f32; 20];
        weight[3] = 0.0;
        vis[6] = f32::NAN; // flagged sample: ignored
        let sums = dft_sums(&uvw, &freq, &vis, &weight, &[0.0, 0.0]).unwrap();
        assert_eq!(sums.samples, 19);
        assert_eq!(sums.weight_sum, 38.0);
        assert!((sums.fluxes()[0] - 1.0).abs() < 1e-6);
        weight[3] = 1.0;
        assert!(dft_sums(&uvw, &freq, &vis, &weight, &[0.0, 0.0]).is_err());
    }

    #[test]
    fn independent_of_the_thread_count() {
        let freq = [1.0e9, 1.3e9, 1.7e9];
        let uvw = uvw(1000);
        let vis: Vec<f32> = (0..6000)
            .map(|k| ((k * 7919) % 1000) as f32 * 1e-3)
            .collect();
        let weight = vec![1.0f32; 3000];
        let lm = [0.01, 0.002, -0.003, 0.004];
        let one = rayon::ThreadPoolBuilder::new()
            .num_threads(1)
            .build()
            .unwrap()
            .install(|| dft_sums(&uvw, &freq, &vis, &weight, &lm).unwrap());
        let four = rayon::ThreadPoolBuilder::new()
            .num_threads(4)
            .build()
            .unwrap()
            .install(|| dft_sums(&uvw, &freq, &vis, &weight, &lm).unwrap());
        assert_eq!(one, four);
    }

    #[test]
    fn refuses_bad_shapes_and_positions() {
        assert!(dft_sums(&[0.0; 4], &[1e9], &[0.0; 2], &[1.0], &[0.0, 0.0]).is_err());
        assert!(dft_sums(&[0.0; 3], &[1e9], &[0.0; 2], &[1.0], &[1.0, 0.5]).is_err());
        let empty = dft_sums(&[0.0; 3], &[1e9], &[0.0; 2], &[0.0], &[0.0, 0.0]).unwrap();
        assert!(empty.fluxes()[0].is_nan());
    }
}
