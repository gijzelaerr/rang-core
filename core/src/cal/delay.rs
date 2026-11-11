// SPDX-License-Identifier: GPL-3.0-or-later AND MIT
//! The delay term K: QuartiCal 0.2.7's `delay` term with its FFT initial
//! estimate (task C2b, `research/c2b-delay.md`; C1 step 4,
//! `research/c1-calibration-chain.md`).
//!
//! Portions are a Rust translation of `quartical/gains/delay/kernel.py`,
//! `quartical/gains/delay/__init__.py` (`Delay.init_term`),
//! `quartical/gains/general/flagging.py` and
//! `quartical/gains/general/inversion.py` from QuartiCal 0.2.7, distributed
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
//!
//! Scope: one direction-independent term, four correlations (`XX, XY, YX,
//! YY`), one chunk, parallel hands only, no robust reweighting and no MAD
//! flags, as `diag.rs` (whose small helpers are copied here, C1 section 4
//! rule 1). `Problem::freq_bin` maps channels to parameter frequency bins;
//! the gains are evaluated in every channel, as QuartiCal's `Delay` does.
//!
//! - Parameters are `tau * nu_mid` (`nu_mid = (min + max) / 2` of the
//!   channel frequencies), gains `exp(i 2 pi (nu / nu_mid - 1) p)`.
//! - The data are scaled to the model's amplitude and the residual
//!   normalised by `|J|^2` (as `phase`); conjugate gradients on the real 2x2
//!   normal equations warm-started from the last update; every update
//!   halved; numbness 1e9; the gain flags are per channel and a parameter is
//!   flagged when every one of its channels is.
//! - The initial estimate is `Delay.init_term`'s FFT on the reference
//!   antenna's baselines.
//!
//! Every interval runs an iteration on rayon's pool and the global stop test
//! (the converged fraction over all per-channel gains) sums integer counts
//! serially, so the result does not depend on the thread count.

use crate::cal::diag::{Error, Trace};
use crate::fused::Model;
use crate::jones::{self, C64, Jones};
use crate::solve::Problem;
use rayon::prelude::*;
use rustfft::FftPlanner;
use rustfft::num_complex::Complex;

/// Numbness of the delay kernel (`update_gain_flags(..., numbness=1e9)`).
const NUMBNESS: f64 = 1e9;
/// Trend above which `finalize_gain_flags` hard-flags a gain.
const TREND_LIMIT: f64 = 1e-6;
/// Conjugate-gradient stopping threshold on `r^T r` (generalised `invert`).
const CG_TOLERANCE: f64 = 1e-30;
/// The initial estimate's FFT length is the multiple of the channel count
/// at or above this.
const ESTIMATE_POINTS: usize = 1 << 15;

#[derive(Clone, Copy, Debug)]
pub struct Settings {
    pub max_iterations: usize,
    pub stop_criterion: f64,
    pub stop_fraction: f64,
    /// QuartiCal's `solver.reference_antenna` for `reference_params`;
    /// `None` leaves the delays unreferenced.
    pub reference_antenna: Option<usize>,
    /// The antenna whose baselines give the FFT initial estimate (QuartiCal's
    /// reference antenna); `None` starts from zero delays
    /// (`initial_estimate=false`).
    pub estimate_antenna: Option<usize>,
}

impl Settings {
    /// Rang's frozen QuartiCal settings, with the initial estimate on.
    pub fn new() -> Self {
        Self {
            max_iterations: 50,
            stop_criterion: 1e-7,
            stop_fraction: 0.99,
            reference_antenna: Some(0),
            estimate_antenna: Some(0),
        }
    }
}

impl Default for Settings {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Clone)]
pub struct Solution {
    /// `ntime_bins * nfreq_bins * nant` delays `[tau_x, tau_y]` in seconds.
    pub delays: Vec<[f64; 2]>,
    /// Parameter flags (1 flagged), per delay.
    pub flags: Vec<i8>,
    /// `ntime_bins * nchan * nant` gains `[g_x, g_y]` per channel.
    pub gains: Vec<[C64; 2]>,
    /// Gain flags per channel.
    pub gain_flags: Vec<i8>,
    pub iterations: usize,
    pub converged_fraction: f64,
}

const ONE: C64 = C64 { re: 1., im: 0. };
const IDENTITY: Jones = [ONE, C64::ZERO, C64::ZERO, ONE];

fn real_scale(a: C64, w: f64) -> C64 {
    C64::new(a.re * w, a.im * w)
}

fn diag(g: &[C64; 2]) -> Jones {
    [g[0], C64::ZERO, C64::ZERO, g[1]]
}

fn check(problem: &Problem, freq: &[f64], settings: &Settings) -> Result<(), Error> {
    let cells = problem.nrow * problem.nchan;
    if problem.data.len() != 8 * cells
        || problem.weights.len() != 4 * cells
        || problem.flag.len() != 4 * cells
        || problem.flag_row.len() != problem.nrow
        || problem.antenna1.len() != problem.nrow
        || problem.antenna2.len() != problem.nrow
        || problem.time_bin.len() != problem.nrow
        || problem.freq_bin.len() != problem.nchan
        || freq.len() != problem.nchan
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
    if [settings.reference_antenna, settings.estimate_antenna]
        .iter()
        .flatten()
        .any(|&r| r >= problem.nant)
    {
        return Err(Error::Settings("reference antenna out of range"));
    }
    if !(settings.stop_criterion.is_finite() && settings.stop_fraction.is_finite()) {
        return Err(Error::Settings(
            "stop criterion and fraction must be finite",
        ));
    }
    if problem.nchan < 2 && settings.estimate_antenna.is_some() {
        return Err(Error::Settings("the initial estimate needs two channels"));
    }
    if freq.iter().any(|f| !f.is_finite()) {
        return Err(Error::Settings("channel frequencies must be finite"));
    }
    Ok(())
}

