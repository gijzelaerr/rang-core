// SPDX-License-Identifier: GPL-3.0-or-later AND MIT
// Follows CASA's C++ source in part (Copyright (C) Associated
// Universities, Inc. Washington DC, USA; (L)GPL version 2 or later):
// notices in THIRD-PARTY-NOTICES.txt.
//! Diagonal gain solvers `diag_complex` (calmode `ap`) and `phase` (calmode
//! `p`), ported from QuartiCal 0.2.7 (task C2a, `research/c2a-gain.md`; C1
//! step 3, `research/c1-calibration-chain.md`).
//!
//! Portions are a Rust translation of `quartical/gains/complex/diag_kernel.py`,
//! `quartical/gains/phase/kernel.py`, `quartical/gains/general/flagging.py`,
//! `quartical/gains/general/inversion.py` and `quartical/gains/general/factories.py`
//! from QuartiCal 0.2.7, distributed under the MIT License:
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
//! Scope: one direction-independent term, four correlations (linear feeds,
//! `XX, XY, YX, YY`), one chunk, no robust reweighting and no MAD flags, as
//! `solve.rs` (which this module leaves untouched; its small helpers are
//! copied here, C1 section 4 rule 1). Both kernels use the parallel hands
//! only (QuartiCal zeroes the cross-hand residuals and weights). The gains
//! are `diag(g_x, g_y)` per (time bin, frequency bin, antenna).
//!
//! - `diag_complex`: Gauss-Newton with QuartiCal's non-generalised 2x2
//!   inverse (an update of zero where `det(J^H J).re < 1e-6`) and the halved
//!   update on even iterations; numbness 1e-6.
//! - `phase`: `g = exp(i phi)`; the data are scaled to the model's amplitude
//!   (`absv1_idiv_absv2`), the residual normalised by `|J|^2`
//!   (`iabsdivsq`), conjugate gradients on the real 2x2 normal equations
//!   warm-started from the previous update, no halving; numbness 1e9.
//!
//! Like `solve.rs`, every solution interval runs `EPOCH` iterations on its
//! own on rayon's pool and the global stop test (the converged fraction
//! over all gains) is applied serially afterwards, so the result is the
//! serial loop's at every thread count. At the end QuartiCal's referencing
//! is applied when `Settings::reference_antenna` is set (`reference_gains`,
//! `reference_params`); CASA's rule is `reference.rs`.

use crate::fused::Model;
use crate::jones::{self, C64, Jones};
use crate::solve::Problem;
use rayon::prelude::*;

/// Numbness of the divergence ladder in `update_gain_flags` (`diag_complex`).
const NUMBNESS_COMPLEX: f64 = 1e-6;
/// Numbness of the `phase` kernel (`update_gain_flags(..., numbness=1e9)`).
const NUMBNESS_PHASE: f64 = 1e9;
/// Trend above which `finalize_gain_flags` hard-flags a gain.
const TREND_LIMIT: f64 = 1e-6;
/// `invert` (non-generalised): no update below this determinant.
const DET_LIMIT: f64 = 1e-6;
/// Conjugate-gradient stopping threshold on `r^T r` (generalised `invert`).
const CG_TOLERANCE: f64 = 1e-30;
/// Iterations each interval runs between two global stop tests.
const EPOCH: usize = 8;

/// The two kernels.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    /// QuartiCal `diag_complex`: amplitude and phase per hand (CASA `ap`).
    DiagComplex,
    /// QuartiCal `phase`: phase per hand (CASA `p`).
    Phase,
}

#[derive(Clone, Copy, Debug)]
pub struct Settings {
    pub kind: Kind,
    pub max_iterations: usize,
    pub stop_criterion: f64,
    pub stop_fraction: f64,
    /// QuartiCal's `solver.reference_antenna`; `None` leaves the gains
    /// unreferenced (for CASA's rule, `reference::apply_refant`).
    pub reference_antenna: Option<usize>,
}

impl Settings {
    /// Rang's frozen QuartiCal settings (as `solve::Settings::default`).
    pub fn new(kind: Kind) -> Self {
        Self {
            kind,
            max_iterations: 50,
            stop_criterion: 1e-7,
            stop_fraction: 0.99,
            reference_antenna: Some(0),
        }
    }
}

#[derive(Debug, Clone)]
pub struct Solution {
    /// `ntime_bins * nfreq_bins * nant` gains `[g_x, g_y]`.
    pub gains: Vec<[C64; 2]>,
    /// 1 hard-flagged, 0 unflagged, per gain.
    pub flags: Vec<i8>,
    pub iterations: usize,
    pub converged_fraction: f64,
}

