// SPDX-License-Identifier: GPL-3.0-or-later
//! Output channels, channel averaging and WSClean's polynomial spectral fit
//! for gemclean (`research/g3-spectral.md`).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The grouping is WSClean 3.7's `makeImagingTableEntryChannelSettings`
//! (`main/wsclean.cpp`): the unique channel frequencies in ascending order,
//! after `-channel-range`, and output channel `i` of `n` takes input channels
//! `i·N/n` to `(i+1)·N/n − 1`. The fit is schaapcommon's
//! `SpectralFitter::Fit` and `Evaluate` in `kPolynomial` mode
//! (`external/schaapcommon/src/fitters/spectralfitter.cc`): a polynomial in
//! `ν/ν_ref − 1` by weighted least squares over the channels of positive
//! weight, `ν_ref` the weighted mean frequency.

use super::input::StokesI;
use rustfft::num_complex::Complex;

/// The input channels of each output channel, as indices into the read
/// channels, each group in ascending frequency.
pub fn channel_groups(
    freq: &[f64],
    range: Option<(usize, usize)>,
    channels_out: usize,
) -> Result<Vec<Vec<usize>>, String> {
    let mut order: Vec<usize> = (0..freq.len()).collect();
    order.sort_by(|&a, &b| freq[a].total_cmp(&freq[b]));
    if order.windows(2).any(|w| freq[w[0]] == freq[w[1]]) {
        return Err("two channels have the same frequency".into());
    }
    let (start, end) = match range {
        Some((s, e)) => {
            if e > order.len() || s >= e {
                return Err(format!(
                    "-channel-range {s} {e}: the data have {} channels",
                    order.len()
                ));
            }
            (s, e)
        }
        None => (0, order.len()),
    };
    let kept = &order[start..end];
    let n = kept.len();
    if channels_out == 0 || channels_out > n {
        return Err(format!(
            "-channels-out {channels_out}: {n} channels are selected"
        ));
    }
    Ok((0..channels_out)
        .map(|i| kept[i * n / channels_out..(i + 1) * n / channels_out].to_vec())
        .collect())
}

/// The channels `keep` of `data` (each row keeps them in this order).
pub fn select_channels(data: StokesI, keep: &[usize]) -> StokesI {
    let nchan = data.freq.len();
    if keep.len() == nchan && keep.iter().enumerate().all(|(i, &k)| i == k) {
        return data;
    }
    let rows = data.rows();
    let mut vis = Vec::with_capacity(rows * keep.len());
    let mut weight = Vec::with_capacity(rows * keep.len());
    for row in 0..rows {
        for &k in keep {
            vis.push(data.vis[row * nchan + k]);
            weight.push(data.weight[row * nchan + k]);
        }
    }
    StokesI {
        freq: keep.iter().map(|&k| data.freq[k]).collect(),
        vis,
        weight,
        ..data
    }
}

/// Weighted means of `width` adjacent channels (the last group may be
/// smaller): visibilities weighted by their Stokes I weights, the weights
/// summed, the frequency the plain mean of the group's frequencies. A group
/// with no weight keeps the plain mean of its visibilities at weight zero.
/// Sums in `f64`; the visibilities are rounded to `f32` once.
pub fn average_channels(data: StokesI, width: usize) -> StokesI {
    if width <= 1 {
        return data;
    }
    let nchan = data.freq.len();
    let groups: Vec<(usize, usize)> = (0..nchan)
        .step_by(width)
        .map(|a| (a, (a + width).min(nchan)))
        .collect();
    let rows = data.rows();
    let mut vis = Vec::with_capacity(rows * groups.len());
    let mut weight = Vec::with_capacity(rows * groups.len());
    for row in 0..rows {
        for &(a, b) in &groups {
            let (mut re, mut im, mut wsum) = (0.0f64, 0.0f64, 0.0f64);
            let (mut pre, mut pim) = (0.0f64, 0.0f64);
            for k in a..b {
                let v = data.vis[row * nchan + k];
                let w = f64::from(data.weight[row * nchan + k]);
                re += w * f64::from(v.re);
                im += w * f64::from(v.im);
                wsum += w;
                pre += f64::from(v.re);
                pim += f64::from(v.im);
            }
            let (vr, vi) = if wsum > 0.0 {
                (re / wsum, im / wsum)
            } else {
                let m = (b - a) as f64;
                (pre / m, pim / m)
            };
            vis.push(Complex::new(vr as f32, vi as f32));
            weight.push(wsum as f32);
        }
    }
    let freq = groups
        .iter()
        .map(|&(a, b)| data.freq[a..b].iter().sum::<f64>() / (b - a) as f64)
        .collect();
    StokesI {
        freq,
        vis,
        weight,
        ..data
    }
}

