// SPDX-License-Identifier: MIT
//! The direction-dependent `diag_complex` term (task DD1, issue #15,
//! `research/dd1-facet-gains.md`): one diagonal gain per (time bin,
//! frequency bin, antenna, direction), all directions solved together
//! against a model with one column per direction (facet), as QuartiCal 0.2.7
//! does with `G.type=diag_complex` and `G.direction_dependent=true`.
//!
//! Portions are a Rust translation of `quartical/gains/complex/diag_kernel.py`
//! and `quartical/gains/general/flagging.py` from QuartiCal 0.2.7,
//! distributed under the MIT License:
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
//! The translation and its integration are part of Rang (MIT).
//!
//! What differs from the direction-independent `diag::solve` (which this
//! module leaves untouched; its small helpers are copied):
//!
//! - the residual of a cell is `V - sum_d G_p,d M_d G_q,d^H` at the gains
//!   entering the iteration, and each direction's `J^H J` and `J^H r` are
//!   accumulated from that one residual with the operator `G_q,d M_d^H`
//!   (directions are not coupled in `J^H J`);
//! - the update is halved on every iteration (`dd_term or loop_idx % 2 == 0`
//!   in `finalize_update`);
//! - pinned directions are not updated (their gains stay at the identity);
//!   the flag ladder and the stop fraction still count their gains;
//! - referencing is per direction, to the reference antenna's gain of the
//!   same direction.
//!
//! `Settings::direction_update` (task DD10, research/dd10-gs.md) selects
//! QuartiCal's update above (`Jacobi`, the default, unchanged) or a
//! Gauss-Seidel sweep over directions, which DD9 (research/dd9-solver.md)
//! found stable where the Jacobi update is not; it has no QuartiCal
//! counterpart.
//!
//! Scope: one term (no chain), four correlations, one chunk, no robust
//! reweighting, no MAD flags. Every solution interval runs `EPOCH`
//! iterations on its own on rayon's pool and the global stop test is
//! applied serially afterwards, as in `diag`, so the result does not depend
//! on the thread count.

use crate::fused::Model;
use crate::jones::{self, C64, Jones};
use crate::solve::Problem;
use rayon::prelude::*;

/// Numbness of the divergence ladder in `update_gain_flags` (`diag_complex`).
const NUMBNESS: f64 = 1e-6;
/// Numbness of the `phase` kernel (`update_gain_flags(..., numbness=1e9)`).
const NUMBNESS_PHASE: f64 = 1e9;
/// Conjugate-gradient stopping threshold on `r^T r` (generalised `invert`).
const CG_TOLERANCE: f64 = 1e-30;

/// The two kernels (task DD3b, research/dd3b-flux-pin.md, adds `Phase`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub enum Kind {
    /// QuartiCal `diag_complex`: amplitude and phase per hand.
    #[default]
    DiagComplex,
    /// QuartiCal `phase` with a direction axis: phase per hand.
    Phase,
}
/// How one iteration updates the directions (task DD10,
/// research/dd10-gs.md).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub enum DirectionUpdate {
    /// QuartiCal 0.2.7: every direction's update from one residual at the
    /// gains entering the iteration (Jacobi over directions).
    #[default]
    Jacobi,
    /// Gauss-Seidel over directions (DD9's reference arm I2): direction d's
    /// `J^H J` and `J^H r` from the residual after directions `0..d` were
    /// updated in this iteration; the same halved per-direction update; the
    /// flag ladder on every gain after the sweep. `diag_complex` only.
    GaussSeidel,
}

/// Trend above which `finalize_gain_flags` hard-flags a gain.
const TREND_LIMIT: f64 = 1e-6;
/// `invert` (non-generalised): no update below this determinant.
const DET_LIMIT: f64 = 1e-6;
/// Iterations each interval runs between two global stop tests.
const EPOCH: usize = 8;

#[derive(Clone, Debug)]
pub struct Settings {
    pub max_iterations: usize,
    pub stop_criterion: f64,
    pub stop_fraction: f64,
    /// QuartiCal's `solver.reference_antenna`; `None` leaves the gains
    /// unreferenced.
    pub reference_antenna: Option<usize>,
    /// QuartiCal's `G.pinned_directions` (its default is `[0]`).
    pub pinned_directions: Vec<usize>,
    pub kind: Kind,
    /// `phase` only: use, as QuartiCal 0.2.7 does, the gain of the **last**
    /// direction in every direction's `J^H r` (its `gains_p[active_term]`
    /// holds the last direction after the direction loop of
    /// `compute_jhj_jhr`). `false` uses each direction's own gain.
    pub phase_last_direction_gain: bool,
    /// Jacobi (QuartiCal's, the default) or Gauss-Seidel over directions.
    pub direction_update: DirectionUpdate,
}

