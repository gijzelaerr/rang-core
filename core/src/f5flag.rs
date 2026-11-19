// SPDX-License-Identifier: MIT
//! The F5 flagger (task F5, issue #40, `research/f5-flagger.md`, section 2):
//! F3's fifteen per-cell planes, F4's eight spectral planes per (baseline,
//! channel), and ten block planes from two order-independent median-polish
//! factorisations per antenna (log amplitude per 2-dump × 8-channel block,
//! section 2c; noise variance per time block × 32 channels, section 2d), fed
//! to a network whose first operation is a 1×1 linear stem. At inference the
//! stem is evaluated at each input's own resolution and summed per cell
//! (section 2b), then F3's five dilated 3×3 layers and head run on 8
//! channels.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
//! see `LICENSES/MIT.txt`.
//!
//! The features follow `rang.f5flag.features_numpy` (NumPy, float64) and the
//! network `rang.f5net` (PyTorch); `tests/test_f5_flag.py` checks parity.
//! Plane order of the materialised features (level 0, 33 inputs): F3's 14
//! (time and channel residuals, antenna and array medians), F4's 8 spectral,
//! 2c's 6, 2d's 4, the mask. Level 1 drops 2d (29), level 2 also F4's 8 (21).

pub use crate::f3flag::Inputs;
use crate::f3flag::{
    self, DILATIONS, HIDDEN, MIN_AGG, check, median, medians_of_u, pair64, residuals,
    rows_by_baseline, u_planes,
};
use crate::f4flag::{self, Spectra};
use rayon::prelude::*;

/// F3's planes without the mask.
pub const CELL_PLANES: usize = 14;
pub const SPEC_PLANES: usize = 8;
pub const AMP_PLANES: usize = 6;
pub const VAR_PLANES: usize = 4;
const AMP_DF: usize = 8;
const VAR_DF: usize = 32;
const POLISH_ITERS: usize = 5;
const MIN_VAR: usize = 64;
const HUBER_K: f64 = 1.345;
const MAD_SCALE: f64 = 1.4826;
const FAMILIES: [[usize; 2]; 2] = [[0, 3], [1, 2]];

/// Inputs of a ladder level (section 2e): 0 all 33, 1 without 2d, 2 also
/// without F4's spectral planes.
pub fn inputs(level: usize) -> Option<usize> {
    match level {
        0 => Some(33),
        1 => Some(29),
        2 => Some(21),
        _ => None,
    }
}

fn has_spec(level: usize) -> bool {
    level <= 1
}

fn has_var(level: usize) -> bool {
    level == 0
}

/// Weights of N5 at a level: stem (n, 8) and b, five 3×3 layers 8 → 8, head.
pub fn weight_count(level: usize) -> usize {
    let n = inputs(level).unwrap_or(0);
    n * HIDDEN + HIDDEN + DILATIONS.len() * (9 * HIDDEN * HIDDEN + HIDDEN) + HIDDEN + 1
}

/// `asinh` in f32 (section 2b rule 3): 0 for non-finite input.
pub(crate) fn ash32(x: f64) -> f32 {
    if !x.is_finite() {
        return 0.0;
    }
    let x = x as f32;
    let a = x.abs();
    let r = if a > 1e18 {
        a.ln() + std::f32::consts::LN_2
    } else {
        (a + a * a / ((a * a + 1.0).sqrt() + 1.0)).ln_1p()
    };
    r.copysign(x)
}

/// Block geometry of one scan.
#[derive(Clone)]
pub(crate) struct Grid {
    pub(crate) nt: usize,
    pub(crate) nc: usize,
    /// 2c: blocks of 2 dumps (the last takes 3 when nt is odd).
    pub(crate) ta: Vec<usize>,
    pub(crate) nta: usize,
    pub(crate) nja: usize,
    /// 2d: `max(1, round(nt / 10))` equal blocks (round half up).
    pub(crate) tv: Vec<usize>,
    pub(crate) ntv: usize,
    pub(crate) njv: usize,
}

impl Grid {
    pub(crate) fn new(nt: usize, nc: usize) -> Grid {
        let nta = (nt / 2).max(1);
        let ta = (0..nt).map(|t| (t / 2).min(nta - 1)).collect();
        let k = nt.saturating_add(5) / 10;
        let k = k.max(1);
        let len = nt.div_ceil(k).max(1);
        let ntv = nt.div_ceil(len).max(1);
        let tv = (0..nt).map(|t| t / len).collect();
        Grid {
            nt,
            nc,
            ta,
            nta,
            nja: nc.div_ceil(AMP_DF),
            tv,
            ntv,
            njv: nc.div_ceil(VAR_DF),
        }
    }
    fn amp_cells(&self) -> usize {
        self.nta * self.nja * 4
    }
    fn var_cells(&self) -> usize {
        self.ntv * self.njv
    }
}

/// One baseline's block statistics: log median amplitude `[τ][j][c]` (2c)
/// and log noise variance from time and channel differences `[T][J]` (2d);
/// NaN where undefined.
pub(crate) struct Blocks {
    pub(crate) amp: Vec<f64>,
    pub(crate) vt: Vec<f64>,
    pub(crate) vf: Vec<f64>,
}

fn mad_sigma2(buf: &mut Vec<f64>) -> f64 {
    if buf.len() < MIN_VAR {
        return f64::NAN;
    }
    let m = median(buf);
    for x in buf.iter_mut() {
        *x = (*x - m).abs();
    }
    let s = MAD_SCALE * median(buf) / std::f64::consts::SQRT_2;
    if s.is_finite() && s > 0.0 {
        (s * s).ln()
    } else {
        f64::NAN
    }
}

