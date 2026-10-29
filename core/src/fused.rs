//! One sweep over the visibility cells: prediction, residual, split sums,
//! whitened amplitudes and antenna-diagonal Gauss--Newton blocks.
//!
//! Real parameter order per antenna follows `rang_toy::response`: XX, XY, YX,
//! YY, each as adjacent real and imaginary parts (eight parameters). Residual
//! rows use the same adjacent order, and the weight of row `k` is the weight
//! of correlation `k / 2`.

use crate::jones::{self, C64, Jones};
use crate::robust;

pub const SPLITS: usize = 3;
pub const BLOCK: usize = 8;

/// The model visibilities: a stored per-cell column or a scalar spectrum.
#[derive(Clone, Copy)]
pub enum Model<'a> {
    /// `nrow * nchan * 8` interleaved complex64 values.
    Stored(&'a [f32]),
    /// `nchan` real fluxes; the model is `S(nu) I`.
    Scalar(&'a [f64]),
}

/// Borrowed views of one block of cells and the gains that predict it.
pub struct Inputs<'a> {
    pub nrow: usize,
    pub nchan: usize,
    pub ntime_bins: usize,
    pub nfreq_bins: usize,
    pub nant: usize,
    /// `nrow * nchan * 8` interleaved complex64 DATA.
    pub data: &'a [f32],
    /// `nrow * nchan * 4` per-correlation weights.
    pub weights: &'a [f32],
    pub model: Model<'a>,
    pub antenna1: &'a [u32],
    pub antenna2: &'a [u32],
    /// Gain time bin of each row and gain frequency bin of each channel.
    pub time_bin: &'a [u32],
    pub freq_bin: &'a [u32],
    /// `ntime_bins * nfreq_bins * nant * 8` doubles: complex 2x2 gains.
    pub gains: &'a [f64],
    /// `ntime_bins * nfreq_bins * nant`, nonzero where the gain is valid.
    pub gain_valid: &'a [u8],
    /// `nrow * nchan` labels: 0 none, 1 train, 2 validation, 3 test.
    pub split: &'a [u8],
}

/// Caller-owned outputs; every slice may be empty to skip that product.
pub struct Outputs<'a> {
    /// `nrow * nchan * 8` doubles: complex128 residuals.
    pub residuals: &'a mut [f64],
    /// `nrow * nchan` robust scores, zero outside train cells.
    pub scores: &'a mut [f64],
    /// `ntime_bins * nfreq_bins * nant * 64` antenna-diagonal blocks.
    pub diag_h: &'a mut [f64],
    /// `ntime_bins * nfreq_bins * nant * 8` gradient slices.
    pub diag_b: &'a mut [f64],
    /// `ntime_bins * nfreq_bins * nant` contributing cell counts.
    pub diag_count: &'a mut [u64],
}

/// Per-split sums of the per-cell mean of `w |r|^2` over four correlations.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct SplitStats {
    pub sum: f64,
    pub cells: u64,
    pub invalid: u64,
    pub nonfinite: u64,
}

impl SplitStats {
    /// The archived loss, or None as `flagging_workflow.solve` reports it.
    pub fn loss(&self) -> Option<f64> {
        if self.invalid > 0 || self.nonfinite > 0 || self.cells == 0 {
            None
        } else {
            Some(self.sum / self.cells as f64)
        }
    }
}

