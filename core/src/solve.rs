//! Full-Jones `complex` gain solver, ported from QuartiCal 0.2.7.
//!
//! Portions are a Rust translation of `quartical/gains/complex/kernel.py`,
//! `quartical/gains/general/flagging.py`, `quartical/gains/general/inversion.py`
//! and `quartical/flagging/flagging.py` from QuartiCal 0.2.7, distributed
//! under the MIT License:
//!
//! > MIT License
//! >
//! > Copyright (c) 2022 Jonathan Simon Kenyon
//! >
//! > Permission is hereby granted, free of charge, to any person obtaining a
//! > copy of this software and associated documentation files (the
//! > "Software"), to deal in the Software without restriction, including
//! > without limitation the rights to use, copy, modify, merge, publish,
//! > distribute, sublicense, and/or sell copies of the Software, and to permit
//! > persons to whom the Software is furnished to do so, subject to the
//! > following conditions:
//! >
//! > The above copyright notice and this permission notice shall be included
//! > in all copies or substantial portions of the Software.
//! >
//! > THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
//! > OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
//! > MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
//! > NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
//! > DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
//! > OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
//! > USE OR OTHER DEALINGS IN THE SOFTWARE.
//!
//! The translation and its integration are part of Rang (GPL-3.0-or-later).
//! Scope and validation: `research/core-phase2.md`. One direction-independent
//! term, four correlations, one chunk, no robust reweighting, no MAD flags.
//! QuartiCal compiles with `fastmath`, so agreement is to rounding, not bits.

use crate::fused::Model;
use crate::jones::{self, C64, Jones};

/// Numbness of the divergence ladder in `update_gain_flags`.
const NUMBNESS: f64 = 1e-6;
/// Trend above which `finalize_gain_flags` hard-flags a gain.
const TREND_LIMIT: f64 = 1e-6;
/// Conjugate-gradient stopping threshold on `r^H r`.
const CG_TOLERANCE: f64 = 1e-30;

pub struct Problem<'a> {
    pub nrow: usize,
    pub nchan: usize,
    pub ntime_bins: usize,
    pub nfreq_bins: usize,
    pub nant: usize,
    /// `nrow * nchan * 8` interleaved complex64 DATA.
    pub data: &'a [f32],
    /// `nrow * nchan * 4` weights.
    pub weights: &'a [f32],
    pub model: Model<'a>,
    /// `nrow * nchan * 4` FLAG values (nonzero = flagged).
    pub flag: &'a [u8],
    /// `nrow` FLAG_ROW values.
    pub flag_row: &'a [u8],
    pub antenna1: &'a [u32],
    pub antenna2: &'a [u32],
    /// Rows must be grouped by time bin in ascending order, as in an MS chunk.
    pub time_bin: &'a [u32],
    pub freq_bin: &'a [u32],
}

#[derive(Clone, Copy, Debug)]
pub struct Settings {
    pub max_iterations: usize,
    pub stop_criterion: f64,
    pub stop_fraction: f64,
}

impl Default for Settings {
    fn default() -> Self {
        // Rang's frozen QuartiCal command, with QuartiCal's default fraction.
        Self {
            max_iterations: 50,
            stop_criterion: 1e-7,
            stop_fraction: 0.99,
        }
    }
}

#[derive(Debug)]
pub struct Solution {
    /// `ntime_bins * nfreq_bins * nant` Jones matrices.
    pub gains: Vec<Jones>,
    /// 1 hard-flagged, 0 unflagged (soft flags are cleared at the end).
    pub flags: Vec<i8>,
    pub iterations: usize,
    pub converged_fraction: f64,
}