impl Default for Settings {
    /// Rang's frozen QuartiCal settings (as `diag::Settings::new`), no
    /// pinned direction.
    fn default() -> Self {
        Self {
            max_iterations: 50,
            stop_criterion: 1e-7,
            stop_fraction: 0.99,
            reference_antenna: Some(0),
            pinned_directions: Vec::new(),
            kind: Kind::DiagComplex,
            phase_last_direction_gain: true,
            direction_update: DirectionUpdate::Jacobi,
        }
    }
}

#[derive(Debug, Clone)]
pub struct Solution {
    /// `ntime_bins * nfreq_bins * nant * ndir` gains `[g_x, g_y]`.
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

fn diag(g: &[C64; 2]) -> Jones {
    [g[0], C64::ZERO, C64::ZERO, g[1]]
}

/// `problem.model` must be `Model::Stored` with `nrow * nchan * ndir * 8`
/// values (cell-major, then direction, then correlation).
fn check(problem: &Problem, ndir: usize, settings: &Settings) -> Result<(), Error> {
    let cells = problem.nrow * problem.nchan;
    if ndir == 0 {
        return Err(Error::Shape("at least one direction"));
    }
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
        Model::Stored(m) if m.len() == 8 * cells * ndir => {}
        Model::Stored(_) => return Err(Error::Shape("model length (nrow * nchan * ndir * 8)")),
        Model::Scalar(_) => return Err(Error::Shape("a DD model must be stored")),
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
    if settings.pinned_directions.iter().any(|&d| d >= ndir) {
        return Err(Error::Settings("pinned direction out of range"));
    }
    if !(settings.stop_criterion.is_finite() && settings.stop_fraction.is_finite()) {
        return Err(Error::Settings(
            "stop criterion and fraction must be finite",
        ));
    }
    if settings.direction_update == DirectionUpdate::GaussSeidel
        && settings.kind != Kind::DiagComplex
    {
        return Err(Error::Settings(
            "the Gauss-Seidel direction update needs diag_complex",
        ));
    }
    Ok(())
}

#[derive(Clone, Copy)]
struct GainState {
    gain: [C64; 2],
    km1_gain: [C64; 2],
    km1_abs2_diff: f64,
    trend: f64,
    jhj: [C64; 2],
    jhr: [C64; 2],
    /// `phase`: parameters, their flag, real `J^H J` (2x2), `J^H r`, and
    /// the warm-started update.
    params: [f64; 2],
    param_flag: bool,
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
    jhj: [C64::ZERO; 2],
    jhr: [C64::ZERO; 2],
    params: [0., 0.],
    param_flag: false,
    jhj_r: [0.; 4],
    jhr_r: [0.; 2],
    update_r: [0.; 2],
    flag: 1,
};

/// The kernel and its options, as `run_interval` needs them.
#[derive(Clone, Copy)]
struct Mode {
    kind: Kind,
    last_direction_gain: bool,
    gauss_seidel: bool,
}

struct CellRef {
    cell: usize,
    p: u32,
    q: u32,
}

/// The unflagged cells of every interval in the serial sweep's order, and
/// `init_flags`: every direction's gain of an antenna an unflagged cell
/// involves starts unflagged.
fn interval_cells(
    problem: &Problem,
    ndir: usize,
    flags_cell: &[bool],
    states: &mut [GainState],
) -> Vec<Vec<CellRef>> {
    let width = problem.nant * ndir;
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
                        for d in 0..ndir {
                            chunk[p as usize * ndir + d].flag = 0;
                            chunk[q as usize * ndir + d].flag = 0;
                        }
                    }
                }
            }
            cells
        })
        .collect()
}

/// `compute_jhwj_jhwr_elem` of `diag_complex` (four correlations, lop = I).
fn elem_complex(rop: &Jones, w: &[f64; 4], res: &Jones, jhr: &mut [C64; 2], jhj: &mut [C64; 2]) {
    let res = [res[0], C64::ZERO, C64::ZERO, res[3]];
    let product = jones::mul(&jones::mul(&IDENTITY, &res), rop);
    jhr[0] = jhr[0] + product[0];
    jhr[1] = jhr[1] + product[3];
    let (r0, r3) = (rop[0], rop[3]);
    jhj[0] = jhj[0] + real_scale(r0, w[0]) * r0.conj();
    jhj[1] = jhj[1] + real_scale(r3, w[3]) * r3.conj();
}

/// `iabsdivsq` on one value: `0` for `0`, else `1/|v|^2`.
fn absdivsq(v: C64) -> C64 {
    if v.re == 0. && v.im == 0. {
        C64::ZERO
    } else {
        C64::new(1. / (v.re * v.re + v.im * v.im), 0.)
    }
}

