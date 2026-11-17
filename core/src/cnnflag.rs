// SPDX-License-Identifier: GPL-3.0-or-later
//! The F2 flagger's inference (task F2, `research/f2-flagger.md`, section 3):
//! per baseline, the six input planes of one scan's (time, channel) plane and
//! a five-layer dilated 3×3 convolutional network with a 1×1 head, in f32.
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The features follow `rang.f2flag.features` (NumPy, float64) and the
//! network `rang.f2flag.forward` (JAX); `tests/test_f2_cnnflag.py` checks
//! parity. Baselines run in parallel on rayon's pool.

use rayon::prelude::*;

/// Input planes per cell: four correlation z, the channel profile, the mask.
pub const INPUTS: usize = 6;
/// Hidden channels of every convolution.
pub const HIDDEN: usize = 8;
/// Dilations of the five 3×3 layers.
pub const DILATIONS: [usize; 5] = [1, 2, 4, 8, 16];
const PROFILE_HALF: usize = 16;
const MAD_SCALE: f64 = 1.4826;
const S_FLOOR: f64 = 1e-3;

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

/// Rows of one flagging call: `(row, chan, 4)` complex64 as interleaved f32,
/// `(row, chan)` flags (1 = flagged before the network), and each row's
/// baseline and time index.
pub struct Inputs<'a> {
    pub nchan: usize,
    pub nbl: usize,
    pub ntime: usize,
    pub data: &'a [f32],
    pub flags: &'a [u8],
    pub baseline: &'a [u32],
    pub time: &'a [u32],
    pub weights: &'a [f32],
}

/// Errors: 1 bad sizes, 2 an index out of range.
pub fn logits(inp: &Inputs, out: &mut [f32]) -> i32 {
    let nrow = inp.baseline.len();
    let nc = inp.nchan;
    if inp.time.len() != nrow
        || inp.data.len() != nrow * nc * 8
        || inp.flags.len() != nrow * nc
        || out.len() != nrow * nc
        || inp.weights.len() != weight_count()
    {
        return 1;
    }
    if inp.baseline.iter().any(|&b| b as usize >= inp.nbl)
        || inp.time.iter().any(|&t| t as usize >= inp.ntime)
    {
        return 2;
    }
    // Rows of each baseline (counting sort).
    let mut start = vec![0usize; inp.nbl + 1];
    for &b in inp.baseline {
        start[b as usize + 1] += 1;
    }
    for b in 0..inp.nbl {
        start[b + 1] += start[b];
    }
    let mut order = vec![0usize; nrow];
    let mut fill = start.clone();
    for (r, &b) in inp.baseline.iter().enumerate() {
        order[fill[b as usize]] = r;
        fill[b as usize] += 1;
    }
    let results: Vec<Vec<(usize, Vec<f32>)>> = (0..inp.nbl)
        .into_par_iter()
        .map(|b| baseline_logits(inp, &order[start[b]..start[b + 1]]))
        .collect();
    for rows in results {
        for (r, values) in rows {
            out[r * nc..(r + 1) * nc].copy_from_slice(&values);
        }
    }
    0
}

fn median(v: &mut [f64]) -> f64 {
    let n = v.len();
    if n == 0 {
        return f64::NAN;
    }
    v.sort_unstable_by(|a, b| a.partial_cmp(b).unwrap());
    if n % 2 == 1 {
        v[n / 2]
    } else {
        0.5 * (v[n / 2 - 1] + v[n / 2])
    }
}

fn mad(v: &mut [f64]) -> f64 {
    let m = median(v);
    for x in v.iter_mut() {
        *x = (*x - m).abs();
    }
    MAD_SCALE * median(v)
}

fn scale(s: f64) -> f64 {
    if s.is_finite() { s.max(S_FLOOR) } else { 1.0 }
}