fn model_at(problem: &Problem, cell: usize, chan: usize) -> Jones {
    match problem.model {
        Model::Stored(m) => jones::from_f32(&m[8 * cell..8 * cell + 8]),
        Model::Scalar(s) => jones::scalar(s[chan]),
    }
}

/// `(MIN_FREQ + MAX_FREQ) / 2` of the window.
pub fn mid_frequency(freq: &[f64]) -> f64 {
    let lo = freq.iter().copied().fold(f64::INFINITY, f64::min);
    let hi = freq.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    (lo + hi) / 2.
}

/// What the solver keeps per parameter (antenna of an interval).
#[derive(Clone, Copy)]
struct ParamState {
    /// The two parameters, `tau * nu_mid` while solving.
    params: [f64; 2],
    flag: bool,
    jhj: [f64; 4],
    jhr: [f64; 2],
    update: [f64; 2],
}

/// What the solver keeps per gain (channel and antenna of an interval).
#[derive(Clone, Copy)]
struct GainState {
    gain: [C64; 2],
    km1_gain: [C64; 2],
    km1_abs2_diff: f64,
    trend: f64,
    flag: i8,
}

struct CellRef {
    cell: usize,
    p: u32,
    q: u32,
}

/// One solution interval: its parameters (per antenna), its gains (per
/// channel of the bin, then antenna) and its unflagged cells.
struct Interval {
    channels: Vec<usize>,
    params: Vec<ParamState>,
    gains: Vec<GainState>,
    cells: Vec<CellRef>,
}

/// The intervals in `(time bin, frequency bin)` order, with QuartiCal's
/// `init_flags` for parameters and per-channel gains: flagged unless an
/// unflagged cell involves the antenna.
fn intervals(problem: &Problem, flags_cell: &[bool]) -> Vec<Interval> {
    let na = problem.nant;
    let mut rows = Vec::with_capacity(problem.ntime_bins);
    let mut start = 0;
    for t in 0..problem.ntime_bins {
        let end = start
            + problem.time_bin[start..]
                .iter()
                .take_while(|&&b| b as usize == t)
                .count();
        rows.push(start..end);
        start = end;
    }
    let mut channels = vec![Vec::new(); problem.nfreq_bins];
    for (chan, &f) in problem.freq_bin.iter().enumerate() {
        channels[f as usize].push(chan);
    }
    let mut local = vec![0usize; problem.nchan];
    for list in &channels {
        for (i, &c) in list.iter().enumerate() {
            local[c] = i;
        }
    }
    (0..problem.ntime_bins * problem.nfreq_bins)
        .into_par_iter()
        .map(|i| {
            let (t, fb) = (i / problem.nfreq_bins, i % problem.nfreq_bins);
            let chans = channels[fb].clone();
            let mut params = vec![
                ParamState {
                    params: [0.; 2],
                    flag: true,
                    jhj: [0.; 4],
                    jhr: [0.; 2],
                    update: [0.; 2],
                };
                na
            ];
            let mut gains = vec![
                GainState {
                    gain: [ONE, ONE],
                    km1_gain: [ONE, ONE],
                    km1_abs2_diff: 0.,
                    trend: 0.,
                    flag: 1,
                };
                chans.len() * na
            ];
            let mut cells = Vec::new();
            for row in rows[t].clone() {
                let (p, q) = (problem.antenna1[row], problem.antenna2[row]);
                for &chan in &chans {
                    let cell = row * problem.nchan + chan;
                    if !flags_cell[cell] {
                        cells.push(CellRef { cell, p, q });
                        params[p as usize].flag = false;
                        params[q as usize].flag = false;
                        gains[local[chan] * na + p as usize].flag = 0;
                        gains[local[chan] * na + q as usize].flag = 0;
                    }
                }
            }
            Interval {
                channels: chans,
                params,
                gains,
                cells,
            }
        })
        .collect()
}