/// `compute_jhwj_jhwr_elem` of `phase` (four correlations, lop = I), as
/// `diag::elem_phase`.
fn elem_phase(
    rop: &Jones,
    w: &[f64; 4],
    gain: &[C64; 2],
    res: &Jones,
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
    jhr[0] += (minus_i * gc_0 * r_0).re;
    jhr[1] += (minus_i * gc_3 * r_3).re;
    let w_0 = normf[0] * C64::new(w[0], 0.);
    let w_3 = normf[3] * C64::new(w[3], 0.);
    let (jh_00, jh_33) = (ONE * rop[0], ONE * rop[3]);
    let jhwj_00 = jh_00 * w_0 * jh_00.conj();
    let jhwj_33 = jh_33 * w_3 * jh_33.conj();
    jhj[0] += jhwj_00.re;
    jhj[3] += jhwj_33.re;
}

/// Generalised `invert`: conjugate gradients on the real 2x2 system,
/// warm-started from `x`, at most two steps (as `diag`).
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

/// `compute_jhj_jhr` for one interval's gains (indexed `antenna * ndir + d`).
#[allow(clippy::too_many_arguments)]
fn accumulate(
    problem: &Problem,
    models: &[f32],
    ndir: usize,
    mode: Mode,
    cells: &[CellRef],
    states: &mut [GainState],
    rop_pq: &mut [Jones],
    rop_qp: &mut [Jones],
) {
    for s in states.iter_mut() {
        s.jhj = [C64::ZERO; 2];
        s.jhr = [C64::ZERO; 2];
        s.jhj_r = [0.; 4];
        s.jhr_r = [0.; 2];
    }
    let adj_identity = jones::adjoint(&IDENTITY);
    for c in cells {
        let (p, q, cell) = (c.p as usize, c.q as usize, c.cell);
        let w: [f64; 4] = std::array::from_fn(|k| f64::from(problem.weights[4 * cell + k]));
        let mut r = jones::from_f32(&problem.data[8 * cell..8 * cell + 8]);
        let mut v_pq: Jones = [C64::ZERO; 4];
        for d in 0..ndir {
            let base = 8 * (cell * ndir + d);
            let m = jones::from_f32(&models[base..base + 8]);
            let dp = diag(&states[p * ndir + d].gain);
            let dq = diag(&states[q * ndir + d].gain);
            rop_pq[d] = jones::mul(&dq, &jones::adjoint(&m));
            rop_qp[d] = jones::mul(&dp, &m);
            let v_pqd = jones::mul(&jones::mul(&adj_identity, &dp), &jones::adjoint(&rop_pq[d]));
            for k in 0..4 {
                v_pq[k] = v_pq[k] + v_pqd[k];
            }
        }
        match mode.kind {
            Kind::DiagComplex => {
                for k in 0..4 {
                    r[k] = r[k] - v_pq[k];
                }
            }
            Kind::Phase => {
                // absv1_idiv_absv2(v, r): |v|/|r| (0 where r is 0); r *= it.
                for k in 0..4 {
                    let n = if r[k].re == 0. && r[k].im == 0. {
                        C64::ZERO
                    } else {
                        C64::new((v_pq[k].norm2() / r[k].norm2()).sqrt(), 0.)
                    };
                    r[k] = r[k] * n - v_pq[k];
                }
            }
        }
        let wr_pq: Jones = std::array::from_fn(|k| real_scale(r[k], w[k]));
        let wr_qp = jones::adjoint(&wr_pq);
        for d in 0..ndir {
            match mode.kind {
                Kind::DiagComplex => {
                    let sp = &mut states[p * ndir + d];
                    elem_complex(&rop_pq[d], &w, &wr_pq, &mut sp.jhr, &mut sp.jhj);
                    let sq = &mut states[q * ndir + d];
                    elem_complex(&rop_qp[d], &w, &wr_qp, &mut sq.jhr, &mut sq.jhj);
                }
                Kind::Phase => {
                    let dg = if mode.last_direction_gain {
                        ndir - 1
                    } else {
                        d
                    };
                    let (gp, gq) = (states[p * ndir + dg].gain, states[q * ndir + dg].gain);
                    let sp = &mut states[p * ndir + d];
                    elem_phase(&rop_pq[d], &w, &gp, &wr_pq, &mut sp.jhr_r, &mut sp.jhj_r);
                    let sq = &mut states[q * ndir + d];
                    elem_phase(&rop_qp[d], &w, &gq, &wr_qp, &mut sq.jhr_r, &mut sq.jhj_r);
                }
            }
        }
    }
}