/// The Dirichlet kernel `sin(nπx) / (n sin(πx))`: the factor on a point
/// source's visibility when `n` channels spaced `δν` are averaged and labelled
/// with their mean frequency, `x = τ δν / c` (`research/gate3c-averaging.md`,
/// HA). 1 at `x = 0`.
pub fn dirichlet(n: usize, x: f64) -> f64 {
    let s = (std::f64::consts::PI * x).sin();
    if s.abs() < 1e-12 {
        return 1.0;
    }
    (n as f64 * std::f64::consts::PI * x).sin() / (n as f64 * s)
}

/// Directions at which [`averaging_peak_at`] averages: 16 azimuths.
pub const AVERAGING_AZIMUTHS: usize = 16;

/// The predicted peak, as a fraction of the unaveraged one, of a point source
/// at radius `radius` (radians, the length of the SIN direction cosines) when
/// `n` adjacent channels of width `dnu` Hz are averaged
/// (`research/gate3c-averaging.md`, HA, full groups): the mean over
/// [`AVERAGING_AZIMUTHS`] azimuths of `Σ W_r D_n(τ_r δν / c) / Σ W_r`, with
/// `τ = u l + v m + w (√(1 − l² − m²) − 1)` metres. `uvw` is `rows × 3`
/// metres and `row_weight` the rows' summed weights (0 skips a row). Sums
/// per fixed block of rows, then in order: the same value at any thread count.
pub fn averaging_peak_at(uvw: &[f64], row_weight: &[f64], n: usize, dnu: f64, radius: f64) -> f64 {
    use rayon::prelude::*;
    const C: f64 = 299_792_458.0;
    const BLOCK: usize = 1 << 15;
    if n <= 1 {
        return 1.0;
    }
    let nw = (1.0 - radius * radius).max(0.0).sqrt() - 1.0;
    let dirs: Vec<(f64, f64)> = (0..AVERAGING_AZIMUTHS)
        .map(|k| {
            let phi = 2.0 * std::f64::consts::PI * k as f64 / AVERAGING_AZIMUTHS as f64;
            (radius * phi.cos(), radius * phi.sin())
        })
        .collect();
    let parts: Vec<(f64, f64)> = row_weight
        .par_chunks(BLOCK)
        .enumerate()
        .map(|(b, ws)| {
            let (mut num, mut den) = (0.0f64, 0.0f64);
            for (i, &w) in ws.iter().enumerate() {
                if w <= 0.0 {
                    continue;
                }
                let r = b * BLOCK + i;
                let (u, v, ww) = (uvw[3 * r], uvw[3 * r + 1], uvw[3 * r + 2]);
                let mut d = 0.0;
                for &(l, m) in &dirs {
                    d += dirichlet(n, (u * l + v * m + ww * nw) * dnu / C);
                }
                num += w * d / AVERAGING_AZIMUTHS as f64;
                den += w;
            }
            (num, den)
        })
        .collect();
    let (num, den) = parts
        .iter()
        .fold((0.0, 0.0), |(a, b), (x, y)| (a + x, b + y));
    if den > 0.0 { num / den } else { 1.0 }
}

