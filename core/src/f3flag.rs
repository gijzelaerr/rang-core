//! The F3 flagger (task F3, `research/f3-flagger.md`, section 3): per scan,
//! fifteen input planes per cross-correlation baseline on the (time,
//! channel) plane, built from noise-normalised amplitudes (time-local and
//! channel-local residuals per correlation, and per-antenna and whole-array
//! medians of their maxima), and F2's five-layer dilated 3×3 network with 15
//! inputs, in f32.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The features follow `rang.f3flag.features_numpy` (NumPy, float64) and the
//! network `rang.f3net.forward` (JAX); `tests/test_f3_flag.py` checks parity.
//! Three passes: per baseline the residual maxima (rayon over baselines),
//! per cell block the antenna and array medians (rayon over blocks), per
//! baseline the planes and the network (rayon over baselines).

use rayon::prelude::*;

/// Input planes per cell.
pub const INPUTS: usize = 15;
/// Hidden channels of every convolution.
pub const HIDDEN: usize = 8;
/// Dilations of the five 3×3 layers.
pub const DILATIONS: [usize; 5] = [1, 2, 4, 8, 16];
const RUNMED_HALF: usize = 16;
const MIN_PAIRS: usize = 16;
const MIN_AGG: usize = 3;
const MAD_SCALE: f64 = 1.4826;
const BLOCK: usize = 256;

/// Weights in `rang.f2flag.flat_weights` order: per layer W (ky, kx, cin,
/// cout) row-major then b; the head W (8, 1) then b (1).
pub fn weight_count() -> usize {
    let mut n = 0;
    let mut cin = INPUTS;
    for _ in DILATIONS {
        n += 9 * cin * HIDDEN + HIDDEN;
        cin = HIDDEN;
    }
    n + HIDDEN + 1
}

/// One scan's rows: `(row, chan, 4)` complex64 as interleaved f32, `(row,
/// chan)` flags (1 = flagged before the network), each row's baseline and
/// time index, and each baseline's two antennas.
pub struct Inputs<'a> {
    pub nchan: usize,
    pub nbl: usize,
    pub ntime: usize,
    pub nant: usize,
    pub data: &'a [f32],
    pub flags: &'a [u8],
    pub baseline: &'a [u32],
    pub time: &'a [u32],
    pub ant1: &'a [u32],
    pub ant2: &'a [u32],
}

fn check(inp: &Inputs) -> i32 {
    let nrow = inp.baseline.len();
    let nc = inp.nchan;
    if inp.time.len() != nrow
        || inp.data.len() != nrow * nc * 8
        || inp.flags.len() != nrow * nc
        || inp.ant1.len() != inp.nbl
        || inp.ant2.len() != inp.nbl
    {
        return 1;
    }
    if inp.baseline.iter().any(|&b| b as usize >= inp.nbl)
        || inp.time.iter().any(|&t| t as usize >= inp.ntime)
        || inp
            .ant1
            .iter()
            .chain(inp.ant2)
            .any(|&a| a as usize >= inp.nant)
    {
        return 2;
    }
    0
}

/// Median of the finite values, NumPy's convention (mean of the two middle
/// values for an even count); NaN if none. Reorders `v`.
fn median(v: &mut Vec<f64>) -> f64 {
    v.retain(|x| x.is_finite());
    let n = v.len();
    if n == 0 {
        return f64::NAN;
    }
    let k = n / 2;
    let (lo, mid, _) = v.select_nth_unstable_by(k, |a, b| a.partial_cmp(b).unwrap());
    let m = *mid;
    if n % 2 == 1 {
        m
    } else {
        let l = lo.iter().copied().fold(f64::NEG_INFINITY, f64::max);
        0.5 * (l + m)
    }
}

/// Rows of each baseline (counting sort).
fn rows_by_baseline(inp: &Inputs) -> (Vec<usize>, Vec<usize>) {
    let mut start = vec![0usize; inp.nbl + 1];
    for &b in inp.baseline {
        start[b as usize + 1] += 1;
    }
    for b in 0..inp.nbl {
        start[b + 1] += start[b];
    }
    let mut order = vec![0usize; inp.baseline.len()];
    let mut fill = start.clone();
    for (r, &b) in inp.baseline.iter().enumerate() {
        order[fill[b as usize]] = r;
        fill[b as usize] += 1;
    }
    (start, order)
}