/// `Delay.init_term`'s initial estimate: per time bin, the data of the
/// baselines to `refant` (flagged cells zeroed) averaged per antenna and
/// channel; per frequency bin and parallel hand the peak of `|FFT|`,
/// zero-padded to `ceil(2^15 / n) * n` points; `-peak` for antennas after
/// the refant in a row (`p == refant`), `+peak` before it. Delays in seconds,
/// `ntime_bins * nfreq_bins * nant`.
pub fn initial_estimate(
    problem: &Problem,
    freq: &[f64],
    flags_cell: &[bool],
    refant: usize,
) -> Vec<[f64; 2]> {
    let (na, nchan, nfb) = (problem.nant, problem.nchan, problem.nfreq_bins);
    let mut out = vec![[0f64; 2]; problem.ntime_bins * nfb * na];
    let mut channels = vec![Vec::new(); nfb];
    for (chan, &f) in problem.freq_bin.iter().enumerate() {
        channels[f as usize].push(chan);
    }
    let delta = freq[1] - freq[0];
    let mut planner = FftPlanner::<f64>::new();
    let mut start = 0;
    for t in 0..problem.ntime_bins {
        let end = start
            + problem.time_bin[start..]
                .iter()
                .take_while(|&&b| b as usize == t)
                .count();
        let sel: Vec<usize> = (start..end)
            .filter(|&r| {
                let (p, q) = (problem.antenna1[r] as usize, problem.antenna2[r] as usize);
                (p == refant || q == refant) && p != q
            })
            .collect();
        start = end;
        if sel.is_empty() {
            continue;
        }
        let mut sum = vec![[C64::ZERO; 4]; na * nchan];
        let mut count = vec![0u64; na * nchan];
        for &row in &sel {
            let (p, q) = (
                problem.antenna1[row] as usize,
                problem.antenna2[row] as usize,
            );
            let ant = if p == refant { q } else { p };
            for chan in 0..nchan {
                let cell = row * nchan + chan;
                if flags_cell[cell] {
                    continue;
                }
                let d = jones::from_f32(&problem.data[8 * cell..8 * cell + 8]);
                let s = &mut sum[ant * nchan + chan];
                for k in 0..4 {
                    s[k] = s[k] + d[k];
                }
                count[ant * nchan + chan] += 1;
            }
        }
        for (s, &c) in sum.iter_mut().zip(&count) {
            if c != 0 {
                let c = c as f64;
                for v in s.iter_mut() {
                    *v = C64::new(v.re / c, v.im / c);
                }
            }
        }
        for (fb, chans) in channels.iter().enumerate() {
            if chans.is_empty() {
                continue;
            }
            let nsel = chans.len();
            let n = ESTIMATE_POINTS.div_ceil(nsel) * nsel;
            let fft = planner.plan_fft_forward(n);
            let val = 1.0 / (n as f64 * delta);
            let positive = (n - 1) / 2 + 1;
            let freq_of = |k: usize| {
                let i = if k < positive {
                    k as i64
                } else {
                    k as i64 - n as i64
                };
                i as f64 * val
            };
            let mut est = vec![[0f64; 2]; na];
            let mut buffer = vec![Complex::new(0f64, 0f64); n];
            for (a, e) in est.iter_mut().enumerate() {
                let valid = chans
                    .iter()
                    .any(|&c| sum[a * nchan + c].iter().any(|v| v.re != 0. || v.im != 0.));
                if !valid {
                    continue;
                }
                for (h, corr) in [(0usize, 0usize), (1, 3)] {
                    buffer.iter_mut().for_each(|b| *b = Complex::new(0., 0.));
                    for (j, &c) in chans.iter().enumerate() {
                        let v = sum[a * nchan + c][corr];
                        buffer[j] = Complex::new(v.re, v.im);
                    }
                    fft.process(&mut buffer);
                    // argmax over the fftshift-ed amplitudes, first maximum.
                    let shift = n / 2;
                    let mut best_k = (n - shift) % n;
                    let mut best = buffer[best_k].re.hypot(buffer[best_k].im);
                    for s in 1..n {
                        let k = (s + n - shift) % n;
                        let amp = buffer[k].re.hypot(buffer[k].im);
                        if amp > best {
                            best = amp;
                            best_k = k;
                        }
                    }
                    e[h] = freq_of(best_k);
                }
            }
            for &row in &sel {
                let (p, q) = (
                    problem.antenna1[row] as usize,
                    problem.antenna2[row] as usize,
                );
                let base = (t * nfb + fb) * na;
                if p == refant {
                    out[base + q] = [-est[q][0], -est[q][1]];
                } else {
                    out[base + p] = est[p];
                }
            }
        }
    }
    out
}

/// `iabsdivsq` on one value: `0` for `0`, else `1/|v|^2`.
fn absdivsq(v: C64) -> C64 {
    if v.re == 0. && v.im == 0. {
        C64::ZERO
    } else {
        C64::new(1. / (v.re * v.re + v.im * v.im), 0.)
    }
}

/// `compute_jhwj_jhwr_elem` of `delay` (four correlations, lop = I).
fn elem(
    rop: &Jones,
    w: &[f64; 4],
    gain: &[C64; 2],
    res: &Jones,
    coeff: f64,
    jhr: &mut [f64; 2],
    jhj: &mut [f64; 4],
) {
    let res = [res[0], C64::ZERO, C64::ZERO, res[3]];
    let lr = jones::mul(&IDENTITY, rop);
    let normf: Jones = std::array::from_fn(|k| absdivsq(lr[k]));
    let res: Jones = std::array::from_fn(|k| res[k] * normf[k]);
    let res = jones::mul(&IDENTITY, &jones::mul(&res, rop));
    let (r_0, r_3) = (res[0], res[3]);
    let (gc_0, gc_3) = (gain[0].conj(), gain[1].conj());
    let minus_i = C64::new(-0., -1.);
    let upd_00 = (minus_i * gc_0 * r_0).re;
    let upd_11 = (minus_i * gc_3 * r_3).re;
    jhr[0] += coeff * upd_00;
    jhr[1] += coeff * upd_11;
    let w_0 = normf[0] * C64::new(w[0], 0.);
    let w_3 = normf[3] * C64::new(w[3], 0.);
    // lop = I: jh_00 = rop0, jh_33 = rop3, jh_03 = jh_30 = 0, so the
    // off-diagonal jhwj_03 is zero.
    let (jh_00, jh_33) = (ONE * rop[0], ONE * rop[3]);
    let jhwj_00 = jh_00 * w_0 * jh_00.conj();
    let jhwj_33 = jh_33 * w_3 * jh_33.conj();
    let coeffsq = coeff * coeff;
    jhj[0] += coeffsq * jhwj_00.re;
    jhj[3] += coeffsq * jhwj_33.re;
}