pub(crate) fn blocks(inp: &Inputs, rows: &[usize], g: &Grid, with_var: bool) -> Blocks {
    let (nt, nc) = (g.nt, g.nc);
    let ncell = nt * nc;
    let mut v = vec![[0f32; 8]; ncell];
    let mut flagged = vec![true; ncell];
    for &r in rows {
        let t = inp.time[r] as usize;
        for f in 0..nc {
            let cell = t * nc + f;
            let k = (r * nc + f) * 8;
            let x = &inp.data[k..k + 8];
            flagged[cell] = inp.flags[r * nc + f] != 0 || !x.iter().all(|z| z.is_finite());
            v[cell].copy_from_slice(x);
        }
    }
    let mut amp = vec![f64::NAN; g.amp_cells()];
    let mut buf = Vec::with_capacity(4 * AMP_DF * 4);
    for ta in 0..g.nta {
        let t0 = ta * 2;
        let t1 = if ta + 1 == g.nta { nt } else { t0 + 2 };
        for j in 0..g.nja {
            let f0 = j * AMP_DF;
            let f1 = (f0 + AMP_DF).min(nc);
            let total = (t1 - t0) * (f1 - f0);
            for c in 0..4 {
                buf.clear();
                for t in t0..t1 {
                    for f in f0..f1 {
                        let i = t * nc + f;
                        if !flagged[i] {
                            let z = &v[i];
                            buf.push((z[2 * c] as f64).hypot(z[2 * c + 1] as f64));
                        }
                    }
                }
                if 2 * buf.len() >= total && !buf.is_empty() {
                    let m = median(&mut buf);
                    if m > 0.0 {
                        amp[(ta * g.nja + j) * 4 + c] = m.ln();
                    }
                }
            }
        }
    }
    let mut vt = vec![f64::NAN; g.var_cells()];
    let mut vf = vec![f64::NAN; g.var_cells()];
    if with_var {
        let mut bt = Vec::new();
        let mut bf = Vec::new();
        for tb in 0..g.ntv {
            let ts: Vec<usize> = (0..nt).filter(|&t| g.tv[t] == tb).collect();
            for jb in 0..g.njv {
                let f0 = jb * VAR_DF;
                let f1 = (f0 + VAR_DF).min(nc);
                bt.clear();
                bf.clear();
                for &t in &ts {
                    for f in f0..f1 {
                        let i = t * nc + f;
                        if flagged[i] {
                            continue;
                        }
                        if t + 1 < nt && g.tv[t + 1] == tb && !flagged[i + nc] {
                            bt.extend(
                                v[i + nc]
                                    .iter()
                                    .zip(&v[i])
                                    .map(|(a, b)| *a as f64 - *b as f64),
                            );
                        }
                        if f + 1 < f1 && !flagged[i + 1] {
                            bf.extend(
                                v[i + 1]
                                    .iter()
                                    .zip(&v[i])
                                    .map(|(a, b)| *a as f64 - *b as f64),
                            );
                        }
                    }
                }
                vt[tb * g.njv + jb] = mad_sigma2(&mut bt);
                vf[tb * g.njv + jb] = mad_sigma2(&mut bf);
            }
        }
    }
    Blocks { amp, vt, vf }
}

/// Baselines of each antenna with the other antenna.
pub(crate) fn of_antenna(inp: &Inputs) -> Vec<Vec<(usize, usize)>> {
    let mut of = vec![Vec::new(); inp.nant];
    for b in 0..inp.nbl {
        let (p, q) = (inp.ant1[b] as usize, inp.ant2[b] as usize);
        if p == q {
            continue;
        }
        of[p].push((b, q));
        of[q].push((b, p));
    }
    of
}

fn med_min(buf: &mut Vec<f64>, min: usize) -> f64 {
    buf.retain(|x| x.is_finite());
    if buf.len() >= min {
        median(buf)
    } else {
        f64::NAN
    }
}

/// Median polish `y_b ≈ γ_p + γ_q + s` with simultaneous updates (section
/// 2c step 2); returns γ (per antenna) and s. Order-independent; its fixed
/// point carries a small per-antenna bias (Amendment 1).
pub(crate) fn polish(y: &[f64], inp: &Inputs, of: &[Vec<(usize, usize)>]) -> (Vec<f64>, f64) {
    let nant = inp.nant;
    let mut buf = Vec::with_capacity(y.len());
    buf.extend_from_slice(y);
    let mut s = med_min(&mut buf, MIN_AGG);
    let mut g = vec![0f64; nant];
    if !s.is_finite() {
        return (vec![f64::NAN; nant], f64::NAN);
    }
    for _ in 0..POLISH_ITERS {
        let mut g2 = vec![f64::NAN; nant];
        for (p, gp) in g2.iter_mut().enumerate() {
            buf.clear();
            buf.extend(of[p].iter().map(|&(b, q)| y[b] - s - g[q]));
            *gp = med_min(&mut buf, MIN_AGG);
        }
        buf.clear();
        buf.extend_from_slice(&g2);
        let c = med_min(&mut buf, 1);
        if c.is_finite() {
            for x in g2.iter_mut() {
                *x -= c;
            }
        }
        buf.clear();
        buf.extend(
            (0..inp.nbl).map(|b| y[b] - g2[inp.ant1[b] as usize] - g2[inp.ant2[b] as usize]),
        );
        s = med_min(&mut buf, MIN_AGG);
        g = g2;
        if !s.is_finite() {
            break;
        }
    }
    (g, s)
}