#[derive(Debug, PartialEq)]
pub enum Error {
    Shape(&'static str),
    Order(&'static str),
    ZeroDivision,
}

const IDENTITY: Jones = [
    C64 { re: 1., im: 0. },
    C64::ZERO,
    C64::ZERO,
    C64 { re: 1., im: 0. },
];

/// CPython's (and Numba's) complex division, `_Py_c_quot`.
fn divide(a: C64, b: C64) -> Result<C64, Error> {
    if b.re == 0. && b.im == 0. {
        return Err(Error::ZeroDivision);
    }
    Ok(if b.re.abs() >= b.im.abs() {
        let ratio = b.im / b.re;
        let denom = b.re + b.im * ratio;
        C64::new((a.re + a.im * ratio) / denom, (a.im - a.re * ratio) / denom)
    } else {
        let ratio = b.re / b.im;
        let denom = b.re * ratio + b.im;
        C64::new((a.re * ratio + a.im) / denom, (a.im * ratio - a.re) / denom)
    })
}

fn real_scale(a: C64, w: f64) -> C64 {
    C64::new(a.re * w, a.im * w)
}

/// `a_kron_bt` with `a = I` as QuartiCal evaluates it for one term.
fn kron_identity(b: &Jones) -> [[C64; 4]; 4] {
    // QuartiCal unpacks b as b00, b10, b01, b11 ("effectively transpose").
    let (b00, b10, b01, b11) = (b[0], b[1], b[2], b[3]);
    let (one, zero) = (C64::new(1., 0.), C64::ZERO);
    let (a00, a01, a10, a11) = (one, zero, zero, one);
    [
        [a00 * b00, a00 * b01, a01 * b00, a01 * b01],
        [a00 * b10, a00 * b11, a01 * b10, a01 * b11],
        [a10 * b00, a10 * b01, a11 * b00, a11 * b01],
        [a10 * b10, a10 * b11, a11 * b10, a11 * b11],
    ]
}

/// `accumulate` for finite operands. With `lop = I`, `I R = R` and twelve of
/// the sixteen Kronecker entries are exact zeros, so only the products that
/// can be nonzero are formed, in the same order and with the same operands as
/// `accumulate`; a multiplication by `1` or `0` of a finite value changes at
/// most the sign of a zero, which no nonzero result depends on. Only the
/// upper triangle of `jhj` is accumulated; `fill_lower` completes it once per
/// iteration. Non-finite cells keep taking the general path, whose NaN
/// propagation through `0 * inf` this shortcut would not reproduce.
fn accumulate_finite(
    rop: &Jones,
    w: &[f64; 4],
    weighted_residual: &Jones,
    jhr: &mut [C64; 4],
    jhj: &mut [[C64; 4]; 4],
) {
    let product = mul(weighted_residual, rop);
    for k in 0..4 {
        jhr[k] = jhr[k] + product[k];
    }
    // Rows of the Kronecker product: [b00 b01 0 0], [b10 b11 0 0],
    // [0 0 b00 b01], [0 0 b10 b11] with (b00, b10, b01, b11) = rop.
    let (r0, r1, r2, r3) = (rop[0], rop[1], rop[2], rop[3]);
    let (c0, c1, c2, c3) = (r0.conj(), r1.conj(), r2.conj(), r3.conj());
    jhj[0][0] = jhj[0][0] + (real_scale(r0, w[0]) * c0 + real_scale(r2, w[1]) * c2);
    jhj[0][1] = jhj[0][1] + (real_scale(r0, w[0]) * c1 + real_scale(r2, w[1]) * c3);
    jhj[1][1] = jhj[1][1] + (real_scale(r1, w[0]) * c1 + real_scale(r3, w[1]) * c3);
    jhj[2][2] = jhj[2][2] + (real_scale(r0, w[2]) * c0 + real_scale(r2, w[3]) * c2);
    jhj[2][3] = jhj[2][3] + (real_scale(r0, w[2]) * c1 + real_scale(r2, w[3]) * c3);
    jhj[3][3] = jhj[3][3] + (real_scale(r1, w[2]) * c1 + real_scale(r3, w[3]) * c3);
}

/// Complete a Hermitian `jhj` from its upper triangle, as the last
/// `accumulate` call on a gain leaves it.
fn fill_lower(jhj: &mut [[C64; 4]; 4]) {
    for i in 1..4 {
        let (upper, lower) = jhj.split_at_mut(i);
        for (j, previous) in upper.iter().enumerate() {
            lower[0][j] = previous[i].conj();
        }
    }
}

fn finite(w: &[f64; 4]) -> bool {
    w.iter().all(|x| x.is_finite())
}

/// `jones::mul`, `jones::adjoint` and `jones::from_f32` operation for
/// operation, inlined into the row loop: the crate's default release profile
/// splits codegen units, and the out-of-line `jones::mul` call was a fifth of
/// the solver's samples after the Kronecker shortcut.
#[inline(always)]
fn mul(a: &Jones, b: &Jones) -> Jones {
    std::array::from_fn(|e| {
        let (r, c) = (e / 2, e % 2);
        a[2 * r] * b[c] + a[2 * r + 1] * b[2 + c]
    })
}

#[inline(always)]
fn adjoint(a: &Jones) -> Jones {
    std::array::from_fn(|e| a[2 * (e % 2) + e / 2].conj())
}

#[inline(always)]
fn from_f32(x: &[f32]) -> Jones {
    std::array::from_fn(|i| C64::new(f64::from(x[2 * i]), f64::from(x[2 * i + 1])))
}

#[inline(always)]
fn all_finite(a: &Jones) -> bool {
    a.iter().all(|x| x.is_finite())
}

/// One `compute_jhwj_jhwr_elem` call with `lop = I`.
fn accumulate(
    rop: &Jones,
    w: &[f64; 4],
    weighted_residual: &Jones,
    jhr: &mut [C64; 4],
    jhj: &mut [[C64; 4]; 4],
) {
    let product = jones::mul(&jones::mul(&IDENTITY, weighted_residual), rop);
    for k in 0..4 {
        jhr[k] = jhr[k] + product[k];
    }
    let kprod = kron_identity(rop);
    for i in 0..4 {
        let jh = kprod[i];
        let jhw: [C64; 4] = std::array::from_fn(|c| real_scale(jh[c], w[c]));
        let (upper, lower) = jhj.split_at_mut(i);
        for (j, previous) in upper.iter().enumerate() {
            lower[0][j] = previous[i].conj();
        }
        for j in i..4 {
            let jc = kprod[j];
            let term = jhw[0] * jc[0].conj()
                + jhw[1] * jc[1].conj()
                + jhw[2] * jc[2].conj()
                + jhw[3] * jc[3].conj();
            jhj[i][j] = jhj[i][j] + term;
        }
    }
}

fn mat_vec(a: &[[C64; 4]; 4], x: &[C64; 4]) -> [C64; 4] {
    std::array::from_fn(|i| {
        let mut out = C64::ZERO;
        for j in 0..4 {
            out = out + a[i][j] * x[j];
        }
        out
    })
}

fn dot(a: &[C64; 4], b: &[C64; 4]) -> C64 {
    let mut out = C64::ZERO;
    for i in 0..4 {
        out = out + a[i].conj() * b[i];
    }
    out
}

/// Generalised `invert`: conjugate gradients warm-started from `x`.
fn conjugate_gradient(a: &[[C64; 4]; 4], b: &[C64; 4], x: &mut [C64; 4]) -> Result<(), Error> {
    let ax = mat_vec(a, x);
    let mut r: [C64; 4] = std::array::from_fn(|i| b[i] - ax[i]);
    let mut p = r;
    let mut r_k = dot(&r, &r);
    if r_k.re == 0. && r_k.im == 0. {
        return Ok(());
    }
    for _ in 0..4 {
        let ap = mat_vec(a, &p);
        let alpha = divide(r_k, dot(&p, &ap))?;
        for i in 0..4 {
            x[i] = x[i] + alpha * p[i];
            r[i] = r[i] - alpha * ap[i];
        }
        let r_next = dot(&r, &r);
        if r_next.re < CG_TOLERANCE {
            break;
        }
        let beta = divide(r_next, r_k)?;
        for i in 0..4 {
            p[i] = p[i] * beta + r[i];
        }
        r_k = r_next;
    }
    Ok(())
}

fn check(problem: &Problem) -> Result<(), Error> {
    let cells = problem.nrow * problem.nchan;
    if problem.data.len() != 8 * cells
        || problem.weights.len() != 4 * cells
        || problem.flag.len() != 4 * cells
        || problem.flag_row.len() != problem.nrow
        || problem.antenna1.len() != problem.nrow
        || problem.antenna2.len() != problem.nrow
        || problem.time_bin.len() != problem.nrow
        || problem.freq_bin.len() != problem.nchan
    {
        return Err(Error::Shape("buffer length mismatch"));
    }
    match problem.model {
        Model::Stored(m) if m.len() != 8 * cells => return Err(Error::Shape("model length")),
        Model::Scalar(s) if s.len() != problem.nchan => {
            return Err(Error::Shape("scalar model length"));
        }
        _ => {}
    }
    if problem
        .antenna1
        .iter()
        .chain(problem.antenna2)
        .any(|&a| a as usize >= problem.nant)
        || problem
            .time_bin
            .iter()
            .any(|&t| t as usize >= problem.ntime_bins)
        || problem
            .freq_bin
            .iter()
            .any(|&f| f as usize >= problem.nfreq_bins)
    {
        return Err(Error::Shape("antenna or bin index out of range"));
    }
    if problem.time_bin.windows(2).any(|w| w[1] < w[0]) {
        return Err(Error::Order("rows must be sorted by time bin"));
    }
    Ok(())
}

/// `_initialise_flags`: FLAG or FLAG_ROW, or zero XX/YY data or weight.
pub fn data_flags(problem: &Problem) -> Vec<bool> {
    let cells = problem.nrow * problem.nchan;
    (0..cells)
        .map(|cell| {
            let row = cell / problem.nchan;
            let flagged = problem.flag[4 * cell..4 * cell + 4].iter().any(|&f| f != 0)
                || problem.flag_row[row] != 0;
            let missing = [0usize, 3].iter().any(|&c| {
                problem.data[8 * cell + 2 * c] == 0. && problem.data[8 * cell + 2 * c + 1] == 0.
            });
            let no_weight = [0usize, 3]
                .iter()
                .any(|&c| problem.weights[4 * cell + c] == 0.);
            flagged || missing || no_weight
        })
        .collect()
}

fn model_at(problem: &Problem, cell: usize, chan: usize) -> Jones {
    match problem.model {
        Model::Stored(m) => jones::from_f32(&m[8 * cell..8 * cell + 8]),
        Model::Scalar(s) => jones::scalar(s[chan]),
    }
}

/// Solve for one `complex` term as QuartiCal 0.2.7 does with rang's settings.
pub fn solve(problem: &Problem, settings: &Settings) -> Result<Solution, Error> {
    check(problem)?;
    let (nrow, nchan, na) = (problem.nrow, problem.nchan, problem.nant);
    let ngains = problem.ntime_bins * problem.nfreq_bins * na;
    let index = |t: usize, f: usize, a: usize| (t * problem.nfreq_bins + f) * na + a;
    let flags_cell = data_flags(problem);

    // init_flags: a gain stays flagged unless an unflagged cell involves it.
    let mut flags = vec![1_i8; ngains];
    for row in 0..nrow {
        let t = problem.time_bin[row] as usize;
        let (p, q) = (
            problem.antenna1[row] as usize,
            problem.antenna2[row] as usize,
        );
        for chan in 0..nchan {
            let f = problem.freq_bin[chan] as usize;
            let flag = i8::from(flags_cell[row * nchan + chan]);
            flags[index(t, f, p)] &= flag;
            flags[index(t, f, q)] &= flag;
        }
    }
    let mut gains = vec![IDENTITY; ngains];
    let mut km1_gain = gains.clone();
    let mut km1_abs2_diffs = vec![0.0_f64; ngains];
    let mut trend = vec![0.0_f64; ngains];
    let mut update = vec![[C64::ZERO; 4]; ngains];
    let mut jhj = vec![[[C64::ZERO; 4]; 4]; ngains];
    let mut jhr = vec![[C64::ZERO; 4]; ngains];
    let stop2 = settings.stop_criterion * settings.stop_criterion;
    let max_iter = settings.max_iterations;
    let mut loop_idx = 0;
    let mut converged_fraction = 0.;

    for iteration in 0..max_iter.max(1) {
        loop_idx = iteration;
        // compute_jhj_jhr
        for block in jhj.iter_mut() {
            *block = [[C64::ZERO; 4]; 4];
        }
        for vector in jhr.iter_mut() {
            *vector = [C64::ZERO; 4];
        }
        for row in 0..nrow {
            let t = problem.time_bin[row] as usize;
            let (p, q) = (
                problem.antenna1[row] as usize,
                problem.antenna2[row] as usize,
            );
            for chan in 0..nchan {
                let cell = row * nchan + chan;
                if flags_cell[cell] {
                    continue;
                }
                let f = problem.freq_bin[chan] as usize;
                let w: [f64; 4] = std::array::from_fn(|c| f64::from(problem.weights[4 * cell + c]));
                let data = from_f32(&problem.data[8 * cell..8 * cell + 8]);
                let gp = gains[index(t, f, p)];
                let gq = gains[index(t, f, q)];
                let m = model_at(problem, cell, chan);
                // rop_pq = Gq M^H, rop_qp = Gp M (lop = I for a single term).
                let rop_pq = mul(&gq, &adjoint(&m));
                let rop_qp = mul(&gp, &m);
                let ip = index(t, f, p);
                let iq = index(t, f, q);
                if all_finite(&gp) && all_finite(&rop_pq) && all_finite(&rop_qp) && finite(&w) {
                    // I^H Gp = Gp exactly for finite Gp (see accumulate_finite).
                    let predicted = mul(&gp, &adjoint(&rop_pq));
                    let residual: Jones = std::array::from_fn(|k| data[k] - predicted[k]);
                    let wr_pq: Jones = std::array::from_fn(|k| real_scale(residual[k], w[k]));
                    if all_finite(&wr_pq) {
                        let wr_qp = adjoint(&wr_pq);
                        accumulate_finite(&rop_pq, &w, &wr_pq, &mut jhr[ip], &mut jhj[ip]);
                        // QuartiCal reuses the pq weight order for qp.
                        accumulate_finite(&rop_qp, &w, &wr_qp, &mut jhr[iq], &mut jhj[iq]);
                        continue;
                    }
                }
                let lop_gp = jones::mul(&jones::adjoint(&IDENTITY), &gp);
                let predicted = jones::mul(&lop_gp, &jones::adjoint(&rop_pq));
                let residual: Jones = std::array::from_fn(|k| data[k] - predicted[k]);
                let wr_pq: Jones = std::array::from_fn(|k| real_scale(residual[k], w[k]));
                let wr_qp = jones::adjoint(&wr_pq);
                accumulate(&rop_pq, &w, &wr_pq, &mut jhr[ip], &mut jhj[ip]);
                // QuartiCal reuses the pq weight order for qp.
                accumulate(&rop_qp, &w, &wr_qp, &mut jhr[iq], &mut jhj[iq]);
            }
        }
        for block in jhj.iter_mut() {
            fill_lower(block);
        }
        // compute_update
        for g in 0..ngains {
            conjugate_gradient(&jhj[g], &jhr[g], &mut update[g])?;
        }
        // finalize_update
        for g in 0..ngains {
            if flags[g] == 1 {
                gains[g] = IDENTITY;
            } else {
                if loop_idx % 2 == 0 {
                    for value in update[g].iter_mut() {
                        *value = divide(*value, C64::new(2., 0.))?;
                    }
                }
                for k in 0..4 {
                    gains[g][k] = gains[g][k] + update[g][k];
                }
            }
        }
        // update_gain_flags
        let mut converged = 0usize;
        let mut flagged = 0usize;
        for g in 0..ngains {
            if flags[g] == 1 {
                flagged += 1;
                continue;
            }
            let mut km1_abs2 = 0.;
            let mut km0_abs2_diff = 0.;
            for k in 0..4 {
                let diff = km1_gain[g][k] - gains[g][k];
                km1_abs2 +=
                    km1_gain[g][k].re * km1_gain[g][k].re + km1_gain[g][k].im * km1_gain[g][k].im;
                km0_abs2_diff += diff.re * diff.re + diff.im * diff.im;
            }
            if km1_abs2 == 0. {
                flags[g] = 1;
                gains[g] = IDENTITY;
                flagged += 1;
                continue;
            }
            let km1_abs2_diff = km1_abs2_diffs[g];
            km1_abs2_diffs[g] = km0_abs2_diff;
            if loop_idx < 2 {
                continue;
            }
            let km1_trend = trend[g];
            let km0_trend = km1_trend + km0_abs2_diff - km1_abs2_diff;
            trend[g] = km0_trend;
            if km0_abs2_diff / km1_abs2 < stop2 {
                flags[g] = 0;
                converged += 1;
            } else if km0_trend < km1_trend && km1_trend < NUMBNESS {
                flags[g] = 0;
            } else if km0_trend > km1_trend && km1_trend > NUMBNESS {
                flags[g] = if flags[g] != 0 { 1 } else { -1 };
            }
            if flags[g] == 1 {
                flagged += 1;
                gains[g] = IDENTITY;
            }
        }
        let solvable = ngains - flagged;
        converged_fraction = if solvable > 0 {
            converged as f64 / solvable as f64
        } else {
            0.
        };
        if converged_fraction < settings.stop_fraction && loop_idx + 1 < max_iter {
            km1_gain.copy_from_slice(&gains);
        }
        if converged_fraction >= settings.stop_fraction {
            break;
        }
    }
    // finalize_gain_flags
    for g in 0..ngains {
        if trend[g] > TREND_LIMIT {
            flags[g] = 1;
            gains[g] = IDENTITY;
        } else if flags[g] == -1 {
            flags[g] = 0;
        }
    }
    Ok(Solution {
        gains,
        flags,
        iterations: loop_idx + 1,
        converged_fraction,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn simulate(truth: &[Jones], nchan: usize) -> (Vec<f32>, Vec<f32>, Vec<u32>, Vec<u32>) {
        let pairs: Vec<(u32, u32)> = (0..4)
            .flat_map(|p| ((p + 1)..4).map(move |q| (p, q)))
            .collect();
        let mut data = Vec::new();
        let mut model = Vec::new();
        for &(p, q) in &pairs {
            for chan in 0..nchan {
                let s = 1. + 0.1 * chan as f64;
                let m = jones::scalar(s);
                let v = jones::mul(
                    &jones::mul(&truth[p as usize], &m),
                    &jones::adjoint(&truth[q as usize]),
                );
                for k in 0..4 {
                    data.extend([v[k].re as f32, v[k].im as f32]);
                    model.extend([m[k].re as f32, m[k].im as f32]);
                }
            }
        }
        let a1 = pairs.iter().map(|x| x.0).collect();
        let a2 = pairs.iter().map(|x| x.1).collect();
        (data, model, a1, a2)
    }

    #[test]
    fn complex_division_matches_cpython() {
        let q = divide(C64::new(1., 2.), C64::new(3., -4.)).unwrap();
        assert!((q.re - (-0.2)).abs() < 1e-16 && (q.im - 0.4).abs() < 1e-16);
        assert_eq!(
            divide(C64::new(1., 0.), C64::ZERO),
            Err(Error::ZeroDivision)
        );
    }

    #[test]
    fn noiseless_solve_reproduces_the_visibilities() {
        let truth: Vec<Jones> = (0..4)
            .map(|a| {
                let x = 0.05 * (a as f64 + 1.);
                [
                    C64::new(1. + x, 0.1 * x),
                    C64::new(0.02, -0.01),
                    C64::new(-0.01, 0.03),
                    C64::new(0.95 - x, -0.2 * x),
                ]
            })
            .collect();
        let nchan = 8;
        let (data, model, a1, a2) = simulate(&truth, nchan);
        let nrow = a1.len();
        let problem = Problem {
            nrow,
            nchan,
            ntime_bins: 1,
            nfreq_bins: 1,
            nant: 4,
            data: &data,
            weights: &vec![1.; nrow * nchan * 4],
            model: Model::Stored(&model),
            flag: &vec![0; nrow * nchan * 4],
            flag_row: &vec![0; nrow],
            antenna1: &a1,
            antenna2: &a2,
            time_bin: &vec![0; nrow],
            freq_bin: &vec![0; nchan],
        };
        let settings = Settings {
            max_iterations: 200,
            ..Settings::default()
        };
        let solution = solve(&problem, &settings).unwrap();
        assert!(solution.flags.iter().all(|&f| f == 0));
        // Gains are determined up to a unitary, so compare baseline products.
        for (row, (&p, &q)) in a1.iter().zip(&a2).enumerate() {
            let (p, q) = (p as usize, q as usize);
            let solved = jones::mul(&solution.gains[p], &jones::adjoint(&solution.gains[q]));
            let expected = jones::mul(&truth[p], &jones::adjoint(&truth[q]));
            for k in 0..4 {
                let d = solved[k] - expected[k];
                assert!(d.norm2().sqrt() < 1e-5, "row {row} entry {k}: {d:?}");
            }
        }
    }

    #[test]
    fn unsupported_gains_stay_flagged_and_identity() {
        let truth = vec![IDENTITY; 4];
        let (data, model, a1, a2) = simulate(&truth, 2);
        let nrow = a1.len();
        // Flag every row involving antenna 3.
        let flag_row: Vec<u8> = a1
            .iter()
            .zip(&a2)
            .map(|(&p, &q)| u8::from(p == 3 || q == 3))
            .collect();
        let problem = Problem {
            nrow,
            nchan: 2,
            ntime_bins: 1,
            nfreq_bins: 1,
            nant: 4,
            data: &data,
            weights: &vec![1.; nrow * 2 * 4],
            model: Model::Stored(&model),
            flag: &vec![0; nrow * 2 * 4],
            flag_row: &flag_row,
            antenna1: &a1,
            antenna2: &a2,
            time_bin: &vec![0; nrow],
            freq_bin: &[0, 0],
        };
        let solution = solve(&problem, &Settings::default()).unwrap();
        assert_eq!(solution.flags[3], 1);
        assert_eq!(solution.gains[3], IDENTITY);
        assert!(solution.flags[..3].iter().all(|&f| f == 0));
    }

    #[test]
    fn rejects_unsorted_rows() {
        let problem = Problem {
            nrow: 2,
            nchan: 1,
            ntime_bins: 2,
            nfreq_bins: 1,
            nant: 2,
            data: &[1.; 16],
            weights: &[1.; 8],
            model: Model::Scalar(&[1.]),
            flag: &[0; 8],
            flag_row: &[0, 0],
            antenna1: &[0, 0],
            antenna2: &[1, 1],
            time_bin: &[1, 0],
            freq_bin: &[0],
        };
        assert!(matches!(
            solve(&problem, &Settings::default()),
            Err(Error::Order(_))
        ));
    }
}