/// Generalised `invert`: conjugate gradients on the real 2x2 system,
/// warm-started from `x`, at most two steps (copied from `diag.rs`).
fn conjugate_gradient(a: &[f64; 4], b: &[f64; 2], x: &mut [f64; 2]) -> Result<(), Error> {
    let mat_vec = |v: &[f64; 2]| [a[0] * v[0] + a[1] * v[1], a[2] * v[0] + a[3] * v[1]];
    let dot = |u: &[f64; 2], v: &[f64; 2]| u[0] * v[0] + u[1] * v[1];
    let ax = mat_vec(x);
    let mut r = [b[0] - ax[0], b[1] - ax[1]];
    let mut p = r;
    let mut r_k = dot(&r, &r);
    if r_k == 0. {
        return Ok(());
    }
    for _ in 0..2 {
        let ap = mat_vec(&p);
        let denom = dot(&p, &ap);
        if denom == 0. {
            return Err(Error::ZeroDivision);
        }
        let alpha = r_k / denom;
        for i in 0..2 {
            x[i] += alpha * p[i];
            r[i] -= alpha * ap[i];
        }
        let r_next = dot(&r, &r);
        if r_next < CG_TOLERANCE {
            break;
        }
        let beta = r_next / r_k;
        for i in 0..2 {
            p[i] = p[i] * beta + r[i];
        }
        r_k = r_next;
    }
    Ok(())
}

/// `exp(1j * coeff * p)` per hand, as Numba evaluates it.
fn param_to_gain(p: &[f64; 2], coeff: f64) -> [C64; 2] {
    std::array::from_fn(|h| {
        let x = coeff * p[h];
        C64::new(x.cos(), x.sin())
    })
}

/// `update_gain_flags` for one gain (copied from `diag.rs`'s ladder).
fn flag_ladder(state: &mut GainState, loop_idx: usize, stop2: f64) -> (bool, bool) {
    if state.flag == 1 {
        return (false, true);
    }
    let mut km1_abs2 = 0.;
    let mut km0_abs2_diff = 0.;
    for k in 0..2 {
        let (old, new) = (state.km1_gain[k], state.gain[k]);
        let diff = old - new;
        km1_abs2 += old.re * old.re + old.im * old.im;
        km0_abs2_diff += diff.re * diff.re + diff.im * diff.im;
    }
    if km1_abs2 == 0. {
        state.flag = 1;
        state.gain = [ONE, ONE];
        return (false, true);
    }
    let km1_abs2_diff = state.km1_abs2_diff;
    state.km1_abs2_diff = km0_abs2_diff;
    if loop_idx < 2 {
        return (false, false);
    }
    let km1_trend = state.trend;
    let km0_trend = km1_trend + km0_abs2_diff - km1_abs2_diff;
    state.trend = km0_trend;
    let mut converged = false;
    if km0_abs2_diff / km1_abs2 < stop2 {
        state.flag = 0;
        converged = true;
    } else if km0_trend < km1_trend && km1_trend < NUMBNESS {
        state.flag = 0;
    } else if km0_trend > km1_trend && km1_trend > NUMBNESS {
        state.flag = if state.flag != 0 { 1 } else { -1 };
    }
    if state.flag == 1 {
        state.gain = [ONE, ONE];
        return (converged, true);
    }
    (converged, false)
}

impl Interval {
    /// `compute_jhj_jhr` for this interval.
    fn accumulate(&mut self, problem: &Problem, coeff: &[f64], local: &[usize]) {
        let na = problem.nant;
        for s in self.params.iter_mut() {
            s.jhj = [0.; 4];
            s.jhr = [0.; 2];
        }
        for c in &self.cells {
            let (p, q, cell) = (c.p as usize, c.q as usize, c.cell);
            let chan = cell % problem.nchan;
            let li = local[chan];
            let w: [f64; 4] = std::array::from_fn(|k| f64::from(problem.weights[4 * cell + k]));
            let data = jones::from_f32(&problem.data[8 * cell..8 * cell + 8]);
            let m = model_at(problem, cell, chan);
            let (gp, gq) = (self.gains[li * na + p].gain, self.gains[li * na + q].gain);
            let (dp, dq) = (diag(&gp), diag(&gq));
            let rop_pq = jones::mul(&dq, &jones::adjoint(&m));
            let rop_qp = jones::mul(&dp, &m);
            let v_pq = jones::mul(
                &jones::mul(&jones::adjoint(&IDENTITY), &dp),
                &jones::adjoint(&rop_pq),
            );
            let r: Jones = std::array::from_fn(|k| {
                // absv1_idiv_absv2(v, r): |v|/|r| (0 where r is 0); r *= it.
                let n = if data[k].re == 0. && data[k].im == 0. {
                    C64::ZERO
                } else {
                    C64::new((v_pq[k].norm2() / data[k].norm2()).sqrt(), 0.)
                };
                data[k] * n - v_pq[k]
            });
            let wr_pq: Jones = std::array::from_fn(|k| real_scale(r[k], w[k]));
            let wr_qp = jones::adjoint(&wr_pq);
            let k = coeff[chan];
            let sp = &mut self.params[p];
            elem(&rop_pq, &w, &gp, &wr_pq, k, &mut sp.jhr, &mut sp.jhj);
            let sq = &mut self.params[q];
            elem(&rop_qp, &w, &gq, &wr_qp, k, &mut sq.jhr, &mut sq.jhj);
        }
    }