/// Robust Chebyshev fit of degree `d` over the blocks (Huber, three IRLS
/// passes after the least-squares start); NaN if fewer than 2(d+1) values.
pub(crate) fn robust_fit(v: &[f64], d: usize) -> Vec<f64> {
    let n = v.len();
    let m = d + 1;
    let fin: Vec<usize> = (0..n).filter(|&j| v[j].is_finite()).collect();
    if fin.len() < 2 * m {
        return vec![f64::NAN; n];
    }
    let basis = |j: usize| -> Vec<f64> {
        let x = 2.0 * (j as f64 + 0.5) / n as f64 - 1.0;
        let mut t = vec![1.0, x];
        while t.len() < m {
            let k = t.len();
            t.push(2.0 * x * t[k - 1] - t[k - 2]);
        }
        t.truncate(m);
        t
    };
    let rows: Vec<Vec<f64>> = (0..n).map(basis).collect();
    let mut w = vec![1.0; n];
    let mut fit = vec![f64::NAN; n];
    for pass in 0..4 {
        let mut a = vec![0.0; m * m];
        let mut rhs = vec![0.0; m];
        for &j in &fin {
            for r in 0..m {
                rhs[r] += w[j] * rows[j][r] * v[j];
                for c in 0..m {
                    a[r * m + c] += w[j] * rows[j][r] * rows[j][c];
                }
            }
        }
        let Some(coef) = solve(&mut a, &mut rhs, m) else {
            return vec![f64::NAN; n];
        };
        for j in 0..n {
            fit[j] = (0..m).map(|r| coef[r] * rows[j][r]).sum();
        }
        if pass == 3 {
            break;
        }
        let mut e: Vec<f64> = fin.iter().map(|&j| v[j] - fit[j]).collect();
        let me = median(&mut e.clone());
        for x in e.iter_mut() {
            *x = (*x - me).abs();
        }
        let scale = MAD_SCALE * median(&mut e);
        if !(scale.is_finite() && scale > 0.0) {
            break;
        }
        for &j in &fin {
            let r = (v[j] - fit[j]).abs();
            w[j] = if r <= HUBER_K * scale {
                1.0
            } else {
                HUBER_K * scale / r
            };
        }
    }
    fit
}

fn solve(a: &mut [f64], b: &mut [f64], m: usize) -> Option<Vec<f64>> {
    for k in 0..m {
        let piv =
            (k..m).max_by(|&i, &j| a[i * m + k].abs().partial_cmp(&a[j * m + k].abs()).unwrap())?;
        if a[piv * m + k].abs() < 1e-300 {
            return None;
        }
        if piv != k {
            for c in 0..m {
                a.swap(k * m + c, piv * m + c);
            }
            b.swap(k, piv);
        }
        for i in k + 1..m {
            let f = a[i * m + k] / a[k * m + k];
            for c in k..m {
                a[i * m + c] -= f * a[k * m + c];
            }
            b[i] -= f * b[k];
        }
    }
    let mut x = vec![0.0; m];
    for k in (0..m).rev() {
        let s: f64 = (k + 1..m).map(|c| a[k * m + c] * x[c]).sum();
        x[k] = (b[k] - s) / a[k * m + k];
    }
    Some(x)
}

fn mad_scale(v: &mut Vec<f64>) -> f64 {
    v.retain(|x| x.is_finite());
    if v.is_empty() {
        return f64::NAN;
    }
    let m = median(v);
    for x in v.iter_mut() {
        *x = (*x - m).abs();
    }
    MAD_SCALE * median(v)
}

/// Per-antenna anomalies on a block grid: `γ` polished per grid cell
/// (`[cell][b]` input), fitted over channel blocks per (antenna, row of the
/// grid), scaled per row. `ncol` channel blocks per row; returns `[cell][p]`
/// z and, if asked, the dispersion Q.
fn factorise(
    y: &[Vec<f64>],
    nrow: usize,
    ncol: usize,
    inp: &Inputs,
    of: &[Vec<(usize, usize)>],
    d: usize,
    want_q: bool,
) -> (Vec<f64>, Vec<f64>) {
    let nant = inp.nant;
    let ncell = nrow * ncol;
    let solved: Vec<(Vec<f64>, Vec<f64>)> = (0..ncell)
        .into_par_iter()
        .map(|cell| {
            let yy = &y[cell];
            let (g, s) = polish(yy, inp, of);
            let mut q = Vec::new();
            if want_q {
                let r: Vec<f64> = (0..inp.nbl)
                    .map(|b| yy[b] - g[inp.ant1[b] as usize] - g[inp.ant2[b] as usize] - s)
                    .collect();
                let mut buf = Vec::new();
                q = (0..nant)
                    .map(|p| {
                        buf.clear();
                        buf.extend(of[p].iter().map(|&(b, _)| r[b]));
                        buf.retain(|x| x.is_finite());
                        if buf.len() >= MIN_AGG {
                            mad_scale(&mut buf)
                        } else {
                            f64::NAN
                        }
                    })
                    .collect();
                let mut all = q.clone();
                let mq = med_min(&mut all, 1);
                for x in q.iter_mut() {
                    *x /= mq;
                }
            }
            (g, q)
        })
        .collect();
    // Fit per (row, antenna) over the row's columns.
    let anomaly: Vec<Vec<f64>> = (0..nrow * nant)
        .into_par_iter()
        .map(|rp| {
            let (row, p) = (rp / nant, rp % nant);
            let v: Vec<f64> = (0..ncol).map(|j| solved[row * ncol + j].0[p]).collect();
            let fit = robust_fit(&v, d);
            (0..ncol).map(|j| v[j] - fit[j]).collect()
        })
        .collect();
    let mut z = vec![f64::NAN; ncell * nant];
    for row in 0..nrow {
        let mut buf: Vec<f64> = (0..nant)
            .flat_map(|p| anomaly[row * nant + p].iter().copied())
            .collect();
        let sig = mad_scale(&mut buf);
        if !(sig.is_finite() && sig > 0.0) {
            continue;
        }
        for p in 0..nant {
            for j in 0..ncol {
                z[(row * ncol + j) * nant + p] = anomaly[row * nant + p][j] / sig;
            }
        }
    }
    let mut q = Vec::new();
    if want_q {
        q = vec![f64::NAN; ncell * nant];
        for (cell, (_, qc)) in solved.iter().enumerate() {
            q[cell * nant..(cell + 1) * nant].copy_from_slice(qc);
        }
    }
    (z, q)
}