/// One baseline's residual planes: `rt`, `rf` (cell, corr) f64 (NaN where
/// undefined), the flag plane, and whether the baseline has a noise scale.
struct Residuals {
    rt: Vec<f64>,
    rf: Vec<f64>,
    flagged: Vec<bool>,
    alive: bool,
}

fn residuals(inp: &Inputs, rows: &[usize]) -> Residuals {
    let nt = inp.ntime;
    let nc = inp.nchan;
    let ncell = nt * nc;
    let mut v = vec![[0f64; 8]; ncell];
    let mut flagged = vec![true; ncell];
    for &r in rows {
        let t = inp.time[r] as usize;
        for f in 0..nc {
            let cell = t * nc + f;
            let k = (r * nc + f) * 8;
            let x = &inp.data[k..k + 8];
            let fin = x.iter().all(|z| z.is_finite());
            flagged[cell] = inp.flags[r * nc + f] != 0 || !fin;
            for i in 0..8 {
                v[cell][i] = x[i] as f64;
            }
        }
    }
    // Noise per correlation from channel differences.
    let mut sigma = [f64::NAN; 4];
    let mut buf = Vec::with_capacity(2 * ncell);
    for (c, s) in sigma.iter_mut().enumerate() {
        buf.clear();
        for t in 0..nt {
            for f in 0..nc.saturating_sub(1) {
                let i = t * nc + f;
                if flagged[i] || flagged[i + 1] {
                    continue;
                }
                buf.push(v[i + 1][2 * c] - v[i][2 * c]);
                buf.push(v[i + 1][2 * c + 1] - v[i][2 * c + 1]);
            }
        }
        if buf.len() / 2 < MIN_PAIRS {
            continue;
        }
        let m = median(&mut buf);
        for x in buf.iter_mut() {
            *x = (*x - m).abs();
        }
        let sc = MAD_SCALE * median(&mut buf) / std::f64::consts::SQRT_2;
        if sc.is_finite() && sc > 0.0 {
            *s = sc;
        }
    }
    let mut valid: Vec<f64> = sigma.iter().copied().filter(|s| s.is_finite()).collect();
    let fallback = median(&mut valid);
    let alive = fallback.is_finite();
    for s in sigma.iter_mut() {
        if !s.is_finite() {
            *s = fallback;
        }
    }
    let mut rt = vec![f64::NAN; ncell * 4];
    let mut rf = vec![f64::NAN; ncell * 4];
    if !alive {
        return Residuals {
            rt,
            rf,
            flagged,
            alive,
        };
    }
    // a, then P (per channel), S (running median of P), g (per time).
    let mut a = vec![f64::NAN; ncell * 4];
    for cell in 0..ncell {
        if flagged[cell] {
            continue;
        }
        for c in 0..4 {
            a[cell * 4 + c] = v[cell][2 * c].hypot(v[cell][2 * c + 1]) / sigma[c];
        }
    }
    drop(v);
    let mut col = Vec::with_capacity(nt.max(nc));
    for c in 0..4 {
        let mut p = vec![f64::NAN; nc];
        for (f, pf) in p.iter_mut().enumerate() {
            col.clear();
            col.extend((0..nt).map(|t| a[(t * nc + f) * 4 + c]));
            *pf = median(&mut col);
        }
        let mut s = vec![f64::NAN; nc];
        for (f, sf) in s.iter_mut().enumerate() {
            let lo = f.saturating_sub(RUNMED_HALF);
            let hi = (f + RUNMED_HALF + 1).min(nc);
            col.clear();
            col.extend_from_slice(&p[lo..hi]);
            *sf = median(&mut col);
        }
        for t in 0..nt {
            col.clear();
            for f in 0..nc {
                let x = a[(t * nc + f) * 4 + c];
                if x.is_finite() && s[f].is_finite() && s[f] > 0.0 {
                    col.push(x / s[f]);
                }
            }
            let g = median(&mut col);
            for f in 0..nc {
                let i = (t * nc + f) * 4 + c;
                let x = a[i];
                rt[i] = x - p[f];
                rf[i] = x - g * s[f];
            }
        }
    }
    Residuals {
        rt,
        rf,
        flagged,
        alive,
    }
}