    /// One iteration: accumulate, `compute_update`, `finalize_update`,
    /// `update_gain_flags` and `update_param_flags`. Returns (converged,
    /// flagged) over this interval's gains.
    fn iterate(
        &mut self,
        problem: &Problem,
        coeff: &[f64],
        local: &[usize],
        loop_idx: usize,
        stop2: f64,
    ) -> Result<(usize, usize), Error> {
        let na = problem.nant;
        self.accumulate(problem, coeff, local);
        for s in self.params.iter_mut() {
            conjugate_gradient(&s.jhj, &s.jhr, &mut s.update)?;
        }
        for s in self.params.iter_mut() {
            for h in 0..2 {
                s.update[h] /= 2.;
                s.params[h] += s.update[h];
            }
        }
        for (li, &chan) in self.channels.iter().enumerate() {
            for a in 0..na {
                let g = &mut self.gains[li * na + a];
                g.gain = if g.flag == 1 {
                    [ONE, ONE]
                } else {
                    param_to_gain(&self.params[a].params, coeff[chan])
                };
            }
        }
        let (mut converged, mut flagged) = (0, 0);
        for g in self.gains.iter_mut() {
            let (c, x) = flag_ladder(g, loop_idx, stop2);
            converged += usize::from(c);
            flagged += usize::from(x);
            g.km1_gain = g.gain;
        }
        for (a, s) in self.params.iter_mut().enumerate() {
            s.flag = (0..self.channels.len()).all(|li| self.gains[li * na + a].flag == 1);
            if s.flag {
                s.params = [0., 0.];
            }
        }
        Ok((converged, flagged))
    }
}

/// Solve the delay term as QuartiCal 0.2.7 does, with its FFT initial
/// estimate when `estimate_antenna` is set and its referencing when
/// `reference_antenna` is set. `freq` holds the channel frequencies (Hz).
pub fn solve(problem: &Problem, freq: &[f64], settings: &Settings) -> Result<Solution, Error> {
    solve_traced(problem, freq, settings, None)
}

/// `solve`, also returning the counts its global stop test sums per
/// iteration (`diag::Trace`, task W3b); recording changes no arithmetic.
pub fn solve_counted(
    problem: &Problem,
    freq: &[f64],
    settings: &Settings,
) -> (Result<Solution, Error>, Trace) {
    let mut trace = Trace::default();
    let result = solve_traced(problem, freq, settings, Some(&mut trace));
    (result, trace)
}