#[derive(Debug, PartialEq)]
pub enum Error {
    Shape(&'static str),
    Order(&'static str),
    ZeroDivision,
    Settings(&'static str),
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Error::Shape(s) | Error::Order(s) | Error::Settings(s) => f.write_str(s),
            Error::ZeroDivision => f.write_str("division by zero in the solver"),
        }
    }
}

const ONE: C64 = C64 { re: 1., im: 0. };
const IDENTITY: Jones = [ONE, C64::ZERO, C64::ZERO, ONE];

/// CPython's (and Numba's) complex division, `_Py_c_quot` (copied from
/// `solve.rs`).
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

/// `a * w` for a real `w`, as Numba multiplies a complex by a float.
fn real_scale(a: C64, w: f64) -> C64 {
    C64::new(a.re * w, a.im * w)
}

fn diag(g: &[C64; 2]) -> Jones {
    [g[0], C64::ZERO, C64::ZERO, g[1]]
}

fn check(problem: &Problem, settings: &Settings) -> Result<(), Error> {
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
    if let Some(r) = settings.reference_antenna
        && r >= problem.nant
    {
        return Err(Error::Settings("reference antenna out of range"));
    }
    if !(settings.stop_criterion.is_finite() && settings.stop_fraction.is_finite()) {
        return Err(Error::Settings(
            "stop criterion and fraction must be finite",
        ));
    }
    Ok(())
}

fn model_at(problem: &Problem, cell: usize, chan: usize) -> Jones {
    match problem.model {
        Model::Stored(m) => jones::from_f32(&m[8 * cell..8 * cell + 8]),
        Model::Scalar(s) => jones::scalar(s[chan]),
    }
}

/// What the solver keeps per gain.
#[derive(Clone, Copy)]
struct GainState {
    gain: [C64; 2],
    km1_gain: [C64; 2],
    km1_abs2_diff: f64,
    trend: f64,
    /// `phase`: the parameters, and their flag (`update_param_flags`).
    params: [f64; 2],
    param_flag: bool,
    /// `diag_complex`: `J^H J` diagonal and `J^H r` (complex).
    jhj_c: [C64; 2],
    jhr_c: [C64; 2],
    /// `phase`: real `J^H J` (2x2, row-major), `J^H r` and the warm-started
    /// update.
    jhj_r: [f64; 4],
    jhr_r: [f64; 2],
    update_r: [f64; 2],
    flag: i8,
}

const FRESH: GainState = GainState {
    gain: [ONE, ONE],
    km1_gain: [ONE, ONE],
    km1_abs2_diff: 0.,
    trend: 0.,
    params: [0., 0.],
    param_flag: false,
    jhj_c: [C64::ZERO; 2],
    jhr_c: [C64::ZERO; 2],
    jhj_r: [0.; 4],
    jhr_r: [0.; 2],
    update_r: [0.; 2],
    flag: 1,
};

/// One unflagged cell of a solution interval and its two antennas.
struct CellRef {
    cell: usize,
    p: u32,
    q: u32,
}

/// The unflagged cells of every interval, in the serial sweep's order, and
/// `init_flags`: a gain stays flagged unless an unflagged cell involves it.
fn interval_cells(
    problem: &Problem,
    flags_cell: &[bool],
    states: &mut [GainState],
    width: usize,
) -> Vec<Vec<CellRef>> {
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
    states
        .par_chunks_mut(width)
        .enumerate()
        .map(|(interval, chunk)| {
            let t = interval / problem.nfreq_bins;
            let mut cells = Vec::new();
            for row in rows[t].clone() {
                let (p, q) = (problem.antenna1[row], problem.antenna2[row]);
                for &chan in &channels[interval % problem.nfreq_bins] {
                    let cell = row * problem.nchan + chan;
                    if !flags_cell[cell] {
                        cells.push(CellRef { cell, p, q });
                        chunk[p as usize].flag = 0;
                        chunk[q as usize].flag = 0;
                    }
                }
            }
            cells
        })
        .collect()
}

/// `iabsdivsq` on one value: `0` for `0`, else `1/|v|^2`.
fn absdivsq(v: C64) -> C64 {
    if v.re == 0. && v.im == 0. {
        C64::ZERO
    } else {
        C64::new(1. / (v.re * v.re + v.im * v.im), 0.)
    }
}

/// `compute_jhwj_jhwr_elem` of `diag_complex` (four correlations, lop = I).
fn elem_complex(rop: &Jones, w: &[f64; 4], res: &Jones, jhr: &mut [C64; 2], jhj: &mut [C64; 2]) {
    // res[1] = res[2] = 0; res = I res; res = res rop.
    let res = [res[0], C64::ZERO, C64::ZERO, res[3]];
    let product = jones::mul(&jones::mul(&IDENTITY, &res), rop);
    jhr[0] = jhr[0] + product[0];
    jhr[1] = jhr[1] + product[3];
    // Rows 0 and 3 of a_kron_bt(I, rop) are (rop0, rop2, 0, 0) and
    // (0, 0, rop1, rop3); the cross-hand weights are zero, so of jhwj_00 and
    // jhwj_33 only the parallel-hand products remain and jhwj_03 is zero.
    let (r0, r3) = (rop[0], rop[3]);
    jhj[0] = jhj[0] + real_scale(r0, w[0]) * r0.conj();
    jhj[1] = jhj[1] + real_scale(r3, w[3]) * r3.conj();
}

/// `compute_jhwj_jhwr_elem` of `phase` (four correlations, lop = I).
fn elem_phase(
    rop: &Jones,
    w: &[f64; 4],
    gain: &[C64; 2],
    res: &Jones,
    jhr: &mut [f64; 2],
    jhj: &mut [f64; 4],
) {
    let res = [res[0], C64::ZERO, C64::ZERO, res[3]];
    // normf = I rop, then 1/|.|^2 per element.
    let lr = jones::mul(&IDENTITY, rop);
    let normf: Jones = std::array::from_fn(|k| absdivsq(lr[k]));
    let res: Jones = std::array::from_fn(|k| res[k] * normf[k]);
    let res = jones::mul(&IDENTITY, &jones::mul(&res, rop));
    let (r_0, r_3) = (res[0], res[3]);
    let (gc_0, gc_3) = (gain[0].conj(), gain[1].conj());
    let minus_i = C64::new(-0., -1.);
    jhr[0] += (minus_i * gc_0 * r_0).re;
    jhr[1] += (minus_i * gc_3 * r_3).re;
    let w_0 = normf[0] * C64::new(w[0], 0.);
    let w_3 = normf[3] * C64::new(w[3], 0.);
    // lop = I: jh_00 = rop0, jh_33 = rop3, jh_03 = jh_30 = 0, so jhwj_03 = 0.
    let (jh_00, jh_33) = (ONE * rop[0], ONE * rop[3]);
    let jhwj_00 = jh_00 * w_0 * jh_00.conj();
    let jhwj_33 = jh_33 * w_3 * jh_33.conj();
    jhj[0] += jhwj_00.re;
    jhj[3] += jhwj_33.re;
}

/// `compute_jhj_jhr` for one interval's gains (indexed by antenna).
fn accumulate(problem: &Problem, kind: Kind, cells: &[CellRef], states: &mut [GainState]) {
    for s in states.iter_mut() {
        s.jhj_c = [C64::ZERO; 2];
        s.jhr_c = [C64::ZERO; 2];
        s.jhj_r = [0.; 4];
        s.jhr_r = [0.; 2];
    }
    for c in cells {
        let (p, q, cell) = (c.p as usize, c.q as usize, c.cell);
        let w: [f64; 4] = std::array::from_fn(|k| f64::from(problem.weights[4 * cell + k]));
        let data = jones::from_f32(&problem.data[8 * cell..8 * cell + 8]);
        let m = model_at(problem, cell, cell % problem.nchan);
        let (gp, gq) = (states[p].gain, states[q].gain);
        let (dp, dq) = (diag(&gp), diag(&gq));
        let rop_pq = jones::mul(&dq, &jones::adjoint(&m));
        let rop_qp = jones::mul(&dp, &m);
        let v_pq = jones::mul(
            &jones::mul(&jones::adjoint(&IDENTITY), &dp),
            &jones::adjoint(&rop_pq),
        );
        let r: Jones = match kind {
            Kind::DiagComplex => std::array::from_fn(|k| data[k] - v_pq[k]),
            Kind::Phase => std::array::from_fn(|k| {
                // absv1_idiv_absv2(v, r): |v|/|r| (0 where r is 0); r *= it.
                let n = if data[k].re == 0. && data[k].im == 0. {
                    C64::ZERO
                } else {
                    C64::new((v_pq[k].norm2() / data[k].norm2()).sqrt(), 0.)
                };
                data[k] * n - v_pq[k]
            }),
        };
        let wr_pq: Jones = std::array::from_fn(|k| real_scale(r[k], w[k]));
        let wr_qp = jones::adjoint(&wr_pq);
        match kind {
            Kind::DiagComplex => {
                let sp = &mut states[p];
                elem_complex(&rop_pq, &w, &wr_pq, &mut sp.jhr_c, &mut sp.jhj_c);
                let sq = &mut states[q];
                elem_complex(&rop_qp, &w, &wr_qp, &mut sq.jhr_c, &mut sq.jhj_c);
            }
            Kind::Phase => {
                let sp = &mut states[p];
                elem_phase(&rop_pq, &w, &gp, &wr_pq, &mut sp.jhr_r, &mut sp.jhj_r);
                let sq = &mut states[q];
                elem_phase(&rop_qp, &w, &gq, &wr_qp, &mut sq.jhr_r, &mut sq.jhj_r);
            }
        }
    }
}

/// Non-generalised `invert` (four correlations) then `v1_imul_v2(b, x, x)`,
/// on the diagonal `jhj` and `jhr` (their off-diagonal entries are zero).
fn update_complex(jhj: &[C64; 2], jhr: &[C64; 2]) -> Result<[C64; 2], Error> {
    let det = jhj[0] * jhj[1] - C64::ZERO * C64::ZERO;
    if det.re < DET_LIMIT {
        return Ok([C64::ZERO; 2]);
    }
    let x0 = divide(jhj[1], det)?;
    let x3 = divide(jhj[0], det)?;
    Ok([jhr[0] * x0, jhr[1] * x3])
}

/// Generalised `invert`: conjugate gradients on the real 2x2 system,
/// warm-started from `x`, at most two steps.
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

/// `compute_update`, `finalize_update`, `update_gain_flags` and (for
/// `phase`) `update_param_flags` for one gain. Returns (converged, flagged).
fn step_gain(
    state: &mut GainState,
    kind: Kind,
    loop_idx: usize,
    stop2: f64,
) -> Result<(bool, bool), Error> {
    match kind {
        Kind::DiagComplex => {
            let mut update = update_complex(&state.jhj_c, &state.jhr_c)?;
            if state.flag == 1 {
                state.gain = [ONE, ONE];
            } else {
                if loop_idx.is_multiple_of(2) {
                    for u in update.iter_mut() {
                        *u = divide(*u, C64::new(2., 0.))?;
                    }
                }
                for (g, u) in state.gain.iter_mut().zip(update) {
                    *g = *g + u;
                }
            }
        }
        Kind::Phase => {
            conjugate_gradient(&state.jhj_r, &state.jhr_r, &mut state.update_r)?;
            if state.flag == 1 {
                state.params = [0., 0.];
                state.gain = [ONE, ONE];
            } else {
                for k in 0..2 {
                    state.params[k] += state.update_r[k];
                    state.gain[k] = C64::new(state.params[k].cos(), state.params[k].sin());
                }
            }
        }
    }
    let numbness = match kind {
        Kind::DiagComplex => NUMBNESS_COMPLEX,
        Kind::Phase => NUMBNESS_PHASE,
    };
    let result = flag_ladder(state, loop_idx, stop2, numbness);
    if kind == Kind::Phase {
        // update_param_flags: a hard-flagged gain resets its parameters.
        state.param_flag = state.flag == 1;
        if state.param_flag {
            state.params = [0., 0.];
        }
    }
    Ok(result)
}

/// `update_gain_flags` for one gain.
fn flag_ladder(state: &mut GainState, loop_idx: usize, stop2: f64, numbness: f64) -> (bool, bool) {
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
    } else if km0_trend < km1_trend && km1_trend < numbness {
        state.flag = 0;
    } else if km0_trend > km1_trend && km1_trend > numbness {
        state.flag = if state.flag != 0 { 1 } else { -1 };
    }
    if state.flag == 1 {
        state.gain = [ONE, ONE];
        return (converged, true);
    }
    (converged, false)
}