fn max_finite(x: &[f64]) -> f64 {
    let m = x
        .iter()
        .copied()
        .filter(|v| v.is_finite())
        .fold(f64::NEG_INFINITY, f64::max);
    if m.is_finite() { m } else { f64::NAN }
}

/// Pass 1 and 2: per antenna and array medians of u^t and u^f; layout
/// `[x][k][cell]` with k = nant for the array (x = 0 time, 1 channel).
fn aggregates(inp: &Inputs, start: &[usize], order: &[usize]) -> Vec<f32> {
    let ncell = inp.ntime * inp.nchan;
    let nbl = inp.nbl;
    // u planes [b][x][cell], NaN where undefined.
    let u: Vec<Vec<f32>> = (0..nbl)
        .into_par_iter()
        .map(|b| {
            let res = residuals(inp, &order[start[b]..start[b + 1]]);
            let mut out = vec![f32::NAN; 2 * ncell];
            if !res.alive {
                return out;
            }
            for cell in 0..ncell {
                if res.flagged[cell] {
                    continue;
                }
                out[cell] = max_finite(&res.rt[cell * 4..cell * 4 + 4]) as f32;
                out[ncell + cell] = max_finite(&res.rf[cell * 4..cell * 4 + 4]) as f32;
            }
            out
        })
        .collect();
    let nant = inp.nant;
    // Baselines of each antenna.
    let mut of_ant: Vec<Vec<usize>> = vec![Vec::new(); nant];
    for b in 0..nbl {
        of_ant[inp.ant1[b] as usize].push(b);
        if inp.ant2[b] != inp.ant1[b] {
            of_ant[inp.ant2[b] as usize].push(b);
        }
    }
    let nblock = ncell.div_ceil(BLOCK);
    let blocks: Vec<(usize, Vec<f32>)> = (0..nblock)
        .into_par_iter()
        .map(|blk| {
            let c0 = blk * BLOCK;
            let c1 = (c0 + BLOCK).min(ncell);
            let w = c1 - c0;
            let mut out = vec![f32::NAN; 2 * (nant + 1) * w];
            let mut buf = Vec::with_capacity(nbl);
            for x in 0..2 {
                for i in 0..w {
                    let cell = c0 + i;
                    for (k, bls) in of_ant.iter().enumerate() {
                        buf.clear();
                        buf.extend(bls.iter().map(|&b| u[b][x * ncell + cell] as f64));
                        buf.retain(|v| v.is_finite());
                        if buf.len() >= MIN_AGG {
                            out[(x * (nant + 1) + k) * w + i] = median(&mut buf) as f32;
                        }
                    }
                    buf.clear();
                    buf.extend((0..nbl).map(|b| u[b][x * ncell + cell] as f64));
                    buf.retain(|v| v.is_finite());
                    if buf.len() >= MIN_AGG {
                        out[(x * (nant + 1) + nant) * w + i] = median(&mut buf) as f32;
                    }
                }
            }
            (c0, out)
        })
        .collect();
    let mut agg = vec![f32::NAN; 2 * (nant + 1) * ncell];
    for (c0, out) in blocks {
        let w = out.len() / (2 * (nant + 1));
        for xk in 0..2 * (nant + 1) {
            agg[xk * ncell + c0..xk * ncell + c0 + w].copy_from_slice(&out[xk * w..xk * w + w]);
        }
    }
    agg
}

fn ash(x: f64) -> f32 {
    if x.is_finite() { x.asinh() as f32 } else { 0.0 }
}

fn pair(a: f32, b: f32) -> (f64, f64) {
    let (a, b) = (a as f64, b as f64);
    match (a.is_finite(), b.is_finite()) {
        (true, true) => (a.max(b), a.min(b)),
        (true, false) => (a, a),
        (false, true) => (b, b),
        _ => (f64::NAN, f64::NAN),
    }
}