/// The per-antenna block quantities of one scan.
pub(crate) struct Antenna {
    pub(crate) grid: Grid,
    /// 2c, `[τ][j][φ][p]`: z of larger magnitude in the family, and max Q.
    pub(crate) z: Vec<f64>,
    pub(crate) q: Vec<f64>,
    /// 2d, `[T][J][p]`: time- and channel-difference anomalies.
    pub(crate) tt: Vec<f64>,
    pub(crate) tf: Vec<f64>,
}

fn transpose(per: &[Vec<f64>], ncell: usize) -> Vec<Vec<f64>> {
    (0..ncell)
        .map(|c| per.iter().map(|v| v[c]).collect())
        .collect()
}

pub(crate) fn antenna(inp: &Inputs, blk: &[Blocks], g: Grid, d: usize, with_var: bool) -> Antenna {
    let nant = inp.nant;
    let of = of_antenna(inp);
    // 2c per correlation: grid rows τ, columns j; one factorisation per c.
    let na = g.nta * g.nja;
    let mut zc = Vec::with_capacity(4);
    let mut qc = Vec::with_capacity(4);
    for c in 0..4 {
        let per: Vec<Vec<f64>> = blk
            .iter()
            .map(|b| (0..na).map(|k| b.amp[k * 4 + c]).collect())
            .collect();
        let y = transpose(&per, na);
        let (z, q) = factorise(&y, g.nta, g.nja, inp, &of, d, true);
        zc.push(z);
        qc.push(q);
    }
    let mut z = vec![f64::NAN; na * 2 * nant];
    let mut q = vec![f64::NAN; na * 2 * nant];
    for k in 0..na {
        for (phi, fam) in FAMILIES.iter().enumerate() {
            for p in 0..nant {
                let (a, b) = (zc[fam[0]][k * nant + p], zc[fam[1]][k * nant + p]);
                let o = (k * 2 + phi) * nant + p;
                z[o] = match (a.is_finite(), b.is_finite()) {
                    (true, true) => {
                        if b.abs() > a.abs() {
                            b
                        } else {
                            a
                        }
                    }
                    (true, false) => a,
                    (false, true) => b,
                    _ => f64::NAN,
                };
                q[o] = f3flag::max_finite(&[qc[fam[0]][k * nant + p], qc[fam[1]][k * nant + p]]);
            }
        }
    }
    let nv = g.var_cells();
    let (mut tt, mut tf) = (vec![f64::NAN; nv * nant], vec![f64::NAN; nv * nant]);
    if with_var {
        let per_t: Vec<Vec<f64>> = blk.iter().map(|b| b.vt.clone()).collect();
        let per_f: Vec<Vec<f64>> = blk.iter().map(|b| b.vf.clone()).collect();
        tt = factorise(&transpose(&per_t, nv), g.ntv, g.njv, inp, &of, d, false).0;
        tf = factorise(&transpose(&per_f, nv), g.ntv, g.njv, inp, &of, d, false).0;
    }
    Antenna {
        grid: g,
        z,
        q,
        tt,
        tf,
    }
}

/// Everything shared by all baselines of a scan.
pub(crate) struct Prepared {
    pub(crate) agg: Vec<f32>,
    pub(crate) spec: Option<Spectra>,
    pub(crate) ant: Antenna,
    pub(crate) level: usize,
}

pub(crate) fn prepare(
    inp: &Inputs,
    start: &[usize],
    order: &[usize],
    level: usize,
    d: usize,
) -> Prepared {
    let ncell = inp.ntime * inp.nchan;
    let g = Grid::new(inp.ntime, inp.nchan);
    let with_var = has_var(level);
    let per: Vec<(Vec<f32>, Vec<f64>, bool, Blocks)> = (0..inp.nbl)
        .into_par_iter()
        .map(|b| {
            let rows = &order[start[b]..start[b + 1]];
            let res = residuals(inp, rows);
            let u = u_planes(&res, ncell);
            (u, res.p, res.alive, blocks(inp, rows, &g, with_var))
        })
        .collect();
    let mut u = Vec::with_capacity(inp.nbl);
    let mut p = Vec::with_capacity(inp.nbl);
    let mut alive = Vec::with_capacity(inp.nbl);
    let mut blk = Vec::with_capacity(inp.nbl);
    for (ub, pb, ab, bb) in per {
        u.push(ub);
        p.push(pb);
        alive.push(ab);
        blk.push(bb);
    }
    let agg = medians_of_u(inp, &u);
    drop(u);
    let spec = if has_spec(level) {
        Some(f4flag::spectra(inp, &p, alive))
    } else {
        None
    };
    let ant = antenna(inp, &blk, g, d, with_var);
    Prepared {
        agg,
        spec,
        ant,
        level,
    }
}