/// The predicted restored peak (`research/gate3c-averaging.md`, A1, HA′) of
/// a point source at radius `radius` (radians) averaged over
/// [`AVERAGING_AZIMUTHS`] azimuths, for `n` channels of width `dnu` averaged
/// in an output channel at `nu` Hz, restored with a Gaussian beam of FWHM
/// `major`, `minor` (radians) and position angle `pa` (radians from north
/// towards east): `exp(−cᵀ Σ⁻¹ c / (8π²))`, `c = π (δν/ν) √((n² − 1)/3) (l, m)`
/// (exact for n = 2, second order above).
pub fn restored_peak_at(n: usize, dnu: f64, nu: f64, beam: (f64, f64, f64), radius: f64) -> f64 {
    if n <= 1 {
        return 1.0;
    }
    let (major, minor, pa) = beam;
    let s = 1.0 / (2.0 * (2.0 * std::f64::consts::LN_2).sqrt());
    let (a2, b2) = ((major * s).powi(2), (minor * s).powi(2));
    let (e1, e2) = ((pa.sin(), pa.cos()), (pa.cos(), -pa.sin()));
    let k = std::f64::consts::PI * dnu / nu * (((n * n) as f64 - 1.0) / 3.0).sqrt();
    let mut sum = 0.0;
    for j in 0..AVERAGING_AZIMUTHS {
        let phi = 2.0 * std::f64::consts::PI * j as f64 / AVERAGING_AZIMUTHS as f64;
        let (cl, cm) = (k * radius * phi.cos(), k * radius * phi.sin());
        let p1 = cl * e1.0 + cm * e1.1;
        let p2 = cl * e2.0 + cm * e2.1;
        let q = p1 * p1 / a2 + p2 * p2 / b2;
        sum += (-q / (8.0 * std::f64::consts::PI * std::f64::consts::PI)).exp();
    }
    sum / AVERAGING_AZIMUTHS as f64
}

/// Each row's summed Stokes I weight over the channels `keep` of `data`
/// (0 for a flagged row).
pub fn row_weights(data: &StokesI, keep: &[usize]) -> Vec<f64> {
    let nchan = data.freq.len();
    (0..data.rows())
        .map(|r| {
            if data.flag_row[r] {
                0.0
            } else {
                keep.iter()
                    .map(|&k| f64::from(data.weight[r * nchan + k]))
                    .sum()
            }
        })
        .collect()
}

/// WSClean's `-fit-spectral-pol` on the joined channels.
#[derive(Clone, Debug)]
pub struct PolynomialFit {
    pub terms: usize,
    /// The channels' frequencies and weights.
    pub frequencies: Vec<f64>,
    pub weights: Vec<f64>,
    /// The weighted mean frequency (150 MHz without weight, as schaapcommon).
    pub reference: f64,
}

impl PolynomialFit {
    pub fn new(terms: usize, frequencies: Vec<f64>, weights: Vec<f64>) -> PolynomialFit {
        let sum: f64 = weights.iter().sum();
        let reference = if sum > 0.0 {
            frequencies
                .iter()
                .zip(&weights)
                .map(|(f, w)| f * w)
                .sum::<f64>()
                / sum
        } else {
            150.0e6
        };
        PolynomialFit {
            terms,
            frequencies,
            weights,
            reference,
        }
    }

    /// The terms of the weighted least-squares polynomial through `values`,
    /// in `x = ν/ν_ref − 1` (as many terms as channels of positive weight at
    /// most; the rest are zero).
    pub fn fit(&self, values: &[f64]) -> Vec<f64> {
        let points: Vec<(f64, f64, f64)> = self
            .frequencies
            .iter()
            .zip(&self.weights)
            .zip(values)
            .filter(|((_, w), _)| **w > 0.0)
            .map(|((f, w), v)| (f / self.reference - 1.0, *v, *w))
            .collect();
        let mut terms = vec![0.0; self.terms];
        let m = self.terms.min(points.len());
        if m == 0 {
            return terms;
        }
        // Householder QR of √w·A, A[i][j] = x_i^j, then back substitution.
        let rows = points.len();
        let mut a = vec![0.0; rows * m];
        let mut b = vec![0.0; rows];
        for (i, &(x, y, w)) in points.iter().enumerate() {
            let s = w.sqrt();
            let mut p = 1.0;
            for j in 0..m {
                a[i * m + j] = s * p;
                p *= x;
            }
            b[i] = s * y;
        }
        for j in 0..m {
            let norm = (j..rows)
                .map(|i| a[i * m + j] * a[i * m + j])
                .sum::<f64>()
                .sqrt();
            if norm == 0.0 {
                continue;
            }
            let alpha = if a[j * m + j] > 0.0 { -norm } else { norm };
            let mut v: Vec<f64> = (j..rows).map(|i| a[i * m + j]).collect();
            v[0] -= alpha;
            let vv: f64 = v.iter().map(|x| x * x).sum();
            if vv == 0.0 {
                continue;
            }
            for col in j..m {
                let dot: f64 = (j..rows).map(|i| v[i - j] * a[i * m + col]).sum();
                let f = 2.0 * dot / vv;
                for i in j..rows {
                    a[i * m + col] -= f * v[i - j];
                }
            }
            let dot: f64 = (j..rows).map(|i| v[i - j] * b[i]).sum();
            let f = 2.0 * dot / vv;
            for i in j..rows {
                b[i] -= f * v[i - j];
            }
        }
        for j in (0..m).rev() {
            let mut s = b[j];
            for k in j + 1..m {
                s -= a[j * m + k] * terms[k];
            }
            let d = a[j * m + j];
            terms[j] = if d != 0.0 { s / d } else { 0.0 };
        }
        terms
    }