/// One baseline's input planes, HWC `(t, f, INPUTS)`.
fn planes(inp: &Inputs, b: usize, rows: &[usize], agg: &[f32]) -> Vec<f32> {
    let nt = inp.ntime;
    let nc = inp.nchan;
    let ncell = nt * nc;
    let nant = inp.nant;
    let res = residuals(inp, rows);
    let mut h = vec![0f32; ncell * INPUTS];
    let (p, q) = (inp.ant1[b] as usize, inp.ant2[b] as usize);
    for cell in 0..ncell {
        let o = cell * INPUTS;
        if res.flagged[cell] {
            h[o + INPUTS - 1] = 1.0;
            continue;
        }
        if !res.alive {
            continue;
        }
        for c in 0..4 {
            h[o + c] = ash(res.rt[cell * 4 + c]);
            h[o + 4 + c] = ash(res.rf[cell * 4 + c]);
        }
        for x in 0..2 {
            let base = x * (nant + 1);
            let (mx, mn) = pair(
                agg[(base + p) * ncell + cell],
                agg[(base + q) * ncell + cell],
            );
            h[o + 8 + 3 * x] = ash(mx);
            h[o + 9 + 3 * x] = ash(mn);
            h[o + 10 + 3 * x] = ash(agg[(base + nant) * ncell + cell] as f64);
        }
    }
    h
}

/// Features `(nsel, ntime, nchan, INPUTS)` f32 of the baselines `select`
/// into `out`. Errors: 1 bad sizes, 2 an index out of range.
pub fn features(inp: &Inputs, select: &[u32], out: &mut [f32]) -> i32 {
    let code = check(inp);
    if code != 0 {
        return code;
    }
    let ncell = inp.ntime * inp.nchan;
    if out.len() != select.len() * ncell * INPUTS {
        return 1;
    }
    if select.iter().any(|&b| b as usize >= inp.nbl) {
        return 2;
    }
    let (start, order) = rows_by_baseline(inp);
    let agg = aggregates(inp, &start, &order);
    out.par_chunks_mut(ncell * INPUTS)
        .zip(select.par_iter())
        .for_each(|(o, &b)| {
            let b = b as usize;
            o.copy_from_slice(&planes(inp, b, &order[start[b]..start[b + 1]], &agg));
        });
    0
}

/// Logits `(row, chan)` f32 into `out`. Errors: 1 bad sizes, 2 an index out
/// of range.
pub fn logits(inp: &Inputs, weights: &[f32], out: &mut [f32]) -> i32 {
    let code = check(inp);
    if code != 0 {
        return code;
    }
    let nc = inp.nchan;
    if out.len() != inp.baseline.len() * nc || weights.len() != weight_count() {
        return 1;
    }
    let (start, order) = rows_by_baseline(inp);
    let agg = aggregates(inp, &start, &order);
    let results: Vec<Vec<(usize, Vec<f32>)>> = (0..inp.nbl)
        .into_par_iter()
        .map(|b| {
            let rows = &order[start[b]..start[b + 1]];
            if rows.is_empty() {
                return Vec::new();
            }
            let h = planes(inp, b, rows, &agg);
            network(inp, rows, h, weights)
        })
        .collect();
    for rows in results {
        for (r, values) in rows {
            out[r * nc..(r + 1) * nc].copy_from_slice(&values);
        }
    }
    0
}

/// The network on one baseline's planes; the rows' logits.
fn network(inp: &Inputs, rows: &[usize], mut h: Vec<f32>, w: &[f32]) -> Vec<(usize, Vec<f32>)> {
    let nt = inp.ntime;
    let nc = inp.nchan;
    let ncell = nt * nc;
    let mut at = 0;
    let mut cin = INPUTS;
    let mut next = vec![0f32; ncell * HIDDEN];
    for &d in DILATIONS.iter() {
        let wl = &w[at..at + 9 * cin * HIDDEN];
        let bl = &w[at + 9 * cin * HIDDEN..at + 9 * cin * HIDDEN + HIDDEN];
        at += 9 * cin * HIDDEN + HIDDEN;
        conv(&h, &mut next, nt, nc, cin, d, wl, bl);
        std::mem::swap(&mut h, &mut next);
        if next.len() != ncell * HIDDEN {
            next = vec![0f32; ncell * HIDDEN];
        }
        cin = HIDDEN;
    }
    let wh = &w[at..at + HIDDEN];
    let bh = w[at + HIDDEN];
    let mut out = Vec::with_capacity(rows.len());
    for &row in rows {
        let t = inp.time[row] as usize;
        let mut v = vec![0f32; nc];
        for (f, vf) in v.iter_mut().enumerate() {
            let o = (t * nc + f) * HIDDEN;
            let mut acc = 0f32;
            for k in 0..HIDDEN {
                acc += wh[k] * h[o + k];
            }
            *vf = acc + bh;
        }
        out.push((row, v));
    }
    out
}