/// One baseline's planes by resolution: per cell F3's 14 and the mask
/// (`(cell, 15)`), per channel F4's 8 (`(f, 8)`, empty without them), per
/// 2c block 6 (`(τ, j, 6)`), per 2d block 4 (`(T, J, 4)`, empty without
/// them), and whether the baseline is alive.
pub(crate) struct Split {
    pub(crate) cell: Vec<f32>,
    pub(crate) spec: Vec<f32>,
    pub(crate) amp: Vec<f32>,
    pub(crate) var: Vec<f32>,
    pub(crate) alive: bool,
}

pub(crate) fn split(inp: &Inputs, b: usize, rows: &[usize], pr: &Prepared) -> Split {
    let nt = inp.ntime;
    let nc = inp.nchan;
    let ncell = nt * nc;
    let nant = inp.nant;
    let res = residuals(inp, rows);
    let alive = res.alive;
    let mut cell = vec![0f32; ncell * 15];
    let (p, q) = (inp.ant1[b] as usize, inp.ant2[b] as usize);
    let agg = &pr.agg;
    for c in 0..ncell {
        let o = c * 15;
        if res.flagged[c] {
            cell[o + 14] = 1.0;
            continue;
        }
        if !alive {
            continue;
        }
        for k in 0..4 {
            cell[o + k] = ash32(res.rt[c * 4 + k]);
            cell[o + 4 + k] = ash32(res.rf[c * 4 + k]);
        }
        for x in 0..2 {
            let base = x * (nant + 1);
            let (mx, mn) = pair64(
                agg[(base + p) * ncell + c] as f64,
                agg[(base + q) * ncell + c] as f64,
            );
            cell[o + 8 + 3 * x] = ash32(mx);
            cell[o + 9 + 3 * x] = ash32(mn);
            cell[o + 10 + 3 * x] = ash32(agg[(base + nant) * ncell + c] as f64);
        }
    }
    let mut spec = Vec::new();
    if let Some(s) = &pr.spec {
        spec = vec![0f32; nc * SPEC_PLANES];
        if s.alive[b] {
            for f in 0..nc {
                for phi in 0..2 {
                    let a = (phi * nant) * nc;
                    let (mx, mn) = pair64(s.ant[a + p * nc + f], s.ant[a + q * nc + f]);
                    let k = f * SPEC_PLANES + 4 * phi;
                    spec[k] = ash32(s.e[b][phi * nc + f]);
                    spec[k + 1] = ash32(mx);
                    spec[k + 2] = ash32(mn);
                    spec[k + 3] = ash32(s.x[phi * nc + f]);
                }
            }
        }
    }
    let an = &pr.ant;
    let g = &an.grid;
    let na = g.nta * g.nja;
    let mut amp = vec![0f32; na * AMP_PLANES];
    for k in 0..na {
        for phi in 0..2 {
            let o = (k * 2 + phi) * nant;
            let (mx, mn) = pair64(an.z[o + p], an.z[o + q]);
            let (qmx, _) = pair64(an.q[o + p], an.q[o + q]);
            let t = k * AMP_PLANES + 3 * phi;
            amp[t] = ash32(mx);
            amp[t + 1] = ash32(mn);
            amp[t + 2] = ash32(qmx);
        }
    }
    let mut var = Vec::new();
    if has_var(pr.level) {
        let nv = g.var_cells();
        var = vec![0f32; nv * VAR_PLANES];
        for k in 0..nv {
            let (a, bq) = pair64(an.tt[k * nant + p], an.tt[k * nant + q]);
            let (c, dq) = pair64(an.tf[k * nant + p], an.tf[k * nant + q]);
            let t = k * VAR_PLANES;
            var[t] = ash32(a);
            var[t + 1] = ash32(bq);
            var[t + 2] = ash32(c);
            var[t + 3] = ash32(dq);
        }
    }
    Split {
        cell,
        spec,
        amp,
        var,
        alive,
    }
}

/// The materialised planes `(cell, inputs)` of one baseline.
fn materialise(inp: &Inputs, sp: &Split, pr: &Prepared) -> Vec<f32> {
    let nt = inp.ntime;
    let nc = inp.nchan;
    let n = inputs(pr.level).unwrap();
    let g = &pr.ant.grid;
    let mut h = vec![0f32; nt * nc * n];
    for t in 0..nt {
        for f in 0..nc {
            let c = t * nc + f;
            let o = c * n;
            let src = &sp.cell[c * 15..c * 15 + 15];
            if src[14] != 0.0 {
                h[o + n - 1] = 1.0;
                continue;
            }
            if !sp.alive {
                continue;
            }
            h[o..o + CELL_PLANES].copy_from_slice(&src[..CELL_PLANES]);
            let mut k = o + CELL_PLANES;
            if !sp.spec.is_empty() {
                h[k..k + SPEC_PLANES].copy_from_slice(&sp.spec[f * SPEC_PLANES..][..SPEC_PLANES]);
                k += SPEC_PLANES;
            }
            let ka = g.ta[t] * g.nja + f / AMP_DF;
            h[k..k + AMP_PLANES].copy_from_slice(&sp.amp[ka * AMP_PLANES..][..AMP_PLANES]);
            k += AMP_PLANES;
            if !sp.var.is_empty() {
                let kv = g.tv[t] * g.njv + f / VAR_DF;
                h[k..k + VAR_PLANES].copy_from_slice(&sp.var[kv * VAR_PLANES..][..VAR_PLANES]);
            }
        }
    }
    h
}