fn solve_traced(
    problem: &Problem,
    freq: &[f64],
    settings: &Settings,
    mut trace: Option<&mut Trace>,
) -> Result<Solution, Error> {
    check(problem, freq, settings)?;
    let na = problem.nant;
    let nchan = problem.nchan;
    let flags_cell = crate::solve::data_flags(problem);
    let mut ivs = intervals(problem, &flags_cell);
    let mid = mid_frequency(freq);
    let mut local = vec![0usize; nchan];
    for iv in &ivs {
        for (i, &c) in iv.channels.iter().enumerate() {
            local[c] = i;
        }
    }
    // init_term: parameters from the estimate (seconds), gains from them by
    // the unscaled formula, then the parameter and gain flags applied.
    if let Some(r) = settings.estimate_antenna {
        let est = initial_estimate(problem, freq, &flags_cell, r);
        for (i, iv) in ivs.iter_mut().enumerate() {
            for (a, s) in iv.params.iter_mut().enumerate() {
                s.params = est[i * na + a];
            }
        }
    }
    let coeff0: Vec<f64> = freq
        .iter()
        .map(|&nu| 2. * std::f64::consts::PI * (nu / 1.0 - mid))
        .collect();
    for iv in ivs.iter_mut() {
        for (li, &chan) in iv.channels.iter().enumerate() {
            for a in 0..na {
                let g = &mut iv.gains[li * na + a];
                g.gain = if g.flag != 0 {
                    [ONE, ONE]
                } else {
                    param_to_gain(&iv.params[a].params, coeff0[chan])
                };
                g.km1_gain = g.gain;
            }
        }
        for s in iv.params.iter_mut() {
            if s.flag {
                s.params = [0., 0.];
            }
            // The solver works on tau * nu_mid.
            for p in s.params.iter_mut() {
                *p *= mid;
            }
        }
    }
    let coeff: Vec<f64> = freq
        .iter()
        .map(|&nu| 2. * std::f64::consts::PI * (nu / mid - 1.))
        .collect();
    let ngains = problem.ntime_bins * nchan * na;
    let stop2 = settings.stop_criterion * settings.stop_criterion;
    let iterations = settings.max_iterations.max(1);
    let mut done = 0;
    let mut fraction = 0.;
    for loop_idx in 0..iterations {
        let counts: Vec<(usize, usize)> = match ivs
            .par_iter_mut()
            .map(|iv| iv.iterate(problem, &coeff, &local, loop_idx, stop2))
            .collect::<Result<_, _>>()
        {
            Ok(counts) => counts,
            Err(error) => {
                if let Some(t) = trace.as_deref_mut() {
                    t.error_iteration = Some(loop_idx);
                }
                return Err(error);
            }
        };
        let (c, x) = counts.iter().fold((0, 0), |(c, x), r| (c + r.0, x + r.1));
        if let Some(t) = trace.as_deref_mut() {
            t.counts.push((c, x));
        }
        let solvable = ngains - x;
        fraction = if solvable > 0 {
            c as f64 / solvable as f64
        } else {
            0.
        };
        done = loop_idx + 1;
        if fraction >= settings.stop_fraction {
            break;
        }
    }
    // finalize_gain_flags, then reference_params.
    for iv in ivs.iter_mut() {
        for g in iv.gains.iter_mut() {
            if g.trend > TREND_LIMIT {
                g.flag = 1;
                g.gain = [ONE, ONE];
            } else if g.flag == -1 {
                g.flag = 0;
            }
        }
        if let Some(r) = settings.reference_antenna {
            let rp = iv.params[r].params;
            for s in iv.params.iter_mut() {
                if !s.flag {
                    s.params = [s.params[0] - rp[0], s.params[1] - rp[1]];
                }
            }
            for (li, &chan) in iv.channels.iter().enumerate() {
                for a in 0..na {
                    iv.gains[li * na + a].gain = param_to_gain(&iv.params[a].params, coeff[chan]);
                }
            }
            for s in iv.params.iter_mut() {
                if s.flag {
                    s.params = [0., 0.];
                }
            }
            for g in iv.gains.iter_mut() {
                if g.flag != 0 {
                    g.gain = [ONE, ONE];
                }
            }
        }
    }
    let mut delays = Vec::with_capacity(ivs.len() * na);
    let mut flags = Vec::with_capacity(ivs.len() * na);
    for iv in &ivs {
        for s in &iv.params {
            delays.push([s.params[0] / mid, s.params[1] / mid]);
            flags.push(i8::from(s.flag));
        }
    }
    let mut gains = vec![[ONE, ONE]; ngains];
    let mut gain_flags = vec![1i8; ngains];
    for (i, iv) in ivs.iter().enumerate() {
        let t = i / problem.nfreq_bins;
        for (li, &chan) in iv.channels.iter().enumerate() {
            for a in 0..na {
                let g = &iv.gains[li * na + a];
                gains[(t * nchan + chan) * na + a] = g.gain;
                gain_flags[(t * nchan + chan) * na + a] = g.flag;
            }
        }
    }
    Ok(Solution {
        delays,
        flags,
        gains,
        gain_flags,
        iterations: done,
        converged_fraction: fraction,
    })
}

/// Rang's delay error per delay and hand (`research/c2b-delay.md` section
/// 1), in seconds: per interval, over the unflagged parallel-hand cells with
/// positive weight whose antennas' delays are unflagged, `chi2 = sum w |V -
/// g_p M g_q^*|^2` with `g = exp(2 pi i tau (nu - nu_mid))`, `nWt` their
/// count and `nPar` the unflagged delays; `k2 = chi2 / max(2 nWt - nPar,
/// 1)`; per delay `hess = sum w (2 pi (nu - nu_mid))^2 |V|^2`;
/// `err = sqrt(k2 / hess)` (0 where `hess` is 0 or the delay is flagged).
pub fn delay_errors(
    problem: &Problem,
    freq: &[f64],
    delays: &[[f64; 2]],
    flags: &[i8],
) -> Result<Vec<[f64; 2]>, Error> {
    let na = problem.nant;
    let nparam = problem.ntime_bins * problem.nfreq_bins * na;
    if delays.len() != nparam || flags.len() != nparam {
        return Err(Error::Shape("delays or flags length"));
    }
    check(
        problem,
        freq,
        &Settings {
            reference_antenna: None,
            estimate_antenna: None,
            ..Settings::new()
        },
    )?;
    let flags_cell = crate::solve::data_flags(problem);
    let ivs = intervals(problem, &flags_cell);
    let mid = mid_frequency(freq);
    let two_pi = 2. * std::f64::consts::PI;
    let mut err = vec![[0f64; 2]; nparam];
    err.par_chunks_mut(na.max(1))
        .zip(ivs.par_iter())
        .enumerate()
        .for_each(|(i, (err, iv))| {
            let d = &delays[i * na..(i + 1) * na];
            let f = &flags[i * na..(i + 1) * na];
            let mut hess = vec![[0f64; 2]; na];
            let (mut chi2, mut nwt) = (0f64, 0usize);
            for c in &iv.cells {
                let (p, q, cell) = (c.p as usize, c.q as usize, c.cell);
                if f[p] != 0 || f[q] != 0 {
                    continue;
                }
                let chan = cell % problem.nchan;
                let x = two_pi * (freq[chan] - mid);
                let data = jones::from_f32(&problem.data[8 * cell..8 * cell + 8]);
                let m = model_at(problem, cell, chan);
                for (h, k) in [(0usize, 0usize), (1, 3)] {
                    let w = f64::from(problem.weights[4 * cell + k]);
                    if w.is_nan() || w <= 0. {
                        continue;
                    }
                    let phase = x * (d[p][h] - d[q][h]);
                    let v = m[k] * C64::new(phase.cos(), phase.sin());
                    chi2 += w * (data[k] - v).norm2();
                    nwt += 1;
                    let dv = w * x * x * v.norm2();
                    hess[p][h] += dv;
                    hess[q][h] += dv;
                }
            }
            let npar = 2 * f.iter().filter(|&&x| x == 0).count();
            let ndof = (2 * nwt).saturating_sub(npar).max(1);
            let k2 = chi2 / ndof as f64;
            for a in 0..na {
                if f[a] != 0 {
                    continue;
                }
                for h in 0..2 {
                    if hess[a][h] > 0. {
                        err[a][h] = (k2 / hess[a][h]).sqrt();
                    }
                }
            }
        });
    Ok(err)
}

