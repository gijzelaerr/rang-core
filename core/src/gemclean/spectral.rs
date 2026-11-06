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
}