/// What the end of the solve needs of a gain after an iteration.
#[derive(Clone, Copy)]
struct Snapshot {
    gain: [C64; 2],
    params: [f64; 2],
    param_flag: bool,
    trend: f64,
    flag: i8,
}

const EMPTY_SNAPSHOT: Snapshot = Snapshot {
    gain: [ONE, ONE],
    params: [0., 0.],
    param_flag: false,
    trend: 0.,
    flag: 0,
};

/// One interval's epoch: (converged, flagged) per completed iteration, and
/// the first error with its iteration.
struct EpochRecord {
    counts: Vec<(usize, usize)>,
    error: Option<(usize, Error)>,
}

#[allow(clippy::too_many_arguments)]
fn run_interval(
    problem: &Problem,
    kind: Kind,
    cells: &[CellRef],
    stop2: f64,
    states: &mut [GainState],
    snapshots: &mut [Snapshot],
    k0: usize,
    n: usize,
) -> EpochRecord {
    let mut record = EpochRecord {
        counts: Vec::with_capacity(n),
        error: None,
    };
    for j in 0..n {
        let loop_idx = k0 + j;
        accumulate(problem, kind, cells, states);
        let (mut converged, mut flagged) = (0usize, 0usize);
        for state in states.iter_mut() {
            match step_gain(state, kind, loop_idx, stop2) {
                Ok((c, x)) => {
                    converged += usize::from(c);
                    flagged += usize::from(x);
                }
                Err(error) => {
                    record.error = Some((loop_idx, error));
                    return record;
                }
            }
        }
        record.counts.push((converged, flagged));
        let row = &mut snapshots[j * states.len()..(j + 1) * states.len()];
        for (snapshot, state) in row.iter_mut().zip(states.iter_mut()) {
            *snapshot = Snapshot {
                gain: state.gain,
                params: state.params,
                param_flag: state.param_flag,
                trend: state.trend,
                flag: state.flag,
            };
            state.km1_gain = state.gain;
        }
    }
    record
}