/// One baseline: features, network, and the rows' logits.
fn baseline_logits(inp: &Inputs, rows: &[usize]) -> Vec<(usize, Vec<f32>)> {
    let nt = inp.ntime;
    let nc = inp.nchan;
    let ncell = nt * nc;
    // log|V| per cell and correlation, NaN where flagged, missing or nonfinite.
    let mut a = vec![f64::NAN; ncell * 4];
    let mut flagged = vec![true; ncell];
    for &r in rows {
        let t = inp.time[r] as usize;
        for f in 0..nc {
            let cell = t * nc + f;
            let fl = inp.flags[r * nc + f] != 0;
            flagged[cell] = fl;
            if fl {
                continue;
            }
            for c in 0..4 {
                let k = ((r * nc + f) * 4 + c) * 2;
                let re = inp.data[k] as f64;
                let im = inp.data[k + 1] as f64;
                let v = re.hypot(im).ln();
                a[cell * 4 + c] = if v.is_finite() { v } else { f64::NAN };
            }
        }
    }
    // Per-channel median over time, per correlation.
    let mut x = vec![f64::NAN; ncell * 4];
    let mut col = Vec::with_capacity(nt);
    for f in 0..nc {
        for c in 0..4 {
            col.clear();
            col.extend(
                (0..nt)
                    .map(|t| a[(t * nc + f) * 4 + c])
                    .filter(|v| !v.is_nan()),
            );
            let m = median(&mut col);
            for t in 0..nt {
                let i = (t * nc + f) * 4 + c;
                x[i] = a[i] - m;
            }
        }
    }
    // Per-correlation scale over the baseline's cells.
    let mut s = [1.0f64; 4];
    let mut all = Vec::with_capacity(ncell);
    for (c, sc) in s.iter_mut().enumerate() {
        all.clear();
        all.extend((0..ncell).map(|i| x[i * 4 + c]).filter(|v| !v.is_nan()));
        *sc = scale(mad(&mut all));
    }
    // Channel profile and its running-median residual.
    let mut p = vec![f64::NAN; nc];
    for (f, pf) in p.iter_mut().enumerate() {
        col.clear();
        col.extend(
            (0..nt)
                .map(|t| 0.5 * (a[(t * nc + f) * 4] + a[(t * nc + f) * 4 + 3]))
                .filter(|v| !v.is_nan()),
        );
        *pf = median(&mut col);
    }
    let mut r = vec![f64::NAN; nc];
    let mut win = Vec::with_capacity(2 * PROFILE_HALF + 1);
    for f in 0..nc {
        let lo = f.saturating_sub(PROFILE_HALF);
        let hi = (f + PROFILE_HALF + 1).min(nc);
        win.clear();
        win.extend(p[lo..hi].iter().copied().filter(|v| !v.is_nan()));
        r[f] = p[f] - median(&mut win);
    }
    all.clear();
    all.extend(r.iter().copied().filter(|v| !v.is_nan()));
    let sp = scale(mad(&mut all));
    let zp: Vec<f32> = r
        .iter()
        .map(|&v| {
            let z = v / sp;
            if z.is_finite() { z.asinh() as f32 } else { 0.0 }
        })
        .collect();
    // Input planes, HWC.
    let mut h = vec![0f32; ncell * INPUTS];
    for cell in 0..ncell {
        let o = cell * INPUTS;
        if flagged[cell] {
            h[o + 5] = 1.0;
            continue;
        }
        for c in 0..4 {
            let z = x[cell * 4 + c] / s[c];
            h[o + c] = if z.is_finite() { z.asinh() as f32 } else { 0.0 };
        }
        h[o + 4] = zp[cell % nc];
    }
    drop(a);
    drop(x);
    // Network.
    let w = inp.weights;
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
        assert_eq!(weight_count(), 2785);
    }

    #[test]
    fn flagged_rows_still_get_logits_and_sizes_are_checked() {
        let nc = 40;
        let nt = 3;
        let nrow = nt;
        let data: Vec<f32> = (0..nrow * nc * 8).map(|i| 1.0 + (i % 7) as f32).collect();
        let flags = vec![0u8; nrow * nc];
        let baseline = vec![0u32; nrow];
        let time: Vec<u32> = (0..nt as u32).collect();
        let weights = vec![0.01f32; weight_count()];
        let inp = Inputs {
            nchan: nc,
            nbl: 1,
            ntime: nt,
            data: &data,
            flags: &flags,
            baseline: &baseline,
            time: &time,
            weights: &weights,
        };
        let mut out = vec![0f32; nrow * nc];
        assert_eq!(logits(&inp, &mut out), 0);
        assert!(out.iter().all(|v| v.is_finite()));
        let mut short = vec![0f32; 3];
        assert_eq!(logits(&inp, &mut short), 1);
    }
}