#[derive(Debug, PartialEq)]
pub enum Error {
    Shape(&'static str),
    Index(&'static str),
}

fn check(inputs: &Inputs, outputs: &Outputs) -> Result<(), Error> {
    let cells = inputs
        .nrow
        .checked_mul(inputs.nchan)
        .ok_or(Error::Shape("cell count overflow"))?;
    let gains = inputs
        .ntime_bins
        .checked_mul(inputs.nfreq_bins)
        .and_then(|n| n.checked_mul(inputs.nant))
        .ok_or(Error::Shape("gain count overflow"))?;
    let optional = |len: usize, want: usize| len == 0 || len == want;
    if inputs.data.len() != 8 * cells
        || inputs.weights.len() != 4 * cells
        || inputs.split.len() != cells
        || inputs.antenna1.len() != inputs.nrow
        || inputs.antenna2.len() != inputs.nrow
        || inputs.time_bin.len() != inputs.nrow
        || inputs.freq_bin.len() != inputs.nchan
        || inputs.gains.len() != 8 * gains
        || inputs.gain_valid.len() != gains
        || !optional(outputs.residuals.len(), 8 * cells)
        || !optional(outputs.scores.len(), cells)
        || !optional(outputs.diag_h.len(), BLOCK * BLOCK * gains)
        || !optional(outputs.diag_b.len(), BLOCK * gains)
        || !optional(outputs.diag_count.len(), gains)
    {
        return Err(Error::Shape("buffer length mismatch"));
    }
    match inputs.model {
        Model::Stored(m) if m.len() != 8 * cells => {
            return Err(Error::Shape("stored model length mismatch"));
        }
        Model::Scalar(s) if s.len() != inputs.nchan => {
            return Err(Error::Shape("scalar model length mismatch"));
        }
        _ => {}
    }
    let normals = !outputs.diag_h.is_empty() || !outputs.diag_b.is_empty();
    if normals && (outputs.diag_h.is_empty() || outputs.diag_b.is_empty()) {
        return Err(Error::Shape("diag_h and diag_b go together"));
    }
    if inputs
        .antenna1
        .iter()
        .chain(inputs.antenna2)
        .any(|&a| a as usize >= inputs.nant)
        || inputs
            .time_bin
            .iter()
            .any(|&t| t as usize >= inputs.ntime_bins)
        || inputs
            .freq_bin
            .iter()
            .any(|&f| f as usize >= inputs.nfreq_bins)
        || inputs.split.iter().any(|&s| s as usize > SPLITS)
    {
        return Err(Error::Index("antenna, bin or split label out of range"));
    }
    Ok(())
}

/// Derivatives of the eight real residual-row outputs with respect to the
/// eight real parameters of one antenna, for `V = Gp M Gq^H`.
/// `left` is `Gp M` and `right` is `M Gq^H`.
/// For the p antenna, `dV = E right`; for q, `dV = left E^H`, so the
/// imaginary-part column carries the opposite sign.
fn antenna_jacobian(left: &Jones, right: &Jones, is_q: bool) -> [[f64; BLOCK]; BLOCK] {
    let mut out = [[0.; BLOCK]; BLOCK];
    for entry in 0..4 {
        let mut basis = [C64::ZERO; 4];
        basis[entry].re = 1.;
        let derivative = if is_q {
            jones::mul(left, &jones::adjoint(&basis))
        } else {
            jones::mul(&basis, right)
        };
        let sign = if is_q { -1. } else { 1. };
        for (output, value) in derivative.iter().enumerate() {
            let column = 2 * entry;
            out[2 * output][column] = value.re;
            out[2 * output + 1][column] = value.im;
            out[2 * output][column + 1] = -sign * value.im;
            out[2 * output + 1][column + 1] = sign * value.re;
        }
    }
    out
}

fn accumulate(
    h: &mut [f64],
    b: &mut [f64],
    jac: &[[f64; BLOCK]; BLOCK],
    weights: &[f64; 4],
    residual: &[f64; BLOCK],
) {
    for (row, values) in jac.iter().enumerate() {
        let w = weights[row / 2];
        for i in 0..BLOCK {
            let wi = w * values[i];
            b[i] += wi * residual[row];
            for k in 0..BLOCK {
                h[i * BLOCK + k] += wi * values[k];
            }
        }
    }
}

/// Run the fused pass. Returns per-split statistics in train, validation,
/// test order. Normals use train cells whose prediction is valid.
pub fn run(inputs: &Inputs, outputs: &mut Outputs) -> Result<[SplitStats; SPLITS], Error> {
    check(inputs, outputs)?;
    let (nrow, nchan, na) = (inputs.nrow, inputs.nchan, inputs.nant);
    let want_scores = !outputs.scores.is_empty();
    let want_normals = !outputs.diag_h.is_empty();
    outputs.scores.fill(0.);
    outputs.diag_h.fill(0.);
    outputs.diag_b.fill(0.);
    outputs.diag_count.fill(0);
    let mut stats = [SplitStats::default(); SPLITS];
    // Per-baseline log amplitudes of whitened train residuals, with cell index.
    let mut amplitudes: Vec<Vec<(usize, f64)>> = vec![Vec::new(); na * na];
    for row in 0..nrow {
        let (p, q) = (inputs.antenna1[row] as usize, inputs.antenna2[row] as usize);
        let t = inputs.time_bin[row] as usize;
        for chan in 0..nchan {
            let cell = row * nchan + chan;
            let f = inputs.freq_bin[chan] as usize;
            let gp_index = (t * inputs.nfreq_bins + f) * na + p;
            let gq_index = (t * inputs.nfreq_bins + f) * na + q;
            let gp = jones::from_f64(&inputs.gains[8 * gp_index..8 * gp_index + 8]);
            let gq = jones::from_f64(&inputs.gains[8 * gq_index..8 * gq_index + 8]);
            let model = match inputs.model {
                Model::Stored(m) => jones::from_f32(&m[8 * cell..8 * cell + 8]),
                Model::Scalar(s) => jones::scalar(s[chan]),
            };
            let left = jones::mul(&gp, &model);
            let right = jones::mul(&model, &jones::adjoint(&gq));
            let predicted = jones::mul(&left, &jones::adjoint(&gq));
            let data = jones::from_f32(&inputs.data[8 * cell..8 * cell + 8]);
            let residual: Jones = std::array::from_fn(|k| data[k] - predicted[k]);
            if !outputs.residuals.is_empty() {
                for (k, value) in residual.iter().enumerate() {
                    outputs.residuals[8 * cell + 2 * k] = value.re;
                    outputs.residuals[8 * cell + 2 * k + 1] = value.im;
                }
            }
            let weights: [f64; 4] =
                std::array::from_fn(|k| f64::from(inputs.weights[4 * cell + k]));
            let valid = inputs.gain_valid[gp_index] != 0
                && inputs.gain_valid[gq_index] != 0
                && jones::is_finite(&gp)
                && jones::is_finite(&gq);
            let label = inputs.split[cell] as usize;
            if label > 0 {
                let stat = &mut stats[label - 1];
                stat.cells += 1;
                if !valid {
                    stat.invalid += 1;
                }
                let mse = residual
                    .iter()
                    .zip(&weights)
                    .map(|(r, w)| r.norm2() * w)
                    .sum::<f64>()
                    / 4.;
                if mse.is_finite() {
                    stat.sum += mse;
                } else {
                    stat.nonfinite += 1;
                }
            }
            if label == 1 && want_scores {
                // Whitening multiplies by sqrt(w) computed in single precision,
                // as NumPy does for float32 weights.
                let amplitude = residual
                    .iter()
                    .enumerate()
                    .map(|(k, r)| {
                        let s = f64::from(inputs.weights[4 * cell + k].sqrt());
                        r.scale(s).norm2()
                    })
                    .sum::<f64>()
                    .sqrt();
                if amplitude.is_finite() {
                    amplitudes[p * na + q].push((cell, amplitude.max(1e-30).ln()));
                }
            }
            if label == 1 && want_normals && valid {
                let rows: [f64; BLOCK] = std::array::from_fn(|k| {
                    let value = residual[k / 2];
                    if k % 2 == 0 { value.re } else { value.im }
                });
                for (index, is_q) in [(gp_index, false), (gq_index, true)] {
                    let jac = antenna_jacobian(&left, &right, is_q);
                    accumulate(
                        &mut outputs.diag_h[64 * index..64 * index + 64],
                        &mut outputs.diag_b[8 * index..8 * index + 8],
                        &jac,
                        &weights,
                        &rows,
                    );
                    outputs.diag_count[index] += 1;
                }
            }
        }
    }
    if want_scores {
        for baseline in &amplitudes {
            let values: Vec<f64> = baseline.iter().map(|(_, v)| *v).collect();
            for ((cell, _), z) in baseline.iter().zip(robust::scores(&values)) {
                outputs.scores[*cell] = z;
            }
        }
    }
    Ok(stats)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn identity_gains(n: usize) -> Vec<f64> {
        (0..n)
            .flat_map(|_| [1., 0., 0., 0., 0., 0., 1., 0.])
            .collect()
    }

    #[test]
    fn jacobian_matches_rang_toy() {
        let gp = [1.1, 0.2, 0.05, -0.01, 0.02, 0.03, 0.9, -0.1];
        let gq = [0.8, -0.3, 0.01, 0.02, -0.04, 0.01, 1.2, 0.2];
        let model = [2.0, 0.1, 0.3, -0.2, 0.25, 0.15, 1.5, -0.05];
        let reference = rang_toy::response::jacobian(&gp, &gq, &model).unwrap();
        let (jp, jq, jm) = (
            jones::from_f64(&gp),
            jones::from_f64(&gq),
            jones::from_f64(&model),
        );
        let left = jones::mul(&jp, &jm);
        let right = jones::mul(&jm, &jones::adjoint(&jq));
        for (station, is_q) in [(0, false), (1, true)] {
            let jac = antenna_jacobian(&left, &right, is_q);
            for (row, values) in jac.iter().enumerate() {
                for (k, value) in values.iter().enumerate() {
                    let expected = reference[row * 16 + station * 8 + k];
                    assert!((value - expected).abs() < 1e-15, "{station} {row} {k}");
                }
            }
        }
    }

    #[test]
    fn identity_gains_give_data_minus_model() {
        let (nrow, nchan) = (2, 3);
        let data: Vec<f32> = (0..nrow * nchan * 8).map(|i| i as f32 * 0.5).collect();
        let weights = vec![2.0_f32; nrow * nchan * 4];
        let flux = vec![1.0, 2.0, 3.0];
        let inputs = Inputs {
            nrow,
            nchan,
            ntime_bins: 1,
            nfreq_bins: 1,
            nant: 2,
            data: &data,
            weights: &weights,
            model: Model::Scalar(&flux),
            antenna1: &[0, 0],
            antenna2: &[1, 1],
            time_bin: &[0, 0],
            freq_bin: &[0, 0, 0],
            gains: &identity_gains(2),
            gain_valid: &[1, 1],
            split: &[1, 2, 3, 1, 2, 0],
        };
        let mut residuals = vec![0.; nrow * nchan * 8];
        let mut outputs = Outputs {
            residuals: &mut residuals,
            scores: &mut [],
            diag_h: &mut [],
            diag_b: &mut [],
            diag_count: &mut [],
        };
        let stats = run(&inputs, &mut outputs).unwrap();
        for cell in 0..nrow * nchan {
            let s = flux[cell % nchan];
            for k in 0..8 {
                let model = if k == 0 || k == 6 { s } else { 0. };
                let expected = f64::from(data[8 * cell + k]) - model;
                assert_eq!(residuals[8 * cell + k], expected);
            }
        }
        assert_eq!(stats[0].cells, 2);
        assert_eq!(stats[2].cells, 1);
        assert!(stats.iter().all(|s| s.invalid == 0));
    }

    #[test]
    fn diagonal_blocks_match_full_normals() {
        let gains: Vec<f64> = (0..4)
            .flat_map(|a| {
                let x = 0.1 * a as f64;
                [1. + x, 0.1, 0.02, -x, 0.01, 0.03, 0.9 - x, 0.05]
            })
            .collect();
        let pairs = [(0u32, 1u32), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)];
        let nrow = pairs.len();
        let nchan = 2;
        let data: Vec<f32> = (0..nrow * nchan * 8)
            .map(|i| ((i * 37 % 11) as f32 - 5.) * 0.3)
            .collect();
        let model: Vec<f32> = (0..nrow * nchan * 8)
            .map(|i| ((i * 13 % 7) as f32 - 3.) * 0.2)
            .collect();
        let weights: Vec<f32> = (0..nrow * nchan * 4).map(|i| 1. + (i % 3) as f32).collect();
        let a1: Vec<u32> = pairs.iter().map(|x| x.0).collect();
        let a2: Vec<u32> = pairs.iter().map(|x| x.1).collect();
        let inputs = Inputs {
            nrow,
            nchan,
            ntime_bins: 1,
            nfreq_bins: 1,
            nant: 4,
            data: &data,
            weights: &weights,
            model: Model::Stored(&model),
            antenna1: &a1,
            antenna2: &a2,
            time_bin: &vec![0; nrow],
            freq_bin: &[0, 0],
            gains: &gains,
            gain_valid: &[1; 4],
            split: &vec![1; nrow * nchan],
        };
        let mut residuals = vec![0.; nrow * nchan * 8];
        let mut h = vec![0.; 4 * 64];
        let mut b = vec![0.; 4 * 8];
        let mut counts = vec![0; 4];
        let mut outputs = Outputs {
            residuals: &mut residuals,
            scores: &mut [],
            diag_h: &mut h,
            diag_b: &mut b,
            diag_count: &mut counts,
        };
        run(&inputs, &mut outputs).unwrap();
        let samples = nrow * nchan;
        let models: Vec<f64> = model.iter().map(|x| f64::from(*x)).collect();
        let w: Vec<f64> = weights.iter().map(|x| f64::from(*x)).collect();
        let p: Vec<usize> = (0..samples).map(|s| a1[s / nchan] as usize).collect();
        let q: Vec<usize> = (0..samples).map(|s| a2[s / nchan] as usize).collect();
        let (full_h, full_b, _) = rang_toy::response::normals(
            1,
            &gains,
            &models,
            &residuals,
            &w,
            &p,
            &q,
            &vec![0; samples],
        )
        .unwrap();
        let scale = full_h.iter().fold(0_f64, |a, x| a.max(x.abs()));
        for a in 0..4 {
            for i in 0..8 {
                let bi = full_b[a * 8 + i];
                assert!((b[a * 8 + i] - bi).abs() <= 1e-13 * scale.max(1.));
                for k in 0..8 {
                    let expected = full_h[(a * 8 + i) * 32 + a * 8 + k];
                    assert!((h[a * 64 + i * 8 + k] - expected).abs() <= 1e-13 * scale);
                }
            }
        }
        assert_eq!(counts, vec![6, 6, 6, 6]);
    }

    #[test]
    fn invalid_gain_marks_split_and_skips_normals() {
        let data = vec![1.0_f32; 8];
        let weights = vec![1.0_f32; 4];
        let inputs = Inputs {
            nrow: 1,
            nchan: 1,
            ntime_bins: 1,
            nfreq_bins: 1,
            nant: 2,
            data: &data,
            weights: &weights,
            model: Model::Scalar(&[1.0]),
            antenna1: &[0],
            antenna2: &[1],
            time_bin: &[0],
            freq_bin: &[0],
            gains: &identity_gains(2),
            gain_valid: &[1, 0],
            split: &[1],
        };
        let mut h = vec![0.; 2 * 64];
        let mut b = vec![0.; 2 * 8];
        let mut counts = vec![0; 2];
        let mut outputs = Outputs {
            residuals: &mut [],
            scores: &mut [],
            diag_h: &mut h,
            diag_b: &mut b,
            diag_count: &mut counts,
        };
        let stats = run(&inputs, &mut outputs).unwrap();
        assert_eq!(stats[0].invalid, 1);
        assert_eq!(stats[0].loss(), None);
        assert_eq!(counts, vec![0, 0]);
    }

    #[test]
    fn rejects_bad_shapes() {
        let inputs = Inputs {
            nrow: 1,
            nchan: 1,
            ntime_bins: 1,
            nfreq_bins: 1,
            nant: 2,
            data: &[0.; 7],
            weights: &[1.; 4],
            model: Model::Scalar(&[1.0]),
            antenna1: &[0],
            antenna2: &[1],
            time_bin: &[0],
            freq_bin: &[0],
            gains: &identity_gains(2),
            gain_valid: &[1, 1],
            split: &[1],
        };
        let mut outputs = Outputs {
            residuals: &mut [],
            scores: &mut [],
            diag_h: &mut [],
            diag_b: &mut [],
            diag_count: &mut [],
        };
        assert!(run(&inputs, &mut outputs).is_err());
    }
}