fn sizes(inp: &Inputs, level: usize, d: usize) -> i32 {
    let code = check(inp);
    if code != 0 {
        return code;
    }
    if inputs(level).is_none() || !(1..=3).contains(&d) {
        return 3;
    }
    0
}

/// Features `(nsel, ntime, nchan, inputs(level))` f32 of the baselines
/// `select` into `out`. Errors: 1 bad sizes, 2 an index out of range, 3 a
/// bad level or fit degree.
pub fn features(inp: &Inputs, level: usize, d: usize, select: &[u32], out: &mut [f32]) -> i32 {
    let code = sizes(inp, level, d);
    if code != 0 {
        return code;
    }
    let n = inputs(level).unwrap();
    let ncell = inp.ntime * inp.nchan;
    if out.len() != select.len() * ncell * n {
        return 1;
    }
    if select.iter().any(|&b| b as usize >= inp.nbl) {
        return 2;
    }
    let (start, order) = rows_by_baseline(inp);
    let pr = prepare(inp, &start, &order, level, d);
    out.par_chunks_mut(ncell * n)
        .zip(select.par_iter())
        .for_each(|(o, &b)| {
            let b = b as usize;
            let sp = split(inp, b, &order[start[b]..start[b + 1]], &pr);
            o.copy_from_slice(&materialise(inp, &sp, &pr));
        });
    0
}

/// The stem at each input's resolution, summed per cell, then F3's layers
/// and head: the rows' logits.
fn network(
    inp: &Inputs,
    rows: &[usize],
    sp: &Split,
    pr: &Prepared,
    w: &[f32],
) -> Vec<(usize, Vec<f32>)> {
    let nt = inp.ntime;
    let nc = inp.nchan;
    let n = inputs(pr.level).unwrap();
    let g = &pr.ant.grid;
    let ws = &w[..n * HIDDEN];
    let bs = &w[n * HIDDEN..n * HIDDEN + HIDDEN];
    let lin = |x: &[f32], k0: usize, acc: &mut [f32; HIDDEN]| {
        for (i, &v) in x.iter().enumerate() {
            if v != 0.0 {
                let r = &ws[(k0 + i) * HIDDEN..(k0 + i + 1) * HIDDEN];
                for o in 0..HIDDEN {
                    acc[o] += r[o] * v;
                }
            }
        }
    };
    let mut k = CELL_PLANES;
    let mut spec_part = Vec::new();
    if !sp.spec.is_empty() {
        spec_part = vec![[0f32; HIDDEN]; nc];
        for (f, acc) in spec_part.iter_mut().enumerate() {
            lin(&sp.spec[f * SPEC_PLANES..][..SPEC_PLANES], k, acc);
        }
        k += SPEC_PLANES;
    }
    let na = g.nta * g.nja;
    let mut amp_part = vec![[0f32; HIDDEN]; na];
    for (i, acc) in amp_part.iter_mut().enumerate() {
        lin(&sp.amp[i * AMP_PLANES..][..AMP_PLANES], k, acc);
    }
    k += AMP_PLANES;
    let mut var_part = Vec::new();
    if !sp.var.is_empty() {
        var_part = vec![[0f32; HIDDEN]; g.var_cells()];
        for (i, acc) in var_part.iter_mut().enumerate() {
            lin(&sp.var[i * VAR_PLANES..][..VAR_PLANES], k, acc);
        }
    }
    let wmask = &ws[(n - 1) * HIDDEN..n * HIDDEN];
    let ncell = nt * nc;
    let mut h = vec![0f32; ncell * HIDDEN];
    for t in 0..nt {
        for f in 0..nc {
            let c = t * nc + f;
            let mut acc = [0f32; HIDDEN];
            acc.copy_from_slice(bs);
            let src = &sp.cell[c * 15..c * 15 + 15];
            if src[14] != 0.0 {
                for o in 0..HIDDEN {
                    acc[o] += wmask[o];
                }
            } else if sp.alive {
                lin(&src[..CELL_PLANES], 0, &mut acc);
                let parts = [
                    spec_part.get(f),
                    amp_part.get(g.ta[t] * g.nja + f / AMP_DF),
                    if var_part.is_empty() {
                        None
                    } else {
                        var_part.get(g.tv[t] * g.njv + f / VAR_DF)
                    },
                ];
                for p in parts.into_iter().flatten() {
                    for o in 0..HIDDEN {
                        acc[o] += p[o];
                    }
                }
            }
            h[c * HIDDEN..(c + 1) * HIDDEN].copy_from_slice(&acc);
        }
    }
    let mut at = n * HIDDEN + HIDDEN;
    let mut next = vec![0f32; ncell * HIDDEN];
    for &dl in DILATIONS.iter() {
        let wl = &w[at..at + 9 * HIDDEN * HIDDEN];
        let bl = &w[at + 9 * HIDDEN * HIDDEN..at + 9 * HIDDEN * HIDDEN + HIDDEN];
        at += 9 * HIDDEN * HIDDEN + HIDDEN;
        f3flag::conv(&h, &mut next, nt, nc, HIDDEN, dl, wl, bl);
        std::mem::swap(&mut h, &mut next);
    }
    let wh = &w[at..at + HIDDEN];
    let bh = w[at + HIDDEN];
    rows.iter()
        .map(|&row| {
            let t = inp.time[row] as usize;
            let v = (0..nc)
                .map(|f| {
                    let o = (t * nc + f) * HIDDEN;
                    let mut acc = 0f32;
                    for kk in 0..HIDDEN {
                        acc += wh[kk] * h[o + kk];
                    }
                    acc + bh
                })
                .collect();
            (row, v)
        })
        .collect()
}

