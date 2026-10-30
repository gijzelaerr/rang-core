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
use rayon::prelude::*;

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
    let product = jones::mul(weighted_residual, rop);
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
        .into_par_iter()
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

/// Everything the solver keeps per gain, so that the gains of one solution
/// interval are one contiguous slice that a rayon task owns.
#[derive(Clone, Copy)]
struct GainState {
    gain: Jones,
    km1_gain: Jones,
    km1_abs2_diff: f64,
    trend: f64,
    update: [C64; 4],
    jhj: [[C64; 4]; 4],
    jhr: [C64; 4],
    flag: i8,
}

/// One unflagged cell of a solution interval and its two antennas.
struct CellRef {
    cell: usize,
    p: u32,
    q: u32,
}

/// The unflagged cells of every solution interval, in the order of the
/// serial sweep (rows ascending, then channels ascending), built once
/// instead of testing every cell's flag on each of up to 50 sweeps; and
/// `init_flags`: a gain stays flagged unless an unflagged cell involves it.
/// `states` holds `width` gains per interval; rows must be sorted by time
/// bin, which `check` enforces.
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

/// `compute_jhj_jhr` for the gains of one interval (`states`, indexed by
/// antenna) over its unflagged cells in the serial sweep's order, pq before
/// qp: every gain receives its contributions in the order of the serial
/// sweep over all cells, so its sums are bit-identical.
fn accumulate_interval(problem: &Problem, cells: &[CellRef], states: &mut [GainState]) {
    for state in states.iter_mut() {
        state.jhj = [[C64::ZERO; 4]; 4];
        state.jhr = [C64::ZERO; 4];
    }
    for c in cells {
        let (p, q, cell) = (c.p as usize, c.q as usize, c.cell);
        let w: [f64; 4] = std::array::from_fn(|c| f64::from(problem.weights[4 * cell + c]));
        let data = jones::from_f32(&problem.data[8 * cell..8 * cell + 8]);
        let m = model_at(problem, cell, cell % problem.nchan);
        let gp = states[p].gain;
        let gq = states[q].gain;
        // rop_pq = Gq M^H, rop_qp = Gp M (lop = I for a single term).
        let rop_pq = jones::mul(&gq, &jones::adjoint(&m));
        let rop_qp = jones::mul(&gp, &m);
        if jones::is_finite(&gp)
            && jones::is_finite(&rop_pq)
            && jones::is_finite(&rop_qp)
            && finite(&w)
        {
            // I^H Gp = Gp exactly for finite Gp (see accumulate_finite).
            let predicted = jones::mul(&gp, &jones::adjoint(&rop_pq));
            let residual: Jones = std::array::from_fn(|k| data[k] - predicted[k]);
            let wr_pq: Jones = std::array::from_fn(|k| real_scale(residual[k], w[k]));
            if jones::is_finite(&wr_pq) {
                let wr_qp = jones::adjoint(&wr_pq);
                let sp = &mut states[p];
                accumulate_finite(&rop_pq, &w, &wr_pq, &mut sp.jhr, &mut sp.jhj);
                // QuartiCal reuses the pq weight order for qp.
                let sq = &mut states[q];
                accumulate_finite(&rop_qp, &w, &wr_qp, &mut sq.jhr, &mut sq.jhj);
                continue;
            }
        }
        let lop_gp = jones::mul(&jones::adjoint(&IDENTITY), &gp);
        let predicted = jones::mul(&lop_gp, &jones::adjoint(&rop_pq));
        let residual: Jones = std::array::from_fn(|k| data[k] - predicted[k]);
        let wr_pq: Jones = std::array::from_fn(|k| real_scale(residual[k], w[k]));
        let wr_qp = jones::adjoint(&wr_pq);
        let sp = &mut states[p];
        accumulate(&rop_pq, &w, &wr_pq, &mut sp.jhr, &mut sp.jhj);
        // QuartiCal reuses the pq weight order for qp.
        let sq = &mut states[q];
        accumulate(&rop_qp, &w, &wr_qp, &mut sq.jhr, &mut sq.jhj);
    }
    for state in states.iter_mut() {
        fill_lower(&mut state.jhj);
    }
}