#[cfg(test)]
#[allow(clippy::needless_range_loop)]
mod tests {
    use super::*;

    struct Sim {
        data: Vec<f32>,
        weights: Vec<f32>,
        model: Vec<f32>,
        flag: Vec<u8>,
        flag_row: Vec<u8>,
        a1: Vec<u32>,
        a2: Vec<u32>,
        tb: Vec<u32>,
        fb: Vec<u32>,
        freq: Vec<f64>,
        nrow: usize,
        nchan: usize,
        nant: usize,
        ntime: usize,
        tau: Vec<[f64; 2]>,
    }

    fn lcg(state: &mut u64) -> f64 {
        *state = state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        ((*state >> 11) as f64) / ((1u64 << 53) as f64)
    }

    /// `V = K_p M K_q^H (+ noise)` with delays up to `scale` seconds.
    fn sim(nant: usize, ntime: usize, nchan: usize, noise: f64, scale: f64) -> Sim {
        let mut s = 20261106u64;
        let freq: Vec<f64> = (0..nchan)
            .map(|c| 856e6 + 856e6 / nchan as f64 * (c as f64 + 0.5))
            .collect();
        let mid = mid_frequency(&freq);
        let mut tau = Vec::new();
        for _ in 0..ntime * nant {
            tau.push([
                scale * (2. * lcg(&mut s) - 1.),
                scale * (2. * lcg(&mut s) - 1.),
            ]);
        }
        let (mut a1, mut a2, mut tb) = (vec![], vec![], vec![]);
        for t in 0..ntime {
            for p in 0..nant {
                for q in p + 1..nant {
                    a1.push(p as u32);
                    a2.push(q as u32);
                    tb.push(t as u32);
                }
            }
        }
        let nrow = a1.len();
        let (mut data, mut model) = (vec![0f32; nrow * nchan * 8], vec![0f32; nrow * nchan * 8]);
        for row in 0..nrow {
            let (p, q, t) = (a1[row] as usize, a2[row] as usize, tb[row] as usize);
            for ch in 0..nchan {
                let cell = row * nchan + ch;
                let m: Jones = [
                    C64::new(10. + lcg(&mut s), 0.),
                    C64::new(0.1 * (lcg(&mut s) - 0.5), 0.1 * (lcg(&mut s) - 0.5)),
                    C64::new(0.1 * (lcg(&mut s) - 0.5), 0.1 * (lcg(&mut s) - 0.5)),
                    C64::new(9. + lcg(&mut s), 0.),
                ];
                let x = 2. * std::f64::consts::PI * (freq[ch] - mid);
                let kp = [tau[t * nant + p][0] * x, tau[t * nant + p][1] * x];
                let kq = [tau[t * nant + q][0] * x, tau[t * nant + q][1] * x];
                let gp = [
                    C64::new(kp[0].cos(), kp[0].sin()),
                    C64::new(kp[1].cos(), kp[1].sin()),
                ];
                let gq = [
                    C64::new(kq[0].cos(), kq[0].sin()),
                    C64::new(kq[1].cos(), kq[1].sin()),
                ];
                let v = jones::mul(&jones::mul(&diag(&gp), &m), &jones::adjoint(&diag(&gq)));
                for k in 0..4 {
                    model[8 * cell + 2 * k] = m[k].re as f32;
                    model[8 * cell + 2 * k + 1] = m[k].im as f32;
                    data[8 * cell + 2 * k] = (v[k].re + noise * (lcg(&mut s) - 0.5)) as f32;
                    data[8 * cell + 2 * k + 1] = (v[k].im + noise * (lcg(&mut s) - 0.5)) as f32;
                }
            }
        }
        Sim {
            weights: vec![1.; nrow * nchan * 4],
            flag: vec![0; nrow * nchan * 4],
            flag_row: vec![0; nrow],
            fb: vec![0; nchan],
            freq,
            data,
            model,
            a1,
            a2,
            tb,
            nrow,
            nchan,
            nant,
            ntime,
            tau,
        }
    }