/// Logits `(row, chan)` f32 into `out`. Errors: 1 bad sizes, 2 an index out
/// of range, 3 a bad level or fit degree.
pub fn logits(inp: &Inputs, level: usize, d: usize, weights: &[f32], out: &mut [f32]) -> i32 {
    let code = sizes(inp, level, d);
    if code != 0 {
        return code;
    }
    let nc = inp.nchan;
    if out.len() != inp.baseline.len() * nc || weights.len() != weight_count(level) {
        return 1;
    }
    let (start, order) = rows_by_baseline(inp);
    let pr = prepare(inp, &start, &order, level, d);
    fill_logits(inp, &pr, &start, &order, weights, out);
    0
}

fn fill_logits(
    inp: &Inputs,
    pr: &Prepared,
    start: &[usize],
    order: &[usize],
    weights: &[f32],
    out: &mut [f32],
) {
    let nc = inp.nchan;
    let results: Vec<Vec<(usize, Vec<f32>)>> = (0..inp.nbl)
        .into_par_iter()
        .map(|b| {
            let rows = &order[start[b]..start[b + 1]];
            if rows.is_empty() {
                return Vec::new();
            }
            let sp = split(inp, b, rows, pr);
            network(inp, rows, &sp, pr, weights)
        })
        .collect();
    for rows in results {
        for (r, values) in rows {
            out[r * nc..(r + 1) * nc].copy_from_slice(&values);
        }
    }
}

/// Logits and W4's anomaly from one preparation pass (the method N5W4 at
/// inference; section 2b rule 4). Errors as `logits`.
pub fn logits_anomaly(
    inp: &Inputs,
    level: usize,
    d: usize,
    weights: &[f32],
    logit: &mut [f32],
    anom: &mut [f32],
) -> i32 {
    let code = sizes(inp, level, d);
    if code != 0 {
        return code;
    }
    let n = inp.baseline.len() * inp.nchan;
    if logit.len() != n || anom.len() != n || weights.len() != weight_count(level) {
        return 1;
    }
    let (start, order) = rows_by_baseline(inp);
    let pr = prepare(inp, &start, &order, level, d);
    fill_logits(inp, &pr, &start, &order, weights, logit);
    fill_anomaly(inp, &pr, anom);
    0
}

/// W4's per-cell anomaly `(row, chan)` f32 (section 3): the larger over the
/// baseline's two antennas of `max(|z_φ|, Q_φ, 𝒯_t, 𝒯_f)` at the cell's
/// blocks; NaN where none is defined. Errors as `logits`.
pub fn anomaly(inp: &Inputs, level: usize, d: usize, out: &mut [f32]) -> i32 {
    let code = sizes(inp, level, d);
    if code != 0 {
        return code;
    }
    if out.len() != inp.baseline.len() * inp.nchan {
        return 1;
    }
    let (start, order) = rows_by_baseline(inp);
    let pr = prepare(inp, &start, &order, level, d);
    fill_anomaly(inp, &pr, out);
    0
}

fn fill_anomaly(inp: &Inputs, pr: &Prepared, out: &mut [f32]) {
    let nc = inp.nchan;
    let an = &pr.ant;
    let g = &an.grid;
    let nant = inp.nant;
    let per_ant = |p: usize, t: usize, f: usize| -> f64 {
        let ka = g.ta[t] * g.nja + f / AMP_DF;
        let mut v = Vec::with_capacity(6);
        for phi in 0..2 {
            let o = (ka * 2 + phi) * nant + p;
            v.push(an.z[o].abs());
            v.push(an.q[o]);
        }
        if has_var(pr.level) {
            let kv = g.tv[t] * g.njv + f / VAR_DF;
            v.push(an.tt[kv * nant + p]);
            v.push(an.tf[kv * nant + p]);
        }
        f3flag::max_finite(&v)
    };
    out.par_chunks_mut(nc).enumerate().for_each(|(r, o)| {
        let b = inp.baseline[r] as usize;
        let t = inp.time[r] as usize;
        let (p, q) = (inp.ant1[b] as usize, inp.ant2[b] as usize);
        for (f, of) in o.iter_mut().enumerate() {
            *of = f3flag::max_finite(&[per_ant(p, t, f), per_ant(q, t, f)]) as f32;
        }
    });
}

/// Block shape `(nta, nja, ntv, njv)` of a scan's per-antenna quantities.
pub fn antenna_shape(ntime: usize, nchan: usize) -> (usize, usize, usize, usize) {
    let g = Grid::new(ntime, nchan);
    (g.nta, g.nja, g.ntv, g.njv)
}