/// `compute_update`, `finalize_update` and `update_gain_flags` for one gain,
/// operation for operation as the serial loops over all gains did them.
/// Returns whether the gain converged and whether it is flagged.
fn step_gain(state: &mut GainState, loop_idx: usize, stop2: f64) -> Result<(bool, bool), Error> {
    conjugate_gradient(&state.jhj, &state.jhr, &mut state.update)?;
    // finalize_update
    if state.flag == 1 {
        state.gain = IDENTITY;
        return Ok((false, true));
    }
    if loop_idx.is_multiple_of(2) {
        for value in state.update.iter_mut() {
            *value = divide(*value, C64::new(2., 0.))?;
        }
    }
    for k in 0..4 {
        state.gain[k] = state.gain[k] + state.update[k];
    }
    // update_gain_flags
    let mut km1_abs2 = 0.;
    let mut km0_abs2_diff = 0.;
    for k in 0..4 {
        let (old, new) = (state.km1_gain[k], state.gain[k]);
        let diff = old - new;
        km1_abs2 += old.re * old.re + old.im * old.im;
        km0_abs2_diff += diff.re * diff.re + diff.im * diff.im;
    }
    if km1_abs2 == 0. {
        state.flag = 1;
        state.gain = IDENTITY;
        return Ok((false, true));
    }
    let km1_abs2_diff = state.km1_abs2_diff;
    state.km1_abs2_diff = km0_abs2_diff;
    if loop_idx < 2 {
        return Ok((false, false));
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
        state.gain = IDENTITY;
        return Ok((converged, true));
    }
    Ok((converged, false))
}

/// Iterations each interval runs between two global stop tests.
const EPOCH: usize = 8;

/// What `finalize_gain_flags` and the output need of a gain after an
/// iteration.
#[derive(Clone, Copy)]
struct Snapshot {
    gain: Jones,
    trend: f64,
    flag: i8,
}

const EMPTY_SNAPSHOT: Snapshot = Snapshot {
    gain: IDENTITY,
    trend: 0.,
    flag: 0,
};

/// One interval's record of an epoch: converged and flagged counts of each
/// iteration it completed, and the first error, with its iteration.
struct EpochRecord {
    counts: Vec<(usize, usize)>,
    error: Option<(usize, Error)>,
}

/// The read-only inputs of every interval task.
struct Context<'a> {
    problem: &'a Problem<'a>,
    cells: Vec<Vec<CellRef>>,
    stop2: f64,
}