fn converged_fraction(converged: usize, flagged: usize, ngains: usize) -> f64 {
    let solvable = ngains - flagged;
    if solvable > 0 {
        converged as f64 / solvable as f64
    } else {
        0.
    }
}

/// The per-iteration record of a counted solve (task W3b,
/// `research/w3b-chainchunks.md`): the converged and flagged gains summed
/// over every interval for each iteration that every interval completed,
/// and the iteration of the first solver error, if any.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Trace {
    pub counts: Vec<(usize, usize)>,
    pub error_iteration: Option<usize>,
}

/// Solve one diagonal term as QuartiCal 0.2.7 does (`diag_complex` or
/// `phase`), with QuartiCal's referencing when `reference_antenna` is set.
pub fn solve(problem: &Problem, settings: &Settings) -> Result<Solution, Error> {
    solve_traced(problem, settings, None)
}

/// `solve`, also returning its `Trace`: the same loop with the counts that
/// the global stop test sums recorded, for replaying the stop test over
/// chunks of intervals (task W3b). Recording changes no arithmetic.
pub fn solve_counted(problem: &Problem, settings: &Settings) -> (Result<Solution, Error>, Trace) {
    let mut trace = Trace::default();
    let result = solve_traced(problem, settings, Some(&mut trace));
    (result, trace)
}