/// The Gauss-Seidel direction sweep of one iteration (`diag_complex`, task
/// DD10, research/dd10-gs.md): for each free direction d in order, its
/// `J^H J` and `J^H r` from the residual at the current gains (directions
/// `0..d` already updated), then its update exactly as `step_gain`'s (halved;
/// flagged gains held at 1). The flag ladder runs afterwards in
/// `run_interval`, with the update already applied.
#[allow(clippy::too_many_arguments)]
fn gauss_seidel_sweep(
    problem: &Problem,
    models: &[f32],
    ndir: usize,
    pinned: &[bool],
    cells: &[CellRef],
    states: &mut [GainState],
    rop_pq: &mut [Jones],
    rop_qp: &mut [Jones],
) -> Result<(), Error> {
    let adj_identity = jones::adjoint(&IDENTITY);
    for d in (0..ndir).filter(|&d| !pinned[d]) {
        for s in states.iter_mut().skip(d).step_by(ndir) {
            s.jhj = [C64::ZERO; 2];
            s.jhr = [C64::ZERO; 2];
        }
        for c in cells {
            let (p, q, cell) = (c.p as usize, c.q as usize, c.cell);
            let w: [f64; 4] = std::array::from_fn(|k| f64::from(problem.weights[4 * cell + k]));
            let mut r = jones::from_f32(&problem.data[8 * cell..8 * cell + 8]);
            let mut v_pq: Jones = [C64::ZERO; 4];
            for e in 0..ndir {
                let base = 8 * (cell * ndir + e);
                let m = jones::from_f32(&models[base..base + 8]);
                let dp = diag(&states[p * ndir + e].gain);
                let dq = diag(&states[q * ndir + e].gain);
                rop_pq[e] = jones::mul(&dq, &jones::adjoint(&m));
                rop_qp[e] = jones::mul(&dp, &m);
                let v_pqe =
                    jones::mul(&jones::mul(&adj_identity, &dp), &jones::adjoint(&rop_pq[e]));
                for k in 0..4 {
                    v_pq[k] = v_pq[k] + v_pqe[k];
                }
            }
            for k in 0..4 {
                r[k] = r[k] - v_pq[k];
            }
            let wr_pq: Jones = std::array::from_fn(|k| real_scale(r[k], w[k]));
            let wr_qp = jones::adjoint(&wr_pq);
            let sp = &mut states[p * ndir + d];
            elem_complex(&rop_pq[d], &w, &wr_pq, &mut sp.jhr, &mut sp.jhj);
            let sq = &mut states[q * ndir + d];
            elem_complex(&rop_qp[d], &w, &wr_qp, &mut sq.jhr, &mut sq.jhj);
        }
        for state in states.iter_mut().skip(d).step_by(ndir) {
            let update = update_complex(&state.jhj, &state.jhr)?;
            if state.flag == 1 {
                state.gain = [ONE, ONE];
            } else {
                for (g, u) in state.gain.iter_mut().zip(update) {
                    let u = divide(u, C64::new(2., 0.))?;
                    *g = *g + u;
                }
            }
        }
    }
    Ok(())
}

/// Non-generalised `invert` then `v1_imul_v2(b, x, x)` on the diagonal.
fn update_complex(jhj: &[C64; 2], jhr: &[C64; 2]) -> Result<[C64; 2], Error> {
    let det = jhj[0] * jhj[1] - C64::ZERO * C64::ZERO;
    if det.re < DET_LIMIT {
        return Ok([C64::ZERO; 2]);
    }
    let x0 = divide(jhj[1], det)?;
    let x3 = divide(jhj[0], det)?;
    Ok([jhr[0] * x0, jhr[1] * x3])
}