    /// The polynomial of `terms` at frequency `nu`.
    pub fn evaluate(&self, terms: &[f64], nu: f64) -> f64 {
        let x = nu / self.reference - 1.0;
        terms.iter().rev().fold(0.0, |acc, &t| acc * x + t)
    }

    /// `values` replaced by the fit evaluated at every channel.
    pub fn fit_and_evaluate(&self, values: &mut [f64]) {
        let terms = self.fit(values);
        for (v, &f) in values.iter_mut().zip(&self.frequencies) {
            *v = self.evaluate(&terms, f);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn groups_follow_wsclean() {
        let freq: Vec<f64> = (0..10).map(|i| 1e9 + 1e6 * i as f64).collect();
        let g = channel_groups(&freq, None, 3).unwrap();
        // i·N/n: 0, 3, 6, 10.
        assert_eq!(g, vec![vec![0, 1, 2], vec![3, 4, 5], vec![6, 7, 8, 9]]);
        let g = channel_groups(&freq, Some((2, 9)), 2).unwrap();
        assert_eq!(g, vec![vec![2, 3, 4], vec![5, 6, 7, 8]]);
        let mut down = freq.clone();
        down.reverse();
        let g = channel_groups(&down, None, 2).unwrap();
        assert_eq!(g, vec![vec![9, 8, 7, 6, 5], vec![4, 3, 2, 1, 0]]);
        assert!(channel_groups(&freq, None, 11).is_err());
        assert!(channel_groups(&freq, Some((5, 11)), 1).is_err());
    }

    #[test]
    fn the_fit_reproduces_a_polynomial_and_drops_zero_weights() {
        let f: Vec<f64> = (0..8).map(|i| 0.9e9 + 0.1e9 * i as f64).collect();
        let w = vec![1.0, 2.0, 0.0, 1.5, 1.0, 3.0, 1.0, 0.5];
        let fit = PolynomialFit::new(3, f.clone(), w.clone());
        let want = [0.7, -0.4, 0.25];
        let mut v: Vec<f64> = f.iter().map(|&nu| fit.evaluate(&want, nu)).collect();
        v[2] = 1e6; // weight zero: ignored
        let got = fit.fit(&v);
        for (g, w) in got.iter().zip(want) {
            assert!((g - w).abs() < 1e-12, "{got:?}");
        }
        fit.fit_and_evaluate(&mut v);
        assert!((v[2] - fit.evaluate(&want, f[2])).abs() < 1e-12);
        let reference = f.iter().zip(&w).map(|(a, b)| a * b).sum::<f64>() / w.iter().sum::<f64>();
        assert_eq!(fit.reference, reference);
        // Fewer points than terms: as many terms as points.
        let few = PolynomialFit::new(4, vec![1e9, 2e9], vec![1.0, 1.0]);
        let t = few.fit(&[1.0, 3.0]);
        assert_eq!(t.len(), 4);
        // x = ∓1/3 about the 1.5 GHz reference: the line 2 + 3x.
        assert!(
            (t[0] - 2.0).abs() < 1e-12 && (t[1] - 3.0).abs() < 1e-12,
            "{t:?}"
        );
        assert!(t[2] == 0.0 && t[3] == 0.0);
    }

    #[test]
    fn a_weighted_line_matches_the_normal_equations() {
        let f = vec![1.0e9, 1.2e9, 1.4e9, 1.6e9];
        let w = vec![1.0, 4.0, 2.0, 0.5];
        let y = [2.0, 1.7, 1.1, 1.05];
        let fit = PolynomialFit::new(2, f.clone(), w.clone());
        let t = fit.fit(&y);
        let x: Vec<f64> = f.iter().map(|v| v / fit.reference - 1.0).collect();
        let (s, sx, sxx, sy, sxy) = x.iter().zip(&w).zip(&y).fold(
            (0.0, 0.0, 0.0, 0.0, 0.0),
            |(s, sx, sxx, sy, sxy), ((x, w), y)| {
                (
                    s + w,
                    sx + w * x,
                    sxx + w * x * x,
                    sy + w * y,
                    sxy + w * x * y,
                )
            },
        );
        let det = s * sxx - sx * sx;
        let b = (s * sxy - sx * sy) / det;
        let a = (sy - b * sx) / s;
        assert!(
            (t[0] - a).abs() < 1e-12 && (t[1] - b).abs() < 1e-12,
            "{t:?} {a} {b}"
        );
    }

    fn stokes(freq: Vec<f64>, vis: Vec<Complex<f32>>, weight: Vec<f32>) -> StokesI {
        let rows = vis.len() / freq.len();
        StokesI {
            uvw: vec![0.0; 3 * rows],
            freq,
            vis,
            weight,
            flag_row: vec![false; rows],
            phase_dir: (0.0, 0.0),
            rows_total: rows as u64,
            correlations: vec![9, 12],
            weight_spectrum: true,
        }
    }

    #[test]
    fn averaging_weights_and_keeps_the_last_short_group() {
        let d = stokes(
            vec![1.0, 2.0, 3.0, 4.0, 5.0],
            vec![
                Complex::new(1.0, 0.0),
                Complex::new(3.0, 2.0),
                Complex::new(5.0, 1.0),
                Complex::new(7.0, 1.0),
                Complex::new(9.0, -1.0),
            ],
            vec![1.0, 3.0, 0.0, 0.0, 2.0],
        );
        let a = average_channels(d, 2);
        assert_eq!(a.freq, vec![1.5, 3.5, 5.0]);
        assert_eq!(a.weight, vec![4.0, 0.0, 2.0]);
        assert_eq!(a.vis[0], Complex::new(2.5, 1.5));
        assert_eq!(a.vis[1], Complex::new(6.0, 1.0)); // no weight: plain mean
        assert_eq!(a.vis[2], Complex::new(9.0, -1.0));
        let s = select_channels(a, &[2, 0]);
        assert_eq!(s.freq, vec![5.0, 1.5]);
        assert_eq!(s.weight, vec![2.0, 4.0]);
    }

    #[test]
    fn dirichlet_is_the_mean_phasor_of_the_group() {
        for n in [2usize, 3, 4, 8] {
            for x in [0.0, 1e-3, 0.05, 0.2, 0.37] {
                let c = (n as f64 - 1.0) / 2.0;
                let mean: f64 = (0..n)
                    .map(|k| (2.0 * std::f64::consts::PI * x * (k as f64 - c)).cos())
                    .sum::<f64>()
                    / n as f64;
                assert!((dirichlet(n, x) - mean).abs() < 1e-12, "{n} {x}");
            }
        }
        assert_eq!(dirichlet(2, 0.0), 1.0);
    }

    #[test]
    fn averaging_peak_matches_the_direct_mean_phasor() {
        // One east-west baseline of 1 km: at radius r and azimuth φ the factor
        // is D_2(1000 r cos φ δν / c) = cos(π x); the mean of 16 directions.
        let uvw = vec![1000.0, 0.0, 0.0];
        let (dnu, r) = (1.0e6, 0.03);
        let got = averaging_peak_at(&uvw, &[1.0], 2, dnu, r);
        let want: f64 = (0..AVERAGING_AZIMUTHS)
            .map(|k| {
                let phi = 2.0 * std::f64::consts::PI * k as f64 / AVERAGING_AZIMUTHS as f64;
                let x = 1000.0 * r * phi.cos() * dnu / 299_792_458.0;
                (std::f64::consts::PI * x).cos()
            })
            .sum::<f64>()
            / AVERAGING_AZIMUTHS as f64;
        assert!((got - want).abs() < 1e-12);
        assert_eq!(averaging_peak_at(&uvw, &[1.0], 1, dnu, r), 1.0);
        assert_eq!(averaging_peak_at(&uvw, &[0.0], 2, dnu, r), 1.0);
    }
}