fn solve_traced(
    problem: &Problem,
    settings: &Settings,
    mut trace: Option<&mut Trace>,
) -> Result<Solution, Error> {
    check(problem, settings)?;
    let na = problem.nant;
    let ngains = problem.ntime_bins * problem.nfreq_bins * na;
    let width = na.max(1);
    let nintervals = ngains / width;
    let mut states = vec![FRESH; ngains];
    let cells = interval_cells(
        problem,
        &crate::solve::data_flags(problem),
        &mut states,
        width,
    );
    // init_flags leaves gains without data hard-flagged; the phase kernel's
    // parameter flags start from them too (update_param_flags runs on every
    // iteration before they are read).
    let stop2 = settings.stop_criterion * settings.stop_criterion;
    let kind = settings.kind;
    let iterations = settings.max_iterations.max(1);
    let mut snapshots = vec![EMPTY_SNAPSHOT; EPOCH * ngains];
    let mut k0 = 0;
    let (j, fraction) = loop {
        let n = EPOCH.min(iterations - k0);
        let records: Vec<EpochRecord> = states
            .par_chunks_mut(width)
            .zip(snapshots.par_chunks_mut(EPOCH * width))
            .enumerate()
            .map(|(interval, (chunk, snaps))| {
                run_interval(problem, kind, &cells[interval], stop2, chunk, snaps, k0, n)
            })
            .collect();
        let mut first_error: Option<(usize, usize)> = None;
        for (interval, record) in records.iter().enumerate() {
            if let Some((k, _)) = record.error
                && first_error.is_none_or(|(e, _)| k < e)
            {
                first_error = Some((k, interval));
            }
        }
        let complete = first_error.map_or(n, |(k, _)| k - k0);
        let mut stop = None;
        let mut fraction = 0.;
        for jj in 0..complete {
            let (c, x) = records
                .iter()
                .fold((0, 0), |(c, x), r| (c + r.counts[jj].0, x + r.counts[jj].1));
            if let Some(t) = trace.as_deref_mut() {
                t.counts.push((c, x));
            }
            fraction = converged_fraction(c, x, ngains);
            if fraction >= settings.stop_fraction {
                stop = Some(jj);
                break;
            }
        }
        if let Some(jj) = stop {
            break (jj, fraction);
        }
        if let Some((k, interval)) = first_error {
            if let Some(t) = trace.as_deref_mut() {
                t.error_iteration = Some(k);
            }
            let mut records = records;
            let (_, error) = records[interval].error.take().expect("recorded");
            return Err(error);
        }
        if k0 + n == iterations {
            break (n - 1, fraction);
        }
        k0 += n;
    };
    // finalize_gain_flags on the stopping iteration's snapshots.
    let mut finals: Vec<Snapshot> = Vec::with_capacity(ngains);
    for snaps in snapshots.chunks(EPOCH * width).take(nintervals) {
        for s in &snaps[j * width..(j + 1) * width] {
            let mut s = *s;
            if s.trend > TREND_LIMIT {
                s.flag = 1;
                s.gain = [ONE, ONE];
            } else if s.flag == -1 {
                s.flag = 0;
            }
            finals.push(s);
        }
    }
    if let Some(r) = settings.reference_antenna {
        for interval in finals.chunks_mut(width) {
            match kind {
                Kind::DiagComplex => reference_gains(interval, r),
                Kind::Phase => reference_params(interval, r),
            }
        }
    } else if kind == Kind::Phase {
        for s in finals.iter_mut() {
            if s.flag != 0 {
                s.gain = [ONE, ONE];
            }
        }
    }
    Ok(Solution {
        gains: finals.iter().map(|s| s.gain).collect(),
        flags: finals.iter().map(|s| s.flag).collect(),
        iterations: k0 + j + 1,
        converged_fraction: fraction,
    })
}