/// The per-antenna quantities of sections 2c-2d into `z`, `q` (`(nta, nja,
/// 2, nant)`) and `tt`, `tf` (`(ntv, njv, nant)`, NaN without 2d), f64.
/// Errors as `logits`.
pub fn antenna_arrays(
    inp: &Inputs,
    level: usize,
    d: usize,
    z: &mut [f64],
    q: &mut [f64],
    tt: &mut [f64],
    tf: &mut [f64],
) -> i32 {
    let code = sizes(inp, level, d);
    if code != 0 {
        return code;
    }
    let (nta, nja, ntv, njv) = antenna_shape(inp.ntime, inp.nchan);
    let (na, nv) = (nta * nja * 2 * inp.nant, ntv * njv * inp.nant);
    if z.len() != na || q.len() != na || tt.len() != nv || tf.len() != nv {
        return 1;
    }
    let (start, order) = rows_by_baseline(inp);
    let pr = prepare(inp, &start, &order, level, d);
    z.copy_from_slice(&pr.ant.z);
    q.copy_from_slice(&pr.ant.q);
    tt.copy_from_slice(&pr.ant.tt);
    tf.copy_from_slice(&pr.ant.tf);
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn weight_counts_are_the_protocols() {
        assert_eq!(weight_count(0), 3201);
        assert_eq!(weight_count(1), 3169);
        assert_eq!(weight_count(2), 3105);
    }

    #[test]
    fn ash32_is_within_the_bar_of_f64() {
        // Section 2b rule 3 (Amendment 1): 2e-6 absolute for |x| <= 1e6,
        // 1e-7 relative above.
        let mut x = 1e-8f64;
        while x < 1e30 {
            for s in [-1.0, 1.0] {
                let v = s * x;
                let want = v.asinh();
                let err = (ash32(v) as f64 - want).abs();
                let bar = if x <= 1e6 { 2e-6 } else { 1e-7 * want.abs() };
                assert!(err <= bar, "{v} {err}");
            }
            x *= 1.37;
        }
        assert_eq!(ash32(0.0), 0.0);
        assert_eq!(ash32(f64::NAN), 0.0);
    }

    #[test]
    fn grids_follow_the_note() {
        let g = Grid::new(10, 2048);
        assert_eq!((g.nta, g.nja, g.ntv, g.njv), (5, 256, 1, 64));
        let g = Grid::new(27, 512);
        assert_eq!((g.nta, g.ntv), (13, 3));
        assert_eq!(g.ta[26], 12);
        assert_eq!(g.tv[26], 2);
        let g = Grid::new(30, 2048);
        assert_eq!(g.ntv, 3);
        let g = Grid::new(1, 8);
        assert_eq!((g.nta, g.ntv), (1, 1));
        let g = Grid::new(25, 8);
        assert_eq!(g.ntv, 3);
    }

    #[test]
    fn polish_recovers_antenna_terms_in_any_order() {
        let nant = 12;
        let mut a1 = Vec::new();
        let mut a2 = Vec::new();
        for p in 0..nant as u32 {
            for q in p + 1..nant as u32 {
                a1.push(p);
                a2.push(q);
            }
        }
        let truth: Vec<f64> = (0..nant).map(|k| 0.1 * (k as f64 * 0.7).sin()).collect();
        let mt: f64 = {
            let mut v = truth.clone();
            median(&mut v)
        };
        let y: Vec<f64> = (0..a1.len())
            .map(|b| 2.0 + truth[a1[b] as usize] + truth[a2[b] as usize])
            .collect();
        let empty = [0f32; 0];
        let flags = [0u8; 0];
        let none = [0u32; 0];
        let inp = Inputs {
            nchan: 1,
            nbl: a1.len(),
            ntime: 1,
            nant,
            data: &empty,
            flags: &flags,
            baseline: &none,
            time: &none,
            ant1: &a1,
            ant2: &a2,
        };
        let of = of_antenna(&inp);
        let (g, s) = polish(&y, &inp, &of);
        for k in 0..nant {
            assert!(
                // Amendment 1: simultaneous median updates stall at 0.016.
                (g[k] - (truth[k] - mt)).abs() < 0.02,
                "{k} {} {} {s}",
                g[k],
                truth[k] - mt
            );
        }
        assert!((s - (2.0 + 2.0 * mt)).abs() < 0.02);
        // Relabelled antennas: the same terms, permuted.
        let perm: Vec<u32> = (0..nant as u32)
            .map(|k| (k * 5 + 3) % nant as u32)
            .collect();
        let b1: Vec<u32> = a1.iter().map(|&a| perm[a as usize]).collect();
        let b2: Vec<u32> = a2.iter().map(|&a| perm[a as usize]).collect();
        let inp2 = Inputs {
            ant1: &b1,
            ant2: &b2,
            ..inp
        };
        let (g2, s2) = polish(&y, &inp2, &of_antenna(&inp2));
        assert_eq!(s, s2);
        for k in 0..nant {
            assert_eq!(g[k], g2[perm[k] as usize]);
        }
    }

    #[test]
    fn robust_fit_ignores_an_outlying_band() {
        let n = 64;
        let mut v: Vec<f64> = (0..n).map(|j| 0.01 * j as f64).collect();
        for x in v.iter_mut().skip(20).take(6) {
            *x += 5.0;
        }
        let fit = robust_fit(&v, 2);
        for j in (0..20).chain(26..n) {
            assert!((fit[j] - 0.01 * j as f64).abs() < 0.2, "{j}");
        }
        assert!(robust_fit(&v[..5], 3).iter().all(|x| x.is_nan()));
    }
}