/// One 3×3 dilated convolution with zero padding, bias and ReLU.
#[allow(clippy::too_many_arguments)]
fn conv(
    input: &[f32],
    out: &mut [f32],
    nt: usize,
    nc: usize,
    cin: usize,
    d: usize,
    w: &[f32],
    b: &[f32],
) {
    for t in 0..nt {
        for f in 0..nc {
            let mut acc = [0f32; HIDDEN];
            acc.copy_from_slice(b);
            for ky in 0..3 {
                let tt = t as isize + (ky as isize - 1) * d as isize;
                if tt < 0 || tt >= nt as isize {
                    continue;
                }
                for kx in 0..3 {
                    let ff = f as isize + (kx as isize - 1) * d as isize;
                    if ff < 0 || ff >= nc as isize {
                        continue;
                    }
                    let src = &input[(tt as usize * nc + ff as usize) * cin..][..cin];
                    let wk = &w[(ky * 3 + kx) * cin * HIDDEN..][..cin * HIDDEN];
                    for (ci, &v) in src.iter().enumerate() {
                        let wc = &wk[ci * HIDDEN..ci * HIDDEN + HIDDEN];
                        for co in 0..HIDDEN {
                            acc[co] += wc[co] * v;
                        }
                    }
                }
            }
            let o = &mut out[(t * nc + f) * HIDDEN..][..HIDDEN];
            for co in 0..HIDDEN {
                o[co] = acc[co].max(0.0);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn weight_count_is_the_protocols() {
        assert_eq!(weight_count(), 3433);
    }

    #[test]
    fn median_follows_numpy() {
        assert_eq!(median(&mut vec![3.0, 1.0, 2.0]), 2.0);
        assert_eq!(median(&mut vec![4.0, 1.0, 3.0, 2.0]), 2.5);
        assert!(median(&mut vec![f64::NAN]).is_nan());
        assert_eq!(median(&mut vec![f64::NAN, 5.0]), 5.0);
    }

    #[test]
    fn sizes_are_checked_and_logits_are_finite() {
        let (nc, nt, nant) = (40, 3, 3);
        let ubl = [(0u32, 1u32), (0, 2), (1, 2)];
        let nrow = nt * ubl.len();
        let data: Vec<f32> = (0..nrow * nc * 8)
            .map(|i| 1.0 + ((i * 7919) % 13) as f32)
            .collect();
        let flags = vec![0u8; nrow * nc];
        let baseline: Vec<u32> = (0..nrow as u32).map(|r| r % 3).collect();
        let time: Vec<u32> = (0..nrow as u32).map(|r| r / 3).collect();
        let ant1: Vec<u32> = ubl.iter().map(|x| x.0).collect();
        let ant2: Vec<u32> = ubl.iter().map(|x| x.1).collect();
        let inp = Inputs {
            nchan: nc,
            nbl: 3,
            ntime: nt,
            nant,
            data: &data,
            flags: &flags,
            baseline: &baseline,
            time: &time,
            ant1: &ant1,
            ant2: &ant2,
        };
        let weights = vec![0.01f32; weight_count()];
        let mut out = vec![0f32; nrow * nc];
        assert_eq!(logits(&inp, &weights, &mut out), 0);
        assert!(out.iter().all(|v| v.is_finite()));
        let mut feat = vec![0f32; nt * nc * INPUTS];
        assert_eq!(features(&inp, &[1], &mut feat), 0);
        assert!(feat.iter().all(|v| v.is_finite()));
        let mut short = vec![0f32; 3];
        assert_eq!(logits(&inp, &weights, &mut short), 1);
        assert_eq!(features(&inp, &[7], &mut feat), 2);
    }
}