/// `reference_gains` of `diag_complex` for one interval: every gain times
/// `conj(g_r)/|g_r|` per hand unless the reference gain is flagged; flagged
/// gains become the identity.
fn reference_gains(interval: &mut [Snapshot], r: usize) {
    let mut rg = interval[r].gain;
    if interval[r].flag == 0 {
        for v in rg.iter_mut() {
            let a = v.re.hypot(v.im);
            *v = C64::new(v.re / a, -v.im / a);
        }
    }
    for s in interval.iter_mut() {
        // v1_imul_v2(g, rg, g) with zero off-diagonals.
        let g = jones::mul(&diag(&s.gain), &diag(&rg));
        s.gain = [g[0], g[3]];
        if s.flag != 0 {
            s.gain = [ONE, ONE];
        }
    }
}

/// `reference_params` of `phase` for one interval: parameters minus the
/// reference antenna's (where the parameters are not flagged), the gains
/// rebuilt from them, then the flags applied.
fn reference_params(interval: &mut [Snapshot], r: usize) {
    let rp = interval[r].params;
    for s in interval.iter_mut() {
        if !s.param_flag {
            s.params = [s.params[0] - rp[0], s.params[1] - rp[1]];
        }
        s.gain = [
            C64::new(s.params[0].cos(), s.params[0].sin()),
            C64::new(s.params[1].cos(), s.params[1].sin()),
        ];
        if s.param_flag {
            s.params = [0., 0.];
        }
        if s.flag != 0 {
            s.gain = [ONE, ONE];
        }
    }
}