    fn problem(s: &Sim) -> Problem<'_> {
        Problem {
            nrow: s.nrow,
            nchan: s.nchan,
            ntime_bins: s.ntime,
            nfreq_bins: 1,
            nant: s.nant,
            data: &s.data,
            weights: &s.weights,
            model: Model::Stored(&s.model),
            flag: &s.flag,
            flag_row: &s.flag_row,
            antenna1: &s.a1,
            antenna2: &s.a2,
            time_bin: &s.tb,
            freq_bin: &s.fb,
        }
    }

    fn max_delay_error(s: &Sim, sol: &Solution) -> f64 {
        let mut worst: f64 = 0.;
        for t in 0..s.ntime {
            for a in 0..s.nant {
                for h in 0..2 {
                    let got = sol.delays[t * s.nant + a][h];
                    let want = s.tau[t * s.nant + a][h] - s.tau[t * s.nant][h];
                    worst = worst.max((got - want).abs());
                }
            }
        }
        worst
    }

    #[test]
    fn counted_solve_equals_solve() {
        // Task W3b: recording the stop test's counts changes nothing.
        let s = sim(6, 4, 16, 0.5, 5e-9);
        let settings = Settings::new();
        let a = solve(&problem(&s), &s.freq, &settings).unwrap();
        let (b, trace) = solve_counted(&problem(&s), &s.freq, &settings);
        let b = b.unwrap();
        assert_eq!(a.delays, b.delays);
        assert_eq!(a.flags, b.flags);
        assert_eq!(a.gains, b.gains);
        assert_eq!(a.iterations, b.iterations);
        assert_eq!(trace.counts.len(), a.iterations);
        assert_eq!(trace.error_iteration, None);
    }

    #[test]
    fn noise_free_delays_are_recovered() {
        let s = sim(5, 3, 64, 0., 15e-9);
        let settings = Settings {
            max_iterations: 200,
            stop_fraction: 1.0,
            stop_criterion: 1e-12,
            ..Settings::new()
        };
        let sol = solve(&problem(&s), &s.freq, &settings).unwrap();
        assert!(sol.flags.iter().all(|&f| f == 0));
        let err = max_delay_error(&s, &sol);
        assert!(err < 1e-15, "{err}");
        // Referenced to antenna 0.
        for t in 0..s.ntime {
            assert_eq!(sol.delays[t * s.nant], [0., 0.]);
        }
    }

    #[test]
    fn the_estimate_is_within_one_fft_bin() {
        let s = sim(4, 2, 32, 0., 8e-9);
        let p = problem(&s);
        let flags = crate::solve::data_flags(&p);
        let est = initial_estimate(&p, &s.freq, &flags, 0);
        let n = ESTIMATE_POINTS.div_ceil(32) * 32;
        let bin = 1. / (n as f64 * (s.freq[1] - s.freq[0]));
        for t in 0..2 {
            for a in 1..4 {
                for h in 0..2 {
                    let want = s.tau[t * 4 + a][h] - s.tau[t * 4][h];
                    assert!((est[t * 4 + a][h] - want).abs() <= bin, "{t} {a} {h}");
                }
            }
        }
    }

    #[test]
    fn threads_are_bit_identical() {
        let s = sim(6, 4, 16, 0.5, 5e-9);
        let mut results = Vec::new();
        for threads in [1, 2, 4] {
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()
                .unwrap();
            let sol = pool.install(|| solve(&problem(&s), &s.freq, &Settings::new()).unwrap());
            let bits: Vec<u64> = sol
                .delays
                .iter()
                .flat_map(|d| [d[0].to_bits(), d[1].to_bits()])
                .collect();
            results.push((bits, sol.iterations, sol.gain_flags.clone()));
        }
        for r in &results[1..] {
            assert_eq!(&results[0], r);
        }
    }

    #[test]
    fn antennas_without_data_are_flagged() {
        let mut s = sim(4, 2, 8, 0., 5e-9);
        for row in 0..s.nrow {
            if s.a1[row] == 3 || s.a2[row] == 3 {
                s.flag_row[row] = 1;
            }
        }
        let sol = solve(&problem(&s), &s.freq, &Settings::new()).unwrap();
        for t in 0..2 {
            assert_eq!(sol.flags[t * 4 + 3], 1);
            assert_eq!(sol.delays[t * 4 + 3], [0., 0.]);
            assert_eq!(sol.flags[t * 4 + 1], 0);
            for c in 0..8 {
                assert_eq!(sol.gain_flags[(t * 8 + c) * 4 + 3], 1);
                assert_eq!(sol.gains[(t * 8 + c) * 4 + 3], [ONE, ONE]);
            }
        }
    }

    #[test]
    fn errors_scale_with_noise() {
        let quiet = sim(5, 1, 32, 0.01, 5e-9);
        let loud = sim(5, 1, 32, 0.1, 5e-9);
        let mut out = Vec::new();
        for s in [&quiet, &loud] {
            let sol = solve(&problem(s), &s.freq, &Settings::new()).unwrap();
            let e = delay_errors(&problem(s), &s.freq, &sol.delays, &sol.flags).unwrap();
            out.push(e.iter().map(|x| x[0] + x[1]).sum::<f64>());
        }
        let ratio = out[1] / out[0];
        assert!(ratio > 7. && ratio < 13., "{ratio}");
    }
}
