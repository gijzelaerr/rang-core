//! The delay term K as QuartiCal 0.2.7's `delay_and_offset`: a delay and a
//! free phase per antenna and hand, with the FFT initial estimate of `delay`
//! (task C2c, `research/c2c-bandpass.md` part 1; the K model of the finish
//! plan, section 7 item 11).
//!
//! Portions are a Rust translation of
//! `quartical/gains/delay_and_offset/kernel.py`,
//! `quartical/gains/delay_and_offset/__init__.py`
//! (`DelayAndOffset.init_term`), `quartical/gains/general/flagging.py` and
//! `quartical/gains/general/inversion.py` (the generalised `invert`) from
//! QuartiCal 0.2.7, distributed under the MIT License:
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
//! Scope as `delay.rs` (whose private helpers are copied here, C1 section 4
//! rule 1, so that `delay.rs` stays as C2b measured it): one
//! direction-independent term, four correlations, parallel hands only, no
//! robust reweighting and no MAD flags.
//!
//! - Parameters per antenna `[phi_x, tau_x nu_mid, phi_y, tau_y nu_mid]`
//!   (QuartiCal's `phase_offset_XX, delay_XX, phase_offset_YY, delay_YY`),
//!   gains `exp(i (2 pi (nu / nu_mid - 1) p_1 + p_0))` per channel.
//! - `jhr = [u, c u]` and `jhj = [[t, c t], [c t, c^2 t]]` per hand; the
//!   update by conjugate gradients on the one 4x4 system (at most four steps,
//!   dot products over all four parameters), warm-started from the last
//!   halved update; every update halved; numbness 1e9.
//! - The initial estimate is `delay.rs`'s (`Delay.init_term` and
//!   `DelayAndOffset.init_term` share it), on the delays only.

use crate::cal::delay::{initial_estimate, mid_frequency};
use crate::cal::diag::{Error, Trace};
use crate::fused::Model;
use crate::jones::{self, C64, Jones};
use crate::solve::Problem;
use rayon::prelude::*;

/// Numbness of the kernel (`update_gain_flags(..., numbness=1e9)`).
const NUMBNESS: f64 = 1e9;
/// Trend above which `finalize_gain_flags` hard-flags a gain.
const TREND_LIMIT: f64 = 1e-6;
/// Conjugate-gradient stopping threshold on `r^T r` (generalised `invert`).
const CG_TOLERANCE: f64 = 1e-30;

pub use crate::cal::delay::Settings;