/// CASA's solution statistics per gain and hand (`VisCalSolver2::getErrors`,
/// `SolvableVisCal::formSolveSNR`), computed on rang's (not pre-averaged)
/// cells of each interval at the solved gains: over the unflagged cells with
/// positive weight of the parallel hands, `chi2 = sum w |r|^2` and `nWt`
/// their count; per gain and hand `hess = sum w |dV/dg|^2`;
/// `k2 = chi2 / max(2 (nWt - nParOK), 1)`, `err = 1 / sqrt(hess / k2 / 2)`,
/// `snr = |g| / err` (9999999 when `err` is 0). Gains flagged in `flags`
/// are not OK and get SNR 0. Returns `(snr, err)`, `ngains * 2` each.
pub fn solution_statistics(
    problem: &Problem,
    gains: &[[C64; 2]],
    flags: &[i8],
) -> Result<(Vec<f32>, Vec<f32>), Error> {
    let na = problem.nant;
    let ngains = problem.ntime_bins * problem.nfreq_bins * na;
    if gains.len() != ngains || flags.len() != ngains {
        return Err(Error::Shape("gains or flags length"));
    }
    let settings = Settings::new(Kind::DiagComplex);
    check(
        problem,
        &Settings {
            reference_antenna: None,
            ..settings
        },
    )?;
    let width = na.max(1);
    let mut states = vec![FRESH; ngains];
    let cells = interval_cells(
        problem,
        &crate::solve::data_flags(problem),
        &mut states,
        width,
    );
    let mut snr = vec![0f32; 2 * ngains];
    let mut err = vec![0f32; 2 * ngains];
    snr.par_chunks_mut(2 * width)
        .zip(err.par_chunks_mut(2 * width))
        .enumerate()
        .for_each(|(interval, (snr, err))| {
            let g = &gains[interval * width..(interval + 1) * width];
            let f = &flags[interval * width..(interval + 1) * width];
            let mut hess = vec![[0f64; 2]; width];
            let (mut chi2, mut nwt) = (0f64, 0usize);
            for c in &cells[interval] {
                let (p, q, cell) = (c.p as usize, c.q as usize, c.cell);
                if f[p] != 0 || f[q] != 0 {
                    continue;
                }
                let data = jones::from_f32(&problem.data[8 * cell..8 * cell + 8]);
                let m = model_at(problem, cell, cell % problem.nchan);
                for (h, k) in [(0usize, 0usize), (1, 3)] {
                    let w = f64::from(problem.weights[4 * cell + k]);
                    if w.is_nan() || w <= 0. {
                        continue;
                    }
                    let v = g[p][h] * m[k] * g[q][h].conj();
                    chi2 += w * (data[k] - v).norm2();
                    nwt += 1;
                    hess[p][h] += w * (m[k] * g[q][h].conj()).norm2();
                    hess[q][h] += w * (g[p][h] * m[k]).norm2();
                }
            }
            let nparok = 2 * f.iter().filter(|&&x| x == 0).count();
            let ndof = (2 * nwt.saturating_sub(nparok)).max(1);
            let k2 = chi2 / ndof as f64;
            for a in 0..width {
                for h in 0..2 {
                    if f[a] != 0 {
                        continue;
                    }
                    let e = if hess[a][h] > 0. {
                        (1. / (hess[a][h] / k2 / 2.).sqrt()) as f32
                    } else {
                        0.
                    };
                    err[2 * a + h] = e;
                    let amp = g[a][h].re.hypot(g[a][h].im) as f32;
                    snr[2 * a + h] = if e > 0. { amp / e } else { 9_999_999. };
                }
            }
        });
    Ok((snr, err))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A random problem `V = G_p M G_q^H` (+ noise) for `nant` antennas.
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
        nrow: usize,
        nchan: usize,
        nant: usize,
        ntime: usize,
        truth: Vec<[C64; 2]>,
    }

    fn lcg(state: &mut u64) -> f64 {
        *state = state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        ((*state >> 11) as f64) / ((1u64 << 53) as f64)
    }

    fn sim(nant: usize, ntime: usize, nchan: usize, noise: f64, phase_only: bool) -> Sim {
        let mut s = 20261106u64;
        let mut truth = Vec::new();
        for _t in 0..ntime {
            for _a in 0..nant {
                let g: [C64; 2] = std::array::from_fn(|_| {
                    let amp = if phase_only {
                        1.
                    } else {
                        0.8 + 0.4 * lcg(&mut s)
                    };
                    let ph = (lcg(&mut s) - 0.5) * 2.;
                    C64::new(amp * ph.cos(), amp * ph.sin())
                });
                truth.push(g);
            }
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
                    C64::new(10. + lcg(&mut s), lcg(&mut s) - 0.5),
                    C64::new(0.1 * (lcg(&mut s) - 0.5), 0.1 * (lcg(&mut s) - 0.5)),
                    C64::new(0.1 * (lcg(&mut s) - 0.5), 0.1 * (lcg(&mut s) - 0.5)),
                    C64::new(9. + lcg(&mut s), lcg(&mut s) - 0.5),
                ];
                let v = jones::mul(
                    &jones::mul(&diag(&truth[t * nant + p]), &m),
                    &jones::adjoint(&diag(&truth[t * nant + q])),
                );
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
            data,
            model,
            a1,
            a2,
            tb,
            nrow,
            nchan,
            nant,
            ntime,
            truth,
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

    fn max_product_error(s: &Sim, sol: &Solution) -> f64 {
        let mut worst: f64 = 0.;
        for t in 0..s.ntime {
            for p in 0..s.nant {
                for q in p + 1..s.nant {
                    for h in 0..2 {
                        let g = sol.gains[t * s.nant + p][h] * sol.gains[t * s.nant + q][h].conj();
                        let e = s.truth[t * s.nant + p][h] * s.truth[t * s.nant + q][h].conj();
                        worst = worst.max((g - e).norm2().sqrt());
                    }
                }
            }
        }
        worst
    }

    #[test]
    fn noise_free_products_are_recovered() {
        for (kind, phase_only) in [(Kind::DiagComplex, false), (Kind::Phase, true)] {
            let s = sim(5, 3, 4, 0., phase_only);
            let settings = Settings {
                max_iterations: 200,
                stop_fraction: 1.0,
                stop_criterion: 1e-12,
                ..Settings::new(kind)
            };
            let sol = solve(&problem(&s), &settings).unwrap();
            assert!(sol.flags.iter().all(|&f| f == 0), "{kind:?}");
            let err = max_product_error(&s, &sol);
            assert!(err < 1e-5, "{kind:?}: {err}");
            // QuartiCal's referencing: antenna 0 has zero phase.
            for t in 0..s.ntime {
                for h in 0..2 {
                    assert!(sol.gains[t * s.nant][h].im.abs() < 1e-12);
                }
            }
        }
    }

    #[test]
    fn counted_solve_equals_solve() {
        // Task W3b: recording the stop test's counts changes nothing, and the
        // counts reproduce the stop.
        let s = sim(6, 4, 8, 0.5, false);
        for kind in [Kind::DiagComplex, Kind::Phase] {
            let settings = Settings::new(kind);
            let a = solve(&problem(&s), &settings).unwrap();
            let (b, trace) = solve_counted(&problem(&s), &settings);
            let b = b.unwrap();
            assert_eq!(a.gains, b.gains);
            assert_eq!(a.flags, b.flags);
            assert_eq!(a.iterations, b.iterations);
            assert_eq!(
                a.converged_fraction.to_bits(),
                b.converged_fraction.to_bits()
            );
            assert!(trace.counts.len() >= a.iterations);
            assert_eq!(trace.error_iteration, None);
            let p = problem(&s);
            let ngains = p.ntime_bins * p.nfreq_bins * p.nant;
            let (c, x) = trace.counts[a.iterations - 1];
            let f = converged_fraction(c, x, ngains);
            assert_eq!(f.to_bits(), a.converged_fraction.to_bits());
        }
    }

    #[test]
    fn threads_are_bit_identical() {
        let s = sim(6, 4, 8, 0.5, false);
        let mut results = Vec::new();
        for threads in [1, 2, 4] {
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()
                .unwrap();
            for kind in [Kind::DiagComplex, Kind::Phase] {
                let sol = pool.install(|| solve(&problem(&s), &Settings::new(kind)).unwrap());
                let bits: Vec<u64> = sol
                    .gains
                    .iter()
                    .flat_map(|g| {
                        [
                            g[0].re.to_bits(),
                            g[0].im.to_bits(),
                            g[1].re.to_bits(),
                            g[1].im.to_bits(),
                        ]
                    })
                    .collect();
                results.push((threads, kind, bits, sol.iterations, sol.flags.clone()));
            }
        }
        for r in &results[2..] {
            let base = results.iter().find(|b| b.1 == r.1).unwrap();
            assert_eq!(base.2, r.2);
            assert_eq!(base.3, r.3);
            assert_eq!(base.4, r.4);
        }
    }

    #[test]
    fn antennas_without_data_are_flagged() {
        let mut s = sim(4, 2, 2, 0., false);
        for row in 0..s.nrow {
            if s.a1[row] == 3 || s.a2[row] == 3 {
                s.flag_row[row] = 1;
            }
        }
        let sol = solve(&problem(&s), &Settings::new(Kind::DiagComplex)).unwrap();
        for t in 0..2 {
            assert_eq!(sol.flags[t * 4 + 3], 1);
            assert_eq!(sol.gains[t * 4 + 3], [ONE, ONE]);
            assert_eq!(sol.flags[t * 4], 0);
        }
    }

    #[test]
    fn snr_scales_with_noise() {
        let quiet = sim(5, 1, 16, 0.01, false);
        let loud = sim(5, 1, 16, 0.1, false);
        let mut out = Vec::new();
        for s in [&quiet, &loud] {
            let sol = solve(&problem(s), &Settings::new(Kind::DiagComplex)).unwrap();
            let (snr, _) = solution_statistics(&problem(s), &sol.gains, &sol.flags).unwrap();
            out.push(snr.iter().map(|&x| f64::from(x)).sum::<f64>() / snr.len() as f64);
        }
        let ratio = out[0] / out[1];
        assert!(ratio > 7. && ratio < 13., "{ratio}");
    }
}