/// Run iterations `k0..k0 + n` of one interval. After each iteration the
/// interval's gains are recorded in `snapshots` (`n * nant`) and copied to
/// `km1_gain`. The copy is unconditional: while the global loop continues,
/// QuartiCal copies on every iteration but the last, and nothing reads
/// `km1_gain` after the loop ends.
fn run_interval(
    context: &Context,
    interval: usize,
    states: &mut [GainState],
    snapshots: &mut [Snapshot],
    k0: usize,
    n: usize,
) -> EpochRecord {
    let problem = context.problem;
    let mut record = EpochRecord {
        counts: Vec::with_capacity(n),
        error: None,
    };
    for j in 0..n {
        let loop_idx = k0 + j;
        accumulate_interval(problem, &context.cells[interval], states);
        let (mut converged, mut flagged) = (0usize, 0usize);
        for state in states.iter_mut() {
            match step_gain(state, loop_idx, context.stop2) {
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

/// The global outcome of an epoch that started at iteration `k0` and ran
/// `n` iterations, as the serial loop would have reached it.
#[derive(Debug, PartialEq)]
enum Outcome {
    /// The stop test passed at offset `j` (iteration `k0 + j`).
    Stop { j: usize, fraction: f64 },
    /// The serial loop would have failed at an iteration of this epoch.
    Fail(usize),
    /// Neither; the fraction after the epoch's last iteration.
    Continue { fraction: f64 },
}

/// Serial decision over the totals of an epoch. `totals[j]` sums the counts
/// of every interval at offset `j`, for the offsets every interval
/// completed; `first_error` is the earliest failing offset, if any. The stop
/// test is applied in iteration order before the earliest error, so an
/// error after the stop (which the serial loop never reaches) is ignored.
fn decide(
    totals: &[(usize, usize)],
    first_error: Option<usize>,
    ngains: usize,
    stop_fraction: f64,
) -> Outcome {
    let mut fraction = 0.;
    for (j, &(converged, flagged)) in totals.iter().enumerate() {
        fraction = converged_fraction(converged, flagged, ngains);
        if fraction >= stop_fraction {
            return Outcome::Stop { j, fraction };
        }
    }
    match first_error {
        Some(j) => Outcome::Fail(j),
        None => Outcome::Continue { fraction },
    }
}

/// Solve for one `complex` term as QuartiCal 0.2.7 does with rang's settings.
///
/// QuartiCal's iteration loop has one global stop test (the converged
/// fraction over all gains), but until it stops, each solution interval
/// (time bin x frequency bin, `nant` gains) evolves independently of the
/// others. Each interval therefore runs `EPOCH` iterations on its own, on
/// rayon's global pool (`RAYON_NUM_THREADS`), recording its counts and gains
/// after every iteration; the stop test is then applied serially, iteration
/// by iteration, and the gains of the stopping iteration are taken from the
/// record. No floating-point value is reduced across intervals, so the
/// result is bit-identical to the serial loop at every thread count.
pub fn solve(problem: &Problem, settings: &Settings) -> Result<Solution, Error> {
    check(problem)?;
    let na = problem.nant;
    let ngains = problem.ntime_bins * problem.nfreq_bins * na;
    let width = na.max(1);
    let mut states = vec![
        GainState {
            gain: IDENTITY,
            km1_gain: IDENTITY,
            km1_abs2_diff: 0.,
            trend: 0.,
            update: [C64::ZERO; 4],
            jhj: [[C64::ZERO; 4]; 4],
            jhr: [C64::ZERO; 4],
            flag: 1,
        };
        ngains
    ];
    let context = Context {
        problem,
        cells: interval_cells(problem, &data_flags(problem), &mut states, width),
        stop2: settings.stop_criterion * settings.stop_criterion,
    };
    let iterations = settings.max_iterations.max(1);
    let mut snapshots = vec![EMPTY_SNAPSHOT; EPOCH * ngains];
    let mut k0 = 0;
    let (j, fraction) = loop {
        let n = EPOCH.min(iterations - k0);
        let records: Vec<EpochRecord> = states
            .par_chunks_mut(width)
            .zip(snapshots.par_chunks_mut(EPOCH * width))
            .enumerate()
            .map(|(interval, (chunk, snaps))| run_interval(&context, interval, chunk, snaps, k0, n))
            .collect();
        // The earliest failing iteration, and the first interval failing there.
        let mut first_error: Option<(usize, usize)> = None;
        for (interval, record) in records.iter().enumerate() {
            if let Some((k, _)) = record.error
                && first_error.is_none_or(|(e, _)| k < e)
            {
                first_error = Some((k, interval));
            }
        }
        let complete = first_error.map_or(n, |(k, _)| k - k0);
        // Integer counts: their sum does not depend on the order.
        let totals: Vec<(usize, usize)> = (0..complete)
            .map(|j| {
                records.iter().fold((0, 0), |(c, x), r| {
                    let (dc, dx) = r.counts[j];
                    (c + dc, x + dx)
                })
            })
            .collect();
        match decide(
            &totals,
            first_error.map(|(k, _)| k - k0),
            ngains,
            settings.stop_fraction,
        ) {
            Outcome::Stop { j, fraction } => break (j, fraction),
            Outcome::Fail(_) => {
                let (_, interval) = first_error.expect("a failure has an error");
                let mut records = records;
                let (_, error) = records[interval].error.take().expect("recorded");
                return Err(error);
            }
            Outcome::Continue { fraction } => {
                if k0 + n == iterations {
                    break (n - 1, fraction);
                }
                k0 += n;
            }
        }
    };
    // The gains of the stopping (or last) iteration, from the record.
    let mut gains = Vec::with_capacity(ngains);
    let mut flags = Vec::with_capacity(ngains);
    for snaps in snapshots.chunks(EPOCH * width).take(ngains / width) {
        for snapshot in &snaps[j * width..(j + 1) * width] {
            // finalize_gain_flags
            let (gain, flag) = if snapshot.trend > TREND_LIMIT {
                (IDENTITY, 1)
            } else if snapshot.flag == -1 {
                (snapshot.gain, 0)
            } else {
                (snapshot.gain, snapshot.flag)
            };
            gains.push(gain);
            flags.push(flag);
        }
    }
    Ok(Solution {
        gains,
        flags,
        iterations: k0 + j + 1,
        converged_fraction: fraction,
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

    // --- Task P1 (research/p1-solver.md): the parallel solver against the
    // serial solver it replaced. `reference_solve` is the body of `solve` at
    // 43dc3c7 verbatim, except that its calls to the removed
    // `#[inline(always)]` copies of `mul`, `adjoint`, `from_f32` and
    // `all_finite` name the `jones` functions they copied operation for
    // operation.

    fn reference_solve(problem: &Problem, settings: &Settings) -> Result<Solution, Error> {
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
                    let w: [f64; 4] =
                        std::array::from_fn(|c| f64::from(problem.weights[4 * cell + c]));
                    let data = jones::from_f32(&problem.data[8 * cell..8 * cell + 8]);
                    let gp = gains[index(t, f, p)];
                    let gq = gains[index(t, f, q)];
                    let m = model_at(problem, cell, chan);
                    // rop_pq = Gq M^H, rop_qp = Gp M (lop = I for a single term).
                    let rop_pq = jones::mul(&gq, &jones::adjoint(&m));
                    let rop_qp = jones::mul(&gp, &m);
                    let ip = index(t, f, p);
                    let iq = index(t, f, q);
                    if jones::is_finite(&gp)
                        && jones::is_finite(&rop_pq)
                        && jones::is_finite(&rop_qp)
                        && finite(&w)
                    {
                        // I^H Gp = Gp exactly for finite Gp (see accumulate_finite).
                        let predicted = jones::mul(&gp, &jones::adjoint(&rop_pq));
                        let residual: Jones = std::array::from_fn(|k| data[k] - predicted[k]);
                        let wr_pq: Jones = std::array::from_fn(|k| real_scale(residual[k], w[k]));
                        if jones::is_finite(&wr_pq) {
                            let wr_qp = jones::adjoint(&wr_pq);
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
                    km1_abs2 += km1_gain[g][k].re * km1_gain[g][k].re
                        + km1_gain[g][k].im * km1_gain[g][k].im;
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

    /// A deterministic pseudo-random sequence in [-1, 1).
    fn noise(state: &mut u64) -> f64 {
        *state = state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        ((*state >> 11) as f64 / (1u64 << 53) as f64) * 2. - 1.
    }

    struct Synthetic {
        nrow: usize,
        nchan: usize,
        ntime_bins: usize,
        nfreq_bins: usize,
        data: Vec<f32>,
        model: Vec<f32>,
        weights: Vec<f32>,
        flag: Vec<u8>,
        flag_row: Vec<u8>,
        a1: Vec<u32>,
        a2: Vec<u32>,
        time_bin: Vec<u32>,
        freq_bin: Vec<u32>,
    }

    impl Synthetic {
        /// Three time bins of two integrations, 4 antennas with
        /// autocorrelations, 12 channels in 4 interleaved frequency bins,
        /// noisy data, flagged cells and rows, one fully flagged interval
        /// and one cell with an infinite weight (the general path).
        fn new(seed: u64) -> Self {
            let mut state = seed;
            let nant = 4;
            let truth: Vec<Jones> = (0..nant)
                .map(|_| {
                    std::array::from_fn(|k| {
                        let diagonal = if k == 0 || k == 3 { 1. } else { 0. };
                        C64::new(diagonal + 0.2 * noise(&mut state), 0.2 * noise(&mut state))
                    })
                })
                .collect();
            let (ntime_bins, nfreq_bins, nchan) = (3, 4, 12);
            let mut s = Self {
                nrow: 0,
                nchan,
                ntime_bins,
                nfreq_bins,
                data: Vec::new(),
                model: Vec::new(),
                weights: Vec::new(),
                flag: Vec::new(),
                flag_row: Vec::new(),
                a1: Vec::new(),
                a2: Vec::new(),
                time_bin: Vec::new(),
                freq_bin: (0..nchan as u32).map(|c| (c * 7) % 4).collect(),
            };
            for t in 0..2 * ntime_bins {
                for p in 0..nant {
                    for q in p..nant {
                        s.a1.push(p as u32);
                        s.a2.push(q as u32);
                        s.time_bin.push((t / 2) as u32);
                        s.flag_row.push(u8::from(t == 3 && p == 1 && q == 2));
                        for chan in 0..nchan {
                            let m: Jones = std::array::from_fn(|k| {
                                let diagonal = if k == 0 || k == 3 { 1. } else { 0.1 };
                                C64::new(
                                    diagonal + 0.3 * noise(&mut state),
                                    0.3 * noise(&mut state),
                                )
                            });
                            let v =
                                jones::mul(&jones::mul(&truth[p], &m), &jones::adjoint(&truth[q]));
                            for k in 0..4 {
                                s.model.extend([m[k].re as f32, m[k].im as f32]);
                                s.data.extend([
                                    (v[k].re + 0.01 * noise(&mut state)) as f32,
                                    (v[k].im + 0.01 * noise(&mut state)) as f32,
                                ]);
                                s.weights.push(1. + noise(&mut state).abs() as f32);
                                // Flag about one cell in ten, and every cell
                                // of time bin 2, frequency bin 1.
                                let flagged = noise(&mut state) > 0.8
                                    || (t / 2 == 2 && s.freq_bin[chan] == 1);
                                s.flag.push(u8::from(flagged));
                            }
                        }
                    }
                }
            }
            s.nrow = s.a1.len();
            // One unflagged cell with an infinite weight takes the general path.
            let cell = 3 * nchan + 5;
            s.flag[4 * cell..4 * cell + 4].fill(0);
            s.weights[4 * cell + 1] = f32::INFINITY;
            s
        }

        fn problem(&self) -> Problem<'_> {
            Problem {
                nrow: self.nrow,
                nchan: self.nchan,
                ntime_bins: self.ntime_bins,
                nfreq_bins: self.nfreq_bins,
                nant: 4,
                data: &self.data,
                weights: &self.weights,
                model: Model::Stored(&self.model),
                flag: &self.flag,
                flag_row: &self.flag_row,
                antenna1: &self.a1,
                antenna2: &self.a2,
                time_bin: &self.time_bin,
                freq_bin: &self.freq_bin,
            }
        }
    }

    fn bits(solution: &Solution) -> (Vec<u64>, Vec<i8>, usize, u64) {
        let gains = solution
            .gains
            .iter()
            .flat_map(|g| g.iter().flat_map(|c| [c.re.to_bits(), c.im.to_bits()]))
            .collect();
        (
            gains,
            solution.flags.clone(),
            solution.iterations,
            solution.converged_fraction.to_bits(),
        )
    }

    fn in_pool<T: Send>(threads: usize, f: impl FnOnce() -> T + Send) -> T {
        rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build()
            .unwrap()
            .install(f)
    }

    #[test]
    fn parallel_solve_is_bit_identical_to_the_serial_solve() {
        // Iteration counts that ended at the cap, and that ended by the
        // stop test before the cap.
        let mut caps = std::collections::BTreeSet::new();
        let mut stops = std::collections::BTreeSet::new();
        for seed in [1, 2] {
            let synthetic = Synthetic::new(seed);
            let problem = synthetic.problem();
            for (max_iterations, stop_criterion, stop_fraction) in
                [1, 2, 3, 7, 8, 9, 16, 17, 50].into_iter().flat_map(|k| {
                    [1e-2, 1e-3, 1e-5]
                        .into_iter()
                        .flat_map(move |c| [0., 0.2, 0.5, 0.8, 0.99, 1.5].map(|f| (k, c, f)))
                })
            {
                {
                    let settings = Settings {
                        max_iterations,
                        stop_criterion,
                        stop_fraction,
                    };
                    let expected = reference_solve(&problem, &settings).unwrap();
                    if expected.iterations < max_iterations {
                        stops.insert(expected.iterations);
                    } else {
                        caps.insert(expected.iterations);
                    }
                    for threads in [1, 3, 8] {
                        let got = in_pool(threads, || solve(&problem, &settings)).unwrap();
                        assert_eq!(
                            bits(&got),
                            bits(&expected),
                            "seed {seed} max {max_iterations} criterion {stop_criterion} \
                             fraction {stop_fraction} threads {threads}"
                        );
                    }
                }
            }
        }
        // The stop test passes at the first iteration and inside the first
        // and second epochs; the cap ends inside and at the end of an epoch.
        assert!(stops.contains(&1), "{stops:?}");
        assert!(stops.iter().any(|&k| k > 1 && k < EPOCH), "{stops:?}");
        assert!(
            stops.iter().any(|&k| k > EPOCH && k % EPOCH != 0),
            "{stops:?}"
        );
        assert!(caps.contains(&EPOCH) && caps.contains(&(EPOCH + 1)) && caps.contains(&50));
    }

    #[test]
    fn decide_applies_the_stop_test_in_iteration_order() {
        // 10 gains; fractions 0.1, 0.5, 0.9 over the three offsets.
        let totals = [(1, 0), (5, 0), (9, 0)];
        assert_eq!(
            decide(&totals, None, 10, 0.5),
            Outcome::Stop {
                j: 1,
                fraction: 0.5
            }
        );
        assert_eq!(
            decide(&totals, None, 10, 0.95),
            Outcome::Continue { fraction: 0.9 }
        );
        // An error after the stop is never reached by the serial loop.
        assert_eq!(
            decide(&totals[..2], Some(2), 10, 0.5),
            Outcome::Stop {
                j: 1,
                fraction: 0.5
            }
        );
        // An error before any stop fails at its iteration.
        assert_eq!(decide(&totals[..1], Some(1), 10, 0.5), Outcome::Fail(1));
        assert_eq!(decide(&[], Some(0), 10, 0.5), Outcome::Fail(0));
        // Flagged gains leave the denominator; none solvable gives zero.
        assert_eq!(
            decide(&[(2, 6)], None, 10, 0.5),
            Outcome::Stop {
                j: 0,
                fraction: 0.5
            }
        );
        assert_eq!(
            decide(&[(0, 10)], None, 10, 0.5),
            Outcome::Continue { fraction: 0. }
        );
    }

    #[test]
    fn interval_cells_follow_the_serial_order_and_init_flags() {
        let synthetic = Synthetic::new(3);
        let problem = synthetic.problem();
        let width = problem.nant;
        let ngains = problem.ntime_bins * problem.nfreq_bins * width;
        let blank = GainState {
            gain: IDENTITY,
            km1_gain: IDENTITY,
            km1_abs2_diff: 0.,
            trend: 0.,
            update: [C64::ZERO; 4],
            jhj: [[C64::ZERO; 4]; 4],
            jhr: [C64::ZERO; 4],
            flag: 1,
        };
        let mut states = vec![blank; ngains];
        let flags_cell = data_flags(&problem);
        let cells = interval_cells(&problem, &flags_cell, &mut states, width);
        let mut expected = vec![Vec::new(); ngains / width];
        let mut flags = vec![1_i8; ngains];
        for row in 0..problem.nrow {
            for chan in 0..problem.nchan {
                let cell = row * problem.nchan + chan;
                let interval = problem.time_bin[row] as usize * problem.nfreq_bins
                    + problem.freq_bin[chan] as usize;
                let flag = i8::from(flags_cell[cell]);
                flags[interval * width + problem.antenna1[row] as usize] &= flag;
                flags[interval * width + problem.antenna2[row] as usize] &= flag;
                if !flags_cell[cell] {
                    expected[interval].push(cell);
                }
            }
        }
        let got: Vec<Vec<usize>> = cells
            .iter()
            .map(|v| v.iter().map(|c| c.cell).collect())
            .collect();
        assert_eq!(got, expected);
        assert_eq!(states.iter().map(|s| s.flag).collect::<Vec<_>>(), flags);
        // The fully flagged interval (time bin 2, frequency bin 1) is empty.
        assert!(cells[2 * problem.nfreq_bins + 1].is_empty());
    }
}