/// `compute_update`, `finalize_update` (DD: halved on every iteration,
/// nothing for a pinned direction) and `update_gain_flags` for one gain.
///
/// `phase`: conjugate gradients warm-started from the previous update, the
/// parameters updated without halving (QuartiCal's `phase`
/// `finalize_update`), numbness 1e9, then `update_param_flags`.
fn step_gain(
    state: &mut GainState,
    kind: Kind,
    pinned: bool,
    loop_idx: usize,
    stop2: f64,
) -> Result<(bool, bool), Error> {
    match kind {
        Kind::DiagComplex => {
            let update = update_complex(&state.jhj, &state.jhr)?;
            if !pinned {
                if state.flag == 1 {
                    state.gain = [ONE, ONE];
                } else {
                    for (g, u) in state.gain.iter_mut().zip(update) {
                        let u = divide(u, C64::new(2., 0.))?;
                        *g = *g + u;
                    }
                }
            }
            Ok(flag_ladder(state, loop_idx, stop2, NUMBNESS))
        }
        Kind::Phase => {
            conjugate_gradient(&state.jhj_r, &state.jhr_r, &mut state.update_r)?;
            if !pinned {
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
            let result = flag_ladder(state, loop_idx, stop2, NUMBNESS_PHASE);
            state.param_flag = state.flag == 1;
            if state.param_flag {
                state.params = [0., 0.];
            }
            Ok(result)
        }
    }
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

struct EpochRecord {
    counts: Vec<(usize, usize)>,
    error: Option<(usize, Error)>,
}

#[allow(clippy::too_many_arguments)]
fn run_interval(
    problem: &Problem,
    models: &[f32],
    ndir: usize,
    mode: Mode,
    pinned: &[bool],
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
    let mut rop_pq = vec![IDENTITY; ndir];
    let mut rop_qp = vec![IDENTITY; ndir];
    for j in 0..n {
        let loop_idx = k0 + j;
        if mode.gauss_seidel {
            // The sweep applies the updates; `step_gain` below then runs the
            // flag ladder only (as for a pinned direction).
            if let Err(error) = gauss_seidel_sweep(
                problem,
                models,
                ndir,
                pinned,
                cells,
                states,
                &mut rop_pq,
                &mut rop_qp,
            ) {
                record.error = Some((loop_idx, error));
                return record;
            }
        } else {
            accumulate(
                problem,
                models,
                ndir,
                mode,
                cells,
                states,
                &mut rop_pq,
                &mut rop_qp,
            );
        }
        let (mut converged, mut flagged) = (0usize, 0usize);
        for (g, state) in states.iter_mut().enumerate() {
            let no_update = pinned[g % ndir] || mode.gauss_seidel;
            match step_gain(state, mode.kind, no_update, loop_idx, stop2) {
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
        for state in states.iter_mut() {
            state.km1_gain = state.gain;
        }
        record.counts.push((converged, flagged));
        let row = &mut snapshots[j * states.len()..(j + 1) * states.len()];
        for (snapshot, state) in row.iter_mut().zip(states.iter()) {
            *snapshot = Snapshot {
                gain: state.gain,
                params: state.params,
                param_flag: state.param_flag,
                trend: state.trend,
                flag: state.flag,
            };
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

/// Solve one direction-dependent term (`settings.kind`: `diag_complex` or
/// `phase`) as QuartiCal 0.2.7 does, with `ndir` model directions in
/// `problem.model` (see `check`).
pub fn solve(problem: &Problem, ndir: usize, settings: &Settings) -> Result<Solution, Error> {
    check(problem, ndir, settings)?;
    let Model::Stored(models) = problem.model else {
        unreachable!("checked")
    };
    let width = problem.nant * ndir;
    let ngains = problem.ntime_bins * problem.nfreq_bins * width;
    let nintervals = problem.ntime_bins * problem.nfreq_bins;
    let mut pinned = vec![false; ndir];
    for &d in &settings.pinned_directions {
        pinned[d] = true;
    }
    let mut states = vec![FRESH; ngains];
    let cells = if width == 0 {
        Vec::new()
    } else {
        interval_cells(
            problem,
            ndir,
            &crate::solve::data_flags(problem),
            &mut states,
        )
    };
    let stop2 = settings.stop_criterion * settings.stop_criterion;
    let iterations = settings.max_iterations.max(1);
    let mut snapshots = vec![EMPTY_SNAPSHOT; EPOCH * ngains];
    let mut k0 = 0;
    let chunk = width.max(1);
    let mode = Mode {
        kind: settings.kind,
        last_direction_gain: settings.phase_last_direction_gain,
        gauss_seidel: settings.direction_update == DirectionUpdate::GaussSeidel,
    };
    let (j, fraction) = loop {
        let n = EPOCH.min(iterations - k0);
        let records: Vec<EpochRecord> = states
            .par_chunks_mut(chunk)
            .zip(snapshots.par_chunks_mut(EPOCH * chunk))
            .enumerate()
            .map(|(interval, (states, snaps))| {
                run_interval(
                    problem,
                    models,
                    ndir,
                    mode,
                    &pinned,
                    &cells[interval],
                    stop2,
                    states,
                    snaps,
                    k0,
                    n,
                )
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
            fraction = converged_fraction(c, x, ngains);
            if fraction >= settings.stop_fraction {
                stop = Some(jj);
                break;
            }
        }
        if let Some(jj) = stop {
            break (jj, fraction);
        }
        if let Some((_, interval)) = first_error {
            let mut records = records;
            let (_, error) = records[interval].error.take().expect("recorded");
            return Err(error);
        }
        if k0 + n == iterations {
            break (n - 1, fraction);
        }
        k0 += n;
    };
    let mut finals: Vec<Snapshot> = Vec::with_capacity(ngains);
    for snaps in snapshots.chunks(EPOCH * chunk).take(nintervals) {
        finals.extend_from_slice(&snaps[j * chunk..(j + 1) * chunk]);
    }
    // finalize_gain_flags on the stopping iteration's snapshots.
    for s in finals.iter_mut() {
        if s.trend > TREND_LIMIT {
            s.flag = 1;
            s.gain = [ONE, ONE];
        } else if s.flag == -1 {
            s.flag = 0;
        }
    }
    if let Some(r) = settings.reference_antenna
        && width > 0
    {
        for interval in finals.chunks_mut(width) {
            match settings.kind {
                Kind::DiagComplex => reference_gains(interval, ndir, r),
                Kind::Phase => reference_params(interval, ndir, r),
            }
        }
    } else if settings.kind == Kind::Phase {
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

/// `reference_gains` of `diag_complex` for one interval: every gain of
/// direction d times `conj(g_r,d)/|g_r,d|` per hand unless the reference
/// gain is flagged; flagged gains become the identity.
fn reference_gains(interval: &mut [Snapshot], ndir: usize, r: usize) {
    for d in 0..ndir {
        let mut rg = interval[r * ndir + d].gain;
        if interval[r * ndir + d].flag == 0 {
            for v in rg.iter_mut() {
                let a = v.re.hypot(v.im);
                *v = C64::new(v.re / a, -v.im / a);
            }
        }
        for s in interval.iter_mut().skip(d).step_by(ndir) {
            let g = jones::mul(&diag(&s.gain), &diag(&rg));
            s.gain = [g[0], g[3]];
            if s.flag != 0 {
                s.gain = [ONE, ONE];
            }
        }
    }
}

/// `reference_params` of `phase` for one interval, per direction: the
/// parameters minus the reference antenna's of the same direction (where not
/// flagged), the gains rebuilt, then the flags applied (as
/// `diag::reference_params`).
fn reference_params(interval: &mut [Snapshot], ndir: usize, r: usize) {
    for d in 0..ndir {
        let rp = interval[r * ndir + d].params;
        for s in interval.iter_mut().skip(d).step_by(ndir) {
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
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cal::diag;

    struct Sim {
        nrow: usize,
        nchan: usize,
        nant: usize,
        ntime: usize,
        data: Vec<f32>,
        weights: Vec<f32>,
        models: Vec<f32>,
        flag: Vec<u8>,
        flag_row: Vec<u8>,
        a1: Vec<u32>,
        a2: Vec<u32>,
        time_bin: Vec<u32>,
        freq_bin: Vec<u32>,
        truth: Vec<[C64; 2]>,
    }

    /// A noiseless problem with `ndir` directions: per direction a model of
    /// varying phase per cell, truth gains per (antenna, direction).
    fn sim(ndir: usize) -> Sim {
        let (nant, nchan, ntime) = (10usize, 4usize, 2usize);
        let mut a1 = Vec::new();
        let mut a2 = Vec::new();
        let mut time_bin = Vec::new();
        for t in 0..ntime {
            for p in 0..nant {
                for q in p + 1..nant {
                    a1.push(p as u32);
                    a2.push(q as u32);
                    time_bin.push(t as u32);
                }
            }
        }
        let nrow = a1.len();
        let truth: Vec<[C64; 2]> = (0..nant * ndir)
            .map(|i| {
                let x = i as f64;
                [
                    C64::new(
                        (1. + 0.05 * (x * 0.7).sin()) * (0.6 * (x * 0.9).sin()).cos(),
                        (1. + 0.05 * (x * 0.7).sin()) * (0.6 * (x * 0.9).sin()).sin(),
                    ),
                    C64::new(
                        (1. - 0.04 * (x * 1.3).cos()) * (0.5 * (x * 1.7).cos()).cos(),
                        (1. - 0.04 * (x * 1.3).cos()) * (0.5 * (x * 1.7).cos()).sin(),
                    ),
                ]
            })
            .collect();
        let mut models = vec![0f32; nrow * nchan * ndir * 8];
        let mut data = vec![0f32; nrow * nchan * 8];
        for row in 0..nrow {
            let (p, q) = (a1[row] as usize, a2[row] as usize);
            for c in 0..nchan {
                let cell = row * nchan + c;
                for d in 0..ndir {
                    let phase =
                        0.37 * (row as f64) * (d as f64 + 1.) + 0.9 * c as f64 * (d as f64 + 1.);
                    let flux = 1.0 / (d as f64 + 1.);
                    let m = C64::new(flux * phase.cos(), flux * phase.sin());
                    let mj: Jones = [m, C64::ZERO, C64::ZERO, m];
                    let base = 8 * (cell * ndir + d);
                    for k in 0..4 {
                        models[base + 2 * k] = mj[k].re as f32;
                        models[base + 2 * k + 1] = mj[k].im as f32;
                    }
                    // Corrupt with the f32-rounded model, as the solver reads it.
                    let mr = jones::from_f32(&models[base..base + 8]);
                    let gp = diag(&truth[p * ndir + d]);
                    let gq = diag(&truth[q * ndir + d]);
                    let v = jones::mul(&jones::mul(&gp, &mr), &jones::adjoint(&gq));
                    for k in 0..4 {
                        data[8 * cell + 2 * k] += v[k].re as f32;
                        data[8 * cell + 2 * k + 1] += v[k].im as f32;
                    }
                }
            }
        }
        Sim {
            nrow,
            nchan,
            nant,
            ntime,
            data,
            weights: vec![1.; nrow * nchan * 4],
            models,
            flag: vec![0; nrow * nchan * 4],
            flag_row: vec![0; nrow],
            a1,
            a2,
            time_bin,
            freq_bin: vec![0; nchan],
            truth,
        }
    }

    fn problem<'a>(s: &'a Sim, models: &'a [f32]) -> Problem<'a> {
        Problem {
            nrow: s.nrow,
            nchan: s.nchan,
            ntime_bins: s.ntime,
            nfreq_bins: 1,
            nant: s.nant,
            data: &s.data,
            weights: &s.weights,
            model: Model::Stored(models),
            flag: &s.flag,
            flag_row: &s.flag_row,
            antenna1: &s.a1,
            antenna2: &s.a2,
            time_bin: &s.time_bin,
            freq_bin: &s.freq_bin,
        }
    }

    #[test]
    fn recovers_noiseless_dd_gains_up_to_gauge() {
        let ndir = 3;
        let s = sim(ndir);
        let settings = Settings {
            max_iterations: 300,
            stop_criterion: 1e-10,
            stop_fraction: 1.0,
            reference_antenna: None,
            pinned_directions: Vec::new(),
            ..Settings::default()
        };
        let sol = solve(&problem(&s, &s.models), ndir, &settings).unwrap();
        assert!(sol.flags.iter().all(|&f| f == 0));
        let width = s.nant * ndir;
        let mut worst: f64 = 0.;
        for t in 0..s.ntime {
            for d in 0..ndir {
                for p in 0..s.nant {
                    for q in p + 1..s.nant {
                        for h in 0..2 {
                            let g = |a: usize| sol.gains[t * width + a * ndir + d][h];
                            let tr = |a: usize| s.truth[a * ndir + d][h];
                            let solved = g(p) * g(q).conj();
                            let truth = tr(p) * tr(q).conj();
                            worst =
                                worst.max((solved - truth).norm2().sqrt() / truth.norm2().sqrt());
                        }
                    }
                }
            }
        }
        assert!(worst < 1e-6, "worst relative product error {worst}");
    }

    #[test]
    fn one_direction_halves_every_step_unlike_di() {
        // With one direction and no pinning the DD term differs from the DI
        // `diag_complex` only by halving on odd iterations too; after one
        // iteration (an even one, halved in both) they agree exactly.
        let s = sim(1);
        let dd = Settings {
            max_iterations: 1,
            reference_antenna: Some(0),
            ..Settings::default()
        };
        let mut di = diag::Settings::new(diag::Kind::DiagComplex);
        di.max_iterations = 1;
        let p = problem(&s, &s.models);
        let a = solve(&p, 1, &dd).unwrap();
        let b = diag::solve(&p, &di).unwrap();
        assert_eq!(a.flags, b.flags);
        for (x, y) in a.gains.iter().zip(&b.gains) {
            assert_eq!(x, y);
        }
    }

    #[test]
    fn pinned_direction_stays_identity_and_shapes_checked() {
        let ndir = 2;
        let s = sim(ndir);
        let settings = Settings {
            reference_antenna: None,
            pinned_directions: vec![0],
            max_iterations: 10,
            ..Settings::default()
        };
        let sol = solve(&problem(&s, &s.models), ndir, &settings).unwrap();
        for (g, gain) in sol.gains.iter().enumerate() {
            if g % ndir == 0 {
                assert_eq!(*gain, [ONE, ONE]);
            }
        }
        let short = &s.models[..s.models.len() - 8];
        assert!(matches!(
            solve(&problem(&s, short), ndir, &settings),
            Err(Error::Shape(_))
        ));
        let bad = Settings {
            pinned_directions: vec![2],
            ..settings
        };
        assert!(matches!(
            solve(&problem(&s, &s.models), ndir, &bad),
            Err(Error::Settings(_))
        ));
    }

    #[test]
    fn phase_one_direction_equals_di_phase_kernel() {
        // With one direction the DD phase kernel is QuartiCal's DI `phase`
        // (no halving in either), so it equals `diag`'s Phase solve.
        let s = sim(1);
        let p = problem(&s, &s.models);
        let dd = Settings {
            kind: Kind::Phase,
            ..Settings::default()
        };
        let mut di = diag::Settings::new(diag::Kind::Phase);
        di.max_iterations = dd.max_iterations;
        let a = solve(&p, 1, &dd).unwrap();
        let b = diag::solve(&p, &di).unwrap();
        assert_eq!(a.flags, b.flags);
        assert_eq!(a.iterations, b.iterations);
        for (x, y) in a.gains.iter().zip(&b.gains) {
            assert_eq!(x, y);
        }
    }

    fn gauss_seidel() -> Settings {
        Settings {
            direction_update: DirectionUpdate::GaussSeidel,
            ..Settings::default()
        }
    }

    #[test]
    fn gauss_seidel_one_direction_equals_jacobi_exactly() {
        // With one direction the sweep forms the same residual, normal
        // equations and halved update as the Jacobi path.
        let s = sim(1);
        let p = problem(&s, &s.models);
        for (refant, iterations) in [(Some(0), 1), (None, 7), (Some(3), 60)] {
            let jacobi = Settings {
                max_iterations: iterations,
                reference_antenna: refant,
                ..Settings::default()
            };
            let gs = Settings {
                max_iterations: iterations,
                reference_antenna: refant,
                ..gauss_seidel()
            };
            let a = solve(&p, 1, &jacobi).unwrap();
            let b = solve(&p, 1, &gs).unwrap();
            assert_eq!(a.flags, b.flags);
            assert_eq!(a.iterations, b.iterations);
            assert_eq!(a.converged_fraction, b.converged_fraction);
            assert_eq!(a.gains, b.gains);
        }
    }

    #[test]
    fn gauss_seidel_reaches_the_jacobi_fixed_point() {
        // Both updates are stationary exactly where every free direction's
        // J^H r vanishes; on a noiseless problem without flags both reach
        // the truth (up to the per-direction phase gauge), and so each other.
        let ndir = 3;
        let s = sim(ndir);
        let tight = |update| Settings {
            max_iterations: 400,
            stop_criterion: 1e-12,
            stop_fraction: 1.0,
            reference_antenna: Some(0),
            direction_update: update,
            ..Settings::default()
        };
        let p = problem(&s, &s.models);
        let a = solve(&p, ndir, &tight(DirectionUpdate::Jacobi)).unwrap();
        let b = solve(&p, ndir, &tight(DirectionUpdate::GaussSeidel)).unwrap();
        assert!(a.flags.iter().chain(&b.flags).all(|&f| f == 0));
        let worst = a
            .gains
            .iter()
            .zip(&b.gains)
            .flat_map(|(x, y)| (0..2).map(move |h| (x[h] - y[h]).norm2().sqrt()))
            .fold(0., f64::max);
        assert!(worst < 1e-9, "Jacobi and Gauss-Seidel differ by {worst}");
    }

    #[test]
    fn gauss_seidel_pins_and_rejects_phase() {
        let ndir = 2;
        let s = sim(ndir);
        let p = problem(&s, &s.models);
        let pinned = Settings {
            reference_antenna: None,
            pinned_directions: vec![0],
            max_iterations: 10,
            ..gauss_seidel()
        };
        let sol = solve(&p, ndir, &pinned).unwrap();
        for (g, gain) in sol.gains.iter().enumerate() {
            if g % ndir == 0 {
                assert_eq!(*gain, [ONE, ONE]);
            }
        }
        let phase = Settings {
            kind: Kind::Phase,
            ..gauss_seidel()
        };
        assert!(matches!(solve(&p, ndir, &phase), Err(Error::Settings(_))));
    }

    #[test]
    fn phase_dd_gains_are_unit_modulus_and_referenced() {
        let ndir = 3;
        let s = sim(ndir);
        let settings = Settings {
            kind: Kind::Phase,
            phase_last_direction_gain: false,
            max_iterations: 100,
            ..Settings::default()
        };
        let sol = solve(&problem(&s, &s.models), ndir, &settings).unwrap();
        let width = s.nant * ndir;
        for (g, gain) in sol.gains.iter().enumerate() {
            for h in gain {
                assert!((h.norm2() - 1.).abs() < 1e-12);
            }
            if (g % width) / ndir == 0 {
                assert!(gain.iter().all(|h| h.im.abs() < 1e-12));
            }
        }
    }
}