#[derive(Debug, Clone)]
pub struct Solution {
    /// `ntime_bins * nfreq_bins * nant` delays `[tau_x, tau_y]` in seconds.
    pub delays: Vec<[f64; 2]>,
    /// The phase offsets `[phi_x, phi_y]` (radians), per delay.
    pub offsets: Vec<[f64; 2]>,
    /// Parameter flags (1 flagged), per antenna of an interval.
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

/// What the solver keeps per antenna of an interval.
#[derive(Clone, Copy)]
struct ParamState {
    /// `[phi_x, tau_x nu_mid, phi_y, tau_y nu_mid]` while solving.
    params: [f64; 4],
    flag: bool,
    jhj: [f64; 16],
    jhr: [f64; 4],
    update: [f64; 4],
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

struct Interval {
    channels: Vec<usize>,
    params: Vec<ParamState>,
    gains: Vec<GainState>,
    cells: Vec<CellRef>,
}

/// The intervals in `(time bin, frequency bin)` order with `init_flags`.
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
                    params: [0.; 4],
                    flag: true,
                    jhj: [0.; 16],
                    jhr: [0.; 4],
                    update: [0.; 4],
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

/// `iabsdivsq` on one value.
fn absdivsq(v: C64) -> C64 {
    if v.re == 0. && v.im == 0. {
        C64::ZERO
    } else {
        C64::new(1. / (v.re * v.re + v.im * v.im), 0.)
    }
}

/// `compute_jhwj_jhwr_elem` of `delay_and_offset` (four correlations,
/// lop = I, so the X-Y coupling `jhwj_03` is zero).
fn elem(
    rop: &Jones,
    w: &[f64; 4],
    gain: &[C64; 2],
    res: &Jones,
    coeff: f64,
    jhr: &mut [f64; 4],
    jhj: &mut [f64; 16],
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
    jhr[0] += upd_00;
    jhr[1] += coeff * upd_00;
    jhr[2] += upd_11;
    jhr[3] += coeff * upd_11;
    let w_0 = normf[0] * C64::new(w[0], 0.);
    let w_3 = normf[3] * C64::new(w[3], 0.);
    let (jh_00, jh_33) = (ONE * rop[0], ONE * rop[3]);
    let tmp_0 = (jh_00 * w_0 * jh_00.conj()).re;
    let tmp_2 = (jh_33 * w_3 * jh_33.conj()).re;
    let coeffsq = coeff * coeff;
    // Row-major 4x4; the X-Y blocks stay zero (tmp_1 = 0 with lop = I).
    jhj[0] += tmp_0;
    jhj[1] += tmp_0 * coeff;
    jhj[4] = jhj[1];
    jhj[5] += tmp_0 * coeffsq;
    jhj[10] += tmp_2;
    jhj[11] += tmp_2 * coeff;
    jhj[14] = jhj[11];
    jhj[15] += tmp_2 * coeffsq;
}

/// The generalised `invert`: conjugate gradients on the real 4x4 system,
/// warm-started from `x`, at most four steps.
fn conjugate_gradient(a: &[f64; 16], b: &[f64; 4], x: &mut [f64; 4]) -> Result<(), Error> {
    let mat_vec = |v: &[f64; 4]| -> [f64; 4] {
        std::array::from_fn(|i| {
            let mut s = 0.;
            for j in 0..4 {
                s += a[4 * i + j] * v[j];
            }
            s
        })
    };
    let dot = |u: &[f64; 4], v: &[f64; 4]| {
        let mut s = 0.;
        for i in 0..4 {
            s += u[i] * v[i];
        }
        s
    };
    let ax = mat_vec(x);
    let mut r: [f64; 4] = std::array::from_fn(|i| b[i] - ax[i]);
    let mut p = r;
    let mut r_k = dot(&r, &r);
    if r_k == 0. {
        return Ok(());
    }
    for _ in 0..4 {
        let ap = mat_vec(&p);
        let denom = dot(&p, &ap);
        if denom == 0. {
            return Err(Error::ZeroDivision);
        }
        let alpha = r_k / denom;
        for i in 0..4 {
            x[i] += alpha * p[i];
            r[i] -= alpha * ap[i];
        }
        let r_next = dot(&r, &r);
        if r_next < CG_TOLERANCE {
            break;
        }
        let beta = r_next / r_k;
        for i in 0..4 {
            p[i] = p[i] * beta + r[i];
        }
        r_k = r_next;
    }
    Ok(())
}

/// `exp(1j * (coeff * p[1] + p[0]))` and `exp(1j * (coeff * p[3] + p[2]))`.
fn param_to_gain(p: &[f64; 4], coeff: f64) -> [C64; 2] {
    let a = coeff * p[1] + p[0];
    let b = coeff * p[3] + p[2];
    [C64::new(a.cos(), a.sin()), C64::new(b.cos(), b.sin())]
}

/// `update_gain_flags` for one gain.
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
    fn accumulate(&mut self, problem: &Problem, coeff: &[f64], local: &[usize]) {
        let na = problem.nant;
        for s in self.params.iter_mut() {
            s.jhj = [0.; 16];
            s.jhr = [0.; 4];
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
            for k in 0..4 {
                s.update[k] /= 2.;
                s.params[k] += s.update[k];
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
                s.params = [0.; 4];
            }
        }
        Ok((converged, flagged))
    }
}

/// Rang's offset start (post hoc, `research/c2c-bandpass.md` section 6; not
/// QuartiCal's): per interval, frequency bin, antenna and hand, the phase of
/// the refant baselines' averaged `V conj(M)` (averaged as `Delay.init_term`
/// averages the data) derotated by the estimated delay about `nu_mid`,
/// `arg sum_c d_c exp(-2 pi i tau (nu_c - nu_mid))`, with the estimate's
/// sign convention (negated
/// where the antenna is the second of a row to the refant). `delays` is
/// `initial_estimate`'s output (seconds).
pub fn offset_estimate(
    problem: &Problem,
    freq: &[f64],
    flags_cell: &[bool],
    refant: usize,
    delays: &[[f64; 2]],
) -> Vec<[f64; 2]> {
    let (na, nchan, nfb) = (problem.nant, problem.nchan, problem.nfreq_bins);
    let mid = mid_frequency(freq);
    let two_pi = 2. * std::f64::consts::PI;
    let mut out = vec![[0f64; 2]; problem.ntime_bins * nfb * na];
    let mut channels = vec![Vec::new(); nfb];
    for (chan, &f) in problem.freq_bin.iter().enumerate() {
        channels[f as usize].push(chan);
    }
    let mut start = 0;
    for t in 0..problem.ntime_bins {
        let end = start
            + problem.time_bin[start..]
                .iter()
                .take_while(|&&b| b as usize == t)
                .count();
        let mut sum = vec![[C64::ZERO; 4]; na * nchan];
        let mut count = vec![0u64; na * nchan];
        // +1 where the antenna is first in a row to the refant, -1 second.
        let mut sign = vec![0f64; na];
        for row in start..end {
            let (p, q) = (
                problem.antenna1[row] as usize,
                problem.antenna2[row] as usize,
            );
            if p == q || (p != refant && q != refant) {
                continue;
            }
            let ant = if p == refant { q } else { p };
            sign[ant] = if p == refant { -1. } else { 1. };
            for chan in 0..nchan {
                let cell = row * nchan + chan;
                if flags_cell[cell] {
                    continue;
                }
                // Post hoc (section 6, third change): the datum times the
                // conjugate model, so that a model phase (a pre-applied G
                // corrupts the model) is not taken for an offset.
                let d = jones::from_f32(&problem.data[8 * cell..8 * cell + 8]);
                let m = model_at(problem, cell, chan);
                let s = &mut sum[ant * nchan + chan];
                for k in 0..4 {
                    s[k] = s[k] + d[k] * m[k].conj();
                }
                count[ant * nchan + chan] += 1;
            }
        }
        start = end;
        for (fb, chans) in channels.iter().enumerate() {
            let base = (t * nfb + fb) * na;
            for a in 0..na {
                if sign[a] == 0. {
                    continue;
                }
                for (h, corr) in [(0usize, 0usize), (1, 3)] {
                    let raw = sign[a] * delays[base + a][h];
                    let mut acc = C64::ZERO;
                    for &c in chans {
                        let n = count[a * nchan + c];
                        if n == 0 {
                            continue;
                        }
                        let v = sum[a * nchan + c][corr];
                        let v = C64::new(v.re / n as f64, v.im / n as f64);
                        let x = -two_pi * raw * (freq[c] - mid);
                        acc = acc + v * C64::new(x.cos(), x.sin());
                    }
                    if acc.re != 0. || acc.im != 0. {
                        out[base + a][h] = sign[a] * acc.im.atan2(acc.re);
                    }
                }
            }
        }
    }
    out
}

/// Solve `delay_and_offset` as QuartiCal 0.2.7 does, with the FFT initial
/// estimate when `estimate_antenna` is set and `reference_params` when
/// `reference_antenna` is set. `freq` holds the channel frequencies (Hz).
pub fn solve(problem: &Problem, freq: &[f64], settings: &Settings) -> Result<Solution, Error> {
    solve_with(problem, freq, settings, false)
}

/// `solve`, optionally with rang's offset start (`offset_estimate`): the
/// offsets start at the FFT peak's derotated phase instead of 0
/// (QuartiCal's start; `false` is `solve`). Post hoc, see
/// `offset_estimate`.
pub fn solve_with(
    problem: &Problem,
    freq: &[f64],
    settings: &Settings,
    start_offsets: bool,
) -> Result<Solution, Error> {
    solve_traced(problem, freq, settings, start_offsets, None)
}

/// `solve_with`, also returning the counts its global stop test sums per
/// iteration (`diag::Trace`, task W3b); recording changes no arithmetic.
pub fn solve_counted(
    problem: &Problem,
    freq: &[f64],
    settings: &Settings,
    start_offsets: bool,
) -> (Result<Solution, Error>, Trace) {
    let mut trace = Trace::default();
    let result = solve_traced(problem, freq, settings, start_offsets, Some(&mut trace));
    (result, trace)
}

fn solve_traced(
    problem: &Problem,
    freq: &[f64],
    settings: &Settings,
    start_offsets: bool,
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
    if let Some(r) = settings.estimate_antenna {
        let est = initial_estimate(problem, freq, &flags_cell, r);
        let off = if start_offsets {
            offset_estimate(problem, freq, &flags_cell, r, &est)
        } else {
            vec![[0f64; 2]; est.len()]
        };
        for (i, iv) in ivs.iter_mut().enumerate() {
            for (a, s) in iv.params.iter_mut().enumerate() {
                let (e, o) = (est[i * na + a], off[i * na + a]);
                s.params = [o[0], e[0], o[1], e[1]];
            }
        }
    }
    // init_term: gains from the parameters by the unscaled formula
    // (`coeff = 2 pi (nu - mid)`), then the flags applied.
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
                s.params = [0.; 4];
            }
            // active_params[..., 1::2] *= mid_freq
            s.params[1] *= mid;
            s.params[3] *= mid;
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
                    for (p, r) in s.params.iter_mut().zip(&rp) {
                        *p -= r;
                    }
                }
            }
            for (li, &chan) in iv.channels.iter().enumerate() {
                for a in 0..na {
                    iv.gains[li * na + a].gain = param_to_gain(&iv.params[a].params, coeff[chan]);
                }
            }
            for s in iv.params.iter_mut() {
                if s.flag {
                    s.params = [0.; 4];
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
    let mut offsets = Vec::with_capacity(ivs.len() * na);
    let mut flags = Vec::with_capacity(ivs.len() * na);
    for iv in &ivs {
        for s in &iv.params {
            delays.push([s.params[1] / mid, s.params[3] / mid]);
            offsets.push([s.params[0], s.params[2]]);
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
        offsets,
        flags,
        gains,
        gain_flags,
        iterations: done,
        converged_fraction: fraction,
    })
}

/// Rang's delay error with the offset (`research/c2c-bandpass.md` section
/// 1, with section 6's post-hoc residual), in seconds: per interval `chi2`
/// of the phase-only residual (each datum scaled to the amplitude of the
/// model `g_p M g_q^*`, `g = exp(i (2 pi tau (nu - nu_mid) + phi))`) over
/// the unflagged parallel-hand cells with positive weight whose antennas are
/// unflagged, `k2 = chi2 / max(nWt - nPar, 1)` (one tangential component
/// per cell) with `nPar` two per unflagged antenna and hand; per antenna and hand
/// `S_k = sum w x^k |V|^2` (`x = 2 pi (nu - nu_mid)`) and `err = sqrt(k2 S0
/// / (S0 S2 - S1^2))`, the offset marginalised (0 where the determinant is
/// not positive or the antenna is flagged).
pub fn delay_errors(
    problem: &Problem,
    freq: &[f64],
    delays: &[[f64; 2]],
    offsets: &[[f64; 2]],
    flags: &[i8],
) -> Result<Vec<[f64; 2]>, Error> {
    let na = problem.nant;
    let nparam = problem.ntime_bins * problem.nfreq_bins * na;
    if delays.len() != nparam || offsets.len() != nparam || flags.len() != nparam {
        return Err(Error::Shape("delays, offsets or flags length"));
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
            let o = &offsets[i * na..(i + 1) * na];
            let f = &flags[i * na..(i + 1) * na];
            let mut s = vec![[[0f64; 3]; 2]; na];
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
                    let phase = x * (d[p][h] - d[q][h]) + (o[p][h] - o[q][h]);
                    let v = m[k] * C64::new(phase.cos(), phase.sin());
                    // Post hoc (section 6): the residual of the kernel's
                    // phase-only fit, the datum scaled to the model's
                    // amplitude, so that an amplitude the term does not
                    // carry (an unapplied G) does not enter chi2.
                    let a = data[k].norm2();
                    let scaled = if a > 0. {
                        real_scale(data[k], (v.norm2() / a).sqrt())
                    } else {
                        data[k]
                    };
                    chi2 += w * (scaled - v).norm2();
                    nwt += 1;
                    let a2 = w * v.norm2();
                    for ant in [p, q] {
                        s[ant][h][0] += a2;
                        s[ant][h][1] += a2 * x;
                        s[ant][h][2] += a2 * x * x;
                    }
                }
            }
            // One real (tangential) residual component per cell and hand.
            let npar = 4 * f.iter().filter(|&&x| x == 0).count();
            let ndof = nwt.saturating_sub(npar).max(1);
            let k2 = chi2 / ndof as f64;
            for a in 0..na {
                if f[a] != 0 {
                    continue;
                }
                for h in 0..2 {
                    let [s0, s1, s2] = s[a][h];
                    let det = s0 * s2 - s1 * s1;
                    if det > 0. && s0 > 0. {
                        err[a][h] = (k2 * s0 / det).sqrt();
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
        phi: Vec<[f64; 2]>,
    }

    fn lcg(state: &mut u64) -> f64 {
        *state = state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        ((*state >> 11) as f64) / ((1u64 << 53) as f64)
    }

    /// `V = K_p M K_q^H (+ noise)`, `K = exp(i (2 pi tau (nu - mid) + phi))`.
    fn sim(nant: usize, ntime: usize, nchan: usize, noise: f64, scale: f64) -> Sim {
        let mut s = 20261106u64;
        let freq: Vec<f64> = (0..nchan)
            .map(|c| 856e6 + 856e6 / nchan as f64 * (c as f64 + 0.5))
            .collect();
        let mid = mid_frequency(&freq);
        let mut tau = Vec::new();
        let mut phi = Vec::new();
        for _ in 0..ntime * nant {
            tau.push([
                scale * (2. * lcg(&mut s) - 1.),
                scale * (2. * lcg(&mut s) - 1.),
            ]);
            phi.push([2. * lcg(&mut s) - 1., 2. * lcg(&mut s) - 1.]);
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
                let g = |a: usize| -> [C64; 2] {
                    std::array::from_fn(|h| {
                        let v = tau[t * nant + a][h] * x + phi[t * nant + a][h];
                        C64::new(v.cos(), v.sin())
                    })
                };
                let v = jones::mul(&jones::mul(&diag(&g(p)), &m), &jones::adjoint(&diag(&g(q))));
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
            phi,
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

    fn wrap(x: f64) -> f64 {
        let t = std::f64::consts::TAU;
        x - t * (x / t).round()
    }

    #[test]
    fn counted_solve_equals_solve() {
        // Task W3b: recording the stop test's counts changes nothing.
        let s = sim(5, 3, 64, 0.3, 15e-9);
        let settings = Settings::new();
        for start in [false, true] {
            let a = solve_with(&problem(&s), &s.freq, &settings, start).unwrap();
            let (b, trace) = solve_counted(&problem(&s), &s.freq, &settings, start);
            let b = b.unwrap();
            assert_eq!(a.delays, b.delays);
            assert_eq!(a.offsets, b.offsets);
            assert_eq!(a.flags, b.flags);
            assert_eq!(a.gains, b.gains);
            assert_eq!(a.iterations, b.iterations);
            assert_eq!(trace.counts.len(), a.iterations);
        }
    }

    #[test]
    fn noise_free_delays_and_offsets_are_recovered() {
        let s = sim(5, 3, 64, 0., 15e-9);
        let settings = Settings {
            max_iterations: 200,
            stop_fraction: 1.0,
            stop_criterion: 1e-12,
            ..Settings::new()
        };
        let sol = solve(&problem(&s), &s.freq, &settings).unwrap();
        assert!(sol.flags.iter().all(|&f| f == 0));
        for t in 0..s.ntime {
            assert_eq!(sol.delays[t * s.nant], [0., 0.]);
            assert_eq!(sol.offsets[t * s.nant], [0., 0.]);
            for a in 0..s.nant {
                for h in 0..2 {
                    let i = t * s.nant + a;
                    let want = s.tau[i][h] - s.tau[t * s.nant][h];
                    let got = sol.delays[i][h];
                    assert!((got - want).abs() < 1e-15, "{t} {a} {h} {got} {want}");
                    let want = s.phi[i][h] - s.phi[t * s.nant][h];
                    let got = sol.offsets[i][h];
                    // float32 data: offsets to about 1e-9 rad.
                    assert!(wrap(got - want).abs() < 1e-7, "{t} {a} {h} {got} {want}");
                }
            }
        }
    }

    #[test]
    fn the_offset_start_is_near_the_truth() {
        let s = sim(5, 2, 64, 0., 15e-9);
        let p = problem(&s);
        let flags = crate::solve::data_flags(&p);
        let est = initial_estimate(&p, &s.freq, &flags, 0);
        let off = offset_estimate(&p, &s.freq, &flags, 0, &est);
        for t in 0..s.ntime {
            for a in 1..s.nant {
                for h in 0..2 {
                    let i = t * s.nant + a;
                    let want = s.phi[i][h] - s.phi[t * s.nant][h];
                    assert!(wrap(off[i][h] - want).abs() < 0.2, "{t} {a} {h}");
                }
            }
        }
        // A phase in the model (a pre-applied G corrupts it) and the same in
        // the data is not an offset.
        let mut t = sim(5, 2, 64, 0., 15e-9);
        for row in 0..t.nrow {
            let ph = 0.7 * (row % 5) as f64 + 1.1;
            let (c, sn) = (ph.cos() as f32, ph.sin() as f32);
            for v in [&mut t.data, &mut t.model] {
                for k in 0..t.nchan * 4 {
                    let i = 8 * (row * t.nchan * 4 / 4) + 2 * k;
                    let (re, im) = (v[i], v[i + 1]);
                    v[i] = re * c - im * sn;
                    v[i + 1] = re * sn + im * c;
                }
            }
        }
        let pt = problem(&t);
        let flags = crate::solve::data_flags(&pt);
        let est = initial_estimate(&pt, &t.freq, &flags, 0);
        let off2 = offset_estimate(&pt, &t.freq, &flags, 0, &est);
        for (x, y) in off.iter().zip(&off2) {
            assert!(wrap(x[0] - y[0]).abs() < 1e-4 && wrap(x[1] - y[1]).abs() < 1e-4);
        }
        // With the start, the solution is the same minimum.
        let tight = Settings {
            max_iterations: 200,
            stop_fraction: 1.0,
            stop_criterion: 1e-12,
            ..Settings::new()
        };
        let a = solve(&p, &s.freq, &tight).unwrap();
        let b = solve_with(&p, &s.freq, &tight, true).unwrap();
        for (x, y) in a.delays.iter().zip(&b.delays) {
            assert!((x[0] - y[0]).abs() < 1e-15 && (x[1] - y[1]).abs() < 1e-15);
        }
    }

    #[test]
    fn the_four_by_four_solve_is_exact_on_a_block_system() {
        // A symmetric positive definite block-diagonal system: four CG steps
        // reach the solution.
        let a = [
            4., 1., 0., 0., 1., 3., 0., 0., 0., 0., 2., 0.5, 0., 0., 0.5, 5.,
        ];
        let want = [0.3, -1.2, 2.0, 0.7];
        let b: [f64; 4] = std::array::from_fn(|i| (0..4).map(|j| a[4 * i + j] * want[j]).sum());
        let mut x = [0.; 4];
        conjugate_gradient(&a, &b, &mut x).unwrap();
        for i in 0..4 {
            assert!((x[i] - want[i]).abs() < 1e-12, "{i}");
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
                .chain(&sol.offsets)
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
            assert_eq!(sol.offsets[t * 4 + 3], [0., 0.]);
            assert_eq!(sol.flags[t * 4 + 1], 0);
        }
    }

    #[test]
    fn errors_scale_with_noise() {
        let quiet = sim(5, 1, 32, 0.01, 5e-9);
        let loud = sim(5, 1, 32, 0.1, 5e-9);
        let mut out = Vec::new();
        for s in [&quiet, &loud] {
            let sol = solve(&problem(s), &s.freq, &Settings::new()).unwrap();
            let e =
                delay_errors(&problem(s), &s.freq, &sol.delays, &sol.offsets, &sol.flags).unwrap();
            out.push(e.iter().map(|x| x[0] + x[1]).sum::<f64>());
        }
        let ratio = out[1] / out[0];
        assert!(ratio > 7. && ratio < 13., "{ratio}");
    }
}
