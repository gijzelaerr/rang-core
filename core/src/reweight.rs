// SPDX-License-Identifier: MIT
//! Empirical visibility variances per block (issue #55, research/apply-reweight.md):
//! the statistics of a statwt-like re-weighting stage. For every block of one
//! group of rows (a baseline within a time block) and `chanbin` channels, the
//! variance of the real and of the imaginary parts of the valid samples, and their
//! mean, `(var_re + var_im) / 2`, as CASA's `statwt` computes it
//! (`StatWtVarianceAndWeightCalculator::computeVariance`, divisor N). `Classic` is
//! statwt's estimator; `Mad` the Gaussian-scaled median absolute deviation,
//! `(1.4826 MAD)^2`, robust to RFI residue.

use rayon::prelude::*;

/// The estimator of a block's variance.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Statistic {
    Classic,
    Mad,
}

/// MAD to standard deviation for Gaussian data.
pub const MAD_SCALE: f64 = 1.4826;

fn classic(x: &[f64]) -> f64 {
    let n = x.len() as f64;
    let mean = x.iter().sum::<f64>() / n;
    x.iter().map(|v| (v - mean) * (v - mean)).sum::<f64>() / n
}

fn median(x: &mut [f64]) -> f64 {
    let n = x.len();
    x.sort_by(|a, b| a.total_cmp(b));
    if n % 2 == 1 {
        x[n / 2]
    } else {
        0.5 * (x[n / 2 - 1] + x[n / 2])
    }
}

fn mad(x: &mut [f64]) -> f64 {
    let m = median(x);
    let mut dev: Vec<f64> = x.iter().map(|v| (v - m).abs()).collect();
    let s = MAD_SCALE * median(&mut dev);
    s * s
}

/// One block's variance from its real and imaginary samples (`None` for none).
pub fn block_variance(re: &mut [f64], im: &mut [f64], statistic: Statistic) -> Option<f64> {
    if re.is_empty() {
        return None;
    }
    let (vr, vi) = match statistic {
        Statistic::Classic => (classic(re), classic(im)),
        Statistic::Mad => (mad(re), mad(im)),
    };
    Some(0.5 * (vr + vi))
}

/// Per group and channel block, the variance and the number of valid samples.
///
/// `values` holds `nrow * nchan` complex values as interleaved `f32` pairs,
/// `valid` `nrow * nchan` flags (nonzero: use the sample), `group` the block
/// group of each row (`< ngroup`). Blocks are `chanbin` channels from channel 0
/// (the last one shorter when `nchan` is not a multiple). A block with fewer than
/// `minsamp` valid samples gets variance NaN. Returns `(variance, count)`, each
/// `ngroup * nblock` in group-major order. Deterministic at every thread count:
/// each block's samples are taken in row then channel order.
#[allow(clippy::too_many_arguments)]
pub fn variances(
    values: &[f32],
    valid: &[u8],
    group: &[u32],
    ngroup: usize,
    nchan: usize,
    chanbin: usize,
    statistic: Statistic,
    minsamp: usize,
) -> Result<(Vec<f64>, Vec<u64>), &'static str> {
    let nrow = group.len();
    if chanbin == 0 {
        return Err("chanbin must be at least 1");
    }
    if values.len() != 2 * nrow * nchan || valid.len() != nrow * nchan {
        return Err("values must be nrow * nchan complex and valid nrow * nchan");
    }
    if group.iter().any(|&g| g as usize >= ngroup) {
        return Err("a group index is out of range");
    }
    let nblock = nchan.div_ceil(chanbin);
    let mut rows: Vec<Vec<usize>> = vec![Vec::new(); ngroup];
    for (r, &g) in group.iter().enumerate() {
        rows[g as usize].push(r);
    }
    let out: Vec<(Vec<f64>, Vec<u64>)> = rows
        .par_iter()
        .map(|rs| {
            let mut var = vec![f64::NAN; nblock];
            let mut count = vec![0u64; nblock];
            let mut re = Vec::new();
            let mut im = Vec::new();
            for b in 0..nblock {
                re.clear();
                im.clear();
                let (c0, c1) = (b * chanbin, ((b + 1) * chanbin).min(nchan));
                for &r in rs {
                    for c in c0..c1 {
                        let cell = r * nchan + c;
                        if valid[cell] != 0 {
                            re.push(values[2 * cell] as f64);
                            im.push(values[2 * cell + 1] as f64);
                        }
                    }
                }
                count[b] = re.len() as u64;
                if re.len() >= minsamp.max(1)
                    && let Some(v) = block_variance(&mut re, &mut im, statistic)
                {
                    var[b] = v;
                }
            }
            (var, count)
        })
        .collect();
    let mut var = Vec::with_capacity(ngroup * nblock);
    let mut count = Vec::with_capacity(ngroup * nblock);
    for (v, c) in out {
        var.extend(v);
        count.extend(c);
    }
    Ok((var, count))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classic_is_the_population_variance_of_each_part_averaged() {
        let mut re = vec![1.0, 2.0, 3.0, 4.0];
        let mut im = vec![0.0, 0.0, 2.0, 2.0];
        let v = block_variance(&mut re, &mut im, Statistic::Classic).unwrap();
        assert!((v - 0.5 * (1.25 + 1.0)).abs() < 1e-15);
    }

    #[test]
    fn mad_ignores_an_outlier() {
        let mut re: Vec<f64> = (0..101).map(|i| ((i as f64) * 0.618).sin()).collect();
        let mut im = re.clone();
        let clean = block_variance(&mut re.clone(), &mut im.clone(), Statistic::Mad).unwrap();
        re[7] = 1e6;
        im[7] = -1e6;
        let dirty = block_variance(&mut re, &mut im, Statistic::Mad).unwrap();
        assert!((dirty / clean - 1.0).abs() < 0.1, "{clean} {dirty}");
    }

    #[test]
    fn blocks_groups_minsamp_and_threads() {
        let (nrow, nchan) = (6, 5);
        let values: Vec<f32> = (0..2 * nrow * nchan)
            .map(|i| ((i * 37 % 11) as f32) - 5.0)
            .collect();
        let mut valid = vec![1u8; nrow * nchan];
        valid[3] = 0;
        let group = vec![0, 1, 0, 1, 0, 1];
        let (var, count) =
            variances(&values, &valid, &group, 2, nchan, 2, Statistic::Classic, 2).unwrap();
        assert_eq!(var.len(), 2 * 3);
        assert_eq!(count, vec![6, 5, 3, 6, 6, 3]);
        let (strict, _) =
            variances(&values, &valid, &group, 2, nchan, 2, Statistic::Classic, 4).unwrap();
        assert!(strict[2].is_nan() && strict[5].is_nan() && !strict[0].is_nan());
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(1)
            .build()
            .unwrap();
        let (one, _) = pool.install(|| {
            variances(&values, &valid, &group, 2, nchan, 2, Statistic::Mad, 1).unwrap()
        });
        let (many, _) = variances(&values, &valid, &group, 2, nchan, 2, Statistic::Mad, 1).unwrap();
        assert_eq!(
            one.iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
            many.iter().map(|v| v.to_bits()).collect::<Vec<_>>()
        );
        assert!(
            variances(
                &values,
                &valid,
                &[0, 2, 0, 0, 0, 0],
                2,
                nchan,
                2,
                Statistic::Mad,
                1
            )
            .is_err()
        );
    }
}
